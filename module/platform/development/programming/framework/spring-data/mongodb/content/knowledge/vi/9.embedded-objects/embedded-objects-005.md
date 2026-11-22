# Ánh xạ value object thành document lồng nhau

## 1. Value object trong mô hình document MongoDB

Trong chương **Đối tượng và nhúng** của **Spring Data MongoDB**, một nhiệm vụ quan trọng là biểu diễn các **value object** của miền nghiệp vụ dưới dạng document lồng bên trong document gốc. Việc này giúp ứng dụng Java giữ được mô hình đối tượng có ý nghĩa, đồng thời khai thác cấu trúc document của MongoDB để truy vấn và cập nhật dữ liệu qua `MongoTemplate` hoặc `MongoRepository`.

**Value object** là đối tượng được nhận diện chủ yếu bởi *giá trị các thuộc tính* thay vì một ID độc lập. Ví dụ:

- Một địa chỉ giao hàng gồm đường, thành phố và mã bưu chính.
- Một số tiền gồm giá trị thập phân và đơn vị tiền tệ.
- Một dòng hàng trong đơn gồm SKU, tên hàng tại lúc mua, số lượng và đơn giá.
- Một khoảng thời gian gồm thời điểm bắt đầu và kết thúc.

Trong một đơn hàng, địa chỉ giao hàng thường là **ảnh chụp tại lúc đặt**. Khi người mua đổi địa chỉ mặc định, địa chỉ đã chốt trong đơn không nên tự động đổi. Value object lồng trong đơn giúp diễn đạt chính sách vòng đời này rõ ràng.

Value object khác entity ở một số điểm:

| Câu hỏi | Value object | Entity |
|---|---|---|
| Nhận diện bằng gì? | Tập giá trị và ý nghĩa nghiệp vụ | ID ổn định qua các thay đổi trạng thái |
| Vòng đời | Thường thuộc về aggregate/document cha | Có thể tồn tại và phát triển độc lập |
| Thay đổi | Thường tạo giá trị mới thay vì sửa trực tiếp đối tượng cũ | Trạng thái có thể thay đổi nhưng ID vẫn giữ |
| Ví dụ | `ShippingAddress`, `Money` | `PurchaseOrder`, `Customer` |
| Cách lưu thường gặp | Embedded document trong cha | Document gốc có `_id`; có thể được tham chiếu |

Đây là **hướng thiết kế**, không phải quy tắc cứng: một địa chỉ có thể là entity khi chính nghiệp vụ cần quản lý, phê duyệt và tham chiếu địa chỉ đó độc lập. Việc một class có hay không có `@Document` cũng không tự quyết định nó có phải value object theo nghiệp vụ hay không.

> Các ví dụ dùng Java 17+, Spring Boot 3.x và Spring Data MongoDB 4.x. Với phiên bản khác, hãy kiểm tra lại API/metadata mapping tương ứng. MongoDB Java Driver ở tầng thấp dùng BSON, còn các ví dụ chính sử dụng Spring Data mapping.

## 2. Quyết định nhúng value object khi nào?

MongoDB lưu một document dưới dạng các cặp khóa–giá trị, trong đó một giá trị có thể là **document con** hoặc **mảng document con**. Vì vậy một aggregate có thể được biểu diễn gần với cách ứng dụng đọc nó:

~~~mermaid
flowchart TD
    O["PurchaseOrder - document gốc"] --> A["ShippingAddress - document con"]
    O --> L["items - mảng OrderLine"]
    L --> M["Money - đơn giá trong mỗi dòng"]
    O --> T["Money - tổng tiền"]
    O --> I["id, customerId, placedAt"]
~~~

Nên cân nhắc nhúng khi:

1. Value object thường được đọc cùng document cha.
2. Value object không có vòng đời cập nhật độc lập hoặc không cần ID riêng.
3. Số lượng phần tử lồng được **giới hạn theo nghiệp vụ**, và tổng kích thước document luôn có thể kiểm soát.
4. Các trường cần thay đổi nhất quán có thể được cập nhật trong cùng document.

Không nên nhúng vô hạn lịch sử giao dịch, lượt xem, đánh giá hoặc các sự kiện phát sinh liên tục vào một document. MongoDB có giới hạn kích thước **16 MiB cho một BSON document**; ngay cả trước giới hạn này, document quá lớn cũng khiến đọc, ghi, quản lý index và xử lý xung đột trở nên khó khăn.

**Nhúng không đồng nghĩa với nhân bản tùy tiện.** Một `ShippingAddress` chụp tại thời điểm mua khác với địa chỉ mặc định hiện tại của khách hàng. Tương tự, đơn giá đã chốt trong `OrderLine` không được đồng bộ lại khi giá niêm yết của sản phẩm thay đổi.

## 3. Ví dụ hoàn chỉnh: aggregate có nhiều value object

Ta xây dựng các kiểu trong package `com.example.orders`. Document gốc `PurchaseOrder` chứa địa chỉ giao hàng, danh sách dòng hàng và tổng tiền. Các value object được biểu diễn bằng **Java record** để nhấn mạnh tính chất dữ liệu theo giá trị.

### 3.1. Address là value object lồng trong đơn hàng

**ShippingAddress.java**

~~~java
package com.example.orders;

import org.springframework.data.mongodb.core.mapping.Field;

public record ShippingAddress(
        String street,
        String city,
        @Field("postal_code") String postalCode) {
}
~~~

`ShippingAddress` không có `@Id` hay `@Document` vì nó không cần collection riêng trong ví dụ. `@Field("postal_code")` nói rằng property Java `postalCode` được lưu dưới trường BSON `postal_code`.

### 3.2. Money là value object với kiểu BSON rõ ràng

**Money.java**

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.util.Objects;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;

public record Money(
        @Field(targetType = FieldType.DECIMAL128) BigDecimal amount,
        String currency) {

    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }
}
~~~

`Money` gồm cả **số tiền** và **đơn vị tiền tệ**. Không nên so sánh hai số tiền khác đơn vị như thể chúng tương đương. Việc dùng `BigDecimal` tránh sai số biểu diễn thường gặp của `double` trong tính toán tiền; `FieldType.DECIMAL128` yêu cầu biểu diễn trường `amount` theo BSON Decimal128 khi được mapping.

BSON Decimal128 có giới hạn về độ chính xác và miền giá trị. Các quy tắc làm tròn, scale, đơn vị nhỏ nhất và quy đổi tiền tệ vẫn là trách nhiệm của tầng nghiệp vụ. Kiểm tra dữ liệu cũ trước khi đổi cách lưu từ String hoặc Double sang Decimal128.

### 3.3. Một dòng hàng chứa value object khác

**OrderLine.java**

~~~java
package com.example.orders;

public record OrderLine(
        String sku,
        String titleAtPurchase,
        int quantity,
        Money unitPrice) {
}
~~~

Một `OrderLine` chứa một `Money` khác. Đây là **đồ thị value object nhiều tầng**:

~~~text
PurchaseOrder
  ├─ shippingAddress: ShippingAddress
  ├─ items: List<OrderLine>
  │    └─ unitPrice: Money
  └─ subtotal: Money
~~~

`titleAtPurchase` và `unitPrice` là thông tin đã chốt của giao dịch. Nếu `OrderLine` cần lịch sử chỉnh sửa riêng, mã định danh dòng hàng hoặc vòng đời độc lập, phải đánh giá lại nó còn là value object thuần túy hay không.

### 3.4. Document gốc có định danh riêng

**PurchaseOrder.java**

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record PurchaseOrder(
        @MongoId(FieldType.STRING) String id,
        String customerId,
        @Field("ship_to") ShippingAddress shippingAddress,
        List<OrderLine> items,
        Money subtotal,
        Instant placedAt) {
}
~~~

`@Document(collection = "orders")` gắn aggregate root với collection `orders`. `@MongoId(FieldType.STRING)` ánh xạ ID thành `_id` kiểu BSON String một cách tường minh; điều này tránh việc một chuỗi trông giống ObjectId được chuyển kiểu ngoài mong muốn. `@Field("ship_to")` đổi tên field chứa địa chỉ, còn class `ShippingAddress` vẫn giữ property Java `postalCode`.

Khi lưu object dưới đây qua `MongoTemplate`:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

PurchaseOrder order = new PurchaseOrder(
        "order-9001",
        "customer-101",
        new ShippingAddress("12 Đường Ví Dụ", "Hà Nội", "100000"),
        List.of(new OrderLine(
                "BOTTLE-500",
                "Bình nước 500 ml",
                2,
                new Money(new BigDecimal("129000.00"), "VND"))),
        new Money(new BigDecimal("258000.00"), "VND"),
        Instant.parse("2026-11-20T08:00:00Z"));

mongoTemplate.save(order);
~~~

Giả sử `mongoTemplate` là bean được inject trong service. Document BSON thu được có cấu trúc tương tự sau; biểu diễn ngày và Decimal128 bằng **MongoDB Extended JSON**, lược bỏ metadata kiểu `_class` nếu có:

~~~json
{
  "_id": "order-9001",
  "customerId": "customer-101",
  "ship_to": {
    "street": "12 Đường Ví Dụ",
    "city": "Hà Nội",
    "postal_code": "100000"
  },
  "items": [
    {
      "sku": "BOTTLE-500",
      "titleAtPurchase": "Bình nước 500 ml",
      "quantity": 2,
      "unitPrice": {
        "amount": { "$numberDecimal": "129000.00" },
        "currency": "VND"
      }
    }
  ],
  "subtotal": {
    "amount": { "$numberDecimal": "258000.00" },
    "currency": "VND"
  },
  "placedAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

Một lần đọc `PurchaseOrder` có thể khôi phục các value object ở nhiều tầng mà không phải truy vấn collection địa chỉ hay tiền tệ riêng. MongoDB không áp đặt khái niệm aggregate của Domain-Driven Design; chính ứng dụng quyết định giới hạn bất biến và cách cập nhật.

## 4. Mapping thực hiện những bước nào?

Với một entity được truy cập qua `MongoTemplate` hoặc `MongoRepository`, Spring Data MongoDB thường sử dụng `MongoMappingContext` và `MappingMongoConverter` để:

1. Xác định metadata của document gốc, bao gồm collection và `_id`.
2. Đọc metadata property/annotation của từng kiểu Java.
3. Ghi các scalar property, rồi chuyển từng value object sang document con.
4. Duyệt collection như `List<OrderLine>` để ghi thành mảng document.
5. Khi đọc, dựng lại object gốc và từng object con bằng constructor/phương thức tạo phù hợp.

| Property Java | Vị trí BSON | Ghi chú |
|---|---|---|
| `PurchaseOrder.id` | `_id` | `@MongoId(FieldType.STRING)` của aggregate root |
| `PurchaseOrder.shippingAddress` | `ship_to` | Đổi tên bằng `@Field` |
| `ShippingAddress.postalCode` | `ship_to.postal_code` | Đổi tên trên value object lồng |
| `PurchaseOrder.items` | `items` | Mảng BSON |
| `OrderLine.unitPrice.amount` | `items[].unitPrice.amount` | Giá trị Decimal128 trong từng phần tử |
| `PurchaseOrder.subtotal.amount` | `subtotal.amount` | Decimal128 |
| `PurchaseOrder.placedAt` | `placedAt` | BSON Date theo conversion hỗ trợ |

**Không cần gắn `@Document` lên mọi value object.** Spring Data có thể lưu class thông thường hoặc record như một document nhúng khi nó là property của aggregate root. Ngược lại, nếu đăng ký một custom converter cho value object để viết ra kiểu BSON đơn giản như String, hình dạng lưu trữ có thể **không còn là document nhúng**. Hãy quyết định và kiểm thử representation.

### Đặt @Id lên value object có ý nghĩa gì?

`@Id` không phải marker để nói “đây là object trong MongoDB”. Nó chỉ định property dùng làm ID và có mapping đặc biệt tới `_id`. Value object không cần nhận diện độc lập thường **không cần `@Id`**; thêm ID có thể làm người đọc hiểu sai ngữ nghĩa bằng nhau theo giá trị.

MongoDB chỉ bảo đảm duy nhất `_id` của mỗi **document gốc trong collection**, không cấp ID toàn cục cho mọi object lồng. Nếu nghiệp vụ thực sự yêu cầu định danh từng phần tử mảng để cập nhật chính xác, có thể bổ sung **khóa phần tử trong mảng** do ứng dụng quản lý, hoặc xem xét đưa phần tử thành entity/document riêng.

## 5. Constructor mapping và tính bất biến

Value object thường được xây dựng bất biến để tránh thay đổi trạng thái không kiểm soát. Java record cung cấp canonical constructor và các accessor theo tên component; Spring Data có thể dùng metadata đó để khôi phục object khi đọc.

Trong ví dụ:

- `ShippingAddress("...", "...", "...")` được dựng từ các trường `street`, `city`, `postal_code`.
- `OrderLine` được dựng từ các field của phần tử mảng, gồm `Money` con.
- `PurchaseOrder` được dựng sau khi các giá trị thành phần đã được chuyển đổi.

Hai record có cùng giá trị thành phần thường bằng nhau theo `equals` do record sinh ra. Điều này phù hợp với value object, nhưng cần nhớ `BigDecimal.equals` phân biệt scale, ví dụ `1.0` khác `1.00` theo `equals`. Nếu miền nghiệp vụ muốn so sánh số tiền theo giá trị số học, phải định nghĩa quy tắc chuẩn hóa, tỷ giá hoặc so sánh tương ứng. Không dùng mặc định `equals` làm thay thế cho chính sách tiền tệ.

### 5.1. Dùng class bất biến thay cho record

Với class có nhiều constructor hoặc muốn kiểm soát invariant chặt hơn, có thể dùng `@PersistenceCreator` để chỉ rõ cách khôi phục object:

~~~java
package com.example.orders;

import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.mongodb.core.mapping.Field;

public final class ContactValue {
    @Field("contact_name")
    private final String name;
    private final String phone;

    @PersistenceCreator
    public ContactValue(String name, String phone) {
        this.name = name;
        this.phone = phone;
    }

    public ContactValue(String name) {
        this(name, null);
    }

    public String getName() { return name; }
    public String getPhone() { return phone; }
}
~~~

Giả sử `ContactValue` là property của một entity được mapping, constructor được đánh dấu nhận `name` và `phone` theo **tên property Java**; annotation `@Field("contact_name")` chuyển đổi với tên BSON. Với class thông thường, cần cung cấp metadata tên tham số constructor phù hợp, ví dụ biên dịch với `-parameters`. Nếu thiếu tên tham số hoặc một property không materialize được, quá trình đọc có thể thất bại.

Một constructor của value object nên kiểm tra invariant thuần túy, ví dụ không cho mã tiền tệ rỗng. Tránh gọi API ngoài, gửi email hoặc ghi database trong constructor: một lần đọc document có thể dựng nhiều value object.

### 5.2. Immutable record vẫn có thể chứa đối tượng mutable

`record PurchaseOrder(..., List<OrderLine> items, ...)` chỉ làm **reference tới list** bất biến, không tự làm mutable `ArrayList` bên trong trở nên immutable. Nếu caller truyền list có thể thay đổi, trạng thái aggregate trong bộ nhớ vẫn có thể thay đổi qua list đó.

Có thể sao chép phòng vệ trong canonical constructor:

~~~java
public PurchaseOrder {
    items = List.copyOf(items);
}
~~~

Đoạn trên là phần thân constructor đặt **bên trong record `PurchaseOrder`** của ví dụ, không phải một class riêng. Nó yêu cầu `items` khác null và các phần tử không null; nếu collection cũ thiếu trường `items`, đọc document có thể gặp lỗi. Vì vậy, khi thêm constraint hoặc constructor validation mới, phải có chiến lược tương thích dữ liệu cũ.

## 6. Truy vấn theo field lồng nhau

Spring Data MongoDB cho phép truy vấn bằng **đường dẫn property Java** khi có entity class làm ngữ cảnh mapping. Ví dụ tìm đơn có mã bưu chính `100000`:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<PurchaseOrder> byPostalCode(
        MongoTemplate template, String postalCode) {
    Query query = Query.query(
            Criteria.where("shippingAddress.postalCode").is(postalCode));
    return template.find(query, PurchaseOrder.class);
}
~~~

Spring Data dùng metadata `@Field` của `PurchaseOrder` và `ShippingAddress` để ánh xạ đường dẫn `shippingAddress.postalCode` thành **`ship_to.postal_code`** trong BSON.

Truy vấn bằng MongoDB shell hoặc Java Driver trực tiếp phải dùng tên BSON:

~~~javascript
db.orders.find({ "ship_to.postal_code": "100000" });
~~~

Tương tự, repository có thể khai báo derived query:

~~~java
package com.example.orders;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PurchaseOrderRepository
        extends MongoRepository<PurchaseOrder, String> {

    List<PurchaseOrder> findByShippingAddress_City(String city);
}
~~~

Dấu gạch dưới trong `findByShippingAddress_City` là cách chỉ rõ điểm phân tách đường dẫn nested property trong tên phương thức Spring Data. Đừng nhầm nó với tên field BSON; Spring Data vẫn mapping tới `ship_to.city`.

### 6.1. Truy vấn trong mảng value object

Muốn tìm đơn chứa **một dòng hàng** có SKU `BOTTLE-500` và số lượng ít nhất 2:

~~~java
Query query = Query.query(
        Criteria.where("items").elemMatch(
                Criteria.where("sku").is("BOTTLE-500")
                        .and("quantity").gte(2)));

List<PurchaseOrder> matching =
        mongoTemplate.find(query, PurchaseOrder.class);
~~~

`$elemMatch` giúp bảo đảm **hai điều kiện áp dụng trên cùng một phần tử mảng**. Nếu viết hai điều kiện dạng `items.sku` và `items.quantity` độc lập, chúng có thể được thỏa bởi hai dòng hàng khác nhau trong cùng đơn.

Trong ứng dụng thực, cần chỉ định giới hạn kết quả, pagination và index theo truy vấn. Index trên đường dẫn nested hoặc mảng là **index của collection chứa document gốc**, không phải index riêng trên class value object.

~~~javascript
db.orders.createIndex({ "ship_to.postal_code": 1, placedAt: -1 });
db.orders.createIndex({ "items.sku": 1 });
~~~

Index đầu có thể phục vụ lọc mã bưu chính rồi sắp xếp theo thời gian; index thứ hai là ứng viên **multikey index** cho mảng `items`. Đây là ví dụ, không phải chỉ dẫn tạo mọi index không qua phân tích workload. Dùng `explain("executionStats")` để xác nhận query plan và cân nhắc chi phí ghi/index.

## 7. Cập nhật một phần document nhúng

Một value object là một khối ý nghĩa trong mô hình miền, nhưng ở tầng BSON có thể cập nhật **cả document con** hoặc **một field của document con**:

| Cách cập nhật | Hành vi | Khi nào phù hợp |
|---|---|---|
`$set: { "ship_to.city": "Đà Nẵng" }` | Chỉ thay field `city` bên trong `ship_to` | Sửa một thuộc tính cụ thể mà nghiệp vụ cho phép |
`$set: { "ship_to": { ... } }` | Thay **toàn bộ** object `ship_to` | Thay value object theo đúng ý nghĩa bất biến |
`save(PurchaseOrder)` | Ghi lại aggregate theo cơ chế save của Spring Data | Khi đã xử lý nghiệp vụ trên tổng thể aggregate; cần kiểm soát concurrent writes |

Ví dụ cập nhật thành phố:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public boolean changeDestinationCity(
        MongoTemplate template, String orderId, String city) {
    Query byId = Query.query(Criteria.where("id").is(orderId));
    Update update = new Update().set("shippingAddress.city", city);
    UpdateResult result =
            template.updateFirst(byId, update, PurchaseOrder.class);
    return result.getModifiedCount() == 1;
}
~~~

Vì đã truyền `PurchaseOrder.class`, Spring Data mapping tên property nested thành field BSON đúng. Lệnh cập nhật trên **một document** được MongoDB thực thi nguyên tử ở cấp document. Tuy nhiên `getModifiedCount() == 0` có thể do không tìm thấy ID *hoặc* giá trị đã giống giá trị hiện tại; nếu nghiệp vụ cần phân biệt, kiểm tra thêm `getMatchedCount()`.

Thay **toàn bộ value object**:

~~~java
ShippingAddress replacement = new ShippingAddress(
        "35 Đường Mới", "Đà Nẵng", "550000");

Update update = new Update().set("shippingAddress", replacement);
mongoTemplate.updateFirst(
        Query.query(Criteria.where("id").is("order-9001")),
        update,
        PurchaseOrder.class);
~~~

Thay cả object con giúp duy trì invariant giữa `street`, `city` và `postalCode` nếu chúng phải được xác nhận cùng nhau. Đổi lại, một bản sao object được đọc từ trước có thể **ghi đè cập nhật mới** của người khác nếu cứ thay toàn bộ mà không có điều kiện cạnh tranh.

### 7.1. Concurrency và @Version trên aggregate root

Value object không cần version riêng nếu nó chỉ được thay thế thông qua aggregate cha. Với cạnh tranh cập nhật trên document gốc, có thể thêm `@Version` vào entity gốc để sử dụng optimistic locking trên các đường ghi do Spring Data hỗ trợ:

~~~java
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public record VersionedOrder(
        @MongoId(FieldType.STRING) String id,
        @Version Long version,
        ShippingAddress shippingAddress) {
}
~~~

Đoạn này là mô hình **minh họa riêng**, không thay thế định nghĩa `PurchaseOrder`. Khi dùng `save` với entity có `@Version`, Spring Data có thể phát hiện bản ghi đã bị thay đổi đồng thời và ném lỗi optimistic locking. Hãy đọc và xử lý phiên bản trả về của thao tác save, nhất là với record bất biến; tránh dùng một object cũ để ghi đè trạng thái mới.

Các lệnh `updateFirst` tự xây dựng cần được xem xét riêng về điều kiện version và cách framework quản lý version; không mặc định một câu lệnh update thủ công tự có đầy đủ kiểm soát tranh chấp giống `save`. Nếu cần compare-and-set, đặt điều kiện version kỳ vọng trong query và cập nhật version một cách rõ ràng.

### 7.2. Mảng value object và array filters

Đối với `items`, việc cập nhật `items.0.quantity` gắn logic vào vị trí phần tử, dễ sai khi mảng được sắp xếp lại. Nếu nghiệp vụ cần sửa một dòng cụ thể, hãy chọn khóa nhận diện dòng có ý nghĩa (SKU nếu duy nhất trong đơn, hoặc một khóa dòng được ứng dụng quản lý) rồi dùng cơ chế positional operator/array filters thích hợp.

Không nên giả định `items.sku` là duy nhất: cùng SKU có thể xuất hiện nhiều lần trong đơn vì khuyến mại, lô hàng hoặc chính sách giá. Nếu cần thao tác độc lập, việc bổ sung `lineId` ổn định trong mảng hoặc tách thành entity riêng có thể phù hợp hơn.

## 8. Null, field thiếu và thay đổi schema của value object

MongoDB cho phép các document trong cùng collection có cấu trúc khác nhau. Điều này ảnh hưởng trực tiếp tới việc khôi phục value object bất biến:

~~~json
{
  "_id": "order-old",
  "customerId": "customer-101",
  "ship_to": {
    "street": "12 Đường Ví Dụ",
    "city": "Hà Nội"
  }
}
~~~

Document cũ thiếu `ship_to.postal_code`, `items` và `subtotal`. Constructor record có thể nhận `null` cho một số thành phần tham chiếu, còn constructor đã thêm `Objects.requireNonNull` hoặc `List.copyOf` có thể ném lỗi khi khôi phục.

Phân biệt:

- **Field thiếu**: BSON không có khóa.
- **Field tồn tại với null**: có khóa nhưng không chứa giá trị.
- **Document con rỗng**: `ship_to: {}`, khác với `ship_to: null`.
- **Mảng rỗng**: `items: []`, khác với không có `items`.
- **Kiểu không tương thích**: trước đây `subtotal` là số, nay là document `Money` gồm `amount` và `currency`.

Chính sách nên thiết kế:

1. Xác định invariant của value object mới và cách đọc dữ liệu lịch sử.
2. Khi thay đổi representation, có thể triển khai **đọc tương thích** trong thời gian chuyển đổi hoặc migration/backfill trước khi ép buộc schema mới.
3. Viết test với tài liệu BSON cũ và mới; kiểm tra cả chiều đọc và chiều ghi.
4. Nếu backfill có khối lượng lớn, chạy theo lô có checkpoint và theo dõi tải; tránh sửa dữ liệu lịch sử không cần thiết.

Không xem constructor validation mới như công cụ migration. Nó có thể làm ứng dụng không đọc được toàn bộ đơn hàng cũ.

## 9. Kiểu đa hình, _class và converter

Với value object có kiểu **khai báo cụ thể** như `ShippingAddress` hoặc `Money`, Spring Data thường có đủ metadata để khôi phục đối tượng. Khi property khai báo là **interface** hoặc base class nhưng runtime chứa nhiều subtype, framework có thể cần **type hint** để nhận biết subtype khi đọc.

Spring Data MongoDB có cơ chế lưu metadata kiểu như `_class` trong một số trường hợp, và hỗ trợ cách cấu hình/alias type metadata. Không nên xóa hoặc thay đổi metadata kiểu chỉ vì muốn BSON “gọn” hơn mà chưa hiểu ảnh hưởng lên:

- Các value object đa hình đang tồn tại.
- Trường hợp đọc lại bằng interface/abstract type.
- Schema evolution khi đổi tên package hoặc class Java.
- Dữ liệu được ghi từ các ứng dụng dùng model khác nhau.

Nếu cần tương thích với hệ thống ngoài không dùng Java class name, cân nhắc **discriminator nghiệp vụ** như `kind` và converter đọc/ghi do ứng dụng kiểm soát, hoặc cấu hình type alias phù hợp. Thay đổi cơ chế lưu `_class` trên dữ liệu cũ cần test và kế hoạch migration.

**Custom converters** như `@WritingConverter`, `@ReadingConverter` và `MongoCustomConversions` hữu ích khi value object có representation đặc thù. Ví dụ mã tiền tệ hoặc một loại đơn vị đo có thể được mã hóa thành scalar. Nhưng khi converter đổi `Money` từ document sang String, các truy vấn `subtotal.amount` và index tương ứng sẽ không còn hợp lệ nếu không được điều chỉnh. Luôn coi đây là quyết định schema.

## 10. Kiểm thử mapping với raw BSON

Unit test của record chỉ chứng minh constructor và `equals` Java hoạt động. Để xác minh Spring Data đã ghi **nested fields và BSON types** đúng, nên có integration test với MongoDB thực. Spring Boot 3.x cung cấp `@DataMongoTest` để tập trung vào MongoDB mapping/repository, nhưng annotation này **không tự khởi chạy MongoDB server**. Có thể cấp database qua Testcontainers và cấu hình URI phù hợp với phiên bản test.

Ví dụ test trong package `com.example.orders`:

~~~java
package com.example.orders;

import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.bson.types.Decimal128;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class EmbeddedValueObjectMappingTest {
    @Autowired
    MongoTemplate mongo;

    @Test
    void persistsNestedValuesAndRestoresThem() {
        PurchaseOrder order = new PurchaseOrder(
                "order-9001",
                "customer-101",
                new ShippingAddress("12 Đường Ví Dụ", "Hà Nội", "100000"),
                List.of(new OrderLine(
                        "BOTTLE-500", "Bình nước 500 ml", 2,
                        new Money(new BigDecimal("129000.00"), "VND"))),
                new Money(new BigDecimal("258000.00"), "VND"),
                Instant.parse("2026-11-20T08:00:00Z"));

        mongo.save(order);

        Document raw = mongo.getCollection("orders")
                .find(eq("_id", "order-9001"))
                .first();
        assertThat(raw).isNotNull();

        Document address = raw.get("ship_to", Document.class);
        assertThat(address.getString("postal_code")).isEqualTo("100000");
        assertThat(raw.containsKey("shippingAddress")).isFalse();

        Document subtotal = raw.get("subtotal", Document.class);
        assertThat(subtotal.get("amount")).isInstanceOf(Decimal128.class);

        PurchaseOrder restored =
                mongo.findById("order-9001", PurchaseOrder.class);
        assertThat(restored).isNotNull();
        assertThat(restored.shippingAddress())
                .isEqualTo(order.shippingAddress());
        assertThat(restored.items()).hasSize(1);
        assertThat(restored.items().get(0).unitPrice().currency())
                .isEqualTo("VND");
    }
}
~~~

Test nên tách database/collection để không phụ thuộc dữ liệu từ lần chạy trước. Với ví dụ thực tế, bổ sung:

| Test | Điều cần chứng minh |
|---|---|
Đọc lại value object hai tầng | `ShippingAddress` và `Money` được materialize đúng |
Đổi tên nested field | `shippingAddress.postalCode` thực sự lưu tại `ship_to.postal_code` |
Decimal128 | `subtotal.amount` có BSON type đúng, không âm thầm lưu Double/String |
Query nested property | `MongoTemplate` và repository trả đúng document |
Array query | `$elemMatch` không ghép nhầm điều kiện từ hai phần tử khác nhau |
Thay nguyên object con | Không để sót field cũ khi schema mới không còn dùng |
Partial update | Chỉ field mong muốn đổi; các field anh em giữ nguyên |
Tương thích schema | Đọc được dữ liệu thiếu/null theo chính sách đã thiết kế |
Tranh chấp | Hai yêu cầu cập nhật không vô tình ghi đè; version được kiểm tra đúng |

Nếu truy vấn chậm, dùng `explain("executionStats")` để kiểm tra số document quét, multikey index, sort và lượng dữ liệu trả về. Việc nhúng giúp đọc gọn hơn nhưng không bảo đảm mọi truy vấn nested đều nhanh.

## 11. Lỗi phổ biến khi ánh xạ value object

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
Gắn `@Document` và `@Id` cho mọi class con | Làm mờ ranh giới entity/value object | Chỉ dùng khi có nhu cầu identity/vòng đời độc lập |
Giả định `@Field` trên nested object không tác động tới query | Query dùng sai field BSON | Dùng typed query và kiểm tra raw BSON |
Sửa tên field mà không migrate dữ liệu | Document cũ đọc thiếu/null | Lập kế hoạch compatibility và backfill |
Cho rằng record luôn bất biến sâu | Mutable list hoặc object bên trong vẫn thay đổi được | Thiết kế value object bất biến và copy phòng vệ phù hợp |
Lưu tiền bằng `double` rồi so sánh chính xác | Sai lệch thập phân và query khó dự đoán | Dùng BigDecimal/Decimal128 theo hợp đồng |
Cập nhật cả `ship_to` từ bản đọc cũ | Ghi đè thay đổi gần đây | Kiểm soát concurrency, dùng version/compare-and-set |
Đọc field nested qua driver với tên property Java | Query raw không tìm đúng dữ liệu | Dùng tên field vật lý `ship_to.postal_code` |
Nhúng danh sách tăng vô hạn | Document quá lớn, vượt giới hạn BSON | Giới hạn mảng hoặc tách collection |
Xóa `_class` bất ngờ với dữ liệu đa hình | Không xác định được subtype khi đọc | Thiết kế type hint/discriminator và test migration |
Không test dữ liệu BSON thật | Lỗi chỉ xuất hiện khi truy vấn hoặc triển khai | Viết integration test cho cả đọc, ghi và cập nhật |

## 12. Bài tập vận dụng

**Bài 1 — Value object và field mapping.** Tạo aggregate `Reservation` có `GuestName`, `DateRange` và `RoomPrice` dưới dạng record. Lưu nested document, đổi tên một field BSON bằng `@Field`, đọc lại raw document và giải thích vì sao các value object không cần `@Id`.

**Bài 2 — Truy vấn nested data.** Mở rộng `PurchaseOrder` có địa chỉ gồm thành phố, quận và mã bưu chính. Viết query repository, `MongoTemplate` và MongoDB shell để tìm theo mã bưu chính; giải thích tên property Java và tên field BSON tương ứng.

**Bài 3 — Mảng value object.** Tạo hai dòng hàng cùng mã SKU nhưng giá bán khác nhau. Viết `$elemMatch` để tìm dòng có cùng SKU và số lượng từ 2 trở lên. Chứng minh vì sao hai điều kiện trên mảng tách rời có thể cho kết quả sai.

**Bài 4 — Cập nhật và concurrency.** Mô phỏng hai yêu cầu đồng thời chỉnh địa chỉ giao hàng. So sánh dùng `save` cả aggregate, `$set` một field và cập nhật có điều kiện theo version; chỉ ra khi nào một lần cập nhật bị ghi đè.

**Bài 5 — Dữ liệu cũ.** Collection đang có `shippingAddress` với field `zip` dạng số, phiên bản mới muốn đổi thành `postal_code` dạng String. Đề xuất đọc tương thích, migration/backfill và test để tránh mất số 0 đầu ở mã bưu chính.

## 13. Ghi nhớ

Trong **Spring Data MongoDB**, value object thường phù hợp để biểu diễn thành **embedded document** khi nó có ý nghĩa theo giá trị, được đọc cùng aggregate cha và không cần vòng đời/ID riêng. Java record hoặc class bất biến giúp diễn đạt mô hình miền; `@Field` và `MappingMongoConverter` nối property Java với tên/kiểu BSON, kể cả qua nhiều tầng object và mảng.

Thiết kế nhúng phải đi cùng **giới hạn kích thước document, chính sách snapshot, truy vấn/index nested, cập nhật nguyên tử ở cấp document, kiểm soát tranh chấp và tương thích schema**. Dùng `MongoRepository` cho truy vấn gắn với entity, `MongoTemplate` cho truy vấn/cập nhật nested linh hoạt, và luôn kiểm tra raw BSON trong integration test khi cần bảo đảm hình dạng dữ liệu thực tế.
