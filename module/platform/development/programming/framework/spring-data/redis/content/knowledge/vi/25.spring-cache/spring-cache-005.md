# Điều kiện `condition`, `unless` và quyết định cache giá trị `null` trong Spring Data Redis

## 1. Vì sao cần điều kiện lưu cache?

Spring Cache giúp tách logic cache khỏi phần lớn mã nghiệp vụ bằng các annotation như `@Cacheable`, `@CachePut` và `@CacheEvict`. Khi Redis được chọn làm cache provider, Spring Data Redis cung cấp `RedisCacheManager` để đọc/ghi dữ liệu cache qua Redis.

Mặc định, với `@Cacheable`, Spring sẽ tìm một giá trị bằng cache name và key trước khi gọi phương thức. Nếu cache hit, phương thức có thể không được gọi. Nếu cache miss, phương thức chạy và kết quả được đưa vào cache theo chính sách.

Tuy nhiên, không phải mọi lời gọi hay mọi kết quả đều đáng cache:

- ID không hợp lệ, request chỉ để thử nghiệm hoặc đối tượng không nằm trong nhóm nên dùng cache.
- Kết quả trả về không tồn tại (`null` hoặc `Optional.empty()`).
- Kết quả có trạng thái tạm thời, nhạy cảm hoặc thay đổi quá nhanh.
- Một lỗi hệ thống bị tầng nghiệp vụ vô tình biểu diễn thành `null`, gây nguy cơ lưu trạng thái sai.
- Một lần tra cứu "không tìm thấy" có thể đáng cache trong thời gian ngắn để giảm tải dữ liệu gốc (**negative caching**), nhưng cũng có thể khiến ứng dụng không thấy bản ghi vừa được tạo.

Hai thuộc tính của annotation giúp kiểm soát việc này:

- **`condition`**: quyết định có áp dụng cơ chế cache cho lời gọi ngay từ đầu hay không.
- **`unless`**: quyết định có **từ chối ghi kết quả vào cache** sau khi phương thức đã chạy hay không.

Ngoài hai biểu thức trên còn có **chính sách Redis cache có lưu `null` hay không**, được cấu hình ở `RedisCacheConfiguration`, `RedisCacheManager` hoặc thuộc tính của Spring Boot. Ba yếu tố này liên quan nhau nhưng không có cùng trách nhiệm.

## 2. Luồng thực thi `@Cacheable`

Ví dụ:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public CustomerDto findCustomer(String id) {
    return customerRepository.findById(id)
            .map(CustomerDto::from)
            .orElse(null);
}
§§§

Ở đây `#p0` là tham số đầu tiên, tương ứng `id`. Luồng xử lý ở một lời gọi **đi qua Spring Cache interceptor**:

§§§mermaid
flowchart TD
    A["Gọi findCustomer(id) qua Spring proxy"] --> B{"condition đúng?"}
    B -->|Không| C["Bỏ qua cơ chế cache"]
    C --> D["Gọi phương thức và trả kết quả"]
    B -->|Có| E["Tạo key và tìm trong Redis cache"]
    E --> F{"Cache hit?"}
    F -->|Có| G["Trả giá trị trong cache, không gọi phương thức"]
    F -->|Không| H["Gọi phương thức"]
    H --> I["Có kết quả trả về thành công"]
    I --> J{"unless đúng?"}
    J -->|Có| K["Không ghi kết quả vào cache"]
    J -->|Không| L["Ghi kết quả theo chính sách RedisCache"]
    K --> M["Trả kết quả"]
    L --> M
§§§

Cần phân biệt:

1. `condition` chạy ở **giai đoạn trước khi gọi phương thức**; nó có thể dùng tham số, thông tin phương thức và target.
2. `unless` chạy ở **giai đoạn sau khi phương thức trả kết quả** trong trường hợp cần xét việc đưa kết quả vào cache; biểu thức có thể dùng `#result`.
3. Khi cache **hit** ở `@Cacheable`, phương thức không phải chạy để tạo lại kết quả, nên biểu thức `unless` **không được dùng để lọc lại một entry đã cache từ trước**.
4. Nếu phương thức ném exception thay vì trả kết quả bình thường, Spring Cache thông thường không cache exception đó như một giá trị hợp lệ.

Vì vậy, `unless` là một **cache put veto**: ngăn ghi kết quả mới, không phải cơ chế bảo đảm mọi giá trị đang tồn tại trong Redis đều thỏa điều kiện hiện tại.

## 3. Bắt đầu với Spring Boot, Redis và Spring Cache

Trong dự án Spring Boot dùng Redis làm cache backend:

§§§groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
§§§

Ví dụ cấu hình phát triển:

§§§yaml
spring:
  cache:
    type: redis
    cache-names: customerById,customerLookup
  data:
    redis:
      host: localhost
      port: 6379
§§§

Bật annotation caching:

§§§java
package com.example.demo;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CachingConfig {
}
§§§

Khi có Redis Cache auto-configuration phù hợp và không có một `CacheManager` khác được chọn, Spring Boot có thể tạo `RedisCacheManager`. Dự án có nhiều cache provider nên cấu hình rõ `spring.cache.type: redis` hoặc một `CacheManager` phù hợp.

Cần ghi nhớ ba lớp:

| Lớp | Trách nhiệm |
|---|---|
| Spring Cache abstraction | Định nghĩa `@Cacheable`, `condition`, `unless`, tạo key, gọi method |
| Spring Data Redis `RedisCacheManager` / `RedisCache` | Quản lý cache entry, TTL, serializer và chính sách `null` |
| Redis server | Lưu key/value đã serialize, quản lý expiration và khả năng phục hồi dữ liệu |

Bật `@EnableCaching` **không tự khiến mọi method được cache**. Method phải được gọi qua cơ chế interception thích hợp, và cache annotations phải nằm ở vị trí Spring có thể nhận diện.

## 4. `condition`: quyết định trước khi thực thi phương thức

### 4.1. `condition` diễn giải điều gì?

`condition` là biểu thức **Spring Expression Language (SpEL)** trả về giá trị boolean. Với `@Cacheable`, nếu biểu thức là `false`, Spring không tìm cache, không sử dụng một entry có sẵn và không ghi cache cho lời gọi đó; phương thức được thực thi bình thường.

Ví dụ chỉ cache khi ID có giá trị và không rỗng:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()"
)
public CustomerDto findCustomer(String id) {
    return loadCustomer(id);
}
§§§

Lời gọi `findCustomer("42")` có thể đi qua cache. Lời gọi `findCustomer(null)` hoặc `findCustomer("   ")` bỏ qua cache. Việc method có chấp nhận null hay không vẫn do quy tắc nghiệp vụ quyết định; `condition` không thay thế validation.

Ví dụ chỉ cache tra cứu theo địa chỉ email thuộc miền cho phép:

§§§java
@Cacheable(
    cacheNames = "customerByEmail",
    key = "#p0",
    condition = "#p0 != null && #p0.endsWith('@example.test')"
)
public CustomerDto findByEmail(String email) {
    return lookupByEmail(email);
}
§§§

Ở đây điều kiện bảo đảm các email ngoài miền đó không sử dụng cache. Nó **không kiểm soát quyền truy cập**: kiểm tra authorization phải được thực hiện độc lập trước khi trả dữ liệu, kể cả khi có cache hit.

### 4.2. Các biến SpEL dùng trước khi gọi method

Các biểu thức Spring Cache thường có thể tham chiếu:

| Biểu thức | Ý nghĩa |
|---|---|
| `#p0`, `#a0` | Tham số thứ nhất của method |
| `#p1`, `#a1` | Tham số thứ hai |
| `#root.args[0]` | Tham số thứ nhất qua root object |
| `#root.methodName` | Tên method được interceptor xét |
| `#root.target` | Đối tượng đang được gọi |
| `#root.targetClass` | Class của target |
| `#root.caches` | Danh sách cache được chọn theo operation |

Tên tham số trực tiếp như `#id` thuận tiện nhưng phụ thuộc khả năng Spring khám phá tên tham số, ví dụ bytecode được biên dịch với `-parameters`. Dùng `#p0` hoặc `#a0` giúp ví dụ không phụ thuộc vào metadata tên tham số.

**`#result` không khả dụng trong `condition` của `@Cacheable`** vì method chưa được gọi. Nếu quyết định chỉ dựa trên dữ liệu đầu vào thì chọn `condition`; nếu quyết định phụ thuộc kết quả trả về thì chọn `unless`.

### 4.3. `condition` không quyết định cache value nào được trả

Giả sử trong cache đã có giá trị dưới key `customerById::42`, nhưng lời gọi hiện tại có `condition=false` vì thêm một tham số điều khiển:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    condition = "#p1"
)
public CustomerDto findCustomer(String id, boolean useCache) {
    return loadCustomer(id);
}
§§§

Với `findCustomer("42", false)`, Spring bỏ qua việc đọc cache dù Redis đã có entry. `condition` là **cổng vào cơ chế cache**, không phải bộ lọc dữ liệu sau khi cache được đọc.

Nếu nhiều biến thể nghiệp vụ dùng cùng cache name, điều kiện và key phải được thiết kế nhất quán để không chia sẻ nhầm dữ liệu giữa tenant, ngôn ngữ, quyền truy cập hoặc biến thể response.

## 5. `unless`: từ chối ghi khi đã biết kết quả

### 5.1. Ví dụ không cache kết quả null

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    unless = "#result == null"
)
public CustomerDto findCustomer(String id) {
    return repository.findById(id)
            .map(CustomerDto::from)
            .orElse(null);
}
§§§

Nếu Repository không tìm thấy khách hàng, method trả `null`; biểu thức `unless` trả `true`, nên Spring **không ghi** kết quả đó vào Redis Cache.

Khi gọi lần sau với cùng ID:

- Vì không có cache entry được ghi trong lần trước, lần sau tiếp tục đi tới method.
- Nếu dữ liệu được tạo ở giữa hai lần gọi, lời gọi mới có cơ hội đọc thấy dữ liệu vừa tạo.
- Đổi lại, nhiều request cùng hỏi một ID không tồn tại sẽ tạo nhiều lần đọc vào nguồn dữ liệu gốc.

### 5.2. Không cache kết quả theo trạng thái nghiệp vụ

Ví dụ một đối tượng record:

§§§java
public record CustomerDto(
        String id,
        String displayName,
        boolean active
) {}
§§§

Chỉ cache DTO đang hoạt động:

§§§java
@Cacheable(
    cacheNames = "activeCustomerById",
    key = "#p0",
    unless = "#result == null || !#result.active()"
)
public CustomerDto findCustomer(String id) {
    return loadCustomer(id);
}
§§§

Giải thích:

- `#result == null` bảo vệ tình huống không có dữ liệu.
- `||` có short-circuit, tránh gọi `active()` trên `null`.
- `!#result.active()` trả `true` với khách hàng không hoạt động nên kết quả này không được ghi cache.
- Khách hàng hợp lệ có `active() == true` có thể được cache nếu không bị chính sách khác từ chối.

Cần phân biệt **trạng thái lúc cache miss** với **trạng thái sau khi đã có cache entry**. Khi khách hàng chuyển từ active sang inactive, một entry đã lưu trước đó không tự mất chỉ vì biểu thức `unless` được khai báo. Phải có eviction, TTL hoặc chiến lược cập nhật cache phù hợp.

### 5.3. `unless` không ngăn gọi method

| Tình huống | Method có chạy? | Có ghi kết quả vào cache? |
|---|---|---|
| Cache miss, `unless=false` | Có | Có, nếu backend cho phép |
| Cache miss, `unless=true` | Có | Không |
| Cache hit | Không (đối với `@Cacheable` thông thường) | Không cần ghi; `unless` không đánh giá lại entry |
| `condition=false` | Có | Không |
| Method ném exception | Có | Không có kết quả bình thường để cache |

Việc thêm `unless` để loại giá trị `null` **không làm method chạy lại khi cache đang có entry `null` được ghi từ phiên bản trước**. Muốn thay đổi chính sách đối với dữ liệu cache hiện có cần xử lý entry cũ.

## 6. Kết hợp `condition` và `unless`

Một phương thức có thể dùng cả hai:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null || !#result.active()"
)
public CustomerDto findCustomer(String id) {
    return loadCustomer(id);
}
§§§

Quy tắc diễn giải:

1. ID không hợp lệ → không dùng cache, vẫn gọi method; method tự chịu trách nhiệm báo lỗi/trả kết quả phù hợp.
2. ID hợp lệ, Redis có entry → trả entry ngay; method không chạy, `unless` không đánh giá lại.
3. ID hợp lệ, Redis chưa có entry → gọi method.
4. Method trả `null` hoặc DTO inactive → không ghi cache.
5. Method trả DTO active → ghi cache theo TTL và serializer của Redis Cache.

Bảng chân trị cho một **cache miss**:

| `condition` | Kết quả method | `unless` | Hành động cache |
|---|---|---|---|
| `false` | Bất kỳ kết quả bình thường | Không cần xét | Bỏ qua cache |
| `true` | DTO active | `false` | Ghi DTO |
| `true` | DTO inactive | `true` | Không ghi |
| `true` | `null` | `true` | Không ghi |
| `true` | Exception | Không có kết quả | Không ghi kết quả bình thường |

`condition` và `unless` không phải một dạng filter dữ liệu hai chiều có thể áp dụng lại trên mọi cache hit. Chúng là hai bước điều khiển việc áp dụng cache và việc chấp nhận **kết quả mới**.

## 7. Cache giá trị `null` là quyết định có chủ đích

### 7.1. "Không có dữ liệu" có thể là một kết quả hữu ích

Xét thao tác tìm khách hàng theo ID. Nếu ID `404` không tồn tại, một lời gọi trả `null`. Với lượng truy cập lớn, nếu mỗi request đều đọc database và đều phát hiện "không có", nguồn dữ liệu chịu tải không cần thiết.

Lưu tạm kết quả "không có" để lần sau trả nhanh được gọi là **negative caching**.

§§§text
Lần gọi 1:
findCustomer("404") -> Redis miss -> DB: không tìm thấy -> lưu dấu vết null

Lần gọi 2:
findCustomer("404") -> Redis hit (giá trị logic null) -> không gọi DB
§§§

Nhưng negative caching cũng có rủi ro: nếu khách hàng `404` được tạo ở database sau lần tra cứu đầu, người dùng có thể tiếp tục nhận kết quả `null` cho đến khi cache hết TTL hoặc được evict.

### 7.2. Redis key không lưu "Java null" theo nghĩa trực tiếp

Redis có các kiểu giá trị nhị phân như String, Hash, Set..., không có một kiểu dữ liệu Redis riêng mang nghĩa **Java `null`**. Để cache một kết quả null, Spring Cache/RedisCache cần biểu diễn nó bằng một **marker/sentinel** do implementation quản lý, rồi serialize marker đó thành dữ liệu Redis.

Spring Data Redis dùng cơ chế chuyển đổi giá trị `null` phù hợp với cache abstraction (chẳng hạn nội bộ dùng `NullValue`). Khi đọc lại, cache abstraction chuyển representation đó về giá trị `null` logic cho caller.

Vì vậy:

- **Redis cache miss**: không có cache entry hợp lệ cho key.
- **Cache hit với `null` logic**: có entry ghi nhận việc tra cứu trước đó không có kết quả.
- Hai trường hợp đều có thể khiến một method Java trả `null`, nhưng cơ chế gọi method và chi phí truy vấn dữ liệu gốc khác nhau.

Không nên dùng `redis-cli GET` để đoán một cách độc lập rằng payload tuần tự hóa là `null`. Serializer có thể là JDK serializer hoặc serializer khác, và giá trị lưu trữ có thể là dữ liệu nhị phân.

### 7.3. API Cache phân biệt miss và cached-null ra sao?

Ở mức Spring Cache API:

§§§java
org.springframework.cache.Cache cache =
        cacheManager.getCache("customerLookup");

if (cache == null) {
    throw new IllegalStateException("Cache region is missing");
}

org.springframework.cache.Cache.ValueWrapper wrapper =
        cache.get("404");

if (wrapper == null) {
    // Cache miss: không có entry.
} else if (wrapper.get() == null) {
    // Có entry: kết quả được cache là null.
} else {
    // Có entry chứa giá trị khác null.
}
§§§

Đây là mô hình phân biệt được `Cache.ValueWrapper` theo hợp đồng `Cache.get(key)`. Ứng dụng dùng `@Cacheable` thường không cần tự viết đoạn code này; Spring Cache interceptor làm việc đó.

## 8. Chính sách mặc định và cấu hình Redis Cache

### 8.1. Mặc định RedisCacheConfiguration cho phép cache null

Trong Spring Data Redis, `RedisCacheConfiguration.defaultCacheConfig()` mặc định cho phép lưu kết quả null qua cache abstraction. Ngoài ra, nó áp dụng các mặc định khác về prefix, serializer và TTL; tùy Spring Boot version và cấu hình ứng dụng, RedisCacheManager cuối cùng có thể được tùy biến thêm.

Điều đáng chú ý: **`unless="#result == null"` vẫn có tác dụng dù Redis Cache cho phép null**. `unless` chặn kết quả từ tầng annotation trước khi cache backend được yêu cầu lưu.

Ngược lại, nếu `unless` không chặn mà backend cấm null, một lời gọi `put(null)` có thể bị từ chối theo hợp đồng backend. Vì vậy khi chủ động tắt cache null và method có thể trả null, nên thiết kế đường annotation hợp lý thay vì trông chờ RedisCacheManager tự bỏ qua mọi null mà không có tác động.

### 8.2. Cấu hình toàn ứng dụng bằng Spring Boot property

Để **không cho phép** lưu null vào Redis Cache:

§§§yaml
spring:
  cache:
    type: redis
    redis:
      cache-null-values: false
      time-to-live: 10m
  data:
    redis:
      host: localhost
      port: 6379
§§§

`spring.cache.redis.cache-null-values: false` là cấu hình của Spring Boot Redis Cache, không phải lệnh cấu hình trực tiếp Redis server. Nó áp dụng chính sách mặc định cho cache manager do Boot tự cấu hình. `time-to-live: 10m` là TTL được chỉ định cho cache entry theo cấu hình này.

Nếu muốn **cho phép negative caching**, có thể đặt:

§§§yaml
spring:
  cache:
    type: redis
    redis:
      cache-null-values: true
      time-to-live: 30s
§§§

Hai đoạn YAML mô tả **hai phương án thay thế**, không nên chép đồng thời vào cùng một file. TTL `30s` ở đây là ví dụ giúp giảm thời gian giữ kết quả không tìm thấy; nếu cùng CacheManager dùng chung TTL cho tất cả entry, những kết quả có dữ liệu cũng chịu TTL đó.

### 8.3. Cấu hình trực tiếp với RedisCacheManager

Nếu cần viết Java configuration thay vì cấu hình Boot:

§§§java
package com.example.demo.cache;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class RedisCacheConfig {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .build();
    }
}
§§§

Cấu hình này cấm lưu null cho các cache dùng cấu hình mặc định của manager. Nó phù hợp khi toàn ứng dụng đã thống nhất rằng null không được cache. Khi khai báo `RedisCacheManager` Bean riêng, cần hiểu nó có thể thay thế hoặc làm thay đổi đường auto-configuration của Spring Boot, vì vậy nên chọn một phương án cấu hình rõ ràng.

### 8.4. Cấu hình hai cache region với TTL và chính sách null khác nhau

Một ứng dụng thường cần:

- `customerById`: lưu DTO hợp lệ 10 phút, không cache null.
- `customerLookup`: cho phép null để giảm truy vấn ID không tồn tại, TTL 20 giây.

Với Spring Boot Redis auto-configuration, có thể dùng customizer:

§§§java
package com.example.demo.cache;

import java.time.Duration;
import org.springframework.boot.autoconfigure.cache.RedisCacheManagerBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration
public class RedisCacheRegionsConfig {

    @Bean
    public RedisCacheManagerBuilderCustomizer cacheRegions() {
        return builder -> builder
                .withCacheConfiguration(
                        "customerById",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofMinutes(10))
                                .disableCachingNullValues()
                )
                .withCacheConfiguration(
                        "customerLookup",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofSeconds(20))
                );
    }
}
§§§

`customerLookup` không gọi `disableCachingNullValues()`, nên dựa vào cấu hình mặc định cho phép null. Ví dụ dùng Spring Boot Redis Cache auto-config và **không đồng thời bật chính sách toàn cục `cache-null-values: false` như mẫu ở mục 8.2** để tránh tạo hai lớp quy định mâu thuẫn không cần thiết. Cấu hình Java này cũng không cần thiết nếu chỉ có một cache region và một TTL chung.

Spring Data Redis phiên bản mới có khả năng TTL động thông qua `RedisCacheWriter.TtlFunction`; tuy nhiên, đó là một cấu hình nâng cao phụ thuộc phiên bản và cách nhận diện value. Hai cache region với chính sách rõ ràng thường dễ hiểu hơn khi bắt đầu thiết kế.

## 9. Hai chiến lược khi method có thể trả null

### 9.1. Chiến lược A: không cache null

Dùng khi bản ghi có thể được tạo ngay sau lúc tra cứu, kết quả không tồn tại mang tính tạm thời, hoặc tầng dữ liệu gốc đủ nhanh để chịu nhiều lần cache miss:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public CustomerDto findCustomer(String id) {
    return repository.findById(id)
            .map(CustomerDto::from)
            .orElse(null);
}
§§§

Kết hợp cache region `customerById` cấu hình `disableCachingNullValues()` sẽ làm chính sách rõ ràng ở cả annotation và backend.

**Hệ quả:** các ID không tồn tại luôn cần truy vấn dữ liệu gốc khi gọi method qua cache, trừ khi có lớp cache khác. Đây là lựa chọn tốt nếu tính mới của dữ liệu khi vừa được tạo quan trọng hơn chi phí những lần không tìm thấy.

### 9.2. Chiến lược B: cache null ngắn hạn

Dùng khi nhiều request lặp lại cùng một ID vắng mặt, chi phí tra cứu đáng kể và ứng dụng chấp nhận một khoảng trễ ngắn trước khi thấy bản ghi mới:

§§§java
@Cacheable(
    cacheNames = "customerLookup",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()"
)
public CustomerDto findCustomer(String id) {
    return repository.findById(id)
            .map(CustomerDto::from)
            .orElse(null);
}
§§§

Ở đây cố ý **không có `unless="#result == null"`**. Cache region `customerLookup` phải cho phép null; TTL ngắn (ví dụ 20 giây) giúp hạn chế thời gian trả kết quả vắng mặt không còn đúng.

Nếu có nghiệp vụ tạo hoặc cập nhật khách hàng, cần một quy tắc eviction/update cho key tương ứng để giảm thời gian stale:

§§§java
@CacheEvict(cacheNames = "customerLookup", key = "#p0")
public void createOrReplace(String id, CreateCustomerRequest request) {
    repository.save(toEntity(id, request));
}
§§§

`CreateCustomerRequest`, `toEntity` và `repository` là các thành phần nghiệp vụ của ứng dụng, không phải API Spring Data Redis có sẵn. Ví dụ chỉ cho thấy định hướng: sau khi dữ liệu gốc được ghi thành công, cần loại bỏ cache entry "không tồn tại" nếu key đó có thể đã được cache trước.

**Không dùng negative caching để che lỗi hạ tầng.** Phương thức nên phân biệt "không tìm thấy" với lỗi kết nối database. Nếu database lỗi nhưng service bắt exception rồi trả null, Spring Cache có thể ghi null như thể bản ghi thật sự không tồn tại, gây ra kết quả sai kéo dài.

## 10. `Optional<T>` và ý nghĩa của `#result`

Spring Cache hỗ trợ phương thức `@Cacheable` trả về `Optional<T>`. Khi sử dụng `unless`, biến `#result` đại diện cho **giá trị nghiệp vụ bên trong Optional**, không phải wrapper `Optional` của phương thức.

Ví dụ:

§§§java
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    unless = "#result == null"
)
public Optional<CustomerDto> findCustomer(String id) {
    return repository.findById(id)
            .map(CustomerDto::from);
}
§§§

Khi `findCustomer("42")` trả `Optional.of(customer)`, `#result` có thể được đánh giá như `customer`.

Khi `findCustomer("999")` trả `Optional.empty()`, `#result` được xem là `null` trong biểu thức `unless`. Vì thế `unless="#result == null"` phù hợp để tránh cache "không tìm thấy" với cả phương thức trả DTO nullable lẫn `Optional<DTO>`.

Một số cách viết sai ý định:

§§§java
// Ý định: "không cache Optional.empty()".
// Nhưng #result không phải Optional wrapper.
@Cacheable(
    cacheNames = "customerById",
    unless = "#result.isEmpty()"
)
public Optional<CustomerDto> findCustomer(String id) {
    return repository.findById(id).map(CustomerDto::from);
}
§§§

Biểu thức này không tương ứng hợp đồng `#result` của Spring Cache và có thể thất bại khi kết quả bên trong vắng mặt. Hãy dùng `#result == null` cho tình huống này.

Với `CompletableFuture`, Reactor `Mono` hoặc `Flux`, Spring Framework phiên bản mới có hỗ trợ cache theo khả năng thích ứng bất đồng bộ riêng. Không suy luận tất cả biểu thức SpEL hoạt động trên wrapper hay thời điểm hoàn tất giống phương thức đồng bộ; cần đối chiếu phiên bản Spring Framework và hợp đồng return type thực tế.

## 11. `@CachePut`, `@CacheEvict` và giới hạn của `unless`

### 11.1. `@CachePut`: method luôn thực thi

`@CachePut` dùng khi muốn gọi method và cập nhật cache bằng kết quả mới:

§§§java
@CachePut(
    cacheNames = "customerById",
    key = "#result.id()",
    condition = "#p0 != null",
    unless = "#result == null"
)
public CustomerDto updateCustomer(UpdateCustomerCommand command) {
    return performUpdate(command);
}
§§§

Trong ví dụ, `UpdateCustomerCommand` là request hợp lệ do ứng dụng tự định nghĩa, `performUpdate` trả `CustomerDto` hoặc null. Nếu biểu thức `key` dùng `#result`, nó phải nằm trong ngữ cảnh sau khi method được thực thi và trả kết quả hợp lệ. Với kiểu có thể trả null, thiết kế key dựa trên tham số ổn định thường đơn giản hơn, chẳng hạn `key="#p0.id()"`, tránh truy cập `#result.id()` khi kết quả vắng mặt.

Điểm chính: `@CachePut` **không dùng cache hit để bỏ qua method**. `condition` quyết định có thực hiện cập nhật cache, `unless` có thể veto việc cập nhật kết quả mới. Tùy nghiệp vụ, nếu update thất bại và trả null, một entry cache cũ vẫn có thể tồn tại; lúc đó cần xác định chiến lược eviction phù hợp.

### 11.2. `@CacheEvict`: loại bỏ dữ liệu đã cache

Ví dụ:

§§§java
@CacheEvict(cacheNames = "customerById", key = "#p0")
public void deleteCustomer(String id) {
    repository.deleteById(id);
}
§§§

Theo mặc định, eviction chạy sau khi method kết thúc thành công. Có thể dùng `beforeInvocation=true` khi muốn evict trước method bất kể kết quả chạy ra sao, nhưng cần hiểu hậu quả đối với lỗi nghiệp vụ.

`unless` không phải cơ chế để quyết định xóa entry cũ trong `@CacheEvict`; nó gắn với việc veto **cache put**. Khi chính sách "không cache null" mới được triển khai, các cache entry null đã tồn tại cần TTL hoặc một quá trình eviction cụ thể.

### 11.3. `sync=true` không kết hợp với `unless`

`@Cacheable(sync = true)` dùng để yêu cầu cache provider phối hợp việc tính toán cache miss cho cùng một key khi khả năng backend cho phép. Tuy nhiên, Spring Cache đặt ràng buộc rằng `sync=true` **không hỗ trợ `unless`**, vì việc cache value gắn liền đường `get(key, Callable)`.

Ví dụ cấu hình không hợp lệ:

§§§java
// Không dùng cách kết hợp này.
@Cacheable(
    cacheNames = "customerById",
    key = "#p0",
    sync = true,
    unless = "#result == null"
)
public CustomerDto findCustomer(String id) {
    return loadCustomer(id);
}
§§§

Nếu cần đồng thời chống "cache stampede" và loại bỏ kết quả null, cân nhắc thiết kế ở tầng cache/provider hoặc một cơ chế bảo vệ riêng có hợp đồng rõ ràng. Không giả định chỉ bật `sync=true` sẽ tự giải quyết yêu cầu từ chối cache null.

## 12. Khi cache null có ích và khi có hại

| Tình huống | Khuyến nghị khởi đầu | Giải thích |
|---|---|---|
| Tra cứu ID không tồn tại được gọi lặp lại rất nhiều | Cache null **TTL ngắn** | Giảm tải các request vô ích |
| Dữ liệu thường được tạo ngay sau lần đọc đầu | Không cache null, hoặc evict chủ động | Tránh "không tìm thấy" bị giữ lại |
| Truy vấn remote service đắt đỏ, missing ổn định | Cân nhắc negative caching | Tiết kiệm network và tải dịch vụ nguồn |
| Dữ liệu nhạy cảm theo người dùng/tenant | Đặt key gồm đúng ngữ cảnh và kiểm soát authorization | Nguy cơ cache chia sẻ nhầm dữ liệu nghiêm trọng hơn quyết định null |
| Dữ liệu không tìm thấy vì lỗi kết nối upstream | **Không cache như null** | Tránh biến outage tạm thời thành kết quả "không tồn tại" |
| Hệ thống cho phép stale vài giây | Có thể cache null TTL ngắn | Chấp nhận độ trễ nhìn thấy dữ liệu mới |
| Hệ thống yêu cầu nhìn thấy ngay sau khi tạo bản ghi | Không cache null hoặc evict khi ghi | TTL một mình có thể không đáp ứng SLA |
| Có hàng triệu key không tồn tại bị quét ngẫu nhiên | Cẩn trọng negative caching | Có thể tăng memory Redis do số entry vắng mặt lớn |
| Kết quả null có thể đổi thành có dữ liệu chỉ sau một event | Dùng event eviction/version hoặc bỏ qua null | Tránh stale kết quả |
| Có quy tắc xóa/tạo/đổi trạng thái rõ ràng | Thiết kế eviction cho từng operation | `unless` không sửa các entry cũ |

Không có một lựa chọn "luôn cache null" hoặc "không bao giờ cache null" đúng cho mọi sản phẩm. Cần xét chi phí miss, tốc độ thay đổi trạng thái, TTL chấp nhận được, lượng key âm và cách đồng bộ khi có dữ liệu mới.

### 12.1. Mất bao lâu để hết stale negative cache?

Giả sử:

§§§text
t = 0s   GET customer 42 -> không có -> cache null (TTL 30s)
t = 5s   Tạo customer 42 ở database
t = 6s   GET customer 42 -> cache hit null
t = 30s  Entry null đã hết TTL; lần đọc sau truy vấn database
§§§

Nếu không có eviction khi tạo customer, người dùng có thể nhận kết quả vắng mặt cho đến khi hết TTL. TTL ngắn giúp **giới hạn tối đa thời gian stale theo mô hình đơn giản**, nhưng tác động thực tế còn tùy failover, key expiration, cache refresh và các lớp cache khác.

Có thể evict ngay sau khi tạo thành công, nhưng trong môi trường nhiều instance cần sử dụng **cùng Redis cache**, key và tên cache nhất quán; nếu còn cache cục bộ ở các instance khác thì eviction phân tán cần được thiết kế riêng.

### 12.2. Cache null không giải quyết mọi kiểu cache stampede

Nếu null không được cache, nhiều request đến cùng một ID không tồn tại có thể đồng thời đánh xuống database. Cache null giúp những request **sau khi kết quả đầu tiên được ghi** không phải gọi database nữa, nhưng không chắc tránh được nhiều request đầu tiên cùng miss trong một cửa sổ nhỏ.

Chống stampede có thể cần phối hợp tải, single-flight, khóa tính toán hoặc rate limiting theo ngữ cảnh. Đổi lại, chúng có thêm chi phí và điểm thất bại riêng. Hãy đo số lần gọi cùng key và chi phí thực tế trước khi thêm cơ chế phức tạp.

## 13. Cấu hình TTL và vấn đề chính sách cho kết quả khác nhau

Một `RedisCacheConfiguration.entryTtl(Duration)` đơn giản áp dụng TTL cho entry của cache region đó. Nếu region vừa cache DTO vừa cache null, cả hai thông thường dùng TTL như cấu hình của region.

Nếu yêu cầu:

- Kết quả có dữ liệu: cache 10 phút.
- Kết quả vắng mặt: cache 10 giây.

thì không thể chỉ đặt một `time-to-live: 10m` rồi kỳ vọng `null` tự có TTL ngắn hơn. Các phương án:

1. Dùng **cache region hoặc cơ chế lưu trữ khác nhau** cho kết quả có/không có dữ liệu, với routing rõ ràng.
2. Dùng `RedisCacheWriter.TtlFunction` nếu phiên bản Spring Data Redis hỗ trợ và bài toán phù hợp, đảm bảo TTL động phân biệt đúng representation của null.
3. Không cache null và chấp nhận gọi lại nguồn dữ liệu.
4. Triển khai negative-cache policy rõ ràng ở service nếu đặc tính nghiệp vụ yêu cầu kiểm soát đầy đủ.

Việc phân loại null ở TTL function cần hiểu đối tượng value đã qua các bước adaptation của Spring Cache; không tự đoán mọi giá trị null vẫn là Java `null` ở đúng lớp đó.

Một cache riêng cho "không có dữ liệu" có thể cần hai lớp lookup. Vì vậy nên cân nhắc tổng độ phức tạp so với lợi ích tiết kiệm truy vấn thực tế.

## 14. Những lỗi cấu hình thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Method vẫn được gọi mọi lần dù đã thêm `@Cacheable` | `condition=false`, cache miss liên tục, `unless=true`, chưa bật caching hoặc self-invocation | Xác định luồng interceptor, điều kiện, cache name/key và cách gọi method |
| Null được cache dù đã thêm `unless` | Entry null đã tồn tại trước khi triển khai, gọi method khác có cùng key/cache, hoặc annotation không được intercept | Kiểm tra eviction, key và đường gọi qua Spring proxy |
| Lỗi khi method trả null | Backend đã `disableCachingNullValues` nhưng annotation vẫn cố ghi null | Thêm `unless="#result == null"` hoặc thay đổi chính sách cache |
| `condition` cố dùng `#result` | Result chưa tồn tại trước khi gọi method | Chuyển logic phụ thuộc kết quả sang `unless` |
| `unless` gọi method trên `null` | Ví dụ `#result.active()` không có null guard | Dùng `#result == null || ...` |
| `unless="#result.isEmpty()"` không hợp với `Optional` | `#result` là giá trị bên trong Optional | Dùng `#result == null` cho empty |
| Cache hit trả dữ liệu không hợp lệ với chính sách mới | `unless` chỉ chặn lần ghi mới | Evict entry cũ hoặc dùng namespace/version key mới |
| Tạo dữ liệu xong vẫn đọc null | Negative cache còn TTL | Evict cache key khi create/update thành công |
| Bị lỗi vì `sync=true` + `unless` | Spring Cache không hỗ trợ tổ hợp | Bỏ `unless` hoặc thiết kế cơ chế cache miss khác |
| Hai người dùng đọc nhầm dữ liệu | Key thiếu tenant/user/security context | Thiết kế key và quyền truy cập đúng phạm vi |
| Khác Redis serializer nên không đọc được entry | CacheManager hoặc app đã đổi serializer | Phối hợp schema/serializer migration và xóa cache cũ khi cần |
| `@Cacheable` không có hiệu lực khi tự gọi method | Self-invocation bỏ qua Spring proxy | Gọi qua Spring-managed bean/interface thích hợp |
| Method bị lỗi nhưng cache null "không tìm thấy" | Tầng dịch vụ nuốt exception upstream rồi trả null | Phân biệt Not Found với Outage, để lỗi thật được xử lý riêng |

### 14.1. Chú ý self-invocation

Ví dụ:

§§§java
@Service
public class CustomerService {

    public CustomerDto loadFromApi(String id) {
        return findCached(id); // Gọi nội bộ; proxy caching có thể bị bỏ qua.
    }

    @Cacheable(cacheNames = "customerById", key = "#p0")
    public CustomerDto findCached(String id) {
        return loadCustomer(id);
    }
}
§§§

Khi dùng Spring proxy mode thông thường, lời gọi trực tiếp qua `this` trong cùng instance không đi qua caching interceptor. Để cache hoạt động, một Spring bean khác có thể gọi method public trên bean proxy sở hữu annotation. Không nên kết luận `condition` hoặc `unless` sai chỉ vì annotation bị bỏ qua do cách gọi.

### 14.2. Không dùng cache key ngắn cho dữ liệu phụ thuộc quyền

Ví dụ API `findDashboard(userId, tenantId, locale)` mà chỉ dùng `key="#p0"` có thể trộn dữ liệu giữa tenant hoặc locale. Cache hit xảy ra **trước** method, nên permission check nằm duy nhất trong thân method có thể không được thực hiện ở cache hit.

Thiết kế cần đặt authorization ở lớp bắt buộc được gọi cho mọi request, đồng thời bảo đảm key chứa đầy đủ biến thể dữ liệu và không chia sẻ thông tin bị giới hạn. `condition` có thể giảm sử dụng cache trong một số trường hợp nhưng **không thay thế access control**.

## 15. Quan sát hành vi thực tế của condition, unless và null

Một cách học dễ hiểu là theo dõi số lần method thực thi khi gọi cùng key nhiều lần.

Ví dụ minh họa một service có bộ đếm số lần truy vấn nguồn:

§§§java
@Service
public class CustomerLookupService {

    private final java.util.concurrent.atomic.AtomicInteger loads =
            new java.util.concurrent.atomic.AtomicInteger();

    @Cacheable(
        cacheNames = "customerById",
        key = "#p0",
        condition = "#p0 != null && !#p0.isBlank()",
        unless = "#result == null"
    )
    public String findName(String id) {
        loads.incrementAndGet();

        if ("404".equals(id)) {
            return null;
        }

        return "Customer-" + id;
    }

    public int loadCount() {
        return loads.get();
    }
}
§§§

Dùng một bean khác để gọi `findName` qua Spring-managed proxy (không tự gọi trong cùng class). Kỳ vọng về logic:

| Lần gọi | Input | Cache ban đầu | Kết quả | Số lần thực thi method |
|---|---|---|---|---|
| 1 | `"42"` | Miss | `"Customer-42"` | Tăng 1 |
| 2 | `"42"` | Hit | `"Customer-42"` | Không tăng |
| 3 | `"404"` | Miss | `null` | Tăng 1 |
| 4 | `"404"` | Vẫn miss vì `unless` | `null` | Tăng 1 |
| 5 | `""` | `condition=false` | `"Customer-"` (ví dụ giả lập) | Tăng 1 |

Ví dụ chỉ minh họa hành vi annotation, không phải nghiệp vụ validation tốt. Trong hệ thống thật, ID rỗng thường cần bị từ chối theo quy tắc domain.

Nếu bỏ `unless` và cho phép cache null, lời gọi thứ ba có thể tạo một entry null; lời gọi thứ tư có thể hit entry đó và không tăng bộ đếm, cho đến khi hết TTL/eviction.

Để quan sát production, theo dõi ít nhất: cache hit/miss, database call theo nhóm kết quả, tỷ lệ không tìm thấy, lượng cache entry, TTL, eviction, độ trễ và sự kiện tạo dữ liệu mới sau negative hit. Tránh log toàn bộ cache value nếu chứa dữ liệu nhạy cảm.

## 16. Quy trình quyết định cho một method cần cache

§§§mermaid
flowchart TD
    A["Method trả dữ liệu hoặc null"] --> B{"Input nào cần được cache?"}
    B --> C["Viết condition trên tham số"]
    C --> D{"Kết quả null có ý nghĩa gì?"}
    D -->|Lỗi upstream| E["Phân biệt lỗi; không trả null như Not Found"]
    D -->|Không tìm thấy thật| F{"Có chấp nhận stale Not Found?"}
    F -->|Không| G["Dùng unless: #result == null"]
    F -->|Có| H["Cho phép null + TTL ngắn + eviction khi có dữ liệu mới"]
    D -->|Không xảy ra| I["Có thể cấm null ở RedisCacheManager"]
    G --> J["Thiết kế TTL, key, serializer, eviction"]
    H --> J
    I --> J
    E --> J
    J --> K["Đo hit/miss và kiểm tra edge case vận hành"]
§§§

Một quy trình ngắn để áp dụng:

1. Viết **hợp đồng method**: input hợp lệ, result tồn tại, not-found, exception.
2. Chọn `condition` dựa trên **tham số và ngữ cảnh trước invocation**.
3. Chọn `unless` dựa trên **kết quả** sau invocation; dùng `#result == null` khi không muốn cache not-found.
4. Chọn chính sách `null` tại Redis cache backend, TTL phù hợp, và vùng cache tương ứng.
5. Thiết kế eviction/update cho các thao tác create/update/delete.
6. Đảm bảo cache key không làm lẫn các biến thể dữ liệu hay vượt qua authorization.
7. Quan sát cache hit/miss và hành vi khi dữ liệu từ "không tồn tại" trở thành "tồn tại".

## 17. Tổng kết

**`condition` quyết định lời gọi có tham gia cache hay không trước khi method chạy; `unless` quyết định có ghi kết quả mới vào cache sau khi method trả về hay không.** Với `@Cacheable`, cache hit thường bỏ qua method và không chạy lại `unless` trên entry đã có.

Còn **quyết định cache giá trị `null`** là một chính sách riêng. Cho phép cache null giúp giảm tải các tra cứu không tìm thấy nhưng có thể trả kết quả stale khi dữ liệu được tạo sau đó; bỏ qua null giúp giữ tính mới tốt hơn nhưng tăng số lần gọi nguồn dữ liệu. Spring Data Redis có khả năng lưu null dưới dạng representation nội bộ do cache abstraction quản lý; `RedisCacheConfiguration.disableCachingNullValues()` và thuộc tính Spring Boot `spring.cache.redis.cache-null-values` giúp quy định chính sách backend.

Một cấu hình đúng cần phối hợp **`condition` trên input, `unless` trên output, TTL, key, eviction và khả năng phân biệt not-found với lỗi hệ thống**. Khi lựa chọn dựa trên đặc điểm nghiệp vụ cụ thể, cache vừa giảm tải vừa tránh che khuất dữ liệu mới hoặc tạo kết quả sai kéo dài.
