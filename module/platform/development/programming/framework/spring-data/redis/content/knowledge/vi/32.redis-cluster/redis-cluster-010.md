# Phân biệt phân mảnh dữ liệu với sao chép và failover trong Redis Cluster

## 1. Vì sao phải phân biệt ba cơ chế?

Một hệ thống Spring Boot dùng Redis để lưu session, cache sản phẩm, giỏ hàng hoặc bộ đếm có thể cần vừa **mở rộng dữ liệu**, vừa **phục vụ khi một node gặp lỗi**, vừa **giảm thời gian gián đoạn**. Trong Redis Cluster, ba nhu cầu này được giải quyết bằng ba cơ chế liên quan nhưng khác bản chất:

1. **Phân mảnh dữ liệu (sharding/partitioning):** phân phối các key Redis lên nhiều **primary/master nodes**. Mục đích chủ yếu là mở rộng dung lượng và tải.
2. **Sao chép dữ liệu (replication):** mỗi primary có thể có một hoặc nhiều **replicas** giữ bản sao dữ liệu của chính primary đó. Mục đích là dự phòng và có thể hỗ trợ các trường hợp đọc từ replica.
3. **Failover:** khi primary không còn khả dụng, Redis Cluster có thể **promote một replica phù hợp** lên primary, chuyển trách nhiệm xử lý các hash slots mà primary cũ quản lý.

Ví dụ một cluster có ba primary và ba replicas:

```text
                              SPRING BOOT
                                  |
                         Lettuce Cluster client
                                  |
                 +----------------+----------------+
                 |                |                |
                 v                v                v
             Primary A        Primary B        Primary C
             slots A          slots B          slots C
                 |                |                |
          replication       replication       replication
                 |                |                |
                 v                v                v
             Replica A1       Replica B1       Replica C1
```

**Primary A và Primary B không giữ cùng một nửa dữ liệu**, vì chúng phụ trách các slot khác nhau. **Replica A1 mới sao chép dữ liệu của Primary A**, không phải dữ liệu của toàn cluster.

Khi Primary B mất, Replica B1 có thể được chọn thay thế và tiếp quản **slots B**. Việc này là **failover**, không phải **resharding**.

> Nguyên tắc ghi nhớ: **Sharding chia dữ liệu; replication nhân bản dữ liệu; failover đổi người giữ vai trò chính khi gặp sự cố.** Ba cơ chế hỗ trợ nhau nhưng không thay thế nhau.

## 2. Redis Cluster là gì?

Redis Cluster là chế độ triển khai nhiều Redis nodes, trong đó dữ liệu được phân phối theo **16.384 hash slots**, đánh số từ `0` đến `16383`. Cluster duy trì thông tin node nào chịu trách nhiệm cho từng slot.

Một key có slot được tính theo công thức khái niệm:

```text
slot(key) = CRC16(key) mod 16384
```

Khi key có **hash tag hợp lệ** trong cặp ngoặc nhọn, phần bên trong hash tag được dùng để tính slot thay vì toàn bộ key.

Ví dụ:

```text
user:42:profile       -> một slot xác định
product:100:stock     -> có thể thuộc slot khác
cart:{user-42}:items  -> slot của "user-42"
cart:{user-42}:total  -> cùng slot của "user-42"
```

Redis Cluster không cần mọi node giữ tất cả 16.384 slots. Các slot được **phân chia quyền sở hữu** giữa các primary đang hoạt động.

Ví dụ minh họa:

| Node | Vai trò | Khoảng slot |
| --- | --- | --- |
| Primary A | Ghi/đọc slot A | `0–5460` |
| Primary B | Ghi/đọc slot B | `5461–10922` |
| Primary C | Ghi/đọc slot C | `10923–16383` |
| Replica A1 | Bản sao A | Theo Primary A |
| Replica B1 | Bản sao B | Theo Primary B |
| Replica C1 | Bản sao C | Theo Primary C |

Các khoảng trong bảng chỉ là một cấu hình phân phối minh họa, không phải yêu cầu phải chia đều tuyệt đối. Khi cluster thay đổi số lượng primary hoặc phân bố tải, có thể di chuyển slot sang primary khác.

### Redis Cluster khác một Redis server lớn ở đâu?

Một server đơn có giới hạn RAM, CPU, network và các loại tải tương ứng. Redis Cluster cho phép nhiều primary xử lý những tập key khác nhau; việc thêm shard có thể mở rộng tổng dung lượng/tải.

Nhưng sharding cũng mang đến chi phí kiến trúc:

- Client phải biết một key thuộc node nào.
- Multi-key operations có thể bị hạn chế bởi slot.
- Giao dịch hoặc Lua script truy cập nhiều key chịu ràng buộc đồng slot.
- Khi di chuyển slot, client phải xử lý redirect.
- Cần vận hành topology, replication, failover và các failure domains.

Không nên bật Redis Cluster chỉ vì muốn HA cho một tập dữ liệu nhỏ. Redis primary–replica với Sentinel là một lựa chọn khác khi không cần chia dữ liệu theo slot.

## 3. Sharding: phân mảnh dữ liệu theo hash slots

**Sharding** giải quyết câu hỏi: **key này được lưu và xử lý ở đâu?**

Giả sử có 30 triệu key cache. Thay vì đặt tất cả trên một Redis primary, cluster phân phối chúng lên ba primary khác nhau:

```text
                      Redis keyspace
                            |
               CRC16 + hash slot mapping
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
          Primary A     Primary B     Primary C
         một nhóm key  một nhóm key  một nhóm key
```

Mỗi primary quản lý **một phần** dữ liệu. Các primary không mặc định sao chép toàn bộ key của nhau. Khi thêm Primary D và chuyển một số slot từ A/B/C sang D, dữ liệu được **tái phân phối**.

### Sharding mở rộng được những gì?

- **Bộ nhớ:** key/value được lưu trên nhiều primary nên tổng dung lượng có thể tăng.
- **Thông lượng:** các primary xử lý command ở những slot khác nhau.
- **Tải network:** dữ liệu có thể được phân tán giữa nhiều node.
- **Độ lớn dataset:** có thể vượt khả năng lưu trên một Redis node đơn lẻ, miễn là từng shard còn đủ tài nguyên.

Nhưng sharding không tự:

- Tạo bản sao dự phòng.
- Bảo đảm node lỗi vẫn có dữ liệu.
- Thực hiện failover.
- Cho phép giao dịch nguyên tử xuyên nhiều slot.
- Ngăn tất cả hotspot; một key cực nóng vẫn thuộc một slot.

Một cluster có ba primary **không có replicas** vẫn có sharding, nhưng khi một primary lỗi, các slot của nó có thể không khả dụng. Vì vậy “đã chia thành nhiều shard” không đồng nghĩa “đã có HA”.

## 4. Replication: sao chép dữ liệu trong một shard

**Replication** giải quyết câu hỏi: **nếu primary đang giữ key bị mất, có bản sao nào của dữ liệu đó không?**

Trong mô hình một shard:

```text
Primary B (slots 5461–10922)
          |
          | replication
          |
          +------> Replica B1
          |
          +------> Replica B2
```

Replica B1/B2 sao chép dữ liệu của **Primary B**, không sao chép dữ liệu Primary A và C.

Nếu primary nhận lệnh:

```redis
SET product:42:price 120000
```

và key thuộc slots B, write sẽ được primary B xử lý rồi truyền thay đổi đến replicas của B theo cơ chế replication.

### Replication có phải sao chép đồng bộ không?

Redis replication thông thường **bất đồng bộ**. Primary có thể trả kết quả thành công cho client trước khi một replica cụ thể nhận và áp dụng đầy đủ write đó.

Timeline:

```text
T0   Client -> Primary B: SET key=value
T1   Primary B thực hiện write
T2   Primary B trả OK
T3   Replication stream truyền write đến Replica B1
T4   Replica B1 áp dụng write
```

Từ T2 đến T4, replica có thể còn giá trị cũ. Độ trễ phụ thuộc network, tải, replication state và những sự cố có thể xảy ra.

**Replication là cơ chế tạo bản sao, không phải lời hứa rằng mọi write đã được ACK trên primary sẽ luôn tồn tại sau failover.**

### Có thể đọc replica không?

Một số client như Lettuce hỗ trợ lựa chọn đọc từ replica theo cấu hình. Điều này có thể giảm tải đọc trên primary, nhưng phải chấp nhận **eventual consistency** và nguy cơ không thấy write vừa thực hiện.

Ví dụ khi update sản phẩm:

```text
Client ghi price=120000 lên Primary B
Client đọc ngay Replica B1
Replica chưa đồng bộ -> trả price=100000
```

Với dashboard hoặc cache ít quan trọng, độ trễ nhỏ có thể được chấp nhận. Với kiểm tra số dư, tồn kho hay xác nhận thanh toán, phải chọn nguồn đọc có thẩm quyền và chính sách nhất quán phù hợp.

## 5. Failover: đổi primary để phục hồi khả năng phục vụ

**Failover** giải quyết câu hỏi: **ai tiếp quản trách nhiệm xử lý slot khi primary hiện tại mất khả dụng?**

Giả sử Primary B lỗi, còn Replica B1 vẫn khả dụng:

```text
Trước sự cố:

Primary B (slots B) ----replication----> Replica B1


Sau khi cluster xác nhận lỗi và failover:

Primary B (offline)

Replica B1 ----------------------------> Primary mới (slots B)
```

Ở tình huống này:

- Không cần tính lại slot của tất cả key.
- Không cần chuyển slots B sang Primary A hoặc C để giữ nguyên partition.
- Replica B1 được **promote** thành primary và tiếp quản các slots B.
- Client phải cập nhật nhận thức topology và kết nối tới primary mới.

Đó là failover; việc phân phối slot **về mặt logic vẫn có cùng nhóm slots** nhưng node sở hữu đã thay đổi.

### Failover có chắc chắn xảy ra không?

Không. Redis Cluster chỉ có thể tự động failover khi đáp ứng các điều kiện về cluster state, network, replica eligibility và khả năng đạt sự đồng thuận cần thiết giữa các primary còn hoạt động.

Ví dụ:

- Primary B lỗi nhưng replica B1 vẫn hoạt động và đủ điều kiện: có thể failover thành công.
- Primary B và toàn bộ replicas của B đều lỗi: không có bản sao sẵn sàng để promote.
- Cluster bị chia mạng nghiêm trọng, không đủ primary để hình thành majority cần thiết: tự động failover có thể không thực hiện được.
- Replica quá lạc hậu hoặc bị tách khỏi primary quá lâu: có thể không đủ điều kiện được chọn theo cấu hình.
- Node có role/slot metadata chưa hội tụ: các client có thể gặp lỗi tạm thời.

**Một replica tồn tại không đồng nghĩa failover luôn thành công**. Kiểm thử thực tế phải bao gồm các điều kiện lỗi và tính phù hợp của topology.

## 6. Bảng so sánh ba cơ chế

| Tiêu chí | Sharding | Replication | Failover |
| --- | --- | --- | --- |
| Câu hỏi | Key nằm ở đâu? | Bản sao của key ở đâu? | Node nào thay primary lỗi? |
| Mục tiêu chính | Mở rộng dung lượng/tải | Dự phòng dữ liệu | Khôi phục khả năng phục vụ |
| Đơn vị | Hash slots / nhóm key | Một primary và replicas của nó | Một nhóm primary–replicas |
| Tác động tới dữ liệu | Phân phối key giữa primaries | Nhân bản trạng thái shard | Tiếp quản vai trò/slot ownership |
| Khi diễn ra | Khi cluster phân phối hoặc reshard | Trong hoạt động liên tục | Khi primary cần thay thế |
| Có tăng tổng dataset capacity? | Có thể | Không, replicas tốn thêm RAM |
| Có dự phòng khi primary chết? | Không nếu đứng riêng | Có bản sao nhưng chưa tự chuyển vai trò | Có thể promote replica |
| Có yêu cầu client topology awareness? | Có | Tùy đường đọc | Có |
| Rủi ro đặc trưng | CROSSSLOT, hotspot, resharding | Replication lag | Downtime, write loss, ambiguous retry |

Một lược đồ suy nghĩ:

```text
Need capacity?       -> sharding
Need backup copies?  -> replication
Need automatic role
replacement?         -> failover

Production HA Cluster = sharding + replicas + failover
```

Không nên coi các thành phần này là ba tên gọi khác nhau của một kỹ thuật.

## 7. Topology tối thiểu và topology có HA

### Ba primary, không có replica

```text
Master A     Master B     Master C
slots A      slots B      slots C
```

Ưu điểm: dữ liệu được phân mảnh, tổng dung lượng trên nhiều primary.

Nhược điểm: nếu một primary mất, không có replica của shard đó để tiếp quản. Tùy cấu hình cluster coverage và trạng thái cluster, nhiều thao tác có thể không được phục vụ.

### Ba primary, mỗi primary một replica

```text
Master A ----> Replica A1
Master B ----> Replica B1
Master C ----> Replica C1
```

Đây là topology mẫu thường được dùng khi giới thiệu Redis Cluster có HA. Phải đặt master và replica của cùng shard trên các failure domains khác nhau (host, rack, availability zone phù hợp), tránh mất cả hai trong một sự cố.

### Một primary với hai replicas có phải Redis Cluster ba shard không?

Không. Đó vẫn là **một shard** có các bản sao. Trong Redis Cluster tự động failover và bầu chọn, các điều kiện majority của primary nodes là yếu tố quan trọng. Một master với replicas không tương đương một cluster ba primary có khả năng mở rộng và điều phối failover.

Nếu mục tiêu chỉ là HA mà không cần sharding, **Redis Sentinel** có thể là mô hình phù hợp hơn trong một số triển khai.

## 8. Hash slot: cách Redis quyết định key đi đâu

Redis Cluster dùng 16.384 slots. Redis tính:

```text
CRC16(key) mod 16384
```

với quy tắc hash tag nếu key chứa một cặp `{}` hợp lệ và không rỗng bên trong.

Các key:

```text
cart:{user-42}:items
cart:{user-42}:total
```

được tính theo đoạn `user-42`, nên nằm trong **cùng một slot**.

Ngược lại:

```text
cart:user-42:items
cart:user-42:total
```

không có bảo đảm trùng slot chỉ vì cùng prefix.

Có thể kiểm tra:

```bash
redis-cli -c -h redis-node-a.internal -p 6379 \
  CLUSTER KEYSLOT 'cart:{user-42}:items'

redis-cli -c -h redis-node-a.internal -p 6379 \
  CLUSTER KEYSLOT 'cart:{user-42}:total'
```

Hai lệnh trên nên trả cùng slot cho hai key có cùng hash tag.

### Hash tag giúp gì?

- Dùng multi-key operations cho các key cần cùng slot.
- Chạy Lua script cần truy cập nhiều key trong cùng slot.
- Giữ một nhóm key nghiệp vụ liên quan trên một shard để thao tác nguyên tử tại Redis.
- Giảm lỗi `CROSSSLOT` trong giao dịch/gọi lệnh có nhiều key.

### Rủi ro của hash tag

Nếu dùng cùng một tag cho mọi key:

```text
cart:{all-users}:user-1
cart:{all-users}:user-2
cart:{all-users}:user-3
```

tất cả có thể bị dồn vào một slot, gây hotspot và mất lợi ích sharding.

Thiết kế tag theo **đơn vị nghiệp vụ cần cùng slot**, ví dụ mỗi user, tenant nhỏ hoặc một aggregate, không chọn một tag toàn cục chỉ để mọi multi-key command “chạy được”.

## 9. MOVED và ASK: client phải hiểu topology

Trong Redis Cluster, một request có thể đến sai node. Redis dùng redirect để hướng client tới node sở hữu slot.

### MOVED

Ví dụ:

```text
-MOVED 9281 10.10.0.12:6379
```

Ý nghĩa: slot `9281` thuộc node `10.10.0.12:6379`; client nên cập nhật hiểu biết topology và gửi lệnh tới node đó.

### ASK

Khi **resharding/migration** đang diễn ra, slot có thể ở trạng thái chuyển tiếp. Redis có thể trả `ASK` để client gửi lệnh kế tiếp đến node đích trong quá trình migration, thường kèm `ASKING` trước lệnh trên node đích theo protocol.

### Khác nhau

| Tín hiệu | Ngữ cảnh | Cách hiểu |
| --- | --- | --- |
| `MOVED` | Slot ownership đã ở node khác | Redirect và refresh topology |
| `ASK` | Slot đang di chuyển, trạng thái tạm thời | Redirect tạm thời theo protocol |
| `READONLY` | Client gửi write tới replica hoặc node không còn giữ role ghi | Cần xác định master mới/connection |
| `CROSSSLOT` | Multi-key command trải qua nhiều slot | Thiết kế lại keys/hash tag/logic |

Dùng Redis Cluster-aware client như Lettuce thông qua Spring Data Redis để client xử lý redirects và topology, thay vì tự parse `MOVED` trong từng service.

**Redis Cluster không phải một proxy endpoint duy nhất.** Seed nodes giúp khám phá cluster, còn driver phải giao tiếp với node sở hữu các slot.

## 10. Resharding không phải failover

Hai thao tác thường bị nhầm:

### Resharding: chủ động chuyển hash slots

Mục tiêu: cân bằng dung lượng/tải hoặc thêm/bớt primary.

```text
Trước:
  Primary A: slots 0–5460
  Primary B: slots 5461–10922

Reshard:
  Di chuyển một nhóm slot từ A sang B

Sau:
  Primary A: ít slot hơn
  Primary B: nhiều slot hơn
```

Key trong các slot được di chuyển theo quy trình migration. Trong giai đoạn chuyển, client có thể gặp `ASK`/`MOVED`.

### Failover: một replica tiếp quản primary lỗi

```text
Trước:
  Primary A owns slots 0–5460
  Replica A1 follows A

Failover:
  Primary A unreachable
  Replica A1 promoted

Sau:
  Primary A1 owns slots 0–5460
```

Không phải vì tăng shard count; Redis đang thay một node trong cùng vị trí logic của cluster.

### So sánh

| Tình huống | Thao tác chính |
| --- | --- |
| Thêm Redis primary để tăng dung lượng | Reshard/rebalance slots |
| Giảm tải một primary nóng theo nhóm key | Di chuyển slots khi phù hợp |
| Master hỏng, replica được promote | Failover |
| Replica mất, primary vẫn khỏe | Khôi phục/thay replica, chưa cần failover |
| Client nhận MOVED khi slots chuyển | Topology/resharding redirect |
| Client thấy READONLY sau role change | Kết nối còn hướng đến replica/node cũ |

Sharding và failover có thể cùng xảy ra trong một hệ thống, nhưng phải phân tích nguyên nhân riêng khi troubleshooting.

## 11. Phạm vi tính nguyên tử của Redis trong Cluster

Một lệnh Redis thông thường được xử lý tại node sở hữu key. Nhưng **multi-key operations** chịu ràng buộc slot.

Ví dụ:

```redis
MGET user:1 user:2
```

Nếu hai key ở các slot khác nhau, Redis Cluster có thể trả:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

Không phải vì replica chưa cập nhật hay failover đang xảy ra. Đây là hậu quả của **sharding**.

Để hai key liên quan cùng slot:

```redis
MGET session:{user-42}:access session:{user-42}:refresh
```

Khi dùng cùng hash tag hợp lệ, cả hai key đi đến cùng slot.

### Transaction và Lua script

Trong Redis Cluster, các lệnh multi-key, transaction và Lua script truy cập nhiều keys thông thường phải có keys thuộc cùng hash slot. Một Lua script không thể tùy ý thực hiện giao dịch nguyên tử xuyên Primary A và Primary B.

Ví dụ nghiệp vụ:

```text
Transfer:
  account:{A}:balance  -> slot X
  account:{B}:balance  -> slot Y
```

Nếu X khác Y, không thể giải quyết bằng cách đưa hai lệnh vào một `MULTI` hoặc một Lua script rồi mặc định Redis Cluster sẽ điều phối giao dịch xuyên shard.

Các hướng thiết kế:

- Điều chỉnh key model để những key cần atomic update cùng một slot, nếu phân phối tải vẫn hợp lý.
- Dùng transaction ở database có thẩm quyền cho nghiệp vụ xuyên aggregate.
- Dùng workflow/saga và idempotency với trạng thái bền vững nếu bản chất là giao dịch phân tán.
- Không gom toàn hệ thống vào một hash tag chỉ để né `CROSSSLOT`.

## 12. Cấu hình Spring Boot để dùng Redis Cluster

Với Spring Boot hiện đại sử dụng `spring.data.redis.*`, cấu hình cơ bản có thể là:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      cluster:
        nodes:
          - redis-node-1.internal:6379
          - redis-node-2.internal:6379
          - redis-node-3.internal:6379
        max-redirects: 5
      connect-timeout: 3s
      timeout: 3s
```

Các node trong `cluster.nodes` là **seed nodes** để client khám phá topology. Chúng không nhất thiết là toàn bộ các node của cluster, nhưng nên có nhiều địa chỉ khả dụng để tránh một seed trở thành điểm yếu khi kết nối lần đầu.

Sau khi khám phá, client dùng thông tin slot ownership để gửi command tới node phù hợp. Đừng tự code chia key theo danh sách seed nodes bằng `hashCode() % 3`, vì Redis Cluster đã có chuẩn hash slots và cơ chế điều phối riêng.

### Vấn đề phiên bản Spring Boot

Một số phiên bản Spring Boot cũ dùng property prefix `spring.redis.*`. Phải xem configuration metadata đúng với phiên bản đang triển khai. Không trộn standalone, Sentinel và Cluster settings rồi mặc định framework sẽ chọn ý định của người viết.

`max-redirects` giới hạn chuỗi redirect mà client xử lý theo cấu hình, **không phải** số lần retry nghiệp vụ hoặc ngưỡng failover. Tính đúng của retry ứng dụng vẫn phải được quản lý riêng.

## 13. Cấu hình Java bằng RedisClusterConfiguration

Khi muốn cấu hình Spring Data Redis tường minh:

```java
package com.example.redis;

import java.time.Duration;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisClusterConfig {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {

        RedisClusterConfiguration cluster =
            new RedisClusterConfiguration(
                List.of(
                    "redis-node-1.internal:6379",
                    "redis-node-2.internal:6379",
                    "redis-node-3.internal:6379"
                )
            );

        cluster.setMaxRedirects(5);

        LettuceClientConfiguration client =
            LettuceClientConfiguration.builder()
                .commandTimeout(Duration.ofSeconds(3))
                .build();

        return new LettuceConnectionFactory(cluster, client);
    }
}
```

Khi tự khai báo `RedisConnectionFactory`, app chịu trách nhiệm thiết lập những thuộc tính cần thiết; không mặc định Spring Boot sẽ tiếp tục áp dụng toàn bộ auto-configured Redis properties lên factory đó.

### Cấu hình xác thực

Nếu Redis nodes dùng ACL hoặc password, Spring Data Redis Cluster configuration có thể nhận authentication:

```java
import org.springframework.data.redis.connection.RedisPassword;

// Sau khi tạo RedisClusterConfiguration:
cluster.setUsername("app-redis-user");
cluster.setPassword(
    RedisPassword.of("PASSWORD_FROM_SECRET_CONFIGURATION")
);
```

Đoạn password trên chỉ là placeholder minh họa API. Trong production, inject giá trị từ secret manager/environment, không commit password vào repository.

Redis Cluster có thể yêu cầu TLS. Khi bật TLS/SSL, phải kiểm tra certificate, CA/truststore, hostname verification và TLS tới **mọi node mà cluster topology trả về**, không chỉ seed node ban đầu.

### Không dùng cấu hình Sentinel để thay Cluster

Hai class có mục đích khác nhau:

```text
RedisClusterConfiguration
  -> seed nodes + hash slots + cluster topology

RedisSentinelConfiguration
  -> master name + Sentinel discovery endpoints
```

Một hệ thống có replica/failover **không mặc nhiên là Redis Sentinel**. Redis Cluster tự có cơ chế failover dựa trên cluster nodes, không cần Sentinel để quản lý các shard của nó.

## 14. Sử dụng StringRedisTemplate trong Cluster

Khi connection factory được cấu hình Cluster, API `StringRedisTemplate` ở tầng ứng dụng gần như không đổi:

```java
package com.example.redis;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheService {

    private final StringRedisTemplate redis;

    public ProductCacheService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void cachePrice(String productId, String price) {
        redis.opsForValue().set(
            "product:price:" + productId,
            price,
            Duration.ofMinutes(5)
        );
    }

    public String findCachedPrice(String productId) {
        return redis.opsForValue().get(
            "product:price:" + productId
        );
    }
}
```

Service chỉ cung cấp key và value; Redis Cluster-aware driver tính slot và định tuyến command.

Ví dụ:

```text
cachePrice("42", "120000")
  -> SET product:price:42 120000 EX 300
  -> driver tìm slot của key
  -> gửi tới primary sở hữu slot
```

Khi slot di chuyển hoặc primary failover, client cập nhật topology theo cơ chế của driver và cấu hình.

**Không cần** tự duy trì bảng `productId -> Redis host` trong business service. Làm vậy dễ xung đột với cơ chế resharding của cluster.

## 15. Cấu hình read-from-replica và cảnh báo stale data

Với Lettuce, có thể chọn chính sách đọc từ replica trong những chế độ client hỗ trợ. Ví dụ:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .readFrom(ReadFrom.REPLICA_PREFERRED)
        .commandTimeout(Duration.ofSeconds(3))
        .build();
```

Khi ứng dụng cấu hình đọc từ replica, cần hiểu:

- Replication là bất đồng bộ.
- Đọc sau ghi không luôn thấy giá trị mới.
- Failover có thể khiến replica role/topology đổi.
- Chọn replica read cho cache/dashboard có thể phù hợp; không thích hợp mặc định cho quyết định cần dữ liệu mới nhất.

### Ví dụ lỗi read-your-writes

```text
T0: SET user:42:status ACTIVE ở Primary B
T1: Primary B trả OK
T2: GET user:42:status ở Replica B1
T3: Replica B1 chưa nhận write -> trả trạng thái cũ
```

Trong những use case cần tính nhất quán cao, đọc primary hoặc nguồn dữ liệu có thẩm quyền theo một chính sách được chứng minh phù hợp. Đọc primary cũng không biến replication/failover thành transaction bền vững tuyệt đối.

## 16. Replication bất đồng bộ và nguy cơ mất write khi failover

Một tình huống:

```text
T0   Client gửi SET order:42 PAID tới Primary B
T1   Primary B thực hiện và trả OK
T2   Primary B mất đột ngột
T3   Replica B1 được promote thành primary mới
T4   B1 chưa nhận write ở T1
T5   Dữ liệu PAID không có ở master mới
```

Điều này có thể xảy ra vì replication thông thường là bất đồng bộ.

Redis cung cấp lệnh như `WAIT` để chờ một mức xác nhận từ replicas cho những write trước đó trên connection. Nhưng `WAIT` **không biến Redis Cluster thành hệ thống giao dịch đồng bộ hoàn toàn** và không bảo đảm không mất dữ liệu trong mọi tình huống crash, failover hoặc persistence failure.

Phải đánh giá:

- Redis là cache hay source of truth?
- Có thể xây lại dữ liệu từ database không?
- Tổn thất một write có ảnh hưởng tài chính không?
- Mức replica lag chấp nhận được?
- Cấu hình persistence RDB/AOF và durability expectation?
- Có cần dùng database giao dịch hoặc một hệ thống khác làm nguồn có thẩm quyền?

Không gán cho sharding hay failover tính năng durability mà chúng không cung cấp.

## 17. Redis Cluster failover được quyết định như thế nào?

Redis Cluster dùng cơ chế trao đổi trạng thái node và thông tin slots qua cluster bus. Khi một primary không phản hồi, các node khác có thể đánh giá node đó ở trạng thái lỗi. Một replica phù hợp có thể xin được bầu thành primary mới.

Các khái niệm thường thấy trong `CLUSTER NODES` hoặc tài liệu Redis:

- `PFAIL`: một node bị đánh giá có khả năng lỗi từ góc nhìn một node.
- `FAIL`: trạng thái lỗi đã được cluster xác nhận theo điều kiện phù hợp.
- Replica có dữ liệu tương đối cập nhật và quyền tiếp quản phù hợp.
- Election cần sự ủy quyền từ đủ primary nodes để tránh split-brain trong cluster partition.
- Replica trở thành primary và nhận trách nhiệm quản lý slots cũ.

**Đừng nhầm quorum của Redis Sentinel với election của Redis Cluster.** Cả hai đều phục vụ HA nhưng là hai hệ thống điều phối khác nhau.

### Vì sao mất majority nguy hiểm?

Giả sử Cluster có ba primary và network bị chia:

```text
Partition 1: Primary A

Partition 2: Primary B + Primary C
```

Nhóm chỉ có Primary A không thể mặc định tiếp tục vận hành như một cluster hoàn chỉnh trong mọi tình huống. Quy tắc majority và cluster state hạn chế hoạt động để tránh những trạng thái sai nghiêm trọng khi phân vùng mạng.

Tính sẵn sàng phụ thuộc vào:

- Những primary nào còn kết nối.
- Hash slots nào còn được phục vụ.
- Replicas ở partition nào.
- Cluster state và cấu hình coverage.
- Quy tắc failover/election.

Không hứa mọi key đều luôn đọc/ghi được chỉ vì cluster vẫn còn một vài node đang chạy.

## 18. Cluster slot coverage và khả năng phục vụ khi shard lỗi

Redis Cluster thường cần 16.384 slots được gán, và hoạt động phục vụ command phụ thuộc trạng thái cluster.

Một cấu hình liên quan là `cluster-require-full-coverage`. Khi bật chế độ yêu cầu phủ toàn bộ slots, mất khả năng phục vụ một số slots có thể khiến cluster từ chối nhiều thao tác thay vì chỉ những key thuộc slots mất.

Nếu cấu hình cho phép partial coverage, một số thao tác ở slots còn có thể tiếp tục hoạt động trong một số tình huống, nhưng điều này **không biến những slots không có owner thành khả dụng**.

Bảng suy nghĩ:

| Tình huống | Ảnh hưởng |
| --- | --- |
| Một replica lỗi, primary còn khỏe | Shard vẫn có thể phục vụ; giảm dự phòng |
| Một primary lỗi, replica được promote | Shard có thể phục hồi sau cửa sổ failover |
| Primary và mọi replicas của shard đều lỗi | Slots liên quan không có node phục vụ |
| Mất majority của primary nodes | Failover/availability có thể bị ảnh hưởng nghiêm trọng |
| Slot đang resharding | Client có thể nhận ASK/MOVED tạm thời |

Chi tiết phụ thuộc Redis version và cấu hình cụ thể. Không nên đưa ra kết luận “chỉ node lỗi mới ảnh hưởng” khi chưa kiểm tra full coverage và cluster state.

## 19. Vận hành Redis Cluster với redis-cli

Kết nối bằng cluster-aware mode:

```bash
redis-cli -c -h redis-node-1.internal -p 6379
```

Tùy shell và môi trường, có thể gõ các lệnh sau trong phiên `redis-cli`:

```redis
CLUSTER INFO
CLUSTER NODES
CLUSTER SHARDS
CLUSTER SLOTS
```

Các lệnh quan trọng:

| Lệnh | Mục đích |
| --- | --- |
| `CLUSTER INFO` | Xem cluster state, slots được gán/phục vụ, số node |
| `CLUSTER NODES` | Xem node ID, role, link state, slot ranges |
| `CLUSTER SHARDS` | Thông tin shard, primary và replicas ở các Redis version hỗ trợ |
| `CLUSTER SLOTS` | Mapping slots với nodes, thường dùng cho client discovery |
| `CLUSTER KEYSLOT key` | Xem slot của một key |
| `INFO replication` | Xem role và trạng thái replication trên node |
| `ROLE` | Xem role của node hiện tại |

Ví dụ kiểm tra slot:

```bash
redis-cli -h redis-node-1.internal -p 6379 \
  CLUSTER KEYSLOT 'cart:{user-42}:items'
```

Dấu `\` trong những ví dụ shell là ký tự nối dòng kiểu Unix; trong Windows PowerShell có thể chạy lệnh trên một dòng thay vì dùng dấu nối đó.

### Khi dùng -c

`redis-cli -c` theo redirect cluster để thao tác với key ở node khác. Nếu dùng `redis-cli` không có cluster-aware mode, bạn có thể nhìn thấy phản hồi `MOVED`; điều này không tự chứng minh Redis bị lỗi.

Không chạy reshard hoặc failover thử nghiệm trực tiếp trên production nếu chưa có quy trình thay đổi được phê duyệt.

## 20. Phân biệt lỗi do sharding, replication và failover

| Triệu chứng | Nhóm nguyên nhân thường gặp | Hướng xem |
| --- | --- | --- |
| `CROSSSLOT` | Sharding / key model | Keys cùng hash slot không? |
| `MOVED` | Sai node hoặc topology đổi | Client cluster-aware, refresh topology |
| `ASK` | Slot migration | Resharding đang diễn ra? |
| Replica trả giá trị cũ | Replication lag | Đường đọc replica, offset/lag |
| `READONLY` sau đổi role | Failover / stale connection | Client đang gửi write tới node nào? |
| `CLUSTERDOWN` | Cluster availability/coverage | `CLUSTER INFO`, slots, majority |
| Timeout vài giây khi primary lỗi | Failover / reconnect | Role change, client timeout, retry |
| Một key quá nóng dù nhiều node | Hot key/slot | Distribution và traffic |
| Primary mất và không có replica | Thiếu dự phòng | Topology replication |
| Write ACK rồi mất sau promotion | Async replication/durability | RPO, replication/persistence |
| Chỉ seed node truy cập được | Network/topology discovery | Địa chỉ nodes được công bố có reachable? |

Chẩn đoán đúng bắt đầu bằng **xác định cơ chế**. Không xử lý `CROSSSLOT` bằng cách thêm replica; không xử lý replication lag bằng cách reshard; không xử lý failover timeout bằng cách đổi thuật toán hash key.

## 21. Network: seed nodes không phải proxy

Trong Redis Cluster, client có thể bắt đầu từ một seed node nhưng sau đó truy cập các nodes khác theo topology. Redis data nodes còn dùng **cluster bus** để trao đổi trạng thái nội bộ.

Ví dụ cấu hình port mặc định:

```text
Redis client port: 6379
Cluster bus port: 16379 (thường base port + 10000)
```

Tùy cấu hình Redis, cluster bus port có thể được đặt riêng; không mặc định mọi deployment đều dùng đúng `16379`.

### Network phải hỗ trợ hai loại traffic

```text
Spring Boot ---> Redis data nodes (client ports)

Redis node A <--> Redis node B (cluster bus ports)
```

Lưu ý:

- Client cần tới được **các Redis nodes mà topology trả về**, không chỉ seed nodes.
- Redis nodes phải giao tiếp được với nhau qua cluster bus.
- DNS/IP/ports công bố bởi cluster phải đúng với mạng của client.
- Docker NAT hoặc Kubernetes networking có thể khiến advertised addresses khác địa chỉ cần thiết.
- Khi failover, replica được promote phải có endpoint reachable từ ứng dụng.

Một cluster có thể trông khỏe từ mạng Redis nội bộ nhưng Spring container vẫn không connect được vì node trả về địa chỉ private khác network.

## 22. Docker/Kubernetes và địa chỉ cluster announce

Ví dụ sai thường gặp:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:6379
```

Nếu Spring chạy trong Docker container khác Redis, `127.0.0.1` trỏ về **chính Spring container**, không phải Redis.

Trong Kubernetes, seed nodes có thể là những DNS của pod hoặc service phù hợp:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-0.redis-headless.svc.cluster.local:6379
          - redis-1.redis-headless.svc.cluster.local:6379
          - redis-2.redis-headless.svc.cluster.local:6379
```

Các tên này **chỉ minh họa**, phụ thuộc Redis operator/topology thực tế.

Bên cạnh seed nodes, Redis cần announce địa chỉ và ports phù hợp để clients và cluster nodes kết nối được. Những lựa chọn cấu hình như `cluster-announce-ip`, `cluster-announce-port`, `cluster-announce-bus-port` có thể liên quan tùy topology.

Không nên “sửa” network issue bằng cách hard-code nhiều nơi trong Java business logic. Sửa discovery/advertised endpoints và kiểm thử từ chính namespace/container đang chạy ứng dụng.

## 23. Mất node không phải lúc nào cũng làm mất dữ liệu như nhau

Xét ba trường hợp:

### Mất replica

```text
Primary A ----> Replica A1 (DOWN)
```

Nếu Primary A vẫn khỏe, read/write trên shard A có thể tiếp tục. Tuy nhiên, HA bị giảm vì không còn replica sẵn sàng cho failover.

### Mất primary nhưng replica còn

```text
Primary B (DOWN)
Replica B1 (UP) ---> có thể promote
```

Cluster có cơ hội phục hồi slots B. Có thể xuất hiện downtime, timeout và lỗi tạm thời trong quá trình election/reconnect.

### Mất cả primary và replicas

```text
Primary C (DOWN)
Replica C1 (DOWN)
```

Không còn bản sao sẵn sàng của slots C. Cluster không thể chỉ dựa vào việc Primary A/B vẫn chạy để tự tái tạo dữ liệu C. Tùy persistence/backup và topology, cần khôi phục dữ liệu hoặc node của shard đó.

**Sharding không tự dự phòng dữ liệu; replication là thứ tạo bản sao.**

## 24. Tại sao việc thêm replica không tăng capacity của dataset?

Nếu Primary A giữ 20 GB dữ liệu và có hai replicas:

```text
Primary A     20 GB
Replica A1    20 GB (xấp xỉ)
Replica A2    20 GB (xấp xỉ)
```

Tổng RAM cần thiết lớn hơn, nhưng **logical dataset của shard A vẫn chỉ khoảng 20 GB**. Không phải 60 GB dữ liệu độc lập có thể ghi vào đó.

Ngược lại, khi thêm Primary D và reshard một số slots sang D:

```text
Trước:
  A = 20 GB, B = 20 GB, C = 20 GB

Sau khi thêm D và rebalance:
  A = 15 GB, B = 15 GB, C = 15 GB, D = 15 GB
```

Các con số chỉ là minh họa phân bố đều. Tổng dữ liệu logic vẫn 60 GB, nhưng tải/dung lượng mỗi primary có thể giảm.

Thêm replica có thể hỗ trợ một số workload đọc khi client cho phép replica reads; nó không tự tăng khả năng xử lý write của shard đó, vì write vẫn phải đi vào primary.

## 25. Đo tải từng shard và hotspot

Sharding phân phối theo slot, nhưng phân phối key đều **không bảo đảm tải đều**.

Ví dụ:

```text
Key                Requests/second
product:hot:42          80,000
product:101                20
product:102                15
...
```

Dù slot key `product:hot:42` được phân phối ngẫu nhiên giữa 16.384 slots, tất cả request tới key này vẫn tập trung vào một shard sở hữu slot.

Các phương án phụ thuộc use case:

- Cache local cho dữ liệu đọc nhiều nếu chấp nhận stale.
- Chia một số workload đọc có kiểm soát.
- Thay đổi data model hoặc phân tách counter khi tính nhất quán cho phép.
- Thêm primary và reshard để cân bằng nhóm slots, nhưng **một hot key đơn lẻ vẫn thuộc một slot**.
- Giảm kích thước payload, batch command hoặc tránh thao tác CPU nặng.

Không nên hứa “thêm node là đủ giải quyết mọi hot key”. Sharding giúp phân chia nhiều keys, không tự chia một key khổng lồ thành nhiều independent slots.

## 26. Redis Cluster và Spring Cache

Spring Cache abstraction (`@Cacheable`, `@CachePut`, `@CacheEvict`) có thể sử dụng Redis làm backing store qua `RedisCacheManager`. Khi `RedisConnectionFactory` là cluster-aware, client định tuyến các Redis keys tới slot phù hợp.

Ví dụ:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final ProductRepository products;

    public ProductQueryService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductView findById(Long id) {
        return products.findViewById(id);
    }
}
```

Ở ví dụ này, `ProductRepository` và `ProductView` đại diện cho tầng dữ liệu/domain của ứng dụng; phần chính là annotation cache.

Những điều cần phân biệt:

- Redis Cluster **chia các cache entries theo slot**.
- Replicas giữ bản sao của shard chứa cache entry.
- Failover giúp shard phục hồi khi có replica được promote.
- `@Cacheable` không tự cung cấp consistency mạnh khi database cập nhật.
- Cache TTL và invalidation vẫn cần thiết.
- Bulk cache clear hoặc xóa theo pattern có thể bị ảnh hưởng bởi cơ chế scan/cluster; phải xác định cách cache writer triển khai trên phiên bản Spring Data Redis.

Nếu Redis chỉ là cache, application có thể fallback đọc database khi cluster unavailable theo chính sách nghiệp vụ. Không nên dùng cùng đường fallback đó cho Redis lock, counter có thẩm quyền hoặc queue quan trọng nếu làm mất tính đúng.

## 27. Pipeline, script và multi-key operations

### Pipeline

Pipelining giảm round-trip nhưng không biến các commands trải qua nhiều slots thành một transaction. Cluster-aware driver có thể định tuyến/pipeline theo node tùy API và cách triển khai; hãy kiểm tra hỗ trợ của phiên bản client.

### Lua scripting

Script Redis chạy trên node của những key liên quan. Các key mà script truy cập phải được khai báo và tuân thủ quy tắc slot.

Ví dụ:

```text
KEYS[1] = cart:{user-42}:items
KEYS[2] = cart:{user-42}:total
```

Cả hai thuộc cùng slot. Script có thể thực hiện một critical section tại node sở hữu slot này.

Ngược lại:

```text
KEYS[1] = cart:{user-42}:items
KEYS[2] = stock:{sku-99}
```

Có khả năng nằm ở hai slots khác nhau; không thể mặc định atomic cross-shard.

### Transaction

`MULTI/EXEC` có thể thực hiện các thao tác phù hợp trên cùng node/slot theo ràng buộc của Redis Cluster. Nó không tạo một distributed transaction coordinator xuyên nhiều primary shards.

Đối với nghiệp vụ tiền tệ hoặc đơn hàng cần cập nhật dữ liệu ở các key thuộc nhiều slot, chọn nguồn dữ liệu chuẩn và thiết kế consistency/idempotency từ đầu.

## 28. Failover và lệnh write không rõ đã thực hiện hay chưa

Một lỗi quan trọng:

```text
App -> Primary B: INCR billing:count
Redis đã tăng counter
Network đứt trước khi app nhận reply
Replica được promote
App nhận timeout
```

App không biết lệnh đã thực hiện hay chưa. Nếu retry vô điều kiện, counter có thể tăng hai lần; nếu không retry, có thể bỏ lỡ một cập nhật. Nếu replication bất đồng bộ làm write mất khi failover, dữ liệu sau promotion còn phức tạp hơn.

Phân loại retry:

| Lệnh | Retry đơn giản có an toàn không? |
| --- | --- |
| `GET key` | Thường có thể thực hiện lại, nhưng kết quả có thể khác do dữ liệu thay đổi |
| `SET key fixedValue` | Thường idempotent nếu không có điều kiện/tác dụng phụ khác |
| `INCR key` | Không an toàn khi retry mù quáng |
| `LPUSH list value` | Có thể ghi trùng |
| `SET key token NX PX ...` | Cần hiểu lock ownership và TTL |
| Lua reservation | Cần idempotency ID và trạng thái đã xử lý |

**Failover không đem lại exactly-once execution.** Cần ID nghiệp vụ ổn định và điều kiện chống lặp khi có tác dụng phụ quan trọng.

## 29. Khôi phục và resharding có tác động tới trải nghiệm người dùng

Ví dụ một hệ thống thương mại điện tử:

```text
Product Cache      -> Redis Cluster
Shopping Cart       -> Redis Cluster
Payment State       -> Database source of truth
```

Khi Primary B failover:

- Một phần key cache thuộc slots B có thể tạm không đọc được.
- Giỏ hàng thuộc slots B có thể lỗi tạm thời nếu không có fallback thích hợp.
- Payment state vẫn cần được xác nhận tại database có thẩm quyền.
- Sau khi replica được promote, client phải khám phá topology mới.

Khi reshard:

- Key của một số slots được chuyển sang node khác.
- Cluster-aware clients xử lý MOVED/ASK.
- Các thao tác có thể chịu latency tăng tạm thời.
- Cần giám sát network, CPU và memory khi di chuyển dữ liệu.

Cả hai tình huống đều có thể làm latency thay đổi, nhưng nguyên nhân và hướng xử lý khác nhau. Đừng kết luận “Redis bị failover” chỉ vì nhìn thấy `MOVED` trong log.

## 30. Cấu hình topology refresh của Lettuce

Lettuce có cơ chế quản lý cluster topology. Trong các deployment có node changes/resharding, ứng dụng cần khám phá và làm mới thông tin slots.

Các lựa chọn thường liên quan:

- Refresh topology khi gặp redirect.
- Periodic topology refresh khi cần.
- Connection reconnect và adaptive topology refresh.
- DNS/advertised endpoints.
- Command timeout và giới hạn redirects.

Ví dụ mức API Lettuce (minh họa khái niệm; cách tích hợp vào Spring Data Redis tùy phiên bản):

```java
import io.lettuce.core.cluster.ClusterClientOptions;
import io.lettuce.core.cluster.ClusterTopologyRefreshOptions;
import java.time.Duration;

ClusterTopologyRefreshOptions refresh =
    ClusterTopologyRefreshOptions.builder()
        .enablePeriodicRefresh(Duration.ofSeconds(30))
        .enableAllAdaptiveRefreshTriggers()
        .build();

ClusterClientOptions options =
    ClusterClientOptions.builder()
        .topologyRefreshOptions(refresh)
        .build();
```

Đoạn code chỉ xây cấu hình Lettuce, **không tự gắn** vào `LettuceConnectionFactory`. Muốn áp dụng, phải tạo client configuration/client resources theo API của phiên bản Spring Data Redis đang dùng và đưa `options` vào đúng chỗ.

Refresh quá thường xuyên tăng truy vấn topology; refresh quá chậm có thể khiến client giữ thông tin cũ lâu. Cần đo tải và hành vi lúc failover/reshard.

## 31. Ví dụ smoke test trên Spring Boot

Giả sử ứng dụng đã có `StringRedisTemplate` do Spring Boot cấu hình Redis Cluster.

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class RedisClusterSmokeTest {

    @Autowired
    StringRedisTemplate redis;

    @Test
    void canReadAndWriteThroughClusterClient() {
        String key = "test:cluster:smoke";

        redis.opsForValue().set(key, "connected");

        assertThat(redis.opsForValue().get(key))
            .isEqualTo("connected");

        redis.delete(key);
    }
}
```

Test này xác nhận một key được route thành công tại thời điểm kiểm tra. Nó **chưa chứng minh**:

- Có nhiều primary thật.
- Replication đang bắt kịp.
- Failover tự động hoạt động.
- Một key ở shard khác cũng truy cập được.
- Multi-key commands cùng slot.
- Không có dữ liệu bị mất sau promotion.

Muốn kiểm tra cluster topology và failover, cần integration test với nhiều Redis nodes thật trong môi trường riêng. Không chạy test gây lỗi node trên production.

## 32. Kịch bản integration test cho ba cơ chế

### Kịch bản A — Chứng minh sharding

1. Tạo cluster có ba primary.
2. Tính slot của nhiều key bằng `CLUSTER KEYSLOT`.
3. Quan sát `CLUSTER SHARDS`/`CLUSTER NODES`.
4. Xác minh các keys thuộc những slot khác nhau được định tuyến đến các primary phù hợp.
5. Thử multi-key operation với key khác slot để thấy giới hạn `CROSSSLOT`.
6. Thử hai key cùng hash tag để minh họa đồng slot.

### Kịch bản B — Chứng minh replication

1. Ghi một key lên primary sở hữu slot.
2. Xem `INFO replication` ở primary và replica.
3. Quan sát replica theo primary và replication status.
4. Dùng đường đọc replica được hỗ trợ trong môi trường test và so sánh giá trị.
5. Gây tải có kiểm soát để hiểu khả năng xuất hiện replication lag.

### Kịch bản C — Chứng minh failover

1. Xác nhận topology ba primary, mỗi primary có replica.
2. Ghi một số key test vào shard mục tiêu.
3. Dùng cơ chế failover có kiểm soát hoặc dừng primary trong môi trường test.
4. Quan sát replica trở thành primary mới và tiếp quản slots.
5. Kiểm tra application reconnect, write sau failover và lỗi tạm thời.
6. Xác định chính sách retry của các write không idempotent.

Một lệnh có thể dùng **trên replica trong môi trường thử nghiệm** để yêu cầu coordinated failover:

```redis
CLUSTER FAILOVER
```

Lệnh này không dành để chạy tùy tiện trên production và có điều kiện hỗ trợ/quy tắc riêng. Test mất điện/network cần thiết kế khác với coordinated failover để quan sát failure behavior thực.

### Kịch bản D — Thử reshard

1. Thêm primary mới.
2. Di chuyển một phần slots trong môi trường test.
3. Quan sát slot map thay đổi và MOVED/ASK redirects.
4. Xác minh key vẫn có thể đọc sau khi migration hoàn tất.
5. Ghi nhận latency/CPU/network trong quá trình di chuyển.

Cần phân biệt rõ các kết quả A/B/C/D, không gom thành một nhãn “Redis Cluster hoạt động”.

## 33. Production checklist theo từng cơ chế

### Sharding

- Các slots được gán đầy đủ theo chiến lược vận hành.
- Không có hotspot nghiêm trọng trên một key hoặc slot.
- Hash tags chỉ dùng khi thực sự cần colocation.
- Mọi multi-key command/script đều tuân thủ slot constraints.
- Các node được công bố có địa chỉ reachable.
- Resharding có kế hoạch và giám sát.

### Replication

- Mỗi primary quan trọng có replica ở failure domain độc lập.
- Replication link và lag được giám sát.
- Redis persistence/backup đáp ứng RPO cần thiết.
- Đọc replica được bật có chủ đích, có chính sách stale data.
- Không hiểu số replicas là số lần tăng logical dataset capacity.

### Failover

- Cluster có số primary và replicas đủ cho mục tiêu HA.
- Election và cluster bus network được cấu hình đúng.
- Failover được thử trong môi trường cô lập.
- Application có timeout/reconnect/topology refresh.
- Các thao tác non-idempotent có retry policy phù hợp.
- Có alert cho role changes, unavailable slots và cluster state.

### Spring Data Redis

- Dùng `RedisClusterConfiguration` hoặc `spring.data.redis.cluster.*`.
- Driver hỗ trợ Redis Cluster, ví dụ Lettuce, và phiên bản tương thích.
- Không tự điều phối key-to-host trong service.
- Không nhầm cấu hình Sentinel với Cluster.
- Serializer/key naming không bị sai lệch khi triển khai nhiều service.
- Cache fallback phù hợp vai trò Redis.
- Có metric theo shard, node và application error codes.

## 34. Những ngộ nhận thường gặp

### “Ba Redis nodes nghĩa là dữ liệu được sao chép ba lần”

Không. Nếu cả ba là primaries, dữ liệu có thể được sharding thành ba phần khác nhau. Muốn bản sao cần replicas theo từng shard.

### “Có replica là đã tăng dung lượng dataset gấp đôi”

Không. Replica thường giữ bản sao dữ liệu shard, nên tốn RAM mà không tăng logical dataset capacity.

### “Failover tức là chia lại hash slots”

Không. Failover thường đưa replica tiếp quản các slots của primary cũ. Resharding là di chuyển slot ownership để thay đổi phân bố dữ liệu/tải.

### “Sharding giúp một hot key chạy trên nhiều primary”

Không. Một key thuộc một slot. Tất cả thao tác với key đó tập trung vào shard sở hữu slot.

### “MOVED nghĩa là dữ liệu mất”

Không. MOVED là cluster redirect báo địa chỉ node sở hữu slot. Client cluster-aware có thể cập nhật routing.

### “ASK và MOVED giống nhau”

Không. ASK chủ yếu liên quan migration tạm thời; MOVED mô tả thay đổi slot ownership.

### “Replication đồng bộ nên write đã OK không thể mất”

Không. Redis replication thông thường là bất đồng bộ. Write đã ACK vẫn có rủi ro chưa tồn tại trên replica được promote.

### “Cluster tự thực hiện transaction nhiều slot”

Không. Các thao tác multi-key chịu ràng buộc slot. Cần thiết kế lại key model hoặc cơ chế giao dịch ngoài Redis.

### “Thêm replica sẽ làm primary xử lý write nhanh hơn”

Không trực tiếp. Write vẫn phải được xử lý ở primary; replication còn tiêu tốn network/CPU. Một số read workloads có thể được chuyển sang replica nếu chấp nhận stale data.

### “Client chỉ cần kết nối được seed node”

Không. Sau discovery, client phải đến được các Redis nodes tương ứng với hash slots và những node được promote/đưa vào cluster.

### “Cluster failover luôn không có downtime”

Không. Detection, election, promotion, topology refresh và reconnect đều mất thời gian; có thể có lỗi và timeout tạm thời.

### “READONLY sau failover là lỗi serializer”

Không. Lỗi này thường liên quan role/đường ghi vào node không còn là primary; cần kiểm tra connection và topology.

### “Sử dụng Redis Cluster là thay thế hoàn toàn cho backup”

Không. Sharding, replication và failover không loại bỏ nhu cầu persistence, backup, recovery drill và đánh giá RPO/RTO.

## 35. Bài tập thiết kế

### Bài A — Chọn node cho dữ liệu

Có ba primary và mỗi primary một replica. Hãy xác định:

- Key thuộc primary nào dựa trên slot?
- Replica nào có bản sao của key đó?
- Khi primary lỗi, node nào có thể tiếp quản?
- Điều gì khác nhau giữa chuyển slot sang primary mới và promote replica?

### Bài B — Sửa CROSSSLOT

Các key:

```text
cart:user-42:items
cart:user-42:total
```

Ứng dụng muốn cập nhật cả hai bằng Lua. Hãy đổi key naming để bảo đảm cùng slot, sau đó giải thích nguy cơ nếu tất cả users bị dồn vào một hash tag duy nhất.

### Bài C — Replication lag

Ứng dụng ghi `available=5` vào primary rồi đọc replica và thấy `available=6`. Hãy giải thích vì sao có thể xảy ra, tác động đến quyết định bán hàng và lựa chọn đường đọc phù hợp.

### Bài D — Failover

Primary B lỗi; Replica B1 được promote. Hãy giải thích vì sao slots B vẫn được xử lý bởi nhóm dữ liệu đó dù node primary đã thay đổi, và vì sao client phải refresh topology.

### Bài E — Resharding

Thêm Primary D để tăng capacity. Hãy mô tả điều gì xảy ra với hash slots, key migration, MOVED/ASK và độ trễ ứng dụng. Giải thích tại sao đây không phải failover.

### Bài F — Retry khi response mất

Một `INCR` có thể đã thực thi trước khi connection đứt. Hãy thiết kế idempotency key và một cách kiểm tra kết quả để tránh tăng số lần xử lý nghiệp vụ không kiểm soát.

## 36. Câu hỏi thường gặp

**Redis Cluster cần bao nhiêu primary?**

Thiết kế phổ biến cho HA dùng ít nhất ba primaries và có replicas, nhưng topology cụ thể phụ thuộc mức chịu lỗi, dữ liệu, failure domains và yêu cầu vận hành. Không suy ra mọi hệ thống nhỏ phải dùng cùng một số node.

**Một replica có chứa toàn bộ cluster dataset không?**

Không. Replica thường sao chép dữ liệu từ primary mà nó theo dõi, tương ứng một shard của cluster.

**Khi thêm replica có cần reshard không?**

Không mặc định. Replica mới sao chép một shard hiện có, không nhận thêm hash slots độc lập. Resharding chủ yếu liên quan thay đổi phân bố slots giữa primaries.

**Failover có làm key đổi hash slot không?**

Thông thường không. Key vẫn có cùng slot theo CRC16; node sở hữu slot có thể đổi khi replica được promote.

**Có thể dùng nhiều key trong Lua của Redis Cluster không?**

Có khi các Redis keys truy cập theo script thuộc cùng hash slot và tuân thủ các ràng buộc liên quan. Không thể mặc định script atomic qua nhiều shards.

**Tại sao một GET sau SET thấy giá trị cũ?**

Nếu đọc replica và replication chưa bắt kịp, có thể xảy ra stale read. Cũng cần kiểm tra cache khác, TTL và consistency của nguồn dữ liệu.

**Redis Cluster có cần Sentinel không?**

Không. Redis Cluster có cơ chế quản lý topology và failover riêng. Sentinel phù hợp mô hình primary–replica không sharding theo hash slots.

**Có thể chỉ đặt một seed node không?**

Về kỹ thuật client có thể khám phá qua một seed khi seed reachable, nhưng để giảm điểm yếu khi bootstrap thường nên cấu hình nhiều seed nodes và bảo đảm mọi data node được công bố có thể truy cập.

**MOVED là lỗi ứng dụng không?**

Không nhất thiết. MOVED là protocol redirect của Redis Cluster. Client cluster-aware cần xử lý nó; nếu MOVED lộ ra ở service, kiểm tra client config/topology refresh.

**Failover có bảo đảm zero data loss không?**

Không. Redis replication thông thường bất đồng bộ, có thể chưa chuyển hết writes đã ACK sang replica được promote.

**Vì sao dùng Redis Cluster mà một node lỗi thì cả API vẫn lỗi?**

Có thể do cluster coverage, mất majority, shard không có replica, network topology hoặc ứng dụng phụ thuộc những key ở slot không khả dụng. Cần xem cluster state và error codes cụ thể.

## 37. Tổng kết

- **Sharding** phân phối các key theo **16.384 hash slots** cho nhiều primaries để mở rộng capacity và throughput.
- **Replication** tạo các bản sao theo từng primary/shard, thường **bất đồng bộ**, nên có replication lag và rủi ro mất write khi failover.
- **Failover** để replica đủ điều kiện thay primary lỗi và tiếp quản các slots của nó; không đồng nghĩa resharding.
- **Resharding** chuyển ownership của slots giữa primaries để đổi phân bố dữ liệu; client cần xử lý MOVED/ASK.
- **Redis Cluster không làm multi-key operations nguyên tử xuyên shards**. Hash tags giúp colocate key khi cần nhưng có thể tạo hotspots.
- **Spring Data Redis** dùng `RedisClusterConfiguration`/Lettuce hoặc `spring.data.redis.cluster.*`; client discovery/routing phụ thuộc seed nodes và network topology được công bố.
- **Replica reads có thể stale**, failover có thể gây timeout, và retry non-idempotent phải được thiết kế cẩn trọng.
- **HA không phải backup và không phải durability tuyệt đối**. Theo dõi role, slots, replication lag, failover và kiểm thử khôi phục trong môi trường cô lập.

Phân biệt rõ sharding, replication và failover giúp thiết kế Redis Cluster đúng mục tiêu: biết cần **thêm shard** khi thiếu dung lượng/tải, **thêm replica** khi thiếu dự phòng, và **kiểm tra failover/topology** khi cần phục hồi sau sự cố mà không đánh đồng các cơ chế.

## Tài liệu tham khảo chính thức

- [Redis – Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis – Redis Cluster tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis – CLUSTER SLOTS](https://redis.io/docs/latest/commands/cluster-slots/)
- [Redis – CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/)
- [Redis – CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/)
- [Redis – Redis Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis – WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis – CLUSTER FAILOVER](https://redis.io/docs/latest/commands/cluster-failover/)
- [Spring Data Redis – Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis – Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html)
- [Spring Data Redis – RedisClusterConfiguration API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/RedisClusterConfiguration.html)
- [Spring Data Redis – LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html)
