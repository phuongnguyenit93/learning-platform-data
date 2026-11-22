# Khả năng pipeline trên Redis Cluster và khác biệt giữa các trình điều khiển trong Spring Data Redis

**Pipelining** là kỹ thuật gửi nhiều lệnh Redis liên tiếp mà không đợi phản hồi của từng lệnh, sau đó nhận kết quả theo lô. Trong Redis Standalone, một kết nối thường đi tới một server nên luồng lệnh tương đối dễ hình dung. Nhưng **Redis Cluster phân tán key theo hash slot**: các lệnh trong cùng một pipeline có thể cần đi đến những master node khác nhau. Vì vậy, câu hỏi “Spring Data Redis có hỗ trợ pipeline trên Cluster không?” phải được trả lời ở ba lớp:

1. **Redis server:** mỗi node vẫn hiểu giao thức pipeline trên kết nối TCP; Cluster có quy tắc định tuyến slot và hạn chế đối với lệnh nhiều key.
2. **Driver Java (Lettuce hoặc Jedis):** quyết định có thể gom lệnh, chia lệnh theo node, quản lý nhiều kết nối, xử lý chuyển hướng `MOVED`/`ASK` và ghép kết quả hay không.
3. **Spring Data Redis:** `RedisTemplate.executePipelined(...)` sử dụng adapter `RedisConnection` của driver và có những giới hạn riêng, không đồng nhất với mọi tính năng của API native.

**Không được suy ra rằng “driver hỗ trợ Redis Cluster” đồng nghĩa “mọi phương thức pipeline của Spring Data Redis đều được hỗ trợ trên Cluster”.** Tài liệu Spring Data Redis ở các nhánh 3.5/4.1 còn lưu ý phạm vi hỗ trợ pipeline là Redis Standalone, đồng thời mô tả hỗ trợ Redis Cluster dựa trên Lettuce và ngoại lệ của một số lệnh cross-slot. Hãy xác nhận **phiên bản Spring Data Redis + connector + thao tác cụ thể** trước khi dùng `executePipelined` trên Cluster. Nếu cần batch cross-node và API Spring không cung cấp, có thể dùng API native cluster-aware của driver một cách có kiểm soát.

## 1. Pipeline làm giảm round trip như thế nào?

Không dùng pipeline:

```text
Ứng dụng       Redis
   | SET k1 v1   |
   |----------->  |
   | <------ OK   |
   | SET k2 v2   |
   |----------->  |
   | <------ OK   |
   | SET k3 v3   |
   |----------->  |
   | <------ OK   |
```

Ứng dụng phải chờ phản hồi trước khi gửi lệnh kế tiếp. Nếu thời gian khứ hồi mạng (RTT) là 2 ms, 500 lệnh tuần tự có thể tiêu tốn đáng kể thời gian chỉ để chờ mạng, chưa tính chi phí xử lý.

Với pipeline:

```text
Ứng dụng       Redis
   | SET k1 v1   |
   | SET k2 v2   |
   | SET k3 v3   |
   |----------->  |  Nhận/xử lý các lệnh
   | <------ OK   |
   | <------ OK   |
   | <------ OK   |
```

Đây là biểu diễn **logic** của việc giảm chờ phản hồi; driver có thể flush dữ liệu qua một hoặc nhiều lần ghi socket. Pipeline không có nghĩa Redis thực thi toàn bộ lệnh trong một CPU instruction hoặc một giao dịch nguyên tử.

### Pipeline khác batch command và transaction

| Khái niệm | Cơ chế | Đảm bảo chính |
|---|---|---|
| Nhiều lệnh bình thường | Gửi một lệnh, chờ một phản hồi | Đơn giản nhưng có nhiều lượt chờ mạng |
| **Pipeline** | Gửi liên tiếp nhiều lệnh, nhận phản hồi sau | Giảm chi phí round trip; **không tự tạo transaction** |
| Lệnh nhiều key, ví dụ `MSET k1 v1 k2 v2` | Một lệnh Redis chứa nhiều key | Tuân theo quy tắc hash slot của **một lệnh** |
| `MULTI`/`EXEC` | Queue và thực thi các lệnh liên tiếp, không bị client khác chen vào | Nhóm lệnh không bị xen giữa; không có rollback kiểu SQL |
| Lua / Redis Function | Thực thi logic trong Redis | Đơn vị thực thi nguyên tử theo semantics script/function; có hạn chế khác |

Một pipeline gồm 100 lệnh `SET` vẫn là **100 lệnh riêng**. Một số lệnh có thể thành công và những lệnh khác thất bại. Mất kết nối khi đang gửi/nhận phản hồi có thể tạo trạng thái không rõ lệnh nào đã thực thi; cần thiết kế retry an toàn.

Redis còn cần giữ kết quả chờ client đọc. Vì vậy không gom số lệnh vô hạn trong một pipeline: chia thành các **batch có giới hạn**, đo bộ nhớ, latency và thông lượng.

## 2. Vì sao Redis Cluster phức tạp hơn Standalone?

Redis Cluster chia keyspace thành **16.384 hash slot**. Với một key thông thường, slot được tính bằng:

```text
slot = CRC16(key) mod 16384
```

Mỗi master node phụ trách một tập slot. Ví dụ giả định:

```text
Redis Cluster

Master A          Master B          Master C
slots 0..5000     slots 5001..10000 slots 10001..16383
    |                  |                   |
    +-- item:1         +-- item:2          +-- item:3
```

Ví dụ trên chỉ nhằm minh họa phân bố; slot thật của `item:1`, `item:2` và `item:3` cần tính bằng `CLUSTER KEYSLOT`, không thể suy ra từ tên key như hình.

Client cluster-aware cần biết key thuộc slot nào và node nào đang sở hữu slot. Khi key của một batch phân bố trên nhiều master, client phải có khả năng:

- Tính slot tương ứng từ **byte của key sau serialization**.
- Chọn kết nối đúng node cho mỗi lệnh.
- Gửi lệnh theo lô qua các kết nối/node liên quan.
- Nhận kết quả và ghép chúng lại theo cách API cam kết.
- Xử lý topology thay đổi, chuyển hướng `MOVED` hoặc `ASK` và lỗi từng phần.

Đó là trách nhiệm của **cluster-aware client**, không phải tính năng tự động của giao thức pipeline trên một socket TCP.

### 2.1. Hai vấn đề cross-slot khác nhau

Phải phân biệt:

**Trường hợp A — nhiều lệnh đơn, mỗi lệnh thao tác một key:**

```redis
SET user:100:name "An"
SET user:200:name "Binh"
GET user:100:name
```

Các key có thể thuộc những slot khác nhau. **Về nguyên tắc**, cluster-aware client có thể định tuyến từng lệnh đến node phụ trách rồi tối ưu cách gửi lệnh theo lô. Những lệnh đơn không tự tạo lỗi `CROSSSLOT` chỉ vì xuất hiện trong cùng một batch client-side. Tuy nhiên, API pipeline cụ thể có thể không hỗ trợ batch cross-node.

**Trường hợp B — một lệnh tự nó chứa nhiều key:**

```redis
MGET user:100:name user:200:name
```

Redis Cluster thường yêu cầu tất cả key trong **cùng một lệnh nhiều key** phải thuộc **cùng hash slot**. Nếu không, server có thể trả:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

Chia lệnh `MGET` không hợp lệ thành hai lệnh `GET` độc lập có thể tránh ràng buộc nhiều key, **nếu** driver có khả năng định tuyến từng lệnh. Đó là thay đổi semantics và số lần gọi lệnh, không phải pipeline khiến `MGET` cross-slot trở nên hợp lệ.

### 2.2. Hash tag ép các key liên quan về cùng slot

Nếu một phần của key nằm trong cặp ngoặc nhọn hợp lệ `{...}`, Redis tính slot dựa trên phần ở giữa. Ví dụ:

```redis
CLUSTER KEYSLOT order:{913}:state
CLUSTER KEYSLOT order:{913}:audit
CLUSTER KEYSLOT order:{913}:items
```

Cả ba lệnh trả **cùng một số slot**, vì cùng hash tag `{913}`.

Do đó, lệnh nhiều key có thể hợp lệ:

```redis
MGET order:{913}:state order:{913}:audit
```

Nhưng:

```redis
MGET order:{913}:state order:{914}:state
```

thường bị lỗi `CROSSSLOT`, vì hai hash tag khác nhau tạo hai slot (trừ trường hợp va chạm hash hiếm, không nên dựa vào).

Hash tag giúp thiết kế nhóm key cần thao tác cùng slot; **không nên đặt tất cả key của hệ thống vào cùng một hash tag**, vì như vậy có thể dồn tải vào một master, làm mất lợi ích phân mảnh.

## 3. MOVED và ASK ảnh hưởng pipeline ra sao?

Topology của Redis Cluster có thể thay đổi khi:

- Rebalance/resharding làm chuyển slot giữa các master.
- Failover thay master đang sở hữu slot.
- Client mới khởi động, cache topology chưa chính xác.
- Mạng hoặc kết nối tới một node bị gián đoạn.

Nếu client gửi lệnh tới node không còn sở hữu slot, Redis có thể trả:

```text
MOVED 12182 redis-node-b:6379
```

`MOVED` báo rằng slot đã được một node khác phục vụ; client nên cập nhật bản đồ slot và gửi lại lệnh phù hợp.

Trong khi chuyển slot, Redis có thể trả `ASK`. Đây là chuyển hướng tạm thời: client cần gửi `ASKING` tới node đích trước lệnh được chuyển hướng, nhưng chưa nên mặc định chuyển vĩnh viễn ánh xạ slot như với `MOVED`.

Khi không dùng pipeline, driver xử lý chuyển hướng và nhận lỗi riêng từng lệnh tương đối trực tiếp. Khi đã phát nhiều lệnh trước khi chờ kết quả:

```text
Ứng dụng
   |
   +-- GET keyA --> Master A --> OK
   |
   +-- GET keyB --> Master B --> MOVED tới C
   |                             |
   |                             +--> thử lại keyB trên C
   |
   +-- SET keyC --> Master C --> có thể thành công hoặc timeout
```

Những kết quả đến từ nhiều kết nối có thể hoàn tất khác thời điểm. Driver phải xử lý phản hồi, chuyển hướng và futures thích hợp. **Không có thứ tự hoàn tất toàn cục giữa các node** mà bạn có thể sử dụng như đảm bảo nghiệp vụ. Một số driver hỗ trợ redirection khi chạy bình thường nhưng có giới hạn riêng khi pipeline/cross-node.

Nếu một lệnh có hiệu ứng ghi đã được thực thi mà phản hồi mất trong lúc chuyển mạng, retry không kiểm soát có thể tạo hiệu ứng lặp lại. Với `INCR`, `LPUSH` hoặc thao tác trừ tồn kho, phải nghĩ tới **idempotency** và reconciliation, không coi timeout là chắc chắn chưa ghi.

## 4. Ba lớp hỗ trợ: Redis, driver và Spring Data Redis

| Lớp | Khả năng tổng quát | Điều cần kiểm tra |
|---|---|---|
| Redis server Standalone | Hỗ trợ pipeline trên một kết nối | Kích thước batch, thời gian xử lý từng lệnh |
| Redis Cluster | Mỗi node vẫn hỗ trợ pipeline; lệnh nhiều key chịu giới hạn slot | Phân bố slot, MOVED/ASK, cross-slot, failover |
| Lettuce native | Cluster-aware routing; API asynchronous có thể phát nhiều lệnh mà chưa đợi phản hồi | Kết nối/node, tương lai phản hồi, flush policy, timeout, retry |
| Jedis native | Pipeline theo API của phiên bản; một số phiên bản mới có `ClusterPipeline` | Phiên bản Jedis thực tế, nhóm lệnh single-node/cross-node được hỗ trợ |
| Spring Data Redis | `RedisTemplate.executePipelined` dùng `RedisConnection` adapter | **Phạm vi pipeline Cluster do Spring Data Redis và connector hỗ trợ**, không suy từ native API |

Tài liệu chính thức về Pipelining của Spring Data Redis (nhánh 3.5/4.1) ghi rõ một giới hạn **“Pipelining is limited to Redis Standalone”**. Cùng trang cũng mô tả Cluster chủ yếu được hỗ trợ qua Lettuce, kèm các trường hợp lệnh cross-slot không hỗ trợ. Điều này phải được đọc như **cảnh báo về phạm vi tích hợp**, thay vì kết luận rằng mọi lời gọi `executePipelined` trên Cluster hoạt động chỉ vì Lettuce hỗ trợ Cluster.

Một hệ thống có thể ở tình huống:

```text
Lettuce native cluster async:
    hỗ trợ phát nhiều lệnh tới nhiều node
             |
             | KHÔNG suy ra
             v
RedisTemplate.executePipelined trên Cluster:
    chắc chắn chạy được cho mọi lệnh, mọi version
```

Vì khả năng thay đổi theo phiên bản, hãy đối chiếu đúng version Spring Data Redis đang sử dụng (ví dụ theo Spring Boot BOM), **không** chỉ nhìn bảng tính năng của bản tài liệu mới nhất.

## 5. Lettuce: mô hình async, Cluster routing và flush

**Lettuce** dựa trên Netty, có API synchronous, asynchronous và reactive. Ở chế độ cluster, `RedisClusterClient` duy trì bản đồ slot và dùng các kết nối tới node thích hợp. API async cho phép phát nhiều lệnh liên tiếp, mỗi lệnh trả `RedisFuture<T>`; ứng dụng có thể chờ kết quả sau khi tất cả lệnh đã được phát đi.

Lettuce xử lý chuyển hướng `MOVED`/`ASK` và hỗ trợ cập nhật topology định kỳ hoặc theo sự kiện. Khả năng này giúp batch trên các key thuộc slot khác nhau **ở cấp native client**, nhưng không biến cả batch thành transaction xuyên node.

### 5.1. Ví dụ Lettuce native async trên Cluster

Đoạn ví dụ dùng một seed node Cluster có thể truy cập ở `127.0.0.1:7000`. Cần dependency Lettuce tương thích với ứng dụng. Ví dụ dùng API native để làm rõ khả năng của driver, **không phải** code của `RedisTemplate.executePipelined`.

```java
import io.lettuce.core.LettuceFutures;
import io.lettuce.core.RedisFuture;
import io.lettuce.core.RedisURI;
import io.lettuce.core.cluster.RedisClusterClient;
import io.lettuce.core.cluster.api.StatefulRedisClusterConnection;
import io.lettuce.core.cluster.api.async.RedisAdvancedClusterAsyncCommands;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;

public final class LettuceClusterBatchExample {

    public static void main(String[] args) throws Exception {
        RedisClusterClient client = RedisClusterClient.create(
                RedisURI.create("redis://127.0.0.1:7000"));

        try {
            try (StatefulRedisClusterConnection<String, String> connection =
                         client.connect()) {

                RedisAdvancedClusterAsyncCommands<String, String> async =
                        connection.async();

                List<RedisFuture<String>> pending = new ArrayList<>();

                // Mỗi SET chỉ có một key. Các key có thể nằm ở các slot khác nhau.
                for (int i = 0; i < 100; i++) {
                    pending.add(async.set("demo:customer:" + i, "READY"));
                }

                boolean finished = LettuceFutures.awaitAll(
                        Duration.ofSeconds(10),
                        pending.toArray(new RedisFuture[0]));

                if (!finished) {
                    throw new IllegalStateException(
                            "Timeout khi đợi batch Redis Cluster");
                }

                for (RedisFuture<String> result : pending) {
                    // Mỗi future có thể thành công hoặc hoàn tất bằng exception.
                    String status = result.get();
                    if (!"OK".equals(status)) {
                        throw new IllegalStateException(
                                "Unexpected SET reply: " + status);
                    }
                }
            }
        } finally {
            client.shutdown();
        }
    }
}
```

Điều quan trọng trong ví dụ:

1. `RedisClusterClient` có thể tính slot và chọn node thích hợp cho từng `SET`.
2. Vòng lặp **không gọi `get()` sau mỗi `set()`**; vì vậy các lệnh được phát đi trước khi chương trình bắt đầu chờ kết quả.
3. `awaitAll` chỉ đợi các future hoàn tất trong timeout; **hoàn tất** vẫn có thể là hoàn tất thất bại. Vì thế cần kiểm tra từng `result.get()`.
4. Kết quả của các future gắn với từng lệnh, không cần giả định node A luôn hoàn tất trước node B.
5. Đây là các lệnh ghi độc lập; khi một future lỗi, những key khác có thể đã được cập nhật.

Trong ứng dụng Spring Boot, không nên tự tạo vô số `RedisClusterClient` trong từng request. Driver/client nên có vòng đời rõ ràng, tái sử dụng theo cấu hình được quản lý, giới hạn số lượng lệnh đang chờ và đóng tài nguyên khi ứng dụng dừng.

### 5.2. Flush policy của Lettuce

Spring Data Redis có API cấu hình Lettuce pipeline flush ở `LettuceConnectionFactory`:

```java
import org.springframework.data.redis.connection.lettuce.LettuceConnection;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

// Ví dụ ý tưởng cấu hình trên factory do ứng dụng sở hữu.
LettuceConnectionFactory factory = /* bean do ứng dụng cấu hình */;
factory.setPipeliningFlushPolicy(
        LettuceConnection.PipeliningFlushPolicy.buffered(50));
```

`buffered(50)` yêu cầu flush sau mỗi 50 lệnh trên pipeline theo cơ chế hỗ trợ của phiên bản Spring Data Redis/Lettuce. Đây là tùy chọn **điều khiển thời điểm flush**, không mở khóa những lệnh bị Cluster từ chối vì cross-slot hay làm `executePipelined` tự nhiên hỗ trợ một Cluster mà adapter không hỗ trợ.

Ở cấp native Lettuce, có thể dùng `setAutoFlushCommands(false)`, phát nhiều lệnh async, sau đó `flushCommands()` và bật auto flush trở lại. Nhưng auto flush là trạng thái **của kết nối**; nếu cùng native connection đang phục vụ nhiều luồng, thay đổi trạng thái này có thể ảnh hưởng lệnh của luồng khác. Chỉ điều khiển flush theo kiểu đó khi sở hữu kết nối dành riêng và kiểm soát vòng đời của nó.

Trong phần lớn ứng dụng, lợi ích chính của pipeline đến từ việc không chờ từng future; chưa cần tối ưu flush policy khi không có số đo chứng minh lợi ích.

## 6. Jedis: pipeline kiểu đồng bộ và sự khác biệt giữa native với Spring

**Jedis** cung cấp API pipeline cho thao tác Redis. Với Standalone, Jedis thường tạo đối tượng pipeline, xếp các lệnh rồi gọi `sync()` để gửi/nhận kết quả. Mỗi lệnh trả một `Response<T>`, chỉ nên đọc sau khi pipeline đã đồng bộ.

Ví dụ ý tưởng với API Jedis native:

```java
import redis.clients.jedis.Jedis;
import redis.clients.jedis.Pipeline;
import redis.clients.jedis.Response;

try (Jedis jedis = new Jedis("127.0.0.1", 6379)) {
    try (Pipeline pipeline = jedis.pipelined()) {
        Response<String> first = pipeline.set("demo:j:1", "A");
        Response<String> second = pipeline.set("demo:j:2", "B");

        pipeline.sync();

        System.out.println(first.get());
        System.out.println(second.get());
    }
}
```

Mẫu trên dành cho **Standalone**. Không được lấy kết nối tới một node bất kỳ của Redis Cluster rồi dùng pipeline đó cho key thuộc mọi node, vì node không sở hữu slot có thể trả `MOVED` và driver phải định tuyến lại.

### 6.1. Jedis Cluster pipeline không phải một khẳng định cố định theo mọi phiên bản

Các bản Jedis mới có cơ chế `ClusterPipeline` trên client cluster-aware, cho phép chia lệnh đơn theo node. Tuy nhiên, **API `JedisCluster.pipelined()`/`ClusterPipeline` là khả năng phụ thuộc phiên bản Jedis native**, và khả năng đó không bảo đảm adapter `JedisConnection` của Spring Data Redis cung cấp đúng một pipeline tương đương trên Cluster.

Với phiên bản Jedis có API tương ứng, cách sử dụng có dạng:

```java
import redis.clients.jedis.HostAndPort;
import redis.clients.jedis.JedisCluster;
import redis.clients.jedis.ClusterPipeline;
import redis.clients.jedis.Response;

// Chỉ áp dụng cho phiên bản Jedis có JedisCluster.pipelined().
try (JedisCluster cluster = new JedisCluster(
        new HostAndPort("127.0.0.1", 7000))) {

    try (ClusterPipeline pipeline = cluster.pipelined()) {
        Response<String> a = pipeline.set("demo:{42}:a", "A");
        Response<String> b = pipeline.set("demo:{43}:b", "B");

        pipeline.sync();

        System.out.println(a.get());
        System.out.println(b.get());
    }
}
```

`ClusterPipeline` của Jedis hiện đại giới hạn **các lệnh có thể gắn với một node**. Những lệnh cần thực thi trên nhiều shard hoặc tất cả node và các lệnh nhiều key ở nhiều slot có thể bị từ chối trong pipeline, dù những lệnh đơn `SET` ở các slot khác nhau có thể được định tuyến tới các node tương ứng.

Nếu phiên bản Jedis trong dự án không có `ClusterPipeline` hoặc không hỗ trợ thao tác mong muốn, **không gọi tên API này bằng cách suy đoán**. Cần chọn một driver/phiên bản đã xác nhận được hỗ trợ, hoặc dùng lệnh đơn theo slot, hoặc xây batch ở tầng ứng dụng và đo hiệu quả.

### 6.2. Bảng so sánh Lettuce và Jedis

| Tiêu chí | Lettuce | Jedis |
|---|---|---|
| Mô hình cơ bản | Netty, API sync/async/reactive | API sync phổ biến, có đối tượng pipeline |
| Pipeline Standalone | Có | Có |
| API native cluster-aware | `RedisClusterClient`, async futures, slot routing | `JedisCluster`/`ClusterPipeline` ở phiên bản có hỗ trợ |
| Cách nhận kết quả | `RedisFuture<T>`, có thể chờ sau khi phát nhiều lệnh | `Response<T>`, gọi `sync()` trước khi đọc |
| Tối ưu flush | Có điều khiển flush ở Spring/Lettuce theo API phù hợp | Pipeline giữ lệnh và đồng bộ bằng `sync()` |
| Redirect và topology | Lettuce cluster client hỗ trợ `MOVED`/`ASK` và refresh topology | Phụ thuộc cluster client, cấu hình và phiên bản Jedis |
| Spring Data Redis reactive API | Hỗ trợ bằng Lettuce | Không cung cấp reactive connector tương đương |
| Giới hạn Spring adapter | Phải theo trang pipelining của Spring Data Redis và version cụ thể | Tương tự; đặc biệt không suy từ native Jedis pipeline |
| Pipeline và transaction | Là hai cơ chế khác nhau; tránh dùng lẫn thiếu kiểm soát | Tài liệu Spring Data Redis ghi pipeline và transaction loại trừ nhau trong Jedis connector |

Không có kết luận chung “Lettuce luôn nhanh hơn Jedis” hoặc ngược lại. Hiệu năng thực tế phụ thuộc RTT, server load, số node, số lệnh mỗi batch, serializer, topology, connection pool và cách sử dụng API.

## 7. Spring Data Redis executePipelined: cách dùng và giới hạn

Spring Data Redis cung cấp:

- `RedisTemplate.executePipelined(RedisCallback<?>)`: thực thi nhiều lệnh trong pipeline và trả danh sách kết quả.
- `RedisTemplate.executePipelined(SessionCallback<?>)`: nhóm nhiều RedisOperations trên một session callback.
- Các overload cho phép chỉ định serializer để giải mã kết quả.

Ví dụ với `StringRedisTemplate` trên Redis Standalone hoặc môi trường **đã xác nhận** hỗ trợ `executePipelined`:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisBulkWriter {

    private final StringRedisTemplate template;

    public RedisBulkWriter(StringRedisTemplate template) {
        this.template = template;
    }

    public List<Object> writeBatch(String tenantId, int count) {
        if (count < 0 || count > 500) {
            throw new IllegalArgumentException(
                    "count must be between 0 and 500");
        }

        return template.executePipelined(
                (RedisCallback<Object>) connection -> {
                    for (int i = 0; i < count; i++) {
                        String key = "demo:{" + tenantId + "}:item:" + i;
                        String value = "READY";

                        connection.stringCommands().set(
                                key.getBytes(StandardCharsets.UTF_8),
                                value.getBytes(StandardCharsets.UTF_8));
                    }

                    // Bắt buộc return null: kết quả callback bị bỏ,
                    // kết quả của các Redis command đến từ pipeline.
                    return null;
                });
    }
}
```

Một số điểm cần hiểu:

1. Callback được gọi để **xếp các thao tác Redis**, không phải nhận kết quả của mỗi `SET` ngay tại thời điểm gọi.
2. Hàm callback cần **trả `null`**; `executePipelined` trả `List<Object>` là kết quả pipeline.
3. Với thao tác như `GET`, kết quả thường được giải mã bằng các serializer của `RedisTemplate`; có thể truyền serializer riêng khi cần.
4. Không cho một callback chạy vô hạn hoặc phát hàng triệu lệnh mà không giới hạn batch.
5. Nếu cluster adapter của phiên bản hiện tại không hỗ trợ pipeline, ví dụ này không trở nên hợp lệ chỉ vì key được đặt cùng hash tag.

**Lưu ý về kiểu trả về:** trong pipeline, các API như `opsForValue().get(...)` có thể trả `null` ngay trong callback vì kết quả thật chưa tới. Nếu cần đọc rồi dùng kết quả để quyết định lệnh tiếp theo, không thể viết theo kiểu tuần tự phụ thuộc từng kết quả bên trong một pipeline bình thường. Hãy chia thành hai giai đoạn, hoặc chọn atomic command/script/transaction phù hợp.

### 7.1. Cấu hình Redis Cluster trong Spring Boot

Ví dụ cấu hình node seed:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:7000
          - 127.0.0.1:7001
          - 127.0.0.1:7002
      timeout: 5s
```

Spring Boot mặc định thường dùng Lettuce khi starter Redis được cài với cấu hình chuẩn. Tùy phiên bản Spring Boot, có thể thay connector và cấu hình connection factory. Đừng mặc định rằng khai báo `cluster.nodes` tự thay đổi giới hạn `executePipelined` của Spring Data Redis.

Kiểm tra ứng dụng sử dụng `LettuceConnectionFactory` hay `JedisConnectionFactory`, phiên bản Spring Data Redis/Jedis/Lettuce theo dependency graph thực tế, và chủ động xác nhận các thao tác cần dùng trong môi trường Redis Cluster thật.

### 7.2. Trường hợp cluster adapter không hỗ trợ pipeline

Nếu `executePipelined` ném `UnsupportedOperationException` hoặc lỗi tương đương:

- Không thử ép chạy qua một RedisConnection của **một node** rồi gửi key ngẫu nhiên thuộc nhiều slot.
- Với số lệnh nhỏ, có thể dùng `RedisTemplate` gọi từng thao tác bình thường để driver định tuyến từng key.
- Nếu cần nhiều lệnh độc lập trên Cluster và hiệu năng là ưu tiên, xem xét **Lettuce native async cluster-aware** hoặc **Jedis ClusterPipeline** phù hợp với phiên bản.
- Nếu lệnh liên quan tới nhiều key, kiểm tra cùng-slot và lựa chọn hash tag, hoặc phân chia thành các lệnh độc lập có xử lý kết quả từng phần.

Không biến tình huống thiếu hỗ trợ của một API thành giả định “Redis Cluster không có pipelining ở cấp giao thức”. Giới hạn có thể nằm ở tầng abstraction cụ thể.

## 8. Bố trí batch theo slot hoặc node

Đối với dữ liệu nhiều tenant, có thể thiết kế:

```text
user:{tenantA}:1
user:{tenantA}:2
user:{tenantB}:1
user:{tenantB}:2
```

Các key cùng `{tenantA}` nằm chung slot, tương tự `{tenantB}`. Điều này hữu ích nếu nghiệp vụ thường xuyên thao tác nhiều key trong một tenant bằng lệnh nhiều key hoặc script. Song nếu một tenant quá lớn, mọi key của tenant sẽ tập trung vào một slot, dễ trở thành điểm nóng.

Lựa chọn phân nhóm theo batch:

| Cách nhóm | Phù hợp khi | Đánh đổi |
|---|---|---|
| Một batch gồm key bất kỳ | Dùng cluster-aware native API hỗ trợ fan-out | Nhiều kết nối và phản hồi không cùng thời điểm |
| Theo **slot** | Cần lệnh nhiều key cùng slot, hoặc muốn kiểm soát routing | Nhiều batch nhỏ nếu dữ liệu phân tán rộng |
| Theo **node** | Batch nhiều lệnh một key trên cùng Redis master | Slot có thể đổi chủ trong lúc chạy; phải xử lý redirect |
| Theo **tenant hash tag** | Các key trong tenant cần thao tác cùng slot | Nguy cơ hot slot khi tenant có lưu lượng lớn |
| Theo batch cố định, ví dụ 200–500 lệnh | Muốn giới hạn memory/latency và giảm burst load | Phải điều chỉnh theo kết quả đo |

**Theo node không đồng nghĩa theo slot.** Một node thường sở hữu nhiều slot; lệnh như `MGET` vẫn yêu cầu các key trong cùng một lệnh thuộc cùng **slot**, kể cả khi các slot khác nhau đang nằm trên cùng một node.

### 8.1. Đừng dùng hash tag chỉ để “bật pipeline”

Redis Cluster **không yêu cầu** mọi lệnh đơn của một batch cluster-aware cùng slot. Hash tag cần thiết nhất khi các lệnh nhiều key hoặc script phụ thuộc các key ở cùng slot. Thêm `{all}` vào mọi key chỉ để pipeline có thể khiến toàn bộ tải đổ về một shard.

Hãy phân biệt vấn đề:

- `CROSSSLOT`: ràng buộc một lệnh nhiều key hoặc transaction/script.
- Không có `executePipelined` trên Cluster: ràng buộc API Spring Data Redis/driver.
- Latency lớn: vấn đề RTT, số lệnh, serialization, tải node và cấu hình batch.

Ba vấn đề trên có giải pháp khác nhau.

## 9. Thứ tự, phản hồi và tính nhất quán

### 9.1. Không có transaction tự động

Một pipeline:

```redis
SET stock:233 "10"
INCR stock:233
SET order:233 "PAID"
```

có thể gửi ba lệnh rất nhanh, nhưng `SET order:233 PAID` không phải commit marker được Redis bảo đảm nếu lệnh trước lỗi. Redis có thể thực thi các lệnh khác trong batch dù một lệnh báo lỗi. Để bảo vệ invariant, phải thiết kế transaction/script hoặc cơ chế đồng bộ riêng.

### 9.2. Thứ tự theo kết nối và giữa các node

Trong một kết nối Redis tới một node, các lệnh được xử lý theo thứ tự giao thức mà node nhận. Với pipeline cross-node:

```text
SET item:A status1 --> Node A --> OK
SET item:B status2 --> Node B --> OK
```

không có đảm bảo Node A hoàn tất trước Node B dù hai lệnh được phát theo thứ tự trong JVM. Nếu thao tác thứ hai phụ thuộc thao tác thứ nhất **đã hoàn tất**, cần chờ kết quả hoặc thiết kế xử lý nghiệp vụ theo luồng rõ ràng; không thể dùng một pipeline đa node như một chuỗi giao dịch toàn cục.

### 9.3. Lỗi từng phần

Một batch gồm 500 lệnh có thể nhận:

- 480 phản hồi thành công;
- 10 phản hồi lỗi do loại dữ liệu hoặc cross-slot;
- 10 lệnh không rõ đã thực thi chưa sau timeout/mất kết nối.

Con số ví dụ minh họa cấu trúc lỗi. Hệ thống cần phân biệt **lệnh thành công**, **lệnh lỗi chắc chắn**, và **kết quả chưa rõ**. Không retry cả batch ghi cộng dồn mà không có idempotency.

Nếu tất cả thao tác là `SET key fixedValue` với cùng nội dung cố định, retry thường ít rủi ro hơn `INCR` hoặc `LPUSH`; tuy nhiên vẫn cần chú ý cập nhật đồng thời và thứ tự sự kiện nghiệp vụ.

### 9.4. Kết quả pipeline và serializer

`executePipelined` trả danh sách kết quả thay vì kết quả tức thời từ từng API trong callback. Spring Data Redis dùng serializer của template để giải mã những response phù hợp. Nếu data được lưu dạng nhị phân hoặc dùng serializer không tương thích, dữ liệu trả về có thể bị giải mã sai hoặc phát sinh exception.

Với driver native, kết quả có kiểu `RedisFuture<T>` (Lettuce) hoặc `Response<T>` (Jedis); trình tự hoàn tất và cách đọc kết quả khác với `List<Object>` của Spring. Không nên viết một lớp trừu tượng tùy tiện giả định ba API trả kết quả giống nhau.

## 10. Hiệu năng: khi nào pipeline giúp và khi nào gây hại?

Pipeline hữu ích khi:

- Có nhiều thao tác độc lập, ít phụ thuộc kết quả lệnh trước.
- RTT mạng đáng kể so với thời gian thực thi từng lệnh.
- Có thể giới hạn số lệnh đang chờ và xử lý response theo batch.
- Driver/server đủ năng lực xử lý lưu lượng phát ra theo lô.

Pipeline ít hữu ích hoặc rủi ro khi:

- Mỗi lệnh có CPU cost lớn: pipeline không làm lệnh Redis thực thi nhanh hơn.
- Mỗi lệnh phụ thuộc kết quả trước đó: phải chờ và quyết định tuần tự.
- Thao tác là blocking command (`BLPOP`, `XREAD BLOCK`...) trên kết nối không phù hợp.
- Batch quá lớn làm tăng hàng đợi, memory giữ response, timeout và tail latency.
- Cluster liên tục reshard/failover, làm tăng số redirect và kết quả chưa rõ.

### 10.1. Không chọn batch size theo một con số “chuẩn” tuyệt đối

Một batch 100 lệnh `SET` với giá trị vài byte rất khác 100 lệnh `HGETALL` trả về các Hash lớn. Chọn batch size dựa trên **tổng dữ liệu yêu cầu và phản hồi**, không chỉ số command.

Ví dụ quy tắc khởi đầu có thể là 100–500 lệnh nhỏ một batch, sau đó đo để điều chỉnh. Con số này chỉ là gợi ý thực nghiệm, không có đảm bảo hiệu quả cho mọi cluster.

Theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Latency p50/p95/p99 của batch | Batch lớn có thể tăng tail latency |
| Throughput (commands/s) | Đánh giá lợi ích sau giảm RTT |
| Số lệnh timeout và redirect | Phát hiện topology bất ổn hoặc quá tải |
| Memory và output buffer trên node | Pipeline nhiều response có thể tạo áp lực bộ nhớ |
| Pool connection, số lệnh in-flight | Phát hiện queue tồn đọng ở client |
| CPU/network từng Redis master | Nhìn thấy shard bị nóng khi hash tag phân bố lệch |

So sánh **cùng workload** giữa gửi tuần tự, Spring pipeline Standalone, Lettuce/Jedis cluster-native batch (nếu hỗ trợ). Không dựa vào kết quả benchmark Standalone để kết luận tốc độ pipeline trên Cluster.

## 11. Các vấn đề thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `executePipelined` lỗi trên Cluster | Adapter Spring Data Redis/driver không hỗ trợ kịch bản | Kiểm tra đúng version và tài liệu; dùng cluster-native API hoặc lệnh đơn |
| `CROSSSLOT` khi `MGET`/`MSET` | Key trong **một lệnh nhiều key** thuộc slot khác nhau | Dùng hash tag cho nhóm liên quan hoặc tách thành lệnh đơn |
| `MOVED`/`ASK` tăng đột biến | Topology thay đổi, client cache slot cũ | Kiểm tra topology refresh, endpoint, driver redirect config |
| Một số key ghi được, một số key không | Pipeline không phải transaction; partial failure | Ghi nhận kết quả từng lệnh, retry idempotent, reconcile |
| `GET` trong callback Spring trả `null` | Lệnh vẫn nằm trong pipeline, chưa có response | Đọc `executePipelined` result thay vì đọc tức thời |
| Kết quả không đúng kiểu | Serializer template khác định dạng dữ liệu | Kiểm tra serializer và overload result serializer |
| Jedis không có `JedisCluster.pipelined()` | Phiên bản Jedis cũ hoặc API khác | Kiểm tra dependency thực tế, chọn API phù hợp phiên bản |
| Jedis pipeline từ một node liên tục `MOVED` | Dùng connection tới một node thay cho cluster-aware pipeline | Dùng client Cluster-aware hoặc nhóm key đúng slot/node |
| Batch chậm hơn gọi lệnh thường | Batch nhỏ quá, nhiều dữ liệu phản hồi, timeout, serialize | Đo RTT, payload, network, chọn kích thước phù hợp |
| Memory Redis tăng khi pipeline lớn | Server giữ nhiều response chưa được đọc | Chia batch, tiêu thụ response đều đặn |
| Thêm một hash tag làm node quá tải | Toàn bộ key cùng slot | Thiết kế tag theo nhóm vừa đủ, phân phối hot tenant |
| Retry `INCR` làm tăng hai lần | Phản hồi bị mất nhưng lệnh đã chạy | Dùng request ID/idempotency và cơ chế xác nhận |

## 12. Thực hành: kiểm tra giới hạn thay vì đoán

### Bài 1 — Phân biệt cùng slot và khác slot

Trên Redis Cluster test, chạy:

```redis
CLUSTER KEYSLOT profile:{acct-7}:name
CLUSTER KEYSLOT profile:{acct-7}:status
CLUSTER KEYSLOT profile:{acct-8}:name
```

Hai key mang `{acct-7}` có cùng slot; key còn lại thường khác slot. Sau đó so sánh:

```redis
MSET profile:{acct-7}:name An profile:{acct-7}:status ACTIVE
MGET profile:{acct-7}:name profile:{acct-7}:status

# Dùng Redis CLI cluster-aware, ví dụ redis-cli -c:
MGET profile:{acct-7}:name profile:{acct-8}:name
```

Lệnh `MGET` thứ hai thông thường nhận `CROSSSLOT`. Dù cùng một chương trình Java phát nó trong pipeline, quy tắc slot cho lệnh nhiều key vẫn giữ nguyên.

### Bài 2 — Pipeline Standalone với Spring Data Redis

Tạo một service `StringRedisTemplate.executePipelined` như mục 7, phát 100 lệnh `SET` và lấy `List<Object>`. Kiểm tra:

1. Callback trả `null`.
2. Kết quả có số phần tử tương ứng các lệnh được xếp, theo cách API phản hồi của phiên bản đang dùng.
3. Dữ liệu thực sự có trong Redis sau khi pipeline kết thúc.

Đối chiếu thời gian gửi tuần tự và pipeline trong môi trường thử nghiệm, không dùng dữ liệu production.

### Bài 3 — Cùng workload trên Cluster

Chạy lại workload nhiều lệnh `SET` một key bằng:

1. `StringRedisTemplate` gửi tuần tự thông qua cluster-aware connection factory.
2. `executePipelined` trên đúng phiên bản Spring Data Redis/driver (ghi nhận có hỗ trợ hay không).
3. Lettuce native async cluster-aware; hoặc Jedis `ClusterPipeline` nếu dependency có hỗ trợ.

Ghi lại thành công/thất bại, latency, throughput, số redirect và trạng thái key cuối. Nếu `executePipelined` không hỗ trợ, ghi rõ **lớp API báo lỗi** thay vì kết luận Redis server không có pipeline.

### Bài 4 — Quan sát chuyển hướng

Trong môi trường Cluster test có thể kiểm soát, chuyển slot hoặc thực hiện failover rồi quan sát phản hồi qua Lettuce/Jedis. Đánh giá:

- Driver tự refresh topology hay cần cấu hình?
- Những lệnh đã nhận response có được đối chiếu theo đúng request không?
- Khi mất kết nối, client có biết chắc lệnh ghi nào đã chạy chưa?
- Cơ chế retry có gây thao tác lặp lại không?

Thao tác thay đổi topology chỉ nên thực hiện trong môi trường kiểm thử có chủ đích. Bài học quan trọng là xử lý lỗi và idempotency, không phải cố tạo redirect trên Redis đang phục vụ nghiệp vụ.

## 13. Nguyên tắc triển khai

1. **Xác định lớp hỗ trợ.** Redis Cluster hỗ trợ các lệnh đơn và mỗi node hiểu pipeline, nhưng `RedisTemplate.executePipelined` phải được xác nhận theo version adapter.
2. **Phân biệt nhiều lệnh một key với một lệnh nhiều key.** Một batch gồm nhiều `SET` độc lập khác slot không giống một `MSET` chứa nhiều key khác slot.
3. **Chọn driver theo nhu cầu thực.** Lettuce mạnh ở async/reactive và cluster-aware futures; Jedis có pipeline sync và những phiên bản mới hỗ trợ ClusterPipeline native. Tính năng native không tự chuyển thành tính năng Spring adapter.
4. **Không giả định batch là transaction.** Các node có thể hoàn tất ở thời điểm khác nhau và lệnh có thể thành công một phần.
5. **Giới hạn batch và in-flight commands.** Đo lượng request/response, timeout, p99 và memory trên từng node.
6. **Thiết kế keyspace có chủ đích.** Dùng hash tag khi cần multi-key cùng slot, tránh dồn toàn hệ thống vào một slot.
7. **Xử lý topology thay đổi.** Cấu hình refresh, timeout, retry và reconciliation theo đặc tính lệnh; không retry mù quáng lệnh có hiệu ứng cộng dồn.

## Tài liệu tham khảo

- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html): `executePipelined`, serializer, Lettuce flush policy và các ghi chú về giới hạn pipeline/Cluster.
- [Spring Data Redis — Drivers](https://docs.spring.io/spring-data/redis/reference/redis/drivers.html): bảng khả năng Lettuce/Jedis, cluster connections, pipeline, transaction và reactive API.
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/): cơ chế giảm round trip và lý do chia batch.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slot, hash tag, `MOVED` và `ASK`.
- [Redis — CROSSSLOT error](https://redis.io/docs/latest/develop/reference/errors/common/crossslot/): quy tắc lệnh nhiều key trên Cluster.
- [Lettuce — High Availability and Sharding](https://redis.github.io/lettuce/ha-sharding/): định tuyến cluster và cập nhật topology.
- [Lettuce — Asynchronous API](https://redis.github.io/lettuce/user-guide/async-api/): `RedisFuture` và cơ chế gửi nhiều lệnh trước khi chờ.
- [Redis — Jedis Pipelines and Transactions](https://redis.io/docs/latest/develop/clients/jedis/transpipe/): pipeline và kiểu `Response<T>` của Jedis.
- [Jedis — ClusterPipeline source](https://github.com/redis/jedis/blob/master/src/main/java/redis/clients/jedis/ClusterPipeline.java): ví dụ về native ClusterPipeline và giới hạn các command nhiều node ở phiên bản Jedis có tính năng này.
