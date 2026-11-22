# Thêm độ lệch TTL để tránh hết hạn đồng loạt

Trong chiến lược cache dùng Spring Data Redis, **TTL (time to live)** quy định một key được phép tồn tại bao lâu kể từ khi được ghi hoặc được gắn thời gian hết hạn. TTL giúp loại bỏ dữ liệu đã cũ và giới hạn dung lượng cache. Nhưng nếu ứng dụng ghi hàng chục nghìn key trong một đợt và gắn **cùng một TTL cố định**, chúng cũng có thể hết hạn gần như đồng thời. Khi đó nhiều request cùng chuyển từ cache hit sang cache miss, buộc hệ thống đọc lại dữ liệu từ database hoặc dịch vụ nguồn.

Một cách giảm rủi ro là thêm **độ lệch TTL (TTL jitter)**: mỗi lần ghi cache sẽ chọn một TTL hơi khác nhau quanh mức chuẩn, hoặc trong một khoảng được quy định. Nhờ các mốc hết hạn trải ra theo thời gian, tải tái tạo cache có cơ hội phân tán thay vì tập trung trong một đỉnh ngắn.

Bài học tập trung vào cách thiết kế khoảng jitter, áp dụng với `RedisTemplate` và Spring Cache dùng `RedisCacheManager`, kiểm thử TTL thực tế, cùng những giới hạn của biện pháp này khi cache có dữ liệu nóng hoặc yêu cầu độ mới nghiêm ngặt.

## 1. Vấn đề: nhiều key cùng hết hạn gây tải đột biến

Giả sử một dịch vụ hiển thị 60.000 sản phẩm. Khi triển khai phiên bản mới hoặc chạy tác vụ làm nóng cache, ứng dụng ghi gần như tất cả key vào Redis trong một phút. Mỗi key được đặt TTL đúng 10 phút:

~~~java
redis.opsForValue().set(
    "product:101",
    serializedProduct,
    Duration.ofMinutes(10)
);
~~~

Đến khoảng 10 phút sau, rất nhiều key đạt mốc hết hạn trong cùng khoảng thời gian ngắn. Những request đầu tiên sau khi key hết hạn phải tải lại sản phẩm từ nguồn dữ liệu.

~~~text
Không có jitter:

Thời gian        10:00        10:05        10:10        10:15
                  |            |            |            |
Ghi cache        ██████████
Cache còn sống   ────────────────────────────
Hết hạn                                      ██████████
Cache miss                                    ▲▲▲▲▲▲▲▲
Tải database                                  █████████

Có jitter:

Thời gian        10:00        10:05        10:09  10:10  10:11
                  |            |            |      |      |
Ghi cache        ██████████
Hết hạn                                  ░░▒▒▓▓▒▒░░░░░░
Cache miss                                ↑ ↑ ↑ ↑ ↑ ↑ ↑
Tải database                              ▒ ▒ ▒ ▒ ▒ ▒
~~~

Hình minh họa chỉ mô tả xu hướng. Redis không bảo đảm số key hết hạn phân bố đều tuyệt đối, và lượng cache miss thực tế còn phụ thuộc lưu lượng truy cập từng key.

Hiện tượng nhiều key hết hạn gần nhau thường được gọi là **cache avalanche**. Cần phân biệt nó với một vài vấn đề liên quan:

| Hiện tượng | Điều xảy ra | TTL jitter hỗ trợ đến đâu? |
| --- | --- | --- |
| **Cache avalanche** | Nhiều key hết hạn gần nhau, gây tải nguồn dữ liệu | Có thể phân tán thời điểm hết hạn của các key |
| **Cache stampede / thundering herd** | Nhiều request đồng thời cùng tái tạo **một key** vừa miss | Không giải quyết triệt để; vẫn cần single-flight, locking hoặc cách bảo vệ nguồn |
| **Cache penetration** | Request liên tục truy vấn key không tồn tại, không được cache | Không giải quyết; cân nhắc negative caching, validation, rate limit |
| **Cache cold start** | Cache trống sau triển khai, Redis mất dữ liệu hoặc chủ động xóa hàng loạt | Jitter chỉ phát huy sau khi dữ liệu được ghi lại; cần warm-up hoặc giới hạn tái tải |
| **Cache eviction** | Redis xóa key vì thiếu bộ nhớ hoặc chính sách eviction | Jitter không thay thế sizing, memory policy và giám sát Redis |

Vì vậy, TTL jitter là **một lớp phòng vệ cho phân bố thời điểm hết hạn**, không phải giải pháp duy nhất cho mọi loại cache miss.

## 2. Jitter thay đổi TTL theo quy tắc nào?

Một TTL cố định có dạng:

~~~text
TTL = 10 phút cho mọi key
~~~

Với jitter đối xứng:

~~~text
baseTTL = 10 phút
jitter  = 1 phút

TTL thực tế mỗi lần ghi ∈ [9 phút, 11 phút]
~~~

Có thể biểu diễn:

\[
T_i = T_{\text{base}} + U(-J,+J)
\]

Trong đó:

- `T_base` là TTL chuẩn theo chính sách cache.
- `J` là biên độ lệch tối đa.
- `U(-J,+J)` là giá trị ngẫu nhiên lấy trong khoảng từ `-J` đến `+J`.
- `T_i` là TTL được áp dụng cho lần ghi thứ `i`.

Nếu 60.000 key được ghi gần như đồng thời, tất cả có TTL đúng 600 giây thì nhiều mốc hết hạn tụ lại quanh giây thứ 600. Nếu mỗi key chọn độc lập một TTL trong khoảng 540–660 giây, các mốc hết hạn có thể nằm trên khoảng 120 giây. Với giả định phân bố đều và có lưu lượng truy cập tương đối đồng đều, số key đạt mốc hết hạn trung bình trên một giây sẽ xấp xỉ:

\[
\frac{60\,000}{120} \approx 500\ \text{key/giây}.
\]

Đây là **ước lượng kỳ vọng**, không phải giới hạn cứng. Xác suất, lưu lượng theo key và thời điểm ghi thực tế có thể khiến một số giây vẫn có nhiều sự kiện hơn các giây khác. Ngoài ra, Redis không nhất thiết dọn key vật lý đúng tại mili giây TTL về 0; việc truy cập key đã quá hạn sẽ khiến Redis xử lý trạng thái hết hạn của key đó.

### Jitter đối xứng, chỉ cộng thêm hay chỉ giảm TTL?

Có ba kiểu chính:

| Chính sách | Công thức | Khi nào phù hợp | Đánh đổi |
| --- | --- | --- | --- |
| Đối xứng | `base ± jitter` | Muốn phân tán quanh TTL chuẩn | Có key hết hạn sớm và có key tồn tại lâu hơn TTL chuẩn |
| Chỉ cộng | `base + random(0, J)` | TTL chuẩn là thời gian sống **tối thiểu**, chấp nhận giữ dữ liệu lâu hơn | Dữ liệu có thể cũ hơn mức TTL ban đầu |
| Chỉ giảm | `base - random(0, J)` | TTL chuẩn là **giới hạn tối đa** về độ cũ | Một phần key phải làm mới sớm hơn và tăng số lần nạp trung bình |

Không nên chọn kiểu jitter chỉ vì một công thức dễ viết. Hãy xác định ý nghĩa nghiệp vụ của `baseTTL`:

- Nếu dữ liệu **không được cũ quá 10 phút**, không dùng chính sách có thể kéo TTL lên 11 phút. Chọn chỉ giảm hoặc dùng một giới hạn cứng.
- Nếu dữ liệu có thể cũ tối đa 12 phút nhưng muốn refresh quanh phút thứ 10, jitter đối xứng ±1 phút có thể phù hợp.
- Nếu TTL gắn với phiên đăng nhập, token hoặc quyền truy cập, **hạn hết hiệu lực nghiệp vụ** phải là ranh giới tuyệt đối. Không được kéo dài TTL vượt thời điểm này vì mục tiêu chống avalanche.

## 3. Nguyên tắc chọn biên độ jitter

Độ lệch phải đủ lớn để rải các mốc hết hạn nhưng không làm mất ý nghĩa độ mới của dữ liệu.

Ví dụ chính sách:

~~~yaml
cache:
  product:
    base-ttl: 10m
    max-jitter: 1m
~~~

Đây là cấu hình minh họa của ứng dụng, **không phải property Spring Boot tự hiểu**. Nếu dùng, ứng dụng phải đọc và áp dụng các tham số này qua `@ConfigurationProperties` hoặc cách cấu hình riêng.

Một số câu hỏi cần quyết định:

1. **Mức độ mới tối đa cho phép là bao nhiêu?** Nếu hợp đồng dữ liệu yêu cầu luôn mới trong 10 phút, TTL thực tế không được vượt 10 phút.
2. **Khoảng thời gian tái tải tối thiểu có thể chịu được là bao lâu?** Jitter quá rộng có thể khiến nhiều key hết hạn quá sớm và làm tăng tần suất đọc nguồn.
3. **Có tính mùa vụ hoặc đợt làm nóng cache tập trung không?** TTL jitter đặc biệt hữu ích nếu các lần ghi tập trung trong những mốc thời gian gần nhau.
4. **Lưu lượng giữa các key có lệch lớn không?** Một key cực nóng cần cơ chế giảm stampede riêng ngay cả khi TTL của các key khác đã được rải.
5. **Cache được refresh mỗi lần đọc hay chỉ lúc ghi?** Nếu dùng time-to-idle (TTI) hoặc tự gia hạn TTL liên tục, quy tắc phân tán hết hạn cần tính cả hành vi đó.

Không có tỷ lệ phần trăm đúng cho mọi ứng dụng. Có thể bắt đầu thử nghiệm ở mức lệch khoảng 5–15% TTL chuẩn cho cache không quá nhạy về độ mới, rồi điều chỉnh bằng số liệu thực. Đây là **gợi ý để benchmark**, không phải giá trị mặc định được Spring Data Redis bảo đảm.

## 4. Xây dựng một chính sách TTL jitter tái sử dụng

Ta tạo một lớp Java chỉ có nhiệm vụ sinh TTL hợp lệ trong khoảng giới hạn. Mỗi lần gọi `nextTtl()` sẽ chọn một độ lệch mới. Đoạn mã dùng Java 21, `Duration` và `ThreadLocalRandom`:

~~~java
package com.example.redis.cache;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;

public final class TtlJitterPolicy {

    private final long baseMillis;
    private final long maxDeviationMillis;

    public TtlJitterPolicy(Duration base, Duration maxDeviation) {
        Objects.requireNonNull(base, "base");
        Objects.requireNonNull(maxDeviation, "maxDeviation");

        long baseMs = base.toMillis();
        long deviationMs = maxDeviation.toMillis();

        if (baseMs <= 0) {
            throw new IllegalArgumentException(
                "Base TTL must be at least one millisecond"
            );
        }
        if (deviationMs < 0 || deviationMs >= baseMs) {
            throw new IllegalArgumentException(
                "Jitter must be non-negative and smaller than base TTL"
            );
        }

        // Tránh overflow khi tính giới hạn TTL lớn nhất.
        Math.addExact(baseMs, deviationMs);
        this.baseMillis = baseMs;
        this.maxDeviationMillis = deviationMs;
    }

    public Duration nextTtl() {
        if (maxDeviationMillis == 0) {
            return Duration.ofMillis(baseMillis);
        }

        // nextLong(origin, bound) loại trừ bound.
        // +1L giúp hai đầu khoảng -J và +J đều có thể được chọn.
        long offsetMillis = ThreadLocalRandom.current().nextLong(
            -maxDeviationMillis,
            maxDeviationMillis + 1L
        );

        return Duration.ofMillis(baseMillis + offsetMillis);
    }
}
~~~

Sử dụng:

~~~java
TtlJitterPolicy policy = new TtlJitterPolicy(
    Duration.ofMinutes(10),
    Duration.ofMinutes(1)
);

Duration ttl1 = policy.nextTtl();
Duration ttl2 = policy.nextTtl();
Duration ttl3 = policy.nextTtl();

// Mỗi giá trị nằm trong [9 phút, 11 phút].
// Chúng có thể trùng nhau do bản chất của lựa chọn ngẫu nhiên.
~~~

Các kiểm tra trong constructor giúp tránh TTL âm/0 và overflow với những khoảng `Duration` được biểu diễn bằng mili giây. Ví dụ này chọn đơn vị mili giây nên không phù hợp nếu ứng dụng cần độ chính xác dưới một mili giây; thời hạn vài phút như ở đây không gặp hạn chế đó.

`ThreadLocalRandom` phù hợp với nhiều thread ghi cache đồng thời mà không cần khóa một bộ sinh số ngẫu nhiên chung. Nó không phải bộ sinh số ngẫu nhiên dành cho mục đích mật mã; TTL jitter không cần tính chất bảo mật của mã token.

### Vì sao không sinh một giá trị duy nhất lúc tạo bean?

Đoạn mã sau nhìn có vẻ dùng jitter nhưng **không phân tán TTL giữa các key**:

~~~java
Duration oneTimeTtl = policy.nextTtl();

// Sai mục tiêu nếu dùng oneTimeTtl cho tất cả các key:
for (String key : keys) {
    redis.opsForValue().set(key, "value", oneTimeTtl);
}
~~~

Một giá trị ngẫu nhiên được chọn một lần rồi dùng lại cho mọi key chỉ dời mốc hết hạn đồng loạt đi sớm hoặc muộn. **Phải tính TTL ở mỗi lần ghi** (hoặc ít nhất mỗi key theo chính sách thiết kế), đặc biệt trong các đợt làm nóng cache hàng loạt.

## 5. Áp dụng trực tiếp với `StringRedisTemplate`

Với Spring Data Redis, phương thức `opsForValue().set(key, value, Duration)` thiết lập giá trị và thời hạn trong cùng thao tác Redis. Đây là lựa chọn phù hợp khi ứng dụng tự quản lý cache bằng `RedisTemplate`.

Ví dụ một cache lưu chuỗi JSON đã được serialize bởi lớp nghiệp vụ:

~~~java
package com.example.redis.cache;

import java.time.Duration;
import java.util.Objects;
import java.util.function.Supplier;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSummaryCache {

    private final StringRedisTemplate redis;
    private final TtlJitterPolicy ttlPolicy = new TtlJitterPolicy(
        Duration.ofMinutes(10),
        Duration.ofMinutes(1)
    );

    public ProductSummaryCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String productId, String summaryJson) {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(summaryJson);

        String key = "cache:product-summary:" + productId;
        Duration ttl = ttlPolicy.nextTtl(); // Lấy một TTL mới cho key.

        // Redis ghi giá trị và TTL trong một thao tác.
        redis.opsForValue().set(key, summaryJson, ttl);
    }

    public String getOrLoad(
            String productId,
            Supplier<String> loadJsonFromSource) {
        String key = "cache:product-summary:" + productId;

        String hit = redis.opsForValue().get(key);
        if (hit != null) {
            return hit;
        }

        // Cache miss: lấy dữ liệu từ nguồn.
        String loaded = Objects.requireNonNull(loadJsonFromSource.get());
        redis.opsForValue().set(key, loaded, ttlPolicy.nextTtl());
        return loaded;
    }
}
~~~

Đối với một cache thông thường, quy trình là:

~~~text
Request tìm product
         |
         v
   GET cache key
    /         \
   hit        miss
    |          |
    v          v
 Trả giá trị   Đọc database/service
               |
               v
          Tính TTL mới
               |
               v
         SET key value PX/EX TTL
               |
               v
            Trả giá trị
~~~

Ví dụ `getOrLoad` nhằm minh họa **vị trí áp dụng TTL jitter**. Nó chưa ngăn nhiều request cùng miss một key rồi đồng thời gọi `loadJsonFromSource.get()`. Nếu sản phẩm đó rất nóng, cần bổ sung cơ chế chống cache stampede ở phần sau.

### Đặt TTL cùng lúc với dữ liệu

Không nên tách hai lệnh:

~~~java
redis.opsForValue().set(key, value);
redis.expire(key, ttlPolicy.nextTtl());
~~~

Giữa `SET` và `EXPIRE`, nếu tiến trình chết hoặc mạng gặp lỗi, key có thể tồn tại mà không có TTL mong muốn. Khi API hỗ trợ, dùng trực tiếp:

~~~java
redis.opsForValue().set(key, value, ttlPolicy.nextTtl());
~~~

Lệnh `SET` của Redis hỗ trợ expiration trong chính lệnh ghi; Spring Data Redis gửi thao tác phù hợp với thời lượng. Đây là hành vi **nguyên tử đối với thao tác ghi giá trị kèm thời hạn của một key**. Nó không làm toàn bộ quá trình tải dữ liệu từ database và ghi cache trở thành giao dịch.

## 6. Áp dụng với Spring Cache và `RedisCacheManager`

Nhiều ứng dụng Spring Boot sử dụng `@Cacheable`, `@CachePut` và `@CacheEvict` thay vì gọi `RedisTemplate` trực tiếp:

~~~java
@Cacheable(cacheNames = "productSummaries", key = "#productId")
public String loadSummary(String productId) {
    return productService.fetchSummaryJson(productId);
}
~~~

Khi dùng Redis làm backend, Spring Cache thường đi qua `RedisCacheManager`. Cấu hình TTL tĩnh cho một cache là cách đơn giản, nhưng nếu mọi entry được ghi cùng lúc thì các entry này vẫn có thể hết hạn gần nhau.

Đối với **Spring Data Redis 3.2 trở lên**, `RedisCacheConfiguration` có thể nhận một **TTL function** qua `entryTtl(...)` để quyết định thời hạn cho từng cache entry. Ta có thể tạo policy như sau:

~~~java
package com.example.redis.cache;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class RedisCacheJitterConfiguration {

    @Bean
    TtlJitterPolicy ttlJitterPolicy() {
        return new TtlJitterPolicy(
            Duration.ofMinutes(10),
            Duration.ofMinutes(1)
        );
    }

    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory factory,
            TtlJitterPolicy policy) {

        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .disableCachingNullValues()
                .entryTtl((key, value) -> policy.nextTtl());

        return RedisCacheManager.builder(factory)
            .cacheDefaults(defaults)
            .build();
    }
}
~~~

Hàm `(key, value) -> policy.nextTtl()` được đánh giá khi cache entry được ghi. Nó làm cho các lần ghi entry có khả năng nhận TTL khác nhau, kể cả khi các entry được tạo bởi cùng một phương thức `@Cacheable`.

**Hai cách cấu hình sau không tương đương:**

~~~java
// TTL cố định: policy được gọi một lần khi tạo cấu hình.
RedisCacheConfiguration.defaultCacheConfig()
    .entryTtl(policy.nextTtl());

// TTL động: policy được gọi cho từng lần ghi cache.
RedisCacheConfiguration.defaultCacheConfig()
    .entryTtl((key, value) -> policy.nextTtl());
~~~

Khi triển khai thực tế:

- Xác nhận phiên bản Spring Data Redis đang dùng hỗ trợ TTL function. Với phiên bản cũ, cân nhắc `RedisTemplate` hoặc một cơ chế ghi cache tùy biến được kiểm chứng.
- Bean `RedisCacheManager` tự định nghĩa sẽ ảnh hưởng cấu hình auto-configuration của Spring Boot. Cần kết hợp lại serializer, key prefix, null caching, transaction awareness và các thiết lập đã được dự án sử dụng.
- Cấu hình ở ví dụ áp dụng cùng policy cho **mọi cache** quản lý bởi manager đó. Hệ thống có cache sản phẩm, cache quyền truy cập và cache cấu hình nên dùng các TTL policy phù hợp với từng loại, không sao chép một policy chung bất chấp nghiệp vụ.
- Với dữ liệu không phải `String`, xác định serializer và tương thích giữa các phiên bản ứng dụng để đọc lại cache đúng kiểu.

### Chỉ áp dụng jitter cho một số vùng cache

Ví dụ `productSummaries` có thể chịu độ cũ 9–11 phút, còn `featureFlags` phải cập nhật nhanh hơn. Thay vì áp dụng một policy chung, có thể khai báo cấu hình riêng cho các cache name:

~~~java
TtlJitterPolicy productPolicy = new TtlJitterPolicy(
    Duration.ofMinutes(10), Duration.ofMinutes(1)
);

RedisCacheConfiguration productConfig =
    RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl((key, value) -> productPolicy.nextTtl());

RedisCacheConfiguration featureConfig =
    RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl(Duration.ofSeconds(30));

RedisCacheManager manager = RedisCacheManager.builder(factory)
    .withInitialCacheConfigurations(java.util.Map.of(
        "productSummaries", productConfig,
        "featureFlags", featureConfig
    ))
    .build();
~~~

Đoạn này minh họa API xây dựng manager; khi đưa vào `@Configuration`, cấu hình cần kết hợp vào bean manager thực tế thay cho việc đồng thời tạo nhiều bean `RedisCacheManager` không có mục đích.

Spring Cache không cung cấp một annotation chuẩn kiểu `@Cacheable(ttl = random)` cho từng lời gọi. Chính **cấu hình cache manager/writer** là nơi quyết định TTL của entry trong ví dụ trên.

## 7. Repository và `@TimeToLive`: trường hợp dùng entity làm cache

Một số hệ thống dùng **Spring Data Redis Repository** với `@RedisHash` cho dữ liệu có vòng đời ngắn. Trong trường hợp đó, TTL được gắn với thực thể có thể biểu diễn bằng `@TimeToLive`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("temporary-products")
public class TemporaryProduct {

    @Id
    private String id;

    private String name;

    @TimeToLive
    private Long ttlSeconds;

    public TemporaryProduct() {
    }

    public TemporaryProduct(String id, String name, long ttlSeconds) {
        this.id = id;
        this.name = name;
        this.ttlSeconds = ttlSeconds;
    }
}
~~~

Khi tạo mới entity, ứng dụng có thể gán `ttlSeconds` theo một chính sách độ lệch tính bằng giây rồi lưu qua repository:

~~~java
long seconds = 600
    + java.util.concurrent.ThreadLocalRandom.current()
        .nextLong(-60, 61); // 540..660 giây

repository.save(new TemporaryProduct(
    "p-101", "Redis Guide", seconds
));
~~~

Trong mô hình repository, `@TimeToLive` đánh dấu một property chứa TTL của thực thể. Nó khác với `@Indexed` (chỉ mục phụ) và khác `@Transient` (loại bỏ thuộc tính khỏi ánh xạ). Khi repository đọc lại entity, property TTL có thể phản ánh **thời gian sống còn lại** của key, tùy cấu hình mapping và thời điểm đọc.

Nếu ứng dụng đã có TTL cố định ở `@RedisHash(timeToLive = ...)`, cần thiết kế rõ nguồn nào quyết định TTL cuối cùng; không gắn nhiều cơ chế TTL mà không hiểu thứ tự ưu tiên. Với cache thông thường theo `@Cacheable`, hãy áp dụng jitter ở `RedisCacheManager` thay vì thêm `@TimeToLive` vào DTO không được Redis Repository quản lý.

## 8. Không vi phạm hạn sử dụng nghiệp vụ

TTL jitter không được kéo dài dữ liệu vượt ranh giới an toàn. Ví dụ một voucher chỉ có hiệu lực đến 18:00; ở 17:55, ứng dụng không được gắn TTL 10–11 phút rồi tiếp tục coi voucher là hợp lệ sau 18:00.

Hãy xác định hai giới hạn:

1. **TTL cache theo hiệu năng**, có jitter.
2. **Thời gian còn hiệu lực thực tế của dữ liệu**, tính từ thời điểm hiện tại đến deadline.

TTL cuối cùng phải không vượt quá giới hạn nghiệp vụ:

\[
TTL_{\text{effective}}
= \min\left(TTL_{\text{jitter}},\
T_{\text{deadline}}-T_{\text{now}}\right)
\]

Nếu thời gian còn lại không dương, bỏ qua ghi cache hoặc xử lý trạng thái hết hạn theo nghiệp vụ.

Ví dụ:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public Duration boundedTtl(
        TtlJitterPolicy policy,
        Instant validUntil,
        Clock clock) {

    Duration remaining =
        Duration.between(clock.instant(), validUntil);

    if (remaining.isZero() || remaining.isNegative()) {
        return Duration.ZERO; // Caller phải bỏ qua ghi cache.
    }

    Duration candidate = policy.nextTtl();
    return candidate.compareTo(remaining) <= 0
        ? candidate
        : remaining;
}
~~~

Sử dụng:

~~~java
Duration ttl = boundedTtl(policy, voucherValidUntil, clock);
if (ttl.compareTo(Duration.ZERO) > 0) {
    redis.opsForValue().set(key, voucherJson, ttl);
}
~~~

`Clock` giúp kiểm thử phép tính deadline mà không phụ thuộc thời gian thực. Tuy nhiên, thay đổi `Clock` trong Java không làm đồng hồ của Redis tiến nhanh hơn; kiểm thử hết hạn thực sự vẫn cần Redis và thời gian thực hoặc một lớp trừu tượng phù hợp.

### Độ mới tuyệt đối và TTL được gia hạn

Ngay cả khi có jitter, nếu mỗi cache hit đều kéo dài thời gian hết hạn, dữ liệu có thể tồn tại rất lâu sau thời điểm được lấy từ nguồn ban đầu. Đây là sự khác biệt giữa:

- **TTL tính từ lần ghi**: key hết hạn sau khoảng thời gian đã chọn khi được tạo/cập nhật.
- **Time-to-idle (TTI)**: một lần truy cập có thể làm mới thời hạn nếu cơ chế cache hỗ trợ và được bật.
- **Độ mới tối đa theo timestamp nguồn**: dữ liệu phải được lấy mới hoàn toàn sau một khoảng cứng, bất kể số lần đọc.

Nếu có yêu cầu “không quá 10 phút kể từ lúc xác thực với nguồn”, cần lưu và kiểm tra mốc thời gian nguồn hoặc một deadline cứng; chỉ dựa vào TTL có thể không đủ nếu hệ thống gia hạn key khi đọc.

## 9. Jitter có thực sự ngăn cache stampede không?

Giả sử một sản phẩm rất phổ biến nhận 2.000 request/giây và chỉ tồn tại trong **một key Redis**. Khi key đó hết hạn, hàng trăm request có thể đồng thời thấy miss trước khi request đầu tiên nạp lại xong.

TTL jitter chỉ thay đổi **khi nào** key hết hạn, không thay đổi việc **bao nhiêu request cùng tái tạo** key đó sau khi miss.

~~~text
                    Key hot hết hạn
                          |
            +-------------+-------------+
            |             |             |
           Req A         Req B         Req C ... Req N
            |             |             |
          GET miss      GET miss      GET miss
            |             |             |
          DB query      DB query      DB query
            |             |             |
           SET           SET           SET
~~~

Với một key nóng, có thể kết hợp TTL jitter với:

| Biện pháp | Mục đích | Lưu ý |
| --- | --- | --- |
| **Single-flight trong JVM** | Nhiều request cùng process dùng chung một lượt tải cho một key | Chỉ bảo vệ trong một instance |
| **Distributed lock** | Chỉ một instance được quyền tái tạo key ở một thời điểm | Cần lock timeout, ownership và xử lý lỗi đúng |
| **Stale-while-revalidate** | Trả dữ liệu cũ trong ngắn hạn, cập nhật ở nền | Chỉ dùng khi nghiệp vụ chấp nhận stale |
| **Refresh-ahead** | Tái tạo key trước mốc hết hạn | Cần giới hạn số job refresh và tránh đồng loạt |
| **Rate limit / backpressure** | Bảo vệ database hoặc upstream khi miss tăng | Phải có hành vi fallback rõ ràng |
| **Cache warming có giới hạn tốc độ** | Nạp dần dữ liệu quan trọng trước khi nhận tải cao | Không được khiến upstream quá tải khi warm-up |

Một hệ thống có nhiều key cùng hết hạn và một vài key cực nóng thường cần **cả phân bố TTL lẫn bảo vệ tái tải một key**.

## 10. Cẩn thận với cách chọn giá trị ngẫu nhiên

### Tính jitter ở mỗi lần ghi, tránh gom theo toàn bộ batch

Khi viết batch 1.000 key:

~~~java
for (CacheEntry entry : entries) {
    Duration ttl = policy.nextTtl();
    redis.opsForValue().set(entry.key(), entry.value(), ttl);
}
~~~

Mỗi iteration chọn một TTL độc lập. Nếu thay bằng cách tính `ttl = policy.nextTtl()` bên ngoài vòng lặp, cả batch lại có cùng TTL.

Với pipeline, ý tưởng vẫn là chọn TTL cho từng lệnh:

~~~java
redis.executePipelined(
    (org.springframework.data.redis.core.SessionCallback<Object>) ops -> {
        for (CacheEntry entry : entries) {
            ops.opsForValue().set(
                entry.key(),
                entry.value(),
                policy.nextTtl()
            );
        }
        return null;
    }
);
~~~

`CacheEntry` trong ví dụ là kiểu dữ liệu chứa hai property `key` và `value`, ví dụ Java record:

~~~java
public record CacheEntry(String key, String value) {
}
~~~

Pipeline giảm round-trip mạng, nhưng không biến toàn batch thành transaction. Nếu muốn hạn chế bộ nhớ phản hồi và độ trễ khi ghi rất nhiều key, nên chia pipeline thành các batch có giới hạn thay vì gom vô hạn.

### Không rải TTL theo request đọc

Nếu không có dữ liệu mới, chỉ vì request vừa đọc một key mà gán TTL khác liên tục có thể làm kéo dài vòng đời cache vô tình. TTL jitter nên được áp dụng theo **sự kiện ghi hoặc refresh thực sự**, phù hợp với chính sách freshness của cache.

### Có cần ngẫu nhiên “công bằng” tuyệt đối?

Không. Mục tiêu là giảm tương quan thời điểm hết hạn giữa các key. Một phân bố đơn giản, độc lập, có giới hạn thường đủ để bắt đầu. Nếu hệ thống có yêu cầu rất lớn và có nhiều batch đồng thời, có thể đánh giá phân bố theo metric thay vì đưa ra giả định rằng random luôn tạo phân bố hoàn hảo.

Đôi khi cần **jitter ổn định theo key** (ví dụ hash của key để chia bucket deterministic), giúp cùng một key luôn có offset cố định qua nhiều lần ghi. Điều này có thể thuận tiện trong một số hệ thống nhưng cũng có nguy cơ tạo nhóm key có cùng offset khi thiết kế bucket quá thô. Chỉ nên chọn deterministic jitter khi cần khả năng tái lập hoặc phân vùng mốc hết hạn; ngẫu nhiên theo mỗi lần ghi thường đơn giản hơn cho cache phổ thông.

## 11. Kiểm thử chính sách TTL mà không phụ thuộc sleep chính xác

Kiểm thử cần tách hai mục tiêu:

1. **Unit test của policy**: xác nhận TTL được sinh trong giới hạn dương và đúng khoảng.
2. **Integration test Redis**: xác nhận TTL thực sự được gắn với key khi ghi cache.

Không nên tạo key TTL 10 phút rồi bắt test đợi đủ 10 phút để kiểm chứng. Test chỉ cần đọc thời gian sống còn lại ngay sau ghi; một bài test riêng về khả năng hết hạn thực sự có thể dùng TTL ngắn và polling với timeout.

### 11.1. Unit test phạm vi TTL

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class TtlJitterPolicyTest {

    @Test
    void returnsPositiveTtlWithinConfiguredRange() {
        TtlJitterPolicy policy = new TtlJitterPolicy(
            Duration.ofMinutes(10),
            Duration.ofMinutes(1)
        );

        for (int i = 0; i < 1000; i++) {
            Duration ttl = policy.nextTtl();
            assertThat(ttl)
                .isBetween(Duration.ofMinutes(9), Duration.ofMinutes(11));
        }
    }

    @Test
    void rejectsJitterThatCanProduceNonPositiveTtl() {
        assertThatThrownBy(() -> new TtlJitterPolicy(
            Duration.ofSeconds(30),
            Duration.ofSeconds(30)
        )).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void zeroJitterKeepsBaseTtl() {
        TtlJitterPolicy policy = new TtlJitterPolicy(
            Duration.ofMinutes(10), Duration.ZERO
        );

        assertThat(policy.nextTtl()).isEqualTo(Duration.ofMinutes(10));
    }
}
~~~

Đoạn test kiểm tra **giới hạn đúng với mọi lần lấy mẫu**; không giả định rằng cứ chọn 1.000 lần thì chắc chắn sẽ xuất hiện đúng giá trị min, max hoặc 1.000 giá trị phân biệt. Những assertion dựa trên kết quả ngẫu nhiên chính xác có thể tạo flaky test.

### 11.2. Integration test với Redis thực

Ví dụ dưới dùng Spring Boot, JUnit 5, Spring Data Redis và Testcontainers. Test tạo key riêng, gắn TTL ngẫu nhiên và đọc lại TTL bằng độ phân giải mili giây.

Với Gradle Groovy và phiên bản dependency do Spring Boot quản lý:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

~~~java
package com.example.redis.cache;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(classes = TtlJitterRedisIntegrationTest.TestApp.class)
class TtlJitterRedisIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    StringRedisTemplate redis;

    @Test
    void writesValueWithBoundedRandomTtl() {
        String key = "test:ttl-jitter:" + UUID.randomUUID();
        TtlJitterPolicy policy = new TtlJitterPolicy(
            Duration.ofMinutes(10), Duration.ofMinutes(1)
        );

        try {
            redis.opsForValue().set(key, "cached", policy.nextTtl());

            assertThat(redis.opsForValue().get(key)).isEqualTo("cached");

            Long remaining = redis.getExpire(
                key, TimeUnit.MILLISECONDS
            );

            // Cho phép độ trễ giữa SET và PTTL trên máy CI.
            // Vẫn đủ rộng để phân biệt TTL sai hoặc thiếu TTL.
            assertThat(remaining)
                .isNotNull()
                .isGreaterThan(Duration.ofMinutes(8).toMillis())
                .isLessThanOrEqualTo(Duration.ofMinutes(11).toMillis());
        } finally {
            redis.delete(key);
        }
    }
}
~~~

Với Redis, `PTTL` (và `getExpire(key, TimeUnit.MILLISECONDS)`) trả giá trị `-1` nếu key tồn tại nhưng không có expiration, `-2` nếu key không tồn tại. Vì vậy, một assertion TTL dương giúp phát hiện trường hợp ghi quên gắn hạn sử dụng. Không khẳng định TTL còn lại bằng **chính xác** thời lượng vừa tạo, vì thời gian đã trôi đi giữa hai lệnh.

### 11.3. Kiểm thử riêng hành vi hết hạn

Nếu mục tiêu là xác nhận key sẽ biến mất sau khi hết hạn, dùng TTL ngắn hơn và polling có timeout:

~~~java
redis.opsForValue().set(
    key, "short-lived", Duration.ofMillis(1200)
);

org.awaitility.Awaitility.await()
    .atMost(Duration.ofSeconds(8))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertThat(redis.opsForValue().get(key)).isNull()
    );
~~~

Đoạn minh họa cần dependency test `org.awaitility:awaitility` nếu dự án chưa có sẵn. Polling kết thúc ngay khi điều kiện đạt, thay vì `Thread.sleep(...)` một khoảng cố định rồi suy diễn trạng thái từ đúng một lần đọc.

**Kiểm thử policy jitter không cần chạy benchmark trong cùng JUnit test.** Benchmark đo hiệu quả phân bố tải phải thực hiện riêng với workload đại diện và metrics server/database thực tế.

## 12. Giám sát hiệu quả của TTL jitter

Để biết jitter có làm giảm tải đột biến hay không, cần đo một vài chỉ số trước và sau khi thay đổi. Một histogram TTL cấu hình đẹp không tự chứng minh database đã bớt chịu tải.

| Chỉ số | Ý nghĩa cần quan sát |
| --- | --- |
| Cache hit rate / miss rate theo thời gian | Có còn spike miss đồng loạt sau mỗi đợt ghi không? |
| Số key hết hạn theo khoảng thời gian | Mốc hết hạn đã được phân tán hơn chưa? |
| QPS database/upstream | Có giảm đỉnh tải ở thời điểm cache miss không? |
| p95/p99 latency của API | Người dùng có còn gặp đợt phản hồi chậm gần mốc hết hạn không? |
| Số lần rebuild cùng một key | Có cache stampede cho hot key cần giải pháp riêng không? |
| Redis memory, evictions và CPU | Tăng biên độ TTL có khiến nhiều key sống lâu hơn và gây áp lực bộ nhớ không? |
| TTL thực tế tại thời điểm ghi | Logic random có thực sự áp dụng cho từng entry hay chỉ chọn một lần? |

Redis có các thông tin chẩn đoán như `INFO stats` với `expired_keys`, `keyspace_hits` và `keyspace_misses`. Những bộ đếm này là **cumulative counters**; cần lấy hiệu giữa các lần quan sát để suy ra tốc độ theo khoảng thời gian. Đồng thời, `expired_keys` phản ánh hoạt động expiration của Redis, không phải log đầy đủ thời điểm mọi key về TTL 0 với độ phân giải tuyệt đối.

Tại tầng ứng dụng, có thể ghi metric histogram cho TTL được chọn và bộ đếm cache miss/refill:

~~~java
Duration ttl = policy.nextTtl();

// Ví dụ tên metric; cách ghi phụ thuộc hệ thống quan sát.
// cache.ttl.assigned.seconds: phân bố thời gian sống đã gán
// cache.miss.count: số lần miss
// cache.refill.duration: thời gian tái tạo dữ liệu

redis.opsForValue().set(key, value, ttl);
~~~

Không đưa ID/key có cardinality cao thành một nhãn metric riêng cho mỗi key. Nên phân nhóm bằng cache name, loại dữ liệu hoặc chính sách TTL để tránh làm hệ thống giám sát quá tải.

### Đánh giá theo loại tải

Nên đo ít nhất hai kịch bản:

1. **Warm-up đồng loạt:** Ghi nhiều key trong một khoảng ngắn, sau đó phát request gần thời điểm các key hết hạn.
2. **Tải thực tế:** Key được tạo/cập nhật ở các thời điểm khác nhau, có cả hot key và cold key, với tỷ lệ cache hit/miss đại diện.

Nếu request tới key đã hết hạn rất thưa, phân tán TTL có thể ít tác động đến tải thực. Nếu hầu hết request dồn vào một hot key, jitter trên hàng nghìn cold key cũng không thay thế được single-flight cho hot key.

## 13. Những sai lầm thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Vẫn hết hạn đồng loạt dù có random | Lấy một TTL ngẫu nhiên lúc khởi tạo bean rồi dùng cho mọi key | Chọn TTL mới **mỗi lần ghi cache entry** |
| Cache lâu hơn yêu cầu nghiệp vụ | Jitter cộng dương vượt giới hạn độ mới | Dùng jitter chỉ giảm hoặc giới hạn theo deadline |
| Cache miss tăng dù chưa tới TTL chuẩn | Jitter đối xứng làm một số key hết hạn sớm | Đánh giá lại TTL tối thiểu và tải refill |
| Nhiều request vẫn đánh vào DB cùng lúc | Một hot key hết hạn và nhiều thread cùng cache miss | Thêm single-flight/lock/refresh-ahead |
| Không tìm thấy TTL trên key | Ghi `SET` không kèm expiration, hoặc ghi đè key làm mất TTL | Dùng `opsForValue().set(key, value, Duration)` |
| `@Cacheable` vẫn có TTL cố định | Cache manager chỉ cấu hình `entryTtl(Duration)` | Dùng TTL function theo từng entry nếu phiên bản hỗ trợ |
| Bài kiểm thử thỉnh thoảng thất bại | So sánh PTTL bằng đúng TTL đã gán hoặc sleep sát ranh giới | Dùng khoảng dung sai và polling có timeout |
| Redis memory tăng sau khi thêm jitter | Nhiều key được giữ sống lâu hơn trước | Giảm TTL lớn nhất, chọn jitter chỉ giảm hoặc điều chỉnh capacity |
| Jitter không hữu ích sau `FLUSHALL`/mất cache | Cache đã trống ngay lập tức, chưa tới giai đoạn hết hạn | Thiết kế warm-up/giới hạn refill riêng |
| Mọi key được refresh khi đọc | Chính sách time-to-idle có thể làm thay đổi phân bố expiry | Xác định rõ TTL và TTI, giới hạn tuổi dữ liệu |
| Ghi hàng loạt làm database nghẽn ngay khi warm-up | Nguồn dữ liệu bị tải đồng loạt tại thời điểm nạp | Giới hạn concurrency, batch size và QPS warm-up |
| Retry ghi cache kéo dài TTL ngoài ý muốn | `SET` có expiration mới tạo lại deadline | Thiết kế lại semantics theo hạn cuối tuyệt đối nếu cần |

## 14. Cách áp dụng trong dự án thực tế

Một quy trình triển khai hợp lý có thể bắt đầu từ cache gây tải đột biến rõ nhất:

1. **Đo baseline:** ghi nhận thời điểm nạp cache, đỉnh cache miss, QPS database, p95/p99 API latency và Redis memory.
2. **Xác định hợp đồng độ mới:** TTL tối đa, TTL tối thiểu hợp lệ, sự khác nhau giữa dữ liệu nghiệp vụ và dữ liệu chỉ phục vụ hiển thị.
3. **Chọn phân bố và biên độ:** đối xứng, chỉ cộng hoặc chỉ giảm; bảo đảm TTL dương và không vượt deadline.
4. **Đặt policy tại đúng đường ghi:** `RedisTemplate`, RedisCacheManager TTL function hoặc property `@TimeToLive` của entity.
5. **Thêm giới hạn tái tải:** single-flight cho hot key và backpressure cho database khi xuất hiện cache miss.
6. **Kiểm thử:** unit test khoảng TTL, integration test PTTL, kiểm tra đường ghi hàng loạt tạo TTL riêng cho từng entry.
7. **Quan sát hiệu quả:** so sánh biểu đồ cache miss, p95/p99 và tải upstream trước/sau; hiệu chỉnh jitter dựa trên kết quả.

Ví dụ một bảng chính sách:

| Loại dữ liệu | TTL chuẩn | Độ lệch đề xuất để thử nghiệm | Ràng buộc |
| --- | --- | --- | --- |
| Danh mục sản phẩm ít thay đổi | 10 phút | ±1 phút | Cho phép dữ liệu sống tối đa 11 phút |
| Kết quả gợi ý không nhạy thời gian | 30 phút | 0–5 phút cộng thêm | Chấp nhận độ cũ tới 35 phút |
| Giá hàng hóa cần mới trong 5 phút | 5 phút | 0–30 giây giảm xuống | Không kéo dài quá 5 phút |
| Quyền truy cập/token | Theo thời hạn hiệu lực thực | Chỉ khi bị chặn bởi deadline | Không vượt hạn hiệu lực hoặc làm yếu yêu cầu bảo mật |
| Negative cache cho ID không tồn tại | 15 giây | 0–3 giây giảm | Phải kiểm soát khả năng dữ liệu xuất hiện mới |

Các thông số chỉ để minh họa cách xác định chính sách; hệ thống thật cần đánh giá đặc điểm cập nhật dữ liệu, yêu cầu độ mới và tải đọc.

## 15. Kết luận

Thêm độ lệch TTL là một kỹ thuật đơn giản nhưng hữu ích để **phân tán thời điểm hết hạn** của nhiều key trong Spring Data Redis. Thay vì áp dụng cùng TTL cho hàng loạt cache entry được ghi gần nhau, ứng dụng chọn một thời hạn độc lập, có giới hạn, cho mỗi lần ghi. Điều này có thể làm dịu những đỉnh cache miss và tải tái tạo dữ liệu khi nhiều key đến hạn đồng thời.

Để áp dụng đúng, hãy phân biệt TTL chuẩn với **giới hạn độ mới của nghiệp vụ**, chọn biên độ không tạo TTL không hợp lệ, tính lại jitter trên **mỗi entry**, và ghi giá trị cùng expiration trong một thao tác Redis. Trong Spring Cache, cần cấu hình TTL function ở RedisCacheManager nếu phiên bản hỗ trợ; với RedisTemplate có thể truyền Duration trực tiếp; với Redis Repository có thể điều khiển TTL trên entity.

Cuối cùng, jitter không tự ngăn nhiều request đồng thời tái tạo một hot key, không xử lý cold start và không thay thế kế hoạch capacity cho Redis/database. Kết hợp nó với giới hạn refill, single-flight khi cần, kiểm thử TTL ở Redis thật và quan sát hiệu năng theo dữ liệu vận hành sẽ giúp chiến lược cache ổn định hơn.
