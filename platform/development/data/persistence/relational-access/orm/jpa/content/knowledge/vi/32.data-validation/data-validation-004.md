# Phân biệt Column nullable và ràng buộc kiểm tra giá trị

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Kiểm tra dữ liệu

Khi ánh xạ một Java entity vào cơ sở dữ liệu quan hệ, chúng ta thường thấy annotation:

~~~java
@Column(nullable = false)
private BigDecimal price;
~~~

Người mới học rất dễ hiểu thành: “Trường price đã được kiểm tra hợp lệ”. Cách hiểu này **chưa đủ**. Thuộc tính **nullable = false** hướng tới việc **không cho phép giá trị SQL NULL** tại cột tương ứng, đặc biệt khi JPA provider sinh schema. Nó **không diễn đạt** những yêu cầu như giá không âm, chuỗi không chứa toàn khoảng trắng, số lượng không vượt tồn kho, ngày kết thúc sau ngày bắt đầu hay mức giảm giá không lớn hơn giá gốc.

Ví dụ:

~~~text
price = NULL     → Vi phạm NOT NULL nếu schema có NOT NULL
price = -100     → KHÔNG vi phạm NOT NULL
price = 0        → Hợp lệ với NOT NULL, có thể sai nghiệp vụ khác
price = 100      → Hợp lệ nếu mọi điều kiện liên quan đều thỏa
~~~

Muốn **kiểm tra giá trị**, ứng dụng có thể dùng các ràng buộc Jakarta Bean Validation như **@NotNull**, **@NotBlank**, **@PositiveOrZero**, **@DecimalMin**, **@Size**; muốn ràng buộc được bảo vệ tại database ngay cả khi SQL được gửi từ công cụ khác, cần **NOT NULL**, **CHECK**, **UNIQUE**, **FOREIGN KEY** hoặc constraint thích hợp trong schema.

Bài này phân biệt rõ bốn lớp:

1. **JPA mapping**: Cách entity field được liên kết với cột và metadata DDL như @Column(nullable = false).
2. **Jakarta Bean Validation**: Kiểm tra object và trả thông tin vi phạm phù hợp với Java/API.
3. **Ràng buộc cơ sở dữ liệu**: NOT NULL, CHECK và các constraints được database thực thi bất kể writer là JPA, JDBC hay SQL bên ngoài.
4. **Quy tắc nghiệp vụ và giao dịch**: Những điều kiện cần tham chiếu nhiều dữ liệu, quyền truy cập, thời gian hoặc concurrency, không thể chỉ mô tả bằng nullable.

**Mục tiêu:** Đọc một field hoặc câu SQL và xác định nó chỉ cấm NULL, hay thật sự giới hạn **miền giá trị**, cũng như biết thời điểm nào và ở lớp nào lỗi được phát hiện.

## 1. Bắt đầu từ câu hỏi: NULL khác giá trị không hợp lệ thế nào?

Một cột trong bảng Product có thể chứa những giá trị khác nhau:

| Giá trị | NULL? | Có thể sai yêu cầu nghiệp vụ? |
|---|---|---|
| NULL | Có | Có, khi field bắt buộc |
| Chuỗi rỗng: "" | Không | Có, với tên sản phẩm bắt buộc có chữ |
| Chuỗi toàn khoảng trắng: "   " | Không | Có, khi không chấp nhận tên trắng |
| Số -10 | Không | Có, với tồn kho/giá không âm |
| Số 0 | Không | Có, nếu giá phải lớn hơn 0 |
| Số 999999999 | Không | Có, nếu vượt giới hạn nghiệp vụ |
| Ngày kết thúc trước ngày bắt đầu | Không nhất thiết | Có, với khoảng thời gian hợp lệ |
| Email "abc" | Không | Có, nếu cần cú pháp email |
| ID tham chiếu không tồn tại | Không | Có, theo FOREIGN KEY |
| SKU trùng với row khác | Không | Có, theo UNIQUE |

**Cấm NULL là một điều kiện nhỏ trong bài toán hợp lệ hóa dữ liệu.** Những điều kiện khác cần ràng buộc khác.

### 1.1. NULL trong SQL không giống null trong một DTO theo mọi trường hợp

Trong Java:

~~~java
String name = null;
~~~

biểu diễn một reference không có object. Trong SQL:

~~~sql
INSERT INTO products (name) VALUES (NULL);
~~~

là một SQL NULL value. Khi JPA ghi Java null vào cột nullable, nó có thể được chuyển thành SQL NULL; nhưng còn có các trường hợp:
- JSON không gửi field nào;
- JSON gửi field với null;
- Java field có default;
- Database có DEFAULT;
- Cột được bỏ qua khỏi INSERT;
- @Column(insertable = false) làm JPA không ghi cột.

Không thể suy ra rằng **JSON field vắng mặt**, **Java null**, **SQL NULL** và **database default** luôn mang cùng ý nghĩa.

### 1.2. NULL và giá trị 0

Một **Integer** có thể chứa null:

~~~java
private Integer stockQuantity;
~~~

Một **int** không có Java null, khởi tạo mặc định là 0:

~~~java
private int stockQuantity;
~~~

Vì vậy @Column(nullable = false) trên int có thể phù hợp với schema NOT NULL, nhưng **không chứng minh 0 là giá trị nghiệp vụ chấp nhận được**. Và nếu request không gửi stockQuantity, Java int có thể mang 0 mà không phát hiện field bị thiếu. DTO dùng Integer + @NotNull thường giúp phát hiện thiếu trường bắt buộc rõ hơn.

### 1.3. Không NULL nhưng vô nghĩa

~~~java
@Column(nullable = false)
private String sku;
~~~

Dù DB không cho NULL, nó vẫn có thể chấp nhận:

~~~text
sku = ""
sku = "     "
sku = "!!!"
sku = "A" lặp lại rất dài (nếu không có giới hạn length)
~~~

Cần thêm **kiểm tra chuỗi**, **giới hạn độ dài** và có thể **CHECK** hay **UNIQUE** ở DB.

## 2. @Column(nullable = false) thực sự làm gì?

Annotation thuộc Jakarta Persistence:

~~~java
import jakarta.persistence.Column;

@Column(nullable = false)
private String name;
~~~

Giá trị **nullable** của @Column mặc định là **true** nếu không khai báo.

### 2.1. Vai trò chính: metadata của cột và DDL generation

Khi provider được yêu cầu tạo schema, metadata:

~~~java
@Column(name = "product_name", nullable = false)
private String name;
~~~

có thể được chuyển thành DDL kiểu:

~~~sql
product_name VARCHAR(255) NOT NULL
~~~

Đây là mục tiêu quan trọng của nullable=false: mô tả nullability của column cho quá trình mapping và schema generation.

### 2.2. Annotation không tự sửa schema production đang tồn tại

Giả sử bảng products đang có:

~~~sql
product_name VARCHAR(255) NULL
~~~

Sau khi lập trình viên thêm:

~~~java
@Column(nullable = false)
private String name;
~~~

và ứng dụng chạy với cơ chế **không tự cập nhật schema**, cột production vẫn có thể cho NULL.

**Java annotation không phải migration đã được áp dụng.** Muốn database từ chối NULL thật, schema thực tế phải có NOT NULL. Hãy dùng công cụ migration như Flyway/Liquibase hoặc quy trình DDL được kiểm soát.

### 2.3. Có provider-level nullability checking không?

Một số JPA providers có thể phát hiện trường null trước khi gửi SQL tùy cấu hình/mapping, nhưng **không nên xem @Column(nullable = false) là thay thế portable cho Jakarta Bean Validation**.

Phân biệt:

- **Mapping metadata:** nullable=false.
- **Object validation:** @NotNull và các Bean Validation constraints.
- **Database enforcement:** schema đã có NOT NULL.

Không nên khẳng định cứ có @Column(nullable=false) thì **mọi trường hợp set null đều ném chính xác một Java validation exception ngay lúc gọi setter**. Setter thông thường chỉ gán field:

~~~java
product.setName(null); // Nếu có setter, không tự động gọi JPA validate.
~~~

Lỗi có thể chỉ xuất hiện khi flush/commit, hoặc không bị DB chặn nếu schema thật vẫn nullable.

### 2.4. DDL generation có thể bị tắt

Trong Spring Boot hoặc cấu hình Jakarta Persistence, schema có thể được quản lý bởi migration thay vì Hibernate tự sinh. Đây là thực hành phổ biến ở production.

Nếu schema không được auto-generate, @Column(nullable=false) **vẫn là thông tin trong model**, nhưng tính đúng đắn ở DB phụ thuộc DDL đã deploy.

### 2.5. Một số thuộc tính khác của @Column

~~~java
@Column(
    name = "unit_price",
    nullable = false,
    precision = 12,
    scale = 2,
    insertable = true,
    updatable = true
)
private BigDecimal price;
~~~

Những thuộc tính này có mục đích khác nhau:

| Thuộc tính | Mục đích chính | Không bảo đảm điều gì |
|---|---|---|
| name | Tên cột | Không xác thực nội dung |
| nullable | Nullability trong mapping/DDL | Không cấm -10 hay chuỗi trắng |
| length | Độ dài cột ký tự khi tạo DDL | Không tự thay @Size validation |
| precision | Độ chính xác số kiểu decimal khi tạo DDL | Không tự kiểm tra quy tắc kinh doanh |
| scale | Số chữ số thập phân lưu trữ | Không phải chính sách làm tròn tiền |
| unique | Gợi ý tạo uniqueness constraint qua schema generation | Không thay migration, không phát hiện trong setter |
| insertable | JPA có đưa cột vào INSERT không | Không ảnh hưởng SQL writer ngoài |
| updatable | JPA có đưa cột vào UPDATE không | Không cấm native SQL/trigger cập nhật |

Một cột **nullable=false, precision=12, scale=2** vẫn có thể nhận số âm nếu schema không có CHECK và application không có validation tương ứng.

### 2.6. @Column(nullable=false) không phải @NotNull

Hai annotation có thể trông giống về mục tiêu “bắt buộc có giá trị”, nhưng khác phạm vi:

~~~java
@Column(nullable = false)
private String name;
~~~

và:

~~~java
@NotNull
private String name;
~~~

**@Column** nằm ở metadata JPA/database mapping. **@NotNull** nằm ở Jakarta Bean Validation và kiểm tra trạng thái của object khi validation được kích hoạt. Chúng có thể bổ sung nhau.

## 3. NOT NULL ở cơ sở dữ liệu

Constraint SQL:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);
~~~

yêu cầu cột name không được lưu SQL NULL.

### 3.1. NOT NULL bảo vệ mọi đường ghi đi qua database

Nếu database đã có NOT NULL, nó chặn:

~~~sql
INSERT INTO products (id, name)
VALUES (1, NULL);
~~~

và:

~~~sql
UPDATE products
SET name = NULL
WHERE id = 1;
~~~

bất kể SQL phát từ:
- JPA provider;
- JDBC;
- Query tool;
- ETL job;
- Migration;
- Service khác;
- Stored procedure (trừ những behavior đặc biệt được DB cho phép).

Đây là lý do **DB constraint là tuyến bảo vệ cuối cùng cho dữ liệu persistent**.

### 3.2. NOT NULL không cấm chuỗi rỗng hoặc âm

~~~sql
INSERT INTO products (id, name)
VALUES (2, '');
~~~

thường có thể đi qua NOT NULL vì chuỗi rỗng không phải NULL. **Ngoại lệ cần chú ý:** một số database như Oracle có ngữ nghĩa riêng với empty string kiểu VARCHAR2, nên không được tuyên bố hành vi giống nhau trên mọi RDBMS.

Tương tự:

~~~sql
INSERT INTO products (id, name)
VALUES (3, '   ');
~~~

vẫn là dữ liệu không NULL ở nhiều database. Muốn cấm khoảng trắng, cần validation/check chuyên biệt.

### 3.3. NOT NULL có thể được báo ở flush hoặc commit

Trong JPA:

~~~java
Product p = new Product();
p.setName(null);
em.persist(p);
~~~

lệnh persist không nhất thiết INSERT ngay. Tùy ID generation và flush timing, SQL có thể được gửi sớm hoặc chỉ lúc flush/commit. Database báo NOT NULL violation khi câu DML tương ứng thực thi, không nhất thiết khi Java setter được gọi.

### 3.4. DEFAULT không tự cho phép NULL

Một cột:

~~~sql
quantity INTEGER NOT NULL DEFAULT 0
~~~

có default 0 nếu INSERT bỏ cột theo semantics DB. Nhưng:

~~~sql
INSERT INTO inventory(quantity) VALUES (NULL);
~~~

thường vẫn vi phạm NOT NULL; explicit NULL không giống omitted column. Nếu JPA luôn gửi cột với null thì default có thể không được sử dụng.

Vì vậy muốn dùng database default phải thiết kế mapping/INSERT behavior, không chỉ thêm @Column(nullable=false).

## 4. Ràng buộc kiểm tra giá trị: CHECK

**CHECK** là database constraint biểu diễn một biểu thức điều kiện trên dữ liệu row.

Ví dụ:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT ck_products_price_nonnegative
        CHECK (price >= 0),
    CONSTRAINT ck_products_quantity_nonnegative
        CHECK (quantity >= 0)
);
~~~

Lúc này database có **hai nhóm điều kiện riêng**:
- **NOT NULL:** giá và số lượng không được NULL;
- **CHECK:** giá và số lượng không được âm.

### 4.1. So sánh cụ thể

| Input price | NOT NULL | CHECK(price >= 0) | Kết quả nếu có cả hai |
|---:|---|---|---|
| NULL | Không thỏa | UNKNOWN | Bị NOT NULL từ chối |
| -10.00 | Thỏa | FALSE | Bị CHECK từ chối |
| 0.00 | Thỏa | TRUE | Được chấp nhận theo hai constraint này |
| 99.99 | Thỏa | TRUE | Được chấp nhận |
| 999999999999.99 | Thỏa | TRUE về mặt không âm | Có thể vượt precision của column |

**Một ràng buộc không thay thế hoàn toàn ràng buộc kia.**

### 4.2. CHECK trong SQL có ba giá trị logic

Một điểm rất dễ nhầm:

~~~sql
CHECK (price >= 0)
~~~

**không nhất thiết từ chối NULL**. SQL NULL so sánh với 0 cho kết quả **UNKNOWN**. Trong các database theo semantics CHECK thông dụng, CHECK từ chối khi biểu thức là FALSE; TRUE hoặc UNKNOWN không tự vi phạm.

Bởi vậy:

~~~sql
price NUMERIC(12, 2)
    CHECK (price >= 0)
~~~

có thể vẫn cho SQL NULL. Muốn bắt buộc có giá và không âm:

~~~sql
price NUMERIC(12, 2) NOT NULL
    CHECK (price >= 0)
~~~

Đây là khác biệt cốt lõi của bài: **NOT NULL kiểm tra sự hiện diện, CHECK kiểm tra điều kiện giá trị; đôi khi cần cả hai**.

### 4.3. CHECK có thể kiểm tra quan hệ giữa nhiều cột

Ví dụ giá khuyến mãi không vượt giá gốc:

~~~sql
CREATE TABLE product_prices (
    id BIGINT PRIMARY KEY,
    list_price NUMERIC(12, 2) NOT NULL,
    sale_price NUMERIC(12, 2) NOT NULL,
    CONSTRAINT ck_prices_nonnegative
        CHECK (list_price >= 0 AND sale_price >= 0),
    CONSTRAINT ck_sale_not_greater_than_list
        CHECK (sale_price <= list_price)
);
~~~

@Column(nullable=false) trên cả hai fields chỉ cấm NULL; nó **không biểu diễn sale_price <= list_price**.

### 4.4. CHECK không thể thay mọi business validation

Một số quy tắc có thể cần:
- Truy vấn số lượng tồn kho ở bảng khác;
- Kiểm tra quyền người dùng;
- So sánh với trạng thái giao dịch khác;
- Gọi external service;
- Quy tắc có thời gian hiện tại;
- Aggregation nhiều rows.

CHECK thông thường phù hợp nhất với điều kiện trên row/columns mà RDBMS hỗ trợ, không phải arbitrary Java business logic hoặc cross-row transaction protocol.

### 4.5. Tên constraint giúp debug

~~~sql
CONSTRAINT ck_products_price_nonnegative
    CHECK (price >= 0)
~~~

Tên rõ ràng giúp:
- Nhìn DB exception biết constraint nào lỗi;
- Viết migration thay đổi rule;
- Gắn mapping trong error handling;
- Tránh phụ thuộc thông điệp lỗi thô do database sinh.

Không xây API trả nguyên SQL exception message chứa SQL/parameters cho client; ánh xạ sang thông báo nghiệp vụ sau khi phân loại lỗi.

## 5. Jakarta Bean Validation: kiểm tra đối tượng Java

Jakarta Bean Validation đưa ra một tập constraints để mô tả **giá trị hợp lệ** của Java properties, parameters và return values. Khi có provider Bean Validation phù hợp, các annotations có thể được kiểm tra bởi:
- Lệnh gọi **Validator.validate(...)**;
- Tầng web khi dùng validation của request DTO;
- JPA lifecycle validation, nếu tích hợp và chế độ validation được bật;
- Service method validation, nếu framework/cấu hình hỗ trợ.

Ví dụ:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;

@NotBlank
private String name;

@NotNull
@PositiveOrZero
private BigDecimal price;
~~~

Ba constraints **@NotBlank**, **@NotNull** và **@PositiveOrZero** kiểm tra **những điều khác nhau**.

### 5.1. @NotNull

~~~java
@NotNull
private BigDecimal price;
~~~

Kiểm tra rằng reference **khác null**. Với value=BigDecimal("-100"), điều kiện @NotNull vẫn **thỏa**.

### 5.2. @NotBlank

~~~java
@NotBlank
private String name;
~~~

Áp cho CharSequence và kiểm tra giá trị không null, sau khi xét tính trắng không chỉ toàn khoảng trắng. Thích hợp cho trường tên bắt buộc có nội dung.

So sánh:

| name | @NotNull | @NotBlank |
|---|---|---|
| null | Vi phạm | Vi phạm |
| "" | Hợp lệ | Vi phạm |
| "   " | Hợp lệ | Vi phạm |
| "ABC" | Hợp lệ | Hợp lệ |

Với @NotBlank, chữ "ABC" hợp lệ về sự hiện diện, **không có nghĩa nó đã thỏa yêu cầu pattern/length/uniqueness**.

### 5.3. @NotEmpty

~~~java
@NotEmpty
private String tags;
~~~

Với String, @NotEmpty yêu cầu khác null và không rỗng, nhưng **không nhất thiết từ chối chuỗi chỉ chứa khoảng trắng**. Annotation này còn áp dụng cho các kiểu collection, map hoặc array được chuẩn hỗ trợ.

Với một tên sản phẩm cần ký tự có nghĩa, **@NotBlank** thường sát yêu cầu hơn @NotEmpty.

### 5.4. @Positive và @PositiveOrZero

~~~java
@Positive
private BigDecimal salePrice;
~~~

yêu cầu số **lớn hơn 0**.

~~~java
@PositiveOrZero
private BigDecimal stockValue;
~~~

yêu cầu số **lớn hơn hoặc bằng 0**.

Chú ý Bean Validation constraints như @PositiveOrZero thường **không tự coi null là lỗi**. Muốn bắt buộc phải có giá trị, kết hợp với **@NotNull**:

~~~java
@NotNull
@PositiveOrZero
private BigDecimal price;
~~~

### 5.5. @Min, @Max và Decimal constraints

~~~java
@NotNull
@Min(0)
@Max(1000)
private Integer quantity;
~~~

Diễn đạt khoảng số lượng từ 0 đến 1000.

Với BigDecimal:

~~~java
@NotNull
@DecimalMin(value = "0.00", inclusive = true)
@DecimalMax(value = "999999.99", inclusive = true)
private BigDecimal price;
~~~

Decimal constraints cho phép dùng chuỗi decimal tường minh, tránh nhầm giá trị dấu phẩy động literal.

**Không mặc định @Min(0) trên mọi loại floating-point đều cho cùng độ chính xác mong muốn với giá tiền**. Với tiền, nên sử dụng BigDecimal, xác định đơn vị và policy precision/scale/rounding.

### 5.6. @Size và @Column(length)

~~~java
@NotBlank
@Size(max = 200)
@Column(nullable = false, length = 200)
private String name;
~~~

- **@Size(max = 200):** kiểm tra độ dài giá trị Java khi validation chạy;
- **@Column(length = 200):** metadata về độ dài cột khi sinh DDL;
- **VARCHAR(200):** giới hạn do database column thực tế thực thi.

Những lớp này có thể có khác biệt về **cách đếm ký tự Unicode**, database collation và cách driver encode. Đừng khẳng định @Size(max=200) luôn có semantics byte/code point hoàn toàn trùng với mọi database VARCHAR(200).

### 5.7. @Digits và database NUMERIC precision/scale

~~~java
@NotNull
@PositiveOrZero
@Digits(integer = 10, fraction = 2)
@Column(
    nullable = false,
    precision = 12,
    scale = 2
)
private BigDecimal price;
~~~

**@Digits** kiểm tra số chữ số nguyên/thập phân hợp lệ ở Java khi validation chạy. **NUMERIC(12,2)** giới hạn cách DB lưu trữ giá trị, có thể liên quan việc rounding, overflow hoặc constraint error tùy DB.

Ví dụ giá "100.999" có thể bị @Digits(fraction=2) từ chối khi validation được kích hoạt; nếu bypass validation và gửi trực tiếp SQL, database có thể làm tròn hoặc xử lý khác theo dialect. Vì thế phải có policy chuẩn hóa BigDecimal rõ và không dựa vào database rounding ngầm.

### 5.8. @Pattern, @Email và giá trị hợp lệ theo cú pháp

~~~java
@NotBlank
@Pattern(regexp = "[A-Z0-9-]{3,64}")
@Column(nullable = false, length = 64)
private String sku;
~~~

Pattern diễn đạt hình dạng mã. Nó **không đảm bảo SKU là duy nhất giữa nhiều rows**. Uniqueness cần database constraint hoặc concurrency-safe application protocol, không chỉ Bean Validation.

Tương tự, @Email kiểm tra cú pháp email ở một mức nhất định; không chứng minh email thật tồn tại, có quyền sở hữu hay được phép sử dụng.

### 5.9. Bean Validation không tự ghi CHECK vào mọi database

Không nên nghĩ:

~~~java
@PositiveOrZero
private BigDecimal price;
~~~

đồng nghĩa schema production chắc chắn có:

~~~sql
CHECK (price >= 0)
~~~

Một provider có thể hỗ trợ tích hợp metadata constraints vào schema generation trong một số cấu hình, nhưng **không phải cam kết portable rằng mọi Bean Validation annotation đều được chuyển thành database CHECK**.

Khi database phải tự bảo vệ dữ liệu khỏi external SQL, hãy quản lý ràng buộc ở **migration/DDL thực tế**.

## 6. Bảng so sánh cốt lõi: @Column, Bean Validation và database

| Cơ chế | Ví dụ | Kiểm tra NULL? | Kiểm tra miền giá trị? | Hoạt động với SQL writer ngoài JPA? |
|---|---|---|---|---|
| @Column(nullable=false) | Metadata JPA | Mô tả không-null/DDL | Không | Chỉ nếu DB schema đã có constraint |
| @NotNull | Constraint Java | Có khi validation chạy | Chỉ không-null | Không |
| @NotBlank | Constraint Java String | Có khi validation chạy | Cấm rỗng/trắng | Không |
| @PositiveOrZero | Constraint Java numeric | Không tự cấm null | Cấm số âm | Không |
| @Size(max=200) | Constraint Java | Không tự cấm null | Giới hạn length | Không |
| SQL NOT NULL | name TEXT NOT NULL | Có | Không cấm số âm/chuỗi trắng | **Có** |
| SQL CHECK | CHECK(price >= 0) | **Không nhất thiết** | Có | **Có** |
| SQL UNIQUE | UNIQUE(sku) | Không thay NOT NULL | Không lặp giá trị theo DB semantics | **Có** |
| SQL FOREIGN KEY | customer_id REFERENCES customers | Không thay NOT NULL | Phải tham chiếu khóa hợp lệ nếu non-null | **Có** |
| Domain method | product.changePrice(...) | Tùy implementation | Bất kỳ business rule đã lập trình | Không nếu SQL bypass app |
| API validation | @Valid request DTO | Tùy constraints | Kiểm tra input sớm | Không |

Điểm quan trọng là **lớp phát hiện lỗi và phạm vi bảo vệ**. Một Product có đủ @NotNull và @PositiveOrZero ở Java vẫn có thể bị external SQL chèn giá âm nếu DB không có CHECK; ngược lại một NOT NULL/CHECK trên DB vẫn bảo vệ dữ liệu nếu application validation bị quên.

### 6.1. Phối hợp nhiều tầng không phải trùng lặp vô ích

Khi cùng quy tắc xuất hiện ở Java và SQL:

~~~java
@NotNull
@PositiveOrZero
@Column(nullable = false, precision = 12, scale = 2)
private BigDecimal price;
~~~

và:

~~~sql
price NUMERIC(12,2) NOT NULL
    CHECK (price >= 0)
~~~

vai trò khác nhau:
- Java: trả lỗi dễ hiểu sớm cho người dùng/client khi validation chạy;
- Domain: giữ invariants khi dùng entity methods;
- Database: tuyến bảo vệ cuối cùng dù có SQL writer khác.

Đây là **defense in depth**, không phải hai cơ chế thay thế nhau. Tuy nhiên cần giữ **chúng nhất quán** khi business rule thay đổi.

### 6.2. Nếu hai lớp không đồng nhất thì sao?

Ví dụ:
- @PositiveOrZero cho phép 0;
- CHECK(price > 0) cấm 0.

Một request giá 0 có thể qua Bean Validation nhưng thất bại lúc flush/commit. Đây là mâu thuẫn contract. Khi thay đổi business requirement, cần sửa **DTO/entity validation + database migration + tests + error handling**.

### 6.3. Không dùng @Column làm nguồn xác thực input duy nhất

Một POST JSON:

~~~json
{
  "name": "   ",
  "price": -500.00
}
~~~

không chứa SQL NULL. Dù entity fields đều @Column(nullable=false), hai giá trị vẫn có thể sai nghiệp vụ. Dùng @NotBlank/@PositiveOrZero hoặc business validation rõ, đồng thời đặt CHECK trong DB khi cần bảo vệ mọi writers.

## 7. @Basic(optional = false) khác @Column(nullable = false)

Ngoài @Column, JPA có **@Basic(optional = false)**:

~~~java
@Basic(optional = false)
private String name;
~~~

Theo JPA, optional=false biểu diễn thuộc tính basic là non-optional ở object persistence model. Nó có thể ảnh hưởng schema generation, kiểm tra nullability và mapping semantics tùy provider.

Trong khi:

~~~java
@Column(nullable = false)
private String name;
~~~

chủ yếu mô tả column nullability cho DDL.

### 7.1. Khi kết hợp

~~~java
@Basic(optional = false)
@Column(nullable = false)
private String name;
~~~

Cấu hình diễn đạt sự không tùy chọn ở cả object mapping lẫn DB column metadata. Tuy nhiên khi cần trả validation errors sớm, vẫn nên dùng @NotNull/@NotBlank theo yêu cầu. Và production schema vẫn phải có NOT NULL thật.

### 7.2. Mặc định của @Basic(optional)

Nếu không khai báo, optional mặc định là true. Với primitive Java field, optional có ý nghĩa khác vì primitive không thể null.

Không cần thêm cả @Basic(optional=false) và @Column(nullable=false) lên mọi field một cách máy móc; dùng có chủ đích, hiểu vai trò và mapping/DDL thực tế.

### 7.3. Quan hệ to-one còn có optional

Ví dụ:

~~~java
@ManyToOne(optional = false, fetch = FetchType.LAZY)
@JoinColumn(name = "category_id", nullable = false)
private Category category;
~~~

Ở đây:
- **@ManyToOne(optional=false):** quan hệ không tùy chọn ở mapping;
- **@JoinColumn(nullable=false):** foreign-key column phải không NULL khi schema được tạo;
- **FOREIGN KEY:** nếu có, đảm bảo ID tham chiếu tồn tại theo constraint DB.

**@Column(nullable=false) không phải annotation cho join column của quan hệ**. Dùng @JoinColumn khi ánh xạ FK relationship.

Một foreign key NOT NULL vẫn không thay thế những business rules như “category phải đang active”.

## 8. Những trường hợp @Column(nullable=false) không đủ

### 8.1. Giá không âm

~~~java
@Column(nullable = false)
private BigDecimal price;
~~~

không cấm -1. Cần:

~~~java
@NotNull
@PositiveOrZero
@Column(nullable = false)
private BigDecimal price;
~~~

và database CHECK khi muốn bảo vệ external writers:

~~~sql
CHECK (price >= 0)
~~~

### 8.2. Phần trăm giảm giá từ 0 đến 100

~~~java
@NotNull
@DecimalMin("0")
@DecimalMax("100")
@Column(nullable = false, precision = 5, scale = 2)
private BigDecimal discountPercent;
~~~

SQL:

~~~sql
discount_percent NUMERIC(5,2) NOT NULL
    CHECK (discount_percent BETWEEN 0 AND 100)
~~~

Không chỉ @Column(nullable=false, precision=5, scale=2); kiểu số vẫn có thể chứa các giá trị âm hoặc lớn hơn 100 trong miền precision nếu không có CHECK.

### 8.3. Chuỗi không chỉ toàn khoảng trắng

~~~java
@NotBlank
@Size(max = 200)
@Column(nullable = false, length = 200)
private String productName;
~~~

Một CHECK PostgreSQL-style có thể dùng:

~~~sql
CONSTRAINT ck_product_name_nonblank
CHECK (length(btrim(product_name)) > 0)
~~~

**btrim** là cú pháp PostgreSQL; database khác có hàm TRIM và semantics khác. Cần kiểm tra Unicode whitespace và normalization: @NotBlank ở Java không tự có cùng tập whitespace với SQL btrim. Muốn contract nhất quán, xác định policy rõ.

### 8.4. Ngày kết thúc sau ngày bắt đầu

~~~java
@Column(nullable = false)
private LocalDate startDate;

@Column(nullable = false)
private LocalDate endDate;
~~~

cấm NULL khi schema thực thi, nhưng không cấm endDate trước startDate.

SQL:

~~~sql
CONSTRAINT ck_valid_date_range
CHECK (end_date >= start_date)
~~~

Ở Java, có thể thêm class-level custom validation hoặc domain method kiểm tra hai fields. Ràng buộc cross-field không chỉ dùng @NotNull.

### 8.5. Trạng thái thuộc tập cho phép

~~~java
@Enumerated(EnumType.STRING)
@Column(nullable = false)
private ProductStatus status;
~~~

@Enumerated định nghĩa persistence representation của enum. Nó không tự bảo đảm mọi external SQL đều chỉ lưu những trạng thái được Java enum công nhận nếu DB schema là VARCHAR không CHECK.

SQL:

~~~sql
CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED'))
~~~

Ràng buộc này phải được đồng bộ với schema migrations và thay đổi enum trong application. Với các hệ nhiều phiên bản service cùng chạy, cần migration tương thích trước/sau deploy để tránh reject giá trị mới.

### 8.6. SKU duy nhất

~~~java
@NotBlank
@Column(nullable = false, unique = true, length = 64)
private String sku;
~~~

Uniqueness bảo vệ **tính duy nhất**, không phải chỉ sự hiện diện. Trong production, cần UNIQUE constraint thực tế. Một pre-check kiểu:

~~~java
if (!repository.existsBySku(sku)) {
    repository.save(product);
}
~~~

không bảo đảm tránh duplicate dưới concurrent requests; hai transactions có thể cùng thấy “chưa tồn tại”. Database UNIQUE vẫn là tuyến quyết định.

### 8.7. Số lượng tồn kho và race

~~~java
@Min(0)
@Column(nullable = false)
private int stockQuantity;
~~~

chỉ kiểm tra giá trị tại một thời điểm Java và/hoặc schema DDL. Khi nhiều writers cùng trừ tồn kho, cần concurrency control và DB CHECK:

~~~sql
CHECK (stock_quantity >= 0)
~~~

Khi nghiệp vụ reserve, dùng optimistic locking, pessimistic locking hoặc atomic conditional SQL phù hợp. Constraint giá trị và kiểm soát cạnh tranh là hai lớp khác nhau.

## 9. Ví dụ hoàn chỉnh: Product có nhiều lớp kiểm tra

Ta xây một Product vừa có JPA mapping, vừa có Bean Validation và những domain methods có chủ đích.

### 9.1. Entity Product

~~~java
package com.example.catalog;

import jakarta.persistence.*;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(
    name = "products",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_products_sku",
            columnNames = {"sku"}
        )
    }
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @NotBlank(message = "Tên sản phẩm không được để trống")
    @Size(max = 200)
    @Column(name = "name", nullable = false, length = 200)
    private String name;

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,64}")
    @Column(nullable = false, length = 64)
    private String sku;

    @NotNull
    @PositiveOrZero
    @Digits(integer = 10, fraction = 2)
    @Column(
        nullable = false,
        precision = 12,
        scale = 2
    )
    private BigDecimal price;

    @NotNull
    @Min(0)
    @Column(name = "stock_quantity", nullable = false)
    private Integer stockQuantity;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private ProductStatus status;

    protected Product() {}

    public Product(
            String sku,
            String name,
            BigDecimal price,
            Integer stockQuantity) {
        changeSku(sku);
        changeName(name);
        changePrice(price);
        setStock(stockQuantity);
        this.status = ProductStatus.DRAFT;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getName() { return name; }
    public String getSku() { return sku; }
    public BigDecimal getPrice() { return price; }
    public Integer getStockQuantity() { return stockQuantity; }
    public ProductStatus getStatus() { return status; }

    public void changeSku(String nextSku) {
        if (nextSku == null || nextSku.isBlank()) {
            throw new IllegalArgumentException(
                "SKU không được trống");
        }
        this.sku = nextSku;
    }

    public void changeName(String nextName) {
        if (nextName == null || nextName.isBlank()) {
            throw new IllegalArgumentException(
                "Tên sản phẩm không được trống");
        }
        this.name = nextName.trim();
    }

    public void changePrice(BigDecimal nextPrice) {
        Objects.requireNonNull(nextPrice, "price");
        if (nextPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Giá không được âm");
        }
        this.price = nextPrice;
    }

    public void setStock(Integer nextStock) {
        Objects.requireNonNull(nextStock, "stockQuantity");
        if (nextStock < 0) {
            throw new IllegalArgumentException(
                "Tồn kho không được âm");
        }
        this.stockQuantity = nextStock;
    }

    public void activate() {
        if (price.signum() <= 0) {
            throw new IllegalStateException(
                "Chỉ bán sản phẩm có giá dương");
        }
        this.status = ProductStatus.ACTIVE;
    }
}
~~~

Enum:

~~~java
package com.example.catalog;

public enum ProductStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}
~~~

**Những ví dụ này nhấn mạnh vai trò của nhiều lớp**, không phải yêu cầu mọi entity phải lặp lại mọi rule ở setter và annotation. Trong dự án thật, có thể tập trung invariants vào factory/domain methods và để Bean Validation mô tả ranh giới input/output phù hợp.

### 9.2. Rule nào nằm ở đâu?

| Field/quy tắc | JPA mapping | Bean Validation | Domain method | DB schema |
|---|---|---|---|---|
| name không NULL | @Column(nullable=false) | @NotBlank bao gồm không null | changeName không chấp nhận null | NOT NULL |
| name không trắng | Không | @NotBlank | changeName | CHECK nonblank nếu cần |
| name tối đa 200 | @Column(length=200) | @Size(max=200) | Có thể bổ sung | VARCHAR(200) |
| sku định dạng | @Column(length=64) | @Pattern, @NotBlank | changeSku có thể kiểm tra thêm | CHECK pattern nếu cần |
| sku duy nhất | @UniqueConstraint | Không thay uniqueness | Không đủ do race | UNIQUE |
| price không NULL | @Column(nullable=false) | @NotNull | requireNonNull | NOT NULL |
| price không âm | Không | @PositiveOrZero | changePrice | CHECK(price >= 0) |
| price độ chính xác | precision/scale | @Digits | Decimal policy | NUMERIC(12,2) |
| stock không NULL | @Column(nullable=false) | @NotNull | setStock | NOT NULL |
| stock không âm | Không | @Min(0) | setStock | CHECK(stock_quantity>=0) |
| status không NULL | @Column(nullable=false) | @NotNull | Constructor/transition | NOT NULL |
| status chỉ DRAFT/ACTIVE/ARCHIVED | @Enumerated(EnumType.STRING) | Enum type | Domain transitions | CHECK IN (...), nếu cần |
| ACTIVE cần price > 0 | Không | Custom class-level nếu cần | activate | CHECK cross-column nếu bắt buộc mọi writer |

### 9.3. DDL tương ứng khi dùng PostgreSQL

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY
        PRIMARY KEY,
    version BIGINT NOT NULL,
    name VARCHAR(200) NOT NULL,
    sku VARCHAR(64) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL,

    CONSTRAINT uk_products_sku
        UNIQUE (sku),

    CONSTRAINT ck_products_name_nonblank
        CHECK (length(btrim(name)) > 0),

    CONSTRAINT ck_products_price_nonnegative
        CHECK (price >= 0),

    CONSTRAINT ck_products_stock_nonnegative
        CHECK (stock_quantity >= 0),

    CONSTRAINT ck_products_status
        CHECK (status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')),

    CONSTRAINT ck_products_active_has_price
        CHECK (
            status <> 'ACTIVE'
            OR price > 0
        )
);
~~~

Ví dụ DDL không mặc định được JPA sinh đầy đủ từ các annotations trên entity. **Các CHECK phải được đưa vào migration** hoặc cấu hình provider-specific tương ứng, và kiểm tra schema đã deploy.

Chú ý nếu thêm trạng thái enum mới, cả Java enum lẫn constraint DB phải được cập nhật theo kế hoạch rollout an toàn.

### 9.4. Vì sao vừa domain method vừa constraint?

- Domain method giúp ngăn chuyển trạng thái sai trong logic Java.
- Bean Validation giúp hiển thị vi phạm cho request/entity theo cơ chế validation.
- Database CHECK bảo vệ dữ liệu nếu writer là JDBC, ETL hoặc service khác không đi qua Product.activate().
- Concurrency/versioning bảo vệ việc nhiều writers cùng thay đổi theo thời gian; CHECK không tự phân xử “ai thắng”.

Một giải pháp tốt không chỉ “có đủ annotations” mà phải chỉ rõ **đường ghi nào có thể bypass tầng nào**.

## 10. Bean Validation xảy ra khi nào?

Điều quan trọng là một annotation validation **không có nghĩa được chạy ở mọi phép gán**.

### 10.1. Validator API rõ ràng

Có thể gọi Jakarta Bean Validation trực tiếp:

~~~java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.ConstraintViolation;
import java.util.Set;

try (ValidatorFactory factory =
         Validation.buildDefaultValidatorFactory()) {

    Validator validator = factory.getValidator();

    Product product = ...;

    Set<ConstraintViolation<Product>> violations =
        validator.validate(product);

    for (ConstraintViolation<Product> violation : violations) {
        System.out.println(
            violation.getPropertyPath() + ": " +
            violation.getMessage()
        );
    }
}
~~~

Cần có Bean Validation provider, chẳng hạn implementation tương thích Jakarta Validation. **API annotation một mình không bảo đảm classpath đã có provider thực thi**.

### 10.2. Vi phạm được trả về dưới dạng tập kết quả

Validator.validate(product) thường trả:
- Tập rỗng nếu không có violation;
- Tập các ConstraintViolation nếu có lỗi.

Lời gọi validate bình thường **không tự ném ConstraintViolationException** chỉ vì có vi phạm. Application có thể quyết định ném exception khi cần:

~~~java
Set<ConstraintViolation<Product>> violations =
    validator.validate(product);

if (!violations.isEmpty()) {
    throw new ConstraintViolationException(
        "Dữ liệu Product không hợp lệ",
        violations
    );
}
~~~

**ConstraintViolationException** ở đây là **jakarta.validation.ConstraintViolationException**, khác với các constraint exceptions từ database/provider.

### 10.3. JPA lifecycle integration

Khi Jakarta Bean Validation được tích hợp với JPA và chế độ validation cho phép, provider có thể kiểm tra các constraints trước những lifecycle operations như INSERT/UPDATE trên entity.

Một Product được persist:

~~~java
em.persist(product);
em.flush();
~~~

có thể bị Bean Validation từ chối trước khi DB thực thi DML. Nhưng thời điểm cụ thể và những validation groups được chạy phụ thuộc cấu hình và lifecycle.

Không mặc định:
- @NotBlank luôn chạy ngay trong constructor;
- @NotNull luôn chạy ở setter;
- em.persist luôn ném ngay trước flush;
- Mọi schema đều tự có CHECK do Bean Validation sinh;
- Validation của request DTO tự được kích hoạt trên mọi Java method.

### 10.4. Persistence validation mode

Jakarta Persistence có các chế độ validation trong persistence-unit configuration, thường gồm:
- **AUTO**: tích hợp khi provider phù hợp hiện diện theo quy tắc runtime;
- **CALLBACK**: yêu cầu callback validation khi được cấu hình đúng;
- **NONE**: không thực thi tự động lifecycle validation qua JPA.

Tùy hệ Jakarta/JPA deployment, thuộc tính cấu hình có namespace như:

~~~text
jakarta.persistence.validation.mode
~~~

và các properties cho validation groups tại pre-persist/pre-update/pre-remove.

Do đó cùng entity có @NotNull có thể được kiểm tra ở JPA lifecycle trong một application nhưng không được kiểm tra tự động trong một application khác nếu validation disabled hoặc provider thiếu. Database constraints vẫn cần tồn tại nếu dữ liệu phải luôn đúng.

### 10.5. Validation ở Spring MVC

Request DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import java.math.BigDecimal;

public record CreateProductRequest(
    @NotBlank String sku,
    @NotBlank String name,
    @NotNull @PositiveOrZero BigDecimal price
) {}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductApplicationService service;

    public ProductController(
            ProductApplicationService service) {
        this.service = service;
    }

    @PostMapping
    public ProductView create(
            @Valid @RequestBody CreateProductRequest request) {
        return service.create(request);
    }
}
~~~

Ở Spring MVC, cần có validation integration/dependency phù hợp; **@Valid** yêu cầu validation của request DTO trong binding pipeline. Khi input sai, ứng dụng có thể trả một response 400 theo exception handling. Cơ chế này **khác** với lỗi database NOT NULL/CHECK phát sinh lúc commit.

### 10.6. @Valid không thay database constraints

Một tool bên ngoài gửi SQL:

~~~sql
UPDATE products
SET price = -100
WHERE id = 42;
~~~

không chạy Spring MVC, không gọi DTO validator, không gọi Product.changePrice. Nếu database không có CHECK, câu SQL có thể thành công. Vì vậy **đặt @Valid ở controller không bảo vệ mọi writers**.

### 10.7. Validation groups

Những operation khác nhau có thể cần validation khác nhau:
- Create: SKU bắt buộc;
- Update: SKU có thể không được thay đổi;
- Draft: Chưa cần giá bán dương;
- Activate: Cần price > 0.

Jakarta Validation cho phép **groups** và class-level/custom constraints để mô tả những tình huống này. Tuy nhiên không phải mọi business workflow nên được nén vào một graph validation groups phức tạp; đôi khi domain methods/commands riêng rõ ràng hơn.

### 10.8. Bean Validation không phải authorization

Constraint value như @PositiveOrZero không kiểm tra người dùng có được phép bán Product đó hay không. Authorization, tenant isolation và business permissions cần được xử lý ở application service và query boundary.

## 11. Thứ tự lỗi có thể xảy ra khi ghi qua JPA

Xem workflow:

~~~text
HTTP JSON
    |
    v
DTO binding
    |
    v
DTO validation (@Valid)
    |
    v
Application/domain service
    |
    v
Entity state changes
    |
    v
JPA lifecycle Bean Validation (nếu bật)
    |
    v
SQL INSERT / UPDATE tại flush/commit
    |
    v
Database constraints (NOT NULL, CHECK, UNIQUE, FK...)
    |
    v
Transaction COMMIT hoặc ROLLBACK
~~~

**Không phải mọi đường ghi đều đi qua tất cả các bước**. JDBC, native SQL và SQL script có thể bỏ qua phần DTO, domain methods và lifecycle Bean Validation.

### 11.1. Vi phạm ở DTO layer

Request:

~~~json
{
  "name": "   ",
  "sku": "ABC-01",
  "price": 100.00
}
~~~

Nếu DTO có @NotBlank, validation có thể từ chối trước khi service persist entity. Người dùng nhận phản hồi gần với business input hơn.

### 11.2. Vi phạm ở entity layer

Một service nội bộ tạo Product bằng constructor/builder không qua REST, sau đó gọi em.persist. Nếu entity Bean Validation hoạt động, @NotBlank/@PositiveOrZero có thể phát hiện lỗi trước SQL.

Tuy nhiên nếu constructor/domain methods đã throw IllegalArgumentException sớm hơn, đó là **domain exception**, không nhất thiết là Bean Validation exception.

### 11.3. Vi phạm ở database layer

Ngay cả nếu DTO/entity validation đúng, DB có thể từ chối:
- UNIQUE SKU vì một transaction khác vừa INSERT cùng SKU;
- CHECK cross-column;
- FK parent không tồn tại;
- NOT NULL do mapping khác hoặc SQL writer ngoài;
- Precision/scale vượt column type.

Đó là lý do service phải xử lý transaction rollback và map lỗi phù hợp; “@Valid pass” không phải lời hứa INSERT chắc chắn thành công.

### 11.4. Thời điểm phát hiện không luôn là em.persist

~~~java
Product product = ...;
em.persist(product);

// Có thể chưa phát INSERT theo provider/ID strategy.

em.flush(); // Có thể phát lỗi validation/database.

transaction.commit(); // Cũng có thể phát lỗi deferred/transaction.
~~~

Với IDENTITY generation có thể INSERT sớm để lấy ID; với SEQUENCE hoặc batching có thể trì hoãn DML. Đừng viết xử lý chỉ bắt lỗi quanh em.persist nếu dữ liệu quan trọng được lưu ở flush/commit.

### 11.5. Transaction lỗi phải rollback

Sau một exception do CHECK, UNIQUE hoặc NOT NULL ở database, không được giả định persistence context/transaction vẫn khỏe. Thực hành an toàn:
- Để lỗi lan qua transaction boundary;
- Rollback unit of work phù hợp;
- Không tiếp tục ghi trên transaction đã bị DB đánh dấu lỗi;
- Không gửi side effects “lưu thành công” trước commit.

Trong Spring, exception có thể được dịch sang DataIntegrityViolationException; trong JPA/provider có thể được bọc trong PersistenceException/RollbackException. Phân loại bằng cause chain và constraint metadata thay vì chỉ so chuỗi message.

## 12. SQL NULL và logic ba giá trị: vì sao CHECK cần NOT NULL?

SQL dùng các giá trị logic **TRUE, FALSE, UNKNOWN** với NULL.

### 12.1. Phép so sánh NULL

~~~sql
SELECT NULL >= 0;
~~~

về mặt SQL semantics không cho TRUE/FALSE mà cho UNKNOWN, với cách hiển thị phụ thuộc DB.

Tương tự:

~~~sql
SELECT NULL = NULL;
~~~

không có nghĩa TRUE. Để kiểm tra NULL trong WHERE, dùng:

~~~sql
WHERE price IS NULL
~~~

hoặc:

~~~sql
WHERE price IS NOT NULL
~~~

Không dùng price = NULL như một cách portable để tìm row chứa NULL.

### 12.2. Hệ quả với CHECK

~~~sql
CHECK (price >= 0)
~~~

chỉ từ chối khi biểu thức là FALSE. Nếu price=NULL, kết quả UNKNOWN có thể được CHECK chấp nhận. Nếu muốn cấm cả NULL:

~~~sql
price NUMERIC(12, 2) NOT NULL
    CHECK (price >= 0)
~~~

### 12.3. Hệ quả với ràng buộc liên cột

~~~sql
CHECK (sale_price <= list_price)
~~~

Nếu sale_price hoặc list_price NULL, biểu thức có thể là UNKNOWN và CHECK không tự từ chối. Để đảm bảo cả hai phải có:

~~~sql
list_price NUMERIC(12,2) NOT NULL,
sale_price NUMERIC(12,2) NOT NULL,
CHECK (sale_price <= list_price)
~~~

### 12.4. Nếu NULL có ý nghĩa nghiệp vụ?

Có khi sale_price là optional; NULL nghĩa “không có khuyến mãi”. Khi đó CHECK cần diễn đạt policy:

~~~sql
sale_price NUMERIC(12,2),
CHECK (
    sale_price IS NULL
    OR (
        sale_price >= 0
        AND sale_price <= list_price
    )
)
~~~

và list_price NOT NULL. Đây là trường hợp **nullable=true hoàn toàn hợp lệ**; không nên cấm NULL máy móc khi domain thực sự có trạng thái “chưa có”.

### 12.5. Nullability nên xuất phát từ domain model

Câu hỏi quan trọng không phải “có nên viết nullable=false cho mọi cột?” mà là:
- Field bắt buộc ở trạng thái nào?
- NULL biểu diễn dữ liệu chưa biết hay không áp dụng?
- Có giá trị mặc định hợp lệ không?
- SQL writer ngoài có cần gửi field không?
- API partial update phân biệt **omitted** và **explicit null** thế nào?

Một database schema tốt phân biệt **tính bắt buộc của dữ liệu** và **miền giá trị** theo contract nghiệp vụ, thay vì chỉ theo thói quen annotation.

## 13. Schema migration: annotation không phải ràng buộc đã deploy

Một ứng dụng có thể định nghĩa:

~~~java
@Column(nullable = false)
private BigDecimal price;
~~~

nhưng production database vẫn có:

~~~sql
price NUMERIC(12,2) NULL
~~~

do schema được tạo từ nhiều năm trước và Hibernate DDL generation đã tắt. Khi đó SQL ngoài JPA có thể ghi NULL vào cột; nếu JPA provider không chặn ở runtime, dữ liệu vẫn có thể sai.

### 13.1. Cần hai loại thay đổi rõ ràng

Khi biến một field từ optional thành required, thường phải thay đổi:

1. Java domain/API contract: Field được yêu cầu khi create/update.
2. Java validation: @NotNull hoặc @NotBlank phù hợp.
3. JPA mapping: nullable=false nếu muốn metadata đồng bộ.
4. DB schema migration: NOT NULL, CHECK và các constraints thực sự được áp.
5. Dữ liệu hiện hữu: làm sạch/backfill các rows không hợp lệ.
6. Writer bên ngoài: đảm bảo tuân thủ constraint sau deploy.
7. Tests/observability: xác minh API và DB đều reject giá trị sai.

Chỉ sửa annotation mà không sửa schema là chưa hoàn thành thay đổi contract.

### 13.2. Migration không được bỏ qua dữ liệu cũ

Ví dụ bảng đã có nhiều products:

~~~sql
SELECT COUNT(*)
FROM products
WHERE price IS NULL
   OR price < 0;
~~~

Nếu còn rows null/âm, thao tác thêm NOT NULL/CHECK có thể thất bại, hoặc nếu dùng cơ chế constraint chưa validate có thể để nợ dữ liệu tồn tại. Cần xác định chính sách sửa dữ liệu trước.

Không mặc định NULL price luôn nên đổi thành 0: **0 có thể mang nghĩa “miễn phí”** trong khi NULL có nghĩa “chưa định giá”. Backfill phải có quyết định nghiệp vụ, audit và kế hoạch rollback.

### 13.3. Ví dụ quy trình migration PostgreSQL

Giả sử cần bảo đảm price không NULL và không âm. Một chiến lược khái niệm:

~~~sql
-- 1) Khảo sát dữ liệu không hợp lệ.
SELECT id, price
FROM products
WHERE price IS NULL OR price < 0;

-- 2) Backfill theo quyết định nghiệp vụ,
-- không tự sửa tất cả NULL thành 0 nếu không hợp lệ.

-- 3) Khi dữ liệu sạch, bổ sung điều kiện.
ALTER TABLE products
    ALTER COLUMN price SET NOT NULL;

ALTER TABLE products
    ADD CONSTRAINT ck_products_price_nonnegative
    CHECK (price >= 0);
~~~

Đây là DDL **PostgreSQL minh họa**, không đại diện cú pháp mọi RDBMS. Trong bảng lớn, thao tác thêm constraint/NOT NULL có thể cần lock/scan và migration nhiều bước để hạn chế downtime.

### 13.4. Expand-and-contract khi có nhiều phiên bản ứng dụng

Một hệ microservices triển khai rolling:
1. Phiên bản cũ có thể vẫn gửi NULL/giá âm;
2. Phiên bản mới thêm @NotNull/@PositiveOrZero;
3. Schema DB thêm NOT NULL/CHECK.

Nếu triển khai constraint quá sớm, phiên bản cũ có thể bị lỗi khi vẫn ghi theo contract cũ. Nếu triển khai Java quá sớm mà DB chưa có constraint, external writer vẫn có thể ghi dữ liệu sai.

Cần kế hoạch:
- Triển khai writer tương thích với rule mới;
- Backfill dữ liệu cũ;
- Theo dõi violations;
- Deploy migration;
- Bỏ hỗ trợ contract cũ sau khi tất cả clients đã chuyển.

Trình tự chính xác tùy mức độ tương thích dữ liệu, database migration tool và uptime requirements.

### 13.5. Đổi một điều kiện là đổi nhiều lớp

Business đổi từ “price >= 0” sang “price > 0 cho ACTIVE, có thể 0 cho DRAFT”.

Có thể cần:
- Domain transition: activate() phải kiểm tra giá dương;
- Class-level validation khi status ACTIVE;
- SQL CHECK cross-column;
- API errors theo operation;
- Test các trạng thái DRAFT/ACTIVE/ARCHIVED;
- Migration có sự tồn tại trạng thái cũ.

Không chỉ đổi @PositiveOrZero thành @Positive trên price nếu DRAFT vẫn được phép giá 0.

### 13.6. Kiểm tra schema thực tế thay vì nhìn entity class

Các phương pháp:
- Dùng catalog của database/information_schema;
- Xem migration history;
- Query constraint definitions;
- Kiểm tra schema validation của provider;
- Chạy INSERT/UPDATE invalid data trong transaction test rồi rollback;
- So sánh DDL giữa các môi trường.

Một annotation đọc đúng trong source code không chứng minh database prod đã có cùng constraint.

### 13.7. Không dựa vào DDL auto-update để thay migration review

Hibernate auto-update/schema generation có ích trong dev/test, nhưng việc biến cột nullable thành NOT NULL hoặc thêm CHECK có dữ liệu hiện hữu, locks và downtime cần migration rõ ràng. Production nên kiểm soát DDL, review và lịch triển khai.

## 14. Thực hiện CHECK theo database hay ORM extension?

Jakarta Persistence có @Column(nullable) nhưng không cung cấp một annotation chuẩn portable đơn giản tương đương mọi SQL CHECK arbitrary expression cho mọi provider/dialect.

### 14.1. CHECK trong migration là đường portable về quản trị schema

SQL CHECK là khái niệm cơ sở dữ liệu quan hệ phổ biến nhưng cú pháp functions, regex và constraint validation có thể khác nhau.

Ví dụ có thể tương thích trên nhiều DB:

~~~sql
CONSTRAINT ck_products_price_nonnegative
    CHECK (price >= 0)
~~~

Còn cú pháp:

~~~sql
CHECK (length(btrim(name)) > 0)
~~~

cụ thể hơn theo PostgreSQL và không được giả định di chuyển nguyên vẹn qua mọi DB.

### 14.2. Provider-specific annotation cần kiểm tra phiên bản

Một số ORM như Hibernate cung cấp annotation/metadata mở rộng để khai báo SQL CHECK ở mapping. Khi dùng extension:
- Kiểm tra package/API tương ứng đúng phiên bản;
- Kiểm tra schema generation có thực sự bật không;
- Kiểm tra dialect sinh CHECK tương ứng;
- Không trông đợi annotation ORM tự apply migration trên bảng production đã tồn tại;
- Vẫn kiểm thử database constraint.

Không nhầm một annotation extension với **Jakarta Persistence standard**.

### 14.3. Domain check + database check thường cần cả hai

Ví dụ giá không âm:

~~~java
public void changePrice(BigDecimal nextPrice) {
    if (nextPrice == null
            || nextPrice.signum() < 0) {
        throw new IllegalArgumentException(
            "Giá không hợp lệ");
    }
    this.price = nextPrice;
}
~~~

DB:

~~~sql
CHECK (price >= 0)
~~~

Domain method giúp phát hiện lỗi sớm trong Java. DB CHECK bảo vệ nếu có external SQL bypass domain. Cả hai cần cùng quy tắc.

### 14.4. CHECK có điều kiện và nullable

Nếu salePrice có thể NULL khi chưa giảm giá:

~~~sql
sale_price NUMERIC(12,2) NULL,
list_price NUMERIC(12,2) NOT NULL,
CHECK (
    sale_price IS NULL
    OR sale_price BETWEEN 0 AND list_price
)
~~~

Không phải mọi cột đều nên nullable=false. Có những giá trị optional là **thiết kế domain đúng**; lúc đó CHECK cần phản ánh quy tắc giá trị khi trường có mặt.

### 14.5. Nếu yêu cầu phụ thuộc bảng khác

Ví dụ “stock reserve không được vượt tổng hàng sẵn có trong kho từ nhiều bảng”. Không nên cố đưa mọi thứ vào một CHECK nếu DB không hỗ trợ subquery trong CHECK hoặc điều kiện cần tính cạnh tranh cross-row.

Cần xét:
- Transaction/concurrency control;
- Atomic SQL update;
- Foreign keys;
- Triggers/stored procedures nếu có lý do;
- Domain service và DB constraints hỗ trợ;
- Eventual consistency nếu hệ phân tán.

**@Column(nullable=false)** hoàn toàn không giải quyết loại invariant phức tạp này.

## 15. Chẩn đoán lỗi: validation exception khác database constraint exception

Một API nhận product sai có thể thất bại ở các tầng khác nhau. Cần phân biệt để trả thông điệp phù hợp và không che lỗi hệ thống.

### 15.1. Các loại lỗi thường gặp

| Lớp | Ví dụ nguyên nhân | Java exception hoặc kết quả thường thấy |
|---|---|---|
| DTO validation | @NotBlank(name) fail ở Spring MVC | Binding/validation exception của Spring MVC |
| Bean Validator.validate | @PositiveOrZero fail | ConstraintViolation collection |
| JPA lifecycle Bean Validation | Entity price âm khi pre-persist/update | jakarta.validation.ConstraintViolationException nếu provider tích hợp |
| Domain method | changePrice(-10) | IllegalArgumentException / domain exception |
| Database NOT NULL | price SQL NULL | JDBC SQL exception, JPA PersistenceException wrapper |
| Database CHECK | price SQL -10 | DB constraint exception, JPA/Spring wrapper |
| Database UNIQUE | SKU bị trùng | DataIntegrityViolationException hoặc provider/SQL exception |
| Foreign key | Category ID không tồn tại | SQL integrity violation |
| Optimistic locking | @Version stale | OptimisticLockException hoặc wrapper |
| Transaction/connection | DB connection lỗi | Persistence/DataAccess exception phù hợp |

Bảng mang tính định hướng. Exception cụ thể tùy JPA provider, transaction manager, driver và tầng exception translation.

### 15.2. jakarta.validation.ConstraintViolationException

Lỗi Bean Validation:

~~~java
catch (jakarta.validation.ConstraintViolationException ex) {
    ex.getConstraintViolations()
        .forEach(v -> {
            System.out.println(
                v.getPropertyPath() + ": " +
                v.getMessage());
        });
}
~~~

Đây là vi phạm constraints trên Java object. Nó khác với SQL constraint violation dù tên “ConstraintViolation” dễ nhầm.

### 15.3. Database constraint exception

Khi DB từ chối SQL:

~~~sql
INSERT INTO products (sku, name, price, stock_quantity, status)
VALUES ('ABC-01', 'Item', -100, 0, 'DRAFT');
~~~

database có thể báo tên **ck_products_price_nonnegative** và SQLSTATE/error code tương ứng. Qua Hibernate/Spring nó có thể được bọc trong nhiều exception layers.

Không giả định database exception luôn là jakarta.validation.ConstraintViolationException; đây thường là **database integrity violation**, không phải Bean Validation.

### 15.4. Spring DataIntegrityViolationException

Trong Spring applications, những vi phạm NOT NULL/CHECK/UNIQUE/FK thường có thể được dịch thành **org.springframework.dao.DataIntegrityViolationException** hoặc exception con/cause tương ứng.

Tuy nhiên:
- Không map mọi DataIntegrityViolationException thành một lỗi field duy nhất;
- Không mặc định exception xảy ra ngay tại repository.save;
- Không trả raw constraint details chứa SQL cho client;
- Không dựa duy nhất vào message string mà thiếu SQLSTATE/constraint name/cause classification.

### 15.5. Lỗi xảy ra tại flush hoặc commit

~~~java
@Transactional
public void createProduct(CreateProductRequest request) {
    Product product = ...;
    em.persist(product);

    // Method có thể return mà SQL chưa hoàn tất.
}
~~~

Trong Spring, transaction interceptor commit sau khi method body return; lỗi DB có thể xuất hiện ngoài try/catch đặt trong body. Cần thiết kế global exception handling/application boundary đủ rộng.

Nếu cần đẩy kiểm tra sớm trong method, có thể gọi em.flush(), nhưng **flush không commit** và không loại trừ các lỗi có thể xuất hiện sau đó.

### 15.6. HTTP status cho input không hợp lệ

Có thể chọn:
- **400 Bad Request** cho request DTO validation/binding error;
- **422 Unprocessable Content** cho business validation failure tùy API contract;
- **409 Conflict** cho uniqueness/state conflict khi phù hợp;
- **500** cho lỗi hệ thống không được mong đợi.

Không coi mỗi lỗi database CHECK là lỗi do client nếu SQL được sinh sai bởi code nội bộ. Cần phân loại lỗi theo ownership, data contract và policy.

### 15.7. Không gửi exception từ database thẳng cho user

Raw SQL errors có thể chứa:
- Tên bảng/cột nội bộ;
- SQL fragment hoặc parameter;
- Dữ liệu nhạy cảm;
- Thông tin về schema;
- Stack trace.

Thay bằng response có code và thông điệp ổn định:

~~~json
{
  "code": "PRODUCT_PRICE_INVALID",
  "field": "price",
  "message": "Giá phải lớn hơn hoặc bằng 0."
}
~~~

Log backend nên giữ correlation ID, exception type và constraint name cần thiết để debug, không lộ secret hoặc dữ liệu cá nhân không cần thiết.

## 16. SQL writer bên ngoài JPA: vì sao database constraints quan trọng?

Giả sử có một job ETL ghi thẳng bảng products:

~~~sql
UPDATE products
SET price = -100
WHERE id = 42;
~~~

Các lớp sau **không được gọi**:
- Spring @Valid request DTO;
- Bean Validator trên entity;
- Product.changePrice();
- JPA lifecycle callbacks;
- JPA @Column mapping.

Nếu database chỉ có:

~~~sql
price NUMERIC(12,2) NOT NULL
~~~

thì -100 **không vi phạm NOT NULL**. Nếu database thêm:

~~~sql
CONSTRAINT ck_products_price_nonnegative
    CHECK (price >= 0)
~~~

thì DB có thể từ chối câu UPDATE đó.

### 16.1. Với batch data import

Một import file chứa:
- product_name = "Item";
- price = -200;
- quantity = -5.

Nếu import đi qua DTO/validation/domain, lỗi có thể được chặn trước SQL. Nếu import chạy COPY/INSERT trực tiếp, chỉ database constraints và import-specific validation bảo vệ state.

Nên thiết kế:
1. Staging/import validation;
2. Error reporting theo dòng;
3. Database NOT NULL/CHECK/UNIQUE/FK;
4. Transaction/chunking phù hợp;
5. Quarantine rows sai thay vì làm bẩn bảng chính;
6. Metrics/alerts cho violations.

### 16.2. CHECK có giúp ứng dụng Java luôn nhận giá mới không?

Không. CHECK chỉ đảm bảo giá lưu ở DB thỏa biểu thức. Nếu entity managed trong persistence context đang giữ giá cũ, CHECK không tự gọi em.refresh. Không nhầm **tính hợp lệ dữ liệu** với **tính mới của dữ liệu**.

### 16.3. CHECK có giúp tránh lost update không?

Không đủ. Hai transactions có thể cùng ghi các giá trị hợp lệ, nhưng transaction sau ghi đè thay đổi transaction trước. Cần optimistic @Version, locking hoặc conditional update phù hợp. Giá luôn không âm không đồng nghĩa mọi update đã giữ nguyên ý định người dùng.

### 16.4. UNIQUE và concurrency

Một Java pre-check:

~~~java
if (!productRepository.existsBySku(sku)) {
    productRepository.save(product);
}
~~~

có thể pass ở hai concurrent transactions. Cả hai cố INSERT SKU giống nhau; chỉ DB UNIQUE constraint quyết định một row phải thất bại. @Column(nullable=false) và @Pattern không giải quyết uniqueness across rows.

### 16.5. FOREIGN KEY và optionality

Cột category_id có thể:
- **NULL** nếu relationship optional;
- **NOT NULL** nếu bắt buộc;
- **REFERENCES categories(id)** để đảm bảo giá trị ID tồn tại.

FK với category_id nullable vẫn có thể cho NULL theo semantics DB. Muốn bắt buộc Category và reference valid, thường cần **NOT NULL + FOREIGN KEY**, tương tự pattern NOT NULL + CHECK cho giá.

### 16.6. Constraint không được viết thành giải pháp cho quyền truy cập

Một CHECK(price >= 0) không quyết định user nào được sửa giá. Authorization và tenant isolation cần có ở tầng application/database security phù hợp. Không suy ra "DB có constraints" là đã an toàn với mọi request.

## 17. Kiểm thử Bean Validation: khác database constraints

Để xác nhận các quy tắc ở Java, có thể dùng Jakarta Validator và JUnit 5, độc lập với database.

### 17.1. DTO dành cho validation test

~~~java
import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public record ProductInput(
    @NotBlank @Size(max = 200)
    String name,

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,64}")
    String sku,

    @NotNull @PositiveOrZero
    @Digits(integer = 10, fraction = 2)
    BigDecimal price,

    @NotNull @Min(0)
    Integer quantity
) {}
~~~

Test cần một **Validator** đã được khởi tạo từ ValidatorFactory, JUnit assertions và các imports tương ứng.

### 17.2. Tên toàn khoảng trắng

~~~java
@Test
void whitespaceNameIsInvalid() {
    ProductInput input = new ProductInput(
        "   ", "ABC-001",
        new BigDecimal("100.00"), 3
    );

    Set<ConstraintViolation<ProductInput>> violations =
        validator.validate(input);

    assertTrue(violations.stream().anyMatch(v ->
        v.getPropertyPath().toString().equals("name")
    ));
}
~~~

Nếu chỉ gắn @NotNull cho name, chuỗi "   " vẫn khác null và có thể vượt qua; @NotBlank biểu diễn ý nghĩa sát hơn.

### 17.3. Giá âm không phải NULL

~~~java
@Test
void negativePriceIsInvalid() {
    ProductInput input = new ProductInput(
        "Bàn phím", "ABC-001",
        new BigDecimal("-1.00"), 3
    );

    assertTrue(validator.validate(input).stream()
        .anyMatch(v ->
            v.getPropertyPath().toString().equals("price")
        ));
}
~~~

Với @NotNull đơn độc, price=-1 không vi phạm. Với @PositiveOrZero, nó vi phạm.

### 17.4. NULL khác 0

~~~java
@Test
void nullAndZeroHaveDifferentMeanings() {
    ProductInput missing = new ProductInput(
        "Item", "ABC-001", null, 3
    );
    ProductInput free = new ProductInput(
        "Item", "ABC-002", BigDecimal.ZERO, 3
    );

    assertFalse(validator.validate(missing).isEmpty());
    assertTrue(validator.validate(free).isEmpty());
}
~~~

Test thể hiện rằng **0 hợp lệ với @PositiveOrZero**. Nếu business cấm giá 0, phải đặt ràng buộc mạnh hơn, không thay đổi chỉ thuộc tính nullable.

### 17.5. Độ chính xác thập phân

~~~java
@Test
void rejectsMoreThanTwoFractionDigits() {
    ProductInput input = new ProductInput(
        "Item", "ABC-001",
        new BigDecimal("10.999"), 3
    );

    assertFalse(validator.validate(input).isEmpty());
}
~~~

@Digits(fraction=2) có thể từ chối giá có ba chữ số phần thập phân trước SQL. Database NUMERIC(12,2) có thể xử lý bằng cách làm tròn hoặc báo lỗi tùy dialect và giá trị. Không để database quyết định rounding policy cho tiền một cách ngầm định.

### 17.6. ConstraintViolationException từ đâu?

Validator.validate trả **tập vi phạm**, thường không ném exception chỉ vì có violation. Nếu application muốn ném:

~~~java
Set<ConstraintViolation<ProductInput>> violations =
    validator.validate(input);

if (!violations.isEmpty()) {
    throw new jakarta.validation.ConstraintViolationException(
        "Dữ liệu không hợp lệ", violations
    );
}
~~~

Nên phân biệt exception này với SQL constraint error do database ném tại INSERT/UPDATE.

## 18. Integration test: chứng minh DB NOT NULL và CHECK

Những tests này xác minh **schema thực tế**, không phải chỉ đọc annotations Java.

### 18.1. Schema test trên PostgreSQL

~~~sql
CREATE TABLE constraint_demo (
    id BIGINT PRIMARY KEY,
    price NUMERIC(12,2) NOT NULL,
    CONSTRAINT ck_demo_price_nonnegative
        CHECK (price >= 0)
);
~~~

Sử dụng database thật/Testcontainers và DataSource JDBC. Không giả định H2 có mọi hành vi giống PostgreSQL/MySQL/Oracle.

### 18.2. Test SQL NULL bị từ chối

~~~java
@Test
void databaseRejectsNull() throws Exception {
    try (Connection c = dataSource.getConnection()) {
        c.setAutoCommit(false);

        try (PreparedStatement ps = c.prepareStatement(
                "INSERT INTO constraint_demo(id, price) VALUES (?, ?)"
        )) {
            ps.setLong(1, 901L);
            ps.setNull(2, Types.NUMERIC);

            assertThrows(
                SQLException.class,
                ps::executeUpdate
            );
        } finally {
            c.rollback();
        }
    }
}
~~~

Test cần imports java.sql.Connection, PreparedStatement, Types, SQLException và JUnit 5 assertThrows. DB NOT NULL từ chối NULL, không cần JPA lifecycle validation.

### 18.3. Test giá âm bị CHECK từ chối

~~~java
@Test
void databaseRejectsNegative() throws Exception {
    try (Connection c = dataSource.getConnection()) {
        c.setAutoCommit(false);

        try (PreparedStatement ps = c.prepareStatement(
                "INSERT INTO constraint_demo(id, price) VALUES (?, ?)"
        )) {
            ps.setLong(1, 902L);
            ps.setBigDecimal(
                2, new BigDecimal("-100.00")
            );

            assertThrows(
                SQLException.class,
                ps::executeUpdate
            );
        } finally {
            c.rollback();
        }
    }
}
~~~

Nếu bảng chỉ có NOT NULL mà không có CHECK, giá -100 vẫn không phải NULL; do đó NOT NULL **không thể thay thế** test CHECK.

### 18.4. Test giá 0 hợp lệ khi rule không âm

~~~java
@Test
void zeroIsAllowedByNonnegativeCheck() throws Exception {
    try (Connection c = dataSource.getConnection()) {
        c.setAutoCommit(false);

        try (PreparedStatement ps = c.prepareStatement(
                "INSERT INTO constraint_demo(id, price) VALUES (?, ?)"
        )) {
            ps.setLong(1, 903L);
            ps.setBigDecimal(2, BigDecimal.ZERO);
            assertEquals(1, ps.executeUpdate());
        } finally {
            c.rollback();
        }
    }
}
~~~

Nếu rule đổi từ giá không âm thành giá phải dương, CHECK phải đổi từ >= 0 thành > 0 và test này cũng phải đổi theo.

### 18.5. Test CHECK mà không có NOT NULL

~~~sql
CREATE TABLE check_only (
    id BIGINT PRIMARY KEY,
    price NUMERIC(12,2),
    CONSTRAINT ck_check_only
        CHECK (price >= 0)
);

INSERT INTO check_only(id, price)
VALUES (1, NULL);
~~~

Trên database có SQL CHECK semantics thông dụng, INSERT này được chấp nhận vì CHECK(UNKNOWN) không tương đương CHECK(FALSE). **CHECK riêng không bắt buộc cột phải có giá trị.**

### 18.6. Test ràng buộc hai cột

~~~sql
CREATE TABLE price_pairs (
    id BIGINT PRIMARY KEY,
    list_price NUMERIC(12,2) NOT NULL,
    sale_price NUMERIC(12,2) NOT NULL,
    CONSTRAINT ck_sale_not_above_list
        CHECK (sale_price <= list_price)
);

-- Cả hai không NULL nhưng rule sai:
INSERT INTO price_pairs(id, list_price, sale_price)
VALUES (1, 100.00, 120.00);
~~~

NOT NULL không thể phát hiện sai lệch giữa hai cột; CHECK cross-column có thể từ chối.

### 18.7. PostgreSQL transaction sau lỗi

Khi statement gây constraint violation, PostgreSQL thường đặt transaction vào trạng thái aborted cho đến rollback, trừ khi dùng savepoint đúng cách. Tests trên luôn rollback trong finally để connection không bị trả về pool trong trạng thái lỗi.

### 18.8. Test JPA lifecycle

Một entity test:

~~~java
@Entity
@Table(name = "validation_demo")
public class ValidationDemo {

    @Id
    private Long id;

    @NotNull
    @PositiveOrZero
    @Column(nullable = false)
    private BigDecimal value;

    protected ValidationDemo() {}

    public ValidationDemo(Long id, BigDecimal value) {
        this.id = id;
        this.value = value;
    }
}
~~~

Với Bean Validation integration được bật, em.persist/flush một Value=-10 có thể bị từ chối trước INSERT. Nhưng nếu database cũng có CHECK, cần xem exception/cause/SQL để biết lớp nào đã chặn. Test chỉ assert “có lỗi” không chứng minh Bean Validation đã chạy.

### 18.9. Test lỗi tại flush/commit

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();
    em.persist(
        new ValidationDemo(
            901L, new BigDecimal("-10.00")
        )
    );

    em.flush();  // Có thể lỗi validation hoặc DB.
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

Đừng bắt lỗi chỉ quanh em.persist; SQL có thể được trì hoãn đến flush/commit.

### 18.10. Test schema drift

Một kiểm thử có giá trị trong CI:
- Migration tạo cột price NUMERIC(12,2) NOT NULL;
- CHECK price >= 0 thực sự được áp;
- JDBC INSERT NULL và -1 đều bị DB từ chối;
- Application Bean Validation và schema thể hiện cùng rule.

Nếu application code có @Column(nullable=false) nhưng test JDBC INSERT NULL vẫn thành công, schema production/test đang không đúng contract, bất kể annotation Java trông có vẻ chính xác.

### 18.11. Test concurrent uniqueness

Hai giao dịch cùng kiểm tra SKU chưa tồn tại rồi cùng INSERT. Một câu existsBySku trước save không thể thay DB UNIQUE constraint. Test cần hai transactions/physical connections để mô phỏng race; xác nhận DB ngăn hai rows cùng SKU và rollback transaction thất bại.

### 18.12. Test external SQL

Cho một writer JDBC không đi qua JPA:

~~~sql
UPDATE products
SET stock_quantity = -10
WHERE id = 42;
~~~

Nếu schema có CHECK(stock_quantity >= 0), database từ chối. Đây là bằng chứng tuyến bảo vệ DB có tác dụng ngay cả khi không có Spring @Valid, entity @Min hoặc domain method.

### 18.13. Test với database đích

Auto-generated H2 schema từ JPA trong unit test có thể khác schema migration PostgreSQL/MySQL ở production. Với constraint quan trọng, cần integration test chạy migration thật trên DB tương thích production và kiểm tra behavior, SQLSTATE/cause cùng rollback.

## 19. Xác định cách chia trách nhiệm cho từng quy tắc

| Yêu cầu | Ràng buộc ở Java/API | Ràng buộc DB | Ghi chú |
|---|---|---|---|
| Tên không null | @NotNull/@NotBlank | NOT NULL | @NotBlank còn cấm trắng |
| Giá không âm | @NotNull + @PositiveOrZero | NOT NULL + CHECK >= 0 | 0 hợp lệ theo rule này |
| Giá dương | @NotNull + @Positive | NOT NULL + CHECK > 0 | Không đồng nhất với không âm |
| Giá tối đa hai số thập phân | @Digits / BigDecimal normalization | NUMERIC(12,2) | Cần rounding policy |
| SKU đúng pattern | @Pattern/@NotBlank | CHECK/regex nếu cần | Regex dialect khác nhau |
| SKU duy nhất | Pre-check chỉ để UX | UNIQUE | Cần DB chống race |
| Category tồn tại | Service validation | FOREIGN KEY | Nếu bắt buộc thêm NOT NULL |
| Date range hợp lệ | Class-level/domain check | CHECK(end >= start) | Cross-field rule |
| Active phải có price>0 | Domain transition/group validation | CHECK cross-column | Phụ thuộc status |
| Tồn kho không âm | @Min(0) | CHECK >= 0 | Concurrency cần bảo vệ riêng |
| User được sửa | Authorization | RLS/quyền DB nếu dùng | Không phải nullable |
| Cùng user không đặt trùng đơn | Domain/idempotency key | UNIQUE phù hợp | Khác với @NotNull |

Chọn tầng theo phạm vi bảo vệ và tính chất rule, không cố ép một annotation làm mọi nhiệm vụ.

## 20. Bài tập thực hành

Các bài tập yêu cầu phân biệt **sự hiện diện của dữ liệu**, **miền giá trị**, **lớp thực thi** và **thời điểm phát hiện lỗi**. Nên thực hành với Product/ProductInput và PostgreSQL schema ở các phần trước.

### Bài 1. Chọn annotation cho giá bắt buộc

Requirement: Product.price phải có và không âm.

Một developer viết:

~~~java
@Column(nullable = false)
private BigDecimal price;
~~~

Hãy chỉ ra điều kiện nào đã được mô tả, điều kiện nào còn thiếu. Bổ sung Bean Validation và DB constraints phù hợp.

### Bài 2. Chuỗi toàn khoảng trắng

Giả sử name="   " và cột name VARCHAR(200) NOT NULL. Giá trị có thể vượt qua NOT NULL không? @NotNull, @NotEmpty và @NotBlank khác nhau như thế nào trên giá trị đó?

### Bài 3. Giá âm vẫn khác NULL

Cho price=-100.00, @Column(nullable=false), schema có NOT NULL nhưng chưa có CHECK.

Nếu gửi SQL UPDATE price=-100, có nhất thiết bị từ chối không? Hãy thêm CHECK/Bean Validation phù hợp.

### Bài 4. SQL CHECK với NULL

Bảng có:

~~~sql
price NUMERIC(12,2),
CHECK (price >= 0)
~~~

Hãy dự đoán kết quả INSERT price=NULL trên database có CHECK semantics thông dụng. Giải thích biểu thức UNKNOWN và vì sao cần NOT NULL khi field bắt buộc.

### Bài 5. Check giá trị 0

So sánh:
- CHECK(price >= 0);
- CHECK(price > 0);
- @PositiveOrZero;
- @Positive.

Giá 0 hợp lệ trong tổ hợp nào? Khi business yêu cầu giá 0 chỉ hợp lệ ở trạng thái DRAFT, cần điều kiện bổ sung gì?

### Bài 6. @Size và @Column(length)

Field:

~~~java
@Size(max = 200)
@Column(length = 200, nullable = false)
private String name;
~~~

Giải thích vai trò từng annotation. Có chắc cách đếm ký tự Java và VARCHAR(200) ở mọi database trùng nhau tuyệt đối không?

### Bài 7. @Digits, precision và scale

Field:

~~~java
@Digits(integer = 10, fraction = 2)
@Column(precision = 12, scale = 2)
private BigDecimal price;
~~~

Tại sao vẫn cần một money rounding/normalization policy khi input là 10.999? @Digits và NUMERIC(12,2) có thể báo kết quả khác nhau ở đâu?

### Bài 8. Primitive vs boxed type

So sánh:

~~~java
private int stockQuantity;
private Integer stockQuantity;
~~~

Khi request không gửi quantity, kiểu nào có thể mang Java null để @NotNull phát hiện field thiếu? Việc @Column(nullable=false) có tự phân biệt “không gửi” với “gửi 0” không?

### Bài 9. Database DEFAULT

Cột quantity INTEGER NOT NULL DEFAULT 0. So sánh:
- INSERT bỏ cột quantity;
- INSERT quantity=NULL.

Khi nào database default có thể được áp? Nếu JPA INSERT explicit null, default có chắc cứu được không?

### Bài 10. @Basic(optional=false)

Viết field String name với @Basic(optional=false), @Column(nullable=false) và @NotBlank. Nêu ý nghĩa riêng của từng annotation; không giải thích ba annotation như những tên đồng nghĩa.

### Bài 11. Quan hệ ManyToOne bắt buộc

Category là quan hệ bắt buộc. Hãy viết:

~~~java
@ManyToOne(optional = false)
@JoinColumn(name = "category_id", nullable = false)
private Category category;
~~~

Giải thích tại sao vẫn cần FOREIGN KEY trong database. FK nullable có tự cấm NULL không?

### Bài 12. SKU format và uniqueness

Product.sku phải đúng pattern [A-Z0-9-]{3,64} và duy nhất.

@Pattern có thay UNIQUE không? @Column(unique=true) có thay database migration trên bảng hiện hữu không? Hãy mô tả race của hai transactions cùng pre-check existsBySku.

### Bài 13. Ràng buộc hai cột

sale_price và list_price đều NOT NULL, nhưng sale_price=120, list_price=100. Hãy viết SQL CHECK và cách validate ở Java; vì sao nullable=false trên hai fields không đủ?

### Bài 14. Ngày bắt đầu và kết thúc

Một Period entity có startDate và endDate NOT NULL. Hãy thiết kế CHECK(end_date >= start_date) và một domain method hoặc class-level Bean Validation tương ứng.

### Bài 15. Optional sale price

NULL sale_price nghĩa “không giảm giá”. Hãy thiết kế:
- @Column(nullable=true) hoặc bỏ nullable;
- CHECK chỉ kiểm tra sale_price trong khoảng khi sale_price có mặt;
- DTO validation không bắt buộc salePrice;
- Hành vi API khi client gửi null để bỏ giảm giá.

### Bài 16. Enum status

ProductStatus gồm DRAFT, ACTIVE, ARCHIVED. Một external SQL writer gửi status="BROKEN".

@Enumerated(EnumType.STRING) có chắc database cấm giá này không nếu cột là VARCHAR(16)? Hãy đề xuất CHECK IN và rollout khi thêm status mới.

### Bài 17. DTO và entity validation

Tạo CreateProductRequest với @NotBlank name, @NotNull @PositiveOrZero price. Dùng @Valid ở Spring Controller. Tại sao SQL tool bên ngoài vẫn có thể bỏ qua toàn bộ validation Java?

### Bài 18. Validation timing

Một entity invalid được persist. Hãy liệt kê những nơi lỗi có thể xuất hiện:
- Domain constructor;
- Bean Validator/DTO binding;
- em.persist;
- em.flush;
- Transaction commit.

Vì sao không viết xử lý chỉ bắt exception tại em.persist?

### Bài 19. Hai loại ConstraintViolationException

Giải thích khác biệt:
- jakarta.validation.ConstraintViolationException;
- Hibernate/JDBC database integrity violation;
- Spring DataIntegrityViolationException.

Không dựa vào tên “ConstraintViolation” mà kết luận cùng một lớp lỗi.

### Bài 20. JPA schema generation bị tắt

Entity đã thêm @Column(nullable=false), nhưng bảng production vẫn cho NULL. Hãy nêu cách kiểm tra schema thực và các bước triển khai migration để sửa.

### Bài 21. Dữ liệu hiện hữu bị NULL

Một bảng có 50.000 rows, 1.000 rows price=NULL. Team muốn thêm NOT NULL.

Có nên UPDATE tất cả NULL thành 0 ngay không? Hãy mô tả quy trình khảo sát, backfill theo nghiệp vụ, migration và rollback policy.

### Bài 22. Cross-state business rule

ACTIVE yêu cầu price>0, DRAFT cho phép 0. Viết CHECK dạng:

~~~sql
CHECK (status <> 'ACTIVE' OR price > 0)
~~~

Giải thích cần NOT NULL cho status/price hay không, và cách bổ sung domain validation để trả lỗi sớm.

### Bài 23. Constraint bị lệch giữa Java và SQL

Java @PositiveOrZero chấp nhận 0, SQL CHECK(price>0) từ chối 0. Hãy nêu lỗi người dùng thấy ở từng layer và cách đồng bộ contract khi thay đổi nghiệp vụ.

### Bài 24. External SQL writer

Một ETL script gửi UPDATE products SET stock_quantity=-5 WHERE id=42. Nếu entity có @Min(0) nhưng database không có CHECK, chuyện gì có thể xảy ra? Giải thích vì sao database constraint cần thiết.

### Bài 25. Transaction và rollback

Service persist Product rồi gửi email trước khi transaction commit. Tại commit DB từ chối UNIQUE SKU. Những state nào đã thay đổi? Thiết kế cơ chế outbox/after-commit để không báo thành công sai.

### Bài 26. Test CHECK nhưng không test NOT NULL

Test chỉ INSERT price=-1 và xác nhận DB từ chối. Có đủ để chứng minh price phải có giá trị không? Bổ sung test với NULL và giải thích SQL UNKNOWN.

### Bài 27. Test với JDBC độc lập

Viết JUnit 5 test dùng DataSource/PreparedStatement để INSERT NULL và -1 vào constraint_demo. Vì sao không dùng mỗi entity validator.validate làm chứng cứ schema có CHECK?

### Bài 28. Test generated schema vs migrations

Một test H2 với Hibernate auto-ddl pass, nhưng production PostgreSQL dùng migration cũ. Hãy đề xuất integration test dùng migration thật và xác nhận constraint từ database catalog hoặc SQL DML.

### Bài 29. Giá tiền và rounding

Business cho phép giá có tối đa 2 số thập phân, API nhận 19.999. Chọn một chính sách:
- Reject sớm;
- Làm tròn rõ ràng theo quy tắc;
- Chuyển về minor currency units.

Tại sao không để NUMERIC(12,2) làm tròn ngầm mà không thông báo?

### Bài 30. Tồn kho và concurrency

DB có CHECK(stock_quantity>=0). Hai transactions cùng trừ tồn kho, mỗi transaction tự tính từ giá trị đã đọc.

CHECK có đủ tránh lost update không? Phân biệt bất biến “không âm” với bảo đảm “mỗi đơn hàng được trừ đúng một lần”. Đề xuất locking/conditional update/idempotency.

### Bài 31. Error mapping ổn định

DB từ chối constraint ck_products_price_nonnegative. Thiết kế HTTP response gồm code/field/message, có correlation ID. Vì sao không trả nguyên SQL exception message cho người dùng?

### Bài 32. Migration rolling deploy

Phiên bản cũ chấp nhận name="" nhưng phiên bản mới yêu cầu @NotBlank và DB CHECK. Hãy đề xuất trình tự:
- Deploy writers tuân rule mới;
- Backfill dữ liệu;
- Áp constraint;
- Bảo đảm clients cũ không còn tạo giá trị sai;
- Kiểm thử sau migration.

### Bài 33. Ràng buộc tài nguyên tham chiếu

Order.customerId không NULL nhưng trỏ tới ID customer đã bị xóa. NOT NULL có phát hiện không? Constraint nào ở database giải quyết? Khi nào cần ON DELETE behavior và application policy?

### Bài 34. Phân biệt 400, 409 và lỗi hệ thống

Cho ba lỗi:
- JSON price=-10 bị DTO validation;
- SKU trùng do concurrent INSERT;
- Database schema thiếu một cột sau migration lỗi.

Chọn cách phân loại HTTP response và xử lý transaction/log phù hợp; không map cả ba thành một message "Giá trị không hợp lệ".

### Bài 35. Tổng hợp thiết kế Product

Yêu cầu:
- name bắt buộc, không trắng, tối đa 200 ký tự;
- sku pattern và unique;
- price không âm, 2 chữ số thập phân;
- stock quantity không âm;
- status chỉ có ba giá trị;
- ACTIVE phải có giá dương;
- category bắt buộc, reference valid;
- SQL writers ngoài JPA phải bị chặn nếu sai.

Hãy viết:
1. Entity annotations JPA;
2. Bean Validation annotations;
3. Domain methods;
4. SQL migration NOT NULL/CHECK/UNIQUE/FK;
5. Tests cho input Java, external JDBC và database constraints;
6. Error handling và transaction boundaries.

## 21. Những tình huống dễ nhầm và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| @Column(nullable=false) nhưng DB vẫn nhận NULL | Schema không được cập nhật | Migration NOT NULL thật |
| name="   " vẫn lưu được | NOT NULL không cấm whitespace | @NotBlank + DB check nếu cần |
| price=-100 vẫn lưu được | Thiếu CHECK/value validation | @PositiveOrZero + DB CHECK |
| CHECK(price>=0) nhưng NULL vẫn lưu | CHECK UNKNOWN được chấp nhận | Thêm NOT NULL |
| @NotNull nhưng API nhận giá âm | @NotNull chỉ cấm null | Thêm numeric constraint |
| @PositiveOrZero nhưng null vẫn pass | Constraint numeric không tự bắt buộc value | Thêm @NotNull |
| @NotEmpty vẫn cho "   " | Chuỗi trắng không rỗng | Dùng @NotBlank |
| @Size không ngăn DB SQL ngoài dài quá | Bean Validation không chạy trên external SQL | DB VARCHAR length/constraint |
| @Digits pass nhưng DB từ chối giá | Precision/scale hoặc normalization khác | Đồng bộ policy/model/schema |
| @Column(length=200) không sửa prod | DDL generation tắt | Migration kiểm soát |
| Constraint lỗi tại commit, không tại persist | Flush/transaction timing | Handle quanh transaction boundary |
| Spring @Valid không chạy | Thiếu provider/config hoặc annotation tại entrypoint | Kiểm tra validation integration |
| Entity validation không chạy trước SQL | Persistence validation mode/provider | Cấu hình hoặc explicit validation |
| Schema có NOT NULL nhưng API trả 500 | Chưa map integrity error | DTO validation + exception translation |
| SKU trùng dù existsBySku false | Race concurrent requests | DB UNIQUE |
| FK reference sai nhưng non-null | NOT NULL không kiểm tra referenced row | FOREIGN KEY |
| status="BROKEN" từ SQL ngoài | JPA enum mapping không bảo vệ external SQL | DB CHECK/domain contract |
| Sale price > list price nhưng hai cột non-null | Cần cross-column constraint | CHECK(sale<=list) |
| DB reject NULL sau migration | Dữ liệu cũ/writer chưa tương thích | Expand-and-contract/backfill |
| @Version conflict dù CHECK pass | Data value hợp lệ nhưng concurrency sai | Optimistic locking/conflict handling |
| CHECK pass nhưng số dư sai | Rule cấp row không đủ cho business invariants | Transaction/ledger/concurrency |
| API trả raw SQL error | Error handler lộ nội bộ | Stable error codes, sanitized logs |
| Java @Positive, DB CHECK >=0 | Inconsistent rules | Đồng bộ constraints và tests |
| DB tự làm tròn số tiền | Thiếu rounding policy | Validate/normalize trước lưu |
| @ManyToOne(optional=false) nhưng FK không có | DB schema chưa có FK | Migration NOT NULL + FOREIGN KEY |
| Primitive int mặc định 0 che input missing | Không có null state | DTO Integer + @NotNull |
| Empty string thành NULL ở DB nào đó | Dialect-specific semantics | Test DB mục tiêu, không giả định portable |
| Stored procedure ghi sai data | Không đi qua Bean Validation | DB constraints |
| Test H2 đúng, PostgreSQL prod sai | Schema/dialect khác | Test migration trên DB mục tiêu |

## 22. Bảng tra cứu nhanh

| Muốn bảo đảm | Java/JPA | Database |
|---|---|---|
| Không NULL | @NotNull / @Column(nullable=false) | NOT NULL |
| Không rỗng/không trắng | @NotBlank | CHECK phù hợp dialect |
| Không âm | @PositiveOrZero hoặc @Min(0) | CHECK(value >= 0) |
| Lớn hơn 0 | @Positive hoặc @DecimalMin(inclusive=false) | CHECK(value > 0) |
| Trong khoảng | @Min/@Max, @DecimalMin/@DecimalMax | CHECK BETWEEN |
| Tối đa ký tự | @Size(max=...) / @Column(length=...) | VARCHAR length/constraint |
| Chữ số thập phân hợp lệ | @Digits, BigDecimal policy | NUMERIC(precision,scale) + policy |
| Pattern | @Pattern | CHECK/regex nếu DB hỗ trợ |
| Duy nhất | Service pre-check để UX | UNIQUE |
| Reference tồn tại | @ManyToOne mapping/service check | FOREIGN KEY |
| Quan hệ bắt buộc | optional=false / @JoinColumn(nullable=false) | FK column NOT NULL |
| Hai cột có quan hệ | Domain/class-level validation | CHECK cross-column |
| Không stale update | @Version | Conditional UPDATE/locking |
| Kiểm tra input API | @Valid trên DTO | Không trực tiếp |
| Bảo vệ SQL ngoài JPA | Không chỉ Java annotations | NOT NULL/CHECK/UNIQUE/FK |
| Áp rule lên dữ liệu cũ | Migration/backfill design | ALTER TABLE + validation |
| Trả lỗi dễ hiểu | Error handler/validation messages | SQLSTATE/constraint name để phân loại |

## 23. Checklist áp dụng nullable và kiểm tra giá trị

### 23.1. Phân tích nghiệp vụ

1. **Field có thật sự bắt buộc không?** SQL NULL có mang nghĩa “chưa biết” hoặc “không áp dụng” không?
2. **Giá trị rỗng có hợp lệ không?** Phân biệt null, "", "   " và default value.
3. **Số 0 có ý nghĩa gì?** Hợp lệ, miễn phí, chưa định giá hay phải dương?
4. **Số âm có được chấp nhận không?** Giá/tồn kho và adjustment có thể khác nhau.
5. **Có min/max không?** Giới hạn number/date/string phải rõ.
6. **Có cần chuẩn hóa BigDecimal không?** Định nghĩa scale và rounding policy.
7. **Có yêu cầu giữa nhiều cột không?** salePrice <= listPrice, endDate >= startDate.
8. **Có rule tùy status không?** DRAFT khác ACTIVE.
9. **Có yêu cầu UNIQUE/FK hoặc cross-row invariant không?**
10. **Những writer nào có thể ghi DB?** JPA, JDBC, ETL, SQL scripts, service khác?

### 23.2. JPA mapping

11. **@Column(nullable=false) đã đặt đúng persistent field chưa?**
12. **Có hiểu nullable mặc định true không?**
13. **Đã phân biệt @Basic(optional=false) với @Column(nullable=false) chưa?**
14. **Với relationship, có dùng @JoinColumn(nullable) và FOREIGN KEY đúng chỗ không?**
15. **Database DEFAULT có thật được dùng khi JPA INSERT cột không?**
16. **Có tránh Java primitive int=0 che mất input field bị thiếu không?**
17. **@Column(length) và @Size có tương thích với schema không?**
18. **Precision/scale có đồng nhất với @Digits và policy rounding không?**
19. **@Enumerated STRING có cần DB CHECK allowed values không?**
20. **@Column(unique=true) có được áp thành UNIQUE migration trên production không?**
21. **Có hiểu insertable/updatable không thay constraints không?**
22. **Có cần @Version/locking để chống concurrent lost updates không?**

### 23.3. Bean Validation

23. **@NotNull, @NotBlank và @NotEmpty có được dùng đúng ngữ nghĩa không?**
24. **Numeric constraint có đi kèm @NotNull khi value bắt buộc không?**
25. **@Min/@Max/@DecimalMin/@DecimalMax có biểu diễn đúng các bounds không?**
26. **@Digits có phù hợp với price currency precision không?**
27. **Có Bean Validation provider thực sự hoạt động không?**
28. **@Valid có được kích hoạt ở API entrypoint phù hợp không?**
29. **JPA lifecycle validation mode có được cấu hình đúng không?**
30. **Validation groups có phản ánh Create/Update/Activate không?**
31. **Domain methods có giữ invariant quan trọng không?**
32. **Có hiểu Validator.validate trả collection violations, không tự ném exception không?**
33. **Có phân biệt value validation với authorization không?**

### 23.4. Database constraints và migrations

34. **Schema thực tế có NOT NULL chưa?** Không chỉ xem entity class.
35. **Giá không âm có CHECK ở database chưa?**
36. **CHECK có thể cho NULL qua UNKNOWN nếu thiếu NOT NULL không?**
37. **Field optional có CHECK biểu diễn NULL đúng nghiệp vụ không?**
38. **Có UNIQUE cho SKU hoặc business key phải duy nhất không?**
39. **Có FOREIGN KEY cho references không?**
40. **Cross-field CHECK đã được đặt tên và quản lý qua migration chưa?**
41. **SQL syntax/regex/trim functions có phù hợp dialect production không?**
42. **Dữ liệu hiện hữu đã được làm sạch/backfill chưa?**
43. **Migration có yêu cầu lock/scan/downtime và rollback plan không?**
44. **Rolling deploy có writers cũ vi phạm contract mới không?**
45. **Có test INSERT/UPDATE qua JDBC để chứng minh DB từ chối invalid values không?**

### 23.5. Transaction và xử lý lỗi

46. **Có xử lý lỗi ở flush/commit boundary không?**
47. **Transaction có rollback sau DB constraint failure không?**
48. **Có phân biệt jakarta.validation.ConstraintViolationException với SQL integrity error không?**
49. **Spring DataIntegrityViolationException có được phân loại theo cause/constraint name không?**
50. **Có error codes ổn định cho API thay vì trả raw SQL exception không?**
51. **Có bảo vệ logs khỏi SQL parameters/PII/secret không?**
52. **Có test concurrency UNIQUE và cập nhật tồn kho không?**
53. **Có test trên DB gần production chứ không chỉ H2 auto-generated DDL không?**
54. **Có test riêng NULL, số âm, số 0, rỗng, trắng, giá vượt giới hạn không?**
55. **Khi business đổi rule, đã sửa đồng bộ Java, DB và tests chưa?**
56. **External SQL writers có tuân thủ những constraints và version policy không?**
57. **Có quy trình sửa legacy rows không hợp lệ không?**
58. **Có phân biệt value validity với transactional consistency không?**
59. **Có quản lý schema constraint names để hỗ trợ debugging không?**
60. **Có hiểu DB constraints không thay thế authentication/authorization không?**

### 23.6. Sơ đồ quyết định

~~~text
Một field cần kiểm tra khi lưu
                |
                v
        Có được phép NULL?
          /            \
        Không           Có
          |              |
  Java: @NotNull/        |  Giữ optional khi domain cho phép
        @NotBlank        |
  JPA: nullable=false    |
  DB: NOT NULL           |
          \              /
           +------------+
                  |
                  v
       Có giới hạn miền giá trị?
          /              \
        Không             Có
          |                |
      Không cần        Java: @Min/@Positive
      CHECK chỉ        @Pattern/@Size
      vì thói quen     Domain cross-field checks
                       DB: CHECK phù hợp
          \              /
           +------------+
                  |
                  v
      Có unique/reference invariant?
          /              \
         Có              Không
          |                |
      DB UNIQUE/FK        Tiếp tục
          \                /
           +--------------+
                  |
                  v
      Có SQL writer ngoài Java không?
                  |
          +-------+-------+
          |               |
         Có             Không
          |               |
    Database constraints vẫn là
    tuyến bảo vệ cuối cùng
                  |
                  v
      Migrations + testing + monitoring
                  |
                  v
      Flush/commit + rollback + error mapping
~~~

## 24. Kết luận

**@Column(nullable = false)** và **ràng buộc kiểm tra giá trị** cùng góp phần giữ dữ liệu hợp lệ, nhưng **không tương đương**.

- **@Column(nullable=false):** metadata nullability của JPA column, đặc biệt cho schema generation. Không tự cấm -100 hoặc một chuỗi toàn khoảng trắng; database production phải có NOT NULL thật nếu muốn enforcement.
- **@NotNull/@NotBlank/@PositiveOrZero/...:** kiểm tra Java objects hoặc API DTOs khi Jakarta Bean Validation được kích hoạt. Giúp báo lỗi sớm, nhưng **không chạy cho SQL bên ngoài JPA**.
- **SQL NOT NULL:** cấm giá trị NULL, không tự cấm số âm hay string trống.
- **SQL CHECK:** kiểm tra miền giá trị, như price >= 0, stock >= 0, sale_price <= list_price. **CHECK đơn lẻ không nhất thiết cấm NULL** vì biểu thức UNKNOWN có thể được chấp nhận.
- **UNIQUE/FK:** các constraints riêng cho tính duy nhất và toàn vẹn tham chiếu.
- **Domain methods/transaction:** bảo vệ workflow và concurrency; không thể thay thế chỉ bằng nullable.

Ví dụ Java cho giá bắt buộc và không âm:

~~~java
@NotNull
@PositiveOrZero
@Digits(integer = 10, fraction = 2)
@Column(
    nullable = false,
    precision = 12,
    scale = 2
)
private BigDecimal price;
~~~

Và ràng buộc thực tế trong database:

~~~sql
price NUMERIC(12, 2) NOT NULL,
CONSTRAINT ck_products_price_nonnegative
    CHECK (price >= 0)
~~~

Phân loại bốn tình huống:

~~~text
price = NULL
  @NotNull có thể từ chối khi Java validation chạy.
  SQL NOT NULL từ chối khi INSERT/UPDATE.

price = -100
  @NotNull không nhận đây là sai.
  @PositiveOrZero từ chối khi Java validation chạy.
  SQL CHECK(price >= 0) từ chối ngay cả khi writer dùng JDBC.

price = 0
  Thỏa rule không âm và không-null.
  Có thể sai nếu business yêu cầu giá bán phải dương.

price = 10.999
  @Digits(fraction=2) có thể từ chối.
  NUMERIC(12,2) có behavior lưu/round theo database.
  Cần chính sách precision/scale và rounding rõ ràng.
~~~

**Nguyên tắc ghi nhớ:** **nullable** trả lời câu hỏi *“Có được thiếu giá trị không?”*, còn **ràng buộc kiểm tra giá trị** trả lời *“Nếu có giá trị, nó phải thỏa điều kiện nào?”*. Trong hệ thống JPA thực tế, thường cần kết hợp annotation mapping, Bean Validation, domain methods và database constraints qua migrations để bảo đảm dữ liệu đúng trên mọi đường ghi.












