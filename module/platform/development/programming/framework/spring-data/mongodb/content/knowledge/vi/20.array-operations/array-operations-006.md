# Cập nhật mọi phần tử bằng `$[]`

> **Chương:** Thao tác array  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; thực hành truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Hiểu phạm vi tác động của toán tử **all positional** `$[]`; cập nhật mảng số và mảng embedded document; phân biệt `$[]` với `$` và `$[identifier]`; kết hợp `MongoTemplate`, xử lý mảng lồng nhau, giá trị thiếu, `upsert`, kiểm soát đồng thời và kiểm thử.

## 1. Vì sao cần toán tử `$[]`?

Giả sử một đơn hàng chứa các mức điểm:

~~~javascript
{
  _id: "o601",
  scores: [70, 80, 90]
}
~~~

Nếu yêu cầu nghiệp vụ là **cộng 5 vào mọi điểm**, thao tác MongoDB phù hợp là:

~~~javascript
db.orders_array_demo_006.updateOne(
  { _id: "o601" },
  { $inc: { "scores.$[]": 5 } }
);
// scores: [75, 85, 95]
~~~

`$[]` là *all positional operator*: một vị trí đặc biệt trong đường dẫn cập nhật, có nghĩa là **mọi phần tử của mảng ở cấp đó**. Nó không phải một array Java, cũng không phải dấu cú pháp thông thường có thể thay bằng `*`.

Cú pháp khái quát:

~~~javascript
db.collection.updateOne(
  { /* điều kiện chọn document */ },
  {
    $set: {
      "arrayField.$[]": newValue
    }
  }
);
~~~

Với mảng chứa object, thêm đường dẫn trường sau `$[]`:

~~~javascript
db.collection.updateOne(
  { _id: "some-id" },
  {
    $set: {
      "line_items.$[].reviewed": true
    }
  }
);
~~~

Trong ví dụ thứ hai, mọi phần tử của `line_items` đều có thuộc tính `reviewed` được đặt thành `true`, kể cả phần tử chưa từng khớp một điều kiện về SKU.

### 1.1. Hai cấp phạm vi không được đánh đồng

Đây là quy tắc quan trọng nhất của bài:

1. **Query chọn document:** `{ _id: "o601" }` hoặc `{ tenant_id: "t01", state: "OPEN" }`.
2. **`$[]` chọn phần tử trong mảng:** **tất cả phần tử** thuộc trường mảng của **mỗi document đã chọn**.

~~~mermaid
flowchart TD
    Q["Filter: chọn document phù hợp"] --> D1["Document o601"]
    Q --> D2["Document o602"]
    D1 --> A1["scores[0]"]
    D1 --> A2["scores[1]"]
    D1 --> A3["scores[2]"]
    D2 --> B1["scores[0]"]
    D2 --> B2["scores[1]"]
    A1 --> U["Áp cùng update operator"]
    A2 --> U
    A3 --> U
    B1 --> U
    B2 --> U
~~~

Khi dùng `updateMany`, số document được chọn có thể nhiều; khi dùng `$[]`, số **phần tử mảng bên trong mỗi document** được sửa cũng có thể nhiều. `UpdateResult.modifiedCount` đếm **document**, **không đếm phần tử**.

## 2. Bộ dữ liệu tự thực hành

Các ví dụ dùng `mongosh` trên database **học tập riêng**, không dùng collection nghiệp vụ đang chạy. Hãy nạp dữ liệu ban đầu một lần:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_array_demo_006;

orders.insertMany([
  {
    _id: "o601",
    tenant_id: "t01",
    state: "OPEN",
    scores: [70, 80, 90],
    line_items: [
      { sku: "A", qty: 2, reviewed: false, unitPriceVnd: 120000 },
      { sku: "B", qty: 4, reviewed: false, unitPriceVnd: 50000 }
    ],
    shipments: [
      {
        warehouse: "HN",
        packages: [
          { sku: "A", scanned: false },
          { sku: "B", scanned: false }
        ]
      },
      {
        warehouse: "DN",
        packages: [
          { sku: "C", scanned: false }
        ]
      }
    ]
  },
  {
    _id: "o602",
    tenant_id: "t01",
    state: "OPEN",
    scores: [65, 75],
    line_items: [
      { sku: "A", qty: 5, reviewed: false, unitPriceVnd: 120000 },
      { sku: "C", qty: 1, reviewed: false, unitPriceVnd: 70000 }
    ],
    shipments: [
      {
        warehouse: "HN",
        packages: [{ sku: "A", scanned: false }]
      }
    ]
  },
  {
    _id: "o603",
    tenant_id: "t01",
    state: "DONE",
    scores: [],
    line_items: [],
    shipments: []
  },
  {
    _id: "o604",
    tenant_id: "t02",
    state: "OPEN",
    scores: [90],
    line_items: [
      { sku: "A", qty: 9, reviewed: false, unitPriceVnd: 120000 }
    ],
    shipments: []
  },
  {
    _id: "o605",
    tenant_id: "t01",
    state: "OPEN",
    shipments: []
    // Dữ liệu legacy: thiếu scores và line_items.
  }
]);

orders.createIndex({ tenant_id: 1, state: 1 });
orders.find({}, { _id: 1, tenant_id: 1, state: 1, scores: 1 });
~~~

Các ID cố định để đối chiếu kết quả. Chạy lại `insertMany` trên collection đã có cùng ID sẽ báo lỗi trùng khóa `_id`. Tránh dùng `drop()`/`deleteMany({})` trên database chia sẻ chỉ để “reset” bài học; dùng collection test mới hoặc dọn đúng dữ liệu do bạn sở hữu.

| ID | Tenant | Scores | Số dòng hàng | Điểm cần chú ý |
| --- | --- | --- | ---: | --- |
| `o601` | t01 | `[70,80,90]` | 2 | Dòng A và B, hai kho HN/DN |
| `o602` | t01 | `[65,75]` | 2 | Dòng A và C, kho HN |
| `o603` | t01 | `[]` | 0 | Mảng rỗng |
| `o604` | t02 | `[90]` | 1 | Tenant khác |
| `o605` | t01 | Missing | Missing | Document cũ thiếu trường mảng |

**Quy ước:** Mỗi đoạn update dưới đây được giải thích trên **fixture ban đầu**; nếu không nói rõ chạy tuần tự, hãy xem các đoạn là **những kịch bản độc lập**. Sau một phép `$inc` hoặc `$set`, dữ liệu đã thay đổi nên kết quả của ví dụ tiếp theo có thể khác.

## 3. Mảng giá trị đơn: cập nhật tất cả phần tử

### 3.1. `$inc` với mảng số

~~~javascript
const result = orders.updateOne(
  { _id: "o601" },
  { $inc: { "scores.$[]": 5 } }
);

printjson(result);
orders.findOne({ _id: "o601" }, { scores: 1 });
// scores: [75, 85, 95]
~~~

`$inc` cộng vào từng phần tử số. Cả ba vị trí đều được tác động bằng **một lệnh update một document**. Nếu mảng có phần tử không phải số, đừng trông đợi phép cộng hoạt động như với dữ liệu hợp lệ; phải kiểm tra schema hoặc xử lý dữ liệu sai kiểu trước.

### 3.2. `$set` gán cùng một giá trị cho mọi phần tử

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "scores.$[]": 0 } }
);
// scores: [0, 0, 0]
~~~

`$set` ở đường dẫn `scores.$[]` **không** thay toàn mảng bằng số 0; nó thay **giá trị của từng phần tử** thành 0 nhưng vẫn giữ độ dài mảng. Nếu muốn thay cả mảng bằng một mảng mới, dùng:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { scores: [10, 20] } }
);
// scores: [10, 20]
~~~

Hai cách khác nhau về phạm vi, dữ liệu giữ lại và khả năng xử lý đồng thời. Thay toàn mảng có thể làm mất phần tử vừa được writer khác bổ sung.

### 3.3. Mảng rỗng: không có phần tử để cập nhật

~~~javascript
const result = orders.updateOne(
  { _id: "o603" },
  { $set: { "scores.$[]": 0 } }
);

// scores của o603 vẫn là [].
~~~

Document `o603` **khớp** theo `_id`, nhưng `scores` rỗng nên không có phần tử nào để sửa. Với driver update trực tiếp như ví dụ này, `matchedCount` có thể là 1 còn `modifiedCount` là 0. Chú ý khi dùng `MongoTemplate` với entity có `@Version`: framework có thể tự tăng version, làm `modifiedCount` khác kịch bản raw driver; không đánh đồng số đếm với số phần tử.

### 3.4. `$unset`, `$pull` và xóa mảng không giống nhau

Muốn **loại phần tử** khỏi mảng, dùng operator phù hợp như `$pull`:

~~~javascript
// Xóa các số từ 80 trở lên (trên fixture gốc o601).
orders.updateOne(
  { _id: "o601" },
  { $pull: { scores: { $gte: 80 } } }
);
// scores: [70].
~~~

Muốn **xóa hẳn trường mảng**:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $unset: { scores: "" } }
);
// Document không còn trường scores.
~~~

Muốn **giữ trường nhưng xóa tất cả phần tử**:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { scores: [] } }
);
// scores: [].
~~~

Không dùng `$unset` trên vị trí mảng với giả định các phần tử sẽ được dồn lại như `$pull`. Khi nghiệp vụ là xóa các phần tử thỏa điều kiện, hãy chọn `$pull`/pipeline thay vì một cập nhật positional không phù hợp.

## 4. Mảng document nhúng: cập nhật field trên mọi object

Trong `o601` có:

~~~javascript
line_items: [
  { sku: "A", qty: 2, reviewed: false, unitPriceVnd: 120000 },
  { sku: "B", qty: 4, reviewed: false, unitPriceVnd: 50000 }
]
~~~

Để đánh dấu **mọi dòng hàng** đã được xem:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "line_items.$[].reviewed": true } }
);
~~~

Kết quả:

~~~javascript
line_items: [
  { sku: "A", qty: 2, reviewed: true, unitPriceVnd: 120000 },
  { sku: "B", qty: 4, reviewed: true, unitPriceVnd: 50000 }
]
~~~

Không cần liệt kê chỉ số `line_items.0.reviewed`, `line_items.1.reviewed`. `$[]` còn hoạt động nếu mảng dài hơn số phần tử mà ứng dụng dự đoán, miễn dữ liệu có kiểu và cấu trúc phù hợp.

### 4.1. Tăng số lượng ở tất cả dòng

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $inc: { "line_items.$[].qty": 1 } }
);
// A qty: 2 -> 3; B qty: 4 -> 5.
~~~

Đây là thao tác cộng trên mọi dòng hàng, **không phải** cách an toàn để cộng số lượng chỉ cho SKU A. Nếu nghiệp vụ cần chọn những dòng hàng theo SKU hoặc điều kiện số lượng, xem `$[identifier]` ở mục 6.

### 4.2. Đổi cả object và đổi field con là hai việc khác nhau

~~~javascript
// Chỉ sửa flag, giữ các field sku/qty/unitPriceVnd.
{ $set: { "line_items.$[].reviewed": true } }

// Thay giá trị mỗi phần tử mảng bằng một document mới:
{ $set: { "line_items.$[]": { reviewed: true } } }
~~~

Lệnh thứ hai **làm mất** `sku`, `qty` và `unitPriceVnd` trong từng phần tử vì nó thay cả embedded object. Để không làm mất dữ liệu, cập nhật chính xác **đường dẫn trường con** cần sửa.

## 5. Lỗi dễ gặp: query khớp một phần tử nhưng `$[]` sửa tất cả

Xét:

~~~javascript
orders.updateOne(
  {
    _id: "o601",
    "line_items.sku": "A"
  },
  {
    $set: { "line_items.$[].reviewed": true }
  }
);
~~~

Ý nghĩa thực:

1. `"line_items.sku": "A"` kiểm tra **trong order có ít nhất một dòng SKU A**.
2. Vì `o601` có A, document này được chọn.
3. `"line_items.$[].reviewed"` áp dụng cho **cả dòng A lẫn dòng B** trong `o601`.

| Dòng hàng | SKU | Khớp `"line_items.sku":"A"` riêng lẻ? | Bị `$[]` cập nhật? |
| --- | --- | --- | --- |
| `o601.lines[0]` | A | Có | **Có** |
| `o601.lines[1]` | B | Không | **Có** |

**Không có mối liên kết ngầm** giữa phần tử khiến *document* khớp query và các phần tử được `$[]` cập nhật.

Điều này đặc biệt nguy hiểm nếu nghiệp vụ là “chỉ giảm giá dòng SKU A” hoặc “chỉ đánh dấu dòng chưa xử lý”. Khi đó, đổi từ `$[]` sang `$` hoặc `$[identifier]` theo đúng ý định.

### 5.1. So sánh ba positional operator

| Operator | Chọn phần tử nào? | Cần gì? | Ví dụ |
| --- | --- | --- | --- |
| `$` | Phần tử **đầu tiên khớp** điều kiện array trong query | Query ràng buộc array tương ứng | `"line_items.$.reviewed"` |
| `$[]` | **Mọi phần tử** của array trong mỗi document khớp | Trường array phải tồn tại, đúng cấu trúc | `"line_items.$[].reviewed"` |
| `$[line]` | **Mọi phần tử khớp** `arrayFilters` | Định nghĩa identifier `line` trong `arrayFilters` | `"line_items.$[line].reviewed"` |

`$` phù hợp khi chỉ muốn một phần tử đầu tiên khớp; nó có những giới hạn khi query đi qua nhiều array hoặc dùng trong upsert. `$[]` phù hợp khi mọi phần tử thật sự cần cùng một cập nhật. `$[identifier]` cho phép filter theo thuộc tính của **từng phần tử**.

### 5.2. Cập nhật đúng phần tử đầu tiên bằng `$`

~~~javascript
orders.updateOne(
  { _id: "o601", "line_items.sku": "A" },
  { $set: { "line_items.$.reviewed": true } }
);
// Chỉ phần tử A đầu tiên khớp query bị sửa.
~~~

Trong trường hợp mảng có nhiều dòng SKU A, `$` chỉ xử lý **phần tử đầu tiên khớp**. Nếu phải xử lý **mọi dòng A**, dùng filtered positional `$[line]`.

## 6. `$[identifier]` + `arrayFilters` khi cần lọc phần tử

### 6.1. Chỉ đánh dấu các dòng SKU A

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "line_items.$[line].reviewed": true } },
  {
    arrayFilters: [
      { "line.sku": "A" }
    ]
  }
);
// Dòng A được đánh dấu; dòng B giữ reviewed:false.
~~~

`line` là **tên biến của phần tử mảng**, không phải một field thật trong MongoDB. Nó được khai báo trong đường dẫn `$[line]` và dùng trong `arrayFilters` qua `line.sku`.

Tên identifier phải hợp lệ theo quy tắc MongoDB (bắt đầu bằng chữ thường, sau đó là chữ/số). Không thêm dấu cách vào `$[ line ]`; dùng `$[line]`.

### 6.2. Điều kiện số lượng trong array filter

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "line_items.$[line].reviewed": true } },
  {
    arrayFilters: [
      {
        "line.qty": { $gte: 3 }
      }
    ]
  }
);
// Trên fixture gốc: chỉ dòng B (qty:4) được sửa.
~~~

Filter `arrayFilters` không phải query chọn order; nó chỉ quyết định những **phần tử** được cập nhật trong mỗi document đã được query chọn.

### 6.3. `$[]` không nhận `arrayFilters` của chính nó

`$[]` không mang tên identifier nên **không cần** một mảng `arrayFilters` tương ứng:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "line_items.$[].reviewed": true } }
);
~~~

Đừng tự đặt `arrayFilters: [{"line.sku":"A"}]` cho một update chỉ có `$[]` mà không có `$[line]`. Nếu muốn lọc, phải **đổi chính đường dẫn update** sang `$[line]`.

### 6.4. Giới hạn của `arrayFilters`

Theo MongoDB Manual, một array filter document không hỗ trợ một số query operator như `$expr`, `$text` hoặc `$where`. Nếu cần tính toán phức tạp theo nhiều trường hoặc dựng lại mảng, cân nhắc **aggregation pipeline update** (`$map`/`$cond`) thay vì cố ép logic vào `arrayFilters`.

Không trộn `arrayFilters` với **update pipeline** mà kỳ vọng chúng hoạt động cùng nhau; `arrayFilters` là tùy chọn cho cập nhật với update operators và không áp dụng cho update dạng aggregation pipeline.

## 7. Mảng lồng nhau: `$[]` ở từng cấp

Order `o601` có nhiều shipment, mỗi shipment có nhiều package:

~~~text
shipments
├── HN
│   └── packages: [A:false, B:false]
└── DN
    └── packages: [C:false]
~~~

### 7.1. Đánh dấu tất cả package trong tất cả shipment

~~~javascript
orders.updateOne(
  { _id: "o601" },
  {
    $set: {
      "shipments.$[].packages.$[].scanned": true
    }
  }
);
~~~

Đường dẫn giải thích theo cấp:

~~~text
shipments             mảng shipment
    .$[]              mọi shipment
    .packages          mảng package trong từng shipment
    .$[]              mọi package
    .scanned          trường boolean cần sửa
~~~

Kết quả: cả A, B ở HN và C ở DN đều có `scanned: true`. Dùng hai `$[]` không có nghĩa chỉ chọn package đầu tiên trong mỗi shipment; nó trải qua **tất cả phần tử của cả hai cấp mảng**.

### 7.2. Tất cả shipment, nhưng chỉ package SKU A

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "shipments.$[].packages.$[pkg].scanned": true } },
  {
    arrayFilters: [
      { "pkg.sku": "A" }
    ]
  }
);
// A ở HN được sửa; B ở HN và C ở DN không đổi.
~~~

Ở cấp `shipments`, `$[]` vẫn đi qua mọi shipment. Ở cấp `packages`, `$[pkg]` chỉ sửa những package thỏa `pkg.sku = "A"`.

### 7.3. Chỉ shipment HN, nhưng tất cả package của shipment đó

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "shipments.$[ship].packages.$[].scanned": true } },
  {
    arrayFilters: [
      { "ship.warehouse": "HN" }
    ]
  }
);
// A/B ở HN được sửa; package C của DN giữ scanned:false.
~~~

### 7.4. Lọc đồng thời hai cấp

~~~javascript
orders.updateOne(
  { _id: "o601" },
  {
    $set: {
      "shipments.$[ship].packages.$[pkg].scanned": true
    }
  },
  {
    arrayFilters: [
      { "ship.warehouse": "HN" },
      { "pkg.sku": "A" }
    ]
  }
);
// Chỉ A trong shipment HN.
~~~

**Nguyên tắc thiết kế:** đặt `$[]` ở cấp muốn **toàn bộ** phần tử, đặt `$[identifier]` ở cấp muốn **lọc**. Khi có nhiều array lồng nhau, nên viết rõ từng cấp và test cả trường hợp không khớp.

### 7.5. Khi mảng lồng nhau không có cấu trúc đồng nhất

Nếu một shipment thiếu `packages`, có `packages: null`, hoặc chứa phần tử không phải document, các đường dẫn như `shipments.$[].packages.$[].scanned` có thể gặp lỗi vì path không tồn tại hoặc sai kiểu. `$[]` không tự tạo mảng con còn thiếu để bạn tiếp tục đi qua.

Với schema có dữ liệu cũ lẫn dữ liệu mới, nên **chuẩn hóa schema** hoặc dùng update được thiết kế riêng cho nhánh dữ liệu lỗi. Không giả định `$[]` bỏ qua mọi phần tử sai kiểu một cách an toàn.

## 8. Spring Data MongoDB: ánh xạ `$[]` qua `MongoTemplate`

### 8.1. Model Java cho document và array

Ví dụ đặt mỗi class trong một file thuộc package `com.example.arrayops`.

~~~java
// OrderLine.java
package com.example.arrayops;

import org.springframework.data.mongodb.core.mapping.Field;

public class OrderLine {
    private String sku;

    @Field("qty")
    private int quantity;

    private boolean reviewed;
    private long unitPriceVnd;

    protected OrderLine() { }

    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
    public boolean isReviewed() { return reviewed; }
    public long getUnitPriceVnd() { return unitPriceVnd; }
}
~~~

~~~java
// PackageItem.java
package com.example.arrayops;

public class PackageItem {
    private String sku;
    private boolean scanned;

    protected PackageItem() { }

    public String getSku() { return sku; }
    public boolean isScanned() { return scanned; }
}
~~~

~~~java
// Shipment.java
package com.example.arrayops;

import java.util.List;

public class Shipment {
    private String warehouse;
    private List<PackageItem> packages;

    protected Shipment() { }

    public String getWarehouse() { return warehouse; }
    public List<PackageItem> getPackages() { return packages; }
}
~~~

~~~java
// OrderDocument.java
package com.example.arrayops;

import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_array_demo_006")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String state;
    private List<Integer> scores;

    @Field("line_items")
    private List<OrderLine> lineItems;

    private List<Shipment> shipments;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
    public List<Integer> getScores() { return scores; }
    public List<OrderLine> getLineItems() { return lineItems; }
    public List<Shipment> getShipments() { return shipments; }
}
~~~

Đáng chú ý:

- Property Java `lineItems` được lưu thành trường BSON `line_items`.
- Property Java `OrderLine.quantity` được lưu thành BSON `qty`.
- `MongoTemplate` sẽ sử dụng metadata entity để ánh xạ **đường dẫn update/query** khi truyền `OrderDocument.class`.
- Hai loại identifier `$[]` và `$[line]` không phải property Java; chúng là **toán tử đường dẫn** của MongoDB.

### 8.2. Cập nhật mảng scalar với `Update.inc`

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

// Trong service có sẵn MongoTemplate template:
Query byId = Query.query(Criteria.where("id").is("o601"));

Update incrementEachScore =
    new Update().inc("scores.$[]", 5);

UpdateResult result = template.updateFirst(
    byId, incrementEachScore, OrderDocument.class
);
// Với dữ liệu gốc: scores [70,80,90] -> [75,85,95].
~~~

`Update.inc("scores.$[]", 5)` là cách biểu diễn `{ $inc: { "scores.$[]": 5 } }` trong Spring Data. Không có một method bắt buộc riêng tên `updateAllElements()`: bạn đưa `$[]` trực tiếp vào **đường dẫn thuộc tính**.

### 8.3. Cập nhật mọi object nhúng bằng `Update.set`

~~~java
Query query = Query.query(
    Criteria.where("id").is("o601")
);

Update update =
    new Update().set("lineItems.$[].reviewed", true);

UpdateResult result = template.updateFirst(
    query, update, OrderDocument.class
);
~~~

Với metadata đã khai báo, đường dẫn Java `lineItems.$[].reviewed` tương ứng với BSON `line_items.$[].reviewed`. Cả dòng A và dòng B của `o601` bị đánh dấu, không cần load `OrderDocument` và sửa `List<OrderLine>` trong bộ nhớ.

### 8.4. Cập nhật mọi phần tử của nhiều document

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("state").is("OPEN")
        .and("scores").type(4) // BSON array; Type 4.
);

Update update = new Update().inc("scores.$[]", 5);

UpdateResult result = template.updateMulti(
    query, update, OrderDocument.class
);
~~~

Filter trên fixture gốc chọn `o601` và `o602`: `o603` không OPEN, `o604` thuộc t02, `o605` không có `scores`. Tổng cộng **5 phần tử score** được tăng trong **2 document**. Khi write acknowledged và không có field version/callback khác, `matchedCount = 2` và `modifiedCount = 2`; số `5` không xuất hiện trong `modifiedCount`.

Trong code nghiệp vụ, có thể dùng `org.bson.BsonType.ARRAY.getValue()` thay cho số BSON 4 để dễ hiểu hơn nếu API criteria/driver hỗ trợ kiểu đó theo phiên bản; quan trọng là ràng buộc **trường array thật**, không dựa trên phỏng đoán.

### 8.5. Fluent update vẫn dùng cùng đường dẫn

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o601"))
    .apply(new Update().set("lineItems.$[].reviewed", true))
    .first();

UpdateResult all = template.update(OrderDocument.class)
    .matching(Criteria.where("tenantId").is("t01")
        .and("state").is("OPEN")
        .and("scores").type(4))
    .apply(new Update().inc("scores.$[]", 5))
    .all();
~~~

`first()` tương ứng ý tưởng `updateFirst`; `all()` tương ứng `updateMulti`. Khác biệt về số **document** không thay đổi ngữ nghĩa `$[]`: mỗi document được chọn vẫn cập nhật **toàn bộ phần tử** ở đường dẫn chỉ định.

### 8.6. Spring Data `Update.filterArray` dùng khi có `$[identifier]`

Nếu chỉ muốn dòng có số lượng `qty >= 3`:

~~~java
Update filtered = new Update()
    .set("lineItems.$[line].reviewed", true)
    .filterArray(
        Criteria.where("line.qty").gte(3)
    );

template.updateFirst(
    Query.query(Criteria.where("id").is("o601")),
    filtered,
    OrderDocument.class
);
// Chỉ dòng B (qty:4) của o601 được đánh dấu.
~~~

**Bẫy mapping:** tài liệu `Update.filterArray(...)` của Spring Data quy định `CriteriaDefinition`/expression trong `arrayFilters` được **đưa thẳng xuống driver, không ánh xạ lại tên field**. Vì vậy viết `line.qty` là đúng tên BSON; `line.quantity` là property Java nhưng **không được tự dịch** trong `arrayFilters`.

Ở chiều ngược lại, đường dẫn `set("lineItems.$[line].reviewed",...)` được ánh xạ theo metadata entity ở phần được Spring Data hỗ trợ. Khi tên Java/BSON khác nhau trong array lồng nhau, nên có integration test xác minh BSON thực để tránh tạo field sai.

## 9. Lỗi khi mảng thiếu, null hoặc sai kiểu

`$[]` được thiết kế để cập nhật **mảng đã tồn tại**. Không nên cho rằng nó sẽ tự tạo `[]` cho trường chưa có:

~~~javascript
// o605 không có scores.
orders.updateOne(
  { _id: "o605" },
  { $inc: { "scores.$[]": 5 } }
);
// Có thể lỗi vì path scores không tồn tại / không phải array.
~~~

Tương tự, với document:

~~~javascript
{ _id: "legacy-001", scores: null }
{ _id: "legacy-002", scores: "70,80" }
~~~

`scores` không phải mảng số hợp lệ; cập nhật positional có thể thất bại do kiểu/path. Không lấy giá trị Java `null` làm bằng chứng rằng BSON là mảng rỗng: **missing**, BSON `null` và `[]` khác nhau.

### 9.1. Chuẩn hóa missing thành mảng rỗng trước

~~~javascript
// Chỉ áp dụng cho document không có trường scores.
orders.updateMany(
  { scores: { $exists: false } },
  { $set: { scores: [] } }
);
~~~

Nếu nghiệp vụ cho phép BSON null và muốn chuyển null thành mảng rỗng:

~~~javascript
orders.updateMany(
  { scores: { $type: "null" } },
  { $set: { scores: [] } }
);
~~~

Hai câu lệnh có **bộ lọc khác nhau**, tránh ghi đè nhầm một mảng đã có giá trị. Sau khi chuẩn hóa, `$[]` trên `[]` không sửa phần tử nào; nếu muốn gán điểm mặc định, cần policy tạo phần tử/mảng rõ ràng, không chỉ dùng positional update.

### 9.2. Giới hạn update vào document có array

~~~javascript
orders.updateMany(
  {
    tenant_id: "t01",
    state: "OPEN",
    scores: { $type: "array" }
  },
  { $inc: { "scores.$[]": 5 } }
);
~~~

Điều kiện `$type: "array"` giúp loại trường missing/null/scalar ở cấp đang kiểm tra, nhưng **không xác minh tất cả phần tử bên trong đều là số**. Nếu trong mảng có chuỗi, object hoặc null thì `$inc` trên phần tử đó vẫn có thể lỗi. Dùng schema validation và quy trình kiểm kê dữ liệu khi yêu cầu toàn vẹn kiểu dữ liệu nghiêm ngặt.

### 9.3. Không dùng bộ lọc rộng như một hình thức bỏ qua lỗi

~~~javascript
orders.updateMany(
  { tenant_id: "t01" },
  { $inc: { "scores.$[]": 5 } }
);
~~~

Query rộng có thể chọn cả `o605` thiếu `scores` và `o603` chứa array rỗng. Trên tập dữ liệu hỗn hợp, thao tác có thể gặp lỗi giữa lúc cập nhật nhiều document. **Update nhiều document không tự có transaction cho cả tập**: một lỗi không bảo đảm mọi cập nhật trước đó sẽ rollback.

Vì vậy cần xác minh schema, thu hẹp query và triển khai transaction/retry khi nghiệp vụ yêu cầu.

## 10. `upsert` và ngoại lệ quan trọng của `$[]`

Trong MongoDB, `upsert` nghĩa là update nếu tìm thấy, hoặc insert document mới nếu không tìm thấy. Với `$[]`, **nhánh insert** có một điều kiện đặc biệt:

> Nếu upsert dẫn tới insert, query phải chứa **phép so sánh bằng chính xác trên trường array được dùng bởi `$[]`**.

### 10.1. Ví dụ hợp lệ: equality trên toàn array

Chạy trên **collection phụ** chỉ dành cho thử nghiệm:

~~~javascript
const arrays = db.array_upsert_demo_006;

arrays.updateOne(
  { values: [2, 4] },
  { $set: { "values.$[]": 0 } },
  { upsert: true }
);
// Nếu chưa có document phù hợp, có thể chèn:
// { _id: ObjectId(...), values: [0, 0] }
~~~

Điều kiện `{ values: [2, 4] }` là **exact equality match** trên trường mảng. MongoDB có đủ cấu trúc mảng để áp `$[]` trong nhánh tạo mới. Chú ý: chạy lại cùng lệnh có thể tạo thêm document vì `values` đã biến thành `[0,0]` và không còn khớp `[2,4]`; ví dụ này minh họa quy tắc của operator, **không phải công thức upsert idempotent cho nghiệp vụ**.

### 10.2. Ví dụ lỗi khi không có array equality

~~~javascript
arrays.updateOne(
  { _id: "new-order-without-array" },
  { $set: { "values.$[]": 0 } },
  { upsert: true }
);
// Nếu _id chưa tồn tại: nhánh insert không có mảng values
// để áp $[]; MongoDB trả lỗi.
~~~

Đừng tin rằng `upsert:true` sẽ tự tạo một mảng rỗng rồi chạy `$[]`. Khi cần tạo document mới với array ban đầu và cập nhật các document cũ, hãy **tách hai đường ghi** hoặc thiết kế upsert theo đúng hợp đồng dữ liệu.

### 10.3. Spring Data fluent `upsert()` không bỏ giới hạn của MongoDB

~~~java
template.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o699"))
    .apply(new Update().set("lineItems.$[].reviewed", true))
    .upsert();
// Nếu o699 chưa tồn tại, có thể lỗi vì thiếu equality trên array.
~~~

Fluent API chỉ thay đổi cách diễn đạt lệnh update; **không** thay đổi yêu cầu của server đối với `$[]` trong nhánh upsert. Trong thực tế, nếu chưa có document, hãy tạo mảng đúng cấu trúc khi insert, sau đó mới dùng all positional update ở những thao tác tiếp theo.

## 11. Số document đã sửa khác số phần tử đã sửa

Ví dụ:

~~~javascript
const result = orders.updateMany(
  {
    tenant_id: "t01",
    state: "OPEN",
    scores: { $type: "array" }
  },
  { $inc: { "scores.$[]": 5 } }
);
~~~

Với dữ liệu ban đầu:

- `o601` có 3 score được tăng.
- `o602` có 2 score được tăng.
- **Tổng cộng 5 phần tử** được thay đổi.
- `matchedCount` là **2 document** và `modifiedCount` là **2 document** (nếu được xác nhận, không có ghi đồng thời, không có hiệu ứng khác).

Khi đọc `UpdateResult` trong Java:

~~~java
UpdateResult result = template.updateMulti(
    Query.query(Criteria.where("tenantId").is("t01")
        .and("state").is("OPEN")
        .and("scores").type(4)),
    new Update().inc("scores.$[]", 5),
    OrderDocument.class
);

if (!result.wasAcknowledged()) {
    throw new IllegalStateException("Update was not acknowledged");
}

long matchedDocuments = result.getMatchedCount();
long modifiedDocuments = result.getModifiedCount();
~~~

**Không có `result.getModifiedArrayElementCount()`** trong API update thông thường. Nếu nghiệp vụ cần thống kê số phần tử đã sửa, có thể đếm điều kiện/độ dài mảng trước/sau trong một quy trình kiểm chứng, nhưng cần tính tới concurrent writes và chi phí truy vấn; không lấy `modifiedCount` làm số phần tử.

### 11.1. Một document khớp nhưng không có thay đổi

Nếu `scores: []` mà query vẫn chọn document đó, `$[]` không có phần tử để cập nhật. Một lệnh raw MongoDB có thể trả `matchedCount=1` và `modifiedCount=0`. Nếu update `$set` gán lại giá trị cũ, cũng có thể không tạo thay đổi BSON.

Đối với Spring Data entity có `@Version`, có thể có update version tự động, làm `modifiedCount` tăng dù mảng không có phần tử được sửa. Luôn xác định **toàn bộ update thực sự gửi đến server** khi giải thích các số đếm.

## 12. `@Version`, cập nhật đồng thời và idempotency

### 12.1. Auto-increment version khác với kiểm tra version kỳ vọng

Nếu entity thêm:

~~~java
@Version
private Long version;
~~~

thì với một số thao tác mapped update của Spring Data MongoDB, version có thể được tăng tự động khi chưa được chỉ định trong `Update`. Nhưng **không vì thế mà query tự biết phiên bản người dùng đã đọc**.

Khi cần ngăn một client cũ cập nhật toàn bộ mảng sau khi writer khác thay đổi đơn hàng:

~~~java
Query query = Query.query(
    Criteria.where("id").is("o601")
        .and("version").is(3L)
);

Update update = new Update()
    .set("lineItems.$[].reviewed", true);

UpdateResult result = template.updateFirst(
    query, update, VersionedOrderDocument.class
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException("Stale order version or missing order");
}
~~~

Ở đây `VersionedOrderDocument` là **biến thể entity có `@Version` và mapping cùng collection**, không phải class đã được khai báo trong mục 8.1. Đây là mã minh họa ý tưởng optimistic locking, cần triển khai variant/model cụ thể khi sử dụng; không chạy nguyên xi trên fixture chưa có version.

### 12.2. `$set` gần idempotent, `$inc` thì không

~~~javascript
{ $set: { "line_items.$[].reviewed": true } }
// Chạy nhiều lần: trạng thái reviewed vẫn là true,
// nếu không có side effect/version khác.

{ $inc: { "scores.$[]": 5 } }
// Chạy hai lần: mỗi phần tử tăng tổng cộng 10.
~~~

Khi request timeout sau khi gửi lệnh, không biết chắc lần đầu đã commit hay chưa. **Retry mù** một phép `$inc` có thể cộng điểm hai lần. Cần thiết kế điều kiện trạng thái, idempotency key, event marker hoặc checkpoint phù hợp với nghiệp vụ.

### 12.3. Xung đột ghi vào cùng một document

Một update sử dụng nhiều operator trên **một document** được MongoDB thực hiện nguyên tử ở cấp document. Nhưng hai request cùng sửa các trường của một order có thể cạnh tranh, tùy điều kiện filter/phiên bản mà request sau có thể ghi tiếp trên trạng thái đã được thay đổi.

Khi thao tác `$[]` có khả năng đổi rất nhiều phần tử cùng lúc, nên kiểm tra:

- Client có được phép sửa **toàn bộ mảng** không?
- Có yêu cầu ràng buộc `state`/`tenant`/`version` không?
- Sau khi update, dữ liệu còn thỏa schema validation và quy tắc nghiệp vụ không?
- Có writer khác đang append/remove các phần tử mảng không?

## 13. Transaction và cập nhật nhiều document

`updateOne` với `$[]` có thể cập nhật nhiều phần tử nhưng tất cả thuộc **một document**, nên thao tác đơn document có tính nguyên tử. `updateMany` có `$[]` cập nhật nhiều document, nhưng không bảo đảm cả tập là một transaction nguyên tử.

~~~javascript
orders.updateMany(
  { tenant_id: "t01", state: "OPEN", line_items: { $type: "array" } },
  { $set: { "line_items.$[].reviewed": true } }
);
~~~

Với nhiều document khớp, mỗi document được cập nhật nguyên tử riêng. Nếu lỗi xảy ra giữa thao tác, có thể tồn tại document đã thay đổi và document chưa thay đổi. Dữ liệu không đồng nhất có thể khiến job dừng giữa chừng.

Khi **all-or-nothing** trên nhiều document là yêu cầu bắt buộc, cân nhắc MongoDB multi-document transactions và `MongoTransactionManager` (hoặc `ReactiveMongoTransactionManager` trong reactive) với topology hỗ trợ. Transaction có chi phí và giới hạn; các job update mảng rất lớn có thể thích hợp hơn với chia batch, idempotency và theo dõi tiến độ.

### 13.1. Không gom mọi thứ vào một transaction khổng lồ

Một document MongoDB có giới hạn kích thước BSON, và mảng lớn làm phép cập nhật trên document nặng hơn. Ngoài kích thước, cần cân nhắc:

- Thời gian giữ transaction và tài nguyên của server.
- Lượng dữ liệu/log cần ghi và replication.
- Write conflict với các request khác sửa cùng document.
- Retry sau lỗi và khả năng quan sát các lô đã xử lý.

Với hàng triệu document, một job có batch và checkpoint thường thực tế hơn một transaction duy nhất kéo dài.

## 14. Hiệu năng: lọc document trước, nhưng `$[]` vẫn sửa tất cả phần tử

Index giúp **tìm document mục tiêu**, không thay đổi phạm vi `$[]` bên trong mảng.

Ví dụ tạo index:

~~~javascript
orders.createIndex({ tenant_id: 1, state: 1 });
orders.createIndex({ "line_items.sku": 1 });
~~~

Index thứ nhất hỗ trợ bộ lọc tenant/trạng thái. Index thứ hai là **multikey index** giúp lọc document theo SKU khi cần. Nhưng query:

~~~javascript
orders.updateMany(
  { "line_items.sku": "A", tenant_id: "t01" },
  { $set: { "line_items.$[].reviewed": true } }
);
~~~

vẫn sửa **tất cả dòng hàng**, không chỉ A. Index `line_items.sku` không tự đổi `$[]` thành `$[line]`. Nếu cần chỉ A, dùng array filter.

### 14.1. Chi phí lớn ngay cả khi chỉ sửa một document

Một document có 50.000 phần tử trong mảng khiến `$[]` phải tác động tới rất nhiều giá trị bên trong cùng document. Số `modifiedCount = 1` không cho biết chi phí ít. Đối với mảng lớn:

- Đo kích thước document, độ trễ thao tác và độ dài mảng.
- Kiểm tra index nào chứa field bị sửa, vì update có thể phải bảo trì index.
- Xem tần suất ghi đồng thời lên một document rất lớn.
- Cân nhắc tách phần tử thành collection riêng nếu phần tử cần vòng đời, cập nhật và phân trang độc lập.

### 14.2. Kiểm chứng bằng truy vấn và log

`explain("executionStats")` trên **query find cùng filter** giúp đánh giá khả năng tìm document (index scan so với collection scan), nhưng không đo đầy đủ chi phí cập nhật hàng nghìn phần tử. Theo dõi cả `matchedCount`, `modifiedCount`, p95/p99 latency, bytes ghi, replication và write conflicts trên môi trường thử nghiệm.

Không tối ưu bằng cách bỏ điều kiện tenant/authorization chỉ để query “nhanh hơn”; `updateMany` không có filter đúng có thể sửa dữ liệu ngoài quyền truy cập.

## 15. Không dùng `$[]` khi mục tiêu là biến đổi cả mảng theo biểu thức phức tạp

`$[]` phù hợp với việc áp **một operator nhất quán** cho mọi phần tử hoặc một trường con của mỗi phần tử, ví dụ:

~~~javascript
{ $inc: { "scores.$[]": 5 } }
{ $set: { "line_items.$[].reviewed": true } }
~~~

Nếu cần biến đổi phần tử theo **nhiều điều kiện**, dùng `$[identifier]` nếu điều kiện diễn đạt được qua `arrayFilters`. Nếu cần tính lại cả cấu trúc mảng theo biểu thức (ví dụ tạo mảng mới, chuyển đổi kiểu, chọn giá trị phụ thuộc nhiều trường), cân nhắc **aggregation pipeline update** với `$map`, `$cond`, `$ifNull` và các expression được server cho phép.

Ví dụ đánh dấu `reviewed` chỉ cho các dòng có `qty >= 3`, đồng thời giữ nguyên các field khác:

~~~javascript
orders.updateOne(
  { _id: "o601" },
  [
    {
      $set: {
        line_items: {
          $map: {
            input: "$line_items",
            as: "item",
            in: {
              $mergeObjects: [
                "$$item",
                {
                  reviewed: {
                    $cond: [
                      { $gte: ["$$item.qty", 3] },
                      true,
                      "$$item.reviewed"
                    ]
                  }
                }
              ]
            }
          }
        }
      }
    }
  ]
);
// Với o601: dòng B (qty:4) true, dòng A (qty:2) giữ false.
~~~

Đây là **pipeline update**, không phải `$[]`. Nó dựng một mảng kết quả từ các phần tử ban đầu. Phải kiểm tra đầu vào `line_items` thực sự là array; nếu missing/null, có thể cần `$ifNull` để chuẩn hóa. Không kèm `arrayFilters` vào pipeline này.

Ở Spring Data MongoDB có `AggregationUpdate` để xây pipeline update. Với yêu cầu đơn giản “chỉ sửa những dòng qty >= 3”, cách `$[line]` thường ngắn, rõ nghĩa và dễ duy trì hơn.

## 16. ReactiveMongoTemplate: toán tử không thay đổi

Reactive access không thay đổi ngữ nghĩa BSON của `$[]`. Ví dụ:

~~~java
import com.mongodb.client.result.UpdateResult;
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Update;

// reactiveTemplate là ReactiveMongoTemplate đã inject:
Mono<UpdateResult> updateAllScores =
    reactiveTemplate.update(OrderDocument.class)
        .matching(Criteria.where("tenantId").is("t01")
            .and("state").is("OPEN")
            .and("scores").type(4))
        .apply(new Update().inc("scores.$[]", 5))
        .all();
~~~

Đây là một `Mono<UpdateResult>`, thao tác chỉ chạy khi có subscriber. Không gọi `block()` trong event loop của WebFlux. Khi cần retry, chú ý một publisher được subscribe lại có thể kích hoạt **lần update tiếp theo**, nên `$inc` dễ bị nhân đôi tác động nếu không có bảo đảm idempotency.

Reactive `first()` chỉ cập nhật một document; reactive `all()` cập nhật nhiều document. Cả hai vẫn cập nhật **mọi phần tử** của mảng trong mỗi document được chọn theo đường dẫn `$[]`.

## 17. Integration test: xác nhận từng phần tử đã thay đổi

Mock `MongoTemplate` không chứng minh được MongoDB hiểu `$[]` đúng, không kiểm tra được ánh xạ `lineItems → line_items` và không phát hiện trường hợp dữ liệu sai kiểu. Hãy dùng MongoDB test instance riêng hoặc Testcontainers.

### 17.1. Ma trận kiểm thử nên có

| Trường hợp | Kết quả mong muốn |
| --- | --- |
| Mảng số có 3 phần tử | `$inc` tăng cả 3 phần tử |
| Mảng object A/B | `$set line_items.$[].reviewed` sửa cả A/B |
| Query có `line_items.sku=A` | Với `$[]`, dòng B vẫn bị sửa |
| `$[line]` + `arrayFilters` | Chỉ dòng được filter khớp thay đổi |
| Mảng rỗng | Không thêm phần tử mới |
| Array missing/null | Có lỗi hoặc cần chuẩn hóa theo schema; không tự tạo array |
| Mảng lồng nhau | Hai `$[]` sửa đúng mọi package của mọi shipment |
| Nested `$[]` + filtered identifier | Chỉ package đáp ứng filter thay đổi |
| `updateMulti` trên nhiều document | Kiểm tra số document, không nhầm số phần tử |
| `upsert` thiếu array equality | Nhánh insert thất bại đúng như kỳ vọng |
| `@Field("line_items")` và `@Field("qty")` | Ánh xạ đúng đường dẫn Java/BSON |
| `@Version` | Kiểm tra auto-version, condition version và hậu quả retry |

### 17.2. Test trực tiếp với `MongoTemplate` và BSON thô

Ví dụ dưới dùng **database test độc lập**. Nó tạo fixture riêng, cập nhật tất cả phần tử bằng `$[]` và xác minh bằng MongoDB Java Driver:

~~~java
package com.example.arrayops;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.model.Filters;

@DataMongoTest
class AllPositionalOperatorTest {
    @Autowired MongoTemplate template;

    @Test
    void updatesEveryArrayElementAndMapsAliases() {
        String id = "fixture-array-006";
        var collection = template.getDb()
            .getCollection("orders_array_demo_006");

        collection.deleteOne(Filters.eq("_id", id));
        try {
            collection.insertOne(new Document("_id", id)
                .append("tenant_id", "fixture-tenant")
                .append("state", "OPEN")
                .append("scores", List.of(10, 20, 30))
                .append("line_items", List.of(
                    new Document("sku", "A")
                        .append("qty", 2)
                        .append("reviewed", false),
                    new Document("sku", "B")
                        .append("qty", 4)
                        .append("reviewed", false)
                )));

            var scored = template.updateFirst(
                Query.query(Criteria.where("id").is(id)),
                new Update().inc("scores.$[]", 5),
                OrderDocument.class
            );
            assertThat(scored.getMatchedCount()).isEqualTo(1L);

            var reviewed = template.update(OrderDocument.class)
                .matching(Criteria.where("id").is(id))
                .apply(new Update()
                    .set("lineItems.$[].reviewed", true))
                .first();
            assertThat(reviewed.getMatchedCount()).isEqualTo(1L);

            Document raw = collection.find(
                Filters.eq("_id", id)
            ).first();
            assertThat(raw).isNotNull();
            assertThat(raw.getList("scores", Integer.class))
                .containsExactly(15, 25, 35);

            List<Document> lines =
                raw.getList("line_items", Document.class);
            assertThat(lines).hasSize(2);
            assertThat(lines.get(0).getBoolean("reviewed")).isTrue();
            assertThat(lines.get(1).getBoolean("reviewed")).isTrue();
            assertThat(raw.containsKey("lineItems")).isFalse();
        } finally {
            collection.deleteOne(Filters.eq("_id", id));
        }
    }
}
~~~

Ví dụ này giả định `@DataMongoTest` cấu hình MongoDB test có kết nối hợp lệ; tùy dự án có thể dùng Testcontainers để tạo database test riêng. Không chạy trên production hay database dùng chung: setup/cleanup có xóa đúng ID fixture của test.

### 17.3. Test riêng lỗi “query khớp A nhưng B cũng được sửa”

Trên hai dòng A/B trong fixture, kiểm tra hai nhánh **độc lập**:

~~~java
// Nhánh 1 — với $[]:
template.updateFirst(
    Query.query(Criteria.where("id").is(id)
        .and("lineItems.sku").is("A")),
    new Update().set("lineItems.$[].reviewed", true),
    OrderDocument.class
);
// Cả A và B có reviewed=true.
~~~

~~~java
// Nhánh 2 — reset fixture rồi dùng filtered positional:
template.updateFirst(
    Query.query(Criteria.where("id").is(id)),
    new Update()
        .set("lineItems.$[line].reviewed", true)
        .filterArray(Criteria.where("line.sku").is("A")),
    OrderDocument.class
);
// A=true, B=false.
~~~

`id` là biến fixture của test, như ở mục 17.2. Đừng chạy liên tiếp hai nhánh mà không reset `reviewed`, vì kết quả của nhánh 1 sẽ che lấp sự khác biệt của nhánh 2. Đây là bài kiểm thử quan trọng nhất để phát hiện nhầm lẫn giữa **lọc document** và **lọc phần tử mảng**.

## 18. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query chọn SKU A nhưng SKU B cũng bị sửa | `$[]` cập nhật mọi phần tử trong document khớp | Dùng `$[line]` + `arrayFilters` nếu chỉ muốn A |
| Chỉ một phần tử được cập nhật | Đã dùng `$` thay vì `$[]` | Chọn operator theo phạm vi cần sửa |
| `matchedCount=1` nhưng mảng không đổi | Mảng rỗng, update cùng giá trị cũ, hoặc điều kiện không dẫn đến sửa | Xem BSON trước/sau và `modifiedCount` |
| `modifiedCount=1` dù sửa 500 phần tử | Count là số **document** | Tách chỉ số phần tử ra khỏi `UpdateResult` |
| Lỗi “path must exist” | Trường array missing/null/sai kiểu hoặc upsert insert thiếu array equality | Chuẩn hóa dữ liệu, lọc đúng array; xem quy tắc upsert |
| Dùng `scores.$[]` với phần tử string gặp lỗi | `$inc` yêu cầu phần tử số | Kiểm tra type/schema, sửa dữ liệu trước |
| Nested path lỗi với document legacy | Có shipment không có `packages` hay phần tử sai kiểu | Chuẩn hóa schema, dùng filter/cập nhật riêng |
| `filterArray("line.quantity", ...)` không khớp | `arrayFilters` không tự map Java field alias | Dùng tên BSON `line.qty` |
| `Update.set("lineItems.$[].reviewed")` sửa sai đường dẫn | Thiếu entity metadata hoặc sai tên collection/property | Dùng overload theo entity và kiểm BSON |
| Update nhiều document chỉ sửa một phần rồi lỗi | `updateMany` không tự có transaction toàn tập | Xử lý schema trước, transaction hoặc job batch có retry |
| Upsert tạo trùng document | Exact array equality bị thay đổi sau update hoặc không có unique key | Không dùng ví dụ `$[]` upsert làm idempotent upsert nghiệp vụ |
| Giá trị tăng hai lần sau retry | `$inc` không idempotent | Dùng điều kiện/idempotency key hoặc kiểm tra kết quả |
| Biến thể reactive không chạy | Chưa subscribe `Mono` | Compose vào reactive chain; kiểm thử bằng `StepVerifier` |
| Update rất chậm khi array lớn | Phải sửa nhiều phần tử và bảo trì index trong một document | Đo latency, giới hạn kích thước array, cân nhắc mô hình tách collection |

## 19. Checklist trước khi dùng `$[]`

1. Xác nhận nghiệp vụ thực sự muốn sửa **mọi phần tử** hay chỉ phần tử được chọn.
2. Chọn **document filter** đúng ID, tenant, state và quyền truy cập.
3. Đảm bảo trường là **BSON array** ở tất cả document có thể được chọn; xử lý missing/null/legacy trước.
4. Xác nhận kiểu mỗi phần tử phù hợp operator (`$inc` yêu cầu số).
5. Với embedded object, cập nhật **field con** thay vì thay cả object.
6. Với nhiều cấp array, chỉ rõ cấp nào dùng `$[]` và cấp nào dùng `$[identifier]`.
7. Khi dùng Spring Data, kiểm tra ánh xạ property Java/BSON; nhớ `arrayFilters` không được tự map lại.
8. Không dùng `$[]` trong nhánh insert của upsert nếu chưa đáp ứng exact array equality.
9. Kiểm tra `UpdateResult` là số **document**, không phải phần tử.
10. Đánh giá version, idempotency, transaction, index và kích thước mảng.
11. Kiểm thử cả trường hợp mảng rỗng, missing, nhiều phần tử và query khớp một phần tử.

## 20. Bài thực hành

Mỗi bài giả định fixture nguyên bản từ mục 2; chạy độc lập, không nối tiếp các cập nhật nếu không tự reset dữ liệu test.

### Bài 1 — Mảng số

`o601.scores = [70,80,90]`. Viết một lệnh tăng **mọi phần tử** thêm 3.

**Đáp án:**

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $inc: { "scores.$[]": 3 } }
);
// [73, 83, 93]
~~~

### Bài 2 — Tìm lỗi logic

Một lập trình viên viết:

~~~javascript
orders.updateOne(
  { _id: "o601", "line_items.sku": "A" },
  { $set: { "line_items.$[].reviewed": true } }
);
~~~

Câu hỏi: Dòng B có thay đổi không? **Có.** Query chỉ yêu cầu order có một dòng A; `$[]` vẫn cập nhật cả A và B. Muốn chỉ A, dùng `$[line]` kèm `arrayFilters`, hoặc `$` khi chỉ muốn một phần tử đầu tiên.

### Bài 3 — Sửa mọi dòng A

Yêu cầu: cập nhật `reviewed = true` cho **mọi dòng SKU A**, không sửa B/C.

**Đáp án:**

~~~javascript
orders.updateMany(
  { tenant_id: "t01", line_items: { $type: "array" } },
  { $set: { "line_items.$[line].reviewed": true } },
  { arrayFilters: [{ "line.sku": "A" }] }
);
~~~

### Bài 4 — Mảng lồng nhau

Trong `o601`, đánh dấu scanned=true cho mọi package của **mọi shipment**, bất kể warehouse/SKU.

**Đáp án:**

~~~javascript
orders.updateOne(
  { _id: "o601" },
  { $set: { "shipments.$[].packages.$[].scanned": true } }
);
~~~

Nếu chỉ muốn package A ở mọi kho, đổi `packages.$[]` thành `packages.$[pkg]` với `arrayFilters:[{"pkg.sku":"A"}]`.

### Bài 5 — Phân biệt số document và số phần tử

Với fixture gốc, dùng `updateMany` trên `t01/OPEN` có `scores` là array, tăng mọi score thêm 5. Hỏi `matchedCount`, `modifiedCount` và số score thay đổi.

**Đáp án:** `matchedCount=2`, `modifiedCount=2` và **5 score** thay đổi (3 ở o601 + 2 ở o602), giả sử không có writer đồng thời/side effect khác và được server xác nhận.

### Bài 6 — Missing array và upsert

`o605` thiếu `scores`. Có nên kỳ vọng `{ $set: { "scores.$[]": 0 } }` tự tạo mảng không? Nếu một upsert insert dùng `$[]`, filter cần có gì?

**Đáp án:** Không; `$[]` cần đường dẫn array có thể áp dụng. Nếu upsert tạo mới, filter phải có **exact equality** trên trường array đó. Trong nghiệp vụ thông thường nên khởi tạo array bằng thao tác insert/set đúng schema rồi cập nhật.

### Bài 7 — Spring Data field alias

Java có `OrderDocument.lineItems` được lưu thành `line_items`, còn `OrderLine.quantity` được lưu thành `qty`. Hãy viết:

1. Update tất cả dòng đặt `reviewed=true`.
2. Update chỉ các dòng có `qty >= 3`.

**Đáp án:**

~~~java
new Update().set("lineItems.$[].reviewed", true);

new Update()
    .set("lineItems.$[line].reviewed", true)
    .filterArray(Criteria.where("line.qty").gte(3));
~~~

`line.qty` trong `arrayFilters` phải dùng **tên BSON**, vì Spring Data không tự ánh xạ phần filter này.

### Bài 8 — Retry không an toàn

Một request tăng mọi score bằng `$inc` đã gửi tới server nhưng mất kết nối trước khi nhận phản hồi. Có nên gửi lại ngay cùng thao tác?

**Đáp án:** Không retry mù. Lần đầu có thể đã thành công; gửi lại sẽ tăng lần thứ hai. Thiết kế idempotency key, điều kiện trạng thái hoặc cơ chế xác minh/đối soát theo nghiệp vụ.

## Tài liệu tham khảo

- [MongoDB Manual — `$[]` All Positional Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-all/): cú pháp, phạm vi, mảng lồng nhau, quy tắc upsert exact array equality.
- [MongoDB Manual — `$` Positional Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional/): phần tử đầu tiên khớp, giới hạn của positional `$`.
- [MongoDB Manual — `$[identifier]` Filtered Positional Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/): `arrayFilters` và lọc từng phần tử.
- [MongoDB Manual — Update Operators](https://www.mongodb.com/docs/manual/reference/mql/update/): phân biệt `$set`, `$inc`, `$pull` và positional operators.
- [MongoDB Manual — `updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updatemany/): tùy chọn `arrayFilters`, kết quả cập nhật và tính nguyên tử.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `MongoTemplate`, `Update`, fluent update và version.
- [Spring Data MongoDB — `Update` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Update.html): `set`, `inc`, `filterArray` và ghi chú không mapping array filter.
- [Spring Data MongoDB — `MongoOperations` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html): `updateFirst`/`updateMulti` và fluent equivalents.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): atomicity mức document và giới hạn update nhiều document.
