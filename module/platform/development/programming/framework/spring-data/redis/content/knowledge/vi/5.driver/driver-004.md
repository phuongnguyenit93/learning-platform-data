# Cấu hình `JedisConnectionFactory` trong Spring Data Redis

`JedisConnectionFactory` là lớp triển khai giao diện **`RedisConnectionFactory`** của Spring Data Redis bằng driver **Jedis**. Nó chịu trách nhiệm tạo và cung cấp kết nối Redis cho các thành phần Spring như `RedisTemplate`, `StringRedisTemplate`, Redis Cache và những API đồng bộ khác sử dụng Spring Data Redis. Khi dùng Jedis, cấu hình connection factory là điểm tập trung để xác định Redis server, cơ chế xác thực, timeout, TLS, connection pool và topology như standalone, Sentinel hoặc Cluster.

Trong ứng dụng Spring Boot, có hai cách thường gặp:

1. **Để Spring Boot tự cấu hình**: khai báo Jedis trên classpath, chọn `client-type: jedis` và cấu hình `spring.data.redis.*`. Đây là cách phù hợp với đa số ứng dụng.
2. **Tự khai báo bean `JedisConnectionFactory`**: xây dựng `RedisStandaloneConfiguration`, `RedisSentinelConfiguration` hoặc `RedisClusterConfiguration` kết hợp `JedisClientConfiguration` khi cần kiểm soát kết nối ngoài những tùy chọn Boot đang cung cấp.

Bài học tập trung vào cách cấu hình đúng trong Spring Data Redis, ý nghĩa từng lớp, điều gì thay đổi khi chuyển topology và những lỗi thực tế dễ gặp khi tích hợp Jedis với Spring Boot.

## 1. `JedisConnectionFactory` nằm ở đâu trong kiến trúc?

Lớp này thuộc package:

```java
org.springframework.data.redis.connection.jedis.JedisConnectionFactory
```

Nó là một adapter giữa Spring Data Redis và thư viện client `redis.clients:jedis`:

```text
                 Ứng dụng Spring Boot
                         |
             Service / Repository / Cache
                         |
          RedisTemplate / StringRedisTemplate
                         |
                RedisConnectionFactory
                         |
                JedisConnectionFactory
                  /               \
     RedisStandaloneConfiguration  JedisClientConfiguration
       hoặc Sentinel / Cluster       timeout / TLS / pool
                  \               /
                    Jedis client
                         |
               Redis standalone / Sentinel / Cluster
```

`RedisConnectionFactory` là **abstraction của Spring Data Redis**; `JedisConnectionFactory` là **một implementation**. `LettuceConnectionFactory` là implementation phổ biến khác, dùng driver Lettuce. Code nghiệp vụ nên làm việc qua `RedisTemplate` hoặc các abstraction Spring Data Redis, nhờ đó có thể đổi driver mà không phải thay toàn bộ lệnh thao tác dữ liệu.

Phân biệt trách nhiệm các lớp:

| Thành phần | Vai trò |
|---|---|
| `JedisConnectionFactory` | Tạo/lấy kết nối Redis thông qua Jedis; tích hợp với vòng đời bean Spring |
| `RedisStandaloneConfiguration` | Cấu hình host, port, database, credentials của standalone server |
| `RedisSentinelConfiguration` | Cấu hình tên master Sentinel, địa chỉ sentinel, xác thực liên quan |
| `RedisClusterConfiguration` | Cấu hình seed nodes, redirect, credentials của Redis Cluster |
| `JedisClientConfiguration` | Cấu hình phía Jedis như connection pooling, timeout, SSL/TLS |
| `RedisTemplate<K,V>` | Thực thi lệnh Redis và dùng serializer cho key/value |
| `StringRedisTemplate` | Template thuận tiện cho dữ liệu key và value dạng chuỗi |

Một connection factory **không tự quyết định serializer cho từng nghiệp vụ**. Nó cung cấp kết nối; template hoặc cache configuration mới quyết định cách dữ liệu Java biến thành các byte mà Redis lưu trữ.

## 2. Jedis và Lettuce: chọn đúng loại driver

Spring Data Redis hỗ trợ các driver phổ biến, nhưng Jedis và Lettuce có những điểm khác nhau:

| Tiêu chí | Jedis | Lettuce |
|---|---|---|
| Lớp Spring Data Redis | `JedisConnectionFactory` | `LettuceConnectionFactory` |
| API Spring Data đồng bộ | Hỗ trợ | Hỗ trợ |
| `ReactiveRedisTemplate` qua Spring Data Redis | Không phải driver reactive của Spring Data Redis | Hỗ trợ qua `ReactiveRedisConnectionFactory` |
| Mô hình kết nối thường dùng | Pool các kết nối đồng bộ khi có nhiều request đồng thời | Có thể chia sẻ native connection cho nhiều thao tác nhờ mô hình I/O của Lettuce; cấu hình tùy tình huống |
| Standalone / Sentinel / Cluster | Hỗ trợ theo phiên bản Jedis và Spring Data Redis tương ứng | Hỗ trợ |
| Tích hợp trong Spring Boot starter | Cần thêm dependency Jedis nếu starter mặc định mang Lettuce | Thường có sẵn với starter mặc định |

Nếu ứng dụng dựa trên Spring MVC, service đồng bộ và muốn sử dụng Jedis, `JedisConnectionFactory` là một lựa chọn phù hợp. Nếu ứng dụng dùng **`ReactiveRedisTemplate`** hoặc luồng Reactor end-to-end, nên chọn Lettuce và `LettuceConnectionFactory`, vì `JedisConnectionFactory` không triển khai `ReactiveRedisConnectionFactory` cho Spring Data Redis.

Điểm cần nhớ: **đưa thư viện Jedis vào dependency không tự đảm bảo ứng dụng đang dùng Jedis**, đặc biệt khi cả Lettuce và Jedis cùng có trên classpath. Cần xác định driver được chọn bởi cấu hình auto-configuration hoặc bean connection factory thực sự đang chạy.

## 3. Thêm dependency cho Jedis trong Spring Boot

Ví dụ Gradle Groovy DSL với Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'redis.clients:jedis'

    // Cần khi dùng connection pool và môi trường chưa có sẵn dependency này.
    implementation 'org.apache.commons:commons-pool2'
}
```

Nếu dự án dùng Spring Boot dependency management hoặc Gradle platform do Boot quản lý, nên **để BOM quyết định các phiên bản tương thích** của Spring Data Redis và Jedis; tránh tùy ý ghép một bản Jedis mới với Spring Data Redis cũ. Thư viện Commons Pool 2 hỗ trợ pooling của Jedis. Khi dự án không dùng dependency management, phải xác định và đồng bộ các version tương thích một cách tường minh.

Với Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>redis.clients</groupId>
        <artifactId>jedis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-pool2</artifactId>
    </dependency>
</dependencies>
```

Trong bài, các ví dụ thuộc nhóm cấu hình **Spring Boot 3.x** với namespace `spring.data.redis.*`. Nếu đang duy trì ứng dụng Spring Boot 2.x, tên thuộc tính Redis thường thuộc nhóm `spring.redis.*`, và API/kết hợp thư viện có thể khác. Nên đối chiếu tài liệu đúng phiên bản đang triển khai.

## 4. Cách khuyến nghị: Spring Boot tự tạo `JedisConnectionFactory`

Khi mục tiêu chỉ là kết nối Redis standalone bằng Jedis, có thể dùng `application.yml`:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
      jedis:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 2
          max-wait: 2s
```

Ý nghĩa:

- `client-type: jedis`: yêu cầu Spring Boot auto-configuration chọn Jedis khi driver khả dụng và không có bean connection factory do ứng dụng tự cung cấp.
- `host`, `port`: địa chỉ Redis standalone.
- `database: 0`: logical database; có thể dùng giá trị khác `0` với Redis standalone hỗ trợ nhiều DB, nhưng **Redis Cluster chỉ dùng DB 0**.
- `connect-timeout`: thời gian tối đa chờ thiết lập kết nối mạng.
- `timeout`: timeout cho các thao tác đọc/ghi theo cách Spring Boot và driver áp dụng cho phiên bản tương ứng.
- `jedis.pool.*`: giới hạn và duy trì các connection có thể tái sử dụng.

Với cấu hình và dependency phù hợp, Boot sẽ tạo một `RedisConnectionFactory` sử dụng Jedis. Các bean như `StringRedisTemplate` do Boot auto-configure sẽ tiêu thụ connection factory đó. Ứng dụng **không cần tự gọi** `new JedisConnectionFactory(...)` trong mỗi service.

### Cấu hình môi trường và mật khẩu

Trong môi trường có xác thực, có thể bổ sung:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME:default}
      password: ${REDIS_PASSWORD}
```

Ví dụ này yêu cầu `REDIS_HOST` và `REDIS_PASSWORD` có giá trị trong môi trường triển khai. `default` là tên user ACL mặc định của Redis 6+; nếu hệ thống chỉ dùng `requirepass` và không cấu hình ACL user riêng, cơ chế xác thực cần phù hợp với server và driver. Không ghi password thật vào repository, log hoặc ví dụ được đưa lên môi trường công khai.

Nếu ứng dụng nằm trong Docker Compose, `localhost` bên trong container thường trỏ về **chính container ứng dụng**. Khi Redis chạy container riêng trong cùng Compose network, dùng DNS service name, chẳng hạn `redis`, thay cho `localhost`.

## 5. Khai báo bean `JedisConnectionFactory` thủ công

Khi cần chính sách kết nối đặc thù, hoặc muốn tách các connection factory, có thể tạo bean bằng Java config.

Ví dụ một kết nối standalone có pooling và timeout:

```java
package com.example.redis;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.jedis.JedisClientConfiguration;
import org.springframework.data.redis.connection.jedis.JedisConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class JedisRedisConfiguration {

    @Bean
    public RedisConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("localhost", 6379);
        server.setDatabase(0);

        JedisClientConfiguration client = JedisClientConfiguration.builder()
                .connectTimeout(Duration.ofSeconds(2))
                .readTimeout(Duration.ofSeconds(3))
                .usePooling()
                .build();

        return new JedisConnectionFactory(server, client);
    }
}
```

Các bước có ý nghĩa riêng:

1. `RedisStandaloneConfiguration` mô tả **server cần kết nối** và logical database.
2. `JedisClientConfiguration` mô tả **hành vi client** như timeout, pooling và có thể là TLS.
3. Constructor `new JedisConnectionFactory(server, client)` ghép hai nhóm thông tin để tạo connection factory.
4. `@Bean` trao quyền quản lý vòng đời factory cho Spring: Spring khởi tạo bean và giải phóng tài nguyên khi context đóng.

Nếu dùng cách thủ công, **Spring Boot không tự áp toàn bộ `spring.data.redis.*` lên bean do bạn tự tạo**. Ví dụ, đổi `spring.data.redis.host` trong YAML chưa chắc thay đổi host hard-code `"localhost"` trong bean phía trên. Muốn cấu hình từ môi trường, hãy bind thuộc tính qua `@ConfigurationProperties`, `RedisProperties` hoặc inject giá trị phù hợp. Tránh khai báo cả auto-configured factory và một factory thủ công tùy tiện khi chưa quyết định bean nào là nguồn chính.

### Constructor và vòng đời bean

`JedisConnectionFactory` triển khai các hợp đồng vòng đời cần thiết với Spring. Trong ứng dụng dùng `@Bean`, framework sẽ gọi những callback khởi tạo/đóng tài nguyên tương ứng. Không cần tạo factory cho mỗi request hoặc tự gọi `afterPropertiesSet()` khi factory đã thuộc Spring ApplicationContext.

Nếu tạo factory bên ngoài Spring để dùng riêng, cần hiểu và tự quản lý vòng đời của factory theo API phiên bản sử dụng. Trong ứng dụng Spring Boot thông thường, nên để container quản lý để tránh rò rỉ connection/pool.

## 6. `RedisStandaloneConfiguration`: địa chỉ, DB và xác thực

Standalone là Redis server thông thường, có thể có một replica và cơ chế failover bên ngoài, nhưng client kết nối theo endpoint cụ thể. Các thuộc tính tiêu biểu:

```java
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;

RedisStandaloneConfiguration standalone =
        new RedisStandaloneConfiguration("redis.internal", 6379);

standalone.setDatabase(1);
standalone.setUsername("app_user");
standalone.setPassword(RedisPassword.of("example-secret"));
```

`example-secret` chỉ là placeholder. Trong code sản phẩm, lấy mật khẩu từ secret manager hoặc cấu hình môi trường, không ghi hằng số trong source. Những version Redis không dùng ACL username cần thiết lập xác thực phù hợp với cách Redis được cấu hình.

Điểm dễ nhầm:

- `database` là chỉ số database logic, không phải tên schema hay database kiểu SQL.
- `database: 1` chỉ thích hợp cho standalone khi server đã bật đủ logical database.
- Database khác `0` **không dùng được khi factory kết nối Redis Cluster**.
- Khai báo một IP primary cố định không tự tạo cơ chế tự phát hiện primary mới khi xảy ra failover. Muốn Sentinel discovery thì cần topology Sentinel tương ứng.

## 7. `JedisClientConfiguration`: timeout, TLS, connection pool

Thông tin server và chính sách client được tách nhau để dễ hiểu. `JedisClientConfiguration` không chỉ định key hay value serializer; nó kiểm soát Jedis kết nối ra sao.

### 7.1. Timeout kết nối và timeout lệnh

Một cấu hình mẫu:

```java
JedisClientConfiguration client = JedisClientConfiguration.builder()
        .connectTimeout(Duration.ofSeconds(2))
        .readTimeout(Duration.ofSeconds(3))
        .usePooling()
        .build();
```

**Connect timeout** giới hạn thời gian thiết lập TCP/TLS connection tới Redis. **Read timeout** liên quan tới thời gian chờ phản hồi lệnh từ server. Cần phân biệt hai loại timeout này với thời gian chờ một connection rảnh trong pool (`max-wait`). Một kết nối đến server chậm, một câu lệnh bị chậm và việc pool đã dùng hết đều là các nguyên nhân khác nhau dẫn tới timeout.

Không có một giá trị timeout tối ưu cho mọi ứng dụng. Ví dụ, thao tác cache đơn giản thường cần phản hồi nhanh, trong khi tác vụ đang thực hiện command tốn thời gian có chính sách riêng. Giá trị timeout còn phải phù hợp với latency thực tế, mức độ tải, retry và SLA của request.

### 7.2. Bật TLS

Nếu Redis server được cấu hình TLS, client cũng phải bật TLS. Ví dụ ở mức Jedis:

```java
JedisClientConfiguration tlsClient = JedisClientConfiguration.builder()
        .useSsl()
        .build();
```

Với Spring Boot auto-configuration, có thể sử dụng:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      host: redis-secure.example.net
      port: 6380
      ssl:
        enabled: true
```

Port `6380` chỉ là ví dụ; cổng thực tế phụ thuộc dịch vụ Redis đang chạy. TLS cũng đòi hỏi cấu hình certificate/truststore và xác minh hostname phù hợp. Không tắt xác thực chứng chỉ chỉ để vượt lỗi handshake trong môi trường cần bảo mật.

Nếu đang dùng **bean factory thủ công**, thuộc tính `spring.data.redis.ssl.enabled` sẽ không tự khiến `JedisClientConfiguration` hard-code trong code được bật TLS. Cần chuyển cấu hình SSL vào builder tương ứng.

### 7.3. Pooling là gì?

Jedis thường làm việc với các kết nối đồng bộ được lấy theo từng luồng thao tác. Một connection pool giữ sẵn các connection để ứng dụng mượn, sử dụng rồi trả về, tránh chi phí kết nối mới cho mỗi lệnh:

```text
Thread A ---> borrow ---> [Redis connection #1] ---\
Thread B ---> borrow ---> [Redis connection #2] ----> Redis
Thread C ---> borrow ---> [Redis connection #3] ---/
                  |
               return
                  v
             Jedis pool
```

Một `JedisConnection`/native Jedis connection dùng cho thao tác đơn lẻ **không nên được nhiều thread sử dụng đồng thời**. Thay vì tự giữ `Jedis` object rồi chia sẻ trong singleton service, hãy dùng `RedisTemplate` và factory được Spring quản lý để việc mượn/trả connection diễn ra theo cơ chế framework.

## 8. Cấu hình Jedis connection pool chi tiết

Khi dùng Spring Boot auto-configuration, nhóm thuộc tính pool phổ biến như sau:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      jedis:
        pool:
          enabled: true
          max-active: 24
          max-idle: 12
          min-idle: 3
          max-wait: 1500ms
          time-between-eviction-runs: 30s
```

| Thuộc tính | Ý nghĩa | Nếu đặt không hợp lý |
|---|---|---|
| `max-active` | Số connection có thể được pool cấp phát đồng thời | Quá nhỏ gây tranh chấp; quá lớn có thể gây áp lực lên Redis |
| `max-idle` | Số connection nhàn rỗi tối đa pool giữ lại | Quá lớn tăng connection idle không cần thiết |
| `min-idle` | Mục tiêu connection idle tối thiểu | Quá lớn làm giữ nhiều connection dù tải thấp |
| `max-wait` | Thời gian chờ tối đa khi mượn connection mà pool đang hết chỗ | Quá ngắn gây lỗi khi tải đột biến; quá dài làm request chậm |
| `time-between-eviction-runs` | Khoảng giữa những lần quét idle connection theo hỗ trợ của pool | Cần phối hợp với chính sách kiểm tra idle và tài nguyên |

Các số trong ví dụ chỉ dùng để giải thích; không phải cấu hình chuẩn cho production. Một service có 10 instance, mỗi instance đặt `max-active: 24`, có thể tạo tới khoảng **240 connection đang hoạt động** trong trường hợp tất cả pool đạt mức tối đa. Cần so với `maxclients` và tải CPU/network của Redis, các connection quản trị/monitoring và những ứng dụng khác cùng truy cập.

### Khi pool hết connection sẽ xảy ra gì?

Giả sử service có `max-active: 2` nhưng 20 request cùng lúc phải thực hiện thao tác Redis đang chậm:

```text
Request 1 ---- dùng connection A ------------------>
Request 2 ---- dùng connection B ------------------>
Request 3 ---- chờ pool (-- max-wait --) -> timeout
Request 4 ---- chờ pool (-- max-wait --) -> timeout
...
```

Lúc này lỗi có thể là **không mượn được connection từ pool**, không nhất thiết vì Redis server từ chối kết nối. Cần kiểm tra thời gian thực thi Redis command, số lượng request đồng thời, kích thước pool, việc kết nối được hoàn trả đúng cách và khả năng Redis quá tải. Tăng `max-active` vô hạn chỉ chuyển điểm nghẽn sang server.

### Connection pooling trong Java config

Jedis hỗ trợ dùng Commons Pool 2 và Spring Data Redis cung cấp builder để bật pooling. Đoạn cấu hình tối thiểu:

```java
JedisClientConfiguration jedisClient =
        JedisClientConfiguration.builder().usePooling().build();

JedisConnectionFactory factory =
        new JedisConnectionFactory(
                new RedisStandaloneConfiguration("localhost", 6379),
                jedisClient);
```

Nếu muốn tùy biến sâu các giới hạn pool trong code, Jedis pooling builder có thể nhận cấu hình Commons Pool tương ứng; kiểu cấu hình và generic liên quan phụ thuộc phiên bản Jedis/Spring Data Redis. Với ứng dụng Spring Boot, thường dễ vận hành hơn khi để các tham số pool trong `application.yml`, tránh chôn những giới hạn capacity vào Java source.

## 9. Cấu hình kết nối Redis Sentinel bằng Jedis

**Redis Sentinel** là cơ chế giám sát Redis master/replica và hỗ trợ discovery/failover. Ứng dụng không nên hard-code địa chỉ một primary có thể thay đổi khi failover. Thay vào đó, Sentinel configuration cung cấp tên master và danh sách endpoint Sentinel.

Ví dụ Spring Boot:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.example.net:26379
          - sentinel-2.example.net:26379
          - sentinel-3.example.net:26379
      username: ${REDIS_USERNAME:default}
      password: ${REDIS_PASSWORD}
      connect-timeout: 2s
      timeout: 3s
```

`mymaster` là tên master group mà Sentinel biết, không phải hostname cụ thể của master Redis. Các địa chỉ `sentinel-*` cần trỏ tới **Sentinel service**, thường nghe cổng `26379`; chúng khác với endpoint của Redis data nodes, thường nghe cổng `6379` nếu chưa tùy chỉnh.

Khi Sentinel tự có cơ chế xác thực riêng, cần cấu hình **credential của Sentinel** bên cạnh credential dành cho Redis data nodes, dùng thuộc tính/cấu hình được hỗ trợ bởi phiên bản Spring Boot và Spring Data Redis đang chạy. Không giả định password Redis server tự dùng được để đăng nhập Sentinel.

### Cấu hình Sentinel bằng Java

```java
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.jedis.JedisClientConfiguration;
import org.springframework.data.redis.connection.jedis.JedisConnectionFactory;

RedisSentinelConfiguration sentinel = new RedisSentinelConfiguration()
        .master("mymaster")
        .sentinel("sentinel-1.example.net", 26379)
        .sentinel("sentinel-2.example.net", 26379)
        .sentinel("sentinel-3.example.net", 26379);

JedisClientConfiguration client =
        JedisClientConfiguration.builder().usePooling().build();

JedisConnectionFactory factory =
        new JedisConnectionFactory(sentinel, client);
```

Đoạn này minh họa topology, chưa khai báo xác thực hoặc TLS. Khi triển khai thật, bổ sung credential cho cả Redis và Sentinel nếu cần. Với bean được Spring quản lý, trả về factory từ một `@Bean`; Spring sẽ quản lý vòng đời và expose nó cho các template.

**Sentinel không phải Redis Cluster.** Sentinel quản lý failover của một nhóm master/replica; nó không phân phối key theo 16.384 slot như Cluster. Cách ứng dụng xác định logical database và mô hình dữ liệu trong Sentinel vẫn khác so với Cluster.

## 10. Cấu hình kết nối Redis Cluster bằng Jedis

Redis Cluster phân phối dữ liệu qua các hash slot. Khi dùng Jedis với Spring Data Redis, cấu hình seed nodes để client khám phá topology và định tuyến lệnh tới node phù hợp.

Ví dụ Spring Boot:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      cluster:
        nodes:
          - redis-1.example.net:6379
          - redis-2.example.net:6379
          - redis-3.example.net:6379
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
```

Nếu Cluster dùng username/password, TLS hoặc cấu hình pool riêng, bổ sung các thuộc tính tương ứng. Danh sách node trên là những endpoint khởi tạo kết nối (**seed nodes**), không có nghĩa dữ liệu chỉ nằm ở ba node này. Các node do Cluster quảng bá phải có địa chỉ mà ứng dụng có thể truy cập được. Nếu Cluster chạy trong mạng container, NAT hoặc Kubernetes, cần kiểm tra địa chỉ quảng bá/tuyến mạng phù hợp.

Ví dụ Java config:

```java
import java.util.List;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.jedis.JedisClientConfiguration;
import org.springframework.data.redis.connection.jedis.JedisConnectionFactory;

RedisClusterConfiguration cluster = new RedisClusterConfiguration(
        List.of(
                "redis-1.example.net:6379",
                "redis-2.example.net:6379",
                "redis-3.example.net:6379"));
cluster.setMaxRedirects(5);

JedisClientConfiguration client =
        JedisClientConfiguration.builder().usePooling().build();

JedisConnectionFactory factory =
        new JedisConnectionFactory(cluster, client);
```

Với Cluster cần ghi nhớ:

- **Redis Cluster chỉ hỗ trợ logical database `0`**. Không dùng `database: 1` hoặc cố chạy lệnh `SELECT`.
- Client hỗ trợ Cluster phải điều hướng theo hash slot, có thể nhận các redirect như `MOVED` hoặc `ASK` khi trạng thái slot thay đổi.
- Những thao tác nhiều key cần kiểm tra ràng buộc các key có cùng slot. Prefix giống nhau chưa chắc đồng nghĩa cùng slot; hash tag `{...}` có thể giúp đặt các key liên quan vào cùng slot khi thật sự cần.
- `FLUSHDB`, `DBSIZE`, `SCAN` trên một node không mặc nhiên là thao tác/quan sát toàn bộ Cluster; công cụ quản trị phải biết topology và phạm vi của từng node.

`JedisConnectionFactory` giải quyết phần kết nối Cluster; nó không tự chuyển chiến lược key/transaction từ standalone sang Cluster. Khi migrate, cần kiểm tra code sử dụng Lua, multi-key commands và những chỗ dựa vào database index.

## 11. Sử dụng connection factory từ `RedisTemplate`

Khi factory đã được tạo, cách gọi thông thường của service không phụ thuộc trực tiếp vào Jedis:

```java
package com.example.redis;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class VisitCounter {

    private final StringRedisTemplate redis;

    public VisitCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment(String articleId) {
        return redis.opsForValue().increment("article:visits:" + articleId);
    }

    public void saveLastVisited(String articleId, String userId) {
        redis.opsForValue().set(
                "article:last-viewed:" + articleId,
                userId,
                Duration.ofMinutes(30));
    }
}
```

`StringRedisTemplate` sử dụng factory do Spring cấp và serialization kiểu string. `increment(...)` dùng lệnh Redis trên giá trị số dạng chuỗi; thao tác trả về `Long` có thể là `null` trong một số ngữ cảnh pipeline/transaction, vì vậy cần xem xét hợp đồng API ở nơi dùng kết quả.

Nếu muốn tự khai báo template:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class TemplateConfig {

    @Bean
    StringRedisTemplate stringRedisTemplate(RedisConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }
}
```

Với Spring Boot, bean `StringRedisTemplate` thường đã được auto-configure nếu chưa có bean phù hợp; khai báo thêm chỉ khi có lý do cụ thể. Nếu đồng thời tồn tại nhiều `RedisConnectionFactory`, cần chọn factory bằng `@Qualifier` hoặc xác định bean `@Primary` để tránh injection mơ hồ.

### Kết nối trực tiếp: chỉ khi thật sự cần

Spring Data Redis có API `RedisConnection` để truy cập lệnh cấp thấp:

```java
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;

public String ping(RedisConnectionFactory factory) {
    try (RedisConnection connection = factory.getConnection()) {
        return connection.ping();
    }
}
```

Khi lấy connection trực tiếp, người gọi cần đóng đúng cách để trả connection về pool hoặc giải phóng tài nguyên. Trong code nghiệp vụ thông thường nên dùng `RedisTemplate` để framework quản lý vòng đời connection, exception translation và các thao tác dữ liệu nhất quán hơn.

## 12. Phân biệt pool connection, Redis database và serializer

Ba khái niệm thường bị lẫn với nhau:

**Connection pool** là nơi giữ connection TCP tái sử dụng. Nhiều connection trong pool có thể cùng thao tác DB 0, và một pool lớn không có nghĩa có thêm Redis database.

**Logical database** là không gian key được chọn trên Redis standalone. Chỉ số database là một phần của server configuration. Trong Redis Cluster, lựa chọn này bị giới hạn ở DB 0.

**Serializer** biến giá trị Java thành byte Redis. Việc thay `JedisConnectionFactory` bằng `LettuceConnectionFactory` không tự chuyển dữ liệu đang lưu từ JDK serialization sang JSON hoặc thay đổi tên key. Cấu hình serializer của `RedisTemplate`/`RedisCacheManager` là một hợp đồng độc lập.

Ví dụ, cùng factory có thể phục vụ hai template với serializer khác nhau:

```text
JedisConnectionFactory
      |
      +--> StringRedisTemplate
      |      key: UTF-8 string
      |      value: UTF-8 string
      |
      +--> RedisTemplate<String, Product>
             key: UTF-8 string
             value: JSON Product
```

Nếu hai template đọc cùng một key mà không thống nhất serializer, có thể gặp lỗi deserialize dù kết nối Jedis hoàn toàn khỏe mạnh. Khi có nhiều nhóm dữ liệu hoặc nhiều service, dùng prefix key và format payload rõ ràng.

## 13. Cách Spring Boot chọn factory và những tình huống dễ xung đột

Xét các tình huống sau:

| Tình huống | Hành vi cần dự kiến |
|---|---|
| Có `spring-boot-starter-data-redis` mặc định và không cấu hình Jedis | Thường dùng Lettuce nếu dependency của starter còn nguyên |
| Có cả Lettuce và Jedis, khai báo `client-type: jedis` | Spring Boot lựa chọn Jedis cho auto-config khi điều kiện classpath và bean phù hợp |
| Có `@Bean RedisConnectionFactory` tự tạo | Auto-config factory thường nhường cho bean tùy chỉnh; thuộc tính Boot không tự áp lên toàn bộ builder thủ công |
| Có hai bean `RedisConnectionFactory` | Injection theo kiểu có thể mơ hồ; cần `@Primary` hoặc `@Qualifier` |
| Có `ReactiveRedisTemplate` nhưng chỉ có Jedis factory | Không có `ReactiveRedisConnectionFactory` thích hợp cho Redis reactive qua Jedis |
| Có `RedisTemplate` tự tạo với serializer tùy chỉnh | Connection factory cung cấp kết nối; serializer của template vẫn phải được cấu hình riêng |

Nếu muốn xác nhận loại factory tại runtime, có thể kiểm tra bean class thay vì suy đoán theo dependency:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class RedisFactoryInspector {

    @Bean
    ApplicationRunner inspectRedisFactory(RedisConnectionFactory factory) {
        return args -> System.out.println(
                "Redis connection factory: " + factory.getClass().getName());
    }
}
```

Đây là đoạn quan sát trong môi trường học tập; ứng dụng production nên sử dụng hệ thống logging thay vì `System.out.println`. Một kết quả chứa tên class `JedisConnectionFactory` cho biết Spring đang injection driver Jedis. Nếu bean được wrapper hoặc proxy, cần kiểm tra thêm cấu hình thực tế của ApplicationContext.

## 14. Một cấu hình môi trường phát triển hoàn chỉnh

Ví dụ `application-dev.yml` dành cho Redis standalone không yêu cầu xác thực trong một môi trường dev cô lập:

```yaml
spring:
  config:
    activate:
      on-profile: dev
  data:
    redis:
      client-type: jedis
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
      jedis:
        pool:
          enabled: true
          max-active: 8
          max-idle: 4
          min-idle: 1
          max-wait: 1s
```

Khi dùng một profile khác cho production, cấu hình không cần giống các giá trị dev. Production thường cần endpoint nội bộ, xác thực, TLS, giới hạn connection theo tải, quan sát lỗi và chính sách retry phù hợp. Lưu ý rằng những thuộc tính thuộc `spring.data.redis.*` chỉ có tác dụng trên factory do Spring Boot tạo/bind hoặc code tùy chỉnh chủ động đọc các thuộc tính đó.

Đoạn code đơn giản để thao tác một key:

```java
import java.time.Duration;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class RedisExampleRunner {

    @Bean
    ApplicationRunner demoRedis(StringRedisTemplate redis) {
        return args -> {
            String key = "demo:jedis:status";
            redis.opsForValue().set(key, "connected", Duration.ofSeconds(60));
            String value = redis.opsForValue().get(key);
            System.out.println("Read from Redis: " + value);
        };
    }
}
```

Trong một môi trường dev có Redis đang hoạt động, kết quả đọc thông thường là:

```text
Read from Redis: connected
```

Demo trên phát sinh thao tác ghi Redis mỗi lần ứng dụng chạy; chỉ bật runner trong môi trường thực hành, không để code demo tự ghi vào Redis production. Cấu hình `@Profile("dev")` trên class hoặc bean là một cách giới hạn phạm vi.

## 15. Các lỗi phổ biến khi cấu hình `JedisConnectionFactory`

| Biểu hiện | Nguyên nhân thường gặp | Cách tiếp cận |
|---|---|---|
| Không tìm thấy class `JedisConnectionFactory` hoặc `Jedis` | Thiếu dependency Spring Data Redis/Jedis, version không tương thích | Kiểm tra dependency graph và BOM đúng phiên bản |
| App đang dùng `LettuceConnectionFactory` | Chỉ thêm Jedis nhưng chưa chọn driver, hoặc có bean factory khác | Kiểm tra `client-type`, các bean và auto-configuration |
| `Connection refused` | Redis chưa chạy, sai host/port, nhầm `localhost` trong Docker | Kiểm tra DNS, network, container, endpoint Redis |
| `NOAUTH` hoặc `WRONGPASS` | Sai password, username ACL, secret hoặc credential Sentinel | Tách credential Redis server và Sentinel; kiểm tra quyền ACL |
| `SSLHandshakeException` | TLS sai cổng hoặc certificate/trust không hợp lệ | Kiểm tra TLS ở client và server; certificate chain, hostname |
| Timeout khi lấy connection | Pool quá nhỏ hoặc connection bị giữ lâu | Kiểm tra pool wait, concurrency, thời gian lệnh và trả connection |
| `RedisCommandTimeoutException` hoặc lỗi timeout tương tự | Redis hoặc mạng chậm, timeout quá ngắn | Phân biệt connect/read/pool wait; quan sát latency trước khi tăng timeout |
| `ERR SELECT is not allowed in cluster mode` | Đang dùng non-zero logical DB hoặc cố gửi `SELECT` trong Cluster | Dùng DB 0; bỏ logic chọn database |
| `MOVED`, `CROSSSLOT` khi truy cập Cluster | Client không theo topology, multi-key khác slot | Sử dụng Cluster-aware factory; rà soát multi-key/hash tag |
| `SerializationException` | Serializer đọc không tương thích dữ liệu đã lưu | Kiểm tra key/value serializer; đây thường không phải lỗi Jedis connection |
| Không inject được `RedisConnectionFactory` | Có nhiều bean cùng kiểu và không có qualifier/primary | Định rõ bean mà template/service phải dùng |
| Cấu hình YAML không tác dụng | Factory tự tạo bằng giá trị hard-code | Bind cấu hình trong Java hoặc chọn Spring Boot auto-config |

### Phân tích một lỗi timeout cho đúng tầng

Khi service báo lỗi liên quan tới Redis, nên xác định nó xuất hiện ở giai đoạn nào:

```text
HTTP request
    |
    v
Borrow connection from pool  -- chờ quá max-wait --> Pool timeout
    |
    v
Connect to Redis             -- quá connect-timeout --> Connect timeout
    |
    v
Send command / wait reply    -- quá read timeout --> Read/command timeout
    |
    v
Deserialize response         -- format khác --> SerializationException
```

Bốn lỗi trên có nguyên nhân và cách xử lý khác nhau. Chỉ tăng `max-active` không giải quyết một Redis server đang chậm; chỉ tăng `readTimeout` không giải quyết lỗi thiếu connection pool. Khi retry, cần kiểm tra tính idempotent của lệnh: `GET` và `SET` với giá trị xác định thường khác `INCR`/`LPUSH` về hậu quả nếu client gửi lại sau khi mất phản hồi.

### Ví dụ khi Redis thay đổi endpoint

Nếu Redis dùng Sentinel và master được failover sang replica, kết nối trực tiếp vào `old-primary:6379` có thể dẫn tới lỗi hoặc ghi vào node không còn primary. Factory cấu hình Sentinel giúp ứng dụng tìm primary thông qua Sentinel theo cơ chế driver. Với Cluster, client cần cập nhật topology và xử lý redirect. Đó là lý do phải chọn **đúng loại cấu hình server** chứ không chỉ thay danh sách hostname.

## 16. Vận hành và quan sát pool trong production

Những điểm nên quan sát để điều chỉnh `JedisConnectionFactory`:

1. **Độ trễ Redis**: thời gian round-trip và thời gian xử lý các command phổ biến, nhất là command có thể chặn hoặc tốn nhiều tài nguyên.
2. **Số lượng kết nối**: connection đang hoạt động/nhàn rỗi trong pool, `connected_clients`, giới hạn `maxclients` trên server.
3. **Tình trạng timeout**: phân loại pool exhaustion, network connect timeout và read/command timeout; nhìn cùng số lượng request đồng thời.
4. **Topology và failover**: endpoint đang được sử dụng, Sentinel master change hoặc Cluster redirect/node unavailable.
5. **Lỗi xác thực/TLS**: phân biệt credential hết hạn, ACL thay đổi, certificate hết hạn hoặc lỗi hostname verification.
6. **Dữ liệu và định dạng**: lỗi serializer, TTL không đúng, keyspace growth, key lớn hoặc hash/list bị phình to.

Tăng connection pool thường làm tăng mức song song của các Redis command, nhưng Redis vẫn có giới hạn về CPU, bộ nhớ, network và số client. Khi nhiều application instance cùng dùng Redis, capacity phải được tính **trên toàn bộ hệ thống**, không chỉ trên một JVM.

Cơ chế retry cũng cần được giới hạn và đo lường. Nếu Redis đang suy giảm, mọi request đồng loạt retry ngay có thể làm tình hình nặng hơn. Đối với những lệnh không idempotent hoặc có hiệu ứng phụ, việc mất phản hồi không đồng nghĩa server chưa thực thi; retry cần quyết định theo hợp đồng nghiệp vụ.

## 17. Những câu hỏi thường gặp

**Có nhất thiết phải định nghĩa `@Bean JedisConnectionFactory` mới dùng được Jedis không?**

Không. Với Spring Boot và dependency phù hợp, `spring.data.redis.client-type: jedis` cùng các thuộc tính cấu hình Redis cho phép Boot tạo factory. Cấu hình bean thủ công có ý nghĩa khi ứng dụng có yêu cầu kết nối đặc thù.

**Tại sao Spring Boot vẫn dùng Lettuce dù đã thêm `redis.clients:jedis`?**

Vì starter thường mang Lettuce và việc có hai client trên classpath không biểu thị rõ lựa chọn. Kiểm tra `spring.data.redis.client-type`, bean tự khai báo và điều kiện auto-configuration. Không cần sửa code nghiệp vụ chỉ để chuyển driver.

**`JedisConnectionFactory` có hỗ trợ Spring WebFlux không?**

Ứng dụng WebFlux vẫn có thể gọi Redis đồng bộ, nhưng đó là thao tác blocking và cần bố trí execution phù hợp để tránh chặn event-loop. Nếu muốn Redis reactive đúng nghĩa thông qua `ReactiveRedisTemplate`, sử dụng Lettuce cùng `ReactiveRedisConnectionFactory`.

**Có cần pool khi chỉ có một service ít request?**

Không có một mức pool bắt buộc cho mọi ứng dụng. Pool có lợi khi nhiều thao tác đồng thời và tái sử dụng connection. Quyết định kích thước nên dựa trên tải, connection life cycle, latency và giới hạn server; với Jedis, cách phổ biến là dùng pooling thay vì chia sẻ native connection không an toàn giữa các thread.

**`database: 3` có thể dùng với Sentinel không?**

Sentinel quản lý master/replica của Redis thông thường, khác Redis Cluster. Logical database vẫn có thể dùng nếu các Redis data node hỗ trợ và cấu hình phù hợp. Ngược lại, Redis Cluster chỉ hỗ trợ DB 0.

**Đổi từ Jedis sang Lettuce có làm mất dữ liệu Redis không?**

Việc thay driver không tự xóa Redis key. Tuy nhiên, cần giữ cùng endpoint, database, tên key, serializer và các đặc tính lệnh. Nếu đồng thời đổi serializer hoặc namespace, ứng dụng có thể không đọc được dữ liệu cũ dù dữ liệu vẫn tồn tại.

**Có cần `@Primary` khi chỉ có một `RedisConnectionFactory` không?**

Không. `@Primary` chủ yếu cần khi có nhiều bean cùng kiểu mà injection không nêu rõ bean nào được sử dụng. Với một factory do Boot tạo, framework tự wiring cho các template phù hợp.

**Nếu Redis Cluster không có DB 1, có thể tách dữ liệu bằng hai connection factory cùng Cluster không?**

Hai factory cùng trỏ một Cluster vẫn nhìn vào chung DB 0. Dùng quy ước prefix/namespace key và Redis ACL nếu cần hạn chế quyền truy cập theo key; nếu cần cách ly mạnh về tài nguyên hoặc vận hành, cân nhắc deployment Redis riêng.

## 18. Tổng kết lựa chọn cấu hình

| Bối cảnh | Hướng cấu hình `JedisConnectionFactory` |
|---|---|
| Spring Boot + Redis standalone thông thường | Thêm Jedis, chọn `client-type: jedis`, khai báo host/port/password/timeout trong YAML |
| Cần kiểm soát timeout, pooling, TLS bằng code | Tạo `RedisStandaloneConfiguration` và `JedisClientConfiguration`, truyền vào constructor factory |
| Redis Sentinel | Dùng `RedisSentinelConfiguration` hoặc `spring.data.redis.sentinel.*`; khai báo master name và sentinel nodes |
| Redis Cluster | Dùng `RedisClusterConfiguration` hoặc `spring.data.redis.cluster.*`; chỉ DB 0 và chú ý hash slot |
| Dùng `ReactiveRedisTemplate` | Chọn Lettuce và `ReactiveRedisConnectionFactory` cho đường reactive |
| Nhiều Redis connection factory | Phân định bean qua `@Qualifier`/`@Primary`; cấu hình template/cache với đúng factory |

`JedisConnectionFactory` là đầu mối tích hợp driver Jedis vào kiến trúc Spring Data Redis. Khi thiết lập nó, hãy tách rõ **server topology** (`RedisStandaloneConfiguration`, Sentinel hoặc Cluster), **hành vi client** (`JedisClientConfiguration`: timeout, pool, TLS), và **cách biểu diễn dữ liệu** (serializer của template/cache). Với Spring Boot, cấu hình tự động thường đơn giản và dễ quản lý; cấu hình Java thủ công nên dành cho những nhu cầu cụ thể. Nhận diện đúng ba ranh giới đó giúp ứng dụng kết nối ổn định, xử lý lỗi có căn cứ và mở rộng Redis mà không làm rối logic nghiệp vụ.
