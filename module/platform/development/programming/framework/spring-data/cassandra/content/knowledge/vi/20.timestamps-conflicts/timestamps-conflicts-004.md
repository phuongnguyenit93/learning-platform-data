# Đơn vị thời gian và nguy cơ nhầm mili giây với micro giây

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **thời điểm nghiệp vụ được lưu trong cột CQL `timestamp`** với **write timestamp của một mutation** mà Cassandra dùng để giải quyết xung đột.
- Nhớ chính xác: CQL `timestamp` biểu diễn thời điểm ở độ phân giải **mili giây (ms)**; `USING TIMESTAMP` và `WRITETIME(column)` dùng **micro giây (µs)**; kiểu Java `Instant` có trường nanosecond (`ns`), nhưng độ chính xác thực tế phụ thuộc nguồn và kiểu lưu.
- Đọc một con số epoch và xác định liệu nó đang ở đơn vị giây, mili giây, micro giây hay nano giây; nhận diện lỗi nhân/chia sai `1.000` hoặc `1.000.000`.
- Viết chuyển đổi epoch milliseconds ↔ microseconds ↔ `Instant` bằng Java có kiểm soát tràn số và xử lý mốc **trước năm 1970**.
- Sử dụng `USING TIMESTAMP`, `WRITETIME`, prepared statements và `CqlSession` đúng ngữ nghĩa, không nhầm chúng với thuộc tính `createdAt`/`updatedAt` của entity.
- Giải thích **last-write-wins (LWW) theo cell**, ảnh hưởng của clock skew, retry, timestamp do client tự cung cấp, tombstone và các sự kiện đến sai thứ tự.
- Biết khi nào cần `IF NOT EXISTS`, `IF ...` và cơ chế điều phối/version nghiệp vụ thay vì cố dùng write timestamp để xây một hệ thống optimistic locking.
- Thiết kế test, metrics và checklist để tránh ghi dữ liệu “ở năm 1970”, giá trị thời gian quá xa trong tương lai hoặc mutation có write timestamp áp đảo các write hợp lệ.
- Kết hợp hiểu biết timestamp với **Spring Data Cassandra**, entity mapping, `CassandraTemplate`, repository, CQL, partition key, paging và vận hành cluster phân tán.

Bài thuộc chương **Timestamp và xung đột** của **SPRING_DATA_CASSANDRA**. Mô-đun học cách truy cập Apache Cassandra bằng Spring Data Cassandra với entity mapping, repository, `CassandraTemplate` và truy vấn CQL; đồng thời thiết kế bảng theo truy vấn, partition key, consistency, paging và kiểm soát hiệu năng. Vì Cassandra phân tán dữ liệu trên nhiều replica và giải quyết xung đột ở mức cell, **đúng đơn vị thời gian là yêu cầu về tính đúng đắn dữ liệu**, không chỉ là vấn đề định dạng ngày giờ.

> **Ghi nhớ nhanh:** `timestamp` CQL: **milliseconds** kể từ Unix epoch. `USING TIMESTAMP` / `WRITETIME`: **microseconds** kể từ Unix epoch. `Instant.getNano()`: phần nanoseconds trong giây, **không** phải số nanosecond từ epoch. `System.nanoTime()`: đồng hồ đo thời gian trôi qua, **không được dùng làm Unix timestamp**.

## 1. Tại sao Cassandra có nhiều loại “timestamp”?

Xét ứng dụng đơn hàng có hai sự kiện:

1. Khách đặt đơn lúc 10:00:00.123 UTC.
2. Hệ thống ghi trạng thái `PAID` vài giây sau đó.

Một bảng đơn giản:

~~~sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    created_at timestamp,
    status text,
    revision bigint
);
~~~

Có ít nhất hai khái niệm thời gian:

| Khái niệm | Chức năng | Đơn vị/kiểu |
| --- | --- | --- |
| `created_at` trong một row | Dữ liệu nghiệp vụ: đơn được tạo lúc nào | CQL `timestamp`, độ phân giải mili giây |
| Write timestamp của cell `status` | Metadata giúp Cassandra chọn giá trị nào thắng khi mutation cạnh tranh | Số nguyên 64-bit, micro giây |
| `Instant` Java | Biểu diễn thời điểm trong ứng dụng | Giây từ epoch + phần nanosecond |
| Thời điểm client nhận response | Quan sát độ trễ và SLA | Đồng hồ/metrics phía ứng dụng, không đồng nghĩa metadata cell |
| `revision` nghiệp vụ | Số phiên bản do ứng dụng định nghĩa | Số nguyên, Cassandra không tự ưu tiên giá trị lớn hơn |

Nếu ứng dụng gửi:

~~~sql
INSERT INTO orders_by_id (order_id, created_at, status, revision)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-25T10:00:00.123Z',
    'CREATED',
    1
);
~~~

thì giá trị `created_at` là **thời gian của một sự kiện**, không phải write timestamp mà server nhất thiết dùng cho toàn mutation. Cassandra có thể gán write timestamp riêng, thường từ cơ chế timestamp mặc định của driver/server, hoặc nhận write timestamp tường minh từ request.

Câu hỏi “cột `created_at` đang bằng bao nhiêu?” khác với “cell `status` được ghi bằng timestamp xung đột bao nhiêu?”. Chúng có thể khác cả **ý nghĩa**, **đơn vị** lẫn **giá trị số**.

### 1.1. Mô hình hai lớp

~~~mermaid
flowchart TD
    A["Java Instant - seconds + nanos"] --> B["CQL timestamp: created_at"]
    B --> C["Giá trị thời điểm được lưu: mili giây"]
    D["Mutation INSERT/UPDATE"] --> E["Write timestamp: micro giây"]
    E --> F["Last-write-wins theo cell"]
    F --> G["Giá trị status được nhìn thấy khi đọc"]
    C --> H["SELECT created_at"]
    G --> I["SELECT status, WRITETIME(status)"]
~~~

Đừng dùng một biến tên `timestamp` mơ hồ cho cả hai lớp. Có thể dùng tên rõ ý nghĩa hơn:

- `createdAt`: `Instant`/giá trị thời điểm của đơn.
- `createdAtEpochMillis`: số mili giây từ epoch.
- `mutationTimestampMicros`: số micro giây dùng cho `USING TIMESTAMP`.
- `statusWriteTimeMicros`: metadata đọc từ `WRITETIME(status)`.
- `businessRevision`: version nghiệp vụ độc lập với đồng hồ.

## 2. Bảng quy đổi các đơn vị thời gian

Một **Unix epoch timestamp** thường đếm thời gian kể từ `1970-01-01T00:00:00Z`. Tên “timestamp” **không nói rõ đơn vị** nếu không có hợp đồng API.

| Đơn vị | Ký hiệu | Số đơn vị trong 1 giây | Trường hợp thường gặp |
| --- | --- | ---: | --- |
| Giây | s | 1 | `Instant.getEpochSecond()`, epoch seconds trong một số API |
| Mili giây | ms | 1.000 | CQL `timestamp`, `System.currentTimeMillis()` |
| Micro giây | µs/us | 1.000.000 | Cassandra `USING TIMESTAMP`, `WRITETIME` |
| Nano giây | ns | 1.000.000.000 | Phần nanosecond của `Instant`, CQL `time` |

Các công thức cơ bản cho thời điểm không âm:

~~~text
epochMillis = epochSeconds * 1_000
epochMicros = epochMillis * 1_000
epochNanos  = epochMicros * 1_000

epochMicros = epochSeconds * 1_000_000
epochNanos  = epochSeconds * 1_000_000_000
~~~

**Cảnh báo:** Với thời điểm **trước epoch**, integer division trong Java làm tròn về 0 có thể tạo lỗi biên. Khi muốn lấy phần giây/mili từ microseconds âm, dùng `Math.floorDiv` / `Math.floorMod` hoặc API `Instant` phù hợp, không cắt chuỗi hay chia số âm tùy tiện.

### 2.1. Một thời điểm, ba dạng số

Chọn thời điểm cố định để dễ kiểm tra:

~~~text
2023-11-14T22:13:20.123Z

epoch seconds (nguyên):       1_700_000_000
epoch milliseconds:           1_700_000_000_123
epoch microseconds:           1_700_000_000_123_000
epoch nanoseconds:            1_700_000_000_123_000_000
~~~

Cùng một thời điểm, nhưng **khác hẳn bậc độ lớn**:

- 10 chữ số thường gợi ý epoch seconds gần hiện tại.
- 13 chữ số thường gợi ý milliseconds.
- 16 chữ số thường gợi ý microseconds.
- 19 chữ số thường gợi ý nanoseconds.

Đây chỉ là **mẹo phát hiện lỗi**, không phải chuẩn kiểm chứng: thời điểm trước epoch, dữ liệu lịch sử hoặc năm khác khiến số chữ số thay đổi. Hợp đồng API/schema phải nói rõ đơn vị.

### 2.2. Cùng giá trị số nhưng hiểu sai đơn vị

Nếu một API gửi `1_700_000_000_123` và bạn hiểu đó là **milliseconds**, nó tương ứng năm 2023 trong ví dụ. Nhưng nếu vô tình dùng trực tiếp nó như **microseconds** cho `USING TIMESTAMP`, đó là thời điểm chỉ cách epoch khoảng 19,7 ngày — vào **tháng 1 năm 1970**.

Ở chiều ngược lại, nếu đọc `1_700_000_000_123_000` microseconds từ `WRITETIME` rồi hiểu là milliseconds để tạo `Instant.ofEpochMilli(…)`, bạn đang cố mô tả một thời điểm rất xa tương lai, thậm chí vượt phạm vi nhiều hệ thống.

Hai lỗi phổ biến:

~~~java
// SAI: milliseconds bị đưa thẳng vào USING TIMESTAMP (đơn vị µs).
long writeTimestampWrong = System.currentTimeMillis();

// SAI: giá trị WRITETIME (µs) bị hiểu là milliseconds.
Instant displayedWrong = Instant.ofEpochMilli(writeTimeMicros);
~~~

Hệ quả có thể là:

- Mutation vô tình mang timestamp quá cũ và **không thắng** cell đang tồn tại.
- Mutation vô tình mang timestamp rất xa tương lai và **áp đảo** nhiều cập nhật hợp lệ sau đó.
- Dữ liệu hiển thị ở năm 1970 hoặc thời điểm không hợp lý.
- Mapper hoặc serializer ném exception do giá trị thời gian vượt miền hỗ trợ.
- Retry hoặc replay làm thay đổi trạng thái theo thứ tự timestamp sai, rất khó tìm nếu chỉ xem `updated_at`.

## 3. CQL timestamp: dữ liệu thời điểm có độ phân giải mili giây

Kiểu CQL `timestamp` dùng để lưu **thời điểm tuyệt đối**, theo đơn vị milliseconds kể từ Unix epoch. Có thể biểu diễn bằng chuỗi ngày giờ có timezone hoặc qua driver bằng `Instant`/kiểu Java tương thích.

~~~sql
CREATE TABLE events_by_id (
    event_id uuid PRIMARY KEY,
    occurred_at timestamp,
    recorded_at timestamp,
    description text
);
~~~

Ví dụ:

~~~sql
INSERT INTO events_by_id (
    event_id, occurred_at, recorded_at, description
)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-25T10:00:00.123Z',
    '2026-11-25T10:00:01.456Z',
    'OrderCreated'
);
~~~

Hai cột `occurred_at` và `recorded_at` vẫn đều là CQL `timestamp`. Chúng khác nhau ở ngữ nghĩa nghiệp vụ: thời điểm sự kiện xảy ra và thời điểm hệ thống ghi nhận.

### 3.1. CQL timestamp không lưu timezone như metadata của từng cell

Một thời điểm ở UTC có thể được hiển thị theo múi giờ địa phương:

~~~text
2026-11-25T10:00:00.123Z
2026-11-25T17:00:00.123+07:00
~~~

Hai chuỗi mô tả **cùng một instant**, không phải hai sự kiện cách nhau bảy giờ. Cassandra lưu giá trị epoch milliseconds, không lưu “Asia/Ho_Chi_Minh” như một thành phần độc lập của kiểu `timestamp`.

Cách an toàn:

- Bên trong ứng dụng dùng `Instant` cho thời điểm tuyệt đối.
- API dùng ISO-8601/RFC 3339 với `Z` hoặc offset rõ ràng.
- Nếu nghiệp vụ cần timezone gốc của lịch hẹn, lưu **zone ID** riêng (ví dụ `Asia/Ho_Chi_Minh`) cùng với instant/giờ địa phương theo mô hình cụ thể.
- Không parse `"2026-11-25 10:00"` thành instant nếu chưa xác định timezone.
- Tránh đồng nhất thời gian nghiệp vụ và thời gian ghi vào Cassandra.

### 3.2. Java Instant có nanoseconds, CQL timestamp lưu milliseconds

~~~java
import java.time.Instant;

Instant input = Instant.parse("2026-11-25T10:00:00.123456789Z");
long epochMillis = input.toEpochMilli();

System.out.println(epochMillis);
// Giá trị milliseconds tương ứng, mất phần micro/nano dưới một ms.
~~~

Khi `input` được lưu vào CQL `timestamp`, không nên kỳ vọng đọc lại giữ chính xác `123456789` nanoseconds. Kiểu Cassandra lưu độ phân giải **mili giây**, nên phần nhỏ hơn một mili giây không có chỗ tồn tại trong cột `timestamp`.

Ví dụ vòng đời:

~~~text
Java input:    10:00:00.123456789Z
CQL timestamp: 10:00:00.123Z
Java readback: 10:00:00.123Z
~~~

Đây là mất độ chính xác theo kiểu dữ liệu, không phải lỗi phân tán hay race condition.

**Lưu ý:** `Instant` có khả năng biểu diễn nanoseconds nhưng đồng hồ máy hoặc nguồn event có thể chỉ chính xác đến milliseconds/microseconds. Độ phân giải của kiểu không đồng nghĩa độ chính xác vật lý của nguồn.

### 3.3. Các kiểu thời gian khác không được nhầm lẫn

| Kiểu Cassandra / Java | Đại diện | Đơn vị hoặc tính chất |
| --- | --- | --- |
| CQL `timestamp` | Thời điểm tuyệt đối | Epoch milliseconds |
| CQL `date` | Ngày lịch | Không chứa giờ trong ngày |
| CQL `time` | Giờ trong ngày | Nanoseconds kể từ nửa đêm, **không** phải epoch timestamp |
| CQL `timeuuid` | UUID theo thời gian | Có phần timestamp và thứ tự đặc thù UUID v1, không phải `long` milliseconds |
| CQL `duration` | Khoảng thời gian | Gồm tháng, ngày, nanoseconds; không phải một epoch instant |
| Java `Instant` | Thời điểm tuyệt đối | Epoch seconds + nanoseconds |
| Java `LocalDateTime` | Ngày/giờ **không kèm zone** | Không đủ để xác định epoch instant |
| Java `System.nanoTime()` | Đo thời gian trôi qua | Không có origin Unix epoch được bảo đảm |

Nếu hệ thống log số microseconds trong khi API lại đặt tên là `timestampMillis`, một lập trình viên khác rất dễ chuyển sai sau này. Đặt tên gắn với **đơn vị và ngữ nghĩa** là biện pháp phòng lỗi rẻ nhất.

## 4. Write timestamp của Cassandra: microseconds trên mutation

Cassandra dùng **write timestamp** để giải quyết xung đột giữa các mutation thường. Write timestamp là metadata gắn với cell/ghi, với độ phân giải **microseconds** kể từ epoch.

Khác với cột `created_at timestamp`:

~~~text
created_at
  = một giá trị nghiệp vụ được lưu trong cell, độ phân giải ms

write timestamp của created_at
  = thời điểm/độ ưu tiên mutation đối với cell ấy, đơn vị µs
~~~

Cassandra có cơ chế tạo timestamp mặc định khi statement không chỉ định, và Java Driver có thể tham gia việc tạo/gửi timestamp tùy configuration. Khi dùng `USING TIMESTAMP` hoặc timestamp tường minh ở driver, **ứng dụng đang trực tiếp tác động đến conflict resolution**.

### 4.1. USING TIMESTAMP nhận microseconds

Ví dụ đơn giản:

~~~sql
CREATE TABLE IF NOT EXISTS timestamp_lab (
    id uuid PRIMARY KEY,
    observed_at timestamp,
    state text,
    revision bigint
);
~~~

Ghi có timestamp tường minh:

~~~sql
INSERT INTO timestamp_lab (
    id, observed_at, state, revision
)
VALUES (
    33333333-3333-4333-8333-333333333333,
    '2023-11-14T22:13:20.123Z',
    'CREATED',
    1
)
USING TIMESTAMP 1700000000123000;
~~~

`1700000000123000` là **microseconds**, không phải milliseconds. Giá trị `observed_at` vẫn là CQL `timestamp` và lưu thời điểm theo milliseconds; `USING TIMESTAMP` chỉ định write timestamp cho những cell được mutation ghi.

Trong ví dụ, hai giá trị cùng đại diện một thời điểm để dễ so sánh. Trong production, chúng **không bắt buộc** giống nhau: một event từ thiết bị có thể xảy ra lúc T0 nhưng được hệ thống ghi lúc T0+10 phút; hay replay event cũ vào ngày hôm nay nhưng bảo tồn write timestamp gốc có chủ ý.

### 4.2. CQL UPDATE và DELETE cũng có timestamp cho mutation

~~~sql
UPDATE timestamp_lab
USING TIMESTAMP 1700000001123000
SET state = 'PAID', revision = 2
WHERE id = 33333333-3333-4333-8333-333333333333;
~~~

Cột `state` và `revision` được cập nhật với write timestamp được chỉ định. Nếu dùng cùng primary key ở một câu lệnh sau nhưng timestamp **nhỏ hơn**, việc gọi lệnh đó muộn hơn theo đồng hồ client không bảo đảm cell mới sẽ thắng.

Với DELETE, Cassandra cần dấu xóa (tombstone) có timestamp để quyết định không khôi phục lại dữ liệu cũ từ replicas. Timestamp của tombstone là yếu tố thiết yếu trong conflict resolution; không nên đổi tùy tiện trong lúc cleanup hoặc replay.

### 4.3. Không phải điều khiển riêng cùng một write timestamp bằng giá trị cột

Đây là cách hiểu sai:

~~~sql
-- Đây chỉ là cập nhật giá trị nghiệp vụ của updated_at,
-- KHÔNG tự đặt write timestamp của cột state bằng giá trị ấy.
UPDATE timestamp_lab
SET observed_at = '2023-11-14T22:13:20.123Z',
    state = 'PAID'
WHERE id = 33333333-3333-4333-8333-333333333333;
~~~

Giá trị `observed_at` có thể rất cũ, trong khi Cassandra vẫn gán write timestamp từ cơ chế hiện tại. Kết quả trả về có thể chứa **một giá trị thời gian nghiệp vụ năm 2023 và write timestamp năm 2026** — hoàn toàn bình thường khi hệ thống ingest dữ liệu lịch sử.

Ngược lại, câu `USING TIMESTAMP` không tự thay đổi nội dung `observed_at` nếu cột đó không được ghi trong mutation.

### 4.4. Write timestamp áp dụng theo cell, không mặc định là row version

~~~text
Mutation A (µs = 1_700_000_000_000_000)
  state = 'CREATED'
  revision = 1

Mutation B (µs = 1_700_000_000_500_000)
  state = 'PAID'

Mutation C (µs = 1_700_000_000_800_000)
  revision = 3
~~~

Một row khi đọc có thể hiển thị `state='PAID'` và `revision=3`, vì hai giá trị có write timestamp thắng ở **hai cell khác nhau**. Cassandra không tự kiểm tra hai field có cùng business revision hoặc có được ghi trong một transaction toàn row không.

Điều này đặc biệt quan trọng khi có hai worker thực hiện **partial updates**, hoặc khi repository save entity đầy đủ vô tình ghi lại field cũ.

## 5. WRITETIME(column) trả metadata microseconds

CQL cho phép quan sát write timestamp của một cell bằng hàm `WRITETIME` (trong phạm vi kiểu cột/phiên bản được hỗ trợ):

~~~sql
SELECT
    id,
    observed_at,
    state,
    WRITETIME(state) AS state_write_us,
    WRITETIME(observed_at) AS observed_write_us
FROM timestamp_lab
WHERE id = 33333333-3333-4333-8333-333333333333;
~~~

Chú ý ba kết quả:

1. `observed_at` trả một giá trị CQL `timestamp`, tức **thời điểm nghiệp vụ tính bằng ms**.
2. `state_write_us` trả write timestamp của cell `state`, tức **epoch microseconds**.
3. `observed_write_us` trả write timestamp của cell `observed_at`; không bắt buộc bằng `state_write_us` nếu hai cell được ghi ở các mutation khác nhau.

### 5.1. Không dùng WRITETIME cho primary key như với cột thường

Ví dụ `WRITETIME(state)` là một phép kiểm tra hợp lý vì `state` là cột dữ liệu thường. `WRITETIME` có giới hạn với primary key và một số loại cột/collection/counter tùy phiên bản; không giả định mọi expression đều có write timestamp có thể đọc theo cùng cú pháp.

Nếu row không có giá trị ở cell được chọn hoặc cell bị xóa, kết quả `WRITETIME` có thể là `null` trong các trường hợp phù hợp. Khi đọc bằng Java Driver, kiểm tra `row.isNull("state_write_us")` trước khi gọi `getLong`.

### 5.2. Java Driver đọc hai loại timestamp khác nhau

~~~java
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;

Row row = session.execute(
    "SELECT observed_at, state, " +
    "WRITETIME(state) AS state_write_us " +
    "FROM timestamp_lab " +
    "WHERE id = 33333333-3333-4333-8333-333333333333"
).one();

if (row != null) {
    Instant observed = row.getInstant("observed_at");

    if (!row.isNull("state_write_us")) {
        long writeMicros = row.getLong("state_write_us");
        Instant writeInstant = TimestampUnits.epochMicrosToInstant(writeMicros);

        System.out.println("Business time: " + observed);
        System.out.println("Cell write time: " + writeInstant);
    }
}
~~~

`epochMicrosToInstant` là helper tự định nghĩa ở phần 7, không phải method có sẵn của Java Driver. Việc đổi µs sang `Instant` chỉ để hiển thị/so sánh, không khiến Cassandra tự thay đổi write metadata.

### 5.3. Một bẫy khi debug

Kỹ sư có thể thấy:

~~~text
observed_at:     2023-11-14T22:13:20.123Z
state_write_us:  1795580000123456
~~~

và cho rằng “Cassandra ghi sai thời gian” vì hai thời điểm không khớp. Nhưng `observed_at` là **data**, còn `state_write_us` là **metadata ghi**. Nếu row được replay nhiều năm sau, chênh lệch là mong đợi.

Muốn so sánh, hãy đổi `state_write_us` thành ISO-8601 bằng helper đúng đơn vị; không đưa số 16 chữ số đó vào formatter mong nhận epoch milliseconds.

## 6. Last-write-wins và nguy cơ dùng sai đơn vị

Cassandra thường giải quyết các mutation cạnh tranh trên cùng cell bằng **write timestamp**. Với hai mutation có timestamp khác nhau, timestamp cao hơn thường thắng. Đây là **last-write-wins theo write timestamp**, không phải “response nào về sau” hoặc “revision nghiệp vụ cao hơn”.

### 6.1. Ví dụ đơn giản

~~~text
Cell state, cùng primary key

T1 = 1_700_000_000_123_000 µs: state = 'PAID'
T2 = 1_700_000_000_124_000 µs: state = 'CANCELLED'

T2 > T1 nên giá trị của mutation T2 có thể thắng.
~~~

Nếu request tạo ra T2 gửi **trước** request T1 nhưng phản hồi về **sau**, thứ tự phản hồi không thay đổi quy tắc so sánh timestamp.

### 6.2. Lỗi milliseconds đưa vào USING TIMESTAMP

Giả sử cell đang có write timestamp:

~~~text
state = 'PAID'
writetime(state) = 1_700_000_000_123_000 µs
~~~

Ứng dụng chạy:

~~~sql
-- SAI ĐƠN VỊ: giá trị này là milliseconds, không phải microseconds.
UPDATE timestamp_lab
USING TIMESTAMP 1700000000123
SET state = 'CANCELLED'
WHERE id = 33333333-3333-4333-8333-333333333333;
~~~

Giá trị 13 chữ số nhỏ hơn timestamp hiện có 16 chữ số tới hàng nghìn lần. Mutation `CANCELLED` có thể **không thắng** cell `PAID`, dù câu lệnh trả thành công theo đường CQL thông thường.

Một bài test chỉ kiểm tra “execute không ném exception” sẽ bỏ qua bug. Phải **đọc lại dữ liệu và WRITETIME** trên row fixture có timestamp đã biết để xác minh.

### 6.3. Lỗi nanoseconds đưa vào microseconds

Một lỗi khác:

~~~java
Instant now = Instant.now();

// SAI: đây gần với epoch nanoseconds, không phải epoch microseconds.
// Giá trị có thể cực lớn, gây future write timestamp.
long wrong = now.getEpochSecond() * 1_000_000_000L + now.getNano();
~~~

Nếu gửi `wrong` vào `USING TIMESTAMP`, Cassandra sẽ xem nanoseconds như microseconds, làm write timestamp lớn hơn thời gian hiện tại khoảng 1.000 lần. Mutation có thể **lấn át** những update bình thường trong thời gian dài.

Vì vậy, nếu phát hiện cell có write timestamp vô lý trong tương lai:

1. Tạm dừng writer gây lỗi.
2. Xác minh đơn vị tại ingress, mapper, prepared statement và config timestamp generator.
3. Đọc `WRITETIME` để xác định cell/partition chịu ảnh hưởng.
4. Lập kế hoạch sửa có kiểm soát theo Cassandra version, tombstone/TTL và cơ chế conflict resolution; đừng chỉ `UPDATE` hiện tại rồi kỳ vọng chắc chắn thắng timestamp tương lai.
5. Thử quy trình sửa trên staging và theo dõi replication/repair/compaction.
6. Ngăn tái phát bằng contract đơn vị rõ ràng, validation và test.

### 6.4. Timestamp trùng nhau cũng không phải “thứ tự request”

Khi hai mutation có cùng write timestamp, Cassandra có các quy tắc hòa giải quyết định (tie-breaking), bao gồm xử lý tombstone và giá trị cell theo semantics cụ thể. **Không dựa vào việc hai timestamp bằng nhau để diễn đạt ordering nghiệp vụ.**

Nếu hai lệnh khác giá trị ghi cùng microsecond, business không nên mặc định “lệnh chạy sau” thắng. Chọn đúng cơ chế đồng thuận/CAS hoặc một writer tuần tự theo khóa nếu cần thứ tự nghiệp vụ chặt.

## 7. Chuyển đổi an toàn giữa Instant, milliseconds và microseconds

### 7.1. Instant → epoch milliseconds

~~~java
import java.time.Instant;

Instant instant = Instant.parse("2023-11-14T22:13:20.123Z");
long millis = instant.toEpochMilli();

// millis = 1700000000123L
~~~

`Instant.toEpochMilli()` trả số nguyên long. Nếu Instant có độ chính xác dưới milliseconds, phần đó không còn trong kết quả. Với các thời điểm quá xa nằm ngoài miền long milliseconds, API có thể báo lỗi; đừng nuốt overflow rồi dùng dữ liệu sai.

### 7.2. Instant → epoch microseconds, không đi qua milliseconds

Khi nguồn `Instant` có phần microsecond cần bảo toàn:

~~~java
import java.time.Instant;

public final class TimestampUnits {

    private TimestampUnits() {
    }

    public static long toEpochMicros(Instant instant) {
        long secondsPart = Math.multiplyExact(
            instant.getEpochSecond(), 1_000_000L);

        long microsWithinSecond = instant.getNano() / 1_000L;

        return Math.addExact(secondsPart, microsWithinSecond);
    }
}
~~~

Giải thích:

- `getEpochSecond()` là **giây nguyên** từ epoch.
- `getNano()` là **nanoseconds trong giây hiện tại**, thuộc khoảng `0..999_999_999`.
- Chia `1_000` chuyển nanoseconds thành microseconds trong giây.
- `Math.multiplyExact` / `Math.addExact` giúp không âm thầm tràn `long`.
- Phần nhỏ hơn microsecond bị bỏ, vì write timestamp cần đơn vị µs.

**Không viết:** `instant.getEpochSecond() * 1_000_000 + instant.getNano()`; vì vế sau vẫn là nanoseconds, dẫn đến đơn vị trộn lẫn.

### 7.3. Epoch microseconds → Instant

Thêm phương thức sau vào lớp `TimestampUnits` ở mục 7.2:

~~~java
import java.time.Instant;

public static Instant epochMicrosToInstant(long micros) {
    long seconds = Math.floorDiv(micros, 1_000_000L);
    long microsRemainder = Math.floorMod(micros, 1_000_000L);

    return Instant.ofEpochSecond(
        seconds,
        microsRemainder * 1_000L
    );
}
~~~

Dùng `floorDiv`/`floorMod` để xử lý thời điểm trước epoch đúng toán học:

~~~text
micros = -1

seconds = -1
remainderMicros = 999_999

Instant = 1969-12-31T23:59:59.999999Z
~~~

Nếu dùng `micros / 1_000_000` và `micros % 1_000_000` rồi đặt thiếu xử lý số âm, có thể gây bug ở boundary.

### 7.4. Milliseconds → microseconds

~~~java
long epochMillis = 1_700_000_000_123L;
long epochMicros = Math.multiplyExact(epochMillis, 1_000L);

// 1_700_000_000_123_000 µs
~~~

Lưu ý **không khôi phục được** microseconds đã mất trước đó nếu ban đầu chỉ có milliseconds. `millis * 1000` chỉ tạo mốc microseconds **là bội của 1.000**.

### 7.5. Microseconds → milliseconds có mất phần lẻ

~~~java
long epochMicros = 1_700_000_000_123_456L;
long epochMillis = Math.floorDiv(epochMicros, 1_000L);

// 1_700_000_000_123 ms
~~~

Giá trị `456µs` dư bị mất trong milliseconds. Đối với application analytics, điều này có thể chấp nhận; nhưng nếu so sánh write timestamp để xác định thứ tự mutation xảy ra trong cùng một millisecond thì **không** được chỉ giữ milliseconds.

### 7.6. Kiểm tra bằng bất biến

Với một thời điểm `Instant` có chính xác microseconds:

~~~java
Instant original = Instant.parse("2023-11-14T22:13:20.123456Z");

long us = TimestampUnits.toEpochMicros(original);
Instant roundTrip = TimestampUnits.epochMicrosToInstant(us);

if (!roundTrip.equals(original)) {
    throw new IllegalStateException("Time conversion mismatch");
}
~~~

Nếu nguồn có nanoseconds không chia hết cho 1.000, round-trip sang microseconds không thể giữ các nanoseconds dư; test phải so sánh tới **microsecond**, không đòi exact equality ngoài độ phân giải.

## 8. Dùng prepared statement để truyền write timestamp đúng kiểu

CQL `USING TIMESTAMP` nhận giá trị integer microseconds; có thể dùng bind marker:

~~~java
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class ExplicitTimestampWriter {

    private final CqlSession session;
    private final PreparedStatement setState;

    public ExplicitTimestampWriter(CqlSession session) {
        this.session = session;

        this.setState = session.prepare(
            "UPDATE timestamp_lab " +
            "USING TIMESTAMP ? " +
            "SET state = ? " +
            "WHERE id = ?"
        );
    }

    public void update(
            UUID id,
            String state,
            Instant writeInstant) {

        long micros = TimestampUnits.toEpochMicros(writeInstant);

        BoundStatement bound = setState.bind(micros, state, id);
        session.execute(bound);
    }
}
~~~

Ở đây, `writeInstant` là **quyết định về write timestamp**, không chỉ là metadata display. Method này chỉ nên được cung cấp cho đường ingest/replay được kiểm soát, chứ không cho phép HTTP client tùy ý gửi timestamp trong quá khứ/tương lai để ghi đè trạng thái người khác.

Nếu không có yêu cầu đặc biệt, **đừng tự đặt `USING TIMESTAMP`**. Dùng timestamp generator/defaults của driver/server phù hợp với kiến trúc, để giảm nguy cơ sinh write timestamp sai do ứng dụng.

### 8.1. Không truyền chuỗi ISO vào USING TIMESTAMP

~~~sql
-- Sai ý tưởng: USING TIMESTAMP cần epoch microseconds,
-- không phải một CQL timestamp literal có timezone.
UPDATE timestamp_lab
USING TIMESTAMP '2023-11-14T22:13:20.123Z'
SET state = 'PAID'
WHERE id = 33333333-3333-4333-8333-333333333333;
~~~

Muốn chỉ định thời điểm viết bằng ISO-8601, parse thành `Instant` và **chuyển sang epoch microseconds**, hoặc dùng cơ chế client-side timestamp được cấu hình rõ. Không lẫn cú pháp `USING TIMESTAMP` với giá trị của cột CQL `timestamp`.

### 8.2. Biến `long` phải mang đơn vị trong tên và contract

~~~java
// Không tốt:
void save(UUID id, String state, long timestamp);

// Tốt hơn:
void saveWithWriteTimestampMicros(
    UUID id, String state, long writeTimestampMicros);
~~~

Khi sử dụng nhiều lớp HTTP → Service → Repository → Driver, sai lầm đơn vị có thể đi qua các interface mà compiler không phát hiện vì cả milliseconds và microseconds đều là `long`.

Một hướng phòng lỗi mạnh hơn là kiểu wrapper:

~~~java
public record EpochMicros(long value) {
    public static EpochMicros from(Instant instant) {
        return new EpochMicros(TimestampUnits.toEpochMicros(instant));
    }
}

public record EpochMillis(long value) {
    public static EpochMillis from(Instant instant) {
        return new EpochMillis(instant.toEpochMilli());
    }
}
~~~

Lớp adapter chuyển `EpochMicros.value()` sang `USING TIMESTAMP`, trong khi DTO API chỉ dùng `EpochMillis` nếu hợp đồng API thực sự gửi milliseconds. Việc dùng wrapper làm sai lầm “truyền micro vào chỗ milli” dễ bị kiểm tra kiểu hơn.

## 9. Spring Data Cassandra: entity timestamp không phải write timestamp

Spring Data Cassandra giúp chuyển đổi giữa Java entity và CQL row qua metadata mapping. Ví dụ:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderById {

    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("created_at")
    private Instant createdAt;

    @Column("updated_at")
    private Instant updatedAt;

    @Column("status")
    private String status;

    @Column("revision")
    private Long revision;

    public OrderById() {
    }

    // Constructor, getters và setters...
}
~~~

CQL:

~~~sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    created_at timestamp,
    updated_at timestamp,
    status text,
    revision bigint
);
~~~

`createdAt` và `updatedAt` là **property nghiệp vụ** của Java entity. Khi chúng được ghi vào các cột `timestamp`, độ phân giải lưu trữ của Cassandra là milliseconds. Chúng **không tự quyết định** write timestamp mà Cassandra dùng cho một `INSERT` hoặc `UPDATE`.

### 9.1. Repository.save không phải optimistic locking bằng thời gian

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderByIdRepository
        extends CassandraRepository<OrderById, UUID> {
}
~~~

Service:

~~~java
OrderById order = repository.findById(orderId).orElseThrow();
order.setUpdatedAt(Instant.now());
order.setStatus("PAID");

repository.save(order);
~~~

Đoạn mã này thể hiện thao tác lưu entity, **không** tự chứng minh rằng:

- Cassandra chỉ cập nhật `updated_at` và `status`.
- Giá trị `updated_at` chắc chắn bằng write timestamp của cell `status`.
- Không có client khác đã cập nhật row trong khoảng giữa `findById` và `save`.
- Nếu `updatedAt` mới hơn, mutation chắc chắn thắng theo thứ tự nghiệp vụ.
- Row được khóa như một managed entity của JPA.

Spring Data Cassandra không có persistence context/dirty checking kiểu Hibernate. CQL mutation vô điều kiện thường có ngữ nghĩa **upsert** và xung đột được quyết định theo write timestamp cấp cell. Nếu cần logic chỉ chấp nhận revision cao hơn, phải có cơ chế kiểm tra thực sự.

### 9.2. Auditing timestamp phục vụ việc gì?

Spring Data Cassandra có hỗ trợ auditing như `@CreatedDate`, `@LastModifiedDate` khi được cấu hình phù hợp. Ví dụ khái niệm:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;

@CreatedDate
@Column("created_at")
private Instant createdAt;

@LastModifiedDate
@Column("updated_at")
private Instant updatedAt;
~~~

Auditing có thể giúp ghi thời điểm tạo/cập nhật **ở cấp entity**, nhưng:

1. Nó phải được bật/cấu hình theo Spring Data version.
2. Kiểu cột `timestamp` vẫn lưu milliseconds.
3. Giá trị auditing không tự là metadata `WRITETIME`.
4. Một request ghi từ cqlsh, Java Driver thuần hoặc service khác có thể bỏ qua auditing Spring Data.
5. Auditing không thay thế LWT, versioning hay phân quyền khi có nhiều writer.

Không lấy `updated_at` làm bằng chứng chắc chắn về mutation đã thắng ở replica nếu có nhiều đường ghi.

### 9.3. CassandraTemplate với UPDATE chỉ một cột

Nếu chỉ muốn thay `status`, một adapter có thể sử dụng CQL tường minh thay vì tạo entity chỉ gồm ID + status rồi gọi `save`:

~~~java
PreparedStatement prepared = session.prepare(
    "UPDATE orders_by_id SET status = ? WHERE order_id = ?"
);

session.execute(prepared.bind("PAID", orderId));
~~~

Giữ phạm vi mutation nhỏ giúp tránh vô tình ghi lại `created_at` hoặc `revision` cũ. Dù vậy, lệnh trên vẫn là upsert **không có điều kiện**. Khi nghiệp vụ cần chuyển từ `CREATED` sang `PAID`, dùng CAS/LWT hoặc điều phối writer đúng yêu cầu.

### 9.4. Không dùng Instant làm cột sắp xếp toàn cụm nếu truy vấn không hỗ trợ

Ví dụ bảng `orders_by_id` với `order_id` là partition key không tự hỗ trợ:

~~~sql
-- Không phải truy vấn hiệu quả chỉ vì có updated_at timestamp:
SELECT * FROM orders_by_id
ORDER BY updated_at DESC;
~~~

Để hiển thị đơn mới nhất theo khách hàng, cần bảng theo truy vấn như `orders_by_customer_month` có partition key `(customer_id, month_bucket)` và clustering columns theo thời gian. Cassandra không biến `updated_at` thành global index/sort chỉ vì property đó là `Instant`.

## 10. Đồng hồ hệ thống, NTP và timestamp generator

### 10.1. “Giờ hiện tại” của ai?

Trong môi trường phân tán, một mutation có thể được gửi bởi:

- API service A chạy ở pod 1.
- Worker B chạy ở máy khác.
- Job replay sự kiện lịch sử.
- Công cụ quản trị gửi CQL.
- Ứng dụng chạy ở data center khác.

Mỗi client hoặc node có thể có đồng hồ lệch nhau, đặc biệt khi NTP chưa đồng bộ, máy ảo bị pause, hay container host có vấn đề.

~~~mermaid
sequenceDiagram
    participant A as Writer A (clock nhanh)
    participant B as Writer B (clock chậm)
    participant C as Cassandra

    A->>C: state=PAID, writeTs=1005000µs
    B->>C: state=SHIPPED, writeTs=1001000µs
    Note over C: PAID có timestamp lớn hơn dù SHIPPED gửi sau
    C-->>B: Mutation accepted
~~~

Khi đọc, `state` có thể vẫn là `PAID` vì write timestamp của mutation `SHIPPED` thấp hơn. Cassandra không biết `SHIPPED` là trạng thái tiếp theo trong workflow.

### 10.2. Client-side timestamp generation

Java Driver có khả năng tạo timestamp request theo cấu hình, có thể dùng timestamp generator nhằm tránh trùng/đi lùi timestamp trên **cùng một tiến trình**. Nhưng ngay cả một generator monotonic trên một client cũng **không** chứng minh monotonic toàn hệ thống với nhiều writer, restart, nhiều DC hoặc lỗi đồng hồ.

Với Cassandra, đồng bộ đồng hồ hệ thống chính xác vẫn rất quan trọng. Cần:

- Đồng bộ NTP/chrony giữa các node và máy chạy client phù hợp hạ tầng.
- Giám sát clock offset, step/time adjustment và sự cố đồng hồ.
- Tránh nhiều writer tự đặt timestamp khác quy ước.
- Xác định chính sách thứ tự nghiệp vụ độc lập đồng hồ khi thực sự cần.
- Chú ý rằng `System.nanoTime()` đo thời gian trôi qua chứ không có epoch; **không** dùng nó cho `USING TIMESTAMP`.

### 10.3. LWW không phải newest event wins

Một event sinh lúc T0 nhưng đến service sau hai phút có thể được ghi với write timestamp **T0+2 phút** nếu sử dụng timestamp hiện tại. Nếu event này là bản cũ, nó vẫn có thể thắng giá trị mới của cùng cell.

Ngược lại, nếu replay với timestamp gốc T0, event cũ có thể thua những mutation mới hơn — nhưng không nên chỉ dựa vào timestamp gốc như một giải pháp ordering tổng quát khi nguồn có clock skew hoặc nhiều thiết bị cùng viết.

Mô hình đúng nên phân biệt:

- `eventTime`: thiết bị/nguồn ghi nhận sự kiện xảy ra lúc nào.
- `ingestTime`: service nhận sự kiện lúc nào.
- `writeTimestampMicros`: Cassandra dùng khi hòa giải.
- `revision` hoặc `sequenceNumber`: thứ tự nghiệp vụ do nguồn có trách nhiệm sinh.
- `processedAt`: thời điểm worker thực thi; không nhất thiết là event time.

Nếu có nhiều nguồn, cần thỏa thuận **nguồn nào có quyền quyết định thứ tự** và cách xử lý sự kiện trễ.

## 11. TTL, tombstone và nguy cơ timestamp tương lai

### 11.1. TTL có đơn vị giây, không phải microseconds

Cassandra hỗ trợ `TTL` cho dữ liệu có thời gian sống:

~~~sql
INSERT INTO draft_orders_by_id (
    draft_id, status
)
VALUES (
    44444444-4444-4444-8444-444444444444,
    'DRAFT'
)
USING TTL 3600;
~~~

Giả định bảng `draft_orders_by_id` đã có cột `draft_id` primary key và `status text`. `3600` là **giây**, tức một giờ. Đừng dùng `3_600_000` vì đó là milliseconds của một giờ; nếu được chấp nhận theo giới hạn version, dữ liệu sẽ sống lâu hơn dự định rất nhiều.

| CQL/API | Đơn vị | Ví dụ |
| --- | --- | --- |
| `USING TTL 3600` | Giây | Hết hạn theo thời gian sống một giờ |
| `TTL(status)` | Giây còn lại | Không phải thời gian tuyệt đối từ epoch |
| `USING TIMESTAMP 1700000000123000` | Epoch microseconds | Metadata write conflict |
| `WRITETIME(status)` | Epoch microseconds | Metadata ghi cell |
| `created_at timestamp` | Epoch milliseconds | Giá trị một thời điểm |

Có thể kết hợp `TTL` và write timestamp ở những câu CQL hỗ trợ, nhưng đó là **hai chính sách khác nhau**. TTL/hạn hết phụ thuộc cơ chế xử lý của Cassandra và thời điểm ghi thực tế; không được suy “USING TIMESTAMP cũ” luôn làm TTL hết hạn từ năm cũ theo cách bạn tưởng.

### 11.2. Retry có thể làm mới hạn sống

Giả sử API ghi `USING TTL 3600` lúc 10:00, phản hồi mất, rồi retry lúc 10:01. Lần ghi thứ hai nếu được áp dụng có thể làm mới thời điểm hết hạn cho các cell được ghi. Cùng giá trị cuối **không** đồng nghĩa cùng lifecycle.

Nếu yêu cầu “hết hạn đúng một giờ sau thời điểm tạo ban đầu”:

1. Lưu `expiresAt` nghiệp vụ hoặc trạng thái tạo lần đầu.
2. Xử lý retry theo idempotency key.
3. Tính TTL còn lại nếu dùng Cassandra TTL; nhớ đơn vị **giây** và giới hạn hợp lệ.
4. Đọc/đối soát trạng thái khi kết quả timeout không rõ.
5. Đừng chỉ đánh dấu statement là idempotent vì payload giống nhau.

### 11.3. Tombstone cũng có write timestamp

Khi bạn xóa cell/row, Cassandra cần ghi nhận dấu xóa để replica không phục hồi lại dữ liệu cũ.

~~~sql
DELETE state FROM timestamp_lab
WHERE id = 33333333-3333-4333-8333-333333333333;
~~~

Nếu tombstone có timestamp thắng cell cũ, dữ liệu cũ bị che. Nếu sau đó bạn cố ghi lại với write timestamp **nhỏ hơn tombstone**, ghi mới có thể không xuất hiện.

Nếu một mutation vô tình dùng timestamp rất xa tương lai, cả update và delete về sau có thể bị chi phối. Việc cleanup phải hiểu timestamp của dữ liệu/tombstone, `gc_grace_seconds`, repair, compaction và khả năng zombie data; **không** xóa rồi viết lại bừa trong production.

### 11.4. Đừng tự dùng timestamp khổng lồ để ép ghi thắng

Một giải pháp sai khi thấy update không áp dụng như mong đợi:

~~~text
"Gửi USING TIMESTAMP 999999999999999999 là chắc chắn thắng!"
~~~

Đây là cách tạo một **future timestamp** có thể tiếp tục áp đảo các mutation hợp lệ. Nó làm dữ liệu khó sửa hơn, tăng nguy cơ mâu thuẫn khi delete/TTL/repair và không tạo optimistic locking.

Cần tìm nguyên nhân: sai đơn vị, clock skew, concurrent writers, LWT thất bại, replay event cũ, hoặc mapper chuyển sai kiểu. Chỉ sửa timestamp khi có runbook được kiểm chứng theo version và phạm vi dữ liệu bị ảnh hưởng.

## 12. LWT/CAS: khi thứ tự nghiệp vụ quan trọng hơn đồng hồ

Nếu dịch vụ cần luật:

~~~text
CREATED -> PAID -> SHIPPED -> COMPLETED
         \-> CANCELLED (khi được phép)
~~~

thì write timestamp không tự biết trạng thái nào hợp lệ. Dùng mutation có điều kiện:

~~~sql
UPDATE orders_by_id
SET status = 'PAID', revision = 2
WHERE order_id = ?
IF status = 'CREATED' AND revision = 1;
~~~

Cassandra dùng **lightweight transaction (LWT)** để kiểm tra điều kiện và áp dụng mutation trong phạm vi hỗ trợ.

Ví dụ driver:

~~~java
PreparedStatement payIfCreated = session.prepare(
    "UPDATE orders_by_id " +
    "SET status = 'PAID', revision = 2 " +
    "WHERE order_id = ? " +
    "IF status = 'CREATED' AND revision = 1"
);

boolean applied = session.execute(
    payIfCreated.bind(orderId)
).wasApplied();

if (!applied) {
    // Phân biệt đã PAID, đã CANCELLED, chưa tồn tại,
    // hoặc một request khác vừa thay đổi state.
}
~~~

Lưu ý:

- `[applied] = false` là kết quả điều kiện không thỏa, không phải luôn là lỗi hạ tầng.
- Timeout LWT có thể khiến kết quả áp dụng **không rõ** với client; cần xác minh.
- LWT có chi phí độ trễ/đồng thuận cao hơn write thông thường.
- Consistency thông thường và **serial consistency** (`SERIAL`/`LOCAL_SERIAL`) là hai thiết lập riêng.
- Một CAS trên row không tự cung cấp giao dịch ACID end-to-end cho email, message broker, kho hàng và các bảng read model khác.

**Đặc biệt:** Đừng thiết kế kết hợp tùy tiện `USING TIMESTAMP` với conditional mutation. Cassandra hạn chế/không hỗ trợ custom timestamp trên các câu lệnh điều kiện LWT ở những phiên bản phổ biến, do yêu cầu tính đúng đắn của giao thức đồng thuận. Khi cần CAS, dùng đúng semantics LWT và không cố “ép thắng” bằng timestamp do client tự đặt.

### 12.1. Revision không có sức mạnh nếu chỉ là một field

~~~sql
-- Không có IF: revision lớn hơn không tự được ưu tiên.
UPDATE orders_by_id
SET status = 'CREATED', revision = 7
WHERE order_id = ?;
~~~

Nếu một writer vừa lưu `revision=8` nhưng mutation `revision=7` về sau nhận write timestamp thắng, Cassandra vẫn có thể đọc ra revision 7. Muốn CAS, phải **so sánh revision trong điều kiện** hoặc đảm bảo thứ tự ghi qua cơ chế khác.

## 13. Retry, idempotency và write timestamp

### 13.1. Timeouts có kết quả không rõ

~~~mermaid
sequenceDiagram
    participant API
    participant Driver
    participant Cassandra
    API->>Driver: UPDATE state = PAID
    Driver->>Cassandra: Mutation
    Cassandra->>Cassandra: Đã ghi cell với write timestamp
    Cassandra--xDriver: Response thất lạc
    Driver-->>API: Timeout
    Note over API,Cassandra: Không chắc ghi có được áp dụng chưa
    API->>Driver: Retry?
~~~

Một lệnh retry có thể:

- Được gán write timestamp khác mutation đầu.
- Tương tác với một writer khác ghi cùng cell trong khoảng đó.
- Làm TTL mới hơn nếu có TTL.
- Với counter hoặc list append, tạo side effect lần nữa.
- Với LWT, trả kết quả điều kiện khác với lần đầu.

Không mặc định “retry cùng CQL” có nghĩa không có side effect. Cần phân loại loại mutation và thiết kế idempotency ở tầng nghiệp vụ.

### 13.2. Idempotency của driver không tự tạo ordering

Java Driver 4.x có `setIdempotent(true/false)` cho statement, ảnh hưởng việc statement có đủ điều kiện retry/speculative execution theo policy hay không. Đánh dấu `true` **không** khiến Cassandra tự so sánh revision hay sửa đồng hồ.

~~~java
BoundStatement read = preparedSelect
    .bind(orderId)
    .setIdempotent(true);

// Một câu SELECT thuần không tạo mutation,
// nên thường phù hợp để retry theo policy.
~~~

Counter increment và append list thường **không lũy đẳng**. Upsert cùng giá trị scalar có thể có kết quả cuối giống nhau trong môi trường không có writer cạnh tranh, nhưng cần xét write timestamp và TTL trước khi khẳng định an toàn.

### 13.3. Khi replay event lịch sử

Có hai chiến lược cần tách rõ:

**Replay với write timestamp hiện tại:** đơn giản về hạ tầng nhưng event cũ có thể thắng state mới của cùng cell nếu không có CAS/order.

**Replay với write timestamp gốc:** có thể giữ độ ưu tiên theo thời gian nguồn, nhưng gặp clock skew, nguồn không đồng bộ và các event có thứ tự nghiệp vụ khác timestamp. Dữ liệu tombstone/TTL cũng cần cân nhắc.

Không có chiến lược tổng quát đúng cho mọi nghiệp vụ. Nếu event có `sequenceNumber` hoặc `revision` do nguồn tin cậy sinh, có thể dùng một writer tuần tự theo khóa hoặc CAS để quyết định event nào được chấp nhận. `eventTime` chỉ là một tín hiệu, không tự là global order của hệ phân tán.

## 14. Consistency level không sửa lỗi đơn vị

Cassandra hỗ trợ consistency levels như `LOCAL_ONE` và `LOCAL_QUORUM`. Với RF=3 trong một data center, local quorum thường yêu cầu 2 replica phản hồi. Nhưng điều đó **không** thay đổi cách so sánh write timestamp của cell.

Ví dụ:

~~~text
Replica có state='PAID' với writeTs=1_700_000_000_123_000 µs
Client gửi state='SHIPPED' với writeTs=1_700_000_000_123 µs

Write mới có timestamp quá cũ do nhầm ms/µs.
Tăng consistency không làm SHIPPED thắng PAID.
~~~

Consistency quyết định tập replica/thời điểm xác nhận; LWW quyết định giá trị thắng khi các mutation cạnh tranh. Để chống ghi trùng/ghi sai state, phải xử lý **tính đúng đắn ở tầng dữ liệu/nghiệp vụ**, không chỉ tăng CL.

Ngoài ra, nếu một đơn được lưu ở hai bảng `orders_by_id` và `orders_by_customer_month`, đó là **hai read model ứng dụng**. LOCAL_QUORUM không tự đồng bộ chúng; cần write path, projector, revision và đối soát theo thiết kế.

## 15. Thiết kế bảng thời gian và paging đúng

Một nhầm lẫn liên quan: dùng `timestamp` làm clustering key mà không xem xét **độ phân giải milliseconds**.

~~~sql
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC, order_id DESC
);
~~~

Tại sao thêm `order_id` sau `created_at`?

- Nhiều đơn có thể được tạo **trong cùng một millisecond**.
- Nếu chỉ dùng `created_at` làm clustering key, hai event cùng thời điểm có thể va chạm khóa và upsert vào cùng row logic.
- `order_id` tạo tie-breaker để mỗi đơn có primary key phân biệt.
- Cursor keyset cần mốc `(lastCreatedAt, lastOrderId)`, không chỉ một `createdAt`.
- Khi có nhiều partition/bucket, ứng dụng phải quản lý cursor riêng; Cassandra không có global `ORDER BY`/`OFFSET` tùy ý.

### 15.1. Đơn vị sai có thể tạo partition/bucket sai

Nếu `month_bucket` được tính bằng cách đọc nhầm microseconds như milliseconds, application có thể:

- Ném lỗi vì năm quá xa;
- Tính tháng/năm sai;
- Ghi row vào partition không phù hợp;
- Không tìm được row ở query theo tháng đúng;
- Khó cleanup vì schema key tạo địa chỉ khác.

Khi tính bucket, hãy lấy từ một `Instant` đã được xác minh:

~~~java
import java.time.Instant;
import java.time.YearMonth;
import java.time.ZoneOffset;

Instant createdAt = Instant.parse("2026-11-25T10:00:00.123Z");

String monthBucket = YearMonth.from(
    createdAt.atZone(ZoneOffset.UTC)
).toString();

// "2026-11"
~~~

Quyết định bucket theo UTC hoặc múi giờ nghiệp vụ phải được ghi thành contract và **giữ nhất quán giữa write và read**. Không tự thay timezone rồi kỳ vọng mọi partition của dữ liệu cũ tự di chuyển.

### 15.2. timeuuid không phải giải pháp tự động cho mọi độ chính xác

`timeuuid` chứa thành phần thời gian với độ phân giải/format của UUID version 1. Nó hữu ích cho một số mô hình event ordering, nhưng không đồng nghĩa:

- Đồng hồ của mọi writer được đồng bộ tuyệt đối.
- Một UUID luôn có business ordering đúng.
- Có thể thay `Instant` hoặc `timestamp` mà không chuyển mapping/schema.
- Có thể tạo unique ID chỉ từ `System.currentTimeMillis()` mà không xét collision.
- Một query qua nhiều partition sẽ tự sắp xếp toàn cụm.

Nếu dùng `timeuuid`, đối chiếu khả năng Java Driver/Spring Data mapping và cách sinh ID. Với cột `time`, đơn vị nanoseconds là **nanoseconds trong ngày**, không phải epoch nanoseconds; không dùng kiểu này để lưu write timestamp.

## 16. Kiểm thử chuyển đổi đơn vị bằng Java

Đây là bộ test minh họa dùng JUnit 5. Các phương thức `TimestampUnits.toEpochMicros` và `TimestampUnits.epochMicrosToInstant` là helpers đã định nghĩa ở phần 7.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class TimestampUnitsTest {

    @Test
    void epochMillisAndMicrosDifferByOneThousand() {
        Instant instant = Instant.parse(
            "2023-11-14T22:13:20.123Z");

        long millis = instant.toEpochMilli();
        long micros = TimestampUnits.toEpochMicros(instant);

        assertEquals(1_700_000_000_123L, millis);
        assertEquals(1_700_000_000_123_000L, micros);
        assertEquals(millis * 1_000L, micros);
    }

    @Test
    void retainsMicrosecondsButNotSubMicroNanos() {
        Instant value = Instant.parse(
            "2023-11-14T22:13:20.123456789Z");

        long micros = TimestampUnits.toEpochMicros(value);

        assertEquals(1_700_000_000_123_456L, micros);
        assertEquals(
            Instant.parse("2023-11-14T22:13:20.123456Z"),
            TimestampUnits.epochMicrosToInstant(micros)
        );
    }

    @Test
    void handlesOneMicrosecondBeforeEpoch() {
        Instant value =
            TimestampUnits.epochMicrosToInstant(-1L);

        assertEquals(
            Instant.parse("1969-12-31T23:59:59.999999Z"),
            value
        );
    }

    @Test
    void detectsLongOverflowForFarFuture() {
        Instant tooFar = Instant.ofEpochSecond(
            Long.MAX_VALUE / 1_000_000L + 1L
        );

        assertThrows(
            ArithmeticException.class,
            () -> TimestampUnits.toEpochMicros(tooFar)
        );
    }
}
~~~

**Điểm kiểm tra:** method `toEpochMicros` cố ý dùng `Math.multiplyExact`; test overflow giúp phát hiện sự cố thay vì để số `long` bị wrap thành âm và âm thầm tạo write timestamp quá cũ.

### 16.1. Test sự khác nhau của CQL timestamp và write timestamp

Bài test tích hợp trên Cassandra staging/Testcontainers (nếu dự án đã có hạ tầng test) có thể:

1. Tạo bảng `timestamp_lab` trong keyspace test.
2. Insert row mới với `observed_at` bằng một ISO time cố định, và `USING TIMESTAMP` bằng microseconds tương ứng.
3. Query `observed_at` và `WRITETIME(state)`.
4. Khẳng định `observed_at` được đọc thành `Instant` chính xác tới milliseconds.
5. Khẳng định `WRITETIME(state)` bằng giá trị microseconds đã gán.
6. Ghi cùng cell với write timestamp **thấp hơn** và xác minh nó không thắng.
7. Ghi cùng cell với write timestamp **cao hơn** và xác minh giá trị thắng.
8. Kiểm tra row khác/ID khác không chịu ảnh hưởng.
9. Dọn dữ liệu fixture trong môi trường test, không thử trên row production.

Cần dùng **ID mới và timestamp được kiểm soát** trong test để tránh dữ liệu cũ/tombstone có timestamp cao làm kết quả sai. Không lấy `Instant.now()` cho mọi assertion cố định vì test có thể chập chờn do clock skew hoặc thời gian thực thi.

### 16.2. Test boundary và hợp đồng API

Thêm các ca:

| Input | Điều cần xác minh |
| --- | --- |
| Epoch seconds 10 chữ số | Không vô tình dùng làm milliseconds |
| Epoch millis 13 chữ số | Cột CQL timestamp nhận đúng thời điểm |
| Epoch micros 16 chữ số | USING TIMESTAMP và WRITETIME đúng |
| Epoch nanos 19 chữ số | Không đưa trực tiếp vào microseconds |
| `Instant` có nanoseconds lẻ | Phần dưới micro/milli bị mất theo đích chuyển |
| `Instant` trước 1970 | `floorDiv/floorMod` và thời điểm không lệch |
| Timestamp gần `Long.MAX_VALUE` | Overflow được phát hiện rõ |
| DTO timezone `+07:00` | Được quy về cùng instant UTC |
| Hai events cùng millisecond | Clustering tie-breaker vẫn phân biệt row |
| Client retry sau timeout | Không làm sai state/TTL/counter |
| Nhiều writers lệch đồng hồ | Không phụ thuộc LWW để bảo đảm business version |

Không áp dụng “kiểm tra số chữ số” như quy tắc duy nhất. Một hợp đồng tốt phải biết **đơn vị chuẩn** và parse/validate theo loại request, không suy mơ hồ từ một long.

## 17. Kiểm soát dữ liệu thời gian ở ranh giới HTTP/API

### 17.1. Cách biểu diễn an toàn

Ưu tiên RFC 3339 / ISO-8601 với offset:

~~~json
{
  "orderId": "11111111-1111-4111-8111-111111111111",
  "createdAt": "2026-11-25T10:00:00.123Z",
  "status": "CREATED"
}
~~~

Nếu giao thức bắt buộc dùng epoch number, đặt tên có đơn vị:

~~~json
{
  "createdAtEpochMillis": 1795600800123
}
~~~

Giá trị ví dụ ở trên phải được đồng bộ với thời điểm ISO thực tế khi đưa vào test; bản chất contract là **milliseconds**, không phải trường đặt tên chung `timestamp`.

### 17.2. Một contract rõ ràng

Tài liệu API nên ghi:

~~~text
createdAt:
  ISO-8601 UTC/offset, parse thành Instant.

createdAtEpochMillis:
  long epoch milliseconds, chỉ dùng nếu client không hỗ trợ ISO.

writeTimestampMicros:
  metadata nội bộ, không nhận từ client công khai.

businessRevision:
  số phiên bản nghiệp vụ, không suy từ Unix timestamp.

expiresAt:
  thời điểm hết hạn nghiệp vụ; không đồng nhất với TTL seconds.
~~~

Nếu cần nhận timestamp từ thiết bị IoT/kết nối ngoài, **không** dùng nó trực tiếp làm mutation timestamp trừ khi hệ thống thực sự muốn quyền điều khiển conflict resolution theo thời điểm thiết bị. Dữ liệu không tin cậy có thể gửi timestamp tương lai làm biến dạng state.

### 17.3. Validation dựa trên miền thời gian

Đối với `createdAt` của đơn hàng “bình thường”, có thể kiểm tra nó nằm trong khoảng hợp lý quanh thời điểm server, chẳng hạn một cửa sổ do nghiệp vụ định nghĩa. Nhưng:

- Không áp dụng cửa sổ vài phút cho dữ liệu lịch sử/backfill.
- Không sửa timestamp bị lỗi bằng cách âm thầm thay bằng `Instant.now()` nếu nguồn cần audit.
- Ghi nhận nguồn, đơn vị đầu vào, transformation và trace ID để điều tra.
- Giữ contract phiên bản cho event schema khi chuyển từ milliseconds sang microseconds.
- Xem xét người dùng ở nhiều timezone và thay đổi daylight saving time ở những khu vực có DST.

## 18. Chẩn đoán lỗi trong production

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Ngày trong UI rơi về tháng 1/1970 | Milliseconds bị hiểu là microseconds hoặc epoch seconds bị hiểu thành ms | Kiểm tra unit ở API/mapper/driver |
| Thời gian nhảy rất xa tương lai | Micro/nano bị hiểu thành milliseconds hoặc microseconds | Kiểm tra số chữ số, Instant conversion |
| UPDATE thành công nhưng state không đổi | Write timestamp mới thấp hơn cell hiện có | Query `WRITETIME(state)`, phát hiện lỗi đơn vị/clock |
| State cũ ghi đè state mới | Retry/replay với timestamp lớn hơn, writer clock lệch | Theo dõi request ID, revision, source timestamp |
| DELETE xong dữ liệu có vẻ quay lại | Tombstone/timestamp/repair hoặc writer cũ | Điều tra timestamp và lifecycle, tránh sửa bừa |
| `updated_at` mới hơn `WRITETIME` | Chúng là hai ngữ nghĩa và đơn vị khác nhau; có thể bị lưu thủ công | So sánh sau khi quy đổi đúng đơn vị |
| Query chậm do clock/time | Không nhất thiết do timestamp; có thể sai partition/bucket | Kiểm tra schema, clustering và paging |
| TTL quá dài/nhanh hết | TTL nhầm mili giây với giây hoặc retry làm mới | Kiểm tra `USING TTL` và `TTL(column)` |
| Hai events cùng thời điểm bị ghi đè | Clustering key chỉ dùng timestamp milliseconds | Thêm event ID/tie-breaker |
| Quorum vẫn trả dữ liệu nghiệp vụ cũ | LWW/clock skew hoặc read model chưa đồng bộ | Phân biệt replica CL với CAS/projection |
| `Instant` đọc lại mất nanoseconds | CQL timestamp chỉ giữ milliseconds | Xác nhận schema/type và kỳ vọng test |
| Timestamp parse sai timezone | Chuỗi thiếu offset hoặc parse `LocalDateTime` sai zone | Dùng ISO-8601 có zone, parse thành Instant |

### 18.1. Runbook điều tra một cell không cập nhật

1. Xác định **primary key** chính xác và cột bị ảnh hưởng.
2. Đọc giá trị hiện tại cùng `WRITETIME(column)` trong một query có partition key đúng.
3. Kiểm tra mutation được gửi: `USING TIMESTAMP`, driver request timestamp, nguồn dữ liệu và đơn vị.
4. So sánh số microseconds hiện tại với request định ghi.
5. Kiểm tra client clocks, NTP offset và timestamp generator.
6. Xem retry/timeouts, có writer khác cùng key và có LWT/CAS không.
7. Kiểm tra cột liên quan có TTL, tombstone hay mutation đồng thời không.
8. Nếu xử lý nhiều bảng, xác định vấn đề thuộc **cùng cell**, **các replica**, hay **read model khác**.
9. Tắt nguồn tạo timestamp sai trước khi sửa dữ liệu.
10. Chọn quy trình phục hồi trên môi trường kiểm soát, đo sau khi thực hiện.

### 18.2. Những chỉ số đáng theo dõi

- Đồng bộ đồng hồ và offset NTP/chrony của node/hosts.
- Driver request timeout, write timeout, unavailable, retry/speculative executions.
- Read/write latency p95/p99, CPU, disk I/O, compaction và pending tasks.
- Tỷ lệ CAS `[applied]=false` cho chuyển trạng thái.
- Số mutation bị phát hiện có write timestamp quá cũ/tương lai so với policy.
- Chênh lệch giữa `eventTime`, `ingestTime` và `processedAt` ở stream.
- Projection lag giữa các bảng denormalized.
- Tombstone/TTL metrics và bất thường ở partition/time bucket.

Không xuất mọi write timestamp/cursor hoặc dữ liệu nhạy cảm vào log công khai. Khi cần debug, log request ID, key đã ẩn danh hóa theo chính sách, loại đơn vị và chênh lệch hữu ích.

## 19. Bài thực hành: hệ thống đơn hàng có hai nguồn sự kiện

### 19.1. Đề bài

Ứng dụng nhận trạng thái đơn hàng từ:

- Payment service: phát event `PAID`.
- Shipping service: phát event `SHIPPED`.
- Retry queue: có thể phát lại event cũ sau timeout.

Một bảng chứa `orders_by_id(order_id, created_at timestamp, status text, revision bigint)`. Yêu cầu:

1. Không cho trạng thái quay lùi từ `SHIPPED` thành `PAID`.
2. Không nhầm `created_at` epoch millis với mutation write timestamp micros.
3. Có thể replay event và truy vấn lịch sử phục vụ audit.
4. Không tạo một partition vô hạn chỉ vì ghi log theo một ID.
5. API trả kết quả ổn định khi client ở múi giờ khác.

### 19.2. Phân tích cách làm sai

~~~java
// SAI: eventTimeMillis (ms) bị dùng trực tiếp cho USING TIMESTAMP (µs).
long mutationTimestamp = event.getEventTimeMillis();

session.execute(prepared.bind(
    mutationTimestamp,
    event.getState(),
    event.getOrderId()
));
~~~

Lỗi này có thể làm mutation mới thua mọi cell đã ghi với microseconds đúng. Một lỗi khác:

~~~java
// NGUY HIỂM: dùng thời gian xử lý hiện tại để cưỡng ép thắng
// mà không kiểm tra revision, event cũ được replay có thể ghi đè.
long mutationTimestamp = TimestampUnits.toEpochMicros(Instant.now());
~~~

Đơn vị đã đúng nhưng semantics nghiệp vụ **vẫn có thể sai**. Correct unit là cần thiết, không đủ cho event ordering.

### 19.3. Hướng xử lý đề xuất

1. `eventTime` lưu thành CQL `timestamp` để biểu diễn thời điểm nghiệp vụ.
2. `revision` hoặc sequence từ nguồn tin cậy dùng để quyết định transition.
3. Dùng LWT `IF revision = ? AND status = ?` hoặc writer tuần tự theo `order_id` khi cần bất biến mạnh.
4. Không tự đặt `USING TIMESTAMP` trừ đường replay có protocol được thiết kế và kiểm chứng.
5. Với event log, lưu từng event có `event_id` riêng trong bảng `events_by_order_bucket`, partition theo order/bucket, clustering theo thời gian/event ID.
6. Dedupe bằng `event_id` hoặc idempotency key, không dùng “gửi hai lần với cùng mili giây chắc chắn là một event”.
7. Định nghĩa quy trình reconcile khi ghi Cassandra thành công nhưng phát sự kiện downstream thất bại.
8. Xuất ISO-8601/UTC và để UI chuyển sang timezone người dùng.

### 19.4. Ma trận test

| Tình huống | Kỳ vọng |
| --- | --- |
| Event PAID revision 2 đến trước SHIPPED revision 3 | Cả hai được xử lý theo thứ tự phù hợp |
| SHIPPED revision 3 đến trước PAID revision 2 | PAID cũ không làm lùi trạng thái |
| PAID revision 2 được retry | Không phát side effect mới/trùng |
| Client gửi milliseconds vào write micros | Validation/test phát hiện lỗi |
| Worker clock nhanh hơn một phút | Không thể chỉ dựa vào LWW để quyết định business revision |
| Event có timestamp nanoseconds | Chuyển đúng µs khi cần, không gửi raw ns |
| Hai event trong cùng millisecond | `event_id`/tie-breaker ngăn va chạm row |
| Timeout sau LWT | Đọc lại trạng thái và phân biệt đã áp dụng/chưa áp dụng |
| Nhiều replica ở LOCAL_QUORUM | Quorum không thay thế CAS theo revision |
| Lưu Instant có .123456789 | CQL timestamp đọc lại .123Z đúng kỳ vọng |
| Timestamp âm trước epoch | Chuyển bằng floorDiv/floorMod |
| Event replay lịch sử | Có policy rõ giữa eventTime, mutationTs và thứ tự nghiệp vụ |

## 20. Các sai lầm phổ biến cần tránh

| Nhận định sai | Thực tế |
| --- | --- |
| “CQL timestamp và USING TIMESTAMP là cùng đơn vị.” | Cột `timestamp` dùng **ms**, write timestamp dùng **µs** |
| “WRITETIME trả milliseconds vì tên là timestamp.” | `WRITETIME` trả **microseconds** |
| “Instant có nano nên Cassandra giữ nano.” | CQL `timestamp` lưu độ phân giải **milliseconds** |
| “Instant.getNano() là epoch nanoseconds.” | Nó chỉ là phần nanosecond **trong giây** |
| “System.nanoTime() phù hợp cho USING TIMESTAMP.” | Đồng hồ monotonic tương đối, không phải epoch timestamp |
| “Long 13 chữ số đưa được vào USING TIMESTAMP.” | Nếu là epoch millis sẽ bị hiểu sai thành microseconds |
| “Long 16 chữ số có thể đưa vào Instant.ofEpochMilli.” | Nếu là epoch micros, phải đổi đơn vị trước |
| “Timestamp lớn luôn nghĩa là sự kiện mới.” | Clock skew/replay có thể làm timestamp và business order khác nhau |
| “updated_at quyết định xung đột cell.” | Nó là giá trị dữ liệu, write timestamp mới tham gia LWW |
| “Repository.save luôn bảo vệ revision cao hơn.” | Upsert không tự thực thi CAS/optimistic version check |
| “LOCAL_QUORUM sửa được ghi sai đơn vị.” | CL chỉ điều khiển replica confirmations |
| “TTL có đơn vị milliseconds giống cột timestamp.” | TTL dùng **giây** |
| “Gửi lại INSERT TTL là hoàn toàn lũy đẳng.” | Có thể kéo dài hạn sống của cell |
| “Hai bản ghi cùng millisecond không sao khi khóa chỉ là timestamp.” | Có thể va chạm primary key, cần tie-breaker |
| “Hai lần write cùng timestamp, lệnh sau chắc thắng.” | Có tie-breaker theo Cassandra, không phải thứ tự request |
| “Sửa timestamp tương lai bằng timestamp lớn hơn nữa.” | Có thể làm dữ liệu càng khó phục hồi |
| “Đọc WRITETIME mọi cột đều được.” | Có giới hạn với primary key/kiểu cột/phiên bản |
| “Dữ liệu thời gian chỉ là vấn đề UI.” | Sai đơn vị ảnh hưởng conflict resolution, TTL và integrity |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Cột CQL `timestamp` và `USING TIMESTAMP` dùng những đơn vị gì?

*Đáp án:* CQL `timestamp` biểu diễn milliseconds; `USING TIMESTAMP` dùng microseconds.

**Câu 2.** Giá trị `1700000000123` là milliseconds; phải chuyển thế nào để dùng làm write timestamp?

*Đáp án:* Nhân 1.000 có kiểm soát overflow → `1700000000123000` microseconds.

**Câu 3.** Tại sao `Instant.getNano()` không thể cộng thẳng vào `getEpochSecond() * 1_000_000`?

*Gợi ý:* Một vế là microseconds, vế kia nanoseconds.

**Câu 4.** `WRITETIME(status)` có bằng giá trị `updated_at timestamp` không?

*Gợi ý:* Không bắt buộc. Một cái metadata ghi cell (µs), một cái data nghiệp vụ (ms).

**Câu 5.** Vì sao hai events cùng millisecond có thể đè nhau nếu chỉ dùng timestamp làm clustering key?

*Gợi ý:* Cùng primary key logic; cần event ID/tie-breaker.

**Câu 6.** Với `micros = -1`, thời điểm ISO-8601 đúng là gì?

*Đáp án:* `1969-12-31T23:59:59.999999Z`.

**Câu 7.** Nếu retry event revision 7 sau event revision 8, việc dùng write timestamp hiện tại có đủ an toàn không?

*Đáp án:* Không. Event cũ có thể thắng; dùng CAS/ordering theo revision.

**Câu 8.** `USING TTL 3600` nghĩa là gì?

*Đáp án:* 3.600 **giây**, tức một giờ, không phải milliseconds.

**Câu 9.** `System.nanoTime()` có thể dùng làm epoch microseconds sau khi chia 1.000 không?

*Đáp án:* Không, vì không có origin Unix epoch.

**Câu 10.** Một write timestamp sai quá xa tương lai có thể ảnh hưởng gì?

*Gợi ý:* Những mutation đúng giờ sau đó có timestamp nhỏ hơn và không thắng.

**Câu 11.** Vì sao `LOCAL_QUORUM` không giúp sửa clock skew giữa các writer?

*Gợi ý:* CL không thay LWW conflict resolution hay business CAS.

**Câu 12.** Tại sao nên tách `eventTime`, `ingestTime` và `writeTimestampMicros`?

*Gợi ý:* Chúng là các mốc có nguồn và ý nghĩa riêng.

**Câu 13.** Java `Instant.parse("2026-11-25T10:00:00.123456789Z")` lưu vào CQL timestamp rồi đọc lại còn gì?

*Đáp án:* Độ chính xác tối đa milliseconds, tức `...00.123Z`.

**Câu 14.** Vì sao không dùng timestamp cực lớn để giải quyết update không thay đổi?

*Gợi ý:* Future timestamp có thể làm mọi mutation hợp lệ về sau thua.

## 22. Checklist trước khi triển khai production

- **Đơn vị:** Đặt tên biến/API rõ `EpochMillis`, `EpochMicros` và `Instant`; tránh `long timestamp` mơ hồ.
- **Giá trị CQL:** `timestamp` lưu milliseconds; write metadata `USING TIMESTAMP`/`WRITETIME` là microseconds.
- **TTL:** `USING TTL`/`TTL(column)` tính bằng giây, khác cả hai đơn vị trên.
- **Chuyển đổi:** Dùng `Math.multiplyExact`, `Math.addExact`, `floorDiv`/`floorMod` và test trước epoch.
- **Độ chính xác:** Không kỳ vọng CQL timestamp giữ lại nanos; xác định precision trong contract.
- **Timezone:** API dùng ISO-8601 có `Z` hoặc offset; tính bucket theo timezone đã chốt.
- **Nguồn sự thật:** Phân biệt event time, ingest time, mutation timestamp và business revision.
- **Clock sync:** Giám sát NTP/chrony, clock offset và nhiều writer ở các DC.
- **LWW:** Biết xung đột giải quyết theo cell/write timestamp, không theo thứ tự response.
- **CAS:** Dùng điều kiện LWT/revision hoặc writer ordering khi bất biến nghiệp vụ yêu cầu.
- **Retry:** Không retry mù counter, list append, TTL hoặc state transition cạnh tranh.
- **Tombstone:** Xóa/TTL có metadata; tránh custom timestamp cực lớn hoặc sửa không kiểm chứng.
- **Spring Data:** Auditing fields là data, không tự điều khiển write timestamp.
- **Query design:** Partition key, clustering tie-breaker, bucket và paging theo access pattern.
- **Validation:** Giới hạn timestamp từ nguồn không tin cậy; không cho client chỉnh metadata ghi tùy ý.
- **Observability:** Theo dõi writeTs bất thường, CAS failures, lag, timeout và per-cell debug có kiểm soát.
- **Kiểm thử:** Unit test conversion + integration test CQL/WRITETIME + concurrency/replay cases.
- **Rollback:** Trước khi sửa timestamp sai trong production phải có runbook theo version và đối soát replicas.

## Tài liệu tham khảo

- [Apache Cassandra — CQL Data Types](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/types.html): kiểu `timestamp`, `date`, `time`, `timeuuid` và các loại dữ liệu liên quan.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): `USING TIMESTAMP`, `WRITETIME`, `TTL` và conditional updates.
- [Apache Cassandra — Architecture](https://cassandra.apache.org/doc/latest/cassandra/architecture/): replication, timestamp conflict resolution, compaction, tombstone và consistency.
- [Apache Cassandra Java Driver 4.x](https://apache.github.io/cassandra-java-driver/): bind values, timestamp generator, prepared statements, row mapping và request configuration.
- [Spring Data Cassandra Reference](https://docs.spring.io/spring-data/cassandra/reference/): entity mapping, `CassandraTemplate`, repository, auditing và CQL operations.
- [Java SE — Instant API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html): `getEpochSecond`, `getNano`, `toEpochMilli` và biểu diễn thời điểm.

## Kết luận

Trong Apache Cassandra, từ “timestamp” có **ít nhất hai nghĩa quan trọng**: giá trị kiểu CQL `timestamp` là thời điểm lưu bằng **milliseconds**, còn write timestamp dùng trong `USING TIMESTAMP` và `WRITETIME` là **microseconds** để phân xử mutation. Java `Instant` lại biểu diễn thời điểm bằng giây và phần nanosecond. Nhầm ba đơn vị này có thể đưa dữ liệu về năm 1970, tạo timestamp tương lai hoặc khiến một UPDATE thành công về mặt request nhưng không thay đổi giá trị quan sát được.

Với **SPRING_DATA_CASSANDRA**, hãy thiết kế hợp đồng thời gian tường minh, chuyển đổi bằng các helper có kiểm soát overflow, dùng `Instant` đúng độ chính xác của CQL, và **không coi auditing field hay consistency level là giải pháp giải quyết xung đột**. Khi nghiệp vụ cần thứ tự chuyển trạng thái, dùng revision/CAS hoặc writer coordination; khi cần replay và retry, phân biệt event time, write timestamp, TTL và tombstone. Chỉ khi kết hợp hiểu biết về đơn vị, partition key, paging, replication và quan sát vận hành, ứng dụng Spring Data Cassandra mới giữ được tính đúng đắn trong hệ thống phân tán.



