# Chọn Hash phẳng, JSON hay nhiều khóa riêng

Trong Spring Data Redis, một đối tượng Java có thể được lưu dưới **một Redis Hash**, **một Redis String chứa JSON**, hoặc **nhiều Redis key độc lập**. Ba phương án có thể biểu diễn cùng một thực thể nghiệp vụ nhưng tạo ra các đặc tính khác nhau về truy vấn, cập nhật, TTL, bộ nhớ, serialization và xử lý đồng thời.

Quy tắc lựa chọn quan trọng nhất là: **mô hình Redis phải phản ánh những thao tác mà ứng dụng thực hiện thường xuyên**. Một DTO có nhiều field không mặc nhiên phải là Redis Hash; một tài liệu JSON có cấu trúc đẹp không mặc nhiên là cách tối ưu nếu ứng dụng chỉ cập nhật một bộ đếm.

## 1. Ba cách biểu diễn cùng một dữ liệu

Giả sử ứng dụng có một hồ sơ người dùng:

~~~java
public record UserProfile(
        String userId,
        String displayName,
        String city,
        long loginCount,
        boolean verified
) {}
~~~

Giá trị mẫu:

~~~text
userId      = 42
displayName = Linh
city        = Ha Noi
loginCount  = 7
verified    = true
~~~

### 1.1. Hash phẳng: một key chứa nhiều field

~~~text
Redis key: user:42:profile
Redis TYPE: hash

displayName  -> Linh
city         -> Ha Noi
loginCount   -> 7
verified     -> true
~~~

~~~redis
HSET user:42:profile displayName "Linh" city "Ha Noi" loginCount 7 verified true
HGET user:42:profile city
HINCRBY user:42:profile loginCount 1
HGETALL user:42:profile
~~~

Đây là một Redis Hash. `city` là **field bên trong key**, không phải key riêng trong keyspace.

### 1.2. JSON: một key chứa toàn bộ tài liệu

~~~text
Redis key: user:42:profile
Redis TYPE: string
~~~

~~~json
{
  "userId": "42",
  "displayName": "Linh",
  "city": "Ha Noi",
  "loginCount": 7,
  "verified": true
}
~~~

~~~redis
SET user:42:profile '{"userId":"42","displayName":"Linh","city":"Ha Noi","loginCount":7,"verified":true}'
GET user:42:profile
~~~

Redis nhìn thấy một **String chứa byte của JSON**. Trong cách lưu này, Redis không tự hiểu các property `city` hoặc `loginCount` như field của Hash.

### 1.3. Nhiều key: mỗi thuộc tính hoặc nhóm thuộc tính một key

~~~text
user:42:displayName -> Linh
user:42:city        -> Ha Noi
user:42:loginCount  -> 7
user:42:verified    -> true
~~~

~~~redis
SET user:42:displayName "Linh"
SET user:42:city "Ha Noi"
SET user:42:loginCount 7
SET user:42:verified true

INCR user:42:loginCount
GET user:42:city
~~~

Dấu hai chấm chỉ là quy ước đặt tên. Redis không tạo thư mục hoặc quan hệ cha–con giữa các key có cùng prefix.

## 2. Bảng so sánh để lựa chọn

| Câu hỏi | Hash phẳng | JSON trong String | Nhiều key riêng |
|---|---|---|---|
| Đọc một thuộc tính? | `HGET` trực tiếp | Thường `GET` cả document rồi parse | `GET` key tương ứng |
| Đọc một số field? | `HMGET` | Thường lấy cả document | Nhiều `GET` hoặc `MGET` |
| Đọc toàn bộ đối tượng? | `HGETALL` và ghép field | `GET` + deserialize | Ghép từ nhiều key |
| Sửa một thuộc tính? | `HSET` | Thường serialize lại cả object | `SET` key riêng |
| Tăng bộ đếm? | `HINCRBY` | Đọc–sửa–ghi nếu không có cơ chế khác | `INCR`/`INCRBY` |
| Đối tượng lồng nhau phức tạp? | Phải flatten hoặc serialize field | Rất tự nhiên | Có thể chia nhóm thành các key |
| TTL thông thường? | TTL toàn key Hash | TTL toàn key String | TTL độc lập mỗi key |
| Xóa toàn bộ đối tượng? | Một `DEL` | Một `DEL` | Xóa các key thành phần |
| Dung lượng? | Hash nhỏ có thể tiết kiệm bộ nhớ | Có tên property trong JSON | Overhead cho từng key |
| Cần schema Java rõ? | Mapping từng field | JSON serializer/DTO | Quy ước từng key |
| Redis Cluster? | Một key thuộc một hash slot | Một key thuộc một hash slot | Các key có thể khác slot |

Đừng coi bảng này là kết quả benchmark. Hiệu năng thật sự phụ thuộc số field, kích thước payload, tốc độ cập nhật, encoding nội bộ của Redis, số lượng key và số lượt trao đổi mạng.

## 3. Hash phẳng: lựa chọn cho những field độc lập

Hash phù hợp với một nhóm thuộc tính tương đối phẳng và thường được sửa hoặc đọc riêng lẻ:

~~~text
user:42:profile [Hash]
  displayName   "Linh"
  city          "Ha Noi"
  locale        "vi"
  verified      "true"
  loginCount    "7"
~~~

Những lệnh quan trọng:

~~~redis
HSET user:42:profile displayName "Linh" city "Ha Noi"
HGET user:42:profile displayName
HMGET user:42:profile displayName city
HEXISTS user:42:profile verified
HINCRBY user:42:profile loginCount 1
HDEL user:42:profile locale
HLEN user:42:profile
~~~

**Ưu điểm chính:** khi chỉ thay đổi một field, `HSET` không phải đọc và ghi lại tất cả các field còn lại. `HINCRBY` có thể tăng một field số nguyên bằng một lệnh Redis nguyên tử.

Một lệnh `HSET` có nhiều cặp field/value cập nhật các field đó trong cùng một thao tác lệnh. Nếu phải thực thi nhiều lệnh độc lập và muốn chúng có cùng một thời điểm commit nghiệp vụ, vẫn cần cơ chế transaction/script phù hợp.

### 3.1. Field và value không có kiểu Java tự động

Redis Hash lưu field/value dưới dạng dữ liệu byte; ứng dụng quyết định serializer:

~~~text
field           giá trị lưu     kiểu mong muốn ở Java
displayName     "Linh"          String
loginCount      "8"             long
verified        "true"          boolean
updatedAt       "1790000000"    epoch seconds
~~~

Một service khác hoàn toàn có thể ghi `loginCount="eight"` bằng `HSET`. Redis không coi đó là vi phạm schema Hash; chỉ khi code thực hiện `HINCRBY` hoặc parse số thì lỗi mới bộc lộ. Vì vậy, hợp đồng tên field và định dạng dữ liệu vẫn phải được ứng dụng quản lý.

Nếu muốn dùng thao tác số nguyên `HINCRBY`, field phải chứa biểu diễn số nguyên hợp lệ. Với số tiền, thường nên có quy ước đơn vị nguyên nhỏ nhất; cần tránh trộn giá trị `100.50` với những lệnh chỉ dành cho số nguyên.

### 3.2. Đối tượng nested làm Hash khó đọc hơn

Giả sử người dùng có:

~~~json
{
  "displayName": "Linh",
  "address": {
    "city": "Ha Noi",
    "district": "Ba Dinh"
  },
  "tags": ["premium", "beta"]
}
~~~

Có thể tự đặt tên field phẳng:

~~~text
displayName       -> Linh
address.city      -> Ha Noi
address.district  -> Ba Dinh
tags              -> ["premium","beta"]
~~~

Nhưng `address.city` chỉ là **một tên field**, Redis không hiểu dấu chấm như JSON path. Nếu tên field được sinh từ dữ liệu bên ngoài, phải có quy tắc escape tránh xung đột. `tags` lúc này là một chuỗi JSON, không phải Set có thể dùng `SADD`/`SISMEMBER`.

Khi schema lồng sâu, array phức tạp hoặc có nhiều subtype, JSON có thể rõ ràng hơn. Nếu `tags` cần phép tập hợp, tách thành một Redis Set riêng thường đúng bài toán hơn.

### 3.3. Tránh HGETALL cho Hash khổng lồ

~~~redis
HGETALL user:42:profile
HSCAN user:42:profile 0 COUNT 100
~~~

Với Hash nhỏ, `HGETALL` thuận tiện vì lấy hết field và value. Với Hash rất lớn, đọc toàn bộ có thể tiêu tốn băng thông, bộ nhớ và thời gian chuyển đổi dữ liệu phía Java.

Nếu chỉ cần vài field, dùng `HMGET`; nếu cần duyệt Hash lớn, cân nhắc `HSCAN` với cursor. `COUNT` trong SCAN là gợi ý, không bảo đảm số kết quả cố định mỗi lượt.

### 3.4. TTL của Hash

~~~redis
HSET user:42:profile displayName "Linh"
EXPIRE user:42:profile 900
TTL user:42:profile
~~~

TTL này gắn với **toàn bộ key Hash**, không tự gắn riêng với `displayName` hay `city`. Nếu key hết hạn, tất cả field biến mất.

Một `HSET` cập nhật field trên key Hash hiện có thường không tự reset TTL. Nếu muốn sliding expiration, ứng dụng cần chủ động gọi `EXPIRE` theo chính sách.

Một số phiên bản Redis mới có hỗ trợ hết hạn theo field Hash. Khả năng dùng thực tế phụ thuộc bản Redis và API driver/Spring Data Redis nên không nên mặc định sẵn có trong mọi hệ thống. Với yêu cầu TTL riêng và cần tính di động giữa các bản triển khai, tách key vẫn là mô hình dễ hiểu.

## 4. HashOperations trong Spring Data Redis

Với dữ liệu field dạng chuỗi, `StringRedisTemplate` giúp dễ quan sát bằng Redis CLI:

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserProfileHashRepository {

    private final StringRedisTemplate redis;
    private final HashOperations<String, Object, Object> hashes;

    public UserProfileHashRepository(StringRedisTemplate redis) {
        this.redis = redis;
        this.hashes = redis.opsForHash();
    }

    private String key(String userId) {
        return "user:" + userId + ":profile";
    }

    public void saveBasicProfile(String userId, String name, String city) {
        String key = key(userId);

        hashes.putAll(key, Map.of(
                "displayName", name,
                "city", city,
                "verified", "false"));

        redis.expire(key, Duration.ofMinutes(30));
    }

    public String findCity(String userId) {
        Object value = hashes.get(key(userId), "city");
        return value == null ? null : value.toString();
    }

    public long recordLogin(String userId) {
        return hashes.increment(key(userId), "loginCount", 1L);
    }
}
~~~

Ở đây `StringRedisTemplate` dùng serializer chuỗi cho key, hash key và hash value. Field `loginCount` được Redis xử lý bằng phép tăng nguyên tử, nhưng nếu một client khác đã lưu nội dung không phải số nguyên thì thao tác sẽ thất bại.

Đừng nhầm:

~~~java
hashes.put("user:42:profile", "address", someJavaObject);
~~~

với việc tự động tách `someJavaObject` ra thành nhiều field. `put` chỉ ghi **một field**, và đối tượng ở value sẽ được xử lý bằng **hash value serializer** đã cấu hình.

Nếu cần chuyển POJO thành map field/value, Spring Data Redis có các cơ chế mapping Hash phù hợp, hoặc có thể tự định nghĩa mapper. Khi làm vậy phải quyết định rõ tên field, kiểu dữ liệu, cách flatten, xử lý null và tương thích schema.

## 5. JSON trong String: lựa chọn cho snapshot có cấu trúc

JSON phù hợp khi ứng dụng thường đọc **cả tài liệu** và DTO có cấu trúc lồng nhau.

Ví dụ snapshot một đơn hàng:

~~~json
{
  "orderId": "O-1001",
  "status": "PAID",
  "customer": {
    "userId": "42",
    "name": "Linh"
  },
  "items": [
    {"sku": "SKU-A", "quantity": 2, "price": 120000},
    {"sku": "SKU-B", "quantity": 1, "price": 80000}
  ],
  "totalAmount": 320000
}
~~~

Một lệnh `GET order:O-1001:snapshot` lấy toàn bộ tài liệu về, rồi Jackson có thể ánh xạ sang DTO. Mô hình này tự nhiên hơn so với việc đặt `items.0.sku`, `items.0.quantity`, `items.1.sku`, ... thành nhiều Hash field.

### 5.1. Lưu JSON bằng Spring Data Redis

DTO minh họa:

~~~java
import java.util.List;

public record OrderLine(String sku, int quantity, long price) {}

public record OrderSnapshot(
        String orderId,
        String status,
        String customerId,
        List<OrderLine> items,
        long totalAmount) {}
~~~

Cấu hình một template có kiểu đích cụ thể (ví dụ Spring Data Redis 3.x, Jackson 2):

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class OrderCacheRedisConfiguration {

    @Bean("orderSnapshotTemplate")
    RedisTemplate<String, OrderSnapshot> orderSnapshotTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper) {

        RedisTemplate<String, OrderSnapshot> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        objectMapper, OrderSnapshot.class));

        return template;
    }
}
~~~

Service dùng template:

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderSnapshotCache {

    private final RedisTemplate<String, OrderSnapshot> redis;

    public OrderSnapshotCache(
            @Qualifier("orderSnapshotTemplate")
            RedisTemplate<String, OrderSnapshot> redis) {
        this.redis = redis;
    }

    public void save(OrderSnapshot snapshot) {
        redis.opsForValue().set(
                "order:" + snapshot.orderId() + ":snapshot",
                snapshot,
                Duration.ofMinutes(10));
    }

    public OrderSnapshot find(String orderId) {
        return redis.opsForValue().get(
                "order:" + orderId + ":snapshot");
    }
}
~~~

Vì `OrderSnapshot` là kiểu đích cụ thể, serializer có thể khôi phục DTO mà không cần phải lưu tên class Java ở root payload. Nếu DTO có các trường đa hình như interface/abstract class, phải cấu hình việc lựa chọn subtype riêng.

**Một Redis String chứa JSON vẫn là String.** Không thể gọi `opsForHash().get(key, "status")` trên chính key đó: Redis sẽ trả lỗi `WRONGTYPE`.

### 5.2. Điểm yếu của JSON: cập nhật một field

Giả sử muốn tăng `loginCount` đang nằm trong JSON String:

~~~text
GET <key>
   |
   v
Deserialize JSON -> Java object
   |
   v
Tăng loginCount trong Java
   |
   v
Serialize object -> JSON mới
   |
   v
SET <key> <new JSON>
~~~

Đây là một **chuỗi nhiều lệnh**, không có tính nguyên tử toàn chuỗi.

Ví dụ hai request chạy đồng thời:

~~~text
Giá trị đầu: {"city":"Ha Noi","loginCount":7}

Thread A đọc bản cũ.
Thread B đọc bản cũ.

A đổi city thành "Da Nang", SET toàn bộ JSON.
B tăng loginCount thành 8, SET toàn bộ JSON.

Kết quả có thể là:
{"city":"Ha Noi","loginCount":8}

Cập nhật của A bị ghi đè.
~~~

Dù mỗi lệnh `SET` là nguyên tử, chuỗi read–modify–write có thể gây **lost update**. Có thể dùng optimistic locking (`WATCH`/`MULTI`/`EXEC`) hoặc script khi cần, nhưng nếu field thường xuyên tăng thì một Hash field hoặc key String counter có thể đơn giản hơn nhiều.

### 5.3. SET ảnh hưởng đến TTL

~~~redis
SET order:O-1001:snapshot '{"status":"PAID"}' EX 600
TTL order:O-1001:snapshot

SET order:O-1001:snapshot '{"status":"SHIPPED"}'
TTL order:O-1001:snapshot
~~~

Lệnh `SET` thứ hai không yêu cầu giữ TTL hoặc đặt TTL mới nên theo mặc định làm mất expiration cũ. Cache có thể tồn tại lâu hơn dự kiến.

Vì vậy, khi cập nhật JSON cache cần thống nhất chính sách: đặt lại TTL, giữ TTL thông qua cơ chế tương ứng, hoặc invalidation rồi cho service nạp snapshot mới.

### 5.4. Phân biệt JSON String với RedisJSON

Một hệ Redis có thể cung cấp các lệnh như `JSON.GET`/`JSON.SET` qua tính năng RedisJSON của bản triển khai tương ứng. Nhưng đó là khả năng **khác** với lưu JSON bytes vào String bằng `SET`.

Không suy rằng:

~~~java
redis.opsForValue().get("order:O-1001:snapshot");
~~~

tự hỗ trợ `$.customer.name` hoặc JSON path. Với JSON String thông thường, cần đọc nguyên value. Nếu hệ thống định sử dụng RedisJSON, hãy kiểm tra phiên bản Redis, cấu hình server, hỗ trợ của client và yêu cầu triển khai.

## 6. Nhiều key riêng: khi cần vòng đời độc lập

Ví dụ người dùng có các nhóm dữ liệu:

~~~text
user:42:profile      [Hash]   name, city, verified
user:42:session      [String] token, TTL 30 phút
user:42:loginCount   [String] bộ đếm
user:42:tags         [Set]    premium, beta
user:42:preferences  [String] JSON, TTL 1 ngày
~~~

Không nhất thiết phải lưu mỗi thuộc tính thành một key String. **“Nhiều key riêng” cho phép mỗi key dùng đúng cấu trúc dữ liệu Redis**.

~~~redis
SET user:42:session "session-abc" EX 1800
INCR user:42:loginCount
SADD user:42:tags "premium" "beta"
SET user:42:preferences '{"theme":"dark"}' EX 86400
~~~

Lợi ích:

- Session có TTL ngắn trong khi bộ đếm tồn tại theo kỳ riêng.
- Tăng bộ đếm bằng `INCR` không ảnh hưởng hồ sơ.
- Tập tag dùng `SADD` và `SISMEMBER`, không cần parse array JSON.
- Mỗi nhóm có thể được xóa/làm mới độc lập.

Đổi lại:

- Có thêm metadata cho mỗi key; nếu mỗi user có hàng chục key cực nhỏ, tổng overhead có thể lớn.
- Xóa một user cần biết các key thành phần.
- Ghép nhiều key không tự đảm bảo một snapshot ở cùng thời điểm.
- Multi-key trong Redis Cluster phải tuân thủ quy tắc hash slot.

### 6.1. Spring Data Redis với key riêng

~~~java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserKeysRepository {

    private final StringRedisTemplate redis;

    public UserKeysRepository(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private String prefix(String userId) {
        return "user:" + userId + ":";
    }

    public void updateCity(String userId, String city) {
        redis.opsForValue().set(prefix(userId) + "city", city);
    }

    public long incrementLoginCount(String userId) {
        Long value = redis.opsForValue()
                .increment(prefix(userId) + "loginCount");

        if (value == null) {
            throw new IllegalStateException("No Redis result");
        }
        return value;
    }

    public void saveSession(String userId, String session) {
        redis.opsForValue().set(
                prefix(userId) + "session",
                session,
                Duration.ofMinutes(30));
    }
}
~~~

Với một tập tag:

~~~java
redis.opsForSet().add("user:42:tags", "premium", "beta");

Boolean isPremium = redis.opsForSet()
        .isMember("user:42:tags", "premium");
~~~

Một key `user:42:tags` sử dụng Redis Set hiệu quả hơn chuỗi JSON nếu chức năng chính là kiểm tra thành viên, loại trùng và phép tập hợp.

### 6.2. Đọc toàn bộ đối tượng khi có nhiều key

Nếu tất cả thuộc tính là String:

~~~java
String name = redis.opsForValue().get("user:42:name");
String city = redis.opsForValue().get("user:42:city");
String verified = redis.opsForValue().get("user:42:verified");
~~~

Có thể dùng `multiGet` cho những key phù hợp:

~~~java
import java.util.List;

List<String> values = redis.opsForValue().multiGet(List.of(
        "user:42:name",
        "user:42:city",
        "user:42:verified"));
~~~

Điều này giảm round-trip trong tình huống có thể thực thi một lệnh multi-key phù hợp. Cần xử lý key vắng mặt, thứ tự kết quả và các giới hạn Redis Cluster. Nếu mỗi key được cập nhật ở những thời điểm khác nhau, ghép chúng thành DTO vẫn có thể thu được các giá trị thuộc các phiên bản khác nhau.

Nếu ứng dụng thường xuyên cần một **snapshot đồng nhất**, một key Hash/JSON có thể dễ quản lý hơn.

### 6.3. Xóa key theo prefix không tự động

~~~redis
DEL user:42
~~~

không xóa:

~~~text
user:42:name
user:42:city
user:42:loginCount
~~~

Nếu tập key được biết trước, hãy xóa theo danh sách. Nếu key sinh động, cần thiết kế index/membership hoặc dùng `SCAN` từng đợt theo phạm vi thích hợp. Tránh dùng `KEYS user:42:*` trên keyspace lớn vì có thể gây tải chặn không mong muốn.

## 7. TTL thường quyết định có tách key hay không

Hãy đặt câu hỏi: **các thuộc tính có cùng vòng đời không?**

| Tình huống | Gợi ý |
|---|---|
| Toàn bộ hồ sơ cache hết hạn sau 30 phút | Hash hoặc JSON |
| Session hết hạn sau 30 phút, profile sau 30 ngày | Tách session thành key riêng |
| Bộ đếm lượt truy cập theo ngày | Key riêng theo ngày với TTL |
| Một số thuộc tính không bao giờ có TTL | Tách khỏi nhóm cache ngắn hạn |
| Mỗi field có TTL riêng | Cân nhắc nhiều key hoặc tính năng field expiration khi được hỗ trợ |
| Muốn gia hạn toàn bộ đối tượng theo hoạt động | Hash/JSON cùng một TTL có thể đơn giản hơn |

Ví dụ:

~~~text
user:42:profile     -> TTL 30 ngày
user:42:session     -> TTL 30 phút
user:42:lastSeen    -> TTL 5 phút
~~~

Một Redis Hash duy nhất thường không phù hợp nếu từng thuộc tính cần hết hạn theo lịch khác nhau và hệ thống không sử dụng cơ chế field expiration. Trái lại, nếu tất cả field hết hạn cùng lúc, tách 20 String key có thể tạo thêm công việc quản lý không cần thiết.

## 8. Tính nguyên tử và nhất quán khi nhiều request cùng ghi

Tính nguyên tử của một lệnh Redis khác với tính nguyên tử của toàn bộ workflow.

### 8.1. Hash: cập nhật một field bằng một lệnh

~~~redis
HINCRBY user:42:profile loginCount 1
~~~

Hai client đồng thời tăng cùng field bằng `HINCRBY` sẽ không mắc lỗi lost update kiểu tự `HGET` rồi `HSET`. Nếu hai client cùng `HSET city` bằng hai giá trị khác nhau, kết quả cuối vẫn phụ thuộc lệnh thực hiện sau.

### 8.2. JSON: SET nguyên tử, chuỗi GET–SET không

~~~redis
SET user:42:snapshot '{"city":"Da Nang","loginCount":8}'
~~~

Lệnh `SET` thay toàn bộ JSON như một giá trị. Nhưng hai thread lấy cùng phiên bản cũ để sửa hai property khác nhau có thể ghi đè lẫn nhau. Nếu cần kiểm tra phiên bản trước khi ghi, cân nhắc `WATCH`/transaction hoặc script và chính sách retry thích hợp.

### 8.3. Nhiều key: mỗi lần SET là một lệnh

~~~redis
SET user:42:city "Da Nang"
SET user:42:verified "true"
~~~

Đây là hai lần cập nhật khác nhau. Một reader xen giữa có thể thấy `city` mới và `verified` cũ.

Khi nghiệp vụ cần tất cả thuộc tính thay đổi như một đơn vị, có thể gói chúng trong một JSON String, một `HSET` nhiều field hoặc dùng cơ chế transaction/script đúng semantics; không nên tự cho rằng các lệnh liên tiếp là nguyên tử.

### 8.4. Khả năng nguyên tử không đảm bảo retry an toàn

Nếu mạng mất sau khi Redis đã thực hiện `INCR` hoặc `HINCRBY` nhưng trước khi client nhận reply, retry có thể tăng lần thứ hai cho cùng một sự kiện. Khi dùng Redis cho tác vụ quan trọng, cần idempotency hoặc cơ chế xác nhận kết quả phù hợp.

## 9. Bộ nhớ, mạng và hiệu năng

Chỉ số quan trọng nhất không phải số field của DTO mà là **dạng truy cập và kích thước dữ liệu thật**.

Ví dụ object JSON có 20 KB nhưng mỗi request chỉ cần `verified`:

- Hash: `HGET key verified` trả về một field nhỏ.
- JSON String: `GET key` trả về cả 20 KB để parse, dù chỉ cần một property.
- Key riêng: `GET user:42:verified` trả về một giá trị nhỏ.

Ngược lại, nếu màn hình luôn cần **toàn bộ 20 KB**, JSON String chỉ cần một `GET` và một lần deserialize; nhiều key riêng có thể phải ghép nhiều phản hồi.

### 9.1. Overhead mỗi key

Một Redis key có chi phí metadata, allocator và dữ liệu cấu trúc. Với một triệu user, mỗi user 20 field:

~~~text
Một Hash mỗi user:
    khoảng 1 triệu key Hash

Một String key cho mỗi field:
    khoảng 20 triệu key String
~~~

Tổng số key có thể ảnh hưởng bộ nhớ, chính sách expiration, scan và vận hành. Hash nhỏ còn có thể sử dụng encoding nội bộ tiết kiệm trong những giới hạn cấu hình/phiên bản nhất định. Tuy nhiên, Hash lớn cũng có chi phí riêng; không suy ra lợi ích bộ nhớ chính xác mà không đo.

### 9.2. Lệnh quan sát

~~~redis
MEMORY USAGE user:42:profile
HLEN user:42:profile
STRLEN user:42:snapshot
INFO memory
DBSIZE
~~~

Với mô hình nhiều key, phải cộng `MEMORY USAGE` của các key thành phần. So một key Hash chứa 20 field với một key String chứa một field là phép so sánh không tương đương.

Khi benchmark, đo:

- Số Redis commands và round-trip trên mỗi request.
- Byte truyền qua mạng.
- Kích thước object/cache và tần suất update từng field.
- CPU JVM cho serialize/deserialize.
- Redis memory và latency khi tải cao.
- Tổng số key và thời gian dọn/expire.

## 10. Redis Cluster và chuyện nhiều key

Redis Cluster chia keyspace thành các hash slot.

Hash và JSON mỗi loại dùng **một key**, nên toàn bộ dữ liệu của key đó thuộc một hash slot. Redis không tự chia các field của cùng một Hash sang nhiều node.

Với nhiều key:

~~~text
user:42:name
user:42:city
user:42:loginCount
~~~

các key có thể nằm ở những slot khác nhau. Các lệnh multi-key chỉ thực hiện được trong phạm vi quy tắc cùng slot của Cluster khi cần.

Khi thật sự phải đặt các key liên quan vào cùng slot, có thể sử dụng **hash tag**:

~~~text
user:{42}:name
user:{42}:city
user:{42}:loginCount
~~~

Các key có hash tag `42` được tính cùng slot. Không gom mọi user về hash tag `{users}`: khi đó toàn bộ key có thể dồn vào một slot, làm mất lợi ích phân tán tải.

Hash quá lớn cũng có thể tạo hotspot vì tất cả field nằm trong một key. Không nên lưu tất cả người dùng thành các field của một key `all-users` chỉ để giảm số key.

## 11. Các ví dụ nghiệp vụ để chọn đúng

### 11.1. Hồ sơ người dùng

~~~text
name, city, locale, verified, loginCount
~~~

Nếu thường xuyên đọc/sửa từng field và cùng TTL, chọn:

~~~text
user:42:profile [Hash]
~~~

`HMGET` lấy những field cần thiết; `HINCRBY` tăng loginCount khi hợp đồng dữ liệu phù hợp.

### 11.2. Snapshot đơn hàng

~~~text
orderId, customer {...}, items [...], shipping {...}, totals {...}
~~~

Nếu UI thường tải toàn bộ snapshot, JSON String phù hợp. Dữ liệu giao dịch chính nên nằm tại nguồn nghiệp vụ đáng tin cậy, còn snapshot Redis được invalidation hoặc refresh khi dữ liệu thay đổi.

### 11.3. Giỏ hàng với số lượng từng SKU

~~~text
cart:42 [Hash]
  SKU-A -> 2
  SKU-B -> 1
~~~

~~~redis
HSET cart:42 SKU-A 2 SKU-B 1
HINCRBY cart:42 SKU-A 1
HDEL cart:42 SKU-B
EXPIRE cart:42 604800
~~~

Hash thích hợp khi mỗi field là số lượng một SKU. Nếu từng item chứa nested options phong phú, có thể cần một schema khác.

### 11.4. Session và bộ đếm riêng

~~~text
user:42:session     [String, TTL 30 phút]
user:42:loginCount  [String, bộ đếm]
~~~

~~~redis
SET user:42:session "session-abc" EX 1800
INCR user:42:loginCount
~~~

Tách key vì TTL và kiểu thao tác khác nhau.

### 11.5. Tags

~~~text
user:42:tags [Set]
~~~

~~~redis
SADD user:42:tags premium beta
SISMEMBER user:42:tags premium
~~~

Khi cần tập phần tử duy nhất hoặc giao/hợp tập, Redis Set thích hợp hơn cả JSON array và một loạt String key.

## 12. Mô hình kết hợp trong ứng dụng thực tế

Một sản phẩm có thể dùng:

~~~text
product:1001:profile      [Hash]
  name, category, brand

product:1001:snapshot     [String JSON]
  images, description, specifications, ...

product:1001:stock        [String counter]
  25

product:1001:tags         [Set]
  keyboard, accessory

product:1001:views:daily  [String counter]
  820
~~~

Mỗi nhóm phục vụ một cách truy cập:

- Profile phẳng để đọc/sửa những field ngắn.
- Snapshot JSON để render trang chi tiết.
- Stock/counter có quy tắc tăng giảm riêng (tồn kho thực phải được bảo vệ bằng nghiệp vụ thích hợp).
- Tags cần phép tập hợp.
- Views có TTL theo kỳ thống kê.

Nếu thông tin sản phẩm được lặp trong cả profile và snapshot, hãy xác định **nguồn dữ liệu nào là chính**, khi nào cần làm mới cache và ứng dụng xử lý dữ liệu cũ thế nào. Sự tiện lợi của việc có nhiều bản sao luôn đi kèm trách nhiệm đồng bộ.

## 13. Những sai lầm cần tránh

### “Một DTO Java = một Redis Hash”

Không. DTO lồng nhiều cấp và thường đọc nguyên khối có thể phù hợp với JSON hơn. Redis Hash phù hợp khi truy cập theo field.

### “JSON thì cập nhật một property cũng rẻ”

Với Redis String JSON thông thường, ứng dụng phải đọc/ghi toàn bộ value. Muốn thao tác JSON path cần khả năng khác, chẳng hạn RedisJSON nếu hạ tầng và client hỗ trợ.

### “Hash cho phép TTL riêng từng field ở mọi Redis”

Thông thường TTL gắn với key. Field expiration phụ thuộc phiên bản và mức hỗ trợ; không mặc định có ở mọi môi trường.

### “Một key cho mỗi thuộc tính luôn linh hoạt hơn”

Nhiều key tăng overhead và làm snapshot/cleanup phức tạp. Chỉ tách khi có nhu cầu truy cập, TTL hoặc kiểu dữ liệu khác biệt.

### “HGETALL luôn tốt vì chỉ gọi một lệnh”

Nếu Hash lớn, phản hồi có thể khổng lồ. Dùng `HGET`/`HMGET` khi chỉ cần ít field.

### “Đặt cùng prefix khiến Redis tự quản lý nhóm key”

Redis không có quan hệ cha–con theo `:`. Muốn dọn tất cả key liên quan cần danh sách, index hoặc quét có kiểm soát.

### “SET JSON mới vẫn giữ TTL cũ”

Lệnh `SET` thông thường không mặc định giữ TTL. Phải đặt/gia hạn/giữ TTL theo API tương ứng.

### “Hai thread cùng cập nhật bằng RedisTemplate sẽ tự nhất quán”

Template có thể được dùng chung nhưng không biến chuỗi read–modify–write thành transaction. Phải sử dụng lệnh nguyên tử, optimistic locking hoặc cơ chế nghiệp vụ phù hợp.

## 14. Di chuyển giữa Hash, JSON và nhiều key

Giả sử trước đây lưu JSON tại:

~~~text
user:42:profile [String JSON]
~~~

và muốn chuyển thành Hash. Không nên trực tiếp `HSET` lên chính key đang là String vì Redis trả `WRONGTYPE`.

Một cách chuyển đổi cache có thể tái tạo:

1. Thiết kế schema mới, serializer và TTL.
2. Dùng namespace mới như `user:42:profile:v2`.
3. Cho ứng dụng mới ghi/đọc cấu trúc v2; khi miss, tải từ nguồn dữ liệu chính.
4. Duy trì đọc tương thích hoặc cho key cũ hết TTL trong thời gian rollout.
5. Theo dõi cache miss, lỗi deserialize và sự tồn tại của key v1.
6. Xóa cách đọc/ghi cũ khi không còn ứng dụng phụ thuộc.

Nếu dữ liệu Redis là nguồn chính, cần migration có kiểm soát hơn: snapshot, đối soát dữ liệu, điều phối ghi trong quá trình chuyển đổi và kế hoạch khôi phục. Không coi cache migration và migration của dữ liệu nghiệp vụ là một.

Schema còn có thể thay đổi mà **kiểu Redis không đổi**. JSON serializer có thể dùng class metadata hoặc schema version; Hash cần quy ước field rõ ràng. Nên duy trì cùng một định dạng giữa nhiều instance đang deploy rolling hoặc dùng namespace version để tránh writer/reader cũ và mới ghi đè dữ liệu không tương thích.

## 15. Cây quyết định

~~~mermaid
flowchart TD
    A[Cần lưu đối tượng vào Redis] --> B{Ứng dụng thường đọc toàn object?}
    B -->|Có| C[JSON String với DTO rõ ràng]
    B -->|Không| D{Các field chủ yếu phẳng?}
    D -->|Có| E{TTL của chúng giống nhau?}
    E -->|Có| F[Redis Hash]
    E -->|Không| G[Tách key theo vòng đời]
    D -->|Không| H[JSON hoặc tách nhóm dữ liệu]
    G --> I{Cần thao tác chuyên biệt?}
    I -->|Có| J[String counter, Set, ZSet, List, Stream...]
    I -->|Không| K[Key String hoặc Hash theo nhóm]
    C --> L[Kiểm tra concurrency, TTL và serializer]
    F --> L
    H --> L
    J --> L
    K --> L
~~~

Sau khi có lựa chọn sơ bộ, hãy kiểm tra:

1. Một request lấy một field, một nhóm field hay toàn bộ object?
2. Thuộc tính nào thay đổi thường xuyên và có thể dùng lệnh nguyên tử?
3. Thuộc tính nào cần TTL độc lập?
4. Dữ liệu có nested object hoặc array phức tạp không?
5. Có cần cập nhật nhiều field/key như một đơn vị?
6. Redis Cluster có yêu cầu cùng hash slot cho các thao tác multi-key không?
7. Số lượng key và dung lượng thật sự là bao nhiêu?
8. Schema/serializer có tương thích giữa các service và phiên bản ứng dụng không?
9. Redis là cache có thể tái tạo hay dữ liệu cần đảm bảo tồn tại?

## 16. Kết luận

**Chọn Hash phẳng** khi đối tượng gồm những field đơn giản, thường đọc hoặc cập nhật từng field, và phần lớn field chia sẻ vòng đời. API chính là `opsForHash()`, với `HGET`, `HMGET`, `HSET`, `HINCRBY`.

**Chọn JSON trong Redis String** khi đối tượng có cấu trúc lồng nhau và ứng dụng thường đọc nguyên snapshot. Dùng `opsForValue()` với JSON serializer/schema rõ ràng; chú ý chi phí đọc–ghi cả document, TTL và lost update.

**Chọn nhiều key riêng** khi những nhóm dữ liệu có TTL, tần suất cập nhật, quyền truy cập hoặc kiểu thao tác khác nhau. Chọn String counter, Set, Sorted Set, Hash hay cấu trúc khác theo từng nhóm, đồng thời quản lý số key, cleanup và consistency.

Trong thực tế, **một thiết kế kết hợp có chủ đích** thường hiệu quả hơn việc ép tất cả dữ liệu vào một kiểu duy nhất. Mô hình Redis tốt là mô hình giúp ứng dụng thực hiện đúng các thao tác cần thiết với số lần truy cập, chi phí lưu trữ và mức độ phối hợp vừa đủ.
