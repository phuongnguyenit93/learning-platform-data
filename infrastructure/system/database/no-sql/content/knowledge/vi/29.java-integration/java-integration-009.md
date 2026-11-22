# Phân trang, đọc dạng luồng và kiểm soát bộ nhớ

Một câu truy vấn NoSQL có thể trả về vài bản ghi hoặc hàng triệu bản ghi. Với dữ liệu nhỏ, gọi driver, nhận một danh sách rồi trả JSON có vẻ đơn giản. Nhưng khi danh sách lớn, cách làm ấy nhanh chóng trở thành một lỗi kiến trúc: ứng dụng Java tốn heap, garbage collector (GC) chạy liên tục, response chậm, kết nối bị giữ lâu và có thể xuất hiện `OutOfMemoryError`.

Ba cơ chế cần phối hợp là **phân trang (pagination)**, **đọc dạng luồng (streaming)** và **kiểm soát bộ nhớ (memory control)**:

- **Phân trang** chia kết quả logic thành những phần có kích thước giới hạn để client điều hướng hoặc worker xử lý tiếp.
- **Đọc dạng luồng** tiêu thụ dữ liệu dần, thay vì đợi tải tất cả kết quả vào RAM.
- **Kiểm soát bộ nhớ** giới hạn lượng dữ liệu đang được giữ đồng thời, gồm kết quả giải mã, buffers, hàng đợi, dữ liệu chuyển đổi và các request song song.

Trong chương **Kết nối Java** của module **Database No SQL**, các cơ chế này còn gắn với driver, kết nối, timeout, retry, cursor state, backpressure và consistency. Bài học sử dụng các ví dụ với MongoDB Java Driver, Apache Cassandra Java Driver, AWS SDK for Java v2/DynamoDB, Redis SCAN và Java thuần để minh họa các mẫu thiết kế; chúng **không có API phân trang giống hệt nhau**.

> **Nguyên tắc quan trọng nhất:** Một API trả từng trang **không đồng nghĩa** ứng dụng dùng bộ nhớ có giới hạn. Nếu backend tải toàn bộ dữ liệu rồi cắt `subList`, hoặc đọc từ cursor nhưng gọi `collect(toList())` cho hàng triệu kết quả, ứng dụng vẫn có thể hết bộ nhớ.

## 1. Tình huống: danh sách giao dịch của người dùng

Giả sử một ứng dụng có bảng/collection chứa 20 triệu giao dịch:

~~~text
transactionId
tenantId
userId
createdAt
amountMinor
currency
status
description
~~~

Người dùng cần:

1. Xem 30 giao dịch mới nhất.
2. Chọn “Xem tiếp” để lấy 30 giao dịch cũ hơn.
3. Xuất báo cáo của một tháng ra CSV.
4. Chạy job thống kê theo ngày mà không giữ tất cả giao dịch trong RAM.

Ba nhu cầu đầu có thể cùng đọc một dữ liệu nguồn nhưng cần **hợp đồng khác nhau**:

| Trường hợp | Mục tiêu | Cách tiếp cận thường hợp lý |
| --- | --- | --- |
| Trang giao dịch | Lấy một trang nhỏ, chuyển trang tiếp | Keyset/cursor, stable ordering |
| Export CSV | Duyệt tất cả kết quả đủ điều kiện | Paged iteration + streaming output |
| Aggregation dài | Xử lý hàng loạt với bộ nhớ giới hạn | Streaming + incremental aggregation |
| Truy vấn admin vài chục dòng | Đơn giản, có thể đi tới trang n | Offset có giới hạn nếu DB hỗ trợ tốt |

**Không nên dùng một API `findAllTransactions()` trả `List<Transaction>` cho cả bốn trường hợp.**

## 2. Phân biệt page ở API, page của driver và batch của ứng dụng

Ba đơn vị dễ bị nhầm:

~~~text
HTTP/API page:
  Màn hình yêu cầu tối đa 30 giao dịch.

Database/driver page:
  Driver lấy một nhóm hàng qua network, ví dụ 100 hoặc 200.

Processing batch:
  Worker xử lý/ghi file thành từng nhóm, ví dụ 500.
~~~

Ba con số **có thể khác nhau**. Một API page 30 records không yêu cầu driver page đúng 30 trong mọi DBMS. Ngược lại, đọc 200 records từ driver không buộc backend trả cả 200 về client.

### Ví dụ đường đi

~~~text
HTTP GET /transactions?pageSize=30&cursor=...
                |
                v
Java service validates user/tenant/query
                |
                v
NoSQL driver fetches a bounded batch
                |
                v
Service maps up to 30 response objects
                |
                v
HTTP response: items + nextCursor
~~~

Nếu response API cần thêm thông tin `hasMore` chính xác, có thể cần đọc dư một item hoặc dùng token/hasMore do storage cung cấp. Quy tắc tùy từng backend, **không lấy “đã đủ 30 item” làm bằng chứng chắc chắn còn trang tiếp**.

## 3. Vì sao `findAll()` nguy hiểm?

Đoạn code:

~~~java
List<Transaction> all = repository.findAll();
List<Transaction> firstPage = all.subList(0, 30);
~~~

có thể khiến ứng dụng tải toàn bộ dữ liệu vào heap **trước khi** chọn 30 phần tử.

Giả sử 100.000 records được giải mã thành trung bình khoảng 2 KiB/record trong Java heap (chỉ là giả định minh họa):

\[
100000\times2\ \text{KiB}\approx195.3\ \text{MiB}
\]

Đó **chưa kể** đối tượng chứa danh sách, String/byte arrays, driver buffers, JSON DTO, logs và các requests khác.

Nếu mười requests tương tự chạy song song, bộ nhớ giữ dữ liệu có thể lớn hơn nhiều. Số byte serialized trên network **không bằng** số byte object Java sau decode.

### Anti-pattern không chỉ có `findAll`

~~~java
// Đọc tất cả rồi lọc ở application.
List<Transaction> all = loadEveryTransaction();
List<Transaction> result = all.stream()
        .filter(tx -> tx.userId().equals(userId))
        .limit(30)
        .toList();
~~~

Giải pháp đúng: **push filter, sort, limit và projection xuống database khi có thể**, và dùng index/access pattern phù hợp.

## 4. Các kiểu phân trang chính

| Chiến lược | Cách tiếp tục | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Offset/limit | `OFFSET n LIMIT k` hoặc `skip(n).limit(k)` | Dễ triển khai trang số | Offset sâu tốn chi phí, biến động dữ liệu gây duplicate/missing |
| Keyset/seek | Gửi khóa sort cuối trang trước | Hiệu quả trên index phù hợp | Cần thứ tự ổn định, không nhảy tùy ý tới trang 500 |
| Opaque cursor/token | Dùng token backend hoặc ứng dụng | Diễn đạt trạng thái tiếp tục chính xác hơn | Có thể bị ràng buộc với query, session, TTL, driver |
| Time-window/bucket | Chia theo khoảng thời gian/partition | Tốt cho export và time-series lớn | Phải định nghĩa ranh giới và xử lý khoảng trống |
| Snapshot/PIT cursor | Đọc từ snapshot/mốc logic | Giảm biến động giữa các trang | Có chi phí và điều kiện hỗ trợ riêng |

Không có thuật toán nào tốt nhất mọi nơi. **Access pattern, indexing và yêu cầu consistency** quyết định cách phân trang.

## 5. Offset pagination: dễ hiểu nhưng có giá

Ví dụ với cơ sở dữ liệu hỗ trợ `skip`:

~~~text
pageSize = 20
page     = 1 → skip 0,  limit 20
page     = 2 → skip 20, limit 20
page     = 3 → skip 40, limit 20
~~~

Trên MongoDB:

~~~java
collection.find(filter)
        .sort(Sorts.descending("createdAt", "_id"))
        .skip(40)
        .limit(20);
~~~

### Vấn đề offset sâu

Yêu cầu:

~~~text
skip(1_000_000).limit(20)
~~~

có thể buộc storage xử lý/bỏ qua số lượng kết quả lớn trước khi tới trang cần đọc, tùy index và query plan. Tốc độ không nhất thiết ổn định khi page number tăng.

### Vấn đề với dữ liệu thay đổi

Giả sử sort mới nhất trước:

~~~text
Trước: [A, B, C, D, E, F]
Trang 1, size 3: [A, B, C]
~~~

Giữa hai requests, item X mới được thêm ở đầu:

~~~text
Sau: [X, A, B, C, D, E, F]
Trang 2 skip(3): [C, D, E]
~~~

Item C bị trả **hai lần**. Nếu một item phía trước bị xóa, khách có thể **bỏ sót** một item.

Offset phù hợp với tập nhỏ/ít biến động hoặc UI thực sự cần số trang, nhưng **không nên mặc định dùng cho lịch sử lớn và ghi liên tục**.

## 6. Keyset pagination: tiếp tục từ khóa cuối trang

Giả sử sắp theo:

~~~text
ORDER BY createdAt DESC, id DESC
~~~

Trang đầu:

~~~text
(2026-11-14T10:00:00Z, 105)
(2026-11-14T09:59:00Z, 104)
(2026-11-14T09:58:00Z, 103)
~~~

Cursor chứa **sort tuple của record cuối**:

~~~text
afterCreatedAt = 2026-11-14T09:58:00Z
afterId        = 103
~~~

Trang tiếp theo dùng điều kiện logic:

\[
(createdAt,id)<(afterCreatedAt,afterId)
\]

với thứ tự giảm dần. Viết tường minh:

~~~sql
WHERE created_at < :last_created_at
   OR (
       created_at = :last_created_at
       AND id < :last_id
   )
ORDER BY created_at DESC, id DESC
LIMIT :page_size;
~~~

Đây là **SQL minh họa logic thứ tự**, không có nghĩa mọi NoSQL hỗ trợ tuple comparison hoặc cú pháp đó. Trên MongoDB có thể biểu diễn bằng `$or`, `$lt` và các filters tương đương; Cassandra/DynamoDB cần thiết kế key schema phù hợp.

### Tại sao phải có tie-breaker?

Nếu chỉ sort `createdAt`, nhiều records có thể cùng timestamp. Cursor bằng timestamp cuối có thể làm **mất các records có timestamp bằng nhau** chưa được trả.

Do đó cần một thứ tự **toàn phần và ổn định trong phạm vi query**, ví dụ `(createdAt,id)`, với `id` duy nhất.

## 7. Chọn thứ tự sort ổn định

Một cursor đúng cần hiểu:

1. Sort theo field nào, ascending hay descending?
2. Những field ấy có **immutable** không?
3. Có unique tie-breaker không?
4. Nulls, kiểu dữ liệu, collation và timezone được so theo quy tắc nào?
5. Có compound index để hỗ trợ filter + sort không?

Ví dụ:

~~~text
Sort: createdAt DESC, transactionId DESC
Filter: tenantId = T42 AND userId = U9
~~~

Nếu transaction `createdAt` bị sửa giữa hai lần gọi API, nó có thể chuyển vị trí qua cursor. Keyset giúp tránh một lớp lỗi offset nhưng **không tự đảm bảo snapshot nhất quán khi dữ liệu đang thay đổi**.

### Nguyên tắc thực hành

Ưu tiên khóa sort **bất biến** (creation timestamp hoặc sequence được commit) và tie-breaker duy nhất. Nếu nghiệp vụ cần list theo field có thể đổi, phải chấp nhận/giải quyết nguy cơ duplicate/missing hoặc dùng snapshot semantics.

## 8. Keyset không bảo đảm một ảnh chụp bất biến

Trong hệ ghi liên tục:

~~~text
T0: Client đọc trang 1.
T1: Một record cũ đổi status/filter.
T2: Một record khác bị xóa.
T3: Client đọc trang 2 từ cursor.
~~~

Keyset vẫn có thể:

- Không trả record đã bị xóa.
- Không trả record mới không thuộc đoạn sau cursor.
- Có kết quả khác khi filter field thay đổi.
- Gặp duplicate nếu sort key có thể được sửa.

Nếu người dùng chỉ duyệt timeline, điều đó có thể chấp nhận được. Nếu yêu cầu **xuất chính xác tập records tại thời điểm T0**, cần một cơ chế khác: snapshot transaction, point-in-time token, application watermark với dữ liệu bất biến, hoặc thuật toán export có high-watermark/reconciliation.

**Cursor biểu diễn vị trí tiếp tục; nó không tự là snapshot token.**

## 9. Offset hay keyset? Chọn theo mục tiêu

| Câu hỏi | Offset | Keyset |
| --- | --- | --- |
| Có nút “trang 1, 2, 3” dễ không? | Có | Không tự nhiên |
| Tới trang rất sâu có ổn không? | Có thể đắt | Thường tốt nếu index đúng |
| Dữ liệu bị insert trước trang hiện tại? | Có thể trùng/bỏ sót | Thường ổn hơn với sort key ổn định |
| Cần unique sort key? | Dù vậy vẫn nên có | Rất quan trọng |
| Tự tạo snapshot consistent? | Không | Không |
| Phù hợp feed vô hạn? | Kém | Thường phù hợp |
| Nhảy tới trang 1000? | Dễ biểu diễn | Cần lưu/checkpoint cursor hoặc phương án khác |

**Không biến “keyset luôn nhanh” thành quy tắc tuyệt đối.** Index sai, filter không chọn lọc, sorting khác storage order hoặc query fan-out có thể vẫn rất đắt.

## 10. Opaque continuation token

Nhiều NoSQL APIs trả về một **continuation token**, không phải integer page:

~~~json
{
  "items": [
    {"transactionId":"tx-101"},
    {"transactionId":"tx-100"}
  ],
  "nextCursor": "opaque-token-from-server"
}
~~~

Client chỉ cần gửi lại token để tiếp tục. Token có thể là:

- Paging state do DB driver cấp.
- Keyset tuple được ứng dụng mã hóa.
- DynamoDB last evaluated key đã đóng gói.
- Search engine sort tuple/snapshot reference.
- Một ID tham chiếu tới server-side state.

**Opaque không có nghĩa token luôn an toàn để công khai nguyên dạng.** Token có thể tiết lộ khóa, thông tin query hoặc nhạy cảm với phiên bản driver. API nên kiểm soát cấu trúc, chữ ký và phạm vi người dùng.

## 11. API phân trang nên trả gì?

Một response:

~~~json
{
  "items": [
    {
      "transactionId": "tx-101",
      "createdAt": "2026-11-14T10:00:00Z",
      "amountMinor": 150000
    }
  ],
  "nextCursor": "opaque-value",
  "pageSize": 30
}
~~~

Các quy tắc:

- `pageSize` có max và default rõ, ví dụ tối đa 100 trong một API cụ thể.
- `nextCursor=null` nghĩa đã xác định hết trang theo semantics backend; không tự suy từ `items.length < pageSize` nếu filter/paging token làm kết quả rỗng tạm thời.
- Exact total count nên là API/chi phí riêng khi cần; không scan tất cả chỉ để hiện “trang 1 trên N”.
- Cursor phải gắn với **filter, sort, tenant, authorization scope, consistency và schema/token version** phù hợp.
- Không cấp khả năng vượt phạm vi tenant khi client đổi cursor.

Pagination token cần được coi là **capability hoặc state không đáng tin từ client**, phải validate trước khi dùng.

## 12. Bảo mật cursor token

Một payload logic:

~~~json
{
  "version": 1,
  "tenantId": "T42",
  "userId": "U9",
  "queryHash": "hash-of-filter-sort",
  "pageSize": 30,
  "lastCreatedAt": "2026-11-14T09:58:00Z",
  "lastId": "tx-103",
  "issuedAt": 1794650000,
  "expiresAt": 1794653600
}
~~~

Các trường là ví dụ minh họa; timestamp expiry phải được tạo theo clock/security contract phù hợp.

### Đừng chỉ Base64-encode

Base64 **không phải encryption** và không bảo vệ khỏi thay đổi nội dung. Cách đóng gói phổ biến:

1. Canonicalize payload với version.
2. **Sign bằng HMAC** hoặc dùng authenticated encryption nếu cần bảo mật thông tin bên trong.
3. Khi nhận, validate signature, expiry, owner scope, query fingerprint và giới hạn kích thước.
4. Kiểm auth của request độc lập với token; không để token thay thế quyền truy cập.
5. Quản lý rotation và TTL.

Nếu token gói pagingState nội bộ DBMS, không cho client tùy ý đổi/giả lập token để quét dữ liệu ngoài phạm vi được phép.

### Cursor không phải định danh trang lâu dài

Một opaque token có thể trở nên vô hiệu sau khi index, session, topology hoặc schema thay đổi tùy backend. API cần nêu lỗi `invalid_cursor`/`expired_cursor` và chiến lược bắt đầu lại.

## 13. MongoDB Java: đọc theo cursor và batch

MongoDB Java sync driver trả về iterator/cursor có thể đọc **dần** từ server. Ví dụ một query để xuất dữ liệu:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

void exportTransactions(
        MongoCollection<Document> collection,
        String tenantId, String userId) {

    try (MongoCursor<Document> cursor = collection
            .find(Filters.and(
                    Filters.eq("tenantId", tenantId),
                    Filters.eq("userId", userId)))
            .sort(Sorts.ascending("createdAt", "_id"))
            .projection(Projections.include(
                    "_id", "createdAt", "amountMinor", "status"))
            .batchSize(200)
            .iterator()) {

        while (cursor.hasNext()) {
            Document row = cursor.next();
            processOne(row);
        }
    }
}
~~~

Trong đó `processOne` là hàm xử lý từng record theo contract riêng.

### Ý nghĩa của `batchSize(200)`

- Driver/server trao đổi theo batches thay vì trả tất cả kết quả một lần.
- Đây là một **gợi ý về số documents mỗi batch**, có thêm những giới hạn byte/protocol; không phải cam kết cố định 200 objects.
- Vòng lặp chỉ giữ `row` đang xử lý **nếu** `processOne` không tích lũy references.
- Cursor phải được đóng để trả tài nguyên server/client, kể cả khi gặp exception hoặc client hủy.

**Không làm**:

~~~java
List<Document> all = new ArrayList<>();
try (MongoCursor<Document> cursor =
         collection.find().batchSize(200).iterator()) {
    while (cursor.hasNext()) {
        all.add(cursor.next());
    }
}
~~~

với hàng triệu documents nếu mục tiêu là bộ nhớ ổn định: `batchSize` không hạn chế `all` tăng lên theo toàn bộ tập dữ liệu.

## 14. MongoDB Java: keyset theo hai trường

Với `createdAt` lưu dạng BSON Date và `_id` là ObjectId:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.bson.types.ObjectId;
import java.util.Date;

void fetchPage(MongoCollection<Document> collection,
               String tenantId,
               Date afterCreatedAt,
               ObjectId afterId,
               int requestedPageSize) {

    int pageSize = Math.max(1,
            Math.min(requestedPageSize, 100));

    Bson scope = Filters.eq("tenantId", tenantId);
    Bson condition = scope;

    if (afterCreatedAt != null && afterId != null) {
        Bson seek = Filters.or(
                Filters.lt("createdAt", afterCreatedAt),
                Filters.and(
                        Filters.eq("createdAt", afterCreatedAt),
                        Filters.lt("_id", afterId)));
        condition = Filters.and(scope, seek);
    }

    try (MongoCursor<Document> cursor = collection
            .find(condition)
            .sort(Sorts.descending("createdAt", "_id"))
            .limit(pageSize)
            .batchSize(pageSize)
            .iterator()) {
        while (cursor.hasNext()) {
            Document row = cursor.next();
            // Đưa vào danh sách response bị chặn bởi pageSize.
            // Dùng sort tuple cuối làm anchor trang tiếp.
        }
    }
}
~~~

### Các điều kiện rất quan trọng

- Có index phù hợp, ví dụ cân nhắc `{tenantId:1, createdAt:-1, _id:-1}` cho query này.
- `createdAt` được lưu thống nhất kiểu Date; nếu có `null` hoặc nhiều kiểu BSON, cần định nghĩa sort contract riêng.
- `_id` là unique tie-breaker; `createdAt` nên bất biến.
- Trang tiếp theo dùng **sort tuple của item cuối đã trả**, không dùng item dư chưa trả.
- Nếu muốn biết `hasMore` chắc hơn, có thể query `pageSize+1`, chỉ trả `pageSize` và dùng record thứ `pageSize+1` để xác định còn dữ liệu trong query đó; vẫn không có snapshot nếu concurrent writes.
- Query phải giữ tenant/auth filter trên **mọi trang**, không dựa vào client để chứng thực.

Keyset này áp dụng cho MongoDB theo data model giả định; không chuyển nguyên điều kiện `$or` sang Cassandra hoặc DynamoDB nếu key schema không hỗ trợ.

## 15. Cassandra Java Driver: page size khác offset

Apache Cassandra tổ chức truy vấn theo **partition key và clustering order**, nên phân trang cần được thiết kế cùng partition/data model. Driver hỗ trợ **paging** thay vì buộc người dùng tự `OFFSET 100000`.

Ví dụ với DataStax/Apache Cassandra Java Driver 4:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

void streamUserOrders(CqlSession session, String userId) {
    SimpleStatement statement = SimpleStatement.builder(
            "SELECT order_id, created_at, status " +
            "FROM orders_by_user WHERE user_id = ?")
            .addPositionalValue(userId)
            .setPageSize(200)
            .build();

    ResultSet rows = session.execute(statement);

    for (Row row : rows) {
        processOrder(row);
    }
}
~~~

Driver có thể **tự fetch trang tiếp theo** khi synchronous iterator hết trang hiện tại và còn dữ liệu. Câu lệnh vẫn có thể tốn nhiều thời gian/tải nếu partition chứa hàng triệu rows; page size không sửa được một data model/partition quá lớn.

### Những điều cần hiểu

- `setPageSize(200)` là giới hạn/hint về số rows trong một page theo semantics driver/server, không phải giới hạn byte chính xác.
- Query `WHERE user_id = ?` cần phù hợp khóa partition/schema.
- Không tự nối `ALLOW FILTERING` để “cho query chạy” khi access pattern sai.
- Không gom hết `ResultSet` vào một `ArrayList`.
- Paging state có thể bị ràng buộc với statement/parameters/protocol/driver; không tùy ý tái sử dụng token cho query khác.
- Network timeout trong lúc lấy trang tiếp theo đòi xử lý recovery/retry có kiểm soát, không tự giả định resume không tạo duplicate.

### Về synchronous paging

Vòng lặp đơn giản nhưng `hasNext()/next()` có thể phải đợi I/O lấy page mới. Nếu chạy trên request thread hoặc event-loop thread, cần biết mô hình blocking của ứng dụng.

## 16. Cassandra asynchronous paging và giới hạn concurrent requests

Driver 4 có `AsyncResultSet`, `currentPage()` và `fetchNextPage()` để ứng dụng điều khiển lấy page kế tiếp.

Mô hình:

~~~text
executeAsync(statement)
   |
   v
AsyncResultSet page 1
   |
   +--> process currentPage items
   |
   +--> if hasMorePages:
              fetchNextPage()
                 |
                 v
              AsyncResultSet page 2
                 ...
~~~

Skeleton:

~~~java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.concurrent.CompletionStage;

CompletionStage<Void> consumeAll(AsyncResultSet page) {
    for (Row row : page.currentPage()) {
        processOrder(row);
    }
    if (!page.hasMorePages()) {
        return java.util.concurrent.CompletableFuture
                .completedFuture(null);
    }
    return page.fetchNextPage().thenCompose(this::consumeAll);
}
~~~

Đây là **skeleton method** trong một service đã định nghĩa `processOrder`; không phải class Java hoàn chỉnh.

### Lưu ý về backpressure

- Code chỉ fetch page tiếp theo **sau khi** xử lý page hiện tại đồng bộ hoàn tất.
- Nếu `processOrder` chỉ **khởi động async I/O** rồi trả ngay, code có thể tiếp tục fetch khi hàng nghìn operations chưa hoàn tất. Khi đó cần đợi các futures/bounded concurrency trước khi fetch tiếp.
- Không dùng `CompletableFuture.allOf` trên danh sách không giới hạn.
- Theo dõi số pages/rows đang in-flight, queue và deadline.

Chính sách **một page đang xử lý hoặc một số ít pages prefetch có giới hạn** là nền tảng kiểm soát memory.

## 17. DynamoDB Query và `LastEvaluatedKey`

AWS DynamoDB trả kết quả `Query` theo page có giới hạn dữ liệu và có thể trả `LastEvaluatedKey` để tiếp tục.

Ví dụ AWS SDK for Java v2:

~~~java
import java.util.Collections;
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.QueryResponse;

void scanUserHistory(
        DynamoDbClient client,
        String userId) {

    Map<String, AttributeValue> nextKey =
            Collections.emptyMap();

    do {
        QueryRequest.Builder builder = QueryRequest.builder()
                .tableName("OrdersByUser")
                .keyConditionExpression("userId = :u")
                .expressionAttributeValues(Map.of(
                        ":u", AttributeValue.builder()
                                .s(userId).build()))
                .limit(100);

        if (nextKey != null && !nextKey.isEmpty()) {
            builder.exclusiveStartKey(nextKey);
        }

        QueryResponse response = client.query(builder.build());

        for (Map<String, AttributeValue> item
                : response.items()) {
            processDynamoItem(item);
        }

        nextKey = response.lastEvaluatedKey();
    } while (nextKey != null && !nextKey.isEmpty());
}
~~~

Đây là **phương thức minh họa**; `processDynamoItem` do ứng dụng định nghĩa. Thiết kế bảng `OrdersByUser` giả định `userId` phù hợp partition key.

### Các đặc điểm cần nhớ

- `LastEvaluatedKey` không rỗng nghĩa là có trạng thái để **tiếp tục duyệt**; không có nghĩa chắc chắn trang sau sẽ trả item phù hợp filter.
- Một `Query` có giới hạn page response theo **dung lượng** (thường được mô tả là tối đa 1 MiB dữ liệu xử lý cho một lần Query theo semantics DynamoDB) và `Limit`, không chỉ theo số records cuối trả về.
- Nếu dùng `FilterExpression`, filter thường được áp **sau khi** đọc những items theo key condition. Một page có thể **không trả item nào** nhưng vẫn có `LastEvaluatedKey` để tiếp tục.
- `Limit` và response item count không giống một cách tuyệt đối khi có filter.
- `Query` theo partition/key condition khác `Scan` quét bảng; không dùng Scan cho endpoint hot nếu access pattern cho phép thiết kế key.
- Hạn chế tổng số concurrent requests và đọc consumption capacity theo workload.

### Không được dừng khi `items.isEmpty()`

Sai:

~~~java
if (response.items().isEmpty()) {
    return;
}
~~~

Vì trang rỗng sau filter vẫn có thể còn continuation token. Điều kiện kết thúc cần dựa vào token theo API.

## 18. DynamoDB paginator của SDK

AWS SDK v2 còn có các **paginator** để lặp qua pages:

~~~java
QueryRequest request = QueryRequest.builder()
        .tableName("OrdersByUser")
        .keyConditionExpression("userId = :u")
        .expressionAttributeValues(Map.of(
                ":u", AttributeValue.builder()
                        .s(userId).build()))
        .limit(100)
        .build();

for (QueryResponse page
        : client.queryPaginator(request)) {
    for (Map<String, AttributeValue> item : page.items()) {
        processDynamoItem(item);
    }
}
~~~

Trong mẫu này, SDK tự điều phối `LastEvaluatedKey`. **Paginators không tự đặt một giới hạn tổng số pages**, nên vòng lặp vẫn có thể chạy rất lâu hoặc tốn nhiều read capacity.

Với HTTP API chỉ cần một trang, không nhất thiết dùng paginator để duyệt mọi page rồi cắt kết quả. Chỉ thực hiện lượng đọc cần thiết cho **một API response**.

## 19. Redis SCAN là cursor-based iteration nhưng không phải snapshot

Redis có lệnh `SCAN` cho phép duyệt keyspace theo cursor:

~~~text
SCAN 0 MATCH tenant:42:* COUNT 200
→ [nextCursor, keys...]

SCAN nextCursor MATCH tenant:42:* COUNT 200
→ ...
~~~

Khi cursor quay về `0` theo contract, một vòng duyệt kết thúc.

### Chú ý đặc biệt

- `COUNT` là **hint về lượng công việc**, không đảm bảo chính xác 200 keys mỗi lần.
- Một lượt `SCAN` có thể trả 0 keys nhưng cursor **chưa về 0**.
- Trong lúc keyspace thay đổi, kết quả có thể có **duplicates**; các bảo đảm về key thêm/xóa trong thời gian scan bị giới hạn bởi semantics Redis.
- Không nên dùng `SCAN` làm một snapshot chính xác cho kế toán hoặc inventory.
- Trên Redis Cluster, cần hiểu cách công cụ duyệt các nodes/shards; một cursor của một node không tự đại diện toàn cluster.
- `KEYS *` có thể gây blocking/tải cao trên tập key lớn, nên không dùng cho đường ứng dụng nóng.

Redis SCAN phục vụ **bảo trì, kiểm kê gần đúng hoặc các công việc có thể dedupe/reconcile**, không thay authoritative range query khi yêu cầu nhất quán snapshot.

## 20. Search engines: `search_after` và snapshot/PIT

Một số search engines hỗ trợ **search-after** thay cho deep offset pagination. Ý tưởng:

~~~json
{
  "sort": [
    {"createdAt":"desc"},
    {"id":"desc"}
  ],
  "search_after": [
    "2026-11-14T09:58:00Z",
    "tx-103"
  ],
  "size": 30
}
~~~

Đây là mô tả **khái niệm request**, không phải đoạn cấu hình có thể dùng nguyên xi trên mọi Elasticsearch/OpenSearch version. Phải tuân theo mapping/DSL của engine và sort-value type.

### Tại sao cần PIT/snapshot?

Search index có thể thay đổi giữa pages. Nếu yêu cầu duyệt nhất quán nhiều trang, một số engines hỗ trợ **point-in-time (PIT)** hoặc snapshot reference cho search context.

Ngay cả khi dùng PIT:

- Token/context có lifetime và chi phí tài nguyên.
- Phải release/expire theo API.
- Cursor sort values gắn với cùng query và PIT.
- Không nên giữ hàng nghìn PIT lâu chỉ vì client không bao giờ đóng.

**search_after là vị trí tiếp tục; PIT mới là một cách giữ ngữ cảnh dữ liệu phù hợp trong phạm vi engine hỗ trợ.**

## 21. Phân trang theo bucket thời gian/partition

Trong NoSQL, đôi khi cần thiết kế key schema để hỗ trợ đọc dài:

~~~text
PK = userId#YYYY-MM
SK = createdAt#transactionId
~~~

Để xem lịch sử một user:

~~~text
November partition → October partition → September ...
~~~

Lợi ích:

- Mỗi partition/bucket có kích thước được giới hạn theo thiết kế.
- Query có thể lấy range theo sort key.
- Tránh một partition vô hạn khi user có lịch sử lớn.
- Worker export có thể checkpoint theo bucket + cursor.

### Hợp đồng cursor

~~~json
{
  "bucket": "2026-11",
  "lastSortKey": "2026-11-14T09:58:00Z#tx-103",
  "queryVersion": 3
}
~~~

Khi hết bucket, chuyển sang bucket kế theo thứ tự xác định. Cần xử lý bucket rỗng, timezone, retention, tenant và limit số bucket/requests của một API.

### Một vấn đề nghiệp vụ

Nếu transaction được phép backdate hoặc `createdAt` thay đổi, cursor theo bucket thời gian có thể thiếu/đúp. Với export cần đúng tập records, hãy chọn khóa immutable và mô tả snapshot/high-watermark.

## 22. Streaming là gì và không phải gì?

Trong Java, “stream” có nhiều nghĩa:

| Khái niệm | Ý nghĩa |
| --- | --- |
| `java.util.stream.Stream<T>` | API xử lý sequence; **không tự đồng nghĩa I/O streaming** |
| DB cursor/iterator | Lấy/tiêu thụ records theo batch |
| Reactive Publisher | Phát records/pages theo subscription và demand |
| HTTP streaming | Gửi response từng chunk thay vì dựng toàn body |
| Java `InputStream`/`OutputStream` | Đọc/ghi bytes dần |
| CDC/change stream | Nhận thay đổi đang xảy ra sau thời điểm subscribe |

Một Java `Stream<T>` tạo từ một `List<T>` đã chứa 1 triệu objects **không tiết kiệm heap**. Một database cursor có thể lazy, nhưng nếu cuối cùng `collect(toList())` vào list lớn, bộ nhớ vẫn tăng.

**Streaming thật cần end-to-end flow control**, không chỉ một method có chữ `stream` trong tên.

## 23. Iterator lazy nhưng phép xử lý có thể eager

So sánh:

~~~java
// Giới hạn bộ nhớ nếu cursor lazy và processOne không giữ record.
while (cursor.hasNext()) {
    processOne(cursor.next());
}
~~~

và:

~~~java
// Vẫn gom tất cả records vào RAM.
List<Document> all = new ArrayList<>();
while (cursor.hasNext()) {
    all.add(cursor.next());
}
~~~

Một trường hợp khác:

~~~java
Map<String, List<Document>> groups = new HashMap<>();
while (cursor.hasNext()) {
    Document row = cursor.next();
    groups.computeIfAbsent(
            row.getString("userId"),
            ignored -> new ArrayList<>()).add(row);
}
~~~

Đường đọc có thể bounded nhưng **aggregation data structure** tăng theo số lượng records. Đối với báo cáo lớn:

- Đẩy group-by xuống analytical database nếu có.
- Xử lý từng partition/time bucket.
- Dùng incremental aggregation khi phép tính cho phép.
- Spill ra disk hoặc dùng external sorting khi cần exact grouping/sorting.
- Dùng approximate algorithms nếu business chấp nhận sai số.

Đừng chỉ kiểm `pageSize` mà quên những collections do business logic tạo ra.

## 24. Ước lượng heap theo concurrency

Một mô hình đơn giản:

\[
M_{\text{data}}\approx
C\times P\times B\times S
\]

Trong đó:

- `C`: số operations/requests concurrent.
- `P`: số pages/batches được giữ hoặc prefetch cho mỗi operation.
- `B`: số items tối đa trong mỗi batch.
- `S`: kích thước object Java trung bình của một item.

Ví dụ:

~~~text
Concurrent requests C = 8
Prefetched pages P    = 2
Items per page B      = 500
Heap per item S       = 5,000 bytes
~~~

Khi đó:

\[
M_{\text{data}}\approx8\times2\times500\times5000
=40,000,000\text{ bytes}\approx38.1\text{ MiB}
\]

Đây chỉ là **phần dữ liệu được giữ** theo mô hình. Còn có:

- Driver/network receive buffers.
- JSON codecs và temporary allocations.
- Object headers, references, String backing arrays.
- TLS/direct/off-heap buffers.
- Executor queues, thread stacks.
- Response serialization và caches.
- GC overhead và những service components khác.

**PageSize nhỏ không bảo đảm memory thấp khi concurrency hoặc prefetch lớn không giới hạn.**

## 25. Chọn pageSize bằng đo đạc, không bằng cảm giác

### Page rất nhỏ

- Nhiều network round trips.
- Tăng overhead protocol và CPU.
- Có thể giảm throughput export.
- Dễ nhạy cảm với latency cross-region.

### Page rất lớn

- Heap và decode spike.
- GC pauses.
- Một request chiếm nhiều network/buffer resources.
- Time-to-first-item lâu hơn trong một số mô hình.
- Khi retry, số work lặp lại lớn.

### Quy trình chọn

1. Chọn giá trị xuất phát có giới hạn, ví dụ 100–500 items với row size vừa, **chỉ để thử**.
2. Đo serialized bytes, heap allocations, p95/p99, CPU, GC, network RTT và QPS.
3. Đo nhiều kích thước record (small/large), không chỉ trung bình.
4. Tăng pageSize nếu network overhead đang chi phối và còn heap headroom.
5. Giảm pageSize/prefetch nếu decode/GC spike.
6. Kiểm trong trường hợp concurrency cao và node chậm.

Kết quả phải được gắn với workload cụ thể, không áp một `fetchSize=1000` cho toàn bộ repository.

## 26. Giới hạn số records và giới hạn bytes khác nhau

Một record có thể:

~~~text
Small document: 200 bytes serialized
Large document: 2 MiB serialized
~~~

Nếu chỉ giới hạn **100 records**, page có thể rất nhỏ hoặc rất lớn.

Nhiều NoSQL databases có giới hạn **page response theo bytes**, nên số items thực tế trên mỗi page có thể biến thiên. Ứng dụng cũng nên có:

- Projection chỉ lấy fields cần.
- Limit kích thước document/request.
- Bounded page items hoặc byte budget.
- Separate blob/object storage cho payload rất lớn nếu hợp lý.

**Đừng truyền hàng nghìn kilobytes JSON metadata nếu UI chỉ cần id, timestamp và amount.**

## 27. Projection giúp giảm memory và network

Ví dụ một document:

~~~json
{
  "id": "L42",
  "title": "Apartment",
  "description": "...long text...",
  "imageMetadata": ["...many items..."],
  "reviewSamples": ["..."],
  "city": "Da Nang",
  "priceMinor": 1750000
}
~~~

Trang search chỉ cần:

~~~json
{
  "id": "L42",
  "title": "Apartment",
  "city": "Da Nang",
  "priceMinor": 1750000
}
~~~

Hãy dùng DB projection/attribute selection để tránh truyền field không cần. Tuy nhiên **projection không tự làm query rẻ về đọc storage** trên mọi engine; có thể vẫn cần fetch record hoặc index chưa cover. Đánh giá query plan và consumed capacity.

### Java object mapping

Nếu ánh xạ mọi BSON document sang một domain aggregate đầy đủ chỉ để lấy hai fields, object graph có thể rất lớn. Chọn DTO nhẹ theo access pattern và tránh tạo nhiều bản sao trung gian không cần thiết.

## 28. Backpressure là gì?

**Backpressure** là cơ chế cho bên xử lý chậm kiểm soát lượng dữ liệu mà bên cung cấp phát thêm.

~~~text
DB pages → Decoder → Business processor → File/HTTP sink
                 fast                 slow
~~~

Nếu producer tạo 10.000 records/s nhưng consumer xử lý 1.000 records/s, hàng đợi tăng:

\[
\Delta Q\approx(10000-1000)\times t
\]

Sau 60 giây, tăng khoảng:

\[
540,000\text{ records}
\]

nếu không hạn chế producer. Đây là nguyên nhân OOM ngay cả khi mỗi database page chỉ 100 rows.

### Cách giữ memory bounded

- Consumer chỉ yêu cầu page/batch mới khi còn capacity.
- Bounded queue, ví dụ `ArrayBlockingQueue` thay vì queue không giới hạn.
- Giới hạn số requests/pages in-flight.
- Khi sink chậm, giảm hoặc dừng fetch.
- Có cancellation/timeout khi client ngắt kết nối.

**Backpressure phải truyền từ sink trở lại nguồn**, không chỉ đặt một queue nhỏ rồi producer vẫn enqueue vô hạn ở nơi khác.

## 29. Java Flow: mô hình request–demand

Java 9+ có `java.util.concurrent.Flow` với các khái niệm `Publisher`, `Subscriber` và `Subscription`.

Một subscriber yêu cầu từng item:

~~~java
import java.util.concurrent.Flow;

final class OneAtATimeSubscriber
        implements Flow.Subscriber<String> {

    private Flow.Subscription subscription;

    @Override
    public void onSubscribe(Flow.Subscription s) {
        subscription = s;
        s.request(1);
    }

    @Override
    public void onNext(String item) {
        try {
            processOne(item);
            subscription.request(1);
        } catch (RuntimeException ex) {
            subscription.cancel();
            throw ex; // Production code: coordinate error reporting.
        }
    }

    @Override
    public void onError(Throwable error) {
        reportFailure(error);
    }

    @Override
    public void onComplete() {
        markCompleted();
    }
}
~~~

`processOne`, `reportFailure` và `markCompleted` là methods thuộc service và không được định nghĩa trong skeleton này.

### Điều quan trọng

- `request(1)` cho biết subscriber có capacity nhận một item theo reactive-streams contract.
- Không gọi `request(Long.MAX_VALUE)` cho pipeline ghi file chậm mà không hiểu buffering.
- Nếu `processOne` bắt đầu một async operation rồi trả ngay, `request(1)` lập tức có thể vẫn làm quá nhiều operations in-flight; phải chỉ request thêm khi async work hoàn tất.
- Một `Publisher` chỉ thật sự kiểm soát DB fetch nếu adapter của nó **truyền demand xuống driver**, không preload toàn bộ kết quả.
- Nếu `onNext` ném exception, cách xử lý lỗi và cancellation tùy implementation; production subscriber nên bảo vệ protocol và truyền failure về supervisor.

**Reactive API không mặc nhiên low-memory nếu có `buffer()`/`collectList()` hoặc unbounded flatMap concurrency.**

## 30. Reactive MongoDB và các thư viện reactive

Một reactive driver có thể trả `Publisher<T>` hoặc kiểu stream của framework (Reactor `Flux`, RxJava `Flowable`...).

Nhưng cần phân biệt:

~~~text
Backpressure-aware source:
  Request N → fetch/deliver bounded amount → wait for more demand.

Not actually bounded:
  Load all database records → emit them via Flux.fromIterable(all).
~~~

Ở tầng application:

- Đặt giới hạn concurrency của `flatMap`.
- Không dùng `collectList()` với một luồng không giới hạn.
- Dùng batching có size/time limit.
- Theo dõi số items buffered.
- Propagate `cancel` khi client disconnect hoặc deadline hết.
- Tránh blocking I/O trực tiếp trên event loop; chuyển đến executor phù hợp nếu framework hỗ trợ.

Tên thư viện và những operators chính xác phụ thuộc version; không sao chép một `Flux` sample từ hệ khác rồi mặc định driver thực sự streaming từ database.

## 31. Async không đồng nghĩa streaming

Một hàm:

~~~java
CompletableFuture<List<Transaction>> loadEverythingAsync();
~~~

có thể chạy không chặn thread gọi nhưng vẫn **tải mọi records vào một list lớn** rồi hoàn tất. Nó là **asynchronous**, không phải bounded-memory streaming.

Ngược lại:

~~~java
Iterator<Transaction> cursor;
while (cursor.hasNext()) {
    writeOne(cursor.next());
}
~~~

có thể dùng ít memory nhưng blocking một worker thread.

Hai trục độc lập:

| | Bounded memory | Có thể unbounded memory |
| --- | --- | --- |
| Synchronous | Iterator/cursor consume-one-at-a-time | `findAll()` |
| Asynchronous | Page-aware async/reactive backpressure | `Future<List<AllRows>>` |

Chọn kiến trúc theo thread model, concurrency và throughput; **đừng coi async là lời giải cho OOM**.

## 32. Bounded processing queue

Giả sử một reader lấy database pages, còn một writer ghi file:

~~~text
DB Reader → bounded queue(256 rows) → File Writer
~~~

Nếu writer chậm, reader phải **chờ** còn capacity, không chuyển sang một list phụ không giới hạn.

Trong Java:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

BlockingQueue<String> queue =
        new ArrayBlockingQueue<>(256);

// Producer phải dùng put/offer với timeout phù hợp.
// Consumer dùng take/poll và báo capacity về upstream.
~~~

### Các chi tiết sản xuất cần thiết

- Có quy tắc end-of-stream (poison item hoặc completion signal), tránh consumer treo.
- Khi producer/consumer lỗi, propagate error, đóng cursor và hủy task còn lại.
- Không để thread blocked vô hạn khi client hủy.
- Không prefetch nhiều pages hơn queue capacity.
- Nếu một row quá lớn, queue 256 items vẫn có thể tốn nhiều memory; cần kiểm byte sizes.

Đừng dùng `Executors.newFixedThreadPool(...)` với work submissions không hạn chế mà không xem queue của executor; một số executor setups dùng **unbounded task queue**.

## 33. Streaming export CSV

Export hàng triệu records thường nên dùng:

~~~text
DB cursor/page reader
        |
        v
Incremental CSV encoder
        |
        v
BufferedWriter / HTTP streaming / object storage upload
~~~

Không tạo một `StringBuilder` chứa toàn CSV trước khi trả client.

Skeleton Java:

~~~java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

void exportCsv(Path output) throws Exception {
    try (BufferedWriter writer =
            Files.newBufferedWriter(
                    output, StandardCharsets.UTF_8)) {

        writer.write("id,createdAt,amountMinor");
        writer.newLine();

        // Mỗi iteration chỉ lấy record kế tiếp từ
        // một cursor/page reader có bounded buffers.
        while (sourceHasNext()) {
            TransactionRow row = sourceNext();
            writer.write(csvEscape(row.id()));
            writer.write(",");
            writer.write(csvEscape(row.createdAt()));
            writer.write(",");
            writer.write(Long.toString(row.amountMinor()));
            writer.newLine();
        }
    }
}
~~~

`TransactionRow`, `sourceHasNext`, `sourceNext` và `csvEscape` là các thành phần do ứng dụng định nghĩa. Đây là skeleton tập trung vào **bộ nhớ và vòng đời writer**, không phải một class Java biên dịch độc lập.

### Tránh các lỗi CSV

- Escape dấu phẩy, quotes và newline theo CSV dialect.
- Nếu file được mở bằng spreadsheet software, xem rủi ro **formula injection** từ chuỗi không tin cậy.
- Đặt encoding và header rõ.
- Không giữ toàn bộ rows chỉ để tạo file.
- Dùng temporary output và atomic/finalized publication nếu cần tránh file xuất dở.

## 34. HTTP response streaming có rủi ro riêng

Khi service stream CSV qua HTTP:

~~~text
DB → encoder → socket
~~~

Nếu client tải rất chậm hoặc đóng browser:

- Socket write có thể block hoặc tạo buffered bytes.
- DB cursor không nên tiếp tục đọc đến hết khi response đã bị hủy.
- Phải giải phóng DB cursor, HTTP resources và worker.
- Deadline lớn cần được quản lý, tránh giữ connection hàng giờ.
- Nếu truyền response theo chunk, lỗi giữa chừng có thể khiến file phía client không hoàn chỉnh.

### Một lựa chọn khác: export bất đồng bộ

Đối với export rất lớn:

~~~text
POST /exports → 202 Accepted, exportId
Background worker → read pages → write object storage
GET /exports/{id} → status and download URL when ready
~~~

Trong **ứng dụng được triển khai**, worker là một thành phần của hệ thống. Bài này chỉ mô tả mô hình kiến trúc, không phải lời hứa rằng bài học đang tự chạy tác vụ nền.

Worker cần checkpoint, retry an toàn, TTL output, quyền truy cập file và giới hạn concurrent exports.

## 35. Streaming output và transactional snapshot

Một export kéo dài một giờ có thể gặp:

~~~text
T0: Export begins, sees record A.
T1: Other service updates B.
T2: Other service deletes C.
T3: Export eventually reaches B/C.
~~~

Nếu query đọc dữ liệu live theo nhiều pages, file không nhất thiết là snapshot tại T0.

Các contract có thể chọn:

1. **Best-effort current records:** dữ liệu theo thời điểm duyệt, không snapshot.
2. **As-of watermark:** chỉ records có immutable sequence ≤ cutoff; cần thiết kế tránh bỏ record cập nhật/deleted nếu yêu cầu ảnh chụp.
3. **Snapshot/PIT read:** dùng chức năng database tương ứng, với resource/TTL constraints.
4. **Consistent analytical snapshot:** xuất từ warehouse/lake snapshot đã materialize.

**“Duyệt hết bằng cursor” không chứng minh export chính xác cùng một thời điểm**.

## 36. Checkpoint và resume export

Một job export có thể chạy lâu, cần tiếp tục khi worker crash:

~~~json
{
  "jobId": "export-801",
  "tenantId": "T42",
  "queryHash": "v3-filter-sort",
  "lastPartition": "2026-11",
  "lastKey": "2026-11-14T09:58:00Z#tx-103",
  "completedParts": 17,
  "snapshotWatermark": "optional-consistency-token"
}
~~~

### Điểm cần giải quyết

- Checkpoint chỉ được tiến sau khi **output part được commit/durable**.
- Khi retry, không được ghi cùng records hai lần vào file cuối hoặc publish hai files cùng job nếu contract cấm.
- Có thể ghi các file parts theo ID ổn định và sau cùng compose/manifest.
- Nếu dùng driver pagingState, phải hiểu token có thể không tồn tại lâu hoặc không dùng được sau schema/session changes; keyset/bucket checkpoint có thể dễ phục hồi hơn trong một số mô hình.
- Snapshot watermark cần được giữ nhất quán nếu yêu cầu fixed dataset.

**Tiếp tục từ cursor là stateful workflow**, không chỉ lưu một string vào Redis rồi mong luôn dùng được.

## 37. Retry khi lỗi ở giữa một page

Giả sử:

~~~text
Page 1: 100 records processed and committed to output.
Page 2: 60 of 100 processed; then connection reset.
~~~

Nếu retry toàn Page 2:

- Những 60 items đầu có thể được xử lý lại.
- Nếu hành động chỉ là ghi một file tạm có thể overwrite, có thể kiểm soát được.
- Nếu mỗi item tạo side effect (send email, debit account), retry sẽ nguy hiểm.

### Những cách tiếp cận

- Cập nhật checkpoint per record hoặc batch theo một atomic boundary có thể phục hồi.
- Idempotency key theo item/event nếu có side effects.
- Output parts theo batch ID và commit marker.
- Process result trước khi advance cursor đúng quy tắc.
- Giữ stable sort/query snapshot contract.

Không suy rằng driver retry tự đảm bảo exactly-once processing. **Transport retry khác nghiệp vụ idempotency.**

## 38. Timeout và cancellation

Các loại thời gian cần tách:

| Loại | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Connect timeout | Thiết lập network connection | Không có nghĩa toàn query timeout |
| Per-request/read timeout | Một lần lấy page | Có thể có partial progress |
| Overall API deadline | Toàn HTTP request | Giới hạn thời gian client chờ |
| Job timeout | Export/scan dài | Có thể checkpoint rồi tiếp tục |
| Cursor idle timeout | Tài nguyên cursor không dùng | Backend có thể đóng cursor |

**Đừng cấu hình một timeout 30 giây rồi kỳ vọng giải quyết mọi tình huống**.

Khi client cancel:

~~~text
cancel signal
    |
    +--> stop requesting more pages
    +--> cancel outstanding tasks if supported
    +--> close cursor/stream
    +--> release output and network resources
    +--> record partial progress if job needs resume
~~~

Không giữ một database cursor mở vô hạn vì client đã rời trang nhưng background thread vẫn chạy theo vòng lặp cũ.

## 39. Connection pool và concurrency

Một service có 200 HTTP requests cùng stream một cursor:

~~~text
200 requests × 1 cursor/connection-like resource each
~~~

Tùy driver/protocol, cursor không nhất thiết giữ một TCP connection riêng suốt đời, nhưng **concurrent queries vẫn tiêu thụ pool slots, server cursors, buffers và backend capacity**.

### Các giới hạn hữu ích

- Max concurrent exports.
- Max scan/query pages in flight.
- Rate limit theo tenant.
- Timeouts và per-operation deadline.
- Bounded executor queue.
- Backpressure tới API/worker.
- Bulkhead cho hot path và batch jobs.

### Không để export làm chậm booking API

Nếu export lớn dùng chung connection pool/CPU với transaction API, p99 booking có thể tăng. Cân nhắc:

- Read replicas/analytics copy nếu consistency phù hợp.
- Worker pool riêng.
- Quota resource.
- Scheduling ban đêm khi workload phù hợp.
- Priority/admission control.

**Phân trang không sửa được contention tài nguyên nếu số jobs đồng thời không giới hạn.**

## 40. Quan sát memory và GC

Metrics/telemetry nên có:

| Nhóm | Signal |
| --- | --- |
| JVM heap | Used/committed/max heap |
| GC | Pause duration, allocation rate, collection frequency |
| Off-heap | Direct buffers/native allocations nếu đo được |
| Cursor/page | Active cursors, batch sizes, page fetch latency |
| Backpressure | Queue depth, requested vs processed items |
| Query | Rows read, bytes received, DB read capacity |
| Concurrency | In-flight queries, exports, request threads |
| HTTP | Response bytes, client cancellations |
| Recovery | Cursor errors, retries, checkpoint/resume |

### Dấu hiệu cảnh báo

- Heap tăng theo số records đã đi qua dù pageSize không đổi.
- GC pause tăng theo thời gian export.
- Queue depth chỉ tăng mà không giảm.
- Số open cursors tiếp tục tăng sau khi API kết thúc.
- Thread dump có nhiều requests chờ DB/page fetch.
- Direct memory tăng dù heap vẫn thấp.

Nếu heap cứ tăng tới khi OOM, cần tìm **đối tượng đang được giữ**, không chỉ giảm `batchSize` một cách mù quáng.

## 41. Các tình huống memory leak

Ví dụ:

~~~java
static final List<Document> DEBUG_RECORDS =
        new ArrayList<>();

void processOne(Document row) {
    DEBUG_RECORDS.add(row);
}
~~~

Ngay cả khi database cursor chỉ giữ 100 records, list static giữ mọi record đã xử lý.

Các nguồn tương tự:

- Cache không giới hạn entries.
- Logging async queue lớn.
- CompletableFuture list không được dọn.
- References giữ trong metrics/tracing attributes.
- Exceptions chứa payload lớn.
- JSON parser tree giữ toàn bộ document.
- Executor/task queue không giới hạn.

**Nguồn dữ liệu streaming không bảo vệ khỏi memory retention ở downstream.**

## 42. Java: demo keyset pagination và xử lý từng trang

Ví dụ hoàn chỉnh không phụ thuộc DBMS để hiểu cơ chế tiếp tục theo sort tuple. Trong production, database phải dùng **index seek**, thay vì quét lại toàn list như demo này.

Tạo file `KeysetPagingDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class KeysetPagingDemo {
    static final class Tx {
        final long createdAtMillis;
        final long id;
        final long amountMinor;

        Tx(long createdAtMillis, long id, long amountMinor) {
            this.createdAtMillis = createdAtMillis;
            this.id = id;
            this.amountMinor = amountMinor;
        }

        @Override
        public String toString() {
            return "Tx{id=" + id
                    + ", createdAt=" + createdAtMillis + "}";
        }
    }

    // Descending createdAt, then descending id.
    static final Comparator<Tx> ORDER =
            Comparator.comparingLong(
                    (Tx tx) -> tx.createdAtMillis)
                    .thenComparingLong(tx -> tx.id)
                    .reversed();

    static List<Tx> nextPage(
            List<Tx> ordered, Tx after, int pageSize) {
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid page size");
        }

        List<Tx> page = new ArrayList<>(pageSize);
        for (Tx tx : ordered) {
            // In descending order, items after anchor have
            // strictly greater comparator value.
            if (after != null && ORDER.compare(tx, after) <= 0) {
                continue;
            }
            page.add(tx);
            if (page.size() >= pageSize) {
                break;
            }
        }
        return page;
    }

    public static void main(String[] args) {
        List<Tx> rows = new ArrayList<>(List.of(
                new Tx(1000, 4, 200),
                new Tx(1000, 3, 300),
                new Tx( 900, 5, 500),
                new Tx( 800, 8, 800),
                new Tx( 800, 7, 700),
                new Tx( 700, 1, 100)));

        rows.sort(ORDER);

        Tx after = null;
        int pageNumber = 1;
        while (true) {
            List<Tx> page = nextPage(rows, after, 2);
            if (page.isEmpty()) {
                break;
            }
            System.out.println("Page " + pageNumber + ": " + page);
            after = page.get(page.size() - 1);
            pageNumber++;
        }
    }
}
~~~

Biên dịch/chạy với Java hỗ trợ `List.of` (Java 9+):

~~~bash
javac KeysetPagingDemo.java
java KeysetPagingDemo
~~~

Kết quả minh họa:

~~~text
Page 1: [Tx{id=4, createdAt=1000}, Tx{id=3, createdAt=1000}]
Page 2: [Tx{id=5, createdAt=900}, Tx{id=8, createdAt=800}]
Page 3: [Tx{id=7, createdAt=800}, Tx{id=1, createdAt=700}]
~~~

### Giới hạn

- Source list đã nằm trong RAM; đây là **demo logic cursor**, không minh họa memory benefit của một DB cursor thật.
- Mỗi lần `nextPage` quét từ đầu list để đơn giản hóa code. Production keyset query dùng index/key condition phù hợp.
- Dữ liệu giả lập không thay đổi; snapshot/concurrency cần contract riêng.
- API thật cần signed/opaque cursor, validation và authorization.

Điểm chính: **mỗi trang chỉ giữ một list bị chặn bởi pageSize** và cursor là sort tuple cuối, không phải offset.

## 43. Projection chỉ chọn fields cần thiết

Một trang transaction thường không cần full JSON:

~~~text
Transaction domain object:
  id, user, source, destination, notes, audit,
  metadata, attachments, full reconciliation details ...

Transaction list DTO:
  id, createdAt, amountMinor, status
~~~

Nên ưu tiên query projection:

~~~text
DB filter + sort + select required fields + bounded page
                  |
                  v
Small DTO mapping
                  |
                  v
HTTP JSON page
~~~

Không yêu cầu database trả field lớn chỉ để application bỏ đi sau khi decode. Tuy vậy, một projection nhỏ **không luôn giảm storage read cost** nếu index/engine vẫn phải đọc đầy đủ record; quan sát query plan.

## 44. Deep pagination và chi phí đếm tổng số

Nhiều giao diện hỏi:

~~~text
Page 1 of 40,781
~~~

Muốn tính exact total count có thể phải làm một query lớn, ảnh hưởng latency và read capacity. Với high-write NoSQL:

- Có thể chỉ cần “Còn nữa” thay vì exact total.
- Dùng approximate count nếu product chấp nhận.
- Dùng pre-aggregated counter theo contract nếu có.
- Trả total ở API riêng cho report.
- Không count mỗi lần user bấm Next nếu chi phí quá lớn.

**Pagination không bắt buộc biết tổng số records**.

## 45. Tenant isolation và rate limiting

Phân trang có thể trở thành công cụ quét dữ liệu nếu không kiểm soát:

~~~text
GET /transactions?tenantId=other-tenant&cursor=...
~~~

Server cần:

1. Lấy authorized tenant/user từ identity, không tin tenant do client tự yêu cầu.
2. Áp filter/key condition bắt buộc ở DB trên **mọi trang**.
3. Ký/kiểm query fingerprint trong cursor.
4. Giới hạn pageSize và max query duration.
5. Rate limit requests, concurrent cursors và exports theo tenant.
6. Không log raw cursor nếu chứa thông tin nhạy cảm.
7. Giới hạn retention của server-side cursor/job state.

Thao tác export của admin và màn hình người dùng thường cần **scope và quota khác nhau**.

## 46. Failure matrix: phân trang và streaming

| Tình huống | Rủi ro | Thiết kế cần kiểm |
| --- | --- | --- |
| DB query timeout ở page 1 | Client không có kết quả | Retry theo idempotent read/deadline |
| Timeout giữa page 20 | Lặp hoặc mất items khi resume | Stable cursor/checkpoint |
| Cursor hết hạn | Không tiếp tục được | Báo expired cursor/bắt đầu lại |
| Index/schema đổi | Token cũ không còn phù hợp | Token version/query validation |
| Duplicate records giữa pages | Sai export/counter | Unique sort key, snapshot/dedupe |
| Search result thay đổi | Page drift | PIT/snapshot nếu cần |
| Mongo cursor không close | Resource leak | Try-with-resources/cancel |
| Async producer nhanh | Queue/OOM | Backpressure, bounded concurrency |
| Client HTTP disconnect | Worker vẫn đọc DB | Propagate cancellation |
| One document quá lớn | Memory spike dù page nhỏ | Byte budget/projection |
| Dynamo filtered page rỗng | Dừng sớm | Kiểm `LastEvaluatedKey` |
| Redis SCAN trả trùng | Xử lý hai lần | Idempotency/dedupe theo mục đích |
| Export worker crash | Partial output | Checkpoint/output parts |
| Multiple exports song song | Pool saturation | Quota/bulkhead |
| Unbounded `collect(toList())` | OOM | Incremental processing |

**Một test chỉ thấy “API trang 1 trả 30 items” chưa kiểm được các lỗi này.**

## 47. Thiết kế bài kiểm thử dữ liệu đang biến động

Để hiểu semantics:

1. Gieo 100 records với `createdAt` và ID có tie-breakers.
2. Gọi trang 1 theo thứ tự giảm dần.
3. Insert record mới đứng trước trang 1.
4. Gọi trang 2 bằng offset, so kết quả.
5. Gọi trang 2 bằng keyset, so kết quả.
6. Đổi sort key của một record, quan sát duplicate/missing.
7. Xóa record ở vùng chưa duyệt.
8. Thử snapshot/PIT nếu backend hỗ trợ.

Ghi rõ **kỳ vọng** trước khi chạy. Một keyset query có thể tốt hơn offset nhưng vẫn không phản ánh snapshot T0 nếu dữ liệu live đổi.

## 48. Fault injection cho streaming và memory

Các tình huống:

- Mỗi page chậm 500 ms.
- Page 5 bị timeout.
- Network disconnect khi đã trả nửa HTTP response.
- Sink ghi file chậm gấp 100 lần producer.
- Consumer xử lý lỗi sau 1.000 records.
- Một document lớn bất thường.
- 100 concurrent exports cùng chạy.
- GC pause khi cursor còn mở.
- Client cancel ngay sau page 1.
- Redis/Mongo/Cassandra/Dynamo page token không còn hợp lệ sau thay đổi cấu hình/query.

Theo dõi:

~~~text
active cursors
heap used and allocation rate
GC pauses
queue depth and in-flight pages
DB read capacity and latency
bytes written to sink
time to first byte / total duration
retry count and checkpoint state
~~~

Không cần tiêm lỗi lên production để học; môi trường lab/staging kiểm soát và dữ liệu test là đủ.

## 49. Các anti-pattern thường gặp

| Anti-pattern | Vấn đề | Thay thế |
| --- | --- | --- |
| `findAll().subList(...)` | Tải hết trước khi phân trang | Limit/keyset tại DB |
| `skip(1_000_000)` ở endpoint hot | Offset sâu có thể tốn nhiều work | Keyset/index |
| Sort chỉ theo timestamp | Tie làm mất/trùng items | Unique tie-breaker |
| Cho cursor đổi filter tùy ý | Sai state/bảo mật | Query fingerprint |
| Base64 token không ký | Client có thể sửa | Signed/AEAD token |
| Batch size nhỏ nhưng `all.add(row)` | Heap vẫn tăng | Process incrementally |
| `collect(toList())` cho stream dài | Giữ mọi item | Streaming sink |
| Prefetch vô hạn | Memory spike | Bounded pages/concurrency |
| `request(Long.MAX_VALUE)` vô điều kiện | Không có downstream demand control | Bounded demand |
| Queue task vô hạn | OOM vì backlog | Bounded executor/queue |
| Không close cursor | Leak tài nguyên | Try-with-resources/cancel |
| Dynamo stop khi items rỗng | Mất items sau filtered page | Theo continuation token |
| Redis SCAN như snapshot | Duplicates/missing khi keyspace đổi | Dedupe/reconcile |
| Đưa cursor vendor trực tiếp ra API | Lộ state và coupling | Opaque signed application token |
| Retry write/export effect không idempotent | Duplicate side effects | Idempotency/checkpoint |
| Exact count mọi trang | Query đắt | Approx/optional count |
| Một pageSize cho mọi row sizes | OOM hoặc overhead | Đo và điều chỉnh theo workload |
| Async `Future<List<All>>` | Không bounded memory | Async paged consumption |
| Không cancel khi client đi | Query dư và leak | Propagate cancel |
| Export live nhưng hứa snapshot | Kết quả không nhất quán | Snapshot/watermark contract |

## 50. Bài tập thực hành

### Bài 1 — Phân biệt ba page sizes

API hiển thị 30 items, driver batchSize=200 và worker xử lý mỗi lần 500. Hãy giải thích ba kích thước này có nghĩa gì và khi nào cần giữ chúng khác nhau.

**Gợi ý:** API page, network fetch batch, processing batch.

### Bài 2 — Offset bị trùng

Cho list [A,B,C,D,E,F], pageSize=3. Đọc page 1 rồi insert X vào đầu, sau đó lấy page 2 bằng skip(3). Vì sao C lặp lại?

**Gợi ý:** vị trí ordinal thay đổi.

### Bài 3 — Keyset tie-breaker

Năm events có cùng `createdAt`. Nếu cursor chỉ chứa timestamp, những events nào có thể bị bỏ sót? Thiết kế khóa sort thứ hai.

**Gợi ý:** ID/sequence duy nhất.

### Bài 4 — Sort key mutable

Một record đổi `updatedAt` trong lúc user đang duyệt pages. Keyset có đảm bảo mỗi item chỉ xuất hiện đúng một lần không? Tại sao?

**Gợi ý:** cursor không phải snapshot.

### Bài 5 — Token security

Thiết kế JSON payload cho cursor theo tenant/user/filter/sort, thêm HMAC và expiry. Nêu điều Base64 đơn thuần không bảo vệ được.

**Gợi ý:** integrity, authorization binding và confidentiality.

### Bài 6 — MongoDB keyset

Viết filter cho thứ tự `createdAt DESC, _id DESC` sau cursor `(lastCreatedAt,lastId)`, áp tenant filter. Nêu compound index thích hợp.

**Gợi ý:** timestamp nhỏ hơn hoặc bằng timestamp với ID nhỏ hơn.

### Bài 7 — Mongo batch và memory

Vì sao `batchSize(100)` chưa bảo vệ heap nếu app gọi `all.add(cursor.next())` cho 10 triệu documents?

**Gợi ý:** list tăng theo tổng records.

### Bài 8 — Cassandra paging

Một query theo partition key có pageSize 200, client iterator đọc 10.000 rows. Những loại network fetch nào có thể diễn ra? Vì sao không nên gọi `ALLOW FILTERING` để sửa query thiếu key?

**Gợi ý:** driver fetch pages, partition design quan trọng.

### Bài 9 — Cassandra async

`processOrder` khởi động async HTTP calls rồi return ngay. Tại sao `fetchNextPage` sau vòng lặp có thể tạo unbounded in-flight work? Thiết kế một bound.

**Gợi ý:** đợi futures theo batch hoặc semaphore concurrency.

### Bài 10 — Dynamo filtered page rỗng

Một `QueryResponse` có `items=[]` nhưng `lastEvaluatedKey` không rỗng. Có nên kết thúc không? Vì sao?

**Gợi ý:** filter sau đọc.

### Bài 11 — Dynamo Query vs Scan

Bạn muốn đọc lịch sử của một user. Tại sao thiết kế `userId` làm key condition thường tốt hơn quét toàn bảng rồi filter `userId`?

**Gợi ý:** consumed capacity và partition key.

### Bài 12 — Redis SCAN

Một SCAN trả 0 keys và cursor=423. Đây là kết thúc chưa? Có được đảm bảo không lặp keys khi keyspace biến động không?

**Gợi ý:** cursor=0 mới đánh dấu kết thúc theo protocol.

### Bài 13 — Memory math

Cho C=12 concurrent requests, P=2 prefetched pages, B=400 items/page, S=3.500 bytes/item. Tính `C×P×B×S` và nêu ba khoản memory ngoài mô hình.

**Gợi ý:** 33.600.000 bytes dữ liệu, chưa gồm buffers/GC/DTO.

### Bài 14 — Page size trade-off

So page sizes 10, 200 và 5.000 với RTT 50 ms, row size trung bình 4 KiB. Nêu giả thuyết về latency/heap và các metrics cần đo.

**Gợi ý:** network round trips đối lập allocation/GC.

### Bài 15 — Projection

Một document 50 KiB nhưng trang danh sách chỉ cần 200 bytes. Bạn sẽ yêu cầu fields nào ở DB, và vì sao projection không chắc chắn làm storage read rẻ tương ứng 250 lần?

**Gợi ý:** index covering/engine read path.

### Bài 16 — Java Stream

`List<AllRows>.stream().limit(30)` có đảm bảo query chỉ đọc 30 rows không? Tại sao?

**Gợi ý:** list có thể đã materialize.

### Bài 17 — Backpressure

Producer 10.000 items/s, consumer 1.000 items/s. Nếu chạy 60 giây không backpressure, hàng đợi có thể tăng thêm bao nhiêu records?

**Gợi ý:** 540.000 records.

### Bài 18 — Reactive request

Giải thích tác dụng `subscription.request(1)` và vì sao `request(Long.MAX_VALUE)` có thể phá giới hạn memory ở downstream.

**Gợi ý:** demand và buffering.

### Bài 19 — Async không streaming

Một function trả `CompletableFuture<List<Row>>` gồm 2 triệu records. Vì sao nó có thể không block caller nhưng vẫn OOM?

**Gợi ý:** asynchronous scheduling khác bounded memory.

### Bài 20 — Bounded queue

Thiết kế reader→`ArrayBlockingQueue(256)`→writer với cancellation, end-of-stream và error propagation. Nếu writer crash, reader nên làm gì?

**Gợi ý:** ngừng fetch, đóng cursor, không chờ put vô hạn.

### Bài 21 — Export CSV

Vì sao không nên tạo một `StringBuilder` chứa 10 GB CSV? Thiết kế pipeline page reader→encoder→sink có bounded memory và file finalization.

**Gợi ý:** buffered writer, temporary output, checksum/manifest.

### Bài 22 — CSV security

Một field description do người dùng nhập có nội dung giống spreadsheet formula. Khi xuất file để mở bằng spreadsheet, cần cân nhắc rủi ro nào ngoài CSV escaping?

**Gợi ý:** formula injection.

### Bài 23 — Client disconnect

Client hủy tải CSV sau 10 giây nhưng service vẫn đọc database trong 20 phút. Hệ thiếu những cơ chế nào?

**Gợi ý:** cancellation propagation, cursor close, deadline.

### Bài 24 — Consistent export

Một export qua 50 pages kéo dài một giờ, trong lúc đó có insert/update/delete. Có thể hứa dữ liệu đúng snapshot T0 không nếu chỉ dùng keyset?

**Gợi ý:** cần snapshot/watermark contract.

### Bài 25 — Checkpoint

Worker đã ghi 60/100 records của page 20 rồi crash. Khi resume toàn page, các records nào có thể bị lặp? Thiết kế checkpoint/output parts để tránh.

**Gợi ý:** commit checkpoint sau durable output và idempotency.

### Bài 26 — Concurrency

100 exports cùng chạy với pageSize 500, mỗi item heap 8 KiB. Tính nguy cơ memory nếu mỗi export prefetch ba pages và đề xuất concurrency limit.

**Gợi ý:** `100×3×500×8192` bytes, chưa gồm buffers.

### Bài 27 — Connection pool

Database driver pool bị hết connections khi nhiều export dài chạy cùng API booking. Nêu ba cách cách ly batch workload.

**Gợi ý:** separate worker pool, quotas, read replica.

### Bài 28 — Heap leak

Cursor `batchSize(100)` nhưng heap tăng từ 100 MiB lên 2 GiB. Tìm ít nhất năm nơi có thể giữ references ngoài driver.

**Gợi ý:** static list, cache, futures, queues, JSON trees, logs.

### Bài 29 — Exact count

Product yêu cầu “trang 1 trên 123.456” cho search với hàng triệu documents cập nhật liên tục. Phân tích chi phí exact count và thiết kế UX không cần exact total trên mọi request.

**Gợi ý:** `nextCursor` và “Load more”.

### Bài 30 — End-to-end API

Thiết kế `GET /users/me/transactions?pageSize=30&cursor=...` với:

1. Filter theo user/tenant từ authentication.
2. Stable sort tuple và compound index.
3. Opaque signed cursor.
4. Bounded pageSize và per-query deadline.
5. Response `items`/`nextCursor`.
6. Xử lý duplicate/missing khi dữ liệu live thay đổi.
7. Retry và expired cursor policy.
8. Memory/concurrency metrics.

**Gợi ý:** tách rõ pagination contract, consistency contract và security contract.

### Bài 31 — So sánh bốn backend

Với MongoDB, Cassandra, DynamoDB và Redis, hãy điền: cách tiếp tục trang, điều kiện kết thúc, có snapshot hay không, cách chọn query/key và rủi ro duplication.

**Gợi ý:** cursor/seek, paging state, LastEvaluatedKey, SCAN cursor có semantics khác nhau.

### Bài 32 — Java demo

Chạy `KeysetPagingDemo`, thêm hai events có cùng createdAt, kiểm tie-breaker. Sau đó mô phỏng thêm record mới trước cursor để quan sát keyset khác offset.

**Gợi ý:** order comparator và last item tuple.

## 51. Checklist triển khai

Trước khi đưa API phân trang/streaming lên môi trường thật:

1. Query có dùng đúng partition key/index cho access pattern không?
2. Có đẩy filter/sort/limit/projection xuống DB không?
3. API dùng offset hay keyset/opaque cursor vì lý do gì?
4. Sort có unique tie-breaker và sort key ổn định không?
5. Token có gắn filter, tenant, query version, expiry không?
6. Cursor token có integrity/authorization validation không?
7. Một page chứa tối đa bao nhiêu items và bao nhiêu bytes?
8. Driver fetch size, API page size và processing batch size được phân biệt chưa?
9. Truy vấn dài có thể giữ cursor/connection bao lâu?
10. Đã có try-with-resources và cancellation trên mọi đường lỗi chưa?
11. Có collection/queue nào tích lũy toàn bộ kết quả không?
12. Concurrent pages, prefetch và async work có giới hạn không?
13. Sink chậm có truyền backpressure về source không?
14. Retry sau page failure có làm lặp side effect không?
15. Snapshot vs live traversal được mô tả rõ chưa?
16. Dynamo `LastEvaluatedKey` và Redis SCAN cursor có được xử lý đúng semantics không?
17. Export có checkpoint/output finalization nếu cần không?
18. Có metrics heap, GC, cursor, query latency, pages in flight, queue depth không?
19. Đã thử row lớn, deep pagination, 100 concurrent clients, network timeout, client cancel chưa?
20. Đã có quota và tenant isolation để tránh data scan trái phép chưa?

**Nếu API chỉ có `pageSize` nhưng còn `findAll()` hoặc `collect(toList())` phía dưới, kiến trúc vẫn chưa kiểm soát bộ nhớ.**

## 52. Tổng kết

1. **Phân trang phải diễn ra ở nơi truy vấn**: DB filter, sort, limit, cursor hoặc keyset; không tải tất cả về Java rồi mới cắt list.
2. **Offset đơn giản nhưng deep offset đắt và dễ drift** khi dữ liệu biến động. Keyset thường phù hợp timeline/feed lớn nếu có index và unique stable sort tuple.
3. **Continuation tokens là contract theo backend**, không phải một chuỗi có thể tái sử dụng cho mọi query. MongoDB cursor/seek, Cassandra paging state, DynamoDB LastEvaluatedKey, Redis SCAN và search_after có semantics khác nhau.
4. **Cursor không tự tạo snapshot**. Nếu cần export đúng một thời điểm, phải có snapshot/PIT, watermark hoặc chiến lược dữ liệu immutable/reconciliation phù hợp.
5. **Streaming thực sự đòi tiêu thụ dần và không tích lũy**. Một Java Stream hoặc async Future vẫn có thể giữ hàng triệu objects.
6. **Page size chỉ là một phần của memory budget**; concurrency, prefetch, row size, driver buffers, JSON decode và queues cũng quyết định peak heap.
7. **Backpressure phải truyền từ consumer tới source**. Bounded queue, giới hạn in-flight và demand-based fetching ngăn producer làm đầy RAM khi sink chậm.
8. **Đóng tài nguyên và hỗ trợ cancellation**: cursor, network operations, HTTP streams và export jobs không được sống mãi sau timeout hoặc client disconnect.
9. **Retry cần semantics phù hợp**. Page replay có thể dẫn tới duplicate processing; business side effects cần idempotency/checkpoints.
10. **Đo đạc trước khi tối ưu**: p95/p99, allocation/GC, page fetch latency, byte size, queue depth, active cursors và concurrency.

**Nguyên tắc thực hành:** khi một API Java phải đọc nhiều dữ liệu NoSQL, hãy trả lời đồng thời ba câu hỏi: **“trang tiếp theo được xác định chính xác bằng gì?”, “tối đa bao nhiêu bytes/objects đang được giữ đồng thời?”, và “khi reader, downstream hay client dừng giữa chừng thì cursor, memory và kết quả được xử lý ra sao?”**. Nếu ba câu hỏi có hợp đồng và giới hạn kiểm chứng được, API mới thật sự phân trang tốt, stream an toàn và kiểm soát bộ nhớ trong môi trường production.
