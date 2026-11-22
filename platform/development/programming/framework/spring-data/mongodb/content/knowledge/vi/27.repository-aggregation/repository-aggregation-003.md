# Ánh xạ kết quả thành DTO, scalar hoặc `AggregationResults`

> **Chương:** Aggregation repository  
> **Module:** `SPRING_DATA_MONGODB` — dùng Spring Data MongoDB kết nối, ánh xạ document và thao tác dữ liệu qua `MongoTemplate` hoặc repository; thực hành aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.  
> **Mục tiêu:** Khai báo `@Aggregation` trên repository; lựa chọn kiểu trả về là DTO/record, interface projection, scalar, `List<T>`, `Slice<T>`, `Stream<T>` hoặc `AggregationResults<T>`; nắm cơ chế chuyển một `Document` thành scalar, phân biệt `_id` của `$group` với ID gốc, xử lý kết quả rỗng, tên alias, dữ liệu sai kiểu và chi phí thực thi.

## 1. Bài toán: cùng một pipeline, nhiều cách nhận kết quả

Một collection `orders` lưu nhiều đơn hàng. Giao diện quản trị có các yêu cầu khác nhau:

1. **Danh sách tóm tắt**: mỗi trạng thái có số đơn hàng và tổng giá trị.
2. **KPI dạng số**: tổng doanh thu đơn `PAID` của một tenant.
3. **Danh sách một trường**: lấy những trạng thái có mặt trong tập dữ liệu.
4. **Báo cáo chẩn đoán**: lấy cả kết quả đã map và response thô của aggregation.

Tất cả đều dùng MongoDB aggregation, nhưng **kiểu trả về Java không giống nhau**. Một pipeline có thể tạo các document:

~~~javascript
[
  { state: "PAID", orderCount: 4, grossVnd: 1250000 },
  { state: "NEW", orderCount: 1, grossVnd: 100000 },
  { state: "CANCELLED", orderCount: 1, grossVnd: 80000 }
]
~~~

Nếu repository khai báo `List<StateSummary>`, Spring Data ánh xạ mỗi document vào một DTO. Nếu pipeline cho một document chỉ chứa `{ total: 1250000 }` và method trả `Long`, Spring Data có thể **trích một giá trị scalar**. Nếu trả `AggregationResults<StateSummary>`, caller nhận wrapper gồm dữ liệu đã map và thông tin phản hồi thô.

~~~mermaid
flowchart TD
    A["Repository @Aggregation"] --> B["MongoDB aggregation pipeline"]
    B --> C["Document / Documents"]
    C --> D{"Kiểu trả về method"}
    D --> E["DTO / record / interface projection"]
    D --> F["Scalar: Long / String"]
    D --> G["List / Slice / Stream"]
    D --> H["AggregationResults<T>"]
    H --> I["mappedResults + rawResults"]
~~~

**Nguyên tắc cốt lõi:** Tính đúng đắn của mapping phụ thuộc vào **hình dạng BSON sau stage cuối cùng** — không phụ thuộc vào entity gốc còn những field gì. Sau `$group` và `$project`, dữ liệu đã thành **read model**; phải thiết kế đầu ra có chủ đích.

## 2. Dữ liệu mẫu và kết quả chuẩn để đối chiếu

### 2.1. Tạo fixture trên MongoDB học tập

Trong `mongosh`, chọn database **test biệt lập**. Không chạy trên collection production:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_repository_agg_demo_003;

orders.insertMany([
  {
    _id: "o701", tenant_id: "t01", state_code: "PAID",
    amount_vnd: NumberLong(120000),
    placed_at: ISODate("2026-10-01T08:00:00Z"),
    buyer_doc: { city_name: "Hà Nội" },
    order_lines: [{ sku: "A", qty: 2 }, { sku: "B", qty: 1 }]
  },
  {
    _id: "o702", tenant_id: "t01", state_code: "PAID",
    amount_vnd: NumberLong(350000),
    placed_at: ISODate("2026-10-02T08:00:00Z"),
    buyer_doc: { city_name: "Huế" },
    order_lines: [{ sku: "A", qty: 3 }]
  },
  {
    _id: "o703", tenant_id: "t01", state_code: "NEW",
    amount_vnd: NumberLong(100000),
    placed_at: ISODate("2026-10-03T08:00:00Z"),
    buyer_doc: { city_name: "Hà Nội" },
    order_lines: [{ sku: "C", qty: 1 }]
  },
  {
    _id: "o704", tenant_id: "t01", state_code: "PAID",
    amount_vnd: NumberLong(530000),
    placed_at: ISODate("2026-10-04T08:00:00Z"),
    buyer_doc: { city_name: "Hà Nội" },
    order_lines: [{ sku: "C", qty: 4 }]
  },
  {
    _id: "o705", tenant_id: "t02", state_code: "PAID",
    amount_vnd: NumberLong(900000),
    placed_at: ISODate("2026-10-05T08:00:00Z"),
    buyer_doc: { city_name: "Hồ Chí Minh" },
    order_lines: [{ sku: "A", qty: 9 }]
  },
  {
    _id: "o706", tenant_id: "t01", state_code: "CANCELLED",
    amount_vnd: NumberLong(80000),
    placed_at: ISODate("2026-10-06T08:00:00Z"),
    buyer_doc: { city_name: "Hà Nội" },
    order_lines: []
  },
  {
    _id: "o707", tenant_id: "t01", state_code: "PAID",
    amount_vnd: NumberLong(250000),
    placed_at: ISODate("2026-10-07T08:00:00Z"),
    buyer_doc: { city_name: "Đà Nẵng" },
    order_lines: [{ sku: "B", qty: 2 }]
  }
]);

orders.createIndex({
  tenant_id: 1,
  state_code: 1,
  placed_at: -1,
  _id: -1
});
~~~

Không chạy lại `insertMany` khi các ID này đã tồn tại; MongoDB sẽ trả duplicate key. Các lệnh aggregation bên dưới chỉ đọc, nên có thể chạy lặp nếu không có writer khác. Với các ví dụ ghi dữ liệu bổ sung ở phần kiểm thử, chỉ dùng những ID fixture riêng.

### 2.2. Số liệu chuẩn

| Phạm vi | Số order | Tổng amount (VND) |
| --- | ---: | ---: |
| t01, PAID | 4 | 1.250.000 |
| t01, NEW | 1 | 100.000 |
| t01, CANCELLED | 1 | 80.000 |
| t01, tất cả trạng thái | 6 | 1.430.000 |
| t02, PAID | 1 | 900.000 |

Với t01 và trạng thái PAID:

\[
120000 + 350000 + 530000 + 250000 = 1250000
\]

Con số **1.250.000** là giá trị kỳ vọng để phát hiện query quên lọc tenant, mapper trích nhầm trường hoặc cộng sai kiểu dữ liệu.

### 2.3. Pipeline BSON tham chiếu

Trước khi viết Java, chạy pipeline tương đương trong `mongosh`:

~~~javascript
orders.aggregate([
  { $match: { tenant_id: "t01" } },
  {
    $group: {
      _id: "$state_code",
      orderCount: { $sum: 1 },
      grossVnd: { $sum: "$amount_vnd" }
    }
  },
  {
    $project: {
      _id: 0,
      state: "$_id",
      orderCount: 1,
      grossVnd: 1
    }
  },
  { $sort: { state: 1 } }
]);
~~~

Kỳ vọng ba trạng thái: CANCELLED, NEW, PAID; tổng lần lượt **80.000**, **100.000** và **1.250.000** VND. `$sort` nằm **sau `$project`** và dùng alias `state`, không dùng lại `state_code` đã bị loại.

## 3. Entity đầu vào: ánh xạ property Java sang BSON

### 3.1. Model miền

Ví dụ các class thuộc package `com.example.repositoryagg`:

~~~java
// OrderState.java
package com.example.repositoryagg;

public enum OrderState {
    NEW, PAID, CANCELLED
}
~~~

~~~java
// BuyerInfo.java
package com.example.repositoryagg;

import org.springframework.data.mongodb.core.mapping.Field;

public class BuyerInfo {
    @Field("city_name")
    private String city;

    protected BuyerInfo() { }

    public String getCity() { return city; }
}
~~~

~~~java
// OrderLine.java
package com.example.repositoryagg;

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

~~~java
// OrderDocument.java
package com.example.repositoryagg;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_repository_agg_demo_003")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("state_code")
    private OrderState state;

    @Field("amount_vnd")
    private long amountVnd;

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
    public long getAmountVnd() { return amountVnd; }
    public Instant getPlacedAt() { return placedAt; }
    public BuyerInfo getBuyer() { return buyer; }
    public List<OrderLine> getLines() { return lines; }
}
~~~

| Property Java | Tên BSON thực |
| --- | --- |
| `id` | `_id` |
| `tenantId` | `tenant_id` |
| `state` | `state_code` |
| `amountVnd` | `amount_vnd` |
| `placedAt` | `placed_at` |
| `buyer.city` | `buyer_doc.city_name` |
| `lines.quantity` | `order_lines.qty` |

`@MongoId(FieldType.STRING)` giữ `_id` dưới dạng BSON string, nhất quán với fixture. Trong repository `@Aggregation`, pipeline được ánh xạ dựa trên **domain type của repository** (`OrderDocument`) để xét metadata như `@Field` khi framework xử lý các field reference.

**Quy ước:** Khi viết pipeline repository trên entity này, ưu tiên đường dẫn **property Java** như `tenantId`, `state`, `amountVnd` trong các biểu thức được Spring Data hỗ trợ mapping. Trong `mongosh` hoặc raw driver, dùng **tên BSON**.

### 3.2. Đừng nhầm input entity và output DTO

Repository sử dụng `OrderDocument` để biết collection và metadata input, nhưng kết quả `$group` **không còn là OrderDocument**:

~~~javascript
{
  _id: "PAID",
  orderCount: 4,
  grossVnd: 1250000
}
~~~

`_id` lúc này là **khóa nhóm** (state), không phải ID đơn hàng. Trả document này vào `OrderDocument` chỉ vì repository gốc có kiểu `OrderDocument` sẽ tạo mapping không phù hợp, dễ nhận object thiếu field hoặc mang ý nghĩa sai.

## 4. `@Aggregation` trên repository

### 4.1. Annotation và tham số

Spring Data MongoDB cung cấp:

~~~java
import org.springframework.data.mongodb.repository.Aggregation;
~~~

Bạn có thể khai báo một stage:

~~~java
@Aggregation("{ '$group': { '_id': '$state', 'orders': { '$sum': 1 } } }")
List<StateCount> countByState();
~~~

hoặc một mảng các stage:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', 'orders': { '$sum': 1 } } }"
})
List<StateCount> countByStateForTenant(String tenantId);
~~~

`?0` là placeholder tham số **đầu tiên**, `?1` là tham số thứ hai. Có thể dùng SpEL `?#{...}` trong những tình huống cần thiết, nhưng không nối trực tiếp JSON từ text người dùng.

Đối với `@Aggregation`, **tên method không cần được parser thành derived query**: chính pipeline annotation quy định thao tác. Method vẫn thuộc repository của `OrderDocument`, nên Spring Data có thông tin input domain type.

### 4.2. Đọc pipeline theo luồng

~~~text
OrderRepository (@Aggregation)
    |
    |  Pipeline JSON khai báo trong annotation
    v
Spring Data: bind tham số, mapping @Field
    |
    v
MongoDB: $match -> $group -> $project -> $sort
    |
    v
BSON document sau stage cuối
    |
    v
DTO | scalar | List | Slice | Stream | AggregationResults
~~~

**Điểm quyết định là output shape.** Khi return type thay đổi từ `StateSummary` thành `Long`, bạn nên kiểm lại pipeline cuối cùng thay vì chỉ đổi chữ ký Java.

## 5. Trả về DTO/record cho báo cáo tổng hợp

### 5.1. Khai báo output record

~~~java
// StateSummary.java
package com.example.repositoryagg;

public record StateSummary(
    String state,
    long orderCount,
    long grossVnd
) {
}
~~~

Tên các component của record nên **khớp alias BSON output**; các constructor parameter phải có kiểu tương thích. Java record được Spring Data hỗ trợ trong mapping class-based khi sử dụng các phiên bản phù hợp.

### 5.2. Repository trả `List<StateSummary>`

~~~java
// OrderRepository.java
package com.example.repositoryagg;

import java.util.List;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0 } }",
        "{ '$group': { " +
            "'_id': '$state', " +
            "'orderCount': { '$sum': 1 }, " +
            "'grossVnd': { '$sum': '$amountVnd' } " +
        "} }",
        "{ '$project': { " +
            "'_id': 0, " +
            "'state': '$_id', " +
            "'orderCount': 1, " +
            "'grossVnd': 1 " +
        "} }",
        "{ '$sort': { 'state': 1 } }"
    })
    List<StateSummary> summarizeByState(String tenantId);
}
~~~

Đoạn Java trên dùng phép nối **các chuỗi hằng** để giúp code trên trang dễ đọc; compiler ghép thành từng chuỗi JSON stage trước khi Spring Data phân tích. Đây không phải phép nối input người dùng vào JSON. Trong code thực, có thể viết mỗi stage trên một dòng hoặc dùng annotation với JSON đầy đủ để đơn giản hơn.

Gọi:

~~~java
List<StateSummary> summaries =
    repository.summarizeByState("t01");

// Theo $sort state ASC:
// CANCELLED: orderCount=1, grossVnd=80000
// NEW:       orderCount=1, grossVnd=100000
// PAID:      orderCount=4, grossVnd=1250000
~~~

### 5.3. Vì sao cần `$project` sau `$group`?

Nếu pipeline dừng ở:

~~~javascript
{
  $group: {
    _id: "$state_code",
    orderCount: { $sum: 1 },
    grossVnd: { $sum: "$amount_vnd" }
  }
}
~~~

thì kết quả có `_id`, `orderCount` và `grossVnd` — **không có field `state`**. Record `StateSummary(String state, ...)` sẽ thiếu giá trị cần thiết nếu không có mapping alias đặc biệt.

Stage:

~~~javascript
{
  $project: {
    _id: 0,
    state: "$_id",
    orderCount: 1,
    grossVnd: 1
  }
}
~~~

chủ động tạo `state`, đúng tên record component. Việc loại `_id` còn tránh sự mơ hồ giữa khóa nhóm và ID gốc.

### 5.4. Khi muốn giữ `_id` của group

Spring Data có thể ánh xạ `_id` sang property được đánh dấu `@Id` trong DTO/class-based projection:

~~~java
// Ví dụ DTO class, nếu cố ý giữ _id làm khóa nhóm:
public class StateGroup {
    @org.springframework.data.annotation.Id
    private String state;
    private long orderCount;
    private long grossVnd;

    protected StateGroup() { }

    public String getState() { return state; }
    public long getOrderCount() { return orderCount; }
    public long getGrossVnd() { return grossVnd; }
}
~~~

Tuy vậy, với read DTO API, **tạo alias `state` rõ ràng** qua `$project` thường dễ hiểu hơn. Nếu client yêu cầu output có tên `groupKey`, hãy chủ động tạo `groupKey`; đừng để mapping `_id` mang hai nghĩa khác nhau trong codebase.

### 5.5. DTO class so với record

Một DTO truyền thống cũng hợp lệ nếu có constructor/getter và metadata phù hợp:

~~~java
public class StateSummaryDto {
    private final String state;
    private final long orderCount;
    private final long grossVnd;

    public StateSummaryDto(
            String state, long orderCount, long grossVnd) {
        this.state = state;
        this.orderCount = orderCount;
        this.grossVnd = grossVnd;
    }

    public String getState() { return state; }
    public long getOrderCount() { return orderCount; }
    public long getGrossVnd() { return grossVnd; }
}
~~~

Với class không phải record, Java compiler/build cần giữ tên tham số constructor hoặc dùng cấu hình mapping thích hợp (`@PersistenceCreator` nếu có nhiều constructor). Nếu output BSON thiếu field hoặc sai kiểu, lỗi mapping có thể xảy ra ngay ở constructor hoặc bị chuyển thành default ngoài ý muốn. Đó là lý do cần test **giá trị từng field**, không chỉ test số phần tử trong danh sách.

## 6. Interface projection từ aggregation document

Không bắt buộc tạo class concrete cho mọi read model. Repository aggregation có thể trả **interface-based projection** dùng proxy đọc các field của `Document` đầu ra.

~~~java
// StateSummaryView.java
package com.example.repositoryagg;

public interface StateSummaryView {
    String getState();
    long getOrderCount();
    long getGrossVnd();
}
~~~

Khai báo một method với cùng pipeline nhưng kiểu trả khác:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', " +
        "'orderCount': { '$sum': 1 }, " +
        "'grossVnd': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'state': '$_id', " +
        "'orderCount': 1, 'grossVnd': 1 } }"
})
List<StateSummaryView> summarizeViews(String tenantId);
~~~

Thêm method này vào `OrderRepository` trong ví dụ. Spring Data có thể tạo projection proxy đọc `state`, `orderCount` và `grossVnd` từ document kết quả.

### 6.1. Nên chọn DTO hay interface projection?

| Tiêu chí | Record / class DTO | Interface projection |
| --- | --- | --- |
| Cơ chế | Ánh xạ document vào object | Proxy truy cập field kết quả |
| Hợp đồng field | Constructor/component rõ tên và kiểu | Getter `get...()` tương ứng field |
| Tính bất biến | Record immutable | Interface expose getter, không phải dữ liệu mutable |
| Debug | Object cụ thể, dễ log/toString | Proxy cần hiểu backing document |
| Dùng khi | Read model ổn định, nhiều tầng nghiệp vụ | Báo cáo nhỏ, chỉ cần getter đơn giản |

Projection chỉ truy cập **field đã có trong output**. Nếu pipeline tạo `revenue` nhưng interface khai báo `getGrossVnd()`, Spring Data không tự hiểu hai tên có cùng nghĩa nghiệp vụ.

### 6.2. Đừng nhầm với tối ưu server-side

Việc return type là `StateSummaryView` **không tự đảm bảo** pipeline chỉ tải các field cần thiết ở các stage trước. Pipeline mới quyết định `$project`, `$group` và kích thước dữ liệu xử lý. Phải xem command BSON và execution plan thay vì suy từ getter Java.

## 7. Scalar: ánh xạ một `Document` thành `Long`, `String`

### 7.1. Pipeline trả một giá trị

KPI “tổng doanh thu PAID của t01”:

~~~javascript
orders.aggregate([
  { $match: { tenant_id: "t01", state_code: "PAID" } },
  {
    $group: {
      _id: null,
      total: { $sum: "$amount_vnd" }
    }
  },
  { $project: { _id: 0, total: 1 } }
]);
// [{ total: 1250000 }]
~~~

Ở Java:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0, 'state': ?1 } }",
    "{ '$group': { '_id': null, " +
        "'total': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'total': 1 } }"
})
Long totalAmountForState(String tenantId, OrderState state);
~~~

Gọi:

~~~java
Long total = repository.totalAmountForState(
    "t01", OrderState.PAID
);
// total == 1_250_000L trên fixture gốc.
~~~

Trong trường hợp này, `@Aggregation` trả **một document có một giá trị**, và Spring Data MongoDB hỗ trợ trích giá trị trực tiếp thành **simple type** như `Long`.

### 7.2. Quy tắc trích simple type của Spring Data

Đối với một **document kết quả duy nhất**, Spring Data MongoDB xem xét các khả năng theo thứ tự:

1. Document chỉ có **một entry**: trả entry đó.
2. Document có **hai entry**, trong đó một entry là `_id`: trả entry còn lại.
3. Nếu nhiều entry: tìm **giá trị đầu tiên có thể gán/chuyển phù hợp với return type**.
4. Nếu không có giá trị phù hợp: **ném exception**.

Minh họa:

| BSON document kết quả | Return type | Đánh giá |
| --- | --- | --- |
| `{total:1250000}` | `Long` | Rõ ràng, khuyến nghị |
| `{_id:null,total:1250000}` | `Long` | Có thể trích `total` theo quy tắc hai entry |
| `{total:1250000,count:4}` | `Long` | **Mơ hồ**, có hơn một số |
| `{total:"not-a-number"}` | `Long` | Sai kiểu, có thể lỗi chuyển đổi |
| `{_id:"PAID"}` | `String` | Có một entry, nhận `"PAID"` |

**Quy tắc thiết kế:** Khi muốn scalar, **chỉ xuất đúng một field mang ý nghĩa cần lấy**, lý tưởng là một `$project` với `_id:0`. Đừng dựa vào “first assignable value” trong document nhiều field vì thứ tự và ý nghĩa lựa chọn dễ gây lỗi khi pipeline thay đổi.

### 7.3. Không coi scalar và một dòng tổng hợp là cùng loại

~~~java
public record TotalAmount(Long total) { }

@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0, 'state': ?1 } }",
    "{ '$group': { '_id': null, " +
        "'total': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'total': 1 } }"
})
TotalAmount totalAmountWrapped(
    String tenantId, OrderState state
);
~~~

`Long` trả trực tiếp **con số**; `TotalAmount` giữ **một object có tên field**. Wrapper DTO thường dễ mở rộng thêm đơn vị tiền tệ, số order hoặc cửa sổ thời gian trong tương lai, và API JSON cũng diễn đạt ý nghĩa tốt hơn.

### 7.4. Kết quả rỗng: `$group` không tự trả 0

Giả sử tenant `t99` không có order PAID. Pipeline:

~~~javascript
[
  { $match: { tenant_id: "t99", state_code: "PAID" } },
  { $group: { _id: null, total: { $sum: "$amount_vnd" } } }
]
~~~

không tự tạo một document `{total:0}` cho tập đầu vào rỗng; kết quả thường là **không có document**. Repository method single-result có thể trả `null` hoặc wrapper tùy chữ ký và version; **không giả định luôn có số 0**.

Thiết kế an toàn:

~~~java
public long totalPaidOrZero(
        String tenantId, OrderRepository repository) {
    Long value = repository.totalAmountForState(
        tenantId, OrderState.PAID
    );
    return value != null ? value : 0L;
}
~~~

Nếu dùng `Optional<Long>` trên repository method được phiên bản Spring Data hỗ trợ, có thể dùng `orElse(0L)`. Với các tổng hợp có thể trả nhiều dòng, đừng áp dụng quy tắc zero cho **mất kết quả do lỗi** — lỗi database/converter phải được báo riêng.

### 7.5. `BigDecimal` và loại số trong MongoDB

Fixture dùng `NumberLong(...)` và `$sum`. Tùy kiểu số đầu vào, phép tổng hợp có thể trả `Int32`, `Int64`, `Double` hoặc `Decimal128` theo quy tắc MongoDB và converter. `Long` phù hợp với số tiền **đơn vị đồng nguyên** trong giới hạn kiểu 64-bit.

Nếu cần phần thập phân, tỷ giá hoặc kế toán chính xác, cân nhắc `Decimal128`/`BigDecimal` và thiết kế phép làm tròn. Không đổi return type thành `Double` chỉ để “hết lỗi map” mà không xem mất mát độ chính xác.

## 8. `List<String>`, `List<Long>`: nhiều scalar từ nhiều document

Nếu mỗi output document đại diện **một trạng thái**, có thể xuất một trường và trả `List<String>`:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state' } }",
    "{ '$project': { '_id': 0, 'state': '$_id' } }",
    "{ '$sort': { 'state': 1 } }"
})
List<String> findDistinctStateNames(String tenantId);
~~~

Kết quả với `t01`:

~~~java
List<String> states =
    repository.findDistinctStateNames("t01");
// ["CANCELLED", "NEW", "PAID"]
~~~

Đây **không phải** chuyển ba document vào **một** `String`; mapper trích một giá trị từ **mỗi** result document và đưa các giá trị vào danh sách.

### 8.1. Tránh một danh sách numeric không rõ nghĩa

Ví dụ `List<Long>` chỉ chứa `grossVnd` của mỗi nhóm mà không còn field `state` sẽ làm mất khả năng biết con số thuộc trạng thái nào.

~~~javascript
[
  { grossVnd: 80000 },
  { grossVnd: 100000 },
  { grossVnd: 1250000 }
]
~~~

Nếu UI phải gắn nhãn, trả `List<StateSummary>` tốt hơn. `List<Long>` phù hợp khi giá trị đã có định danh rõ bằng thứ tự khác, hoặc client chỉ cần chuỗi numeric có contract thứ tự ổn định.

### 8.2. Nhiều result document nhưng return type đơn

Nếu pipeline `$group` theo state trả **ba document** mà method lại khai báo:

~~~java
StateSummary oneSummary(String tenantId);
~~~

thì không có định nghĩa rõ document nào được chọn. Spring Data query method single-result thông thường yêu cầu tối đa một result hoặc có quy tắc giới hạn rõ; khi số lượng vượt mức, có thể báo lỗi kích thước kết quả tùy cơ chế thực thi. Đừng dựa vào việc “lấy ngẫu nhiên dòng đầu”.

Nếu thật sự muốn một nhóm đứng đầu, đặt `$sort` rồi `$limit:1` **trong pipeline** và xác minh thứ tự; nếu muốn tất cả nhóm, trả `List<StateSummary>`.

## 9. `AggregationResults<T>`: giữ dữ liệu đã map và phản hồi thô

Đôi khi application cần thấy **cả mapped result lẫn raw response**, hoặc cần debug converter mà không mất thông tin BSON.

Spring Data MongoDB hỗ trợ:

~~~java
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
~~~

### 9.1. Repository trả wrapper generic

~~~java
// TotalAmount.java
package com.example.repositoryagg;

public record TotalAmount(Long total) {
}
~~~

Trong `OrderRepository`:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0, 'state': ?1 } }",
    "{ '$group': { '_id': null, " +
        "'total': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'total': 1 } }"
})
AggregationResults<TotalAmount> totalAmountRaw(
    String tenantId, OrderState state
);
~~~

Gọi:

~~~java
AggregationResults<TotalAmount> results =
    repository.totalAmountRaw("t01", OrderState.PAID);

List<TotalAmount> mapped = results.getMappedResults();
TotalAmount unique = results.getUniqueMappedResult();
org.bson.Document response = results.getRawResults();

// mapped.size() == 1.
// unique.total() == 1_250_000L trên fixture gốc.
~~~

`AggregationResults<T>` có các API chính:

| API | Ý nghĩa |
| --- | --- |
| `getMappedResults()` | Danh sách `T` đã được Spring Data map; rỗng nếu không có |
| `getUniqueMappedResult()` | Trả `T` khi có đúng 1; `null` nếu không có; lỗi nếu hơn 1 |
| `getRawResults()` | `Document` phản hồi thô từ server/driver |
| `getServerUsed()` | Thông tin server đã dùng khi khả dụng; có thể null |
| `iterator()` | Duyệt mapped results; wrapper triển khai `Iterable<T>` |

### 9.2. `getUniqueMappedResult()` không phải “lấy dòng đầu”

Giả sử pipeline nhóm theo trạng thái tạo ba row. Nếu code gọi:

~~~java
var unique = results.getUniqueMappedResult();
~~~

thì đây là **vi phạm hợp đồng**: `getUniqueMappedResult()` yêu cầu **0 hoặc 1** result và ném `IllegalArgumentException` khi danh sách có nhiều hơn một. Khi cần một trong các nhóm, dùng filter đủ hẹp hoặc `$sort` + `$limit` với mục tiêu rõ ràng.

### 9.3. `getRawResults()` dùng khi nào?

Raw result hữu ích khi:

- Kiểm tra kiểu BSON thực `Long`/`Double`/`Decimal128`.
- Đối chiếu output field khi DTO bị null hoặc sai tên.
- Chẩn đoán metadata phản hồi từ driver/server theo khả năng của API.
- Tạm thời tìm nguyên nhân một aggregation không map đúng vào record.

Nhưng `getRawResults()` **không nên bị trả thẳng lên API công khai**: nó có thể chứa metadata nội bộ, chi tiết BSON hoặc dữ liệu cần kiểm soát. Cấu trúc raw response có thể khác theo server/driver và không phải hợp đồng nghiệp vụ ổn định.

### 9.4. `AggregationResults<Document>` khi chưa có DTO

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', " +
        "'orderCount': { '$sum': 1 } } }"
})
AggregationResults<org.bson.Document> countRaw(String tenantId);
~~~

Wrapper generic `Document` giúp nhìn trực tiếp các key `_id` và `orderCount`. Cách này phù hợp để thử pipeline hoặc xây một adapter rất thấp, nhưng khi output đã cố định, nên đổi thành DTO/record có nghĩa nghiệp vụ.

### 9.5. Phân biệt wrapper với API template

`MongoTemplate.aggregate(...)` thường trả `AggregationResults<T>` trực tiếp:

~~~java
AggregationResults<StateSummary> results =
    template.aggregate(
        aggregation,
        "orders_repository_agg_demo_003",
        StateSummary.class
    );
~~~

`@Aggregation` trên repository có thể **bóc một scalar hoặc danh sách** giúp caller đơn giản, nhưng cũng hỗ trợ trả chính `AggregationResults<T>` khi bạn cần thông tin thô. Cả hai dùng MongoDB aggregation bên dưới; khác nhau ở vị trí khai báo pipeline và cách chọn hợp đồng return type.

## 10. Các giới hạn `Sort`, `Pageable`, `Slice` và `Page`

### 10.1. `Sort` được nối vào cuối pipeline

Một repository method có thể nhận tham số `Sort`:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', " +
        "'orderCount': { '$sum': 1 }, " +
        "'grossVnd': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'state': '$_id', " +
        "'orderCount': 1, 'grossVnd': 1 } }"
})
List<StateSummary> summarizeSorted(
    String tenantId,
    org.springframework.data.domain.Sort sort
);
~~~

Gọi:

~~~java
List<StateSummary> topFirst = repository.summarizeSorted(
    "t01",
    Sort.by(Sort.Order.desc("grossVnd"))
);
// PAID, NEW, CANCELLED.
~~~

Spring Data nối `$sort` theo tham số vào **cuối pipeline annotation**. Quan trọng: `Sort` được ánh xạ theo **return type** (`StateSummary`), không chỉ theo `OrderDocument` đầu vào.

### 10.2. Alias đầu ra và `@Id` trên return type

Tài liệu Spring Data nêu ví dụ nếu return DTO có field `lastname` gắn `@Id`, `Sort.by("lastname")` có thể được dịch sang `$sort` trên `_id` của kết quả nhóm. Vì vậy:

- Nếu output đã tạo alias `grossVnd`, sort theo `grossVnd`.
- Nếu muốn sort theo `state`, bảo đảm output thực sự có `state`.
- Nếu DTO đánh dấu `@Id` lên một field nhận `_id` của group, xác nhận tên BSON sau mapping trước khi chấp nhận sort.

Đừng viết `Sort.by("amountVnd")` chỉ vì entity nguồn có property ấy nếu output sau `$group` chỉ còn `grossVnd`.

### 10.3. `Pageable` bổ sung sort, skip và limit vào cuối pipeline

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', " +
        "'orderCount': { '$sum': 1 }, " +
        "'grossVnd': { '$sum': '$amountVnd' } } }",
    "{ '$project': { '_id': 0, 'state': '$_id', " +
        "'orderCount': 1, 'grossVnd': 1 } }"
})
org.springframework.data.domain.Slice<StateSummary> summarizeSlice(
    String tenantId,
    org.springframework.data.domain.Pageable pageable
);
~~~

Gọi:

~~~java
var slice = repository.summarizeSlice(
    "t01",
    org.springframework.data.domain.PageRequest.of(
        0, 2,
        Sort.by(Sort.Order.asc("state"))
    )
);

// Trang đầu có tối đa 2 nhóm; slice.hasNext() cho biết còn nhóm tiếp.
~~~

`Pageable` tác động đến **output sau các stage đã khai báo**, nên nếu pipeline đã group theo state thì nó phân trang **các nhóm**, không phân trang đơn hàng gốc. Nếu bạn muốn “chỉ đọc 100 order đầu rồi mới group”, cần đặt `$limit` **trước `$group`** có chủ đích — và phải chấp nhận kết quả thống kê chỉ trên tập con đó.

### 10.4. `@Aggregation` không hỗ trợ `Page<T>`

**Không khai báo**:

~~~java
// KHÔNG ĐƯỢC hỗ trợ đối với repository @Aggregation:
// @Aggregation(...)
// Page<StateSummary> summarizePage(
//     String tenantId, Pageable pageable);
~~~

Spring Data MongoDB documentation quy định: repository methods dùng `@Aggregation` **không hỗ trợ kiểu trả `Page`**. Có thể nhận `Pageable` nhưng chọn `Slice<T>`, `List<T>` hoặc loại phù hợp khác.

Vì sao? `Page` cần **totalElements / totalPages**; với aggregation có `$group`, `$unwind`, `$facet`, các stage biến đổi output và làm cho một count query tự sinh không đơn giản. Nếu UI thật sự cần tổng số **nhóm** sau pipeline, hãy thiết kế pipeline riêng để đếm số nhóm hoặc dùng `$facet`/`MongoTemplate`, rồi tạo một page DTO ở tầng service theo hợp đồng đã xác định.

### 10.5. Đừng đánh đồng count order và count nhóm

`t01` có **6 order**, nhưng pipeline `$group` theo state trả **3 nhóm**. Nếu user hỏi “trang 1 / tổng 3 trạng thái”, `totalElements` phải là 3 nhóm, không phải 6 order. Đây là một lý do phải làm rõ **đơn vị đang phân trang** trước khi nghĩ tới metadata total.

## 11. `Stream<T>`: tiêu thụ kết quả theo cursor

Repository aggregation có thể trả `Stream<StateSummary>`:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$project': { '_id': 0, 'state': 1, " +
        "'amountVnd': 1 } }"
})
java.util.stream.Stream<org.bson.Document> streamProjected(
    String tenantId
);
~~~

Để xử lý:

~~~java
try (var stream = repository.streamProjected("t01")) {
    stream.forEach(row -> {
        // Đọc từng document kết quả; không giữ cả tập trong một List lớn.
        System.out.println(row);
    });
}
~~~

**Luôn đóng Stream** sau khi đọc: stream có thể dựa trên MongoDB cursor phía server, và giữ mở sẽ tốn tài nguyên kết nối/cursor. Nếu thực tế chỉ có ba nhóm, `List<StateSummary>` đơn giản hơn; stream thường có ích khi pipeline trả số lượng result lớn.

Không dùng `stream.toList()` rồi tuyên bố đã tiết kiệm bộ nhớ: thao tác đó lại materialize toàn bộ output. Khi stream có khả năng dài, cần giới hạn tốc độ xử lý, timeout, retry/checkpoint và logging phù hợp.

### 11.1. Stream không có nghĩa là `$match`/`$group` miễn phí

Pipeline vẫn phải thực hiện các stage trên server. `$group` hoặc `$sort` có thể là blocking stage và tiêu tốn tài nguyên trước khi phát result. Stream chỉ kiểm soát **cách client tiêu thụ output**, không tự tối ưu công việc của server.

## 12. Reactive repository và kiểu kết quả

`ReactiveMongoRepository` hỗ trợ `@Aggregation` với kiểu reactive:

~~~java
package com.example.repositoryagg;

import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0 } }",
        "{ '$group': { '_id': '$state', " +
            "'orderCount': { '$sum': 1 }, " +
            "'grossVnd': { '$sum': '$amountVnd' } } }",
        "{ '$project': { '_id': 0, 'state': '$_id', " +
            "'orderCount': 1, 'grossVnd': 1 } }"
    })
    Flux<StateSummary> summarizeByState(String tenantId);

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'state': ?1 } }",
        "{ '$group': { '_id': null, " +
            "'total': { '$sum': '$amountVnd' } } }",
        "{ '$project': { '_id': 0, 'total': 1 } }"
    })
    Mono<Long> totalAmountForState(
        String tenantId, OrderState state
    );
}
~~~

`Flux<StateSummary>` phát nhiều nhóm; `Mono<Long>` phát không quá một scalar. Khi không có kết quả (ví dụ tenant t99 không có order), `Mono` có thể hoàn tất rỗng:

~~~java
Mono<Long> total = reactiveRepository
    .totalAmountForState("t99", OrderState.PAID)
    .defaultIfEmpty(0L);
~~~

Publisher chỉ thực thi khi có subscriber. Đừng gọi `block()` trong event loop của WebFlux. Reactive không thay đổi **shape BSON** của `$group`/`$project`, không tự thêm total count và không làm sort/group lớn rẻ hơn.

### 12.1. `Mono<Page<T>>` không được hỗ trợ trong reactive repository

Nếu cần phân trang reactive, dùng `Pageable` để giới hạn result của `Flux` theo những trường hợp framework hỗ trợ, hoặc thiết kế cửa sổ/cursor riêng. Không tự tạo `Mono<Page<T>>` từ annotation rồi mong framework tự thực hiện count aggregation bên dưới.

## 13. `@Meta`: tùy chọn tài nguyên cho aggregation

Aggregation lớn có thể cần giới hạn thời gian, comment để theo dõi hoặc cho phép dùng disk:

~~~java
import org.springframework.data.mongodb.repository.Meta;

@Meta(allowDiskUse = "true", maxExecutionTimeMs = 10_000)
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0 } }",
    "{ '$group': { '_id': '$state', " +
        "'orderCount': { '$sum': 1 } } }"
})
List<org.bson.Document> countWithOptions(String tenantId);
~~~

`allowDiskUse` và `maxExecutionTimeMs` là **options**, không quyết định hình dạng DTO/scalar. Chỉ bật `allowDiskUse` khi workload thực sự cần và đã đánh giá tài nguyên; đừng coi disk spill là cách chữa sai index, pipeline không cần thiết hoặc input thiếu filter tenant.

`@Meta` còn có `comment` để gắn thông tin chẩn đoán. Không đưa PII, token hoặc dữ liệu nhạy cảm vào comment/log.

## 14. Khi nào chuyển sang `MongoTemplate.aggregate`?

`@Aggregation` rất phù hợp cho pipeline tương đối ổn định, tiêu chí ít thay đổi và return type rõ ràng. Nếu pipeline dài, có nhiều nhánh có điều kiện, cần type-safe DSL, logic phức tạp hoặc phải kiểm soát các tùy chọn khác, dùng `MongoTemplate`/`MongoOperations`.

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

// template được inject trong service/fragment:
Aggregation pipeline = Aggregation.newAggregation(
    OrderDocument.class,
    Aggregation.match(
        Criteria.where("tenantId").is("t01")
            .and("state").is(OrderState.PAID)
    ),
    Aggregation.group()
        .sum("amountVnd").as("total"),
    Aggregation.project("total")
        .andExclude("_id")
);

AggregationResults<TotalAmount> results =
    template.aggregate(pipeline, TotalAmount.class);

TotalAmount total = results.getUniqueMappedResult();
~~~

Khi dùng typed aggregation như trên, input entity `OrderDocument` giúp Spring Data ánh xạ `tenantId`/`state`/`amountVnd` sang BSON theo `@Field` trong các DSL operation phù hợp. `TotalAmount.class` là **output type**.

### 14.1. Những nhu cầu template diễn đạt tốt hơn

- Tạo `Criteria` động theo những filter nghiệp vụ tùy chọn.
- Dùng `AggregationOptions.strictMapping()` khi muốn kiểm tra property input chặt chẽ.
- Xây nhiều pipeline tương tự với một số stage tái sử dụng.
- Chạy `$facet` để lấy data và count trong một báo cáo có ngữ nghĩa được xác định.
- Tùy chỉnh `AggregationOperation` và kiểm tra pipeline BSON.
- Dùng `aggregateStream` cho output lớn trong workflow phù hợp.

Một custom repository fragment có thể dùng `MongoOperations` để vẫn cung cấp giao diện repository ổn định cho service.

### 14.2. Không lẫn template `AggregationResults` với repository `Page`

`AggregationResults<T>` **không phải** `Page<T>`. Nó chứa mapped results và raw response, **không tự có** `totalElements` hay `totalPages`. Nếu UI muốn một Page thật, service phải cung cấp count theo **đúng đơn vị output** và tính toán metadata/consistency rõ ràng.

## 15. Mapping `@Field`, alias và DTO: các lỗi khó thấy

### 15.1. Input mapping và output alias là hai việc

Entity:

~~~java
@Field("amount_vnd")
private long amountVnd;
~~~

Pipeline:

~~~javascript
{ $group: { _id: null, total: { $sum: "$amountVnd" } } }
~~~

Khi mapping input reference được áp dụng, Spring Data dùng field BSON `amount_vnd`. Nhưng tên `total` là **alias do aggregation tạo**, không được tự đổi sang `amount_vnd`.

Output DTO:

~~~java
public record TotalAmount(Long total) { }
~~~

đọc giá trị alias `total`. Đừng đặt record `TotalAmount(Long amountVnd)` rồi kỳ vọng mapper tự hiểu `amountVnd` có nghĩa giống `total`.

### 15.2. Alias ở cuối pipeline quan trọng hơn tên field gốc

Pipeline:

~~~javascript
[
  { $group: { _id: "$state_code", grossVnd: { $sum: "$amount_vnd" } } },
  { $project: { _id: 0, state: "$_id", grossVnd: 1 } }
]
~~~

Output chỉ có `state` và `grossVnd`. Không còn `state_code` hay `amount_vnd` như field trực tiếp. Một Sort parameter ở repository phải nói về **output type**, ví dụ `Sort.by("grossVnd")`.

### 15.3. Raw `Document` dùng để xác định lỗi ở đâu

Khi record nhận null:

1. Tạm thử method trả `AggregationResults<org.bson.Document>`.
2. Kiểm tra `getMappedResults()` có đúng field/kiểu BSON không.
3. So sánh pipeline `mongosh` và câu lệnh thực mà driver gửi.
4. Nếu BSON đúng, sửa DTO constructor/alias/converter.
5. Nếu BSON sai, sửa `$match`/`$group`/`$project` và cách mapping property.

Không sửa bằng cách đổi hàng loạt sang `Map<String,Object>` hoặc bật conversion mơ hồ để che lỗi. Một read DTO tốt nên có contract trường rõ ràng.

### 15.4. `_id` của `$group` khác `_id` của order

Trước `$group`:

~~~javascript
{ _id: "o701", state_code: "PAID", amount_vnd: 120000 }
~~~

Sau `$group` theo trạng thái:

~~~javascript
{ _id: "PAID", grossVnd: 1250000 }
~~~

Từ đây, `_id` không còn nghĩa là order ID. Nếu DTO có `String id` và không quan tâm semantics, người đọc code rất dễ hiểu nhầm. Dùng alias `state` hoặc `groupKey` để chỉ rõ ý nghĩa.

### 15.5. Numeric overflow và kiểu mapping

Tổng tiền lớn có thể vượt giới hạn `int`; luôn chọn kiểu kết quả phù hợp, ít nhất `long/Long` nếu dữ liệu là số nguyên 64-bit. Với `$avg`, output thường có kiểu số thực/decimal tùy dữ liệu; không khai báo `Long` nếu nghiệp vụ cần giữ phần thập phân.

Nếu dùng `BigDecimal`, xác minh converter với BSON `Decimal128` và độ chính xác đầu vào; không tin số liệu tài chính chỉ vì một test nhỏ cho ra kết quả đúng.

## 16. Bảo mật, quyền truy cập và chi phí aggregation

`@Aggregation` không tự thêm tenant/authorization. Nếu bỏ `tenantId` khỏi `$match`:

~~~javascript
[
  { $match: { state_code: "PAID" } },
  { $group: { _id: null, total: { $sum: "$amount_vnd" } } }
]
~~~

thì tổng trên fixture là **2.150.000 VND** vì gồm cả `o705` thuộc t02:

\[
1250000 + 900000 = 2150000
\]

Một báo cáo tổng sai không chỉ là lỗi số học mà còn là **rò thông tin giữa tenant**.

### 16.1. Đưa tenant vào mọi pipeline

Repository method:

~~~java
@Aggregation(pipeline = {
    "{ '$match': { 'tenantId': ?0, 'state': ?1 } }",
    "{ '$group': { '_id': null, " +
        "'total': { '$sum': '$amountVnd' } } }"
})
Long totalForTenantAndState(
    String authorizedTenantId,
    OrderState state
);
~~~

`authorizedTenantId` phải được xác định ở tầng service từ security context, không tin một chuỗi tenant tùy ý do client gửi.

### 16.2. Giới hạn workload

- Đặt `$match` có chọn lọc sớm, kiểm kế hoạch truy vấn.
- Tạo index theo **field BSON thật**, ví dụ `tenant_id` và `state_code`.
- Cân nhắc `$limit`/`$sort` đúng vị trí, không làm sai kết quả tổng hợp.
- Giới hạn page size và tránh deep offset ở output lớn.
- Dùng `@Meta`/max execution time khi phù hợp; theo dõi p95/p99 và tài nguyên server.
- Không trả raw `AggregationResults.getRawResults()` lên API public hoặc log không lọc.

### 16.3. Lưu ý pipeline `$out` và `$merge`

Aggregation không phải lúc nào cũng chỉ đọc. `$out` và `$merge` có thể **ghi dữ liệu** vào collection đích. Với pipeline có stage ghi, return type `void` có thể được hỗ trợ, nhưng yêu cầu phân quyền, kế hoạch vận hành và test khác hẳn bài toán trả DTO/scalar.

Đừng dùng stage ghi trong một repository analytics public chỉ vì annotation cho phép khai báo raw pipeline.

## 17. Kiểm thử tích hợp trên MongoDB thật

Mock repository trả một `StateSummary` đúng giá trị **không chứng minh**:

- `@Field("amount_vnd")` đã được áp dụng ở pipeline.
- `_id` sau `$group` đã được alias thành `state`.
- `Long` lấy đúng `total` chứ không lấy nhầm count.
- `AggregationResults<T>` thực sự chứa mapped document và raw response.
- Tenant khác không bị tính vào tổng.
- `Slice` có semantics pagination theo nhóm, không phải theo order.

Cần integration test chạy với MongoDB test riêng, ví dụ dùng Testcontainers hoặc một database do test sở hữu.

### 17.1. Ma trận test

| Test | Kỳ vọng |
| --- | --- |
| `summarizeByState("t01")` | 3 nhóm, PAID có 4 order và 1.250.000 VND |
| `totalAmountForState("t01",PAID)` | `1_250_000L` |
| `totalAmountForState("t99",PAID)` | Không có kết quả; service xử lý về 0 nếu quy định |
| `findDistinctStateNames("t01")` | 3 chuỗi CANCELLED, NEW, PAID |
| `totalAmountRaw` | `getMappedResults` có 1, `getUniqueMappedResult` đúng |
| `getUniqueMappedResult` trên 3 nhóm | Báo lỗi nhiều result, không âm thầm chọn đầu |
| DTO record `StateSummary` | Field `state`, `orderCount`, `grossVnd` đúng alias |
| Interface projection | Getter đúng dữ liệu BSON output |
| Sort trên `grossVnd` | PAID đứng đầu khi sort DESC |
| `Slice` size 2 | Có 2 nhóm ở cửa sổ đầu, cờ hasNext đúng |
| Tenant t02 | Không được lọt vào kết quả của t01 |
| Scalar nhiều field kiểu số | Nhận diện mơ hồ, sửa `$project` để chỉ một field |
| Reactive `Mono<Long>` | Subscribe và nhận đúng; hoàn tất rỗng khi không khớp |
| Numeric type BSON | Kiểm tra Long/Decimal128 theo model thực |

### 17.2. Integration test với dữ liệu do test sở hữu

Ví dụ sau dùng ba ID dành riêng cho test: hai order PAID của tenant test và một order PAID thuộc tenant khác.

~~~java
package com.example.repositoryagg;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
class RepositoryAggregationMappingTest {
    @Autowired MongoTemplate template;
    @Autowired OrderRepository repository;

    @Test
    void mapsDtoScalarAndRawResultWithTenantIsolation() {
        List<String> ids = List.of(
            "fixture-ra003-a",
            "fixture-ra003-b",
            "fixture-ra003-other"
        );

        var collection = template.getDb()
            .getCollection("orders_repository_agg_demo_003");

        collection.deleteMany(Filters.in("_id", ids));
        try {
            collection.insertMany(List.of(
                new Document("_id", ids.get(0))
                    .append("tenant_id", "fixture-ra003")
                    .append("state_code", "PAID")
                    .append("amount_vnd", 100000L),
                new Document("_id", ids.get(1))
                    .append("tenant_id", "fixture-ra003")
                    .append("state_code", "PAID")
                    .append("amount_vnd", 200000L),
                new Document("_id", ids.get(2))
                    .append("tenant_id", "other-fixture-ra003")
                    .append("state_code", "PAID")
                    .append("amount_vnd", 900000L)
            ));

            List<StateSummary> rows =
                repository.summarizeByState("fixture-ra003");
            assertThat(rows).hasSize(1);
            assertThat(rows.get(0).state()).isEqualTo("PAID");
            assertThat(rows.get(0).orderCount()).isEqualTo(2L);
            assertThat(rows.get(0).grossVnd()).isEqualTo(300000L);

            Long scalar = repository.totalAmountForState(
                "fixture-ra003", OrderState.PAID);
            assertThat(scalar).isEqualTo(300000L);

            var wrapped = repository.totalAmountRaw(
                "fixture-ra003", OrderState.PAID);
            assertThat(wrapped.getMappedResults()).hasSize(1);
            assertThat(wrapped.getUniqueMappedResult())
                .isNotNull();
            assertThat(wrapped.getUniqueMappedResult().total())
                .isEqualTo(300000L);
            assertThat(wrapped.getRawResults()).isNotNull();
        } finally {
            collection.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

Test này **chỉ phù hợp với MongoDB test biệt lập**. Nó dọn đúng ba fixture ID, tránh xóa dữ liệu không thuộc test. Tên class/package/mapping phải khớp các phần của bài nếu đưa vào project thật; `@DataMongoTest` cần repository/entity nằm trong phạm vi component scan của test configuration.

### 17.3. Test kết quả không có document

~~~java
@Test
void emptyAggregationIsNotImplicitlyZero() {
    Long value = repository.totalAmountForState(
        "tenant-with-no-orders", OrderState.PAID
    );

    // Với query $group trên tập rỗng, không sinh document tổng.
    assertThat(value).isNull();
}
~~~

Đoạn test có thể đặt vào cùng class `RepositoryAggregationMappingTest` khi repository đã inject; tenant test phải bảo đảm không có dữ liệu phù hợp. Với môi trường/sao chép code dùng reactive hoặc `Optional`, kỳ vọng phải được điều chỉnh theo contract của return type.

### 17.4. Test độ nhất quán giữa số và DTO

Khi hai method tính một KPI từ **cùng điều kiện**:

~~~java
Long scalar = repository.totalAmountForState(
    "fixture-ra003", OrderState.PAID);
TotalAmount value = repository.totalAmountWrapped(
    "fixture-ra003", OrderState.PAID);

assertThat(value.total()).isEqualTo(scalar);
~~~

Test này so sánh mapping scalar và wrapper DTO. Nó không đảm bảo hai câu truy vấn có snapshot giống nhau nếu có writer đồng thời; chạy trong fixture test cô lập hoặc dùng yêu cầu nhất quán rõ ràng.

## 18. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| DTO field `state` null | `$group` chỉ trả `_id`, chưa project alias | `$project` từ `_id` sang `state` |
| DTO `grossVnd=0` nhưng BSON có giá trị | Alias sai, kiểu số không tương thích hoặc constructor mismatch | Xem `AggregationResults<Document>` và DTO mapping |
| Scalar trả sai số | Output có nhiều field numeric, mapper chọn một giá trị khác | Project đúng một field, exclude `_id` |
| Scalar null khi không có order | `$group` trên tập rỗng không xuất document | Dùng `Long`/`Optional` và default 0 ở service |
| Trả một `StateSummary` nhưng pipeline tạo 3 nhóm | Mismatch cardinality một-nhiều | Trả `List/Flux` hoặc thêm `$sort` + `$limit` có chủ đích |
| `getUniqueMappedResult()` ném lỗi | Có hơn một mapped result | Dùng `getMappedResults()` hoặc giới hạn pipeline |
| `Sort.by("amountVnd")` sau group không đúng | Sort mapping dựa trên output, không còn field nguồn | Dùng `grossVnd` hoặc alias thực của DTO |
| `Page<StateSummary>` không hoạt động | `Page` không được hỗ trợ cho `@Aggregation` | Dùng `Slice` hoặc tự thiết kế count với template |
| Page size 2 lại có 2 **nhóm**, không phải 2 **order** | Pageable nối sau `$group` | Quyết định rõ pagination trước/sau group |
| Thiếu dữ liệu tenant khác làm tổng sai | `$match` thiếu tenant | Ràng buộc tenant từ security context |
| `@Field` không có tác dụng như dự kiến | Raw BSON/tên field hoặc alias không được map theo domain | Kiểm input entity và pipeline BSON đã thực thi |
| Raw response có metadata khó hiểu | `getRawResults()` là driver response, không phải DTO | Không trả thẳng raw; đọc mapped results |
| Stream chiếm tài nguyên | Không đóng `Stream`/server cursor | `try-with-resources` |
| Reactive không trả dữ liệu | Publisher chưa subscribe | Compose `Flux/Mono` vào chain/StepVerifier |
| Aggregation chậm dù trả 1 scalar | `$group`/`$sort` vẫn xử lý tập lớn | Index, explain, filter, giới hạn workload |
| Số tiền sai phần lẻ | Dùng `double` cho tiền tệ/loại BSON không phù hợp | `Decimal128`/`BigDecimal` hoặc số nguyên theo đơn vị nhỏ nhất |

## 19. Checklist chọn return type

1. **Xác định output của stage cuối**: một document hay nhiều document, những field nào và kiểu BSON gì?
2. **Đưa input metadata vào repository** bằng `OrderDocument` và dùng `@Field` nhất quán.
3. **Trả DTO/record** khi output có nhiều field mang ngữ nghĩa (state, count, sum).
4. **Dùng interface projection** khi chỉ cần getter đơn giản trên output document.
5. **Trả `Long`/`String` scalar** khi mỗi output document chỉ có **một field cần lấy**.
6. **Dùng `List<Scalar>`** khi pipeline tạo nhiều output document, mỗi document đại diện một giá trị.
7. **Dùng `AggregationResults<T>`** khi cần mapped results và raw response để phân tích/kiểm chứng.
8. **Không dùng `getUniqueMappedResult()`** cho pipeline có thể tạo hơn một nhóm.
9. **Xử lý kết quả rỗng**, không tin tổng luôn bằng 0 nếu không có document input.
10. **Sort theo output type và alias**, đặc biệt sau `$group`/`$project`.
11. **Dùng `Slice` thay `Page`** trên repository `@Aggregation`; tự thiết kế total count khi nghiệp vụ yêu cầu.
12. **Đóng Stream**, không materialize số lượng không giới hạn vào heap.
13. **Kiểm tenant, index và tài nguyên**, đừng xem aggregation chỉ đọc vì `$out`/`$merge` có thể ghi.
14. **Integration test BSON thật** cho DTO, scalar, wrapper, alias, null/missing và kiểu số.

## 20. Bài thực hành

Mỗi bài dưới đây dựa trên fixture mục 2, chưa có thay đổi từ writer khác.

### Bài 1 — Chọn kiểu DTO

Pipeline group theo state tạo `{state:"PAID",orderCount:4,grossVnd:1250000}`. Trả `Long` có hợp lý không?

**Đáp án:** Không nếu ứng dụng cần cả ba field. Dùng `StateSummary` record/class hoặc interface projection. `Long` chỉ hợp lý khi pipeline project đúng một giá trị cần lấy.

### Bài 2 — Khóa nhóm `_id`

Kết quả `$group`:

~~~javascript
{ _id: "PAID", orderCount: 4, grossVnd: 1250000 }
~~~

`_id` có phải `o701` của order không?

**Đáp án:** Không. Nó là **khóa nhóm** `"PAID"`. Tạo `$project: {state:"$_id",_id:0,...}` để DTO có field `state` rõ nghĩa.

### Bài 3 — Tổng scalar

Với t01/PAID, `Long totalAmountForState(...)` cần trả gì?

**Đáp án:** `1_250_000L`. Pipeline nên kết thúc bằng `{ $project: { _id:0,total:1 } }` sau `$group`.

### Bài 4 — Không có order

Tenant t99 không có order PAID. `$group` mặc nhiên sinh `{total:0}` không?

**Đáp án:** Không. Có thể không có result document, method nhận `null`/empty tùy return type. Quy đổi về 0 ở service nếu đó là hợp đồng nghiệp vụ.

### Bài 5 — Scalar mơ hồ

Nếu pipeline trả `{orders:4,total:1250000}` và method khai báo `Long`, điều gì bất ổn?

**Đáp án:** Có hai giá trị số; mapper có quy tắc trích nhưng mục tiêu nghiệp vụ **không rõ**. Project chỉ `total` hoặc trả DTO gồm cả `orders` và `total`.

### Bài 6 — List scalar

Muốn lấy danh sách tên trạng thái của t01, không cần count, chọn `List<String>` hay `String`?

**Đáp án:** `List<String>`, với pipeline tạo một document một field cho từng trạng thái; kết quả CANCELLED, NEW, PAID.

### Bài 7 — `AggregationResults`

`getMappedResults()`, `getUniqueMappedResult()` và `getRawResults()` khác nhau thế nào?

**Đáp án:** Lần lượt là danh sách object đã map, object duy nhất khi có tối đa một result, và response BSON thô của driver/server. `getUniqueMappedResult()` báo lỗi nếu có hơn một result.

### Bài 8 — `Sort` sau pipeline

Output DTO có `grossVnd` nhưng entity gốc là `amountVnd`. Nên truyền `Sort.by("grossVnd")` hay `Sort.by("amountVnd")`?

**Đáp án:** `grossVnd` vì Sort parameter của repository aggregation được áp vào **cuối pipeline** và ánh xạ theo **return type**.

### Bài 9 — Pagination

Một pipeline nhóm đơn hàng thành ba trạng thái. `Pageable.ofSize(2)` đặt vào repository `@Aggregation` sẽ phân trang gì?

**Đáp án:** **Nhóm sau aggregation**, vì sort/skip/limit được thêm vào cuối pipeline. Với `@Aggregation` không khai báo return type `Page<T>`; dùng `Slice<T>` nếu cần `hasNext`.

### Bài 10 — Count đúng đơn vị

Tenant t01 có sáu đơn nhưng ba trạng thái. Nếu UI đang hiển thị bảng **nhóm theo state**, tổng số item là bao nhiêu?

**Đáp án:** **3 nhóm**, không phải 6 order. Nếu cần `Page` thủ công, phép count phải đếm output sau `$group`.

### Bài 11 — Giữ raw data

DTO trả `grossVnd=0` nhưng raw MongoDB có `grossVnd: NumberLong(1250000)`. Nên điều tra ở đâu?

**Đáp án:** Kiểm alias, tên component constructor và converter/output type; có thể tạm trả `AggregationResults<Document>` để xác minh shape/kiểu BSON.

### Bài 12 — Bảo vệ tenant

Vì sao tổng PAID không có `tenantId` có thể thành 2.150.000 VND?

**Đáp án:** Đã cộng thêm `900.000` của tenant t02. `@Aggregation` không tự lọc tenant; điều kiện phải được đưa vào `$match` từ security context.

### Bài 13 — Reactive scalar

Một `Mono<Long>` từ repository aggregation cho tenant không có order phát giá trị `0L` mặc định không?

**Đáp án:** Không. Nó có thể hoàn tất rỗng; dùng `defaultIfEmpty(0L)` nếu service muốn quy định zero. Không gọi `block()` trên event loop.

### Bài 14 — Hiệu năng

Một pipeline `$group` trả một `Long` nhưng vẫn chậm. Tại sao?

**Đáp án:** Return type chỉ thay **cách map output**; server vẫn phải lọc/tổng hợp nhiều document. Kiểm index cho tenant/state, explain, tài nguyên group/sort và thời gian chạy, không tối ưu bằng đổi DTO thành scalar.

## Tài liệu tham khảo

- [Spring Data MongoDB — MongoDB-specific Query Methods, Aggregation Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): `@Aggregation`, placeholders, DTO/scalar, `AggregationResults`, Stream, Sort/Pageable/Slice và giới hạn `Page`.
- [Spring Data MongoDB — `@Aggregation` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/repository/Aggregation.html): chú thích pipeline, mapping field, các tham số.
- [Spring Data MongoDB — `AggregationResults<T>` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/AggregationResults.html): `getMappedResults()`, `getRawResults()`, `getUniqueMappedResult()` và `getServerUsed()`.
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html): typed aggregation, aggregation operations, alias, mapping và MongoTemplate.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `@Field`, `@MongoId`, converter, DTO/record mapping.
- [Spring Data MongoDB — `@Meta` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/repository/Meta.html): `allowDiskUse`, `maxExecutionTimeMs` và comment.
- [MongoDB Manual — `$group`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/): nhóm và accumulator.
- [MongoDB Manual — `$project`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/): alias, giữ/loại `_id`, output shape.
- [MongoDB Manual — `$sum`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sum/): tính tổng, kiểu số và accumulator.
- [MongoDB Manual — Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/): thứ tự stage và dữ liệu trung gian.
- [MongoDB Manual — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/): khả năng tối ưu pipeline và phân tích hiệu năng.
