# BigDecimal, Decimal128 và khai báo kiểu lưu tường minh

## 1. Mục tiêu bài học

Trong **Spring Data MongoDB**, đối tượng Java được ánh xạ sang document BSON và ngược lại thông qua cơ chế mapping/conversion. Với dữ liệu như **giá sản phẩm, đơn giá, chiết khấu, tiền thuế và tổng giá trị đơn hàng**, chọn sai kiểu lưu có thể làm phát sinh sai số, so sánh không đúng hoặc báo cáo aggregation khó kiểm chứng.

Bài học thuộc chương **Kiểu dữ liệu** và tiếp tục sử dụng mô hình **Mini Commerce**, gồm ba collection: `products`, `customers` và `orders`. Ta sẽ dùng `BigDecimal` trong Java, lưu dưới dạng BSON `Decimal128` và kiểm tra cả dữ liệu thực tế trong MongoDB. Kiến thức này phục vụ những phần tiếp theo về `MongoTemplate`, repository, query, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

Sau khi hoàn thành, người học có thể:

- Giải thích khác biệt giữa Java `BigDecimal`, BSON `Decimal128`, BSON `Double` và BSON `String`.
- Khai báo `@Field(targetType = FieldType.DECIMAL128)` cho các trường tiền tệ cần lưu tường minh.
- Nhận biết thay đổi về **biểu diễn BigDecimal mặc định giữa Spring Data MongoDB 4.x và 5.x**.
- Lưu, đọc, lọc, cập nhật và aggregation các trường kiểu Decimal128 qua repository hoặc `MongoTemplate`.
- Kiểm tra kiểu BSON thật bằng `$type`, `mongosh` và integration test.
- Thiết kế quy tắc precision, scale, rounding và phương án di chuyển dữ liệu đang lưu dạng chuỗi.

**Điều kiện đầu vào:** Java cơ bản, Spring Boot với `spring-boot-starter-data-mongodb`, MongoDB đang hoạt động, hiểu `@Document`, `@Id`, repository và `MongoTemplate`. Các ví dụ giả định Java 17 trở lên và MongoDB phiên bản có hỗ trợ Decimal128. Không cần chạy transaction chỉ để thực hành ánh xạ một trường tiền tệ.

## 2. Vì sao tiền tệ không nên dùng double?

Java `double` sử dụng số thực nhị phân IEEE 754. Nhiều phân số thập phân như `0.1` không có biểu diễn hữu hạn chính xác trong hệ nhị phân. Vì vậy:

```java
System.out.println(0.1 + 0.2); // 0.30000000000000004
```

Điều này có thể không đáng ngại ở phép tính đồ họa hay đo đạc mang sai số chấp nhận được, nhưng với **tiền, thuế hoặc phân chia số dư**, cần chính sách chính xác và làm tròn có kiểm soát.

Java `BigDecimal` biểu diễn các giá trị thập phân theo hệ số nguyên và scale, phù hợp với phép tính thập phân chính xác trong phạm vi được biểu diễn. Tuy nhiên **BigDecimal là kiểu Java**, không phải tên kiểu BSON của MongoDB. Khi lưu cần quyết định kiểu BSON đích.

| Kiểu | Nơi tồn tại | Đặc điểm | Rủi ro/quy tắc sử dụng |
| --- | --- | --- | --- |
| `BigDecimal` | Java | Số thập phân tùy ý theo độ dài khả dụng của Java, có `precision` và `scale` | Phải chọn quy tắc làm tròn và kiểu lưu BSON |
| `Decimal128` | MongoDB BSON / Java Driver (`org.bson.types.Decimal128`) | Số thập phân 128-bit, tối đa **34 chữ số có nghĩa** | Không biểu diễn được mọi giá trị BigDecimal; phải kiểm tra giới hạn |
| `Double` | BSON | Số thực nhị phân 64-bit | Không dùng làm nguồn sự thật cho tính toán tiền chính xác |
| `String` | BSON | Chuỗi ký tự, chẳng hạn `"129900.00"` | Lọc, sắp xếp, so sánh thường mang **ngữ nghĩa từ điển**, không phải số |
| `Int64` hoặc `Long` | BSON/Java | Số nguyên 64-bit | Có thể dùng để lưu số đơn vị nhỏ nhất nếu miền giá trị và đơn vị được xác định rõ |

**Ví dụ với cách lưu số nhỏ nhất:** nếu chính sách hệ thống quy định tất cả tiền luôn tính bằng 100 đồng hoặc bằng cent, có thể lưu kiểu số nguyên `long` kèm đơn vị rõ ràng. Bài này chọn `BigDecimal + Decimal128` vì cần hỗ trợ số thập phân và aggregation trực tiếp trong MongoDB.

## 3. BigDecimal, precision và scale

Hai khái niệm Java thường bị lẫn:

- **Precision**: số lượng chữ số có nghĩa trong hệ số biểu diễn thập phân.
- **Scale**: số chữ số ở bên phải dấu thập phân (có thể âm với một số biểu diễn).

Ví dụ:

```java
BigDecimal value = new BigDecimal("129900.00");

System.out.println(value.precision()); // 8
System.out.println(value.scale());     // 2
```

Trong Mini Commerce, quy ước ví dụ là **2 chữ số thập phân** để dễ minh họa, còn sản phẩm thực tế phải đặt scale theo tiền tệ và nghiệp vụ (ví dụ đơn vị không có phần lẻ, quy tắc thuế, tỷ giá).

Không tạo tiền từ literal `double`:

```java
// Nên:
BigDecimal safe = new BigDecimal("0.10");
BigDecimal alsoSafe = BigDecimal.valueOf(0.1);

// Tránh: lấy chính xác biểu diễn nhị phân của double.
BigDecimal unsafe = new BigDecimal(0.1);
```

`BigDecimal.valueOf(0.1)` sử dụng biểu diễn thập phân của `double` để tạo đối tượng, có hành vi khác constructor `new BigDecimal(double)`. Nhưng trong API sản xuất, truyền/nhận **chuỗi thập phân chính xác** hoặc cấu trúc đã xác thực vẫn dễ kiểm soát hơn việc đi qua `double`.

Hãy đặt chính sách scale và rounding **trước** khi ghi:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

static BigDecimal money(String value) {
    BigDecimal amount = new BigDecimal(value);
    if (amount.signum() < 0) {
        throw new IllegalArgumentException("Amount must not be negative");
    }

    // Không âm thầm làm tròn số có quá 2 chữ số sau dấu chấm.
    return amount.setScale(2, RoundingMode.UNNECESSARY);
}
```

`RoundingMode.UNNECESSARY` sẽ phát sinh `ArithmeticException` khi cần làm tròn. Nếu hệ thống có phép tính thuế/chiết khấu cho phép thêm chữ số thập phân, hãy quy định bước làm tròn cụ thể (chẳng hạn `HALF_UP` hoặc `HALF_EVEN`) theo yêu cầu nghiệp vụ và áp dụng một cách nhất quán.

Khi so sánh giá trị:

```java
BigDecimal a = new BigDecimal("129900.0");
BigDecimal b = new BigDecimal("129900.00");

System.out.println(a.compareTo(b) == 0); // true: cùng giá trị số
System.out.println(a.equals(b));         // false: khác scale
```

Đối chiếu giá tiền trong test nên dùng `compareTo` hoặc chuẩn hóa scale trước khi dùng `equals`, tùy hợp đồng dữ liệu. Không giả định mọi phép toán hoặc tất cả client đều giữ nguyên biểu diễn scale ban đầu.

## 4. Decimal128 là gì và giới hạn ở đâu?

MongoDB lưu BSON Decimal128 theo chuẩn IEEE 754 decimal floating-point 128-bit. Dạng BSON này hỗ trợ:

- Tối đa **34 chữ số có nghĩa**;
- Dải số mũ thập phân xấp xỉ **−6143 đến +6144**;
- Các giá trị đặc biệt của Decimal128 (chẳng hạn NaN và Infinity) ở tầng driver/BSON;
- So sánh và phép toán số trong MongoDB với ngữ nghĩa số thay vì so sánh ký tự.

**Giới hạn cốt lõi:** `BigDecimal` có thể biểu diễn một số quá dài hoặc có scale/số mũ ngoài khả năng Decimal128. Vì vậy, “dùng BigDecimal ở Java” **không bảo đảm mọi giá trị đều lưu vừa Decimal128**. Chuyển đổi có thể thất bại nếu không biểu diễn chính xác được giá trị.

Ví dụ với MongoDB Java Driver:

```java
import java.math.BigDecimal;
import org.bson.types.Decimal128;

BigDecimal javaValue = new BigDecimal("129900.00");
Decimal128 bsonValue = new Decimal128(javaValue);

System.out.println(bsonValue.toString());           // 129900.00
System.out.println(bsonValue.bigDecimalValue());     // 129900.00
```

`Decimal128.bigDecimalValue()` dành cho giá trị số hữu hạn có thể chuyển thành BigDecimal. Nếu đọc dữ liệu bên ngoài có NaN/Infinity, cần xử lý riêng; chúng không phải số tiền hợp lệ. Trong Mini Commerce, hãy validate số tiền hữu hạn, không âm (nếu nghiệp vụ yêu cầu) và giới hạn độ lớn trước khi ghi.

### 4.1. Dạng hiển thị không phải kiểu lưu

Cùng một giá trị số có thể được trình bày ở các dạng khác nhau:

```javascript
// mongosh:
NumberDecimal("129900.00")
```

```json
{
  "price": { "$numberDecimal": "129900.00" }
}
```

- `NumberDecimal("...")` là cú pháp sử dụng trong `mongosh`.
- `{"$numberDecimal": "..."}` là **MongoDB Extended JSON** biểu diễn kiểu Decimal128.
- `"129900.00"` chỉ là chuỗi BSON String khi đó là giá trị string thật.
- `129900.00` trong JSON thông thường không tự nói lên kiểu BSON sẽ được lưu; khi đi qua client JSON có thể phát sinh quy tắc chuyển kiểu khác.

Vì vậy, đừng kết luận kiểu dữ liệu từ việc nhìn số trên giao diện. Hãy kiểm tra bằng `$type` hoặc lấy BSON trực tiếp trong integration test.

## 5. Khác biệt giữa Spring Data MongoDB 4.x và 5.x

Đây là phần cần chú ý nhất khi đọc các bài hướng dẫn trên mạng:

| Dòng Spring Data MongoDB | Hành vi/cấu hình đối với `BigDecimal` |
| --- | --- |
| **4.x** (ví dụ 4.5) | Theo tài liệu phiên bản này, cách lưu mặc định lịch sử của `BigDecimal` là **String**, trừ khi chỉ định kiểu đích hoặc converter khác |
| **5.0 trở lên** | Theo migration guide, hạ tầng cấu hình không còn mặc định biểu diễn `BigDecimal`/`BigInteger`; cần **cấu hình representation tường minh** khi persist các kiểu này |
| Cả hai dòng | `@Field(targetType = FieldType.DECIMAL128)` diễn đạt ý định lưu Decimal128 cho **một thuộc tính** |

Không nên ghi một quy tắc “BigDecimal luôn tự động là Decimal128” hay “BigDecimal luôn tự động là String” cho mọi phiên bản. Trong dự án thực tế, hãy kiểm tra Spring Data MongoDB được Spring Boot BOM quản lý phiên bản nào, chọn chiến lược lưu thống nhất và xác nhận BSON bằng test.

**Hai cấp cấu hình khác nhau**:

1. **Cấp thuộc tính**: dùng `@Field(targetType = FieldType.DECIMAL128)` (hoặc `FieldType.STRING` khi cần tương thích dữ liệu chuỗi cũ).
2. **Cấp toàn bộ mapping**: cấu hình `MongoCustomConversions.BigDecimalRepresentation` cho những `BigDecimal` chưa có annotation hoặc khi cần chính sách mặc định chung.

Trên Spring Data MongoDB 5.x, nên định nghĩa rõ representation trong cấu hình converter theo hướng dẫn migration, đồng thời vẫn khai báo `@Field(targetType = DECIMAL128)` ở các field tiền quan trọng để hợp đồng BSON hiển thị ngay tại entity.

## 6. Khai báo kiểu lưu tường minh với @Field

### 6.1. Ví dụ Product: lưu price thành Decimal128

Mô hình `products` của Mini Commerce có `price` là giá bán hiện tại. Dùng Java `BigDecimal` kết hợp annotation:

```java
package com.example.minicommerce.domain;

import java.math.BigDecimal;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document(collection = "products")
public class Product {
    @Id
    private String id;

    private String sku;
    private String name;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal price;

    private int stock;

    public Product() {}

    public Product(String id, String sku, String name,
                   BigDecimal price, int stock) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.stock = stock;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }

    public int getStock() { return stock; }
    public void setStock(int stock) { this.stock = stock; }
}
```

Giải thích:

- `@Document(collection = "products")`: entity ánh xạ tới collection.
- `@Id`: thuộc tính `id` ánh xạ tới `_id`.
- `price`: **Java dùng BigDecimal**, BSON mong đợi là **Decimal128** nhờ `@Field(targetType = FieldType.DECIMAL128)`.
- `stock`: số lượng tồn kho dạng số nguyên, không cần Decimal128.

Để ví dụ không phụ thuộc chuyển đổi chuỗi hexadecimal sang ObjectId, ta sử dụng ID như `"prod-001"`. Nếu dự án dùng `ObjectId`, hãy nhất quán kiểu ID và tham chiếu giữa các collection.

### 6.2. Ánh xạ tên field và kiểu lưu cùng lúc

Nếu hệ thống đã quy định BSON dùng `unit_price` trong khi Java dùng `unitPrice`:

```java
@Field(name = "unit_price", targetType = FieldType.DECIMAL128)
private BigDecimal unitPrice;
```

`@Field` xử lý **cả tên lưu** và **kiểu đích**. Điều này quan trọng khi viết query/update, vì Spring Data mapping có thể chuyển tên thuộc tính Java thành tên BSON tương ứng.

### 6.3. OrderLine: đóng băng giá khi tạo đơn

Giá `Product.price` có thể đổi theo chương trình khuyến mại. `OrderLine.unitPrice` phải giữ giá chốt tại lúc đặt; `lineTotal` bằng `quantity × unitPrice`.

```java
import java.math.BigDecimal;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public class OrderLine {
    private String productId;
    private String sku;
    private int quantity;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal unitPrice;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal lineTotal;

    // Constructor/getter/setter phù hợp với mapping của dự án.
}
```

Trong `Order`, cũng nên khai báo tường minh `totalAmount`:

```java
@Document(collection = "orders")
public class Order {
    @Id
    private String id;

    private String customerId;
    private List<OrderLine> lines;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal totalAmount;

    // Các trường trạng thái, thời gian và constructor/getter/setter.
}
```

Đây là đoạn mô tả các field cốt lõi, cần import `List`, `BigDecimal`, `Id`, `Document`, `Field`, `FieldType` và bổ sung implementation khi ghép thành source thực tế.

**Quy tắc nghiệp vụ:** server tải `Product.price` từ cơ sở dữ liệu, chuẩn hóa scale theo chính sách, tính `lineTotal` và `totalAmount` bằng BigDecimal. Không tin cậy giá hay tổng tiền do client gửi. Transaction khi đặt hàng có thể bảo đảm tạo đơn và trừ tồn nhất quán, nhưng transaction **không tự sửa lỗi làm tròn hoặc sai kiểu số**.

## 7. Cấu hình representation ở cấp converter

`@Field(targetType = ...)` thể hiện hợp đồng tại từng thuộc tính. Với Spring Data MongoDB 5.x, tài liệu migration yêu cầu cấu hình default `BigDecimalRepresentation` khi persist những `BigDecimal` cần xử lý theo mặc định.

Nếu ứng dụng **đã sử dụng** `AbstractMongoClientConfiguration`, có thể cấu hình trong lớp đó:

```java
import org.springframework.data.mongodb.config.AbstractMongoClientConfiguration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions.MongoConverterConfigurationAdapter;

// Đặt trong lớp extends AbstractMongoClientConfiguration:
@Override
protected void configureConverters(
        MongoConverterConfigurationAdapter adapter) {
    adapter.bigDecimal(
        MongoCustomConversions.BigDecimalRepresentation.DECIMAL128);
}
```

Giải thích:

- `BigDecimalRepresentation.DECIMAL128`: đặt Decimal128 làm cách biểu diễn mặc định trong cấu hình converter.
- Có thể chọn `BigDecimalRepresentation.STRING` để giữ định dạng chuỗi của ứng dụng cũ trong giai đoạn tương thích/migration, nhưng đây là lựa chọn cần cân nhắc vì truy vấn số.
- Nếu muốn hỗ trợ nhiều định dạng và chỉ định riêng theo field, tham khảo `MongoCustomConversions.create(config -> config.bigDecimal(...))` của phiên bản đang dùng; thứ tự các representation được đăng ký ảnh hưởng định dạng mặc định.
- Không thêm hai cấu hình `MongoCustomConversions` chồng chéo hoặc thay đổi chiến lược lưu khi chưa đánh giá dữ liệu hiện có.

**Đừng sao chép đoạn override vào một lớp `@Configuration` bất kỳ**: `configureConverters(...)` là extension point của `AbstractMongoClientConfiguration`. Nếu dùng hoàn toàn Spring Boot auto-configuration, hãy đăng ký một bean `MongoCustomConversions` theo API của phiên bản đang dùng, hoặc một customizer/bean conversion phù hợp rồi kiểm thử bean mapping cuối cùng. Tránh tự dựng một `MongoTemplate` thứ hai chỉ để đặt Decimal128.

### 7.1. Ví dụ cấu hình global bằng MongoCustomConversions

Trong ứng dụng Spring Boot dùng auto-configuration (không kế thừa lớp cấu hình ở trên), có thể đặt bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration
public class DecimalMappingConfiguration {
    @Bean
    MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(config ->
            config.bigDecimal(
                MongoCustomConversions.BigDecimalRepresentation.DECIMAL128));
    }
}
```

Đây là ví dụ dành cho những phiên bản có factory method `MongoCustomConversions.create(...)`. Nếu dự án đã đăng ký custom conversions khác (enum, mã hóa, value object...), cần **gộp** cấu hình theo API phiên bản đó để không làm mất các converter quan trọng. Xác minh bằng integration test rằng `MongoTemplate` thực tế dùng converter mong đợi.

## 8. Kiểm tra BSON thật khi insert qua MongoTemplate

Khai báo repository:

```java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {
}
```

Thử insert sản phẩm trong môi trường test:

```java
Product sample = new Product(
    "prod-001",
    "LAP-001",
    "Bàn phím cơ Mini",
    new BigDecimal("129900.00"),
    20
);

mongoTemplate.insert(sample);
```

Trong `mongosh`:

```javascript
use mini_commerce

db.products.findOne(
  { _id: "prod-001" },
  { sku: 1, name: 1, price: 1, stock: 1 }
)

db.products.aggregate([
  { $match: { _id: "prod-001" } },
  { $project: { _id: 0, priceType: { $type: "$price" }, price: 1 } }
])
```

Với cấu hình thành công, `priceType` phải là `"decimal"`. Giá `price` có thể hiển thị dưới dạng `Decimal128("129900.00")` hoặc `NumberDecimal("129900.00")` tùy công cụ. Dùng `$type` để xác minh chính xác.

MongoDB Extended JSON có thể biểu diễn một document như sau:

```json
{
  "_id": "prod-001",
  "sku": "LAP-001",
  "name": "Bàn phím cơ Mini",
  "price": { "$numberDecimal": "129900.00" },
  "stock": 20
}
```

Khi kiểm tra raw BSON với MongoDB driver:

```java
import org.bson.Document;
import org.bson.types.Decimal128;

Document stored = mongoTemplate.getCollection("products")
    .find(new Document("_id", "prod-001"))
    .first();

if (stored == null) {
    throw new IllegalStateException("Sample product missing");
}

Object rawPrice = stored.get("price");
if (!(rawPrice instanceof Decimal128 decimal128)) {
    throw new IllegalStateException(
        "Expected BSON Decimal128 but found: " + rawPrice);
}

BigDecimal result = decimal128.bigDecimalValue();
System.out.println(result); // 129900.00
```

Đây là chứng cứ mạnh hơn việc chỉ gọi `repository.findById(...)`: repository có thể **đọc chuyển đổi** từ các BSON type khác nhau, còn raw BSON chỉ ra loại đã được persist.

## 9. Query và cập nhật với Decimal128

### 9.1. Lọc giá với MongoTemplate

Ví dụ tìm sản phẩm từ `100000.00` đến dưới `200000.00`:

```java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("price")
        .gte(new BigDecimal("100000.00"))
        .lt(new BigDecimal("200000.00"))
);

List<Product> found = mongoTemplate.find(query, Product.class);
```

Khi truyền `Product.class`, Spring Data sử dụng metadata mapping của entity để chuyển filter sang kiểu BSON thích hợp. Vẫn cần test trên dữ liệu thật, đặc biệt khi collection chứa **trộn String và Decimal128** từ các phiên bản cũ.

Lọc trực tiếp trong `mongosh` bằng giá trị Decimal128:

```javascript
db.products.find({
  price: {
    $gte: NumberDecimal("100000.00"),
    $lt: NumberDecimal("200000.00")
  }
})
```

**Đừng dùng chuỗi** `"100000.00"` làm ngưỡng so sánh trong truy vấn raw MongoDB cho trường Decimal128. Đây là một kiểu BSON khác và query có thể không cho kết quả mong muốn.

### 9.2. Cập nhật giá đúng kiểu

```java
import org.springframework.data.mongodb.core.query.Update;

Query filter = Query.query(
    Criteria.where("_id").is("prod-001"));

Update change = new Update()
    .set("price", new BigDecimal("139900.00"));

mongoTemplate.updateFirst(filter, change, Product.class);
```

Đối với update qua mapped entity class, Spring Data có thể áp dụng conversion dựa trên `@Field`. Kiểm tra giá trị raw sau cập nhật để bảo đảm `price` tiếp tục là `Decimal128`. Không pha trộn với thao tác raw driver ghi `double` hoặc `String` vào cùng field.

Trong `mongosh`, khi cần chỉnh sửa trực tiếp:

```javascript
db.products.updateOne(
  { _id: "prod-001" },
  { $set: { price: NumberDecimal("139900.00") } }
)
```

Nếu cập nhật đồng thời giá và tồn kho theo phiên bản sản phẩm, cân nhắc optimistic locking hoặc cập nhật có điều kiện. Kiểu Decimal128 không tự ngăn xung đột ghi.

### 9.3. Index và thứ tự sắp xếp

Ví dụ màn hình lọc sản phẩm đang bán theo danh mục rồi sắp xếp giá:

```javascript
db.products.createIndex({ active: 1, category: 1, price: 1 })

db.products
  .find({
    active: true,
    category: "phu-kien",
    price: { $gte: NumberDecimal("100000.00") }
  })
  .sort({ price: 1 })
  .explain("executionStats")
```

Index cần được đánh giá theo query shape thật. So sánh `totalKeysExamined`, `totalDocsExamined` và `nReturned`, không chỉ nhìn kết quả sắp xếp đúng. Nếu trường `price` chứa cả String và Decimal128, thứ tự index và filter theo **BSON type** có thể tạo hành vi bất ngờ. Chuẩn hóa kiểu dữ liệu trước khi tối ưu query.

## 10. Aggregation với Decimal128 trong đơn hàng

Mô hình `orders` chứa các dòng hàng được nhúng. Giả sử:

```json
{
  "_id": "order-001",
  "customerId": "customer-001",
  "status": "PLACED",
  "lines": [
    {
      "productId": "prod-001",
      "sku": "LAP-001",
      "quantity": 2,
      "unitPrice": { "$numberDecimal": "129900.00" },
      "lineTotal": { "$numberDecimal": "259800.00" }
    }
  ],
  "totalAmount": { "$numberDecimal": "259800.00" }
}
```

Để thống kê doanh thu của đơn `PLACED` trong MongoDB:

```javascript
db.orders.aggregate([
  { $match: { status: "PLACED" } },
  {
    $group: {
      _id: null,
      orderCount: { $sum: 1 },
      revenue: { $sum: "$totalAmount" }
    }
  }
])
```

Nếu `totalAmount` đều lưu Decimal128, tổng doanh thu mang ngữ nghĩa số thập phân. Không nên mặc nhiên tính doanh thu bằng `double` trong Java hoặc làm tròn ở nhiều nơi. Nếu có dữ liệu String cũ, `$sum` không hoạt động như mong đợi trên chuỗi và có thể bỏ qua giá trị không phải số; phải chuẩn hóa trước khi báo cáo.

Báo cáo sản phẩm bán chạy:

```javascript
db.orders.aggregate([
  { $match: { status: "PLACED" } },
  { $unwind: "$lines" },
  {
    $group: {
      _id: "$lines.productId",
      unitsSold: { $sum: "$lines.quantity" },
      revenue: { $sum: "$lines.lineTotal" }
    }
  },
  { $sort: { revenue: -1 } },
  { $limit: 10 }
])
```

Với `MongoTemplate`, sử dụng `Aggregation.match`, `unwind`, `group`, `sort` và `limit` tương ứng. Khi phân tích dữ liệu tài chính thật, phải quyết định rõ cách xử lý đơn hủy, hoàn tiền, các đơn vị tiền tệ và giao dịch đã phát sinh; chỉ lọc `status = "PLACED"` là một quy tắc thực hành đơn giản.

## 11. Dữ liệu cũ: String, Double và Decimal128 bị trộn

Một collection có thể chứa nhiều phiên bản representation sau thời gian nâng cấp:

```javascript
// Ba document đều có giá hiển thị gần giống nhau
{ _id: "p1", price: "129900.00" }
{ _id: "p2", price: 129900.0 }              // BSON Double
{ _id: "p3", price: NumberDecimal("129900.00") }
```

Nhìn bằng mắt, chúng có vẻ cùng một số. Trong MongoDB, `price` mang ba **BSON type** khác nhau, ảnh hưởng đến comparison, sorting, aggregation và conversion.

### 11.1. Thống kê BSON type trước khi sửa dữ liệu

```javascript
db.products.aggregate([
  {
    $group: {
      _id: { $type: "$price" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
```

Những kết quả có thể gặp:

| `_id` của nhóm | Ý nghĩa |
| --- | --- |
| `"decimal"` | BSON Decimal128 |
| `"string"` | BSON String |
| `"double"` | BSON Double |
| `"missing"` | Document không có field `price` |
| `"null"` | Field tồn tại nhưng là BSON Null |

Trước migration, cần biết số lượng mỗi nhóm, giá trị bất thường (rỗng, ký tự không phải số, quá giới hạn) và dependency của các ứng dụng khác. Không vội đổi field type nếu một service cũ đang kỳ vọng chuỗi.

### 11.2. Kiểm tra chuỗi có chuyển được sang Decimal128

Có thể dùng `$convert` với `onError` và `onNull` để **phát hiện dữ liệu lỗi mà không lập tức ghi**:

```javascript
db.products.aggregate([
  { $match: { price: { $type: "string" } } },
  {
    $project: {
      price: 1,
      convertedPrice: {
        $convert: {
          input: "$price",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $match: { convertedPrice: null } }
])
```

Pipeline trả các document chuỗi không chuyển được thành Decimal128. Một số giá trị hợp lệ theo cú pháp nhưng vượt giới hạn Decimal128 vẫn có thể không chuyển được. Đối với dữ liệu liên quan tiền, cần thêm kiểm tra miền giá trị và scale theo chính sách nghiệp vụ.

### 11.3. Quy trình migration an toàn

1. **Kiểm kê** dữ liệu bằng `$type` và thống kê các field tài chính ở `products`, `orders`, bao gồm `lines.unitPrice` và `lines.lineTotal`.
2. **Sao lưu hoặc có cơ chế rollback** được kiểm tra. Xác định code nào đang đọc/ghi dạng chuỗi.
3. **Validate trước**: cú pháp số, precision, scale, miền giá trị, document thiếu field, dữ liệu Double đã mất độ chính xác.
4. **Thử trên dữ liệu staging** với số lượng và phân bố đại diện; đối chiếu tổng doanh thu trước/sau bằng quy tắc chuyển đổi rõ ràng.
5. **Đổi theo lô** và theo dõi lỗi. Ví dụ các trường String đã được kiểm tra có thể chuyển bằng aggregation pipeline update.
6. **Triển khai reader/writer tương thích** theo chiến lược chuyển tiếp, rồi mới chuyển toàn bộ sang Decimal128; tránh chạy các phiên bản code ghi hai kiểu trong cùng thời điểm.
7. **Kiểm chứng** `$type`, repository, query khoảng giá, index và báo cáo aggregation sau migration. Chỉ xóa logic tương thích khi dữ liệu đã thống nhất.

Ví dụ thao tác chuyển **sau khi đã xác minh mọi chuỗi trong tập mục tiêu hợp lệ**, chỉ chạy trong môi trường/lô được kiểm soát:

```javascript
db.products.updateMany(
  { price: { $type: "string" } },
  [
    {
      $set: { price: { $toDecimal: "$price" } }
    }
  ]
)
```

**Cảnh báo:** `$toDecimal` có thể lỗi khi chuỗi không hợp lệ hoặc không thể chuyển. `updateMany` trên nhiều document không tự biến toàn bộ quá trình thành một giao dịch nguyên tử; cần backup, giám sát và chiến lược batch/retry. Không chạy ví dụ trực tiếp trên production khi chưa kiểm kê và có kế hoạch phục hồi.

Với nguồn dữ liệu đã lưu là Double, giá trị gốc có thể đã bị làm tròn trước khi ghi; chuyển sang Decimal128 **không khôi phục độ chính xác đã mất**. Trường hợp này cần đối chiếu sổ sách/nguồn nghiệp vụ, không chỉ ép kiểu tự động.

## 12. Kiểm thử ánh xạ và dữ liệu tài chính

Test chỉ đối chiếu `product.getPrice().compareTo(expected) == 0` chưa chứng minh **BSON thật** là Decimal128. Nên có ít nhất một integration test với MongoDB thật hoặc Testcontainers:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class ProductDecimalMappingTest {
    @Autowired
    MongoTemplate mongoTemplate;

    @Test
    void storesDecimal128AndReadsBigDecimal() {
        String id = "decimal-mapping-test";
        var raw = mongoTemplate.getCollection("products");

        raw.deleteOne(new Document("_id", id));
        try {
            Product product = new Product(
                id, "DEC-TEST", "Sản phẩm thử nghiệm",
                new BigDecimal("129900.00"), 3);

            mongoTemplate.insert(product);

            Document bson = raw.find(new Document("_id", id)).first();
            assertNotNull(bson);
            assertInstanceOf(Decimal128.class, bson.get("price"));
            assertEquals(
                0,
                new BigDecimal("129900.00").compareTo(
                    ((Decimal128) bson.get("price")).bigDecimalValue()));

            Product loaded = mongoTemplate.findById(id, Product.class);
            assertNotNull(loaded);
            assertEquals(
                0,
                new BigDecimal("129900.00").compareTo(loaded.getPrice()));
        } finally {
            raw.deleteOne(new Document("_id", id));
        }
    }
}
```

Đoạn test giả định `Product` ở mục 6 đã được import đúng package, Spring context có MongoDB kết nối được, và collection test được cô lập. Chỉ xóa fixture có ID cố định trong **database thử nghiệm riêng**; không sao chép cơ chế dọn dẹp sang production.

### 12.1. Những test bổ sung nên có

| Trường hợp | Điều cần kiểm tra |
| --- | --- |
| `new BigDecimal("0.10")` | Lưu thành BSON Decimal128 và đọc đúng giá trị |
| `new BigDecimal("129900.00")` | Đọc/ghi đúng giá; test scale theo hợp đồng nếu cần |
| Input quá 2 chữ số thập phân | Bị từ chối hoặc làm tròn theo chính sách đã công bố |
| Số có hơn 34 chữ số có nghĩa | Được phát hiện và báo lỗi, không âm thầm mất dữ liệu |
| Số âm, null, giá bằng 0 | Có validate đúng nghiệp vụ |
| `@Field(targetType = DECIMAL128)` | BSON thực tế là Decimal128, không phải String/Double |
| Query giá theo khoảng | Trả đúng sản phẩm, filter dùng giá trị số |
| `MongoTemplate.updateFirst` | Sau khi cập nhật giá vẫn giữ BSON type Decimal128 |
| Aggregation tổng `totalAmount` | Tổng tiền đúng với các đơn hợp lệ và không chứa String |
| Dữ liệu cũ chứa String hoặc Double | Có migration/test tương thích rõ ràng |
| Đồng thời cập nhật giá/tồn kho | Cơ chế concurrency/transaction phù hợp, không liên quan việc chọn Decimal128 |

Nếu dùng `ReactiveMongoRepository` hoặc `ReactiveMongoTemplate`, mapping vẫn cần kiểu đích đúng. Test có thể dùng Reactor `StepVerifier`, nhưng vẫn phải xác minh BSON raw trong database. Reactive access không thay đổi precision của Decimal128 và không tự động sửa kiểu dữ liệu legacy.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Giá được lưu thành chuỗi | Spring Data 4.x dùng mặc định cũ hoặc cấu hình representation là STRING | Khai báo `@Field(targetType = DECIMAL128)`, rà soát converter và test BSON |
| Nâng cấp lên 5.x rồi conversion lỗi | Không đăng ký `BigDecimalRepresentation` phù hợp | Cấu hình representation tường minh theo migration guide |
| Lọc `price >= 100` trả thiếu dữ liệu | Collection trộn String/Decimal128 hoặc truyền ngưỡng sai kiểu | Kiểm kê `$type`, chuẩn hóa BSON và dùng ngưỡng Decimal128 |
| Tổng aggregation sai | `$sum` gặp String/giá trị thiếu hoặc quy tắc trạng thái sai | Chuẩn hóa dữ liệu và filter theo trạng thái nghiệp vụ |
| Giá bị lệch khi đọc/ghi | Có bước chuyển qua `double` hoặc client JSON làm mất precision | Dùng BigDecimal từ chuỗi, Decimal128 trong BSON, test end-to-end |
| Ghi số lớn bị lỗi | BigDecimal vượt precision/exponent Decimal128 | Validate trước, cân nhắc mô hình lưu khác nếu yêu cầu thật sự vượt giới hạn |
| So sánh hai BigDecimal bằng `equals` thất bại | Cùng giá trị nhưng khác scale | Chuẩn hóa scale hoặc dùng `compareTo` |
| Ghi giá thành công nhưng update bị đổi BSON type | Một đường ghi dùng raw driver/chuỗi/Double | Quy định thống nhất đường ghi và kiểm tra BSON sau update |
| `NumberDecimal(129900.00)` mất chữ số mong muốn | Truyền number qua JavaScript trước khi tạo decimal | Dùng `NumberDecimal("129900.00")` với chuỗi |
| Báo cáo Decimal128 không đúng với tiền tệ | Không phân biệt đơn vị tiền, tỷ giá hoặc quy tắc rounding | Thiết kế rõ currency, scale và phép quy đổi |

## 14. Bài tập ứng dụng

**Bài tập 1 — Lưu giá đúng kiểu.** Tạo `Product` có `price: BigDecimal`, gắn `@Field(targetType = FieldType.DECIMAL128)`. Ghi sản phẩm `LAP-001` giá `129900.00` và kiểm tra `$type` trả `"decimal"`.

**Bài tập 2 — Truy vấn khoảng giá.** Thêm ba sản phẩm có giá `99000.00`, `129900.00` và `219900.00`. Dùng `MongoTemplate` lọc sản phẩm trong `[100000.00, 200000.00)`; xác nhận chỉ sản phẩm giá `129900.00` được chọn. Kiểm tra raw `mongosh` dùng `NumberDecimal("...")`.

**Bài tập 3 — Đơn hàng và aggregation.** Tạo một `Order` có hai dòng hàng, server tự tính `lineTotal` và `totalAmount` bằng BigDecimal. Ghi BSON Decimal128, sau đó dùng aggregation `$sum` để tính doanh thu. So sánh với tổng được tính trong Java.

**Bài tập 4 — Nâng cấp kiểu lưu.** Trong database test, tạo các document có `price` kiểu String, Double và Decimal128. Thống kê `$type`, kiểm tra lỗi chuyển đổi, chuyển dữ liệu String hợp lệ sang Decimal128 theo lô và chạy lại truy vấn/tổng doanh thu. Mô tả rủi ro mất chính xác từ Double.

**Bài tập 5 — Nâng cấp framework.** Xác định dự án dùng Spring Data MongoDB 4.x hay 5.x; ghi lại lựa chọn `BigDecimalRepresentation` đang áp dụng, cập nhật integration test để phát hiện thay đổi BSON type khi nâng cấp.

Người học hoàn thành khi trả lời được:

1. Vì sao `BigDecimal` trong Java vẫn cần chọn kiểu BSON đích?
2. Khi nào `Decimal128` vượt quá giới hạn so với `BigDecimal`?
3. `@Field(targetType = FieldType.DECIMAL128)` và cấu hình `MongoCustomConversions` khác nhau ở cấp độ nào?
4. Điều gì thay đổi ở Spring Data MongoDB 5.x so với 4.x về representation mặc định?
5. Vì sao truy vấn, index và aggregation trên trường `price` có thể sai khi BSON chứa cả String lẫn Decimal128?
6. Kiểm thử thế nào để xác nhận **kiểu lưu thực tế**, không chỉ giá trị Java đọc ra?

**Kết quả mong đợi:** người học lưu được `BigDecimal` thành Decimal128 một cách tường minh, kiểm chứng dữ liệu BSON thực tế, kiểm soát precision/scale và chuẩn bị migration an toàn khi dữ liệu cũ có kiểu lưu khác. Đây là nền tảng đáng tin cậy cho thiết kế truy vấn, aggregation, index, transaction, reactive access và kiểm thử dữ liệu tài chính của Mini Commerce.

## Tài liệu tham khảo

- [Spring Data MongoDB 4.5 — Custom Conversions](https://docs.spring.io/spring-data/data-mongodb/reference/4.5/mongodb/mapping/custom-conversions.html): hành vi lưu BigDecimal lịch sử và cách khai báo `@Field(targetType = DECIMAL128)`.
- [Spring Data MongoDB 5.1 — Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): biểu diễn tường minh, `MongoCustomConversions` và định dạng số lớn.
- [Spring Data MongoDB — Migration Guide 4.x to 5.x](https://docs.spring.io/spring-data/mongodb/reference/migration-guide/migration-guide-4.x-to-5.x.html): thay đổi BigDecimal/BigInteger conversions khi nâng cấp.
- [MongoDB — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): đặc tính của Decimal128 và các BSON type.
- [MongoDB — Decimal128 in mongosh](https://www.mongodb.com/docs/mongodb-shell/reference/data-types/): cách tạo giá trị Decimal128 đúng kiểu trong shell.
