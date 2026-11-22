# Đọc thời hạn còn lại và hiểu kết quả khóa không tồn tại hoặc không có TTL

Trong Spring Data Redis, **TTL** (*time to live*) là thời gian còn lại trước khi một Redis key hết hạn. Một lệnh đọc TTL không chỉ trả thời gian dương: Redis còn dùng **giá trị đặc biệt** để phân biệt một khóa đã mất với một khóa vẫn tồn tại nhưng không có expiration.

Ba trạng thái cần nhớ:

- **`-2`:** key không tồn tại tại thời điểm hỏi Redis.
- **`-1`:** key tồn tại nhưng **không có thời hạn hết hạn**.
- **`0` hoặc số dương:** key có expiration và còn thời gian theo độ phân giải của lệnh/đơn vị đọc.

Sự khác biệt này quan trọng với cache, session, dữ liệu tạm, khóa điều phối và các chính sách dọn dữ liệu. Nếu coi `-1` là “còn một giây” hoặc coi mọi giá trị không dương là key mất, ứng dụng có thể đưa ra quyết định sai.

Bài học thuộc chương **Hết hạn và loại bỏ** trong Spring Data Redis, tập trung vào Redis `TTL`/`PTTL`, Java API `getExpire()`, ý nghĩa sentinel, thao tác đặt/xóa TTL và những tình huống thay đổi đồng thời.

## 1. TTL là thời hạn còn lại, không phải thời điểm tạo key

Giả sử ứng dụng lưu cache một sản phẩm trong 15 phút:

~~~redis
SET cache:product:42 '{"id":"42","name":"Keyboard"}' EX 900
~~~

`EX 900` đặt expiration 900 giây kể từ lúc Redis thực thi lệnh. Sau đó:

~~~redis
TTL cache:product:42
~~~

trả số **giây còn lại**, ví dụ gần 900 nếu vừa ghi và gần 600 sau khoảng 5 phút. Vì đồng hồ vẫn trôi và lệnh qua mạng có độ trễ, không kỳ vọng kết quả phải luôn bằng chính xác 900 ngay sau ghi.

~~~text
T0: SET key value EX 900
     |
     |  Còn khoảng 900 giây
     v
T1: năm phút sau
     |
     |  Còn khoảng 600 giây
     v
T2: sau deadline
     |
     |  Key không còn khả dụng
     v
TTL key -> -2
~~~

TTL **không** tự nói được key được tạo lúc nào, ai ghi, đã từng bị thay thế chưa, hoặc lý do key không còn. Đây là phép đo tại thời điểm thực thi, không phải lịch sử đầy đủ.

## 2. Redis TTL và PTTL khác nhau thế nào?

Redis có hai lệnh cơ bản:

| Lệnh | Độ phân giải | Ví dụ |
|---|---|---|
| `TTL key` | Giây | `TTL cache:product:42` |
| `PTTL key` | Mili giây | `PTTL cache:product:42` |

Cả hai đều dùng `-2` cho key không tồn tại và `-1` cho key tồn tại nhưng không có expiration. Khi key có expiration, TTL cho số giây; PTTL cho số mili giây.

Ví dụ:

~~~redis
SET demo:ttl "hello" EX 30
TTL demo:ttl
PTTL demo:ttl
~~~

Nếu vừa ghi, `TTL` có thể gần 30 và `PTTL` gần 30000. Giá trị giảm dần khi thời gian trôi, không nhất thiết hai phép đọc chuyển đổi chính xác cho nhau vì thực hiện ở hai thời điểm khác nhau.

### 2.1. Key còn dưới một giây

~~~redis
SET demo:short "x" PX 700
TTL demo:short
PTTL demo:short
~~~

Nếu đọc kịp trước khi key biến mất, `TTL` có thể trả **0** do thời hạn còn dưới một giây; `PTTL` có thể trả vài trăm mili giây. Sau deadline, cả hai sẽ báo `-2`.

**`TTL = 0` không đồng nghĩa key không tồn tại.** Nếu cần làm việc với timeout ngắn hơn một giây, sử dụng `PTTL` hoặc Java API yêu cầu đơn vị mili giây.

### 2.2. Khi nào dùng giây, khi nào dùng mili giây?

- Với cache 15 phút, key hết hạn sau vài giờ hoặc thống kê thời hạn tổng quan, giây thường dễ hiểu và đủ dùng.
- Với deadline dưới một giây, polling có chu kỳ ngắn hoặc phân tích độ lệch expiration, mili giây diễn đạt tốt hơn.
- Không lấy `TTL` đã làm tròn theo giây rồi nhân 1000 và coi đó là giá trị mili giây chính xác.
- Cả hai kết quả đều chỉ là ảnh chụp. Key có thể bị thay đổi ngay sau khi Redis trả lời.

## 3. Hiểu chính xác -2: khóa không tồn tại

Ví dụ:

~~~redis
DEL demo:missing
TTL demo:missing
# -2

PTTL demo:missing
# -2
~~~

Giá trị `-2` có nghĩa key không tồn tại **tại thời điểm Redis xử lý lệnh**. Nó không cho biết vì sao.

Những nguyên nhân có thể gồm:

1. Key chưa bao giờ được tạo.
2. Key đã bị `DEL` hoặc `UNLINK`.
3. Key hết hạn theo TTL.
4. Key bị loại bỏ do chính sách eviction khi thiếu bộ nhớ.
5. Ứng dụng hỏi nhầm key prefix, database, Redis endpoint hoặc logical namespace.
6. Key đã được một request khác xóa trong lúc ứng dụng xử lý.

Do đó, **không thể suy từ `-2` rằng key chắc chắn đã hết hạn tự nhiên**. Nếu nghiệp vụ cần biết lý do xóa, phải có log, metric, event hoặc nguồn dữ liệu đáng tin cậy khác.

### 3.1. Key có thể hết hạn ngay giữa hai lời gọi

~~~text
Thread A: TTL cache:42 -> 1
               |
               | Thời gian trôi
               v
Thread A: GET cache:42 -> nil
~~~

Hai kết quả không mâu thuẫn. Khi đọc TTL, key còn hạn; lúc GET chạy, nó đã hết hạn hoặc bị xóa.

### 3.2. `EXISTS` khác gì với `TTL`?

~~~redis
EXISTS demo:missing
# 0

TTL demo:missing
# -2
~~~

Với một key, `EXISTS` cho biết có/không. `TTL` phân biệt thêm trạng thái **có expiration** hay **không có expiration**.

Nhưng gọi `EXISTS` rồi `TTL` trong hai lệnh riêng **không tạo snapshot nguyên tử**: một client khác có thể xóa hoặc tạo key giữa hai lệnh.

## 4. Hiểu chính xác -1: khóa tồn tại nhưng không có TTL

~~~redis
SET demo:persistent "hello"
TTL demo:persistent
# -1

GET demo:persistent
# "hello"
~~~

Redis tìm thấy key, nhưng key không có deadline expiration. Giá trị này không nói key đã hết hạn một giây trước hoặc sẽ hết hạn sau một giây.

Những nguyên nhân thường gặp:

- Ứng dụng tạo key bằng `SET` không kèm `EX`/`PX`.
- Key được tạo như dữ liệu không cần hết hạn.
- Lệnh `PERSIST` đã xóa expiration.
- Một lần `SET` ghi đè trước đó làm mất TTL.
- Nhiều service dùng cùng key nhưng không thống nhất chính sách expiration.

### 4.1. -1 có phải lỗi không?

**Phụ thuộc hợp đồng nghiệp vụ.**

| Loại key | `TTL = -1` có hợp lý không? |
|---|---|
| Cấu hình lâu dài của ứng dụng | Có thể hoàn toàn hợp lý |
| Bản ghi trạng thái cần tồn tại đến khi xóa thủ công | Có thể hợp lý |
| Cache sản phẩm 15 phút | Thường đáng điều tra |
| Session bắt buộc hết hạn sau 30 phút | Có thể là lỗi nghiêm trọng |
| Khóa điều phối bắt buộc có deadline | Không nên mặc nhiên chấp nhận |

Đừng sửa tất cả key có `TTL=-1` bằng cách gán một TTL ngẫu nhiên. Trước hết xác định chúng có được thiết kế là persistent hay không.

### 4.2. PERSIST giữ dữ liệu nhưng xóa thời hạn

~~~redis
SET demo:persist "value" EX 60
TTL demo:persist
# gần 60

PERSIST demo:persist
# 1 nếu key đang có expiration và expiration được gỡ

TTL demo:persist
# -1

GET demo:persist
# "value"
~~~

`PERSIST` không xóa key và không xóa value. Nó chỉ loại bỏ deadline.

## 5. Hiểu số 0: vẫn có expiration

Một ví dụ rất dễ hiểu sai:

~~~redis
SET demo:short "hello" PX 500
TTL demo:short
~~~

Nếu thao tác đủ nhanh, Redis có thể trả `0` vì còn chưa tới một giây. Nhưng key có thể vẫn có value:

~~~redis
GET demo:short
# Có thể còn "hello" nếu chưa hết hạn
~~~

Bảng diễn giải:

| Kết quả TTL | Diễn giải |
|---:|---|
| `-2` | Key không tồn tại |
| `-1` | Key tồn tại, không có expiration |
| `0` | Key có expiration, thời gian theo giây còn rất ngắn |
| `1` | Còn khoảng một giây theo phép đọc hiện tại |
| `30` | Còn khoảng 30 giây |
| `900` | Còn khoảng 15 phút |

**Sai lầm điển hình:** viết `if (ttl <= 0)` để kết luận key không tồn tại. Điều kiện này gộp cả persistent (`-1`), missing (`-2`) và sắp hết hạn (`0`).

Nếu thực sự cần phân loại ba trạng thái, điều kiện đúng phải kiểm tra **giá trị sentinel cụ thể**.

## 6. Ví dụ đầy đủ bằng Redis CLI

Có thể theo dõi trạng thái TTL của một key thử nghiệm theo trình tự.

### Bước 1 — Key chưa tồn tại

~~~redis
DEL lesson:ttl:state
TTL lesson:ttl:state
# -2
~~~

### Bước 2 — Tạo key không có expiration

~~~redis
SET lesson:ttl:state "value"
TTL lesson:ttl:state
# -1
~~~

### Bước 3 — Đặt TTL 60 giây

~~~redis
EXPIRE lesson:ttl:state 60
# 1 nếu đặt thành công

TTL lesson:ttl:state
# Gần 60

PTTL lesson:ttl:state
# Gần 60000
~~~

### Bước 4 — Loại bỏ TTL

~~~redis
PERSIST lesson:ttl:state
TTL lesson:ttl:state
# -1
~~~

### Bước 5 — Xóa key

~~~redis
DEL lesson:ttl:state
TTL lesson:ttl:state
# -2
~~~

Các giá trị gần 60 hoặc 60000 chỉ mang tính minh họa. Kết quả phụ thuộc thời gian đã trôi giữa các lệnh và việc client khác có sửa key hay không.

## 7. Spring Data Redis: getExpire()

Với template imperative, Spring Data Redis cho phép hỏi thời hạn còn lại:

~~~java
Long seconds = stringRedisTemplate.getExpire(key);
~~~

Overload có đơn vị:

~~~java
Long milliseconds = stringRedisTemplate.getExpire(
        key, java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

`getExpire(key)` dùng đơn vị giây. `getExpire(key, TimeUnit.MILLISECONDS)` giúp đọc thời gian còn lại theo mili giây.

Spring Data Redis chuyển kết quả của Redis về Java `Long`. Các trạng thái sentinel cần được giữ nguyên ý nghĩa:

- `-2L`: key không tồn tại.
- `-1L`: key tồn tại nhưng không có TTL.
- `0L` hoặc số dương: key có expiration.
- `null`: có thể gặp trong pipeline/transaction khi kết quả chưa có ngay; **không phải sentinel TTL của Redis**.

### 7.1. Ví dụ service đọc TTL

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TtlReaderService {

    private final StringRedisTemplate redis;

    public TtlReaderService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long getSeconds(String key) {
        return redis.getExpire(key);
    }

    public Long getMillis(String key) {
        return redis.getExpire(key, TimeUnit.MILLISECONDS);
    }
}
~~~

Ví dụ sử dụng:

~~~java
Long seconds = ttlReaderService.getSeconds("cache:product:42");
Long millis = ttlReaderService.getMillis("cache:product:42");
~~~

Nếu key còn 400 mili giây, cách đọc theo giây có thể trả 0 trong khi cách đọc theo mili giây trả một số dương dưới 1000.

### 7.2. Không unbox Long quá sớm

Không nên viết:

~~~java
long ttl = redis.getExpire(key);
~~~

nếu code có khả năng chạy trong ngữ cảnh mà API trả null, bởi việc unbox có thể ném `NullPointerException`.

An toàn hơn:

~~~java
Long ttl = redis.getExpire(key);

if (ttl == null) {
    throw new IllegalStateException("TTL result is unavailable");
}
~~~

Trong pipeline/transaction, việc nhận kết quả phải tuân theo API của ngữ cảnh đó, không coi null là key đã hết hạn.

### 7.3. Không biến giá trị sentinel thành Duration âm

Sai ý nghĩa:

~~~java
Long ttl = redis.getExpire(key);
Duration remaining = Duration.ofSeconds(ttl);
~~~

Nếu ttl bằng -1, kết quả Java chỉ là một Duration âm, còn ý nghĩa Redis là **key tồn tại nhưng không hết hạn**.

Cần phân loại trước khi tạo Duration.

## 8. Mô hình Java biểu diễn trạng thái expiration rõ ràng

Với các service có nhiều quyết định dựa trên TTL, nên dùng một kiểu domain có thể phân biệt **MISSING**, **PERSISTENT** và **EXPIRING**.

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class KeyLifetimeService {

    public enum State {
        MISSING,
        PERSISTENT,
        EXPIRING
    }

    public record Lifetime(State state, Duration remaining) {

        public static Lifetime missing() {
            return new Lifetime(State.MISSING, null);
        }

        public static Lifetime persistent() {
            return new Lifetime(State.PERSISTENT, null);
        }

        public static Lifetime expiring(Duration remaining) {
            return new Lifetime(State.EXPIRING, remaining);
        }
    }

    private final StringRedisTemplate redis;

    public KeyLifetimeService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Lifetime inspect(String key) {
        Long ttlMillis = redis.getExpire(key, TimeUnit.MILLISECONDS);

        if (ttlMillis == null) {
            throw new IllegalStateException(
                    "TTL result unavailable in current context");
        }

        if (ttlMillis == -2L) {
            return Lifetime.missing();
        }

        if (ttlMillis == -1L) {
            return Lifetime.persistent();
        }

        if (ttlMillis >= 0L) {
            return Lifetime.expiring(Duration.ofMillis(ttlMillis));
        }

        throw new IllegalStateException(
                "Unexpected Redis TTL: " + ttlMillis);
    }
}
~~~

Ví dụ cách sử dụng:

~~~java
KeyLifetimeService.Lifetime lifetime =
        keyLifetimeService.inspect("cache:product:42");

switch (lifetime.state()) {
    case MISSING -> {
        // Key không tồn tại khi đọc TTL.
    }

    case PERSISTENT -> {
        // Có value nhưng không có deadline.
    }

    case EXPIRING -> {
        Duration remaining = lifetime.remaining();
        // Có expiration, có thể còn ít hoặc nhiều thời gian.
    }
}
~~~

Cách này không ép `-1` hay `-2` thành một Duration âm. Một số dự án có thể dùng `Optional<Duration>`, sealed interface hoặc record con để tránh null trong field `remaining`. Dù dùng kiểu nào, **đừng làm mất thông tin ba trạng thái**.

## 9. Đặt TTL đúng cách từ Spring Data Redis

Với một cache String:

~~~java
import java.time.Duration;

redis.opsForValue().set(
        "cache:product:42",
        "{\"id\":\"42\",\"name\":\"Keyboard\"}",
        Duration.ofMinutes(15));
~~~

Đây là cách ghi **value và TTL trong cùng một thao tác** thông qua API thích hợp.

Đối với key đã tồn tại:

~~~java
Boolean changed = redis.expire(
        "cache:product:42",
        Duration.ofMinutes(15));
~~~

`expire` là thao tác **đặt hoặc thay TTL**, khác với `getExpire` là thao tác **đọc TTL**.

Hai lệnh độc lập:

~~~text
SET key value
EXPIRE key 900
~~~

có một khoảng ở giữa mà key đã có value nhưng chưa có TTL. Nếu tiến trình crash trong khoảng đó, key có thể tồn tại vô hạn. Khi ghi cache với TTL bắt buộc, nên dùng overload SET có Duration hoặc một phương pháp nguyên tử tương ứng.

### 9.1. Trả về Boolean có thể cần xử lý null

Trong ngữ cảnh gọi bình thường, `expire` cho biết lệnh có áp đặt thời hạn thành công hay không. Nếu key không tồn tại, Redis không thể gán expiration cho key đó.

Với API Spring Data Redis, giá trị Boolean vẫn có thể là null trong pipeline/transaction; tránh unbox mà không hiểu ngữ cảnh.

## 10. SET có thể làm TTL biến mất

Đây là nguyên nhân phổ biến khiến một cache bất ngờ nhận `TTL = -1`.

~~~redis
SET cache:user:42 '{"name":"Linh"}' EX 600

TTL cache:user:42
# Gần 600

SET cache:user:42 '{"name":"Linh","city":"Ha Noi"}'

TTL cache:user:42
# -1
~~~

Lần `SET` thứ hai ghi đè value mà không đặt expiration mới hoặc yêu cầu giữ TTL cũ. Redis mặc định loại bỏ expiration trước đó của key khi SET thông thường thay giá trị.

Vì vậy, nếu có nhiều đoạn mã cùng ghi một cache key, phải thống nhất:

- Mọi lần ghi có đặt TTL mới không?
- Muốn **gia hạn TTL** mỗi lần ghi hay **giữ deadline cũ**?
- Có đường ghi nào dùng `SET` không kèm TTL không?
- Có dùng API giữ TTL được phiên bản Redis/Spring Data Redis hỗ trợ không?

### 10.1. Các lệnh sửa tại chỗ thường giữ TTL key

Những lệnh như `HSET` trên Hash đã tồn tại hoặc `INCR` trên String số nguyên hiện hữu thông thường không tự reset expiration cấp key.

~~~redis
HSET cache:profile:42 city "Ha Noi"
EXPIRE cache:profile:42 600

HSET cache:profile:42 name "Linh"
TTL cache:profile:42
# TTL vẫn tiếp tục giảm
~~~

Với một key số nguyên:

~~~redis
SET counter:42 5 EX 600
INCR counter:42
TTL counter:42
# TTL vẫn còn, trừ khi key đã hết hạn
~~~

Nhưng không suy rộng sang mọi lệnh ghi: thay thế nguyên value bằng `SET` có semantics khác. Luôn kiểm tra cách mỗi thao tác ảnh hưởng đến TTL của key.

### 10.2. GET không tự gia hạn expiration

~~~redis
SET demo:read "value" EX 60
GET demo:read
TTL demo:read
~~~

Lệnh `GET` không làm TTL quay về 60 giây. Nếu muốn **sliding expiration**, ứng dụng phải chủ động làm mới deadline theo chính sách.

Redis có lệnh `GETEX` cho một số trường hợp đọc và cập nhật thời hạn trong một thao tác, nếu server/client hỗ trợ. Tuy nhiên, không được mặc định mọi lần đọc cache đều phải gia hạn TTL, vì điều đó có thể giữ một key “nóng” tồn tại mãi.

## 11. EXPIRE 0 không giống TTL trả 0

Cần phân biệt:

~~~redis
SET demo:zero "value" EX 60
TTL demo:zero
~~~

và:

~~~redis
EXPIRE demo:zero 0
~~~

Trong trường hợp thứ nhất, `TTL demo:zero` có thể trả 0 khi chỉ còn ít hơn một giây.

Trong trường hợp thứ hai, `EXPIRE key 0` yêu cầu một expiration không dương và khiến key hết hạn ngay theo semantics Redis. Hai chữ số 0 không mang cùng ý nghĩa.

**TTL là phép đo; EXPIRE là lệnh thay đổi trạng thái.**

## 12. TTL của Hash, List, Set và Sorted Set

TTL gắn với **Redis key**, bất kể key chứa cấu trúc nào:

~~~redis
HSET profile:42 name "Linh"
EXPIRE profile:42 600
TTL profile:42

LPUSH queue:recent "task-a" "task-b"
EXPIRE queue:recent 300
TTL queue:recent

SADD tags:42 premium beta
EXPIRE tags:42 3600
TTL tags:42

ZADD leaderboard:week 120 user:an
EXPIRE leaderboard:week 604800
TTL leaderboard:week
~~~

Một Redis Hash có thể chứa nhiều field, nhưng phép `TTL profile:42` thông thường đọc expiration của **toàn bộ key Hash**, không phải expiration của riêng field `name`.

Một số phiên bản Redis mới có cơ chế hết hạn theo field của Hash và các lệnh riêng tương ứng. Nếu hệ thống dùng tính năng đó, cần phân biệt key-level TTL và field-level TTL. Không suy rằng `TTL key` tự trả thời gian sống của một field.

## 13. Dùng TTL với cache: phân loại hành vi

Giả sử key `cache:product:42` phải hết hạn sau 15 phút.

| TTL đọc được | Ý nghĩa | Hành vi có thể phù hợp |
|---|---|---|
| `-2` | Cache không tồn tại | Cache miss, tải từ database nguồn |
| `-1` | Cache tồn tại nhưng không có expiration | Điều tra đường ghi/config nếu không có chủ đích |
| `0` | Cache sắp hết hạn | Có thể vẫn tồn tại lúc đọc; đừng tự coi missing |
| `> 0` | Cache còn thời gian sống | Ghi metric hoặc dùng cho UX nếu phù hợp |

Đối với **cache best-effort**, key không tồn tại là tình huống bình thường. Có thể đọc nguồn chính rồi nạp lại cache.

Tuy nhiên, cách viết:

~~~text
TTL key > 0
    => GET key chắc chắn trả value
~~~

là sai vì hai lệnh không nguyên tử và key có thể bị xóa, hết hạn hoặc evict ngay sau khi đọc TTL.

Nếu chỉ muốn lấy giá trị, nên đọc qua `opsForValue().get(key)` rồi xử lý cache hit/miss theo hợp đồng dữ liệu. TTL phù hợp với **giám sát vòng đời** hơn là làm một thao tác kiểm tra bắt buộc trước mọi GET.

### 13.1. Đừng xóa tất cả key TTL -1

Một hệ thống có thể có namespace `config:feature-flags` chủ ý không đặt TTL. Nếu job giám sát thấy `-1` rồi tự gán expiration ngắn hoặc xóa key, nó có thể phá dữ liệu.

Chính sách dọn dữ liệu phải dựa trên **định nghĩa từng namespace**. Ví dụ:

~~~text
cache:product:*   -> TTL 15 phút, -1 có thể là lỗi
session:*         -> TTL bắt buộc, -1 cần xử lý an toàn
config:*          -> có thể persistent, -1 là hợp lệ
~~~

## 14. Dùng TTL với session: không tự cho phép truy cập

Một session có deadline 30 phút có thể được lưu dưới key:

~~~redis
SET session:abc "session-data" EX 1800
~~~

Khi kiểm tra:

~~~text
TTL session:abc -> 1200    Còn khoảng 20 phút tại thời điểm đọc
TTL session:abc -> 0       Sắp hết hạn
TTL session:abc -> -2      Key không tồn tại
TTL session:abc -> -1      Key tồn tại nhưng thiếu expiration
~~~

Nếu kiến trúc quy định session bắt buộc có TTL, `-1` có thể là dấu hiệu sai chính sách. Không nên coi “không có TTL” là session hợp lệ vô hạn chỉ vì value vẫn tồn tại.

Mặt khác, **TTL không phải chứng cứ xác thực quyền truy cập**: session có thể bị thu hồi ngay sau khi TTL dương. Phải dùng cơ chế session/authentication đúng ở thời điểm phục vụ yêu cầu.

### 14.1. Coi TTL là deadline tham khảo, không phải khóa bảo đảm

Ví dụ:

~~~text
Thread A: TTL session:abc -> 300
Thread B: DEL session:abc
Thread A: xử lý request
~~~

Nếu Thread A cho phép một hành động quan trọng chỉ vì đã thấy TTL dương thì có lỗi *time-of-check to time-of-use* (TOCTOU). Cần dựa trên cơ chế xác thực/ủy quyền nhất quán, không phải một lần kiểm tra TTL rời rạc.

## 15. TTL với khóa điều phối công việc

Một khóa tạm dùng để điều phối có thể được tạo bằng lệnh có điều kiện:

~~~redis
SET lock:job:42 "owner-token" NX PX 30000
PTTL lock:job:42
~~~

`PTTL` cho biết hạn còn lại của key khóa. Nhưng:

- `PTTL = -2` không chứng minh caller chắc chắn được phép chiếm khóa.
- `PTTL > 0` không chứng minh caller là chủ sở hữu.
- `PTTL = -1` có thể là lỗi nếu khóa bắt buộc có deadline.
- Sau khi đọc TTL, key có thể bị mất và được một worker khác tạo lại.

Vì vậy, **giành quyền sở hữu** phải dựa trên thao tác nguyên tử như SET NX cùng TTL, và **giải phóng** phải kiểm tra token chủ sở hữu bằng cơ chế nguyên tử phù hợp. Không dùng chỉ số TTL thay thế quy tắc khóa.

## 16. Redis Cluster và các trường hợp đọc nhầm key

Trong Redis Cluster, lệnh TTL trên một key được client cluster-aware định tuyến tới node sở hữu slot của key. Nhưng nếu ứng dụng cấu hình sai endpoint hoặc sai serializer, kết quả `-2` dễ gây nhầm rằng key tự hết hạn.

Các trường hợp thường gặp:

- Service mới dùng key prefix khác phiên bản cũ.
- Một service dùng `StringRedisTemplate`, service kia dùng serializer key khác, tạo byte key khác nhau.
- Ứng dụng chuyển sang Redis server/database khác.
- Một môi trường Standalone dùng logical database khác.
- Redis Cluster đang failover hoặc thay đổi topology, cần client cập nhật định tuyến.
- Cache được tạo ở một môi trường nhưng ứng dụng đọc ở môi trường khác.

Ví dụ, hai template đều nhận Java String `cache:product:42`, nhưng serializer key khác nhau có thể gửi **hai dãy byte khác nhau** đến Redis. TTL của một key có thể là `-2` dù Redis CLI nhìn thấy một key trông giống về mặt tên hiển thị.

Khi tất cả key đột nhiên có TTL -2 sau deploy, hãy kiểm tra endpoint, database, serializer và key prefix trước khi kết luận tất cả đã bị expiration.

## 17. Độ chính xác, thời điểm quan sát và thay đổi đồng thời

TTL không phải bộ đếm do ứng dụng điều khiển. Kết quả có thể thay đổi:

~~~text
T1: TTL key = 60
T2: TTL key = 59
T3: client khác EXPIRE key 300
T4: TTL key = 300
~~~

TTL có thể **tăng** khi một client gia hạn. Ngược lại, key có thể biến mất trước deadline vì DEL/eviction.

Một số nguyên tắc:

1. Dùng thời gian còn lại từ Redis như kết quả quan sát tại lúc lệnh được xử lý.
2. Không suy rằng hai lệnh TTL liên tiếp phải giảm đúng 1 giây.
3. Không dùng TTL để suy chắc về trạng thái sau đó.
4. Không dùng TTL làm lịch sử lý do xóa.
5. Nếu điều kiện TTL phải được kiểm tra cùng thao tác ghi, thiết kế một cơ chế nguyên tử thích hợp.
6. Đừng xây scheduler không mất việc chỉ từ việc chờ key hết hạn.

Redis có cơ chế xử lý key hết hạn theo thời gian. Deadline của key và thời điểm bộ nhớ thực tế được thu hồi không nhất thiết trùng tuyệt đối. Nếu yêu cầu nghiệp vụ phải xử lý một công việc đúng hạn và có retry, hãy dùng thiết kế queue/scheduler có lưu trạng thái, không chỉ dựa vào key tự biến mất.

## 18. TTL và keyspace notifications

Redis có thể cấu hình thông báo sự kiện liên quan tới key, bao gồm expiration. Nhưng:

- Sự kiện expiration không phải lời hứa phát ra chính xác ngay tại deadline.
- Subscriber bị ngắt mạng có thể bỏ lỡ thông báo vì cơ chế Pub/Sub không giữ backlog cho subscriber offline.
- Những thông báo này phù hợp hơn với quan sát hoặc xử lý best-effort.

Khi chỉ cần biết **còn bao lâu**, dùng TTL/PTTL. Khi cần đảm bảo một nghiệp vụ được thực thi sau deadline, cần một mô hình có trạng thái bền vững, xác nhận và retry.

## 19. Các lỗi thường gặp khi đọc TTL trong Spring Data Redis

### 19.1. Coi -1 là thời hạn âm một giây

Sai. `-1` là **key tồn tại nhưng không có expiration**.

### 19.2. Coi -2 là “đã hết hạn hai giây”

Sai. `-2` chỉ nói key **không tồn tại**, không nói thời điểm hay nguyên nhân.

### 19.3. Coi 0 là key không tồn tại

Sai. `TTL = 0` có thể xảy ra khi key còn dưới một giây. Khi cần độ phân giải cao hơn, dùng PTTL.

### 19.4. Viết if (ttl <= 0) để phân loại missing

Sai vì gộp `-2`, `-1` và `0`. Hãy kiểm tra từng sentinel.

### 19.5. Tạo Duration âm trước khi phân loại

Sai về semantics nghiệp vụ. Sentinel không phải khoảng thời gian âm thông thường.

### 19.6. Gọi expire() khi định đọc TTL

`expire()` **thay đổi** deadline; `getExpire()` **đọc** deadline. Nhầm API có thể gia hạn TTL ngoài ý muốn.

### 19.7. Cho rằng GET luôn gia hạn TTL

GET thông thường không reset expiration. Sliding expiration phải được thiết kế chủ động.

### 19.8. SET lại value mà quên TTL

SET thông thường có thể xóa TTL, khiến `getExpire()` chuyển từ số dương sang `-1`.

### 19.9. Tin rằng TTL dương đảm bảo GET sau đó thành công

Không. Key có thể bị xóa/expire giữa hai lệnh.

### 19.10. Coi null từ getExpire là -2

Null trong một số bối cảnh pipeline/transaction là tình trạng chưa có giá trị trực tiếp, không phải sentinel key missing.

### 19.11. Cho rằng -2 luôn do expiration

Không. Nó có thể do DEL, eviction, sai key, sai database, sai serializer hoặc key chưa từng tạo.

### 19.12. Dùng TTL như cơ chế khóa phân tán

TTL không xác nhận quyền sở hữu và không chống được race. Dùng các thao tác điều kiện nguyên tử và token chủ sở hữu.

## 20. Một ví dụ giám sát ba nhóm dữ liệu

Ứng dụng có:

~~~text
cache:product:42         -> cache 15 phút
session:token-abc        -> session 30 phút
config:feature-flags     -> cấu hình persistent
~~~

Giả sử đọc:

| Key | Kết quả TTL | Ý nghĩa |
|---|---:|---|
| cache:product:42 | 480 | Còn khoảng 8 phút |
| cache:product:42 | -2 | Cache key không tồn tại |
| cache:product:42 | -1 | Bất thường nếu cache bắt buộc có expiration |
| session:token-abc | 1200 | Còn khoảng 20 phút tại thời điểm đọc |
| session:token-abc | -1 | Cần điều tra nếu session bắt buộc hết hạn |
| session:token-abc | -2 | Không có session key |
| config:feature-flags | -1 | Có thể đúng theo thiết kế |
| config:feature-flags | -2 | Key cấu hình không tồn tại, cần kiểm tra nguồn |

Với cache, có thể nạp lại dữ liệu khi không tìm thấy key. Với session, cần thực hiện chính sách bảo mật/ủy quyền phù hợp. Với cấu hình persistent, không tự xóa key chỉ vì TTL -1.

Các metric có thể quan sát là: tỷ lệ cache miss, số key cache trả -1 bất ngờ, số lỗi ghi thiếu expiration, phân bố TTL ở các key được lấy mẫu và thay đổi sau deploy. Không cần quét toàn bộ Redis keyspace trong từng HTTP request chỉ để tính TTL.

## 21. Tóm tắt quy tắc sử dụng

~~~text
Redis CLI:

TTL key        -> đơn vị giây
PTTL key       -> đơn vị mili giây

-2             -> KEY MISSING
-1             -> KEY EXISTS, NO EXPIRATION
>= 0           -> KEY HAS EXPIRATION,
                  TIME LEFT IN SELECTED UNIT

Spring Data Redis:

getExpire(key)
    -> Long, đơn vị giây

getExpire(key, TimeUnit.MILLISECONDS)
    -> Long, đơn vị mili giây

null ở một số ngữ cảnh thực thi
    -> chưa có kết quả trực tiếp, không phải TTL sentinel
~~~

Thứ tự xử lý hợp lý trong code:

1. Chọn đúng key, đúng namespace và key serializer.
2. Chọn giây hay mili giây theo nghiệp vụ.
3. Phân loại `-2`, `-1` và `>= 0` trước khi tạo `Duration`.
4. Coi kết quả là ảnh chụp trạng thái, không phải bảo đảm cho thao tác sau.
5. Duy trì TTL nhất quán trên mọi đường ghi và cập nhật key.
6. Với cache, session và distributed lock, áp dụng chính sách riêng cho trạng thái persistent/missing thay vì một điều kiện chung.

**Kết luận:** Đọc TTL trong Spring Data Redis không chỉ là lấy một con số. **`-2` là khóa không tồn tại**, **`-1` là khóa tồn tại nhưng không có thời hạn**, còn **`0` hoặc số dương là khóa có expiration và thời gian còn lại theo đơn vị đang đọc**. Phân biệt đúng các trạng thái này giúp tránh nhầm cache miss, giữ dữ liệu vô hạn ngoài ý muốn, diễn giải sai thời gian ngắn và đưa ra quyết định đồng thời không an toàn.
