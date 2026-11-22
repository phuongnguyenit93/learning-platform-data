# Truy vấn collection, document nhúng và giới hạn đối sánh phần tử

> **Chương:** Truy vấn suy diễn  
> **Module:** `SPRING_DATA_MONGODB` — ánh xạ document, truy vấn MongoDB bằng repository hoặc `MongoTemplate`, đồng thời thực hành kiểm thử và chẩn đoán hiệu năng.  
> **Mục tiêu:** Viết derived query trên thuộc tính của document nhúng và mảng; hiểu cách MongoDB đối sánh từng phần tử; nhận biết tình huống `And` không có nghĩa “cùng phần tử”; chuyển sang `$elemMatch`, `@Query` hoặc `MongoTemplate` khi cần điều kiện chính xác.

## 1. Truy vấn suy diễn hoạt động ở mức nào?

Spring Data MongoDB có thể tạo truy vấn từ tên phương thức repository, chẳng hạn:

~~~java
List<OrderDocument> findByState(String state);
List<OrderDocument> findByShippingAddressCity(String city);
List<OrderDocument> findByLinesSku(String sku);
~~~

Spring Data phân tích phần sau `By` thành **đường dẫn thuộc tính Java** và các toán tử (`And`, `GreaterThan`, `In`, …), sau đó ánh xạ thành truy vấn BSON cho **collection MongoDB** của entity. Ví dụ:

| Phương thức repository | Điều kiện MongoDB tương ứng về ý nghĩa |
| --- | --- |
| `findByState("OPEN")` | `{ state: "OPEN" }` |
| `findByShippingAddressCity("Hà Nội")` | `{ "shippingAddress.city": "Hà Nội" }` |
| `findByLinesSku("A")` | `{ "lines.sku": "A" }` |
| `findByLinesQuantityGreaterThan(5)` | `{ "lines.quantity": { $gt: 5 } }` |

Một repository `MongoRepository<OrderDocument, String>` làm việc với **collection** khai báo bằng `@Document(collection = "...")`, không tự tạo join với collection khác chỉ vì tên phương thức đi qua một thuộc tính tham chiếu. Ở bài này, từ **collection** còn chỉ trường Java `List`/mảng được lưu dưới dạng **BSON array**. Cần phân biệt rõ hai nghĩa:

- **MongoDB collection**: tập document cùng tên, ví dụ `orders_derived_demo_008`.
- **Collection-valued property**: trường như `List<OrderLine> lines` hoặc `List<String> tags` nằm *bên trong* một document.

Derived query trả về **document gốc** thỏa điều kiện. Nếu truy vấn khớp một phần tử của `lines`, kết quả thông thường vẫn là một `OrderDocument` với toàn bộ `lines`, trừ khi bạn cấu hình projection/aggregation riêng.

## 2. Bộ dữ liệu dùng xuyên suốt bài

Trong `mongosh`, tạo dữ liệu trên **database thử nghiệm độc lập**. Các ID cố định chỉ phục vụ minh họa; không chạy lại `insertMany` trên cùng collection nếu dữ liệu vẫn còn.

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_derived_demo_008;

orders.insertMany([
  {
    _id: "o001",
    state: "OPEN",
    shippingAddress: { city: "Hà Nội", district: "Cầu Giấy" },
    tags: ["online", "priority"],
    lines: [
      { sku: "A", quantity: 1, unitPriceVnd: 120000 },
      { sku: "B", quantity: 8, unitPriceVnd: 20000 }
    ],
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "o002",
    state: "OPEN",
    shippingAddress: { city: "Hồ Chí Minh", district: "Quận 1" },
    tags: ["online"],
    lines: [
      { sku: "A", quantity: 6, unitPriceVnd: 120000 },
      { sku: "C", quantity: 1, unitPriceVnd: 45000 }
    ],
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "o003",
    state: "PAID",
    shippingAddress: { city: "Hà Nội", district: "Ba Đình" },
    tags: ["store"],
    lines: [
      { sku: "B", quantity: 7, unitPriceVnd: 20000 }
    ],
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "o004",
    state: "DRAFT",
    shippingAddress: { city: "Đà Nẵng", district: "Hải Châu" },
    tags: [],
    lines: [],
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "o005",
    state: "OPEN",
    shippingAddress: { city: "Hà Nội", district: "Đống Đa" },
    tags: ["priority"],
    lines: [
      { sku: "A", quantity: 3, unitPriceVnd: 120000 },
      { sku: "A", quantity: 9, unitPriceVnd: 120000 }
    ],
    createdAt: ISODate("2026-10-05T08:00:00Z")
  }
]);

orders.find({}, { _id: 1, state: 1, lines: 1 }).sort({ _id: 1 });
~~~

Ý nghĩa của bộ dữ liệu:

| Order | Thành phố | Dòng hàng | Điểm dùng để kiểm chứng |
| --- | --- | --- | --- |
| `o001` | Hà Nội | A × 1; B × 8 | Có A và có dòng số lượng lớn, **nhưng không có A với số lượng lớn** |
| `o002` | Hồ Chí Minh | A × 6; C × 1 | Có A với số lượng lớn ngay trên một dòng |
| `o003` | Hà Nội | B × 7 | Không chứa A |
| `o004` | Đà Nẵng | Không có dòng hàng | Mảng rỗng |
| `o005` | Hà Nội | A × 3; A × 9 | Có hai dòng A, một dòng đạt ngưỡng |

Các truy vấn dưới đây dùng dữ liệu ban đầu này. Nếu thay đổi collection khi thực hành, hãy tự tính lại kết quả kỳ vọng.

## 3. Ánh xạ document nhúng bằng Spring Data MongoDB

Một order chứa **một object nhúng** `shippingAddress` và **mảng object nhúng** `lines`. Đối với MongoDB, đây là hai cấu trúc khác nhau:

~~~text
OrderDocument
├── _id: "o001"
├── shippingAddress: { city, district }     ← một embedded document
├── tags: ["online", "priority"]             ← mảng scalar
└── lines: [                                  ← mảng embedded documents
      { sku: "A", quantity: 1 },
      { sku: "B", quantity: 8 }
    ]
~~~

### 3.1. Khai báo entity

Mỗi đoạn dưới đây đại diện cho một file Java trong package `com.example.derived`.

~~~java
// ShippingAddress.java
package com.example.derived;

public class ShippingAddress {
    private String city;
    private String district;

    protected ShippingAddress() {}

    public ShippingAddress(String city, String district) {
        this.city = city;
        this.district = district;
    }

    public String getCity() { return city; }
    public String getDistrict() { return district; }
}
~~~

~~~java
// OrderLine.java
package com.example.derived;

public class OrderLine {
    private String sku;
    private int quantity;
    private long unitPriceVnd;

    protected OrderLine() {}

    public OrderLine(String sku, int quantity, long unitPriceVnd) {
        this.sku = sku;
        this.quantity = quantity;
        this.unitPriceVnd = unitPriceVnd;
    }

    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
    public long getUnitPriceVnd() { return unitPriceVnd; }
}
~~~

~~~java
// OrderDocument.java
package com.example.derived;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_derived_demo_008")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    private String state;
    private ShippingAddress shippingAddress;
    private List<String> tags;
    private List<OrderLine> lines;
    private Instant createdAt;

    protected OrderDocument() {}

    public String getId() { return id; }
    public String getState() { return state; }
    public ShippingAddress getShippingAddress() { return shippingAddress; }
    public List<String> getTags() { return tags; }
    public List<OrderLine> getLines() { return lines; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

`ShippingAddress` và `OrderLine` không cần `@Document` nếu chúng chỉ được lưu **nhúng** trong order. Trường `@MongoId(FieldType.STRING)` giữ `_id` là BSON string; tránh chuyển ngầm chuỗi hex sang `ObjectId` nếu dùng `@Id String` mặc định.

### 3.2. Repository cơ bản

~~~java
// OrderRepository.java
package com.example.derived;

import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    List<OrderDocument> findByState(String state);

    List<OrderDocument> findByShippingAddressCity(String city);

    List<OrderDocument> findByLinesSku(String sku);

    List<OrderDocument> findByLinesQuantityGreaterThan(int quantity);

    List<OrderDocument> findByLinesSkuAndLinesQuantityGreaterThan(
        String sku, int quantity
    );

    List<OrderDocument> findByTags(String tag);

    Page<OrderDocument> findByState(String state, Pageable pageable);
}
~~~

Các phương thức được Spring Data **suy diễn từ tên** khi repository được tạo. Nếu tên đường dẫn Java sai (chẳng hạn `ShippingCity` khi entity chỉ có `shippingAddress.city`), ứng dụng có thể lỗi khi khởi tạo repository với thông báo về property path; lỗi này khác với việc MongoDB trả về kết quả rỗng.

## 4. Document nhúng đơn: truy vấn theo đường dẫn thuộc tính

### 4.1. Dot notation trong MongoDB

Để tìm order giao tới Hà Nội:

~~~javascript
orders.find({ "shippingAddress.city": "Hà Nội" });
// Kết quả trên dữ liệu gốc: o001, o003, o005.
~~~

Tương ứng với derived query:

~~~java
List<OrderDocument> hanoi =
    repository.findByShippingAddressCity("Hà Nội");
// Dự kiến chứa o001, o003, o005 (thứ tự chưa bảo đảm).
~~~

Spring Data tách `ShippingAddressCity` thành đường dẫn Java `shippingAddress.city`, sau đó chuyển tên trường sang đường dẫn BSON khi thực thi.

Không viết truy vấn như sau nếu muốn match một thuộc tính con:

~~~javascript
orders.find({ shippingAddress: { city: "Hà Nội" } });
~~~

Truy vấn so sánh **toàn bộ subdocument** thường yêu cầu các trường và thứ tự trường của document so sánh khớp với document được lưu. Dữ liệu mẫu còn có `district` nên điều kiện chỉ chứa `city` sẽ không chọn ba order ở trên. Sử dụng dot notation khi chỉ lọc theo một hoặc vài trường con.

### 4.2. Kết hợp tiêu chí trong subdocument và ngoài subdocument

~~~java
List<OrderDocument> findByStateAndShippingAddressCity(
    String state, String city
);
~~~

Ý nghĩa:

~~~javascript
orders.find({
  state: "OPEN",
  "shippingAddress.city": "Hà Nội"
});
// Kết quả: o001 và o005.
~~~

`And` nối các **điều kiện độc lập trên cùng order**. Vì `shippingAddress` chỉ là một object nhúng, ở đây không xuất hiện câu hỏi “hai tiêu chí có thuộc cùng phần tử của mảng không”.

### 4.3. Phân giải đường dẫn có tên mơ hồ

Spring Data Commons ưu tiên cố gắng nhận dạng property trực tiếp trước khi tách tên ở các vị trí camel case. Nếu entity có cả `shippingAddress` và `shippingAddressCity`, phương thức `findByShippingAddressCity` có thể bị hiểu là property trực tiếp `shippingAddressCity`.

Để chỉ rõ điểm tách, có thể dùng `_`:

~~~java
List<OrderDocument> findByShippingAddress_City(String city);
~~~

Dấu gạch dưới ở đây là **ký hiệu giúp parser phân tách đường dẫn Java**, không phải ký tự bắt buộc trong BSON. Nếu class không có xung đột tên thuộc tính, phương thức ngắn `findByShippingAddressCity` thường dễ đọc hơn.

Nếu dùng `@Field("shipping_address")` trên property `shippingAddress`, phần tên phương thức vẫn dựa vào **property Java**, còn converter có trách nhiệm ánh xạ đường dẫn truy vấn sang `shipping_address.city`. Khi điều tra sai kết quả, kiểm tra cả tên Java và tên BSON thực tế.

## 5. Trường kiểu Collection: truy vấn một phần tử bằng dot notation

Với `lines` là `List<OrderLine>`, truy vấn sau:

~~~javascript
orders.find({ "lines.sku": "A" });
// Kết quả: o001, o002, o005.
~~~

có nghĩa là trong mảng `lines` có **ít nhất một phần tử** có `sku: "A"`. Phương thức derived tương ứng:

~~~java
List<OrderDocument> containingSkuA =
    repository.findByLinesSku("A");
~~~

Tương tự:

~~~javascript
orders.find({ "lines.quantity": { $gt: 5 } });
// Kết quả: o001 (B×8), o002 (A×6), o003 (B×7), o005 (A×9).
~~~

~~~java
List<OrderDocument> someLineHasLargeQuantity =
    repository.findByLinesQuantityGreaterThan(5);
~~~

Điều kiện đi qua `List<OrderLine>` được ánh xạ thành đường dẫn như `"lines.sku"`. MongoDB tìm những **document có ít nhất một phần tử** đáp ứng điều kiện; repository không tự trả riêng phần tử `OrderLine` đó.

### 5.1. Mảng scalar: tìm giá trị có trong mảng

`tags` là `List<String>`, không phải mảng document:

~~~javascript
orders.find({ tags: "priority" });
// Kết quả: o001, o005.
~~~

Với equality trên trường mảng scalar, MongoDB khớp nếu **có phần tử bằng giá trị**. Một derived query:

~~~java
List<OrderDocument> priorityOrders =
    repository.findByTags("priority");
~~~

có cùng ý nghĩa đối với trường `tags` trong mô hình này. Nó khác với phép so sánh toàn bộ mảng `tags: ["priority"]`, vốn yêu cầu cả mảng có cấu trúc tương ứng.

Với `Containing`, phải đọc theo **kiểu property**: `findByNameContaining("abc")` trên `String` thường tạo tìm kiếm theo regex, còn `Containing` trên `Collection` liên quan đến phép tìm phần tử trong tập. Đừng áp đặt một cách diễn giải `Containing` cho mọi kiểu dữ liệu.

## 6. Bẫy trọng tâm: `And` có thể khớp **hai phần tử khác nhau**

Giả sử yêu cầu nghiệp vụ:

> Tìm order có **một dòng hàng SKU A với số lượng lớn hơn 5**.

Một người có thể viết:

~~~java
List<OrderDocument> findByLinesSkuAndLinesQuantityGreaterThan(
    String sku, int quantity
);
~~~

và gọi:

~~~java
var results = repository
    .findByLinesSkuAndLinesQuantityGreaterThan("A", 5);
~~~

Spring Data suy diễn điều kiện tương ứng về ý nghĩa:

~~~javascript
orders.find({
  "lines.sku": "A",
  "lines.quantity": { $gt: 5 }
});
~~~

**Điểm dễ nhầm:** MongoDB không buộc hai điều kiện dot notation này cùng khớp trên **một phần tử `lines`**. Một phần tử có thể thỏa `sku = A`, phần tử khác thỏa `quantity > 5`.

| Order | Có phần tử SKU A? | Có phần tử quantity > 5? | Derived query với `And` | Có **cùng một dòng A** quantity > 5? |
| --- | --- | --- | --- | --- |
| `o001` | Có, A × 1 | Có, B × 8 | **Có** | **Không** |
| `o002` | Có, A × 6 | Có, A × 6 | Có | Có |
| `o003` | Không | Có, B × 7 | Không | Không |
| `o004` | Không | Không | Không | Không |
| `o005` | Có, A × 3 / A × 9 | Có, A × 9 | Có | Có |

Kết quả derived query là **o001, o002, o005**. Nhưng kết quả **đúng với yêu cầu cùng một dòng** chỉ là **o002, o005**.

Sơ đồ thể hiện trường hợp `o001`:

~~~text
Order o001
lines[0] = { sku: "A", quantity: 1 }   ← thỏa lines.sku = "A"
lines[1] = { sku: "B", quantity: 8 }   ← thỏa lines.quantity > 5

Hai điều kiện đúng trên toàn order.
Không có phần tử riêng lẻ nào thỏa đồng thời cả hai.
~~~

### 6.1. `And` trong tên phương thức không phải `$elemMatch`

`And` mô tả toán tử logic giữa các **predicate của query trên document**. Nó không tự giới hạn phạm vi vào cùng index/phần tử của một mảng. Thậm chí viết lại thành:

~~~javascript
orders.find({
  $and: [
    { "lines.sku": "A" },
    { "lines.quantity": { $gt: 5 } }
  ]
});
~~~

vẫn cho kết quả có `o001`. `$and` chỉ kết hợp điều kiện; nó không cấp ngữ nghĩa “cùng phần tử”.

Vì vậy nếu cần ràng buộc nhiều trường của **một object nằm trong mảng**, hãy dùng `$elemMatch`.

## 7. Dùng `$elemMatch` để ràng buộc cùng một phần tử

### 7.1. Truy vấn chuẩn MongoDB

~~~javascript
orders.find({
  lines: {
    $elemMatch: {
      sku: "A",
      quantity: { $gt: 5 }
    }
  }
});
// Kết quả: o002 và o005. o001 bị loại.
~~~

`$elemMatch` yêu cầu có **ít nhất một phần tử của mảng `lines`** thỏa **tất cả điều kiện bên trong**. `sku` và `quantity` ở đây là thuộc tính của **một `OrderLine`**, không phải hai nhánh độc lập của toàn order.

Một lợi ích phụ: `$elemMatch` chỉ khớp **mảng**. Trong trường hợp dữ liệu bị lỗi và `lines` lỡ được lưu như một object đơn lẻ, dot notation có thể vẫn khớp `lines.sku`, nhưng `$elemMatch` sẽ không coi object đơn lẻ ấy là mảng hợp lệ.

### 7.2. Viết `@Query` trong repository

Khi derived query không diễn đạt đúng phạm vi phần tử, khai báo truy vấn BSON rõ ràng:

~~~java
package com.example.derived;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Query(
        "{ 'lines': { '$elemMatch': { " +
        "  'sku': ?0, " +
        "  'quantity': { '$gt': ?1 }" +
        "} } }"
    )
    List<OrderDocument> findHavingLineWithQuantityGreaterThan(
        String sku, int minExclusive
    );
}
~~~

Đây là **phiên bản rút gọn** của `OrderRepository` ở mục 3: trong dự án thực tế, thêm import `@Query` và phương thức mới vào **cùng interface hiện có**, không tạo hai interface trùng tên trong một package.

Sử dụng:

~~~java
List<OrderDocument> result =
    repository.findHavingLineWithQuantityGreaterThan("A", 5);
// Dự kiến o002, o005.
~~~

Trong `@Query`, `?0` và `?1` lấy tham số theo vị trí (bắt đầu từ 0). Spring Data thực hiện binding và escape giá trị chuỗi, nên không cần tự ghép giá trị user vào JSON query. Tên phương thức `findHavingLineWithQuantityGreaterThan` ở đây **không phải tiêu chí suy diễn** vì `@Query` đã khai báo nội dung MongoDB cần dùng.

Hạn chế nên ghi nhớ: `@Query` trả về **toàn bộ order** theo mapping mặc định. `$elemMatch` trong **filter** chỉ chọn order nào được trả về, **không cắt mảng `lines` thành những phần tử khớp**.

### 7.3. Viết bằng `MongoTemplate` và `Criteria.elemMatch`

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Trong service có sẵn MongoTemplate template:
Criteria oneLine = Criteria.where("sku").is("A")
    .and("quantity").gt(5);

Query query = Query.query(
    Criteria.where("lines").elemMatch(oneLine)
);

List<OrderDocument> result =
    template.find(query, OrderDocument.class);
// Dự kiến o002, o005.
~~~

`Criteria.where("lines").elemMatch(...)` biểu diễn cùng cú pháp MongoDB. Cách này hữu ích khi query được xây dựng theo nhiều filter tùy chọn, hoặc khi cần bổ sung projection, sort và pagination.

### 7.4. Kết hợp điều kiện trên order với điều kiện trên một dòng hàng

~~~javascript
orders.find({
  state: "OPEN",
  "shippingAddress.city": "Hà Nội",
  lines: {
    $elemMatch: {
      sku: "A",
      quantity: { $gt: 5 }
    }
  }
});
// Dữ liệu gốc: chỉ o005.
~~~

Tương đương qua `MongoTemplate`:

~~~java
Criteria criteria = Criteria.where("state").is("OPEN")
    .and("shippingAddress.city").is("Hà Nội")
    .and("lines")
    .elemMatch(
        Criteria.where("sku").is("A")
            .and("quantity").gt(5)
    );

List<OrderDocument> found = template.find(
    Query.query(criteria),
    OrderDocument.class
);
~~~

Ở ví dụ này, `state` và `shippingAddress.city` lọc ở cấp **order**, còn các trường `sku`/`quantity` lọc trong **một phần tử của `lines`**. Sự khác biệt về phạm vi là trọng tâm khi thiết kế query document nhúng.

## 8. Giới hạn của truy vấn theo mảng

### 8.1. Cần phân biệt “một phần tử” với “hai phần tử”

Nếu yêu cầu là “order có SKU A **và** SKU B, không cần cùng một dòng”, dùng:

~~~javascript
orders.find({
  "lines.sku": { $all: ["A", "B"] }
});
// Trong dữ liệu gốc: o001.
~~~

`$all` phù hợp cho các giá trị thuộc **mảng**. Với trường `"lines.sku"` trong mảng embedded document, truy vấn yêu cầu tập giá trị SKU chứa cả A và B; mỗi giá trị có thể đến từ phần tử khác nhau. Không thể yêu cầu một dòng có `sku` vừa bằng A vừa bằng B thông thường.

Nếu muốn tìm **có một dòng A > 5 và một dòng B > 5**, có thể dùng hai `$elemMatch` trên cùng mảng, kết hợp bằng `$and`:

~~~javascript
orders.find({
  $and: [
    { lines: { $elemMatch: { sku: "A", quantity: { $gt: 5 } } } },
    { lines: { $elemMatch: { sku: "B", quantity: { $gt: 5 } } } }
  ]
});
// Dữ liệu gốc: không có order nào thỏa cả hai.
~~~

Hai `$elemMatch` độc lập có thể khớp hai phần tử khác nhau, đúng với yêu cầu có **hai loại dòng hàng**.

### 8.2. `$elemMatch` ở mức mảng nào?

Xét một cấu trúc lồng nhiều mảng:

~~~javascript
{
  _id: "nested-001",
  shipments: [
    {
      warehouse: "HN",
      packages: [
        { sku: "A", quantity: 1 },
        { sku: "B", quantity: 8 }
      ]
    }
  ]
}
~~~

Muốn “một shipment từ HN có **một package A > 5**”, phải đặt `$elemMatch` đúng cấp:

~~~javascript
db.nested_orders_demo_008.find({
  shipments: {
    $elemMatch: {
      warehouse: "HN",
      packages: {
        $elemMatch: {
          sku: "A",
          quantity: { $gt: 5 }
        }
      }
    }
  }
});
// Document minh họa trên không khớp.
~~~

Đặt `$elemMatch` ngoài cùng chỉ ràng buộc các trường trong **một shipment**. `$elemMatch` bên trong ràng buộc `sku` và `quantity` trong **một package**. Mỗi toán tử có phạm vi tại một mảng cụ thể.

Ví dụ dùng collection khác để minh họa cú pháp; nếu muốn chạy, cần insert document vào `nested_orders_demo_008` trước. Không sửa dữ liệu mẫu chính chỉ để thực hành cấu trúc khác.

### 8.3. `$elemMatch` filter khác `$elemMatch` projection

~~~javascript
// Filter: chọn order có ít nhất một dòng A quantity > 5.
orders.find({
  lines: { $elemMatch: { sku: "A", quantity: { $gt: 5 } } }
});
~~~

Query trên trả về **toàn bộ mảng lines** của những order phù hợp. Nếu muốn response chỉ hiển thị **phần tử đầu tiên** thỏa điều kiện, dùng projection `$elemMatch`:

~~~javascript
orders.find(
  { _id: "o005" },
  {
    lines: {
      $elemMatch: { sku: "A", quantity: { $gt: 5 } }
    }
  }
);
// Chỉ một dòng A×9 được đưa vào phần lines của kết quả.
~~~

Projection này **không trả mọi phần tử khớp** nếu order chứa nhiều dòng cùng đạt ngưỡng. Muốn xây một mảng kết quả gồm tất cả phần tử phù hợp, cân nhắc aggregation `$filter`. Đó là bài toán **biến đổi kết quả**, khác với việc tìm các order thỏa predicate.

### 8.4. Đối sánh document nguyên khối có thể phụ thuộc thứ tự field

~~~javascript
// So sánh cả embedded document với giá trị chỉ có 2 trường.
orders.find({
  lines: {
    sku: "A",
    quantity: 6
  }
});
~~~

Trong ví dụ này `lines` là mảng chứa các subdocument có cả `unitPriceVnd`. So sánh document nguyên khối đòi hỏi cấu trúc và thứ tự field phù hợp, nên không thay thế cho tìm thuộc tính con. Dùng dot notation hoặc `$elemMatch` để biểu diễn điều kiện một phần của subdocument; không dùng object equality tùy tiện.

### 8.5. `Not` và null trên mảng dễ bị hiểu sai

Các câu hỏi “không có dòng SKU A”, “có dòng khác A”, “chỉ có dòng không phải A” **không tương đương**. Chẳng hạn:

~~~javascript
// Không có phần tử lines.sku nào bằng A; có thể gồm order lines rỗng.
orders.find({ "lines.sku": { $ne: "A" } });
~~~

Query trên khác với:

~~~javascript
// Có ít nhất một phần tử của lines có sku khác A.
orders.find({
  lines: { $elemMatch: { sku: { $ne: "A" } } }
});
~~~

`o001` có cả A và B: truy vấn thứ nhất **không** khớp, truy vấn thứ hai **có** khớp (dòng B). Đừng suy đoán ngữ nghĩa của `Not` trong tên phương thức chỉ từ tiếng Anh; hãy đối chiếu BSON thực tế, nhất là với mảng và trường thiếu.

## 9. Sắp xếp, phân trang và kết quả trên mảng

Repository có thể kết hợp derived query với `Pageable`:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

Page<OrderDocument> page = repository.findByState(
    "OPEN",
    PageRequest.of(
        0, 2,
        Sort.by(Sort.Order.desc("createdAt"), Sort.Order.asc("id"))
    )
);
~~~

`Page<OrderDocument>` phân trang **document order**, không phân trang các phần tử của `lines`. `totalElements` được tính theo các order thỏa điều kiện (và có thể cần count query). Nếu gọi `findByLinesSku("A", pageable)`, các trang vẫn chứa order có SKU A, chứ không trở thành các trang `OrderLine` riêng lẻ.

Không giả định thứ tự các order nếu không có sort. Khi phân trang, nên bổ sung trường khóa ổn định như `_id` để hạn chế trùng/lọt bản ghi trong trường hợp nhiều document cùng `createdAt`.

Nếu sắp xếp trực tiếp theo `lines.quantity` là trường mảng, MongoDB có các quy tắc chọn giá trị từ nhiều phần tử làm khóa sort, kết quả có thể khác ý định “sắp xếp theo số lượng của dòng A”. Muốn sắp xếp theo **dòng A cụ thể**, thường cần aggregation để tìm phần tử/giá trị cần dùng làm khóa sắp xếp trước khi sort.

## 10. Index multikey và hiệu năng truy vấn

MongoDB hỗ trợ **multikey index** khi field được index chứa mảng. Ví dụ:

~~~javascript
orders.createIndex({ "shippingAddress.city": 1 });
orders.createIndex({ "lines.sku": 1 });
~~~

Index `"shippingAddress.city"` phục vụ điều kiện trên object nhúng. Index `"lines.sku"` trở thành multikey khi có mảng `lines` và giúp truy vấn tìm order theo SKU.

### 10.1. Compound multikey index cho cùng một dòng hàng

Nếu thường xuyên tìm bằng **SKU và số lượng trên cùng phần tử**:

~~~javascript
orders.createIndex({
  "lines.sku": 1,
  "lines.quantity": 1
});
~~~

Vì hai field cùng thuộc **mảng `lines`**, compound multikey index có thể hữu ích. Tuy nhiên việc ràng buộc **cùng một phần tử** bằng `$elemMatch` còn có ý nghĩa đối với cách MongoDB **kết hợp các index bounds**.

~~~javascript
orders.find({
  lines: {
    $elemMatch: {
      sku: "A",
      quantity: { $gt: 5 }
    }
  }
}).explain("executionStats");
~~~

Với các điều kiện dot notation rời rạc không có `$elemMatch`, MongoDB không thể tùy ý coi hai điều kiện thuộc cùng một phần tử để kết hợp index bounds như trường hợp `$elemMatch`. Vì vậy khác biệt ở đây vừa là **tính chính xác nghiệp vụ** vừa có thể ảnh hưởng đến **hiệu năng**.

### 10.2. Không phải mọi compound index trên hai array field đều hợp lệ

MongoDB có ràng buộc đối với compound multikey index: một document không được đồng thời có **hai field index độc lập đều là mảng** trong trường hợp cấu trúc index vi phạm giới hạn “parallel arrays”. Ví dụ một index kết hợp `tags` và `lines.sku` cần được đánh giá cẩn thận, vì cả hai có thể là mảng.

Với `"lines.sku"` và `"lines.quantity"`, hai đường dẫn cùng bắt nguồn từ một mảng embedded document `lines` nên là trường hợp cần thử nghiệm và giải thích theo **compound bounds for same array**. Đừng dùng quy tắc index của trường scalar để suy diễn mọi trường hợp mảng lồng.

### 10.3. Đo trước khi tối ưu

Khi xem `explain("executionStats")`, chú ý:

- `winningPlan`: có dùng index (`IXSCAN`) hay phải quét collection (`COLLSCAN`)?
- `totalKeysExamined` và `totalDocsExamined`: bao nhiêu khóa/index và document đã được duyệt?
- `nReturned`: số order thực tế trả về.
- Sort có phải thực hiện trong bộ nhớ hay không?

Mục tiêu không phải tạo index cho **mọi** đường dẫn; mỗi index làm tăng chi phí ghi và dung lượng lưu trữ. Chọn index dựa trên truy vấn có tần suất cao, độ chọn lọc và kết quả đo trên dữ liệu đủ đại diện.

## 11. Giới hạn của derived query và khi nào cần API khác

| Yêu cầu | Derived query | Hướng phù hợp |
| --- | --- | --- |
| Lọc order theo `state` | Rõ ràng | `findByState` |
| Lọc theo `shippingAddress.city` | Rõ ràng | `findByShippingAddressCity` |
| Có **bất kỳ** dòng nào SKU A | Rõ ràng | `findByLinesSku` |
| Có dòng SKU A **và** có dòng số lượng > 5, có thể khác nhau | `And` diễn đạt được | `findByLinesSkuAndLinesQuantityGreaterThan` |
| Có **cùng một dòng** SKU A với số lượng > 5 | Tên phương thức dễ gây hiểu sai | `@Query` + `$elemMatch` hoặc `Criteria.elemMatch` |
| Có nhiều điều kiện trong mảng lồng nhau | Khó biểu đạt an toàn | `MongoTemplate`/`@Query` với các cấp `$elemMatch` |
| Chỉ lấy các dòng hàng thỏa điều kiện | Derived filter không đủ | Aggregation `$filter` hoặc projection phù hợp |
| Tính tổng số lượng theo SKU trên các order | Không phải lọc đơn giản | Aggregation `$unwind`, `$match`, `$group` |
| Kết hợp document từ hai collection độc lập | Không phải property traversal đơn giản | `$lookup`, hai lần truy vấn hoặc mô hình nhúng phù hợp |

Sử dụng tên derived query khi **ý nghĩa điều kiện đọc ra rõ ràng**. Với yêu cầu “cùng một phần tử”, tên `findByLinesSkuAndLinesQuantityGreaterThan` dễ khiến reviewer tin rằng đã ràng buộc đúng, dù query tạo ra không có `$elemMatch`. Khi đó, một `@Query` tường minh thường an toàn hơn.

### 11.1. Không thay `$elemMatch` bằng Query by Example một cách máy móc

Spring Data hỗ trợ `Query by Example` để truy vấn từ một probe object. Nhưng QBE có phạm vi matcher và giới hạn riêng; không nên giả định việc đặt một `OrderLine` trong một probe có nghĩa MongoDB sẽ ràng buộc mọi thuộc tính trên **cùng phần tử** như `$elemMatch`. Với nghiệp vụ cần đúng ngữ nghĩa mảng, hãy kiểm tra query thực tế hoặc dùng API có thể hiện rõ `$elemMatch`.

### 11.2. Reactive repository vẫn dùng cùng ngữ nghĩa MongoDB

~~~java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    Flux<OrderDocument> findByLinesSku(String sku);
}
~~~

Việc trả `Flux<OrderDocument>` chỉ thay đổi **mô hình thực thi bất đồng bộ**; không đổi ngữ nghĩa dot notation và `$elemMatch`. Nếu reactive query cần cùng một phần tử, vẫn phải dùng `@Query` hoặc `ReactiveMongoTemplate` với `Criteria.elemMatch`. Publisher chỉ thực thi khi được subscribe trong chuỗi reactive.

## 12. Chẩn đoán lỗi và kiểm thử

### 12.1. Những sai sót phổ biến

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `findByShippingAddressCity` lỗi khi khởi động | Không có property Java `shippingAddress.city` hoặc parser chọn đường dẫn sai | Kiểm tra model, dùng `ShippingAddress_City` để tách rõ nếu mơ hồ |
| Query theo city trả rỗng | Sai tên BSON/alias, sai kiểu dữ liệu, sai database hoặc collection | So sánh với `mongosh` và mapping `@Field` |
| `findByLinesSku("A")` trả cả order có dòng B | Derived query chọn order, không project riêng dòng khớp | Kiểm tra toàn bộ `lines` của order được trả |
| `And` cho kết quả có `o001` dù A chỉ có quantity 1 | Hai predicate khớp ở hai phần tử khác nhau | Sử dụng `$elemMatch` |
| Dùng `$elemMatch` mà dữ liệu có `lines` là object đơn | `$elemMatch` chỉ xử lý array | Kiểm tra schema/type của `lines`, sửa dữ liệu sai mô hình |
| Mongo query đúng nhưng repository trả sai dữ liệu mong đợi | Converter/mapping khác kiểu BSON hoặc dùng nhầm repository | Kiểm tra property path, `@Document`, `@MongoId` và query đã sinh |
| Truy vấn nhanh khi ít dữ liệu nhưng chậm ở production | Thiếu index multikey hoặc phải duyệt nhiều document | Đo `explain("executionStats")`, thiết kế index theo predicate |
| `@Query` trả về đủ order nhưng không cắt `lines` | `$elemMatch` ở filter, không phải projection | Dùng projection `$elemMatch` hoặc aggregation `$filter` |
| Sắp xếp theo `lines.quantity` khó dự đoán | Mỗi order có nhiều quantity | Tính khóa sort cụ thể bằng aggregation |

### 12.2. Test phân biệt hai trường hợp bắt buộc

Lỗi phổ biến là unit test chỉ chứa order có một phần tử `lines`. Khi đó cả derived query và `$elemMatch` đều có thể trả kết quả giống nhau, khiến sai lầm không bị phát hiện. Test nên có ít nhất:

1. **Cross-element trap:** order `o001` có A×1 và B×8. Derived query với `And` **khớp**, nhưng `$elemMatch` **không**.
2. **Same-element match:** order `o002` có A×6. Cả hai truy vấn đều khớp.
3. **Nhiều phần tử cùng SKU:** order `o005` có A×3, A×9. `$elemMatch` khớp nhờ A×9.
4. **Mảng rỗng:** order `o004` không có dòng hàng; không khớp.
5. **Sai kiểu/thiếu mảng:** chỉ thêm fixture trong collection test riêng nếu domain cho phép dữ liệu legacy không chuẩn.

### 12.3. Integration test với MongoDB thật hoặc Testcontainers

Ví dụ dưới đây dùng `OrderRepository` đã khai báo phương thức `@Query` ở mục 7.2, trên MongoDB test cô lập:

~~~java
package com.example.derived;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class EmbeddedArrayQueryTest {
    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    @Test
    void elemMatchExcludesCrossElementFalsePositive() {
        // Chạy với MongoDB test biệt lập và collection dành riêng cho test.
        var collection = template.getDb()
            .getCollection("orders_derived_demo_008");

        collection.deleteMany(new Document("_id", new Document("$in",
            List.of("test-cross-008", "test-same-008"))));

        try {
            collection.insertOne(new Document("_id", "test-cross-008")
                .append("state", "OPEN")
                .append("lines", List.of(
                    new Document("sku", "A").append("quantity", 1),
                    new Document("sku", "B").append("quantity", 8)
                )));

            collection.insertOne(new Document("_id", "test-same-008")
                .append("state", "OPEN")
                .append("lines", List.of(
                    new Document("sku", "A").append("quantity", 6)
                )));

            var broad = repository
                .findByLinesSkuAndLinesQuantityGreaterThan("A", 5)
                .stream().map(OrderDocument::getId).toList();

            var precise = repository
                .findHavingLineWithQuantityGreaterThan("A", 5)
                .stream().map(OrderDocument::getId).toList();

            assertThat(broad).contains("test-cross-008", "test-same-008");
            assertThat(precise).contains("test-same-008");
            assertThat(precise).doesNotContain("test-cross-008");
        } finally {
            collection.deleteMany(new Document("_id", new Document("$in",
                List.of("test-cross-008", "test-same-008"))));
        }
    }
}
~~~

Test cần repository thực tế trong ApplicationContext, database test, và converter phù hợp với entity. Trên collection test trống, nếu có thêm fixture khác thỏa SKU A thì kết quả vẫn chính xác vì `contains/doesNotContain` chỉ kiểm tra các ID cụ thể. Trong dự án thật, ưu tiên dùng **collection riêng cho test** để không tác động đến dữ liệu khác; phần setup trong ví dụ xóa đúng hai ID fixture nên chỉ dùng trong môi trường test riêng.

Điểm cần kiểm chứng là **MongoDB query engine** và **Spring Data mapping** chạy thật. Mock repository sẽ không tái hiện việc hai field của một array khớp hai phần tử khác nhau.

### 12.4. Đọc query và kiểm tra execution plan

Khi nghi ngờ query sinh sai, tái hiện điều kiện bằng `mongosh` trước:

~~~javascript
// Rộng: có thể khớp trên các phần tử khác nhau.
orders.find({
  "lines.sku": "A",
  "lines.quantity": { $gt: 5 }
}, { _id: 1 });

// Chính xác: cùng một phần tử.
orders.find({
  lines: { $elemMatch: { sku: "A", quantity: { $gt: 5 } } }
}, { _id: 1 });
~~~

Sau khi xác nhận tập kết quả, mới phân tích index bằng `explain("executionStats")`. Không sửa index để giải quyết **lỗi ngữ nghĩa** của query; index có thể tăng tốc nhưng không làm điều kiện `And` tự biến thành `$elemMatch`.

## 13. Bài thực hành

### Bài 1 — Document nhúng đơn

Tìm tất cả order giao đến Hà Nội, trạng thái `OPEN`.

**Đáp án gợi ý:**

~~~java
List<OrderDocument> findByStateAndShippingAddressCity(
    String state, String city
);
~~~

Gọi `findByStateAndShippingAddressCity("OPEN", "Hà Nội")` trả về **o001, o005** trên bộ dữ liệu gốc.

### Bài 2 — Đánh giá một derived query

Cho phương thức:

~~~java
List<OrderDocument> findByLinesSkuAndLinesQuantityGreaterThan(
    String sku, int quantity
);
~~~

Với `("A", 5)`, query có lấy `o001` không? **Có.** Dòng A×1 và dòng B×8 thỏa hai điều kiện riêng trên cùng order. Hãy giải thích vì sao nó không đáp ứng yêu cầu “một dòng A×n với n > 5”.

### Bài 3 — Viết lại điều kiện chính xác

Viết truy vấn `mongosh` chọn order có một dòng A với quantity `>= 5`.

**Đáp án:**

~~~javascript
orders.find({
  lines: {
    $elemMatch: {
      sku: "A",
      quantity: { $gte: 5 }
    }
  }
});
// Kết quả: o002 và o005.
~~~

Nếu chuyển sang Spring Data, dùng `@Query` với `$elemMatch` hoặc `Criteria.where("lines").elemMatch(...)`; nhớ đổi `$gt` thành `$gte` theo yêu cầu.

### Bài 4 — Một hay hai phần tử?

Tìm order có **cả dòng SKU A và dòng SKU B**, không cần cùng dòng. Điều kiện nào phù hợp?

**Đáp án:**

~~~javascript
orders.find({
  "lines.sku": { $all: ["A", "B"] }
});
// Kết quả: o001.
~~~

Đây là yêu cầu về **hai giá trị trong tập dòng hàng**; không nên ghép `sku: "A"` và `sku: "B"` vào cùng một `$elemMatch`.

### Bài 5 — Projection trên phần tử mảng

Muốn tìm order có dòng A quantity > 5, nhưng chỉ hiển thị **dòng đầu tiên** khớp thay vì cả mảng. Sử dụng gì?

**Đáp án:** dùng `$elemMatch` trong **projection** bên cạnh filter; nếu muốn lấy tất cả dòng khớp, dùng aggregation `$filter`. Kiểm tra điều kiện ở tầng filter và mục tiêu chuyển đổi response trước khi chọn API.

### Bài 6 — Chẩn đoán hiệu năng

Truy vấn thường xuyên là “SKU A với quantity > 5 trên cùng một dòng”. Đề xuất index và cách xác nhận hiệu quả.

**Đáp án tham khảo:** cân nhắc compound multikey index `{ "lines.sku": 1, "lines.quantity": 1 }`; dùng `$elemMatch` trên `lines` và đo `explain("executionStats")` với dữ liệu đại diện. Đối chiếu `keysExamined`, `docsExamined` và `nReturned` trước/sau, đồng thời đánh giá chi phí ghi của index.

## Tài liệu tham khảo

- [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): keyword suy diễn, `Containing`, `@Query` và giới hạn/phương thức repository.
- [Spring Data Commons — Defining Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): cú pháp `findBy...`, property traversal và ký hiệu `_` khi tên mơ hồ.
- [Spring Data MongoDB — `Criteria` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html): `elemMatch(Criteria)` và các toán tử khác.
- [MongoDB Manual — Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/): dot notation và truy vấn array embedded documents.
- [MongoDB Manual — `$elemMatch` Query Predicate](https://www.mongodb.com/docs/manual/reference/operator/query/elemmatch/): một phần tử phải thỏa tất cả predicate.
- [MongoDB Manual — `$elemMatch` Projection](https://www.mongodb.com/docs/manual/reference/operator/projection/elemmatch/): giới hạn các phần tử trả về trong projection.
- [MongoDB Manual — Multikey Index Bounds](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/multikey-index-bounds/): mối quan hệ giữa `$elemMatch` và kết hợp index bounds.
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/): index cho array và giới hạn compound multikey.
