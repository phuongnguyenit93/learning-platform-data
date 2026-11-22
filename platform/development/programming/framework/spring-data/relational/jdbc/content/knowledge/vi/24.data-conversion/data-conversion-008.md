# Giới hạn một thuộc tính–một giá trị và dữ liệu nhiều cột

Trong **Spring Data Relational JDBC (Spring Data JDBC)**, mapping thông thường xem mỗi property được lưu như một giá trị cột. Khi một kiểu domain tùy chỉnh cần được lưu vào một cột, ta có thể đăng ký converter để chuyển kiểu đó sang kiểu JDBC đơn giản như `String`, `Long`, `BigDecimal` hoặc kiểu tương ứng của database.

Giới hạn quan trọng là một converter thông thường chuyển **một giá trị nguồn thành một giá trị đích**. Nó không tự tách một property thành nhiều cột vật lý. Nếu một value object như `Money` có cả số tiền và đơn vị tiền tệ, nhưng cần lưu thành hai cột riêng để truy vấn và ràng buộc dữ liệu, hãy dùng `@Embedded`. Spring Data JDBC trải phẳng các property bên trong object vào cùng bảng với aggregate root.

Bài học này phân biệt ba mô hình:

- **Một property – một cột:** custom converter chuyển một kiểu domain thành một giá trị database.
- **Một value object – nhiều cột:** `@Embedded` ánh xạ các property con thành nhiều cột trong cùng bảng.
- **Dữ liệu qua nhiều bảng:** dùng quan hệ aggregate hoặc truy vấn đọc/DTO; converter không thay thế JOIN hay mapping aggregate.

## 1. Mapping mặc định và giới hạn của converter

Giả sử entity `Product` có property `productCode` với kiểu domain riêng:

~~~java
public record ProductCode(String value) {}
~~~

Database chỉ cần lưu nội dung mã sản phẩm trong một cột `product_code`. Converter có thể chuyển `ProductCode` thành `String` khi ghi và chuyển `String` trở lại `ProductCode` khi đọc.

~~~mermaid
flowchart LR
    Domain["ProductCode<br/>một property"]
    Write["Writing Converter"]
    Column[("product_code<br/>một cột")]
    Read["Reading Converter"]
    Loaded["ProductCode<br/>một property"]
    Domain --> Write --> Column --> Read --> Loaded
~~~

Đây là trường hợp phù hợp với custom conversion: một giá trị domain có một biểu diễn database duy nhất.

Ngược lại, nếu property `price` có kiểu `Money` gồm `amount` và `currencyCode`, một converter `Money -> BigDecimal` chỉ có thể trả về một giá trị `BigDecimal`. Nó không tự tạo thêm cột `currency_code`. Nếu converter trả về chuỗi như `"125000.00|VND"`, database vẫn chỉ nhận **một giá trị trong một cột**.

| Domain property | Biểu diễn | Cột vật lý |
|---|---|---|
| `ProductCode("BK-01")` | `String("BK-01")` | `product_code` |
| `Money(125000, "VND")` qua converter sang chuỗi | `"125000.00|VND"` | `price` |
| `Money(125000, "VND")` qua `@Embedded` | Hai property con | `price_amount`, `price_currency_code` |

Không nên kỳ vọng một converter thông thường trả về object có nhiều field rồi framework tự phân rã object đó thành nhiều cột. Việc phân rã thành nhiều cột là trách nhiệm của mapping metadata, chẳng hạn `@Embedded`.

## 2. Khi nào nên dùng custom converter cho một cột?

Converter phù hợp khi kiểu domain là một giá trị logic và có thể biểu diễn gọn bằng một kiểu database:

- Mã định danh có định dạng riêng như `ProductCode`, `CustomerNumber`.
- Một trạng thái domain có biểu diễn scalar như `String` hoặc số.
- Một giá trị đo lường đã có quy ước đơn vị cố định.
- Một kiểu wrapper để bảo vệ miền giá trị, ví dụ `EmailAddress` hoặc `PostalCode`.

Ví dụ `ProductCode` có validation:

~~~java
package com.example.inventory;

public record ProductCode(String value) {

    public ProductCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Product code must not be blank"
            );
        }
        if (value.length() > 40) {
            throw new IllegalArgumentException(
                "Product code is too long"
            );
        }
    }
}
~~~

Kiểu domain giữ quy tắc hợp lệ ở một nơi. Database lưu giá trị scalar trong cột `VARCHAR`.

## 3. Viết Reading Converter và Writing Converter

Spring Data dùng converter theo hai hướng:

- **Writing converter:** chuyển kiểu domain sang kiểu có thể ghi xuống database.
- **Reading converter:** chuyển kiểu database đọc được thành kiểu domain.

Với `ProductCode`, hai converter có thể viết như sau:

~~~java
package com.example.inventory;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class ProductCodeWritingConverter
        implements Converter<ProductCode, String> {

    @Override
    public String convert(ProductCode source) {
        return source.value();
    }
}

@ReadingConverter
public class ProductCodeReadingConverter
        implements Converter<String, ProductCode> {

    @Override
    public ProductCode convert(String source) {
        return new ProductCode(source);
    }
}
~~~

Annotation `@WritingConverter` và `@ReadingConverter` làm rõ chiều chuyển đổi. Điều này đặc biệt hữu ích khi cả source type và target type đều là kiểu đơn giản, ví dụ `String`, `Long` hoặc `BigDecimal`.

### Đăng ký converter

Trong cấu hình Spring Data JDBC, có thể đăng ký converter bằng cách mở rộng `AbstractJdbcConfiguration`:

~~~java
package com.example.config;

import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

import com.example.inventory.ProductCodeReadingConverter;
import com.example.inventory.ProductCodeWritingConverter;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new ProductCodeReadingConverter(),
            new ProductCodeWritingConverter()
        );
    }
}
~~~

Phương thức cấu hình converter có thể khác giữa các thế hệ Spring Data; hãy dùng API tương ứng với phiên bản mà dự án quản lý. Không tự tạo một `ConversionService` riêng rồi giả định Spring Data JDBC sẽ tự sử dụng nó.

### Dùng kiểu domain trong entity

~~~java
package com.example.inventory;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;

    @Column("product_code")
    private ProductCode productCode;

    protected Product() {
    }

    public Product(String name, ProductCode productCode) {
        this.name = name;
        this.productCode = productCode;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public ProductCode getProductCode() {
        return productCode;
    }
}
~~~

Schema tương ứng:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    product_code VARCHAR(40) NOT NULL UNIQUE
);
~~~

Khi lưu `Product`, writing converter chuyển `ProductCode` thành chuỗi để ghi vào `product_code`. Khi đọc, reading converter dựng lại `ProductCode` từ chuỗi trong cột. Dữ liệu vẫn chiếm một cột và có thể được tìm kiếm/index bằng SQL như một giá trị chuỗi.

## 4. Một converter không tự ánh xạ một property thành nhiều cột

Xét value object:

~~~java
public record Money(
    BigDecimal amount,
    String currencyCode
) {}
~~~

Có hai thành phần dữ liệu độc lập:

- `amount`: giá trị số tiền.
- `currencyCode`: mã tiền tệ như `VND`, `USD` hoặc `EUR`.

Nếu đăng ký converter:

~~~java
Converter<Money, String>
~~~

thì đích của converter là một `String`. Spring Data JDBC lưu kết quả vào một cột được mapping cho property đó. Converter không có hợp đồng trả về “hai cột”, và không thể tự yêu cầu framework tạo cả `price_amount` lẫn `price_currency_code`.

Có thể serialize `Money` thành JSON hoặc chuỗi có định dạng để lưu trong một cột, nhưng đó là **một cột chứa một giá trị tổng hợp**. Cách này khác với lưu amount và currency ở hai cột độc lập.

### Vì sao không nên nhét nhiều giá trị vào một chuỗi nếu cần truy vấn?

Giả sử lưu:

~~~text
125000.00|VND
~~~

Database không còn thấy amount và currency như hai thuộc tính riêng. Muốn lọc theo amount, kiểm tra currency hoặc tạo index cho từng phần, ứng dụng phải dùng hàm tách chuỗi/JSON hoặc xử lý ở tầng khác. Việc đó làm truy vấn phức tạp và có thể hạn chế khả năng tận dụng index cùng constraint.

Nếu nghiệp vụ cần:

- Lọc tất cả sản phẩm có giá lớn hơn một ngưỡng.
- Nhóm báo cáo theo currency.
- Kiểm tra amount không âm.
- Tạo index riêng cho amount hoặc currency.

thì hai cột riêng thường thể hiện schema rõ hơn.

## 5. Dùng @Embedded cho value object nhiều cột

`@Embedded` cho phép nhúng các property của một object vào cùng bảng với entity chứa nó. Một property Java như `price` có thể được trải phẳng thành nhiều cột dựa trên các property con.

### Value object Money

~~~java
package com.example.inventory;

import java.math.BigDecimal;

public class Money {

    private BigDecimal amount;
    private String currencyCode;

    protected Money() {
        // Dành cho Spring Data JDBC.
    }

    public Money(BigDecimal amount, String currencyCode) {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Amount must be non-negative"
            );
        }
        if (currencyCode == null ||
                !currencyCode.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Currency code must contain three uppercase letters"
            );
        }
        this.amount = amount;
        this.currencyCode = currencyCode;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrencyCode() {
        return currencyCode;
    }
}
~~~

### Entity Product nhúng Money

~~~java
package com.example.inventory;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("products")
public class Product {

    @Id
    private Long id;

    private String name;

    @Embedded(
        prefix = "price_",
        onEmpty = Embedded.OnEmpty.USE_NULL
    )
    private Money price;

    protected Product() {
    }

    public Product(String name, Money price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Money getPrice() {
        return price;
    }
}
~~~

Với prefix `price_`, các property con được ánh xạ:

| Property Java | Cột SQL |
|---|---|
| `name` | `name` |
| `price.amount` | `price_amount` |
| `price.currencyCode` | `price_currency_code` |

Một property `price` trong entity trở thành hai cột vật lý. Đây là mapping nhiều cột mà `@Embedded` cung cấp.

### Schema SQL

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    price_amount NUMERIC(14, 2),
    price_currency_code VARCHAR(3)
);
~~~

Hai cột price cho phép NULL trong ví dụ vì `price` có thể không tồn tại. Nếu mọi sản phẩm bắt buộc phải có giá, hãy đặt cột `NOT NULL` và bảo đảm entity luôn có `Money` hợp lệ. Ràng buộc schema phải thống nhất với chính sách null của mapping.

### Dữ liệu minh họa

~~~sql
INSERT INTO products (
    name,
    price_amount,
    price_currency_code
) VALUES
    ('Keyboard', 1250000.00, 'VND'),
    ('Notebook', 4.50, 'USD'),
    ('Sample item', NULL, NULL);
~~~

Khi đọc:

- Keyboard có `Money(1250000.00, "VND")`.
- Notebook có `Money(4.50, "USD")`.
- Sample item có `price == null` vì cả nhóm cột embedded đều NULL và dùng `USE_NULL`.

## 6. Prefix giúp tránh trùng tên cột

Một entity có thể nhúng nhiều object cùng kiểu. Ví dụ sản phẩm có giá bán và giá vốn, cả hai đều dùng kiểu `Money`:

~~~java
@Embedded(
    prefix = "selling_",
    onEmpty = Embedded.OnEmpty.USE_NULL
)
private Money sellingPrice;

@Embedded(
    prefix = "cost_",
    onEmpty = Embedded.OnEmpty.USE_NULL
)
private Money costPrice;
~~~

Các cột được tạo theo prefix:

| Property | Cột amount | Cột currency |
|---|---|---|
| `sellingPrice` | `selling_amount` | `selling_currency_code` |
| `costPrice` | `cost_amount` | `cost_currency_code` |

Tên cột cuối cùng còn phụ thuộc naming strategy và cấu hình mapping của ứng dụng; khi cần schema tường minh, có thể khai báo tên cột trên property con bằng `@Column`. Điều quan trọng là hai embedded property phải có nhóm cột không xung đột.

Prefix có tác dụng ở tầng mapping và schema. Nó không tạo quan hệ hoặc bảng mới.

## 7. Xử lý object null, object rỗng và null một phần

Khi dùng `@Embedded`, Spring Data JDBC cần quyết định khi nào nhóm cột null có nghĩa object không tồn tại. `onEmpty` điều khiển quyết định này:

| Cấu hình | Tất cả cột embedded là SQL NULL | Kết quả |
|---|---|---|
| `USE_NULL` | Có | Property embedded là Java `null` |
| `USE_EMPTY` | Có | Framework tạo instance với các property bên trong null/default |
| Cả hai | Có ít nhất một cột khác NULL | Framework dựng object và ánh xạ từng property |

Ví dụ với `Money`:

| `price_amount` | `price_currency_code` | `USE_NULL` |
|---:|---|---|
| NULL | NULL | `price == null` |
| 125000 | VND | `price` có cả hai giá trị |
| 125000 | NULL | `price` tồn tại, `currencyCode == null` |
| NULL | USD | `price` tồn tại, `amount == null` |

Trạng thái null một phần không tự biến toàn bộ object thành null. Nếu domain yêu cầu amount và currency luôn đi cùng nhau, cần validation và constraint database để cấm trạng thái một phần.

Ví dụ constraint PostgreSQL:

~~~sql
ALTER TABLE products
ADD CONSTRAINT ck_product_price_pair
CHECK (
    (price_amount IS NULL AND price_currency_code IS NULL)
    OR
    (price_amount IS NOT NULL AND price_currency_code IS NOT NULL)
);
~~~

Constraint cho phép giá hoàn toàn vắng mặt hoặc đầy đủ cả hai thành phần. Nó ngăn dữ liệu nửa chừng có thể tạo ra `Money` không hợp lệ.

Nếu dùng `USE_EMPTY`, class embedded phải có thể được khởi tạo ở trạng thái rỗng theo mapping. Đừng dựa vào `USE_EMPTY` để tự sinh giá trị mặc định nghiệp vụ; annotation chỉ quyết định có tạo object khi toàn bộ cột null hay không.

## 8. Khi nào dùng converter, khi nào dùng @Embedded?

Chọn theo hình dạng dữ liệu cần lưu:

| Nhu cầu | Giải pháp | Số cột |
|---|---|---:|
| `ProductCode` chỉ có một giá trị mã | Reading/Writing Converter | 1 |
| `EmailAddress` được chuẩn hóa thành một chuỗi | Converter | 1 |
| `Money` cần amount và currency truy vấn độc lập | `@Embedded` | 2 |
| `Address` cần street, city, postal code | `@Embedded` | Nhiều cột |
| Một object cần lưu nguyên JSON | Converter/JSON mapping theo database | 1 |
| Order có nhiều OrderItem | `@MappedCollection` | Bảng con riêng |
| Order tham chiếu Customer aggregate khác | ID hoặc `AggregateReference` | FK scalar |
| Báo cáo JOIN nhiều bảng thành DTO | Spring JDBC `RowMapper`/`ResultSetExtractor` | Result set nhiều cột |

### Converter

Dùng khi toàn bộ property có một biểu diễn database duy nhất. Ví dụ mã bưu chính, mã sản phẩm, enum có format riêng.

### @Embedded

Dùng khi object là value object thuộc entity/aggregate chứa nó và các thành phần cần lưu thành nhiều cột trong cùng bảng. Object không có identity hoặc vòng đời độc lập.

### Quan hệ aggregate

Nếu object có identity, vòng đời hoặc repository riêng, hãy xem xét mô hình aggregate/quan hệ phù hợp. Không nhúng một entity độc lập chỉ để tránh tạo bảng.

### DTO và RowMapper

Nếu nhiều cột đến từ JOIN hoặc phép tính báo cáo, đó thường là read model. Dùng query tùy chỉnh và mapper thay vì cố chuyển result set thành một value object đơn bằng converter.

## 9. JSON trong một cột vẫn là một giá trị

Đôi khi object nhiều field được lưu dưới dạng JSON:

~~~json
{
  "amount": 125000,
  "currencyCode": "VND"
}
~~~

Nếu converter serialize object thành JSON text, database lưu toàn bộ nội dung trong một cột như `price_json`. Cách này hữu ích khi:

- Cấu trúc object thay đổi thường xuyên.
- Ứng dụng thường đọc/ghi toàn bộ object cùng nhau.
- Database hỗ trợ kiểu JSON và truy vấn JSON phù hợp.
- Không cần ràng buộc quan hệ ở từng thành phần.

Nhưng JSON một cột khác với hai cột `price_amount` và `price_currency_code`:

| Tiêu chí | JSON trong một cột | Embedded nhiều cột |
|---|---|---|
| Lưu trữ | Một cột JSON/text | Nhiều cột có kiểu riêng |
| Lọc theo amount | Cần toán tử JSON hoặc trích xuất | SQL so sánh trực tiếp |
| Constraint từng thành phần | Thường phức tạp hơn | Có thể dùng NOT NULL/CHECK |
| Index riêng từng thuộc tính | Phụ thuộc hỗ trợ JSON/index của DB | Index cột thông thường |
| Thay đổi cấu trúc | Linh hoạt | Cần migration schema |
| Kiểu dữ liệu ở database | Thường là JSON/JSONB hoặc text | NUMERIC, VARCHAR, DATE... |

Không chọn JSON chỉ vì converter dễ viết. Hãy dựa vào cách ứng dụng truy vấn, kiểm tra và cập nhật các thành phần.

## 10. JdbcValue vẫn đại diện cho một giá trị JDBC

Trong một số trường hợp, writing converter cần chỉ rõ JDBC type được sử dụng khi bind giá trị. Spring Data JDBC cung cấp `JdbcValue` để mang giá trị cùng kiểu JDBC tương ứng.

Ví dụ về ý tưởng:

~~~java
@WritingConverter
public class ProductCodeToJdbcValueConverter
        implements Converter<ProductCode, JdbcValue> {

    @Override
    public JdbcValue convert(ProductCode source) {
        return JdbcValue.of(
            source.value(),
            JDBCType.VARCHAR
        );
    }
}
~~~

`JdbcValue` giúp chỉ rõ cách một giá trị được bind xuống JDBC, chẳng hạn `VARCHAR`, `BIGINT` hoặc `TIMESTAMP`. Nó **không phải container để trả về nhiều cột**. Một `JdbcValue` vẫn mô tả một giá trị cho một vị trí cột trong thao tác ghi.

Tên package và API cụ thể của `JdbcValue` phụ thuộc phiên bản Spring Data JDBC. Chỉ dùng cơ chế này khi cần điều khiển JDBC type; nếu converter sang kiểu Java đơn giản đã hoạt động đúng, không cần thêm lớp trung gian.

## 11. Giới hạn của một property trải trên nhiều cột

Khi dùng `@Embedded`, một property Java có nhiều property con, và mỗi property con được ánh xạ riêng. Tuy nhiên, đây không phải cách tùy ý ánh xạ một property sang bất kỳ nhóm cột nào:

- Các property con phải được Spring Data Relational nhận diện và mapping.
- Prefix/column mapping phải tạo tên cột không xung đột.
- Embedded object thuộc bảng của entity chứa nó.
- Embedded object không có khóa chính riêng.
- Embedded object không có repository độc lập.
- Không thể dùng `@Embedded` để JOIN nhiều bảng hoặc gọi một converter rồi tự động phân rã kết quả thành nhiều cột.

Nếu object có cấu trúc lồng nhau, có thể nhúng tiếp value object bên trong theo mapping phù hợp. Khi đó cần quản lý prefix ở từng cấp và hiểu quy tắc null của mỗi embedded property.

Nếu một phần dữ liệu cần nằm ở bảng khác vì có nhiều hàng hoặc quan hệ riêng, hãy dùng `@MappedCollection` cho thành phần con thuộc aggregate hoặc ID reference cho aggregate khác. Không dùng embedded mapping để thay thế quan hệ bảng.

## 12. Thay đổi schema khi chuyển từ một cột sang nhiều cột

Giả sử phiên bản đầu lưu `Money` trong một cột chuỗi:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    price_value VARCHAR(80)
);
~~~

Sau đó muốn truy vấn amount và currency độc lập, schema mới có:

~~~sql
ALTER TABLE products
ADD COLUMN price_amount NUMERIC(14, 2),
ADD COLUMN price_currency_code VARCHAR(3);
~~~

Quá trình chuyển đổi dữ liệu cần có migration:

1. Thêm các cột mới ở trạng thái nullable.
2. Chuyển dữ liệu cũ từ `price_value` sang amount và currency theo format đã lưu.
3. Kiểm tra các hàng lỗi/không parse được.
4. Đối chiếu số lượng hàng và giá trị sau migration.
5. Cập nhật entity sang `@Embedded`.
6. Chuyển các query, index và constraint sang cột mới.
7. Chỉ xóa cột cũ sau khi mọi phiên bản ứng dụng và job liên quan đã ngừng sử dụng nó.

Không parse chuỗi cũ bằng cách giả định delimiter luôn xuất hiện đúng một lần hoặc dữ liệu luôn hợp lệ. Migration phải xử lý dữ liệu lịch sử thực tế và có cách phát hiện bản ghi không chuyển đổi được.

## 13. Query và index với dữ liệu nhiều cột

Ưu điểm của `@Embedded` là mỗi thành phần có thể được truy vấn như cột bình thường:

~~~sql
SELECT id, name, price_amount, price_currency_code
FROM products
WHERE price_currency_code = 'VND'
  AND price_amount >= 1000000
ORDER BY price_amount DESC, id DESC;
~~~

Có thể tạo index theo workload:

~~~sql
CREATE INDEX idx_products_currency_amount
    ON products(price_currency_code, price_amount);
~~~

Index ghép có thể hỗ trợ truy vấn lọc theo currency rồi so sánh amount. Thứ tự cột index cần căn cứ vào điều kiện lọc và execution plan. Không phải mọi tổ hợp đều cần index.

Với converter lưu chuỗi ghép, truy vấn tương đương thường phải parse chuỗi hoặc dùng hàm đặc thù của database. Điều này phức tạp hơn và có thể làm giảm khả năng sử dụng index thông thường.

## 14. Validation domain và constraint database

Mapping nhiều cột không tự bảo đảm value object hợp lệ. Ví dụ `Money` có thể bị đọc thành object với amount có giá trị nhưng currency null nếu database chứa dữ liệu một phần.

Nên xác định quy tắc ở cả hai tầng:

- **Domain validation:** constructor/factory kiểm tra amount không âm, currency có mã hợp lệ và các thành phần bắt buộc đi cùng nhau.
- **Database constraint:** CHECK/NOT NULL/foreign key bảo vệ dữ liệu kể cả khi có writer khác ứng dụng.
- **Migration:** sửa hoặc từ chối dữ liệu lịch sử không đáp ứng quy tắc mới.
- **Read mapping:** xử lý có chủ đích với dữ liệu cũ/null thay vì giả định mọi hàng đều hoàn hảo.

Nếu schema cho phép một value object vắng mặt, các cột có thể cùng null. Nếu object tồn tại, có thể bắt buộc các cột con đều có giá trị. CHECK constraint có thể thể hiện quy tắc “tất cả null hoặc tất cả non-null”.

## 15. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Mong converter trả về nhiều cột | Mapping không tự tách object thành các cột | Dùng `@Embedded` cho value object nhiều property |
| Converter `Money -> String` nhưng cần lọc amount/currency | Phải parse chuỗi hoặc dùng hàm DB | Lưu amount và currency ở hai cột |
| Dùng `@Embedded` cho entity có identity riêng | Mờ ranh giới aggregate và vòng đời | Dùng aggregate/table relation phù hợp |
| Quên prefix khi nhúng cùng kiểu nhiều lần | Trùng tên cột | Đặt prefix riêng cho từng embedded property |
| Nghĩ prefix tạo bảng mới | Schema và mapping sai | Embedded flatten vào bảng chứa |
| Dùng `USE_NULL` nhưng dữ liệu partial-null | Object vẫn được tạo với property con null | Validate và dùng CHECK constraint nếu cần |
| Dùng primitive cho cột embedded nullable | Không biểu diễn được SQL NULL | Dùng wrapper/reference type |
| Dùng `USE_EMPTY` như giá trị mặc định nghiệp vụ | Object rỗng bị hiểu nhầm là dữ liệu hợp lệ | Đặt factory/default rõ ràng hoặc dùng `USE_NULL` |
| Ghi JSON vì dễ serialize nhưng thường xuyên lọc từng field | Truy vấn/index phức tạp | Cân nhắc embedded columns |
| Nghĩ `JdbcValue` chứa được nhiều cột | Nhầm JDBC value với row/object mapping | Dùng nó để chỉ rõ một JDBC value/type |
| Dùng converter để dựng DTO từ JOIN | Không có mapping nhiều hàng/nhiều bảng | Dùng RowMapper/ResultSetExtractor |
| Chuyển schema nhưng không migrate dữ liệu cũ | Dữ liệu bị mất hoặc không đọc được | Thực hiện migration có đối chiếu |

## 16. Bài thực hành

1. Tạo `ProductCode` dưới dạng record và hai converter đọc/ghi với `String`.
2. Đăng ký converter trong cấu hình Spring Data JDBC; lưu và đọc lại Product để xác nhận property được dựng thành `ProductCode`.
3. Tạo value object `Money` gồm `BigDecimal amount` và `String currencyCode`.
4. Nhúng Money vào Product bằng `@Embedded(prefix = "price_")`.
5. Tạo schema có `price_amount` và `price_currency_code`; lưu và đọc sản phẩm có giá VND và USD.
6. Thử hàng có cả hai cột price null, rồi đọc với `USE_NULL` và `USE_EMPTY`; quan sát khác biệt.
7. Thử dữ liệu partial-null và quyết định domain có cho phép hay không.
8. Thêm CHECK constraint để bảo đảm hai cột cùng null hoặc cùng có giá trị.
9. Viết query lọc sản phẩm theo currency và amount; so sánh với phương án lưu Money thành một chuỗi.
10. Thiết kế migration từ cột `price_value` chứa chuỗi sang hai cột embedded; liệt kê cách xử lý bản ghi lỗi.
11. Thảo luận trường hợp nên lưu object thành JSON một cột và trường hợp nên trải phẳng thành nhiều cột.
12. Xác định khi nào một object nên là embedded value object, khi nào cần bảng riêng hoặc aggregate reference.

## 17. Ghi nhớ

Custom converter của Spring Data JDBC chuyển một kiểu domain thành một giá trị database và ngược lại. Nó phù hợp với property có một biểu diễn scalar, chẳng hạn mã sản phẩm hoặc email đã được kiểm tra. Converter không tự phân rã một property thành nhiều cột vật lý; `JdbcValue` cũng chỉ mô tả một giá trị JDBC cùng kiểu bind của nó.

Khi một value object cần nhiều cột độc lập trong cùng bảng, dùng `@Embedded` và prefix để ánh xạ các property con. Khi dữ liệu cần nằm ở bảng khác, dùng mô hình quan hệ aggregate; khi kết quả đến từ JOIN/báo cáo, dùng query và DTO/RowMapper. Chọn cách lưu dựa trên nhu cầu truy vấn, constraint, vòng đời và ý nghĩa domain, đồng thời xác định rõ cách xử lý object null và null một phần.
