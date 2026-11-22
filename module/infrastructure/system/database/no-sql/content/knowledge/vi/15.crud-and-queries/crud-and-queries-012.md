# Đọc dạng luồng, giới hạn bộ nhớ và đóng tài nguyên

## 1. Bài toán mở đầu: truy vấn đúng nhưng ứng dụng hết bộ nhớ

Giả sử hệ thống lưu 20 triệu sự kiện thiết bị trong một database NoSQL. Nhóm vận hành cần xuất lịch sử của một thiết bị ra file để điều tra sự cố. Một cách viết rất dễ gặp:

~~~java
List<Document> all = new ArrayList<>();

for (Document doc : collection.find(filter)) {
    all.add(doc);
}

writeCsv(all);
~~~

Đoạn mã có thể hoạt động với 500 bản ghi thử nghiệm. Nhưng khi kết quả thực tế có vài triệu bản ghi, toàn bộ dữ liệu dồn vào heap Java, kéo theo cấp phát object, garbage collection kéo dài và nguy cơ **OutOfMemoryError**. Ngay cả khi database đã gửi kết quả qua mạng theo từng batch, việc ứng dụng tự thêm hết vào List vẫn khiến bộ nhớ tăng theo tổng số bản ghi.

Một hướng tốt hơn là **đọc dần và xử lý dần**:

~~~text
NoSQL database
    -> nhận một phần kết quả
    -> xử lý hoặc ghi ra output
    -> giải phóng phần đã xử lý
    -> lấy phần tiếp theo
    -> đóng cursor/kết nối khi kết thúc
~~~

Tuy nhiên, không phải cứ đổi List thành Stream là an toàn. Nếu tầng xử lý phía sau chậm, vẫn có thể tích lũy hàng triệu object trong queue. Nếu cursor không được đóng, hệ thống có thể giữ tài nguyên mạng, bộ nhớ và trạng thái truy vấn ở server. Nếu request bị hủy nhưng worker vẫn chạy, thao tác đọc tiếp tục tiêu thụ tài nguyên vô ích.

**Mục tiêu của bài:** thiết kế một đường đọc dữ liệu NoSQL có mức sử dụng bộ nhớ được kiểm soát, biết giới hạn lượng dữ liệu đang bay giữa các tầng, đóng tài nguyên trong mọi tình huống và khôi phục có kiểm soát khi truy vấn dài bị gián đoạn.

## 2. Đọc dạng luồng nghĩa là gì?

Trong ngữ cảnh truy vấn, **đọc dạng luồng (streaming read)** là cách ứng dụng tiêu thụ kết quả **từng phần trong khi kết quả còn đang được tạo hoặc tải**, thay vì đợi tất cả bản ghi nằm trong bộ nhớ rồi mới xử lý.

Ví dụ:

~~~text
Không có streaming ở application:

DB --[page1, page2, page3, ...]--> List chứa mọi bản ghi
                                     |
                                     v
                                   xử lý

Có streaming ở application:

DB --> batch nhỏ --> xử lý --> output
       batch nhỏ --> xử lý --> output
       batch nhỏ --> xử lý --> output
~~~

**Tính chất quan trọng:** số bản ghi đang được giữ trong memory nên phụ thuộc vào kích thước batch và các buffer có giới hạn, **không phụ thuộc trực tiếp vào tổng số bản ghi của toàn bộ kết quả**.

### 2.1. Streaming không đồng nghĩa với dữ liệu thời gian thực

Cần phân biệt:

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Streaming query results** | Đọc dần kết quả của một truy vấn | Xuất 2 triệu đơn hàng qua cursor |
| **Pagination** | Chia kết quả thành từng trang có điểm tiếp tục | Query trả 100 item mỗi lần |
| **Database cursor** | Trạng thái/đối tượng để tiếp tục duyệt kết quả | MongoDB cursor |
| **Change stream / CDC** | Nghe thay đổi phát sinh sau thời điểm đăng ký | MongoDB change stream, DynamoDB Streams |
| **Event streaming** | Luồng sự kiện được phát liên tục qua broker | Kafka consumer xử lý order events |
| **HTTP response streaming** | Gửi dần kết quả cho client | NDJSON hoặc server-side streaming |

Có thể kết hợp nhiều loại: ứng dụng dùng cursor đọc dữ liệu lịch sử rồi stream thành NDJSON qua HTTP. Nhưng một cursor truy vấn hữu hạn **không phải** change stream, và API nhận từng page **không tự bảo đảm** bộ nhớ hữu hạn nếu client gom mọi page vào List.

### 2.2. Pull và push

Hai mô hình tiêu thụ phổ biến:

- **Pull:** consumer chủ động yêu cầu phần tử/page tiếp theo khi sẵn sàng. Ví dụ iterator qua MongoCursor hoặc lặp từng page từ DynamoDB.
- **Push:** publisher đẩy dữ liệu tới consumer. Cần một cơ chế kiểm soát tốc độ để producer không vượt khả năng xử lý của consumer.

Trong reactive streams, **backpressure** là cơ chế consumer thông báo lượng dữ liệu sẵn sàng nhận, thường qua yêu cầu demand. Nhưng không phải mọi driver, wrapper hay operator đều truyền demand xuyên suốt tới database theo cùng cách; phải hiểu nơi nào có buffer và nơi nào dữ liệu được prefetch.

## 3. Những dạng API thường xuất hiện trong NoSQL

| Hệ / kiểu truy vấn | Hình thức thường dùng | Lưu ý |
| --- | --- | --- |
| MongoDB synchronous Java driver | FindIterable và MongoCursor | Cursor cần close; batch được lấy khi lặp |
| MongoDB reactive driver | Publisher | Subscription/cancellation và backpressure theo API |
| Cassandra Java driver | ResultSet với paging hoặc AsyncResultSet | Page size khác tổng số hàng; session có vòng đời riêng |
| DynamoDB | Query/Scan với LastEvaluatedKey hoặc paginator | Mỗi request trả trang; muốn tiếp tục cần token |
| Redis | SCAN/HSCAN/SSCAN/ZSCAN | Cursor quét dần key/element; có thể lặp hoặc thiếu nếu tập thay đổi |
| Elasticsearch/OpenSearch | Search-after/PIT, scroll trong một số use case | Phân trang sâu cần hiểu snapshot và lifecycle |

Không có một interface “stream” chung cho tất cả NoSQL. Điều cần thống nhất ở **tầng ứng dụng** là: lấy từng phần, không tích lũy vô hạn, giới hạn số lượng dữ liệu xử lý, theo dõi hủy/lỗi và quản lý tài nguyên của driver đúng cách.

## 4. Ba giới hạn khác nhau: tổng số bản ghi, kích thước page và bộ nhớ

Một truy vấn có thể có các thuộc tính:

~~~text
Query limit     = tối đa 10.000 records cho yêu cầu
Fetch/page size = gợi ý hoặc giới hạn khoảng 200 records mỗi lần lấy
Buffer capacity = tối đa 300 records đang chờ xử lý
~~~

Chúng giải quyết ba vấn đề:

1. **Total query limit:** bao nhiêu kết quả được phép trả hoặc xử lý cho một yêu cầu.
2. **Page/fetch size:** mỗi lượt truyền dữ liệu/đọc từ driver có bao nhiêu phần tử hoặc bytes, tùy engine.
3. **Buffer limit:** ứng dụng được phép giữ bao nhiêu object đang chờ ở các tầng.

**Page size không thay thế total limit.** Đặt batchSize = 200 không ngăn vòng lặp đọc 2 triệu document. Ngược lại, đặt limit = 1000 không bảo đảm bộ nhớ thấp nếu mỗi document chứa một trường payload hàng chục MB hoặc ứng dụng tạo nhiều bản sao dữ liệu.

### 4.1. Tại sao batch nhỏ chưa chắc đủ?

~~~java
List<Document> all = new ArrayList<>();

try (MongoCursor<Document> cursor = collection.find(filter)
        .batchSize(100)
        .iterator()) {
    while (cursor.hasNext()) {
        all.add(cursor.next()); // Vẫn giữ toàn bộ kết quả.
    }
}
~~~

Cursor được đóng đúng, batch chỉ lấy từng phần, nhưng List vẫn lớn theo tổng kết quả. Vấn đề **bộ nhớ application** chưa được giải quyết.

### 4.2. Tại sao buffer nhỏ chưa chắc đủ?

Giả sử producer lấy 200 record mỗi lượt và đưa vào một bounded queue chứa tối đa 300 record. Nhưng consumer lại ghi chúng vào một List toàn cục để “xử lý sau”. Queue có giới hạn không giúp gì vì **bộ nhớ được giữ ở tầng sau**.

Hãy nhìn xuyên suốt chuỗi:

~~~mermaid
flowchart LR
    D[("Database")] --> B["Driver batch"]
    B --> Q["Worker queue"]
    Q --> T["Transform / DTO"]
    T --> O["Output buffer"]
    O --> X["File, API, downstream"]
~~~

Mỗi mũi tên và mỗi node có thể cấp phát bộ nhớ. Cần biết **mức dữ liệu giữ đồng thời** của từng tầng, không chỉ kích thước batch được cấu hình trên driver.

## 5. Ước lượng ngân sách bộ nhớ

Giả sử trung bình một record sau deserialize có kích thước **s** byte. Gọi:

- **P:** số record tối đa trong batch/prefetch của driver.
- **Q:** số record tối đa trong queue xử lý.
- **B:** số record tối đa trong output batch.
- **W:** số worker và lượng record mỗi worker giữ đồng thời.
- **M_other:** bộ nhớ cho runtime, kết nối, index của ứng dụng, caches và object khác.

Một ước lượng sơ bộ:

\[
M_{\text{records}}\approx (P+Q+B+W)\times s
\]

và:

\[
M_{\text{total}}\approx M_{\text{records}}+M_{\text{other}}
\]

Ví dụ minh họa:

~~~text
P = 200
Q = 300
B = 100
W = 20
s = 12 KiB / record

Tạm tính phần data đang giữ:
  (200 + 300 + 100 + 20) * 12 KiB
  = 7.440 KiB, khoảng 7,3 MiB
~~~

Đây **không phải mức sử dụng heap thực tế**. Java Document, String, collection lồng nhau, các buffer BSON/JSON, encoding, TLS/network buffer và đối tượng trung gian có overhead riêng. Kích thước **s** phải được đo trên dữ liệu thật, đặc biệt là p95/p99, không chỉ từ số byte JSON thô.

### 5.1. Sự chênh lệch kích thước bản ghi

Hai document:

~~~json
{"id":"A1","status":"OK"}
~~~

~~~json
{
  "id": "A2",
  "payload": "...vài MB text/blob...",
  "nested": {
    "history": ["...rất nhiều entries..."]
  }
}
~~~

đều được tính là **một document**. Nếu batchSize = 200, số lượng object có giới hạn nhưng lượng bytes có thể rất khác nhau.

Với dữ liệu có document lớn, nên dùng **projection** chỉ lấy trường cần thiết, tách blob ra object storage nếu phù hợp, hoặc đặt giới hạn/kiểm tra kích thước payload ở nguồn.

### 5.2. Giới hạn số request chạy song song

Một request có peak memory 8 MiB có thể chấp nhận được. Nhưng **100 request đồng thời** có thể tạo áp lực rất lớn:

\[
M_{\text{concurrent}}\approx C\times M_{\text{per-query}}
\]

với **C** là số truy vấn đồng thời. Ngoài heap, các request còn giữ connection, socket, cursor server-side và tài nguyên database. Do đó thường cần **admission control**, giới hạn số tác vụ xuất dữ liệu chạy đồng thời và quota theo tenant/người dùng.

## 6. Giảm lượng dữ liệu trước khi truyền về ứng dụng

Lựa chọn tốt nhất thường là **không đọc dữ liệu không cần thiết**.

### 6.1. Filter tại database

Thay vì quét mọi event rồi lọc trong Java:

~~~text
Scan mọi tenant -> Java lọc tenant T01 -> xử lý
~~~

hãy dùng partition/primary key, index hoặc query có điều kiện phù hợp:

~~~text
Query tenant=T01, device=D17, time in range -> xử lý
~~~

Một truy vấn có điều kiện không phù hợp index vẫn có thể phải scan nhiều dữ liệu trên server; đừng kết luận chỉ vì có WHERE thì đã tối ưu.

### 6.2. Projection

Nếu chỉ xuất:

~~~text
eventId, eventTime, status
~~~

đừng lấy thêm:

~~~text
fullPayload, image, rawSensorDump, auditTrail
~~~

Projection thường giảm số bytes truyền và số object phải cấp phát. Nhưng nếu query cần sort theo một trường, phải giữ điều kiện khóa/index để engine thực hiện truy vấn đúng.

### 6.3. Sort và pagination phải phù hợp khóa

Một sort không được index hỗ trợ có thể khiến database hoặc ứng dụng phải giữ nhiều dữ liệu trước khi trả kết quả. Với truy vấn lớn, cần thiết kế **thứ tự rõ ràng và đường truy cập phù hợp**, ví dụ:

~~~text
partition/group: (tenantId, deviceId)
order: (eventTime DESC, eventId DESC)
~~~

Lúc này ứng dụng có thể lấy theo dải thời gian và dùng cursor để tiếp tục thay vì sort một List khổng lồ trong JVM.

## 7. Java và MongoDB: đọc bằng MongoCursor

MongoDB synchronous Java driver cung cấp **FindIterable** và **MongoCursor**. Ví dụ giả định đã có MongoCollection<Document> được quản lý bởi tầng repository:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Projections.include;
import static com.mongodb.client.model.Sorts.descending;

public void exportEvents(
        MongoCollection<Document> collection,
        String tenantId,
        java.util.function.Consumer<Document> sink) {

    try (MongoCursor<Document> cursor = collection
            .find(eq("tenantId", tenantId))
            .projection(include("eventId", "eventTime", "status"))
            .sort(descending("eventTime", "eventId"))
            .batchSize(200)
            .iterator()) {

        while (cursor.hasNext()) {
            Document document = cursor.next();
            sink.accept(document);
        }
    }
}
~~~

Ý nghĩa:

1. Driver đưa về từng batch để iterator có thể duyệt dần.
2. Projection giảm dữ liệu được chuyển về.
3. Sort chỉ nên dùng khi có index phù hợp với truy vấn thực tế.
4. Consumer xử lý từng document thay vì thêm hết vào List.
5. **try-with-resources** gọi close khi kết thúc bình thường **hoặc khi có exception** trong khối.

Đây là ví dụ thao tác đồng bộ, có thể **block thread** khi lấy batch mới hoặc khi sink xử lý. Không gọi trực tiếp đoạn mã blocking này trên event-loop của một ứng dụng reactive.

### 7.1. Cẩn thận: sink cũng có thể tích lũy vô hạn

Trong ví dụ:

~~~java
sink.accept(document);
~~~

sink phải xử lý có giới hạn, ví dụ ghi từng dòng ra BufferedWriter hoặc đẩy vào queue bounded. Nếu sink tự làm:

~~~java
List<Document> all = new ArrayList<>();
exportEvents(collection, "T01", all::add);
~~~

thì cách đọc vẫn không giới hạn bộ nhớ. **Streaming phải kéo dài tới nơi nhận cuối cùng**, hoặc có giới hạn rõ ràng ở từng buffer.

### 7.2. Giới hạn toàn bộ kết quả

Nếu endpoint chỉ cho phép xuất tối đa 10.000 document:

~~~java
try (MongoCursor<Document> cursor = collection
        .find(eq("tenantId", "T01"))
        .projection(include("eventId", "eventTime", "status"))
        .limit(10_000)
        .batchSize(200)
        .iterator()) {

    while (cursor.hasNext()) {
        process(cursor.next());
    }
}
~~~

**limit(10_000)** giới hạn lượng kết quả của truy vấn; **batchSize(200)** ảnh hưởng cách driver lấy từng phần. Không nên xem batchSize là giới hạn tổng, hoặc limit là bảo đảm heap nhỏ nếu process tiếp tục giữ mọi object.

### 7.3. Đóng cursor khi client ngắt kết nối

Một HTTP export có thể bị user hủy sau 500 dòng. Nếu code vẫn tiếp tục đọc cho hết 10 triệu dòng, tài nguyên bị lãng phí.

Ứng dụng cần gắn việc hủy request với vòng đời producer:

~~~text
HTTP client disconnect
    -> hủy công việc đang xuất
    -> dừng vòng lặp đọc
    -> close MongoCursor
    -> đóng/flush output nếu còn hợp lệ
~~~

try-with-resources giúp **close khi control rời khối**, nhưng không tự biết client đã ngắt nếu vòng lặp không có cách nhận tín hiệu cancel. Cần tích hợp cancellation/interrupt theo framework và cơ chế I/O.

### 7.4. Không dùng noCursorTimeout như giải pháp mặc định

Cursor lâu có thể bị timeout vì inactivity hoặc chính sách session/server. Bật tùy chọn tránh cursor timeout có thể khiến cursor bị bỏ quên tồn tại lâu hơn, tăng áp lực tài nguyên. Không nên dùng nó để chữa một job quá chậm hoặc thiếu đóng tài nguyên.

Ưu tiên: truy vấn có giới hạn, cursor được đóng, xử lý đủ nhanh hoặc dùng checkpoint để mở lại truy vấn. Nếu bắt buộc chạy lâu, phải hiểu **cursor timeout, session timeout, network timeout và driver lifecycle** của phiên bản MongoDB đang dùng.

## 8. DynamoDB: đọc theo trang với Query và paginator

DynamoDB Query yêu cầu một **giá trị partition key** phù hợp, có thể kèm sort-key condition. Một Query không tự động trả mọi item trong một response. API trả theo trang và cung cấp **LastEvaluatedKey** nếu còn điểm tiếp tục.

Ví dụ Java AWS SDK v2:

~~~java
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.QueryResponse;

import java.util.Map;

public void readDeviceEvents(DynamoDbClient client) {
    QueryRequest request = QueryRequest.builder()
        .tableName("DeviceEvents")
        .keyConditionExpression("PK = :pk")
        .expressionAttributeValues(Map.of(
            ":pk",
            AttributeValue.builder()
                .s("TENANT#T01#DEVICE#D17")
                .build()
        ))
        .limit(200)
        .build();

    for (QueryResponse page : client.queryPaginator(request)) {
        for (Map<String, AttributeValue> item : page.items()) {
            processItem(item);
        }
    }
}
~~~

Hàm **processItem** đại diện một bộ xử lý không tích lũy vô hạn. Để hoạt động an toàn, các output buffer phía sau cũng cần giới hạn.

Điểm cần lưu ý:

- Paginator tự gọi các trang tiếp theo khi được duyệt, nhưng nó **không tạo giới hạn tổng kết quả**.
- **limit(200)** trong Query xác định số item tối đa được DynamoDB đánh giá cho một request/page theo semantics của API, không phải cam kết luôn trả đúng 200 item.
- Query có giới hạn dữ liệu theo trang của dịch vụ; một page có thể kết thúc vì giới hạn bytes trước khi đạt limit.
- **FilterExpression** được áp dụng sau khi đọc item theo key condition; page có thể trả ít item, thậm chí rỗng, dù vẫn còn LastEvaluatedKey.
- Nên ưu tiên Query trên key/index phù hợp hơn Scan toàn bộ bảng khi workload cho phép.

### 8.1. Điều kiện dừng đúng với LastEvaluatedKey

Nếu viết vòng lặp thủ công:

~~~java
Map<String, AttributeValue> exclusiveStartKey = null;

do {
    QueryRequest.Builder builder = QueryRequest.builder()
        .tableName("DeviceEvents")
        .keyConditionExpression("PK = :pk")
        .expressionAttributeValues(Map.of(
            ":pk",
            AttributeValue.builder()
                .s("TENANT#T01#DEVICE#D17")
                .build()
        ))
        .limit(200);

    if (exclusiveStartKey != null && !exclusiveStartKey.isEmpty()) {
        builder.exclusiveStartKey(exclusiveStartKey);
    }

    QueryResponse response = client.query(builder.build());

    for (Map<String, AttributeValue> item : response.items()) {
        processItem(item);
    }

    exclusiveStartKey = response.lastEvaluatedKey();
} while (exclusiveStartKey != null && !exclusiveStartKey.isEmpty());
~~~

Không được dừng chỉ vì **response.items() rỗng**, nhất là khi có filter, nếu API vẫn trả continuation key. Không nên kết luận “đã đọc xong” dựa vào số item nhận được thấp hơn page size.

### 8.2. Ghi cursor cho request kế tiếp

Nếu API phục vụ người dùng với từng trang:

~~~text
GET /events?deviceId=D17&pageSize=50&cursor=...
~~~

Server có thể lưu/mã hóa **LastEvaluatedKey** và trả continuation token. Token phải ràng buộc với tenant, điều kiện truy vấn, index và page semantics. Nên ký hoặc bảo vệ token trước khi đưa ra client, tránh để người dùng tự sửa khóa tiếp tục sang dữ liệu tenant khác.

Không nên giữ một vòng lặp paginator chạy mãi trong server chỉ để chờ user bấm “Next”; mỗi request nên đọc phần cần thiết rồi kết thúc theo mô hình API.

### 8.3. Vòng đời DynamoDbClient

**DynamoDbClient** là client có tài nguyên kết nối, thường được tạo và quản lý **dùng chung trong vòng đời ứng dụng**. Không tạo và đóng một client mới cho từng record hoặc từng page. Đóng client ở shutdown hoặc theo lifecycle của dependency injection container.

Trái với cursor MongoDB, một QueryResponse bình thường không phải một resource server-side mà ứng dụng cần gọi close sau mỗi page. Nhưng các kết nối HTTP, thread pools và async client vẫn thuộc lifecycle của SDK client.

## 9. Cassandra: page size và ResultSet

Cassandra Java driver hỗ trợ paging để truy vấn không cần nhận toàn bộ kết quả cùng một lúc. Ví dụ dựa trên DataStax Java Driver 4 API:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public void readHistory(CqlSession session) {
    SimpleStatement statement = SimpleStatement.builder(
        "SELECT event_id, event_time, status " +
        "FROM events_by_device " +
        "WHERE tenant_id = ? AND device_id = ?")
        .addPositionalValues("T01", "D17")
        .setPageSize(200)
        .build();

    ResultSet rows = session.execute(statement);
    for (Row row : rows) {
        processRow(row);
    }
}
~~~

Giả định bảng có primary key cho phép Query theo tenant_id và device_id; thiết kế thật phải đối chiếu partition key/clustering key. **setPageSize(200)** điều chỉnh kích thước page mong muốn, không có nghĩa toàn truy vấn chỉ trả tối đa 200 hàng. Một iterator của ResultSet có thể **block khi cần fetch trang mới**.

### 9.1. ResultSet và CqlSession có vòng đời khác nhau

Ở Java Driver 4, ResultSet thông thường không được dùng như một MongoCursor phải đóng thủ công ở cuối vòng lặp. **CqlSession** mới là thành phần giữ pool/kết nối và cần được đóng theo vòng đời ứng dụng.

Không đưa CqlSession vào try-with-resources **bên trong mỗi request** nếu nó là session dùng chung do container quản lý. Nếu ứng dụng tự tạo một session ngắn hạn cho một job độc lập, phải đóng nó khi job hoàn thành; trách nhiệm sở hữu tài nguyên phụ thuộc cách ứng dụng khởi tạo.

### 9.2. Paging bất đồng bộ

Driver còn có AsyncResultSet để xử lý page bất đồng bộ. Logic khái niệm:

~~~text
executeAsync(statement)
    -> nhận currentPage
    -> xử lý từng row trong page
    -> nếu hasMorePages và consumer còn sẵn sàng:
           fetchNextPage()
    -> nếu không: kết thúc
~~~

Không nên gọi fetchNextPage vô hạn ngay khi trang trước chưa được xử lý, vì như vậy lại tạo prefetch/buffer không giới hạn trong ứng dụng. Cần điều phối completion, giới hạn số page đang bay, xử lý timeout và cancellation.

### 9.3. Chia query theo khóa

Một query có hàng triệu record trong cùng một partition có thể gây áp lực lớn lên Cassandra. Streaming chỉ giới hạn bộ nhớ phía client; nó **không sửa được** partition quá lớn, truy vấn không phù hợp khóa, tombstone nhiều hoặc độ trễ server-side.

Khi thiết kế lịch sử, có thể cần bucket theo ngày/giờ, query trong một partition và tiếp tục bucket tiếp theo. Khi làm vậy, phải quản lý cursor/boundary ở application vì paging state của một query không tự nhiên nhảy sang partition của ngày khác.

## 10. Redis: SCAN thay vì quét tất cả key bằng KEYS

Đọc từng phần trong Redis có khác biệt quan trọng giữa:

~~~redis
KEYS event:*
~~~

và:

~~~redis
SCAN 0 MATCH event:* COUNT 200
~~~

Lệnh **KEYS** có thể duyệt toàn keyspace theo cách gây ảnh hưởng lớn tới latency khi số key rất nhiều. **SCAN** là giao thức duyệt từng bước bằng cursor, thường phù hợp hơn cho công việc kiểm kê/dọn dẹp không cần snapshot tức thời.

### 10.1. Cursor của SCAN

Một vòng lặp khái niệm:

~~~text
cursor = "0"

do:
    response = SCAN cursor MATCH "event:*" COUNT 200
    cursor = response.nextCursor
    for each key in response.keys:
        process key
while cursor != "0"
~~~

Những điều cần hiểu:

- **COUNT** là hint về khối lượng công việc, không bảo đảm mỗi lượt trả chính xác 200 key.
- Một lượt SCAN có thể trả **0 key** nhưng cursor vẫn chưa kết thúc.
- Một key có thể được trả lặp; consumer phải chịu được duplicate.
- Tập key thay đổi trong lúc quét không tạo một snapshot nhất quán; có thể có phần tử được thêm/xóa khiến kết quả tùy thời điểm.
- Không lấy cursor SCAN làm một ID vĩnh viễn hoặc cơ chế phân trang người dùng có bảo đảm snapshot.

### 10.2. SCAN không tự tiết kiệm tất cả tài nguyên

Nếu một job dùng SCAN để lấy 100.000 key rồi đưa vào ArrayList, heap vẫn tăng. Nếu mỗi lần SCAN lại dùng MGET tất cả key với payload rất lớn mà không giới hạn, network buffer và heap vẫn có thể phình.

Thiết kế nên giới hạn:

~~~text
SCAN cursor
    -> một nhóm key nhỏ
    -> đọc value cần thiết theo batch bounded
    -> xử lý idempotent
    -> tiếp tục cursor
~~~

Nếu ứng dụng cần truy vấn nghiệp vụ theo thứ tự thời gian hoặc theo owner, SCAN qua tên key thường không phải access pattern tốt. Nên dùng cấu trúc Sorted Set/index phụ trợ hoặc lưu theo thiết kế truy vấn phù hợp.

### 10.3. Redis connection phải được hoàn trả

Khi dùng connection pool, cần tuân thủ API của client: mượn connection/session, sử dụng trong khối có cleanup phù hợp, **đóng/return về pool** sau khi xong. Đóng kết nối logic từ pool khác với đóng toàn bộ client/pool của ứng dụng. Phải xác định ai là owner của tài nguyên và framework đã quản lý thay chưa.

## 11. Java Stream API: tên Stream không tự bảo đảm đóng cursor

Java Stream có thể là:

~~~java
Stream<String> stream = list.stream();
~~~

Đây là stream từ List đã có trong memory, **không phải cơ chế truy vấn paging**.

Một repository khác có thể trả:

~~~java
Stream<Event> stream = repository.streamEvents(...);
~~~

Nếu Stream được xây trên database cursor, nó có thể giữ connection/cursor cần cleanup. Nên dùng:

~~~java
try (Stream<Event> stream = repository.streamEvents(...)) {
    stream.forEach(this::processEvent);
}
~~~

Nhưng điều này chỉ đóng resource đúng khi implementation của repository đã gắn close handler hoặc tài nguyên vào Stream. **Java Stream không tự biết một cursor ẩn phải đóng ra sao**.

Khi tự viết repository stream, phải thiết kế:

~~~text
open cursor
    -> spliterator/iterator truy xuất từng phần
    -> stream.onClose(cursor::close)
    -> consumer dùng try-with-resources
~~~

Đây là mô hình khái niệm. Implementation cụ thể phải xử lý exception, không trả một Stream đã mất lifecycle ownership và kiểm tra khả năng song song.

### 11.1. Không dùng terminal operations gom hết dữ liệu

Các thao tác sau có thể gom toàn bộ kết quả:

~~~java
List<Event> all = stream.toList();
~~~

~~~java
Map<String, List<Event>> grouped = stream
    .collect(Collectors.groupingBy(Event::tenantId));
~~~

~~~java
Event[] all = stream.toArray(Event[]::new);
~~~

Ngay cả khi source lazy, terminal operation có thể biến streaming thành **materialization toàn phần**. Nếu cần tổng hợp, ưu tiên accumulator có kích thước giới hạn hoặc aggregation được thực hiện tại database khi phù hợp.

### 11.2. sorted() trên Stream có thể phá giới hạn bộ nhớ

~~~java
stream.sorted(comparing(Event::eventTime)).forEach(this::processEvent);
~~~

Nếu stream chưa có thứ tự và lượng kết quả lớn, sorted cần biết các phần tử để sắp theo comparator; nó có thể phải giữ lượng dữ liệu rất lớn. Hãy cố thiết kế database index/sort để trả dữ liệu đã có thứ tự, hoặc sử dụng external sort có giới hạn disk/RAM cho tác vụ batch.

### 11.3. parallel() không nhất thiết tốt hơn

Không nên tùy tiện gọi:

~~~java
stream.parallel().forEach(this::processEvent);
~~~

khi stream được cấp bởi một cursor có trạng thái, có quy tắc thread-safety hoặc order-specific processing. Cursor của database có thể không thread-safe; xử lý song song cũng có thể khiến buffer và số request tăng không kiểm soát.

Nếu cần song song, tách thành những partition/query độc lập, giới hạn concurrency và tính toán đúng lượng tài nguyên mỗi partition tiêu thụ.

## 12. Backpressure: consumer chậm thì producer phải làm gì?

Giả sử database có thể trả 10.000 record/giây, nhưng hệ ghi file hoặc API downstream chỉ xử lý 1.000 record/giây.

Nếu producer liên tục lấy dữ liệu và đưa vào queue không giới hạn:

~~~text
Producer 10.000/s -> Unbounded queue -> Consumer 1.000/s
                       backlog +9.000/s
~~~

Queue tăng theo thời gian; dù mỗi page chỉ 100 record, ứng dụng vẫn có thể OOM.

Giải pháp là **giới hạn dữ liệu đang bay**:

~~~text
Producer -> bounded queue -> Consumer
    ^          |
    |          |
    +-- chờ khi đầy
~~~

### 12.1. Bounded queue

Ví dụ một pipeline Java đồng bộ có BlockingQueue kích thước tối đa 500:

~~~java
BlockingQueue<Event> queue = new ArrayBlockingQueue<>(500);

// Producer:
// queue.put(event);  // Block khi queue đầy.

// Consumer:
// Event event = queue.take();
// writeOutput(event);
~~~

Đoạn trên chỉ minh họa cơ chế backpressure của queue. Pipeline hoàn chỉnh còn cần quy tắc kết thúc (sentinel hoặc signaling), truyền exception giữa thread, cancellation, interrupt và đóng cursor. Không được chạy producer vô hạn khi consumer đã chết hoặc HTTP client đã ngắt.

### 12.2. Giới hạn concurrency

Nếu có 20 worker xử lý và mỗi worker giữ 100 record, bộ nhớ tối đa của tầng worker có thể tăng tới 2.000 record, chưa kể driver buffer và queue. Nên dùng:

- Thread pool/concurrency limit có kích thước rõ.
- Bounded queue hoặc reactive demand.
- Timeout cho bước output.
- Truyền tín hiệu cancel về nguồn đọc.
- Giới hạn công việc đang thực hiện theo tenant.

### 12.3. Reactive Streams

Một reactive Publisher có thể hỗ trợ demand qua yêu cầu của Subscriber. Tuy nhiên, operator như prefetch, flatMap với concurrency cao hoặc buffer có thể làm phát sinh dữ liệu trung gian.

Quy tắc:

~~~text
Database publisher
   -> bounded prefetch
   -> transform
   -> bounded write concurrency
   -> downstream subscriber
~~~

Nếu downstream không theo kịp, nên giảm demand hoặc tạm dừng fetch. Nếu dùng operator drop/latest cho dữ liệu nghiệp vụ, phải hiểu hậu quả mất record: phù hợp với một số luồng telemetry cho phép mất mẫu, nhưng thường **không phù hợp** khi xuất dữ liệu tài chính hoặc migration cần đầy đủ.

### 12.4. Tài nguyên trong reactive phải đóng khi cancel

Trong reactive, các trường hợp kết thúc gồm:

1. Publisher hoàn tất bình thường.
2. Một stage phát lỗi.
3. Subscriber hủy subscription.
4. Timeout khiến pipeline bị cancel.

Cần có cơ chế cleanup **cho cả bốn**, ví dụ resource-scoped publisher hoặc using/usingWhen tùy framework. Không chỉ gọi close trong callback onComplete, vì onComplete không bắt buộc xảy ra khi client cancel.

## 13. Vòng đời tài nguyên: ai mở thì ai đóng?

Một truy vấn NoSQL có thể dùng nhiều tầng tài nguyên:

| Tài nguyên | Ai thường sở hữu? | Khi nào đóng? |
| --- | --- | --- |
| MongoCursor | Repository/job truy vấn | Khi đọc hết, lỗi hoặc hủy |
| MongoClient | Application/container | Khi shutdown hoặc hết scope quản lý |
| DynamoDbClient | Application/container | Khi shutdown, không phải sau mỗi page |
| CqlSession | Application/container | Khi shutdown hoặc khi job độc lập kết thúc |
| Redis pooled connection | Đoạn code mượn connection | Khi hoàn trả về pool sau thao tác |
| HTTP response OutputStream | Framework/controller tương ứng | Theo lifecycle HTTP và lỗi/hủy |
| BufferedWriter file export | Job tạo file | Sau flush/close, kể cả lỗi |
| Reactive subscription | Consumer/caller | Cancel khi không còn cần dữ liệu |
| Executor/worker pool | Application/job manager | Shutdown khi ngừng nhiệm vụ hoặc ứng dụng |

**Nguyên tắc ownership:** tài nguyên được tạo trong scope nào phải có đường cleanup rõ ràng, kể cả scope đó bị thoát do exception, timeout hoặc client ngắt kết nối.

### 13.1. try-with-resources

~~~java
try (MongoCursor<Document> cursor = query.iterator();
     BufferedWriter writer = Files.newBufferedWriter(outputPath)) {
    while (cursor.hasNext()) {
        Document doc = cursor.next();
        writer.write(toCsvLine(doc));
        writer.newLine();
    }
}
~~~

Mẫu này giúp đóng **cả cursor và writer** khi khối kết thúc bình thường hoặc ném exception. Đối với file export, cần quyết định thêm:

- Nếu xuất lỗi giữa chừng, có xóa file tạm không?
- File chỉ được công bố khi ghi hoàn chỉnh chưa?
- Có cần flush/fsync theo mục tiêu durability?
- File có chứa dữ liệu nhạy cảm cần được bảo vệ không?

Không được coi việc writer.close() là bằng chứng file đầu ra đã sẵn sàng phục vụ nếu quá trình ghi đã thất bại trước đó.

### 13.2. Resource leak có thể không làm OOM ngay

Cursor hoặc connection bị bỏ quên có thể tạo:

- Số connection đang dùng tăng liên tục.
- Hết connection trong pool dù heap chưa đầy.
- Cursor server-side bị giữ qua timeout.
- Thread/future chờ mạng không giải phóng.
- Hệ database phải làm việc cho request client đã hủy.

Vì vậy, giám sát chỉ mỗi heap không đủ; phải theo dõi **connection pool, open cursors, active queries, pending futures và số job bị cancel**.

### 13.3. Không đóng tài nguyên do framework đang sở hữu

Nếu framework Spring quản lý singleton MongoClient/DynamoDbClient/CqlSession, một repository **không được tự close singleton đó ở cuối request** vì sẽ làm hỏng request khác. Repository chỉ đóng cursor/stream mà nó tạo ra hoặc theo hợp đồng API.

Nếu code tự tạo client cho một công cụ batch độc lập, nó phải đóng client khi công cụ kết thúc.

## 14. Streaming HTTP: không gom hết trước khi trả response

Một endpoint xuất dữ liệu có thể trả:

~~~text
GET /api/events/export?deviceId=D17
~~~

Nếu controller làm:

~~~text
dbResult.toList()
    -> serialize giant JSON array
    -> HTTP response
~~~

thì nó vẫn cần memory tương ứng tập dữ liệu. Với kết quả lớn, có thể sử dụng **NDJSON**: mỗi dòng là một JSON object độc lập.

~~~http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson
~~~

Payload:

~~~text
{"eventId":"E1","eventTime":"2026-11-14T03:00:00Z"}
{"eventId":"E2","eventTime":"2026-11-14T03:00:01Z"}
{"eventId":"E3","eventTime":"2026-11-14T03:00:02Z"}
~~~

Đường xử lý:

~~~text
Cursor -> từng Document -> JSON line -> HTTP output
~~~

Khi ghi mạng chậm, output writer hoặc reactive transport cần tạo **backpressure** để không tiếp tục fetch vô hạn. Streaming response không miễn phí; socket có buffer, proxy/CDN có thể buffer và client có thể đọc rất chậm.

### 14.1. Các rủi ro của HTTP streaming

- Khi header/status đã gửi, lỗi ở record thứ 500 có thể không còn trả HTTP 500 theo cách thông thường.
- Client có thể nhận **file một phần**.
- Proxy timeout hoặc buffering có thể khiến ứng dụng tưởng dữ liệu đã được stream nhưng client chưa nhận.
- Một JSON array thường khó sửa sau lỗi giữa chừng; NDJSON thuận lợi hơn cho xử lý từng dòng.
- Nếu client ngắt, server cần cancel pipeline và close cursor.
- Phải kiểm tra quyền trước khi stream và trong các job dài khi chính sách quyền có thể thay đổi.

### 14.2. Khi nào nên dùng export job thay vì giữ HTTP mở?

Với export kéo dài hàng chục phút/hàng giờ:

~~~text
POST /exports
    -> tạo job, trả jobId

Worker:
    -> đọc theo cursor/page có checkpoint
    -> ghi file tạm có giới hạn buffer
    -> hoàn tất mới công bố file

GET /exports/{jobId}
    -> trạng thái / tiến độ
~~~

Job có thể giới hạn concurrency, retry, áp dụng retention và kiểm tra quyền khi tải file. Dù dùng job async, bộ đọc vẫn phải bounded và đóng cursor/connection.

## 15. Timeout, retry và cancellation trong truy vấn dài

Một stream có thể gián đoạn bởi:

- Database/network timeout.
- Cursor timeout do không hoạt động.
- Application restart.
- Rate limit hoặc overloaded backend.
- Consumer xử lý lỗi một record.
- Client cancel hoặc đóng kết nối HTTP.

Không phải lúc nào có thể retry **giữa stream hiện tại** rồi tiếp tục ở đúng record kế tiếp. Cơ chế phụ thuộc cursor và consistency của truy vấn.

### 15.1. Retry cả truy vấn có thể tạo dữ liệu trùng

Giả sử đã xuất:

~~~text
E1
E2
E3
~~~

sau đó kết nối lỗi. Nếu query chạy lại từ đầu, file có thể trở thành:

~~~text
E1
E2
E3
E1
E2
E3
E4
...
~~~

Đối với export, cần cơ chế **checkpoint** hoặc output idempotent để tránh ghi trùng. Không thể coi paging cursor là một bookmark tồn tại vĩnh viễn.

### 15.2. Keyset pagination để khôi phục

Với thứ tự:

~~~text
eventTime DESC, eventId DESC
~~~

checkpoint có thể là:

~~~json
{
  "tenantId": "T01",
  "deviceId": "D17",
  "lastEventTime": "2026-11-14T08:30:00Z",
  "lastEventId": "E107",
  "sort": "eventTime_desc_eventId_desc",
  "queryVersion": 1
}
~~~

Khi tiếp tục, chỉ đọc các tuple **nhỏ hơn** tuple cuối đã xử lý:

~~~text
eventTime < lastTime
OR
(eventTime = lastTime AND eventId < lastId)
~~~

Đây là điều kiện logic; cách viết cụ thể tùy MongoDB, Cassandra, DynamoDB hoặc engine khác. Với DynamoDB có thể dùng LastEvaluatedKey cho một chuỗi Query phù hợp, nhưng khả năng lưu/reuse lâu dài phải được đánh giá theo hợp đồng token, index và điều kiện truy vấn.

### 15.3. Checkpoint phải theo sau output commit

Nếu job:

~~~text
1. Đọc E107.
2. Ghi checkpoint = E107.
3. Crash trước khi ghi E107 ra file.
~~~

thì khi chạy lại, E107 có thể bị **bỏ sót**.

Một nguyên tắc:

~~~text
read batch
    -> transform
    -> write output durably theo phạm vi yêu cầu
    -> commit checkpoint
~~~

Nếu output và checkpoint ở hai hệ không có transaction chung, vẫn có cửa sổ khiến job ghi lại một batch sau crash. Vì vậy thiết kế **at-least-once + deduplication** hoặc output idempotent thường thực tế hơn lời hứa exactly-once không có cơ chế chứng minh.

### 15.4. Dữ liệu thay đổi trong lúc đọc

Một cursor/page sequence không nhất thiết là snapshot cố định:

- Record mới có thể được thêm vào vùng query.
- Record cũ có thể bị xóa.
- Một field sort có thể được cập nhật.
- Replica/read preference có thể tạo độ trễ khác nhau.

Nếu nghiệp vụ cần export nhất quán tại một mốc, phải cân nhắc snapshot/point-in-time hoặc watermark phù hợp với database. Nếu chấp nhận kết quả đang thay đổi, hãy mô tả semantics để consumer hiểu có thể xuất hiện thiếu/lặp/biến động.

## 16. Cân bằng tính đầy đủ, độ trễ và chi phí

Streaming kết quả lớn không có nghĩa nên chạy mọi query theo cùng cách.

| Use case | Cách đọc thường phù hợp | Điều cần chú ý |
| --- | --- | --- |
| API trả 20 kết quả mới nhất | Query + limit | Không mở stream dài cho kết quả nhỏ |
| UI phân trang | Keyset/continuation token | Bảo vệ cursor theo tenant và filter |
| Export vài trăm nghìn record | Cursor/page + output streaming | Memory budget, timeout, cancel |
| Migration/backfill | Batch/page + checkpoint | Idempotency, trạng thái nguồn thay đổi |
| Đọc sự kiện liên tục | Change stream/CDC | Resume token, retention, backpressure |
| Quét key Redis phục vụ bảo trì | SCAN + giới hạn tốc độ | Không snapshot, có duplicate |
| Đọc ngẫu nhiên theo ID | BatchGet/multi-get có kiểm soát | Chunk ID list, không gửi batch khổng lồ |
| Tổng hợp thống kê | Server-side aggregation khi phù hợp | Không tải toàn bộ record về JVM để sum |

Một truy vấn cần kết quả đầy đủ và trật tự ổn định phải được thiết kế khác một dashboard chỉ cần một trang dữ liệu gần đúng. Không nên dùng streaming chỉ vì tên gọi có vẻ “tối ưu”; hãy bắt đầu từ access pattern và hợp đồng kết quả.

## 17. Bảo mật và giới hạn tài nguyên khi stream NoSQL

Các endpoint cho phép đọc rất nhiều dữ liệu là mục tiêu dễ bị lạm dụng hoặc gây quá tải do lỗi người dùng.

Các biện pháp quan trọng:

1. **Bắt buộc lọc tenant/quyền** từ ngữ cảnh đã xác thực, không chỉ tin tham số client.
2. **Giới hạn khoảng thời gian và tổng số record** cho request tương tác.
3. **Hạn chế concurrent exports** theo tenant/user và toàn hệ.
4. **Timeout và cancellation** rõ ràng cho query, HTTP, worker.
5. **Projection** để tránh gửi payload nhạy cảm không cần thiết.
6. **Đếm bytes** đầu ra, không chỉ số record, nhất là khi kích thước document biến thiên.
7. **Không log toàn bộ document** hoặc continuation token nhạy cảm.
8. **Bảo vệ cursor/token** để client không thể sửa sang phạm vi dữ liệu khác.
9. **Rate limit** cả số request lẫn lượng dữ liệu được trích xuất.
10. **Quản lý file export**: TTL, encryption/access control và cleanup khi thất bại.

Nếu đọc một query streaming trong 30 phút mà quyền của người dùng bị thu hồi giữa chừng, kiến trúc cần quyết định có kiểm tra lại authorization ở các checkpoint hay không. Không nên mặc định quyền tại thời điểm bắt đầu áp dụng vĩnh viễn cho mọi job nhạy cảm.

## 18. Giám sát streaming và phát hiện leak

Một pipeline tốt cần quan sát không chỉ latency, mà cả tốc độ tiêu thụ, tài nguyên và khả năng kết thúc.

| Metric | Vì sao cần |
| --- | --- |
| Active streams/cursors | Phát hiện query bị bỏ quên hoặc tăng bất thường |
| Open DB connections / pool utilization | Cảnh báo cạn connection |
| In-flight pages và bytes | Kiểm soát prefetch/memory |
| Buffer/queue depth | Biết producer có đang vượt consumer không |
| Pages/records per second | Quan sát throughput thực |
| p95/p99 fetch latency | Phát hiện query/network chậm |
| Output write latency | Phát hiện sink chậm hoặc bị nghẽn |
| Heap used, allocation rate, GC pause | Phát hiện materialization/pressure |
| Stream cancellation count | Phát hiện client disconnect hoặc timeout |
| Cursor close errors/leaked resources | Kiểm tra lifecycle và cleanup |
| Export retry/duplicate count | Đánh giá correctness khi phục hồi |
| Oldest active stream age | Phát hiện job sống quá lâu |

### 18.1. Một ví dụ sự cố

~~~text
Heap:           bình thường
Active cursors: tăng từ 30 lên 3.000
DB connections: pool gần hết
Request errors: tăng timeout
~~~

Ứng dụng có thể chưa OOM, nhưng đang **rò rỉ cursor hoặc giữ connection**. Kiểm tra đường cleanup khi exception, cancel và timeout quan trọng hơn việc chỉ tăng heap.

### 18.2. Trace theo một job

Có thể gắn:

~~~text
exportJobId
tenantId (đã kiểm soát quyền)
queryType
queryStart
pagesFetched
recordsProcessed
bytesWritten
lastCheckpoint
closeReason = COMPLETE | ERROR | CANCEL | TIMEOUT
~~~

Log không nên chứa toàn bộ payload hoặc secret. Quan sát được **vì sao stream kết thúc** sẽ giúp xử lý những job treo hoặc bị hủy liên tục.

## 19. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Query xong gọi toList() | Heap tăng theo tổng record | Xử lý từng phần |
| Đặt batchSize nhỏ rồi gom tất cả vào List | Vẫn OOM | Bounded end-to-end pipeline |
| Không đóng MongoCursor | Leaked server/client resources | try-with-resources |
| Đóng singleton MongoClient/CqlSession sau mỗi request | Request khác mất kết nối, overhead cao | Đóng theo application lifecycle |
| Dùng Stream.parallel() trên cursor có trạng thái | Race, tài nguyên tăng, sai thứ tự | Parallel theo partition/query độc lập |
| Gọi sorted() trên stream lớn | Materialize dữ liệu để sort | Sort bằng index hoặc external sort |
| Queue không giới hạn | Producer nhanh làm đầy heap | Bounded queue/backpressure |
| Retry export từ đầu không checkpoint | Lặp record | Cursor/seek checkpoint và dedup |
| Checkpoint trước khi output commit | Bỏ sót record khi crash | Output commit trước checkpoint |
| Coi pageSize là tổng giới hạn | Query vẫn đọc toàn bộ dữ liệu | Total limit riêng |
| Coi page rỗng là hết dữ liệu | Bỏ sót trang sau khi filter | Dựa vào continuation token |
| Dùng KEYS Redis trong keyspace lớn | Tăng latency/server load | SCAN có giới hạn và hiểu semantics |
| Giữ HTTP stream mở bất chấp client cancel | Lãng phí cursor/connection | Propagate cancellation |
| Tin mọi query có WHERE đều hiệu quả | Scan nặng ở server | Thiết kế key/index phù hợp |
| Quên giới hạn đồng thời | OOM/pool exhaustion ở giờ cao điểm | Concurrency/admission control |
| Chỉ đo heap, không đo connection/cursor | Leak không phát hiện sớm | Resource metrics và close reason |
| Tự chế continuation token không bảo vệ | Có thể đọc sai tenant/sai query | Token có integrity và context |

## 20. Quy trình thiết kế một luồng đọc an toàn

### Bước 1 — Viết hợp đồng của truy vấn

Xác định người dùng cần **một trang**, **toàn bộ dữ liệu** hay **một snapshot tại thời điểm nào**. Nêu thứ tự, độ chính xác, quyền, số record tối đa, độ trễ cho phép và response khi timeout.

### Bước 2 — Thiết kế access pattern

Dùng partition/group key và sort key hoặc index phù hợp. Tránh quét toàn bộ database chỉ vì API có thể stream.

### Bước 3 — Giới hạn kết quả ở database

Filter, projection, limit, time range, page size và query timeout theo khả năng engine. Phân biệt mỗi tham số có ý nghĩa **tổng** hay **trên từng page**.

### Bước 4 — Đặt memory budget

Đo kích thước record thực tế. Giới hạn driver prefetch, queue, output buffer, số worker và số stream đồng thời. Có dự phòng cho object overhead và GC.

### Bước 5 — Xác định ownership tài nguyên

Ai tạo cursor, ai đóng; client/connection pool do ai quản lý; output file do ai cleanup. Đảm bảo cleanup khi hoàn tất, exception, timeout và cancellation.

### Bước 6 — Thiết kế backpressure

Nếu output chậm, producer phải chờ hoặc giảm demand thay vì tiếp tục fetch vô hạn. Mọi buffer phải có giới hạn hữu hình.

### Bước 7 — Chọn cơ chế resume

Với job dài, dùng continuation/keyset token và checkpoint phù hợp. Đặt checkpoint sau khi output hoàn tất theo phạm vi cam kết; chấp nhận và xử lý cửa sổ retry/duplicate nếu không có transaction chung.

### Bước 8 — Kiểm thử ở tải thật

Thử record lớn, nhiều tenant, rất nhiều trang, client cancel, database timeout, consumer lỗi giữa chừng, retry sau checkpoint và dữ liệu nguồn thay đổi.

### Bước 9 — Giám sát và cleanup

Theo dõi active streams, cursor/connection pool, memory, queue depth, duration và lỗi đóng. Có deadline cho job treo và quy trình thu dọn file tạm.

## 21. Bài tập thực hành

### Bài 1: Tìm nguyên nhân OOM

Cho:

~~~java
List<Document> result = new ArrayList<>();
try (MongoCursor<Document> cursor = query.batchSize(50).iterator()) {
    while (cursor.hasNext()) {
        result.add(cursor.next());
    }
}
~~~

**Câu hỏi:** Đã dùng batchSize=50 và đóng cursor, vì sao vẫn có thể OOM?

**Gợi ý:** List giữ mọi document. Batch size chỉ điều chỉnh fetch, không giới hạn toàn bộ dữ liệu. Cần xử lý/ghi dần hoặc giới hạn tổng số record.

### Bài 2: Phân biệt ba giới hạn

Một API có:

~~~text
totalLimit = 5.000
pageSize = 200
queueCapacity = 300
~~~

**Câu hỏi:** Mỗi tham số bảo vệ điều gì?

**Gợi ý:** Total limit giới hạn số record toàn yêu cầu; page size ảnh hưởng mỗi lần fetch; queue capacity giới hạn record chờ xử lý. Cả ba cần được xem cùng kích thước record, output buffer và concurrency.

### Bài 3: Ước lượng bộ nhớ

Giả sử:

~~~text
driver batch = 100 records
queue = 200 records
output batch = 50 records
average decoded size = 8 KiB / record
~~~

**Câu hỏi:** Ước lượng phần dữ liệu đang giữ, chưa tính Java object overhead?

**Gợi ý:** (100+200+50) × 8 KiB = **2.800 KiB**, khoảng **2,73 MiB**. Heap thực tế có thể cao hơn.

### Bài 4: Page rỗng ở DynamoDB

Một Query có FilterExpression trả **0 items** nhưng LastEvaluatedKey không rỗng.

**Câu hỏi:** Có được kết luận hết dữ liệu không?

**Gợi ý:** Không. Filter áp dụng sau khi đọc theo điều kiện khóa. Tiếp tục theo LastEvaluatedKey; chỉ kết thúc theo semantics token của API.

### Bài 5: Redis SCAN

Một vòng SCAN trả danh sách key rỗng nhưng next cursor = "4532".

**Câu hỏi:** Có nên dừng? SCAN có thể trả lại key đã thấy trước đó không?

**Gợi ý:** Không dừng khi cursor chưa về "0". SCAN có thể trả duplicate; job nên idempotent, và không có snapshot nhất quán nếu keyspace thay đổi.

### Bài 6: Cursor và request bị hủy

HTTP client đóng kết nối sau 500 dòng NDJSON, nhưng worker vẫn gọi cursor.next() đến hết 1 triệu bản ghi.

**Câu hỏi:** Thiếu cơ chế gì?

**Gợi ý:** Propagate cancellation từ HTTP tới producer, dừng vòng lặp và close cursor; không chỉ tin try-with-resources khi vòng lặp chưa thoát.

### Bài 7: Retry sau crash

Job đã ghi E1, E2, E3 ra file nhưng crash trước khi lưu checkpoint E3. Khi chạy lại, nó bắt đầu từ E1.

**Câu hỏi:** Làm sao tránh file bị lặp hoặc giữ dữ liệu sai?

**Gợi ý:** Output idempotent/dedup theo eventId, partition file theo batch có commit marker hoặc cơ chế resume, cùng checkpoint sau output commit.

### Bài 8: Java Stream không lazy như mong đợi

~~~java
try (Stream<Event> events = repository.streamAll()) {
    List<Event> all = events.toList();
}
~~~

**Câu hỏi:** Đóng Stream đã đủ bảo đảm memory bounded chưa?

**Gợi ý:** Chưa. toList materializes toàn bộ kết quả. Tương tự sorted(), groupingBy() hoặc toArray() có thể tăng memory đáng kể.

### Bài 9: Ai đóng client?

Trong Spring application, MongoClient được khai báo singleton và nhiều repository dùng chung. Một method repository gọi mongoClient.close() sau khi xong query.

**Câu hỏi:** Tại sao sai dù close là việc tốt?

**Gợi ý:** Client thuộc lifecycle ứng dụng/container, không thuộc request. Repository chỉ nên đóng resource nó mở như cursor. Đóng singleton có thể làm hỏng request khác.

### Bài 10: Streaming và tính nhất quán

Một job xuất 500.000 sự kiện, trong lúc chạy một số sự kiện bị xóa hoặc đổi eventTime.

**Câu hỏi:** Streaming có tự bảo đảm output là snapshot không?

**Gợi ý:** Không. Cần xác định semantics của cursor/pagination ở engine và sử dụng snapshot/point-in-time/watermark phù hợp khi nghiệp vụ yêu cầu tính nhất quán tại một mốc.

## 22. Kết luận

Đọc dạng luồng trong NoSQL giúp ứng dụng xử lý tập kết quả lớn mà không bắt buộc tải toàn bộ vào heap. Nhưng một pipeline chỉ thật sự kiểm soát bộ nhớ khi **mỗi tầng từ database đến output đều có giới hạn**, không sử dụng những thao tác gom dữ liệu vô hạn và có **backpressure** khi consumer chậm.

MongoCursor, DynamoDB paginator, Cassandra paging và Redis SCAN cung cấp các cơ chế đọc dần với semantics khác nhau. **Batch size, page size, query limit, continuation token và cursor lifecycle không phải là cùng một khái niệm.** Cần hiểu khả năng của từng API, chọn key/index phù hợp và tránh quét dữ liệu không cần thiết.

Cuối cùng, tính ổn định phụ thuộc vào **đóng cursor/connection đúng ownership, xử lý cancellation, timeout, retry và checkpoint**, cùng quan sát active streams, heap, queue, connection pool và lỗi. Một hệ thống streaming tốt không chỉ tránh OOM khi dữ liệu lớn, mà còn dừng đúng lúc, khôi phục được sau sự cố và không giữ tài nguyên khi người dùng không còn cần kết quả.
