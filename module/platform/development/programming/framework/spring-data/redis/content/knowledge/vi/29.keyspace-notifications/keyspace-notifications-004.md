# Sự kiện hết hạn và khác biệt với thời điểm TTL chạm không trong Spring Data Redis

## 1. Vì sao TTL hết mà sự kiện `expired` chưa đến?

Giả sử một ứng dụng Spring Boot lưu mã xác thực vào Redis với TTL 30 giây. Nhóm phát triển đăng ký nhận thông báo khóa hết hạn để cập nhật trạng thái phiên làm việc. Sau khi chạy thử, họ thấy:

- TTL của key giảm dần từ `30` về `1`, rồi có lúc trả `0`.
- Một số key biến mất ngay khi được truy cập, trong khi những key ít ai đọc có thể được dọn sau đó.
- Listener nhận `expired` không đúng chính xác giây thứ 30; có lúc thông báo đến trễ.
- Sau khi ứng dụng mất kết nối và kết nối lại, một số sự kiện hết hạn không được gửi bù.
- Xóa key bằng `DEL` hoặc yêu cầu `EXPIRE key 0` không nhất thiết tạo sự kiện `expired` như họ kỳ vọng.

Đây không chỉ là vấn đề cấu hình Spring Data Redis. Nó bắt nguồn từ **cơ chế hết hạn của Redis** và **cách Redis phát keyspace notifications**.

Điểm mấu chốt:

> **TTL chạm mốc hết hạn là điều kiện để một key không còn hợp lệ; sự kiện `expired` được phát khi Redis thực sự xử lý việc xóa key do hết hạn. Hai thời điểm này không được bảo đảm trùng nhau.**

Trong Redis, key có thời hạn sống được xác định theo deadline. Nhưng việc thu hồi bộ nhớ và phát notification không phải một bộ định thời chính xác đến từng key, chạy callback ngay tại deadline. Redis sử dụng các cơ chế **xóa khi truy cập (lazy expiration)** và **quét xóa chủ động (active expiration)**.

Vì vậy, **không nên dùng key expiration event như một bộ lập lịch công việc có yêu cầu chạy đúng thời điểm, giao chắc chắn hoặc có khả năng replay**.

Sau bài học, bạn có thể:

1. Phân biệt deadline hết hạn, TTL còn lại, key bị loại khỏi keyspace và notification được publish.
2. Hiểu `TTL`, `PTTL`, `EXPIRE`, `PEXPIRE`, `EXPIREAT`, `PERSIST` và các kết quả đặc biệt `-1`, `-2`.
3. Giải thích lazy expiration và active expiration.
4. Cấu hình `notify-keyspace-events`, phân biệt `expired`, `expire`, `del` và `evicted`.
5. Nhận thông báo Redis bằng `RedisMessageListenerContainer`, `ChannelTopic` hoặc `PatternTopic`.
6. Hiểu tích hợp Redis Repository với `RedisKeyExpiredEvent` và giới hạn của shadow copy.
7. Nhận diện vấn đề mất event, sự kiện đến muộn, nhiều node Redis Cluster và độ trễ listener.
8. Thiết kế giải pháp phù hợp nếu nghiệp vụ cần xử lý deadline đáng tin cậy.

## 2. Ba thời điểm phải tách biệt

Với một key có TTL, ít nhất có ba mốc quan trọng:

**Mốc A — gán deadline:** khi `SET ... EX`, `EXPIRE`, `PEXPIRE` hoặc cấu hình TTL trong Spring Data Redis thiết lập thời hạn cho key.

**Mốc B — deadline đã tới:** thời gian còn lại của key hết; về mặt ngữ nghĩa key đã hết hạn và không còn là dữ liệu hợp lệ.

**Mốc C — Redis xử lý xóa key và phát sự kiện:** khi cơ chế lazy hoặc active expiration thực sự phát hiện/xử lý key hết hạn, Redis có thể publish notification `expired` nếu tính năng đã bật.

Minh họa:

```text
Thời gian ------------------------------------------------------------>

t = 0s                        t = 30s                    t = 30s + Δ
  |                               |                            |
  | SET code:123 X EX 30          | Deadline đã tới            | Active scan
  |                               |                            | phát hiện key
  |                               |                            | và xóa
  v                               v                            v
  +-------------------------------+----------------------------+
       Key hợp lệ theo TTL           Key đã hết hạn logic
                                     nhưng có thể chưa được
                                     quét xóa vật lý

                    Nếu có GET/EXISTS truy cập key đã hết hạn:
                              Redis có thể xóa lazy
                              và phát event tại đây
```

`Δ` là khoảng trễ **không có SLA thời gian cố định** chỉ từ việc dùng `EXPIRE`. Nó phụ thuộc tải, việc key có được truy cập không, chu kỳ quét, cấu hình Redis và nhiều yếu tố vận hành.

Thông báo có thể đến rất sát deadline trong thử nghiệm nhỏ, nhưng không được dùng kết quả đó để suy ra Redis cam kết gọi listener chính xác ở mốc TTL bằng 0.

### 2.1. Vì sao key hết hạn logic vẫn có thể chiếm RAM thêm một thời gian?

Redis phải giữ nhiều key và xử lý nhiều tác vụ. Việc đặt một timer độc lập có callback cứng cho từng key không phải mô hình expiration thường dùng.

Một số key đã quá deadline vẫn có thể còn trong cấu trúc nội bộ đến khi được truy cập hoặc được active expiration quét tới. Khi một lệnh truy cập key đã hết hạn, Redis xử lý nó như key không còn hợp lệ; cơ chế lazy có thể loại bỏ key và trả kết quả không tồn tại.

Điều này dẫn đến sự khác biệt:

```text
Key không còn hợp lệ để đọc
    ≠
Đã có notification `expired` tại đúng timestamp deadline
```

Đồng thời, dữ liệu có deadline đã qua không có nghĩa một application listener nhất định đang online để nhận được sự kiện.

### 2.2. Bốn khái niệm dễ bị trộn

| Khái niệm | Câu hỏi trả lời | Bản chất |
|---|---|---|
| TTL còn lại | Key còn thời gian hợp lệ bao lâu? | Số giây/mili giây ước tính tại lúc đọc |
| Deadline | Key phải được coi là hết hạn từ thời điểm nào? | Thông tin thời gian hết hạn |
| Expiration processing | Redis đã phát hiện/xử lý xóa key quá hạn chưa? | Thao tác nội bộ lazy hoặc active |
| Key expiration event | Redis có publish thông báo `expired` chưa? | Pub/Sub notification, phụ thuộc xử lý xóa và cấu hình |

Một hệ thống muốn “hết hạn thì không còn dùng được” có thể chỉ cần TTL. Một hệ thống muốn “khi đến hạn phải tạo hóa đơn, gửi email hoặc chuyển trạng thái bền vững” cần một cơ chế đáng tin cậy hơn notification.

## 3. Redis lưu và áp dụng TTL như thế nào?

Redis cho phép gắn thời hạn cho một key bằng các lệnh khác nhau.

Ví dụ:

```redis
SET verification:123 abc123 EX 30
```

Key được ghi với thời hạn sống 30 giây.

Đặt thời hạn bằng lệnh riêng:

```redis
SET verification:456 def456
EXPIRE verification:456 30
```

Đặt thời hạn mili giây:

```redis
SET verification:789 ghi789 PX 1500
```

Đặt TTL cho key đang tồn tại:

```redis
PEXPIRE verification:456 2500
```

Xác định deadline tuyệt đối:

```redis
EXPIREAT verification:456 1893456000
```

Trong ví dụ, `1893456000` là Unix timestamp tính bằng **giây**; `PEXPIREAT` nhận timestamp tính bằng **mili giây**. Redis tính deadline dựa trên thời gian hệ thống.

### 3.1. Redis TTL là theo key, không phải từng field thông thường

Với một Redis String hoặc Hash đơn giản, `EXPIRE` và `TTL` làm việc với **Redis key**:

```redis
HSET session:123 userId u-7 state ACTIVE
EXPIRE session:123 60
```

Thời hạn trên có tác động đến cả `session:123`, không chỉ trường `state`. Trong các phiên bản Redis có tính năng field-level expiration, đó là API riêng; không nên trộn nó với keyspace expiration notification và vòng đời của toàn key đang được bàn ở đây.

### 3.2. Một số lệnh làm thay đổi TTL

| Thao tác | Tác động thường gặp |
|---|---|
| `SET key value EX 30` | Tạo/ghi đè giá trị và thiết lập thời hạn 30 giây |
| `EXPIRE key 30` | Thiết lập lại thời hạn với mốc tính từ lúc gọi |
| `PEXPIRE key 1500` | Thiết lập thời hạn bằng mili giây |
| `PERSIST key` | Bỏ TTL; key trở thành không có deadline tự hết hạn |
| `SET key newValue` | Thông thường thay giá trị và xóa TTL cũ nếu không dùng tùy chọn giữ TTL |
| `SET key newValue KEEPTTL` | Giữ thời hạn trước đó của key nếu được hỗ trợ |
| `DEL key` | Xóa key tường minh, không chờ deadline |
| `UNLINK key` | Gỡ liên kết key và giải phóng bộ nhớ bất đồng bộ theo cơ chế command |
| `RENAME` | Chuyển key và các thông tin liên quan theo ngữ nghĩa lệnh, gồm TTL khi áp dụng |
| Lệnh chỉ đọc giá trị | Thông thường không làm mới TTL, trừ một số lệnh/tùy chọn có ngữ nghĩa riêng |

Đừng giả định hoạt động đọc thông thường tự tạo **sliding expiration**. Nếu ứng dụng muốn phiên còn hoạt động được kéo dài thời hạn, nó phải thiết kế thao tác refresh TTL phù hợp.

### 3.3. Thay đổi giá trị có thể vô tình làm mất TTL

Ví dụ:

```redis
SET session:123 active EX 30
TTL session:123
SET session:123 refreshed
TTL session:123
```

Sau lệnh `SET` không có `KEEPTTL` hoặc expiration option, key thường trở thành key không có thời hạn, và `TTL` có thể trả `-1`. Khi đó sẽ không có `expired` theo deadline cũ bởi vì deadline đã bị hủy.

Trong Spring Data Redis, tùy thao tác ghi và API cụ thể, cũng cần kiểm tra hành vi TTL khi thay đổi entity hoặc key trực tiếp. Không nên suy chỉ từ tên method `save` hoặc `set` rằng deadline cũ được giữ nguyên.

## 4. Đọc TTL và PTTL đúng cách

Redis cung cấp hai lệnh:

```redis
TTL verification:123
PTTL verification:123
```

- `TTL` trả số **giây** còn lại, làm tròn theo ngữ nghĩa lệnh.
- `PTTL` trả số **mili giây** còn lại, hữu ích khi cần quan sát sát deadline.

Các giá trị đặc biệt rất quan trọng:

| Giá trị | `TTL`/`PTTL` có nghĩa gì? |
|---:|---|
| Số dương | Key tồn tại, có deadline và còn khoảng thời gian dương |
| `0` | Có thể key còn tồn tại nhưng thời gian còn lại rất nhỏ theo đơn vị trả về; **không đồng nghĩa đã phát event** |
| `-1` | Key tồn tại nhưng **không có TTL** |
| `-2` | Key **không tồn tại** tại thời điểm lệnh kiểm tra, kể cả trường hợp đã hết hạn |
 
### 4.1. `TTL = 0` không có nghĩa event đã được gửi

Giả sử key còn 600 mili giây:

```text
PTTL key -> 600
TTL  key -> 0
```

`TTL` hiển thị `0` vì thời gian còn lại tính theo giây nguyên, nhưng key vẫn đang có thời hạn sống dương. Nó có thể được truy cập hợp lệ cho đến khi hết hạn thật.

Do đó:

> **Đừng kiểm tra `TTL == 0` rồi kết luận key đã bị xóa hoặc Spring listener đã nhận `expired`.**

Nếu ứng dụng cần độ phân giải nhỏ hơn một giây để hiển thị countdown, có thể dùng `PTTL`. Nhưng ngay cả `PTTL` cũng chỉ là phép đọc thời gian còn lại tại thời điểm gọi, không phải bằng chứng event đã được publish.

### 4.2. `TTL = -2` cũng không chứng minh listener đã thấy event

Ví dụ:

```redis
TTL missing:key
```

trả `-2` nếu key không tồn tại. Key có thể chưa từng tồn tại, đã bị xóa bằng `DEL`, đã hết hạn hoặc đã bị eviction. Từ `-2` không thể suy ra nguyên nhân key biến mất, càng không thể suy ra consumer đã nhận một thông báo.

Muốn biết nguyên nhân, cần quan sát hành vi ghi/xóa và sự kiện theo loại cùng với dữ liệu nghiệp vụ khác.

### 4.3. Kiểm tra EXPIRE và thời hạn còn lại bằng Spring Data Redis

Dùng `StringRedisTemplate`:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class VerificationCodeStore {

    private final StringRedisTemplate redis;

    public VerificationCodeStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String tokenId, String code) {
        String key = "verification:" + tokenId;

        redis.opsForValue().set(
            key,
            code,
            Duration.ofSeconds(30)
        );
    }

    public Duration remaining(String tokenId) {
        String key = "verification:" + tokenId;

        Long millis = redis.getExpire(
            key,
            TimeUnit.MILLISECONDS
        );

        if (millis == null) {
            throw new IllegalStateException(
                "Could not read remaining TTL"
            );
        }

        if (millis == -2L) {
            // Key không tồn tại.
            return Duration.ZERO;
        }

        if (millis == -1L) {
            // Không có TTL; không nên giả định sẽ nhận expired.
            throw new IllegalStateException(
                "Key exists without expiration"
            );
        }

        return Duration.ofMillis(millis);
    }
}
```

Ở đây `getExpire(key, TimeUnit.MILLISECONDS)` tương ứng ý định lấy TTL ở độ phân giải mili giây. Ví dụ trả `Duration.ZERO` cho key không tồn tại nhằm minh họa một lựa chọn API; trong ứng dụng thật, nên trả một kiểu kết quả phân biệt rõ `NOT_FOUND`, `PERSISTENT` và `EXPIRING` nếu nghiệp vụ cần biết nguyên nhân.

**Không dùng `remaining() == Duration.ZERO` để kích hoạt side effect một lần duy nhất** vì hai request có thể cùng thấy hết hạn, hoặc key không tồn tại từ trước.

## 5. Lazy expiration: xóa khi truy cập

Redis có cơ chế **lazy expiration**, còn được hiểu là kiểm tra thời hạn khi một key được truy cập qua command phù hợp.

Ví dụ:

```redis
SET demo:lazy value PX 1000
```

Sau khi deadline đã qua, một lệnh như:

```redis
GET demo:lazy
```

có thể khiến Redis nhận ra key đã hết hạn, xử lý xóa và trả `nil`.

Luồng minh họa:

```text
t0: SET demo:lazy value PX 1000
       |
       v
t1: deadline hết hạn
       |
       | Key có thể chưa được active scan tới.
       |
       v
t2: GET demo:lazy
       |
       +--> Redis kiểm tra expire time
       |
       +--> Key đã quá deadline
       |
       +--> Loại key hết hạn
       |
       +--> Nếu notifications đã bật:
                phát __keyevent@0__:expired
       |
       v
GET trả nil
```

**Điểm đáng nhớ:** chính một thao tác đọc key đã hết hạn có thể kích hoạt xử lý xóa. Vì vậy, khi thử nghiệm bằng cách gọi `GET` liên tục rồi quan sát event, bạn đang tác động đến cơ chế lazy expiration. Thời gian event thấy được không hoàn toàn độc lập với hành vi kiểm thử.

### 5.1. Key không được đọc có thể vẫn được dọn

Redis không chỉ dựa vào thao tác truy cập. Nếu một key quá hạn nhưng không ai gọi `GET`/`EXISTS`, **active expiration** vẫn có thể xóa nó sau đó.

Do vậy, không nên kết luận “key sẽ tồn tại mãi nếu không ai đọc”. Ngược lại, cũng không nên kết luận active expiration sẽ xóa đúng tại deadline của mọi key.

### 5.2. Lazy expiration không đồng nghĩa listener chạy đồng bộ với GET

Việc Redis phát một notification và việc một Java listener xử lý notification là hai bước khác nhau:

```text
Redis xử lý xóa key
      |
      +--> Tạo Pub/Sub event
                  |
                  +--> Network
                  |
                  +--> Redis client / listener container
                  |
                  +--> Thread handler Java
```

Một lệnh `GET` có thể trả `nil` trước khi code Java callback nhìn thấy event do độ trễ mạng, scheduling hoặc xử lý khác nhau. Không nên gắn yêu cầu đồng bộ nghiệp vụ vào giả định “GET trả nil thì callback chắc chắn đã hoàn tất”.

## 6. Active expiration: Redis quét và xóa key hết hạn

Redis sử dụng cơ chế **active expiration** để chủ động tìm và xóa các key có deadline đã qua, ngay cả khi các key đó không được ứng dụng truy cập.

Về mặt ý tưởng, Redis định kỳ lấy mẫu các key có expire time, kiểm tra deadline và xóa những key quá hạn. Thuật toán và cách phân bổ ngân sách CPU được cải tiến qua các phiên bản Redis; chi tiết số lượng mẫu và heuristics không nên coi là API ổn định cho ứng dụng.

Sơ đồ:

```text
Redis chứa nhiều key có TTL:
    k1: expired
    k2: expires in 20s
    k3: expired
    k4: expires in 2s
    k5: expired
    ...

Active expiration cycle:
    chọn các key có timeout để xem xét
           |
           +--> k1 quá hạn: xóa, có thể phát expired
           +--> k2 còn hạn: giữ
           +--> k3 quá hạn: xóa, có thể phát expired
           ...

Các key khác được xem trong những lượt tiếp theo.
```

### 6.1. Vì sao sự kiện có thể đến muộn?

- Redis phải phục vụ các lệnh khác ngoài tác vụ dọn hết hạn.
- Số key có TTL rất lớn, nhiều key hết hạn cùng thời điểm.
- Redis dành ngân sách CPU có giới hạn cho active expiration.
- Key ít được truy cập nên không có lazy expiration kích hoạt sớm.
- Cấu hình, phiên bản Redis, giới hạn CPU và tình trạng tải khác nhau.
- Redis Cluster có nhiều node; mỗi node xử lý expiration cho dữ liệu mình sở hữu.
- Sau khi Redis phát event, còn có thời gian vận chuyển và xử lý ở client.

Do vậy, thời điểm nhận event có thể được mô tả:

```text
T_listener
    = T_deadline
    + độ trễ đến lúc Redis xử lý xóa
    + độ trễ truyền notification
    + độ trễ xử lý listener
```

Đây là mô hình để phân tích, không phải cam kết rằng cả ba thành phần đều dương và đo độc lập được trong mọi trường hợp. Ý quan trọng là **ứng dụng không điều khiển chính xác độ trễ đó bằng TTL**.

### 6.2. Có thể điều chỉnh nhịp active expiration không?

Redis có các tham số vận hành liên quan như `hz` và `active-expire-effort` ở những phiên bản hỗ trợ. Chúng ảnh hưởng đến mức độ Redis dành tài nguyên cho hoạt động nền, nhưng tăng chúng có trade-off về CPU và latency.

Trong môi trường được phép:

```redis
CONFIG GET hz
CONFIG GET active-expire-effort
```

Không nên tùy ý đổi các tham số này chỉ vì muốn “event đến đúng mili giây”. Chúng **không chuyển Redis expiration thành hệ thống scheduler có bảo đảm chính xác**. Với Redis managed service, việc thay đổi configuration có thể bị giới hạn.

## 7. Sự kiện `expire` khác sự kiện `expired`

Tên rất giống nhau nhưng chỉ hai thời điểm khác nhau:

- **`expire`**: sự kiện thuộc nhóm generic khi thao tác thiết lập timeout cho key thành công (trong các điều kiện tương ứng).
- **`expired`**: sự kiện phát khi Redis **xóa key vì quá hạn** theo cơ chế expiration.

Ví dụ:

```redis
SET demo:ttl value
EXPIRE demo:ttl 30
```

Ở thời điểm `EXPIRE demo:ttl 30`, key được **gắn deadline**. Nếu bật thông báo phù hợp, Redis có thể phát event `expire` lúc này.

Sau khi deadline đi qua và Redis thực sự dọn key, Redis có thể phát event **`expired`**. Đây là hai bước riêng:

```text
t0: EXPIRE demo:ttl 30
    |
    +--> Event "expire" (đã thiết lập TTL; nếu bật nhóm generic)
    |
t0 + 30s:
    +--> Deadline key đã qua
           |
           +--> Redis xóa do expiration
                   |
                   +--> Event "expired" (nếu bật nhóm x)
```

**Không đăng ký nghe `expire` rồi hiểu nó là sự kiện key đã chết.** Một key được đặt TTL 24 giờ có thể phát `expire` ngay lúc cấu hình, nhưng vẫn tồn tại trong 24 giờ tiếp theo.

### 7.1. `expired` và `del` cũng khác nhau

Nếu xóa tường minh:

```redis
DEL demo:ttl
```

Redis phát event loại xóa key (như `del` nếu bật nhóm sự kiện tương ứng), **không phải một `expired` thông thường**.

Nếu đặt thời hạn bằng 0 hoặc thời điểm đã qua:

```redis
EXPIRE demo:ttl 0
```

khi key đang tồn tại, Redis xử lý xóa ngay theo ngữ nghĩa command. Trong Redis, trường hợp timeout âm hoặc bằng 0, hay `EXPIREAT` với thời điểm đã qua, phát event `del` thay vì `expired` theo tài liệu Redis về keyspace notifications.

Vì thế, một handler chỉ nghe `expired` **không thể bao quát mọi cách key biến mất**.

### 7.2. `evicted` không phải `expired`

Redis có thể xóa key do **memory eviction** khi áp dụng `maxmemory` và chính sách chọn key. Event lúc đó là `evicted`, không phải `expired`.

| Nguyên nhân key biến mất | Ví dụ | Loại event đáng quan sát |
|---|---|---|
| TTL đã qua, Redis xử lý expiration | `SET key value EX 3`, sau đó hết hạn | `expired` |
| Client chủ động xóa | `DEL key` | `del` |
| Client đặt thời hạn ngay lập tức | `EXPIRE key 0` | `del` |
| Redis loại key do áp lực bộ nhớ | `maxmemory` + eviction | `evicted` |
| Ghi đè/đổi kiểu dữ liệu theo command | `SET`, `RENAME`, ... | Event tương ứng với lệnh và cấu hình |
| Không có key từ đầu | `TTL missing:key -> -2` | Không thể suy ra phải có event |

Một hệ thống cần “dọn tài nguyên khi key không còn nữa vì bất cứ lý do gì” không thể chỉ nghe `expired` rồi giả định đầy đủ. Tuy nhiên, nghe nhiều loại event vẫn **không biến Pub/Sub thành nguồn sự kiện bền vững**.

## 8. Bật Redis keyspace notifications

Redis **không nhất thiết bật keyspace notifications theo mặc định**, vì phát event có thêm chi phí xử lý. Cấu hình liên quan là:

```redis
CONFIG GET notify-keyspace-events
```

Nếu được phép thay đổi runtime:

```redis
CONFIG SET notify-keyspace-events Ex
```

Trong đó:

- `E`: bật loại channel **keyevent**.
- `x`: chọn sự kiện **expired**.
- `K`: bật loại channel **keyspace**.
- `g`: chọn nhóm generic command events, trong đó có một số sự kiện như `del` và `expire`.
- `e`: chọn sự kiện **evicted**; đây là chữ thường `e`, khác chữ hoa `E`.

Một số cấu hình:

| Cấu hình | Ý nghĩa tiêu biểu |
|---|---|
| `Ex` | Phát keyevent notifications cho `expired` |
| `Kx` | Phát keyspace notifications cho `expired` |
| `KEx` | Phát cả keyspace và keyevent notifications cho `expired` |
| `Egx` | Phát keyevent notifications cho nhóm generic và expired |
| `Ege` | Phát keyevent notifications cho generic và evicted, không tự thêm `expired` |
| Chuỗi trống | Không bật keyspace notifications |

Phải bật **ít nhất một trong `K` hoặc `E`** cùng với các ký tự chọn nhóm event thì cấu hình mới có ý nghĩa phát notification tương ứng.

Với ứng dụng Spring chỉ cần biết key hết hạn và lắng nghe channel `__keyevent@0__:expired`, `Ex` là ví dụ phù hợp.

### 8.1. Cấu hình trong redis.conf

Ở môi trường bạn quản lý Redis server, có thể dùng:

```conf
notify-keyspace-events Ex
```

Đối với dịch vụ managed Redis, thường cấu hình qua parameter group, console hoặc cơ chế quản trị do nhà cung cấp hỗ trợ. `CONFIG SET` có thể bị cấm hoặc bị reset sau restart tùy môi trường. Không nên để application buộc Redis bật cấu hình bằng lệnh bị cấm rồi làm toàn bộ startup thất bại.

### 8.2. Bật event gây tác động gì?

Khi bật notification, Redis phải tạo các Pub/Sub message tương ứng mỗi khi event đủ điều kiện xảy ra. Trên hệ thống nhiều key có TTL ngắn, số event có thể rất lớn. Các listener, connection và network cũng chịu tải.

Chỉ bật các nhóm thực sự cần. Tránh bật quá nhiều sự kiện chỉ để phục vụ một handler expiration đơn giản mà chưa cân nhắc QPS, network, CPU và phạm vi bảo mật.

## 9. Keyevent channel và keyspace channel khác nhau thế nào?

Redis cung cấp hai cách biểu diễn cùng một sự kiện.

### 9.1. Keyevent notifications: channel là loại event

Với DB số 0 và event `expired`, tên channel:

```text
__keyevent@0__:expired
```

Khi key `verification:123` hết hạn và Redis xử lý xóa, message logic là:

```text
channel = "__keyevent@0__:expired"
payload = "verification:123"
```

Người nghe biết **sự kiện gì** từ channel, và biết **key nào** từ payload.

Với cấu hình `Ex`, subscribe:

```redis
SUBSCRIBE __keyevent@0__:expired
```

Đây là cách thường dùng khi cần nghe **mọi key hết hạn trong một Redis logical database** rồi lọc key theo namespace ở application.

### 9.2. Keyspace notifications: channel là tên key

Với cùng một key, channel dạng:

```text
__keyspace@0__:verification:123
```

Payload:

```text
expired
```

Ở đây channel mang **tên key**, còn body mang **loại event**.

Với cấu hình `Kx`, có thể subscribe theo pattern:

```redis
PSUBSCRIBE __keyspace@0__:verification:*
```

Nếu mọi key `verification:*` phát `expired`, listener nhận channel theo tên từng key và payload `"expired"`.

### 9.3. Bảng đối chiếu

| Tiêu chí | Keyevent | Keyspace |
|---|---|---|
| Prefix channel | `__keyevent@...__:` | `__keyspace@...__:` |
| Channel đại diện | Event type | Key name |
| Payload đại diện | Key name | Event type |
| Cần bật ký tự | `E` + nhóm sự kiện | `K` + nhóm sự kiện |
| Ví dụ cấu hình nghe expired | `Ex` | `Kx` |
| Ví dụ subscribe | `__keyevent@0__:expired` | `__keyspace@0__:verification:*` |
| Hữu ích khi | Quan tâm mọi key của một loại event | Quan tâm các event của một nhóm key |

Nếu người viết handler nhầm kênh, lỗi rất dễ xuất hiện:

```java
// Sai nếu nghe __keyspace@0__:verification:123:
// message.getBody() = "expired", KHÔNG phải tên key.
```

Trong thực tế cần quyết định rõ dạng subscription rồi viết logic parse channel/body tương ứng. Dạng keyevent thường dễ dùng nhất để nghe `expired` và lấy tên key trực tiếp.

## 10. Thử nghiệm bằng Redis CLI

Mở hai terminal kết nối đến cùng Redis DB 0.

Terminal A — đăng ký nhận `expired`:

```bash
redis-cli
```

```redis
SUBSCRIBE __keyevent@0__:expired
```

Terminal B — bật event trong môi trường được phép:

```redis
CONFIG SET notify-keyspace-events Ex
```

Tạo key có TTL ngắn:

```redis
SET demo:expiry:1 hello PX 3000
```

Quan sát:

```redis
PTTL demo:expiry:1
TTL demo:expiry:1
```

Sau khi key hết hạn, terminal A có thể nhận:

```text
message
__keyevent@0__:expired
demo:expiry:1
```

**Không yêu cầu event phải xuất hiện chính xác 3.000 mili giây sau `SET`.** Khi Redis đang bận hoặc key chưa được quét, notification có thể đến muộn.

### 10.1. Quan sát TTL hiển thị 0 nhưng key còn tồn tại

Dùng key TTL 1,5 giây:

```redis
SET demo:expiry:short hello PX 1500
```

Khi đã qua khoảng 0,7–1,2 giây, nếu gọi kịp:

```redis
TTL demo:expiry:short
PTTL demo:expiry:short
GET demo:expiry:short
```

`TTL` có thể cho `0`, trong khi `PTTL` còn một số mili giây dương và `GET` vẫn trả `"hello"`.

Đây là tình huống thực tế cho thấy **`TTL == 0` không đồng nghĩa key đã hết hạn logic hoặc event đã được phát**.

Lưu ý: chạy lệnh thủ công có độ trễ. Có thể không bắt được chính xác khoảng thời gian còn dưới một giây trong mọi lần thử.

### 10.2. Thử xóa tường minh

Mở thêm một terminal khác theo dõi event chung:

```redis
CONFIG SET notify-keyspace-events Egx
```

Subscribe ở một connection:

```redis
PSUBSCRIBE __keyevent@0__:*
```

Với key mới:

```redis
SET demo:expiry:manual hello EX 30
DEL demo:expiry:manual
```

Có thể quan sát các event theo đúng nhóm đã bật, trong đó xóa tường minh thuộc `del`, **không phải** `expired`. Nếu chỉ subscribe `__keyevent@0__:expired`, người nghe không được thông báo `del` chỉ vì key vừa biến mất.

### 10.3. Thử EXPIRE 0

```redis
SET demo:expiry:immediate hello
EXPIRE demo:expiry:immediate 0
```

Trong Redis, timeout bằng 0 khiến key bị xóa ngay. Hệ thống phát loại event `del` trong trường hợp này theo ngữ nghĩa lệnh; không nên dùng trường hợp đó để kiểm thử delivery của `expired` mà không phân biệt loại event.

### 10.4. Kiểm tra cấu hình trước và sau

```redis
CONFIG GET notify-keyspace-events
```

Kết quả có thể là chuỗi đã chuẩn hóa theo Redis, không nhất thiết giữ nguyên thứ tự chữ cái bạn vừa truyền. Điều quan trọng là có cờ `E` và `x` cho trường hợp `__keyevent@0__:expired`.

Không tự thay đổi các cấu hình trên production chỉ để làm bài thực hành.

## 11. Spring Data Redis: nghe event bằng RedisMessageListenerContainer

Trong Spring Boot, một cách rõ ràng để nhận keyevent expiration là dùng `RedisMessageListenerContainer`.

Ví dụ này lắng nghe event `expired` từ Redis DB 0, trong đó **body chứa tên key**. Listener chỉ làm log và phân loại; không dùng event như cơ chế bền vững để thực hiện một nghĩa vụ kinh doanh bắt buộc.

Dependency thường dùng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Cấu hình Redis ví dụ:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Kích hoạt `notify-keyspace-events Ex` **ở Redis server** bằng phương pháp quản trị phù hợp.

### 11.1. Một bean xử lý notification

```java
package com.example.expiration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class ExpiredKeyHandler {

    private static final Logger log =
        LoggerFactory.getLogger(ExpiredKeyHandler.class);

    public void onExpiredKey(String redisKey) {
        log.info("Redis key expired: {}", redisKey);

        if (redisKey.startsWith("verification:")) {
            // Ghi metric/telemetry hoặc thực hiện
            // tác vụ best-effort phù hợp.
            log.debug("Verification key expired: {}", redisKey);
        }
    }
}
```

Những key cùng Redis DB có thể thuộc nhiều namespace. Vì `Ex` gửi event cho mọi key hết hạn, hãy lọc key theo tiền tố hoặc hợp đồng đặt tên phù hợp trước khi quyết định xử lý.

Không nên log giá trị bí mật, session token hoặc payload nhạy cảm từ tên key. Nếu key chứa dữ liệu nhạy cảm, cân nhắc đặt ID không tiết lộ thông tin nghiệp vụ trong key name.

### 11.2. Đăng ký container và listener

```java
package com.example.expiration;

import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class ExpirationListenerConfiguration {

    @Bean("expiredKeyMessageListener")
    MessageListener expiredKeyMessageListener(
            ExpiredKeyHandler handler) {

        return (message, pattern) -> {
            String key = new String(
                message.getBody(),
                StandardCharsets.UTF_8
            );

            handler.onExpiredKey(key);
        };
    }

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory connectionFactory,
            @Qualifier("expiredKeyMessageListener")
            MessageListener listener) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        container.addMessageListener(
            listener,
            new ChannelTopic("__keyevent@0__:expired")
        );

        return container;
    }
}
```

Ở đây:

- `ChannelTopic` đăng ký chính xác channel keyevent expiration của DB 0.
- `message.getBody()` chứa bytes tên key, được giải mã UTF-8 theo quy ước key name ví dụ.
- `message.getChannel()` chứa bytes của `__keyevent@0__:expired`.
- Callback không nhận giá trị cũ đã bị xóa; chỉ nhận tên key.
- Container quản lý connection Pub/Sub và đăng ký listener theo lifecycle của Spring.

**Quan trọng:** các cấu hình bean ở đây mang tính ví dụ. Nếu ứng dụng đã có `RedisMessageListenerContainer`, hãy đăng ký thêm listener vào container được quản lý chung thay vì vô tình tạo các container trùng tên hoặc đăng ký cùng handler nhiều lần.

### 11.3. Lắng nghe nhiều DB hoặc dạng keyspace

Nếu muốn lắng nghe keyevent `expired` ở mọi logical DB thông thường:

```java
new PatternTopic("__keyevent@*__:expired")
```

Trong callback pattern, `pattern` cho biết mẫu đã khớp; tên channel thực tế nằm trong `message.getChannel()`.

Nếu muốn nghe các event của nhóm key `verification:*` theo **keyspace**:

```java
new PatternTopic("__keyspace@0__:verification:*")
```

thì phải bật `Kx` và hiểu rằng **body là tên event**, ví dụ `"expired"`, còn tên key nằm trong `message.getChannel()` sau prefix. Không thể dùng nguyên handler của keyevent mà vẫn coi body là tên key.

Với Redis Cluster, cách đăng ký nhiều DB không phải giải pháp mở rộng Cluster: Redis Cluster thông thường chỉ hỗ trợ DB 0. Cần xử lý phạm vi node riêng như phần sau.

## 12. RedisKeyExpiredEvent và Redis Repository

Spring Data Redis còn có tích hợp cho các entity được lưu bằng **Redis Repository**, chẳng hạn:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "verificationTokens", timeToLive = 30)
public class VerificationToken {

    @Id
    private String id;

    private String userId;

    // Constructor, getter và setter tương ứng.
}
```

Khi lưu entity qua Redis Repository, key chính có TTL theo cấu hình phù hợp. Tích hợp Redis Repository có thể đăng ký listener expiration và chuyển thông báo thành **Spring application event** như `RedisKeyExpiredEvent`, tùy cấu hình repository và lifecycle listener.

Ví dụ một event handler Spring:

```java
import org.springframework.context.event.EventListener;
import org.springframework.data.redis.core.RedisKeyExpiredEvent;
import org.springframework.stereotype.Component;

@Component
public class VerificationTokenExpiryObserver {

    @EventListener
    public void onKeyExpired(RedisKeyExpiredEvent<?> event) {
        // Nhận biết có sự kiện expiration từ Redis Repository.
        // Không giả định entity gốc vẫn đọc được ở thời điểm này.
    }
}
```

**Không được hiểu `@RedisHash(timeToLive = ...)` tự cung cấp một scheduler có giao hàng chắc chắn.** Cơ chế repository vẫn dựa trên thông báo expiration của Redis trong những cấu hình có hỗ trợ và sự kiện không được giữ bền vững khi ứng dụng offline.

### 12.1. Vì sao event có thể không chứa toàn bộ entity?

Khi Redis phát `expired`, key gốc đã bị xóa do hết hạn. Nếu listener ngay lúc đó gọi:

```redis
GET verificationTokens:token-123
```

thì key chính thường đã không còn, kết quả có thể là `nil`. Với một entity Hash, `HGETALL` trên key cũ cũng không thể lấy lại nội dung đã xóa.

Keyevent notification thông thường chỉ có tên key, **không kèm value trước khi bị xóa**.

### 12.2. Shadow copy (phantom copy) trong Redis Repository

Để hỗ trợ gửi nội dung entity trong sự kiện expiration, Spring Data Redis Repository có thể lưu thêm một **bản sao phụ** của entity và để bản sao sống thêm một khoảng thời gian sau TTL chính. Cơ chế này thường được gọi là *shadow copy* hoặc *phantom copy* trong tài liệu Spring Data Redis.

Về mặt logic:

```text
Lưu verificationTokens:token-123
    |
    +--> Hash chính, TTL 30s
    |
    +--> Bản sao hỗ trợ expiration event,
         có thời gian sống bổ sung (nếu cấu hình bật)

Sau 30s:
    Hash chính hết hạn và Redis xóa
    |
    +--> Event expired
    |
    +--> Listener/repository có thể lấy dữ liệu
         từ bản sao khi nó vẫn tồn tại
```

Chi phí của cách này là **RAM, số key, số thao tác ghi và quản lý vòng đời bản sao**. Nó không phải bảo đảm phát event hoặc replay khi subscriber mất kết nối.

Khi tính năng shadow copy tắt, Spring có thể chỉ có thông tin định danh/key cho event. Handler không nên mặc định nhận được DTO đầy đủ trong mọi cấu hình.

### 12.3. Repository secondary index có thể cần expiration event để dọn

Nếu entity dùng `@Indexed`, repository có thể duy trì các Set chỉ mục chứa ID của entity. Khi Hash chính hết hạn, những quan hệ index cần được dọn để tránh ID stale.

Nếu listener expiration bị tắt, kết nối đứt hoặc Redis không phát notification, việc cleanup index phụ thuộc vào cơ chế repository/cấu hình và có thể không diễn ra như mong muốn. Vì vậy, trong hệ thống có Redis Repository + TTL + secondary index, **keyspace notifications còn ảnh hưởng đến tính nhất quán của index**, không chỉ đến callback ứng dụng.

Không nên tự xóa key Hash bằng Redis CLI rồi giả định các Set chỉ mục phụ luôn được cập nhật đầy đủ.

### 12.4. Listener khởi động muộn

Tùy cấu hình, Spring Data Redis Repository có thể đăng ký listener khi khởi động hoặc khi lần đầu thực sự cần TTL. Nếu có key hết hạn trước khi listener bắt đầu subscribe, những event đã phát không được replay.

Với ứng dụng sử dụng expiration event để duy trì dữ liệu phụ, cần hiểu chính sách khởi tạo listener và đánh giá yêu cầu khi service restart. Kể cả khởi động listener từ rất sớm, vẫn không thể loại bỏ sự cố mất kết nối hoặc downtime.

### 12.5. Managed Redis và CONFIG SET bị cấm

Một số cấu hình listener trong Spring Data Redis cố thiết lập `notify-keyspace-events` qua `CONFIG SET` nếu được yêu cầu. Dịch vụ Redis managed có thể cấm `CONFIG`.

Trong những trường hợp như vậy, cần:

1. Cấu hình keyspace notifications ở cấp Redis service bằng cơ chế được hỗ trợ.
2. Tránh để Spring tự gọi `CONFIG SET` khi provider không cho phép.
3. Với listener/repository tương ứng, dùng tùy chọn cấu hình phù hợp để không tự chỉnh `notify-keyspace-events` (ví dụ cấu hình giá trị trống cho keyspace notifications config parameter khi API hỗ trợ).
4. Kiểm tra listener thực sự subscribe và nhận event trên Redis đang dùng.

Không được coi “ứng dụng Spring khởi động thành công” là bằng chứng chắc chắn Redis đã bật `Ex`.

## 13. Vì sao Pub/Sub expiration event không bền vững?

Redis keyspace notifications sử dụng **Redis Pub/Sub**. Pub/Sub thông thường không duy trì backlog cho những subscriber tạm thời vắng mặt và không có cơ chế ACK/replay tự động.

Ví dụ:

```text
t0: Listener đang online.
t1: Listener mất kết nối.
t2: Redis xóa key hết hạn và phát event.
t3: Listener kết nối lại.

Kết quả:
    Event ở t2 không được Redis tự phát lại.
```

Tương tự:

```text
t0: Redis xóa key hết hạn.
t1: Spring service mới bắt đầu subscribe.

Kết quả:
    Service không thể yêu cầu Redis replay event ở t0
    chỉ bằng cách gọi SUBSCRIBE.
```

Việc Redis đã phát event không có nghĩa **mọi application instance** nhận thành công. Một listener chậm, bị restart hoặc có lỗi xử lý cũng có thể làm mất việc xử lý nghiệp vụ.

### 13.1. At-most-once và xử lý trùng là hai vấn đề khác nhau

Pub/Sub không tự retry thông điệp chưa ACK. Nhưng ứng dụng vẫn có thể thực hiện side effect trùng do:

- Nhiều instance cùng subscribe.
- Listener được đăng ký hai lần.
- Có đồng thời subscriber `ChannelTopic("__keyevent@0__:expired")` và pattern bao phủ cùng channel.
- Một quy trình khác cũng phát hiện deadline và xử lý cùng nghiệp vụ.
- Publisher/nghiệp vụ khác tạo lại key cùng tên.

Vì vậy, dù Redis Pub/Sub không có replay, **idempotency** vẫn cần thiết cho side effect quan trọng; riêng event expiration không đủ bảo đảm “đúng một lần”.

### 13.2. Event không chứa danh tính bất biến của phiên bản key

Giả sử key:

```text
session:123
```

đã hết hạn, rồi một request khác lập tức tạo lại cùng tên:

```text
t1: session:123 (phiên cũ) hết hạn và bị xóa
t2: Redis phát event expired cho "session:123"
t3: Request mới ghi lại session:123 (phiên mới)
t4: Listener nhận event của phiên cũ
```

Nếu listener tại t4 gọi `GET session:123`, nó có thể nhìn thấy **phiên mới**. Không được xóa hoặc thay đổi dữ liệu phiên mới chỉ vì nhận event cho **cùng tên key**.

Nên dùng key/token generation riêng, event ID hoặc version và thiết kế handler theo ngữ nghĩa **phiên bản dữ liệu**, không coi tên key là một định danh bất biến xuyên mọi lần tái tạo.

## 14. Đừng dùng expired event làm nguồn dữ liệu nghiệp vụ chính

Một số ví dụ dễ gây lỗi:

### 14.1. Gửi email đúng lúc mã ưu đãi hết hạn

Thiết kế sai:

```text
SET coupon:123 payload EX 86400

Listener:
    nhận expired coupon:123
    -> gửi email thông báo coupon hết hạn
```

Nếu listener tắt vào thời điểm Redis dọn key, email có thể không được gửi. Nếu Redis dọn muộn, email đến muộn. Nếu cần bảo đảm nghiệp vụ, việc gửi email cần được lên lịch hoặc ghi nhận bằng hệ thống có trạng thái bền vững, retry và idempotency.

### 14.2. Tự động hủy đơn hàng sau 15 phút

Nếu business invariant yêu cầu đơn hàng **không thể được thanh toán sau deadline**, hãy kiểm tra deadline ở nguồn dữ liệu giao dịch khi xử lý lệnh thanh toán. Đừng để event expiration là nơi duy nhất đổi trạng thái đơn hàng, vì event có thể trễ hoặc mất.

Có thể dùng Redis TTL để cache trạng thái tạm và notification làm tín hiệu best-effort, nhưng quyết định nghiệp vụ phải dựa trên deadline/transaction ở nơi sở hữu dữ liệu.

### 14.3. Thu hồi tài nguyên ngoài Redis

Ví dụ key giữ trạng thái `"reservation:123"` và khi expired thì phải giải phóng một slot trong hệ thống khác. Nếu subscriber không chạy, slot có thể bị giữ vô thời hạn. Cần một job reconciliation theo nguồn trạng thái bền vững hoặc cơ chế lease có deadline được hệ thống sở hữu tài nguyên tự kiểm tra.

### 14.4. Thống kê và quan sát ít ràng buộc

Nếu chỉ cần ghi metric “ước lượng số key vừa hết hạn” hoặc log chẩn đoán, Pub/Sub expiration có thể là một tín hiệu hữu ích với chấp nhận mất event. Nhưng không nên dùng số event quan sát được để suy ra chính xác toàn bộ số key đã hết hạn trong mọi tình huống mất kết nối.

## 15. Redis Cluster và phạm vi thông báo

Redis Cluster phân phối các key trên các primary node theo hash slot. Cơ chế **keyspace notifications** hoạt động trên node xử lý key tương ứng; thông báo keyspace/keyevent **không tự động được broadcast như một bản tin toàn cục đến mọi node Cluster**.

Ví dụ:

```text
Redis Cluster
  |
  +-- Primary A: slot của verification:101
  |       Redis xử lý expired và phát event local
  |
  +-- Primary B: slot của verification:102
  |       Redis xử lý expired và phát event local
  |
  +-- Primary C: slot của verification:103
          Redis xử lý expired và phát event local
```

Nếu listener chỉ subscribe connection tới Primary A, nó không được bảo đảm nhận notification của các key do B và C xử lý.

Cần:

- Hiểu rõ topology Redis Cluster và node nào phát keyevent.
- Thiết kế subscription tới các node cần theo dõi; xác nhận khả năng của driver/container trong phiên bản Spring Data Redis.
- Xử lý slot migration, resharding và failover.
- Theo dõi Redis config trên từng node liên quan.
- Chấp nhận vẫn có cửa sổ mất event khi node/connection đổi trạng thái.

Trong Redis Cluster thông thường chỉ sử dụng logical DB 0; ví dụ channel `__keyevent@0__:expired` vẫn cần đăng ký **đúng node** để quan sát toàn bộ Cluster.

**Không được suy rằng `PatternTopic("__keyevent@*__:expired")` sẽ tự nghe tất cả node.** Dấu `*` trong tên topic khớp phần DB trong channel, không phải wildcard node Cluster.

### 15.1. Redis replica và failover

Ở cấu hình có primary/replica, expiration và replication có những quy tắc riêng để đồng bộ thao tác xóa. Không nên suy rằng mỗi replica phát event giống hệt primary tại cùng timestamp. Khi failover, node sở hữu key và connection listener có thể thay đổi; ứng dụng cần đối chiếu với thiết kế quan sát của chính deployment.

Đối với ứng dụng quan trọng, keyspace notification trong Cluster càng không phải cơ chế duy nhất để ghi nhận workflow deadline.

## 16. Vòng đời listener và độ trễ phía Java

Ngay cả khi Redis phát `expired` kịp thời, application callback có thể xử lý sau đó.

Một listener chậm:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    // Gọi HTTP API không timeout, xử lý file,
    // hoặc thực hiện thao tác blocking kéo dài...
}
```

có thể chiếm thread xử lý, làm nhiều notification xếp chờ trong executor hoặc buffer. Redis Pub/Sub không biến những message đang chờ đó thành một queue bền vững.

Một số hướng thiết kế:

1. **Giữ callback ngắn**: decode key, phân loại, ghi metric hoặc phát yêu cầu có kiểm soát.
2. **Không làm I/O chậm trực tiếp** nếu có thể chuyển đến worker phù hợp.
3. **Giới hạn hàng đợi và concurrency** khi offload; queue không giới hạn gây rủi ro hết heap.
4. **Không dựa vào queue trong JVM để chống mất sự kiện khi restart**.
5. **Đặt timeout và backoff** cho phần công việc gọi hệ thống khác.
6. **Theo dõi reconnect, listener errors và tốc độ thông điệp**.
7. **Tránh handler chạy nhiều lần cùng nghiệp vụ** khi có nhiều instance subscription.

Nếu phải bảo đảm công việc cuối cùng được hoàn thành, sự kiện Pub/Sub nên là *hint* để đánh thức một luồng kiểm tra dữ liệu bền vững, không phải nguồn duy nhất mang trách nhiệm hoàn tất.

## 17. Cách đo độ trễ expiration notification

Muốn phân tích độ trễ, cần ghi nhận **deadline gốc** và thời điểm listener xử lý. Với một key chỉ chứa tên `"demo:123"`, khi key hết hạn bạn không còn giá trị gốc để suy ra thời hạn đã được đặt, trừ khi đã lưu timestamp ở nơi khác.

Một mô hình thử nghiệm:

```text
Ứng dụng tạo key tại T0, TTL = 5000 ms.
Ghi deadline dự kiến = T0 + 5000 ms
vào nơi quan sát độc lập.

Redis xóa key vào Tdelete.
Redis phát event tại Tpublish (gần với xử lý xóa).
Ứng dụng nhận tại Treceive.

Quan sát delta:
    Treceive - (T0 + 5000 ms)
```

Cần hiểu giá trị đo chịu ảnh hưởng:

- Đồng hồ máy ứng dụng và đồng hồ Redis có thể không đồng bộ tuyệt đối.
- Lúc client gửi `SET` và Redis áp dụng lệnh không chính xác bằng timestamp trước khi gửi.
- Network và thread scheduling ảnh hưởng thời điểm ghi log.
- `Tdelete` và `Tpublish` không dễ đo trực tiếp từ application qua event đơn giản.
- Event có thể bị bỏ lỡ hoàn toàn; không có `Treceive`.

Để đánh giá trễ, đo trên **nhiều key và nhiều mức tải**, theo phân phối p50/p95/p99 nếu cần. Không suy cam kết SLA từ một lần demo thành công.

### 17.1. Chỉ số nên theo dõi

| Chỉ số | Giúp trả lời câu hỏi |
|---|---|
| Số key được tạo có TTL | Workload expiration bao nhiêu? |
| Số event `expired` observer nhận | Observer nhìn thấy bao nhiêu notification? |
| Độ trễ dự kiến đến callback | Event đến muộn mức nào? |
| Số lỗi/reconnect Pub/Sub | Có cửa sổ bị mất notification không? |
| Listener handler latency | Callback có xử lý quá chậm không? |
| Redis expired key metrics | Redis thực sự dọn bao nhiêu key trong khoảng đo? |
| CPU và memory Redis | Active expiration có chịu tải cao không? |
| Event type `del`/`evicted` | Có key biến mất không phải do TTL không? |

Redis có thống kê `expired_keys` trong `INFO stats`, phản ánh số key bị xóa do expiration ở mức Redis process theo cách Redis đếm. Nó không phải số event mà một subscriber Java đã nhận thành công.

Trong môi trường Cluster, cần tổng hợp/hiểu số liệu từng node theo đúng phạm vi; không lấy một node làm đại diện cho toàn hệ thống.

## 18. Chẩn đoán khi không thấy expired event

Có thể đi theo thứ tự:

**Bước 1 — Key có thực sự được gắn TTL?**

```redis
TTL demo:expiry:1
PTTL demo:expiry:1
```

Nếu `-1`, key không có TTL. Nếu `-2`, key không tồn tại; chưa thể xác nhận nguyên nhân.

**Bước 2 — Redis notifications đã bật đúng loại?**

```redis
CONFIG GET notify-keyspace-events
```

Muốn nghe `__keyevent@0__:expired` thì phải có `E` và `x`. Chỉ bật `x` mà thiếu `E` hoặc `K` không đủ.

**Bước 3 — Listener đang subscribe đúng channel?**

Kiểm tra `ChannelTopic("__keyevent@0__:expired")` thay vì `__keyspace@0__:...`. Nếu muốn biết tên key từ body, chọn keyevent.

**Bước 4 — Cùng Redis instance/DB/node?**

Trong standalone, kiểm tra connection/database. Trong Cluster, cần kiểm tra node sở hữu key. Một listener chỉ nghe một primary có thể bỏ lỡ key ở primary khác.

**Bước 5 — Có thao tác xóa không phải expiration?**

Nếu ứng dụng gọi `DEL`, `UNLINK`, `EXPIRE key 0` hoặc key bị evict, đừng mong luôn thấy event `expired`. Bật loại event bổ sung theo nhu cầu chẩn đoán.

**Bước 6 — Subscriber có online khi Redis phát event?**

Pub/Sub không có backlog. Nếu listener mới kết nối sau deadline/dọn key, sự kiện đã qua không được replay.

**Bước 7 — Có đủ thời gian để active expiration chạy?**

Nếu chỉ kiểm tra ngay tại mốc TTL và key không được truy cập, event có thể đến muộn. Đừng đặt điều kiện “chậm hơn đúng 10 ms là lỗi” mà không có SLA thực tế.

**Bước 8 — Callback có lỗi không?**

Kiểm tra logs listener, cấu hình executor, exception, serializer, permission, network và thời gian xử lý.

**Bước 9 — Có trùng registration hoặc nhiều instance không?**

Nếu thấy hai lần xử lý cho cùng tên key, phân biệt event type, matched pattern, instance nguồn, lần tạo key mới và logic idempotency.

**Bước 10 — Có nhầm giữa observability và cam kết nghiệp vụ không?**

Nếu một tác vụ bắt buộc phải chạy đúng lúc, kết luận “notifications đang mất” có thể chưa phải nguyên nhân sâu xa; cần thiết kế lại bằng workflow có trạng thái bền vững và recovery.

## 19. Những ngộ nhận thường gặp

### “TTL bằng 0 thì key chắc chắn đã bị xóa”

Không chính xác. `TTL` trả theo giây nguyên nên một key còn vài trăm mili giây có thể trả `0`. `PTTL` giúp quan sát sát deadline hơn, nhưng cũng không cho biết listener đã chạy.

### “Đến giây 30 Redis sẽ chạy callback của tôi”

Không có callback Java được Redis bảo đảm chạy đúng timestamp deadline. Redis xóa bằng lazy/active expiration rồi publish thông báo best-effort; còn độ trễ truyền nhận.

### “Không ai GET key thì sẽ không bao giờ có expired event”

Không đúng. Active expiration có thể phát hiện và xóa key mà không cần truy cập. Nhưng thời điểm không được đảm bảo chính xác.

### “EXPIRE chính là expired”

Không đúng. `expire` thường gắn với lúc **thiết lập TTL**; `expired` gắn với lúc **Redis xóa key do quá hạn**.

### “EXPIRE key 0 sẽ gửi expired”

Không nên kỳ vọng vậy. Timeout bằng 0 khiến key bị xóa ngay và theo tài liệu keyspace notifications phát `del`, không phải `expired`.

### “DEL, eviction và expiration đều giống nhau”

Không. Đây là các nguyên nhân key biến mất khác nhau, với các event type như `del`, `evicted` và `expired`.

### “Redis phát event tức là Spring chắc chắn xử lý”

Không. Redis Pub/Sub không lưu backlog hoặc có ACK processing. Application có thể offline, crash, nhận trễ hoặc mất event.

### “PatternTopic trên Cluster sẽ nghe được tất cả node”

Không tự động. Pattern là so khớp tên channel, không phải cơ chế tổng hợp notification xuyên mọi primary.

### “KeyExpiredEvent sẽ chứa đầy đủ entity”

Không bảo đảm. Key chính đã bị xóa; nếu tích hợp repository cần payload có thể phải sử dụng shadow copy và trả thêm chi phí RAM, vẫn không bảo đảm giao event.

### “Chỉ cần tăng hz thì thời điểm expired sẽ chính xác”

Không. Tuning active expiration giúp điều chỉnh chi phí/độ trễ trong một số workload, không cung cấp hard real-time scheduler.

## 20. Thiết kế thay thế khi deadline là nghiệp vụ bắt buộc

Nếu hệ thống cần “đến lúc T phải xem xét và thực hiện công việc, có retry, không mất khi ứng dụng ngừng”, có thể chọn kiến trúc phù hợp hơn.

### 20.1. Lưu deadline bền vững trong database và chạy scheduler

Ví dụ bảng logic:

```sql
CREATE TABLE scheduled_jobs (
    job_id VARCHAR(100) PRIMARY KEY,
    due_at TIMESTAMP NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempts INTEGER NOT NULL
);
```

Worker định kỳ tìm những job đã đến hạn, claim bằng transaction/cơ chế khóa phù hợp của database, xử lý và cập nhật trạng thái. Khi worker crash, job vẫn có trong database và worker khác có thể retry.

```text
Create job --> DB lưu due_at
                  |
                  v
          Worker quét due_at <= now
                  |
                  v
             Claim job
                  |
                  v
            Execute + retry
                  |
                  v
        DONE / FAILED / DLQ
```

Cơ chế này có **độ trễ theo lịch polling và scheduling**; nó không bảo đảm chạy đúng mili giây, nhưng có thể bảo đảm lưu trách nhiệm xử lý và phục hồi tốt hơn Pub/Sub.

### 20.2. Redis Sorted Set làm chỉ mục deadline

Nếu ứng dụng muốn tận dụng Redis, có thể lưu deadline trong Sorted Set:

```redis
ZADD jobs:due 1893456000000 job-101
```

Trong đó score là Unix timestamp mili giây. Worker tìm ID tới hạn:

```redis
ZRANGEBYSCORE jobs:due -inf 1893456000000 LIMIT 0 100
```

Đây là ví dụ đọc logic; ứng dụng phải truyền timestamp hiện tại thích hợp. Cần **claim/removal nguyên tử** để tránh hai worker cùng lấy một job và phải có phương án recovery khi worker crash sau claim.

Không được đơn giản gọi `ZRANGEBYSCORE` rồi `ZREM` bằng hai bước không phối hợp và giả định không xảy ra race. Có thể dùng Lua/script trong phạm vi slot thích hợp hoặc lưu trạng thái job bền vững ở nơi khác.

Sorted Set chỉ giúp **tìm job đến hạn**, chưa tự cung cấp retry/ACK/durable side effect.

### 20.3. Redis Streams cho giao công việc có ACK

Redis Streams với consumer group, PEL và `XACK` giúp theo dõi công việc đã giao nhưng chưa xác nhận. Tuy nhiên, Stream **không tự hoãn thời điểm đọc tới deadline**. Nếu cần delayed job, thường cần thêm bộ phận scheduler đưa job đến hạn vào Stream, hoặc kết hợp cơ chế due index với Stream.

```text
Due scheduler / DB / ZSET
         |
         | job đã tới hạn
         v
Redis Stream
         |
         | XREADGROUP
         v
Consumer xử lý
         |
         +--> Thành công: XACK
         |
         +--> Thất bại: retry/recovery pending
```

Ngay cả khi dùng Streams, side effect quan trọng vẫn cần idempotency, dead-letter handling và retention hợp lý.

### 20.4. Redis TTL dùng cho lease, không dùng làm job scheduler

Với session hoặc lock thuê tài nguyên, TTL có thể là nguồn kiểm tra **lease còn hợp lệ không**. Ứng dụng có trách nhiệm không chấp nhận lease đã quá deadline dựa trên trạng thái được kiểm tra đúng cách.

Notification `expired` có thể giúp phát tín hiệu best-effort để dọn cache hoặc cập nhật metric, nhưng không nên là cách duy nhất quyết định lease đã hết hạn hay chưa.

### 20.5. Bảng lựa chọn

| Nhu cầu | Giải pháp phù hợp | Giới hạn cần hiểu |
|---|---|---|
| Dữ liệu cache tự biến mất sau 10 phút | TTL Redis | Không cần callback tại deadline |
| Mã xác thực không còn hợp lệ sau 30 giây | TTL + kiểm tra key/deadline khi xác thực | Không dựa vào listener để từ chối mã |
| Cập nhật metric khi key hết hạn, chấp nhận thiếu mẫu | Keyevent `expired` | Best-effort Pub/Sub |
| Gửi thông báo bắt buộc sau deadline | Scheduler có job state bền vững | Có độ trễ scheduling nhưng retry được |
| Xử lý công việc đã giao với ACK/recovery | Redis Streams / broker phù hợp | Phải thiết kế idempotency |
| Đánh thức job theo timestamp trong Redis | ZSET deadline + worker claim | Cần xử lý race và crash |
| Dọn Redis Repository secondary index | Cơ chế repository expiration + kiểm soát vận hành | Có thể bị ảnh hưởng nếu notification bỏ lỡ |
| Điều phối nghiệp vụ phải chính xác một lần | Transaction/idempotency/outbox phù hợp | Không thể suy ra từ `expired` |

## 21. Bài thực hành có hướng dẫn

### Bài 1 — TTL bằng 0 nhưng key còn hợp lệ

1. Trong Redis thử nghiệm, bật `notify-keyspace-events Ex`.
2. Tạo key: `SET lab:ttl:zero value PX 1500`.
3. Gọi `TTL`, `PTTL`, `GET` trong vài thời điểm.
4. Ghi nhận lần quan sát có `TTL = 0` nhưng `PTTL` vẫn dương.
5. Giải thích vì sao điều này không chứng minh sự kiện `expired` đã được publish.

### Bài 2 — So sánh lazy và active expiration

1. Mở subscriber `SUBSCRIBE __keyevent@0__:expired`.
2. Tạo một số key có TTL ngắn.
3. Với một nhóm key, liên tục kiểm tra bằng `GET` sau deadline.
4. Với nhóm còn lại, không truy cập trong một khoảng thời gian.
5. Ghi thời gian nhận event.
6. Giải thích vì sao việc truy cập có thể làm thay đổi thời điểm xử lý xóa.

Không dùng kết quả vài lần thử để đặt SLA cụ thể cho toàn Redis.

### Bài 3 — Phân biệt `expire`, `expired` và `del`

Bật loại event tương ứng:

```redis
CONFIG SET notify-keyspace-events Egx
PSUBSCRIBE __keyevent@0__:*
```

Tạo key và đặt TTL:

```redis
SET lab:events:a value
EXPIRE lab:events:a 3
```

Quan sát event thiết lập timeout và event xóa do quá hạn. Tiếp theo:

```redis
SET lab:events:b value
DEL lab:events:b
```

và:

```redis
SET lab:events:c value
EXPIRE lab:events:c 0
```

Phân biệt sự kiện tạo ra bởi ba đường xóa.

### Bài 4 — Keyevent so với keyspace

Chạy một subscriber keyevent:

```redis
SUBSCRIBE __keyevent@0__:expired
```

Chạy subscriber khác với cấu hình hỗ trợ keyspace:

```redis
CONFIG SET notify-keyspace-events KEx
PSUBSCRIBE __keyspace@0__:lab:*
```

Tạo một key `lab:demo` có TTL ngắn. So sánh:

- Channel của từng message.
- Body của từng message.
- Vai trò của `K` và `E`.
- Vì sao một `MessageListener` phải giải mã khác nhau cho hai kiểu subscription.

### Bài 5 — Listener Spring Boot

1. Cấu hình `notify-keyspace-events Ex` ở Redis.
2. Đăng ký `RedisMessageListenerContainer` với `ChannelTopic("__keyevent@0__:expired")`.
3. Dùng `StringRedisTemplate` lưu `verification:token-1` với TTL 5 giây.
4. Quan sát callback ghi log tên key sau khi Redis xử lý expiration.
5. Dừng ứng dụng trước khi TTL kết thúc, khởi động lại sau đó.
6. Giải thích vì sao callback không được replay cho sự kiện xảy ra khi ứng dụng offline.

### Bài 6 — Xóa key rồi tạo lại cùng tên

1. Đặt TTL ngắn cho key `lab:session:123`.
2. Sau khi key cũ hết hạn, tạo key mới cùng tên.
3. Quan sát một callback `expired` có thể đến sau khi key mới đã được tạo.
4. Giải thích vì sao handler không được tự động xóa key mới chỉ dựa trên tên key trong payload.
5. Đề xuất version/generation ID để tách hai incarnation của cùng key.

### Bài 7 — Thiết kế deadline tin cậy

Bài toán: đơn hàng chưa thanh toán phải được xem xét hủy sau 15 phút và phải có khả năng retry khi worker chết.

- Chỉ ra hai rủi ro nếu dùng `expired` làm trigger duy nhất.
- Đề xuất lưu `due_at` trong database hoặc ZSET có job state.
- Mô tả claim, retry, idempotency và kiểm tra trạng thái đơn trước khi hủy.
- Giải thích vai trò Redis TTL nếu vẫn muốn dùng để cache trạng thái tạm.

### Bài 8 — Cluster và phạm vi node

Giả sử Redis Cluster có ba primary. Hai key `verification:101` và `verification:102` nằm trên hai primary khác nhau.

- Vì sao `PatternTopic("__keyevent@*__:expired")` không tự gom mọi event của cả hai primary?
- Cần quan sát node nào?
- Điều gì xảy ra khi slot migration hoặc failover?
- Vì sao một nguồn job bền vững vẫn cần thiết cho tác vụ bắt buộc?

## 22. Câu hỏi tự đánh giá

1. Phân biệt deadline hết hạn, xóa key và thời điểm Java nhận callback.
2. Vì sao `TTL` có thể trả `0` khi key vẫn còn hợp lệ?
3. `TTL = -1` và `TTL = -2` khác nhau ra sao?
4. Khi nào lazy expiration có thể xảy ra?
5. Nếu key không được đọc, Redis còn cơ chế nào để xóa?
6. Sự kiện `expire` và `expired` thuộc hai thời điểm nào?
7. Tại sao `EXPIRE key 0` có thể tạo `del` thay vì `expired`?
8. Sự kiện `evicted` có liên quan gì tới `maxmemory`?
9. `notify-keyspace-events Ex` bật những notification nào?
10. Body của channel `__keyevent@0__:expired` chứa thông tin gì?
11. Body của channel `__keyspace@0__:mykey` chứa thông tin gì?
12. Vì sao callback không thể `GET` lại chắc chắn giá trị đã hết hạn?
13. Shadow copy của Spring Data Redis giải quyết vấn đề gì và có chi phí gì?
14. Vì sao app restart có thể làm mất các expiration notifications?
15. Trong Redis Cluster, listener chỉ nghe một node có đủ không?
16. Redis TTL có bảo đảm chạy job đúng tại deadline không?
17. Cách xử lý nào phù hợp nếu gửi email sau hạn là nghĩa vụ bắt buộc?
18. Vì sao listener nhận event cho tên key cũ không nên tùy ý sửa key vừa được tạo lại?
19. Độ trễ của active expiration và độ trễ của listener khác nhau ra sao?
20. Tại sao `expired_keys` trong `INFO stats` không phải số callback đã xử lý?

## 23. Ghi nhớ

- **TTL chạm deadline không đồng nghĩa Redis phát `expired` ngay lập tức.** Event được tạo khi Redis xử lý xóa key vì quá hạn.
- Redis dùng **lazy expiration** khi truy cập và **active expiration** khi quét chủ động; cả hai đều không phải scheduler chính xác theo từng key.
- `TTL = 0` có thể chỉ vì key còn dưới một giây; `PTTL` cho độ phân giải mili giây. `-1` là key tồn tại không TTL, `-2` là key không tồn tại.
- **`expire` khác `expired`**: một bên gắn với thiết lập deadline, bên kia với xóa key do hết hạn. `DEL`/`EXPIRE key 0` liên quan đến `del`, eviction liên quan đến `evicted`.
- Bật `notify-keyspace-events Ex` để nghe `__keyevent@0__:expired`; body là **tên key**. Với keyspace channel, channel mang tên key còn body mang tên event.
- Spring Data Redis có thể nhận event bằng `RedisMessageListenerContainer`, `ChannelTopic` hoặc listener expiration của Redis Repository. **Key đã hết hạn thường không thể đọc lại value**; shadow copy là một lựa chọn có thêm chi phí bộ nhớ.
- Keyspace notifications dựa trên **Pub/Sub best-effort**, không replay và không ACK end-to-end. Không được dùng làm trigger duy nhất cho công việc bắt buộc.
- Trên Redis Cluster, notification gắn với node xử lý key; **pattern channel không tự biến thành wildcard cho toàn bộ Cluster**.
- Để xử lý deadline đáng tin cậy, dùng scheduler/job state bền vững, ZSET + cơ chế claim/recovery, Redis Streams hoặc broker phù hợp, kết hợp idempotency và đối soát.
- Redis TTL rất phù hợp để xác định **thời gian hợp lệ của dữ liệu**, nhưng không tự bảo đảm **thời điểm và thành công của side effect nghiệp vụ**.

### Tài liệu tham khảo chính thức

- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis — Key expiration](https://redis.io/docs/latest/develop/use/keyspace/)
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/)
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/)
- [Redis — PEXPIRE](https://redis.io/docs/latest/commands/pexpire/)
- [Redis — PERSIST](https://redis.io/docs/latest/commands/persist/)
- [Redis — CONFIG SET](https://redis.io/docs/latest/commands/config-set/)
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis — Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Spring Data Redis — Pub/Sub messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
