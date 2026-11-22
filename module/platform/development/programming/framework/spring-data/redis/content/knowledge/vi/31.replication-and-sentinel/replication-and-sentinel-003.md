# Cấu hình kết nối Redis Sentinel trong Spring Data Redis

## 1. Mục tiêu: ứng dụng tìm đúng Redis master sau failover

Một ứng dụng Spring Boot thường kết nối Redis bằng một cặp host và port cố định:

```yaml
spring:
  data:
    redis:
      host: redis-primary.internal
      port: 6379
```

Cách này dễ hiểu nhưng có hạn chế: nếu Redis master gặp sự cố và một replica được **promote thành master**, địa chỉ ghi hợp lệ đã thay đổi. Ứng dụng tiếp tục gửi lệnh đến địa chỉ cũ có thể gặp lỗi kết nối hoặc `READONLY`.

**Redis Sentinel** là cơ chế giám sát và phối hợp failover cho mô hình Redis primary–replica. Khi dùng Sentinel, ứng dụng không hard-code một địa chỉ master duy nhất. Nó biết **tên nhóm master** và một số địa chỉ Sentinel, hỏi Sentinel để khám phá master hiện tại, rồi kết nối tới Redis data node tương ứng.

```text
                         Spring Boot
                             |
                             | 1. Hỏi Sentinel:
                             |    master "mymaster" ở đâu?
                             v
                +---------------------------+
                | Sentinel A / B / C        |
                | ports thường là 26379     |
                +-------------+-------------+
                              |
                              | 2. Trả địa chỉ Redis master
                              v
                      +---------------+
                      | Redis Master  |
                      | 10.10.0.11    |
                      | port 6379     |
                      +-------+-------+
                              |
                 replication bất đồng bộ
                         /           \
                        v             v
               +-------------+ +-------------+
               | Replica 1   | | Replica 2   |
               +-------------+ +-------------+
```

Khi master đổi, Redis client được cấu hình Sentinel có thể khám phá master mới và khôi phục kết nối theo cơ chế của driver.

**Điều cần nhớ:** Sentinel giúp *khám phá và chuyển đổi master*, không biến Redis thành một cơ sở dữ liệu giao dịch phân tán không mất dữ liệu, không bảo đảm zero downtime và không tự retry mọi thao tác nghiệp vụ an toàn.

Bài này tập trung vào cách **cấu hình kết nối Redis Sentinel với Spring Data Redis**, kèm các điều kiện hạ tầng cần có, ví dụ Spring Boot, cấu hình Java thuần, authentication, kiểm thử failover và xử lý lỗi vận hành.

## 2. Ba thành phần khác nhau: master, replica, Sentinel

| Thành phần | Chức năng | Port minh họa |
| --- | --- | --- |
| Redis master | Nhận các lệnh ghi và là nguồn replication | `6379` |
| Redis replica | Sao chép dữ liệu từ master, có thể được promote | `6379` |
| Redis Sentinel | Giám sát trạng thái, phối hợp bầu chọn/failover, cung cấp địa chỉ master hiện tại | `26379` |

Sentinel **không phải Redis proxy cho mọi lệnh GET/SET**. Với cấu hình Sentinel tiêu chuẩn, quy trình kết nối là:

1. Spring Data Redis/Lettuce kết nối tới một Sentinel đã biết.
2. Driver hỏi Sentinel master có tên `mymaster` hiện là node nào.
3. Driver tạo kết nối dữ liệu trực tiếp tới Redis node được trả về.
4. Khi failover, client phải phát hiện thay đổi và kết nối tới node phù hợp.

Sơ đồ hai loại kết nối:

```text
Spring application
    |
    +-- Discovery/control --> Sentinel :26379
    |
    +-- Data operations ---> Redis master :6379
```

Hệ quả thực tế:

- Firewall phải cho phép **cả kết nối tới Sentinel và kết nối tới các Redis data nodes có thể trở thành master**.
- DNS/IP mà Sentinel trả về phải **truy cập được từ chính môi trường chạy Spring Boot**.
- Chỉ mở port `26379` chưa đủ; application phải tới được port Redis data node.
- Nếu cấu hình ứng dụng vẫn chỉ dùng `host/port` cố định, việc deploy Sentinel ở hạ tầng **không tự làm ứng dụng biết master mới**.

## 3. Sentinel thực hiện giám sát và failover như thế nào?

Redis Sentinel theo dõi master, replica và các Sentinel khác. Nó dùng quá trình đánh giá tình trạng master, đồng thuận cần thiết và bầu chọn leader để thực hiện failover.

Các khái niệm:

- **Subjectively Down (SDOWN):** một Sentinel tự đánh giá node không phản hồi theo ngưỡng được cấu hình.
- **Objectively Down (ODOWN):** đủ Sentinel đồng ý master không còn khả dụng theo cấu hình quorum.
- **Quorum:** số Sentinel tối thiểu cần xác nhận master bị lỗi để đạt trạng thái ODOWN.
- **Authorization/leader election:** ngoài quorum, failover cần sự chấp thuận/đa số thích hợp trong tập Sentinel đã biết để một leader thực hiện chuyển đổi.
- **Promotion:** chọn một replica phù hợp thành master mới; những replica còn lại được cấu hình theo master mới.

Ví dụ ba Sentinel và quorum hai:

```text
Sentinel A ----\
Sentinel B -----+---- monitor mymaster, quorum = 2
Sentinel C ----/
```

Quorum `2` **không có nghĩa chỉ cần hai Sentinel trong mọi tình huống là mọi failover chắc chắn xảy ra**; cần xét số Sentinel đang hoạt động, majority authorization và connectivity.

Một triển khai thường có **ít nhất ba Sentinel trên các failure domain độc lập**, đi cùng một master và các replica. Chạy ba process Sentinel trên cùng một máy vật lý không mang lại tính sẵn sàng tương đương ba host độc lập.

### Sentinel và Redis Cluster không giống nhau

| Tiêu chí | Sentinel | Redis Cluster |
| --- | --- | --- |
| Mục tiêu chính | HA cho một nhóm master–replicas | Phân chia dữ liệu theo hash slots và HA cho các shard |
| Phân phối dữ liệu | Không sharding tự động | Có sharding |
| Client config | Master name + Sentinel addresses | Cluster seed nodes |
| Ghi thông thường | Vào master được chọn | Vào node sở hữu key slot |
| Khả năng mở rộng dung lượng bằng sharding | Không tự có | Có |
| Spring connection configuration | `RedisSentinelConfiguration` | `RedisClusterConfiguration` |

Một hệ thống Redis lớn có thể có nhiều nhóm Sentinel độc lập, nhưng không được xem như một Redis Cluster thống nhất chỉ vì có nhiều master.

## 4. Chuẩn bị topology trước khi cấu hình Spring Boot

Ví dụ môi trường minh họa:

| Vai trò | Host | Port |
| --- | --- | --- |
| Redis master ban đầu | `10.10.0.11` | `6379` |
| Redis replica 1 | `10.10.0.12` | `6379` |
| Redis replica 2 | `10.10.0.13` | `6379` |
| Sentinel A | `10.10.0.21` | `26379` |
| Sentinel B | `10.10.0.22` | `26379` |
| Sentinel C | `10.10.0.23` | `26379` |

Các địa chỉ trên **chỉ để minh họa**; thay bằng địa chỉ do hạ tầng cung cấp. Tên nhóm Redis master được Sentinel theo dõi:

```text
mymaster
```

`mymaster` là **tên logic do quản trị Redis Sentinel cấu hình**, không phải hostname. Tên mà client dùng phải khớp chính xác với tên mà Sentinel biết.

Trước khi viết Java cần xác nhận:

1. Redis master và replicas đã cấu hình replication đúng.
2. Tập Sentinel giám sát cùng một tên `mymaster`.
3. Client Spring có đường mạng đến các Sentinel.
4. Client Spring có đường mạng đến Redis master hiện tại **và các replica có thể được promote**.
5. Tài khoản/credential để đăng nhập Redis data nodes khác gì tài khoản truy cập Sentinel.
6. DNS/IP được Sentinel công bố có thể được Spring client resolve và connect.
7. Redis server, Spring Data Redis và Lettuce/Jedis dùng phiên bản tương thích với các tùy chọn xác thực/TLS dự kiến.

Chỉ khi các điều kiện này rõ ràng, file `application.yml` mới có ý nghĩa.

## 5. Minh họa cấu hình Redis master, replica và Sentinel

Đây là cấu hình hạ tầng **để hiểu cơ chế**, không phải bộ cấu hình production hoàn chỉnh. Production cần thêm ACL, bind/listen addresses, firewall, persistence, giám sát và quản lý secret.

Một Redis master có thể dùng file cấu hình thông thường, chẳng hạn:

```conf
port 6379
appendonly yes
```

Một replica phải theo dõi master ban đầu:

```conf
port 6379
replicaof 10.10.0.11 6379
appendonly yes
```

Khi dùng authentication giữa Redis master và replica, replica cần cơ chế xác thực tới master phù hợp, ví dụ `masterauth` ở mô hình password truyền thống hoặc ACL user được cấp quyền.

Trên **mỗi Sentinel**, file cấu hình có thể có:

```conf
port 26379

sentinel monitor mymaster 10.10.0.11 6379 2
sentinel down-after-milliseconds mymaster 10000
sentinel failover-timeout mymaster 60000
sentinel parallel-syncs mymaster 1
```

Dòng monitor có cấu trúc:

```text
sentinel monitor <master-name> <master-ip> <master-port> <quorum>
```

Ở đây:

- `mymaster` là tên client phải dùng.
- `10.10.0.11:6379` là địa chỉ master ban đầu mà Sentinel theo dõi.
- `2` là quorum phục vụ đánh giá ODOWN.
- `down-after-milliseconds` là ngưỡng đánh giá mất phản hồi.
- `failover-timeout` ảnh hưởng một số mốc và nhịp failover/retry của Sentinel.
- `parallel-syncs` giới hạn số replicas đồng thời đồng bộ theo master mới trong giai đoạn failover.

**Lưu ý:** Sentinel chủ động cập nhật và ghi lại cấu hình trạng thái khi topology thay đổi. Không nên phân phối file cấu hình rồi ép ghi đè định kỳ mà không hiểu cách Sentinel lưu master mới. File cấu hình Sentinel phải nằm trên vị trí mà process có quyền ghi khi cần.

### Authentication của Sentinel tới master khác authentication của app tới Sentinel

Nếu Redis data nodes yêu cầu password, Sentinel cần credential để giám sát và thao tác failover. Ví dụ cấu hình truyền thống:

```conf
sentinel auth-pass mymaster REDIS_DATA_NODE_PASSWORD
```

Nếu dùng Redis ACL, Sentinel có thể cần `sentinel auth-user` và `sentinel auth-pass` tương ứng với quyền phù hợp trên data nodes.

Những credential đó là để **Sentinel đăng nhập Redis master/replicas**. Chúng không tự cấp quyền cho ứng dụng Spring Boot kết nối tới **cổng Sentinel 26379**. Nếu chính Sentinel cũng yêu cầu client authentication, Spring cần cấu hình credential riêng ở phía Sentinel.

## 6. Cấu hình Spring Boot bằng application.yml

Với nhiều phiên bản Spring Boot hiện đại sử dụng namespace `spring.data.redis`, cách cấu hình cơ bản là:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
          - sentinel-c.internal:26379
      connect-timeout: 3s
      timeout: 3s
```

Các mục chính:

| Thuộc tính | Vai trò |
| --- | --- |
| `spring.data.redis.sentinel.master` | Tên master logic Sentinel theo dõi |
| `spring.data.redis.sentinel.nodes` | Các địa chỉ Sentinel để client discovery |
| `spring.data.redis.client-type` | Chọn Lettuce/Jedis theo dependency và Boot version |
| `spring.data.redis.connect-timeout` | Giới hạn thời gian thiết lập kết nối phù hợp với client/config |
| `spring.data.redis.timeout` | Giới hạn thời gian chờ Redis operation phù hợp với client/config |

Với Spring Boot auto-configuration được bật và dependency phù hợp, ứng dụng có thể nhận `RedisConnectionFactory`, `StringRedisTemplate` và `RedisTemplate` để thực hiện lệnh Redis.

Ví dụ sử dụng:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionFlagService {

    private final StringRedisTemplate redis;

    public SessionFlagService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void markActive(String id) {
        redis.opsForValue().set("session:active:" + id, "1");
    }

    public boolean isActive(String id) {
        return "1".equals(
            redis.opsForValue().get("session:active:" + id)
        );
    }
}
```

Service này **không cần** tự gọi `SENTINEL get-master-addr-by-name`. Khi Spring Data Redis được cấu hình Sentinel, driver chịu trách nhiệm khám phá master và quản lý connection phù hợp.

### Phiên bản Spring Boot và prefix

Trong các ứng dụng Spring Boot cũ, bạn có thể gặp namespace `spring.redis.*` thay vì `spring.data.redis.*`. Cần dùng **đúng prefix của phiên bản Boot đang chạy**, không trộn hai cách đặt property và kỳ vọng chúng đều có hiệu lực.

Ngoài ra, không nên đồng thời đưa các cấu hình standalone host/port, Redis URL và Sentinel với giả định không có thứ tự ưu tiên. Ưu tiên cấu hình thuộc một mô hình kết nối rõ ràng, kiểm tra giá trị thực mà Spring Boot bind vào connection factory.

## 7. Dùng environment variables thay vì ghi password trong Git

Trong ứng dụng thật, không nên hard-code Redis password và Sentinel password trong YAML commit lên repository.

Ví dụ:

```yaml
spring:
  data:
    redis:
      username: ${REDIS_DATA_USERNAME:default}
      password: ${REDIS_DATA_PASSWORD}
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
          - sentinel-c.internal:26379
        username: ${REDIS_SENTINEL_USERNAME:default}
        password: ${REDIS_SENTINEL_PASSWORD}
```

Bốn thông tin cần phân biệt:

- **Redis data username**: user mà application dùng đăng nhập Redis master/replica.
- **Redis data password**: password tương ứng với data user.
- **Sentinel username**: user mà application dùng đăng nhập Sentinel, nếu Sentinel yêu cầu.
- **Sentinel password**: password cho kết nối application → Sentinel.

Tùy Spring Boot/Spring Data Redis version, các thuộc tính Sentinel username/password có thể cần xác nhận trong configuration metadata; một số phiên bản cũ có hỗ trợ khác nhau. Nếu framework không expose property cần thiết, có thể cấu hình `RedisSentinelConfiguration` bằng Java.

Trong ví dụ dùng `${REDIS_DATA_USERNAME:default}`, `default` là giá trị mặc định của placeholder trong Spring; còn `${REDIS_DATA_PASSWORD}` yêu cầu environment/properties thực tế cung cấp giá trị.

**Lưu ý bảo mật:** không đặt password thật trong tài liệu, log, command history hoặc URL lệnh được lưu công khai. Dùng secret manager, Kubernetes Secret hoặc hệ thống quản lý cấu hình của tổ chức theo chính sách vận hành.

## 8. Cấu hình Java thuần bằng RedisSentinelConfiguration

Khi cần điều chỉnh chi tiết mà auto-configuration không đủ, Spring Data Redis cung cấp `RedisSentinelConfiguration`.

Ví dụ khai báo `LettuceConnectionFactory`:

```java
package com.example.redis;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisSentinelConnectionConfig {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {

        RedisSentinelConfiguration sentinel =
            new RedisSentinelConfiguration()
                .master("mymaster")
                .sentinel("sentinel-a.internal", 26379)
                .sentinel("sentinel-b.internal", 26379)
                .sentinel("sentinel-c.internal", 26379);

        // Nếu Redis data nodes dùng ACL:
        sentinel.setUsername("app-redis-user");
        sentinel.setPassword(
            RedisPassword.of("DATA_NODE_PASSWORD_FROM_SECRET")
        );

        // Nếu cổng Sentinel cũng bật ACL:
        sentinel.setSentinelUsername("app-sentinel-user");
        sentinel.setSentinelPassword(
            RedisPassword.of("SENTINEL_PASSWORD_FROM_SECRET")
        );

        LettuceClientConfiguration client =
            LettuceClientConfiguration.builder()
                .commandTimeout(Duration.ofSeconds(3))
                .shutdownTimeout(Duration.ofMillis(100))
                .build();

        return new LettuceConnectionFactory(sentinel, client);
    }
}
```

**Chú ý:** các chuỗi password ở trên chỉ là placeholder để minh họa API; trong triển khai thật phải lấy credential qua cấu hình/secret injection thay vì commit chúng vào mã nguồn.

Nếu hệ thống không yêu cầu authentication ở một phía, bỏ những dòng credential tương ứng; không giả định tất cả môi trường đều có hai bộ user/password.

Ví dụ trên chọn **Lettuce** vì đây là Redis client được Spring Boot dùng phổ biến. Với các phiên bản cụ thể, cần kiểm tra API/constructor và khả năng hỗ trợ Sentinel ACL/TLS của Spring Data Redis và Lettuce tương ứng.

### Vì sao không gọi `new RedisStandaloneConfiguration()`?

`RedisStandaloneConfiguration` phù hợp khi biết một địa chỉ Redis cố định. Với Sentinel, `RedisSentinelConfiguration` mang master name và danh sách các Sentinel discovery endpoints.

Dùng factory standalone rồi tự đổi host thủ công sau failover sẽ làm mất lợi ích chính của driver hỗ trợ Sentinel và tạo một cơ chế cập nhật topology không cần thiết.

## 9. Tách cấu hình khỏi source code với @ConfigurationProperties hoặc @Value

Đoạn Java ở trên giúp thấy các API, nhưng production nên đưa địa chỉ và credentials ra cấu hình.

Một ví dụ tối giản dùng `@Value`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class SentinelWiringConfig {

    @Bean
    LettuceConnectionFactory redisConnectionFactory(
            @Value("${app.redis.master}") String master,
            @Value("${app.redis.sentinel-a}") String sentinelA,
            @Value("${app.redis.sentinel-b}") String sentinelB,
            @Value("${app.redis.password}") String password) {

        RedisSentinelConfiguration config =
            new RedisSentinelConfiguration()
                .master(master)
                .sentinel(sentinelA, 26379)
                .sentinel(sentinelB, 26379);

        config.setPassword(RedisPassword.of(password));
        return new LettuceConnectionFactory(config);
    }
}
```

Cấu hình ứng dụng:

```yaml
app:
  redis:
    master: mymaster
    sentinel-a: sentinel-a.internal
    sentinel-b: sentinel-b.internal
    password: ${REDIS_DATA_PASSWORD}
```

Ví dụ này không đặt Sentinel client authentication, vì giả định Sentinel đang cho phép ứng dụng discovery trong mạng thử nghiệm. Khi Sentinel yêu cầu ACL, phải thêm credentials tương ứng.

Trong hệ thống có nhiều Sentinel nodes, nên dùng cấu hình dạng danh sách và lặp tạo endpoints thay vì đặt tên `sentinel-a`, `sentinel-b` cố định như ví dụ tối giản.

**Không nên đồng thời định nghĩa custom `RedisConnectionFactory` và kỳ vọng Spring Boot vẫn tự áp dụng toàn bộ `spring.data.redis.*` properties lên bean đó.** Khi tự tạo factory, ứng dụng chịu trách nhiệm cấu hình các thuộc tính cần thiết cho factory.

## 10. Đăng ký StringRedisTemplate khi tự tạo connection factory

Nếu ứng dụng tự khai báo `RedisConnectionFactory`, Spring Boot có thể tạo template theo auto-configuration nếu điều kiện phù hợp. Để rõ ràng, cũng có thể khai báo:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisTemplateConfig {

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        return new StringRedisTemplate(connectionFactory);
    }
}
```

`StringRedisTemplate` dùng serializer phù hợp cho key/value dạng chuỗi. Redis Sentinel chỉ ảnh hưởng cách connection factory tìm Redis node; nó **không thay đổi** cách Java serialize payload, cách xử lý TTL hoặc các thao tác ở tầng template.

Ví dụ sử dụng:

```java
String key = "demo:sentinel:ping";
redis.opsForValue().set(key, "ok");

String value = redis.opsForValue().get(key);
```

Khi master hoạt động và client đã khám phá đúng địa chỉ, giá trị đọc dự kiến là `"ok"`.

Nếu muốn lưu object JSON, hãy cấu hình `RedisTemplate` serializer riêng. Không để việc kết nối qua Sentinel che khuất vấn đề tương thích serializer.

## 11. Lettuce và Jedis: khác nhau ở cách tích hợp, không ở hợp đồng Sentinel

Spring Data Redis có thể kết nối qua Lettuce hoặc Jedis tùy dependency và cấu hình.

| Chủ đề | Lettuce | Jedis |
| --- | --- | --- |
| Kiểu client | Client hỗ trợ mô hình connection và I/O hiện đại của Lettuce | Client Redis với cấu hình pool/connection tương ứng |
| Tích hợp Spring Data Redis | `LettuceConnectionFactory` | `JedisConnectionFactory` |
| Sentinel | Hỗ trợ qua Sentinel configuration phù hợp | Hỗ trợ qua Sentinel configuration phù hợp |
| Timeout, pool, SSL, reconnect | Dùng cấu hình Lettuce | Dùng cấu hình Jedis |
| Lựa chọn | Theo dependency/khả năng của app | Theo dependency/khả năng của app |

Đoạn code khởi tạo Jedis (minh họa, khi đã có dependency Jedis và phiên bản Spring Data Redis hỗ trợ):

```java
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.jedis.JedisConnectionFactory;

RedisSentinelConfiguration sentinel =
    new RedisSentinelConfiguration()
        .master("mymaster")
        .sentinel("sentinel-a.internal", 26379)
        .sentinel("sentinel-b.internal", 26379);

JedisConnectionFactory factory =
    new JedisConnectionFactory(sentinel);
```

Khi dùng Spring Boot, đừng chọn `client-type: jedis` nếu dependency Jedis cần thiết chưa có. Không lẫn cấu hình timeout/pool của Lettuce với Jedis; từng driver có API và behavior riêng.

Trong bài, các ví dụ chính dùng Lettuce nhằm giữ một đường cấu hình dễ theo dõi.

## 12. Tên master logic không phải hostname

Một lỗi cấu hình rất thường gặp:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: sentinel-a.internal
```

Trường `master` **không phải hostname của Sentinel**. Nó phải là **tên nhóm Redis master** trong:

```conf
sentinel monitor mymaster 10.10.0.11 6379 2
```

Do đó giá trị đúng phải là:

```yaml
sentinel:
  master: mymaster
```

Danh sách `nodes` là nơi đặt host/port Sentinel để client tìm master.

Một Sentinel có thể theo dõi nhiều master groups với các tên khác nhau. Chọn sai master name khiến lệnh tìm master không có kết quả, dù port Sentinel vẫn reachable.

## 13. Kiểm tra topology qua redis-cli

Trước khi phân tích lỗi Spring Boot, dùng Redis CLI kiểm tra Sentinel:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL get-master-addr-by-name mymaster
```

Ví dụ kết quả:

```text
1) "10.10.0.11"
2) "6379"
```

Đây là Redis **data master** mà Sentinel đang báo, không phải Sentinel endpoint.

Các lệnh thường dùng:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL masters

redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL master mymaster

redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL replicas mymaster

redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL sentinels mymaster
```

Trên Redis data node:

```bash
redis-cli -h 10.10.0.11 -p 6379 INFO replication
redis-cli -h 10.10.0.11 -p 6379 ROLE
```

Trong ví dụ:

- Sentinel báo `10.10.0.11:6379` đang là master.
- `INFO replication`/`ROLE` trên data node cho biết vai trò mà node tự thấy.
- Thông tin của các Sentinel khác nhau có thể tạm thời lệch nhau trong giai đoạn lỗi/failover, nên kiểm tra nhiều node khi chẩn đoán.

Các dòng trên trình bày cú pháp command dễ đọc; trên PowerShell Windows có thể nhập toàn bộ lệnh một dòng, không dùng `\` như ký tự nối dòng.

### Nếu có password

Dùng cách nhập secret an toàn mà hạ tầng hỗ trợ; tránh để password xuất hiện trực tiếp trong shell history hoặc danh sách process. Password Sentinel và password Redis data node có thể **khác nhau**, vì vậy dùng đúng credential khi kiểm tra từng port.

## 14. Kiểm tra network theo địa chỉ Sentinel công bố

Một tình huống điển hình:

1. Ứng dụng kết nối được Sentinel `sentinel-a.internal:26379`.
2. Sentinel trả `10.10.0.11:6379` là master.
3. Container Spring Boot không thể truy cập `10.10.0.11:6379`.
4. Application báo lỗi connection timeout, dù Sentinel vẫn khỏe.

Sơ đồ:

```text
Spring container ---- OK ----> Sentinel :26379
Spring container ---- FAIL --> Redis master :6379
```

Khi debug, cần kiểm tra **cả hai đường**. Không chỉ kiểm tra ping Sentinel.

Các câu hỏi:

- Địa chỉ master trả về có thể được resolve/routing từ network của Spring app không?
- Port Redis data node có mở cho ứng dụng không?
- Sau failover, địa chỉ replica được promote có cũng reachable không?
- Sentinel và replicas có quảng bá địa chỉ LAN/internal đúng thay vì `127.0.0.1` không?
- Có NAT, overlay network, Docker port mapping hoặc service mesh làm thay đổi địa chỉ được client nhìn thấy không?
- Có IPv4/IPv6 khác nhau khiến client nhận địa chỉ không truy cập được không?

**Sentinel khám phá địa chỉ, không proxy traffic**; vì vậy advertised address là một phần quan trọng của thiết kế.

## 15. Lỗi localhost trong Docker/Kubernetes

Trong Docker, `127.0.0.1` bên trong Spring container là **chính Spring container**, không phải Redis container. Vì vậy:

```yaml
spring:
  data:
    redis:
      sentinel:
        nodes:
          - 127.0.0.1:26379
```

chỉ đúng nếu Sentinel thực sự chạy trong cùng network namespace với Spring process.

Ví dụ thay bằng DNS service nội bộ:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-0.redis.svc.cluster.local:26379
          - sentinel-1.redis.svc.cluster.local:26379
          - sentinel-2.redis.svc.cluster.local:26379
```

Tên trên chỉ là mẫu; Kubernetes/Docker topology thật có thể dùng tên khác.

**Quan trọng hơn:** dù `sentinel-0.redis.svc.cluster.local` reachable, Sentinel có thể trả địa chỉ Redis master thuộc mạng private khác, không accessible từ application. Cần bảo đảm Sentinel **advertise địa chỉ data nodes thực sự truy cập được**.

Ở môi trường có NAT/port mapping, có thể cần cấu hình announce phù hợp, quản lý địa chỉ replica/Sentinel hoặc chọn Redis service/operator hỗ trợ kết nối Sentinel xuyên network boundaries. Đừng giả định mapping `6379:6379` trên host tự sửa mọi địa chỉ Redis công bố.

## 16. Authentication: hai đường kết nối khác nhau

Một deployment có thể có ít nhất ba loại credential:

```text
Spring App -----------> Sentinel :26379
   dùng Sentinel ACL/password

Spring App -----------> Redis master :6379
   dùng Redis data ACL/password

Sentinel -------------> Redis master/replicas :6379
   dùng credential giám sát/failover
```

**Không nhầm**:

- `spring.data.redis.password`: credential application dùng cho Redis data nodes.
- `spring.data.redis.sentinel.password`: credential application dùng để authenticate tới Sentinel, nếu phiên bản hỗ trợ property này.
- `sentinel auth-pass mymaster ...`: credential Sentinel process dùng kết nối Redis nodes; không phải password Spring ứng dụng dùng để truy cập Sentinel port.
- User ACL của Redis data node và user ACL của Sentinel có thể khác nhau.

### Ví dụ cấu hình phân biệt credential

```yaml
spring:
  data:
    redis:
      username: ${REDIS_DATA_USER:default}
      password: ${REDIS_DATA_PASSWORD}
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
          - sentinel-c.internal:26379
        username: ${REDIS_SENTINEL_USER:default}
        password: ${REDIS_SENTINEL_PASSWORD}
```

Đây là ví dụ cho phiên bản Spring Boot hỗ trợ các thuộc tính tương ứng. Cần đối chiếu configuration metadata/driver đang dùng khi triển khai thực tế, đặc biệt với ứng dụng Spring Boot cũ.

Nếu chỉ có data password mà Sentinel không yêu cầu client authentication, **không cần** gán Sentinel password bằng cùng password.

## 17. TLS/SSL và Sentinel

Ở môi trường yêu cầu mã hóa kết nối, cần xác định TLS cho **cả đường data** và **đường Sentinel discovery**, chứ không chỉ một cổng.

```text
Spring -- TLS? --> Sentinel :26379
Spring -- TLS? --> Redis master :6379
Sentinel -- TLS? --> Redis data nodes
```

Trong các Spring Boot version hỗ trợ cấu hình SSL cho Redis, có thể gặp property như:

```yaml
spring:
  data:
    redis:
      ssl:
        enabled: true
```

Nhưng **không nên suy ra chỉ bật một property là đã cấu hình TLS đầy đủ cho mọi đường Sentinel/data, CA và hostname verification**. Chi tiết phụ thuộc phiên bản Spring Boot, Spring Data Redis, Lettuce/Jedis và hạ tầng Redis/Sentinel.

Khi cần TLS:

1. Xác nhận Redis data nodes và Sentinel ports có hỗ trợ TLS.
2. Cấp truststore/CA phù hợp cho JVM/client.
3. Xác định hostname trong certificate khớp địa chỉ client sử dụng.
4. Kiểm tra behavior của Sentinel discovery và node failover qua TLS.
5. Kiểm tra kết nối đến **replica sau khi được promote**, không chỉ master ban đầu.
6. Không vô hiệu hóa certificate/hostname verification chỉ để kết nối “chạy được”.

Nếu Redis provider yêu cầu kết hợp Sentinel authentication và TLS đặc thù, ưu tiên hướng dẫn chính thức của provider và client library version cụ thể.

## 18. Pool, timeout và reconnect khi failover

Trong mô hình Sentinel, connection tới master hiện tại có thể bị mất khi failover đang diễn ra. Application cần xử lý các lỗi tạm thời.

Những thông số cần quan tâm:

- **Connect timeout:** thời gian chờ mở kết nối tới Sentinel hoặc Redis data node.
- **Command timeout:** thời gian chờ lệnh Redis.
- **Pool sizing** nếu sử dụng connection pool: giới hạn active/idle và thời gian chờ connection.
- **Reconnect behavior:** hành vi Lettuce/Jedis khi endpoint mất kết nối hoặc đổi role.
- **Read preference:** có đọc replica hay không.
- **Circuit breaker/backoff:** nếu Redis lỗi kéo dài, có tiếp tục dồn tải hay giảm số request.

Ví dụ client configuration ở tầng Java:

```java
LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .commandTimeout(Duration.ofSeconds(3))
        .shutdownTimeout(Duration.ofMillis(100))
        .build();
```

Mức `3s` chỉ để minh họa; cần điều chỉnh theo latency, SLA và load thực. Timeout quá thấp gây false failures; quá cao khiến request HTTP hoặc worker bị treo lâu khi failover.

### Retry không phải lúc nào cũng an toàn

Giả sử client gửi:

```redis
INCR billing:counter
```

Redis đã thực hiện lệnh nhưng response bị mất trong failover. Nếu client tự retry, counter có thể tăng lần thứ hai.

Tương tự, `LPUSH`, `INCRBY`, ghi job hoặc một Lua script có tác dụng phụ không tự an toàn khi retry mù quáng.

Phân biệt:

| Thao tác | Khi response mất có thể retry thế nào? |
| --- | --- |
| `GET` | Thường có thể đọc lại theo consistency policy |
| `SET key value` | Thường idempotent nếu cùng key/value và không có điều kiện thời gian phụ thuộc |
| `INCR` | Không an toàn nếu retry vô điều kiện |
| `LPUSH` | Có thể thêm phần tử trùng |
| `SET key value NX` | Retry cần hiểu key đã được tạo chưa và owner/token là ai |
| Lua reserve/charge | Cần idempotency key và cách kiểm tra kết quả đã áp dụng |

Sentinel giúp kết nối tới master mới; nó **không định nghĩa idempotency cho lệnh Redis**.

## 19. Vì sao failover không đảm bảo zero downtime?

Quy trình failover cần thời gian để Sentinel:

1. Phát hiện master không phản hồi.
2. Đạt quorum/authorization.
3. Chọn replica đủ điều kiện.
4. Promote replica thành master.
5. Cập nhật topology và để client tìm lại master.

Trong giai đoạn này:

- Các connection cũ có thể bị lỗi hoặc timeout.
- Một số request có thể gặp `READONLY` nếu client đang giữ endpoint cũ.
- Client có thể phải reconnect/resubscribe.
- Network split có thể dẫn tới trạng thái khó đồng bộ.
- Các write đã trả ACK trước đó vẫn có thể chưa được replica được chọn nhận đủ do replication bất đồng bộ.

Do đó:

> Sentinel mang lại **high availability và cơ chế tự động chuyển đổi vai trò**, không đồng nghĩa không mất dữ liệu, không lỗi request và không gián đoạn trong mọi trường hợp.

Ứng dụng cần quyết định khi Redis unavailable:

- Fail request hay trả thông báo thử lại?
- Có fallback sang database không?
- Cache read có thể bỏ qua Redis để đọc nguồn chuẩn không?
- Một thao tác quan trọng có cần lưu ở hệ khác trước khi trả kết quả không?
- Lệnh có thể retry an toàn hay phải kiểm tra idempotency state?

## 20. Replication bất đồng bộ và nguy cơ mất write

Redis replication thông dụng là bất đồng bộ. Master có thể chấp nhận một write và phản hồi cho client trước khi replica được chọn trong failover đã nhận write đó.

Ví dụ:

```text
T0: App SET order:42 = "PAID" vào master A
T1: Master A trả OK
T2: Master A mất trước khi replica B nhận write
T3: Sentinel promote replica B
T4: Redis mới không có order:42 = "PAID"
```

Điều này không phải lúc nào cũng xảy ra, nhưng **không bị loại trừ** chỉ vì dùng Sentinel.

Redis có các cơ chế như `WAIT` để chờ một mức xác nhận replication trong tình huống nhất định, song điều đó **không tạo transaction bền vững tuyệt đối** hay loại bỏ mọi rủi ro failover/persistence. Cần đánh giá riêng khi dữ liệu Redis là nguồn chuẩn của nghiệp vụ quan trọng.

Nếu Redis chỉ là cache của PostgreSQL, ứng dụng có thể tái tạo cache khi miss. Nếu Redis giữ trạng thái duy nhất của thanh toán, yêu cầu độ bền cần được thiết kế cẩn trọng hơn nhiều.

## 21. Replica reads: tối ưu đọc nhưng có thể đọc dữ liệu cũ

Với Lettuce và Spring Data Redis, một số cấu hình cho phép đọc từ replica khi dùng cơ chế tương ứng của client.

Ví dụ ý tưởng:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .readFrom(ReadFrom.REPLICA_PREFERRED)
        .build();
```

Cách này chỉ nên dùng khi phiên bản driver và cách cấu hình Sentinel/replica connections hỗ trợ; cần kiểm tra hành vi thực tế của ứng dụng.

Khi đọc replica:

- Dữ liệu có thể **trễ** so với master vì replication bất đồng bộ.
- Lệnh ghi vẫn cần master.
- Một request ghi xong rồi đọc ngay replica có thể thấy giá trị cũ.
- Trong failover, replica topology và read preference có thể thay đổi.

Với nghiệp vụ cần **read-your-writes** hoặc ra quyết định tài chính, không mặc định đọc replica là đủ đúng. Phân biệt đường đọc cache/hiển thị với đường kiểm tra trạng thái có thẩm quyền.

## 22. Sentinel và transaction/Lua/Pipeline

Các API mức cao của Spring Data Redis vẫn có thể sử dụng khi kết nối qua Sentinel:

- `StringRedisTemplate`/`RedisTemplate`.
- `opsForValue`, `opsForHash`, `opsForSet`, `opsForZSet`.
- Lua script qua `RedisScript`.
- Pipelining.
- Pub/Sub listeners.

Tuy nhiên, trong failover, bất kỳ workflow nào cũng có thể gặp mất kết nối.

**Pipeline:** không phải transaction; failover giữa đường có thể làm client không rõ lệnh nào đã thực thi trước khi kết nối đứt.

**Lua:** khi chạy trên một master, script được Redis thực thi theo ngữ nghĩa của Lua scripting, nhưng client timeout vẫn có thể xảy ra sau khi script đã thực hiện. Retry cần idempotency.

**MULTI/EXEC:** transaction gắn với connection và Redis node; mất connection hoặc đổi master có thể làm kết quả không rõ từ góc nhìn client.

**Pub/Sub:** subscription có thể cần khôi phục; message phát khi listener offline không được Redis phát lại.

Sentinel không tăng bảo đảm của từng API lên “exactly once”. Cần phân tích failure scenario riêng cho thao tác quan trọng.

## 23. Quan sát Redis và Spring khi dùng Sentinel

Đừng chỉ nhìn sức khỏe Redis master ban đầu. Cần quan sát ba lớp:

| Lớp | Tín hiệu quan trọng |
| --- | --- |
| Sentinel | Số Sentinel online, quorum, leader/failover events, địa chỉ master hiện tại |
| Redis nodes | Role, replication offset/lag, master link status, persistence, memory, evictions |
| Spring client | Connection failures, command timeouts, reconnects, errors như `READONLY`, request latency |

Lệnh Redis/Sentinel hữu ích:

```bash
redis-cli -h sentinel-a.internal -p 26379 SENTINEL master mymaster
redis-cli -h sentinel-b.internal -p 26379 SENTINEL master mymaster
redis-cli -h redis-node.internal -p 6379 INFO replication
redis-cli -h redis-node.internal -p 6379 INFO stats
```

Theo dõi logs từ Lettuce/Jedis và Spring Data Redis ở mức phù hợp khi có failover. Không nên bật debug log chứa thông tin kết nối/credential quá rộng trong production.

Metrics gợi ý:

```text
redis_connection_errors_total
redis_command_timeouts_total
redis_command_latency_seconds
redis_failover_events_total
redis_reconnects_total
redis_replication_lag_seconds
redis_role_changes_total
redis_fallback_reads_total
```

Tên metric chỉ mang tính gợi ý thiết kế; không phải mọi tên đều có sẵn từ Spring Boot Actuator. Cần gắn instrumentation theo client và hệ thống giám sát đang dùng.

### Liveness và readiness khác nhau

Một service có thể vẫn **live** dù Redis tạm thời không kết nối. **Readiness** quyết định có nên tiếp tục nhận traffic phụ thuộc Redis hay không.

Không nên restart toàn bộ pod liên tục chỉ vì Redis đang failover trong một khoảng ngắn; việc restart ồ ạt có thể làm vấn đề nặng hơn. Chính sách readiness/fallback phải theo nghiệp vụ và khả năng phục hồi của ứng dụng.

## 24. Kiểm thử kết nối Sentinel trước khi thử failover

Trong môi trường test:

1. Xác nhận có một master và ít nhất một replica.
2. Xác nhận các Sentinel cùng biết tên `mymaster`.
3. Chạy Spring app với cấu hình Sentinel.
4. Dùng `StringRedisTemplate` ghi một key thử nghiệm.
5. Đọc lại key để xác nhận đường data hoạt động.
6. Kiểm tra Sentinel báo đúng địa chỉ master hiện tại.
7. Xác minh key test không nằm trong namespace production.

Ví dụ smoke test Java:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class SentinelConnectionSmokeTest {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void canReadAndWriteUsingSentinelDiscoveredMaster() {
        String key = "test:sentinel:smoke";

        redis.opsForValue().set(key, "connected");

        assertThat(redis.opsForValue().get(key))
            .isEqualTo("connected");

        redis.delete(key);
    }
}
```

Đây là một smoke test minh họa. Nó cần môi trường Redis/Sentinel test đang chạy và cấu hình Spring Boot trỏ đúng mạng/credential. Test thành công chứng minh đường đọc/ghi lúc đó hoạt động, **chưa chứng minh failover hoạt động**.

Không chạy test xóa key dùng chung trong production.

## 25. Kiểm thử failover trong môi trường cô lập

Một bài integration test đầy đủ nên có một topology Redis master, replicas và nhiều Sentinel thực sự. Testcontainers có thể hỗ trợ chạy các container Redis/Sentinel, nhưng dựng topology nhiều process cần cấu hình mạng, persistence và advertise addresses; không nên giả định chỉ chạy một `GenericContainer` Redis mặc định là đã có Sentinel.

### Kịch bản

```text
1. Start Redis master + replicas + 3 Sentinel
2. Spring app kết nối qua Sentinel master name
3. SET smoke:sentinel = "before"
4. Kiểm tra GET trả "before"
5. Kích hoạt failover có kiểm soát
6. Quan sát master hiện tại đổi sang replica
7. Chờ client tìm lại master mới
8. SET smoke:sentinel:after = "after"
9. GET xác nhận lệnh dữ liệu mới hoạt động
10. Ghi nhận lỗi tạm thời trong quá trình failover
```

Trên Sentinel **chỉ trong môi trường thử nghiệm**, có thể dùng:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL FAILOVER mymaster
```

Lệnh này yêu cầu Sentinel thực hiện failover có kiểm soát nếu điều kiện phù hợp. Nó không phải thao tác nên chạy tùy tiện trên Redis production. Nếu cần mô phỏng crash thật, dùng môi trường test để dừng master rồi quan sát quá trình promote.

### Điều gì cần xác nhận?

- Client nhận địa chỉ master mới.
- Write sau failover đi vào master mới.
- Có lỗi tạm thời như timeout/connection failure trong cửa sổ failover.
- Các lệnh quan trọng có chính sách retry/idempotency thích hợp.
- Không nhầm lệnh read từ replica với write lên master.
- Các endpoint được Sentinel công bố reachable từ ứng dụng.
- Không mất bí mật trong logs/metrics.
- Hệ thống không gửi lại tác dụng phụ hai lần khi response của write bị mất.

Test không được chấm chỉ bằng câu “sau failover app vẫn còn chạy”; cần quan sát cụ thể đường Redis operation và ngữ nghĩa nghiệp vụ.

## 26. Khi thiết kế retry sau failover

Giả sử một service dùng Redis làm cache của database:

```text
GET product:42
     |
     +-- Redis reachable -> đọc cache
     |
     +-- Redis unavailable -> đọc database nguồn chuẩn
```

Đây là một fallback có thể phù hợp nếu Redis thật sự chỉ là cache và business cho phép bỏ cache.

Ngược lại, nếu Redis lưu một distributed lock hoặc counter dùng để ngăn oversell, không thể tùy tiện “bỏ qua Redis” rồi coi kiểm tra thành công. Khi Redis không khả dụng, nên fail closed hoặc chuyển sang một cơ chế đồng bộ có thẩm quyền khác.

Bảng định hướng:

| Mục đích Redis | Khi Sentinel failover |
| --- | --- |
| Cache đọc | Có thể fallback database, theo policy |
| Session | Xác định chính sách login/session availability |
| Rate limit | Chọn fail open/closed dựa trên rủi ro |
| Distributed lock | Không tự nhận lock khi Redis không rõ trạng thái |
| Idempotency key | Không đổi request ID khi retry |
| Counter tài chính | Không retry `INCR` vô điều kiện |
| Queue/Streams | Cần xem lại kết quả ACK/write sau reconnect |
| Pub/Sub | Chấp nhận gap hoặc có reconciliation |

Cách xử lý Redis unavailable phải được quyết định bởi yêu cầu của dữ liệu, không chỉ một annotation `@Retryable`.

## 27. Những lỗi cấu hình thường gặp

### Sai master name

Triệu chứng: Sentinel reachable nhưng client không tìm được master. Kiểm tra `SENTINEL get-master-addr-by-name mymaster`. Giá trị phải trùng `sentinel monitor` trong hạ tầng.

### Chỉ cấu hình một địa chỉ Sentinel

Nếu chỉ một Sentinel endpoint và nó unavailable, client có thể không tìm được master hiện tại dù các Sentinel khác còn chạy. Cấu hình nhiều Sentinel ở các failure domain khác nhau.

### Dùng hostname Sentinel làm host Redis cố định

```yaml
spring:
  data:
    redis:
      host: sentinel-a.internal
      port: 26379
```

Đây không phải cách cấu hình Sentinel đúng. Cổng `26379` cung cấp Sentinel commands, không phải đường data Redis thông thường cho mọi `GET/SET`.

### Chỉ mở port 26379

Application tìm được master nhưng connect tới `6379` thất bại. Mở network path tới các Redis data nodes có thể được promote.

### Dùng localhost trong container

`127.0.0.1` có thể trỏ vào chính Spring container. Dùng DNS/network service phù hợp và kiểm tra địa chỉ mà Sentinel trả về.

### Password của Sentinel và Redis data bị hoán đổi

Triệu chứng: `NOAUTH`, `WRONGPASS`, authentication failures. Kiểm tra credential cho từng đường: app→Sentinel, app→Redis data, Sentinel→Redis data.

### Redis ACL không cấp quyền đúng

App có thể discovery được master nhưng không đủ quyền `GET/SET`; hoặc Sentinel có thể authenticate nhưng không đủ quyền giám sát/failover. Đừng giải quyết bằng cách mở toàn bộ ACL nếu không cần; cấp quyền đúng vai trò.

### TLS bật một phía

Sentinel/Redis data nodes có thể dùng TLS khác nhau. Kết nối thành công tới Sentinel không chứng minh data path đã mã hóa đúng. Kiểm tra cả đường data và discovery.

### Client tiếp tục ghi vào node cũ

Trong failover có thể gặp `READONLY` hoặc timeout. Kiểm tra driver reconnect, thông tin topology, kết nối cũ và cách retry.

### Replica đọc stale data

Đọc replica có thể chậm hơn master. Không dùng replica reads cho quyết định đòi hỏi thấy write mới nhất nếu không có bảo đảm phù hợp.

### Chạy toàn bộ Sentinel trên một server

Ba process trên một máy không loại bỏ single point of failure của máy đó. Tách failure domains.

### Nhầm Redis Sentinel với Redis Cluster

Sai connection configuration có thể khiến client xử lý topology theo cơ chế không phù hợp. Chọn `RedisSentinelConfiguration` cho Sentinel master name, không dùng Cluster configuration thay thế.

## 28. Hướng dẫn chẩn đoán theo triệu chứng

| Triệu chứng | Khả năng cần kiểm tra | Bước chẩn đoán đầu tiên |
| --- | --- | --- |
| Không kết nối được Sentinel | DNS, firewall, port, TLS | Kiểm tra TCP tới từng `:26379` |
| Kết nối Sentinel nhưng không tìm thấy master | Sai master name, Sentinel chưa monitor | `SENTINEL get-master-addr-by-name` |
| Tìm được master nhưng Redis timeout | Address/port trả về không reachable | Kiểm tra đường tới data node `:6379` |
| `NOAUTH`/`WRONGPASS` | Sai user/password một trong các đường | Tách auth Sentinel và auth Redis |
| `READONLY` sau failover | Client vẫn thấy replica/node cũ | Kiểm tra role/master discovery, reconnect |
| Thỉnh thoảng mất lệnh khi failover | Disconnect, replica lag, retry | Xem timestamps, error logs, idempotency |
| GET trả dữ liệu cũ | Replica reads hoặc cache TTL | Kiểm tra `ReadFrom`, source of truth |
| Failover không xảy ra | Quorum/majority, replica không đủ điều kiện | Xem `SENTINEL master`, Sentinel logs |
| Ứng dụng chạy nhưng ghi lỗi sau failover | Redis mới không reachable/ACL | Kiểm tra address, ACL, role |
| Một Sentinel trả master khác | Topology đang hội tụ hoặc cấu hình lệch | Kiểm tra nhiều Sentinel và failover state |

Không nên thay đổi nhiều yếu tố cùng lúc (password, DNS, TLS, master name) rồi không biết điều gì gây lỗi. Kiểm tra từ network/discovery → Redis data connection → Spring factory → business operation.

## 29. Checklist triển khai production

**Hạ tầng Redis**

- Có master và replicas phù hợp yêu cầu HA.
- Có ít nhất ba Sentinel trên các failure domain thích hợp cho thiết kế phổ biến.
- Quorum, timeout, replica priority và failover policy được vận hành quản lý.
- Master/replica replication và persistence được cấu hình theo nhu cầu.
- Redis data nodes có địa chỉ reachable từ toàn bộ app nodes.
- Sentinel announce và data node advertise phù hợp network topology.
- Có monitoring role changes, replica lag, failover và persistence health.

**Spring Data Redis**

- `sentinel.master` đúng tên.
- `sentinel.nodes` chứa nhiều discovery endpoints.
- Prefix property phù hợp Spring Boot version.
- Client Lettuce/Jedis được lựa chọn rõ và dependency đúng.
- Auth cho Redis data và Sentinel được tách.
- TLS/CA/hostname validation đúng với topology.
- Timeout, pool và reconnect được kiểm tra dưới tải thật.
- Không đồng thời hard-code standalone host làm đường kết nối chính.
- Template serializers không bị thay đổi ngoài ý muốn.

**Ứng dụng và nghiệp vụ**

- Retry idempotent cho write có thể bị thực thi trước khi timeout.
- Có fallback khi Redis chỉ là cache; tránh fallback sai khi Redis là nguồn điều phối quan trọng.
- Không giả định zero downtime hay zero data loss.
- Đã kiểm thử failover có kiểm soát trong môi trường riêng.
- Có logs, metrics và alert về Sentinel + Redis + app.
- Có kế hoạch vận hành khi cả Sentinel hoặc nhiều Redis nodes cùng lỗi.

## 30. Bài tập thực hành

### Bài tập A — Cấu hình Spring Boot auto-configuration

Cho ba Sentinel:

```text
sentinel-1.internal:26379
sentinel-2.internal:26379
sentinel-3.internal:26379
```

Tên master `catalogmaster`. Hãy viết `application.yml` và một service dùng `StringRedisTemplate` ghi/đọc `catalog:test`. Giải thích vì sao không cần biết master IP cố định.

### Bài tập B — Tìm lỗi master name

Sentinel dùng:

```conf
sentinel monitor inventorymaster 10.10.0.11 6379 2
```

Spring dùng:

```yaml
sentinel:
  master: mymaster
```

Hãy giải thích nguyên nhân không tìm được master và cách sửa. Xác minh bằng `SENTINEL get-master-addr-by-name inventorymaster`.

### Bài tập C — Kiểm tra announced address

Spring chạy trong Kubernetes và truy cập được Sentinel, nhưng Sentinel trả IP private chỉ reachable từ một network khác. Hãy nêu lý do lỗi, phân biệt discovery endpoint và data endpoint, rồi đề xuất thay đổi network/advertise phù hợp.

### Bài tập D — Thử failover

Trong môi trường test có một master, hai replicas và ba Sentinel:

1. Ghi key bằng `StringRedisTemplate`.
2. Kích hoạt failover test.
3. Quan sát Sentinel master address đổi.
4. Ghi và đọc lại qua Spring connection factory.
5. Ghi nhận timeout/READONLY có thể xuất hiện.
6. Giải thích tại sao smoke test không chứng minh mọi write trước failover đều được bảo toàn.

### Bài tập E — Retry một lệnh INCR

Ứng dụng gửi `INCR billing:count`, Redis có thể đã thực thi nhưng response mất. Thiết kế một cách tránh tính trùng trong nghiệp vụ bằng idempotency key hoặc lưu request state. Giải thích vì sao retry mù quáng không đủ.

### Bài tập F — Authentication và TLS

Một ứng dụng yêu cầu Redis data user/password khác Sentinel user/password. Hãy vẽ hai đường kết nối và phân biệt credential app→Sentinel, app→Redis và Sentinel→Redis. Kiểm tra cấu hình TLS cho từng đường thay vì chỉ nhìn một cờ SSL.

## 31. Câu hỏi thường gặp

**Sentinel có phải một địa chỉ Redis proxy duy nhất không?**

Không. Sentinel giúp client khám phá master hiện tại; client thường kết nối trực tiếp tới Redis data node để thực hiện lệnh.

**Spring Boot có cần tự gọi SENTINEL get-master-addr-by-name mỗi request không?**

Không. Dùng cấu hình Sentinel với Lettuce/Jedis thông qua Spring Data Redis để driver quản lý discovery và reconnect.

**Master name trong YAML có phải hostname của Redis master không?**

Không. Nó là tên logic trong `sentinel monitor`, ví dụ `mymaster`.

**Vì sao Sentinel kết nối thành công nhưng GET/SET vẫn lỗi?**

Client còn phải truy cập được Redis data node mà Sentinel báo. Kiểm tra firewall, DNS/IP, TLS và credential trên đường Redis `:6379`.

**Có nên khai báo cả Redis host và Sentinel nodes không?**

Chọn một mô hình kết nối rõ ràng. Khi dùng Sentinel, master name và Sentinel nodes là thông tin discovery. Không dựa vào sự pha trộn host/port standalone để sửa lỗi failover.

**Có thể dùng StringRedisTemplate bình thường với Sentinel không?**

Có. Nếu `RedisConnectionFactory` được cấu hình Sentinel đúng, template sử dụng connection đó như những Redis operations khác.

**Sentinel có đảm bảo không mất write trong failover không?**

Không. Replication Redis thông thường là bất đồng bộ; write đã được master ACK vẫn có nguy cơ chưa được replica mới nhận.

**Trong failover, vì sao có timeout hoặc READONLY?**

Client có thể đang giữ connection tới node cũ, topology cần thời gian hội tụ và Redis mới cần được promote. Cần xử lý lỗi tạm thời và retry an toàn.

**Có nên luôn đọc replica để tăng hiệu năng không?**

Không mặc định. Replica có thể trả dữ liệu trễ. Chỉ dùng khi use case chấp nhận eventual consistency và client configuration phù hợp.

**Redis Sentinel và Redis Cluster có thể dùng cùng một connection config không?**

Không. Hai mô hình topology khác nhau; Spring Data Redis có cấu hình riêng cho Sentinel và Cluster.

**Có cần ba Sentinel?**

Triển khai ba Sentinel ở các failure domain độc lập là lựa chọn HA thường gặp. Số lượng và quorum thực tế phải dựa trên khả năng chịu lỗi, network và kiến trúc vận hành; một Sentinel duy nhất tạo điểm yếu trong discovery/failover.

**Bật TLS ở Redis data nodes có nghĩa Sentinel cũng tự dùng TLS không?**

Không thể suy ra. Cần xác minh cấu hình Redis/Sentinel server và Spring client hỗ trợ TLS trên từng đường.

## 32. Tổng kết

Cấu hình Redis Sentinel trong Spring Data Redis cần hiểu đúng **discovery**, **Redis data connection** và **failover**:

1. **Redis Sentinel là control plane**, theo dõi master/replicas và cung cấp địa chỉ master hiện tại; nó không proxy mọi lệnh Redis.
2. **Spring Boot dùng `spring.data.redis.sentinel.master` và `sentinel.nodes`** theo phiên bản Boot phù hợp để cấu hình discovery.
3. **Spring Data Redis có `RedisSentinelConfiguration`**, kết hợp `LettuceConnectionFactory` hoặc `JedisConnectionFactory` khi cần cấu hình Java thuần.
4. **Master name là tên logic**, không phải hostname; danh sách Sentinel là discovery endpoints, còn data operations kết nối tới Redis node.
5. **Authentication/TLS cần phân biệt các đường app→Sentinel, app→Redis và Sentinel→Redis**.
6. **Mọi node có thể trở thành master phải reachable** từ ứng dụng; Docker/Kubernetes/NAT/advertise addresses là nguồn lỗi phổ biến.
7. **Failover gây cửa sổ lỗi tạm thời** và replication bất đồng bộ có thể làm mất một số write; không giả định zero downtime hay zero data loss.
8. **Retry phải xét idempotency**, nhất là `INCR`, queue operations, Lua và transaction.
9. **Kiểm thử failover trên topology thật trong môi trường cô lập**, quan sát role, reconnect và đường đọc/ghi sau chuyển master.

Khi các nguyên tắc trên được áp dụng, Spring Boot có thể tiếp tục làm việc với Redis master thay đổi theo Sentinel mà không cần hard-code địa chỉ master, đồng thời vẫn có thiết kế rõ ràng để xử lý những khoảng lỗi không tránh khỏi của hệ thống phân tán.

## Tài liệu tham khảo chính thức

- [Spring Data Redis – Redis Sentinel Support](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html)
- [Spring Data Redis – RedisSentinelConfiguration API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/RedisSentinelConfiguration.html)
- [Spring Data Redis – LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot – Redis Auto Configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.redis)
- [Redis – High Availability with Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [Redis – Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis – WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis – Sentinel Commands](https://redis.io/docs/latest/commands/sentinel/)
