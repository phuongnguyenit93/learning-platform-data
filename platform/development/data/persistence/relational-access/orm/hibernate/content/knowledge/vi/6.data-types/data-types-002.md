# Chuỗi, số, boolean, dữ liệu nhị phân và đối tượng lớn trong Hibernate ORM

Hibernate ORM giúp lưu các thuộc tính Java vào cột của cơ sở dữ liệu quan hệ và đọc các giá trị đó trở lại thành đối tượng. Với các kiểu cơ bản như `String`, `Integer`, `BigDecimal`, `Boolean` hoặc `byte[]`, việc ánh xạ thường được Hibernate thực hiện tự động. Tuy nhiên, **kiểu Java không quyết định duy nhất kiểu cột SQL thực tế**: JDBC driver, Hibernate dialect, cấu hình ánh xạ, phiên bản framework và thiết kế schema cùng ảnh hưởng đến kết quả.

Bài này trình bày cách Hibernate xử lý năm nhóm dữ liệu thường gặp:

1. Chuỗi ký tự: văn bản ngắn, dài, Unicode và cách giới hạn độ dài.
2. Số: số nguyên, số thực, số thập phân chính xác và giới hạn miền giá trị.
3. Boolean: giá trị đúng/sai, khả năng null và dữ liệu legacy.
4. Dữ liệu nhị phân: `byte[]`, cột binary và chi phí bộ nhớ.
5. Đối tượng lớn: `BLOB`, `CLOB`, cách lưu và truy cập dữ liệu có kích thước lớn.

Đích đến là lựa chọn ánh xạ đúng về **ý nghĩa nghiệp vụ, độ chính xác, hiệu năng và khả năng tương thích database**, thay vì chỉ đặt annotation để Hibernate tự tạo schema.

## 1. Chuỗi chuyển đổi từ Java đến cơ sở dữ liệu

Với một thuộc tính entity, Hibernate cần giải quyết hai việc khác nhau:

- **Ánh xạ phía Java**: thuộc tính có kiểu và cách biểu diễn nào trong chương trình?
- **Ánh xạ phía JDBC/SQL**: giá trị sẽ được gắn vào tham số JDBC và đọc từ kết quả SQL bằng cách nào? Cột của database sử dụng loại dữ liệu gì?

Luồng khái niệm:

```text
Entity Java
  String | Integer | BigDecimal | Boolean | byte[]
                        |
                        v
                  Hibernate ORM
             Java type + JDBC type
                        |
                        v
                    JDBC driver
                        |
                        v
                   SQL column
      VARCHAR | INTEGER | DECIMAL | BOOLEAN
               VARBINARY | BLOB | CLOB
```

Chẳng hạn, thuộc tính `String description` thường được ánh xạ thành chuỗi thông qua JDBC và cột kiểu `VARCHAR`, nhưng ánh xạ cụ thể có thể được điều chỉnh bằng `@Column`, `@Lob`, `@Nationalized` hoặc một annotation riêng của Hibernate.

### Ánh xạ mặc định và ánh xạ tường minh

Với entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;
    private Integer quantity;
    private Boolean active;

    protected Product() {
    }
}
```

Hibernate có thể suy ra cách lưu các trường cơ bản mà không yêu cầu `@Column` cho từng thuộc tính. Nếu ứng dụng cần giới hạn cụ thể, tên cột khác, kiểu lớn hoặc precision/scale, phải khai báo và đảm bảo schema thật sự tương thích.

**Lưu ý quan trọng:** thuộc tính `@Column(length = 100)` là metadata ánh xạ và hỗ trợ tạo DDL; nó **không thay thế validation ở API** và không tự bảo đảm cột hiện hữu đã có kích thước phù hợp. Đối với database được quản lý bằng migration, việc thay đổi annotation phải đi kèm migration tương ứng.

## 2. Chuỗi ký tự: `String`, `CHAR`, `VARCHAR` và Unicode

### 2.1. `String` và cột `VARCHAR`

Đối với các chuỗi thông thường, kiểu Java phổ biến nhất là `String`. Hibernate thường sử dụng loại JDBC dành cho chuỗi, tương ứng với `VARCHAR` hoặc biến thể do dialect xác định.

Ví dụ:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    @Column(name = "phone_number", length = 32)
    private String phoneNumber;

    protected Customer() {
    }
}
```

Trong ví dụ:

- `displayName` có độ dài khai báo là 120; database thường sử dụng một cột chuỗi có kích thước tương ứng khi Hibernate tạo schema.
- `nullable = false` cung cấp metadata về tính bắt buộc của cột; nên có ràng buộc `NOT NULL` thực sự trong database.
- `phoneNumber` dùng `String` thay vì số nguyên vì số điện thoại có thể chứa dấu `+`, số `0` ở đầu hoặc ký tự phân cách; số điện thoại không phải đại lượng để cộng/trừ.

Dùng `VARCHAR` cho chuỗi có độ dài thay đổi thường hợp lý hơn `CHAR` nếu không có yêu cầu cố định độ rộng. `CHAR(n)` có semantics đệm khoảng trắng tùy database và cách so sánh có thể khác kỳ vọng với dữ liệu người dùng.

### 2.2. `length` là giới hạn loại cột, không phải kiểm tra nghiệp vụ đầy đủ

`@Column(length = 120)` không tự làm xuất hiện một thông báo thân thiện khi client gửi chuỗi dài 121 ký tự. Kết quả có thể phụ thuộc schema, dialect và database: câu lệnh ghi thất bại, dữ liệu bị từ chối hoặc có hành vi khác theo hệ quản trị/cấu hình.

Nếu muốn kiểm tra ở tầng Java, ứng dụng có thể dùng Jakarta Bean Validation:

```java
import jakarta.persistence.Column;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

@NotBlank
@Size(max = 120)
@Column(name = "display_name", nullable = false, length = 120)
private String displayName;
```

`@Size` đo độ dài chuỗi theo cách của Bean Validation; còn `VARCHAR(n)` có thể áp dụng quy tắc đếm ký tự/byte khác nhau theo database và encoding. Với Unicode, emoji hoặc ký tự được biểu diễn bằng nhiều code unit, **giới hạn ở Java và giới hạn SQL không nhất thiết đồng nhất tuyệt đối**. Nên kiểm thử dữ liệu thực tế, nhất là khi dùng nhiều ngôn ngữ.

### 2.3. Unicode và dữ liệu quốc tế hóa

`String` là chuỗi Unicode ở phía Java. Để lưu đúng tiếng Việt, tiếng Trung hoặc emoji, database, cột, JDBC driver và cấu hình encoding phải hỗ trợ phù hợp.

Một số hệ quản trị dùng `NVARCHAR`/`NCHAR` để biểu diễn nationalized character data, trong khi hệ khác có `VARCHAR` hỗ trợ UTF-8 đầy đủ. Hibernate hỗ trợ annotation `@Nationalized` khi cần yêu cầu ánh xạ nationalized theo khả năng của dialect:

```java
import jakarta.persistence.Column;
import org.hibernate.annotations.Nationalized;

@Nationalized
@Column(length = 200)
private String localizedTitle;
```

Không nên cho rằng `@Nationalized` bắt buộc ở mọi database để lưu tiếng Việt. Ví dụ, cột `VARCHAR` trên PostgreSQL dùng encoding UTF-8 của database thường đã đáp ứng Unicode. Ngược lại, một số cấu hình SQL Server dùng `NVARCHAR` cho dữ liệu Unicode có thể thích hợp hơn.

**Khuyến nghị:** quyết định encoding/collation của database và loại cột từ nhu cầu tìm kiếm, sắp xếp, so sánh và ngôn ngữ thực tế. Hãy coi annotation là phần mô tả của thiết kế ấy.

### 2.4. Chuỗi dài: `VARCHAR` lớn, `TEXT` và `CLOB`

Không phải mọi nội dung văn bản đều nên ánh xạ giống tên sản phẩm. Mô tả dài, nội dung tài liệu và log có yêu cầu lưu trữ, truy vấn và index khác nhau.

Ba nhóm thường gặp:

| Kiểu cột | Mục đích | Lưu ý |
|---|---|---|
| `VARCHAR(n)` | Chuỗi có giới hạn rõ ràng | Thích hợp tên, mã, nhãn; chọn độ dài theo nghiệp vụ |
| `TEXT` hoặc dạng chuỗi dài của DB | Văn bản dài; tên/semantics phụ thuộc hệ quản trị | Không có một tên kiểu SQL thống nhất cho mọi database |
| `CLOB` / `NCLOB` | Character Large Object, có thể có cách truy cập LOB riêng | Kiểu và API truy cập phụ thuộc dialect, driver và thiết kế schema |

Ví dụ dùng `@Lob` cho văn bản lớn:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Lob;

@Lob
@Column(name = "full_content")
private String fullContent;
```

Với `String`, `@Lob` thường biểu thị mong muốn lưu theo **character LOB**, như `CLOB`. Tuy nhiên, **không được đồng nhất `@Lob String` với một cột `TEXT` thông thường**. Một số database/driver có cách lưu và truy cập LOB khác biệt rõ ràng.

Khi chỉ cần một cột chuỗi dài theo kiểu JDBC `LONGVARCHAR` thay vì LOB, Hibernate 6 có API ánh xạ riêng:

```java
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@JdbcTypeCode(SqlTypes.LONGVARCHAR)
private String fullContent;
```

`@JdbcTypeCode` là API riêng của Hibernate và ví dụ trên áp dụng cho dòng Hibernate hỗ trợ annotation này. Loại SQL vật lý vẫn do dialect/schema quyết định. Nếu viết:

```java
@Column(columnDefinition = "TEXT")
private String fullContent;
```

thì đó là một lựa chọn phụ thuộc vào database có kiểu `TEXT` tương ứng; `columnDefinition` chủ yếu ảnh hưởng khai báo DDL và không tự giải quyết mọi khác biệt trong binding JDBC. Vì thế, không nên sử dụng định nghĩa này như một “bản vá” phổ quát cho mapping LOB.

## 3. Số nguyên: `Byte`, `Short`, `Integer`, `Long` và `BigInteger`

Các kiểu số nguyên Java khác nhau về khoảng giá trị và khả năng chứa `null`.

| Java | Mục đích thường gặp | Nhóm SQL/JDBC thường tương ứng | Điểm chú ý |
|---|---|---|---|
| `byte` / `Byte` | Giá trị nguyên nhỏ | `TINYINT` hoặc tương đương | Không phải database nào cũng có TINYINT |
| `short` / `Short` | Giá trị nguyên ngắn | `SMALLINT` | Khoảng giá trị nhỏ hơn `Integer` |
| `int` / `Integer` | Đếm, số lượng thông thường | `INTEGER` | Dễ tràn nếu miền giá trị rất lớn |
| `long` / `Long` | ID, counter lớn | `BIGINT` | Phổ biến cho khóa chính |
| `BigInteger` | Số nguyên rất lớn | `NUMERIC`/`DECIMAL` hoặc ánh xạ phù hợp | Cần precision đủ lớn ở database |

Tương quan trên mô tả ý tưởng chung; dialect có thể chọn type SQL khác. Tránh suy ra một loại cột cố định chỉ từ tên kiểu Java.

Ví dụ:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class WarehouseStock {
    @Id
    private Long productId;

    @Column(nullable = false)
    private Integer availableUnits;

    @Column(nullable = false)
    private Long lifetimeUnitsSold;

    protected WarehouseStock() {
    }
}
```

### Chọn primitive hay wrapper?

`int`, `long`, `boolean` không chứa được `null`, trong khi `Integer`, `Long`, `Boolean` có thể. Điều này quan trọng khi thiết kế ràng buộc:

- `Integer quantity` có thể biểu diễn dữ liệu chưa biết nếu schema cho phép `NULL`.
- `int quantity` mặc định `0` khi khởi tạo object Java; `0` có thể mang nghĩa “không còn hàng”, khác với “chưa biết”.
- Với các trường bắt buộc, wrapper vẫn hữu ích trong giai đoạn entity mới chưa có giá trị hợp lệ, nhưng cần validation hoặc quy tắc khởi tạo rõ ràng.

Đặc biệt, khóa chính sinh tự động thường sử dụng `Long id`; trạng thái `id == null` trước khi được cấp khóa có ý nghĩa tự nhiên. `long` có giá trị mặc định `0` nên dễ gây nhầm trong mã nghiệp vụ.

### Tràn số và giới hạn của database

Cột `INTEGER` và `BIGINT` có khoảng giá trị hữu hạn. Việc Java dùng `Long` không đảm bảo mọi database tự hỗ trợ đúng miền giá trị trong cấu hình cột đang có. Với `BigInteger`, cần chủ động chọn độ chính xác đủ lớn; không nên giả định database có thể lưu số nguyên tùy ý lớn.

Ngoài ra, entity có annotation `@Column(nullable = false)` không thay thế việc kiểm tra số âm, giới hạn số lượng hoặc điều kiện nghiệp vụ như “đơn hàng phải có số lượng lớn hơn 0”.

## 4. Số thực và số thập phân chính xác

Có hai nhóm rất khác nhau:

- **Dấu phẩy động nhị phân**: `float`/`Float` và `double`/`Double`.
- **Số thập phân tùy ý độ chính xác trong Java**: `BigDecimal`.

### 4.1. `float` và `double`: phù hợp đo lường gần đúng

Các kiểu `float`/`double` sử dụng biểu diễn nhị phân theo IEEE 754 và không thể biểu diễn chính xác mọi số thập phân. Ví dụ:

```java
double result = 0.1 + 0.2;
System.out.println(result); // Thường in 0.30000000000000004.
```

Điều này không phải lỗi của Hibernate. Nó xuất phát từ biểu diễn số dấu phẩy động. Các kiểu này phù hợp trong nhiều bài toán đo lường, thống kê, khoa học và tính toán chấp nhận sai số xác định.

Với số tiền, thuế suất cần chính xác theo chữ số thập phân hoặc số dư tài khoản, `double` thường không phù hợp.

### 4.2. `BigDecimal` cho giá trị thập phân cần chính xác

`BigDecimal` lưu giá trị thập phân theo cách cho phép xử lý chính xác các chữ số đã khai báo (trong phạm vi thao tác và rounding mode được lựa chọn).

Ví dụ entity:

```java
import java.math.BigDecimal;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class InvoiceLine {
    @Id
    private Long id;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal amount;

    protected InvoiceLine() {
    }

    public InvoiceLine(Long id, BigDecimal amount) {
        this.id = id;
        this.amount = amount;
    }
}
```

Thông số:

- **`precision = 18`**: tổng số chữ số thập phân của giá trị theo khai báo kiểu `DECIMAL/NUMERIC`.
- **`scale = 2`**: số chữ số phần thập phân.
- Với một cột `DECIMAL(18,2)`, thường tối đa 16 chữ số ở phần nguyên và 2 chữ số thập phân, tùy khả năng và quy tắc cụ thể của database.

Ví dụ khởi tạo:

```java
BigDecimal price = new BigDecimal("1250.75");

BigDecimal tax = price.multiply(new BigDecimal("0.10"));
BigDecimal total = price.add(tax)
    .setScale(2, java.math.RoundingMode.HALF_UP);
```

Sử dụng constructor từ chuỗi hoặc `BigDecimal.valueOf(double)` khi phù hợp. Tránh:

```java
BigDecimal price = new BigDecimal(0.1); // Mang theo sai số nhị phân của double.
```

### `precision` và `scale` không tự thực hiện quy tắc làm tròn nghiệp vụ

Nếu Java đưa vào `BigDecimal("123.456")` nhưng cột chỉ cho phép scale 2, database có thể làm tròn hoặc từ chối tùy hệ quản trị/cấu hình. Hibernate annotation không tự xác lập chính sách “luôn làm tròn HALF_UP” cho toàn hệ thống.

Trong nghiệp vụ tài chính, hãy xác định rõ:

1. Đơn vị tiền tệ và số chữ số thập phân hợp lệ.
2. Cách làm tròn, thời điểm làm tròn và chính sách cộng dồn.
3. Ràng buộc database và validation trước khi lưu.
4. Cách xử lý các giá trị vượt precision/scale.

Ngoài ra, `BigDecimal.equals` xét cả scale, trong khi `compareTo` xét giá trị số:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
```

Khi so sánh ý nghĩa tiền tệ, cân nhắc `compareTo` hoặc chuẩn hóa scale theo quy tắc domain, thay vì dựa vào `equals` một cách máy móc.

### Bảng chọn kiểu số

| Nhu cầu | Kiểu Java thường phù hợp | Vì sao |
|---|---|---|
| Số lượng nguyên nhỏ/vừa | `Integer` hoặc `int` | Rõ ràng, tính toán nguyên |
| ID hoặc số đếm lớn | `Long` / `long` | Miền giá trị rộng |
| Số nguyên cực lớn | `BigInteger` | Tránh giới hạn `long`, cần schema tương ứng |
| Kích thước, đo lường gần đúng | `Double` / `double` | Chấp nhận được sai số floating point |
| Giá tiền, tỷ lệ cần biểu diễn thập phân chính xác | `BigDecimal` | Kiểm soát precision, scale và rounding |

## 5. Boolean: `boolean`, `Boolean` và dữ liệu legacy

Ở Java, giá trị đúng/sai được biểu diễn bằng `boolean` hoặc `Boolean`. Hibernate có thể ánh xạ sang JDBC `BOOLEAN` hoặc cách lưu tương ứng mà dialect hỗ trợ. Không phải hệ quản trị nào cũng có một kiểu SQL `BOOLEAN` vật lý giống nhau.

Ví dụ:

```java
import jakarta.persistence.Column;

@Column(name = "active", nullable = false)
private boolean active;
```

Tùy database, một giá trị boolean có thể được lưu bằng kiểu `BOOLEAN`, `BIT` hoặc một biểu diễn tương đương. **Ứng dụng nên truy vấn trên thuộc tính entity**, ví dụ `where p.active = true` trong JPQL, thay vì giả định dữ liệu vật lý luôn là số `1` hay chuỗi `'Y'`.

### 5.1. `boolean` khác `Boolean` khi có giá trị không xác định

- `boolean`: chỉ có `true` và `false`; giá trị mặc định là `false`.
- `Boolean`: có thể là `true`, `false` hoặc `null`.

Ví dụ “đã được phê duyệt chưa?” có thể cần ba trạng thái: chưa đánh giá, đã phê duyệt, bị từ chối. Chỉ một `Boolean` nullable có thể mô tả kỹ thuật nhưng chưa chắc là mô hình domain rõ nhất; `enum` trạng thái có thể phù hợp hơn nếu nghiệp vụ phức tạp.

Nếu database có `NULL` mà entity khai báo primitive `boolean`, việc đọc dữ liệu có thể gặp sự cố do không có giá trị Java tương ứng. Cần thống nhất nullable giữa schema, mapping và quy tắc nghiệp vụ.

### 5.2. Boolean lưu dạng `Y`/`N` hoặc `1`/`0`

Cơ sở dữ liệu cũ đôi khi dùng cột `CHAR(1)` chứa `Y` hoặc `N`. Có thể chuyển bằng **`AttributeConverter`** chuẩn Jakarta Persistence:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class YesNoBooleanConverter
        implements AttributeConverter<Boolean, String> {

    @Override
    public String convertToDatabaseColumn(Boolean value) {
        if (value == null) {
            return null;
        }
        return value ? "Y" : "N";
    }

    @Override
    public Boolean convertToEntityAttribute(String dbValue) {
        if (dbValue == null) {
            return null;
        }
        return switch (dbValue) {
            case "Y" -> true;
            case "N" -> false;
            default -> throw new IllegalArgumentException(
                "Invalid boolean database value: " + dbValue
            );
        };
    }
}
```

Áp dụng cho trường cụ thể:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Convert;

@Convert(converter = YesNoBooleanConverter.class)
@Column(name = "is_enabled", length = 1)
private Boolean enabled;
```

Từ phía Java, `enabled` vẫn là `Boolean`; trong database, dữ liệu là `Y` hoặc `N`. Việc xử lý `null` cần thống nhất với schema và logic sử dụng.

Các phiên bản Hibernate hiện đại còn có những converter/kiểu boolean dựng sẵn cho biểu diễn phổ biến. Nên kiểm tra tài liệu phiên bản trước khi tự viết converter; ví dụ ở trên minh họa cách làm có tính chuẩn và có thể mở rộng theo miền dữ liệu.

### 5.3. Chú ý đến cơ chế lọc theo SQL

Khi dùng converter, điều kiện JPQL trên thuộc tính boolean thường có thể được Hibernate xử lý theo mapping. Nhưng nếu bạn tự viết native SQL:

```sql
SELECT *
FROM legacy_settings
WHERE is_enabled = 'Y';
```

thì cần dùng biểu diễn thực tế của cột. Native SQL làm việc với schema vật lý, không tự diễn giải mọi khái niệm thuộc tính Java như JPQL.

## 6. Dữ liệu nhị phân: `byte[]` và cột binary

Không phải dữ liệu nào cũng là văn bản. Ảnh, mã hóa, file nén, nội dung giao thức hay dữ liệu serialize có thể được biểu diễn bằng dãy byte.

Kiểu Java thông dụng là `byte[]`:

```java
import jakarta.persistence.Column;

@Column(name = "checksum", length = 32)
private byte[] checksum;
```

Một chuỗi băm SHA-256 dạng raw bytes có độ dài 32 byte là ví dụ hợp lý cho một cột binary có giới hạn. Nếu lưu SHA-256 dạng chuỗi hexadecimal, chiều dài biểu diễn và loại cột sẽ khác.

### 6.1. `VARBINARY` không đồng nghĩa `BLOB`

| Kiểu lưu trữ | Đặc điểm | Tình huống thường gặp |
|---|---|---|
| `BINARY(n)` | Dữ liệu nhị phân với kích thước cố định theo semantics database | Hash/dữ liệu cố định nếu DB hỗ trợ phù hợp |
| `VARBINARY(n)` | Dữ liệu nhị phân có giới hạn chiều dài | Token bytes, checksum, payload nhỏ |
| Dạng binary dài của DB | Cột dành cho payload nhị phân lớn hơn giới hạn thông thường | File/payload trung bình, phụ thuộc dialect |
| `BLOB` | Binary Large Object, có thể được DB xử lý như LOB riêng | Tài liệu nhị phân lớn, ảnh, âm thanh, video khi chủ động lưu trong DB |

Hibernate có thể dùng mapping binary mặc định cho `byte[]`, còn `@Lob` chỉ định ý định lưu như binary LOB:

```java
import jakarta.persistence.Basic;
import jakarta.persistence.FetchType;
import jakarta.persistence.Lob;

@Lob
@Basic(fetch = FetchType.LAZY)
private byte[] fileData;
```

Với `byte[]`, `@Lob` thường diễn đạt **BLOB semantics**. Nhưng `FetchType.LAZY` trên **basic attribute** chỉ là một yêu cầu/hint theo khả năng của provider; Hibernate thường cần bytecode enhancement thích hợp để lazy-load một thuộc tính basic. Nếu không có cơ chế tương ứng, dữ liệu vẫn có thể được tải ngay khi tải entity. Vì vậy không nên coi `@Basic(fetch = LAZY)` là bảo đảm tránh đọc toàn bộ file.

### 6.2. `byte[]` và `Byte[]`

`byte[]` là mảng primitive, thường phù hợp để biểu diễn một chuỗi bytes thực tế. `Byte[]` là mảng wrapper có thể chứa phần tử `null`; ý nghĩa và cơ chế mapping có thể khác theo version Hibernate, đặc biệt khi xử lý null element.

Đối với payload nhị phân thông thường, **ưu tiên `byte[]`** trừ khi thực sự có yêu cầu đặc biệt về kiểu wrapper. Đừng chọn `Byte[]` chỉ vì muốn cột nullable: bản thân trường `byte[]` cũng có thể bằng `null`.

### 6.3. Dữ liệu nhị phân và chi phí bộ nhớ

Nếu trường `byte[] fileData` chứa 40 MB, đọc entity kèm thuộc tính đó có thể tạo mảng byte kích thước lớn trong heap JVM. Khi nhiều request cùng truy cập, chi phí bộ nhớ và truyền dữ liệu tăng nhanh.

Ví dụ ứng dụng chỉ cần danh sách tên file:

```java
List<FileSummary> summaries = entityManager.createQuery("""
    select new com.example.files.FileSummary(f.id, f.fileName, f.contentType)
    from StoredFile f
    order by f.fileName
    """, FileSummary.class)
    .getResultList();
```

Câu JPQL sử dụng **constructor projection** để chỉ chọn metadata cần thiết. `FileSummary` là DTO có constructor tương ứng; ví dụ này giả định `StoredFile` có các thuộc tính được truy vấn. Cách chọn dữ liệu theo nhu cầu thường đáng tin cậy hơn việc tải cả entity chứa payload lớn rồi hy vọng thuộc tính `@Lob` luôn lazy.

### 6.4. Tránh lưu object Java tùy ý bằng serialize nhị phân

Một mảng byte có thể chứa dữ liệu serialize của object Java, nhưng việc này dễ tạo phụ thuộc chặt vào cấu trúc class, phiên bản runtime và rủi ro bảo mật khi deserialize dữ liệu không đáng tin cậy.

Nếu cần lưu cấu trúc nghiệp vụ, ưu tiên các cột quan hệ phù hợp hoặc định dạng có hợp đồng rõ ràng như JSON/Avro/Protobuf tùy yêu cầu. Không nên mặc định lưu cả object graph dưới dạng BLOB thay cho thiết kế persistence.

## 7. LOB là gì? Phân biệt `BLOB`, `CLOB`, `NCLOB`

**LOB (Large Object)** là nhóm kiểu dữ liệu dành cho nội dung lớn. Có ba khái niệm phổ biến:

- **BLOB — Binary Large Object**: chuỗi byte.
- **CLOB — Character Large Object**: văn bản ký tự.
- **NCLOB — National Character Large Object**: văn bản theo semantics nationalized của DB.

Trong Jakarta Persistence, `@Lob` là annotation đánh dấu thuộc tính cần được lưu như large object.

Ví dụ:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;

@Entity
public class Document {
    @Id
    private Long id;

    @Column(nullable = false, length = 200)
    private String title;

    @Lob
    private String body;

    @Lob
    private byte[] attachment;

    protected Document() {
    }
}
```

Ý nghĩa:

- `body` dùng `String` và `@Lob`, ứng với character LOB như `CLOB` hoặc dạng thích hợp do Hibernate/dialect quyết định.
- `attachment` dùng `byte[]` và `@Lob`, ứng với binary LOB như `BLOB`.
- `title` vẫn là chuỗi ngắn thông thường, không bị nâng thành LOB chỉ vì entity có hai trường LOB khác.

### 7.1. Cột lớn thông thường khác LOB locator

Cần phân biệt hai kiểu làm việc:

1. **Materialized LOB**: ứng dụng lấy toàn bộ nội dung dưới dạng `String` hoặc `byte[]`.
2. **LOB locator/handle**: ứng dụng làm việc với `java.sql.Blob`, `Clob` hoặc `NClob`, có thể cung cấp API stream tùy driver/database.

Ví dụ sử dụng contract JDBC:

```java
import java.sql.Blob;
import java.sql.Clob;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;

@Entity
public class ArchivedDocument {
    @Id
    private Long id;

    @Lob
    private Clob textContent;

    @Lob
    private Blob binaryContent;

    protected ArchivedDocument() {
    }
}
```

Sử dụng `Blob`/`Clob` không có nghĩa mọi driver đều stream hiệu quả hoặc cho phép truy cập không giới hạn sau khi transaction kết thúc. Locator có thể gắn với **JDBC connection hoặc transaction**; cần kiểm tra khả năng hỗ trợ của database/driver và quản lý tài nguyên rõ ràng.

### 7.2. Ví dụ đọc BLOB qua stream

Giả sử entity có trường `Blob binaryContent` và một service đang chạy trong transaction:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.Blob;
import java.sql.SQLException;

public void copyContent(ArchivedDocument document, OutputStream output)
        throws SQLException, IOException {

    Blob blob = document.getBinaryContent();
    if (blob == null) {
        return;
    }

    try (InputStream input = blob.getBinaryStream()) {
        input.transferTo(output);
    }
}
```

Đây là mã minh họa thao tác đọc `Blob`. Môi trường chạy cần duy trì Session, JDBC connection/transaction hợp lệ cho locator khi đọc. Việc `transferTo` giúp đọc theo stream ở cấp Java API, **không bảo đảm driver tránh tải toàn bộ nội dung vào bộ nhớ nội bộ**.

Ngoài ra:

- Kiểm soát kích thước, quyền truy cập và giới hạn tải xuống ở tầng API.
- Không để logic serialization response cố lấy LOB sau khi Session đã đóng.
- Nếu quản lý locator thủ công, xem contract `Blob.free()` và vòng đời tài nguyên do provider/driver yêu cầu; tránh giải phóng handle trước khi còn cần đọc.

## 8. `@Lob` không có nghĩa “tất cả cột văn bản dài đều giống nhau”

Đây là một điểm dễ gây lỗi khi đổi database. Ví dụ:

```java
@Lob
private String description;
```

Có thể dẫn tới mapping dùng semantics `CLOB`. Nhưng database đang có cột kiểu `TEXT` có thể được driver/Hibernate xử lý khác so với `CLOB`, nhất là khi một hệ quản trị triển khai LOB qua locator hoặc object identifier.

Ví dụ PostgreSQL thường dùng:

- `TEXT` hoặc `VARCHAR` để chứa văn bản.
- `BYTEA` để chứa binary value.
- Cơ chế large object riêng dựa trên object identifier (`OID`) cho những nhu cầu khác.

Do đó, khi mapping một cột `TEXT` hoặc `BYTEA` đã tồn tại trong PostgreSQL, đừng tự động gắn `@Lob` và giả định Hibernate sẽ dùng đúng cách bind JDBC của cột hiện có. Cần chọn JDBC type và dialect phù hợp, có thể dùng mapping Hibernate 6 như:

```java
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

@JdbcTypeCode(SqlTypes.LONGVARCHAR)
private String articleBody;

@JdbcTypeCode(SqlTypes.LONGVARBINARY)
private byte[] rawPayload;
```

Những annotation này gợi ý loại JDBC Hibernate nên sử dụng; **schema thực tế vẫn cần được kiểm tra** và khả năng hỗ trợ tùy dialect. Dùng `@Column(columnDefinition = "...")` để ép tên SQL có thể hữu ích khi được quản lý theo database cụ thể, nhưng không phải giải pháp độc lập cho mọi vấn đề JDBC/LOB.

### So sánh ngắn

| Nhu cầu | Java field | Hướng ánh xạ thường cân nhắc |
|---|---|---|
| Tên hoặc tiêu đề ngắn | `String` | `@Column(length = n)` |
| Văn bản dài trong cột text của DB | `String` | Loại JDBC chuỗi dài phù hợp dialect/schema |
| Văn bản theo semantics character LOB | `String` hoặc `Clob` | `@Lob`; kiểm tra driver/DB |
| Binary nhỏ, giới hạn rõ | `byte[]` | Binary/varbinary mapping |
| Binary dài trong cột binary dạng inline | `byte[]` | Mapping binary dài tương ứng |
| Binary LOB qua cơ chế BLOB | `byte[]` hoặc `Blob` | `@Lob` và kiểm tra lifecycle |
| Ảnh/video rất lớn, traffic cao | Metadata trong entity, bytes ở object storage | Cân nhắc tách payload khỏi DB |

## 9. Ví dụ entity tổng hợp nhiều kiểu dữ liệu

Giả sử một hệ thống bán hàng có catalog chứa giá, số lượng, trạng thái hoạt động, mô tả và ảnh.

```java
import java.math.BigDecimal;
import jakarta.persistence.Basic;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;

@Entity
@Table(name = "catalog_products")
public class CatalogProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private Integer availableQuantity;

    @Column(nullable = false)
    private boolean active;

    @Lob
    private String longDescription;

    @Lob
    @Basic(fetch = FetchType.LAZY)
    private byte[] thumbnail;

    protected CatalogProduct() {
    }

    public CatalogProduct(
            String name,
            BigDecimal price,
            Integer availableQuantity) {
        this.name = name;
        this.price = price;
        this.availableQuantity = availableQuantity;
        this.active = true;
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

    public Integer getAvailableQuantity() {
        return availableQuantity;
    }

    public boolean isActive() {
        return active;
    }

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }

    public void changeAvailableQuantity(int newQuantity) {
        this.availableQuantity = newQuantity;
    }
}
```

Trong ví dụ:

- `name` → chuỗi ngắn được giới hạn độ dài.
- `price` → thập phân có precision/scale rõ ràng.
- `availableQuantity` → số nguyên; logic nghiệp vụ cần kiểm tra không âm nếu đó là yêu cầu.
- `active` → boolean không nullable theo thiết kế bảng.
- `longDescription` → character LOB; chọn mapping phù hợp khi triển khai với DB cụ thể.
- `thumbnail` → binary LOB; nếu muốn nạp lazy một thuộc tính basic, cần xác nhận bytecode enhancement và truy vấn thật sự.

### Ghi xuống database

```java
import java.math.BigDecimal;
import jakarta.persistence.EntityManager;

public void addProduct(EntityManager em) {
    CatalogProduct product = new CatalogProduct(
        "Bàn phím cơ",
        new BigDecimal("1250000.00"),
        15
    );
    em.persist(product);
}
```

Đoạn mã giả định `EntityManager` đang tham gia một transaction hợp lệ do caller hoặc framework quản lý. Hibernate dùng metadata mapping của `CatalogProduct` để ràng buộc tham số JDBC phù hợp.

### Đọc danh sách nhẹ bằng DTO

Nếu danh sách chỉ cần tên, giá, số lượng và trạng thái, hãy chọn đúng trường:

```java
List<ProductCard> products = em.createQuery("""
    select new com.example.catalog.ProductCard(
        p.id, p.name, p.price, p.availableQuantity, p.active
    )
    from CatalogProduct p
    where p.active = true
    order by p.name
    """, ProductCard.class)
    .getResultList();
```

Ví dụ giả định `ProductCard` là DTO có constructor đúng thứ tự và kiểu dữ liệu. Cách query này tránh cố ý lấy hai thuộc tính LOB cho màn hình danh sách.

**Lưu ý:** chú thích `@Basic(fetch = LAZY)` trên `thumbnail` vẫn có thể hữu ích khi cấu hình hỗ trợ, nhưng projection là cách trực tiếp để kiểm soát các cột được yêu cầu trong use case trên.

## 10. Schema thực tế và ảnh hưởng của Hibernate Dialect

Khi Hibernate giao tiếp với database, **dialect** giúp chọn cú pháp SQL và kiểu cột được hệ quản trị hỗ trợ. Chẳng hạn, cùng một `Boolean` có thể ánh xạ sang kiểu boolean bản địa của DB A nhưng dạng bit/số trên DB B.

Minh họa khái niệm, không phải DDL dùng chung cho tất cả hệ quản trị:

```sql
CREATE TABLE catalog_products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    price DECIMAL(18, 2) NOT NULL,
    available_quantity INTEGER NOT NULL,
    active BOOLEAN NOT NULL,
    long_description CLOB,
    thumbnail BLOB
);
```

DDL này chỉ mô tả **ý nghĩa cột**. Không nên chạy nguyên văn trên mọi database: tên kiểu `BOOLEAN`, `CLOB`, `BLOB`, cú pháp identity và đặc điểm storage khác nhau. Trong dự án thật, schema phải được xác định theo hệ quản trị/phiên bản đang triển khai.

### Không nên xem auto-DDL là nguồn sự thật duy nhất

Cấu hình tự tạo/cập nhật schema của Hibernate hữu ích trong môi trường thử nghiệm và học tập. Với hệ thống có dữ liệu thật:

1. Thiết kế schema và ràng buộc theo database đã chọn.
2. Quản lý thay đổi bằng migration (ví dụ Flyway/Liquibase).
3. Giữ ánh xạ entity đồng bộ với migration.
4. Kiểm tra trên đúng DB/driver vì H2 hoặc database nhúng có thể không biểu hiện giống PostgreSQL/Oracle/SQL Server.
5. Khi đổi `String` sang `@Lob String` hay `byte[]` sang `@Lob byte[]`, đánh giá **chuyển đổi dữ liệu và JDBC binding**, không chỉ đổi annotation.

Giá trị như `length`, `precision` và `scale` nên xuất phát từ miền dữ liệu và thực tế database, thay vì lấy một giá trị lớn tùy ý để tránh lỗi trong ngắn hạn.

## 11. Cách Hibernate xử lý `null`, default và dữ liệu rỗng

Các kiểu dữ liệu có ý nghĩa đặc biệt khi chưa có giá trị:

| Giá trị Java | Biểu diễn/ý nghĩa cần cân nhắc |
|---|---|
| `null` ở `String` | Thông thường là SQL `NULL`; khác chuỗi rỗng |
| `""` | Chuỗi rỗng, nhưng một số DB có semantics riêng đối với chuỗi rỗng |
| `null` ở `Integer` | Chưa có số liệu, nếu schema cho phép |
| `0` | Số 0 thực sự, không đồng nghĩa chưa biết |
| `null` ở `Boolean` | Trạng thái chưa biết/chưa xác định nếu domain cho phép |
| `false` ở `boolean` | Giá trị boolean xác định là false |
| `null` ở `byte[]` | Không có payload; thường khác mảng rỗng |
| `new byte[0]` | Payload có độ dài bằng 0 |

Đặc biệt, **SQL `NULL` khác Java `null` ở cách được sử dụng trong biểu thức truy vấn**. Ví dụ `where p.description = null` là biểu thức không đúng ý trong SQL chuẩn; dùng `IS NULL` hoặc JPQL `is null`.

`@Column(nullable = false)` thể hiện yêu cầu mapping và hỗ trợ constraint trong schema. Nếu entity mới có trường bắt buộc chưa điền, việc ghi có thể thất bại ở Hibernate hoặc database; nên có validation hợp lý trước đó.

Ngoài ra, **SQL default** như `DEFAULT 0` không đương nhiên được áp dụng khi Hibernate gửi một giá trị tường minh, kể cả `NULL`. Muốn sử dụng default do database sinh, cần một chiến lược mapping/insert phù hợp, không chỉ thêm default ở DDL rồi mong Hibernate luôn bỏ qua cột ấy.

## 12. Vấn đề hiệu năng khi lưu văn bản và binary lớn

Không phải tất cả dữ liệu cần nằm trong cùng một entity được truy vấn thường xuyên.

### 12.1. Tải thừa payload

Một entity chứa `byte[] attachment` lớn có thể gây:

- Tăng heap và áp lực garbage collector nếu tải toàn bộ byte array.
- Tăng băng thông JDBC/network.
- Query danh sách chậm dù giao diện chỉ hiển thị tên và kích thước.
- Khó kiểm soát việc serializer vô tình xuất nội dung nhị phân.

Các cách giảm chi phí:

- Tách metadata và payload thành hai bảng/entity có ranh giới truy cập rõ ràng.
- Dùng DTO projection cho truy vấn list.
- Sử dụng fetch/lazy thích hợp và kiểm tra SQL thật.
- Stream dữ liệu khi driver/database hỗ trợ đúng.
- Giới hạn kích thước upload và tránh giữ nhiều payload cùng lúc trong heap.

### 12.2. Có nên lưu file trong database?

Không có lựa chọn đúng cho mọi hệ thống.

| Lưu trong database (BLOB/LOB) | Lưu ngoài database (object storage hoặc file service) |
|---|---|
| Có thể gắn cập nhật metadata và dữ liệu vào cùng transaction DB theo thiết kế | Dễ phục vụ nội dung lớn qua hệ thống chuyên biệt |
| Hưởng cơ chế backup, quyền và replication của DB | Giảm tải và dung lượng database cho file lớn |
| Quản lý bằng công cụ DB quen thuộc | Cần xử lý tính nhất quán giữa metadata DB và file/object riêng |
| Backup/restore và replication DB có thể nặng khi chứa nhiều file | Cần chính sách quản lý vòng đời, phân quyền, xóa file mồ côi |

Nếu lưu bên ngoài, entity có thể giữ `storageKey`, `contentType`, `sizeBytes`, `checksum` và trạng thái xử lý. Ứng dụng phải tính tới trường hợp database đã commit nhưng upload file thất bại, hoặc ngược lại, vì transaction database thông thường không bao phủ object storage.

### 12.3. Index và tìm kiếm

Index trên cột ngắn như mã sản phẩm hoặc giá có ý nghĩa khác với tìm kiếm toàn văn trên một `CLOB` lớn. Database thường không cho tạo index B-tree thông thường trên mọi loại LOB, hoặc có giới hạn riêng.

Với yêu cầu tìm kiếm nội dung dài, có thể cân nhắc:

- Full-text index của database;
- Cột tìm kiếm/projection được tối ưu;
- Hệ thống search chuyên dụng khi quy mô và tính năng yêu cầu.

Không nên chọn `CLOB` chỉ để né giới hạn `VARCHAR` rồi kỳ vọng nó hỗ trợ truy vấn, sort và index giống hệt mọi loại chuỗi thông thường.

## 13. Các lỗi thường gặp khi ánh xạ kiểu cơ bản

### 13.1. Chuỗi dài hơn giới hạn cột

**Triệu chứng:** lỗi khi insert/update giá trị chuỗi dài.

**Nguyên nhân:** `String` Java có thể chứa giá trị dài hơn `VARCHAR(n)` đã khai báo; annotation/schema/validation không đồng bộ.

**Hướng xử lý:** xác định độ dài hợp lệ theo nghiệp vụ, đồng bộ `@Column` và migration; validation phía ứng dụng không thay thế constraint DB.

### 13.2. Mất chữ số thập phân hoặc giá tiền sai

**Triệu chứng:** giá trị sau khi đọc khác số được tính trong ứng dụng.

**Nguyên nhân có thể:** lưu giá bằng `double`, scale của cột nhỏ, database làm tròn hoặc ứng dụng sử dụng rounding mode không thống nhất.

**Hướng xử lý:** `BigDecimal` với precision/scale rõ ràng; xác định chính sách rounding và kiểm tra ràng buộc thực tế.

### 13.3. Boolean dữ liệu legacy đọc sai

**Triệu chứng:** cột `Y/N` nhưng entity được khai báo `Boolean` thuần và không có mapping phù hợp.

**Hướng xử lý:** dùng converter chuẩn/tính năng được Hibernate hỗ trợ, định nghĩa rõ cả ba trường hợp `Y`, `N`, `NULL` và xử lý giá trị ngoài miền.

### 13.4. `BLOB`/`CLOB` không khớp cột `BYTEA`/`TEXT`

**Triệu chứng:** lỗi bind JDBC, lỗi đọc stream hoặc thông báo không thể chuyển đổi giữa LOB locator và kiểu cột hiện có.

**Nguyên nhân:** nhầm `@Lob` với “cột dài” bất kể semantics của database, hoặc chọn mapping theo ví dụ của DB khác.

**Hướng xử lý:** đối chiếu schema vật lý, Hibernate dialect và kiểu JDBC; chọn loại JDBC hoặc API tương thích với DB đang dùng. Đối với PostgreSQL, đặc biệt phân biệt cột `BYTEA` và large-object `OID` khi xét binary LOB.

### 13.5. Lỗi truy cập LOB sau khi Session/transaction đã đóng

**Triệu chứng:** lỗi khi gọi `blob.getBinaryStream()` hoặc truy cập trường lazy ngoài transaction.

**Nguyên nhân:** JDBC locator, persistence context hoặc connection cần thiết đã hết vòng đời.

**Hướng xử lý:** xác định thời điểm cần đọc và stream nội dung khi tài nguyên hợp lệ; không để entity chứa handle bị giữ lâu rồi truy cập ở tầng presentation.

### 13.6. Áp lực bộ nhớ khi đọc nhiều file

**Triệu chứng:** heap tăng nhanh hoặc chậm khi tải danh sách entity có payload lớn.

**Nguyên nhân:** materialize dữ liệu binary thành `byte[]`/chuỗi dài, hoặc nạp LOB eager.

**Hướng xử lý:** tách list/detail, projection DTO, phân trang, streaming có kiểm soát, giới hạn dữ liệu và cân nhắc storage phù hợp.

## 14. Cách chọn kiểu dữ liệu theo nhu cầu thực tế

Một quy trình có thể áp dụng cho từng thuộc tính:

1. **Xác định ý nghĩa miền dữ liệu.** Đây là tên, số lượng, tiền, trạng thái, file hay nội dung văn bản?
2. **Chọn kiểu Java thể hiện đúng semantics.** Ví dụ số tiền dùng `BigDecimal`; số điện thoại dùng `String`; dữ liệu nhị phân thường dùng `byte[]`.
3. **Xác định nullable, độ dài và miền giá trị.** Với số thập phân, nêu rõ precision/scale và rounding.
4. **Chọn loại cột SQL từ DB mục tiêu.** Chú ý Unicode/collation, giới hạn độ dài, binary/LOB và khả năng tạo index.
5. **Chọn mapping Hibernate/Jakarta Persistence.** Bắt đầu từ ánh xạ cơ bản; thêm `@Column`, converter hoặc ánh xạ kiểu chuyên biệt khi có lý do.
6. **Thiết kế đường truy vấn.** Tránh tải LOB nếu use case chỉ cần metadata; với payload lớn, xác định cách streaming và ownership tài nguyên.
7. **Quản lý schema bằng migration và kiểm chứng trên DB thật.** Việc Hibernate sinh SQL thành công trên một DB không đủ để kết luận mapping sẽ giống ở mọi nơi.

## 15. Ghi nhớ

- Hibernate ánh xạ giữa **kiểu Java, kiểu JDBC và kiểu cột SQL**; ba lớp này liên quan nhưng không đồng nhất.
- `String` thường dùng cho chuỗi ngắn; `length` mô tả giới hạn cột, còn encoding và collation do database quyết định.
- `Integer`/`Long` phù hợp số nguyên; `BigDecimal` phù hợp thập phân cần chính xác. `float`/`double` là số gần đúng.
- `boolean` luôn có true/false; `Boolean` còn có thể null. Với `Y/N` hoặc `1/0` legacy, cần mapping phù hợp.
- `byte[]` phù hợp bytes vật lý; kích thước dữ liệu quyết định có nên dùng cột binary thông thường, LOB hay storage riêng.
- `@Lob` mô tả **semantics của large object**, không phải cách viết trung lập cho mọi cột `TEXT` hoặc `BYTEA`.
- `Blob`/`Clob` có thể liên quan locator và transaction; `String`/`byte[]` là dữ liệu materialized và có chi phí heap tương ứng.
- `@Basic(fetch = LAZY)` trên basic/LOB cần điều kiện hỗ trợ và kiểm tra truy vấn; projection giúp chọn cột theo nhu cầu rõ ràng hơn.
- Mapping đúng cần đồng bộ với schema thực tế, JDBC driver, dialect, migration và các ràng buộc nghiệp vụ.

Nắm vững các nhóm kiểu dữ liệu này giúp tránh những lỗi tưởng nhỏ nhưng có tác động lớn: mất độ chính xác tiền tệ, lỗi Unicode, xử lý sai trạng thái `NULL`, ánh xạ LOB không tương thích hoặc tải payload quá lớn. Hibernate giảm công việc chuyển đổi dữ liệu, nhưng **lựa chọn kiểu và thiết kế lưu trữ vẫn là trách nhiệm của ứng dụng**.
