# MongoCursor, giải phóng tài nguyên và xử lý tập dữ liệu lớn trong MongoDB Java Driver

## 1. Tại sao cần MongoCursor?

Một dịch vụ Java cần đọc 10 triệu tài liệu từ collection `orders` để xuất CSV, chuyển đổi dữ liệu hoặc đồng bộ sang hệ thống khác. Cách viết đầu tiên có thể là:

```java
List<Document> all = collection.find()
    .into(new ArrayList<>());

for (Document document : all) {
    process(document);
}
```

Đoạn mã này **thu thập toàn bộ kết quả vào bộ nhớ heap của Java**. Nó có thể phù hợp nếu truy vấn chỉ trả vài chục hoặc vài trăm bản ghi, nhưng rất nguy hiểm khi không có giới hạn số lượng:

- `OutOfMemoryError` khi tổng các object vượt heap.
- Garbage collector phải theo dõi một lượng lớn object sống lâu.
- Thời gian chờ kết quả hoàn tất dài trước khi xử lý những phần tử đầu tiên.
- Khó dừng sớm hoặc hủy một tác vụ dài.
- Khó kiểm soát lỗi khi dữ liệu thay đổi hoặc kết nối bị mất giữa chừng.

**`MongoCursor<TResult>`** cho phép đọc tuần tự các kết quả, trong khi driver chỉ giữ **một phần** dữ liệu trong bộ nhớ tại một thời điểm. Các kết quả được nhận từ MongoDB theo **batch**, sau đó ứng dụng xử lý từng tài liệu.

```text
MongoDB: 10,000,000 documents
                |
           find/aggregate
                |
                v
      Server-side cursor
                |
      firstBatch (e.g. 101)
                |
                v
        Java MongoCursor
                |
       hasNext() / next()
                |
           batch ended?
                |
       getMore next batch
                |
             ...
                |
     exhausted or close()
```

Tuy vậy, cursor **không tự động biến mọi chương trình thành memory-safe**: code vẫn có thể gom tài liệu vào `List`, giữ `Map` vô hạn hoặc đẩy tài liệu vào một hàng đợi không giới hạn. Cần kết hợp cursor, cấu trúc xử lý có giới hạn và chính sách giải phóng tài nguyên.

> **Nguyên tắc chính:** dữ liệu càng lớn, càng cần kiểm soát **vòng đời cursor, batch size, tốc độ xử lý và khả năng khôi phục từ checkpoint**. Chỉ dùng `cursor()` chưa đủ.

---

## 2. MongoCursor là gì trong Java Sync Driver?

Trong MongoDB Java Sync Driver, interface nằm tại:

```java
com.mongodb.client.MongoCursor<TResult>
```

`TResult` là kiểu dữ liệu driver trả ra: thường là `Document`, POJO được codec ánh xạ hoặc một dạng BSON phù hợp.

Theo API driver hiện đại:

- `MongoCursor<TResult>` kế thừa `Iterator<TResult>` và `Closeable` / `AutoCloseable`.
- `hasNext()` cho biết có phần tử tiếp theo hay không.
- `next()` lấy phần tử tiếp theo.
- `tryNext()` lấy phần tử nếu có hoặc trả `null` theo semantics của cursor.
- `available()` trả số tài liệu **sẵn có cục bộ và không cần blocking**, không phải số tài liệu tổng.
- `close()` kết thúc cursor và yêu cầu giải phóng tài nguyên.
- `getServerCursor()` có thể cho biết server-side cursor metadata nếu đang còn handle.
- Interface được đánh dấu **NotThreadSafe**, ngoại trừ việc có thể gọi `close()` đồng thời với phương thức khác để hủy cursor bị chặn theo hợp đồng API.

### 2.1. MongoCursor không phải một collection

`MongoCollection<Document>` đại diện collection và cung cấp thao tác query. `MongoCursor<Document>` đại diện **một lần duyệt kết quả** của một truy vấn.

### 2.2. MongoCursor không phải durable iterator

Một cursor đang mở phụ thuộc vào phiên kết nối, server-side cursor state, session và topology. Không được lưu cursor ID vào database rồi coi là checkpoint có thể resume sau process restart hoặc primary failover.

### 2.3. Java Sync Driver là blocking

`hasNext()` có thể đợi `getMore` qua mạng; `next()` và codec có thể tiêu thụ CPU. Duyệt bằng cursor giúp giới hạn bộ nhớ nhưng **không biến các lời gọi thành non-blocking**. Với Reactive Streams cần dùng driver/API reactive tương ứng.

---

## 3. Chuẩn bị ví dụ Java

Các đoạn mã dùng Java MongoDB Sync Driver và giả định `MongoCollection<Document>` đã được khởi tạo:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

String uri = System.getenv("MONGODB_URI");

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase database = client.getDatabase("sales");
    MongoCollection<Document> orders =
        database.getCollection("orders");

    // Gọi các ví dụ xử lý ở đây.
}
```

Trong ứng dụng web hoặc background worker thực tế, `MongoClient` thường được tạo **một lần cho vòng đời ứng dụng** để dùng connection pool, thay vì mở rồi đóng sau từng request hoặc từng tài liệu.

**Phân biệt vòng đời:**

| Đối tượng | Vòng đời điển hình |
| --- | --- |
| `MongoClient` | Dài hạn, theo tiến trình/service |
| `MongoDatabase` / `MongoCollection` handle | Có thể tái sử dụng |
| `FindIterable` / `AggregateIterable` | Cấu hình một query |
| `MongoCursor` | Một lần duyệt, cần được đóng |
| `ClientSession` | Một phạm vi thao tác/session rõ ràng |
| `BufferedWriter` / `OutputStream` | Một tệp xuất hoặc HTTP response |

Nếu dùng POJO thay `Document`, đảm bảo codec registry và data mapping tương thích, nhưng quy tắc cursor cleanup không đổi.

---

## 4. FindIterable khác MongoCursor như thế nào?

```java
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import org.bson.Document;

FindIterable<Document> iterable =
    orders.find(Filters.eq("status", "PAID"))
        .batchSize(500)
        .limit(10_000);

// Terminal operation tạo cursor/khởi tạo truy vấn.
try (MongoCursor<Document> cursor = iterable.cursor()) {
    while (cursor.hasNext()) {
        Document order = cursor.next();
        process(order);
    }
}
```

`FindIterable` cho phép cấu hình:

- `filter` từ `find(...)`.
- `sort(...)`, `projection(...)`.
- `limit(...)` và `skip(...)`.
- `batchSize(...)`.
- `maxTime(...)`, `noCursorTimeout(...)`.
- Các options khác theo API/driver version.

Gọi `find(...)` và thêm các options tạo đối tượng mô tả truy vấn; những thao tác **terminal** như `first()`, `into(...)`, `cursor()`/`iterator()` hoặc việc bắt đầu iterate mới thực thi truy vấn phù hợp.

### 4.1. Phương thức `cursor()` và `iterator()`

Cả hai được dùng trong tài liệu Java driver để bắt đầu duyệt. Khi muốn một tài nguyên có chủ sở hữu rõ và dễ dùng `try-with-resources`, hãy nhất quán với `cursor()`:

```java
try (MongoCursor<Document> cursor =
         orders.find().cursor()) {
    // ...
}
```

### 4.2. Không khởi tạo cursor quá sớm

Nếu bạn tạo cursor rồi mới chờ user upload file hoặc chờ external API rất lâu, server-side state có thể bị timeout. Chỉ khởi tạo ngay trước lúc có thể bắt đầu tiêu thụ.

---

## 5. Mẫu chuẩn: try-with-resources

Đây là mẫu nên dùng cho truy vấn trả nhiều documents:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public final class OrderReader {

    public static void consume(
            MongoCollection<Document> orders
    ) {
        try (MongoCursor<Document> cursor =
                 orders.find(
                     Filters.eq("status", "READY")
                 ).cursor()) {

            while (cursor.hasNext()) {
                Document order = cursor.next();
                process(order);
            }
        }
    }

    private static void process(Document order) {
        System.out.println(order.get("_id"));
    }
}
```

### 5.1. Tại sao phải đóng?

Một cursor chưa hoàn tất có thể còn server-side state, session, network buffers và tài nguyên driver liên quan. `close()` giúp yêu cầu giải phóng có chủ đích thay vì chờ timeout.

### 5.2. Khi nào Java tự gọi `close()`?

Với `try-with-resources`, Java đóng cursor khi rời khỏi scope, kể cả khi:

- Vòng lặp đọc hết.
- Gặp `break`.
- Có `return` trong khối.
- `process()` ném exception.
- `hasNext()` hoặc `next()` ném exception.
- Logic bên trong bị hủy theo luồng xử lý đã được thiết kế.

### 5.3. Cursor hết dữ liệu có tự đóng không?

MongoDB giải phóng cursor server-side khi đã exhausted. Tuy nhiên code thực tế có thể dừng sớm, nên `try-with-resources` vẫn là lựa chọn an toàn.

### 5.4. Đừng bỏ qua lỗi

Đóng cursor không đồng nghĩa tác vụ thành công. Nếu lỗi xuất CSV ở document thứ 500.000, phải đánh dấu job thất bại hoặc partial, không tự trả `COMPLETED`.

---

## 6. Vì sao enhanced for-each có rủi ro?

Java cho phép:

```java
for (Document order : orders.find()) {
    process(order);
}
```

Cách này ngắn, nhưng driver documentation cảnh báo: nếu exception xuất hiện hoặc vòng lặp kết thúc sớm, cursor **có thể không được đóng chủ động**.

Ví dụ:

```java
for (Document order : orders.find()) {
    if (isTarget(order)) {
        break;
    }
}
```

Đoạn code không có biến cursor để `close()` trong `finally`.

### 6.1. Viết lại

```java
try (MongoCursor<Document> cursor =
         orders.find().cursor()) {
    while (cursor.hasNext()) {
        Document order = cursor.next();
        if (isTarget(order)) {
            break;
        }
    }
}
```

### 6.2. Có thể dùng forEach của iterable không?

Có:

```java
orders.find().forEach(order -> process(order));
```

Nhưng khi cần dừng sớm, cancellation, checkpoint, output stream hoặc xử lý exception chi tiết, explicit `MongoCursor` giúp quản lý vòng đời rõ ràng hơn.

---

## 7. Đóng cursor khi `return` sớm

Ví dụ tìm tài liệu đầu tiên vi phạm quy tắc:

```java
public Document findFirstInvalid(
        MongoCollection<Document> orders
) {
    try (MongoCursor<Document> cursor =
             orders.find().cursor()) {

        while (cursor.hasNext()) {
            Document order = cursor.next();

            if (isInvalid(order)) {
                return order;
            }
        }
        return null;
    }
}
```

Dù `return` nằm bên trong `try`, Java vẫn đóng resource trước khi method trả về.

### 7.1. Có nên dùng `first()`?

Nếu điều kiện của bạn chỉ là truy vấn để lấy một bản ghi, `first()` thường gọn hơn:

```java
Document order = orders.find(
    Filters.eq("_id", orderId)
).first();
```

Dùng cursor explicit khi thực sự phải kiểm tra nhiều documents hoặc xử lý theo streaming.

---

## 8. Cơ chế firstBatch và getMore

MongoDB không gửi toàn bộ kết quả nhiều triệu tài liệu trong một network response.

```text
Java find()
    |
    v
Server executes find
    |
    v
First batch + cursor ID
    |
    v
Java consumes documents in first batch
    |
    v
Has more server-side results?
   | yes
   v
getMore(cursor ID)
    |
    v
Next batch
    |
    v
Repeat until exhausted/close
```

### 8.1. Giới hạn batch theo tài liệu MongoDB

Với lệnh `find` thông thường:

- First batch mặc định tối đa **101 documents hoặc khoảng 16 MiB**, tùy giới hạn nào đạt trước.
- Các batch tiếp theo được lấy qua `getMore`.
- Khi không chỉ định batch size, subsequent batches bị giới hạn bởi khoảng **16 MiB**.
- Khi đặt batch size, server có thể trả ít hơn số documents yêu cầu vì giới hạn bytes hoặc batch cuối.
- Một BSON document vẫn chịu giới hạn 16 MiB độc lập.

### 8.2. Cursor ID là tài nguyên server tạm thời

Nếu query chưa exhausted, server có thể trả cursor ID khác 0. Nếu toàn bộ kết quả vừa một batch, server có thể không cần giữ cursor mở.

Không dùng cursor ID làm ID tài liệu, version, token phân trang public hoặc checkpoint sau restart.

### 8.3. Batching không tạo snapshot bất biến

Nhiều `getMore` có thể diễn ra trong lúc writers khác insert/update/delete. Một ordinary cursor không mặc nhiên bảo đảm toàn bộ dữ liệu của các batch là trạng thái của database tại cùng một thời điểm.

---

## 9. Điều chỉnh batchSize

```java
try (MongoCursor<Document> cursor =
         orders.find(
             Filters.eq("status", "READY")
         )
         .batchSize(500)
         .cursor()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

`batchSize(500)` có nghĩa yêu cầu **tối đa khoảng 500 documents trong một batch**, còn phụ thuộc byte limit và điều kiện server.

**Không có nghĩa truy vấn chỉ trả 500 documents.** Muốn tổng tối đa 500:

```java
orders.find(filter)
    .limit(500);
```

### 9.1. Batch nhỏ

Có thể phù hợp nếu:

- Documents lớn, nhiều arrays hoặc strings.
- Xử lý từng record chậm.
- Nhiều cursors hoạt động đồng thời.
- Cần phản hồi sớm đến client.
- Muốn tránh giữ batch cục bộ quá lớn.

Đổi lại số lần `getMore` và round trips có thể tăng.

### 9.2. Batch lớn

Có thể giúp giảm network round trips khi:

- Documents nhỏ.
- Pipeline xử lý nhanh.
- Network latency lớn.
- Có memory headroom.
- Cần throughput cao.

Nhưng có thể tăng batch buffer/GC pressure và thời gian xử lý trước lần `getMore` kế tiếp.

### 9.3. Không có batch size tối ưu cho mọi workload

Thử các mức có ý nghĩa như 100, 250, 500, 1000, đồng thời đo document throughput, heap, GC, getMore latency và tác động tới các queries khác.

---

## 10. Phân biệt `limit`, `batchSize`, `skip` và `into`

| Thao tác | Mục đích |
| --- | --- |
| `limit(100)` | Giới hạn **tổng** số documents kết quả |
| `batchSize(100)` | Điều chỉnh **số documents trên mỗi batch** |
| `skip(100)` | Bỏ qua 100 documents đầu theo query |
| `first()` | Lấy một document đầu hoặc null |
| `into(list)` | Thu toàn bộ kết quả vào collection đích |
| `countDocuments(filter)` | Đếm documents khớp filter |
| `cursor()` | Nhận một `MongoCursor` để duyệt thủ công |

Ví dụ dễ gây OOM:

```java
List<Document> all = orders.find()
    .batchSize(100)
    .into(new ArrayList<>());
```

Dù fetch theo batch 100, toàn bộ documents cuối cùng vẫn vào `all`.

Nếu cần chỉ 100 records:

```java
List<Document> page = orders.find()
    .sort(Sorts.ascending("_id"))
    .limit(100)
    .into(new ArrayList<>());
```

Với 100 kết quả, dùng `into` có thể hợp lý. Vấn đề là **tập dữ liệu không có giới hạn**, không phải bản thân `into()` luôn sai.

---

## 11. `available()` là số kết quả cục bộ, không phải tổng số

```java
try (MongoCursor<Document> cursor =
         orders.find().cursor()) {
    int immediatelyAvailable = cursor.available();
    System.out.println(immediatelyAvailable);
}
```

`available()` cho biết số documents đang sẵn có ở client **mà không phải đợi đọc thêm từ server**.

Nó không phải:

- Tổng số tài liệu khớp filter.
- Tổng documents trong collection.
- Số documents chắc chắn còn ở server.
- Dấu hiệu đáng tin cậy để kết luận server cursor đã được close.

Khi cursor exhausted, `available()` thường là 0. Một implementation vẫn có thể báo documents còn buffer sau khi cursor bị đóng sớm, theo semantics API; không dùng `available()` để kiểm tra trạng thái đã đóng.

### 11.1. Sai lầm thường gặp

```java
int total = orders.find().cursor().available();
```

Sai về ý nghĩa, và còn tạo cursor mà không được close.

### 11.2. Khi cần count

```java
long total = orders.countDocuments(
    Filters.eq("status", "READY")
);
```

Tuy nhiên count có chi phí thực thi. Một API phân trang không nhất thiết phải chạy exact count ở mọi request.

### 11.3. Không dùng available làm điều kiện lặp

Sai:

```java
while (cursor.available() > 0) {
    process(cursor.next());
}
```

Nó có thể dừng khi hết batch cục bộ dù server còn dữ liệu. Dùng:

```java
while (cursor.hasNext()) {
    process(cursor.next());
}
```

---

## 12. `hasNext()`, `next()` và `tryNext()`

### 12.1. hasNext()

```java
boolean has = cursor.hasNext();
```

Kiểm tra document tiếp theo có tồn tại. **Có thể block** khi cần yêu cầu batch kế tiếp qua mạng.

### 12.2. next()

```java
Document next = cursor.next();
```

Trả document tiếp theo. Nếu đã hết, việc gọi tiếp có thể gây `NoSuchElementException` theo iterator contract.

### 12.3. tryNext()

```java
Document maybe = cursor.tryNext();
```

Một phương thức đặc biệt có thể trả `null` nếu chưa có phần tử sẵn sàng. Nó hữu ích nhất khi thiết kế tailable cursor hoặc change stream có trạng thái “chưa có sự kiện mới”.

### 12.4. Không hiểu null là dữ liệu đã hết mãi mãi

Với tailable/change streams, `tryNext() == null` không nhất thiết là tín hiệu stream kết thúc. Cần phân biệt cursor thường hữu hạn và cursor chờ events.

---

## 13. Tập dữ liệu lớn và bộ nhớ Java

Giả sử trung bình một Java `Document` đã decode chiếm 12 KiB.

```text
1 document:          12 KiB
500 documents:     5.9 MiB
1 million docs:   11.4 GiB
10 million docs:   114 GiB
```

Đây chỉ là phép tính minh họa, không phải kích thước chắc chắn của mọi document. Object overhead, strings, arrays, codec buffers, metadata và garbage collector đều làm giá trị thực khác đi.

### 13.1. Mô hình bounded processing

```text
MongoCursor
    |
    v
Read one
    |
    v
Transform
    |
    v
Write to bounded sink
    |
    v
Discard reference
    |
    v
Read next
```

### 13.2. Mô hình unbounded processing

```text
MongoCursor
    |
    v
Keep appending to ArrayList/HashMap
    |
    v
Millions of live objects
    |
    v
GC pressure / OOM
```

Việc dùng cursor mà sau đó gọi `buffer.add(cursor.next())` vô hạn **không bảo vệ heap**.

---

## 14. Ví dụ đọc theo luồng với filter, sort và projection

Giả sử collection:

```javascript
{
  _id: ObjectId("691800000000000000000001"),
  tenantId: "T100",
  status: "PAID",
  customerId: "C100",
  totalMinor: 199000,
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

Java:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public final class OrderScan {

    public static void scan(
            MongoCollection<Document> orders,
            String tenantId
    ) {
        try (MongoCursor<Document> cursor =
                 orders.find(
                     Filters.eq("tenantId", tenantId)
                 )
                 .sort(Sorts.ascending("_id"))
                 .projection(
                     Projections.fields(
                         Projections.include(
                             "customerId",
                             "status",
                             "totalMinor",
                             "createdAt"
                         )
                     )
                 )
                 .batchSize(500)
                 .cursor()) {

            while (cursor.hasNext()) {
                Document order = cursor.next();
                process(order);
            }
        }
    }
}
```

**Ý nghĩa:**

- `Filters.eq("tenantId",...)` hạn chế đúng tenant.
- Sort theo `_id` có thứ tự rõ.
- Projection giảm fields được truyền về client.
- Batch 500 giúp giới hạn số documents mong đợi mỗi lượt fetch.
- Cursor được close ngay cả khi `process` lỗi.

Projection giảm network/decoding cost, nhưng không tự bảo đảm tất cả physical disk reads trên server giảm tương ứng. Muốn giảm đọc document pages, cần query/index hỗ trợ covered query hoặc access pattern phù hợp.

---

## 15. Query/index vẫn là yếu tố nền tảng

Cursor giảm memory của ứng dụng nhưng không sửa truy vấn kém.

Ví dụ:

```java
collection.find(
    Filters.eq("status", "PENDING")
).sort(
    Sorts.descending("createdAt")
);
```

Nếu collection lớn và chưa có index phù hợp, server có thể đọc rất nhiều pages và thực hiện blocking sort trước khi trả batch đầu tiên.

Một index tham khảo:

```javascript
db.orders.createIndex({
  status: 1,
  createdAt: -1
});
```

Nếu queries còn filter theo tenant:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
```

Chọn index dựa vào query shapes, cardinality và `explain`, không tạo nhiều index tùy ý.

### 15.1. Time to first result

Một cursor có thể được mở nhưng mất nhiều giây/phút trước khi nhận document đầu tiên nếu có scan/sort/aggregation nặng ở server. `batchSize` không làm một blocking sort vô điều kiện trở nên streaming.

### 15.2. Đo bằng explain

```javascript
db.orders.find({
  tenantId: "T100",
  status: "PAID"
}).sort({
  createdAt: -1
}).explain("executionStats");
```

Quan sát `totalKeysExamined`, `totalDocsExamined`, `nReturned`, `IXSCAN`, `COLLSCAN`, `FETCH`, `SORT` và execution stats theo version.

---

## 16. Xuất CSV 1 triệu bản ghi không gom vào List

Ví dụ một class xuất CSV đơn giản:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Date;

public final class OrdersCsvExport {

    public static long export(
            MongoCollection<Document> orders,
            String tenantId,
            Path path
    ) throws IOException {

        long count = 0;

        try (BufferedWriter writer =
                 Files.newBufferedWriter(
                     path, StandardCharsets.UTF_8
                 );
             MongoCursor<Document> cursor =
                 orders.find(
                     Filters.eq("tenantId", tenantId)
                 )
                 .sort(Sorts.ascending("_id"))
                 .batchSize(500)
                 .cursor()) {

            writer.write(
                "id,customerId,status,totalMinor,createdAt"
            );
            writer.newLine();

            while (cursor.hasNext()) {
                Document d = cursor.next();

                ObjectId id = d.getObjectId("_id");
                String customer = d.getString("customerId");
                String status = d.getString("status");
                Object total = d.get("totalMinor");
                Date date = d.getDate("createdAt");

                writer.write(csv(id.toHexString()));
                writer.write(",");
                writer.write(csv(customer));
                writer.write(",");
                writer.write(csv(status));
                writer.write(",");
                writer.write(csv(
                    total == null ? "" : total.toString()
                ));
                writer.write(",");
                writer.write(csv(
                    date == null
                        ? ""
                        : date.toInstant().toString()
                ));
                writer.newLine();

                count++;

                if (count % 1000 == 0) {
                    writer.flush();
                }
            }
        }

        return count;
    }

    private static String csv(String value) {
        if (value == null) {
            return "";
        }
        return "\"" + value.replace("\"", "\"\"")
            + "\"";
    }
}
```

### 16.1. Bộ nhớ ứng dụng

Bộ nhớ cần cho một batch driver, buffer của writer và logic xử lý; không cần chứa 1 triệu documents cùng lúc.

### 16.2. Tệp xuất có thể dở dang

Nếu `getMore` lỗi tại record thứ 200.000, output file đã có một phần dữ liệu. `try-with-resources` chỉ đảm bảo đóng tài nguyên, **không** đánh dấu file hoàn tất.

Một quy trình production nên:

1. Ghi vào temporary file.
2. Chỉ đánh dấu COMPLETED sau khi tất cả records được xuất.
3. Kiểm tra checksum/count khi cần.
4. Atomic rename/move khi filesystem hỗ trợ.
5. Dọn temp khi thất bại.
6. Có chính sách bảo mật và thời gian lưu.

### 16.3. CSV formula injection

Nếu file được mở trong spreadsheet software, chuỗi người dùng bắt đầu bằng `=`, `+`, `-`, `@` có thể bị xử lý như công thức trong một số môi trường. CSV quoting không tự chống formula injection. Cần policy bảo vệ theo output consumer, đặc biệt khi export dữ liệu nhập từ bên ngoài.

---

## 17. Nếu đầu ra chậm hơn MongoDB

Giả sử MongoDB có thể fetch 40.000 documents/giây nhưng downstream API chỉ ghi 200 documents/giây.

Trong vòng lặp đồng bộ:

```java
while (cursor.hasNext()) {
    Document d = cursor.next();
    externalApi.send(d);
}
```

thread sẽ đợi `externalApi.send` trước khi gọi `next` tiếp. Vì vậy có backpressure theo luồng điều khiển, nhưng cursor có thể **bị giữ mở quá lâu**.

### 17.1. Nguy cơ

- Một batch xử lý kéo dài hàng chục phút.
- Session idle timeout.
- External call bị treo.
- Export bị hủy nhưng cursor chưa close nếu owner không đúng.
- Nhiều jobs giữ resources khiến connection pool hoặc server state chịu áp lực.

### 17.2. Thiết kế tốt hơn

- Batch size vừa phải.
- Timeout ở downstream.
- Giới hạn số jobs đồng thời.
- Bounded work queue.
- Chia job thành pages và checkpoints.
- Chỉ giữ cursor trong scope một phần công việc đủ ngắn.
- Có cancellation và cleanup.

---

## 18. Session và cursor timeout

MongoDB có nhiều lớp thời gian sống:

| Cơ chế | Vai trò |
| --- | --- |
| `cursorTimeoutMillis` | Idle timeout của server cursor theo nhóm áp dụng, mặc định khoảng 10 phút |
| `localLogicalSessionTimeoutMinutes` | Logical session idle timeout, mặc định khoảng 30 phút |
| `noCursorTimeout(true)` | Yêu cầu tránh cursor idle timeout thông thường |
| Driver/network timeouts | Kiểm soát I/O và lựa chọn server |
| `maxTime(...)` | Giới hạn thời gian thực thi ở server theo API |
| Client-side operation timeout / CSOT | Giới hạn thao tác client theo cấu hình được hỗ trợ |
| Business deadline | SLA tổng của export/backfill |

### 18.1. Session idle timeout có thể vượt noCursorTimeout

Drivers gắn phần lớn operations với implicit hoặc explicit session. Tài liệu MongoDB nói server có thể expire một session không hoạt động trong **30 phút mặc định**, đóng các cursors liên quan kể cả khi cursor bật `noCursorTimeout`.

Ví dụ:

```text
10:00:  firstBatch được nhận
10:01:  Java bắt đầu xử lý 500 documents
10:32:  session có thể đã expire
10:35:  Java gọi getMore
        -> cursor not found / session-related error
```

### 18.2. Không bật `noCursorTimeout` cho tất cả queries

```java
try (MongoCursor<Document> cursor =
         collection.find(filter)
             .noCursorTimeout(true)
             .batchSize(100)
             .cursor()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

Option này **không**:

- Ngăn restart/primary election.
- Ngăn session timeout.
- Ngăn network failure.
- Thay thế `close()`.
- Tạo khả năng resume.
- Đảm bảo một job dài sẽ hoàn tất.

Chỉ dùng khi có yêu cầu và hiểu rõ rủi ro resource leak.

---

## 19. Vì sao xử lý batch quá chậm gây cursor not found?

Giả sử:

```text
batchSize = 500
Mỗi document cần gọi external API mất 5 giây

Batch processing time:
  500 × 5s = 2500s ≈ 41 phút 40 giây
```

Có thể đã vượt session idle timeout mặc định trước khi Java xin batch tiếp.

Các hướng xử lý:

1. Giảm batch size.
2. Không thực hiện công việc cực chậm trong cùng cursor.
3. Dùng checkpoint để mở một query mới theo từng page.
4. Cân nhắc explicit session/refresh chỉ khi thực sự cần và được phép.
5. Theo dõi timeout của nguồn dữ liệu và downstream.
6. Không mặc định mọi lỗi cursor not found đều do driver bug.

### 19.1. Explicit session refresh

Tài liệu MongoDB mô tả khả năng dùng explicit session rồi gọi `refreshSessions` định kỳ nếu cursor có thể idle lâu hơn giới hạn. Đây là quy trình nâng cao, cần quyền phù hợp và bám đúng API driver/session, không phải lý do để thiết kế một cursor sống vô hạn.

Trong phần lớn background jobs, **đọc một page, xử lý, checkpoint rồi đóng cursor** dễ phục hồi hơn.

---

## 20. Session và thứ tự đóng tài nguyên

Một cursor có thể được tạo trong một `ClientSession`:

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class SessionRead {

    public static void run(
            MongoClient client,
            MongoCollection<Document> collection
    ) {
        try (ClientSession session = client.startSession();
             MongoCursor<Document> cursor =
                 collection.find(
                     session,
                     new Document()
                 ).cursor()) {

            while (cursor.hasNext()) {
                process(cursor.next());
            }
        }
    }
}
```

Java đóng tài nguyên trong `try-with-resources` theo **thứ tự ngược lại**:

1. Cursor được đóng.
2. Session được đóng.

Đây là thứ tự phù hợp vì cursor được gắn với session.

### 20.1. Không dùng session giữa nhiều threads

`ClientSession` không được chia sẻ đồng thời tùy tiện. Query và session phải thuộc cùng `MongoClient`; tuân thủ contract driver.

### 20.2. Không giữ transaction hàng giờ cho export

Một transaction dài giữ snapshot/resource state và chịu transaction lifetime limit, ảnh hưởng concurrency và có thể thất bại. Nếu cần ảnh chụp nhất quán của cả dataset lớn, xem giải pháp snapshot/backup hoặc read concern tương thích thay vì mặc định mở transaction rất dài.

---

## 21. Server `maxTime` và client-side timeout

Ví dụ:

```java
try (MongoCursor<Document> cursor =
         collection.find(filter)
             .maxTime(
                 30,
                 java.util.concurrent.TimeUnit.SECONDS
             )
             .cursor()) {
    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

`maxTime` là giới hạn của thao tác thực thi phía server theo semantics MongoDB/driver version. Nó **không** tự hủy một `process()` đang block trong Java hoặc HTTP call đến bên thứ ba.

### 21.1. CSOT và timeout modes mới

Java Sync Driver hiện đại có hướng dẫn **Client-Side Operation Timeout (CSOT)**. Khi được hỗ trợ và đã cấu hình timeout ở client/database/collection, có các chế độ:

- `TimeoutMode.CURSOR_LIFETIME`: một deadline cho toàn bộ lifetime, từ khởi tạo đến đọc hết.
- `TimeoutMode.ITERATION`: deadline cho từng thao tác `hasNext`, `next`, `tryNext`; timeout được gia hạn sau mỗi lần.
- Tailable/Change Stream cursors có default phù hợp với iteration mode.

Ví dụ chỉ dành cho driver version có API này:

```java
import com.mongodb.TimeoutMode;

// Giả định client/collection đã cấu hình CSOT.
try (MongoCursor<Document> cursor =
         collection.find()
             .timeoutMode(TimeoutMode.ITERATION)
             .cursor()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

Không gọi `timeoutMode` trên driver cũ hoặc khi chưa hiểu CSOT effective settings. Dùng đúng Javadocs của dependency đang chạy.

### 21.2. Timeout không tự làm retry an toàn

Nếu đã ghi một phần CSV hoặc gọi external API trước khi timeout, retry toàn bộ job có thể tạo trùng lặp. Cần checkpoint/idempotency.

---

## 22. Dữ liệu có thể thay đổi trong khi cursor đang đọc

Giả sử job bắt đầu đọc lúc 10:00:

```text
10:00  cursor bắt đầu
10:01  lấy batch 1
10:02  user cập nhật hoặc xóa documents
10:03  lấy batch 2
10:04  writer insert documents mới
10:05  lấy batch 3
```

Không được mặc định tất cả documents của các batches phản ánh chính xác một **snapshot tại 10:00**.

Tùy read concern, sort/index/filter, các writes đồng thời có thể dẫn tới thay đổi kết quả hoặc ảnh hưởng tính nhất quán mong muốn.

### 22.1. Sort không phải snapshot

```java
collection.find()
    .sort(Sorts.ascending("_id"))
    .cursor();
```

Sort giúp duyệt theo thứ tự khóa, **không** tự đóng băng toàn bộ collection.

### 22.2. Ứng dụng cần snapshot nhất quán?

Cân nhắc:

- Snapshot/backup phù hợp với hệ thống.
- Read concern và sessions với semantics được hỗ trợ.
- Dataset bất biến hoặc append-only.
- High-water mark với checkpoint.
- Change Streams để đồng bộ những thay đổi tiếp theo.
- Quiesce writes/maintenance window khi business cho phép.

Đừng dùng transaction nhiều giờ chỉ vì muốn export “chắc chắn không thay đổi” mà chưa đánh giá resource limits.

---

## 23. Cursor ID không phải checkpoint bền vững

Không lưu:

```text
jobId=export-100
serverCursorId=12345678901234
```

rồi mong đợi process restart có thể tiếp tục từ cursor ID đó.

Vì cursor ID phụ thuộc server/session state, nó có thể không còn khi:

- Process/restart.
- Cursor idle timeout.
- Session expiration.
- Primary election.
- Network hoặc topology changes.
- Server killCursors.
- Query exhausted.

Muốn resume tác vụ lớn, cần **logical checkpoint**, ví dụ `_id` cuối đã xử lý và được xác nhận thành công.

---

## 24. Keyset pagination cho job lớn

Nếu documents có khóa `_id` với thứ tự ổn định:

```text
Page 1:
  find _id > (none), sort _id asc, limit 500
  checkpoint lastId=A

Page 2:
  find _id > A, sort _id asc, limit 500
  checkpoint lastId=B

Page 3:
  find _id > B, ...
```

Mỗi page có cursor sống ngắn rồi được đóng.

### 24.1. Ví dụ Java

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.ObjectId;

public final class KeysetScanner {

    private static final int PAGE_SIZE = 500;

    public static ObjectId scanPage(
            MongoCollection<Document> collection,
            ObjectId lastProcessedId
    ) {
        Bson filter = lastProcessedId == null
            ? new Document()
            : Filters.gt("_id", lastProcessedId);

        ObjectId lastSuccessful = lastProcessedId;

        try (MongoCursor<Document> cursor =
                 collection.find(filter)
                     .sort(Sorts.ascending("_id"))
                     .limit(PAGE_SIZE)
                     .batchSize(100)
                     .cursor()) {

            while (cursor.hasNext()) {
                Document document = cursor.next();

                processIdempotently(document);

                lastSuccessful =
                    document.getObjectId("_id");
            }
        }

        return lastSuccessful;
    }

    private static void processIdempotently(
            Document document
    ) {
        // Ghi kết quả với idempotency key phù hợp.
    }
}
```

Caller lưu checkpoint khi page được xử lý thành công và theo transaction/ack policy của sink.

### 24.2. Không phải exactly-once tự động

Nếu job xử lý document A thành công nhưng crash trước khi ghi checkpoint A, lần chạy sau có thể xử lý lại A. **Downstream phải idempotent** hoặc dùng transaction/outbox phù hợp nếu yêu cầu exactly-once theo business.

### 24.3. `_id` ObjectId không phải commit timestamp

ObjectId thường chứa timestamp phần giây và có thể do client sinh. Nó không chứng minh tuyệt đối thứ tự commit giữa các clients/hosts. Keyset theo `_id` là **thứ tự của khóa**, không phải lịch sử giao dịch chính xác toàn cục.

---

## 25. Vì sao `skip` lớn có thể chậm?

Một cách phân trang dễ viết:

```java
collection.find()
    .sort(Sorts.ascending("_id"))
    .skip(1_000_000)
    .limit(100)
    .into(new ArrayList<>());
```

Khi offset lớn, server vẫn phải đi qua nhiều index entries hoặc documents để đến vị trí mong muốn. Cost tăng theo offset trong nhiều query plans.

### 25.1. So sánh

| Cách | Điểm mạnh | Điểm yếu |
| --- | --- | --- |
| `skip + limit` | Dễ nhảy tới page N | Offset lớn đắt, concurrent writes làm lệch |
| Keyset `_id > lastId` | Thích hợp quét và resume | Không nhảy tùy ý tới page N |
| Một cursor dài | Code đơn giản, throughput cao khi ổn định | Khó resume khi lỗi |
| Pages + durable checkpoint | Dễ retry, giới hạn lifetime | Cần application state |
| Partitioned scan | Song song | Cần chia không trùng/lọt |

### 25.2. Chọn theo mục đích

- UI 10–20 trang đầu: offset pagination có thể đủ.
- Migration hàng triệu records: keyset/checkpoint thường phù hợp hơn.
- Consistent export: có thể cần snapshot strategy bổ sung.
- Event sync: Change Streams hơn là quét định kỳ nếu use case phù hợp.

---

## 26. Keyset theo `createdAt` và `_id`

Nếu sort chỉ bởi `createdAt`, nhiều documents có thể trùng thời điểm; cần tie-breaker ổn định.

Index gợi ý:

```javascript
db.orders.createIndex({
  createdAt: 1,
  _id: 1
});
```

Query page tiếp theo:

```javascript
{
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $gt: lastId }
    }
  ]
}
```

Java:

```java
Bson nextPageFilter = Filters.or(
    Filters.gt("createdAt", lastCreatedAt),
    Filters.and(
        Filters.eq("createdAt", lastCreatedAt),
        Filters.gt("_id", lastId)
    )
);

try (MongoCursor<Document> cursor =
         orders.find(nextPageFilter)
             .sort(Sorts.ascending("createdAt", "_id"))
             .limit(500)
             .batchSize(100)
             .cursor()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

**Quan trọng:** fields làm checkpoint cần có semantics bất biến hoặc mutation policy rõ. Nếu `createdAt`/sort key bị sửa trong lúc scan, có thể bỏ sót hoặc xử lý lại documents.

---

## 27. Retry sau lỗi: tạo truy vấn mới từ checkpoint

Các lỗi có thể xảy ra:

- Primary election.
- Connection reset.
- Server selection timeout.
- Cursor bị session timeout.
- Downstream API trả 429 hoặc 503.
- Một document lỗi schema.
- Java process bị restart.

Không nên gọi lại `next()` vô hạn trên một cursor đã lỗi hoặc cố tái sử dụng server cursor ID.

### 27.1. Workflow bền vững

```text
START JOB
    |
    v
Load durable checkpoint
    |
    v
Open bounded page query
    |
    v
Read + apply idempotent effects
    |
    v
Persist checkpoint after acknowledgement
    |
    v
Close cursor
    |
    +--> More? next page
    |
    +--> Error? backoff and retry from checkpoint
    |
    v
COMPLETE
```

### 27.2. Không checkpoint trước khi ghi downstream

Sai:

```text
Read 500 docs
Save lastId
Call external API
API failed
Restart skips those docs
```

Tốt hơn:

```text
Read 500 docs
Apply operations with idempotency keys
Confirm successful outcome
Save lastId
```

Vẫn có một khoảng hở giữa effect được xác nhận và checkpoint được ghi, vì vậy **idempotency** bảo vệ trường hợp retry làm lại một phần đã thành công.

---

## 28. Bulk xử lý với bộ nhớ có giới hạn

Để chuyển nhiều documents sang collection khác, có thể dùng `bulkWrite` theo batch.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOneModel;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;

import java.util.ArrayList;
import java.util.List;

public final class BulkMigration {

    public static long run(
            MongoCollection<Document> source,
            MongoCollection<Document> destination
    ) {
        final int WRITE_BATCH = 500;
        List<WriteModel<Document>> pending =
            new ArrayList<>(WRITE_BATCH);
        long processed = 0;

        try (MongoCursor<Document> cursor =
                 source.find()
                     .batchSize(500)
                     .cursor()) {

            while (cursor.hasNext()) {
                Document input = cursor.next();
                Document output = transform(input);

                pending.add(
                    new ReplaceOneModel<>(
                        Filters.eq("_id", output.get("_id")),
                        output,
                        new ReplaceOptions().upsert(true)
                    )
                );

                if (pending.size() >= WRITE_BATCH) {
                    destination.bulkWrite(pending);
                    processed += pending.size();
                    pending.clear();
                }
            }

            if (!pending.isEmpty()) {
                destination.bulkWrite(pending);
                processed += pending.size();
                pending.clear();
            }
        }

        return processed;
    }

    private static Document transform(Document src) {
        Document copy = new Document(src);
        copy.put("migrated", true);
        return copy;
    }
}
```

### 28.1. Vì sao dùng upsert theo `_id`?

Khi cùng input được xử lý lại, replace/upsert với cùng khóa giúp giảm duplicate records nếu transformation **deterministic** và không có concurrent writes xung đột.

### 28.2. Không tự suy ra mọi bulk failure đều rollback

Một bulk batch có thể thành công một phần trước khi lỗi. Với `ordered`/`unordered` behavior, server có thể dừng hoặc tiếp tục các operations khác. Phải đọc write errors và ghi nhận checkpoint dựa trên kết quả được xác nhận.

### 28.3. Đừng sửa source trong khi quét theo filter có thể thay đổi

Nếu quét `state: "PENDING"` rồi cập nhật chính field `state`, index/truy vấn có thể bị ảnh hưởng. Dùng immutable key, page queries, idempotent updates hoặc destination collection mới theo migration runbook.

---

## 29. Xử lý song song: một cursor không được chia cho nhiều threads

`MongoCursor` **không thread-safe**.

Sai:

```java
executor.submit(() -> process(cursor.next()));
executor.submit(() -> process(cursor.next()));
```

Hai worker cùng gọi `next()` trên một cursor có thể gây race hoặc lỗi ngoài contract.

### 29.1. Producer–consumer

```text
         MongoCursor
             |
    1 producer thread
             |
             v
       Bounded Queue
       capacity = 1000
             |
       +-----+-----+
       |     |     |
       v     v     v
      W1    W2    W3
       |     |     |
       +-----+-----+
             |
             v
     Downstream results
```

Chỉ một thread đọc cursor; nhiều worker xử lý dữ liệu đã chuyển thành tasks.

### 29.2. Backpressure

Nếu bounded queue đầy, producer phải chờ hoặc điều tiết tốc độ. Không tạo `new LinkedBlockingQueue<>()` không có capacity nếu input có thể là hàng triệu documents và downstream chậm.

### 29.3. Checkpoint với workers song song

Không lưu `_id` **lớn nhất vừa xử lý xong** nếu những `_id` thấp hơn chưa hoàn tất. Sau restart sẽ bỏ sót chúng.

Cần:

- Theo dõi contiguous committed prefix.
- Hoặc checkpoint riêng theo partition.
- Hoặc đẩy tasks tới durable queue với ack semantics.
- Idempotency khi retry.

---

## 30. `close()` từ thread khác để hủy cursor

API MongoCursor có một ngoại lệ đối với NotThreadSafe: **`close()` được phép gọi đồng thời với các phương thức khác**, kể cả để hủy `hasNext()`/`next()` đang block.

Ví dụ:

```text
Worker:
  cursor.hasNext() đang chờ getMore

Cancellation controller:
  cursor.close()

Worker:
  thoát chờ / nhận exception / dừng
```

### 30.1. Thiết kế cancellation

- Một owner duy nhất đọc cursor.
- Cơ chế cancel có thể truy cập cursor hiện hành để `close()`.
- Không gọi `next()` trên cursor từ cancel thread.
- Workers/queues cũng được dừng có kiểm soát.
- Output tạm được đóng/dọn.
- Job được đánh dấu `CANCELLED` thay vì `COMPLETED`.

### 30.2. Không trông chờ garbage collector

GC không có deadline để đóng server resources. Hãy dùng `try-with-resources`/explicit cleanup.

---

## 31. Tailable cursor và `tryNext()`

**Tailable cursor** phục vụ luồng dữ liệu đang được thêm vào một **capped collection**. Nó khác truy vấn thông thường đọc một tập kết quả hữu hạn.

```java
import com.mongodb.CursorType;
import com.mongodb.client.MongoCursor;
import java.util.concurrent.TimeUnit;

try (MongoCursor<Document> cursor =
         cappedCollection.find()
             .cursorType(CursorType.TailableAwait)
             .maxAwaitTime(2, TimeUnit.SECONDS)
             .cursor()) {

    while (!Thread.currentThread().isInterrupted()) {
        Document event = cursor.tryNext();

        if (event == null) {
            // Có thể chưa có document mới ở lần thử này.
            continue;
        }

        process(event);
    }
}
```

### 31.1. Khác ordinary cursor ở đâu?

- Cursor chờ documents mới.
- `null` từ `tryNext` có thể chỉ mang nghĩa chưa có event.
- Có thể mất vị trí nếu capped collection overwrite old data.
- Có thể cần vòng lặp retry/resume theo application.
- Cần cancellation và timeout hợp lệ.
- Không dùng cho một collection thường không capped nếu API yêu cầu capped behavior.

### 31.2. Chú ý busy-spin

Nếu `tryNext()` trả `null` liên tục không chờ theo cấu hình/mode, cần backoff để tránh CPU loop. Với awaitData/maxAwaitTime, behavior chờ cần đối chiếu driver version.

### 31.3. Khi nào dùng Change Streams?

Nếu cần phản ứng với insert/update/delete trên collection/database, **Change Streams** thường phù hợp hơn. Nó có resume token riêng và những yêu cầu về oplog/window; không thay resume token bằng cursor ID.

---

## 32. Session và cursor khi có Change Streams

Change Streams dùng cursor dài hạn, thường trả về `MongoChangeStreamCursor<TResult>` hoặc API tương ứng.

Quy tắc vận hành:

- Đóng stream khi service stop.
- Xử lý `tryNext()` không có event.
- Theo dõi server errors và resume token.
- Lưu checkpoint/resume token **sau khi** downstream được xác nhận phù hợp.
- Giới hạn network/processing timeout.
- Tính toán oplog history retention và khả năng mất resume point.
- Không dùng cùng cursor giữa nhiều threads ngoài cancellation được API cho phép.

Một Change Stream có thể hợp lệ khi mở nhiều giờ; một ordinary export cursor mở nhiều giờ thường nên được xem xét chia page.

---

## 33. Sort, index và consistency của pagination

Để duyệt một tập dữ liệu lớn, thứ tự phải rõ:

```java
collection.find(
    Filters.eq("tenantId", tenantId)
)
.sort(Sorts.ascending("createdAt", "_id"))
.batchSize(500);
```

Tại sao `_id` là tie-breaker?

Hai orders có thể có cùng `createdAt`. Nếu sort không có khóa cuối ổn định, các pages có thể không nhất quán về thứ tự.

### 33.1. Chỉ sort chưa bảo vệ khỏi concurrent update

Nếu field sort được sửa trong lúc scan, một document có thể di chuyển trong thứ tự. Với batch processing nhiều giờ, cần immutable sort key hoặc snapshot/reconciliation.

### 33.2. Index cho filter + sort

```javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: 1,
  _id: 1
});
```

Đây là index gợi ý theo query shape, không phải lời khuyên tạo index chung cho mọi hệ thống.

---

## 34. Aggregation cũng phải close cursor

```java
import com.mongodb.client.AggregateIterable;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Accumulators;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

List<Bson> pipeline = List.of(
    Aggregates.match(
        Filters.eq("tenantId", tenantId)
    ),
    Aggregates.group(
        "$status",
        Accumulators.sum("count", 1)
    )
);

AggregateIterable<Document> iterable =
    orders.aggregate(pipeline);

try (MongoCursor<Document> cursor =
         iterable.batchSize(100).cursor()) {
    while (cursor.hasNext()) {
        System.out.println(cursor.next().toJson());
    }
}
```

### 34.1. Batch size không giảm hết memory của aggregation

Các stages như `$sort`, `$group`, `$setWindowFields` có thể cần intermediate memory hoặc disk spill trước khi trả results. Cursor giúp client không giữ toàn bộ output nhưng **không biến blocking aggregation stage thành streaming**.

### 34.2. allowDiskUse không tự tăng tốc

Khi được hỗ trợ, `allowDiskUse` cho phép một số stages spill ra disk để hoàn thành, nhưng có thể làm query chậm hơn. Hãy tối ưu `$match`, index, cardinality và execution plan.

---

## 35. HTTP streaming và cursor lifecycle

Endpoint export dữ liệu lớn có thể dùng:

```text
GET /api/exports/orders?tenantId=T100

HTTP response OutputStream
           ^
           |
       CSV writer
           ^
           |
      MongoCursor
           ^
           |
        MongoDB
```

### 35.1. Khi client ngắt kết nối

`OutputStream.write` có thể ném IOException. Nếu writer và cursor nằm trong `try-with-resources`, resources được đóng theo scope.

### 35.2. HTTP response đã commit

Sau khi gửi vài MB CSV, server không thể thay payload đã gửi bằng một JSON lỗi hoàn chỉnh. Cần xử lý partial download: hủy kết nối, log, thông báo retry theo contract.

### 35.3. Xuất dữ liệu rất lớn nên là background job

Thay vì giữ HTTP connection hàng giờ:

1. Nhận yêu cầu export và tạo job ID.
2. Chạy job có checkpoint trong worker giới hạn.
3. Ghi file tạm/object storage.
4. Hoàn tất, xác minh, publish download URL có quyền truy cập.
5. Dọn file theo retention.
6. Nếu lỗi, job FAILED với khả năng retry.

Streaming HTTP có thể hợp lý với output vừa phải; không phải mọi case đều cần job architecture.

---

## 36. Monitoring open cursors trên MongoDB server

Trên môi trường có quyền thích hợp:

```javascript
const cursorMetrics =
    db.serverStatus().metrics.cursor;

printjson(cursorMetrics);
```

Các nhóm/counters thường gặp theo phiên bản:

- `open.total`.
- `open.noTimeout`.
- `open.pinned`.
- `timedOut`.
- `lifespan` histograms hoặc các thống kê liên quan.

**Tên field và schema có thể thay đổi theo MongoDB Server version.**

### 36.1. Tín hiệu đáng điều tra

- Open cursor count tăng mãi sau khi requests kết thúc.
- `noTimeout` cursor tăng không có owner rõ.
- `timedOut` tăng cùng export failures.
- Cursor lifespan vượt SLA.
- getMore latency cao.
- Heap/connection pool/threads cùng tăng.

### 36.2. Không phải nhiều cursors luôn là leak

Một dịch vụ có nhiều Change Streams dài hạn có thể chủ động giữ nhiều cursors. Cần đối chiếu **số lượng theo thiết kế** và trạng thái ownership, không kill tất cả.

---

## 37. `currentOp` và `killCursors`

Khi điều tra query/getMore kéo dài:

```javascript
db.currentOp();
```

Hoặc:

```javascript
db.adminCommand({
  currentOp: 1
});
```

MongoDB có lệnh quản trị `killCursors` để kết thúc một server cursor biết ID và namespace.

```javascript
// Ví dụ cú pháp để nhận biết, KHÔNG chạy trên production.
db.runCommand({
  killCursors: "orders",
  cursors: [NumberLong("123456789")]
});
```

### 37.1. Ưu tiên application close

Application có `MongoCursor` thì **gọi `close()`**. Manual kill chỉ dùng khi có mục đích quản trị được phê duyệt, xác minh đúng cursor/collection và hiểu hậu quả làm job hợp lệ thất bại.

### 37.2. Close cursor khác close client

Đóng một cursor không có nghĩa đóng connection pool của MongoClient. Không gọi `client.close()` sau từng document để “giải phóng tài nguyên”.

---

## 38. Có bao nhiêu connection cho mỗi cursor?

Một quan niệm sai:

> 100 cursors luôn tương đương 100 TCP connections bị pin suốt lifetime.

Không phải mọi query đều pin connection. Driver quản lý connection pools; behavior có thể khác khi chạy transactions, load-balanced deployments, Change Streams hoặc những operations đặc thù.

Vì vậy phải **đo riêng**:

- `metrics.cursor.open`.
- Connection pool active/checked-out.
- Pool wait time.
- Driver thread count.
- getMore latency.
- Pinned connections/cursors khi topology hỗ trợ metric.
- Server selection timeouts.

Không tăng connection pool chỉ vì thấy cursor count cao nếu bottleneck nằm ở downstream hoặc heap.

---

## 39. Retryable writes không làm external API idempotent

Một worker:

```text
Read order O100 from cursor
    |
    v
Charge payment gateway
    |
    v
Save processed checkpoint
```

Nếu thanh toán thành công nhưng database save timeout, retry có thể charge lần nữa.

**Giải pháp:** stable idempotency key theo business operation, lưu trạng thái và reconciliation với gateway. MongoDB retryable writes không bảo vệ các lời gọi HTTP bên ngoài MongoDB.

### 39.1. Đừng dùng cursor position làm transaction boundary

Cần phân biệt:

- Read position.
- Side effect acknowledged.
- Checkpoint persisted.
- Business operation completed.

Một cursor chỉ cho biết thứ tự đọc, không chứng minh các side effects đã được commit.

---

## 40. Tổ chức job xử lý tập lớn theo partitions

Với workload rất lớn có thể chia theo khoảng khóa:

```text
Worker A: _id in [min, boundary1)
Worker B: _id in [boundary1, boundary2)
Worker C: _id in [boundary2, max]
```

Mỗi worker có:

- Một cursor riêng.
- Filter phạm vi không trùng lặp.
- Batch size riêng.
- Checkpoint riêng.
- Retry policy.
- Owner/lease và heartbeat.
- Metrics throughput/errors.

### 40.1. Không partition bằng cách đoán ObjectId đều nhau

ObjectIds không nhất thiết phân bố đều theo số học; một khoảng có thể chứa rất nhiều documents và khoảng khác hầu như rỗng.

### 40.2. Cần giới hạn parallelism

Nhiều workers đồng thời có thể bão hòa:

- Disk IOPS và index reads.
- Network.
- MongoDB CPU.
- Connection pools.
- Downstream API.
- Java heap.

Tăng số workers không luôn tăng throughput.

---

## 41. Thiết kế trạng thái background job

Một schema tham khảo:

```javascript
{
  _id: "export-orders-T100-20261114",
  state: "RUNNING",
  tenantId: "T100",
  startedAt: ISODate("2026-11-14T08:00:00Z"),
  updatedAt: ISODate("2026-11-14T08:30:00Z"),
  lastProcessedId: ObjectId("691800000000000000000111"),
  processedCount: NumberLong("250000"),
  failedCount: NumberLong("3"),
  attempt: 2,
  workerId: "worker-01",
  schemaVersion: 1
}
```

Các thông tin cần có:

- `state`: CREATED, RUNNING, RETRY_WAIT, FAILED, COMPLETED, CANCELLED.
- `lease`/owner để tránh hai workers xử lý cùng partition.
- Durable checkpoint.
- Attempt count.
- Processed/failed counts.
- Heartbeat.
- Query filter/version.
- Output ID/temp file path.
- Data retention và quyền truy cập.

Không lưu server cursor ID làm progress checkpoint.

---

## 42. Lỗi thường gặp và cách nhận biết

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `MongoCursorNotFoundException` | Cursor/server session expired | Chia page, kiểm tra timeout, resume từ checkpoint |
| Network reset trong getMore | Server election/network issue | Retry job từ checkpoint |
| OutOfMemoryError | `into(List)`, unbounded buffer | Cursor + bounded processing |
| Dừng đúng 100 documents | Loop dựa vào `available()` | Dùng `hasNext()` |
| Batch 500 nhưng kết quả chỉ 120 | Limit byte hoặc cuối kết quả | Bình thường |
| `hasNext()` lâu | Server getMore, disk, network | Query metrics, index, timeout |
| `first()` trả record “lạ” | Thiếu sort | Sort rõ theo nghiệp vụ |
| Nhiều cursors idle | Quên close, request leak | try-with-resources, lifecycle monitor |
| noCursorTimeout vẫn bị kill | Session idle hoặc topology event | Không dựa vào noCursorTimeout |
| Export có dòng trùng | Retry không idempotent | Keyset/checkpoint/idempotency |
| Export thiếu records | Sort key thay đổi, checkpoint sai | Stable key, data consistency |
| Bulk partial success | Ordered/unordered bulk semantics | Xử lý write errors, ack |
| Parallel cursor lỗi | Nhiều threads gọi next | Một producer, bounded queue |
| HTTP export bị cắt | Client disconnect hoặc cursor failure | Partial response policy |
| Secondary bị replication lag | Reporting scan quá lớn | Giới hạn workload/capacity |
| Query trả chậm từ đầu | Blocking sort/scan | Explain, index |
| Connection pool timeout | Quá nhiều operations/waits | Pool metrics và concurrency |
| `maxTime` không dừng HTTP call | Server timeout không bao application | Deadline ở nhiều tầng |

---

## 43. Các anti-pattern nên tránh

### 43.1. Lưu cursor làm field của singleton service

```java
// Tránh trong Spring singleton:
private MongoCursor<Document> cursor;
```

Một cursor thuộc **một lần xử lý**, không phải tài nguyên toàn cục chia sẻ.

### 43.2. Mở cursor rồi trả cho code khác mà không quy định ai đóng

```java
public MongoCursor<Document> openOrders() {
    return collection.find().cursor();
}
```

Nếu API này là bắt buộc, phải ghi rõ **caller owns and closes** trong Javadoc và kiểm tra usage; thường tốt hơn là method nhận callback và đóng cursor nội bộ.

### 43.3. Ép Java Stream parallel trực tiếp trên cursor

`MongoCursor` không thread-safe. Nếu muốn song song, một producer đọc tuần tự và phân phối tasks tới bounded queue.

### 43.4. Tăng batchSize vô hạn

Batch lớn có thể tăng heap/GC, không sửa bottleneck downstream hoặc blocking sort server.

### 43.5. Đưa toàn bộ kết quả vào HashMap để “xử lý sau”

Memory vẫn tăng theo tổng kết quả, mất lợi ích streaming.

### 43.6. Bật noCursorTimeout toàn hệ thống

Dễ tạo idle server cursors dài hạn và không loại bỏ session timeout.

### 43.7. Coi cursor ID là pagination token public

Cursor ID không bền vững, không mang quyền tenant và không phải API contract an toàn.

### 43.8. Mở transaction kéo dài suốt migration

Dễ vượt transaction lifetime và gây resource pressure, không thay durable checkpoint.

### 43.9. Không kiểm tra output khi gặp lỗi

CSV/file đích có thể dở dang dù cursor được close đúng.

---

## 44. Kịch bản: MongoCursor bị lỗi sau 35 phút

**Triệu chứng:** job đọc 500 documents đầu, sau đó ngoại lệ khi gọi `getMore` sau một giai đoạn xử lý lâu.

**Phân tích:**

```text
Batch size: 500
Processing per document: 5 seconds
Elapsed per batch: ~41 minutes
Session idle timeout default: ~30 minutes
```

**Giải pháp:**

1. Giảm batch size.
2. Giới hạn external API latency.
3. Chuyển sang page queries ngắn.
4. Lưu checkpoint sau processed output.
5. Kiểm tra KMS/network/primary election nếu có evidence khác.
6. Không mặc định cứ `noCursorTimeout(true)` là đủ.

---

## 45. Kịch bản: OOM dù dùng batchSize(100)

**Code:**

```java
List<Document> documents = collection.find()
    .batchSize(100)
    .into(new ArrayList<>());
```

**Vấn đề:** `into` vẫn gom toàn bộ 8 triệu kết quả vào list.

**Sửa:**

```java
try (MongoCursor<Document> cursor =
         collection.find()
             .batchSize(100)
             .cursor()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
```

Nhưng `process` cũng không được giữ references vô hạn.

---

## 46. Kịch bản: export chậm vì sort không có index

**Triệu chứng:**

```text
Time to first document: 80 seconds
Batch size: 100
Server execution stats: blocking sort
Disk reads: high
```

**Cách xử lý:**

- Dùng explain.
- Xem filter và sort cùng index.
- Giảm phạm vi dữ liệu.
- Dùng keyset pages nếu có stable key.
- Cân nhắc pre-computed output.
- Không chỉ tăng batch size.

---

## 47. Kịch bản: migration bỏ sót dữ liệu sau restart

**Luồng sai:**

```text
Read document D100
Save checkpoint D100
Write D100 to destination -> failed
Restart: query D > D100
D100 is skipped
```

**Sửa:**

```text
Read D100
Apply idempotent write successfully
Save checkpoint D100
Restart may replay if checkpoint save fails
Idempotency prevents duplicate harmful effects
```

Nếu nhiều workers, checkpoint phải phản ánh các tasks đã xử lý **liên tục** chứ không chỉ ID lớn nhất hoàn tất.

---

## 48. Kịch bản: API export gây tải lớn cho production

Một user yêu cầu xuất mọi đơn hàng trong 5 năm, truy vấn không có index phù hợp, 50 requests xuất đồng thời.

**Rủi ro:**

- Disk I/O tăng.
- Cursor count tăng.
- Memory/bandwidth pressure.
- Latency của API bình thường xấu đi.
- Output chứa dữ liệu nhạy cảm.
- Các requests bị proxy timeout.

**Hướng giải quyết:**

1. RBAC/tenant authorization.
2. Quotas về file rows/bytes, concurrent exports.
3. Async job với checkpoint.
4. Query theo time window/index.
5. Có thể dùng reporting secondary/cluster nếu consistency cho phép.
6. Bảo vệ output, retention và audit.
7. Giám sát p95/p99 của workloads quan trọng.

---

## 49. Security checklist cho xử lý dữ liệu lớn

- Không tin tenant ID do client gửi để tự quyết quyền.
- Dùng authenticated tenant context và filter đúng.
- Không export trường nhạy cảm nếu không được phép.
- Giới hạn số lượng records/bytes.
- Đặt timeout/rate limit cho API export.
- Không log raw documents hoặc credentials.
- Không lưu CSV production ở thư mục world-readable.
- Dọn temp files sau FAILED/CANCELLED.
- Không dùng cursor ID làm capability token.
- Dùng TLS/auth và least-privilege DB roles.
- Có audit event cho export/download.
- Tách quyền read dataset khỏi quyền quản trị MongoDB.
- Nếu lưu kết quả ra object storage, dùng encryption và access policies.

---

## 50. Checklist kiểm tra code MongoCursor

- [ ] Có biết query có thể trả bao nhiêu documents không?
- [ ] Không dùng `into(List)` trên kết quả unbounded?
- [ ] Có phân biệt `batchSize` và `limit`?
- [ ] Mọi explicit cursor có owner rõ?
- [ ] Có try-with-resources hoặc finally close?
- [ ] `break`/`return`/exception đều cleanup?
- [ ] Không dùng `available()` làm total count?
- [ ] Không dùng `available()` làm điều kiện lặp kết thúc?
- [ ] Có filter/sort/projection/index phù hợp?
- [ ] Đã đo time-to-first-document?
- [ ] Batch size phù hợp document sizes?
- [ ] Không giữ records vô hạn trong queue/map?
- [ ] Có xử lý lỗi giữa getMore?
- [ ] Có timeout ở server/client/downstream?
- [ ] Không bật noCursorTimeout vô điều kiện?
- [ ] Có xét session idle khi processing chậm?
- [ ] Có checkpoint cho job dài?
- [ ] Checkpoint sau effect được xác nhận?
- [ ] Retry có idempotency?
- [ ] Không chia cursor cho nhiều threads?
- [ ] Nếu parallel, queue bounded và checkpoint đúng thứ tự?
- [ ] Cancellation gọi close/cleanup?
- [ ] Không mở transaction hàng giờ tùy tiện?
- [ ] Không coi cursor là snapshot bất biến?
- [ ] Có bảo vệ file output khi partial failure?
- [ ] Có metrics open cursors/heap/getMore?
- [ ] Không đóng MongoClient toàn cục theo từng cursor?
- [ ] Có diễn tập primary election/network interruption?
- [ ] Có kiểm soát quyền tenant và dữ liệu nhạy cảm?
- [ ] Có strategy giải quyết records thay đổi trong lúc scan?

---

## 51. Bài tập thực hành có đáp án

### Bài 1 — Tổng số documents

```java
int n = collection.find().cursor().available();
```

**Hỏi:** `n` là tổng documents đúng không?

**Đáp án:** Không. Nó chỉ là số documents có sẵn cục bộ; còn có lỗi không đóng cursor.

### Bài 2 — Batch và limit

Query match 1.000.000 documents và `.batchSize(100)`.

**Hỏi:** Có thể đọc hơn 100 documents không?

**Đáp án:** Có. Batch size chỉ điều chỉnh số documents mỗi batch.

### Bài 3 — Early break

```java
for (Document d : collection.find()) {
    if (isTarget(d)) break;
}
```

**Hỏi:** Điều gì cần sửa?

**Đáp án:** Dùng explicit MongoCursor + try-with-resources để đóng khi break.

### Bài 4 — Exception

`process()` throw ở document thứ 300, cursor nằm trong try-with-resources.

**Đáp án:** Java vẫn gọi close.

### Bài 5 — Bộ nhớ

Mỗi document Java decode trung bình 8 KiB, batchSize 2000, 30 cursors.

**Đáp án:** Estimate 8 × 2000 × 30 KiB = 468,750 KiB ≈ 468,75 MiB, chưa tính overhead khác.

### Bài 6 — Session timeout

Một batch mất 45 phút xử lý, rồi getMore báo cursor not found.

**Đáp án:** Có thể do session idle; giảm cursor/page lifetime, không chỉ noCursorTimeout.

### Bài 7 — available 0

`available() == 0` nhưng `hasNext()` vẫn có thể trả true?

**Đáp án:** Có thể; batch cục bộ rỗng nhưng server còn dữ liệu.

### Bài 8 — Skip lớn

Page thứ 10.000 dùng `skip(1_000_000)`.

**Đáp án:** Có thể đắt vì phải đi qua nhiều entries; keyset thường phù hợp cho scan tuần tự.

### Bài 9 — Checkpoint

Job save checkpoint rồi mới gọi API ngoài, API lỗi.

**Đáp án:** Có thể bỏ sót dữ liệu sau restart; checkpoint sau effect đã được xác nhận.

### Bài 10 — Duplicate effect

Job gọi payment gateway xong crash trước checkpoint.

**Đáp án:** Cần idempotency key để tránh charge lại khi retry.

### Bài 11 — Parallel cursor

Ba threads gọi `cursor.next()` trên cùng cursor.

**Đáp án:** Không thread-safe; dùng một producer + bounded queue.

### Bài 12 — Cancellation

Một thread đang `hasNext()` và thread khác cần hủy.

**Đáp án:** Interface cho phép `close()` đồng thời, nhưng không cho phép chia các operations đọc đồng thời tùy ý.

### Bài 13 — Tailable

`tryNext()` trả null trên Change Stream/tailable cursor.

**Đáp án:** Có thể chưa có event, không có nghĩa stream kết thúc.

### Bài 14 — Snapshot

Sort `_id` tăng dần có bảo đảm tất cả documents như tại 10:00?

**Đáp án:** Không, phải xét concurrent writes và read concern/snapshot policy.

### Bài 15 — CSV giữa chừng

HTTP đã gửi 5 MiB CSV rồi database lỗi.

**Đáp án:** Không thể thay bytes đã gửi bằng JSON 500 hoàn chỉnh; cần partial/failure policy.

### Bài 16 — Cursor ID

Có thể lưu server cursor ID để resume sau restart?

**Đáp án:** Không. Dùng logical checkpoint/keyset hoặc Change Stream resume token tùy use case.

### Bài 17 — MongoClient

Có nên `client.close()` sau mỗi cursor?

**Đáp án:** Không nếu client là singleton/long-lived pool; đóng cursor theo task, client theo app lifecycle.

### Bài 18 — Batch 0

Tại server `batchSize:0` có thể tạo cursor nhưng first batch rỗng. Có phải “không có kết quả”?

**Đáp án:** Không; vẫn có thể có các kết quả ở getMore. Không dùng first batch rỗng để kết luận query không match.

### Bài 19 — Projection

Chỉ trả hai fields, có chắc disk I/O giảm 90%?

**Đáp án:** Không. Projection giảm result size; physical reads còn phụ thuộc plan/covered query.

### Bài 20 — Aggregation

Aggregation `$group` 100 triệu events, Java dùng batchSize(100).

**Đáp án:** Server vẫn có thể cần nhiều intermediate memory/disk; batch size ở client không giải quyết.

### Bài 21 — Bulk partial success

BulkWrite trả exception sau khi đã apply một phần.

**Đáp án:** Không giả định rollback toàn bộ; xử lý result/errors, idempotency và checkpoint.

### Bài 22 — Keyset theo timestamp

Hai documents có cùng `createdAt`.

**Đáp án:** Dùng tie-breaker `_id`, sort `(createdAt,_id)` và lexicographic filter tương ứng.

### Bài 23 — Sort key mutable

Một document bị sửa `createdAt` khi scan.

**Đáp án:** Có thể đọc lặp/bỏ sót. Dùng immutable key hoặc snapshot/reconciliation.

### Bài 24 — Downstream chậm

MongoDB đọc 20.000 docs/s nhưng sink chỉ ghi 200 docs/s.

**Đáp án:** Sink quyết định throughput; tăng batchSize không giải quyết và còn tăng memory/lifetime.

### Bài 25 — Count cho progress

Lệnh count quá đắt trên dataset lớn.

**Đáp án:** Có thể chỉ hiển thị processed count/high-water/partitions; không bắt buộc exact total.

### Bài 26 — Retry cả request

Một exception ở `next()` dẫn tới retry toàn HTTP request, trong đó có thao tác gửi email.

**Đáp án:** Cần idempotency cho external side effects và resume từ checkpoint.

### Bài 27 — Tải đồng thời

50 exports lớn chạy cùng lúc và p99 API tăng mạnh.

**Đáp án:** Giới hạn concurrency/quota, tối ưu index, tách reporting workload hoặc chuyển sang jobs.

### Bài 28 — CSOT

`maxTime` của query có chắc hạn chế 1 giờ xử lý CSV ở Java không?

**Đáp án:** Không. Cần deadline end-to-end và lựa chọn CSOT/timeout mode thích hợp.

### Bài 29 — Server metrics

`metrics.cursor.open.total` tăng không giảm sau khi jobs dừng.

**Đáp án:** Điều tra cursor ownership/leak hoặc các long-lived streams hợp lệ, không kill bừa toàn bộ.

### Bài 30 — Phương án nên chọn

Cần chuyển 30 triệu documents trong nhiều giờ, có thể process restart bất kỳ lúc nào.

**Đáp án:** Chia page/partition, cursor scope ngắn, durable checkpoint, idempotent writes, bounded memory, retry/backoff, monitoring và đối soát.

---

## 52. Tài liệu MongoDB chính thức

- [Access Data From a Cursor — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/cursor/): cách dùng `FindIterable`, `MongoCursor`, `first`, `into`, `available`, close và try-with-resources.
- [MongoCursor API — Java Sync Driver](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/driver-sync/com/mongodb/client/MongoCursor.html): `hasNext`, `next`, `tryNext`, `available`, `close` và thread safety.
- [Cursors — MongoDB Manual](https://www.mongodb.com/docs/manual/core/cursors/): server cursor ID, getMore và vòng đời.
- [getMore Command — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/command/getMore/): các batch tiếp theo, batchSize và timeouts.
- [cursor.batchSize — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/method/cursor.batchSize/): first batch 101/16 MiB và tradeoffs.
- [cursor.noCursorTimeout — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/method/cursor.noCursorTimeout/): idle cursor/session timeouts.
- [MongoDB Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/): BSON document limits và session idle timeout.
- [Limit Server Execution Time — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/csot/): CSOT và cursor lifetime/iteration timeout.
- [Query Documents — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/): filter, sort, projection, limit.
- [Limit Returned Results — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/limit/): limit/skip.
- [Bulk Write Operations — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/): ordered/unordered, errors và batch write.
- [Transactions — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/): ClientSession và transaction semantics.
- [Change Streams — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/): event cursor/resume token.
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/): query diagnostics với chi phí profiler.
- [serverStatus — MongoDB Manual](https://www.mongodb.com/docs/manual/reference/command/serverStatus/): `metrics.cursor` và các metrics server khác.
- [Java Sync Driver Compatibility](https://www.mongodb.com/docs/drivers/java/sync/current/compatibility/): Java/driver/server compatibility.
- [Java Reactive Streams Driver](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/): API non-blocking và reactive backpressure.

**Lưu ý phiên bản:** các API như `timeoutMode()` và CSOT, semantics getMore của tailable/Change Streams, `metrics.cursor` và server timeouts có thể khác theo Java Driver/MongoDB Server/topology. Đối chiếu version đang sử dụng trước khi đưa code vào production.

---

## 53. Tổng kết

**MongoCursor** là cách tiếp cận quan trọng để Java xử lý kết quả MongoDB lớn mà không giữ toàn bộ trong heap:

1. `FindIterable` cấu hình query; `MongoCursor` thực hiện duyệt.
2. MongoDB trả kết quả theo **batches**, Java tự gọi `getMore` khi cần.
3. `batchSize` điều chỉnh mỗi lượt fetch, **không** giới hạn tổng kết quả; `limit` mới làm việc đó.
4. `available()` chỉ báo tài liệu đang sẵn cục bộ, không phải total count.
5. Dùng `try-with-resources` để `close()` cả khi đọc hết, dừng sớm hoặc gặp lỗi.
6. `noCursorTimeout` không vô hiệu hóa session timeout, failover và network issues.
7. MongoCursor **không thread-safe**; nếu xử lý song song, chỉ một producer đọc và dùng bounded queue.
8. Một job lớn cần **checkpoint + idempotency + retry từ truy vấn mới**, không dùng server cursor ID như resume token.
9. Filter, index, sort, projection và aggregation vẫn phải tối ưu để server không đọc quá nhiều.
10. Với HTTP export lớn, cần quản lý partial output, quotas, cancellation và bảo mật.

Mẫu cốt lõi:

```java
try (MongoCursor<Document> cursor =
         collection.find(filter)
             .sort(sort)
             .projection(projection)
             .batchSize(500)
             .cursor()) {

    while (cursor.hasNext()) {
        processIdempotently(cursor.next());
    }
}
```

Sau đó mở rộng bằng checkpoint, bounded buffering, cancellation, monitoring và data consistency theo yêu cầu thực tế.

**Đọc tập dữ liệu lớn an toàn là bài toán về cả bộ nhớ, tốc độ, vòng đời tài nguyên lẫn khả năng phục hồi — không chỉ một vòng lặp `while (cursor.hasNext())`.**
