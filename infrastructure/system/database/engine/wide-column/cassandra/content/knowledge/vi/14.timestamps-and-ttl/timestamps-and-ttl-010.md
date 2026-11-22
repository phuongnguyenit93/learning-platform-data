# Cập nhật giá trị có TTL và ý nghĩa thời hạn mới

## 1. Mục tiêu: hiểu đúng điều xảy ra khi ghi đè một giá trị sắp hết hạn

Trong **Apache Cassandra**, hệ quản trị cơ sở dữ liệu **wide-column phân tán**, một cell có thể được ghi với **TTL** (*time to live*) để tự hết hiệu lực sau số giây quy định. Vấn đề xuất hiện khi ứng dụng **cập nhật lại chính cell đó** trước khi TTL cũ kết thúc: cell có giữ hạn cũ, cộng thêm thời gian mới, hay bắt đầu đếm lại?

**Quy tắc chính:** Nếu một mutation cập nhật cell **thắng theo write timestamp**, nó tạo **phiên bản giá trị mới** với metadata mới. TTL và thời điểm hết hạn của phiên bản mới được xác định **theo lần ghi mới**, chứ không cộng vào TTL còn lại của phiên bản cũ.

- `UPDATE ... USING TTL 120 SET value = ...`: phiên bản mới được đặt thời hạn **120 giây tính từ lần ghi mới**.
- `UPDATE ... SET value = ...` trên bảng **không có TTL mặc định**: phiên bản mới **không có TTL**, dù phiên bản trước đang đếm ngược.
- `UPDATE ... SET value = ...` trên bảng có `default_time_to_live = 600`: phiên bản mới thường nhận **TTL mặc định 600 giây**.
- `UPDATE ... USING TTL 0 SET value = ...`: phiên bản mới **không có TTL**, kể cả khi bảng có TTL mặc định.
- `UPDATE` một **cột khác**: không tự làm mới TTL của cell chưa được ghi.

Điều kiện quan trọng nằm ở chữ **“thắng”**: Cassandra hòa giải các lần ghi cùng cell bằng **last-write-wins (LWW)** theo mutation timestamp. Một lệnh `UPDATE` chạy thành công nhưng mang timestamp nhỏ hơn phiên bản hiện tại có thể **không thay đổi** giá trị hay TTL quan sát được.

Trong bài này, ta dùng CQL và Java để dự đoán kết quả, phân biệt **thời hạn tương đối** với **hạn chót nghiệp vụ tuyệt đối**, và hiểu tác động tới replication, tombstone, compaction, repair.

## 2. Timeline: TTL mới không cộng với TTL cũ

Giả sử một cell được ghi lần đầu với TTL **300 giây** lúc `10:00:00`:

```text
10:00:00                                               10:05:00
   |---------------- TTL cũ: 300 giây ----------------------|
   |
   +-- status = 'PENDING' (phiên bản A)

10:01:30                         10:03:30
   |--------------------------------|
   +-- UPDATE status = 'PAID'        |
       USING TTL 120                |
       phiên bản B thắng             +-- B hết hạn
```

Tại `10:01:30`, TTL còn lại của phiên bản A xấp xỉ **210 giây**. Khi ghi phiên bản B với TTL **120 giây**, thời hạn mới là khoảng **`10:03:30`**, không phải `10:07:00` (210 + 120 giây), cũng không phải `10:05:00` (hạn cũ).

| Tình huống tại `10:01:30` | TTL phiên bản mới | Thời điểm hết hạn mới, giả sử ghi thành công và đồng hồ chuẩn |
|---|---|---|
| Ghi `'PAID' USING TTL 120` | 120 giây | Khoảng `10:03:30` |
| Ghi `'PAID' USING TTL 600` | 600 giây | Khoảng `10:11:30` |
| Ghi `'PAID'`, bảng không có TTL mặc định | Không TTL | Không hết hạn vì TTL |
| Ghi `'PAID' USING TTL 0` | Không TTL | Không hết hạn vì TTL |
| Chỉ ghi cột `updated_by` | Cell `status` giữ hạn cũ | Khoảng `10:05:00` |

**Lưu ý về thuật ngữ:** “Gia hạn TTL” thường được dùng để nói tăng thời gian sống, nhưng một TTL mới **ngắn hơn** có thể làm giá trị hết hạn **sớm hơn** dự kiến ban đầu. Vì vậy, chính xác hơn nên nói **đặt lại thời hạn cho phiên bản cell mới**.

Không có tác vụ đếm ngược độc lập cho từng cell. Cassandra lưu metadata expiration, rồi khi đọc hoặc xử lý SSTable sẽ xác định cell còn sống hay đã hết hạn. `ttl(column)` trả về **giây còn lại**, thường thấp hơn một chút so với TTL vừa khai báo do độ trễ và độ phân giải theo giây.

## 3. Thiết lập bảng CQL để quan sát TTL khi cập nhật

Thực hành trong **keyspace thử nghiệm** đã chọn bằng `USE <keyspace>;`. Các UUID cố định dưới đây giả định **chưa từng có dữ liệu**; nếu chạy lại ví dụ, hãy đổi UUID để tránh tombstone hoặc write timestamp từ lần trước ảnh hưởng kết quả.

```sql
CREATE TABLE IF NOT EXISTS payment_state_by_id (
    payment_id uuid PRIMARY KEY,
    state text,
    updated_by text,
    event_at timestamp
);
```

Schema này phục vụ truy vấn một khoản thanh toán theo `payment_id`. Nó không nhằm minh họa toàn bộ cách quản lý giao dịch thanh toán thật; trạng thái tiền tệ quan trọng thường cần điều kiện chuyển trạng thái hoặc nguồn sự kiện đáng tin cậy.

Tạo một cell đang có TTL:

```sql
INSERT INTO payment_state_by_id (
    payment_id, state, updated_by, event_at
)
VALUES (
    10101010-1010-4010-8010-101010101010,
    'PENDING',
    'checkout',
    '2026-11-21T00:00:00Z'
)
USING TTL 300;

SELECT state,
       ttl(state) AS state_ttl_s,
       writetime(state) AS state_write_us,
       updated_by, ttl(updated_by) AS updated_by_ttl_s,
       event_at
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

Khi vừa ghi và chưa có mutation xung đột:

- `state = 'PENDING'`, `ttl(state)` gần **300 giây**.
- `updated_by` cũng được ghi trong `INSERT`, nên nó có TTL gần **300 giây**.
- `event_at` là **thời gian nghiệp vụ** lưu trong cột CQL `timestamp`, không phải mốc bắt đầu TTL.
- `writetime(state)` là mutation timestamp **micro giây** dùng cho LWW, không phải số giây còn lại.

Vì cả ba cột được ghi cùng mutation, chúng thường nhận metadata theo lần ghi đó. Các phép cập nhật tiếp theo có thể làm TTL giữa các cell khác nhau.

## 4. Thử nghiệm A: ghi đè cùng cell với TTL mới

Trước khi 300 giây ban đầu hết hạn, chạy:

```sql
UPDATE payment_state_by_id
USING TTL 120
SET state = 'PAID'
WHERE payment_id = 10101010-1010-4010-8010-101010101010;

SELECT state, ttl(state), writetime(state),
       updated_by, ttl(updated_by), writetime(updated_by)
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

Nếu mutation mới thắng LWW, kết quả ngay sau cập nhật:

| Cột | Giá trị | TTL còn lại | Write timestamp |
|---|---|---|---|
| `state` | `PAID` | Gần **120 giây** | Timestamp của `UPDATE` |
| `updated_by` | `checkout` | Đếm tiếp từ **300 giây của `INSERT`** | Timestamp của `INSERT` |
| `event_at` | Mốc nghiệp vụ ban đầu | Đếm tiếp từ **300 giây của `INSERT`** | Timestamp của `INSERT` |

Đây là ví dụ trực tiếp về **TTL theo cell**: cập nhật `state` không kéo dài `updated_by` hoặc `event_at`. Hơn nữa, nếu cập nhật `state` với TTL 120 khi `state` cũ còn 250 giây, phiên bản mới lại **hết hạn sớm hơn** bản cũ.

### Ghi lại đúng cùng một giá trị có tác dụng không?

Có. Cassandra không cần chuỗi mới khác chuỗi cũ mới coi là mutation. Ví dụ:

```sql
UPDATE payment_state_by_id
USING TTL 600
SET state = 'PAID'
WHERE payment_id = 10101010-1010-4010-8010-101010101010;

SELECT state, ttl(state), writetime(state)
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

Dù `state` vẫn là `'PAID'`, nếu lần ghi lại thắng timestamp, `ttl(state)` gần **600 giây từ lần `UPDATE` mới**, và `writetime(state)` thay đổi theo mutation mới. **Giá trị giống nhau không có nghĩa metadata giống nhau.**

Trong ứng dụng thực, ghi lặp với TTL khác nhau có thể gây quá hạn sớm hoặc kéo dài dữ liệu ngoài dự kiến. Cần kiểm soát retry và quy tắc idempotency.

## 5. Thử nghiệm B: cập nhật mà không có `USING TTL`

Với bảng `payment_state_by_id` ở trên, ta không đặt `default_time_to_live`; mặc định nó là `0` (**không TTL mặc định**). Khi ghi lại `state` mà không có `USING TTL`:

```sql
UPDATE payment_state_by_id
SET state = 'SETTLED'
WHERE payment_id = 10101010-1010-4010-8010-101010101010;

SELECT state, ttl(state), writetime(state),
       updated_by, ttl(updated_by)
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

Nếu mutation mới thắng:

- `state = 'SETTLED'`.
- `ttl(state) = null`: phiên bản mới **không còn hạn TTL**.
- `updated_by` vẫn giữ TTL riêng được đặt trong `INSERT` ban đầu, nếu nó chưa hết hạn.

Điều này thường gây bất ngờ: **một cột từng được ghi với TTL không tự giữ TTL ấy khi bị ghi đè mà không chỉ định TTL mới**.

Trong production, một API sửa trạng thái mà vô tình bỏ `USING TTL` có thể biến dữ liệu tạm thành dữ liệu tồn tại lâu dài. Nếu yêu cầu mọi lần cập nhật vẫn hết hạn, cần thiết kế API luôn truyền TTL phù hợp hoặc dùng TTL mặc định của bảng.

## 6. Thử nghiệm C: đặt `USING TTL 0` một cách có chủ đích

`USING TTL 0` yêu cầu phiên bản cell mới **không có TTL**, kể cả khi bảng có TTL mặc định. Đây là cách đặt chính sách không hết hạn theo TTL cho **cell được ghi**, không phải lệnh xóa.

```sql
UPDATE payment_state_by_id
USING TTL 0
SET state = 'ARCHIVED'
WHERE payment_id = 10101010-1010-4010-8010-101010101010;

SELECT state, ttl(state), writetime(state)
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

Nếu thắng LWW, kết quả là `state = 'ARCHIVED'` và `ttl(state) = null`. Không có ý nghĩa “hết hạn ngay lập tức” hay “xóa trong 0 giây”.

| Câu ghi | Trên bảng không có TTL mặc định | Trên bảng `default_time_to_live = 900` |
|---|---|---|
| `UPDATE ... SET state = 'X'` | Cell mới **không TTL** | Cell mới có TTL **900 giây** |
| `UPDATE ... USING TTL 120 SET state = 'X'` | TTL **120 giây** | TTL **120 giây** |
| `UPDATE ... USING TTL 0 SET state = 'X'` | **Không TTL** | **Không TTL** |

Không sử dụng TTL `-1`, giá trị âm hay mã hóa không rõ ràng để biểu diễn “vĩnh viễn”. `TTL 0` phải là quyết định rõ ràng về vòng đời dữ liệu; với dữ liệu nhạy cảm, “không TTL” có thể dẫn đến yêu cầu bảo lưu hoặc xóa riêng.

## 7. Thử nghiệm D: cập nhật một cột khác không gia hạn cell TTL

Đây là trường hợp dễ bị nhầm với “TTL của row”. Tạo một khóa riêng:

```sql
INSERT INTO payment_state_by_id (payment_id, state, updated_by)
VALUES (
    20202020-2020-4020-8020-202020202020,
    'PENDING',
    'checkout'
)
USING TTL 180;

-- Chỉ thay cột updated_by, không ghi lại state.
UPDATE payment_state_by_id
USING TTL 3600
SET updated_by = 'operations'
WHERE payment_id = 20202020-2020-4020-8020-202020202020;

SELECT state, ttl(state), writetime(state),
       updated_by, ttl(updated_by), writetime(updated_by)
FROM payment_state_by_id
WHERE payment_id = 20202020-2020-4020-8020-202020202020;
```

Khi vừa cập nhật:

- `state = 'PENDING'`, `ttl(state)` tiếp tục giảm từ **180 giây** của `INSERT`.
- `updated_by = 'operations'`, `ttl(updated_by)` gần **3.600 giây** từ lần `UPDATE`.
- Hai cell trong cùng row có write timestamp và expiration khác nhau.

Sau khi `state` hết hạn, row **vẫn có thể còn** vì `updated_by` chưa hết TTL. Java client cần chuẩn bị cho trường hợp cột `state` bằng `null` trong một row vẫn tồn tại.

**Kết luận:** Đừng gọi TTL của một cột là “TTL của toàn đối tượng” trừ khi thiết kế schema và mọi đường ghi bảo đảm vòng đời đồng nhất.

## 8. TTL mặc định của bảng khi cập nhật

Cassandra hỗ trợ `default_time_to_live`, một thuộc tính bảng tính bằng **giây**. Khi có TTL mặc định, những mutation **không chỉ định TTL riêng** thường dùng giá trị mặc định hiện hành để ghi các cell.

```sql
CREATE TABLE IF NOT EXISTS short_cache_by_key (
    cache_key text PRIMARY KEY,
    payload text,
    refreshed_by text
) WITH default_time_to_live = 900;

INSERT INTO short_cache_by_key (cache_key, payload, refreshed_by)
VALUES ('summary:42', 'initial', 'worker-a');

SELECT payload, ttl(payload), refreshed_by, ttl(refreshed_by)
FROM short_cache_by_key
WHERE cache_key = 'summary:42';
```

Hai cell dữ liệu ban đầu có TTL gần **900 giây**. Bây giờ cập nhật `payload`:

```sql
-- Không có USING TTL: nhận TTL mặc định 900 giây cho payload mới.
UPDATE short_cache_by_key
SET payload = 'recomputed'
WHERE cache_key = 'summary:42';

SELECT payload, ttl(payload),
       refreshed_by, ttl(refreshed_by)
FROM short_cache_by_key
WHERE cache_key = 'summary:42';
```

Nếu update thắng, `ttl(payload)` gần **900 giây** từ lần cập nhật, trong khi `ttl(refreshed_by)` vẫn đếm theo `INSERT`.

### Ghi đè mặc định bằng TTL riêng

```sql
UPDATE short_cache_by_key
USING TTL 60
SET payload = 'transient'
WHERE cache_key = 'summary:42';

SELECT payload, ttl(payload)
FROM short_cache_by_key
WHERE cache_key = 'summary:42';
```

Cell `payload` mới có TTL gần **60 giây**, không phải 900 giây. Nếu muốn không TTL dù bảng có mặc định:

```sql
UPDATE short_cache_by_key
USING TTL 0
SET payload = 'pinned'
WHERE cache_key = 'summary:42';
```

**Đổi `default_time_to_live` bằng `ALTER TABLE` không tự cập nhật metadata của các cell đã có**. Nó chỉ ảnh hưởng những lần ghi sau khi schema mới có hiệu lực. Nếu muốn thay đổi thời hạn của một cell cũ, cần mutation mới phù hợp, chứ không chỉ sửa default.

## 9. Khi phiên bản ghi mới thua last-write-wins thì TTL có đổi không?

**Không nhất thiết.** Cassandra phân xử xung đột theo **mutation timestamp**, tính bằng **micro giây kể từ Unix epoch**, chứ không theo thời gian request đến. Điều này áp dụng cả với cell có TTL.

Để tránh đồng hồ hiện tại làm sai ví dụ, hãy dùng **một UUID mới** với timestamp thủ công:

```sql
INSERT INTO payment_state_by_id (payment_id, state)
VALUES (
    30303030-3030-4030-8030-303030303030,
    'FIRST'
)
USING TIMESTAMP 1800000000002000 AND TTL 600;

-- Câu UPDATE gửi sau nhưng timestamp lại nhỏ hơn.
UPDATE payment_state_by_id
USING TIMESTAMP 1800000000001000 AND TTL 30
SET state = 'SECOND'
WHERE payment_id = 30303030-3030-4030-8030-303030303030;

SELECT state, writetime(state), ttl(state)
FROM payment_state_by_id
WHERE payment_id = 30303030-3030-4030-8030-303030303030;
```

Kết quả mong đợi ngay sau hai mutation:

| Biểu thức | Giá trị |
|---|---|
| `state` | `FIRST` |
| `writetime(state)` | `1800000000002000` |
| `ttl(state)` | Gần **600 giây**, không phải 30 |

Lý do: `SECOND@...1000` không thắng `FIRST@...2000`, nên **TTL 30 của mutation thua không trở thành metadata của cell đang hiển thị**.

Nếu thử lại với timestamp `1800000000003000` và TTL 30, phiên bản mới thắng rồi nhận hạn mới khoảng **30 giây kể từ mutation sau**. Không dùng `USING TIMESTAMP` bất thường trên dữ liệu sản xuất chỉ để “chỉnh TTL”; timestamp ở tương lai có thể che các ghi hợp lệ về sau.

### Timestamp bằng nhau

Khi hai giá trị cùng cell có timestamp bằng nhau, Cassandra dùng các quy tắc tie-break nội bộ; không nên giả định mutation gửi sau thắng. Với tombstone xung đột giá trị sống ở cùng timestamp, tombstone được ưu tiên. Do đó, khi kiểm tra việc đặt lại TTL, nên dùng các ghi có thứ tự timestamp rõ ràng và khóa thử chưa từng dùng.

## 10. Khi TTL mới hết hạn, giá trị cũ có xuất hiện trở lại không?

**Không được thiết kế theo giả định đó.** TTL không cung cấp lịch sử phiên bản kiểu “stack” hay cơ chế tự quay về giá trị trước:

```text
10:00    state = PENDING   TTL 1 giờ       (phiên bản A)
10:05    state = PAID      TTL 2 phút      (phiên bản B thắng)
10:07    B hết hạn
         |
         +-- KHÔNG mặc định quay lại state = PENDING.
             Dữ liệu hết hạn được xử lý qua expiration/tombstone.
```

Về mặt lưu trữ, các phiên bản cũ có thể còn trong memtable/SSTable hoặc trên replica khác, nhưng Cassandra dùng metadata timestamp và tombstone để ngăn bản cũ xuất hiện lại khi dữ liệu mới đã hết hạn hoặc bị xóa. Việc dọn tombstone phải tuân điều kiện an toàn; nếu một replica giữ bản cũ quá lâu và tombstone bị loại bỏ không đúng thời điểm, có rủi ro **zombie data**.

Đừng dùng cập nhật TTL ngắn làm “ghi đè tạm thời rồi tự hoàn nguyên” một trạng thái quan trọng. Nếu nghiệp vụ cần quay về giá trị trước, **ứng dụng phải thực hiện một transition mới** với timestamp/thứ tự nghiệp vụ phù hợp, hoặc lưu sự kiện và tính lại trạng thái từ nguồn đáng tin cậy.

Một trường hợp khác là TTL của cell mới dài hơn TTL cũ. Khi cell mới hết hạn sau này, bản cũ cũng không tự trở lại; TTL mới kiểm soát vòng đời phiên bản mới, không lưu một ngăn xếp dữ liệu dự phòng.

## 11. Retry, timeout và idempotency: TTL có thể bị làm mới ngoài ý muốn

Trong ứng dụng phân tán, một request có thể đã được một số replica chấp nhận nhưng client lại gặp **timeout** trước khi biết kết quả. Nếu ứng dụng chủ động **phát một mutation mới** với cùng giá trị, timestamp lớn hơn và TTL giống nhau, thời hạn hết hiệu lực có thể bị đẩy về sau:

| Thời điểm | Thao tác | Hạn sống dự kiến |
|---|---|---|
| `12:00` | `INSERT token USING TTL 300` | Khoảng `12:05` |
| `12:02` | Retry bằng mutation **mới** `USING TTL 300` và timestamp thắng | Khoảng `12:07` |
| `12:05` | Ứng dụng tưởng token đã hết theo lần ghi đầu | Token có thể còn sống do lần ghi sau |

**Không phải mọi retry đều kéo dài TTL.** Nếu một retry thực sự gửi lại cùng mutation với cùng timestamp/expiration metadata, nó có thể mang tính idempotent hơn. Cần phân biệt retry do driver thực hiện với việc ứng dụng tạo một **request ghi hoàn toàn mới**; cách driver cấp timestamp và cách TTL được tính tại các thời điểm khác nhau phải được kiểm chứng theo phiên bản đang dùng.

### Khi cần một hạn chót tuyệt đối

Với OTP, token hoặc phiên xử lý có yêu cầu “hết hiệu lực lúc 12:05 bất kể retry”, hãy dùng **`expires_at` là thời điểm nghiệp vụ tuyệt đối** từ nguồn thời gian đáng tin cậy:

1. Xác định `expires_at` tại lúc tạo sự kiện (hoặc lấy từ nguồn phát hành token).
2. Trước mỗi lần ghi/retry, tính thời gian còn lại `expires_at - trustedNow`.
3. Nếu đã hết hạn, **không ghi lại**; xử lý như đối tượng đã quá hạn.
4. Nếu còn hạn, chuyển khoảng còn lại thành TTL dương hợp lệ, ghi và vẫn **kiểm tra `expires_at`** ở đường xác thực nghiệp vụ.

Cassandra TTL hữu ích cho quản lý lưu trữ tự động, **không thay thế** logic xác thực hạn chót, chống dùng lại token hoặc compare-and-set giữa nhiều client. Đặc biệt, **không chuyển thời gian còn lại bằng 0 thành `USING TTL 0`**: trong Cassandra, TTL 0 nghĩa là **không hết hạn**, hoàn toàn ngược với ý định!

## 12. Java Driver: API cập nhật với TTL mới và deadline

Trong Java, **Apache/DataStax Cassandra Java Driver 4.x** cho phép bind TTL bằng prepared statement. Số được truyền vào `USING TTL ?` là **giây**, không phải mili giây hay micro giây:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class ExpiringPaymentStateRepository {
    private final CqlSession session;
    private final Clock clock;
    private final PreparedStatement updateWithTtl;
    private final PreparedStatement updateWithoutTtl;
    private final PreparedStatement inspect;

    public ExpiringPaymentStateRepository(CqlSession session, Clock clock) {
        this.session = session;
        this.clock = clock;
        this.updateWithTtl = session.prepare(
            "UPDATE payment_state_by_id USING TTL ? " +
            "SET state = ? WHERE payment_id = ?"
        );
        this.updateWithoutTtl = session.prepare(
            "UPDATE payment_state_by_id " +
            "SET state = ? WHERE payment_id = ?"
        );
        this.inspect = session.prepare(
            "SELECT state, ttl(state) AS ttl_s, " +
            "writetime(state) AS write_us " +
            "FROM payment_state_by_id WHERE payment_id = ?"
        );
    }

    public void replaceForSeconds(UUID id, String state, int ttlSeconds) {
        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        // Mutation mới sẽ đặt lại TTL nếu nó thắng LWW.
        session.execute(updateWithTtl.bind(ttlSeconds, state, id));
    }

    public void replaceWithoutTtl(UUID id, String state) {
        // Với bảng không có default TTL: cell mới không TTL.
        session.execute(updateWithoutTtl.bind(state, id));
    }

    public void replaceUntil(UUID id, String state, Instant expiresAt) {
        long secondsLeft = Duration.between(clock.instant(), expiresAt)
            .getSeconds();
        if (secondsLeft <= 0) {
            throw new IllegalStateException("Object already expired");
        }
        int ttlSeconds = Math.toIntExact(secondsLeft);
        // Đồng thời phải kiểm tra giới hạn TTL của Cassandra/cluster.
        replaceForSeconds(id, state, ttlSeconds);
    }

    public void inspect(UUID id) {
        Row row = session.execute(inspect.bind(id)).one();
        if (row == null) {
            System.out.println("No live row");
            return;
        }
        String state = row.getString("state");
        Integer ttl = row.isNull("ttl_s") ? null : row.getInt("ttl_s");
        Long writeUs = row.isNull("write_us") ? null : row.getLong("write_us");
        System.out.printf("state=%s ttl=%s writeUs=%s%n",
            state, ttl, writeUs);
    }
}
```

**Vì sao `replaceUntil` cần kiểm tra kỹ hơn trên production?** Ví dụ dùng số giây **làm tròn xuống** từ hạn chót. Nếu còn ít hơn một giây, nó từ chối thay vì vô tình gán TTL 0. Tuy nhiên:

- Phải bảo đảm `clock` đủ đáng tin cậy và các host đồng bộ thời gian.
- TTL thực được tính trong quá trình Cassandra xử lý ghi, có độ trễ; TTL theo giây không phải cơ chế deadline chính xác tới mili giây.
- Không phải mọi TTL dương `int` đều hợp lệ trên mọi phiên bản Cassandra; kiểm tra mức tối đa và chính sách overflow của cluster.
- Nếu yêu cầu kiểm soát hạn tuyệt đối, thêm cột `expires_at timestamp` và xác thực giá trị đó ở đường đọc/sử dụng nghiệp vụ.
- Các chuyển trạng thái thanh toán quan trọng nên có **điều kiện cập nhật** hoặc chuỗi sự kiện, không chỉ dựa vào TTL/LWW.

Đoạn mã cố tình tách **ghi với TTL mới** và **ghi không chỉ định TTL** để thể hiện hai chính sách khác nhau. Nếu bảng được thay đổi sang `default_time_to_live > 0`, hành vi của `replaceWithoutTtl` cũng thay đổi theo TTL mặc định đó.

## 13. Các trường hợp đặc biệt: collection, UDT, counter và LWT

### 13.1. Collection và UDT

Một cột collection/UDT **không frozen** có thể được biểu diễn bằng nhiều cell:

- `map<text,text>`: cập nhật `settings['theme']` có thể đặt TTL mới **cho key đó** mà không gia hạn các key khác.
- `set<text>` và `list<text>`: những phần tử được ghi ở các thời điểm khác nhau có thể hết TTL khác nhau.
- UDT không frozen: `SET address.city = 'Hue'` có thể tạo phiên bản field `city` với TTL mới, không tự đặt lại `street`.

Ngược lại, với `frozen<map<...>>` hoặc `frozen<udt>`, toàn bộ giá trị là **một cell**. Ghi lại giá trị frozen tạo timestamp/TTL của **cả cell**, không có TTL riêng cho từng thành phần.

Nếu nghiệp vụ cần cập nhật phần tử độc lập với thời hạn sống rõ ràng, chọn dạng lưu trữ phù hợp hoặc thiết kế **mỗi phần tử thành row riêng** theo truy vấn. Collection không nên tăng trưởng vô hạn trong một partition.

### 13.2. Counter

Counter có quy tắc cập nhật đặc thù, không hỗ trợ `USING TTL` như cột dữ liệu thường. Không đem ví dụ cập nhật scalar + TTL áp dụng cho counter.

### 13.3. LWT và điều kiện nghiệp vụ

Khi nhiều dịch vụ cùng ghi một trạng thái, **LWT** (*lightweight transaction*) với `IF` cho phép kiểm tra điều kiện cập nhật theo cơ chế Paxos, ví dụ:

```sql
-- Ví dụ trên một UUID khác, chỉ cập nhật nếu trạng thái đang là PENDING.
UPDATE payment_state_by_id
SET state = 'PAID'
WHERE payment_id = 40404040-4040-4040-8040-404040404040
IF state = 'PENDING';
```

Kết quả chứa `[applied]` để client biết điều kiện đã thỏa hay chưa. LWT có chi phí cao hơn ghi thường và không nên kết hợp tùy tiện với các yêu cầu tự cấp `USING TIMESTAMP`. TTL vẫn chỉ quản lý vòng đời dữ liệu; **không tự đảm bảo chuyển trạng thái có điều kiện**.

## 14. Replication, compaction và repair khi TTL bị đặt lại

Cassandra có thể lưu một partition trên nhiều replica theo **replication factor (RF)**. Một cập nhật cell có TTL mới được điều phối đến replica; các node không nhất thiết nhận request đồng thời. **Consistency level** (`ONE`, `QUORUM`, `ALL`) ràng buộc điều kiện phản hồi cho đọc/ghi, nhưng không thay đổi luật LWW hoặc ý nghĩa của `USING TTL`.

| Cơ chế | Liên hệ với TTL mới |
|---|---|
| **Mutation timestamp** | Chọn phiên bản cell thắng; TTL quan sát gắn với phiên bản thắng |
| **TTL/expiration metadata** | Cho biết khi nào phiên bản đó hết hiệu lực |
| **Replication** | Một số replica có thể tạm thời chứa phiên bản khác, cần reconciliation |
| **Consistency level** | Quy định mức replica tham gia/xác nhận; không cộng TTL cũ và mới |
| **Repair** | Giúp replica đối chiếu và hội tụ phiên bản dữ liệu |
| **Compaction** | Dọn SSTable/tombstone an toàn khi điều kiện cho phép |

Khi một cell hết TTL, nó được xử lý tương tự dữ liệu đã xóa; Cassandra phải bảo vệ trước khả năng **bản cũ từ replica** xuất hiện lại. Do đó, việc TTL kết thúc **không có nghĩa byte dữ liệu lập tức biến mất khỏi đĩa**. Tombstone, `gc_grace_seconds`, lịch repair và chính sách compaction ảnh hưởng tới khả năng dọn vật lý an toàn.

Một workload liên tục “làm mới” TTL với tần suất cao có thể tạo nhiều phiên bản trong SSTable và tăng áp lực compaction/tombstone, nhất là khi TTL ngắn và lưu lượng lớn. Hãy đo **latency, tỷ lệ ghi, số lượng tombstone, dung lượng đĩa và tần suất repair** thay vì chỉ quan sát `ttl()` ở một vài khóa.

Không hạ `gc_grace_seconds` hay can thiệp trực tiếp SSTable chỉ để giải quyết “TTL không reset”; trước tiên phải xác nhận mutation có thắng LWW và client đang dùng chính sách TTL nào.

## 15. Checklist chẩn đoán: vì sao TTL sau `UPDATE` không như mong đợi?

Truy vấn đúng partition key và cell cần quan sát:

```sql
SELECT payment_id,
       state, ttl(state) AS state_ttl_s,
       writetime(state) AS state_write_us,
       updated_by, ttl(updated_by) AS updated_by_ttl_s
FROM payment_state_by_id
WHERE payment_id = 10101010-1010-4010-8010-101010101010;
```

| Triệu chứng | Giả thuyết chính | Điều cần kiểm tra |
|---|---|---|
| TTL gần 120 ngay sau cập nhật, trước đó gần 300 | Bình thường: phiên bản mới có TTL 120 | Đúng cell, đúng thời điểm update |
| `ttl(state) = null` nhưng `state` còn | Cell mới **không có TTL** | CQL bỏ `USING TTL`, `USING TTL 0`, TTL mặc định |
| `ttl(state)` vẫn là TTL cũ | Mutation mới **không thắng** hoặc đọc phiên bản khác | `writetime(state)`, `USING TIMESTAMP`, clock skew, replica/CL |
| TTL sau ghi gần 900 dù lệnh không có TTL | Bảng có **default_time_to_live = 900** | Schema hiện tại, đường CQL thực tế |
| TTL mới đang giảm dù value không đổi | Ghi cùng giá trị tạo phiên bản cell mới | Timestamp/TTL của lần ghi lặp |
| TTL của `state` đổi nhưng `updated_by` không đổi | Chỉ ghi `state` | Các cột được `SET` trong mutation |
| Giá trị biến mất trước khi TTL cũ kết thúc | Phiên bản mới có TTL ngắn hơn, hoặc delete | Lịch sử mutation, TTL của bản thắng |
| Giá trị đã hết TTL nhưng vẫn chiếm đĩa | Dữ liệu/tombstone chờ compaction an toàn | SSTable, compaction, repair |
| Retry khiến thời gian sống dài hơn kỳ vọng | Ứng dụng tạo mutation mới với hạn mới | Event ID, retry policy, mutation timestamp, `expires_at` |

**Ba bước nhanh nhất** khi điều tra:

1. Đọc **giá trị, `ttl()` và `writetime()` của đúng cell** đang bị nghi vấn.
2. Kiểm tra **CQL cuối cùng** và **TTL mặc định của bảng**; phân biệt mutation nào đã thực sự ghi cell.
3. Đối chiếu **nguồn mutation timestamp, log retry và trạng thái replica**, tránh quy lỗi cho TTL khi nguyên nhân là LWW/clock skew.

`ttl(column) = null` **không tự chứng minh** cell đã hết hạn. Nếu value vẫn tồn tại, khả năng thường gặp là **phiên bản hiện tại không có TTL**. Nếu value không còn sống, có thể do hết TTL, DELETE, chưa được ghi hoặc reconciliation.

## 16. Bài tập tự kiểm tra

**Câu 1.** Lúc 10:00 ghi `status = A USING TTL 300`. Lúc 10:01 ghi `status = B USING TTL 120` và B thắng. Nếu không có ghi khác, B hết hạn lúc nào?

**Đáp án:** Khoảng **10:03**, tức 120 giây từ lần ghi B. Không cộng 240 giây còn lại của A.

**Câu 2.** Cùng tình huống trên nhưng lần ghi B có TTL 600. Hạn mới xấp xỉ lúc nào?

**Đáp án:** **10:11**, tức 600 giây tính từ 10:01.

**Câu 3.** Một cell có TTL 60 giây. Ứng dụng ghi lại **cùng giá trị** với `USING TTL 300` và mutation thắng. TTL có reset không?

**Đáp án:** **Có.** Giá trị có thể không đổi nhưng metadata phiên bản cell mới có TTL khoảng 300 giây.

**Câu 4.** Bảng có `default_time_to_live = 0`. Một `UPDATE` ghi lại cell từng có TTL nhưng **không có `USING TTL`**. Kết quả nếu mutation thắng?

**Đáp án:** Phiên bản mới **không TTL**, nên `ttl(cell) = null` khi cell còn sống.

**Câu 5.** Bảng có `default_time_to_live = 900`. `UPDATE ... SET value = 'X'` không có TTL riêng tạo thời hạn mới nào?

**Đáp án:** TTL **900 giây** cho phiên bản cell được ghi, nếu mutation thắng.

**Câu 6.** Hai cột `state` và `updated_by` có TTL 300 lúc ban đầu. Chỉ cập nhật `state` với TTL 120. `updated_by` có reset TTL không?

**Đáp án:** **Không.** `updated_by` giữ thời hạn thuộc phiên bản của chính nó.

**Câu 7.** A được ghi với timestamp 500 và TTL 300. B được ghi sau với timestamp 400 và TTL 30. Sau hai lệnh, `ttl(column)` có chắc gần 30 không?

**Đáp án:** **Không.** B thua LWW, nên cell vẫn có giá trị/TTL của A nếu A chưa hết hạn.

**Câu 8.** Retry token sau khi đã hết hạn; ứng dụng tính số giây còn lại là 0 rồi gọi `USING TTL 0`. Có đúng không?

**Đáp án:** **Sai và nguy hiểm**: TTL 0 nghĩa là **không hết hạn**, không phải hết hạn ngay. Phải từ chối ghi token đã hết hạn hoặc xử lý ở luồng nghiệp vụ phù hợp.

**Câu 9.** Một cell mới có TTL 30 thay cell cũ có TTL 3600. Khi cell mới hết hạn, bản cũ có tự hiện lại không?

**Đáp án:** **Không được giả định vậy.** TTL không lưu stack phiên bản. Cassandra dùng metadata hết hạn/tombstone để ngăn bản cũ xuất hiện lại; nếu muốn khôi phục trạng thái trước, ứng dụng phải chủ động ghi sự kiện/phiên bản hợp lệ mới.

---

**Ghi nhớ:** Khi cập nhật một giá trị có TTL, **mutation thắng LWW tạo phiên bản cell mới và thời hạn sống mới**. TTL mới tính bằng giây **từ lần ghi mới**, không cộng dồn TTL còn lại hay giữ nguyên hạn cũ. Không chỉ định TTL có thể **loại bỏ TTL** (bảng không có TTL mặc định) hoặc **áp dụng default TTL** (bảng có `default_time_to_live`); `USING TTL 0` nghĩa là **không TTL**, không phải hết hạn ngay. Hãy quan sát `ttl()` cùng `writetime()`, kiểm soát retry và dùng `expires_at` khi nghiệp vụ cần hạn tuyệt đối.
