# Thời hạn của khóa Hash và khả năng hết hạn từng trường theo phiên bản

## 1. Vấn đề: muốn hết hạn cả Hash hay chỉ một field?

Redis Hash lưu nhiều cặp **field → value** bên trong một Redis key. Trong Spring Data Redis, cấu trúc này thường được thao tác qua **HashOperations**:

~~~text
Redis key: session:42
  ├── userId       → "42"
  ├── displayName  → "An"
  ├── otp          → "903715"
  └── lastSeen     → "2026-11-12T15:00:00Z"
~~~

Giả sử hồ sơ phiên làm việc cần tồn tại 30 phút, nhưng mã OTP chỉ hợp lệ trong 60 giây. Ta có **hai yêu cầu hết hạn khác nhau**:

1. **TTL của toàn bộ Hash key:** sau 30 phút, Redis loại bỏ key **session:42**, nghĩa là mọi field cùng biến mất.
2. **TTL của một Hash field:** sau 60 giây, chỉ field **otp** biến mất; **userId**, **displayName** và **lastSeen** vẫn được giữ nếu Hash key chưa hết hạn.

Hai khả năng này không xuất hiện đồng thời từ những phiên bản Redis đầu tiên. Trước **Redis 7.4**, cơ chế expiration gốc của Redis chỉ áp dụng ở cấp **key**, không có TTL độc lập cho từng field bên trong Hash. **Redis 7.4** bổ sung nhóm lệnh cho *hash field expiration*. **Redis 8.0** tiếp tục bổ sung lệnh kết hợp đọc/ghi field và xử lý TTL trong một lần thực thi.

Vì vậy, khi viết code Spring Data Redis, phải phân biệt **phiên bản Redis server**, **phiên bản Spring Data Redis** và **khả năng của driver**. Không thể suy ra hỗ trợ field TTL chỉ vì dự án đã có **HashOperations.put()** và **RedisTemplate.expire()**.

## 2. Key, field, value và TTL thuộc phạm vi nào?

Một Redis Hash có cấu trúc:

~~~text
                       Redis server
                            |
                     key = cart:42
                       type = hash
                       TTL = 1800 s
                            |
                 +----------+----------+
                 |          |          |
               field A    field B    field C
               itemCount  coupon     region
                 "3"       "SAVE5"     "VN"
~~~

**Key** là đối tượng mà Redis quản lý ở lớp lưu trữ chính; **Hash field** là mục dữ liệu nằm bên trong key ấy. Redis command **EXPIRE cart:42 1800** gắn TTL cho **cart:42**. Khi key hết hạn, cả ba field bị xóa cùng nhau.

Kể từ Redis 7.4, có thể đặt thêm TTL riêng cho **coupon** mà không buộc **itemCount** và **region** hết hạn cùng thời điểm. Ví dụ **HEXPIRE cart:42 60 FIELDS 1 coupon** cho field **coupon** tồn tại thêm 60 giây.

| Cấp expiration | Đối tượng bị loại bỏ | Lệnh chính | Redis hỗ trợ |
|---|---|---|---|
| **Key TTL** | Toàn bộ Redis key và mọi field của Hash | EXPIRE, PEXPIRE, EXPIREAT, PEXPIREAT | Có từ các phiên bản Redis rất sớm |
| **Hash field TTL** | Chỉ những field được chỉ định | HEXPIRE, HPEXPIRE, HEXPIREAT, HPEXPIREAT | Redis **7.4+** |
| **Hash field write + TTL** | Ghi field và đặt hạn trong cùng command | HSETEX | Redis **8.0+** |
| **Hash field read + refresh TTL** | Đọc field và tùy chọn đặt lại hạn trong cùng command | HGETEX | Redis **8.0+** |

**Nguyên tắc ưu tiên:** nếu cả **key** và **field** cùng có hạn, đối tượng nào hết hạn trước thì ảnh hưởng trước. Field không thể sống sót sau khi key chứa nó bị xóa.

## 3. TTL toàn bộ Hash bằng lệnh Redis quen thuộc

### 3.1. Tạo Hash rồi đặt TTL cho key

Ví dụ trong redis-cli:

~~~redis
HSET session:42 userId 42 displayName An locale vi
EXPIRE session:42 1800
TTL session:42
~~~

Hành vi mong đợi:

- **HSET** tạo hoặc cập nhật field trong một Hash.
- **EXPIRE session:42 1800** gắn thời hạn 1.800 giây cho Redis key **session:42**.
- **TTL session:42** trả về số giây còn lại (có thể nhỏ hơn 1.800 do thời gian trôi qua).
- Khi key hết hạn, **HGET session:42 userId**, **HGETALL session:42** đều không còn dữ liệu.

Không có field nào mang TTL riêng trong ví dụ này. Cả ba field chia sẻ một hạn của toàn bộ key.

### 3.2. Đọc TTL của Hash key

~~~redis
TTL session:42
PTTL session:42
~~~

**TTL** trả thời gian còn lại tính theo giây; **PTTL** trả theo mili giây:

| Kết quả TTL/PTTL | Ý nghĩa |
|---|---|
| Số không âm | Key có thời hạn, đây là thời gian còn lại |
| **-1** | Key tồn tại nhưng không có expiration ở cấp key |
| **-2** | Key không còn tồn tại |

Nếu Hash vẫn có field nhưng TTL(key) là **-1**, không thể suy ra field chắc chắn cũng không có hạn trên Redis 7.4+. Cần kiểm tra field TTL riêng bằng **HTTL/HPTTL**.

### 3.3. Đặt hạn theo thời điểm hoặc theo khoảng thời gian

~~~redis
EXPIRE session:42 1800
PEXPIRE session:42 1800000
EXPIREAT session:42 1893456000
PEXPIREAT session:42 1893456000000
~~~

Các command này đều nhằm vào **Hash key**, không nhằm vào field. **EXPIRE/PEXPIRE** dùng thời lượng tương đối; **EXPIREAT/PEXPIREAT** dùng mốc Unix timestamp tuyệt đối. Giá trị thời gian trong ví dụ là minh họa, cần chọn mốc tương lai phù hợp khi thực hành.

**PERSIST session:42** xóa TTL của key, giúp key tiếp tục tồn tại cho đến khi bị xóa hoặc được đặt expiration khác; đây **không** phải lệnh xóa TTL của một field. **DEL session:42** xóa ngay cả Hash.

## 4. Cấu hình key TTL với Spring Data Redis

Với **StringRedisTemplate**:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionHashStore {
    private final StringRedisTemplate redis;
    private final HashOperations<String, String, String> hashes;

    public SessionHashStore(StringRedisTemplate redis) {
        this.redis = redis;
        this.hashes = redis.opsForHash();
    }

    public void saveSession(String sessionId, String userId) {
        String key = "session:" + sessionId;
        hashes.put(key, "userId", userId);
        hashes.put(key, "locale", "vi");
        redis.expire(key, Duration.ofMinutes(30));
    }

    public Long remainingKeyTtlSeconds(String sessionId) {
        return redis.getExpire(
            "session:" + sessionId,
            TimeUnit.SECONDS
        );
    }
}
~~~

Ở đây:

- **hashes.put(key, field, value)** tương ứng HSET.
- **redis.expire(key, Duration)** đặt TTL cho **Redis key** có kiểu Hash, giống cách đặt TTL cho String/List/Set key.
- **redis.getExpire(key, TimeUnit.SECONDS)** đọc TTL của **key**, không đọc TTL field.

Đây là API phổ biến trong Spring Data Redis, kể cả trên các phiên bản không có hỗ trợ hash field expiration cấp cao.

**Điểm cần lưu ý về tính nguyên tử:** đoạn **put → put → expire** gồm ba Redis command. Nếu tiến trình ngừng sau HSET nhưng trước EXPIRE, key có thể được tạo mà chưa có thời hạn. Khi yêu cầu “tạo Hash cùng TTL của key trong một đơn vị thực thi”, cân nhắc một Lua script/transaction phù hợp; **EXPIRE được gọi sau nhiều HSET không tự làm cả chuỗi nguyên tử**.

### 4.1. Ghi thêm field có làm mất TTL của key không?

Thao tác **HSET** cập nhật một field trong Hash thông thường **không xóa TTL đã gắn cho Hash key**. Hãy phân biệt với **SET** ghi đè toàn bộ Redis String value: lệnh SET có semantics khác và thường xóa key TTL trước đó nếu không chỉ định giữ hạn.

~~~redis
HSET session:42 userId 42
EXPIRE session:42 120
HSET session:42 locale en
TTL session:42
~~~

TTL(key) vẫn còn, dù đã có thêm field **locale**. Nhưng việc **HSET** một field đang có TTL riêng trong Redis 7.4+ lại có tác động khác đối với **field TTL**; phần sau sẽ giải thích.

### 4.2. Khi cần tạo phiên là thao tác nguyên tử

Nếu chỉ muốn minh họa HSET + EXPIRE trên một Redis instance, có thể đưa hai command vào Lua để tránh khoảng hở:

~~~lua
-- KEYS[1] = session key
-- ARGV[1] = userId, ARGV[2] = TTL giây
local ttl = tonumber(ARGV[2])
if not ttl or ttl <= 0 or ttl ~= math.floor(ttl) then
    return redis.error_reply("invalid ttl")
end
redis.call("HSET", KEYS[1], "userId", ARGV[1])
redis.call("EXPIRE", KEYS[1], ttl)
return 1
~~~

Script này chỉ có ý nghĩa khi chính sách nghiệp vụ cho phép cập nhật field **userId** và reset TTL của toàn bộ session. Nếu có nhiều field, thêm chúng vào script với kiểm tra input trước khi ghi. Redis script thực thi liên tiếp không bị command client khác chen vào, nhưng **không có rollback tự động** sau khi một lệnh đã ghi thành công rồi script gặp lỗi runtime.

## 5. Bước ngoặt Redis 7.4: TTL cho từng Hash field

**Redis 7.4** giới thiệu hash field expiration (HFE). Nhờ đó cùng một Hash có thể có những field với thời hạn khác nhau:

~~~text
Hash key: profile:42             key TTL: không có
  ├── displayName = "An"          field TTL: không có
  ├── locale      = "vi"          field TTL: không có
  ├── loginCode   = "903715"      field TTL: 60 giây
  └── lastDevice  = "android"     field TTL: 1 ngày
~~~

Khi **loginCode** hết hạn, chỉ field ấy bị xóa. Hai field không có expiration vẫn còn, miễn là cả Hash key chưa bị xóa.

### 5.1. Các command mới từ Redis 7.4

| Command | Công dụng | Đơn vị |
|---|---|---|
| **HEXPIRE** | Đặt TTL tương đối cho một/nhiều field | Giây |
| **HPEXPIRE** | Đặt TTL tương đối | Mili giây |
| **HEXPIREAT** | Đặt thời điểm hết hạn tuyệt đối | Unix timestamp giây |
| **HPEXPIREAT** | Đặt thời điểm hết hạn tuyệt đối | Unix timestamp mili giây |
| **HTTL** | Đọc TTL còn lại của field | Giây |
| **HPTTL** | Đọc TTL còn lại của field | Mili giây |
| **HEXPIRETIME** | Đọc timestamp hết hạn của field | Giây |
| **HPEXPIRETIME** | Đọc timestamp hết hạn của field | Mili giây |
| **HPERSIST** | Bỏ hạn của field, giữ nguyên giá trị | Không áp dụng |

**HEXPIRE/HTTL** là lệnh khác hoàn toàn với **EXPIRE/TTL** ở cấp key. Tiền tố **H** của nhóm lệnh mới chỉ thao tác với *field* thuộc Redis Hash.

### 5.2. Ví dụ: một field hết hạn, các field khác còn

~~~redis
DEL profile:42
HSET profile:42 displayName An locale vi loginCode 903715
HEXPIRE profile:42 60 FIELDS 1 loginCode
HTTL profile:42 FIELDS 3 displayName locale loginCode
TTL profile:42
~~~

Khi vừa đặt hạn:

~~~text
HTTL profile:42 FIELDS 3 displayName locale loginCode
1) (integer) -1    # displayName còn, không có field TTL
2) (integer) -1    # locale còn, không có field TTL
3) (integer) 60    # loginCode còn khoảng 60 giây

TTL profile:42
(integer) -1        # bản thân Hash key không có TTL
~~~

Giá trị thời gian thực tế có thể giảm ngay khi câu lệnh được xử lý. Sau hơn 60 giây, **HGET profile:42 loginCode** không còn trả về code, nhưng **HGET profile:42 locale** vẫn có thể trả **vi**.

Vì Redis có cơ chế loại bỏ dữ liệu đã hết hạn, không nên thiết kế nghiệp vụ dựa trên giả định một sự kiện callback từ Redis sẽ luôn được gửi đúng từng mili giây. Khi truy cập field đã hết hạn, client cần xử lý như field không tồn tại.

### 5.3. Đặt TTL cho nhiều field

~~~redis
HSET profile:42 loginCode 903715 resetCode 281946
HEXPIRE profile:42 90 FIELDS 2 loginCode resetCode
HTTL profile:42 FIELDS 2 loginCode resetCode
~~~

**FIELDS 2** nghĩa là có đúng hai tên field đi sau. Nếu số này không khớp số đối số, Redis báo lỗi cú pháp; nó không có nghĩa chọn field có index 2.

**HEXPIRE** trả **một mã kết quả cho mỗi field**, vì mỗi field có thể đang tồn tại, không tồn tại hoặc không thỏa điều kiện đặt hạn.

## 6. Hiểu mã kết quả của HEXPIRE và HTTL

### 6.1. HEXPIRE trả kết quả theo field

Ví dụ:

~~~redis
HEXPIRE profile:42 60 FIELDS 2 loginCode missingCode
~~~

Nếu **loginCode** tồn tại và **missingCode** không có:

~~~text
1) (integer) 1
2) (integer) -2
~~~

Ý nghĩa các mã chính:

| Mã | Ý nghĩa |
|---|---|
| **1** | Đã đặt hoặc cập nhật expiration thành công |
| **0** | Không đáp ứng điều kiện **NX/XX/GT/LT** |
| **-2** | Field hoặc Hash key không tồn tại |
| **2** | Field bị xóa ngay vì thời hạn đặt bằng 0 hoặc thời điểm tuyệt đối đã qua |

Không suy luận rằng kết quả dạng mảng luôn chỉ chứa **1**. Khi đặt hạn cho nhiều field, ứng dụng cần xem kết quả tương ứng từng field.

### 6.2. HTTL/HPTTL trả bao nhiêu?

~~~redis
HTTL profile:42 FIELDS 3 displayName loginCode unknown
~~~

Với Hash còn tồn tại và field tương ứng:

- **Số không âm**: thời gian còn lại của field, theo giây đối với HTTL.
- **-1**: field đang tồn tại nhưng không có field TTL.
- **-2**: field không tồn tại hoặc đã hết hạn.

Nếu Hash key không còn, response cụ thể có thể được biểu diễn khác nhau theo command/client; đừng lấy một phần tử số của kết quả mà không xác định tình trạng key. **TTL(key)** và **HTTL(key, field)** là hai phép đo độc lập.

### 6.3. Đọc thời điểm hết hạn tuyệt đối

~~~redis
HEXPIRETIME profile:42 FIELDS 1 loginCode
HPEXPIRETIME profile:42 FIELDS 1 loginCode
~~~

Các lệnh **EXPIRETIME** trả mốc thời gian tuyệt đối; chúng khác với **HTTL** là khoảng thời gian còn lại. Trong Java, nếu chuyển Unix timestamp thành **Instant**, phải dùng đúng đơn vị giây hoặc mili giây. Nhầm hai đơn vị có thể làm hạn lệch hàng chục năm.

## 7. NX, XX, GT và LT khi đặt hạn của field

Từ Redis 7.4, các lệnh đặt TTL cho field hỗ trợ lựa chọn điều kiện:

~~~text
HEXPIRE key seconds [NX | XX | GT | LT] FIELDS count field ...
~~~

| Tùy chọn | Ý nghĩa |
|---|---|
| **NX** | Chỉ đặt expiration nếu field hiện chưa có expiration |
| **XX** | Chỉ đặt expiration nếu field hiện đã có expiration |
| **GT** | Chỉ cập nhật khi hạn mới *muộn hơn* hạn hiện tại |
| **LT** | Chỉ cập nhật khi hạn mới *sớm hơn* hạn hiện tại |

Đây là các tùy chọn **loại trừ lẫn nhau** trong một lệnh. Chúng kiểm soát việc cập nhật **hạn của field**, không phải điều kiện field có value giống một chuỗi Java nào đó.

Ví dụ chỉ đặt hạn nếu field chưa có hạn:

~~~redis
HSET profile:42 tempCode 999111
HEXPIRE profile:42 120 NX FIELDS 1 tempCode
HEXPIRE profile:42 300 NX FIELDS 1 tempCode
~~~

Lần đầu có thể trả **1**; lần sau trả **0** vì field đã có expiration.

Ví dụ kéo dài hạn chỉ khi hạn mới xa hơn:

~~~redis
HEXPIRE profile:42 300 GT FIELDS 1 tempCode
~~~

**GT** hữu ích khi hệ thống chỉ cho gia hạn, còn **LT** phù hợp nếu hệ thống muốn giới hạn hạn không được vượt quá một mốc. Redis xem field không có expiration như thời hạn vô hạn khi đánh giá các điều kiện GT/LT, nên cần hiểu khác biệt giữa field chưa có TTL và field đang có TTL.

## 8. Tương tác giữa TTL của key và TTL của field

### 8.1. Hash key hết hạn trước field

~~~redis
DEL session:43
HSET session:43 userId 43 loginCode 123456
EXPIRE session:43 30
HEXPIRE session:43 300 FIELDS 1 loginCode
~~~

Mặc dù **loginCode** được đặt thời hạn 300 giây, toàn bộ **session:43** chỉ còn khoảng 30 giây. Khi key hết hạn:

~~~text
session:43 (key) ── hết hạn ──► toàn bộ Hash biến mất
                                 ├── userId     xóa
                                 └── loginCode  xóa
~~~

Field TTL không thể khiến field tồn tại sau khi key đã bị xóa.

### 8.2. Field hết hạn trước key

~~~redis
DEL session:44
HSET session:44 userId 44 loginCode 123456
EXPIRE session:44 1800
HEXPIRE session:44 60 FIELDS 1 loginCode
~~~

Sau khoảng 60 giây, **loginCode** hết hạn trong khi **userId** còn. Sau khoảng 1.800 giây, Redis xóa toàn bộ key. Có thể hình dung:

~~~text
t = 0
  session:44
    userId    [==============================] 30 phút
    loginCode [==]                              60 giây

t ≈ 60s: loginCode không còn
t ≈ 30m: session:44 không còn
~~~

### 8.3. Chỉ còn một field và field ấy hết hạn

Nếu Hash chỉ chứa field **loginCode**, Redis xóa field cuối cùng thì Hash không còn phần tử; Redis thường xóa luôn key Hash rỗng. Khi ấy **TTL(key)** sẽ cho biết key không tồn tại. Không thể dựa vào một Hash rỗng để giữ state cho những field sẽ thêm sau này.

### 8.4. HPERSIST không làm key sống lâu hơn

~~~redis
HPERSIST session:44 FIELDS 1 loginCode
~~~

Lệnh này bỏ TTL **riêng của loginCode** nếu field còn tồn tại, nhưng **TTL của session:44 vẫn giữ nguyên**. Nếu key còn 15 phút, cả Hash vẫn hết hạn sau khoảng 15 phút.

Ngược lại, **PERSIST session:44** bỏ key TTL nhưng không tự động xóa field TTL. Phạm vi của hai command hoàn toàn khác nhau.

## 9. Ghi lại field ảnh hưởng thế nào đến TTL?

Đây là điểm dễ gây lỗi nhất khi sử dụng HFE.

### 9.1. HSET ghi đè field có thể xóa field TTL

Giả sử:

~~~redis
HSET otp:42 code 123456
HEXPIRE otp:42 60 FIELDS 1 code
HTTL otp:42 FIELDS 1 code
~~~

Field **code** có hạn khoảng 60 giây. Nếu ứng dụng cập nhật bằng:

~~~redis
HSET otp:42 code 999999
HTTL otp:42 FIELDS 1 code
~~~

Việc **HSET ghi đè nội dung field** sẽ loại bỏ field expiration đã gắn, và HTTL có thể trả **-1**. Code mới trở thành field không tự hết hạn nếu không được đặt lại TTL.

Đây là hành vi khác với **key TTL**: HSET không tự xóa TTL của Hash key, nhưng ghi đè field có thể xóa TTL **của field ấy**. Nếu chỉ gọi **HSET** rồi giả định OTP mới tiếp tục hết hạn sau 60 giây, ứng dụng có thể lưu mã xác nhận lâu hơn dự kiến.

### 9.2. HINCRBY không có cùng semantics với HSET

Những lệnh thay đổi nội dung field theo cách không thay thế toàn bộ value, chẳng hạn **HINCRBY**, có thể giữ TTL field đang có. Cần dựa trên semantics của từng Redis command; không nên quy mọi cập nhật field thành cùng một loại thao tác.

Ví dụ đếm số lần trong một cửa sổ:

~~~redis
HSET rate:client42 attempts 0
HEXPIRE rate:client42 60 FIELDS 1 attempts
HINCRBY rate:client42 attempts 1
HTTL rate:client42 FIELDS 1 attempts
~~~

Lệnh tăng không được hiểu là thao tác “tạo lại field và xóa hạn” như HSET. Khi dùng một command khác, cần kiểm tra quy định về giữ/xóa field expiration của chính command ấy.

### 9.3. Hai lệnh HSET rồi HEXPIRE không nguyên tử

~~~redis
HSET otp:42 code 999999
HEXPIRE otp:42 60 FIELDS 1 code
~~~

Lời gọi thứ nhất và thứ hai là hai command. Nếu ứng dụng dừng hoặc kết nối lỗi sau HSET nhưng trước HEXPIRE, code có thể tồn tại không có field TTL. Khi nhiều request ghi vào cùng field, một request khác cũng có thể xen vào giữa hai lệnh.

Từ **Redis 8.0**, **HSETEX** giải quyết trực tiếp nhu cầu ghi value và đặt expiration của field trong cùng command. Với Redis 7.4, Lua script phù hợp có thể gói hai bước trong một lần thực thi. Với Redis trước 7.4, không có native field expiration để Lua tự gọi.

## 10. Các lệnh tiện dụng bổ sung trong Redis 8.0

**Redis 8.0** có thêm các command cho phép phối hợp truy cập field với expiration mà không cần nhiều round trip:

### 10.1. HSETEX: ghi field cùng TTL

~~~redis
HSETEX otp:42 EX 60 FIELDS 1 code 903715
~~~

Ý nghĩa:

- Ghi **code = 903715** trong Hash **otp:42**.
- Đặt TTL 60 giây cho chính field **code**.
- Hai hành động diễn ra trong **một command**.

**HSETEX** còn hỗ trợ **PX**, **EXAT**, **PXAT**, **KEEPTTL** và các điều kiện **FNX/FXX** cho nhóm field. **KEEPTTL** nhằm giữ hạn field cũ khi cập nhật, trong khi **EX** đặt hạn mới; các lựa chọn expiration này không dùng đồng thời với nhau.

Ví dụ muốn cập nhật value nhưng giữ field TTL hiện có:

~~~redis
HSETEX otp:42 KEEPTTL FIELDS 1 code 812333
~~~

Đừng nhầm **HSETEX** với **SETEX**: **SETEX** chỉ làm việc với Redis String key; **HSETEX** làm việc với field trong Redis Hash và cần Redis 8.0+.

### 10.2. HGETEX: đọc và cập nhật hạn

~~~redis
HGETEX session:42 EX 900 FIELDS 1 lastDevice
~~~

Lệnh đọc value của **lastDevice**, đồng thời đặt lại thời hạn của chính field đó thành 900 giây. Đây có thể là cơ chế *sliding expiration* cho field được truy cập, nếu yêu cầu nghiệp vụ thật sự là “mỗi lần đọc thành công sẽ gia hạn”.

Không nên tự động gia hạn field trong mọi GET; một phép đọc dùng cho kiểm tra/monitoring có thể vô tình làm dữ liệu tồn tại lâu hơn.

### 10.3. HGETDEL: đọc rồi xóa

~~~redis
HGETDEL otp:42 FIELDS 1 code
~~~

Lấy giá trị code và xóa field ấy trong một command nguyên tử. Lệnh có thể giúp xây dựng cơ chế “lấy một lần”, nhưng việc kiểm tra **code nhập vào có đúng không** phải được thiết kế rõ. Nếu ứng dụng đọc/xóa trước khi so sánh, một mã sai có thể khiến mã thật bị xóa ngoài ý muốn; Lua script cho thao tác so sánh và xóa có điều kiện là một cách phù hợp.

## 11. Hỗ trợ trong Spring Data Redis theo phiên bản

Redis server có lệnh không đồng nghĩa phương thức Java đã tồn tại trong phiên bản Spring Data Redis hiện dùng. Phần dưới phân biệt chính xác hai lớp hỗ trợ:

| Khả năng | Redis server | Spring Data Redis |
|---|---|---|
| TTL của **toàn bộ Hash key** | Hỗ trợ từ lâu | **RedisTemplate.expire/getExpire/persist** |
| TTL của **một field Hash** | **Redis 7.4+** | API cấp cao trên **HashOperations** được bổ sung từ **Spring Data Redis 3.5** |
| Đọc TTL của field | **HTTL/HPTTL** từ Redis 7.4+ | **HashOperations.getTimeToLive(...)** từ 3.5 |
| Xóa TTL của field | **HPERSIST** từ Redis 7.4+ | **HashOperations.persist(key, fields)** từ 3.5 |
| Ghi field + expiration cùng command | **HSETEX** từ Redis 8.0+ | Cần kiểm tra phiên bản Spring Data Redis/driver thực tế có API tương ứng |

Nếu project đang dùng một nhánh Spring Data Redis **trước 3.5**, method **HashOperations.expire(key, Duration, fields)** trong ví dụ dưới **không có sẵn**, dù Redis server đã nâng cấp lên 7.4. Không sao chép ví dụ mới vào project cũ rồi cho rằng đây là lỗi Redis connection.

Với Spring Boot, phiên bản Spring Data Redis thường được quyết định bởi bộ quản lý dependency của Spring Boot. Khi muốn dùng API mới, cần chọn một tổ hợp Spring Boot, Spring Data Redis và driver được hỗ trợ, thay vì nâng một jar lẻ không kiểm soát tương thích.

### 11.1. API key TTL hoạt động trên nhiều phiên bản Spring Data Redis

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public class HashKeyExpiry {
    private final StringRedisTemplate redis;

    public HashKeyExpiry(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean setWholeHashTtl(String key, Duration ttl) {
        // Hạn cho toàn bộ Redis Hash key.
        return Boolean.TRUE.equals(redis.expire(key, ttl));
    }
}
~~~

**redis.expire(key, ttl)** không hề nhận tên field; nó luôn điều khiển expiration của key Redis chứa Hash.

### 11.2. API field TTL từ Spring Data Redis 3.5+

Ví dụ dùng **StringRedisTemplate** và **HashOperations**:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class HashFieldExpiryService {
    private final HashOperations<String, String, String> hashes;

    public HashFieldExpiryService(StringRedisTemplate redis) {
        this.hashes = redis.opsForHash();
    }

    public void saveShortLivedCode(String userId, String code) {
        String key = "user:temporary:" + userId;
        hashes.put(key, "code", code);

        // Có từ Spring Data Redis 3.5 và cần Redis 7.4+.
        var changes = hashes.expire(
            key,
            Duration.ofSeconds(60),
            List.of("code")
        );
        // 'changes' chứa kết quả theo field, không phải Boolean.
        // Khi dùng pipeline/transaction, kết quả có thể tạm là null.
    }

    public void inspectCodeTtl(String userId) {
        String key = "user:temporary:" + userId;

        var ttls = hashes.getTimeToLive(
            key,
            TimeUnit.SECONDS,
            List.of("code")
        );
        // 'ttls' là tập kết quả expiration cho từng field.
    }

    public void makeCodePersistent(String userId) {
        hashes.persist(
            "user:temporary:" + userId,
            List.of("code")
        );
    }
}
~~~

Các method đáng nhớ trong API **HashOperations** của Spring Data Redis 3.5:

~~~java
hashes.expire(key, Duration.ofSeconds(60), List.of("code"));
hashes.expireAt(key, java.time.Instant.now().plusSeconds(60),
                List.of("code"));
hashes.getTimeToLive(key, List.of("code"));
hashes.getTimeToLive(key, TimeUnit.MILLISECONDS,
                     List.of("code"));
hashes.persist(key, List.of("code"));
~~~

Một biến thể **expire(key, Expiration, ExpirationOptions, fields)** cho phép truyền lựa chọn expiration chi tiết hơn. Những phương thức này trả về các đối tượng kết quả như **ExpireChanges** và **Expirations** cho từng field. Không nên đối xử kết quả như **Boolean** của lệnh **redis.expire(key, ttl)**.

**Cảnh báo về ví dụ saveShortLivedCode:** **hashes.put()** và **hashes.expire()** vẫn là **hai command riêng**. Đoạn code thể hiện API field TTL, không chứng minh ghi field kèm TTL là nguyên tử. Nếu không chấp nhận khoảng hở, cần một command như HSETEX (Redis 8.0+) hoặc script trên Redis 7.4+.

### 11.3. Nếu Spring Data Redis/driver chưa có API tương ứng?

Có ba hướng thực tế:

1. **Dùng key TTL** nếu toàn bộ Hash nên hết hạn cùng lúc.
2. **Nâng cấp stack một cách có kiểm soát** nếu server 7.4+ và yêu cầu field TTL là trọng tâm.
3. **Sử dụng giao diện command cấp thấp hoặc Lua script** được driver/server hỗ trợ, bảo đảm serialization/key slot đúng và quản lý kết quả/lỗi, khi high-level API chưa có.

Không tự gọi API **HashOperations.expire(...)** trên Spring Data Redis trước 3.5, và cũng không gửi **HEXPIRE** tới Redis trước 7.4.

## 12. Lua script khi muốn ghi field cùng TTL trên Redis 7.4

Redis 7.4 có **HSET** và **HEXPIRE** nhưng chưa có **HSETEX**. Có thể dùng Lua script để gộp hai thao tác mà không cho command khác chen vào:

~~~lua
-- KEYS[1]: Hash key, ví dụ otp:42
-- ARGV[1]: field, ví dụ code
-- ARGV[2]: value, ví dụ 903715
-- ARGV[3]: TTL tính theo giây
local seconds = tonumber(ARGV[3])

if not seconds or seconds <= 0 or seconds ~= math.floor(seconds) then
    return redis.error_reply("ttl must be a positive integer")
end

redis.call("HSET", KEYS[1], ARGV[1], ARGV[2])
local result = redis.call(
    "HEXPIRE", KEYS[1], seconds, "FIELDS", 1, ARGV[1]
)
return result[1]
~~~

Trong Spring Data Redis, có thể gọi bằng **RedisScript**:

~~~java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

DefaultRedisScript<Long> script = new DefaultRedisScript<>();
script.setResultType(Long.class);
script.setScriptText("""
    local seconds = tonumber(ARGV[3])
    if not seconds or seconds <= 0 or seconds ~= math.floor(seconds) then
        return redis.error_reply('invalid ttl')
    end
    redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
    local results = redis.call('HEXPIRE', KEYS[1], seconds,
                               'FIELDS', 1, ARGV[1])
    return results[1]
    """);

// Redis server phải hỗ trợ HEXPIRE (7.4 trở lên).
Long applied = stringRedisTemplate.execute(
    script,
    List.of("otp:42"),
    "code", "903715", "60"
);
~~~

Đây là minh họa cách thực thi thao tác phía server. **stringRedisTemplate** là bean đã được inject, không phải biến được tạo trong code block này. Trong ứng dụng thật nên khai báo script dùng lại, không tạo mới mỗi request.

Script chạy trong một ranh giới thực thi của Redis, giúp loại bỏ khoảng hở giữa HSET và HEXPIRE. Tuy vậy Redis script không có rollback tự động nếu script ghi thành công rồi phát sinh lỗi runtime sau đó; luôn kiểm tra input và tình trạng dữ liệu có thể kiểm tra trước khi ghi.

Đối với Redis Cluster, các key mà script truy cập phải được khai báo phù hợp trong **KEYS** và tuân thủ yêu cầu hash slot. Một script không tự biến nhiều master thành giao dịch nguyên tử liên cụm.

## 13. Cách thiết kế tương thích Redis trước 7.4

Nếu server Redis đang chạy **6.x**, **7.0**, **7.2** hoặc các bản trước 7.4, không có native field TTL. Khi đó, tùy yêu cầu có thể:

### 13.1. Đặt TTL chung cho toàn bộ Hash

Phù hợp khi mọi field cùng vòng đời, ví dụ dữ liệu một session ngắn:

~~~redis
HSET session:42 userId 42 locale vi
EXPIRE session:42 1800
~~~

Ưu điểm: mô hình gọn, ít key, API Spring Data Redis phổ biến. Nhược điểm: một field ngắn hạn không thể tự biến mất trước các field còn lại nhờ Redis expiration gốc.

### 13.2. Tách field cần hạn riêng thành Redis key khác

~~~text
Hash key: profile:42
  displayName  -> "An"
  locale       -> "vi"

String key: profile:42:loginCode
  value        -> "903715"
  key TTL      -> 60 giây
~~~

Ví dụ:

~~~redis
HSET profile:42 displayName An locale vi
SET profile:42:loginCode 903715 EX 60
~~~

Đây là một cách phổ biến để có hạn độc lập bằng key TTL truyền thống. Ưu điểm là dễ áp dụng và Redis tự xóa từng key. Nhược điểm là số lượng key tăng; cần quy tắc đặt tên và dọn dữ liệu để các key liên quan không trở thành dữ liệu mồ côi khi profile bị xóa.

### 13.3. Lưu mốc hết hạn ngay trong value và kiểm tra ở application

Ví dụ:

~~~text
Hash key: profile:42
  loginCode     -> "903715"
  codeExpiresAt -> "2026-11-12T16:00:00Z"
~~~

Service đọc cả code và mốc hết hạn, rồi coi code đã hết hiệu lực khi thời gian hiện tại vượt qua mốc. Cách này là **hết hạn theo ngữ nghĩa ứng dụng**, không tự xóa field tại Redis. Cần thêm lazy cleanup, scheduled cleanup hoặc cơ chế dọn riêng nếu muốn giải phóng bộ nhớ.

Lưu thời gian ở client còn có thể bị ảnh hưởng bởi lệch đồng hồ giữa nhiều instance. Nếu yêu cầu bảo mật hay tính chính xác cao, nên thiết kế kiểm tra và tiêu thụ code nguyên tử phía server, cùng quy tắc thời gian rõ ràng.

### Bảng so sánh phương án

| Phương án | Redis tối thiểu | Field được Redis tự xóa? | Đánh đổi |
|---|---|---|---|
| TTL toàn Hash key | Redis cũ | Không, xóa cả Hash | Đơn giản nếu cùng vòng đời |
| Mỗi dữ liệu ngắn hạn là key riêng | Redis cũ | Xóa cả key riêng tương ứng | Nhiều key hơn, cần đồng bộ vòng đời |
| Timestamp lưu trong Hash | Redis cũ | Không | Cần kiểm tra và dọn bằng ứng dụng |
| HEXPIRE cho Hash field | Redis 7.4 | Có | Cần server/client hỗ trợ, chú ý HSET ghi đè |
| HSETEX cho field | Redis 8.0 | Có | Ghi + TTL đồng thời, cần client hỗ trợ command |

## 14. Redis Repository, @RedisHash và TTL có giống HashOperations không?

Spring Data Redis có **Redis Repository** ánh xạ object thành Redis Hash thông qua **@RedisHash**:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "login_session", timeToLive = 1800)
public class LoginSession {
    @Id
    private String id;

    private String userId;

    public LoginSession() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
}
~~~

**timeToLive = 1800** trong **@RedisHash** là TTL mặc định (tính bằng giây) cho **toàn bộ key thực thể**, không phải thời hạn cho từng thuộc tính Java. Annotation **@TimeToLive** có thể được dùng để biểu diễn TTL của entity theo property, nhưng vẫn không đồng nghĩa mỗi property được Redis tự hết hạn.

Không suy ra rằng đặt **@RedisHash** lên một POJO sẽ khiến các field như **otp** có TTL độc lập trên Redis 7.4. Khả năng key-value repository ánh xạ TTL của **entity** là một cơ chế riêng; field-level expiration phải được thiết kế và sử dụng qua API/command phù hợp với mapping và phiên bản.

Khi repository còn duy trì secondary indexes hoặc metadata key, expiration và event cleanup có thể liên quan đến những key phụ. Nếu can thiệp trực tiếp vào field bằng Redis command ngoài repository, phải hiểu ảnh hưởng tới mapping/index và vòng đời thực thể; không nên giả định repository tự cập nhật mọi cấu trúc phụ sau những thay đổi bên ngoài nó.

## 15. Chọn chiến lược hết hạn cho từng nghiệp vụ

### 15.1. Session toàn bộ có cùng TTL

Nếu mọi thông tin phiên đều phải biến mất sau 30 phút, một Hash key có TTL cấp key là lựa chọn gọn:

~~~text
session:{sessionId}
  userId, roles, deviceId, createdAt
  TTL(key) = 30 phút
~~~

Nếu ứng dụng muốn *sliding session*, cần xác định có refresh TTL(key) sau mỗi request hay chỉ sau hành vi sử dụng cụ thể. Gọi **EXPIRE** trên key là thay đổi trạng thái; nếu mọi request đều refresh, phiên có thể kéo dài ngoài ý muốn khi có background traffic.

### 15.2. Một field ngắn hạn nằm cùng dữ liệu dài hạn

~~~text
profile:{userId}
  displayName     không có field TTL
  locale          không có field TTL
  loginCode       field TTL = 60 giây
~~~

Trên Redis 7.4+, dùng HFE khi mô hình dữ liệu và client phù hợp. Nếu server cũ, tách **loginCode** thành key riêng có TTL 60 giây sẽ rõ ràng và dễ vận hành.

### 15.3. Đếm sự kiện theo cửa sổ thời gian

Một Hash có thể chứa những field đại diện từng bucket thời gian:

~~~text
metrics:request:api
  2026-11-12T14:00   14  (hết hạn sau 24 giờ)
  2026-11-12T15:00   27  (hết hạn sau 24 giờ)
  2026-11-12T16:00   18  (hết hạn sau 24 giờ)
~~~

Field TTL giúp Redis tự loại các bucket cũ. Nhưng thiết kế giới hạn tần suất chính xác còn phải xét cách tạo bucket, cập nhật counter, thời điểm đặt TTL và tính nguyên tử; chỉ “HINCRBY rồi HEXPIRE” ở hai command riêng chưa loại được mọi race condition.

### 15.4. OTP/mã xác minh

Field TTL có thể phù hợp để tự xóa code, nhưng các quy tắc sau vẫn quan trọng:

- Không ghi code mới bằng HSET rồi quên đặt lại field TTL.
- Không coi một lệnh **HGET** là đã “tiêu thụ” code một lần.
- Xác định giới hạn thử sai, chống dùng lại, quyền truy cập và thời hạn của yêu cầu.
- Nếu cần so sánh code rồi xóa chỉ khi khớp, hãy thiết kế thao tác server-side nguyên tử, không dựa vào nhiều request đọc/ghi xen kẽ.
- Khi Redis timeout, response không nói chắc thao tác trước đã xảy ra hay chưa; retry phải cân nhắc idempotency.

## 16. Quan sát và chẩn đoán TTL thực tế

### 16.1. Khác nhau giữa không có field và đã hết hạn

Sau khi field TTL hết hạn, **HGET key field** trả kết quả không tồn tại, tương tự khi field chưa từng được tạo. Redis thông thường không lưu lịch sử “field này vừa hết hạn” để HGET phân biệt được.

Muốn biết từng field đang ở trạng thái nào trước khi hết hạn, Redis 7.4+ có thể dùng:

~~~redis
HGET profile:42 loginCode
HEXISTS profile:42 loginCode
HTTL profile:42 FIELDS 1 loginCode
TTL profile:42
TYPE profile:42
~~~

**HEXISTS** kiểm tra tồn tại ở thời điểm lệnh chạy. Không được sử dụng **HEXISTS → HGET** như một snapshot nguyên tử; field có thể hết hạn hoặc bị client khác thay đổi giữa hai lệnh.

### 16.2. Thời gian còn lại không phải một con số cố định

Ví dụ:

~~~redis
HEXPIRE profile:42 60 FIELDS 1 loginCode
HTTL profile:42 FIELDS 1 loginCode
~~~

Kết quả có thể là **60**, **59** hoặc thấp hơn tùy thời gian trôi qua. Test không nên kiểm tra bằng phép bằng đúng “60 giây” nếu không kiểm soát thời gian thực thi; điều cần kiểm tra là hạn đã được đặt và field biến mất sau khoảng thời gian thích hợp.

### 16.3. Thiếu command do phiên bản cũ

Nếu gọi **HEXPIRE** mà Redis trả lỗi **unknown command**, trước hết xác nhận server:

~~~bash
redis-cli INFO server
~~~

Tìm trường **redis_version** và kiểm tra có thực sự là Redis 7.4+ hay không. Cũng cần xác định endpoint đang kết nối đúng môi trường; có thể local container là Redis 8.x nhưng staging vẫn chạy 7.2.

Nếu Redis server đủ mới mà ứng dụng Java không biên dịch được khi gọi **HashOperations.expire(...)**, nhiều khả năng **Spring Data Redis quá cũ**. Đây là lỗi khác với unknown command trả về từ server. Nếu code biên dịch nhưng command thất bại khi runtime, kiểm tra driver, quyền Redis ACL, topology và message lỗi gốc.

### 16.4. Bộ nhớ và expiration events

Expiration được Redis quản lý phía server nhưng không nên coi đó là bộ hẹn giờ gửi event đúng thời điểm hoặc có delivery guarantee giống durable message queue. **Keyspace notifications**, nếu được bật và hỗ trợ cho trường hợp tương ứng, là cơ chế quan sát/notification có tính chất khác với bản ghi sự kiện bền vững.

Nếu một hành động nghiệp vụ buộc phải diễn ra khi field hết hạn (ví dụ giải phóng tài nguyên ở database), nên có workflow đáng tin cậy riêng; đừng phụ thuộc duy nhất vào notification expiration vốn có thể bị bỏ lỡ khi consumer ngắt kết nối.

## 17. Các lỗi thường gặp và cách tránh

| Hiểu nhầm | Hậu quả | Cách làm đúng |
|---|---|---|
| **expire(hashKey, 60s)** chỉ xóa một field | Cả Hash biến mất | Xác định cấp key hay field; dùng HFE nếu cần |
| **@RedisHash(timeToLive=...)** đặt TTL cho từng thuộc tính | Toàn entity bị xóa cùng lúc | Hiểu annotation áp dụng cho key entity |
| Redis 7.2 cũng có **HEXPIRE** | Unknown command | Chỉ dùng HFE trên Redis 7.4+ |
| Spring Data Redis 3.3 có sẵn **HashOperations.expire(fields)** | Compile error | API field TTL được thêm từ 3.5 |
| **HSET** giữ nguyên field TTL như HINCRBY | Field mới có thể sống vô hạn | Đặt lại hạn hoặc dùng HSETEX/KEEPTTL khi hỗ trợ |
| **HPERSIST** làm Hash key không hết hạn | Hash vẫn bị xóa khi key TTL đến hạn | Phân biệt HPERSIST với PERSIST |
| Field TTL dài hơn key TTL thì field sống lâu hơn | Dữ liệu mất khi key hết hạn | Xem key TTL như giới hạn trên của vòng đời field |
| **HEXPIRE** cho một nhóm field trả một Boolean | Diễn giải nhầm kết quả nhiều field | Đọc mã kết quả của từng field |
| **HSET + HEXPIRE** là một thao tác nguyên tử | Có khoảng hở trước khi đặt hạn | HSETEX hoặc script tùy phiên bản |
| “Field hết hạn” đồng nghĩa event luôn tới consumer | Bỏ lỡ hành động nghiệp vụ | Dùng cơ chế xử lý đáng tin cậy riêng |

## 18. Bài tập suy luận

### Bài 1: TTL key hay TTL field?

Một Hash **session:55** chứa **userId** và **otp**. Code chạy **EXPIRE session:55 60**. Sau 60 giây, field nào còn?

**Giải thích:** Cả Hash key hết hạn; **userId** và **otp** đều bị xóa. **EXPIRE** không nhận field name và luôn áp dụng cho key.

### Bài 2: Hai hạn khác nhau

Redis 7.4 có Hash key TTL 300 giây và field **otp** TTL 600 giây. Hỏi **otp** có thể còn sau phút thứ 5 không?

**Giải thích:** Không. Khi Hash key hết hạn, mọi field bị xóa bất kể từng field đang có hạn dài hơn.

### Bài 3: OTP mới không hết hạn

Ứng dụng đặt **HEXPIRE otp:55 60 FIELDS 1 code**, sau đó ghi lại code bằng **HSET otp:55 code 888888**. Vì sao code mới có thể tồn tại lâu hơn 60 giây?

**Giải thích:** HSET ghi đè field xóa field TTL cũ. Cần đặt lại expiration; muốn tránh khoảng hở giữa ghi và đặt TTL, dùng **HSETEX** trên Redis 8.0+ hoặc script phù hợp trên Redis 7.4+.

### Bài 4: Mã kết quả

Lệnh **HEXPIRE profile:55 60 FIELDS 2 code missing** trả **[1, -2]**. Ý nghĩa là gì?

**Giải thích:** Field **code** được đặt/cập nhật hạn thành công; field **missing** không tồn tại. Mỗi vị trí trong response tương ứng một field trong danh sách gửi đi.

### Bài 5: Redis 7.2 và Spring Data Redis 3.5

Project đã nâng Spring Data Redis lên 3.5 nhưng server Redis vẫn ở 7.2. Có thể gọi **hashOps.expire(key, Duration, fields)** để xóa field tự động sau TTL không?

**Giải thích:** API Java có thể hiện diện nhưng server không hỗ trợ **HEXPIRE**. Cần nâng Redis lên 7.4+ hoặc chọn mô hình key TTL/timestamp phù hợp.

### Bài 6: Redis 8.0 nhưng Java API cũ

Server Redis 8.0 hỗ trợ **HSETEX**, nhưng application sử dụng phiên bản Spring Data Redis không có method ánh xạ. Có thể kết luận Redis server không hỗ trợ field TTL?

**Giải thích:** Không. Redis hỗ trợ từ 7.4/8.0 tương ứng, còn thư viện Java cần phiên bản và driver thích hợp hoặc cơ chế command cấp thấp. Phải kiểm tra hai lớp khả năng riêng.

### Bài 7: HPERSIST và PERSIST

Hash **profile:55** có key TTL 300 giây và field **avatarTemp** TTL 60 giây. Sau lệnh **HPERSIST profile:55 FIELDS 1 avatarTemp**, chuyện gì xảy ra?

**Giải thích:** Field **avatarTemp** không còn hạn riêng nhưng vẫn nằm trong Hash chịu TTL(key) khoảng 300 giây. Dùng **PERSIST profile:55** mới xóa TTL ở cấp key; lệnh đó cũng không mặc nhiên bỏ field expiration.

## 19. Checklist triển khai theo phiên bản

Trước khi chọn TTL cho Redis Hash, trả lời:

1. **Muốn hết hạn toàn bộ Hash hay từng field?** Nếu cùng vòng đời, key TTL thường đủ.
2. **Redis server là phiên bản nào?** Native field TTL cần **7.4+**; HSETEX/HGETEX cần **8.0+**.
3. **Spring Data Redis và driver có API tương ứng không?** High-level field expiration có từ **Spring Data Redis 3.5**.
4. **Hành vi khi cập nhật field là gì?** HSET ghi đè xóa TTL field; cần quyết định đặt lại, giữ nguyên hay gia hạn hạn.
5. **Có TTL cấp key song song không?** Key hết hạn trước sẽ xóa mọi field.
6. **Có cần cập nhật value và hạn nguyên tử không?** Chọn HSETEX hoặc script khi cần, không mặc nhiên ghép HSET + HEXPIRE.
7. **Có xử lý timeout, retry và key không tồn tại không?** Đọc đúng các mã kết quả; không coi lỗi mạng là bằng chứng lệnh chưa chạy.
8. **Có phụ thuộc vào expiration notification để làm nghiệp vụ không?** Nếu có, thiết kế thêm cơ chế phục hồi/đảm bảo thực thi.

## 20. Tài liệu tham khảo

- [Redis — Hashes và Hash field expiration](https://redis.io/docs/latest/develop/data-types/hashes/)
- [Redis — HEXPIRE, cú pháp, điều kiện và kết quả](https://redis.io/docs/latest/commands/hexpire/)
- [Redis — HTTL](https://redis.io/docs/latest/commands/httl/)
- [Redis — HSETEX (Redis 8.0+)](https://redis.io/docs/latest/commands/hsetex/)
- [Redis — HGETEX (Redis 8.0+)](https://redis.io/docs/latest/commands/hgetex/)
- [Spring Data Redis 3.5 — HashOperations API](https://docs.spring.io/spring-data/redis/reference/3.5/api/java/org/springframework/data/redis/core/HashOperations.html)

## 21. Tổng kết

**TTL của Hash key** và **TTL của Hash field** là hai mức quản lý vòng đời dữ liệu khác nhau. **EXPIRE/TTL** áp dụng cho cả key nên tất cả field cùng biến mất khi key hết hạn. Từ **Redis 7.4**, **HEXPIRE/HTTL** và các lệnh liên quan cho phép từng field hết hạn độc lập. **Redis 8.0** bổ sung **HSETEX/HGETEX** để thực hiện các thao tác field kèm expiration trong một command; **Spring Data Redis 3.5** bổ sung API field expiration ở **HashOperations**.

Khi triển khai, phải kiểm tra **đồng thời phiên bản Redis server và Spring Data Redis**, hiểu **TTL cấp key luôn giới hạn vòng đời field**, và đặc biệt chú ý **HSET ghi đè có thể xóa field TTL**. Những hệ thống chưa có native field expiration vẫn có thể dùng key TTL riêng hoặc timestamp trong dữ liệu, nhưng cần nhận thức rõ khác biệt về độ phức tạp, tự dọn dẹp và tính nguyên tử.
