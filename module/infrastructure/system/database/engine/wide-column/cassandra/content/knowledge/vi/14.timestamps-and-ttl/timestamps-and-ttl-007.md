# TTL cho dữ liệu ghi mới và thời điểm bắt đầu đếm trong Apache Cassandra

## 1. TTL giải quyết vấn đề gì?

Trong **Apache Cassandra**, cơ sở dữ liệu **wide-column phân tán**, một số dữ liệu chỉ có giá trị trong thời gian ngắn: mã xác thực, trạng thái thiết bị tạm thời, cache, thông báo chưa đọc hoặc phiên làm việc. Giữ chúng mãi sẽ làm tăng kích thước bảng và chi phí vận hành. Cassandra hỗ trợ **Time To Live (TTL)** để dữ liệu tự **hết hiệu lực sau một khoảng thời gian được khai báo**.

Ví dụ, một mã xác thực chỉ được sử dụng trong 5 phút:

```sql
INSERT INTO login_challenge_by_id (
    challenge_id, user_id, code_hash
)
VALUES (
    11111111-7777-4777-8777-111111111111,
    22222222-7777-4777-8777-222222222222,
    'example-hash-not-a-real-code'
)
USING TTL 300;
```

TTL `300` được tính bằng **giây**. Nếu mutation được Cassandra xử lý để ghi lúc khoảng `10:00:00`, các giá trị có TTL sẽ hết hiệu lực vào khoảng `10:05:00`. Giá trị hết hạn không còn được trả về như dữ liệu sống, dù các byte trên đĩa có thể chưa được compaction dọn ngay.

**Điểm quan trọng nhất của bài:** TTL của một cell mới bắt đầu tính khi **Cassandra thực hiện lần ghi tạo phiên bản cell đó**. Nó **không** bắt đầu từ lúc bảng được tạo, từ thời điểm ghi trong cột nghiệp vụ như `created_at`, hoặc từ mutation timestamp do ứng dụng cố tình đưa về quá khứ.

TTL đặc biệt hữu ích khi thiết kế bảng theo **truy vấn và vòng đời dữ liệu**. Tuy nhiên, cần phân biệt hiệu lực ở mức cell, trạng thái replica và thời điểm dọn vật lý để tránh kỳ vọng sai.

## 2. Khi nào đồng hồ TTL bắt đầu chạy?

Một câu `INSERT` hoặc `UPDATE` có `USING TTL N` tạo phiên bản dữ liệu có **khoảng sống N giây tính từ lần ghi được xử lý**. Cassandra lưu metadata hết hạn cùng dữ liệu. Trong cluster, đồng hồ phía server trên đường xử lý ghi tham gia việc xác định thời điểm hết hạn; vì vậy cần đồng bộ đồng hồ các node. Không xem thời gian client gửi request hay thời gian ứng dụng nhận phản hồi là mốc chính xác tuyệt đối của TTL.

Xét một lần ghi thành công với TTL 120 giây:

```text
Client gửi INSERT         Cassandra xử lý ghi              Đến hạn
      |                            |                           |
      |------ độ trễ mạng -------->|<------- 120 giây -------->|
      |                            |                           |
      |                    TTL bắt đầu đếm                Cell hết hiệu lực
      |                            |
      |                   ttl(column) ≈ 120
      |                            |
      |                    Sau khoảng 30 giây
      |                   ttl(column) ≈ 90
```

Giả sử Cassandra xử lý ghi lúc `12:00:00` theo thời gian mà hệ thống dùng để tính expiration:

| Mốc quan sát | Cell còn sống? | `ttl(column)` ước lượng |
|---|---|---|
| `12:00:00`, ngay sau ghi | Có | Gần `120` giây |
| `12:00:30` | Có | Gần `90` giây |
| `12:01:59` | Có thể còn, tùy làm tròn và thời điểm đọc | Gần `0–1` giây |
| Từ khoảng `12:02:00` | Không còn là cell sống | Không còn TTL của giá trị sống để quan sát |

Các giá trị TTL đọc được có thể chênh một vài giây vì quá trình gửi request, thời điểm lấy mẫu, độ phân giải theo **giây**, và đồng hồ node. Khi viết bài kiểm thử, nên kiểm tra **khoảng hợp lý** thay vì so sánh tuyệt đối với `120`.

**Không có bộ đếm nền chạy cho từng cell.** Cassandra lưu metadata thời hạn và tính trạng thái còn sống khi cần đọc/xử lý dữ liệu. Đến hạn không có nghĩa có một tác vụ ngay lập tức xóa byte khỏi mọi SSTable.

## 3. TTL, mutation timestamp và cột thời gian là ba thứ khác nhau

Chương **Timestamp và TTL** có ba khái niệm dễ nhầm:

| Thành phần | Đơn vị | Vai trò | Có quyết định lúc TTL bắt đầu đếm? |
|---|---|---|---|
| `USING TTL 120` | Giây | Đặt thời gian sống cho cell được ghi | **Có:** cấp thời hạn tương đối từ lúc ghi |
| `USING TIMESTAMP 1700000000000000` | Micro giây từ Unix epoch | Metadata hòa giải phiên bản theo **last-write-wins** | **Không:** không biến TTL 120 thành “120 giây kể từ năm 2023” |
| Cột `created_at timestamp` | Mili giây từ Unix epoch | Lưu thời gian nghiệp vụ | **Không:** chỉ là dữ liệu ứng dụng |
| `writetime(col)` | Micro giây | Đọc write timestamp của cell sống | Chỉ để quan sát; không phải TTL còn lại |
| `ttl(col)` | Giây còn lại | Đọc phần thời gian sống chưa hết | Không cung cấp trực tiếp thời điểm tuyệt đối ban đầu |

Ví dụ, khi **import dữ liệu lịch sử** với một write timestamp quá khứ nhưng đặt TTL 120 giây, cell mới ghi vẫn được tính thời hạn **từ lần import này**. `USING TIMESTAMP` chọn vị trí của mutation trong quy tắc LWW; TTL điều khiển tuổi thọ phiên bản cell được ghi.

Điều đó cũng giải thích vì sao **một mutation có timestamp cao nhưng được ghi trước không nhất thiết hết hạn muộn hơn mutation có timestamp thấp được xử lý sau**. Đừng suy thời điểm hết hạn từ giá trị `writetime()`.

## 4. CQL cơ bản: TTL khi `INSERT` dữ liệu mới

Chạy trong một **keyspace thử nghiệm** đã được tạo và chọn bằng `USE <keyspace>;`. Dùng UUID chưa từng ghi để kết quả không bị ảnh hưởng bởi tombstone hoặc timestamp của lần chạy trước.

### Bước 1 — Tạo bảng minh họa

```sql
CREATE TABLE IF NOT EXISTS login_challenge_by_id (
    challenge_id uuid PRIMARY KEY,
    user_id uuid,
    code_hash text,
    created_at timestamp
);
```

Thiết kế này phục vụ truy vấn **một challenge theo ID**. Với ứng dụng thật, chỉ lưu mã băm/giá trị xác thực thích hợp và cân nhắc thêm các bảng phục vụ truy vấn theo người dùng hoặc thời gian; tránh xem TTL là cơ chế bảo mật duy nhất.

### Bước 2 — Ghi tất cả dữ liệu mới với TTL 300 giây

```sql
INSERT INTO login_challenge_by_id (
    challenge_id, user_id, code_hash, created_at
)
VALUES (
    11111111-7777-4777-8777-111111111111,
    22222222-7777-4777-8777-222222222222,
    'example-hash-not-a-real-code',
    '2025-01-01T00:00:00Z'
)
USING TTL 300;

SELECT challenge_id, user_id, code_hash,
       ttl(code_hash) AS code_remaining_s,
       writetime(code_hash) AS code_write_us,
       created_at, ttl(created_at) AS created_at_remaining_s
FROM login_challenge_by_id
WHERE challenge_id = 11111111-7777-4777-8777-111111111111;
```

Ngay sau ghi:

- `code_hash` và `created_at` là những **cell được ghi**; `ttl(code_hash)` và `ttl(created_at)` gần 300 giây.
- `created_at` là **ngày 01/01/2025**, cố ý nằm rất xa trong quá khứ; nó **không khiến TTL hết hạn ngay**. Cả hai cell vẫn sống khoảng 300 giây kể từ lần `INSERT` hiện tại.
- `writetime(code_hash)` là mutation timestamp (micro giây) được driver/coordinator cấp khi câu lệnh không có `USING TIMESTAMP`.
- `challenge_id` là **primary key**, không thể dùng `ttl(challenge_id)` hay `writetime(challenge_id)` như cột dữ liệu thường.

Khi tất cả cell có ý nghĩa của row hết hạn, bản ghi không còn dữ liệu sống cho lần đọc. Khóa vẫn có thể xuất hiện trong cấu trúc lưu trữ ở dạng metadata/tombstone cho đến khi được xử lý dọn dẹp an toàn.

### Bước 3 — Quan sát sau khi hết hạn

Chạy lại câu `SELECT` sau khi hết TTL sẽ không còn trả về cell `code_hash` và `created_at` như giá trị sống. Tùy dữ liệu còn lại của row và cách client hiển thị, có thể thấy không còn row hoặc các biểu thức dữ liệu nhận `null`. **Không kỳ vọng `ttl(code_hash)` trả số âm để báo “quá hạn”**.

> **Thực hành:** Để quan sát nhanh mà không phải dùng TTL 300 giây, hãy tạo **một UUID mới** và thay `USING TTL 300` thành `USING TTL 10`. Đọc ngay rồi đọc lại sau khi hết 10 giây. Đừng ghi đè cùng khóa cũ với timestamp thấp hơn vì kết quả có thể bị LWW che.

## 5. Ghi mới với `USING TIMESTAMP` và TTL: kiểm chứng mốc bắt đầu

Đây là thí nghiệm quan trọng nhất để phân biệt **thời gian phiên bản** với **thời gian hết hạn**.

```sql
-- UUID riêng cho thí nghiệm, chưa từng có dữ liệu trước đó.
INSERT INTO login_challenge_by_id (challenge_id, code_hash)
VALUES (
    33333333-7777-4777-8777-333333333333,
    'historical-write-timestamp'
)
USING TTL 180 AND TIMESTAMP 1700000000000000;

SELECT code_hash,
       writetime(code_hash) AS write_us,
       ttl(code_hash) AS remaining_s
FROM login_challenge_by_id
WHERE challenge_id = 33333333-7777-4777-8777-333333333333;
```

Nếu chưa có phiên bản cạnh tranh:

| Trường | Giá trị mong đợi |
|---|---|
| `code_hash` | `historical-write-timestamp` |
| `write_us` | `1700000000000000`, tương ứng mốc năm 2023 |
| `remaining_s` | Gần **180 giây**, không phải số âm hoặc `null` chỉ vì write timestamp cũ |

**Lý do:** TTL được xác định khi Cassandra xử lý **lần ghi hiện tại**; con số `1700000000000000` chỉ là timestamp dùng để phân xử phiên bản. Dù vậy, một write timestamp cũ có thể **thua** nếu khóa đã có dữ liệu hoặc tombstone với timestamp lớn hơn; khi đó thí nghiệm không quan sát được phiên bản mới. Luôn dùng khóa mới.

Theo cùng logic, cố ý gán mutation timestamp rất xa tương lai **không phải** cách hợp lệ để “kéo dài TTL”. Nó còn có thể khiến các lần cập nhật bình thường thua theo last-write-wins. Không dùng các timestamp thử nghiệm bất thường cho dữ liệu production.

## 6. TTL được áp dụng cho cell nào?

Cassandra gắn TTL với **những cell dữ liệu được mutation ghi**, không mặc định cấp một bộ đếm duy nhất cho toàn hàng.

| Cách ghi | Những cell chịu TTL |
|---|---|
| `INSERT` nhiều cột thường với `USING TTL 60` | Các cell dữ liệu được ghi trong `INSERT` |
| `UPDATE ... USING TTL 60 SET state = ...` | Cell `state` được cập nhật |
| `UPDATE ... SET note = ...` không gán TTL, bảng không có default TTL | Cell `note` mới không có TTL |
| `CREATE TABLE ... WITH default_time_to_live = 900` | Các cell ghi mới chịu TTL mặc định nếu không có TTL riêng |
| Primary key | Không dùng `ttl(pk)`; khóa phục vụ định danh/định tuyến dữ liệu |

Ví dụ một row vừa có cell sống lâu, vừa có cell hết hạn:

```sql
CREATE TABLE IF NOT EXISTS device_status_by_id (
    device_id text PRIMARY KEY,
    device_name text,
    latest_state text,
    last_notice text
);

INSERT INTO device_status_by_id (device_id, device_name)
VALUES ('sensor-ttl-01', 'Boiler A');

UPDATE device_status_by_id
USING TTL 45
SET latest_state = 'WARN'
WHERE device_id = 'sensor-ttl-01';

SELECT device_name, ttl(device_name),
       latest_state, ttl(latest_state),
       writetime(latest_state)
FROM device_status_by_id
WHERE device_id = 'sensor-ttl-01';
```

Ngay sau cập nhật, `ttl(device_name)` là `null` và `ttl(latest_state)` gần 45 giây. Sau khoảng 45 giây, `latest_state` sẽ hết hiệu lực nhưng `device_name = 'Boiler A'` vẫn tồn tại.

Điều này quan trọng với ứng dụng Java: **một hàng có thể được đọc ra dù một số cột đã hết TTL**, và từng thuộc tính cần được hiểu như giá trị có thể `null`. Đừng coi TTL của một cột là “ngày hết hạn” của toàn đối tượng nghiệp vụ nếu bảng chứa nhiều cột có vòng đời khác nhau.

## 7. `UPDATE` có làm TTL đếm lại từ đầu không?

**Có, nếu mutation mới thắng và được ghi như một phiên bản cell mới.** Khi cập nhật lại chính cell đang có TTL, metadata của phiên bản mới (write timestamp, TTL và thời điểm hết hạn) được xác định theo lần ghi mới.

Thử trên một khóa riêng:

```sql
INSERT INTO device_status_by_id (device_id, latest_state)
VALUES ('sensor-renew-01', 'STARTING')
USING TTL 60;

SELECT latest_state, writetime(latest_state), ttl(latest_state)
FROM device_status_by_id
WHERE device_id = 'sensor-renew-01';

-- Thực hiện lần cập nhật này trước khi TTL 60 giây hết.
UPDATE device_status_by_id
USING TTL 300
SET latest_state = 'RUNNING'
WHERE device_id = 'sensor-renew-01';

SELECT latest_state, writetime(latest_state), ttl(latest_state)
FROM device_status_by_id
WHERE device_id = 'sensor-renew-01';
```

Nếu phiên bản mới thắng theo timestamp, `latest_state` chuyển sang `RUNNING`, TTL bắt đầu lại **gần 300 giây từ lần UPDATE**. Nó **không** bằng “số giây còn lại của bản cũ cộng 300”.

### Ghi lại mà không đặt TTL

Với bảng có `default_time_to_live = 0` (mặc định không có TTL), câu:

```sql
UPDATE device_status_by_id
SET latest_state = 'RUNNING_STABLE'
WHERE device_id = 'sensor-renew-01';

SELECT latest_state, ttl(latest_state)
FROM device_status_by_id
WHERE device_id = 'sensor-renew-01';
```

có thể tạo phiên bản mới **không TTL** nếu mutation thắng. Khi đó `ttl(latest_state) = null` dù phiên bản trước đã có TTL. **TTL không tự di truyền từ cell cũ**. Ngược lại, nếu bảng có **default TTL khác 0**, lần ghi không chỉ định `USING TTL` vẫn có thể nhận TTL mặc định.

Một lần ghi cũ hơn về **mutation timestamp** có thể không thay thế được phiên bản mới dù được gửi sau, nên cũng không “gia hạn TTL” như ứng dụng kỳ vọng. Xem `writetime()` cùng `ttl()` sau cập nhật để hiểu phiên bản nào đang sống.

## 8. TTL mặc định của bảng và thứ tự ưu tiên

Khi dữ liệu của bảng có vòng đời đồng nhất, thay vì gõ `USING TTL` trong mọi câu ghi, có thể cấu hình **`default_time_to_live`**:

```sql
CREATE TABLE IF NOT EXISTS transient_message_by_id (
    message_id uuid PRIMARY KEY,
    content text,
    source text
) WITH default_time_to_live = 900;
```

Một câu ghi thông thường:

```sql
INSERT INTO transient_message_by_id (message_id, content, source)
VALUES (
    44444444-7777-4777-8777-444444444444,
    'Temporary notification',
    'system'
);

SELECT content, ttl(content), source, ttl(source)
FROM transient_message_by_id
WHERE message_id = 44444444-7777-4777-8777-444444444444;
```

Hai cell dữ liệu mới thường có TTL gần **900 giây**. Nếu câu ghi có TTL riêng:

```sql
INSERT INTO transient_message_by_id (message_id, content, source)
VALUES (
    55555555-7777-4777-8777-555555555555,
    'Short notification',
    'system'
)
USING TTL 120;
```

TTL **120 giây của câu ghi** được dùng cho các cell được ghi, thay cho TTL mặc định 900 giây. Lần đếm bắt đầu từ **lần ghi thứ hai**, không phải từ khi bảng được `CREATE`.

| Tình huống | TTL áp dụng cho cell mới |
|---|---|
| Bảng không đặt TTL, câu ghi không `USING TTL` | Không có TTL |
| Bảng `default_time_to_live = 900`, ghi không `USING TTL` | Theo mặc định: 900 giây |
| Bảng `default_time_to_live = 900`, ghi `USING TTL 120` | Theo câu ghi: 120 giây |
| Cập nhật một cell trên bảng có TTL mặc định | Cell cập nhật nhận TTL theo chính sách của mutation mới |

**Không tự sửa `default_time_to_live` của một bảng production để thử nghiệm:** thay đổi chính sách mặc định ảnh hưởng các lần ghi mới và có thể khiến hành vi hết hạn khác mong đợi. Với dữ liệu có vòng đời đa dạng, cân nhắc tách bảng theo kiểu truy vấn và vòng đời.

## 9. Hết TTL có đồng nghĩa xóa ngay trên đĩa?

**Không.** TTL quyết định thời điểm một cell **không còn được coi là dữ liệu sống**. Sau thời hạn, Cassandra xử lý cell như dữ liệu đã hết hạn và dùng cơ chế tombstone/metadata xóa để bảo vệ tính nhất quán giữa replica.

```text
      Ghi cell mới             Hết TTL            Dọn vật lý an toàn
           |                      |                        |
           v                      v                        v
        Dữ liệu sống       Cell hết hiệu lực        Compaction có thể
        ttl() giảm         không trả về như live    loại bỏ dữ liệu/tombstone
                                |
                                +-- Cần xét replica và repair
                                    trước khi dọn tombstone
```

Vì sao không thể xóa vật lý ngay? Với replication factor `RF = 3`, một replica có thể tạm thời không nhận đủ mutation hoặc không sẵn sàng. Khi node cũ quay lại, dữ liệu đã hết hiệu lực không được phép “sống lại” chỉ vì replica ấy có bản ghi cũ hơn. **Tombstone** giúp che các phiên bản cũ trong giai đoạn hòa giải.

**Compaction** là nơi nhiều dữ liệu hết hạn/tombstone có thể được dọn khi điều kiện an toàn cho phép. **Repair** giúp đồng bộ replica; các thiết lập về thời gian giữ tombstone, chính sách repair và sự sẵn sàng của node ảnh hưởng đến rủi ro **zombie data**. Vì vậy:

- Không xem TTL như một lệnh “xóa byte ngay lập tức”.
- Không giảm `gc_grace_seconds` hoặc bỏ repair chỉ vì muốn reclaim dung lượng nhanh.
- Theo dõi số lượng tombstone, tần suất compaction, dung lượng đĩa và latency đọc ở bảng ghi nhiều dữ liệu TTL.

TTL hỗ trợ quản lý vòng đời dữ liệu nhưng **không tự thực thi quy định bảo mật/xóa vật lý ngay**. Các yêu cầu xóa dữ liệu nhạy cảm cần quy trình lưu trữ, sao lưu và quản trị riêng.

## 10. TTL và replication: thời điểm quan sát có khác nhau không?

Cassandra là hệ thống phân tán, nên dữ liệu có thể đến các replica không đồng thời. Mức nhất quán **ONE, QUORUM, ALL** quyết định số replica cần đáp ứng yêu cầu đọc/ghi, nhưng **không định nghĩa lại TTL là bao nhiêu giây**.

Giả sử một mutation có TTL 60 giây được điều phối cho ba replica:

- Request ghi với `CL = ONE` có thể hoàn tất trước khi cả ba replica đã hội tụ.
- Một lần đọc sát thời điểm ghi ở mức yếu có thể nhìn thấy phiên bản khác do replica chưa cập nhật.
- Khi TTL sắp hết, lệch đồng hồ giữa node có thể làm việc quan sát thời điểm hết hạn có sai lệch.
- Hòa giải phiên bản vẫn dùng **mutation timestamp**, trong khi TTL/expiration metadata xác định liệu cell đang sống hay đã hết hạn.

Đừng suy rằng `ttl(column) = 45` trên một lần đọc có nghĩa **mọi replica** đang đồng bộ tuyệt đối còn 45 giây. Đây là giá trị tính cho dữ liệu được lần đọc đó quan sát trong bối cảnh đồng hồ hệ thống và thời điểm xử lý.

**Clock skew** gây lỗi cả ở việc cấp mutation timestamp lẫn khi tính/quan sát expiration. Cần đồng bộ giờ giữa node Cassandra và host chạy driver bằng NTP/chrony hoặc dịch vụ tương đương. Một `USING TIMESTAMP` trong tương lai **không phải** cách kéo dài TTL; nó có thể khiến những lần cập nhật khác thua theo LWW.

## 11. Thực hành Java: ghi challenge TTL bằng prepared statement

Ứng dụng Java kết nối Cassandra thường dùng **Apache/DataStax Cassandra Java Driver 4.x**. CQL cho phép bind TTL như một tham số để tạo challenge với thời hạn được quy định tại runtime:

```java
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class LoginChallengeRepository {
    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement select;

    public LoginChallengeRepository(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO login_challenge_by_id " +
            "(challenge_id, user_id, code_hash, created_at) " +
            "VALUES (?, ?, ?, ?) USING TTL ?"
        );
        this.select = session.prepare(
            "SELECT code_hash, ttl(code_hash) AS remaining_s " +
            "FROM login_challenge_by_id WHERE challenge_id = ?"
        );
    }

    public void create(
        UUID challengeId,
        UUID userId,
        String hashedCode,
        int ttlSeconds
    ) {
        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        // created_at là dữ liệu nghiệp vụ; TTL bắt đầu từ lần Cassandra ghi.
        session.execute(
            insert.bind(challengeId, userId, hashedCode, Instant.now(), ttlSeconds)
        );
    }

    public Integer remainingSeconds(UUID challengeId) {
        Row row = session.execute(select.bind(challengeId)).one();
        if (row == null || row.isNull("remaining_s")) {
            return null;
        }
        return row.getInt("remaining_s");
    }
}
```

Ở đây `ttlSeconds` là **số giây**, không phải epoch milliseconds hay microseconds. `created_at` được bind bằng `Instant` vào cột CQL `timestamp` ở mức mili giây, **không** làm căn cứ bắt đầu TTL. Khi dùng cùng repository cho nhiều request, mỗi `INSERT` tạo mutation mới và có hạn hết hiệu lực riêng.

### Đừng dùng TTL như hạn chót pháp lý hoặc khóa nghiệp vụ tuyệt đối

Ví dụ một client đặt TTL 300 giây và nhận `remainingSeconds = 298`. Nếu ứng dụng yêu cầu “mã chỉ được dùng trước đúng 10:05:00 UTC”, nên lưu thêm **hạn chót nghiệp vụ `expires_at`** từ một nguồn thời gian đáng tin cậy và kiểm tra hạn khi xác thực; TTL dùng để dọn dữ liệu tự động. Điều này hữu ích vì thời điểm xử lý ghi có độ trễ và các host có thể sai lệch đồng hồ.

Với yêu cầu chống dùng lại challenge, cần thiết kế chuyển trạng thái/đánh dấu tiêu thụ có điều kiện hoặc điều phối riêng. TTL **không tạo ra transaction compare-and-set**, cũng không bảo đảm challenge chỉ được dùng một lần dưới nhiều request cạnh tranh.

## 12. Những trường hợp thường gây nhầm thời điểm bắt đầu đếm

| Tình huống | TTL bắt đầu từ đâu? | Điều cần lưu ý |
|---|---|---|
| `INSERT ... USING TTL 60` vào khóa mới | Lần `INSERT` được xử lý ghi | Không bắt đầu từ `CREATE TABLE` |
| `INSERT` với cột `created_at` là ngày cũ | Lần `INSERT` được xử lý ghi | `created_at` không điều khiển TTL |
| `INSERT ... USING TIMESTAMP <quá khứ> AND TTL 60` | Lần ghi hiện tại | Mutation timestamp có vai trò LWW riêng |
| `UPDATE ... USING TTL 120` trên cùng cell | Lần `UPDATE` mới **nếu phiên bản thắng** | TTL của phiên bản mới được đặt lại |
| Ghi cột khác trong cùng row | Theo lần ghi của cột đó | Không gia hạn TTL của cell chưa đụng tới |
| `default_time_to_live = 900` | Mỗi lần ghi dữ liệu mới nhận default TTL | Không bắt đầu khi bảng được tạo |
| Retry một mutation cũ với timestamp lớn hơn | Theo mutation thắng mới | Có thể vô tình kéo dài tuổi thọ hoặc ghi đè trạng thái |
| Dữ liệu hết TTL | Không còn cell sống | Dọn byte vật lý phụ thuộc compaction và điều kiện an toàn |

Một điểm cần phân biệt: **retry ở tầng client không nhất thiết được xem là “cùng một mutation” về metadata** nếu ứng dụng cấp timestamp hoặc TTL khác nhau trong mỗi lần thử. Với nghiệp vụ cần hạn hết hiệu lực tuyệt đối, đừng trông đợi các retry tự động bảo toàn chính xác mốc hết hạn; hãy quản lý `expires_at` hoặc chính sách phát lại ở tầng ứng dụng.

### Counter và primary key

Cassandra không dùng TTL trên **counter column** theo kiểu dữ liệu thường; counter có cơ chế cập nhật riêng. Primary key được dùng để định danh partition/row và không thể đọc TTL trực tiếp bằng `ttl(primary_key_column)`. Khi mọi cell dữ liệu sống của một row hết hạn, row có thể không còn được truy vấn như một bản ghi có dữ liệu.

## 13. Chẩn đoán dữ liệu hết hạn sớm hoặc muộn

Khi gặp báo cáo “bản ghi vừa được tạo nhưng đã biến mất” hoặc “TTL đặt 5 phút nhưng vẫn thấy dữ liệu”, hãy kiểm tra theo thứ tự:

| Bước | Kiểm tra | Vì sao |
|---|---|---|
| 1 | `SELECT value, ttl(value), writetime(value)` theo đúng partition key | Xác định cell còn sống, TTL còn lại và timestamp đang thắng |
| 2 | `INSERT/UPDATE` có `USING TTL` không? | TTL thực được khai báo theo giây |
| 3 | Bảng có `default_time_to_live` không? | Có thể tự cấp TTL dù câu ghi không có `USING TTL` |
| 4 | Mutation tác động những cột nào? | TTL theo cell, không mặc định cho toàn hàng |
| 5 | Có cập nhật/retry một cell sau đó không? | Phiên bản mới thắng có thể đặt lại TTL |
| 6 | Có `USING TIMESTAMP`/driver timestamp riêng không? | Timestamp cũ có thể thua bản đang sống hoặc tombstone |
| 7 | Đồng hồ các node và service có đồng bộ không? | Clock skew có thể ảnh hưởng expiration và phân xử |
| 8 | RF/CL, replica health, repair/compaction ra sao? | Phân biệt vấn đề replica với dữ liệu đã hết TTL |

Truy vấn thực hành:

```sql
SELECT challenge_id,
       code_hash,
       ttl(code_hash) AS remaining_s,
       writetime(code_hash) AS write_us,
       created_at,
       ttl(created_at) AS created_at_remaining_s
FROM login_challenge_by_id
WHERE challenge_id = 11111111-7777-4777-8777-111111111111;
```

**Cách đọc:** `write_us` cho biết timestamp dùng trong LWW (µs), `remaining_s` cho biết TTL còn lại (giây), còn `created_at` là thời gian nghiệp vụ (ms). `writetime()` và `ttl()` chỉ phản ánh phiên bản cell còn sống mà truy vấn quan sát, không liệt kê tombstone hoặc các phiên bản đã thua.

Không quét toàn bảng với `ALLOW FILTERING` chỉ để tìm bản ghi sắp hết TTL. Khi phải giám sát nhiều đối tượng, thiết kế bảng theo **truy vấn cần chạy**, lưu các event/thời điểm cần thiết ở tầng ứng dụng và dùng các công cụ vận hành Cassandra để theo dõi tombstone, repair, compaction.

## 14. Bài tập tự kiểm tra

**Câu 1.** Một row được ghi lúc 10:00 với `USING TTL 120`. Cột `created_at` trong row lại chứa thời gian 08:00. Cell sẽ hết hiệu lực lúc nào nếu đồng hồ và xử lý ghi bình thường?

**Đáp án:** Khoảng **10:02**, tức 120 giây sau lần Cassandra xử lý ghi. `created_at` không quyết định TTL.

**Câu 2.** `USING TIMESTAMP 1700000000000000 AND TTL 60` tạo một cell mới hôm nay. Có phải cell đã hết hạn từ năm 2023?

**Đáp án:** Không. Write timestamp cũ dùng cho LWW; TTL 60 giây tính từ **lần ghi hiện tại**. Với khóa đã có bản mới hơn, mutation có thể thua và không trở thành giá trị nhìn thấy.

**Câu 3.** Câu `INSERT` đặt TTL 90 giây cho `state` và `note`. Sau 30 giây, ứng dụng chỉ cập nhật `state` với TTL 120 giây. `note` có được gia hạn thành 120 giây không?

**Đáp án:** **Không.** `note` giữ thời hạn của lần ghi trước và sẽ hết hạn theo lịch riêng; `state` có TTL từ mutation mới nếu nó thắng.

**Câu 4.** Vì sao `ttl(column)` có thể là `null` ngay cả khi cell còn giá trị?

**Đáp án:** Vì cell hiện tại **không có TTL**, chẳng hạn bảng không có TTL mặc định và lần ghi mới không dùng `USING TTL`.

**Câu 5.** Bảng `default_time_to_live = 900`, nhưng một `INSERT` dùng `USING TTL 120`. TTL cho cell trong câu `INSERT` là bao nhiêu?

**Đáp án:** **120 giây**, vì TTL khai báo trong câu ghi được ưu tiên cho dữ liệu mà câu ghi đó tạo.

**Câu 6.** Sau khi TTL 120 giây hết, dung lượng SSTable có nhất thiết giảm ngay không?

**Đáp án:** **Không.** Cell hết hiệu lực về mặt đọc trước; dọn vật lý phụ thuộc compaction và điều kiện an toàn liên quan tombstone/replica/repair.

**Câu 7.** Có thể dùng chỉ `ttl(code_hash)` để chứng minh tuyệt đối một OTP chỉ được dùng đúng một lần không?

**Đáp án:** **Không.** TTL chỉ quản lý hạn sống của dữ liệu. Chống dùng lại cần kiểm tra và cập nhật trạng thái theo điều kiện hoặc một cơ chế tiêu thụ có điều phối.

**Câu 8.** Nếu `UPDATE` sử dụng timestamp thấp hơn phiên bản đang thắng, có thể bảo đảm TTL được reset không?

**Đáp án:** **Không.** Mutation timestamp thấp hơn có thể thua theo LWW, nên TTL nhìn thấy của cell vẫn thuộc phiên bản đang thắng.

---

**Ghi nhớ:** TTL của Cassandra được tính bằng **giây kể từ khi phiên bản dữ liệu được ghi**, áp dụng cho **các cell mà mutation tác động**. Nó độc lập với cột thời gian nghiệp vụ và mutation timestamp dùng cho LWW. `ttl(column)` cho biết thời gian còn lại, `writetime(column)` cho biết write timestamp; hai hàm phải được đọc đúng ngữ cảnh. Khi TTL hết, dữ liệu mất hiệu lực trước khi được dọn vật lý, nên cần chú ý replication, tombstone, compaction và repair.
