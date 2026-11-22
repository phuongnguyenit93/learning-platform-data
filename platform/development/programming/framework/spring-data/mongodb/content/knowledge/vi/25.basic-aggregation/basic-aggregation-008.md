# Ánh xạ tên thuộc tính, `@Field`, alias và `strictMapping`

> **Chương:** Aggregation cơ bản  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Phân biệt tên property Java, tên field BSON và alias trong aggregation; biết `TypedAggregation` sử dụng `@Field` thế nào; hiểu phạm vi field được xuất ra sau `$project`/`$group`; sử dụng `AggregationOptions.strictMapping()` đúng lúc và kiểm thử pipeline thật để tránh kết quả rỗng hoặc sai ngầm.

## 1. Ba loại tên dễ bị nhầm trong aggregation

Một ứng dụng Java có thể gọi số tiền đơn hàng là `totalVnd`, trong khi MongoDB lưu tên trường `amount_vnd`. Báo cáo lại muốn xuất tên `revenue`.

Đó là **ba tên khác nhau**:

| Lớp | Ví dụ | Ai định nghĩa? |
| --- | --- | --- |
| **Property miền Java** | `totalVnd` | Thuộc tính trong `OrderDocument` |
| **Tên field BSON** | `amount_vnd` | `@Field("amount_vnd")` và document MongoDB |
| **Alias của pipeline** | `revenue` | `$project`, `$group`, `.as("revenue")` |

Khi có metadata của input entity, Spring Data MongoDB có thể biên dịch tên **property Java** thành tên **BSON** trong các stage được framework hỗ trợ. Sau khi tạo alias bằng `$project` hoặc `$group`, những stage tiếp theo phải dùng **tên kết quả được stage trước xuất ra**.

~~~mermaid
flowchart LR
    A["Java: totalVnd"] -->|"@Field"| B["MongoDB: amount_vnd"]
    B -->|"$project / $group"| C["Output: revenue"]
    C --> D["DTO: revenue"]
    D --> E["API JSON: revenue"]
~~~

**Không đồng nhất:**

- `@Field` là metadata ánh xạ **entity với BSON**.
- `.as("revenue")` là **alias được tạo trong pipeline**.
- Tên property của **DTO đầu ra** là bước ánh xạ kết quả, không thay ngược tên field trong collection.
- `strictMapping` là quy tắc xác thực **tham chiếu field trong quá trình dựng pipeline có mapping**, không phải bộ kiểm tra schema toàn MongoDB.

### 1.1. Vì sao lỗi tên field có thể khó phát hiện?

Một `$match` dùng nhầm:

~~~javascript
{ totalVnd: { $gte: 500000 } }
~~~

trên collection thực chỉ có `amount_vnd` thường trả **0 document**, không nhất thiết báo lỗi. Một `$group` tham chiếu field không tồn tại có thể tính toán dựa trên null/missing và sinh ra báo cáo khó phát hiện sai.

Tệ hơn, pipeline có thể thực thi không lỗi nhưng kết quả không phản ánh nghiệp vụ. Bài này tập trung vào cách phòng tránh bằng **typed input**, **alias đúng stage**, **strict mapping** và **integration test**.

## 2. Chuẩn bị fixture riêng cho bài học

### 2.1. Dữ liệu trong `mongosh`

Chỉ chạy các lệnh sau trên **database học tập biệt lập**, không dùng dữ liệu production:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_aggregation_demo_008;

orders.insertMany([
  {
    _id: "o801",
    tenant_id: "t01",
    state_code: "PAID",
    amount_vnd: 300000,
    placed_at: ISODate("2026-10-01T08:00:00Z"),
    buyer_doc: { display_name: "An", city_name: "Hà Nội" },
    order_lines: [
      { sku: "A", qty: 2 },
      { sku: "B", qty: 4 }
    ]
  },
  {
    _id: "o802",
    tenant_id: "t01",
    state_code: "PAID",
    amount_vnd: 800000,
    placed_at: ISODate("2026-10-02T08:00:00Z"),
    buyer_doc: { display_name: "Bình", city_name: "Hà Nội" },
    order_lines: [{ sku: "A", qty: 5 }]
  },
  {
    _id: "o803",
    tenant_id: "t01",
    state_code: "NEW",
    amount_vnd: 150000,
    placed_at: ISODate("2026-10-03T08:00:00Z"),
    buyer_doc: { display_name: "Chi", city_name: "Đà Nẵng" },
    order_lines: [{ sku: "A", qty: 1 }]
  },
  {
    _id: "o804",
    tenant_id: "t02",
    state_code: "PAID",
    amount_vnd: 999000,
    placed_at: ISODate("2026-10-04T08:00:00Z"),
    buyer_doc: { display_name: "Dũng", city_name: "Hà Nội" },
    order_lines: [{ sku: "A", qty: 6 }]
  },
  {
    _id: "o805",
    tenant_id: "t01",
    state_code: "PAID",
    amount_vnd: 400000,
    placed_at: ISODate("2026-10-05T08:00:00Z"),
    buyer_doc: { display_name: "An", city_name: "Huế" },
    order_lines: [{ sku: "C", qty: 3 }]
  },
  {
    _id: "o806",
    tenant_id: "t01",
    state_code: "PAID",
    amount_vnd: 600000,
    placed_at: ISODate("2026-10-05T08:00:00Z"),
    buyer_doc: { display_name: "Hoa", city_name: "Hà Nội" },
    order_lines: [{ sku: "A", qty: 5 }]
  }
]);

orders.createIndex({
  tenant_id: 1,
  state_code: 1,
  placed_at: -1,
  _id: -1
});
~~~

Các ID cố định chỉ phục vụ bài thực hành. Nếu chạy `insertMany` lần hai, MongoDB báo trùng `_id`. Hãy dùng database/collection test mới hoặc reset riêng fixture do bạn sở hữu, **không xóa collection dùng chung**.

### 2.2. Bảng đối chiếu dữ liệu

| ID | Tenant | State | Amount (VND) | Buyer | City |
| --- | --- | --- | ---: | --- | --- |
| `o801` | t01 | PAID | 300.000 | An | Hà Nội |
| `o802` | t01 | PAID | 800.000 | Bình | Hà Nội |
| `o803` | t01 | NEW | 150.000 | Chi | Đà Nẵng |
| `o804` | t02 | PAID | 999.000 | Dũng | Hà Nội |
| `o805` | t01 | PAID | 400.000 | An | Huế |
| `o806` | t01 | PAID | 600.000 | Hoa | Hà Nội |

Trong tenant t01, có **4 order PAID** với tổng tiền **2.100.000 VND**: `300000 + 800000 + 400000 + 600000`. Số liệu này được dùng làm oracle khi kiểm thử aggregation. `o804` tuy PAID nhưng **không được tính** vì thuộc tenant khác.

### 2.3. Kiểm tra ngôn ngữ BSON gốc

Truy vấn trực tiếp MongoDB phải dùng tên field thực:

~~~javascript
orders.find(
  { tenant_id: "t01", state_code: "PAID" },
  { _id: 1, amount_vnd: 1, "buyer_doc.city_name": 1 }
);
~~~

Một truy vấn `{ tenantId: "t01" }` ở `mongosh` **không** được MongoDB tự chuyển thành `tenant_id`. Khả năng đó thuộc lớp mapping của Spring Data khi có metadata entity và một operation hỗ trợ ánh xạ.

## 3. Mô hình miền với `@Field` và nested properties

### 3.1. Enum trạng thái

~~~java
// OrderState.java
package com.example.aggregation;

public enum OrderState {
    NEW, PAID, CANCELLED
}
~~~

Theo mapping mặc định, enum thường được lưu như chuỗi tên hằng. Nếu dự án có custom converter, BSON có thể khác; đừng suy diễn từ Java type mà không kiểm tra dữ liệu thực.

### 3.2. Buyer nhúng trong document

~~~java
// BuyerInfo.java
package com.example.aggregation;

import org.springframework.data.mongodb.core.mapping.Field;

public class BuyerInfo {
    @Field("display_name")
    private String displayName;

    @Field("city_name")
    private String city;

    protected BuyerInfo() { }

    public String getDisplayName() { return displayName; }
    public String getCity() { return city; }
}
~~~

### 3.3. Dòng hàng nhúng

~~~java
// OrderLine.java
package com.example.aggregation;

import org.springframework.data.mongodb.core.mapping.Field;

public class OrderLine {
    private String sku;

    @Field("qty")
    private int quantity;

    protected OrderLine() { }

    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
}
~~~

### 3.4. Aggregate root

~~~java
// OrderDocument.java
package com.example.aggregation;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_aggregation_demo_008")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("state_code")
    private OrderState state;

    @Field("amount_vnd")
    private long totalVnd;

    @Field("placed_at")
    private Instant placedAt;

    @Field("buyer_doc")
    private BuyerInfo buyer;

    @Field("order_lines")
    private List<OrderLine> lines;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public OrderState getState() { return state; }
    public long getTotalVnd() { return totalVnd; }
    public Instant getPlacedAt() { return placedAt; }
    public BuyerInfo getBuyer() { return buyer; }
    public List<OrderLine> getLines() { return lines; }
}
~~~

Trong model này:

| Đường dẫn Java | Đường dẫn BSON |
| --- | --- |
| `id` | `_id` |
| `tenantId` | `tenant_id` |
| `state` | `state_code` |
| `totalVnd` | `amount_vnd` |
| `placedAt` | `placed_at` |
| `buyer` | `buyer_doc` |
| `buyer.displayName` | `buyer_doc.display_name` |
| `buyer.city` | `buyer_doc.city_name` |
| `lines` | `order_lines` |
| `lines.quantity` | `order_lines.qty` |

`@MongoId(FieldType.STRING)` giữ `_id` ở dạng BSON string. Các object nhúng `BuyerInfo` và `OrderLine` **không phải document riêng**; metadata của chúng được dùng để ánh xạ đường dẫn lồng nhau.

## 4. `Aggregation`, `TypedAggregation` và ngữ cảnh mapping

Spring Data MongoDB có hai cách tạo pipeline nổi bật:

~~~java
import static org.springframework.data.mongodb.core.aggregation.Aggregation.*;

// Pipeline không mang input type tại lúc tạo:
Aggregation untyped = newAggregation(
    match(Criteria.where("tenant_id").is("t01"))
);

// Pipeline có input type:
TypedAggregation<OrderDocument> typed = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01"))
);
~~~

`TypedAggregation<OrderDocument>` giữ thông tin **kiểu document đầu vào**. Khi Spring Data chuyển các operation chuẩn sang BSON, thông tin này được sử dụng để ánh xạ những property như `tenantId`, `totalVnd` và đường dẫn nested, có xét `@Field`.

### 4.1. Thực thi bằng `MongoTemplate`

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;
import org.springframework.data.mongodb.core.query.Criteria;

// template là MongoTemplate đã được inject:
TypedAggregation<OrderDocument> pipeline = Aggregation.newAggregation(
    OrderDocument.class,
    Aggregation.match(Criteria.where("tenantId").is("t01"))
);

AggregationResults<Document> results = template.aggregate(
    pipeline, Document.class
);

var rows = results.getMappedResults();
~~~

Với typed aggregation, Spring Data suy ra tên collection từ `@Document(collection = "orders_aggregation_demo_008")`. Có các overload `aggregate(aggregation, collectionName, outputType)` và `aggregate(aggregation, inputType, outputType)`; đừng trộn input collection với output DTO type.

### 4.2. Hai hướng dùng aggregation không typed

~~~java
Aggregation rawNames = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("tenant_id").is("t01")
    )
);

var result = template.aggregate(
    rawNames,
    "orders_aggregation_demo_008",
    Document.class
);
~~~

Ở dạng **không có input type** và chỉ đưa tên collection, đừng mặc định Spring Data biết `OrderDocument` để ánh xạ `tenantId`. Nếu muốn viết property Java, hãy cung cấp context typed/input entity tương ứng thay vì trông đợi framework tự suy từ tên collection.

### 4.3. Bản đồ trách nhiệm

~~~text
TypedAggregation<OrderDocument>
    |
    +-- input type / MappingMongoConverter
    |       +-- @Field, @MongoId, enum/custom converter khi phù hợp
    |
    +-- AggregationOperationContext
    |       +-- ánh xạ field reference của operation chuẩn
    |       +-- theo dõi các field/alias được stage xuất ra
    |
    +-- MongoDB aggregation pipeline
    |       +-- $match, $project, $group, $sort, $unwind...
    |
    +-- output mapping
            +-- Document hoặc DTO/record kết quả
~~~

Một **typed pipeline** giúp ánh xạ và kiểm tra đường dẫn theo domain, nhưng không tự giải quyết tất cả sai khác BSON, dynamic fields, raw stages, schema legacy hoặc quyền truy cập.

## 5. `$match`: viết tên Java, để Spring Data ánh xạ sang BSON

### 5.1. Filter theo tenant và enum

~~~java
TypedAggregation<OrderDocument> pipeline = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID))
);

var result = template.aggregate(pipeline, Document.class);
~~~

Pipeline BSON về ý nghĩa:

~~~javascript
[
  {
    $match: {
      tenant_id: "t01",
      state_code: "PAID"
    }
  }
]
~~~

Với fixture, kết quả gồm `o801`, `o802`, `o805` và `o806`. `o804` PAID nhưng thuộc tenant t02 nên bị loại.

**Quy tắc:** Trong DSL có input entity type, thường viết theo **property Java** (`tenantId`, `state`). Ở `mongosh` hoặc raw driver, viết theo **BSON** (`tenant_id`, `state_code`).

### 5.2. Range field ánh xạ `@Field`

~~~java
match(Criteria.where("tenantId").is("t01")
    .and("totalVnd").gte(500_000L))
~~~

Tương đương điều kiện BSON:

~~~javascript
{
  tenant_id: "t01",
  amount_vnd: { $gte: 500000 }
}
~~~

Trên fixture, những order t01 có tổng tiền từ 500.000 là `o802` và `o806`. Nếu thêm `state = PAID`, vẫn là hai order này.

### 5.3. Vì sao không nên dùng tên BSON trong một typed pipeline?

Code:

~~~java
// KHÔNG nên dùng tên BSON thay property khi viết TypedAggregation:
match(Criteria.where("amount_vnd").gte(500_000L))
~~~

có thể có hành vi khác nhau theo mapping mode và phiên bản: framework không tìm thấy property Java `amount_vnd`, nên `strictMapping` có thể báo lỗi; chế độ relaxed có thể giữ nguyên đường dẫn không biết. Điều này khiến pipeline khó kiểm soát và dễ hỏng khi rename Java property hoặc thay đổi cách mapping.

Chọn **một quy ước rõ ràng**: DSL entity-aware dùng tên Java; raw BSON dùng tên MongoDB, và kiểm thử ranh giới giữa hai cách.

## 6. `$project` và alias do pipeline tạo ra

Đây là chỗ rất dễ nhầm lẫn giữa `@Field` và `.as(...)`.

### 6.1. Projection chỉ giữ trường có sẵn

~~~java
TypedAggregation<OrderDocument> projection = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")),
    project("state", "totalVnd")
);
~~~

Về ý nghĩa, MongoDB sẽ nhận một `$project` trên những **tên field BSON được ánh xạ**, ví dụ `state_code` và `amount_vnd`. Vì chỉ include các trường, `_id` của MongoDB **thường vẫn xuất hiện mặc định** nếu không loại tường minh.

### 6.2. Alias để tạo hình dạng kết quả mới

Giả sử API muốn các field `orderId`, `buyerName` và `amount`:

~~~java
TypedAggregation<OrderDocument> cards = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)),
    project()
        .and("_id").as("orderId")
        .and("buyer.displayName").as("buyerName")
        .and("totalVnd").as("amount")
        .andExclude("_id"),
    sort(Sort.Direction.DESC, "amount")
);
~~~

Định nghĩa pipeline này dùng **property Java ở vế nguồn**:

- `buyer.displayName` được ánh xạ từ `buyer_doc.display_name`.
- `totalVnd` được ánh xạ từ `amount_vnd`.
- `orderId`, `buyerName` và `amount` là **tên field kết quả**, không phải tên field mới trong collection.

MongoDB pipeline về ý nghĩa tương đương:

~~~javascript
[
  { $match: { tenant_id: "t01", state_code: "PAID" } },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      buyerName: "$buyer_doc.display_name",
      amount: "$amount_vnd"
    }
  },
  { $sort: { amount: -1 } }
]
~~~

Kết quả trên fixture theo tổng tiền giảm dần:

~~~javascript
[
  { orderId: "o802", buyerName: "Bình", amount: 800000 },
  { orderId: "o806", buyerName: "Hoa", amount: 600000 },
  { orderId: "o805", buyerName: "An", amount: 400000 },
  { orderId: "o801", buyerName: "An", amount: 300000 }
]
~~~

Ở stage `$sort` sau `$project`, ta dùng alias `amount`, **không dùng lại `totalVnd` hoặc `amount_vnd`** vì các tên nguồn ấy không còn được stage trước xuất ra.

### 6.3. Sai phổ biến: sort theo property đã bị loại

~~~java
newAggregation(
    OrderDocument.class,
    project().and("totalVnd").as("amount"),
    sort(Sort.Direction.DESC, "totalVnd")
);
// Sai về ngữ nghĩa: stage trước chỉ xuất amount, không còn totalVnd.
~~~

Theo quy tắc field exposure của Spring Data aggregation, stage tiếp theo chỉ được tham chiếu **field đã giữ lại hoặc alias mới được xuất ra**. Dùng alias `amount` mới đúng:

~~~java
newAggregation(
    OrderDocument.class,
    project().and("totalVnd").as("amount"),
    sort(Sort.Direction.DESC, "amount")
);
~~~

Một số tổ hợp operation/phiên bản phát hiện tham chiếu không còn hợp lệ khi dựng pipeline; những trường hợp khác có thể phát sinh pipeline không cho kết quả mong muốn. Đừng dựa hoàn toàn vào ngoại lệ — **kiểm tra pipeline BSON và output thực**.

### 6.4. `@Field` không phải `.as(...)`

~~~java
@Field("amount_vnd")
private long totalVnd;
~~~

khác hoàn toàn với:

~~~java
project().and("totalVnd").as("amount");
~~~

Thứ nhất ánh xạ **field lưu trong collection**; thứ hai tạo **field trong output pipeline**. Kể cả tên alias trùng một property Java khác, Spring Data không sửa dữ liệu collection hay tự rename thuộc tính entity.

### 6.5. `_id` và alias `orderId`

MongoDB `$project` giữ `_id` mặc định, trừ khi đặt `_id: 0`. Nếu vừa tạo `orderId: "$_id"` vừa không exclude `_id`, output có thể chứa **cả hai**.

~~~javascript
// Muốn chỉ có orderId và không còn _id:
{ $project: { _id: 0, orderId: "$_id" } }
~~~

Trong Spring Data, dùng `andExclude("_id")` khi muốn loại trường gốc. Hãy chọn output schema một cách tường minh để DTO không vô tình chứa cả `id` và `orderId`.

## 7. `$group`: tên field nguồn, `_id` nhóm và alias kết quả

### 7.1. Gom đơn hàng PAID theo trạng thái

~~~java
TypedAggregation<OrderDocument> totals = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)),
    group("state")
        .count().as("orderCount")
        .sum("totalVnd").as("grossVnd")
);

var result = template.aggregate(totals, Document.class)
    .getMappedResults();
~~~

Về ý nghĩa, BSON tương ứng:

~~~javascript
[
  { $match: { tenant_id: "t01", state_code: "PAID" } },
  {
    $group: {
      _id: "$state_code",
      orderCount: { $sum: 1 },
      grossVnd: { $sum: "$amount_vnd" }
    }
  }
]
~~~

Kết quả gồm **một document tổng hợp**:

~~~javascript
{
  _id: "PAID",
  orderCount: 4,
  grossVnd: 2100000
}
~~~

Ở đây `state` và `totalVnd` trong Spring DSL là tên Java; `state_code` và `amount_vnd` là tên BSON; `orderCount` và `grossVnd` là **alias** của các accumulator. `_id` sau `$group` **là khóa nhóm**, không còn là ID đơn hàng gốc.

### 7.2. Sau `$group`, field nguồn không còn khả dụng như trước

Các field hiện có sau `$group` trên ví dụ là `_id`, `orderCount`, `grossVnd`. Stage:

~~~java
sort(Sort.Direction.DESC, "grossVnd")
~~~

hợp lệ vì `grossVnd` được `group` tạo ra. Ngược lại:

~~~java
sort(Sort.Direction.DESC, "totalVnd")
~~~

không đúng ý nghĩa: mỗi document đầu ra đã là một **nhóm**, không còn một `totalVnd` của từng order.

### 7.3. Đổi tên khóa nhóm thành property DTO

Có thể bổ sung `$project` sau `$group`:

~~~java
TypedAggregation<OrderDocument> totals = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")),
    group("state")
        .count().as("orderCount")
        .sum("totalVnd").as("grossVnd"),
    project("orderCount", "grossVnd")
        .and("_id").as("stateName")
        .andExclude("_id"),
    sort(Sort.Direction.DESC, "grossVnd")
);
~~~

Nhờ alias `stateName`, output có thể là:

~~~javascript
{
  stateName: "PAID",
  orderCount: 4,
  grossVnd: 2100000
}
~~~

Pipeline ví dụ này match **tenant t01** nhưng không giới hạn trạng thái, nên thực tế còn một document nhóm NEW. Đoạn JSON trên là **nhóm PAID**, không phải toàn bộ output. Nếu chỉ cần PAID, thêm điều kiện trạng thái ở `$match` đầu.

## 8. Đường dẫn nested và `@Field` trên từng cấp

Với:

~~~java
@Field("buyer_doc")
private BuyerInfo buyer;

// Trong BuyerInfo:
@Field("city_name")
private String city;
~~~

đường dẫn Java `buyer.city` phải ánh xạ tới BSON `buyer_doc.city_name`.

### 8.1. Group số order theo thành phố

~~~java
TypedAggregation<OrderDocument> byCity = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)),
    group("buyer.city")
        .count().as("orders"),
    sort(Sort.Direction.DESC, "orders")
);
~~~

Về ý nghĩa, `$group._id` dùng `"$buyer_doc.city_name"`. Kết quả trên fixture:

~~~javascript
[
  { _id: "Hà Nội", orders: 3 },
  { _id: "Huế", orders: 1 }
]
~~~

Nếu quên `@Field("city_name")` trong `BuyerInfo`, Spring Data có thể dựng đường dẫn dựa theo tên mặc định `city`, dẫn đến query sai khi BSON vẫn mang tên `city_name`.

### 8.2. Mảng embedded document và `$unwind`

Để thống kê số lượng theo SKU:

~~~java
TypedAggregation<OrderDocument> unitsBySku = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")),
    unwind("lines"),
    group("lines.sku")
        .sum("lines.quantity").as("units"),
    sort(Sort.Direction.DESC, "units")
);
~~~

Typed mapping cần hiểu:

~~~text
lines                 -> order_lines
lines.sku             -> order_lines.sku
lines.quantity        -> order_lines.qty
~~~

Sau `$unwind`, mỗi dòng hàng tạo một bản ghi trung gian. `$group` dùng trường `qty` ở BSON để cộng số lượng. `unwind("lines")` không thay đổi bản thân collection; đó là biến đổi các document **trong pipeline**.

Trong fixture của tenant t01, tổng `qty` theo SKU là:

| SKU | Đóng góp | Tổng |
| --- | --- | ---: |
| A | 2 (o801) + 5 (o802) + 1 (o803) + 5 (o806) | 13 |
| B | 4 (o801) | 4 |
| C | 3 (o805) | 3 |

`o804` thuộc tenant t02 nên không được tính. Ví dụ này cho thấy nested `@Field` ở cả **array** và **element** đều quan trọng.

### 8.3. Dùng `$elemMatch` nếu filter cần cùng một phần tử

Nếu muốn lọc order có dòng `sku=A` và `quantity>=5`, cần ràng buộc hai điều kiện trên **cùng một dòng hàng**:

~~~java
match(Criteria.where("lines").elemMatch(
    Criteria.where("sku").is("A")
        .and("quantity").gte(5)
))
~~~

Đừng viết hai predicate dot-notation độc lập rồi tin rằng chúng luôn khớp cùng một phần tử mảng. Bên cạnh mapping tên field, **ngữ nghĩa matching của MongoDB** cũng phải đúng.

## 9. `strictMapping`: kiểm tra property không tồn tại trong typed pipeline

Spring Data MongoDB trước đây kiểm tra chặt tham chiếu tới property của input type. **Từ phiên bản 3.2**, khi tham chiếu một property không tồn tại, chế độ mapping thông thường **không còn mặc định ném lỗi** như trước. Nếu muốn lấy lại hành vi kiểm tra nghiêm ngặt, dùng `AggregationOptions.strictMapping()`.

### 9.1. Thiết lập trong `TypedAggregation`

~~~java
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;
import org.springframework.data.mongodb.core.aggregation.TypedAggregation;

AggregationOptions strictOptions =
    AggregationOptions.builder()
        .strictMapping()
        .build();

TypedAggregation<OrderDocument> strictPipeline =
    Aggregation.newAggregation(
        OrderDocument.class,
        Aggregation.match(
            Criteria.where("tenantId").is("t01")
        ),
        Aggregation.project("state", "totalVnd")
    ).withOptions(strictOptions);

var rows = template.aggregate(
    strictPipeline,
    Document.class
).getMappedResults();
~~~

Code trên dùng các property tồn tại (`tenantId`, `state`, `totalVnd`) nên ánh xạ về field BSON tương ứng.

### 9.2. Phát hiện lỗi gõ sai property

~~~java
TypedAggregation<OrderDocument> typo = Aggregation.newAggregation(
    OrderDocument.class,
    Aggregation.project("totalVNDD") // Gõ sai: chỉ có totalVnd.
).withOptions(
    AggregationOptions.builder()
        .strictMapping()
        .build()
);

// Khi dựng/render/thực thi typed aggregation,
// Spring Data báo lỗi tham chiếu property không tồn tại.
template.aggregate(typo, Document.class);
~~~

Không dựa vào một lớp exception duy nhất cho mọi phiên bản và mọi loại operation; trong bài test có thể xác nhận xảy ra lỗi ở ranh giới **dịch tham chiếu property/pipeline**, trước khi coi kết quả aggregation là hợp lệ.

**Lưu ý:** `strictMapping` không tự phát hiện mọi lỗi viết sai field trong một đoạn **raw JSON stage** không qua mapping context; nó cũng không kiểm chứng dữ liệu BSON thật có đủ trường hoặc đúng kiểu.

### 9.3. So sánh ba chế độ mapping

`AggregationOptions.Builder` có ba lựa chọn quan trọng:

| Mode | Cách hoạt động | Khi nào cân nhắc |
| --- | --- | --- |
| `strictMapping()` | Ánh xạ domain property có xét `@Field`; **báo lỗi** khi tham chiếu property không tồn tại trong phạm vi kiểm tra | Pipeline typed cần bắt lỗi đổi tên/gõ sai property sớm |
| `relaxedMapping()` | Ánh xạ property biết được; nếu không biết, **giữ tên người dùng cung cấp** | Pipeline cố ý tham chiếu field mới/chưa khai báo, output stage đặc biệt |
| `noMapping()` | **Không áp dụng domain type mapping**; dùng tên field trong pipeline như đã viết | Chủ động viết theo BSON/raw schema; đã kiểm tra kỹ mọi đường dẫn |

Ví dụ:

~~~java
AggregationOptions strict = AggregationOptions.builder()
    .strictMapping()
    .build();

AggregationOptions relaxed = AggregationOptions.builder()
    .relaxedMapping()
    .build();

AggregationOptions raw = AggregationOptions.builder()
    .noMapping()
    .build();
~~~

Ba mode đều là **tùy chọn cấp pipeline** thông qua `withOptions(...)`. Không nên nhầm `noMapping()` với việc trả kết quả kiểu `Document.class`: **output type** và **quy tắc ánh xạ input references** là hai khái niệm khác nhau.

### 9.4. Lỗi có thể bị che trong relaxed mapping

Giả sử người viết gõ sai `totalVnd` thành `totalVNDD`:

~~~java
Aggregation.project("totalVNDD");
~~~

Ở chế độ relaxed, Spring Data có thể giữ nguyên tên không biết. MongoDB không có field đó trong document, nên output thường thiếu field cần thiết mà không báo lỗi rõ ràng. Nếu báo cáo chỉ nhìn số hàng, sự cố rất dễ bị bỏ sót.

**Khuyến nghị:** Dùng `strictMapping()` cho pipeline dựa trên **entity schema ổn định**. Nếu cần field động do stage trước tạo hoặc dữ liệu legacy có trường ngoài model, chọn điểm dùng relaxed/raw **có chủ đích**, kiểm pipeline và test output, thay vì tắt mapping để che lỗi.

### 9.5. `strictMapping` không phải schema validation của MongoDB

Nó **không bảo đảm**:

- Collection thật có mọi trường được khai báo trong entity.
- Mọi document có kiểu dữ liệu đúng (`amount_vnd` đôi khi bị lưu thành chuỗi).
- `tenantId` đã được ràng buộc bởi phân quyền.
- Alias sau `$project` được DTO serialize như mong muốn.
- Một `AggregationOperation` raw tự dựng bằng `Document` được kiểm tra đầy đủ.
- Pipeline có kết quả đúng nghiệp vụ dù không còn lỗi tên property.

Do đó kiểm tra mapping cần đi cùng **MongoDB schema validation**, kiểm dữ liệu cũ và integration test kết quả.

## 10. Raw aggregation stage và biên giới mapping

Không phải mọi stage đều đi qua builder typed/mapping giống nhau. Spring Data hỗ trợ tạo raw stage để sử dụng tính năng driver/MongoDB chưa được một DSL cụ thể biểu diễn.

Ví dụ:

~~~java
AggregationOperation rawMatch = context ->
    new Document("$match",
        new Document("tenant_id", "t01"));

TypedAggregation<OrderDocument> pipeline =
    Aggregation.newAggregation(
        OrderDocument.class,
        rawMatch,
        Aggregation.project("state", "totalVnd")
    );
~~~

Trong `rawMatch`, bạn đang trả một `Document` BSON **đã tự dựng**; chuỗi `tenant_id` ở đây là field BSON thật. Không nên viết `tenantId` rồi kỳ vọng mọi implementation raw stage tự gọi converter.

### 10.1. Nếu cần mapping cho raw Document

Một custom operation có thể chủ động dùng context:

~~~java
AggregationOperation mappedMatch = context -> {
    Document stage = new Document("$match",
        new Document("tenantId", "t01"));
    return context.getMappedObject(stage);
};
~~~

Ở đây `getMappedObject(...)` yêu cầu context áp dụng domain mapping khi có đủ thông tin. Tuy nhiên cách viết custom stage/field references cần kiểm thử chặt theo phiên bản Spring Data và cấu trúc stage, đặc biệt với những operator mới, expression nested hoặc alias từ stage trước.

Đừng áp dụng `getMappedObject` mù quáng vào mọi JSON raw chứa tên field **đã ở dạng BSON**, vì bạn có thể tạo ra cách xử lý khác dự định. Khi pipeline phức tạp, lựa chọn rõ ràng hơn là: **dùng Spring DSL cho phần entity-aware** và **raw BSON có kiểm chứng** cho phần thật sự cần API thấp.

### 10.2. `Aggregation.stage(...)` và tên field raw

Những phiên bản Spring Data MongoDB cung cấp `Aggregation.stage(String json)` để chèn một stage JSON/BSON nguyên bản. Loại stage raw này **không được tự ánh xạ tên field bằng `@Field`**:

~~~java
AggregationOperation raw = Aggregation.stage(
    "{ $match: { tenant_id: 't01' } }"
);
~~~

Đây là code minh họa raw stage. Trong dự án, dùng tên BSON thật và không ghép input người dùng vào JSON thô. Nếu stage có nhiều tham số từ request, ưu tiên DSL/binding có kiểu hoặc xây BSON bằng API an toàn.

### 10.3. Không biến `noMapping()` thành “giải pháp sửa mọi lỗi”

Ví dụ:

~~~java
TypedAggregation<OrderDocument> rawNames =
    Aggregation.newAggregation(
        OrderDocument.class,
        Aggregation.match(
            Criteria.where("tenant_id").is("t01")
        )
    ).withOptions(
        AggregationOptions.builder().noMapping().build()
    );
~~~

Ở chế độ noMapping, `tenant_id` được dùng nguyên dạng. Nếu đổi sang `Criteria.where("tenantId")` nhưng vẫn để `noMapping()`, query sẽ tham chiếu **field BSON tên tenantId** (không có trong fixture), dẫn đến kết quả rỗng.

**Không trộn tên Java và tên BSON tùy ý** trong cùng một pipeline đang tắt mapping.

## 11. Field exposure: stage nào xuất ra những field nào?

Aggregation là một **chuỗi biến đổi dữ liệu**. Mỗi stage nhận document từ stage trước, không phải lúc nào cũng nhận entity gốc.

### 11.1. Chuỗi hoạt động theo tên

~~~text
OrderDocument (input)
  tenantId, state, totalVnd, buyer.displayName
             |
             | typed mapping
             v
MongoDB $match
  tenant_id, state_code, amount_vnd, buyer_doc.display_name
             |
             | $project tạo alias
             v
orderId, buyerName, amount
             |
             | $sort sử dụng alias
             v
orderId, buyerName, amount
~~~

Một khi `$project` loại `amount_vnd` và tạo `amount`, stage sau **không được viết như thể đang đọc document gốc**.

### 11.2. `$addFields` giữ field cũ, `$project` có thể loại field

Ví dụ MongoDB:

~~~javascript
[
  { $addFields: { amountWithTax: { $multiply: ["$amount_vnd", 1.1] } } },
  { $sort: { amountWithTax: -1 } }
]
~~~

`$addFields` thêm field mới và thường **giữ** những field cũ. Ngược lại:

~~~javascript
[
  { $project: { amount: "$amount_vnd", _id: 0 } },
  { $sort: { amount: -1 } }
]
~~~

`$project` ở đây chỉ để lại `amount`; mọi tên nguồn không được include sẽ không còn. Khi viết Spring DSL tương ứng, cần tôn trọng cùng ngữ nghĩa.

### 11.3. `$group` thay toàn bộ shape của document

~~~javascript
{
  $group: {
    _id: "$state_code",
    revenue: { $sum: "$amount_vnd" }
  }
}
~~~

Sau stage này, các trường `tenant_id`, `buyer_doc` hoặc `amount_vnd` từng document đã **không còn trong output**, trừ khi được tích lũy vào accumulator. Nếu stage tiếp cần một giá trị, phải thêm vào pipeline đúng chỗ hoặc tạo accumulator/alias thích hợp.

### 11.4. Không giả định `strictMapping` hiểu mọi output động

Một stage raw tùy ý có thể tạo field ngoài model mà Spring Data không dự đoán đầy đủ. Khi dùng `strictMapping`, hãy:

- Giữ các field động trong DSL có thể theo dõi alias nếu phù hợp.
- Đặt raw stage ở ranh giới rõ ràng và dùng tên output đúng.
- Kiểm tra BSON pipeline sau khi render.
- Có integration test cho từng alias quan trọng.

Nhiệm vụ của `strictMapping` là kiểm tra **tham chiếu theo metadata mà framework biết**, không phải chứng minh mọi stage MongoDB trả schema cố định.

## 12. DTO đầu ra: tên record khác với tên lưu trữ

Một aggregation có thể trả `org.bson.Document` để debug, nhưng API thường cần DTO:

~~~java
// OrderCard.java
package com.example.aggregation;

public record OrderCard(
    String orderId,
    String buyerName,
    long amount
) {
}
~~~

Pipeline:

~~~java
TypedAggregation<OrderDocument> pipeline = newAggregation(
    OrderDocument.class,
    match(Criteria.where("tenantId").is("t01")
        .and("state").is(OrderState.PAID)),
    project()
        .and("_id").as("orderId")
        .and("buyer.displayName").as("buyerName")
        .and("totalVnd").as("amount")
        .andExclude("_id"),
    sort(Sort.Direction.DESC, "amount")
);

List<OrderCard> cards = template.aggregate(
    pipeline, OrderCard.class
).getMappedResults();
~~~

`OrderCard` có constructor canonical nhận đúng các field output `orderId`, `buyerName` và `amount`. Với record/DTO class-based projection, tên và kiểu constructor phải tương thích BSON được trả về; có thể cần `@PersistenceCreator` hoặc custom converter khi dùng constructor phức tạp.

### 12.1. Vì sao phải phân biệt input type với output type?

Trong lời gọi:

~~~java
template.aggregate(pipeline, OrderCard.class);
~~~

- `OrderDocument.class` (nằm trong `TypedAggregation`) định nghĩa **metadata input**, dùng để map property Java sang BSON.
- `OrderCard.class` định nghĩa **cách materialize output** đã qua pipeline.

Chuyển output sang `Document.class` **không tắt mapping input** nếu pipeline vẫn là typed. Ngược lại, chỉ truyền `OrderCard.class` làm output **không làm framework suy ra** `@Field` của `OrderDocument` nếu pipeline không có input type.

### 12.2. `@Field` trên DTO không thay thế alias

Có thể dùng metadata mapping của class kết quả trong một số tình huống, nhưng điều đơn giản và dễ kiểm thử nhất là tạo output alias **khớp tên property DTO**.

~~~javascript
{ buyerName: "An", amount: 300000 }
~~~

được ánh xạ rõ ràng vào:

~~~java
record OrderCard(String orderId, String buyerName, long amount) { }
~~~

Không trông chờ một `@Field("amount_vnd")` của input entity tự đổi output alias `amount` thành field khác. Đó là hai lớp mapping độc lập.

### 12.3. Missing/null và primitive trong DTO

Nếu pipeline không xuất `amount` nhưng DTO khai báo `long amount`, quá trình ánh xạ có thể thất bại hoặc tạo default tùy constructor/converter. Với dữ liệu có khả năng thiếu số, cân nhắc `Long`/`BigDecimal` và policy xử lý null cụ thể. Với tiền tệ, đừng áp dụng phép nhân số thực tùy tiện nếu yêu cầu độ chính xác tài chính; cần kiểu và quy tắc làm tròn được thiết kế rõ.

## 13. Đo và kiểm tra pipeline trước khi tin kết quả

### 13.1. Ưu tiên so sánh với pipeline `mongosh`

Khi nghi ngờ mapping, dựng một pipeline BSON **minh bạch**:

~~~javascript
orders.aggregate([
  {
    $match: {
      tenant_id: "t01",
      state_code: "PAID"
    }
  },
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      buyerName: "$buyer_doc.display_name",
      amount: "$amount_vnd"
    }
  },
  { $sort: { amount: -1 } }
]);
~~~

So sánh số record, thứ tự, tên key và giá trị với `TypedAggregation`. Nếu raw BSON đúng nhưng Spring Data trả sai, kiểm tra `@Field`, context của pipeline, alias stage và mapping DTO.

### 13.2. Quan sát command thực tế

Có thể bật log phù hợp hoặc cấu hình `CommandListener` của MongoDB Java Driver trong môi trường test để ghi nhận **lệnh aggregate đã được gửi**. Khi log:

- Không ghi raw request chứa PII, email hoặc token ra hệ thống chung.
- Lọc/ẩn thông tin nhạy cảm.
- Kiểm tra tên BSON trong `$match`, `$project`, `$group`, `$sort`.

`Aggregation.toString()` hoặc việc in object Java không nhất thiết phản ánh **đúng pipeline đã được mapping hoàn chỉnh** trong mọi cấu hình. Hãy dùng command thực tế hoặc kiểm qua driver/database khi cần khẳng định.

### 13.3. Debug theo từng stage

Nếu pipeline 4 stage cho kết quả sai, chạy lần lượt:

1. Chỉ `$match` để kiểm tra filter và tenant.
2. Thêm `$project`, xem field nguồn và alias.
3. Thêm `$group` nếu cần tổng hợp, kiểm tra `_id` và accumulator.
4. Thêm `$sort`/`$limit`, tham chiếu đúng field còn lại.
5. Chạy DTO mapping và kiểm so sánh với `Document.class`.

Đừng bắt đầu bằng chỉnh sửa toàn bộ 4 stage cùng lúc; việc cô lập stage giúp tìm lỗi tên nhanh hơn.

## 14. Mapping, index và hiệu năng

Đổi tên Java property hoặc tạo alias không tự khiến truy vấn nhanh hơn. **Index thuộc về tên field BSON lưu trong collection**, không phải tên DTO:

~~~javascript
orders.createIndex({
  tenant_id: 1,
  state_code: 1,
  placed_at: -1,
  _id: -1
});
~~~

Khi ứng dụng viết:

~~~java
match(Criteria.where("tenantId").is("t01")
    .and("state").is(OrderState.PAID))
~~~

và typed mapping chuyển sang BSON `tenant_id/state_code`, index trên có thể hỗ trợ tìm document, tùy selectivity và query plan.

### 14.1. `$match` sớm để giảm tập dữ liệu

Ở mức nguyên tắc, đặt `$match` có chọn lọc gần đầu pipeline giúp giảm lượng dữ liệu phải xử lý ở stage sau; MongoDB còn có các bước optimizer riêng. Tuy nhiên cần xem `explain("executionStats")` chứ không chỉ đếm số stage.

~~~javascript
orders.explain("executionStats").aggregate([
  { $match: { tenant_id: "t01", state_code: "PAID" } },
  { $group: { _id: "$state_code", revenue: { $sum: "$amount_vnd" } } }
]);
~~~

Đây là công cụ phân tích **execution plan**, không thay thế đo latency và số byte trả về trong ứng dụng. Trên fixture chỉ có 6 document, không thể rút ra kết luận hiệu năng production.

### 14.2. Alias sau `$project` không phải field được index sẵn

Giả sử `$project` tạo:

~~~javascript
{ amount: "$amount_vnd" }
~~~

thì tên `amount` là output **trong pipeline**, không phải field vật lý ở collection. Việc tạo index `{ amount: 1 }` trên collection gốc sẽ không tự hỗ trợ sort theo alias được tính ở giữa pipeline. Hãy xác định stage nào có thể tận dụng index và liệu sort có thể được đặt trước các phép biến đổi mà vẫn giữ đúng kết quả hay không.

### 14.3. `allowDiskUse` và pipeline lớn

Với pipeline có sort/group lớn, `AggregationOptions` hỗ trợ các tùy chọn như `allowDiskUse(true)` theo khả năng MongoDB. Đây là một **biện pháp tài nguyên**, không giải quyết tên field sai:

~~~java
AggregationOptions options = AggregationOptions.builder()
    .strictMapping()
    .allowDiskUse(true)
    .build();

TypedAggregation<OrderDocument> configured =
    pipeline.withOptions(options);
~~~

Không bật disk spill mà không kiểm soát workload, deadline và memory; đo hiệu năng trên tập dữ liệu đủ lớn, đánh giá index và số document đi qua từng stage.

## 15. Phân biệt `strictMapping` với quyền truy cập và độ đúng nghiệp vụ

Một pipeline có property hoàn toàn đúng nhưng vẫn có thể gây rò dữ liệu nếu thiếu tenant filter:

~~~java
TypedAggregation<OrderDocument> unsafe = newAggregation(
    OrderDocument.class,
    match(Criteria.where("state").is(OrderState.PAID)),
    group("state").sum("totalVnd").as("revenue")
).withOptions(AggregationOptions.builder().strictMapping().build());
~~~

`strictMapping` có thể chấp nhận mọi property, nhưng kết quả sẽ cộng **mọi tenant**, gồm `o804` của t02. Đối với ứng dụng multi-tenant, tenant phải được **ràng buộc từ server** và đưa vào `$match`.

### 15.1. Một query an toàn cần nhiều tầng kiểm soát

- **Field correctness:** input type và `@Field`/strict mapping kiểm tên property.
- **Business correctness:** filter, cùng phần tử mảng, group key và alias đúng yêu cầu.
- **Security scope:** tenant/authorization được kiểm trước khi thực thi.
- **Data correctness:** BSON đúng kiểu, xử lý missing/null, converter nhất quán.
- **Operational safety:** limit, timeout, index và metric cho báo cáo lớn.

Không dùng strict mapping làm chứng chỉ rằng toàn bộ pipeline đã an toàn và đúng.

## 16. Integration test xác nhận mapping và alias

Unit test chỉ mock `MongoTemplate.aggregate` có thể kiểm service gọi đúng method, nhưng **không chứng minh**:

- `tenantId` thật sự đổi thành `tenant_id`.
- `buyer.displayName` thật sự đổi thành `buyer_doc.display_name`.
- Alias `amount` còn tồn tại khi stage `sort` chạy.
- `strictMapping` phát hiện property sai.
- DTO record ánh xạ đúng cấu trúc output.

Hãy chạy integration test với MongoDB test riêng/Testcontainers và fixture được cô lập.

### 16.1. Test typed projection và alias

~~~java
package com.example.aggregation;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.domain.Sort;

@DataMongoTest
class AggregationFieldMappingTest {
    @Autowired MongoTemplate template;

    @Test
    void typedAggregationMapsNestedFieldsAndProjectionAliases() {
        String id = "fixture-agg008";
        var collection = template.getDb()
            .getCollection("orders_aggregation_demo_008");

        collection.deleteOne(Filters.eq("_id", id));
        try {
            collection.insertOne(
                new Document("_id", id)
                    .append("tenant_id", "fixture-tenant-008")
                    .append("state_code", "PAID")
                    .append("amount_vnd", 500000L)
                    .append("placed_at",
                        Date.from(Instant.parse(
                            "2026-10-01T08:00:00Z")))
                    .append("buyer_doc",
                        new Document("display_name", "Test")
                            .append("city_name", "Huế"))
                    .append("order_lines", List.of(
                        new Document("sku", "A").append("qty", 2)))
            );

            var pipeline = Aggregation.newAggregation(
                OrderDocument.class,
                Aggregation.match(
                    Criteria.where("tenantId").is("fixture-tenant-008")
                        .and("state").is(OrderState.PAID)
                ),
                Aggregation.project()
                    .and("_id").as("orderId")
                    .and("buyer.displayName").as("buyerName")
                    .and("totalVnd").as("amount")
                    .andExclude("_id"),
                Aggregation.sort(Sort.Direction.DESC, "amount")
            );

            List<OrderCard> cards = template.aggregate(
                pipeline, OrderCard.class
            ).getMappedResults();

            assertThat(cards).hasSize(1);
            assertThat(cards.get(0).orderId()).isEqualTo(id);
            assertThat(cards.get(0).buyerName()).isEqualTo("Test");
            assertThat(cards.get(0).amount()).isEqualTo(500000L);
        } finally {
            collection.deleteOne(Filters.eq("_id", id));
        }
    }
}
~~~

Test gọi **aggregation thực**, không chỉ giả lập converter. Trường `buyer_doc.display_name` ở BSON đã được xác minh thông qua `buyer.displayName` của Java input. Alias `buyerName`/`amount` được khẳng định bằng output DTO.

**Chỉ chạy trên database test biệt lập.** Phần setup/cleanup chủ động xóa đúng ID fixture, không dùng ID này ở job hoặc test chạy song song.

### 16.2. Test `strictMapping` phát hiện typo

Thêm một integration test riêng (hoặc test chuyên biệt cho mapping context):

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;

@Test
void strictMappingRejectsUnknownInputProperty() {
    var typoPipeline = Aggregation.newAggregation(
        OrderDocument.class,
        Aggregation.project("totalVNDD")
    ).withOptions(
        AggregationOptions.builder().strictMapping().build()
    );

    assertThatThrownBy(() ->
        template.aggregate(typoPipeline, Document.class)
    ).isInstanceOf(RuntimeException.class);
}
~~~

Đoạn test này có thể đặt trong cùng class `AggregationFieldMappingTest` ở mục 16.1, với `template` đã inject và import `Document`/`Aggregation` tương ứng. Nó kiểm sự kiện lỗi khi một input property không tồn tại; không nên cố định message/loại exception quá chi tiết nếu dự án cần hỗ trợ nhiều phiên bản Spring Data.

### 16.3. Test alias stage sau không dùng tên nguồn

Chạy hai pipeline **độc lập**:

~~~java
// Đúng: sort trên alias đã được $project xuất ra.
var correct = Aggregation.newAggregation(
    OrderDocument.class,
    Aggregation.project().and("totalVnd").as("amount"),
    Aggregation.sort(Sort.Direction.DESC, "amount")
);

// Sai ngữ nghĩa: totalVnd không còn được xuất sau project.
var wrong = Aggregation.newAggregation(
    OrderDocument.class,
    Aggregation.project().and("totalVnd").as("amount"),
    Aggregation.sort(Sort.Direction.DESC, "totalVnd")
);
~~~

Không dựa vào giả định cả hai phải phát sinh cùng một loại exception. Hãy xác minh: pipeline đúng sort theo `amount` và có giá trị; pipeline sai phải bị **đánh dấu là không hợp đồng** dù framework báo lỗi ở lúc render hay server trả kết quả không mong muốn.

### 16.4. Ma trận kiểm thử cần có

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Typed `$match` trên `tenantId` | BSON lọc `tenant_id` |
| Typed `$match` trên `state` enum | BSON lọc `state_code` chính xác |
| Typed `$group.sum("totalVnd")` | Dùng field `amount_vnd`, tổng t01 PAID 2.100.000 |
| Nested `buyer.city` | Dùng `buyer_doc.city_name`, Hà Nội 3, Huế 1 |
| Array `lines.quantity` | Dùng `order_lines.qty`, tổng theo SKU đúng |
| `project().and(...).as(...)` | Output có alias mong muốn, không tự rename source data |
| Sort sau project | Tham chiếu alias, không tham chiếu property đã bị loại |
| `_id` bị exclude | Output không chứa `_id` khi đã tạo `orderId` |
| `strictMapping` và property gõ sai | Báo lỗi tham chiếu field chưa có trong input |
| Relaxed mapping | Tên không biết có thể được giữ; cần kiểm output |
| No mapping | Tên BSON tự viết không bị đổi |
| Raw stage | Đường dẫn dùng BSON, không trông chờ mapping ngầm |
| DTO output | Tên/kiểu constructor khớp alias |
| Tenant khác | `o804` tuyệt đối không được tính vào kết quả t01 |
| Legacy missing/null | Có chính sách riêng, không nhầm với lỗi gõ sai property |

## 17. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `$match` trả rỗng nhưng `mongosh` có dữ liệu | Dùng tên Java trong raw BSON hoặc tên BSON sai trong typed context | Kiểm tra `@Field`, input type và pipeline thực |
| `strictMapping` báo lỗi `totalVNDD` | Property không tồn tại trên domain input | Sửa tên Java property; không tắt strict để che typo |
| Sau khi đổi sang `noMapping` thì query rỗng | Code vẫn dùng `tenantId` thay vì BSON `tenant_id` | Dùng một quy ước tên nhất quán |
| DTO có `amount=0` dù BSON có `amount_vnd` | `$project` không tạo alias `amount` hoặc kiểu DTO không khớp | Kiểm tra output `Document` và constructor |
| Sort sau project không đúng | Dùng `totalVnd` sau khi chỉ còn `amount` | Sort theo alias đã expose |
| Group kết quả có `_id="PAID"`, không phải ID đơn hàng | `$group` đặt khóa nhóm ở `_id` | Đổi alias khóa nhóm sau group |
| Output vừa có `_id` vừa có `orderId` | Projection chưa exclude `_id` | Dùng `andExclude("_id")` |
| Nested city không tìm thấy | Quên mapping ở `buyer` hoặc `BuyerInfo.city` | So sánh `buyer.city` với `buyer_doc.city_name` |
| Unit tổng theo SKU sai | Group tham chiếu `quantity` thay vì `qty` hoặc unwind sai mảng | Dùng typed mapping và kiểm raw pipeline |
| Raw `AggregationOperation` không áp `@Field` | Trả `Document` thủ công không qua context mapping | Viết BSON đúng hoặc gọi `context.getMappedObject(...)` có kiểm chứng |
| Tắt strict mà kết quả vẫn sai | Relaxed mode cho phép property lạ, server xử lý missing | Bật strict ở use case typed và test giá trị |
| Tổng t01 có cả t02 | Thiếu điều kiện tenant | Tenant từ security context phải vào `$match` |
| Pipeline ít field nhưng hiệu năng vẫn kém | `$group`/sort tốn tài nguyên hoặc index không hỗ trợ | Đo `explain`, stage order, index, dữ liệu thật |
| Test mock pass, production sai mapping | Mock không chạy converter hoặc MongoDB | Integration test qua `MongoTemplate.aggregate` |
| Document thiếu `amount_vnd` trong thực tế | Schema legacy, không phải lỗi property Java | Kiểm BSON/migration/null policy |

## 18. Checklist viết aggregation có mapping đúng

1. **Định nghĩa input schema:** entity class, `@Document`, `@Field`, nested object và kiểu BSON.
2. **Chọn ngôn ngữ tên:** typed DSL dùng **property Java**; raw MongoDB dùng **tên BSON**.
3. **Ưu tiên typed aggregation** khi pipeline xuất phát từ một entity có metadata rõ ràng.
4. **Bật `strictMapping()`** khi cần bắt tham chiếu property sai; hiểu các giới hạn của nó.
5. **Đặt alias có mục đích:** `@Field` ánh xạ lưu trữ, `.as(...)` tạo output stage.
6. **Theo dõi field exposure** sau từng `$project`, `$group` và `$unwind`.
7. **Sort/group theo tên hiện có**, không dùng property đã bị loại ở stage trước.
8. **Phân biệt `_id` gốc và `_id` nhóm**, thiết kế DTO output tường minh.
9. **Không tin raw stage được map tự động**; tự kiểm BSON hoặc gọi mapping context đúng chỗ.
10. **Giữ tenant/authorization bắt buộc** ngay ở `$match`, không tin strict mapping làm thay.
11. **Kiểm dữ liệu legacy**: missing/null/sai kiểu cần chính sách xử lý riêng.
12. **Kiểm pipeline thật** bằng `mongosh`/command listener và integration test cho alias, nested mapping, total.
13. **Đo index/hiệu năng** trên dữ liệu đại diện; đừng suy chi phí từ một fixture nhỏ.

## 19. Bài thực hành

Các bài sau dùng fixture ban đầu tại mục 2, không cần thao tác ghi.

### Bài 1 — Phân biệt ba tên

Entity khai báo `@Field("amount_vnd") long totalVnd;`. Báo cáo cần field output `revenue`.

**Câu hỏi:** Đâu là property Java, đâu là field BSON, đâu là alias?

**Đáp án:** `totalVnd` là property Java; `amount_vnd` là field MongoDB; `revenue` là alias do `project().and("totalVnd").as("revenue")` tạo ra.

### Bài 2 — Chọn đúng `Criteria` typed

Viết điều kiện tìm đơn t01, trạng thái PAID, tiền từ 500.000:

~~~java
match(Criteria.where("tenantId").is("t01")
    .and("state").is(OrderState.PAID)
    .and("totalVnd").gte(500_000L))
~~~

**Đáp án:** đoạn trên đúng khi dùng typed aggregation với `OrderDocument.class`. MongoDB thấy các tên `tenant_id`, `state_code`, `amount_vnd`; kết quả `o802` và `o806`.

### Bài 3 — Alias `$project`

Cho:

~~~java
project().and("totalVnd").as("amount")
~~~

Stage tiếp nên sort `totalVnd` hay `amount`?

**Đáp án:** `amount`, vì stage project chỉ expose alias đó. Dùng `sort(Sort.Direction.DESC, "amount")`.

### Bài 4 — `_id` thay đổi ý nghĩa

Sau:

~~~java
group("state").sum("totalVnd").as("grossVnd")
~~~

`_id` còn là ID order không?

**Đáp án:** Không. `_id` của output `$group` là **khóa nhóm**, ở đây là state (`NEW`/`PAID`). Muốn output `stateName`, tạo `project().and("_id").as("stateName")` và loại `_id` nếu cần.

### Bài 5 — Tính tổng để phát hiện thiếu tenant

Tenant t01 có bốn order PAID. Tổng tiền là bao nhiêu?

**Đáp án:** **2.100.000 VND**. Nếu báo cáo bao gồm `o804` của t02, tổng sẽ cao hơn và vi phạm phạm vi tenant.

### Bài 6 — Nested property path

Java `buyer.city` dùng `@Field("buyer_doc")` trên buyer và `@Field("city_name")` trên city. BSON path nào sẽ được sử dụng?

**Đáp án:** `buyer_doc.city_name`. Với t01/PAID, Hà Nội có 3 order, Huế có 1.

### Bài 7 — `strictMapping`

Người viết typed aggregation gõ `"totalVNDD"` trong `project`. Từ Spring Data MongoDB 3.2, liệu mặc định luôn ném lỗi giống phiên bản cũ không?

**Đáp án:** Không. Để yêu cầu kiểm tra property không tồn tại, dùng:

~~~java
AggregationOptions.builder().strictMapping().build()
~~~

và áp dụng bằng `pipeline.withOptions(...)`. Kiểm thử trên phiên bản framework đang dùng.

### Bài 8 — `noMapping`

Pipeline đã chọn `noMapping()` nhưng filter `Criteria.where("tenantId").is("t01")`. Có vấn đề gì?

**Đáp án:** `noMapping` không tự đổi `tenantId` sang `tenant_id`. Trên fixture, MongoDB không có `tenantId` nên query có thể rỗng. Khi chủ động noMapping, dùng BSON field name thật.

### Bài 9 — Raw stage

Một `AggregationOperation` raw trả:

~~~java
new Document("$match", new Document("tenantId", "t01"))
~~~

Nó có chắc được chuyển thành `tenant_id` không?

**Đáp án:** Không. Raw BSON có thể được đưa nguyên xuống driver. Dùng `tenant_id` hoặc sử dụng `context.getMappedObject(...)` một cách có chủ đích, rồi kiểm tra pipeline thực.

### Bài 10 — Aggregation trả DTO

Muốn lấy `OrderCard(orderId, buyerName, amount)`, điều gì cần đồng bộ?

**Đáp án:** Input type phải là `OrderDocument.class` để map `@Field`; `$project` phải tạo đúng ba alias `orderId`/`buyerName`/`amount`; constructor/record output phải nhận được đúng tên và kiểu BSON. Không trông chờ `@Field` input tự đổi output DTO.

### Bài 11 — Lỗi sai kiểu BSON

Một document legacy có `amount_vnd: "500000"` dạng chuỗi. `strictMapping` có phát hiện không?

**Đáp án:** Không; property `totalVnd` tồn tại trên Java class nên tên vẫn hợp lệ, nhưng dữ liệu thật có thể sai kiểu. Cần schema validation, migration dữ liệu và integration test cho số liệu tổng hợp.

### Bài 12 — Hiệu năng

Pipeline nhóm doanh thu theo state vẫn chậm dù đã bật `strictMapping`. Nên làm gì?

**Đáp án:** Kiểm tra index trên BSON field của `$match`, độ chọn lọc tenant/state, số document qua `$group`, plan và metric; strictMapping kiểm tên property chứ không tối ưu thuật toán/truy vấn.

## Tài liệu tham khảo

- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): `TypedAggregation`, `@Field`, thay đổi từ phiên bản 3.2, projection aliases, field exposure và các aggregation stages.
- [Spring Data MongoDB — `AggregationOptions.Builder` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/AggregationOptions.Builder.html): `strictMapping()`, `relaxedMapping()`, `noMapping()` và các tùy chọn vận hành.
- [Spring Data MongoDB — `TypedAggregation` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/TypedAggregation.html): input type, `withOptions` và thông tin mapping.
- [Spring Data MongoDB — `MongoOperations` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html): các overload `aggregate`, `aggregateStream`.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): ánh xạ `@Document`, `@Field`, `@MongoId` và embedded properties.
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/): cấu trúc stage và dữ liệu trung gian.
- [MongoDB Manual — `$project`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/): include/exclude, field expressions và aliases.
- [MongoDB Manual — `$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/): khóa nhóm `_id` và accumulators.
- [MongoDB Manual — `$unwind`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/): xử lý array thành các document trung gian.
- [MongoDB Manual — `$match`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/): lọc document trước các stage tổng hợp.
