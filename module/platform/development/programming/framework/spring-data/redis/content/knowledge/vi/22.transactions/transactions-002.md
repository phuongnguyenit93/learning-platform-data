# Thực thi giao dịch qua SessionCallback

Trong **Spring Data Redis**, `SessionCallback` cho phép thực hiện nhiều thao tác Redis trong **cùng một phiên làm việc với kết nối Redis**. Đây là cơ chế đặc biệt quan trọng khi sử dụng giao dịch Redis bằng `MULTI`, `EXEC` và `DISCARD`, vì các lệnh này có trạng thái gắn với **một kết nối**.

Một giao dịch Redis không hoạt động giống transaction của cơ sở dữ liệu quan hệ: `MULTI` bắt đầu hàng đợi lệnh, `EXEC` thực thi những lệnh đã xếp hàng theo thứ tự và không cho lệnh từ client khác chen vào giữa. Nhưng Redis **không tự rollback các thay đổi đã thành công nếu một lệnh bên trong `EXEC` bị lỗi khi chạy**. Vì vậy, dùng `SessionCallback` đúng giúp gói các thao tác vào cùng giao dịch Redis, còn việc đảm bảo nghiệp vụ chính xác vẫn đòi hỏi hiểu rõ đặc tính nguyên tử, lỗi và cạnh tranh.

## 1. Vì sao cần SessionCallback?

Các thao tác gọi qua `RedisTemplate` thường được thực hiện theo từng lần gọi template. Mỗi lời gọi có thể mượn và trả một kết nối từ connection factory hoặc pool. Nếu viết:

```java
redisTemplate.multi();
redisTemplate.opsForValue().set("order:1001:status", "RESERVED");
redisTemplate.opsForSet().add("orders:reserved", "1001");
redisTemplate.exec();
```

thì chỉ nhìn các dòng Java, **không được mặc định** tất cả thao tác đều nằm trên một kết nối Redis. Nếu không có cơ chế ràng buộc kết nối thích hợp, `MULTI` có thể được gửi trên một connection, các lệnh sau chạy trên connection khác hoặc `EXEC` không tìm thấy transaction phù hợp.

`SessionCallback` khắc phục vấn đề ở ranh giới Spring Data Redis: những thao tác thực hiện qua đối tượng `RedisOperations` được cung cấp trong callback được thực thi với **cùng connection/session được ràng buộc cho callback đó**.

Sơ đồ khái niệm:

```text
Ứng dụng Spring
     |
     v
redisTemplate.execute(SessionCallback)
     |
     +-- Redis connection C
     |      |
     |      +-- MULTI
     |      +-- SET order:1001:status RESERVED  (xếp hàng)
     |      +-- SADD orders:reserved 1001       (xếp hàng)
     |      +-- EXEC                           (thực thi hàng đợi)
     |
     v
Kết quả EXEC được chuyển đổi và trả về
```

Ý nghĩa của `SessionCallback` rộng hơn giao dịch: nó giúp gắn một chuỗi thao tác với cùng kết nối khi yêu cầu của Redis cần điều đó. Trong bài này, mục tiêu chính là **thực thi giao dịch `MULTI`/`EXEC`**.

## 2. Redis MULTI/EXEC thực hiện những gì?

Redis transaction có các lệnh cơ bản:

| Lệnh | Vai trò |
|---|---|
| `MULTI` | Bắt đầu chế độ transaction, những lệnh tiếp theo được đưa vào hàng đợi. |
| `EXEC` | Thực thi tuần tự các lệnh đã xếp hàng và trả kết quả của từng lệnh. |
| `DISCARD` | Bỏ hàng đợi, thoát trạng thái transaction trước khi `EXEC`. |
| `WATCH key ...` | Theo dõi khóa để kiểm soát cạnh tranh theo cơ chế optimistic locking. |
| `UNWATCH` | Bỏ theo dõi khóa khi chưa bắt đầu transaction hoặc khi không tiếp tục thao tác. |

Trên Redis CLI, có thể hình dung:

```redis
MULTI
SET order:1001:status RESERVED
SADD orders:reserved 1001
EXEC
```

Phản hồi của Redis khi gửi các lệnh sau `MULTI` thường là `QUEUED`. Chỉ tại `EXEC` các thao tác mới chạy và Redis trả danh sách kết quả. Không nên dựa vào dữ liệu đọc “ngay giữa transaction” như thể các lệnh trước đó đã được thực thi.

### Điều Redis đảm bảo

Trong một Redis server thực thi giao dịch, các lệnh thuộc một `EXEC` được chạy theo thứ tự, không bị lệnh của client khác chen vào giữa. Nếu cần cập nhật một vài cấu trúc dữ liệu cùng lúc, đây là đặc tính có ích.

### Điều Redis không đảm bảo

Redis transaction không cung cấp rollback kiểu SQL sau lỗi runtime của một lệnh. Ví dụ một lệnh có thể lỗi `WRONGTYPE` trong lúc `EXEC`, nhưng những lệnh khác vẫn có thể được thực thi. Vì vậy, “đã chạy `MULTI`/`EXEC`” **không đồng nghĩa với tất cả lệnh thành công hoặc tất cả bị đảo ngược**.

Ngoài ra, hai lệnh `GET` rồi `SET` được gửi trước/sau `MULTI` không tự biến thành phép kiểm tra và cập nhật có điều kiện. Với kịch bản đọc, tính toán rồi ghi, cần `WATCH`, một lệnh Redis có điều kiện hoặc script thích hợp.

## 3. Ví dụ cơ bản với StringRedisTemplate và SessionCallback

Giả sử hệ thống đặt hàng cần:

1. Ghi trạng thái đơn hàng thành `RESERVED`.
2. Thêm ID đơn hàng vào tập `orders:reserved`.
3. Thực hiện cả hai thao tác trong cùng transaction Redis.

Cấu hình Spring Boot có `StringRedisTemplate` dùng serializer chuỗi cho khóa và giá trị:

```java
import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ReservationStore {

    private final StringRedisTemplate redis;

    public ReservationStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> markReserved(String orderId) {
        String statusKey = "order:" + orderId + ":status";
        String reservedSetKey = "orders:reserved";

        return redis.execute(new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings("unchecked")
            public List<Object> execute(RedisOperations operations)
                    throws DataAccessException {

                // Tất cả lệnh dưới đây sử dụng cùng session/connection.
                operations.multi();

                operations.opsForValue().set(statusKey, "RESERVED");
                operations.opsForSet().add(reservedSetKey, orderId);

                // EXEC thực thi các lệnh đã xếp hàng.
                return operations.exec();
            }
        });
    }
}
```

Khi gọi:

```java
List<Object> results = reservationStore.markReserved("1001");
```

logic Redis tương đương:

```text
MULTI
  SET order:1001:status RESERVED
  SADD orders:reserved 1001
EXEC
```

**Lưu ý về kiểu trả về:** `RedisOperations` trong chữ ký `SessionCallback.execute` là kiểu giao diện tổng quát, nên ví dụ sử dụng `@SuppressWarnings` cho các cảnh báo generic/raw type. `StringRedisTemplate` giúp đọc/ghi các khóa và giá trị string. Khi giao dịch hoàn thành, `exec()` trả về danh sách kết quả đã được chuyển đổi theo cơ chế template; chi tiết kiểu của từng phần tử phụ thuộc lệnh, serializer và cấu hình.

### Lý do gọi thao tác qua `operations`

Tất cả thao tác trong callback nên đi qua **đối tượng `RedisOperations` được callback cung cấp**. Không gọi lẫn:

```java
operations.multi();
redis.opsForValue().set(statusKey, "RESERVED"); // Không nên trộn như thế.
operations.exec();
```

vì việc gọi thẳng template bên ngoài chuỗi operations được callback quản lý có thể gây nhầm lẫn về kết nối và ranh giới transaction. Giữ một đường thao tác rõ ràng giúp người đọc và người bảo trì hiểu chính xác lệnh nào nằm trong giao dịch.

## 4. Giá trị trả về khi các lệnh đang được xếp hàng

Trong chế độ `MULTI`, Redis **xếp hàng** thay vì thực thi ngay các lệnh dữ liệu. Vì vậy, mã sau không đúng về mặt ý tưởng:

```java
operations.multi();

Boolean wasAdded = operations.opsForSet()
        .add("orders:reserved", "1001");

// Không dùng wasAdded để quyết định luồng nghiệp vụ ở đây.
if (Boolean.TRUE.equals(wasAdded)) {
    operations.opsForValue().set("order:1001:status", "RESERVED");
}

operations.exec();
```

Khi một lệnh được queue, giá trị trả về trực tiếp qua template có thể là `null`, không phải kết quả thật của lệnh Redis sau `EXEC`. Muốn biết `SADD` có thêm phần tử mới hay không, cần xem kết quả tương ứng **sau `exec()`**.

Ví dụ hợp lý:

```java
List<Object> results = redis.execute(new SessionCallback<List<Object>>() {
    @Override
    public List<Object> execute(RedisOperations operations) {
        operations.multi();

        operations.opsForValue().set("order:1001:status", "RESERVED");
        operations.opsForSet().add("orders:reserved", "1001");

        return operations.exec();
    }
});

if (results == null) {
    throw new IllegalStateException("Transaction did not produce results");
}

// Hai phần tử kết quả ứng với SET và SADD theo thứ tự lệnh
// trong trường hợp transaction được thực thi bình thường.
```

Không nên dựa vào việc phần tử đầu tiên luôn là một kiểu cụ thể khi chưa kiểm tra đường serializer/conversion và phiên bản API đang dùng. Với `StringRedisTemplate`, `SET` và `SADD` có những dạng phản hồi Redis khác nhau; khi cần kết luận nghiệp vụ, hãy xử lý **kết quả của chính lệnh phù hợp** và trạng thái giao dịch.

## 5. SessionCallback đảm bảo phạm vi connection, không tự tạo transaction

`SessionCallback` chỉ thiết lập phạm vi thực thi trên cùng connection/session. Nó **không tự gọi `MULTI` hoặc `EXEC`**.

```java
redis.execute(new SessionCallback<Void>() {
    @Override
    public Void execute(RedisOperations operations) {
        operations.opsForValue().set("a", "1");
        operations.opsForValue().set("b", "2");
        return null;
    }
});
```

Hai lệnh này cùng session nhưng **không phải Redis transaction**, vì không có `operations.multi()` và `operations.exec()`. Nếu một lệnh thành công rồi lệnh tiếp theo thất bại, không có cơ chế giao dịch nào được khai báo để gắn chúng với nhau.

Ba khái niệm cần phân biệt:

| Cơ chế | Ý nghĩa |
|---|---|
| `RedisTemplate.execute(SessionCallback)` | Giữ các thao tác trong callback trên cùng connection/session. |
| `operations.multi()` / `operations.exec()` | Tạo và kết thúc Redis transaction trên connection đó. |
| `@Transactional` của Spring | Ranh giới transaction do Spring quản lý; chỉ ảnh hưởng Redis khi được cấu hình tích hợp tương ứng, và có giới hạn riêng. |

Khi mục tiêu là thao tác Redis rõ ràng, `SessionCallback` với `MULTI`/`EXEC` thường dễ theo dõi hơn việc kỳ vọng một annotation ở service tự điều khiển Redis.

## 6. Thực thi giao dịch có xử lý lỗi và DISCARD

Nếu xảy ra exception **trước khi gửi `EXEC`**, connection có thể đang ở trạng thái transaction với các lệnh đã queue. Khi không muốn tiếp tục, cần gọi `DISCARD` để xóa hàng đợi.

Một mẫu tổ chức luồng:

```java
import java.util.List;

import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

public List<Object> updateTwoKeys(StringRedisTemplate redis) {
    return redis.execute(new SessionCallback<List<Object>>() {
        @Override
        public List<Object> execute(RedisOperations operations) {
            boolean execStarted = false;

            operations.multi();
            try {
                operations.opsForValue().set("workflow:1001:state", "READY");
                operations.opsForValue().set("workflow:1001:owner", "worker-7");

                // Sau điểm này, DISCARD không được xem là rollback.
                execStarted = true;
                return operations.exec();
            } catch (RuntimeException original) {
                if (!execStarted) {
                    try {
                        operations.discard();
                    } catch (RuntimeException discardFailure) {
                        original.addSuppressed(discardFailure);
                    }
                }
                throw original;
            }
        }
    });
}
```

Mẫu trên thể hiện trách nhiệm **hủy các lệnh còn queue khi phát hiện lỗi trước `EXEC`**. Nếu `EXEC` đã bắt đầu được gửi và kết nối bị đứt, kết quả có thể **không xác định từ phía client**: Redis có thể đã thực thi một phần hoặc toàn bộ logic của giao dịch, trong khi ứng dụng không nhận được phản hồi. Gọi `DISCARD` sau đó không phải cách hoàn tác.

**Không retry một transaction không idempotent theo kiểu “gửi lại toàn bộ” chỉ vì client không nhận được kết quả.** Với lệnh tăng số dư hoặc đếm lượt, retry có thể tạo tác động hai lần. Thiết kế idempotency key hoặc kiểm tra trạng thái đích là cần thiết cho nghiệp vụ cho phép retry.

Với lỗi xảy ra ngay khi gọi `operations.multi()`, giao dịch chưa chắc đã được mở; không cần và cũng không nên coi `DISCARD` là thao tác dọn bắt buộc bất kể trạng thái. Các đường lỗi bất định cần xử lý ở tầng service, không dựa vào một giả định về trạng thái connection.

### EXEC không có rollback cho lỗi runtime

Giả sử:

```redis
SET counter "not-a-number"
MULTI
INCR counter
SET workflow:1001:status COMPLETE
EXEC
```

Trong giao dịch này, `INCR counter` gặp lỗi vì giá trị không phải số, nhưng `SET workflow:1001:status COMPLETE` vẫn có thể được thực thi. Không thể suy luận “`EXEC` trả một lỗi nên mọi lệnh đều không có tác dụng”. Ứng dụng cần kiểm soát dữ liệu đầu vào, kiểm tra kết quả và chọn cơ chế phù hợp nếu nghiệp vụ yêu cầu phép cập nhật có điều kiện chặt chẽ hơn.

## 7. Đọc dữ liệu, tính toán rồi ghi: dùng WATCH

Một tình huống phổ biến: chỉ trừ tồn kho khi còn đủ hàng.

Giả sử khóa:

```text
inventory:sku-123:available = "10"
```

Hai client cùng muốn trừ 7. Nếu chỉ:

```text
GET inventory:sku-123:available
tính toán
MULTI
SET inventory:sku-123:available giá trị mới
EXEC
```

thì cả hai client có thể đã đọc cùng giá trị `10` trước khi vào transaction. Cả hai đặt kết quả thành `3`, dù tổng cộng yêu cầu 14 đơn vị. `MULTI`/`EXEC` bảo vệ nhóm lệnh ghi khỏi bị chen ngang, nhưng **không tự bảo vệ dữ liệu đã đọc trước `MULTI`**.

Cơ chế `WATCH` cho phép theo dõi khóa. Nếu khóa bị client khác thay đổi sau `WATCH` và trước `EXEC`, transaction sẽ bị hủy theo cơ chế optimistic locking.

### Ví dụ Spring Data Redis với WATCH và SessionCallback

```java
import java.util.List;

import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class InventoryStore {

    private final StringRedisTemplate redis;

    public InventoryStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean reserveUnits(String sku, long quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        String key = "inventory:" + sku + ":available";

        Boolean committed = redis.execute(new SessionCallback<Boolean>() {
            @Override
            public Boolean execute(RedisOperations operations) {
                operations.watch(key);

                try {
                    Object rawValue = operations.opsForValue().get(key);
                    if (!(rawValue instanceof String current)) {
                        // Không có dữ liệu hoặc representation không hợp lệ.
                        operations.unwatch();
                        return false;
                    }

                    long available = Long.parseLong(current);
                    if (available < quantity) {
                        operations.unwatch();
                        return false;
                    }

                    operations.multi();
                    operations.opsForValue()
                            .set(key, Long.toString(available - quantity));

                    // Kết quả EXEC có thể rỗng/null khi WATCH bị xung đột.
                    List<Object> execResults = operations.exec();
                    return execResults != null && !execResults.isEmpty();
                } catch (RuntimeException ex) {
                    // Nếu chưa MULTI hoặc EXEC đã kết thúc thì UNWATCH;
                    // nếu đang queue, DISCARD là trách nhiệm đường lỗi.
                    // Chính sách cleanup thực tế cần theo dõi trạng thái
                    // từng giai đoạn, không được coi UNWATCH là rollback.
                    throw ex;
                }
            }
        });

        return Boolean.TRUE.equals(committed);
    }
}
```

Ở luồng thành công:

1. `WATCH` bắt đầu theo dõi khóa tồn kho.
2. `GET` đọc số lượng hiện tại **trước `MULTI`**.
3. Ứng dụng kiểm tra đủ hàng rồi tính giá trị mới.
4. `MULTI` queue `SET` với số lượng đã trừ.
5. `EXEC` chỉ thành công nếu điều kiện WATCH không bị vi phạm. Khi có client khác thay đổi khóa, kết quả sẽ cho thấy giao dịch không được commit.

Lưu ý: ví dụ nhấn mạnh **thứ tự WATCH → READ → MULTI → WRITE → EXEC**. Với triển khai production, hãy bổ sung quản lý cleanup theo giai đoạn và retry có giới hạn như phần tiếp theo.

### Phiên bản quản lý trạng thái rõ ràng hơn

Khi callback có nhiều nhánh lỗi, nên mô hình hóa trạng thái của giao dịch để không gọi `UNWATCH` trong lúc còn lệnh đang queue hoặc gọi `DISCARD` sau `EXEC` như một thao tác rollback:

```java
public boolean reserveUnitsSafely(String sku, long quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }

    String key = "inventory:" + sku + ":available";

    Boolean result = redis.execute(new SessionCallback<Boolean>() {
        @Override
        public Boolean execute(RedisOperations operations) {
            boolean watched = false;
            boolean queued = false;

            try {
                operations.watch(key);
                watched = true;

                String current = (String) operations.opsForValue().get(key);
                if (current == null) {
                    operations.unwatch();
                    watched = false;
                    return false;
                }

                long available = Long.parseLong(current);
                if (available < quantity) {
                    operations.unwatch();
                    watched = false;
                    return false;
                }

                operations.multi();
                queued = true;

                operations.opsForValue()
                        .set(key, Long.toString(available - quantity));

                // Từ đây không còn suy luận được rằng DISCARD
                // có thể hoàn tác nếu kết nối bị lỗi ở EXEC.
                queued = false;
                watched = false;
                List<Object> results = operations.exec();

                // Giao dịch có một lệnh SET, kết quả bình thường
                // sẽ là một danh sách kết quả không rỗng.
                return results != null && !results.isEmpty();
            } catch (RuntimeException original) {
                try {
                    if (queued) {
                        operations.discard();
                    } else if (watched) {
                        operations.unwatch();
                    }
                } catch (RuntimeException cleanupError) {
                    original.addSuppressed(cleanupError);
                }
                throw original;
            }
        }
    });

    return Boolean.TRUE.equals(result);
}
```

Ví dụ này cố ý **không tự retry** khi `EXEC` trả lỗi hay client mất kết nối. Retry chỉ nên thực hiện khi phân biệt được xung đột optimistic locking với lỗi hạ tầng và biết chắc hành động có thể gửi lại an toàn. Đối với tồn kho/đặt hàng thực, cần cân nhắc idempotency, reservation ID, hạn giữ hàng và nguồn dữ liệu xác thực, ngoài kiểm tra số còn lại.

### WATCH không phải một Redis lock

`WATCH` không khóa Redis key để ngăn các client khác sửa. Nó chỉ phát hiện xung đột vào lúc `EXEC`. Hai client có thể cùng đọc giá trị; một client commit trước, client còn lại bị abort và cần tính lại nếu retry. Đây là **optimistic concurrency control**.

Giữa các lần retry, nên có giới hạn số lần, backoff ngắn có jitter và cơ chế phân biệt “hết hàng” với “bị thay đổi cạnh tranh”. Một khóa nóng với quá nhiều client đồng thời có thể tạo tỷ lệ xung đột cao; trong trường hợp này cần cân nhắc cách thiết kế khác.

## 8. So sánh MULTI/EXEC, WATCH và Redis Lua

Các cơ chế dưới đây cùng liên quan đến cập nhật nhiều dữ liệu, nhưng giải quyết những vấn đề khác nhau.

| Cơ chế | Làm được gì? | Giới hạn nổi bật |
|---|---|---|
| `MULTI` + `EXEC` trong `SessionCallback` | Queue và thực thi các lệnh Redis theo thứ tự không bị xen giữa | Không đọc kết quả lệnh queue để quyết định lệnh tiếp theo; không rollback lỗi runtime |
| `WATCH` + `MULTI` + `EXEC` | Đọc trước rồi thực hiện cập nhật có kiểm tra xung đột | Cần xử lý abort/retry; xung đột nhiều khi khóa nóng |
| Lua script với `EVAL`/`EVALSHA` | Kiểm tra điều kiện và cập nhật trên Redis server trong một lần thực thi script | Cần kiểm soát tác dụng phụ khi lỗi; bị ràng buộc bởi key access/hash slot trên Cluster |
| Lệnh Redis nguyên tử chuyên biệt | Ví dụ `INCRBY`, `SET NX PX`, `HINCRBY` | Phù hợp với một số thao tác hẹp, không thay mọi workflow |

### Khi nào dùng script thay vì SessionCallback?

Ví dụ kiểm tra tồn kho và trừ số lượng yêu cầu “chỉ cập nhật nếu đủ” rất phù hợp với **một thao tác có điều kiện trên server**, dùng script Lua hoặc chức năng tương đương phù hợp Redis.

Một script minh họa:

```lua
-- KEYS[1]: inventory key
-- ARGV[1]: quantity to reserve
local qty = tonumber(ARGV[1])
if not qty or qty <= 0 then
    return redis.error_reply("INVALID_QUANTITY")
end

local current = tonumber(redis.call("GET", KEYS[1]))
if not current then
    return 0
end

if current < qty then
    return 0
end

redis.call("DECRBY", KEYS[1], qty)
return 1
```

Script kiểm tra và trừ tồn kho trong cùng lần thực thi trên Redis, không có cửa sổ đọc/ghi ở client giữa hai bước. Tuy nhiên, Redis script cũng không có rollback tự động cho mọi lỗi sau khi đã sửa dữ liệu; hãy kiểm tra điều kiện và kiểu dữ liệu trước khi thực hiện thao tác có tác dụng phụ.

Với nhiều key trên Redis Cluster, cần đảm bảo những khóa truy cập trong script tuân thủ giới hạn cùng hash slot. Tránh phát triển script chạm nhiều key có namespace phân tán mà chưa xét ràng buộc cluster.

**SessionCallback vẫn phù hợp** khi muốn nhóm những lệnh đơn giản, dùng `WATCH` để optimistic concurrency hoặc cần các thao tác Spring Data Redis trên cùng connection. Không có một cơ chế phù hợp cho mọi bài toán.

## 9. @Transactional của Spring có thay SessionCallback được không?

Spring hỗ trợ `@Transactional` và `PlatformTransactionManager` cho nhiều nguồn tài nguyên. Nhưng RedisTemplate **không tự tham gia transaction Spring chỉ vì bạn đặt `@Transactional` trên method**.

Spring Data Redis cung cấp cơ chế transaction support cho `RedisTemplate`, có thể được bật:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;

@Configuration
public class RedisTransactionConfig {

    @Bean
    public RedisTemplate<String, String> transactionAwareRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, String> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);
        template.setKeySerializer(
                org.springframework.data.redis.serializer.StringRedisSerializer
                        .UTF_8);
        template.setValueSerializer(
                org.springframework.data.redis.serializer.StringRedisSerializer
                        .UTF_8);

        template.setEnableTransactionSupport(true);
        template.afterPropertiesSet();
        return template;
    }
}
```

Đoạn trên minh họa việc bật transaction support; trong dự án thực tế còn phải cân nhắc bean template hiện có, serializer cho hash và cấu hình transaction manager. Không mặc định chỉ riêng đoạn cấu hình này đã thiết lập đầy đủ mọi phối hợp giữa Redis và các nguồn tài nguyên khác.

Một số khác biệt:

- `SessionCallback` chủ động gọi `MULTI`/`EXEC` trong phạm vi callback.
- Transaction management của Spring có thể gắn Redis connection vào transaction hiện tại khi được bật; các thao tác ghi Redis được queue theo ngữ nghĩa phù hợp.
- Trong trường hợp transaction Spring, thao tác đọc có thể dùng **kết nối khác** với connection đang queue lệnh ghi. Vì thế, đừng kỳ vọng đọc lại ngay trong method sẽ luôn thấy giá trị vừa queue.
- Một transaction của Spring liên quan đồng thời tới JDBC và Redis **không tự động trở thành distributed transaction có commit nguyên tử trên cả hai hệ thống**. Nếu JDBC commit thành công nhưng cập nhật Redis lỗi, cần thiết kế tính nhất quán và cơ chế khôi phục như outbox/event hoặc quy trình bù phù hợp.

Dùng `@Transactional` nên xuất phát từ kiến trúc quản lý transaction của ứng dụng. Dùng `SessionCallback` khi muốn thể hiện rõ ranh giới một giao dịch Redis cụ thể.

### Vì sao không nên lồng transaction tùy tiện?

Ví dụ, một method đã bật Redis transaction support của Spring mà lại tự gọi `operations.multi()` bên trong `SessionCallback` có thể tạo tương tác khó đoán về connection đang bind và trạng thái transaction. Nếu không có yêu cầu rõ, chọn **một cơ chế quản lý giao dịch cho cùng đường thao tác**, tránh để cả Spring transaction boundary và `MULTI` thủ công cùng điều khiển một kết nối mà chưa thiết kế.

## 10. Giao dịch Redis trên Cluster và khi dùng pipeline

Trên Redis Cluster, việc thực hiện lệnh nhiều khóa có thể chịu giới hạn về **hash slot**. Không thể giả định một `MULTI`/`EXEC` trải qua bất kỳ khóa nào ở các master node khác nhau. Nếu transaction cần nhiều khóa, hãy thiết kế để chúng nằm cùng slot, hoặc thay đổi ranh giới dữ liệu/transaction.

Redis dùng **hash tag** trong tên khóa để định hướng slot cho các khóa liên quan:

```text
order:{1001}:status
order:{1001}:items
order:{1001}:reservation
```

Những khóa này chia sẻ phần hash tag `1001`, nên được ánh xạ tới cùng hash slot trong Redis Cluster. Ví dụ:

```java
String keyStatus = "order:{1001}:status";
String keyItems = "order:{1001}:items";
```

Hash tag giúp bố trí khóa, nhưng không tự tăng tính nhất quán nghiệp vụ. Cũng không nên đưa mọi khóa toàn hệ thống vào một hash tag chung: làm vậy có thể dồn tải vào một slot/node.

### Pipeline khác transaction thế nào?

**Pipelining** chủ yếu giảm số lần chờ phản hồi qua mạng bằng việc gửi nhiều lệnh liên tiếp. Nó không mặc định tạo ranh giới nguyên tử như `MULTI`/`EXEC`.

| | SessionCallback + MULTI/EXEC | Pipelining |
|---|---|---|
| Mục tiêu | Giao dịch nhóm lệnh trên một kết nối | Giảm round-trip |
| Redis queue trước khi chạy | Có, giữa MULTI và EXEC | Không nhất thiết |
| Client khác chen giữa các lệnh trong nhóm | Không trong thời gian EXEC chạy | Có thể |
| Có kết quả từng lệnh | Có từ EXEC | Có sau khi pipeline trả kết quả |
| Có rollback SQL | Không | Không |

Spring Data Redis có API `executePipelined(...)` cho pipeline. Không dùng `executePipelined` thay `SessionCallback` khi nghiệp vụ thực sự cần thao tác transaction.

## 11. Đảm bảo cùng connection và chú ý RedisTemplate

`SessionCallback` hoạt động qua `RedisTemplate.execute(SessionCallback<T>)`. Đối tượng `RedisOperations` bên trong callback là đường dùng các thao tác theo cùng connection. Khi dùng template với serializer tùy chỉnh, kết quả trả về từ `exec()` phụ thuộc cách template chuyển đổi response.

Các điểm thường gây nhầm:

1. **Gọi `multi()` rồi thao tác template bên ngoài callback:** chưa chắc cùng connection.
2. **Gọi `exec()` ở ngoài callback:** không bảo đảm kết thúc transaction đã được mở trong callback khác.
3. **Dùng nhiều RedisTemplate trỏ tới cùng Redis:** không đồng nghĩa mọi lời gọi được ràng buộc cùng một session.
4. **Đọc kết quả trong thời gian command đang queue:** kết quả thực chưa có cho đến EXEC.
5. **Lẫn serializer:** ghi qua `StringRedisTemplate` nhưng đọc cùng key bằng template khác có thể gặp representation không tương thích.
6. **Trộn Spring-managed transaction và manual MULTI:** cần hiểu transaction support đã bật hay chưa.
7. **Xem callback là transaction tự động:** callback không gọi MULTI/EXEC thay bạn.

Khi thiết kế API service, đặt transaction vào một method có phạm vi nhỏ, tên phản ánh hành động nghiệp vụ, và trả về kết quả có ý nghĩa rõ ràng thay vì phát tán `List<Object>` ra tầng controller.

## 12. Một service trả kết quả có ý nghĩa nghiệp vụ

Ví dụ đánh dấu đơn hàng là đã chuẩn bị, đồng thời thêm ID vào Redis Set để worker tìm thấy. Những lệnh này cần đi cùng nhau trong Redis, nhưng không dựa vào giá trị return của lệnh queue.

```java
import java.util.List;

import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderQueueStore {

    private final StringRedisTemplate redis;

    public OrderQueueStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void enqueueReady(String orderId) {
        String stateKey = "order:{" + orderId + "}:state";
        String queueKey = "order:{" + orderId + "}:ready";

        List<Object> results =
                redis.execute(new SessionCallback<List<Object>>() {
                    @Override
                    public List<Object> execute(RedisOperations operations) {
                        operations.multi();

                        operations.opsForValue().set(stateKey, "READY");
                        operations.opsForSet().add(queueKey, orderId);

                        return operations.exec();
                    }
                });

        if (results == null || results.size() != 2) {
            throw new IllegalStateException(
                    "Redis transaction was not confirmed");
        }
    }
}
```

Trong ví dụ, hai khóa dùng chung hash tag của một đơn hàng nên phù hợp hơn khi deploy trên Redis Cluster. `Set` ở đây là tập gắn với đơn hàng, không phải hàng đợi toàn cục. Nếu yêu cầu worker xử lý theo thứ tự, chống mất message và ack/retry, cần một cơ chế queue thích hợp như Redis Streams hoặc hệ thống message broker; không nên xem `SADD` là hàng đợi đáng tin cậy chỉ vì nó chạy trong transaction.

Giá trị `results.size() == 2` chỉ cho biết số phản hồi dự kiến của transaction trong đường thực thi bình thường. Để xác nhận **kết quả của mỗi lệnh**, cần xem nội dung từng phần tử, xử lý error response và điều kiện nghiệp vụ. Với lỗi kết nối trong lúc `EXEC`, ứng dụng không thể kết luận chắc chắn transaction chưa chạy nếu không có cơ chế kiểm tra bổ sung.

## 13. Ví dụ chống race với WATCH: giữ quyền sở hữu một trạng thái

Giả sử tài nguyên có khóa `job:17:state`, trạng thái ban đầu `NEW`. Hai worker chỉ được chuyển sang `RUNNING` khi trạng thái vẫn là `NEW`.

Luồng cần thực hiện:

```text
Worker A                               Worker B
   |                                     |
WATCH job:17:state                    WATCH job:17:state
GET -> NEW                            GET -> NEW
   |                                     |
MULTI                                  MULTI
SET RUNNING                            SET RUNNING
   |                                     |
EXEC -> thành công                     EXEC -> abort do key đổi
   |                                     |
Worker A nhận job                     Worker B không được nhận job
```

Thực tế thứ tự có thể đảo ngược; mục đích là **chỉ transaction không xung đột được commit**.

```java
public boolean claimJob(String jobId) {
    String stateKey = "job:" + jobId + ":state";

    Boolean claimed = redis.execute(new SessionCallback<Boolean>() {
        @Override
        public Boolean execute(RedisOperations operations) {
            operations.watch(stateKey);

            String current =
                    (String) operations.opsForValue().get(stateKey);
            if (!"NEW".equals(current)) {
                operations.unwatch();
                return false;
            }

            operations.multi();
            operations.opsForValue().set(stateKey, "RUNNING");
            List<Object> results = operations.exec();

            return results != null && !results.isEmpty();
        }
    });

    return Boolean.TRUE.equals(claimed);
}
```

Ví dụ minh họa `WATCH` cho trạng thái Redis. Trong production, callback vẫn cần quy trình cleanup trước EXEC khi có exception, trạng thái `RUNNING` nên gắn owner/lease, và worker phải có phương án khôi phục khi nhận job rồi chết trước khi xử lý. Nếu hệ thống cần queue phân tán mạnh về độ tin cậy, Redis Streams với consumer group và chính sách xử lý lại thường rõ ràng hơn một khóa trạng thái tự viết.

## 14. Giao dịch không thay thế ranh giới nghiệp vụ và tính bền vững

Một số yêu cầu nằm ngoài phạm vi của `SessionCallback`:

### 14.1. Redis transaction không bao phủ tài nguyên ngoài Redis

Một thao tác có thể cần vừa ghi database quan hệ, vừa cập nhật Redis:

```text
JDBC: INSERT orders(...)
Redis: SET order:1001:status CREATED
```

Redis `MULTI`/`EXEC` không bảo đảm nếu JDBC commit rồi Redis thất bại thì cả hai cùng rollback. Thiết kế thường dùng nguồn dữ liệu có tính nhất quán phù hợp làm nguồn sự thật, rồi đồng bộ Redis qua outbox/event, retry idempotent và đối soát.

### 14.2. Chạy thành công chưa chắc đã bền tuyệt đối sau sự cố

Tính bền của Redis phụ thuộc cấu hình persistence (RDB/AOF), replication và failover. Một `EXEC` thành công không tự nâng Redis thành hệ thống đảm bảo dữ liệu được nhân bản và fsync theo yêu cầu độ bền của từng nghiệp vụ. Với dữ liệu tài chính hoặc tồn kho, cần xác định vai trò Redis và nơi giữ sự thật cuối cùng.

### 14.3. Không thể đọc kết quả của lệnh queue để quyết định câu lệnh tiếp theo

Trong `MULTI`, kết quả các lệnh được trả sau `EXEC`. Nếu cần thao tác “đọc, kiểm tra, ghi” trên server trong một bước nguyên tử, hãy cân nhắc script hoặc các lệnh điều kiện của Redis; `WATCH` phù hợp nếu chấp nhận retry do xung đột.

### 14.4. Error và retry có thể gây tác dụng lặp

Nếu kết nối đứt đúng lúc gửi `EXEC`, client có thể không biết kết quả. Với `INCRBY` hay `LPUSH`, gửi lại có thể áp dụng thao tác hai lần. Nên gắn ID yêu cầu và kiểm soát idempotency ở ranh giới nghiệp vụ.

## 15. Cách quan sát giao dịch SessionCallback

Khi một endpoint gọi transaction Redis nhiều lần hoặc có latency cao, cần phân biệt:

- **Độ trễ client/connection:** thời gian lấy connection, chờ mạng, serialize/deserialize.
- **Thời gian thực thi tại Redis:** Redis xử lý các lệnh của `EXEC`.
- **Tỷ lệ xung đột WATCH:** các transaction bị hủy và phải retry.
- **Tỷ lệ lỗi lệnh:** một hay nhiều phản hồi trong transaction bị lỗi.
- **Độ dài giao dịch:** số lệnh được queue; giao dịch quá nhiều lệnh có thể tăng thời gian Redis bị chiếm xử lý nhóm lệnh.
- **Tác động tới dữ liệu:** số request bị retry hoặc không biết kết quả khi mất kết nối.

Có thể theo dõi các thống kê tổng thể:

```bash
redis-cli INFO commandstats
redis-cli INFO stats
redis-cli SLOWLOG GET 10
```

`INFO commandstats` là số liệu toàn instance, không có sẵn tương quan với một request Spring cụ thể. `SLOWLOG` chỉ ghi những lệnh vượt ngưỡng thời gian xử lý phía Redis; nó không bao gồm thời gian mạng và không nhất thiết biểu diễn toàn bộ độ trễ của transaction ở phía ứng dụng.

Ở ứng dụng, có thể đặt timer quanh lời gọi `redis.execute(SessionCallback)`, bổ sung metric theo loại nghiệp vụ, outcome `committed`/`conflict`/`error`/`unknown` và các phép retry. Tránh ghi log giá trị khóa chứa dữ liệu nhạy cảm.

## 16. Những sai lầm dễ gặp

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Gọi `multi()`, thao tác và `exec()` rời rạc không giữ connection | Không chắc lệnh nằm cùng transaction | Dùng `execute(SessionCallback)` với một `RedisOperations` |
| Tưởng `SessionCallback` tự tạo transaction | Hai lệnh vẫn chạy độc lập | Gọi rõ `multi()` và `exec()` khi cần |
| Dựa vào return của `set(...)` trong lúc MULTI | Giá trị lệnh queue chưa phải kết quả thật | Đọc danh sách trả từ `exec()` |
| Xem EXEC như SQL rollback | Một lệnh runtime lỗi nhưng lệnh khác vẫn có thể chạy | Kiểm tra trước điều kiện, xử lý kết quả và thiết kế idempotency |
| Đọc trước MULTI rồi SET theo giá trị đọc | Race/lost update | Dùng WATCH hoặc thao tác nguyên tử có điều kiện |
| Retry ngay sau lỗi kết nối EXEC | Có thể tạo tác động lặp | Phân loại outcome không xác định và kiểm tra idempotency |
| Dùng các khóa ở nhiều slot trên Cluster | Transaction nhiều khóa có thể thất bại | Thiết kế key hash tag phù hợp |
| Bật `@Transactional` và giả định Redis tự tham gia | Redis writes có thể không được queue như kỳ vọng | Hiểu và cấu hình transaction support |
| Trộn JDBC và Redis transaction rồi nghĩ commit nguyên tử | Dữ liệu hai hệ thống có thể lệch | Outbox/event và cơ chế phục hồi |
| Dùng transaction để tạo queue mà không có ack/lease | Worker lỗi làm mất trạng thái xử lý | Chọn mô hình queue/stream phù hợp |

## 17. Quy trình chọn cách thực thi

```text
Có nhiều thao tác Redis cần xử lý cùng nhau?
                    |
            +-------+-------+
            |               |
           Không            Có
            |               |
            v               v
    Dùng lệnh Redis    Có cần kết quả một lệnh
    nguyên tử đơn lẻ   để quyết định lệnh tiếp?
                            |
                       +----+----+
                       |         |
                      Không      Có
                       |         |
                       v         v
                  SessionCallback  Cân nhắc WATCH
                  + MULTI/EXEC     hoặc Lua/điều kiện
                       |                 |
                       +--------+--------+
                                |
                                v
                     Có nhiều khóa trên Cluster?
                                |
                           +----+----+
                           |         |
                          Có        Không
                           |         |
                           v         |
                    Kiểm tra cùng  |
                    hash slot      |
                           +---------+
                                |
                                v
                     Xác định kết quả,
                     lỗi, retry, idempotency
```

**Điểm cốt lõi:** `SessionCallback` cung cấp phạm vi kết nối nhất quán để điều khiển giao dịch Redis bằng `MULTI`/`EXEC`. Hãy đặt tất cả thao tác của transaction vào cùng callback, đọc kết quả từ `exec()` và dùng `WATCH` khi cần kiểm soát thay đổi sau khi đọc. Đừng nhầm tính nguyên tử khi thực thi nhóm lệnh với khả năng rollback kiểu SQL; tính đúng đắn của nghiệp vụ còn phụ thuộc xử lý xung đột, lỗi kết nối, idempotency và ranh giới dữ liệu bên ngoài Redis.

