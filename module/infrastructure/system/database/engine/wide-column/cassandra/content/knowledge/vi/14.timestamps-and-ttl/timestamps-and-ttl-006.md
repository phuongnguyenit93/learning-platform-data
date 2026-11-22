# WRITETIME, TTL và quan sát metadata của giá trị trong Apache Cassandra

## 1. Vì sao cần quan sát metadata của một giá trị?

Trong **Apache Cassandra**, cơ sở dữ liệu **wide-column phân tán**, ứng dụng thường đọc một giá trị bằng `SELECT` nhưng giá trị đó chỉ phản ánh **phiên bản đang hiển thị**. Hai bản ghi có nội dung giống nhau vẫn có thể mang metadata khác nhau, đặc biệt là:

- **Write timestamp** (mutation timestamp): mốc thời gian Cassandra dùng để hòa giải các phiên bản của cùng một cell theo cơ chế **last-write-wins**.
- **Time to live (TTL)**: thời gian sống còn lại của một cell được cấu hình tự hết hạn.

CQL cung cấp hai hàm quan sát thiết yếu:

```sql
SELECT writetime(state), ttl(state)
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

Hai hàm trên giúp trả lời các câu hỏi rất thực tế: “Vì sao ghi mới không thắng?”, “Cell còn bao nhiêu giây trước khi hết hạn?”, “Cột này có TTL hay không?”, và “Hai cột của cùng hàng có được ghi ở hai thời điểm khác nhau không?”.

**Giới hạn:** `writetime()` và `ttl()` cho biết metadata của **giá trị đang có hiệu lực trong kết quả đọc**. Chúng **không cung cấp lịch sử chỉnh sửa**, không liệt kê phiên bản thua, không hiện tombstone bị che, và không thay thế công cụ quan sát replica/SSTable khi điều tra sâu.

## 2. Phân biệt write timestamp, CQL `timestamp` và TTL

Đều có liên quan đến thời gian nhưng ba khái niệm đảm nhiệm ba vai trò khác nhau:

| Khái niệm | Đơn vị | Nguồn giá trị | Mục đích |
|---|---|---|---|
| Mutation timestamp | **Micro giây** (µs) kể từ Unix epoch | `USING TIMESTAMP`, client/driver hoặc coordinator | Phân xử phiên bản cell theo LWW |
| Cột CQL kiểu `timestamp` | **Mili giây** (ms) kể từ Unix epoch | Giá trị nghiệp vụ được `INSERT`/`UPDATE` | Lưu mốc thời gian của sự kiện hoặc nghiệp vụ |
| TTL được khai báo (`USING TTL`) | **Giây** | CQL ghi hoặc `default_time_to_live` của bảng | Đặt khoảng thời gian cell được giữ sống |
| `ttl(column)` | **Giây còn lại** | Cassandra tính dựa trên metadata hết hạn của cell | Quan sát thời hạn còn lại tại lúc đọc |

Ví dụ: một cảm biến gửi sự kiện lúc `2026-11-21T01:20:30.123Z` vào cột `event_at timestamp`. Cassandra có thể ghi cell này với mutation timestamp `1795224030123456`, trong khi ứng dụng gắn TTL `3600` giây. Mốc thời gian nghiệp vụ, thứ tự phiên bản và thời hạn tồn tại đều là thông tin riêng.

Với cùng một giá trị `event_at`:

```text
event_at                       -> thời gian của sự kiện (kiểu timestamp, ms)
writetime(event_at)            -> thời gian ghi metadata của cell (epoch µs)
ttl(event_at)                  -> số giây còn sống nếu có TTL
```

Không được kết luận rằng `writetime(event_at)` bằng chính giá trị `event_at`. Cassandra **không tự lấy cột thời gian nghiệp vụ làm write timestamp**, trừ khi ứng dụng cố ý dùng giá trị đó để cấp timestamp cho mutation.

## 3. Hàm `WRITETIME(column)`

`writetime(column)` trả về **write timestamp của cell đang tồn tại**, là số nguyên 64-bit tính bằng **micro giây từ Unix epoch**.

```sql
SELECT state,
       writetime(state) AS state_write_us
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

Nếu trả về:

```text
 state  | state_write_us
--------+------------------
 online | 1795224030123456
```

thì `state_write_us` là metadata dùng để so sánh phiên bản `state`. Con số đó **không tự chứng minh** request được thực hiện đúng vào mốc giờ này: timestamp có thể được client đặt thủ công, nguồn đồng hồ có thể lệch, hoặc một driver có thể tạo timestamp tăng đơn điệu.

### Những điều cần nhớ

1. **Áp dụng theo cell:** hai cột trong một row có thể có `writetime()` khác nhau vì được cập nhật ở những mutation khác nhau.
2. **Không phải khóa sắp xếp:** Cassandra không cho phép tùy ý `ORDER BY writetime(state)`; muốn đọc dữ liệu theo thứ tự thời gian cần thiết kế **clustering key** tương ứng.
3. **Không phải lịch sử:** khi bản mới thắng, `writetime()` không trả về timestamp của các bản từng thua.
4. **Không dùng trên primary key:** partition key và clustering key xác định vị trí dữ liệu, không được truy vấn bằng `writetime()` như cột dữ liệu thông thường.
5. **Không áp dụng cho counter:** counter dùng cơ chế ghi riêng. Với collection hoặc các kiểu phức tạp, khả năng lấy write timestamp và ý nghĩa ở mức phần tử phụ thuộc cấu trúc lưu trữ; hãy kiểm tra theo kiểu cột/phiên bản Cassandra trước khi sử dụng.
6. **Có thể trả về `null`:** khi cell không có giá trị sống để quan sát, ví dụ cột chưa được ghi hoặc đã hết hạn, CQL không trả về một write timestamp của giá trị còn sống.

Vì đơn vị là micro giây, không thể lấy trực tiếp số `writetime()` và truyền vào API mong đợi epoch **mili giây** mà không chuyển đơn vị.

## 4. Hàm `TTL(column)`

`ttl(column)` trả về **số giây còn lại** trước khi một cell có TTL hết hạn. Đây là số đếm giảm dần, không phải thời điểm tuyệt đối và cũng không phải giá trị TTL ban đầu.

```sql
SELECT state,
       ttl(state) AS state_remaining_s
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

Diễn giải kết quả:

| Kết quả của `ttl(state)` | Diễn giải |
|---|---|
| Số dương, ví dụ `113` | Cell đang có TTL và còn khoảng 113 giây tại lúc Cassandra đọc |
| `null`, trong khi `state` còn giá trị | Cell hiện không có TTL hết hạn (không có TTL hoặc TTL đã được loại bỏ) |
| `null`, đồng thời `state = null` | Không còn cell sống để quan sát: có thể chưa từng ghi, bị xóa hoặc hết TTL |

Lưu ý: **`ttl(state) = null` không đủ để kết luận cell đã bị xóa**. Phải đọc cả `state` và kiểm tra cấu hình TTL. Bên cạnh đó, TTL được lưu và tính theo mức giây, nên giá trị quan sát có thể ít hơn một chút so với số giây khai báo do thời gian request và thời gian thực thi.

### TTL không phải khóa tự động phục hồi phiên bản cũ

Khi một mutation ghi giá trị mới kèm TTL, giá trị đó sẽ hết hạn theo cơ chế của Cassandra. Không nên suy luận rằng khi giá trị mới hết hạn, giá trị cũ trước đó sẽ tự xuất hiện trở lại. Cassandra xử lý expiration bằng metadata/tombstone để tránh replica mang bản cũ làm sống lại dữ liệu đã hết hạn.

## 5. Thực hành CQL: quan sát lần ghi không có TTL

Các ví dụ trong bài chạy ở **keyspace thử nghiệm** mà bạn đã tạo và chọn bằng `USE <keyspace>;`. Nếu đã dùng các khóa thử từ lần chạy trước, hãy thay bằng khóa mới để không chịu ảnh hưởng của tombstone hoặc timestamp tồn tại.

Tạo bảng phục vụ truy vấn theo `device_id`:

```sql
CREATE TABLE IF NOT EXISTS device_latest_by_id (
    device_id text PRIMARY KEY,
    state text,
    description text,
    event_at timestamp
);
```

Ghi trạng thái và thời gian sự kiện:

```sql
INSERT INTO device_latest_by_id (
    device_id, state, description, event_at
)
VALUES (
    'sensor-01',
    'online',
    'device reporting normally',
    '2026-11-21T01:20:30.123Z'
);

SELECT device_id,
       state,
       writetime(state) AS state_write_us,
       ttl(state) AS state_remaining_s,
       description,
       writetime(description) AS description_write_us,
       ttl(description) AS description_remaining_s,
       event_at,
       writetime(event_at) AS event_at_write_us
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

Kết quả kỳ vọng về **quan hệ giữa các trường**:

- `state` và `description` đều có giá trị; `writetime(...)` cho mỗi cell có giá trị số micro giây.
- Câu `INSERT` này không chỉ định TTL; nếu bảng cũng không có `default_time_to_live` thì `ttl(state)` và `ttl(description)` là **`null`**.
- `event_at` hiển thị mốc thời gian nghiệp vụ ở độ phân giải mili giây; `writetime(event_at)` là metadata ghi của cell, có thể khác `event_at`.
- Các cột được ghi trong cùng mutation thông thường có thể mang cùng write timestamp; một lần cập nhật sau đó có thể khiến timestamp giữa các cột khác nhau.

Vì câu ghi không dùng `USING TIMESTAMP`, giá trị `writetime()` thực tế phụ thuộc nguồn timestamp được driver hoặc coordinator cấp. **Không cố định con số kết quả** như một phần của test này.

## 6. Quan sát TTL giảm dần theo thời gian

Chỉ cập nhật cột `state`, gán TTL 120 giây:

```sql
UPDATE device_latest_by_id
USING TTL 120
SET state = 'alert'
WHERE device_id = 'sensor-01';

SELECT state,
       writetime(state) AS state_write_us,
       ttl(state) AS state_remaining_s,
       description,
       ttl(description) AS description_remaining_s
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

Ngay sau khi cập nhật, kết quả thường tương tự:

```text
state = alert
state_write_us = <epoch microseconds của UPDATE>
state_remaining_s = <một số dương gần 120>
description = device reporting normally
description_remaining_s = null
```

Nếu chạy lại cùng câu `SELECT` sau khoảng 30 giây, `state_remaining_s` sẽ còn xấp xỉ 90 giây. Sau khi TTL hết hạn, `state` không còn là giá trị sống để truy vấn; `description` vẫn có thể tồn tại, bởi TTL được gắn cho **cell được cập nhật**, không mặc nhiên áp lên mọi cột của row.

### Lưu ý khi thử nghiệm bằng tay

Không nên lấy số TTL trả về rồi so sánh bằng đúng 120, 90 hay 0 trong test tự động. Có độ trễ thực thi và làm tròn theo giây; hãy kiểm tra khoảng hợp lý, ví dụ `0 < ttl(state) <= 120` ngay sau khi ghi, khi cell vẫn đang sống.

Ví dụ này cũng cho thấy một row có thể đồng thời chứa:

| Cột | Giá trị | TTL hiện tại | Write timestamp |
|---|---|---|---|
| `state` | `alert` | Có, giảm dần từ 120 giây | Timestamp của lệnh `UPDATE` |
| `description` | `device reporting normally` | Không | Timestamp của lệnh `INSERT` |
| `event_at` | Mốc thời gian nghiệp vụ | Không | Timestamp của lệnh `INSERT` |

Đó là lý do khi chẩn đoán một row phải đọc `writetime()` và `ttl()` **theo cột cần kiểm tra**.

## 7. Cập nhật lại một cell ảnh hưởng metadata thế nào?

### 7.1. Ghi lại cùng cell với TTL mới

Trên một khóa thử riêng, tạo giá trị có TTL ngắn rồi ghi lại trước khi hết hạn:

```sql
INSERT INTO device_latest_by_id (device_id, state)
VALUES ('sensor-renew', 'temporary')
USING TTL 60;

SELECT state, writetime(state), ttl(state)
FROM device_latest_by_id
WHERE device_id = 'sensor-renew';

UPDATE device_latest_by_id
USING TTL 300
SET state = 'renewed'
WHERE device_id = 'sensor-renew';

SELECT state, writetime(state), ttl(state)
FROM device_latest_by_id
WHERE device_id = 'sensor-renew';
```

Nếu mutation mới thắng LWW, `state = 'renewed'` có **write timestamp mới** và `ttl(state)` gần **300 giây**. TTL mới không cộng dồn với 60 giây còn lại; nó là thời hạn của **phiên bản cell mới được ghi**.

### 7.2. Ghi lại cùng cell mà không đặt TTL

Với bảng **không có `default_time_to_live`**, cập nhật cùng cột mà không dùng `USING TTL` tạo một phiên bản mới **không có TTL**:

```sql
UPDATE device_latest_by_id
SET state = 'persistent'
WHERE device_id = 'sensor-renew';

SELECT state, writetime(state), ttl(state)
FROM device_latest_by_id
WHERE device_id = 'sensor-renew';
```

Nếu lần ghi này có write timestamp lớn hơn bản cũ, kết quả là `state = 'persistent'` và `ttl(state) = null`. Đừng tưởng TTL ban đầu “bám vĩnh viễn” vào cột. Đây là metadata của phiên bản cell đang sống.

**Ngoại lệ cần nhớ:** nếu bảng được cấu hình `default_time_to_live > 0`, lệnh không ghi `USING TTL` vẫn có thể nhận **TTL mặc định của bảng**. Khi muốn hiểu kết quả `ttl()`, luôn xét cả CQL lẫn cấu hình bảng.

### 7.3. Cập nhật cột khác

```sql
UPDATE device_latest_by_id
SET description = 'checked by operator'
WHERE device_id = 'sensor-renew';

SELECT state, writetime(state), ttl(state),
       description, writetime(description), ttl(description)
FROM device_latest_by_id
WHERE device_id = 'sensor-renew';
```

Lần ghi `description` không làm timestamp hoặc TTL của cell `state` tự thay đổi. Cassandra quản lý metadata trên từng cell, nên **hai cột cùng một row không nhất thiết có cùng vòng đời**.

## 8. TTL mặc định ở mức bảng

Ngoài `USING TTL` trong câu ghi, Cassandra hỗ trợ tùy chọn bảng **`default_time_to_live`**, tính bằng giây. Nó phù hợp với dữ liệu có vòng đời đồng nhất, ví dụ thông tin phiên làm việc hoặc bản ghi cache.

```sql
CREATE TABLE IF NOT EXISTS session_cache_by_id (
    session_id uuid PRIMARY KEY,
    account_id uuid,
    payload text
) WITH default_time_to_live = 900;

INSERT INTO session_cache_by_id (session_id, account_id, payload)
VALUES (
    77777777-7777-4777-8777-777777777777,
    88888888-8888-4888-8888-888888888888,
    'short-lived session'
);

SELECT payload, writetime(payload), ttl(payload)
FROM session_cache_by_id
WHERE session_id = 77777777-7777-4777-8777-777777777777;
```

`ttl(payload)` gần 900 giây ngay sau ghi dù `INSERT` **không** có `USING TTL`, bởi bảng đã đặt TTL mặc định. Một lệnh `INSERT ... USING TTL 300` có thể ghi TTL riêng cho những cell được tác động, thay cho thời hạn mặc định theo semantics CQL.

TTL mặc định là quyết định **mô hình dữ liệu và vòng đời**; nó khác với replication factor hay mức nhất quán. Với bảng dùng TTL rộng rãi, cần dự tính tombstone, compaction, repair và lượng truy vấn vào dữ liệu đã hết hạn.

## 9. Xóa cell, tombstone và giới hạn quan sát

Xóa một giá trị khác với việc thay giá trị bằng chuỗi rỗng hoặc chuỗi `'null'`:

```sql
INSERT INTO device_latest_by_id (device_id, state, description)
VALUES ('sensor-delete', 'offline', 'maintenance');

DELETE state FROM device_latest_by_id
WHERE device_id = 'sensor-delete';

SELECT state, writetime(state), ttl(state), description
FROM device_latest_by_id
WHERE device_id = 'sensor-delete';
```

Ở row trên, `state` không còn giá trị sống; `description` vẫn là `'maintenance'`. Kết quả `writetime(state)` và `ttl(state)` không cho thấy timestamp của tombstone vừa được tạo.

**Tombstone** lưu thông tin cần thiết để ngăn dữ liệu cũ trên replica khác tái xuất hiện. Nếu một client ghi lại giá trị với timestamp **thấp hơn** tombstone, Cassandra vẫn ưu tiên tombstone. Nếu cần nghiên cứu timestamp tombstone hoặc các phiên bản cũ, phải dùng công cụ kiểm tra nội bộ/SSTable và nhật ký thao tác phù hợp với phiên bản Cassandra.

Với TTL, khi một cell hết hạn, nó được xử lý theo cơ chế dữ liệu đã xóa. Do vậy:

- `ttl(state)` **không** tiếp tục trả số âm trong các lần `SELECT` bình thường.
- Không coi giá trị `null` là bằng chứng duy nhất để phân biệt **chưa từng ghi**, **đã xóa**, **đã hết hạn** và **không còn sống vì reconciliation**.
- Không lấy `writetime()` và `ttl()` thay cho lịch sử sự kiện nghiệp vụ hay audit log.

Tombstone được dọn theo chính sách compaction và an toàn replication/repair. Dọn không đúng điều kiện có thể gây **zombie data** (dữ liệu cũ xuất hiện trở lại). Cần vận hành repair và cấu hình tombstone phù hợp thay vì cố dùng TTL để “xóa sạch ngay lập tức”.

## 10. `WRITETIME` và `TTL` trong hệ thống phân tán

Một partition có thể có nhiều replica, ví dụ `RF = 3`. Khi client ghi ở consistency level `ONE`, các replica khác có thể chưa có cùng phiên bản ngay lập tức. Khi đọc, Cassandra có cơ chế reconciliation các phiên bản dữ liệu từ những replica tham gia truy vấn; write timestamp là một phần quan trọng trong quyết định phiên bản hiển thị.

| Khía cạnh | Vai trò |
|---|---|
| **Write timestamp** | Chọn phiên bản cell thắng khi xung đột |
| **TTL/expiration metadata** | Quy định khi nào giá trị không còn sống và được xử lý như dữ liệu hết hạn |
| **Replication factor** | Quy định số replica giữ partition |
| **Read/write consistency level** | Quy định số replica tham gia/xác nhận phù hợp cho một yêu cầu |
| **Repair/compaction** | Giúp replica hội tụ và dọn dữ liệu/tombstone theo quy tắc an toàn |

`writetime()` trong một lần `SELECT` phản ánh **giá trị mà yêu cầu đọc đó quan sát**, không có nghĩa mọi replica trên cluster đã ngay lập tức đồng bộ hoàn toàn. Mức nhất quán của lần đọc, trạng thái replica, write timeout và repair ảnh hưởng dữ liệu được quan sát tại thời điểm truy vấn.

Nếu một `UPDATE` mới báo thành công nhưng dữ liệu vẫn là bản cũ, ngoài vấn đề replica chưa đồng bộ, hãy kiểm tra **write timestamp**. Một client có đồng hồ chạy nhanh hoặc cố ý gán `USING TIMESTAMP` trong tương lai có thể khiến mutation hợp lệ về sau thua theo LWW. Tăng `QUORUM` hoặc `ALL` không biến timestamp nhỏ hơn thành bản thắng.

TTL còn có mối liên hệ với đồng hồ và thời gian hết hạn: độ lệch đồng hồ có thể khiến quan sát thời điểm hết hạn khác kỳ vọng. Tuy nhiên **mutation timestamp** và **expiration time** là hai metadata khác nhau; không được giả định thay đổi `USING TIMESTAMP` sẽ tự kéo TTL dài hoặc ngắn theo đúng độ lệch giữa các timestamp.

## 11. Đọc metadata từ Java Driver

Trong ứng dụng Java, dùng **Apache/DataStax Cassandra Java Driver 4.x** để đọc giá trị và metadata của một cell thông thường. Prepared statement giúp thực thi truy vấn lặp lại theo partition key:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class DeviceMetadataReader {
    private final CqlSession session;
    private final PreparedStatement statement;

    public DeviceMetadataReader(CqlSession session) {
        this.session = session;
        this.statement = session.prepare(
            "SELECT state, " +
            "writetime(state) AS state_write_us, " +
            "ttl(state) AS state_ttl_s " +
            "FROM device_latest_by_id WHERE device_id = ?"
        );
    }

    public void inspect(String deviceId) {
        Row row = session.execute(statement.bind(deviceId)).one();
        if (row == null) {
            System.out.println("Device row not found or no live columns");
            return;
        }

        String state = row.getString("state"); // Có thể null.
        Long writtenAtMicros = row.isNull("state_write_us")
            ? null : row.getLong("state_write_us");
        Integer remainingSeconds = row.isNull("state_ttl_s")
            ? null : row.getInt("state_ttl_s");

        System.out.printf("state=%s, writeUs=%s, ttlSeconds=%s%n",
            state, writtenAtMicros, remainingSeconds);
    }
}
```

**Không dùng `getLong()` hoặc `getInt()` một cách mù quáng cho metadata có thể `null`**. Trong Java, kiểu nguyên thủy `long`/`int` không biểu diễn được `null`, trong khi `Long`/`Integer` cho phép giữ trạng thái “không có metadata trả về”.

### Chuyển `writetime()` thành `Instant`

Nếu cần trình bày write timestamp trong log/monitoring, có thể đổi epoch microseconds thành Java `Instant` mà không mất phần micro giây:

```java
import java.time.Instant;

public static Instant fromEpochMicros(long micros) {
    long seconds = Math.floorDiv(micros, 1_000_000L);
    long remainingMicros = Math.floorMod(micros, 1_000_000L);
    return Instant.ofEpochSecond(seconds, remainingMicros * 1_000L);
}
```

`Math.floorDiv` và `Math.floorMod` xử lý đúng cả timestamp trước Unix epoch. Không lấy `Instant.ofEpochMilli(micros)`: điều đó nhầm **micro giây** thành **mili giây**, dẫn đến mốc thời gian sai rất xa.

Nếu muốn tính thời điểm hết hạn dự kiến, có thể lấy thời điểm **đọc** và `ttl(column)` còn lại để ước lượng. Đây **chỉ là gần đúng** vì TTL tính theo giây, request có độ trễ và metadata expiration có thể được xử lý theo thời gian node; không dùng phép cộng này như hạn chót chính xác tới micro giây.

## 12. Phân biệt thời điểm ghi với thời điểm sự kiện trong thiết kế bảng

Một yêu cầu thường gặp: “Đọc 100 mẫu đo gần nhất của thiết bị theo thời gian phát sinh”. **Không** thiết kế bằng cách đọc toàn bộ row rồi `ORDER BY writetime(value)`. Cassandra sắp xếp trong partition theo **clustering key**, và `writetime()` là metadata của cell, không phải khóa truy vấn có thể dùng thay thế.

Ví dụ thiết kế theo truy vấn:

```sql
CREATE TABLE IF NOT EXISTS readings_by_device_day (
    device_id text,
    reading_day date,
    event_time timeuuid,
    temperature double,
    PRIMARY KEY ((device_id, reading_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

SELECT event_time, temperature,
       writetime(temperature), ttl(temperature)
FROM readings_by_device_day
WHERE device_id = 'sensor-01'
  AND reading_day = '2026-11-21'
LIMIT 100;
```

Ở đây `event_time` là **clustering key** sắp xếp các bản ghi; `writetime(temperature)` chỉ quan sát metadata của cell nhiệt độ. Nếu thời gian sự kiện cần độ chính xác khác hoặc yêu cầu thứ tự tuyệt đối giữa nhiều nguồn, thiết kế khóa và nguồn thời gian riêng (ví dụ epoch microseconds + event ID, hoặc sequence từ nguồn tin cậy).

**Time bucket theo ngày** giới hạn số bản ghi trong mỗi partition cho luồng dữ liệu có lưu lượng phù hợp; với thiết bị quá nhiều mẫu mỗi ngày, có thể cần bucket nhỏ hơn. Đây là phần liên quan đến thiết kế bảng theo truy vấn, tách biệt mục tiêu kiểm tra metadata.

## 13. Chẩn đoán nhanh với `WRITETIME` và `TTL`

Khi dữ liệu đọc khác kỳ vọng, có thể theo chuỗi kiểm tra sau:

| Hiện tượng | Truy vấn/kiểm tra | Nguyên nhân cần xem xét |
|---|---|---|
| Cell đột ngột biến mất | `SELECT value, ttl(value), writetime(value)` | Hết TTL, `DELETE`, ghi `null`, sai khóa, hay replica chưa đồng bộ |
| `ttl(value)` là `null`, nhưng value còn | Đối chiếu `USING TTL` và `default_time_to_live` | Cell không có TTL trong phiên bản đang thắng |
| `ttl(value)` thấp hơn TTL vừa đặt | Đo thời gian giữa ghi và đọc | TTL là **giây còn lại**, không phải TTL ban đầu |
| Cập nhật thành công nhưng value cũ vẫn thắng | Xem `writetime(value)`, timestamp trong client log | Mutation mới có timestamp nhỏ hơn hoặc bị tombstone che |
| Hai cột một row có `writetime` khác nhau | Kiểm tra các lệnh `UPDATE` từng cột | Hai cell được ghi ở các mutation khác nhau |
| `writetime(value)` ở xa tương lai | So sánh epoch µs với UTC, timestamp generator, `USING TIMESTAMP` | Clock skew hoặc client cấp timestamp sai |
| `writetime` trả `null` dù từng có ghi | Kiểm tra value, delete/TTL, lịch sử request | Không còn cell sống để hàm đọc metadata |
| Kết quả khác nhau giữa các lần đọc | Đối chiếu CL, RF, replica health, repair và ghi đồng thời | Replica hoặc phiên bản chưa đồng bộ; TTL có thể đang giảm |

Một truy vấn chẩn đoán gọn:

```sql
SELECT device_id,
       state,
       writetime(state) AS state_write_us,
       ttl(state) AS state_ttl_s,
       description,
       writetime(description) AS description_write_us,
       ttl(description) AS description_ttl_s
FROM device_latest_by_id
WHERE device_id = 'sensor-01';
```

**Ba nguyên tắc khi đọc kết quả:**

1. **So sánh metadata theo đúng cell:** `writetime(state)` không đại diện cho toàn row.
2. **Giữ đúng đơn vị:** write timestamp là µs; CQL `timestamp` là ms; TTL là giây.
3. **Kiểm chứng nguồn gán timestamp:** `writetime()` không cho biết ai tạo timestamp; cần log ứng dụng, cấu hình driver/coordinator và lịch sử ghi.

Trong production, tránh quét toàn bảng chỉ để tìm cell có TTL thấp. Mô hình wide-column yêu cầu truy vấn theo partition key phù hợp; để giám sát toàn hệ thống hãy dùng mẫu theo khóa đã biết, số liệu ứng dụng và công cụ vận hành thay vì `ALLOW FILTERING` trên bảng lớn.

## 14. Bài tập tự kiểm tra

**Câu 1.** `writetime(state)` trả về `1800000000000123`. Giá trị này tính bằng micro giây hay mili giây?

**Đáp án:** **Micro giây** từ Unix epoch. Nếu ứng dụng Java muốn tạo `Instant` từ đó, dùng phép chuyển epoch microseconds thích hợp.

**Câu 2.** Cell `state` còn `'online'`, nhưng `ttl(state) = null`. Có thể kết luận cell đã hết hạn không?

**Đáp án:** Không. Giá trị vẫn còn; `ttl(state) = null` thường có nghĩa phiên bản hiện tại **không được đặt TTL**.

**Câu 3.** Câu `UPDATE ... USING TTL 120 SET state = 'alert'` chỉ thay `state`. `description` có tự hết hạn sau 120 giây không?

**Đáp án:** Không. TTL gắn với cell được ghi; `description` giữ metadata riêng nếu không được cập nhật trong cùng mutation.

**Câu 4.** Một cell được ghi với TTL 60 giây, sau 10 giây được ghi lại với TTL 300 giây. Thời gian sống còn lại của bản mới có bằng 350 giây không?

**Đáp án:** Không. Khi bản mới thắng, nó mang TTL mới khoảng **300 giây từ lần ghi mới**, không cộng thời gian của phiên bản trước.

**Câu 5.** Một cell đã bị `DELETE`. `writetime(cell)` có giúp đọc trực tiếp write timestamp của tombstone không?

**Đáp án:** Không. `writetime()` quan sát metadata của giá trị sống; cần lịch sử mutation hoặc công cụ SSTable/điều tra nội bộ phù hợp để xem tombstone.

**Câu 6.** Vì sao một bảng được tạo với `default_time_to_live = 900` vẫn trả `ttl(payload)` là số dương dù câu `INSERT` không chứa `USING TTL`?

**Đáp án:** Vì bảng có TTL mặc định; Cassandra áp dụng thời hạn mặc định cho dữ liệu ghi nếu lệnh không ghi đè chính sách đó.

**Câu 7.** Muốn truy vấn 100 bản ghi mới nhất của thiết bị, có nên dùng `writetime(temperature)` làm khóa sắp xếp không?

**Đáp án:** Không. Cần thiết kế **partition key** và **clustering key** theo truy vấn (chẳng hạn `reading_day` và `event_time`); `writetime()` chỉ dùng để quan sát metadata.

**Câu 8.** Cả hai replica có khác biệt, một ghi `state = A` timestamp `200` và một ghi `state = B` timestamp `300`. `writetime(state)` sau reconciliation sẽ là bao nhiêu nếu không có tombstone mới hơn?

**Đáp án:** `300`, vì phiên bản `B` thắng theo LWW. Hàm không trả về danh sách cả `200` và `300`.

---

**Ghi nhớ:** `WRITETIME(column)` cho biết **mutation timestamp tính bằng micro giây** của cell đang sống; `TTL(column)` cho biết **số giây còn lại** nếu cell có TTL. Đọc hai hàm **theo từng cột**, đặt trong ngữ cảnh `USING TTL`/`default_time_to_live`, LWW, replication và tombstone. Chúng rất hữu ích cho chẩn đoán, nhưng không cung cấp lịch sử phiên bản hay thay thế thiết kế bảng theo truy vấn trong Cassandra.
