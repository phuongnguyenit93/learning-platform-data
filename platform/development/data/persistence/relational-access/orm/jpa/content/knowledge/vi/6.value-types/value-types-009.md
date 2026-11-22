# Áp dụng converter tường minh và tự động trong JPA

Khi ánh xạ thuộc tính của entity, Java Persistence API (JPA) thường xử lý trực tiếp các kiểu cơ bản như `String`, `Integer`, `BigDecimal` hoặc `LocalDate`. Nhưng ứng dụng thực tế còn có những **kiểu giá trị** (*value types*) biểu diễn quy tắc nghiệp vụ: mã sản phẩm, mã kho, đơn vị đo, địa chỉ email hay mã định danh được đóng gói trong một lớp riêng. Một cột SQL có thể lưu các giá trị này dưới dạng `VARCHAR` hoặc kiểu cơ bản khác, trong khi code Java muốn thao tác bằng object có ý nghĩa.

**Attribute converter** là cơ chế chuẩn của JPA giúp chuyển đổi giữa kiểu thuộc tính Java và kiểu dữ liệu được lưu ở database. Có hai cách áp dụng chính:

- **Tường minh:** chỉ định converter trên thuộc tính cụ thể bằng `@Convert(converter = ...)`.
- **Tự động:** đánh dấu lớp converter với `@Converter(autoApply = true)` để JPA áp dụng cho các thuộc tính có kiểu phù hợp trong phạm vi persistence unit.

Hai cách dùng cùng giao diện `AttributeConverter<X, Y>`. Điểm khác nhau là **ai chọn nơi converter được áp dụng**: lập trình viên chỉ rõ từng thuộc tính, hay provider tự tìm những thuộc tính có kiểu Java tương ứng.

## 1. Converter nằm ở đâu trong quá trình persistence?

Ví dụ một entity có thuộc tính Java kiểu `ProductCode`, nhưng bảng `product` có cột `product_code VARCHAR(40)`.

~~~text
                     TẦNG JAVA
             Product entity
                 |
                 |  product.code : ProductCode
                 v
           AttributeConverter
      ProductCode <----> String
                 |
                 v
             JPA Provider
                 |
                 |  JDBC parameter / result
                 v
                     TẦNG SQL
         product.product_code VARCHAR(40)
~~~

Hai hướng được thực hiện bởi converter:

1. **Java → database:** chuyển `ProductCode` thành `String` để provider lưu vào cột SQL phù hợp.
2. **Database → Java:** lấy chuỗi từ kết quả truy vấn, chuyển lại thành `ProductCode` khi dựng entity.

JPA vẫn đảm nhiệm vòng đời entity, dirty checking, truy vấn và giao dịch. Converter chỉ đảm nhiệm **chuyển đổi giá trị của một thuộc tính**; nó không tự mở kết nối JDBC hoặc commit transaction.

Một số trường hợp điển hình:

| Kiểu Java mong muốn | Dạng lưu database | Lý do dùng converter |
|---|---|---|
| `ProductCode` | `VARCHAR(40)` | Đóng gói kiểm tra/chuẩn hóa mã sản phẩm |
| `WarehouseCode` | `VARCHAR(20)` | Tránh dùng `String` tùy ý cho mã kho |
| `Percentage` | `DECIMAL(7,4)` | Biểu diễn phần trăm bằng kiểu nghiệp vụ riêng |
| `ColorCode` | `VARCHAR(7)` | Đóng gói định dạng mã màu |
| `MoneyInCents` | `BIGINT` | Lưu số nguyên đơn vị nhỏ nhất, tránh trôi số thực |

Ví dụ chỉ minh họa cách chọn kiểu lưu; với tiền tệ cần thiết kế rõ đơn vị, làm tròn, miền giá trị và thông tin tiền tệ. Converter không thay thế những quyết định đó.

## 2. Giao diện `AttributeConverter<X, Y>`

Trong Jakarta Persistence 3.x, API nằm ở package `jakarta.persistence`:

~~~java
package jakarta.persistence;

public interface AttributeConverter<X, Y> {
    Y convertToDatabaseColumn(X attribute);

    X convertToEntityAttribute(Y dbData);
}
~~~

Trong đó:

- **`X`:** kiểu của thuộc tính entity ở Java, chẳng hạn `ProductCode`.
- **`Y`:** kiểu Java đại diện cho giá trị đưa xuống/lấy lên từ tầng lưu trữ, chẳng hạn `String`. Provider ánh xạ `Y` tới kiểu JDBC/SQL phù hợp.
- **`convertToDatabaseColumn(X)`:** biến đổi trước khi ghi giá trị vào database.
- **`convertToEntityAttribute(Y)`:** biến đổi dữ liệu đọc từ database về kiểu Java mong muốn.

Ví dụ khai báo:

~~~java
public class ProductCodeConverter
        implements AttributeConverter<ProductCode, String> {
    // ...
}
~~~

Ở đây không có phương thức “convert SQL thành byte”. JDBC/provider vẫn phụ trách chuyển giữa `String` Java và kiểu cột SQL. Converter là tầng ánh xạ **giá trị Java với giá trị Java dùng cho lưu trữ**.

### 2.1. Vòng đời gọi converter

~~~text
persist / flush
    ProductCode("SP-001")
          |
          v
convertToDatabaseColumn(...)
          |
          v
       "SP-001"
          |
          v
    INSERT / UPDATE qua JDBC

find / query
    SELECT product_code qua JDBC
          |
          v
       "SP-001"
          |
          v
convertToEntityAttribute(...)
          |
          v
    ProductCode("SP-001")
~~~

Provider có thể tối ưu hay hoãn SQL theo flush mode và trạng thái entity, vì vậy không nên suy ra mỗi setter chắc chắn gọi converter hoặc thực thi một `UPDATE` ngay lập tức. Converter có thể được gọi nhiều lần tùy các thao tác provider thực hiện; hãy thiết kế hai phương thức thuần về mặt logic và ít tác dụng phụ.

### 2.2. Null và dữ liệu không hợp lệ

Converter nên xử lý `null` rõ ràng:

~~~java
@Override
public String convertToDatabaseColumn(ProductCode code) {
    return code == null ? null : code.value();
}

@Override
public ProductCode convertToEntityAttribute(String value) {
    return value == null ? null : new ProductCode(value);
}
~~~

Điều này tránh `NullPointerException` khi cột cho phép `NULL`. Nếu dữ liệu database không hợp lệ với quy tắc của value object, constructor hoặc converter có thể báo lỗi; JPA provider có thể bọc lỗi trong exception persistence tương ứng.

Không nên âm thầm biến giá trị không hợp lệ thành giá trị mặc định vì có thể che giấu lỗi dữ liệu. Nếu cột không được phép rỗng, khai báo constraint/validation riêng, chẳng hạn `@Column(nullable = false)` và một quy tắc Bean Validation phù hợp.

## 3. Áp dụng converter tường minh với `@Convert`

Khi chỉ một hoặc một số thuộc tính cần chuyển đổi, hãy chọn `@Convert(converter = ...)`. Cách này làm cho dependency hiển thị ngay tại nơi khai báo thuộc tính.

### 3.1. Bước 1: Tạo kiểu giá trị `ProductCode`

Ví dụ Java 17 trở lên, dùng một class bất biến:

~~~java
package com.example.shop.domain;

import java.util.Locale;
import java.util.Objects;

public final class ProductCode {
    private final String value;

    public ProductCode(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Product code is required");
        }

        String normalized = raw.trim().toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z0-9-]{1,40}")) {
            throw new IllegalArgumentException(
                "Invalid product code: " + raw
            );
        }

        this.value = normalized;
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof ProductCode other)) {
            return false;
        }
        return value.equals(other.value);
    }

    @Override
    public int hashCode() {
        return Objects.hash(value);
    }

    @Override
    public String toString() {
        return value;
    }
}
~~~

`ProductCode` là *value object*: hai instance có cùng mã được xem là cùng một giá trị. Ví dụ sử dụng Java 17 để dùng cú pháp `instanceof ProductCode other`. Nếu dự án dùng phiên bản Java cũ hơn, cần viết lại phần so sánh theo cú pháp tương thích.

Quy tắc cho phép tối đa 40 ký tự ASCII viết hoa, số và dấu gạch nối chỉ là ví dụ nghiệp vụ. Nếu mã sản phẩm cần Unicode, ký tự khác hoặc chính sách chuẩn hóa riêng, hãy chỉnh quy tắc cho phù hợp thay vì coi đây là quy tắc bắt buộc của JPA.

### 3.2. Bước 2: Viết converter

~~~java
package com.example.shop.persistence;

import com.example.shop.domain.ProductCode;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class ProductCodeConverter
        implements AttributeConverter<ProductCode, String> {

    @Override
    public String convertToDatabaseColumn(ProductCode attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public ProductCode convertToEntityAttribute(String dbData) {
        return dbData == null ? null : new ProductCode(dbData);
    }
}
~~~

`@Converter(autoApply = false)` khai báo converter nhưng **không yêu cầu tự áp dụng cho mọi thuộc tính `ProductCode`**. Giá trị `false` cũng là mặc định của `autoApply`, nên có thể viết ngắn gọn `@Converter`.

Để converter có tác dụng, phải có một vị trí sử dụng rõ ràng như `@Convert(converter = ProductCodeConverter.class)`.

### 3.3. Bước 3: Gắn `@Convert` lên field của entity

~~~java
package com.example.shop.domain;

import com.example.shop.persistence.ProductCodeConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = ProductCodeConverter.class)
    @Column(name = "product_code", length = 40, nullable = false)
    private ProductCode code;

    @Column(name = "title", length = 200, nullable = false)
    private String title;

    protected Product() {
    }

    public Product(ProductCode code, String title) {
        this.code = code;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public ProductCode getCode() {
        return code;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Phân biệt các annotation:

| Annotation | Vai trò |
|---|---|
| `@Entity` | Khai báo loại object được JPA quản lý |
| `@Id` | Xác định khóa chính của entity |
| `@Convert(converter = ...)` | Chọn converter cho thuộc tính `code` |
| `@Column(name = "product_code")` | Chọn cột SQL chứa mã |
| `@Column(length = 40)` | Metadata độ dài cột chuỗi nếu provider sinh DDL |
| `@Converter` trên lớp converter | Đăng ký converter và quy tắc tự động áp dụng |

Trong ví dụ này `code` là một thuộc tính persistent được ánh xạ thành một cột; `ProductCode` không cần `@Entity` hay `@Embeddable`. JPA sử dụng converter để lưu giá trị nó chứa.

### 3.4. Bước 4: Schema database tương ứng

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_code VARCHAR(40) NOT NULL,
    title VARCHAR(200) NOT NULL
);
~~~

Nhờ converter, ứng dụng xử lý `ProductCode` còn bảng vẫn chứa chuỗi `product_code`. Việc tạo bảng thực tế phải được quản lý qua schema generation hoặc migration phù hợp. `@Convert` tự nó không tạo schema.

### 3.5. Bước 5: Lưu và đọc entity

Trong một transaction do Spring quản lý, service có thể viết:

~~~java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {
    private final EntityManager entityManager;

    public ProductService(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public Long createProduct() {
        Product product = new Product(
            new ProductCode("sp-001"),
            "Sổ tay"
        );

        entityManager.persist(product);
        return product.getId();
    }

    @Transactional(readOnly = true)
    public Product findProduct(Long id) {
        return entityManager.find(Product.class, id);
    }
}
~~~

Ở tầng Java, mã sản phẩm là `ProductCode("SP-001")`. Trong bảng, giá trị lưu là chuỗi `SP-001`. Khi đọc bản ghi, converter tạo lại `ProductCode` cho thuộc tính `code`.

`@Transactional` trong ví dụ thuộc Spring. Với JPA thuần dùng `RESOURCE_LOCAL`, cần chủ động bắt đầu/commit/rollback giao dịch bằng `EntityTransaction` hoặc dùng transaction manager khác.

## 4. Áp dụng tự động bằng `@Converter(autoApply = true)`

Khi **tất cả các thuộc tính cùng một value type** nên có cùng cách chuyển đổi, khai báo converter tự động giúp tránh lặp `@Convert` trên từng field.

### 4.1. Tạo kiểu giá trị `WarehouseCode`

~~~java
package com.example.shop.domain;

import java.util.Locale;
import java.util.Objects;

public final class WarehouseCode {
    private final String value;

    public WarehouseCode(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("Warehouse code is required");
        }

        String normalized = raw.trim().toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z0-9-]{1,20}")) {
            throw new IllegalArgumentException(
                "Invalid warehouse code: " + raw
            );
        }

        this.value = normalized;
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object value) {
        return value instanceof WarehouseCode other
            && this.value.equals(other.value);
    }

    @Override
    public int hashCode() {
        return Objects.hash(value);
    }
}
~~~

### 4.2. Khai báo converter tự động

~~~java
package com.example.shop.persistence;

import com.example.shop.domain.WarehouseCode;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = true)
public class WarehouseCodeConverter
        implements AttributeConverter<WarehouseCode, String> {

    @Override
    public String convertToDatabaseColumn(WarehouseCode attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public WarehouseCode convertToEntityAttribute(String dbData) {
        return dbData == null ? null : new WarehouseCode(dbData);
    }
}
~~~

Điểm quyết định là `autoApply = true`: khi provider nhận diện converter này trong persistence unit, nó sẽ áp dụng cho các **thuộc tính persistent đủ điều kiện có kiểu `WarehouseCode`**, không cần khai báo `@Convert` trên từng thuộc tính.

### 4.3. Entity không cần nhắc đến converter

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "inventory_stock")
public class InventoryStock {

    @Id
    private Long id;

    @Column(name = "warehouse_code", length = 20, nullable = false)
    private WarehouseCode warehouseCode;

    @Column(name = "backup_warehouse_code", length = 20)
    private WarehouseCode backupWarehouseCode;

    protected InventoryStock() {
    }

    // Constructor, getters và nghiệp vụ khác...
}
~~~

Cả `warehouseCode` và `backupWarehouseCode` đều có kiểu `WarehouseCode`, nên cùng converter tự động được áp dụng (giả định không có khai báo override hoặc loại trừ).

Nếu một entity khác cũng có `WarehouseCode`:

~~~java
@Entity
public class Shipment {

    @Id
    private Long id;

    private WarehouseCode originWarehouse;
    private WarehouseCode destinationWarehouse;

    protected Shipment() {
    }
}
~~~

Các thuộc tính phù hợp trong `Shipment` cũng được chuyển đổi tự động. Không cần copy annotation converter sang mọi entity.

### 4.4. Phạm vi tự động áp dụng

`autoApply` hoạt động trong phạm vi **persistence unit đã quản lý/nhận diện converter**. Với cách bootstrap dùng `persistence.xml`, các class được quét hoặc liệt kê phải nằm trong phạm vi quản lý thích hợp. Nếu thiết lập `exclude-unlisted-classes` hoặc cấu hình scanning đặc biệt, cần bảo đảm provider phát hiện lớp converter.

Trong dự án dùng Spring Boot/Hibernate, converter thường được tìm thấy nhờ entity scanning hoặc package scanning phù hợp. Nhưng việc một file `.java` có tồn tại trong source không đảm bảo converter đã được đăng ký ở persistence unit đang chạy.

Một khía cạnh quan trọng của đặc tả là converter tự động được chọn dựa trên **kiểu thuộc tính Java `X`**. Vì vậy:

- `WarehouseCode` tự động chuyển được nếu converter đã đăng ký.
- `String` không tự động dùng `WarehouseCodeConverter`, mặc dù kết quả cột cuối cùng là chuỗi.
- Một kiểu khác như `ProductCode` không dùng `WarehouseCodeConverter`.
- Nếu nhiều converter tự động cùng nhắm vào một kiểu `X`, cần giải quyết rõ ràng; không nên dựa vào thứ tự quét lớp để chọn ngẫu nhiên.

## 5. So sánh converter tường minh và tự động

| Tiêu chí | `@Convert(converter = ...)` | `@Converter(autoApply = true)` |
|---|---|---|
| Điểm kích hoạt | Annotation trên thuộc tính/vị trí ánh xạ | Annotation trên lớp converter |
| Phạm vi | Chỗ được khai báo cụ thể | Các thuộc tính đủ điều kiện có cùng kiểu `X` trong PU |
| Mức rõ ràng ở entity | Rất rõ converter được chọn | Entity gọn, cần biết cấu hình provider |
| Mức lặp | Có thể lặp trên nhiều thuộc tính | Ít lặp cho kiểu giá trị dùng rộng rãi |
| Phù hợp nhất | Có ngoại lệ theo thuộc tính, conversion không đồng nhất | Một value type có một representation mặc định nhất quán |
| Khi cần thay đổi converter | Sửa các vị trí khai báo tương ứng | Sửa một converter có thể tác động nhiều entity |
| Rủi ro cần chú ý | Quên annotation hoặc chọn nhầm converter | Tác động lan rộng ngoài dự kiến nếu kiểu `X` quá phổ biến |
| Độ phụ thuộc provider | Cả hai là cơ chế chuẩn JPA | Cả hai là cơ chế chuẩn JPA; việc quét cần được cấu hình đúng |

### Quy tắc lựa chọn

Chọn **tường minh** khi một thuộc tính có quy tắc đặc thù hoặc có nhiều cách biểu diễn hợp lệ cho cùng một value type. Chọn **tự động** khi cả dự án thống nhất “mọi giá trị `WarehouseCode` đều lưu thành `VARCHAR` theo cùng một format”.

Không nên đặt converter tự động cho một kiểu quá phổ biến, chẳng hạn `String` hoặc `Integer`, nếu mục đích chỉ điều chỉnh một vài field. Converter tự động kiểu `String` có thể làm thay đổi ngoài dự kiến tên khách hàng, mã giao dịch, mô tả sản phẩm và nhiều cột khác trong toàn persistence unit.

## 6. Ưu tiên áp dụng: Tường minh, tự động và tắt chuyển đổi

Có thể hình dung cách JPA quyết định converter cho một thuộc tính cơ bản đủ điều kiện như sau:

~~~text
Thuộc tính persistent
       |
       v
Có @Convert(converter = SomeConverter.class)?
       |                         |
      Có                        Không
       |                         |
       v                         v
Dùng converter chỉ định     Có @Convert(disableConversion = true)?
                                 |                    |
                                Có                   Không
                                 |                    |
                                 v                    v
                           Không áp dụng        Có converter autoApply
                           converter           phù hợp với kiểu X?
                                                  |          |
                                                 Có         Không
                                                  |          |
                                                  v          v
                                          Áp dụng auto   Mapping mặc định
~~~

Đây là mô hình tư duy cho tình huống phổ biến. Quy tắc chính xác còn bao gồm loại thuộc tính được JPA cho phép convert, vị trí annotation trong access strategy, và các khai báo converter trên embedded/mapped superclass. Không nên giả định mọi field Java đều tự động được convert.

### 6.1. Ghi đè converter tự động bằng converter tường minh

Giả sử ứng dụng có converter tự động cho `WarehouseCode`, nhưng một cột legacy phải dùng định dạng khác. Khi thích hợp, có thể khai báo converter tường minh dành riêng cho cột:

~~~java
@Convert(converter = LegacyWarehouseCodeConverter.class)
@Column(name = "legacy_warehouse_code", length = 25)
private WarehouseCode legacyWarehouseCode;
~~~

`LegacyWarehouseCodeConverter` cũng phải triển khai `AttributeConverter<WarehouseCode, Y>` với kiểu lưu trữ thích hợp. Converter được chỉ định tường minh cho field này thay thế lựa chọn tự động. Các field `WarehouseCode` khác tiếp tục dùng converter tự động.

Ví dụ tối giản:

~~~java
@Converter
public class LegacyWarehouseCodeConverter
        implements AttributeConverter<WarehouseCode, String> {

    @Override
    public String convertToDatabaseColumn(WarehouseCode code) {
        return code == null ? null : "WH:" + code.value();
    }

    @Override
    public WarehouseCode convertToEntityAttribute(String value) {
        if (value == null) {
            return null;
        }
        if (!value.startsWith("WH:")) {
            throw new IllegalArgumentException(
                "Unsupported legacy warehouse code: " + value
            );
        }
        return new WarehouseCode(value.substring(3));
    }
}
~~~

Mục đích ở đây là minh họa cách một cột có thể lưu `WH:HN-01` trong khi những cột khác lưu `HN-01`. Không nên thay đổi định dạng dữ liệu của một cột thật mà không chuẩn bị migration/khả năng đọc ngược.

### 6.2. Tắt chuyển đổi bằng `disableConversion`

JPA cung cấp:

~~~java
@Convert(disableConversion = true)
private String rawText;
~~~

Điều này hữu ích khi một converter tự động đang áp dụng lên `String` và một field cụ thể **muốn giữ mapping cơ bản mặc định** của `String`.

Ví dụ tình huống độc lập:

~~~java
@Converter(autoApply = true)
public class TrimmedStringConverter
        implements AttributeConverter<String, String> {

    @Override
    public String convertToDatabaseColumn(String value) {
        return value == null ? null : value.trim();
    }

    @Override
    public String convertToEntityAttribute(String value) {
        return value;
    }
}
~~~

Nếu converter này đã được đăng ký, một entity có thể loại trừ field cần giữ nguyên khoảng trắng:

~~~java
@Column(name = "summary")
private String summary; // auto conversion có thể trim khi ghi

@Convert(disableConversion = true)
@Column(name = "verbatim_text")
private String verbatimText; // lưu bằng mapping String thông thường
~~~

Đây là ví dụ **minh họa cơ chế**, không phải khuyến nghị bật trimming trên mọi `String`. Việc tự thay đổi nội dung văn bản có thể không thích hợp với tên riêng, nội dung có chữ ký số, thông điệp người dùng và các lĩnh vực yêu cầu giữ nguyên dữ liệu.

**Lưu ý quan trọng:** nếu tắt converter trên một field kiểu custom như `WarehouseCode` mà provider không có mapping cơ bản cho kiểu đó, quá trình bootstrap hoặc ghi đọc có thể lỗi. `disableConversion = true` chỉ tắt cơ chế chuyển đổi, không tự cung cấp cách lưu trữ khác cho kiểu Java chưa được JPA hỗ trợ.

### 6.3. Không đặt một converter tự động trùng kiểu một cách mơ hồ

Ví dụ có hai lớp:

~~~java
@Converter(autoApply = true)
class WarehouseCodeConverterA
        implements AttributeConverter<WarehouseCode, String> {
    // ...
}

@Converter(autoApply = true)
class WarehouseCodeConverterB
        implements AttributeConverter<WarehouseCode, String> {
    // ...
}
~~~

Khi cùng một loại `WarehouseCode` có nhiều converter tự động đủ điều kiện, cấu hình trở nên mơ hồ và provider có thể báo lỗi hoặc cần quy tắc lựa chọn riêng. Một thiết kế ổn định là chọn **một converter mặc định cho mỗi kiểu giá trị**, rồi dùng `@Convert(converter = ...)` tại những vị trí có ngoại lệ. Không trông đợi thứ tự classpath quyết định converter nào thắng.

## 7. Vị trí đặt `@Convert` và access strategy

JPA hỗ trợ hai kiểu truy cập persistent state:

- **Field access:** annotation ánh xạ đặt trên field, ví dụ `@Id` gắn field; JPA truy cập giá trị field theo chiến lược ánh xạ.
- **Property access:** annotation đặt trên getter JavaBean; JPA truy cập thông qua property theo quy tắc tương ứng.

Nếu entity đang dùng field access:

~~~java
@Entity
public class Product {

    @Id
    private Long id;

    @Convert(converter = ProductCodeConverter.class)
    private ProductCode code;
}
~~~

Nếu entity dùng property access, annotation converter đặt trên getter:

~~~java
@Entity
public class Product {

    private Long id;
    private ProductCode code;

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    @Convert(converter = ProductCodeConverter.class)
    public ProductCode getCode() {
        return code;
    }

    public void setCode(ProductCode code) {
        this.code = code;
    }
}
~~~

Việc để `@Id` trên getter trong ví dụ thứ hai làm entity sử dụng property access mặc định. Không trộn annotation trên field và getter một cách tùy tiện; nếu cần kiểu truy cập khác cho một phần mô hình, khai báo `@Access` phù hợp.

**Thực hành tốt:** đặt `@Convert` cạnh `@Column`, `@Basic` và các annotation mapping của chính thuộc tính đó, nhất quán với access strategy của entity.

## 8. Converter với embeddable và collection

Converter cũng liên quan đến các thuộc tính cơ bản nằm trong mô hình phức tạp hơn như `@Embeddable` hoặc element collection. Trong một số tình huống, `@Convert(attributeName = "...")` cho phép chỉ ra thuộc tính cụ thể bên trong embedded value.

### 8.1. Converter trực tiếp trên field của embeddable

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Embeddable;

@Embeddable
public class ShipmentInfo {

    @Convert(converter = ProductCodeConverter.class)
    @Column(name = "tracking_code", length = 40)
    private ProductCode trackingCode;

    protected ShipmentInfo() {
    }
}
~~~

Với một entity:

~~~java
@Entity
public class Shipment {

    @Id
    private Long id;

    @Embedded
    private ShipmentInfo info;
}
~~~

Ở đây `ShipmentInfo` là object được nhúng, không phải entity độc lập có khóa chính. Thuộc tính `trackingCode` của nó được chuyển đổi như đã khai báo.

### 8.2. Chỉ định theo đường dẫn bằng `attributeName`

Khi cần đặt cấu hình conversion từ vị trí khai báo embedded attribute, có thể dùng tên field bên trong embeddable:

~~~java
@Embedded
@Convert(
    attributeName = "trackingCode",
    converter = ProductCodeConverter.class
)
private ShipmentInfo info;
~~~

Cách này hữu ích khi một embeddable được sử dụng ở nhiều nơi nhưng chỉ một vị trí cần converter khác. Với embedding lồng nhau, `attributeName` có thể là đường dẫn thuộc tính phân tách bằng dấu chấm theo quy tắc JPA.

**Không đồng thời giữ cấu hình @Convert trùng nhau ở nhiều vị trí mà không có chủ đích.** Hãy chọn một chỗ rõ ràng để giải thích cấu hình override. Nếu đây là hệ thống dùng provider/phiên bản đặc thù, cần thử mapping thực tế của loại collection/Map vì tên đường dẫn và khả năng hỗ trợ chi tiết phụ thuộc cấu trúc ánh xạ.

### 8.3. `@ElementCollection` và Map

Một collection của basic/value type có thể có converter cho phần tử hoặc cho thuộc tính nhúng theo quy tắc JPA. Ví dụ lưu các mã kho vào một bảng collection:

~~~java
@Entity
public class StockGroup {

    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "stock_group_warehouse",
        joinColumns = @JoinColumn(name = "group_id")
    )
    @Column(name = "warehouse_code", length = 20)
    private Set<WarehouseCode> warehouses = new HashSet<>();
}
~~~

Nếu `WarehouseCodeConverter` được đăng ký với `autoApply = true` và kiểu phần tử đủ điều kiện, provider có thể áp dụng converter cho giá trị phần tử. Với Map hoặc embeddable sâu hơn, hãy phân biệt **key, value và các thuộc tính lồng bên trong** trước khi chọn `attributeName`, rồi đối chiếu đặc tả/provider đang dùng.

Converter ở đây chỉ biến đổi giá trị, không quyết định tên bảng collection, khóa ngoại hay cấu trúc quan hệ; các annotation collection mapping vẫn có nhiệm vụ đó.

## 9. Những thuộc tính không nên/mặc định không thể áp dụng converter

Đặc tả JPA giới hạn việc áp dụng converter ở một số vị trí. Các trường hợp thường không thuộc phạm vi tự động áp dụng chuẩn gồm:

| Trường hợp | Vì sao cần chú ý |
|---|---|
| `@Id` và `@EmbeddedId` | Định danh entity có quy tắc mapping và identity riêng; dùng converter cho ID không phải trường hợp di động được đặc tả bảo đảm |
| `@Version` | Thuộc tính version phục vụ optimistic locking và có quy tắc kiểu/so sánh đặc thù |
| Quan hệ `@ManyToOne`, `@OneToMany`, `@OneToOne`, `@ManyToMany` | Đây là mapping quan hệ giữa entity, không phải giá trị cơ bản đổi thành một cột |
| Thuộc tính có `@Enumerated` | JPA đã dùng cơ chế ánh xạ enum được khai báo; không kết hợp tùy tiện với converter |
| Thuộc tính có `@Temporal` | JPA đã áp dụng mapping temporal tương ứng; không giả định converter sẽ được áp dụng |
| Thuộc tính không persistent / `@Transient` | Không có cột persistent để JPA thực hiện chuyển đổi |

Đối với những vị trí không được đặc tả bảo đảm, một provider có thể cung cấp phần mở rộng; code phụ thuộc phần mở rộng đó **không còn mang tính di động của JPA chuẩn**.

### 9.1. Enum: `@Enumerated` khác converter

Cách ánh xạ enum quen thuộc:

~~~java
public enum OrderStatus {
    NEW, PAID, CANCELLED
}

@Enumerated(EnumType.STRING)
@Column(name = "status", length = 20)
private OrderStatus status;
~~~

Ở đây JPA dùng tên enum constant như `PAID` để lưu chuỗi, theo quy tắc `EnumType.STRING`.

Nếu muốn mã SQL tùy chỉnh, chẳng hạn `"N"`, `"P"`, `"C"`, có thể cân nhắc converter riêng cho enum, **nhưng không gắn đồng thời `@Enumerated` lên cùng field được convert**. Cách converter thường hữu ích khi yêu cầu format database khác với tên constant và cần kiểm soát backward compatibility.

Ví dụ:

~~~java
@Converter
public class OrderStatusCodeConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus status) {
        if (status == null) {
            return null;
        }
        return switch (status) {
            case NEW -> "N";
            case PAID -> "P";
            case CANCELLED -> "C";
        };
    }

    @Override
    public OrderStatus convertToEntityAttribute(String code) {
        if (code == null) {
            return null;
        }
        return switch (code) {
            case "N" -> OrderStatus.NEW;
            case "P" -> OrderStatus.PAID;
            case "C" -> OrderStatus.CANCELLED;
            default -> throw new IllegalArgumentException(
                "Unknown order status code: " + code
            );
        };
    }
}
~~~

Sử dụng:

~~~java
@Convert(converter = OrderStatusCodeConverter.class)
@Column(name = "status", length = 1, nullable = false)
private OrderStatus status;
~~~

Đoạn `switch expression` yêu cầu Java phiên bản hỗ trợ cú pháp tương ứng; ví dụ dùng Java 17. Với enum custom converter, phải tính đến dữ liệu cũ khi đổi mã, vì đổi từ `PAID` sang `P` không tự cập nhật bản ghi đã lưu.

### 9.2. Không nhầm converter với quan hệ hoặc embeddable

Nếu một object gồm nhiều thuộc tính cần lưu vào nhiều cột, `@Embeddable`/`@Embedded` thường phù hợp hơn converter một cột. Nếu một object là entity có identity riêng và quan hệ tới object khác, dùng `@ManyToOne`, `@OneToOne`... thay vì ép cả entity thành chuỗi qua converter.

Converter phù hợp nhất khi **một giá trị ở tầng Java có một cách biểu diễn cơ bản ở tầng database**.

## 10. Converter trong JPQL và native SQL

### 10.1. Truy vấn JPQL theo thuộc tính đã convert

Entity `Product` có thuộc tính `code` kiểu `ProductCode`:

~~~java
List<Product> products = entityManager.createQuery(
        "SELECT p FROM Product p WHERE p.code = :code",
        Product.class)
    .setParameter("code", new ProductCode("SP-001"))
    .getResultList();
~~~

Ở tầng JPQL, `p.code` là **thuộc tính Java `ProductCode`**. Khi provider tạo SQL và bind tham số cho phép so sánh thuộc tính đã convert, nó có ngữ cảnh mapping để chuyển giá trị theo converter tương ứng.

Ví dụ về mặt ý tưởng, SQL có thể là:

~~~sql
SELECT id, product_code, title
FROM product
WHERE product_code = ?;
-- Tham số thực tế: "SP-001"
~~~

Không nên nhầm `ProductCode` thành tên cột. JPQL làm việc với entity và property; SQL làm việc với bảng, cột và giá trị JDBC.

Các thao tác JPQL phức tạp, function database và literal không phải lúc nào cũng có ngữ cảnh đủ rõ để chuyển một value type tùy chỉnh. Nếu gặp vấn đề bind parameter, kiểm tra đúng kiểu parameter và metadata provider, thay vì tự nối giá trị vào chuỗi JPQL.

### 10.2. Native SQL không tự chuyển mọi tham số value object

Trong `createNativeQuery` hoặc JDBC thuần, SQL trực tiếp không nhất thiết mang ngữ cảnh mapping thuộc tính `ProductCode` cho từng tham số. Ví dụ:

~~~java
entityManager.createNativeQuery(
    "SELECT * FROM product WHERE product_code = ?"
).setParameter(1, "SP-001").getResultList();
~~~

Ở đây dùng giá trị lưu trữ `String` một cách rõ ràng. Nếu cần chuyển một `ProductCode` thành dạng cột ở mã truy vấn native, có thể dùng logic chuyển đổi phù hợp hoặc API provider có typing rõ ràng; không giả định một tham số `new ProductCode(...)` luôn được tự nhận diện trong native SQL.

Nếu trả về entity đầy đủ theo ánh xạ JPA:

~~~java
List<Product> products = entityManager.createNativeQuery(
    "SELECT id, product_code, title FROM product WHERE product_code = ?",
    Product.class
).setParameter(1, "SP-001")
 .getResultList();
~~~

Provider có thể dựng entity và áp dụng mapping/converter của `Product.code` ở phía kết quả. Kết quả native query phải chứa đủ cột phù hợp để ánh xạ entity.

### 10.3. JPQL UPDATE, cache và logic domain

Với managed entity, thay đổi value object được provider xem là thay đổi thuộc tính theo cơ chế dirty checking khi có sự khác biệt. Nhưng converter không biến object thành tracked mutable value object một cách kỳ diệu.

Nếu `ProductCode` là object mutable và code sửa bên trong mà không thay field reference, khả năng phát hiện thay đổi còn phụ thuộc cơ chế dirty checking/snapshot của provider. **Ưu tiên value object bất biến**, tạo instance mới khi thay giá trị và triển khai `equals()/hashCode()` nhất quán.

Nếu dùng JPQL bulk update hoặc thao tác JDBC trực tiếp, những thay đổi có thể bỏ qua trạng thái managed entity đã được cache trong persistence context. Converter không thay thế yêu cầu đồng bộ context/transaction.

## 11. Những giới hạn cần thiết kế trước

### 11.1. Converter không phải migration schema

Từ:

~~~java
@Convert(converter = ProductCodeConverter.class)
@Column(name = "product_code", length = 40)
private ProductCode code;
~~~

không thể kết luận database chắc chắn có `VARCHAR(40)`. Schema có thể đang dùng `CHAR(20)`, `VARCHAR(10)` hoặc một kiểu khác. Cần kiểm tra DDL thực tế và áp dụng migration có kiểm soát nếu thay đổi dạng lưu trữ.

Chuyển converter từ lưu `"SP-001"` sang `"P:SP-001"` cũng là thay đổi **format dữ liệu**. Nếu database đã chứa các giá trị cũ, converter mới cần chiến lược đọc tương thích hoặc migration để chuyển dữ liệu.

### 11.2. Converter không thay thế validation

Constructor của `ProductCode` có thể kiểm tra tính hợp lệ khi code tạo object mới, nhưng dữ liệu từ database và API vẫn cần được xử lý nghiêm túc.

- `@Column(nullable = false)` mô tả metadata/constraint NULL.
- `@Column(length = 40)` mô tả độ dài cột khi tạo schema.
- Converter chuyển giá trị giữa hai kiểu.
- Bean Validation hoặc validation domain thực thi quy tắc nghiệp vụ.
- Constraint của database bảo vệ tính toàn vẹn dữ liệu ở tầng lưu trữ.

Những trách nhiệm này hỗ trợ nhau; không nên dồn tất cả vào `convertToDatabaseColumn`.

### 11.3. Converter không tự giải quyết mã hóa và bảo mật

Có thể bắt gặp converter “mã hóa” chuỗi trước khi lưu. Nhưng việc bảo vệ dữ liệu nhạy cảm còn liên quan quản lý khóa, thuật toán, rotation, truy vấn/index, threat model và chính sách truy cập.

Không nên triển khai một converter mã hóa đơn giản rồi mặc định hệ thống đã đạt yêu cầu an toàn. Nếu cần encryption at rest hoặc mã hóa field, hãy sử dụng giải pháp bảo mật được thiết kế, kiểm định và quản lý khóa phù hợp.

### 11.4. Chi phí khi converter có tác dụng phụ

Một converter có thể được gọi trong flush, load, query binding hoặc hoạt động nội bộ của provider. Tránh:

- Gọi mạng/HTTP hoặc truy vấn database bổ sung trong converter.
- Đọc thời gian hiện tại hay random để tạo kết quả khác nhau qua các lần gọi.
- Thay đổi object đầu vào ngoài ý muốn.
- Ghi log giá trị nhạy cảm.
- Phụ thuộc transaction mới hoặc bean có vòng đời không rõ ràng.

Converter lý tưởng là hàm biến đổi xác định: cùng đầu vào hợp lệ trả về cùng giá trị, xử lý null rõ ràng và không phụ thuộc hệ thống ngoài.

## 12. Khi nào nên dùng converter, khi nào nên chọn mapping khác?

| Nhu cầu | Hướng tiếp cận thường phù hợp |
|---|---|
| Value object một giá trị lưu trong một cột | `AttributeConverter<X,Y>` |
| Một value object có nhiều thành phần lưu trong nhiều cột | `@Embeddable` + `@Embedded` |
| Object có identity và vòng đời độc lập | `@Entity` và quan hệ JPA |
| Enum cần lưu tên constant | `@Enumerated(EnumType.STRING)` |
| Enum cần mã lưu riêng | Converter tường minh khi không dùng `@Enumerated` |
| Cột dùng kiểu DB chuyên biệt mà JPA/JDBC mapping cơ bản không đủ | Mapping/extension của provider hoặc cấu hình JDBC phù hợp |
| Chỉ cần đổi tên cột hoặc độ dài | `@Column`, không cần converter |
| Tính toán giá trị không cần lưu | `@Transient` hoặc phương thức domain |
| Thay đổi toàn bộ nội dung giá trị trước khi gửi API | Xử lý ở tầng API/domain thay vì ép vào persistence converter |

Không phải cứ có custom Java class thì converter là lựa chọn đúng. Hãy xét object đó đại diện cho **một giá trị đơn** hay một cấu trúc quan hệ/aggregate có nhiều thành phần.

## 13. Lỗi thường gặp và cách xử lý

### Lỗi 1: `No basic type mapping` hoặc lỗi ánh xạ cho custom class

~~~java
private ProductCode code; // không @Convert, không autoApply
~~~

Nếu provider không biết cách ánh xạ kiểu `ProductCode`, bootstrap có thể thất bại hoặc gặp lỗi khi persistence. Cần khai báo `@Convert(converter = ProductCodeConverter.class)` hoặc đăng ký converter tự động phù hợp.

### Lỗi 2: Đặt `autoApply=true` nhưng converter không chạy

Kiểm tra:

1. Converter có nằm trong phạm vi quét/đăng ký của persistence unit thực sự đang dùng không?
2. Kiểu `X` có đúng với kiểu thuộc tính hay không?
3. Thuộc tính có thuộc nhóm không được convert tự động, chẳng hạn `@Id`, `@Version`, quan hệ hoặc field đã dùng `@Enumerated` không?
4. Có `@Convert(disableConversion = true)` hoặc converter tường minh ở một vị trí mapping liên quan không?
5. Đang dùng JPA mapping hay native SQL không mang metadata chuyển đổi?

### Lỗi 3: Converter tự động tác động quá nhiều thuộc tính

~~~java
@Converter(autoApply = true)
public class UppercaseConverter
        implements AttributeConverter<String, String> {
    // ...
}
~~~

Một converter như vậy có thể áp dụng rộng rãi cho `String` trong PU, làm thay đổi dữ liệu không mong muốn. Nếu chỉ cần normalize mã nghiệp vụ, hãy tạo value type riêng như `ProductCode` và dùng converter cho kiểu đó.

### Lỗi 4: Đọc dữ liệu cũ bị exception

~~~java
@Override
public ProductCode convertToEntityAttribute(String value) {
    return new ProductCode(value);
}
~~~

Nếu DB có giá trị không hợp lệ theo quy tắc mới, constructor sẽ báo lỗi. Cần quyết định xử lý dữ liệu legacy bằng migration, cơ chế tương thích hoặc quy trình làm sạch dữ liệu. Không nên nuốt exception rồi trả `null` vì có thể làm mất khả năng phát hiện dữ liệu hỏng.

### Lỗi 5: Kết hợp `@Enumerated` và `@Convert`

~~~java
@Enumerated(EnumType.STRING)
@Convert(converter = OrderStatusCodeConverter.class)
private OrderStatus status;
~~~

Đây là cấu hình không phù hợp với cách dùng converter có tính di động được JPA đặc tả. Hãy chọn một chiến lược: lưu tên enum bằng `@Enumerated` hoặc lưu mã tùy chỉnh bằng converter.

### Lỗi 6: Dùng converter trên `@Id` hoặc relation và kỳ vọng mọi provider hỗ trợ

Những vị trí này có quy tắc ánh xạ riêng và không nằm trong phạm vi conversion chuẩn bảo đảm tương tự basic attribute. Nếu buộc phải dùng cơ chế vendor, cần đọc tài liệu provider và kiểm tra tích hợp trên phiên bản cụ thể.

### Lỗi 7: Converter trả kiểu dữ liệu không phù hợp với cột

Ví dụ converter trả `String` `"SP-001"` nhưng schema đang khai báo `BIGINT`. Converter không tự đổi kiểu cột. Hãy thống nhất kiểu `Y`, JDBC mapping và kiểu SQL; quản lý thay đổi schema riêng.

### Lỗi 8: Kiểu dữ liệu mutable khiến dirty checking bất ngờ

Nếu converter dùng custom mutable class mà không có so sánh giá trị ổn định, provider có thể khó xác định thay đổi hoặc lưu lại không đúng thời điểm kỳ vọng. Hãy ưu tiên value object bất biến với `equals()/hashCode()` rõ ràng và thao tác cập nhật bằng cách thay instance mới.

## 14. Bài tập thực hành

### Bài 1: Chọn cách áp dụng

Ứng dụng có kiểu `WarehouseCode` xuất hiện trong 12 entity. Tất cả cột đều lưu dạng chuỗi viết hoa `"HN-01"`, không có ngoại lệ.

**Đề xuất:** dùng một `WarehouseCodeConverter` với `@Converter(autoApply = true)` và bảo đảm converter được đăng ký trong persistence unit. Các entity chỉ khai báo thuộc tính `WarehouseCode`; có thể vẫn dùng `@Column` để chỉ định tên, độ dài và nullability.

Nếu một cột legacy dùng dạng `"WH:HN-01"`, đặt `@Convert(converter = LegacyWarehouseCodeConverter.class)` riêng trên cột đó.

### Bài 2: Dự đoán kiểu dữ liệu

~~~java
@Converter(autoApply = false)
public class PercentageConverter
        implements AttributeConverter<Percentage, BigDecimal> {

    @Override
    public BigDecimal convertToDatabaseColumn(Percentage value) {
        return value == null ? null : value.asDecimal();
    }

    @Override
    public Percentage convertToEntityAttribute(BigDecimal value) {
        return value == null ? null : Percentage.fromDecimal(value);
    }
}
~~~

Hỏi:

- `X` là gì? **`Percentage`**.
- `Y` là gì? **`BigDecimal`**.
- Có tự động áp dụng trên mọi `Percentage` không? **Không**, vì `autoApply = false`.
- Muốn áp dụng cho field `discount` thì khai báo gì? **`@Convert(converter = PercentageConverter.class)`**.
- Cột SQL có bắt buộc là `DECIMAL(7,4)` không? **Không**; phải chọn precision/scale và schema thích hợp theo giá trị thực tế.

### Bài 3: Xác định converter nào được chọn

Giả sử có một converter `WarehouseCodeConverter` với `autoApply = true`. Trong entity:

~~~java
private WarehouseCode mainWarehouse;

@Convert(converter = LegacyWarehouseCodeConverter.class)
private WarehouseCode legacyWarehouse;

@Convert(disableConversion = true)
private String rawNote;
~~~

**Kết quả:** `mainWarehouse` dùng converter tự động. `legacyWarehouse` dùng converter tường minh. `rawNote` có yêu cầu không áp dụng conversion; vì là `String`, nó có thể tiếp tục sử dụng mapping basic mặc định. Với kiểu custom như `WarehouseCode`, tắt conversion mà không có mapping thay thế có thể khiến persistence thất bại.

### Bài 4: Phân biệt value object và entity

Bài toán có `Address` gồm `street`, `city`, `postalCode`, mỗi thành phần cần cột riêng trong bảng khách hàng. Có nên làm một converter biến cả `Address` thành chuỗi không?

**Gợi ý:** thường nên dùng `@Embeddable` và `@Embedded` để các cột có cấu trúc, dễ truy vấn và ràng buộc. Converter một cột phù hợp hơn nếu chủ đích rõ ràng là lưu một giá trị đơn đã được chuẩn hóa.

### Bài 5: Tư duy migration

Database đang chứa mã trạng thái `"PAID"`, `"NEW"`. Converter mới yêu cầu `"P"`, `"N"`. Nếu chỉ đổi source code converter mà không sửa dữ liệu cũ thì chuyện gì xảy ra?

**Đáp án:** converter mới có thể không nhận biết các giá trị cũ khi đọc, dẫn tới lỗi. Cần cơ chế đọc tương thích trong giai đoạn chuyển đổi hoặc migration schema/dữ liệu được kiểm soát; sau đó mới bỏ đường đọc legacy nếu phù hợp.

## 15. Ghi nhớ cốt lõi

- **`AttributeConverter<X,Y>` chuyển đổi giữa kiểu giá trị Java `X` và dạng lưu trữ `Y`** qua hai phương thức `convertToDatabaseColumn`, `convertToEntityAttribute`.
- **`@Convert(converter = ...)` chọn converter tường minh** cho một thuộc tính hoặc một vị trí ánh xạ xác định.
- **`@Converter(autoApply = true)` cho phép áp dụng tự động** lên các thuộc tính persistent có kiểu `X` phù hợp trong persistence unit đã đăng ký converter.
- **Converter tường minh có thể ghi đè lựa chọn tự động; `@Convert(disableConversion = true)` có thể tắt conversion**, nhưng chỉ thích hợp khi còn cách ánh xạ dữ liệu hợp lệ.
- **Converter không thay `@Column`, Bean Validation, migration hay transaction management.** Nó chuyển đổi giá trị, còn database lưu theo schema thực tế.
- **Không áp dụng converter tùy tiện cho `@Id`, `@Version`, quan hệ, `@Enumerated` hoặc `@Temporal`** nếu muốn bảo đảm tính di động theo đặc tả.
- **Ưu tiên value object bất biến, logic chuyển đổi ổn định và quy tắc null rõ ràng** để giảm lỗi khi dirty checking và đọc dữ liệu.
- **Khi thay đổi converter, hãy xét dữ liệu đang lưu** và đánh giá ảnh hưởng tới tất cả entity chịu tác động bởi `autoApply`.

Hiểu rõ sự khác biệt giữa chuyển đổi tường minh và tự động giúp mô hình JPA giữ được kiểu giá trị giàu ý nghĩa ở tầng Java, đồng thời quản lý nhất quán cách lưu trữ các giá trị đó trong cơ sở dữ liệu quan hệ.
