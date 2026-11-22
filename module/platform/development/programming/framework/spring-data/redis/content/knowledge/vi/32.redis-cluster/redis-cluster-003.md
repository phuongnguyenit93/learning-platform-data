# Khám phá topology và xử lý chuyển hướng MOVED, ASK

Khi ứng dụng dùng **Spring Data Redis** kết nối với **Redis Cluster**, một khóa Redis không nhất thiết nằm trên node đầu tiên mà client kết nối. Cluster phân bố không gian khóa thành **16.384 hash slot**, mỗi slot được một primary sở hữu tại một thời điểm. Redis client phải biết node nào đang sở hữu slot của khóa để gửi lệnh đúng nơi. Thông tin đó được gọi là **cluster topology**.

Topology có thể thay đổi khi thêm/bớt node, chuyển slot (*resharding*) hoặc failover. Nếu client dùng thông tin cũ, Redis có thể trả lỗi chuyển hướng **`MOVED`** hoặc **`ASK`**. Đối với Spring Data Redis dùng Lettuce, driver thường xử lý các chuyển hướng này và cập nhật bản đồ slot thay vì bắt business code tự phân tích chuỗi lỗi.

Bài học giải thích Redis Cluster định tuyến khóa ra sao, cách khám phá và làm mới topology trong Spring Data Redis, ý nghĩa chính xác của `MOVED`/`ASK`, những giới hạn liên quan đến multi-key commands, cách xử lý lỗi/retry và các bước kiểm chứng bằng Redis CLI.

## 1. Vì sao ứng dụng phải biết topology của Redis Cluster?

Redis standalone có một endpoint dữ liệu chính. Redis Cluster thì gồm nhiều node, thường bao gồm các primary và các replica:

```text
                 Spring Data Redis + Lettuce
                            |
                   Cluster slot map
                            |
         +------------------+------------------+
         |                  |                  |
         v                  v                  v
     Primary A          Primary B          Primary C
     slots 0..5460      5461..10922       10923..16383
         |                  |                  |
         v                  v                  v
      Replica A          Replica B          Replica C
```

Các khoảng slot ở sơ đồ chỉ là **ví dụ một cách phân bổ**. Redis Cluster không bắt buộc luôn chia đều ba khoảng như vậy; trong thực tế các node có thể sở hữu nhiều khoảng slot và topology sẽ thay đổi theo resharding.

Khi ứng dụng chạy:

```java
stringRedisTemplate.opsForValue().get("user:42:status");
```

client cần thực hiện về mặt logic:

1. Tính hash slot của khóa `user:42:status`.
2. Tra cứu slot đó trong slot map hiện có.
3. Chọn node thích hợp với loại lệnh (thông thường primary cho ghi).
4. Gửi command đến node đó.
5. Nếu Redis báo định tuyến sai, xử lý redirection và cập nhật topology theo chính sách driver.
6. Trả kết quả hoặc lỗi cuối cùng cho ứng dụng.

Nếu ứng dụng chỉ mở TCP connection đến một node seed rồi gửi mọi khóa vào node đó, những khóa thuộc slot khác sẽ thường gây `MOVED`. Việc có cluster-aware driver giúp tránh một vòng chuyển hướng cho mỗi thao tác trong trạng thái bình thường.

## 2. Redis Cluster dùng 16.384 hash slot

Redis Cluster ánh xạ tên khóa sang một số nguyên từ **0 đến 16383**:

```text
slot = CRC16(keyBytes) mod 16384
```

Trong thực tế, quy tắc hash tag có thể khiến Redis chỉ dùng **phần nằm giữa cặp ngoặc nhọn hợp lệ** để tính slot, thay vì toàn bộ khóa.

Ví dụ:

```text
cart:{user-42}:items
cart:{user-42}:total
```

Cả hai khóa đều có hash tag `{user-42}`, nên cùng được ánh xạ vào một hash slot. Đây là một công cụ thiết kế quan trọng khi nghiệp vụ cần lệnh Redis nhiều khóa trong cùng slot.

Redis không phân phối trực tiếp từng khóa bằng việc tra một bảng ánh xạ tên key → node cho mọi key. Nó ánh xạ **hash slot → node**. Một node primary có thể sở hữu nhiều slot và rất nhiều khóa thuộc các slot đó.

### Kiểm tra slot bằng Redis CLI

```bash
redis-cli -p 7000 CLUSTER KEYSLOT 'cart:{user-42}:items'
redis-cli -p 7000 CLUSTER KEYSLOT 'cart:{user-42}:total'
redis-cli -p 7000 CLUSTER KEYSLOT 'user:42:status'
```

Hai câu lệnh đầu phải ra cùng slot nếu cluster và Redis CLI đang hoạt động đúng. Không cần đoán hoặc hard-code giá trị số slot trong ứng dụng; driver tính slot từ byte khóa đã được serialize.

**Lưu ý quan trọng:** Spring Data Redis có serializer cho key. Nếu Java dùng `StringRedisSerializer`, key byte thường tương ứng với chuỗi UTF-8. Nếu dùng JDK serializer hoặc một codec tùy chỉnh, dãy byte thực tế của Redis key khác, nên slot có thể khác so với kết quả CLI khi nhập chuỗi dễ đọc. Cần xác định chính xác **wire format của key** khi debug routing.

## 3. Topology gồm những thông tin gì?

Một bản topology đủ cho cluster client thường cần thông tin như:

- ID của từng node trong cluster.
- Endpoint host/port mà client có thể kết nối.
- Node là primary hay replica; replica thuộc primary nào.
- Hash slot và khoảng slot được mỗi primary sở hữu.
- Trạng thái liên quan failover, node availability và chuyển slot.
- Phiên bản/trạng thái topology mà client đang dùng để lựa chọn đường đi.

Có thể hình dung bản đồ phía client:

```text
slot 0..5460       -> redis-a:7000 (primary)
slot 5461..10922   -> redis-b:7001 (primary)
slot 10923..16383  -> redis-c:7002 (primary)

Redis replica endpoints cũng nằm trong topology
để phục vụ failover hoặc read-from-replica khi cấu hình.
```

Một địa chỉ **seed node** chỉ là điểm khởi đầu để khám phá cluster. Nó không đồng nghĩa mọi command sẽ được gửi đến seed, và cũng không có nghĩa seed là một load balancer biết định tuyến mọi khóa.

### Seed list không phải slot map

Cấu hình:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a:7000
          - redis-b:7001
          - redis-c:7002
        max-redirects: 5
```

cho ứng dụng một số endpoint có thể dùng để liên hệ cluster. Sau kết nối/khám phá, driver thu được topology và biết thực tế slot nào thuộc primary nào.

Các endpoint là ví dụ. Cần thay bằng host/port tương ứng và cấu hình TLS/ACL trong môi trường thật. Nếu dùng một phiên bản Spring Boot khác, cần đối chiếu prefix của Redis properties với phiên bản đó.

Không nên nghĩ rằng mỗi lần chạy `GET` sẽ lần lượt thử từng node trong danh sách seed. Một cluster-aware client có khả năng **routing theo slot**.

## 4. Redis CLI dùng lệnh nào để khám phá topology?

Các lệnh quan sát hữu ích:

```bash
redis-cli -h redis-a -p 7000 CLUSTER INFO
redis-cli -h redis-a -p 7000 CLUSTER NODES
redis-cli -h redis-a -p 7000 CLUSTER SLOTS
redis-cli -h redis-a -p 7000 CLUSTER SHARDS
```

Ý nghĩa:

| Lệnh | Thông tin chính |
|---|---|
| `CLUSTER INFO` | Trạng thái cluster, tổng slot hoạt động, các thông số cluster-wide |
| `CLUSTER NODES` | Danh sách node, ID, role, trạng thái kết nối và các slot/range theo góc nhìn node đang hỏi |
| `CLUSTER SLOTS` | Ánh xạ slot range tới primary/replica endpoints; được nhiều Redis clients dùng lịch sử |
| `CLUSTER SHARDS` | Thông tin shard/slot/node ở dạng cấu trúc; được khuyến khích trong các Redis version hỗ trợ |
| `CLUSTER KEYSLOT key` | Slot được tính cho một Redis key |
| `CLUSTER MYID` | Node ID của node Redis đang kết nối |

`CLUSTER SHARDS` có ở những Redis version mới, trong khi `CLUSTER SLOTS` phổ biến và được hỗ trợ bởi nhiều driver. Đừng viết logic của ứng dụng yêu cầu tất cả cluster luôn cùng cung cấp một dạng output; để Lettuce xử lý discovery theo khả năng của Redis/driver.

### Trạng thái cluster ok không có nghĩa ứng dụng định tuyến đúng

Ví dụ `cluster_state:ok` cho biết cluster theo góc nhìn Redis đang vận hành đủ điều kiện, nhưng **không chứng minh**:

- client đã refresh slot map mới nhất;
- endpoint Redis quảng bá có thể truy cập từ mạng ứng dụng;
- mọi application instance dùng cùng cấu hình;
- tất cả lệnh có đủ ACL;
- Redis replica được phép và đủ mới để trả dữ liệu;
- một thao tác multi-key có các key ở cùng slot.

Cần kết hợp Redis cluster state, client routing logs, endpoint reachability và thử lệnh qua đường Spring thực tế.

## 5. Khám phá topology ban đầu diễn ra như thế nào?

Một luồng điển hình với Lettuce cluster client:

```text
Spring Boot khởi động
        |
        v
Lettuce nhận danh sách seed endpoints
        |
        v
Kết nối một/một số seed node sẵn sàng
        |
        v
Lấy cluster topology (slot ranges, node endpoints)
        |
        v
Tạo/cập nhật slot map trong Redis client
        |
        v
GET keyA -> route primary của slotA
SET keyB -> route primary của slotB
```

Không cần application tự triển khai đoạn:

```java
try {
    getFromNodeA(key);
} catch (MovedException e) {
    parseHostAndRetry(e);
}
```

Khi đã cấu hình Redis cluster đúng với Lettuce, nên để driver đảm nhận redirect, connection routing và refresh slot map. Logic nghiệp vụ chỉ dùng `RedisTemplate`, `StringRedisTemplate` hoặc `ReactiveRedisTemplate` theo kiểu dữ liệu và use case.

Tuy nhiên, driver không thể tự sửa một topology bị quảng bá endpoint **không thể kết nối được**. Ví dụ Redis trả `10.0.0.5:7001` trong topology nhưng container ứng dụng chỉ có thể truy cập `redis-service.internal:7001`. Khi đó cluster client có thể khám phá node nhưng không mở được kết nối tới node đích.

## 6. MOVED là gì?

`MOVED` là phản hồi Redis cho biết **slot mà command đang truy cập thuộc node khác**.

Phản hồi ví dụ:

```text
-MOVED 12182 redis-b:7001
```

Ý nghĩa:

- `MOVED`: tên loại redirection;
- `12182`: số slot của khóa đang được truy cập;
- `redis-b:7001`: endpoint mà node trả lời cho rằng đang sở hữu slot đó.

Thông điệp ví dụ chỉ mô tả cấu trúc; số slot không được gắn cứng với một tên key cụ thể trong bài.

### Luồng xử lý MOVED

```text
Client đang tin slot 12182 -> redis-a
        |
        | GET key thuộc slot 12182
        v
redis-a
        |
        +--> "-MOVED 12182 redis-b:7001"
                              |
                              v
                   Client định tuyến lại command
                              |
                              v
                          redis-b
                              |
                              v
                         Trả kết quả
```

Một cluster-aware client thường có thể:

1. Nhận `MOVED`.
2. Thực thi lại command tại endpoint đích, trong giới hạn redirection/retry phù hợp.
3. Nhận ra slot map hiện tại có thể đã lỗi thời.
4. Kích hoạt hoặc lên lịch topology refresh để cập nhật ánh xạ slot cho các command tiếp theo.

Điểm cốt lõi: **`MOVED` liên quan quyền sở hữu slot**, không đơn thuần là “node hiện tại tạm bận”. Nếu client vẫn cứ gửi tất cả lệnh cùng slot vào node cũ, nó có thể phải chịu redirect liên tục.

### MOVED xuất hiện trong những trường hợp nào?

- Client chỉ biết một seed node và chưa có slot map.
- Cluster đã reshard, slot chuyển sang primary khác.
- Client chưa refresh topology sau failover/đổi primary.
- Client giữ một topology cũ so với trạng thái mới mà node Redis đã biết.
- Ứng dụng cấu hình driver không thực sự cluster-aware, khiến mọi lệnh đi đến một endpoint.

Một lần `MOVED` trong lúc topology thay đổi không nhất thiết là sự cố. Nhưng **số lượng MOVED cao liên tục** là tín hiệu nên xem lại topology refresh, endpoint discovery, failover và cấu hình cluster client.

## 7. ASK là gì?

`ASK` là redirection **tạm thời**, chủ yếu xuất hiện trong giai đoạn **migrating/importing hash slot** khi Redis Cluster đang chuyển các khóa từ primary nguồn sang primary đích.

Phản hồi minh họa:

```text
-ASK 12182 redis-b:7001
```

Không giống `MOVED`, `ASK` **không khẳng định quyền sở hữu chính thức của cả slot đã chuyển sang node đích**. Nó cho biết **command cụ thể này** cần được gửi tạm sang node đích.

### Trạng thái migrating và importing

Khi reshard một slot từ A sang B:

```text
Primary A: slot đang MIGRATING sang B
Primary B: slot đang IMPORTING từ A

Các key trong slot có thể đang được di chuyển
một phần tại thời điểm chuyển đổi.
```

Trong giai đoạn này, có thể tồn tại key còn ở A và key đã chuyển sang B. Node nguồn có thể trả `ASK` cho các yêu cầu phù hợp để client thử command ở B, trong khi quyền sở hữu chính thức của slot chưa được công bố hoàn toàn chuyển sang B.

### Luồng xử lý ASK và ASKING

```text
Client dùng slot map hiện tại: slot 12182 -> A
       |
       | GET key
       v
       A
       |
       +--> "-ASK 12182 B:7001"
                    |
                    v
           Kết nối đến B
                    |
                    +--> ASKING
                    |      (B cho phép command sau đó
                    |       truy cập slot đang importing)
                    |
                    +--> GET key
                    |
                    v
                Trả kết quả

Slot map dài hạn của client vẫn chưa đổi
chỉ vì nhận một lần ASK.
```

**`ASKING` là một Redis command có ý nghĩa cho yêu cầu tiếp theo trên đúng kết nối phù hợp.** Client cần gửi `ASKING` rồi gửi command được redirect tới node nhập slot theo cách giữ đúng ngữ cảnh kết nối. Không nên chỉ bắt `ASK` rồi gửi `GET` sang node đích từ một connection bất kỳ mà không có `ASKING`.

Sau khi reshard hoàn tất và quyền sở hữu slot chính thức đổi, các node sẽ hướng client theo topology mới, và `MOVED` có thể xuất hiện nếu slot map phía client còn cũ.

## 8. Bảng đối chiếu MOVED và ASK

| Thuộc tính | `MOVED` | `ASK` |
|---|---|---|
| Ý nghĩa | Slot thuộc về node khác | Command này cần xử lý tạm ở node khác |
| Bối cảnh thường gặp | Slot map sai/cũ, đổi ownership, failover | Resharding khi slot migrating/importing |
| Có cập nhật slot map lâu dài chỉ từ redirect? | Có cơ sở cập nhật/làm mới topology | **Không** nên đổi chủ slot lâu dài chỉ từ ASK |
| Request tiếp theo đến đâu? | Node đang sở hữu slot theo topology mới | Command hiện tại đến node được ASK chỉ định |
| Có cần `ASKING` trước command ở đích? | Không vì MOVED | **Có**, theo giao thức ASK |
| Mục tiêu client | Retry ở owner mới và refresh topology | Retry tạm thời với ASKING, tiếp tục theo dõi topology |
| Khi lỗi kéo dài | Kiểm tra slot map/endpoint/redirect loop | Kiểm tra resharding kẹt, importing state và retry |
| Có được xem là command đã thực thi nghiệp vụ? | Redirect báo từ chối định tuyến, không phải kết quả nghiệp vụ thành công | Redirect tạm, cần thực thi lại đúng giao thức |

Một câu dễ nhớ:

> **MOVED: “slot này thuộc nơi khác”. ASK: “với command này, hãy hỏi tạm node kia và nói ASKING trước”.**

Cả hai thường được Redis client hỗ trợ trong mức redirect giới hạn. Ứng dụng Spring Data Redis không cần tự gửi `ASKING` khi Lettuce đang xử lý ASK đúng cách.

## 9. Vì sao ASK không nên làm thay đổi toàn bộ slot map?

Hãy xem ví dụ slot S đang chuyển từ A sang B. Một số key thuộc S vẫn ở A, số khác đã tới B:

```text
Slot S đang MIGRATING A -> B

A: keyX (chưa di chuyển)
B: keyY (đã di chuyển)
```

Nếu client nhận một `ASK` cho `keyY` rồi cập nhật toàn bộ slot S là thuộc B, yêu cầu `keyX` tiếp theo có thể bị gửi nhầm đến B khi key đó vẫn còn ở A.

Vì vậy:

- `ASK` nên được xử lý **theo từng command**.
- Slot map được cập nhật khi topology/ownership thực sự thay đổi, không chỉ vì một ASK riêng lẻ.
- Khi migration hoàn tất, topology discovery sẽ phản ánh chủ slot mới.
- Nếu quá trình di chuyển kéo dài, client có thể gặp nhiều `ASK` mà cluster vẫn chưa chuyển ownership.
- Giám sát thời gian ASK kéo dài giúp phát hiện resharding chưa kết thúc.

## 10. Spring Data Redis và Lettuce xử lý redirect ở tầng nào?

Trong cấu hình phổ biến:

```text
Business Service
        |
        v
StringRedisTemplate / RedisTemplate
        |
        v
LettuceConnectionFactory
        |
        v
Lettuce cluster client
        |
        +--> hash slot lookup
        +--> node routing
        +--> MOVED/ASK redirection
        +--> topology refresh
        +--> connection/retry handling
        |
        v
Redis Cluster
```

`StringRedisTemplate` không cần biết một khóa ở primary A hay primary B. Nó gửi command qua Redis connection abstraction. Phần quản lý topology và redirection nằm chủ yếu ở **driver cluster-aware**.

Khi gặp lỗi:

- Một `MOVED` hợp lệ thường được driver điều hướng lại, không nhất thiết xuất hiện thành exception ở service.
- `ASK` có thể được driver xử lý bằng `ASKING` rồi command trên node đích.
- Nếu vượt giới hạn redirect, endpoint không kết nối được, cluster không khả dụng hoặc driver không có topology hợp lệ, application vẫn có thể nhận lỗi Redis.
- Không nên tự bắt mọi Redis exception rồi parse chuỗi `MOVED`/`ASK` để retry tại tầng nghiệp vụ; làm vậy dễ xung đột với driver và tạo retry lặp.

Điểm phải cấu hình đúng ngay từ đầu là connection factory thực sự được tạo cho **Redis Cluster**, không phải standalone connection factory trỏ đến một node cluster.

## 11. Cấu hình Redis Cluster qua Spring Boot properties

Ví dụ dùng Spring Boot và Lettuce:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-a.internal:7000
          - redis-b.internal:7001
          - redis-c.internal:7002
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
```

Ý nghĩa:

- `cluster.nodes` là danh sách seed endpoints.
- `max-redirects` giới hạn số lần chuyển hướng cluster theo cơ chế hỗ trợ của Spring/driver.
- `connect-timeout` và `timeout` giúp tránh một yêu cầu chờ vô hạn khi mạng/node không đáp ứng.
- Spring Boot và Lettuce dùng topology khám phá được để định tuyến.
- Phải dùng DNS/IP/port thực sự truy cập được từ môi trường chạy ứng dụng.

Các giá trị là ví dụ, cần điều chỉnh theo latency, retry budget, deployment và Spring Boot version. Không tự đặt giới hạn redirect quá lớn để “giải quyết” lỗi topology lâu dài. Một redirect loop có thể biểu thị cấu hình node không nhất quán hoặc reshard/failover đang có vấn đề.

### Có cần liệt kê tất cả primary làm seed không?

Không nhất thiết. Một vài node seed có thể đủ để khám phá cluster nếu chúng truy cập được và cung cấp topology đầy đủ. Tuy nhiên, **nhiều seed tăng cơ hội kết nối ban đầu** khi một seed không khả dụng.

Không cần liệt kê thủ công mọi Redis replica để từng key có đường đi, nhưng nên cấu hình đủ seed endpoints ổn định, DNS và ACL/TLS để client học được topology đúng. Danh sách seed không thay thế refresh khi cluster đổi node.

## 12. Cấu hình Lettuce topology refresh chủ động

Khi topology thay đổi, một bản đồ slot từng đúng có thể trở nên cũ. Lettuce hỗ trợ refresh theo lịch và refresh thích ứng khi gặp tín hiệu cluster thay đổi.

Ví dụ Java cấu hình tường minh, dành cho ứng dụng muốn tự quản lý connection factory thay vì chỉ dùng Boot auto-config:

```java
package example.redis.cluster;

import java.time.Duration;
import java.util.List;

import io.lettuce.core.cluster.ClusterClientOptions;
import io.lettuce.core.cluster.ClusterTopologyRefreshOptions;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisClusterConfigurationExample {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        RedisClusterConfiguration cluster =
                new RedisClusterConfiguration(
                        List.of(
                                "redis-a.internal:7000",
                                "redis-b.internal:7001",
                                "redis-c.internal:7002"));

        cluster.setMaxRedirects(5);

        ClusterTopologyRefreshOptions refreshOptions =
                ClusterTopologyRefreshOptions.builder()
                        .enablePeriodicRefresh(Duration.ofSeconds(30))
                        .enableAllAdaptiveRefreshTriggers()
                        .build();

        ClusterClientOptions clientOptions =
                ClusterClientOptions.builder()
                        .topologyRefreshOptions(refreshOptions)
                        .build();

        LettuceClientConfiguration clientConfiguration =
                LettuceClientConfiguration.builder()
                        .clientOptions(clientOptions)
                        .commandTimeout(Duration.ofSeconds(3))
                        .build();

        return new LettuceConnectionFactory(
                cluster, clientConfiguration);
    }

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory redisConnectionFactory) {
        return new StringRedisTemplate(redisConnectionFactory);
    }
}
```

Ở đây:

1. `RedisClusterConfiguration` khai báo seed nodes và giới hạn redirects.
2. `ClusterTopologyRefreshOptions.enablePeriodicRefresh(...)` yêu cầu Lettuce cập nhật topology định kỳ.
3. `enableAllAdaptiveRefreshTriggers()` bật các nhóm tín hiệu refresh thích ứng mà Lettuce hỗ trợ, chẳng hạn khi phát hiện redirection/topology bất thường.
4. `ClusterClientOptions` gắn options refresh vào cluster client.
5. `LettuceClientConfiguration` thiết lập command timeout.
6. `LettuceConnectionFactory` tạo kết nối theo kiểu cluster.
7. `StringRedisTemplate` sử dụng factory đó ở tầng thao tác Redis.

**Lưu ý:** phiên bản Lettuce/Spring Data Redis có thể cung cấp thêm tùy chọn hoặc thay đổi builder API; hãy đối chiếu dependency được quản lý trong dự án khi áp dụng vào code thật. Cấu hình Java này **không cần triển khai đồng thời** với một bean factory tự động khác nếu sẽ gây trùng bean. Nó cũng chưa có ACL/TLS credentials; production phải cấu hình bảo mật từ môi trường thích hợp.

### Periodic refresh và adaptive refresh khác nhau

| Cách làm mới | Kích hoạt khi nào | Lợi ích |
|---|---|---|
| **Periodic** | Theo chu kỳ định trước | Hạn chế slot map quá cũ khi có thay đổi ít tạo redirect |
| **Adaptive** | Khi có tín hiệu như nhiều redirect hoặc thay đổi topology được driver nhận thấy | Phản ứng nhanh hơn với failover/reshard |
| **Initial discovery** | Khi cluster client bắt đầu hoặc cần topology đầu tiên | Cung cấp slot map để routing ban đầu |
| **MOVED handling** | Khi command được server hướng sang owner mới | Sửa đường đi command hiện tại và gợi ý map cần refresh |
| **ASK handling** | Khi một command cần đi tạm sang node importing | Hoàn thành command trong lúc reshard, không tự đổi ownership toàn slot |

Adaptive refresh thường có giới hạn tần suất/throttle để tránh mọi redirect đều tạo một loạt yêu cầu khám phá topology. Không nên đặt polling quá dày mà chưa đánh giá tải trên các node và số lượng client instances.
## 13. Cấu hình ứng dụng dùng RedisTemplate không cần tự xử lý MOVED/ASK

Với connection factory cluster-aware, service vẫn gọi Redis như bình thường:

```java
package example.redis.cluster;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserStatusService {

    private final StringRedisTemplate redis;

    public UserStatusService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void updateStatus(String userId, String status) {
        redis.opsForValue()
                .set("user:{" + userId + "}:status", status);
    }

    public String readStatus(String userId) {
        return redis.opsForValue()
                .get("user:{" + userId + "}:status");
    }
}
```

Business code không chứa node address, hash slot hay logic parse redirect. Đó là điểm mạnh của cluster-aware client. Nếu thay Redis topology hoặc reshard một số slot, service trên về nguyên tắc không cần sửa.

Tuy nhiên, mã phải tuân theo hợp đồng **serializer và đặt tên key**. Trong ví dụ, hash tag của mỗi user ID giúp các key liên quan tới cùng user có thể cùng slot nếu cần, nhưng chỉ nên áp dụng khi nghiệp vụ có lý do. Không sử dụng một hash tag chung cho tất cả user vì sẽ dồn tải của toàn bộ ứng dụng vào một slot/primary.

### Cluster routing và API reactive

Nếu ứng dụng dùng `ReactiveRedisTemplate`, việc chọn slot và xử lý redirect cũng nằm ở Lettuce cluster client. Khác biệt là kết quả phát qua `Mono`/`Flux`, không phải do caller chờ đồng bộ. Các lỗi vượt qua khả năng routing/retry được báo qua publisher.

Cần giữ pipeline reactive đúng cách; một publisher chưa được subscribe sẽ không tự gửi command chỉ vì service đã tạo nó.

## 14. MOVED/ASK khác CROSSSLOT như thế nào?

Một lỗi rất hay gặp khi chuyển từ standalone sang Redis Cluster là sử dụng lệnh nhiều khóa không thuộc cùng slot.

Ví dụ:

```bash
redis-cli -c -p 7000 MGET user:42:profile user:43:profile
```

Hai khóa có thể thuộc các slot khác nhau. Redis Cluster không thể tự thực hiện một lệnh `MGET` đa slot như một command nguyên tử thông thường, nên có thể báo:

```text
-CROSSSLOT Keys in request don't hash to the same slot
```

**`CROSSSLOT` không phải `MOVED` hoặc `ASK`.** Driver không thể chỉ retry trên node khác để biến một lệnh đa slot không hợp lệ thành hợp lệ.

### Hash tag khi cần lệnh nhiều khóa

Ví dụ cùng một người dùng:

```text
user:{42}:profile
user:{42}:settings
user:{42}:balance
```

Các key này cùng hash tag `{42}`, vì vậy cùng slot. Có thể dùng lệnh nhiều khóa khi Redis command được hỗ trợ và mọi key thuộc cùng slot:

```bash
redis-cli -c -p 7000 CLUSTER KEYSLOT 'user:{42}:profile'
redis-cli -c -p 7000 CLUSTER KEYSLOT 'user:{42}:settings'
```

Lưu ý:

- Hash tag chỉ giải quyết **slot placement**.
- Nó không bảo đảm dữ liệu của nhiều key luôn nhất quán về nghiệp vụ.
- Nó không giải quyết lỗi Redis node, mạng hoặc giao dịch với database khác.
- Nếu cố đặt tất cả key bằng hash tag `{global}`, một slot sẽ trở thành điểm nóng.
- Khi dùng Redis serializer nhị phân, cần biết byte của key thực tế để xác định hash tag có áp dụng đúng không.

Một số API cấp cao có thể chia một thao tác sang nhiều node hoặc chạy nhiều command độc lập khi được hỗ trợ. Không nên suy ra chúng có cùng tính nguyên tử như một lệnh Redis đơn: cần biết rõ contract của API và driver.

## 15. MOVED, ASK và các lỗi Redis Cluster khác

Không phải lỗi cluster nào cũng là redirection. Khi thiết kế handling, cần phân nhóm:

| Lỗi/trạng thái | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `MOVED` | Slot thuộc primary khác so với node đang nhận lệnh | Cluster-aware routing, refresh topology, retry theo driver |
| `ASK` | Chuyển hướng tạm khi slot đang migrating/importing | Gửi `ASKING` rồi command tới target, không đổi slot owner lâu dài |
| `CROSSSLOT` | Một command nhiều key không đáp ứng slot constraint | Thiết kế lại key/tag hoặc tách thao tác; không retry mù |
| `TRYAGAIN` | Trạng thái cluster tạm thời chưa thể xử lý command, có thể trong resharding | Retry có giới hạn/backoff khi phù hợp, kiểm tra reshard |
| `CLUSTERDOWN` | Cluster không thể phục vụ command do trạng thái cluster | Kiểm tra node/slot coverage, failover và hạ tầng |
| `READONLY` | Gửi ghi vào replica/read-only endpoint | Kiểm tra route primary/replica và topology |
| Timeout/mất kết nối | Node không phản hồi, DNS/TLS/mạng lỗi | Phân biệt command chưa gửi và kết quả không chắc chắn |
| `NOAUTH`/`NOPERM` | Authentication hoặc ACL không phù hợp | Sửa credentials/permissions, không retry chuyển hướng |
| Redirect quá nhiều lần | Slot map dao động, node không đồng thuận hoặc max redirects quá thấp | Quan sát topology/failover, không chỉ tăng limit vô hạn |

Trong Redis Cluster đang reshard, một số lệnh đa key trên cùng slot có thể gặp `TRYAGAIN` nếu các key tạm thời nằm ở các pha di chuyển khác nhau. Đây không giống `CROSSSLOT`: ở `TRYAGAIN`, slot có thể hợp lệ nhưng trạng thái tạm thời khiến command chưa thể hoàn tất.

### Không phân loại mọi lỗi là “retry được”

Một exception do schema/serializer sai, ACL thiếu quyền hoặc `CROSSSLOT` không tự biến mất nhờ retry nhiều lần. Retry không phân loại lỗi sẽ gây tải thêm đúng lúc cluster đang gặp sự cố.

Cần biết lỗi là **routing transient**, **hạ tầng tạm thời** hay **lỗi thiết kế/configuration** để chọn phản ứng phù hợp.

## 16. Khi failover xảy ra, topology đổi như thế nào?

Redis Cluster có thể chuyển vai trò primary cho một replica trong trường hợp failover. Ví dụ:

```text
Trước failover:
  Primary A -> slot S
  Replica A1 -> sao chép A

Sau failover:
  A1 được bầu làm primary mới cho slot S
  A có thể không khả dụng hoặc tham gia lại với vai trò khác
```

Client vẫn đang tin rằng slot S thuộc endpoint A có thể gặp:

- Lỗi kết nối đến A.
- `MOVED` từ node biết topology mới.
- Kết quả cluster topology refresh cho biết A1 là owner mới.
- Một khoảng thời gian command thất bại trong lúc failover.

Lettuce cluster-aware client được thiết kế để theo dõi routing/topology, nhưng **không thể bảo đảm mọi command trong thời điểm failover đều thành công**. Ứng dụng cần có timeout, retry budget và cách xử lý kết quả không chắc chắn.

### Failover không tạo consistency mạnh mặc định

Redis Cluster thường sao chép dữ liệu từ primary sang replica **bất đồng bộ**. Nếu primary gặp sự cố trước khi một write vừa được xác nhận kịp sao chép, vẫn có thể có rủi ro mất dữ liệu gần thời điểm failover theo mô hình durability/consistency thực tế.

Vì vậy, “client đã xử lý MOVED thành công” không đồng nghĩa “mọi write trước failover được bảo toàn”. Đây là hai khía cạnh khác nhau: **routing** và **durability**.

Nếu Redis giữ dữ liệu nghiệp vụ quan trọng, cần đánh giá replication, persistence, backup và cơ chế xác nhận theo yêu cầu; không dựa riêng vào redirect handling.

## 17. Đọc từ Redis replica và hậu quả với tính mới

Đường ghi Redis Cluster thường phải đến primary chịu trách nhiệm slot. Một số ứng dụng cấu hình Lettuce cho phép **đọc từ replica** để phân tán tải.

Ví dụ một tùy chọn client, dùng khi đã hiểu consistency tradeoff:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration clientConfiguration =
        LettuceClientConfiguration.builder()
                .readFrom(ReadFrom.REPLICA_PREFERRED)
                .build();
```

Khi chọn đọc replica:

- Read có thể lấy **bản cũ** do replication lag.
- Failover có thể làm replica/primary role đổi.
- Không thể giả định read-your-writes chỉ vì client vừa ghi primary.
- Routing phải dựa trên topology mới và driver support đúng chế độ đọc.
- Không nên dùng replica read cho quyết định nghiệp vụ yêu cầu xác nhận trạng thái mới nhất mà chưa có bảo đảm bổ sung.

Việc tùy biến read preference trên một `LettuceClientConfiguration` phải kết hợp với cấu hình cluster phù hợp. Đây là ví dụ minh họa option, không phải khuyến nghị đọc replica cho mọi ứng dụng.

## 18. Địa chỉ node được Redis quảng bá có phải luôn truy cập được?

Một trong những sự cố Redis Cluster khó nhận diện nhất xuất hiện trong Kubernetes, Docker, NAT hoặc giữa các mạng VPC.

Giả sử application kết nối seed endpoint:

```text
redis-gateway.example.internal:7000
```

Nhưng khi hỏi topology, Redis trả địa chỉ của các node:

```text
10.1.0.8:7000
10.1.0.9:7001
10.1.0.10:7002
```

Nếu application chạy ngoài mạng chứa `10.1.0.0/16`, những địa chỉ đó có thể không truy cập được. Cluster discovery thành công về mặt trả dữ liệu nhưng command tới slot owner lại thất bại.

Các triệu chứng:

- Kết nối được seed nhưng `GET` một số key lại timeout.
- `CLUSTER NODES`/`CLUSTER SHARDS` hiện hostname/IP khác với những endpoint service có thể truy cập.
- Số lỗi tăng khi command đi sang slot ở node khác.
- Một số application instance trong mạng nội bộ hoạt động tốt, instance từ mạng khác bị lỗi.
- TLS hostname verification không khớp địa chỉ được Redis quảng bá.

Các hướng xử lý vận hành:

1. Bảo đảm endpoint Redis công bố trong topology có thể kết nối từ mọi client cluster cần phục vụ.
2. Xác định chính xác DNS, NAT, service discovery và cluster announce settings của Redis/server.
3. Đối chiếu TLS certificate và hostname được client sử dụng.
4. Với managed Redis, tuân theo hướng dẫn endpoint/discovery của nhà cung cấp.
5. Tránh biến một node đơn lẻ thành proxy không biết định tuyến rồi mong driver tự xử lý mọi địa chỉ NAT sai.

Redis có các thiết lập quảng bá địa chỉ/port cluster ở cấp server. Không nên thay đổi tùy tiện trên production chỉ vì thấy một `MOVED`: hãy kiểm tra toàn bộ mô hình mạng trước.

### Client port và cluster bus port

Redis Cluster còn dùng một kênh **cluster bus** để các node trao đổi trạng thái cluster. Cổng bus thường là một cổng khác với cổng client, trong triển khai mặc định truyền thống có thể theo quy tắc offset. Nhưng **application Redis client không gửi GET/SET qua cluster bus port**.

Cần phân biệt:

- Cổng client dùng cho RESP commands.
- Cổng cluster bus phục vụ giao tiếp giữa các Redis nodes.
- Endpoint quảng bá cho client phải trỏ đúng cổng phục vụ Redis commands.

Mở nhầm cluster bus port cho Spring application sẽ không giải quyết MOVED/ASK.

## 19. Retry an toàn khi có chuyển hướng và mất kết nối

Một nguyên tắc quan trọng là phân biệt **redirect response rõ ràng** với **timeout không xác định trạng thái thực thi**.

### 19.1. Redirect response

Nếu Redis trả `MOVED` hoặc `ASK` thay vì thực thi command nghiệp vụ trên node không phù hợp, driver có thể thực hiện lại command theo redirect protocol. Đây là chức năng bình thường của cluster-aware client.

Tuy vậy, giới hạn số lần redirect và endpoint có thể gây lỗi cuối cùng. Ứng dụng thường nên cho client xử lý routing thay vì tự tạo một lớp retry “thêm ba lần” cho mọi exception.

### 19.2. Mất phản hồi sau khi command đã gửi

Giả sử:

```text
App -> Redis primary: INCR billing:counter
Redis: INCR thành công
Mạng: mất phản hồi trước khi app nhận
App: timeout, không biết kết quả
```

Nếu ứng dụng retry `INCR` mà không có cơ chế idempotency, counter có thể bị tăng hai lần.

| Command | Retry sau timeout | Ghi chú |
|---|---|---|
| `GET` | Thường ít rủi ro side effect | Có thể nhận giá trị mới hơn ở lần retry |
| `SET key value` | Tùy hợp đồng | Ghi cùng giá trị có thể lặp, nhưng TTL/version có thể thay đổi |
| `DEL` | Thường idempotent về trạng thái cuối | Kết quả số key đã xóa có thể khác |
| `INCR`/`DECR` | Không retry mù quáng | Có thể gây thực thi lặp |
| `LPUSH`/`XADD` | Không retry mù quáng | Có thể tạo entry trùng |
| Lua với side effect | Tùy thiết kế | Atomicity không tự bảo đảm idempotency |

Cần giới hạn số lần retry, backoff phù hợp, timeout tổng thể và cơ chế nhận diện thao tác đã thực hiện khi nghiệp vụ có side effect.

### Không dùng MOVED như một lý do để bỏ qua lỗi

Nếu command vẫn thất bại sau khi Lettuce xử lý redirect, cần lưu lỗi gốc, hostname, slot/namespace (nếu có) và topology state. Không biến mọi exception thành cache miss hoặc một giá trị mặc định mà không có telemetry.

## 20. Lab: quan sát MOVED bằng redis-cli

Dùng một **Redis Cluster thử nghiệm** có nhiều primary đang hoạt động. Các cổng và hostname sau đây chỉ là ví dụ; thay cho môi trường lab của bạn.

### Bước 1 — Khám phá topology

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER INFO
redis-cli -h 127.0.0.1 -p 7000 CLUSTER NODES
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SLOTS
```

Nếu Redis version hỗ trợ:

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER SHARDS
```

Xác định slot ranges mà từng primary sở hữu.

### Bước 2 — Tính hash slot của một khóa

```bash
redis-cli -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'course:redis:352'
```

So sánh kết quả với ranges ở bước 1 để xác định owner.

### Bước 3 — Gửi command đến một node không sở hữu slot

Chọn một node thử nghiệm **không sở hữu slot** của `course:redis:352`, rồi chạy không có `-c`:

```bash
redis-cli -h 127.0.0.1 -p 7000 GET 'course:redis:352'
```

Nếu node 7000 không sở hữu slot, Redis có thể trả:

```text
(error) MOVED <slot> <owner-host>:<owner-port>
```

`<slot>` và `<owner-host>` trong ví dụ là ký hiệu giải thích, không phải output literal.

Nếu node 7000 đã sở hữu slot thì lệnh có thể trả giá trị hoặc nil và **không có MOVED**. Muốn quan sát MOVED, hãy chọn đúng node khác owner theo topology.

### Bước 4 — Để redis-cli tự chuyển hướng

```bash
redis-cli -c -h 127.0.0.1 -p 7000 SET 'course:redis:352' 'ready'
redis-cli -c -h 127.0.0.1 -p 7000 GET 'course:redis:352'
```

Tùy trạng thái slot, CLI có thể hiển thị thông báo chuyển hướng và tự kết nối đến owner mới. Tùy chọn `-c` bật cluster mode giúp redis-cli tự theo redirect, bao gồm cách xử lý ASK phù hợp.

Kết quả này minh họa giao thức server; ở ứng dụng Spring Data Redis, Lettuce thường thực hiện tương tự ở tầng driver mà business service không thấy từng bước.

### Bước 5 — Kiểm tra các key cùng hash tag

```bash
redis-cli -c -p 7000 CLUSTER KEYSLOT 'cart:{lab-user}:items'
redis-cli -c -p 7000 CLUSTER KEYSLOT 'cart:{lab-user}:total'
```

Hai kết quả phải giống nhau. Thử `MGET` với hai key cùng hash tag sau khi đã tạo giá trị, rồi so sánh với các key không có hash tag chung để hiểu `CROSSSLOT`.

## 21. Lab: quan sát ASK trong khi resharding

`ASK` thường chỉ xuất hiện trong một **khoảng thời gian chuyển slot**, nên khó quan sát hơn `MOVED` khi cluster đã ổn định.

Quy trình quan sát ở **cluster lab riêng biệt**:

1. Tạo Redis Cluster nhiều primary, có một số key trong slot S.
2. Ghi nhận owner hiện tại của slot S bằng `CLUSTER SLOTS`/`CLUSTER SHARDS`.
3. Sử dụng công cụ quản trị cluster để reshard slot S từ primary A sang primary B.
4. Trong lúc slot đang ở trạng thái migrating/importing, gửi lệnh tới key trong slot S.
5. Quan sát có `ASK S B:port` hay không, tùy key đã/chưa được di chuyển và thời điểm command.
6. Dùng `redis-cli -c` để quan sát client tự theo redirect.
7. Sau khi reshard xong, kiểm tra owner mới của slot và quan sát `MOVED` từ client đang dùng topology cũ.

Vì khoảng ASK thường ngắn, không phải mọi lần thử đều nhìn thấy nó. Một lần không thấy ASK **không có nghĩa hệ thống sai**.

Không thực hiện thử nghiệm reshard chủ động trên Redis Cluster production chỉ để quan sát lỗi. Thao tác chuyển slot có thể ảnh hưởng routing, latency và dữ liệu đang được các ứng dụng sử dụng.

### Vì sao không đưa hai lệnh ASKING và GET thành hai redis-cli command rời?

`ASKING` phải được gắn đúng với command chuyển hướng **trên cùng connection**. Nếu chạy hai tiến trình `redis-cli` độc lập, mỗi lệnh có thể dùng TCP connection khác, khiến trạng thái ASKING không áp dụng như mong muốn.

Để quan sát ở cấp giao thức, dùng một phiên interactive connection hoặc để cluster-aware client như `redis-cli -c`/Lettuce thực hiện đúng chuỗi `ASKING` rồi command.

## 22. Kiểm thử tích hợp Spring Data Redis với cluster thật

Một phép thử chỉ dùng mock `StringRedisTemplate` không xác nhận được driver tính slot và xử lý MOVED/ASK. Cần có **cluster lab** riêng, có seed nodes, slot ranges và DNS mạng tương tự môi trường triển khai.

Ví dụ service đơn giản để kiểm chứng đường đọc/ghi:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ClusterProbeService {

    private final StringRedisTemplate redis;

    public ClusterProbeService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String putAndGet(String key, String value) {
        redis.opsForValue().set(key, value);
        return redis.opsForValue().get(key);
    }
}
```

Một integration test có thể gọi `putAndGet` trên nhiều key có slot khác nhau để xác minh driver routing, rồi chủ động tạo topology change trong cluster test environment và tiếp tục đọc/ghi.

Các tình huống cần quan sát:

- Kết nối từ một seed node nhưng thao tác khóa trên các primary khác.
- Slot map ban đầu có đủ dải 0..16383 không.
- Một node seed không khả dụng khi app khởi động.
- Cluster reshard gây MOVED/ASK và client vẫn đọc đúng.
- Thay primary bằng failover và theo dõi error/recovery.
- Redirect vượt giới hạn hoặc node đích không truy cập được.
- Sử dụng một multi-key command có các key khác slot để phân biệt CROSSSLOT.
- Endpoint được Redis quảng bá không thể kết nối từ test client.
- Đọc replica có thể thấy version cũ khi đã bật read preference.
- Timeout xảy ra sau một write có side effect và cách retry được bảo vệ.

Không cần đặt assert “zero error trong mọi mili giây failover” khi hạ tầng Redis không cung cấp bảo đảm đó. Nên kiểm chứng **thời gian phục hồi**, giới hạn lỗi và tính đúng của nghiệp vụ sau khi cluster ổn định.

## 23. Các chỉ số nên giám sát khi vận hành topology

Một ứng dụng chỉ ghi log “Redis connection failed” khó giúp phân biệt lỗi slot map, lỗi mạng và lỗi reshard.

| Tín hiệu | Điều cần điều tra |
|---|---|
| Số lần `MOVED` | Slot map lỗi thời, ownership thay đổi hoặc client không cluster-aware |
| Số lần `ASK` | Resharding đang diễn ra; nếu kéo dài có thể đang kẹt |
| Topology refresh count/duration | Driver cập nhật map có nhanh và thành công không |
| Redirect retries/exhausted | Redirect loop, node unreachable hoặc max redirects |
| Redis command timeout | Mạng, node overload, latency hoặc routing không thành công |
| Redis failover events | Primary đổi vai trò, kết nối và tính sẵn sàng |
| `CLUSTERDOWN`/`TRYAGAIN` | Khả năng phục vụ slot và trạng thái chuyển cluster |
| `CROSSSLOT` errors | Mẫu key/multi-key command không phù hợp |
| Endpoint connection failures | DNS, NAT, TLS, ACL hoặc announce address sai |
| Redis command latency p95/p99 | Độ trễ người dùng nhận được qua các node |
| Read-from-replica lag | Rủi ro trả dữ liệu cũ |
| Node CPU/memory/slot distribution | Tải lệch, hot slots/hot keys, reshard pressure |

Không phải mọi driver đều xuất sẵn một metric có tên “MOVED count”. Có thể cần cấu hình logs, Lettuce metrics/tracing hoặc ứng dụng quan sát lỗi đã phân loại. Tránh log mọi redirect ở mức quá chi tiết trong production vì có thể làm log flood trong thời gian resharding.

## 24. Chẩn đoán theo triệu chứng

### 24.1. GET một số key chạy, key khác timeout

Khả năng lớn là chỉ một số slot định tuyến đến node/endpoint không thể truy cập. Kiểm tra:

1. `CLUSTER KEYSLOT` của key lỗi.
2. Slot owner trong `CLUSTER SHARDS` hoặc `CLUSTER SLOTS`.
3. Host/port được quảng bá có kết nối được từ application không.
4. DNS/TLS/ACL của node đó.
5. Lettuce đã khám phá topology và có retry/refresh phù hợp chưa.

Không suy ra toàn cluster đã chết chỉ vì một phần key bị lỗi.

### 24.2. Application thấy MOVED liên tục

Kiểm tra factory có thực sự cluster-aware không, topology refresh có hoạt động, Redis đang reshard/failover, endpoint có thể truy cập và slot map có dao động hay không.

Nếu ứng dụng kết nối cluster bằng standalone factory, có thể phải theo redirect nhiều lần hoặc báo lỗi. **Sửa connection topology**, không chỉ tăng max redirects.

### 24.3. ASK kéo dài lâu bất thường

Kiểm tra slot migrating/importing có hoàn tất không. Một resharding kẹt có thể khiến nhiều command phải được điều hướng tạm thời. Xác nhận trạng thái bằng các lệnh cluster quản trị từ hạ tầng, giám sát quá trình migration và tác động lên latency.

Không tự sửa `CLUSTER SETSLOT` trên production nếu chưa có kế hoạch/ownership rõ ràng.

### 24.4. Spring Data Redis báo CROSSSLOT

Kiểm tra tất cả Redis key thực sự tham gia command, bao gồm key do Repository/index/metadata hoặc Lua script sử dụng. Đặt hash tag có chủ đích khi cần nhiều key cùng slot hoặc tách operation theo ngữ nghĩa phù hợp. Retry redirect không sửa lỗi CROSSSLOT.

### 24.5. Failover xong vẫn kết nối primary cũ

Kiểm tra topology refresh, DNS, driver version, node role mới, Redis Cluster announce endpoints và cách application chọn read/write node. Nếu dùng read preference tới replica, cần phân biệt cache cũ với primary ownership sai.

### 24.6. Redis CLI -c chạy, ứng dụng Spring lỗi

Khả năng gồm:

- CLI và ứng dụng dùng DNS/network namespace khác.
- CLI dùng TLS/auth khác.
- Spring cấu hình standalone thay vì cluster.
- Serializer của key trong Spring khác chuỗi gõ ở CLI.
- Spring dùng một Redis database/index không phù hợp (Redis Cluster thông thường dùng database 0).
- Driver Lettuce/Spring Data version hoặc client options khác.
- Application giữ topology cũ vì không refresh hoặc không nhận được node endpoints.

Cần so sánh **cùng key byte, cùng topology, cùng security context** thay vì chỉ kết luận vì CLI thành công thì Java phải thành công.

## 25. Những nhầm lẫn phổ biến

**“MOVED nghĩa là Redis đã mất key.”** Không. MOVED là chỉ dẫn định tuyến slot đến node khác; không tự nói key có tồn tại hay không.

**“ASK giống MOVED, cứ cập nhật slot map là được.”** Sai. ASK là chuyển hướng tạm thời trong resharding, cần `ASKING` trên target cho command đó; không đánh đồng với quyền sở hữu slot lâu dài.

**“Lettuce đã có seed nên không cần topology refresh.”** Seed chỉ hỗ trợ khám phá ban đầu. Slot ownership có thể đổi sau failover/resharding.

**“MOVED và ASK luôn phải được xử lý trong code service.”** Không khi sử dụng cluster-aware Lettuce đúng cấu hình. Driver thường tự xử lý; service nên tập trung nghiệp vụ và lỗi còn lại.

**“CROSSSLOT là MOVED đặc biệt.”** Không. CROSSSLOT phản ánh lệnh nhiều key không phù hợp với phân vùng slot. Nó không có target node duy nhất để redirect một cách nguyên tử.

**“Dùng hash tag giống nhau cho mọi key sẽ đơn giản nhất.”** Nó dồn toàn bộ key lên một slot, làm giảm hiệu quả phân tán và tạo hot spot.

**“Failover với MOVED được xử lý nghĩa là không mất write nào.”** Không. Redis Cluster có replication/failover semantics riêng, thường có rủi ro dữ liệu gần thời điểm primary lỗi nếu chưa được sao chép bền vững.

**“Client timeout nên retry INCR an toàn.”** Không. Redis có thể đã thực thi INCR trước khi phản hồi mất; retry có thể tăng hai lần.

**“Kết nối tới một endpoint seed thành công nghĩa là mọi node đều truy cập được.”** Không. Endpoint topology quảng bá có thể nằm sau NAT, mạng riêng hoặc hostname không được ứng dụng resolve.

## 26. Câu hỏi tự đánh giá

**1. Vì sao Redis Cluster dùng slot map thay vì chỉ kết nối một host?**

Vì Redis Cluster phân bố khóa vào 16.384 slot, các slot thuộc những primary khác nhau; client cần định tuyến mỗi command tới node phù hợp.

**2. MOVED báo điều gì?**

Node đang nhận command cho rằng slot thuộc một node khác. Client nên chuyển lệnh và làm mới bản đồ topology theo cơ chế cluster-aware.

**3. ASK xuất hiện chủ yếu trong giai đoạn nào?**

Khi Redis Cluster đang migrating/importing slot trong resharding, một command có thể phải được xử lý tạm trên node nhận dữ liệu.

**4. ASK cần lệnh gì trước command ở node đích?**

`ASKING`, trên cùng connection phù hợp, ngay trước command được chuyển hướng.

**5. Có nên cập nhật vĩnh viễn owner của toàn slot sau một ASK không?**

Không. ASK là chuyển hướng tạm thời theo command; slot map dài hạn chỉ nên cập nhật khi ownership/topology đã thay đổi.

**6. Vì sao hai key khác hash slot không được ghép vào mọi multi-key command?**

Redis Cluster có giới hạn các command nhiều key theo hash slot. Một lệnh như `MGET` khác slot có thể báo `CROSSSLOT`.

**7. Hash tag giúp gì?**

Các key có cùng nội dung tag hợp lệ giữa ngoặc nhọn được tính cùng slot, hữu ích cho multi-key operations trong phạm vi một entity.

**8. Vì sao MOVED có thể xảy ra ngay cả khi Redis Cluster đang `cluster_state:ok`?**

Client có thể đang dùng slot map cũ sau reshard/failover, hoặc gửi command tới một seed không sở hữu slot.

**9. Vì sao Redis CLI chạy được nhưng Spring vẫn lỗi?**

Có thể khác client mode, endpoint, mạng, TLS/ACL, serialization hoặc topology refresh.

**10. Có nên retry mọi timeout sau failover không?**

Không. Với write có side effect như `INCR`, command có thể đã thực thi nhưng caller mất phản hồi; cần idempotency và chính sách retry phù hợp.

## 27. Ghi nhớ khi triển khai

- Redis Cluster định tuyến theo **16.384 hash slot**; client cluster-aware duy trì ánh xạ slot → primary.
- Seed nodes dùng để **khám phá topology**, không phải nơi nhận mọi command.
- `MOVED` báo slot thuộc node khác; client cần chuyển hướng và xem lại topology.
- `ASK` là redirect **tạm thời** trong resharding; cần `ASKING` trước command trên node đích và không tự đổi owner toàn slot.
- Spring Data Redis với Lettuce cluster-aware thường xử lý redirects ở tầng driver; business service không nên tự parse response để route.
- Cấu hình topology refresh định kỳ/thích ứng để hạn chế slot map lỗi thời; theo dõi redirect loops và endpoint connectivity.
- `CROSSSLOT` không phải lỗi redirect; multi-key commands cần đáp ứng slot constraints, có thể thiết kế hash tags hợp lý.
- Redis Cluster failover không loại bỏ rủi ro lỗi command, timeout hoặc mất write theo replication semantics.
- Retry phải phân biệt redirect có phản hồi và **timeout không rõ lệnh đã chạy chưa**.
- Dùng Redis CLI `CLUSTER INFO`, `CLUSTER SHARDS`/`SLOTS`, `CLUSTER KEYSLOT` và `redis-cli -c` để chẩn đoán ở môi trường thích hợp.
- Trong Kubernetes/NAT/TLS, kiểm tra **node endpoints được Redis quảng bá** có thực sự truy cập được từ các application instances.
- Không dùng một hash tag chung cho tất cả key, không sửa slot ownership trên production khi chưa có kế hoạch điều phối.

Một mô hình tư duy hữu ích là: **slot map quyết định nơi gửi lệnh, MOVED cập nhật nhận thức về chủ slot, ASK giải quyết command trong lúc slot đang di chuyển**. Khi ba khía cạnh này được phân biệt rõ, việc cấu hình Lettuce, đọc log và khôi phục sau reshard/failover sẽ ít nhầm lẫn hơn nhiều.

## Tài liệu tham khảo

- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): kết nối Redis Cluster, RedisClusterConfiguration và Spring Data Redis operations.
- [Spring Data Redis — LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html): connection factory cho standalone/Sentinel/Cluster.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): thao tác Redis thông qua template.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, hash tags, MOVED, ASK, ASKING, migration và failover.
- [Redis — Redis Cluster Tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/): cấu hình và vận hành cluster.
- [Redis — CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/): thông tin shard/slot/node.
- [Redis — CLUSTER SLOTS](https://redis.io/docs/latest/commands/cluster-slots/): ánh xạ slot range tới endpoint.
- [Redis — CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/): xác định slot cho một key.
- [Redis — ASKING](https://redis.io/docs/latest/commands/asking/): giao thức ASK redirect khi slot importing.
- [Redis — CLUSTER NODES](https://redis.io/docs/latest/commands/cluster-nodes/): node ID, role và slot ranges.
- [Lettuce — Redis Cluster](https://redis.github.io/lettuce/ha-sharding/): cluster client, routing và topology refresh.

