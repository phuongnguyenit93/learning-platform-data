# Ánh xạ thuộc tính cơ bản bằng @Basic và @Column trong JPA

## 1. Thuộc tính cơ bản là gì?

Trong Jakarta Persistence (JPA), một **entity** là đối tượng Java có danh tính bền vững, được ánh xạ vào dữ liệu trong cơ sở dữ liệu quan hệ. Ngoài khóa chính và các quan hệ với entity khác, entity còn chứa những thuộc tính đơn giản như tên, giá, số lượng, ngày tạo, trạng thái, hoặc một đoạn văn bản. Những thuộc tính đó thường được ánh xạ thành **các cột của bảng**.

Ví dụ, một sản phẩm có dữ liệu như sau:

| Thuộc tính trong Java | Kiểu Java | Cột trong bảng |
|---|---|---|
| id | Long | id |
| sku | String | sku |
| displayName | String | display_name |
| unitPrice | BigDecimal | unit_price |
| stockQuantity | int | stock_quantity |
| active | boolean | active |

Trong trường hợp cơ bản, một thuộc tính Java tương ứng với một cột SQL; JPA đọc giá trị cột thành thuộc tính và ghi giá trị thuộc tính trở lại cột khi persistence context được đồng bộ. Hai annotation quan trọng để điều chỉnh hành vi đó là:

- **@Basic**: mô tả cách JPA quản lý một thuộc tính cơ bản, chủ yếu qua các tùy chọn tải dữ liệu và tính tùy chọn của giá trị.
- **@Column**: mô tả cột vật lý tương ứng trong bảng, như tên cột, khả năng nhận NULL, độ dài, độ chính xác, khả năng ghi khi INSERT hoặc UPDATE.

Hai annotation này có thể đặt cùng một thuộc tính, vì chúng giải quyết **hai lớp vấn đề khác nhau**. Đặc biệt, phần lớn thuộc tính cơ bản không bắt buộc viết cả hai annotation; JPA có các giá trị mặc định.

> Bài học tập trung vào ánh xạ thuộc tính cơ bản của entity bằng Jakarta Persistence. Tên package trong các ví dụ là **jakarta.persistence**, phù hợp với các phiên bản JPA hiện đại. Dự án dùng JPA 2.x cũ có thể dùng package **javax.persistence**; không nên trộn hai hệ annotation trong một dự án.

## 2. Cơ chế ánh xạ mặc định

Xét entity tối giản:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private int quantity;

    protected Product() {
    }

    public Product(String name, int quantity) {
        this.name = name;
        this.quantity = quantity;
    }
}
~~~

Ở đây, **name** và **quantity** không có @Basic hoặc @Column. Vì là những trường có kiểu dữ liệu cơ bản được JPA hỗ trợ, chúng vẫn được xem là thuộc tính lưu trữ theo quy tắc ánh xạ mặc định. Theo mặc định, JPA sử dụng tên thuộc tính để suy ra tên cột; provider và naming strategy có thể điều chỉnh tên vật lý thực tế.

Điều này có nghĩa:

1. Không cần viết **@Basic** chỉ để một String hoặc int được lưu xuống database.
2. Không cần viết **@Column** nếu các giá trị mặc định đã phù hợp với schema.
3. Nên viết **@Column** khi cần diễn đạt rõ hợp đồng dữ liệu: ví dụ cột **product_name** dài tối đa 150 ký tự hoặc **unit_price** có độ chính xác 13 chữ số.
4. Khi đang dùng database có sẵn, cần kiểm tra tên cột thực tế. Không nên phụ thuộc vào naming strategy suy đoán.

### 2.1. JPA nhận biết field hay getter như thế nào?

Vị trí đặt annotation định danh, thường là **@Id**, quyết định cách truy cập mặc định của entity:

**Field access**: @Id đặt trên trường; JPA làm việc trực tiếp với trường.

~~~java
@Entity
public class Customer {
    @Id
    private Long id;

    @Column(name = "full_name")
    private String fullName;

    protected Customer() {}

    public String getFullName() {
        return fullName;
    }
}
~~~

**Property access**: @Id đặt trên getter; các annotation ánh xạ được đặt trên getter.

~~~java
@Entity
public class Customer {
    private Long id;
    private String fullName;

    protected Customer() {}

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    @Column(name = "full_name")
    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
~~~

Nếu dùng field access mà đặt @Column chỉ trên getter, kỳ vọng mapping của getter đó có hiệu lực là sai về cách tổ chức annotation. Việc trộn field và property access không được xác định nhất quán có thể dẫn đến mapping khó dự đoán; khi thật sự cần phối hợp, phải dùng **@Access** để chỉ rõ chiến lược cho phần thích hợp.

## 3. Annotation @Basic

@Basic đánh dấu một thuộc tính có kiểu cơ bản được JPA quản lý. Cú pháp:

~~~java
import jakarta.persistence.Basic;
import jakarta.persistence.FetchType;

@Basic(optional = false, fetch = FetchType.EAGER)
private String title;
~~~

Các thuộc tính cấu hình chính:

| Thuộc tính @Basic | Giá trị mặc định | Ý nghĩa |
|---|---|---|
| **optional** | **true** | Giá trị thuộc tính có được phép vắng mặt/null ở mức mapping JPA hay không |
| **fetch** | **FetchType.EAGER** | Gợi ý cách provider tải thuộc tính: eager hoặc lazy |

Ví dụ sau tương đương về mặt khai báo mặc định:

~~~java
private String title;

@Basic
private String title;

@Basic(optional = true, fetch = FetchType.EAGER)
private String title;
~~~

Ba dòng trên là **ba cách khai báo thay thế**, không phải ba trường trong cùng một entity. Có thể bỏ @Basic nếu không cần thay đổi hành vi mặc định.

### 3.1. optional = false

~~~java
@Basic(optional = false)
private String title;
~~~

Khai báo này nói rằng đối với thuộc tính cơ bản có kiểu tham chiếu, **JPA không coi null là giá trị hợp lệ theo mapping**. Đây là thông tin để provider áp dụng các ràng buộc liên quan. Tuy nhiên, không nên coi nó như một lệnh kiểm tra đầu vào Java có thông báo lỗi thống nhất trước khi chạy SQL; hành vi phát hiện lỗi phụ thuộc provider, thời điểm flush và cấu hình xác thực.

Nếu muốn ràng buộc rõ ở tầng cơ sở dữ liệu, thường khai báo thêm:

~~~java
@Basic(optional = false)
@Column(name = "title", nullable = false, length = 200)
private String title;
~~~

Đối với kiểu nguyên thủy như **int**, **long** và **boolean**, giá trị không thể là Java null, nên thuộc tính optional của @Basic về bản chất không có ý nghĩa giống như đối với String, Long hoặc BigDecimal. Nếu ứng dụng cần phân biệt “không biết số lượng” với “số lượng bằng 0”, hãy dùng **Integer**, không dùng int.

### 3.2. fetch = EAGER và LAZY

~~~java
@Basic(fetch = FetchType.EAGER)
private String title;

@Basic(fetch = FetchType.LAZY)
private String longDescription;
~~~

- **EAGER**: provider phải đáp ứng yêu cầu tải thuộc tính theo cách bảo đảm dữ liệu sẵn sàng khi entity được tải.
- **LAZY**: là **gợi ý** cho provider về việc trì hoãn tải thuộc tính; provider được phép tải eager. Với thuộc tính cơ bản, hỗ trợ lazy có thể cần bytecode enhancement/weaving tùy provider.

Không nên viết code dựa trên giả định rằng @Basic(fetch = LAZY) **chắc chắn** làm cột bị loại khỏi câu SELECT đầu tiên. Để xác định lượng dữ liệu thực sự được truy vấn, có thể dùng DTO projection, query chọn trường cần thiết hoặc tính năng fetch phù hợp với provider.

Một ví dụ có ý nghĩa về mặt thiết kế:

~~~java
@Entity
public class Document {
    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false, length = 180)
    private String title;

    @Basic(fetch = FetchType.LAZY)
    @Column(name = "raw_content")
    private String rawContent;

    protected Document() {}
}
~~~

Nếu **rawContent** lớn, lazy basic attribute có thể giúp giảm dữ liệu tải trong một số cấu hình, nhưng ứng dụng vẫn cần xác nhận khả năng lazy thực tế của ORM và hành vi khi truy cập entity sau khi context đã đóng.

### 3.3. Những kiểu dữ liệu thường dùng với @Basic

Các kiểu cơ bản phổ biến bao gồm:

| Nhóm | Ví dụ Java | Gợi ý thiết kế |
|---|---|---|
| Chuỗi | String, char/Character | Dùng @Column(length = ...) nếu lưu VARCHAR có giới hạn |
| Số nguyên | byte, short, int, long và wrapper tương ứng | Wrapper cho phép null; primitive không cho phép |
| Số thập phân | BigDecimal, BigInteger | BigDecimal phù hợp số tiền; khai báo precision/scale thích hợp |
| Số thực | float, double và wrapper | Cẩn trọng sai số biểu diễn khi tính tiền |
| Boolean | boolean, Boolean | Boolean biểu diễn được trạng thái null nếu nghiệp vụ cần |
| Ngày/giờ | LocalDate, LocalTime, LocalDateTime và các kiểu thời gian được phiên bản JPA hỗ trợ | Chọn đúng ngữ nghĩa ngày, giờ và múi giờ |
| Dữ liệu nhị phân | byte[] và các kiểu được provider hỗ trợ | Dữ liệu rất lớn có thể cần @Lob hoặc chiến lược lưu riêng |
| Enum | Enum Java | Nên định nghĩa @Enumerated hoặc converter thay vì dựa vào thứ tự ordinal |

Danh sách các kiểu được chuẩn hóa có thay đổi theo phiên bản Jakarta Persistence. Khi dùng một kiểu Java đặc biệt, cần xác nhận nó là **basic type chuẩn**, một mapping do provider hỗ trợ hay phải dùng **AttributeConverter**.

## 4. Annotation @Column

@Column mô tả **cột SQL lưu thuộc tính**. Nó chỉ định chi tiết schema và cách JPA đưa giá trị vào lệnh INSERT/UPDATE.

~~~java
import jakarta.persistence.Column;

@Column(
    name = "product_name",
    nullable = false,
    length = 150
)
private String name;
~~~

### 4.1. Các tham số quan trọng

| Thuộc tính @Column | Mặc định thường gặp theo annotation | Tác dụng |
|---|---|---|
| **name** | Tên thuộc tính Java | Tên cột được ánh xạ; có thể bị naming strategy xử lý |
| **unique** | false | Chỉ định ràng buộc duy nhất trên cột; shortcut cho unique constraint một cột khi sinh schema |
| **nullable** | true | Cột có chấp nhận SQL NULL khi JPA sinh schema hay không |
| **insertable** | true | Có đưa cột vào những lệnh INSERT do JPA tạo cho mapping đó hay không |
| **updatable** | true | Có đưa cột vào những lệnh UPDATE do JPA tạo cho mapping đó hay không |
| **length** | 255 | Độ dài dùng cho cột chuỗi có độ dài xác định, điển hình là VARCHAR |
| **precision** | 0 (chưa chỉ định) | Tổng số chữ số cho cột số chính xác như DECIMAL/NUMERIC |
| **scale** | 0 (chưa chỉ định) | Số chữ số phần thập phân cho cột số chính xác |
| **columnDefinition** | Chuỗi rỗng | Định nghĩa SQL cột được yêu cầu khi tạo schema |
| **table** | Bảng chính của entity | Chỉ định bảng chứa cột khi entity có mapping đến bảng phụ |

Lưu ý: giá trị **0** mặc định của precision/scale là trạng thái chưa cung cấp chỉ dẫn cụ thể; không nên hiểu rằng cột tiền tệ mặc định là DECIMAL(0,0). DDL cuối cùng tùy kiểu Java, dialect và quy tắc sinh schema.

Một annotation có thể khai báo nhiều tham số:

~~~java
@Column(
    name = "unit_price",
    nullable = false,
    precision = 13,
    scale = 2,
    insertable = true,
    updatable = true
)
private BigDecimal unitPrice;
~~~

@Column không tự biến một trường thành persistent nếu trường đó bị loại khỏi mapping, chẳng hạn đánh dấu **@Transient** hoặc **transient** theo quy tắc JPA. Ngược lại, có nhiều trường cơ bản vẫn được lưu nếu không khai báo @Column.

## 5. Ví dụ entity đầy đủ với @Basic và @Column

Giả sử xây dựng chức năng quản lý danh mục sản phẩm. Ta muốn đảm bảo:

- SKU không được để trống ở mức dữ liệu và phải duy nhất.
- Tên sản phẩm bắt buộc có, tối đa 160 ký tự theo schema.
- Giá sản phẩm dùng số thập phân chính xác với 13 chữ số, trong đó 2 chữ số thập phân.
- Số lượng tồn kho mặc định theo đối tượng là 0.
- Ghi chú cho phép null và có độ dài tối đa 1000 ký tự theo DDL.

~~~java
package com.example.catalog;

import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "catalog_products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "product_id")
    private Long id;

    @Basic(optional = false)
    @Column(name = "sku", nullable = false, unique = true, length = 40)
    private String sku;

    @Basic(optional = false)
    @Column(name = "display_name", nullable = false, length = 160)
    private String displayName;

    @Basic(optional = false)
    @Column(name = "unit_price", nullable = false, precision = 13, scale = 2)
    private BigDecimal unitPrice;

    @Column(name = "stock_quantity", nullable = false)
    private int stockQuantity;

    @Column(name = "active", nullable = false)
    private boolean active = true;

    @Column(name = "internal_note", length = 1000)
    private String internalNote;

    protected Product() {
        // Constructor dành cho JPA.
    }

    public Product(String sku, String displayName, BigDecimal unitPrice) {
        this.sku = sku;
        this.displayName = displayName;
        this.unitPrice = unitPrice;
        this.stockQuantity = 0;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getDisplayName() {
        return displayName;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public int getStockQuantity() {
        return stockQuantity;
    }

    public String getInternalNote() {
        return internalNote;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Price must be non-negative");
        }
        this.unitPrice = newPrice;
    }

    public void changeQuantity(int newQuantity) {
        if (newQuantity < 0) {
            throw new IllegalArgumentException("Quantity must be non-negative");
        }
        this.stockQuantity = newQuantity;
    }

    public void setInternalNote(String internalNote) {
        this.internalNote = internalNote;
    }
}
~~~

Đây là field access vì @Id đặt trên trường. Việc không có setter public cho tất cả thuộc tính **không ngăn** JPA thao tác các trường đã ánh xạ khi dùng field access.

Một DDL minh họa cho PostgreSQL, nếu schema được thiết kế tương ứng với các yêu cầu trên, có thể là:

~~~sql
CREATE TABLE catalog_products (
    product_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(160) NOT NULL,
    unit_price NUMERIC(13, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    active BOOLEAN NOT NULL,
    internal_note VARCHAR(1000)
);
~~~

DDL này là **minh họa độc lập**, không phải cam kết chính xác về SQL Hibernate hoặc provider bất kỳ sẽ sinh. Cách đặt tên, kiểu cột và cú pháp sinh khóa phụ thuộc dialect, provider, schema-generation settings và cơ sở dữ liệu. Dữ liệu thật nên được quản lý bằng schema migration được kiểm soát.

## 6. Khác biệt giữa @Basic(optional = false) và @Column(nullable = false)

Hai lựa chọn này thường được dùng chung, nhưng không phải một:

| Khía cạnh | @Basic(optional = false) | @Column(nullable = false) |
|---|---|---|
| Tầng biểu đạt | Mapping tính tùy chọn của basic attribute trong JPA | Mapping tính cho phép NULL của cột |
| Ý nghĩa chính | Giá trị basic attribute không được xem là optional | Đề xuất ràng buộc NOT NULL khi sinh schema |
| Kiểm tra Java trước khi ghi | Có thể ảnh hưởng cách provider kiểm tra trạng thái | Không bảo đảm có kiểm tra Java trước SQL |
| Tác động đến schema generation | Có thể được provider dùng khi suy ra ràng buộc | Nêu rõ yêu cầu nullable cho cột |
| Thay thế Bean Validation? | Không | Không |
| Bảo đảm database hiện có đã có NOT NULL? | Không | Không, nếu chưa áp dụng DDL tương ứng |

Ví dụ:

~~~java
@Basic(optional = false)
@Column(name = "email", nullable = false, length = 254)
private String email;
~~~

Ở đây, cả mapping entity và mong muốn đối với cột DB đều được diễn đạt rõ ràng. Nhưng nếu ứng dụng đang dùng schema cũ có cột **email** cho phép NULL, chỉ thêm annotation **không tự sửa schema** trong mọi môi trường.

Nếu muốn kiểm tra đầu vào ở tầng ứng dụng, có thể kết hợp Jakarta Validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@NotBlank
@Size(max = 254)
@Basic(optional = false)
@Column(name = "email", nullable = false, length = 254)
private String email;
~~~

**@NotBlank** kiểm tra String phải có ký tự không phải khoảng trắng; **@Size(max = 254)** kiểm tra độ dài theo ngữ nghĩa Bean Validation. **@Column(length = 254)** là mô tả schema cho cột, không phải lệnh tự cắt chuỗi hoặc một validator chuẩn trên mọi đường ghi.

Khi bật tích hợp Bean Validation với JPA, kiểm tra có thể được chạy tự động ở những thời điểm vòng đời entity thích hợp. Nhưng validator, JPA và ràng buộc DB vẫn thuộc các lớp trách nhiệm khác nhau; ứng dụng nên xử lý lỗi ở từng lớp.

### 6.1. Null, chuỗi rỗng và giá trị mặc định

Các trạng thái sau khác nhau:

~~~java
String a = null;
String b = "";
String c = "   ";
~~~

- **null** là không có giá trị Java; khi ánh xạ thông thường sẽ tương ứng SQL NULL.
- **""** là chuỗi rỗng, không đồng nghĩa NULL trong tất cả DB. Ví dụ một số hệ quản trị có quy tắc xử lý chuỗi rỗng đặc biệt; phải xét dialect và schema đang dùng.
- **"   "** là một chuỗi gồm khoảng trắng; **nullable = false** không cấm nó.

Với **int quantity**, giá trị Java mặc định là 0, không có nghĩa DB có DEFAULT 0. Nếu SQL INSERT bỏ qua cột vì **insertable = false**, số 0 trong object Java không tự làm DB ghi 0. Cần hiểu rõ khác biệt giữa **default của Java**, **giá trị do ORM gửi** và **DEFAULT của database**.

## 7. Đặt tên cột bằng @Column(name = ...)

~~~java
@Column(name = "created_at")
private LocalDateTime createdAt;
~~~

Tên field là **createdAt**, nhưng cột DB là **created_at**. Trong JPQL, ta truy vấn qua **tên thuộc tính entity**, không dùng tên cột vật lý:

~~~java
List<Product> products = em.createQuery(
    "select p from Product p where p.unitPrice >= :minPrice",
    Product.class
).setParameter("minPrice", new BigDecimal("100.00"))
 .getResultList();
~~~

JPQL dùng **p.unitPrice**, không dùng **p.unit_price**. SQL native lại dùng tên cột thật:

~~~sql
SELECT product_id, unit_price
FROM catalog_products
WHERE unit_price >= 100.00;
~~~

Cần đặc biệt chú ý khi làm việc với schema do người khác thiết kế: tên trường Java có thể dùng camelCase, còn cột SQL dùng snake_case. Nếu database sử dụng chữ hoa/chữ thường nhạy cảm hoặc tên là từ khóa SQL, cân nhắc đặt lại tên ở schema hoặc cấu hình quoting theo provider/dialect. Không nên cho rằng một tên được quote ở mọi DB sẽ có cùng ngữ nghĩa.

## 8. length, precision và scale

### 8.1. length cho chuỗi

~~~java
@Column(name = "short_code", length = 32, nullable = false)
private String shortCode;
~~~

**length = 32** mô tả độ dài cột chuỗi trong schema generation (thường tương ứng VARCHAR(32) nếu mapping phù hợp). Nó không có tác dụng tự động:

- Cắt String dài hơn 32 ký tự trước khi INSERT.
- Bảo đảm kiểm tra đầu vào của form hoặc API.
- Đổi cột đang tồn tại từ VARCHAR(255) thành VARCHAR(32) khi schema migration không chạy.

Độ dài tính bằng ký tự, byte, code point hay giới hạn cụ thể của DB có thể khác nhau theo hệ quản trị và encoding. Nếu có yêu cầu nghiêm ngặt về Unicode hoặc kích thước lưu trữ, kiểm tra quy định của database đang dùng.

### 8.2. precision và scale cho số thập phân

~~~java
@Column(
    name = "amount",
    nullable = false,
    precision = 12,
    scale = 2
)
private BigDecimal amount;
~~~

Với kiểu SQL DECIMAL/NUMERIC, **precision** là tổng số chữ số và **scale** là số chữ số sau dấu thập phân. Chẳng hạn NUMERIC(12,2) có thể biểu diễn các giá trị trong phạm vi phù hợp, gồm tối đa 10 chữ số phần nguyên và 2 chữ số phần thập phân.

| Giá trị | Phù hợp về số chữ số với NUMERIC(12,2)? | Lưu ý |
|---|---|---|
| 123.45 | Có | 5 chữ số có nghĩa |
| 9999999999.99 | Có | Giới hạn dương điển hình |
| 10000000000.00 | Không | 11 chữ số phần nguyên |
| 12.345 | Cần xét quy tắc làm tròn | DB/provider có thể làm tròn hoặc từ chối, tùy hệ thống |

Không nên dựa vào DB để tự động xử lý số tiền nhiều hơn 2 chữ số thập phân. Có thể chuẩn hóa **BigDecimal** theo chính sách làm tròn rõ ràng trước khi lưu:

~~~java
BigDecimal normalized = input.setScale(2, RoundingMode.HALF_UP);
~~~

Ví dụ này cần import **java.math.RoundingMode** và chọn chế độ làm tròn theo nghiệp vụ. Không dùng **double** làm nguồn tính toán tiền chính xác nếu có thể tránh, vì double lưu dạng nhị phân và có sai số biểu diễn.

### 8.3. Thuộc tính chưa được hỗ trợ giống nhau trên mọi kiểu

Đặt **precision/scale** trên String không khiến String thành DECIMAL. Tương tự, đặt **length** trên BigDecimal không dùng để quyết định số chữ số. Cách provider diễn giải các tham số phụ thuộc loại Java, JDBC mapping và SQL dialect.

## 9. unique và ràng buộc dữ liệu

~~~java
@Column(name = "sku", unique = true, nullable = false, length = 40)
private String sku;
~~~

**unique = true** biểu đạt mong muốn giá trị của cột này là duy nhất trong bảng khi sinh schema. Nó không có nghĩa rằng JPA sẽ truy vấn trước để kiểm tra mọi SKU trùng và báo lỗi nghiệp vụ đẹp. Ràng buộc UNIQUE ở DB mới là nơi có thể bảo vệ dữ liệu khỏi hai giao dịch đồng thời cùng chèn một SKU.

Nếu unique kết hợp nhiều cột, ví dụ **tenant_id + code**, có thể khai báo constraint tại @Table:

~~~java
@Entity
@Table(
    name = "tenant_products",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_tenant_product_code",
        columnNames = {"tenant_id", "product_code"}
    )
)
public class TenantProduct {
    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "product_code", nullable = false, length = 40)
    private String productCode;

    protected TenantProduct() {}
}
~~~

**columnNames** ở đây là tên cột trong bảng, không phải thuộc tính JPQL. Để dùng ví dụ cần import các annotation phù hợp từ **jakarta.persistence**.

Quy tắc của UNIQUE với các giá trị NULL có thể khác nhau giữa các DB và chế độ constraint. Nếu nghiệp vụ muốn đúng một record theo khóa cụ thể, kết hợp constraint, NOT NULL và khóa tương ứng. Khi truy cập đồng thời, phải bắt lỗi vi phạm unique từ DB và chuyển thành thông báo nghiệp vụ phù hợp.

## 10. insertable và updatable

Hai thuộc tính của @Column tác động trực tiếp đến SQL mà JPA tạo cho mapping:

~~~java
@Column(name = "external_ref", insertable = false, updatable = false)
private String externalReference;
~~~

| Cấu hình | INSERT do JPA tạo | UPDATE do JPA tạo | Ứng dụng nào phù hợp? |
|---|---|---|---|
| insertable=true, updatable=true | Có thể bao gồm cột | Có thể bao gồm cột | Thuộc tính đọc/ghi bình thường |
| insertable=true, updatable=false | Có thể bao gồm cột | Bỏ cột khỏi UPDATE | Giá trị ghi ban đầu rồi không sửa qua mapping này |
| insertable=false, updatable=true | Bỏ cột khỏi INSERT | Có thể bao gồm cột khi UPDATE | Cột do DB cấp ban đầu nhưng có thể chỉnh sau |
| insertable=false, updatable=false | Bỏ cột khỏi cả hai | Bỏ cột khỏi cả hai | Cột do DB tính, trigger quản lý, hoặc mapping chỉ đọc |

**Cảnh báo:** “không updatable” không có nghĩa object Java bất biến. Setter vẫn có thể làm giá trị trường trong bộ nhớ thay đổi; chỉ là thay đổi đó **không được JPA ghi vào cột bằng UPDATE thông thường**. Lúc đọc lại hoặc refresh, giá trị có thể khác giá trị đã gán trong Java.

### 10.1. Cột do database sinh

Ví dụ, DB có:

~~~sql
CREATE TABLE audit_records (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);
~~~

Entity có thể ánh xạ:

~~~java
@Entity
@Table(name = "audit_records")
public class AuditRecord {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String description;

    @Column(name = "created_at", insertable = false, updatable = false)
    private LocalDateTime createdAt;

    protected AuditRecord() {}

    public AuditRecord(String description) {
        this.description = description;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }
}
~~~

JPA bỏ **created_at** khỏi câu INSERT, để DB áp dụng DEFAULT CURRENT_TIMESTAMP. Không được giả định trường **createdAt** trong entity Java sẽ tự có giá trị mới ngay lập tức sau **persist()**: có thể cần **flush()** và **refresh()** trong transaction phù hợp hoặc tính năng đọc giá trị sinh tự động của provider.

~~~java
tx.begin();
AuditRecord record = new AuditRecord("created");
em.persist(record);
em.flush();
em.refresh(record);
LocalDateTime valueFromDatabase = record.getCreatedAt();
tx.commit();
~~~

Nếu DB không có DEFAULT hoặc trigger tương ứng, insertable=false không tự tạo giá trị cột. Khi cột còn ràng buộc NOT NULL, INSERT có thể thất bại.

### 10.2. insertable/updatable không phải bảo mật

Đặt **updatable=false** trên entity chỉ ngăn ORM ghi cột theo mapping đó. Nó không ngăn truy cập bằng native SQL, database tool hoặc một service khác. Muốn bảo vệ dữ liệu cần quyền DB, API authorization, ràng buộc nghiệp vụ và thiết kế cập nhật phù hợp.

## 11. columnDefinition và tính phụ thuộc SQL dialect

**columnDefinition** cho phép cung cấp chuỗi SQL dùng trong định nghĩa cột khi provider sinh schema:

~~~java
@Column(
    name = "status",
    nullable = false,
    columnDefinition = "varchar(24) default 'PENDING'"
)
private String status;
~~~

Ưu điểm: có thể dùng cú pháp SQL riêng của một database, ví dụ DEFAULT hoặc một kiểu cột cụ thể.

Hạn chế:

- Định nghĩa có thể **không portable** giữa PostgreSQL, Oracle, MySQL, SQL Server...
- Phần khai báo có thể xung đột với các thuộc tính khác (length, nullable) hoặc với schema đang tồn tại.
- Giá trị DEFAULT chỉ phát huy khi DB xử lý cột theo ngữ nghĩa mặc định; nếu JPA gửi explicit NULL trong INSERT, DB thường không tự áp dụng DEFAULT như khi cột bị bỏ khỏi INSERT.
- Sửa columnDefinition trong code không tự cập nhật schema của hệ thống đã triển khai.

Nếu mục tiêu là vận hành sản phẩm lâu dài, thường dùng migration SQL rõ ràng (Flyway, Liquibase hoặc quy trình tương đương) và để annotation phản ánh schema đã chốt. Chỉ dùng columnDefinition khi sự phụ thuộc database là chủ đích.

## 12. Thuộc tính table và bảng phụ

Thông thường, thuộc tính cơ bản nằm trong bảng chính của entity. Tham số **table** trên @Column có thể trỏ tới bảng phụ khi entity dùng **@SecondaryTable**:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.SecondaryTable;
import jakarta.persistence.Table;

@Entity
@Table(name = "employee")
@SecondaryTable(name = "employee_details")
public class Employee {
    @Id
    private Long id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Column(name = "biography", table = "employee_details")
    private String biography;

    protected Employee() {}
}
~~~

Ở đây, **displayName** lưu trong bảng **employee**, còn **biography** lưu trong bảng **employee_details** được liên kết bằng định danh theo mapping bảng phụ. Ví dụ giả định khóa ngoại/khóa chính dùng quy tắc mặc định tương thích; schema đặc biệt có thể phải cấu hình **@PrimaryKeyJoinColumn** hoặc tùy chọn liên quan.

Chỉ đặt **@Column(table = "employee_details")** mà không khai báo bảng phụ phù hợp sẽ không tạo ra một mô hình lưu hợp lệ. Đây là ánh xạ **các cột của cùng một entity trải trên nhiều bảng**, khác với quan hệ **@ManyToOne**, **@OneToMany** giữa nhiều entity.

## 13. @Basic và @Column khác những annotation liên quan như thế nào?

Một thuộc tính dùng cả @Basic lẫn @Column vẫn là **basic attribute**. Tuy nhiên, một số giá trị cần kiểu mapping bổ sung:

| Nhu cầu | Annotation/cơ chế thường dùng | Quan hệ với @Basic/@Column |
|---|---|---|
| Không lưu một trường vào database | @Transient hoặc transient Java theo quy tắc mapping | Trường bị loại khỏi persistence; @Column không áp dụng cho nó |
| Lưu enum theo tên | @Enumerated(EnumType.STRING) | @Column đặt tên cột/độ dài; @Enumerated quyết định biểu diễn |
| Lưu dữ liệu lớn | @Lob | Mô tả lưu dạng large object; @Column có thể cung cấp tên cột |
| Chuyển kiểu domain sang kiểu DB | @Convert và AttributeConverter | Converter chuyển giá trị; @Column mô tả cột |
| Ánh xạ thuộc tính tới bảng khác của cùng entity | @SecondaryTable, @Column(table=...) | Vẫn có thể là basic attribute |
| Ánh xạ quan hệ với entity khác | @ManyToOne, @OneToMany, ... | Dùng association mapping, không coi đơn giản là @Basic |
| Định danh của entity | @Id, @GeneratedValue | Khóa chính có thể dùng @Column cho tên cột nhưng có quy tắc riêng |
| Kiểm tra dữ liệu đầu vào | @NotNull, @NotBlank, @Size và validation layer | Bổ sung, không phải cơ chế mapping cột |

Ví dụ enum:

~~~java
public enum ProductStatus {
    DRAFT, ACTIVE, ARCHIVED
}

@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 20)
private ProductStatus status;
~~~

Lưu theo **EnumType.STRING** thường dễ hiểu và ổn định hơn ordinal khi thêm hoặc sắp xếp lại các giá trị enum; vẫn cần quản lý quá trình đổi tên enum vì chuỗi lưu trong DB cũng cần tương thích.

Ví dụ converter để ánh xạ kiểu domain:

~~~java
@Converter(autoApply = false)
public class YesNoConverter implements AttributeConverter<Boolean, String> {
    @Override
    public String convertToDatabaseColumn(Boolean value) {
        if (value == null) return null;
        return value ? "Y" : "N";
    }

    @Override
    public Boolean convertToEntityAttribute(String value) {
        if (value == null) return null;
        return "Y".equals(value);
    }
}

@Convert(converter = YesNoConverter.class)
@Column(name = "enabled_flag", length = 1)
private Boolean enabled;
~~~

Converter chuyển dữ liệu Boolean ↔ String; **length = 1** mô tả cột lưu ký hiệu. Việc áp dụng converter với các loại thuộc tính hoặc annotation mapping khác có giới hạn được đặc tả; cần xác nhận cấu hình khi dùng @Convert cùng @Enumerated hoặc các mapping đặc biệt.

## 14. Cách thay đổi thuộc tính được đồng bộ xuống database

Trong Unit of Work, một entity đang **managed** sẽ được JPA theo dõi. Khi ứng dụng đổi một thuộc tính ánh xạ cơ bản:

~~~java
EntityTransaction tx = em.getTransaction();
tx.begin();

Product product = em.find(Product.class, 5L);
if (product == null) {
    throw new IllegalArgumentException("Product not found");
}

product.changePrice(new BigDecimal("149.90"));
product.setInternalNote("Giá cập nhật theo đợt nhập mới");

tx.commit();
~~~

Đoạn mã giả định **em** là EntityManager RESOURCE_LOCAL đã tạo hợp lệ, được đóng tại tầng gọi và có cơ chế rollback khi lỗi. Không cần **em.update(product)** vì JPA không có API như vậy; dirty checking sẽ kiểm tra trạng thái các thuộc tính được ánh xạ khi đồng bộ.

Sơ đồ khái quát:

~~~mermaid
flowchart LR
    A[Entity Product managed] --> B[Thay đổi thuộc tính Java]
    B --> C[Persistence Context theo dõi]
    C --> D[Flush]
    D --> E[SQL UPDATE các cột được ghi]
    E --> F[Commit hoặc Rollback]
~~~

Nếu thuộc tính có **updatable = false**, provider không cập nhật cột đó bằng SQL UPDATE thông thường ngay cả khi thuộc tính đã bị thay đổi trong Java. Nếu entity đã **detached**, sửa thuộc tính cũng không tự sinh UPDATE; khi cần hợp nhất trạng thái, dùng **merge()** đúng cách và thao tác trên entity managed được trả về.

Không nên suy ra provider luôn tạo SQL UPDATE chứa duy nhất trường đã đổi: chiến lược tạo SQL, dirty checking và dynamic update là chi tiết triển khai của ORM. Điều chuẩn cần dựa vào là **ngữ nghĩa của mapping và transaction**.

## 15. Schema generation, migrations và dữ liệu đang tồn tại

Các thuộc tính **nullable**, **unique**, **length**, **precision**, **scale** và **columnDefinition** đặc biệt hữu ích khi **JPA tạo schema** hoặc khi một provider dùng chúng để suy ra SQL. Chúng **không phải công cụ migration đầy đủ** cho một database đã có dữ liệu.

Phân biệt ba lớp:

1. **Java/JPA mapping:** định nghĩa thuộc tính nào thuộc entity và chúng tương ứng với cột nào.
2. **Cơ sở dữ liệu:** các cột, kiểu dữ liệu, constraints, indexes hiện có mới thực thi các giới hạn ở DB.
3. **Quy trình triển khai:** tạo hoặc thay đổi schema bằng migration và kiểm tra tương thích dữ liệu cũ.

Giả sử ban đầu **sku** lưu trong VARCHAR(255), sau đó sửa thành:

~~~java
@Column(name = "sku", length = 40, nullable = false, unique = true)
private String sku;
~~~

Trong hệ thống đã chạy, cần xác định có SKU hiện tại dài hơn 40 ký tự không, có giá trị NULL không, có dữ liệu trùng không và cần migration nào để thay đổi cột, thêm constraint. Chỉ sửa annotation không giải quyết tự động các vấn đề đó.

Khi phát triển, tính năng tự tạo/kiểm tra schema của provider có thể hữu ích. Trong production, thường nên dùng migration có phiên bản và kiểm soát rõ những thay đổi làm mất hoặc biến đổi dữ liệu.

## 16. Những lỗi thường gặp khi dùng @Basic và @Column

### 16.1. Nghĩ rằng @Column(nullable = false) là validator cho HTTP request

~~~java
@Column(nullable = false)
private String name;
~~~

Mapping thể hiện yêu cầu cột không chấp nhận NULL, nhưng không đảm bảo người dùng nhận lỗi “Tên không được trống” ngay khi nhập. Hãy xác thực request/DTO, quy tắc nghiệp vụ, đồng thời giữ constraint ở DB.

### 16.2. Dùng @Column(length) để giới hạn giá trị trong bộ nhớ

~~~java
@Column(length = 20)
private String code;
~~~

Một String dài 200 ký tự vẫn có thể được gán vào **code** trong Java. Lỗi có thể chỉ xuất hiện lúc flush/commit, hoặc provider/DB có hành vi khác nhau. Cần kiểm tra độ dài trước khi lưu khi hợp đồng API yêu cầu.

### 16.3. Dùng double cho số tiền

~~~java
@Column(precision = 13, scale = 2)
private double amount;
~~~

Chỉ đặt precision/scale không sửa được sai số biểu diễn nhị phân của **double**. Ưu tiên **BigDecimal** cho số tiền, đồng thời quy định cách làm tròn và đơn vị tiền tệ.

### 16.4. Dùng fetch = LAZY rồi cho rằng truy vấn chắc chắn nhẹ

~~~java
@Basic(fetch = FetchType.LAZY)
private String largeText;
~~~

Đây là hint cho basic attribute, có thể yêu cầu bytecode enhancement mới trì hoãn tải thật sự. Nếu cần tối ưu chắc chắn, dùng query projection chỉ lấy cột cần thiết và đo SQL thực tế ở môi trường triển khai.

### 16.5. Đặt annotation sai phía access

Nếu @Id đặt trên field nhưng @Column đặt trên getter, mapping không nên được kỳ vọng tuân theo getter. Hãy thống nhất field access hoặc property access, hoặc chỉ rõ **@Access** theo quy tắc JPA.

### 16.6. Hiểu sai insertable = false

**insertable = false** không có nghĩa cột sẽ tự có giá trị. Nếu DB không sinh giá trị và cột NOT NULL, INSERT có thể thất bại. Nếu DB có default, đối tượng Java không nhất thiết nhìn thấy default cho đến khi tải lại/refresh.

### 16.7. Dùng unique = true thay thế ràng buộc duy nhất nhiều cột

**unique = true** phù hợp shortcut cho một cột. Nghiệp vụ như “mỗi tenant có mã sản phẩm riêng” phải khai báo unique gồm **tenant_id, product_code** ở cấp bảng và bảo đảm ràng buộc thật sự tồn tại ở DB.

### 16.8. Nhầm tên field với tên cột trong JPQL

Trong **select p from Product p where p.displayName = :name**, **displayName** là tên thuộc tính Java. Trong SQL native, cột thực là **display_name** theo @Column. Dùng sai tên gây lỗi parse truy vấn hoặc sai kết quả.

### 16.9. Đọc lại entity managed sau cập nhật trực tiếp bằng SQL

Nếu một câu native SQL hoặc JPQL bulk UPDATE sửa bảng, instance entity đang managed có thể vẫn giữ giá trị cũ. @Column không tự làm refresh. Khi trộn bulk DML với persistence context, cần chủ động đồng bộ hoặc làm mới context đúng thời điểm.

## 17. Bài tập thực hành

### Bài 1: Ánh xạ khách hàng

Yêu cầu tạo entity **Customer** với:

- Khóa chính **id** kiểu Long, do DB sinh.
- **fullName**: bắt buộc, cột **full_name**, tối đa 120 ký tự.
- **email**: bắt buộc, cột **email_address**, tối đa 254 ký tự, duy nhất.
- **loyaltyPoints**: kiểu int, cột **loyalty_points**, không cho SQL NULL.

Một lời giải minh họa:

~~~java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Basic(optional = false)
    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @Basic(optional = false)
    @Column(
        name = "email_address",
        nullable = false,
        unique = true,
        length = 254
    )
    private String email;

    @Column(name = "loyalty_points", nullable = false)
    private int loyaltyPoints;

    protected Customer() {}

    public Customer(String fullName, String email) {
        this.fullName = fullName;
        this.email = email;
        this.loyaltyPoints = 0;
    }
}
~~~

Với dữ liệu đầu vào từ API, nên bổ sung validation phù hợp. Hãy kiểm tra DDL và unique constraint đã tồn tại trước khi dựa vào ràng buộc DB.

### Bài 2: Giải thích mapping

~~~java
@Basic(optional = false, fetch = FetchType.LAZY)
@Column(name = "summary", nullable = false, length = 500)
private String summary;
~~~

**Câu hỏi:** Có thể khẳng định thuộc tính chỉ tải khi gọi getter không?

**Trả lời:** Không. LAZY đối với basic attribute là hint và có thể cần hỗ trợ bytecode enhancement của provider. **optional = false** và **nullable = false** liên quan tính hợp lệ của giá trị null ở tầng mapping/schema, không làm lazy loading được bảo đảm.

### Bài 3: Phân tích cấu hình thiếu nhất quán

~~~java
@Column(name = "price", nullable = false, precision = 10, scale = 2)
private BigDecimal price;
~~~

Nếu bảng thật có cột **price VARCHAR(30)**, ứng dụng có chắc ghi/đọc đúng không?

**Trả lời:** Không. Mapping Java dự kiến một giá trị BigDecimal với cách chuyển JDBC phù hợp, nhưng schema thực lại dùng chuỗi. Nhà cung cấp có thể không tương thích hoặc DB phải chuyển kiểu với rủi ro lỗi. Cần làm cho mapping và schema phù hợp qua migration hoặc mapping/converter rõ ràng.

### Bài 4: Cột ngày do database tạo

Yêu cầu **created_at** do DB tự đặt khi INSERT và ứng dụng không tự UPDATE. Cách khai báo nào hợp lý?

~~~java
@Column(name = "created_at", insertable = false, updatable = false)
private LocalDateTime createdAt;
~~~

**Giải thích:** Cần thêm DEFAULT/trigger tương ứng ở DB. Sau INSERT, cần tải lại giá trị theo cách thích hợp nếu mã Java muốn dùng ngay ngày tạo.

### Bài 5: Chọn mapping cho mã định danh hiển thị

Một hệ thống bán hàng có **orderNumber** là chuỗi dễ đọc, tối đa 30 ký tự; mỗi số đơn hàng phải duy nhất. Khóa chính kỹ thuật vẫn là **id** Long.

~~~java
@Basic(optional = false)
@Column(name = "order_number", nullable = false, unique = true, length = 30)
private String orderNumber;
~~~

**Giải thích:** **orderNumber** là business key có unique constraint riêng, không nhất thiết thay thế khóa chính kỹ thuật **id**. Hãy bảo đảm quy trình phát số đơn tránh xung đột đồng thời và xử lý lỗi unique từ DB.

## 18. Bảng ghi nhớ

| Muốn làm gì? | Nên dùng gì? |
|---|---|
| Lưu một String/int/BigDecimal theo mapping mặc định | Không nhất thiết cần @Basic hay @Column |
| Thông báo giá trị basic attribute không được null | @Basic(optional = false), thường kết hợp @Column(nullable = false) |
| Đổi tên cột trong DB | @Column(name = "...") |
| Giới hạn độ dài cột VARCHAR khi sinh schema | @Column(length = ...) |
| Xác định số chữ số cho DECIMAL | @Column(precision = ..., scale = ...) với BigDecimal |
| Ràng buộc unique một cột | @Column(unique = true) và bảo đảm constraint ở DB |
| Ràng buộc unique nhiều cột | @Table(uniqueConstraints = ...) |
| Bỏ cột khỏi INSERT/UPDATE do ORM sinh | @Column(insertable = false/updatable = false) |
| Gợi ý tải chậm một thuộc tính cơ bản | @Basic(fetch = LAZY), lưu ý phụ thuộc provider |
| Dùng định nghĩa cột SQL đặc thù | @Column(columnDefinition = "..."), cân nhắc tính portable |
| Lưu thuộc tính ở bảng phụ của cùng entity | @SecondaryTable + @Column(table = "...") |
| Kiểm tra dữ liệu trước khi lưu | Validation, logic nghiệp vụ và DB constraints |

Khi thiết kế một thuộc tính JPA, hãy xác định **kiểu Java**, **kiểu cột SQL**, **quy tắc null/unique/độ dài**, **cách tải**, **quyền tham gia INSERT/UPDATE** và **schema hiện hành**. @Basic mô tả ngữ nghĩa của basic attribute trong JPA; @Column điều chỉnh cách thuộc tính gắn với cột vật lý. Hiểu rõ hai phần này giúp mapping dễ bảo trì và tránh nhiều lỗi chỉ xuất hiện khi ứng dụng flush hoặc commit dữ liệu.
