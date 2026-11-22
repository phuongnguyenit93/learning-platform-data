# Thực thi aggregation, bulkWrite và đọc kết quả theo lô

Trong ứng dụng Java dùng MongoDB, rất nhiều bài toán không dừng ở `findOne()` hoặc `insertOne()`. Một hệ thống thực tế thường phải:

- Lọc, nhóm, tính tổng và sắp xếp hàng triệu document bằng **aggregation pipeline**.
- Cập nhật hoặc chèn nhiều document trong một đợt bằng **`bulkWrite()`**.
- Đọc một tập kết quả lớn mà không tải toàn bộ vào JVM bằng **cursor và batch**.
- Biến đổi dữ liệu từ collection nguồn sang collection đích, vừa đọc vừa ghi, có thể khởi chạy lại khi một job thất bại.
- Theo dõi latency, lỗi từng thao tác, số record xử lý, thời gian chờ kết nối và khả năng phục hồi.

Ba kỹ thuật này có quan hệ mật thiết: **aggregation tạo dữ liệu**, **cursor chuyển dữ liệu từng phần**, còn **bulkWrite ghi dữ liệu hiệu quả hơn so với nhiều round trip riêng lẻ**. Tuy nhiên, chúng không thay thế cho nhau, cũng không tự giải quyết tính đúng đắn, khả năng retry hoặc nhất quán dữ liệu.

Bài học **“Thực thi aggregation, bulkWrite và đọc kết quả theo lô”** trong chương **Java Driver** hướng dẫn cách dùng **MongoDB Java Sync Driver** với ví dụ Java, BSON builders, quản lý tài nguyên, tối ưu hiệu năng, xử lý lỗi và một bài toán chuyển dữ liệu có thể vận hành được.

> **Ba điều cần ghi nhớ ngay:** `aggregate()` trả về một đối tượng kết quả được đánh giá khi tiêu thụ; `batchSize()` là gợi ý về số document server gửi theo một lần lấy dữ liệu, không giới hạn tổng số kết quả; và `bulkWrite()` là nhóm thao tác ghi, **không mặc nhiên là một transaction nguyên tử cho cả nhóm**.

---

## 1. Bức tranh tổng thể

Một luồng Java xử lý dữ liệu có thể trông như sau:

```text
MongoDB collection: orders
          │
          ▼
Java Sync Driver
          │
          ▼
aggregate(pipeline)
          │
          ▼
AggregateIterable<Document>
          │
          ▼
MongoCursor<Document>
  ├── batch từ server #1
  ├── getMore / batch #2
  ├── getMore / batch #3
  └── ...
          │
          ▼
Java transformation / validation
          │
          ▼
List<WriteModel<Document>>
          │
          ├── Đủ 500 thao tác → bulkWrite(...)
          ├── Đủ 500 thao tác → bulkWrite(...)
          └── Còn 147 thao tác → bulkWrite(...)
          │
          ▼
MongoDB collection: orderSummaries
```

Tại đây có **hai loại batch khác nhau**:

1. **Read batch**: do MongoDB server và cursor protocol điều khiển, chịu ảnh hưởng bởi `batchSize()` và giới hạn kích thước phản hồi.
2. **Write batch**: do ứng dụng gom các `WriteModel` rồi gọi `bulkWrite()`, sau đó driver có thể phân chia các lệnh thực tế để tuân thủ giới hạn giao thức/server.

Không có quy tắc bắt buộc rằng read batch size và write batch size phải bằng nhau.

## 2. Chọn API phù hợp

| Nhu cầu | API Java Sync Driver | Đặc điểm |
|---|---|---|
| Tìm một document | `find(...).first()` | Đơn giản, trả một kết quả hoặc `null` |
| Đọc nhiều documents | `find(...)` + `MongoCursor` | Duyệt dần theo cursor |
| Tổng hợp dữ liệu | `aggregate(pipeline)` | Lọc, nhóm, tính toán, join, chuyển đổi |
| Nhận kết quả aggregation | `AggregateIterable<T>` | Duyệt, giới hạn, batch, timeout |
| Insert nhiều documents đơn thuần | `insertMany()` | Chèn danh sách cùng loại thao tác |
| Nhiều dạng ghi trong một đợt | `bulkWrite(models, options)` | Insert/update/replace/delete |
| Cập nhật một document | `updateOne()` | Dễ quản lý kết quả cho một thao tác |
| Ghi theo logic ngay trên server | `$merge` / `$out` | Stage cuối của aggregation có ghi |
| Theo dõi thay đổi liên tục | `watch()` / change streams | Luồng sự kiện, khác batch scan |
| Transaction nhiều documents | `ClientSession` / transaction API | Atomicity với điều kiện hỗ trợ |

Câu hỏi chọn API không chỉ là “cái nào nhanh nhất?” mà còn là **kết quả cần xử lý ở đâu, số round trip bao nhiêu, mức nhất quán nào cần thiết và khi lỗi thì tiếp tục ra sao**.

## 3. Chuẩn bị môi trường Java

Ví dụ dùng **MongoDB Java Sync Driver**. Chọn một phiên bản driver được nhà cung cấp hỗ trợ với MongoDB Server đang chạy; các API dưới đây sử dụng phong cách driver 5.x.

### 3.1. Maven

```xml
<dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>${mongodb.driver.version}</version>
</dependency>
```

`mongodb.driver.version` là property của dự án, phải được khai báo thành một phiên bản cụ thể đã được kiểm tra tính tương thích. Không điền một version tùy ý chỉ vì ví dụ sử dụng driver 5.x.

### 3.2. Gradle

```groovy
dependencies {
    implementation "org.mongodb:mongodb-driver-sync:${mongoDriverVersion}"
}
```

`mongoDriverVersion` là biến cấu hình của build. Cách viết này chỉ minh họa dependency, không yêu cầu chạy Gradle để thực hiện bài học.

### 3.3. Connection string

Tạo cấu hình connection trong secret manager hoặc biến môi trường:

```text
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster-host>/
```

Giá trị trên là cấu trúc minh họa, không phải URI có thể kết nối thật. Production phải cấu hình TLS, network access, RBAC và database users phù hợp.

Không:

- Hardcode password vào source;
- Commit `.env` chứa secrets;
- Ghi nguyên URI vào logs;
- Tắt xác minh certificate/hostname để “khắc phục” lỗi TLS.

### 3.4. Khởi tạo client

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import org.bson.Document;

public class MongoSetup {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is not configured");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("demo_orders");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            System.out.println(
                "Connected collection: " + orders.getNamespace()
            );
        }
    }
}
```

Trong web service, nên dùng **một `MongoClient` dùng chung theo lifecycle ứng dụng**, không tạo và đóng client trong mỗi HTTP request. `MongoClient` quản lý pools, monitoring và topology discovery.

## 4. Dữ liệu mẫu và yêu cầu bài toán

Collection `demo_orders.orders` chứa:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T-01",
  customerId: "C-105",
  status: "PAID",
  amountCents: NumberLong("249900"),
  createdAt: ISODate("2026-11-10T08:30:00Z"),
  updatedAt: ISODate("2026-11-10T08:31:00Z"),
  channel: "WEB",
  tags: ["priority", "gift"]
}
```

Những documents khác:

```javascript
{
  _id: "ORD-1002",
  tenantId: "T-01",
  customerId: "C-105",
  status: "PAID",
  amountCents: NumberLong("100000"),
  createdAt: ISODate("2026-11-11T09:00:00Z"),
  channel: "APP"
}
```

```javascript
{
  _id: "ORD-1003",
  tenantId: "T-02",
  customerId: "C-205",
  status: "CANCELLED",
  amountCents: NumberLong("350000"),
  createdAt: ISODate("2026-11-11T10:00:00Z"),
  channel: "WEB"
}
```

Bài toán gồm ba phần:

1. Tính **tổng doanh thu đã thanh toán theo khách hàng** trong một khoảng ngày.
2. Đọc các kết quả một cách **giới hạn bộ nhớ**.
3. Ghi hoặc cập nhật collection `customerRevenue` theo từng nhóm bằng **bulk upsert**.

Sử dụng tiền nguyên đơn vị nhỏ nhất (`amountCents`) để tránh các sai số của `double` trong ví dụ. Ở hệ thống tài chính thực tế, có thể dùng `Decimal128`, `BigDecimal` và quy tắc xử lý tiền tệ chặt chẽ hơn.

### 4.1. Các index ứng viên

Một index phục vụ lọc dữ liệu:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: 1,
  customerId: 1
});
```

Đây chỉ là **ứng viên**: cần xem query shapes, `explain("executionStats")`, cardinality và read/write cost. Không tạo index trên production chỉ vì nó xuất hiện trong ví dụ.

## 5. Aggregation pipeline là gì?

Aggregation pipeline là danh sách các **stages** chạy lần lượt trên tập documents. Mỗi stage nhận stream đầu vào, xử lý và chuyển stream sang stage tiếp theo.

```text
orders
  │
  ▼
$match      lọc tenant/status/date
  │
  ▼
$group      gom theo customerId
  │
  ▼
$project    chuẩn hóa fields kết quả
  │
  ▼
$sort       sắp theo tổng doanh thu
  │
  ▼
$limit      lấy top N khách hàng
  │
  ▼
aggregation result
```

Một pipeline có thể có stages:

| Stage | Mục đích |
|---|---|
| `$match` | Lọc documents |
| `$project` | Chọn/biến đổi fields |
| `$group` | Nhóm và tính tổng |
| `$sort` | Sắp xếp |
| `$limit` | Giới hạn số kết quả |
| `$skip` | Bỏ qua một số kết quả |
| `$unwind` | Tách phần tử array thành documents |
| `$lookup` | Kết hợp dữ liệu từ collection khác |
| `$set` / `$addFields` | Thêm/chỉnh fields |
| `$facet` | Chạy các nhánh aggregation |
| `$count` | Đếm documents |
| `$merge` | Ghi kết quả vào collection đích |
| `$out` | Ghi kết quả ra collection theo semantics stage |

Một số stages có yêu cầu vị trí và phiên bản; không thể hoán đổi thứ tự tùy tiện.

## 6. Viết pipeline trực tiếp bằng `Document`

Java Driver chấp nhận các `Bson` stages. `org.bson.Document` là một cách mô tả gần cú pháp MongoDB shell:

```java
import java.util.Arrays;
import java.util.Date;
import java.util.List;

import org.bson.Document;
import org.bson.conversions.Bson;

Date from = new Date(1761955200000L);
Date to = new Date(1764547200000L);

List<Bson> pipeline = Arrays.asList(
    new Document("$match",
        new Document("tenantId", "T-01")
            .append("status", "PAID")
            .append("createdAt",
                new Document("$gte", from).append("$lt", to))
    ),

    new Document("$group",
        new Document("_id", "$customerId")
            .append("grossCents",
                new Document("$sum", "$amountCents"))
            .append("orderCount",
                new Document("$sum", 1))
    ),

    new Document("$sort",
        new Document("grossCents", -1)
    ),

    new Document("$limit", 50)
);
```

Khoảng ngày ở đây minh họa timestamp bằng milliseconds Unix. Trong ứng dụng nên dùng `Instant`/`Date.from(instant)` rõ timezone; `to` thường chọn dạng **exclusive** để tránh đếm trùng biên.

### 6.1. Ý nghĩa từng stage

1. `$match`: chỉ lấy đơn hàng tenant T-01, đã thanh toán, thuộc khoảng ngày.
2. `$group`: nhóm theo khách hàng và tính tổng cents, đếm số order.
3. `$sort`: sắp giảm theo tổng doanh thu.
4. `$limit`: lấy nhiều nhất 50 khách hàng.

Output có dạng:

```javascript
{
  _id: "C-105",
  grossCents: NumberLong("349900"),
  orderCount: 2
}
```

Kết quả `grossCents` phụ thuộc dữ liệu đầu vào và quy tắc accumulator. Không giả định mọi tổng trong mọi collection luôn là Java `Long`; nếu `Decimal128`, floating-point hoặc overflow được áp dụng, phải xử lý đúng BSON type.

### 6.2. `Document` linh hoạt nhưng dễ sai tên field/operator

Nhược điểm:

- Tên stages/fields là chuỗi, dễ gõ sai;
- Lồng nhiều `Document` khó đọc;
- Không có type safety cho cấu trúc BSON;
- Dễ vô tình lẫn dữ liệu đầu vào không kiểm soát.

Với pipeline phổ biến, MongoDB Java Driver có **builder APIs** giúp biểu đạt ý đồ rõ hơn.

## 7. Dùng builder `Aggregates`, `Filters`, `Accumulators`

Java Driver cung cấp các factory methods:

- `Filters.eq`, `gte`, `lt`, `and`;
- `Aggregates.match`, `group`, `project`, `sort`, `limit`;
- `Accumulators.sum`, `avg`, `max`, `min`;
- `Sorts.ascending`, `descending`;
- `Projections.include`, `excludeId`, `fields`.

Ví dụ:

```java
import java.util.Arrays;
import java.util.Date;
import java.util.List;

import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;

import org.bson.conversions.Bson;

Date from = new Date(1761955200000L);
Date to = new Date(1764547200000L);

List<Bson> pipeline = Arrays.asList(
    Aggregates.match(
        Filters.and(
            Filters.eq("tenantId", "T-01"),
            Filters.eq("status", "PAID"),
            Filters.gte("createdAt", from),
            Filters.lt("createdAt", to)
        )
    ),

    Aggregates.group(
        "$customerId",
        Accumulators.sum("grossCents", "$amountCents"),
        Accumulators.sum("orderCount", 1)
    ),

    Aggregates.sort(
        Sorts.descending("grossCents")
    ),

    Aggregates.limit(50)
);
```

Builder sinh BSON tương ứng với các stages, không thay đổi semantics của MongoDB.

### 7.1. Khi nào dùng builder, khi nào dùng `Document`?

| Tình huống | Lựa chọn |
|---|---|
| Các stages phổ biến, dễ biểu diễn | Builders |
| Stage mới mà driver builder chưa hỗ trợ thuận tiện | `Document` hoặc `BsonDocument` |
| Pipeline được tạo động từ query plan nội bộ | Builders kết hợp `Bson` |
| Query phụ thuộc đầu vào người dùng | Validate và allowlist; không đưa raw BSON |
| Pipeline dài/nhiều branches | Tách thành hàm tạo stages |

Không chấp nhận `request.body` như một pipeline tự do nếu ứng dụng không cho phép khách hàng thực thi tùy ý MongoDB operators.

## 8. Gọi `aggregate()` trong Java

Với collection:

```java
MongoCollection<Document> orders =
    client.getDatabase("demo_orders")
          .getCollection("orders");
```

Thực thi:

```java
import com.mongodb.client.AggregateIterable;

AggregateIterable<Document> result =
    orders.aggregate(pipeline);

for (Document row : result) {
    String customerId = row.getString("_id");
    Object grossCents = row.get("grossCents");
    Number count = (Number) row.get("orderCount");

    System.out.printf(
        "Customer=%s gross=%s count=%d%n",
        customerId,
        grossCents,
        count.longValue()
    );
}
```

Nếu dữ liệu lớn hoặc chứa thông tin nhạy cảm, **không in mọi document vào log production**. Ví dụ dùng dữ liệu doanh thu giả định.

### 8.1. `AggregateIterable` là gì?

`aggregate()` trả về một `AggregateIterable<TResult>` — một đối tượng biểu diễn kết quả aggregation và hỗ trợ các tùy chọn như:

```java
orders.aggregate(pipeline)
    .allowDiskUse(true)
    .batchSize(200)
    .maxTime(30, java.util.concurrent.TimeUnit.SECONDS);
```

Việc thực thi trên server gắn với **tiêu thụ iterable** (ví dụ `iterator()`, vòng `for`, `first()` hoặc `into()`), không phải chỉ cần tạo biến `result`.

Điều này đặc biệt quan trọng với aggregation có `$merge` hoặc `$out`: chỉ tạo `AggregateIterable` mà không tiêu thụ nó có thể khiến pipeline không được gửi để chạy.

### 8.2. Không nhầm builder object với dữ liệu

`AggregateIterable<Document>` **không** phải là `List<Document>` đã nằm hoàn toàn trong RAM. Driver thường dùng cursor để lấy kết quả từ server theo batch khi ứng dụng duyệt.

Nếu muốn lưu toàn bộ kết quả, API `into()` có thể làm được, nhưng phải cân nhắc kích thước.

## 9. `first()`, `into()`, `forEach()` và `iterator()`

Các cách tiêu thụ kết quả:

### 9.1. Lấy kết quả đầu tiên

```java
Document first = orders.aggregate(pipeline).first();

if (first == null) {
    System.out.println("No aggregation result");
}
```

Hữu ích khi kết quả có tối đa một document, chẳng hạn aggregation tổng kết đơn giản. Khi chỉ cần một record trong pipeline nhiều kết quả, cân nhắc `$limit: 1` theo ý đồ.

### 9.2. Gom toàn bộ vào `List`

```java
import java.util.ArrayList;
import java.util.List;
import org.bson.Document;

List<Document> all = orders.aggregate(pipeline)
    .into(new ArrayList<>());
```

Dễ xử lý trong JVM, nhưng nếu pipeline trả vài triệu records thì `List` này có thể ngốn nhiều RAM hoặc gây `OutOfMemoryError`.

### 9.3. Dùng vòng `for`

```java
for (Document row : orders.aggregate(pipeline)) {
    process(row);
}
```

Cú pháp gọn, nhưng khi cần chủ động đóng cursor hoặc xử lý vòng đời phức tạp, nên dùng `MongoCursor`.

### 9.4. Dùng cursor rõ ràng

```java
import com.mongodb.client.MongoCursor;

try (MongoCursor<Document> cursor =
         orders.aggregate(pipeline).iterator()) {

    while (cursor.hasNext()) {
        Document row = cursor.next();
        process(row);
    }
}
```

`MongoCursor` hỗ trợ `close()`; try-with-resources giúp giải phóng cursor ngay cả khi processing throws exception.

**Với tập kết quả lớn, kiểu quản lý cursor này thường dễ kiểm soát tài nguyên hơn việc gọi `into(new ArrayList<>())`.**

## 10. Phân biệt lazy execution và synchronous blocking

**MongoDB Java Sync Driver** là driver đồng bộ. Dù `AggregateIterable` được tiêu thụ lười (*lazy*) và có batching, thread đang gọi `hasNext()`, `next()` hoặc `bulkWrite()` vẫn có thể **chờ I/O**.

```text
AggregateIterable created
        │
        ▼
cursor = iterable.iterator()
        │
        ▼
send aggregate command
        │
        ▼
fetch first batch
        │
        ▼
cursor.next() ...
        │
        ▼
need more docs?
        │
        └── getMore network round trip
```

Lazy không có nghĩa non-blocking/reactive. Nếu service dùng event-loop không cho phép block, phải cân nhắc Reactive Streams Driver hoặc một mô hình thực thi bất đồng bộ phù hợp.

### 10.1. Không dùng `parallelStream()` trực tiếp trên một cursor

`MongoCursor` không phải một concurrent random-access collection. Không chia sẻ cùng cursor cho nhiều threads mà không có cơ chế điều phối được hỗ trợ. Nếu cần xử lý song song:

- Một thread đọc từ cursor;
- Chuyển dữ liệu sang bounded queue;
- Workers xử lý độc lập;
- Có backpressure/cancellation;
- Có chiến lược thứ tự và idempotency.

Tăng concurrency vô hạn có thể làm OOM hoặc nghẽn connection pool.

## 11. `batchSize()` thực sự điều khiển điều gì?

Ví dụ:

```java
AggregateIterable<Document> iterable =
    orders.aggregate(pipeline)
          .batchSize(250);
```

`batchSize(250)` yêu cầu server gửi **số document mục tiêu tối đa hoặc gần mức đó cho một batch**, nhưng còn bị ràng buộc bởi kích thước phản hồi, thời gian và semantics của cursor/stage.

Nó **không**:

- Giới hạn tổng số documents trả về là 250;
- Bảo đảm mọi batch có đúng 250 documents;
- Bảo đảm chỉ có một network request;
- Đổi cách MongoDB tính `$group` hoặc kết quả logic;
- Định nghĩa số thao tác khi ứng dụng gọi `bulkWrite`;
- Tự tạo checkpoint khi JVM crash;
- Bảo đảm memory dùng cố định tuyệt đối bất kể document size.

### 11.1. `batchSize` so với `$limit`

| Tùy chọn | Tác dụng |
|---|---|
| `$limit: 1000` | Pipeline trả tối đa 1.000 results ở vị trí áp dụng |
| `.batchSize(100)` | Kết quả có thể được gửi thành nhiều batch khoảng 100 |
| `find().limit(1000)` | Cursor trả tối đa 1.000 documents |
| `find().batchSize(100)` | Điều chỉnh kích thước batch của find cursor |
| Application buffer 500 | Gom 500 records trong JVM để xử lý/ghi |
| Bulk write list 500 | Một invocation chứa 500 write models |

### 11.2. Ví dụ tính batch gần đúng

Giả sử aggregation tạo 1.250 documents.

```text
batchSize = 250

Batch 1 → ~250 docs
Batch 2 → ~250 docs
Batch 3 → ~250 docs
Batch 4 → ~250 docs
Batch 5 → ~250 docs
```

Số batch thực tế có thể khác vì server message size limits và các điều kiện xử lý. Vì vậy chỉ coi đây là sơ đồ khái niệm, không đặt business logic theo giả định batch luôn có chính xác 250 record.

### 11.3. Trade-off của batch nhỏ và batch lớn

| Batch nhỏ | Batch lớn |
|---|---|
| Giảm số docs giữ tại client mỗi lượt | Giảm số lần network round trips |
| Dễ kiểm soát memory khi docs lớn | Có thể tăng memory pressure |
| Có thể tăng overhead `getMore` | Có thể ảnh hưởng fairness/latency giữa clients |
| Phù hợp stream/processing chậm | Phù hợp consume nhanh, network RTT cao |
| Không sửa query plan | Không sửa query plan |

Không có `batchSize` tối ưu bất biến. Bắt đầu từ số hợp lý rồi đo network, heap, end-to-end duration và `getMore` count.

## 12. `getMore` và vòng đời cursor

Một cursor không nhất thiết chứa toàn bộ kết quả ngay từ đầu. Sau khi ứng dụng đọc hết batch hiện tại, driver có thể gửi **`getMore`** để lấy phần tiếp theo.

```text
aggregate command
    │
    ▼
firstBatch
    │
    ▼
Java consumes documents
    │
    ▼
getMore → nextBatch
    │
    ▼
Java consumes documents
    │
    ▼
getMore → nextBatch
    │
    ▼
cursor exhausted / closed
```

### 12.1. Tại sao cần đóng cursor?

Một cursor có thể có trạng thái phía server và giữ tài nguyên. Nếu dừng sớm:

```java
try (MongoCursor<Document> cursor =
         orders.aggregate(pipeline).iterator()) {

    for (int i = 0; i < 10 && cursor.hasNext(); i++) {
        process(cursor.next());
    }
}
```

Đóng cursor thông báo cho driver dọn tài nguyên liên quan. Không dựa hoàn toàn vào timeout hoặc garbage collector để xử lý cursor bị bỏ dở.

### 12.2. Cursor có thể timeout

Một cursor bị bỏ không đọc lâu hoặc mất session/network có thể bị đóng theo timeout semantics của server/client/session. Ứng dụng phải coi cursor là nguồn dữ liệu **có thể lỗi khi đang duyệt**.

Không nghĩ rằng `aggregate()` đã trả iterable nghĩa là toàn bộ 1 triệu documents đã sẵn sàng trong JVM.

### 12.3. Batch không phải transaction boundary

Các document ở batch 1 và batch 2 **không tự nằm trong cùng một snapshot nhất quán** chỉ vì chúng thuộc một cursor. Nếu dữ liệu đang thay đổi, cần thiết kế read concern/snapshot/transaction hoặc cơ chế reconciliation theo yêu cầu nghiệp vụ.

## 13. Xử lý bộ nhớ an toàn với kết quả lớn

Sai khi dữ liệu hàng triệu rows:

```java
List<Document> allRows = orders.aggregate(pipeline)
    .into(new ArrayList<>());

for (Document row : allRows) {
    heavyTransform(row);
}
```

Nếu mỗi document trung bình hàng KB, danh sách có thể lên nhiều GB ngoài overhead của `Document`, nested objects và Java heap.

Hướng thường tốt hơn:

```java
long processed = 0;

try (MongoCursor<Document> cursor =
         orders.aggregate(pipeline)
               .batchSize(300)
               .iterator()) {

    while (cursor.hasNext()) {
        Document row = cursor.next();
        lightweightTransform(row);
        processed++;
    }
}

System.out.println("Processed rows: " + processed);
```

### 13.1. Dùng projection để giảm payload

Nếu cần mỗi `_id`, `customerId` và `amountCents`:

```java
import static com.mongodb.client.model.Aggregates.*;
import static com.mongodb.client.model.Projections.*;

List<Bson> pipeline = Arrays.asList(
    match(Filters.eq("tenantId", "T-01")),
    project(fields(include("_id", "customerId", "amountCents")))
);
```

Không lấy `shippingAddress`, `paymentDetails` hoặc `items` khi không sử dụng. Điều này giảm network, decoding, heap và rủi ro lộ PII.

### 13.2. Document size ảnh hưởng batch thực

300 documents mỗi cái 200 bytes rất khác 300 documents mỗi cái 2 MB. MongoDB có giới hạn kích thước BSON document và message, nên cần quan sát **bytes**, không chỉ số record.

### 13.3. Cần dừng đúng cách

Khi job bị hủy hoặc thread bị interrupt:

- Dừng đọc cursor;
- Đóng cursor;
- Không để worker giữ vô hạn queue/pending writes;
- Lưu checkpoint khi đã commit dữ liệu;
- Báo trạng thái job và lỗi;
- Chỉ resume theo cơ chế có kiểm chứng.

## 14. `allowDiskUse()` có tác dụng gì?

Một số aggregation stages phải xử lý nhiều dữ liệu trước khi trả kết quả, ví dụ `$group` và `$sort`.

```java
AggregateIterable<Document> iterable =
    orders.aggregate(pipeline)
          .allowDiskUse(true);
```

`allowDiskUse(true)` cho phép những stages được hỗ trợ dùng disk tạm trong những trường hợp cần thiết, tùy phiên bản, server configuration và giới hạn.

Nó **không** có nghĩa:

- Luôn dùng disk;
- Hết giới hạn tài nguyên;
- Có thể sort vô hạn miễn phí;
- Query chắc chắn nhanh;
- JVM không thể OOM;
- Không cần indexes;
- Mọi stage đều có thể spill.

MongoDB Server từ những dòng phiên bản nhất định có cấu hình `allowDiskUseByDefault`; hành vi mặc định cần được xác minh trên server thực tế.

### 14.1. Rủi ro của disk spill

- Disk I/O tăng;
- Temporary storage tăng;
- Latency p95/p99 có thể xấu đi;
- Nhiều jobs cùng spill có thể gây saturation;
- Có thể xuất hiện lỗi nếu disk thiếu hoặc stage có giới hạn riêng.

Trong production, theo dõi metrics/logs của aggregation và disk, không dùng `allowDiskUse(true)` như phương án chữa mọi pipeline chậm.

### 14.2. Tối ưu thứ tự stages

Một pipeline hợp lý có thể:

```text
$match bằng điều kiện có index
        ↓
$project chỉ fields cần thiết
        ↓
$group
        ↓
$sort
        ↓
$limit
```

Nhưng không được tự hoán đổi mọi stages. Ví dụ `$match` sau `$group` lọc trên kết quả nhóm, không tương đương lọc từng document trước nhóm. Cần giữ semantics đúng và kiểm tra query plan.

## 15. Timeout cho aggregation

Ví dụ:

```java
import java.util.concurrent.TimeUnit;

AggregateIterable<Document> iterable =
    orders.aggregate(pipeline)
          .batchSize(300)
          .maxTime(30, TimeUnit.SECONDS);
```

`maxTime` đặt giới hạn thời gian server xử lý theo semantics command/operation của MongoDB. Nó không phải một **deadline tuyệt đối cho toàn bộ job Java**, nhất là khi job còn làm transformation, ghi output, đợi pool, network và nhiều `getMore` rounds.

Những timeout khác:

| Timeout | Vai trò |
|---|---|
| Server selection | Chờ tìm server phù hợp |
| Connection checkout | Chờ lấy connection từ pool |
| Connect timeout | Thiết lập kết nối |
| Read/socket timeout | Chờ I/O trên socket theo driver config |
| `maxTime` / `maxTimeMS` | Giới hạn operation phía MongoDB |
| Application deadline | Giới hạn thời gian tổng của workflow |
| Batch job timeout | Giới hạn một lần chạy/scheduler |

Không đặt mọi timeout thành “vô hạn” để tránh exception. Một operation chạy chậm thực sự cần điều tra query plan, cache, resource contention hoặc data model.

## 16. Theo dõi aggregation bằng `explain`

Đối với pipeline trên, có thể dùng `explain` thông qua Java Driver khi version hỗ trợ:

```java
Document plan = orders.aggregate(pipeline)
    .explain();

System.out.println(
    plan.get("queryPlanner") != null
        ? "Plan available"
        : "Inspect explain output structure for this server"
);
```

Output có thể khác nhau theo MongoDB Server version, aggregation stages và query engine. Không giả định `queryPlanner` luôn là field top-level.

Cần quan sát:

- `$match` có index-supported plan không;
- `COLLSCAN` hay `IXSCAN`;
- `totalKeysExamined`, `totalDocsExamined`;
- Blocking sort;
- Group spill;
- Query execution time;
- Số documents đi qua từng stage;
- Network/result size.

`explain()` là công cụ phân tích, không thay p95/p99 của toàn bộ API dưới tải thực.

## 17. Aggregation group có thể làm kết quả nhỏ hơn rất nhiều

Giả sử:

```text
Orders input: 5.000.000 documents
Unique customers: 100.000
```

Pipeline `$group` theo customer có thể chỉ trả khoảng 100.000 rows, dù MongoDB phải xử lý phần lớn 5 triệu orders.

`batchSize(500)` giới hạn lượng **output rows trên mỗi batch**, không giới hạn số input documents mà `$group` phải xử lý.

Điều này quan trọng khi tối ưu:

- `$match` giảm tập input;
- Index hỗ trợ lọc;
- `$group` cần memory/disk tương ứng cardinality;
- Output streaming chỉ giải quyết **phần đọc kết quả**, không tự giảm server work.

Một pipeline trả ít kết quả vẫn có thể rất đắt.

## 18. `$lookup` và dữ liệu nhiều collection

Nếu cần tính doanh thu và lấy thông tin customer, có thể dùng `$lookup` theo điều kiện phiên bản/index:

```javascript
{
  $lookup: {
    from: "customers",
    localField: "_id",
    foreignField: "_id",
    as: "customer"
  }
}
```

Trong Java, có thể dùng `Aggregates.lookup()` hoặc `Document`.

### 18.1. Không biến `$lookup` thành N+1 queries ở Java

Một cách kém hiệu quả:

```text
Read 100.000 group results
        │
        └── Với mỗi result gọi customers.findOne(...)
                   → 100.000 round trips
```

Hướng tốt hơn tùy workload:

- `$lookup` hợp lệ và được index hỗ trợ;
- Batch lookup customer IDs theo `$in` có giới hạn;
- Prejoin/materialized view;
- Denormalization có kiểm soát.

### 18.2. Bảo mật khi join

Nếu ứng dụng multi-tenant, phải bảo đảm join không làm lộ record tenant khác. `customerId` chỉ unique trong tenant có thể không đủ khi join trên `_id` không được thiết kế đúng. Kiểm tra **tenant scope trên nguồn và dữ liệu liên quan**.

## 19. Aggregation ghi trực tiếp với `$merge` hoặc `$out`

Không phải mọi aggregation cần đem kết quả về JVM rồi gọi `bulkWrite()`.

Một pipeline có thể ghi ngay trên MongoDB:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01", status: "PAID" } },
  {
    $group: {
      _id: "$customerId",
      totalCents: { $sum: "$amountCents" }
    }
  },
  {
    $merge: {
      into: "customerRevenue",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);
```

Đây là **ví dụ ý tưởng**. Nếu nhiều tenants có cùng customer ID, `_id` kết quả phải bao gồm tenant; nếu không, có thể trộn dữ liệu. Dữ liệu output và unique key phải được thiết kế đúng.

### 19.1. Java: pipeline có `$merge`

```java
List<Bson> pipeline = Arrays.asList(
    Aggregates.match(Filters.eq("tenantId", "T-01")),
    Aggregates.group(
        new Document("tenantId", "$tenantId")
            .append("customerId", "$customerId"),
        Accumulators.sum("totalCents", "$amountCents")
    ),
    new Document("$merge",
        new Document("into", "customerRevenue")
            .append("on", "_id")
            .append("whenMatched", "replace")
            .append("whenNotMatched", "insert")
    )
);
```

**Quan trọng:** tạo `AggregateIterable` chưa đủ để chắc chắn pipeline đã chạy. Phải tiêu thụ:

```java
try (MongoCursor<Document> cursor =
         orders.aggregate(pipeline).iterator()) {

    while (cursor.hasNext()) {
        cursor.next();
    }
}
```

`$merge` thường không tạo các result documents nghiệp vụ như pipeline chỉ đọc; việc cursor được tiêu thụ mới khiến server thực thi pipeline. Không chỉ gọi `orders.aggregate(pipeline);` rồi kết luận materialization đã hoàn thành.

### 19.2. Khi nào chọn `$merge` thay `bulkWrite`?

`$merge` có thể phù hợp khi:

- Tất cả transformation dùng được aggregation stages;
- Muốn xử lý gần dữ liệu, giảm truyền dữ liệu qua JVM;
- Target là collection được phép;
- Merge semantics phù hợp;
- Có kế hoạch idempotency, indexes và quyền.

Java `bulkWrite` phù hợp hơn khi:

- Business logic phải chạy trong Java;
- Cần external API hoặc validation ngoài MongoDB;
- Muốn điều khiển từng loại write model;
- Cần trả kết quả/định tuyến records;
- Có yêu cầu checkpoint/migration riêng.

`$merge` cũng không tự là transaction nguyên tử trên mọi documents đầu ra. Phải hiểu failure/retry behavior và thiết kế idempotency.

## 20. `bulkWrite()` là gì?

`MongoCollection.bulkWrite()` cho phép gom **nhiều thao tác ghi** trên cùng collection vào một lần gọi API:

- `InsertOneModel<T>`;
- `UpdateOneModel<T>`;
- `UpdateManyModel<T>`;
- `ReplaceOneModel<T>`;
- `DeleteOneModel<T>`;
- `DeleteManyModel<T>`.

Ví dụ:

```text
BulkWrite:
  1. Insert order A
  2. Update order B
  3. Delete stale order C
  4. Replace order D
  5. Update status of order E
```

MongoDB Driver nhận `List<WriteModel<T>>`, sau đó tổ chức lệnh ghi theo giới hạn và semantics server/driver.

### 20.1. Vì sao thường hiệu quả hơn vòng lặp gọi đơn lẻ?

So sánh:

```java
for (Document d : documents) {
    collection.insertOne(d);
}
```

với:

```java
List<WriteModel<Document>> operations = ...;
collection.bulkWrite(operations);
```

Bulk operation có thể giảm round trips và overhead điều phối, nhưng mức tăng tốc thực tế tùy kích thước batch, topology, network, indexes, validation và số thao tác.

Không có nghĩa `bulkWrite` luôn nhanh hơn mọi `insertMany` hoặc server-side `$merge`; cần benchmark đúng workload.

## 21. Ví dụ `bulkWrite` với nhiều loại thao tác

```java
import java.util.ArrayList;
import java.util.List;

import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.DeleteOneModel;
import com.mongodb.client.model.InsertOneModel;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.WriteModel;
import com.mongodb.bulk.BulkWriteResult;

import org.bson.Document;

List<WriteModel<Document>> writes = new ArrayList<>();

writes.add(
    new InsertOneModel<>(
        new Document("_id", "ORD-2001")
            .append("tenantId", "T-01")
            .append("status", "NEW")
            .append("amountCents", 149900L)
    )
);

writes.add(
    new UpdateOneModel<>(
        Filters.and(
            Filters.eq("_id", "ORD-1001"),
            Filters.eq("tenantId", "T-01")
        ),
        Updates.combine(
            Updates.set("status", "SHIPPED"),
            Updates.currentDate("updatedAt")
        ),
        new UpdateOptions().upsert(false)
    )
);

writes.add(
    new DeleteOneModel<>(
        Filters.and(
            Filters.eq("_id", "TEMP-01"),
            Filters.eq("tenantId", "T-01")
        )
    )
);

BulkWriteResult result = orders.bulkWrite(
    writes,
    new BulkWriteOptions().ordered(true)
);

if (result.wasAcknowledged()) {
    System.out.println("Inserted: " + result.getInsertedCount());
    System.out.println("Matched: " + result.getMatchedCount());
    System.out.println("Modified: " + result.getModifiedCount());
    System.out.println("Deleted: " + result.getDeletedCount());
}
```

**Không chạy nguyên ví dụ trên dữ liệu production.** Đây là mô tả thao tác trên collection thử nghiệm, với IDs giả định.

### 21.1. Tại sao dùng `WriteModel<Document>`?

Tất cả operations trong một collection-scoped bulk phải tương ứng với kiểu document của collection. `WriteModel<TDocument>` cho phép biểu diễn các thao tác khác nhau bằng cấu trúc type-safe hơn so với gửi JSON tự do.

### 21.2. `ordered(true)` có nghĩa gì?

Các writes được xử lý theo semantics thứ tự: khi xuất hiện write error trong ordered bulk, phần còn lại thường không được xử lý tiếp theo quy tắc bulk write.

`ordered(true)` **không làm cả batch atomic** và không đảm bảo mọi thao tác trước lỗi được hoàn tác.

## 22. `ordered` và `unordered`: lựa chọn chiến lược

Ví dụ:

```java
new BulkWriteOptions().ordered(true);
```

so với:

```java
new BulkWriteOptions().ordered(false);
```

### 22.1. Ordered bulk

Ý tưởng:

```text
Write 1 → success
Write 2 → success
Write 3 → duplicate key error
Write 4 → not executed
Write 5 → not executed
```

Thích hợp khi:

- Một số thao tác phụ thuộc thứ tự;
- Muốn dừng sớm khi gặp lỗi;
- Cần dự đoán sequence của các operations ở mức API;
- Không chấp nhận xử lý các operations phía sau nếu trước đó đã lỗi.

Nhưng ordered **vẫn không phải transaction cho toàn bộ danh sách**.

### 22.2. Unordered bulk

Ví dụ:

```java
new BulkWriteOptions().ordered(false);
```

MongoDB có thể thực hiện các thao tác không theo thứ tự nguồn và có thể tiếp tục các thao tác khác sau những lỗi ghi riêng lẻ.

Ý tưởng:

```text
Write 1 → success
Write 2 → duplicate key
Write 3 → success
Write 4 → success
Write 5 → validation error
```

Thích hợp khi:

- Operations độc lập;
- Muốn đạt throughput tốt;
- Muốn các record hợp lệ tiếp tục được ghi dù một số record lỗi.

**Không cam kết rằng mọi operation luôn được thử khi xảy ra lỗi cấp connection/server/command.** Một lỗi nghiêm trọng có thể khiến phần còn lại chưa được xử lý.

### 22.3. Unordered không bảo đảm thứ tự cập nhật cùng record

Không dùng unordered cho sequence:

```text
Update status = PAID
Update status = SHIPPED
Update status = DELIVERED
```

nếu cả ba thao tác cùng một document và kết quả phụ thuộc thứ tự.

Thay vào đó:

- Gộp thành một update trạng thái cuối nếu hợp logic;
- Dùng ordered;
- Dùng optimistic concurrency/version guard;
- Hoặc transaction khi cần multi-document atomicity.

### 22.4. So sánh

| Tiêu chí | `ordered(true)` | `ordered(false)` |
|---|---|---|
| Thứ tự thao tác | Theo trình tự được quy định | Không bảo đảm |
| Write error ở giữa | Thường dừng các write sau lỗi | Có thể tiếp tục các writes khác |
| Dùng cho operations độc lập | Được | Thường phù hợp hơn |
| Phụ thuộc thứ tự cập nhật | Phù hợp hơn | Không nên |
| Atomic cả batch | **Không** | **Không** |
| Partial success | Có thể | Có thể |
| Độ phức tạp retry | Cần xử lý | Cần xử lý |

## 23. Các mô hình ghi phổ biến

### 23.1. Insert

```java
new InsertOneModel<>(
    new Document("_id", "ORD-3001")
        .append("tenantId", "T-01")
);
```

Nếu `_id` trùng, MongoDB có thể trả duplicate key error.

### 23.2. Update một record

```java
new UpdateOneModel<>(
    Filters.eq("_id", "ORD-3001"),
    Updates.set("status", "PAID")
);
```

### 23.3. Update nhiều records

```java
new com.mongodb.client.model.UpdateManyModel<>(
    Filters.and(
        Filters.eq("tenantId", "T-01"),
        Filters.eq("status", "PENDING")
    ),
    Updates.set("needsReview", true)
);
```

`updateMany` có thể ảnh hưởng rất nhiều documents; phải xác minh filter trước khi thực thi.

### 23.4. Replace

```java
new com.mongodb.client.model.ReplaceOneModel<>(
    Filters.eq("_id", "ORD-3001"),
    new Document("_id", "ORD-3001")
        .append("tenantId", "T-01")
        .append("status", "PAID")
        .append("amountCents", 100000L)
);
```

`replaceOne` thay nội dung document theo semantics của replace; không giống `$set` từng field. Nếu replacement bỏ quên fields cũ, chúng có thể bị xóa khỏi document.

### 23.5. Delete many

```java
new com.mongodb.client.model.DeleteManyModel<>(
    Filters.and(
        Filters.eq("tenantId", "T-01"),
        Filters.eq("archived", true)
    )
);
```

Không dùng filter rỗng cho delete trên production trừ khi đó là tác vụ đã được phê duyệt và kiểm soát.

## 24. `upsert(true)` và tính idempotent

Upsert là thao tác:

- Có document khớp → update/replace;
- Không có document khớp → insert theo semantics của operation.

Ví dụ:

```java
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.UpdateOptions;

WriteModel<Document> operation =
    new UpdateOneModel<>(
        Filters.eq("_id", "T-01:C-105"),
        Updates.combine(
            Updates.set("tenantId", "T-01"),
            Updates.set("customerId", "C-105"),
            Updates.set("grossCents", 349900L)
        ),
        new UpdateOptions().upsert(true)
    );
```

Nếu chạy lại với cùng giá trị, kết quả trạng thái có thể giống lần trước. Đây là một dạng **idempotent update** khi business semantics và input không thay đổi.

### 24.1. `$inc` không idempotent nếu retry thủ công

Không nên tự retry mù:

```java
new UpdateOneModel<>(
    Filters.eq("_id", "COUNTER-1"),
    Updates.inc("count", 1)
);
```

Nếu write đã thành công nhưng client timeout trước khi nhận ACK rồi job chạy lại thao tác như một request mới, `count` có thể tăng lần nữa.

Driver hỗ trợ retryable writes cho một số thao tác đủ điều kiện và sử dụng session/transaction identifiers để giảm nguy cơ lặp trong phạm vi hỗ trợ. **Application retry ngoài cơ chế đó không tự giữ cùng identity của write**, và các thao tác multi-update cũng có điều kiện khác.

### 24.2. Tạo khóa duy nhất cho bản ghi tổng hợp

Khi tạo `customerRevenue`, có thể dùng:

```text
_id = tenantId + ":" + customerId + ":" + period
```

Nếu các thành phần không bảo đảm không chứa dấu phân cách, dùng structured compound key hoặc encoding không mơ hồ.

Ví dụ:

```java
Document id = new Document("tenantId", "T-01")
    .append("customerId", "C-105")
    .append("period", "2026-11");
```

MongoDB cho phép `_id` là BSON document, nhưng cần quy ước thứ tự fields và cách serialize nhất quán. Khóa upsert phải phản ánh đúng business identity để không ghi trộn tenants.

## 25. Kết quả trả về `BulkWriteResult`

Sau `bulkWrite()` thành công:

```java
BulkWriteResult result = collection.bulkWrite(
    writes,
    new BulkWriteOptions().ordered(false)
);
```

Các thông tin phổ biến:

| API | Ý nghĩa |
|---|---|
| `wasAcknowledged()` | Write concern có acknowledgment không |
| `getInsertedCount()` | Số documents được insert |
| `getMatchedCount()` | Số documents match updates/replacements |
| `getModifiedCount()` | Số documents thực sự modified khi được hỗ trợ |
| `getDeletedCount()` | Số documents được delete |
| `getUpserts()` | Danh sách những upsert insertions |

### 25.1. Matched khác modified

Giả sử:

```text
Document status hiện tại = "PAID"
UpdateOne: set status = "PAID"
```

Có thể:

```text
matchedCount = 1
modifiedCount = 0
```

Đây không nhất thiết là lỗi, vì document đã có giá trị mong muốn.

### 25.2. Upsert count không đồng nghĩa insert model count

Một `UpdateOneModel` với `upsert(true)` có thể thêm document mới. Khi đó record xuất hiện trong `getUpserts()`, không nhất thiết được tính vào `getInsertedCount()` dành cho insert models.

### 25.3. Unacknowledged writes

Nếu chọn write concern không xác nhận, một số counters không sẵn sàng hoặc không thể dùng như bình thường. Với batch ETL quan trọng, cần cân nhắc write concern phù hợp; không chọn unacknowledged chỉ để tăng con số throughput trong benchmark.

## 26. Xử lý `MongoBulkWriteException`

Bulk có thể **thành công một phần** rồi trả lỗi.

```java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;
import com.mongodb.bulk.BulkWriteResult;

try {
    BulkWriteResult result = collection.bulkWrite(
        writes,
        new BulkWriteOptions().ordered(false)
    );

    recordSuccess(result);

} catch (MongoBulkWriteException ex) {
    BulkWriteResult partial = ex.getWriteResult();

    if (partial != null && partial.wasAcknowledged()) {
        recordPartialCounts(partial);
    }

    for (BulkWriteError error : ex.getWriteErrors()) {
        int requestIndex = error.getIndex();
        int errorCode = error.getCode();

        // Chỉ log metadata đã được phê duyệt.
        recordFailure(requestIndex, errorCode);
    }

    if (ex.getWriteConcernError() != null) {
        recordWriteConcernProblem(
            ex.getWriteConcernError().getCode()
        );
    }

    throw ex; // Để job framework quyết định retry/reconcile.
}
```

`recordSuccess`, `recordPartialCounts`, `recordFailure` và `recordWriteConcernProblem` là hàm ứng dụng cần hiện thực; ví dụ tập trung vào luồng xử lý lỗi.

### 26.1. Index của lỗi ứng với thao tác nào?

`BulkWriteError.getIndex()` giúp nhận diện vị trí operation tương ứng trong danh sách write requests theo ngữ nghĩa driver. Nếu cần retry một subset, phải lưu mapping giữa `WriteModel` và business ID/job ID khi build batch.

Không chỉ log “bulk error 11000” mà không biết document nào gây lỗi, đặc biệt trong ETL lớn.

### 26.2. Partial success là bình thường trong unordered bulk

Một unordered bulk có thể có:

```text
Requested: 500
Succeeded: 490
Failed due duplicate key: 8
Failed due schema validation: 2
```

Nếu job tự động chạy lại cả 500 thao tác, thành công sẽ phụ thuộc idempotency. Một bộ `InsertOneModel` có `_id` đã tồn tại có thể trả duplicate key hàng loạt; các thao tác `$inc` có thể ghi lặp.

### 26.3. `writeConcernError` khác write error

- **Write error:** một write model cụ thể bị từ chối, ví dụ duplicate key, validation.
- **Write concern error:** hoạt động không đạt điều kiện xác nhận ghi đã yêu cầu, dù một số thay đổi có thể đã được thực hiện.

Khi gặp write concern/network timeout, **không tự suy lệnh chắc chắn chưa ghi**. Cần đọc trạng thái theo business key hoặc áp dụng idempotency/reconciliation.

### 26.4. Không nuốt exception rồi báo thành công

Sai:

```java
try {
    collection.bulkWrite(writes);
} catch (Exception ignored) {
    // Job tiếp tục và báo completed.
}
```

Một job như vậy có thể bỏ qua hàng nghìn records và không ai biết. Cần phân loại lỗi, lưu failed IDs/retry metadata và kết thúc với trạng thái đúng.

## 27. Các giới hạn kích thước của bulk operation

Một danh sách `WriteModel` quá lớn có thể:

- Tiêu thụ nhiều heap trước khi gửi;
- Làm thời gian xây batch kéo dài;
- Tăng rủi ro thất bại một đợt lớn;
- Tốn chi phí retry/reconciliation;
- Đụng giới hạn kích thước BSON/message/batch từ server.

MongoDB driver có cơ chế chia operations theo những giới hạn giao thức/server như `maxWriteBatchSize`, `maxBsonObjectSize`, `maxMessageSizeBytes` trong phạm vi hỗ trợ. **Không nên hiểu rằng truyền một triệu operations vào một `bulkWrite()` sẽ thành một command mạng duy nhất.**

### 27.1. Kiểm soát batch ở ứng dụng

Ví dụ lựa chọn bắt đầu:

```text
Read cursor batchSize: 250
Write operation buffer: 400
Maximum buffer memory: monitored
```

Không có quy định phải dùng 400. Với document lớn, nên dùng batch nhỏ hơn. Với tác vụ lightweight và network RTT cao, có thể thử batch lớn hơn.

### 27.2. Batch size ảnh hưởng tail latency

Một batch rất lớn có thể giảm số round trips nhưng tăng:

- Latency cho đến khi một batch được ACK;
- Số records cần reconcile khi lỗi;
- Memory peak;
- Contention;
- Thời gian giữ worker.

Vì vậy tối ưu theo throughput **và** p95/p99, không chỉ tổng số record/giây.

## 28. Ví dụ `bulkWrite` theo nhóm 400 thao tác

Một hàm cơ sở:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public final class BulkBuffer {
    private final MongoCollection<Document> collection;
    private final int maxOperations;
    private final List<WriteModel<Document>> pending =
        new ArrayList<>();

    public BulkBuffer(
        MongoCollection<Document> collection,
        int maxOperations
    ) {
        if (maxOperations <= 0) {
            throw new IllegalArgumentException("maxOperations must be positive");
        }
        this.collection = collection;
        this.maxOperations = maxOperations;
    }

    public void add(WriteModel<Document> operation) {
        pending.add(operation);

        if (pending.size() >= maxOperations) {
            flush();
        }
    }

    public void flush() {
        if (pending.isEmpty()) {
            return;
        }

        collection.bulkWrite(
            pending,
            new BulkWriteOptions().ordered(false)
        );

        // Chỉ clear khi đã nhận thành công theo write concern.
        pending.clear();
    }
}
```

Trong production, cần bổ sung:

- Lưu business IDs tương ứng mỗi model;
- Xử lý partial write failures;
- Retry/reconciliation;
- Metrics;
- Error classification;
- Backoff/cancellation;
- Không chia sẻ buffer này giữa nhiều threads nếu không có đồng bộ phù hợp;
- Giới hạn bytes, không chỉ operation count.

### 28.1. Vì sao clear sau thành công?

Nếu clear trước khi gọi bulk và call lỗi, job mất toàn bộ danh sách chưa xử lý. Tuy nhiên, nếu call lỗi sau **partial success**, giữ nguyên danh sách để retry cũng chưa đủ. Cần phân loại trạng thái của từng operation và bảo đảm idempotency.

### 28.2. `flush()` cuối job là bắt buộc

Nếu đã gom 1.050 operations với max batch 400:

```text
Batch 1: 400
Batch 2: 400
Buffer cuối: 250
```

Nếu quên `flush()` lúc kết thúc, **250 operations còn lại không được gửi**.

## 29. Kết hợp aggregation, cursor và `bulkWrite`

Đây là bài toán tổng hợp: đọc những orders thuộc một tenant và khoảng ngày; thay đổi cấu trúc dữ liệu trong Java; upsert sang collection `orderExports`.

Để dễ triển khai, ví dụ dùng source documents **độc lập**, không dùng aggregation `$group` tạo thay đổi mỗi khách hàng. Điều này giúp giải thích chính xác cách mỗi source record ánh xạ sang một target write.

### 29.1. Thiết kế target

Một record nguồn:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T-01",
  customerId: "C-105",
  status: "PAID",
  amountCents: NumberLong("249900")
}
```

Target `orderExports`:

```javascript
{
  _id: {
    tenantId: "T-01",
    orderId: "ORD-1001"
  },
  customerId: "C-105",
  status: "PAID",
  amountCents: NumberLong("249900")
}
```

Dùng `_id` gồm tenant + orderId để tránh ghi trộn các business IDs giữa tenants.

### 29.2. Pipeline lấy các fields cần thiết

```java
import static com.mongodb.client.model.Aggregates.*;
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Projections.*;

List<Bson> pipeline = Arrays.asList(
    match(and(
        eq("tenantId", "T-01"),
        eq("status", "PAID")
    )),
    project(fields(
        include("_id", "tenantId", "customerId",
                "status", "amountCents")
    ))
);
```

Không dùng `into(new ArrayList<>())` nếu source lớn.

### 29.3. Hàm chuyển source thành write model

```java
import com.mongodb.client.model.ReplaceOneModel;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.WriteModel;
import com.mongodb.client.model.Filters;

import org.bson.Document;

static WriteModel<Document> toExportWrite(Document src) {
    String orderId = src.getString("_id");
    String tenantId = src.getString("tenantId");

    Document targetId = new Document("tenantId", tenantId)
        .append("orderId", orderId);

    Document replacement = new Document("_id", targetId)
        .append("customerId", src.getString("customerId"))
        .append("status", src.getString("status"))
        .append("amountCents", src.get("amountCents"));

    return new ReplaceOneModel<>(
        Filters.eq("_id", targetId),
        replacement,
        new ReplaceOptions().upsert(true)
    );
}
```

Ưu điểm: với cùng source record, chạy lại thao tác có thể tạo **cùng target state**, khác với `$inc`.

Nhưng nếu source được cập nhật trong lúc job chạy, một record cũ có thể **ghi đè dữ liệu mới** trong target. Đó là vấn đề source revision, sẽ xử lý ở phần sau.

### 29.4. Job đầy đủ ở mức API

```java
import com.mongodb.client.AggregateIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;

import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.WriteModel;

import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

static long exportOrders(
    MongoCollection<Document> source,
    MongoCollection<Document> target,
    List<Bson> pipeline
) {
    final int readBatchSize = 250;
    final int writeBatchSize = 400;

    long processed = 0;
    List<WriteModel<Document>> pending =
        new ArrayList<>(writeBatchSize);

    AggregateIterable<Document> iterable = source.aggregate(pipeline)
        .batchSize(readBatchSize)
        .maxTime(60, TimeUnit.SECONDS);

    try (MongoCursor<Document> cursor = iterable.iterator()) {
        while (cursor.hasNext()) {
            Document src = cursor.next();

            pending.add(toExportWrite(src));
            processed++;

            if (pending.size() >= writeBatchSize) {
                target.bulkWrite(
                    pending,
                    new BulkWriteOptions().ordered(false)
                );
                pending.clear();
            }
        }
    }

    if (!pending.isEmpty()) {
        target.bulkWrite(
            pending,
            new BulkWriteOptions().ordered(false)
        );
        pending.clear();
    }

    return processed;
}
```

Hàm trên minh họa **đọc streaming + ghi theo batch**. Nó chưa cung cấp transaction toàn job, checkpoint bền vững, xử lý partial failures hoặc change capture. Những phần này là bắt buộc nếu mục tiêu là ETL production có khả năng resume chính xác.

### 29.5. Tại sao không gọi `bulkWrite` cho từng record?

Nếu tạo một `List` một phần tử rồi gọi `bulkWrite` trong mỗi vòng lặp, không tận dụng được lợi ích gom writes. Phải giữ buffer đủ lớn theo workload, nhưng cũng không để buffer tăng không giới hạn.

### 29.6. Có cần mở hai `MongoClient`?

Thông thường có thể dùng **cùng MongoClient** nếu source/target nằm trong cùng deployment và security context. Hai deployments khác nhau có thể cần hai clients và connection strings riêng. Không tạo client mới cho mỗi batch.

## 30. Sai lầm về nhất quán: đọc trong lúc dữ liệu thay đổi

Giả sử ETL:

```text
T1: Cursor đọc ORD-1001, sourceRevision=7
T2: User cập nhật ORD-1001 lên revision=8
T3: Worker khác export revision=8 sang target
T4: ETL cũ bulk replace revision=7 vào target
```

Kết quả target bị ghi đè bằng dữ liệu cũ.

### 30.1. Phương án đơn giản: snapshot dataset

Nếu nghiệp vụ cho phép, chạy ETL trên một bản snapshot nhất quán hoặc tập nguồn đã được đóng băng trong thời gian xử lý.

Ưu điểm: đơn giản hơn về semantics. Nhược điểm: có thể cần storage/thời gian/cơ chế snapshot phù hợp.

Không giả định chỉ thêm `readConcern("majority")` cho một chuỗi nhiều lệnh đọc là đủ để tạo snapshot toàn job.

### 30.2. Phương án: source revision và guarded writes

Lưu:

```javascript
{
  _id: "ORD-1001",
  sourceRevision: 8
}
```

Trong target cũng lưu revision. Một job cũ không được overwrite target revision mới.

Ví dụ logic:

```text
If target revision < source revision:
    allow update
Else:
    skip as stale or duplicate
```

Một guarded update phải **gắn điều kiện vào chính thao tác atomic** và phải xử lý upsert/unique key đúng; không chỉ đọc target revision rồi quyết định ở Java, vì một worker khác có thể ghi giữa hai bước.

### 30.3. Khó khăn với upsert cạnh tranh

Nếu target chưa tồn tại, hai workers có thể cùng upsert. Cần unique key ổn định và retry/duplicate-key reconciliation. Một filter điều kiện version không được thiết kế kỹ có thể tạo duplicate hoặc conflict.

Với luồng phức tạp, cân nhắc transactional outbox, versioned staging collection, `$merge` có semantics phù hợp hoặc change streams để catch-up.

### 30.4. Deletes cũng phải được phản ánh

Một batch scan đơn thuần chỉ thấy documents đang tồn tại; nếu source đã bị xóa sau khi export, target không tự biết phải xóa.

Cần:

- Tombstones;
- Change stream delete events;
- Reconciliation toàn bộ key set;
- TTL/retention đồng bộ theo policy.

Không kết luận mirror chính xác chỉ vì tất cả source documents hiện thấy đã được upsert.

## 31. Cursor và checkpoint: `batchSize` không giúp resume

Một job xử lý 2 triệu records có thể chết sau 1,2 triệu records.

```text
Processed: 1,200,000
JVM crash
Cursor lost
```

Khi restart, `MongoCursor` cũ không còn là một checkpoint bền vững. Cần lưu:

- Job ID;
- Source range/watermark;
- Định danh cuối đã **commit** ở target;
- Pipeline/transform version;
- Retry count;
- Error records;
- Snapshot/revision context;
- Start/end timestamps.

### 31.1. Keyset pagination cho scan ổn định

Khi quét documents theo `_id`:

```javascript
db.orders.find({
  tenantId: "T-01",
  _id: { $gt: lastCommittedId }
})
.sort({ _id: 1 })
.limit(500);
```

Cần có index phù hợp, ví dụ tùy workload:

```javascript
db.orders.createIndex({
  tenantId: 1,
  _id: 1
});
```

Mẫu trên không phải full snapshot. Document mới có `_id` nhỏ hơn watermark hoặc document bị cập nhật/xóa trong lúc scan có thể không được xử lý đúng; cần catch-up mechanism.

### 31.2. Java `find` theo keyset

```java
import com.mongodb.client.FindIterable;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;

String tenantId = "T-01";
String lastCommittedId = "ORD-1000";

FindIterable<Document> page = orders.find(
    Filters.and(
        Filters.eq("tenantId", tenantId),
        Filters.gt("_id", lastCommittedId)
    )
)
.sort(Sorts.ascending("_id"))
.limit(500)
.batchSize(100);
```

`limit(500)` xác định **trang logic**; `batchSize(100)` điều chỉnh network fetching bên trong trang.

### 31.3. Khi nào ghi checkpoint?

**Sau khi xác nhận** các writes tương ứng đã thành công theo write concern và logic đối soát. Nếu ghi watermark trước rồi `bulkWrite` thất bại, job có thể bỏ mất records.

Nếu một batch thành công một phần, không được cập nhật checkpoint vượt qua những records chưa được xử lý mà không có cơ chế theo dõi failed IDs.

### 31.4. Không dùng offset `skip` làm checkpoint cho dataset đang đổi

Nếu documents được thêm/xóa trong khi đọc từng trang:

```text
Page 1: skip 0, limit 500
Page 2: skip 500, limit 500
```

các record có thể bị đọc trùng hoặc bỏ sót. Keyset và change capture thường phù hợp hơn cho những jobs lớn, nhưng vẫn phải thiết kế consistency.

## 32. `aggregate` kết hợp `bulkWrite`: nhóm kết quả rồi ghi

Một bài toán khác là **tính tổng theo khách hàng**, rồi materialize `customerRevenue`.

Pipeline:

```java
List<Bson> pipeline = Arrays.asList(
    Aggregates.match(
        Filters.and(
            Filters.eq("tenantId", "T-01"),
            Filters.eq("status", "PAID")
        )
    ),

    Aggregates.group(
        "$customerId",
        Accumulators.sum("grossCents", "$amountCents"),
        Accumulators.sum("orderCount", 1)
    )
);
```

Một group result:

```javascript
{
  _id: "C-105",
  grossCents: NumberLong("349900"),
  orderCount: 2
}
```

Chuyển thành `UpdateOneModel`:

```java
static WriteModel<Document> toRevenueWrite(
    String tenantId,
    Document grouped
) {
    String customerId = grouped.getString("_id");

    Document targetId = new Document("tenantId", tenantId)
        .append("customerId", customerId);

    return new UpdateOneModel<>(
        Filters.eq("_id", targetId),
        Updates.combine(
            Updates.set("tenantId", tenantId),
            Updates.set("customerId", customerId),
            Updates.set("grossCents", grouped.get("grossCents")),
            Updates.set("orderCount", grouped.get("orderCount")),
            Updates.currentDate("computedAt")
        ),
        new UpdateOptions().upsert(true)
    );
}
```

Đây là **ghi lại tổng toàn phần** theo group, không cộng dồn các delta. Nếu chạy cùng nguồn/snapshot và logic không đổi, trạng thái tổng hợp có thể hội tụ về cùng giá trị.

### 32.1. Vấn đề cập nhật nguồn giữa hai lần chạy

Nếu nguồn thay đổi sau khi aggregation đã tính group, target có thể tạm thời stale. Một chiến lược là tính toàn bộ group theo `snapshotTime` hoặc giữ `computedAt/sourceWatermark`, sau đó chạy catch-up.

### 32.2. Group bị xóa hoàn toàn

Nếu khách hàng không còn order `PAID`, pipeline mới có thể **không tạo group result**; target tổng cũ vẫn tồn tại. Cần xóa/reconcile những keys không còn thuộc kết quả hoặc có cơ chế tombstone.

Đây là lỗi thường gặp trong materialized view, không được giải quyết chỉ bằng `upsert(true)`.

### 32.3. Có thể dùng `$merge`

Nếu toàn bộ tính toán ở MongoDB và không cần Java transformation, `$merge` có thể giảm network/JVM overhead. Nhưng vẫn phải xử lý missing groups, consistency, quyền và failure semantics.

## 33. Bulk operation không phải transaction

Một ordered bulk:

```text
Update A → committed
Update B → committed
Update C → failed
Update D → never executed
```

Không có mặc định rollback A/B khi C thất bại.

### 33.1. Single-document atomicity

MongoDB đảm bảo atomicity cho một thao tác ghi đối với **một document** theo ngữ nghĩa hỗ trợ, nhưng không biến tất cả `WriteModel` trên nhiều documents thành một đơn vị atomic.

Nếu cần tất cả A/B/C cùng thành công hoặc cùng rollback, cần thiết kế **multi-document transaction** khi deployment hỗ trợ.

### 33.2. Transaction không miễn phí

Transaction có chi phí:

- Giữ tài nguyên/snapshot;
- Coordination;
- Retry khi transient errors;
- Timeouts;
- Khả năng xung đột;
- Giới hạn quy mô/thời gian theo version/config.

Không đưa một migration 50 triệu records vào **một transaction khổng lồ** chỉ để dễ nghĩ về atomicity.

### 33.3. Ví dụ session + bulk

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;

try (ClientSession session = client.startSession()) {
    session.startTransaction();

    try {
        collection.bulkWrite(
            session,
            writes,
            new BulkWriteOptions().ordered(true)
        );

        session.commitTransaction();
    } catch (Exception ex) {
        session.abortTransaction();
        throw ex;
    }
}
```

Đây là **khung minh họa**, chưa có retry handling cho transaction commit và transient error labels. Các helper chuẩn như `withTransaction` hoặc driver transaction callback theo version thường phù hợp hơn nếu triển khai đúng.

Cần kiểm tra topology support, session lifecycle và write concern. Transactions không làm những external API calls trở thành atomic cùng database.

## 34. Read concern và write concern

Hai khái niệm thường bị nhầm:

- **Write concern:** điều kiện xác nhận ghi ở server/replica set.
- **Read concern:** mức bảo đảm cho dữ liệu được đọc theo option được hỗ trợ.

Ví dụ muốn collection sử dụng majority write concern:

```java
import com.mongodb.WriteConcern;

MongoCollection<Document> durableWrites =
    collection.withWriteConcern(WriteConcern.MAJORITY);
```

### 34.1. `MAJORITY` không phải idempotency

Nếu cùng một `$inc` được client gọi thành hai request độc lập, cả hai đều đạt majority thì counter có thể tăng hai lần. Majority giúp điều kiện xác nhận ghi, không quyết định hành vi retry nghiệp vụ.

### 34.2. `readConcern("majority")` không tự là snapshot toàn job

Đọc một triệu rows trong nhiều calls/phases mà source tiếp tục đổi có thể sinh kết quả không phải một ảnh tại một thời điểm. Đối với yêu cầu snapshot thật, cần dùng cơ chế snapshot read/transaction hoặc snapshot backup phù hợp MongoDB version, topology và duration.

### 34.3. Write concern thấp không phải cách sửa throughput an toàn

Hạ write concern có thể giảm waiting trong một số trường hợp nhưng làm thay đổi durability guarantee. Đặt dựa trên RPO/business semantics, không tự thay để kết quả benchmark đẹp hơn.

## 35. Retryable writes và lỗi không xác định kết quả

Một tình huống:

```text
T1: Client gửi bulk update
T2: Server đã ghi
T3: Network mất trước khi ACK tới client
T4: Client nhận timeout
```

Client có thể **không biết** lệnh đã ghi chưa.

### 35.1. Không đồng nhất retryable driver và retry thủ công

Retryable writes của driver chỉ áp dụng cho **những thao tác đủ điều kiện** và theo điều kiện server/session/transaction. Bulk chứa thao tác multi-document như `updateMany` hoặc `deleteMany` có tính retryability khác. Không mặc định “bật `retryWrites=true` thì cả mọi bulk luôn an toàn để retry”.

Vòng retry mới ở tầng ứng dụng có thể tạo request identity mới và gây duplicate effects, kể cả khi driver retries ban đầu an toàn theo giao thức.

### 35.2. Cách giảm rủi ro

- Sử dụng operation id/business key ổn định.
- Upsert theo unique key khi phù hợp.
- Prefer `$set`/replace tới trạng thái cuối thay vì `$inc` không idempotent khi replay.
- Dùng optimistic version guard.
- Reconcile kết quả theo `_id` nếu timeout.
- Không retry mãi một lỗi validation/authorization.
- Có retry budget và exponential backoff với jitter.
- Log job ID, batch ID, model indexes, lỗi và mốc commit.

### 35.3. Các lỗi không nên retry vô hạn

| Loại | Hướng xử lý |
|---|---|
| Duplicate key do logic nghiệp vụ | Validate/skip/quản lý conflict |
| Schema validation error | Sửa dữ liệu/mapping |
| Unauthorized | Sửa quyền/credentials |
| Invalid BSON/dimension/type | Sửa input |
| Rate limit/transient network | Retry có giới hạn |
| Write concern timeout | Kiểm tra trạng thái trước retry |
| Primary stepdown | Driver retry/resume theo khả năng |
| Disk full | Chặn job, xử lý capacity |
| Wrong collection/tenant | Dừng và điều tra bảo mật |

## 36. Bulk và ràng buộc uniqueness

Để upsert theo business key, phải có index bảo đảm uniqueness khi phù hợp.

Ví dụ collection doanh thu:

```javascript
{
  _id: {
    tenantId: "T-01",
    customerId: "C-105"
  },
  grossCents: NumberLong("349900")
}
```

`_id` được MongoDB kiểm soát uniqueness trong phạm vi collection. Nếu thay bằng fields độc lập:

```javascript
{
  tenantId: "T-01",
  customerId: "C-105"
}
```

cần cân nhắc unique compound index:

```javascript
db.customerRevenue.createIndex(
  { tenantId: 1, customerId: 1 },
  { unique: true }
);
```

Khi upsert cạnh tranh, hai workers cùng không tìm thấy record có thể dẫn tới duplicate key conflict. Không coi duplicate key luôn là mất dữ liệu; có thể cần đọc lại và quyết định based on idempotent semantics.

### 36.1. Đừng dùng unordered updates xóa cùng key

Nếu một bulk vừa xóa vừa upsert cùng document và order-dependent, unordered có thể tạo kết quả không ổn định. Phải chia phases hoặc dùng ordered/transaction với business semantics rõ.

### 36.2. Một batch có nhiều operations cùng `_id`

Nên tránh tạo nhiều operations có cùng target key khi không chủ ý. Có thể deduplicate trong Java theo business key trước khi xây bulk, hoặc merge changes thành một update.

## 37. Bảo mật và tenant isolation trong aggregation/bulk

Trong hệ multi-tenant, câu query:

```java
orders.aggregate(
    Arrays.asList(
        Aggregates.match(
            Filters.eq("status", "PAID")
        )
    )
);
```

có thể lấy orders thuộc **mọi tenants** nếu collection shared. Đây là lỗi bảo mật nếu caller chỉ được truy cập một tenant.

### 37.1. Lấy tenant từ identity tin cậy

```java
String tenantId = trustedAuthContext.getTenantId();
```

`trustedAuthContext` là service do ứng dụng cung cấp sau authentication/authorization, không phải giá trị frontend tự gửi.

Pipeline:

```java
Aggregates.match(
    Filters.and(
        Filters.eq("tenantId", tenantId),
        Filters.eq("status", "PAID")
    )
);
```

### 37.2. Bulk update cũng cần tenant scope

Không dùng:

```java
Filters.eq("_id", orderId)
```

nếu `_id` không đủ bảo đảm phạm vi theo data model/authorization. Với shared collection:

```java
Filters.and(
    Filters.eq("_id", orderId),
    Filters.eq("tenantId", tenantId)
)
```

Với upsert, phải xác minh business key và inserted fields bao gồm tenant đúng, không để caller ghi vào tenant khác.

### 37.3. Không log raw documents

Các pipeline/bulk errors có thể chứa field names, values hoặc command metadata nhạy cảm. Log:

```text
traceId
jobId
tenant scope (theo policy)
operationType
requestIndex
errorCode
batchSize
duration
```

Không log passwords, MongoDB URI, document body/PII, raw query vector hoặc tokens nếu policy không cho phép.

## 38. Observability cho aggregation và bulk

Một ETL/batch job nên có metrics:

### 38.1. Read path

- Aggregation duration;
- Rows yielded;
- `getMore` frequency;
- Read batches/latency;
- Server operation latency;
- Query plan/scan efficiency;
- Disk spill;
- Cursor errors;
- Heap usage và GC;
- Source lag.

### 38.2. Write path

- Bulk calls;
- Models attempted;
- Inserted/matched/modified/deleted/upserts;
- Partial failures;
- Duplicate key count;
- Write concern errors;
- Retry count;
- Write p95/p99;
- Batch bytes/operations;
- Target storage/replication lag.

### 38.3. Business/completeness

- Eligible source documents;
- Processed documents;
- Last committed watermark;
- Target documents/current revisions;
- Failed/rejected records;
- Reconciliation difference;
- Last successful job run;
- RPO/freshness target.

### 38.4. Phân biệt “processed” và “committed”

Nếu cursor đọc 10.000 rows nhưng bulkWrite mới commit 9.600, dashboard phải phản ánh:

```text
rowsRead = 10000
rowsAttemptedToWrite = 10000
rowsAcknowledgedOrReconciled = 9600
rowsPendingOrFailed = 400
```

Không dùng một counter `processed` làm bằng chứng đã ghi đủ dữ liệu.

## 39. Bài toán memory và throughput

Có một số tham số cần tune cùng nhau:

```text
readBatchSize
writeBatchSize
maxBufferedBytes
workerConcurrency
MongoClient maxPoolSize
serverSelectionTimeout
maxTimeMS / application deadline
writeConcern
```

### 39.1. Batch nhỏ

Ưu điểm:

- Bộ nhớ thấp;
- Dễ retry từng phần;
- Giảm blast radius khi lỗi.

Nhược điểm:

- Nhiều round trips;
- Tăng overhead mỗi bulk;
- Throughput thấp hơn khi network latency lớn.

### 39.2. Batch lớn

Ưu điểm:

- Giảm số round trips;
- Có thể tăng throughput khi documents nhỏ và server đủ headroom.

Nhược điểm:

- Peak heap cao;
- Partial failures phức tạp;
- Latency của mỗi batch cao;
- Dễ dồn tải lên server;
- Có thể gây GC pauses.

### 39.3. Concurrency

Nếu chạy 20 workers song song, mỗi worker có write buffer 1.000 docs:

```text
Up to 20.000 pending write models
+ Current read batches
+ Decoded BSON objects
+ Network buffers
+ Driver pools
```

Cần hạn chế tổng memory và concurrent writes, không chỉ nhìn một worker.

### 39.4. Little's Law và số operations đang chạy

Một quan hệ khái quát:

\[
L \approx \lambda W
\]

Trong hệ ổn định:

- \(L\): số operations trung bình đang xử lý/chờ;
- \(\lambda\): throughput operations/giây;
- \(W\): thời gian trong hệ thống (giây).

Ví dụ 200 write operations/s, mỗi write trung bình 0,05 s, concurrency trung bình khoảng 10. Đây không phải công thức tính `maxPoolSize` chính xác; còn burst, batch, server selection, query mix và tail latency.

## 40. Kịch bản kiểm thử hiệu năng

Tạo một staging dataset đại diện, không dùng production không được phép.

### 40.1. Các tham số thử

| Trial | Read batch | Write batch | Workers |
|---|---:|---:|---:|
| A | 100 | 100 | 1 |
| B | 250 | 400 | 1 |
| C | 500 | 1000 | 1 |
| D | 250 | 400 | 4 |
| E | 500 | 1000 | 8 |

### 40.2. Các chỉ số

- Tổng thời gian job;
- Documents/second;
- Read/network bytes;
- Bulk p95/p99;
- Heap peak;
- GC pause;
- CPU/disk/cache;
- Connection pool wait;
- Replication lag;
- Errors/retries;
- Target integrity.

### 40.3. Không chọn chỉ dựa throughput cao nhất

Nếu D đạt 30.000 docs/s còn E đạt 32.000 docs/s nhưng heap tăng gấp bốn và p99 trên API production tăng, D có thể là lựa chọn an toàn hơn.

### 40.4. Có thể dùng backpressure

Một pipeline:

```text
Cursor reader (1 thread)
       │
       ▼
Bounded queue (max 1000 records)
       │
       ▼
Transform workers (limited)
       │
       ▼
Bounded write buffers
       │
       ▼
bulkWrite
```

Queue đầy thì reader **chậm lại**, thay vì tiếp tục lấy dữ liệu đến OOM. Cần xử lý cancellation và shutdown để không bỏ records sau khi báo job complete.

## 41. Đọc dữ liệu theo lô với `find()` thay aggregation

Khi không cần grouping/transformation trên server, `find()` có thể đơn giản hơn:

```java
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;

FindIterable<Document> iterable = orders.find(
    Filters.eq("tenantId", "T-01")
)
.projection(
    Projections.include("_id", "customerId", "amountCents")
)
.sort(Sorts.ascending("_id"))
.batchSize(300);

try (MongoCursor<Document> cursor = iterable.iterator()) {
    while (cursor.hasNext()) {
        Document order = cursor.next();
        process(order);
    }
}
```

### 41.1. `FindIterable` và `AggregateIterable` giống ở đâu?

Cả hai hỗ trợ duyệt bằng cursor và có batch size. Các kết quả không nhất thiết được materialize toàn bộ trong JVM.

### 41.2. Khác nhau ở đâu?

- `find()` tập trung truy vấn documents với filter, projection, sort.
- `aggregate()` hỗ trợ transformation, group, join, facets, stages phức tạp.
- Các tùy chọn khả dụng khác nhau.
- Chi phí server khác nhau theo pipeline/query shape.

Đừng dùng aggregation phức tạp khi `find()` đã đáp ứng, và đừng tải toàn bộ dữ liệu về Java để group nếu MongoDB có thể group hiệu quả bằng pipeline.

## 42. Cursor vòng lặp có phải phân trang API không?

Không hoàn toàn.

Một API có thể cần:

```text
GET /orders?pageSize=20&cursor=...
```

Cursor MongoDB trong Java là resource server-side/client-side cho quá trình duyệt. Không nên gửi trực tiếp nội bộ `MongoCursor` vào token frontend.

### 42.1. API pagination ổn định

Nên có:

- Sort key ổn định;
- Tie-breaker như `_id`;
- Limit hợp lý;
- Cursor token do backend phát hành;
- Tenant/auth scope;
- Token signing nếu cần;
- Xử lý dữ liệu cập nhật giữa pages.

### 42.2. `skip()` offset lớn có chi phí

Ví dụ:

```java
orders.find(Filters.eq("tenantId", "T-01"))
    .sort(Sorts.ascending("_id"))
    .skip(500_000)
    .limit(20);
```

Server có thể phải đi qua nhiều records trước khi trả trang. Keyset pagination có thể tốt hơn cho dữ liệu lớn.

### 42.3. Đừng biến `batchSize()` thành pageSize công khai

`batchSize(500)` trên một cursor đọc 2 triệu rows không có nghĩa client sẽ nhận đúng 500 items rồi có thể tự lưu cursor qua nhiều HTTP requests. API pagination cần thiết kế riêng cho lifecycle và security.

## 43. Cần chú ý khi dùng Java POJO thay `Document`

Có thể định nghĩa:

```java
public class Order {
    private String id;
    private String tenantId;
    private String customerId;
    private long amountCents;

    // Public no-arg constructor, getters/setters,
    // mapping annotations hoặc codec conventions tùy cấu hình.
}
```

Rồi sử dụng `MongoCollection<Order>` khi registry/codec hỗ trợ POJO mapping.

### 43.1. Aggregation output khác source type

Một source `Order` có fields order, nhưng `$group` trả:

```javascript
{
  _id: "C-105",
  grossCents: NumberLong("349900"),
  orderCount: 2
}
```

Không thể mặc định decode kết quả group vào `Order` vì cấu trúc khác.

Các lựa chọn:

```java
AggregateIterable<Document> rows =
    orders.aggregate(pipeline, Document.class);
```

hoặc một DTO riêng khi codec/mapping được cấu hình đúng.

### 43.2. DTO gắn với ngữ nghĩa

```java
public class RevenueRow {
    private String id;
    private long grossCents;
    private long orderCount;

    // Constructors/getters/setters theo codec.
}
```

Cần kiểm tra BSON `_id` mapping và accumulator result types. Với `Decimal128`, dùng kiểu phù hợp thay vì ép sang `long`.

### 43.3. Không ép kiểu dữ liệu tiền một cách tùy tiện

Nếu nguồn dùng `NumberDecimal`, output của `$sum` có thể là `Decimal128`. Một phép:

```java
Long gross = row.getLong("grossCents");
```

có thể sai type. Đọc bằng `get()` rồi xử lý có kiểm soát hoặc dùng codec/DTO đúng.

## 44. Aggregation với `$facet`: cân nhắc bộ nhớ

`$facet` cho phép nhiều nhánh xử lý trên cùng input:

```javascript
db.orders.aggregate([
  { $match: { tenantId: "T-01" } },
  {
    $facet: {
      byStatus: [
        { $group: { _id: "$status", count: { $sum: 1 } } }
      ],
      recent: [
        { $sort: { createdAt: -1 } },
        { $limit: 10 }
      ]
    }
  }
]);
```

Kết quả thường là một document chứa nhiều arrays nhánh. Nó có những giới hạn kích thước/memory theo MongoDB version và stage; không thể chỉ đặt `batchSize(100)` để tránh một `$facet` result document quá lớn.

### 44.1. Batch size không chia một BSON document ra nhiều phần

Nếu một output document quá lớn, giảm batch size không giải quyết giới hạn BSON document. Phải thay pipeline để mỗi output record nhỏ hơn hoặc thiết kế phân trang/streaming khác.

### 44.2. Khi nào nên tách queries?

Nếu các nhánh khác nhau cần nhiều indexes hoặc có bottleneck memory, đôi khi hai queries riêng hiệu quả hơn một `$facet`. Benchmark với dữ liệu thực.

## 45. `$sort`, `$group`, `$limit` và thứ tự pipeline

Ví dụ hai pipelines:

```text
A: $match → $sort → $limit → $group
B: $match → $group → $sort → $limit
```

Chúng **không tương đương**.

A nhóm **một subset** đã được giới hạn. B nhóm toàn bộ documents khớp `$match`, sau đó chọn top groups.

Trong bài toán “top customers theo revenue”, thường cần B (hoặc biến thể đúng nghĩa). Không đưa `$limit` lên đầu chỉ để query nhanh hơn mà bỏ qua yêu cầu nghiệp vụ.

### 45.1. `$match` càng sớm càng tốt khi semantics cho phép

Lọc sớm thường giảm dữ liệu cho `$group`/`$sort`, và có thể tận dụng index.

### 45.2. Projection không được bỏ field cần ở stage sau

Nếu `$project` bỏ `amountCents` trước `$group` tính tổng, output sẽ sai. Chỉ thu gọn fields **sau khi xác định dependencies** của các stages.

### 45.3. Sort trước group khác sort sau group

Sort theo `createdAt` trước group không tự có nghĩa group results được sort theo doanh thu. Mỗi stage thay hình dạng/tập dữ liệu.

## 46. Xử lý exception khi đọc cursor

Một cursor có thể lỗi khi gọi `hasNext()` hoặc `next()`:

```java
try (MongoCursor<Document> cursor =
         orders.aggregate(pipeline).iterator()) {

    while (cursor.hasNext()) {
        Document row = cursor.next();
        process(row);
    }

} catch (com.mongodb.MongoException ex) {
    // Ghi errorCode/category, traceId, jobId.
    // Quyết định retry/resume theo checkpoint và idempotency.
    throw ex;
}
```

Có thể xảy ra:

- Server selection/connection loss;
- Network timeout;
- Cursor killed/expired;
- Operation exceeded time limit;
- Primary failover;
- Authorization failure;
- Data decoding/codec exception.

### 46.1. Đọc một nửa rồi exception không phải “không đọc gì”

Nếu đã xử lý 10.000 rows rồi cursor fail, ứng dụng có thể đã ghi/đẩy dữ liệu tương ứng. Không retry toàn bộ mà bỏ qua idempotency.

### 46.2. Không giữ cursor sống qua thời gian chờ người dùng

Không nên tạo cursor trong một HTTP request rồi chờ user bấm “tiếp tục” sau vài giờ để dùng lại. Dùng API pagination token và query lại theo keyset nếu nghiệp vụ cần.

## 47. `getMore` và operational metrics

Khi batch size nhỏ hoặc result set lớn, MongoDB driver phải gọi thêm `getMore`.

Theo dõi:

```text
aggregate command duration
getMore command count
getMore duration
total cursor lifetime
rows returned
rows/sec
bytes received
```

`CommandListener` của Java Driver có thể quan sát commands theo name (như `aggregate`, `getMore`, `bulkWrite` có thể biểu hiện thành các commands ghi tương ứng tùy driver/server). Không giả định mọi bulk được gửi với command tên `"bulkWrite"` trên mọi phiên bản; driver có thể gửi các write commands theo loại thao tác.

### 47.1. Nhiều `getMore` có phải lỗi?

Không. Đó là phần bình thường của cursor protocol. Nó chỉ đáng tối ưu khi round-trip overhead, network RTT hoặc latency đang ảnh hưởng throughput.

### 47.2. Không in raw command bodies

Command documents có thể chứa PII, tenant data hoặc update payload. Logging/tracing nên giới hạn fields an toàn.

## 48. Java Command Monitoring

Một listener đơn giản:

```java
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandSucceededEvent;
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandStartedEvent;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class SafeCommandMetrics
        implements CommandListener {

    private final LongAdder successes = new LongAdder();
    private final LongAdder failures = new LongAdder();
    private final LongAdder totalMicros = new LongAdder();

    @Override
    public void commandStarted(CommandStartedEvent event) {
        // Không log event.getCommand() vì có thể chứa dữ liệu nhạy cảm.
    }

    @Override
    public void commandSucceeded(CommandSucceededEvent event) {
        successes.increment();
        totalMicros.add(
            event.getElapsedTime(TimeUnit.MICROSECONDS)
        );
    }

    @Override
    public void commandFailed(CommandFailedEvent event) {
        failures.increment();
        totalMicros.add(
            event.getElapsedTime(TimeUnit.MICROSECONDS)
        );
    }

    public long getSuccesses() {
        return successes.sum();
    }

    public long getFailures() {
        return failures.sum();
    }
}
```

Đăng ký với `MongoClientSettings`:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");

SafeCommandMetrics metrics = new SafeCommandMetrics();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .addCommandListener(metrics)
    .build();

MongoClient client = MongoClients.create(settings);
```

Trong ứng dụng thực, dùng histogram/metrics backend thay vì chỉ một tổng thời gian. Cần phân tách `aggregate`, `getMore`, insert/update/delete và các lỗi command.

## 49. Connection pool và concurrency

MongoDB Java Sync Driver quản lý connection pools theo server/topology.

Nếu batch job mở hàng chục cursors và chạy rất nhiều bulks song song:

- Pool checkout wait có thể tăng;
- Connections active tăng;
- Server CPU/I/O tăng;
- Application heap/threads tăng;
- API traffic chung có thể bị ảnh hưởng.

### 49.1. Một `MongoClient` dùng chung

Không tạo một `MongoClient` cho mỗi 400 writes; cách đó tạo connection/TLS/authentication overhead và pool churn.

### 49.2. Worker concurrency nên có giới hạn

Một số thiết kế:

```text
One shared MongoClient
    │
    ├── ETL worker A
    ├── ETL worker B
    ├── ETL worker C
    └── Web API (tách workload ưu tiên nếu cần)
```

Nếu ETL chạy chung cluster với API quan trọng, có thể cần throttling hoặc maintenance window để không ảnh hưởng latency của người dùng.

### 49.3. Đừng tăng `maxPoolSize` vô hạn

Pool lớn hơn có thể làm giảm thời gian chờ ở JVM trong một số trường hợp nhưng dồn nhiều operations xuống MongoDB, làm server nghẽn hơn. Cân bằng bằng load tests và metrics.

## 50. Lưu trữ kết quả aggregation: Java bulk hay `$merge`?

| Tiêu chí | Cursor + Java `bulkWrite` | Server-side `$merge` |
|---|---|---|
| Logic Java tùy chỉnh | Linh hoạt | Giới hạn theo aggregation expressions |
| Network từ server tới app | Có, theo output | Thường ít hơn |
| JVM memory | Có buffer và transforms | Không cần giữ results ở Java |
| Kiểm soát từng write model | Rõ ràng | Theo `$merge` options |
| Idempotency | Do app thiết kế | Do keys/merge semantics thiết kế |
| Xử lý external services | Dễ tích hợp | Không trực tiếp |
| Error/retry orchestration | Ứng dụng xử lý | Theo aggregation/write semantics |
| Ghi nhiều collections | Có thể gọi riêng từng collection | Stage `$merge` đích một collection mỗi pipeline |
| Transaction toàn tập | Không mặc định | Không mặc định |
| Checkpoint/restart | Ứng dụng cần xây | Cần chiến lược chạy lại/reconciliation |

Không gọi `$merge` và `bulkWrite` là hai đường triển khai luôn tương đương. Chúng có những điều kiện xử lý khi dữ liệu nguồn thay đổi và target pre-existing records khác nhau.

## 51. Quản lý toàn bộ job theo state machine

Một ETL production nên có trạng thái rõ ràng:

```text
PENDING
   │
   ▼
RUNNING
   │
   ├── source cursor
   ├── transform
   ├── bulk write
   └── checkpoint
   │
   ├── success → COMPLETED
   ├── transient error → RETRYING
   ├── permanent error → FAILED
   └── cancellation → CANCELLED
```

Metadata ví dụ:

```javascript
{
  _id: "JOB-20261114-001",
  pipelineVersion: "v3",
  tenantId: "T-01",
  sourceCollection: "orders",
  targetCollection: "orderExports",
  state: "RUNNING",
  lastCommittedId: "ORD-4500",
  rowsRead: NumberLong("4500"),
  rowsAcknowledged: NumberLong("4400"),
  failures: 0,
  startedAt: ISODate("2026-11-14T03:00:00Z")
}
```

Đây chỉ là mô hình, không phải cơ chế exactly-once tự động.

### 51.1. Lease và tránh chạy trùng

Nếu có nhiều scheduler instances, có thể hai jobs cùng quét và ghi target. Dùng job lease/ownership hoặc thiết kế idempotent/concurrency-safe. Một distributed lock tự xây cũng cần expiration/renewal semantics; không coi `status: RUNNING` là lock an toàn.

### 51.2. Version pipeline

Nếu logic transform thay đổi, checkpoint từ pipeline v1 không tự phù hợp với v2. Lưu `pipelineVersion` để quyết định resume hay rebuild.

### 51.3. Job kết thúc nhưng nguồn vẫn đổi

Nếu nguồn liên tục có writes, hoàn thành scan lịch sử không đồng nghĩa target đã cập nhật đến hiện tại. Cần change stream, CDC/outbox hoặc periodic reconciliation.

## 52. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| `aggregate()` tạo iterable rồi không duyệt | Pipeline chưa thực sự chạy | Tiêu thụ iterable |
| `into(new ArrayList<>())` trên triệu rows | OOM/JVM GC | Cursor streaming |
| Dùng `batchSize` như `limit` | Trả nhiều dữ liệu hơn dự kiến | Dùng `$limit` hoặc `limit()` |
| Giả định batch luôn đúng N docs | Sai logic processing | Xử lý từng record |
| Không đóng cursor | Giữ tài nguyên server/client | Try-with-resources |
| Coi Sync Driver là non-blocking | Thread bị chờ I/O | Thiết kế threads/Reactive khi cần |
| `allowDiskUse(true)` là tối ưu mặc định | Disk spill vẫn đắt | Index/query plan/resource review |
| Dùng `$limit` trước `$group` cho top revenue | Sai kết quả | Giữ pipeline semantics |
| Một bulk hàng triệu write models | OOM, retry khó | Chunk bounded writes |
| Quên flush buffer cuối | Mất records | Flush sau vòng lặp |
| Clear buffer trước khi write | Mất dữ liệu khi lỗi | Chỉ clear sau thành công |
| Coi bulkWrite atomic cho cả nhóm | Partial writes ngoài ý muốn | Transaction hoặc idempotency |
| Dùng unordered cho writes phụ thuộc thứ tự | Kết quả không ổn định | Ordered/logic khác |
| Retry toàn bộ `$inc` sau timeout | Double increment | Reconcile/idempotency |
| Coi error là “chưa ghi gì” | Sai trạng thái | Partial result/verification |
| Chỉ đọc `getInsertedCount` | Bỏ qua upserts/matched | Đọc đúng counters |
| Dùng acknowledged=false cho ETL | Không biết write result | Write concern phù hợp |
| Key target không có tenant | Cross-tenant corruption | Compound business key |
| Checkpoint trước commit | Bỏ sót records | Checkpoint sau xác nhận |
| Quét `skip` trên dữ liệu đang đổi | Duplicate/missing | Keyset + CDC/reconcile |
| Dùng `majority` như snapshot toàn job | Dữ liệu không đồng thời | Snapshot/capture plan |
| Upsert mà không xử lý deletes | Target stale | Tombstones/reconciliation |
| Materialized view không xóa groups cũ | Tổng cũ còn tồn tại | Full reconciliation |
| Chỉ đo read rows, không đo committed writes | Báo job thành công sai | Metrics hai phía |
| Tạo MongoClient mỗi batch | Connection churn | Shared client |
| Log raw query/URI | Lộ secrets/PII | Redaction |
| Không giới hạn worker concurrency | Quá tải DB/pool | Backpressure |
| Chỉ thử 100 records | Không thấy memory/performance | Representative load test |
| Dùng POJO nguồn để decode `$group` output | Mapping failure | DTO/Document phù hợp |

## 53. Bài tập thực hành

### Bài 1 — Aggregation builders

Từ `orders`, viết pipeline Java dùng `Aggregates` và `Filters`:

- Lọc `tenantId = T-01`;
- Chỉ trạng thái `PAID`;
- Ngày thuộc tháng 11/2026;
- Nhóm theo `customerId`;
- Tính tổng `amountCents` và số order;
- Sắp tổng giảm;
- Trả top 20.

Giải thích vị trí `$match`, `$group`, `$sort`, `$limit`.

### Bài 2 — `Document` so với builders

Viết cùng pipeline theo hai phong cách. So sánh:

1. Độ dễ đọc;
2. Khả năng dùng stage mới;
3. Khả năng tái sử dụng;
4. Rủi ro gõ sai fields;
5. Cách validate user input.

### Bài 3 — `batchSize` vs `limit`

Pipeline trả 10.000 documents, `.batchSize(200)`.

1. Có phải kết quả chỉ 200 không?
2. Số batch dự kiến?
3. Vì sao batch thực không nhất thiết đúng 200?
4. Nếu chỉ muốn 200 kết quả phải thêm gì?
5. Nếu một document vượt BSON size limit, giảm batch size có giúp không?

### Bài 4 — Cursor lifecycle

Viết Java code:

- Dùng `MongoCursor<Document>`;
- Đọc tối đa 1.000 records;
- Dừng sớm khi có business condition;
- Đóng cursor;
- Bắt `MongoException`;
- Ghi metrics an toàn.

### Bài 5 — Memory

Một aggregate trả 2 triệu rows, mỗi row trung bình 2 KiB.

1. Vì sao `into(ArrayList)` có thể OOM?
2. Kích thước logical payload khoảng bao nhiêu?
3. Overhead Java có thể làm memory thực khác thế nào?
4. Chọn read batch size ra sao?
5. Projection giúp giảm network/heap thế nào?

### Bài 6 — Ordered/unordered

Bulk có năm operations, thứ ba vi phạm unique index.

1. Ordered sẽ xảy ra gì?
2. Unordered có thể xảy ra gì?
3. Cả nhóm có atomic không?
4. Khi nào không được dùng unordered?
5. Có thể retry toàn bộ danh sách không?

### Bài 7 — `BulkWriteResult`

Một bulk trả:

```text
insertedCount = 100
matchedCount = 200
modifiedCount = 170
deletedCount = 20
upserts = 15
```

1. Vì sao matched khác modified?
2. Upserts có nhất thiết nằm trong insertedCount không?
3. Nếu unacknowledged thì metrics nào không chắc chắn?
4. Những chỉ số nào phải log sau partial failure?

### Bài 8 — Retry `$inc`

Một update tăng `totalRevenue` thêm 100.000 cents bị timeout sau khi server có thể đã ghi.

1. Retry thủ công có rủi ro gì?
2. Vì sao `$set` về trạng thái cuối có thể an toàn hơn?
3. Cần business idempotency key nào?
4. Majority write concern có tự giải quyết không?
5. Viết cách reconciliation.

### Bài 9 — Full batch flush

Dùng write buffer 400 và 1.050 input records.

1. Có bao nhiêu full batches?
2. Có bao nhiêu record cuối?
3. Khi nào gọi `flush()`?
4. Nếu batch cuối lỗi, checkpoint phải phản ánh gì?
5. Nếu job chết ngay sau ACK trước checkpoint, resume an toàn thế nào?

### Bài 10 — `MongoBulkWriteException`

Thiết kế handler:

- Lấy `getWriteErrors`;
- Map `getIndex` tới business IDs;
- Phân loại duplicate key vs validation vs transient;
- Lấy partial result;
- Xử lý write concern error;
- Lưu dead-letter;
- Không log raw PII.

### Bài 11 — ETL và source mutation

Một worker đọc source revision 7, worker khác ghi target revision 8 trước khi worker đầu hoàn thành.

1. Rủi ro stale overwrite là gì?
2. Check-then-update ở Java có atomic không?
3. Thiết kế version guard.
4. Cần unique key ra sao?
5. Nếu source bị xóa, target xử lý thế nào?

### Bài 12 — Checkpoint

Một job quét 100.000 records, bulk 500 mỗi lần.

1. Khi nào checkpoint `lastCommittedId`?
2. Nếu batch thành công một phần thì sao?
3. Vì sao cursor không tự lưu resume position?
4. So sánh offset và keyset pagination.
5. Nếu `_id` của record mới nhỏ hơn watermark thì sao?

### Bài 13 — `$merge` hay Java bulk

Bài toán tính revenue per customer:

1. Khi nào dùng `$merge`?
2. Khi nào cần logic Java?
3. Cái nào giảm network transfer?
4. Cách xử lý group không còn xuất hiện?
5. Cả hai có atomic all-documents không?

### Bài 14 — Transaction

Có hai writes phải thành công cùng nhau: cập nhật order và ghi payment record.

1. BulkWrite có đủ không?
2. Khi nào dùng multi-document transaction?
3. Session lifecycle ra sao?
4. Commit retry xử lý thế nào?
5. Vì sao không đưa 5 triệu operations vào một transaction?

### Bài 15 — Performance benchmark

Thử 3 cấu hình:

```text
A: readBatchSize=100, writeBatchSize=100, workers=1
B: readBatchSize=250, writeBatchSize=400, workers=2
C: readBatchSize=500, writeBatchSize=1000, workers=8
```

Đo:

- Throughput;
- Heap/GC;
- Command/getMore count;
- Bulk p95;
- Server CPU/disk/replication lag;
- Retry/errors;
- API p99 bị ảnh hưởng.

Chọn cấu hình phù hợp theo SLO thay vì chỉ số rows/sec.

### Bài 16 — Multi-tenant security

Một API export orders của tenant A.

1. Pipeline có tenant predicate ở đâu?
2. Bulk target key nên thiết kế thế nào?
3. User có được tự gửi tenantId khác không?
4. Logs nên chứa fields nào?
5. Nếu `$lookup` customers, cần kiểm tra quyền gì?

### Bài 17 — POJO/DTO

Source `Order` dùng `Decimal128` cho amount, aggregation tính `$sum`.

1. Vì sao `getLong()` có thể không phù hợp?
2. Cần DTO dạng gì?
3. Cách configure codec?
4. Test round-trip và overflow ra sao?
5. Vì sao aggregate output không nhất thiết có schema nguồn?

### Bài 18 — Phân tích incident

Một ETL job vừa được tăng batch từ 400 lên 10.000 và workers từ 2 lên 32, sau đó:

```text
Heap tăng gấp 5
GC pause kéo dài
Pool checkout timeout
Replica lag tăng
Bulk partial failures xuất hiện
```

Hãy:

1. Xác định những bottlenecks có thể xảy ra;
2. Đề xuất các metrics/logs/traces cần xem;
3. Nêu biện pháp giảm tải có kiểm soát;
4. Thiết kế rollback config;
5. Kiểm tra data completeness sau sự cố.

## 54. Checklist production

### Aggregation

- [ ] Pipeline dùng đúng business filters và tenant scope.
- [ ] `$match` được đẩy sớm khi semantics cho phép.
- [ ] Index/query plan được kiểm tra trên workload đại diện.
- [ ] Không có `COLLSCAN` không mong đợi trên đường nóng.
- [ ] `$group`, `$sort`, `$lookup`, `$facet` được đánh giá memory/disk.
- [ ] `allowDiskUse` chỉ dùng với hiểu biết về chi phí.
- [ ] Có `maxTime` và deadline phù hợp.
- [ ] Không log raw dữ liệu nhạy cảm.
- [ ] Kiểu BSON của kết quả được xử lý đúng.
- [ ] Dữ liệu liên tục thay đổi có consistency strategy.

### Cursor và đọc theo lô

- [ ] Dùng cursor streaming khi result lớn.
- [ ] Không dùng `into(List)` trên dữ liệu không giới hạn.
- [ ] `batchSize` khác `limit`.
- [ ] Đã tính đến `getMore` và network round trips.
- [ ] Cursor được đóng khi xong hoặc lỗi.
- [ ] Có backpressure/bounded queue khi dùng parallel processing.
- [ ] Có checkpoint bền vững nếu job cần resume.
- [ ] Checkpoint chỉ tăng khi writes đã xác minh.
- [ ] Chú ý dữ liệu thêm/sửa/xóa trong lúc scan.

### BulkWrite

- [ ] Chọn `ordered` theo dependencies thực tế.
- [ ] Mỗi batch có giới hạn số operations và memory.
- [ ] Flush buffer cuối.
- [ ] Partial write success/error được xử lý.
- [ ] `BulkWriteResult` được đọc theo acknowledgment semantics.
- [ ] Upserts và matched/modified được phân biệt.
- [ ] Không retry không-idempotent writes mù quáng.
- [ ] Có business key/unique constraint phù hợp.
- [ ] Có retry budget/dead-letter/reconciliation.
- [ ] `bulkWrite` không bị nhầm thành transaction.
- [ ] Có write concern/timeout đúng nghiệp vụ.
- [ ] Không ghi đè source revision mới bằng dữ liệu cũ.

### Vận hành

- [ ] MongoClient dùng chung theo lifecycle.
- [ ] Có driver command/pool monitoring.
- [ ] Có read/write throughput, p95/p99 và error metrics.
- [ ] Có theo dõi heap/GC/CPU/disk/replication lag.
- [ ] Load test với dataset và concurrency đại diện.
- [ ] Có runbook dừng/resume/retry job.
- [ ] Có khả năng chứng minh data completeness.
- [ ] Không chứa passwords/PII trong logs hoặc batch metadata công khai.
- [ ] Có owner, alert và kế hoạch xử lý sự cố.

## 55. Tài liệu tham khảo

Đọc tài liệu cho **đúng phiên bản MongoDB Java Sync Driver và MongoDB Server đang sử dụng**:

- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Java Driver Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
- [Java Driver Bulk Write Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/)
- [Java Driver Read Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
- [Java Driver Update Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/)
- [MongoDB Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/)
- [MongoDB Aggregation Stages](https://www.mongodb.com/docs/manual/reference/operator/aggregation/)
- [MongoDB `aggregate` Command](https://www.mongodb.com/docs/manual/reference/command/aggregate/)
- [MongoDB `getMore` Command](https://www.mongodb.com/docs/manual/reference/command/getMore/)
- [MongoDB `bulkWrite` Command](https://www.mongodb.com/docs/manual/reference/command/bulkWrite/)
- [MongoDB Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Cursor Lifecycle](https://www.mongodb.com/docs/manual/core/cursors/)
- [MongoDB Java Driver Monitoring](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/)
- [MongoDB Java Driver Connection Pools](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/connection-pools/)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)

## Kết luận

Trong MongoDB Java Sync Driver, **aggregation**, **cursor/batch** và **`bulkWrite`** là ba công cụ phối hợp để xử lý khối lượng dữ liệu lớn mà vẫn kiểm soát được chi phí và tính đúng đắn.

**Aggregation** đưa lọc, nhóm, tính toán và join đến gần MongoDB server. Nên thiết kế pipeline dựa trên đúng semantics, tận dụng index và đo memory/disk usage. **`AggregateIterable`** là đối tượng kết quả được tiêu thụ khi ứng dụng duyệt; nếu pipeline có `$merge` hoặc `$out`, đừng chỉ tạo iterable rồi cho rằng write đã chạy.

**Cursor và `batchSize`** giúp đọc dần theo network batches thay vì bắt JVM giữ mọi kết quả. Nhưng `batchSize` không giới hạn tổng kết quả, không bảo đảm số lượng chính xác từng batch và không tự cung cấp checkpoint hay snapshot consistency. Với dữ liệu lớn, dùng `MongoCursor` trong try-with-resources, projection, timeout và bounded processing.

**`bulkWrite`** giảm overhead khi gom nhiều write models và cho phép ordered hoặc unordered semantics. Tuy vậy, **có thể thành công một phần**, counters có nhiều loại và cả bulk không tự có tính atomic như transaction. Thiết kế retry phải gắn với unique business key, idempotency, write concern, partial errors và reconciliation; đừng tăng lại `$inc` sau một timeout chưa xác minh.

Khi ghép ba kỹ thuật thành job ETL, thành công được đo bằng **số dữ liệu đã được xác nhận ghi đúng, khả năng resume an toàn, tenant isolation, throughput và p95/p99 không làm hỏng SLO của hệ thống**, chứ không chỉ bởi một vòng lặp đọc nhanh hoặc một bulk call trả về không lỗi.

**Cách làm bền vững là: lọc đúng ở server, đọc vừa đủ theo cursor, ghi theo batch có kiểm soát và luôn thiết kế tình huống lỗi/khởi chạy lại trước khi đưa job vào production.**

