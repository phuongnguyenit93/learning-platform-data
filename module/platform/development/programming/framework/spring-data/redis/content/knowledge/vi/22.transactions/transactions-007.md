# WATCH và cập nhật lạc quan với kiểm tra xung đột

## 1. Vì sao đọc rồi ghi lại có thể làm mất tính đúng đắn?

Giả sử hệ thống bán vé chỉ còn **một chỗ trống**. Hai người dùng cùng gửi yêu cầu đặt chỗ. Nếu ứng dụng Spring Boot làm theo ba bước:

1. Đọc số chỗ trống trong Redis.
2. Nếu số chỗ lớn hơn 0, tính số chỗ mới bằng số cũ trừ 1.
3. Ghi số chỗ mới về Redis.

thì cả hai yêu cầu có thể cùng đọc được giá trị `1`:

~~~text
                 Redis: seats:event-42 = "1"

Request A                                 Request B
---------                                 ---------
GET -> 1                                  GET -> 1
Kiểm tra 1 > 0                            Kiểm tra 1 > 0
Tính 1 - 1 = 0                            Tính 1 - 1 = 0
SET 0                                     SET 0
Trả "đặt thành công"                       Trả "đặt thành công"

                 Redis: seats:event-42 = "0"
                 Nhưng đã bán thành công 2 vé!
~~~

Lệnh `GET` và `SET` riêng lẻ đều được Redis thực thi nguyên tử, nhưng **chuỗi đọc → kiểm tra → ghi không phải một thao tác nguyên tử**. Giá trị có thể bị thay đổi sau lúc đọc và trước lúc ghi.

Đây là vấn đề **cập nhật đồng thời** (concurrent update), thường biểu hiện thành:

- **Cập nhật bị mất (lost update):** hai yêu cầu cùng tính từ một giá trị cũ rồi ghi đè lên nhau.
- **Vi phạm điều kiện nghiệp vụ:** tồn kho không được âm, số lượt sử dụng không được vượt hạn mức, mã ưu đãi chỉ được dùng một lần.
- **Quyết định dựa trên trạng thái cũ:** ứng dụng xác nhận một thao tác dù dữ liệu đã thay đổi trước thời điểm lưu.

Trong Redis, `WATCH` kết hợp với `MULTI` và `EXEC` hỗ trợ **kiểm soát đồng thời lạc quan** (optimistic concurrency control): ứng dụng giả định ít xung đột, nhưng kiểm tra lại trước khi xác nhận các lệnh ghi.

Trong Spring Data Redis, cơ chế này thường được triển khai bằng `RedisTemplate`/`StringRedisTemplate` với `SessionCallback` để các lệnh trong một lượt giao dịch đi qua **cùng một kết nối Redis**.

## 2. Mô hình lạc quan: WATCH theo dõi thay đổi, EXEC quyết định có thực thi hay không

### 2.1. Ý nghĩa của từng lệnh

| Lệnh | Vai trò |
|---|---|
| `WATCH key [key ...]` | Theo dõi một hoặc nhiều khóa để phát hiện thay đổi trước `EXEC` |
| `GET key`, `HGET ...` | Đọc trạng thái hiện tại và kiểm tra điều kiện nghiệp vụ |
| `MULTI` | Bắt đầu giao dịch, từ đây các lệnh tiếp theo được đưa vào hàng đợi |
| `SET`, `DECR`, `HSET`, ... | Những lệnh ghi sẽ được xếp hàng, chờ `EXEC` |
| `EXEC` | Nếu không có xung đột trên khóa đã theo dõi, thực thi hàng đợi; nếu có xung đột, hủy việc thực thi cả hàng đợi |
| `DISCARD` | Bỏ hàng đợi và kết thúc giao dịch đang mở |
| `UNWATCH` | Hủy theo dõi khóa khi không tiếp tục giao dịch |

Một luồng thông thường:

~~~text
WATCH seats:event-42
        |
GET seats:event-42
        |
Kiểm tra còn vé?
     /        \
   Không        Có
    |           |
 UNWATCH       MULTI
    |           |
  Dừng      DECR seats:event-42
                |
               EXEC
             /      \
          Thành công   Xung đột
              |           |
        Xác nhận vé   Đọc lại và thử lại
~~~

`WATCH` tự nó không khóa Redis và không ngăn các kết nối khác ghi dữ liệu. Nó đánh dấu rằng giao dịch sắp tới **chỉ hợp lệ nếu những khóa được theo dõi không bị sửa** trước `EXEC`.

### 2.2. Hai yêu cầu cạnh tranh cùng một khóa

Giả sử cả A và B đều theo dõi `seats:event-42` khi giá trị còn 1:

~~~text
Thời điểm       Client A                        Client B
---------       --------                        --------
t1              WATCH seats:event-42
t2                                              WATCH seats:event-42
t3              GET -> 1
t4                                              GET -> 1
t5              MULTI
t6              DECR seats:event-42 (QUEUED)
t7                                              MULTI
t8                                              DECR seats:event-42 (QUEUED)
t9              EXEC -> [0] (thành công)
t10                                             EXEC -> nil (bị hủy)
t11             Trả thành công                  Xử lý xung đột / thử lại

Kết quả Redis: seats:event-42 = 0
Chỉ một giao dịch thực sự trừ chỗ.
~~~

A đã thay đổi khóa sau khi B gọi `WATCH`. Bởi vậy Redis phát hiện khóa theo dõi không còn ở trạng thái như lúc B bắt đầu giao dịch và **không thực thi** hàng đợi của B khi B gọi `EXEC`.

Nếu không có xung đột, `EXEC` trả về danh sách kết quả của những lệnh đã xếp hàng. Nếu giao dịch bị hủy do `WATCH`, Redis trả phản hồi null/nil cho `EXEC`. Cách API Java biểu diễn phản hồi này phụ thuộc driver và lớp trừu tượng, nhưng với Spring Data Redis thường là kết quả `exec()` bằng `null`.

### 2.3. Lệnh ghi nào được tính là xung đột?

Giả sử A đã gọi:

~~~redis
WATCH seats:event-42
~~~

Trong thời gian trước khi A gọi `EXEC`, nếu một kết nối khác thực hiện:

~~~redis
SET seats:event-42 20
~~~

hoặc:

~~~redis
DECR seats:event-42
~~~

thì A sẽ không được phép xác nhận giao dịch cũ.

Redis cũng tính các thay đổi xảy ra do **hết hạn TTL hoặc thu hồi bộ nhớ (eviction)** là thay đổi gây hủy giao dịch `WATCH` trên các phiên bản Redis hiện đại; hành vi này được ghi nhận từ Redis 6.0.9. Vì vậy, khóa có TTL có thể tạo xung đột dù ứng dụng không chủ động ghi nó.

`WATCH` theo dõi **khóa**, không tự hiểu điều kiện nghiệp vụ như “số chỗ phải lớn hơn 0”. Phải kiểm tra điều kiện bằng mã ứng dụng **sau khi WATCH, trước MULTI** và đọc lại khi có xung đột.

## 3. Thử trực tiếp bằng Redis CLI

Mở hai cửa sổ `redis-cli`, gọi là **Client A** và **Client B**. Các phiên phải kết nối đến cùng Redis và cùng cơ sở dữ liệu; đối với Redis Cluster, phải cùng nút sở hữu khóa thích hợp.

Khởi tạo dữ liệu một lần:

~~~redis
SET seats:event-42 1
~~~

**Client A:**

~~~redis
WATCH seats:event-42
GET seats:event-42
~~~

Redis trả giá trị `"1"`.

**Client B:**

~~~redis
WATCH seats:event-42
GET seats:event-42
~~~

Redis cũng trả `"1"`.

Tiếp theo **Client A** gọi:

~~~redis
MULTI
DECR seats:event-42
EXEC
~~~

`DECR` nằm trong giao dịch sẽ trả `QUEUED` khi được xếp hàng. `EXEC` thực thi lệnh và trả kết quả trừ chỗ (thường bằng 0).

Sau đó **Client B** gọi:

~~~redis
MULTI
DECR seats:event-42
EXEC
~~~

Lượt `EXEC` của B bị hủy vì khóa đã bị A thay đổi sau thời điểm B bắt đầu `WATCH`. Giao dịch B không làm giảm giá trị xuống -1.

Lúc này, B có thể **khởi tạo một lượt mới**:

~~~redis
WATCH seats:event-42
GET seats:event-42
~~~

Kết quả là `"0"`. B kiểm tra không còn chỗ và kết thúc:

~~~redis
UNWATCH
~~~

Việc kiểm tra và dừng sau khi đọc lại mới là phần bảo đảm điều kiện “chỉ bán khi còn chỗ”. Redis không tự suy ra điều kiện đó chỉ từ `WATCH`.

### Phân biệt ba loại kết quả

| Tình huống | Kết quả | Cách xử lý |
|---|---|---|
| Không có xung đột; điều kiện được đáp ứng | `EXEC` thực thi hàng đợi | Kiểm tra kết quả các lệnh rồi xác nhận |
| Có thay đổi trên khóa đã `WATCH` | `EXEC` hủy hàng đợi | Đọc lại trạng thái trong lượt mới; giới hạn số lần thử |
| Điều kiện không được đáp ứng ngay lúc đọc | Không cần `MULTI`/`EXEC` | `UNWATCH` rồi trả hết hàng hoặc từ chối nghiệp vụ |

Một giao dịch bị hủy do xung đột **không đồng nghĩa** với hết hàng. Số chỗ có thể đã tăng, giảm, hoặc bị thay đổi bởi thao tác khác; cần đọc lại trước khi quyết định.

## 4. Vì sao phải WATCH trước khi đọc và MULTI sau khi kiểm tra?

Thứ tự đúng khi điều kiện phụ thuộc vào một khóa:

~~~redis
WATCH seats:event-42
GET seats:event-42
# Kiểm tra số chỗ > 0 tại ứng dụng
MULTI
DECR seats:event-42
EXEC
~~~

Nếu đọc trước khi `WATCH`:

~~~redis
GET seats:event-42
# Có kết nối khác thay đổi giá trị ở đây
WATCH seats:event-42
MULTI
DECR seats:event-42
EXEC
~~~

thì thay đổi giữa `GET` và `WATCH` **không được theo dõi**, trong khi quyết định của ứng dụng vẫn dựa trên giá trị cũ. Giao dịch có thể hoàn tất dù điều kiện trước đó đã trở nên sai.

Nếu gọi `MULTI` trước khi đọc:

~~~redis
MULTI
GET seats:event-42
DECR seats:event-42
EXEC
~~~

thì `GET` ở giữa không trả giá trị để ứng dụng kiểm tra ngay; Redis chỉ trả `QUEUED`, sau đó trả kết quả khi `EXEC` chạy. Như vậy, ứng dụng **không thể dùng kết quả GET trong cùng hàng đợi để ra quyết định trước lúc xếp lệnh DECR**.

Đối với mô hình kiểm tra rồi cập nhật bằng `WATCH`, luồng thông thường là:

**`WATCH → đọc → kiểm tra → MULTI → xếp lệnh ghi → EXEC`**.

Redis thực thi các lệnh đã xếp hàng liên tiếp trong một `EXEC` mà không chen lệnh từ client khác giữa những lệnh đó. Tuy nhiên, giao dịch Redis không cung cấp cơ chế rollback toàn bộ như giao dịch SQL nếu một lệnh đã chạy nhưng phát sinh lỗi thực thi.

## 5. Spring Data Redis: sử dụng SessionCallback để giữ cùng kết nối

### 5.1. Vì sao không nên viết các lời gọi rời rạc?

`WATCH` gắn với **kết nối Redis**. Các thao tác `MULTI` và `EXEC` của giao dịch cũng phải diễn ra trên kết nối đó.

Đoạn sau thể hiện ý định nhưng không bảo đảm được ngữ cảnh phiên nếu các thao tác được tổ chức tùy tiện:

~~~java
// Ví dụ KHÔNG NÊN dùng như một giao dịch đầy đủ.
redisTemplate.watch(key);
String value = redisTemplate.opsForValue().get(key);
redisTemplate.multi();
redisTemplate.opsForValue().decrement(key);
redisTemplate.exec();
~~~

Không nên mặc định từng lần gọi vào `RedisTemplate` ở những đoạn mã hoặc luồng khác nhau luôn chia sẻ đúng một kết nối đã `WATCH`. Sử dụng **`SessionCallback`** để nhóm các thao tác cần cùng một kết nối.

`RedisTemplate.execute(SessionCallback<T>)` cho phép chạy nhiều thao tác của `RedisOperations` trong một phiên kết nối. Đây là cách Spring Data Redis khuyến nghị cho các chuỗi lệnh `MULTI`/`EXEC` do chương trình tự điều khiển.

### 5.2. Chuẩn bị StringRedisTemplate

Spring Boot có thể tự cấu hình `StringRedisTemplate` khi dự án có Spring Data Redis starter và thông tin kết nối Redis phù hợp.

`StringRedisTemplate` dùng cách biểu diễn chuỗi cho tên khóa và giá trị, thuận tiện cho ví dụ tồn kho số nguyên:

~~~text
key: seats:event-42
value: "1"
~~~

Một mã dựa trên `RedisTemplate<String, String>` cần bảo đảm serializer được cấu hình nhất quán giữa quá trình ghi dữ liệu ban đầu và các lệnh trong giao dịch. Nếu giá trị được lưu bằng một serializer khác, việc ép chuỗi rồi phân tích số có thể thất bại.

### 5.3. Ví dụ hoàn chỉnh: giữ chỗ với WATCH

Đây là ví dụ dùng một khóa Redis cho số chỗ còn lại. Nó thể hiện rõ ba kết quả: **đặt thành công**, **hết chỗ**, và **xung đột cần thử lại**.

~~~java
package com.example.redis;

public enum ReserveResult {
    RESERVED,
    SOLD_OUT,
    NOT_FOUND,
    TOO_MUCH_CONTENTION
}
~~~

Service:

~~~java
package com.example.redis;

import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SeatReservationService {

    private static final int MAX_ATTEMPTS = 5;

    private final StringRedisTemplate redis;

    public SeatReservationService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public ReserveResult reserveOne(String eventId) {
        String key = "seats:" + eventId;

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            AttemptResult result = attemptOnce(key);

            switch (result) {
                case COMMITTED:
                    return ReserveResult.RESERVED;
                case SOLD_OUT:
                    return ReserveResult.SOLD_OUT;
                case NOT_FOUND:
                    return ReserveResult.NOT_FOUND;
                case CONFLICT:
                    // Bắt đầu lại từ WATCH/GET ở lượt mới.
                    break;
            }
        }

        return ReserveResult.TOO_MUCH_CONTENTION;
    }

    private AttemptResult attemptOnce(String key) {
        return redis.execute(new SessionCallback<AttemptResult>() {

            @Override
            @SuppressWarnings("unchecked")
            public <K, V> AttemptResult execute(
                    RedisOperations<K, V> sessionOperations)
                    throws DataAccessException {

                // Callback thuộc StringRedisTemplate, nên key/value
                // đang dùng StringRedisSerializer.
                RedisOperations<String, String> ops =
                        (RedisOperations<String, String>)
                        (RedisOperations<?, ?>) sessionOperations;

                boolean watching = false;
                boolean inMulti = false;

                try {
                    ops.watch(key);
                    watching = true;

                    String raw = ops.opsForValue().get(key);

                    if (raw == null) {
                        return AttemptResult.NOT_FOUND;
                    }

                    long available = Long.parseLong(raw);

                    if (available <= 0) {
                        return AttemptResult.SOLD_OUT;
                    }

                    ops.multi();
                    inMulti = true;

                    ops.opsForValue().decrement(key);

                    List<Object> result = ops.exec();
                    inMulti = false;
                    watching = false;

                    if (result == null) {
                        // WATCH phát hiện khóa đã thay đổi.
                        return AttemptResult.CONFLICT;
                    }

                    if (result.size() != 1
                            || !(result.get(0) instanceof Number)) {
                        throw new IllegalStateException(
                                "Kết quả EXEC không như mong đợi"
                        );
                    }

                    return AttemptResult.COMMITTED;

                } finally {
                    if (inMulti) {
                        // Thử đóng giao dịch còn mở nếu xảy ra lỗi.
                        // Không biến lỗi kết nối thành xung đột để tự retry.
                        try {
                            ops.discard();
                        } catch (RuntimeException ignored) {
                            // Giữ nguyên lỗi gốc.
                        }
                    } else if (watching) {
                        // Hủy WATCH nếu thoát trước MULTI/EXEC.
                        try {
                            ops.unwatch();
                        } catch (RuntimeException ignored) {
                            // Giữ nguyên lỗi gốc, nếu có.
                        }
                    }
                }
            }
        });
    }

    private enum AttemptResult {
        COMMITTED,
        CONFLICT,
        SOLD_OUT,
        NOT_FOUND
    }
}
~~~

Các điểm cần hiểu:

1. `redis.execute(new SessionCallback<...>())` bảo đảm chuỗi thao tác được gửi theo một ngữ cảnh phiên kết nối.
2. `ops.watch(key)` phải được gọi **trước** `ops.opsForValue().get(key)`.
3. `raw == null` được xử lý riêng vì khóa chưa tồn tại không đồng nghĩa với có 0 chỗ.
4. Nếu `available <= 0`, phương thức thoát sớm; khối `finally` thực hiện `UNWATCH`.
5. Nếu còn chỗ, `ops.multi()` mở giao dịch và `decrement(key)` được xếp hàng.
6. `ops.exec()` trả `null` khi có xung đột do `WATCH` trong cơ chế trả kết quả thông dụng của Spring Data Redis. Chỉ trường hợp này mới được thử lại như xung đột thông thường.
7. Sau `EXEC` thành công, code còn kiểm tra số lượng và loại kết quả trước khi trả thành công.
8. `MAX_ATTEMPTS` ngăn việc thử lại không giới hạn khi một khóa được cập nhật liên tục.

Trong ứng dụng có nhiều yêu cầu đồng thời vào cùng một khóa, có thể bổ sung **tạm dừng ngắn, tăng dần và ngẫu nhiên** giữa các lần thử. Cách này tránh tất cả client tranh chấp liên tục trong các vòng lặp sát nhau. Một request có thể từ chối sớm và để phía gọi thử lại sau thay vì chiếm tài nguyên quá lâu.

> Ví dụ tập trung vào đúng một khóa tồn kho. Với hệ thống đặt vé thật, còn phải xử lý định danh yêu cầu, thanh toán, huỷ đặt chỗ, ghi nhận lịch sử và tính nhất quán với các hệ thống bên ngoài. Giao dịch Redis trên số chỗ không tự giải quyết các bước đó.

### 5.4. Vì sao không thử lại mọi ngoại lệ?

Cần phân biệt rõ:

- **Xung đột có chứng cứ:** `EXEC` trả phản hồi bị hủy do `WATCH`. Các lệnh ghi đã xếp hàng không chạy; có thể thực hiện lượt đọc/kiểm tra mới.
- **Hết chỗ hoặc không tìm thấy khóa:** điều kiện nghiệp vụ không thỏa. Không nên biến thành lỗi hệ thống hoặc cứ thử đi thử lại vô hạn.
- **Lỗi mạng, timeout, mất kết nối khi EXEC:** ứng dụng có thể không biết chắc Redis đã nhận và thực thi giao dịch hay chưa. Tự động gửi lại cùng lệnh có thể gây tác động lặp.

Vì vậy, không nên viết:

~~~java
try {
    reserveOne(eventId);
} catch (Exception e) {
    // Không an toàn khi retry mọi lỗi mà không biết giao dịch đã commit chưa.
    reserveOne(eventId);
}
~~~

Nếu một yêu cầu không được phép xử lý hai lần, hệ thống cần thêm **khóa chống lặp theo requestId** hoặc mô hình ghi nhận kết quả có thể xác minh. Tránh đồng nhất “không nhận được phản hồi” với “chắc chắn chưa thực thi”.

## 6. WATCH không biến MULTI/EXEC thành khóa độc quyền

Khác với khóa bi quan (pessimistic locking), `WATCH` không ngăn người khác ghi vào khóa. Nó chỉ khiến giao dịch của mình bị hủy nếu dữ liệu được theo dõi thay đổi.

~~~text
Khóa bi quan (ý tưởng):            WATCH lạc quan trong Redis:

A giữ khóa                          A WATCH + GET
B phải chờ                          B vẫn được SET/DECR
A cập nhật rồi mở khóa              A EXEC có thể bị hủy
B tiếp tục                          A đọc lại và thử lại
~~~

Hệ quả:

- Khi **xung đột thấp**, cách lạc quan có thể hiệu quả vì không phải chặn client khác.
- Khi **xung đột cao**, nhiều client có thể đọc, tính toán và bị hủy ở `EXEC`. Tải từ các lượt thử lại có thể tăng.
- `WATCH` không cung cấp fairness, hàng chờ hoặc cam kết rằng yêu cầu sẽ thành công sau một số lần thử.
- Đối với khóa có lượng ghi rất cao, một lệnh Redis nguyên tử chuyên biệt hoặc Lua script có thể phù hợp hơn.

Việc dùng `WATCH` không thay thế cho việc đo đạc tỉ lệ xung đột và số lần retry thực tế.

## 7. WATCH nhiều khóa khi điều kiện trải rộng

Một nghiệp vụ có thể phải kiểm tra **hai khóa**. Ví dụ, người dùng cần có đủ số dư điểm và sự kiện còn chỗ:

~~~text
points:user-7 = 100
seats:event-42 = 2

Điều kiện:
  points:user-7 >= 30
  seats:event-42 > 0

Khi hợp lệ:
  points:user-7 -= 30
  seats:event-42 -= 1
~~~

Trong Redis CLI, có thể theo dõi cả hai:

~~~redis
WATCH points:user-7 seats:event-42
GET points:user-7
GET seats:event-42

# Nếu hai điều kiện đều đạt:
MULTI
DECRBY points:user-7 30
DECR seats:event-42
EXEC
~~~

Nếu **bất kỳ khóa được theo dõi nào** bị sửa trước `EXEC`, Redis hủy các lệnh đã xếp hàng. Điều này giúp quyết định không dựa trên trạng thái cũ của riêng một khóa.

Trong Java:

~~~java
ops.watch(List.of(
        "points:user-7",
        "seats:event-42"
));
~~~

Các lệnh đọc, kiểm tra và ghi tiếp theo cũng cần chạy trong **cùng SessionCallback**.

**Trong Redis Cluster:** giao dịch nhiều khóa phải tuân thủ giới hạn về khe băm (hash slot). Với các lệnh yêu cầu nhiều khóa trong một giao dịch, những khóa đó cần thuộc cùng slot. Có thể dùng hash tag trong tên khóa như `points:{order-42}:user-7` và `seats:{order-42}:event-42` để đưa phần có cùng tag vào cùng slot, nhưng cần thiết kế namespace theo nghiệp vụ từ đầu. Không nên giả định rằng mọi cặp khóa trong cluster đều có thể tham gia chung một `MULTI/EXEC`.

Ngoài ra, thao tác nhiều khóa trong một giao dịch Redis chỉ bảo đảm giới hạn trong **phạm vi Redis**. Nó không tự tạo giao dịch xuyên Redis, cơ sở dữ liệu SQL, dịch vụ thanh toán hoặc hệ thống gửi thông báo.

## 8. Khi nào phải WATCH cả khóa định danh hoặc điều kiện?

Một điểm dễ bỏ sót là: chỉ WATCH khóa sẽ ghi **chưa chắc đã đủ**.

Giả sử ứng dụng kiểm tra trạng thái tài khoản tại:

~~~text
users:7:status = ACTIVE
~~~

rồi trừ điểm tại:

~~~text
users:7:points = 100
~~~

Nếu chỉ:

~~~redis
WATCH users:7:points
GET users:7:status
GET users:7:points
MULTI
DECRBY users:7:points 30
EXEC
~~~

thì thay đổi `users:7:status` từ `ACTIVE` sang `BLOCKED` có thể **không làm hủy giao dịch**, vì Redis chỉ theo dõi khóa điểm.

Để trạng thái tài khoản là một phần của điều kiện nhất quán, phải theo dõi cả khóa trạng thái:

~~~redis
WATCH users:7:status users:7:points
GET users:7:status
GET users:7:points
# Kiểm tra ACTIVE và đủ điểm
MULTI
DECRBY users:7:points 30
EXEC
~~~

Tổng quát: **WATCH tất cả các khóa Redis có giá trị làm cơ sở cho quyết định cần được bảo vệ**, không chỉ khóa cuối cùng sẽ bị ghi.

Dù vậy, nếu điều kiện nằm ở một cơ sở dữ liệu khác hoặc phụ thuộc thời gian thực ngoài Redis, `WATCH` không thể bảo vệ những yếu tố ấy. Cần một cơ chế phối hợp rộng hơn.

## 9. MULTI/EXEC có nguyên tử nhưng không có rollback kiểu SQL

Redis dùng `MULTI`/`EXEC` để xếp nhiều lệnh rồi thực thi chúng liên tiếp khi giao dịch được chấp nhận. Điều đó bảo vệ khỏi sự xen kẽ giữa lệnh của các client khác trong lúc thực thi hàng đợi.

Nhưng không nên diễn giải thành “mọi lỗi đều tự rollback”:

~~~redis
SET counter "hello"

MULTI
INCR counter
SET status "done"
EXEC
~~~

`INCR` trên giá trị không phải số sẽ phát sinh lỗi thực thi. Redis không dùng cơ chế rollback truyền thống để hoàn tác lệnh khác đã thực thi thành công trong hàng đợi. Vì vậy, `SET status "done"` có thể vẫn được thực thi, dù `INCR` lỗi.

Cần phân biệt:

| Trường hợp | Điều gì xảy ra? |
|---|---|
| Khóa được WATCH bị thay đổi trước EXEC | Toàn bộ hàng đợi bị hủy, không chạy |
| Giao dịch không bị xung đột | Các lệnh được thực thi theo thứ tự |
| Một lệnh xếp hàng có lỗi khi thực thi | Không tự động rollback những lệnh khác đã thành công |
| Lệnh có lỗi cú pháp/không thể xếp hàng | Redis có cơ chế từ chối thực thi giao dịch tương ứng |

Bài toán cập nhật lạc quan cần vừa **kiểm tra trước khi MULTI**, vừa chọn những lệnh ghi phù hợp để giảm nguy cơ lỗi trong lúc EXEC.

## 10. So sánh WATCH với các cách cập nhật khác

### 10.1. Chỉ dùng INCR/DECR

~~~redis
DECR seats:event-42
~~~

`DECR` là lệnh nguyên tử. Nếu yêu cầu chỉ là tăng hoặc giảm bộ đếm và không cần điều kiện kiểm tra trước, thao tác nguyên tử này thường đơn giản hơn `WATCH`.

Tuy nhiên, `DECR` **không tự từ chối khi giá trị đang bằng 0**. Nếu nghiệp vụ không cho phép tồn kho âm, chỉ gọi `DECR` mà không xử lý điều kiện sẽ không đủ.

### 10.2. WATCH + MULTI/EXEC

Đây là phương án phù hợp khi:

- Cần đọc trạng thái để quyết định có cập nhật hay không.
- Muốn hủy ghi khi dữ liệu thay đổi trong lúc kiểm tra.
- Số lượng khóa liên quan không quá lớn và xung đột ở mức chấp nhận được.
- Mã nghiệp vụ có thể thực hiện lại bước đọc/kiểm tra một cách an toàn sau xung đột.

Ưu điểm là logic kiểm tra có thể được diễn đạt trực tiếp bằng Java. Chi phí là số lượt mạng và khả năng phải thử lại khi nhiều yêu cầu cạnh tranh.

### 10.3. Lua script thực thi điều kiện và cập nhật ở phía Redis

Nếu điều kiện và thao tác ghi ngắn gọn, có thể dùng Lua script để đọc và cập nhật trong **một lần thực thi nguyên tử** tại Redis:

~~~lua
-- KEYS[1] = "seats:event-42"
local seats = tonumber(redis.call("GET", KEYS[1]))

if seats == nil then
    return -1  -- Không tìm thấy khóa
end

if seats <= 0 then
    return 0   -- Hết chỗ
end

return redis.call("DECR", KEYS[1])
~~~

Chạy script qua Spring Data Redis với `RedisScript<Long>`/`DefaultRedisScript<Long>` và truyền khóa cùng tham số thích hợp. Lua tránh cửa sổ thời gian giữa `GET` và `DECR` bằng cách thực hiện cả hai bên trong Redis.

Nhưng Lua script cũng có giới hạn:

- Script chạy trên luồng xử lý Redis, vì vậy script dài hoặc xử lý dữ liệu lớn có thể làm tăng độ trễ các lệnh khác.
- Logic Lua phải được quản lý, kiểm thử, triển khai và bảo trì.
- Redis Cluster vẫn có quy tắc về khóa/slot.
- Việc gọi script qua mạng có thể gặp tình trạng không rõ kết quả nếu timeout xảy ra sau khi Redis thực thi; yêu cầu chống lặp vẫn cần được thiết kế riêng.

Không có lựa chọn luôn tốt hơn cho mọi trường hợp. Khi chỉ cần thay đổi một bộ đếm, lệnh nguyên tử có thể đủ; khi cần quyết định phức tạp dựa trên trạng thái, `WATCH` hoặc script là những công cụ nên cân nhắc.

## 11. Tránh nhầm với giao dịch Spring @Transactional

`@Transactional` trong Spring thường gắn với quản lý giao dịch của một resource cụ thể, chẳng hạn JPA/database. Nó **không tự biến** chuỗi:

~~~java
String current = redis.opsForValue().get(key);
// Kiểm tra điều kiện
redis.opsForValue().set(key, next);
~~~

thành một giao dịch `WATCH/MULTI/EXEC`.

Spring Data Redis có tùy chọn tham gia ngữ cảnh giao dịch Spring qua `setEnableTransactionSupport(true)`, nhưng đó là cấu hình riêng và có những ngữ nghĩa khác:

- Các lệnh ghi trong transaction có thể được xếp hàng cho `EXEC` lúc hoàn tất transaction.
- Các lệnh đọc trong một ngữ cảnh transaction có thể được thực hiện trên kết nối khác, tùy cơ chế quản lý của Spring Data Redis.
- Nó không tự thêm `WATCH` cho những điều kiện vừa đọc.
- Việc kết hợp Redis và cơ sở dữ liệu khác không tự tạo giao dịch phân tán có thể rollback đồng thời cả hai.

Khi cần `WATCH` cụ thể, hãy thiết kế rõ chuỗi lệnh và sử dụng `SessionCallback` cùng kết nối. Không nên trộn một cách máy móc cơ chế điều khiển `MULTI/EXEC` thủ công với ngữ cảnh `@Transactional` mà chưa hiểu chính xác ranh giới kết nối và commit.

## 12. Những lỗi phổ biến khi triển khai

### Lỗi 1: WATCH sau khi đọc

~~~text
GET -> WATCH -> MULTI -> SET -> EXEC
~~~

Thay đổi giữa `GET` và `WATCH` bị bỏ lọt. Hãy theo dõi trước khi đọc dữ liệu dùng làm điều kiện.

### Lỗi 2: Tách WATCH/MULTI/EXEC sang các kết nối khác nhau

`WATCH` gắn với kết nối. Nếu đọc và thực thi transaction trên những kết nối không thống nhất, cơ chế phát hiện xung đột không còn đúng như mong đợi. Dùng `SessionCallback` để bảo đảm phiên kết nối.

### Lỗi 3: Đọc bên trong MULTI rồi muốn quyết định ngay

~~~redis
MULTI
GET seats:event-42
~~~

`GET` được xếp hàng thay vì trả ngay số chỗ cần kiểm tra. Đọc và kiểm tra trước `MULTI` khi dùng `WATCH`.

### Lỗi 4: Coi mọi EXEC rỗng là xung đột

Phân biệt **phản hồi abort do WATCH** với giao dịch thành công nhưng không có lệnh được xếp hàng, hoặc kết quả bị chuyển đổi bởi driver. Trong ví dụ Java, một lệnh `DECR` chắc chắn được xếp hàng, nên chúng ta kiểm tra `result == null` và xác nhận có đúng một kết quả kiểu số khi commit.

### Lỗi 5: Sau xung đột chỉ gửi lại EXEC mà không đọc lại

`EXEC` thất bại nghĩa là quyết định trước đó có thể đã lỗi thời. Cần **WATCH lại, GET lại, kiểm tra lại, rồi mới MULTI/EXEC**.

### Lỗi 6: Lặp vô hạn khi khóa nóng

Nếu hàng trăm yêu cầu cùng tranh chấp một khóa, rất nhiều giao dịch có thể liên tục bị hủy. Giới hạn số lần thử, có độ trễ thử lại phù hợp và ghi nhận tỉ lệ xung đột. Với tải lớn, cân nhắc script hoặc thiết kế dữ liệu khác.

### Lỗi 7: WATCH không đủ các khóa điều kiện

Nếu quyết định dựa trên `status` và `balance` nhưng chỉ WATCH `balance`, thay đổi `status` không nhất thiết làm hủy giao dịch. Cần bao phủ các khóa liên quan đến tính đúng đắn của quyết định.

### Lỗi 8: Tin rằng EXEC lỗi sẽ tự rollback tất cả

Redis không rollback một lệnh đã thành công chỉ vì một lệnh khác trong cùng `EXEC` lỗi khi thực thi. Hãy thiết kế các lệnh có kiểu dữ liệu/giá trị hợp lệ và xử lý từng kết quả.

### Lỗi 9: Thử lại sau mọi timeout mà không có khóa chống lặp

Timeout khi gửi `EXEC` có thể xảy ra dù Redis đã thực thi giao dịch. Thử lại không kiểm soát có thể đặt hai vé. Các thao tác quan trọng nên có `requestId` và quy tắc thực hiện một lần theo nghiệp vụ.

### Lỗi 10: Quên UNWATCH/DISCARD khi thoát sớm

Nếu không còn nhu cầu commit, hãy dọn trạng thái `WATCH` hoặc transaction đang mở. Trong `SessionCallback` nên dùng `try/finally` để có đường dọn dẹp khi nhánh điều kiện thất bại hoặc ném ngoại lệ.

## 13. Xử lý xung đột trong API và trong tác vụ nền

Giả sử tầng HTTP gọi:

~~~java
ReserveResult result = seatReservationService.reserveOne(eventId);
~~~

Một cách ánh xạ kết quả:

| Kết quả dịch vụ | Ý nghĩa | Hướng phản hồi |
|---|---|---|
| `RESERVED` | Đã thực thi thao tác trừ chỗ | Xác nhận thành công sau khi các bước nghiệp vụ khác phù hợp |
| `SOLD_OUT` | Đã đọc lại và thấy không còn chỗ | Trả thông báo hết hàng |
| `NOT_FOUND` | Không tìm thấy khóa sự kiện | Báo dữ liệu/sự kiện không tồn tại |
| `TOO_MUCH_CONTENTION` | Vượt giới hạn thử lại do xung đột | Trả lỗi có thể thử lại sau hoặc đưa vào cơ chế xử lý thích hợp |

Đừng biến `TOO_MUCH_CONTENTION` thành `SOLD_OUT`: hai trạng thái có ý nghĩa khác nhau. Ngược lại, cũng không nên cho rằng mọi lỗi có thể tự động thử lại mà không xét khả năng giao dịch đã commit.

Với tác vụ nền xử lý nhiều bản ghi, nên đo:

- Số lượt `EXEC` thành công.
- Số lượt bị abort do `WATCH`.
- Số lần thử trung bình cho mỗi thao tác.
- Độ trễ đầu cuối và tỉ lệ vượt giới hạn thử.
- Khối lượng yêu cầu trên những khóa nóng.

Những số liệu này giúp xác định khi nào cơ chế lạc quan vẫn phù hợp và khi nào nên đổi thiết kế.

## 14. Thực hành với xung đột thật

Có thể kiểm chứng theo ba bài tập trên Redis phát triển.

### Bài tập A: Không có xung đột

Khởi tạo:

~~~redis
SET stock:item-1 5
~~~

Trên một client:

~~~redis
WATCH stock:item-1
GET stock:item-1
MULTI
DECR stock:item-1
EXEC
~~~

`EXEC` trả kết quả của `DECR`; khóa còn 4. Trường hợp này không cần thử lại.

### Bài tập B: Có xung đột giữa hai client

Trên Client A:

~~~redis
WATCH stock:item-1
GET stock:item-1
~~~

Trong lúc A đang kiểm tra, Client B sửa khóa:

~~~redis
DECR stock:item-1
~~~

Quay lại Client A:

~~~redis
MULTI
DECR stock:item-1
EXEC
~~~

`EXEC` của A bị hủy bởi `WATCH`, vì khóa thay đổi sau thời điểm A bắt đầu theo dõi. A cần mở lượt theo dõi và đọc mới nếu muốn thử tiếp.

### Bài tập C: Theo dõi hai khóa

Khởi tạo:

~~~redis
SET account:7:status ACTIVE
SET account:7:balance 100
~~~

Client A:

~~~redis
WATCH account:7:status account:7:balance
GET account:7:status
GET account:7:balance
~~~

Client B:

~~~redis
SET account:7:status BLOCKED
~~~

Client A tiếp tục:

~~~redis
MULTI
DECRBY account:7:balance 30
EXEC
~~~

Giao dịch A bị hủy dù khóa `balance` không thay đổi; nguyên nhân là **khóa status cũng được WATCH**.

Trong thực hành, có thể dùng `MONITOR` trong môi trường phát triển để quan sát lệnh, nhưng không bật công cụ giám sát tốn tài nguyên này một cách tùy tiện trên hệ thống đang có tải lớn.

## 15. Câu hỏi tự kiểm tra

**1. Redis đã thực thi riêng từng lệnh theo cơ chế nguyên tử. Vì sao GET rồi SET vẫn có thể sai?**

Vì một client khác có thể thay đổi dữ liệu giữa hai lệnh. Tính nguyên tử của từng lệnh không tự khiến cả chuỗi đọc–kiểm tra–ghi trở thành một thao tác nguyên tử.

**2. WATCH có khóa dữ liệu để client khác phải chờ không?**

Không. Client khác vẫn được cập nhật khóa. Nếu khóa theo dõi thay đổi trước `EXEC`, giao dịch của client đang WATCH sẽ bị hủy.

**3. Tại sao WATCH phải đặt trước GET?**

Để mọi thay đổi xảy ra sau khi ứng dụng bắt đầu dựa vào dữ liệu đều có thể bị phát hiện ở `EXEC`. Đọc trước WATCH tạo một khoảng thời gian thay đổi không được bảo vệ.

**4. Khi EXEC bị hủy, có thể lập tức gửi lại DECR mà không GET lại không?**

Không. Giá trị mới có thể đã thay đổi hoặc điều kiện nghiệp vụ không còn đúng. Cần bắt đầu lượt mới từ `WATCH` và đọc lại.

**5. WATCH hai khóa mà chỉ một khóa thay đổi thì giao dịch có được commit không?**

Không. Bất kỳ khóa nào trong tập được WATCH bị sửa đều có thể làm `EXEC` hủy hàng đợi.

**6. MULTI/EXEC có tự rollback tất cả lệnh khi một lệnh lỗi thực thi không?**

Không. Redis không cung cấp rollback kiểu SQL cho những lệnh đã thực thi thành công trong hàng đợi.

**7. Tại sao SessionCallback quan trọng trong Spring Data Redis?**

Vì `WATCH`, `MULTI` và `EXEC` phải dùng cùng một kết nối Redis. `SessionCallback` là cơ chế nhóm các thao tác `RedisOperations` trên cùng phiên kết nối.

**8. Nếu timeout xảy ra sau khi gửi EXEC, có thể kết luận giao dịch chắc chắn thất bại không?**

Không. Ứng dụng có thể không nhận được phản hồi dù Redis đã thực thi. Cần thiết kế chống lặp hoặc cơ chế xác minh trạng thái thay vì thử lại một cách mù quáng.

## 16. Ghi nhớ

- **`WATCH` là kiểm soát đồng thời lạc quan trên khóa Redis**: không khóa người ghi khác, nhưng làm `EXEC` hủy giao dịch nếu dữ liệu theo dõi đã thay đổi.
- Thứ tự quan trọng là **`WATCH → đọc → kiểm tra → MULTI → xếp lệnh ghi → EXEC`**.
- **Giao dịch bị hủy do xung đột phải đọc lại từ đầu**. Nên giới hạn số lần thử và theo dõi độ trễ khi nhiều client cạnh tranh.
- Trong Spring Data Redis, dùng **`SessionCallback`** để các thao tác liên quan đến `WATCH/MULTI/EXEC` có cùng kết nối.
- **`EXEC` được chấp nhận** không đồng nghĩa Redis có rollback kiểu SQL cho mọi lỗi thực thi.
- Chọn giữa **lệnh Redis nguyên tử, WATCH và Lua script** theo điều kiện nghiệp vụ, số khóa liên quan, tỉ lệ xung đột và khả năng vận hành.

### Tài liệu tham khảo

- [Redis — Transactions, MULTI/EXEC và WATCH](https://redis.io/docs/latest/develop/using-commands/transactions/).
- [Redis — WATCH](https://redis.io/docs/latest/commands/watch/).
- [Redis — MULTI](https://redis.io/docs/latest/commands/multi/).
- [Redis — EXEC](https://redis.io/docs/latest/commands/exec/).
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
