# Query fields sort và limit trong Spring Integration MongoDB

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Đọc và xây dựng Spring Data MongoDB `Query` gồm **filter**, **fields/projection**, **sort** và **limit** đúng theo hợp đồng nghiệp vụ.
- Hiểu vì sao MongoDB inbound channel adapter **`MongoDbMessageSource`** và outbound gateway **`MongoDbOutboundGateway`** cần kiểm soát số document, độ lớn payload và thứ tự kết quả.
- Dùng `Query.fields().include(...)` và `exclude(...)` để chọn trường cần lấy; biết quy tắc đặc biệt của `_id` và tác động lên entity mapping.
- Dùng `Query.with(Sort.by(...))` để sắp xếp tăng/giảm; thêm khóa phụ `_id` khi sort key có thể trùng để có thứ tự toàn phần ổn định.
- Dùng `Query.limit(n)` để giới hạn **số document trả về**, không nhầm với `maxMessagesPerPoll` của Spring Integration hay số Spring Messages sau splitter.
- So sánh **offset pagination** (`skip` + `limit`) và **keyset/cursor pagination** trên tập dữ liệu thay đổi.
- Chọn index theo filter + sort, kiểm tra `explain` trong môi trường test và phân biệt **giảm dữ liệu trả về** với **tăng tốc truy vấn**.
- Xây dựng inbound polling flow, outbound request/reply gateway, transformer/splitter và test bảo đảm query vẫn chứa điều kiện tenant, giới hạn kết quả, chỉ trả các field được phép.
- Nhận biết rủi ro **đọc lặp**, **bỏ sót document**, **ghi đè vì entity thiếu field**, **query quá rộng** và xử lý retry/idempotency khi nhiều worker cùng chạy.

Bài thuộc chương **Adapter MongoDB** của module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối hệ thống ngoài vào Spring Integration bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, chú trọng **hợp đồng message, lỗi và vòng đời kết nối**. Ở đây, query fields, sort và limit là các quyết định **ở tầng MongoDB query**, ảnh hưởng trực tiếp đến payload và hiệu năng của luồng message phía sau.

## 1. Tình huống: chỉ đọc dữ liệu cần thiết cho telemetry pipeline

Một collection `telemetry_events` chứa hàng triệu bản ghi. Mỗi bản ghi có nhiều field và có thể kèm payload thiết bị khá lớn:

~~~json
{
  "_id": "evt-102",
  "tenantId": "tenant-a",
  "deviceId": "node-7",
  "status": "NEW",
  "sequence": 102,
  "temperatureC": 26.5,
  "observedAt": "2026-11-20T08:00:01Z",
  "rawPayload": "large-sensor-frame-..."
}
~~~

Hệ thống có hai nhu cầu:

1. **Background worker:** mỗi 5 giây poll tối đa 50 sự kiện `NEW` của `tenant-a`, lấy các field cần xử lý, theo thứ tự `observedAt` cũ nhất trước.
2. **API request/reply:** khi người dùng tra cứu lịch sử thiết bị, trả tối đa 20 bản ghi mới nhất, chỉ những field được phép hiển thị, không trả `rawPayload`.

Nếu chỉ viết `find({ status: "NEW" })` không có giới hạn:

- Một lần poll có thể đọc rất nhiều document và tạo **`Message<List<T>>` cực lớn**.
- Splitter có thể phát hàng nghìn messages trong một chu kỳ.
- HTTP request có thể kéo quá nhiều dữ liệu về RAM, vượt timeout hoặc rò field nhạy cảm.
- Sort không rõ ràng khiến “mới nhất” hoặc “cũ nhất” bị hiểu nhầm.
- Retry một lượt poll có thể đọc lại cùng document nếu trạng thái vẫn thỏa query.

Giải pháp là định nghĩa một **hợp đồng truy vấn có giới hạn và có thể kiểm thử**:

~~~mermaid
flowchart LR
    R["Poller hoặc Request"] --> F["Criteria / Filter"]
    F --> S["Sort"]
    S --> L["Limit"]
    L --> P["Fields / Projection"]
    P --> DB[("MongoDB")]
    DB --> M["Message<List<T>> hoặc Message<T>"]
    M --> H["Splitter / Reply / Handler"]
~~~

Sơ đồ mô tả các tùy chọn của một query, không khẳng định MongoDB thực thi vật lý theo chính thứ tự của các ô. Server có query planner và có thể tận dụng index/optimization; hãy dùng `explain` để kiểm tra thực tế.

## 2. Phân biệt filter, fields, sort, limit và skip

| Thành phần | Câu hỏi nó trả lời | API Spring Data | Ý nghĩa |
|---|---|---|---|
| **Filter / criteria** | **Document nào** phù hợp? | `Query.query(Criteria.where(...))` | Lọc theo tenant, trạng thái, thiết bị, thời gian |
| **Fields / projection** | Trả về **field nào** từ mỗi document? | `query.fields().include(...)` / `exclude(...)` | Giảm dữ liệu trả qua mạng, giới hạn contract payload |
| **Sort** | Kết quả theo **thứ tự nào**? | `query.with(Sort.by(...))` | ASC/DESC, tie-break với `_id` |
| **Limit** | Trả tối đa **bao nhiêu document**? | `query.limit(n)` | Giới hạn batch/result size |
| **Skip** | Bỏ qua bao nhiêu kết quả đầu tiên? | `query.skip(n)` | Offset pagination; có chi phí ở offset lớn |
| **Collection** | Truy vấn ở tập document nào? | `find(query, Class, "collection")` | Collection trong database đã chọn |
| **Entity class** | Map kết quả thành kiểu Java nào? | `find(query, Event.class, ...)` | Spring Data MongoDB conversion |
| **Poller** | Khi nào gọi query? | `Pollers.fixedDelay(...)` | Cấu hình Spring Integration, **không phải phần của MongoDB Query** |

Ví dụ cùng một query ở mongosh:

~~~javascript
db.telemetry_events.find(
  { tenantId: "tenant-a", status: "NEW" },
  { _id: 1, tenantId: 1, deviceId: 1, sequence: 1, observedAt: 1 }
).sort({ observedAt: 1, _id: 1 }).limit(50)
~~~

Và bằng Spring Data:

~~~java
Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("NEW"))
        .with(Sort.by(
                Sort.Order.asc("observedAt"),
                Sort.Order.asc("_id")))
        .limit(50);

query.fields()
        .include("id")
        .include("tenantId")
        .include("deviceId")
        .include("sequence")
        .include("observedAt");
~~~

Trong Java, `id` là property đã gắn `@Id` và có thể được Spring Data mapping thành `_id`. Nếu bạn trực tiếp dùng raw MongoDB driver/mongosh, phải viết field BSON thật, ví dụ `_id`, không có Java mapping tự động.

## 3. Dependency và dữ liệu lab

### 3.1. Dependency Maven

Một dự án **Spring Boot 3.x** có thể sử dụng dependency management của Boot:

~~~xml
<!-- Trong phần <dependencies> của pom.xml -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-mongodb</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Các ví dụ dùng Java 17+, Spring Data `MongoOperations` và **blocking MongoDB driver**. Với Spring Boot/Spring Integration major version khác, cần đối chiếu BOM, starter và API thay vì sao chép version riêng lẻ hoặc trộn blocking/reactive.

Trong `application.yml` của môi trường lab (Spring Boot 3.x):

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://127.0.0.1:27017/adapter_query_lab
~~~

**Chỉ dùng URI local để học**. Production phải có secret management, TLS/role phù hợp, timeout, pool và authorization. Nếu Spring Boot đã tạo `MongoTemplate`/`MongoOperations`, tái sử dụng bean đó.

### 3.2. Seed dữ liệu với các giá trị sort trùng nhau

Trong `mongosh`, tạo dữ liệu để phân biệt thứ tự và projection:

~~~javascript
use adapter_query_lab

db.telemetry_events.insertMany([
  {
    _id: "evt-101", tenantId: "tenant-a",
    deviceId: "node-7", status: "NEW", sequence: 101,
    temperatureC: 25.5,
    observedAt: ISODate("2026-11-20T08:00:00Z"),
    rawPayload: "private-frame-101"
  },
  {
    _id: "evt-102", tenantId: "tenant-a",
    deviceId: "node-7", status: "NEW", sequence: 102,
    temperatureC: 26.5,
    observedAt: ISODate("2026-11-20T08:00:01Z"),
    rawPayload: "private-frame-102"
  },
  {
    _id: "evt-103", tenantId: "tenant-a",
    deviceId: "node-8", status: "NEW", sequence: 103,
    temperatureC: 27.1,
    observedAt: ISODate("2026-11-20T08:00:01Z"),
    rawPayload: "private-frame-103"
  },
  {
    _id: "evt-104", tenantId: "tenant-a",
    deviceId: "node-8", status: "DONE", sequence: 104,
    temperatureC: 26.8,
    observedAt: ISODate("2026-11-20T08:00:02Z")
  },
  {
    _id: "evt-201", tenantId: "tenant-b",
    deviceId: "node-7", status: "NEW", sequence: 201,
    temperatureC: 29.4,
    observedAt: ISODate("2026-11-20T08:00:02Z")
  }
])
~~~

Kết quả query của worker theo `tenant-a` và `status=NEW` sẽ gồm `evt-101`, `evt-102` và `evt-103`, theo sort `observedAt ASC, _id ASC`. Document `evt-104` là DONE nên không phù hợp, còn `evt-201` thuộc tenant khác nên phải bị loại.

**Không chạy seed trên production.** Gửi `insertMany` lần nữa với ID trùng có thể gây duplicate key. Với integration test, nên dùng database/collection riêng và ID thử nghiệm duy nhất, cleanup đúng những document test đã tạo.

### 3.3. Entity mapping

~~~java
package example.mongodb;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "telemetry_events")
public record TelemetryEvent(
        @Id String id,
        String tenantId,
        String deviceId,
        String status,
        long sequence,
        BigDecimal temperatureC,
        Instant observedAt,
        String rawPayload) {
}
~~~

`@Document(collection="telemetry_events")` chỉ định collection mặc định của entity khi thao tác không truyền tên collection khác. Spring Integration inbound/gateway có thể **chọn collection tường minh**, vì vậy luôn kiểm tra cả MongoOperations bean, database và collection khi chẩn đoán query sai.

## 4. Query.fields(): projection là gì?

**Projection** là việc chỉ chọn một số field trong kết quả MongoDB, thay vì tải toàn bộ BSON document. Đó là ý nghĩa của từ **fields** trong chủ đề bài, không phải các Java reflection fields.

Ví dụ document chứa `rawPayload` lớn nhưng handler chỉ cần ID, tenant, device, sequence và thời gian. Ta yêu cầu MongoDB chỉ trả những trường ấy:

~~~javascript
db.telemetry_events.find(
  { tenantId: "tenant-a", status: "NEW" },
  {
    _id: 1,
    tenantId: 1,
    deviceId: 1,
    sequence: 1,
    observedAt: 1
  }
)
~~~

Kết quả ví dụ:

~~~json
{
  "_id": "evt-101",
  "tenantId": "tenant-a",
  "deviceId": "node-7",
  "sequence": 101,
  "observedAt": "2026-11-20T08:00:00Z"
}
~~~

**Field `rawPayload`, `status` và `temperatureC` không nằm trong response** dù các field vẫn tồn tại trong document gốc. Điều này có thể giảm băng thông và giảm số bytes mà ứng dụng cần map, nhưng không tự bảo đảm query chỉ đọc các field đó từ disk; hiệu năng thực tế còn phụ thuộc index/query planner.

### 4.1. Bao gồm trường: include

Spring Data:

~~~java
Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("NEW"));

query.fields()
        .include("tenantId")
        .include("deviceId")
        .include("sequence")
        .include("observedAt");
~~~

Khi có ít nhất một field được include, MongoDB chỉ trả những field đã include, **cộng `_id` theo mặc định**. Không cần gọi `.include("id")` nếu chỉ muốn giữ ID. Tuy vậy, khi dự án dùng mapping `@Id` và class khác nhau, cần test field name/result thực tế.

### 4.2. Loại trừ trường: exclude

Nếu muốn giữ phần lớn document nhưng loại raw payload:

~~~java
query.fields().exclude("rawPayload");
~~~

Câu lệnh này là **một phương án thay thế** tập các `include(...)` trước đó, không đặt tiếp trên cùng query nếu vừa include field thông thường vừa exclude field khác.

### 4.3. Quy tắc đặc biệt của _id

Trong MongoDB projection:

- `_id` được **bao gồm mặc định** trừ khi loại trừ tường minh.
- Có thể include các field khác và **exclude `_id`**.
- Thông thường không được trộn **include** và **exclude** trên các field khác nhau, ngoại lệ là `_id`.

Ví dụ chỉ trả device ID và sequence, không trả `_id`:

~~~java
query.fields()
        .include("deviceId")
        .include("sequence")
        .exclude("id"); // Mapped @Id -> MongoDB _id
~~~

Bản query tương đương ở mongosh:

~~~javascript
db.telemetry_events.find(
  { tenantId: "tenant-a" },
  { deviceId: 1, sequence: 1, _id: 0 }
)
~~~

**Cân nhắc kỹ trước khi bỏ `_id`.** Với một luồng cần chống trùng, ACK, retry hoặc ghi trạng thái DONE, event ID thường là khóa quan trọng. Nếu projection loại nó, downstream có thể không đủ dữ liệu để thực hiện idempotency.

### 4.4. Trường lồng nhau và @Field

Giả sử entity có property `deviceId` nhưng MongoDB lưu là `device_id`:

~~~java
@org.springframework.data.mongodb.core.mapping.Field("device_id")
String deviceId;
~~~

Với `MongoTemplate` và entity mapping, bạn có thể dùng property name `deviceId` trong `Criteria` hoặc `query.fields()`, để Spring Data chuyển sang field BSON. Nhưng với **raw driver/mongosh**, phải dùng tên thực `device_id`.

Đối với document lồng nhau, có thể chọn field bằng dot notation:

~~~java
query.fields().include("device.location.city");
~~~

Nếu chọn một nhánh nhỏ của nested document, các field anh em không nhất thiết có trong entity sau mapping. Kiểm tra kiểu đối tượng được deserialize và schema version, đặc biệt khi dùng Java record với các field bắt buộc.

## 5. Projection và entity class: tránh đọc một nửa rồi save cả document

Nếu dùng `TelemetryEvent.class` từ mục 3 nhưng chỉ project `id`, `tenantId`, `deviceId`, `sequence`, `observedAt`, các field không được trả sẽ là **null/default** tùy kiểu và mapping. Ví dụ:

~~~text
MongoDB document gốc:
  _id, tenantId, deviceId, status, sequence,
  temperatureC, observedAt, rawPayload

Projection:
  _id, tenantId, deviceId, sequence, observedAt

Entity sau mapping:
  id = "evt-101"
  status = null
  temperatureC = null
  rawPayload = null
~~~

**Đừng gửi entity chỉ được đọc một phần thẳng sang MongoDB outbound `save(...)` để cập nhật một field.** Save có thể thay thế document theo ID, khiến những field bị loại khỏi projection biến mất hoặc bị ghi thành null/default.

### 5.1. Dùng DTO kết quả phù hợp projection

Tạo một class/record chỉ chứa các field được truy vấn:

~~~java
package example.mongodb;

import java.time.Instant;

import org.springframework.data.annotation.Id;

public record TelemetrySummary(
        @Id String id,
        String tenantId,
        String deviceId,
        long sequence,
        Instant observedAt) {
}
~~~

Khi chỉ cần summary, dùng MongoOperations đọc:

~~~java
List<TelemetrySummary> summaries = mongoOperations.find(
        query, TelemetrySummary.class, "telemetry_events");
~~~

Trong Spring Integration, nếu query inbound/gateway đọc theo summary, cấu hình `entityClass(TelemetrySummary.class)` và bảo đảm field projection tương thích. DTO không có `status` và `rawPayload` nên downstream **không được giả định** các field ấy vẫn tồn tại.

Khi cần đọc entity đầy đủ để cập nhật, hãy truy vấn đủ dữ liệu theo contract hoặc dùng **partial update** bằng `MongoOperations.updateFirst` / `findAndModify` theo điều kiện thay vì save một object thiếu field.

### 5.2. Projection không thay thế authorization

Hạn chế field là một lớp bảo vệ, nhưng **không đủ để phân quyền**. Query còn cần filter tenant/owner do server xác thực; MongoDB account cũng nên có quyền tối thiểu. Một client không thể chỉ dựa vào việc frontend ẩn nút để ngăn đọc collection hoặc field của tenant khác.

## 6. Query.with(Sort): thứ tự có ý nghĩa nghiệp vụ

Sort xác định thứ tự các document **trong kết quả query**.

| Nhu cầu | Sort | Ghi chú |
|---|---|---|
| Event cũ nhất trước | `Sort.by(ASC, "observedAt")` | Thêm `_id` để xử lý timestamp trùng |
| Event mới nhất trước | `Sort.by(DESC, "observedAt")` | API lịch sử, dashboard |
| Ưu tiên cao nhất trước | `Sort.by(DESC, "priority")` | Cần quy định tie-break |
| FIFO theo lúc đưa vào inbox | `createdAt ASC, _id ASC` | Chỉ là “FIFO” nếu createdAt đúng contract |
| Page theo khóa bền | `observedAt DESC, _id DESC` | Hữu ích cho keyset pagination |

### 6.1. Sort ổn định với khóa phụ

Giả sử `evt-102` và `evt-103` có cùng `observedAt`. Nếu chỉ sort theo timestamp, MongoDB không bảo đảm thứ tự tương đối của hai document đó.

Cấu hình:

~~~java
Sort oldestFirst = Sort.by(
        Sort.Order.asc("observedAt"),
        Sort.Order.asc("_id"));

Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("NEW"))
        .with(oldestFirst)
        .limit(50);
~~~

Kết quả mong đợi trong dữ liệu lab:

~~~text
evt-101  2026-11-20T08:00:00Z
evt-102  2026-11-20T08:00:01Z
evt-103  2026-11-20T08:00:01Z
~~~

Thêm `_id` giúp xác định thứ tự khi timestamp trùng, nhưng **không chứng minh ID mã hóa thời gian**. Nếu cần sự kiện “đúng thứ tự phát sinh”, phải có timestamp/sequence đáng tin, chính sách xử lý gói đến muộn và kiểm soát clock drift.

### 6.2. ASC và DESC

~~~java
// Cũ nhất trước:
Sort.by(
    Sort.Order.asc("observedAt"),
    Sort.Order.asc("_id"));

// Mới nhất trước:
Sort.by(
    Sort.Order.desc("observedAt"),
    Sort.Order.desc("_id"));
~~~

Hai đoạn là **hai phương án thay thế**. Không gọi `.with(...)` nhiều lần chỉ để đoán cách sort được ghép; hãy tạo một `Sort` hoàn chỉnh cho một hợp đồng truy vấn.

### 6.3. Sort trước khi projection được áp dụng ở phía kết quả

MongoDB có thể sắp xếp trên field không nằm trong projection trả về. Ví dụ query sort theo `observedAt` nhưng API chỉ trả device ID và sequence. Tuy nhiên, nếu API muốn **phân trang bằng cursor**, nó có thể cần cả sort fields để tạo cursor cho trang tiếp theo; nên giữ những field cần thiết trong DTO/cursor.

### 6.4. Index và sort

Một sort không khớp index có thể cần xử lý nhiều document hoặc tạo in-memory sort ở phía server. Đừng giả định có `limit(20)` thì MongoDB không cần đọc/xem xét thêm dữ liệu.

Kiểm tra `explain("executionStats")` trong lab để biết có `IXSCAN`, `COLLSCAN` hay stage sort. Chi tiết plan thay đổi theo MongoDB version, thống kê dữ liệu và index; không hard-code kỳ vọng một plan duy nhất cho mọi dataset.

## 7. Query.limit(): giới hạn document, không giới hạn số lần poll

`Query.limit(50)` yêu cầu tối đa **50 document** của lần query đó:

~~~java
Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("NEW"))
        .with(Sort.by(
                Sort.Order.asc("observedAt"),
                Sort.Order.asc("_id")))
        .limit(50);
~~~

Nếu có 1.000 document khớp, query lần này trả tối đa 50. Nhưng **không tự loại** 50 document khỏi collection; nếu poll sau vẫn dùng cùng filter `status=NEW`, nó có thể lấy lại đúng 50 document trước đó.

### 7.1. maxMessagesPerPoll(1) hoàn toàn khác limit(1)

| Cấu hình | Tầng | Giới hạn |
|---|---|---|
| `Pollers.fixedDelay(5000)` | Spring Integration poller | Khi nào gọi source |
| `maxMessagesPerPoll(1)` | Polling endpoint | Số lần gọi `receive()` tối đa trong một poll |
| `Query.limit(50)` | MongoDB query | Số document tối đa trong **một query** |
| `expectSingleResult(true)` | MongoDB message source | Dùng `findOne`, một document mỗi `receive()` |
| `.split()` | Spring Integration | Một message chứa List → nhiều messages con |
| `QueueChannel(64)` | Spring Messaging | Capacity số Spring Messages tại queue |
| `replyTimeout=5000` | Messaging gateway | Thời gian caller chờ reply, không phải query limit |

Ví dụ:

~~~text
MongoDB có 10.000 document NEW
Poller.maxMessagesPerPoll(1)
Source sử dụng find(query.limit(50))
=> Tối đa 1 Message<List<50 documents>> ở đầu ra source
=> Splitter tạo tối đa 50 Message<T>
=> Không có trạng thái claim? Poll sau có thể đọc lại 50 document ấy.
~~~

Đây là lý do phải đặt cả **limit** ở query và **rate/capacity** ở downstream.

### 7.2. Limit không tự bảo đảm giới hạn bytes

Nếu mỗi document chứa binary/raw payload vài MB, 50 document vẫn có thể là một batch rất lớn. Cần kết hợp **fields projection**, giới hạn kích thước document, record validation và đôi khi giảm limit xuống 10 hoặc thấp hơn theo đo tải thật.

### 7.3. Vì sao limit 0 không phải cách giới hạn an toàn?

Trong MongoDB/Spring Data, `limit(0)` thường mang ý nghĩa **không áp một giới hạn số document hữu hiệu**. Với request nhận từ người dùng, phải validate giới hạn dương. Đừng biến input “0” thành một query đọc vô hạn vì nghĩ rằng nó sẽ trả 0 document.

Ví dụ validation:

~~~java
public record SearchTelemetryRequest(
        String deviceId, int limit) {

    public SearchTelemetryRequest {
        if (deviceId == null
                || !deviceId.matches("[A-Za-z0-9_-]{1,64}")
                || limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                    "deviceId invalid or limit out of [1,100]");
        }
    }
}
~~~

### 7.4. Limit không thay thế retry, dedup hoặc transaction

Nếu gọi `limit(1)` để lấy một job, hai instance có thể cùng nhìn thấy job đó trước khi worker nào cập nhật trạng thái. Muốn claim độc quyền phải dùng thao tác cập nhật MongoDB **nguyên tử có điều kiện** như `findAndModify` trong thiết kế work queue. Sort + limit chỉ giúp **lựa chọn**, không giúp **giành quyền xử lý**.

## 8. Tập hợp một Query hoàn chỉnh với Criteria, fields, sort và limit

Đặt query builder vào class riêng để unit test:

~~~java
package example.mongodb;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public final class MongoReadQueries {

    private MongoReadQueries() {}

    public static Query inboxBatch(
            String tenantId, int requestedLimit) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "tenantId must be authorized");
        }
        if (requestedLimit < 1 || requestedLimit > 100) {
            throw new IllegalArgumentException(
                    "Batch size must be 1..100");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(tenantId)
                        .and("status").is("NEW"))
                .with(Sort.by(
                    Sort.Order.asc("observedAt"),
                    Sort.Order.asc("_id")))
                .limit(requestedLimit);

        query.fields()
                .include("tenantId")
                .include("deviceId")
                .include("sequence")
                .include("observedAt");

        // MongoDB vẫn mặc định trả _id.
        return query;
    }

    public static Query recentByDevice(
            String tenantId, SearchTelemetryRequest request) {

        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing authorized tenant");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(tenantId)
                        .and("deviceId").is(request.deviceId()))
                .with(Sort.by(
                    Sort.Order.desc("observedAt"),
                    Sort.Order.desc("_id")))
                .limit(request.limit());

        query.fields()
                .include("tenantId")
                .include("deviceId")
                .include("sequence")
                .include("observedAt");

        return query;
    }
}
~~~

**Hai query có mục tiêu khác nhau:**

- `inboxBatch(...)` phục vụ worker: lọc `status=NEW`, **cũ nhất trước**, giới hạn batch.
- `recentByDevice(...)` phục vụ search API: lọc device ID và tenant, **mới nhất trước**, giới hạn request.

Trong ví dụ, `tenantId` là tham số cho mục đích demo, nhưng production phải được lấy từ **identity/authorization context do server xác thực**, không chỉ tin một chuỗi do client gửi.

### 8.1. Kiểm tra query trước khi đi vào IntegrationFlow

Bạn có thể gọi trực tiếp MongoTemplate:

~~~java
List<TelemetrySummary> batch = mongoOperations.find(
        MongoReadQueries.inboxBatch("tenant-a", 50),
        TelemetrySummary.class,
        "telemetry_events");
~~~

Điều này hữu ích để xác minh query logic trong Spring Data trước khi thêm adapter/poller. Nếu query đã sai ở tầng MongoOperations, việc bọc thêm MessageChannel không tự sửa được.

### 8.2. Không dùng lại một Query rồi sửa trong nhiều thread

`Query` là một object có các tùy chọn mutable như fields, sort và limit. Không tạo một singleton `Query` rồi cho cả HTTP requests và poller cùng sửa `limit` theo input mỗi caller.

**Tạo Query mới trên mỗi operation**, như hai factory methods trong ví dụ. Cách này giảm race condition và cho phép test từng request với tiêu chí độc lập.

## 9. Inbound polling: fields/sort/limit trong MongoDbMessageSource

Ở MongoDB inbound, **poller** chủ động gọi `MongoDbMessageSource.receive()`. Source thực thi query theo cấu hình và tạo message khi có dữ liệu. Theo contract source, mặc định:

- `expectSingleResult(false)` gọi `MongoOperations.find(...)` và trả **`Message<List<T>>`**.
- `expectSingleResult(true)` gọi `findOne(...)` và trả **`Message<T>`**.
- List rỗng được xem như không có message.

### 9.1. Java DSL với Query có limit và projection

Tạo một inbound adapter có giới hạn batch:

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class BoundedMongoInboundConfig {

    @Bean("inboxSummaries")
    public MessageChannel inboxSummaries() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow mongoInboxFlow(
            MongoDatabaseFactory mongoDatabaseFactory) {

        return IntegrationFlow
            .from(
                MongoDb.inboundChannelAdapter(
                        mongoDatabaseFactory,
                        MongoReadQueries.inboxBatch("tenant-a", 50))
                    .collectionName("telemetry_events")
                    .entityClass(TelemetrySummary.class)
                    .expectSingleResult(false),
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(5000)
                           .maxMessagesPerPoll(1)))
            .split()
            .channel("inboxSummaries")
            .get();
    }
}
~~~

**Lưu ý API:** Java DSL Spring Integration có overload `MongoDb.inboundChannelAdapter(MongoDatabaseFactory, Query)`. Không mặc định có overload `(MongoOperations, Query)` trong blocking factory ở mọi phiên bản; với MongoOperations, DSL hỗ trợ overload query **chuỗi**. Nếu đã có `MongoTemplate` và muốn dùng `Query` object trực tiếp, có thể cấu hình `MongoDbMessageSource` nhận `Expression` trả Query như mục 10.

Trong ví dụ, `TelemetrySummary` có đúng các field đã chọn, nên downstream không mong chờ status, temperature hay raw payload. Nếu handler cần `status` để quyết định xử lý, phải **thêm field đó vào projection/DTO** hoặc tự quy định rằng source chỉ lấy NEW rồi dùng contract riêng.

### 9.2. Handler nhận một summary

~~~java
package example.mongodb;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class SummaryObserver {

    private static final Logger log =
            LoggerFactory.getLogger(SummaryObserver.class);

    @ServiceActivator(inputChannel = "inboxSummaries")
    public void observe(TelemetrySummary summary) {
        log.info("Polled id={}, tenant={}, device={}, sequence={}",
                summary.id(), summary.tenantId(),
                summary.deviceId(), summary.sequence());

        // Chỉ quan sát. Không tự đánh dấu DONE hay ACK nguồn.
    }
}
~~~

**Đây là demo read-only.** Sau 5 giây, các `NEW` document vừa đọc vẫn còn trong collection và sẽ tiếp tục thỏa query; dù có `limit(50)`, batch đầu có thể được đọc **lặp lại mãi**. Để sử dụng production, cần claim/lease, retry và idempotency (mục 14).

### 9.3. Vì sao maxMessagesPerPoll và limit phải đi chung?

Giả sử có 5.000 document NEW:

~~~text
fixedDelay(5000)
maxMessagesPerPoll(1)
Query.limit(50)
    |
    v
1 MongoDB query <= 50 documents
    |
    v
1 Message<List<TelemetrySummary>>
    |
    v
Splitter => <= 50 Message<TelemetrySummary>
~~~

Chỉ cấu hình `maxMessagesPerPoll(1)` không ngăn query trả 5.000 document. Chỉ cấu hình `limit(50)` cũng không ngăn poll liên tục phát lại 50 document nếu không thay trạng thái.

## 10. MongoDbMessageSource nhận Query động bằng SpEL

Nếu cần dùng MongoOperations đã được Boot cấu hình, nguồn có thể nhận `Expression` trả một `Query` mới trên mỗi lần `receive()`.

### 10.1. Một provider tạo Query mỗi lần poll

~~~java
package example.mongodb;

import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component("mongoInboxQueryPlan")
public class MongoInboxQueryPlan {

    public Query nextBatch() {
        // Trong production, tenant/work type phải đến
        // từ policy có quyền, không phải input chưa validate.
        return MongoReadQueries.inboxBatch("tenant-a", 50);
    }
}
~~~

### 10.2. Cấu hình source với expression

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.expression.common.LiteralExpression;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.mongodb.inbound.MongoDbMessageSource;

@Configuration
@EnableIntegration
public class SpelMongoSourceConfig {

    @Bean
    public MongoDbMessageSource boundedSource(
            MongoOperations mongoOperations) {

        MongoDbMessageSource source = new MongoDbMessageSource(
                mongoOperations,
                new SpelExpressionParser().parseExpression(
                    "@mongoInboxQueryPlan.nextBatch()"));

        source.setCollectionNameExpression(
                new LiteralExpression("telemetry_events"));
        source.setEntityClass(TelemetrySummary.class);
        source.setExpectSingleResult(false);
        return source;
    }

    @Bean
    public IntegrationFlow boundedSourceFlow(
            MongoDbMessageSource boundedSource) {

        return IntegrationFlow
            .from(boundedSource,
                endpoint -> endpoint.poller(
                    Pollers.fixedDelay(5000)
                           .maxMessagesPerPoll(1)))
            .split()
            .channel("inboxSummaries")
            .get();
    }
}
~~~

Ví dụ là **phương án thay thế** mục 9, không đăng ký cả hai flow cùng quét dữ liệu NEW trong một context. Cần có `MongoInboxQueryPlan` là Spring bean và channel/handler `inboxSummaries` tương ứng.

**Điểm ngữ cảnh:** inbound polling **không có request Message đầu vào**, vì vậy expression như `payload.deviceId` không có nghĩa như trong outbound gateway. Ở source, dùng bean policy, configuration, scheduler-controlled state hoặc query provider được quản lý.

### 10.3. Query động cũng cần limit theo mọi nhánh

Nếu `nextBatch()` đôi khi trả `Query` thiếu `limit`, việc bản query khác có giới hạn không cứu được poll ấy. Kiểm tra contract query trong unit tests, kể cả các nhánh NEW/RETRY, theo tenant và điều kiện sau restart.

## 11. Outbound gateway: query theo request với fields, sort, limit

`MongoDbOutboundGateway` là **request/reply endpoint**, khác inbound polling. Nó nhận request Message, thực hiện query và trả reply qua kênh phù hợp.

### 11.1. Cấu hình Java DSL

~~~java
package example.mongodb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.mongodb.dsl.MongoDb;
import org.springframework.data.mongodb.core.MongoOperations;
import org.springframework.messaging.Message;

@Configuration
@EnableIntegration
@IntegrationComponentScan
public class MongoSearchFlowConfig {

    @Bean
    public IntegrationFlow searchFlow(
            MongoOperations mongoOperations) {

        return IntegrationFlow.from("mongoSearchRequests")
            .handle(MongoDb.outboundGateway(mongoOperations)
                .collectionName("telemetry_events")
                .entityClass(TelemetrySummary.class)
                .expectSingleResult(false)
                .queryFunction(
                    (Message<SearchTelemetryRequest> message) ->
                        MongoReadQueries.recentByDevice(
                            "tenant-a",
                            message.getPayload())))
            .get();
    }
}
~~~

Ở đây queryFunction nhận **request Message**, lấy DTO đã validate từ payload, xây Query có filter + fields + sort + limit. Hãy xem `"tenant-a"` là giá trị lab: ứng dụng thật phải đưa tenant từ authentication/authorization context tin cậy, không từ một chuỗi do client tự khai.

Flow **không ép reply vào QueueChannel tĩnh**, vì caller nhiều request nên có replyChannel riêng. Nếu muốn trả dữ liệu qua API, có thể dùng interface `@MessagingGateway`.

### 11.2. @MessagingGateway để ghép request và reply

~~~java
package example.mongodb;

import java.util.List;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
public interface TelemetrySearchApi {

    @Gateway(
        requestChannel = "mongoSearchRequests",
        replyTimeout = 5000)
    List<TelemetrySummary> recent(
            SearchTelemetryRequest request);
}
~~~

Caller:

~~~java
List<TelemetrySummary> results = searchApi.recent(
        new SearchTelemetryRequest("node-7", 20));
~~~

Đoạn gọi nằm trong service đã inject `TelemetrySearchApi`. `@IntegrationComponentScan` cần quét package chứa interface hoặc dùng cách đăng ký proxy tương đương.

**Không dùng một reply QueueChannel chung** rồi để hai HTTP request cùng gọi `receive()` mà không có correlation; message của caller A có thể bị B lấy. `@MessagingGateway` thường tạo temporary reply channel để ghép reply với đúng lời gọi.

### 11.3. Đọc một document với expectSingleResult(true)

Nếu bật `expectSingleResult(true)`, gateway dùng `findOne(...)` và trả một entity khi có dữ liệu. **Nó không tự lấy “document mới nhất” nếu Query thiếu sort.** `Query.limit(20)` không biến một `findOne` thành danh sách 20 document. Khi không có document, cần xác minh hợp đồng no-result/no-reply và timeout; không mặc định Spring Message có payload `null`.

### 11.4. Reply payload là List dù có một kết quả

Khi `expectSingleResult(false)`, `find(...)` trả một `List<TelemetrySummary>`. Nếu DB chỉ có một document, reply vẫn mang **List** thay vì tự unwrap. Với query trả rỗng, gateway list path có thể phát empty list; business API nên quy định trả `[]` và phân biệt với database error.

## 12. Pagination: skip/limit và keyset

Query theo API thường cần pagination, không chỉ một limit cố định.

### 12.1. Offset pagination với skip

Trang số 3, mỗi trang 20 phần tử:

~~~java
int pageNumber = 3; // 1-based
int pageSize = 20;

Query query = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("deviceId").is("node-7"))
        .with(Sort.by(
            Sort.Order.desc("observedAt"),
            Sort.Order.desc("_id")))
        .skip((long) (pageNumber - 1) * pageSize)
        .limit(pageSize);
~~~

**Ưu điểm:** dễ hiểu, phù hợp tập dữ liệu nhỏ hoặc UI có số trang cố định.

**Hạn chế:** offset lớn có thể tốn công vì server phải đi qua nhiều record để bỏ qua; khi document mới được thêm hoặc xóa trong lúc người dùng chuyển trang, dữ liệu có thể **lặp hoặc bị bỏ sót giữa các trang** dù sort ổn định.

Cần giới hạn cả page number, page size và tổng offset được phép. Không cho client gửi skip rất lớn mà không có resource budget.

### 12.2. Keyset pagination dùng tuple (observedAt, _id)

Với sort mới nhất trước `observedAt DESC, _id DESC`, trang tiếp theo lấy những document có khóa **nhỏ hơn khóa cuối trang trước**:

~~~text
last page item:
  observedAt = 2026-11-20T08:00:01Z
  _id = "evt-102"

next page condition:
  observedAt < lastObservedAt
  OR (observedAt == lastObservedAt AND _id < lastId)
~~~

Query Spring Data:

~~~java
import java.time.Instant;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Instant lastObservedAt = Instant.parse(
        "2026-11-20T08:00:01Z");
String lastId = "evt-102";

Criteria afterCursor = new Criteria().orOperator(
        Criteria.where("observedAt").lt(lastObservedAt),
        new Criteria().andOperator(
            Criteria.where("observedAt").is(lastObservedAt),
            Criteria.where("_id").lt(lastId)));

Query query = Query.query(
        new Criteria().andOperator(
            Criteria.where("tenantId").is("tenant-a"),
            Criteria.where("deviceId").is("node-7"),
            afterCursor))
        .with(Sort.by(
            Sort.Order.desc("observedAt"),
            Sort.Order.desc("_id")))
        .limit(20);

query.fields()
        .include("tenantId")
        .include("deviceId")
        .include("sequence")
        .include("observedAt");
~~~

Đây là **ví dụ minh họa keyset với `_id` kiểu String BSON đúng như dữ liệu lab**. Nếu production dùng `ObjectId` hoặc ID kiểu khác, hãy dùng đúng kiểu BSON/mapping khi so sánh; không giả định so sánh String ID là tương đương ObjectId ở mọi trường hợp.

Ưu điểm keyset:

- Tránh skip offset lớn.
- Phù hợp với sort key ổn định và index hỗ trợ.
- Khi tập dữ liệu tăng, thường giữ hiệu năng tốt hơn offset.

Giới hạn:

- Có thể khó “nhảy trực tiếp đến trang 500”.
- Phải giữ đầy đủ sort keys để tạo cursor.
- Các field sort dùng cho cursor nên **không null**, không đổi tùy tiện.
- Update `observedAt` hoặc xóa document giữa các request vẫn có thể ảnh hưởng kết quả.
- Cursor nên có encoding/validation chống giả mạo hoặc nhúng query filter/tenant để tránh chuyển cursor giữa tenant khác.

Spring Data MongoDB còn hỗ trợ API **ScrollPosition/KeysetScrollPosition** ở những phiên bản phù hợp; nếu dùng API đó, đọc JavaDocs chính xác theo version và kiểm thử mapping/id sort. Ví dụ trên dùng Criteria thông thường để dễ nhìn thấy điều kiện.

### 12.3. Đừng dùng skip để “đánh dấu đã poll”

Một số người viết inbound source theo kiểu:

~~~text
Poll #1: skip=0, limit=50
Poll #2: skip=50, limit=50
Poll #3: skip=100, limit=50
~~~

Cách này **không an toàn** nếu các document bị xử lý, cập nhật status hoặc xóa khỏi tập khớp query giữa các lần poll: vị trí thay đổi và bạn có thể bỏ sót document. Với work queue, hãy dùng **claim/lease** hoặc một checkpoint/keyset có semantics được định nghĩa và phục hồi được.

## 13. Tối ưu index theo filter + sort

Giả sử worker query:

~~~text
Filter: tenantId = tenant-a, status = NEW
Sort:   observedAt ASC, _id ASC
Limit:  50
Fields: _id, tenantId, deviceId, sequence, observedAt
~~~

Một index gợi ý trong lab:

~~~javascript
db.telemetry_events.createIndex({
  tenantId: 1,
  status: 1,
  observedAt: 1,
  _id: 1
})
~~~

Nó có thể hỗ trợ lọc theo equality trên `tenantId`/`status` và sort theo `observedAt`/`_id`. Tuy nhiên, hiệu quả thực tế phụ thuộc dữ liệu, cardinality, MongoDB version và plan; cần dùng `explain` thay vì kết luận chỉ vì thấy index tồn tại.

Trong mongosh:

~~~javascript
db.telemetry_events.find(
  { tenantId: "tenant-a", status: "NEW" },
  { _id: 1, tenantId: 1, deviceId: 1,
    sequence: 1, observedAt: 1 }
).sort({ observedAt: 1, _id: 1 })
 .limit(50)
 .explain("executionStats")
~~~

Quan sát các đại lượng như `totalDocsExamined`, `totalKeysExamined`, số document trả về và các stage, đồng thời so sánh khi query chạy với dữ liệu có kích thước/độ phân bố thực tế.

### 13.1. Projection không mặc nhiên tạo covered query

Query trên có projection `deviceId`/`sequence` nhưng index gợi ý chưa chứa những field đó. MongoDB có thể phải đọc document đầy đủ để lấy các field còn thiếu. Nếu muốn **covered query**, cần xem xét index chứa đủ các field filter/sort/projection và cách index multikey/collation ảnh hưởng; index quá rộng lại tăng chi phí ghi và dung lượng.

**Không tạo index cho mọi tổ hợp field chỉ để “bao phủ”** nếu workload không chứng minh lợi ích. Hãy đánh đổi tốc độ đọc, tốc độ ghi, RAM và chi phí quản trị.

### 13.2. Sort theo field thiếu hoặc null

Khi một số document thiếu `observedAt`, sort và keyset semantics sẽ khó ổn định. Trong một pipeline telemetry quan trọng, nên validate các field dùng cho sort và cursor trước khi lưu; cân nhắc index partial, xử lý schema migration hoặc chính sách cho bản ghi legacy.

### 13.3. Collation và kiểu so sánh

Sort theo String có thể thay đổi theo collation/case sensitivity. Các giá trị `_id` trong lab có dạng `evt-101`, phù hợp so sánh từ điển có kiểm soát; nhưng nếu dữ liệu production dùng ID hỗn hợp kiểu String/ObjectId, hãy quy định một schema nhất quán trước khi dùng keyset cursor.

## 14. Polling an toàn: sort + limit không giải quyết duplicate

Có một hiểu nhầm phổ biến:

> “Đã sort theo thời gian và limit 50 rồi, mỗi poll sẽ tự lấy 50 job tiếp theo.”

**Sai nếu query không đổi điều kiện hoặc không thay đổi trạng thái.** MongoDB không ghi nhớ danh sách document đã trả về ở những lần `find()` độc lập. Source lặp lại query sẽ nhận lại những document vẫn còn khớp.

~~~mermaid
flowchart TD
    A["Poller"] --> Q["find(status=NEW, sort, limit=50)"]
    Q --> R["50 docs"]
    R --> M["Message<List<T>>"]
    M --> H{"Có claim/ACK không?"}
    H -->|"Không"| Q
    H -->|"Có + hoàn tất"| U["DB state thay đổi"]
    U --> N["Query tiếp có thể chọn batch khác"]
~~~

### 14.1. updateExpression không phải ACK nghiệp vụ

MongoDB inbound adapter có thể được cấu hình update document vừa đọc. Ví dụ chuyển từ `NEW` sang `CLAIMED`:

~~~java
import org.springframework.data.mongodb.core.query.Update;

MongoDb.inboundChannelAdapter(
        mongoOperations, "{ 'status': 'NEW' }")
    .collectionName("telemetry_events")
    .entityClass(TelemetryEvent.class)
    .update(new Update().set("status", "CLAIMED"));
~~~

**Đây chỉ là đoạn builder**, cần gắn vào flow có poller. Nó cho thấy cách hạn chế việc document vẫn khớp query ở lần sau; nó **không bảo đảm downstream đã commit** và không tự biến query+update thành thao tác claim nguyên tử giữa nhiều worker.

### 14.2. Khi có hai worker

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant D as MongoDB
    A->>D: find(status=NEW).sort(...).limit(50)
    B->>D: find(status=NEW).sort(...).limit(50)
    D-->>A: evt-101..evt-150
    D-->>B: evt-101..evt-150
    Note over A,B: Cả hai có thể xử lý cùng một tập
~~~

Giải pháp production khi cần độc quyền: **atomic claim** trên từng document (thường `findAndModify` với điều kiện status/lease), owner/version, lease expiration, retry/backoff, idempotency key và state DONE chỉ sau khi business operation hoàn tất.

### 14.3. Projection phải giữ ID để hoàn tất công việc

Nếu downstream cần đánh dấu `DONE` theo `_id`, projection phải giữ ID. Bỏ `_id` vì “tiết kiệm bytes” có thể khiến handler không biết document nào cần ACK hoặc đối chiếu duplicate.

### 14.4. Sự kiện thay đổi trong lúc phân trang

Nếu dùng offset pagination để quét tập `NEW` rồi chuyển từng document sang DONE, tập kết quả co lại và `skip` ở poll sau sẽ bỏ qua document. Với work queue, **đừng tăng skip như checkpoint**. Dùng claim + query lại tập NEW/RETRY hoặc keyset bền với điều kiện rõ ràng, tùy mô hình nghiệp vụ.

## 15. XML: query-expression trả Query có fields, sort, limit

Spring Integration MongoDB XML cho phép `query-expression` trả một Spring Data `Query`. Không phải mọi tùy chọn như `fields/sort/limit` đều là XML attribute riêng của inbound adapter; có thể định nghĩa trong Query object.

Ví dụ bean policy:

~~~java
package example.mongodb;

import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Component;

@Component("mongoReadPlan")
public class MongoReadPlan {

    public Query queryForPoll() {
        return MongoReadQueries.inboxBatch("tenant-a", 50);
    }
}
~~~

XML inbound adapter:

~~~xml
<!-- XML có namespace int và int-mongodb theo phiên bản -->
<int:channel id="inboxBatchResults"/>

<int-mongodb:inbound-channel-adapter
        id="mongoBoundedInbound"
        channel="inboxBatchResults"
        mongo-template="mongoTemplate"
        collection-name="telemetry_events"
        query-expression="@mongoReadPlan.queryForPoll()"
        entity-class="example.mongodb.TelemetrySummary">
    <int:poller fixed-delay="5000"
                max-messages-per-poll="1"/>
</int-mongodb:inbound-channel-adapter>
~~~

Trong đoạn XML này, channel đầu ra nhận **`Message<List<TelemetrySummary>>`** khi có kết quả; nếu handler muốn từng event, thêm splitter bên ngoài hoặc triển khai handler phù hợp.

**Chọn một trong `query` và `query-expression`**. Nếu đã dùng query-expression để tạo Query, đừng đồng thời đặt `query="{...}"` và mong framework tự gộp hai truy vấn.

### 15.1. XML outbound gateway cũng có query-expression

Ví dụ khi request đã là DTO hợp lệ:

~~~xml
<int:channel id="mongoSearchRequests"/>
<int:channel id="mongoSearchReplies">
    <int:queue capacity="16"/>
</int:channel>

<int-mongodb:outbound-gateway
        id="mongoSearchGateway"
        request-channel="mongoSearchRequests"
        reply-channel="mongoSearchReplies"
        mongo-template="mongoTemplate"
        collection-name="telemetry_events"
        query-expression="@mongoReadQueryPolicy.forRequest(payload)"
        entity-class="example.mongodb.TelemetrySummary"/>
~~~

Bean `mongoReadQueryPolicy` cần tồn tại; `forRequest(payload)` trả Query có filter/projection/sort/limit. Đây là **flow request/reply với reply queue tĩnh để minh họa**, không phải mặc định an toàn cho nhiều HTTP requests đồng thời. Nếu nhiều caller, dùng temporary reply channel do `@MessagingGateway` tạo hoặc một cơ chế correlation rõ ràng.

## 16. Kiểm thử query builder mà không cần MongoDB

### 16.1. Unit test fields/sort/limit và tenant condition

JUnit 5:

~~~java
package example.mongodb;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.query.Query;

import static org.junit.jupiter.api.Assertions.*;

class MongoReadQueriesTest {

    @Test
    void inboxQueryHasRequiredLimitsAndFields() {
        Query query = MongoReadQueries.inboxBatch(
                "tenant-a", 50);

        Document filter = query.getQueryObject();
        Document projection = query.getFieldsObject();
        Document sort = query.getSortObject();

        assertEquals("tenant-a",
                filter.getString("tenantId"));
        assertEquals("NEW",
                filter.getString("status"));
        assertEquals(50, query.getLimit());

        assertEquals(1, projection.getInteger("deviceId"));
        assertEquals(1, projection.getInteger("sequence"));
        assertFalse(projection.containsKey("rawPayload"));

        assertEquals(1, sort.getInteger("observedAt"));
        assertEquals(1, sort.getInteger("_id"));
    }

    @Test
    void queryRejectsInvalidBatchLimit() {
        assertThrows(IllegalArgumentException.class,
            () -> MongoReadQueries.inboxBatch("tenant-a", 0));
        assertThrows(IllegalArgumentException.class,
            () -> MongoReadQueries.inboxBatch("tenant-a", 101));
    }

    @Test
    void searchQueryIsNewestFirst() {
        Query query = MongoReadQueries.recentByDevice(
            "tenant-a",
            new SearchTelemetryRequest("node-7", 20));

        assertEquals("node-7",
                query.getQueryObject().getString("deviceId"));
        assertEquals(20, query.getLimit());
        assertEquals(-1,
                query.getSortObject().getInteger("observedAt"));
        assertEquals(-1,
                query.getSortObject().getInteger("_id"));
    }
}
~~~

**Những assertion trên kiểm tra Query object trước khi Spring Data mapping Java property sang BSON field.** Nếu entity có `@Field("device_id")`, khi chạy MongoTemplate, query mapper có thể đổi tên field theo entity class. Muốn kiểm chứng field **trong MongoDB thật**, cần integration test.

### 16.2. Test thứ tự, batch size và projection ở database thật

Dùng MongoDB lab hoặc Testcontainers (nếu runner cho phép), seed các document có ID và thời gian xác định:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoOperations;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class MongoReadProjectionIntegrationTest {

    @Autowired
    MongoOperations mongoOperations;

    @Test
    void returnsBoundedOldestFirstSummaries() {
        List<TelemetrySummary> items = mongoOperations.find(
                MongoReadQueries.inboxBatch("tenant-a", 2),
                TelemetrySummary.class,
                "telemetry_events");

        assertEquals(2, items.size());

        assertEquals("evt-101", items.get(0).id());
        assertEquals("evt-102", items.get(1).id());

        assertEquals("tenant-a", items.get(0).tenantId());
        assertNotNull(items.get(0).observedAt());
    }
}
~~~

**Điều kiện:** test DB có đúng seed của mục 3 và không bị các test khác thay đổi. Nếu dùng một Testcontainers instance mới, phải tạo seed trong setup. Bài test không tự tạo MongoDB server; tuyệt đối không chạy trên production.

Muốn kiểm tra projection thật, có thể đọc raw `Document` theo Query đã cấu hình và xác nhận `rawPayload` vắng mặt, hoặc so sánh BSON được gửi/nhận theo test setup. Kiểm tra record `TelemetrySummary` không có property rawPayload **chưa đủ** để khẳng định MongoDB projection đang loại field khỏi network response; phải assert `Query.fields()` hoặc raw result.

### 16.3. Test outbound gateway theo từng request

Với `TelemetrySearchApi` từ mục 11:

~~~java
@Autowired
TelemetrySearchApi searchApi;

@Test
void searchRespectsLimitAndTenantScope() {
    List<TelemetrySummary> results = searchApi.recent(
            new SearchTelemetryRequest("node-7", 2));

    assertTrue(results.size() <= 2);
    assertTrue(results.stream().allMatch(
        item -> "tenant-a".equals(item.tenantId())
                && "node-7".equals(item.deviceId())));
}
~~~

Đây là **fragment đặt trong class test có Spring context và test DB đã seed**. Để tránh false positive, thêm `assertFalse(results.isEmpty())` hoặc assert ID được seed; chỉ `allMatch` trên list rỗng sẽ trả true và có thể che lỗi wiring.

### 16.4. Test inbound polling qua QueueChannel

Cấu hình một test-only flow:

~~~text
MongoDB test collection
   -> MongoDbMessageSource + Poller
   -> Message<List<TelemetrySummary>>
   -> Splitter
   -> QueueChannel test sink
   -> JUnit receive(timeout)
~~~

Các assertion nên bao gồm:

1. Đợi message bằng `receive(5000)` thay vì sleep cố định.
2. Assert payload type `TelemetrySummary` sau splitter.
3. Assert đúng ID/tenant/sequence/timestamp.
4. Assert header `MongoHeaders.COLLECTION_NAME` phù hợp.
5. Khi có 60 NEW documents và limit=50, xác minh **một query** trả không quá 50.
6. Không có result thì source không tự tạo payload null.
7. Không bật hai poller cùng query test data nếu bạn muốn kết quả ổn định.
8. Nếu đang test `Query.limit`, không để upstream update status hoặc data change ảnh hưởng assertion.
9. Dùng test collection riêng, dừng poller trước cleanup.
10. Thử lặp hai chu kỳ để phát hiện re-poll khi không claim.

## 17. Các lỗi thường gặp

| Lỗi / triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `limit(50)` mà handler nhận 50 messages | Splitter biến một List thành 50 Messages | Đúng contract; phân biệt document với source message |
| `maxMessagesPerPoll(1)` nhưng tải nhiều dữ liệu | Một find() trả List lớn | Đặt `Query.limit` |
| `limit(0)` trả rất nhiều document | 0 không phải “trả 0” trong API | Validate n >= 1 |
| Chỉ sort theo observedAt, kết quả đảo vị trí | Nhiều document có cùng timestamp | Thêm tie-break `_id` |
| Sort mới nhất nhưng thực tế random | Thiếu `with(Sort)` trong query cuối | Unit test `getSortObject` |
| Java entity bị thiếu field | Projection không lấy field đó | DTO projection riêng hoặc lấy đủ |
| Save entity projection làm mất dữ liệu | Ghi đè document thiếu field | Dùng partial update, không save mù |
| Query có tenant filter nhưng test không thấy | Sai DB/collection hoặc field name mapping | Kiểm tra MongoOperations, Query và seed |
| Query trả List lớn dù poller chậm | Poller không giới hạn query result | Projection + limit + bounded downstream |
| Skip pagination bị sót record | Dataset thay đổi giữa các trang | Keyset/claim/checkpoint phù hợp |
| Keyset mất kết quả khi sort key null | Điều kiện cursor không xử lý thiếu field | Validate/migrate sort keys |
| Không trả _id | Projection loại trừ id | Giữ id nếu cần dedup/ACK |
| Query index không dùng | Index không phù hợp filter/sort/collation | `explain` trên data test gần thực |
| Outbound gateway timeout | Query nặng hoặc reply channel sai | Query limit/index/timeouts/correlation |
| Poll đọc lặp 50 document | Chưa cập nhật state/claim | Claim/lease/idempotency |
| Nhiều worker xử lý trùng | Cùng query NEW trước update | Atomic claim theo owner/version |
| App tăng RAM | List, rawPayload và queue lớn | Fields projection, giảm batch, bounded queue |
| Data tenant khác xuất hiện | Filter tenant thiếu, authorization yếu | Server-side tenant scope + test bảo mật |

Luôn khoanh vùng theo thứ tự:

~~~text
Business request / Poller
   -> Query builder (filter + fields + sort + limit)
   -> MongoOperations / MongoTemplate
   -> MongoDB database & collection
   -> find/findOne result
   -> MongoDbMessageSource / MongoDbOutboundGateway
   -> Message payload/headers
   -> Splitter / channel / handler
~~~

Không kết luận “MongoDB trả thiếu dữ liệu” trước khi kiểm tra projection. Không kết luận “Spring Integration tạo trùng” trước khi kiểm tra query có lặp lại các document còn `NEW`.

## 18. Vận hành: hiệu năng, lỗi, timeout và bảo mật

### 18.1. Đo đúng số lượng và độ trễ

Các metric gợi ý (cần tự instrument hoặc map từ hệ thống monitoring):

| Metric | Dùng để biết |
|---|---|
| `mongo_query_runs_total` | Số lần query thực hiện |
| `mongo_query_result_documents` | Số document trả về mỗi query |
| `mongo_query_projection_bytes` | Dung lượng dữ liệu đọc/trao đổi theo observation phù hợp |
| `mongo_query_latency_seconds` | Query duration |
| `mongo_query_limit_rejected_total` | Request limit vượt policy |
| `mongo_query_timeout_total` | Query/driver timeout |
| `mongo_inbound_source_messages_total` | Số Message<List<T>> từ source |
| `mongo_splitter_messages_total` | Số Message<T> sau splitter |
| `mongo_inbound_empty_polls_total` | Query không có result |
| `mongo_gateway_requests_total` | Request/reply workload |
| `mongo_index_scan_ratio` | Tình trạng query scan cần đo |
| `mongo_inbox_oldest_age_seconds` | Tuổi event cũ nhất chưa xử lý |
| `mongo_claim_conflicts_total` | Tranh chấp claim đa worker |

**Không nhầm số source message và số document.** Một source message có thể mang List 50 phần tử; số messages sau splitter khác trước splitter.

### 18.2. Timeout đúng tầng

- `Pollers.fixedDelay(5000)`: lịch poll, **không phải query timeout**.
- `QueueChannel.receive(5000)` trong test: JUnit đợi Message, **không giới hạn thời gian MongoDB query**.
- `@Gateway(replyTimeout=...)`: caller đợi reply, **không hủy mọi DB operation ngay khi hết hạn**.
- MongoDB driver/server selection/socket timeout và query maxTime: chi phối DB I/O thực sự.
- Business downstream timeout: HTTP/Kafka/JMS/AMQP operation có deadline riêng.

Khi xuất hiện lỗi MongoDB query, nó có thể xảy ra **trước khi một Message được tạo**. Một query không có dữ liệu thường chỉ là empty poll, không phải `ErrorMessage`. Lỗi handler sau splitter đi theo error propagation của channel/poller (đồng bộ hoặc bất đồng bộ).

### 18.3. Bảo mật

- **Không cho client tự gửi MongoDB raw Query/JSON hoặc SpEL string** để được đánh giá trong server.
- Đưa điều kiện tenant/owner bắt buộc vào Criteria từ identity đã xác thực.
- Đặt cap cho limit, offset, số query song song và time budget.
- Projection chỉ trả field được phép; **không xem projection là thay thế RBAC**.
- Collection/database có allowlist, role least privilege, TLS và secret management.
- Log query template ID, count, duration, collection logic và error class; không dump thông tin nhạy cảm.
- Với tracing/metrics, tránh label cardinality cao như từng `eventId` hoặc device ID.
- Với concurrency, kiểm tra retry/idempotency và tình trạng dữ liệu thiếu/trùng do các worker.
- Thử `explain` và load test trên dataset test đủ lớn thay vì giả định một query index đã tối ưu.

### 18.4. Graceful shutdown và backpressure

Nếu polling source trả 50 document và splitter phát messages vào ExecutorChannel/QueueChannel, một số message có thể **chưa được xử lý xong** khi endpoint stop. Cần quy trình dừng producer, drain việc đang chạy có deadline, giữ state/lease hợp lệ và phục hồi sau restart. Queue in-memory không tự bền; nếu không thể mất event, dùng durable source/queue và idempotent handler.

## 19. Bài thực hành tổng hợp

Bài tập: thiết kế dịch vụ **MongoDB → Spring Integration → Kafka/JMS/HTTP/DB** với query giới hạn, đồng thời tạo API tra cứu lịch sử thiết bị theo request.

### Phần A — Query và projection

1. Seed dữ liệu năm document của mục 3.
2. Truy vấn `tenant-a` / `status=NEW` theo mongosh.
3. Dùng `query.fields().include(...)` để chỉ lấy tenantId, deviceId, sequence, observedAt và `_id` mặc định.
4. So sánh kết quả khi `exclude("rawPayload")` theo **query riêng**.
5. Thử include một field rồi exclude một field khác không phải ID; giải thích vì sao projection không hợp lệ.
6. Tạo `TelemetrySummary`, kiểm tra mapping. Thảo luận vì sao không save một partial entity.

### Phần B — Sort và limit

1. Sort theo `observedAt ASC`, quan sát hai document cùng timestamp.
2. Bổ sung `_id ASC` và assert thứ tự `evt-101`, `evt-102`, `evt-103`.
3. Đổi sang `DESC` để lấy mới nhất trước.
4. Query `limit(2)`, assert đúng hai document và ID mong đợi.
5. Thử input limit=0 và limit=10000, xác minh validation từ chối.
6. Tạo index trên `tenantId/status/observedAt/_id` và so sánh `explain`/latency.

### Phần C — Spring Integration inbound

1. Dùng `MongoDb.inboundChannelAdapter(mongoDatabaseFactory, Query)` với `limit(50)`, `Pollers.fixedDelay(5000)`.
2. Assert một `Message<List<TelemetrySummary>>` trước splitter và các messages riêng sau splitter.
3. Tạo test sink bằng `QueueChannel`, chờ bằng timeout hữu hạn và assert ID/headers.
4. Seed 200 document NEW, giải thích vì sao maxMessagesPerPoll=1 không có nghĩa một document.
5. Cho poller chạy hai chu kỳ mà không update state; xác nhận sự kiện có thể lặp.
6. Đề xuất claim/lease, retry, idempotency và batch policy để không đọc mãi cùng dữ liệu.

### Phần D — Gateway và phân trang

1. Định nghĩa `SearchTelemetryRequest` có limit 1..100.
2. Dùng `MongoReadQueries.recentByDevice(...)` trong `queryFunction` của outbound gateway.
3. Tạo `@MessagingGateway` trả `List<TelemetrySummary>`.
4. Thử hai request với device khác nhau, assert kết quả chỉ thuộc tenant được phép.
5. Thử offset pagination với skip/limit; chèn document giữa các page để quan sát rủi ro.
6. Thử keyset theo `(observedAt, _id)` và kiểm tra cursor khi timestamps trùng.
7. Đề xuất DTO response không chứa rawPayload/field nhạy cảm.

### Phần E — Vận hành và độ tin cậy

1. Tắt MongoDB test instance để quan sát query error khác empty poll.
2. Kiểm tra driver timeout, reply timeout, queue receive timeout là ba loại riêng.
3. Chạy hai worker cùng đọc NEW để giải thích duplicate dù có sort/limit.
4. Mô phỏng crash sau khi claim nhưng trước business commit; đề xuất lease và recovery.
5. Đặt metrics document count, source message count, latency, empty poll, limit reject và retry.
6. Đề xuất graceful shutdown, bounded queue và cách đảm bảo không ACK nguồn trước khi đích xử lý xong.

**Câu hỏi tự đánh giá:**

- Filter, projection, sort và limit khác nhau thế nào?
- Vì sao chỉ dùng `maxMessagesPerPoll(1)` không giới hạn số document?
- Trong projection include, `_id` có được trả về mặc định không?
- Có được include field A nhưng exclude field B khác `_id` không?
- Khi dùng entity có `@Field("device_id")`, Query dựa trên tên property nào?
- Vì sao đọc partial entity rồi save trở lại có nguy cơ mất field?
- Khi timestamps trùng, vì sao cần thêm sort theo `_id`?
- `limit(0)` có phải luôn đồng nghĩa không trả document không?
- Vì sao `Query.limit(50)` không ngăn polling đọc lại 50 bản ghi?
- `skip + limit` có thể bỏ sót bản ghi khi dataset thay đổi không?
- Keyset cursor cần giữ những sort fields nào?
- Tại sao một query projection ít field chưa chắc là covered query?
- Outbound gateway khác inbound polling source ở điểm nào?
- Khi nào nên dùng atomic claim thay vì sort + limit?
- Làm sao test đúng tenant, ID, số lượng, thứ tự và field được trả?

## 20. Tài liệu tham khảo

- [Spring Data MongoDB Reference — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): `Query`, `Criteria`, `fields()`, `with(Sort)`, `limit`, `skip` và projections.
- [Spring Data MongoDB Reference — Repository Query Methods / Scrolling](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): offset/keyset scrolling, pagination và sort.
- [Spring Integration Reference — MongoDB Support](https://docs.spring.io/spring-integration/reference/mongodb.html): MongoDB inbound polling, outbound gateway, query-expression, collection và transaction synchronization.
- [Spring Integration API — MongoDb DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/dsl/MongoDb.html): overload `inboundChannelAdapter(MongoDatabaseFactory, Query)` và `outboundGateway(MongoOperations)`.
- [Spring Integration API — MongoDbMessageSource](https://docs.spring.io/spring-integration/api/org/springframework/integration/mongodb/inbound/MongoDbMessageSource.html): `expectSingleResult`, list payload và empty query.
- [MongoDB Manual — Project Fields to Return from Query](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/): inclusion/exclusion và ngoại lệ `_id`.
- [MongoDB Manual — Query Optimization](https://www.mongodb.com/docs/manual/core/query-optimization/): index, query plan và query performance.
- [MongoDB Manual — explain](https://www.mongodb.com/docs/manual/reference/method/cursor.explain/): xem execution plan và thống kê query.
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): poller, maxMessagesPerPoll và lifecycle.

## Kết luận

**Query fields, sort và limit** quyết định lần lượt **trường nào được trả về**, **thứ tự kết quả** và **số document tối đa** từ MongoDB. Khi ghép với `MongoDbMessageSource`, những tùy chọn này xác định kích thước và nội dung một `Message<List<T>>`; khi ghép với `MongoDbOutboundGateway`, chúng ràng buộc kết quả của từng request/reply. **`maxMessagesPerPoll` giới hạn số lần lấy Spring Message, không thay thế `Query.limit`.**

Trong **SPRING_INTEGRATION_ADAPTERS**, một truy vấn tốt phải có **tenant filter đúng quyền, fields projection phù hợp DTO, sort ổn định, limit dương có cap, index được đo bằng explain và timeout rõ ràng**. Song song, một pipeline polling bền vững vẫn phải có **claim/lease, retry, idempotency, error handling và shutdown/recovery**; sort + limit không tự đánh dấu document đã xử lý hoặc tạo exactly-once.
