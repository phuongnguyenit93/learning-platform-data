# Phân biệt tính nguyên tử của lệnh với MULTI/EXEC trong Spring Data Redis

Trong Redis, một lệnh đơn như `INCR`, `SET` hay `HSET` thường được thực thi như một thao tác **nguyên tử** đối với các client khác trên Redis server đang xử lý lệnh đó. Redis cũng có cơ chế **`MULTI`/`EXEC`** để xếp hàng và thực thi nhiều lệnh liên tiếp mà không cho lệnh của client khác chen vào giữa quá trình thực thi nhóm. Hai cơ chế này liên quan tới tính nguyên tử, nhưng **không có cùng phạm vi**, và cả hai đều không tự đem lại giao dịch với rollback giống cơ sở dữ liệu quan hệ.

Khi dùng Spring Data Redis, sự khác biệt trở nên quan trọng vì một phương thức Java có thể gửi nhiều lệnh, một lời gọi repository có thể cập nhật nhiều key, còn `@Transactional` không tự biến tất cả các thao tác đó thành một transaction Redis theo ý nghĩa mong muốn.

Bài học này đi từ lệnh đơn, chuỗi lệnh, `MULTI`/`EXEC`, xử lý lỗi, `WATCH`, đến cách gọi giao dịch với `RedisTemplate` và cách chọn công cụ phù hợp cho từng yêu cầu nghiệp vụ.

## 1. “Nguyên tử” đang nói về điều gì?

Trong ngữ cảnh Redis, ta cần tách ít nhất ba câu hỏi:

1. **Một lệnh có bị client khác chen vào giữa khi server xử lý không?** Đây là tính nguyên tử của **lệnh đơn** về mặt quan sát và thực thi trên server.
2. **Một nhóm lệnh có được chạy liên tiếp mà không có lệnh khác xen giữa không?** Đây là tính chất quan trọng của **`MULTI`/`EXEC`**.
3. **Nếu lệnh thứ ba thất bại, mọi thay đổi của lệnh thứ nhất và thứ hai có tự được hoàn tác không?** Redis transaction **không** cung cấp rollback tổng quát theo kiểu SQL cho lỗi phát sinh khi `EXEC` đang thực thi.

Những câu hỏi trên cũng khác với **độ bền dữ liệu sau sự cố**. Một lệnh được Redis xử lý nguyên tử không có nghĩa thay đổi đã được lưu xuống đĩa hoặc đồng bộ đến mọi replica trong mọi cấu hình.

Có thể hình dung:

```text
Đơn vị nhỏ nhất:     [ INCR counter ]              -> một lệnh nguyên tử

Nhiều lệnh độc lập:  [ GET counter ] ... [ SET ]    -> có khoảng trống cho client khác

MULTI/EXEC:          MULTI
                     [ SET key:a ... ] --queued--
                     [ INCR key:b ]    --queued--
                     EXEC
                     [ chạy SET ][ chạy INCR ]      -> chạy liền nhau trên server

Rollback kiểu SQL:   một bước lỗi -> hoàn tác mọi bước
                     Redis MULTI/EXEC KHÔNG bảo đảm điều này.
```

**Quy tắc đầu tiên:** muốn biết chương trình có an toàn khi nhiều request chạy đồng thời hay không, phải xác định **toàn bộ phép toán nghiệp vụ cần nguyên tử**. Đừng chỉ kiểm tra xem các lệnh Redis riêng lẻ có nguyên tử hay không.

## 2. Tính nguyên tử của một lệnh Redis

Redis xử lý các lệnh trên một server theo mô hình thực thi được tuần tự hóa về mặt thao tác dữ liệu. Trong lúc một lệnh đang cập nhật dữ liệu, client khác không quan sát được các bước trung gian của chính lệnh đó bằng cách chen một lệnh đọc vào giữa.

Ví dụ:

```redis
SET views:article:42 0
INCR views:article:42
GET views:article:42
```

`INCR views:article:42` tự đọc giá trị hiện tại, cộng `1` và lưu lại trên server như một thao tác. Nếu nhiều client đồng thời gửi `INCR` tới cùng key, chúng không bị tình trạng cùng đọc một giá trị cũ rồi cùng ghi lại cùng một kết quả như mẫu `GET`/`SET` phía client.

### 2.1. Ví dụ mất cập nhật khi dùng hai lệnh

Giả sử bộ đếm ban đầu bằng `10`. Hai request A và B muốn tăng thêm một đơn vị:

```text
Thời điểm     Client A                           Client B
---------     --------                           --------
t1            GET count -> 10
t2                                               GET count -> 10
t3            SET count 11
t4                                               SET count 11
Kết quả:      count = 11, mặc dù có hai yêu cầu tăng.
```

Mỗi lệnh `GET` và `SET` đều được Redis xử lý nguyên tử **riêng lẻ**, nhưng chuỗi **đọc → tính → ghi** của từng request không nguyên tử.

Cách phù hợp hơn:

```redis
SET count 10
INCR count
INCR count
GET count
```

Kết quả sau hai lệnh tăng thành công là `12`. Phần đọc giá trị cũ và tăng được thực hiện bên trong từng lệnh `INCR`, không có khoảng trống để client khác chèn thao tác ghi giữa bước đọc và bước tăng.

### 2.2. Những lệnh có thể thay một chuỗi thao tác phía client

| Nhu cầu | Mẫu dễ có race condition | Lệnh/cách thường thích hợp hơn |
|---|---|---|
| Tăng bộ đếm | `GET` rồi `SET(value + 1)` | `INCR`, `INCRBY`, `HINCRBY` |
| Tạo khóa nếu chưa tồn tại | `EXISTS` rồi `SET` | `SET key value NX` |
| Ghi giá trị kèm TTL | `SET` rồi `EXPIRE` | `SET key value EX seconds` hoặc `PX` |
| Lấy và xóa khóa cùng lúc | `GET` rồi `DEL` | `GETDEL` khi được Redis hỗ trợ |
| Thêm thành viên vào tập | `SMEMBERS`, sửa Java Set, ghi lại | `SADD`, `SREM` trên Redis Set |
| Ghi nhiều giá trị được Redis hỗ trợ như một lệnh | Nhiều `SET` riêng rẽ | `MSET` nếu mô hình và phạm vi server/cluster cho phép |
| Kiểm tra điều kiện phức tạp rồi cập nhật | `GET`, `if`, `SET` | `WATCH` + `MULTI`/`EXEC` hoặc Lua/Redis Function |

Ví dụ ghi khóa và đặt TTL trong **một lệnh**:

```redis
SET auth:otp:42 "hash-of-code" NX EX 120
```

Lệnh trên chỉ ghi khi khóa chưa tồn tại và đặt thời hạn 120 giây cùng thao tác ghi thành công. Nếu tách thành `SETNX` và `EXPIRE`, tiến trình có thể dừng ở giữa, khiến khóa mới được tạo mà không có TTL.

### 2.3. Nguyên tử của lệnh không đồng nghĩa bất biến nghiệp vụ được bảo vệ

Ví dụ:

```redis
DECR stock:sku-5
```

`DECR` là thao tác nguyên tử, nhưng nó vẫn có thể làm số lượng trở thành `-1`. Nếu yêu cầu là “chỉ trừ tồn kho khi số lượng còn đủ”, tính nguyên tử của `DECR` **chưa giải quyết điều kiện nghiệp vụ**.

Muốn kiểm tra `stock >= quantity` rồi mới trừ, cần một cơ chế thực hiện cả kiểm tra và cập nhật nguyên tử, chẳng hạn Lua/Redis Function hoặc `WATCH` với giao dịch có điều kiện. Phần sau sẽ minh họa.

## 3. Nhiều lệnh đơn nguyên tử chưa tạo thành một thao tác nguyên tử

Đoạn Java sau gồm hai thao tác ghi:

```java
stringRedisTemplate.opsForValue().set("order:42:status", "PAID");
stringRedisTemplate.opsForValue().increment("metrics:paid-orders");
```

Từng lệnh Redis có tính nguyên tử của chính nó. Tuy nhiên, giữa hai lệnh có thể xảy ra:

- Client khác đọc trạng thái mới nhưng bộ đếm còn cũ.
- Tiến trình Java ngừng sau lệnh `SET` nhưng trước lệnh `INCR`.
- Lệnh đầu thành công, lệnh sau lỗi do dữ liệu hoặc cấu hình.
- Một request khác chen thao tác vào giữa hai lệnh.

Bởi vậy, **“hai lệnh đều nguyên tử” không suy ra “cặp lệnh nguyên tử”**.

Đây chính là lúc cần cân nhắc phạm vi của `MULTI`/`EXEC`, hoặc tìm một cách biểu diễn nghiệp vụ bằng **một lệnh**.

## 4. `MULTI`/`EXEC`: xếp hàng rồi thực thi nhóm lệnh

Redis transaction sử dụng hai lệnh chính:

- `MULTI`: bắt đầu chế độ xếp hàng các lệnh thuộc transaction.
- `EXEC`: thực thi danh sách lệnh đã xếp hàng.

Ví dụ trong Redis CLI:

```redis
SET metrics:paid-orders 0

MULTI
SET order:42:status "PAID"
INCR metrics:paid-orders
EXEC
```

Trong phiên làm việc tương tác, Redis thường trả:

```text
OK
QUEUED
QUEUED
1) OK
2) (integer) 1
```

`QUEUED` chỉ xác nhận lệnh được xếp hàng, **không có nghĩa lệnh đã chạy**. Kết quả thực sự được trả sau `EXEC`.

Khi `EXEC` bắt đầu thực thi, Redis chạy các lệnh trong nhóm theo thứ tự. Trong thời gian đó, các lệnh của client khác trên cùng server thực thi không chen vào giữa các lệnh của nhóm.

```text
Client A                           Redis                       Client B
--------                           -----                       --------
MULTI ---------------------------> bắt đầu queue
SET order:42 PAID ---------------> QUEUED
INCR paid-orders ----------------> QUEUED
                                                                   GET ...
EXEC ----------------------------> chạy SET
                                   chạy INCR
                                 -> trả kết quả
                                                                   GET được phục vụ
```

Hình vẽ minh họa tính không xen giữa của nhóm khi server thực thi `EXEC`; không có nghĩa Redis chặn mọi thao tác của client B trong suốt thời gian client A đang **xếp hàng** các lệnh. Các client khác vẫn có thể thực hiện lệnh ở khoảng thời gian trước `EXEC`.

### 4.1. `MULTI`/`EXEC` bảo đảm điều gì?

- Những lệnh đã được xếp hàng thành công sẽ được server thực thi **theo thứ tự** trong giai đoạn `EXEC`.
- Lệnh của client khác không xen giữa các lệnh trong chính giai đoạn thực thi nhóm đó.
- Client nhận được kết quả từng lệnh trong phản hồi `EXEC`.
- Có thể kết hợp với `WATCH` để tránh commit dựa trên dữ liệu đã bị client khác sửa trước khi `EXEC`.

### 4.2. `MULTI`/`EXEC` không tự bảo đảm điều gì?

- **Không rollback toàn bộ** nếu một lệnh bị lỗi khi đang được thực thi.
- **Không cho ứng dụng lấy kết quả `GET` bên trong queue rồi quyết định có xếp hàng lệnh tiếp theo hay không** theo cách thông thường, vì kết quả `GET` chỉ có sau `EXEC`.
- **Không gộp một chuỗi lệnh Java đã chạy ngoài transaction** thành một khối.
- **Không tự biến nhiều instance Redis, nhiều shard Redis Cluster hoặc Redis + RDBMS thành một transaction phân tán.**
- **Không tự bảo đảm durability trên mọi replica hoặc disk** khi `EXEC` trả về.
- **Không áp dụng ngầm** chỉ vì code dùng Spring Data Redis Repository hay thêm `@Transactional`.

Điểm cần nắm là `MULTI`/`EXEC` có tính **không bị xen giữa khi chạy nhóm lệnh**, nhưng khác với tính **all-or-nothing có hoàn tác** mà lập trình viên có thể quen từ cơ sở dữ liệu quan hệ.

## 5. Hai loại lỗi trong transaction Redis

Phân biệt lỗi **trước** `EXEC` và lỗi **khi thực thi** là điều cốt yếu.

### 5.1. Lỗi khi xếp hàng: transaction có thể bị hủy trước khi thực thi

Ví dụ lệnh sai số lượng tham số:

```redis
MULTI
SET tx:a 10
INCR
EXEC
```

Lệnh `INCR` thiếu key, nên Redis có thể phát hiện lỗi ngay lúc xếp hàng. Trên các phiên bản Redis hiện đại, transaction sẽ bị đánh dấu lỗi; `EXEC` không thực thi các lệnh đã xếp hàng mà trả lỗi dạng `EXECABORT`.

**Kết quả mong đợi:** `SET tx:a 10` trong nhóm không được thực thi khi `EXEC` bị hủy do lỗi queue-time.

Nhóm lỗi này có thể gồm lệnh sai cú pháp/sai số lượng tham số hoặc lỗi ở giai đoạn Redis nhận/xếp hàng lệnh. Không phải mọi lỗi đều có thể phát hiện sớm: Redis có thể chỉ biết key đang sai kiểu dữ liệu khi thực sự chạy lệnh.

### 5.2. Lỗi khi chạy: các lệnh khác vẫn có thể thành công

Đặt một key chứa chuỗi không phải số:

```redis
SET tx:number "hello"
```

Sau đó:

```redis
MULTI
SET tx:before "done"
INCR tx:number
SET tx:after "done"
EXEC
```

Tại `EXEC`, lệnh `INCR tx:number` lỗi do `"hello"` không thể dùng như số nguyên, nhưng hai lệnh `SET` còn lại vẫn có thể được thực thi thành công.

Có thể hình dung phản hồi:

```text
1) OK
2) (error) ERR value is not an integer or out of range
3) OK
```

Sau đó:

```redis
GET tx:before
GET tx:number
GET tx:after
```

Ta thấy `tx:before = "done"`, `tx:number = "hello"` và `tx:after = "done"`.

**Redis không tự rollback hai lệnh `SET` đã thành công chỉ vì `INCR` gặp lỗi.** Đây là khác biệt lớn giữa Redis transaction với kỳ vọng “một lỗi trong transaction thì hoàn tác tất cả” thường gặp khi dùng RDBMS.

### 5.3. `DISCARD` không phải rollback

Trước khi gọi `EXEC`, có thể hủy danh sách lệnh đã xếp hàng:

```redis
MULTI
SET tx:temporary "value"
DISCARD
GET tx:temporary
```

Lệnh `SET tx:temporary` không được chạy vì ta đã hủy queue trước `EXEC`.

Nhưng nếu đã:

```redis
MULTI
SET tx:temporary "value"
EXEC
```

thì `DISCARD` sau đó **không có tác dụng hoàn tác** thay đổi vừa thực thi. Muốn bù lại phải thực hiện một lệnh mới, ví dụ `DEL`, và cân nhắc ảnh hưởng của cập nhật đồng thời; phép bù đó không phải rollback nguyên tử.

| Trường hợp | Hành vi |
|---|---|
| `DISCARD` trước `EXEC` | Hủy các lệnh chưa được chạy |
| Lỗi phát hiện khi queue, `EXECABORT` | Nhóm không được chạy |
| Lỗi runtime ở một lệnh trong `EXEC` | Những lệnh khác có thể đã được chạy |
| Client mất kết nối trước `EXEC` | Các lệnh đang chờ trên connection đó không được commit chỉ bởi `MULTI` |
| Client mất kết nối khi/ sau khi gửi `EXEC` | Kết quả có thể **không rõ** với client: server có thể đã thực thi |
| Gửi một lệnh sửa ngược sau `EXEC` | Là thao tác mới, cần xét race condition và idempotency |

## 6. `MULTI`/`EXEC` không tự sửa được lỗi đọc–sửa–ghi

Giả sử tồn kho của sản phẩm bằng `1`:

```redis
SET stock:sku-5 1
```

Hai request đều làm:

```text
GET stock:sku-5
if stock > 0:
    MULTI
    DECR stock:sku-5
    SET reservation:<request> "created"
    EXEC
```

Cả request A và B có thể cùng đọc `1` trước khi một request gọi `EXEC`.

```text
Client A                        Client B
--------                        --------
GET stock -> 1
                                GET stock -> 1
MULTI
DECR stock
SET reservation:A created
EXEC  -> stock = 0
                                MULTI
                                DECR stock
                                SET reservation:B created
                                EXEC -> stock = -1
```

Mỗi transaction đều không có lệnh client khác xen vào **bên trong `EXEC` của nó**, nhưng cả hai đều dựa vào điều kiện được đọc **trước transaction**. `MULTI` không tự khóa giá trị đã đọc trước đó.

Không thể giải quyết đơn giản bằng cách xếp `GET` vào `MULTI` rồi làm `if` trong Java:

```redis
MULTI
GET stock:sku-5
```

Kết quả `GET` lúc này là `QUEUED`, không phải giá trị tồn kho để Java ra quyết định. Muốn gắn điều kiện với phép ghi an toàn, sử dụng **`WATCH`** hoặc thực hiện điều kiện tại server bằng Lua/Redis Function.

## 7. `WATCH`: kiểm tra dữ liệu không đổi trước `EXEC`

`WATCH key` là cơ chế optimistic concurrency của Redis.

Quy trình thường gặp:

```text
WATCH key
  |
GET key              -> đọc để ra quyết định
  |
Kiểm tra điều kiện
  |
MULTI
  |
xếp các lệnh ghi
  |
EXEC                 -> chạy nếu watched key chưa bị sửa;
                        hủy transaction nếu watched key đã đổi
```

Ví dụ phiên Redis CLI (chỉ mang tính mô phỏng, toàn bộ lệnh phía một client phải dùng **cùng connection**):

```redis
WATCH stock:sku-5
GET stock:sku-5
```

Nếu đủ tồn kho, client tiếp tục:

```redis
MULTI
DECR stock:sku-5
SET reservation:A "created"
EXEC
```

Nếu client khác đã sửa key `stock:sku-5` sau `WATCH` và trước `EXEC`, Redis sẽ từ chối thực thi transaction đang chờ. Phản hồi `EXEC` trong giao thức Redis cho một transaction bị hủy vì `WATCH` là **null reply**; thư viện client có thể ánh xạ kết quả theo API riêng.

Client cần xử lý kết quả này bằng cách đọc lại và cân nhắc retry; không coi null reply là thành công.

### 7.1. `WATCH` bảo vệ điều gì, chưa bảo vệ điều gì?

- Bảo vệ quyết định dựa trên **những key được theo dõi**. Nếu dữ liệu phụ thuộc nhiều key, phải xác định đủ key cần watch.
- Việc thay đổi key bởi client khác, kể cả những thay đổi do quá trình hết hạn/eviction, có thể làm transaction bị hủy.
- `WATCH` cần thực hiện trước `MULTI`; không dùng nó như phép đọc có điều kiện ngay giữa queue.
- Những lệnh `WATCH`, `GET`, `MULTI`, `EXEC` thuộc cùng transaction phải gắn với **một connection Redis**.
- Có thể có nhiều lần abort dưới tải đồng thời; phía ứng dụng cần retry có giới hạn, backoff và thông báo khi không còn đủ điều kiện.
- `WATCH` không thay thế kiểm tra nghiệp vụ. Nếu stock bằng `0`, logic phải dừng, không cần cố `EXEC`.
- `WATCH` không mang cơ chế rollback cho lỗi runtime **sau khi** các lệnh trong `EXEC` bắt đầu chạy.

Với một transaction bị bỏ qua trước `MULTI`, dùng `UNWATCH` hoặc kết thúc connection đúng cách để không để lại trạng thái watch cho hoạt động sau.

### 7.2. Tại sao `WATCH` là optimistic, không phải khóa pessimistic?

`WATCH` không bắt tất cả client khác phải ngừng sửa key. Các client khác vẫn có thể cập nhật dữ liệu bình thường. Redis chỉ kiểm tra khi client đang theo dõi gọi `EXEC`: nếu dữ liệu bị thay đổi, transaction bị hủy và client phải thực hiện lại phép tính trên dữ liệu mới.

Điều này giúp tránh chặn đồng thời lâu dài, nhưng ứng dụng phải chấp nhận khả năng xung đột và retry. `WATCH` không phải một khóa hàng như `SELECT ... FOR UPDATE` của RDBMS.

## 8. Lua script hoặc Redis Function: điều kiện và cập nhật tại server

Nếu một phép toán nghiệp vụ cần đọc dữ liệu, kiểm tra điều kiện rồi ghi **trong một lần thực thi nguyên tử tại Redis server**, Lua script thường là lựa chọn rõ ràng.

Ví dụ trừ tồn kho khi còn đủ:

```lua
-- KEYS[1] = "stock:sku-5"
-- ARGV[1] = số lượng muốn trừ
local requested = tonumber(ARGV[1])
if not requested or requested <= 0 or requested % 1 ~= 0 then
    return redis.error_reply("quantity must be a positive integer")
end

local raw = redis.call("GET", KEYS[1])
if not raw then
    return -1  -- không tìm thấy key tồn kho
end

local current = tonumber(raw)
if not current then
    return redis.error_reply("invalid stock value")
end

if current < requested then
    return 0   -- không đủ hàng
end

return redis.call("DECRBY", KEYS[1], requested)
```

Ứng dụng có thể gọi script qua `EVAL` hoặc API scripting của Spring Data Redis; Redis thực thi phần logic trong script mà không cho lệnh của client khác chen giữa.

Ví dụ trực tiếp trong Redis CLI:

```redis
SET stock:sku-5 2
EVAL "local n=tonumber(redis.call('GET',KEYS[1])); local q=tonumber(ARGV[1]); if not n or not q or q<=0 then return -1 end; if n<q then return 0 end; return redis.call('DECRBY',KEYS[1],q)" 1 stock:sku-5 1
GET stock:sku-5
```

Sau lần trừ thành công, số lượng còn `1`.

Lưu ý quan trọng:

- Script phải được thiết kế để kiểm tra những điều kiện có thể lỗi **trước bước ghi** khi cần giảm nguy cơ cập nhật dở dang.
- Lua cũng **không có rollback tổng quát** nếu script gây lỗi sau khi đã thay đổi dữ liệu.
- Script dài hoặc xử lý quá nhiều dữ liệu có thể chặn các lệnh khác tại Redis server trong thời gian chạy.
- Redis Cluster yêu cầu các key liên quan đến script tuân thủ các quy tắc định tuyến/hash slot phù hợp.
- Tính nguyên tử của script trên Redis không tự bảo đảm transaction với PostgreSQL, Kafka hay một hệ thống ngoài Redis.

`WATCH` phù hợp với cách đọc–tính ở client có thể retry. Lua/Redis Function phù hợp khi có thể đưa phép kiểm tra và cập nhật lên Redis server thành một thao tác rõ ràng.

## 9. Spring Data Redis: gọi lệnh đơn nguyên tử

Với dữ liệu đơn giản, nên chọn trực tiếp API `ValueOperations`, `HashOperations`, `SetOperations` tương ứng thay vì tạo transaction chỉ để thực hiện một phép toán đã có lệnh nguyên tử.

Ví dụ tăng bộ đếm:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ViewCounterService {

    private final StringRedisTemplate redis;

    public ViewCounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long increase(String articleId) {
        Long value = redis.opsForValue()
                .increment("views:article:" + articleId);
        if (value == null) {
            throw new IllegalStateException("Redis không trả kết quả");
        }
        return value;
    }
}
```

Lời gọi `increment` tương ứng với lệnh tăng nguyên tử trên Redis. Tránh thay bằng:

```java
String key = "views:article:" + articleId;
String raw = redis.opsForValue().get(key);
long current = raw == null ? 0 : Long.parseLong(raw);
redis.opsForValue().set(key, Long.toString(current + 1));
```

Đoạn thứ hai tạo khoảng trống giữa `GET` và `SET`, nên có thể mất cập nhật khi nhiều request chạy cùng lúc.

Một ví dụ ghi giá trị và TTL trong cùng lệnh:

```java
import java.time.Duration;

redis.opsForValue().set(
        "auth:otp:" + userId,
        hashedOtp,
        Duration.ofMinutes(2)
);
```

Cách này phù hợp khi cần đặt thời gian sống cho giá trị ngay lúc ghi. Tuy nhiên, một lệnh atomic không bảo đảm key sẽ tồn tại đủ hai phút nếu ứng dụng xóa chủ động hoặc Redis eviction theo cấu hình bộ nhớ.

## 10. Spring Data Redis: dùng `SessionCallback` cho `MULTI`/`EXEC`

`RedisTemplate` có API thực thi callback gắn với một session/connection, hữu ích khi cần `MULTI` và `EXEC` đúng trên cùng connection.

Ví dụ dùng `StringRedisTemplate` ghi hai key trong một transaction Redis:

```java
import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisTransactionDemo {

    private final StringRedisTemplate redis;

    public RedisTransactionDemo(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> writeTwoFlags() {
        return redis.execute(new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings("unchecked")
            public <K, V> List<Object> execute(
                    RedisOperations<K, V> operations
            ) throws DataAccessException {

                K firstKey = (K) "demo:tx:flag:a";
                K secondKey = (K) "demo:tx:flag:b";
                V value = (V) "ready";

                operations.multi();
                operations.opsForValue().set(firstKey, value);
                operations.opsForValue().set(secondKey, value);
                return operations.exec();
            }
        });
    }
}
```

Ở đây:

- `SessionCallback` duy trì phạm vi kết nối cho các lệnh transaction.
- `multi()` bắt đầu xếp hàng.
- Các lệnh `set(...)` được xếp hàng; đừng xem phản hồi mỗi lời gọi như kết quả đã commit.
- `exec()` thực thi nhóm và trả kết quả theo cách driver/serializer của template biểu diễn.
- Giá trị key/value được ép kiểu trong callback vì chữ ký generic của `SessionCallback`; code này sử dụng `StringRedisTemplate`, vì vậy dữ liệu thực tế đều là chuỗi.

Trong code thực tế cần xử lý thêm exception giữa `multi()` và `exec()`; nếu còn ở chế độ transaction chưa thực thi, có thể cần `discard()` để hủy hàng đợi trước khi trả connection. Không nên gọi `discard()` mù quáng sau khi `EXEC` đã thực thi rồi. Cũng không nên dùng callback trên để nhầm lẫn rằng `MULTI` có cơ chế rollback khi lệnh runtime thất bại.

### 10.1. Đọc kết quả trong lúc queue

Ví dụ ý tưởng sau **không** hoạt động như một read–modify–write thông thường:

```java
operations.multi();

// Giá trị trong transaction chỉ được trả khi EXEC chạy.
operations.opsForValue().get(key);

// Không thể dựa vào giá trị trả về lúc này để if/else và
// quyết định kết quả của GET đã được xếp hàng.
operations.exec();
```

Trong chế độ `MULTI`, Redis trả trạng thái `QUEUED` cho `GET` và chỉ cung cấp kết quả thật lúc `EXEC`. Ở Spring Data Redis, lời gọi đọc trong phần đang queue có thể trả `null`/giá trị placeholder tùy API; các kết quả thực nằm trong phản hồi `exec()`.

Nếu bài toán cần **ra quyết định dựa trên dữ liệu hiện tại**, dùng `WATCH` trước `MULTI` hoặc đưa phép so sánh vào script/server-side logic.

### 10.2. `@Transactional` khác gì `SessionCallback`?

Spring cung cấp annotation:

```java
@Transactional
public void businessOperation() {
    redis.opsForValue().set("demo:a", "1");
    redis.opsForValue().set("demo:b", "2");
}
```

Chỉ annotation này **không đủ căn cứ** để kết luận hai lệnh đã được đưa vào cùng Redis transaction:

1. Phải biết `@Transactional` đang dùng **transaction manager** nào, ví dụ transaction manager của RDBMS.
2. `RedisTemplate` có thể được cấu hình **tham gia Spring transaction** bằng cách bật transaction support; mặc định khả năng này không tự được bật chỉ vì có annotation.
3. Hành vi với lệnh đọc và thời điểm thực thi các lệnh ghi có khác biệt khi dùng connection đã tham gia Redis transaction.
4. Redis transaction vẫn mang giới hạn của `MULTI`/`EXEC` về lỗi runtime, durability và phạm vi server.
5. Có transaction DB và transaction Redis cùng xuất hiện trong một service **không** đồng nghĩa chúng có cơ chế commit/rollback phân tán nguyên tử.

Nếu cần quản lý transaction Redis trực tiếp ở cấp template, `SessionCallback` cho phép nhìn thấy rõ `multi()` và `exec()`. Khi cần tích hợp với Spring transaction management, phải cấu hình đúng, nắm rõ tài nguyên tham gia và chọn strategy xử lý lỗi phù hợp.

## 11. Đừng nhầm pipelining với transaction

Spring Data Redis có API pipeline nhằm giảm số lần trao đổi qua mạng khi gửi nhiều lệnh.

Ví dụ về ý tưởng:

```text
Pipeline:
  Gửi SET a 1
  Gửi SET b 2
  Gửi INCR c
  Nhận kết quả theo batch
```

Pipeline giúp cải thiện hiệu quả giao tiếp mạng, nhưng **không tạo một nhóm lệnh nguyên tử**: lệnh từ client khác vẫn có thể chen vào quá trình server nhận/thực thi các lệnh được pipeline gửi đến.

`MULTI`/`EXEC` giải quyết vấn đề khác:

```text
Transaction:
  MULTI
  SET a 1   -> QUEUED
  SET b 2   -> QUEUED
  INCR c    -> QUEUED
  EXEC      -> thực thi nhóm không bị interleave
```

Có thể kết hợp pipeline và transaction trong những hoàn cảnh nhất định, nhưng khi đó vẫn cần hiểu rõ **khi nào kết quả trở về** và **lúc nào `EXEC` thực thi**. Đừng coi `executePipelined(...)` là cách thay thế cho `multi()`/`exec()` hoặc một phép compare-and-set nguyên tử.

## 12. Một lệnh `MSET` và một transaction nhiều `SET` khác nhau thế nào?

Nếu nhiệm vụ chỉ là thiết lập cùng lúc nhiều giá trị và môi trường Redis hỗ trợ, `MSET` là một lệnh Redis đơn:

```redis
MSET config:current:A "on" config:current:B "off"
```

Trên phạm vi Redis server tương ứng, một lệnh `MSET` có tính nguyên tử của **một lệnh** đối với những key nó thao tác. Điều này tránh phải tự viết:

```redis
MULTI
SET config:current:A "on"
SET config:current:B "off"
EXEC
```

khi không cần logic phụ.

Tuy nhiên, cần lựa chọn dựa trên nhu cầu:

| Trường hợp | Cách cân nhắc |
|---|---|
| Ghi nhiều cặp key/value không có thao tác phụ | `MSET` nếu dùng được với mô hình dữ liệu |
| Chỉ ghi nếu không key nào tồn tại | `MSETNX` nếu phù hợp và các key trong phạm vi được hỗ trợ |
| Vừa ghi, vừa tăng counter, vừa thay đổi Set | `MULTI`/`EXEC` nếu yêu cầu các lệnh chạy không bị xen giữa |
| Phải kiểm tra điều kiện rồi mới ghi | `WATCH` + `MULTI`/`EXEC` hoặc Lua |
| Cần đọc và sửa nhiều hệ thống khác nhau | Không thể dùng chỉ `MSET`/`MULTI` để tạo distributed transaction |

Trong Redis Cluster, lệnh đa key phải đáp ứng những giới hạn hash slot liên quan. Không nên suy luận rằng `MSET` hoặc `MULTI` có thể cập nhật nguyên tử key nằm trên hai node độc lập.

## 13. Redis Cluster giới hạn phạm vi transaction nhiều key

Redis Cluster phân phối key vào các hash slot. Những thao tác trên nhiều key thường phải dùng những key cùng slot để có thể chạy trong phạm vi một node thích hợp.

Ví dụ key có cùng hash tag:

```text
checkout:{order-42}:status
checkout:{order-42}:reservation
checkout:{order-42}:counter
```

Đoạn trong `{...}` giúp các key cùng hash tag được định tuyến về cùng hash slot.

Ngược lại:

```text
checkout:order-42:status
checkout:order-42:reservation
```

không nên được mặc định nằm cùng slot chỉ vì nhìn có cùng tiền tố.

Những điều cần nhớ:

- Có thể cần thiết kế tên key sao cho các key cần cập nhật cùng transaction nằm chung slot.
- `WATCH`/`MULTI`/`EXEC`, Lua và các lệnh đa key có giới hạn theo phạm vi cluster.
- Một transaction trên một node **không biến thành transaction phân tán** qua tất cả shard.
- Dùng cùng hash tag chỉ giải quyết **điều kiện đồng vị trí của key**, không giải quyết lỗi runtime, retry, idempotency hoặc đồng bộ với hệ thống khác.
- Key dữ liệu chính và các secondary index do Spring Data Redis Repository quản lý không nên được mặc định nằm chung slot; phải xét mô hình key thực tế.

Nếu thao tác phải cập nhật nhiều tài khoản trên những shard khác nhau, cần thay đổi cách phân vùng dữ liệu, dùng điều phối nghiệp vụ hoặc chọn hệ thống có khả năng bảo đảm transaction đa đối tượng phù hợp.

## 14. Lệnh nguyên tử, `MULTI`/`EXEC` và độ bền dữ liệu

Tính nguyên tử khi thực thi và độ bền sau sự cố không phải cùng một thuộc tính.

Redis có thể được cấu hình với RDB snapshot, AOF và replication. Hành vi khi một node gặp sự cố phụ thuộc cấu hình ghi đĩa, trạng thái replica và quy trình failover.

Ví dụ:

```text
Client gửi EXEC
   |
Redis thực thi nhóm lệnh
   |
Client nhận phản hồi thành công
   |
Node gặp sự cố trước khi toàn bộ bản sao nhận thay đổi
```

Có thể xuất hiện sự khác nhau giữa những bản sao hoặc mất dữ liệu đã được xác nhận tùy cấu hình. Không suy luận rằng chỉ cần `EXEC` thành công là dữ liệu đã được ghi bền trên mọi máy.

Một số khái niệm nên tách bạch:

| Thuộc tính | Ý nghĩa |
|---|---|
| Tính nguyên tử của lệnh | Một lệnh không bị xen giữa bởi lệnh khác trên server xử lý |
| Tính không xen giữa của `EXEC` | Các lệnh đã xếp hàng chạy liên tiếp trong lúc transaction thực thi |
| `WATCH` optimistic concurrency | Phát hiện key đã đổi trước khi quyết định `EXEC` |
| Rollback | Khôi phục thay đổi khi một bước thất bại; Redis transaction không có rollback tổng quát |
| Durability | Khả năng giữ dữ liệu qua restart/crash tùy cấu hình |
| Replication | Thay đổi được truyền đến replica, thường có độ trễ |
| Idempotency | Thực hiện lại yêu cầu không tạo tác động nghiệp vụ trùng lặp |

Khi ứng dụng retry sau timeout, có thể gặp trường hợp **lệnh đã được Redis thực thi nhưng client không nhận được phản hồi**. Ví dụ retry `INCR` bừa bãi có thể tăng bộ đếm hai lần. Với giao dịch đặt hàng, cần thiết kế request ID hoặc cơ chế idempotency để biết một yêu cầu đã được xử lý hay chưa.

## 15. Redis Repository `save()` không tự tương đương `MULTI`/`EXEC`

Spring Data Redis Repository đưa các đối tượng Java vào Redis thông qua cơ chế ánh xạ; dữ liệu một entity có thể được lưu trong Redis Hash cùng những key phụ trợ như tập ID và secondary index.

Ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("users")
public class User {
    @Id
    private String id;

    @Indexed
    private String email;

    // constructors, getters, setters...
}
```

Lệnh:

```java
userRepository.save(user);
```

không nhất thiết chỉ là một lệnh `HSET`. Repository có thể cập nhật dữ liệu chính và những cấu trúc dùng cho index hoặc quản lý keyspace.

Vì vậy:

- Một câu gọi `save` trong Java **không có nghĩa một lệnh Redis**.
- Không tự cho rằng các key dữ liệu/index được cập nhật nguyên tử chỉ vì chúng cùng thuộc một entity.
- Không mặc định `@Transactional` biến toàn bộ thao tác repository thành một transaction Redis có rollback kiểu JPA.
- Không sửa thô field Redis bằng `HSET` rồi giả định repository sẽ tự cập nhật secondary index.
- Nếu cần bất biến mạnh trên nhiều key, thiết kế dữ liệu và thao tác cập nhật phải xuất phát từ phạm vi bảo đảm của Redis chứ không chỉ từ API repository.

Nếu một thuộc tính cần tăng đồng thời rất thường xuyên, có thể tách thành một counter Redis do `StringRedisTemplate` quản lý và dùng `INCRBY`, đồng thời xác định cách đồng bộ với entity gốc nếu cả hai cùng tồn tại.

## 16. Những tình huống thực tế và cách chọn cơ chế

### 16.1. Đếm lượt xem

Yêu cầu: mỗi request thành công làm số lượt xem tăng thêm `1`.

**Phù hợp:** `INCR views:article:<id>` hoặc `opsForValue().increment(...)`.

Không cần `MULTI` chỉ để tăng một giá trị, và tránh `GET` → `SET` phía Java.

### 16.2. Cấp một mã dùng một lần

Yêu cầu: nếu key chưa tồn tại, ghi mã xác thực cùng TTL.

**Phù hợp:** `SET key value NX EX 120` hoặc API Spring Data Redis có lựa chọn tương ứng.

Một lệnh có thể kết hợp điều kiện “chưa tồn tại” với việc đặt TTL; thao tác `EXISTS` rồi `SET` tạo race condition.

### 16.3. Ghi hai field trạng thái rồi phát hiện đọc ở giữa

Yêu cầu: thay đổi hai key cùng lúc sao cho client khác không quan sát được trạng thái chỉ một trong hai đã cập nhật trong khoảng Redis thực thi nhóm.

**Có thể phù hợp:** `MULTI`/`EXEC` khi cả hai key nằm trong phạm vi server/cluster được hỗ trợ và các thao tác được phép.

Vẫn phải xét lỗi runtime khi một lệnh trong nhóm thất bại; nếu bất biến không chấp nhận cập nhật dở dang, cần thiết kế cách thực hiện chắc chắn hơn.

### 16.4. Trừ tồn kho khi đủ hàng

Yêu cầu: stock không âm và hai request không thể cùng mua đơn vị cuối cùng.

**Phù hợp:** Lua/Redis Function có kiểm tra rồi trừ, hoặc `WATCH` + `MULTI`/`EXEC` với retry.

**Chưa đủ:** `GET stock`, `if stock > 0`, `DECR stock` dù `DECR` tự nó là một lệnh nguyên tử.

### 16.5. Chuyển tiền giữa hai tài khoản

Yêu cầu: tổng số tiền và điều kiện số dư phải được bảo toàn, không được ghi nợ mà thiếu ghi có.

Một `MULTI` chỉ bảo đảm nhóm lệnh không xen giữa, nhưng không rollback lệnh đã chạy nếu bước sau lỗi runtime. Với tài khoản nằm trên nhiều shard hoặc nhiều hệ thống, bài toán còn phức tạp hơn. Cần thiết kế nguồn dữ liệu và transaction thật sự đáp ứng invariant tiền tệ; nếu dùng Redis, phải có cơ chế kiểm soát điều kiện, lỗi, durability và phục hồi rất chặt chẽ.

Không nên lấy ví dụ này để suy luận rằng bất kỳ hai lệnh `DECRBY` và `INCRBY` nào trong `MULTI` cũng tạo thành một giao dịch ngân hàng an toàn.

### 16.6. Ghi đơn hàng trong PostgreSQL rồi xóa cache Redis

Yêu cầu: DB thay đổi là nguồn sự thật; cache cần phản ánh dữ liệu mới.

**Phù hợp:** commit transaction DB rồi vô hiệu cache; nếu cần bảo đảm việc vô hiệu được thực hiện, dùng chiến lược retry/outbox hoặc TTL như cơ chế phục hồi.

**Chưa đủ:** `@Transactional` trên service rồi giả định Redis tự rollback/commit đồng bộ với RDBMS.

## 17. Bảng quyết định: dùng lệnh đơn hay `MULTI`/`EXEC`?

| Câu hỏi thiết kế | Lựa chọn nên xem trước | Vì sao |
|---|---|---|
| Một lệnh Redis đã thực hiện trọn phép toán? | **Lệnh đơn** | Ít round trip và tránh tự tạo khoảng trống concurrency |
| Nhiều lệnh cần chạy liên tục, không xen giữa? | **`MULTI`/`EXEC`** | Redis thực thi nhóm lệnh theo thứ tự tại `EXEC` |
| Phải đọc trước, quyết định ở client rồi ghi? | **`WATCH` + `MULTI`/`EXEC`** | Phát hiện thay đổi của key đã theo dõi trước `EXEC` |
| Muốn kiểm tra và ghi như một phép toán ở server? | **Lua/Redis Function** | Có thể gom điều kiện và cập nhật trong phạm vi thực thi nguyên tử |
| Nhiều lệnh chỉ cần gửi nhanh, không yêu cầu transaction? | **Pipeline** | Giảm round trip, không bảo đảm không xen giữa |
| Cần rollback toàn bộ sau lỗi runtime? | **Thiết kế lại invariant hoặc chọn storage/transaction phù hợp** | Redis `MULTI`/`EXEC` không cung cấp rollback kiểu SQL |
| Nhiều Redis shard, DB hoặc hệ thống khác nhau cùng tham gia? | **Kiến trúc phối hợp/nguồn dữ liệu giao dịch phù hợp** | Một `EXEC` không trải qua các resource độc lập |
| Cần cập nhật nhiều entity và secondary index bằng repository? | **Xem kỹ giới hạn mapping và phạm vi thao tác** | `save()` không mặc định tương đương một transaction nguyên tử |

## 18. Các hiểu lầm thường gặp

**“Redis single-threaded nên cả đoạn Java dùng Redis là nguyên tử.”** Sai. Mỗi lệnh Redis có thể là nguyên tử, nhưng giữa hai lần gọi từ Java, các client khác vẫn có thể gửi lệnh.

**“Đã dùng `MULTI` thì các lệnh bên trong được chạy ngay.”** Sai. Lệnh được xếp hàng; `EXEC` mới bắt đầu thực thi nhóm.

**“Đặt `GET` bên trong `MULTI` là đủ để `if` phía Java không race.”** Sai. Giá trị `GET` trong queue chỉ có sau `EXEC`; nếu cần điều kiện, phải dùng cơ chế thích hợp.

**“`MULTI`/`EXEC` giống SQL transaction nên gặp lỗi sẽ rollback.”** Sai. Lỗi runtime của một lệnh không làm Redis tự hoàn tác những lệnh khác đã thành công.

**“Có thể gọi `DISCARD` để đảo ngược `EXEC`.”** Sai. `DISCARD` hủy hàng đợi **trước** khi transaction được thực thi.

**“`WATCH` khóa key để không ai sửa được.”** Sai. `WATCH` theo dõi thay đổi và làm transaction abort nếu dữ liệu bị sửa; đó là optimistic concurrency.

**“Dùng `executePipelined` tương đương transaction.”** Sai. Pipelining tối ưu truyền lệnh qua mạng; không tự tạo nhóm thực thi không bị xen giữa.

**“`@Transactional` tự bật `MULTI`/`EXEC` cho mọi `RedisTemplate`.”** Sai. Cần cấu hình transaction support, xác định transaction manager và hiểu behavior của tài nguyên Redis.

**“Lệnh/transaction trả OK thì dữ liệu chắc chắn được lưu trên mọi node.”** Sai. Kết quả thực thi khác độ bền và replication.

**“Một lệnh Lua là phép rollback tự động.”** Sai. Lua có khả năng chạy nguyên tử về mặt không xen giữa, nhưng lỗi sau các bước ghi không tạo rollback tổng quát.

## 19. Thực hành: tái hiện sự khác biệt trong Redis CLI

Có thể dùng một Redis thử nghiệm và hai terminal CLI độc lập để quan sát.

### Bài thực hành A — Hai lệnh riêng lẻ có race

Terminal A:

```redis
SET lab:count 10
GET lab:count
```

Trước khi A `SET`, ở terminal B:

```redis
GET lab:count
```

Nếu cả hai đều đọc `10`, rồi lần lượt chạy:

```redis
SET lab:count 11
```

kết quả cuối chỉ là `11`. Điều này minh họa mất cập nhật.

Thử lại bằng hai lần `INCR lab:count` (sau khi reset về `10`) để thấy kết quả `12`.

### Bài thực hành B — Queue và kết quả sau `EXEC`

```redis
MULTI
SET lab:a 1
SET lab:b 2
EXEC

GET lab:a
GET lab:b
```

Hai lệnh `SET` nhận `QUEUED` trước `EXEC`, sau `EXEC` hai key có giá trị mới.

### Bài thực hành C — Lỗi runtime không rollback

```redis
SET lab:number "text"

MULTI
SET lab:before "ok"
INCR lab:number
SET lab:after "ok"
EXEC

GET lab:before
GET lab:number
GET lab:after
```

`INCR` thất bại nhưng hai lần `SET` khác vẫn có thể thành công. Điều này cho thấy vì sao không được xem `EXEC` như cơ chế rollback SQL.

### Bài thực hành D — `WATCH` phát hiện xung đột

Terminal A:

```redis
SET lab:watched 1
WATCH lab:watched
GET lab:watched
```

Terminal B:

```redis
SET lab:watched 2
```

Trở lại terminal A:

```redis
MULTI
SET lab:watched 3
EXEC
```

Transaction ở terminal A bị hủy do key đã thay đổi sau khi `WATCH`. Đọc lại:

```redis
GET lab:watched
```

giá trị là `2`, không phải `3`, nếu không có client nào khác cập nhật tiếp.

Các bài thực hành trên tập trung quan sát hành vi Redis. Khi chuyển sang Spring Data Redis, cần bảo đảm các lệnh của cùng transaction dùng cùng connection; hai `redisTemplate.execute(...)` độc lập không đương nhiên giữ nguyên trạng thái `WATCH`/`MULTI` giữa hai connection.

## 20. Kết luận

**Tính nguyên tử của lệnh** giúp một phép toán Redis đơn lẻ, như `INCR` hoặc `SET ... NX EX`, được thực thi mà không bị client khác chen thao tác vào giữa. **`MULTI`/`EXEC`** cho phép nhiều lệnh được xếp hàng rồi thực thi liên tiếp, không xen giữa trong giai đoạn `EXEC`.

Tuy vậy, `MULTI`/`EXEC` không tự rollback các lệnh đã thành công khi gặp lỗi runtime, không tự giải quyết phép đọc–sửa–ghi dựa trên dữ liệu đọc trước đó và không tạo transaction phân tán với database hoặc Redis shard khác.

Trong Spring Data Redis, lựa chọn tốt bắt đầu từ câu hỏi **“Phép toán nghiệp vụ nào cần nguyên tử?”**:

- Nếu một lệnh Redis đã diễn tả đủ phép toán, dùng **một lệnh**.
- Nếu cần nhiều lệnh chạy liền nhau, cân nhắc **`MULTI`/`EXEC`**.
- Nếu cần kiểm tra điều kiện và tránh xung đột, dùng **`WATCH` với retry** hoặc **Lua/Redis Function**.
- Nếu cần rollback qua nhiều nguồn dữ liệu, phải thiết kế **transaction và cơ chế phục hồi ở cấp hệ thống** phù hợp, thay vì suy diễn từ `@Transactional` hoặc `RedisRepository.save()`.

Phân biệt đúng các phạm vi này giúp tránh mất cập nhật, trạng thái nửa vời và những lỗi chỉ xuất hiện khi hệ thống có tải đồng thời hoặc xảy ra sự cố.
