# Kiểm chứng quyền tối thiểu cho cache, Repository và listener

Trong **Spring Data Redis**, một tài khoản Redis kết nối thành công và gọi `PING` được chưa chắc đã có quyền thực hiện toàn bộ hoạt động của ứng dụng. Một request `@Cacheable` có thể đọc được cache nhưng `@CacheEvict(allEntries = true)` bị từ chối; một Redis Repository có thể lưu entity nhưng không cập nhật được secondary index; một Redis Stream consumer có thể nhận event nhưng không được `XACK`; hoặc một Pub/Sub listener được tạo thành công nhưng không thể subscribe vào channel keyspace notification.

Đó là lý do **kiểm chứng quyền tối thiểu (least privilege)** không dừng ở việc tạo ACL user rồi thử `GET`. Ta cần liệt kê các đường đi Redis **thực tế** của từng thành phần Spring, cấp đúng quyền theo **command, key pattern và channel pattern**, sau đó chạy cả kiểm thử được phép lẫn kiểm thử bị từ chối. Đặc biệt, phải kiểm chứng các thao tác ít xảy ra như cache clear, entity expiration, Stream reclaim và reconnect sau failover.

Bài học hướng dẫn cách xây dựng permission contract và bộ kiểm thử an toàn cho ba nhóm:

1. **Spring Cache** dùng `RedisCacheManager` và `RedisCacheWriter`.
2. **Spring Data Redis Repository** dùng Redis Hash, ID, index và expiration.
3. **Listener** gồm Pub/Sub, keyspace notification và Redis Streams consumer/producer.

Các ví dụ hướng tới Redis có **ACL** (Redis 6 trở lên; một số khả năng như `ACL DRYRUN`, quyền đọc/ghi key chi tiết tùy phiên bản). Cấu hình phải được đối chiếu với Redis server, Spring Boot, Spring Data Redis và Lettuce thực tế trong dự án. Tất cả thao tác quản trị ACL trong bài chỉ nên thử trên Redis lab/staging do bạn kiểm soát.

## 1. Quyền tối thiểu nghĩa là gì trong Redis?

Redis ACL kiểm soát nhiều chiều độc lập:

- **User identity:** client đã xác thực với user nào, user có ở trạng thái `on` không.
- **Command permission:** user được gọi `GET`, `SET`, `DEL`, `HSET`, `XREADGROUP`, `SUBSCRIBE`… hay không.
- **Key permissions:** command được phép thao tác những Redis key nào theo pattern đã cấp.
- **Pub/Sub channel permissions:** client được publish/subscribe trên channel nào.
- **Read/write key permissions:** các Redis phiên bản hỗ trợ có thể phân biệt key pattern được đọc/ghi.
- **Lệnh quản trị:** ACL, CONFIG, FLUSH*, CLUSTER và các thao tác nhạy cảm thường cần tách khỏi application user.

Ví dụ một user chỉ phục vụ cache sản phẩm có thể cần quyền với namespace `svc:cache:products::*` nhưng **không** cần quyền đọc session của service khác, không cần `CONFIG SET` và không cần xóa toàn bộ Redis database.

```text
                   Ứng dụng Spring
                          |
                          v
                Redis AUTH app_cache
                          |
                          v
        +-----------------+------------------+
        |                 |                  |
   COMMAND ACL        KEY PATTERN       CHANNEL ACL
        |                 |                  |
     GET/SET/DEL     svc:cache:*           (không cần)
        |
        v
     Cho phép hoặc từ chối từng command thực tế
```

**Một quyền đúng phải vừa đủ để workflow chạy, nhưng không cho phép vượt namespace hoặc thực hiện thao tác không nằm trong trách nhiệm của workflow.**

## 2. Ba nhóm lỗi bảo mật cần phân biệt

| Redis error | Ý nghĩa | Hướng điều tra |
|---|---|---|
| `NOAUTH Authentication required` | Command được gửi mà chưa xác thực phù hợp | Credentials, handshake, connection factory |
| `WRONGPASS invalid username-password pair or user is disabled` | Username/password không hợp lệ hoặc user bị vô hiệu hóa | Secret, rotation, ACL user state |
| `NOPERM ... command ...` | User đã xác thực nhưng thiếu quyền chạy command | Command allowlist/category |
| `NOPERM ... key ...` | Command dùng Redis key nằm ngoài quyền được cấp | Key pattern, serializer, namespace |
| `NOPERM ... channel ...` | Pub/Sub channel bị chặn | Channel pattern và subscribe/publish permissions |
| `READONLY ... replica` | Đang ghi vào node chỉ đọc | Primary/replica routing, không phải ACL |
| `OOM ... maxmemory` | Redis không thể cấp phát theo memory policy | Dữ liệu/TTL/capacity, không phải ACL |
| `CROSSSLOT` | Các key của command không đáp ứng hash slot | Thiết kế key/Cluster, không phải ACL |

Không nên bắt toàn bộ `DataAccessException` rồi retry nhiều lần. `NOPERM` là kết quả từ chối có chủ đích; retry cùng user/quyền/command không tự thay đổi kết quả.

## 3. Quy trình kiểm chứng theo hành vi thật

Một quy trình nên đi theo chiều từ workflow sang ACL, thay vì bắt đầu bằng `+@all` rồi gỡ dần theo cảm tính:

1. **Liệt kê các nghiệp vụ Redis** mà ứng dụng thực hiện: cache hit, cache miss, cache put, evict, clear, Repository save/delete/find/index, listener subscribe/ACK/reclaim.
2. **Xác định key/channel namespaces thực tế**, kể cả key do framework sinh ra.
3. **Xác định Redis commands** của mỗi đường đi, bằng tài liệu API, logs/traces và chạy thử ở môi trường cô lập.
4. **Nhóm theo identity**: cache user, repository user, stream producer, stream consumer, Pub/Sub listener, operator.
5. **Tạo allowlist tối thiểu** cho từng identity trên Redis lab.
6. **Chạy positive tests**: các workflow hợp lệ phải thành công.
7. **Chạy negative tests**: command ngoài hợp đồng, key ngoài namespace, channel khác phải bị từ chối.
8. **Kiểm chứng rare paths**: cache clear, Repository index cleanup, expiration, listener reconnect/reclaim, failover.
9. **So sánh quyền cấp và quyền thực sự cần**, thu hẹp phần dư.
10. **Chốt bản quyền có version, ownership và quy trình rotation**, chạy lại permission tests khi nâng Redis/Spring Data Redis hoặc đổi tính năng.

```text
Workload inventory
       |
       v
Command + Key + Channel contract
       |
       v
ACL allowlist cho từng service principal
       |
       +--> Positive tests: chức năng được phép chạy
       |
       +--> Negative tests: vượt quyền bị chặn
       |
       v
Observability + regression tests + controlled rollout
```

Không nên lấy việc `PING` thành công hoặc một API trả 200 làm bằng chứng quyền đã đủ: service có thể trả dữ liệu từ cache hit mà chưa từng đi qua quyền ghi, hoặc fallback che một lỗi ACL.

## 4. Bảng phân quyền khởi đầu cho ba thành phần

| Thành phần | Các command thường liên quan | Key/channel liên quan | Kiểm thử quan trọng |
|---|---|---|---|
| `@Cacheable` hit | `GET` | Cache key theo cache name/prefix | Hit được đọc đúng |
| `@Cacheable` miss + cache fill | `GET`, `SET` | Cache key | Miss tải nguồn và ghi cache |
| `@CachePut` | `SET` và TTL option | Cache key | Update cache có TTL |
| `@CacheEvict` theo key | `DEL` hoặc lệnh xóa tương đương | Cache key | Key bị xóa |
| `@CacheEvict(allEntries=true)` | `KEYS` hoặc `SCAN`, `DEL`/`UNLINK` tùy writer | Namespace theo cache | Clear không bị NOPERM |
| Cache put-if-absent | `SET` với NX/PX hoặc đường tương đương | Cache key | Không overwrite khi key có sẵn |
| Repository `save` | `HSET`, `DEL`, `SADD`, `SREM`, `EXPIRE`… tùy mapping | Hash, index, metadata, TTL keys | Save, index update, TTL |
| Repository `findById` | `HGETALL` hoặc Hash reads | Entity hash | Mapping đọc đúng |
| Repository `delete` | `DEL`, index set cleanup… | Hash + index keys | Không để index mồ côi |
| Repository query indexed | `SMEMBERS`/Set reads và Hash reads | Secondary index + entity keys | Query ra đúng entity |
| Pub/Sub listener | `SUBSCRIBE`/`PSUBSCRIBE` | Channel ACL `&...` | Chỉ nhận channel được phép |
| Pub/Sub publisher | `PUBLISH` | Channel ACL | Chỉ publish được channel cho phép |
| Keyspace event listener | `PSUBSCRIBE` hoặc `SUBSCRIBE` | `__keyevent@0__:expired`... | Nhận expiration đúng scope |
| Stream producer | `XADD`, đôi khi `XTRIM` | Stream key | Ghi message/retention |
| Stream group consumer | `XREADGROUP`, `XACK` | Stream key | Đọc và ACK đúng |
| Stream recovery | `XPENDING`, `XAUTOCLAIM`/`XCLAIM` | Stream key/group | Claim pending sau crash |
| Stream bootstrap | `XGROUP`/`XINFO`... | Stream key | Group tồn tại hoặc được tạo đúng |

Đây là **bản đồ bắt đầu**, không phải allowlist có thể sao chép nguyên xi cho mọi application. RedisCacheWriter, repository mapping, serializer, listener mode và Redis server version có thể thay đổi command thực tế.

## 5. Cách đọc cú pháp Redis ACL

Trong Redis ACL, những token phổ biến gồm:

| ACL token | Ý nghĩa khái quát |
|---|---|
| `on` / `off` | Bật/tắt user |
| `>password` | Thêm password cho user theo cách của Redis ACL |
| `+get`, `+set` | Cho phép command cụ thể |
| `-get`, `-@all` | Thu hồi command/nhóm command |
| `+@read`, `+@write` | Cho phép nhóm command theo ACL category |
| `~svc:cache:*` | Cho phép key theo glob pattern |
| `resetkeys` | Xóa key patterns đã cấp |
| `resetchannels` | Xóa channel patterns đã cấp |
| `&svc:events:*` | Cho phép Pub/Sub channel pattern |
| `%R~pattern`, `%W~pattern` | Quyền đọc/ghi key chi tiết ở Redis version có hỗ trợ |
| `reset` | Khôi phục nhiều thiết lập user về cấu hình hạn chế, cần kiểm tra lại mọi thuộc tính |

**Key rules và channel rules là hai cơ chế khác nhau.** Cấp `~svc:events:*` cho Redis keys không tự cấp quyền subscribe `svc:events:updated`. Ngược lại, cấp `&svc:events:*` cho channels không cấp quyền đọc Redis key trùng tên.

### Category có thể rộng hơn mong đợi

`+@read` hoặc `+@write` thuận tiện nhưng có thể cấp nhiều Redis commands ngoài phạm vi thực sự cần. Với service cần bảo vệ chặt, thường ưu tiên **explicit command allowlist** rồi mở thêm những lệnh có bằng chứng từ workflow.

Không đồng nhất Redis ACL với authorization nghiệp vụ: Redis cho phép `GET svc:session:*` không có nghĩa ứng dụng đã xác thực user thật hoặc kiểm tra đúng tenant. ACL là một lớp phòng vệ ở hạ tầng.

## 6. Tạo user lab theo nguyên tắc tối thiểu

**Chỉ dùng Redis lab riêng.** Các lệnh ACL SETUSER cần một tài khoản quản trị đã được phép và nên nhập trong Redis CLI interactive session để tránh ký tự `>` bị shell hiểu thành chuyển hướng output.

Ví dụ tạo một user chỉ thao tác cache lab:

```text
ACL SETUSER lab_cache reset on >CHANGE_THIS_LAB_PASSWORD ~lab:cache:* +ping +get +set +del
ACL GETUSER lab_cache
ACL DRYRUN lab_cache GET lab:cache:products::42
ACL DRYRUN lab_cache SET lab:cache:products::42 value
ACL DRYRUN lab_cache DEL lab:cache:products::42
```

Đây là user **chưa đủ cho mọi cache writer**: nếu ứng dụng dùng `SCAN` hoặc `KEYS` để clear, các command đó vẫn bị từ chối.

Kiểm chứng âm:

```text
ACL DRYRUN lab_cache GET lab:session:42
ACL DRYRUN lab_cache HSET lab:cache:products::42 field value
ACL DRYRUN lab_cache XADD lab:events * type Demo
```

Kỳ vọng các command/key ngoài allowlist bị từ chối.

`ACL DRYRUN` là công cụ có trong Redis version hỗ trợ (Redis 7 trở lên). Với phiên bản cũ, có thể thử bằng connection xác thực dưới user lab trong môi trường cô lập. **DRYRUN mô phỏng kiểm tra quyền, không thực thi command và không thay thế kiểm thử workflow end-to-end.**

## 7. Kiểm tra user thực tế mà Spring đang dùng

Trong Spring Boot, credentials Redis thường được inject qua environment/secret manager:

```yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      username: app_cache
      password: "INJECT_FROM_SECRET_MANAGER"
      connect-timeout: 2s
      timeout: 3s
      ssl:
        enabled: true
```

`INJECT_FROM_SECRET_MANAGER` chỉ là ký hiệu minh họa; password thật không được hard-code trong file commit lên source control. Tham số Redis property phải phù hợp Spring Boot version đang chạy.

Một app có thể có nhiều `RedisConnectionFactory`/RedisTemplate khác nhau. Việc đặt một username ở `application.yml` không chứng minh **mọi Redis bean** đang dùng user đó nếu một factory khác được tạo thủ công.

Dùng Redis CLI qua cùng mạng và account để xác minh trong môi trường an toàn:

```bash
redis-cli -h redis.internal -p 6379 --user app_cache --askpass ACL WHOAMI
```

`ACL WHOAMI` giúp nhận diện user hiện hành nếu user có quyền gọi nó; một service least-privilege **không nhất thiết phải được cấp ACL WHOAMI**. Operator có thể xác nhận identity từ connection configuration, Redis access logs hoặc phép thử trên lab mà không tăng quyền ứng dụng.

### Không tiết lộ secrets trong diagnostics

Tránh ghi cả Redis URI có user/password vào exception logs. Không gửi `AUTH username password` thành command được lưu trong shell history. Không đưa secret vào Actuator health details, metrics tags hoặc tracing attributes.

## 8. Spring Cache: key prefix quyết định phạm vi ACL

Khi dùng Spring Cache với Redis:

```java
@Cacheable(cacheNames = "products", key = "#id")
public ProductView findById(String id) {
    return repository.findById(id)
            .map(ProductView::from)
            .orElseThrow();
}
```

Redis key thực tế phụ thuộc `RedisCacheConfiguration`, cache name, key converter, prefix và serializer. Một quy ước mặc định thường bao gồm **cache name + phân cách + key**, nhưng không nên viết ACL theo ví dụ đoán nếu dự án có custom prefix.

Nên đặt namespace tường minh:

```java
import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class ApplicationCacheConfig {

    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory factory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .computePrefixWith(
                                cacheName -> "lab:cache:"
                                        + cacheName + "::")
                        .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager.builder(factory)
                .cacheDefaults(defaults)
                .build();
    }
}
```

Với cấu hình minh họa, một key cache có dạng:

```text
lab:cache:products::42
lab:cache:prices::42
```

Trong Redis thật, value có thể là JSON/JDK bytes tùy serializer. **ACL kiểm tra Redis key được gửi**, nên việc đổi key serializer hoặc prefix có thể làm pattern không còn khớp. Kiểm tra byte/key thực tế khi debug, không chỉ tên cache trong annotation.

## 9. Spring Cache: phải kiểm thử cả cache hit và miss

Nếu chỉ kiểm thử cache hit, có thể bỏ sót thiếu quyền `SET`. Nếu chỉ kiểm thử cache miss, có thể bỏ sót việc cache không được đọc vì value serializer lỗi và Spring âm thầm fallback.

Một chuỗi kiểm thử cơ bản:

1. Xóa riêng key cache lab đã biết từ setup bằng quyền phù hợp.
2. Gọi `findById("42")` lần đầu; nguồn dữ liệu chuẩn được gọi.
3. Xác nhận Redis cache key được tạo và có TTL mong đợi.
4. Gọi `findById("42")` lần hai.
5. Xác nhận nguồn dữ liệu **không** bị gọi thêm ở lần hai.
6. Xác nhận service trả đúng payload, không phải fallback giả.
7. Thử lại với user **bị thu hồi quyền SET** trên Redis lab để chứng minh đường cache fill thật sự phát hiện permission denial.

Mục tiêu không chỉ là HTTP 200. Nếu hệ thống có `CacheErrorHandler` bỏ qua lỗi cache write, request vẫn có thể trả thành công từ database. Đó có thể là **chính sách degrade hợp lệ**, nhưng permission test phải đo được rằng cache fill thất bại và ghi nhận `NOPERM`.

### Test negative không được đoán từ response

Ví dụ một test được quyền đọc nhưng không được ghi:

```text
GET lab:cache:products::42 -> OK nếu key tồn tại
SET lab:cache:products::42 bytes EX ... -> NOPERM

Ứng dụng có CacheErrorHandler bỏ qua lỗi:
  findById() có thể vẫn thành công;
  Redis key không được cập nhật;
  metric/cache error phải tăng.
```

Vì vậy assert **Redis state, số lần gọi nguồn và tín hiệu lỗi**, không chỉ response status.

## 10. Cache eviction theo key cần quyền khác cache read

`@CacheEvict` xóa entry, thường dùng `DEL` hoặc đường xóa tương đương:

```java
@CacheEvict(cacheNames = "products", key = "#id")
public void invalidateProduct(String id) {
    // Source-of-truth update được thực hiện ở luồng phù hợp.
}
```

Đường đọc có thể chỉ dùng `GET`, nhưng eviction phải có quyền ghi/xóa trên key namespace.

Test:

- Cache key tồn tại.
- Thực hiện nghiệp vụ làm `@CacheEvict` chạy.
- Redis key biến mất hoặc được invalidated theo contract.
- Sau đó truy vấn lại phải tải nguồn thay vì nhận value cũ.
- Khi chỉ thu hồi `DEL`, application phải phát hiện lỗi eviction hoặc có đường repair rõ ràng.

**Không nên mặc định bỏ qua lỗi cache evict** như bỏ qua lỗi cache put. Nếu database đã đổi nhưng key stale còn lại, endpoint có thể liên tục trả dữ liệu cũ cho tới khi TTL hết.

Đặc biệt nếu dùng cache mutation `transactionAware()` hoặc callback after-commit, một Redis `NOPERM` có thể xuất hiện **sau khi database đã commit**. Không retry toàn bộ transaction SQL chỉ vì Redis eviction thất bại.

## 11. Cache clear toàn bộ không giống evict một entry

Trong Spring Cache:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void invalidateAllProducts() {
}
```

`allEntries = true` có thể khiến `RedisCacheWriter` duyệt các keys của cache rồi xóa. Tùy cấu hình:

- Writer mặc định có thể dùng `KEYS` + `DEL` cho clear.
- Writer được cấu hình scan-based có thể dùng `SCAN` + `DEL`/`UNLINK` hoặc command tương ứng.
- Trên Redis Cluster, chiến lược SCAN và khả năng client hỗ trợ cần được xác minh riêng.
- Một cache clear **không nhất thiết là một thao tác nguyên tử** với các cache writes đồng thời.

Nếu ACL user chỉ có `GET`, `SET` và `DEL`, cache hit/miss/evict-key đều có thể thành công nhưng clear vẫn bị `NOPERM` vì thiếu `KEYS` hoặc `SCAN`.

### Cấu hình scan-based cache writer khi phù hợp

Một hướng cấu hình có thể dùng `BatchStrategies.scan(batchSize)`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.BatchStrategies;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
class ScanningCacheConfig {

    @Bean
    RedisCacheManager scanningCacheManager(
            RedisConnectionFactory factory) {

        RedisCacheWriter writer =
                RedisCacheWriter.nonLockingRedisCacheWriter(
                        factory,
                        BatchStrategies.scan(100));

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .computePrefixWith(
                                name -> "lab:cache:" + name + "::");

        return RedisCacheManager.builder(writer)
                .cacheDefaults(defaults)
                .build();
    }
}
```

Ví dụ chỉ áp dụng khi dự án sử dụng Spring Data Redis version có API builder/writer tương ứng. `SCAN` giảm tác động một lần quét lớn so với `KEYS` ở nhiều trường hợp, nhưng **không đảm bảo snapshot**, và vẫn cần kiểm soát lượng key cùng lúc và quyền xóa.

### Cảnh báo bảo mật với SCAN/KEYS

Quyền gọi `SCAN` hoặc `KEYS` có thể làm lộ tên key ngoài namespace tùy Redis version và ACL behavior. **Key pattern ACL không nên được xem là bảo đảm mọi lệnh liệt kê key sẽ tự lọc theo tenant.**

Nếu yêu cầu cách ly chặt chẽ, có thể tránh cấp quyền cache clear toàn namespace cho application runtime; dùng TTL và một job quản trị được phân quyền riêng, hoặc đặt cache của các trust boundaries khác nhau trên Redis instances/tenants khác. Đây là quyết định kiến trúc, không chỉ một dòng ACL.

## 12. Cache putIfAbsent, TTL và các đường lệnh ẩn

`Cache.putIfAbsent` hoặc lệnh Redis có dạng `SET ... NX ...` cần được kiểm thử riêng nếu ứng dụng có logic chống ghi đè.

Trong Redis ACL, `SET` là một command với các tùy chọn, nhưng framework có thể lựa chọn nhiều lệnh tùy version/feature, ví dụ `SET` cùng TTL hoặc một đường triển khai sử dụng command khác.

Test nên có:

- Key chưa tồn tại: put-if-absent thành công.
- Key đã tồn tại: value cũ được giữ.
- TTL đúng khi entry mới được tạo.
- User không được ghi namespace khác.
- Nếu command bị từ chối, error handling không biến denial thành “key đã tồn tại”.
- Khi có nhiều writers, không diễn giải một kết quả put-if-absent như lock phân tán hoàn chỉnh.

Việc cấp `+set` nhưng không cấp `+expire` có thể vẫn đủ cho `SET EX`, nhưng không đủ nếu application còn gọi `EXPIRE` riêng. **Phân tích command thật**, không tự thêm mọi command có tên giống nhau vì suy đoán.

## 13. Redis Repository không đơn thuần là một Hash

Một entity ví dụ:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash(value = "lab:repo:customers", timeToLive = 600)
public class CustomerSnapshot {

    @Id
    private String id;

    @Indexed
    private String email;

    private String displayName;

    // Constructors, getters, setters...
}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;
import java.util.List;

public interface CustomerSnapshotRepository
        extends CrudRepository<CustomerSnapshot, String> {

    List<CustomerSnapshot> findByEmail(String email);
}
```

Spring Data Redis Repository có thể lưu aggregate vào Redis Hash **và tạo các key phụ** cho keyspace metadata, secondary index, TTL hoặc expiration/shadow copy tùy mapping và configuration.

Vì thế **cấp quyền duy nhất trên `lab:repo:customers:*` theo dự đoán có thể chưa đủ**, nhất là khi index/keyspace metadata được đặt tên khác phần dự kiến. Cần quan sát key/command thực tế trong môi trường lab theo chính phiên bản Repository đang chạy.

### Repository save có thể là nhiều command

Một phương thức Java `repository.save(entity)` có thể kéo theo các thao tác Redis như:

```text
repository.save(customer)
    |
    +--> cập nhật Redis Hash của entity
    +--> cập nhật ID/keyspace tracking
    +--> xóa/thêm secondary index membership
    +--> thiết lập TTL cho key chính
    +--> tùy cấu hình: shadow copy / expiration metadata
```

**Một API Java không bằng một Redis command.** Đừng cấp `+hset` rồi coi Repository save đã được phân quyền đầy đủ.

## 14. Kiểm chứng repository.save và findById

Tạo dữ liệu thử nghiệm bằng Repository thật:

```java
String id = "lab-" + java.util.UUID.randomUUID();

CustomerSnapshot customer =
        new CustomerSnapshot(id, "lab@example.test", "Test Customer");

repository.save(customer);

CustomerSnapshot loaded =
        repository.findById(id).orElseThrow();
```

Giả định `CustomerSnapshot` có constructor phù hợp. Đây là mảnh test minh họa, không phải một chương trình độc lập hoàn chỉnh.

Các assertion:

1. `save` không phát `NOPERM`.
2. `findById` đọc được đúng entity/field.
3. TTL trên entity key phù hợp nếu đã cấu hình expiration.
4. Secondary index `findByEmail` tìm ra entity.
5. Update email làm index cũ bị bỏ và index mới xuất hiện.
6. Delete entity khiến `findById` empty và query theo index không trả entry đã xóa.
7. Không có index membership mồ côi hoặc key phụ không được cleanup theo contract.
8. Một account cùng app nhưng khác prefix không được sửa entity.

Cần chạy các test dưới **Redis ACL user của ứng dụng**, không vô tình dùng Redis admin connection trong Spring context vì khi đó các test sẽ “xanh” dù permission production thiếu.

## 15. Secondary index là một đường quyền riêng

Giả sử entity có:

```java
@Indexed
private String email;
```

Repository có thể tạo Set/index keys và sử dụng chúng để query. Đường `findById` đọc Hash có thể thành công trong khi `findByEmail` thất bại do thiếu `SMEMBERS` hoặc thiếu key permissions trên index key.

Khi update một field indexed, framework có thể cần xóa thành viên ở index cũ và thêm vào index mới. Nếu `SREM` bị từ chối nhưng `HSET` đã chạy, Redis có nguy cơ chứa **Hash mới nhưng index cũ**.

Test riêng:

```text
Arrange:
  save customer email=A
Assert:
  findByEmail(A) -> customer

Act:
  customer.email=B
  repository.save(customer)

Assert:
  findByEmail(A) -> không trả customer
  findByEmail(B) -> customer
  findById(id).email -> B
```

Không chỉ assert hash chứa B. Nếu dùng Redis Repository, **tính nhất quán của index** là một phần hợp đồng của persistence layer.

Với Redis Cluster, keyspace/index keys còn chịu giới hạn phân vùng và khả năng hỗ trợ các thao tác đa key trong framework; một test standalone với ACL đúng không chứng minh Repository tự scale trên mọi topology.

## 16. Kiểm chứng Repository delete và cleanup

`repository.deleteById(id)` không chỉ đơn giản là “được cấp `DEL` một key”. Có thể có cleanup ID set, secondary index và các cấu trúc phụ.

Bộ test tối thiểu:

```text
save customer
  -> findById OK
  -> findByEmail OK

deleteById(customer.id)
  -> findById EMPTY
  -> findByEmail EMPTY
  -> index key không còn tham chiếu tới id
```

Negative test:

- Thu hồi `DEL`: delete thất bại hoặc phát tín hiệu lỗi phù hợp.
- Thu hồi `SREM`: index cleanup có thể thất bại; kiểm tra dữ liệu/index sau lỗi.
- Cho phép key chính nhưng từ chối key index: operation phải được nhận diện là permission gap.
- Bảo đảm user repository không được `DEL` cache/session namespace của service khác.

Không dùng `deleteAll()` trên Redis dùng chung chỉ để kiểm tra ACL: phạm vi xóa có thể rộng hơn một tập dữ liệu thử nghiệm. Dùng entity IDs/keyspace được cô lập và container Redis riêng.

## 17. TTL và sự kiện hết hạn làm phát sinh đường listener

Spring Data Redis Repository có thể hỗ trợ expiration/keyspace notifications. Ngoài việc `EXPIRE` trên entity key, ứng dụng còn có thể:

- Lưu metadata phục vụ expiration.
- Theo dõi keyspace/keyevent notifications.
- Tạo shadow copy/phantom copy để phát sự kiện expired với thông tin entity (tùy cấu hình).
- Khởi tạo listener khi repository context start.
- Tương tác với Redis `notify-keyspace-events` server configuration nếu được cho phép và yêu cầu.

Những đường này thường **không được chạy trong test CRUD thông thường** nếu key chưa từng hết hạn hoặc listener chưa khởi động.

### Cấu hình keyspace event listener có chủ đích

Ví dụ:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.RedisKeyValueAdapter;
import org.springframework.data.redis.repository.configuration.EnableRedisRepositories;

@Configuration
@EnableRedisRepositories(
        enableKeyspaceEvents =
                RedisKeyValueAdapter.EnableKeyspaceEvents.ON_STARTUP,
        keyspaceNotificationsConfigParameter = "")
public class RedisRepositoryEventsConfig {
}
```

Trong các Spring Data Redis versions hỗ trợ các thuộc tính tương ứng, một chuỗi cấu hình notification rỗng được dùng để **không yêu cầu framework tự gọi CONFIG SET**; operator phải bật keyspace notifications đúng trên Redis server bằng một kênh quản trị riêng.

Không cấp `+config` cho repository runtime chỉ để nó tự bật server notifications. Nhiều managed Redis services cấm `CONFIG`, và việc cho application thay đổi cấu hình server có thể mở rộng ảnh hưởng của một lỗi deployment.

## 18. Keyspace notifications khác với quyền truy cập entity key

Ví dụ Redis keyevent notification khi một key ở database 0 hết hạn:

```text
Channel: __keyevent@0__:expired
Message: lab:repo:customers:42
```

Quyền Pub/Sub channel được kiểm tra **độc lập** với quyền `GET/HSET` trên entity key:

```text
~lab:repo:customers:*         # key pattern
&__keyevent@0__:expired       # channel pattern
+psubscribe                   # command permission
```

Dòng trong ví dụ là các **ACL concepts**, không phải một tập ACL SETUSER hoàn chỉnh. Nếu listener dùng `SUBSCRIBE` thay vì `PSUBSCRIBE`, cần cấp đúng command thực tế.

### Phạm vi sự kiện có thể rộng hơn ứng dụng

Channel `__keyevent@0__:expired` là notification cấp Redis database/node. Message có thể chứa **tên các keys của nhiều ứng dụng** cùng dùng database. Một listener chỉ lọc prefix `lab:repo:*` sau khi nhận message vẫn có thể đã nhận tên key ngoài prefix.

Điều này tạo câu hỏi **bảo mật và cách ly dữ liệu**:

- Có được phép cho ứng dụng thấy tên key ngoài namespace không?
- Có nên tách Redis deployment/database hoặc notification workload khác không?
- Redis Cluster dùng keyspace notifications theo node; listener đã theo dõi đúng nodes chưa?
- Managed Redis có cho cấu hình `notify-keyspace-events` không?
- Việc thông báo bị bỏ lỡ khi listener offline có được phép không?

Pub/Sub notifications **không phải durable event log**. Một consumer offline có thể bỏ lỡ expiration notification; không dựa vào chúng như nguồn duy nhất cho workflow bắt buộc exactly-once.

## 19. Kiểm chứng khả năng nhận keyspace event

Một test tích hợp có thể:

1. Dùng Redis lab đã được operator bật notification với những event types cần thiết.
2. Khởi tạo Repository/expiration listener bằng user hạn chế.
3. Tạo một entity thử nghiệm với TTL ngắn nhưng đủ thời gian đăng ký listener.
4. Đợi listener xác nhận đã subscribe.
5. Quan sát expired event tương ứng sau thời gian hợp lý.
6. Xác nhận event không gây truy cập/ghi ngoài namespace.
7. Thu hồi channel permission trong một test độc lập và kiểm chứng listener báo lỗi đăng ký hoặc không nhận event.
8. Xác minh reconnect/resubscribe sau khi Redis tạm ngắt kết nối.
9. Kiểm tra application không coi một event bị bỏ lỡ là bằng chứng entity chưa hết hạn.

Expiration trong Redis không phải scheduler thực thi callback ở thời điểm chính xác từng mili giây. Test nên có timeout phù hợp, tránh assert dựa vào `Thread.sleep` cố định rất ngắn.

### Không tự tạo “sự kiện hết hạn” bằng GET nil

`GET` trả nil sau TTL chỉ chứng minh key không còn tồn tại tại thời điểm đọc; nó **không chứng minh listener đã nhận keyevent notification**. Cần quan sát callback/event thật và trạng thái subscription.

## 20. Phân biệt Pub/Sub listener và Redis Stream listener

| Đặc điểm | Pub/Sub | Redis Streams |
|---|---|---|
| Đơn vị | Channel/message được publish | Stream key/entry có ID |
| Đọc | `SUBSCRIBE` / `PSUBSCRIBE` | `XREAD` / `XREADGROUP` |
| Cấp ACL | Command + **channel pattern** | Command + **key pattern** |
| Độ bền khi subscriber offline | Không có replay mặc định | Entry tồn tại trong retention để đọc lại |
| Consumer group/PEL | Không | Có |
| ACK/recovery | Không có theo Pub/Sub core | `XACK`, `XPENDING`, `XAUTOCLAIM`… |
| Subscription config | Channel ACL và connection | Group/stream key/command ACL |
| Phù hợp | Thông báo realtime, keyspace events | Event processing có delivery/retry theo group |

Đừng gọi chung “listener permission” rồi dùng một ACL user có `+subscribe` và `~stream:*`. Đối với Redis Streams, `SUBSCRIBE` không phải command đọc stream; với Pub/Sub, `XREADGROUP` cũng không giúp nhận channel.

## 21. Pub/Sub listener: command và channel phải đồng thời đúng

Ví dụ ứng dụng nghe thông báo inventory:

```text
PUBLISH lab:channels:inventory-updated product-42
SUBSCRIBE lab:channels:inventory-updated
```

Nếu user chỉ có `+subscribe` nhưng không có channel rule, Redis có thể từ chối:

```text
NOPERM this user has no permissions to access one of the channels used as arguments
```

Một allowlist dành cho **subscriber** có thể là:

```text
ACL SETUSER lab_subscriber reset on >LAB_SUB_SECRET +ping +subscribe &lab:channels:inventory-updated
```

Một **publisher** riêng:

```text
ACL SETUSER lab_publisher reset on >LAB_PUB_SECRET +ping +publish &lab:channels:inventory-updated
```

Nhập qua Redis CLI interactive trên môi trường lab. Không dùng mật khẩu mẫu cho production.

Nếu service cần pattern subscription, ví dụ mọi channel `lab:channels:inventory:*`, cân nhắc `+psubscribe` và channel pattern tương ứng. Đừng cấp wildcard `&*` khi service chỉ cần một channel.

### Test positive/negative

- Subscriber đúng channel: nhận message do publisher hợp lệ gửi.
- Subscriber thử channel `other:secret`: bị từ chối.
- Publisher thử publish `other:secret`: bị từ chối.
- Thử `PUBLISH` bằng subscriber-only user: bị từ chối do thiếu command permission.
- Thử `SUBSCRIBE` bằng publisher-only user: bị từ chối.
- Sau reconnect, listener vẫn đăng ký được channel được phép.
- Subscriber offline khi publish: không giả định message được lưu lại để replay.

## 22. RedisMessageListenerContainer trong Spring

Một Pub/Sub listener Spring Data Redis thường sử dụng `RedisMessageListenerContainer`:

```java
import java.nio.charset.StandardCharsets;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class InventoryListenerConfig {

    @Bean
    RedisMessageListenerContainer inventoryListenerContainer(
            RedisConnectionFactory factory) {

        RedisMessageListenerContainer container =
                new RedisMessageListenerContainer();

        container.setConnectionFactory(factory);

        MessageListener listener = (Message message, byte[] pattern) -> {
            String payload = new String(
                    message.getBody(),
                    StandardCharsets.UTF_8);

            // Gọi handler ứng dụng; không ghi payload nhạy cảm ra log.
            handleInventoryNotification(payload);
        };

        container.addMessageListener(
                listener,
                new ChannelTopic("lab:channels:inventory-updated"));

        return container;
    }

    private static void handleInventoryNotification(String payload) {
        // Ví dụ: invalidation/reload theo nghiệp vụ.
    }
}
```

Container dùng Redis connection/subscription lifecycle riêng; quyền của account trong factory được dùng để đăng ký. Nếu injection nhầm factory của cache-only user, listener có thể nhận `NOPERM` dù cache vẫn chạy tốt.

Khi test, nên xác nhận subscription đã sẵn sàng **trước** khi publish. Một message được publish trước khi subscriber thực sự đăng ký sẽ bị bỏ qua theo semantics Pub/Sub, không phải bằng chứng ACL sai.

## 23. Redis Streams: phân quyền producer, consumer và recovery

Một Stream workflow thường gồm:

```text
Producer                         Redis Stream
  |
  +-- XADD ----------------------> lab:streams:orders
                                      |
                                      v
Consumer Group orders-workers
  |
  +-- XREADGROUP
  |
  +-- process business effect
  |
  +-- XACK
  |
Recovery worker
  |
  +-- XPENDING / XAUTOCLAIM
```

Một cách tách identity:

| Principal | Lệnh cần xem xét | Không cần theo mặc định |
|---|---|---|
| Stream producer | `XADD`; `XTRIM` nếu thực sự sở hữu retention | `XACK`, `XGROUP` admin, `DEL` mọi key |
| Stream consumer | `XREADGROUP`, `XACK`; có thể `XPENDING` | `XADD`, `FLUSHDB`, `CONFIG` |
| Stream recovery | `XPENDING`, `XAUTOCLAIM`/`XCLAIM`, `XACK` khi phù hợp | `XADD` nếu không có nhiệm vụ producer |
| Stream bootstrap/migration | `XGROUP CREATE`/`DESTROY`/`SETID` và kiểm tra cần thiết | Quyền runtime dài hạn nếu bootstrap riêng |
| Operator | Các lệnh quản trị có kiểm soát | Không dùng trực tiếp làm app user |

Tách producer/consumer tránh trường hợp service chỉ đọc event lại có quyền phát sự kiện giả mạo. Tách bootstrap khỏi runtime tránh cấp quyền thay đổi consumer group structure trong suốt vòng đời ứng dụng.

## 24. Stream consumer đọc được chưa chắc ACK được

Một user được cấp `+xreadgroup` và key pattern có thể đọc event thành công nhưng bị Redis từ chối khi `XACK` vì thiếu `+xack`.

Hệ quả:

1. Business handler có thể đã chạy.
2. Event vẫn nằm trong Pending Entries List của group.
3. Recovery worker có thể reclaim rồi xử lý lại event.
4. Nếu không có idempotency, business action có thể bị lặp.
5. Một test chỉ chờ listener callback được gọi **không phát hiện** lỗi ACK.

Một test đúng:

```text
Arrange:
  Tạo stream/group trên Redis lab với quyền bootstrap.
  XADD một event có ID biết trước.
  Consumer hạn chế XREADGROUP nhận event.

Act:
  Handler xử lý event.
  Consumer gọi XACK bằng account đang dùng thật.

Assert:
  Event không còn pending trong group.
  Business effect đúng một lần theo protocol/idempotency.
  Không có NOPERM trong ACK path.
```

Negative test thu hồi `XACK` trên container riêng, bảo đảm hệ thống phát hiện pending/error và không trả success giả. Đừng chạy denial test trên Redis Stream production vì có thể tạo event pending thật.

## 25. Consumer group bootstrap nên tách khỏi runtime

Nhiều hệ thống khởi tạo group bằng `XGROUP CREATE` khi startup:

```bash
redis-cli XGROUP CREATE lab:streams:orders workers 0-0 MKSTREAM
```

Nếu một runtime consumer user chỉ cần `XREADGROUP` và `XACK`, việc cấp thêm `+xgroup` có thể rộng hơn cần thiết. Có hai cách thiết kế:

- **Bootstrap riêng:** migration/operator tạo stream và consumer group trước deployment; runtime user không cần `XGROUP`.
- **Self-bootstrap:** service được cấp quyền tạo group theo phạm vi hẹp, nhưng phải kiểm soát idempotent startup và các subcommands được phép theo Redis version.

Với ứng dụng critical, bootstrap riêng thường giúp giảm privilege lâu dài và tránh việc application restart làm thay đổi group state ngoài ý muốn.

### Redis ACL subcommands

Redis có thể hỗ trợ giới hạn subcommands ở phiên bản phù hợp, nhưng không giả định mọi Redis server hỗ trợ cùng cú pháp ACL selectors/subcommands. Nếu không có quyền chi tiết cần thiết, cân nhắc **tách bootstrap identity** thay vì cho runtime dùng toàn bộ `+xgroup`.

## 26. Recovery là một đường quyền ít được chạy

Một Stream consumer bình thường có thể chỉ gọi:

```text
XREADGROUP
XACK
```

Sau khi một worker crash, recovery lại gọi:

```text
XPENDING
XAUTOCLAIM
XACK
```

Nếu ACL thiếu `XAUTOCLAIM`, service có thể chạy nhiều tuần không có lỗi rồi **không thể khôi phục pending events** ngay khi sự cố xảy ra.

Bộ test nên mô phỏng:

1. Consumer A nhận message nhưng không ACK.
2. Đợi idle timeout trong môi trường lab.
3. Recovery consumer B dùng user thật gọi `XAUTOCLAIM` hoặc giao thức phù hợp.
4. B xử lý lại bằng logic idempotent.
5. B ACK thành công.
6. Pending count/age trở về mức mong đợi.
7. Một user không có nhiệm vụ recovery bị từ chối quyền claim nếu chính sách đã tách principal.

Đừng dùng mỗi `XINFO GROUPS` để kết luận recovery hoạt động. Cần thực hiện chính command reclaim/ACK.

## 27. Test Stream với Spring Data Redis

Một API đọc theo group có thể dùng:

```java
import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class StreamConsumerProbe {

    private final StringRedisTemplate redis;

    public StreamConsumerProbe(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<MapRecord<String, Object, Object>> read(
            String stream,
            String group,
            String consumer) {

        return redis.opsForStream().read(
                Consumer.from(group, consumer),
                StreamReadOptions.empty()
                        .count(10)
                        .block(Duration.ofSeconds(1)),
                StreamOffset.create(
                        stream,
                        ReadOffset.lastConsumed()));
    }
}
```

Các generic types/overloads cần được đối chiếu với Spring Data Redis version và serializers của dự án. Đây là ví dụ tập trung vào **đường command `XREADGROUP`**; một integration test thực sự còn phải tạo group, gửi event, xử lý, `XACK` và kiểm tra pending.

Ví dụ ACK:

```java
Long acked = redis.opsForStream()
        .acknowledge(
                "lab:streams:orders",
                "workers",
                receivedRecord.getId());
```

`receivedRecord` là entry đã được consumer nhận trong test. Nếu app dùng auto-ACK mode, cần hiểu khi nào container thực hiện ACK và thực sự test đúng cấu hình đó.

## 28. Phân biệt stream key ACL và Pub/Sub channel ACL

Ví dụ:

```text
Redis key:
  lab:streams:orders

Redis channel:
  lab:channels:orders-updated
```

Producer/consumer của Stream cần quyền theo Redis **key**:

```text
~lab:streams:orders
+xadd
+xreadgroup
+xack
```

Pub/Sub listener cần quyền theo Redis **channel**:

```text
&lab:channels:orders-updated
+subscribe
```

Không hoán đổi `~...` và `&...`. Nếu một service vừa dùng Stream vừa subscribe channel, nó có thể cần **cả hai**, nhưng nên đánh giá tách connection factory/principal khi khác mức tin cậy.

## 29. Cách lấy danh sách Redis command thực tế

Phân quyền dựa trên tài liệu API thôi có thể thiếu những command framework gọi ở paths ít gặp. Các nguồn bằng chứng có thể dùng trong **môi trường cô lập**:

- Redis command logs/traces từ client có giới hạn và được kiểm soát dữ liệu.
- Lettuce command observation/metrics.
- Redis `ACL LOG` sau khi chạy tests bằng user hạn chế.
- `ACL DRYRUN` cho một command với key/channel cụ thể.
- Redis `MONITOR` trong lab riêng để quan sát command khi thật sự cần; không dùng thường xuyên trên production vì chi phí và nguy cơ lộ dữ liệu.
- Quan sát keyspace bằng quyền quản trị lab để tìm Hash/index/metadata keys.
- Ghi nhận version Spring Data Redis và cấu hình cache writer/listener.
- Mappings từ test input đến key thực tế được tạo.

`MONITOR` có thể hiển thị command arguments và dữ liệu nhạy cảm; không trích xuất log raw vào ticket hoặc chat. Redis ACL LOG cũng là nguồn chẩn đoán bảo mật và nên được bảo vệ.

### Công cụ không thể thay cho test

Một lần `ACL DRYRUN app_cache GET lab:cache:products::42` chỉ chứng minh rule ACL cho **lệnh GET giả định**. Nó không chứng minh `@Cacheable` thực tế chỉ gọi GET, vì cache miss có thể gọi SET; cache clear lại cần SCAN/KEYS; và serializer có thể tạo Redis key byte khác dự kiến.

## 30. Cách sử dụng ACL DRYRUN có hệ thống

Trên Redis lab có Redis version hỗ trợ:

```text
ACL DRYRUN lab_cache GET lab:cache:products::42
ACL DRYRUN lab_cache SET lab:cache:products::42 payload EX 60
ACL DRYRUN lab_cache DEL lab:cache:products::42
ACL DRYRUN lab_cache SCAN 0 MATCH lab:cache:products::* COUNT 100
ACL DRYRUN lab_cache GET lab:session:42
```

Với Repository, test đúng command/index key được quan sát:

```text
ACL DRYRUN lab_repository HGETALL lab:repo:customers:42
ACL DRYRUN lab_repository HSET lab:repo:customers:42 email a@example.test
ACL DRYRUN lab_repository SADD lab:repo:index:email:a@example.test 42
ACL DRYRUN lab_repository SREM lab:repo:index:email:a@example.test 42
```

**Tên index key ở trên chỉ là placeholder minh họa**. Không giả định Spring Data Redis phiên bản thực tế tạo đúng tiền tố đó. Khi cho phép ACL, phải thay bằng những key thực tế quan sát được trong lab.

Với Pub/Sub:

```text
ACL DRYRUN lab_subscriber SUBSCRIBE lab:channels:inventory-updated
ACL DRYRUN lab_subscriber SUBSCRIBE other:secret
```

Nếu Redis version không hỗ trợ `ACL DRYRUN` hoặc managed Redis giới hạn lệnh này, dùng một test identity thực sự và kiểm tra command trực tiếp trên Redis cô lập.

## 31. ACL LOG giúp phát hiện thiếu quyền nhưng không phải cơ chế quan sát duy nhất

Trong lab hoặc dưới quyền operator:

```text
ACL LOG
ACL LOG 20
```

Các bản ghi có thể chứa thông tin denial: lý do, user, context, command hoặc key/channel bị từ chối theo khả năng Redis version.

Ứng dụng có thể nhận `NOPERM` mà không có đủ chi tiết trong exception ngoài cùng do Spring exception translation. Khi đó **root cause + ACL LOG + operation name** giúp định vị:

```text
App:
  repository.save(customer) -> RedisSystemException / NOPERM

Redis ACL LOG:
  user lab_repository
  command SREM (ví dụ)
  reason command

Kết luận:
  Đường update index đang cần SREM;
  không phải thiếu quyền HSET cho hash chính.
```

Một nguyên tắc quan trọng: ACL LOG là dữ liệu nhạy cảm và có dung lượng/định dạng hữu hạn. Không nên dùng nó như audit store bền vững duy nhất; cần hệ thống log/alert của ứng dụng và Redis phù hợp.

## 32. Cách thiết kế ACL allowlist có thể tái tạo

Nên quản lý hợp đồng dưới dạng bảng hoặc cấu hình kiểm soát phiên bản:

```text
Principal: app_cache
  key patterns:
    lab:cache:products::*
    lab:cache:prices::*
  commands:
    PING, GET, SET, DEL
    SCAN nếu cache clear dựa trên SCAN và cho phép theo policy
  no channel access
  deny:
    FLUSHDB, CONFIG, ACL, XADD, HSET, session keys

Principal: app_repository
  key patterns:
    entity hash keys
    secondary index keys
    keyspace metadata/expiration keys đã xác minh
  commands:
    HGETALL, HSET, DEL, SADD, SREM, SMEMBERS,
    EXPIRE và các command thật sự phát sinh
  channel access:
    chỉ khi có keyspace notification listener

Principal: app_listener
  Sub/Pub:
    SUBSCRIBE/PSUBSCRIBE và channel pattern cần thiết
  hoặc Stream:
    XREADGROUP, XACK, XPENDING/XAUTOCLAIM theo vai trò
```

Nên tách contract theo **environment và deployment** nếu key namespaces/topology khác nhau, nhưng tránh hai môi trường vô tình mang chính sách permission khác biệt mà không có lý do.

### Vì sao không khuyến nghị copy một ACL SETUSER hoàn chỉnh?

Repository và cache writer có thể sinh key và commands khác theo framework version. Việc sao chép một allowlist từ bài giảng lên production có thể làm mất chức năng hiếm gặp như TTL expiration cleanup. **Các rule phải được sinh từ workflow và kiểm chứng trong môi trường tương đương**, rồi mới rollout có kiểm soát.

## 33. Cần tách tài khoản hay dùng một user chung?

Có hai lựa chọn:

### Một identity dùng chung cho app

```text
Spring Application
   |
   +--> RedisCacheManager
   +--> Redis Repository
   +--> Pub/Sub listener
   +--> Stream consumer
           |
           v
      One Redis user
```

Ưu điểm là cấu hình đơn giản. Nhược điểm: bất kỳ lỗi hoặc secret leak trong app có thể dùng **tập hợp quyền của mọi thành phần**. Một REST API chỉ cần đọc cache có thể có quyền XADD vào Stream hoặc xóa index.

### Nhiều identity theo trách nhiệm

```text
Spring Application
   |
   +--> CacheManager ----------> cacheConnectionFactory (app_cache)
   |
   +--> CustomerRepository ----> repositoryConnectionFactory (app_repository)
   |
   +--> Pub/Sub container -----> listenerConnectionFactory (app_subscriber)
   |
   +--> Stream consumer -------> streamConnectionFactory (app_stream_consumer)
```

Ưu điểm: giảm blast radius. Đánh đổi: nhiều credentials, nhiều connection factories, cần bảo trì wiring và lifecycle.

**Không bắt buộc tách user cho mọi bean**. Hãy quyết định theo threat model, mức phân chia nghiệp vụ, trust boundaries và khả năng vận hành. Nếu tách, phải đảm bảo Spring injection dùng đúng factory, nếu không có thể biến một sự cố bảo mật thành các lỗi `NOPERM` khó tìm.

## 34. Cấu hình nhiều factory cần có qualifier rõ ràng

Một ví dụ wiring ở mức kiến trúc:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisTemplatesConfig {

    @Bean("cacheOps")
    StringRedisTemplate cacheOps(
            @Qualifier("cacheConnectionFactory")
            RedisConnectionFactory factory) {

        return new StringRedisTemplate(factory);
    }

    @Bean("eventOps")
    StringRedisTemplate eventOps(
            @Qualifier("eventConnectionFactory")
            RedisConnectionFactory factory) {

        return new StringRedisTemplate(factory);
    }
}
```

Đoạn trên giả định `cacheConnectionFactory` và `eventConnectionFactory` đã được tạo an toàn bằng credentials tương ứng; không phải cấu hình khởi tạo factory hoàn chỉnh.

Nếu application còn dùng Redis auto-configuration của Spring Boot, cần xem xét bean precedence, `@Primary`, qualifiers và consumer injection rõ ràng. Chỉ tạo nhiều factories khi có lý do; kiểm tra service thật sự sử dụng connection đã dự kiến trong integration tests.

Đặc biệt khi Repository framework được enable, connection factory/template nó sử dụng có thể được chọn qua repository configuration. Không nên suy rằng một `@Qualifier` trong một service bất kỳ sẽ tự thay đổi factory mà toàn bộ Redis Repository đang dùng.

## 35. Kiểm thử tích hợp bằng Redis thật, không chỉ mock

Unit test mock `RedisTemplate` không thể chứng minh Redis ACL thực sự cho phép hay từ chối command/key/channel.

Nên có integration test với Redis cô lập:

```text
JUnit 5 / Spring Test
        |
        +--> Spring ApplicationContext
        |      |
        |      +--> CacheManager
        |      +--> Redis Repository
        |      +--> Listener container
        |
        +--> Redis lab/Testcontainers
                |
                +--> admin bootstrap creates ACL users
                +--> application connects as restricted users
                +--> test inputs occupy lab:* namespace
```

Các yêu cầu:

- Redis server version tương đương production nếu dựa vào ACL DRYRUN, key read/write rules hoặc Streams command support.
- ACL users phải được tạo **trước khi** Spring components kết nối/khởi động.
- Không dùng admin credentials làm account ứng dụng trong test.
- Dùng key và channel riêng cho mỗi test.
- Cleanup dữ liệu và group/stream theo phạm vi lab.
- Có cả positive và negative tests.
- Nếu chạy song song, mỗi test phải tránh đụng Redis keys của test khác.
- Không gọi `FLUSHALL` trên Redis dùng chung.

### Gradle dependencies minh họa

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-cache")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers")
}
```

Testcontainers trong trường hợp này chỉ là **công cụ dựng Redis server thật**; không có một hệ thống ACL giả định nào tự thay thế Redis server. Cần Docker/container runtime trên máy test và cấu hình dependency BOM phù hợp.

## 36. Bootstrap ACL trên Redis test instance

Trong test lab, một script khởi tạo Redis có thể chạy trước khi Spring context tạo connection:

```text
ACL SETUSER lab_cache reset on >LAB_CACHE_SECRET ~lab:cache:* +ping +get +set +del

ACL SETUSER lab_repository reset on >LAB_REPO_SECRET ~lab:repo:* +ping +hgetall +hset +del +sadd +srem +smembers +expire

ACL SETUSER lab_subscriber reset on >LAB_SUB_SECRET +ping +subscribe &lab:channels:inventory-updated

ACL SETUSER lab_stream_consumer reset on >LAB_STREAM_SECRET ~lab:streams:orders +ping +xreadgroup +xack +xpending +xautoclaim
```

**Đây chỉ là các allowlists để khởi động bài lab**, không phải tuyên bố rằng chúng đủ cho tất cả Redis Repository/cache/listener implementations. Test sẽ làm lộ những command/key phụ bị thiếu. Mật khẩu mẫu cần thay bằng secrets lab và không dùng lại ngoài môi trường cô lập.

Chú ý:

- `lab_repository` ở trên có thể thiếu index keys nằm ngoài `lab:repo:*` hoặc các commands khác. Dùng test để xác định.
- `lab_cache` chưa có `SCAN`/`KEYS`, nên `clear` có thể lỗi — đây là negative case có chủ đích.
- `lab_subscriber` chỉ nghe một channel cụ thể; nếu listener dùng pattern subscription cần command `PSUBSCRIBE` phù hợp.
- `lab_stream_consumer` không được `XADD`/`XGROUP CREATE`, vì bootstrap và producer là vai trò khác.
- Redis 6/7 và managed Redis có thể khác chi tiết ACL command support.
- Nếu dùng Redis Cluster, cần chuẩn bị ACL/user trên các nodes theo cơ chế quản lý phù hợp, không chỉ seed node.

## 37. Ma trận integration tests khuyến nghị

| ID | Tính năng | Test | Assertion chính |
|---|---|---|---|
| AUTH-01 | Authentication | Username/password đúng | Connection và lệnh được phép thành công |
| AUTH-02 | Authentication | Password sai | WRONGPASS/connection failure rõ, không fallback im lặng |
| CACHE-01 | Cache read | Hit với user cache | Trả value, không gọi source |
| CACHE-02 | Cache fill | Miss dẫn tới SET | Key mới tồn tại, có TTL |
| CACHE-03 | Cache evict | Evict một key | Key không còn, lần sau miss |
| CACHE-04 | Cache clear | Clear allEntries | Xóa đúng namespace theo writer strategy |
| CACHE-05 | Cache clear denial | Không cấp SCAN/KEYS | Clear báo lỗi/metric, không giả thành công |
| CACHE-06 | Namespace escape | GET/SET ngoài cache prefix | Redis trả NOPERM |
| CACHE-07 | Cache PUT denial | Thu hồi SET trong lab | Phát hiện cache write failure kể cả khi service fallback |
| REPO-01 | Repository save/read | Save + findById | Hash/fields chính xác |
| REPO-02 | Secondary index | Save + findByIndexedField | Query trả entity |
| REPO-03 | Index migration | A → B | Index A sạch, index B cập nhật |
| REPO-04 | Delete cleanup | Delete entity | Hash và index không còn entry |
| REPO-05 | TTL | Entity hết hạn | Lifecycle theo contract |
| REPO-06 | Permission denial | Thu hồi SREM/HSET/DEL | Đường lỗi hiển thị và state được kiểm tra |
| REPO-07 | Namespace escape | Repository user xóa cache/session key | Bị NOPERM |
| PUB-01 | Pub/Sub subscriber | Đúng channel | Nhận notification sau subscribe |
| PUB-02 | Channel denial | Ngoài channel được cấp | NOPERM |
| PUB-03 | Publisher denial | Subscriber thử PUBLISH | Bị từ chối |
| PUB-04 | Reconnect | Redis connection gián đoạn trong lab | Listener subscribe lại hợp lệ |
| EXP-01 | Expiration listener | Key TTL hết hạn | Nhận event đúng scope khi notifications enabled |
| EXP-02 | Config permission | Runtime không có CONFIG SET | Startup không yêu cầu quyền admin |
| STREAM-01 | Producer | XADD với producer user | Message được ghi |
| STREAM-02 | Consumer read | XREADGROUP | Event được nhận |
| STREAM-03 | ACK | XACK | Pending entry được ACK |
| STREAM-04 | Reclaim | XAUTOCLAIM sau worker chết | Event được nhận lại có kiểm soát |
| STREAM-05 | Missing ACK ACL | Thu hồi XACK | Pending không được coi là đã xử lý |
| STREAM-06 | Role separation | Consumer thử XADD | NOPERM |
| ROTATE-01 | Secret rotation | Client mở connection mới | Dùng secret mới, không còn phụ thuộc secret cũ |
| CLUSTER-01 | Cluster routing | Keys ở các slots/nodes | Không có quyền thừa, routing hoạt động |
| OBS-01 | Security telemetry | Gây một denial trong lab | ACL LOG/app metric ghi nhận đúng loại |

Ma trận này cần điều chỉnh khi workload không dùng tất cả tính năng. **Một bộ test permission tốt kiểm chứng đúng những đường app dùng**, không cần tạo feature chỉ để test.

## 38. Test code: đọc/ghi cache với principal hạn chế

Một integration test ở cấp service có thể sử dụng Mockito spy để kiểm tra nguồn chỉ được gọi khi miss:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

@Test
void cacheHitAndCacheMissUseAllowedRedisOperations() {
    String id = "lab-product-42";

    ProductView first = productService.findById(id);
    ProductView second = productService.findById(id);

    assertThat(second).isEqualTo(first);

    verify(productSource, times(1)).loadProduct(id);
}
```

Ví dụ giả định app có `productService`, `productSource` và test context đã wiring caching đúng. Cần xóa key cache trước test, không để cache state test trước ảnh hưởng kết quả. Nếu proxy Spring Cache không được dùng do self-invocation, test có thể cho kết quả sai; hãy gọi qua Spring bean thực.

Sau test service, đọc lại Redis key bằng account/đường quan sát phù hợp trong lab để xác nhận cache fill và TTL, tránh kết luận rằng “service trả đúng nên Redis ACL đúng”.

### Kiểm chứng cache evict

```java
@Test
void evictInvalidatesTheExpectedCacheEntry() {
    String id = "lab-product-43";

    productService.findById(id);         // populate cache
    productService.invalidate(id);       // @CacheEvict
    productService.findById(id);         // load again

    verify(productSource, times(2)).loadProduct(id);
}
```

Nếu một test chỉ gọi `invalidate` mà không kiểm tra key/call count, có thể bỏ qua cache evict bị `NOPERM` hoặc cache annotation không qua proxy.

## 39. Negative test: sai namespace phải thất bại

Các permission tests nên chứng minh user **không** thể làm các thao tác ngoài quyền.

Một ví dụ:

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.springframework.dao.DataAccessException;

@Test
void cacheIdentityCannotDeleteSessionKey() {
    assertThatThrownBy(() ->
            cacheTemplate.delete("lab:session:someone-else"))
            .isInstanceOf(DataAccessException.class);
}
```

Tùy Spring Data Redis/Lettuce version, exception cụ thể có thể được bọc hoặc dịch khác nhau. Test nên xác minh root cause chứa **Redis NOPERM** khi cần phân biệt denial với mạng lỗi, thay vì ràng buộc mọi version vào một exception subclass.

**Không thực thi negative test trên key thật của dịch vụ khác**, kể cả kỳ vọng NOPERM. Chỉ dùng namespace lab, với một key thử nghiệm được tạo sẵn trong Redis container và thuộc “vùng cấm” giả lập.

## 40. Negative test cho Pub/Sub channel

Một listener test cần phân biệt “không nhận message” vì không được quyền với “không nhận message” vì publish trước lúc subscriber đăng ký.

Quy trình:

1. Khởi động container và listener.
2. Chờ xác nhận subscription sẵn sàng (hook trạng thái/đồng bộ test).
3. Publish message vào channel đúng bằng publisher account hợp lệ.
4. Kiểm chứng callback nhận đúng một message hoặc theo contract của test.
5. Với user không được phép, cố subscribe channel khác qua một connection test riêng.
6. Assert Redis báo denial `NOPERM`, không chỉ đợi callback timeout.
7. Publish trên channel đúng bằng subscriber-only user cũng phải bị từ chối nếu role tách.
8. Test reconnect và xác định listener không tự đăng ký vào channel ngoài allowlist.

Vì Pub/Sub không lưu lịch sử cho subscriber offline, **việc callback không được gọi không đủ để chứng minh ACL đã chặn thành công**. Cần quan sát actual command error/ACL LOG trong lab.

## 41. Negative test cho Stream ACK và recovery

Test có chủ đích:

```text
Setup:
  Bootstrap account tạo lab:streams:orders + workers group
  Producer account XADD event id=...
  Consumer account XREADGROUP event

Case A (positive):
  Consumer XACK -> success
  XPENDING không còn event đó trong group

Case B (negative):
  Consumer account không có quyền XACK
  XACK -> NOPERM
  Event vẫn pending
  Recovery account reclaim/ACK theo protocol
```

Cần giữ idempotency của business handler, vì một event có thể được xử lý trước khi ACK lỗi rồi sau đó được reclaim. Một permission test không nên tạo duplicate email/payment thật; dùng fake business sink hoặc database test với unique operation ID.

### Test số pending không thay cho test xử lý nghiệp vụ

`XPENDING` có thể cho thấy event pending giảm, nhưng không tự chứng minh side effect đã được commit. Phải kiểm chứng cả Redis PEL lẫn nguồn dữ liệu nghiệp vụ test.

## 42. Xử lý lỗi: không để fallback che NOPERM

Với Redis cache tùy chọn, việc đọc từ database khi Redis lỗi có thể hợp lệ. Nhưng trong permission tests, phải thấy rằng Redis `SET`/`DEL` bị từ chối nếu thiếu quyền.

Ví dụ anti-pattern:

```java
try {
    cache.put(key, value);
} catch (Exception ignored) {
    // Service vẫn trả thành công.
}
```

Nếu ứng dụng chọn best-effort cache, cần:

- Phân loại exception theo root cause.
- Ghi metric cache failure theo command/operation.
- Không log credentials hoặc toàn bộ payload.
- Không mặc định bỏ lỗi evict/clear nếu dữ liệu stale có thể gây sai nghiệp vụ.
- Không cho security regression bị che bởi service response thành công.
- Tạo readiness/health policy phù hợp với vai trò cache, không biến một cache optional denial thành restart storm.

Trong Spring Cache, `CacheErrorHandler` có thể quyết định xử lý lỗi cache GET/PUT/EVICT/CLEAR. Cần test từng callback path theo Spring version và error policy thực tế.

## 43. Quan sát lỗi ACL mà không mở rộng quyền application

Những tín hiệu nên ghi nhận:

| Tín hiệu | Cách dùng |
|---|---|
| Redis command error rate | Phân biệt Redis timeout vs NOPERM |
| `NOPERM` theo command | Phát hiện quyền thiếu hoặc code mới chạy command chưa cấp |
| `NOAUTH`/`WRONGPASS` | Phát hiện lỗi credentials/rotation |
| ACL LOG events | Phân tích denial trên Redis bằng operator identity |
| Cache put/evict/clear failures | Phát hiện cache stale hoặc loss of efficiency |
| Repository save/index/delete failures | Phát hiện dữ liệu và index không nhất quán |
| Listener subscribe errors | Phát hiện consumer đã start nhưng không nhận message |
| Stream XACK/reclaim errors | Phát hiện pending backlog không phục hồi |
| Keyspace notification callback rate | Phát hiện listener bị mất subscription hoặc config |
| Redis connection/reconnect failures | Phân biệt ACL với network/TLS/topology |

Tránh tag metric bằng raw key hoặc channel chứa user ID/token; cardinality cao vừa làm tăng chi phí telemetry vừa có thể rò rỉ thông tin.

Không cho ứng dụng runtime quyền `ACL LOG` hoặc `MONITOR` chỉ để tự quan sát. Hãy giữ một đường điều tra riêng thuộc operator.

## 44. Redis ACL không thay thế kiểm soát dữ liệu và mạng

Least privilege của Redis chỉ là một lớp:

- **TLS:** mã hóa và xác minh certificate/hostname; không disable verification vì lỗi credentials.
- **Network isolation:** private endpoint, firewall, security groups; không expose Redis công khai.
- **Secrets management:** rotation, không commit password, giới hạn ai đọc được secret.
- **Application authorization:** xác nhận người dùng/tenant trước khi lấy Redis key; đừng tin prefix do client gửi.
- **Data minimization:** không lưu token nhạy cảm hoặc payload không cần thiết trong Redis.
- **Serialization safety:** tránh deserialize dữ liệu không tin cậy bằng cơ chế có nguy cơ chạy mã ngoài mong đợi.
- **Key naming:** dùng namespace rõ và không đưa bí mật vào tên key.
- **Observability:** không log raw Redis commands chứa token/password.
- **Resource isolation:** Redis ACL không mặc định cấp quota memory/CPU riêng cho từng user; workload gây tải lớn vẫn có thể ảnh hưởng dịch vụ khác.
- **Persistence/backups:** dữ liệu bị xóa khỏi keyspace không đồng nghĩa đã bị xóa khỏi mọi snapshot/backup.

Một user chỉ có quyền `GET lab:cache:*` vẫn có thể đọc mọi dữ liệu nhạy cảm được các service khác vô tình ghi dưới prefix đó. **Thiết kế namespace và tenant isolation quan trọng không kém tên command.**

## 45. Những giới hạn khi dùng Redis Cluster

Redis Cluster đòi hỏi xem xét:

- Identity/ACL policy được áp dụng nhất quán trên các nodes theo cách vận hành Redis/managed service.
- Client tìm thấy topology và kết nối được đến những node endpoints được quảng bá.
- Một ứng dụng có thể có quyền trên seed node nhưng gặp `NOPERM`/`WRONGPASS` trên node khác nếu policy/secret không đồng bộ.
- Một keyspace/index/script nhiều key cần tuân thủ hash slot constraints.
- Một Pub/Sub/keyspace notification listener có thể chỉ theo dõi phạm vi node, không phải tự nhận mọi event từ mọi primary.
- Cache clear với SCAN phải kiểm chứng cách quét và xóa keys trên toàn cluster theo driver strategy.
- Failover/resharding có thể làm mở connection mới và tái xác thực; secret rotation phải bao phủ các nodes mới.
- Khi đọc replica, dữ liệu có thể stale; thành công ACL không bảo đảm read-your-writes.

**Một test trên Redis standalone không đủ chứng minh permission contract hoạt động trong Cluster.** Với production Cluster, cần integration tests riêng trên cluster lab, đặc biệt cho cache clear, Repository index operations và listener subscriptions.

## 46. Thay đổi ACL có thể khiến listener hỏng ngay khi reconnect

Một listener có thể subscribe thành công từ trước. Sau khi ACL/secret thay đổi:

```text
T0 Listener đã subscribe, đang nhận message
T1 Redis admin rotate user/password hoặc sửa channel pattern
T2 Redis disconnect/failover
T3 Listener reconnect bằng credentials mới/cũ
T4 SUBSCRIBE bị NOPERM hoặc AUTH bị WRONGPASS
T5 Ứng dụng vẫn chạy HTTP nhưng listener không nhận message
```

Không chỉ test “listener chạy lúc startup”. Bộ test rotation/reconnect nên xác nhận:

1. Một connection mới xác thực được với secret mới.
2. Listener resubscribe được channel được phép.
3. Message mới được nhận sau reconnect.
4. Stream consumer có thể XREADGROUP/ACK/reclaim sau failover.
5. Cache/Repository cũng sử dụng secret mới.
6. Secret cũ được thu hồi có kiểm soát khi tất cả clients đã chuyển.
7. Dashboard cảnh báo khi subscribe/recovery command lỗi.

Đừng thử secret rotation bằng cách đổi ACL user production đột ngột khi chưa có deployment plan và rollback.

## 47. Phân quyền lệnh quản trị: tách khỏi runtime

Những lệnh có độ nhạy cao thường không nên cấp cho app:

```text
ACL SETUSER / ACL DELUSER
CONFIG SET / CONFIG REWRITE
FLUSHDB / FLUSHALL
SHUTDOWN
MONITOR
CLUSTER SETSLOT / CLUSTER FAILOVER
REPLICAOF
SCRIPT FLUSH
FUNCTION FLUSH
```

Một số command quản trị cần thiết trong CI bootstrap, migration, operator tasks hoặc incident recovery. Dùng **operator/migration principal** và truy cập qua quy trình quản trị riêng.

Đặc biệt:

- Repository keyspace notifications cần Redis config đúng, nhưng app runtime không nhất thiết được phép `CONFIG SET`.
- Stream group creation có thể là một migration thay vì quyền runtime.
- Cache clear có thể là một chức năng nghiệp vụ có giới hạn; không tương đương `FLUSHDB`.
- Một script app cần `EVAL` không có lý do được `SCRIPT FLUSH`.
- Một health check cần `PING` không cần `CONFIG GET` hoặc `ACL LIST`.

## 48. Runbook khi gặp NOPERM trong production

Không sửa bằng cách cấp `+@all ~* &*`. Đi theo trình tự:

1. **Xác định triệu chứng:** Cache GET/PUT/EVICT/CLEAR, Repository save/index/delete hay listener subscribe/ACK.
2. **Ghi nhận exception root cause** và Redis error code; tránh log secret/raw payload.
3. **Xác nhận principal đang dùng** ở connection factory thực tế, kể cả sau reconnect.
4. **Xác nhận endpoint/topology:** đúng Redis, database, primary/replica, cluster node.
5. **Tìm command bị chặn:** app operation trace + ACL LOG với operator quyền phù hợp.
6. **Xác định key hoặc channel cụ thể** trong lab/telemetry an toàn.
7. **Đối chiếu ACL contract**: thiếu command, pattern hay read/write access?
8. **Tái hiện trên Redis lab** bằng cùng version/schema và principal hạn chế.
9. **Chạy positive + negative tests** trước khi thêm đúng quyền thiếu.
10. **Rollout permission change có kiểm soát**, theo dõi lỗi và có rollback path.
11. **Đối soát side effects**: cache stale, Repository index mồ côi, Stream pending, listener missed events.
12. **Bổ sung regression test** cho đường ít gặp từng gây sự cố.

Một `NOPERM` sau `repository.save` có thể để lại một phần state đã cập nhật nếu hoạt động gồm nhiều commands không nguyên tử. Khôi phục permission **không tự sửa những index hoặc event đã thiếu**; cần reconciliation khi thích hợp.

## 49. Chuyển từ quyền rộng sang quyền tối thiểu an toàn

Nếu ứng dụng đang dùng một user quyền rộng, không nên ngay lập tức thu hồi mọi quyền ở production.

Quy trình chuyển đổi:

```text
Current broad user
     |
     v
Workload inventory + trace trong staging
     |
     v
Tạo restricted user mới
     |
     v
Chạy integration tests: Cache/Repo/Listener
     |
     v
Canary deployment một số app instances
     |
     v
Giám sát NOPERM, app SLO, index/stream state
     |
     v
Mở rộng rollout và giữ rollback window
     |
     v
Thu hồi broad user và credentials cũ
```

Trong canary:

- Cache hit có thể che quyền SET còn thiếu.
- Repository index update/delete ít xảy ra có thể chưa được kích hoạt.
- Stream reclaim cần fault injection ở lab trước canary.
- Keyspace expiration event có thể xuất hiện muộn.
- Secret rotation/failover có thể buộc reconnect và lộ lỗi subscription.

Vì thế canary thông thường không thay thế integration tests của các đường hiếm.

## 50. Các lỗi thiết kế phổ biến

**“PING thành công là ACL đã đúng.”**  
Sai. PING không kiểm tra GET/SET/HSET/XACK hoặc key/channel patterns.

**“Cho GET/SET là đủ cho Spring Cache.”**  
Chưa chắc. Evict/clear/put-if-absent và TTL paths có command khác.

**“Repository chỉ lưu một Hash nên cho HSET/HGETALL là đủ.”**  
Sai trong nhiều mapping: secondary index, keyspace metadata và expiration tạo lệnh/key bổ sung.

**“@Indexed chỉ ảnh hưởng query Java, không cần ACL riêng.”**  
Sai. Index cần tạo, cập nhật và cleanup bằng Redis commands.

**“Keyspace listener chỉ cần quyền key pattern.”**  
Sai. Pub/Sub còn cần command và channel ACL.

**“Redis Streams consumer chỉ cần XREADGROUP.”**  
Sai khi cần ACK, pending/recovery; phải kiểm chứng XACK và reclaim.

**“Đã cấp ~lab:* nên subscriber nghe được &lab:*.”**  
Sai. Key và channel permissions là hai chiều độc lập.

**“Dùng +@all trước rồi thu hẹp sau cho dễ.”**  
Rủi ro: quyền thừa có thể tồn tại lâu hoặc bị quên; nên xây allowlist từ workload.

**“ACL DRYRUN pass nghĩa là framework save chắc chắn thành công.”**  
Không. Save có thể gọi nhiều commands và keys phụ.

**“Cấp CONFIG SET cho Repository để bật notifications là bình thường.”**  
Không mặc định. Cấu hình server nên do operator quản lý nếu có thể.

**“Một test user dùng account admin cho xanh là đủ.”**  
Sai. Test phải chạy dưới cùng principal bị hạn chế như production.

**“Nếu permission lỗi, retry vô hạn sẽ tự hồi phục.”**  
Sai. Cùng command/user/quyền vẫn bị NOPERM cho tới khi cấu hình thay đổi.

## 51. Bài thực hành 1: quyền Cache theo ba lớp

Dùng một Redis server lab và hai users:

```text
lab_cache_read:
  ~lab:cache:*
  +get, +ping

lab_cache_rw:
  ~lab:cache:*
  +get, +set, +del, +ping
```

Các bước:

1. Cấu hình `RedisCacheManager` với prefix `lab:cache:`.
2. Dùng RW user tạo một entry `products::42` có TTL.
3. Dùng read user chạy `@Cacheable` hit, xác nhận kết quả.
4. Xóa entry bằng RW user, rồi gọi `@Cacheable` miss với read user; ghi nhận cache fill denial.
5. Dùng RW user test `@CacheEvict`.
6. Thử `allEntries = true` với RW user và quan sát thiếu `KEYS`/`SCAN` nếu writer cần.
7. Cấp đúng quyền clear (nếu policy cho phép) hoặc thay bằng thiết kế invalidation/TTL khác.
8. Dùng cả hai users thử truy cập `lab:session:42`, assert NOPERM.
9. Xác nhận không user nào có quyền `FLUSHDB`.

Ghi lại bảng “operation – command – key – expected allow/deny – actual result” để đưa vào regression suite.

## 52. Bài thực hành 2: Repository có secondary index

Trên Redis lab:

1. Tạo `CustomerSnapshot` có `@RedisHash`, `@Indexed email` và TTL.
2. Dùng một restricted repository user; bắt đầu bằng Hash commands và namespace được quan sát.
3. `save` entity A, `findById`, `findByEmail`.
4. Đổi email A → B, save, tìm theo A và B.
5. Delete entity; xác nhận index cleanup.
6. Thu hồi `SREM` hoặc quyền index key trong một test **độc lập**.
7. Quan sát `NOPERM`, hash/index sau lỗi và khả năng cần reconciliation.
8. Xác định framework đã dùng những Redis keys ngoài prefix dự kiến nào.
9. Kiểm tra expiration listener khi TTL hết hạn nếu tính năng được bật.
10. Xác nhận repository user không thể xóa cache namespace.

Bài học chính: **đủ quyền cho một Hash không đồng nghĩa đủ quyền cho persistence abstraction của Repository**.

## 53. Bài thực hành 3: listener Pub/Sub và Streams

### Pub/Sub

1. Tạo subscriber user với `+subscribe` và `&lab:channels:inventory-updated`.
2. Tạo publisher user với `+publish` và cùng channel.
3. Khởi động `RedisMessageListenerContainer` bằng subscriber user.
4. Đợi subscription sẵn sàng rồi publish event.
5. Assert callback nhận event.
6. Thử subscribe/publish channel khác bằng users tương ứng: NOPERM.
7. Ngắt kết nối Redis lab rồi khôi phục; test resubscribe.

### Streams

1. Tạo stream/group bằng bootstrap user.
2. Producer user chỉ có `XADD` trên stream key được phép.
3. Consumer user có `XREADGROUP`, `XACK`.
4. Recovery user có `XPENDING` và `XAUTOCLAIM` nếu thiết kế tách recovery.
5. Nhận và ACK message, kiểm tra PEL.
6. Tạo message pending do consumer A không ACK, cho B reclaim sau idle threshold.
7. Thu hồi `XACK` trong một test độc lập: đảm bảo denial không bị coi là xử lý hoàn tất.
8. Thử consumer `XADD` hoặc producer `XACK`: phải bị chặn.
9. Kiểm tra idempotency khi event được giao lại.

Pub/Sub cần **channel ACL**, Streams cần **key ACL**. Một listener chạy được khi khởi động chưa đủ: phải thử chính các đường publish, receive, ACK và reconnect.

## 54. Câu hỏi tự đánh giá

**1. Vì sao Redis PING thành công không chứng minh quyền tối thiểu đã đúng?**  
Vì PING không thực hiện các command/key/channel khác mà Cache, Repository và listener dùng.

**2. Spring Cache thường có những nhóm operation nào cần test?**  
Hit, miss/fill, put, evict theo key, clear toàn cache, put-if-absent và TTL.

**3. Vì sao clear có thể NOPERM khi GET/SET/DEL đều thành công?**  
Vì cache writer có thể cần `KEYS` hoặc `SCAN` để tìm keys trước khi xóa.

**4. Vì sao không nên cấp SCAN/KEYS rộng mà không đánh giá?**  
Vì có thể để lộ tên keys, tăng bề mặt quan sát và gây tác động vận hành nếu sử dụng sai.

**5. Repository save chỉ gọi HSET phải không?**  
Không. Tùy mapping nó có thể cập nhật index, ID tracking, TTL và metadata keys.

**6. Vì sao update @Indexed phải test cả index cũ và index mới?**  
Vì Hash có thể được đổi nhưng index cũ không được cleanup khi ACL thiếu quyền `SREM`.

**7. ACL key pattern và channel pattern khác nhau thế nào?**  
`~pattern` quy định quyền Redis keys; `&pattern` quy định Pub/Sub channels.

**8. Keyspace notification listener cần quyền gì ngoài key permissions?**  
Quyền subscribe/pattern subscribe vào Redis event channel phù hợp.

**9. Pub/Sub có lưu event cho subscriber offline không?**  
Không. Nó không cung cấp replay/ACK như Redis Streams.

**10. Vì sao Stream consumer chỉ có XREADGROUP chưa đủ?**  
Vì cần `XACK` và có thể cần `XPENDING`/`XAUTOCLAIM` cho recovery.

**11. XACK thất bại sau khi xử lý nghiệp vụ gây hậu quả gì?**  
Message còn pending và có thể bị giao lại, đòi hỏi idempotency.

**12. ACL DRYRUN có thay thế integration test Repository save không?**  
Không. Nó kiểm tra một command giả định; save có thể dùng nhiều commands/keys.

**13. Khi nào nên tách nhiều Redis ACL users?**  
Khi các thành phần có trách nhiệm/mức tin cậy khác nhau và lợi ích giảm blast radius vượt chi phí vận hành.

**14. Có nên cấp CONFIG SET cho app để khởi tạo keyspace notifications không?**  
Thông thường không. Nên để operator/migration quản lý server config khi có thể.

**15. Negative test được gọi là thành công khi nào?**  
Khi Redis thật từ chối hành động ngoài quyền, root cause có thể quy về NOPERM và không có side effect trái phép.

**16. Vì sao một test cache trả HTTP 200 chưa đủ?**  
Cache write có thể bị lỗi nhưng service fallback vẫn trả dữ liệu, làm permission regression bị che.

**17. Redis ACL có tự giới hạn số byte memory mỗi user sử dụng không?**  
Không mặc định như một quota nghiệp vụ riêng; cần capacity/resource isolation và giám sát thêm.

**18. Một permission test standalone có đủ cho Redis Cluster production không?**  
Không. Cluster có nhiều nodes/slots, routing, cache clear, notification scope và failover cần test riêng.

## 55. Checklist triển khai least privilege

- [ ] Xác định đầy đủ Cache, Repository và listener paths thực tế.
- [ ] Mỗi identity có documented owner, Redis endpoint và key/channel namespace.
- [ ] Không dùng default/admin credentials cho ứng dụng khi có thể tách app user.
- [ ] Command allowlist dựa trên thao tác được quan sát, không mặc định `+@all`.
- [ ] Key patterns phù hợp **key bytes/prefix** và metadata thực tế.
- [ ] Pub/Sub channel permissions được thiết kế riêng bằng `&...`.
- [ ] Cache hit, miss, write, evict, clear và TTL được test.
- [ ] Cache writer dùng KEYS hay SCAN được xác minh theo version/config.
- [ ] Repository CRUD, secondary indexes, update indexed field và delete cleanup được test.
- [ ] Repository expiration/keyspace notification không đòi quyền admin không cần thiết.
- [ ] Stream producer, consumer, ACK và reclaim chạy với identity đúng.
- [ ] Không để consumer có quyền XADD hoặc producer có quyền XACK nếu không cần.
- [ ] Negative tests chứng minh ngoài namespace và channel bị NOPERM.
- [ ] Root cause của NOPERM được quan sát, không bị CacheErrorHandler/fallback che hết.
- [ ] Redis ACL LOG/MONITOR chỉ dùng qua kênh vận hành được bảo vệ.
- [ ] Không thử denial trên keys/messages production.
- [ ] Không có `CONFIG SET`, `FLUSHALL`, `MONITOR` trong quyền runtime nếu không có lý do đặc biệt.
- [ ] Có test reconnect, rotation, failover và đúng principal sau reconnect.
- [ ] Redis Cluster tests bao gồm nhiều slots/nodes nếu production dùng Cluster.
- [ ] Secrets dùng secret manager/TLS, không hard-code hay log ra metrics.
- [ ] Permission changes có canary, rollback và bước reconciliation.
- [ ] Khi nâng Redis/Spring Data Redis, chạy lại permission contract tests.

## 56. Tổng kết

**Kiểm chứng quyền tối thiểu cho Spring Data Redis phải diễn ra ở cấp workflow, không chỉ một Redis command.**

- Với **Spring Cache**, kiểm chứng `GET`, cache fill `SET`, eviction `DEL`, clear với `SCAN`/`KEYS` theo writer thực tế, TTL và những nhánh lỗi/fallback.
- Với **Redis Repository**, kiểm chứng Redis Hash **và** secondary index, keyspace metadata, update/delete cleanup, TTL và expiration listener; không suy luận key pattern chỉ từ tên class Java.
- Với **listener Pub/Sub**, cấp command `SUBSCRIBE`/`PSUBSCRIBE` và **channel ACL** độc lập với key ACL; thử subscribe, reconnect và từ chối channel ngoài phạm vi.
- Với **Redis Streams**, phân biệt producer, consumer, bootstrap và recovery; test `XADD`, `XREADGROUP`, `XACK`, `XPENDING`/`XAUTOCLAIM` đúng theo trách nhiệm.
- Với **hạ tầng**, tách operator permissions khỏi application, dùng TLS/secrets, kiểm chứng Redis Cluster topology và bảo vệ thông tin ACL logs.

Phương pháp cốt lõi là: **liệt kê command/key/channel phát sinh → tạo allowlist → chạy positive tests → chạy negative tests → kiểm chứng hậu quả khi lỗi → quản lý thay đổi bằng regression suite**.

Một application chỉ thực sự đạt least privilege khi **những thao tác hợp lệ đều chạy và những thao tác không thuộc trách nhiệm đều bị Redis từ chối**, kể cả các đường hiếm gặp như cache clear, index cleanup, Stream reclaim hoặc reconnect sau failover.

## Tài liệu tham khảo

- [Redis — ACL Overview](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): users, key permissions, command categories và channel rules.
- [Redis — ACL SETUSER](https://redis.io/docs/latest/commands/acl-setuser/): tạo/chỉnh user và các ACL rule tokens.
- [Redis — ACL DRYRUN](https://redis.io/docs/latest/commands/acl-dryrun/): thử quyền command/key/channel mà không thực thi command.
- [Redis — ACL GETUSER](https://redis.io/docs/latest/commands/acl-getuser/): xem cấu hình quyền của một user.
- [Redis — ACL LOG](https://redis.io/docs/latest/commands/acl-log/): thông tin command/ACL denial theo server.
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): channel subscription và delivery semantics.
- [Redis — Keyspace Notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/): event channels, notify-keyspace-events và giới hạn độ bền.
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/): consumer group, ID, ACK và pending.
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/): đọc nhóm consumer.
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/): acknowledge message.
- [Redis — XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/): reclaim pending messages.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): RedisCacheManager, RedisCacheWriter và batch strategies.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): entity mapping, keyspace và repository lifecycle.
- [Spring Data Redis — Secondary Indexes](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/indexes.html): @Indexed và index maintenance.
- [Spring Data Redis — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html): entity expiration, shadow copy và events.
- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html): RedisMessageListenerContainer và subscriber management.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): Stream listener, group, ACK/recovery.
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): node topology, slot routing và multi-key constraints.
- [Spring Boot — Redis Auto-configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.redis): Lettuce/Redis connection settings.
