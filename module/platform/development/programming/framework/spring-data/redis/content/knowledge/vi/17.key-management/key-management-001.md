# Kiểm tra tồn tại, kiểu dữ liệu và đổi tên khóa trong Spring Data Redis

## 1. Vì sao cần quản lý khóa?

Redis lưu dữ liệu theo cặp **key–value**. Mỗi khóa có một tên, một kiểu dữ liệu Redis và có thể có thời gian hết hạn (TTL). Trong ứng dụng Spring, ngoài các thao tác đọc/ghi giá trị, đôi khi cần biết một khóa còn tồn tại hay không, xác định loại dữ liệu đang nằm dưới khóa, hoặc chuyển dữ liệu sang một tên khóa mới.

Ví dụ, hệ thống có thể lưu `user:42:status` để biểu diễn trạng thái người dùng. Khi đổi quy ước đặt tên sang `profile:42:status`, ta cần hiểu chính xác việc đổi tên sẽ tác động thế nào đến khóa cũ, khóa đích và TTL. Tương tự, nếu mã nguồn mong đợi một Redis Hash nhưng khóa thực tế chứa String, thao tác đọc Hash có thể thất bại với lỗi `WRONGTYPE`.

Bài học này tập trung vào ba nhóm thao tác thuộc **keyspace**:

- **Kiểm tra tồn tại**: Redis `EXISTS`, Spring Data Redis `hasKey(...)`.
- **Xác định kiểu dữ liệu**: Redis `TYPE`, Spring Data Redis `type(...)`.
- **Đổi tên**: Redis `RENAME` / `RENAMENX`, Spring Data Redis `rename(...)` / `renameIfAbsent(...)`.

Đây là các thao tác trên **khóa**, không phải chuyển đổi kiểu dữ liệu hay biến đổi nội dung giá trị.

## 2. Hiểu các lệnh Redis trước khi dùng Spring

| Nhu cầu | Redis CLI | Ý nghĩa kết quả |
|---|---|---|
| Một khóa có tồn tại? | `EXISTS key` | `1` nếu có, `0` nếu không; dạng nhiều khóa trả về số khóa tồn tại |
| Khóa lưu kiểu gì? | `TYPE key` | `string`, `hash`, `list`, `set`, `zset`, `stream` hoặc `none` |
| Đổi tên, cho phép thay thế đích | `RENAME old new` | Đổi tên thành công trả `OK`; nếu đích có sẵn, dữ liệu đích bị thay thế |
| Đổi tên chỉ khi đích chưa có | `RENAMENX old new` | `1` nếu đổi tên, `0` nếu đích đã tồn tại |

Chạy thử trong một Redis thử nghiệm:

```redis
SET demo:user:42:state "ACTIVE"
EXISTS demo:user:42:state
# (integer) 1

TYPE demo:user:42:state
# string

TYPE demo:user:999:state
# none

RENAME demo:user:42:state demo:profile:42:state
# OK

EXISTS demo:user:42:state
# (integer) 0

EXISTS demo:profile:42:state
# (integer) 1

GET demo:profile:42:state
# "ACTIVE"
```

`RENAME` chuyển **cùng một giá trị** từ tên cũ sang tên mới: sau khi thành công, khóa nguồn không còn tồn tại. Redis không tạo thêm một bản sao để giữ cả hai tên.

Với trường hợp muốn giữ nguyên khóa đích nếu nó đã tồn tại:

```redis
SET demo:source "new-value"
SET demo:target "existing-value"

RENAMENX demo:source demo:target
# (integer) 0

GET demo:source
# "new-value"

GET demo:target
# "existing-value"
```

Nếu nguồn không tồn tại, `RENAME` và `RENAMENX` trả lỗi thay vì tự tạo dữ liệu. Vì vậy cần phân biệt ba tình huống: nguồn không có, đích đã có, và lệnh được thực hiện thành công.

## 3. Cấu hình Spring Boot và ánh xạ API

Với ứng dụng Spring Boot sử dụng Spring Data Redis, khai báo dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Ví dụ cấu hình kết nối Redis trên máy phát triển:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Spring Boot tự cấu hình `StringRedisTemplate` khi cấu hình kết nối và dependency phù hợp. Template này phù hợp để thao tác với khóa dạng chuỗi dễ đọc trong `redis-cli`. Dùng cùng một quy tắc serialize khóa ở các thành phần ghi, đọc và đổi tên; khóa được ghi bằng serializer khác có thể có biểu diễn byte khác dù trông giống nhau ở phía Java.

Ánh xạ API phổ biến:

| Spring Data Redis | Kiểu trả về | Lệnh Redis tương ứng | Ghi chú |
|---|---|---|---|
| `stringRedisTemplate.hasKey(key)` | `Boolean` | `EXISTS` | Có thể là `null` trong ngữ cảnh pipeline/transaction |
| `stringRedisTemplate.type(key)` | `DataType` | `TYPE` | `DataType.NONE` cho khóa không tồn tại khi gọi thông thường |
| `stringRedisTemplate.rename(oldKey, newKey)` | `void` | `RENAME` | **Ghi đè** khóa đích nếu đã tồn tại |
| `stringRedisTemplate.renameIfAbsent(oldKey, newKey)` | `Boolean` | `RENAMENX` | `true` khi đổi tên; `false` khi đích đã tồn tại; có thể `null` trong pipeline/transaction |

`DataType` ở đây là `org.springframework.data.redis.connection.DataType`, biểu diễn **kiểu Redis thực tế** dưới một khóa. Đây không phải `Class<?>` của đối tượng Java được ứng dụng serialize vào Redis.

## 4. Xây dựng dịch vụ quản lý khóa

Ví dụ dưới đây giả định các phương thức được gọi đồng bộ thông thường, không đặt trong Redis pipeline hoặc transaction. Vì API trả về `Boolean` dạng object, hãy tránh tự động unbox khi chưa xét đến khả năng `null`.

```java
package com.example.redis;

import org.springframework.data.redis.connection.DataType;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisKeyManagementService {

    private final StringRedisTemplate redisTemplate;

    public RedisKeyManagementService(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /** Trả true khi khóa tồn tại tại thời điểm Redis xử lý lệnh. */
    public boolean exists(String key) {
        requireKey(key);
        return Boolean.TRUE.equals(redisTemplate.hasKey(key));
    }

    /** Trả DataType.NONE nếu khóa không tồn tại ở thời điểm kiểm tra. */
    public DataType typeOf(String key) {
        requireKey(key);
        return redisTemplate.type(key);
    }

    /** Đổi tên và thay thế toàn bộ khóa đích nếu đích đã tồn tại. */
    public void renameReplacingTarget(String sourceKey, String targetKey) {
        requireDistinctKeys(sourceKey, targetKey);
        redisTemplate.rename(sourceKey, targetKey);
    }

    /** Chỉ đổi tên khi khóa đích chưa tồn tại. */
    public boolean renameIfTargetAbsent(String sourceKey, String targetKey) {
        requireDistinctKeys(sourceKey, targetKey);
        return Boolean.TRUE.equals(
                redisTemplate.renameIfAbsent(sourceKey, targetKey)
        );
    }

    private static void requireKey(String key) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("Redis key must not be blank");
        }
    }

    private static void requireDistinctKeys(String sourceKey, String targetKey) {
        requireKey(sourceKey);
        requireKey(targetKey);
        if (sourceKey.equals(targetKey)) {
            throw new IllegalArgumentException(
                    "Source and target Redis keys must be different"
            );
        }
    }
}
```

Trong ví dụ này, không cho phép tên khóa rỗng là một **quy tắc của ứng dụng** nhằm tránh gọi nhầm, không phải giới hạn bắt buộc của Redis. Ở hệ thống nhiều tenant hoặc nhiều chức năng, mã nghiệp vụ còn phải kiểm soát prefix và quyền truy cập, không nhận tùy ý tên khóa của tenant khác.

Nếu một hệ thống dùng `RedisTemplate<String, MyObject>` thay cho `StringRedisTemplate`, các thao tác keyspace tương tự vẫn có trên `RedisTemplate`. Điểm cần kiểm tra là **key serializer**. Ví dụ, khóa dùng JDK serializer sẽ không được Redis lưu bằng chính chuỗi UTF-8 nhìn thấy trong Java; `redis-cli EXISTS my:key` có thể trả `0` dù ứng dụng đang đọc được bằng đúng serializer của nó.

## 5. Kiểm tra một khóa có tồn tại: hasKey

Giả sử mã ứng dụng lưu trạng thái phiên:

```java
String sessionKey = "demo:session:7";
redisTemplate.opsForValue().set(sessionKey, "ACTIVE");

boolean present = keyService.exists(sessionKey);  // true
boolean absent = keyService.exists("demo:session:missing"); // false
```

`hasKey` chỉ cho biết khóa **tồn tại tại thời điểm lệnh được Redis xử lý**. Nó không đảm bảo khóa vẫn còn khi lệnh tiếp theo chạy: TTL có thể hết hạn hoặc một client khác có thể xóa, ghi đè hay đổi tên khóa giữa hai lệnh.

Vì vậy, tránh dùng kiểu suy luận sau để bảo đảm một thao tác liên tiếp sẽ thành công:

```java
// Hai lệnh riêng biệt, trạng thái có thể thay đổi ở giữa.
if (keyService.exists(sourceKey)) {
    keyService.renameReplacingTarget(sourceKey, targetKey);
}
```

Ví dụ trên vẫn có thể thất bại nếu nguồn bị xóa trước `RENAME`. Trong trường hợp chỉ cần đọc giá trị, nên dùng ngay thao tác đọc phù hợp (và xử lý kết quả không có); không cần luôn gọi `hasKey` trước. Khi cần đổi tên có điều kiện theo trạng thái của **đích**, sử dụng `renameIfAbsent` để Redis kiểm tra và đổi tên trong **một lệnh nguyên tử**.

Lưu ý: `Boolean.TRUE.equals(...)` trả `false` khi Spring nhận `null`. Cách viết này tránh `NullPointerException` trong gọi đồng bộ, nhưng **không nên dùng giá trị trả về của những phương thức này để kết luận nghiệp vụ ngay trong pipeline/transaction**, vì `null` có thể chỉ là kết quả chưa được materialize. Hãy xử lý kết quả được trả về sau khi pipeline hoặc transaction hoàn tất.

## 6. Kiểm tra kiểu Redis: type

Các kiểu thường gặp và API thao tác tương ứng:

| `TYPE` trong Redis | `DataType` trong Spring | Ví dụ Spring Data Redis |
|---|---|---|
| `string` | `DataType.STRING` | `opsForValue()` |
| `hash` | `DataType.HASH` | `opsForHash()` |
| `list` | `DataType.LIST` | `opsForList()` |
| `set` | `DataType.SET` | `opsForSet()` |
| `zset` | `DataType.ZSET` | `opsForZSet()` |
| `stream` | `DataType.STREAM` | `opsForStream()` |
| `none` | `DataType.NONE` | Khóa không tồn tại |

Tạo thử một khóa Hash:

```java
String key = "demo:user:42";
redisTemplate.opsForHash().put(key, "name", "Linh");
redisTemplate.opsForHash().put(key, "role", "reader");

DataType dataType = keyService.typeOf(key);
System.out.println(dataType); // HASH

DataType missingType = keyService.typeOf("demo:user:missing");
System.out.println(missingType); // NONE
```

Một trường hợp cần kiểm soát schema:

```java
DataType actual = keyService.typeOf("demo:user:42");

if (actual == DataType.NONE) {
    // Chưa có khóa: xử lý tình huống dữ liệu vắng mặt.
} else if (actual != DataType.HASH) {
    throw new IllegalStateException(
            "Expected Redis HASH but found " + actual
    );
} else {
    // Có thể thao tác như HASH, tùy thuộc trạng thái tại thời điểm gọi.
}
```

Nếu gọi `opsForHash()` trên một khóa thực tế có kiểu String, Redis thường báo lỗi `WRONGTYPE Operation against a key holding the wrong kind of value`. `type(...)` hỗ trợ chẩn đoán và kiểm tra tiền điều kiện, nhưng không loại bỏ hoàn toàn thay đổi đồng thời giữa các lệnh.

Redis `TYPE` mô tả **kiểu lưu trữ của value trong Redis**. Chẳng hạn một object Java được serialize thành JSON rồi ghi qua `opsForValue().set(...)` vẫn là Redis `string`; nó không tự trở thành Redis `hash` chỉ vì JSON chứa nhiều trường.

## 7. Đổi tên có ghi đè: rename

`rename(source, target)` ánh xạ sang `RENAME`:

- Sau khi thành công, **nguồn biến mất**, đích trỏ đến dữ liệu trước đó của nguồn.
- Nếu đích đã tồn tại, **dữ liệu cũ của đích bị thay thế**. Đừng gọi cách này khi cần bảo toàn giá trị đích.
- **Kiểu dữ liệu của nguồn không đổi**: một Redis Hash vẫn là Hash ở tên mới.
- **TTL của nguồn được giữ lại trên tên mới**; nếu đích từng có TTL riêng, TTL đó không còn áp dụng vì giá trị đích cũ đã bị thay thế.
- Nếu nguồn không tồn tại, Redis trả lỗi; Spring thường chuyển lỗi thành một ngoại lệ thuộc hệ `DataAccessException`.

Ví dụ chạy với dữ liệu thử nghiệm:

```java
String oldKey = "demo:account:42:legacy";
String newKey = "demo:account:42:current";

redisTemplate.opsForValue().set(oldKey, "ACTIVE");
redisTemplate.opsForValue().set(newKey, "STALE");

keyService.renameReplacingTarget(oldKey, newKey);

// oldKey không còn; newKey chứa "ACTIVE".
// Giá trị "STALE" trước đó ở newKey đã bị thay thế.
```

Có thể quan sát trực tiếp TTL trước và sau đổi tên:

```redis
SET demo:otp:old "123456" EX 120
TTL demo:otp:old
# Một số giây dương, tối đa gần 120

RENAME demo:otp:old demo:otp:new
# OK

TTL demo:otp:old
# (integer) -2  (khóa không tồn tại)

TTL demo:otp:new
# Một số giây dương còn lại của hạn dùng ban đầu
```

Khi `TTL` trả `-1` nghĩa là khóa có tồn tại nhưng không có thời hạn; `-2` nghĩa là khóa không tồn tại. TTL còn lại luôn giảm theo thời gian, không nên kiểm tra bằng cách mong đợi chính xác cùng một số giây trước và sau thao tác.

`RENAME` là thao tác nguyên tử tại Redis trong phạm vi lệnh đó. Tuy nhiên, các bước nghiệp vụ trước và sau `RENAME` (chẳng hạn cập nhật bản ghi cơ sở dữ liệu khác) **không tự động** trở thành một transaction phân tán.

## 8. Đổi tên an toàn khi đích chưa tồn tại: renameIfAbsent

Nếu không được phép ghi đè đích, dùng `renameIfAbsent(source, target)`, tương ứng `RENAMENX`:

```java
String draft = "demo:report:42:draft";
String published = "demo:report:42:published";

redisTemplate.opsForValue().set(draft, "draft-content");
redisTemplate.opsForValue().set(published, "approved-content");

boolean renamed = keyService.renameIfTargetAbsent(draft, published);

System.out.println(renamed); // false vì published đã tồn tại
// draft vẫn giữ "draft-content"; published giữ "approved-content".
```

Khi không có đích, kết quả thành công là `true`, nguồn sẽ biến mất và đích mới chứa nội dung cùng TTL từ nguồn.

Tại sao không tự ghép hai lệnh?

```java
// Không bảo đảm tránh ghi đè trong điều kiện đồng thời.
if (!keyService.exists(targetKey)) {
    keyService.renameReplacingTarget(sourceKey, targetKey);
}
```

Giữa lần kiểm tra và `RENAME`, tiến trình khác có thể tạo `targetKey`. Khi đó `RENAME` vẫn ghi đè nó. `RENAMENX` giải quyết chính xác điều kiện **đích chưa tồn tại** trong một lần xử lý trên Redis.

Dù `RENAMENX` là nguyên tử, nếu nguồn biến mất trước lúc Redis nhận lệnh thì thao tác vẫn có thể thất bại. Ứng dụng phải quyết định có cần retry, báo thiếu dữ liệu hay xem đây là tình huống bình thường. Không nên coi tất cả ngoại lệ khi đổi tên là “đích đã tồn tại”; trường hợp đó được biểu diễn bằng `false` khi gọi thông thường.

## 9. Redis Cluster, khóa có TTL và quy ước đặt tên

### Giới hạn trong Redis Cluster

Trong Redis Cluster, `RENAME` và `RENAMENX` yêu cầu hai khóa nằm trong **cùng hash slot**. Các khóa khác slot có thể gây lỗi `CROSSSLOT`.

Hash tag trong tên khóa giúp điều hướng các khóa liên quan vào cùng slot:

```text
profile:{user:42}:draft
profile:{user:42}:active
```

Hai tên trên có cùng phần `{user:42}` nên được tính slot theo cùng nội dung tag. Chỉ sử dụng hash tag có chủ đích; thiết kế tag quá rộng có thể làm dữ liệu phân bố không đều giữa các shard. Ngoài Redis Cluster, quy tắc cùng slot này không phải vấn đề đối với Redis standalone.

### TTL và vòng đời khóa

- Khóa có thể tự hết hạn giữa `hasKey` và `type` / `rename`.
- `RENAME` đưa TTL của **nguồn** sang tên đích; TTL trước đó của đích không được giữ nếu đích bị thay thế.
- Kiểm tra `EXISTS` sau khi TTL hết hạn là kiểm tra trạng thái hiện tại, không phải bằng chứng rằng dữ liệu chưa từng được ghi.
- Nếu một workflow cần “chuyển trạng thái” đồng thời với nhiều điều kiện trên nội dung value, nên cân nhắc một lệnh nguyên tử phù hợp hoặc Lua script thay vì ghép nhiều lần kiểm tra độc lập.

### Namespace và an toàn dữ liệu

Nên dùng tên khóa có cấu trúc, chẳng hạn `app:entity:id:purpose`, để tránh xung đột giữa các chức năng. Trong ứng dụng nhiều tenant, cần xác thực cả **khóa nguồn lẫn khóa đích** trước khi đổi tên. Không nên xuất một API HTTP cho phép client tùy ý truyền hai khóa Redis, vì thao tác có thể ghi đè dữ liệu của người dùng khác.

## 10. Các lỗi dễ gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `hasKey` trả `false` dù tưởng đã ghi | Sai prefix, khác Redis database, khác serializer hoặc khóa đã hết TTL | Kiểm tra cách tạo key, cấu hình kết nối và TTL |
| `type` trả `DataType.NONE` | Khóa không tồn tại ở thời điểm gọi | Xử lý trường hợp dữ liệu vắng mặt |
| `WRONGTYPE` khi dùng `opsForHash` hoặc `opsForValue` | Loại giá trị trong Redis khác loại được API đọc mong đợi | Xác định `TYPE` thực tế và thống nhất schema/key namespace |
| `rename` làm mất dữ liệu tại đích | `RENAME` cho phép ghi đè | Dùng `renameIfAbsent` nếu phải bảo toàn đích |
| `renameIfAbsent` trả `false` | Đích đã tồn tại | Giữ nguyên dữ liệu và quyết định nghiệp vụ xử lý xung đột |
| Đổi tên báo lỗi khi nguồn không có | Khóa hết hạn, bị xóa hoặc đổi tên trước đó | Xử lý lỗi nguồn vắng mặt; không mặc định xem đây là xung đột đích |
| Redis Cluster báo `CROSSSLOT` | Nguồn và đích ở hai slot khác nhau | Thiết kế khóa cùng hash slot, cân nhắc hash tag |
| Redis CLI không tìm thấy khóa mà Spring đọc được | Key serializer không tương thích chuỗi CLI | Dùng hoặc kiểm tra cùng serializer, thường là `StringRedisTemplate` cho ví dụ chuỗi |
| Kết quả `Boolean` là `null` trong pipeline/transaction | Kết quả chưa sẵn có tại thời điểm gọi | Đọc kết quả sau khi hoàn tất pipeline/transaction |

## 11. Khi nào chọn thao tác nào?

- Chọn **`hasKey`** khi thật sự cần một câu trả lời tồn tại tại thời điểm kiểm tra, ví dụ để hiển thị trạng thái hoặc hỗ trợ chẩn đoán. Không dùng nó như khóa đồng bộ cho một lệnh riêng tiếp theo.
- Chọn **`type`** khi cần phân biệt Redis String, Hash, List, Set, Sorted Set hoặc Stream, nhất là khi kiểm tra dữ liệu cũ hoặc chẩn đoán `WRONGTYPE`. Với khóa được thiết kế tốt, kiểu dữ liệu nên ổn định theo namespace.
- Chọn **`rename`** khi việc **thay thế khóa đích** là chủ ý và đã được kiểm soát; hiểu rằng nguồn không còn sau khi thành công.
- Chọn **`renameIfAbsent`** khi giá trị đích phải được bảo toàn nếu đã tồn tại. Đây là cách kiểm tra điều kiện tồn tại của đích và đổi tên một cách nguyên tử.

Các phương thức trên giúp quản lý tên và loại khóa rõ ràng trong Spring Data Redis. Thiết kế đúng cần đi cùng quy ước tên khóa, serializer nhất quán, chính sách TTL và xử lý cạnh tranh giữa nhiều client.
