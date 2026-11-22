# Kiểm tra Document thực tế để xác minh tên trường và kiểu dữ liệu

## 1. Vì sao phải kiểm tra dữ liệu đã lưu?

Trong **Spring Data MongoDB**, class Java mô tả cách ứng dụng *muốn* ánh xạ dữ liệu, còn document BSON trong MongoDB phản ánh điều ứng dụng *thực sự đã ghi*. Hai biểu diễn không nhất thiết giống nhau hoàn toàn:

- Thuộc tính Java `customerId` có thể được lưu dưới tên `customer_id` nhờ `@Field`.
- Thuộc tính Java `id` thường được lưu trong trường MongoDB `_id`; kiểu BSON có thể là `string` hoặc `objectId` tùy cách khai báo và dữ liệu được ghi.
- `BigDecimal` có thể được lưu theo nhiều kiểu tùy mapping/converter; muốn chắc chắn lưu BSON `decimal` cần khai báo và **kiểm tra giá trị thực tế**.
- `Instant` cần được kiểm tra xem đã lưu là BSON Date hay một chuỗi ký tự; BSON Date có độ chính xác theo mili giây.
- Object lồng nhau và `List` có thể tạo document con và array, nhưng converter tùy chỉnh có thể thay đổi biểu diễn.
- Một document cũ có thể thiếu trường, chứa `null`, hoặc dùng kiểu khác với document mới.

Vì thế, quy trình kiểm tra đúng là đối chiếu **ba lớp**:

1. **Mô hình Java:** các field, record component, `@Id`, `@MongoId`, `@Field`, converter.
2. **BSON được lưu:** tên trường, kiểu, cấu trúc lồng nhau và giá trị trong collection.
3. **Đối tượng Java sau khi đọc:** dữ liệu Spring Data chuyển về có phù hợp với mong đợi hay không.

Bài học thuộc chương **Ánh xạ cơ bản**, sử dụng module **SPRING_DATA_MONGODB**: kết nối và ánh xạ document, truy cập bằng repository hoặc `MongoTemplate`, sau đó dùng truy vấn, aggregation, index, kiểm thử và công cụ chẩn đoán để phát hiện sai lệch. Phần này tập trung vào cách **xác minh hiện trạng lưu trữ**, trước khi bàn sâu đến tối ưu hoặc migration.

## 2. Tình huống: một đơn hàng với các kiểu dữ liệu khác nhau

Giả sử ứng dụng có đơn hàng gồm mã đơn, mã khách hàng, thời điểm đặt hàng, tổng tiền, trạng thái thanh toán và các dòng hàng. Mục tiêu là biết chính xác MongoDB lưu các trường ấy dưới tên nào, kiểu BSON gì.

### 2.1. Mô hình Java có ánh xạ rõ ràng

Ví dụ dùng Java 17+ và Spring Data MongoDB. Các `import` trong đoạn sau là phần cần thiết cho mô hình:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record OrderDocument(
    @MongoId(FieldType.STRING)
    String id,

    @Field("customer_id")
    String customerId,

    @Field("placed_at")
    Instant placedAt,

    @Field(value = "total_amount", targetType = FieldType.DECIMAL128)
    BigDecimal totalAmount,

    @Field("is_paid")
    Boolean paid,

    List<OrderLine> items
) {
    public record OrderLine(
        @Field("product_id")
        String productId,

        int quantity,

        @Field(value = "unit_price", targetType = FieldType.DECIMAL128)
        BigDecimal unitPrice
    ) {}
}
```

Điểm quan trọng:

- `@Document(collection = "orders")` chọn collection `orders`.
- `@MongoId(FieldType.STRING)` xác định `id` là BSON string trong trường `_id`. Cách này thể hiện rõ chủ đích dùng ID dạng chuỗi; nếu chỉ dùng `@Id String` thì trong các cấu hình/thao tác thường gặp, ID chuỗi có hình dạng ObjectId hợp lệ có thể được chuyển thành BSON `ObjectId`.
- `@Field("customer_id")` và `@Field("placed_at")` thay **tên lưu trong MongoDB**, không đổi tên field Java.
- `@Field(targetType = FieldType.DECIMAL128)` yêu cầu lưu giá trị `BigDecimal` bằng BSON Decimal128 qua mapping tương ứng.
- `List<OrderLine>` biểu diễn mảng các document con; `productId` thành `product_id` trong từng phần tử.
- `Boolean paid` cho phép thể hiện giá trị thiếu/null ở lớp Java. Trong nghiệp vụ thực tế, có thể yêu cầu cờ này không được null bằng validation và schema.

Khi repository gọi `save` hoặc `insert` qua mapping mặc định của Spring Data, document có thể chứa thêm trường metadata như `_class`. Điều đó phụ thuộc cấu hình `MappingMongoConverter`/type mapper và cách ánh xạ kiểu; không nên kết luận chỉ từ class Java.

### 2.2. Ví dụ document BSON được kỳ vọng

Trong `mongosh`, tạo dữ liệu kiểm tra trên **database dành riêng cho học tập/kiểm thử**, không dùng nguyên lệnh ghi vào môi trường thật:

```javascript
db.orders.insertOne({
  _id: "ord-1001",
  customer_id: "cust-01",
  placed_at: ISODate("2026-11-20T01:00:00Z"),
  total_amount: NumberDecimal("1250000.50"),
  is_paid: true,
  items: [
    {
      product_id: "sku-7",
      quantity: NumberInt(2),
      unit_price: NumberDecimal("625000.25")
    }
  ]
});
```

Lệnh `insertOne` của `mongosh` **ghi trực tiếp**, không đi qua converter của Spring Data. Nó hữu ích để tạo document mẫu có kiểu BSON được chỉ định minh bạch, nhưng **chưa chứng minh** repository ghi dữ liệu giống như vậy. Để xác minh mapping Java, ta cần ghi bằng repository hoặc `MongoTemplate` rồi đọc dữ liệu thô từ MongoDB.

## 3. Xem document thô và kiểu BSON bằng mongosh

### 3.1. Chọn đúng database, collection, bản ghi

Trong terminal có `mongosh` đã kết nối đến môi trường kiểm thử:

```javascript
db.getName();
db.getCollectionNames();
db.orders.findOne({ _id: "ord-1001" });
```

Cần kiểm tra database hiện tại trước khi đọc hoặc chạy các lệnh ghi. Nếu `findOne` trả về `null`, trước tiên xác minh collection, giá trị `_id` và **kiểu ID**; cùng chuỗi hiển thị nhưng BSON string khác BSON ObjectId.

Nếu ID lưu bằng ObjectId, bộ lọc cần dùng đúng kiểu:

```javascript
// Chỉ dùng khi _id thực sự là BSON ObjectId:
db.orders.findOne({ _id: ObjectId("64b000000000000000000001") });

// Nếu _id là BSON string thì truy vấn bằng string:
db.orders.findOne({ _id: "64b000000000000000000001" });
```

Hai truy vấn trên không tương đương về kiểu. Cần đối chiếu BSON thực tế; đừng tự chuyển tất cả ID thành ObjectId.

### 3.2. Hiển thị Extended JSON để nhìn rõ các kiểu BSON

Trong `mongosh`, các giá trị đặc biệt có thể hiển thị dưới dạng helper như `ISODate(...)`, `Long(...)` hoặc `Decimal128(...)`. Khi cần lưu kết quả điều tra hoặc so sánh kiểu một cách rõ ràng, dùng **Extended JSON (EJSON)**:

```javascript
const doc = db.orders.findOne({ _id: "ord-1001" });

if (doc != null) {
  print(EJSON.stringify(doc, null, 2, { relaxed: false }));
}
```

Chế độ canonical (`relaxed: false`) biểu diễn kiểu BSON bằng thẻ Extended JSON, ví dụ:

| Kiểu BSON | Dấu hiệu trong canonical Extended JSON |
| --- | --- |
| `ObjectId` | `{"$oid":"..."}` |
| `Date` | `{"$date":{"$numberLong":"..."}}` |
| `Decimal128` | `{"$numberDecimal":"1250000.50"}` |
| `Int32` | `{"$numberInt":"2"}` |
| `Int64` | `{"$numberLong":"2"}` |
| `Double` | `{"$numberDouble":"2.0"}` |
| `String` | Chuỗi JSON thông thường, ví dụ `"cust-01"` |
| `Boolean` | `true` hoặc `false` |
| `Null` | `null` |

**EJSON là cách biểu diễn để quan sát và trao đổi**, không phải cấu trúc gốc BSON đã được lưu. Trong MongoDB, thông tin kiểu nằm trong BSON; một chuỗi trông giống `2026-11-20T01:00:00Z` vẫn là BSON string nếu được ghi bằng chuỗi, không tự trở thành Date.

### 3.3. Quan sát kiểu bằng aggregation `$type`

Để xác minh nhiều trường cùng lúc, dùng `$type` trong aggregation pipeline:

```javascript
db.orders.aggregate([
  { $match: { _id: "ord-1001" } },
  {
    $project: {
      _id: 0,
      idType: { $type: "$_id" },
      customerType: { $type: "$customer_id" },
      placedAtType: { $type: "$placed_at" },
      totalType: { $type: "$total_amount" },
      paidType: { $type: "$is_paid" },
      itemsType: { $type: "$items" },
      missingFieldType: { $type: "$field_not_present" }
    }
  }
]);
```

Với document mẫu, kết quả kỳ vọng là:

```json
{
  "idType": "string",
  "customerType": "string",
  "placedAtType": "date",
  "totalType": "decimal",
  "paidType": "bool",
  "itemsType": "array",
  "missingFieldType": "missing"
}
```

`$type` ở **aggregation** báo kiểu của biểu thức tại vị trí cần kiểm tra. Khi trường không tồn tại, nó trả về `"missing"`; với giá trị BSON null, kết quả là `"null"`. Ngược lại, cú pháp `$type` dùng trong **query filter** có ngữ nghĩa khớp tài liệu và có điểm khác khi xét các phần tử của mảng.

### 3.4. Xem kiểu của các trường lồng nhau

Không nên chỉ kiểm tra `items` là array rồi kết luận mọi phần tử của mảng đều hợp lệ. Cần kiểm tra kiểu các trường bên trong:

```javascript
db.orders.aggregate([
  { $match: { _id: "ord-1001" } },
  { $unwind: "$items" },
  {
    $project: {
      _id: 0,
      productIdType: { $type: "$items.product_id" },
      quantityType: { $type: "$items.quantity" },
      unitPriceType: { $type: "$items.unit_price" }
    }
  }
]);
```

Với dữ liệu mẫu, các kiểu tương ứng là `string`, `int` và `decimal`. Nếu mảng có nhiều dòng, `$unwind` tạo kết quả cho từng dòng; một document chứa các phần tử không đồng nhất sẽ bộc lộ sự khác biệt ở kết quả.

## 4. Không nhầm tên trường Java với tên trường trong MongoDB

Spring Data ánh xạ thuộc tính Java sang BSON thông qua `MappingMongoConverter`. Trước khi tìm lỗi dữ liệu, hãy xem các nguồn xác định tên lưu:

| Khai báo Java | Tên trường BSON thường gặp | Ghi chú |
| --- | --- | --- |
| `@MongoId String id` | `_id` | Định danh MongoDB; kiểu phụ thuộc khai báo và converter |
| `@Field("customer_id") String customerId` | `customer_id` | Tên do annotation chỉ định |
| `Instant placedAt`, không có `@Field` | `placedAt` | Theo quy tắc mặc định khi không có naming strategy riêng |
| `@Field("placed_at") Instant placedAt` | `placed_at` | Tên đã tùy chỉnh |
| `List<OrderLine> items` | `items` | Array, phần tử lồng nhau vẫn được mapping |
| `@Transient String temporaryValue` | Không lưu trường này | Là transient trong Spring Data mapping |
| `@Field(value="unit_price", targetType=DECIMAL128)` | `unit_price` với BSON decimal | Xác minh trực tiếp sau khi ghi |

Ở ứng dụng có **field naming strategy**, custom converter hoặc mapping khác, kết quả có thể khác các quy tắc mặc định. Vì vậy, các bảng quy tắc chỉ là giả thuyết cần kiểm chứng qua document thực.

Ví dụ nhầm tên thường gặp:

```javascript
// Sai đối với model có @Field("customer_id"):
db.orders.find({ customerId: "cust-01" });

// Đúng với document mẫu đã lưu:
db.orders.find({ customer_id: "cust-01" });
```

Còn khi dùng `MongoTemplate` để truy vấn theo entity, Spring Data có thể ánh xạ tên **property Java** thành tên trường BSON:

```java
Query query = Query.query(
    Criteria.where("customerId").is("cust-01")
);

List<OrderDocument> orders =
    mongoTemplate.find(query, OrderDocument.class);
```

Đoạn trên giả định `mongoTemplate` và các `import` cho `Query`, `Criteria`, `List` đã sẵn có. Khi đi qua mapping của `OrderDocument`, `customerId` được chuyển thành `customer_id`. Với câu truy vấn thô trong `mongosh`, Aggregation builder dùng raw BSON hoặc lệnh trực tiếp trên driver, phải hiểu rõ các bước có/không có mapping; không nên suy rằng mọi API tự chuyển tên Java.

### Trường `_class` có cần xuất hiện?

Mặc định, nhiều cấu hình Spring Data MongoDB dùng `_class` làm type hint khi ghi document. Lý do là hỗ trợ xác định kiểu khi ánh xạ trở lại, đặc biệt với kiểu đa hình. Việc document được tạo thủ công trong `mongosh` thiếu `_class` không chứng minh ứng dụng Spring Data đã vô hiệu hóa nó.

Khi kiểm tra:

```javascript
db.orders.find(
  { _id: "ord-1001" },
  { _id: 1, _class: 1, customer_id: 1 }
);
```

Projection không trả trường `_class` nếu nó không tồn tại. Không tự xóa hoặc thêm `_class` chỉ để “đồng bộ cho đẹp”: hành vi của trường này là một phần trong cấu hình mapping, có thể ảnh hưởng tới việc đọc các kiểu khác nhau và tương thích dữ liệu cũ.

## 5. Đối chiếu tên trường và kiểu dữ liệu bằng Java, không chỉ bằng mongosh

### 5.1. Ghi qua repository rồi đọc thô bằng MongoDB Java Driver

Đây là cách kiểm tra quan trọng nhất khi muốn xác nhận **mapping từ Java sang BSON**. Ví dụ sau giả định đã có `OrderRepository` extends `MongoRepository<OrderDocument, String>` và `MongoTemplate` được cấu hình đến một database kiểm thử.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.bson.Document;
import org.bson.types.Decimal128;
import org.springframework.data.mongodb.core.MongoTemplate;

import static com.mongodb.client.model.Filters.eq;

OrderDocument order = new OrderDocument(
    "ord-2001",
    "cust-02",
    Instant.parse("2026-11-20T01:00:00Z"),
    new BigDecimal("1250000.50"),
    true,
    List.of(new OrderDocument.OrderLine(
        "sku-7", 2, new BigDecimal("625000.25")
    ))
);

orderRepository.insert(order);

// Lấy collection trực tiếp từ driver để thấy tên/kiểu BSON thực sự.
Document raw = mongoTemplate.getCollection("orders")
    .find(eq("_id", "ord-2001"))
    .first();

if (raw == null) {
    throw new IllegalStateException("Không tìm thấy document đã ghi");
}

System.out.println(raw.toJson());
System.out.println(raw.keySet());
System.out.println(raw.get("total_amount").getClass().getName());

if (!(raw.get("total_amount") instanceof Decimal128)) {
    throw new IllegalStateException("total_amount không phải Decimal128");
}
```

Với mapping như đã khai báo, cần quan sát:

- Có `_id` với BSON string `"ord-2001"` và `customer_id` với BSON string `"cust-02"`.
- Có `placed_at` với BSON Date; khi Java Driver đọc thành `Document`, giá trị thường là `java.util.Date`.
- Có `total_amount` là `org.bson.types.Decimal128`; giá trị `BigDecimal` đọc lại phải chính xác theo quy tắc tiền tệ.
- Có `items` là `List`, các phần tử là document, trong đó `unit_price` cũng là Decimal128.
- Không có field `customerId` hoặc `totalAmount`, trừ khi có cấu hình/converter khác làm thay đổi kết quả.

**Phân biệt hai đường đọc:** `mongoTemplate.findById("ord-2001", OrderDocument.class)` trả về đối tượng Java **đã được chuyển đổi**. Điều đó chứng minh việc đọc mapping hoạt động, nhưng không tự chứng minh chính xác BSON đang lưu. `getCollection("orders")` trả về collection driver và bỏ qua lớp chuyển đổi entity của Spring Data, vì vậy phù hợp để kiểm tra dữ liệu thô. Nếu dùng `Document.toJson()`, hãy nhớ dạng JSON có thể được hiển thị theo `JsonWriterSettings`; kiểm tra type của giá trị Java thô vẫn hữu ích.

### 5.2. Xác minh bằng kiểm thử tích hợp

Có thể viết kiểm thử thật trên MongoDB kiểm thử (ví dụ MongoDB trong Testcontainers) để phát hiện regression khi đổi annotation, converter hoặc phiên bản thư viện.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OrderMappingIntegrationTest {
    @Autowired MongoTemplate mongoTemplate;
    @Autowired OrderRepository orderRepository;

    @Test
    void writesExpectedFieldNamesAndBsonTypes() {
        String id = "mapping-check-001";
        OrderDocument input = new OrderDocument(
            id, "cust-02",
            Instant.parse("2026-11-20T01:00:00Z"),
            new BigDecimal("1250000.50"),
            true,
            List.of(new OrderDocument.OrderLine(
                "sku-7", 2, new BigDecimal("625000.25")
            ))
        );
        orderRepository.insert(input);

        Document raw = mongoTemplate.getCollection("orders")
            .find(eq("_id", id))
            .first();

        assertThat(raw).isNotNull();
        assertThat(raw.get("_id")).isEqualTo(id);
        assertThat(raw).containsKey("customer_id")
                       .doesNotContainKey("customerId");
        assertThat(raw.get("placed_at")).isInstanceOf(java.util.Date.class);
        assertThat(raw.get("total_amount")).isInstanceOf(Decimal128.class);

        List<?> items = raw.getList("items", Document.class);
        Document first = (Document) items.get(0);

        assertThat(first.get("product_id")).isEqualTo("sku-7");
        assertThat(first.get("quantity")).isInstanceOf(Integer.class);
        assertThat(first.get("unit_price")).isInstanceOf(Decimal128.class);

        OrderDocument roundTrip = orderRepository.findById(id)
            .orElseThrow();
        assertThat(roundTrip.totalAmount())
            .isEqualByComparingTo("1250000.50");
    }
}
```

Ví dụ giả định database kiểm thử sạch hoặc ID duy nhất, MongoDB thực đã được kết nối đến Spring Boot và có cấu hình repository thích hợp. Nếu Testcontainers được dùng, cần cấu hình container MongoDB và kết nối Spring Boot riêng; phần cấu hình môi trường không được thể hiện trong đoạn trên. Bài học này cung cấp **mẫu kiểm thử**, không khẳng định kiểm thử đã được chạy.

Lợi ích của kiểm thử: phân biệt được hai tình huống khác nhau:

- **Ghi sai nhưng đọc “đúng”:** custom converter có thể tự giải một kiểu cũ, khiến entity đọc lên có vẻ bình thường dù BSON không đúng chuẩn lưu trữ mới.
- **Ghi đúng nhưng đọc sai:** mapping constructor, enum converter hoặc tên property có thể làm object nhận giá trị null hoặc sai loại dù BSON đúng.

## 6. Các kiểu BSON dễ nhầm nhất

### 6.1. String và ObjectId ở `_id`

Trong MongoDB, `_id` có thể là nhiều kiểu BSON; không phải mọi `_id` đều là ObjectId. `@Id String id` và `@MongoId(FieldType.STRING)` thể hiện chủ đích mapping khác nhau.

Nếu chỉ kiểm tra `findById` của repository, converter có thể che khuất sự khác biệt. Với tài liệu thô, thử:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$_id" },
      count: { $sum: 1 }
    }
  }
]);
```

Collection có cả `string` và `objectId` ở `_id` thường là dấu hiệu dữ liệu được nhập từ nhiều nguồn/đời ứng dụng khác nhau. Migration phải xác định quan hệ tham chiếu, đường query và tính duy nhất trước khi đổi kiểu ID.

### 6.2. Decimal128, double, int, long và chuỗi số

Giá trị **1.250.000,50** có thể được lưu dưới nhiều BSON type:

```javascript
db.mapping_type_samples.insertMany([
  { _id: "decimal", amount: NumberDecimal("1250000.50") },
  { _id: "double",  amount: 1250000.50 },
  { _id: "string",  amount: "1250000.50" },
  { _id: "long",    amount: NumberLong("1250000") }
]);

db.mapping_type_samples.aggregate([
  {
    $project: {
      _id: 1,
      amountType: { $type: "$amount" }
    }
  }
]);
```

Các giá trị trên **không tương đương** về kiểu, độ chính xác và khả năng tính toán. Với tiền, dùng `BigDecimal` trong Java và cấu hình mapping sang Decimal128 hoặc lưu đơn vị nhỏ nhất bằng số nguyên theo quy định nghiệp vụ. Nếu giá trị vượt phạm vi biểu diễn của Decimal128, chuyển đổi có thể thất bại; không nên mặc định mọi `BigDecimal` đều lưu được.

Bộ lọc giúp tìm document lệch chuẩn:

```javascript
db.orders.find({ total_amount: { $type: "string" } });
db.orders.find({ total_amount: { $type: "double" } });
db.orders.find({ total_amount: { $type: "decimal" } });
```

Nên kiểm tra cả schema, dữ liệu không hợp lệ và số liệu báo cáo trước khi đổi kiểu hàng loạt; không chỉ viết một lệnh cập nhật tự động cho mọi chuỗi.

### 6.3. BSON Date và chuỗi thời gian

`ISODate("2026-11-20T01:00:00Z")` ghi BSON Date, còn `"2026-11-20T01:00:00Z"` ghi String. Java `Instant` thường ánh xạ sang BSON Date với cấu hình chuyển đổi tiêu chuẩn; cần xác minh khi có converter/custom codec.

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$placed_at" },
      count: { $sum: 1 }
    }
  }
]);
```

BSON Date lưu mốc thời gian UTC theo mili giây. Với `Instant` có phần nano nhỏ hơn mili giây, quá trình ghi/đọc có thể mất độ chính xác thấp hơn mili giây. Các kiểu như `LocalDateTime` không chứa múi giờ và có thêm yếu tố chuyển đổi theo cấu hình; cần quy định rõ timezone và cách biểu diễn. Đừng nhầm BSON `timestamp` chuyên dụng với BSON `date` dùng cho thời điểm nghiệp vụ.

### 6.4. Boolean, null và trường không tồn tại

Một trường có ba trạng thái quan trọng:

```javascript
// Trường tồn tại và giá trị bằng true:
db.orders.find({ is_paid: true });

// Trường tồn tại nhưng BSON type là null:
db.orders.find({ is_paid: { $type: "null" } });

// Không có trường is_paid:
db.orders.find({ is_paid: { $exists: false } });
```

Điều kiện `{ is_paid: null }` trong MongoDB thường khớp cả document có giá trị null **và** document thiếu trường. Vì vậy không dùng nó khi cần phân biệt hai trường hợp.

Nếu field Java là kiểu nguyên thủy `boolean`, giá trị mặc định `false` có thể làm mất khả năng phân biệt “chưa có dữ liệu” và “đã xác nhận là false”. Dùng `Boolean`, validation, giá trị mặc định và migration tùy ý nghĩa nghiệp vụ; không bắt buộc dùng wrapper cho mọi boolean.

### 6.5. Array, object lồng nhau, UUID và enum

- Với `List`, dữ liệu BSON là `array`; từng phần tử có thể là document, scalar hoặc null. Kiểm tra bằng `$unwind` hay kiểm tra phần tử đầu tiên nếu dữ liệu đủ ổn định.
- Với Java object lồng nhau, BSON thường là `object`/subdocument; field con có thể chịu ảnh hưởng của `@Field` và converter.
- UUID thường có biểu diễn BSON Binary với subtype và chính sách UUID representation; dữ liệu từ client/driver cũ có thể khác biểu diễn mới. Cần kiểm tra cả **kiểu binary và subtype**, không chỉ chuỗi UUID được hiển thị sau khi đọc.
- Enum thường được ghi dưới dạng tên chuỗi theo converter thông dụng, nhưng custom converter có thể dùng giá trị khác. Khi đổi tên enum, dữ liệu cũ có thể mất khả năng đọc; cần chiến lược tương thích.

## 7. Kiểm tra cả collection: phát hiện các đời dữ liệu khác nhau

Kiểm tra đúng một document là bước đầu. Nếu dữ liệu được tạo bởi nhiều phiên bản ứng dụng, cùng một field có thể mang nhiều kiểu hoặc tên khác nhau.

### 7.1. Thống kê kiểu theo từng field

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        customerIdType: { $type: "$customer_id" },
        totalType: { $type: "$total_amount" },
        placedAtType: { $type: "$placed_at" }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Đầu ra giúp phát hiện document có `total_amount` là `decimal`, `string` hoặc `missing`. Phương pháp này quét dữ liệu để tính kết quả nên có thể tốn tài nguyên trên collection lớn; nên chạy trong môi trường được phép, giới hạn dữ liệu hoặc lên kế hoạch kiểm tra phù hợp.

### 7.2. Tìm trường đặt sai tên hoặc thiếu tên mới

```javascript
// Dữ liệu còn dùng tên camelCase cũ:
db.orders.find(
  { totalAmount: { $exists: true } },
  { _id: 1, totalAmount: 1, total_amount: 1 }
);

// Dữ liệu chưa có tên mới:
db.orders.find(
  { total_amount: { $exists: false } },
  { _id: 1, total_amount: 1 }
);

// Dữ liệu chứa cùng lúc cả hai tên:
db.orders.find({
  totalAmount: { $exists: true },
  total_amount: { $exists: true }
});
```

Phân biệt rõ:

- Thiếu trường vì **đời schema cũ** và chưa migration.
- Thiếu trường vì **quy tắc ghi bỏ qua null** hay field `@Transient`.
- Thiếu trường vì **sai tên truy vấn**, sai collection hoặc dữ liệu nhập thủ công.
- Có hai trường cùng ý nghĩa nhưng khác tên dẫn đến một phía cập nhật, một phía vẫn cũ.

Khi có dữ liệu không đồng nhất, ứng dụng cần quy tắc chuyển đổi dữ liệu cũ, phiên bản schema hoặc migration được kiểm chứng. Đừng đổi hàng loạt field chỉ dựa trên mẫu một document.

### 7.3. Kiểm tra cấu trúc các dòng hàng

Với document có `items` là array, nên thống kê kiểu ở từng item:

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: {
        productIdType: { $type: "$items.product_id" },
        quantityType: { $type: "$items.quantity" },
        unitPriceType: { $type: "$items.unit_price" }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Nếu `items` bị thiếu, null hoặc là mảng rỗng, `$unwind` mặc định không phát ra dòng; vì thế kết quả chỉ phản ánh **các phần tử đã được unwind**. Muốn rà soát cả document thiếu/mảng rỗng, kiểm tra riêng với `$type` và `$size` (kèm điều kiện bảo vệ kiểu mảng khi cần).

## 8. Khi nào dùng repository, MongoTemplate và raw driver?

| Công cụ | Mục tiêu phù hợp | Điểm cần nhớ |
| --- | --- | --- |
| `MongoRepository`/`CrudRepository` | Lưu/đọc entity theo mô hình Java, kiểm tra round-trip | Kết quả đã được converter chuyển đổi |
| `MongoTemplate.find(...)` | Truy vấn entity với mapping theo property và kiểu Java | Vẫn đi qua converter khi trả entity |
| `MongoTemplate.getCollection("orders")` | Truy cập `MongoCollection<Document>` trực tiếp | Thấy cấu trúc thô; không tự mapping theo entity Java |
| `mongosh findOne`, `EJSON` | Xem tên/kiểu thực tế của BSON bằng công cụ độc lập | Phải truy cập đúng DB, collection, ID và quyền |
| `mongosh aggregate` với `$type` | Đếm/phát hiện kiểu lệch chuẩn ở nhiều bản ghi | Có thể quét dữ liệu và tốn chi phí |
| Kiểm thử tích hợp với raw BSON | Tự động phát hiện thay đổi mapping | Cần MongoDB test, dữ liệu cô lập và điều kiện kiểm tra rõ |

Một ví dụ dễ nhầm:

```java
// Truy vấn theo property Java, đi qua mapping của OrderDocument:
Query mapped = Query.query(Criteria.where("customerId").is("cust-02"));
mongoTemplate.find(mapped, OrderDocument.class);

// Truy vấn raw driver: phải dùng tên BSON thực tế:
mongoTemplate.getCollection("orders")
    .find(com.mongodb.client.model.Filters.eq("customer_id", "cust-02"));
```

Khi debug, ghi nhận chính xác API nào tạo truy vấn; đừng so sánh `Criteria.where("customerId")` trong Template với `db.orders.find({customerId: ...})` trong mongosh như thể chúng cùng sử dụng một lớp chuyển đổi.

## 9. Chẩn đoán các lỗi ánh xạ thường gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xác minh |
| --- | --- | --- |
| Repository đọc thấy entity nhưng `mongosh` không có field Java cùng tên | `@Field` hoặc naming strategy đổi tên | Xem field BSON bằng `findOne` và `$type` |
| `findById` không thấy record mong đợi | Không khớp BSON string/ObjectId, sai DB/collection/ID | `findOne` theo từng kiểu và `$type: "$_id"` |
| Tổng tiền bị đọc thành null hoặc sai số | Field thiếu/đổi tên; string/double/decimal không đúng mapping | EJSON canonical, `$type`, raw `Decimal128` |
| Thời gian lệch hoặc mất phần mili/nano | Lưu chuỗi thay vì Date; timezone/converter; giới hạn precision | `$type`, EJSON, kiểm tra round-trip `Instant` |
| `_class` xuất hiện ngoài dự kiến | Type mapper mặc định hoặc kiểu đa hình | Đọc BSON thực và cấu hình converter của ứng dụng |
| Một số document cũ lỗi, document mới đúng | Dữ liệu không đồng nhất từ các phiên bản schema | Aggregation thống kê `$type` và tìm missing |
| Thao tác với array trả kết quả lạ | Có phần tử thiếu trường hoặc khác kiểu | `$unwind` và `$type` trên trường con |
| Truy vấn chậm dù mapping đúng | Thiếu index, lọc sai tên field, sort không phù hợp | Xem `getIndexes()` và `explain("executionStats")` |
| Reactive repository hoạt động khác bản imperative | Dùng converter/config/client khác; kiểm thử chưa tương đồng | Ghi qua từng đường, đọc raw BSON, so sánh |

### Xác nhận index và query plan sau khi đã kiểm tra tên

Index trong MongoDB gắn với **tên trường BSON**:

```javascript
db.orders.getIndexes();

db.orders.createIndex({
  customer_id: 1,
  placed_at: -1
});

db.orders.find({ customer_id: "cust-02" })
         .sort({ placed_at: -1 })
         .limit(20)
         .explain("executionStats");
```

Câu lệnh tạo index chỉ để minh họa trên database kiểm thử. Một index khai báo nhầm `customerId` thay vì `customer_id` có thể tồn tại hợp lệ nhưng không hỗ trợ truy vấn mong muốn. Khi dùng annotation như `@Indexed` hoặc `@CompoundIndex`, cần xác nhận index đã thực sự được tạo; Spring Data không bảo đảm tự tạo index ở mọi cấu hình và phiên bản.

## 10. Kiểu dữ liệu còn liên quan đến aggregation và transaction

Một pipeline aggregation có thể cho kết quả sai nếu trường tiền là chuỗi ở một số document hoặc nếu thời gian là string ở một số nơi. Ví dụ thống kê kiểu trước khi cộng tiền:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$total_amount" },
      documents: { $sum: 1 }
    }
  }
]);
```

Khi chuyển sang tổng hợp doanh thu, cần dùng đúng BSON numeric type, bộ lọc trạng thái, currency và các quy tắc hoàn tiền. Đừng bỏ qua document lỗi kiểu chỉ vì pipeline chạy xong mà không báo lỗi: một số phép toán/biểu thức có cách xử lý giá trị không phải số theo ngữ nghĩa riêng.

Một thao tác ghi **một document** của MongoDB có tính nguyên tử, nhưng điều đó **không xác nhận** tên trường/kiểu đã đúng, và không bảo đảm dữ liệu ở các document khác cùng thay đổi. Khi nghiệp vụ cần transaction đa document, Spring Data MongoDB hỗ trợ `MongoTransactionManager` trong môi trường triển khai MongoDB phù hợp. Với Reactive MongoDB, dùng `ReactiveMongoTemplate`/`ReactiveMongoRepository` và `ReactiveMongoTransactionManager` khi cần transaction reactive.

Dù dùng API imperative hay reactive, quy trình kiểm chứng mapping không đổi: **ghi bằng đường ứng dụng dùng thật → đọc BSON thô → đối chiếu dữ liệu sau round-trip → kiểm tra index và truy vấn thực tế**. Reactive access hỗ trợ mô hình bất đồng bộ, không tự điều chỉnh sai lệch kiểu dữ liệu hoặc làm query nhanh hơn.

## 11. Nếu phát hiện kiểu hoặc tên không đồng nhất thì xử lý thế nào?

Trước khi migration, cần đo phạm vi và xác định dữ liệu nguồn đáng tin cậy. Một quy trình an toàn về mặt kỹ thuật:

1. **Phân loại:** xác định các kiểu BSON đang có (`string`, `decimal`, `double`, `missing`, `null`...) và tên field cũ/mới.
2. **Xác định hợp đồng chuẩn:** tên, BSON type, các trường bắt buộc, cách biểu diễn ID/tiền/ngày và phiên bản schema.
3. **Chọn quy tắc biến đổi:** ví dụ chỉ chuyển chuỗi số hợp lệ theo định dạng được chấp nhận, không tự chuyển chuỗi mơ hồ, giá trị thiếu hoặc dữ liệu sai nghiệp vụ.
4. **Bảo đảm tương thích khi triển khai:** nếu code cũ và code mới chạy đồng thời, phải quy định giai đoạn đọc được hai định dạng hoặc phối hợp thứ tự release/migration.
5. **Thử trên dữ liệu sao chép trong môi trường kiểm thử**, có thống kê trước và sau, cùng kịch bản rollback/khôi phục thích hợp.
6. **Kiểm tra lại BSON thực** và round-trip sau migration, sau đó theo dõi truy vấn chậm, lỗi chuyển đổi và kết quả nghiệp vụ.

Có thể cân nhắc collection validator với `$jsonSchema` nhằm ngăn ghi thêm kiểu sai:

```javascript
// Minh họa cấu trúc validator, cần cân nhắc dữ liệu cũ trước khi áp dụng:
{
  $jsonSchema: {
    bsonType: "object",
    required: ["customer_id", "placed_at", "total_amount"],
    properties: {
      customer_id: { bsonType: "string" },
      placed_at: { bsonType: "date" },
      total_amount: { bsonType: "decimal" },
      items: { bsonType: "array" }
    }
  }
}
```

Đây là **fragment cấu hình**, không phải lệnh chạy trực tiếp. Validator giúp kiểm soát schema ở phía MongoDB nhưng không thay thế Bean Validation, logic nghiệp vụ hoặc quá trình migration dữ liệu đã tồn tại. Mức áp dụng validator, xử lý document cũ và thứ tự cập nhật phải được thiết kế trước.

## 12. Bài thực hành tự kiểm tra

Hãy tạo database/collection riêng, sau đó thực hiện tuần tự:

1. Tạo `OrderDocument` với các annotation ở mục 2 và repository tương ứng.
2. Ghi một đơn bằng repository. Đọc lại bằng repository và ghi nhận các giá trị nhận được.
3. Dùng `mongosh` hoặc raw driver đọc chính `_id` ấy. Liệt kê tên BSON thực tế, thử `EJSON.stringify(..., {relaxed:false})`.
4. Dùng `$type` kiểm tra `_id`, `customer_id`, `placed_at`, `total_amount`, `is_paid`, `items` và `items.unit_price`.
5. Thử thêm một document mới có `total_amount` là string bằng `mongosh`; chạy aggregation đếm nhóm kiểu. Quan sát vì sao cùng một collection có thể chứa dữ liệu không đồng nhất.
6. Thử tìm theo `customerId` trong `mongosh` và theo `customerId` qua `MongoTemplate` sử dụng entity; giải thích sự khác nhau về mapping tên.
7. Viết kiểm thử tích hợp xác nhận BSON Date, Decimal128, string `_id` và round-trip `BigDecimal`.
8. Quan sát `getIndexes()`, sau đó đánh giá một truy vấn lọc/sắp xếp bằng `explain("executionStats")`; đối chiếu tên field trong index với tên BSON thực tế.

**Kết quả cần giải thích được:** vì sao class Java không đủ để kết luận về dữ liệu lưu; trường nào được đổi tên; kiểu BSON của ID, thời gian và tiền là gì; trường nào thiếu hay null; và vì sao phải kiểm tra **cả khi ghi lẫn khi đọc**.

## 13. Checklist trước khi hoàn tất một thay đổi mapping

| Câu hỏi | Cách xác minh |
| --- | --- |
| Java property map vào tên BSON nào? | Kiểm tra annotation/config; đọc document thô |
| `id` lưu BSON string hay ObjectId? | `$type` trên `_id` và raw driver |
| Tiền lưu decimal, int/long, double hay string? | EJSON canonical, `$type`, raw `Decimal128` |
| Thời gian lưu Date hay chuỗi? | `$type` trên trường thời gian; round-trip |
| Field thiếu, null hay có giá trị mặc định? | `$exists`, `$type:"null"`, kiểm thử các trường hợp |
| Mảng và subdocument có đúng cấu trúc? | `$unwind`, `$type` các field con |
| Dữ liệu cũ có cùng định dạng không? | Aggregation nhóm theo kiểu, tìm field cũ/missing |
| Converter có làm khác BSON thực không? | Ghi bằng repository/template rồi đọc raw collection |
| Index có dùng tên BSON đúng không? | `getIndexes()` và `explain("executionStats")` |
| Có kiểm thử tái hiện sau khi đổi schema? | Test tích hợp viết/read-back và kiểm tra tên + BSON type |

Một mapping đáng tin cậy không chỉ là class Java biên dịch được hay repository trả về object. Với **Spring Data MongoDB**, cần nhìn vào **document BSON thực tế**, xác minh tên trường, kiểu dữ liệu và cấu trúc lồng nhau, đồng thời kiểm tra khả năng chuyển đổi hai chiều. Khi đã có bằng chứng rõ ràng, việc thiết kế truy vấn, aggregation, index, transaction, reactive access và chẩn đoán hiệu năng mới dựa trên cấu trúc dữ liệu thật của hệ thống.

