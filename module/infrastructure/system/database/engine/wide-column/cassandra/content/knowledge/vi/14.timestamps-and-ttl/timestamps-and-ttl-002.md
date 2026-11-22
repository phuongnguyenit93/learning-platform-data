# Độ chính xác timestamp của mutation so với kiểu timestamp trong dữ liệu

## 1. Hai loại timestamp, hai mục đích trong Cassandra

Trong **Apache Cassandra** (cơ sở dữ liệu phân tán theo mô hình **wide-column**), từ *timestamp* xuất hiện trong hai ngữ cảnh thường bị nhầm lẫn:

- **Mutation timestamp** (còn gọi là *write timestamp*) là metadata đi kèm một lần ghi cell. Cassandra dùng nó để phân xử phiên bản khi có ghi xung đột theo cơ chế **last-write-wins**.
- **Kiểu dữ liệu CQL `timestamp`** là kiểu dữ liệu của một cột do người thiết kế bảng định nghĩa, dùng để lưu một thời điểm trong nghiệp vụ, chẳng hạn lúc tạo đơn hàng hoặc thời điểm thiết bị phát sinh sự kiện.

Hai giá trị có thể biểu diễn cùng một mốc thời gian, nhưng **không cùng độ phân giải, không tự động đồng bộ với nhau và không đảm nhiệm cùng vai trò**.

| Đặc tính | Mutation timestamp | Cột CQL kiểu `timestamp` |
|---|---|---|
| Mục đích | Chọn phiên bản thắng trong xung đột ghi của cell | Lưu mốc thời gian nghiệp vụ để hiển thị, lưu trữ hoặc truy vấn |
| Đơn vị lưu/biểu diễn cốt lõi | **Micro giây (µs)** kể từ Unix epoch | **Mili giây (ms)** kể từ Unix epoch |
| Số chữ số phần giây có thể biểu diễn | Tới 6 chữ số: `.123456` | Tới 3 chữ số: `.123` |
| Cách gán | `USING TIMESTAMP`, timestamp generator trong driver hoặc coordinator | Giá trị trong `INSERT`, `UPDATE` hay tham số truy vấn |
| Cách đọc qua CQL | `writetime(ten_cot)` với cột hỗ trợ | `SELECT ten_cot` |
| Có thể dùng làm partition/clustering key? | Không, vì nó là metadata của cell | Có thể dùng cột CQL `timestamp` trong khóa nếu đáp ứng cách thiết kế bảng |
| Ảnh hưởng trực tiếp đến last-write-wins? | **Có** | **Không**; trừ khi ứng dụng chủ động chuyển giá trị thành mutation timestamp khi ghi |

> **Ý quan trọng:** “Micro giây” và “mili giây” ở đây là **độ phân giải biểu diễn**. Việc dùng đơn vị micro giây không có nghĩa đồng hồ của máy đo thời gian ngoài đời chính xác tuyệt đối tới từng micro giây, hay mọi lần ghi đều có timestamp khác nhau.

## 2. Unix epoch và phép đổi đơn vị

Cả hai dạng đều có thể dựa trên **Unix epoch**, tức mốc `1970-01-01T00:00:00Z`. Với cùng một thời điểm:

```text
2026-01-01T00:00:00.123456Z
                       └── 123456 micro giây trong giây đầu tiên

Epoch seconds:        1767225600
Epoch milliseconds:   1767225600123
Epoch microseconds:   1767225600123456
                                    ^^^
                            456 µs còn dư sau khi đổi sang ms
```

Quan hệ số học với các epoch không âm:

```text
microseconds = milliseconds * 1_000 + microseconds_remainder
milliseconds = floor(microseconds / 1_000)

1767225600123456 µs
  = 1767225600123 ms * 1000 + 456 µs
```

Nếu lưu sự kiện trên vào **cột CQL `timestamp`**, chỉ giữ được mốc ở mức mili giây, ví dụ `2026-01-01T00:00:00.123Z`. Phần `456 µs` nhỏ hơn một mili giây không được cột này bảo toàn. Trong khi đó, mutation timestamp có thể mang số `1767225600123456` dưới dạng metadata.

Nếu chuyển ngược từ epoch milliseconds sang epoch microseconds bằng cách nhân `1000`, phần nhỏ hơn mili giây đã mất **không thể khôi phục**:

```text
1767225600123 ms × 1000 = 1767225600123000 µs
1767225600123456 µs - 1767225600123000 µs = 456 µs bị mất
```

Các con số trên còn minh họa lỗi phổ biến: đưa trực tiếp giá trị 13 chữ số của **epoch milliseconds** vào `USING TIMESTAMP`, nơi Cassandra chờ giá trị khoảng 16 chữ số của **epoch microseconds**. Mutation đó bị hiểu như một thời điểm rất xa trong quá khứ so với các ghi hiện tại, dễ liên tục thua theo last-write-wins.

## 3. Ví dụ CQL: cùng một cột, hai timestamp khác nhau

Thí nghiệm sau dành cho một **keyspace thử nghiệm** đã được chọn bằng `USE`. Dùng một UUID chưa từng ghi để tránh dữ liệu và tombstone của lần chạy trước làm sai kết quả.

### Tạo bảng

```sql
CREATE TABLE IF NOT EXISTS event_records (
    event_id uuid PRIMARY KEY,
    event_at timestamp,
    processing_state text
);
```

`event_at` là cột chứa thời điểm của sự kiện; `processing_state` là trạng thái mà ứng dụng có thể thay đổi. Mỗi cell vẫn được Cassandra gắn **write timestamp riêng**.

### Ghi với mutation timestamp chỉ định rõ

```sql
INSERT INTO event_records (
    event_id,
    event_at,
    processing_state
)
VALUES (
    22222222-2222-2222-2222-222222222222,
    '2026-01-01T00:00:00.123Z',
    'queued'
)
USING TIMESTAMP 1767225600123456;

SELECT event_at,
       writetime(event_at),
       processing_state,
       writetime(processing_state)
FROM event_records
WHERE event_id = 22222222-2222-2222-2222-222222222222;
```

Kết quả về mặt ý nghĩa:

| Biểu thức | Giá trị kỳ vọng | Diễn giải |
|---|---|---|
| `event_at` | `2026-01-01 00:00:00.123` theo cách hiển thị của client | Cột CQL `timestamp`, mức **mili giây** |
| `writetime(event_at)` | `1767225600123456` | Write timestamp của cell `event_at`, mức **micro giây** |
| `processing_state` | `queued` | Dữ liệu cột text |
| `writetime(processing_state)` | `1767225600123456` | Write timestamp của cell `processing_state` |

**Nhận xét:** `event_at` và `writetime(event_at)` đều liên quan đến thời gian, nhưng một bên là **giá trị người dùng**, bên kia là **metadata Cassandra dùng để hòa giải ghi**. Trường hợp này chúng gần bằng nhau là do ta **cố tình** chọn cùng mốc. Cassandra không tự suy ra mutation timestamp từ `event_at`.

### Chênh nhau một vài micro giây cũng có thể đổi kết quả LWW

Thử cập nhật `processing_state` với timestamp **cũ hơn** timestamp ban đầu **56 µs**:

```sql
UPDATE event_records
USING TIMESTAMP 1767225600123400
SET processing_state = 'stale'
WHERE event_id = 22222222-2222-2222-2222-222222222222;

SELECT processing_state, writetime(processing_state)
FROM event_records
WHERE event_id = 22222222-2222-2222-2222-222222222222;
```

Kết quả vẫn là `queued` với write timestamp `1767225600123456` vì mutation `...3400` nhỏ hơn `...3456`. Dù câu `UPDATE` đã chạy sau `INSERT`, nó vẫn thua theo quy tắc LWW.

Tiếp theo ghi với timestamp **mới hơn một micro giây**:

```sql
UPDATE event_records
USING TIMESTAMP 1767225600123457
SET processing_state = 'processed'
WHERE event_id = 22222222-2222-2222-2222-222222222222;

SELECT event_at, writetime(event_at),
       processing_state, writetime(processing_state)
FROM event_records
WHERE event_id = 22222222-2222-2222-2222-222222222222;
```

Lúc này `processing_state = 'processed'` với write timestamp `...3457`; `event_at` vẫn mang write timestamp `...3456`, vì chỉ cell trạng thái được cập nhật. Cột `event_at` tự nó **không tăng độ chính xác** chỉ vì mutation mới hơn 1 µs.

**Giới hạn của `writetime()`:** hàm đọc write timestamp của các cột thường được hỗ trợ; không dùng để đọc timestamp của **primary-key column** hoặc **counter**. Với cell đã xóa, `writetime()` không phải công cụ xem trực tiếp timestamp của tombstone. Tùy trạng thái dữ liệu và loại cột, kết quả có thể là `null` hoặc truy vấn bị từ chối.

## 4. Khác biệt giữa độ phân giải, độ chính xác và thứ tự ghi

Hãy tách ba khái niệm:

1. **Độ phân giải (resolution):** đơn vị nhỏ nhất mà biểu diễn cho phép phân biệt. Mutation timestamp dùng µs; CQL `timestamp` dùng ms.
2. **Độ chính xác (accuracy):** thời gian được ghi nhận có gần thời gian thực tế không. Đồng hồ lệch, độ trễ mạng, bộ sinh timestamp hoặc thời điểm lấy mẫu đều gây sai lệch.
3. **Thứ tự đảm bảo (ordering):** hai số timestamp có phản ánh thứ tự nghiệp vụ thực tế không. Cassandra chỉ so sánh các **giá trị timestamp**, không tự biết sự kiện nào thực sự xảy ra trước.

Ví dụ, một máy có đồng hồ nhanh hơn thực tế 5 phút có thể gán mutation timestamp tương lai cho `status = 'approved'`. Máy khác nhận sự kiện `status = 'cancelled'` sau đó theo thời gian thực nhưng gán timestamp nhỏ hơn. Cassandra có thể tiếp tục chọn `approved` do LWW. Sự có mặt của **micro giây** không giải quyết sai lệch này.

Tương tự, hai yêu cầu từ hai dịch vụ có thể nhận **cùng mutation timestamp** dù cấu trúc thời gian hỗ trợ micro giây. Cassandra có quy tắc phân xử khi timestamp bằng nhau; không nên mặc định “lệnh gửi sau thắng”. Trường hợp tombstone xung đột với giá trị sống ở cùng timestamp, tombstone được ưu tiên. Khi ứng dụng cần cập nhật có điều kiện, có thể cần **lightweight transaction (LWT)** hoặc mô hình dữ liệu/sự kiện được thiết kế riêng.

## 5. Timestamp mặc định đến từ đâu?

Khi câu CQL không có `USING TIMESTAMP`, Cassandra/driver vẫn phải xác định mutation timestamp cho ghi thông thường. Tùy phiên bản và cấu hình:

- **Driver** có thể tạo timestamp phía client bằng một **timestamp generator** rồi gửi cùng yêu cầu.
- **Coordinator** có thể tạo timestamp khi phía client không cung cấp.
- **`USING TIMESTAMP <số>`** cho phép người viết CQL chỉ định timestamp theo đơn vị **micro giây**, thay cho chính sách tự sinh của câu ghi đó.

Một số bộ sinh timestamp phía client cố duy trì thứ tự tăng trên cùng tiến trình khi nhiều mutation được phát nhanh. Điều này **không bảo đảm** thứ tự toàn cục giữa nhiều ứng dụng hoặc độ chính xác tuyệt đối của đồng hồ vật lý.

Để giảm xung đột không mong muốn, nên đồng bộ giờ hệ thống, giám sát **clock skew**, thống nhất chính sách tạo timestamp giữa các service và hạn chế tự gán timestamp trừ khi bài toán thật sự cần. Đối với retry của cùng một sự kiện, cần xem xét dùng timestamp ổn định để tránh một retry muộn vô tình trở thành bản ghi mới hơn.

## 6. Ứng dụng Java: `Instant`, mili giây và micro giây

Ứng dụng Java kết nối Cassandra bằng **DataStax/Apache Cassandra Java Driver** (API 4.x) thường xử lý thời điểm nghiệp vụ bằng `java.time.Instant`.

`Instant` của Java hỗ trợ phần nano giây, nhưng khi bind vào cột CQL `timestamp`, Cassandra lưu ở **độ phân giải mili giây**. Nếu muốn tự gán mutation timestamp, phải chuyển `Instant` sang **epoch microseconds** đúng đơn vị.

```java
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public class EventRepository {
    private final CqlSession session;
    private final PreparedStatement insert;

    public EventRepository(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO event_records " +
            "(event_id, event_at, processing_state) " +
            "VALUES (?, ?, ?) USING TIMESTAMP ?"
        );
    }

    public void save(UUID eventId, Instant eventTime) {
        // Ví dụ: 2026-01-01T00:00:00.123456Z
        long epochMillis = eventTime.toEpochMilli(); // 1767225600123

        // Chuyển đúng sang epoch microseconds, giữ phần µs từ Instant.
        long epochMicros = Math.addExact(
            Math.multiplyExact(eventTime.getEpochSecond(), 1_000_000L),
            eventTime.getNano() / 1_000L
        ); // 1767225600123456

        // event_at chỉ lưu đến ms; mutation timestamp nhận epochMicros.
        session.execute(insert.bind(eventId, eventTime, "queued", epochMicros));
    }
}
```

Với `Instant.parse("2026-01-01T00:00:00.123456Z")`, phép tính trả đúng hai giá trị trong phần 2. Dùng `Math.multiplyExact` và `Math.addExact` còn giúp phát hiện tràn số nếu phạm vi thời gian bất thường.

### Các lỗi Java dễ gặp

| Mã hoặc ý tưởng sai | Vấn đề | Cách xử lý |
|---|---|---|
| `USING TIMESTAMP = System.currentTimeMillis()` | Truyền **ms** vào trường yêu cầu **µs** | Chuyển đúng đơn vị; nếu cần micro giây thực, lấy nguồn thời gian có phần nhỏ hơn ms |
| `eventTime.toEpochMilli() * 1000` và nghĩ luôn chính xác 1 µs | Đơn vị đã đúng, nhưng phần nhỏ hơn **1 ms** từ `Instant` bị mất | Dùng `getEpochSecond()` và `getNano()/1000` nếu cần giữ micro giây sẵn có |
| `eventTime.getNano()` đem dùng làm Unix microseconds | `getNano()` chỉ là phần trong giây, không có số giây từ epoch | Cộng phần giây epoch × 1 triệu với phần nano quy đổi |
| Dùng `Instant.now()` ở mọi client rồi tin thứ tự toàn hệ thống | Đồng hồ giữa máy có thể lệch; độ phân giải không đồng nghĩa độ chính xác | Đồng bộ đồng hồ và thiết kế quy tắc thứ tự nghiệp vụ rõ ràng |
| Mong đọc lại đủ `.123456` từ cột `timestamp` | CQL `timestamp` chỉ giữ mức ms | Cất thêm epoch microseconds dạng `bigint` khi có yêu cầu bảo toàn |

Lưu ý: không nhất thiết phải dùng chính `eventTime` làm mutation timestamp. Ví dụ, nghiệp vụ có thể cần **thời gian phát sinh sự kiện** và **thời gian cập nhật trạng thái** là hai dòng thời gian độc lập. Chọn cùng một timestamp chỉ khi chính sách xung đột của hệ thống thật sự yêu cầu điều đó.

## 7. Nếu nghiệp vụ cần giữ micro giây trong dữ liệu

Hệ thống telemetry, tài chính hoặc xử lý luồng có thể nhận dữ liệu có dấu thời gian chính xác tới micro giây. Khi đó một cột CQL `timestamp` **không đủ để lưu nguyên vẹn** độ phân giải đầu vào.

Một lựa chọn rõ ràng là lưu **epoch microseconds** vào cột `bigint` và tùy nhu cầu lưu thêm cột `timestamp` để thuận tiện hiển thị:

```sql
CREATE TABLE sensor_events_by_device_day (
    device_id text,
    event_day date,
    event_time_us bigint,
    event_id uuid,
    event_at timestamp,
    measurement double,
    PRIMARY KEY (
        (device_id, event_day),
        event_time_us,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time_us DESC,
    event_id ASC
);
```

Mô hình này phù hợp với truy vấn **các sự kiện mới nhất của một thiết bị trong một ngày**, có thể lọc theo `device_id`, `event_day` và khoảng `event_time_us` (theo thứ tự clustering key). `event_id` giúp phân biệt nhiều sự kiện cùng micro giây. `event_at` chỉ dùng làm giá trị thời gian mức mili giây thuận tiện cho trình bày. Cần giới hạn số bản ghi trong mỗi partition bằng chiến lược bucket phù hợp với lưu lượng thật.

Ví dụ truy vấn:

```sql
SELECT event_time_us, event_id, event_at, measurement
FROM sensor_events_by_device_day
WHERE device_id = 'sensor-07'
  AND event_day = '2026-01-01'
  AND event_time_us >= 1767225600000000
  AND event_time_us < 1767312000000000
LIMIT 100;
```

Ở đây, **thứ tự đọc hàng** do **clustering key `event_time_us`** tạo ra; Cassandra **không tự sắp xếp hàng theo `writetime()`**. Đó là nguyên tắc quan trọng của thiết kế bảng theo truy vấn trong hệ thống wide-column.

Việc lưu micro giây dưới dạng `bigint` vẫn chỉ phản ánh độ chính xác của dữ liệu nguồn. Nếu cảm biến chỉ đo đến mili giây, việc nhân số mili giây lên `1000` không tạo ra thông tin thời gian mới.

## 8. Liên hệ TTL, replication, consistency và repair

Chương **Timestamp và TTL** còn có một đơn vị thời gian khác cần phân biệt: **TTL (time to live) trong CQL tính theo giây**.

```sql
UPDATE event_records
USING TTL 3600
SET processing_state = 'temporary'
WHERE event_id = 22222222-2222-2222-2222-222222222222;
```

Ở lệnh này:

- `TTL 3600` quy định vòng đời của cell trạng thái trong khoảng **3.600 giây**.
- Mutation của cell vẫn có **write timestamp tính bằng micro giây** (theo chính sách tự sinh nếu không có `USING TIMESTAMP`).
- Nếu đọc `ttl(processing_state)` ngay sau khi ghi, có thể quan sát số **giây còn lại** của cell, chứ không phải micro giây.
- Cột `event_at timestamp` trong bảng vẫn là dữ liệu nghiệp vụ có độ phân giải **mili giây**.

Trong cluster có nhiều replica, các bản ghi đến các node không nhất thiết theo cùng thứ tự. **Replication factor** quyết định số bản sao; **consistency level** như `ONE`, `QUORUM`, `ALL` quyết định yêu cầu phản hồi khi đọc/ghi; còn **mutation timestamp** quyết định phiên bản cell thắng khi hòa giải. Tăng consistency level không sửa được một mutation mang timestamp sai đơn vị hoặc đến từ đồng hồ bị lệch.

Khi một cell hết TTL hoặc bị xóa, Cassandra dùng cơ chế dữ liệu hết hạn/tombstone để ngăn bản cũ xuất hiện trở lại trước khi được dọn an toàn. Các công việc **compaction**, **repair** và chính sách tombstone phải được xem xét trong vận hành; không thể chỉ dựa vào độ phân giải timestamp để suy ra replica đã hoàn toàn đồng bộ.

## 9. Checklist khi phát hiện lỗi timestamp

| Triệu chứng | Cần kiểm tra |
|---|---|
| `UPDATE` báo thành công nhưng `SELECT` giữ giá trị trước đó | `writetime()` của cell, `USING TIMESTAMP` và khả năng có tombstone mang timestamp lớn hơn |
| Hai dịch vụ ghi “cùng lúc” nhưng ghi của một dịch vụ luôn thua | Đơn vị **ms/µs**, timestamp generator, clock skew giữa máy |
| API nhận `.123456` nhưng đọc từ cột thời gian chỉ còn `.123` | Kiểu CQL `timestamp` có độ phân giải **ms**; cần `bigint` nếu muốn lưu đủ µs |
| Dữ liệu xuất hiện khác nhau giữa các replica | Mức nhất quán, replica đang tham gia đọc, tình trạng repair và xung đột write timestamp |
| Các kết quả hiển thị lệch vài giờ | Cách định dạng múi giờ của client và offset trong chuỗi CQL; dùng `Z` hoặc offset rõ ràng |
| Truy vấn không thể `ORDER BY writetime(...)` | Muốn sắp thứ tự sự kiện phải thiết kế clustering key theo truy vấn |

Để chẩn đoán, cần ghi lại **đơn vị và nguồn tạo timestamp** trong log ứng dụng, không chỉ in một số nguyên trần. Khi truyền thời gian dưới dạng JSON hay API, nên đặt tên rõ: `eventTimeEpochMicros`, `eventTimeEpochMillis` hoặc dùng ISO-8601 có offset như `2026-01-01T00:00:00.123Z`.

## 10. Bài tập tự kiểm tra

**Câu 1.** Một ứng dụng lưu `event_at` = `2026-01-01T00:00:00.123Z` và `writetime(event_at)` = `1767225600123456`. Hai giá trị có trái ngược nhau không?

**Đáp án:** Không. `event_at` là dữ liệu mức mili giây; `writetime(event_at)` là metadata mức micro giây. Chúng không bị ràng buộc phải bằng nhau, dù ví dụ chọn gần cùng mốc.

**Câu 2.** Nếu hai mutation cùng một cell có timestamp lần lượt `1767225600123456` và `1767225600123457`, mutation nào thắng sau hòa giải?

**Đáp án:** Mutation có `...3457` vì lớn hơn 1 µs. Không suy ra rằng mutation này chắc chắn đến sau theo thời gian vật lý.

**Câu 3.** Có thể dùng `Instant.toEpochMilli() * 1000` để tạo số micro giây không?

**Đáp án:** Có thể tạo **giá trị epoch microseconds**, nhưng **không giữ được phần µs dưới mức ms** của `Instant`. Nếu cần độ phân giải micro giây vốn có, dùng `getEpochSecond() * 1_000_000 + getNano() / 1_000`.

**Câu 4.** Muốn liệt kê sự kiện của thiết bị theo thứ tự từ mới đến cũ ở mức micro giây, chỉ lưu mutation timestamp có đủ không?

**Đáp án:** Không. Cassandra không dùng mutation timestamp làm khóa sắp thứ tự truy vấn. Hãy lưu mốc thời gian nghiệp vụ với độ phân giải cần thiết và thiết kế **clustering key** theo cách truy vấn.

**Câu 5.** `USING TTL 3600` tương ứng 3.600 micro giây, mili giây hay giây?

**Đáp án:** **Giây**. TTL, CQL `timestamp` và mutation timestamp là ba khái niệm thời gian với ba vai trò, đơn vị khác nhau.

**Ghi nhớ:** Mutation timestamp của Cassandra biểu diễn **micro giây** và phục vụ **last-write-wins**; kiểu cột CQL `timestamp` lưu mốc thời gian nghiệp vụ ở mức **mili giây**; TTL được tính bằng **giây**. Chuyển đổi đơn vị đúng là điều kiện cần, nhưng độ chính xác đồng hồ và thứ tự nghiệp vụ vẫn phải được thiết kế và kiểm soát riêng.
