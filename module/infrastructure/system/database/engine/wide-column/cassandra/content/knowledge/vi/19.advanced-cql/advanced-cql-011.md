# Đánh giá cách tính tại ứng dụng hoặc kho phân tích thay vì quét rộng

## Mục tiêu bài học

Apache Cassandra được thiết kế để phân phối dữ liệu trên nhiều node, phục vụ truy vấn có **partition key rõ ràng** với độ trễ thấp và khả năng mở rộng theo chiều ngang. Tuy nhiên, khi một yêu cầu đòi tính tổng, đếm, nhóm hoặc thống kê trên hàng triệu bản ghi nằm rải rác ở nhiều partition, cách viết CQL trông đơn giản có thể gây **quét rộng** (*wide scan*), tải lớn trên cluster và độ trễ khó kiểm soát.

Trong chương **CQL nâng cao** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, bài học này đặt câu hỏi thực tế: **Nên tính trong Cassandra, tại ứng dụng Java, trên một bảng tổng hợp đã chuẩn bị sẵn, hay chuyển sang kho phân tích?** Việc lựa chọn phải xuất phát từ mô hình wide-column, partition key, truy vấn cần phục vụ, độ chính xác, replication, consistency level và đặc điểm vận hành như compaction/repair.

Sau bài này, bạn có thể:

- Nhận diện truy vấn Cassandra có nguy cơ quét nhiều partition, đặc biệt `COUNT(*)`, `GROUP BY` không phù hợp và `ALLOW FILTERING`.
- Phân biệt **tính toán trên một tập dữ liệu có giới hạn** ở ứng dụng với **phân tích toàn tập** trên kho phân tích.
- Thiết kế bảng theo truy vấn, giới hạn khối lượng đọc bằng partition key và khoảng thời gian.
- Chọn giữa tính trực tiếp trên ứng dụng, bảng tổng hợp trước (*pre-aggregation*) và hệ thống OLAP/data warehouse.
- Triển khai ví dụ CQL và Java có giới hạn số hàng, phân trang và kiểm soát lỗi.
- Đánh giá độ trễ, độ mới dữ liệu, chi phí vận hành, khả năng đối soát và mức nhất quán của kết quả.

## 1. Vì sao quét rộng không phù hợp với Cassandra?

Một hàng Cassandra được định vị thông qua **partition key**. Token của partition key quyết định cách dữ liệu được phân phối tới các replica theo topology và replication factor. Các cột **clustering** xác định thứ tự dữ liệu *bên trong một partition*, giúp đọc một khoảng hàng hiệu quả khi đã biết partition key.

Hãy tưởng tượng hệ thống ghi nhận thanh toán từ 100.000 thiết bị, mỗi thiết bị tạo nhiều sự kiện mỗi ngày:

| Yêu cầu sản phẩm | Phạm vi cần đọc |
| --- | --- |
| Hiển thị 20 sự kiện mới nhất của **một thiết bị** trong ngày | Một partition hoặc số partition đã biết và giới hạn |
| Tính tổng thanh toán của **một thiết bị** trong 15 phút | Một partition/ngày, khoảng clustering đã biết |
| Tính tổng tiền của **mọi thiết bị** thuộc một tenant trong tháng | Rất nhiều partition theo thiết bị và ngày |
| Xếp hạng 100 tenant có doanh thu cao nhất quý | Nhiều tenant, nhiều partition, phép tổng hợp và sắp xếp toàn tập |

Cassandra rất phù hợp với hai truy vấn đầu nếu bảng được thiết kế theo đúng khóa truy vấn. Hai truy vấn sau thuộc kiểu **phân tích trên tập lớn**; nếu cố lấy toàn bộ hàng từ Cassandra về một service Java để cộng, ứng dụng phải điều phối hàng loạt request và vận chuyển dữ liệu qua mạng.

~~~mermaid
flowchart TD
    Q["Yêu cầu tính toán mới"] --> K{"Biết partition key và\nphạm vi đọc đủ nhỏ?"}
    K -->|Có| A["Đọc có giới hạn bằng CQL\nTính tại ứng dụng nếu cần"]
    K -->|Không| F{"Kết quả có được gọi\nthường xuyên, cần nhanh?"}
    F -->|Có| P["Tổng hợp trước theo khóa truy vấn\nĐọc bảng summary"]
    F -->|Không hoặc truy vấn khám phá| W["Kho phân tích / OLAP\nETL, CDC hoặc batch export"]
    A --> V["Đo latency, số hàng, lỗi, chi phí"]
    P --> V
    W --> V
~~~

**Quét rộng** không chỉ có nghĩa là một partition có nhiều hàng. Nó còn có thể là một truy vấn hoặc nhiều truy vấn ứng dụng cùng lúc chạm vào hàng nghìn partition khác nhau. Coordinator, replica, CPU, I/O, network, heap, tombstone và compaction đều có thể chịu ảnh hưởng.

## 2. Những câu CQL dễ gây hiểu nhầm

### 2.1. COUNT(*) không phải bộ đếm metadata tức thì

~~~sql
-- Cú pháp hợp lệ, nhưng nguy hiểm trên bảng lớn:
SELECT COUNT(*) FROM events_by_device_day;
~~~

Cassandra không duy trì sẵn một tổng số hàng chính xác trên toàn bộ cluster để trả câu này với chi phí hằng số. Truy vấn đếm phải xử lý dữ liệu thực tế, có thể tiêu tốn nhiều lần đọc và timeout khi bảng lớn. Ngay cả đếm trong **một partition rất lớn** cũng cần xử lý nhiều hàng; việc đã có partition key không biến `COUNT(*)` thành một phép đọc O(1).

~~~sql
-- Đếm trong đúng một partition có thể chấp nhận được nếu partition nhỏ:
SELECT COUNT(*)
FROM events_by_device_day
WHERE tenant_id = 'tenant-a'
  AND device_id = 11111111-1111-4111-8111-111111111111
  AND day = '2026-11-21';
~~~

**Câu hỏi thiết kế:** service cần số đếm chính xác ngay lập tức đến mức nào? Nếu dashboard hiển thị số lượt giao dịch theo ngày nhiều lần mỗi giây, nên cân nhắc số đếm đã tổng hợp thay vì chạy lại `COUNT(*)` trên dữ liệu gốc.

### 2.2. GROUP BY trong CQL không giống GROUP BY ở hệ OLAP

`GROUP BY` trong Cassandra có những giới hạn liên quan đến thứ tự **primary key** và clustering key. Nó không cung cấp engine phân tích tùy ý với phép join, sort, shuffle và group-by trên mọi cột như các hệ SQL OLAP. Một yêu cầu `GROUP BY tenant_id` trên dữ liệu có partition key theo `device_id` không tự biến thành truy vấn hiệu quả.

Không nên chuyển một báo cáo kiểu:

~~~sql
-- SQL PHÂN TÍCH MINH HỌA, không phải mẫu truy vấn CQL nên chạy trên
-- bảng giao dịch phân tán theo device_id:
SELECT tenant_id, DATE(event_time), SUM(amount_minor)
FROM all_events
GROUP BY tenant_id, DATE(event_time);
~~~

thành một lần quét Cassandra chỉ vì tên hàm tổng hợp có vẻ tương tự. Cần đánh giá **phân phối dữ liệu thực tế** và giới hạn cú pháp CQL trước khi chọn công cụ.

### 2.3. ALLOW FILTERING không biến quét rộng thành rẻ

Giả sử partition key gồm `(tenant_id, device_id, day)` nhưng người dùng chỉ biết `tenant_id` và tháng. Câu lệnh:

~~~sql
-- Ví dụ nhu cầu không khớp khóa phân vùng; không nên lấy đây
-- làm thiết kế truy vấn cho báo cáo tháng:
SELECT event_time, amount_minor
FROM events_by_device_day
WHERE tenant_id = 'tenant-a'
ALLOW FILTERING;
~~~

có thể bị Cassandra từ chối hoặc, khi ép lọc được cho phép trong một tình huống cụ thể, phải đọc và loại bỏ rất nhiều hàng. `ALLOW FILTERING` chỉ thừa nhận một kế hoạch lọc tiềm ẩn rủi ro; nó **không bổ sung partition key**, không tạo chỉ mục phù hợp và không cam kết giới hạn số partition cần kiểm tra.

`LIMIT 100` cũng không tự sửa vấn đề. Nó giới hạn số hàng **trả ra**, không bảo đảm server chỉ cần kiểm tra 100 hàng trên đĩa hay liên lạc với 100 partition. Thêm `LIMIT` hữu ích cho truy vấn đã đúng mô hình, nhưng không phải thay thế cho việc định hình phạm vi đọc.

### 2.4. Index, materialized view và batch không phải kho phân tích

- **Secondary index/SAI** có thể giúp truy vấn theo điều kiện được chỉ mục hỗ trợ. Nhưng việc có index không có nghĩa `SUM`/`GROUP BY` trên lượng dữ liệu lớn trở thành rẻ; phải đo selectivity, fan-out và chi phí đọc.
- **Materialized view** trong Cassandra hỗ trợ một số cách nhìn dữ liệu theo khóa khác, **không tự tính sẵn SUM/AVG/COUNT** như một bảng OLAP aggregate.
- **BATCH** nhóm các thao tác ghi; batch không phải cơ chế chạy phép tổng hợp phân tán hay giải pháp tăng tốc đọc toàn tập.
- `CONSISTENCY QUORUM` tăng yêu cầu xác nhận từ replica trong một số cấu hình, **không thay đổi độ phức tạp** của truy vấn phân tích rộng.

## 3. Thiết kế đường đọc có giới hạn theo partition

Giả sử nhu cầu trực tuyến là: “Trong một giờ của một ngày, thiết bị X thuộc tenant Y phát sinh bao nhiêu giao dịch thanh toán và tổng tiền bao nhiêu?” Ta thiết kế bảng sự kiện theo đúng khóa truy vấn:

~~~sql
CREATE TABLE events_by_device_day (
    tenant_id text,
    device_id uuid,
    day date,
    event_time timestamp,
    event_id timeuuid,
    event_type text,
    amount_minor bigint,
    PRIMARY KEY ((tenant_id, device_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
~~~

**Phân tích schema:**

- `(tenant_id, device_id, day)` là **composite partition key**. Hệ thống định vị đúng partition của thiết bị trong ngày.
- `event_time` và `event_id` là clustering columns; `event_id` giúp phân biệt các sự kiện có cùng timestamp. Ứng dụng phải giữ một định danh sự kiện ổn định nếu cần ghi lại idempotent.
- `amount_minor` lưu số tiền ở đơn vị nhỏ nhất như đồng/xu tùy đơn vị tiền tệ; tránh sai số `float` trong phép cộng tiền.
- `day` cần được tính nhất quán từ thời điểm sự kiện (ví dụ theo UTC) để truy vấn thời gian không bỏ sót hoặc đếm đôi giữa các ngày.
- Không để một partition ngày tăng vô hạn nếu một thiết bị có lưu lượng cực cao; điều chỉnh bucket giờ hoặc shard khi có bằng chứng tải lớn.

Nạp một vài hàng thử nghiệm:

~~~sql
INSERT INTO events_by_device_day (
    tenant_id, device_id, day, event_time,
    event_id, event_type, amount_minor
) VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:10:00Z',
    now(), 'PAYMENT', 12000
);

INSERT INTO events_by_device_day (
    tenant_id, device_id, day, event_time,
    event_id, event_type, amount_minor
) VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:15:00Z',
    now(), 'PAYMENT', 8500
);

INSERT INTO events_by_device_day (
    tenant_id, device_id, day, event_time,
    event_id, event_type, amount_minor
) VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:20:00Z',
    now(), 'HEARTBEAT', 0
);
~~~

Đọc một cửa sổ thời gian trong **đúng partition**:

~~~sql
SELECT event_time, event_id, event_type, amount_minor
FROM events_by_device_day
WHERE tenant_id = 'tenant-a'
  AND device_id = 11111111-1111-4111-8111-111111111111
  AND day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time <  '2026-11-21T10:00:00Z';
~~~

Ứng dụng có thể duyệt các hàng nhận được và chỉ cộng các hàng `event_type = 'PAYMENT'`. Với dữ liệu thử nghiệm trên, kết quả dự kiến là **2 giao dịch**, tổng `20500` đơn vị tiền nhỏ nhất. Ta không cần tạo bảng summary mới nếu cửa sổ có ít hàng và tần suất truy vấn thấp.

**Giới hạn quan trọng:** “Có partition key” không đồng nghĩa “tự động nhẹ”. Một partition chứa hàng triệu hàng, hoặc ứng dụng đồng thời đọc hàng nghìn partition, vẫn có thể quá tốn kém. Hãy đo kích thước partition, số hàng trong khoảng clustering, số request/giây và thời gian phản hồi.

## 4. Khi nào tính tại ứng dụng Java?

Tính toán ở ứng dụng phù hợp nếu:

1. Có **số lượng partition biết trước, tương đối nhỏ**; ví dụ đúng một thiết bị/một ngày, hoặc vài partition đã được giới hạn.
2. Số hàng cần đọc có **trần dự kiến** dựa trên dữ liệu thật; có thể đặt giới hạn và xử lý khi vượt trần.
3. Công thức gọn, chẳng hạn cộng tổng, đếm theo loại, tính tỷ lệ trên tập hàng nhỏ, hoặc xử lý logic nghiệp vụ không tiện diễn đạt bằng CQL.
4. Hệ thống chấp nhận việc đọc dữ liệu gốc; độ trễ, băng thông và tải replica đã được đo trong điều kiện thực tế.

Một mẫu Java Driver 4.x với prepared statement, phân trang và giới hạn số hàng:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class DevicePaymentCalculator {
    private static final long MAX_SCANNED_ROWS = 10_000L;

    private final CqlSession session;
    private final PreparedStatement readWindow;

    public record Totals(long visitedRows, long paymentCount, long amountMinor) {}

    public DevicePaymentCalculator(CqlSession session) {
        this.session = session;
        this.readWindow = session.prepare(
            "SELECT event_type, amount_minor FROM events_by_device_day " +
            "WHERE tenant_id = ? AND device_id = ? AND day = ? " +
            "AND event_time >= ? AND event_time < ?");
    }

    public Totals calculate(
            String tenantId,
            UUID deviceId,
            LocalDate day,
            Instant fromInclusive,
            Instant toExclusive) {
        if (tenantId == null || tenantId.isBlank()
                || deviceId == null || day == null
                || fromInclusive == null || toExclusive == null
                || !fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Tham số khoảng đọc không hợp lệ");
        }
        // Lớp gọi cũng phải bảo đảm from/to nằm trong đúng bucket "day".
        BoundStatement bound = readWindow.bind(
                tenantId, deviceId, day, fromInclusive, toExclusive)
            .setPageSize(200)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        long visited = 0;
        long paymentCount = 0;
        long totalMinor = 0;
        for (Row row : session.execute(bound)) {
            if (++visited > MAX_SCANNED_ROWS) {
                throw new IllegalStateException(
                    "Cửa sổ dữ liệu vượt giới hạn; cần dùng bảng tổng hợp");
            }
            if ("PAYMENT".equals(row.getString("event_type"))) {
                paymentCount = Math.addExact(paymentCount, 1);
                if (!row.isNull("amount_minor")) {
                    totalMinor = Math.addExact(totalMinor, row.getLong("amount_minor"));
                }
            }
        }
        return new Totals(visited, paymentCount, totalMinor);
    }
}
~~~

Trong ví dụ:

- Phạm vi đọc **một partition** và một khoảng clustering xác định ngay trong CQL. Không làm `SELECT *` toàn bảng.
- `setPageSize(200)` giới hạn số hàng mỗi trang truyền về, tránh tải tất cả vào một `List`; nó **không đặt trần tổng số hàng**. Vì vậy vẫn cần `MAX_SCANNED_ROWS`.
- Nếu vượt trần hoặc truy vấn timeout, phương thức báo lỗi thay vì trả về một tổng **thiếu dữ liệu**. Ứng dụng cần chuyển sang báo cáo tổng hợp hoặc thông báo phạm vi quá lớn.
- `Math.addExact` phát hiện tràn số `long`. Số tiền lưu dạng đơn vị nhỏ nhất để tránh sai số dấu phẩy động.
- `LOCAL_QUORUM` chỉ là lựa chọn minh họa; phải phù hợp replication factor/datacenter và yêu cầu độ mới dữ liệu. Nó không tạo snapshot nguyên tử cho nhiều hàng đang bị sửa trong lúc đọc.

Nếu khoảng thời gian vượt qua nhiều ngày, ứng dụng phải xác định các bucket/ngày tương ứng và kiểm soát **tổng** số partition/hàng, không chỉ trần của từng ngày. Phân trang, rate limiting và timeout là các lớp bảo vệ bổ sung, không thay thế việc giới hạn phạm vi dữ liệu ngay từ thiết kế schema.

## 5. Khi nào tạo bảng tổng hợp trước?

Giả sử màn hình của tenant thường xuyên hỏi: “Trong tháng này tổng số giao dịch và tổng tiền theo từng ngày là bao nhiêu?” Nếu mỗi lần đều đọc sự kiện của hàng chục nghìn thiết bị, thời gian và tải sẽ tăng theo khối lượng dữ liệu gốc.

Ta có thể lưu **một hàng tổng hợp cho mỗi tenant/ngày**, nhóm theo tháng để tránh một partition tenant tồn tại vô hạn:

~~~sql
CREATE TABLE tenant_daily_payment_totals (
    tenant_id text,
    year_month text,
    day date,
    payment_count bigint,
    total_minor bigint,
    as_of timestamp,
    PRIMARY KEY ((tenant_id, year_month), day)
) WITH CLUSTERING ORDER BY (day DESC);
~~~

Ví dụ một job/stream processor đã tính toán xong và ghi snapshot:

~~~sql
INSERT INTO tenant_daily_payment_totals (
    tenant_id, year_month, day,
    payment_count, total_minor, as_of
) VALUES (
    'tenant-a', '2026-11', '2026-11-21',
    842, 9876543, '2026-11-21T10:00:00Z'
);
~~~

Ứng dụng đọc toàn bộ ngày trong một tháng từ **một partition đã biết**:

~~~sql
SELECT day, payment_count, total_minor, as_of
FROM tenant_daily_payment_totals
WHERE tenant_id = 'tenant-a'
  AND year_month = '2026-11'
  AND day >= '2026-11-01'
  AND day < '2026-12-01';
~~~

Mỗi tenant/tháng có tối đa vài chục hàng ngày thay vì hàng triệu sự kiện gốc. `year_month` là một chuỗi được ứng dụng chuẩn hóa theo dạng `YYYY-MM`; công thức phân chia thời gian, timezone và tên bucket phải thống nhất giữa hệ ghi và hệ đọc.

Đổi lại, tổng hợp trước tạo ra vấn đề riêng:

| Vấn đề | Cách thiết kế |
| --- | --- |
| **Độ mới** | Ghi `as_of` và hiển thị dữ liệu cập nhật đến thời điểm nào. |
| **Trùng sự kiện** | Dùng `event_id` ổn định và cơ chế khử trùng/đối soát. Không xem một lệnh `counter + 1` lặp lại là idempotent. |
| **Sự kiện đến muộn** | Cho phép sửa lại tổng ngày cũ hoặc chạy job bù theo cửa sổ. |
| **Sai lệch giữa raw và summary** | Lập lịch so sánh tổng với nguồn sự kiện và sửa bản tổng hợp. |
| **Sự cố giữa hai lần ghi** | Không giả định ghi sự kiện và cập nhật summary ở hai partition/bảng là một transaction nguyên tử. |
| **Phân phối tải** | Nếu một tenant/tháng trở nên quá nóng, cân nhắc chia shard hoặc phân loại summary theo tiêu chí truy vấn. |

**Nên ưu tiên ghi snapshot tổng hợp có thể tái tạo** khi pipeline hỗ trợ tính lại, vì ghi cùng giá trị `payment_count` và `total_minor` cho cùng kỳ dễ idempotent hơn cộng counter sau mỗi sự kiện. Tuy nhiên, nếu nhiều writer cùng tính và ghi snapshot, vẫn cần cơ chế điều phối phiên bản/checkpoint để tránh snapshot cũ ghi đè snapshot mới.

Khi cần các tập số đếm **gần đúng**, counter có thể hữu dụng. Nhưng Cassandra counter không bảo đảm gửi trùng `+1` chỉ tăng một lần; vì vậy không dùng counter đơn thuần cho tổng tiền hay dữ liệu phải đối soát chính xác.

## 6. Khi nào chuyển sang kho phân tích/OLAP?

Hãy xem xét data warehouse, data lakehouse, công cụ OLAP hoặc hệ xử lý phân tán khi có một hoặc nhiều đặc điểm sau:

- **Nhiều partition không biết trước**: tổng mọi thiết bị theo quý, phân phối theo khu vực, tenant hoặc sản phẩm.
- **Nhóm và tổng hợp tùy ý**: `GROUP BY` theo các thuộc tính không nằm trong khóa Cassandra, hàng chục phép tính, số lượng nhóm lớn.
- **Join** với dữ liệu từ nhiều nguồn như người dùng, doanh thu, danh mục sản phẩm hoặc chiến dịch.
- **Phân tích lịch sử dài**: so sánh nhiều tháng/năm, truy vấn khám phá, dashboard BI thay đổi liên tục.
- **Yêu cầu quét nhiều dữ liệu** nhưng không muốn gây ảnh hưởng tới latency của ứng dụng giao dịch đang dùng Cassandra.

Luồng dữ liệu tham khảo:

~~~mermaid
flowchart LR
    A["Ứng dụng / sự kiện nghiệp vụ"] --> B["Cassandra: truy vấn OLTP"]
    A --> S["Luồng sự kiện có ID"]
    B -. "CDC hoặc export theo lô" .-> E["Pipeline ETL/stream"]
    S --> E
    E --> D["Kho phân tích / OLAP"]
    D --> R["Dashboard, tổng hợp, báo cáo"]
    E --> P["Bảng summary Cassandra\ncho màn hình cần độ trễ thấp"]
~~~

Các hướng đồng bộ phổ biến gồm **batch export**, **CDC** ở phiên bản hỗ trợ hoặc đẩy sự kiện nghiệp vụ vào một luồng dữ liệu rồi nạp vào hệ phân tích. Chọn hướng nào còn phụ thuộc yêu cầu độ trễ, vận hành, công cụ sẵn có và khả năng khôi phục. CDC có thể phải xử lý lặp lại, sự kiện đến trễ, thứ tự cập nhật và sự cố đồng bộ; không mặc nhiên có *exactly-once* end-to-end.

Ở hệ phân tích, báo cáo như sau hợp lý hơn về mặt kiến trúc (SQL **minh họa**, cú pháp thời gian tùy hệ quản trị):

~~~sql
SELECT
    tenant_id,
    DATE_TRUNC('month', event_time) AS month_bucket,
    COUNT(*) AS payment_count,
    SUM(amount_minor) AS total_minor
FROM analytics_events
WHERE event_type = 'PAYMENT'
  AND event_time >= TIMESTAMP '2026-11-01 00:00:00'
  AND event_time <  TIMESTAMP '2026-12-01 00:00:00'
GROUP BY tenant_id, DATE_TRUNC('month', event_time);
~~~

Đây là dạng truy vấn dành cho engine có khả năng đọc cột, phân vùng dữ liệu phân tích, tổng hợp và shuffle/merge kết quả trên lượng dữ liệu lớn. Không nên sao chép nguyên câu SQL vào `cqlsh` và mong Cassandra thực hiện tương tự.

Hãy làm rõ **nguồn sự thật** (*source of truth*). Nếu Cassandra lưu dữ liệu nghiệp vụ gốc và kho phân tích chỉ là bản sao, cần có cơ chế phát hiện thiếu/trùng dữ liệu, quản lý độ trễ đồng bộ, và khả năng tái dựng từ log hoặc export. Nếu tổ chức đã có event log bền vững làm nguồn sự thật, một pipeline có thể nuôi cả Cassandra lẫn kho phân tích, nhưng phải mô tả rõ khả năng retry và khử trùng.

## 7. Ma trận quyết định

| Tiêu chí | Tính ở Java sau CQL có giới hạn | Bảng summary trong Cassandra | Kho phân tích/OLAP |
| --- | --- | --- | --- |
| Quy mô đọc | Ít partition và ít hàng, có trần rõ | Ít hàng summary cho mỗi khóa truy vấn | Rất nhiều hàng/partition và lịch sử |
| Độ trễ | Thường thấp nếu phạm vi nhỏ | Thấp, ổn định cho truy vấn cố định | Tùy engine/tải; phù hợp báo cáo và batch |
| Độ mới | Gần dữ liệu OLTP, chịu consistency đã chọn | Trễ theo pipeline tổng hợp | Trễ theo ETL/CDC và lịch cập nhật |
| Truy vấn mới | Cần thay logic Java, vẫn bị hạn chế phạm vi | Có thể cần thêm bảng summary | Linh hoạt hơn cho SQL/BI |
| Chi phí | Network và CPU app, replica read | Thêm storage và công việc duy trì summary | Hạ tầng/pipeline phân tích riêng |
| Tính đúng | Phụ thuộc phạm vi và độ ổn định dữ liệu đọc | Phụ thuộc dedupe, late events, đối soát | Phụ thuộc ingest, dedupe và watermark |
| Tình huống điển hình | Tổng giao dịch một thiết bị trong 15 phút | Tổng tiền tenant theo ngày trên dashboard | Top tenant theo doanh thu, phân tích quý/năm |

Không có ngưỡng số hàng chung đúng cho mọi hệ thống. Một partition với 2.000 hàng nhỏ có thể rẻ hơn 200 hàng chứa giá trị rất lớn hoặc nhiều tombstone. Hãy đo với **kích thước row, RF, số node, số replica tiếp xúc, mức đồng thời và latency mục tiêu**.

### Quy trình chọn phương án

1. **Xác định đầu ra:** tính chỉ số nào, nhóm theo trường nào, cần chính xác hay gần đúng, độ mới tối đa chấp nhận được.
2. **Vẽ khóa truy vấn:** từ các tham số request có suy ra partition key cụ thể không? Một request thường chạm bao nhiêu partition?
3. **Ước lượng khối lượng:** số hàng trong một partition, số partition, kích thước trả về, số request/giây và khung thời gian truy vấn.
4. **Thử phương án nhỏ nhất:** nếu truy vấn có giới hạn, đo CQL + Java; nếu là dashboard gọi lặp lại, thử summary; nếu là báo cáo rộng, thử kho phân tích.
5. **Định nghĩa sai lệch chấp nhận được:** dữ liệu có thể trễ 30 giây hay 1 giờ? Khi nào phải đối soát? Timeout có thể trả báo cáo chưa hoàn tất không?
6. **Kiểm tra tác động tới OLTP:** theo dõi latency, read timeouts, hot partition và tài nguyên Cassandra khi có tải truy vấn thật.

## 8. Consistency, compaction, repair và sự cố

Một báo cáo có thể không chính xác vì **thiếu dữ liệu hoặc xử lý sai**, ngay cả khi cú pháp CQL hợp lệ. Phân tích các nguồn sai khác:

**Consistency level.** Với replication factor phù hợp, `LOCAL_QUORUM` thường có mức xác nhận khác `LOCAL_ONE`, nhưng nhiều lệnh đọc riêng lẻ không tự tạo một **snapshot nguyên tử trên toàn tập**. Nếu sự kiện tiếp tục đến trong lúc Java đọc nhiều trang/partition, tổng nhận được có thể phản ánh nhiều thời điểm khác nhau. Với số liệu tài chính, cần định nghĩa mốc chốt dữ liệu và cách tái tính/đối soát.

**Tombstone và TTL.** Dữ liệu đã xóa hoặc hết TTL có thể tạo tombstone; truy vấn phạm vi lớn phải xử lý nhiều tombstone, làm latency tăng và có thể gây cảnh báo/lỗi. Đừng coi `LIMIT 100` là bảo đảm truy vấn chỉ phải xét 100 row sống.

**Compaction.** SSTable và hoạt động compaction ảnh hưởng số file cần đọc, I/O và hiệu năng. Lựa chọn chiến lược compaction cần dựa trên mô hình ghi, đọc, TTL và bucket thời gian; đổi compaction không thể biến một truy vấn thiếu partition key thành tổng hợp phân tán hiệu quả.

**Repair.** Repair giúp duy trì đồng bộ dữ liệu giữa các replica theo cơ chế Cassandra. Repair không tự tính lại summary bị cộng trùng, không thay event deduplication và không suy ra event nghiệp vụ đã bị pipeline bỏ sót.

**Node/network lỗi.** Một job Java quét hàng nghìn partition dễ gặp timeout từng phần. Không được âm thầm bỏ các partition lỗi rồi trả tổng như thể đầy đủ. Hãy ghi nhận phạm vi đã hoàn thành, checkpoint, retry có giới hạn và kết quả cuối cùng có trạng thái “complete/incomplete” rõ ràng.

**Tải ghi đồng thời.** Một summary đang được dựng khi dữ liệu tiếp tục đến có thể bị lệch do watermark/event late arrival. Cần phân biệt `as_of` (mốc dữ liệu đã xử lý), thời điểm hiển thị và kỳ báo cáo đã đóng.

## 9. Tối ưu và quan sát trước khi quyết định

Các chỉ số nên thu thập cho từng phương án:

| Nhóm | Chỉ số cần quan sát | Ý nghĩa |
| --- | --- | --- |
| Truy vấn Cassandra | p50/p95/p99, read timeout, số partition mỗi request | Thấy rõ độ trễ và fan-out |
| Dữ liệu Cassandra | Kích thước partition, hàng đọc, tombstone, TTL | Tìm dấu hiệu quét rộng dù kết quả nhỏ |
| Hạ tầng | CPU, disk I/O, network, heap, compaction pressure | Tránh báo cáo làm ảnh hưởng đường OLTP |
| Ứng dụng Java | Số hàng duyệt, bytes truyền, số trang, concurrency | Ngăn tăng bộ nhớ, request không có trần |
| Summary | `as_of`, chênh lệch đối soát, số sự kiện đến muộn | Đánh giá độ mới và độ đúng |
| Kho phân tích | Ingest lag, số bản ghi thiếu/trùng, thời gian job, chi phí quét | Đảm bảo pipeline phân tích đáng tin cậy |

Khi so sánh, dùng **cùng một tập sự kiện và một mốc thời gian chốt** để kiểm tra kết quả Java, bảng summary và warehouse. Nếu kết quả khác nhau, tìm nguyên nhân: cửa sổ thời gian, timezone, event duplicate, late arrival, dữ liệu còn cập nhật, lỗi phân trang hoặc pipeline sync.

Không dùng một lần chạy thành công trên dữ liệu mẫu nhỏ làm bằng chứng rằng `COUNT(*)` hay quét toàn bảng phù hợp với sản xuất. Thử tải đồng thời, partition lớn và lỗi node theo quy mô gần với thực tế, nhưng chỉ cần lưu kết quả đo/thiết kế ở bài học này; việc triển khai môi trường vận hành cần kế hoạch riêng.

## 10. Bài thực hành và câu hỏi vận dụng

**Thực hành 1 — Giới hạn theo partition.** Tạo bảng `events_by_device_day`, nạp ba hàng mẫu. Chạy truy vấn từ 09:00 đến 10:00 UTC và tính tổng trên ứng dụng. Thêm sự kiện loại `HEARTBEAT` để chứng minh phép cộng phải xét `event_type`. Đánh giá tác động nếu tăng lên 100.000 hàng trong ngày.

**Thực hành 2 — Nhận diện quét rộng.** Một yêu cầu mới muốn “đếm toàn bộ giao dịch của 10.000 thiết bị trong tháng” từ bảng `events_by_device_day`. Giải thích vì sao `WHERE tenant_id = ? ALLOW FILTERING` hoặc `COUNT(*)` trên toàn bảng không phải giải pháp có khả năng mở rộng. Đề xuất cách bổ sung bảng theo truy vấn hoặc báo cáo OLAP.

**Thực hành 3 — Summary.** Tạo `tenant_daily_payment_totals`, ghi tổng cho ba ngày rồi đọc cả tháng bằng `(tenant_id, year_month)`. Mô tả sự kiện đến muộn làm thay đổi số của ngày hôm trước, cách cập nhật lại snapshot và cách hiển thị `as_of`.

**Thực hành 4 — Lỗi giữa pipeline.** Một event được ghi thành công vào Cassandra nhưng job summary tạm ngừng. Nêu cách phát hiện lỗ hổng, replay có kiểm soát và đối soát. Trả lời vì sao tự động gửi lại một lệnh `counter + 1` không giải quyết bài toán chính xác tuyệt đối.

**Thực hành 5 — Chọn nơi tính.** Với ba yêu cầu sau, chọn Java, summary hay OLAP rồi giải thích: (a) tổng số tiền một thiết bị trong 5 phút; (b) dashboard tenant cập nhật mỗi phút, xem 30 ngày; (c) truy vấn khám phá doanh thu mọi tenant theo sản phẩm, vùng và quý.

**Câu hỏi tư duy:** Nếu warehouse trễ 10 phút nhưng dữ liệu được đối soát chính xác theo watermark, còn Java quét toàn bảng đưa kết quả gần thời gian thực nhưng đôi khi timeout hoặc thiếu partition, cách nào đúng hơn với báo cáo quyết toán? Lựa chọn phụ thuộc **hợp đồng dữ liệu** của báo cáo, không chỉ tốc độ.

## Ghi nhớ

**Cassandra tối ưu cho truy vấn biết khóa phân vùng và phạm vi dữ liệu có giới hạn; nó không phải engine quét rộng để tính tổng hợp tùy ý.** Hãy tính tại ứng dụng Java khi số partition và số hàng có trần, dùng bảng summary cho chỉ số thường xuyên được đọc với độ trễ thấp, và chọn kho phân tích/OLAP cho nhóm, join, xếp hạng hoặc phân tích lịch sử trên lượng dữ liệu lớn. Mọi phương án cần được đánh giá bằng latency, số hàng/partition thực tế, mức nhất quán, độ mới, đối soát và khả năng phục hồi khi lỗi.
