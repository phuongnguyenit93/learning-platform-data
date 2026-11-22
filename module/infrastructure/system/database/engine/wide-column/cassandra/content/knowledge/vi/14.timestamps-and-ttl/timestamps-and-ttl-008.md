# default_time_to_live và TTL được chỉ định trong câu lệnh

## 1. Hai cách khai báo thời gian sống trong Cassandra

Trong **Apache Cassandra**, hệ quản trị cơ sở dữ liệu **wide-column phân tán**, dữ liệu được tổ chức theo partition key và clustering key để phục vụ các truy vấn đã biết trước. Ngoài việc thiết kế bảng theo truy vấn, ta cần thiết kế **vòng đời dữ liệu**: một sự kiện cảm biến, thông báo tạm hay bản ghi cache thường không cần tồn tại mãi.

Cassandra hỗ trợ **time to live (TTL)** theo hai cách:

1. **TTL mặc định của bảng**: tùy chọn `default_time_to_live` đặt trong `CREATE TABLE` hoặc `ALTER TABLE`. Nếu một mutation không chỉ định TTL riêng, các cell được ghi sẽ áp dụng TTL mặc định của bảng.
2. **TTL chỉ định trong câu lệnh**: `USING TTL <seconds>` trong `INSERT` hoặc `UPDATE`. Câu ghi tự quyết định thời gian sống của các cell mà nó cập nhật, **ưu tiên hơn** TTL mặc định của bảng.

Điểm cốt lõi là **TTL gắn với phiên bản cell được ghi**, không phải một bộ đếm chung của toàn partition. Thay đổi TTL mặc định của bảng không tự viết lại tất cả dữ liệu hiện có. Một lệnh ghi cột khác cũng không tự gia hạn TTL của cột chưa được cập nhật.

Ví dụ bảng cache giữ dữ liệu **15 phút** theo mặc định, nhưng một số thông báo chỉ cần sống **2 phút**:

```sql
CREATE TABLE IF NOT EXISTS notification_cache_by_id (
    notification_id uuid PRIMARY KEY,
    account_id uuid,
    payload text,
    priority text
) WITH default_time_to_live = 900;

-- Không chỉ định TTL: các cell dữ liệu mới nhận TTL mặc định 900 giây.
INSERT INTO notification_cache_by_id (
    notification_id, account_id, payload, priority
)
VALUES (
    11111111-8888-4888-8888-111111111111,
    22222222-8888-4888-8888-222222222222,
    'Thông báo thông thường',
    'NORMAL'
);

-- Chỉ định TTL riêng: các cell dữ liệu mới nhận TTL 120 giây.
INSERT INTO notification_cache_by_id (
    notification_id, account_id, payload, priority
)
VALUES (
    33333333-8888-4888-8888-333333333333,
    22222222-8888-4888-8888-222222222222,
    'Thông báo ưu tiên ngắn hạn',
    'HIGH'
)
USING TTL 120;
```

Thời gian sống của hai bản ghi khác nhau **do chính sách của hai lần ghi**, dù cùng nằm trong một bảng.

## 2. `default_time_to_live`: TTL mặc định ở cấp bảng

`default_time_to_live` là thuộc tính bảng, có giá trị là **số giây**. Giá trị mặc định của thuộc tính này là **`0`**, nghĩa là **không áp dụng thời hạn sống mặc định**.

```sql
CREATE TABLE IF NOT EXISTS session_data_by_id (
    session_id uuid PRIMARY KEY,
    owner_id uuid,
    session_payload text
) WITH default_time_to_live = 1800;
```

Bảng trên thiết lập TTL mặc định **1.800 giây = 30 phút**. Khi `INSERT` ghi `session_payload` mà **không có `USING TTL`**, phiên bản cell mới sẽ có thời hạn sống khoảng 30 phút kể từ lần ghi.

```sql
INSERT INTO session_data_by_id (
    session_id, owner_id, session_payload
)
VALUES (
    44444444-8888-4888-8888-444444444444,
    55555555-8888-4888-8888-555555555555,
    'example-session'
);

SELECT session_payload,
       ttl(session_payload) AS remaining_seconds,
       writetime(session_payload) AS write_micros
FROM session_data_by_id
WHERE session_id = 44444444-8888-4888-8888-444444444444;
```

Ngay sau ghi, `remaining_seconds` thường xấp xỉ `1800`. `write_micros` là mutation timestamp dùng cho **last-write-wins (LWW)**, tính bằng micro giây, **không phải** TTL ban đầu và không phải thời gian sống còn lại.

**Tại sao đây là mặc định chứ không phải “hạn sử dụng của bảng”?** Bởi từng mutation tạo dữ liệu vào thời điểm khác nhau. Hai cell trong cùng bảng được ghi cách nhau một giờ có thể hết hạn cách nhau một giờ. Tùy chọn bảng quyết định TTL **khi ghi cell mới**, không ấn định một ngày hết hạn chung cho toàn bảng.

## 3. Thứ tự ưu tiên giữa TTL mặc định và TTL của câu lệnh

Để xác định thời gian sống của một cell vừa ghi, hãy xét **TTL mà chính mutation đang dùng**:

| TTL của bảng | TTL trên `INSERT`/`UPDATE` | TTL của cell mới |
|---|---|---|
| `default_time_to_live = 0` | Không chỉ định | **Không TTL** |
| `default_time_to_live = 900` | Không chỉ định | **900 giây** |
| `default_time_to_live = 900` | `USING TTL 120` | **120 giây** |
| `default_time_to_live = 900` | `USING TTL 3600` | **3.600 giây** |
| `default_time_to_live = 900` | `USING TTL 0` | **Không TTL** cho các cell được ghi bởi mutation đó |
| `default_time_to_live = 0` | `USING TTL 120` | **120 giây** |
| Bảng hiện `1800` nhưng cell cũ được ghi khi mặc định là `900` | Không có mutation mới trên cell cũ | Cell cũ **giữ thời hạn của phiên bản đã ghi** |

Trong CQL, **`USING TTL 0` có ý nghĩa đặc biệt**: đặt phiên bản mới của cell ở trạng thái **không hết hạn theo TTL**. Đây là cách ghi đè TTL mặc định cho một số dữ liệu cần tồn tại lâu hơn. Nó **không tự kéo ngược** các cell khác trong hàng và cũng không làm tất cả dữ liệu cũ của bảng trở thành vĩnh viễn.

Chỉ nên dùng `USING TTL 0` khi thực sự muốn phiên bản mới không có TTL. Không dùng số âm làm TTL, không dùng `-1` để biểu diễn “không giới hạn”, và không giả định mọi hệ thống đều hỗ trợ TTL cực lớn: giới hạn hợp lệ, chính sách chống tràn mốc expiration và hành vi thông báo lỗi phụ thuộc phiên bản Cassandra/cấu hình cluster.

**Quy tắc chọn TTL chỉ có tác dụng nếu mutation giành được phiên bản thắng**. Nếu client cố ghi một cell ở timestamp thấp hơn phiên bản đang sống hoặc tombstone đã có, câu lệnh đó có thể được xác nhận nhưng **không thay đổi** giá trị/TTL mà các lần đọc quan sát.

## 4. Thực hành CQL: so sánh mặc định, TTL riêng và TTL 0

Các ví dụ dùng **keyspace thử nghiệm** đã được chọn bằng `USE <keyspace>;`. Nếu bảng cùng tên đã được tạo trước đó với cấu hình khác, hãy kiểm tra schema hoặc tạo bảng thử mới; `CREATE TABLE IF NOT EXISTS` **không** sửa bảng đã tồn tại.

### Bước 1 — Bảng mặc định 600 giây

```sql
CREATE TABLE IF NOT EXISTS ttl_policy_lab_by_id (
    item_id uuid PRIMARY KEY,
    title text,
    state text,
    note text
) WITH default_time_to_live = 600;
```

### Bước 2 — Ba hàng dùng ba chính sách TTL

```sql
-- Hàng A: mặc định 600 giây.
INSERT INTO ttl_policy_lab_by_id (item_id, title, state)
VALUES (
    aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa,
    'Theo mac dinh',
    'OPEN'
);

-- Hàng B: TTL riêng 90 giây.
INSERT INTO ttl_policy_lab_by_id (item_id, title, state)
VALUES (
    bbbbbbbb-8888-4888-8888-bbbbbbbbbbbb,
    'TTL rieng',
    'OPEN'
)
USING TTL 90;

-- Hàng C: ghi rõ TTL 0; không đặt thời hạn sống cho các cell mới.
INSERT INTO ttl_policy_lab_by_id (item_id, title, state)
VALUES (
    cccccccc-8888-4888-8888-cccccccccccc,
    'Khong TTL',
    'OPEN'
)
USING TTL 0;
```

### Bước 3 — Đọc TTL thực tế của từng cell

```sql
SELECT item_id, title, ttl(title) AS title_ttl,
       state, ttl(state) AS state_ttl
FROM ttl_policy_lab_by_id
WHERE item_id IN (
    aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa,
    bbbbbbbb-8888-4888-8888-bbbbbbbbbbbb,
    cccccccc-8888-4888-8888-cccccccccccc
);
```

CQL trên chỉ truy vấn tập **partition key cụ thể**. Kết quả khái niệm ngay sau ghi:

| Hàng | `ttl(title)` | `ttl(state)` | Giải thích |
|---|---:|---:|---|
| A | Gần `600` | Gần `600` | Áp dụng TTL mặc định |
| B | Gần `90` | Gần `90` | TTL câu lệnh ghi đè TTL bảng |
| C | `null` | `null` | `USING TTL 0` tạo cell không TTL |

Trong thực nghiệm, mỗi lần `SELECT` đều tốn thời gian, vì thế các số TTL dương **giảm dần**; không kiểm tra chúng bằng so sánh bằng chính xác `600` hay `90`. Nếu không muốn dùng truy vấn `IN`, có thể đọc riêng từng partition bằng `WHERE item_id = ...`.

### Bước 4 — Một cột mới có thể có TTL khác các cột cũ

```sql
-- Ghi cột note với TTL ngắn, giữ nguyên title và state.
UPDATE ttl_policy_lab_by_id
USING TTL 30
SET note = 'can xu ly som'
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;

SELECT title, ttl(title),
       state, ttl(state),
       note, ttl(note)
FROM ttl_policy_lab_by_id
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;
```

`title` và `state` giữ TTL còn lại của lần `INSERT` (ban đầu 600 giây); `note` có thời gian sống còn lại gần 30 giây. **TTL mặc định ở mức bảng không biến mọi cell thành một gói có cùng một bộ đếm.**

## 5. `UPDATE` trên cell cũ: TTL có được gia hạn không?

Một `UPDATE` ghi lại cell sẽ tạo **phiên bản mới** cho cell đó. Nếu mutation thắng theo timestamp, cell nhận thời hạn sống của **lần ghi mới**:

```sql
-- Hàng A từng có state với default TTL 600 giây.
UPDATE ttl_policy_lab_by_id
USING TTL 1200
SET state = 'PROCESSING'
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;

SELECT title, ttl(title),
       state, ttl(state),
       writetime(state) AS state_write_us
FROM ttl_policy_lab_by_id
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;
```

Nếu lần ghi mới thắng, `state` có TTL gần **1.200 giây** kể từ lần `UPDATE`, còn `title` vẫn đếm ngược từ **600 giây của lần `INSERT`**. TTL không cộng `1200` vào số giây còn lại của bản cũ.

Với bảng đang có TTL mặc định 600 giây, cập nhật **không** chỉ định `USING TTL` sẽ nhận **default TTL 600 giây cho phiên bản mới**:

```sql
UPDATE ttl_policy_lab_by_id
SET state = 'QUEUED'
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;

SELECT state, ttl(state)
FROM ttl_policy_lab_by_id
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;
```

Nếu lần cập nhật thắng, `state` có TTL gần 600 giây. Nó **không giữ** TTL 1.200 giây của phiên bản trước, vì TTL của cell mới được quyết định bởi mutation vừa thực hiện.

### Muốn chuyển một cell sang không TTL

```sql
UPDATE ttl_policy_lab_by_id
USING TTL 0
SET state = 'ARCHIVED'
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;

SELECT state, ttl(state), title, ttl(title)
FROM ttl_policy_lab_by_id
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;
```

Kết quả kỳ vọng nếu mutation thắng: `state = 'ARCHIVED'`, `ttl(state) = null`; `title` tiếp tục có TTL còn lại của chính nó. Để đặt TTL 0 cho **một phiên bản mới**, vẫn phải **ghi lại giá trị của cell**; không có thao tác làm toàn bộ các cell cũ trong bảng “bỏ TTL” chỉ bằng cách sửa tùy chọn mặc định.

**Lưu ý về thời gian:** TTL bắt đầu đếm khi Cassandra xử lý mutation được ghi, không bắt đầu từ một cột `created_at` hay giá trị `USING TIMESTAMP` do ứng dụng đặt ở quá khứ. Đồng hồ server và quá trình xử lý expiration ảnh hưởng mốc thực tế; không thiết kế deadline pháp lý/chính xác tuyệt đối chỉ dựa vào `ttl()`.

## 6. `ALTER TABLE` đổi TTL mặc định: hiệu lực từ lúc nào?

Ta có thể thay đổi chính sách mặc định mà **không** tạo bảng khác:

```sql
ALTER TABLE ttl_policy_lab_by_id
WITH default_time_to_live = 1800;
```

Từ sau khi schema thay đổi được áp dụng, những mutation **không có `USING TTL`** sẽ dùng mặc định mới **1.800 giây**. Nhưng Cassandra **không đi qua tất cả SSTable để viết lại TTL của các cell đã tồn tại**.

Ví dụ:

```sql
-- Hàng D được ghi sau khi đổi default TTL sang 1800.
INSERT INTO ttl_policy_lab_by_id (item_id, title, state)
VALUES (
    dddddddd-8888-4888-8888-dddddddddddd,
    'Sau ALTER',
    'OPEN'
);

SELECT title, ttl(title), state, ttl(state)
FROM ttl_policy_lab_by_id
WHERE item_id = dddddddd-8888-4888-8888-dddddddddddd;
```

`ttl(title)` và `ttl(state)` ở hàng D xấp xỉ `1800`. Các cell ở hàng A/B/C **không tự nhận** TTL 1.800 giây chỉ vì bảng đã đổi cấu hình. Khi một cell cũ được **cập nhật lại mà không chỉ định TTL**, cell đó mới có thể nhận default TTL **hiện hành**.

| Thao tác | Cell cũ trong bảng | Cell ghi mới sau thao tác |
|---|---|---|
| Đổi default từ `600` sang `1800` | Giữ TTL gắn với phiên bản trước | Nếu không có `USING TTL`: 1800 giây |
| Đổi default từ `1800` sang `0` | TTL đang tồn tại không tự biến mất | Nếu không có `USING TTL`: không TTL |
| Ghi `USING TTL 45` sau khi đổi default | Không tác động cột không được ghi | Cột được ghi: 45 giây |

Khi rollout schema giữa các node, phải đợi schema agreement và bảo đảm client dùng metadata phù hợp trước khi kiểm thử. Trong production, đổi TTL mặc định là thay đổi **chính sách lưu trữ trong tương lai**: cần dự đoán lượng dữ liệu mới, thời gian giữ tombstone và kế hoạch compaction/repair.

## 7. `USING TTL 0`, `null` và những ngộ nhận

Ba biểu thức sau mang ý nghĩa khác nhau:

- **`USING TTL 0`:** yêu cầu phiên bản các cell được ghi **không có TTL**.
- **`ttl(col) = null`:** hàm truy vấn không trả về thời gian sống còn lại. Nếu `col` vẫn có giá trị thì cell hiện **không có TTL**; nếu `col` không còn giá trị, có thể do chưa ghi, xóa hoặc đã hết TTL.
- **`default_time_to_live = 0`:** bảng không có thời hạn sống **mặc định**; câu ghi cụ thể vẫn có thể dùng `USING TTL 120`.

Đặc biệt, `USING TTL 0` **không xóa giá trị**. Nó tạo một phiên bản dữ liệu không có TTL khi giá trị được ghi thành công. Xóa cell là thao tác khác:

```sql
DELETE state FROM ttl_policy_lab_by_id
WHERE item_id = cccccccc-8888-4888-8888-cccccccccccc;
```

`DELETE` tạo tombstone (dấu xóa) để che các phiên bản cũ. Nếu muốn bảo đảm cập nhật có điều kiện trước khi xóa hoặc trước khi đổi trạng thái, hãy cân nhắc **lightweight transaction (LWT)** và kiểm tra kết quả áp dụng; TTL không thay thế điều kiện nghiệp vụ.

Một cell đang có TTL có thể được ghi đè bằng một mutation ở write timestamp **thấp hơn** phiên bản đang thắng. Khi đó, bản ghi mới có thể không xuất hiện dù câu `UPDATE` trả thành công; `ttl()` vẫn hiển thị metadata của **bản thắng hiện tại**, không phải TTL của request vừa gửi. Đây là tương tác trực tiếp giữa chương **Timestamp và TTL**.

## 8. TTL theo cell, hàng và khóa chính

Ví dụ hàng A có các cell:

```text
Partition: item_id = A
|
+-- title = "Theo mac dinh"  | TTL theo INSERT ban đầu
+-- state = "ARCHIVED"      | TTL = không có (USING TTL 0)
+-- note = "can xu ly som" | TTL 30 giây từ UPDATE riêng
```

Việc `note` hết hạn trước không buộc `title` và `state` biến mất. Một hàng có thể tiếp tục trả về **một phần dữ liệu**, bởi TTL là metadata của các cell sống. Nếu **mọi dữ liệu sống** đã hết hạn và không còn row marker sống phù hợp, hàng có thể biến mất khỏi kết quả truy vấn.

Primary key gồm partition key và clustering key, đóng vai trò xác định địa chỉ dữ liệu. Không truy vấn `ttl(primary_key_column)` hoặc `writetime(primary_key_column)` như với cột thông thường.

Với collection có nhiều phần tử hoặc các mutation xóa cả row/partition, phạm vi cell và tombstone phức tạp hơn ví dụ scalar ở đây. Khi thiết kế hệ thống thực, tránh suy luận rằng mọi cấu trúc Cassandra đều có đúng một timestamp/TTL chung cho cả hàng.

## 9. Java Driver: đặt TTL riêng hoặc dùng TTL mặc định

Ứng dụng Java có thể sử dụng **Apache/DataStax Cassandra Java Driver 4.x** để chủ động chọn TTL từng request. Prepared statement với `USING TTL ?` nhận tham số kiểu số nguyên **giây**, không phải `Duration.toMillis()` hoặc epoch microseconds.

```java
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class NotificationCacheRepository {
    private final CqlSession session;
    private final PreparedStatement insertDefault;
    private final PreparedStatement insertWithTtl;
    private final PreparedStatement updateWithTtl;
    private final PreparedStatement selectRemaining;

    public NotificationCacheRepository(CqlSession session) {
        this.session = session;

        this.insertDefault = session.prepare(
            "INSERT INTO notification_cache_by_id " +
            "(notification_id, account_id, payload, priority) " +
            "VALUES (?, ?, ?, ?)"
        );
        this.insertWithTtl = session.prepare(
            "INSERT INTO notification_cache_by_id " +
            "(notification_id, account_id, payload, priority) " +
            "VALUES (?, ?, ?, ?) USING TTL ?"
        );
        this.updateWithTtl = session.prepare(
            "UPDATE notification_cache_by_id USING TTL ? " +
            "SET payload = ? WHERE notification_id = ?"
        );
        this.selectRemaining = session.prepare(
            "SELECT payload, ttl(payload) AS payload_ttl_s " +
            "FROM notification_cache_by_id WHERE notification_id = ?"
        );
    }

    // Theo default_time_to_live của bảng (ví dụ 900 giây).
    public void saveDefault(UUID notificationId, UUID accountId,
                            String payload, String priority) {
        session.execute(insertDefault.bind(
            notificationId, accountId, payload, priority
        ));
    }

    // TTL riêng; 0 có nghĩa phiên bản mới không TTL.
    public void saveWithTtl(UUID notificationId, UUID accountId,
                            String payload, String priority, int ttlSeconds) {
        if (ttlSeconds < 0) {
            throw new IllegalArgumentException("TTL must be nonnegative");
        }
        session.execute(insertWithTtl.bind(
            notificationId, accountId, payload, priority, ttlSeconds
        ));
    }

    // Chỉ cập nhật payload; các cell khác giữ metadata của chúng.
    public void replacePayload(UUID notificationId, String payload,
                               int ttlSeconds) {
        if (ttlSeconds < 0) {
            throw new IllegalArgumentException("TTL must be nonnegative");
        }
        session.execute(updateWithTtl.bind(ttlSeconds, payload, notificationId));
    }

    public Integer getRemainingSeconds(UUID notificationId) {
        Row row = session.execute(selectRemaining.bind(notificationId)).one();
        if (row == null || row.isNull("payload_ttl_s")) {
            return null;
        }
        return row.getInt("payload_ttl_s");
    }
}
```

Những điểm cần kiểm soát:

- Dùng `saveDefault(...)` khi muốn **nhận chính sách TTL của bảng**; đây là đường đi không dùng `USING TTL`.
- Dùng `saveWithTtl(..., 120)` khi muốn chỉ định **120 giây** cho những cell được `INSERT`.
- Dùng `saveWithTtl(..., 0)` khi muốn các cell mới **không TTL** trong trường hợp nghiệp vụ cho phép.
- `replacePayload(...)` chỉ đổi `payload`. `account_id` và `priority` không được ghi lại nên không tự được gia hạn TTL.
- `getRemainingSeconds(...) == null` có thể nghĩa là **không TTL hoặc không có cell sống**. Muốn phân biệt cần truy vấn thêm chính giá trị và trạng thái nghiệp vụ.

Nếu muốn cấu hình thời gian ở dạng `Duration`, cần chuyển sang **giây một cách có kiểm tra**, tránh làm tròn một khoảng dưới một giây thành `0` rồi vô tình khiến cell không hết hạn. Cũng phải xét giới hạn TTL của phiên bản Cassandra đang chạy; kiểm tra số giây hợp lệ trước khi gửi.

## 10. TTL, mutation timestamp và đồng hồ phân tán

TTL được xác định theo lần ghi của phiên bản cell mới, còn **mutation timestamp** là metadata có độ phân giải **micro giây** dùng để chọn phiên bản khi hai writer ghi cùng cell. Cột CQL kiểu `timestamp` lại biểu diễn mốc nghiệp vụ ở độ phân giải **mili giây**.

Ví dụ nhập dữ liệu lịch sử nhưng muốn cache kết quả trong 2 phút:

```sql
INSERT INTO ttl_policy_lab_by_id (item_id, title)
VALUES (
    eeeeeeee-8888-4888-8888-eeeeeeeeeeee,
    'Su kien duoc import'
)
USING TIMESTAMP 1700000000000000 AND TTL 120;

SELECT title, writetime(title), ttl(title)
FROM ttl_policy_lab_by_id
WHERE item_id = eeeeeeee-8888-4888-8888-eeeeeeeeeeee;
```

Nếu chưa có phiên bản cạnh tranh, `writetime(title)` là `1700000000000000` (một mốc trong quá khứ), trong khi `ttl(title)` **gần 120 giây** ngay sau lần import. TTL **không** được đếm từ write timestamp trong quá khứ. Việc nhập dữ liệu cũ và lựa chọn TTL là hai quyết định khác nhau.

Trong cluster có **RF = 3**, replica có thể chưa nhận cùng mutation ngay lập tức, tùy **consistency level (CL)**. `ONE`, `QUORUM` và `ALL` quyết định yêu cầu phản hồi đọc/ghi; chúng **không thay đổi** TTL mặc định hay TTL ghi rõ trong câu lệnh. Một bản ghi có timestamp ở tương lai có thể khiến mutation mới với TTL đúng nhưng timestamp thấp hơn **thua theo LWW**.

Đồng hồ phía server có ảnh hưởng tới thời điểm hết hạn; vì vậy cần đồng bộ giờ của các node Cassandra. Nếu driver/client tạo mutation timestamp, đồng hồ host ứng dụng cũng cần được giám sát để giảm xung đột. Thay đổi `USING TIMESTAMP` để “kéo dài TTL” là sai mục đích và có thể làm phát sinh future timestamp che các ghi hợp lệ về sau.

## 11. Hết TTL, tombstone, compaction và repair

Khi TTL hết, Cassandra coi cell là dữ liệu đã hết hạn và xử lý tương tự **tombstone** để ngăn một replica còn dữ liệu cũ làm nó xuất hiện trở lại. TTL làm giá trị **không còn sống về mặt đọc**, nhưng không bảo đảm các byte được xóa ngay lập tức khỏi mọi SSTable.

```text
Ghi mutation                         Hết TTL                        Dọn vật lý
     |                                  |                               |
     v                                  v                               v
Phiên bản cell sống  --đếm TTL--> Cell hết hiệu lực --compaction an toàn--> Loại bỏ
                                    |
                              Tombstone/metadata
                              bảo vệ trước bản cũ
```

Cassandra dùng **compaction** để hợp nhất/dọn SSTable khi đủ điều kiện; **repair** giúp các replica hội tụ. Một bảng có mặc định TTL thấp nhưng lưu lượng ghi cao có thể tạo nhiều dữ liệu hết hạn và áp lực tombstone, ảnh hưởng latency đọc, dung lượng đĩa và công việc compaction.

Vì vậy, trước khi bật TTL mặc định cho bảng lớn, hãy xem:

1. **Đặc điểm truy vấn và partition:** một partition có bao nhiêu cell, tần suất ghi/đọc, có thường xuyên đọc lẫn dữ liệu đã hết hạn không?
2. **Chiến lược compaction:** bảng chuỗi thời gian có thể cân nhắc `TimeWindowCompactionStrategy` khi phù hợp với mô hình ghi và thời gian sống; không mặc định áp dụng cho mọi bảng.
3. **Repair và tombstone:** không giảm `gc_grace_seconds` tùy tiện chỉ để dọn dữ liệu nhanh; nếu còn replica giữ bản cũ, dọn tombstone thiếu an toàn có thể gây **zombie data**.
4. **Thời gian lưu trữ thực tế:** TTL không phải bảo đảm xóa vật lý ngay trên đĩa, snapshot, backup hoặc bản sao ngoài Cassandra.

Nếu một cell hết hạn, `ttl(cell)` không trả về số âm trong `SELECT` thông thường; khi không có giá trị sống, kết quả có thể là `null` hoặc row không còn xuất hiện. `writetime(cell)` cũng không đọc trực tiếp timestamp của tombstone đã tạo.

## 12. Retry, ghi đồng thời và thay đổi chính sách trong vận hành

Ba tình huống gây lỗi thường gặp:

**Retry làm gia hạn TTL ngoài ý muốn.** Một request cache với TTL 300 giây bị timeout, client phát lại sau 2 phút như một ghi mới. Nếu bản retry trở thành phiên bản thắng, thời hạn sống có thể được xác lập lại từ lần ghi sau, khiến cache tồn tại lâu hơn mong muốn. Với nghiệp vụ có thời hạn tuyệt đối, hãy lưu thêm `expires_at` và xác định chính sách retry/idempotency rõ ràng.

**Thay đổi default TTL nhưng kỳ vọng cell cũ đổi theo.** Người vận hành `ALTER TABLE ... WITH default_time_to_live = 60` để giảm lưu trữ. Cell được ghi từ hôm trước có thể vẫn giữ TTL cũ, hoặc không TTL, cho tới khi hết hạn hay được cập nhật lại. Cần kế hoạch chuyển đổi dữ liệu cũ riêng nếu yêu cầu vòng đời thay đổi.

**Hai writer dùng TTL khác nhau cho cùng cell.** Dịch vụ A ghi `state = 'READY' USING TTL 120`; dịch vụ B ghi `state = 'DONE' USING TTL 0`. Cassandra so sánh **write timestamp** để chọn phiên bản thắng. TTL mà `ttl(state)` trả về gắn với **phiên bản thắng**, chứ không phải “lấy TTL lớn nhất” hay “ưu tiên có TTL”.

Một cách phân biệt rõ tại tầng ứng dụng:

| Ý định | Chính sách |
|---|---|
| Mọi thông báo mới mặc định hết hạn sau 15 phút | `default_time_to_live = 900` |
| Một thông báo chỉ giữ 2 phút | `INSERT ... USING TTL 120` |
| Một bản ghi cần lưu dài hạn trong cùng bảng | `INSERT/UPDATE ... USING TTL 0` với chính sách kiểm soát |
| Cell cũ phải đổi sang TTL mới | **Ghi lại cell** theo TTL mong muốn, bảo đảm mutation thắng LWW |
| Khách hàng cần hạn sử dụng tuyệt đối, chính xác theo nghiệp vụ | Lưu `expires_at` và kiểm tra nghiệp vụ; dùng TTL để quản lý lưu trữ |

## 13. Chẩn đoán TTL không giống kỳ vọng

Một câu truy vấn theo đúng partition key:

```sql
SELECT item_id, title, writetime(title), ttl(title),
       state, writetime(state), ttl(state),
       note, writetime(note), ttl(note)
FROM ttl_policy_lab_by_id
WHERE item_id = aaaaaaaa-8888-4888-8888-aaaaaaaaaaaa;
```

Đọc kết quả cùng schema và lịch sử mutation:

| Hiện tượng | Cần kiểm tra |
|---|---|
| Không khai báo `USING TTL` nhưng `ttl(title)` có số dương | Bảng có `default_time_to_live > 0` |
| Khai báo `USING TTL 120` nhưng đọc thấy gần `900` | Đã đọc đúng cell/khóa chưa? Có mutation khác thắng? Có ghi lại không gán TTL và nhận default 900 không? |
| Sau `ALTER TABLE`, cell cũ vẫn còn TTL cũ | `ALTER` không sửa metadata đã ghi của cell |
| `ttl(state) = null` nhưng `state` còn giá trị | Cell hiện tại **không TTL**, có thể do `USING TTL 0` |
| `ttl(state) = null` và `state = null` | Chưa có cell sống; kiểm tra TTL hết hạn, delete, key và replica |
| `UPDATE` báo thành công nhưng TTL không đổi | `writetime(state)`, timestamp của mutation mới, tombstone và LWW |
| TTL vừa gán đã giảm vài giây | `ttl()` cho **giây còn lại** tại lúc đọc; có độ trễ và độ phân giải giây |
| Tình trạng hết hạn khác nhau giữa các lần đọc | Đối chiếu CL, replica health, clock skew, repair và các ghi cạnh tranh |

Không chạy quét toàn bảng hoặc `ALLOW FILTERING` trên dữ liệu lớn chỉ để tìm những cell có TTL thấp. Với Cassandra, hãy **thiết kế truy vấn theo partition key** hoặc dùng hệ thống giám sát/metadata nghiệp vụ phù hợp. Nếu cần xóa theo thời điểm định kỳ ở quy mô lớn, cân nhắc bảng chia bucket theo thời gian và chính sách compaction đi kèm.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Bảng có `default_time_to_live = 600`. Một lệnh `INSERT` không có `USING TTL` ghi `state`. TTL của phiên bản mới là bao nhiêu?

**Đáp án:** Khoảng **600 giây** từ lần ghi. `ttl(state)` ngay sau đó gần 600 và giảm dần.

**Câu 2.** Cũng bảng trên, một lệnh `INSERT ... USING TTL 90` ghi `state`. Mức 600 hay 90 giây được áp dụng?

**Đáp án:** **90 giây**, vì TTL chỉ định trong câu lệnh ưu tiên hơn TTL mặc định của bảng.

**Câu 3.** `INSERT ... USING TTL 0` trên bảng mặc định TTL 600 có ý nghĩa gì?

**Đáp án:** Phiên bản các cell dữ liệu được ghi **không TTL**. Các cell cũ không được cập nhật vẫn giữ metadata riêng của chúng.

**Câu 4.** Đổi `default_time_to_live` từ 600 sang 1800 có làm mọi cell đang tồn tại gia hạn thêm 20 phút không?

**Đáp án:** **Không**. Tùy chọn mới áp dụng cho **mutation sau đó** khi không có TTL riêng; cell cũ giữ hạn đã được gắn.

**Câu 5.** `state` có TTL 120, sau đó `UPDATE ... SET note = ...` (không chạm `state`). `state` có đếm lại 120 giây không?

**Đáp án:** **Không**. Chỉ cell được cập nhật mới nhận TTL của mutation đó.

**Câu 6.** `state` được cập nhật `USING TTL 30` nhưng timestamp của mutation nhỏ hơn phiên bản đang thắng. `ttl(state)` có chắc chuyển thành gần 30 không?

**Đáp án:** **Không**. Nếu mutation thua LWW, cell vẫn giữ giá trị/TTL của phiên bản thắng.

**Câu 7.** Một lần import hôm nay sử dụng `USING TIMESTAMP` mang mốc năm 2023 và `USING TTL 120`. Cell có tự hết hạn ngay vì mốc năm 2023 không?

**Đáp án:** **Không**. Mutation timestamp chi phối thứ tự LWW; TTL được đếm từ lần ghi có hiệu lực hiện tại nếu mutation thắng.

**Câu 8.** Bảng TTL mặc định tạo nhiều tombstone. Có nên luôn giảm `gc_grace_seconds` để giảm dung lượng ngay?

**Đáp án:** **Không**. Cần đánh giá replication, lịch repair, compaction và nguy cơ zombie data. TTL không bảo đảm xóa vật lý ngay lập tức.

---

**Ghi nhớ:** `default_time_to_live` quyết định **TTL mặc định cho các cell được ghi mới**; `USING TTL N` trên `INSERT`/`UPDATE` **ghi đè chính sách mặc định** cho những cell được mutation tác động, trong đó `USING TTL 0` biểu diễn **không TTL**. TTL gắn với **phiên bản cell đang thắng**, được tính theo giây từ lần ghi; đổi default TTL không tự viết lại dữ liệu cũ. Hãy kiểm tra `ttl()` cùng `writetime()`, tính đến replication, compaction, tombstone và repair khi áp dụng chính sách TTL ở quy mô lớn.
