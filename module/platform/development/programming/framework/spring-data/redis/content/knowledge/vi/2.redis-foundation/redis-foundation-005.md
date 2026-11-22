# Redis logical database và giới hạn khi sử dụng Cluster

Trong Redis, **logical database** (cơ sở dữ liệu logic) là một *không gian khóa* được đánh số bên trong cùng một Redis server. Cơ chế này tiện khi muốn phân nhóm dữ liệu trên Redis chạy ở chế độ standalone, nhưng có một giới hạn quan trọng: **Redis Cluster chỉ hỗ trợ database số `0`**. Khi ứng dụng Spring Data Redis chuyển từ standalone sang Cluster, cách phân tách dữ liệu dựa vào `SELECT 1`, `SELECT 2`, … phải được thay thế bằng chiến lược khác.

Bài học này giải thích database logic hoạt động ra sao, cách cấu hình với Spring Data Redis, vì sao Cluster không hỗ trợ nhiều database, và cách thiết kế key để ứng dụng có thể mở rộng mà không bị phụ thuộc vào `SELECT`.

## 1. Logical database thực chất là gì?

Redis lưu dữ liệu dưới dạng các cặp **key–value**. Thay vì có bảng, schema và các quan hệ như cơ sở dữ liệu quan hệ, một Redis instance ở chế độ standalone có thể chứa nhiều không gian key độc lập, được đánh số từ `0` trở đi.

Ví dụ cấu hình Redis standalone thường dùng mặc định:

```conf
databases 16
```

Cấu hình này tạo ra **16 logical database**, với chỉ số `0` đến `15`. Con số 16 là **mặc định thông dụng**, không phải giới hạn cứng của Redis: quản trị viên có thể cấu hình số lượng database khác khi chạy standalone. Nếu client không chọn database, Redis sử dụng **DB 0**.

Hãy hình dung hai database có thể cùng chứa một key tên `user:1001` nhưng mang giá trị khác nhau:

```text
Redis standalone (cùng một tiến trình Redis)
│
├── DB 0
│   ├── user:1001  -> "An"
│   └── cart:9001  -> "..."
│
├── DB 1
│   ├── user:1001  -> "Bình"
│   └── token:abc  -> "..."
│
└── DB 2
    └── report:last-run -> "..."
```

Hai key `user:1001` thuộc DB 0 và DB 1 không ghi đè nhau vì chúng nằm trong hai không gian key khác nhau. Tuy nhiên, ba database trên **vẫn dùng chung tiến trình, RAM, CPU, kết nối mạng, chính sách giới hạn tài nguyên và hạ tầng lưu trữ** của cùng Redis instance.

> **Phân biệt:** Logical database của Redis không phải database có bảng và schema như MySQL/PostgreSQL, cũng không phải một Redis server độc lập. Nó chỉ cung cấp ranh giới tên key ở mức logic trong chế độ standalone.

## 2. Chọn database bằng lệnh `SELECT`

Với Redis standalone, lệnh `SELECT <index>` đổi database đang được sử dụng bởi **kết nối hiện tại**:

```redis
SET user:1001 "An"
SELECT 1
GET user:1001
SET user:1001 "Bình"
SELECT 0
GET user:1001
```

Kết quả mong đợi nếu bắt đầu từ DB 0 và hai DB chưa có dữ liệu liên quan:

```text
SET user:1001 "An"  -> OK           (ghi vào DB 0)
SELECT 1             -> OK           (đổi sang DB 1)
GET user:1001        -> (nil)        (DB 1 chưa có key)
SET user:1001 "Bình" -> OK           (ghi vào DB 1)
SELECT 0             -> OK           (trở lại DB 0)
GET user:1001        -> "An"
```

Có thể thao tác rõ ràng từ terminal:

```bash
# Mỗi lệnh tạo kết nối riêng và chọn database qua -n.
redis-cli -n 0 GET user:1001
redis-cli -n 1 GET user:1001

# Đếm key trong database hiện tại (ở đây là DB 1).
redis-cli -n 1 DBSIZE

# Liệt kê thống kê các DB có key hoặc key đang hết hạn.
redis-cli INFO keyspace
```

`INFO keyspace` có thể trả về dữ liệu tương tự:

```text
# Keyspace
db0:keys=12,expires=4,avg_ttl=...
db1:keys=8,expires=2,avg_ttl=...
```

Những thông số này phản ánh số key theo database trong **một Redis instance**. Không nên mặc định `INFO keyspace` phản ánh toàn bộ các node của một Cluster.

### `SELECT` gắn với connection, không gắn với từng key

`SELECT 1` chỉ thay đổi trạng thái của kết nối đang gửi lệnh. Nó không tạo database mới, không chuyển key từ DB 0 sang DB 1, và không tự ảnh hưởng tới các kết nối Redis khác.

Điểm này đặc biệt quan trọng khi dùng Spring Data Redis: ứng dụng thường làm việc qua `RedisConnectionFactory` và cơ chế quản lý/tái sử dụng kết nối. Không nên tự gọi `SELECT` trong mỗi hàm nghiệp vụ rồi giả định mọi thao tác tiếp theo sẽ chạy trên cùng connection đã chọn. Hãy cấu hình database ở **connection factory** khi dùng standalone; nếu cần tách nhóm dữ liệu trong Cluster, hãy thiết kế namespace bằng prefix của key.

## 3. Logical database phân tách được gì, không phân tách được gì?

| Khía cạnh | Nhiều DB trên cùng Redis standalone |
|---|---|
| Tên key | Độc lập: `DB 0/user:1` và `DB 1/user:1` là hai key riêng |
| `SELECT` | Chọn DB theo connection |
| Dữ liệu khi đọc/ghi | Chỉ truy cập key trong DB đang chọn |
| RAM và CPU | Dùng chung tài nguyên của Redis instance |
| Giới hạn bộ nhớ và eviction | Chính sách cấp instance, không cấp riêng từng DB |
| Persistence (RDB/AOF) | Cấu hình và vòng đời persistence của instance dùng chung |
| Khả năng mở rộng hoặc HA | Không có shard/replica riêng cho từng logical DB |
| Cô lập bảo mật | Không thay thế ACL, phân quyền hoặc Redis instance độc lập |

Ví dụ, nếu toàn Redis instance đạt `maxmemory`, cơ chế loại bỏ key (theo `maxmemory-policy`) không bảo đảm mỗi logical database được một hạn mức RAM riêng. Một nhóm ứng dụng có thể gây ảnh hưởng tới nhóm khác mặc dù chúng đang dùng DB khác nhau.

Hai lệnh quản trị cũng cần được phân biệt:

```bash
# Chỉ xóa key của database được chọn trên Redis standalone.
redis-cli -n 2 FLUSHDB

# Xóa key thuộc tất cả logical database trên Redis standalone.
redis-cli FLUSHALL
```

**Cảnh báo:** Đây là các lệnh xóa dữ liệu. Chỉ dùng trên môi trường thử nghiệm có kiểm soát; không chạy để “xác minh” trong môi trường đang chứa dữ liệu cần giữ lại. Với Redis Cluster, các lệnh quản trị gửi tới một node không mặc nhiên thực hiện trên mọi node trong cụm.

Nếu cần cách ly mạnh về tài nguyên, bảo mật hoặc vận hành, hãy cân nhắc **Redis instance/Cluster riêng** và chính sách ACL phù hợp, thay vì xem logical database là ranh giới cô lập hoàn chỉnh.

## 4. Redis Cluster dùng hash slot nên chỉ có DB 0

Redis Cluster phân phối key qua **16.384 hash slot** (`0` đến `16383`). Một key được ánh xạ tới một slot bằng công thức khái quát:

```text
hashSlot = CRC16(key) mod 16384
```

Mỗi primary node chịu trách nhiệm một tập hash slot; replica có thể sao chép dữ liệu của primary để hỗ trợ sẵn sàng cao. Khi key được ghi hoặc đọc, client hỗ trợ Cluster sẽ tìm đúng primary/node chịu trách nhiệm dựa vào slot và thông tin định tuyến do Cluster cung cấp.

```text
Ứng dụng Spring Data Redis / Cluster-aware client
                     │
             Tính slot của key
                     │
             16.384 hash slots
              /      |      \
       Primary A  Primary B  Primary C
       slots ...  slots ...  slots ...
           │          │          │
       Replica A  Replica B  Replica C
```

Cluster được thiết kế với **một không gian key duy nhất là DB 0**. Vì vậy:

- Không có khả năng sử dụng DB 1, DB 2, … để tách ứng dụng trong cùng Redis Cluster.
- Lệnh `SELECT` bị từ chối trong Cluster mode; không dùng `SELECT 0` như một thao tác cần thiết để “khởi tạo” Cluster.
- Các key được phân phối theo slot, không theo logical database.
- Cấu hình database khác `0` hoặc client cố gửi `SELECT` có thể khiến kết nối/thao tác thất bại, tùy driver và thời điểm khởi tạo kết nối.

Ví dụ khi kết nối tới một Cluster node:

```bash
redis-cli -c -h redis-node-1 -p 6379
```

```redis
SELECT 1
```

Phản hồi điển hình:

```text
(error) ERR SELECT is not allowed in cluster mode
```

Tùy phiên bản và cách driver diễn giải lỗi, thông báo cụ thể có thể khác nhau. **Giới hạn chức năng thì không thay đổi: Redis Cluster chỉ dùng DB 0.**

### Chuyển hướng `MOVED` và thao tác nhiều key

Redis Cluster còn có hai khái niệm cần hiểu khi thiết kế Spring Data Redis:

1. **Điều hướng slot:** Nếu gửi lệnh tới node không sở hữu slot của key, Redis có thể trả `MOVED`. Một client Cluster-aware như Lettuce sẽ dùng topology/redirect để truy cập đúng node. Khi slot đang được di chuyển, Redis cũng có thể sử dụng `ASK`.
2. **Thao tác nhiều key:** Các lệnh yêu cầu thao tác nhiều key cùng lúc, chẳng hạn một số lệnh trên nhiều key và transaction Lua nhiều key, thường đòi hỏi các key liên quan thuộc **cùng hash slot**. Nếu khác slot, có thể gặp lỗi `CROSSSLOT`.

Ví dụ hai key có prefix giống nhau chưa chắc ở cùng slot:

```text
shop:cart:1001
shop:cart:1002
```

Khi thực sự cần đặt các key liên quan vào cùng slot, Redis Cluster hỗ trợ **hash tag**: phần nằm trong cặp `{}` hợp lệ sẽ được dùng để tính hash slot.

```text
shop:{cart:1001}:items
shop:{cart:1001}:total
```

Hai key trên dùng chung chuỗi hash `cart:1001`, nên thuộc cùng slot. Hash tag **không** tạo thêm logical database; dùng quá nhiều key vào một hash tag còn có thể dồn tải về một slot/node. Chỉ áp dụng khi có yêu cầu thao tác đa key cụ thể, không dùng như cách mặc định để gom toàn bộ dữ liệu của một ứng dụng về một node.

## 5. Cấu hình Spring Data Redis khi dùng standalone

Với Spring Boot 3.x và Spring Data Redis, có thể chỉ định database cho standalone bằng thuộc tính `spring.data.redis.database` trong `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 2
      timeout: 2s
```

Khi ứng dụng dùng auto-configuration mặc định của Spring Boot, `RedisConnectionFactory` kết nối đến Redis standalone với DB 2. Những thành phần như `StringRedisTemplate` và `RedisTemplate` dùng cùng connection factory này sẽ mặc định làm việc với DB được cấu hình. Nếu không khai báo `database`, giá trị mặc định thường là `0`.

Ví dụ lưu giỏ hàng với `StringRedisTemplate`:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartRedisStore {
    private final StringRedisTemplate redis;

    public CartRedisStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String cartId, String json) {
        String key = "shop:dev:cart:" + cartId;
        redis.opsForValue().set(key, json, Duration.ofMinutes(30));
    }

    public String load(String cartId) {
        return redis.opsForValue().get("shop:dev:cart:" + cartId);
    }
}
```

Đoạn Java này không biết “DB 2” là gì: lựa chọn database thuộc về cấu hình kết nối, còn code chỉ thao tác trên các key. Prefix `shop:dev:cart:` giúp thể hiện phạm vi và dễ vận hành ngay cả khi standalone đang có nhiều DB.

**Lưu ý về version:** `spring.data.redis.*` là nhóm thuộc tính phổ biến trong Spring Boot 3.x. Ở dự án Spring Boot cũ hơn, tên thuộc tính có thể là `spring.redis.*`; phải đối chiếu đúng phiên bản framework mà ứng dụng thực sự sử dụng.

### Có nên tạo nhiều `RedisTemplate` cho nhiều DB?

Trong standalone, có thể tạo **các `RedisConnectionFactory` khác nhau** với chỉ số database riêng và gắn mỗi template vào factory tương ứng. Tuy nhiên, đây là cấu hình dành cho trường hợp thật sự cần nhiều DB; nó làm tăng độ phức tạp của việc quản lý connection factory và các bean phụ thuộc.

Không nên hiểu rằng tạo nhiều `RedisTemplate` tự sinh ra nhiều logical database. Mỗi template chỉ dùng các thiết lập của connection factory được cấp. Và khi chuyển sang Cluster, **không thể dùng nhiều connection factory trỏ tới các DB số khác nhau trong cùng Cluster** để tái tạo cách tách dữ liệu cũ.

## 6. Cấu hình Spring Data Redis khi dùng Redis Cluster

Với Cluster, khai báo danh sách seed node để client khám phá topology:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      cluster:
        nodes:
          - redis-node-1.example.net:6379
          - redis-node-2.example.net:6379
          - redis-node-3.example.net:6379
      timeout: 2s
```

Các host trên chỉ là địa chỉ minh họa. Trong ứng dụng thực tế, hãy dùng endpoint có thể kết nối được từ môi trường chạy, đồng thời cấu hình TLS, xác thực và các thuộc tính topology phù hợp với Cluster đang sử dụng.

Ở chế độ này:

- **Không cấu hình `spring.data.redis.database: 1`** hay bất kỳ DB khác `0`.
- Nên **bỏ hẳn thuộc tính `database`** để thể hiện rõ mô hình Cluster một database, đồng thời tránh giả định rằng có thể chọn database qua `SELECT`.
- Để driver hỗ trợ điều hướng slot; không tự chọn một node cố định cho toàn bộ key.
- Tập trung việc phân tách dữ liệu tại **tên key** hoặc ở mức **Cluster riêng** nếu cần cách ly mạnh.

Phần `CartRedisStore` ở trên vẫn dùng được về mặt API khi chuyển sang Cluster, bởi `StringRedisTemplate` không dựa vào `SELECT`. Thay đổi quan trọng nằm ở cấu hình kết nối và quy ước đặt key, cùng những ràng buộc slot cho lệnh nhiều key.

### Redis Cache, Spring Session và Redis Repository cũng phải đặt tên rõ ràng

Không chỉ code gọi `RedisTemplate` trực tiếp mới tạo key. Những thành phần khác như Spring Cache, Spring Session hoặc Spring Data Redis Repository cũng có thể ghi key vào Redis. Khi nhiều thành phần chia sẻ một Cluster, cần xác định rõ **prefix/namespace thực tế của từng thành phần**, gồm cả các key phụ như index, metadata hoặc TTL liên quan.

Ví dụ với Spring Cache, có thể cấu hình prefix thống nhất qua `RedisCacheConfiguration`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration
public class RedisCacheNamingConfig {
    @Bean
    RedisCacheConfiguration redisCacheConfiguration() {
        return RedisCacheConfiguration.defaultCacheConfig()
                .computePrefixWith(cacheName -> "shop:prod:cache:" + cacheName + "::");
    }
}
```

Ví dụ cache `products` có key `1001` sẽ có tên đầy đủ theo quy tắc `shop:prod:cache:products::1001` (với serializer key tương ứng). Đừng tắt cache key prefix khi nhiều cache hoặc ứng dụng dùng chung Redis, vì có thể gây đụng tên key. Với Session/Repository, hãy dùng cơ chế cấu hình namespace/keyspace mà phiên bản thư viện hỗ trợ; không mặc định chúng tự dùng prefix giống `RedisTemplate`.

## 7. Thay thế logical database bằng key namespace

Giả sử một hệ thống đang chạy standalone:

```text
DB 1: service-user      -> user:1001, session:abc
DB 2: service-order     -> order:2001, session:abc
DB 3: service-report    -> last-run
```

Nếu đem dữ liệu sang DB 0 trong cùng Cluster mà giữ nguyên tên key, hai key `session:abc` có thể **va chạm**. Redis sẽ không biết chúng từng thuộc DB 1 hay DB 2.

Hãy thiết kế lại tên key, ví dụ:

```text
shop:prod:user:user:1001
shop:prod:user:session:abc
shop:prod:order:order:2001
shop:prod:order:session:abc
shop:prod:report:last-run
```

Một quy tắc thường dùng:

```text
<system>:<environment>:<service>:<entity>:<identity>
```

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| System | `shop` | Nhận diện hệ thống sở hữu dữ liệu |
| Environment | `prod`, `staging` | Phân biệt môi trường khi cần dùng chung hạ tầng |
| Service | `user`, `order` | Phân biệt ứng dụng hoặc bounded context |
| Entity | `session`, `cart` | Loại dữ liệu |
| Identity | `1001`, `abc` | ID bản ghi/người dùng/phiên |

Quy tắc này chỉ là một gợi ý. Trong code thực tế nên có helper/service tạo key tập trung để giảm lỗi gõ prefix và thuận tiện đổi tên khi cần. Nếu có dữ liệu nhạy cảm, không đưa secret hoặc thông tin cá nhân dạng rõ vào tên key chỉ để phục vụ việc phân nhóm.

**Prefix không đồng nghĩa với phân quyền.** Các ứng dụng vẫn có thể đọc hoặc ghi key của nhau nếu dùng credential có đủ quyền. Có thể kết hợp Redis ACL với key pattern và tài khoản riêng cho từng ứng dụng. Nhưng ACL/prefix cũng không cung cấp mức cách ly tài nguyên tương đương Redis Cluster riêng.

## 8. Chuyển từ nhiều standalone DB sang Redis Cluster

Việc chuyển đổi cần coi là một **bài toán di trú dữ liệu và ứng dụng**; chỉ sửa `application.yml` từ `database: 2` sang `cluster.nodes` là chưa đủ.

### Bước 1 — Kiểm kê những logical database đang được dùng

Xác định mọi ứng dụng/worker/job sử dụng Redis, database index, loại key, TTL, serialization và quyền truy cập. Trên standalone, có thể xem thống kê:

```bash
redis-cli INFO keyspace
redis-cli -n 1 --scan --pattern 'user:*'
redis-cli -n 2 --scan --pattern '*'
```

`SCAN` là cơ chế duyệt tăng dần phù hợp hơn `KEYS *` cho hệ thống nhiều key, nhưng không cung cấp snapshot nhất quán khi dữ liệu đang thay đổi. Cần chiến lược xử lý key thêm/xóa trong thời gian migrate.

### Bước 2 — Thiết kế namespace trước khi copy dữ liệu

Lập mapping tường minh:

| Nguồn standalone | Key cũ | Key đích trong Cluster |
|---|---|---|
| DB 1 | `user:1001` | `shop:prod:user:user:1001` |
| DB 1 | `session:abc` | `shop:prod:user:session:abc` |
| DB 2 | `session:abc` | `shop:prod:order:session:abc` |

Tại đây cũng cần quyết định key nào thực sự phải cùng slot để hỗ trợ thao tác đa key; chỉ đặt hash tag cho những nhóm có yêu cầu đó.

### Bước 3 — Chuyển dữ liệu theo cách bảo toàn ý nghĩa

Khi di trú, cần giữ đúng **kiểu dữ liệu Redis** (string, hash, list, set, sorted set, stream…), giá trị nhị phân/serializer và **TTL còn lại**. Ví dụ nếu một session chỉ còn hạn 10 phút, không nên vô tình đặt TTL thành 30 ngày sau khi copy.

Các cách thực hiện có thể gồm script di trú sử dụng client phù hợp, quy trình đọc/ghi từng kiểu dữ liệu hoặc công cụ migrate hỗ trợ Redis Cluster. Không có một lệnh `SELECT` hay thao tác đổi cấu hình nào tự động chuyển toàn bộ các DB standalone thành namespace trong Cluster.

### Bước 4 — Điều chỉnh code, cache và những lệnh phụ thuộc DB/slot

Rà lại nơi ứng dụng:

- Cấu hình `database` khác `0`, gọi trực tiếp `SELECT` hoặc tạo nhiều connection factory để chia DB.
- Dùng prefix trùng nhau giữa các ứng dụng; tạo key qua RedisTemplate, cache, session và repository.
- Chạy Lua script, transaction, `MGET`/`MSET`, phép set trên nhiều key hoặc thao tác atomic đa key mà trước đó giả định mọi key nằm cùng một node.
- Thực hiện `SCAN`, thống kê hoặc xóa key trên một connection và giả định đó là toàn bộ dữ liệu Cluster.

### Bước 5 — Kiểm tra và chuyển traffic có kiểm soát

Đối chiếu số lượng/key mẫu, kiểu dữ liệu, giá trị, TTL và kết quả nghiệp vụ sau khi migrate. Để hạn chế mất ghi khi chuyển traffic, phải có phương án rõ ràng như đóng băng ghi ngắn hạn, ghi song song có kiểm soát hoặc đồng bộ phần thay đổi cuối cùng. Phương án chính xác phụ thuộc hệ thống và khả năng chấp nhận downtime.

Sau khi chạy trên Cluster, việc `SCAN` hoặc `DBSIZE` một node **không đại diện cho tất cả primary nodes**. Với các phép kiểm kê thủ công, cần duyệt từng primary; dùng client/công cụ có hỗ trợ Cluster nếu muốn tổng hợp ở mức toàn cụm.

## 9. Thực hành: quan sát sự khác biệt

Các thao tác dưới đây được chia thành hai môi trường thử nghiệm khác nhau. Chúng không yêu cầu xóa dữ liệu và dùng prefix riêng để tránh nhầm với key ứng dụng khác.

### Thực hành A — Redis standalone

```bash
redis-cli -n 0 SET demo:logical-db:sample "from-db0"
redis-cli -n 1 SET demo:logical-db:sample "from-db1"

redis-cli -n 0 GET demo:logical-db:sample
# "from-db0"

redis-cli -n 1 GET demo:logical-db:sample
# "from-db1"

redis-cli INFO keyspace
```

Rút ra được: cùng tên key có thể chứa giá trị khác nhau ở hai database. Hãy nhớ rằng `-n 1` chỉ dùng khi standalone đã cấu hình ít nhất hai DB.

### Thực hành B — Redis Cluster

```bash
redis-cli -c -h redis-node-1 -p 6379 SET demo:cluster:user:1001 "An"
redis-cli -c -h redis-node-1 -p 6379 GET demo:cluster:user:1001

# Quan sát slot của các key.
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT demo:cluster:user:1001
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT demo:cluster:user:1002

# Hai key có cùng hash tag phải trả về cùng slot.
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT 'demo:{cart:1001}:items'
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT 'demo:{cart:1001}:total'
```

Trong Cluster, `redis-cli -c` hỗ trợ redirect khi key thuộc node khác. Thử `SELECT 1` trong phiên kết nối Cluster sẽ bị từ chối. Không cần tạo DB 1 để kiểm tra; điều quan trọng là thấy được **một keyspace duy nhất**, định tuyến bằng hash slot.

## 10. Một số nhầm lẫn thường gặp

**“Có thể bật `databases 16` để Cluster hỗ trợ DB 1–15 không?”**

Không. Tham số `databases` có ý nghĩa với standalone; Redis Cluster vẫn chỉ hỗ trợ DB 0. Không có cấu hình đơn giản nào làm Cluster hỗ trợ nhiều logical database.

**“Nếu cấu hình `spring.data.redis.database: 0` thì Cluster chắc chắn dùng được?”**

Chỉ số `0` phù hợp với không gian key của Cluster, nhưng điều đó không quyết định khả năng kết nối. Client phải được cấu hình theo Cluster và không gửi lệnh `SELECT` trái phép. Cách biểu đạt rõ ràng nhất trong Spring Boot là cấu hình `cluster.nodes` và **không khai báo database**.

**“Prefix `service-a:` có đảm bảo mọi key của service A nằm chung node?”**

Không. Hash slot được tính từ key, nên prefix chung vẫn có thể phân phối key lên nhiều node. Chỉ một hash tag phù hợp mới ép các key liên quan về cùng slot; thường không nên ép toàn bộ key của một service vào một slot.

**“`@RedisHash` hay tên cache có tạo database riêng không?”**

Không. `@RedisHash` mô tả keyspace/mapping cho entity Redis Repository; cache name tham gia cách đặt key khi dùng Spring Cache. Những khái niệm đó khác với logical database được chọn bằng `SELECT`.

**“Muốn dev, staging và production độc lập thì chỉ cần key prefix?”**

Prefix giúp tránh va chạm tên key, nhưng các môi trường vẫn chia sẻ tài nguyên và có thể ảnh hưởng nhau. Với production hoặc yêu cầu vận hành/bảo mật cao, nên cân nhắc hạ tầng Redis độc lập và credential/ACL riêng.

**“Có thể dùng `DBSIZE` để đếm tổng số key của Cluster không?”**

Không nên. `DBSIZE` trên một node phản ánh dữ liệu của node được truy vấn, không tự cộng số key của tất cả primary nodes trong Cluster. Công cụ giám sát cần hiểu topology và tổng hợp đúng phạm vi.

## 11. Chọn chiến lược phân tách dữ liệu

| Nhu cầu | Standalone nhiều DB | Prefix/namespace trong Cluster | Redis instance/Cluster riêng |
|---|---|---|---|
| Tránh va chạm tên key | Có | Có, nếu quy ước chặt chẽ | Có |
| Dùng khi Redis Cluster bật | Không | Có | Có |
| Cô lập CPU/RAM | Không | Không | Có, nếu hạ tầng tài nguyên tách biệt |
| Cô lập quyền truy cập | Không phải ranh giới bảo mật | Kết hợp ACL để giới hạn key | Có thể cấp quyền và chính sách độc lập |
| Đơn giản cho môi trường thử nghiệm standalone | Có | Có | Thường tốn công hơn |
| Phù hợp mở rộng theo hash slot | Không | Có | Có |

Khi viết ứng dụng Spring Data Redis mới có khả năng triển khai lên Cluster, lựa chọn thực tế là **dùng DB 0, xây dựng namespace key nhất quán, sử dụng client hiểu Cluster và kiểm tra những thao tác đa key**. Nếu các nhóm dữ liệu cần cô lập mạnh về tài nguyên hoặc vận hành, dùng Redis deployment riêng. Cách tổ chức này tránh phụ thuộc vào tính năng `SELECT` chỉ có ở standalone và giúp quá trình mở rộng sau này rõ ràng hơn.
