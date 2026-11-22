# Khám phá primary và thay đổi topology khi failover

Trong một hệ thống Redis có **replication** và **Sentinel**, ứng dụng không nên giả định một máy chủ cố định sẽ mãi đóng vai trò **primary**. Redis replica sao chép dữ liệu từ primary, còn Redis Sentinel giám sát các instance và điều phối việc chọn một replica để thăng cấp khi primary gặp sự cố. Sau failover, địa chỉ primary có thể đổi từ máy này sang máy khác; những connection cũ của ứng dụng phải được làm mới và các lệnh ghi mới cần đến đúng primary mới.

Trong **Spring Data Redis**, việc khám phá primary thường do Redis client và `RedisConnectionFactory` xử lý. Với cấu hình Sentinel, ứng dụng cung cấp **tên master logic** và danh sách các Sentinel node, thay vì ghim vào địa chỉ Redis primary ban đầu. Client hỏi Sentinel để tìm primary hiện tại, thiết lập connection rồi khôi phục connection khi topology thay đổi.

Bài học trình bày cơ chế khám phá primary, các giai đoạn failover, cấu hình Spring Boot/Lettuce, tác động đến thao tác đọc–ghi, retry và cách kiểm chứng trạng thái sau khi chuyển vai trò.

## 1. Primary, replica và Sentinel làm việc gì?

Redis replication thường có một primary chấp nhận các lệnh ghi và một hoặc nhiều replica sao chép dữ liệu từ primary. Replication mặc định là **bất đồng bộ**, nên replica có thể chậm hơn primary.

Redis Sentinel là tiến trình giám sát riêng, thực hiện phát hiện lỗi, thông báo trạng thái, điều phối failover và cung cấp địa chỉ primary hiện tại. **Sentinel không phải proxy chuyển tiếp các lệnh `GET`, `SET`, `HGET`** và không trực tiếp lưu dữ liệu nghiệp vụ như Redis data node.

| Thành phần | Chức năng | Cổng thường gặp |
| --- | --- | --- |
| Redis primary | Nhận ghi, phục vụ dữ liệu và phát luồng replication | `6379` |
| Redis replica | Sao chép dữ liệu; có thể phục vụ đọc nếu client được cấu hình | `6379` hoặc cổng được chỉ định |
| Redis Sentinel | Giám sát, khám phá primary và điều phối failover | `26379` |
| Spring Data Redis | API Java để truy cập Redis qua các template, repository | Không phải máy chủ Redis |
| Lettuce hoặc Jedis | Driver kết nối tới Redis/Sentinel và phục hồi theo cấu hình | Kết nối TCP/TLS |

Mô hình ví dụ:

~~~text
                    Spring Boot application
                             |
                 "Primary của mymaster là ai?"
                             |
                 +-----------+-----------+
                 |           |           |
                 v           v           v
             Sentinel S1 Sentinel S2 Sentinel S3
                 |           |           |
                 +-----------+-----------+
                             |
                         Giám sát
                             |
                             v
                    Redis A (PRIMARY)
                      /           \
                     v             v
              Redis B (REPLICA) Redis C (REPLICA)
~~~

Các Sentinel cùng theo dõi một nhóm replication có tên logic `mymaster`. Tên này **không phải hostname**; sau failover nó vẫn giữ nguyên dù primary vật lý đã đổi.

## 2. Vì sao không ghim địa chỉ primary?

Nếu cấu hình ứng dụng chỉ trỏ vào:

~~~yaml
spring:
  data:
    redis:
      host: redis-a.internal
      port: 6379
~~~

thì ban đầu ứng dụng hoạt động khi Redis A là primary. Nhưng nếu A hỏng và B được thăng cấp, ứng dụng có thể vẫn cố kết nối tới A. Khi A quay lại với vai trò replica, lệnh ghi vào A có thể bị từ chối.

Các vấn đề có thể xảy ra:

- Lỗi kết nối trong lúc Redis A ngừng hoạt động.
- Lệnh ghi `READONLY` nếu A đang là replica.
- Connection cũ bị reset hoặc timeout khi role thay đổi.
- Phải chỉnh cấu hình hoặc restart ứng dụng nếu không có cơ chế khám phá primary mới.

Với client hiểu Sentinel, đường truy cập là:

~~~text
Trước failover:
  App → Sentinel: get-master-addr-by-name mymaster
  Sentinel → App: redis-a.internal:6379
  App → Redis A: SET ...

Sau failover:
  App → Sentinel: get-master-addr-by-name mymaster
  Sentinel → App: redis-b.internal:6379
  App → Redis B: SET ...
~~~

Đây là **discovery theo vai trò**: ứng dụng biết cần kết nối tới primary hiện tại, không phụ thuộc một địa chỉ cứng.

## 3. Sentinel cung cấp thông tin primary như thế nào?

Sentinel theo dõi các Redis instance, trao đổi thông tin với Sentinel khác, nhận biết replica và ghi nhận topology của nhóm. Client có thể hỏi:

~~~bash
redis-cli -h sentinel-1.internal -p 26379 SENTINEL get-master-addr-by-name mymaster
~~~

Phản hồi ban đầu:

~~~text
1) "redis-a.internal"
2) "6379"
~~~

Sau failover:

~~~text
1) "redis-b.internal"
2) "6379"
~~~

Các lệnh quan sát khác:

~~~bash
redis-cli -h sentinel-1.internal -p 26379 SENTINEL master mymaster
redis-cli -h sentinel-1.internal -p 26379 SENTINEL replicas mymaster
redis-cli -h sentinel-1.internal -p 26379 SENTINEL sentinels mymaster
~~~

`SENTINEL master` cho biết thông tin master mà Sentinel đang theo dõi, `SENTINEL replicas` liệt kê các replica đã phát hiện, và `SENTINEL sentinels` cho biết những Sentinel ngang hàng. Trong giai đoạn failover, các Sentinel có thể chưa hội tụ metadata ngay lập tức; một phản hồi tức thời từ một node chưa chắc là snapshot nhất quán của toàn bộ hệ thống.

### Tên master và quorum

Một cấu hình Sentinel minh họa:

~~~text
port 26379
sentinel monitor mymaster 10.0.0.11 6379 2
sentinel down-after-milliseconds mymaster 5000
sentinel failover-timeout mymaster 60000
~~~

Ở đây:

- `mymaster` là tên nhóm Redis được theo dõi.
- `10.0.0.11:6379` là địa chỉ primary ban đầu.
- `2` là quorum để công nhận rằng master đã gặp lỗi theo điều kiện Sentinel.
- `down-after-milliseconds` là khoảng thời gian liên quan đến phát hiện mất phản hồi.
- `failover-timeout` điều chỉnh các mốc điều phối failover.

**Quorum không hoàn toàn đồng nghĩa số phiếu cần để được phép thực hiện failover.** Sentinel còn dùng cơ chế bầu leader đòi hỏi đa số Sentinel đủ điều kiện. Với ba Sentinel độc lập, quorum 2 là cấu hình phổ biến, nhưng phải đánh giá failure domain và khả năng đạt đa số khi một số Sentinel bị mất.

Đặt ba Sentinel trên cùng một máy không bảo vệ được khi cả máy đó hỏng. Sentinel nên phân bố ở những host hoặc vùng lỗi phù hợp.

## 4. Trình tự một lần failover

Khi Redis A mất phản hồi:

1. **SDOWN:** Một Sentinel tự nhận định A đang *subjectively down* vì không phản hồi như yêu cầu.
2. **ODOWN:** Các Sentinel trao đổi trạng thái, đạt quorum và xác nhận A *objectively down*.
3. **Bầu điều phối:** Sentinel lựa chọn leader cho vòng failover theo cơ chế bỏ phiếu.
4. **Chọn replica:** Leader đánh giá các replica còn khả dụng, trạng thái đồng bộ và những ưu tiên liên quan.
5. **Thăng cấp:** Replica B được chuyển sang primary mới.
6. **Chuyển replication:** Các replica khác được hướng tới B. Khi A trở lại, nó có thể được cấu hình thành replica của B.
7. **Thông báo topology:** Sentinel cập nhật master address và phát sự kiện chuyển master.
8. **Client khôi phục:** Redis driver nhận biết primary đã đổi, kết nối lại tới B; lệnh mới tiếp tục đi qua primary mới.

~~~text
             Trước failover                     Sau failover

          Redis A [PRIMARY]                   Redis A [DOWN]
             /         \                           |
            v           v                          | có thể quay lại
      Redis B [R]   Redis C [R]                     v
                                               Redis A [REPLICA]

                                              Redis B [PRIMARY]
                                                     |
                                                     v
                                              Redis C [REPLICA]

          App → Redis A                      App → Redis B
~~~

**Failover không phải chuyển đổi tức thì hoặc hoàn toàn không gián đoạn.** Trong khoảng thời gian phát hiện sự cố, bầu primary mới và cập nhật connection, một số lệnh có thể timeout, bị từ chối hoặc gặp connection error. Spring Data Redis có thể phục hồi thông qua driver, nhưng vẫn cần chính sách xử lý lỗi tại tầng ứng dụng.

### Redis Sentinel có bảo đảm không mất dữ liệu không?

Không. Replication mặc định bất đồng bộ. Redis A có thể trả thành công cho một lệnh `SET` trước khi B nhận thay đổi. Nếu A ngừng hoạt động đúng lúc và B được thăng cấp, một số ghi đã được A xác nhận có thể không tồn tại trên primary mới.

Các biện pháp như persistence, theo dõi replication lag hoặc lệnh xác nhận replication (`WAIT` và những cơ chế phù hợp với phiên bản Redis) có thể giảm rủi ro trong một số trường hợp, nhưng **không tự biến Sentinel thành một giao thức ghi đồng bộ hoàn toàn không mất dữ liệu**. Cần xác định rõ Redis đang là cache hay nguồn dữ liệu quan trọng để thiết kế chính sách khôi phục tương ứng.

## 5. Cấu hình Spring Boot kết nối Sentinel

Với Spring Boot 3.x, có thể cấu hình Sentinel cho Lettuce bằng `application.yml`:

~~~yaml
spring:
  data:
    redis:
      client-type: lettuce
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.internal:26379
          - sentinel-2.internal:26379
          - sentinel-3.internal:26379
      connect-timeout: 2s
      timeout: 3s
~~~

Danh sách `nodes` là những địa chỉ Sentinel mà ứng dụng có thể truy cập. Không đưa địa chỉ Redis primary cố định vào làm một điểm kết nối thay thế cho cơ chế Sentinel khi mục tiêu là tự khám phá role.

Nếu Redis và Sentinel đều có xác thực, cần phân biệt **credentials truy cập data nodes** với **credentials dành cho Sentinel**:

~~~yaml
spring:
  data:
    redis:
      username: redis-app-user
      password: REDIS_DATA_PASSWORD_FROM_SECRET_STORE
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.internal:26379
          - sentinel-2.internal:26379
          - sentinel-3.internal:26379
        username: sentinel-app-user
        password: SENTINEL_PASSWORD_FROM_SECRET_STORE
~~~

Các giá trị password chỉ là chỗ giữ vị trí minh họa; trong ứng dụng thật hãy inject từ môi trường/secret manager, không commit bí mật vào source code. Nếu hạ tầng không yêu cầu Redis/Sentinel username hoặc password, cấu hình những trường đó theo cơ chế xác thực đang dùng.

Tùy phiên bản Spring Boot/Spring Data Redis, cần xác nhận các tên property và khả năng của driver được chọn. Với Spring Boot cũ, namespace `spring.redis` có thể khác `spring.data.redis` ở các phiên bản hiện đại.

### Cấu hình Java với `RedisSentinelConfiguration`

Khi không muốn để Spring Boot tự tạo connection factory, có thể cấu hình thủ công:

~~~java
package com.example.redis.sentinel;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisSentinelClientConfig {

    @Bean
    RedisConnectionFactory redisConnectionFactory() {
        RedisSentinelConfiguration sentinel =
            new RedisSentinelConfiguration()
                .master("mymaster")
                .sentinel("sentinel-1.internal", 26379)
                .sentinel("sentinel-2.internal", 26379)
                .sentinel("sentinel-3.internal", 26379);

        LettuceClientConfiguration client =
            LettuceClientConfiguration.builder()
                .commandTimeout(Duration.ofSeconds(3))
                .build();

        return new LettuceConnectionFactory(sentinel, client);
    }
}
~~~

Ví dụ minh họa discovery nên chưa thêm Redis/Sentinel ACL, TLS hoặc các điều kiện bảo mật khác. Khi cần, cấu hình chúng trên Sentinel configuration và Lettuce client configuration tương ứng. Tránh vô tình tạo nhiều `RedisConnectionFactory` không nhất quán khi ứng dụng vừa có auto-configuration vừa có bean tùy biến.

Với một factory Sentinel-aware, `RedisTemplate`, `StringRedisTemplate`, Spring Cache và nhiều API Spring Data Redis khác đều sử dụng cơ chế kết nối bên dưới. Business service không cần tự chạy `SENTINEL get-master-addr-by-name` trước mỗi lệnh Redis.

## 6. Khám phá primary khi khởi động

Luồng khởi tạo:

~~~text
           Spring Boot khởi động
                    |
                    v
      Đọc mymaster + Sentinel nodes
                    |
                    v
       LettuceConnectionFactory
                    |
                    v
         Tìm Sentinel khả dụng
                    |
                    v
    Hỏi primary của nhóm "mymaster"
                    |
                    v
          Nhận host:port Redis
                    |
                    v
       Kết nối Redis primary hiện tại
                    |
                    v
   RedisTemplate / repository / cache manager
                    |
                    v
              GET / SET / HGET
~~~

Client có thể thử nhiều Sentinel nếu một node không phản hồi. Nhưng cần phân biệt: **một Sentinel trả lời discovery** và **đủ số Sentinel để bầu primary mới** là hai điều kiện khác nhau. Khi đa số Sentinel không còn khả dụng, client có thể vẫn đọc được thông tin cũ nhưng hệ thống không thể tự động hoàn tất failover mới.

Sentinel là **điểm khám phá**, không phải proxy dữ liệu:

~~~text
App → Sentinel       : hỏi địa chỉ primary
App → Redis primary  : thực hiện các lệnh GET/SET
~~~

Sau khi kết nối trực tiếp tới primary, ứng dụng không truyền mọi lệnh qua cổng Sentinel `26379`.

## 7. Điều gì xảy ra với connection khi primary thay đổi?

Giả sử Redis A đang phục vụ một số connection của ứng dụng và B được thăng cấp:

- Connection tới A có thể bị ngắt nếu A chết.
- Connection tới A vẫn có thể tồn tại nếu A bị cô lập hoặc sau khi A quay lại ở vai trò khác.
- Lệnh đang thực thi có thể gặp connection reset, timeout hoặc `READONLY`.
- Lettuce Sentinel-aware có thể cập nhật endpoint, reconnect và sử dụng B cho các connection thích hợp.
- Những thao tác mới sau khi driver phục hồi được gửi đến primary hiện tại.

Timeline minh họa:

~~~text
T0    SET thành công tại Redis A
T1    Redis A hỏng / mạng mất kết nối
T2    Một số command gặp lỗi
T3    Sentinel nhận định ODOWN, điều phối failover
T4    Redis B được thăng cấp
T5    Client cập nhật địa chỉ primary và tạo connection
T6    Lệnh mới phục hồi tại Redis B
~~~

Khoảng thời gian `T1–T6` phụ thuộc timeout phát hiện Sentinel, cơ chế election, độ trễ mạng, Redis driver và tải ứng dụng. Không thể cam kết một số giây cố định chỉ vì đã bật Sentinel.

### Đừng tự cache địa chỉ primary từ một lookup duy nhất

Một anti-pattern:

~~~java
// Chỉ hỏi Sentinel một lần, rồi dùng client standalone mãi mãi.
String primaryHost = discoverPrimaryAtStartup();
RedisStandaloneConfiguration config =
    new RedisStandaloneConfiguration(primaryHost, 6379);
~~~

Đoạn này chuyển discovery thành một lookup cố định. Khi topology đổi, `RedisStandaloneConfiguration` không tự cập nhật vai trò. Dùng `RedisSentinelConfiguration` với driver hỗ trợ là cách thích hợp hơn cho topology Sentinel.

## 8. Đọc từ replica và giới hạn nhất quán

Để giảm tải primary, một số ứng dụng cấu hình Lettuce ưu tiên đọc từ replica. Cấu hình programmatic có thể dùng:

~~~java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .readFrom(ReadFrom.REPLICA_PREFERRED)
        .commandTimeout(Duration.ofSeconds(3))
        .build();
~~~

`ReadFrom.REPLICA_PREFERRED` ưu tiên replica cho những lệnh đọc mà driver nhận diện là read-only; khả năng fallback còn phụ thuộc topology và kết nối thực tế. Cần dùng client configuration này khi tạo `LettuceConnectionFactory` tương ứng.

**Đọc replica có thể nhận dữ liệu cũ do replication bất đồng bộ:**

~~~text
Client -- SET counter=100 --> Primary
                                 |
                          Đồng bộ bất đồng bộ
                                 |
                                 v
Client -- GET counter ------> Replica
                                 |
                                 v
                      Có thể vẫn thấy counter=99
~~~

Nếu một API yêu cầu **read-your-writes** sau lệnh cập nhật quan trọng, hãy cân nhắc đọc từ primary hoặc thiết kế cơ chế nhất quán riêng. Khi failover, replica có thể đổi vai trò thành primary và những replica khác cần được cấu hình lại; giả định đọc luôn mới như primary là sai.

Với cache thường, replica reads có thể được chấp nhận. Với quyền truy cập, số dư, hạn mức hay dữ liệu bắt buộc nhất quán, phải đánh giá rõ độ trễ replication và ngữ nghĩa đọc trước khi cho phép.

## 9. Retry trong cửa sổ failover

Khi Redis mất kết nối đúng lúc client gửi command, một timeout **không chứng minh** Redis chưa thực thi lệnh. Nếu retry không đúng loại thao tác, nghiệp vụ có thể bị áp dụng hai lần.

| Thao tác | Retry có thể gây gì? | Cách suy nghĩ |
| --- | --- | --- |
| `GET key` | Kết quả có thể thay đổi giữa hai lần đọc | Thường chấp nhận retry giới hạn cho truy vấn |
| `SET key value` | Có thể ghi đè thay đổi mới hơn | Lũy đẳng về cùng giá trị chỉ khi ngữ cảnh không có cạnh tranh |
| `DEL key` | Số lượng key đã xóa trả về khác nhau | Có thể phù hợp nếu mục tiêu cuối cùng là key không tồn tại |
| `INCR`/`DECR` | Tăng/giảm hai lần nếu lệnh đầu đã chạy | Không retry mù |
| `LPUSH`/`RPUSH` | Thêm phần tử trùng | Cần dedupe nếu nghiệp vụ không chấp nhận |
| `XADD` sinh ID tự động | Tạo hai entry có cùng nội dung | Cần event ID ổn định và kiểm soát trùng |
| `SET` kèm TTL | Làm mới lại mốc hết hạn khi retry | Cân nhắc deadline nghiệp vụ |

Tại tầng ứng dụng nên trả lời:

1. Nếu Redis đã áp dụng lệnh nhưng phản hồi bị mất, thử lại có an toàn không?
2. Nếu Redis đã đổi primary, nguồn nào xác định trạng thái nghiệp vụ cuối cùng?
3. Retry bao nhiêu lần, timeout thế nào và có backoff/jitter không?
4. Khi hết retry, API trả lỗi, fallback hay đưa tác vụ vào queue?
5. Khi hàng trăm instance cùng retry, upstream/database có chịu được không?

Không bật retry vô hạn cho tất cả command. `INCR`, ghi sự kiện, thay đổi số dư hay giao dịch nhiều bước cần cách giải quyết trùng lặp/idempotency được thiết kế theo nghiệp vụ.

### Ví dụ cache-aside có đường fallback khi Redis lỗi

~~~java
package com.example.redis.sentinel;

import java.time.Duration;
import java.util.Objects;
import java.util.function.Supplier;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;

    public ProductCacheReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String load(
            String id,
            Supplier<String> fetchFromDatabase) {
        Objects.requireNonNull(id);
        Objects.requireNonNull(fetchFromDatabase);

        String key = "cache:product:" + id;
        try {
            String cached = redis.opsForValue().get(key);
            if (cached != null) {
                return cached;
            }
        } catch (RedisConnectionFailureException error) {
            // Cache cho phép miss tạm thời; production cần metric.
        }

        String loaded = Objects.requireNonNull(
            fetchFromDatabase.get()
        );

        try {
            redis.opsForValue().set(
                key, loaded, Duration.ofMinutes(5)
            );
        } catch (RedisConnectionFailureException error) {
            // Best-effort cache: vẫn trả dữ liệu từ nguồn chính.
        }
        return loaded;
    }
}
~~~

Đây là lựa chọn cho cache **không phải nguồn dữ liệu chính**. Không áp dụng fallback im lặng khi Redis thực sự giữ trạng thái quan trọng của nghiệp vụ. Mã minh họa chỉ bắt lỗi kết nối; trong thực tế có thể gặp timeout hoặc lỗi driver khác, cần phân loại cụ thể. Không catch toàn bộ `RuntimeException` rồi che lỗi serialization hoặc lập trình.

Ví dụ chưa chống nhiều request cùng cache miss; khi failover làm tỷ lệ miss tăng, nên có rate limit, single-flight, circuit breaker hoặc kiểm soát concurrency để tránh làm database quá tải.

## 10. Tác động đến Spring Cache, Repository và transaction

Nếu ứng dụng dùng `RedisCacheManager`, `RedisTemplate` hoặc Redis Repository dựa trên cùng `RedisConnectionFactory` Sentinel-aware, các tầng này có thể hưởng cơ chế khám phá địa chỉ qua driver.

Tuy nhiên, **khôi phục connection không đồng nghĩa khôi phục hoàn toàn các command đã gửi trước sự cố**:

- Một pipeline có thể đã gửi một phần lệnh nhưng chưa nhận đầy đủ phản hồi.
- Một transaction `MULTI/EXEC` có thể gặp lỗi kết nối đúng lúc client không biết Redis đã thực thi hay chưa.
- Repository có thể ghi một entity bằng nhiều key, ví dụ Hash và secondary indexes; failover trong chuỗi thao tác không tự biến toàn bộ chuỗi thành transaction nguyên tử.
- Spring Cache có thể tăng cache miss, đồng thời nhiều request cùng tải lại dữ liệu từ nguồn.

Sentinel giúp tìm **primary mới**, không phải transaction manager của những hệ thống khác. Đặc biệt, Redis replication bất đồng bộ có nghĩa rằng một lệnh đã thành công tại primary cũ vẫn có nguy cơ không nằm trong dữ liệu primary mới.

## 11. Khác biệt giữa Redis Sentinel và Redis Cluster

Hai mô hình đều có topology thay đổi nhưng mục tiêu khác nhau:

| Khía cạnh | Redis + Sentinel | Redis Cluster |
| --- | --- | --- |
| Mục tiêu | Tính sẵn sàng cao cho một nhóm Redis replication | Chia keyspace thành nhiều slot trên nhiều primary |
| Ghi dữ liệu | Một primary hiện tại của nhóm | Primary sở hữu hash slot tương ứng |
| Discovery | Master name + danh sách Sentinel | Cluster node/slot topology |
| Failover | Replica được thăng cấp cho nhóm | Replica của shard có thể thành primary |
| Tự động phân mảnh key? | **Không** | **Có** |
| Khả năng client phải hỗ trợ | Sentinel discovery/reconnect | Slot map, redirect `MOVED`/`ASK` và topology refresh |

Không cấu hình `spring.data.redis.sentinel.master` để kết nối Redis Cluster và kỳ vọng client tự hiểu hash slot. Với Cluster, cần dùng Redis Cluster configuration của Spring Data Redis.

Sentinel không làm tăng khả năng mở rộng write throughput bằng cách chia dữ liệu cho nhiều primary độc lập. Nếu bài toán cần sharding, hãy đánh giá Redis Cluster hoặc một mô hình phân vùng khác.

## 12. Địa chỉ được Sentinel công bố phải kết nối được

Một lỗi rất thường gặp với Docker, Kubernetes hoặc NAT là **ứng dụng kết nối được tới Sentinel nhưng không kết nối được địa chỉ primary mà Sentinel trả về**.

~~~text
Ứng dụng ngoài Docker network
       |
       +-- Kết nối sentinel.company:26379 thành công
       |
       +-- Sentinel trả Redis primary = 172.18.0.5:6379
       |
       +-- 172.18.0.5 chỉ tồn tại trong Docker network
       |
       +-- Ứng dụng không kết nối được Redis primary
~~~

Phải bảo đảm các địa chỉ mà Redis/Sentinel quảng bá là địa chỉ reachable từ peer và client. Các thiết lập như `sentinel announce-ip`, `sentinel announce-port` hoặc replica announce có thể liên quan tùy topology.

Chỉ mở cổng Sentinel `26379` qua firewall là chưa đủ nếu client không thể kết nối tới Redis data node sau discovery. Khi vận hành trong Kubernetes, cần thiết kế DNS/Service/StatefulSet và cấu hình announce theo đúng phạm vi network của ứng dụng.

Hãy kiểm tra từ **chính nơi ứng dụng chạy**, không chỉ từ một terminal bên trong Redis container.

## 13. Quan sát primary mới và replication

Một số lệnh kiểm tra (thực hiện trong môi trường được phép):

~~~bash
# Hỏi Sentinel đang nhận diện primary nào.
redis-cli -h sentinel-1.internal -p 26379 SENTINEL get-master-addr-by-name mymaster

# Quan sát metadata của nhóm.
redis-cli -h sentinel-1.internal -p 26379 SENTINEL master mymaster
redis-cli -h sentinel-1.internal -p 26379 SENTINEL replicas mymaster

# Kiểm tra role thực tế trên Redis data nodes.
redis-cli -h redis-a.internal -p 6379 ROLE
redis-cli -h redis-b.internal -p 6379 ROLE
redis-cli -h redis-b.internal -p 6379 INFO replication
~~~

`ROLE` và `INFO replication` cho biết role hiện tại và thông tin đồng bộ. Output có thể còn dùng thuật ngữ legacy `master/slave` tùy Redis version, dù bài học dùng primary/replica.

Không chỉ xác nhận Sentinel trả host mới mà kết luận ứng dụng đã phục hồi. Cần kiểm tra:

- Client có thực hiện được một lệnh ghi/đọc thử an toàn sau chuyển đổi không?
- Có lỗi `READONLY` hoặc reconnect lặp đi lặp lại không?
- Replica đang theo kịp primary mới ở mức chấp nhận được không?
- p95/p99 latency và error rate của API đã phục hồi chưa?
- Cache miss có khiến database hoặc upstream quá tải không?

Một số metric và log nên theo dõi:

| Nguồn | Tín hiệu | Mục đích |
| --- | --- | --- |
| Sentinel | `+sdown`, `+odown`, `+switch-master` | Quan sát phát hiện lỗi và thời điểm đổi primary |
| Redis | `INFO replication`, replication lag/offset | Theo dõi quá trình đồng bộ replica |
| Client | reconnect, command timeout, connection error | Đo tác động tới ứng dụng |
| API | error rate, p95/p99 latency | Đo mức ảnh hưởng nghiệp vụ |
| Cache | hit/miss, fallback QPS | Phát hiện cache avalanche khi Redis gián đoạn |
| Hạ tầng | Tình trạng Sentinel nodes và network | Đánh giá khả năng đạt quorum/majority |

Sentinel có phát Pub/Sub notification về chuyển đổi primary, nhưng notification không phải event log bền vững để replay. Nếu hệ thống giám sát mất kết nối, nó có thể bỏ lỡ thông báo; cần kết hợp kiểm tra trạng thái hiện tại.

## 14. Kiểm thử failover trong môi trường riêng

Để kiểm thử thật sự về Redis Sentinel, cần một topology có primary, replica đủ điều kiện và nhiều Sentinel độc lập. Một Redis container duy nhất không chứng minh được khả năng bầu primary mới.

Mô hình test:

~~~text
Redis A: 10.0.0.11:6379    PRIMARY ban đầu
Redis B: 10.0.0.12:6379    REPLICA
Redis C: 10.0.0.13:6379    REPLICA

Sentinel S1: 10.0.0.21:26379
Sentinel S2: 10.0.0.22:26379
Sentinel S3: 10.0.0.23:26379

master name = mymaster
quorum      = 2
~~~

Đây là sơ đồ minh họa, không phải file cấu hình triển khai sẵn. Nếu dùng Docker Compose, Testcontainers hoặc Kubernetes, phải thiết lập replication, Sentinel monitor và địa chỉ announce theo network của môi trường test.

### Quy trình thử có kiểm soát

1. Khởi động topology test và xác nhận Sentinel trả địa chỉ Redis A.
2. Khởi động ứng dụng Spring Boot với cấu hình Sentinel; thực hiện `SET`/`GET` trên key test riêng.
3. Chờ replica nhận dữ liệu và ghi nhận trạng thái replication trước sự cố.
4. Dừng primary A hoặc sử dụng thủ tục `SENTINEL FAILOVER mymaster` **chỉ trong môi trường thử nghiệm được phép**.
5. Quan sát Sentinel xác định primary mới B hoặc C; kiểm tra `ROLE` trực tiếp.
6. Tiếp tục gửi yêu cầu qua **cùng ứng dụng đang chạy**, quan sát các lỗi chuyển tiếp, rồi chờ connection factory tự phục hồi.
7. Xác minh những lệnh mới sau failover đọc/ghi thành công mà không phải đổi `spring.data.redis.host` thủ công.
8. Khởi động lại Redis A, xác minh nó không tự chiếm lại vai trò primary cũ mà được cấu hình đúng theo topology mới.
9. Đối soát các thao tác xảy ra ngay sát sự cố, nhất là những lệnh không lũy đẳng và có kết quả timeout.

Không thực hiện failover thử trên production chỉ để kiểm tra ví dụ. Cần môi trường riêng, dữ liệu giả lập và phương án khôi phục.

### Tránh kiểm thử bằng thời gian chờ cứng

Một bài kiểm thử JUnit/Testcontainers nên dùng **polling với timeout hữu hạn** để chờ Sentinel trả primary mới, Redis mới chuyển role và ứng dụng thực hiện thành công lệnh thử. Không nên chỉ `Thread.sleep(5000)` rồi giả định failover chắc chắn hoàn tất sau 5 giây.

Các mốc discovery, election và reconnect là bất đồng bộ. Một test cố định một số giây dễ flaky khi máy CI chậm hoặc network thay đổi. Cũng không thể dùng một integration test đơn giản để khẳng định không mất bất kỳ ghi nào dưới mọi tình huống phân vùng.

## 15. Lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| App vẫn kết nối primary cũ | Dùng host cố định hoặc lookup một lần | Cấu hình Sentinel-aware `LettuceConnectionFactory` |
| Kết nối được Sentinel nhưng không được Redis data node | Sentinel trả IP nội bộ/NAT không truy cập được | Sửa announce, DNS hoặc routing |
| Không thể tự bầu primary | Không đủ Sentinel đạt quorum/majority | Phân bố và giám sát Sentinel độc lập |
| Lệnh ghi trả `READONLY` | App đang nối tới replica hoặc connection cũ | Kiểm tra role và chính sách reconnect |
| Ghi được ACK rồi mất sau failover | Replication bất đồng bộ, replica chưa kịp nhận | Xem durability và chiến lược bảo toàn nghiệp vụ |
| Đọc thấy dữ liệu cũ | Đọc replica có replication lag | Đọc primary nếu cần read-your-writes |
| Retry làm counter tăng hai lần | `INCR` đã chạy nhưng client không nhận response | Dùng idempotency/đối soát, không retry mù |
| Redis A quay lại nhưng không cho ghi | A hiện là replica của primary mới | Discovery lại primary, không ép ghi vào A |
| Cache miss tăng đột biến | Redis failover gây gián đoạn, nhiều request fallback | Single-flight, rate limit, backoff/circuit breaker |
| Kết nối hay timeout sau khi failover | Client chưa cập nhật topology hoặc mạng không ổn định | Quan sát driver reconnect và địa chỉ Sentinel công bố |
| Thử ứng dụng Redis Cluster bằng Sentinel config | Nhầm topology | Dùng Redis Cluster configuration đúng |
| Pipeline/transaction chưa có kết quả chắc chắn | Connection lỗi giữa chừng | Đối soát trạng thái thực tế, không mặc định rollback |

## 16. Tổng kết

**Redis Sentinel cho phép khám phá primary theo vai trò và điều phối việc đổi primary khi replica được thăng cấp.** Trong Spring Data Redis, cấu hình Sentinel bằng master name, nhiều Sentinel nodes và Lettuce giúp ứng dụng không cần chỉnh địa chỉ Redis thủ công sau mỗi lần chuyển đổi.

Tuy vậy, cơ chế này không biến failover thành một thao tác tức thì hoặc không bao giờ mất dữ liệu. Replication mặc định bất đồng bộ, client có thể gặp timeout giữa lúc đổi role và những lệnh chưa có phản hồi không phải lúc nào cũng an toàn để retry. Đọc replica còn chịu rủi ro dữ liệu cũ.

Một hệ thống dùng Sentinel tốt cần đồng thời: **discovery đúng**, **địa chỉ reachable**, **quorum/majority phù hợp**, **client reconnect**, **retry có idempotency**, **phân biệt replica reads với primary reads**, và **kiểm thử failover ở môi trường kiểm soát**. Khi các ranh giới này rõ ràng, Spring Data Redis có thể tiếp tục làm việc với primary mới mà không biến mọi lần failover thành một lần sửa cấu hình ứng dụng.
