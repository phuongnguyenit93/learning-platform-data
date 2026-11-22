# Điều chỉnh pool, số kết nối và mức đồng thời trong Spring Data Redis

Redis thường có độ trễ rất thấp, nhưng ứng dụng Spring Data Redis vẫn có thể bị chậm khi lưu lượng tăng: request đợi lấy connection từ pool, quá nhiều lệnh được gửi đồng thời, một vài thao tác chặn kết nối lâu, Redis server quá tải, hoặc nhiều ứng dụng cùng tạo ra hàng nghìn kết nối. Khi ấy, tăng `max-active` hay số worker thread không phải lúc nào cũng cải thiện throughput; đôi khi nó chỉ làm hàng đợi dài hơn và p99 xấu hơn.

Bài học này hướng dẫn cách **điều chỉnh pool, số kết nối và mức đồng thời** theo workload thực tế của Spring Data Redis. Trọng tâm là hiểu khác biệt giữa **Lettuce** và **Jedis**, sự khác nhau giữa **kết nối dùng chung (shared connection)** và **kết nối lấy từ pool**, cách tách những thao tác blocking/long-lived, xác định ngân sách kết nối cho nhiều instance, kiểm soát concurrency trong Spring MVC/WebFlux và đo đạc trước khi thay cấu hình.

Một nguyên tắc cần nhớ ngay:

> **Số kết nối không đồng nghĩa số request có thể xử lý, và kích thước connection pool không tự quyết định throughput Redis.** Phải xác định chỗ nghẽn nằm ở pool, Redis client, network, Redis server hay logic nghiệp vụ rồi mới chọn biện pháp.

## 1. Sơ đồ đường đi của một thao tác Redis

Một `GET` qua `StringRedisTemplate` nhìn đơn giản:

```java
String value = redis.opsForValue().get("cache:product:42");
```

Nhưng thời gian mà caller phải chờ có thể gồm nhiều đoạn:

```text
HTTP / scheduled job / message handler
          |
          v
Thread hoặc Reactor subscriber
          |
          v
Spring Data Redis template
          |
          +-- serialize key/value
          |
          v
RedisConnectionFactory
          |
          +-- shared native connection?
          |
          +-- borrow from pool?
          |
          +-- establish/reconnect?
          |
          v
Lettuce/Jedis client
          |
          +-- client command queue
          +-- socket / event loop / network
          |
          v
Redis server
          |
          +-- command execution
          +-- CPU/memory/I/O pressure
          |
          v
Response -> deserialize -> business logic
```

Có thể tách latency đo từ ứng dụng thành các thành phần khái niệm:

```text
T_app
  = T_wait_for_connection
  + T_client_queue_and_serialization
  + T_network
  + T_server_wait_and_execution
  + T_response_processing
```

Các thành phần có thể chồng lấp và không phải lúc nào framework cũng cung cấp từng metric riêng. Mục tiêu của mô hình là **tránh quy mọi latency cao cho “thiếu connection”**.

Ví dụ:

- `T_wait_for_connection` cao: pool có thể đang hết connection.
- `T_server_wait_and_execution` cao: Redis đang xử lý lệnh nặng, Lua, nhiều key, CPU cao.
- Network RTT cao: thêm connection không làm khoảng cách mạng biến mất.
- Java GC/serialization chậm: tăng Redis pool không giải quyết phía ứng dụng.
- Lệnh `BLPOP` hoặc `XREAD BLOCK` giữ connection lâu: cần tách loại connection hoặc thay chiến lược worker.

## 2. Những khái niệm không nên đánh đồng

| Khái niệm | Nghĩa | Điều nó không tự bảo đảm |
|---|---|---|
| TCP connection | Kết nối mạng tới Redis endpoint | Một connection chỉ thực hiện một request tại mọi thời điểm |
| Redis native connection | Connection do Lettuce/Jedis quản lý | Luôn có thể dùng an toàn từ mọi thread ở mọi client |
| `RedisConnection` | Abstraction connection của Spring Data Redis | Được phép chia sẻ cùng wrapper giữa nhiều thread |
| Connection pool | Tập connection được mượn/trả | Server sẽ xử lý nhanh hơn nếu pool lớn |
| Pool `max-active` | Trần số connection active của **pool đó** | Trần số connection của toàn ứng dụng, toàn cluster hay mọi pool |
| Pool `max-idle` | Giới hạn connection nhàn rỗi được giữ | Số connection đang dùng |
| Pool `min-idle` | Số idle mà pool cố gắng duy trì theo chính sách | Pool luôn có sẵn đúng số đó ngay khi startup |
| `max-wait` | Thời gian đợi mượn connection khi pool cạn | Timeout cho Redis command |
| Command timeout | Giới hạn chờ phản hồi lệnh theo Redis client | Lệnh chắc chắn chưa được server thực thi |
| Application concurrency | Số tác vụ xử lý đồng thời | Số connection tối thiểu phải bằng số tác vụ |
| Redis server throughput | Khả năng xử lý lệnh ở server | Tự tăng tuyến tính với số connection |

Đặc biệt, **pool ở phía ứng dụng khác với các client connections mà Redis server thống kê**. Nếu deployment có 20 pods, mỗi pod có nhiều Redis clients/pools, Redis nhìn thấy tổng các connection của nhiều nguồn, không chỉ giá trị `max-active` trong một file cấu hình.

## 3. Lettuce và Jedis: quyết định đầu tiên trước khi chỉnh pool

Spring Data Redis hỗ trợ các Redis clients như **Lettuce** và **Jedis**, với khả năng và cấu hình thay đổi theo phiên bản Spring Data Redis/Spring Boot.

### 3.1. Lettuce: native connection có thể multiplex

Lettuce dựa trên Netty và thường hỗ trợ sử dụng một **native connection thread-safe** cho nhiều lệnh thông thường đang diễn ra đồng thời. Client có thể đưa nhiều command in-flight qua một connection và ghép phản hồi với từng request.

Mô hình:

```text
Thread A -- GET k1 --+
Thread B -- GET k2 --+
Thread C -- SET k3 --+--> one shared Lettuce native connection
Thread D -- INCR k4 -+          |
                               v
                          Redis server
```

Điều đó **không** có nghĩa mọi command chạy song song bên trong Redis server; nó có nghĩa nhiều caller không cần mỗi người giữ một socket riêng chỉ để gửi lệnh thông thường.

Hệ quả:

- Một shared native connection có thể phục vụ nhiều request thông thường.
- Tăng connection pool cho mọi `GET` không nhất thiết mang lại hiệu quả.
- Nhiều connection hơn có thể hữu ích trong các workload đặc thù, nhưng phải đo.
- Blocking, transaction và subscription có những quy tắc connection khác với `GET`/`SET` thông thường.
- Không được đồng nhất **native Lettuce connection thread-safe** với việc mọi đối tượng `RedisConnection` cấp thấp của Spring đều thread-safe.

### 3.2. Jedis: quản lý connection theo cách khác

Jedis thường sử dụng kết nối được mượn để thực hiện thao tác; một `Jedis` connection object không nên được chia sẻ tùy tiện giữa các thread cùng lúc.

Với Jedis, connection pooling thường có ý nghĩa trực tiếp hơn để tái sử dụng socket cho những thao tác được gọi đồng thời. Nếu không có đủ connection, các caller có thể phải đợi pool. Nếu pool quá lớn, Redis có nhiều socket hơn mà chưa chắc CPU đủ xử lý.

### 3.3. Không copy pool config từ client này sang client khác

Một cấu hình `max-active=32` có thể giúp một workload Jedis nhưng gần như không thay đổi đường đi của phần lớn thao tác `GET` thông thường với Lettuce đang dùng shared connection.

Trước khi tuning, xác định:

1. Application dùng `LettuceConnectionFactory` hay `JedisConnectionFactory`?
2. `LettuceConnectionFactory` có đang `shareNativeConnection` không?
3. Có cấu hình pool thực sự và dependency cần thiết không?
4. Những thao tác nào thực sự lấy dedicated/pooled connection?
5. Có nhiều `RedisConnectionFactory` trong một application context không?
6. Có task Pub/Sub, stream polling, transaction hay blocking command giữ connection lâu không?

## 4. `LettuceConnectionFactory` và shared native connection

Trong cấu hình phổ biến, `LettuceConnectionFactory` có chế độ **chia sẻ native connection** cho các lệnh thông thường, không blocking và không transaction.

Ý tưởng:

```text
StringRedisTemplate
      |
      v
LettuceConnectionFactory
      |
      +--> shared native Lettuce connection
      |        |
      |        +-- GET
      |        +-- SET
      |        +-- HGET
      |        +-- INCR
      |
      +--> dedicated connection khi cần
               |
               +-- blocking operation
               +-- transaction/session
               +-- một số trường hợp đặc thù
```

Thông tin chi tiết về dedicated connection và pooling phải được đối chiếu với Spring Data Redis/Lettuce version đang dùng, nhưng ranh giới quan trọng là: **đừng mặc định mỗi lần `opsForValue().get()` đều borrow một connection từ pool**.

### 4.1. Vì sao pool có thể không ảnh hưởng tới `GET`?

Giả sử ứng dụng:

```java
redis.opsForValue().get("product:1");
redis.opsForValue().get("product:2");
redis.opsForValue().get("product:3");
```

và đang dùng Lettuce shared connection. Những thao tác thông thường có thể đi qua cùng một native connection. Nếu chỉnh:

```yaml
spring:
  data:
    redis:
      lettuce:
        pool:
          max-active: 64
```

thì không thể suy luận rằng lập tức có 64 connection phục vụ ba `GET`. Pool có thể chỉ được dùng cho các loại kết nối/operations cần dedicated connection hoặc theo cấu hình client factory.

**Tuning đúng phải xuất phát từ đường đi thực tế của command**, không phải từ tên property.

### 4.2. `shareNativeConnection=false` không phải lựa chọn mặc định để tăng tốc

Có thể cấu hình `LettuceConnectionFactory` không dùng shared native connection cho những thao tác thường ngày:

```java
factory.setShareNativeConnection(false);
```

Nhưng thay đổi đó có thể khiến nhiều lời gọi phải lấy/tạo các connection riêng. Nếu không có pool thích hợp, chi phí mở socket và xác thực có thể tăng. Nếu có pool, các request lại có thể nghẽn ở borrow queue.

Chỉ xem xét khi có bằng chứng rằng mô hình shared connection không phù hợp với workload, ví dụ nhu cầu cô lập một số thao tác hay vấn đề queueing cụ thể; sau đó phải benchmark lại.

### 4.3. Không tự giữ `RedisConnection` qua nhiều thread

Sai về mặt sử dụng abstraction:

```java
RedisConnection conn = connectionFactory.getConnection();

// Lưu conn toàn cục rồi cho nhiều thread thao tác trực tiếp?
```

Spring Data Redis thường kỳ vọng connection wrapper được quản lý qua `RedisTemplate` hoặc callback/session và không được tùy tiện chia sẻ giữa nhiều thread.

Dùng:

```java
StringRedisTemplate
```

hoặc:

```java
redis.execute((RedisCallback<String>) connection -> {
    // Làm việc trong phạm vi callback.
    return "...";
});
```

Framework quản lý lifecycle connection phù hợp. Đối tượng template thường được thiết kế để tái sử dụng dưới tải đồng thời khi cấu hình đúng.

## 5. Khi nào connection pool thực sự cần thiết?

Pooling thường hữu ích khi **connection không được chia sẻ** hoặc chi phí tạo connection mới đủ lớn so với vòng đời thao tác.

Các tình huống cần đánh giá:

| Workload | Vấn đề connection | Hướng cân nhắc |
|---|---|---|
| GET/SET ngắn với Lettuce shared connection | Shared connection có thể multiplex | Đo trước, pool không nhất thiết là nút điều chỉnh chính |
| Jedis với nhiều request song song | Cần mượn connection cho các thao tác | Pool có giới hạn, timeout mượn connection |
| Redis `BLPOP`, `BRPOP` | Blocking command giữ connection trong lúc đợi | Dedicated connections; sizing theo số consumer |
| `XREAD BLOCK`/stream polling | Polling có thể giữ connection lâu | Tách pool/factory hoặc ngân sách riêng |
| Transaction `MULTI/EXEC`/`WATCH` | Session cần connection phù hợp | Dedicated/session-safe connection |
| Redis Pub/Sub | Subscription connection sống lâu | Tách khỏi connection phục vụ request nếu cần |
| Native Lettuce/Jedis connection per request | Tạo socket liên tục tốn chi phí | Pool hoặc shared connection phù hợp |
| Cluster nhiều primary | Kết nối phân theo node/slot | Tính số node và driver topology |
| Sentinel failover | Kết nối cần được thay thế/định tuyến lại | Reconnect và discovery, không chỉ tăng pool |

Pool phù hợp là **công cụ tái sử dụng một tài nguyên hữu hạn**, không phải bộ tăng tốc độc lập.

## 6. Cấu hình Lettuce pool bằng Spring Boot

Với Spring Boot 3.x và cấu hình Redis thường gặp:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 2s
      lettuce:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 2
          max-wait: 300ms
```

Đây là **ví dụ để bắt đầu đo**, không phải thông số chuẩn cho mọi hệ thống. Giá trị thực phải dựa trên concurrency, mức sử dụng dedicated connections, Redis server capacity và ngân sách kết nối của cả deployment.

Dependency Gradle phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    // Khi dùng commons-pool-backed connection pooling:
    implementation 'org.apache.commons:commons-pool2'
}
```

`commons-pool2` cung cấp pool implementation được Spring Data Redis/Lettuce pooling sử dụng. Với Boot/BOM, nên để dependency management chọn phiên bản tương thích.

### 6.1. Ý nghĩa từng property

| Property | Ý nghĩa | Cần tránh |
|---|---|---|
| `client-type: lettuce` | Chọn Redis client theo Boot version hỗ trợ | Nghĩ rằng nó tự bật pooling |
| `connect-timeout` | Chờ thiết lập kết nối | Dùng làm thời gian chờ Redis command |
| `timeout` | Giới hạn chờ command theo cấu hình Boot/client | Coi timeout là bằng chứng command chưa chạy |
| `pool.enabled` | Yêu cầu dùng pool nếu Boot/version/dependency hỗ trợ | Giả định pool được dùng cho mọi GET của shared connection |
| `pool.max-active` | Trần active connections trong pool | Nhân máy móc với request threads |
| `pool.max-idle` | Số idle connections tối đa giữ lại | Đặt lớn gây giữ socket không cần |
| `pool.min-idle` | Mức idle pool cố gắng duy trì | Đặt ngang max-active cho mọi pod |
| `pool.max-wait` | Thời gian chờ mượn connection khi cạn | Để chờ vô hạn dù API có deadline ngắn |

Property names và default có thể khác giữa Spring Boot versions; kiểm tra configuration metadata của đúng stack đang dùng. Ví dụ trên phản ánh các tên property thường gặp trong Boot 3.x.

### 6.2. `max-active` là trần, không phải số connection lúc khởi động

Nếu `max-active=16` và `min-idle=2`, điều này **không nghĩa** application tạo luôn 16 socket và sử dụng cả 16. Pool có thể tạo connection theo nhu cầu, giữ idle theo policy và đóng idle thừa.

Khi quan sát Redis:

```redis
INFO clients
```

số `connected_clients` còn gồm kết nối của ứng dụng khác, Redis CLI, subscription, monitoring và các connection driver quản lý ngoài pool.

### 6.3. Khi `max-wait` hết hạn

Nếu mọi connection của pool đang active và có nhiều caller mới đến:

```text
Request 1...16 -> đang giữ toàn bộ 16 pooled connections
Request 17     -> đợi borrow
Request 18     -> đợi borrow
...
```

Với `max-wait=300ms`, một caller có thể nhận lỗi khi không mượn được connection trong thời gian đó. Lỗi này khác với một Redis command đã được gửi tới server nhưng chờ phản hồi quá lâu.

Nếu ứng dụng gọi `GET` bằng shared Lettuce connection thì ví dụ borrow queue có thể **không xuất hiện ở con đường GET đó**. Phải xác định đúng workload/connection acquisition khi diễn giải metric.

## 7. Tự cấu hình `LettucePoolingClientConfiguration`

Nếu không dùng Spring Boot auto-configuration hoặc muốn cấu hình connection factory tường minh, Spring Data Redis có API `LettucePoolingClientConfiguration`.

Ví dụ minh họa:

```java
package com.example.redis;

import java.time.Duration;

import io.lettuce.core.api.StatefulConnection;
import org.apache.commons.pool2.impl.GenericObjectPoolConfig;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettucePoolingClientConfiguration;

@Configuration(proxyBeanMethods = false)
public class RedisPoolConfiguration {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("localhost", 6379);

        GenericObjectPoolConfig<StatefulConnection<?, ?>> pool =
                new GenericObjectPoolConfig<>();

        pool.setMaxTotal(16);
        pool.setMaxIdle(8);
        pool.setMinIdle(2);
        pool.setMaxWait(Duration.ofMillis(300));
        pool.setBlockWhenExhausted(true);

        LettuceClientConfiguration client =
                LettucePoolingClientConfiguration.builder()
                    .poolConfig(pool)
                    .commandTimeout(Duration.ofSeconds(2))
                    .build();

        LettuceConnectionFactory factory =
                new LettuceConnectionFactory(server, client);

        // Chế độ shared connection của factory cần được
        // chọn có chủ đích theo workload.
        // Không đổi mặc định chỉ vì đã bật pool.
        return factory;
    }
}
```

Ví dụ sử dụng các API phổ biến của Spring Data Redis, Lettuce và Commons Pool 2; xác nhận chữ ký builder/generic theo phiên bản đang triển khai trước khi dùng. Khi tự khai báo factory, nhiều properties của Spring Boot **không tự áp dụng** cho bean đó nếu code không đọc chúng.

### 7.1. Không tự đặt `shareNativeConnection(false)` một cách máy móc

Có thể thêm:

```java
factory.setShareNativeConnection(false);
```

khi thật sự muốn các regular operations không dùng shared native connection. Nhưng khi đó phải đánh giá:

- Chi phí mượn/trả pool cho số lượng command rất lớn.
- Số connection active ở Redis.
- Pool wait time và exhausted errors.
- Throughput, p95/p99 trước/sau.
- Tác động với transaction, blocking command và reconnect.

Dùng pool không đồng nghĩa mọi application nên tắt shared connection. Một factory mặc định shared có thể hiệu quả hơn đáng kể cho nhiều cache GET ngắn.

### 7.2. `validateConnection` và chi phí kiểm tra

`LettuceConnectionFactory` có tùy chọn kiểm tra connection khi lấy connection. Việc chủ động validation có thể giúp phát hiện kết nối không hợp lệ trong một số tình huống, nhưng cũng thêm công việc, ví dụ `PING`/I/O, vào đường đi lấy connection tùy triển khai.

Không bật validation cho mọi operation mà không đo latency, đặc biệt khi phần lớn GET đang dùng shared connection và client có cơ chế reconnect.

### 7.3. Không nhân đôi connection factory ngoài ý muốn

Ví dụ một ứng dụng có:

```text
RedisConnectionFactory A -> StringRedisTemplate
RedisConnectionFactory B -> ReactiveRedisTemplate
RedisConnectionFactory C -> RedisMessageListenerContainer
```

Mỗi factory/client có thể duy trì kết nối, pool và tài nguyên riêng. Nếu mục tiêu chỉ là dùng một Redis deployment, cần xem factory nào có thể được chia sẻ hợp lý và factory nào cần tách vì workload, không tạo bean mới tùy tiện.

Khi có nhiều factory, phải cộng ngân sách connection ở mức **toàn ứng dụng**, không chỉ xem một pool.

## 8. Jedis pooling trong Spring Boot

Nếu ứng dụng chọn Jedis:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 2s
      jedis:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 2
          max-wait: 300ms
```

Dependency cần Jedis tương ứng và thường cần Commons Pool 2. Khi dùng Spring Boot starter Redis mặc định (thường dựa trên Lettuce), muốn chuyển sang Jedis cần điều chỉnh dependencies và client type nhất quán, tránh có cả hai client trên classpath mà không hiểu Boot sẽ chọn gì.

Một số khác biệt:

- Jedis connection object không phải thứ nên dùng đồng thời từ nhiều thread.
- Pool có thể trở thành điểm chờ rõ ràng khi mỗi thao tác borrow connection.
- Cấu hình pool phải đủ cho **thao tác đang giữ connection**, không chỉ số request HTTP.
- Connection bị hỏng sau failover phải được thay thế theo cơ chế client/pool.
- Một số API synchronous/reactive hoặc đặc tính topology có mức hỗ trợ khác nhau giữa driver/versions.

**Không có một con số `max-active` chung cho cả Lettuce và Jedis.** Cùng bài toán có thể cần chiến lược connection khác hẳn.

## 9. Công thức tư duy để ước lượng concurrency

Để có một điểm khởi đầu, có thể dùng một dạng của **Little's Law**:

\[
L \approx \lambda \times W
\]

trong đó:

- \(L\): số thao tác đang đồng thời chờ/được xử lý trong một hệ thống ổn định.
- \(\lambda\): throughput, ví dụ số Redis operations mỗi giây.
- \(W\): thời gian trung bình một operation tồn tại trong hệ thống, tính bằng giây.

Ví dụ một service phát **1.200 Redis operations/giây**, thời gian bình quân trên đường đi là **8 ms**:

\[
L \approx 1200 \times 0.008 = 9.6
\]

Có thể hình dung tại một thời điểm trung bình có khoảng **10 thao tác in-flight** trên đường đo đó.

Điều này **không chứng minh cần pool 10 connections**:

- Với Lettuce shared connection, nhiều thao tác có thể cùng in-flight trên một native connection.
- Với Jedis, connection occupancy còn gồm thời gian mượn connection và thao tác.
- Số trung bình không phản ánh burst và tail latency.
- Nếu mỗi HTTP request gọi Redis năm lần, phải tính **Redis operations**, không chỉ HTTP requests.
- Nếu operation đợi pool, \(W\) đã có thể bao gồm queueing; dùng số đó để mở pool theo vòng lặp dễ tạo sai lệch.
- Khi Redis server đã quá tải, tăng concurrency làm \(W\) tăng, không tăng throughput tương ứng.

Vì vậy, phép tính này dùng để **ước lượng workload và kiểm tra mức hợp lý**, rồi phải xác nhận bằng đo đạc.

## 10. Phân biệt số request, số lệnh Redis và số connection

Một ứng dụng có:

```text
300 HTTP requests/s
Mỗi request:
  GET user
  GET permissions
  GET product
  SET cache
  INCR metric
```

Lưu lượng Redis có thể lên tới:

```text
300 requests/s × 5 commands/request
= khoảng 1.500 Redis commands/s
```

Nhưng nếu các lệnh của mỗi request chạy tuần tự, một HTTP request không gửi cả năm lệnh cùng lúc.

Ngược lại, nếu code dùng `Mono.zip` hoặc `flatMap` để gửi nhiều command độc lập song song, số command in-flight có thể tăng đáng kể dù HTTP RPS không thay đổi.

### 10.1. Xác định độ chiếm dụng connection

Đối với một pool mà mỗi operation cần dedicated connection, một cách tư duy là:

```text
Cần đủ active connections cho số tác vụ giữ connection
trong thời gian cao điểm + biên an toàn có đo đạc.
```

Ví dụ:

```text
Số worker giữ BLPOP đồng thời:      8
Số Redis transactions đồng thời:    4
Số task khác dùng dedicated conn:  2
```

Nếu **cùng dùng một pool** thì có thể cần ngân sách ít nhất phù hợp với 14 connection đang giữ, trước khi tính burst và failover. Nhưng các operations này có thể thuộc factory/client khác nhau; không cộng gộp nếu thực tế chúng đã tách pool.

Không lấy “số thread của servlet container = 200” làm mặc định cho `max-active=200`.

## 11. Ngân sách connection khi có nhiều instance

Đây là nơi một cấu hình nhìn vô hại trở thành vấn đề production.

Giả sử:

```text
8 application pods
Mỗi pod:
    1 factory phục vụ GET/SET
    1 factory cho stream listener
    pool dedicated tối đa 24
    các shared/subscription connections khác
```

Trần connection lý thuyết không chỉ là `24` mà có thể liên quan tới:

```text
8 pods × 24 pooled connections = 192 pooled connections
```

Còn phải cộng:

- Shared native connections.
- Redis Pub/Sub subscriptions.
- Stream blocking consumers.
- Redis CLI/monitoring connections.
- Redis admin/exporter connections.
- Các service khác dùng cùng Redis.
- Connection tới replica hoặc các node khác khi dùng Cluster.
- Connection sinh ra trong rolling deployment, khi old/new pods cùng tồn tại.

**`max-active` là giới hạn cho một pool, không phải quota Redis của cả deployment.** Và pool chưa chắc tạo đủ kết nối đến trần, nên đây là ngân sách **worst-case**, không phải số `connected_clients` hiện hữu.

### 11.1. Công thức lập ngân sách thực tế

Có thể lập bảng:

| Nguồn | Số instance | Trần connection/instance | Tổng trần ước lượng |
|---|---:|---:|---:|
| API service A | 8 | 16 | 128 |
| Background worker B | 4 | 12 | 48 |
| Pub/Sub listeners | 8 | 1–n | Theo topology |
| Exporter/health/CLI | n | n | Dự phòng |
| Deployment surge | n | n | Dự phòng |
| Client khác | n | n | Dự phòng |

Đừng cộng con số ví dụ rồi coi là đúng cho toàn bộ Redis server. Cần xác định số connection tới **từng endpoint thực tế**, vì Cluster có nhiều Redis nodes, còn Sentinel có các endpoint giám sát riêng.

### 11.2. Mối liên hệ với `maxclients`

Redis giới hạn số client connection qua `maxclients` và cả giới hạn file descriptors của OS. Kiểm tra:

```redis
CONFIG GET maxclients
INFO clients
INFO stats
```

Các dấu hiệu:

- `connected_clients` gần mức khả dụng.
- `rejected_connections` tăng.
- Application gặp lỗi mở connection hoặc timeout.
- Redis server/host chạm giới hạn file descriptors.
- Trong lúc deployment, số connection tăng đột ngột.

Không nên chỉ tăng `maxclients` mà không kiểm tra memory/OS limits; mỗi client connection tiêu thụ tài nguyên và có thể có input/output buffers.

## 12. Redis Cluster: số kết nối không còn chỉ tới một server

Với Redis Cluster:

```text
Spring service
     |
     v
Cluster-aware client
     |
     +-- Primary A (slots ...)
     +-- Primary B (slots ...)
     +-- Primary C (slots ...)
     +-- replicas nếu read policy sử dụng
```

Client có thể duy trì kết nối tới nhiều node theo topology, read policy và workload. Do đó:

- Một app pod không nhất thiết chỉ có một TCP connection tổng cộng.
- Pool hoặc connection limit có thể tác động theo node/client configuration.
- Các node có workload không cân bằng sẽ có lượng connection/in-flight command khác nhau.
- Resharding có thể thay đổi nơi lệnh được gửi.
- Cluster topology refresh có thêm hoạt động quản lý kết nối.
- Failover/redirect có thể tạo kết nối mới trong thời gian recovery.

Khi lập ngân sách, xem `INFO clients` **trên từng primary/replica**, không chỉ hỏi một node rồi coi là số toàn cluster.

### 12.1. Hash slot và hot keys quan trọng hơn pool

Nếu mọi key dùng cùng hash tag:

```text
cache:{all}:product:1
cache:{all}:product:2
cache:{all}:product:3
```

chúng cùng slot, nên một primary có thể gánh nhiều traffic trong khi các primary khác rảnh.

Tăng pool của ứng dụng không tự chuyển key sang node khác. Cần đánh giá key schema, hot slot, phân phối dữ liệu và command mix trước.

### 12.2. Pipelining trên Cluster

Pipeline có thể giảm round trips nhưng cách định tuyến qua nhiều node và xử lý lỗi phụ thuộc driver/Spring Data Redis version. Không tự xem một pipeline trên nhiều slot là một thao tác nguyên tử hoặc một connection duy nhất.

Nếu bottleneck là round trip per command, **batching/pipelining phù hợp** có thể giúp hơn tăng kết nối; nhưng phải test routing, thứ tự kết quả, command timeout và retry.

## 13. Sentinel: reconnect không phải tăng pool

Với Redis Sentinel, client phải phát hiện primary mới khi failover:

```text
Primary cũ chết
   |
   v
Sentinel chọn replica làm primary mới
   |
   v
Client cập nhật endpoint và reconnect
   |
   v
Lệnh Redis tiếp tục
```

Nếu gặp timeout trong failover, tăng `max-active` lên gấp đôi có thể không thay đổi được thời gian Sentinel chuyển vai trò hoặc việc client phát hiện địa chỉ mới.

Cần kiểm tra:

- Client được cấu hình Sentinel-aware, không trỏ host primary cố định.
- Địa chỉ Sentinel trả về có reachable từ application.
- Command/connect timeout và topology refresh/reconnect behavior.
- Tình trạng pool connections cũ và tạo connection mới.
- Redis auth/TLS ở primary mới.
- Unknown outcome của các write gửi trong lúc kết nối mất.

Sau failover, không retry mù `INCR`, `LPUSH` hoặc những write không idempotent chỉ để che lỗi tạm thời.

## 14. Lệnh blocking chiếm connection theo thời gian chờ

Một lệnh bình thường:

```redis
GET cache:product:42
```

thường hoàn thành nhanh.

Trong khi:

```redis
BLPOP queue:jobs 0
```

có thể đợi **vô hạn** tới khi có phần tử. Một connection đang chạy blocking command không thích hợp để dùng như connection multiplex thông thường cho những command độc lập trên cùng luồng chờ.

Tương tự, Redis Streams:

```redis
XREADGROUP GROUP workers worker-1 BLOCK 5000 STREAMS stream:jobs >
```

có thể giữ connection đang chờ tới 5 giây hoặc đến khi có entry.

### 14.1. Vì sao pool bị cạn?

Giả sử pool có `max-active=8`, đồng thời có 8 workers dùng `BLPOP` vô hạn:

```text
Pool size: 8
Worker 1 -> BLPOP giữ connection 1
Worker 2 -> BLPOP giữ connection 2
...
Worker 8 -> BLPOP giữ connection 8

Request GET cần borrow dedicated connection:
    Không còn connection -> đợi max-wait -> lỗi
```

Với Lettuce shared connection, GET thông thường có thể vẫn dùng shared native connection riêng, nên mức độ ảnh hưởng phụ thuộc factory và connection path. Nhưng mọi thành phần cùng mượn **một pool dedicated** sẽ phải chia ngân sách đó.

Hướng thiết kế:

- Đếm số blocking consumers đồng thời.
- Đặt timeout `BLOCK` hữu hạn khi hợp lý.
- Tách factory/pool cho blocking consumers nếu workload cạnh tranh mạnh.
- Không dùng vô hạn consumer threads mà không có ngân sách connection/server.
- Theo dõi `blocked_clients` ở Redis và các pool active/waiting.
- Với Streams, thiết kế consumer groups, ACK/pending/reclaim độc lập với pool tuning.

### 14.2. Block timeout khác borrow timeout

Giả sử:

```text
Pool max-wait:          200 ms
XREAD BLOCK timeout:  5000 ms
Redis command timeout: 3000 ms
```

Nếu Redis command timeout nhỏ hơn thời gian `BLOCK` mà client mong đợi, ứng dụng có thể thấy timeout client khi command vẫn đang đợi hợp lệ trên server.

Cần đồng bộ các giới hạn:

- Thời gian chờ pool.
- Thời gian chờ Redis command.
- Thời gian `BLOCK` của BLPOP/XREAD.
- Deadline tổng của worker/request.
- Shutdown/cancellation behavior.

Không chọn các giá trị độc lập chỉ vì mỗi property có sẵn trong file YAML.

## 15. Pub/Sub và listener containers: kết nối sống lâu

`RedisMessageListenerContainer` thường quản lý subscription connection để nhận message qua channel hoặc pattern. Một connection subscribe có thể sống lâu và phục vụ nhiều listener của cùng container.

```text
RedisMessageListenerContainer
       |
       +-- subscription connection (long-lived)
       |
       +-- callback dispatch executor
                |
                +-- MessageListener A
                +-- MessageListener B
```

Hai loại tài nguyên cần tách:

1. **Kết nối tới Redis** để subscribe.
2. **Thread/executor** để dispatch và chạy handler Java.

Nếu handler chậm, tăng connection pool không nhất thiết giúp, vì bottleneck có thể ở callback executor hoặc database phía sau.

### 15.1. Subscription executor và listener task executor

Một cấu hình minh họa:

```java
@Bean
RedisMessageListenerContainer redisMessageListenerContainer(
        RedisConnectionFactory connectionFactory,
        MessageListener listener,
        @Qualifier("redisListenerExecutor") Executor listenerExecutor,
        @Qualifier("redisSubscriptionExecutor") Executor subscriptionExecutor
) {
    RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

    container.setConnectionFactory(connectionFactory);
    container.setTaskExecutor(listenerExecutor);
    container.setSubscriptionExecutor(subscriptionExecutor);

    container.addMessageListener(
        listener,
        new ChannelTopic("catalog.events")
    );

    return container;
}
```

Các beans executor được định nghĩa ở cấu hình khác của application. Không dùng cùng một executor chỉ có một worker cho cả công việc duy trì subscription lâu dài và callback nếu nó khiến callback không được thực thi.

Và dù thread executor nhiều hơn, Pub/Sub vẫn **không có durable ACK/replay**; message có thể mất khi subscriber offline. Tuning thread/pool không tạo khả năng giao hàng bền vững.

## 16. Số thread của Spring MVC và Redis pool

Trong ứng dụng Spring MVC/Tomcat:

```text
HTTP worker thread
     |
     v
Service
     |
     v
StringRedisTemplate GET
     |
     v
Thread chờ kết quả rồi tiếp tục
```

Nếu mỗi request dùng một phần thời gian chờ Redis, số HTTP threads và tổng latency request ảnh hưởng đến concurrency. Tuy nhiên, với Lettuce shared native connection, **không cần tự động đặt pool size bằng số Tomcat threads**.

Một số rủi ro:

- Quá nhiều HTTP threads có thể dồn traffic xuống Redis nhanh hơn server xử lý.
- Một endpoint gọi Redis 20 lần không tương đương endpoint chỉ gọi một lần.
- Nếu Redis timeout vài giây, nhiều request threads có thể bị giữ lâu, ảnh hưởng khả năng nhận request mới.
- Pool borrow wait có thể cộng với command timeout, làm request total time tăng.
- Tăng số request threads có thể chỉ tăng queueing và timeout ở downstream.

Khi điều chỉnh, đo cùng lúc **HTTP concurrency, Redis command concurrency và pool metrics** thay vì chỉ xem một property.

## 17. WebFlux và ReactiveRedisTemplate: giới hạn bằng Reactor

Ứng dụng Spring WebFlux dùng `ReactiveRedisTemplate` hoặc `ReactiveStringRedisTemplate` nhận `Mono`/`Flux` thay vì kết quả đồng bộ.

Ví dụ:

```java
Mono<String> value =
        reactiveRedis.opsForValue().get("cache:product:42");
```

Một API reactive không giữ một worker thread để chờ mỗi Redis command theo kiểu blocking truyền thống. Nhưng không có nghĩa ta có thể tạo **vô hạn** thao tác Redis song song.

Ví dụ không giới hạn theo ý muốn:

```java
return Flux.fromIterable(productIds)
        .flatMap(id ->
            reactiveRedis.opsForValue()
                    .get("cache:product:" + id)
        );
```

`flatMap` có concurrency mặc định theo Reactor version/operator, không phải một con số tối ưu cho Redis production. Với số lượng ID rất lớn, fan-out có thể tạo áp lực lên driver, network buffers và Redis server.

### 17.1. Giới hạn concurrency tường minh

```java
public Flux<String> cachedProducts(List<String> productIds) {
    int concurrency = 16;

    return Flux.fromIterable(productIds)
            .flatMap(
                id -> reactiveRedis.opsForValue()
                        .get("cache:product:" + id),
                concurrency
            );
}
```

Chọn `16` chỉ là ví dụ. Phải đo:

- Redis operations/sec.
- Tail latency.
- Netty event-loop/CPU.
- Timeout và retry.
- Số command đang chờ ở client.
- Redis server CPU và command latency.

Khi ứng dụng có 20 pods, concurrency 16 ở mỗi request **không có nghĩa** tổng in-flight commands toàn deployment chỉ là 16. Phải tính thêm số request đồng thời trên từng pod.

### 17.2. Khi cần thứ tự kết quả

`flatMap` có thể trả item không theo thứ tự đầu vào.

```java
return Flux.fromIterable(productIds)
        .concatMap(id ->
            reactiveRedis.opsForValue()
                .get("cache:product:" + id)
        );
```

`concatMap` xử lý tuần tự hơn, giúp bảo toàn thứ tự nhưng giảm concurrency. Có thể dùng `flatMapSequential` để chạy một số request đồng thời mà vẫn phát kết quả theo thứ tự đầu vào, đổi lại bộ nhớ buffer và latency.

Lưu ý: Redis key không có sẽ dẫn tới `Mono.empty()` trong nhiều API; cần wrapper chứa ID nếu muốn giữ một kết quả tương ứng từng input, kể cả cache miss.

### 17.3. Reactive backpressure không thay `maxmemory` hay Redis capacity

Ngay cả khi `Flux.take(10)` chỉ phát 10 item xuống subscriber, một command Redis như `SMEMBERS` có thể đã lấy một tập dữ liệu rất lớn. Backpressure ở Reactor **không tự làm Redis server chỉ đọc đúng 10 phần tử**.

Tránh lệnh không giới hạn dữ liệu; dùng range/scan/cursor phù hợp. Không tăng pool để giải quyết một lệnh Redis vốn trả quá nhiều dữ liệu.

## 18. Điều chỉnh concurrency cho batch và pipeline

Redis pipeline giảm overhead network round trip bằng cách gửi nhiều lệnh trước khi chờ kết quả, nhưng không tạo transaction nguyên tử.

Mô hình:

```text
Không pipeline:
  GET A -> wait
  GET B -> wait
  GET C -> wait

Có pipeline:
  GET A
  GET B
  GET C
  -> nhận các responses
```

Trong Spring Data Redis:

```java
List<Object> results = redis.executePipelined(
    (RedisCallback<Object>) connection -> {
        for (String key : keys) {
            connection.stringCommands().get(
                redis.getStringSerializer().serialize(key)
            );
        }
        return null;
    }
);
```

Ở đây `keys` là danh sách String được truyền vào method; callback trả `null` theo hợp đồng `executePipelined`.

### 18.1. Pipeline ảnh hưởng pool/concurrency thế nào?

- Một pipeline có thể gửi nhiều lệnh qua một hoặc một số connection tùy driver và topology.
- Giảm round trips có thể giúp throughput mà **không cần tăng connections**.
- Batch quá lớn có thể tăng memory/response buffering, tail latency và chi phí Redis server.
- Lệnh ghi bên trong pipeline vẫn có thể tạo kết quả một phần hoặc outcome không chắc chắn khi timeout.
- Trong Redis Cluster, routing pipeline qua nhiều slot/node có giới hạn và đặc điểm theo driver/version.
- Pipeline không thay thế tính nguyên tử của Lua/`MULTI/EXEC`.

Nên benchmark batch size theo các mức nhỏ → vừa → lớn, quan sát p95/p99 và memory. Đừng coi “gửi càng nhiều command trong một batch thì càng nhanh” là chân lý.

### 18.2. Dùng lệnh Redis native khi phù hợp

Một số trường hợp nhanh và đúng hơn nếu dùng lệnh native:

```java
redis.opsForValue().increment(counterKey);
```

thay vì:

```text
GET counter
parse + 1
SET counter
```

Lệnh `INCR` vừa tiết kiệm round trip, vừa tránh lost update của read-modify-write không nguyên tử.

Với nhiều key cùng slot hoặc standalone, `MGET` có thể hữu ích; nhưng khi chuyển sang Redis Cluster cần kiểm tra giới hạn same-slot và khả năng fan-out của client.

## 19. Vì sao tăng connections có thể làm hiệu năng tệ hơn?

Giả sử Redis server có khả năng bền vững khoảng **X commands/s** với workload hiện tại. Nếu app gửi quá X:

```text
Arrival rate > service capacity
          |
          v
Queue growth
          |
          v
Waiting + timeout
          |
          v
Retries (nếu có)
          |
          v
Arrival rate càng tăng
```

Tăng pool size có thể cho phép thêm command tới Redis, đẩy tài nguyên server tới giới hạn nhanh hơn. Khi không có backpressure, tail latency có thể tăng dù throughput thành công tăng rất ít.

Một số dấu hiệu:

- Pool active tăng nhưng completed operations/sec không tăng.
- Redis CPU đạt mức cao, command latency tăng.
- Client pending commands/queue tăng.
- p99 tăng sau khi nâng `max-active`.
- `rejected_connections` tăng vì nhiều pods cùng tạo socket.
- Memory của Redis tăng do client output buffers.
- DB downstream hoặc external service bị quá tải bởi handler chạy đồng thời.

Không đánh giá cấu hình bằng một chỉ số duy nhất như “số connection đang mở”.

## 20. Tạo các pool riêng để cô lập workload khi cần

Một Redis deployment có thể được dùng cho:

```text
1. GET/SET cache (latency-sensitive)
2. Background cache warmup (batch-heavy)
3. Stream workers với XREAD BLOCK
4. Pub/Sub subscriptions
5. Lua scripts / transactions
```

Không nhất thiết mọi workload nên dùng chung một connection factory hoặc pool. Nếu một nhóm task giữ dedicated connections rất lâu hoặc tạo burst lớn, có thể tách tài nguyên.

Mô hình:

```text
                     Spring application
                           |
               +-----------+-----------+
               |           |           |
             Cache       Stream       Pub/Sub
             template    worker       container
               |           |           |
          Factory A    Factory B    Factory C
           (shared)    (dedicated) (subscription)
               |           |           |
               +-----------+-----------+
                           |
                         Redis
```

Lợi ích tiềm năng:

- Stream blocking consumers không tranh pool borrow với cache requests.
- Có thể đặt timeout riêng cho cache và stream polling.
- Giới hạn concurrency/queue theo workload.
- Dễ đo số connection, error rate và latency riêng.

Đánh đổi:

- Nhiều connection factories có thể làm tổng số socket tăng.
- Cấu hình Redis host/auth/TLS cần đồng nhất.
- Khó quản lý hơn khi có nhiều beans.
- Trong Cluster, số connection quản lý có thể tăng theo node.
- Tách pool **không tạo ra nhiều CPU Redis server**; workload vẫn có thể cạnh tranh ở server.

Chỉ tách khi dữ liệu đo cho thấy cần cô lập hoặc khi semantics blocking/subscription bắt buộc.

## 21. Cấu hình timeout theo một ngân sách end-to-end

Một request HTTP có deadline 1 giây nhưng cấu hình:

```text
Pool max-wait:     2 giây
Redis timeout:     5 giây
DB timeout:        3 giây
```

thường là một cấu hình khó kiểm soát, vì các giới hạn từng tầng dài hơn đáng kể so với thời gian mà caller có thể chấp nhận.

Cần định nghĩa:

```text
HTTP request budget
    |
    +-- authentication / business logic
    +-- pool borrow budget
    +-- Redis command budget
    +-- downstream work
    +-- serialization / response
```

Ví dụ minh họa:

```text
HTTP SLA/deadline:         800 ms
Pool borrow budget:        100 ms
Redis command budget:      250 ms
Business + DB budget:      350 ms
Response/margin:           100 ms
```

Các con số chỉ là cách tư duy, không phải khuyến nghị mặc định. Trong một request có nhiều command tuần tự, tổng budget phải tính cả số bước và retry.

### 21.1. Timeout không khẳng định command chưa chạy

Với:

```redis
INCR metrics:charged
```

một timeout có thể xảy ra **sau khi Redis đã tăng** nhưng trước khi client nhận response. Nếu app retry mù, có thể tăng hai lần.

Pool tuning, retry policy và idempotency phải được thiết kế cùng nhau. Tăng số connection để “giảm timeout” không thay thế cơ chế xử lý outcome không chắc chắn.

### 21.2. Chờ pool vô hạn không phù hợp request có deadline

`max-wait` âm/vô hạn theo cấu hình pool có thể khiến request nằm chờ borrow rất lâu khi pool cạn. Trong ứng dụng có traffic và SLA rõ, nên đặt thời gian chờ có giới hạn, đo số lượt bị từ chối và có chính sách overload.

Nhưng một `max-wait` quá thấp cũng có thể tạo lỗi giả khi pool được dùng đúng nhưng burst ngắn; chọn bằng dữ liệu p95/p99 borrow wait và độ nhạy nghiệp vụ.

## 22. Retry có thể tạo "connection storm"

Khi Redis tạm chậm, một hệ thống có thể phản ứng:

```text
Redis chậm
  -> command timeout
  -> mọi caller retry ngay
  -> số command đồng thời tăng
  -> Redis càng chậm
  -> các pod tự scale
  -> số connection mới tăng
  -> lỗi lan rộng
```

Tình trạng này còn gọi là retry storm/connection storm.

Cách giảm:

- Retry có giới hạn và **jittered exponential backoff** khi loại lỗi phù hợp.
- Circuit breaker hoặc bulkhead cho workload không bắt buộc.
- Giới hạn concurrency ở caller.
- Không retry command không idempotent nếu không có operation ID/cơ chế chống trùng.
- Tránh scale pods quá nhanh khi Redis đang ở giới hạn connection/server.
- Quan sát pool borrow wait, connect error và Redis `rejected_connections`.
- Giảm load có kiểm soát nếu Redis chỉ là cache và nguồn chính có thể phục vụ.

**Không bật retry vô hạn trên mọi exception Spring Data Redis.** `WRONGTYPE`, `CROSSSLOT` hoặc script argument error là lỗi thiết kế/dữ liệu, retry không làm chúng biến mất.

## 23. Metrics cần theo dõi ở ứng dụng và Redis server

Một tuning cycle phải dựa trên hai phía.

### 23.1. Metric ở ứng dụng

| Metric | Mục tiêu |
|---|---|
| Redis command throughput | Số command đã gửi/hoàn thành theo loại |
| Redis command duration p50/p95/p99 | Latency client nhìn thấy |
| Pool active | Số dedicated connections đang được mượn |
| Pool idle | Số connections đang nhàn rỗi |
| Pool waiters | Số caller chờ borrow |
| Pool borrow wait duration | Thời gian đợi connection |
| Pool borrow failures/timeouts | Dấu hiệu thiếu connection hoặc saturation |
| Connect/reconnect attempts | Dấu hiệu network/topology không ổn định |
| Client command queue/pending requests | Phát hiện fan-out quá mức |
| Application request p95/p99 | Tác động người dùng thật |
| Retry count và retry delay | Phân biệt load gốc và load do retry |
| Event-loop blocking/GC pauses | Xác định bottleneck phía JVM |
| Worker/HTTP thread utilization | Tác động của synchronous Redis call |

Không phải mọi metric trên được Spring Boot tự xuất ra. Mức có sẵn phụ thuộc Lettuce/Jedis, Commons Pool, Micrometer, Actuator và cách instrument.

### 23.2. Metric Redis server

Redis CLI:

```redis
INFO clients
INFO stats
INFO commandstats
INFO memory
INFO cpu
INFO persistence

CONFIG GET maxclients
SLOWLOG GET 20
LATENCY LATEST
```

Một số chỉ số hữu ích:

| Chỉ số | Giải thích |
|---|---|
| `connected_clients` | Client connections đang mở |
| `blocked_clients` | Client đang đợi blocking command và các trạng thái tương ứng |
| `rejected_connections` | Kết nối bị từ chối theo giới hạn/tình trạng Redis |
| `instantaneous_ops_per_sec` | Tốc độ command tức thời ước lượng |
| `total_commands_processed` | Số command server đã xử lý |
| `cmdstat_get` / `cmdstat_set` | Thống kê theo loại lệnh, tùy phiên bản |
| `used_memory` và RSS | Áp lực bộ nhớ và memory overhead |
| CPU time | Xem server có bị giới hạn tài nguyên không |
| Persistence in progress/fork latency | Snapshot/AOF rewrite có gây đỉnh latency không |

### 23.3. SLOWLOG không đo toàn bộ latency

`SLOWLOG` nhìn vào thời gian thực thi lệnh ở Redis server theo ngữ nghĩa của Redis, không cộng toàn bộ thời gian chờ pool, network và serialization phía Java.

Ví dụ:

```text
Application GET p99: 500 ms
SLOWLOG: không có GET chậm
```

không đồng nghĩa Redis luôn bình thường. Có thể phần lớn thời gian nằm ở **pool borrow**, client queue, reconnect hoặc network.

Ngược lại, nếu `SLOWLOG` có lệnh nặng hoặc Lua chạy lâu, tăng pool không sửa server-side bottleneck.

## 24. Đo Commons Pool 2

Khi Spring Data Redis dùng pooling dựa trên Apache Commons Pool 2, có thể xem các thống kê của `GenericObjectPool` trong phạm vi quản lý mà ứng dụng/driver cung cấp.

Các khái niệm tương ứng:

```text
numActive
numIdle
numWaiters
mean/max borrow wait
borrowed count
created/destroyed count
```

Cách truy cập các metric cụ thể có thể qua JMX/MBeans, registry hoặc instrumentation của client, tùy Spring Data Redis/Lettuce/Jedis và cấu hình.

Đừng giả định có sẵn một Micrometer meter tên cố định `redis.pool.active` trên mọi project. Nếu tự viết exporter, nên đặt tên metric ổn định và xác nhận nó gắn với **đúng pool** đang được RedisTemplate sử dụng.

### 24.1. Phân biệt pool hết connection với server quá tải

| Dấu hiệu | Khả năng | Biện pháp điều tra |
|---|---|---|
| `active` sát max, `waiters` tăng, Redis CPU thấp | Pool có thể quá nhỏ hoặc connection bị giữ lâu | Trace borrow duration, blocking commands, leak |
| `active` thấp, Redis CPU cao, p99 cao | Server/command bottleneck | Commandstats, SLOWLOG, script, large keys |
| `connected_clients` rất cao, nhiều idle | Pool quá nhiều hoặc scale pods | Giảm idle/min-idle, xem factories |
| Lỗi connect tăng khi deployment | Connection storm, maxclients, auth/network | Check Redis/OS/client logs |
| Pool wait thấp nhưng HTTP chậm | Nút nghẽn ở DB/logic khác | Distributed tracing |
| `blocked_clients` cao | Nhiều blocking consumers | XREAD/BLPOP workers, pool isolation |
| Memory cao khi nhiều clients | Buffers/queues và overhead | CLIENT LIST, INFO memory |

Đây là bảng hướng điều tra, không phải chẩn đoán chắc chắn chỉ từ một metric.

## 25. Instrument thời gian thao tác Redis trong Spring

Một `Timer` của Micrometer có thể đo thời gian `StringRedisTemplate` nhìn từ ứng dụng:

```java
package com.example.redis;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;
    private final Timer getTimer;

    public ProductCacheReader(
            StringRedisTemplate redis,
            MeterRegistry registry
    ) {
        this.redis = redis;
        this.getTimer = Timer.builder("app.redis.cache.get")
                .description("Redis GET duration from application")
                .register(registry);
    }

    public String get(String productId) {
        String key = "cache:product:" + productId;

        return getTimer.record(
                () -> redis.opsForValue().get(key)
        );
    }
}
```

Metric này đo **tổng thời gian lời gọi client**, không tách được tất cả nguồn latency. Nếu Redis client đã có native command metrics, có thể kết hợp chúng với `Timer` của service để xác định chỗ mất thời gian.

Không đưa `productId` hoặc toàn bộ Redis key thành metric label; cardinality sẽ tăng rất lớn. Phân loại theo nhóm thao tác/cached resource thay vì từng object.

### 25.1. Thời gian borrow và thời gian command cần tách nếu có thể

Một `Timer` bọc `redis.opsForValue().get(...)` không chứng minh bao nhiêu ms đã dùng để chờ pool. Nếu hệ thống cần phân tích pool saturation, phải instrument đúng điểm borrow hoặc dùng metric từ pool.

Một lần đo tốt sẽ có timeline:

```text
HTTP request start
    |
    +-- pool borrow wait
    |
    +-- Redis command RTT
    |
    +-- Java decode + business logic
    |
HTTP response
```

Nếu có distributed tracing, tạo span theo operation type và layer; tránh ghi key/value nhạy cảm vào trace.

## 26. Tránh connection leak và session giữ quá lâu

Một kết nối được mượn từ pool nhưng không trả lại sẽ làm số active tăng dần cho tới khi pool cạn.

Khi sử dụng `RedisTemplate`, framework thường quản lý connection lifecycle. Nhưng khi tự gọi factory cấp thấp:

```java
RedisConnection conn = connectionFactory.getConnection();
```

cần đóng/trả connection đúng cách:

```java
try (RedisConnection conn = connectionFactory.getConnection()) {
    // Thao tác trong phạm vi connection.
}
```

Hợp đồng `close()`/release phụ thuộc implementation và Spring Data Redis context, nên ưu tiên callback `RedisTemplate.execute(...)` khi không cần quản lý connection thủ công.

### 26.1. Transaction và SessionCallback

Khi dùng `SessionCallback` để giữ session qua nhiều lệnh, connection có thể được gắn với các thao tác thuộc session; không nên đặt logic HTTP chậm hoặc chờ external API dài trong phạm vi giữ session.

Ví dụ có rủi ro:

```text
Borrow Redis connection
WATCH key
Call external service (chờ 5 giây)
MULTI/EXEC
Release connection
```

Trong 5 giây chờ external service, connection/session bị giữ dù không làm Redis work. Điều đó có thể giảm năng lực pool.

Nếu transaction có thể bị abort khi key thay đổi, thêm thời gian chờ giữa `WATCH` và `EXEC` còn làm tăng conflict. Tổ chức code sao cho thời gian giữ connection và critical section ngắn nhất phù hợp nghiệp vụ.

## 27. Một shared Lettuce connection cũng có giới hạn

Không nên đi tới kết luận ngược rằng **một Lettuce connection luôn là tối ưu**.

Một connection dùng chung có thể gặp:

- Client-side command queue/backpressure khi fan-out quá lớn.
- TCP/socket-level head-of-line effects trong những tình huống nhất định.
- Tranh chấp event-loop hoặc serialization khi payload lớn.
- Timeout khi Redis không thể xử lý kịp lượng lệnh.
- Connection bị ngắt dẫn tới nhiều pending commands bị ảnh hưởng.
- Workload có command đặc thù cần dedicated connection.

Vì vậy, trong những ứng dụng rất lớn hoặc có tải bất thường, nhiều connections hoặc nhiều factories có thể giúp cô lập tài nguyên, nhưng **kết quả cần được đo**.

Tối ưu thường theo thứ tự:

1. Dùng lệnh Redis native phù hợp, tránh command thừa.
2. Giảm payload lớn/serialization nặng.
3. Giới hạn fan-out và áp dụng batching hợp lý.
4. Đảm bảo không dùng blocking command trên đường shared connection.
5. Kiểm tra client queue, event-loop, Redis CPU và network.
6. Chỉ sau đó thử thêm connections/factories nếu bằng chứng cho thấy cần.

## 28. Cấu hình pool lớn và bài toán idle connections

Giả sử 20 pods, mỗi pod đặt:

```yaml
max-active: 100
max-idle: 100
min-idle: 100
```

Với một pool dedicated được khởi tạo/duy trì đầy đủ, hệ thống có thể cố giữ lượng idle connections lớn dù traffic thấp.

Hậu quả:

- Redis và OS cần quản lý nhiều sockets/file descriptors.
- TLS/auth handshake có thể tạo burst khi deploy.
- Redis `connected_clients` tăng.
- Pod khởi động nhiều đồng thời có thể tạo connection storm.
- Thay node/failover khiến số kết nối cần được tái lập tăng mạnh.
- Tài nguyên bị giữ mà không tăng throughput.

Đừng đặt `min-idle = max-active` chỉ để tránh một vài ms connection establishment nếu không đo được lợi ích rõ ràng. Có thể chọn min-idle nhỏ, max-idle vừa phải và warm-up có giới hạn.

### 28.1. Pool quá nhỏ cũng tạo queueing

Ngược lại, với Jedis hoặc dedicated pool:

```yaml
max-active: 2
max-wait: 50ms
```

nhiều request đỉnh có thể gặp borrow timeout dù Redis server vẫn rảnh. Khi có bằng chứng rõ về waiters/borrow latency cao, tăng pool từ 2 lên 4/8 có thể cải thiện.

Không thể đánh giá bằng số kết nối đơn lẻ. Cần so **throughput, p99, error rate và Redis CPU** trước/sau.

## 29. Tuning khi dùng Redis làm cache

Với cache read-heavy:

```text
GET: 90%
SET/DEL/EXPIRE: 10%
Giá trị thường nhỏ
```

Bước đầu:

- Xác nhận cache hit rate và số command mỗi request.
- Với Lettuce, ưu tiên shared native connection trước khi nghĩ tới pool lớn.
- Tránh gọi Redis nhiều lần cho cùng một request nếu có thể compose/batch.
- Đặt TTL hợp lý để tránh dữ liệu phình và cache stampede.
- Đo Redis CPU/network cùng RTT.
- Giới hạn số request fallback về database khi Redis lỗi.
- Dùng cache key/serializer nhỏ gọn phù hợp.

### 29.1. Cache miss storm không sửa bằng pool lớn

Giả sử Redis chậm hoặc toàn bộ cache hết hạn đồng loạt:

```text
Cache miss tăng
    |
    v
Nhiều request cùng gọi DB
    |
    v
DB chậm
    |
    v
Request giữ tài nguyên lâu
```

Tăng pool Redis có thể làm hàng loạt request vượt qua bước GET nhanh hơn nhưng không giải quyết DB overload.

Cần cơ chế như TTL jitter, request coalescing, background refresh hoặc key-level stampede protection khi thích hợp.

## 30. Tuning cho counter và lệnh ghi cao

Workload counter:

```java
Long current =
        redis.opsForValue().increment("metrics:article:42");
```

Nếu hàng nghìn request cùng tăng một key:

- Lệnh `INCR` nguyên tử, nhưng một hot key vẫn tạo tải trên Redis server.
- Tăng số connections không biến một key thành nhiều shard.
- Nếu cần throughput cao hơn, có thể xem batching, sharding counter theo partition rồi tổng hợp theo semantics chấp nhận được.
- Nếu là số dư/tiền hoặc bất biến nghiệp vụ, không tùy tiện shard mà mất atomicity.

Một mẫu sai:

```text
GET counter
parse current
SET counter = current + 1
```

dù dùng nhiều threads/connections, mẫu đó vẫn có lost update. Tuning pool không sửa race condition của thuật toán.

## 31. Tuning với Redis Streams và consumer group

Với một stream consumer group:

```text
XREADGROUP BLOCK
   |
   v
process message
   |
   v
XACK
```

Số consumer/concurrency ảnh hưởng:

- Số blocking connections.
- Số message xử lý đồng thời.
- Pending Entries List (PEL).
- Thứ tự side effect.
- Database/API downstream.
- Số bản ghi được ACK.
- Tần suất claim/retry khi consumer chết.

### 31.1. Đừng tăng số consumer theo số CPU máy ứng dụng một cách máy móc

Nếu handler gọi database chậm, tăng số Redis stream consumer có thể chỉ làm DB quá tải và pending count tăng.

Đo riêng:

```text
Redis read throughput
Handler processing duration
ACK throughput
Pending count / idle time
Retry/claim count
```

Nếu read nhanh nhưng handler chậm, bottleneck không ở Redis connection pool mà ở business handler. Có thể cần giới hạn handler concurrency hoặc tăng năng lực downstream.

### 31.2. Consumer identity và pending recovery

Pool size không giải quyết việc consumer chết sau khi nhận message nhưng trước `XACK`. Redis Streams cần chính sách xử lý pending (`XPENDING`, `XAUTOCLAIM`/`XCLAIM` theo version) và idempotency.

Khi scale consumer instances, đảm bảo consumer name/ownership rõ ràng và không trộn việc nhiều worker xử lý cùng message với vấn đề thiếu connection.

## 32. Tuning khi dùng Redis Pub/Sub

Pub/Sub thường dùng subscription connection sống lâu và listener executor.

Thay vì tăng connections cho mỗi message, cần xem:

- Container có nhận message đủ nhanh?
- Dispatch queue có backlog?
- Listener có logic chặn thread lâu?
- Có đăng ký nhiều channel/pattern chồng lấp?
- Message payload quá lớn?
- Client bị reconnect liên tục?
- Có event bị mất khi subscriber offline?
- Các service cần broadcast hay work-queue semantics?

Nếu listener `onMessage` mất 2 giây vì gọi external API, tăng `max-active` không trực tiếp giảm 2 giây ấy.

Và nếu nghiệp vụ cần không mất message, chuyển sang Redis Streams hoặc broker phù hợp thay vì dùng Pub/Sub với pool rất lớn.

## 33. Load testing có kiểm soát để chọn kích thước pool

Không nên chọn cấu hình chỉ từ cảm giác “production nhiều traffic”. Một quy trình benchmark rõ ràng:

### Giai đoạn 1 — Ghi nhận cấu hình hiện tại

```text
Redis version / topology
Spring Boot / Spring Data Redis
Lettuce hay Jedis
Shared connection? Pool enabled?
max-active / max-idle / min-idle / max-wait
connect timeout / command timeout
Số app pods và threads
Workload GET/SET/HGET/INCR/XREAD...
```

### Giai đoạn 2 — Đặt workload gần thực tế

Ví dụ:

```text
70% cache reads
20% cache writes
10% counters/scripts
Value size distribution giống production
TTL và miss rate giống production
Một số batch requests
```

Không dùng toàn lệnh `PING` để chọn pool cho hệ thống có Lua script và payload JSON hàng chục KB.

### Giai đoạn 3 — Warm-up và baseline

Cho ứng dụng, JVM/GC, connection factory và Redis ổn định. Đo:

- Throughput thành công.
- p50/p95/p99 request latency.
- Redis command duration.
- CPU/memory/network.
- Pool active/idle/waiters.
- Timeout/error rate.

### Giai đoạn 4 — Thay một biến mỗi lần

Ví dụ với dedicated/Jedis pool:

```text
Run A: max-active = 4
Run B: max-active = 8
Run C: max-active = 16
Run D: max-active = 32
```

Giữ workload, topology, key distribution và timeout giống nhau. Không tăng đồng thời số pods, pool size và batch size rồi khó biết yếu tố nào tạo thay đổi.

Với Lettuce shared connection, một thí nghiệm quan trọng khác là **giữ shared connection và thay giới hạn workload concurrency**; thay `max-active` một mình có thể không có tác động đáng kể tới các GET/SET thông thường.

### Giai đoạn 5 — Quan sát saturation

Một thay đổi là có ích khi:

- Throughput thành công tăng hoặc p99 giảm trong cùng workload.
- Borrow wait giảm nếu trước đó pool thực sự thiếu.
- Redis CPU/latency không bị đẩy vào saturation.
- Memory/socket overhead nằm trong ngân sách.
- Không xuất hiện nhiều timeout/retry/connection errors hơn.

### Giai đoạn 6 — Thử peak và failure

Sau khi chọn cấu hình ở tải ổn định, thử:

- Burst traffic.
- Redis chậm ngắn hạn.
- Connection reconnect.
- Rolling deployment nhiều pod cùng lúc.
- Sentinel/Cluster failover nếu production dùng.
- Blocking consumers tăng.
- Redis `maxclients` gần ngưỡng trong lab có kiểm soát.

Không chỉ báo một con số throughput cao nhất rồi bỏ qua khả năng phục hồi.

## 34. Ví dụ bảng đọc kết quả benchmark

Giả sử suite test trên staging cho ra dữ liệu **minh họa**:

| Dedicated pool max-active | Throughput thành công/s | p99 (ms) | Pool wait p95 (ms) | Redis CPU |
|---:|---:|---:|---:|---:|
| 4 | 1.100 | 85 | 28 | 38% |
| 8 | 1.800 | 45 | 8 | 54% |
| 16 | 1.950 | 47 | 1 | 78% |
| 32 | 1.960 | 120 | 0 | 98% |

Đây **không phải** số đo đã chạy hay khuyến nghị pool size. Nó minh họa tình huống:

- 4 connections thực sự thiếu cho workload dedicated.
- Tăng lên 8 mang lại cải thiện.
- Tăng 8 lên 16 mang lại lợi ích nhỏ hơn.
- Tăng 32 khiến Redis gần saturation và p99 xấu đi dù pool wait bằng 0.

Kết luận đúng từ dữ liệu ví dụ là **cần chọn cấu hình theo điểm cân bằng giữa throughput, latency và headroom**, không theo `max-active` lớn nhất.

Nếu ứng dụng đang dùng Lettuce shared connection, phải đo con đường command thực tế trước khi áp bảng này.

## 35. Nhìn từ Redis CLI: kiểm tra client connections

Một số command trong lab/staging:

```redis
INFO clients
CLIENT LIST
CONFIG GET maxclients
INFO stats
INFO commandstats
```

### 35.1. `CLIENT LIST`

`CLIENT LIST` có thể cho thông tin về địa chỉ client, tuổi kết nối, trạng thái, loại lệnh và các thông số buffer tùy Redis version. Đây là công cụ điều tra:

- Bao nhiêu clients xuất phát từ một application instance?
- Có nhiều idle connections không?
- Có blocking clients nào không?
- Có client output buffer tăng bất thường?
- Có kết nối bị giữ rất lâu bởi workload không mong muốn?

Không log/publish toàn bộ `CLIENT LIST` lên hệ thống công khai nếu nó chứa IP và metadata nhạy cảm.

### 35.2. `connected_clients` không phải số tác vụ đang chạy

Một Lettuce shared connection có thể mang nhiều in-flight commands trong khi `connected_clients` tăng rất ít. Ngược lại, hàng trăm pooled idle connections vẫn làm `connected_clients` cao dù Redis ops/s thấp.

Cần kết hợp **connection count + command throughput + pool activity + latency**.

### 35.3. `blocked_clients` không đồng nghĩa pool borrow waiters

Redis server `blocked_clients` là các client đang chờ blocking commands hoặc trạng thái blocking server theo semantics Redis. Pool `numWaiters` là số caller Java đang chờ **borrow connection**, có thể chưa hề gửi command tới Redis.

Hai số khác nhau và phản ánh các điểm nghẽn khác nhau.

## 36. Những hiểu lầm thường gặp

**“Pool 100 connections nhanh gấp 10 lần pool 10.”** Không có tỷ lệ chung. Redis CPU, network và command latency có thể là giới hạn.

**“Lettuce phải có một connection cho mỗi request HTTP.”** Không đúng với mô hình shared native connection cho thao tác thông thường.

**“Bật Lettuce pool thì mọi GET lập tức dùng pooled connection.”** Không thể suy luận vậy khi factory đang shared native connection.

**“`shareNativeConnection(false)` luôn tăng concurrency.”** Có thể tăng connection acquisition overhead và gây pool contention.

**“Số HTTP threads quyết định pool size.”** Không. Phải tính Redis command mix, concurrency và driver semantics.

**“Một TCP connection chỉ có một Redis command đang chờ.”** Không phải giả định đúng với mọi Redis client, nhất là Lettuce multiplexing.

**“`max-active` là số kết nối Redis toàn cluster.”** Sai. Nó là giới hạn một pool; còn nodes, factories và pods.

**“`max-wait` là command timeout.”** Sai. Borrow connection và chờ phản hồi là hai pha khác nhau.

**“`BLPOP 0` giống `GET` vì đều là một lệnh.”** Sai. Nó có thể chiếm dedicated connection rất lâu.

**“Dùng một executor 100 threads cho Pub/Sub sẽ tạo 100 subscription connections.”** Không nhất thiết. Subscription connections và callback executor là tài nguyên riêng.

**“Reactors `flatMap` tự giới hạn số Redis operations theo `max-active`.”** Không nên suy luận như vậy, đặc biệt với Lettuce shared connection.

**“Tăng connections giải quyết được hot key.”** Không. Hot key và Lua nặng là bottleneck phía server/data model.

**“Pipeline tương đương transaction.”** Không. Nó tối ưu gửi lệnh, không có all-or-nothing.

**“SLOWLOG không có command chậm nghĩa là pool bình thường.”** Không. Borrow wait không nằm trong Redis command execution time.

**“`connected_clients` thấp nghĩa là không có concurrency cao.”** Không. Multiplexing có thể có nhiều commands trên một connection.

**“Timeout nghĩa là Redis chắc chắn chưa chạy lệnh.”** Không. Retry không idempotent có thể tạo duplicate.

**“Scale application pods giúp Redis tăng capacity tương ứng.”** Không. Có thể gây thêm connections và requests vào cùng Redis server.

**“Redis Cluster có ba primary thì pool size phải nhân 3 một cách đơn giản.”** Không chính xác. Driver quản lý connection theo node/slot; cần quan sát actual connections và budget per node.

**“`min-idle=max-active` luôn tốt cho latency.”** Có thể gây nhiều idle sockets và connection storm trong rolling deployment.

**“Mọi Redis workload nên dùng chung một pool.”** Không phải lúc nào cũng phù hợp, đặc biệt khi có blocking consumers.

## 37. Checklist vận hành khi điều chỉnh pool và concurrency

### 37.1. Xác định kiến trúc

- [ ] Đã biết client là Lettuce hay Jedis và version tương ứng.
- [ ] Đã biết factory dùng shared connection hay dedicated connections.
- [ ] Đã biết những thao tác nào thực sự borrow pool.
- [ ] Đã kiểm kê số `RedisConnectionFactory`/templates trong application.
- [ ] Đã thống kê các blocking/persistent connections (Streams, Pub/Sub, transaction).
- [ ] Đã tính số pods/instances và rolling deployment surge.

### 37.2. Chọn cấu hình có cơ sở

- [ ] Pool `max-active` được chọn từ concurrency và borrow wait thực tế.
- [ ] `max-idle`/`min-idle` không giữ socket vô ích.
- [ ] `max-wait` và command timeout phù hợp request deadline.
- [ ] Có giới hạn concurrency ở Reactor/worker, không chỉ pool size.
- [ ] Các task blocking không làm nghẽn workload latency-sensitive.
- [ ] Không tự tắt shared Lettuce connection khi chưa đo.

### 37.3. Quan sát và benchmark

- [ ] Có p50/p95/p99 Redis và application latency.
- [ ] Có pool active/idle/waiters và borrow wait khi pool được sử dụng.
- [ ] Có Redis `connected_clients`, `blocked_clients`, `rejected_connections`.
- [ ] Có CPU, memory, network, commandstats và SLOWLOG/latency monitoring.
- [ ] Đã test workload gần production, gồm cả payload và cache miss.
- [ ] Đã thử burst, failure/reconnect và nhiều pods cùng startup.
- [ ] Đã so trước/sau bằng cùng điều kiện đo.

### 37.4. Đảm bảo tính đúng đắn

- [ ] Không retry mù lệnh ghi không idempotent khi timeout.
- [ ] Không thay transaction bằng pipeline để tăng throughput.
- [ ] Không chia một `RedisConnection` wrapper thủ công cho nhiều threads.
- [ ] Không tạo connection leak qua code cấp thấp.
- [ ] Redis Cluster routing và Sentinel failover được test theo topology thực.
- [ ] Không tăng concurrency tới mức quá tải DB hoặc downstream.
- [ ] Có rollback plan nếu thay pool khiến p99 hoặc error rate xấu đi.

## 38. Quy trình lựa chọn tối ưu theo loại ứng dụng

### 38.1. Ứng dụng cache dùng Lettuce

1. Bắt đầu với mô hình shared native connection phù hợp mặc định.
2. Đo latency GET/SET và throughput thực.
3. Xác định có blocking/transaction tasks hay không.
4. Nếu chủ yếu GET/SET, ưu tiên tối ưu số command, payload, fan-out và Redis server trước.
5. Chỉ thay pooling/sharing khi có bằng chứng từ metric/benchmark.
6. Đo lại dưới traffic peak và khi reconnect.

### 38.2. Ứng dụng Jedis synchronous

1. Ước lượng số callers giữ connection đồng thời.
2. Chọn pool có giới hạn và borrow timeout rõ.
3. Đo active/waiters và percentiles.
4. Tăng max-active từng bước nếu borrow wait cao trong khi Redis còn headroom.
5. Giảm min-idle/max-idle nếu giữ nhiều socket không cần.
6. Đảm bảo connection được trả đúng lúc và không giữ qua I/O ngoài Redis.

### 38.3. Ứng dụng WebFlux với reactive Redis

1. Giữ pipeline không blocking end-to-end.
2. Không gọi `.block()` trong event-loop.
3. Giới hạn `flatMap`/request fan-out theo năng lực Redis.
4. Cân nhắc `concatMap`/`flatMapSequential` khi cần thứ tự.
5. Đo pending commands, event-loop pressure và Redis latency.
6. Không dựa vào pool như cơ chế backpressure duy nhất.

### 38.4. Ứng dụng có Redis Streams/PubSub

1. Đếm blocking consumers và subscription connections.
2. Tách ngân sách connection/executor khỏi cache requests nếu cần.
3. Đồng bộ `BLOCK` timeout và command timeout.
4. Đo throughput handler và pending/ACK, không chỉ tốc độ đọc.
5. Dùng idempotency/reclaim cho Streams; Pub/Sub không có durable replay.
6. Tránh tăng consumer concurrency vượt năng lực xử lý downstream.

## 39. Kết luận

Điều chỉnh pool, số kết nối và mức đồng thời trong Spring Data Redis là bài toán **quản lý tài nguyên end-to-end**, không phải chỉ sửa `max-active` trong YAML.

Những nguyên tắc quan trọng:

1. **Hiểu Redis client trước:** Lettuce thường có shared native connection có thể multiplex lệnh thông thường; Jedis có chiến lược quản lý connection khác và thường dựa nhiều hơn vào pooling.
2. **Phân biệt shared và dedicated:** blocking commands, transactions và subscriptions có thời gian giữ connection khác GET/SET.
3. **Tính ngân sách toàn deployment:** nhiều pods, factories, pool, Redis nodes và rolling deployment cùng góp vào `connected_clients`.
4. **Giới hạn concurrency ở nguồn:** thread pool, worker count và Reactor `flatMap` có thể tạo nhiều lệnh hơn khả năng Redis xử lý.
5. **Dùng pipeline/batch đúng lúc:** giảm round trips mà không nhầm với transaction hoặc bỏ qua giới hạn Cluster.
6. **Chọn timeout có chủ đích:** pool borrow wait, command timeout và request deadline là ba lớp khác nhau.
7. **Đo đúng tầng:** kết hợp pool active/waiters, Redis command metrics, `INFO clients`, CPU và p95/p99 application latency.
8. **Không đánh đổi tính đúng đắn:** timeout có outcome không chắc chắn, retry lệnh ghi cần idempotency; nhiều connection hơn không sửa race condition.
9. **Benchmark trước khi mở rộng:** chọn mức concurrency/pool nhỏ nhất đáp ứng throughput, latency và headroom ở tải thực, thay vì chọn số connection lớn nhất có thể.

Một cấu hình Redis tốt thường không phải cấu hình có nhiều connection nhất, mà là cấu hình **đủ connection cho các hoạt động thật sự cần dedicated resources**, cho phép thao tác thông thường đi qua client hiệu quả, giới hạn tải khi Redis chậm và duy trì p95/p99 ổn định ngay cả khi traffic tăng hoặc topology thay đổi.
