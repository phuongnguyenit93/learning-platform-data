# Dùng `executePipelined` với `RedisCallback` trong Spring Data Redis

Khi ứng dụng cần gửi hàng trăm hoặc hàng nghìn lệnh Redis độc lập, thời gian truyền lệnh qua mạng có thể trở thành một phần đáng kể của độ trễ. **Redis pipelining** cho phép client gửi nhiều lệnh liên tiếp rồi thu thập các phản hồi theo lô, giảm việc phải chờ một vòng trao đổi mạng cho mỗi lệnh. Spring Data Redis cung cấp phương thức `RedisTemplate.executePipelined(...)` để sử dụng cơ chế này.

Với biến thể **`executePipelined(RedisCallback<?>)`**, lập trình viên làm việc trực tiếp với `RedisConnection` bên trong callback. Cách này phù hợp khi cần điều khiển chính xác chuỗi lệnh Redis cấp thấp, hiểu rõ byte serialization và chủ động ghép từng phản hồi với lệnh tương ứng.

Điểm cần nhớ ngay từ đầu:

- **Pipeline tối ưu trao đổi mạng; không biến nhiều lệnh thành một giao dịch nguyên tử.**
- `executePipelined` thu thập **kết quả sau khi callback kết thúc**. Không dùng kết quả của lệnh đang xếp vào pipeline để ra quyết định ngay trong callback.
- Callback truyền cho `executePipelined` **phải trả về `null`**; các phản hồi thực tế nằm trong `List<Object>` do phương thức trả về.
- Với `RedisCallback`, key và value được gửi qua giao diện lệnh cấp thấp dưới dạng `byte[]`. Phải dùng serializer phù hợp với dữ liệu đang có.
- Pipeline có thể giúp giảm độ trễ mạng, nhưng lô quá lớn làm tăng bộ nhớ và có thể khiến Redis hoặc client chịu tải không cần thiết.

Bài viết này giải thích cách pipeline hoạt động, cách gọi đúng API, cách giải mã phản hồi và những giới hạn khi áp dụng vào hệ thống thực tế.

## 1. Vì sao cần pipeline?

Giả sử một request cần đọc 100 giá trị cache:

```text
cache:product:p001
cache:product:p002
...
cache:product:p100
```

Nếu ứng dụng gọi Redis tuần tự bằng `GET`, mỗi lần lại chờ kết quả rồi mới gửi lệnh tiếp:

```text
Ứng dụng                     Redis
    | --- GET p001 ----------> |
    | <-------- kết quả -------|
    | --- GET p002 ----------> |
    | <-------- kết quả -------|
    |            ...
    | --- GET p100 ----------> |
    | <-------- kết quả -------|
```

Nếu độ trễ mạng qua lại là đáng kể, tổng thời gian có thể chứa nhiều lần chờ không cần thiết, dù từng lệnh `GET` trên Redis rất nhanh.

Với pipeline:

```text
Ứng dụng                     Redis
    | --- GET p001 ----------> |
    | --- GET p002 ----------> |
    |            ...           |
    | --- GET p100 ----------> |
    | <------ các kết quả ------|
```

Client gửi các lệnh theo lô mà không yêu cầu mỗi lời gọi phải hoàn tất một vòng truyền mạng trước khi bắt đầu lệnh sau. Redis xử lý lệnh và tạo phản hồi; driver thu thập các phản hồi rồi trả chúng cho Spring Data Redis.

Lợi ích chính là **giảm thời gian chờ do network round trip**. Pipeline không làm mỗi lệnh `GET` tự chạy nhanh hơn về tính toán và không loại bỏ chi phí serialize dữ liệu, thực thi lệnh hay lưu kết quả.

### 1.1. Phân biệt pipeline với lệnh nhiều key

Với nhiều lệnh đọc cùng loại, Redis còn có các lệnh như `MGET`. Ví dụ:

```redis
MGET cache:product:p001 cache:product:p002 cache:product:p003
```

`MGET` là **một lệnh** lấy nhiều key, có thể là lựa chọn đơn giản hơn pipeline nhiều `GET` khi đáp ứng đúng yêu cầu. Trong Spring Data Redis, có thể cân nhắc `opsForValue().multiGet(keys)`.

Pipeline có ích khi muốn gửi **nhiều lệnh khác nhau** (`GET`, `INCR`, `SETEX`, `HGET`...), khi cần một chuỗi thao tác không có lệnh nhiều key tương ứng, hoặc khi API cấp thấp cần điều khiển riêng từng key.

Trong Redis Cluster, các lệnh nhiều key như `MGET` phải tuân thủ quy tắc hash slot; pipeline qua nhiều node cũng phụ thuộc vào khả năng routing của driver và cấu hình cluster. Vì vậy không thể mặc định hai cách luôn thay thế nhau trong mọi môi trường.

## 2. API `executePipelined` và vai trò của `RedisCallback`

`RedisTemplate` có phương thức theo dạng:

```java
List<Object> executePipelined(RedisCallback<?> action);
```

Một biến thể khác cho phép chỉ định serializer dùng khi xử lý kết quả trả về:

```java
List<Object> executePipelined(
        RedisCallback<?> action,
        RedisSerializer<?> resultSerializer
);
```

Ví dụ hình thức tối giản:

```java
List<Object> results = stringRedisTemplate.executePipelined(
    (RedisCallback<Object>) connection -> {
        // Gửi các Redis commands qua connection.
        return null;
    }
);
```

Trong đó:

| Thành phần | Vai trò |
|---|---|
| `StringRedisTemplate` | Template có serializer kiểu String, tiện cho key/value văn bản |
| `executePipelined(...)` | Mở pipeline, thực hiện callback, đóng pipeline và thu kết quả |
| `RedisCallback<?>` | Cho phép thao tác trực tiếp với `RedisConnection` |
| `RedisConnection` | Giao diện cấp thấp gửi lệnh Redis, thường sử dụng `byte[]` |
| `return null` | Kết quả của callback không dùng làm kết quả pipeline |
| `List<Object>` | Các phản hồi được Spring Data Redis trả sau khi pipeline hoàn tất |

`RedisCallback` là một functional interface có phương thức nhận `RedisConnection` và trả kết quả do callback xác định. Nhưng trong **`executePipelined`**, phần giá trị callback trả về bắt buộc phải là `null`, vì Spring Data Redis sử dụng danh sách phản hồi của pipeline làm kết quả cuối.

Nếu muốn thực thi callback và nhận một kết quả tính toán trực tiếp của callback, đó là mục đích khác của `RedisTemplate.execute(...)`.

## 3. Ví dụ tối thiểu: gửi nhiều `SET` qua pipeline

Giả sử muốn ghi ba trạng thái xử lý:

```text
job:101:status = QUEUED
job:102:status = QUEUED
job:103:status = QUEUED
```

Đầu tiên, tạo service với `StringRedisTemplate`:

```java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.stereotype.Service;

@Service
public class JobStatusBatchWriter {

    private final StringRedisTemplate redis;

    public JobStatusBatchWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> markQueued() {
        RedisSerializer<String> serializer = redis.getStringSerializer();

        return redis.executePipelined(
            (RedisCallback<Object>) connection -> {
                connection.stringCommands().set(
                    serializer.serialize("job:101:status"),
                    serializer.serialize("QUEUED")
                );

                connection.stringCommands().set(
                    serializer.serialize("job:102:status"),
                    serializer.serialize("QUEUED")
                );

                connection.stringCommands().set(
                    serializer.serialize("job:103:status"),
                    serializer.serialize("QUEUED")
                );

                return null;
            }
        );
    }
}
```

Ba lệnh `SET` được gửi qua cùng một pipeline do Spring Data Redis quản lý. Sau khi callback chạy xong, template đóng pipeline và trả về danh sách phản hồi.

Lệnh `SET` thông thường trả kết quả báo thành công. Cách biểu diễn cụ thể trong danh sách phụ thuộc driver và bước chuyển đổi kết quả. Vì thế không nên ép toàn bộ phần tử của `List<Object>` thành `String` nếu pipeline chứa nhiều loại lệnh.

### 3.1. Vì sao phải tự serialize key/value?

Với API cấp cao:

```java
redis.opsForValue().set("job:101:status", "QUEUED");
```

`StringRedisTemplate` tự dùng serializer cấu hình trên template để đổi key và value thành byte.

Với `RedisCallback`, ta gọi trực tiếp lệnh trên `RedisConnection`:

```java
connection.stringCommands().set(
    byte[] key,
    byte[] value
);
```

Do đó **ứng dụng phải tự cung cấp byte đúng chuẩn**. Trong ví dụ, `getStringSerializer()` thực hiện chuyển đổi cho key/value chuỗi.

Nếu tùy ý dùng `String.getBytes()` ở những nơi khác trong dự án đang dùng một serializer khác, key được ghi bởi pipeline có thể không tương thích với key được đọc bởi repository hoặc `RedisTemplate`. Mã Java nhìn giống nhau nhưng byte thực tế trong Redis khác nhau.

Không nên xem serializer như phần trang trí: nó là một phần của quy ước lưu trữ dữ liệu.

## 4. Ví dụ thực tế: đọc nhiều key bằng một pipeline

Bài toán: nhận danh sách mã sản phẩm, đọc cache của từng mã và trả về `Map<String, String>` để tầng gọi biết giá trị thuộc sản phẩm nào.

```java
package com.example.redis;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheBatchReader {

    private final StringRedisTemplate redis;

    public ProductCacheBatchReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Map<String, String> findCachedProducts(List<String> ids) {
        Map<String, String> result = new LinkedHashMap<>();

        if (ids.isEmpty()) {
            return result;
        }

        RedisSerializer<String> serializer = redis.getStringSerializer();

        List<Object> replies = redis.executePipelined(
            (RedisCallback<Object>) connection -> {
                for (String id : ids) {
                    byte[] key = serializer.serialize(
                        "cache:product:" + id
                    );

                    connection.stringCommands().get(key);
                }

                // Quan trọng: executePipelined yêu cầu callback trả null.
                return null;
            }
        );

        if (replies.size() != ids.size()) {
            throw new IllegalStateException(
                "Số phản hồi không khớp số lệnh GET"
            );
        }

        for (int i = 0; i < ids.size(); i++) {
            // StringRedisTemplate xử lý kết quả GET theo
            // value serializer của template.
            String value = (String) replies.get(i);
            result.put(ids.get(i), value);
        }

        return result;
    }
}
```

Cách gọi:

```java
List<String> ids = List.of("p101", "p102", "p103");

Map<String, String> products =
        productCacheBatchReader.findCachedProducts(ids);

System.out.println(products.get("p101"));
System.out.println(products.get("p102"));
```

Nếu key `cache:product:p102` không tồn tại, giá trị tương ứng trong kết quả có thể là `null`. Ví dụ giữ entry `p102 -> null` để biểu diễn cache miss; một API khác có thể chỉ đưa entry có giá trị vào map, tùy yêu cầu nghiệp vụ.

### 4.1. Vì sao có thể ghép phản hồi theo vị trí?

Các phản hồi của pipeline được Redis/driver thu theo **thứ tự lệnh được gửi** trên connection tương ứng. Trong ví dụ, câu lệnh GET thứ `i` tương ứng với `ids.get(i)`. Do đó có thể sử dụng chỉ số để ánh xạ:

```text
Lệnh gửi                         Phản hồi nhận
----------------------------------------------
GET cache:product:p101           replies[0]
GET cache:product:p102           replies[1]
GET cache:product:p103           replies[2]
```

Dù vậy, không nên thay đổi thứ tự hoặc số lượng lệnh trong callback mà quên cập nhật đoạn code ánh xạ kết quả. Nếu thêm một lệnh `PING` vào giữa các lệnh GET, vị trí phản hồi của các lệnh phía sau sẽ dịch chuyển.

Khi chứa nhiều loại lệnh, nên lưu một danh sách metadata tương ứng với từng lệnh để biết phản hồi nào thuộc thao tác nào.

### 4.2. Giá trị trả về không có ngay trong callback

Đoạn sau là một cách hiểu sai:

```java
redis.executePipelined(
    (RedisCallback<Object>) connection -> {
        byte[] raw = connection.stringCommands()
            .get("cache:product:p101".getBytes());

        // Không dựa vào raw để quyết định lệnh kế tiếp:
        // GET đang được xếp vào pipeline và chưa có kết quả
        // theo cách gọi đồng bộ thông thường.

        return null;
    }
);
```

Các lệnh được đưa vào pipeline nên giá trị trả trực tiếp từ lời gọi cấp thấp trong callback thường không phải kết quả cuối để ứng dụng xử lý. **Kết quả phải được sử dụng bên ngoài callback**, từ `List<Object>` của `executePipelined`.

Nếu lệnh B chỉ được gửi khi kết quả thực của lệnh A đáp ứng điều kiện, hai lệnh đó **có phụ thuộc dữ liệu**. Một pipeline đơn giản không thích hợp để rẽ nhánh ngay giữa lô. Khi đó, tách thành các giai đoạn đọc rồi ghi, hoặc dùng Lua/Redis Function, `WATCH` và cơ chế thích hợp nếu cần tính nguyên tử.

## 5. Ghi nhiều khóa với TTL bằng `setEx`

Pipeline phù hợp khi có nhiều bản ghi cache cần ghi riêng rẽ và cùng áp dụng một thời gian sống.

Ví dụ lưu các thông báo trạng thái tạm trong 300 giây:

```java
package com.example.redis;

import java.util.List;
import java.util.Map;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.stereotype.Service;

@Service
public class TemporaryStatusWriter {

    private final StringRedisTemplate redis;

    public TemporaryStatusWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> writeStatuses(Map<String, String> statuses) {
        RedisSerializer<String> serializer = redis.getStringSerializer();

        return redis.executePipelined(
            (RedisCallback<Object>) connection -> {
                for (Map.Entry<String, String> entry : statuses.entrySet()) {
                    byte[] key = serializer.serialize(
                        "status:" + entry.getKey()
                    );
                    byte[] value = serializer.serialize(entry.getValue());

                    connection.stringCommands().setEx(
                        key,
                        300L,
                        value
                    );
                }
                return null;
            }
        );
    }
}
```

`setEx` ghi giá trị và thời hạn trong **một lệnh Redis cho mỗi key**, nên tránh khoảng trống khi gửi `SET` rồi `EXPIRE` riêng rẽ. Tuy nhiên, toàn bộ những lệnh `setEx` của pipeline **không tạo thành một transaction**. Nếu có lỗi hoặc mất kết nối, có thể có khóa được ghi thành công và khóa khác chưa được ghi.

Ví dụ gửi:

```java
Map<String, String> statuses = Map.of(
    "task-1", "RUNNING",
    "task-2", "QUEUED",
    "task-3", "DONE"
);

temporaryStatusWriter.writeStatuses(statuses);
```

Nếu nghiệp vụ cần **mọi trạng thái được cập nhật đồng thời hoặc không có trạng thái nào thay đổi**, pipeline một mình không đáp ứng yêu cầu ấy.

## 6. Pipeline hỗn hợp: `SET`, `INCR` và `GET` trả các kiểu khác nhau

Một pipeline có thể gồm nhiều loại lệnh:

```java
RedisSerializer<String> serializer = redis.getStringSerializer();

List<Object> results = redis.executePipelined(
    (RedisCallback<Object>) connection -> {
        byte[] key = serializer.serialize("demo:pipeline:counter");

        connection.stringCommands().set(
            key,
            serializer.serialize("10")
        );

        connection.stringCommands().incr(key);

        connection.stringCommands().get(key);

        return null;
    }
);
```

Logic được Redis xử lý theo thứ tự:

```text
SET demo:pipeline:counter 10
INCR demo:pipeline:counter
GET demo:pipeline:counter
```

Nếu không có thao tác khác chen giữa những lệnh này, `GET` nhìn thấy `"11"`. Nhưng pipeline **không tự bảo đảm không có thao tác của client khác xen giữa các lệnh**. Ví dụ giá trị cuối có thể khác nếu client khác cùng sửa key đúng lúc.

Danh sách kết quả chứa phản hồi theo vị trí:

| Vị trí | Lệnh | Loại kết quả thường gặp |
|---|---|---|
| `results.get(0)` | `SET` | Kết quả xác nhận lệnh ghi |
| `results.get(1)` | `INCR` | Giá trị số sau khi tăng, thường biểu diễn bằng `Long` |
| `results.get(2)` | `GET` | Giá trị được giải mã, thường là `String` với `StringRedisTemplate` |

Vì kiểu kết quả hỗn hợp, **không ép cả danh sách về `List<String>` hoặc `List<Long>`**. Dựa vào loại lệnh và serializer để xử lý từng vị trí.

Nếu cần điều kiện “chỉ INCR khi GET thấy dữ liệu hợp lệ”, pipeline không phải công cụ bảo đảm điều kiện. Cần thiết kế phép kiểm tra và cập nhật tại server hoặc dùng cơ chế optimistic concurrency phù hợp.

## 7. Spring Data Redis quản lý pipeline như thế nào?

Về mặt ý tưởng, quy trình của `executePipelined` có thể được diễn đạt:

```text
Caller
  |
  | redisTemplate.executePipelined(callback)
  v
RedisTemplate mở pipeline
  |
  | callback.doInRedis(connection)
  |   ├─ Gửi lệnh 1
  |   ├─ Gửi lệnh 2
  |   ├─ Gửi lệnh 3
  |   └─ return null
  |
RedisTemplate kết thúc pipeline và thu các phản hồi
  |
Giải mã kết quả theo serializer được cấu hình
  |
  v
List<Object> trả về cho caller
```

Cách hoạt động thực tế dưới lớp connection còn phụ thuộc Redis client (ví dụ Lettuce hoặc Jedis), nhưng ở cấp API ứng dụng, `executePipelined` chịu trách nhiệm quản lý thời điểm thu kết quả.

### 7.1. Không tự mở hoặc đóng lại pipeline bên trong callback

Khi dùng:

```java
redis.executePipelined((RedisCallback<Object>) connection -> {
    // Gửi lệnh ở đây.
    return null;
});
```

Spring Data Redis đã quản lý pipeline cho lời gọi này.

Không cần cố làm:

```java
connection.openPipeline();
// gửi lệnh...
connection.closePipeline();
```

ngay bên trong callback của `executePipelined`. Làm vậy trộn hai cơ chế quản lý pipeline và có thể khiến hành vi thu kết quả không đúng mong đợi.

Nếu sử dụng API `RedisConnection` trực tiếp ở một luồng khác, việc mở/đóng pipeline có quy tắc riêng, nhưng đó không phải là luồng đang được minh họa ở đây.

### 7.2. Không giữ `RedisConnection` để dùng sau callback

`RedisConnection` bên trong `RedisCallback` thuộc phạm vi thực thi do Spring Data Redis quản lý. Không lưu connection này vào field của service, biến toàn cục hoặc gửi qua thread khác để tiếp tục gọi sau khi callback kết thúc.

Nên kết thúc toàn bộ thao tác gửi lệnh trong callback, nhận danh sách phản hồi từ phương thức `executePipelined`, rồi xử lý chúng ở bên ngoài callback.

### 7.3. Không biến callback thành một tác vụ bất đồng bộ tùy ý

`executePipelined` là một lời gọi đồng bộ ở tầng API: caller nhận danh sách kết quả sau khi lệnh pipeline được thực hiện và phản hồi đã được thu về. Tác dụng của pipeline chủ yếu nằm ở cách gửi nhiều lệnh qua kết nối, không có nghĩa service tự chạy ở background rồi trả về `CompletableFuture`.

Nếu cần API reactive, Spring Data Redis có các API reactive riêng cho Redis; không nên đánh đồng chúng với `RedisTemplate.executePipelined`.

## 8. Serializer: phần dễ gây lỗi khi dùng `RedisCallback`

Với `StringRedisTemplate`, hai ví dụ thường dùng:

```java
RedisSerializer<String> serializer =
        stringRedisTemplate.getStringSerializer();

byte[] key = serializer.serialize("cache:user:42");
byte[] value = serializer.serialize("ACTIVE");
```

Sử dụng cùng serializer cho key và value hợp lý khi cả hai đều là chuỗi. Nếu ứng dụng sử dụng `RedisTemplate<String, UserProfile>` với key serializer kiểu String và value serializer mã hóa đối tượng, hai loại serializer có thể khác nhau:

```text
Key:
  "cache:user:42" -> StringRedisSerializer -> byte[]

Value:
  UserProfile(...) -> JSON/byte serializer cấu hình -> byte[]
```

Không thể lấy byte chuỗi JSON tùy ý rồi kỳ vọng một `RedisTemplate` được cấu hình với serializer khác sẽ tự đọc thành đúng object.

### 8.1. Luồng serialization của callback khác API cấp cao

So sánh:

```java
redis.opsForValue().set("cache:user:42", "ACTIVE");
```

với:

```java
redis.executePipelined(
    (RedisCallback<Object>) connection -> {
        connection.stringCommands().set(
            serializer.serialize("cache:user:42"),
            serializer.serialize("ACTIVE")
        );
        return null;
    }
);
```

Trong ví dụ thứ hai, serialization của tham số **là trách nhiệm của code bên trong callback**.

### 8.2. Deserialization của kết quả

Sau khi pipeline kết thúc, `RedisTemplate` xử lý những kết quả đọc dựa trên serializer đã cấu hình; ví dụ:

- Redis String đọc qua `GET` thường dùng value serializer.
- Lệnh liên quan tới Redis Hash có thể cần hash key/hash value serializer tương ứng.
- Lệnh số và trạng thái ghi thường trả về loại kết quả riêng, không được hiểu như một byte chuỗi cần parse thành object tùy ý.

Một số trường hợp có thể chỉ định serializer cho kết quả:

```java
List<Object> values = redis.executePipelined(
    (RedisCallback<Object>) connection -> {
        // Các GET bằng lệnh Redis cấp thấp.
        return null;
    },
    redis.getStringSerializer()
);
```

Việc truyền serializer kết quả phù hợp khi dữ liệu đọc được lưu theo cùng định dạng và API cho phép. Không nên đặt một serializer duy nhất tùy ý rồi mong nó diễn giải mọi kiểu phản hồi hỗn hợp trong pipeline.

### 8.3. Triệu chứng sai serializer

Giả sử code ngoài pipeline sử dụng key serializer là `StringRedisSerializer`, nhưng callback lại ghi key bằng một serializer có tiền tố byte khác:

```text
Bên ngoài:
  GET "cache:user:42" -> nil

Bên trong pipeline:
  SET <bytes không khớp> "ACTIVE" -> thành công
```

Lúc này pipeline đã ghi một key, nhưng key **không cùng byte** với key mà `opsForValue().get(...)` sử dụng. Redis phân biệt key theo byte; tên hiển thị gần giống nhau không đủ để bảo đảm đang thao tác cùng key.

Khi thấy `GET` ngoài pipeline không đọc được giá trị đã ghi, hãy xem lại serializer, key prefix, selected database và connection factory trước khi cho rằng pipeline không thực thi.

## 9. Dùng `RedisCallback` hay `SessionCallback`?

Spring Data Redis có cả `RedisCallback` và `SessionCallback`, phục vụ các mức trừu tượng khác nhau.

| Tiêu chí | `RedisCallback` | `SessionCallback` |
|---|---|---|
| Đối tượng callback nhận | `RedisConnection` | `RedisOperations` |
| Mức API | Cấp thấp, thao tác Redis commands | Cấp template, dùng operations |
| Truyền tham số | Thường sử dụng `byte[]` | Dựa vào serializer của `RedisTemplate` |
| Phù hợp | Điều khiển trực tiếp lệnh, xử lý nhiều lệnh Redis cấp thấp | Gom các thao tác cấp template dùng cùng session |
| Pipeline | `executePipelined(RedisCallback<?>)` | Có biến thể `executePipelined(SessionCallback<?>)` |
| Rủi ro cần chú ý | Tự serialize tham số, xử lý kết quả lệnh thấp cấp | Phân biệt callback result với pipeline result và semantics của operations |

Ví dụ `SessionCallback` có thể sử dụng `opsForValue().get(...)` và serializer của template trực tiếp. Tuy nhiên, ở bài này, mục tiêu là **`executePipelined` với `RedisCallback`**, vì vậy cần nhận diện rõ kiểu của connection và trách nhiệm chuyển đổi dữ liệu.

Không chọn `SessionCallback` chỉ vì nghĩ pipeline tự trở thành transaction, và không chọn `RedisCallback` chỉ vì tưởng mọi lệnh sẽ chạy nguyên tử. Cả hai cách đều có thể đưa lệnh vào pipeline; nguyên tử là một yêu cầu khác.

## 10. Pipeline không phải `MULTI`/`EXEC`

Đây là khác biệt quan trọng nhất khi áp dụng pipeline cho nghiệp vụ.

**Pipeline:**

```text
Gửi lệnh A
Gửi lệnh B
Gửi lệnh C
Thu phản hồi A, B, C
```

Mục tiêu: giảm thời gian chờ mạng. Các lệnh của client khác **có thể** xen giữa A, B, C.

**Redis transaction bằng `MULTI`/`EXEC`:**

```text
MULTI
A -> QUEUED
B -> QUEUED
C -> QUEUED
EXEC -> Redis thực thi nhóm theo thứ tự, không bị xen giữa
```

Mục tiêu: thực thi nhóm lệnh không bị interleave trong giai đoạn `EXEC`. Tuy nhiên, Redis không có rollback tổng quát cho những lệnh đã chạy nếu lệnh khác trong transaction gặp lỗi runtime.

| Thuộc tính | Pipeline | `MULTI`/`EXEC` |
|---|---|---|
| Giảm số round trip | Có thể | Có thể khi gửi lệnh nhóm, tùy client |
| Lệnh được thực thi khi nào | Khi Redis nhận và xử lý lệnh | Các lệnh được queue trước, chạy lúc `EXEC` |
| Client khác có thể chen giữa các lệnh? | Có | Không trong lúc Redis thực thi nhóm `EXEC` |
| Kết quả lệnh sẵn ngay cho Java bên trong callback? | Không, thu sau pipeline | Không, thu sau `EXEC` |
| Tự rollback khi một lệnh runtime lỗi? | Không | Không |
| Tạo transaction với PostgreSQL? | Không | Không |
| Phù hợp nhất | Nhiều thao tác độc lập, giảm RTT | Cần nhóm lệnh chạy liền nhau |

Nếu cần điều kiện “đọc giá trị hiện tại, kiểm tra rồi ghi” theo cách không có race condition, cả pipeline thông thường lẫn `MULTI` đơn lẻ có thể chưa đủ; cần `WATCH` hoặc Lua/Redis Function phù hợp.

### 10.1. Vì sao pipeline không bảo vệ được read–modify–write?

Ví dụ sai về concurrency:

```java
// Một request khác có thể thay đổi key giữa những lệnh.
String value = redis.opsForValue().get("counter:42");
long next = Long.parseLong(value) + 1;
redis.opsForValue().set("counter:42", Long.toString(next));
```

Đưa `GET` và `SET` vào pipeline cũng không giải quyết được việc phải **đọc kết quả GET rồi mới tính ra giá trị SET** trong Java. Kết quả `GET` không sẵn trong callback để tạo lệnh phụ thuộc.

Nếu phép toán là tăng một bộ đếm, Redis đã có `INCR`: đó là một lệnh nguyên tử và thường là giải pháp đúng. Nếu điều kiện phức tạp, cân nhắc Lua/Redis Function hoặc cơ chế optimistic concurrency.

## 11. Xử lý lỗi và giới hạn tính nhất quán

Một pipeline có nhiều lệnh không có bảo đảm **all-or-nothing**:

```text
SET cache:a A   -> có thể đã thành công
SET cache:b B   -> có thể đã thành công
SET cache:c C   -> có thể lỗi hoặc chưa chạy
```

Nếu kết nối mất hoặc Redis trả lỗi, ứng dụng không được giả định cả ba lệnh đều thất bại. Tùy lỗi và driver, có thể nhận exception, một phản hồi lỗi trong lô hoặc không có kết quả đủ để biết chính xác lệnh nào đã thực thi.

### 11.1. Quy tắc xử lý

- Với **cache có thể tái tạo**, có thể thiết kế retry, bỏ qua entry lỗi, dùng TTL và nạp lại từ nguồn dữ liệu chính.
- Với **lệnh ghi idempotent** như `SET key fixedValue`, việc retry có thể chấp nhận được nếu không phá vỡ tính đúng đắn của nghiệp vụ.
- Với **lệnh có tác dụng cộng dồn** như `INCR`, không retry mù quáng sau timeout: lệnh có thể đã tăng thành công nhưng phản hồi bị mất, retry sẽ tăng lần thứ hai.
- Nếu cần cập nhật nhiều key như một đơn vị nhất quán, lựa chọn pipeline không đủ; phải thiết kế transaction/server-side atomic operation theo phạm vi Redis hỗ trợ.
- Với lỗi dữ liệu hoặc lỗi kiểu Redis như `WRONGTYPE`, chạy lại cùng lô mà không xử lý nguyên nhân có thể tiếp tục thất bại.

Ví dụ ngữ nghĩa retry:

```text
Client gửi INCR metrics:orders
Redis đã thực thi -> metrics:orders tăng 1
Mạng ngắt trước khi phản hồi tới client
Client không biết đã thực thi hay chưa
Client retry INCR -> metrics:orders có thể tăng thêm 1 lần nữa
```

Muốn yêu cầu chỉ tính một lần, cần thiết kế idempotency key hoặc cơ chế nghiệp vụ phù hợp; pipeline không tự cung cấp tính năng này.

### 11.2. Pipeline không bảo đảm Redis persistence

Ngay cả khi `executePipelined` trả danh sách phản hồi thành công, dữ liệu có tồn tại sau crash/failover hay không còn phụ thuộc cấu hình persistence, replication và topology Redis. Pipeline chủ yếu tác động tới cách **gửi và thu phản hồi**, không thay đổi chính sách lưu bền dữ liệu.

## 12. Chia batch để tránh pipeline quá lớn

Gửi hàng triệu lệnh trong một pipeline duy nhất có thể làm tăng đáng kể:

- Bộ nhớ đệm yêu cầu ở client/driver.
- Bộ nhớ dành cho phản hồi ở server trong lúc chờ client đọc.
- Bộ nhớ chứa `List<Object>` khi Spring Data Redis trả toàn bộ kết quả.
- Độ trễ của request và thời gian giữ connection.
- Khả năng gặp timeout khi response quá lớn.

Thông thường nên **chia nhỏ danh sách đầu vào thành các batch** rồi thực hiện nhiều pipeline. Không có kích thước batch tối ưu cho mọi hệ thống; lựa chọn phụ thuộc kích thước value, round-trip time, tốc độ xử lý Redis, giới hạn connection và memory budget của ứng dụng.

Ví dụ chia lô đọc với tối đa 200 key mỗi lần:

```java
public Map<String, String> findCachedProductsInBatches(
        List<String> productIds,
        ProductCacheBatchReader reader
) {
    final int batchSize = 200;
    Map<String, String> results = new LinkedHashMap<>();

    for (int start = 0; start < productIds.size(); start += batchSize) {
        int end = Math.min(start + batchSize, productIds.size());

        List<String> batch = productIds.subList(start, end);

        Map<String, String> partial = reader.findCachedProducts(batch);
        results.putAll(partial);
    }

    return results;
}
```

Trong ví dụ, `findCachedProducts` là phương thức ở phần 4. Mỗi batch có một lời gọi `executePipelined`, vì vậy ứng dụng giới hạn lượng phản hồi cần lưu trong một lần thực thi. Nếu danh sách ID có giá trị trùng, `Map` sẽ chỉ giữ một entry cho mỗi key; nếu cần bảo toàn số lượng/vị trí trùng lặp, trả một `List` song song với input.

### 12.1. Không có “batch size thần kỳ”

Có thể bắt đầu từ vài chục hoặc vài trăm lệnh cho mỗi batch, rồi đo đạc. Những tiêu chí cần quan sát:

| Chỉ số | Điều cần chú ý |
|---|---|
| Request latency p50/p95/p99 | Pipeline có giảm độ trễ đầu cuối thực tế không? |
| Network RTT và throughput | Có đang giảm thời gian chờ so với gọi từng lệnh không? |
| Kích thước response | Mỗi key trả vài byte hay hàng MB? |
| JVM heap và GC | `List<Object>` của batch có làm tăng áp lực bộ nhớ không? |
| Redis memory/network output | Server có bị tồn đọng phản hồi lớn không? |
| Timeout, connection pool | Batch có giữ connection quá lâu hoặc ảnh hưởng request khác không? |
| Redis CPU | Pipeline tăng throughput có làm server quá tải không? |

Đánh giá trên workload và môi trường gần với thực tế, vì pipeline có thể cải thiện rõ khi mạng có độ trễ nhưng không giúp nhiều khi lệnh nặng về CPU hoặc server đã đạt giới hạn xử lý.

## 13. Redis Cluster và chuyện kết nối

Trong Redis standalone, lệnh qua một connection hướng tới cùng một Redis server. Với Redis Cluster, key được phân vào nhiều hash slot và các node khác nhau.

Một pipeline chứa các key thuộc nhiều slot cần được driver xử lý theo routing của cluster. Các Redis client có khả năng pipeline trên cluster khác nhau về cách nhóm lệnh theo node, thứ tự thu phản hồi, cách xử lý redirect và các giới hạn kết nối.

Vì vậy:

1. Kiểm tra khả năng pipeline của phiên bản Spring Data Redis và driver đang dùng với chế độ cluster thực tế.
2. Không giả định mọi key trong pipeline được gửi tới một server duy nhất.
3. Không suy ra việc các lệnh nằm trong cùng pipeline sẽ mang lại transaction nguyên tử trên nhiều hash slot.
4. Nếu cần lệnh đa key hoặc Lua script, phải tuân thủ quy tắc hash slot/định tuyến tương ứng.
5. Với workload lớn, cân nhắc nhóm key theo locality hoặc thiết kế key naming phù hợp để giảm số node/connection phải sử dụng, khi điều này có ý nghĩa với nghiệp vụ.

Redis Cluster cũng có cơ chế failover, redirect và replication ảnh hưởng tới thời gian và lỗi. Pipeline không thay thế thiết kế retry/idempotency.

## 14. Khi nào nên tránh `RedisCallback` pipeline?

Không phải mọi bài toán nhiều lệnh đều nên dùng `executePipelined`:

**Một lệnh Redis đã đủ.** Nếu cần tăng số nguyên, dùng `INCR`; nếu cần lấy nhiều String key có thể dùng `MGET` khi phù hợp; nếu muốn ghi giá trị với TTL, dùng `SET` kèm `EX/PX`. Một lệnh đơn thường dễ hiểu hơn.

**Lệnh sau phụ thuộc kết quả lệnh trước.** Pipeline không cho đọc kết quả trung gian theo cách đồng bộ thông thường để rẽ nhánh trong callback. Nếu có invariant cần bảo đảm, dùng thao tác nguyên tử thích hợp.

**Cần nhóm lệnh không bị xen giữa.** Cân nhắc Redis `MULTI`/`EXEC`; nếu còn điều kiện kiểm tra thì `WATCH` hoặc script. Pipeline một mình không cung cấp tính chất này.

**Dữ liệu lớn và khó kiểm soát batch.** Một pipeline quá lớn có thể gây áp lực bộ nhớ và timeout. Hãy phân đoạn hoặc dùng cấu trúc dữ liệu/giải pháp streaming phù hợp.

**Logic nghiệp vụ sống ở JPA/RDBMS.** Gửi lệnh Redis bằng pipeline không biến thao tác trong PostgreSQL và Redis thành một distributed transaction. Cần outbox, invalidation sau commit hoặc cơ chế điều phối phù hợp.

**Cần code đơn giản và serializer tự động.** Nếu số thao tác ít, API `opsForValue()`, `opsForHash()`, `opsForSet()` thường rõ ràng hơn vì template tự xử lý serialization.

## 15. Ví dụ ứng dụng: nạp lại nhiều cache entry sau khi truy vấn DB

Giả sử tầng dịch vụ vừa lấy danh sách sản phẩm từ cơ sở dữ liệu nguồn và muốn đưa chúng vào Redis với TTL 10 phút. Mỗi sản phẩm có ID và payload JSON đã chuẩn hóa thành chuỗi.

```java
package com.example.redis;

public record CachedProduct(String id, String json) {
}
```

Service ghi cache theo batch:

```java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheWarmupService {

    private final StringRedisTemplate redis;

    public ProductCacheWarmupService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void warmUp(List<CachedProduct> products) {
        if (products.isEmpty()) {
            return;
        }

        RedisSerializer<String> serializer = redis.getStringSerializer();

        redis.executePipelined(
            (RedisCallback<Object>) connection -> {
                for (CachedProduct product : products) {
                    byte[] key = serializer.serialize(
                        "cache:product:" + product.id()
                    );

                    byte[] value = serializer.serialize(product.json());

                    // Mỗi SETEX ghi giá trị và TTL trong một lệnh.
                    connection.stringCommands().setEx(
                        key,
                        600L,
                        value
                    );
                }

                return null;
            }
        );
    }
}
```

Luồng hoạt động:

```text
DB query -> List<CachedProduct>
    |
    v
ProductCacheWarmupService.warmUp(products)
    |
    v
RedisTemplate.executePipelined
    |
    +-> SETEX cache:product:p101 600 <json-101>
    +-> SETEX cache:product:p102 600 <json-102>
    +-> SETEX cache:product:p103 600 <json-103>
    |
    v
Thu kết quả và kết thúc
```

Ví dụ sử dụng một pipeline cho toàn bộ input để tập trung minh họa API; với số lượng lớn cần chia batch như phần 12.

Giả định `product.json()` là chuỗi JSON **đã được chuẩn bị**. `StringRedisTemplate` chỉ chuyển chuỗi thành byte; nó không tự kiểm tra JSON có đúng schema của `Product` hay không. Khi đọc lại, cần parse JSON bằng bộ chuyển đổi domain thích hợp.

Đây là một trường hợp pipeline phù hợp vì từng cache entry có thể được ghi **độc lập**. Nếu ghi một phần rồi mất kết nối, hệ thống vẫn có thể tái tạo phần còn thiếu từ DB theo chính sách cache.

## 16. Quan sát và thử nghiệm hành vi pipeline

Khi phát triển, có thể tạo một bộ key thử nghiệm:

```redis
SET lab:pipe:a "A"
SET lab:pipe:b "B"
SET lab:pipe:c "C"
```

Gọi service đọc batch với các key tương ứng (điều chỉnh prefix trong code cho đúng), rồi so sánh giá trị trong `List<Object>` hoặc map với kết quả CLI:

```redis
GET lab:pipe:a
GET lab:pipe:b
GET lab:pipe:c
```

Để quan sát một pipeline hỗn hợp, gửi `SET`, `INCR`, `GET` rồi đọc lại key. Điều quan trọng không phải thấy chúng “chạy cùng lúc”, mà là hiểu **thứ tự lệnh và thứ tự phản hồi**.

Trong môi trường thử nghiệm, có thể quan sát số lệnh Redis và độ trễ để so sánh gọi tuần tự với pipeline. Tránh bật công cụ giám sát có chi phí lớn trên môi trường production chỉ để kiểm chứng một ví dụ đơn giản.

### 16.1. Những lỗi thường gặp khi triển khai

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Callback trả dữ liệu nhưng kết quả bị từ chối | `executePipelined` yêu cầu callback return `null` | Trả `null`, xử lý `List<Object>` bên ngoài |
| `GET` bên trong callback trả `null` | Lệnh đang được pipeline, chưa có phản hồi cuối | Đọc kết quả từ `executePipelined` |
| Đọc ngoài pipeline không thấy key vừa ghi | Serializer của raw connection khác template | Dùng serializer thống nhất; kiểm tra byte của key |
| `ClassCastException` khi ép kết quả | Pipeline có kết quả Boolean/Long/String hỗn hợp | Ánh xạ theo thứ tự và kiểu từng lệnh |
| Kết quả được gán sai ID | Thứ tự/ số lượng lệnh khác với metadata đầu vào | Giữ mapping 1–1 giữa lệnh và vị trí phản hồi |
| Batch lớn bị timeout hoặc tăng heap | Quá nhiều lệnh, value hoặc response lớn | Chia batch và đo latency/memory |
| Ghi một phần khi có lỗi | Pipeline không có rollback | Xử lý retry/idempotency hoặc dùng transaction phù hợp |
| Kết quả `GET` không đồng nhất khi client khác sửa key | Pipeline không bảo đảm isolation | Dùng mô hình đọc/ghi có điều kiện hoặc transaction nếu cần |
| Pipeline trên Redis Cluster hoạt động khác standalone | Driver routing và hash slot | Kiểm tra hỗ trợ cluster, tối ưu key placement |

## 17. Các nguyên tắc triển khai thực tế

Khi chọn `executePipelined(RedisCallback<?>)` cho một chức năng Spring Data Redis, nên làm rõ các điểm sau:

1. **Xác định các lệnh độc lập.** Nếu lệnh sau cần kết quả lệnh trước để quyết định, không xem chúng là một pipeline đơn giản.
2. **Chuẩn hóa serializer.** Khi gọi `RedisConnection` trực tiếp, luôn chuyển key/value qua serializer phù hợp với dữ liệu hệ thống.
3. **Giữ callback đơn giản.** Chỉ chuẩn bị và gửi lệnh rồi `return null`; xử lý kết quả sau khi method trả về.
4. **Giữ thứ tự rõ ràng.** Nếu dùng `List<Object>` để ghép kết quả, lưu cùng thứ tự lệnh hoặc metadata tương ứng.
5. **Giới hạn batch.** Tách lô theo kích thước dữ liệu và kết quả đo đạc, tránh tích lũy phản hồi không giới hạn.
6. **Thiết kế lỗi từng phần.** Pipeline không có rollback, nên các thao tác ghi nên idempotent hoặc có cách phục hồi phù hợp.
7. **Chọn đúng công cụ cho invariant.** Một lệnh nguyên tử, `MULTI`/`EXEC`, `WATCH`, Lua hay giao dịch DB giải quyết các yêu cầu khác với pipeline.
8. **Đo lợi ích đầu cuối.** Giảm RTT chỉ có giá trị khi tổng độ trễ và tài nguyên của hệ thống thực sự được cải thiện.

## 18. Kết luận

`executePipelined` với `RedisCallback` là cách trực tiếp để **gửi một loạt Redis commands thông qua `RedisConnection` rồi nhận các phản hồi theo lô** trong Spring Data Redis. Nó đặc biệt hữu ích với batch `GET`, `SET`, `SETEX` hoặc nhiều thao tác nhỏ độc lập, khi chi phí trao đổi mạng đáng kể.

Ba điều quan trọng nhất là:

- **Callback trả `null`**; kết quả được lấy từ `List<Object>` trả về bởi `executePipelined`.
- **Các lệnh trong `RedisCallback` dùng byte-level API**, nên serialization của key/value phải phù hợp với `RedisTemplate` và dữ liệu hiện có.
- **Pipeline không tạo transaction nguyên tử hay rollback**, và không giải quyết phép đọc–sửa–ghi có điều kiện.

Khi kết hợp hiểu đúng về callback, serializer, thứ tự phản hồi và kích thước batch, pipeline giúp Spring Data Redis xử lý nhiều thao tác nhỏ hiệu quả mà vẫn giữ ranh giới rõ ràng giữa tối ưu hiệu năng và bảo đảm tính nhất quán dữ liệu.
