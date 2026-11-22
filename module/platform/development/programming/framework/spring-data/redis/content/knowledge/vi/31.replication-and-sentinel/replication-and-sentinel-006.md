# Chính sách đọc từ primary hoặc replica của trình điều khiển

## 1. Vì sao kết nối được Redis không đồng nghĩa đọc đúng phiên bản dữ liệu?

Giả sử hệ thống Spring Boot lưu phiên đăng nhập, cấu hình sản phẩm và kết quả cache trong Redis. Để tăng khả năng sẵn sàng, Redis được triển khai với **một primary** và **hai replica**, còn **Sentinel** giám sát và thực hiện chuyển đổi vai trò khi primary gặp sự cố.

```text
                        Spring Boot
                            |
                       Redis Client
                            |
                     Sentinel nodes
                   (khám phá primary)
                            |
                            v
                   +----------------+
          GHI ---> | Primary P      | <--- ĐỌC mặc định
                   +----------------+
                     |            |
          Replication|            |Replication
                     v            v
                +----------+  +----------+
                | Replica A|  | Replica B|
                +----------+  +----------+
                      ^             ^
                      |             |
                Có thể ĐỌC     Có thể ĐỌC
                 qua driver     qua driver
```

**Primary** nhận các lệnh ghi và là nguồn để replica đồng bộ dữ liệu. **Replica** sao chép dữ liệu từ primary, thường phục vụ các truy vấn đọc. Redis replication thông thường là **bất đồng bộ**: tại một thời điểm, replica có thể chưa nhận được thay đổi mới nhất của primary.

Chính vì vậy, cùng một đoạn code:

```java
redisTemplate.opsForValue().get("product:42:price");
```

có thể có kết quả khác nhau tùy **node mà Redis client chọn để đọc**.

Trình điều khiển Redis như **Lettuce** có chính sách đọc (*read routing policy*) để quyết định lệnh đọc sẽ được gửi đến primary hay replica. Trong Spring Data Redis, cấu hình này thường được truyền qua `LettuceClientConfiguration`.

Điểm quan trọng cần hiểu từ đầu:

> **Sentinel giúp phát hiện primary và hỗ trợ failover; chính sách `ReadFrom` của Lettuce quyết định đường đọc. Hai cơ chế liên quan nhưng không thay thế nhau.**

Bài học tập trung vào cách hoạt động của các chính sách đọc, lựa chọn chúng theo yêu cầu nhất quán và cấu hình trong ứng dụng Spring Data Redis sử dụng Sentinel.

## 2. Phân biệt Replication, Sentinel và ReadFrom

### 2.1. Replication làm gì?

Redis replication sao chép các thao tác thay đổi dữ liệu từ primary tới replica. Replica duy trì bản sao để hỗ trợ khả năng phục hồi và có thể chia tải đọc.

Một chuỗi thao tác điển hình:

```text
t0: Spring Boot -> SET account:7:status "ACTIVE" -> Primary
t1: Primary trả OK cho ứng dụng
t2: Primary truyền thay đổi qua replication stream
t3: Replica A nhận và áp dụng thay đổi
t4: Replica B nhận và áp dụng thay đổi
```

Không có bảo đảm mặc định rằng `t2`, `t3` và `t4` đã hoàn thành **trước** khi client nhận phản hồi ghi ở `t1`.

Nếu ứng dụng ghi xong rồi đọc ngay từ replica, replica có thể vẫn thấy **giá trị cũ** hoặc chưa có khóa.

### 2.2. Sentinel làm gì?

Redis Sentinel có các trách nhiệm chính:

- Giám sát primary và các replica của một nhóm Redis.
- Phát hiện primary có vấn đề.
- Phối hợp bầu chọn và failover theo cấu hình.
- Thông báo hoặc cho phép client khám phá địa chỉ primary hiện tại.
- Cung cấp thông tin về các replica đang được theo dõi.

Sentinel **không phải** node lưu mọi dữ liệu ứng dụng và **không phải** cổng proxy nhận tất cả lệnh `GET`/`SET` rồi chuyển tiếp. Redis client thường hỏi Sentinel về topology, sau đó kết nối trực tiếp với những Redis data nodes thích hợp.

```text
Spring Boot
    |
    | Hỏi Sentinel: primary của "mymaster" là ai?
    v
Sentinel
    |
    | Trả địa chỉ primary / thông tin topology
    v
Spring Boot ---- SET ----> Primary
      |
      +-------- GET ----> Primary hoặc Replica
                          (theo chính sách client)
```

### 2.3. ReadFrom làm gì?

Lettuce cung cấp khái niệm `ReadFrom` để lựa chọn nơi gửi các **lệnh đọc thích hợp** trong topology primary–replica.

Ví dụ:

```java
ReadFrom.REPLICA_PREFERRED
```

biểu thị mong muốn **ưu tiên đọc từ replica**, nhưng có thể chuyển sang primary khi không có replica thích hợp theo chính sách lựa chọn của client.

Bản thân `ReadFrom`:

- Không tạo replica mới.
- Không thay đổi cơ chế replication bất đồng bộ của Redis.
- Không bảo đảm dữ liệu replica đã theo kịp primary.
- Không tự giúp một transaction SQL và Redis có tính nhất quán mạnh.
- Không làm các lệnh ghi hợp lệ được chạy trên replica chỉ vì đặt chính sách đọc.
- Không bảo đảm ứng dụng không bị gián đoạn trong mọi thời điểm failover.

## 3. Các chính sách đọc cần biết

Tên hằng có thể thay đổi hoặc có alias/deprecation giữa các phiên bản Lettuce. Trong những phiên bản hiện đại, tài liệu thường dùng khái niệm **upstream** để chỉ primary; ở những phiên bản cũ thường dùng tên **master**.

| Chính sách Lettuce | Ý nghĩa thực tế | Khi nào cân nhắc |
|---|---|---|
| `ReadFrom.UPSTREAM` | Gửi lệnh đọc tới upstream/primary | Đường đọc cần thấy dữ liệu mới nhất mà primary đã áp dụng |
| `ReadFrom.UPSTREAM_PREFERRED` | Ưu tiên primary, có thể dùng replica khi primary không khả dụng theo chính sách client | Đường đọc ưu tiên độ mới nhưng chấp nhận khả năng fallback |
| `ReadFrom.REPLICA` | Chỉ chọn replica cho lệnh đọc đủ điều kiện | Phần đọc chấp nhận bản sao có thể trễ và có chính sách lỗi khi không có replica |
| `ReadFrom.REPLICA_PREFERRED` | Ưu tiên replica; fallback primary khi không có replica phù hợp | Giảm tải đọc cho primary, đồng thời có đường dự phòng |
| `ReadFrom.ANY` | Có thể chọn primary hoặc replica | Trường hợp chấp nhận không kiểm soát chặt nơi đọc |
| `ReadFrom.LOWEST_LATENCY` | Ưu tiên node có độ trễ đo được thấp hơn theo cơ chế client | Khi quan tâm latency và chấp nhận lựa chọn node thay đổi |

Trong một số phiên bản có thể gặp `ReadFrom.MASTER` / `ReadFrom.MASTER_PREFERRED`, là cách đặt tên cũ cho ưu tiên primary. Khi triển khai, sử dụng chính xác API của phiên bản Lettuce đã khóa trong dự án.

### 3.1. Đọc primary

```java
ReadFrom.UPSTREAM
```

Ưu điểm:

- Sau khi lệnh ghi hoàn thành trên primary và không có thay đổi cạnh tranh, lượt đọc tiếp theo trên **cùng primary hiện hành** có thể thấy giá trị vừa ghi.
- Không chịu phần trễ replication giữa primary và replica cho đường đọc này.
- Phù hợp hơn với các màn hình hoặc luồng cần *read-your-writes*.

Giới hạn:

- Tải đọc tiếp tục đè lên primary.
- Nếu primary không khả dụng, không phải mọi lượt đọc đều tự động thành công.
- Trong failover, một ghi đã được primary cũ xác nhận nhưng chưa replication có thể mất khỏi primary mới. Đọc primary **không phải lời hứa về độ bền tuyệt đối** xuyên failover.

### 3.2. Ưu tiên replica

```java
ReadFrom.REPLICA_PREFERRED
```

Ưu điểm:

- Có thể giảm tải đọc lên primary.
- Phân bổ một phần lưu lượng đọc tới replica.
- Có thể quay lại primary khi không có replica phù hợp, giúp duy trì khả năng đọc trong một số tình huống topology thay đổi.

Rủi ro:

- Đọc bản dữ liệu chưa kịp cập nhật.
- Một lượt đọc sau ghi có thể thấy phiên bản cũ.
- Độ mới phụ thuộc độ trễ replication và việc client chọn replica nào.
- **Fallback primary không có nghĩa driver tự phát hiện replica đã trễ dữ liệu.** Replica vẫn online nhưng chậm có thể tiếp tục được chọn.

### 3.3. Chỉ đọc replica

```java
ReadFrom.REPLICA
```

Cách này có ý nghĩa khi workload thật sự muốn tách phần đọc và chấp nhận mất khả năng đọc khi không có replica. Nó thường **không phải** lựa chọn mặc định an toàn cho API quan trọng, bởi:

- Có thể không có replica đủ điều kiện trong quá trình khởi động/failover.
- Một replica ở trạng thái lỗi có thể làm tăng timeout.
- Đọc có thể stale dù node vẫn phản hồi bình thường.

### 3.4. Chọn theo độ trễ không đồng nghĩa chọn theo độ mới

```java
ReadFrom.LOWEST_LATENCY
```

Node có RTT thấp nhất chưa chắc có dữ liệu mới nhất. Một replica đặt gần ứng dụng có thể trả lời nhanh hơn primary nhưng chậm áp dụng replication.

Nếu yêu cầu nghiệp vụ là “người dùng vừa đổi mật khẩu phải thấy trạng thái mới ngay”, **không nên chọn node chỉ theo RTT**.

## 4. Redis phân biệt lệnh đọc và lệnh ghi như thế nào?

Chính sách `ReadFrom` chủ yếu áp dụng với các lệnh được driver xác định là **read-only** và hỗ trợ định tuyến tới replica. Ví dụ về đường đọc:

```redis
GET product:42
HGETALL product:42
MGET cache:1 cache:2
TTL session:42
```

Đường ghi:

```redis
SET product:42 "new"
HSET product:42 price 120
DEL cache:1
INCR metrics:requests
```

Thông thường các lệnh ghi phải tới primary. Redis replica mặc định không cho phép ghi trực tiếp dữ liệu như một primary đang hoạt động.

Các điểm cần lưu ý:

- Không tự suy luận rằng **mọi lệnh có vẻ “đọc”** đều được mọi phiên bản driver định tuyến tới replica. Driver phải biết ngữ nghĩa của lệnh.
- Transaction `MULTI/EXEC`, Lua scripts và lệnh server đặc biệt cần xét riêng, không giả định tuân theo chính sách đọc thông thường.
- Các lệnh có phụ thuộc trạng thái phiên hoặc kết nối có thể có ngữ nghĩa khác với một `GET` độc lập.
- Đối với Redis Cluster, việc định tuyến còn phụ thuộc hash slot; không lấy ví dụ Sentinel rồi áp dụng nguyên xi cho Cluster.

**Quan trọng:** chính sách `ReadFrom` không kiểm tra logic nghiệp vụ. Nó không biết thao tác nào “cần nhất quán mạnh” nếu lập trình viên không phân loại đường đọc.

## 5. Độ trễ replication và dữ liệu cũ

### 5.1. Tình huống đọc-sau-ghi

Một request cập nhật trạng thái phiên:

```text
t0  Spring Boot -> SET user:7:status ACTIVE -> Primary
t1  Primary trả OK
t2  Spring Boot -> GET user:7:status -> Replica A
t3  Replica A vẫn giữ BLOCKED
t4  Replica A nhận bản sao mới và áp dụng ACTIVE
```

Tại `t2`, ứng dụng có thể đọc **`BLOCKED`**, dù ghi ở primary đã trả OK.

Đây là tình huống **replication lag**, không phải Redis client tự làm thay đổi dữ liệu.

### 5.2. Read-after-write consistency

*Read-your-writes* nghĩa là một client sau khi tự ghi xong có thể thấy chính thay đổi đó ở các lượt đọc kế tiếp.

Nếu có yêu cầu này:

- Đọc lại từ **primary** sau khi ghi.
- Hoặc trả thẳng dữ liệu vừa ghi từ ngữ cảnh request khi phù hợp.
- Hoặc sử dụng một cơ chế phối hợp version/replication cụ thể, chấp nhận độ phức tạp và giới hạn thực tế.

Không nên chỉ đổi `REPLICA_PREFERRED` thành `REPLICA` rồi hy vọng dữ liệu sẽ nhất quán hơn.

### 5.3. Ví dụ nghiệp vụ nào chấp nhận replica lag?

| Dữ liệu / chức năng | Đọc replica có thể phù hợp? | Lưu ý |
|---|---|---|
| Danh mục sản phẩm ít đổi | Có thể | Chấp nhận hiển thị chậm trong khoảng ngắn |
| Thống kê lượt xem phục vụ dashboard | Có thể | Ghi rõ độ trễ dự kiến |
| Cache bài viết công khai | Có thể | Kết hợp TTL/invalidation phù hợp |
| Tồn kho hiển thị tham khảo | Có thể, nếu chấp nhận trễ | Quyết định đặt hàng phải có kiểm tra chính xác khác |
| Người dùng vừa sửa hồ sơ và đọc lại ngay | Nên ưu tiên primary | Tránh hiện dữ liệu cũ sau cập nhật |
| Đăng xuất/thu hồi phiên | Thận trọng; thường cần nguồn chính xác | Replica lag có thể trả trạng thái phiên cũ |
| Số dư và lệnh thanh toán | Không dùng replica stale làm quyết định cuối | Cần nguồn có thẩm quyền và cơ chế transaction |
| Khóa phân tán / điều kiện cạnh tranh | Không dựa vào replica stale | Phải thao tác nhất quán ở nơi có quyền ghi |

Các gợi ý này là phân loại theo **ngữ nghĩa nghiệp vụ**. Cùng một khóa có thể có đường đọc phục vụ hiển thị cho phép stale và đường đọc quyết định giao dịch phải lấy dữ liệu mới hơn.

## 6. Cấu hình Sentinel cho Spring Boot

Spring Boot có hỗ trợ cấu hình kết nối Redis Sentinel qua properties. Ví dụ cho Spring Boot 3.x:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
          - sentinel-c.internal:26379
      connect-timeout: 2s
      timeout: 2s
```

Trong cấu hình:

- `master` là **tên nhóm primary** mà các Sentinel theo dõi, ví dụ `mymaster`. Đây không phải hostname của primary.
- `nodes` là các **địa chỉ Sentinel**, thường ở cổng 26379, không phải danh sách replica để đọc trực tiếp.
- Client dùng Sentinel để khám phá địa chỉ Redis data nodes.
- Nếu primary đổi sau failover, driver cần cập nhật topology/kết nối phù hợp.

Trong các phiên bản Spring Boot cũ, prefix có thể là `spring.redis.*` thay vì `spring.data.redis.*`. Cần sử dụng prefix của phiên bản dự án.

**Chỉ có YAML Sentinel chưa quyết định mọi lệnh đọc sẽ được gửi tới replica.** Phần còn lại là cấu hình của Redis driver.

## 7. Cấu hình chính sách đọc trong Lettuce

### 7.1. Cách dùng Spring Boot auto-configuration

Với Spring Boot 3.x dùng Lettuce, có thể tùy chỉnh builder của client bằng `LettuceClientConfigurationBuilderCustomizer`:

```java
package com.example.redis;

import io.lettuce.core.ReadFrom;

import org.springframework.boot.autoconfigure.data.redis
        .LettuceClientConfigurationBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class LettuceReadPolicyConfig {

    @Bean
    public LettuceClientConfigurationBuilderCustomizer
    readFromReplicaPreferred() {

        return builder ->
                builder.readFrom(ReadFrom.REPLICA_PREFERRED);
    }
}
```

Cách cấu hình này có ý nghĩa:

1. Spring Boot đọc cấu hình Sentinel trong `application.yml`.
2. Spring Boot tạo cấu hình client Lettuce, có áp dụng customizer nếu đi qua auto-configuration tương ứng.
3. Lettuce có chính sách `REPLICA_PREFERRED` cho lệnh đọc hỗ trợ routing.
4. Các lệnh ghi vẫn được gửi tới primary theo cơ chế Redis.

**Điểm cần cẩn trọng:** một customizer dùng cho Redis connection factory được auto-configured có thể ảnh hưởng tới **nhiều đường đọc dùng chung factory**. Nếu ứng dụng vừa có dữ liệu chấp nhận stale vừa có dữ liệu cần đọc primary, không nên áp dụng `REPLICA_PREFERRED` toàn cục mà thiếu phân loại.

Ngoài ra, nếu dự án đã tự tạo `LettuceConnectionFactory` thủ công, Spring Boot có thể không áp dụng customizer ở ví dụ này. Khi đó, cấu hình `readFrom` trực tiếp trong factory do bạn tạo.

### 7.2. Tạo LettuceConnectionFactory theo chính sách đọc

Ví dụ Java Spring Data Redis:

```java
package com.example.redis;

import java.time.Duration;

import io.lettuce.core.ReadFrom;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce
        .LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce
        .LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class SentinelRedisConfiguration {

    @Bean
    public RedisSentinelConfiguration redisSentinelConfiguration() {
        return new RedisSentinelConfiguration()
                .master("mymaster")
                .sentinel("sentinel-a.internal", 26379)
                .sentinel("sentinel-b.internal", 26379)
                .sentinel("sentinel-c.internal", 26379);
    }

    @Bean
    public LettuceConnectionFactory redisConnectionFactory(
            RedisSentinelConfiguration sentinels) {

        LettuceClientConfiguration client =
                LettuceClientConfiguration.builder()
                        .readFrom(ReadFrom.REPLICA_PREFERRED)
                        .commandTimeout(Duration.ofSeconds(2))
                        .build();

        return new LettuceConnectionFactory(sentinels, client);
    }

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            LettuceConnectionFactory connectionFactory) {
        return new StringRedisTemplate(connectionFactory);
    }
}
```

Để các đoạn import dễ đọc, ở đây có thể viết các dòng import đầy đủ trên một dòng trong file Java thật:

```java
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
```

Không đặt dấu xuống dòng ở **giữa qualified name trong lệnh import** như cách trình bày rút gọn theo cột; Java yêu cầu cú pháp import liền mạch.

**Lưu ý cho dự án thật:**

- Đặt đúng hostname và cấu hình xác thực/TLS.
- Nếu dùng auto-configuration của Spring Boot, thường không cần tự tạo toàn bộ factory; dùng customizer như mục 7.1 sẽ gọn hơn.
- Nếu tự đăng ký nhiều `RedisConnectionFactory`, phải quản lý bean name/`@Primary` để tránh tiêm nhầm.
- `LettuceClientConfiguration.readFrom(...)` yêu cầu driver/topology hỗ trợ đọc replica. Không tự suy ra chỉ cần một địa chỉ Redis đơn lẻ bất kỳ là client sẽ khám phá mọi replica trong mọi môi trường NAT/Container.
- Không được kỳ vọng code có thể ghi trên replica vì đặt policy đọc.

## 8. Một ứng dụng cần cả hai đường đọc: primary và replica

Chọn replica cho tất cả `GET` có thể làm những đường đọc sau cập nhật nhìn thấy dữ liệu cũ. Một giải pháp rõ ràng là định nghĩa **hai Redis access paths**:

```text
                      ProductService
                      /            \
                     /              \
          Đọc cần mới nhất        Đọc chấp nhận trễ
                   |                    |
              Primary reader        Replica reader
                   |                    |
                 PRIMARY              REPLICA
```

Tách bằng hai factory/template có cấu hình `ReadFrom` khác nhau.

### 8.1. Hai connection factories trong một cấu hình

Ví dụ:

```java
package com.example.redis;

import java.time.Duration;

import io.lettuce.core.ReadFrom;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class DualReadRoutingConfiguration {

    @Bean
    public RedisSentinelConfiguration sentinelTopology() {
        return new RedisSentinelConfiguration()
                .master("mymaster")
                .sentinel("sentinel-a.internal", 26379)
                .sentinel("sentinel-b.internal", 26379)
                .sentinel("sentinel-c.internal", 26379);
    }

    @Bean("primaryRedisConnectionFactory")
    @Primary
    public LettuceConnectionFactory primaryRedisConnectionFactory(
            RedisSentinelConfiguration topology) {

        LettuceClientConfiguration config =
                LettuceClientConfiguration.builder()
                        .readFrom(ReadFrom.UPSTREAM)
                        .commandTimeout(Duration.ofSeconds(2))
                        .build();

        return new LettuceConnectionFactory(topology, config);
    }

    @Bean("replicaRedisConnectionFactory")
    public LettuceConnectionFactory replicaRedisConnectionFactory(
            RedisSentinelConfiguration topology) {

        LettuceClientConfiguration config =
                LettuceClientConfiguration.builder()
                        .readFrom(ReadFrom.REPLICA_PREFERRED)
                        .commandTimeout(Duration.ofSeconds(2))
                        .build();

        return new LettuceConnectionFactory(topology, config);
    }

    @Bean("primaryRedisTemplate")
    @Primary
    public StringRedisTemplate primaryRedisTemplate(
            @Qualifier("primaryRedisConnectionFactory")
            LettuceConnectionFactory factory) {

        return new StringRedisTemplate(factory);
    }

    @Bean("replicaRedisTemplate")
    public StringRedisTemplate replicaRedisTemplate(
            @Qualifier("replicaRedisConnectionFactory")
            LettuceConnectionFactory factory) {

        return new StringRedisTemplate(factory);
    }
}
```

Trong cấu hình này, cả hai factory đều tìm primary và các replica qua Sentinel nhưng có **chính sách chọn node đọc khác nhau**.

`@Primary` giúp các thành phần không dùng `@Qualifier` ưu tiên factory/template hướng primary, nhưng ở những hệ thống có cấu hình Redis phức tạp, vẫn nên tiêm rõ tên bean cho các chức năng quan trọng.

**Lưu ý:** ví dụ tạo thêm kết nối và tài nguyên client. Một dự án có nhiều factory cần đặt timeout, pool, lifecycle, monitoring và security nhất quán. Đây là lựa chọn có chủ đích, không phải mẫu buộc phải dùng cho mọi ứng dụng.

### 8.2. Service chọn đường đọc theo ngữ nghĩa nghiệp vụ

```java
package com.example.redis;

import java.time.Duration;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductRedisService {

    private final StringRedisTemplate primary;
    private final StringRedisTemplate replicaPreferred;

    public ProductRedisService(
            @Qualifier("primaryRedisTemplate")
            StringRedisTemplate primary,
            @Qualifier("replicaRedisTemplate")
            StringRedisTemplate replicaPreferred) {

        this.primary = primary;
        this.replicaPreferred = replicaPreferred;
    }

    public void updatePrice(long productId, String price) {
        primary.opsForValue().set(
                key(productId),
                price,
                Duration.ofMinutes(10)
        );
    }

    // Ví dụ: API danh mục có thể chấp nhận dữ liệu hơi cũ.
    public Optional<String> readForCatalog(long productId) {
        return Optional.ofNullable(
                replicaPreferred.opsForValue().get(key(productId))
        );
    }

    // Ví dụ: đọc ngay sau khi người dùng vừa cập nhật giá.
    public Optional<String> readAfterUpdate(long productId) {
        return Optional.ofNullable(
                primary.opsForValue().get(key(productId))
        );
    }

    private String key(long productId) {
        return "product:price:" + productId;
    }
}
```

Điểm quan trọng không nằm ở việc có hai phương thức `get` khác nhau, mà ở **quy tắc chọn chúng**:

- Đường đọc phục vụ hiển thị ít nhạy cảm có thể dùng replica.
- Đường đọc sau ghi hoặc dùng để quyết định nghiệp vụ phải chọn nơi có bảo đảm độ mới phù hợp.
- Ghi luôn đi qua primary.
- `REPLICA_PREFERRED` cho phép fallback theo chính sách driver, nhưng **không tự xác minh replica đã bắt kịp primary**.

### 8.3. Không thay read policy toàn cục trên một client đang chia sẻ

Một số API ở tầng Lettuce cho phép thay đổi `ReadFrom` trên kết nối. Tuy nhiên, nếu nhiều request chia sẻ cùng client/connection và mỗi request đổi policy qua lại, ta có thể tạo lỗi định tuyến khó dự đoán.

Ở tầng Spring Data Redis, an toàn hơn là chọn **template/factory được cấu hình sẵn cho từng loại đường đọc**, thay vì sửa một trạng thái routing dùng chung trong lúc nhiều thread hoặc reactive subscriptions cùng hoạt động.

## 9. Cấu hình mặc định và sự khác biệt giữa client

Spring Data Redis hỗ trợ nhiều driver, phổ biến là Lettuce và Jedis. Các khả năng chọn node đọc và cơ chế tự khám phá replica **không nhất thiết tương đương** giữa chúng.

- `LettuceClientConfiguration.readFrom(...)` là API cấu hình rõ ràng của **Lettuce**.
- Không nên áp dụng nguyên xi `ReadFrom` của Lettuce cho một cấu hình dùng **Jedis**.
- Một kết nối Redis được cấu hình chỉ tới một server **không mặc nhiên có** discovery đầy đủ và failover Sentinel.
- Cách Spring tạo, chia sẻ và quản lý connection có thể làm thay đổi hành vi thực tế của các lời gọi.

Trước khi chọn chính sách, hãy biết ứng dụng đang sử dụng:

```text
Spring Boot version:
Spring Data Redis version:
Redis driver: Lettuce/Jedis
Redis server version:
Redis mode: standalone + replica / Sentinel / Cluster
ConnectionFactory bean:
ReadFrom policy:
Transaction support:
Serializer:
Timeout:
```

Một hệ thống Spring Boot dùng auto-configuration có thể thay đổi hành vi khi ứng dụng thêm `RedisConnectionFactory` tùy chỉnh. Vì vậy, hãy xem cấu hình thực sự có hiệu lực và thử tại môi trường cùng topology với production.

## 10. Replica lag, TTL và nguy cơ cache miss giả

Replica chậm không chỉ trả giá trị cũ mà còn có thể cho kết quả **không thấy khóa** ở một thời điểm.

Ví dụ:

```text
t0:  Primary SET session:42 ACTIVE EX 60
t1:  Primary trả OK
t2:  GET từ replica -> nil vì chưa nhận SET
t3:  Replica áp dụng SET
```

Nếu ứng dụng coi `nil` là “phiên đã bị xóa”, nó có thể đưa ra quyết định sai.

Hoặc:

```text
t0:  Replica vẫn còn giá trị V1
t1:  Primary cập nhật V2
t2:  GET replica trả V1
t3:  Replica nhận V2
```

Với cache-aside:

```text
GET replica -> cache miss
              |
              v
         Đọc database
              |
              v
         Ghi cache primary
```

Nếu một số lượng lớn khóa vừa được ghi vào primary nhưng chưa tới replica, rất nhiều lượt đọc replica có thể gây **cache miss giả** và làm tăng tải database. Với workload này, việc thêm replica chưa chắc làm cả hệ thống nhanh hơn.

### 10.1. TTL đọc từ replica

`TTL` là lệnh đọc trạng thái thời hạn của khóa trên node được chọn. Vì giá trị/metadata của replica có thể trễ, kết quả về tồn tại khóa và TTL cũng cần được hiểu trong bối cảnh replication.

Không nên dùng một phép đọc TTL trên replica làm đồng hồ chính xác cho quyết định thu hồi quyền hoặc xác nhận hết hạn nghiệp vụ.

### 10.2. Đọc nhiều khóa không phải một ảnh chụp nhất quán

Nếu ứng dụng cần đọc `profile:42` và `permissions:42`, hai lệnh được gửi tới những replica khác nhau hoặc ở những thời điểm khác nhau có thể phản ánh **những mốc cập nhật khác nhau**.

Chọn cùng một read policy không tự tạo snapshot xuyên nhiều khóa. Nếu các khóa phải được kiểm tra nhất quán, hãy thiết kế thao tác và nơi đọc phù hợp với yêu cầu nghiệp vụ thay vì giả định replica có một ảnh chụp đồng bộ tức thời.

## 11. Sentinel failover tác động thế nào đến đường đọc?

### 11.1. Trước và sau failover

Giả sử:

```text
Ban đầu:
  P1: primary
  R1: replica
  R2: replica

Sau sự cố:
  P1: không khả dụng
  R1: được Sentinel nâng thành primary
  R2: theo primary R1
```

Quá trình từ phát hiện lỗi tới công bố topology mới **không phải tức thời**.

```text
t0     P1 lỗi
t1     Sentinel phát hiện và xác nhận trạng thái down
t2     Sentinel chọn replica thích hợp để promote
t3     R1 trở thành primary mới
t4     Redis client phát hiện topology mới và reconnect
t5     Các lệnh có thể phục hồi theo connection/timeout policy
```

Trong giai đoạn này:

- Lệnh ghi có thể lỗi, timeout hoặc phải reconnect.
- Lệnh đọc hướng primary có thể tạm không khả dụng.
- Lệnh đọc hướng replica có thể gặp node đang thay vai trò hoặc chưa đồng bộ.
- Không được giả định mọi lệnh đang chờ đều sẽ hoàn tất thành công.
- Client có thể cần thời gian để thay đổi kết nối sau khi topology đổi.

### 11.2. Replica được promote có thể thiếu dữ liệu gần nhất

Vì Redis replication thông thường bất đồng bộ, primary cũ có thể đã trả `OK` cho một số write nhưng những write này chưa được chuyển đầy đủ đến replica được promote.

Do đó, **Sentinel failover không phải cam kết không mất bất kỳ write đã xác nhận nào**.

Sử dụng `ReadFrom.UPSTREAM` bảo đảm bạn hướng đọc đến primary hiện hành theo driver, nhưng không thể biến một sự kiện failover thành mô hình linearizable/durable tuyệt đối.

Đối với trạng thái tài chính, đơn hàng quan trọng hoặc dữ liệu không được phép mất, cần xem xét nguồn có thẩm quyền và chính sách bền vững nhất quán toàn hệ thống.

### 11.3. REPLICA_PREFERRED trong failover

`REPLICA_PREFERRED` có nghĩa ưu tiên replica đủ điều kiện rồi fallback theo cấu hình client. Nó **không có nghĩa**:

- Luôn tìm được một replica khả dụng trong mọi sự cố.
- Tự đợi replica bắt kịp primary.
- Tự xác nhận tất cả write trước đó đã được replication.
- Loại bỏ timeout.
- Tự retry các lệnh ghi một cách an toàn.

Vì vậy, cần chính sách timeout, retry, giám sát và xử lý lỗi rõ ràng ở ứng dụng.

## 12. READONLY của Cluster khác chính sách ReadFrom của Sentinel

Một lỗi khái niệm dễ gặp là áp dụng hướng dẫn Redis Cluster vào Sentinel.

### Redis Sentinel

- Một primary và các replica của một nhóm dữ liệu.
- Sentinel khám phá primary và quản lý failover.
- Lettuce `ReadFrom` có thể chọn primary/replica cho lệnh đọc.
- Không có phân chia dữ liệu theo 16.384 hash slot như Redis Cluster.

### Redis Cluster

- Dữ liệu phân chia theo hash slot, có nhiều primary và các replica cho từng primary.
- Client định tuyến theo slot.
- Redis có lệnh `READONLY` cho kết nối tới replica trong ngữ cảnh Redis Cluster để cho phép đọc theo cơ chế phù hợp.
- Chính sách đọc còn phải xét node sở hữu slot và topology của từng shard.

`READONLY` trong Redis Cluster **không phải** câu lệnh chung thay thế `ReadFrom.REPLICA_PREFERRED` của Lettuce khi kết nối tới Redis Sentinel.

Tương tự, không nên thiết kế một lệnh `MGET` trên các khóa thuộc nhiều slot khác nhau mà giả định sẽ hoạt động chỉ vì client đang bật read-from-replica.

## 13. RedisTemplate, transaction và read routing

`RedisTemplate` có thể sử dụng các kết nối khác nhau tùy cấu hình và cách điều phối operation. Điều này đặc biệt cần chú ý khi dùng:

```java
redisTemplate.setEnableTransactionSupport(true);
```

hoặc khi ứng dụng chủ động sử dụng:

```java
SessionCallback
MULTI
EXEC
WATCH
```

Một số nguyên tắc:

1. **`ReadFrom` không biến các lệnh đọc rời rạc thành một transaction.**
2. **Transaction Redis có ngữ nghĩa riêng về connection và primary.** Không mặc định lệnh đọc trong mọi transaction được định tuyến giống một `GET` độc lập.
3. Đối với `WATCH` và `MULTI/EXEC`, các lệnh liên quan cần cùng ngữ cảnh kết nối/phiên phù hợp; replica read stale không thể dùng làm cơ sở an toàn cho quyết định giao dịch trên primary.
4. Khi Spring Data Redis tham gia transaction Spring, cách đọc và ghi được xử lý qua các kết nối riêng tùy cấu hình; cần hiểu phiên bản/semantics cụ thể.
5. Nếu logic cần kiểm tra rồi ghi có ràng buộc đúng đắn, nên chạy kiểm tra/giao dịch ở phía có quyền cập nhật hoặc dùng script/atomic command phù hợp.

Ví dụ **không an toàn**:

```text
Replica: GET stock:item-1 -> 5 (stale)
Primary: HSET/DECR/SET dựa trên 5
```

Nếu primary đã có `stock=0` mà replica vẫn báo `5`, việc kiểm tra từ replica đã sai từ đầu.

Không dùng replica reads cho các bước cấp quyền, trừ số dư, khóa phân tán hoặc kiểm tra giới hạn có yêu cầu tính đúng đắn mạnh mà chưa có phương án xác minh trên primary.

## 14. WAIT có giải quyết hoàn toàn replica lag không?

Redis có lệnh:

```redis
WAIT numreplicas timeout
```

Ví dụ:

```redis
WAIT 1 1000
```

Lệnh này yêu cầu Redis chờ cho một số replica báo đã tiếp nhận tiến độ replication của các write trước đó trên kết nối, trong thời gian chờ cho phép.

Tuy nhiên:

- `WAIT` **không tự biến Redis thành hệ thống nhất quán mạnh**.
- Nếu có nhiều replica, việc một replica xác nhận không bảo đảm **mọi replica** đã cập nhật.
- `REPLICA_PREFERRED` có thể chọn một replica khác, chưa theo kịp.
- Không bảo đảm mọi bản ghi đã bền vững trên đĩa hoặc an toàn trước mọi kiểu failover.
- Cần kiểm tra giá trị trả về và các giới hạn áp dụng của lệnh; không coi timeout là đã đồng bộ thành công.

Nếu dùng `WAIT`, phải hiểu **ngữ cảnh connection và thứ tự write trước đó**, không phát `WAIT` tùy tiện từ một RedisTemplate/connection khác rồi suy ra nó đang chờ đúng write mong muốn.

Với dữ liệu cần *read-your-writes*, đọc lại trên primary vẫn là một lựa chọn rõ ràng hơn việc hy vọng chính sách replica và `WAIT` tình cờ chọn đúng bản sao.

## 15. Quan sát replication và trạng thái Sentinel

### 15.1. Xác định primary theo Sentinel

Trên một Sentinel:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL get-master-addr-by-name mymaster
```

Redis có thể trả địa chỉ và cổng primary hiện tại.

Để xem các replica Sentinel biết tới:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL replicas mymaster
```

Đây là metadata khám phá topology; nó không tự chứng minh các read command của Spring Boot thực sự đi đến replica nào.

### 15.2. Xem vai trò và tiến độ replication

Kết nối tới một Redis data node:

```bash
redis-cli -h redis-primary.internal -p 6379 ROLE
redis-cli -h redis-primary.internal -p 6379 INFO replication
```

Trên replica:

```bash
redis-cli -h redis-replica-a.internal -p 6379 ROLE
redis-cli -h redis-replica-a.internal -p 6379 INFO replication
```

Các trường thường hữu ích trong `INFO replication` gồm:

| Thông tin | Ý nghĩa |
|---|---|
| `role` | Node là primary hay replica |
| `connected_slaves` / thông tin replica | Các replica mà primary đang thấy; cách đặt tên có thể phụ thuộc phiên bản |
| `master_repl_offset` | Tiến độ replication mà primary/replica báo cáo theo ngữ cảnh |
| `slave_repl_offset` | Offset được báo tại một số trường thống kê theo phiên bản/vai trò |
| `master_link_status` | Trạng thái kết nối replication của replica tới primary |
| `master_last_io_seconds_ago` | Thời gian kể từ hoạt động I/O liên quan primary trên replica |

Chỉ số offset cung cấp dấu hiệu replication lag, nhưng **không thay thế một phép đo độ mới theo thời gian thực trên dữ liệu nghiệp vụ**.

### 15.3. Quan sát đường đi của lệnh đọc

Nếu muốn biết read policy có được áp dụng:

- Ghi lại `ReadFrom` thực sự được cấu hình ở connection factory.
- Dùng Redis client logging/metrics ở môi trường thử nghiệm khi cần.
- Quan sát số lệnh `GET` và CPU trên từng data node.
- Trong thí nghiệm có tải cô lập, so sánh `INFO commandstats` trước và sau lượt đọc.
- Không bật `MONITOR` bừa bãi trên Redis production vì có thể tốn tài nguyên và làm lộ nội dung lệnh.

Kết quả `INFO commandstats` tăng trên replica là dấu hiệu có thể giúp xác minh routing, nhưng trong hệ thống có nhiều client đồng thời, phải tránh khẳng định mọi lệnh tăng đều thuộc ứng dụng của mình.

### 15.4. Các metric nên theo dõi

| Metric | Câu hỏi vận hành |
|---|---|
| Replication lag theo replica | Bản sao chậm tới đâu? |
| Trạng thái liên kết primary–replica | Replica còn đồng bộ được không? |
| Tốc độ read/write mỗi node | Tải có được phân bổ như kỳ vọng không? |
| p95/p99 read latency | Replica có thật sự giúp request nhanh hơn? |
| Số fallback sang primary | Chính sách ưu tiên replica có đang bị thiếu replica không? |
| Số reconnect/failover | Client có hay bị gián đoạn kết nối không? |
| Redis timeout/error | Có ảnh hưởng đến trải nghiệm người dùng? |
| Stale-read incidents | Có dữ liệu cũ vượt ngưỡng chấp nhận không? |
| Miss/hit cache | Lag có gây miss giả hoặc tăng tải dữ liệu nguồn không? |

Không phải driver nào cũng xuất sẵn mọi metric. Nếu không có chỉ số fallback/route, cần bổ sung quan sát phù hợp ở tầng client hoặc môi trường thử nghiệm.

## 16. Thực hành: kiểm tra chính sách đọc

### Bài tập A: Quan sát replica lag mà không cố tình phá topology

1. Chuẩn bị Redis primary + replica + Sentinel trong môi trường thử nghiệm.
2. Dùng client hướng primary để ghi một khóa mới với phiên bản tăng dần.
3. Dùng client hướng replica để đọc lại khóa.
4. Ghi thời điểm ghi và thời điểm replica bắt đầu thấy phiên bản mới.
5. Lặp nhiều lần với các kích thước payload và mức tải khác nhau.

Ví dụ:

```redis
SET demo:replication:version 101
GET demo:replication:version
```

Lệnh `SET` nên được chạy trên primary; lệnh `GET` ở bước so sánh cần chỉ rõ node/kết nối. Nếu đọc trực tiếp bằng Redis CLI tới replica, hãy đảm bảo đang dùng địa chỉ replica thực tế.

**Không phải lần thử nào cũng quan sát được dữ liệu cũ**; nếu replication rất nhanh, replica có thể áp dụng trước khi bạn đọc. Bài thực hành nhằm minh họa giới hạn và đo độ trễ, không nhằm ép hệ thống luôn có stale read.

### Bài tập B: So sánh ReadFrom.UPSTREAM và REPLICA_PREFERRED

Tạo hai template như mục 8:

```java
primary.opsForValue().set("demo:price", "120");
String fromPrimary = primary.opsForValue().get("demo:price");
String fromReplica = replicaPreferred.opsForValue().get("demo:price");
```

Lặp nhiều lần trong môi trường thử nghiệm. Ghi:

```text
Lần chạy | Kết quả primary | Kết quả replica | Thời gian | Node được chọn
```

Đừng diễn giải một lần cả hai cùng trả `120` là bằng chứng replica **luôn** nhất quán tức thời.

### Bài tập C: Khi replica không khả dụng

Trong môi trường thử nghiệm được kiểm soát, làm replica tạm không khả dụng rồi so sánh:

- `REPLICA` có thể không còn node đủ điều kiện để đọc.
- `REPLICA_PREFERRED` có thể fallback sang primary theo cơ chế client.
- `UPSTREAM` vẫn hướng về primary nếu primary còn hoạt động.

Quan sát timeout, reconnect và latency. Không thực hiện việc tắt replica chủ động trên production chỉ để thử đường fallback.

### Bài tập D: Đổi primary qua failover

Trong một môi trường Sentinel thử nghiệm riêng, thực hiện quy trình failover theo hướng dẫn vận hành. Sau đó xác nhận:

- Sentinel đã công bố primary mới.
- Lettuce cập nhật kết nối.
- Các write mới được gửi tới primary mới.
- Chính sách read-from tiếp tục hoạt động.
- Ứng dụng có chính sách xử lý timeout trong khoảng chuyển đổi.

**Không giả định failover đồng nghĩa không mất write đang replication**; cần phân tích dữ liệu và cam kết của ứng dụng.

### Bài tập E: Đường đọc sau ghi

Tạo một API cập nhật trạng thái rồi đọc lại ngay. So sánh:

```text
WRITE primary -> READ primary
WRITE primary -> READ replicaPreferred
```

Nếu API có hợp đồng “đã lưu là đọc ngay thấy”, hãy giữ đường đọc primary cho tình huống đó hoặc thiết kế một cơ chế nhất quán rõ ràng hơn.

## 17. Lỗi thường gặp khi chọn primary/replica

### Lỗi 1: Có Sentinel là tự động mọi GET dùng replica

Sentinel giúp khám phá primary và failover. Driver mới là thành phần áp dụng read routing; phải cấu hình `ReadFrom` nếu muốn ưu tiên replica.

### Lỗi 2: Coi replica là bản sao cập nhật ngay lập tức

Redis replication thông thường bất đồng bộ. Replica có thể trả dữ liệu cũ hoặc chưa có khóa ngay sau một lệnh ghi.

### Lỗi 3: Dùng REPLICA_PREFERRED cho cả kiểm tra nghiệp vụ quan trọng

Đọc số dư, quyền truy cập hoặc tồn kho từ replica stale có thể dẫn tới quyết định sai. Chọn primary hoặc cơ chế kiểm soát đồng thời phù hợp cho thao tác cần chính xác.

### Lỗi 4: Hiểu REPLICA_PREFERRED là tự chuyển primary khi replica chậm

Chính sách ưu tiên replica thường fallback khi không có replica phù hợp theo topology, **không phải** khi replica trả dữ liệu cũ nhưng vẫn hoạt động bình thường.

### Lỗi 5: Dùng ReadFrom.REPLICA mà không có đường xử lý khi mất replica

Nếu chỉ cho phép đọc replica, ứng dụng cần xử lý trường hợp replica không tồn tại hoặc lỗi. `REPLICA_PREFERRED` thường linh hoạt hơn cho dữ liệu chấp nhận stale.

### Lỗi 6: Đổi chính sách trên connection dùng chung trong từng request

Có thể gây tương tác khó lường giữa các request. Tách template/factory có chính sách cố định rõ ràng là một cách thiết kế dễ kiểm soát hơn.

### Lỗi 7: Nhầm connection pool với số lệnh Redis

Lettuce có thể multiplex nhiều lệnh trên kết nối. Tăng số connection không tự giải quyết replication lag hay bảo đảm routing đúng.

### Lỗi 8: Nghĩ Sentinel proxy mọi câu lệnh

Sentinel cung cấp thông tin topology và failover; client kết nối trực tiếp đến Redis data nodes. Nếu network chỉ cho phép kết nối tới Sentinel mà chặn primary/replica, ứng dụng vẫn có thể lỗi.

### Lỗi 9: Không xét failover khi đánh giá nhất quán

Ngay cả đọc primary mới sau failover không bảo đảm mọi write cũ đã được replication trước khi primary cũ gặp lỗi. Phải hiểu giới hạn durability của Redis replication.

### Lỗi 10: Dùng WAIT rồi mặc định replica nào cũng đã đồng bộ

`WAIT` có ngữ nghĩa chờ số lượng replica xác nhận replication trước đó, không đảm bảo một `ReadFrom.REPLICA_PREFERRED` sẽ chọn đúng replica đã bắt kịp, cũng không biến Redis thành transaction phân tán.

### Lỗi 11: Không tính timeout và retry

Trong lúc failover/reconnect có thể có timeout. Retry quá mức gây tăng tải; retry lệnh ghi không idempotent có thể thực hiện tác dụng phụ lặp.

### Lỗi 12: Chỉ nhìn p50, bỏ qua stale reads

Replica đọc nhanh hơn ở p50 nhưng có thể trả dữ liệu cũ trong các trường hợp quan trọng. Cần đo cả p95/p99 và độ mới theo nghiệp vụ.

### Lỗi 13: Giả định chọn `LOWEST_LATENCY` cũng chọn dữ liệu mới nhất

Độ trễ mạng và độ trễ replication là hai chỉ số khác nhau. Replica gần nhất có thể là replica stale nhất.

### Lỗi 14: Không biết phiên bản API

Các tên `MASTER`/`UPSTREAM`, các lựa chọn ReadFrom và chi tiết cấu hình Boot/Lettuce thay đổi theo phiên bản. Nên kiểm tra dependency đã khóa và cấu hình thực sự có hiệu lực.

### Lỗi 15: Không phân biệt Sentinel và Cluster

Cluster dùng hash slot và có cơ chế định tuyến riêng; không lấy logic Redis Sentinel primary–replica để áp dụng nguyên xi cho tất cả các thao tác Redis Cluster.

## 18. Thiết kế chính sách đọc theo yêu cầu hệ thống

Một ma trận quyết định đơn giản:

| Yêu cầu | Lựa chọn đáng cân nhắc | Điều cần đánh đổi |
|---|---|---|
| Hiển thị catalog, chấp nhận stale | `REPLICA_PREFERRED` | Đọc cũ trong replication lag |
| Đọc ngay sau ghi cùng nghiệp vụ | `UPSTREAM` | Tải đọc lên primary |
| API cần luôn ưu tiên dữ liệu chính xác | Primary và kiểm soát transaction phù hợp | Khả năng sẵn sàng có thể giảm khi primary lỗi |
| Khối lượng đọc lớn và cho phép stale | `REPLICA_PREFERRED` hoặc replica-only có chính sách lỗi | Tính nhất quán cuối cùng |
| Phần đọc chỉ phục vụ thống kê nền | Replica, tùy workload | Có thể chậm trễ/tạm thiếu dữ liệu |
| Một số endpoint cần độ mới, số khác cần throughput | Hai template/factory với policy rõ ràng | Cấu hình và tài nguyên client tăng |
| Dữ liệu không được mất sau failover | Không dựa riêng vào ReadFrom/Sentinel | Cần thiết kế durability và nguồn dữ liệu có thẩm quyền |

Một mẫu phân lớp hữu ích:

```text
HTTP Controller
      |
      v
Business Service
      |
      +--> Read model có thể stale
      |          |
      |          v
      |    Replica-preferred template
      |
      +--> Read cần cập nhật ngay / validation
      |          |
      |          v
      |     Primary-only template
      |
      +--> Write
                 |
                 v
            Primary
```

Hãy đặt quyết định chọn primary/replica ở **tầng service hoặc repository đủ hiểu nghiệp vụ**, thay vì thay đổi bí mật trong một helper khiến người dùng API không biết dữ liệu có thể stale.

### 18.1. Có thể đặt SLO cho độ mới

Nếu yêu cầu chấp nhận stale, nên viết rõ giới hạn mong muốn:

```text
Catalog có thể cũ tối đa khoảng 2 giây trong tải bình thường.
Dashboard có thể trễ tối đa khoảng 30 giây.
Đường đọc xác minh thay đổi của chính người dùng phải dùng primary.
```

Đây là **các ngưỡng minh họa**, không phải bảo đảm mà Redis tự cung cấp. Phải đo thực tế replication lag và có phương án khi vượt ngưỡng.

Nếu dữ liệu cũ vượt giới hạn cho phép, có thể:

- Tạm chuyển đường đọc quan trọng sang primary.
- Thực hiện xác minh phiên bản ở nguồn có thẩm quyền.
- Thông báo độ trễ hoặc trả trạng thái chưa đồng bộ.
- Hạn chế lưu lượng đọc vào các replica đang có vấn đề.
- Sử dụng cơ chế ứng dụng khác nếu yêu cầu nhất quán vượt khả năng mô hình này.

## 19. Câu hỏi tự kiểm tra

**1. Sentinel có quyết định trực tiếp mọi GET sẽ đọc từ replica không?**

Không. Sentinel hỗ trợ giám sát và khám phá primary/failover; Lettuce áp dụng chính sách chọn node đọc khi driver/topology hỗ trợ.

**2. REPLICA_PREFERRED khác REPLICA ở đâu?**

`REPLICA_PREFERRED` ưu tiên replica nhưng có thể fallback primary khi không có replica phù hợp; `REPLICA` yêu cầu đường đọc hướng replica, dễ gặp lỗi khi không có replica đủ điều kiện.

**3. Viết xong rồi GET replica ngay có chắc thấy dữ liệu mới?**

Không. Replication thường bất đồng bộ nên replica có thể chưa nhận và áp dụng thay đổi.

**4. Đọc primary có giải quyết mọi vấn đề nhất quán sau failover không?**

Không. Primary mới có thể chưa nhận các write mà primary cũ đã xác nhận trước khi lỗi.

**5. Tại sao không nên chỉ dựa vào độ trễ mạng để chọn replica?**

Vì RTT thấp không phản ánh dữ liệu có mới hay không. Latency routing và replication lag là hai khái niệm khác nhau.

**6. `ReadFrom` có chuyển lệnh SET sang replica không?**

Không. Chính sách đọc áp dụng cho lệnh đọc thích hợp; ghi thông thường phải tới primary.

**7. Tại sao có thể cần hai StringRedisTemplate?**

Vì một đường đọc có thể chấp nhận stale, còn đường khác cần đọc primary sau ghi. Hai template với read policy cố định làm ranh giới rõ ràng hơn.

**8. `WAIT 1 1000` có chắc tất cả replica đều đã bắt kịp?**

Không. Nó chỉ chờ số replica xác nhận đạt điều kiện theo ngữ nghĩa lệnh, không bảo đảm mọi replica hoặc mọi dạng bền vững dữ liệu.

**9. Số pending connection thấp có chứng minh replica không lag không?**

Không. Trạng thái kết nối client và độ trễ replication là hai chỉ số khác nhau.

**10. Khi chạy Redis Cluster, có thể dùng đúng toàn bộ mô hình Sentinel không?**

Không. Cluster còn có hash slots, nhiều primary và cơ chế định tuyến riêng. Cần cấu hình và đánh giá tương ứng.

## 20. Ghi nhớ

- **Redis replication thông thường bất đồng bộ.** Replica có thể trả giá trị cũ hoặc chưa thấy một khóa vừa ghi trên primary.
- **Sentinel quản lý giám sát, khám phá primary và failover**; **Lettuce `ReadFrom` quyết định chính sách đọc** theo topology hỗ trợ.
- **`ReadFrom.UPSTREAM`** phù hợp hơn với đường đọc cần thấy dữ liệu đã ghi trên primary hiện hành; **`ReadFrom.REPLICA_PREFERRED`** phù hợp với đọc có thể chấp nhận stale và muốn chia tải, có fallback theo chính sách driver.
- **Fallback không phải phát hiện replica lag**; replica hoạt động bình thường vẫn có thể trả dữ liệu cũ.
- Spring Data Redis có thể cấu hình qua **`LettuceClientConfigurationBuilderCustomizer`** hoặc **`LettuceClientConfiguration.readFrom(...)`** trong connection factory.
- Với ứng dụng có yêu cầu đọc khác nhau, **phân tách primary template và replica-preferred template** giúp quyết định nhất quán minh bạch.
- **Read routing không tạo tính nhất quán mạnh hoặc bảo đảm không mất dữ liệu khi failover.** Cần đánh giá read-your-writes, transaction, durability, retry và idempotency theo nghiệp vụ.
- Đo cả **latency và độ mới dữ liệu**, cùng trạng thái Sentinel, replica lag, đường đi của các lệnh và tỷ lệ lỗi khi failover.

### Tài liệu tham khảo

- [Spring Data Redis — High Availability: Redis Sentinel](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html).
- [Spring Data Redis — Redis Configuration](https://docs.spring.io/spring-data/redis/reference/redis/redis-configuration.html).
- [Spring Data Redis — LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html).
- [Lettuce — ReadFrom: read preferences](https://redis.github.io/lettuce/ha-sharding/).
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/).
- [Redis — INFO](https://redis.io/docs/latest/commands/info/).
- [Redis — WAIT](https://redis.io/docs/latest/commands/wait/).
