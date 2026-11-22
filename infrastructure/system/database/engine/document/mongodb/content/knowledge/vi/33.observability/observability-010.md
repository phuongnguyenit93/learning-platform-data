# Bảo vệ dữ liệu nhạy cảm trong log, profiler và hệ thống giám sát MongoDB

Khi một ứng dụng MongoDB chạy chậm, nhóm vận hành thường tăng mức log, bật profiler, lấy `explain()`, bật command monitoring trong driver hoặc chuyển dữ liệu sang hệ thống APM. Những công cụ này cực kỳ hữu ích để xác định query chậm, lỗi kết nối và nút thắt tài nguyên. Nhưng chúng cũng có thể vô tình tạo ra **một bản sao của dữ liệu nhạy cảm ở nơi không phải database nghiệp vụ**.

Ví dụ, một lệnh truy vấn tìm khách hàng theo địa chỉ email có thể chứa email trong `filter`; một aggregation có thể chứa số định danh trong `$match`; lỗi xác thực có thể kèm tên tài khoản; một bản trace có thể mang nguyên connection string nếu ứng dụng gắn nó vào span attributes. Nếu dữ liệu này đi vào centralized logs, dashboard, ticket hỗ trợ hoặc một dịch vụ giám sát bên thứ ba, số người và hệ thống có thể đọc được nó thường lớn hơn nhiều so với số người có quyền đọc collection gốc.

Bài học thuộc chương **Quan sát hệ thống** trong module **Database Engine Document MongoDB**, tập trung vào cách **bảo vệ dữ liệu nhạy cảm trong log, database profiler và hệ thống giám sát** mà vẫn giữ được khả năng chẩn đoán hiệu năng và sự cố.

Sau bài học, bạn sẽ:

1. Nhận diện các đường dữ liệu có thể làm lộ PII, credentials, query literals và thông tin nội bộ.
2. Phân biệt diagnostic server log, `system.profile`, audit log, metrics, traces và application/driver logs.
3. Thiết kế logging theo hướng **data minimization**, dùng allowlist fields, redaction và sampling.
4. Hiểu cơ chế `security.redactClientLogData` và các giới hạn của biện pháp che log phía server.
5. Bật/quan sát/tắt profiler trong môi trường lab có kiểm soát, hiểu tác động hiệu năng và bảo mật.
6. Dùng MongoDB Java Sync Driver để ghi thông tin hiệu năng có ích mà không log nguyên BSON command.
7. Áp dụng RBAC, TLS, mã hóa lưu trữ, retention, xóa dữ liệu và quy trình phản ứng khi log bị lộ.
8. Xây checklist vận hành và đánh giá những đánh đổi giữa khả năng quan sát và mức độ phơi lộ dữ liệu.

> **Lưu ý an toàn:** mọi email, tenant ID, token và ví dụ query trong bài đều là dữ liệu giả lập. Không bật profiler mức cao, tăng debug logging hay xuất logs production để thực hành. Các tính năng MongoDB/Atlas có thể khác theo phiên bản, tier và loại deployment; kiểm tra tài liệu của hệ thống đang sử dụng trước khi cấu hình.

## 1. Tại sao “dữ liệu chỉ để debug” vẫn phải được bảo vệ?

Một document nghiệp vụ có thể được bảo vệ bởi database RBAC, firewall, TLS và cơ chế mã hóa, nhưng khi một dòng log chứa lại giá trị từ document, bản sao này chịu một vòng đời hoàn toàn khác:

```text
MongoDB collection (có database RBAC)
                  |
                  | Query / Command / Error
                  v
        Mongod diagnostic log
        system.profile / APM event
        Java application log
                  |
                  v
          Fluent Bit / Agent
                  |
                  v
       Central log / tracing vendor
                  |
         +--------+--------+
         |        |        |
      Dashboard  Alert   Export CSV
         |        |        |
         +--------+--------+
                  |
               Người đọc
```

Đường đi này mở ra những rủi ro:

- **Nhân bản bí mật:** một connection URI chứa password bị ghi vào log, rồi tiếp tục được đưa lên nhiều hệ thống.
- **Quyền rộng hơn:** đội hỗ trợ được xem dashboard nhưng không được phép đọc dữ liệu khách hàng trên MongoDB.
- **Thời hạn dài hơn:** collection gốc xóa một document, nhưng log/trace giữ bản sao thêm nhiều tháng.
- **Lưu trữ bên ngoài:** dữ liệu được gửi tới log SaaS ở một region hoặc nhà cung cấp chưa được phê duyệt.
- **Khó xóa triệt để:** cùng giá trị có thể tồn tại trong index tìm kiếm, cảnh báo, export và backup của hệ thống log.
- **Sai giả định về độ an toàn:** không log toàn bộ document nhưng vẫn lộ email, địa chỉ, mã khôi phục hoặc session token trong query predicate.

**Quyền truy cập log phải được xem là một loại quyền truy cập dữ liệu**, không phải đặc quyền vận hành vô hại.

## 2. Phân loại dữ liệu trước khi quyết định log cái gì

Không phải tất cả thông tin quan sát được đều có độ nhạy như nhau.

| Nhóm dữ liệu | Ví dụ | Cách xử lý gợi ý |
| --- | --- | --- |
| **Credentials và secrets** | Password, access token, API key, JWT, URI có user:password, private key | Không ghi vào log; nếu lộ thì thu hồi/rotate |
| **PII và định danh người dùng** | Email, số điện thoại, địa chỉ, CMND/CCCD, mã số cá nhân | Tránh ghi giá trị thô; chỉ dùng chỉ số tổng hợp/ID giả danh có kiểm soát |
| **Dữ liệu nghiệp vụ nhạy cảm** | Số dư, hồ sơ sức khỏe, nội dung tin nhắn, tài liệu nội bộ | Không đưa vào query logs/APM khi không cần |
| **Thông tin hệ thống nội bộ** | Hostname, IP private, namespace, tenant identifier, topology | Chỉ thu thập khi cần và giới hạn quyền |
| **Thông tin query shape** | Tên collection, loại lệnh, số field được lọc, duration, docs examined | Thường hữu ích cho performance nhưng vẫn xét tính nhạy cảm của field names |
| **Metrics tổng hợp** | Connection count, CPU %, query latency histogram, replication lag | Ưu tiên cho giám sát thường xuyên |
| **Trace correlation** | Opaque request ID, service name, span duration | Hữu ích nếu ID không chứa dữ liệu nhạy cảm |

### Bốn cấp phân loại tham khảo

```text
PUBLIC         dữ liệu công khai, không định danh
INTERNAL       kiến trúc và trạng thái hệ thống
CONFIDENTIAL   dữ liệu khách hàng/nghiệp vụ bị hạn chế
SECRET         passwords, tokens, keys, private credentials
```

Đây là mô hình minh họa; tổ chức có thể dùng hệ phân loại khác. Dữ liệu `SECRET` thường phải **không xuất hiện trong log ngay từ đầu**, thay vì dựa vào regex để xóa sau khi đã gửi đi.

### Một chuỗi dễ bị bỏ qua: MongoDB connection string

```text
mongodb+srv://app_user:<password>@cluster.example.mongodb.net/orders
```

Nếu một exception hoặc debug message in nguyên URI, thông tin account, hostname và có thể cả password được sao chép vào log. Không in `MONGODB_URI`, không gắn URI nguyên văn vào trace attributes và không đưa secrets vào các field `comment` của MongoDB commands.

## 3. Các nguồn observability trong MongoDB khác nhau ra sao?

| Nguồn | Nội dung chính | Nguy cơ nhạy cảm |
| --- | --- | --- |
| **MongoDB diagnostic log** | Startup, kết nối, lỗi, slow operations, trạng thái server | Query command/field/value tùy event và cấu hình |
| **Database profiler** `system.profile` | Thông tin operation đã được profile, duration, plan, command | Có thể lưu **query literals, filter, pipeline và identifiers** |
| **Audit log** | Hành động cần audit như authentication/authorization/DDL theo capability | Identity, namespace, event parameters |
| **Driver command monitoring** | Command started/succeeded/failed events trong ứng dụng | Started event có thể chứa command BSON với giá trị thật |
| **Application logs** | Request, exception, business operations | Email, token, payload, query filter do lập trình viên log |
| **Metrics** | Counts, gauges, latency, cache, locks, queue/replication | Metric labels có thể chứa tenant/user ID nếu thiết kế sai |
| **Distributed tracing/APM** | Spans, attributes, events, error details | Raw query, database name, URL, user metadata hoặc exception |
| **Query explain/current operations** | Query plan, operation state, statistics | Có thể hiển thị filter/query values và namespace |
| **Export/backup/crash dump** | Bản sao từ các nguồn trên hoặc bộ nhớ | Có thể chứa toàn bộ dữ liệu log lẫn secrets |

**Không nên dùng chung một policy “cho phép ghi mọi thứ ở DEBUG trong 7 ngày”** cho các nguồn này. Mỗi nguồn cần owner, cấp truy cập, retention, cách kiểm soát và phương án xử lý sự cố.

## 4. Ba mục tiêu thường mâu thuẫn

Khi thiết kế observability, cần cân bằng:

1. **Chẩn đoán tốt:** có đủ context để xác định query chậm, collection/index liên quan, client và thời điểm.
2. **Giảm dữ liệu nhạy cảm:** không thu thập email, password, token, nội dung document nếu không cần.
3. **Giảm chi phí/tác động:** log volume, profiler overhead và chi phí lưu trữ/egress không vượt budget.

Chẳng hạn, muốn biết một truy vấn chậm vì quét nhiều document, nhóm vận hành thường **không cần biết email cụ thể được tìm**. Những trường hữu ích hơn là:

```text
operation: find
collection: customers
duration_ms: 820
docs_examined: 210000
keys_examined: 0
plan_summary: COLLSCAN
app_component: customer-api
request_id: opaque-7a31
```

Các chỉ số này có thể đủ để phát hiện thiếu index. Trong khi đó:

```text
filter: {email: "customer.real@example.com"}
access_token: "eyJ..."
```

không cần cho phần lớn hoạt động theo dõi performance và tạo rủi ro mới nếu bị ghi ra log.

## 5. Query có thể làm lộ PII dù response không chứa PII

Xét collection `customers` có document:

```javascript
{
  _id: "CUS-01",
  email: "demo-user@example.invalid",
  phone: "+00-000-000-000",
  status: "ACTIVE"
}
```

Một backend tìm khách hàng:

```javascript
db.customers.findOne({
  email: "demo-user@example.invalid"
});
```

Response có thể chỉ dùng `_id`, nhưng **giá trị email đã nằm trong command gửi tới database**. Nếu profiler, debug driver hoặc tracing ghi BSON command, email có thể xuất hiện trong telemetry.

Các nơi query literal có thể xuất hiện:

- Equality và range predicates như `email`, `phone`, `accountNo`, `createdAt`.
- Aggregation `$match`, `$lookup`, `$project` chứa dữ liệu literal.
- Update `$set` với nội dung tài khoản hoặc session metadata.
- Error messages trả về từ các constraint/validation failures.
- `comment` do ứng dụng gửi trong command.
- HTTP URL, request body hoặc application debug statements.

### “Không log response” chưa đủ

Nếu ứng dụng không ghi document trả về nhưng log:

```java
log.debug("Mongo filter: {}", filter.toBsonDocument());
```

thì truy vấn theo email vẫn có nguy cơ lộ email. Một policy tốt phải xét cả **request-side query data**, không chỉ response hoặc database rows.

## 6. Query shape và query literal là hai khái niệm khác nhau

**Query literal** là giá trị cụ thể được gửi trong một truy vấn:

```javascript
{ email: "demo-user@example.invalid", status: "ACTIVE" }
```

**Query shape** biểu diễn dạng/cấu trúc truy vấn, không cần giữ nguyên tất cả giá trị:

```text
find customers
filter keys: email == ?, status == ?
sort: none
limit: 1
```

Khả năng đo query shape giúp:

- Nhóm các lần chạy của cùng mẫu query.
- So p50/p95/p99 latency theo mẫu.
- Nhận diện thiếu index hay thay đổi query plan.
- Giảm nhu cầu lưu nhiều giá trị PII.

Tuy nhiên, **shape cũng có thể nhạy cảm**: tên field, collection, tenant-specific namespaces hoặc truy vấn liên quan dữ liệu sức khỏe có thể tiết lộ cấu trúc nội bộ. Cần giới hạn quyền tới shape metadata, dù không còn email gốc.

### Không tự phát minh query fingerprint thiếu ổn định

Thay query values bằng `?` rồi hash toàn chuỗi một cách tùy ý có thể tạo những fingerprint không ổn định theo field order, BSON type, serialization hoặc phiên bản driver. Nếu server/observability platform cung cấp query shape identifier được hỗ trợ, ưu tiên dùng nó. Dù vậy, phải xác nhận ý nghĩa, tính ổn định và quyền xem identifiers theo phiên bản.

## 7. MongoDB diagnostic log có thể chứa gì?

MongoDB diagnostic log có thể ghi:

- Lúc tiến trình khởi động, thay đổi trạng thái và thông tin môi trường.
- Kết nối/đóng kết nối, client metadata và lỗi mạng.
- Replication, sharding, storage engine và các lỗi vận hành.
- Slow operations, tùy diagnostic verbosity, threshold và loại thao tác.
- Thông tin phục vụ troubleshooting.

**Không mặc định server log chỉ chứa metadata vô hại.** Một số dòng log có thể chứa command data hoặc phần thông tin liên quan đến query. Các trường và mức chi tiết phụ thuộc MongoDB server version, command, profiling/logging configuration và tính năng redaction được hỗ trợ.

### Ví dụ dòng log được tối giản

```json
{
  "t": "2026-11-14T08:01:00.000Z",
  "s": "I",
  "c": "COMMAND",
  "msg": "Slow query",
  "attr": {
    "ns": "shop_app.orders",
    "durationMillis": 820,
    "planSummary": "COLLSCAN",
    "docsExamined": 210000
  }
}
```

Đây là **minh họa cấu trúc thông tin** chứ không phải một mẫu log chuẩn áp dụng y hệt mọi phiên bản. Trong log thực có thể có thêm command, filter hoặc các thuộc tính khác chứa dữ liệu nhạy cảm.

### Verbosity càng cao không phải lúc nào càng tốt

Diagnostic verbosity cao có thể:

- Tăng khối lượng log và I/O.
- Tăng chi phí ingest vào hệ thống log tập trung.
- Thu thập nhiều context chưa được phân loại.
- Làm dữ liệu nhạy cảm xuất hiện ở nhiều dòng hơn.
- Che lấp signal quan trọng bằng noise.

Một biện pháp tốt là chỉ tăng logging **theo mục tiêu, trong thời gian giới hạn, trên hệ thống được phép**, rồi trở về baseline và xử lý artifacts đã thu thập theo retention.

## 8. Server-side redaction: `security.redactClientLogData`

Một số edition/deployment MongoDB hỗ trợ tùy chọn bảo mật như `security.redactClientLogData` để **che một phần dữ liệu liên quan đến client operations** trước khi ghi diagnostic server logs.

Ví dụ minh họa configuration option, **chỉ áp dụng khi deployment/version hỗ trợ**:

```yaml
security:
  authorization: enabled
  redactClientLogData: true
```

Mục đích của option là giảm khả năng log phía server chứa những giá trị nhạy cảm từ operations. Nhưng cần phân biệt:

1. **Phạm vi giới hạn:** không bảo đảm mọi message, stack trace, audit record, driver log hoặc exporter đều được che.
2. **Không thay đổi dữ liệu lưu trong collection:** tùy chọn log không sửa document hoặc lệnh query thực.
3. **Không tự bảo vệ `system.profile` và mọi nguồn telemetry khác:** mỗi nguồn phải được kiểm soát riêng.
4. **Không thay thế quyền truy cập:** người có quyền đọc log vẫn có thể thấy metadata nội bộ.
5. **Có thể giảm chi tiết phục vụ debug:** một số thông tin nguyên văn không còn xuất hiện.

**Không khẳng định option tồn tại và có hành vi giống nhau trên MongoDB Community, Enterprise hoặc mọi tier Atlas.** Trước khi triển khai, đối chiếu chính xác tài liệu server/Atlas đang sử dụng và thử trong môi trường có dữ liệu giả lập.

### Redaction không phải encryption

| Cơ chế | Tác dụng |
| --- | --- |
| Redaction | Bỏ/ẩn giá trị trước khi ghi hoặc hiển thị |
| Masking | Thay một phần giá trị để người xem khó nhận biết |
| Encryption in transit | Bảo vệ bytes trên mạng |
| Encryption at rest | Bảo vệ bytes trên phương tiện lưu trữ |
| RBAC | Giới hạn ai được truy cập |
| Retention/deletion | Hạn chế thời gian dữ liệu còn tồn tại |

Một log đã được mã hóa khi lưu trữ vẫn có thể hiển thị nguyên email cho người dùng có quyền giải mã. **Mã hóa không làm dữ liệu bớt nhạy cảm khi đã được đọc**.

## 9. Database profiler là gì?

MongoDB **database profiler** thu thập thông tin về các operations theo cấu hình profiling, thường được ghi vào collection hệ thống:

```text
<database>.system.profile
```

Ví dụ:

```text
shop_app.system.profile
```

Profiler giúp xem:

- Lệnh gì đã chạy, tại thời điểm nào.
- Mức latency của operation.
- Số documents/keys được examined trong những loại operation tương ứng.
- Plan summary và các chỉ số truy vấn khả dụng.
- Namespace/command information và client metadata theo version.

**Rủi ro:** profile document có thể chứa **command BSON hoặc literals** từ query. Vì vậy, `system.profile` phải được phân loại và quản lý như một **nguồn dữ liệu có thể chứa nội dung nhạy cảm**, không chỉ một bảng thống kê.

### Mẫu mô tả một profile record

```javascript
{
  ts: ISODate("2026-11-14T08:01:00Z"),
  ns: "shop_app.customers",
  op: "query",
  millis: 820,
  command: {
    find: "customers",
    filter: {
      email: "demo-user@example.invalid"
    }
  },
  docsExamined: 210000,
  planSummary: "COLLSCAN"
}
```

Đây là **mẫu khái niệm đã giản lược**. Fields cụ thể khác nhau theo loại operation và phiên bản MongoDB. Điều cần nhớ là **query predicate có thể nằm trong profile record**, dù bạn chỉ mở profiler để đo thời gian.

## 10. Các mức profiling và rủi ro

Database profiler thường có ba mức:

| Level | Ý nghĩa khái quát | Đánh giá |
| ---: | --- | --- |
| `0` | Không ghi profile records cho database theo chế độ profiling thông thường | Phù hợp baseline khi không cần profiler |
| `1` | Profile operations theo ngưỡng chậm/filter và sampling được hỗ trợ | Dùng có mục đích, giới hạn thời gian |
| `2` | Profile mọi operations trong phạm vi áp dụng | **Nguy cơ overhead và lộ dữ liệu lớn**, chỉ dùng rất có kiểm soát |

Một số server versions hỗ trợ **profile filter** và những tùy chọn chọn lọc hơn. Tên options và cách tương tác với `slowms`/sampling cần đối chiếu theo release thực tế.

### Level 0 không đồng nghĩa server ngừng mọi slow-operation logging

Khi tắt database profiler bằng level 0, MongoDB vẫn có thể ghi **diagnostic log** cho slow operations theo server configuration. Đây là **hai nguồn khác nhau**:

- `system.profile`: database profiler.
- Diagnostic log: log của tiến trình MongoDB, có thể chứa thông tin slow operations.

Tắt một nguồn không tự tắt hoặc xóa dữ liệu đã ghi ở nguồn còn lại.

### Profiling level 2 có gì đáng lo?

Ở level 2, lượng profile records có thể tăng theo mọi thao tác. Trên workload nhiều nghìn requests mỗi giây:

- Profiler có thể tạo chi phí ghi/I/O và tác động đến latency.
- Nhiều commands chứa query values sẽ được lưu.
- Người có quyền đọc `system.profile` có thể thấy thông tin không cần thiết.
- Bản dump/export hoặc ảnh chụp profiler dễ chứa dữ liệu nhạy cảm.

Không bật level 2 trên production theo mặc định chỉ để tìm một query chậm.

## 11. Quan sát profiling status bằng `mongosh`

Trên một **database lab được phép**, dùng:

```javascript
use mongo_observability_lab

db.getProfilingStatus();
```

Lệnh cho biết các thông số profiling mà phiên bản/deployment hỗ trợ. Một số môi trường Atlas/managed tiers có giới hạn quyền thay đổi hoặc cách thu thập riêng; không giả định mọi database user được phép chạy các lệnh này.

### Bật mức 1 có sampling trong lab

Ví dụ minh họa:

```javascript
db.setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.1
});
```

Ý tưởng:

- `1`: profile theo điều kiện slow operations.
- `slowms: 100`: ngưỡng chậm 100 ms trong ngữ cảnh cấu hình được hỗ trợ.
- `sampleRate: 0.1`: chỉ lấy một tỷ lệ thao tác theo hành vi server/version.

**Không coi sampling là “không bao giờ ghi PII”.** Dù chỉ profile 10% các operations đủ điều kiện, một bản ghi có thể vẫn chứa đúng giá trị nhạy cảm mà chính sách cấm lưu.

### Không thay đổi settings production tùy tiện

Các thông số slow-operation logging/profiling có thể ảnh hưởng những phần khác của tiến trình, không chỉ một collection. Cần lưu lại baseline của môi trường, hiểu phạm vi tác động và có phương án rollback. Sau bài tập lab, tắt profiling theo trạng thái ban đầu của lab:

```javascript
db.setProfilingLevel(0);
```

Trên production, **không mù quáng đặt level 0 nếu baseline vốn được quản lý ở level khác**, và không quên phục hồi những tham số `slowms`/sampling đã thay đổi. Dùng cấu hình vận hành đã được phê duyệt.

## 12. Đọc `system.profile` theo hướng giảm lộ thông tin

Trong lab:

```javascript
const lab = db.getSiblingDB("mongo_observability_lab");

lab.system.profile.find(
  {},
  {
    _id: 0,
    ts: 1,
    ns: 1,
    op: 1,
    millis: 1,
    planSummary: 1,
    docsExamined: 1,
    keysExamined: 1
  }
).sort({ ts: -1 }).limit(10);
```

Đây là **projection allowlist**: chỉ hiển thị các fields cần để phân tích hiệu năng. Không dùng:

```javascript
// Không nên in nguyên profile documents của production:
db.system.profile.find().forEach(printjson);
```

vì nó có thể in `command`, `filter` hoặc những fields nhạy cảm ra terminal history, ticket, shell capture hoặc log automation.

### Projection chỉ giảm dữ liệu được trả về, không xóa dữ liệu đã lưu

Đây là ranh giới cực kỳ quan trọng:

```text
Profile record trên disk:
  có thể có command/filter với PII
             |
             v
Query projection
             |
             v
Màn hình chỉ thấy ts, millis, ns, docsExamined
```

Projection giúp **không lan truyền thêm** thông tin nhạy cảm qua output, nhưng bytes gốc vẫn có thể nằm trong `system.profile`. Muốn bảo vệ dữ liệu khi lưu phải kiểm soát **việc thu thập, quyền đọc collection, retention và vị trí backup/export**.

### `system.profile` thường là capped collection

Profiler sử dụng collection hệ thống có cơ chế capped theo thiết kế/phiên bản MongoDB. Capped collection có giới hạn dung lượng và có thể ghi đè dữ liệu cũ theo vòng quay, nhưng **không phải một cam kết retention chính xác theo số ngày**. Không dựa vào kích thước capped collection để đảm bảo tài liệu chứa PII được xóa sau đúng N giờ.

Không tùy tiện drop/recreate `system.profile` để “dọn log” trên production: collection hệ thống có các quy tắc quản lý và tác động tới profiling. Cần theo quy trình chính thức cho bản server đang dùng.

## 13. Profiler và audit log không giống nhau

**Profiler** phục vụ phân tích hiệu năng/operations, còn **audit log** phục vụ theo dõi ai đã thực hiện những hành động nào theo audit policy và tính năng được hỗ trợ.

| Khía cạnh | Database profiler | Audit log |
| --- | --- | --- |
| Mục tiêu chính | Chẩn đoán hiệu năng/truy vấn | Theo dõi hành vi bảo mật và tuân thủ |
| Phạm vi thu thập | Theo level, filter, slowms, sampling | Theo audit configuration/filters |
| Nội dung | Operation timing, query/command/plan info | Auth, authz, DDL và events theo policy |
| Nguy cơ PII | Query literals, namespaces | Identity, event parameters, có thể metadata nhạy cảm |
| Quyền truy cập | Quyền đọc/kiểm soát profiling tương ứng | Thường quyền audit/security được giới hạn |
| Retention | Profiling collection và chính sách vận hành | Chính sách audit riêng, có thể yêu cầu giữ lâu |

Audit log support, destinations và cấu hình có thể khác giữa MongoDB Enterprise, Atlas và community deployments. **Không hứa mọi MongoDB deployment đều có cùng audit capability**.

Đối với sự cố bảo mật, audit log thường cần được bảo vệ trước hành vi sửa/xóa trái phép, trong khi profiler nên bật chọn lọc để tránh data exposure/performance overhead. Không dùng profiler thay thế một hệ audit tuân thủ.

## 14. MongoDB diagnostic log redaction không bảo vệ driver log

Ngay cả khi server đã cấu hình log redaction, ứng dụng vẫn có thể lộ dữ liệu **trước khi gửi lệnh**:

```java
Document filter = new Document(
    "email", "demo-user@example.invalid");

// Không phù hợp cho production:
logger.debug("Mongo query = {}", filter.toJson());
```

Thông tin này được in bởi **Java application logger**, không nằm trong phạm vi của tùy chọn redaction phía `mongod`.

Tương tự, một MongoDB driver có thể cung cấp **command monitoring events** phục vụ APM/debug. Nếu ứng dụng hoặc library tùy biến serialize toàn bộ `CommandStartedEvent.getCommand()`, query literals có thể đi vào log.

### Quy tắc thực tế

- Không log toàn bộ BSON query/aggregation pipelines.
- Không log nguyên request body/response body nếu có dữ liệu người dùng.
- Không log credentials, tokens hoặc connection strings.
- Chỉ cho phép một số **field name/metric name** được định nghĩa trước.
- Thay dữ liệu người dùng bằng opaque correlation ID khi cần liên kết request.
- Kiểm soát logger categories và mức DEBUG trong production.
- Không dựa vào redaction server để giải quyết logging ở application/driver/tracing layers.

## 15. Ví dụ Java Sync Driver: command monitoring an toàn hơn

MongoDB Java Sync Driver có thể gắn `CommandListener`. Dưới đây là ví dụ chỉ log **tên lệnh, database name đã được phê duyệt và thời gian thực hiện**, thay vì ghi nội dung `command`.

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.event.CommandFailedEvent;
import com.mongodb.event.CommandListener;
import com.mongodb.event.CommandStartedEvent;
import com.mongodb.event.CommandSucceededEvent;

import java.util.Set;
import java.util.concurrent.TimeUnit;

public final class SafeMongoCommandMonitor {
    private static final Set<String> ALLOWED_COMMANDS =
        Set.of("find", "aggregate", "insert", "update",
               "delete", "count", "getMore");

    private static String safeCommandName(String name) {
        return ALLOWED_COMMANDS.contains(name) ? name : "other";
    }

    static final class SafeListener implements CommandListener {
        @Override
        public void commandStarted(CommandStartedEvent event) {
            // Không gọi event.getCommand().toJson()
            // và không gửi command BSON sang APM/logs.
        }

        @Override
        public void commandSucceeded(CommandSucceededEvent event) {
            long millis =
                event.getElapsedTime(TimeUnit.MILLISECONDS);

            System.out.printf(
                "mongo_command status=ok kind=%s elapsed_ms=%d%n",
                safeCommandName(event.getCommandName()),
                millis
            );
        }

        @Override
        public void commandFailed(CommandFailedEvent event) {
            System.out.printf(
                "mongo_command status=error kind=%s%n",
                safeCommandName(event.getCommandName())
            );

            // Không log Throwable/stack trace nguyên vẹn
            // nếu chúng có thể chứa URI hoặc query values.
        }
    }

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Thiếu MONGODB_URI");
        }

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .addCommandListener(new SafeListener())
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            client.getDatabase("mongo_observability_lab")
                .runCommand(new org.bson.Document("ping", 1));
        }
    }
}
```

**Đây là một mẫu logging tối giản.** Việc dùng `System.out` trong ví dụ chỉ để hiển thị; hệ thống thật nên dùng metrics/logging library được cấu hình và kiểm soát. Nếu chỉ cần duration histograms, một metrics collector không ghi text per-operation có thể phù hợp hơn.

### Những điều ví dụ cố tình không làm

Không gọi:

```java
event.getCommand().toJson();
```

Không log:

```text
MongoClientSettings chứa connection string
CommandStartedEvent command BSON
Exception message có secrets/query values
Raw database documents
```

Thậm chí tên database/collection cũng có thể nhạy cảm nếu namespace chứa tenant identifiers. Đó là lý do ví dụ dùng allowlist command names và không log database name.

### Cẩn thận với lỗi và exception text

`CommandFailedEvent.getThrowable()`, stack traces và exception messages có thể hữu ích cho chẩn đoán nhưng không nên được xem là an toàn tuyệt đối. Nếu ứng dụng cần error telemetry, dùng **error class/category được cho phép** và lưu thông tin chi tiết nhạy cảm trong một kênh điều tra có quyền hạn hẹp, nếu chính sách cho phép.

## 16. Chặn sự cố tại nguồn: không log toàn bộ query

So sánh:

```java
// KHÔNG NÊN:
logger.info("Searching customer with filter={}",
    new Document("email", customerEmail).toJson());
```

Với:

```java
// HƯỚNG TỐT HƠN:
logger.info(
    "customer_lookup outcome={} latency_ms={} request_id={}",
    found ? "found" : "not_found",
    elapsedMillis,
    safeRequestId
);
```

Trong mẫu thứ hai:

- Email không đi vào log.
- Kết quả tìm kiếm được biểu diễn dạng category.
- Latency hỗ trợ chẩn đoán.
- Request ID là một **opaque token do hệ thống cấp** để liên kết log, không chứa email, phone, access token hoặc nội dung người dùng.

### Request ID cũng có thể trở thành dữ liệu nhạy cảm

Nếu hệ thống dùng:

```text
request_id = "user-email@example.com-2026-11-14"
```

thì việc đổi tên field thành `request_id` không bảo vệ PII. Hãy dùng ID ngẫu nhiên/opaque, đặt giới hạn length và xác thực format trước khi log.

## 17. MongoDB `comment`: tốt cho correlation, nhưng không để PII

Một số MongoDB commands hỗ trợ field `comment` để gắn context cho operation. Công cụ phân tích có thể hiển thị comment khi xem query hoặc profiler.

Ví dụ trong lab:

```javascript
db.orders.find(
  { status: "NEW" }
).comment("orders-list-v2");
```

Đây là **nhãn cố định theo loại truy vấn**, không phải dữ liệu khách hàng. Không làm:

```javascript
// KHÔNG NÊN: comment có PII.
db.orders.find({
  customerEmail: "demo-user@example.invalid"
}).comment("customer=demo-user@example.invalid");
```

### Dùng comment thế nào là hợp lý?

- Query template ID được phê duyệt: `orders-list-v2`.
- Tên service/component đã được kiểm duyệt.
- Correlation ID không chứa thông tin người dùng.
- Không chứa secrets, raw request input, JWT, session IDs.
- Không dựa vào `comment` để thực thi authorization.

Hỗ trợ/comment placement cụ thể tùy MongoDB driver và command. Nếu muốn gắn metadata liên kết ở APM, phải hiểu **nó có thể được lưu tại những telemetry sinks nào**.

## 18. Tận dụng metrics không chứa document values

Nhiều câu hỏi vận hành có thể được trả lời bằng **metrics tổng hợp**, không cần profiler raw documents:

- Có bao nhiêu connections đang mở?
- p95 query latency tăng từ lúc nào?
- CPU, cache misses và disk I/O có tăng không?
- Replication lag có vượt SLA không?
- Số operations failed theo error category có tăng?
- Number of documents/keys examined theo query shape có bất thường?

Ví dụ lấy một ít server status fields trong lab có quyền phù hợp:

```javascript
const status = db.getSiblingDB("admin")
  .runCommand({ serverStatus: 1 });

printjson({
  connectionsCurrent: status.connections?.current,
  connectionsAvailable: status.connections?.available,
  opcounters: status.opcounters
});
```

Lệnh này không in toàn bộ `serverStatus`. Tuy nhiên, serverStatus vẫn là thông tin vận hành cần quyền thích hợp, và đối tượng `opcounters` có nhiều trường hơn một metric duy nhất. Chọn fields hẹp theo nhu cầu nếu xuất ra hệ giám sát.

### Metrics cũng cần kiểm soát

Không phải mọi metric labels đều an toàn:

```text
TỐT HƠN:
  mongodb_query_duration_seconds{
    service="orders-api",
    operation="find",
    outcome="ok"
  }

KHÔNG NÊN:
  mongodb_query_duration_seconds{
    customer_email="demo-user@example.invalid",
    phone="+00-000-000-000"
  }
```

Thêm email/userId làm label vừa **rò rỉ định danh** vừa gây **high cardinality**, tăng CPU/RAM/storage cho hệ thống metrics. Nếu cần đo theo tenant, chỉ dùng opaque tenant identifier theo chính sách và đánh giá cardinality/ quyền truy cập.

## 19. Tracing và APM: một đường rò phổ biến

Các APM agents hoặc distributed tracing libraries có thể tự động thu thập:

- HTTP route/method/status.
- Database system, operation name và collection.
- Database statement/query/command.
- Exception class/message/stack trace.
- Request URL, headers và một số attributes do app gắn thủ công.

Không nên bật tính năng **capture database statements** hoặc **capture request bodies** mà chưa đánh giá nguồn dữ liệu thực.

### Ví dụ một span cần tối giản

```text
span.name = "MongoDB find"
db.system = "mongodb"
db.operation = "find"
app.component = "customer-api"
duration_ms = 95
status = "ok"
request_id = "opaque-7a31"
```

Tránh:

```text
db.statement = "{email:'demo-user@example.invalid'}"
http.url = "/customers?email=demo-user@example.invalid"
db.connection_string = "mongodb+srv://user:password@..."
exception.message = "full raw payload with secrets"
```

### Filter phải chạy trước khi dữ liệu rời ứng dụng

Nếu toàn bộ command đã được gửi đến nhà cung cấp APM, rồi UI dashboard mới ẩn field `db.statement`, dữ liệu gốc có thể vẫn tồn tại trong backend, exporter queues hoặc các bản sao. **Ưu tiên chặn/redact tại agent hoặc collector trước khi export**, không chỉ ẩn ở tầng giao diện.

## 20. Biến một pipeline giám sát thành nhiều điểm kiểm soát

```text
Source: MongoDB / Application
           |
           v
  Local agent / instrumentation
  - không thu thập payload thô
  - allowlist attributes
           |
           v
  Collector / log processor
  - redact/drop field nhạy cảm
  - sampling và routing
           |
           v
  Central observability store
  - encryption
  - RBAC / separation of duties
  - retention
           |
           v
  Dashboard / query / export
  - row/field access controls
  - audit views/downloads
```

**Ưu tiên thứ tự:** không thu thập → che trước export → kiểm soát truy cập khi lưu → giảm retention → giám sát exports. Nếu đợi tới bước cuối mới che, bytes nhạy cảm đã có thể nằm trong network buffers, collectors và backups.

### Một pipeline redaction thất bại như thế nào?

Một processor loại field có tên `password` nhưng không loại:

```text
passwd
pwd
accessToken
authorization
api_key
credentials
mongo_uri
sessionCookie
```

Hoặc secret nằm trong nested JSON, string message hay exception stack trace. Regex theo vài từ khóa **không thể bảo đảm** che mọi cách xuất hiện. Đối với cấu trúc dữ liệu đã biết, dùng **allowlist schema** đáng tin cậy hơn blacklist chung.

## 21. Redaction, masking, tokenization và hashing

Các cơ chế thường gặp:

| Cơ chế | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Drop field** | Không lưu giá trị | Bỏ toàn bộ `email` khỏi log |
| **Redact** | Thay bằng marker | `email: "[REDACTED]"` |
| **Mask** | Chỉ giữ phần không nhạy cảm | `phone: "***-***-1234"`, nếu chính sách cho phép |
| **Tokenize** | Thay bằng opaque ID có bảng ánh xạ được bảo vệ | `customer_ref: "tok-7a31"` |
| **Hash** | Tạo fingerprint một chiều | Hash có khóa theo policy nếu cần liên kết |
| **Aggregate** | Giữ số liệu tổng thay vì từng identity | 95th percentile latency |

### Hash không tự biến PII thành dữ liệu công khai

Email thường có không gian đoán tương đối nhỏ. Nếu log chứa `SHA256(email)` không salt, người có danh sách email phổ biến có thể tính thử hash để suy ra người dùng. **Hashing alone không bảo đảm anonymous**.

Khi cần liên kết events theo một identity, cân nhắc:

- Opaque request/customer ID không mang ý nghĩa trực tiếp.
- HMAC có khóa bảo vệ thay vì plain hash, nếu dùng fingerprint.
- Retention và quyền truy cập giới hạn.
- Không dùng cùng một pseudonym vượt quá phạm vi cần thiết nếu có nguy cơ theo dõi cá nhân.

### Masking cũng có thể làm lộ dữ liệu

Việc giữ bốn chữ số cuối của tài khoản hoặc điện thoại có thể không được phép trong một số bối cảnh. Quy tắc masking phải theo classification/ compliance, không mặc định luôn an toàn chỉ vì không thấy toàn bộ giá trị.

## 22. Regex redaction không thay thế data minimization

Ví dụ một log processor tìm pattern `password=...`. Nó có thể bỏ sót:

```json
{
  "command": {
    "update": "profiles",
    "updates": [
      {
        "q": {"email": "demo-user@example.invalid"},
        "u": {"$set": {"sessionToken": "synthetic-do-not-use"}}
      }
    ]
  }
}
```

Ngay cả khi processor tìm được `sessionToken`, nó còn phải xử lý email trong nested query. Một logger **không ghi field `command`** từ đầu thường an toàn hơn một pipeline cố làm sạch chuỗi command BSON.

### Cách tiếp cận ưu tiên

1. **Không log raw commands**.
2. Thiết kế **structured events** với fields đã phê duyệt.
3. Nếu buộc phải thu thập command text để điều tra, thực hiện trong môi trường được kiểm soát, sampling hẹp, retention rất ngắn và phê duyệt riêng.
4. Thực hiện redaction theo cấu trúc trước khi export.
5. Theo dõi tỷ lệ events bị drop/redact và lỗi processor.
6. Đánh giá nguy cơ không phát hiện được secret mới.

Đừng tuyên bố một bộ regex tổng quát đã “xóa 100% PII khỏi toàn bộ log”.

## 23. Phân quyền cho `system.profile` và nguồn diagnostic

Người dùng vận hành cần metric latency **không tự động cần quyền đọc mọi profile document**. Nên tách:

- **Database app user:** chỉ quyền đọc/ghi namespace nghiệp vụ.
- **Monitoring account:** chỉ quyền cần cho metrics/status được phê duyệt.
- **Performance investigator:** quyền tạm thời để đọc thông tin profiler theo sự cố.
- **Security/audit operator:** quyền riêng cho audit logs/access logs.
- **Backup/restore operator:** quyền sao lưu và phục hồi theo chính sách.

Việc cấu hình profiling hoặc đọc `system.profile` yêu cầu quyền cụ thể theo server/version. Không dùng tài khoản `root` hoặc `atlasAdmin` làm credentials mặc định cho một exporter đơn giản.

### Thao tác đọc đã có thể gây lộ

Ngay cả một lệnh `find()` trên `system.profile` cũng có thể trả PII. Nên:

1. Hạn chế người có `find` trên namespace này.
2. Dùng projection/aggregations chỉ lấy fields cần.
3. Tránh export full raw profile data sang hệ thống log thứ hai.
4. Dùng session/role tạm thời nếu tổ chức hỗ trợ.
5. Theo dõi ai truy cập và xuất dữ liệu chẩn đoán theo khả năng auditing.

### Namespace có thể tiết lộ thông tin

Nếu database/collection được đặt tên theo khách hàng hoặc dự án bí mật, `ns` cũng có thể chứa thông tin nhạy cảm. Có thể cần ánh xạ namespace sang service identifier tổng quát trong public/team-wide dashboards, và chỉ cho nhóm DBA xem thông tin chi tiết.

## 24. Bảo vệ truy cập hệ thống log/monitoring

Một mô hình quản trị:

| Vai trò | Quyền hợp lý | Tránh cấp |
| --- | --- | --- |
| Developer | Metrics và dashboard của service phụ trách | Toàn bộ raw production profiler logs |
| On-call operator | Alert, error categories, query shapes | Passwords/PII/raw commands |
| DBA điều tra | Truy cập tạm theo incident vào dữ liệu diagnostic cần thiết | Quyền vĩnh viễn tới mọi secret |
| Security team | Audit events theo nhiệm vụ, incident artifacts có kiểm soát | Export không ghi dấu hoặc chia sẻ công khai |
| Vendor/support | Metrics/sanitized support bundles | Raw memory dump, production secrets |

Nguyên tắc:

- SSO/MFA cho observability platform khi phù hợp.
- Role-based access theo team, environment, namespace/data classification.
- Tách production khỏi staging/development.
- Audit việc đọc/xuất dữ liệu nhạy cảm nếu platform hỗ trợ.
- Chặn sharing links công khai và kiểm tra dashboard permissions.
- Không copy raw profiler output vào ticket/chat rộng người xem.

Một dashboard chứa email của khách hàng là **nơi lưu dữ liệu khách hàng**, dù tên nó là “Performance Dashboard”.

## 25. Mã hóa đường truyền và lưu trữ

**TLS:** bảo vệ đường truyền từ application tới MongoDB và từ monitoring agents tới collectors/backends.

**Encryption at rest:** giảm rủi ro khi phương tiện lưu trữ bị truy cập trái phép, áp dụng cho database volumes, log files, backup và observability storage theo chính sách.

**Client-side Field Level Encryption/Queryable Encryption:** có thể giúp bảo vệ một số field dữ liệu ở database theo tính năng và giới hạn tương ứng, nhưng **không tự bảo vệ logs sinh ra trước bước mã hóa ở client**, ví dụ:

```text
Java app:
  có plaintext email
       |
       +--> logger.debug(plaintext email)  [RÒ RỈ]
       |
       v
  Client-side encryption
       |
       v
  MongoDB nhận dữ liệu mã hóa
```

Do đó, mã hóa dữ liệu trong MongoDB **không cho phép** application ghi plaintext lên logs một cách an toàn.

### Backup và exports cũng cần mã hóa

Nếu `system.profile`/logs đã được đưa vào backup, bản backup có thể giữ dữ liệu nhạy cảm lâu hơn retention tại nguồn. Nên quản lý encryption keys, access, lifecycle và backup deletion theo cùng data classification. Không mặc định backup MongoDB luôn chứa hoặc không chứa `system.profile`: phạm vi phụ thuộc công cụ/kiểu backup và configuration.

## 26. Retention: giữ bao lâu là đủ?

Mỗi loại telemetry có mục đích khác nhau:

```text
Operational metrics:
  đủ dài để theo dõi xu hướng / capacity

Diagnostic logs:
  thời gian điều tra sự cố, có chính sách xóa

Raw profiler:
  thời gian ngắn, chỉ trong đợt điều tra được duyệt

Security audit logs:
  theo yêu cầu điều tra và compliance

Incident artifacts:
  theo quy trình evidence retention riêng
```

Không có một con số retention chung phù hợp mọi tổ chức. Chính sách cần xác định:

- **Mục đích xử lý** và người sở hữu dữ liệu.
- **Loại dữ liệu nhạy cảm** có thể xuất hiện.
- **Thời gian cần thiết** để phát hiện/điều tra vấn đề.
- **Số bản sao** trong agents, buffers, queues, indexed store, archives, exports, backups.
- **Quy trình deletion** sau khi hết thời hạn hoặc có yêu cầu pháp lý.
- **Ngoại lệ legal hold** có được kiểm soát không.

### Log rotation không đồng nghĩa deletion

Việc chuyển từ `mongod.log` sang `mongod.log.1` hoặc file nén chỉ thay nơi chứa; bytes nhạy cảm vẫn có thể tồn tại. Cần phối hợp **rotation + secure access + retention/deletion + backup policy**.

### Sampling không đồng nghĩa giảm mức phân loại bảo mật

Một event có password vẫn là **SECRET** dù chỉ được chọn 1/10.000 lần. Sampling giảm khối lượng, không biến một vi phạm nguyên tắc “không được log credentials” thành hợp lệ.

## 27. Log ingestion và dữ liệu nằm ngoài database

Trong một hệ thống tập trung, cùng một event có thể tồn tại ở:

```text
1. Local mongod log
2. Local agent buffer
3. Message broker / spool directory
4. Collector memory/queue
5. Central log store
6. Search index của log platform
7. Dashboard cache
8. Notification / alert message
9. Exported JSON/CSV
10. Backup/archive của log platform
```

Một thao tác xóa event ở điểm 5 chưa chắc xóa những bản sao tại 1–4 và 6–10. Vì vậy, **data lineage** của diagnostic data rất quan trọng.

### Không đẩy raw data đến kênh alert phổ biến

Một cảnh báo:

```text
MongoDB slow query exceeded 2s
service=orders-api
query_shape=find_by_customer
p95=2200ms
```

thường đủ để đánh thức on-call. Không cần đính kèm:

```text
email, session token, raw filter,
full command body, document payload
```

vào email/chat alert, nơi người nhận có thể forward/screenshot và retention khó kiểm soát.

## 28. Sự cố lộ thông tin qua log: runbook

Giả sử đội vận hành phát hiện một connection URI có password xuất hiện trong centralized log. Phản ứng nên ưu tiên **giảm tác động và bảo vệ bằng chứng**:

1. **Xác định phạm vi:** event nào, service nào, timestamps nào, log sinks nào, ai có quyền xem.
2. **Giảm tiếp tục rò rỉ:** tắt hoặc sửa logger đang ghi URI/command, thu hẹp export route nếu cần.
3. **Thu hồi/rotate secrets bị lộ** theo quy trình được phê duyệt; không chờ xóa log mới rotate.
4. **Kiểm tra truy cập bất thường:** authentication attempts, network access, hoạt động của user/token liên quan.
5. **Khoanh quyền truy cập log:** tạm thời giới hạn viewers/exports của tập log bị ảnh hưởng.
6. **Bảo toàn thông tin phục vụ điều tra** trong kênh được phép, tránh sao chép secret sang ticket công khai.
7. **Xóa hoặc redact những bản sao** ở hệ thống log/alerts/exports/backups theo quy định và khả năng kỹ thuật.
8. **Kiểm tra lại instrumentation** bằng dữ liệu giả lập và rules để ngăn lặp lại.
9. **Ghi nhận incident**: nguyên nhân, phạm vi dữ liệu, mức ảnh hưởng, corrective actions.
10. **Thông báo/tuân thủ** theo chính sách và pháp luật áp dụng khi có thông tin cá nhân bị ảnh hưởng.

### Xóa log không thay thế rotate secret

Một token từng xuất hiện trong dashboard có thể đã được tải về, chụp màn hình hoặc dùng trước khi xóa. Nếu là credential có thể sử dụng, **thu hồi hiệu lực** mới là cách giảm rủi ro tiếp tục bị lạm dụng.

### Không “bảo vệ bằng chứng” bằng cách phát tán thêm

Nhóm điều tra không nên paste nguyên credential vào một ticket hoặc nhóm chat để “ghi lại sự cố”. Dùng secret reference, incident ID và nơi lưu chứng cứ được kiểm soát; nội dung có thể cần chính sách bảo mật cao hơn log thường.

## 29. Debug chậm: ưu tiên metrics và query shape trước profiler

Một quy trình chẩn đoán hợp lý:

```text
Alert p95 latency tăng
          |
          v
Metrics: CPU/I/O/cache/connections
          |
          v
Query shape / planSummary / index stats
          |
          v
Explain trên query giả lập hoặc được redacted
          |
          v
Profiler chọn lọc khi thật sự cần
          |
          v
Tắt profiling / kiểm soát artifacts
```

Điều này giảm việc bật raw-data collection khi chưa cần thiết.

### Ví dụ không cần PII vẫn phát hiện thiếu index

Một báo cáo cho thấy:

```text
Operation: find
Collection: customers
Duration p95: 900 ms
Plan: COLLSCAN
Docs examined: 450000
Returned docs: 1
```

Không cần biết email cụ thể để nhận ra query đang quét nhiều documents và cần đánh giá index/selectivity.

### `explain()` cũng phải xem là diagnostic data

Một `explain()` có thể chứa:

- Filter/query shape với literal values.
- Namespace, index names, plan cache keys và thống kê.
- Aggregation pipeline.

Khi gửi explain cho người khác, cần chọn trường cần thiết hoặc redaction trước khi chia sẻ. **Không copy nguyên explain production vào diễn đàn công khai hoặc ticket vendor nếu chưa rà soát data classification.**

## 30. `currentOp` và các thông tin đang chạy

Trong các môi trường được phép, `$currentOp`/công cụ quan sát operations có thể giúp tìm operation đang chạy lâu hoặc chờ lock. Tuy nhiên, full operation details cũng có thể chứa command/filter.

Một cách tiếp cận là chỉ lấy **các trường cần thiết**:

```javascript
db.getSiblingDB("admin").aggregate([
  {
    $currentOp: {
      allUsers: false,
      localOps: true
    }
  },
  {
    $project: {
      _id: 0,
      type: 1,
      op: 1,
      secs_running: 1,
      waitingForLock: 1
    }
  }
]);
```

**Lưu ý:** `$currentOp` có giới hạn/permissions và semantics khác nhau theo topology, server version và Atlas tier. Ví dụ chỉ minh họa việc **projection bỏ trường `command`**, không phải một API được bảo đảm có đủ mọi field trên mọi deployment.

Không thực hiện:

```javascript
// Cẩn thận: có thể hiển thị raw command/query values.
db.currentOp();
```

rồi paste nguyên output vào log/ticket không giới hạn quyền.

## 31. Atlas observability: không được lẫn capability với quyền mặc định

MongoDB Atlas có những tính năng monitoring, Query Profiler, Performance Advisor, logs và integrations tùy cluster tier, edition và phiên bản. Không phải mọi Atlas deployment đều cho phép cấu hình profiler qua `db.setProfilingLevel()` theo cách giống tự quản lý, hoặc hỗ trợ cùng mức xuất logs.

Điểm cần kiểm tra khi dùng Atlas:

- **Ai có project/organization permissions để xem logs, profiler và query data?**
- **Database user** có những quyền gì trong MongoDB data plane?
- Project monitoring có gửi dữ liệu tới external integrations không?
- Tài khoản người dùng/vendor nào xem được query details?
- Log export có đi sang cloud storage, SaaS hoặc region khác không?
- Retention của profiler/log/tracing theo tier/platform là gì?
- Có cấu hình redaction/diagnostic logging tương ứng và giới hạn gì?

### Phân biệt quyền UI với quyền collection

Một người được phép mở Atlas monitoring dashboard **không nhất thiết** có MongoDB `readWrite` trên `ordersdb`; ngược lại, một database app user cũng không nên có quyền quản lý toàn bộ Atlas project. Nhưng dashboard/log vẫn có thể chứa metadata hoặc giá trị nhạy cảm. **Phải review cả Atlas project permissions lẫn database RBAC**.

### Không xem screenshot là dữ liệu vô hại

Screenshots của Query Profiler, Performance Advisor hoặc trang Logs có thể chứa namespace, query filter, ID và literal values. Khi chia sẻ qua ticket/wiki, cần redaction và quyền truy cập tương ứng như nội dung gốc.

## 32. Triển khai theo nguyên tắc “privacy by design”

Một design review cho MongoDB observability nên trả lời:

1. **Chúng ta cần phát hiện điều gì?** Latency, error rate, replication lag, index efficiency hay access violations?
2. **Metric tối thiểu nào đủ?** Có cần full query text không?
3. **Dữ liệu có thể chứa PII/secret ở field nào?** Query, comments, error, labels, headers?
4. **Dữ liệu chạy qua những hệ thống nào?** Agent, collector, broker, SaaS, export, backups?
5. **Ai có thể đọc/export?** Developer, DBA, support, vendor, on-call?
6. **Giữ bao lâu?** Mỗi loại telemetry có policy riêng không?
7. **Đường xóa là gì?** Xóa ở source có làm sạch mọi bản sao không?
8. **Cần ghi nhận audit truy cập không?** Đặc biệt với raw profiler/audit artifacts.
9. **Có kênh điều tra ngoại lệ không?** Khi cần raw data, ai phê duyệt và giới hạn thời gian?
10. **Làm sao chứng minh cấu hình hoạt động?** Dùng dữ liệu giả lập và bài kiểm tra có kiểm soát.

### Mẫu quyết định kỹ thuật

```text
Service: customer-api
Observability objective: query p95 + missing index detection
Primary data: aggregated latency, plan summary, docs examined
Prohibited in logs: email, phone, token, URI, raw BSON command
Command monitoring: allowlisted names and durations only
Profiler: normally disabled; short, approved investigation window
Access: on-call metrics; DBA restricted diagnostic access
Transport/storage: TLS and encryption at rest
Retention: per data-class policy
Third-party export: reviewed and approved
Owner: platform/database team
```

Đây là mẫu **ghi chính sách**, không phải báo cáo một hệ thống có thật đã đạt yêu cầu. Mỗi tổ chức cần điền policy và controls của mình.

## 33. Kiểm tra redaction trên dữ liệu giả lập

Một môi trường lab được tạo với các giá trị giả:

```javascript
use mongo_observability_lab

db.customers.insertMany([
  {
    _id: "CUS-DEMO-01",
    email: "demo-user@example.invalid",
    phone: "+00-000-000-000",
    status: "ACTIVE"
  },
  {
    _id: "CUS-DEMO-02",
    email: "another-user@example.invalid",
    phone: "+00-000-000-001",
    status: "INACTIVE"
  }
]);

db.customers.createIndex({ email: 1 });
```

**Kịch bản kiểm thử chính sách**:

1. Thực hiện query theo `email` trong lab.
2. Bật logger/collector ở chế độ tương ứng với production policy, không nhất thiết profiler.
3. Kiểm tra event **được phép export** không chứa email, phone hoặc query literal gốc.
4. Kiểm tra metrics vẫn có operation type và latency.
5. Kiểm tra full exporter queues và event transforms nếu công cụ cho phép.
6. Đảm bảo policy vẫn hoạt động khi error xảy ra.

Không thực hiện các bước trên với email/password thật. Việc thử redaction chỉ bằng chuỗi `password` có thể không phát hiện rò rỉ trong query literals hoặc nested BSON.

### Kiểm tra lỗi ở đường exception

Một service có thể an toàn ở happy path:

```java
logger.info("lookup ok request_id={}", requestId);
```

nhưng nguy hiểm ở error path:

```java
// KHÔNG NÊN nếu throwable có thể chứa raw query/credentials:
logger.error("lookup failed for query={}", filter, exception);
```

Cần policy cho cả error messages, wrapped exceptions và error responses gửi tới frontend.

## 34. Mức độ chi tiết khi điều tra sự cố bảo mật

Đôi khi incident forensic cần thông tin chi tiết hơn metrics thông thường, chẳng hạn tìm một truy vấn độc hại theo user/session ID. Không vì vậy mà chuyển mọi logger sang debug vô thời hạn.

Một quy trình ngoại lệ:

1. Tạo incident ID và xác định mục tiêu điều tra cụ thể.
2. Phê duyệt quyền thu thập raw diagnostic data.
3. Chỉ thu thập trong **window ngắn và scope hẹp**.
4. Dùng môi trường/sink có quyền truy cập được giới hạn.
5. Bảo vệ artifacts bằng encryption/controlled storage.
6. Không đưa secrets vào chat hoặc ticket rộng người xem.
7. Khi kết thúc, đưa instrumentation về baseline.
8. Xử lý artifacts theo incident retention, legal hold và deletion policy.

**Khả năng điều tra sâu là một trường hợp đặc biệt được kiểm soát**, không phải lý do để thu thập mọi command của mọi khách hàng vĩnh viễn.

## 35. Multi-tenant systems: thêm một rủi ro

Ứng dụng SaaS thường có:

```text
tenant-01
tenant-02
tenant-03
```

Một logger có thể ghi:

```json
{
  "operation": "find",
  "tenantId": "tenant-01",
  "customerEmail": "demo-user@example.invalid"
}
```

Điều này tạo nguy cơ **cross-tenant data visibility** nếu dashboard cho nhiều đội hỗ trợ hoặc tenant administrators xem cùng log index.

Các lựa chọn:

- Tránh customer-level identifiers trong log.
- Dùng tenant grouping khi thật sự cần, với opaque ID/approved labels.
- Tách observability data theo tenant hoặc access scope nếu requirement bắt buộc.
- Không cho tenant người dùng truy cập raw MongoDB profiler/log data của cluster chung.
- Thực thi filter/permissions ở backend observability, không chỉ frontend.
- Tránh chứa tenant ID trong URL chia sẻ public của dashboard.

**Hệ thống bảo vệ business collections bằng tenant filter nhưng để lộ dữ liệu đó qua logs là một sự cố phân quyền**, dù database query logic vẫn đúng.

## 36. Tránh high-cardinality labels vừa tốn kém vừa làm lộ dữ liệu

Một metric cardinality có thể tăng theo tích số nhãn:

```text
service (20 values)
 × operation (8 values)
 × customer_id (100.000 values)
 = tới 16.000.000 tổ hợp nhãn
```

Đây là ước lượng số tổ hợp lý thuyết, không phải số time series luôn có trong backend.

Nếu metrics chỉ cần đếm latency theo service/operation, dùng `customer_id` làm label vừa tốn bộ nhớ/chi phí vừa đưa identifier vào hệ thống monitoring. Điều tương tự xảy ra với `email`, `sessionId`, dynamic URL path chứa UUID/user ID hoặc raw query string.

### Giảm cardinality

- Dùng route templates thay raw URLs, ví dụ `/customers/{id}` thay `/customers/CUS-123`.
- Dùng operation/query-shape categories thay full query text.
- Dùng nhóm lỗi cố định thay exception message.
- Nếu cần phân tích theo tenant, đánh giá series count và quyền hạn riêng.
- Đưa chi tiết từng request vào tracing hạn chế quyền, không nhồi vào metric labels.

## 37. Security audit và diagnostic logs có retention khác nhau

Một sự cố lạm dụng database privileges có thể đòi audit trail giữ lâu theo quy định, trong khi raw profiler chỉ cần ít giờ để điều tra query chậm. Nếu trộn cả hai vào một log index:

- Có thể giữ query literals không cần thiết quá lâu.
- Khó cấp quyền điều tra riêng.
- Khó đặt retention theo data class.
- Alert và dashboard có thể vô tình lộ event details.

Nên phân vùng theo **mục đích và độ nhạy**:

```text
Operational metrics
Diagnostic logs
Raw profiler / limited investigation data
Security audit trail
Incident evidence
```

Không dùng một TTL policy chung cho mọi loại dữ liệu. Khi có audit compliance, cần tính cả tính toàn vẹn, quyền chỉnh sửa, vị trí lưu trữ và khả năng truy xuất chứng cứ.

## 38. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai? | Hướng đúng |
| --- | --- | --- |
| “Log không nằm trong DB nên không chứa dữ liệu khách hàng” | Query/filter/command có thể chứa PII | Phân loại log như data |
| “Không log response là đủ” | Query predicate và exception vẫn có thể lộ | Không log raw inputs/commands |
| “Server redaction bảo vệ mọi logger” | Driver/app/APM/audit có pipeline riêng | Kiểm soát từng nguồn |
| “Bật `redactClientLogData` là không còn secret” | Phạm vi redaction có giới hạn | Data minimization + tests + RBAC |
| “Profiler chỉ lưu millis” | Có thể lưu command/filter | Bảo vệ `system.profile` |
| “Profiler level 2 chỉ tăng disk, không rủi ro khác” | Thu nhiều values và tạo overhead | Chọn level/scope tối thiểu |
| “Level 0 tắt mọi slow query log” | Diagnostic logs và profile khác nhau | Kiểm tra từng nguồn |
| “Sampling 1% nghĩa là PII an toàn” | 1% records vẫn chứa PII thật | Không thu thập giá trị cấm |
| “Query projection xóa giá trị đã lưu” | Chỉ giới hạn output | Cần thu thập/retention controls |
| “Mã hóa at rest làm dashboard vô hại” | Người có quyền vẫn thấy plaintext sau giải mã | RBAC/data minimization |
| “Field encryption bảo vệ app logs” | App có plaintext trước encryption | Không log ở client |
| “Hash email là anonymous” | Có thể bị đoán/brute-force | Opaque ID/HMAC và policy |
| “Log rotation là xóa log” | File rotated vẫn tồn tại | Retention/deletion |
| “Metrics luôn không nhạy cảm” | Labels có thể chứa ID/email | Low-cardinality approved labels |
| “Trace query text là bắt buộc để đo latency” | Duration/shape thường đủ | Dùng structured attributes tối thiểu |
| “Ẩn field trong dashboard là đã xóa” | Backend, exports, backups còn giữ | Redact trước export |
| “Atlas monitoring role là DB role” | Quyền UI và data plane khác nhau | Review cả hai |
| “Có quyền xem profiler tức được xem mọi dữ liệu” | Least privilege vẫn áp dụng | Giới hạn scope |
| “Raw `explain()` luôn chia sẻ công khai được” | Có thể chứa filter/literals | Sanitized output |
| “`comment` không bao giờ được ghi lại” | Có thể xuất hiện trong diagnostics | Không đặt PII trong comment |
| “Incident xong xóa secret khỏi log là đủ” | Secret có thể đã bị sử dụng/copy | Rotate/revoke + investigate |
| “Một regex chặn hết secrets” | Nested payload/biến thể key dễ bỏ sót | Allowlist và không thu thập |

## 39. Bài tập thực hành và đáp án

### Bài 1. Lộ email qua filter

Ứng dụng query:

```javascript
db.customers.find({ email: "demo-user@example.invalid" });
```

Ứng dụng không log response nhưng log `filter.toJson()`. Email có thể bị lộ không?

**Đáp án:** Có. Giá trị email nằm trong query literal. Không log full BSON filter; dùng operation/query shape, duration và opaque request ID.

### Bài 2. Profiling level 2

Team bật profiler level 2 trên production trong cả tuần để “có đủ dữ liệu nếu sự cố xảy ra”. Rủi ro?

**Đáp án:** Tăng overhead và thu nhiều commands có thể chứa PII; cần baseline metrics, profiling chọn lọc theo cửa sổ ngắn và quyền truy cập hạn chế.

### Bài 3. Projection

Truy vấn `system.profile` chỉ lấy `millis` và `planSummary`. Có nghĩa command literals đã được xóa khỏi profile collection không?

**Đáp án:** Không. Projection chỉ hạn chế fields trả về; data đã lưu vẫn có thể tồn tại trong profile records.

### Bài 4. Redaction server

Đã bật `security.redactClientLogData` ở server. Java logger ghi nguyên `filter.toJson()`. Server option có tự che email trong Java log không?

**Đáp án:** Không. Server-side log redaction không kiểm soát logging do ứng dụng thực hiện. Cần sửa application instrumentation.

### Bài 5. URI

Developer thêm log `"Mongo URI=" + System.getenv("MONGODB_URI")` để hỗ trợ debug. Vấn đề?

**Đáp án:** URI có thể chứa username/password và thông tin topology nội bộ. Không log raw URI; ghi một nhãn endpoint/service đã được phê duyệt, không chứa secrets.

### Bài 6. `comment`

Có nên đặt `comment: "user=demo-user@example.invalid"` trên query để tìm theo request không?

**Đáp án:** Không. Comment có thể xuất hiện trong diagnostic/profiler; dùng query-template ID hoặc opaque correlation ID.

### Bài 7. Histogram

Đội muốn đo p95 query latency theo `service` và `operation`. Có cần đặt `email` trong metric label không?

**Đáp án:** Không. Email không cần thiết, rò PII và làm tăng label cardinality.

### Bài 8. TLS

Central log store mã hóa dữ liệu at rest. Như vậy người có quyền dashboard có thể xem nguyên token trong log một cách an toàn không?

**Đáp án:** Không. Encryption at rest bảo vệ storage, không ngăn người có quyền đọc/hiển thị plaintext; token không nên có trong log từ đầu.

### Bài 9. Sampling

Một log chứa số định danh cá nhân, nhưng được sample với xác suất 0,1%. Có còn là dữ liệu nhạy cảm không?

**Đáp án:** Có. Sampling giảm số lần ghi, không thay đổi tính nhạy cảm của giá trị được ghi.

### Bài 10. Query shape

Giữa hai thông tin `filter.email="demo-user@example.invalid"` và `filterKeys=["email"]`, thông tin nào thường thích hợp hơn để nhóm hiệu năng truy vấn?

**Đáp án:** Query shape/field keys (nếu chúng được cho phép theo chính sách) thường đủ cho phân nhóm; không cần lưu literal email.

### Bài 11. Mã hóa field

Ứng dụng dùng client-side field encryption trước khi gửi MongoDB, nhưng log email plaintext trước bước encrypt. Dữ liệu được bảo vệ chưa?

**Đáp án:** Chưa ở đường log. Phải chặn logging plaintext ở ứng dụng; mã hóa dữ liệu trên đường tới database không tự sửa logger.

### Bài 12. Profiler retention

`system.profile` có cấu trúc capped. Có thể cam kết mọi giá trị bị xóa đúng sau 24 giờ không?

**Đáp án:** Không. Capped size/ring behavior không tương đương TTL theo thời gian chính xác. Cần retention policy và cách kiểm soát profiler phù hợp.

### Bài 13. Audit và profiler

Có thể dùng profiler thay thế security audit log để chứng minh mọi thao tác phân quyền trong hệ thống không?

**Đáp án:** Không. Hai nguồn có mục đích, coverage và policy khác nhau; audit capability tùy edition/tier.

### Bài 14. Tracing

Một APM span có `db.statement` chứa query với phone của khách hàng. Chỉ ẩn field trên dashboard đã đủ chưa?

**Đáp án:** Chưa. Giá trị đã có thể nằm trong collector/backend/backups. Nên loại/che trước khi export và xử lý các bản sao đã ghi.

### Bài 15. Exception

Application không log filter khi query thành công nhưng khi lỗi lại log nguyên `exception` và raw request. Vấn đề?

**Đáp án:** Error path vẫn có thể lộ credentials/query values. Cần error category và structured fields được phép, kiểm soát exception text.

### Bài 16. Multi-tenant metrics

Một dashboard chung cho nhiều tenant có label `customer_email`. Nguy cơ?

**Đáp án:** Rò dữ liệu giữa tenants và high cardinality; cần bỏ định danh cá nhân và giới hạn dashboard access theo policy.

### Bài 17. Lộ secret

Một password xuất hiện trong log tập trung và đã được xóa khỏi dashboard. Có nên rotate không?

**Đáp án:** Có. Secret có thể đã bị copy/sử dụng; phải thu hồi/rotate, điều tra truy cập và xử lý mọi log sinks/exports theo incident process.

### Bài 18. Debug chậm

Truy vấn có `docsExamined=450000`, `nReturned=1` và `planSummary=COLLSCAN`. Đội DBA có cần giá trị email cụ thể để biết nên kiểm tra index không?

**Đáp án:** Thường không. Query shape, plan summary và examined counts đủ để nhận diện hướng điều tra thiếu index.

### Bài 19. Không log raw commands

Trong Java CommandListener, vì sao không nên mặc định gọi `event.getCommand().toJson()` rồi gửi sang log platform?

**Đáp án:** Command BSON có thể mang filter, updates, pipeline và literals nhạy cảm. Chỉ thu thập command name, outcome, duration và approved fields.

### Bài 20. Retention

Central log retention là 7 ngày, nhưng một cảnh báo gửi raw error text qua email giữ 1 năm. Chính sách xóa 7 ngày đã được thực thi hoàn chỉnh chưa?

**Đáp án:** Chưa. Dữ liệu còn tồn tại trong email/alerts. Retention phải xét cả downstream copies.

### Bài 21. Monitor user

Một exporter chỉ cần connection counts nhưng được cấp database role `root` để khỏi lỗi permission. Đây có phải least privilege không?

**Đáp án:** Không. Cần monitoring account với quyền tối thiểu cho metrics/status được phép; không dùng admin credential cho exporter.

### Bài 22. Diagnostic screenshot

Người vận hành chụp màn hình profiler có hiển thị query literals rồi gửi vào chat nhóm rộng. Có thể xem screenshot là metadata kỹ thuật không?

**Đáp án:** Không. Screenshot có thể chứa thông tin khách hàng hoặc nội bộ; cần redaction và phân quyền như dữ liệu nguồn.

### Bài 23. Hash email

Team dùng SHA-256(email) làm metric label. Có chắc đã ẩn danh tuyệt đối không?

**Đáp án:** Không. Email có thể bị đoán từ danh sách ứng viên; dùng aggregate metrics hoặc opaque ID/HMAC theo chính sách, và xem xét cardinality.

### Bài 24. Xóa khỏi nguồn

Một bản ghi khách hàng đã bị xóa khỏi MongoDB. Có thể khẳng định email không còn ở bất cứ nơi nào khác không?

**Đáp án:** Không. Diagnostic logs, profiler, APM, collectors, alerts, backups và exports có thể còn bản sao. Cần data lineage và lifecycle ở tất cả hệ thống liên quan.

## 40. Checklist khi triển khai observability

### 40.1. Collection và instrumentation

- [ ] Liệt kê những field/command có thể chứa PII, credentials hoặc dữ liệu nghiệp vụ nhạy cảm.
- [ ] Không log raw MongoDB commands, query filters, aggregation pipelines hoặc document payloads theo mặc định.
- [ ] Không log connection strings, headers có token hoặc environment variables chứa secrets.
- [ ] Dùng structured logging allowlist: operation, duration, outcome, query shape ID được phê duyệt.
- [ ] Dùng opaque request IDs; không nhúng email/phone/user input vào correlation ID.
- [ ] Không đặt PII vào `comment`, APM attributes hoặc metric labels.
- [ ] Kiểm tra cả happy path lẫn error path.

### 40.2. MongoDB server và profiler

- [ ] Xác định cấu hình server diagnostic logging và những tính năng redaction khả dụng.
- [ ] Không nhầm server redaction với application/driver log protection.
- [ ] Profiler mặc định ở baseline tối thiểu theo policy; chỉ bật chi tiết khi có nhu cầu.
- [ ] Hạn chế profiling scope/time/sample; không mặc định level 2 production.
- [ ] Giới hạn quyền đọc/điều khiển `system.profile`.
- [ ] Sử dụng projection để giảm dữ liệu diagnostic đưa ra ngoài.
- [ ] Sau điều tra, phục hồi cấu hình profiling/logging đã ghi nhận.
- [ ] Đánh giá quyền truy cập Atlas Query Profiler/Logs/Performance Advisor theo tier/project.

### 40.3. Log/metrics/tracing pipeline

- [ ] Redact/drop trước khi xuất sang collector/vendor khi có thể.
- [ ] Metric labels low-cardinality, không chứa customer IDs/email/tokens.
- [ ] Không capture raw HTTP body, URL query params hoặc `db.statement` tùy tiện.
- [ ] RBAC/MFA và audit exports trên observability platform.
- [ ] TLS cho network path, encryption at rest cho logs/backups.
- [ ] Retention rõ ràng cho logs/profiler/traces/audit/incident artifacts.
- [ ] Có chính sách về vendors, regions, legal hold, exports và backups.
- [ ] Theo dõi lỗi redaction pipeline, volume tăng bất thường và secrets detection.

### 40.4. Vận hành và xử lý sự cố

- [ ] Có runbook điều tra hiệu năng theo hướng metrics → shape → targeted profiling.
- [ ] Có quy trình phê duyệt tạm thời khi cần raw diagnostic data.
- [ ] Có quy trình rotation/revocation nếu secrets xuất hiện trong logs.
- [ ] Không paste raw profiler/exception output vào ticket/chat rộng người xem.
- [ ] Test controls trên dữ liệu giả lập, gồm nested payload và error paths.
- [ ] Có data lineage tới agents, collectors, dashboards, alerts, exports và backups.
- [ ] Định kỳ review log configuration, access rights và retention drift.

## 41. Tổng kết

**Log, profiler và hệ thống giám sát là những nguồn dữ liệu cần được bảo vệ**, không chỉ là công cụ kỹ thuật. MongoDB diagnostic logs và `system.profile` có thể chứa thông tin về query, command, namespace và đôi khi **giá trị literal của dữ liệu khách hàng**. Java driver command monitoring, application logging, APM/tracing và metrics labels có thể tiếp tục nhân bản các giá trị đó ra ngoài MongoDB.

Chiến lược bảo vệ hiệu quả nhất bắt đầu bằng **không thu thập dữ liệu không cần thiết**. Với phần lớn vấn đề hiệu năng, metrics tổng hợp, query shape, latency, index/plan statistics và opaque correlation IDs là đủ. Khi cần profiling chi tiết, chỉ bật ở phạm vi và thời gian được duyệt, kiểm soát quyền đọc `system.profile`, hạn chế raw exports và trả cấu hình về baseline.

Các biện pháp redaction như `security.redactClientLogData` (khi deployment hỗ trợ), masking, TLS, encryption at rest và RBAC đều hữu ích nhưng **không thay thế nhau**. Một server đã bật redaction không thể tự sửa Java logger đang ghi `filter.toJson()`. Một log được mã hóa vẫn có thể lộ email qua dashboard được cấp quyền quá rộng. Một secret đã xóa khỏi log vẫn cần được rotate nếu đã bị công bố.

Một hệ thống MongoDB có khả năng quan sát tốt phải bảo đảm **đủ thông tin để xử lý sự cố, ít dữ liệu nhạy cảm nhất có thể, chỉ đúng người có quyền truy cập và dữ liệu được xóa theo vòng đời xác định**.

### Tài liệu tham khảo chính thức để đối chiếu theo phiên bản

- [MongoDB Manual — Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/)
- [MongoDB Manual — `db.setProfilingLevel()`](https://www.mongodb.com/docs/manual/reference/method/db.setProfilingLevel/)
- [MongoDB Manual — `db.getProfilingStatus()`](https://www.mongodb.com/docs/manual/reference/method/db.getProfilingStatus/)
- [MongoDB Manual — Log Messages](https://www.mongodb.com/docs/manual/reference/log-messages/)
- [MongoDB Manual — Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/)
- [MongoDB Manual — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Java Sync Driver — Monitor Commands](https://www.mongodb.com/docs/drivers/java/sync/current/monitoring-and-logging/monitoring/)
- [MongoDB Atlas — Monitoring and Alerts](https://www.mongodb.com/docs/atlas/monitoring-alerts/)
