# Kiểm thử cache key, TTL và cách ly dữ liệu giữa người dùng hoặc tenant

> **Module:** Spring Boot – testing  
> **Nhóm:** Tích hợp bổ sung  
> **Đề bài:** Cache key, TTL và dữ liệu tách biệt giữa người dùng hoặc tenant  
> **Mục tiêu:** Thiết kế cache key có đủ phạm vi bảo mật, kiểm tra cache hit/miss/invalidation, chứng minh TTL thực trên provider, tránh cross-tenant data leakage, sử dụng Spring Cache + Redis + Testcontainers và tách security authorization khỏi caching. Ví dụ thực hành Java 17, Spring Boot 3.5, Maven, JUnit Jupiter và Redis 7.

## 1. Tại sao cache là một ranh giới kiểm thử quan trọng?

Cache không chỉ tối ưu hiệu năng; một khóa cache sai có thể biến một request hợp lệ thành **rò rỉ dữ liệu người dùng hoặc tenant khác**.

Giả sử hai tenant đều có hồ sơ mã `42`:

```text
Tenant "north": profileId = "42" -> "NORTH-42"
Tenant "south": profileId = "42" -> "SOUTH-42"

Nguồn dữ liệu đúng:
  repository.find("north", "42") -> "NORTH-42"
  repository.find("south", "42") -> "SOUTH-42"

Cache key SAI: "profiles::42"
  request north/42 -> cache write "NORTH-42"
  request south/42 -> cache hit  "NORTH-42"   <-- LEAK!

Cache key ĐÚNG: chứa tenant + loại dữ liệu + profileId
  "profiles::v1:t:5:north:p:2:42" -> "NORTH-42"
  "profiles::v1:t:5:south:p:2:42" -> "SOUTH-42"
```

Ngay cả khi database query có `WHERE tenant_id = ?` đúng, một `@Cacheable(key="#profileId")` có thể trả dữ liệu từ cache **trước khi truy vấn database được gọi**. Điều này làm cho unit test repository đều pass nhưng một hệ thống dùng chung Redis vẫn không an toàn.

Bốn hợp đồng cần kiểm thử tách biệt:

1. **Identity / scope:** Cache entry thuộc tenant, user, record, projection, locale, role/policy version nào?
2. **Freshness:** Cache hit đúng; update/evict và TTL ngăn dữ liệu cũ tồn tại vượt mức cho phép.
3. **Correctness:** Miss phải truy vấn đúng nguồn dữ liệu, trả kết quả đúng và không làm chồng keys giữa các caches.
4. **Security:** Tenant identity được xác thực/ủy quyền từ trusted context; cache không thay thế authorization.

### 1.1. Luồng Spring Cache

```text
HTTP / message / business caller
              |
          authorization
              |
        trusted tenantId
              |
       Spring AOP cache proxy
              |
     cache name + logical key
              |
          RedisCacheManager
              |
       Redis GET / cache hit?
          /            \
         YES           NO
          |             |
      return value    service method
                          |
                    tenant-scoped repository
                          |
                     Redis SET + TTL
                          |
                       return
```

**Cảnh báo đặc biệt:** Nếu Spring caching interceptor trả một cache hit, body của method có `@Cacheable` **không được chạy**. Vì vậy việc kiểm tra quyền *chỉ bên trong body* của cached method có nguy cơ bị bỏ qua trên cache hit. Luôn thực hiện authentication/tenant authorization **trước cache interception**, ví dụ ở API/security facade hoặc một advice có ordering được kiểm thử, rồi truyền tenant đã xác thực vào cached service.

## 2. Spring Cache key được hình thành như thế nào?

### 2.1. `@EnableCaching`, `@Cacheable` và proxy

Spring Cache abstraction chỉ tạo cơ chế intercept khi bật cache advice, thường bằng `@EnableCaching`. Khi gọi một **Spring-managed proxy bean** từ bên ngoài, `@Cacheable` tra `CacheManager`:

- Có entry cho cache name/key: trả cached value, method body không được gọi.
- Không có entry: gọi method body, rồi ghi kết quả vào cache theo `condition`/`unless`/provider config.
- Cache eviction/update có thể dùng `@CacheEvict` hoặc `@CachePut`.
- `@Caching` có thể gom nhiều operations nhưng cần xác định rõ mỗi key.

Một object được tạo bằng `new Service(...)` trong pure unit test không được Spring AOP bọc, do đó annotation cache không có tác dụng. Tương tự, **self-invocation** `this.cachedMethod(...)` thường bỏ qua proxy interception mặc định.

### 2.2. Default `SimpleKeyGenerator`: tiện nhưng không thay hợp đồng bảo mật

Khi không khai `key` hoặc `keyGenerator`:

- Không có arguments: `SimpleKey.EMPTY`.
- Một argument phù hợp: chính argument đó làm key.
- Nhiều arguments: `SimpleKey` chứa tất cả tham số.

Ví dụ:

```java
@Cacheable("profiles")
public String find(String tenantId, String profileId) {
    //...
}
```

Với hai tham số này, default key thường đã phân biệt tenant và profile. Nhưng nếu refactor API chỉ còn `find(String profileId)` và tenant nằm trong ThreadLocal/auth context, default key **không có tenant**. Hoặc developer thêm `key = "#profileId"`, nó sẽ bỏ tenant khỏi key dù method vẫn có hai args.

Với dữ liệu tenant-sensitive, xác định **key contract công khai và ổn định**; viết test chứng minh tenant A và B với cùng record ID không share cache entry. Đừng phụ thuộc vào hiện trạng method signature một cách vô thức.

### 2.3. SpEL key

Có thể dùng indices độc lập cách Java compiler lưu parameter names:

```java
@Cacheable(
    cacheNames = "profiles",
    key = "T(com.example.cachelab.CacheKeys).profile(#p0, #p1)")
public String get(String tenantId, String profileId) {
    return repository.find(tenantId, profileId);
}
```

Đây là snippet trong bean Spring, không phải file độc lập. `#p0` và `#p1` lần lượt là argument thứ nhất và thứ hai; `T(...)` gọi static utility class. Đặt key builder tập trung sẽ giúp `@Cacheable`, `@CacheEvict` và `@CachePut` dùng cùng hợp đồng.

Thực hành không nên xây key bằng nối chuỗi thiếu escape khi các ID có thể chứa dấu phân cách:

```text
bad: tenant + ":" + id

tenant "a:b", id "c"    => "a:b:c"
tenant "a",   id "b:c"  => "a:b:c"
```

Các biện pháp tốt gồm: ID đã được canonicalize/validate, length-prefix encoding, tagged fields, hoặc stable binary encoding. Không hash toàn bộ key rồi bỏ tenant khỏi audit context nếu không hiểu collision/security/rotation trade-offs.

## 3. Thiết kế cache key theo phạm vi bảo mật

### 3.1. Những dimension cần xem xét

Cache key phải phân biệt **mọi yếu tố làm thay đổi nội dung response**:

| Dimension | Khi nào cần? | Ví dụ |
| --- | --- | --- |
| Environment / application namespace | Nhiều ứng dụng/env dùng một Redis | `prod:billing` vs `test:billing` |
| Cache name / projection | Cùng ID nhưng các loại giá trị khác nhau | `profiles` vs `profileSummaries` |
| Tenant ID | Multi-tenant data | `north` vs `south` |
| User ID | Giá trị riêng từng user trong cùng tenant | `user-17` vs `user-18` |
| Record ID / natural key | Entity riêng | `profile-42` |
| Permission/role/policy version | Response phụ thuộc quyền | `policy-v4` |
| Locale / currency / timezone | View được cá nhân hóa | `vi-VN` vs `en-US` |
| Schema/cache version | Deploy thay đổi serialization/semantics | `v2` |
| Filter/sort/page/projection | Query result thay đổi theo params | `page=2,sort=name` |

**Không thêm mọi dimension vào tất cả keys vô điều kiện.** Chọn theo *hợp đồng của dữ liệu*. Ví dụ một public catalog giống nhau cho mọi tenant có thể share key nếu không có nội dung hoặc policy tenant-specific; hồ sơ khách hàng thường không được share.

### 3.2. Tenant context nào đáng tin?

Tenant ID từ query parameter hoặc HTTP header do client tự khai **không mặc nhiên đáng tin**. Trong production:

1. Authenticate principal/session/token.
2. Resolve tenant mà principal thực sự thuộc về, kiểm tra active membership/authorization.
3. Chọn tenant đã xác thực làm scope cho cache lookup.
4. Truy vấn repository với **cùng tenant** được phép.
5. Cache và invalidation dùng cùng scope.
6. Nếu authorization thay đổi, xác định cách invalidate caches hoặc bao gồm policy version.

**Tuyệt đối không xây cache key sau khi nhận tenant ID tùy ý rồi coi đó là authorization.** Nếu user có thể tự đặt tenantId = "south", key đúng về hình thức vẫn không bảo vệ dữ liệu tenant south.

### 3.3. User-scoped vs tenant-scoped

Một admin và một end-user cùng tenant có thể nhìn những trường khác nhau. Nếu cache return value đã được filter/ẩn theo quyền, key chỉ chứa tenant+record vẫn có thể lộ trường dành riêng cho admin. Tùy thiết kế:

- Cache **raw tenant entity** chỉ trong trusted backend và áp quyền/projection **sau khi lấy từ cache**; phải bảo đảm tầng downstream luôn kiểm soát quyền.
- Hoặc cache **authorized/view DTO** theo user/role/policy version, với invalidation khi phân quyền đổi.
- Không cache PII/token/secrets nếu không cần. Đánh giá encryption, Redis ACL/TLS, access logs, retention và data classification.
- Cache key cũng có thể lộ identifiers qua metrics/logs; tránh đưa token/password/email đầy đủ vào key.

TTL không thay authorization. Một entry sai tenant dù hết hạn sau 2 giây vẫn có thể gây sự cố trong 2 giây đó.

### 3.4. Cache name prefix khác tenant prefix

Spring Data Redis mặc định prefix Redis keys bằng cache name, dạng:

```text
profiles::<logical-key>
```

Prefix này giúp `profiles` và `profileSummaries` không chồng nhau khi dùng cùng logical key. **Nó không tự thêm tenant.** Tenant/user/record dimensions vẫn phải nằm trong logical key hoặc được triển khai bằng cơ chế namespacing tương đương.

Không tắt `spring.cache.redis.use-key-prefix` tùy tiện trên shared Redis. Nếu tự viết `RedisCacheManager`, giữ prefix isolation và test đường đi thực tế.

## 4. TTL: thời gian hết hạn thuộc cache provider, không chỉ annotation

### 4.1. `@Cacheable` không tự có tham số TTL

`@Cacheable` của Spring Framework không có một `ttl=...` attribute phổ quát. TTL phụ thuộc provider: Redis, Caffeine, Ehcache, Hazelcast, v.v.

Với Spring Boot 3.5 và RedisCacheManager auto-configuration, có thể cấu hình:

```properties
spring.cache.type=redis
spring.cache.redis.time-to-live=10m
spring.cache.redis.cache-null-values=false
spring.cache.redis.use-key-prefix=true
```

- `time-to-live=10m`: entry được viết sẽ hết hạn sau 10 phút trong Redis.
- `cache-null-values=false`: không cache null values với cấu hình provider tương ứng.
- `use-key-prefix=true`: giữ cache name prefix (thông thường là mặc định).
- `spring.cache.type=redis`: yêu cầu dùng Redis cache provider trong project có dependencies phù hợp.

**Default TTL của RedisCacheConfiguration không nhất thiết có expiration**; nếu quên cấu hình, entries có thể tồn tại tới khi bị evict/memory pressure/administrative action. Test phải kiểm tra TTL *thực trên Redis*, không chỉ đọc property file.

### 4.2. Per-cache TTL bằng `RedisCacheManager`

Nếu mỗi loại dữ liệu cần TTL khác nhau:

```java
@Bean
RedisCacheManager cacheManager(
        RedisConnectionFactory factory) {
    RedisCacheConfiguration defaultConfig =
            RedisCacheConfiguration.defaultCacheConfig()
                    .entryTtl(Duration.ofMinutes(5))
                    .disableCachingNullValues();

    Map<String, RedisCacheConfiguration> perCache = Map.of(
            "profiles", defaultConfig.entryTtl(Duration.ofMinutes(10)),
            "permissions", defaultConfig.entryTtl(Duration.ofSeconds(30)));

    return RedisCacheManager.builder(factory)
            .cacheDefaults(defaultConfig)
            .withInitialCacheConfigurations(perCache)
            .build();
}
```

Đây là **snippet nâng cao**, cần `RedisCacheManager`, `RedisConnectionFactory`, `RedisCacheConfiguration`, `Duration`, `Map`, `@Bean` imports và Spring configuration class. Không thêm snippet này vào project runnable bên dưới vì dự án chính dùng Boot auto-configuration cho một cache để dễ kiểm chứng.

Lưu ý `RedisCacheManager` thay bean auto-configured có thể khiến các properties `spring.cache.redis.*` không còn tự áp dụng như bạn tưởng; phải test configuration thực tế thay vì chỉ nhìn property file.

### 4.3. TTL khác TTI

- **TTL (time-to-live):** thời hạn kể từ lần ghi hoặc refresh entry theo provider; cache hit thường **không kéo dài TTL**.
- **TTI (time-to-idle):** hết hạn sau một khoảng không được truy cập; có thể cần provider-specific support.
- Redis bình thường có expiration/TTL; Spring Data Redis có cơ chế TTI emulation bằng các lệnh như `GETEX` khi bật cấu hình tương ứng và version Redis phù hợp.
- Đừng đồng nhất TTL 10 phút với “giữ tối đa 10 phút kể từ lần đọc cuối” nếu không thực sự có TTI.
- TTL không giải quyết stale authorization, revoked consent hoặc data delete request ngay lập tức. Các events đó có thể đòi invalidate chủ động.

### 4.4. TTL Redis có thể kiểm tra qua `PTTL`

Redis TTL/expiration semantics:

| Redis TTL result | Ý nghĩa |
| ---: | --- |
| Số dương | Còn thời gian sống |
| `-1` | Key tồn tại nhưng không có expiration |
| `-2` | Key không tồn tại |
| `0` hoặc gần 0 | Có thể đang sát thời điểm hết hạn; đừng assert exact milliseconds |

Với Spring Data Redis:

```java
Long ttlMs = redisTemplate.getExpire(
        redisKey, TimeUnit.MILLISECONDS);
```

Một test hợp lý kiểm tra TTL dương, không vượt quá thời gian cấu hình, sau đó **đợi đến khi key thật sự biến mất** bằng bounded polling/Awaitility. Không assert TTL chính xác 4000ms vì thời gian mạng/JVM/CI trôi qua sau lệnh SET.

## 5. Invalidation: TTL không thay việc xóa cache khi cập nhật dữ liệu

Có ba dạng thay đổi cần bảo vệ:

1. **Read:** `@Cacheable` lookup, miss thì lấy datasource, hit thì không gọi datasource.
2. **Update:** `@CacheEvict` xóa đúng key tenant+record sau khi update thành công hoặc `@CachePut` cập nhật cache chính xác.
3. **Delete/revoke:** Invalidate ngay khi business contract yêu cầu; không để một entry cũ chỉ chờ TTL nếu nội dung đã bị xóa/thu hồi quyền.

Ví dụ:

```java
@CacheEvict(
    cacheNames = "profiles",
    key = "T(com.example.cachelab.CacheKeys).profile(#p0, #p1)")
public void update(String tenantId, String profileId, String value) {
    repository.update(tenantId, profileId, value);
}
```

Nếu key của `@Cacheable` là tenant+id nhưng `@CacheEvict` chỉ dùng id, dữ liệu cũ không bị xóa đúng. Nếu một update làm `allEntries=true` hoặc `cache.clear()`, nó có thể xóa của toàn bộ tenants, vừa giảm hiệu năng vừa gây rủi ro phối hợp; không dùng nếu chỉ muốn invalidate một record.

### 5.1. Eviction và transaction ordering

`@CacheEvict` mặc định thực hiện **sau successful invocation** của method. Điều này không tự bảo đảm atomicity giữa database commit và Redis eviction. Với transactional updates, có thể cần transaction-aware cache manager hoặc after-commit events/outbox/invalidation logic rõ ràng.

Một transaction có thể rollback nhưng cache đã bị thay đổi nếu advice order không đúng; ngược lại DB đã commit mà eviction fail có thể để cache stale. Hãy viết integration tests cho transaction boundaries khi dữ liệu nhạy cảm và quan trọng.

### 5.2. Stampede, concurrent loads, stale-while-revalidate

Khi nhiều requests gặp cache miss cùng lúc:

- Nhiều thread có thể cùng gọi datasource, gây **cache stampede**.
- `@Cacheable(sync=true)` có thể phối hợp loading với một số cache providers, nhưng không tự bảo đảm distributed locking/exactly-once trên mọi instance.
- RedisCacheWriter mặc định có các concurrency semantics riêng; không suy diễn atomicity cho operation gồm nhiều lệnh.
- TTL quá ngắn làm miss thường xuyên; TTL quá dài làm stale data kéo dài.
- Jitter TTL có thể giảm việc rất nhiều keys cùng hết hạn một lúc nếu provider/config hỗ trợ và thiết kế phù hợp.
- Với dữ liệu phân quyền, ưu tiên correctness, revocation và containment hơn chỉ hit ratio.

## 6. Kiểm thử cache: ma trận tối thiểu

| Case | Input và setup | Assertion quan trọng |
| --- | --- | --- |
| Cache miss | Tenant north/profile 42 lần đầu | Repository load 1, value đúng |
| Cache hit | Cùng tenant/profile lần thứ hai | Value như cũ, repository load không tăng |
| Cross-tenant | north/42 rồi south/42 | Hai values đúng và khác nhau |
| Cross-record | north/42 rồi north/43 | Không share entry |
| Wrong key negative | Chỉ key theo id trong test mô phỏng | Chứng minh collision/rò rỉ có thể xảy ra |
| TTL exists | Đọc Redis PTTL sau cached write | TTL dương, hữu hạn |
| Expiry | Đợi bounded đến khi key hết hạn | Read tiếp theo load datasource lại |
| Tenant-specific invalidation | Update north/42 | Cache south/42 không bị xóa |
| User/role-specific response | Cùng tenant nhưng quyền khác | Không share authorized view sai |
| Null/negative caching | Record missing/permission denied | Behavior theo cache-null policy, tránh thông tin cũ |
| Transaction rollback | Update rồi rollback | Cache phản ánh source of truth |
| Multiple app instances | Shared Redis, khác JVM caches | Namespace/serialized value hợp lệ |

**Hai loại bằng chứng bổ sung nhau:** unit test `CacheKeys` bảo vệ composition/validation; Redis Testcontainers bảo vệ cách Spring AOP + CacheManager + Redis thực sự xử lý cache hit/TTL/eviction.

## 7. Dự án Java 17 + Spring Boot 3.5 + Redis Testcontainers

Dự án **runnable-design**, gồm pure Java unit tests và integration tests với Redis thật (cần Docker runtime). Data source được thay bằng một in-memory repository **có dữ liệu tenant-scoped** để tập trung test cache. Không phải ví dụ authentication/authorization hoàn chỉnh: mã gọi `service.get(tenantId, profileId)` giả định tenantId đã được xác thực ở một lớp trên trước cache. Ở hệ thống thật phải enforce điều này tại security boundary.

### 7.1. Mục tiêu bộ test

Có **8 phương thức JUnit `@Test`**:

- **3 unit tests** kiểm tra key builder không colliding khi thay tenant/record, và từ chối ID không hợp lệ.
- **5 integration tests** với Redis: cache hit, tenant isolation, record isolation, evict một tenant, TTL + expiration thực.

Tất cả integration tests dùng Docker Redis riêng, không có credentials production, không flush Redis chung.

### 7.2. Cây thư mục

```text
tenant-cache-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/cachelab/
    │   │   ├── CacheLabApplication.java
    │   │   ├── CacheKeys.java
    │   │   ├── ProfileRepository.java
    │   │   └── ProfileService.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/cachelab/
            ├── CacheKeysTest.java
            └── ProfileCacheIntegrationTest.java
```

Java public classes có file riêng trùng tên, package `com.example.cachelab`.

### 7.3. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>tenant-cache-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-redis</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.awaitility</groupId>
            <artifactId>awaitility</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Ý nghĩa:

- `starter-cache`: Spring Cache abstraction/AOP infrastructure.
- `starter-data-redis`: Redis connection factory, RedisCacheManager/provider, RedisTemplate.
- `starter-test`: JUnit Jupiter, AssertJ và Spring test.
- `spring-boot-testcontainers`: `@ServiceConnection` tạo Redis connection details cho test container.
- `testcontainers` + `junit-jupiter`: Docker container lifecycle/test integration.
- `awaitility`: bounded polling điều kiện hết hạn TTL, không dùng `Thread.sleep` cố định.

Spring Boot parent quản lý dependency versions tương thích. Không cần HTTP starter hoặc một Redis instance production.

### 7.4. `application.properties`

```properties
# src/main/resources/application.properties
spring.cache.type=redis
spring.cache.redis.time-to-live=30m
spring.cache.redis.cache-null-values=false
spring.cache.redis.use-key-prefix=true
```

Đây là cấu hình Redis cache provider cho project mẫu. Test integration sẽ override TTL xuống 4 giây để kiểm tra expiry. Cấu hình production thật phải chọn TTL theo loại dữ liệu, rủi ro stale và business policy; không lấy 30 phút làm giá trị mặc định cho mọi loại cache.

### 7.5. `CacheLabApplication.java`

```java
// src/main/java/com/example/cachelab/CacheLabApplication.java
package com.example.cachelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;

@SpringBootApplication
@EnableCaching
public class CacheLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheLabApplication.class, args);
    }
}
```

`@EnableCaching` quan trọng: không bật cache advice thì các `@Cacheable` annotations có thể không được intercept. Test hit/miss bên dưới sẽ phát hiện nếu quên annotation này.

### 7.6. `CacheKeys.java` — key contract có tenant + record, không mơ hồ

```java
// src/main/java/com/example/cachelab/CacheKeys.java
package com.example.cachelab;

public final class CacheKeys {

    private CacheKeys() {
    }

    public static String profile(
            String tenantId, String profileId) {
        requireId(tenantId, "tenantId", 32);
        requireId(profileId, "profileId", 64);

        return "v1:t:" + tenantId.length() + ":" + tenantId
                + ":p:" + profileId.length() + ":" + profileId;
    }

    private static void requireId(
            String id, String field, int maxLength) {
        if (id == null
                || id.length() > maxLength
                || !id.matches("[a-z0-9-]+")) {
            throw new IllegalArgumentException(
                    "Invalid " + field);
        }
    }
}
```

**Giải thích:**

- Key có schema version `v1` để quản lý thay đổi nghĩa/serialization.
- Có label `t`/`p`, length prefix và cả hai ID, tránh nhập nhằng khi phát triển key format.
- Validation chặn null, string rỗng, uppercase/các ký tự ngoài whitelist; không tự trim/normalize các identifiers đã cấp phát nếu chưa có policy thống nhất.
- Đây là **input shape validation**, không phải tenant authorization; user vẫn phải được xác minh quyền truy cập tenant.
- Cũng không dùng password/token vào cache key, vì Redis key names/logs có thể lộ.
- Với Spring RedisCacheManager mặc định, physical Redis key thêm prefix cache name `profiles::` trước logical key.

Không lấy `hashCode()` Java như một key toàn cục giữa versions/JVM cho dữ liệu cần không-collision; nếu cần hash để giảm độ dài, hãy dùng encoding/namespace và xác định collision risk/test vector rõ.

### 7.7. `ProfileRepository.java` — test-only data source

```java
// src/main/java/com/example/cachelab/ProfileRepository.java
package com.example.cachelab;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Repository;

@Repository
public class ProfileRepository {

    private record Id(String tenant, String profile) {
    }

    private final ConcurrentMap<Id, String> values =
            new ConcurrentHashMap<>();
    private final AtomicInteger loads = new AtomicInteger();

    public ProfileRepository() {
        reset();
    }

    public String find(String tenantId, String profileId) {
        loads.incrementAndGet();
        return values.get(new Id(tenantId, profileId));
    }

    public void update(
            String tenantId, String profileId, String value) {
        values.put(new Id(tenantId, profileId), value);
    }

    public int loadCount() {
        return loads.get();
    }

    public void reset() {
        values.clear();
        values.put(new Id("north", "42"), "NORTH-42");
        values.put(new Id("north", "43"), "NORTH-43");
        values.put(new Id("south", "42"), "SOUTH-42");
        loads.set(0);
    }
}
```

Repository dùng composite `Id(tenant,profile)` nên nguồn dữ liệu **đúng scope**; đây là thiết kế cho bài học chứ không phải persistence production. Nó giúp mô phỏng lỗi đặc biệt quan trọng: database trả dữ liệu đúng nhưng cache key không có tenant vẫn gây rò dữ liệu.

`loadCount()` là phép đo datasource calls, hữu ích để chứng minh cache hit thực. Test không chỉ so sánh return value vì hai giá trị trùng nhau đôi khi có thể che việc cache không hoạt động.

### 7.8. `ProfileService.java` — caching và eviction thống nhất key

```java
// src/main/java/com/example/cachelab/ProfileService.java
package com.example.cachelab;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {

    private final ProfileRepository repository;

    public ProfileService(ProfileRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
            cacheNames = "profiles",
            key = "T(com.example.cachelab.CacheKeys).profile(#p0,#p1)")
    public String get(String tenantId, String profileId) {
        return repository.find(tenantId, profileId);
    }

    @CacheEvict(
            cacheNames = "profiles",
            key = "T(com.example.cachelab.CacheKeys).profile(#p0,#p1)")
    public void update(
            String tenantId, String profileId, String value) {
        CacheKeys.profile(tenantId, profileId);
        repository.update(tenantId, profileId, value);
    }
}
```

**Cần hiểu:**

- `@Cacheable` key có cả tenant và profile; hai tenants có cùng profileId không share.
- `@CacheEvict` dùng **chính cùng key builder**; update north/42 không xóa south/42.
- Trước update, `CacheKeys.profile` validate input shape; nó không kiểm tra quyền sở hữu tenant.
- Khi `get` hit cache, repository không chạy. Do đó **không được đặt auth check chỉ bên trong `get` method** rồi tin nó luôn được gọi.
- Sample gọi từ test bean đã được Spring inject để thực sự đi qua cache AOP proxy.
- Spring `@Cacheable` trả null khi repo không tìm thấy; vì `cache-null-values=false`, không cache null theo provider policy mẫu. Production phải quyết định negative caching/missing data theo business/security semantics.

### 7.9. Ranh giới authorization bên ngoài cache — minh họa

Một service/facade production nên resolve tenant từ authenticated principal và kiểm tra membership **trước** khi gọi cached bean:

```java
// Snippet kiến trúc, không phải một file trong project mẫu:
public String profileForAuthenticatedUser(String profileId) {
    String tenantId = tenantResolver.requireAuthorizedTenant();
    return profileService.get(tenantId, profileId);
}
```

`tenantResolver` ở đây là service của ứng dụng thực, chưa được định nghĩa trong demo. Nó phải xác định tenant từ principal/claims đáng tin và verify permission. Không cho client truyền `X-Tenant-ID` tùy ý rồi bỏ qua membership. Nếu quyền thay đổi mà cached DTO chứa data phụ thuộc role, cần cache key phù hợp hoặc evict/refresh ngay theo policy.

## 8. Unit tests: contract của CacheKeys, không cần Docker

### 8.1. `CacheKeysTest.java`

```java
// src/test/java/com/example/cachelab/CacheKeysTest.java
package com.example.cachelab;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CacheKeysTest {

    @Test
    void differentTenantsNeverProduceSameKey() {
        String north = CacheKeys.profile("north", "42");
        String south = CacheKeys.profile("south", "42");

        assertThat(north).isNotEqualTo(south);
        assertThat(north).contains("north");
        assertThat(south).contains("south");
    }

    @Test
    void differentRecordsNeverProduceSameKey() {
        assertThat(CacheKeys.profile("north", "42"))
                .isNotEqualTo(
                        CacheKeys.profile("north", "43"));
    }

    @Test
    void rejectsMissingOrInvalidIdentifiers() {
        assertThatThrownBy(
                () -> CacheKeys.profile("", "42"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Invalid tenantId");

        assertThatThrownBy(
                () -> CacheKeys.profile("north", "bad:42"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Invalid profileId");
    }
}
```

**Ba methods** chỉ kiểm tra key composition/validation. Chúng không chứng minh RedisCacheManager dùng builder này đúng, không chứng minh TTL, không kiểm tra authorization. Những hợp đồng đó có integration tests riêng.

### 8.2. Lệnh chạy unit

```bash
mvn -B -ntp -Dtest=CacheKeysTest test
```

Không cần Docker hoặc một Redis server. Đây là source để học viên chạy; chưa phải kết quả test đã thực thi trong tài liệu.

## 9. Integration tests: Redis thật, cache hit/miss, TTL và tenant isolation

### 9.1. Redis container và Spring Boot 3.5 `@ServiceConnection`

Redis không cần một Testcontainers module riêng cho ví dụ này; dùng `GenericContainer`:

```java
@Container
@ServiceConnection(name = "redis")
static GenericContainer<?> redis =
        new GenericContainer<>("redis:7.4-alpine")
                .withExposedPorts(6379);
```

Tại sao chỉ rõ `name="redis"`?

- Spring Boot có Redis service connection factory match image name `redis`.
- `GenericContainer` không phải một container subclass chuyên Redis; `name="redis"` làm intent rõ và cũng hoạt động khi dùng `@Bean` generic container.
- `@ServiceConnection` cung cấp `RedisConnectionDetails` từ container, giúp auto-configured Redis client nối đúng mapped host/port.
- Test không dùng `localhost:6379` cố định. Trên CI Docker daemon/network có thể có topology khác.
- `@Container` start/stop theo JUnit class lifecycle, không tái sử dụng một Redis server production.

### 9.2. `ProfileCacheIntegrationTest.java`

```java
// src/test/java/com/example/cachelab/ProfileCacheIntegrationTest.java
package com.example.cachelab;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.cache.CacheManager;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@Testcontainers
@SpringBootTest(properties = {
        "spring.cache.type=redis",
        "spring.cache.redis.time-to-live=4s",
        "spring.cache.redis.cache-null-values=false",
        "spring.cache.redis.use-key-prefix=true"
})
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ProfileCacheIntegrationTest {

    @Container
    @ServiceConnection(name = "redis")
    static GenericContainer<?> redis =
            new GenericContainer<>("redis:7.4-alpine")
                    .withExposedPorts(6379);

    @Autowired
    ProfileService service;

    @Autowired
    ProfileRepository repository;

    @Autowired
    CacheManager cacheManager;

    @Autowired
    StringRedisTemplate redisStrings;

    @BeforeEach
    void resetIsolatedTestData() {
        // Chỉ an toàn vì container Redis này thuộc test.
        cacheManager.getCache("profiles").clear();
        repository.reset();
    }

    @Test
    void secondCallForSameTenantAndIdIsCacheHit() {
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");

        assertThat(repository.loadCount()).isEqualTo(1);
    }

    @Test
    void sameIdOfDifferentTenantsCannotShareValue() {
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(service.get("south", "42"))
                .isEqualTo("SOUTH-42");

        assertThat(repository.loadCount()).isEqualTo(2);

        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(repository.loadCount()).isEqualTo(2);
    }

    @Test
    void differentProfilesWithinTenantRemainSeparate() {
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(service.get("north", "43"))
                .isEqualTo("NORTH-43");

        assertThat(repository.loadCount()).isEqualTo(2);
    }

    @Test
    void updatingOneTenantEvictsOnlyItsEntry() {
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(service.get("south", "42"))
                .isEqualTo("SOUTH-42");
        assertThat(repository.loadCount()).isEqualTo(2);

        service.update("north", "42", "NORTH-42-v2");

        // south vẫn HIT: không gọi repository lại.
        assertThat(service.get("south", "42"))
                .isEqualTo("SOUTH-42");
        assertThat(repository.loadCount()).isEqualTo(2);

        // north đã bị evict: load lại dữ liệu mới.
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42-v2");
        assertThat(repository.loadCount()).isEqualTo(3);
    }

    @Test
    void entryHasTtlAndIsLoadedAgainAfterExpiration() {
        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(repository.loadCount()).isEqualTo(1);

        String redisKey = "profiles::"
                + CacheKeys.profile("north", "42");

        Long ttlMs = redisStrings.getExpire(
                redisKey, TimeUnit.MILLISECONDS);

        assertThat(ttlMs).isNotNull();
        assertThat(ttlMs).isPositive();
        assertThat(ttlMs).isLessThanOrEqualTo(4_000L);

        await()
                .atMost(Duration.ofSeconds(12))
                .pollInterval(Duration.ofMillis(100))
                .until(() -> Boolean.FALSE.equals(
                        redisStrings.hasKey(redisKey)));

        assertThat(service.get("north", "42"))
                .isEqualTo("NORTH-42");
        assertThat(repository.loadCount()).isEqualTo(2);
    }
}
```

**Giải thích kiểm thử:**

- Mỗi test reset in-memory repository và xóa cache `profiles` trong **Redis container test-only**. Không làm điều này trên Redis dùng chung với jobs/người dùng khác.
- Test `secondCall...` chứng minh Spring AOP thực sự intercept: lần thứ hai không gọi repository.
- `sameIdOfDifferentTenants...` là **assertion chống cross-tenant leakage**: cùng ID 42 nhưng values khác nhau.
- `differentProfiles...` bảo vệ dimension record ID trong cùng tenant.
- `updatingOneTenant...` chứng minh invalidation của north không xóa hoặc làm reload cache của south.
- `entryHasTtl...` kiểm tra **physical Redis PTTL** và đợi key hết hạn rồi load lại. Không chỉ nhìn `spring.cache.redis.time-to-live` trong file.
- `@DirtiesContext(AFTER_CLASS)` tránh context caching kéo dài hơn lifecycle của class-scoped Redis container. Với nhiều test classes chia sẻ Spring context, cân nhắc context-managed container bean.
- Các tests không bật parallel methods; trong môi trường parallel, `@BeforeEach cache.clear()` có thể race với method khác, nên dùng namespace/cache riêng per test hoặc không clear shared scope.

### 9.3. Vì sao không assert TTL chính xác 4000ms?

Thời gian đã trôi giữa lệnh Redis SET của cache provider và thời điểm test gọi `getExpire`. Kết quả có thể còn 3990ms, 3800ms, v.v. Test kiểm tra `ttlMs > 0` và `ttlMs <= 4000`, rồi bounded-await đến expiration. Nếu cache không có expiry, Redis trả `-1`; nếu key chưa tồn tại/đã mất, trả `-2`, cả hai đều fail assertion.

Nếu CI quá chậm tới mức 4 giây đã trôi trước khi đo TTL, test có thể flaky; khi đó tăng TTL test lên 8–15 giây hoặc tách configuration TTL riêng cho test này, không dùng retry vô hạn để che vấn đề. Bài mẫu chọn 4 giây để dễ quan sát; môi trường CI khác nhau cần sizing thực.

### 9.4. Tại sao cần test Redis thật?

Pure unit test có thể chứng minh `CacheKeys.profile` tạo key khác nhau, nhưng không chứng minh:

- Spring `@Cacheable` có thực sự chạy qua proxy.
- `RedisCacheManager` được chọn thay vì SimpleCacheManager/NoOpCacheManager.
- Redis physical key có cache-name prefix và entry TTL.
- Eviction dùng cùng key với lookup.
- Serialization và connection details hoạt động.
- Cache hit tránh datasource call và expiry load lại.

Khi một trong các điều ấy sai, Redis Testcontainers integration sẽ giúp tìm lỗi thật.

## 10. Chạy Maven và CI

### 10.1. Lệnh chạy

```bash
java -version
mvn -version

# Pure unit tests:
mvn -B -ntp -Dtest=CacheKeysTest test

# Redis integration:
docker version
docker info
mvn -B -ntp -Dtest=ProfileCacheIntegrationTest test

# Tất cả 8 test methods:
mvn -B -ntp test
```

Theo source code:

| Test class | JUnit `@Test` count | Cần Docker? |
| --- | ---: | --- |
| `CacheKeysTest` | 3 | Không |
| `ProfileCacheIntegrationTest` | 5 | Có |
| **Tổng** | **8** | Full suite cần Docker |

Đây là các lệnh người học tự chạy, **không phải một báo cáo rằng source đã được biên dịch hoặc chạy thành công** trong môi trường soạn tài liệu. Lần đầu Docker có thể phải pull image Redis và Maven có thể tải dependencies.

### 10.2. GitHub Actions minh họa

```yaml
name: Tenant Cache Integration

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  tests:
    runs-on: ubuntu-24.04
    timeout-minutes: 20

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Check Docker daemon
        run: |
          docker version
          docker info --format 'Engine={{.ServerVersion}}'
      - name: Run all tests
        run: mvn -B -ntp test
      - name: Upload reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: cache-surefire
          path: target/surefire-reports/
          if-no-files-found: ignore
```

- `contents: read` giới hạn quyền GitHub API token, **không** cấp Docker socket permissions.
- Runner cần Docker-compatible daemon, quyền tạo Redis container, image registry reachability, CPU/RAM/disk đủ.
- `@ServiceConnection(name="redis")` giúp lấy host/port động, tránh `localhost:6379` cố định.
- Không chạy `docker system prune --volumes` trên shared runner. Không tắt Testcontainers Ryuk chỉ để đạt pipeline xanh.
- Nếu Docker không available, mandatory integration job phải báo **ENVIRONMENT FAIL**, không silently skip và không dùng `mvn test || true`.
- Với supply-chain-sensitive repository, pin Actions theo reviewed commit SHAs thay vì chỉ movable version tags.

### 10.3. Vì sao container test cần dọn đúng cách?

Một `@Container` static được JUnit Testcontainers extension start/stop theo class. Spring TestContext đôi khi cache bean RedisConnectionFactory lâu hơn class; nếu test class khác reuse context trỏ stopped container, sẽ xảy ra connection refused.

Trong demo có một integration class và `@DirtiesContext(AFTER_CLASS)`. Ở suite lớn cần chọn container bean sống theo Spring context hoặc mô hình shared static container có lifecycle đúng, không reuse container từ lần CI trước nếu muốn isolation.

## 11. Lỗi thường gặp và cách tự chẩn đoán

### 11.1. Chỉ dùng recordId làm key trong multi-tenant service

**Sai:**

```java
@Cacheable(cacheNames = "profiles", key = "#profileId")
public String get(String tenantId, String profileId) { ... }
```

**Hậu quả:** north/42 và south/42 cùng physical key `profiles::42`. Spring cache có thể trả giá trị tenant north cho tenant south mà không gọi repository, dù SQL gốc đúng.

**Sửa:** Key phải chứa tenant scope + record ID (và user/policy context nếu response thực sự khác), như `CacheKeys.profile`.

### 11.2. Cho user truyền tenant ID tùy ý

Ngay cả key có tenant chính xác, caller có thể yêu cầu tenant khác nếu security layer không kiểm tra. Không dùng cache key như authentication. Resolve tenant từ trusted principal hoặc kiểm tra membership/authorization trước cache interception.

### 11.3. Check quyền trong method đã `@Cacheable`

Cache hit sẽ bỏ qua method body. Nếu authorization logic chỉ ở đó, một hit có thể né check. Thiết kế authorization facade/security advice đúng thứ tự, và viết tests cho authorized/unauthorized user cùng record ID.

### 11.4. Cache auth-filtered view nhưng key thiếu user/role

Hai người cùng tenant có thể có view khác nhau. Nếu cached value là DTO đã lọc theo quyền, key cũng cần user/role/policy version hoặc thiết kế lại để filter sau cache trên trusted raw data. Invalidate khi quyền/consent thay đổi.

### 11.5. Quên bật `@EnableCaching`

Có `@Cacheable` trên method nhưng không có AOP cache advice, mỗi lần gọi đều chạy repository. Unit key test vẫn xanh; integration `loadCount` sẽ phát hiện.

### 11.6. Self-invocation `this.get(...)`

Gọi cached method nội bộ cùng bean thường bỏ qua Spring proxy. Đặt call qua một Spring-injected bean khác hoặc refactor adapter/service; đừng dựa vào annotation tác dụng khi gọi bằng `this`.

### 11.7. Cache name prefix bị tắt

Dùng một Redis database cho nhiều caches mà disabled key prefix có thể gây collisions. Giữ `use-key-prefix=true` trừ khi có chiến lược namespacing tương đương và tests xác nhận.

### 11.8. Tưởng `@Cacheable` tự có TTL

Spring Cache abstraction không định nghĩa expiration chung; muốn TTL phải cấu hình RedisCacheManager/Caffeine/Ehcache provider. Redis `PTTL=-1` cho thấy entry không có expiry; không tuyên bố TTL active chỉ vì đặt annotation.

### 11.9. TTL đã hết nhưng service vẫn trả dữ liệu cũ

Có thể service dùng một cache khác (Caffeine/local L1), DB source stale, key không đúng, test đang đọc key sai, hoặc provider config không phải Redis. Kiểm tra cache manager bean, physical Redis key, TTL và datasource calls.

### 11.10. TTL quá ngắn khiến test CI flaky

Nếu TTL chỉ 100ms và runner tải nặng, cache hit test có thể hết hạn ngay trước lần thứ hai. Sử dụng TTL dài đủ cho hit/isolation tests, còn expiry test dùng bounded await theo TTL thực và có timeout tương xứng. Không dùng fixed `Thread.sleep` với assumption chính xác từng millisecond.

### 11.11. Update không xóa đúng key

`@Cacheable` key chứa tenant+id nhưng `@CacheEvict` key chỉ chứa id hoặc nhầm cache name. Kết quả stale data tới hết TTL. Dùng một key builder chung, test update một tenant và xác nhận tenant khác không bị evict.

### 11.12. `@CacheEvict(allEntries=true)` xóa cả tenants

All-entries eviction tác động toàn cache, không chỉ tenant hiện hành. Trong shared Redis sẽ ảnh hưởng mọi tenant thuộc cache đó. Chỉ dùng khi business cần global reset và đã hiểu cost/consistency.

### 11.13. Cache null, empty/error responses mà không có policy

Negative caching có thể giúp hiệu năng nhưng khiến record mới tạo hoặc quyền vừa cấp vẫn bị trả absent; cache unauthorized response có thể chứa thông tin nhạy cảm/stale. Chọn explicit null/empty policy; không cache exception một cách tùy tiện; kiểm tra khi data vừa được tạo hoặc permission changed.

### 11.14. Global Redis flush trong `@BeforeEach`

`FLUSHDB`/`FLUSHALL` hoặc `cache.clear()` trên shared Redis xóa dữ liệu khác, gây race với parallel jobs. Trong sample chỉ clear một cache **trên container do test sở hữu**. Ứng dụng thật nên tách database/container/key namespace và cleanup scoped.

### 11.15. Redis key chứa PII hoặc secret

Cache keys có thể xuất hiện trong CLI, logs, metrics và backups. Không đưa access token/password/raw email vào key nếu không có lý do và bảo vệ phù hợp. Dùng stable opaque IDs hoặc keyed hash khi phù hợp với security model.

### 11.16. Tưởng cache isolation thay database RLS

Cache scope và database tenant filter/RLS là **hai lớp độc lập**. Test cả SQL row-level authorization lẫn cache key separation. Một trong hai đúng chưa bảo đảm lớp còn lại an toàn.

### 11.17. Test chỉ chạy một tenant

Nếu test không đưa cùng record ID ở hai tenants khác nhau, rất khó phát hiện key bỏ tenant. Thiết kế fixture cố ý **same ID, different values** và gọi theo cả thứ tự north→south lẫn south→north trong một bộ test rộng hơn.

### 11.18. Context caching và container lifecycle

Nếu Spring context được cache sau khi Redis Testcontainers static field stop, cache manager/connection factory có thể trỏ host port cũ. Dùng `@DirtiesContext` có chủ đích hoặc context-managed Testcontainers bean, không fix bằng retry mãi.

### 11.19. Cache stampede sau expire

Nhiều requests cùng miss có thể chạm DB đồng thời. `@Cacheable(sync=true)` không tự đảm bảo distributed locking trên mọi nodes/providers. Nếu có SLA và high load, test concurrency/locking theo provider thực tế và đo DB load.

## 12. Kiểm tra các case đặc biệt về bảo mật và lifecycle

### 12.1. Token/tenant switching trong cùng session

Một user có quyền đổi tenant trong UI. Nếu cache key dựa trên userId nhưng không dựa trên tenant, sau khi switch có thể nhận data tenant cũ. Test phải làm request trong cùng authenticated session với tenant A→B, dùng same record ID và chứng minh cache không bị share.

### 12.2. Role downgrade hoặc membership revoke

Ví dụ một admin từng xem profile đầy đủ, sau đó quyền bị thu hồi. Nếu cache vẫn trả authorized view cũ, TTL còn vài phút có thể vượt chính sách bảo mật. Giải pháp phụ thuộc thiết kế: authorization trước cache, cache version key theo permission, invalidate khi revoke, hoặc không cache những views nhạy cảm.

### 12.3. Tenant deletion/migration

Khi tenant bị khóa/xóa/di chuyển shard, cache entries cũ không được “sống tiếp” tạo phantom data. Cần purge **scoped to tenant** hoặc dùng namespace/version để key cũ không còn được lookup. Không dùng toàn Redis FLUSHALL.

### 12.4. Cache schema/version rollover

Triển khai mới thay object serialization hoặc nghĩa của key. Nếu không version keys hoặc xóa cache theo rollout, có thể deserialize fail hoặc trả data theo format cũ. Schema prefix `v1` giúp migration có kế hoạch; thực tế cần test compatibility/backfill/evict behavior.

### 12.5. Shared cache với nhiều ứng dụng

Một Redis cluster có thể được dùng bởi nhiều apps/environments. Prefix cache name chỉ là một phần. Thêm environment/app namespace qua cache prefix config nếu cần; bảo đảm test/prod không dùng cùng credentials/Redis DB mà vô tình đọc keys của nhau.

### 12.6. TTL và event ordering

Một update liên tiếp có thể tạo race: request cũ load DB, update DB và evict, request cũ hoàn tất và put stale value vào Redis. TTL giới hạn thời gian stale, không loại trừ race. Với dữ liệu quan trọng có thể cần versioned keys, compare-and-set, eviction sequencing, DB version checks hoặc avoid caching theo risk; test concurrency thực khi cần.

### 12.7. Cache provider tự động có đúng không?

Spring Boot lựa chọn cache provider dựa trên dependencies/config. Nếu project có nhiều providers, kiểm tra `CacheManager` được chọn thật, không dựa vào tên dependency. `spring.cache.type=redis` trong ví dụ làm ý định rõ và integration test kiểm tra physical Redis key.

### 12.8. Spring test slices không phải full caching integration

`@DataRedisTest` tập trung một slice Redis và có thể không nạp `@EnableCaching`/service AOP theo cùng cách full app. Nó tốt để test repositories/Redis ops; để kiểm tra `@Cacheable` trên service cùng cache manager/config thực, `@SpringBootTest` như ví dụ minh bạch hơn. Nếu dùng slice, cần explicit `@Import` và tests xác minh proxy/cache setup.

## 13. Checklist trước khi merge code có cache đa tenant

- [ ] Mọi value có dữ liệu tenant/user đều có key scope tương ứng.
- [ ] Tenant ID được lấy từ trusted authenticated context, không chỉ từ client header.
- [ ] Authorization chạy **trước cache hit**, không chỉ trong body của cached method.
- [ ] Cache keys không trộn tenant A/B với cùng record ID.
- [ ] User/role/policy/locale/filter dimensions được xét nếu value phụ thuộc chúng.
- [ ] Cache name prefix và app/env namespace hợp lệ trên shared Redis.
- [ ] `@Cacheable`/`@CacheEvict`/`@CachePut` dùng key contract nhất quán.
- [ ] `@EnableCaching` và provider CacheManager được bật/chọn đúng.
- [ ] Spring proxy/self-invocation behavior được hiểu/test rõ.
- [ ] Redis TTL được cấu hình bằng provider và kiểm tra `PTTL > 0`.
- [ ] Expiration test dùng bounded await thay fixed sleeps.
- [ ] Data updates, deletes, permission revokes có invalidation policy đúng SLA.
- [ ] Null/negative caching có quyết định rõ, không vô tình giữ permission denied responses.
- [ ] Cache values/keys không lộ secrets/PII không cần thiết.
- [ ] Redis ACL/TLS và environment separation được thiết lập trong production.
- [ ] Tenant-scoped database access cũng được test độc lập.
- [ ] Integration tests có fixtures same-ID-different-tenants.
- [ ] Tests không dùng `FLUSHDB`/`FLUSHALL` trên shared Redis.
- [ ] CI có Docker daemon/port mapping và không skip mandatory Redis tests.
- [ ] Context cache và Redis Testcontainers lifecycle không để stale connections.
- [ ] Load/concurrency tests được thêm khi stampede/cross-node consistency có rủi ro.
- [ ] QA báo đúng unit, integration, environment failure và skipped.

## 14. Bài tập thực hành

**Bài 1 — Tạo lỗi có kiểm soát.** Trong một nhánh demo riêng, đổi key của `ProfileService.get` thành `key="#p1"`. Chạy test cross-tenant để quan sát kết quả sai. Khôi phục key builder tenant-scoped và xác nhận test xanh. Không đưa biến thể sai lên production.

**Bài 2 — Thêm user scope.** Cho hai users trong cùng tenant nhận các authorized views khác nhau. Thiết kế key có user hoặc policy version nếu cache DTO đã filter theo quyền. Viết test để role A không thể hit role B view.

**Bài 3 — Đổi TTL.** Thử `spring.cache.redis.time-to-live=8s` trong test. Đọc `getExpire` sau write, chờ bounded expiration và xác minh repository load lần nữa. Giải thích vì sao assert TTL chính xác 8000ms dễ flaky.

**Bài 4 — Evict đúng tenant.** Update north/42, xác minh south/42 vẫn hit cache và north/42 reload value mới. Thử cố ý dùng eviction key thiếu tenant để thấy stale data.

**Bài 5 — Security boundary.** Thiết kế một API dùng authenticated principal để resolve tenant. Test một user thuộc north nhưng cố gửi header `X-Tenant-ID: south`; API phải từ chối hoặc bỏ qua giá trị untrusted, không bao giờ tra cache của south.

**Bài 6 — Data delete & privilege revoke.** Thu hồi quyền user đang có cached authorized view; xác định business rule yêu cầu invalidate ngay hay chấp nhận TTL tối đa và viết test tương ứng.

**Bài 7 — Cache name collision.** Tạo cache `profiles` và `summaries` có cùng logical key. Bật/tắt key prefix trong broker test riêng; chứng minh namespace collision khi cấu hình sai.

**Bài 8 — CI isolation.** Chạy hai integration jobs song song dùng Redis Testcontainers riêng; bảo đảm không có global `FLUSHALL` và containers tự cleanup. Xác định Docker host/port mapping nếu Maven chạy trong Docker executor.

**Bài 9 — Transaction rollback.** Tạo update transactional DB test-only rồi gây rollback; đánh giá thứ tự `@CacheEvict` so với transaction commit và thiết kế after-commit invalidation nếu cần.

**Bài 10 — Multi-node miss storm.** Mô phỏng nhiều requests đồng thời sau expiration, đo repository load count; đánh giá `sync=true`, provider locking và các chiến lược chống stampede theo constraints.

## 15. Câu hỏi tự kiểm tra

**1.** Tại sao `key="#profileId"` có thể nguy hiểm trong multi-tenant service?  
**Đáp án:** Nhiều tenants có cùng record ID sẽ dùng một cache entry, gây cross-tenant leakage khi hit.

**2.** Cache key có tenant đã thay thế authorization chưa?  
**Đáp án:** Chưa; tenant phải được xác thực/ủy quyền trước khi cache lookup.

**3.** Nếu kiểm tra quyền chỉ trong `@Cacheable` method body thì rủi ro gì?  
**Đáp án:** Cache hit có thể bỏ qua method body, nên check không chạy.

**4.** Mặc định `SimpleKeyGenerator` có chứa các method arguments không?  
**Đáp án:** Có; nhưng nếu tenant không phải argument hoặc dùng explicit key bỏ tenant, vẫn dễ collision.

**5.** Cache name prefix `profiles::` có tự thêm tenant không?  
**Đáp án:** Không. Nó chỉ tách cache names; cần tenant trong logical key.

**6.** `@Cacheable` có thuộc tính `ttl` mặc định cho mọi provider không?  
**Đáp án:** Không. TTL được cấu hình ở Redis/Caffeine/Ehcache hoặc cache manager thích hợp.

**7.** Redis `PTTL=-1` nói gì?  
**Đáp án:** Key tồn tại nhưng không có expiration; `-2` là key không tồn tại.

**8.** TTL có được kéo dài sau mỗi cache GET không?  
**Đáp án:** Không theo TTL thông thường; time-to-idle cần semantics/config khác.

**9.** Tại sao update north/42 không nên clear toàn bộ profiles cache?  
**Đáp án:** Vì sẽ gây eviction cả tenants khác; đúng hơn là evict chỉ scoped key của north/42.

**10.** Tại sao một pure unit test key builder chưa chứng minh Redis integration an toàn?  
**Đáp án:** Nó chưa chạy Spring proxy, cache manager, Redis physical prefixes/TTL/eviction.

**11.** Tại sao `StringRedisTemplate.getExpire` tốt hơn chỉ đọc property TTL?  
**Đáp án:** Nó quan sát expiry được ghi thật trên provider, bắt được config không áp dụng.

**12.** Redis Testcontainers có tự giải quyết client-supplied tenant spoofing không?  
**Đáp án:** Không. Broker test bảo vệ behavior cache; security boundary phải được kiểm chứng riêng.

## 16. Tài liệu chính thức

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): CacheManager, proxy semantics, caching advice.
- [Spring Framework — Declarative Annotation-Based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, key SpEL, `@CacheEvict`, default key generation.
- [Spring Boot 3.5 — Caching](https://docs.spring.io/spring-boot/3.5/reference/io/caching.html): Redis cache auto-configuration, `spring.cache.redis.time-to-live` và key prefix.
- [Spring Boot 3.5 — Testcontainers Service Connections](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection(name="redis")` trên GenericContainer.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data-redis/reference/redis/redis-cache.html): RedisCacheManager, TTL, serialization, key prefix, invalidation behavior.
- [Spring Data Redis — RedisCacheConfiguration](https://docs.spring.io/spring-data/redis/docs/3.5.x/api/org/springframework/data/redis/cache/RedisCacheConfiguration.html): `entryTtl`, null value policy, prefixes.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers` và `@Container` lifecycle.
- [Redis — EXPIRE and TTL](https://redis.io/docs/latest/commands/ttl/): Redis expiration return codes.
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/): millisecond expiration.
- [Redis — GETEX](https://redis.io/docs/latest/commands/getex/): key read with expiration update, liên quan TTI.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): authorization boundaries, advice và policy checking.

**Kết luận:** Cache đa tenant là phần của correctness **và** bảo mật, không chỉ hiệu năng. Key phải chứa mọi dimension quyết định giá trị trả về, nhất là tenant/user/record; tenant identity phải được xác thực trước cache lookup. TTL cần được cấu hình và **đo trên cache provider**, không chỉ ghi trong tài liệu. Việc evict phải dùng chính key contract của lookup. Kết hợp pure key-builder unit tests với Spring AOP + Redis Testcontainers integration tests để bảo vệ cache hits, cross-tenant isolation, expiry và invalidation; dùng authorization tests riêng cho security boundary.