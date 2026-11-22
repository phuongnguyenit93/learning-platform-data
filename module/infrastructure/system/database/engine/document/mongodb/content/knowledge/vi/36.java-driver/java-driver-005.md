# Ánh xạ Document, POJO codec và quy ước tên trường trong MongoDB Java Driver

## Mục tiêu bài học

Khi làm việc với MongoDB bằng **Java Sync Driver**, ứng dụng phải chuyển qua lại giữa **BSON** (định dạng tài liệu lưu trong MongoDB) và dữ liệu mà Java hiểu được. Hai cách biểu diễn thường gặp là:

- **`Document`**: cấu trúc linh hoạt kiểu map, thích hợp truy vấn động, đọc dữ liệu chưa biết schema, thử nghiệm và thao tác với các trường thay đổi theo từng bản ghi.
- **POJO (Plain Old Java Object)**: class Java có các thuộc tính kiểu rõ ràng, thích hợp với domain model, compile-time checks và API nghiệp vụ ổn định.

Để lưu/đọc POJO, Java Driver cần **codec** phù hợp. `CodecRegistry` tìm codec cho từng kiểu, còn `PojoCodecProvider` tạo codec dựa trên thông tin class, conventions, getters/setters và các annotation như `@BsonId`, `@BsonProperty`, `@BsonIgnore`, `@BsonCreator`.

Điểm nhiều người mắc lỗi là **tên thuộc tính Java không mặc nhiên bằng tên field BSON trong database**. Ví dụ `customerName` có thể được lưu dưới khóa `customer_name`, và khi viết `Filters.eq(...)` hay `Updates.set(...)` bằng chuỗi, ta thường phải dùng **tên BSON**, không phải tên property Java.

Bài thuộc **Database Engine Document MongoDB → Java Driver → Ánh xạ Document, POJO codec và quy ước tên trường**.

Sau bài học, bạn có thể:

1. Giải thích pipeline chuyển đổi `Java object ↔ Codec ↔ BSON ↔ MongoDB`.
2. Dùng `Document` để tạo, đọc, cập nhật, duyệt các document lồng nhau.
3. Phân biệt `Document`, `BsonDocument`, POJO, Java record và DTO.
4. Cấu hình `PojoCodecProvider` cùng **default codec registry** cho `MongoCollection<YourPojo>`.
5. Sử dụng annotations để ánh xạ `_id` và tên field BSON riêng.
6. Hiểu JavaBean conventions, constructors, getter/setter, private fields và `@BsonCreator`.
7. Thiết kế quy ước `camelCase`/`snake_case` nhất quán qua POJO, query, index, JSON API.
8. Xử lý kiểu BSON `ObjectId`, số nguyên, `Decimal128`, ngày giờ, UUID, enum, nested arrays và map.
9. Nhận diện sự khác nhau giữa field **missing**, **null** và **default value**.
10. Bảo vệ dữ liệu khi đổi tên field, thay đổi schema, thêm/xóa property và dùng replace updates.
11. Debug `CodecConfigurationException`, codec registry order, naming mismatch và vấn đề dữ liệu legacy.
12. Viết integration tests round-trip, kiểm tra chính xác dữ liệu đã lưu, không chỉ kiểm tra POJO ở phía Java.

> **Quy tắc quan trọng:** POJO là một **cách biểu diễn**, không phải một schema tuyệt đối do MongoDB tự cưỡng chế. Nếu collection chứa dữ liệu không thống nhất hoặc query dùng sai tên BSON, việc ánh xạ có thể lỗi hoặc trả kết quả không như mong đợi.

---

## 1. Từ Java đến MongoDB: đường đi của dữ liệu

Giả sử Java có một đối tượng:

~~~java
Customer customer = new Customer();
customer.setFullName("Nguyễn An");
customer.setLoyaltyPoints(120);
~~~

MongoDB có thể lưu document tương ứng:

~~~javascript
{
  _id: ObjectId("6914bb000000000000000001"),
  full_name: "Nguyễn An",
  loyalty_points: 120
}
~~~

Đường đi:

~~~text
  Java code
      |
      v
  Customer POJO
      |
      v
  CodecRegistry -> Codec<Customer>
      |
      v
  BSON encoding
      |
      v
  MongoDB: _id, full_name, loyalty_points

  MongoDB BSON
      |
      v
  BSON decoding + Codec<Customer>
      |
      v
  Customer POJO
~~~

### 1.1. Encoding và decoding

- **Encoding/serialization**: chuyển Java object thành BSON để gửi qua driver hoặc lưu trong database.
- **Decoding/deserialization**: đọc BSON và xây lại Java object.
- **Round-trip**: encode rồi decode và kiểm tra object/result đúng theo contract.

### 1.2. Codec là gì?

`Codec<T>` quy định cách chuyển giữa BSON và kiểu Java `T`. Driver có codecs cho nhiều kiểu cơ bản như `String`, `Integer`, `Date`, `ObjectId`, `Document`, `List` và những kiểu BSON đã được hỗ trợ.

Một POJO domain `Customer` không mặc nhiên có codec chỉ vì class nằm trong project. Cần register `PojoCodecProvider`, cấu hình model hoặc custom codec phù hợp.

### 1.3. `CodecRegistry` hoạt động như thế nào?

Registry là tập codecs/providers; khi driver cần codec cho `Customer.class`, nó tìm theo thứ tự các registries/providers. Nếu không tìm được codec phù hợp, có thể gặp:

~~~text
org.bson.codecs.configuration.CodecConfigurationException:
Can't find a codec for CodecCacheKey{clazz=...}
~~~

Thứ tự registration có ý nghĩa vì codec/provider đầu tiên phù hợp sẽ được dùng.

---

## 2. Dùng `Document` trước khi dùng POJO

`org.bson.Document` là kiểu document dạng key-value có thể chứa số, chuỗi, ngày, nested documents, danh sách và các giá trị BSON hỗ trợ.

### 2.1. Tạo document bằng Java

~~~java
import org.bson.Document;
import org.bson.types.ObjectId;

Document customer = new Document()
    .append("_id", new ObjectId())
    .append("full_name", "Nguyễn An")
    .append("loyalty_points", 120)
    .append("active", true);

System.out.println(customer.toJson());
~~~

Trong MongoDB, keys thật là `_id`, `full_name`, `loyalty_points`, `active`.

### 2.2. Tạo collection kiểu `Document`

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

String uri = System.getenv("MONGODB_URI");

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase db =
        client.getDatabase("java_codec_lab");

    MongoCollection<Document> collection =
        db.getCollection("customers");

    Document customer = new Document()
        .append("full_name", "Nguyễn An")
        .append("loyalty_points", 120);

    collection.insertOne(customer);

    System.out.println(customer.get("_id"));
}
~~~

Mã ví dụ cần MongoDB đã chạy và biến môi trường `MONGODB_URI` hợp lệ. Chạy trong database lab; không dùng dữ liệu giả để ghi vào production.

### 2.3. Đọc document

~~~java
Document found = collection.find(
    new Document("full_name", "Nguyễn An")
).first();

if (found != null) {
    String name = found.getString("full_name");
    Integer points = found.getInteger("loyalty_points");

    System.out.println(name);
    System.out.println(points);
}
~~~

Các getter typed như `getString` và `getInteger` yêu cầu giá trị thực tế có kiểu Java tương thích sau decode. Không tự động chuyển mọi `Long` thành `Integer` theo mong muốn.

### 2.4. Nested document

~~~java
Document shippingAddress = new Document()
    .append("city", "Hồ Chí Minh")
    .append("district", "Bình Thạnh");

Document order = new Document()
    .append("tenant_id", "tenant-a")
    .append("order_code", "ORD-101")
    .append("shipping_address", shippingAddress)
    .append("status", "PAID");
~~~

Lấy nested:

~~~java
Document address =
    order.get("shipping_address", Document.class);

String city =
    address == null ? null : address.getString("city");
~~~

### 2.5. Arrays

~~~java
import java.util.List;

Document order = new Document()
    .append("order_code", "ORD-102")
    .append("tags", List.of("express", "gift"))
    .append(
        "items",
        List.of(
            new Document("sku", "SKU-1")
                .append("qty", 2),
            new Document("sku", "SKU-2")
                .append("qty", 1)
        )
    );
~~~

Khi đọc `items`, phải kiểm tra kiểu phần tử thực sự. `Document` linh hoạt nhưng không đem lại compile-time schema safety.

---

## 3. `Document`, `BsonDocument`, `Bson` và POJO khác nhau ra sao?

| Loại | Đặc điểm | Khi nên dùng |
|---|---|---|
| `Document` | Map key-value, values là Java objects | Schema động, raw projection, tools |
| `BsonDocument` | Map với `BsonValue` rõ ràng | Cần kiểm tra BSON types chính xác |
| `RawBsonDocument` | Giữ raw BSON dưới dạng phù hợp cho một số thao tác | Trường hợp xử lý raw data và performance đặc thù |
| `Bson` | Interface biểu diễn filter/update/stage BSON | `Filters`, `Updates`, aggregation |
| POJO | Java class typed được codec ánh xạ | Domain model/CRUD có schema tương đối ổn |
| Java record | Carrier bất biến theo Java record contract | Read model/immutable data khi driver hỗ trợ |

### 3.1. `Document` không phải JSON

`Document` là Java object. Phương thức `toJson()` chuyển object sang JSON/Extended JSON string để biểu diễn, nhưng MongoDB lưu BSON.

~~~java
Document doc = new Document(
    "_id",
    new ObjectId()
);

String json = doc.toJson();
~~~

`json` chỉ là một bản biểu diễn; không nên coi JSON string đó là định dạng lưu trữ trong MongoDB.

### 3.2. `BsonDocument` khi cần phân biệt loại số

~~~java
import org.bson.BsonDocument;

BsonDocument raw = new BsonDocument()
    .append("quantity", new org.bson.BsonInt32(3))
    .append("total", new org.bson.BsonInt64(3000000000L))
    .append("name", new org.bson.BsonString("Bút"));

System.out.println(raw.get("quantity").getBsonType());
System.out.println(raw.get("total").getBsonType());
~~~

Khi cần kiểm tra chính xác `INT32` vs `INT64` hoặc `DECIMAL128`, `BsonDocument` hữu ích hơn so với chỉ nhìn text JSON.

### 3.3. `Document.parse` cần hiểu Extended JSON

~~~java
Document parsed = Document.parse(
    "{\"name\":\"An\",\"score\":10}"
);
~~~

Với ObjectId, Date, Decimal128 và Binary, cần dùng dạng Extended JSON phù hợp nếu muốn giữ kiểu BSON. Không parse JSON client-supplied chưa kiểm chứng để làm MongoDB update pipeline không giới hạn.

### 3.4. `Document` và POJO có thể dùng song song

Một service có thể dùng:

- POJO cho collection `customers`.
- `Document` cho báo cáo aggregation có shape động.
- `BsonDocument` khi diagnostic payload kiểu BSON.
- DTO riêng cho HTTP JSON response.

Không có quy tắc phải dùng một kiểu cho toàn bộ project.

---

## 4. Hạn chế của `Document`: kiểm tra kiểu ở runtime

Giả sử collection có hai documents:

~~~javascript
{ _id: 1, loyalty_points: 120 }
{ _id: 2, loyalty_points: NumberLong("120") }
~~~

Khi driver decode:

~~~java
Document doc = collection.find(
    new Document("_id", 2)
).first();

Integer points =
    doc.getInteger("loyalty_points"); // Có thể lỗi kiểu.
~~~

Field thứ hai có thể là `Long` thay vì `Integer`.

### 4.1. Không ép kiểu mù

~~~java
Object raw = doc.get("loyalty_points");

if (raw instanceof Number value) {
    long points = value.longValue();
    System.out.println(points);
}
~~~

Ví dụ trên chỉ hợp lý nếu schema cho phép numbers và miền giá trị nằm trong phạm vi `long`. `Number.doubleValue()` hoặc các conversions khác có thể gây mất precision.

### 4.2. Missing và null

~~~java
Document a = new Document();
Document b = new Document("loyalty_points", null);

System.out.println(a.containsKey("loyalty_points")); // false
System.out.println(b.containsKey("loyalty_points")); // true
~~~

Hai document đều có thể trả `null` khi gọi `get`, nhưng ngữ nghĩa lưu trữ khác nhau.

### 4.3. Vấn đề khi đổi tên field

Nếu một developer đổi Java constant `"full_name"` thành `"fullName"` mà chưa migrate dữ liệu, truy vấn có thể không tìm được bản ghi cũ. Đây là một lỗi thường gặp khi chuyển từ `Document` sang POJO.

---

## 5. Định nghĩa một POJO Java rõ ràng

Ta muốn map:

~~~javascript
{
  _id: ObjectId("6914cc000000000000000001"),
  full_name: "Nguyễn An",
  loyalty_points: 120,
  active: true
}
~~~

sang class Java:

~~~java
package example.model;

import org.bson.codecs.pojo.annotations.BsonId;
import org.bson.codecs.pojo.annotations.BsonProperty;
import org.bson.types.ObjectId;

public class Customer {

    @BsonId
    private ObjectId id;

    @BsonProperty("full_name")
    private String fullName;

    @BsonProperty("loyalty_points")
    private Integer loyaltyPoints;

    private Boolean active;

    // Constructor không tham số cho POJO codec.
    public Customer() {
    }

    public ObjectId getId() {
        return id;
    }

    public void setId(ObjectId id) {
        this.id = id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public Integer getLoyaltyPoints() {
        return loyaltyPoints;
    }

    public void setLoyaltyPoints(Integer loyaltyPoints) {
        this.loyaltyPoints = loyaltyPoints;
    }

    public Boolean getActive() {
        return active;
    }

    public void setActive(Boolean active) {
        this.active = active;
    }
}
~~~

### 5.1. Bốn ánh xạ cụ thể

| Java property | Annotation | BSON field |
|---|---|---|
| `id` | `@BsonId` | `_id` |
| `fullName` | `@BsonProperty("full_name")` | `full_name` |
| `loyaltyPoints` | `@BsonProperty("loyalty_points")` | `loyalty_points` |
| `active` | Không cần vì cùng tên | `active` |

### 5.2. Vì sao dùng wrapper `Integer` và `Boolean`?

Wrapper có thể biểu diễn **chưa có giá trị** bằng `null`. Primitive `int`/`boolean` luôn có giá trị mặc định (0/false) sau khởi tạo đối tượng; điều đó có thể làm che giấu chuyện field BSON bị missing.

Nếu nghiệp vụ bảo đảm field luôn tồn tại, có thể dùng primitive cùng schema validation. Nhưng khi đọc dữ liệu legacy cần hiểu sự khác biệt.

### 5.3. Getter/setter là một phần contract của POJO codec

Driver POJO codec thường dùng JavaBean-style getters/setters để đọc/ghi các private properties. Tên getter/setter phải nhất quán với Java property.

Không nên trộn `getFullName()` với setter tên sai như `setFull_name()` rồi kỳ vọng codec đoán được ý định.

---

## 6. Kết hợp `PojoCodecProvider` với `CodecRegistry`

Đây là cấu hình quan trọng nhất khi dùng Java Sync Driver với POJO.

~~~java
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;

import org.bson.codecs.configuration.CodecProvider;
import org.bson.codecs.configuration.CodecRegistry;
import org.bson.codecs.pojo.PojoCodecProvider;

import static org.bson.codecs.configuration
    .CodecRegistries.fromProviders;
import static org.bson.codecs.configuration
    .CodecRegistries.fromRegistries;

String uri = System.getenv("MONGODB_URI");

CodecProvider pojoProvider =
    PojoCodecProvider.builder()
        .automatic(true)
        .build();

CodecRegistry registry = fromRegistries(
    MongoClientSettings.getDefaultCodecRegistry(),
    fromProviders(pojoProvider)
);

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase database = client
        .getDatabase("java_codec_lab")
        .withCodecRegistry(registry);

    MongoCollection<Customer> customers =
        database.getCollection("customers", Customer.class);

    // Các thao tác insert/find được typed với Customer.
}
~~~

### 6.1. Vì sao phải giữ default registry?

Default registry có codecs cho `String`, numbers, `ObjectId`, `Document`, lists và nhiều loại dữ liệu khác. Nếu thay bằng registry chỉ chứa `PojoCodecProvider`, một số types như enum hoặc nested values có thể không tìm được codec.

### 6.2. `automatic(true)`

Nó cho phép provider thử tạo codecs dựa trên các POJO classes/fields gặp phải thay vì yêu cầu explicit registration từng class.

Thuận tiện khi học, nhưng với hệ thống lớn, **explicit registration** của domain classes/packages giúp kiểm soát model scope và giảm việc tự động ánh xạ ngoài ý muốn.

### 6.3. Explicit registration theo class/package

~~~java
CodecProvider pojoProvider =
    PojoCodecProvider.builder()
        .register(
            Customer.class,
            Address.class
        )
        .build();
~~~

Hoặc:

~~~java
CodecProvider pojoProvider =
    PojoCodecProvider.builder()
        .register("example.model")
        .build();
~~~

Trong trường hợp dùng explicit registration, bảo đảm các nested POJOs hoặc derived types cũng được register theo model cần dùng.

### 6.4. Registry dùng được ở nhiều cấp

Có thể áp:

- `MongoClientSettings.codecRegistry(...)` ở client.
- `database.withCodecRegistry(...)` ở database.
- `collection.withCodecRegistry(...)` ở collection.

Dùng một cách thống nhất để tránh collection này đọc POJO đúng nhưng collection khác báo missing codec.

---

## 7. CRUD typed với `MongoCollection<Customer>`

### 7.1. Insert

~~~java
Customer customer = new Customer();
customer.setFullName("Nguyễn An");
customer.setLoyaltyPoints(120);
customer.setActive(true);

customers.insertOne(customer);
~~~

Với `@BsonId ObjectId` và generator convention phù hợp, codec có thể sinh ObjectId khi chưa có ID. Luôn kiểm tra ID sau insert hoặc dùng `InsertOneResult.getInsertedId()` theo nghiệp vụ; không tự hứa mọi kiểu ID được sinh tự động.

### 7.2. Find

~~~java
import static com.mongodb.client.model.Filters.eq;

Customer found =
    customers.find(
        eq("full_name", "Nguyễn An")
    ).first();

if (found != null) {
    System.out.println(found.getFullName());
}
~~~

**Lưu ý:** Chuỗi `"full_name"` trong `Filters.eq` là **BSON field name** đang lưu, không phải tên Java `fullName`.

### 7.3. Update

~~~java
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.set;

customers.updateOne(
    eq("full_name", "Nguyễn An"),
    set("loyalty_points", 130)
);
~~~

`Updates.set` cũng cần tên field BSON `loyalty_points`.

### 7.4. Delete

~~~java
customers.deleteOne(
    eq("_id", found.getId())
);
~~~

### 7.5. Typed collection không tự viết lại filter strings

`MongoCollection<Customer>` chỉ đặt document class cho dữ liệu được encode/decode. Nó **không biến** tên Java property trong filter string thành tên BSON tương ứng.

Đây là một điểm cực kỳ quan trọng khi chuyển từ raw Document sang POJO.

---

## 8. Java field name, BSON key, JSON API name là ba lớp

Một endpoint có thể nhận JSON:

~~~json
{
  "customerName": "Nguyễn An",
  "loyaltyScore": 120
}
~~~

Domain POJO:

~~~java
private String fullName;
private Integer loyaltyPoints;
~~~

BSON:

~~~javascript
{
  full_name: "Nguyễn An",
  loyalty_points: 120
}
~~~

Ba tên có thể **khác nhau có chủ ý**.

### 8.1. Nên tách các lớp

| Lớp | Vai trò | Công cụ liên quan |
|---|---|---|
| HTTP JSON DTO | Public API contract | Jackson, JSON-B |
| Java domain POJO | Business type và validation | Java code |
| BSON document | Persistent schema | MongoDB Java Codec |
| Query/index field name | Đường dẫn trong MongoDB | `Filters`/`Updates`/index |
| Aggregation output alias | Tên field tạm/báo cáo | `$project`/`$group` |

### 8.2. `@JsonProperty` không thay `@BsonProperty`

Nếu ứng dụng dùng Jackson:

~~~java
@JsonProperty("customerName")
private String fullName;
~~~

Annotation đó cấu hình JSON serialization **của Jackson**, không tự đổi tên field BSON của native MongoDB PojoCodec.

Ngược lại:

~~~java
@BsonProperty("full_name")
private String fullName;
~~~

không tự định nghĩa tên JSON HTTP response.

### 8.3. Không trộn hai cơ chế vô ý

Một class có thể có cả Jackson lẫn BSON annotations nếu được thiết kế rõ, nhưng dễ tạo coupling giữa public API và data persistence. Với hệ thống lớn, nên cân nhắc DTO riêng.

---

## 9. Quy ước đặt tên field: chọn sớm, dùng nhất quán

Một số quy ước:

| Quy ước | Java | BSON |
|---|---|---|
| CamelCase đồng nhất | `customerName` | `customerName` |
| Java camelCase, BSON snake_case | `customerName` | `customer_name` |
| Business-specific | `id` | `_id` |
| Legacy alias | `postalCode` | `zip` |
| Acronym policy | `apiKey` | `api_key` |
| Nested | `shippingAddress.city` | `shipping_address.city` |

### 9.1. Phương án A — cùng camelCase

Ưu điểm:

- Ít annotation.
- Query strings dễ suy từ tên property.
- Ít quy tắc chuyển đổi.

Nhược điểm: nếu database hiện tại dùng snake_case, phải migrate hoặc duy trì aliases.

### 9.2. Phương án B — Java camelCase, BSON snake_case

Ưu điểm:

- Consistency nếu team/legacy schema chọn snake_case.
- Tên field lưu trữ không phụ thuộc cách đặt tên variable Java.

Nhược điểm:

- Phải dùng annotations hoặc custom naming convention.
- Query/index/aggregation luôn phải biết **BSON field names**.
- Khi đổi tên Java property, mapping không nên vô tình đổi persistent schema.

### 9.3. Chọn một định nghĩa chính thức

Ví dụ policy:

~~~text
Java classes/properties:
  PascalCase / camelCase

MongoDB collections:
  plural lowercase (customers, purchaseOrders)

BSON fields:
  snake_case, ngoại lệ _id

Date/time:
  *_at cho thời điểm; lưu BSON Date UTC

Identifier:
  *_id cho references, _id cho primary key

Money:
  *_minor_units hoặc Decimal128, có currency

Tenant:
  tenant_id đến từ authentication context
~~~

Policy chỉ là ví dụ; **điều quan trọng là không thay đổi tùy từng developer**.

### 9.4. Không lạm dụng field names chứa ký tự đặc biệt

MongoDB có các quy tắc riêng với keys chứa `.` hoặc bắt đầu bằng `$`, và semantics của dotted paths khác literal field name. Với ứng dụng Java thông thường, tránh dùng tên BSON chứa dấu chấm, dollar-prefix, whitespace kỳ lạ hoặc ký tự khó parse làm property path.

### 9.5. Indexes phải theo tên BSON

~~~javascript
db.customers.createIndex(
  {
    tenant_id: 1,
    full_name: 1
  }
);
~~~

Nếu field thực tế là `full_name`, tạo index trên `fullName` sẽ không giúp query đúng và có thể gây confusion.

---

## 10. `@BsonProperty`: đổi tên một field cụ thể

~~~java
import org.bson.codecs.pojo.annotations.BsonProperty;

public class Product {

    @BsonProperty("product_code")
    private String productCode;

    @BsonProperty("display_name")
    private String displayName;

    public Product() {}

    public String getProductCode() {
        return productCode;
    }

    public void setProductCode(String value) {
        productCode = value;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String value) {
        displayName = value;
    }
}
~~~

BSON:

~~~javascript
{
  product_code: "SKU-2026",
  display_name: "Sản phẩm A"
}
~~~

### 10.1. Annotation convention phải được bật

`Conventions.DEFAULT_CONVENTIONS` bao gồm `ANNOTATION_CONVENTION`; với configuration tùy biến, nếu bỏ annotation convention thì `@BsonProperty` có thể không được áp dụng như kỳ vọng.

### 10.2. Đặt annotation ở vị trí nào?

Tài liệu driver mô tả annotation trên fields/accessors; với private field mapping, nên có getters/setters phù hợp hoặc configured conventions để driver truy cập đúng property.

Dùng một phong cách nhất quán (ví dụ annotations trên private fields và JavaBean public accessors) để tránh xung đột.

### 10.3. Không dùng `@BsonProperty` để đổi tên mọi query tự động

~~~java
Filters.eq("product_code", "SKU-2026");
~~~

Là đúng khi MongoDB field thực là `product_code`. Không viết `Filters.eq("productCode",...)` rồi trông chờ filter được map bởi POJO metadata.

---

## 11. `@BsonId` và khóa `_id`

### 11.1. ObjectId tự nhiên

~~~java
public class Product {

    @BsonId
    private ObjectId id;

    public Product() {}

    public ObjectId getId() {
        return id;
    }

    public void setId(ObjectId id) {
        this.id = id;
    }
}
~~~

BSON `_id` mặc định có unique index; driver/codec có thể sinh ObjectId theo generator convention khi ID chưa có.

### 11.2. Business identifier khác physical ID

~~~javascript
{
  _id: ObjectId("6914dd000000000000000001"),
  tenant_id: "tenant-a",
  product_code: "SKU-2026"
}
~~~

`product_code` là business key; `_id` là MongoDB document ID. Có thể cần unique compound index `tenant_id + product_code`, nhưng không mặc định chúng là một khái niệm.

### 11.3. `String` và BSON ObjectId representation

Khi ứng dụng buộc property ID là `String` nhưng MongoDB vẫn lưu BSON ObjectId, có thể dùng:

~~~java
import org.bson.BsonType;
import org.bson.codecs.pojo.annotations.BsonId;
import org.bson.codecs.pojo.annotations.BsonRepresentation;

public class LegacyEntity {

    @BsonId
    @BsonRepresentation(BsonType.OBJECT_ID)
    private String id;

    public LegacyEntity() {}

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }
}
~~~

`@BsonRepresentation` **không phải bộ chuyển đổi kiểu tùy ý**. Tài liệu driver minh họa `String ↔ ObjectId`, còn kiểu khác có thể yêu cầu codec thực thi `RepresentationConfigurable`.

### 11.4. Không đổi từ ObjectId sang String trong database một cách vô thức

~~~javascript
{ _id: ObjectId("6914dd000000000000000001") }
~~~

khác với:

~~~javascript
{ _id: "6914dd000000000000000001" }
~~~

Hai BSON types khác nhau, query và index equality không coi chúng là cùng ID.

### 11.5. Composite `_id`

Có thể dùng một object/value type làm `_id` khi thiết kế schema yêu cầu, nhưng phải có codec cho embedded ID type và ổn định giá trị. Không đổi `_id` của document đã tồn tại bằng update thông thường.

---

## 12. Annotation quan trọng trong POJO codec

| Annotation | Chức năng | Khi dùng |
|---|---|---|
| `@BsonId` | Property map tới `_id` | Định danh document |
| `@BsonProperty` | Chỉ định tên field BSON | snake_case/legacy field |
| `@BsonIgnore` | Không map property | Derived/runtime-only value |
| `@BsonCreator` | Chọn constructor/static factory khi decode | Immutable/constructor-only models |
| `@BsonRepresentation` | Đổi BSON representation khi codec hỗ trợ | Ví dụ String ↔ ObjectId |
| `@BsonExtraElements` | Nhận các fields chưa được map | Forward compatibility/dynamic fields |
| `@BsonDiscriminator` | Phân biệt subtype | Polymorphic document hierarchy |

Các annotation thuộc package:

~~~java
org.bson.codecs.pojo.annotations
~~~

### 12.1. Không có annotation đặt collection name

Native POJO codec không có một annotation MongoDB built-in riêng để map class sang collection. Thường chỉ định:

~~~java
database.getCollection("products", Product.class);
~~~

Có thể lưu constant `COLLECTION_NAME` trong class/repository.

### 12.2. Annotation khác với validator

`@BsonProperty("full_name")` giúp codec map field; nó **không** cưỡng chế dữ liệu trong MongoDB luôn có `full_name` hoặc `loyalty_points` là số không âm.

Để enforce schema ở database có thể cân nhắc `$jsonSchema` validator và indexes; ở ứng dụng cần validation riêng.

---

## 13. `@BsonIgnore`: loại property khỏi lưu trữ

Ví dụ:

~~~java
public class Customer {

    private String fullName;

    @BsonIgnore
    private String displayLabelCache;

    public Customer() {}

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String value) {
        fullName = value;
    }

    public String getDisplayLabelCache() {
        return displayLabelCache;
    }

    public void setDisplayLabelCache(String value) {
        displayLabelCache = value;
    }
}
~~~

`displayLabelCache` có thể được tính từ dữ liệu khác, không cần lưu BSON.

### 13.1. `transient` và `static`

POJO mapping mặc định tập trung vào instance properties được hỗ trợ. Những field `static` hoặc `transient` không nên dùng để lưu nghiệp vụ một cách vô tình.

### 13.2. Cẩn thận với dữ liệu bảo mật

Không chỉ gắn `@BsonIgnore` rồi coi thông tin đã bảo mật: field có thể vẫn xuất hiện ở JSON API, logs hoặc tracing nếu không có controls tương ứng. Mapping persistence và data exposure là hai lớp khác nhau.

### 13.3. Derived values

Nếu property chỉ là `getFullNameUpperCase()` nhưng không có backing field phù hợp, driver có thể coi đây là bean property tùy conventions. Nên thiết kế explicit model/ignore để không vô tình tạo field mới khi insert/replace.

---

## 14. `@BsonCreator`: constructor có tham số

POJO codec mặc định thường dùng constructor không tham số để tạo object rồi set properties. Với class bất biến hoặc không muốn public setters, có thể dùng constructor được đánh dấu.

~~~java
import org.bson.codecs.pojo.annotations.BsonCreator;
import org.bson.codecs.pojo.annotations.BsonProperty;

public final class CountryCode {

    private final String code;
    private final String displayName;

    @BsonCreator
    public CountryCode(
        @BsonProperty("code") String code,
        @BsonProperty("display_name") String displayName
    ) {
        this.code = code;
        this.displayName = displayName;
    }

    public String getCode() {
        return code;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

### 14.1. Vì sao annotate toàn bộ tham số?

Tài liệu driver yêu cầu các parameters của `@BsonCreator` được annotate `@BsonProperty` hoặc `@BsonId`, để codec biết mapping khi tạo instance.

### 14.2. Constructor này không phải JSON constructor mặc định

`@JsonCreator` của Jackson không thay `@BsonCreator`. Nếu dùng cả hai frameworks, phải cấu hình phù hợp cho từng lớp.

### 14.3. Dữ liệu thiếu constructor argument

Khi field được đánh dấu constructor-required nhưng BSON document thiếu nó, behavior có thể gây default/null/exception tùy kiểu và model. Với invariant quan trọng, validate ngay trong constructor:

~~~java
if (code == null || code.isBlank()) {
    throw new IllegalArgumentException(
        "code is required"
    );
}
~~~

Khi schema cũ thiếu property mới, cần migration/default strategy thay vì để đọc production hàng loạt thất bại.

---

## 15. JavaBean conventions, private fields và setter access

### 15.1. Đường mặc định

Ví dụ:

~~~java
private String city;

public String getCity() { return city; }

public void setCity(String city) {
    this.city = city;
}
~~~

Với POJO codec, getter/setter cùng visibility phù hợp giúp ánh xạ property `city`.

### 15.2. Private setter hoặc không có setter

Khi không có public setter, việc deserialize private fields có thể yêu cầu convention:

~~~java
import org.bson.codecs.pojo.Conventions;
import org.bson.codecs.pojo.PojoCodecProvider;

import java.util.ArrayList;
import java.util.List;

List<org.bson.codecs.pojo.Convention> conventions =
    new ArrayList<>(Conventions.DEFAULT_CONVENTIONS);

conventions.add(
    Conventions.SET_PRIVATE_FIELDS_CONVENTION
);

PojoCodecProvider pojoProvider =
    PojoCodecProvider.builder()
        .automatic(true)
        .conventions(conventions)
        .build();
~~~

Convention cho phép đặt **private field** bằng reflection khi thiếu setter, theo điều kiện driver. Getter vẫn được yêu cầu cho serialization trong trường hợp liên quan. Tránh dùng nó như lý do bỏ thiết kế constructor/encapsulation cẩn thận.

### 15.3. Getter-setter modifiers phải phù hợp

Native POJO codec có những yêu cầu về visibility và JavaBean property introspection. Trộn một getter private và setter public cho cùng property có thể làm mapping lỗi.

### 15.4. Java record không phải JavaBean POJO thông thường

Record có canonical constructor và accessor `name()` thay vì `getName()`. Java Driver hiện có **record codec** và hướng dẫn riêng, không nên áp nguyên các giả định POJO getters/setters cho record.

---

## 16. Java records: khi nào cân nhắc thay POJO mutable?

Java records là một cách tạo immutable data carriers, có thể hữu ích với read-only views hoặc DTO.

~~~java
public record CustomerSummary(
    String fullName,
    int loyaltyPoints
) {}
~~~

Driver Java hiện hỗ trợ encode/decode records bằng default codec registry theo hướng dẫn **Document Data Format: Records**. Java records yêu cầu Java 16+ về cú pháp (Java 17 LTS phổ biến).

### 16.1. Record và BSON naming

Nếu BSON dùng `full_name` còn record component là `fullName`, cần cấu hình mapping phù hợp với record codec/annotations được phiên bản driver hỗ trợ hoặc dùng DTO conversion rõ ràng. Đừng mặc định `@BsonProperty` trên POJO và mọi record version hoạt động hoàn toàn giống nhau.

### 16.2. Immutable không tự bảo đảm database immutable

Record object ở Java không có setters, nhưng MongoDB document vẫn có thể được update bằng `Updates.set(...)`. Immutability của domain và quyền update ở database là hai khái niệm khác nhau.

### 16.3. Khi nào dùng POJO mutable?

Khi cần JavaBeans, frameworks cũ, setters, hoặc mapped entities có cấu trúc phức tạp. Khi muốn immutable constructor-based class, có thể dùng `@BsonCreator`.

---

## 17. Nested POJO: ánh xạ document lồng nhau

BSON:

~~~javascript
{
  customer_name: "Nguyễn An",
  shipping_address: {
    city: "Hồ Chí Minh",
    district: "Bình Thạnh"
  }
}
~~~

POJO lồng nhau:

~~~java
public class Address {

    private String city;
    private String district;

    public Address() {}

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }

    public String getDistrict() {
        return district;
    }

    public void setDistrict(String district) {
        this.district = district;
    }
}
~~~

~~~java
public class Order {

    @BsonProperty("customer_name")
    private String customerName;

    @BsonProperty("shipping_address")
    private Address shippingAddress;

    public Order() {}

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String name) {
        customerName = name;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public void setShippingAddress(Address address) {
        shippingAddress = address;
    }
}
~~~

Registry phải có codec cho `Order` và `Address` (qua automatic hoặc explicit registration).

### 17.1. Dotted paths trong query

~~~java
Filters.eq(
    "shipping_address.city",
    "Hồ Chí Minh"
);
~~~

`shipping_address` là BSON field của parent; `city` là BSON field của nested Address.

### 17.2. Nested arrays và map

~~~java
public class Order {

    private java.util.List<OrderItem> items;

    @BsonProperty("extra_attributes")
    private java.util.Map<String, String> extraAttributes;

    public Order() {}

    // Getters và setters cho hai properties.
}
~~~

Element types nên rõ ràng. `List<OrderItem>` cho codec biết object type của mỗi phần tử; `List<Object>` gây khó cho schema/versioning.

### 17.3. Map keys là BSON field names

Với `Map<String,String>`, các map keys có thể trở thành field names trong nested BSON document. Phải validate keys do user nhập, tránh dấu chấm/dollar-prefix khi không chủ đích và ngăn dữ liệu quá lớn.

---

## 18. Enum serialization và giá trị legacy

~~~java
public enum CustomerStatus {
    ACTIVE,
    INACTIVE,
    BLOCKED
}
~~~

~~~java
public class Customer {

    private CustomerStatus status;

    public Customer() {}

    public CustomerStatus getStatus() {
        return status;
    }

    public void setStatus(CustomerStatus status) {
        this.status = status;
    }
}
~~~

### 18.1. Default enum codecs

Driver default codec registry có hỗ trợ các kiểu enum tương ứng. Từ Java Driver 4.5, `PojoCodecProvider` không tự bao gồm enum codec riêng; cần kết hợp default registry hoặc custom enum codec.

### 18.2. Đổi tên enum có thể làm decode lỗi

Database lưu:

~~~javascript
{ status: "INACTIVE" }
~~~

Nếu code đổi enum member thành `DISABLED` mà không migrate legacy documents hoặc custom mapping, decode có thể thất bại.

### 18.3. Đừng coi enum tên Java là schema bất biến

Có thể dùng stable code như `"A"`, `"I"` với codec riêng để tránh phụ thuộc tên enum; tuy nhiên việc thêm custom codec phải đồng bộ registry và test migration.

### 18.4. Trạng thái không nhận diện

Nếu dữ liệu được tạo bởi phiên bản ứng dụng mới hơn, phiên bản cũ có thể chưa biết enum value. Cần forward-compatibility policy: reject rõ, dùng `UNKNOWN` với mapping có kiểm soát hoặc rolling deployment tránh incompatible writes.

---

## 19. Missing, null và primitive defaults trong POJO

BSON có thể có:

~~~javascript
{ _id: 1 }
{ _id: 2, loyalty_points: null }
{ _id: 3, loyalty_points: 0 }
~~~

Trong POJO:

~~~java
private Integer loyaltyPoints;
~~~

`null` có thể đại diện missing hoặc BSON null sau decode; chỉ nhìn Java property không biết chắc field đã có trong document hay không.

### 19.1. Default null serialization

Theo tài liệu native POJO codec, mặc định những properties có giá trị `null` thường **bị bỏ qua khi serialize**, trừ khi custom serialization được cấu hình.

Do đó:

~~~java
customer.setLoyaltyPoints(null);
customers.insertOne(customer);
~~~

không phải bằng chứng rằng BSON có `loyalty_points:null`. Hãy kiểm tra raw document thực tế.

### 19.2. Cẩn thận khi xử lý PATCH

Một HTTP PATCH:

~~~json
{
  "loyaltyPoints": null
}
~~~

có thể mang nghĩa **xóa giá trị**, trong khi property POJO `null` có thể cũng có nghĩa **client không gửi field này**.

Không dùng một POJO đơn giản và `replaceOne` cho mọi PATCH nếu không phân biệt ba trạng thái:

- Không gửi field → giữ nguyên.
- Gửi null → đặt null hoặc unset theo API contract.
- Gửi giá trị → cập nhật giá trị.

### 19.3. Primitive defaults

~~~java
private int loyaltyPoints;
private boolean active;
~~~

Khi BSON thiếu field, object có thể giữ `0` và `false`. Nếu business cần phân biệt “chưa có dữ liệu” với “có giá trị 0/false”, dùng wrappers hoặc explicit presence flags và validation.

### 19.4. MongoDB filter null semantics

~~~javascript
db.customers.find({ loyalty_points: null });
~~~

Thông thường tìm cả documents có field null **và field không tồn tại**. Nếu muốn chỉ field tồn tại và là null, dùng điều kiện thích hợp như `$type:10` hoặc logic `$exists`; nếu muốn missing, dùng `$exists:false`.

---

## 20. `@BsonExtraElements`: giữ các trường chưa biết

Ví dụ BSON có field mới:

~~~javascript
{
  _id: ObjectId("6914ee000000000000000001"),
  full_name: "Nguyễn An",
  loyalty_points: 120,
  preferred_language: "vi",
  app_feature_flag: "BETA"
}
~~~

POJO phiên bản cũ chỉ biết `full_name` và `loyalty_points`.

Nếu cần giữ các field chưa biết:

~~~java
import org.bson.Document;
import org.bson.codecs.pojo.annotations.BsonExtraElements;

public class FlexibleCustomer {

    @BsonProperty("full_name")
    private String fullName;

    @BsonExtraElements
    private Document extras;

    public FlexibleCustomer() {}

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String value) {
        fullName = value;
    }

    public Document getExtras() {
        return extras;
    }

    public void setExtras(Document extras) {
        this.extras = extras;
    }
}
~~~

`@BsonExtraElements` có thể nhận `Document`, `BsonDocument` hoặc `Map<String,Object>` theo tài liệu.

### 20.1. Dùng khi nào?

- Tiến hóa schema từng bước.
- Truy xuất metadata động.
- Hệ thống mở rộng field theo tenant.
- Tool migration cần bảo toàn unknown properties.

### 20.2. Không nên lạm dụng

Nếu cho người dùng ghi arbitrary extras, cần validation/size limits/authorization. Unknown fields có thể vô tình ghi đè fields mới của phiên bản app khác nếu mapping không được quản lý cẩn thận.

### 20.3. Dữ liệu lạ và replace

Nếu POJO **không chứa** extras và được decode từ document có field mới, rồi application dùng `replaceOne` toàn object, unknown fields có thể bị mất. Đây là lý do tiến hóa schema phải đi cùng quy trình update an toàn.

---

## 21. Polymorphism và `@BsonDiscriminator`

Giả sử có nhiều loại event trong một collection:

~~~text
Event
  +-- UserCreatedEvent
  +-- OrderPaidEvent
~~~

Một BSON document có field xác định subtype:

~~~javascript
{
  _t: "OrderPaidEvent",
  order_id: "ORD-101",
  amount: NumberLong("500000")
}
~~~

`@BsonDiscriminator` hoặc `ClassModelBuilder.enableDiscriminator(true)` giúp codec chọn subtype đúng khi decode kiểu abstract/interface trong những cấu hình hỗ trợ.

### 21.1. Quy tắc

- Register base class và các subtypes.
- Chỉ định discriminator key/value có contract rõ.
- Không để người dùng tùy ý gửi discriminator class name dẫn tới việc chọn class ngoài whitelist.
- Không đổi discriminator value khi deploy mà không có migration/compatibility plan.
- Kiểm tra đọc dữ liệu legacy khi thêm subtype mới.

### 21.2. Ví dụ annotation định hướng

~~~java
import org.bson.codecs.pojo.annotations.BsonDiscriminator;

@BsonDiscriminator(
    key = "_t",
    value = "OrderPaidEvent"
)
public class OrderPaidEvent {
    // Properties + getters/setters + no-arg constructor.
}
~~~

Nếu một property khai báo base `Event` nhưng thực tế chứa derived classes, provider/model phải được cấu hình cho polymorphic decoding; chỉ gắn annotation ở một subtype chưa đủ cho mọi kiến trúc.

### 21.3. Khi nào dùng discriminator?

Hữu ích với union-like models, nhưng nếu có quá nhiều kiểu events với schema khác biệt, đôi khi dùng `Document` + explicit event type dispatch hoặc riêng collections sẽ dễ vận hành hơn.

---

## 22. `ClassModel`, `PropertyModel` và custom conventions

Khi annotation không đủ, POJO codec hỗ trợ cấu hình model lập trình.

- `ClassModel`: thông tin về class, constructor, ID, discriminator, property list.
- `PropertyModel`: thông tin về một property, BSON field names, codec và serialization policy.
- `Convention`: quy tắc áp dụng cho model trong lúc xây codec.

### 22.1. Ví dụ explicit ClassModel

~~~java
import org.bson.codecs.pojo.ClassModel;
import org.bson.codecs.pojo.PojoCodecProvider;

ClassModel<Customer> customerModel =
    ClassModel.builder(Customer.class)
        .build();

PojoCodecProvider provider =
    PojoCodecProvider.builder()
        .register(customerModel)
        .build();
~~~

### 22.2. Tên BSON qua model builder

Trong Java Driver có `PropertyModelBuilder` với các cấu hình `readName(...)`/`writeName(...)`. Chúng kiểm soát cách codec đọc và ghi tên trường BSON. Khi dùng hướng này, cần **thiết lập cùng tên mong muốn cho cả hai chiều** nếu không cố tình tách biệt, và kiểm tra docs/Javadoc phiên bản cụ thể.

Ví dụ ý tưởng:

~~~java
var model = ClassModel.builder(Customer.class);

model.getProperty("fullName")
    .readName("full_name")
    .writeName("full_name");
~~~

Sau đó register `model.build()` vào `PojoCodecProvider`. Với nhiều classes, có thể hiện thực `Convention` để duy trì naming policy ở một nơi.

### 22.3. Custom snake_case convention

Một convention có thể duyệt `ClassModelBuilder.getPropertyModelBuilders()`, chuyển `camelCase` sang `snake_case` và chỉ đổi tên mapped properties theo rules. Nhưng cần xử lý:

- Acronyms: `apiURL` → `api_url` hay `api_u_r_l`?
- ID: `id` cần giữ `_id`.
- Fields có `@BsonProperty` explicit: annotation có được ưu tiên?
- Field names legacy không theo quy tắc.
- Nested POJOs và maps.
- Ordering của conventions.
- Read/write field names cùng nhau.

### 22.4. Thứ tự conventions quan trọng

`Conventions.DEFAULT_CONVENTIONS` bao gồm:

- `CLASS_AND_PROPERTY_CONVENTION`.
- `ANNOTATION_CONVENTION`.
- `OBJECT_ID_GENERATORS`.

Nếu thêm custom convention, builders áp conventions theo thứ tự, convention sau có thể thay behavior của convention trước. Vì vậy cần tests xác nhận `@BsonProperty` explicit không bị custom naming policy ghi đè.

### 22.5. Khuyến nghị thực tế

- Một vài field khác tên: dùng `@BsonProperty`.
- Hàng trăm classes theo snake_case: cân nhắc custom convention, nhưng viết tests kỹ cho acronym/legacy.
- Migration phức tạp: explicit mapping hoặc DTO conversion dễ kiểm soát hơn.
- Không tự viết full custom codec cho mọi POJO nếu conventions đã giải quyết.

---

## 23. Tùy chỉnh codec riêng cho Value Object

Một domain có thể dùng custom type như `Money`, `EmailAddress` hoặc `CurrencyCode`, trong khi BSON chỉ lưu string/Decimal128.

Nếu không có codec:

~~~text
CodecConfigurationException:
Can't find a codec for class example.domain.Money
~~~

### 23.1. Ví dụ kiểu custom

~~~java
public final class EmailAddress {

    private final String value;

    public EmailAddress(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Email không được rỗng"
            );
        }
        this.value = value;
    }

    public String value() {
        return value;
    }
}
~~~

### 23.2. Viết một `Codec<EmailAddress>`

~~~java
import org.bson.BsonReader;
import org.bson.BsonWriter;

import org.bson.codecs.Codec;
import org.bson.codecs.DecoderContext;
import org.bson.codecs.EncoderContext;

public final class EmailAddressCodec
        implements Codec<EmailAddress> {

    @Override
    public void encode(
            BsonWriter writer,
            EmailAddress value,
            EncoderContext context) {

        writer.writeString(value.value());
    }

    @Override
    public EmailAddress decode(
            BsonReader reader,
            DecoderContext context) {

        return new EmailAddress(reader.readString());
    }

    @Override
    public Class<EmailAddress> getEncoderClass() {
        return EmailAddress.class;
    }
}
~~~

### 23.3. Thứ tự registry

~~~java
import static org.bson.codecs.configuration
    .CodecRegistries.fromCodecs;
import static org.bson.codecs.configuration
    .CodecRegistries.fromProviders;
import static org.bson.codecs.configuration
    .CodecRegistries.fromRegistries;

CodecRegistry registry = fromRegistries(
    fromCodecs(new EmailAddressCodec()),
    MongoClientSettings.getDefaultCodecRegistry(),
    fromProviders(
        PojoCodecProvider.builder()
            .automatic(true)
            .build()
    )
);
~~~

Custom codec đặt trước default/POJO providers nếu muốn nó được ưu tiên. Lưu ý codec trên chỉ xử lý `String` BSON, không tự đọc BSON `null`/loại khác; trong domain thật cần thống nhất null semantics, normalization và error handling.

### 23.4. Vì sao không map email bằng string luôn?

Với một hệ thống nhỏ, dùng `String` đơn giản hơn. Value Object có lợi khi cần invariant/normalization nhưng tăng chi phí mapping và maintenance. Chọn theo yêu cầu.

---

## 24. Decimal128, số tiền và độ chính xác

BSON có `Int32`, `Int64`, `Double` và `Decimal128`. Nếu dữ liệu tiền cần độ chính xác thập phân, nên định nghĩa contract rõ.

### 24.1. Lưu `Decimal128` trong `Document`

~~~java
import org.bson.types.Decimal128;
import java.math.BigDecimal;

Document invoice = new Document()
    .append("currency", "USD")
    .append(
        "total",
        new Decimal128(new BigDecimal("123.45"))
    );
~~~

### 24.2. POJO property

~~~java
public class Invoice {

    private Decimal128 total;

    public Invoice() {}

    public Decimal128 getTotal() {
        return total;
    }

    public void setTotal(Decimal128 value) {
        total = value;
    }
}
~~~

Khi tính toán domain:

~~~java
BigDecimal amount =
    invoice.getTotal().bigDecimalValue();
~~~

### 24.3. Tránh `double` cho tiền

~~~java
double total = 0.1 + 0.2;
~~~

Floating-point binary có thể không biểu diễn chính xác 0.1/0.2. Dùng `BigDecimal`/`Decimal128` hoặc integer minor units theo contract, và lưu currency.

### 24.4. `Decimal128` không phải `Long`

Nếu BSON field `total` là `Decimal128` mà POJO khai `Long`, codec không tự đảm bảo convert có precision. Cần migration hoặc custom codec/mapper có kiểm soát.

### 24.5. Null và missing

Một field tiền missing, null và bằng 0 có thể biểu diễn nghiệp vụ khác nhau; validator/migration phải định nghĩa rạch ròi.

---

## 25. Date, Instant, LocalDate và timezone

MongoDB BSON Date biểu diễn thời điểm bằng milliseconds từ epoch UTC. Cách hiển thị có thể dùng timezone khác, nhưng giá trị thời điểm là UTC.

### 25.1. Java `Date`

~~~java
import java.util.Date;

public class AuditEvent {

    private Date createdAt;

    public AuditEvent() {}

    public Date getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Date value) {
        createdAt = value;
    }
}
~~~

### 25.2. Java `Instant`

~~~java
import java.time.Instant;

Instant now = Instant.now();
~~~

Java Driver hiện có codecs hỗ trợ các kiểu `java.time` thông dụng, gồm `Instant`. Dùng `Instant` cho một thời điểm tuyệt đối, nhưng kiểm tra chính xác kiểu/codec với driver đang sử dụng.

### 25.3. `LocalDate` là ngày lịch, không phải timestamp nghiệp vụ

Ngày sinh “1995-06-10” không nên vô tình chuyển thành thời điểm với timezone không rõ. Có thể biểu diễn như string chuẩn ISO hoặc loại dữ liệu được driver hỗ trợ theo domain contract.

### 25.4. `LocalDateTime` không có timezone

Nếu dùng `LocalDateTime` như absolute event time mà không có zone, thông tin múi giờ bị mơ hồ. Nên dùng `Instant` cho `createdAt`/`paidAt`, dùng `LocalDate` cho ngày lịch, lưu timezone riêng nếu nghiệp vụ cần.

### 25.5. Millisecond precision

BSON Date có độ chính xác milliseconds. Java `Instant` có thể chứa nanoseconds. Round-trip có thể mất phần nhỏ hơn millisecond; không viết assertion bằng `Instant.equals` nếu input có nanoseconds chưa normalize.

### 25.6. Naming field ngày giờ

`created_at`, `updated_at`, `paid_at` là các mốc. `billing_date` có thể là local date. Tên field phải phản ánh semantic để người dùng không nhầm.

---

## 26. UUID và binary representation

UUID trong Java thường là `java.util.UUID`, nhưng BSON có binary subtype/representation khác nhau. Khi chuyển đổi driver cũ sang mới, cần chú ý `UuidRepresentation`.

### 26.1. Cấu hình rõ UUID representation

Ví dụ (chỉ dùng nếu schema BSON đang lưu UUID theo STANDARD):

~~~java
import com.mongodb.MongoClientSettings;
import org.bson.UuidRepresentation;

MongoClientSettings settings =
    MongoClientSettings.builder()
        .applyConnectionString(
            new com.mongodb.ConnectionString(uri)
        )
        .uuidRepresentation(
            UuidRepresentation.STANDARD
        )
        .build();

try (MongoClient client =
         MongoClients.create(settings)) {

    // ...
}
~~~

### 26.2. Không đổi representation tùy tiện

Dữ liệu legacy dùng representation khác có thể không lookup đúng sau khi đổi. Migration phải kiểm tra subtype/bytes, test round-trip và chọn conversion strategy chính xác.

### 26.3. UUID string khác UUID Binary

`"550e8400-e29b-41d4-a716-446655440000"` dưới BSON String không đồng nhất với UUID lưu BSON Binary. Query phải dùng type đúng.

---

## 27. Unknown fields, schema evolution và backwards compatibility

MongoDB cho phép collection có documents khác structure:

~~~javascript
// V1
{
  _id: 1,
  full_name: "Nguyễn An"
}

// V2
{
  _id: 2,
  full_name: "Bình",
  loyalty_points: 20
}

// V3
{
  _id: 3,
  full_name: "Chi",
  loyalty_points: 40,
  preferred_language: "vi"
}
~~~

### 27.1. Thêm property mới

Nếu code V3 cần `preferredLanguage`, những documents V1/V2 có thể decode với `null`/default. Nếu field bắt buộc, cần backfill hoặc app fallback trước khi enforce.

### 27.2. Xóa property khỏi Java class

Nếu code mới không còn field `oldField` nhưng database còn chứa field, reading có thể bỏ qua, nhưng **replaceOne từ POJO mới có nguy cơ xóa oldField**. Không dùng full replace vô tư trong rolling deployments.

### 27.3. Rename field là migration dữ liệu

Nếu chuyển BSON `full_name` sang `display_name`:

1. Ghi nhận tất cả queries/indexes/aggregation liên quan.
2. Thêm code đọc cả hai hoặc tạo migration compatibility window.
3. Backfill documents.
4. Tạo/sửa indexes phù hợp.
5. Chuyển writes sang tên mới.
6. Đối soát data.
7. Loại tên cũ khi chắc chắn mọi versions của app không còn dùng.

Chỉ đổi `@BsonProperty("full_name")` thành `@BsonProperty("display_name")` **không** tự rename dữ liệu đã có trong MongoDB.

### 27.4. Schema version

Có thể lưu field `schema_version` để phân biệt những formats. Tuy nhiên nó không thay migration/validation; decoder phải biết cách xử lý từng version đã tồn tại.

### 27.5. Rolling application deployment

Trong thời gian V1 và V2 chạy song song, V2 không nên ghi một BSON structure mà V1 chắc chắn decode lỗi, trừ khi có feature flag/traffic isolation. Dùng expand → migrate → contract.

---

## 28. Update operators vs replace toàn bộ POJO

### 28.1. Partial update an toàn hơn cho PATCH

~~~java
customers.updateOne(
    Filters.eq("_id", customerId),
    Updates.combine(
        Updates.set("full_name", "Nguyễn An"),
        Updates.set("loyalty_points", 150)
    )
);
~~~

Chỉ các fields chỉ định được sửa; unknown fields còn lại được giữ.

### 28.2. `replaceOne` thay toàn bộ document

~~~java
customers.replaceOne(
    Filters.eq("_id", customer.getId()),
    customer
);
~~~

Thao tác replace lấy representation của toàn bộ POJO để thay document (trừ những ràng buộc với `_id`). Nếu POJO không chứa field cũ, nó có thể bị loại khỏi database.

### 28.3. Null + replace có thể làm mất dữ liệu

Nếu POJO được decode từ một projection thiếu fields, các missing properties có thể thành null. Encode/replace mặc định có thể bỏ qua chúng; do vậy **đừng replace bằng một POJO chỉ được load một phần**.

### 28.4. Khi nào replace có thể phù hợp?

- Document đại diện aggregate root và mọi fields đã được load/validated.
- Có version field để optimistic concurrency.
- Schema được quản lý chặt.
- Yêu cầu overwrite có chủ đích.
- Không có writers/legacy fields ngoài model.

### 28.5. `_id` không được thay đổi

Nếu POJO mang một ID khác với document đích, replace có thể lỗi vì `_id` là immutable. Thiết kế ID consistent, tránh trộn ObjectId và String representation.

---

## 29. Projection và typed POJO

Giả sử query chỉ cần tên:

~~~java
Customer partial = customers.find(
    Filters.eq("_id", customerId)
).projection(
    Projections.include("full_name")
).first();
~~~

POJO có thể được tạo với:

~~~text
id        = ObjectId...
fullName  = "Nguyễn An"
loyaltyPoints = null
active    = null
~~~

### 29.1. Partial POJO không phải full entity

Nếu dùng `partial` để `replaceOne`, dữ liệu `loyalty_points`/`active` có thể bị mất.

### 29.2. Tốt hơn: dùng DTO/read model

Có thể dùng `Document` để đọc projection rồi map sang DTO:

~~~java
Document doc = customers
    .withDocumentClass(Document.class)
    .find(
        Filters.eq("_id", customerId)
    )
    .projection(
        Projections.include("full_name")
    )
    .first();

String name =
    doc == null ? null : doc.getString("full_name");
~~~

### 29.3. Aggregation có output shape khác entity

Nếu `$group` trả fields `_id` và `totalRevenue`, đó không phải một Customer POJO. Nên đọc bằng `Document` hoặc một report/read model tương ứng thay vì cố decode sang Customer.

---

## 30. Optimistic locking bằng version field

Một POJO có thể dùng version nghiệp vụ:

~~~javascript
{
  _id: ObjectId("6914ff000000000000000001"),
  full_name: "Nguyễn An",
  loyalty_points: 120,
  version: 3
}
~~~

### 30.1. Conditional update

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.set;

long expectedVersion = 3L;

var result = customers.updateOne(
    and(
        eq("_id", customerId),
        eq("version", expectedVersion)
    ),
    combine(
        set("loyalty_points", 130),
        inc("version", 1)
    )
);

if (result.getModifiedCount() != 1) {
    throw new IllegalStateException(
        "Optimistic concurrency conflict"
    );
}
~~~

### 30.2. Vì sao cần?

Hai requests đọc cùng entity rồi replace ở các thời điểm khác nhau có thể gây lost update. Version filter giúp một writer phát hiện dữ liệu đã đổi.

### 30.3. POJO codec không tự thêm optimistic locking

Một annotation `@BsonProperty("version")` chỉ map field; nó không tự biến `replaceOne` thành compare-and-swap. Business/application layer phải xây filter, update và retry policy.

---

## 31. Tên field trong Filters, Updates, Sorts và Indexes

Nếu:

~~~java
@BsonProperty("full_name")
private String fullName;
~~~

thì:

~~~java
Filters.eq("full_name", "Nguyễn An");
Updates.set("full_name", "Nguyễn Bình");
Sorts.ascending("full_name");
Indexes.ascending("full_name");
~~~

là cách tham chiếu field đã lưu.

### 31.1. Tránh magic strings rải rác

Một cách đơn giản:

~~~java
public final class CustomerFields {

    public static final String ID = "_id";
    public static final String FULL_NAME = "full_name";
    public static final String LOYALTY_POINTS = "loyalty_points";
    public static final String TENANT_ID = "tenant_id";

    private CustomerFields() {}
}
~~~

Dùng:

~~~java
Filters.eq(
    CustomerFields.FULL_NAME,
    "Nguyễn An"
);
~~~

### 31.2. Không suy từ Java getter bằng reflection ở mỗi query

Có thể tạo typed query DSL ở tầng ứng dụng, nhưng nếu tự reflection mapping, phải xử lý annotations, nested paths, polymorphism và custom conventions. Đừng tự viết một ORM chưa được kiểm thử chỉ để tránh vài constants.

### 31.3. Dotted paths sau rename

Nếu parent field đổi từ `shippingAddress` thành `shipping_address`, query path cũng cần đổi:

~~~java
Filters.eq(
    "shipping_address.city",
    "Hồ Chí Minh"
);
~~~

---

## 32. Codec registry order và lỗi xung đột

### 32.1. Registry được duyệt theo thứ tự

~~~java
CodecRegistry registry = fromRegistries(
    fromCodecs(new EmailAddressCodec()),
    MongoClientSettings.getDefaultCodecRegistry(),
    fromProviders(pojoProvider)
);
~~~

Codec custom ở đầu có thể được ưu tiên cho type `EmailAddress`.

### 32.2. Đặt POJO auto provider trước default có thể gây vấn đề

Nếu automatic POJO codec cố map một class mà default codec có support chuẩn, behavior có thể khác kỳ vọng. Cách cấu hình được MongoDB hướng dẫn thường đặt **default codec registry trước PojoCodecProvider**.

### 32.3. Multi-module application

Một module đăng ký codec custom cho Money, module khác tạo client mới với default registry. Kết quả: module này đọc được, module kia lỗi. Tạo shared database client/registry configuration và kiểm thử.

### 32.4. Dependency versions

`mongodb-driver-sync`, `mongodb-driver-core` và `bson` phải tương thích nhau. Classpath có JAR phiên bản xung đột gây runtime errors dù MongoDB Server không liên quan.

---

## 33. Cách chẩn đoán `CodecConfigurationException`

### 33.1. “Can't find a codec for class X”

Nguyên nhân:

- Chưa register `PojoCodecProvider`.
- Codec registry chỉ có default codecs.
- Nested class chưa được register trong explicit mode.
- Field type `Optional<T>`, interface hoặc generic chưa có codec.
- Đặt registry ở database khác, collection đang dùng client default.
- Custom type không có codec.
- Class/constructor/getters/setters không phù hợp.

Giải pháp:

1. Xem class bị thiếu codec.
2. Kiểm tra collection generic type thực tế.
3. In/đối chiếu codec registry configuration.
4. Register POJO/class/package hoặc custom codec.
5. Test encode/decode trên một document mẫu.

### 33.2. Exception ở property cụ thể

Nếu codec được tạo cho `Customer` nhưng lỗi ở `Money` field, không nhất thiết Customer thiếu codec; cần codec cho **nested property type**.

### 33.3. Không xác định đúng constructor

Nếu không có constructor không tham số hoặc `@BsonCreator` hợp lệ, driver có thể không tạo được instance khi decode.

### 33.4. Mapping sai tên trường

Truy vấn `Filters.eq("fullName",...)` trả không có kết quả vì BSON đang là `full_name`; đó **không phải lỗi codec**, mà là query dùng sai field key.

### 33.5. Enum value lạ

Nếu database có `"SUSPENDED"` nhưng enum Java không có giá trị đó, decoding có thể lỗi. Cần migration/fallback policy, không chỉ đổi registry.

### 33.6. Kiểu số không khớp

`Long` ↔ `Integer` hoặc `Decimal128` ↔ `Double` không được giả định convert âm thầm. Kiểm tra BSON type thực tế bằng `BsonDocument`.

---

## 34. Kiểm tra raw BSON khi POJO đọc sai

### 34.1. Xem document từ mongosh

~~~javascript
use java_codec_lab

db.customers.findOne({
  full_name: "Nguyễn An"
});
~~~

### 34.2. Xem bằng Document collection trong Java

~~~java
MongoCollection<Document> rawCustomers =
    database.getCollection(
        "customers",
        Document.class
    );

Document raw = rawCustomers.find(
    Filters.eq(
        "full_name",
        "Nguyễn An"
    )
).first();

if (raw != null) {
    System.out.println(raw.toJson());
}
~~~

### 34.3. So sánh ba thứ

- Raw BSON field names và BSON types.
- POJO annotations/conventions và Java field types.
- Filter/project/update paths mà ứng dụng gửi.

Ví dụ:

~~~text
Raw BSON:        loyalty_points (INT64)
POJO:            loyaltyPoints (Integer)
Query filter:    loyaltyPoints
~~~

Có ít nhất hai vấn đề: kiểu số và tên query field.

### 34.4. `toJson` dùng để quan sát, không phải chứng minh type equality

Extended JSON có nhiều dạng hiển thị (relaxed/canonical). Để xác định type chính xác, dùng BSON-aware inspection hoặc test decode.

---

## 35. Test round-trip an toàn trong lab

### 35.1. Tạo khách hàng

~~~java
Customer customer = new Customer();
customer.setFullName("Khách test");
customer.setLoyaltyPoints(25);
customer.setActive(true);
~~~

### 35.2. Insert rồi đọc đúng theo ID

~~~java
customers.insertOne(customer);

ObjectId id = customer.getId();

Customer actual = customers
    .find(Filters.eq("_id", id))
    .first();

if (actual == null) {
    throw new AssertionError(
        "Customer was not found"
    );
}

if (!"Khách test".equals(actual.getFullName())) {
    throw new AssertionError(
        "fullName round-trip failed"
    );
}

if (!Integer.valueOf(25)
        .equals(actual.getLoyaltyPoints())) {
    throw new AssertionError(
        "loyaltyPoints round-trip failed"
    );
}
~~~

### 35.3. Kiểm tra raw persisted schema

~~~java
Document raw = customers
    .withDocumentClass(Document.class)
    .find(Filters.eq("_id", id))
    .first();

if (raw == null
        || !raw.containsKey("full_name")) {
    throw new AssertionError(
        "BSON field full_name missing"
    );
}

if (raw.containsKey("fullName")) {
    throw new AssertionError(
        "Unexpected Java-style BSON field"
    );
}
~~~

### 35.4. Cleanup

~~~java
customers.deleteOne(
    Filters.eq("_id", id)
);
~~~

Chạy chỉ trên test database/collection. Trong test suite thực tế, nên dùng unique IDs, teardown và assertions framework (JUnit/AssertJ) để tránh test này đụng test khác.

### 35.5. Vì sao kiểm tra raw field quan trọng?

Nếu cả encoder và decoder cùng dùng sai field `fullName` thay vì contract `full_name`, test chỉ so Java properties có thể **vẫn pass**. Kiểm tra raw BSON giúp phát hiện mapping lệch với schema lưu trữ.

---

## 36. Test migrations và đổi tên field

Giả sử chuyển từ `customer_name` sang `full_name`.

### 36.1. Chuẩn bị document legacy

~~~javascript
db.customers.insertOne({
  _id: "legacy-101",
  customer_name: "Khách cũ",
  loyalty_points: 10
});
~~~

### 36.2. Đọc bằng mapping mới

Nếu POJO chỉ có `@BsonProperty("full_name")`, `fullName` có thể null. Không coi đây là lý do dữ liệu bị mất; field cũ vẫn tồn tại trong MongoDB.

### 36.3. Chọn phương án migration

- **Expand:** code đọc cả schema cũ/mới qua migration mapper.
- **Backfill:** chuyển giá trị cũ sang field mới.
- **Switch writes:** mọi phiên bản app dùng field mới theo rollout.
- **Contract:** xóa old field và old index sau khi hoàn tất.
- **Validate:** đếm documents thiếu field mới và kiểm tra dữ liệu.

### 36.4. Ví dụ migration giản lược (chỉ lab)

~~~javascript
db.customers.updateMany(
  {
    customer_name: { $exists: true },
    full_name: { $exists: false }
  },
  [
    {
      $set: {
        full_name: "$customer_name"
      }
    },
    {
      $unset: "customer_name"
    }
  ]
);
~~~

Trên production cần dry-run, quyền, rollback plan, batch/rate limit, xử lý duplicates/conflicts và audit trước khi chạy.

### 36.5. Kết hợp optimistic concurrency

Nếu app đang cập nhật cùng document, migration cần tránh ghi đè thay đổi mới. Có thể khóa writes trong cửa sổ nhỏ hoặc dùng version/generation CAS cùng bulk batches.

---

## 37. Naming policy trong hệ thống nhiều microservices

Hệ thống có Java, Node.js và Python clients cùng đọc một collection.

~~~text
Java service:    customerName
Node service:    customerName
Python service:  customer_name
MongoDB BSON:    full_name
~~~

Nếu mỗi service tự quyết định mapping, nguy cơ mỗi bên ghi một field khác nhau.

### 37.1. Schema contract là nguồn thống nhất

Quy định BSON schema độc lập language:

~~~yaml
collection: customers
fields:
  _id: objectId
  tenant_id: string
  full_name: string
  loyalty_points: int32
  created_at: date
~~~

Đây là một **schema contract mẫu**, không phải cấu hình MongoDB tự áp dụng. Có thể dùng `$jsonSchema` validator để enforce phần phù hợp.

### 37.2. Contract tests

- Java serialize đúng field names.
- Node/Python đọc đúng.
- Không có cả `full_name` và `fullName` ngoài migration window.
- Nullable/default behavior được xác định.
- Date precision và timezone thống nhất.
- Currency/Decimal128 schema rõ ràng.

### 37.3. Versioning

Khi đổi BSON field, thông báo các teams dùng chung collection. Đừng đổi annotation trong một repo rồi cho rằng mọi clients đã tự thích nghi.

---

## 38. Performance: chi phí POJO mapping và Document

### 38.1. POJO không mặc định nhanh hơn mọi trường hợp

Driver codec encode/decode theo type. POJO có lợi về type safety, nhưng performance phụ thuộc:

- Codec cache/reflection/model initialization.
- BSON types.
- Kích thước documents.
- Số field/nested arrays.
- Projection.
- Serialization ở HTTP boundary.
- Network/query/index overhead.

Với đa số CRUD, query plan/index/network thường quan trọng hơn chênh lệch nhỏ của POJO vs `Document`.

### 38.2. Document tốt cho shape động

Aggregation trả fields không cố định (ví dụ pivot/dashboard) có thể dùng `Document` để tránh tạo nhiều POJOs một lần.

### 38.3. POJO tốt cho domain model ổn định

Định nghĩa type giúp:

- Catch một số lỗi compile-time.
- Validation của domain logic.
- IDE refactoring.
- Unit tests.
- API/service signatures rõ.
- Cấu trúc nested dễ hiểu.

### 38.4. Projection giảm payload

Nếu chỉ cần hai fields, đừng decode hàng trăm fields. Nhưng tránh dùng partial POJO rồi replace toàn entity.

### 38.5. Benchmark đúng

Đo p50/p95/p99 latency và CPU khi:

- Query raw `Document`.
- Query typed POJO.
- Projection nhỏ.
- Read nhiều nested items.
- Đồng thời 100 requests.
- Với data size/index/schema giống production.

Không đưa ra số phần trăm “POJO nhanh hơn X%” nếu chưa đo trên workload thực.

---

## 39. Bảo mật và validation khi ánh xạ BSON

### 39.1. Không tin dữ liệu người dùng

Một API nhận arbitrary JSON rồi biến thẳng thành `Document` để update DB có thể cho user sửa:

- `tenant_id`.
- `role`.
- `is_admin`.
- `balance`.
- `deleted_at`.
- `schema_version`.
- Fields chứa flags/security metadata.

Nên dùng DTO whitelist và explicit update fields, không truyền raw client map vào update/replace.

### 39.2. Tên field do người dùng cung cấp

Nếu user gửi path như `"tenant_id"` hoặc `"$where"`, không cho phép nó trở thành arbitrary query/update operator. Xây API an toàn theo allowlist.

### 39.3. Tenant isolation

~~~java
Filters.and(
    Filters.eq("tenant_id", trustedTenantId),
    Filters.eq("_id", customerId)
);
~~~

`trustedTenantId` phải lấy từ authenticated server context, không lấy từ request JSON bất kỳ.

### 39.4. Ẩn nhạy cảm ở logs

`Document.toJson()` có thể in toàn bộ password reset token, PII hay payment details. Chỉ log allowlisted fields hoặc redact trước khi in.

### 39.5. Codec không phải data encryption

PojoCodec và annotations map fields/types. Nếu cần encryption (CSFLE/Queryable Encryption), cần library/config/KMS/keys tương ứng; không xem `@BsonIgnore` hoặc `@BsonProperty` như cơ chế mã hóa.

---

## 40. Troubleshooting nhanh

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Can't find a codec for class Customer` | Chưa đăng ký POJO provider | Thêm provider vào registry |
| `Can't find a codec for class Money` | Nested custom type thiếu codec | Register custom codec |
| `fullName == null` sau find | BSON là `full_name` nhưng annotation thiếu/sai | Kiểm tra raw BSON, mapping |
| `find(eq("fullName",...))` không trả rows | Sai tên BSON field | Dùng `full_name` |
| `@BsonProperty` không có hiệu lực | Annotation convention bị bỏ | Bật `ANNOTATION_CONVENTION` |
| Không tạo được POJO | Thiếu no-arg constructor/creator | Thêm public ctor hoặc `@BsonCreator` |
| Property private không được set | Thiếu setter/convention | JavaBean setter hoặc private field convention |
| Bị mất field sau `replaceOne` | POJO thiếu field hoặc partial projection | Dùng `$set`/DTO/full entity |
| Enum decode lỗi | DB có giá trị không nằm trong enum | Migration/fallback codec |
| Integer/Long mismatch | Legacy BSON numeric types khác | Schema migration/type check |
| UUID query không thấy ID | Binary representation mismatch | Kiểm tra subtype/config |
| Date lệch giờ | Dùng LocalDateTime sai timezone | Instant/UTC + business zone |
| Không map nested POJO | Nested type thiếu codec | Register nested type |
| Unknown field không giữ lại | POJO không map field | `@BsonExtraElements` hoặc migration |
| JSON đúng mà BSON sai | Nhầm Jackson annotation với BSON | Tách `@JsonProperty`/`@BsonProperty` |
| Lỗi sau nâng driver | Version conflict/behavior đổi | Kiểm tra dependency + round-trip tests |
| `@BsonRepresentation` gây lỗi | Type codec không hỗ trợ representation | Custom codec/đổi schema |
| Query index không được dùng | Index theo Java name, BSON khác | Index theo field thực |

---

## 41. Checklist thiết kế POJO mapping

### 41.1. Model

- [ ] Class thuộc domain rõ, không dùng raw map cho mọi entity.
- [ ] Có constructor/getters/setters hoặc `@BsonCreator` hợp lệ.
- [ ] ID map đúng `_id` và BSON type.
- [ ] Null/missing/default được định nghĩa.
- [ ] Nested classes, enum, UUID và custom types có codec.
- [ ] Không lưu property runtime-only ngoài ý muốn.
- [ ] Không dùng Java record với cấu hình POJO class không phù hợp.

### 41.2. Codec

- [ ] Có `PojoCodecProvider`/registered classes.
- [ ] Có default registry cho built-in types.
- [ ] Registry được áp đúng client/database/collection.
- [ ] Conventions gồm annotation processing khi cần.
- [ ] Custom codecs có thứ tự ưu tiên đúng.
- [ ] Đã kiểm tra incompatibilities của các driver JARs.

### 41.3. Naming

- [ ] Java properties và BSON names có policy rõ.
- [ ] `@BsonProperty` dùng cho khác tên.
- [ ] `Filters`/`Updates`/`Indexes` dùng BSON key thực.
- [ ] API JSON mapping tách biệt với BSON.
- [ ] Dotted paths và array/map keys hợp lệ.
- [ ] Có field constants/schema contract nếu dùng nhiều services.
- [ ] Có plan migrate old field names.

### 41.4. Data correctness

- [ ] Round-trip tests trên actual MongoDB.
- [ ] Kiểm tra raw BSON field names/types.
- [ ] Test missing/null/zero.
- [ ] Test numeric precision/Decimal128.
- [ ] Test timezones và Date precision.
- [ ] Test legacy documents và unknown fields.
- [ ] Không replace partial POJO.
- [ ] Có optimistic concurrency nếu data có concurrent writers.
- [ ] Có database schema validation phù hợp.

### 41.5. Security

- [ ] Tenant ID từ trusted context.
- [ ] Input DTO whitelist.
- [ ] Không expose arbitrary update fields.
- [ ] Sensitive fields được redact trong logs.
- [ ] Encryption/roles/permissions ngoài POJO codec vẫn được bảo vệ.

---

## 42. Bài tập thực hành

### Bài tập 1 — Document cơ bản

Tạo `Document` cho customer gồm `_id`, `full_name`, `loyalty_points` và `active`. Insert vào collection lab, find bằng `full_name`, in `toJson()`.

### Bài tập 2 — Nested document

Tạo order có `shipping_address.city` và `items` array. Dùng `get("shipping_address", Document.class)` đọc city.

### Bài tập 3 — Missing vs null

Tạo hai documents: field `loyalty_points` missing và explicit null. Kiểm tra `containsKey`/`get` và so với MongoDB `$exists`.

### Bài tập 4 — BsonDocument types

Tạo một field `Int32` và một field `Int64` có cùng giá trị 10. Xác minh BSON type khác nhau.

### Bài tập 5 — POJO codec registration

Tạo `Customer` với public no-arg constructor, getters/setters. Kết hợp `PojoCodecProvider` với default registry, insert/fetch qua `MongoCollection<Customer>`.

### Bài tập 6 — `@BsonProperty`

Đổi Java property `fullName` map BSON `full_name`. Test raw persisted document có đúng field.

### Bài tập 7 — Query name trap

Thử `Filters.eq("fullName",...)` và `Filters.eq("full_name",...)`; giải thích vì sao một query không tìm ra khách.

### Bài tập 8 — `@BsonId`

Dùng `ObjectId id` annotated, insert khi id null. Đọc ID từ result/entity rồi query bằng đúng BSON type.

### Bài tập 9 — String ObjectId representation

Tạo model dùng `String id` và `@BsonRepresentation(BsonType.OBJECT_ID)`. So sánh raw BSON với model dùng string ID không annotation.

### Bài tập 10 — `@BsonIgnore`

Thêm property chỉ để cache `displayLabelCache`. Xác nhận nó không nằm trong BSON sau insert.

### Bài tập 11 — `@BsonCreator`

Tạo immutable `CountryCode` với constructor có tham số annotated. Insert/read nested object và kiểm tra invariants.

### Bài tập 12 — Private fields convention

Tạo POJO thiếu setter cho một private field, cấu hình `SET_PRIVATE_FIELDS_CONVENTION`, test decode và so sánh với cấu hình mặc định.

### Bài tập 13 — Java record

Tạo record đọc từ BSON với default registry theo tài liệu record codec. So sánh với POJO mutable.

### Bài tập 14 — Nested POJO

Tạo `Order` chứa `Address` và `List<OrderItem>`. Đăng ký nested codecs đúng và đọc lại.

### Bài tập 15 — Enum và legacy value

Lưu enum `ACTIVE`; thêm document chứa status `SUSPENDED` chưa có trong enum. Quan sát lỗi decode và đề xuất migration.

### Bài tập 16 — Unknown fields

Thêm field `preferred_language` vào BSON mà POJO cũ không biết. Dùng `@BsonExtraElements` để giữ giá trị đó.

### Bài tập 17 — Null serialization

Insert POJO có `Integer loyaltyPoints=null`. So sánh raw BSON với document có field null explicit.

### Bài tập 18 — PATCH vs replace

Tạo document có field `preferred_language` không có trong POJO. Dùng `replaceOne` bằng POJO partial rồi quan sát mất field trong lab; sau đó dùng `Updates.set` để chỉ thay một field.

### Bài tập 19 — Decimal128

Lưu giá trị tiền `123.45` bằng `Decimal128(BigDecimal)`. Xác nhận không biến thành `Double`.

### Bài tập 20 — Instant precision

Lưu `Instant` có nanoseconds rồi đọc lại. Mô tả precision BSON Date và cách normalize milliseconds.

### Bài tập 21 — UUID

Tạo record với UUID STANDARD representation. Kiểm tra BSON binary subtype; giải thích nguy cơ với legacy representation.

### Bài tập 22 — Schema rename migration

Chuyển `customer_name` sang `full_name` theo expand/migrate/contract và kiểm tra cả Java và MongoDB queries.

### Bài tập 23 — Optimistic locking

Thêm `version`, dùng filter `_id + version` để update, mô phỏng hai writers và xác định conflict.

### Bài tập 24 — DTO vs Entity

Thiết kế HTTP DTO với `customerName` nhưng MongoDB entity có `full_name`. Nêu cách giữ ranh giới Jackson/BSON rõ ràng.

### Bài tập 25 — Codec tùy chỉnh

Tạo `EmailAddressCodec` encode/decode BSON string và kiểm thử invalid/valid email.

### Bài tập 26 — Naming convention

Thiết kế rule snake_case cho `customerName`, `apiURL`, `createdAt` và `_id`. Dùng test cases để tránh convention đổi tên ID hoặc annotation explicit.

### Bài tập 27 — Partial projection

Đọc `Customer` bằng projection chỉ gồm `full_name`, giải thích vì sao không `replaceOne` từ partial entity.

### Bài tập 28 — Data compatibility

Tạo các documents có `loyalty_points` là Int32, Int64, null, missing. Đề xuất schema migration/validation và test POJO decode.

### Bài tập 29 — Security

Thiết kế API chỉ cho user sửa `full_name`. Ngăn request JSON sửa `tenant_id`, `role` hoặc `balance`.

### Bài tập 30 — Full integration lab

Tạo collection `customers`, model POJO, registry, indexes, CRUD, update/version, raw BSON assertion, migration test và cleanup. Không chạy trên dữ liệu production.

---

## 43. Câu hỏi ôn tập

1. BSON khác JSON ở đâu?
2. `Document` là gì?
3. Khi nào nên dùng `Document` thay POJO?
4. `BsonDocument` khác `Document` thế nào?
5. Codec là gì?
6. `CodecRegistry` dùng để làm gì?
7. `PojoCodecProvider` làm gì?
8. Vì sao không chỉ tạo class Java là có thể deserialize tự động?
9. Tại sao phải kết hợp default codec registry?
10. `automatic(true)` khác explicit `register(...)` ra sao?
11. `MongoCollection<Customer>` có tự ánh xạ tên filter string không?
12. `@BsonId` map tới BSON field nào?
13. `@BsonProperty("full_name")` có nghĩa gì?
14. Query nên dùng `fullName` hay `full_name` nếu data lưu snake_case?
15. `@JsonProperty` có đổi MongoDB BSON field không?
16. Vì sao không nên trộn API DTO và persistence entity tùy tiện?
17. Default POJO codec tạo object bằng constructor nào?
18. `@BsonCreator` giúp giải quyết tình huống nào?
19. Các tham số constructor `@BsonCreator` cần annotation gì?
20. `@BsonIgnore` khác field `transient` và logic API privacy thế nào?
21. `SET_PRIVATE_FIELDS_CONVENTION` dùng để làm gì?
22. Tại sao JavaBean naming convention quan trọng?
23. Java record có đặc điểm gì khác mutable POJO?
24. `Conventions.DEFAULT_CONVENTIONS` gồm gì?
25. Vì sao ordering giữa conventions quan trọng?
26. `ClassModel` và `PropertyModel` khác nhau ra sao?
27. Khi nào nên dùng custom convention thay `@BsonProperty`?
28. Vì sao cần xử lý acronym khi camelCase → snake_case?
29. `@BsonRepresentation` có chuyển mọi kiểu tùy ý không?
30. ObjectId BSON khác string chứa ObjectId hex ra sao?
31. Tại sao enum rename có thể làm documents cũ không decode được?
32. `@BsonExtraElements` giải quyết vấn đề gì?
33. Khi nào unknown fields có nguy cơ mất?
34. Missing và explicit null khác nhau ở MongoDB ra sao?
35. Primitive default values có thể che giấu schema missing như thế nào?
36. Default POJO codec thường serialize null properties ra sao?
37. Vì sao không nên dùng replace cho HTTP PATCH?
38. `replaceOne` khác `Updates.set` thế nào?
39. Vì sao partial projection không nên dùng làm full entity replacement?
40. Decimal128 phù hợp cho dữ liệu nào?
41. Vì sao double nguy hiểm với tiền?
42. BSON Date giữ precision gì?
43. `Instant` khác `LocalDateTime` như thế nào?
44. UUID representation mismatch gây lỗi gì?
45. `List<OrderItem>` cần những codecs nào?
46. Vì sao `Map` keys cần validation?
47. Polymorphic POJO cần discriminator khi nào?
48. Codec registry order có tác động gì?
49. `CodecConfigurationException` thường do những nguyên nhân nào?
50. Vì sao raw BSON verification quan trọng dù POJO round-trip đã pass?
51. Schema migration đổi tên field cần những bước nào?
52. Những trường nào nên nằm trong schema contract đa ngôn ngữ?
53. Optimistic concurrency có do POJO codec tự sinh ra không?
54. Khi nào cần database `$jsonSchema` validator?
55. Một hệ thống đã dùng POJO có còn cần kiểm tra quyền tenant và input whitelist không?

---

## 44. Tổng kết

Khi truy cập MongoDB bằng Java, dữ liệu luôn đi qua tầng chuyển đổi giữa **Java objects** và **BSON**. Tùy nhu cầu, ta có thể dùng `Document` để thao tác linh hoạt hoặc POJO để có kiểu rõ, API domain ổn định và code dễ bảo trì.

Những điểm phải nhớ:

1. **`Document` là cấu trúc linh hoạt**, thích hợp schema động và aggregation output, nhưng đòi kiểm tra runtime types.
2. **POJO codec cần được cấu hình**: `PojoCodecProvider` kết hợp default `CodecRegistry` và áp vào client/database/collection.
3. **Tên Java property không nhất thiết là tên BSON**: `@BsonProperty` map tên; `Filters`, `Updates` và indexes vẫn dùng tên BSON đã lưu.
4. **`@BsonId` xác định `_id`**, còn `@BsonCreator` hỗ trợ constructor-based decoding khi không dùng no-arg constructor.
5. **Null, missing, default values và unknown fields khác nhau**: đừng dùng POJO replacement làm mất fields ngoài ý muốn.
6. **Nested types, enums, money, dates và UUID cần mapping contract rõ ràng**; không tin vào ép kiểu tự động.
7. **Đổi tên field là schema migration**, không chỉ thay annotation trong code.
8. **Codec registry order quan trọng** khi có custom types và custom conventions.
9. **Kiểm thử cả hai chiều và raw BSON thực tế**, vì encode và decode cùng một mapping sai vẫn có thể pass round-trip test.
10. **Security và data validation nằm ngoài mapping**: POJO không tự giải quyết tenant isolation, quyền ghi, schema invariants hoặc encryption.

**Câu hỏi kiểm tra cuối cùng:** Sau khi đổi tên một Java property từ `fullName` sang `displayName`, ứng dụng còn đọc được BSON `full_name` của tuần trước, query/index có còn đúng và update có làm mất những field mới của một service khác không? Nếu có thể trả lời và chứng minh các câu hỏi đó, bạn đã thực sự kiểm soát được tầng ánh xạ dữ liệu.

## Tài liệu tham khảo

- [MongoDB Java Sync Driver — Document Data Format: Documents](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/documents/)
- [MongoDB Java Sync Driver — Document Data Format: POJOs](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/document-data-format-pojo/)
- [MongoDB Java Sync Driver — POJO Customization](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/pojo-customization/)
- [MongoDB Java Sync Driver — Document Data Format: Records](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/document-data-format-record/)
- [MongoDB Java Sync Driver — Encode Data with Type Codecs](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/codecs/)
- [MongoDB Java Sync Driver — BSON Data Formats](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/)
- [MongoDB Java Sync Driver — Read Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [MongoDB Java Sync Driver — Update Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/)
- [MongoDB Java Sync Driver — Insert Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/insert/)
- [MongoDB Java Sync Driver — BSON Type Mapping](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/bson/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Extended JSON](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/)
- [MongoDB Manual — Field Names](https://www.mongodb.com/docs/manual/core/dot-dollar-considerations/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Java Driver Javadoc — POJO Codecs](https://mongodb.github.io/mongo-java-driver/5.6/apidocs/bson/org/bson/codecs/pojo/package-summary.html)
