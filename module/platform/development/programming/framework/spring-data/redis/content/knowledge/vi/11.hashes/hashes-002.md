# Ghi, đọc và xóa trường bằng HashOperations

Trong **Spring Data Redis**, `HashOperations` là API dùng để thao tác với các **field (trường)** nằm bên trong một **Redis Hash**. Nếu một đối tượng có nhiều thuộc tính và ứng dụng thường đọc hoặc sửa riêng từng thuộc tính, Redis Hash giúp tránh phải đọc rồi ghi lại toàn bộ đối tượng mỗi lần thay đổi một trường.

Ba thao tác cơ bản nhất của bài học:

- **Ghi trường:** `hashOperations.put(redisKey, field, value)`, tương ứng với lệnh Redis `HSET`.
- **Đọc trường:** `hashOperations.get(redisKey, field)`, tương ứng với `HGET`.
- **Xóa trường:** `hashOperations.delete(redisKey, field)`, tương ứng với `HDEL`.

Ví dụ, một ứng dụng có thể lưu cài đặt của người dùng:

~~~text
Redis key: user:42:settings
Redis type: Hash

Field       Value
----------  --------
language    vi
theme       dark
timezone    Asia/Ho_Chi_Minh
~~~

Muốn đổi giao diện từ `dark` sang `light`, ứng dụng chỉ cần cập nhật field `theme` của Hash `user:42:settings`. Nó không cần lấy cả Hash, chuyển thành object, chỉnh sửa rồi ghi đè toàn bộ.

## 1. Redis Hash là gì?

**Redis Hash** lưu nhiều cặp **field → value** bên trong **một Redis key**. Về cách hình dung, nó gần với `Map<String, String>` trong Java, nhưng dữ liệu thật nằm ở Redis Server và được truy cập qua các lệnh Redis.

~~~text
                         Redis Server
                +-----------------------------+
                | Key: user:42:settings       |
                | Type: Hash                  |
                |                             |
                | language  -> "vi"            |
                | theme     -> "dark"          |
                | timezone  -> "Asia/..."      |
                +-----------------------------+
                       ^          ^       ^
                       |          |       |
               HSET theme     HGET theme  HDEL theme
~~~

**Phân biệt ba khái niệm quan trọng:**

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Redis key | `user:42:settings` | Định danh **toàn bộ Hash** trong Redis |
| Hash field (hash key) | `theme` | Định danh **một trường** bên trong Hash |
| Hash value | `dark` | Giá trị của field đó |

Redis key và Hash field đều có thể được biểu diễn bằng `String` ở phía Java, nhưng **không phải cùng một cấp**. Redis key chọn một Hash; field chọn một phần tử bên trong Hash.

Một Redis Hash có thể chứa các field như `firstName`, `lastName`, `locale`, `lastSeen`. Các field không phải bảng quan hệ, không có SQL JOIN và không tự có schema hoặc cơ chế validation đối tượng. Ứng dụng vẫn chịu trách nhiệm kiểm tra dữ liệu, định nghĩa tên field và kiểu giá trị.

### 1.1. Các lệnh Redis tương ứng

Có thể thử trên Redis Server dùng riêng cho môi trường học:

~~~bash
HSET user:42:settings language vi theme dark
HGET user:42:settings theme
HSET user:42:settings theme light
HGET user:42:settings theme
HDEL user:42:settings language
HGETALL user:42:settings
~~~

Kết quả minh họa:

~~~text
HSET lần đầu: thêm hai field, trả 2
HGET theme: "dark"
HSET theme light: cập nhật field đã tồn tại, trả 0
HGET theme: "light"
HDEL language: xóa một field, trả 1
HGETALL: còn field theme = "light"
~~~

`HSET` có thể **thêm field mới hoặc cập nhật field đã tồn tại**. Nó không thất bại chỉ vì field đã tồn tại. Giá trị trả về của Redis `HSET` đếm **số field được thêm mới**, không phải số field có giá trị bị thay đổi. Trong Spring Data Redis, phương thức `HashOperations.put(...)` tập trung vào thao tác ghi và thường có kiểu trả về `void`.

## 2. HashOperations nằm ở đâu trong Spring Data Redis?

Luồng khái niệm:

~~~text
ProfileService / SettingsService
             |
             | hashOps.put / get / delete
             v
   HashOperations<K, HK, HV>
             |
             v
         RedisTemplate
             |
             | serialize Redis key, hash field, hash value
             v
    RedisConnectionFactory
             |
             v
      Lettuce hoặc Jedis
             |
             | HSET / HGET / HDEL qua mạng
             v
          Redis Server
             |
             v
     Hash được lưu và thay đổi
~~~

Ở đây:

- **Redis Server** thực sự thực thi `HSET`, `HGET` và `HDEL`.
- **Lettuce/Jedis** là Redis driver truyền lệnh và nhận phản hồi.
- **RedisConnectionFactory** cung cấp kết nối cho Spring Data Redis.
- **RedisTemplate** quản lý cách thực thi các thao tác Redis, serializer và vòng đời kết nối.
- **HashOperations** cung cấp API Java theo cấu trúc Hash để mã nghiệp vụ không phải tự chuyển lệnh thành bytes.

### 2.1. Các generic của HashOperations

Khai báo thường gặp:

~~~java
HashOperations<K, HK, HV>
~~~

| Tham số | Vai trò | Ví dụ |
|---|---|---|
| `K` | Kiểu của Redis key | `String` cho `user:42:settings` |
| `HK` | Kiểu của Hash field | `String` cho `theme` |
| `HV` | Kiểu của Hash value | `String` cho `dark` |

Với `StringRedisTemplate`:

~~~java
HashOperations<String, String, String> hashOps =
        stringRedisTemplate.opsForHash();
~~~

Cả Redis key, Hash field và Hash value đều được xử lý như chuỗi phía Java. Nếu dùng `RedisTemplate<String, UserSetting>` hoặc template tùy chỉnh, cách khai báo generic và **serializer** phải tương thích với dữ liệu cần lưu.

**Không nhầm `HK` với `K`:** cả hai trong ví dụ đều có kiểu String, nhưng `K` định danh Hash, còn `HK` định danh field thuộc Hash đó.

## 3. Chuẩn bị ứng dụng Spring Boot

### 3.1. Thêm dependency

Với Spring Boot 3.x dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Starter này cung cấp Spring Data Redis và hạ tầng Redis client. Mặc định thông dụng, Spring Boot dùng Lettuce làm driver nếu không chọn driver khác.

**Redis Server phải có sẵn và truy cập được.** Chỉ thêm starter không có nghĩa JVM sẽ tự chạy Redis Server.

### 3.2. Cấu hình Redis endpoint

Ví dụ `src/main/resources/application.yml`:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

`localhost` chỉ phù hợp khi Spring Boot nhìn thấy Redis qua chính môi trường chạy đó. Nếu Spring Boot và Redis chạy trong hai container Docker Compose riêng biệt, host thường là **tên service Redis** trong network Compose, chẳng hạn `redis`. Với dịch vụ Redis được quản lý, cấu hình địa chỉ, xác thực và TLS theo endpoint thực tế.

Spring Boot 3.x thường auto-configure bean `StringRedisTemplate` khi dependency và cấu hình phù hợp. Ta inject bean này vào service:

~~~java
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SettingsStore {

    private final HashOperations<String, String, String> hashOps;

    public SettingsStore(StringRedisTemplate redis) {
        this.hashOps = redis.opsForHash();
    }
}
~~~

Phương thức `opsForHash()` trả về abstraction cho Hash và có thể được sử dụng lại. Nó **không tự tạo một Hash** trên Redis chỉ vì ứng dụng đã gọi phương thức này. Redis key được tạo khi có lệnh ghi phù hợp.

## 4. Ghi một trường bằng put()

API cơ bản:

~~~java
hashOps.put(redisKey, hashField, value);
~~~

Ví dụ:

~~~java
hashOps.put("user:42:settings", "theme", "dark");
~~~

Redis thực hiện thao tác tương đương:

~~~text
HSET user:42:settings theme dark
~~~

**Trường hợp A — Hash chưa tồn tại:** Redis tạo một key kiểu Hash rồi thêm field `theme` và value `dark`.

**Trường hợp B — Hash đã có nhưng field `theme` chưa có:** Redis thêm field `theme`, giữ các field khác.

**Trường hợp C — Field `theme` đã tồn tại:** Redis thay giá trị field đó bằng `dark` mới, giữ các field khác.

**Trường hợp D — Redis key đã tồn tại nhưng có kiểu khác, ví dụ String:** thao tác Hash có thể lỗi `WRONGTYPE`. Redis không tự chuyển một String key sang Hash khi nhận HSET.

### 4.1. Thêm field và cập nhật field dùng cùng một put()

~~~java
String redisKey = "user:42:settings";

hashOps.put(redisKey, "language", "vi");
hashOps.put(redisKey, "theme", "dark");

// Cập nhật một field đã tồn tại.
hashOps.put(redisKey, "theme", "light");
~~~

Sau các lệnh:

~~~text
user:42:settings
  language -> "vi"
  theme    -> "light"
~~~

Field `language` không bị thay đổi bởi việc ghi `theme`.

### 4.2. put() và việc ghi cả đối tượng

Ghi riêng field bằng `HSET` khác với ghi toàn bộ đối tượng dưới dạng JSON:

~~~text
String JSON:
  SET user:42:settings '{"language":"vi","theme":"light"}'
  -> thay toàn bộ String payload

Redis Hash:
  HSET user:42:settings theme light
  -> chỉ thay một field của Hash
~~~

Khi ứng dụng thường cập nhật một hoặc vài thuộc tính, Hash giúp giảm việc phải gửi/serialize cả object. Nếu ứng dụng luôn đọc và ghi nguyên snapshot nhỏ, một String JSON vẫn có thể là lựa chọn đơn giản hơn. Hãy chọn cách lưu theo access pattern thực tế.

## 5. Đọc một trường bằng get()

API:

~~~java
HV value = hashOps.get(redisKey, hashField);
~~~

Với String:

~~~java
String theme =
        hashOps.get("user:42:settings", "theme");
~~~

Tương ứng:

~~~text
HGET user:42:settings theme
~~~

Nếu field tồn tại, `get()` trả về giá trị đã được deserialize. Nếu Redis key không tồn tại hoặc field không tồn tại, **kết quả thông thường là `null`**.

### 5.1. get() trả null: có hai tình huống thường gặp

~~~java
String value = hashOps.get(
        "user:42:settings", "timezone");
~~~

`null` có thể có nghĩa:

1. Hash `user:42:settings` không tồn tại vì chưa được tạo, bị xóa hoặc hết TTL.
2. Hash có tồn tại, nhưng field `timezone` chưa được ghi hoặc đã bị `HDEL`.

Nếu chỉ cần áp dụng giá trị mặc định, service có thể xử lý cả hai trường hợp như nhau:

~~~java
String language =
        hashOps.get("user:42:settings", "language");

String effectiveLanguage =
        language != null ? language : "vi";
~~~

Nhưng nếu nghiệp vụ phải phân biệt **“hồ sơ chưa tồn tại”** và **“hồ sơ có nhưng thiếu field”**, cần kiểm tra thêm sự tồn tại của Redis key hoặc trạng thái aggregate theo quy tắc của ứng dụng.

### 5.2. Kiểm tra field tồn tại bằng hasKey()

`HashOperations.hasKey(...)` kiểm tra field bên trong Hash:

~~~java
Boolean exists = hashOps.hasKey(
        "user:42:settings", "theme");

if (Boolean.TRUE.equals(exists)) {
    System.out.println("Trường theme tồn tại");
}
~~~

Phương thức này tương ứng với ý tưởng của lệnh Redis `HEXISTS`. Nó khác với `redis.hasKey(redisKey)`, dùng để kiểm tra sự tồn tại của **toàn bộ Redis key**.

~~~java
boolean hashExists = Boolean.TRUE.equals(
        redis.hasKey("user:42:settings"));

boolean themeExists = Boolean.TRUE.equals(
        hashOps.hasKey("user:42:settings", "theme"));
~~~

Lưu ý rằng kết quả kiểm tra và thao tác sau đó **không được khóa lại với nhau**. Một client khác có thể xóa field ngay sau khi `hasKey()` trả true. Nếu nghiệp vụ cần xử lý một điều kiện đồng thời một cách atomic, phải dùng lệnh Redis có điều kiện hoặc cơ chế thích hợp, không chỉ `hasKey() → put()`.

## 6. Xóa một trường bằng delete()

API:

~~~java
Long removedCount =
        hashOps.delete(redisKey, hashField);
~~~

Ví dụ:

~~~java
Long deleted = hashOps.delete(
        "user:42:settings",
        "theme");
~~~

Tương ứng:

~~~text
HDEL user:42:settings theme
~~~

`HDEL` xóa **field theme** chứ không xóa các field khác trong Hash.

Ví dụ trước khi xóa:

~~~text
user:42:settings
  language -> "vi"
  theme    -> "light"
  timezone -> "Asia/Ho_Chi_Minh"
~~~

Sau `HDEL user:42:settings theme`:

~~~text
user:42:settings
  language -> "vi"
  timezone -> "Asia/Ho_Chi_Minh"
~~~

### 6.1. Giá trị trả về của delete()

`delete(...)` trả về số field thực sự được xóa, thông thường qua `Long`:

| Tình huống | Kết quả Redis HDEL | Ý nghĩa |
|---|---:|---|
| Field tồn tại | 1 | Đã xóa một field |
| Field không tồn tại | 0 | Không có field tương ứng để xóa |
| Hash key không tồn tại | 0 | Không có dữ liệu tương ứng |
| Xóa nhiều field, có hai field tồn tại | 2 | Đã xóa hai field |

Trong một số ngữ cảnh pipeline/transaction, API Spring Data Redis có thể trả `null` cho một lời gọi chưa có kết quả ngay. Với lời gọi đồng bộ thông thường:

~~~java
Long removed = hashOps.delete(key, "theme");

if (removed != null && removed > 0) {
    System.out.println("Đã xóa field theme");
}
~~~

Lệnh xóa một field không tồn tại thường không phải lỗi. Điều này làm `HDEL` hữu ích trong những quy trình cleanup có tính idempotent.

### 6.2. Xóa nhiều field trong một lệnh

`HashOperations.delete(...)` có tham số varargs:

~~~java
Long deleted = hashOps.delete(
        "user:42:settings",
        "theme",
        "timezone");
~~~

Tương ứng:

~~~text
HDEL user:42:settings theme timezone
~~~

Kết quả đếm **các field thực sự tồn tại và đã được xóa**, không phải tổng số tên field truyền vào.

### 6.3. Khi xóa field cuối cùng thì sao?

Redis không giữ một Hash rỗng như một giá trị độc lập theo cách thông thường. Khi `HDEL` xóa **field cuối cùng**, key Hash đó cũng biến mất khỏi keyspace:

~~~bash
HSET demo:single only-field only-value
HDEL demo:single only-field
EXISTS demo:single
~~~

Kết quả `EXISTS` thường là `0` sau khi xóa field cuối. Vì vậy, đừng thiết kế quy tắc nghiệp vụ dựa trên giả định “Hash vẫn tồn tại khi đã xóa hết field”.

### 6.4. HDEL khác DEL

~~~text
HDEL user:42:settings theme
    -> xóa field theme, giữ các field khác

DEL user:42:settings
    -> xóa toàn bộ Redis key, bao gồm mọi field
~~~

Trong Spring:

~~~java
// Xóa một trường.
hashOps.delete("user:42:settings", "theme");

// Xóa toàn bộ Redis Hash.
redis.delete("user:42:settings");
~~~

Chọn đúng thao tác theo ý định. Với một phiên người dùng cần thu hồi toàn bộ, `redis.delete(key)` có thể phù hợp. Với thay đổi một cài đặt, `hashOps.delete(key, field)` phù hợp hơn.

## 7. Ví dụ service hoàn chỉnh: quản lý cài đặt người dùng

Đây là một service Spring Boot minh họa các thao tác quan trọng trên cùng Hash:

~~~java
package com.example.redislearning;

import java.util.Collection;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserSettingsHashService {

    private final StringRedisTemplate redis;
    private final HashOperations<String, String, String> hashOps;

    public UserSettingsHashService(StringRedisTemplate redis) {
        this.redis = redis;
        this.hashOps = redis.opsForHash();
    }

    private String key(String userId) {
        return "user:" + userId + ":settings";
    }

    // Ghi mới hoặc ghi đè giá trị của một field.
    public void putSetting(
            String userId,
            String field,
            String value) {
        hashOps.put(key(userId), field, value);
    }

    // Đọc một field, trả null nếu không tìm thấy.
    public String getSetting(String userId, String field) {
        return hashOps.get(key(userId), field);
    }

    // Phân biệt field đang tồn tại và field bị thiếu.
    public boolean containsField(String userId, String field) {
        return Boolean.TRUE.equals(
                hashOps.hasKey(key(userId), field));
    }

    // Xóa một hoặc nhiều field, trả số field thực sự đã xóa.
    public long removeSettings(String userId, String... fields) {
        Long count = hashOps.delete(
                key(userId), (Object[]) fields);
        return count == null ? 0L : count;
    }

    // Ghi nhiều field thuộc cùng Hash.
    public void putAllSettings(
            String userId,
            Map<String, String> settings) {
        hashOps.putAll(key(userId), settings);
    }

    // Đọc một danh sách field đã biết.
    public List<String> getSelectedSettings(
            String userId,
            Collection<String> fields) {
        return hashOps.multiGet(key(userId), fields);
    }

    // Chỉ dùng khi Hash dự kiến có kích thước nhỏ/hữu hạn.
    public Map<String, String> getAllSettings(String userId) {
        return hashOps.entries(key(userId));
    }

    // Xóa toàn bộ Hash của user.
    public void removeAllSettings(String userId) {
        redis.delete(key(userId));
    }
}
~~~

### 7.1. Thử gọi service

~~~java
settings.putSetting("42", "language", "vi");
settings.putSetting("42", "theme", "dark");
settings.putSetting("42", "timezone", "Asia/Ho_Chi_Minh");

String themeBefore = settings.getSetting("42", "theme");
// themeBefore = "dark"

settings.putSetting("42", "theme", "light");

String themeAfter = settings.getSetting("42", "theme");
// themeAfter = "light"

boolean languageExists =
        settings.containsField("42", "language");
// languageExists = true

long removed = settings.removeSettings("42", "language");
// removed = 1 nếu field vừa tồn tại

String languageAfter = settings.getSetting("42", "language");
// languageAfter = null
~~~

Tất cả các lệnh đều dùng Redis key `user:42:settings`, nhưng chọn **field khác nhau**. Việc đặt tên key tập trung trong phương thức `key(...)` giúp tránh ghi nhầm namespace.

### 7.2. Chú ý đầu vào của service

Ví dụ phục vụ học tập, nên nhìn rõ API trước khi thêm validation. Trong ứng dụng thực tế:

- `userId` phải được lấy từ ngữ cảnh xác thực hoặc được kiểm tra quyền, không mặc định tin tưởng ID do client cung cấp.
- `field` nên thuộc danh sách trường cho phép, tránh người dùng ghi một field không nằm trong schema nghiệp vụ.
- `value` cần được kiểm tra định dạng/giới hạn kích thước; ví dụ `theme` chỉ nhận `dark` hoặc `light`.
- Không đặt thông tin bí mật thô trong tên Redis key/field vì chúng có thể xuất hiện trong log và công cụ quan sát.
- Nếu có nhiều tenant, namespace và chính sách truy cập phải được thiết kế để ngăn việc truy cập chéo dữ liệu.

**Redis Hash không tự kiểm tra business schema.** Đó là trách nhiệm của service hoặc tầng domain.

## 8. Ghi nhiều trường bằng putAll()

Khi có một tập giá trị cùng thuộc một Hash, `putAll(...)` tiện hơn gọi `put(...)` lần lượt:

~~~java
Map<String, String> preferences = Map.of(
        "language", "vi",
        "theme", "dark",
        "notifications", "enabled"
);

hashOps.putAll(
        "user:42:settings",
        preferences);
~~~

Spring Data Redis gửi một thao tác ghi nhiều field tương ứng các lệnh Hash hỗ trợ nhiều cặp field/value, thay vì buộc code gọi `put` cho từng field.

Một cách biểu diễn từ Redis CLI:

~~~bash
HSET user:42:settings language vi theme dark notifications enabled
~~~

### 8.1. putAll có xóa các field cũ không?

**Không.** Đây là thao tác **ghi thêm/ghi đè các field được chỉ định**, không phải “thay toàn bộ Hash bằng Map mới”.

Giả sử Redis có:

~~~text
language = vi
theme = dark
timezone = Asia/Ho_Chi_Minh
~~~

Gọi:

~~~java
hashOps.putAll(
        "user:42:settings",
        Map.of("theme", "light"));
~~~

Kết quả:

~~~text
language = vi
theme = light
timezone = Asia/Ho_Chi_Minh
~~~

Field `language` và `timezone` còn nguyên.

Nếu yêu cầu **đồng bộ toàn bộ Hash theo snapshot mới**, cần thiết kế rõ cách xử lý những field không còn trong snapshot, ví dụ xóa field đã bỏ bằng `HDEL`. Không nên hiểu `putAll` như thay toàn bộ bản ghi SQL hoặc replace whole object.

### 8.2. Tính atomic của nhiều field

Một Redis command có thể ghi nhiều cặp field/value trong một lần thực thi; đây là ranh giới atomic của **một command**. Ngược lại, các lời gọi `put(...)` trong vòng lặp vẫn là nhiều command độc lập.

Nếu nghiệp vụ cần thao tác kiểm tra điều kiện phức tạp rồi ghi nhiều field, chỉ dùng `putAll(...)` chưa đủ; có thể cần Lua script hoặc transaction với ngữ nghĩa thích hợp.

## 9. Đọc nhiều trường mà không tải toàn bộ Hash

Khi chỉ cần một vài field đã biết, dùng `multiGet(...)`:

~~~java
List<String> fields = List.of(
        "theme", "language", "timezone");

List<String> values = hashOps.multiGet(
        "user:42:settings",
        fields);
~~~

Ý tưởng Redis tương ứng:

~~~text
HMGET user:42:settings theme language timezone
~~~

Danh sách kết quả phản ánh các field đã yêu cầu theo thứ tự, với giá trị `null` cho field thiếu trong trường hợp thông thường.

Ví dụ:

~~~text
Fields: [theme, language, timezone]
Values: [light, null, Asia/Ho_Chi_Minh]
~~~

Ở đây field `language` đã bị xóa nên có giá trị null.

### 9.1. Khi nào dùng get(), multiGet() và entries()?

| Nhu cầu | API | Lệnh Redis tương ứng |
|---|---|---|
| Chỉ đọc một field | `get(key, field)` | HGET |
| Đọc một số field có tên biết trước | `multiGet(key, fields)` | HMGET |
| Đọc tất cả field | `entries(key)` | HGETALL |
| Chỉ muốn biết field có tồn tại không | `hasKey(key, field)` | HEXISTS |
| Chỉ cần số field | `size(key)` | HLEN |
| Chỉ cần tên tất cả field | `keys(key)` | HKEYS |
| Chỉ cần toàn bộ value | `values(key)` | HVALS |

`entries(...)` tiện cho Hash nhỏ như cài đặt UI có vài field:

~~~java
Map<String, String> all =
        hashOps.entries("user:42:settings");
~~~

Nhưng với Hash rất lớn, `HGETALL` chuyển toàn bộ field/value về ứng dụng và có chi phí tăng theo kích thước Hash. Nếu màn hình chỉ cần ba thuộc tính, `multiGet(...)` thường thích hợp hơn.

**Không dùng `HGETALL` mặc định trên Hash có thể chứa hàng trăm nghìn field**, chỉ vì API trả Map thuận tiện. Khi aggregate lớn, xem xét thiết kế lại ranh giới key, giới hạn dữ liệu, hoặc duyệt có kiểm soát bằng HSCAN theo nhu cầu.

## 10. Đọc hoặc xóa field không tồn tại

HashOperations có nhiều thao tác thân thiện với key/field chưa tồn tại:

~~~java
String missing = hashOps.get(
        "user:42:settings", "doesNotExist");
// Thông thường: null

Boolean exists = hashOps.hasKey(
        "user:42:settings", "doesNotExist");
// Thông thường: false

Long deleted = hashOps.delete(
        "user:42:settings", "doesNotExist");
// Thông thường: 0
~~~

Đây là các kết quả bình thường từ Redis cho trường hợp **không có field**; không nên tự động xem là lỗi kết nối.

Ngược lại, khi key đã tồn tại nhưng thuộc **kiểu Redis khác**, ví dụ String thay vì Hash, Redis có thể trả lỗi `WRONGTYPE`:

~~~bash
SET user:42:settings unexpected-string
HGET user:42:settings theme
~~~

Lệnh HGET thứ hai bị lỗi vì tên key hiện trỏ tới String. Điều này nhấn mạnh cần **quy ước tên key và kiểu dữ liệu ổn định** trong suốt vòng đời ứng dụng.

### 10.1. Xóa field nhiều lần có an toàn không?

Nếu yêu cầu là “đảm bảo field đã biến mất”, việc gọi `delete(...)` lặp lại là một kiểu thao tác idempotent:

~~~java
hashOps.delete("user:42:settings", "deprecatedField");
hashOps.delete("user:42:settings", "deprecatedField");
~~~

Lần đầu có thể trả 1, lần sau trả 0. Trạng thái cuối cùng giống nhau: field không tồn tại. Dĩ nhiên, trong hệ thống có cập nhật đồng thời, một client khác vẫn có thể ghi lại field giữa hoặc sau hai lần xóa. Redis không tự ngăn điều đó.

## 11. HashOperations.putIfAbsent(): chỉ tạo field khi chưa có

`put(...)` ghi đè field đã tồn tại. Khi nghiệp vụ muốn **chỉ gán một giá trị mặc định ở lần đầu**, Spring Data Redis cung cấp `putIfAbsent(...)` tương ứng ý tưởng `HSETNX`:

~~~java
Boolean created = hashOps.putIfAbsent(
        "user:42:settings",
        "language",
        "vi");
~~~

Kết quả thông thường:

- `true`: field chưa tồn tại, Redis đã thêm giá trị.
- `false`: field đã tồn tại, Redis giữ nguyên giá trị cũ.

Ví dụ:

~~~text
User đã có language = "en"

putIfAbsent(key, "language", "vi")
    -> không ghi đè; language vẫn là "en"

put(key, "language", "vi")
    -> cập nhật field thành "vi"
~~~

Một lệnh `HSETNX` xử lý việc “chỉ thêm nếu chưa có” **tại Redis Server trong một command atomic**. Cách làm sau đây không tương đương khi có nhiều client đồng thời:

~~~java
// Dễ race condition: client khác có thể ghi giữa hai lệnh.
if (!Boolean.TRUE.equals(hashOps.hasKey(key, "language"))) {
    hashOps.put(key, "language", "vi");
}
~~~

Khi muốn không ghi đè field có sẵn, **ưu tiên `putIfAbsent(...)`** thay vì tự ghép `hasKey → put`.

## 12. HashOperations.increment(): cập nhật trường số

Redis Hash thường lưu một vài bộ đếm trong cùng một aggregate:

~~~text
Key: metrics:product:SKU-A
Hash fields:
  views     -> "120"
  favorites -> "18"
~~~

Trong Spring Data Redis:

~~~java
Long totalViews = hashOps.increment(
        "metrics:product:SKU-A",
        "views",
        1L);
~~~

Lệnh Redis tương ứng là `HINCRBY`. Redis thực hiện phép tăng số nguyên tại server, giúp tránh lỗi lost update của mô hình tự `HGET`, cộng trong Java rồi `HSET`.

Ví dụ:

~~~java
String key = "metrics:product:SKU-A";

hashOps.put(key, "views", "120");

Long afterFirst = hashOps.increment(key, "views", 1L);
Long afterSecond = hashOps.increment(key, "views", 1L);

// afterFirst thường là 121, afterSecond là 122.
~~~

Với field chưa tồn tại, Redis xử lý giá trị ban đầu theo ngữ nghĩa của lệnh increment (thường coi là 0). Nếu field đang chứa một chuỗi không biểu diễn được thành số nguyên hợp lệ, lệnh có thể bị từ chối.

**Một lệnh HINCRBY là atomic**, nhưng nó không tự kiểm tra business invariant như “không được vượt hạn mức” hoặc “tồn kho không được âm”. Với điều kiện nhiều bước, dùng script hoặc giải pháp atomic phù hợp.

## 13. TTL là của Redis key, không mặc nhiên là của từng Hash field

Xét Hash cài đặt người dùng:

~~~text
Key: user:42:settings
  language -> vi
  theme    -> dark
  timezone -> Asia/Ho_Chi_Minh

TTL của key: 30 phút
~~~

Đặt TTL qua `StringRedisTemplate`:

~~~java
redis.expire(
        "user:42:settings",
        Duration.ofMinutes(30));
~~~

Tương ứng:

~~~text
EXPIRE user:42:settings 1800
~~~

Đây là TTL cho **toàn bộ Hash key**. Khi key hết hạn, tất cả field của nó không còn được đọc như dữ liệu tồn tại.

### 13.1. HSET có tự gia hạn TTL không?

Với Redis thông thường, `HSET` thêm/sửa một field trong key Hash đang tồn tại **không tự đặt lại thời gian hết hạn của key**:

~~~text
T0: HSET user:42:settings theme dark
T1: EXPIRE user:42:settings 600
T2: sau 300 giây, HSET user:42:settings theme light
T3: TTL còn khoảng 300 giây; không tự trở lại 600
~~~

Nếu muốn sliding expiration, ứng dụng phải chủ động đưa ra chính sách làm mới TTL. Ví dụ:

~~~java
String key = "user:42:settings";

hashOps.put(key, "theme", "light");
redis.expire(key, Duration.ofMinutes(30));
~~~

**Đây vẫn là hai Redis command riêng**, không tạo thành một thao tác atomic chỉ vì cùng nằm trong một method Java. Nếu TTL là một invariant bắt buộc trong trường hợp crash hoặc cập nhật cạnh tranh, cần một giải pháp atomic ở Redis Server.

### 13.2. Hash field có TTL riêng được không?

Các phiên bản Redis mới có tính năng liên quan đến **hash-field expiration**, nhưng khả năng sử dụng còn phụ thuộc **phiên bản Redis Server, driver và API Spring Data Redis**. Không nên giả định mọi môi trường đều hỗ trợ TTL độc lập cho từng field chỉ vì Redis Hash có nhiều field.

Khi thiết kế cần **mỗi item một TTL khác nhau** và môi trường không cung cấp API field-expiration tương thích, thường nên tách thành nhiều Redis key độc lập với thời hạn riêng. Còn khi tất cả field thuộc cùng một phiên/aggregate, TTL theo key Hash là mô hình tự nhiên.

## 14. Serialization: vì sao StringRedisTemplate dễ dùng để học Hash?

Redis lưu key, field và value theo biểu diễn bytes. `HashOperations` dùng serializer của RedisTemplate để chuyển qua lại với các kiểu Java.

Với `StringRedisTemplate`:

~~~java
HashOperations<String, String, String> hashOps =
        redis.opsForHash();

hashOps.put("profile:42", "name", "Lan");
~~~

Những giá trị trên thường có thể kiểm tra trực tiếp bằng redis-cli:

~~~bash
HGET profile:42 name
~~~

Kết quả:

~~~text
"Lan"
~~~

Với một `RedisTemplate<String, Object>` tùy biến hoặc dùng serializer khác, cả Redis key, hash field và hash value có thể được biểu diễn theo định dạng khác. Redis CLI có thể hiển thị dữ liệu nhị phân hoặc client khác không đọc được theo cách mong đợi.

### 14.1. Hash value kiểu đối tượng Java

Ví dụ ứng dụng muốn lưu một cấu trúc phức tạp:

~~~text
Key: order:42
Field: shippingAddress
Value: JSON {"city":"HCMC","postalCode":"700000"}
~~~

Có thể lựa chọn:

1. **StringRedisTemplate**, tự serialize nội dung field thành JSON String bằng Jackson và tự deserialize khi đọc.
2. **RedisTemplate** cấu hình hash value serializer phù hợp, ví dụ JSON serializer.
3. Tách đối tượng thành nhiều Hash field đơn giản nếu access pattern thiên về truy cập từng thuộc tính.

Lựa chọn phụ thuộc cách ứng dụng đọc/ghi dữ liệu và yêu cầu tương thích với các client khác. **Đổi serializer sau khi đã có dữ liệu cần kế hoạch migration**, vì các bytes cũ không tự biến đổi sang định dạng mới.

### 14.2. Không truyền null như một cách xóa field

Muốn xóa trường, sử dụng `delete(key, field)` với ngữ nghĩa `HDEL`. Đừng coi `put(key, field, null)` là một thao tác xóa hợp lệ; serializer hoặc implementation có thể từ chối null hoặc hành xử khác với mong đợi.

Nếu nghiệp vụ cần biểu diễn “giá trị chưa được đặt”, hãy thống nhất một quy tắc: field không tồn tại, hoặc sentinel value có ý nghĩa rõ ràng. Không nhập nhằng giữa null phía Java với xóa field trong Redis.

## 15. Cập nhật đồng thời: atomic từng lệnh không có nghĩa atomic cả chuỗi

Các Redis command riêng lẻ như `HSET`, `HDEL` và `HINCRBY` có ngữ nghĩa atomic tại Redis Server. Tuy nhiên, chuỗi lệnh của service có thể bị các request khác xen vào.

Ví dụ hai request cập nhật cùng field:

~~~text
T0: theme = dark

Request A: HSET user:42:settings theme light
Request B: HSET user:42:settings theme system

Kết quả cuối phụ thuộc thứ tự hai lệnh được Redis thực thi.
~~~

Một lệnh `HSET` không bị “ghi nửa field”, nhưng **không có quy tắc ưu tiên nghiệp vụ** giữa hai cập nhật trừ khi ứng dụng thiết kế một quy tắc.

### 15.1. Race condition của check-then-act

Ví dụ:

~~~java
if (!Boolean.TRUE.equals(hashOps.hasKey(key, "theme"))) {
    hashOps.put(key, "theme", "dark");
}
~~~

Hai client có thể đều đọc kết quả false trước khi một trong hai ghi, rồi cùng `put`. Nếu cần “chỉ ghi khi chưa có”, hãy dùng một lệnh `putIfAbsent`.

### 15.2. Race condition của read-modify-write

~~~java
String raw = hashOps.get(key, "views");
long next = Long.parseLong(raw) + 1;
hashOps.put(key, "views", Long.toString(next));
~~~

Hai request có thể đọc cùng `views = 100` rồi đều ghi `101`, làm mất một lượt tăng. Với counter số nguyên, dùng `hashOps.increment(key, "views", 1L)` để Redis tăng atomic.

### 15.3. Khi phải sửa nhiều field có ràng buộc chung

Ví dụ cập nhật `status = PAID` và `paidAt = timestamp`. Nếu cả hai field phải thay đổi trong cùng một đơn vị logic, có thể dùng `putAll` để ghi nhiều field trong cùng một thao tác Hash phù hợp; với điều kiện kiểm tra phức tạp hoặc phối hợp nhiều key, cần xem xét Lua script hoặc transaction theo ngữ nghĩa Redis.

**Spring Data Redis không tự cung cấp transaction phân tán với database quan hệ** chỉ vì nhiều lệnh được gọi trong một phương thức `@Transactional`.

## 16. BoundHashOperations: làm việc nhiều lần với một key

Khi code gọi nhiều thao tác trên **cùng một Redis Hash key**, Spring Data Redis cung cấp `BoundHashOperations`:

~~~java
import org.springframework.data.redis.core.BoundHashOperations;

BoundHashOperations<String, String, String> settings =
        redis.boundHashOps("user:42:settings");

settings.put("language", "vi");
settings.put("theme", "dark");

String theme = settings.get("theme");
Long removed = settings.delete("language");
~~~

So sánh:

~~~java
// HashOperations: truyền Redis key vào mỗi lần gọi.
hashOps.put("user:42:settings", "theme", "dark");
hashOps.get("user:42:settings", "theme");
hashOps.delete("user:42:settings", "theme");

// BoundHashOperations: key được gắn một lần.
var bound = redis.boundHashOps("user:42:settings");
bound.put("theme", "dark");
bound.get("theme");
bound.delete("theme");
~~~

Hai cách vẫn gửi các lệnh Redis tương đương. `BoundHashOperations` giúp giảm lặp lại tên key và làm code rõ hơn khi xử lý một aggregate, **không tự tạo transaction, lock hoặc cache dữ liệu**.

Nếu service xử lý nhiều user, đừng tạo một bound object gắn với `user:42:settings` làm field singleton dùng cho tất cả user. Hãy tạo đối tượng bound theo đúng key của request/aggregate hiện tại.

## 17. Thực hành đối chiếu bằng redis-cli

Sau khi đã có Redis Server và redis-cli, có thể thực hành thủ công:

### Bước 1: Xóa dữ liệu demo cũ nếu có

~~~bash
DEL demo:hash:118
~~~

### Bước 2: Thêm ba field

~~~bash
HSET demo:hash:118 name Lan language vi theme dark
~~~

Quan sát:

~~~bash
TYPE demo:hash:118
HLEN demo:hash:118
HGETALL demo:hash:118
~~~

Kết quả `TYPE` là `hash`, `HLEN` là 3, còn `HGETALL` trả về ba cặp field/value. Thứ tự hiển thị của kết quả toàn Hash không nên được dùng làm một contract thứ tự nghiệp vụ.

### Bước 3: Đọc một field và kiểm tra field tồn tại

~~~bash
HGET demo:hash:118 theme
HEXISTS demo:hash:118 theme
HEXISTS demo:hash:118 timezone
~~~

Kết quả `HGET theme` là `dark`, `HEXISTS theme` là 1 và `HEXISTS timezone` là 0.

### Bước 4: Cập nhật field

~~~bash
HSET demo:hash:118 theme light
HGET demo:hash:118 theme
~~~

Giá trị `theme` giờ là `light`, trong khi `name` và `language` không đổi.

### Bước 5: Xóa field

~~~bash
HDEL demo:hash:118 language
HGET demo:hash:118 language
HGETALL demo:hash:118
~~~

`HGET` đối với field đã xóa trả nil; Hash vẫn còn các field khác.

### Bước 6: Xóa cả Hash

~~~bash
DEL demo:hash:118
EXISTS demo:hash:118
~~~

`EXISTS` trả 0 nếu key đã được xóa và không có client khác tạo lại trong lúc kiểm tra.

Những lệnh trên sử dụng **cùng loại Redis commands** mà Spring Data Redis gửi khi gọi HashOperations. Nếu ứng dụng kết nối Redis instance khác hoặc serializer khác, bạn sẽ không thấy đúng key/value đó khi thử CLI.

## 18. Bài thực hành Java: ghi–đọc–xóa một field có key riêng

Ví dụ dưới đây tạo một key thử nghiệm bằng UUID, tránh ghi đè dữ liệu nghiệp vụ và đặt TTL dự phòng:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisHashExercise {

    private final StringRedisTemplate redis;
    private final HashOperations<String, String, String> hashOps;

    public RedisHashExercise(StringRedisTemplate redis) {
        this.redis = redis;
        this.hashOps = redis.opsForHash();
    }

    public void runOnce() {
        String key = "demo:hash:" + UUID.randomUUID();

        try {
            hashOps.put(key, "theme", "dark");
            redis.expire(key, Duration.ofMinutes(2));

            String readBack = hashOps.get(key, "theme");
            System.out.println("Read theme: " + readBack);

            hashOps.put(key, "theme", "light");
            System.out.println(
                    "Updated theme: " + hashOps.get(key, "theme"));

            Long removed = hashOps.delete(key, "theme");
            System.out.println("Deleted field count: " + removed);

            String afterDelete = hashOps.get(key, "theme");
            System.out.println("After delete: " + afterDelete);
        } finally {
            redis.delete(key);
        }
    }
}
~~~

Đây là class có phương thức `runOnce()` để **người học gọi chủ động**, không tự chạy chỉ vì có `@Component`. Có thể gọi từ một runner dành riêng cho môi trường thử nghiệm hoặc bài test tích hợp kết nối Redis. Không nên đặt thao tác ghi thử nghiệm này trên endpoint công khai không kiểm soát.

Kết quả minh họa khi không có thao tác cạnh tranh:

~~~text
Read theme: dark
Updated theme: light
Deleted field count: 1
After delete: null
~~~

TTL hai phút giúp key tự hết hạn nếu quá trình dừng trước phần cleanup. Trong ví dụ, xóa field cuối có thể đã làm Hash key biến mất, nên `redis.delete(key)` ở `finally` có thể không cần xóa thêm gì; điều đó vẫn bình thường.

Chú ý `hashOps.put(...)` và `redis.expire(...)` là **hai command** nên không đảm bảo atomic nếu việc đặt TTL là ràng buộc bắt buộc của nghiệp vụ. Bài thực hành chỉ nhằm quan sát các thao tác Hash cơ bản.

## 19. Lỗi thường gặp khi dùng HashOperations

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `get(key, field)` trả `null` | Redis key hoặc field chưa tồn tại, đã bị xóa/hết hạn | Kiểm tra `hasKey` ở cấp field, `redis.hasKey` ở cấp key, TTL |
| `delete(key, field)` trả 0 | Field không tồn tại | Xác nhận tên field, key và luồng ghi trước đó |
| `WRONGTYPE` khi `HGET/HSET` | Cùng tên Redis key được lưu dưới kiểu String/List/... | Kiểm tra `TYPE key`, quy ước key và migration |
| `HGETALL` chậm hoặc tạo Map lớn | Hash có quá nhiều field | Đọc chọn lọc bằng `get`/`multiGet`, xem thiết kế aggregate |
| Field cập nhật bị mất | Nhiều client cùng cập nhật, dùng read-modify-write | Dùng atomic command hoặc cơ chế concurrency phù hợp |
| Thêm field xong key biến mất | TTL key đã hết hoặc có client khác xóa | Kiểm tra `TTL`, chính sách expiration/invalidation |
| `hasKey` trả false nhưng ngay sau đó `get` có giá trị | Có luồng khác vừa tạo field | Đừng giả định nhiều lệnh độc lập là snapshot/transaction |
| Đọc ra bytes khó hiểu ở redis-cli | Serializer không phải chuỗi | Kiểm tra hash key/value serializer |
| Lỗi `RedisConnectionFailureException` | Redis Server/network/auth/config không kết nối được | Kiểm tra host, port, TLS, ACL, driver |
| Ghi qua Java nhưng CLI không thấy dữ liệu | Khác Redis endpoint/database, key serializer hoặc key đã hết TTL | Đối chiếu cấu hình và bytes key |
| Xóa một field làm mất cả Hash | Field đó là field cuối cùng | Hiểu ngữ nghĩa HDEL với Hash rỗng |
| `putAll` không xóa field cũ | putAll chỉ ghi/ghi đè các field truyền vào | Dùng HDEL riêng cho field cần xóa |

### 19.1. Redis Hash là một key chung cho các field

Một Hash có hàng triệu field vẫn là **một Redis key**. Trong Redis Cluster, nó thuộc một hash slot. Khi mọi request tập trung vào một key lớn hoặc key rất nóng, các thao tác của cùng Hash có thể gây áp lực lên một node/slot; không phải vì API HashOperations sai.

Nếu mỗi user có một Hash riêng như `user:42:settings`, `user:57:settings`, tải có thể phân tán theo nhiều key tốt hơn. Tránh gom toàn bộ user vào một Hash toàn cục chỉ để giảm số lượng key.

### 19.2. HGETALL không phải cách phân trang

`hashOps.entries(key)` tải toàn bộ Hash. Redis cung cấp `HSCAN` để duyệt theo cursor khi cần kiểm tra/duyệt Hash lớn, nhưng scan không có semantics snapshot bất biến khi dữ liệu thay đổi đồng thời. Nếu API nghiệp vụ thường cần phân trang chính xác hoặc truy vấn phức tạp, phải thiết kế dữ liệu và index cho yêu cầu đó; không nên coi HSCAN thay thế hoàn toàn database query.

### 19.3. Tránh log dữ liệu nhạy cảm

Hash field/value có thể chứa cấu hình nội bộ, token hoặc thông tin người dùng. Không nên log toàn bộ `entries()` trên production chỉ để debug, và không dùng `HGETALL` tùy tiện với key có dữ liệu bí mật. Quy định cụ thể về audit/ACL phải phù hợp môi trường vận hành.

## 20. Khi nào chọn HashOperations thay vì String JSON hoặc nhiều key?

| Access pattern | Cách lưu thường hợp lý | Lý do |
|---|---|---|
| Mỗi user có vài thuộc tính, thường sửa một field | Một Redis Hash/user + `HashOperations` | HGET/HSET/HDEL theo field |
| Luôn đọc/ghi nguyên snapshot JSON nhỏ | Một String JSON/user | GET/SET trọn payload đơn giản |
| Mỗi thuộc tính có TTL khác nhau | Nhiều Redis key riêng hoặc cơ chế field TTL được hỗ trợ phù hợp | TTL độc lập, dễ quản lý |
| Cần đếm số liệu của một entity theo từng counter | Redis Hash + `increment` | HINCRBY atomic theo field |
| Một bảng xếp hạng theo score | Sorted Set + `ZSetOperations` | Truy vấn theo score/rank |
| Danh sách có thứ tự | List + `ListOperations` | LPUSH/RPUSH/LRANGE |
| Số lượng field quá lớn và phát triển không giới hạn | Xem lại aggregate/chia partition/retention | Giảm big key và chi phí đọc/xóa |

Redis Hash phù hợp với **một aggregate có nhiều trường liên quan và vòng đời tương đồng**. Nếu từng field có TTL độc lập hoặc yêu cầu phân mảnh theo nhiều key, nên cân nhắc ranh giới lưu trữ khác.

## 21. Câu hỏi củng cố

**1. `HashOperations.put(key, field, value)` thêm field mới hay cập nhật field cũ?**

Cả hai. Redis HSET tạo field nếu chưa có, hoặc ghi đè value nếu đã có. Các field khác không bị ghi đè.

**2. `HashOperations.get(key, field)` trả gì khi field không tồn tại?**

Thông thường trả `null`. Kết quả đó cũng có thể xảy ra khi toàn bộ Hash key không tồn tại.

**3. Xóa field và xóa Redis key khác nhau thế nào?**

`hashOps.delete(key, field)` gửi HDEL để xóa field; `redis.delete(key)` gửi DEL để xóa toàn bộ Redis key và mọi field.

**4. `delete(key, "theme")` trả 0 có nghĩa Redis lỗi không?**

Không. Nó thường chỉ có nghĩa field `theme` không tồn tại tại thời điểm xóa.

**5. `hashOps.putAll(key, map)` có xóa những field không nằm trong map không?**

Không. Nó ghi hoặc ghi đè các field được cung cấp, còn các field không được đề cập vẫn tồn tại.

**6. Muốn chỉ tạo field nếu chưa có, dùng gì?**

`putIfAbsent(key, field, value)`, tương ứng HSETNX. Nó xử lý điều kiện ở Redis Server trong một command.

**7. Muốn tăng counter thuộc một Hash mà tránh lost update thì làm sao?**

Dùng `hashOps.increment(key, field, delta)` tương ứng HINCRBY, thay vì đọc rồi cộng trong Java rồi ghi lại.

**8. `HSET` có tự gia hạn TTL của Hash key không?**

Thông thường không. TTL của key vẫn tiếp tục trôi; cần đặt chính sách làm mới TTL rõ ràng nếu nghiệp vụ yêu cầu.

**9. Khi xóa field cuối cùng, Hash key còn tồn tại không?**

Không theo ngữ nghĩa Redis Hash thông thường: xóa field cuối làm key biến mất.

**10. Khi nào không nên dùng `hashOps.entries(key)` trong request?**

Khi Hash có thể chứa số field rất lớn hoặc payload lớn. Nên đọc các field cần thiết, giới hạn aggregate hoặc thiết kế cách duyệt phù hợp.

**11. Khác biệt giữa `redis.hasKey(key)` và `hashOps.hasKey(key, field)`?**

Lệnh thứ nhất kiểm tra **toàn Redis key**; lệnh thứ hai kiểm tra **một field bên trong Hash**.

**12. Vì sao `StringRedisTemplate` thường dễ dùng cho ví dụ Hash cơ bản?**

Vì key, field và value là chuỗi, có serializer nhất quán, dễ quan sát dữ liệu qua redis-cli và không cần cấu hình serialization object phức tạp.

## Ghi nhớ

~~~text
Redis Hash key: user:42:settings
    |
    +-- Field: theme     -> "dark"
    +-- Field: language  -> "vi"
    +-- Field: timezone  -> "Asia/Ho_Chi_Minh"

HashOperations<String, String, String> hashOps
    |
    +-- put(key, field, value)     -> HSET  (ghi / cập nhật)
    +-- get(key, field)            -> HGET  (đọc một field)
    +-- delete(key, fields...)     -> HDEL  (xóa field)
    +-- hasKey(key, field)         -> HEXISTS
    +-- putIfAbsent(key, field, v) -> HSETNX
    +-- putAll(key, map)           -> ghi nhiều field
    +-- multiGet(key, fields)      -> HMGET
    +-- entries(key)               -> HGETALL
    +-- increment(key, field, n)   -> HINCRBY

redis.delete(key)                  -> DEL toàn bộ Hash
redis.expire(key, duration)        -> TTL toàn bộ Hash key
~~~

**Nắm chắc `put()`, `get()` và `delete()` là nền tảng sử dụng HashOperations.** Mỗi thao tác chọn một Redis Hash bằng **key** và chọn trường bên trong bằng **field**. Khi mở rộng sang `putAll`, `multiGet`, `hasKey` và `increment`, hãy giữ đúng ngữ nghĩa Redis: TTL thuộc key, từng command độc lập, cấu trúc dữ liệu phải thống nhất và tính atomic của một lệnh không tự biến nhiều lời gọi Java thành một transaction.
