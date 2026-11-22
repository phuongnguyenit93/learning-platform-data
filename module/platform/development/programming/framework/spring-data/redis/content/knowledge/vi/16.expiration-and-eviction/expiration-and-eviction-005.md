# Ảnh hưởng của các lệnh ghi đến TTL hiện có trong Spring Data Redis

## 1. Vấn đề: ghi đè dữ liệu có làm mất thời hạn sống?

Giả sử một ứng dụng lưu mã xác thực trong Redis và yêu cầu mã tự hết hạn sau hai phút:

```redis
SET otp:user:42 "123456" EX 120
```

Sau 30 giây, ứng dụng phát hiện mã cần thay đổi và thực hiện:

```redis
SET otp:user:42 "654321"
```

Giá trị đã thay đổi, nhưng **thời hạn hết hạn cũng bị xóa**. Lệnh `SET` thông thường thay thế giá trị của key và khiến key trở thành không có TTL, dù trước đó key đã được gắn thời hạn. Nếu ứng dụng chỉ tập trung vào dữ liệu mới mà bỏ qua thuộc tính hết hạn, mã xác thực có thể tồn tại lâu hơn chính sách cho phép.

Hiểu chính xác tác động của từng loại lệnh ghi đến TTL là điều cần thiết khi triển khai cache, session, giỏ hàng, OTP, bộ đếm giới hạn truy cập hoặc dữ liệu tạm thời bằng **Spring Data Redis**.

Kết quả cần nắm được sau bài học:

- Phân biệt thao tác **thay thế toàn bộ giá trị**, **chỉnh sửa nội dung hiện có**, **thay đổi thời điểm hết hạn** và **xóa key**.
- Dự đoán TTL sau các lệnh Redis thường gặp và API tương ứng trong `RedisTemplate` / `StringRedisTemplate`.
- Chọn cách ghi phù hợp để **xóa TTL**, **thiết lập TTL mới**, **giữ hạn hết cũ** hoặc **gia hạn chủ động**.
- Nhận diện các lỗi thực tế khi kết hợp lệnh ghi với `EXPIRE`, khi key đã hết hạn, hoặc khi nhiều client ghi đồng thời.

## 2. TTL là thuộc tính của key, không phải của chuỗi giá trị

**TTL (Time To Live)** là khoảng thời gian còn lại trước khi Redis xem một key là hết hạn. Redis lưu thời điểm hết hạn gắn với **key**; TTL không phải một trường nằm trong giá trị String, Hash, List, Set hoặc Sorted Set. Khi thời điểm này trôi qua, key sẽ được coi là không còn tồn tại và có thể bị loại bỏ bằng cơ chế hết hạn chủ động hoặc thụ động.

Hai lệnh quan sát thường dùng:

```redis
TTL cache:product:42
PTTL cache:product:42
```

| Kết quả | Ý nghĩa |
|---|---|
| `TTL` trả về số nguyên không âm | Số **giây** TTL còn lại, ở độ phân giải giây. |
| `PTTL` trả về số nguyên không âm | Số **mili giây** TTL còn lại. |
| `-1` | Key còn tồn tại nhưng **không có thời điểm hết hạn**. |
| `-2` | Key **không tồn tại** (bao gồm trường hợp đã hết hạn). |

Ví dụ:

```text
> SET cache:product:42 "A" EX 120
OK
> TTL cache:product:42
(integer) 120
> PTTL cache:product:42
(integer) 119980
```

Các số TTL thực tế giảm dần theo thời gian; số trong ví dụ chỉ minh họa. Nếu `PTTL` giảm từ 90.000 xuống 89.000 mili giây sau một lệnh ghi thì **không có nghĩa lệnh ghi đã đặt lại TTL**. Trước hết hãy xác định TTL đang tiếp tục đếm theo hạn cũ hay được làm mới thành một thời lượng khác.

Một key có thể tồn tại không giới hạn về mặt TTL, nhưng điều đó **không bảo đảm key luôn tồn tại**: thao tác xóa thủ công, chính sách loại bỏ khi thiếu bộ nhớ (eviction) hoặc quản trị Redis vẫn có thể xóa key. TTL và eviction là hai cơ chế khác nhau.

## 3. Quy tắc cốt lõi của Redis

Redis phân biệt giữa **ghi đè/thay thế giá trị của key** và **sửa nội dung bên trong giá trị đang tồn tại**.

1. **Thay thế toàn bộ giá trị:** thông thường **xóa TTL cũ**. Ví dụ: `SET` không kèm tùy chọn hết hạn, `GETSET`, `MSET` và nhiều lệnh ghi kết quả vào key đích như `SUNIONSTORE`.
2. **Sửa một phần giá trị hiện có:** thông thường **giữ nguyên thời điểm hết hạn cũ**. Ví dụ: `INCR`, `APPEND`, `HSET`, `LPUSH`, `SADD`, `ZADD`.
3. **Chỉ định hạn hết hạn trong chính lệnh ghi:** TTL được **thay bằng hạn mới**, trừ trường hợp lệnh yêu cầu rõ ràng `KEEPTTL`.
4. **Thao tác trực tiếp lên expiration:** `EXPIRE` / `PEXPIRE` có thể đặt hoặc cập nhật hạn; `PERSIST` bỏ hạn; `DEL` / `UNLINK` xóa key.

Đây là quy tắc theo **ngữ nghĩa của lệnh Redis thực sự được gửi**, không dựa trên việc phương thức Java có chứa chữ `set`, `update` hay `save`. Một phương thức ở tầng ứng dụng có thể phát sinh nhiều lệnh Redis khác nhau.

### Bảng đối chiếu nhanh

| Lệnh Redis | Tác động lên key đã có TTL | Lưu ý |
|---|---|---|
| `SET key value` | **Xóa TTL** | Giá trị được thay hoàn toàn. |
| `SET key value EX 60`, `PX 60000` | **Đặt TTL mới** | Thay cả giá trị và hạn hết hạn trong một lệnh. |
| `SET key value KEEPTTL` | **Giữ thời điểm hết hạn cũ** | Không khởi động lại đồng hồ TTL. |
| `SET ... NX` / `SET ... XX` | Tùy lệnh **có thực thi thành công không** | Nếu điều kiện thất bại, key và TTL không đổi; nếu thành công, áp dụng quy tắc `SET` và tùy chọn hết hạn đi kèm. |
| `GETSET`, `MSET` | **Xóa TTL** của key được ghi đè | Các lệnh thay thế giá trị. |
| `INCR`, `DECR`, `INCRBY`, `APPEND`, `SETRANGE`, `SETBIT` | **Giữ TTL** | Chỉnh sửa giá trị String hiện có. |
| `HSET`, `HINCRBY`, `HDEL` | **Giữ TTL**, nếu key vẫn tồn tại | Xóa trường cuối cùng có thể khiến cả Hash biến mất. |
| `LPUSH`, `RPUSH`, `LSET`, `LTRIM` | **Giữ TTL**, nếu List vẫn tồn tại | Thao tác làm List rỗng có thể xóa key. |
| `SADD`, `SREM`, `ZADD`, `ZREM`, `XADD` | **Giữ TTL**, nếu key vẫn tồn tại | Chỉnh sửa cấu trúc dữ liệu hiện có. |
| `SUNIONSTORE`, `ZUNIONSTORE`, `SORT ... STORE` | **Xóa TTL cũ** của key đích | Kết quả được ghi thay thế vào key đích. |
| `EXPIRE`, `PEXPIRE`, `EXPIREAT`, `PEXPIREAT` | **Thiết lập/cập nhật thời điểm hết hạn** | Có thể thay đổi TTL mà không thay đổi giá trị. |
| `PERSIST` | **Xóa TTL** | Key vẫn còn, trừ khi đã biến mất trước đó. |
| `GETEX key EX 60` / `GETEX key PERSIST` | **Đổi TTL** / **xóa TTL** | Dù tên bắt đầu bằng GET, đây có thể là lệnh ghi. |
| `DEL`, `UNLINK`, `GETDEL` | **Xóa key** | Truy vấn TTL sau đó trả `-2`. |
| `RENAME source destination` | Key đích **nhận TTL của source** | Nếu destination đã tồn tại, cả giá trị và hạn cũ của destination bị thay thế. |

**Điểm dễ nhầm:** `HSET` cập nhật một field **không** đồng nghĩa đặt lại thời gian sống của cả Hash; ngược lại, `SET` gán một String mới thường **làm mất TTL**, dù String mới có nội dung bằng hệt String cũ.

## 4. Ghi đè toàn bộ: TTL biến mất nếu không được chỉ định

### 4.1. `SET` thông thường

```text
> SET session:42 "draft" EX 90
OK
> TTL session:42
(integer) 90
> SET session:42 "confirmed"
OK
> TTL session:42
(integer) -1
> GET session:42
"confirmed"
```

TTL `-1` ở đây nghĩa là key **vẫn tồn tại**, nhưng không còn hết hạn tự động theo hạn cũ. Redis không ghi nhớ số giây ban đầu để áp dụng lại vào lần `SET` tiếp theo.

Lệnh `GETSET` (đọc giá trị cũ rồi đặt giá trị mới) cũng thay thế toàn bộ giá trị và xóa TTL. Tương tự, `MSET` ghi nhiều cặp key/value và xóa TTL cũ của những key bị ghi đè. Redis hiện đại có thể có các lệnh bổ sung tùy phiên bản, nhưng không được suy diễn các tùy chọn của `SET` sang mọi lệnh ghi hàng loạt.

### 4.2. Ghi thành công hay thất bại mới quyết định tác động

`SET` hỗ trợ điều kiện:

- `NX`: chỉ ghi khi key chưa tồn tại.
- `XX`: chỉ ghi khi key đã tồn tại.

Ví dụ với key hiện có:

```text
> SET lock:42 "owner-A" EX 60
OK
> SET lock:42 "owner-B" NX
(nil)
> TTL lock:42
(integer) 58
> SET lock:42 "owner-B" XX
OK
> TTL lock:42
(integer) -1
```

Lệnh `NX` thất bại nên không sửa value hoặc TTL; lệnh `XX` thành công, ghi đè và xóa TTL vì không kèm tùy chọn hết hạn. Tương tự, `MSETNX` thất bại khi có key đã tồn tại sẽ không thay đổi các key trong nhóm.

Trong Spring Data Redis, `opsForValue().setIfAbsent(key, value)` thường được dùng để tạo lock hoặc marker. Nếu muốn key mới có hạn, hãy dùng biến thể có `Duration`; việc tạo key không kèm hạn có thể tạo dữ liệu tồn tại lâu ngoài dự kiến.

## 5. Đặt hạn mới hay giữ nguyên hạn cũ khi ghi String

Để giải quyết bài toán thay giá trị mà vẫn kiểm soát TTL, cần chọn **một trong ba ý định** sau.

### 5.1. Thay giá trị và khởi tạo TTL mới

```text
> SET otp:user:42 "123456" EX 120
OK
> SET otp:user:42 "654321" EX 120
OK
> TTL otp:user:42
(integer) 120
```

Tùy chọn `EX` nhận giây, `PX` nhận mili giây; `EXAT` và `PXAT` dùng thời điểm Unix tuyệt đối (giây/mili giây). Việc ghi giá trị và đặt expiration trong **cùng một lệnh `SET`** là thao tác nguyên tử ở phía Redis.

Thích hợp khi một bản ghi mới có vòng đời độc lập, ví dụ mỗi mã OTP mới được phép tồn tại tối đa hai phút kể từ khi phát hành.

### 5.2. Thay giá trị nhưng giữ nguyên deadline cũ

```text
> SET ticket:42 "issued" EX 120
OK
> SET ticket:42 "used" KEEPTTL
OK
> TTL ticket:42
(integer) 110
```

`KEEPTTL` giữ **thời điểm hết hạn còn lại**, không đặt lại thời lượng 120 giây. Nó hữu ích khi một token, phiên làm việc hoặc giỏ hàng phải kết thúc tại deadline đã định ngay cả khi trạng thái được cập nhật.

Redis hỗ trợ tùy chọn `SET ... KEEPTTL` từ Redis 6.0. Nếu key chưa tồn tại hoặc đã hết hạn trước khi `SET` chạy, không có TTL cũ nào để giữ: key mới được tạo mà không có hạn, trừ khi lệnh sử dụng cách thiết lập expiration khác. Vì vậy, nếu yêu cầu nghiệp vụ là "chỉ sửa key đã tồn tại mà giữ hạn", hãy cân nhắc `SET ... XX KEEPTTL`.

### 5.3. Thay giá trị và chủ động xóa TTL

```redis
SET feature:banner "permanent"
```

Đây là lựa chọn đúng nếu chuyển một key từ dữ liệu tạm thời sang dữ liệu cần giữ lâu dài. Điểm quan trọng là **ý định xóa TTL phải rõ ràng**; không nên vô tình đạt kết quả này khi chỉ muốn cập nhật một trường trạng thái.

## 6. Chỉnh sửa tại chỗ: TTL tiếp tục đếm

Các lệnh tác động lên nội dung của một key thường không thay deadline. Redis coi đó là **cập nhật giá trị hiện có**, không phải thay thế cả key.

### 6.1. String dùng làm bộ đếm

```text
> SET rate:user:42 "0" EX 60
OK
> INCR rate:user:42
(integer) 1
> INCRBY rate:user:42 2
(integer) 3
> TTL rate:user:42
(integer) 57
```

`INCR` / `INCRBY` tăng giá trị nhưng giữ hạn ban đầu. Vì vậy, nếu bộ đếm biểu diễn một cửa sổ thời gian cố định, mỗi lượt truy cập **không tự kéo dài cửa sổ**. `DECR`, `APPEND`, `SETRANGE` và `SETBIT` cũng thuộc nhóm thay đổi nội dung giữ TTL.

Nếu bộ đếm **đã hết hạn trước lúc `INCR` chạy**, Redis coi key như không tồn tại, khởi tạo giá trị mới và **không tự gắn TTL** cho key mới. Đây là lý do một thuật toán rate limiting phải bảo đảm việc gắn hạn khi khởi tạo bộ đếm, không chỉ dựa vào TTL của lần trước.

### 6.2. Hash: cập nhật field không reset TTL của Hash

```text
> HSET cart:42 item:1 2
(integer) 1
> EXPIRE cart:42 300
(integer) 1
> HSET cart:42 item:2 1
(integer) 1
> HINCRBY cart:42 item:1 1
(integer) 3
> TTL cart:42
(integer) 295
```

TTL thuộc về **`cart:42`**, không thuộc riêng `item:1` hoặc `item:2`. Mỗi lần `HSET` / `HINCRBY` không tự gia hạn cả giỏ hàng. Xóa một field bằng `HDEL` cũng giữ hạn của key nếu Hash còn field khác; nếu xóa field cuối cùng, key có thể biến mất và `TTL` trả `-2`.

Tương tự, các thao tác List, Set, Sorted Set và Stream thường giữ TTL khi thay đổi phần tử trong cấu trúc hiện có. Nếu một thao tác làm key không còn tồn tại (chẳng hạn xóa phần tử cuối cùng của Set), sẽ không có TTL để giữ.

### 6.3. So sánh hai cách biểu diễn cùng một nghiệp vụ

Giỏ hàng được lưu như một **String JSON**:

```text
SET cart:42 "{\"item1\":2}" EX 300
SET cart:42 "{\"item1\":3}"             # TTL cũ bị xóa
```

Giỏ hàng được lưu như một **Redis Hash**:

```text
HSET cart:42 item1 2
EXPIRE cart:42 300
HSET cart:42 item1 3                    # TTL tiếp tục đếm
```

Không phải Redis "ưu tiên" Hash; đây là khác biệt giữa `SET` thay giá trị nguyên khối và `HSET` sửa trường trong cấu trúc hiện có. Khi chọn mô hình dữ liệu, hãy tính đến hành vi expiration của **lệnh cập nhật dự kiến**.

## 7. Các lệnh thay đổi TTL trực tiếp

### 7.1. `EXPIRE` có thể gia hạn hoặc rút ngắn

```text
> SET cart:42 "content" EX 300
OK
> EXPIRE cart:42 30
(integer) 1
> TTL cart:42
(integer) 30
```

`EXPIRE` đặt thời lượng mới **tính từ lúc lệnh thực thi**, không cộng thêm vào thời lượng còn lại. Tương tự, `PEXPIRE` làm việc bằng mili giây, còn `EXPIREAT` / `PEXPIREAT` đặt deadline tuyệt đối.

Lệnh `EXPIRE` còn hỗ trợ điều kiện (Redis 7.0+):

| Tùy chọn | Điều kiện để áp dụng expiration |
|---|---|
| `NX` | Key hiện chưa có expiration. |
| `XX` | Key hiện đã có expiration. |
| `GT` | Deadline mới muộn hơn deadline hiện tại. |
| `LT` | Deadline mới sớm hơn deadline hiện tại. |

Khi dùng `GT`, một key không có TTL được xem như có deadline vô hạn, nên bạn không thể dùng `GT` để đặt TTL hữu hạn cho key đó. Với `LT`, key không có TTL được xem như hạn vô hạn, nên có thể gắn deadline ngắn hơn. Tùy chọn điều kiện giúp tránh vô tình gia hạn hoặc rút ngắn key khi nhiều luồng cùng thao tác.

Nếu đặt `EXPIRE` / `PEXPIRE` với thời lượng không dương, hoặc đặt thời điểm `EXPIREAT` / `PEXPIREAT` trong quá khứ, Redis sẽ **xóa key ngay**. Trạng thái sau đó là `TTL = -2`.

### 7.2. `PERSIST` bỏ hạn nhưng giữ giá trị

```text
> SET notice:42 "temporary" EX 60
OK
> PERSIST notice:42
(integer) 1
> TTL notice:42
(integer) -1
```

Không nên nhầm `PERSIST` với `DEL`: `PERSIST` chỉ xóa metadata hết hạn; `DEL` xóa luôn key.

### 7.3. Lệnh có chữ GET vẫn có thể đổi TTL

`GET` và `MGET` thông thường không thay TTL. Tuy nhiên:

- `GETEX key EX 30`: đọc giá trị và đặt TTL mới 30 giây.
- `GETEX key PERSIST`: đọc giá trị và xóa TTL.
- `GETEX key` không kèm tùy chọn: đọc và không yêu cầu thay đổi TTL.
- `GETDEL key`: đọc rồi xóa key.

Khi xây dựng **sliding expiration** (gia hạn thời hạn sau mỗi lần truy cập), cần chủ động chọn `GETEX ... EX` hoặc kết hợp cơ chế phù hợp. Việc chỉ dùng `GET` không tự kéo dài thời hạn sống.

## 8. Ghi vào key đích và đổi tên key

### 8.1. Các lệnh *STORE có key đích riêng

```text
> SET result:42 "old" EX 60
OK
> SADD group:A alice bob
(integer) 2
> SADD group:B bob carol
(integer) 2
> SUNIONSTORE result:42 group:A group:B
(integer) 3
> TTL result:42
(integer) -1
```

`SUNIONSTORE` ghi kết quả Set mới vào `result:42`, thay thế giá trị và làm mất TTL cũ của key đích. Các lệnh tương tự như `ZUNIONSTORE`, `SINTERSTORE` hay `SORT ... STORE` cũng cần được xem là **ghi kết quả mới vào key đích**, thay vì cập nhật từng phần tử bên trong key đó.

### 8.2. `RENAME` mang theo TTL của nguồn

```text
> SET temp:42 "A" EX 120
OK
> RENAME temp:42 active:42
OK
> TTL temp:42
(integer) -2
> TTL active:42
(integer) 115
```

Key mới `active:42` nhận giá trị **và hạn hết hạn** từ `temp:42`. Nếu `active:42` đã tồn tại trước đó, TTL cũ của `active:42` không được giữ; thuộc tính của key nguồn thay thế thuộc tính của đích. Nếu nguồn không có TTL, đích sau `RENAME` cũng không có TTL.

Đây là lý do khi thiết kế quy trình "tạo dữ liệu tạm rồi chuyển thành chính thức", phải xem việc đổi tên có thực sự phù hợp với yêu cầu thời hạn sống.

## 9. Tác động qua API Spring Data Redis

`StringRedisTemplate` là lựa chọn thuận tiện khi key và value đều là String; `RedisTemplate<K, V>` dùng cơ chế tương tự với các serializer được cấu hình. Hành vi TTL cơ bản cuối cùng vẫn phụ thuộc vào lệnh Redis do operation tạo ra.

| Mã Java | Redis thường tương ứng | Tác động lên TTL đã có |
|---|---|---|
| `opsForValue().set(key, value)` | `SET` | Xóa TTL. |
| `opsForValue().set(key, value, Duration.ofMinutes(5))` | `SET` kèm expiration | Đặt lại TTL năm phút. |
| `opsForValue().setIfAbsent(key, value, Duration.ofSeconds(30))` | `SET ... NX` kèm expiration | Tạo key với TTL khi thành công; key có sẵn không đổi. |
| `opsForValue().setIfPresent(key, value)` | `SET ... XX` | Nếu thành công, ghi đè và xóa TTL. |
| `opsForValue().getAndSet(key, value)` | `GETSET` hoặc thao tác `SET GET` tương đương | Ghi đè và xóa TTL. |
| `opsForValue().multiSet(values)` | `MSET` | Xóa TTL cũ của các key được ghi. |
| `opsForValue().increment(key)` | `INCR` | Giữ TTL nếu key tồn tại. |
| `opsForValue().set(key, value, offset)` | `SETRANGE` | Giữ TTL nếu key tồn tại; **khác overload `set(key, value)`**. |
| `opsForHash().put(key, field, value)` | `HSET` | Giữ TTL của Hash nếu key tồn tại. |
| `opsForList().rightPush(key, value)` | `RPUSH` | Giữ TTL của List nếu key tồn tại. |
| `expire(key, Duration.ofSeconds(30))` | `EXPIRE` / `PEXPIRE` | Thay deadline. |
| `persist(key)` | `PERSIST` | Bỏ expiration. |
| `delete(key)` | `DEL` | Xóa key. |
| `rename(source, destination)` | `RENAME` | Mang TTL từ nguồn sang đích. |

### 9.1. Service Java minh họa các ý định khác nhau

Ví dụ dưới đây dùng Spring Boot và `spring-boot-starter-data-redis`, với `StringRedisTemplate` được inject vào bean:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ExpiringKeyService {

    private final StringRedisTemplate redis;

    public ExpiringKeyService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    // Thay toàn bộ value và xóa TTL trước đó.
    public void replaceWithoutTtl(String key, String value) {
        redis.opsForValue().set(key, value);
    }

    // Thay value và khởi động lại vòng đời 5 phút.
    public void replaceWithFreshTtl(String key, String value) {
        redis.opsForValue().set(key, value, Duration.ofMinutes(5));
    }

    // Chỉ tạo key nếu chưa có; khi thành công gắn TTL ngay.
    public boolean createIfAbsent(String key, String value) {
        return Boolean.TRUE.equals(
            redis.opsForValue().setIfAbsent(
                key, value, Duration.ofSeconds(30)
            )
        );
    }

    // Ghi field vào Hash mà không tự thay TTL của Hash hiện có.
    public void updateCartField(String key, String field, String quantity) {
        redis.opsForHash().put(key, field, quantity);
    }

    // Tăng counter hiện có, giữ TTL hiện tại của counter.
    public Long incrementCounter(String key) {
        return redis.opsForValue().increment(key);
    }

    // Chỉ khi muốn chủ động gia hạn vòng đời.
    public boolean refreshTtl(String key, Duration ttl) {
        return Boolean.TRUE.equals(redis.expire(key, ttl));
    }

    // Phân biệt -2 (vắng key), -1 (không TTL), >=0 (thời gian còn).
    public Long remainingMillis(String key) {
        return redis.getExpire(key, TimeUnit.MILLISECONDS);
    }

    public boolean removeExpiration(String key) {
        return Boolean.TRUE.equals(redis.persist(key));
    }
}
```

Ví dụ `getExpire` trả về `Long`, có thể là `null` trong ngữ cảnh pipeline/transaction theo hợp đồng Spring Data Redis. Đừng ép trả về kiểu `long` hoặc coi `null` là "không tồn tại" khi đang dùng các cơ chế đó.

### 9.2. Giữ TTL cũ khi thay toàn bộ String qua kết nối mức thấp

Với Spring Data Redis 3.x, khi cần `SET ... KEEPTTL`, có thể dùng `RedisCallback` và `RedisStringCommands`. Ví dụ sau minh họa trường hợp khóa/giá trị được mã hóa UTF-8 giống cấu hình mặc định của `StringRedisTemplate`:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.data.redis.connection.RedisStringCommands;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.types.Expiration;

public class KeepTtlWriter {

    private final StringRedisTemplate redis;

    public KeepTtlWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Boolean replaceAndKeepTtl(String key, String value) {
        byte[] keyBytes = key.getBytes(StandardCharsets.UTF_8);
        byte[] valueBytes = value.getBytes(StandardCharsets.UTF_8);

        return redis.execute((RedisCallback<Boolean>) connection ->
            connection.stringCommands().set(
                keyBytes,
                valueBytes,
                Expiration.keepTtl(),
                RedisStringCommands.SetOption.upsert()
            )
        );
    }
}
```

Đây là **một lệnh `SET` nguyên tử có `KEEPTTL`**, tránh cửa sổ đua khi ứng dụng đọc TTL rồi ghi giá trị và đặt lại hạn bằng các lệnh riêng. Mã cần kết nối Redis hỗ trợ `KEEPTTL` (Redis 6.0+). Với serializer tùy biến, phải dùng đúng serializer của template thay vì mặc định `StandardCharsets.UTF_8`; nếu không, các byte key/value có thể khác với dữ liệu đã ghi trước đó. Ở các phiên bản Spring Data Redis khác, hãy đối chiếu API đang dùng vì bề mặt lệnh mức thấp có thể thay đổi.

Nếu nghiệp vụ muốn **chỉ sửa một key còn tồn tại**, có thể thay `SetOption.upsert()` bằng `SetOption.ifPresent()` để áp dụng điều kiện `XX` cùng `KEEPTTL`; nếu key biến mất trước lúc thực thi, lệnh sẽ không tạo lại key không có expiration.

### 9.3. Không suy diễn hành vi của Redis Repository từ `HSET`

Các repository được ánh xạ từ object (ví dụ `@RedisHash`, `@TimeToLive`) có thể thực hiện nhiều thao tác ghi, cập nhật chỉ mục hoặc gắn lại thời hạn tùy cấu hình và phiên bản. Vì thế, không thể kết luận `repository.save(entity)` luôn giữ TTL chỉ vì dữ liệu được biểu diễn bằng Hash. Khi cần chính sách hết hạn chính xác, phải hiểu hành vi mapping của repository hoặc dùng operation Redis có ngữ nghĩa TTL rõ ràng.

## 10. Hai chính sách expiration thường gặp

### 10.1. Fixed expiration: deadline cố định kể từ khi tạo

Ví dụ: giỏ hàng hết hạn 15 phút kể từ thời điểm tạo. Cập nhật số lượng sản phẩm không kéo dài deadline:

```java
String key = "cart:42";

// Khởi tạo và đặt TTL ban đầu.
redis.opsForHash().put(key, "item:101", "1");
redis.expire(key, Duration.ofMinutes(15));

// Các thay đổi tiếp theo không gọi expire().
redis.opsForHash().put(key, "item:101", "2");
redis.opsForHash().put(key, "item:102", "1");
```

Ở ví dụ rút gọn này, hai thao tác khởi tạo ban đầu là **hai lệnh riêng**; nếu ứng dụng lỗi giữa hai lệnh, key có thể tồn tại mà không có TTL. Trong hệ thống thực tế phải xử lý rủi ro đó, chẳng hạn bằng script Lua hoặc transaction phù hợp khi cần bảo đảm tạo giá trị và gắn TTL như một đơn vị.

### 10.2. Sliding expiration: gia hạn theo hoạt động gần nhất

Ví dụ: session hết hạn sau 15 phút **không hoạt động**. Cập nhật Hash bằng `HSET` **không đủ** để gia hạn TTL. Ứng dụng phải chủ động gia hạn:

```java
String key = "session:42";
redis.opsForHash().put(key, "lastAction", "view-cart");
redis.expire(key, Duration.ofMinutes(15));
```

Khác biệt về chính sách:

| Tình huống | Fixed expiration | Sliding expiration |
|---|---|---|
| Cập nhật giá trị | Hạn cũ giữ nguyên | Hạn được chủ động gia hạn |
| Thao tác phù hợp | `HSET`, `INCR`, hoặc `SET KEEPTTL` | Ghi kèm TTL mới, `EXPIRE`, hoặc thao tác kết hợp tương ứng |
| Rủi ro khi triển khai sai | Key bị kéo dài vòng đời ngoài chính sách | Key hết hạn dù người dùng vẫn hoạt động |

Khi cần đảm bảo "chỉ gia hạn khi key còn tồn tại" trong bối cảnh nhiều request đồng thời, phải xét thời điểm key có thể hết hạn giữa các lệnh, hoặc gói các thao tác có điều kiện vào một script Lua.

## 11. Các lỗi dễ gặp khi cập nhật dữ liệu có TTL

### Lỗi 1: `SET` rồi `EXPIRE` trong hai lệnh để tạo cache

```java
redis.opsForValue().set(key, value);
redis.expire(key, Duration.ofMinutes(5));
```

Nếu ứng dụng ngắt hoặc lệnh thứ hai thất bại, key có thể ở lại mà không có TTL. Cách ngắn gọn hơn khi muốn TTL mới là **ghi giá trị và TTL trong cùng một lệnh**:

```java
redis.opsForValue().set(key, value, Duration.ofMinutes(5));
```

### Lỗi 2: Đọc TTL rồi ghi đè và gắn lại "số giây còn"

```java
Long ttl = redis.getExpire(key);
redis.opsForValue().set(key, newValue);
if (ttl != null && ttl > 0) {
    redis.expire(key, Duration.ofSeconds(ttl));
}
```

Đoạn này không tương đương `KEEPTTL`. TTL đã giảm trong khoảng thời gian giữa các lệnh; key có thể hết hạn hoặc bị client khác thay đổi; việc gán TTL cũ lại có thể **dịch deadline**. Đặc biệt, khi `ttl = -1` hoặc `-2`, cách xử lý rất dễ sai.

Nếu muốn giữ đúng deadline của một key đã tồn tại, ưu tiên `SET ... XX KEEPTTL` thay vì dựng lại thời hạn từ giá trị đọc được.

### Lỗi 3: Tin rằng thao tác increment luôn giữ TTL, kể cả key mới

`INCR` giữ hạn của **key đang tồn tại**, nhưng khi key chưa có hoặc đã hết hạn, thao tác tạo counter mới **không có TTL**. Trong ví dụ giới hạn request bằng cửa sổ một phút, cặp lệnh sau có rủi ro khi process dừng giữa chừng:

```text
INCR rate:user:42
EXPIRE rate:user:42 60
```

Có thể xử lý bằng script Lua để nguyên tử hóa thao tác khởi tạo và gắn thời hạn:

```lua
-- KEYS[1]: tên counter; ARGV[1]: TTL mili giây, ví dụ "60000"
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return count
```

Script này minh họa một cửa sổ tính từ lần truy cập đầu tiên khi counter chưa có; nếu hệ thống có thể để lại **counter tồn tại nhưng không TTL** từ một phiên bản cũ, cần có chính sách sửa dữ liệu tồn đọng riêng. Không nên mặc định script trên chữa được mọi dữ liệu lỗi trong Redis.

### Lỗi 4: Vô tình gia hạn TTL trong mỗi lần sửa field

`HSET` tự nó giữ deadline. Nếu cứ gọi thêm `EXPIRE key 900` sau mọi lần sửa giỏ hàng, ta đã biến chính sách 15 phút từ lúc tạo thành 15 phút từ lần sửa cuối. Điều đó đúng hay sai phụ thuộc vào nghiệp vụ; tác động do **lệnh `EXPIRE` bổ sung**, không phải do `HSET`.

### Lỗi 5: Nhầm `-1` với `-2`

Một key bị `SET` ghi đè thường vẫn tồn tại và `TTL` trả `-1`. Khi key bị xóa hoặc hết hạn, Redis trả `-2`. Ở tầng Java, nên phân biệt rõ hai trạng thái này, đặc biệt khi xử lý cache miss, cấp phát lại key và thống kê dữ liệu tạm.

### Lỗi 6: Chỉ nhìn tên operation mà bỏ qua các lệnh nội bộ

Một lớp service có tên `updateSession` có thể gọi `opsForValue().set` hoặc `opsForHash().put`; hai cách có tác động TTL khác nhau. Mã dùng `repository.save` cũng có thể chứa nhiều thao tác khác một lệnh `HSET` trực tiếp. Khi gặp key "bỗng không hết hạn", hãy tìm **lệnh Redis cuối cùng ghi vào key** và phân loại theo bảng ở mục 3.

## 12. Cách kiểm tra hành vi TTL bằng redis-cli

Có thể tái hiện trên các key thử nghiệm riêng, theo từng nhóm thao tác:

```text
# 1. Thay toàn bộ giá trị làm mất TTL
SET demo:ttl:string "v1" EX 120
TTL demo:ttl:string
SET demo:ttl:string "v2"
TTL demo:ttl:string
# Lần TTL cuối: -1

# 2. Ghi với KEEPTTL giữ deadline đang đếm
SET demo:ttl:keep "v1" EX 120
SET demo:ttl:keep "v2" KEEPTTL
PTTL demo:ttl:keep
# PTTL còn dương và không bị đặt lại thành 120000 ms

# 3. Thao tác vào Hash giữ TTL
HSET demo:ttl:hash field1 "A"
EXPIRE demo:ttl:hash 120
HSET demo:ttl:hash field2 "B"
TTL demo:ttl:hash
# TTL còn dương; tiếp tục giảm dần

# 4. Xóa expiration nhưng vẫn giữ giá trị
PERSIST demo:ttl:hash
TTL demo:ttl:hash
# -1

# 5. Xóa key rồi xem TTL
DEL demo:ttl:hash
TTL demo:ttl:hash
# -2
```

Các dòng bắt đầu bằng `#` là chú thích của tài liệu; khi chạy tương tác trên redis-cli, chỉ thực hiện những dòng lệnh Redis. TTL có thể giảm tới `-2` nếu bạn để quá thời gian thử nghiệm.

Khi điều tra sự cố thật, trình tự hữu ích là: xác định **key bị ảnh hưởng**, lấy `PTTL` trước/sau thao tác trong môi trường kiểm soát, tra **lệnh Redis thực tế** phát sinh và đối chiếu với chính sách hết hạn đã chọn. Không dùng `KEYS *` trên Redis sản xuất chỉ để tìm key; hãy dùng tên key đã biết hoặc cơ chế quét phù hợp.

## 13. Tình huống tự suy luận

Giả sử tại thời điểm bắt đầu, các key được tạo như sau:

```redis
SET a "10" EX 100
SET b "hello" EX 100
HSET c field1 "x"
EXPIRE c 100
```

Sau đó ứng dụng lần lượt thực hiện:

| Lệnh | Kết quả mong đợi đối với TTL |
|---|---|
| `INCR a` | `a` tiếp tục có TTL; không quay lại 100 giây. |
| `SET a "11"` | `a` có `TTL = -1`. |
| `SET b "world" KEEPTTL` | `b` tiếp tục đếm tới deadline cũ. |
| `HSET c field2 "y"` | `c` tiếp tục có TTL. |
| `EXPIRE c 200` | `c` nhận TTL mới khoảng 200 giây. |
| `PERSIST c` | `c` còn tồn tại nhưng `TTL = -1`. |
| `DEL b` | `b` không còn tồn tại, `TTL = -2`. |

Thứ tự các thao tác và thời gian thực thi có thể làm thay đổi số giây cụ thể, nhưng **loại trạng thái** (còn hạn, không có hạn, đã mất key) phải khớp với ngữ nghĩa của lệnh.

## 14. Ghi nhớ để thiết kế đúng

Mỗi khi viết hoặc sửa một thao tác ghi vào Redis, hãy làm rõ ba câu hỏi:

1. **Thao tác có thay cả giá trị của key không?** Nếu có, xem lại TTL cũ; `SET` thông thường sẽ xóa nó.
2. **Deadline mong muốn là từ lúc tạo, từ lần cập nhật gần nhất, hay một mốc tuyệt đối?** Từ đó chọn `KEEPTTL`, TTL mới, hoặc thay đổi expiration có điều kiện.
3. **Có thể xảy ra lỗi hoặc cập nhật đồng thời giữa các lệnh không?** Nếu cần bảo đảm tính nguyên tử, ưu tiên một lệnh hỗ trợ expiration trực tiếp hoặc dùng Lua/transaction thích hợp.

Quy tắc thực dụng nhất: **`SET` thay toàn bộ thường xóa TTL; thao tác sửa tại chỗ thường giữ TTL; `EXPIRE` thay deadline; `KEEPTTL` giữ deadline cũ.** Hãy luôn kiểm chứng bằng lệnh thực tế mà Spring Data Redis gửi đi và chính sách vòng đời của dữ liệu.

## Tài liệu tham khảo

- [Redis – EXPIRE: điều kiện, xóa TTL khi ghi đè và hành vi của RENAME](https://redis.io/docs/latest/commands/expire/)
- [Redis – SET: EX/PX/EXAT/PXAT, NX/XX và KEEPTTL](https://redis.io/docs/latest/commands/set/)
- [Redis – GETEX: đọc và đồng thời thay đổi expiration](https://redis.io/docs/latest/commands/getex/)
- [Spring Data Redis 3.3 – ValueOperations API](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/core/ValueOperations.html)
- [Spring Data Redis 3.3 – RedisStringCommands API](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/connection/RedisStringCommands.html)
- [Spring Data Redis 3.3 – Expiration.keepTtl() API](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/core/types/Expiration.html)
