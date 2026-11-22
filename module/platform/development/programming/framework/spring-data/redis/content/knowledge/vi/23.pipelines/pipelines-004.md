# Dùng executePipelined với SessionCallback

Khi một ứng dụng Spring cần đọc hoặc ghi nhiều khóa Redis, cách gọi từng lệnh và chờ từng phản hồi có thể tạo ra rất nhiều lần chờ mạng. **Pipelining** cho phép gửi một nhóm lệnh Redis liên tiếp rồi nhận kết quả sau khi các lệnh đã được gửi, nhờ đó giảm chi phí *round-trip* trong các tác vụ xử lý theo lô.

Spring Data Redis cung cấp `RedisTemplate.executePipelined(...)`. Khi sử dụng biến thể nhận **`SessionCallback`**, ứng dụng có thể xây dựng nhóm thao tác bằng API cấp cao `RedisOperations` trong cùng một phiên làm việc. Đây là cách thuận tiện để dùng các thao tác như `opsForValue()`, `opsForHash()` và `opsForSet()` mà vẫn có phạm vi pipeline rõ ràng.

Điểm quan trọng nhất: **`executePipelined` gom việc gửi và nhận phản hồi, nhưng không tự tạo một giao dịch nguyên tử**. Các lệnh có thể thành công hoặc thất bại riêng; kết quả của một lệnh chưa sẵn sàng để quyết định lệnh kế tiếp ngay bên trong callback.

## 1. Vì sao cần pipeline?

Giả sử một API cần đọc 300 bản ghi trạng thái trong Redis:

```java
for (String key : keys) {
    String value = stringRedisTemplate.opsForValue().get(key);
    // Xử lý từng kết quả ngay tại đây.
}
```

Với kiểu gọi tuần tự, client phải thực hiện nhiều lần gửi lệnh và chờ phản hồi:

```text
Ứng dụng                             Redis
   | -------- GET key:1 ------------> |
   | <------- value:1 --------------- |
   | -------- GET key:2 ------------> |
   | <------- value:2 --------------- |
   | -------- GET key:3 ------------> |
   | <------- value:3 --------------- |
   |                ...                |
```

Nếu chi phí một vòng đi-về mạng là khoảng 1 ms, 300 lần chờ riêng có thể tạo ra khoảng 300 ms chi phí chờ trong một mô hình đơn giản, chưa tính xử lý tại Redis, serialization, connection pool và tác vụ ứng dụng. Con số này **chỉ là ví dụ trực giác**, không phải phép dự báo độ trễ thực tế.

Pipeline thay đổi cách giao tiếp:

```text
Ứng dụng                             Redis
   | -------- GET key:1 ------------> |
   | -------- GET key:2 ------------> |
   | -------- GET key:3 ------------> |
   |                ...                |
   | <------- value:1 --------------- |
   | <------- value:2 --------------- |
   | <------- value:3 --------------- |
   |                ...                |
```

Client không cần chờ kết quả của từng lệnh trước khi gửi lệnh kế tiếp. Nhờ vậy, pipeline có thể cải thiện đáng kể tổng thời gian khi xử lý nhiều lệnh độc lập, đặc biệt nếu độ trễ mạng đáng kể.

Tuy nhiên:

- Redis vẫn phải **thực thi các lệnh**; pipeline không biến 300 `GET` thành một `GET`.
- Dữ liệu phản hồi vẫn cần truyền qua mạng và chuyển đổi kiểu.
- Pipeline quá lớn có thể tiêu thụ nhiều bộ nhớ ở cả client lẫn Redis.
- Nếu lệnh sau **phải dùng kết quả lệnh trước để quyết định**, không thể viết một pipeline thuần như thể kết quả đã có ngay.

## 2. Vai trò của SessionCallback trong executePipelined

Spring Data Redis có hai biến thể thường gặp:

```java
redisTemplate.executePipelined(RedisCallback<?> callback);
redisTemplate.executePipelined(SessionCallback<?> callback);
```

Cả hai đều tạo phạm vi pipeline, nhưng cách biểu đạt thao tác khác nhau:

| Cách gọi | API trong callback | Thích hợp khi |
|---|---|---|
| `executePipelined(RedisCallback)` | `RedisConnection` ở mức thấp | Cần điều khiển lệnh/serialization trực tiếp |
| `executePipelined(SessionCallback)` | `RedisOperations` ở mức template | Muốn dùng `opsForValue()`, `opsForHash()`, `opsForSet()` và serializer đã cấu hình |

`SessionCallback` giữ các thao tác của callback trong cùng một session/kết nối theo cơ chế Spring Data Redis. Khi pipeline đang mở, những lệnh thực thi thông qua `RedisOperations` được đưa vào luồng pipeline.

Mô hình khái niệm:

```text
StringRedisTemplate.executePipelined(SessionCallback)
                 |
                 v
       Mở pipeline cho session
                 |
                 v
       Callback nhận RedisOperations
                 |
       +---------+----------+
       |         |          |
       v         v          v
     GET A     GET B      GET C
       |         |          |
       +---------+----------+
                 |
                 v
       Callback phải return null
                 |
                 v
       Flush/nhận phản hồi pipeline
                 |
                 v
       Deserialization và chuyển đổi kết quả
                 |
                 v
              List<Object>
```

### Quy tắc về giá trị trả về

**Callback truyền cho `executePipelined` phải trả về `null`.** Kết quả của các lệnh pipeline được Spring Data Redis gom lại và trả về **bởi chính `executePipelined`**, không phải bằng giá trị trả về của `SessionCallback.execute(...)`.

```java
List<Object> replies = redisTemplate.executePipelined(
        new SessionCallback<Object>() {
            @Override
            public Object execute(RedisOperations operations) {
                operations.opsForValue().get("profile:1");
                operations.opsForValue().get("profile:2");

                // Bắt buộc: không trả về một value tự tính ở đây.
                return null;
            }
        });
```

Nếu callback trả về một giá trị khác `null`, API pipeline có thể từ chối lời gọi bằng exception vì giá trị đó xung đột với cơ chế gom kết quả. Không trả về một `List` tự tạo từ các lệnh đã queue.

## 3. Ví dụ hoàn chỉnh: đọc hàng loạt bằng StringRedisTemplate

Giả sử ứng dụng quản lý trạng thái xử lý của nhiều đơn hàng. Mỗi trạng thái là một string value tại các khóa:

```text
order:1001:status -> "PAID"
order:1002:status -> "CREATED"
order:1003:status -> "SHIPPED"
```

Ta cần đọc 100–500 khóa cho một màn hình quản trị. Vì các lần `GET` độc lập với nhau, đây là trường hợp phù hợp để dùng pipeline.

### 3.1. Service dùng executePipelined(SessionCallback)

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStatusReader {

    private final StringRedisTemplate redis;

    public OrderStatusReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> loadStatuses(List<String> orderIds) {
        if (orderIds.isEmpty()) {
            return List.of();
        }

        List<Object> replies = redis.executePipelined(
                new SessionCallback<Object>() {
                    @Override
                    public Object execute(RedisOperations operations)
                            throws DataAccessException {

                        for (String orderId : orderIds) {
                            String key = "order:" + orderId + ":status";
                            operations.opsForValue().get(key);
                        }

                        // Kết quả GET sẽ được tập hợp sau khi callback kết thúc.
                        return null;
                    }
                });

        if (replies.size() != orderIds.size()) {
            throw new IllegalStateException(
                    "Unexpected number of Redis pipeline replies");
        }

        List<String> statuses = new ArrayList<>(replies.size());
        for (Object reply : replies) {
            // StringRedisTemplate dùng string value serializer.
            // Key chưa tồn tại có thể cho kết quả null.
            statuses.add(reply == null ? null : (String) reply);
        }
        return statuses;
    }
}
```

Ví dụ sử dụng:

```java
List<String> statuses = reader.loadStatuses(
        List.of("1001", "1002", "1003"));

// statuses[0] tương ứng order:1001:status
// statuses[1] tương ứng order:1002:status
// statuses[2] tương ứng order:1003:status
```

**Điểm cần hiểu trong ví dụ:**

1. Tất cả lệnh được phát ra qua `operations` do callback nhận được.
2. Không có `GET` nào được dùng để quyết định lệnh tiếp theo.
3. Callback trả về `null`.
4. Lời gọi bên ngoài `redis.executePipelined(...)` nhận `List<Object>`.
5. Kết quả được xử lý **theo thứ tự lệnh đã xếp**, nên phần tử thứ `i` ứng với ID thứ `i`.
6. Một khóa không tồn tại có thể trả `null`; đừng dùng `List.copyOf(replies)` nếu cần giữ các phần tử `null` vì `List.copyOf` không chấp nhận `null`.

Trong ứng dụng thực tế, danh sách ID cần được giới hạn độ dài, xác thực theo phạm vi quyền truy cập và xử lý quy tắc tên khóa nhất quán. Nếu muốn trả `Map<orderId, status>`, có thể ghép từng ID với phản hồi cùng chỉ số. Khi ID lặp lại, `Map` sẽ không giữ được các vị trí trùng; hãy quyết định khử trùng lặp trước khi queue hoặc trả một danh sách tương ứng đầu vào.

### 3.2. Vì sao không lấy kết quả trực tiếp trong callback?

Cách sau không phù hợp:

```java
redis.executePipelined(new SessionCallback<Object>() {
    @Override
    public Object execute(RedisOperations operations) {
        Object value = operations.opsForValue().get("order:1001:status");

        if ("PAID".equals(value)) {
            operations.opsForValue()
                    .set("order:1001:next", "SHIP");
        }
        return null;
    }
});
```

Trong thời gian pipeline đang mở, giá trị trả về trực tiếp của lệnh `get(...)` thường là `null` do kết quả thật chỉ được tập hợp sau khi pipeline được flush/đọc. Vì thế, điều kiện kiểm tra ở ví dụ này không phản ánh giá trị từ Redis.

Nếu cần đọc rồi quyết định ghi, hãy dùng hai giai đoạn (đọc theo pipeline, xử lý kết quả, rồi ghi theo pipeline) khi chấp nhận được khoảng trống đồng thời, hoặc chọn `WATCH`/Lua/lệnh nguyên tử nếu cần bảo vệ điều kiện ghi trước cạnh tranh.

## 4. Ghi nhiều khóa với TTL trong một pipeline

Không chỉ đọc, `executePipelined` còn hữu ích khi cần nạp cache theo lô, ví dụ tạo giá trị cho 1.000 sản phẩm.

```java
import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheBatchWriter {

    private final StringRedisTemplate redis;

    public ProductCacheBatchWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public record CacheEntry(String key, String jsonValue) {
    }

    public void writeBatch(List<CacheEntry> entries, Duration ttl) {
        if (entries.isEmpty()) {
            return;
        }
        if (ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        List<Object> replies = redis.executePipelined(
                new SessionCallback<Object>() {
                    @Override
                    public Object execute(RedisOperations operations) {
                        for (CacheEntry entry : entries) {
                            operations.opsForValue().set(
                                    entry.key(),
                                    entry.jsonValue(),
                                    ttl);
                        }
                        return null;
                    }
                });

        if (replies.size() != entries.size()) {
            throw new IllegalStateException(
                    "Unexpected pipeline reply count");
        }

        // Kiểm tra từng kết quả phù hợp ngữ nghĩa lệnh/serializer
        // nếu logic nghiệp vụ cần xác nhận mọi lệnh đã thành công.
    }
}
```

Gọi service:

```java
writer.writeBatch(
        List.of(
                new ProductCacheBatchWriter.CacheEntry(
                        "product:101:summary", "{\"name\":\"A\"}"),
                new ProductCacheBatchWriter.CacheEntry(
                        "product:102:summary", "{\"name\":\"B\"}")
        ),
        Duration.ofMinutes(5));
```

Phương thức `opsForValue().set(key, value, Duration)` đặt giá trị và TTL trong cùng một lệnh Redis phù hợp, giúp tránh khoảng thời gian khóa được ghi nhưng chưa có TTL như khi tách `SET` và `EXPIRE` thành hai lệnh riêng.

**Đừng diễn giải `replies.size() == entries.size()` thành bảo đảm tất cả ghi thành công.** Đây mới là kiểm tra cấu trúc kết quả; từng phản hồi và exception cần được xử lý theo ngữ nghĩa thực tế của lệnh và driver. Đồng thời, pipeline không đảm bảo khả năng rollback: nếu một lệnh trong nhóm lỗi thì các lệnh trước có thể đã có hiệu lực.

### Giữ TTL khác nhau theo từng khóa

Nếu mỗi nhóm dữ liệu có yêu cầu độ mới khác nhau, đưa TTL vào từng entry:

```java
public record CacheEntry(
        String key,
        String jsonValue,
        Duration ttl) {
}
```

Sau đó:

```java
for (CacheEntry entry : entries) {
    operations.opsForValue().set(
            entry.key(), entry.jsonValue(), entry.ttl());
}
```

Mỗi lệnh trong pipeline tự mang TTL riêng. Việc gom lệnh không buộc mọi khóa dùng cùng hạn. Khi nạp nóng lượng lớn cache, có thể thêm **TTL jitter** để tránh nhiều khóa hết hạn cùng thời điểm, miễn không vượt trần độ cũ mà nghiệp vụ cho phép.

## 5. Đọc nhiều loại dữ liệu trong cùng SessionCallback

Một pipeline có thể chứa những thao tác khác loại. Ví dụ, với một đơn hàng cần đọc string trạng thái, hash metadata và TTL còn lại:

```java
List<Object> replies = redis.executePipelined(
        new SessionCallback<Object>() {
            @Override
            public Object execute(RedisOperations operations) {
                operations.opsForValue()
                        .get("order:1001:status");

                operations.opsForHash()
                        .get("order:1001:metadata", "owner");

                operations.getExpire("order:1001:status");

                return null;
            }
        });
```

Thứ tự logic:

| Chỉ số | Lệnh phát ra | Dữ liệu kỳ vọng |
|---:|---|---|
| 0 | `GET order:1001:status` | Chuỗi trạng thái hoặc `null` |
| 1 | `HGET order:1001:metadata owner` | Giá trị Hash hoặc `null` |
| 2 | `TTL order:1001:status` | Thời gian còn lại, với giá trị đặc biệt khi khóa không tồn tại/không có TTL |

**Không giả định mọi phần tử `List<Object>` đều là `String`.** Spring Data Redis sử dụng serializer và cơ chế chuyển đổi phù hợp với thao tác; có phản hồi là chuỗi, số, danh sách, boolean hoặc `null`. Để ánh xạ kết quả an toàn, cần biết loại lệnh ở từng vị trí và dùng cấu trúc kết quả rõ ràng.

Ví dụ khi kết quả được dùng để dựng DTO, có thể viết một lớp record:

```java
public record OrderSnapshot(
        String status,
        String owner,
        Long ttlSeconds) {
}
```

Sau khi kiểm tra số lượng/kiểu phản hồi, ánh xạ `replies.get(0)`, `replies.get(1)` và `replies.get(2)` vào các trường thích hợp. Cần kiểm tra cách `getExpire` được chuyển đổi trong phiên bản Spring Data Redis đang dùng; tránh ép kiểu mù với một pipeline gồm nhiều lệnh khác loại.

### Cẩn thận với số lượng phản hồi

Nếu trong callback có một nhánh điều kiện khiến một số lệnh không được queue, danh sách kết quả sẽ khác cấu trúc mong đợi. Nên xác định thứ tự và số lượng lệnh trước khi tạo pipeline, hoặc lưu metadata tương ứng với từng lệnh đã queue:

```text
Danh sách lệnh đã queue:
  [ GET customer:1, GET customer:4, GET customer:9 ]

Danh sách reply:
  [ value:1, value:4, null ]

Ghép theo chỉ số:
  customer:1 -> value:1
  customer:4 -> value:4
  customer:9 -> null
```

Đừng diễn giải một `null` ở vị trí bất kỳ là toàn bộ pipeline thất bại: nó có thể chỉ nghĩa khóa không tồn tại. Ngược lại, đừng bỏ qua một exception hoặc phản hồi lỗi vì các phần tử khác trông hợp lệ.

## 6. Khác biệt giữa executePipelined(SessionCallback) và RedisCallback

Cả hai cách có thể triển khai pipeline đúng, nhưng trách nhiệm của lập trình viên khác nhau.

### 6.1. SessionCallback với API cấp cao

```java
List<Object> replies = stringRedisTemplate.executePipelined(
        new SessionCallback<Object>() {
            @Override
            public Object execute(RedisOperations operations) {
                operations.opsForValue().get("product:1:summary");
                operations.opsForValue().get("product:2:summary");
                return null;
            }
        });
```

Ưu điểm:

- Tận dụng `RedisOperations` đã quen thuộc.
- Dùng serializer của template cho các thao tác thông thường.
- Dễ đưa nhiều `opsFor...()` vào cùng một session.
- Ít phải thao tác trực tiếp với byte arrays.

### 6.2. RedisCallback với connection cấp thấp

```java
import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.core.RedisCallback;

List<Object> replies = stringRedisTemplate.executePipelined(
        (RedisCallback<Object>) connection -> {
            connection.stringCommands().get(
                    "product:1:summary".getBytes(StandardCharsets.UTF_8));
            connection.stringCommands().get(
                    "product:2:summary".getBytes(StandardCharsets.UTF_8));
            return null;
        });
```

Ở cấp thấp, lập trình viên chịu trách nhiệm về encoding khóa, giá trị, lựa chọn command và sự tương thích với dữ liệu ứng dụng. API connection có thể thay đổi nhẹ theo phiên bản Spring Data Redis; đoạn ví dụ minh họa đường thao tác bằng `RedisConnection`.

**Chọn `SessionCallback` khi cần một chuỗi lệnh Redis thông thường thông qua template; chọn `RedisCallback` khi cần quyền kiểm soát trực tiếp với connection hoặc serialization.** Không cần đổi sang API mức thấp chỉ vì muốn pipelining.

## 7. Pipeline và giao dịch Redis giải quyết hai vấn đề khác nhau

Những từ *pipeline*, *session* và *transaction* rất dễ bị trộn lẫn, nhưng mỗi từ giải quyết một việc:

| Cơ chế | Mục tiêu | Có rollback kiểu SQL? | Có đảm bảo nhóm lệnh nguyên tử? |
|---|---|---|---|
| Gọi từng lệnh `RedisTemplate` | Thao tác độc lập | Không | Không |
| `executePipelined(SessionCallback)` | Giảm thời gian chờ khi gửi nhiều lệnh | Không | Không |
| `MULTI`/`EXEC` | Queue rồi thực thi nhóm lệnh không bị lệnh client khác chen giữa | Không | Có ranh giới thực thi nhóm lệnh, nhưng lỗi runtime từng lệnh không được rollback |
| `WATCH` + `MULTI`/`EXEC` | Phát hiện thay đổi khóa trước commit | Không | Có điều kiện hủy transaction khi xung đột |
| Lua/script Redis | Thực thi logic trên Redis server trong một lượt xử lý | Không tự rollback mọi tác dụng phụ khi script lỗi | Script có ngữ nghĩa thực thi không bị lệnh khác chen giữa trên server |

Ví dụ một pipeline ghi hai khóa:

```text
SET order:1001:state READY
SADD ready-orders 1001
```

Nếu kết nối bị lỗi giữa quá trình gửi/nhận, ứng dụng có thể ở trạng thái không biết đã có bao nhiêu lệnh được Redis xử lý. Vì pipeline **không phải transaction**, không được coi hai thay đổi luôn đồng thời cùng có hiệu lực.

Ngược lại, với `MULTI`/`EXEC`, các lệnh được nhóm để thực thi cùng một ranh giới Redis transaction, nhưng một lệnh lỗi runtime trong `EXEC` vẫn có thể không ngăn lệnh khác thực thi. Những tình huống có logic nghiệp vụ phức tạp cần chọn công cụ phù hợp thay vì mặc định pipeline hay transaction giải quyết tất cả.

### Không kết hợp MULTI/EXEC vào pipeline một cách tùy tiện

Về nguyên tắc Redis hỗ trợ queue transaction và pipelining trong những bối cảnh nhất định, nhưng lồng `multi()`/`exec()` vào `executePipelined(...)` làm cấu trúc kết quả phức tạp hơn và khó xử lý điều kiện lỗi. Lời gọi `exec()` trong khi pipeline đang mở không phải lúc nào cũng có kết quả trực tiếp như trong `SessionCallback` dùng cho transaction thông thường.

Nếu mục tiêu là **giảm round-trip cho các lệnh độc lập**, dùng pipeline thuần. Nếu mục tiêu là **nguyên tử khi thực thi nhóm lệnh**, thiết kế transaction hoặc script rõ ràng. Chỉ kết hợp khi có lý do cụ thể và hiểu cách driver/Spring Data Redis biểu diễn kết quả lồng nhau.

## 8. Pipeline không phù hợp cho thao tác phụ thuộc kết quả trước

Ví dụ sai về mặt ý tưởng:

```java
redis.executePipelined(new SessionCallback<Object>() {
    @Override
    public Object execute(RedisOperations operations) {
        Long stock = operations.opsForValue()
                .increment("inventory:sku-1", 0);

        if (stock != null && stock > 0) {
            operations.opsForValue()
                    .decrement("inventory:sku-1", 1);
        }
        return null;
    }
});
```

Do kết quả của lệnh queue chưa sẵn sàng, điều kiện trong callback không phản ánh tồn kho tại Redis. Hơn nữa, nếu tách hai pipeline đọc rồi ghi, một client khác có thể thay đổi số lượng trong khoảng giữa, dẫn đến cạnh tranh.

Các giải pháp:

- Với luồng đọc phục vụ hiển thị: pipeline đọc toàn bộ, xử lý kết quả **sau khi pipeline kết thúc**, rồi có thể pipeline thêm các lệnh ghi.
- Với yêu cầu cập nhật có điều kiện: dùng một lệnh Redis nguyên tử phù hợp, `WATCH`/`MULTI`/`EXEC` hoặc Lua script.
- Với yêu cầu nhất quán vượt Redis: xác định dữ liệu gốc và cơ chế giao dịch ở hệ thống phù hợp, dùng Redis như cache hoặc projection.

Pipeline là tối ưu **giao tiếp mạng**; không phải ngôn ngữ điều khiển luồng lệnh phụ thuộc dữ liệu trên server.

## 9. Chọn kích thước lô để tránh pipeline quá lớn

Một pipeline gồm 100 lệnh có thể có chi phí hợp lý; pipeline gồm hàng triệu lệnh trong cùng một callback có thể chiếm rất nhiều bộ nhớ, kéo dài thời gian phản hồi và gây ảnh hưởng tới những ứng dụng khác dùng chung Redis.

Chi phí bao gồm:

1. **Bộ nhớ phía Redis:** phản hồi của các lệnh đang pipeline có thể cần được đệm trước khi gửi cho client.
2. **Bộ nhớ phía ứng dụng:** `List<Object>` chứa toàn bộ phản hồi, thêm chi phí deserialize và dựng đối tượng Java.
3. **Network throughput:** nhiều byte vẫn phải truyền, dù số lần chờ giảm.
4. **Thời gian xử lý server:** Redis vẫn thực hiện từng command.
5. **Độ trễ p95/p99:** một lô quá lớn có thể làm các request khác phải chờ tài nguyên.
6. **Khả năng phục hồi:** nếu lô lớn lỗi ở giữa, phạm vi thao tác cần đối soát cũng lớn.

Bắt đầu với các lô kích thước vừa phải (chẳng hạn 100, 250 hoặc 500 lệnh mỗi lô làm điểm thử nghiệm), sau đó điều chỉnh bằng đo lường thực tế. Đây **không phải các giới hạn chính thức của Spring Data Redis**. Kích thước phù hợp phụ thuộc kích thước value, số lệnh, tốc độ mạng, tài nguyên Redis, độ phức tạp serializer và mức đồng thời của hệ thống.

### Chia danh sách thành nhiều pipeline

Ví dụ chia một danh sách khóa thành lô tối đa 250:

```java
import java.util.ArrayList;
import java.util.List;

public List<String> loadInBatches(
        List<String> orderIds,
        int batchSize) {

    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize must be positive");
    }

    List<String> all = new ArrayList<>(orderIds.size());

    for (int start = 0; start < orderIds.size(); start += batchSize) {
        int end = Math.min(start + batchSize, orderIds.size());
        List<String> batch = orderIds.subList(start, end);

        all.addAll(loadStatuses(batch));
    }

    return all;
}
```

Trong đó `loadStatuses(batch)` là phương thức dùng `executePipelined(SessionCallback)` đã trình bày ở phần đầu. Cách chia lô giúp giới hạn số lệnh và số phản hồi được giữ đồng thời trong bộ nhớ ở một pipeline.

Đối với tập dữ liệu rất lớn, có thể đẩy từng lô sang một consumer xử lý tiếp thay vì dồn tất cả phản hồi vào `all`. Cũng nên giới hạn số pipeline chạy song song để tránh tình huống tối ưu một request nhưng làm quá tải Redis khi có hàng nghìn request đồng thời.

## 10. Kết hợp pipeline với đúng Redis data type

Không phải lúc nào cũng cần pipelining. Nếu tất cả dữ liệu là string value độc lập và biết trước khóa, Redis có những lệnh gom thao tác ở phía server như `MGET`, `MSET`, có thể phù hợp hơn.

Ví dụ:

```java
List<String> values =
        stringRedisTemplate.opsForValue().multiGet(
                List.of("product:1", "product:2", "product:3"));
```

So sánh:

| Trường hợp | Lựa chọn cân nhắc |
|---|---|
| Nhiều `GET` trên string values | `multiGet`/`MGET` nếu phù hợp; hoặc pipeline `GET` |
| Nhiều `SET` string có cùng dạng | `multiSet` hoặc pipeline `SET` |
| Nhiều `SET` cần TTL riêng | Pipeline `set(key, value, Duration)` |
| Đọc nhiều Redis Hash độc lập | Pipeline các lệnh Hash hoặc thiết kế read model |
| Gửi lệnh khác loại theo thứ tự cố định | `executePipelined(SessionCallback)` |
| Mỗi bước phụ thuộc phản hồi của bước trước | Không dùng pipeline thuần làm điều kiện |

**`MGET` chỉ áp dụng cho Redis string values**, không dùng nó để đọc tùy ý các Redis Hash mà `@RedisHash` Repository quản lý. Đọc một loạt Redis Hash có thể dùng pipeline với `HGETALL`/`HMGET` phù hợp, nhưng khi đi xuống `RedisConnection` cần xử lý serialization/field mapping đúng chuẩn.

Lệnh gom phía server và pipelining cũng có những giới hạn khác nhau trên Redis Cluster khi khóa ở nhiều hash slot. Vì vậy, lựa chọn dựa trên kiểu dữ liệu, cách phân bố khóa và cấu hình client/cluster, không chỉ số dòng Java.

## 11. SessionCallback trong Redis Cluster

Ở Redis Cluster, các khóa được chia theo **hash slot** và phân bố trên nhiều node. Trong môi trường này:

- Không mặc định tất cả khóa được phục vụ bởi một node hoặc một connection vật lý trong mọi cấu hình client.
- Khả năng pipelining qua nhiều node phụ thuộc Spring Data Redis, driver (ví dụ Lettuce) và topology.
- Khi các lệnh cần nằm trong **cùng một transaction** hoặc script nhiều khóa, Redis Cluster thường yêu cầu khóa thuộc cùng hash slot.
- Pipeline các lệnh độc lập trên các slot khác nhau không tạo bảo đảm thứ tự hoặc nguyên tử trên toàn cluster như một transaction.
- Di chuyển slot, failover và chuyển hướng `MOVED`/`ASK` có thể ảnh hưởng chi phí hoặc cách driver xử lý kết quả.

Nếu một tác vụ chỉ liên quan đến một aggregate có nhiều khóa, có thể sử dụng **hash tag**:

```text
order:{1001}:status
order:{1001}:items
order:{1001}:payment
```

Phần trong ngoặc nhọn là hash tag; các khóa có cùng `{1001}` sẽ được ánh xạ vào cùng hash slot. Điều này có ích nếu nghiệp vụ cần thực hiện một số thao tác nhiều khóa trên cùng slot.

Tuy nhiên, **không đặt mọi khóa vào cùng một hash tag toàn cục** để “dễ pipeline”, vì làm như vậy có thể tập trung tải vào một slot/node và mất lợi ích phân tán của Redis Cluster.

Trong thực tế, cần đo và xác minh hỗ trợ pipeline của driver/topology đang dùng trước khi coi ví dụ trên một Redis đơn là tối ưu cho cluster nhiều node.

## 12. Lỗi, retry và idempotency

Pipeline có thể đã gửi một số lệnh trước khi ứng dụng nhận được lỗi. Nếu connection bị gián đoạn trong lúc gửi hoặc thu phản hồi, không thể luôn kết luận chắc chắn Redis chưa xử lý bất kỳ lệnh nào.

Ví dụ:

```text
Pipeline:
  SET product:1:status READY
  INCR batch:processed
  LPUSH queue:ready product:1

Ứng dụng mất kết nối trước khi đọc hết phản hồi.
```

Nếu gửi lại nguyên pipeline:

- `SET ... READY` thường có thể lặp an toàn với cùng giá trị (nếu không có concurrent update hoặc yêu cầu thứ tự phiên bản).
- `INCR batch:processed` có thể cộng thêm lần nữa.
- `LPUSH queue:ready product:1` có thể tạo phần tử trùng.

Do đó, **pipeline không mặc định idempotent**. Cách phục hồi cần gắn với ý nghĩa nghiệp vụ của từng command.

Các biện pháp:

1. Ưu tiên lệnh ghi có thể lặp lại an toàn khi nghiệp vụ cho phép.
2. Gắn operation ID hoặc event ID để chống xử lý trùng, với cơ chế ghi/kiểm tra nguyên tử phù hợp.
3. Với lô quan trọng, lưu trạng thái hoặc checkpoint đủ để đối soát sau lỗi.
4. Phân biệt lỗi deserialize/command với lỗi kết nối không xác định kết quả.
5. Nếu retry, giới hạn số lần và thêm backoff có jitter để tránh nhiều client cùng gửi lại tải lớn.
6. Không dựa vào số lượng phần tử trong `List<Object>` như bằng chứng tất cả thao tác có hiệu lực.

Một số lệnh sẽ thất bại do kiểu dữ liệu không đúng, quyền ACL, lỗi cú pháp hoặc trạng thái cluster. Những lệnh khác trong pipeline vẫn có thể đã chạy. Spring Data Redis hoặc driver có thể báo lỗi bằng exception ở mức pipeline thay vì cung cấp một danh sách kết quả “đẹp” cho mọi trường hợp; ứng dụng cần bắt lỗi tại ranh giới service.

## 13. Quan sát và đánh giá hiệu quả pipeline

Một pipeline có thể giảm thời gian chờ mạng nhưng đồng thời tăng tải Redis nếu ứng dụng bắt đầu gửi nhiều thao tác hơn trước. Để đánh giá chính xác, nên so sánh **cùng tập dữ liệu, cùng số lệnh và cùng mức đồng thời** giữa cách gọi tuần tự, pipeline và lệnh gom đặc biệt (nếu có).

| Chỉ số | Điều cần biết |
|---|---|
| Tổng thời gian xử lý batch | Pipeline có giảm thời gian thực tế không? |
| Latency p50/p95/p99 của API | Các request có ổn định hơn hay bị lô lớn làm chậm? |
| Số command Redis mỗi request | Pipeline không tự giảm số command |
| Lượng dữ liệu truyền/nhận | Dung lượng lớn có trở thành nút thắt? |
| Kích thước batch trung bình và cực đại | Có pipeline quá lớn hoặc phân bố lệch? |
| Lỗi command và tỷ lệ retry | Có phát sinh ghi lặp hoặc lỗi một phần? |
| CPU/bộ nhớ Redis và client | Deserialization, output buffer và thao tác lặp có quá nặng? |

Một số công cụ quan sát:

```bash
redis-cli INFO commandstats
redis-cli INFO stats
redis-cli INFO memory
redis-cli SLOWLOG GET 10
```

`INFO commandstats` cho thấy lượng lệnh theo loại ở phạm vi Redis instance. Chỉ số này không tự cho biết bao nhiêu round-trip của một request cụ thể đã được tiết kiệm. `SLOWLOG` tập trung vào lệnh có thời gian xử lý phía Redis vượt ngưỡng, không bao gồm toàn bộ thời gian mạng hoặc thời gian chờ connection.

Ở phía Spring, có thể ghi timer quanh `executePipelined` và thêm thông tin loại batch, số lệnh, kích thước dữ liệu, outcome và độ trễ. Tránh ghi toàn bộ Redis key/value vào log nếu chứa thông tin cá nhân hoặc bí mật.

### Ví dụ so sánh

Giả sử batch 500 khóa có các đặc trưng minh họa:

| Cách thực hiện | Số lệnh Redis logic | Hình thức giao tiếp |
|---|---:|---|
| 500 lần gọi `get` tuần tự | 500 | Chờ phản hồi từng lệnh |
| Một pipeline 500 `GET` | 500 | Gửi nhiều lệnh, tập hợp phản hồi |
| Một `MGET` chứa 500 khóa string cùng phạm vi hỗ trợ | 1 | Một lệnh gom nhiều khóa |

Không có con số latency cố định nào được bảo đảm cho ba cách. `MGET` có thể là lựa chọn tự nhiên với string value và key tương thích; pipeline linh hoạt hơn khi cần lệnh khác loại hoặc TTL riêng. Với Redis Cluster, `MGET` nhiều khóa qua các slot cần kiểm tra cách client hỗ trợ và xử lý; đừng giả định mọi topology đều có cùng đặc tính.

## 14. Trường hợp thực tế: làm nóng cache giá sản phẩm

Một dịch vụ cần chuẩn bị cache cho 2.000 sản phẩm trước khi đón tải lớn. Mỗi sản phẩm có:

- Khóa `product:<id>:price` dạng string.
- Giá trị đã serialize và kiểm soát version.
- TTL theo yêu cầu độ mới, có thể khác nhau giữa nhóm sản phẩm.

Thực hiện từng `SET` tuần tự gây nhiều lần chờ mạng. Một pipeline duy nhất 2.000 lệnh có thể tăng áp lực bộ nhớ và thời gian xử lý; thiết kế có thể chia thành nhiều batch, ví dụ khoảng 200 lệnh mỗi batch rồi đo lường để điều chỉnh.

Luồng:

```text
Danh sách 2.000 bản ghi cần nạp
                 |
                 v
       Phân lô theo batchSize
                 |
          +------+------+
          |             |
        Batch 1       Batch 2      ... Batch N
          |             |
          v             v
    executePipelined executePipelined
      (SET + TTL)    (SET + TTL)
          |             |
          +------+------+
                 |
                 v
       Theo dõi số lệnh, lỗi,
       tổng thời gian và độ trễ
                 |
                 v
         Xử lý kết quả và tiếp tục
```

Các quyết định vận hành:

- Dùng `SET` có TTL trong cùng lệnh khi lưu một giá trị cache.
- Rải nhịp nạp hoặc bổ sung TTL jitter nếu nhiều khóa dễ hết hạn đồng loạt.
- Hạn chế số batch chạy cùng lúc để không dồn tải Redis.
- Tạo cơ chế xác định batch nào đã được áp dụng trong trường hợp kết nối lỗi.
- Không dùng một pipeline lớn làm ranh giới commit nghiệp vụ; với dữ liệu cần nhất quán, thiết kế thêm version/idempotency hoặc nguồn dữ liệu gốc.

## 15. Những lỗi dễ gặp khi dùng executePipelined

| Lỗi | Tác động | Cách tránh |
|---|---|---|
| Callback trả giá trị khác `null` | `executePipelined` không chấp nhận giá trị return của callback | Luôn `return null` |
| Dùng kết quả `get(...)` ngay bên trong callback | Giá trị chưa được trả về khi pipeline đang queue | Xử lý `List<Object>` sau callback |
| Gọi lệnh qua template khác hoặc connection khác trong callback | Dễ sai phạm vi pipeline/session | Dùng `RedisOperations` của callback |
| Giả định pipeline là transaction | Có thể xuất hiện thay đổi một phần | Dùng `MULTI`/`EXEC` hoặc cơ chế nguyên tử phù hợp khi cần |
| Gửi một pipeline khổng lồ | Tăng bộ nhớ và gây đỉnh độ trễ | Chia lô có giới hạn |
| Ép mọi phản hồi sang `String` | Lệnh khác loại có kiểu kết quả khác | Ánh xạ theo thứ tự và kiểu lệnh |
| Bỏ qua `null` ở kết quả | Dễ nhầm khóa thiếu với giao dịch lỗi | Phân biệt missing value và exception |
| Retry nguyên batch gồm `INCR`/`LPUSH` | Gây tác dụng lặp | Thiết kế idempotency/đối soát |
| Nhầm `MGET` với pipeline Hash | Không đọc được Redis Hash bằng `MGET` | Chọn đúng API Redis data type |
| Tưởng pipeline hỗ trợ mọi multi-key operation trên Redis Cluster | Có thể gặp giới hạn slot/topology | Xem khả năng driver và bố trí khóa |

## 16. Chọn executePipelined(SessionCallback) khi nào?

```text
Có nhiều lệnh Redis trong một tác vụ?
                  |
             +----+----+
             |         |
            Không      Có
             |         |
             v         v
       Lệnh thường   Các lệnh có độc lập,
                     không cần kết quả trước?
                          |
                     +----+----+
                     |         |
                    Có        Không
                     |         |
                     v         v
                 Xét MGET/    Dùng lệnh điều kiện,
                 MSET nếu     WATCH/transaction,
                 phù hợp      Lua hoặc hai giai đoạn
                     |
                     v
            Cần nhiều lệnh khác loại,
            hoặc TTL riêng từng key?
                     |
                +----+----+
                |         |
               Có        Không
                |         |
                v         v
         executePipelined  Cân nhắc lệnh gom
         (SessionCallback)  phía server trước
                |
                v
           Giới hạn batch,
           đo latency, xử lý lỗi,
           retry và idempotency
```

**Điểm cốt lõi:** `executePipelined(SessionCallback)` là lựa chọn thuận tiện khi cần phát nhiều lệnh Redis độc lập thông qua `RedisOperations` trong cùng một session và tập hợp kết quả sau khi pipeline hoàn tất. Callback phải trả `null`; mọi phản hồi được nhận ở `List<Object>` bên ngoài. Thiết kế đúng phải phân biệt pipeline với transaction, ánh xạ phản hồi theo lệnh, giới hạn kích thước batch và xử lý cả trường hợp lỗi một phần hoặc mất kết nối.

