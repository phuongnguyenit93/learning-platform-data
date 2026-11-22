# Vì sao giao dịch Redis không rollback dữ liệu như cơ sở dữ liệu SQL

Khi thấy `MULTI`, `EXEC`, `DISCARD` hoặc `@Transactional` trong một ứng dụng dùng Spring Data Redis, lập trình viên rất dễ liên tưởng tới transaction của PostgreSQL hoặc MySQL: nhiều lệnh được nhóm lại, và nếu một lệnh lỗi thì tất cả thay đổi trước đó được tự động khôi phục. **Redis không cung cấp cơ chế rollback như vậy cho những lệnh đã thực thi trong `EXEC`.**

Redis transaction giải quyết một vấn đề hẹp nhưng quan trọng: **gom và thực thi tuần tự một nhóm lệnh mà không bị lệnh của client khác chen vào giữa**. Cơ chế này giúp tránh quan sát trạng thái trung gian từ client khác, nhưng không tạo bản sao dữ liệu cũ hay nhật ký undo để phục hồi các thay đổi nếu một lệnh trong nhóm thất bại.

Hệ quả thực tế:

- **`DISCARD`** hủy các lệnh **chưa thực thi**, còn nằm trong hàng đợi sau `MULTI`.
- Nếu `EXEC` đã bắt đầu thực thi, **một lỗi khi chạy lệnh không tự hoàn tác các lệnh đã thành công**; Redis tiếp tục xử lý những lệnh còn lại.
- **`WATCH`** có thể khiến `EXEC` từ chối chạy **trước khi** nhóm lệnh được thực thi nếu key được theo dõi đã thay đổi. Đây là kiểm soát cạnh tranh lạc quan, **không phải rollback sau khi ghi**.
- Trong Spring Data Redis, `RedisTemplate` và `@Transactional` không biến Redis thành hệ quản trị cơ sở dữ liệu có undo/redo transaction kiểu SQL.

Bài này phân biệt **atomic execution**, **rollback**, **optimistic locking**, **durability** và **Spring transaction management**, sau đó minh họa bằng Redis CLI và mã Java.

## 1. So sánh giao dịch Redis với giao dịch SQL

Hãy xét chuyển 30 đơn vị giữa hai số dư:

```text
Ban đầu:
  account:A = 100
  account:B = 50

Mong muốn:
  account:A = 70
  account:B = 80
```

Một giao dịch SQL phổ biến:

```sql
BEGIN;
UPDATE accounts SET balance = balance - 30 WHERE id = 'A';
UPDATE accounts SET balance = balance + 30 WHERE id = 'B';
COMMIT;
```

Nếu trước `COMMIT` xảy ra lỗi khiến transaction phải hủy và ứng dụng/database thực hiện `ROLLBACK`, các thay đổi chưa commit sẽ được hoàn tác. Đó là đặc tính **atomicity theo nghĩa all-or-nothing** của giao dịch SQL trong điều kiện sử dụng transaction đúng cách. Mức cô lập, hành vi sau từng loại lỗi và chi tiết triển khai còn tùy cơ sở dữ liệu và cấu hình.

Trong Redis:

```redis
SET account:A 100
SET account:B 50

MULTI
DECRBY account:A 30
INCRBY account:B 30
EXEC
```

Nếu cả hai lệnh chạy thành công, kết quả cũng là `70` và `80`. Tuy nhiên, nếu một lệnh trong `EXEC` không thể thực hiện vì dữ liệu không hợp lệ, những lệnh khác vẫn có thể thành công. Redis **không tự khôi phục số dư ban đầu**.

| Khía cạnh | Transaction SQL điển hình | Redis `MULTI`/`EXEC` |
|---|---|---|
| Mục tiêu | Quản lý các thay đổi như một đơn vị commit/rollback | Xếp hàng và thực thi nhóm lệnh liên tiếp, không bị client khác chen vào |
| Trạng thái trước khi commit/thực thi | Các thay đổi trong transaction chịu cơ chế isolation của DB | Lệnh được xếp hàng sau `MULTI`, chưa tác động dữ liệu |
| Khi gặp lỗi trong lúc thực thi | Transaction có thể bị rollback theo cơ chế DB và cách ứng dụng xử lý | Lệnh lỗi được báo lỗi; lệnh khác vẫn được thực thi |
| Hủy trước khi chạy/commit | `ROLLBACK` hủy transaction | `DISCARD` bỏ hàng đợi trước `EXEC` |
| Phát hiện cập nhật đồng thời | Tùy isolation, lock, version, constraint | `WATCH` theo dõi key, có thể hủy `EXEC` trước khi chạy |
| Rollback những lệnh Redis đã chạy | Không áp dụng | **Không có** trong `MULTI`/`EXEC` |
| Bền vững sau sự cố | Tùy engine, log và cấu hình | Tùy RDB/AOF, replication và cấu hình Redis; khác khái niệm rollback |

**Đừng đánh đồng “Redis transaction là atomic” với “Redis có rollback như SQL”.** Trong tài liệu Redis, atomicity của `MULTI`/`EXEC` nhấn mạnh tính thực thi nhóm lệnh mà không có lệnh client khác xen vào. Tính chất đó không đồng nghĩa tất cả lệnh đều sẽ thành công hoặc toàn bộ thay đổi được undo nếu có lỗi khi chạy.

## 2. Redis xử lý MULTI, lệnh được xếp hàng và EXEC như thế nào?

Một phiên giao dịch Redis thường gồm:

1. Client gửi `MULTI` để bắt đầu transaction.
2. Client gửi các lệnh cần nhóm; Redis đưa chúng vào hàng đợi và trả `QUEUED` nếu lệnh được chấp nhận.
3. Client gửi `EXEC` để chạy các lệnh đã xếp hàng theo thứ tự.
4. Redis trả một danh sách kết quả tương ứng với các lệnh, bao gồm cả kết quả lỗi của lệnh không chạy thành công.

```text
Client                           Redis
  |                                |
  | MULTI                          |
  |------------------------------->|
  |<-------------------------------| OK
  | SET order:233:state APPROVED   |
  |------------------------------->|  Đưa vào queue
  |<-------------------------------| QUEUED
  | INCR order:233:updates         |
  |------------------------------->|  Đưa vào queue
  |<-------------------------------| QUEUED
  | EXEC                           |
  |------------------------------->|
  |                                |  Chạy SET
  |                                |  Chạy INCR
  |<-------------------------------| [OK, 1]
  |                                |
```

Trong giai đoạn `MULTI` đến trước `EXEC`, những lệnh được xếp hàng **chưa sửa Redis**. Khi Redis xử lý `EXEC`, các lệnh được chạy liên tiếp và không có lệnh của client khác xen giữa các lệnh thuộc nhóm đó. Sau khi `EXEC` kết thúc, trạng thái mới được quan sát bởi client khác.

Ví dụ thành công:

```redis
SET cart:233:total 0

MULTI
SET cart:233:state "PAID"
INCRBY cart:233:total 2
EXEC
```

Kết quả minh họa:

```text
OK
QUEUED
QUEUED
1) OK
2) (integer) 2
```

Sau đó:

```redis
GET cart:233:state
# "PAID"

GET cart:233:total
# "2"
```

Lưu ý: gọi một lệnh đọc như `GET` sau `MULTI` trên **cùng kết nối** cũng thường nhận `QUEUED`, không trả giá trị đọc ngay tại thời điểm gọi. Kết quả của nó chỉ xuất hiện trong phản hồi `EXEC`. Đây là điểm cần nhớ khi dùng API Spring Data Redis bên dưới.

## 3. Lỗi khi chạy trong EXEC: các lệnh thành công không bị hoàn tác

Đây là tình huống giải thích rõ nhất vì sao Redis không rollback giống SQL.

Trước tiên tạo dữ liệu khiến một lệnh sẽ bị lỗi:

```redis
SET cart:233:total "not-a-number"
DEL cart:233:state cart:233:audit
```

Bắt đầu transaction:

```redis
MULTI
SET cart:233:state "CONFIRMED"
INCR cart:233:total
SET cart:233:audit "written"
EXEC
```

Các lệnh đều có cú pháp hợp lệ nên khi xếp hàng, Redis phản hồi:

```text
OK
QUEUED
QUEUED
QUEUED
```

Nhưng `INCR cart:233:total` không thể tăng giá trị `"not-a-number"` thành số nguyên. Kết quả `EXEC` sẽ có dạng:

```text
1) OK
2) (error) ERR value is not an integer or out of range
3) OK
```

Kiểm tra lại:

```redis
GET cart:233:state
# "CONFIRMED"

GET cart:233:total
# "not-a-number"

GET cart:233:audit
# "written"
```

Kết quả cho thấy:

| Lệnh trong nhóm | Kết quả | Trạng thái sau `EXEC` |
|---|---|---|
| `SET cart:233:state "CONFIRMED"` | Thành công | `state = "CONFIRMED"` |
| `INCR cart:233:total` | Lỗi dữ liệu không phải số nguyên | `total` giữ nguyên `"not-a-number"` |
| `SET cart:233:audit "written"` | Thành công | `audit = "written"` |

Nếu ứng dụng hiểu `state = "CONFIRMED"` nghĩa là “mọi bước thanh toán đã thành công”, dữ liệu bây giờ **không đáp ứng quy tắc nghiệp vụ**. Redis không biết quy tắc “chỉ xác nhận khi cập nhật tổng thành công”, và bản thân `MULTI`/`EXEC` không tự thực hiện rollback để phục hồi trạng thái trước đó.

Không có lệnh `ROLLBACK` tương đương SQL để gọi sau tình huống này. Gửi `DISCARD` **sau `EXEC`** cũng không thể khôi phục giá trị đã ghi; khi đó transaction đã kết thúc.

### Tại sao Redis có thiết kế này?

Redis ưu tiên mô hình xử lý lệnh đơn giản, nhanh và có thể dự đoán. Với transaction của Redis:

- Các lỗi cú pháp hoặc lệnh không được nhận diện có thể được phát hiện khi **xếp hàng**.
- Các lỗi chỉ biết khi truy cập dữ liệu thực tế, chẳng hạn `INCR` trên chuỗi không phải số hoặc thao tác sai kiểu, có thể chỉ xuất hiện lúc **thực thi**.
- Redis không tạo hệ thống undo log để phục hồi tất cả dữ liệu trước `EXEC`. Khi một lệnh chạy lỗi, những lệnh khác vẫn tiếp tục theo thứ tự.

Vì vậy, người viết ứng dụng phải tự bảo đảm **tiền điều kiện nghiệp vụ**, xử lý kết quả từng lệnh và lựa chọn cơ chế điều phối phù hợp nếu cần bảo đảm mạnh hơn.

## 4. Phân biệt lỗi khi xếp hàng với lỗi lúc thực thi

Hai kiểu lỗi này có hành vi rất khác nhau.

### 4.1. Lỗi khi xếp hàng: EXECABORT trước khi có lệnh nào chạy

Ví dụ lệnh `INCR` bị thiếu tham số:

```redis
DEL cart:233:state

MULTI
SET cart:233:state "CONFIRMED"
INCR
EXEC
```

Phản hồi minh họa:

```text
OK
QUEUED
(error) ERR wrong number of arguments for 'incr' command
(error) EXECABORT Transaction discarded because of previous errors.
```

Khi Redis phát hiện lỗi khi xếp hàng, transaction bị đánh dấu không hợp lệ; `EXEC` hủy nhóm thay vì chạy một phần lệnh đã xếp hàng. Vì vậy `cart:233:state` không được tạo bởi `SET` ở trên.

Đây là **từ chối thực thi cả nhóm trước khi chạy**, không phải rollback dữ liệu đã ghi. Nó không chứng minh rằng Redis có cơ chế hoàn tác khi lệnh thứ hai gặp lỗi **trong `EXEC`**.

### 4.2. Lỗi lúc chạy: những lệnh còn lại vẫn được thực thi

Với `INCR` trên `"not-a-number"`, cú pháp hợp lệ nên được xếp hàng bình thường. Redis chỉ biết rằng dữ liệu không phải số khi thực thi, vì vậy `EXEC` trả lỗi riêng cho lệnh đó, còn các lệnh khác vẫn chạy.

### 4.3. Bảng quyết định nhanh

| Tình huống | Lệnh đã thực thi? | Hành vi |
|---|---|---|
| Gọi `MULTI` rồi `DISCARD` | Chưa | Hủy hàng đợi, không có thay đổi của các lệnh đã xếp |
| Lệnh sai cú pháp/sai số tham số trong giai đoạn xếp hàng | Chưa | `EXECABORT` khi gọi `EXEC`; nhóm bị hủy |
| Lệnh hợp lệ nhưng lỗi kiểu dữ liệu trong `EXEC` | Có, các lệnh khác vẫn chạy | Không rollback; đọc kết quả từng lệnh |
| `WATCH` phát hiện key thay đổi trước `EXEC` | Chưa chạy nhóm | `EXEC` bị hủy do xung đột; có thể đọc lại và thử lại |
| Mất kết nối khi client chờ phản hồi `EXEC` | Không chắc từ phía client | Không được suy đoán transaction chưa chạy; phải thiết kế idempotency/reconciliation |

Đặc tính không rollback của Redis cần được nhìn cùng **thời điểm phát hiện lỗi**. Nói “hễ có lỗi Redis transaction vẫn chạy một phần” cũng quá đơn giản: lỗi khi xếp hàng có thể khiến toàn bộ `EXEC` bị từ chối; lỗi lúc thực thi mới là ví dụ điển hình cho việc đã có thay đổi nhưng không được hoàn tác.

## 5. DISCARD chỉ hủy những lệnh còn trong hàng đợi

`DISCARD` cho phép dừng một transaction khi vẫn còn ở giai đoạn xếp hàng:

```redis
SET demo:233:status "NEW"

MULTI
SET demo:233:status "APPROVED"
SET demo:233:notification "READY"
DISCARD

GET demo:233:status
# "NEW"

EXISTS demo:233:notification
# (integer) 0
```

Ở ví dụ này không cần “đảo ngược” một `SET` nào, vì cả hai `SET` chỉ nằm trong queue và chưa được thực thi. `DISCARD` bỏ queue và kết thúc transaction. Nếu có các key đang được `WATCH` trên kết nối đó, `DISCARD` cũng dừng việc theo dõi.

Không có chuyện “`DISCARD` sẽ phục hồi dữ liệu Redis về trước khi transaction bắt đầu” trong trường hợp đã thực thi một phần: **sau `EXEC`, transaction cũ không còn trạng thái queue để DISCARD**.

Trong thiết kế ứng dụng, hủy trước khi chạy là biện pháp phòng ngừa, còn sửa hậu quả sau khi lệnh đã chạy là một **nghiệp vụ bù trừ (compensation)**, có thể yêu cầu lệnh mới và cũng có thể gặp lỗi mới.

## 6. WATCH chống xung đột ghi, không tạo rollback

`WATCH` cung cấp optimistic concurrency control: theo dõi một hoặc nhiều key trước khi bắt đầu `MULTI`. Nếu một key được theo dõi bị thay đổi bởi client khác trước `EXEC`, Redis hủy việc thực thi nhóm lệnh.

Giả sử có 5 sản phẩm trong kho và mỗi yêu cầu muốn mua 2 sản phẩm.

### 6.1. Client A

```redis
SET inventory:item-233 5

WATCH inventory:item-233
GET inventory:item-233
# "5"

MULTI
DECRBY inventory:item-233 2
EXEC
```

Nếu không có ai sửa `inventory:item-233` trong thời gian từ `WATCH` đến `EXEC`, Redis thực thi nhóm lệnh và số lượng giảm thành 3.

### 6.2. Nếu client B sửa kho trước EXEC

Thứ tự sự kiện:

```text
Thời điểm       Client A                     Client B
--------------------------------------------------------------
t1              WATCH inventory:item-233
t2              GET -> 5
t3                                           SET inventory:item-233 1
t4              MULTI
t5              DECRBY inventory:item-233 2
t6              EXEC -> transaction bị hủy
```

Redis CLI trả kết quả rỗng/`(nil)` cho `EXEC` bị hủy bởi `WATCH`. Số lượng tồn kho không bị giảm bởi transaction của A. A có thể đọc lại tồn kho, kiểm tra điều kiện và thử lại với chính sách retry có giới hạn.

**Đây là từ chối thực thi trước khi ghi.** Không có thay đổi nào của nhóm A cần rollback.

### 6.3. WATCH không kiểm tra điều kiện nghiệp vụ thay bạn

Nếu `WATCH` thành công nhưng trước đó client lập trình sai, chẳng hạn không kiểm tra kho còn ít nhất 2 sản phẩm, Redis vẫn có thể thực thi `DECRBY` và cho kết quả âm. `WATCH` chỉ phát hiện xung đột thay đổi key, không biết điều kiện “không bán vượt tồn kho”.

Một luồng xử lý có kiểm tra điều kiện phải thực hiện theo thứ tự:

1. Trên cùng kết nối, `WATCH` key.
2. Đọc giá trị hiện tại.
3. Nếu điều kiện nghiệp vụ không thỏa, `UNWATCH` hoặc kết thúc phiên theo dõi; không gửi `MULTI` để ghi.
4. Nếu điều kiện thỏa, `MULTI` và xếp các lệnh.
5. Gọi `EXEC`; nếu bị hủy do xung đột, đọc lại và retry có giới hạn.

Vẫn cần xét **lỗi lúc thực thi** của từng lệnh. `WATCH` không bổ sung rollback khi một lệnh trong `EXEC` bị lỗi.

### Một vài chi tiết của WATCH

- `WATCH` phải chạy trước `MULTI` và gắn với **cùng kết nối Redis** dùng để `EXEC`.
- `EXEC` và `DISCARD` kết thúc việc watch của transaction; có thể gọi `UNWATCH` để hủy theo dõi trước đó.
- Một key được theo dõi bị thay đổi, xóa hoặc hết hạn trong thời gian theo dõi cũng là tình huống cần quan tâm. Việc key tự hết hạn được Redis hiện đại coi là thay đổi có thể làm `EXEC` bị hủy.
- Kiểm soát cạnh tranh bằng `WATCH` hữu ích khi quyết định ghi phụ thuộc vào dữ liệu vừa đọc. Nếu chỉ cần một thao tác Redis đơn lẻ đã có tính nguyên tử, thường không cần tạo một transaction phức tạp.

## 7. Spring Data Redis thực hiện transaction như thế nào?

Spring Data Redis cung cấp các API giao dịch ở cấp Redis Operations:

| API | Vai trò |
|---|---|
| `RedisOperations.multi()` | Gửi `MULTI` |
| `RedisOperations.exec()` | Gửi `EXEC` và lấy danh sách kết quả |
| `RedisOperations.discard()` | Hủy hàng đợi bằng `DISCARD` trước khi thực thi |
| `RedisOperations.watch(key)` | Theo dõi key để phát hiện cập nhật đồng thời |
| `RedisOperations.unwatch()` | Ngừng theo dõi các key đang watch |
| `SessionCallback` | Cho nhiều thao tác dùng **cùng một kết nối Redis** |
| `RedisTemplate.setEnableTransactionSupport(true)` | Cho phép RedisTemplate tham gia cơ chế đồng bộ transaction của Spring khi có transaction manager |

Một điểm rất quan trọng: **`RedisTemplate` không tự bật transaction support mặc định.** Nếu dùng `@Transactional` trong Spring mà không cấu hình template đúng, không thể mặc định rằng những thao tác Redis đã được gửi trong một nhóm `MULTI`/`EXEC`.

### 7.1. Dùng SessionCallback để giữ cùng kết nối

`MULTI`, các lệnh được queue và `EXEC` phải đi qua cùng một kết nối Redis. Các lời gọi `RedisTemplate` độc lập không phải lúc nào cũng được bảo đảm gắn vào một connection trong toàn bộ chuỗi thao tác. `SessionCallback` là cách thường dùng để bao bọc nhóm lệnh.

Ví dụ với `StringRedisTemplate`:

```java
import java.util.List;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisTransactionDemo {

    private final StringRedisTemplate redisTemplate;

    public RedisTransactionDemo(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public List<Object> executeCommands() {
        return redisTemplate.execute(new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public List<Object> execute(RedisOperations operations) {
                operations.multi();
                try {
                    operations.opsForValue().set(
                            "demo:233:status", "APPROVED");
                    operations.opsForValue().increment(
                            "demo:233:counter");
                } catch (RuntimeException ex) {
                    // Chỉ hủy được các lệnh chưa chạy bằng EXEC.
                    operations.discard();
                    throw ex;
                }
                return operations.exec();
            }
        });
    }
}
```

Ví dụ sử dụng kiểu `RedisOperations` raw trong callback để minh họa API như các ví dụ transaction phổ biến; trong dự án có quy định tránh raw type, có thể tạo một adapter hoặc dùng `RedisCallback` và các thao tác trên `RedisConnection` để giữ kiểu chặt chẽ.

Nếu `demo:233:counter` đã chứa một chuỗi không phải số, `increment` có thể gây lỗi **khi `EXEC` xử lý** lệnh đã xếp. Khi đó `status` có thể đã được ghi. `try/catch` quanh giai đoạn xếp lệnh **không thể** hoàn tác việc Redis đã thực thi trong `EXEC`; nó chỉ cho phép hủy queue khi có lỗi sớm trước `EXEC`.

Sau `multi()`, các phương thức trả kết quả ngay như `increment(...)` có thể trả `null` do đang nằm trong pipeline/transaction và kết quả thực tế xuất hiện ở danh sách của `exec()`. Không nên diễn giải `null` như “không tăng được”. Loại và cách biểu diễn phần tử trả về có thể phụ thuộc serializer và driver; cần đọc kết quả thực thi thay vì dựa vào giá trị trung gian.

Nếu ứng dụng cần phân tích lỗi từng lệnh, xem xét trực tiếp từng phần tử của kết quả `EXEC` và hành vi chuyển lỗi thành exception của phiên bản driver. Không nên chỉ thấy lời gọi `exec()` hoàn tất là tuyên bố toàn bộ nghiệp vụ thành công.

### 7.2. Một cách khác: RedisCallback với RedisConnection

Với thao tác ở mức byte, `RedisCallback` cho phép truy cập trực tiếp Redis connection trong một callback:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public class LowLevelRedisTransaction {

    private final StringRedisTemplate redisTemplate;

    public LowLevelRedisTransaction(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public List<Object> run() {
        return redisTemplate.execute((RedisCallback<List<Object>>) connection -> {
            byte[] statusKey =
                    "demo:233:status".getBytes(StandardCharsets.UTF_8);
            byte[] counterKey =
                    "demo:233:counter".getBytes(StandardCharsets.UTF_8);
            byte[] value =
                    "APPROVED".getBytes(StandardCharsets.UTF_8);

            connection.multi();
            connection.stringCommands().set(statusKey, value);
            connection.stringCommands().incr(counterKey);
            return connection.exec();
        });
    }
}
```

Cách này cho thấy việc dùng cùng Redis connection rõ ràng hơn, nhưng nhà phát triển phải tự mã hóa key/value. Nó phù hợp khi cần kiểm soát lệnh thấp, còn code nghiệp vụ thường dễ bảo trì hơn khi đi qua `StringRedisTemplate` hoặc một service có interface rõ ràng.

**Lưu ý với Redis Cluster:** lệnh trong một transaction có thể phải thỏa các ràng buộc hash slot; không thể tùy ý nhóm các key thuộc slot khác nhau thành một giao dịch trên mọi triển khai cluster.

## 8. @Transactional trong Spring có tạo rollback cho Redis không?

`@Transactional` là cơ chế quản lý transaction của Spring. Annotation này không tự thay đổi khả năng của Redis server. Để RedisTemplate đồng bộ với một transaction Spring đang hoạt động, cần bật transaction support trên template và có một `PlatformTransactionManager` phù hợp với phạm vi công việc đang quản lý.

Ví dụ cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisTemplateConfig {

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        StringRedisTemplate template =
                new StringRedisTemplate(connectionFactory);
        template.setEnableTransactionSupport(true);
        return template;
    }
}
```

Khi có một Spring transaction đang hoạt động, các thao tác ghi thông qua template đã bật transaction support có thể được queue vào Redis transaction và được xử lý theo vòng đời transaction của Spring:

```text
Spring transaction bắt đầu
        |
        v
RedisTemplate dùng connection gắn với transaction
        |
        v
MULTI + xếp các thao tác ghi Redis
        |
        +-- Spring rollback trước khi Redis EXEC
        |         |
        |         v
        |      DISCARD queue
        |
        +-- Spring commit
                  |
                  v
                 EXEC
                  |
                  v
        Redis thực thi các lệnh theo thứ tự
        (không có undo nếu một lệnh lỗi lúc chạy)
```

Đó là **tích hợp điều khiển thời điểm queue/EXEC/DISCARD**, không phải bổ sung undo log hay phục hồi dữ liệu sau một lệnh Redis đã thực thi.

### 8.1. Một ví dụ dễ gây hiểu lầm

Giả sử có service:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutWorkflowService {

    private final StringRedisTemplate redisTemplate;

    public CheckoutWorkflowService(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    @Transactional
    public void confirm() {
        redisTemplate.opsForValue().set(
                "demo:233:state", "CONFIRMED");

        redisTemplate.opsForValue().increment(
                "demo:233:total");
    }
}
```

Để annotation này có hiệu lực, ứng dụng **phải có transaction manager** và cấu hình RedisTemplate tham gia transaction như trên. Nếu dùng JDBC transaction manager, transaction của JDBC vẫn có trách nhiệm riêng với database quan hệ; Redis được phối hợp qua Spring transaction synchronization, không tự trở thành tài nguyên XA có two-phase commit.

Ngay cả khi đã cấu hình, nếu key `demo:233:total` lưu chuỗi không phải số thì:

1. Các lời gọi Redis trong method có thể mới chỉ **xếp hàng**, không biết lỗi kiểu dữ liệu thực tế.
2. Khi Spring transaction đến giai đoạn commit, `EXEC` thực thi các lệnh.
3. `SET demo:233:state CONFIRMED` có thể thành công rồi `INCR` lỗi.
4. Redis không tự undo lệnh `SET` vừa chạy.

Không nên suy luận rằng vì method có `@Transactional` nên `CONFIRMED` nhất định bị trả về trạng thái cũ nếu `INCR` lỗi trong `EXEC`.

### 8.2. Vì sao không thể xem Redis + SQL là một transaction duy nhất?

Giả sử ứng dụng:

```text
1. INSERT order vào PostgreSQL
2. Ghi Redis status = CONFIRMED
3. COMMIT
```

Chỉ dùng một `@Transactional` không mặc nhiên tạo **atomic commit phân tán** giữa PostgreSQL và Redis. Ngay cả khi cả hai tài nguyên có kết nối transaction ở tầng Spring, vẫn tồn tại tình huống một hệ thống ghi thành công còn hệ thống kia lỗi hoặc mất kết nối. Redis transaction không hỗ trợ rollback những thay đổi đã thực thi để khớp trạng thái với SQL.

Nếu PostgreSQL là dữ liệu nguồn của đơn hàng, một mô hình an toàn hơn thường là:

1. Ghi đơn hàng và bản ghi **transactional outbox** vào cùng transaction PostgreSQL.
2. Commit SQL transaction.
3. Một tiến trình đọc outbox để cập nhật Redis cache hoặc gửi sự kiện, có retry và idempotency.
4. Nếu Redis tạm lỗi, tiến trình tiếp tục thử; PostgreSQL vẫn là nguồn dữ liệu chính xác.

Cách này chấp nhận rằng Redis có thể cập nhật chậm so với SQL, nhưng dễ giải thích và khôi phục sau lỗi hơn là giả định cả hai được commit/rollback cùng lúc.

## 9. Vì sao Redis transaction không bảo đảm mọi quy tắc nghiệp vụ?

`MULTI`/`EXEC` ngăn client khác xen lệnh vào giữa nhóm đã queue, nhưng không tự xác nhận các điều kiện nghiệp vụ:

- **Không vượt tồn kho:** cần kiểm tra số lượng hiện có và xử lý cạnh tranh.
- **Không trừ số dư thành âm:** cần kiểm tra tiền điều kiện ngay trong luồng ghi nguyên tử.
- **Không xác nhận đơn hàng khi bước ghi khác lỗi:** cần cấu trúc lệnh và kiểm tra đầu vào để tránh trạng thái nửa thành công.
- **Không xử lý cùng một yêu cầu hai lần:** cần idempotency key hoặc cơ chế đánh dấu đã xử lý.

Ví dụ sau có thể gây kết quả sai dù `MULTI`/`EXEC` đều thành công:

```redis
SET stock:item-233 1

MULTI
DECRBY stock:item-233 2
SET order:233:state "CONFIRMED"
EXEC
```

Kết quả là kho còn `-1` và đơn hàng được đánh dấu xác nhận. Đây **không phải lỗi runtime** của Redis: cả hai lệnh đều hợp lệ. Do đó, có rollback cũng không giúp nếu ứng dụng không định nghĩa/kiểm tra quy tắc cần bảo vệ.

### 9.1. Lua script hoặc Redis Function cho thao tác có điều kiện

Redis cho phép thực thi Lua script theo kiểu nguyên tử: các lệnh của script chạy mà không bị client khác chen vào. Với nghiệp vụ “chỉ giảm kho nếu đủ hàng”, có thể **kiểm tra trước khi ghi** trong một script:

```lua
-- KEYS[1]: key tồn kho
-- KEYS[2]: key trạng thái đơn hàng
-- ARGV[1]: số lượng cần mua

local quantity = tonumber(ARGV[1])
if quantity == nil or quantity <= 0 or quantity % 1 ~= 0 then
    return redis.error_reply("invalid quantity")
end

local stock = redis.call("GET", KEYS[1])
if stock == false then
    return redis.error_reply("stock key is missing")
end

local current = tonumber(stock)
if current == nil or current < quantity then
    return redis.error_reply("insufficient stock or invalid stock value")
end

-- Không có thao tác ghi nào xảy ra trước các kiểm tra.
redis.call("DECRBY", KEYS[1], quantity)
redis.call("SET", KEYS[2], "CONFIRMED")
return current - quantity
```

Có thể gọi script theo key/argument:

```redis
EVAL "<nội dung script Lua ở trên>" 2 stock:item-233 order:233:state 2
```

Đoạn `EVAL` trên là cú pháp minh họa; khi chạy thực tế, cần truyền toàn bộ script dưới dạng một đối số hoặc dùng `SCRIPT LOAD`/`EVALSHA` qua client.

Với script, kiểm tra điều kiện và thay đổi kho diễn ra trong cùng một lần thực thi không bị chen vào. Tuy nhiên, **Lua script của Redis cũng không cung cấp rollback tự động khi lỗi runtime xảy ra sau một lệnh ghi đã thành công**. Vì vậy, script nên kiểm tra mọi điều kiện có thể kiểm tra trước khi ghi, hạn chế lệnh có thể lỗi sau bước ghi đầu tiên và đảm bảo idempotency khi cần.

Trong Redis Cluster, các key của script/transaction cũng phải phù hợp với ràng buộc cùng hash slot theo kiểu triển khai. Không coi Lua script là lời giải mặc định cho mọi loại giao dịch phân tán.

### 9.2. Lệnh Redis đơn có tính nguyên tử có thể tốt hơn

Nếu yêu cầu chỉ là “tăng một counter”, hãy dùng một lệnh `INCR` thay vì `GET` + `SET`. Nếu yêu cầu là “chỉ tạo key khi chưa có”, cân nhắc `SET key value NX`. Nếu cần đổi một Hash field, dùng thao tác Hash phù hợp.

Một lệnh Redis được xử lý nguyên tử ở cấp lệnh có thể đơn giản và dễ kiểm soát hơn nhóm nhiều lệnh. Nhưng khi điều kiện phụ thuộc nhiều key, vẫn phải chọn `WATCH` hoặc script theo khả năng và hạn chế của chúng.

## 10. Mất kết nối, retry và tính bền vững

Giả sử client gửi `EXEC` rồi mất kết nối trước khi nhận phản hồi. Có ít nhất hai khả năng:

1. Redis chưa nhận hoặc chưa thực thi `EXEC`.
2. Redis đã thực thi nhóm lệnh nhưng phản hồi không đến được client.

Từ góc nhìn client, không thể kết luận “không thấy phản hồi nghĩa là không có thay đổi”. Nếu tự động gửi lại một lệnh `INCR` hoặc `DECRBY`, ứng dụng có thể tăng/trừ **hai lần**.

Ví dụ nguy hiểm:

```redis
MULTI
INCR order:233:sequence
SET order:233:status "APPROVED"
EXEC
```

Nếu `EXEC` đã chạy nhưng client timeout, lần retry nguyên nhóm có thể tăng `order:233:sequence` lần nữa. Cần thiết kế thao tác có thể thực hiện lại an toàn, chẳng hạn dùng **request ID**, trạng thái đã xử lý và một luồng kiểm tra/ghi nguyên tử phù hợp. Chỉ gắn `@Transactional` không giải quyết được “kết quả không rõ sau timeout”.

### Atomicity không đồng nghĩa durability

Redis còn có các cơ chế lưu dữ liệu bền vững như RDB, AOF và replication. Những lựa chọn này quyết định khả năng phục hồi dữ liệu sau sự cố, nhưng không biến `EXEC` thành transaction rollback kiểu SQL.

| Khái niệm | Câu hỏi nó trả lời |
|---|---|
| Atomic execution của `MULTI`/`EXEC` | Client khác có thể chen lệnh vào giữa nhóm hay không? |
| Rollback | Nếu lệnh thứ hai thất bại sau khi lệnh thứ nhất đã sửa dữ liệu, dữ liệu có được hoàn tác không? |
| Optimistic concurrency với `WATCH` | Dữ liệu đã thay đổi từ lần đọc đến lúc định ghi chưa? |
| Durability | Sau sự cố máy chủ, thay đổi đã được thực thi có còn không? |
| Idempotency | Nếu client gửi cùng yêu cầu thêm một lần, hiệu ứng có bị nhân đôi không? |

Không nên dùng một tính chất để suy ra các tính chất khác. Một hệ thống có thể thực thi một nhóm lệnh liên tiếp nhưng vẫn cần xử lý lỗi runtime, sự cố mạng, lost response và độ bền lưu trữ.

## 11. Chọn giải pháp theo yêu cầu

| Nhu cầu | Hướng bắt đầu | Điều cần nhớ |
|---|---|---|
| Gom nhiều lệnh Redis và không cho client khác xen vào | `MULTI` + `EXEC` | Không có rollback sau lỗi thực thi |
| Hủy nhiều lệnh đã queue nhưng chưa chạy | `DISCARD` | Không thể undo kết quả của `EXEC` trước đó |
| Đọc giá trị, kiểm tra, rồi chỉ ghi nếu key chưa đổi | `WATCH` + `MULTI`/`EXEC` | Có thể bị hủy do xung đột; cần retry có giới hạn |
| Kiểm tra điều kiện và cập nhật nhiều trường Redis trong một bước | Lua script / Redis Function | Kiểm tra trước ghi; script cũng không tự rollback lỗi sau ghi |
| Một counter hoặc thao tác kiểm tra đơn giản | `INCR`, `SET NX` và lệnh nguyên tử tương ứng | Dùng lệnh đơn khi đủ biểu đạt nghiệp vụ |
| Dữ liệu nghiệp vụ cần rollback và invariant nhiều bản ghi | Transaction của cơ sở dữ liệu phù hợp | Redis cache thường không nên là nguồn sự thật duy nhất cho ledger |
| Phối hợp ghi SQL và cập nhật Redis | SQL transaction + outbox + xử lý idempotent | Không có distributed rollback mặc định giữa hai hệ |
| Retry sau timeout | Request ID và cơ chế kiểm tra hiệu ứng đã áp dụng | Không gửi lặp lệnh không idempotent một cách mù quáng |

## 12. Bài thực hành bằng Redis CLI và Spring Data Redis

### Thực hành A — Nhóm thành công

1. Tạo `lab:233:a = 0` và `lab:233:b = 0`.
2. `MULTI`, queue hai lệnh `INCR` rồi `EXEC`.
3. Quan sát hai kết quả số nguyên và giá trị mới của hai key.

```redis
SET lab:233:a 0
SET lab:233:b 0
MULTI
INCR lab:233:a
INCR lab:233:b
EXEC
MGET lab:233:a lab:233:b
```

### Thực hành B — Lỗi runtime không rollback

1. Gán `lab:233:b` thành chuỗi `bad`.
2. `MULTI`, queue `INCR lab:233:a`, `INCR lab:233:b` và `SET lab:233:done 1`.
3. Gọi `EXEC` rồi kiểm tra cả ba key.
4. Giải thích vì sao `a` đã tăng và `done` đã được ghi dù `b` báo lỗi.

```redis
SET lab:233:b bad
MULTI
INCR lab:233:a
INCR lab:233:b
SET lab:233:done 1
EXEC
MGET lab:233:a lab:233:b lab:233:done
```

### Thực hành C — DISCARD và lỗi khi queue

1. `MULTI`, queue `SET lab:233:cancelled yes` rồi gọi `DISCARD`; dùng `EXISTS` để kiểm tra.
2. Lặp lại nhưng gửi lệnh sai số tham số trong khi queue, sau đó `EXEC`.
3. So sánh việc **hủy trước khi ghi** với tình huống ở thực hành B.

```redis
MULTI
SET lab:233:cancelled yes
DISCARD
EXISTS lab:233:cancelled

MULTI
SET lab:233:should-not-exist yes
INCR
EXEC
EXISTS lab:233:should-not-exist
```

### Thực hành D — WATCH với hai cửa sổ CLI

1. Cửa sổ A: `WATCH lab:233:stock` và đọc số lượng.
2. Cửa sổ B: sửa `lab:233:stock`.
3. Cửa sổ A: `MULTI`, queue `DECRBY` và gọi `EXEC`.
4. Quan sát transaction bị hủy do xung đột; thử lại bằng cách đọc giá trị mới.

### Thực hành E — Quan sát ở Spring Data Redis

1. Tạo `StringRedisTemplate` và sử dụng `SessionCallback` như mục 7.
2. Đặt `demo:233:counter = "not-a-number"` trước khi chạy callback.
3. Gọi callback rồi quan sát cách driver biểu diễn lỗi của `EXEC`.
4. Đọc lại `demo:233:status` và `demo:233:counter` ngoài transaction.
5. Giải thích vì sao một exception do client nhận được không phải bằng chứng Redis đã hoàn tác `SET` thành công.

Chạy thực hành trên Redis test và các key có prefix riêng. Không dùng key nghiệp vụ thật để cố ý gây lỗi transaction.

## 13. Những hiểu lầm cần tránh

**“MULTI/EXEC giống BEGIN/COMMIT của SQL.”** Chúng giống nhau ở mục tiêu nhóm các thay đổi, nhưng Redis không hỗ trợ undo khi một lệnh trong `EXEC` lỗi.

**“Nếu EXEC báo lỗi thì không lệnh nào được thực thi.”** Chỉ đúng với một số tình huống như transaction bị từ chối vì lỗi queue hoặc xung đột `WATCH`. Lỗi runtime riêng của một lệnh vẫn có thể để lại các thay đổi của những lệnh khác.

**“DISCARD là lệnh ROLLBACK của Redis.”** `DISCARD` chỉ hủy queue chưa chạy. Sau `EXEC`, không thể gọi `DISCARD` để hoàn tác lịch sử.

**“WATCH khiến các lệnh không bao giờ lỗi.”** `WATCH` chỉ kiểm tra xung đột với key được theo dõi trước khi `EXEC` chạy; nó không đảm bảo dữ liệu đúng kiểu hay mọi điều kiện nghiệp vụ đều thỏa.

**“@Transactional bảo đảm Redis và SQL rollback cùng nhau.”** Annotation của Spring không tự thêm distributed atomic commit hoặc undo log cho Redis. Cần hiểu transaction manager, Redis transaction support và cơ chế tích hợp thực tế.

**“Không nhận được kết quả EXEC thì retry sẽ an toàn.”** Redis có thể đã thực thi `EXEC` trước khi kết nối mất. Mọi thao tác có hiệu ứng cộng dồn đều cần idempotency/reconciliation phù hợp.

**“Lua script có rollback như SQL.”** Lua script chạy không bị lệnh client khác xen vào, nhưng lệnh đã ghi trong script cũng không tự được hoàn tác nếu script gặp lỗi runtime sau đó.

## 14. Kết luận

Redis transaction cung cấp tính thực thi tuần tự của một nhóm lệnh và một số công cụ kiểm soát cạnh tranh (`MULTI`, `EXEC`, `DISCARD`, `WATCH`). Đây là một tập tính năng hữu ích, nhưng **không tương đương hệ thống transaction có rollback như các cơ sở dữ liệu SQL**.

Khi một lệnh trong `EXEC` lỗi lúc thực thi, Redis tiếp tục xử lý các lệnh còn lại, không khôi phục những thay đổi đã thành công. `DISCARD` và việc `WATCH` làm `EXEC` bị hủy đều xảy ra **trước khi** nhóm lệnh được chạy. Trong Spring Data Redis, `SessionCallback` bảo đảm chuỗi lệnh dùng cùng connection và `setEnableTransactionSupport(true)` cho phép tích hợp với vòng đời transaction của Spring, nhưng không thay đổi ngữ nghĩa rollback tại Redis server.

Để xây dựng nghiệp vụ an toàn, hãy kiểm tra điều kiện trước khi ghi, chọn lệnh đơn/`WATCH`/Lua theo bài toán, đọc kết quả và xử lý lỗi thực thi, giới hạn retry, thiết kế idempotency, đồng thời dùng cơ sở dữ liệu phù hợp làm nguồn sự thật khi cần ACID và rollback mạnh.

## Tài liệu tham khảo

- [Redis — Transactions](https://redis.io/docs/latest/develop/interact/transactions/): `MULTI`, `EXEC`, `DISCARD`, `WATCH`, các loại lỗi và lý do Redis không hỗ trợ rollback.
- [Redis — MULTI](https://redis.io/docs/latest/commands/multi/): bắt đầu queue các lệnh.
- [Redis — EXEC](https://redis.io/docs/latest/commands/exec/): thực thi các lệnh đã xếp và trả kết quả.
- [Redis — DISCARD](https://redis.io/docs/latest/commands/discard/): hủy transaction đang queue.
- [Redis — WATCH](https://redis.io/docs/latest/commands/watch/): optimistic locking trước `EXEC`.
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): sử dụng `SessionCallback`, `multi`/`exec` và transaction support với Spring.
- [Spring Data Redis API — SessionCallback](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/SessionCallback.html): callback giữ nhiều Redis Operations trong một session kết nối.
