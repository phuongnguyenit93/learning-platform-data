# Giới hạn JOIN, lọc tùy ý và tổng hợp trên tập dữ liệu rộng

> **Chương:** CQL và CqlTemplate  
> **Phạm vi:** Spring Data Cassandra, Apache Cassandra, `CqlTemplate`, `CassandraTemplate` và Java driver.  
> **Mục tiêu:** nhận diện đúng giới hạn của `JOIN`, `ALLOW FILTERING`, `GROUP BY` và phép đếm/tổng hợp trên nhiều partition; thiết kế bảng phục vụ truy vấn, tổng hợp trước dữ liệu và sử dụng `CqlTemplate` đúng phạm vi.

## 1. Bài toán: một dashboard cần truy vấn khác với lịch sử thiết bị

Hệ thống IoT lưu hàng triệu sự kiện nhiệt độ, pin yếu và mất kết nối mỗi ngày. API hiện tại đáp ứng tốt câu hỏi: “50 sự kiện mới nhất của **một thiết bị trong một ngày UTC**”. Product muốn thêm dashboard:

1. Hiển thị sự kiện kèm tên thiết bị và tên chi nhánh.
2. Lọc sự kiện `BATTERY_LOW` của **mọi thiết bị thuộc một chi nhánh** trong 24 giờ.
3. Vẽ biểu đồ **số cảnh báo theo giờ** và tìm **top 10 thiết bị có nhiều lỗi nhất trong 7 ngày**.

Nếu quen với SQL quan hệ, lập trình viên có thể muốn viết một câu có `JOIN`, `WHERE` linh hoạt, `GROUP BY` và `ORDER BY COUNT(*) DESC`. Cassandra không phải một công cụ thực thi truy vấn quan hệ/OLAP tổng quát. Dữ liệu được phân phối theo **partition key** và sắp xếp trong partition bằng **clustering columns**. Đường truy cập cần được thiết kế trước.

`CqlTemplate` giúp thực thi CQL, bind tham số, ánh xạ kết quả và dịch ngoại lệ; nó **không bổ sung JOIN hay một bộ tối ưu hóa truy vấn đa bảng**.

Sau bài này, bạn sẽ biết cách phân biệt một truy vấn có chi phí dự đoán được với một tác vụ scan rộng, đồng thời chọn mô hình dữ liệu và pipeline thích hợp với từng loại báo cáo.

## 2. Schema nguồn: khóa chỉ phục vụ một số mẫu đọc

Giả sử keyspace và bảng được tạo bằng migration. Ví dụ replication dưới đây chỉ dùng cho Cassandra một node:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    tenant_id   uuid,
    device_id   uuid,
    event_day   date,
    event_time  timestamp,
    event_id    uuid,
    site_id     uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        event_time, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC, event_id ASC
);

CREATE TABLE IF NOT EXISTS telemetry.devices_by_id (
    tenant_id    uuid,
    device_id    uuid,
    site_id      uuid,
    display_name text,
    PRIMARY KEY ((tenant_id), device_id)
);

CREATE TABLE IF NOT EXISTS telemetry.sites_by_id (
    tenant_id uuid,
    site_id   uuid,
    site_name text,
    PRIMARY KEY ((tenant_id), site_id)
);
~~~

Trong production nhiều node/datacenter, chọn `NetworkTopologyStrategy` và replication factor theo topology thật. Không chép cấu hình `SimpleStrategy`/RF=1 của ví dụ vào hạ tầng sản xuất.

| Thành phần bảng event | Vai trò | Điều hỗ trợ |
| --- | --- | --- |
| `tenant_id, device_id, event_day` | Partition key tổng hợp | Xác định nơi lưu các sự kiện của một thiết bị/ngày |
| `event_time DESC` | Clustering column thứ nhất | Event mới đứng trước trong partition |
| `event_id ASC` | Clustering column thứ hai | Phân biệt event có cùng millisecond |
| `site_id, event_type, payload` | Regular columns | Lưu thông tin; **không** tự tạo chỉ mục tra cứu toàn cluster |

Truy vấn đúng access pattern:

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Cassandra có đủ partition key để định tuyến; dữ liệu trong partition đã theo thứ tự clustering. Nhưng chỉ biết `site_id` và `event_type` **không** xác định các device partitions liên quan. Một bảng được tối ưu cho lịch sử thiết bị không tự phục vụ dashboard theo chi nhánh.

## 3. CQL không hỗ trợ JOIN giữa các bảng

CQL `SELECT` đọc từ **một bảng**. JOIN giữa event, device và site như SQL quan hệ **không hợp lệ** trong Cassandra:

~~~sql
-- PSEUDO-SQL KHÔNG CHẠY ĐƯỢC TRONG CASSANDRA:
SELECT e.event_time, d.display_name, s.site_name
FROM events_by_device_day e
JOIN devices_by_id d ON e.device_id = d.device_id
JOIN sites_by_id s ON e.site_id = s.site_id
WHERE e.event_type = 'BATTERY_LOW';
~~~

Cassandra cũng không có subquery kiểu SQL quan hệ để thay thế JOIN trong câu này. Lý do nằm ở mô hình phân tán: mỗi bảng có partition key riêng, dữ liệu có thể ở những node khác nhau. Truy vấn JOIN tùy ý có thể đòi hỏi fan-out, trao đổi dữ liệu lớn và xử lý trên nhiều node, trái với mục tiêu đọc có độ trễ dễ dự đoán của Cassandra.

**Không hỗ trợ JOIN ở tầng CQL không có nghĩa giao diện không thể kết hợp thông tin.** Có ba cách thông dụng:

- **Denormalization:** ghi sẵn tên thiết bị/site hoặc thông tin cần hiển thị vào bảng đọc của dashboard.
- **Lookup ở ứng dụng:** nếu chỉ có vài partition key xác định, đọc metadata bằng vài query và ghép ở service.
- **Hệ thống khác:** nếu liên kết dữ liệu rộng, lọc ad hoc và phân tích thường xuyên, đưa dữ liệu sang search/OLAP/warehouse.

Mỗi phương án có chi phí khác nhau; cần chọn theo access pattern, số row, độ trễ dữ liệu được chấp nhận và khả năng vận hành.

## 4. Khi nào application-side join hợp lý?

Với màn hình chi tiết **một event**, có thể thực hiện:

~~~text
1. Đọc event theo full primary key.
2. Đọc device bằng (tenant_id, device_id).
3. Đọc site bằng (tenant_id, site_id).
4. Ghép ba kết quả trong Java.
~~~

Đây là vài lượt đọc với **partition key đã biết**. Sau khi đo độ trễ và tần suất truy vấn, cách làm đó có thể hợp lý.

Nhưng nếu trang trả 1.000 event và service đọc metadata riêng cho từng event:

~~~text
1 query lấy danh sách sự kiện
+ 1.000 query lấy thông tin thiết bị
+ 1.000 query lấy thông tin chi nhánh
= có thể thành 2.001 lượt đọc
~~~

Đó là lỗi **N+1** ở tầng ứng dụng. Cần gom các ID trùng, cache kết quả, giới hạn số row hoặc tạo projection có sẵn thông tin hiển thị. Không nên chạy hàng nghìn request song song không giới hạn chỉ vì Java hỗ trợ async.

Nếu lưu `display_name` trong bảng cảnh báo, hãy chốt ý nghĩa dữ liệu: **tên tại thời điểm event xảy ra** hay **tên hiện tại**? Snapshot ít cần cập nhật lịch sử; tên hiện tại đòi hỏi lookup hoặc đồng bộ projection khi thiết bị đổi tên. Đây là quyết định nghiệp vụ, không phải tùy chọn của `CqlTemplate`.

## 5. Điều kiện WHERE phải đi cùng mô hình khóa

Câu đúng trên bảng event:

~~~sql
SELECT *
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25'
  AND event_time >= '2026-11-25T08:00:00Z'
  AND event_time <  '2026-11-25T10:00:00Z';
~~~

Đây là truy vấn một partition với dải clustering column đầu tiên.

Ngược lại:

~~~sql
-- Không phù hợp với primary key của bảng:
SELECT *
FROM telemetry.events_by_device_day
WHERE site_id = 33333333-3333-4333-8333-333333333333
  AND event_type = 'BATTERY_LOW';
~~~

Hai điều kiện ở đây nằm trên regular columns; không có partition key để Cassandra định vị các row cần thiết. Cassandra có thể từ chối truy vấn hoặc yêu cầu lọc thêm, tùy schema/index/phiên bản.

**Một query chạy được không chứng minh nó phù hợp tải.** Khi dataset lớn, phải ước lượng số partition bị chạm, số row phải đọc và kích thước dữ liệu được truyền, không chỉ số row cuối cùng trả cho client.

## 6. ALLOW FILTERING không phải cách tối ưu truy vấn

CQL có `ALLOW FILTERING`:

~~~sql
-- Câu lệnh minh họa; không dùng làm API production thường xuyên:
SELECT *
FROM telemetry.events_by_device_day
WHERE site_id = 33333333-3333-4333-8333-333333333333
  AND event_type = 'BATTERY_LOW'
ALLOW FILTERING;
~~~

Cú pháp này cho phép một số truy vấn thực hiện filtering phía server, kể cả khi Cassandra phải xem nhiều row/partition để tìm dữ liệu. Nhưng nó **không tạo index**, **không thay partition key**, và **không bảo đảm lượng công việc tỷ lệ với số kết quả cuối**.

Giả sử bảng chứa 100 triệu sự kiện, chỉ một phần rất nhỏ là `BATTERY_LOW` của một site. Để trả 50 event khớp điều kiện, hệ thống có thể phải kiểm tra một lượng dữ liệu lớn hơn nhiều so với 50 row.

### LIMIT không bảo vệ khỏi scan tốn kém

~~~sql
SELECT *
FROM telemetry.events_by_device_day
WHERE event_type = 'BATTERY_LOW'
LIMIT 50
ALLOW FILTERING;
~~~

`LIMIT 50` giới hạn **số kết quả trả về**, không có nghĩa Cassandra chỉ đọc đúng 50 row trên đĩa trước khi lọc. Nếu điều kiện ít khớp, query có thể tiêu tốn nhiều I/O và latency ngay cả khi response rất nhỏ.

Chỉ cân nhắc `ALLOW FILTERING` khi biết chắc tập dữ liệu nhỏ/hữu hạn hoặc phục vụ tác vụ chuyên biệt, có giới hạn và đã benchmark. Đừng biến nó thành giải pháp mặc định cho API nhiều người dùng.

## 7. Secondary index và SAI có giới hạn riêng

Cassandra cung cấp các phương án index khác nhau, bao gồm secondary index truyền thống và Storage-Attached Index (SAI) ở các phiên bản/nền tảng hỗ trợ. Index có thể giúp một số truy vấn lọc, nhưng không trở thành relational JOIN/OLAP engine.

Khi đánh giá index, hỏi:

1. Cluster đang dùng phiên bản Cassandra nào, index loại gì được hỗ trợ?
2. Cardinality và độ chọn lọc của cột `event_type`/`site_id` ra sao?
3. Một query qua index phải đi tới bao nhiêu node, bao nhiêu partition?
4. Có cần `ORDER BY event_time DESC` toàn cục không, hay vẫn phải merge?
5. Chi phí xây index, lưu trữ, ghi cập nhật và vận hành thế nào?
6. p95/p99 có đạt mục tiêu trên site/tenant có traffic lớn nhất và các đợt cảnh báo hàng loạt?

Thêm index trên `event_type` **không** tự giải quyết yêu cầu “50 event mới nhất của site” trên hàng nghìn partition ngày–thiết bị. Với truy vấn nghiệp vụ ổn định, bảng đọc theo site/type/day thường dễ giới hạn lượng dữ liệu đọc hơn.

## 8. GROUP BY của Cassandra không giống GROUP BY SQL

CQL có `GROUP BY` nhưng chỉ cho phép nhóm theo **primary key columns**, tuân theo thứ tự/điều kiện khóa. Nó không hỗ trợ nhóm tùy ý trên mọi regular column.

Ví dụ yêu cầu thống kê theo site và event type:

~~~sql
-- KHÔNG PHẢI CQL HỢP LỆ cho bảng nguồn:
SELECT site_id, event_type, COUNT(*)
FROM telemetry.events_by_device_day
GROUP BY site_id, event_type;
~~~

`site_id` và `event_type` là regular columns trong bảng này, nên không thể dùng như một phép GROUP BY tổng quát trên toàn cluster.

Những giới hạn cần nhớ:

- Chỉ nhóm theo các cột thuộc **primary key** theo quy tắc thứ tự của CQL.
- Khi một thành phần khóa đã bị ràng buộc bằng đẳng thức, CQL có quy tắc cho phép bỏ thành phần đó khỏi `GROUP BY`.
- Phép aggregate vẫn phải xử lý những row thuộc phạm vi query; `GROUP BY` không tự tạo bảng số liệu đã tính sẵn.
- Cassandra không cung cấp bộ công cụ phân tích hoàn chỉnh kiểu SQL warehouse với mọi `HAVING`, window functions và sắp xếp theo aggregate trên toàn bộ cluster.
- Truy vấn nhiều partition có thể phát sinh chi phí trên nhiều node; không nên suy ra `GROUP BY` cho phép tổng hợp rẻ chỉ vì cú pháp được chấp nhận.

Nhu cầu “số cảnh báo theo giờ, nhóm theo site” thường được phục vụ tốt hơn bằng **rollup table** được tính trước.

## 9. COUNT(*) có cú pháp nhưng không miễn phí

Một câu đếm **trong partition đã biết** là hợp lệ:

~~~sql
SELECT COUNT(*)
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25';
~~~

Cassandra vẫn phải xử lý các row phù hợp để tính con số. Nó không duy trì một phép đếm chính xác, tức thì và rẻ cho mọi tập dữ liệu.

| Yêu cầu | Dùng COUNT trên bảng nguồn? | Phương án |
| --- | --- | --- |
| Đếm vài trăm event trong một partition nhỏ | Có thể chấp nhận nếu tần suất ít và đã đo | `COUNT(*)` có partition key |
| Đếm 3 triệu row trong một partition rất lớn | Chi phí cao, không nên gọi thường xuyên | Tách bucket hoặc lưu summary |
| Đếm toàn bộ events của một tenant trong 30 ngày | Phải đọc nhiều partition | Pre-aggregation hoặc pipeline phân tích |
| Tổng cảnh báo từng giờ của site | Lọc/tổng hợp rộng trên bảng nguồn | Rollup theo site/type/day/hour |
| Top 10 device lỗi nhiều nhất tuần qua | Không có SQL aggregate top-N tổng quát | Snapshot top-N hoặc OLAP |

Đừng dùng `LIMIT` để “tăng tốc phép đếm toàn bộ”: giới hạn số row được xét hoặc số kết quả có thể khiến ngữ nghĩa của con số không còn là **total**.

Một phép đếm còn phụ thuộc vào thời điểm ghi/đọc, consistency, TTL/tombstone và dữ liệu đến muộn. Nếu sản phẩm yêu cầu chính xác tuyệt đối theo một cửa sổ thời gian, cần chốt cơ chế đồng bộ, phiên bản snapshot và đối soát.

## 10. SUM, AVG và các phép aggregate khác cũng phải đọc dữ liệu

CQL có các hàm tổng hợp như `SUM`, `AVG`, `MIN` và `MAX` tùy phiên bản và kiểu dữ liệu được hỗ trợ. Nhưng việc server trả một giá trị aggregate **không có nghĩa chỉ đọc một row**.

Ví dụ giả sử bảng đã có cột số `temperature_celsius` do migration bổ sung:

~~~sql
-- Chỉ minh họa khi cột temperature_celsius thực sự tồn tại:
SELECT AVG(temperature_celsius)
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-25';
~~~

Ngay cả với một partition, phép tính vẫn có thể đọc rất nhiều sự kiện. Nhu cầu “nhiệt độ trung bình toàn hệ thống mỗi giờ trong năm” đòi hỏi một mô hình tổng hợp/phân tích khác; không thể chỉ tăng timeout cho `AVG`.

Cần làm rõ: tính **trực tiếp trên dữ liệu thô** hay đọc **số liệu đã tổng hợp**? Có chấp nhận lag không? Event đến muộn được bổ sung vào bucket thế nào? Số liệu cũ cần sửa/xóa thì có được tính lại không? Những câu hỏi đó quyết định kiến trúc.

## 11. ORDER BY và LIMIT không thực hiện top-N toàn cluster

Với bảng `events_by_device_day`, `CLUSTERING ORDER BY (event_time DESC, event_id ASC)` chỉ sắp các row **trong partition**. Không viết được truy vấn tổng quát:

~~~sql
-- Ý định kiểu SQL, không phải access pattern hợp lệ:
SELECT *
FROM telemetry.events_by_device_day
ORDER BY event_time DESC
LIMIT 50;
~~~

Cassandra không gom mọi partition về một nơi để sắp xếp toàn cluster như một công cụ quan hệ.

Phân biệt rõ:

- `LIMIT 50`: giới hạn row trả về trong query.
- **Fetch page size:** số row mục tiêu mà driver lấy ở từng lần fetch; không phải total limit.
- **Paging state:** trạng thái đọc tiếp cùng query; không phải offset cho trang bất kỳ.
- `PER PARTITION LIMIT`: giới hạn theo partition trong những truy vấn phù hợp; không phải top-N toàn cục.
- `ORDER BY`: gắn với thứ tự clustering, không sắp xếp tùy ý theo regular column hoặc aggregate.

Nếu muốn “50 event mới nhất của một site”, nên có một bảng đọc theo site và time bucket, rồi ghép một số bucket đã biết ở ứng dụng.

## 12. Bảng đọc theo site/type/day thay cho lọc rộng

Access pattern Q2:

~~~text
Input: tenantId, siteId, eventType, from/to, cursor
Sort:  event_time DESC, device_id ASC, event_id ASC
Limit: 50 cảnh báo/trang
Scope: tối đa 24 giờ, theo UTC
~~~

Bảng denormalized:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.alerts_by_site_type_day (
    tenant_id    uuid,
    site_id      uuid,
    event_type   text,
    event_day    date,
    event_time   timestamp,
    device_id    uuid,
    event_id     uuid,
    display_name text,
    message      text,
    PRIMARY KEY (
        (tenant_id, site_id, event_type, event_day),
        event_time, device_id, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC, device_id ASC, event_id ASC
);
~~~

Giải thích:

- `tenant_id + site_id + event_type + event_day` tạo partition phù hợp với filter API.
- `event_time DESC` đáp ứng sắp xếp mới nhất trước trong partition.
- `device_id + event_id` tránh ghi đè event khác nhau cùng timestamp và giữ thứ tự có tie-breaker.
- `display_name` phục vụ UI mà không cần JOIN mỗi row.
- `message` là projection nhỏ, không cần sao chép toàn bộ payload nếu giao diện không dùng.

Query:

~~~sql
SELECT event_time, device_id, event_id, display_name, message
FROM telemetry.alerts_by_site_type_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND site_id = 33333333-3333-4333-8333-333333333333
  AND event_type = 'BATTERY_LOW'
  AND event_day = '2026-11-25'
LIMIT 50;
~~~

Query có đủ partition key, không cần `ALLOW FILTERING`. Với cửa sổ 24 giờ qua nửa đêm UTC, đọc tối đa hai partition ngày rồi ghép ở ứng dụng, giữ continuation state đúng cho từng bucket.

Nếu site có lưu lượng cảnh báo rất lớn, bucket ngày có thể trở thành hot partition; cần đo byte/partition, row count, p95/p99 và burst traffic để quyết định bucket giờ hoặc shard. Shard làm tăng số partition và độ phức tạp khi merge.

## 13. Denormalization và đồng bộ dữ liệu giữa nhiều bảng

Một bảng projection không tự nhận dữ liệu từ bảng nguồn chỉ vì chúng có cột giống nhau.

~~~mermaid
flowchart LR
    A["Thiết bị gửi event"] --> B["Ingest / event log"]
    B --> C["events_by_device_day"]
    B --> D{"Event cần dashboard?"}
    D -->|Có| E["alerts_by_site_type_day"]
    D -->|Không| F["Bỏ qua projection"]
    E --> G["API cảnh báo theo site"]
    C --> H["API timeline theo device"]
~~~

Nếu ghi bảng nguồn thành công nhưng projector lỗi, bảng dashboard tạm thiếu dữ liệu. Nên có nguồn event có thể replay, event ID ổn định, retry idempotent, checkpoint và job reconciliation. Hai lệnh ghi hai bảng/partition **không tự tạo transaction ACID đa bảng**.

Giá trị consistency như `LOCAL_QUORUM` quyết định số replica cần phản hồi cho từng read/write; chúng **không tự đẩy sự kiện sang bảng projection** khi consumer còn chậm. Cần theo dõi projection lag và chốt độ trễ dữ liệu mà sản phẩm chấp nhận.

## 14. CqlTemplate khác CassandraTemplate và CqlSession ở đâu?

| API | Cấp độ | Dùng khi |
| --- | --- | --- |
| `CqlTemplate` | Thực thi CQL, bind tham số, ánh xạ row bằng callback | Cần kiểm soát câu CQL và projection nhẹ |
| `CassandraTemplate` | Mapping entity, `Query`/`Criteria`, CRUD | Nghiệp vụ thiên về domain entity |
| `CassandraRepository` | Interface CRUD và query methods | Truy vấn ổn định, đơn giản |
| `CqlSession` | Java driver, tùy chọn statement/paging/timeout chi tiết | Cần điều khiển thấp hơn và xử lý paging state |

`CqlTemplate` thuộc package `org.springframework.data.cassandra.core.cql.CqlTemplate`. Nó thực thi CQL, quản lý tài nguyên quanh thao tác và dịch exception Cassandra sang `DataAccessException` của Spring. `CassandraTemplate` thiên về mapping entity.

Cả hai vẫn phải tuân theo partition key và giới hạn CQL. Nếu một truy vấn sai mô hình, đổi từ repository sang template **không biến nó thành truy vấn hiệu quả**.

Spring Boot với starter Cassandra có thể auto-configure `CqlTemplate`, `CassandraTemplate` và `CqlSession`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-cassandra'
}
~~~

Ví dụ kết nối (datacenter phải đúng môi trường thật):

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: telemetry
    schema-action: none
~~~

Tạo schema qua migration trước khi dùng template. `schema-action: none` không tự tạo keyspace/bảng.

## 15. Đọc một partition bằng CqlTemplate và RowMapper

Ví dụ Java dùng bind markers, không nối giá trị từ HTTP vào CQL:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.CqlTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class EventTimelineDao {
    private final CqlTemplate cqlTemplate;

    public EventTimelineDao(CqlTemplate cqlTemplate) {
        this.cqlTemplate = cqlTemplate;
    }

    public record EventView(
        Instant time, UUID eventId, String type, String payload
    ) { }

    public List<EventView> latest(
            UUID tenantId, UUID deviceId, LocalDate utcDay) {

        String cql =
            "SELECT event_time, event_id, event_type, payload "
          + "FROM telemetry.events_by_device_day "
          + "WHERE tenant_id = ? AND device_id = ? "
          + "AND event_day = ? LIMIT 50";

        return cqlTemplate.query(
            cql,
            (row, rowNum) -> new EventView(
                row.getInstant("event_time"),
                row.getUuid("event_id"),
                row.getString("event_type"),
                row.getString("payload")
            ),
            tenantId, deviceId, utcDay
        );
    }
}
~~~

`query(String, RowMapper<T>, Object... args)` dùng prepared/bind parameters, trả kết quả đã ánh xạ. Nó không JOIN bảng nào: mỗi `row` là row từ câu `SELECT` hợp lệ trên **một bảng**.

Truy vấn chỉ nhắm một partition có đủ khóa và `LIMIT 50`. Nếu cần phân trang nhiều request, sử dụng paging state của driver hoặc `Slice`/`CassandraPageRequest` trong Spring Data. `List` kết quả không tự chứa continuation token. Đừng đọc toàn bộ hàng triệu row vào List vì có fetch paging ở driver.

## 16. CqlTemplate.queryForObject có thể đếm nhưng không làm COUNT rẻ

Ví dụ chỉ nên dùng trong partition đã được giới hạn và với tần suất hợp lý:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.CqlTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class EventCountDao {
    private final CqlTemplate cqlTemplate;

    public EventCountDao(CqlTemplate cqlTemplate) {
        this.cqlTemplate = cqlTemplate;
    }

    public long countDeviceDay(
            UUID tenantId, UUID deviceId, LocalDate day) {

        Long value = cqlTemplate.queryForObject(
            "SELECT COUNT(*) FROM telemetry.events_by_device_day "
          + "WHERE tenant_id = ? AND device_id = ? "
          + "AND event_day = ?",
            Long.class,
            tenantId, deviceId, day
        );

        return value == null ? 0 : value;
    }
}
~~~

`queryForObject` chuyển kết quả một row/một cột sang `Long`, nhưng không thay đổi độ phức tạp của `COUNT(*)`. Nó vẫn phải xử lý dữ liệu thuộc phạm vi đếm.

Ví dụ nguy hiểm:

~~~java
// Anti-pattern: không gọi thường xuyên trên bảng dữ liệu lớn.
Long total = cqlTemplate.queryForObject(
    "SELECT COUNT(*) FROM telemetry.events_by_device_day",
    Long.class
);
~~~

Dù cú pháp CQL hợp lệ, đây là phép đếm trên bảng rộng, có thể tạo tải rất lớn. Đừng dùng để tạo chỉ số “tổng event toàn hệ thống” mỗi khi người dùng tải dashboard.

## 17. CqlTemplate.execute phù hợp DML có khóa nhưng không sửa access pattern

Ví dụ cập nhật tên thiết bị bằng đúng partition key và clustering key của bảng metadata:

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.CqlTemplate;

public class DeviceNameWriter {
    private final CqlTemplate template;

    public DeviceNameWriter(CqlTemplate template) {
        this.template = template;
    }

    public void rename(UUID tenantId, UUID deviceId, String newName) {
        if (tenantId == null || deviceId == null
                || newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Thông tin không hợp lệ");
        }

        template.execute(
            "UPDATE telemetry.devices_by_id "
          + "SET display_name = ? "
          + "WHERE tenant_id = ? AND device_id = ?",
            newName, tenantId, deviceId
        );
    }
}
~~~

`CqlTemplate.execute` thực thi statement với giá trị bind. Nhưng không có phương thức nào của template biến một CQL thiếu partition key thành đường đọc nhanh. Nếu cần consistency/page size/timeout đặc biệt, phải xem cấu hình driver/template của phiên bản đang dùng.

## 18. Tạo rollup table cho biểu đồ cảnh báo theo giờ

Product cần “số `BATTERY_LOW` của site S trong từng giờ của ngày D”. Nếu đếm lại từ mọi raw event ở mỗi request, dashboard sẽ đắt. Một bảng read model chứa **số liệu đã tính sẵn** có thể phù hợp:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry.alert_counts_by_site_day (
    tenant_id     uuid,
    site_id       uuid,
    event_type    text,
    metric_day    date,
    hour_utc      timestamp,
    event_count   bigint,
    calculated_at timestamp,
    PRIMARY KEY (
        (tenant_id, site_id, event_type, metric_day),
        hour_utc
    )
) WITH CLUSTERING ORDER BY (hour_utc ASC);
~~~

Mỗi partition đại diện site/type/ngày, chứa một row cho mỗi giờ được tổng hợp. Ví dụ ghi snapshot:

~~~sql
INSERT INTO telemetry.alert_counts_by_site_day (
    tenant_id, site_id, event_type, metric_day,
    hour_utc, event_count, calculated_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    33333333-3333-4333-8333-333333333333,
    'BATTERY_LOW',
    '2026-11-25',
    '2026-11-25T08:00:00Z',
    126,
    '2026-11-25T08:05:00Z'
);
~~~

Dashboard đọc:

~~~sql
SELECT hour_utc, event_count
FROM telemetry.alert_counts_by_site_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND site_id = 33333333-3333-4333-8333-333333333333
  AND event_type = 'BATTERY_LOW'
  AND metric_day = '2026-11-25';
~~~

Khi có vài chục row tổng hợp, việc tải biểu đồ ổn định hơn nhiều so với quét toàn bộ event. Đổi lại cần pipeline tính toán, xử lý retry và dữ liệu đến muộn.

### Không tăng bigint bằng phép cộng như SQL thông thường

CQL không cho `UPDATE event_count = event_count + 1` với một cột `bigint` bình thường như ý tưởng SQL. Phép cộng kiểu counter thuộc **counter columns** và có ngữ nghĩa khác, không tự bảo đảm idempotent nếu event bị replay.

Một cách thiết kế vững hơn là:

1. Dùng event ID ổn định và nguồn event có thể phát lại.
2. Bộ xử lý luồng/batch chống trùng hoặc đối soát theo hợp đồng đã chốt.
3. Tính tổng theo `(tenant, site, type, hour)`.
4. Upsert **snapshot đã tính** vào đúng full primary key.
5. Giữ version/thời điểm và quy tắc chống snapshot cũ ghi đè mới.
6. Điều chỉnh bucket khi late event hoặc sửa/xóa event, theo dõi lag và sai số.

Counter table có thể phù hợp cho một số workload, nhưng mỗi phép tăng không idempotent dưới retry không kiểm soát. Không dùng counter làm giải pháp mặc định cho báo cáo cần độ chính xác tuyệt đối.

## 19. Top-N theo 7 ngày cần xử lý ngoài một SELECT CQL

Yêu cầu: “Top 10 device có nhiều `DISCONNECTED` nhất trong bảy ngày gần đây”.

Một ý tưởng kiểu SQL:

~~~sql
-- KHÔNG PHẢI truy vấn CQL phù hợp trên bảng nguồn:
SELECT device_id, COUNT(*) AS n
FROM telemetry.events_by_device_day
WHERE event_type = 'DISCONNECTED'
GROUP BY device_id
ORDER BY n DESC
LIMIT 10;
~~~

Không có đường truy cập theo event type và không có aggregate/sort top-N toàn cluster như SQL warehouse.

Phương án thực tế:

- Tổng hợp các event theo device/site/ngày hoặc cửa sổ giờ trong stream/batch.
- Tính top-N cho một site/tenant và khoảng thời gian được chốt.
- Ghi **snapshot top-N** vào bảng read model hoặc kho analytics.
- API đọc bảng snapshot đã có thứ tự ổn định (`count DESC` rồi `device_id ASC` để phá hòa).
- Ghi rõ thời điểm snapshot, độ trễ cập nhật và cách xử lý event đến muộn.

Nếu product muốn chọn bất kỳ tổ hợp điều kiện, thời gian dài và nhiều chiều nhóm, một search engine/warehouse/OLAP có thể phù hợp hơn việc tạo nhiều bảng Cassandra cho mọi tổ hợp.

## 20. Fan-out nhiều partition phải có giới hạn

Một giải pháp tạm cho dashboard site là lấy danh sách thiết bị rồi truy vấn mỗi device/day:

~~~text
2.000 thiết bị × 2 ngày
= có thể lên tới 4.000 partition reads
+ lookup metadata
+ merge/sort kết quả
~~~

Cách này có thể gây áp lực lớn lên coordinator, mạng, CPU, bộ nhớ ứng dụng và tail latency. Với rất ít thiết bị và tần suất truy vấn thấp, fan-out có thể chấp nhận nếu đã đo; với dashboard thường xuyên, nên dùng projection.

Nếu fan-out là bắt buộc:

- Chốt giới hạn tối đa device, bucket ngày, row và concurrency.
- Truy vấn theo đúng partition key của từng nguồn.
- Merge các luồng đã được sắp theo clustering time; tránh giữ mọi row vào RAM.
- Dùng paging state riêng của từng partition; không tái sử dụng state giữa filter/bucket khác.
- Cố định `from`/`to` khi phân trang nhiều request và kiểm tra quyền tenant/site.
- Quan sát p95/p99, request timeout và số partition mỗi API.
- Có ngưỡng chuyển sang read model khi tải tăng.

`CqlTemplate` có thể giúp thực thi các query thành phần, nhưng việc JOIN/merge ở ứng dụng vẫn là trách nhiệm của service.

## 21. Truy vấn rộng offline khác truy vấn rộng online

Không phải mọi lần đọc nhiều row đều sai. Backfill, xuất dữ liệu lịch sử và analytics có thể buộc đọc dữ liệu trên nhiều partition. Vấn đề là **để các công việc này tranh tài nguyên với HTTP API tương tác**, hoặc đọc không giới hạn, không checkpoint và không đo ảnh hưởng cluster.

Với offline job, có thể chọn:

- Đọc danh sách partition/bucket đã biết từ catalog có kiểm soát.
- Phân đoạn token range với công cụ/pipeline phù hợp để scan dữ liệu, giới hạn concurrency.
- Sử dụng Spark/ETL, CDC hoặc event log để chuyển dữ liệu sang data lake/warehouse.
- Chia công việc thành checkpoint có thể resume sau lỗi.
- Đặt thời gian chạy, throughput, số row/batch và ngân sách cluster riêng.
- Theo dõi tác động lên latency online, compaction, I/O và error rate.

**Driver fetch page size nhỏ không biến việc đọc 200 triệu row thành tác vụ nhỏ.** Nó chỉ giới hạn lượng row cho từng lần fetch; nếu client tiếp tục đọc đến hết thì toàn bộ dữ liệu vẫn được xử lý.

## 22. Bảng lựa chọn theo access pattern

| Mục tiêu | Phương án ưu tiên | Điều cần tránh |
| --- | --- | --- |
| Lịch sử một thiết bị/ngày | Partition key đầy đủ, clustering và `LIMIT`/paging | `SELECT *` toàn cluster rồi filter Java |
| Chi tiết một event theo full key | `CassandraRepository.findById`/CQL full key | Lọc chỉ bằng regular column |
| Tên device trong trang chi tiết | Một số lookup có key hoặc snapshot | JOIN CQL |
| Cảnh báo một site/type/day | Bảng `alerts_by_site_type_day` | `ALLOW FILTERING` trên event table |
| Biểu đồ count theo giờ | Bảng rollup `alert_counts_by_site_day` | `COUNT(*)` raw mỗi request |
| Top-N theo tuần | Pipeline aggregate + snapshot | `GROUP BY` và `ORDER BY COUNT` toàn cluster |
| Truy vấn ad hoc nhiều chiều | Search/OLAP/warehouse | Cố dùng CQL như SQL warehouse |
| Backfill nhiều năm | Job offline có checkpoint và giới hạn tải | HTTP request synchronous không giới hạn |

Chi phí thêm bảng projection nằm ở ghi/đồng bộ/backfill/storage. Đổi lại, API quan trọng có thể đọc một số partition nhỏ với latency dự đoán được. Quyết định dựa vào **tổng chi phí** và yêu cầu nghiệp vụ.

## 23. Kiểm soát hiệu năng và vận hành

Trước khi đưa query mới lên production, đo:

| Nhóm | Chỉ số | Mục đích |
| --- | --- | --- |
| API | p50/p95/p99 latency theo query ID | Phân biệt timeline, dashboard, analytics |
| Driver | timeout, unavailable, retry, page fetch | Phát hiện fan-out, retry storm |
| Truy vấn | số partition chạm, row/byte đọc và trả | Chi phí thật so với kết quả cuối |
| Cluster | CPU, disk I/O, tombstone scan, compaction | Tác động tới các workload khác |
| Mô hình | row/partition, kích thước partition lớn nhất | Nhận diện bucket nóng |
| Index | scan/selectivity, chi phí xây và cập nhật | Kiểm tra index có hiệu quả không |
| Pipeline | lag, replay, duplicate, reconciliation drift | Độ mới và tính đúng của read model |

Đừng dùng thử nghiệm vài trăm row local để khẳng định query chạy tốt khi có hàng trăm triệu sự kiện. Nên nạp workload đại diện, kể cả site có nhiều thiết bị nhất và những đợt cảnh báo đồng loạt.

Cần phân biệt **timeout phía client** với Cassandra server báo lỗi: tăng timeout không sửa missing partition key hoặc đếm/quét quá nhiều dữ liệu. Nếu xuất hiện retry tăng, nó còn có thể đẩy tải cluster lên cao hơn.

## 24. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| `JOIN` bị lỗi cú pháp | CQL không hỗ trợ JOIN | Denormalization, lookup bounded hoặc analytics |
| `WHERE event_type` không được hỗ trợ | Không có đường định tuyến/index phù hợp | Bảng đọc theo access pattern |
| `ALLOW FILTERING` chạy nhưng p99 rất xấu | Quét nhiều row để lấy ít kết quả | Sửa partition key/read model |
| `LIMIT 50` vẫn gây timeout | LIMIT không giới hạn chi phí lọc trước đó | Tránh quét rộng |
| `COUNT(*)` làm cluster tăng tải | Đếm trên dữ liệu lớn | Rollup/stream aggregate |
| `GROUP BY site_id` không hợp lệ | Regular column, sai quy tắc CQL | Group trong pipeline hoặc bảng số liệu |
| `ORDER BY event_time` không sắp toàn cluster | Chỉ theo clustering/order phù hợp | Read model và merge bounded |
| `CqlTemplate.query` trả quá nhiều row | Truy vấn không giới hạn/đọc hết paging | Giới hạn query và cursor |
| 2.001 query metadata cho một trang | N+1 application lookup | Cache/dedup/projection |
| Counter đếm sai sau retry | Increment bị phát lại | Idempotency và reconciliation |
| Projection có lag | Consumer chậm/lỗi | Quan sát lag và replay, không chỉ đổi consistency |
| Cursor trang 2 sai | Thay đổi filter/window hoặc paging state | Token ràng buộc query, cursor theo bucket |

## 25. Mẫu đánh giá một yêu cầu truy vấn mới

~~~text
Query ID:             Q2 — BATTERY_LOW theo site
Input:                tenantId, siteId, eventType, from/to, cursor
Output:               50 cảnh báo + thông tin hiển thị
Sort:                 event_time DESC, device_id ASC, event_id ASC
Time window:          tối đa 24h theo UTC
Candidate table:      alerts_by_site_type_day
Partition key:        tenant + site + eventType + eventDay
Clustering:           eventTime DESC, deviceId ASC, eventId ASC
Expected partitions:  tối đa hai bucket UTC cho 24h
SLO:                  p95/timeout cần được chốt với product
Data freshness:       lag projection chấp nhận được
Risks:                burst traffic, hot partition, backfill, retry
Validation:           không ALLOW FILTERING, paging đúng, đối soát PASS
~~~

Trình tự áp dụng:

1. Chốt input, filter, sort, thời gian, page size, quyền và độ mới dữ liệu.
2. Đối chiếu từng filter với partition key/clustering key của bảng hiện tại.
3. Ước lượng số partition, số row và byte cần đọc trong tình huống xấu nhất.
4. Đánh giá lookup bounded, denormalization, index hoặc analytics.
5. Chọn schema/pipeline, quy tắc retry/idempotency, TTL và backfill.
6. Test với dữ liệu đại diện, đặt SLO và quan sát rollout.
7. Ghi lại access pattern nào **không** được hỗ trợ; không mở rộng `WHERE` vô hạn.

## 26. Bài tập vận dụng

### Bài A — JOIN theo thiết bị và site

Màn hình chi tiết một event cần thêm tên thiết bị và tên site. Hãy so sánh vài lookup có partition key với việc ghi sẵn thông tin snapshot vào bảng đọc. Khi nào việc lookup trở thành N+1 nguy hiểm?

**Gợi ý:** một event có thể chấp nhận vài lookup; 1.000 event và hai query metadata cho mỗi event có thể thành hàng nghìn request. Cần dedup/cache hoặc projection.

### Bài B — ALLOW FILTERING cùng LIMIT

Product muốn 50 `BATTERY_LOW` mới nhất toàn hệ thống từ bảng theo device/day; developer thêm `ALLOW FILTERING LIMIT 50`. Giải thích vì sao query vẫn có thể quét rộng và đề xuất partition key cho bảng theo site/type/day.

**Gợi ý:** `LIMIT` chỉ khống chế kết quả, không giúp xác định partition cần đọc; phải thiết kế khóa theo input người dùng biết.

### Bài C — Đếm dữ liệu lớn

Một partition có 2.000 event, partition khác có 3 triệu event. Hai phép `COUNT(*)` có cùng chi phí không? Khi nào nên dùng rollup?

**Gợi ý:** aggregate cần xử lý dữ liệu được tính; query thường xuyên hoặc partition lớn nên dùng số liệu đã tổng hợp.

### Bài D — GROUP BY không theo primary key

`site_id` và `event_type` là regular columns. Tại sao không thể viết một `GROUP BY site_id, event_type` như SQL warehouse? Vẽ bảng read model cho số liệu theo site/type/hour.

**Gợi ý:** `GROUP BY` CQL chỉ dùng các cột primary key theo quy tắc khóa, không nhóm tùy ý trên toàn cluster.

### Bài E — CqlTemplate

Viết `CqlTemplate.query` với ba bind values để đọc 50 event của một tenant/device/day và ánh xạ `event_time`, `event_id`, `event_type` vào DTO. Vì sao `RowMapper` không tự tạo JOIN hoặc đổi partition key?

**Gợi ý:** tham khảo `EventTimelineDao`; Java map kết quả sau khi Cassandra đã thực thi CQL.

### Bài F — Rollup và duplicate

Consumer nhận sự kiện E hai lần vì retry. Nếu tăng counter mỗi lần, số đếm có thể sai thế nào? Đề xuất dùng event ID ổn định, snapshot rollup, checkpoint và reconciliation.

**Gợi ý:** counter increment không idempotent với at-least-once; cần dedup/replay hoặc cơ chế tính lại bucket.

### Bài G — Top-N tuần qua

Sản phẩm muốn 10 thiết bị lỗi nhiều nhất trong bảy ngày, có thứ tự và trang tiếp. Vì sao `ORDER BY COUNT(*) DESC OFFSET 10` không phù hợp? Đề xuất pipeline batch/stream và bảng snapshot top-N.

**Gợi ý:** chốt window, snapshot version, tie-breaker và continuation token; hoặc dùng OLAP.

### Bài H — Online so với offline

Một job cần đọc 100 triệu event để backfill, còn API chỉ trả 50 row. Hãy chọn chiến lược đọc cho từng loại, giới hạn concurrency và chỉ số đo. Vì sao cả hai không nên dùng cùng query không giới hạn?

**Gợi ý:** online phải đọc đúng partition; offline có thể scan có checkpoint và ngân sách tải riêng, không tranh tài nguyên vô hạn.

**Tiêu chí đạt:** người học chỉ ra giới hạn JOIN/ALLOW FILTERING/GROUP BY, lý giải chi phí `COUNT(*)`, viết đúng `CqlTemplate` với bind parameters, thiết kế projection/rollup có partition key phù hợp và phân biệt API tương tác với analytics.

## 27. Checklist trước khi đưa truy vấn lên production

- [ ] Có đầy đủ partition key hoặc index phù hợp đã benchmark?
- [ ] Số partition, số row, byte và page fetch lớn nhất đã được ước lượng?
- [ ] Không phụ thuộc `ALLOW FILTERING` cho request thường xuyên trên bảng lớn?
- [ ] Không dùng `COUNT(*)`/`GROUP BY` rộng làm API dashboard?
- [ ] `ORDER BY` có khớp clustering và phạm vi partition?
- [ ] `LIMIT`, fetch page và paging state được phân biệt đúng?
- [ ] Nếu cần JOIN, đã chọn projection, lookup bounded hoặc analytics?
- [ ] Bảng đọc mới có partition key, bucket và tie-breaker hợp lý?
- [ ] Pipeline có replay, idempotency, backfill và reconciliation?
- [ ] Đã chốt consistency, độ mới dữ liệu, retention và quyền tenant/site?
- [ ] Đã đo p95/p99, timeout và burst traffic trên dữ liệu đại diện?
- [ ] Có dashboard vận hành, canary và phương án rollback?

## Tài liệu tham khảo

- [Apache Cassandra — Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): giới hạn `JOIN`, `GROUP BY`, `WHERE`, `ORDER BY`, `LIMIT` và `ALLOW FILTERING`.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/cql_singlefile.html): cú pháp `SELECT`, aggregation và primary key.
- [Apache Cassandra — Query-driven Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html): denormalization và thiết kế theo access pattern.
- [Spring Data Cassandra — CQL Template API](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html): `CqlTemplate`, `RowMapper`, bind parameters và execute.
- [Spring Data Cassandra — CqlTemplate Javadoc](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/CqlTemplate.html): overload `query` và `queryForObject`.
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): đối chiếu API entity mapping.
- [Spring Boot — Cassandra](https://docs.spring.io/spring-boot/reference/data/nosql.html): starter và auto-configuration.
