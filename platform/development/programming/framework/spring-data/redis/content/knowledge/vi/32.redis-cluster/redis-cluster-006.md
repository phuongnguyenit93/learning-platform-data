# Thao tác nhiều nút qua RedisClusterConnection

Trong một Redis Standalone, mọi khóa được quản lý bởi một Redis server. Khi chuyển sang **Redis Cluster**, không gian khóa được chia thành **16.384 hash slot**, phân phối cho nhiều primary node. Ứng dụng Spring Data Redis vẫn có thể dùng những API quen thuộc như `RedisTemplate.opsForValue()`, nhưng một số công việc như **khám phá topology, kiểm tra node chủ quản của key, quét khóa trên từng node hoặc giám sát nhiều shard** cần hiểu sâu hơn về `RedisClusterConnection`.

**`RedisClusterConnection` là interface cluster-aware của Spring Data Redis**, cho phép tương tác với kết nối Redis Cluster và các thao tác đặc thù liên quan đến cụm. Tuy nhiên, nó **không biến nhiều Redis node thành một server có transaction toàn cục**. Thao tác nhiều node thường phải giải quyết các vấn đề: định tuyến theo slot, lệnh cross-slot, kết quả một phần khi node lỗi, quá trình di chuyển slot và sự khác nhau giữa primary với replica.

Bài học này đi từ nền tảng Redis Cluster tới ví dụ Java dùng `RedisClusterConnection`, sau đó phân tích cách thiết kế thao tác nhiều node đúng nghĩa trong một ứng dụng Spring Data Redis.

## 1. Redis Cluster phân phối khóa như thế nào?

Redis Cluster có 16.384 hash slot, từ `0` tới `16383`. Với khóa bình thường, Redis xác định slot từ CRC16 của tên khóa theo quy tắc Redis Cluster rồi lấy phần dư cho số slot.

```text
                       Redis Cluster
              16.384 hash slot (0..16383)
                             |
              +--------------+--------------+
              |              |              |
              v              v              v
         Primary A       Primary B       Primary C
        slot 0..5400   slot 5401..10900  slot 10901..16383
              |              |              |
              v              v              v
          Replica A      Replica B       Replica C
```

Các dải slot trong sơ đồ chỉ mang tính minh họa; số primary và phân bố slot thực tế tùy cụm.

Ví dụ:

```text
product:101        -> một slot -> một primary
product:102        -> slot khác -> có thể ở primary khác
product:103        -> slot khác -> có thể ở primary thứ ba
```

Khi ứng dụng gửi `GET product:101`, một client Redis cluster-aware như Lettuce sẽ định tuyến tới node hiện quản lý slot của khóa đó, dựa trên topology mà driver đã khám phá và các phản hồi chuyển hướng khi cần.

**Một key được định tuyến theo slot, không phải theo một node cố định mãi mãi.** Khi Redis Cluster reshard hoặc failover, node quản lý slot có thể thay đổi. Ứng dụng không nên lưu lâu dài bảng ánh xạ key → địa chỉ node rồi xem đó là sự thật bất biến.

### Hash tag để đặt các khóa liên quan vào cùng slot

Nếu cần xử lý nhiều khóa thuộc một aggregate, Redis Cluster hỗ trợ **hash tag**:

```text
cart:{user42}:items
cart:{user42}:total
cart:{user42}:version
```

Phần `{user42}` được dùng trong tính slot, nên ba khóa trên được ánh xạ vào cùng hash slot. Cách này hữu ích khi cần Lua script hoặc transaction nhiều khóa.

Đừng đặt tất cả khóa của toàn hệ thống vào một hash tag chung như `{all}`: điều đó dồn tải vào một slot, làm giảm khả năng phân tán của Cluster.

## 2. RedisClusterConnection là gì?

Các loại interface liên quan:

| API | Vai trò chính |
|---|---|
| `RedisConnectionFactory` | Cung cấp connection tới Redis; có đường lấy cluster connection khi được cấu hình phù hợp |
| `RedisConnection` | API connection mức thấp cho các lệnh Redis thông thường |
| `RedisClusterConnection` | Connection cluster-aware với các thao tác đặc thù về node/slot/topology |
| `RedisTemplate<K,V>` | API cấp cao, sử dụng serializer và connection factory |
| `StringRedisTemplate` | RedisTemplate dùng serializer chuỗi |
| `RedisClusterNode` | Mô tả một node mà Spring Data Redis biết tới trong Cluster |
| `LettuceConnectionFactory` | Connection factory dùng Lettuce, có thể được cấu hình cho Redis Cluster |

`RedisClusterConnection` phù hợp khi ứng dụng phải thao tác với **đặc điểm của cụm** thay vì chỉ thao tác một khóa.

Các khả năng điển hình:

- Lấy danh sách node mà Cluster hiện biết.
- Tra cứu thông tin tổng quan của cụm.
- Xác định node hoặc slot liên quan đến một key.
- Quét dữ liệu trên node cụ thể trong phạm vi API hỗ trợ.
- Truy vấn số khóa ở một slot hoặc thông tin cluster đặc thù.
- Gửi lệnh thông thường và để connection/driver định tuyến theo key.

**Không bắt buộc mọi thao tác Redis Cluster phải dùng `RedisClusterConnection` trực tiếp.** Với `GET`/`SET` theo key, `RedisTemplate` thường rõ ràng và dễ bảo trì hơn; driver cluster-aware vẫn có thể định tuyến phía dưới. Chỉ xuống mức connection khi cần năng lực topology, node-scoped command hoặc kiểm soát thao tác thấp hơn.

### Không nhầm với một connection vật lý duy nhất

Tên `RedisClusterConnection` không có nghĩa mọi lệnh đều được gửi tới một socket TCP hay một Redis server. Một cluster-aware connection của thư viện có thể quản lý tuyến đến nhiều node và nhiều kết nối vật lý tùy driver.

Do đó, không thể suy luận:

```text
Dùng cùng một RedisClusterConnection
             |
             v
Mọi lệnh chạy trong cùng Redis transaction   <-- SAI
```

Một transaction Redis là ranh giới trên connection/node cụ thể và chịu ràng buộc slot. Redis Cluster không cung cấp transaction nguyên tử tổng quát trên nhiều primary.

## 3. Chuẩn bị ứng dụng Spring Data Redis kết nối Cluster

Một ứng dụng Spring Boot dùng Redis với Lettuce thường có dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Ví dụ khai báo Redis Cluster trong `application.yml`:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-node-1:6379
          - redis-node-2:6379
          - redis-node-3:6379
        max-redirects: 5
      timeout: 2s
```

Các địa chỉ trên là ví dụ. Cấu hình production cần host có thật, TLS, ACL, secret, timeout và chính sách reconnect theo hạ tầng.

Những node trong cấu hình là **seed nodes** để driver có thể tiếp cận Cluster và khám phá topology. Chúng không nhất thiết là toàn bộ node trong cụm, và cũng không có nghĩa chỉ ba node đó sẽ được dùng.

### 3.1. Tự cấu hình connection factory khi cần

Nếu không dựa vào auto-configuration, có thể tạo factory như sau:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisClusterConfig {

    @Bean
    public RedisConnectionFactory redisConnectionFactory() {
        RedisClusterConfiguration cluster =
                new RedisClusterConfiguration(
                        List.of(
                                "redis-node-1:6379",
                                "redis-node-2:6379",
                                "redis-node-3:6379"));

        cluster.setMaxRedirects(5);

        return new LettuceConnectionFactory(cluster);
    }
}
```

Trong dự án Spring Boot thực tế, thường chỉ chọn **một cách cấu hình connection factory**: qua properties và auto-configuration, hoặc khai báo bean có kiểm soát. Tạo nhiều factory mà không phân biệt rõ có thể khiến `RedisTemplate`, cache manager và code dùng `RedisClusterConnection` trỏ tới những Redis deployment khác nhau.

Nếu muốn đọc từ replica, tự động refresh topology hoặc sử dụng TLS/SSL đặc thù, cần cấu hình tương ứng ở driver/Lettuce client configuration; `maxRedirects` không thay thế các cấu hình đó.

### 3.2. Đừng dùng Standalone để suy luận hành vi Cluster

Một bài test chỉ chạy `GET`/`SET` trên Redis Standalone có thể chứng minh code serializer hoạt động, nhưng không chứng minh:

- Node discovery đúng.
- Routing qua nhiều slot đúng.
- Xử lý `MOVED`/`ASK` khi reshard đúng.
- Script nhiều key có cùng slot.
- Một phần node lỗi được báo và xử lý đúng.
- Quét dữ liệu nhiều node không bỏ sót hoặc xử lý trùng.

Những yêu cầu này phải được kiểm chứng trên **Redis Cluster thật hoặc môi trường test mô phỏng Cluster đúng cấu trúc**, không chỉ một Redis server.

## 4. Lấy RedisClusterConnection từ RedisConnectionFactory

Spring Data Redis có đường lấy cluster connection từ connection factory khi factory được cấu hình theo Cluster.

```java
import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.stereotype.Service;

@Service
public class ClusterConnectionExample {

    private final RedisConnectionFactory factory;

    public ClusterConnectionExample(
            RedisConnectionFactory factory) {
        this.factory = factory;
    }

    public void inspectConnection() {
        try (RedisClusterConnection connection =
                     factory.getClusterConnection()) {

            // Các thao tác cluster-aware được thực hiện tại đây.
            System.out.println(connection.clusterGetClusterInfo());
        }
    }
}
```

Chỉ gọi `getClusterConnection()` nếu ứng dụng thực sự kết nối theo Cluster. Một connection factory không hỗ trợ Cluster có thể từ chối yêu cầu; cần xử lý như lỗi cấu hình, không tự coi đó là “Cluster có một node”.

Connection mức thấp cần được **đóng/giải phóng đúng vòng đời**. Trong ví dụ, `try-with-resources` đảm bảo `close()` khi kết thúc. Không cache một `RedisClusterConnection` do factory cấp rồi chia sẻ tùy tiện giữa nhiều thread hoặc giữ mãi qua failover/reshard.

Một số lớp triển khai connection bên dưới có quản lý connection chung hoặc pool; việc `close()` cần để abstraction trả/giải phóng tài nguyên theo đúng hợp đồng của Spring Data Redis.

## 5. Khám phá danh sách node và trạng thái Cluster

### 5.1. clusterGetNodes()

`RedisClusterConnection.clusterGetNodes()` cho phép ứng dụng nhận các node mà Spring Data Redis/driver biết tới.

```java
import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisClusterNode;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.stereotype.Service;

@Service
public class ClusterTopologyService {

    private final RedisConnectionFactory factory;

    public ClusterTopologyService(RedisConnectionFactory factory) {
        this.factory = factory;
    }

    public void printKnownNodes() {
        try (RedisClusterConnection connection =
                     factory.getClusterConnection()) {

            Iterable<RedisClusterNode> nodes =
                    connection.clusterGetNodes();

            for (RedisClusterNode node : nodes) {
                System.out.println(
                        "Node=" + node.getId()
                        + " address=" + node.getHost()
                        + ":" + node.getPort());
            }
        }
    }
}
```

Danh sách node là một **ảnh chụp topology tại thời điểm truy vấn**, không phải sổ đăng ký bất biến. Khi failover hoặc thay đổi slot, topology có thể khác đi. Nếu cần phát hiện và phản ứng khi topology đổi, phải dùng cơ chế refresh và quan sát của driver, không chạy một lần khi ứng dụng khởi động rồi giả định mãi mãi đúng.

Trong Redis Cluster có **primary và replica**. Khi duyệt node để thực hiện một thao tác dữ liệu, cần biết thao tác có nên chạy trên primary, replica hay cả hai. Ví dụ: quét các key trên tất cả primary thường phù hợp hơn quét cả replica, vì replica chứa bản sao và có thể làm dữ liệu bị đếm trùng.

### 5.2. clusterGetClusterInfo()

`clusterGetClusterInfo()` trả thông tin tổng quan của Cluster qua abstraction Spring Data Redis.

```java
public String clusterHealthSummary(
        RedisConnectionFactory factory) {

    try (RedisClusterConnection connection =
                 factory.getClusterConnection()) {
        return connection.clusterGetClusterInfo().toString();
    }
}
```

Thông tin tổng quan có ích cho health check hoặc điều tra, nhưng **một kết quả cluster state tốt không chứng minh thao tác nghiệp vụ nhiều node được thực thi nguyên tử hoặc không thể lỗi**.

Nếu ứng dụng cần giám sát node cụ thể, còn phải quan sát tình trạng connection, bộ nhớ, tốc độ lệnh, latency và độ trễ replica của từng node. Chỉ số trên một seed node không đại diện cho toàn bộ cụm.

## 6. Xác định node quản lý một key

Khi muốn kiểm tra xem một key đang được quản lý ở đâu, dùng `clusterGetNodeForKey(...)` với **byte array của key**, không phải giá trị Java chưa qua serialization.

Ví dụ:

```java
import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisClusterNode;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;

public RedisClusterNode findOwner(
        RedisConnectionFactory factory,
        String redisKey) {

    StringRedisSerializer serializer = new StringRedisSerializer();
    byte[] rawKey = serializer.serialize(redisKey);

    try (RedisClusterConnection connection =
                 factory.getClusterConnection()) {
        return connection.clusterGetNodeForKey(rawKey);
    }
}
```

Nếu ứng dụng dùng serializer khác, byte array đưa vào cơ chế tính slot phải giống **chính xác dữ liệu key vật lý mà Redis nhận được**. Một key Java có cùng chuỗi hiển thị nhưng được serialize thành hai dãy byte khác nhau có thể dẫn đến tên khóa và slot khác nhau.

Ví dụ:

```text
Java key = "product:101"

String serializer:
    Redis key bytes = UTF-8("product:101")

Serializer có prefix/định dạng khác:
    Redis key bytes = một dãy byte khác
    => key vật lý và slot có thể khác
```

Lưu ý thêm: `clusterGetNodeForKey(...)` cung cấp thông tin từ topology được biết vào thời điểm đó. Nếu Cluster đang di chuyển slot, node chủ quản thực tế có thể thay đổi ngay sau khi tra cứu. Không dùng kết quả một lần để tự dựng logic routing cố định cho hàng giờ.

### Xem hash slot trực tiếp bằng Redis CLI

```bash
redis-cli -c -h redis-node-1 -p 6379 \
    CLUSTER KEYSLOT 'cart:{user42}:items'

redis-cli -c -h redis-node-1 -p 6379 \
    CLUSTER KEYSLOT 'cart:{user42}:total'
```

Hai khóa có cùng hash tag `{user42}` phải được ánh xạ cùng slot. Điều này đặc biệt quan trọng trước khi dùng Lua script hoặc transaction nhiều khóa.

## 7. Gửi lệnh theo key qua cùng RedisClusterConnection

Cách đơn giản nhất để thao tác nhiều node là **lặp qua những key thuộc các slot khác nhau và để cluster-aware driver định tuyến từng lệnh**.

Ví dụ đọc nhiều string key:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.stereotype.Service;

@Service
public class ClusterKeyReader {

    private final RedisConnectionFactory factory;
    private final StringRedisSerializer serializer =
            new StringRedisSerializer();

    public ClusterKeyReader(RedisConnectionFactory factory) {
        this.factory = factory;
    }

    public Map<String, String> readValues(List<String> keys) {
        Map<String, String> result = new LinkedHashMap<>();

        try (RedisClusterConnection connection =
                     factory.getClusterConnection()) {

            for (String key : keys) {
                byte[] rawKey = serializer.serialize(key);

                // Cluster-aware connection/driver xác định tuyến
                // từ key/slot trong cấu hình Cluster phù hợp.
                byte[] rawValue =
                        connection.stringCommands().get(rawKey);

                result.put(key, rawValue == null
                        ? null
                        : serializer.deserialize(rawValue));
            }
        }

        return result;
    }
}
```

Nếu danh sách là:

```text
product:101
product:102
product:103
```

ba khóa có thể được phục vụ từ ba primary khác nhau. Về phía Java, ta dùng một abstraction `RedisClusterConnection`, nhưng mỗi lệnh `GET` vẫn được định tuyến theo slot.

**Ví dụ trên thực hiện các lệnh tuần tự**, không phải một operation `MGET` nguyên tử và cũng không tự pipeline. Một số thư viện/driver có thể hỗ trợ tối ưu scatter-gather hoặc pipelining theo Cluster trong các API nhất định, nhưng phải kiểm tra đúng phiên bản đang dùng thay vì suy luận từ vòng lặp này.

### Khi nào dùng RedisTemplate thay vì connection mức thấp?

Đối với một đường nghiệp vụ chỉ cần `GET`/`SET`:

```java
@Service
public class ProductCache {

    private final StringRedisTemplate redis;

    public ProductCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String get(String productId) {
        return redis.opsForValue()
                .get("product:" + productId);
    }
}
```

`StringRedisTemplate` thường là lựa chọn rõ ràng hơn vì đã quản lý serializer và connection lifecycle. Nếu factory đã cấu hình Redis Cluster, lệnh theo key vẫn được định tuyến theo Cluster.

**Dùng `RedisClusterConnection` khi thực sự cần cluster-specific API**, ví dụ khám phá node, kiểm tra placement, quét một node hoặc lập công cụ vận hành.

## 8. Quét khóa trên nhiều node bằng SCAN

Một nhiệm vụ điển hình cần biết topology là **liệt kê khóa thỏa một pattern** để làm báo cáo hoặc công cụ vận hành.

Trên Standalone, một lệnh `SCAN` được thực hiện trên một server. Trên Cluster, **một lệnh SCAN tới một node không tự quét tất cả node**. Để tìm trên toàn Cluster, phải duyệt các primary có slot và thực hiện scan từng node qua API hỗ trợ.

```text
          Pattern: cache:product:*
                      |
                      v
            Cluster node discovery
                      |
          +-----------+-----------+
          |           |           |
          v           v           v
      Primary A   Primary B   Primary C
          |           |           |
      SCAN match  SCAN match   SCAN match
          |           |           |
          +-----------+-----------+
                      |
                      v
                Tổng hợp kết quả
                      |
                      v
             Dedupe / xử lý theo lô
```

### 8.1. Ví dụ Spring Data Redis

Ở các phiên bản Spring Data Redis cung cấp overload quét node, một mẫu sử dụng là `scan(RedisClusterNode, ScanOptions)`:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.connection.RedisClusterConnection;
import org.springframework.data.redis.connection.RedisClusterNode;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.serializer.StringRedisSerializer;

public List<String> scanProductKeys(
        RedisConnectionFactory factory) {

    StringRedisSerializer serializer = new StringRedisSerializer();
    ScanOptions options = ScanOptions.scanOptions()
            .match("cache:product:*")
            .count(200)
            .build();

    List<String> result = new ArrayList<>();

    try (RedisClusterConnection connection =
                 factory.getClusterConnection()) {

        for (RedisClusterNode node : connection.clusterGetNodes()) {
            // Quét primary để tránh lặp dữ liệu replica.
            if (!node.isMaster()) {
                continue;
            }

            try (Cursor<byte[]> cursor =
                         connection.scan(node, options)) {

                while (cursor.hasNext()) {
                    result.add(
                            serializer.deserialize(cursor.next()));
                }
            }
        }
    }

    return result;
}
```

**Điều kiện của ví dụ:** API `scan(node, options)` và thuộc tính vai trò node phải tồn tại theo phiên bản Spring Data Redis đang dùng. Trước khi tích hợp, đối chiếu chữ ký phương thức và kiểu trả về của thư viện dự án; các module/phiên bản có thể khác nhau ở chi tiết abstraction.

Một số điểm cần lưu ý:

- `COUNT 200` chỉ là **gợi ý lượng công việc**, không bảo đảm Redis trả chính xác 200 key trong mỗi lượt.
- `SCAN` là cursor-based iteration, không có ảnh chụp dữ liệu nguyên tử ở một thời điểm.
- Một key có thể được trả nhiều lần, nhất là khi dữ liệu thay đổi trong lúc scan; caller cần chịu được duplicate.
- Nếu key bị thêm hoặc xóa khi scan, kết quả không phải snapshot đồng nhất.
- Reshard, failover hoặc đổi vai trò node trong lúc scan có thể làm kết quả thiếu/trùng.
- Đọc tất cả key vào một `List` có thể tốn bộ nhớ lớn. Trong production nên xử lý từng lô hoặc stream kết quả ra nơi khác với backpressure.
- Quét primary là lựa chọn phổ biến để không đếm lặp dữ liệu replica; không được mặc định rằng đọc cùng pattern trên replica tương đương với dữ liệu nhất quán ở primary.

**Không dùng `KEYS cache:product:*` trên production lớn** làm cách thay thế cho scan toàn Cluster: `KEYS` có thể gây chặn trên một node và cũng không tự đảm bảo thu thập toàn cụm.

### 8.2. Khi mục tiêu là xóa hàng loạt

Nếu cần xóa nhiều khóa theo pattern, không nên mặc định “SCAN rồi DEL tất cả ngay” là thao tác không tốn chi phí:

```text
SCAN từng primary
    |
    v
Thu các key phù hợp
    |
    v
Chia lô nhỏ
    |
    v
DEL/UNLINK theo key hoặc nhóm tương thích slot
    |
    v
Theo dõi lỗi, tốc độ và số lần retry
```

`UNLINK` có thể giúp giảm thời gian giải phóng bộ nhớ đồng bộ của một số value, nhưng vẫn tạo tải và cần dùng đúng API. Thao tác xóa theo pattern **không nguyên tử trên toàn Cluster**. Các key có thể được tạo lại trong lúc scan hoặc xóa.

Với dữ liệu cache lớn, thường nên cân nhắc prefix phiên bản hoặc cơ chế invalidation có kiểm soát thay vì quét/xóa hàng triệu khóa trong request HTTP.

## 9. Đếm key theo slot và theo node

Redis Cluster có thể cung cấp thông tin số key ở một slot và một số lệnh dùng để khảo sát key thuộc slot. Spring Data Redis hỗ trợ các thao tác cluster-scoped phù hợp ở mức `RedisClusterConnection` trong những phiên bản có API tương ứng.

Ý nghĩa của những tác vụ này:

- Xác định slot nào đang tập trung nhiều key.
- Kiểm tra việc phân phối dữ liệu sau di chuyển slot.
- Phục vụ công cụ chẩn đoán hoặc migration.
- Đối chiếu xem các khóa liên quan có cùng slot như thiết kế không.

Ở cấp Redis CLI, một số lệnh liên quan:

```bash
redis-cli -c -h redis-node-1 -p 6379 CLUSTER INFO
redis-cli -c -h redis-node-1 -p 6379 CLUSTER NODES
redis-cli -c -h redis-node-1 -p 6379 CLUSTER SLOTS
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT 'cart:{user42}:items'
```

Thông tin slot count hoặc node count cần được đặt trong ngữ cảnh **thời điểm, node được hỏi và quá trình reshard**. Đừng xem một số liệu nhất thời là bộ đếm nghiệp vụ chính xác. Khả năng thay đổi topology và key trong khi đo có thể khiến một báo cáo tổng hợp không phản ánh một snapshot nguyên tử.

### Không nhầm node count với số bản ghi duy nhất

Nếu quét cả primary lẫn replica, cùng một key có thể xuất hiện tại nhiều node vì replication. Cộng số key trên tất cả node mà không phân biệt vai trò sẽ **đếm trùng bản sao**, không phải số key logic của Cluster.

Nếu chỉ cần số key cache/đối tượng nghiệp vụ, nên xem có thể duy trì bộ đếm/inventory ở nguồn dữ liệu phù hợp không, thay vì thực hiện full-cluster scan mỗi khi API được gọi.

## 10. Lệnh nhiều key và giới hạn CROSSSLOT

Một số lệnh Redis chấp nhận nhiều key, ví dụ:

```redis
MGET product:101 product:102
MSET product:101 value1 product:102 value2
```

Trên Redis Cluster, những lệnh nhiều key ở một node thường yêu cầu tất cả key thuộc **cùng hash slot**. Nếu key khác slot, Redis có thể trả lỗi `CROSSSLOT` hoặc client/driver phải xử lý bằng cách chia thao tác theo từng slot khi API cụ thể hỗ trợ.

Không suy luận rằng mọi overload của `multiGet`/`multiSet` trong Spring Data Redis có cùng hành vi trên mọi driver và version. Một số implementation có thể cung cấp thao tác scatter-gather ở mức client đối với một số lệnh, nhưng những thao tác ấy **không trở thành nguyên tử trên toàn Cluster**.

### So sánh ba phương án đọc nhiều key

| Cách làm | Đặc tính | Giới hạn |
|---|---|---|
| Gọi `GET` tuần tự cho từng key | Mỗi key định tuyến riêng; dễ kiểm soát lỗi từng lệnh | Nhiều round-trip, chậm với số lượng lớn |
| `MGET` các key cùng slot | Một lệnh Redis lấy nhiều string value | Chỉ dùng đúng kiểu dữ liệu và ràng buộc slot |
| Scatter-gather/pipeline theo node | Có thể tăng throughput cho các key khác slot | Phụ thuộc driver/API; không có snapshot/transaction toàn cục |

Với một lô lớn, hãy nhóm theo slot hoặc theo owner node nếu thật sự cần tối ưu giao tiếp, nhưng nhớ rằng owner có thể đổi khi reshard. Không hardcode cách chia bằng địa chỉ node đã tra cứu lâu trước đó.

### Hash tag cho nhóm key cần cùng thao tác

```text
order:{1001}:state
order:{1001}:items
order:{1001}:payment
```

Những key có chung `{1001}` có thể dùng trong cùng lệnh nhiều key hoặc Lua script tương thích Cluster. Đổi lại, tất cả dữ liệu của một aggregate sẽ cùng slot. Việc phân bố hash tag phải chọn đủ hạt nhỏ để không dồn mọi aggregate vào một primary.

## 11. Giao dịch MULTI/EXEC trong Redis Cluster

Redis transaction `MULTI`/`EXEC` có ranh giới thực thi trên node/connection phù hợp. Redis Cluster không biến transaction nhiều slot trở thành một distributed transaction hai pha.

```text
Primary A (slot X)             Primary B (slot Y)
       |                              |
       | MULTI                        |
       | SET key-X                    | SET key-Y
       | EXEC                         |
       |                              |
       +------ Không có commit nguyên tử chung ------+
```

Nếu một nghiệp vụ cần cập nhật nhiều key cùng slot, có thể dùng transaction Redis hoặc Lua script thích hợp. Nếu key nằm ở các slot/primary khác nhau, phải thiết kế lại ranh giới nhất quán hoặc dùng một hệ thống transaction có bảo đảm phù hợp.

**Cùng một `RedisClusterConnection` không có nghĩa các lệnh trên các node khác nhau cùng một `MULTI`.** Việc gọi `multi()`/`exec()` mà không nắm rõ slot, connection routing và trạng thái transaction có thể gây lỗi hoặc tạo giả định nhất quán sai.

Trong Spring Data Redis, `SessionCallback` thường được dùng cho transaction Redis qua `RedisTemplate` imperative. Nhưng không mặc định mô hình session đó cho phép transaction xuyên toàn Cluster: nó vẫn chịu giới hạn Redis server và hash slot.

### Transaction Redis không rollback lỗi runtime theo kiểu SQL

Ngay cả khi tất cả key cùng slot và `EXEC` chạy được, một Redis command lỗi runtime trong transaction không khiến Redis tự hoàn tác tất cả lệnh đã thành công. Vì vậy, “cùng slot” giải quyết khả năng **thực thi cùng ranh giới Redis**, không thay thế validation và thiết kế phục hồi.

## 12. Lua scripting trên Cluster

Lua script thường được dùng để kiểm tra điều kiện và ghi dữ liệu trong một lần xử lý phía Redis:

```lua
-- KEYS[1] = inventory:{sku42}:available
-- ARGV[1] = requested quantity

local qty = tonumber(ARGV[1])
if not qty or qty <= 0 or qty ~= math.floor(qty) then
    return -1
end

local rawStock = redis.call('GET', KEYS[1])
local stock = tonumber(rawStock)

if not stock or stock < qty then
    return 0
end

redis.call('DECRBY', KEYS[1], ARGV[1])
return 1
```

Đây là một ví dụ một-key, nên không vướng tình huống multi-slot. Nếu script truy cập nhiều key:

```text
inventory:{sku42}:available
inventory:{sku42}:reserved
inventory:{sku42}:processed
```

các key cần phù hợp với giới hạn slot của Redis Cluster và được khai báo rõ qua `KEYS` theo hợp đồng script.

Scripting có hai ưu điểm so với đọc trên client rồi ghi:

1. Điều kiện được kiểm tra ngay trên server, tránh khoảng trống giữa các round-trip.
2. Các bước trong script không bị lệnh của client khác chen giữa trên node thực thi.

Nhưng:

- Script không chạy xuyên nhiều primary như một transaction phân tán.
- Script chạy lâu có thể chặn các lệnh khác trên primary đó.
- Nếu một lệnh ghi thành công rồi script gặp lỗi runtime ở bước sau, ghi trước đó **không tự rollback**.
- Khi client timeout hoặc failover giữa `EVAL`, kết quả có thể không xác định từ góc nhìn ứng dụng.
- `EVALSHA` có thể gặp `NOSCRIPT` trên node khác hoặc sau thay đổi script cache; executor/driver cần xử lý đúng.

### Khi nào không cần RedisClusterConnection trực tiếp cho script?

Với một script nghiệp vụ, thường nên khai báo `RedisScript<T>` và dùng `RedisTemplate.execute(...)`. Kết nối đã cluster-aware sẽ định tuyến theo khóa script theo khả năng tương ứng. Chỉ dùng API thấp hơn khi cần điều khiển cluster-specific behavior hoặc có lý do vận hành.

Không nên tự lựa chọn primary bằng địa chỉ IP rồi gửi một script nhiều khóa mà không kiểm tra hash slot. Để driver định tuyến theo key và kiểm tra rõ điều kiện slot là cách dễ bảo trì hơn.

## 13. Pipelining trên nhiều node

Pipelining giảm round-trip bằng cách gửi nhiều command trước khi thu hồi tất cả kết quả. Nhưng trên Redis Cluster, các key có thể phân bố trên nhiều primary, nên hành vi pipeline phụ thuộc driver và cấu hình connection.

```text
Java application
      |
      +---- pipeline commands for slot A ---> Primary A
      |
      +---- pipeline commands for slot B ---> Primary B
      |
      +---- pipeline commands for slot C ---> Primary C
```

Những điểm cần kiểm tra:

- API pipeline cụ thể có hỗ trợ Cluster không?
- Driver định tuyến từng command theo key và gom kết quả như thế nào?
- Thứ tự kết quả được liên hệ lại với thứ tự lệnh ra sao?
- Một node chậm có kéo dài cả batch không?
- Khi một node lỗi, kết quả các node khác có thể đã được áp dụng chưa?
- Có giới hạn số command, kích thước payload và memory hay không?

**Pipelining không cung cấp tính nguyên tử toàn cụm.** Một batch có thể thay đổi dữ liệu ở primary A rồi lỗi tại primary B. Không retry cả batch mù quáng nếu chứa lệnh tăng/giảm bộ đếm hoặc ghi sự kiện có tác dụng lặp.

Đối với nhiều key chỉ cần đọc, cân nhắc dùng những API cấp cao mà driver hỗ trợ scatter-gather. Đối với thao tác ghi nhạy cảm, thiết kế idempotency và đối soát thay vì dựa vào pipeline như một ranh giới commit.

## 14. Redis Cluster reshard và phản hồi MOVED/ASK

Topology Cluster không bất biến. Khi chuyển slot giữa các primary, client có thể nhận:

- **`MOVED`:** slot hiện thuộc node khác; client cần dùng tuyến mới và cập nhật topology theo cơ chế hỗ trợ.
- **`ASK`:** chuyển hướng tạm thời thường xuất hiện trong giai đoạn di chuyển slot; client phải tuân thủ cơ chế ASK để gửi yêu cầu đến node đích phù hợp.

```text
Client tin rằng slot S ở Primary A
                 |
                 v
          Gửi GET key(S)
                 |
                 v
     Primary A trả MOVED/ASK
                 |
                 v
     Cluster-aware driver xử lý
     chuyển hướng theo quy tắc
                 |
                 v
        Gửi tới node phù hợp
```

Một số giới hạn:

1. Driver có thể tự xử lý chuyển hướng, nhưng mức độ và số lần retry phụ thuộc cấu hình.
2. Khi topology đang đổi, một lệnh khảo sát owner trước đó có thể lập tức trở nên cũ.
3. Nếu vượt giới hạn redirect, ứng dụng phải xử lý lỗi chứ không tự cho rằng Redis đã thực hiện lệnh.
4. Với lệnh có side effect, network timeout khiến client không chắc kết quả — không giống một phản hồi `MOVED` rõ ràng trước thực thi.
5. Không coi đổi topology là tín hiệu cần xóa toàn bộ cache/khóa Redis.

Hãy kiểm tra hành vi Lettuce topology refresh và redirect trong đúng môi trường triển khai. Một seed node hoạt động được không bảo đảm các node được quảng bá trong topology đều truy cập được từ mạng ứng dụng, đặc biệt với container hoặc NAT.

## 15. Primary, replica và tính nhất quán khi đọc

Redis Cluster thường có replica cho các primary. Replication Redis về cơ bản là bất đồng bộ, nên một replica có thể chậm hơn primary.

```text
Application
      |
      +---- SET key ---> Primary A
      |                       |
      |                 Async replication
      |                       |
      +---- GET key ---> Replica A
                              |
                              v
                       Có thể còn value cũ
```

Nếu Lettuce được cấu hình đọc từ replica, một lệnh `GET` sau `SET` có thể thấy dữ liệu cũ dù hai lệnh được gọi tuần tự trong Java.

Cần phân biệt:

- **Đọc phục vụ báo cáo, dashboard, cache phụ:** đôi khi chấp nhận độ trễ replica.
- **Đọc xác nhận quyền, số dư, tồn kho hoặc điều kiện ghi:** thường cần nguồn dữ liệu authoritative hoặc cơ chế nhất quán chặt hơn.
- **Script ghi:** phải chạy trên primary/slot phù hợp; không suy luận read preference replica làm mọi thao tác đọc/ghi/script chạy ở cùng node.

Mỗi khi bổ sung replica-read policy, cần kiểm tra:

- Mức stale có thể chấp nhận.
- Hành vi khi replica bị lag hoặc không sẵn sàng.
- Read-your-writes có được yêu cầu ở một API cụ thể không.
- Failover ảnh hưởng tuyến đọc/ghi và script cache ra sao.

Đọc trên replica không làm thao tác nhiều node “nhanh hơn mà hoàn toàn nhất quán” theo mặc định.

## 16. Failover và trạng thái kết quả không xác định

Giả sử ứng dụng chạy một lô thay đổi trên nhiều key:

```text
1. SET product:101 READY (Primary A) -> thành công
2. INCR metrics:updated (Primary B) -> đã gửi
3. Connection reset trước khi nhận response của bước 2
4. Primary B failover
```

Ứng dụng không thể chắc chắn chỉ từ exception liệu bước 2 đã tăng bộ đếm hay chưa. Nếu retry toàn bộ lô:

- Bước 1 có thể chỉ là ghi lại cùng value (khi không có cạnh tranh khác).
- Bước 2 có thể làm bộ đếm tăng thêm một lần nữa.
- Một số dữ liệu có thể không xuất hiện trên primary mới ngay theo kỳ vọng vì replication/failover.

Do đó, cần phân biệt **các loại lỗi**:

| Loại lỗi | Đánh giá phù hợp |
|---|---|
| `CROSSSLOT` được trả rõ khi command chưa thực thi | Cần sửa thiết kế key/slot; không retry vô nghĩa |
| `MOVED`/`ASK` rõ ràng | Driver cần xử lý redirect và topology |
| `NOSCRIPT` | Script chưa nằm trong cache của node được hỏi; executor cần nạp/gọi lại theo cách hỗ trợ |
| Timeout/network reset | Có thể không biết command đã áp dụng hay chưa |
| Lỗi sau một số ghi thành công | Có thể đã tạo trạng thái một phần trên nhiều key/node |
| Replica trả dữ liệu cũ | Có thể do replication lag, không đồng nghĩa primary chưa ghi |
| ACL/permission error | Lỗi cấu hình quyền; retry không sửa được nếu không đổi quyền |

Với thao tác ghi nhạy cảm, nên dùng **operation ID, idempotency, version check và cơ chế đối soát**. Đặc biệt không dùng `INCR` hoặc `LPUSH` trong một vòng retry không giới hạn khi không có cách phát hiện đã thực hiện trước đó.

## 17. Một transaction xuyên Cluster cần giải quyết ở tầng kiến trúc

Giả sử mỗi node giữ một phần dữ liệu:

```text
Primary A: account:alice:balance
Primary B: account:bob:balance
```

Yêu cầu chuyển tiền giữa hai tài khoản cần tính đúng **ghi nợ bên A và ghi có bên B**. Không thể chỉ dùng hai command trong một `RedisClusterConnection` rồi mặc định có all-or-nothing.

Những hướng thiết kế phụ thuộc yêu cầu:

- Đưa thao tác quyết định số dư vào database có transaction thích hợp.
- Tổ chức sổ cái/event log bền và các projection Redis chỉ phục vụ đọc.
- Nếu nghiệp vụ có thể giới hạn trong một aggregate/slot, sắp xếp key cùng hash tag rồi dùng Lua script hoặc transaction phù hợp.
- Nếu phải phối hợp nhiều node, xây workflow có idempotency, trạng thái chuyển tiếp và đối soát theo mô hình saga/compensation; không gọi đây là Redis transaction toàn cụm.
- Với dữ liệu tài chính hoặc trạng thái nhạy cảm, ưu tiên bất biến nghiệp vụ và nguồn sự thật hơn tối ưu round-trip.

Một key slot layout tốt có thể giảm nhu cầu cross-slot cho những thao tác thuộc cùng aggregate, nhưng không thể dùng một hash tag toàn hệ thống để thay cho thiết kế consistency.

## 18. Các thao tác quản trị node cần tách khỏi đường nghiệp vụ

`RedisClusterConnection` và các lệnh `CLUSTER` mức thấp có thể cung cấp chức năng liên quan tới membership, slot allocation, failover hoặc thay đổi topology trong một số API/phiên bản.

**Không để HTTP request thông thường tự quản trị Redis Cluster** chỉ để thực hiện một thao tác nghiệp vụ. Ví dụ:

- Không gọi thao tác di chuyển slot như một cách giải quyết `CROSSSLOT` tạm thời.
- Không tự đánh dấu node failed hoặc kích hoạt failover trong đường xử lý đơn hàng.
- Không tạo/xóa slot tùy tiện khi một lệnh GET thất bại.
- Không cấp quyền cluster-admin cho service chỉ cần đọc/ghi cache.

Các tác vụ vận hành nên được quản lý bằng công cụ và quy trình hạ tầng có phân quyền, giám sát, audit và rollback plan tương ứng. Ứng dụng nghiệp vụ thường chỉ cần quyền với các key/command thực tế, không cần quyền đổi topology.

### Cluster discovery cũng là dữ liệu nhạy cảm

Danh sách node và địa chỉ mạng có thể là thông tin nội bộ. Không trả nguyên `CLUSTER NODES`, credential hoặc địa chỉ riêng của hạ tầng ra public API. Nếu cần health endpoint, chỉ công bố trạng thái khái quát và giữ chi tiết node trong hệ thống quan sát có phân quyền.

## 19. Kiểm thử thao tác nhiều node

Một bộ test cho Redis Cluster nên bao gồm **nhiều slot và nhiều primary thực sự**, không chỉ dùng một key quen thuộc.

### 19.1. Kiểm tra routing bình thường

1. Tạo Cluster thử nghiệm có nhiều primary.
2. Cấu hình Spring Data Redis trỏ tới seed node của Cluster.
3. Viết/read các key có slot khác nhau.
4. Gọi `clusterGetNodes()` để kiểm tra discovery.
5. Gọi `clusterGetNodeForKey(...)` cho từng key để quan sát owner.
6. Đảm bảo serializer tạo key bytes đúng như những gì Redis thực lưu.

### 19.2. Kiểm tra cùng slot và khác slot

```text
cart:{user42}:items
cart:{user42}:total          -> cùng slot

cart:{user42}:items
cart:{user99}:items          -> thường khác slot
```

Thử command nhiều key hoặc script theo hợp đồng:

- Với key cùng tag: phải đi vào đường thực thi tương thích slot.
- Với key không cùng slot: phải xử lý từ chối hoặc chia việc theo đúng API, không giả định transaction nguyên tử.
- Không dựa duy nhất vào hình dạng chuỗi nếu serializer có thể đổi byte key.

### 19.3. Kiểm tra SCAN khi đang thay đổi dữ liệu

Trong khi scan trên nhiều node:

- Thêm một số key mới.
- Xóa một số key.
- Thử trường hợp cursor trả một phần dữ liệu.
- Thử gián đoạn kết nối một node.
- Xem ứng dụng có chấp nhận duplicate/partial result và báo lỗi không.

Một công cụ quét để kiểm kê/đối soát cần thể hiện rằng kết quả là **best effort tại thời điểm quan sát**, không phải snapshot nhất quán tuyệt đối.

### 19.4. Kiểm tra reshard và failover

Dưới môi trường thử nghiệm có kiểm soát:

- Di chuyển một slot sang primary khác.
- Quan sát `MOVED`/`ASK` và khả năng driver tự cập nhật tuyến.
- Đọc/ghi key thuộc slot đang chuyển.
- Thử lỗi kết nối giữa một chuỗi thao tác nhiều key.
- Thử failover primary và đo thời gian phục hồi.
- Kiểm tra script cache/`NOSCRIPT` sau thay đổi node.
- Đảm bảo logic retry không tạo tác dụng phụ trùng.

Đây là các bài test về khả năng ứng dụng làm việc với **Cluster động**, không phải chỉ kiểm tra `PING`.

## 20. Giám sát theo từng node, từng slot và toàn Cluster

Một Redis Cluster có thể hoạt động ở trạng thái tổng thể tốt nhưng một primary cụ thể quá tải hoặc replica của nó bị lag.

Những chỉ số nên thu thập:

| Phạm vi | Chỉ số cần quan sát |
|---|---|
| **Toàn Cluster** | cluster state, số slot được gán, node fail, số redirect, sự kiện reshard/failover |
| **Primary node** | CPU, memory, command latency, connected clients, blocked clients, network I/O |
| **Replica node** | replication lag, link state, khả năng catch-up |
| **Ứng dụng** | p50/p95/p99 từng loại command, timeout, retry, redirect failures |
| **Dữ liệu** | Phân bố hot key/slot, memory skew, kích thước key/value |
| **Batch nhiều node** | Số thành công, số thất bại, loại command và key range cần retry |
| **SCAN/maintenance** | Thời gian scan, số node quét, lỗi từng node, duplicates, độ dài batch |

Redis CLI:

```bash
redis-cli -c -h redis-node-1 -p 6379 CLUSTER INFO
redis-cli -c -h redis-node-1 -p 6379 CLUSTER NODES
redis-cli -c -h redis-node-1 -p 6379 CLUSTER SLOTS

redis-cli -h redis-node-1 -p 6379 INFO stats
redis-cli -h redis-node-1 -p 6379 INFO memory
redis-cli -h redis-node-1 -p 6379 INFO commandstats
redis-cli -h redis-node-1 -p 6379 SLOWLOG GET 10
```

Với lệnh `INFO`, nên thu thập từ từng node thích hợp để xem skew. `SLOWLOG` phản ánh thời gian thực thi lệnh phía Redis, không cộng thời gian mạng hoặc chờ phía client. Không dùng `MONITOR` kéo dài hoặc `KEYS *` trên Redis production bận rộn chỉ để lấy metric.

### Không nhầm “Cluster healthy” với “batch thành công toàn bộ”

Một batch có thể ghi thành công trên primary A và thất bại trên primary B dù `CLUSTER INFO` cho trạng thái tổng thể là healthy. Health check đo năng lực hạ tầng, còn kết quả batch cần **đối soát theo từng operation**.

## 21. Quy tắc xử lý kết quả một phần

Khi một thao tác nghiệp vụ liên quan nhiều key thuộc nhiều node, nên có hợp đồng trả kết quả rõ:

```text
Input:
  keys = [key-A, key-B, key-C]

Output:
  key-A -> SUCCESS
  key-B -> FAILED (timeout; outcome unknown)
  key-C -> NOT_ATTEMPTED
```

Không biến ba trạng thái này thành một boolean `false` và retry tất cả mà không phân biệt.

Một mô hình Java có thể dùng kiểu kết quả theo từng key:

```java
public enum OperationStatus {
    SUCCESS,
    FAILED,
    UNKNOWN,
    NOT_ATTEMPTED
}

public record KeyOperationResult(
        String redisKey,
        OperationStatus status,
        String errorCode) {
}
```

Các quy tắc:

- **SUCCESS** khi có phản hồi xác nhận theo hợp đồng command.
- **FAILED** khi biết rõ thao tác bị từ chối và không có side effect.
- **UNKNOWN** khi timeout/lỗi mạng khiến không thể khẳng định đã áp dụng hay chưa.
- **NOT_ATTEMPTED** khi logic dừng trước khi gửi lệnh tới key đó.

Với `UNKNOWN`, cần kiểm tra trạng thái, operation ID hoặc version trước khi retry. Với command có side effect không idempotent như tăng số lượng, không chỉ nhìn “không nhận được response” để quyết định gửi lại.

Nếu nghiệp vụ yêu cầu all-or-nothing xuyên các node, một danh sách kết quả một phần chỉ giúp quan sát, **không giải quyết được transaction**. Lúc đó cần thay đổi mô hình dữ liệu hoặc bổ sung giao thức phối hợp/đối soát thích hợp.

## 22. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Coi `RedisClusterConnection` là một node duy nhất | Tưởng tất cả command cùng transaction/connection | Hiểu abstraction cluster-aware và routing theo slot |
| Hardcode key → IP node | Sai khi reshard/failover | Để driver khám phá/định tuyến và refresh topology |
| Quét `SCAN` một node rồi coi là toàn Cluster | Thiếu key ở node khác | Duyệt các primary phù hợp |
| Quét cả primary lẫn replica rồi cộng số key | Đếm trùng bản sao | Chọn primary và xác định rõ phạm vi |
| Dùng `KEYS *` để kiểm kê production | Gây tải, có thể chặn node | Dùng SCAN theo lô và giới hạn |
| Không đóng cluster connection/cursor | Rò rỉ tài nguyên | `try-with-resources` hoặc giải phóng theo API |
| Dùng Java key khác serializer trong thao tác slot | Tính nhầm placement | Sử dụng key bytes thực |
| Gọi `MGET` nhiều slot rồi kỳ vọng atomic | Lỗi cross-slot hoặc chia lệnh không nguyên tử | Gom key theo slot, hiểu API scatter-gather |
| Cho mọi key cùng `{all}` | Hot slot và mất phân tán | Hash tag theo aggregate phù hợp |
| Dùng `MULTI`/Lua xuyên nhiều primary | Không có transaction toàn Cluster | Thiết kế lại ranh giới nhất quán |
| Pipeline nhiều node rồi coi là một commit | Có thể hoàn tất một phần | Idempotency/đối soát từng operation |
| Retry cả batch sau network timeout | Có thể lặp `INCR`/`LPUSH` | Theo dõi outcome và operation ID |
| Tin replica luôn trả dữ liệu mới nhất | Có thể đọc stale | Primary read khi cần consistency |
| Không test MOVED/ASK/failover | Routing lỗi trong reshard | Test Cluster động và cấu hình driver |
| Cấp quyền quản trị Cluster cho service | Rủi ro thao tác đổi topology | Principle of least privilege |
| Dùng node metrics làm ACK nghiệp vụ | Đánh giá sai kết quả nhiều node | Theo dõi kết quả từng thao tác |

## 23. Quy trình lựa chọn API

```text
Cần thao tác với Redis Cluster?
                |
                v
       Chỉ đọc/ghi key thông thường?
           +----+----+
           |         |
          Có        Không
           |         |
           v         v
    RedisTemplate   Cần xem topology,
    cluster-aware   slot, node/scan?
           |              |
           |              v
           |     RedisClusterConnection
           |              |
           +------+-------+
                  |
                  v
            Thao tác nhiều key?
             +----+----+
             |         |
            Không     Có
             |         |
             v         v
        Định tuyến   Có cần atomicity
        theo slot    giữa các key?
                         |
                    +----+----+
                    |         |
                   Có        Không
                    |         |
                    v         v
              Key cùng slot?  Lệnh từng key/
                    |         scatter-gather
               +----+----+    có kiểm soát
               |         |
              Có        Không
               |         |
               v         v
         Lua/MULTI   Đổi mô hình dữ liệu,
         phù hợp    dùng nguồn transaction
                    hoặc workflow bù
               |         |
               +----+----+
                    |
                    v
          Test reshard/failover,
          timeout, retry/idempotency
                    |
                    v
            Giám sát từng node
            và kết quả từng lệnh
```

## 24. Tổng kết

`RedisClusterConnection` giúp Spring Data Redis làm việc với những khía cạnh cụ thể của Redis Cluster: **khám phá node, tra vị trí key, kiểm tra topology, quét trên từng node và gửi lệnh được định tuyến theo slot**. Đây là công cụ quan trọng khi xây chức năng vận hành, kiểm kê, chẩn đoán hoặc xử lý lô mà dữ liệu phân bố trên nhiều primary.

Nhưng cần giữ ranh giới rõ ràng:

1. **Connection cluster-aware không phải transaction toàn Cluster.** Các lệnh ở những primary khác nhau có thể thành công hoặc thất bại riêng.
2. **Slot là đơn vị định tuyến.** Multi-key command, Lua script và Redis transaction phải tuân thủ ràng buộc slot; hash tag giúp gom khóa cùng aggregate.
3. **Topology có thể thay đổi.** Reshard, `MOVED`/`ASK` và failover khiến thông tin owner tại một thời điểm không phải sự thật lâu dài.
4. **Quét nhiều node không tạo snapshot nguyên tử.** SCAN cần cursor, giới hạn tải, chấp nhận duplicate và có kế hoạch xử lý khi node đổi.
5. **Hệ thống phải chịu được kết quả không xác định.** Timeout, mất kết nối và retry với lệnh có side effect đòi hỏi idempotency, version hoặc đối soát.
6. **Theo dõi toàn cụm lẫn từng node.** Primary quá tải, replica lag hoặc một slot nóng không thể được đánh giá chỉ qua một kết quả `PING`.

Với nghiệp vụ chỉ cần `GET`/`SET` theo key, hãy ưu tiên `RedisTemplate` cluster-aware để tận dụng serializer và lifecycle. Khi cần thực sự làm việc theo node/slot, dùng `RedisClusterConnection` nhưng luôn xem thao tác nhiều nút là **một bài toán phân tán có giới hạn nhất quán và lỗi một phần**, không phải một chuỗi Redis command nguyên tử trên toàn Cluster.

