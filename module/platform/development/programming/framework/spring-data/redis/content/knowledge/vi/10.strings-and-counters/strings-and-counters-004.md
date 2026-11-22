# Đọc và ghi nhiều khóa bằng `multiGet` và `multiSet` trong Spring Data Redis

Khi một trang cần hiển thị 20 sản phẩm, một API cần lấy trạng thái của nhiều tài khoản, hoặc một tác vụ cần nạp trước nhiều mục cache, việc gọi Redis `GET` riêng cho từng key làm tăng số lần gửi yêu cầu qua mạng. Redis hỗ trợ thao tác nhiều key bằng **`MGET`** (đọc nhiều giá trị) và **`MSET`** (ghi nhiều cặp key–value). Trong Spring Data Redis, hai lệnh này được biểu diễn qua `ValueOperations.multiGet(...)` và `ValueOperations.multiSet(...)`.

Hai API này hữu ích khi làm việc với các **Redis string**: mỗi Redis key lưu một giá trị nhị phân, có thể là chuỗi UTF-8, JSON hoặc một định dạng được serializer của ứng dụng quy định. Để dùng đúng, cần hiểu thứ tự kết quả, key không tồn tại, TTL, khả năng ghi đè, tính atomic và giới hạn của Redis Cluster.

## 1. Bài toán: đọc và ghi từng key hay theo nhóm?

Giả sử dịch vụ catalog cache tên sản phẩm theo key:

```text
shop:catalog:product-name:p101 -> "Bàn phím"
shop:catalog:product-name:p102 -> "Chuột"
shop:catalog:product-name:p103 -> "Màn hình"
```

Nếu đọc từng key:

```redis
GET shop:catalog:product-name:p101
GET shop:catalog:product-name:p102
GET shop:catalog:product-name:p103
```

Ứng dụng phải thực hiện ba thao tác lệnh Redis. Khi mỗi lệnh được gửi và chờ phản hồi riêng, chi phí mạng tăng theo số key.

Thay bằng một lệnh:

```redis
MGET shop:catalog:product-name:p101 shop:catalog:product-name:p102 shop:catalog:product-name:p103
```

Redis trả về các giá trị theo đúng thứ tự các key được yêu cầu:

```text
1) "Bàn phím"
2) "Chuột"
3) "Màn hình"
```

Tương tự, thay vì gửi ba lệnh `SET` riêng, có thể ghi bằng:

```redis
MSET shop:catalog:product-name:p101 "Bàn phím" shop:catalog:product-name:p102 "Chuột" shop:catalog:product-name:p103 "Màn hình"
```

Đó là cơ sở của các phương thức Spring Data Redis:

| Redis command | Spring Data Redis API | Ý nghĩa |
|---|---|---|
| `GET key` | `opsForValue().get(key)` | Đọc một giá trị |
| `SET key value` | `opsForValue().set(key, value)` | Ghi một giá trị |
| `MGET key1 key2 ...` | `opsForValue().multiGet(keys)` | Đọc giá trị của nhiều key |
| `MSET key1 value1 key2 value2 ...` | `opsForValue().multiSet(map)` | Ghi nhiều cặp key–value |
| `MSETNX key1 value1 ...` | `opsForValue().multiSetIfAbsent(map)` | Chỉ ghi toàn bộ nếu tất cả key chưa tồn tại |

`multiGet` và `multiSet` là API của **`ValueOperations<K,V>`**, nên chúng áp dụng cho thao tác **Redis string value**. Đừng nhầm chúng với thao tác nhiều field trong một Redis hash.

## 2. Luồng xử lý trong Spring Data Redis

Trong một ứng dụng Spring Boot, chúng ta thường dùng `StringRedisTemplate` khi key và value đều là chuỗi:

```text
Controller / Service
       |
       v
StringRedisTemplate
       |
       v
ValueOperations<String, String>
       |                 |
       | multiGet(keys)  | multiSet(map)
       v                 v
RedisConnectionFactory (Lettuce hoặc Jedis)
       |
       v
Redis connection
       |
       v
MGET / MSET trên Redis
```

Với `RedisTemplate<String, Product>`, cách hoạt động tương tự, nhưng `keySerializer` mã hóa tên key và `valueSerializer` mã hóa object thành `byte[]` trước khi gửi lệnh. Khi đọc, giá trị được giải mã theo serializer cấu hình.

Cả hai phương thức **không có trách nhiệm chọn Redis data type dựa trên class Java**: Redis nhận các key và value ở dạng byte. Một JSON được lưu bằng `multiSet` vẫn là **Redis string chứa JSON**, không tự trở thành Redis hash.

## 3. Cấu hình Spring Boot cơ bản

Ví dụ dành cho Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
```

Spring Boot thường tự cung cấp `RedisConnectionFactory` và `StringRedisTemplate` khi điều kiện auto-configuration phù hợp. Service có thể inject template:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CatalogCache {
    private final StringRedisTemplate redis;

    public CatalogCache(StringRedisTemplate redis) {
        this.redis = redis;
    }
}
```

Ví dụ giả định có Redis đang chạy tại `localhost:6379`. Khi ứng dụng chạy trong container, địa chỉ Redis phải được cấu hình theo network thực tế; `localhost` trong container không trỏ tới container Redis khác.

## 4. `multiGet`: đọc nhiều key theo đúng thứ tự

Phương thức:

```java
List<V> multiGet(Collection<K> keys);
```

Được gọi thông qua `redisTemplate.opsForValue()`. Giá trị trả về tương ứng với các key **theo thứ tự lặp của collection truyền vào**.

Ví dụ:

```java
List<String> keys = List.of(
        "shop:catalog:product-name:p101",
        "shop:catalog:product-name:p102",
        "shop:catalog:product-name:p103"
);

List<String> values = redis.opsForValue().multiGet(keys);
```

Nếu có đủ ba key, `values` tương đương:

```text
[
  "Bàn phím",
  "Chuột",
  "Màn hình"
]
```

Điều quan trọng là **giá trị ở vị trí `i` tương ứng với key ở vị trí `i`**. Redis không trả về một `Map<String,String>` chứa cả key và value; nó trả về dãy value. Spring Data Redis giải mã dãy đó thành `List<V>`.

### 4.1. Key không tồn tại được biểu diễn bằng `null`

Giả sử `p102` chưa được cache:

```redis
MGET shop:catalog:product-name:p101 shop:catalog:product-name:p102 shop:catalog:product-name:p103
```

Kết quả ở mức Redis:

```text
1) "Bàn phím"
2) (nil)
3) "Màn hình"
```

Ở mức Java, kết quả thông thường là:

```java
List<String> values = List.of(...); // Minh họa ý tưởng, không dùng List.of với null.
```

Cách biểu diễn dữ liệu thật phải cho phép phần tử `null`, chẳng hạn:

```text
values.get(0) == "Bàn phím"
values.get(1) == null
values.get(2) == "Màn hình"
```

`List.of(...)` trong Java **không cho phép phần tử `null`**. Vì vậy, không thể dùng nó để tạo một danh sách giả lập gồm những giá trị trả về bị thiếu. Danh sách do `multiGet` trả về có thể chứa `null` ở các vị trí key không tồn tại.

Lưu ý thêm: Redis `MGET` trả nil cho một key không có giá trị kiểu string hợp lệ, bao gồm trường hợp key không tồn tại và trường hợp key có Redis type không phải string. Nếu thấy `null` bất ngờ, cần kiểm tra `TYPE key` và hợp đồng serializer; đừng vội kết luận đó chỉ là cache miss.

### 4.2. Chọn collection có thứ tự ổn định

Nên truyền `List<String>` nếu cần ghép lại kết quả với ID ban đầu. `HashSet` không cung cấp thứ tự duyệt được đảm bảo cho nghiệp vụ; `Map` tạo từ kết quả cũng có thể làm mất thông tin key trùng lặp.

Ví dụ:

```java
List<String> keys = List.of("k3", "k1", "k2");
List<String> values = redis.opsForValue().multiGet(keys);

// values[0] thuộc k3
// values[1] thuộc k1
// values[2] thuộc k2
```

Nếu input có key lặp, dãy kết quả vẫn theo từng vị trí yêu cầu. Khi chuyển sang `Map`, các phần tử trùng key sẽ bị gộp; điều này có thể là chủ đích nhưng không còn giữ nguyên toàn bộ input.

### 4.3. Giá trị trả về của cả lời gọi cũng có thể `null`

Trong ngữ cảnh thực thi đồng bộ bình thường, `multiGet` trả về danh sách các phần tử ứng với key. Tuy nhiên, các API Spring Data Redis có thể trả về **`null` cho chính kết quả phương thức** khi thao tác được đưa vào pipeline hoặc transaction: kết quả thực tế được gom và trả sau.

Do đó, cần phân biệt:

- `values != null` nhưng `values.get(i) == null`: thường là key thứ `i` không có string value có thể đọc.
- `values == null`: có thể do ngữ cảnh pipeline/transaction; không thể suy ra toàn bộ key đều thiếu.

Khi dùng `multiGet` thông thường trong service, có thể kiểm tra `values == null` để không vô tình đánh đồng tình huống này với cache miss.

## 5. Ví dụ Java hoàn chỉnh: đọc nhiều sản phẩm và giữ ánh xạ ID

Giả sử service nhận danh sách product ID và muốn trả về dữ liệu cùng thứ tự input. Một record kết quả giữ rõ cả ID và payload:

```java
package com.example.shop.redis;

public record CachedProduct(String productId, String json) {
    public boolean found() {
        return json != null;
    }
}
```

Service:

```java
package com.example.shop.redis;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductBatchCache {

    private final StringRedisTemplate redis;

    public ProductBatchCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static String key(String id) {
        Objects.requireNonNull(id, "productId");
        if (id.isBlank()) {
            throw new IllegalArgumentException("productId must not be blank");
        }
        return "shop:catalog:product-json:v1:" + id;
    }

    public List<CachedProduct> readMany(List<String> productIds) {
        Objects.requireNonNull(productIds, "productIds");

        if (productIds.isEmpty()) {
            return List.of();
        }

        List<String> keys = productIds.stream()
                .map(ProductBatchCache::key)
                .toList();

        List<String> payloads = redis.opsForValue().multiGet(keys);

        if (payloads == null) {
            throw new IllegalStateException(
                    "multiGet result unavailable in this execution context");
        }
        if (payloads.size() != productIds.size()) {
            throw new IllegalStateException(
                    "Unexpected number of Redis values");
        }

        List<CachedProduct> result = new ArrayList<>(productIds.size());
        for (int i = 0; i < productIds.size(); i++) {
            result.add(new CachedProduct(
                    productIds.get(i),
                    payloads.get(i)
            ));
        }
        return result;
    }
}
```

Nếu dữ liệu Redis chứa `p101` và `p103` nhưng thiếu `p102`, `readMany(List.of("p101","p102","p103"))` trả về ba phần tử, trong đó phần tử thứ hai có `json == null` và `found() == false`.

Ở một API đọc cache, có thể lấy các ID thiếu rồi truy vấn nguồn dữ liệu chính và nạp bù cache. Cần xử lý từng ID thiếu, **không xóa vị trí `null` rồi ghép tuần tự các giá trị còn lại**, vì sẽ dẫn tới gán sản phẩm sai ID.

Hàm `key(...)` ở trên chỉ minh họa tên key tập trung. Khi ID lấy từ input bên ngoài, ứng dụng nên xác thực hoặc mã hóa ID theo quy tắc namespace đã thống nhất, nhất là nếu ID có thể chứa dấu phân tách, ký tự điều khiển hoặc dữ liệu nhạy cảm.

## 6. `multiSet`: ghi nhiều cặp key–value trong một lệnh

Phương thức của `ValueOperations`:

```java
void multiSet(Map<? extends K, ? extends V> m);
```

Ví dụ:

```java
Map<String, String> products = new LinkedHashMap<>();
products.put("shop:catalog:product-name:p101", "Bàn phím");
products.put("shop:catalog:product-name:p102", "Chuột");
products.put("shop:catalog:product-name:p103", "Màn hình");

redis.opsForValue().multiSet(products);
```

`LinkedHashMap` giúp dễ đọc và lặp lại dữ liệu theo thứ tự chèn trong ví dụ, nhưng `MSET` không yêu cầu có thứ tự cặp key–value để bảo đảm ý nghĩa: mỗi key được gắn với đúng value của nó.

`multiSet` thường không trả về một danh sách giá trị hoặc số lượng key đã ghi. Nếu lệnh hoàn tất thành công, các cặp được ghi theo semantics của Redis `MSET`.

### 6.1. `MSET` ghi đè key có sẵn

Nếu Redis đã có:

```text
shop:catalog:product-name:p101 -> "Bàn phím cũ"
```

Gọi `multiSet` với giá trị `"Bàn phím"` sẽ thay value hiện tại. `MSET` không phải thao tác chỉ ghi khi key chưa tồn tại.

Khi đã tồn tại key kiểu Redis khác, thao tác `MSET` có thể thay key đó bằng Redis string. Vì vậy, đặt tên key và phân định quyền ghi rõ ràng là cần thiết, nhất là khi nhiều service dùng chung Redis.

### 6.2. `MSET` không đặt TTL

Redis `MSET` không nhận cặp tham số hết hạn cho từng key giống dạng `SET key value EX seconds`. Mỗi cặp được ghi như một giá trị không kèm expiry mới; **TTL cũ trên những key bị thay thế cũng bị bỏ đi** theo semantics ghi đè của `MSET`.

Ví dụ:

```redis
SET demo:batch:a "old" EX 30
TTL demo:batch:a
MSET demo:batch:a "new" demo:batch:b "second"
TTL demo:batch:a
```

Sau `MSET`, `TTL demo:batch:a` thông thường trả về `-1`, nghĩa là key tồn tại nhưng không có thời hạn tự hết hạn. Điều này rất quan trọng nếu những key là cache hoặc session đáng lẽ chỉ sống trong thời gian ngắn.

### 6.3. `MSET` là atomic ở phạm vi một lệnh trên một Redis server

Trên một Redis server, `MSET` ghi các cặp key–value như **một lệnh atomic**: một client khác không quan sát được trạng thái trong đó chỉ một số key của cùng lệnh `MSET` đã được cập nhật rồi mới tới các key còn lại.

Tuy nhiên, tính atomic đó không bao gồm những câu lệnh khác ở trước/sau, không tự đảm bảo dữ liệu quan hệ được duy trì ở database bên ngoài, và không đồng nghĩa với một transaction nghiệp vụ phân tán.

## 7. Ví dụ Java: ghi nhiều payload JSON

Trong ứng dụng dùng `StringRedisTemplate`, có thể chủ động chuyển object sang JSON ở tầng ứng dụng rồi dùng `multiSet` để ghi nhiều giá trị:

```java
package com.example.shop.redis;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductBatchWriter {

    private final StringRedisTemplate redis;

    public ProductBatchWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void writeMany(Map<String, String> jsonByProductId) {
        Objects.requireNonNull(jsonByProductId, "jsonByProductId");

        if (jsonByProductId.isEmpty()) {
            return;
        }

        Map<String, String> redisEntries = new LinkedHashMap<>();

        jsonByProductId.forEach((id, json) -> {
            Objects.requireNonNull(id, "productId");
            Objects.requireNonNull(json, "json");
            if (id.isBlank()) {
                throw new IllegalArgumentException("productId must not be blank");
            }
            redisEntries.put(
                    "shop:catalog:product-json:v1:" + id,
                    json
            );
        });

        redis.opsForValue().multiSet(redisEntries);
    }
}
```

Ví dụ input:

```java
writer.writeMany(Map.of(
        "p101", "{\"name\":\"Bàn phím\"}",
        "p102", "{\"name\":\"Chuột\"}"
));
```

Lúc này Redis lưu **hai key kiểu string**, mỗi value chứa văn bản JSON. `StringRedisTemplate` không tự kiểm tra JSON hợp lệ. Nếu cần viết object Java trực tiếp, hãy dùng `RedisTemplate<String, Product>` với serializer phù hợp và bảo đảm các bên đọc cùng sử dụng hợp đồng định dạng.

**Lưu ý:** Phương thức này thích hợp cho dữ liệu không cần TTL hoặc có chính sách expiry được xử lý riêng một cách có chủ đích. Với cache bắt buộc hết hạn, cần cân nhắc API khác ở phần tiếp theo.

## 8. TTL: khi nào không nên dùng `multiSet`?

`ValueOperations.set(key, value, timeout)` cho phép đặt TTL cho từng lần ghi:

```java
redis.opsForValue().set(
        "shop:catalog:product-json:v1:p101",
        "{\"name\":\"Bàn phím\"}",
        Duration.ofMinutes(10)
);
```

Trong khi đó, `multiSet(Map)` không có overload tương ứng nhận TTL cho toàn bộ map. Có thể thử làm:

```java
redis.opsForValue().multiSet(values);
values.keySet().forEach(key ->
        redis.expire(key, Duration.ofMinutes(10))
);
```

Nhưng **đây là nhiều lệnh**: `MSET` hoàn tất trước, sau đó `EXPIRE` được gửi lần lượt. Nếu ứng dụng mất kết nối giữa chừng, có thể tồn tại key không có TTL. Client khác cũng có thể đọc các key trước khi mọi lệnh `EXPIRE` hoàn tất.

Đối với cache, một cách rõ ràng và thường an toàn hơn là dùng `set(key, value, ttl)` cho từng key và, khi cần giảm lượt trao đổi mạng, **pipeline** các lệnh `SET` độc lập. Cách này có thể giảm chi phí round-trip nhưng không làm nhiều lệnh trở thành một thao tác atomic chung.

Nếu cần vừa cập nhật nhiều key vừa áp TTL **trong cùng một thao tác atomic**, cần thiết kế giải pháp phù hợp như Lua script hoặc transaction trên Redis, có kiểm tra ràng buộc Redis Cluster. Một script/chunk Lua cần được thiết kế có giới hạn công việc, xử lý kiểu dữ liệu và lỗi một cách cẩn trọng; không nên triển khai chỉ để tránh vài lệnh mạng khi dữ liệu không yêu cầu atomicity.

| Nhu cầu | Cách thường phù hợp |
|---|---|
| Ghi nhiều giá trị string, không cần TTL | `multiSet(map)` |
| Ghi một giá trị có TTL | `set(key, value, Duration)` |
| Ghi nhiều giá trị với TTL riêng | Lặp `set(..., ttl)`, có thể pipeline |
| Nhiều key phải cập nhật atomic và cùng slot | Xem xét `MSET` hoặc script/transaction thiết kế cho cùng slot |
| Cache có thể tính lại khi thiếu | Cho phép cache miss và refill; tránh làm phức tạp quá mức |

## 9. `multiSetIfAbsent`: chỉ ghi khi tất cả key chưa tồn tại

Ngoài `multiSet`, `ValueOperations` còn cung cấp:

```java
Boolean multiSetIfAbsent(Map<? extends K, ? extends V> m);
```

Đây là thao tác tương ứng với Redis `MSETNX`. Khác với từng lệnh `SETNX` riêng lẻ, `MSETNX` kiểm tra **cả nhóm key**: nếu **bất kỳ key nào** đã tồn tại, lệnh không ghi cặp nào trong nhóm.

Ví dụ:

```redis
SET demo:batch:existing "value"
MSETNX demo:batch:existing "new" demo:batch:other "other"
```

Kết quả là `0` (không ghi). `demo:batch:existing` giữ giá trị `"value"`, và `demo:batch:other` vẫn không được tạo.

Nếu mọi key đều chưa tồn tại:

```redis
MSETNX demo:batch:new1 "a" demo:batch:new2 "b"
```

Kết quả là `1` và cả hai key được tạo.

Trong Java:

```java
Map<String, String> initial = Map.of(
        "demo:batch:new1", "a",
        "demo:batch:new2", "b"
);

Boolean inserted = redis.opsForValue().multiSetIfAbsent(initial);

if (Boolean.TRUE.equals(inserted)) {
    // Tất cả key đều chưa tồn tại và được ghi.
} else if (Boolean.FALSE.equals(inserted)) {
    // Ít nhất một key đã tồn tại, không có key nào được ghi.
} else {
    // Kết quả có thể được trả sau trong pipeline/transaction.
}
```

`MSETNX` không tự đặt TTL và không phải cơ chế khóa phân tán đầy đủ. Nếu muốn lock, cần thiết kế cả thời hạn, token sở hữu, giải phóng lock an toàn và xử lý tiến trình chết.

## 10. Phân biệt `multiGet` với thao tác nhiều field trong Redis hash

Có hai API Spring Data Redis cùng tên `multiGet` nhưng thuộc hai nhóm khác nhau:

| API | Lệnh tương đương | Mô hình dữ liệu |
|---|---|---|
| `redis.opsForValue().multiGet(redisKeys)` | `MGET` | Nhiều Redis key, mỗi key có string value |
| `redis.opsForHash().multiGet(redisKey, fields)` | `HMGET` | Nhiều field bên trong **một** Redis hash key |

Ví dụ dữ liệu:

```redis
HSET shop:catalog:inventory:p101 available 25 reserved 4 warehouse "HCM"
```

Muốn lấy hai field `available` và `reserved`:

```java
List<Object> values = redis.opsForHash().multiGet(
        "shop:catalog:inventory:p101",
        List.of("available", "reserved")
);
```

Lệnh Redis tương ứng là:

```redis
HMGET shop:catalog:inventory:p101 available reserved
```

Không dùng `opsForValue().multiGet` với các **field** `available`, `reserved` vì chúng không phải Redis key độc lập.

Tương tự, `opsForHash().putAll(redisKey, map)` dùng để ghi nhiều field của một Redis hash; `opsForValue().multiSet(map)` dùng để ghi nhiều key Redis string. Chúng khác nhau về loại dữ liệu, semantics truy cập và thiết kế keyspace.

## 11. Redis Cluster: giới hạn hash slot với lệnh nhiều key

Redis Cluster phân phối key qua **16.384 hash slot**. Redis server yêu cầu những key liên quan tới một lệnh đa key có tính atomic trên node phải nằm trong **cùng slot**. Với các lệnh native `MGET`, `MSET` và `MSETNX`, gửi một nhóm key thuộc các slot khác nhau trực tiếp tới Cluster có thể nhận lỗi `CROSSSLOT`.

Ví dụ:

```text
shop:cart:101:items
shop:cart:101:total
```

Dù hai tên cùng prefix, chúng không tự động cùng hash slot. Redis tính slot từ nội dung key, không từ đoạn prefix phân tách bởi dấu `:`.

### 11.1. Dùng hash tag khi cần đặt nhiều key chung slot

Redis Cluster hỗ trợ **hash tag**: nếu tên key chứa cặp ngoặc nhọn hợp lệ, Redis tính hash slot dựa trên phần bên trong ngoặc.

```text
shop:cart:{101}:items
shop:cart:{101}:total
```

Cả hai key có hash tag `101` nên cùng slot và có thể dùng trong một lệnh `MGET` hoặc `MSET` trên Cluster.

Kiểm tra bằng Redis CLI:

```bash
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT 'shop:cart:{101}:items'
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT 'shop:cart:{101}:total'
```

Hai kết quả phải bằng nhau. Địa chỉ node chỉ là ví dụ; thay bằng endpoint Redis Cluster của môi trường thực hành.

Hash tag chỉ nên gom các key **thực sự cần thao tác cùng nhau**. Nếu dùng `{shop}` cho tất cả key trong ứng dụng, chúng sẽ rơi vào một slot, dẫn tới phân phối tải kém và tạo điểm nóng.

### 11.2. Client có thể xử lý cross-slot khác nhau

Một số client/framework có thể chia thao tác đọc nhiều key thành các lệnh gửi đến từng node và tổng hợp kết quả. Điều đó phụ thuộc driver, phiên bản và API. Không được giả định rằng mọi `multiGet` cross-slot đều thực hiện một lệnh `MGET` native atomic; cũng không được giả định `multiSet` cross-slot sẽ có atomicity giống một lệnh trên một node.

Nếu ứng dụng cần **semantics atomic chắc chắn**, hãy thiết kế những key liên quan ở cùng slot và dùng lệnh/transaction được Redis Cluster hỗ trợ trong trường hợp đó. Nếu ứng dụng chỉ cần đọc dữ liệu cache độc lập ở nhiều slot, việc gom kết quả hoặc phân nhóm theo slot có thể phù hợp nhưng cần đánh giá hành vi cụ thể của driver.

### 11.3. Namespace và serializer key cũng ảnh hưởng slot

`StringRedisTemplate` thường dùng serializer UTF-8 cho key. Một template khác dùng serializer nhị phân cho key sẽ tạo **các byte key khác nhau**, có thể khiến hash slot khác nhau dù chuỗi Java trông giống nhau. Trong kiến trúc nhiều service hoặc nhiều ngôn ngữ, nên thống nhất quy tắc key và key serializer.

Redis Cluster chỉ hỗ trợ logical database số `0`; việc dùng DB 1 để nhóm key liên quan là một cách làm chỉ áp dụng cho Redis standalone, không giải quyết được hạn chế slot của Cluster.

## 12. `multiGet` có phải một snapshot nhất quán?

Với một lệnh `MGET` native được thực thi trên cùng một Redis server, Redis xử lý lệnh đó atomic trong thứ tự lệnh của server: không có một lệnh khác chen vào giữa việc lấy các phần tử của chính `MGET` đó.

Tuy nhiên, điều này **không bảo đảm rằng các key đã tạo nên một phiên bản nghiệp vụ nhất quán trước đó** nếu phía ghi cập nhật từng key bằng nhiều lệnh.

Ví dụ:

```text
Trạng thái đầu: price=100, discount=10

Writer:
    SET price 120
    SET discount 20

Reader chạy MGET giữa hai lệnh SET:
    price=120, discount=10
```

Reader nhận một tổ hợp trạng thái có thể chưa phản ánh quy tắc nghiệp vụ mà writer mong muốn. `MGET` không tự ghép hai lần `SET` thành một transaction; muốn reader thấy chúng thay đổi cùng nhau, phía writer cần cập nhật bằng một thao tác atomic phù hợp như `MSET` khi các key nằm cùng phạm vi thực thi.

Ngay cả khi dùng `MSET`, một thao tác cập nhật tiếp theo ở hệ thống khác hoặc database khác vẫn có thể thất bại. Với những dữ liệu cần transaction liên hệ nhiều nguồn, Redis `MGET`/`MSET` không thay thế cơ chế nhất quán tổng thể.

Trong Redis Cluster, việc đọc các key nằm trên nhiều slot/node có thể là nhiều thao tác mạng, vì vậy không có snapshot atomic toàn Cluster chỉ từ việc gọi một API tổng hợp ở client.

## 13. So sánh `multiGet` với pipeline và nhiều lệnh `GET`

**`multiGet`** gửi một thao tác đọc nhiều key (nếu topology/driver cho phép). **Pipeline** gửi nhiều lệnh mà không phải chờ phản hồi từng lệnh trước khi gửi lệnh tiếp theo. Chúng giải quyết những vấn đề liên quan nhưng không hoàn toàn giống nhau.

| Cách làm | Số lệnh logic | Có thể giảm round-trip? | Atomic nhiều key? | Điểm lưu ý |
|---|---:|---|---|---|
| Vòng lặp `GET` đồng bộ | N lệnh | Không, nếu chờ từng lệnh | Không | Dễ triển khai, nhưng nhiều lần trao đổi mạng |
| `MGET` | 1 lệnh Redis native trong phạm vi hỗ trợ | Có | Một lệnh trên một server/slot | Chỉ cho Redis string, có giới hạn Cluster |
| Pipeline N lệnh `GET` | N lệnh | Có | Không | Tốn thêm bộ nhớ để gom kết quả, phù hợp lệnh độc lập |
| `HMGET` | 1 lệnh đọc nhiều field | Có | Một Redis hash key | Không phải đọc nhiều Redis key |
| Transaction `MULTI`/`EXEC` | N lệnh nằm trong transaction | Phụ thuộc cách gửi | Theo semantics Redis transaction | Cần kiểm tra Cluster, lỗi command và hình thức trả kết quả |

Ví dụ vòng lặp đồng bộ:

```java
List<String> values = new ArrayList<>();
for (String key : keys) {
    values.add(redis.opsForValue().get(key));
}
```

Cách này dễ hiểu, nhưng nếu mỗi `get` chờ response trước khi gọi tiếp thì ứng dụng phải chờ nhiều round-trip. `multiGet` thường là lựa chọn tự nhiên khi cùng lấy nhiều Redis string key ở một lần.

Pipeline có thể hữu ích khi cần các command khác nhau hoặc các lệnh có TTL riêng:

```text
SET key1 value1 EX 60
SET key2 value2 EX 120
SET key3 value3 EX 180
```

Dùng pipeline để gửi nhanh ba lệnh trên không làm chúng atomic. Nếu ứng dụng mất kết nối sau khi một phần lệnh đến server, cần xử lý trạng thái hoàn thành không chắc chắn. Thông tin trả về cũng được thu thập khi pipeline kết thúc, thay vì ở từng lời gọi API được xếp hàng vào pipeline.

## 14. Kích thước batch: ít lệnh hơn chưa chắc luôn nhanh hơn

`MGET` giúp giảm round-trip, nhưng một lời gọi với hàng trăm nghìn key vẫn có thể tạo payload lớn, khiến Redis phải xử lý nhiều dữ liệu và ứng dụng phải giữ list kết quả lớn trong bộ nhớ.

Các yếu tố cần quan sát:

- **Số key trong một lần gọi:** số phần tử quá lớn làm tăng kích thước request và response.
- **Kích thước mỗi value:** lấy 100 key chứa JSON 1 KB khác hẳn lấy 100 key chứa payload 1 MB.
- **Độ trễ mạng:** khi RTT cao, việc giảm số lần gọi thường đem lại lợi ích đáng kể.
- **Serialization/deserialization:** giải mã rất nhiều JSON object có thể chiếm CPU của JVM, ngay cả khi Redis phản hồi nhanh.
- **Hash slot và topology:** trên Cluster, grouping theo slot hoặc chia lệnh có thể ảnh hưởng hành vi và thông lượng.
- **Giới hạn connection/pool:** nhiều batch lớn chạy song song có thể làm một connection bận lâu, gây queueing cho request khác.

Không có một kích thước batch chuẩn cho mọi hệ thống. Nên lựa chọn dựa trên kích thước payload và latency quan sát được. Với danh sách rất lớn, có thể chia thành các batch có giới hạn:

```java
public List<String> readByChunks(
        StringRedisTemplate redis,
        List<String> keys,
        int chunkSize) {

    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize must be positive");
    }

    List<String> all = new ArrayList<>(keys.size());
    for (int start = 0; start < keys.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, keys.size());
        List<String> part = redis.opsForValue()
                .multiGet(keys.subList(start, end));

        if (part == null) {
            throw new IllegalStateException(
                    "Unexpected multiGet result in pipeline/transaction");
        }
        all.addAll(part);
    }
    return all;
}
```

Code này minh họa chia một danh sách thành nhiều lần `multiGet`. Mỗi phần được nối theo đúng thứ tự input, kể cả các phần tử `null`. Nếu một batch lỗi sau khi các batch trước đã đọc thành công, caller cần quyết định retry hoặc trả lỗi; việc chia batch không tạo snapshot nhất quán trên toàn bộ danh sách.

## 15. Serializer và tình huống nhiều kiểu value

`StringRedisTemplate` dùng chuỗi cho key và value, phù hợp với ví dụ tên sản phẩm hoặc payload JSON đã serialize. Nếu cần đọc/ghi object Java:

```java
public record ProductSnapshot(String id, String name, long priceMinor) {}
```

Có thể cấu hình một `RedisTemplate<String, ProductSnapshot>` sử dụng `StringRedisSerializer` cho key và serializer JSON có kiểu rõ ràng cho value:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProductRedisConfig {

    @Bean
    RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(ProductSnapshot.class));
        template.afterPropertiesSet();
        return template;
    }
}
```

Sau đó có thể dùng:

```java
Map<String, ProductSnapshot> values = Map.of(
        "catalog:product:v1:p101",
        new ProductSnapshot("p101", "Bàn phím", 350000),
        "catalog:product:v1:p102",
        new ProductSnapshot("p102", "Chuột", 180000)
);

productRedisTemplate.opsForValue().multiSet(values);

List<ProductSnapshot> products = productRedisTemplate.opsForValue()
        .multiGet(List.of(
                "catalog:product:v1:p101",
                "catalog:product:v1:p102"
        ));
```

Kết quả đọc phụ thuộc vào **serializer được dùng khi ghi**. Nếu các key đã chứa payload JDK serialization hoặc dữ liệu hash, thay serializer thành Jackson rồi gọi `multiGet` sẽ không tự chuyển được dữ liệu cũ. Khi thay định dạng, cần có chiến lược version key, migration hoặc tạo lại cache.

Với các kiểu Java phức tạp như `Instant`, polymorphic type và định dạng JSON tùy biến, cần cấu hình Jackson mapper/module phù hợp với phiên bản framework. Không nên giả định mọi serializer tự kế thừa toàn bộ cấu hình `ObjectMapper` của ứng dụng.

## 16. Xử lý cache miss theo nhóm và tránh làm mất thứ tự

Một trường hợp thực tế: API nhận `["p101","p102","p103"]`, Redis chỉ có `p101`, `p103`. Quy trình thường là:

```text
Input IDs:       p101, p102, p103
                    |
multiGet(keys)       v
Cache result:    hit,  null, hit
                    |
                    +----> tìm các ID bị thiếu: p102
                                  |
                              đọc database
                                  |
                              nạp cache
                                  |
Kết quả API:     p101, p102, p103
```

Khi nạp lại dữ liệu, cần chú ý:

1. Chỉ những ID thiếu thực sự mới cần đọc database; Redis có thể trả `null` cho kiểu dữ liệu sai nên cần biết điều kiện hợp đồng khi diagnostic.
2. Kết quả database có thể không theo thứ tự ID yêu cầu, vì vậy phải ghép theo **ID**, không ghép theo vị trí mặc định.
3. Dữ liệu bị xóa hoặc không tồn tại trong database cần chính sách rõ ràng: trả missing, cache giá trị sentinel hoặc không cache.
4. Khi nạp cache và cần TTL, dùng thao tác ghi có expiry tương ứng; `multiSet` không tự đặt expiry.
5. Nhiều request cùng cache miss một key có thể cùng đọc database (cache stampede); `multiGet` không tự giải quyết vấn đề này.

Ví dụ pseudocode:

```text
ids = ["p101", "p102", "p103"]
redisValues = multiGet(makeKeys(ids))
missedIds = select ids[i] where redisValues[i] is null

dbRows = database.findByIds(missedIds)
dbById = indexById(dbRows)

return ids.map(id ->
    cached value if present
    else dbById.get(id)
)
```

Với cache có thể tái tạo, tính đúng đắn của logic ghép theo ID thường quan trọng hơn việc giảm thêm một lệnh Redis.

## 17. Lỗi và những hiểu nhầm thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Kết quả `multiGet` có `null` ở giữa | Key không tồn tại, hết TTL, hoặc Redis type không phù hợp | Kiểm tra key gốc và `TYPE`/`EXISTS` ở môi trường được phép |
| `multiGet` trả `null` toàn bộ | Lời gọi trong pipeline/transaction hoặc ngữ cảnh kết quả hoãn | Kiểm tra cách gọi `executePipelined` / `SessionCallback` |
| Kết quả bị gán nhầm ID | Ghép list theo thứ tự khác input; đã xóa các `null` trước khi ghép | Giữ `List` key có thứ tự và ghép theo chỉ số |
| `multiSet` ghi rồi key không hết hạn | Lệnh `MSET` không đặt TTL và xóa TTL cũ khi ghi đè | Quan sát `TTL key`, sửa chiến lược ghi |
| `multiSetIfAbsent` không tạo key mới dù một số key chưa tồn tại | Một key trong nhóm đã tồn tại, nên `MSETNX` không ghi tất cả | Dùng `EXISTS` với key liên quan hoặc đổi semantics nghiệp vụ |
| Lỗi `CROSSSLOT` | Key trong lệnh đa key native thuộc nhiều slot Cluster | Kiểm tra `CLUSTER KEYSLOT`; thiết kế hash tag khi thực sự cần |
| Lỗi deserialize khi đọc nhiều key | Writer và reader dùng serializer/schema khác nhau | Kiểm tra serializer/encoding/version của key |
| `MGET` thấy `nil` nhưng `EXISTS` cho thấy key có mặt | Key có Redis type không phải string hoặc trạng thái đã đổi giữa hai lệnh | Kiểm tra `TYPE` và cách service khác ghi key |
| Batch rất lớn làm request chậm | Nhiều key hoặc payload lớn, CPU deserialization/memory/connection bận | Giới hạn batch, đo latency và kích thước response |

Các lệnh như `TYPE` và `TTL` có thể giúp chẩn đoán, nhưng kết quả của những lệnh gọi riêng **không phải một snapshot nhất quán** nếu có writer thay đổi key đồng thời.

## 18. Bài thực hành với Redis CLI

Trên Redis standalone thử nghiệm, ghi một nhóm key:

```bash
redis-cli MSET demo:multikey:p1 "A" demo:multikey:p2 "B" demo:multikey:p3 "C"
```

Đọc lần lượt và đọc cùng lúc:

```bash
redis-cli GET demo:multikey:p1
redis-cli GET demo:multikey:p2
redis-cli MGET demo:multikey:p3 demo:multikey:p1 demo:multikey:missing
```

Dự kiến lệnh `MGET` cuối hiển thị:

```text
1) "C"
2) "A"
3) (nil)
```

Quan sát rằng kết quả theo **thứ tự yêu cầu** (`p3`, `p1`, `missing`), không theo thứ tự đã ghi (`p1`, `p2`, `p3`).

Kiểm tra tính ghi đè và TTL:

```bash
redis-cli SET demo:multikey:expire "old" EX 120
redis-cli TTL demo:multikey:expire
redis-cli MSET demo:multikey:expire "new" demo:multikey:p4 "D"
redis-cli TTL demo:multikey:expire
```

Sau `MSET`, key `demo:multikey:expire` còn tồn tại nhưng không còn TTL, nên `TTL` sẽ trả `-1` nếu không có thao tác đồng thời khác làm thay đổi key.

Thử `MSETNX`:

```bash
redis-cli MSETNX demo:multikey:p1 "overwritten?" demo:multikey:only-if-all-new "X"
redis-cli EXISTS demo:multikey:only-if-all-new
```

Vì `p1` đã tồn tại, lệnh `MSETNX` trả `0` và key mới cũng không được tạo. Bài thực hành chỉ dùng prefix `demo:multikey:` để tránh tác động lên key nghiệp vụ; nếu thao tác trên một Redis đang chia sẻ, cần xác nhận môi trường và quyền sử dụng trước khi ghi.

### Kiểm tra trên Redis Cluster

Nếu có Cluster thử nghiệm, dùng hai key cùng hash tag:

```bash
redis-cli -c -h redis-node-1 -p 6379 MSET 'demo:{batch42}:a' "A" 'demo:{batch42}:b' "B"
redis-cli -c -h redis-node-1 -p 6379 MGET 'demo:{batch42}:a' 'demo:{batch42}:b'
```

Vì hash tag `batch42` giống nhau, hai key thuộc cùng slot. Khi làm việc với key khác slot, hành vi của client/framework cần được xem xét theo phần Redis Cluster trước đó; không dùng multi-key operation với giả định atomic xuyên node.

## 19. Những câu hỏi tự kiểm tra

**1. Tại sao `multiGet` trả về `List` mà không phải `Map`?**

Lệnh `MGET` trả danh sách các value theo thứ tự key được cung cấp. Vị trí giúp phân biệt key có mặt và key bị thiếu, cũng như giữ được những lần lặp key nếu input có duplicate.

**2. Redis thiếu key thứ hai trong ba key được yêu cầu thì kết quả ra sao?**

Thông thường danh sách có ba phần tử, với phần tử thứ hai là `null`. Không được xóa `null` rồi ghép lại theo ID vì sẽ làm sai thứ tự.

**3. `multiSet` có thể thay thế `set(key, value, Duration)` khi ghi cache không?**

Không tương đương. `multiSet` không có tham số TTL; việc ghi đè có thể xóa TTL cũ. Nếu TTL là yêu cầu, cần chọn chiến lược ghi hỗ trợ expiry.

**4. `multiSetIfAbsent` khác gọi `setIfAbsent` nhiều lần ở điểm nào?**

`multiSetIfAbsent` dùng semantics `MSETNX`: nếu bất kỳ key nào đã tồn tại, cả nhóm không được ghi. Gọi `setIfAbsent` từng key có thể tạo một phần nhóm trước khi gặp key đã tồn tại.

**5. Đọc 100 key bằng `multiGet` có luôn atomic trong Redis Cluster không?**

Không thể giả định. Lệnh native nhiều key có ràng buộc cùng slot; một số client có thể phân tán thao tác đọc qua nhiều node, khi đó không có snapshot atomic xuyên toàn Cluster.

**6. `multiGet` có thể đọc nhiều field `name` và `price` từ cùng một Redis hash không?**

Dùng `opsForHash().multiGet(hashKey, fields)` tương ứng `HMGET`. `opsForValue().multiGet(keys)` dùng cho nhiều Redis key string.

**7. Tại sao `multiGet` giảm chi phí mạng nhưng vẫn có thể làm server chậm?**

Số key và kích thước payload quá lớn khiến Redis, JVM và network phải xử lý lượng dữ liệu đáng kể trong một lần. Cần đo latency và chia batch phù hợp thay vì tăng kích thước không giới hạn.

## 20. Kết luận

Trong Spring Data Redis, **`opsForValue().multiGet(keys)`** dùng để đọc nhiều Redis string key và trả giá trị theo đúng thứ tự key đầu vào; key thiếu có thể cho phần tử `null`. **`opsForValue().multiSet(map)`** ghi nhiều cặp key–value theo semantics Redis `MSET`, ghi đè dữ liệu cũ và **không tự đặt TTL**. Khi muốn ghi có điều kiện cho cả nhóm, dùng `multiSetIfAbsent` và hiểu semantics “tất cả hoặc không có gì” của `MSETNX`.

Đối với ứng dụng thực tế, cần giữ nhất quán key namespace và serializer, ghép kết quả theo ID thay vì bỏ qua vị trí thiếu, lựa chọn batch có kích thước hợp lý, và phân biệt atomicity của một lệnh với transaction nghiệp vụ. Trong Redis Cluster, thiết kế hash slot và hash tag phải phù hợp với những thao tác đa key cần thực hiện cùng nhau.
