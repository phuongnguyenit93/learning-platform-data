# Thực hành tổng hợp: Thiết kế bảng lịch sử hoạt động theo tenant và bucket thời gian

## 1. Bối cảnh và mục tiêu

Một ứng dụng SaaS nhiều khách hàng (multi-tenant) cần lưu lịch sử hoạt động: đăng nhập, tạo đơn hàng, đổi cấu hình, cập nhật quyền và các thao tác kiểm toán. Mỗi bản ghi thuộc đúng một `tenant_id`; API thường hiển thị hoạt động mới nhất trước và cho phép lọc theo khoảng thời gian. Hệ thống sử dụng **Apache Cassandra** vì cần ghi liên tục, mở rộng qua nhiều node và chấp nhận truy vấn có quy luật rõ ràng.

Bài thực hành này kết hợp **kiến trúc phân tán, wide-column, khóa phân vùng, thiết kế bảng theo truy vấn, CQL, replication, consistency, compaction, repair, xử lý lỗi và Java Driver**. Đích đến là một thiết kế có thể giải thích, chạy thử và vận hành, thay vì chỉ tạo được bảng.

**Giả định bài toán** (điều chỉnh các con số trong môi trường thật):

- API chính: `GET /tenants/{tenantId}/activities?from=...&to=...&limit=50&cursor=...`.
- Dữ liệu chỉ được đọc trong phạm vi một tenant; mặc định trả theo `occurred_at` giảm dần.
- Giữ bản ghi trong **90 ngày tính từ thời điểm ghi vào Cassandra**; không cần sửa từng sự kiện sau khi phát hành.
- Thời gian sự kiện và bucket đều chuẩn hóa theo **UTC**; API nhận khoảng nửa mở `[from, to)`.
- Một tenant có thể có vài trăm đến hàng triệu sự kiện/ngày; tenant lớn có thể phát sinh đột biến tải.
- API không cần thống kê toàn cục hoặc tìm mọi sự kiện theo `action` mà không có tenant và thời gian.

**Tiêu chí nghiệm thu:** truy vấn phổ biến chạy theo khóa phân vùng, không dùng `ALLOW FILTERING`; một tenant không lẫn dữ liệu của tenant khác; một partition không tăng vô hạn; API đi qua nhiều ngày theo đúng thứ tự; người triển khai giải thích được consistency, TTL, compaction và cách xử lý replica lỗi.

## 2. Chuyển yêu cầu đọc thành mô hình wide-column

Trong Cassandra, **partition key** quyết định vị trí dữ liệu trên các replica theo token; **clustering columns** sắp thứ tự các hàng *bên trong cùng một partition*. Không nên bê nguyên sơ đồ quan hệ (một bảng theo thực thể và truy vấn tùy ý) sang Cassandra.

| Truy vấn cần phục vụ | Đường truy cập | Hàm ý thiết kế |
| --- | --- | --- |
| 50 hoạt động gần nhất của tenant A | Các bucket thời gian gần nhất của A, theo thứ tự mới đến cũ | Đưa tenant và bucket vào partition key; sắp sự kiện giảm dần |
| Hoạt động của A trong 3 ngày | Lần lượt đọc các bucket cắt khoảng `[from, to)` | Mỗi truy vấn CQL chỉ nhắm một partition, ghép kết quả ở ứng dụng |
| Trang kế tiếp của lịch sử A | Tiếp tục partition và paging state hiện tại; sau đó chuyển bucket kế tiếp | Cursor API lưu bucket hiện tại và trạng thái phân trang |
| Tìm mọi sự kiện `LOGIN` của tất cả tenant | **Không nằm trong API yêu cầu** | Cần mô hình truy vấn/bảng riêng nếu sau này có yêu cầu này |

Mỗi sự kiện tối thiểu mang các trường:

| Trường | Vai trò |
| --- | --- |
| `tenant_id` | Định danh tenant; bắt buộc lấy từ ngữ cảnh đã xác thực |
| `bucket_day` | Ngày UTC tính từ `occurred_at`, dùng để chia partition |
| `occurred_at` | Thời điểm hoạt động xảy ra, dùng để sắp xếp và lọc |
| `event_id` | UUID ổn định từ nguồn phát; phân biệt sự kiện trùng thời điểm và giúp ghi lại an toàn |
| `actor_id`, `action`, `object_type`, `object_id` | Thông tin cần hiển thị trong danh sách |
| `details_json` | Payload nhỏ, có giới hạn kích thước; không chứa tài liệu lớn tùy ý |

Khóa chính cho phiên bản cơ bản:

~~~sql
PRIMARY KEY ((tenant_id, bucket_day), occurred_at, event_id)
~~~

Cặp `(tenant_id, bucket_day)` là **composite partition key**. Hai cột `occurred_at` và `event_id` là **clustering columns**. Một tenant có nhiều partition, mỗi ngày một partition. Các sự kiện của hai tenant trùng ngày vẫn nằm ở hai partition riêng biệt. Việc đưa `event_id` vào khóa giúp hai sự kiện có cùng millisecond không ghi đè lẫn nhau.

**Giới hạn cần nhớ:** Cassandra không tự nối các bucket để tạo một kết quả sắp xếp toàn cục. Một truy vấn thiếu `bucket_day` không thể dùng khóa trên để lấy “mọi hoạt động của tenant A”. Logic duyệt bucket thuộc ứng dụng.

## 3. Chọn kích thước bucket và ước lượng partition

Bucket không có kích thước tốt nhất cho mọi tenant. Ước lượng thô:

~~~text
dung_lượng_partition ≈
  số_sự_kiện_tenant_mỗi_ngày × byte_mỗi_sự_kiện
  / số_bucket_mỗi_ngày
  / số_shard_mỗi_bucket
~~~

Ví dụ tenant ghi **2.400.000 sự kiện/ngày**, mỗi hàng trung bình khoảng **1 KiB** (ước lượng ban đầu, gồm payload nhưng chưa tính hết overhead). Bucket ngày tạo khoảng **2.344 MiB/partition**; bucket giờ tạo khoảng **98 MiB/partition**; bucket giờ với **4 shard** còn khoảng **24,4 MiB/partition** nếu phân bố đều. Cần đo kích thước thật và xét giờ cao điểm vì tải không đều.

Để bắt đầu thực hành, chọn **bucket ngày** vì ít partition phải đọc và dễ kiểm tra. Khi đo thấy một số tenant tạo partition quá lớn hoặc có một partition nhận quá nhiều ghi, chuyển tenant nóng sang **bucket giờ** và/hoặc **shard**. Ngưỡng vận hành thực tế phụ thuộc hàng, workload và phiên bản; có thể lấy mục tiêu thăm dò ở mức vài chục MiB/partition rồi hiệu chỉnh bằng số liệu, thay vì coi đó là giới hạn cứng của Cassandra.

| Phương án | Ưu điểm | Chi phí |
| --- | --- | --- |
| Theo ngày, không shard | Đọc 7 ngày chỉ khoảng 7 partition/tenant | Tenant lớn có thể tạo partition lớn và điểm nóng |
| Theo giờ, không shard | Nhỏ hơn, phân tán tải theo thời gian | Đọc 7 ngày có thể cần 168 partition |
| Theo giờ + shard | Tách tải ghi trong cùng một giờ của tenant lớn | Phải đọc nhiều shard và trộn kết quả theo thời gian |

Nếu bổ sung shard, khóa có thể trở thành:

~~~sql
PRIMARY KEY ((tenant_id, bucket_hour, shard_id), occurred_at, event_id)
~~~

`bucket_hour` là mốc đầu giờ UTC; `shard_id` lấy bằng hàm băm ổn định trên `event_id`, ví dụ `hash(event_id) mod 4` với kết quả được chuẩn hóa không âm. Số shard cần được quy định theo phiên bản thiết kế và có cách tra cứu khi thay đổi. Để lấy lịch sử một giờ, ứng dụng phải đọc **đủ các shard có thể chứa dữ liệu** rồi trộn theo `(occurred_at DESC, event_id DESC)`. Không dùng một shard ngẫu nhiên cho toàn bộ request đọc. **Phần lab CQL dưới đây cố ý dùng bucket ngày, chưa dùng shard**, để quan sát rõ partition và thứ tự hàng trước khi mở rộng.

## 4. Tạo keyspace và bảng bằng CQL

Đầu tiên, xem tên data center mà node trả về:

~~~sql
SELECT data_center FROM system.local;
~~~

Ví dụ sau giả sử cụm có **3 replica trong data center `datacenter1`**. Thay `datacenter1` bằng tên thực tế từ cụm. Lệnh `LOCAL_QUORUM` phía dưới chỉ chạy thành công khi đủ replica hoạt động.

~~~sql
CREATE KEYSPACE IF NOT EXISTS activity_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS activity_lab.activities_by_tenant_day (
    tenant_id     text,
    bucket_day    date,
    occurred_at   timestamp,
    event_id      uuid,
    actor_id      text,
    action        text,
    object_type   text,
    object_id     text,
    details_json  text,
    PRIMARY KEY ((tenant_id, bucket_day), occurred_at, event_id)
)
WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC)
 AND default_time_to_live = 7776000
 AND compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_unit': 'DAYS',
    'compaction_window_size': '1'
 };
~~~

**Giải thích các lựa chọn:**

1. `NetworkTopologyStrategy` phân phối replica theo topology data center; RF=3 được đặt theo từng DC, không đồng nghĩa cụm có đúng ba node. Trong lab **một node**, có thể dùng RF=1 và `CONSISTENCY ONE` để học cú pháp, nhưng không thể lấy đó làm bằng chứng về hành vi `LOCAL_QUORUM` khi replica lỗi.
2. `CLUSTERING ORDER BY` giúp lấy hoạt động mới trước trong **mỗi** ngày của **mỗi** tenant.
3. `default_time_to_live = 7776000` tương ứng 90 × 24 × 60 × 60 giây. TTL tính từ **thời điểm ghi**, không tính từ `occurred_at`. Sự kiện đến muộn vẫn có thể được giữ 90 ngày sau lúc ingest; nếu chính sách là “xóa đúng 90 ngày sau thời điểm sự kiện” thì phải tính TTL còn lại ở tầng ghi cho từng bản ghi.
4. `TimeWindowCompactionStrategy` (TWCS) thường thích hợp cho dữ liệu ghi theo thời gian với TTL tương đối đồng đều. **Cửa sổ TWCS dựa vào timestamp ghi của cell/SSTable**, không dựa trực tiếp vào giá trị cột `bucket_day`. Ghi dữ liệu rất trễ, cập nhật hàng cũ thường xuyên hoặc trộn TTL không đồng đều có thể khiến dọn dữ liệu kém hiệu quả.
5. Bảng dùng `details_json` kiểu text để đơn giản hóa lab. Trong ứng dụng thật, chỉ lưu các trường cần đọc, giới hạn payload và tránh biến một hàng thành kho chứa dữ liệu lớn.

## 5. Ghi dữ liệu mẫu và kiểm tra kết quả

Trong cụm có RF=3 ở DC hiện tại, thiết lập mức nhất quán cho phiên cqlsh:

~~~sql
CONSISTENCY LOCAL_QUORUM;
~~~

Ghi bốn hoạt động vào ba partition: hai ngày của `tenant-a` và một ngày của `tenant-b`.

~~~sql
INSERT INTO activity_lab.activities_by_tenant_day
(tenant_id, bucket_day, occurred_at, event_id, actor_id, action,
 object_type, object_id, details_json)
VALUES
('tenant-a', '2026-11-19', '2026-11-19T09:10:00Z',
 11111111-1111-4111-8111-111111111111,
 'u-1', 'LOGIN', 'session', 's-1', '{"ip":"192.0.2.10"}');

INSERT INTO activity_lab.activities_by_tenant_day
(tenant_id, bucket_day, occurred_at, event_id, actor_id, action,
 object_type, object_id, details_json)
VALUES
('tenant-a', '2026-11-19', '2026-11-19T10:15:00Z',
 22222222-2222-4222-8222-222222222222,
 'u-1', 'UPDATE', 'order', 'o-9', '{"field":"status"}');

INSERT INTO activity_lab.activities_by_tenant_day
(tenant_id, bucket_day, occurred_at, event_id, actor_id, action,
 object_type, object_id, details_json)
VALUES
('tenant-a', '2026-11-18', '2026-11-18T23:58:00Z',
 33333333-3333-4333-8333-333333333333,
 'u-2', 'CREATE', 'order', 'o-9', '{}');

INSERT INTO activity_lab.activities_by_tenant_day
(tenant_id, bucket_day, occurred_at, event_id, actor_id, action,
 object_type, object_id, details_json)
VALUES
('tenant-b', '2026-11-19', '2026-11-19T11:00:00Z',
 44444444-4444-4444-8444-444444444444,
 'u-3', 'LOGIN', 'session', 's-2', '{}');
~~~

Đọc hoạt động của tenant A trong ngày 19/11:

~~~sql
SELECT occurred_at, event_id, actor_id, action, object_id
FROM activity_lab.activities_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND bucket_day = '2026-11-19'
LIMIT 50;
~~~

**Kết quả mong đợi:** hàng `10:15 UPDATE` đứng trước `09:10 LOGIN`; không có hàng nào của `tenant-b` hoặc của ngày 18/11. Kiểm tra lọc trong một bucket:

~~~sql
SELECT occurred_at, action, object_id
FROM activity_lab.activities_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND bucket_day = '2026-11-19'
  AND occurred_at >= '2026-11-19T09:30:00Z'
  AND occurred_at <  '2026-11-20T00:00:00Z'
LIMIT 50;
~~~

**Kết quả mong đợi:** chỉ có `10:15 UPDATE`. Với dữ liệu thật, `bucket_day` **phải** được tính từ cùng giá trị `occurred_at` sau khi chuẩn hóa UTC. Không tính ngày theo timezone của máy Java hoặc theo timezone của người dùng, vì sẽ làm ghi vào bucket sai và khiến truy vấn bỏ sót hàng gần nửa đêm.

Thử đọc thiếu một phần partition key:

~~~sql
-- Không phải truy vấn được mô hình bảng này hỗ trợ:
-- SELECT * FROM activity_lab.activities_by_tenant_day
-- WHERE tenant_id = 'tenant-a';
~~~

Giữ ví dụ trên ở dạng comment để tránh chạy lỗi trong tập lệnh. Không “sửa” bằng cách thêm `ALLOW FILTERING`: việc quét nhiều partition sẽ tăng chi phí theo kích thước dữ liệu và không cho ra thứ tự toàn cục mà API cần.

## 6. Đọc qua nhiều bucket và thiết kế phân trang

### 6.1. Một request gồm những bước nào?

Ví dụ API cần 50 hoạt động của tenant A trong khoảng `[2026-11-18T00:00:00Z, 2026-11-20T00:00:00Z)`:

1. Xác thực tenant từ token/quyền truy cập; kiểm tra tenant trong URL trùng tenant được phép đọc. Giới hạn độ rộng khoảng thời gian và `limit` để tránh yêu cầu quét không giới hạn.
2. Xét bucket **19/11 rồi 18/11**. Với mỗi bucket, truy vấn khóa `(tenant_id, bucket_day)`, giới hạn `occurred_at` trong phần giao với khoảng người dùng yêu cầu.
3. Duyệt các hàng theo thứ tự clustering giảm dần, cộng vào kết quả cho tới `limit`; nếu hết ngày thì chuyển ngày trước.
4. Nếu còn dữ liệu, trả một **cursor** chứa ngày đang đọc và trạng thái tiếp tục; nếu đã hết khoảng thì trả `nextCursor = null`.

Mỗi truy vấn chỉ nhắm **một partition**. Thứ tự tổng thể đúng vì mọi timestamp trong ngày 19/11 UTC mới hơn mọi timestamp của ngày 18/11 UTC. Nếu API sau này chia một giờ thành nhiều shard, thứ tự không còn suy ra bằng cách nối mảng: phải **merge các luồng đã sắp xếp** giữa các shard.

Pseudocode cho thiết kế ngày:

~~~text
getPage(authorizedTenant, fromUtc, toUtc, limit, cursor):
    validate(fromUtc < toUtc, 1 <= limit <= configuredMax)
    state = verifyCursorOrStart(cursor, authorizedTenant, fromUtc, toUtc)
    result = []

    while result.size < limit and state.day >= fromUtc.dateUTC:
        begin = max(fromUtc, startOfDayUTC(state.day))
        end   = min(toUtc, startOfNextDayUTC(state.day))

        if begin >= end:
            state = previousDay(state.day)
            continue

        page = readOnePartition(
            tenantId=authorizedTenant,
            day=state.day,
            occurredAtFrom=begin,
            occurredAtTo=end,
            pagingState=state.driverPagingState
        )
        appendUpToLimit(result, page.rows)

        if page.hasMoreInSamePartition:
            state.driverPagingState = page.nextPagingState
        else:
            state.day = state.day - 1 day
            state.driverPagingState = null

    return result, signAndEncode(state) if moreDataPossible else null
~~~

Đoạn này mô tả **cách tổ chức**, không phải chương trình hoàn chỉnh: khi một lần lấy dữ liệu từ driver trả về nhiều hơn chỗ trống của trang API, phải giữ lại các hàng chưa dùng hoặc giới hạn/fetch phù hợp để không làm mất hàng. `LIMIT 50` của CQL chỉ giới hạn tối đa hàng của *một truy vấn*, còn **driver page size** kiểm soát số hàng được lấy theo từng trang giao thức. Hai khái niệm này không thay thế nhau.

### 6.2. Cursor an toàn và nhất quán

Cursor nên bao gồm bucket đang đọc, driver paging state (nếu có), `tenantId`, `from`, `to`, `limit` hoặc hash bộ tham số, phiên bản schema và thời hạn hiệu lực. Ký hoặc mã hóa xác thực token để ngăn sửa tenant hay giới hạn thời gian; **không nhận trực tiếp paging state bất kỳ từ client và ghép vào một truy vấn khác**. Paging state phải gắn với đúng CQL statement và các tham số tương ứng.

Cassandra không cung cấp snapshot xuyên nhiều partition cho feed này. Ghi mới hoặc ghi trễ trong lúc phân trang có thể làm kết quả thay đổi; API cần công bố ngữ nghĩa kiểu **lịch sử gần thời gian thực**, cân nhắc cố định một mốc `to` ở trang đầu, và dùng `event_id` để loại trùng ở phía người dùng khi cần. Mốc `to` chỉ chặn sự kiện mới có `occurred_at` sau mốc đó; nó **không** biến các trang thành một snapshot giao dịch nếu sự kiện cũ đến muộn.

## 7. Đọc từ ứng dụng Java

Ví dụ dùng **DataStax/Apache Cassandra Java Driver 4.x** với `CqlSession`. Đoạn mã chỉ đọc **trang giao thức đầu tiên của một bucket**; tầng API sẽ vận dụng thuật toán ở phần 6 để đi qua nhiều ngày và lưu cursor.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PagingState;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;

public class ActivityHistoryExample {
    public static void main(String[] args) {
        // Cấu hình contact points, xác thực và local DC theo cụm thật.
        try (CqlSession session = CqlSession.builder()
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT occurred_at, event_id, actor_id, action, object_id " +
                "FROM activity_lab.activities_by_tenant_day " +
                "WHERE tenant_id = ? AND bucket_day = ? " +
                "AND occurred_at >= ? AND occurred_at < ?");

            String tenantId = "tenant-a"; // Lấy từ ngữ cảnh đã xác thực.
            LocalDate dayUtc = LocalDate.parse("2026-11-19");
            Instant from = Instant.parse("2026-11-19T00:00:00Z");
            Instant to = Instant.parse("2026-11-20T00:00:00Z");

            BoundStatement bound = query.bind(tenantId, dayUtc, from, to)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setPageSize(50);

            ResultSet rows = session.execute(bound);
            int available = rows.getAvailableWithoutFetching();

            for (int i = 0; i < available; i++) {
                Row row = rows.one();
                System.out.printf("%s | %s | %s%n",
                    row.getInstant("occurred_at"),
                    row.getString("action"),
                    row.getUuid("event_id"));
            }

            PagingState nextPage = rows.getExecutionInfo().getPagingState();
            // Khi nextPage != null, chuyển nó vào cursor được xác thực
            // và dùng lại với cùng câu truy vấn/tham số ở request sau.
        }
    }
}
~~~

**Điểm kiểm tra Java:** `LocalDate` ánh xạ sang CQL `date`, `Instant` ánh xạ sang `timestamp`, và `UUID` ánh xạ sang `uuid`. Sử dụng prepared statement và bind tham số; không nối chuỗi tenant vào CQL. Với ứng dụng web, giữ `CqlSession` sống và dùng lại (quản lý vòng đời như một tài nguyên ứng dụng), không tạo session cho từng request. Chỉ trả dữ liệu của tenant đã kiểm tra quyền, kể cả khi người gọi cố thay `tenantId` trong URL hoặc cursor.

Đối với phần ghi Java, tạo `event_id` **một lần tại nguồn phát** và giữ nguyên qua mọi lần retry; tính `bucket_day = occurredAt.atZone(UTC).toLocalDate()`. Với cùng bộ khóa chính, retry sẽ upsert cùng hàng; tạo UUID mới mỗi lần retry lại tạo thêm hàng khác. Nếu sự kiện có thể cập nhật `occurred_at` thì đó là thay đổi khóa chính: thiết kế này phù hợp hơn với sự kiện bất biến (append-only).

## 8. Consistency, replication và thử lỗi

Trong mỗi DC có **RF=3**, một ví dụ cấu hình là ghi `LOCAL_QUORUM` và đọc `LOCAL_QUORUM`. Mỗi thao tác cần phản hồi từ **2 trong 3 replica nội vùng**; `R + W > RF` (2 + 2 > 3) tạo giao nhau giữa tập replica đã xác nhận ghi và tập replica phục vụ đọc, theo điều kiện hoạt động phù hợp. Điều đó **không** biến Cassandra thành cơ sở dữ liệu giao dịch ACID tổng quát: các thao tác cạnh tranh trên cùng cell được hòa giải theo timestamp (last-write-wins), và clock lệch hoặc lỗi phối hợp có thể ảnh hưởng kết quả. `LOCAL_QUORUM` cũng chỉ đảm bảo quorum **trong data center local**, không yêu cầu quorum đồng thời ở DC xa.

| Thử nghiệm với RF=3, LOCAL_QUORUM | Kỳ vọng | Cần quan sát |
| --- | --- | --- |
| Đủ ba replica | Ghi/đọc thành công nếu không có lỗi khác | Độ trễ p95, timeout và số replica phản hồi |
| Một replica tạm ngừng | Thường vẫn có thể ghi/đọc với hai replica còn lại | Độ trễ và khả năng replica phục hồi bắt kịp |
| Hai replica tạm ngừng | Quorum nội vùng không đạt; request có thể thất bại | Ứng dụng trả lỗi có kiểm soát, retry có backoff |
| Gửi lại sự kiện cùng khóa | Một hàng logic theo cùng primary key | Không xuất hiện bản ghi trùng do UUID mới |

Trong lab, chỉ thử ngắt replica trên **cụm kiểm thử được phép gây lỗi**. Không giảm `CONSISTENCY` trong production chỉ để che một lỗi quorum mà chưa đánh giá yêu cầu đọc/ghi. Khi timeout ghi, client có thể **không biết** write đã thành công trên một số replica hay chưa; retry cùng `event_id` và cùng payload sẽ giảm nguy cơ tạo bản ghi trùng. Không coi timeout là bằng chứng rằng dữ liệu chưa được lưu.

Đối với một yêu cầu API đọc không khả dụng, nên trả lỗi rõ ràng (ví dụ trạng thái 503) và dùng retry có giới hạn, exponential backoff và jitter ở tầng thích hợp. Không tự động đổ qua truy vấn quét toàn bảng hoặc trả dữ liệu tenant khác.

## 9. TTL, TWCS, tombstone và repair

**TTL** giúp lịch sử hết hạn tự động, nhưng hàng hết hạn không nhất thiết biến mất ngay khỏi đĩa. Cassandra biểu diễn xóa/hết hạn bằng **tombstone**; compaction mới có thể loại dữ liệu vật lý khi đủ điều kiện an toàn. Vì vậy phải theo dõi tombstone, dung lượng ổ đĩa và độ trễ đọc dài hạn, đặc biệt khi API đọc nhiều bucket đã hết hạn.

**TWCS** gom SSTable theo cửa sổ thời gian ghi, thường hữu ích khi workload chủ yếu append-only và dữ liệu trong cửa sổ có TTL gần nhau. Nếu liên tục cập nhật hoạt động cũ hoặc ghi bù lượng lớn sự kiện quá khứ, việc nhiều cửa sổ chứa dữ liệu liên quan có thể giảm hiệu quả dọn. Điều chỉnh độ rộng cửa sổ dựa trên tốc độ ghi, retention, SSTable và compaction thực đo.

**Repair** đồng bộ dữ liệu lệch giữa các replica; replication và `LOCAL_QUORUM` **không loại bỏ nhu cầu repair**. Lập lịch repair phù hợp với `gc_grace_seconds`, thời gian replica có thể offline và chính sách bảo trì; không hạ `gc_grace_seconds` tùy tiện vì replica bỏ lỡ tombstone có thể gây **resurrection** (dữ liệu đã xóa xuất hiện lại). Việc TTL hết hạn và xóa tombstone cần được kiểm nghiệm dưới chính sách repair/compaction của cụm thật.

Các phép đo nên có trong dashboard:

- Kích thước partition theo tenant/bucket, độ lệch tenant nóng, lưu lượng đọc/ghi và p95/p99 latency.
- Số timeout, unavailable, retry, pending compactions, lượng SSTable và disk usage.
- Tombstone warnings/scan, repair thành công hoặc quá hạn, độ trễ và lỗi của driver.
- Độ sâu bucket mà một request quét, số partition bị đọc mỗi request, kích thước cursor và tỉ lệ trang trống.

Tránh áp dụng `SELECT COUNT(*)` trên nhiều partition hoặc quét tất cả tenant để đếm sự kiện cho dashboard. Nếu cần thống kê, thiết kế pipeline/bảng tổng hợp phục vụ đúng truy vấn và chấp nhận ngữ nghĩa nhất quán của nó.

## 10. Bài tập mở rộng và câu hỏi tự kiểm tra

**Bài A — Kiểm tra phân vùng và thứ tự:** ghi thêm hai sự kiện của `tenant-a` với cùng `occurred_at` nhưng hai `event_id` khác nhau. Xác minh cả hai tồn tại và thứ tự trong một partition ổn định. Ghi sự kiện lúc `2026-11-20T00:01:00Z` và xác minh nó thuộc bucket 20/11, không xuất hiện khi query ngày 19/11.

**Bài B — Phân trang nhiều ngày:** triển khai API trả từng trang 2 bản ghi trên dữ liệu mẫu và dữ liệu của bài A. Kiểm tra trang sau không bỏ sót hoạt động ở ranh giới ngày và cursor của tenant A không dùng lại được cho tenant B. Thêm test với khoảng `to` đúng 00:00 UTC để đảm bảo không đọc nhầm ngày mới.

**Bài C — Tenant nóng:** giả định tenant X có 2,4 triệu sự kiện/ngày, hàng trung bình 1 KiB và lưu 90 ngày. Tính partition size khi bucket ngày, giờ, giờ × 4 shard; giải thích trade-off số partition đọc cho API 24 giờ. Sau đó dùng kích thước hàng thực đo và peak hour để chọn thông số, thay vì chỉ dựa trên trung bình.

**Bài D — Tính nhất quán và lỗi:** trên cụm kiểm thử RF=3, chạy `LOCAL_QUORUM`, ghi bằng `event_id` cố định, ngắt một replica rồi đọc, sau đó đánh giá ảnh hưởng nếu ngắt thêm replica. Mô tả kết quả và xem log/metrics của driver. Không thực hiện lỗi chủ động trên hệ thống đang phục vụ người dùng.

**Bài E — Vận hành:** diễn giải vì sao bản ghi TTL 90 ngày có thể còn chiếm dung lượng sau 90 ngày, TWCS dựa trên timestamp nào, và vì sao giảm `gc_grace_seconds` khi repair chưa bảo đảm là nguy hiểm. Đề xuất ít nhất ba metrics để phát hiện partition quá lớn và tombstone scan.

**Câu hỏi ra quyết định:**

1. Vì sao khóa `PRIMARY KEY (tenant_id, occurred_at)` có thể tạo partition tăng không giới hạn? Vì sao chỉ tạo index trên `occurred_at` không giải quyết yêu cầu đọc theo tenant và bucket?
2. Nếu API thêm tính năng “tất cả hoạt động của actor U trong tenant A suốt 30 ngày”, có cần bảng mới `activities_by_tenant_actor_day` không? Hãy mô tả primary key của bảng đó và chi phí ghi nhân đôi.
3. Nếu tenant đang dùng bucket ngày được đổi sang bucket giờ, ứng dụng đọc dữ liệu cũ bằng cách nào trong giai đoạn chuyển đổi? Cần lưu/định phiên bản quy tắc bucket, backfill có kiểm soát hoặc đọc cả schema cũ trong cửa sổ chuyển tiếp.
4. Nếu hoạt động xảy ra lúc 23:59 UTC nhưng tới hệ thống lúc 00:10 ngày sau, nó phải được ghi vào bucket ngày nào? Theo thiết kế này: **ngày của `occurred_at`**, trong khi TTL 90 ngày bắt đầu từ lúc write.

## 11. Checklist nghiệm thu

- [ ] Khóa partition chứa **cả tenant và bucket**; hai sự kiện trùng `occurred_at` vẫn phân biệt bằng `event_id`.
- [ ] Truy vấn API giới hạn tenant, khoảng thời gian, số hàng và dùng đúng partition key; **không** có `ALLOW FILTERING` hay quét tất cả partition.
- [ ] Trả mới trước cũ trong mỗi bucket; ghép các bucket mới đến cũ; nếu có shard thì merge đúng thứ tự.
- [ ] Xử lý thời gian UTC và khoảng `[from, to)`, kể cả ranh giới nửa đêm và sự kiện đến muộn.
- [ ] Cursor được ràng buộc tenant/tham số, có xác thực và tiếp tục đúng vị trí mà không bỏ hàng.
- [ ] Retry ghi dùng `event_id` ổn định; Java Driver dùng prepared statement, paging, consistency và session dùng lại.
- [ ] Tính partition size từ lưu lượng thực, có phương án bucket giờ/shard cho tenant nóng.
- [ ] RF, mức consistency, hành vi khi replica lỗi, TTL, TWCS, tombstone và repair được kiểm tra trên môi trường phù hợp.
- [ ] Các giới hạn được công bố: không có join giữa bucket, không có snapshot giao dịch xuyên partition, và truy vấn mới có thể cần bảng mới.

**Kết quả của bài thực hành** là một bảng Cassandra phục vụ feed lịch sử hoạt động **theo tenant và thời gian**, kèm thuật toán đọc nhiều partition, cách kết nối Java và các quyết định vận hành có thể giải thích bằng đặc tính phân tán của Cassandra.
