# Retry với timestamp/TTL và nguy cơ thay đổi kết quả nghiệp vụ

## 1. Vì sao “thử lại cùng một lệnh” chưa chắc có cùng ý nghĩa?

Trong **Apache Cassandra**, cơ sở dữ liệu **wide-column phân tán**, một ứng dụng Java có thể gửi mutation tới coordinator, coordinator chuyển tiếp tới các replica theo **replication factor (RF)** và **consistency level (CL)**. Nếu client gặp timeout, mất kết nối hoặc coordinator trả lỗi, ứng dụng thường muốn **retry** để hoàn tất tác vụ.

Nhưng có một khác biệt quan trọng:

> **Retry không đồng nghĩa với việc mutation trước chắc chắn thất bại.** Lần ghi đầu có thể đã được một số replica chấp nhận, hoặc đã đủ điều kiện ghi nhưng phản hồi bị mất. Phát lại có thể tạo thêm một phiên bản cell với **timestamp mới**, **TTL mới** hoặc **hiệu ứng nghiệp vụ mới**.

Với Cassandra, hai loại metadata cần quan sát là:

- **Mutation timestamp** (micro giây từ Unix epoch): dùng để phân xử phiên bản của cùng một cell theo **last-write-wins (LWW)**.
- **TTL** (giây): quyết định khoảng thời gian một phiên bản cell còn sống, được tính khi phiên bản đó được ghi, không phải “hạn cố định” tự bảo toàn qua mọi retry.

Ví dụ một dịch vụ xử lý trạng thái đơn hàng:

1. `E1`: cập nhật `state = 'PENDING'` được gửi lúc 10:00 nhưng timeout.
2. `E2`: cập nhật `state = 'PAID'` được gửi lúc 10:01 và hoàn tất.
3. Ứng dụng **tạo lại lệnh E1** lúc 10:02 với timestamp mới lớn hơn E2.

Nếu cả hai đụng cùng cell và E1 retry có timestamp lớn nhất, Cassandra có thể hiển thị lại **`PENDING`**, dù đó là sự kiện nghiệp vụ **cũ hơn**. Vấn đề không nằm ở tính đúng đắn của LWW: hệ thống đang thực hiện quy tắc so sánh timestamp đã được cung cấp, chứ không biết thứ tự nghiệp vụ.

Mục tiêu bài này là phân biệt **retry ở giao thức/driver** với **phát lại thao tác nghiệp vụ**, xây dựng ví dụ CQL/Java và thiết kế để không vô tình đổi thứ tự sự kiện hoặc kéo dài dữ liệu có TTL.

## 2. Timeout ghi là “không biết kết quả”, không phải “chưa ghi”

Một request ghi Cassandra đi qua nhiều bước. Hình sau minh họa với RF = 3; số replica cần xác nhận thực tế phụ thuộc CL:

```text
  Java client             Coordinator             Replica A/B/C
      |                         |                        |
      +---- UPDATE ------------>|                        |
      |                         +------ mutation ------->|
      |                         |<----- một số ACK ------+
      |                         |
      |      (mất mạng hoặc client timeout)
      X<------ phản hồi? -------|
      |
      +---- RETRY? ------------>|    Lần 1 có thể đã ghi
                                |    thành công một phần
                                |    hoặc đủ CL.
```

Một vài trạng thái cần tách biệt:

| Tình huống | Điều client biết | Nguy cơ khi phát lại |
|---|---|---|
| Chưa gửi request ra mạng và biết chắc chưa thực thi | Chưa có hiệu ứng server | Có thể gửi lần đầu |
| Client timeout sau khi request đã gửi | **Không chắc** số replica đã áp dụng | Dữ liệu có thể đã tồn tại |
| Server báo write timeout | Không đạt điều kiện xác nhận đúng hạn | Một số replica vẫn có thể đã ghi |
| Request đạt CL và ACK tới client | Ghi được xác nhận theo CL | Chưa bảo đảm phiên bản sẽ thắng nếu có timestamp lớn hơn |
| LWT timeout/unknown | Không chắc điều kiện đã được áp dụng | Retry thiếu kiểm tra có thể chuyển trạng thái lần nữa |

**Không suy ra “write timeout = rollback”.** Cassandra không cung cấp transaction rollback thông thường cho một write đã đến replica. Khi điều kiện nghiệp vụ quan trọng, cần chiến lược **reconcile sau timeout** bằng khóa nghiệp vụ, event ID/version và mức nhất quán thích hợp.

## 3. Ba kiểu retry có thể tạo ra ba kết quả khác nhau

Không phải mọi “retry” có chung semantics:

| Cách thử lại | Cái gì có thể thay đổi? | Điều cần kiểm soát |
|---|---|---|
| **Driver retry cùng execution** theo chính sách | Coordinator/đường mạng; timestamp/expiration thực tế tùy cách driver/server xử lý và phiên bản | Tính idempotent, retry policy, logs, timeout |
| **Ứng dụng gọi lại cùng prepared statement** | Statement mới hoặc timestamp generator có thể tạo mutation timestamp mới; TTL tương đối có thể được tính lại | Lưu context của cùng sự kiện, không tự cấp thứ tự mới |
| **Phát lại sự kiện từ queue/DLQ** sau nhiều phút/giờ | Độ trễ lớn, TTL ban đầu hết hoặc event đã lỗi thời; event mới đã xử lý | Event ID, business version, deadline tuyệt đối, điều kiện chuyển trạng thái |

Ví dụ lỗi thường gặp:

```text
E1: ORDER_CREATED  -> timestamp 100  -> status = PENDING
E2: PAYMENT_DONE   -> timestamp 200  -> status = PAID
retry E1           -> timestamp 300  -> status = PENDING

Trạng thái sau hòa giải: PENDING (timestamp 300),
nhưng thứ tự nghiệp vụ đúng là E1 trước E2.
```

**Timestamp lớn hơn không nhất thiết là sự kiện mới hơn.** Nếu các service độc lập sử dụng đồng hồ riêng hoặc driver timestamp generator riêng, đồng hồ lệch càng làm thứ tự LWW khác thứ tự nghiệp vụ. Không sửa vấn đề bằng cách tăng CL lên `QUORUM` hay `ALL`: CL quyết định yêu cầu replica, không định nghĩa thứ tự trạng thái.

## 4. Thực hành CQL: retry sự kiện cũ làm lùi trạng thái

Chỉ chạy trong **keyspace thử nghiệm** đã chọn bằng `USE <keyspace>;`. Các UUID phải chưa từng dùng; mọi timestamp cố định trong ví dụ là **micro giây** để minh họa, không dùng làm “timestamp chuẩn” ở production.

### 4.1. Tạo bảng theo truy vấn trạng thái hiện tại

```sql
CREATE TABLE IF NOT EXISTS retry_order_state_by_id (
    order_id uuid PRIMARY KEY,
    state text,
    last_event_id text,
    last_source text
);
```

Bảng tối ưu truy vấn “cho biết trạng thái hiện tại của `order_id`”. Đây là một **latest-state table**; nếu cần chống lùi trạng thái tuyệt đối, phải thêm cơ chế điều phối/điều kiện, không chỉ dựa trên cấu trúc trên.

### 4.2. E1 và E2 được xử lý đúng thứ tự

```sql
INSERT INTO retry_order_state_by_id (
    order_id, state, last_event_id, last_source
)
VALUES (
    11111111-1313-4131-8131-111111111111,
    'PENDING', 'E1', 'checkout'
)
USING TIMESTAMP 1700000000001000;

UPDATE retry_order_state_by_id
USING TIMESTAMP 1700000000002000
SET state = 'PAID',
    last_event_id = 'E2',
    last_source = 'payment'
WHERE order_id = 11111111-1313-4131-8131-111111111111;

SELECT state, writetime(state),
       last_event_id, writetime(last_event_id)
FROM retry_order_state_by_id
WHERE order_id = 11111111-1313-4131-8131-111111111111;
```

Kết quả: `state = 'PAID'` và `writetime(state) = 1700000000002000`, bởi E2 có timestamp lớn hơn E1.

### 4.3. Phát lại E1 bằng timestamp mới

```sql
-- Lỗi ứng dụng: retry E1 được cấp timestamp CAO HƠN E2.
UPDATE retry_order_state_by_id
USING TIMESTAMP 1700000000003000
SET state = 'PENDING',
    last_event_id = 'E1-retry',
    last_source = 'checkout'
WHERE order_id = 11111111-1313-4131-8131-111111111111;

SELECT state, writetime(state), last_event_id
FROM retry_order_state_by_id
WHERE order_id = 11111111-1313-4131-8131-111111111111;
```

Kết quả đáng chú ý: `state = 'PENDING'` và `writetime(state) = 1700000000003000`. Mutation được áp dụng **đúng quy tắc LWW**, nhưng giá trị lại **sai so với luồng nghiệp vụ** đã hoàn tất thanh toán.

### 4.4. Khi retry giữ timestamp ban đầu

Trên một khóa khác, mô phỏng E1 replay với **timestamp E1 giữ nguyên**:

```sql
INSERT INTO retry_order_state_by_id (order_id, state, last_event_id)
VALUES (
    22222222-1313-4131-8131-222222222222,
    'PENDING', 'E1'
)
USING TIMESTAMP 1700000000001000;

UPDATE retry_order_state_by_id
USING TIMESTAMP 1700000000002000
SET state = 'PAID', last_event_id = 'E2'
WHERE order_id = 22222222-1313-4131-8131-222222222222;

-- Replay E1 nhưng dùng lại write timestamp của E1, thấp hơn E2.
UPDATE retry_order_state_by_id
USING TIMESTAMP 1700000000001000
SET state = 'PENDING', last_event_id = 'E1'
WHERE order_id = 22222222-1313-4131-8131-222222222222;

SELECT state, writetime(state), last_event_id
FROM retry_order_state_by_id
WHERE order_id = 22222222-1313-4131-8131-222222222222;
```

Kết quả: `PAID@1700000000002000` tiếp tục thắng. Đây là **một cách giảm rủi ro replay cũ đảo thứ tự**, nhưng **không đủ thành quy tắc tổng quát**: phải bảo đảm timestamp thực sự đại diện cho thứ tự nghiệp vụ, xử lý clock skew, trùng timestamp, tombstone và các tác nhân ghi khác.

## 5. Retry TTL: cùng số giây có thể tạo hạn hết hiệu lực khác

Với TTL, điều cần phân biệt là **thời hạn tương đối** và **deadline tuyệt đối**.

Nếu yêu cầu nghiệp vụ là “token sống 5 phút kể từ lần phát hành đầu tiên”:

```text
12:00  phát hành token -> ghi TTL 300    Hạn nghiệp vụ: 12:05
12:02  ứng dụng tạo ghi mới cùng token
       với TTL 300, timestamp mới thắng
                                      Hạn TTL mới: khoảng 12:07
12:05  token đáng lẽ không được dùng nữa
       nhưng cell mới có thể vẫn còn sống
```

Lỗi không nằm ở phép tính `300 giây`: đó là hành vi **đặt một TTL tương đối mới từ lần ghi mới**. Khi request replay được xây dựng lại, Cassandra có thể xác lập expiration mới. Nếu cần hạn nghiệp vụ không thay đổi, phải lưu/điều phối hạn đó ở tầng ứng dụng.

### 5.1. Thực hành CQL trên cell TTL

```sql
CREATE TABLE IF NOT EXISTS retry_token_by_id (
    token_id uuid PRIMARY KEY,
    expires_at timestamp,
    token_hash text
);

-- expires_at: mốc nghiệp vụ, lưu riêng và không TTL trong bảng thử.
INSERT INTO retry_token_by_id (token_id, expires_at)
VALUES (
    33333333-1313-4131-8131-333333333333,
    '2030-01-01T12:05:00Z'
);

-- Token sống 300 giây từ lần ghi này.
UPDATE retry_token_by_id
USING TTL 300
SET token_hash = 'example-hash-not-a-token'
WHERE token_id = 33333333-1313-4131-8131-333333333333;

SELECT token_hash, ttl(token_hash) AS remaining_s,
       writetime(token_hash) AS write_us, expires_at
FROM retry_token_by_id
WHERE token_id = 33333333-1313-4131-8131-333333333333;
```

Trường `expires_at` trong ví dụ chỉ là mốc **minh họa độc lập**; trong ứng dụng thực, phải tính từ **thời điểm phát hành đáng tin cậy**, không hard-code năm 2030. Lần ghi `token_hash` mới với `USING TTL 300` có thể khiến `ttl(token_hash)` gần 300 giây dù `expires_at` không đổi. Cần dùng `expires_at` để đánh giá token đã quá hạn nghiệp vụ hay chưa.

Giả lập ứng dụng chủ động tạo lại mutation sau đó:

```sql
-- Thực hiện trên khóa thử đang còn sống, sau khi đã đợi một khoảng.
UPDATE retry_token_by_id
USING TTL 300
SET token_hash = 'example-hash-not-a-token'
WHERE token_id = 33333333-1313-4131-8131-333333333333;

SELECT token_hash, ttl(token_hash), writetime(token_hash), expires_at
FROM retry_token_by_id
WHERE token_id = 33333333-1313-4131-8131-333333333333;
```

Nếu lần ghi mới thắng theo mutation timestamp, TTL còn lại thường **quay về gần 300 giây**, kể cả khi chuỗi `token_hash` không đổi. Đây là **rủi ro làm mới TTL qua một mutation mới**; không phải tất cả retry nội bộ của driver đều nhất thiết làm điều này.

### 5.2. Retry với cùng mutation timestamp thì sao?

Nếu ứng dụng dùng lại **cùng timestamp** cho lệnh có TTL, vẫn không được mặc định rằng **hạn hết hiệu lực chắc chắn được giữ nguyên**. Expiration metadata phụ thuộc cách xử lý ghi và đường retry; xung đột cùng timestamp còn liên quan quy tắc tie-break cell. Một statement có cùng value, timestamp và TTL **không tự mang một `expires_at` tuyệt đối bất biến**.

Vì vậy, khi tính idempotency cho TTL, hãy phân biệt:

- **Idempotent về giá trị**: gửi lại cùng `token_hash` vẫn cho ra cùng chuỗi.
- **Idempotent về version**: không tạo timestamp mới làm một event cũ thắng.
- **Idempotent về thời hạn**: không vô tình dời deadline cho cùng đối tượng.
- **Idempotent về nghiệp vụ**: không phát token mới, không thanh toán/ghi sổ hai lần, không đảo trạng thái.

Một đường retry chỉ an toàn khi thỏa **đúng các bất biến mà nghiệp vụ yêu cầu**, không phải chỉ nhìn thấy giá trị giống nhau sau `SELECT`.

## 6. `USING TIMESTAMP`, driver generator và coordinator trong một lần thử lại

Mutation timestamp có thể được cấp qua nhiều đường:

1. CQL `USING TIMESTAMP <epoch_micros>` do ứng dụng đặt rõ.
2. Statement timestamp qua Java Driver 4.x, ví dụ `BoundStatement.setQueryTimestamp(long)`.
3. Timestamp generator của driver, nếu client được cấu hình cấp timestamp.
4. Coordinator của Cassandra khi request không mang timestamp phía client.

| Cách retry | Đặc điểm cần chú ý |
|---|---|
| Phát lại CQL có `USING TIMESTAMP 1700000000001000` cố định | Timestamp được yêu cầu giữ nguyên; **TTL và nghiệp vụ vẫn cần đánh giá riêng** |
| Tạo statement mới rồi gọi `setQueryTimestamp(nowMicros)` | Một event cũ có thể nhận timestamp mới lớn hơn event sau |
| Sử dụng timestamp generator của driver | Tính tăng đơn điệu trong một generator không bảo đảm thứ tự giữa các host hoặc service |
| Để coordinator cấp timestamp | Các coordinator có đồng hồ khác nhau; khi retry qua node khác có thể đổi thứ tự LWW |

Đừng giả định “retry luôn tự sinh timestamp mới”, cũng đừng giả định “driver retry luôn giữ nguyên timestamp”: phải phân biệt **retry cùng execution** và **ứng dụng xây lệnh mới**, cấu hình generator, phiên bản driver và đường request thực tế. Khi debug, thu thập đủ thông tin để biết mutation nào đã mang timestamp nào.

**Clock skew** là một nguyên nhân làm tình huống xấu hơn: máy client có đồng hồ chạy nhanh tạo future timestamp, khiến các cập nhật hợp lệ về sau không thắng. Cần đồng bộ giờ host ứng dụng và Cassandra node bằng NTP/chrony hoặc dịch vụ tương đương.

## 7. “Idempotent” của driver không tự biến nghiệp vụ thành an toàn

Ở tầng database, một thao tác thường được gọi là **idempotent** nếu lặp lại nó với cùng ý nghĩa không tạo kết quả cuối khác về mặt dữ liệu cần quan tâm. Ví dụ `SET state = 'PAID'` có vẻ an toàn hơn `counter = counter + 1`, nhưng trong thực tế vẫn phải xét **timestamp, TTL và event order**.

Java Driver 4.x hỗ trợ khai báo **tính idempotent của statement** để retry/speculative execution policy có thể quyết định khi nào được gửi lại. Đánh dấu này là **khai báo của lập trình viên**, không phải một transaction đảm bảo hệ thống tự khử trùng lặp hoặc giữ deadline.

| Lệnh | Có thể đánh giá ra sao? | Rủi ro cần kiểm soát |
|---|---|---|
| `UPDATE ... SET state = 'PAID'` với version/thứ tự ổn định | Có thể idempotent theo giá trị | Replay cũ/timestamp mới có thể phá state mới hơn |
| `INSERT ... USING TTL 300` | Cần xem kỹ | Ghi lại vào thời điểm sau có thể thay đổi hạn sống |
| `UPDATE counter SET count = count + 1` | **Không** idempotent nếu gửi lặp | Có thể cộng hai lần |
| `INSERT ... VALUES (..., now())` | Phụ thuộc ý định/cách thực thi | Retry có thể sinh khóa hoặc event khác |
| Chuyển trạng thái với `IF state = ...` | Có điều kiện, nhưng timeout có thể cho outcome không rõ | Cần đọc/đối chiếu kết quả và event ID |

**Quy tắc thực hành:** chỉ đánh dấu một statement idempotent khi hiểu chính xác hành vi của request **khi thực thi lại**, kể cả expiration và tương tác với các writer khác. Không bật retry trên mọi write chỉ vì CQL trông giống `UPDATE SET`.

### Retry policy và speculative execution

Retry có thể xảy ra vì timeout, lỗi kết nối hay unavailable tùy chính sách. **Speculative execution** có thể gửi thêm cùng request sang coordinator khác khi request chậm, vì vậy cũng phải xét idempotency. Điều này rất khác với “khi Java gọi `execute()` lần thứ hai mới tạo ra retry”.

Không khuyến khích tăng số lần retry để che một cluster mất ổn định: retries quá nhiều có thể làm quá tải thêm khi node đang gặp sự cố (*retry storm*). Cần giới hạn số lần, backoff, đo latency/error rate và phân biệt lỗi tạm thời với lỗi schema/policy không thể tự sửa bằng retry.

## 8. Java Driver 4.x: gắn timestamp của sự kiện với statement

Đoạn mã sau minh họa cách **không cấp một timestamp mới cho cùng một event** khi ứng dụng chủ động thực thi lại. Nó giả định nguồn cấp `eventTimestampMicros` có thể dùng làm version theo thứ tự nghiệp vụ; điều này **phải được bảo đảm ngoài Cassandra**.

```java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class OrderStateWriter {
    private final CqlSession session;
    private final PreparedStatement update;

    public OrderStateWriter(CqlSession session) {
        this.session = session;
        this.update = session.prepare(
            "UPDATE retry_order_state_by_id " +
            "SET state = ?, last_event_id = ?, last_source = ? " +
            "WHERE order_id = ?"
        );
    }

    public void writeEvent(UUID orderId, String state, String eventId,
                           String source, long eventTimestampMicros) {
        BoundStatement mutation = update.bind(state, eventId, source, orderId)
            .setQueryTimestamp(eventTimestampMicros);

        // Không đánh dấu idempotent một cách máy móc. Chỉ bật cơ chế
        // retry tự động nếu đã chứng minh semantics an toàn toàn hệ thống.
        session.execute(mutation);
    }
}
```

Trong Java Driver 4.x, `setQueryTimestamp(...)` trả về một statement mới theo kiểu API bất biến. Giá trị `eventTimestampMicros` cần ở **micro giây**, không phải `System.currentTimeMillis()` (mili giây).

**Ưu điểm có điều kiện:** cùng `eventId` được phát lại với timestamp như cũ sẽ không đơn giản nhận một mốc mới chỉ vì queue giao hàng trễ. **Nhưng**:

- Nếu hai sự kiện khác nhau có cùng timestamp, Cassandra sử dụng tie-break nội bộ, **không biết** version nghiệp vụ nào đúng.
- Nếu timestamp được lấy từ đồng hồ các service khác nhau mà không đồng bộ, thứ tự có thể vẫn sai.
- Nếu một cell bị xóa bằng tombstone có timestamp lớn hơn, replay cũ không làm dữ liệu sống lại.
- Nếu event có TTL, ổn định timestamp **không đồng nghĩa** ổn định expiration deadline.
- Không dùng `setQueryTimestamp()` tùy tiện cho **LWT/counter**; các thao tác này có ràng buộc riêng.

Đối với trạng thái thanh toán, đặt timestamp từ event time chỉ là một lựa chọn thiết kế nếu event time thực sự đáng tin cậy. Khi cần **chuyển trạng thái có điều kiện**, ưu tiên dùng version được kiểm soát và LWT thay vì lấy đồng hồ làm cơ chế duy nhất.

## 9. Java: giữ deadline nghiệp vụ không đổi qua retry TTL

Một thiết kế bền vững hơn cho token là lưu một `expiresAt` tuyệt đối do **nguồn tin cậy** tạo lúc phát hành. Mỗi lần gửi mutation sẽ tính **TTL còn lại**, không mặc định gửi lại TTL ban đầu.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class TokenWriter {
    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement putExpiringHash;

    public TokenWriter(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.putExpiringHash = session.prepare(
            "UPDATE retry_token_by_id USING TTL ? " +
            "SET token_hash = ? WHERE token_id = ?"
        );
    }

    public void writeUntil(UUID tokenId, String hash, Instant expiresAt) {
        // Dùng mốc cấp phát đầu tiên, không tính lại expiresAt từ NOW.
        long secondsLeft = Duration.between(clock.instant(), expiresAt)
            .getSeconds(); // Làm tròn xuống số giây.

        if (secondsLeft <= 0) {
            throw new IllegalStateException("Token already expired");
        }
        if (secondsLeft > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("TTL out of int range");
        }

        // Kiểm tra giới hạn TTL/expiration theo phiên bản Cassandra.
        session.execute(putExpiringHash.bind(
            Math.toIntExact(secondsLeft), hash, tokenId
        ));
    }
}
```

Ví dụ này **giảm rủi ro vô ý kéo dài TTL** khi ứng dụng tạo lại lệnh sau một khoảng chờ. Nó **không bảo đảm deadline chính xác tuyệt đối**: TTL được tính bằng giây, có độ trễ mạng và đồng hồ server/client có thể lệch. Vì vậy **khi sử dụng token, luôn kiểm tra `expires_at` theo mốc nghiệp vụ**, và đối với token chỉ được dùng một lần cần cơ chế tiêu thụ nguyên tử.

**Lỗi đặc biệt nguy hiểm:** nếu còn 0 giây, không được gửi `USING TTL 0`. Trong Cassandra, **TTL 0 có nghĩa không TTL**, chứ không phải “hết hạn ngay lập tức”. Đường ghi phải từ chối hoặc xử lý token đã hết hạn theo chính sách.

Khi retry sau timeout, cần cố định cùng `tokenId`/`expiresAt` và không phát hành token mới nếu thao tác chỉ là gửi lại việc lưu trữ. Việc tạo lại token mới là **một sự kiện nghiệp vụ khác**, phải được quản lý độc lập.

## 10. Idempotency key và event log: tránh phát lại thành một nghiệp vụ mới

Một cách mạnh hơn so với chỉ “gửi lại cùng CQL” là gán **event ID hoặc idempotency key** cho mỗi sự kiện nghiệp vụ.

```text
Message broker / API
      |
      +-- eventId=E1, orderId=O1, version=1, state=PENDING
      |
      +-- eventId=E2, orderId=O1, version=2, state=PAID
      |
      +-- replay eventId=E1
               |
               +-- nhận ra E1 đã xử lý / version đã cũ
               +-- không chuyển state từ PAID về PENDING
```

Ví dụ bảng lưu lịch sử theo đơn hàng:

```sql
CREATE TABLE IF NOT EXISTS order_events_by_order (
    order_id uuid,
    event_id uuid,
    event_version bigint,
    state text,
    source text,
    PRIMARY KEY ((order_id), event_id)
);

-- Event ID không đổi qua retry; IF NOT EXISTS có thể giúp phát hiện
-- trùng ở đúng row sự kiện này.
INSERT INTO order_events_by_order (
    order_id, event_id, event_version, state, source
)
VALUES (
    44444444-1313-4131-8131-444444444444,
    55555555-1313-4131-8131-555555555555,
    1, 'PENDING', 'checkout'
)
IF NOT EXISTS;
```

Đọc trường `[applied]` để biết lần `INSERT IF NOT EXISTS` có ghi row hay không. Tuy vậy, **dedupe event ở một bảng và cập nhật latest-state ở bảng khác không tự trở thành transaction nguyên tử xuyên hai partition**. Nếu cần đảm bảo nhất quán xuyên bảng, phải thiết kế thêm outbox/inbox, trạng thái xử lý, cơ chế replay/reconcile hoặc điều phối ở dịch vụ.

**Event ID không thay thế business version.** Một sự kiện có ID mới nhưng là trạng thái cũ vẫn có thể làm lùi latest-state nếu không kiểm tra thứ tự. Version cần có nguồn cấp đáng tin cậy (đơn writer, bộ điều phối hoặc cơ chế cập nhật có điều kiện).

## 11. LWT: dùng compare-and-set khi thứ tự trạng thái quan trọng

**Lightweight transaction (LWT)** của Cassandra cho phép cập nhật có điều kiện qua `IF`, dựa trên Paxos. Thay vì “ai có timestamp lớn hơn thắng”, ta kiểm tra phiên bản nghiệp vụ hiện có trước khi chuyển trạng thái.

Tạo bảng thử có version:

```sql
CREATE TABLE IF NOT EXISTS versioned_order_state_by_id (
    order_id uuid PRIMARY KEY,
    version bigint,
    state text,
    last_event_id text
);

INSERT INTO versioned_order_state_by_id (
    order_id, version, state, last_event_id
)
VALUES (
    66666666-1313-4131-8131-666666666666,
    1, 'PENDING', 'E1'
)
IF NOT EXISTS;

-- Chỉ chuyển sang PAID nếu phiên bản đang là 1.
UPDATE versioned_order_state_by_id
SET version = 2, state = 'PAID', last_event_id = 'E2'
WHERE order_id = 66666666-1313-4131-8131-666666666666
IF version = 1;
```

Nếu `[applied] = true`, transition được áp dụng. Bây giờ E1 retry với điều kiện `IF version = 0` hoặc `IF version = 1` sẽ **không tùy tiện làm lùi trạng thái** sau khi version đã lên 2.

### Retry LWT sau timeout

LWT cũng có thể trả timeout khiến client **không biết transition đã commit hay chưa**. Không được giả định timeout đồng nghĩa `[applied] = false`. Một quy trình bảo thủ:

1. Đọc lại row theo mức nhất quán phù hợp với luồng LWT và phiên bản Cassandra.
2. So sánh `version`, `last_event_id` và trạng thái với **chính event đang retry**.
3. Nếu event đã được áp dụng, coi là hoàn tất về nghiệp vụ.
4. Nếu version đã tiến xa hơn, coi event là cũ và không đè lùi.
5. Nếu vẫn ở expected version, có thể thử lại CAS theo chính sách retry giới hạn.

Trong LWT, không gán `USING TIMESTAMP` do client tự chọn như ghi thường. CAS giúp bảo vệ điều kiện trong phạm vi hỗ trợ, đổi lại chi phí và độ trễ cao hơn; không dùng cho mọi write nếu nghiệp vụ chỉ cần LWW.

## 12. Retry với TTL trên collection, counter, delete và batch

Không phải mọi mutation CQL đều có rủi ro giống nhau:

| Đối tượng/thao tác | Điều cần lưu ý khi retry |
|---|---|
| **Scalar SET** cùng cell | Timestamp mới có thể đổi phiên bản thắng; TTL có thể tạo thời hạn mới |
| **Map/UDT không frozen** cập nhật một key/field | Chỉ thành phần được ghi có thể nhận timestamp/TTL mới; các phần khác giữ metadata |
| **Frozen collection/UDT** | Ghi lại thay toàn bộ cell; TTL gắn với cả giá trị frozen |
| **Counter** `+ 1` | Retry có thể cộng trùng; không coi là idempotent |
| **`DELETE`** | Tombstone có timestamp riêng; retry với timestamp mới có thể thay thứ tự xóa/ghi |
| **Batch nhiều mutation** | Không tự giải quyết dedupe/thứ tự nghiệp vụ; timeout batch vẫn cần reconcile |
| **LWT với `IF`** | Kết quả timeout không rõ; kiểm tra `[applied]` và trạng thái/version khi reconcile |

Một lỗi phổ biến với `DELETE`: ứng dụng xóa một cell, gặp timeout, rồi tạo lại `DELETE` với timestamp rất lớn. Tombstone mới có thể che một **ghi hợp lệ được thực hiện giữa hai lần xóa**. Điều đó đặc biệt nguy hiểm khi xóa được tái thử theo lịch mà không biết đã có nghiệp vụ mới.

Với bộ đếm (*counter*), không đưa `USING TTL` hoặc `USING TIMESTAMP` theo cách ghi scalar. Counter có semantics và giới hạn riêng; muốn tránh cộng trùng cần event ID/dedupe hoặc mô hình tính toán khác.

## 13. Replication, consistency level và “thành công” của request

Giả sử `RF = 3` và ứng dụng dùng `CL = QUORUM` khi ghi. Quorum thường là hai replica trong ba, nhưng:

- ACK từ quorum **không bảo đảm** một mutation có timestamp thấp hơn sẽ thắng phiên bản đang có timestamp lớn hơn.
- **Retry** có thể đi qua coordinator khác, nhưng thay CL không tự cố định timestamp hoặc TTL.
- Đọc tại `ONE` ngay giữa các mutation có thể thấy phiên bản tạm khác nhau do replica chưa đồng bộ.
- **Repair** có thể làm các replica hội tụ theo luật Cassandra, nhưng không thể tự xác định rằng nghiệp vụ `PAID` đáng lẽ phải thắng `PENDING`.
- TTL hết hạn tạo thông tin expiration/tombstone để ngăn giá trị cũ tái xuất hiện; **compaction** và `gc_grace_seconds` liên quan thu hồi an toàn, không bảo toàn deadline nghiệp vụ thay cho ứng dụng.

Khi điều tra timeout, cần phân biệt **số replica ACK**, **phiên bản cell đang thắng**, và **event nghiệp vụ đã hoàn tất**. Đây là ba câu hỏi khác nhau, không nên gộp thành câu “Cassandra đã ghi hay chưa?”.

## 14. Chẩn đoán sự cố retry gây mất cập nhật hoặc kéo dài TTL

### 14.1. Truy vấn quan sát cell

```sql
SELECT order_id, state, writetime(state) AS state_write_us,
       last_event_id, writetime(last_event_id) AS event_write_us
FROM retry_order_state_by_id
WHERE order_id = 11111111-1313-4131-8131-111111111111;

SELECT token_id, token_hash, ttl(token_hash) AS ttl_s,
       writetime(token_hash) AS token_write_us, expires_at
FROM retry_token_by_id
WHERE token_id = 33333333-1313-4131-8131-333333333333;
```

`writetime()` cho biết **metadata của cell sống đang quan sát**, không liệt kê toàn bộ những lần retry, phiên bản thua hay tombstone. `ttl()` cho biết **giây còn lại** (hoặc `null` nếu cell không có TTL/không còn sống), không phải hạn tuyệt đối của nghiệp vụ.

### 14.2. Checklist theo dấu một lần retry

| Câu hỏi | Bằng chứng nên lấy |
|---|---|
| Retry do driver hay do service/queue tạo mới? | Request ID, retry attempt, stack trace, chính sách retry |
| Có chắc lần trước chưa apply không? | Coordinator timeout, các ACK, log ứng dụng, dữ liệu hiện tại |
| Cùng `event_id` hay tạo event mới? | Idempotency key, offset/sequence của broker |
| Mutation timestamp thay đổi không? | `USING TIMESTAMP`, `setQueryTimestamp`, generator, `writetime` khi cell sống |
| TTL/deadline được xác lập từ đâu? | `USING TTL`, `default_time_to_live`, `expires_at` nguồn phát hành |
| Có writer khác xử lý event mới hơn trong lúc chờ? | Business version, state transition log |
| Client có nhầm giây/mili giây/micro giây? | Đơn vị biến, chuyển `Duration`/`Instant` |
| Có tombstone/expired cell không? | DELETE, TTL, công cụ SSTable và lịch mutation |
| Có khác replica/CL/clock skew? | RF/CL, node health, NTP offset, repair status |
| Có retry storm? | Throughput, latency, timeout rate, số lần và backoff |

**Không thu thập token plaintext hoặc dữ liệu bí mật** chỉ để điều tra. Log cấu trúc nên chứa ID giả danh, khóa nghiệp vụ thích hợp, event ID, timestamp micro giây, TTL giây, hạn UTC, số lần retry và loại kết quả.

## 15. Quy trình triển khai retry an toàn trong ứng dụng Java

Một thiết kế thực tế có thể theo các nguyên tắc sau:

1. **Phân loại thao tác:** state overwrite, create-once, counter, TTL cache, token một lần, LWT. Không dùng một chính sách retry chung cho tất cả.
2. **Cấp event ID và version tại nguồn nghiệp vụ:** bảo toàn qua mọi lần phát lại. Không dùng “thời điểm retry” làm version của một event cũ.
3. **Xác định deadline tuyệt đối nếu có TTL nghiệp vụ:** lưu `expires_at` ngay lúc phát hành; khi ghi lại tính thời gian còn lại và từ chối nếu hết hạn.
4. **Chọn cơ chế chống cạnh tranh:** một writer theo key, LWT/CAS, hoặc event log + projector có version. Dựa vào LWW đơn thuần chỉ khi đúng semantics mong muốn.
5. **Cấu hình driver idempotency chính xác:** xem xét retry policy, speculative execution, timeouts và lỗi có thể retry.
6. **Giới hạn retry:** số lần, backoff có jitter, timeout tổng và hàng đợi lỗi/DLQ. Không replay vô hạn vào cluster đang quá tải.
7. **Reconcile sau unknown outcome:** đọc trạng thái/version/event ID trước khi quyết định tạo mutation mới.
8. **Kiểm thử với failure injection:** thử mất ACK, coordinator timeout, replica chậm, event đến sai thứ tự, clock skew, TTL sát 0 và retry sau deadline.
9. **Quan sát được quyết định:** log vì sao một event được ghi, bỏ qua vì version cũ, coi như đã áp dụng hay chuyển sang xử lý thủ công.

### Bảng lựa chọn theo nghiệp vụ

| Yêu cầu | Gợi ý |
|---|---|
| Cache có thể làm mới sau mỗi lần truy cập | Chủ động gia hạn TTL; chấp nhận semantics “sliding expiration” |
| Token phải hết đúng hạn phát hành | `expires_at` bất biến + TTL còn lại + kiểm tra hạn khi sử dụng |
| Đơn hàng không được lùi từ `PAID` về `PENDING` | Version/CAS hoặc projector có thứ tự; không chỉ dựa vào timestamp nhận request |
| Sự kiện có thể đến lặp từ queue | Event ID, dedupe và checkpoint/offset phù hợp |
| Counter/thao tác tăng giảm | Không retry mù; dedupe nguồn hoặc thiết kế thay thế |
| Ghi thuần có thể replay, không có nghiệp vụ thứ tự | Xác minh tính idempotent và policy retry trước khi cho phép |

## 16. Bài tập tình huống và đáp án

**Câu 1.** E1 có timestamp `100`, E2 có timestamp `200`. Retry E1 nhận timestamp `300`. Sau hòa giải cùng cell, giá trị của event nào thắng?

**Đáp án:** **E1 retry** nếu không có tombstone/phiên bản lớn hơn, bởi `300 > 200`. Đây có thể là một lần lùi trạng thái nghiệp vụ.

**Câu 2.** Client nhận write timeout. Có thể kết luận lần ghi chưa có ở replica nào không?

**Đáp án:** **Không.** Một số replica hoặc đủ replica đã có thể nhận mutation nhưng client không nhận được kết quả rõ ràng.

**Câu 3.** Token phát hành lúc 12:00 với TTL 300; ứng dụng tạo lại mutation với TTL 300 lúc 12:02 và mutation mới thắng. Có thể dùng token tới 12:07 không?

**Đáp án:** Cell có thể còn sống tới khoảng 12:07, nhưng **hạn nghiệp vụ đúng** nếu tính từ lần phát hành đầu vẫn là 12:05. Phải kiểm tra `expires_at` bất biến.

**Câu 4.** Nếu replay dùng lại cùng mutation timestamp nhưng tạo lại câu `USING TTL 300`, có thể bảo đảm expiration tuyệt đối giữ nguyên không?

**Đáp án:** **Không được mặc định.** TTL là metadata thời hạn tương đối, đường thực thi và quy tắc xung đột/tie-break cần kiểm chứng; deadline nghiệp vụ phải được bảo toàn riêng.

**Câu 5.** Có thể dùng `USING TTL 0` để hết hạn token ngay khi thời gian còn lại bằng 0 không?

**Đáp án:** **Không.** `TTL 0` nghĩa là **không TTL**. Phải từ chối hoặc xử lý token đã hết hạn.

**Câu 6.** Đánh dấu một statement `isIdempotent = true` trong Java Driver có tự bảo đảm API thanh toán không bị xử lý hai lần?

**Đáp án:** **Không.** Cờ driver chỉ hỗ trợ quyết định retry/speculative execution; idempotency nghiệp vụ cần event ID, kiểm soát side effect và trạng thái/version.

**Câu 7.** Nếu E1 retry với timestamp `100` và E2 đã thắng timestamp `200`, E1 có làm lùi trạng thái không?

**Đáp án:** Với cùng cell thông thường và không có tương tác phức tạp khác, **không**: E2 có timestamp lớn hơn. Nhưng phải chắc timestamp thể hiện thứ tự hợp lệ; trường hợp timestamp trùng và tombstone có quy tắc khác.

**Câu 8.** `CL = ALL` có ngăn retry cũ mang timestamp mới lớn hơn ghi đè state nghiệp vụ không?

**Đáp án:** **Không.** ALL ràng buộc xác nhận replica, không thay thế điều kiện chuyển trạng thái.

**Câu 9.** LWT `IF version = 1` timeout. Client có thể kết luận điều kiện không áp dụng và luôn gửi lại ngay không?

**Đáp án:** **Không.** Kết quả có thể chưa rõ; nên reconcile version/event ID rồi thử lại CAS có giới hạn nếu còn cần thiết.

**Câu 10.** Vì sao `UPDATE state = 'PAID'` hai lần có thể không idempotent ở cấp nghiệp vụ, dù cùng giá trị?

**Đáp án:** Lần sau có thể mang write timestamp mới hoặc đặt lại TTL, gây thay đổi thứ tự LWW hay deadline; ngoài ra side effect của dịch vụ có thể bị thực hiện hai lần nếu thiếu dedupe.

---

**Ghi nhớ:** Trong Cassandra, **retry có thể thay đổi kết quả nghiệp vụ** khi một event cũ được cấp **mutation timestamp mới** hoặc một giá trị được ghi lại với **TTL tương đối mới**. Timeout không chứng minh lần ghi trước thất bại; cờ idempotent của driver không thay thế tính idempotent của nghiệp vụ. Hãy bảo toàn **event ID/version**, phân biệt retry cùng execution với mutation mới, đặt **`expires_at` tuyệt đối** cho dữ liệu có deadline và dùng **LWT/điều phối** khi trạng thái phải tuân thứ tự rõ ràng. RF, CL, repair và compaction giữ vai trò phân tán/dọn dữ liệu, chứ không tự quyết định đúng sai của luồng nghiệp vụ.
