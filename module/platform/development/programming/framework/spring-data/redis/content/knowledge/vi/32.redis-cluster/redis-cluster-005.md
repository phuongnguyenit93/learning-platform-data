# Giới hạn lệnh nhiều khóa và lỗi CROSSSLOT trong Redis Cluster

> **Module:** Spring Data Redis  
> **Chương:** Redis Cluster  
> **Chủ đề:** Hiểu vì sao nhiều lệnh Redis chỉ chấp nhận các key cùng hash slot, cách chẩn đoán lỗi `CROSSSLOT`, sử dụng hash tag và thiết kế lại thao tác trong Spring Data Redis khi cần truy cập nhiều key.

## 1. Bối cảnh: tại sao một lệnh chạy trên Redis standalone nhưng lỗi trên Redis Cluster?

Một ứng dụng Spring Boot có thể đang dùng Redis standalone:

~~~redis
SET user:101:name "An"
SET user:102:name "Binh"
MGET user:101:name user:102:name
~~~

Ở Redis standalone, tất cả key thuộc cùng một Redis instance. Lệnh `MGET` đọc hai key trong một command nên hoạt động bình thường.

Khi chuyển sang Redis Cluster, các key được phân bố lên những **hash slot** và những node khác nhau. Nếu `user:101:name` và `user:102:name` thuộc hai slot khác nhau, một command `MGET` yêu cầu đọc chúng cùng lúc sẽ bị từ chối:

~~~text
(error) CROSSSLOT Keys in request don't hash to the same slot
~~~

Không phải do key không tồn tại. Cũng không phải vì Redis Cluster không hỗ trợ `MGET`. Vấn đề là **hai key không thuộc cùng hash slot**, trong khi command đang yêu cầu thao tác trên nhiều key như một đơn vị.

Điểm quan trọng nhất của bài:

> **Một Redis Cluster command thực sự thao tác trên nhiều key thường yêu cầu tất cả key của command thuộc cùng hash slot. Một ứng dụng có thể truy cập nhiều key ở nhiều slot bằng các command độc lập, nhưng không vì thế mà có một lệnh nguyên tử xuyên các slot.**

Đây là giới hạn của mô hình phân vùng Redis Cluster, không phải lỗi đặc biệt của Spring Boot.

### 1.1. Ba mục tiêu cần phân biệt

Khi code cần nhiều key, hãy tự hỏi:

1. **Chỉ cần lấy nhiều dữ liệu để tổng hợp?** Có thể dùng nhiều request đơn lẻ theo từng key và tổng hợp kết quả ở client.
2. **Cần một Redis command nhiều key?** Các key liên quan phải cùng slot.
3. **Cần tính nguyên tử cho nhiều key?** Cần đưa chúng vào cùng slot và dùng đúng Redis command, transaction hoặc Lua/Redis Function phù hợp; nếu ở nhiều slot thì phải thay đổi mô hình nhất quán.

Việc chọn sai giữa ba mục tiêu dễ dẫn tới sửa lỗi `CROSSSLOT` bằng cách chia command nhưng vô tình làm mất atomicity mà nghiệp vụ cần.

## 2. Redis Cluster phân vùng dữ liệu bằng 16.384 hash slots

Redis Cluster sử dụng **16.384 hash slots**, đánh số từ 0 đến 16383. Mỗi key được ánh xạ tới một slot. Cluster phân bổ quyền sở hữu các slot giữa các primary node; replica phục vụ các vai trò liên quan tới sao chép và failover.

### 2.1. Công thức ánh xạ slot

Với key không chứa **hash tag** hợp lệ, slot được tính theo:

\[
\operatorname{slot}(key)=\operatorname{CRC16}(key)\bmod 16384
\]

Hàm băm xử lý các bytes của key Redis, không dựa vào Java `String.hashCode()`. Vì vậy không thể dùng `String.hashCode() % 16384` để thay thế hash slot calculation của Redis Cluster.

Ví dụ ý tưởng:

~~~text
user:101:name ──CRC16 / 16384──> slot A
user:102:name ──CRC16 / 16384──> slot B
user:103:name ──CRC16 / 16384──> slot C
~~~

Các ký hiệu A/B/C chỉ minh họa; slot cụ thể phải được tính từ key bytes thực tế. Các key nhìn giống nhau về prefix **không tự động** cùng slot.

### 2.2. Hash slot và cluster node là hai tầng khác nhau

Một node Redis Cluster có thể sở hữu hàng nghìn slot:

~~~text
Redis Cluster
├── Primary node A: nhóm slot 1
├── Primary node B: nhóm slot 2
└── Primary node C: nhóm slot 3
~~~

Hai key khác slot **có thể tình cờ** cùng được đặt trên một node tại một thời điểm. Tuy nhiên một Redis command nhiều key vẫn có thể trả `CROSSSLOT` vì quy tắc dựa vào **slot**, không chỉ vào việc hai key có cùng địa chỉ server hiện tại hay không.

Khi resharding, một slot có thể chuyển sang node khác. Vì thế data model phải dựa trên slot, không dựa vào giả định một node luôn giữ một nhóm key cố định.

### 2.3. Redis CLI kiểm tra slot

Trên một node thuộc Redis Cluster:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT user:101:name
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT user:102:name
~~~

Lệnh `CLUSTER KEYSLOT key` trả về slot của key đã cho. Khi hai kết quả khác nhau, chúng **không thể** được gửi cùng nhau trong một command multi-key yêu cầu đồng slot.

Nếu môi trường Redis managed hạn chế quyền thực thi một số command, dùng client tooling hoặc khả năng quan sát được nhà cung cấp hỗ trợ. Đừng suy ra hai key cùng slot chỉ từ tên key hoặc từ việc chúng đang ở cùng Redis node.

## 3. Hash tag: cách kiểm soát những key cùng slot

Redis Cluster hỗ trợ **hash tag**: một chuỗi không rỗng nằm trong cặp ngoặc nhọn `{...}` đầu tiên được nhận diện hợp lệ trong tên key. Redis băm phần **bên trong cặp ngoặc**, thay vì băm toàn bộ key.

Ví dụ:

~~~text
order:{o-101}:status
order:{o-101}:items
order:{o-101}:payment
~~~

Cả ba key được hash dựa trên tag `o-101`, do đó thuộc **cùng slot**.

~~~text
order:{o-101}:status   ───┐
order:{o-101}:items    ───┼── hash("o-101") ──> Cùng slot
order:{o-101}:payment  ───┘
~~~

Đây là giải pháp cơ bản khi một nhóm key liên quan phải tham gia cùng một Redis command.

### 3.1. Hash tag áp dụng như thế nào?

| Key | Phần được băm | Hệ quả |
|---|---|---|
| `user:101:profile` | Toàn bộ key | Không có slot grouping chủ động |
| `user:{101}:profile` | `101` | Cùng slot với các key có tag `{101}` |
| `user:{101}:settings` | `101` | Cùng slot với `user:{101}:profile` |
| `user:{102}:profile` | `102` | Có thể thuộc slot khác |
| `order:{o-101}:status` | `o-101` | Cùng slot với các key chứa `{o-101}` |
| `{tenant-7}:user:101` | `tenant-7` | Mọi key cùng tag tenant-7 sẽ chung slot |

**Lưu ý:** Hai tag khác nhau vẫn **có thể tình cờ** rơi vào cùng slot do chỉ có 16.384 slot. Nhưng chỉ nên dùng cùng một tag có chủ đích để bảo đảm co-location cho những key phải thao tác cùng nhau.

### 3.2. Thử thực tế

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'order:{o-101}:status'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'order:{o-101}:items'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'order:{o-101}:payment'
~~~

Ba kết quả phải giống nhau với cách encode key đồng nhất.

Thử tiếp:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 MGET 'order:{o-101}:status' 'order:{o-101}:payment'
~~~

Nếu keys chứa Redis String và có cùng slot, `MGET` có thể chạy bình thường. Nếu một key không tồn tại, vị trí tương ứng được trả nil; **key không tồn tại không phải nguyên nhân `CROSSSLOT`**.

### 3.3. Cẩn thận với tag rỗng hoặc không nhất quán

Ví dụ các key:

~~~text
user:{}:profile
user:{101}:profile
user:{101}:settings
user:{101:profile
~~~

Không nên xem `{}` rỗng hoặc dấu ngoặc thiếu là một hash tag dùng để grouping. Quy tắc parsing hash tag có các trường hợp biên; đơn giản nhất là đặt **một cặp `{...}` không rỗng, rõ ràng và ổn định**, tránh cặp ngoặc không liên quan ở phía trước.

Không dùng cùng một logical ID nhưng encode khác nhau:

~~~text
order:{101}:status
order:{order-101}:payment
~~~

Hai tag khác nhau nên không bảo đảm cùng slot. Cần thống nhất hàm dựng key ở mọi publisher/consumer và mọi service.

### 3.4. Hash tag không làm Redis tự tạo quan hệ dữ liệu

Hash tag chỉ điều khiển việc chọn hash slot. Nó không:

- Tạo foreign key.
- Đảm bảo key tồn tại.
- Bảo đảm toàn bộ thao tác nhiều command là atomic.
- Tự duy trì index.
- Đặt TTL giống nhau cho các key.
- Đảm bảo business transaction với database.

Nó chỉ làm cho **các command có yêu cầu cùng slot** có cơ hội thực thi hợp lệ; atomicity còn phụ thuộc lệnh hoặc transaction được sử dụng.

## 4. Những lệnh nhiều key thường bị ràng buộc cùng slot

Để hiểu lỗi `CROSSSLOT`, trước hết phải xác định command nào mang nhiều **key arguments**. Nhiều value arguments trong một command không đồng nghĩa nhiều Redis keys.

### 4.1. Các nhóm command thường gặp

| Nhóm | Command | Ví dụ yêu cầu nhiều key |
|---|---|---|
| Redis String | `MGET`, `MSET`, `MSETNX` | Đọc/ghi nhiều String keys |
| Xóa nhiều key | `DEL`, `UNLINK` | Xóa nhiều key trong một command |
| Set operations | `SUNION`, `SINTER`, `SDIFF` | Tính kết quả từ nhiều Sets |
| Store Set result | `SUNIONSTORE`, `SINTERSTORE`, `SDIFFSTORE` | Nhiều nguồn và key đích |
| Sorted Set operations | `ZUNION`, `ZINTER`, `ZDIFF` và các biến thể STORE | Nhiều sorted set keys |
| Di chuyển/đổi key | `RENAME`, `RENAMENX`, `COPY` | Source và destination keys |
| List operations | `LMOVE`, `BLMOVE`, `RPOPLPUSH` | Source và destination |
| Blocking operations | `BLPOP`, `BRPOP` | Một danh sách key ứng viên |
| Stream multi-read | `XREAD`/`XREADGROUP` với nhiều stream keys | Một lệnh đọc từ nhiều streams |
| Bitmap operations | `BITOP` | Key đích và nhiều key nguồn |
| Scripting | `EVAL`, `EVALSHA`, `FCALL` | Danh sách `KEYS` có thể phải cùng slot |
| Transactions | `WATCH`, `MULTI`/`EXEC` khi chứa thao tác đa key | Toàn bộ keys liên quan cần cùng slot |

Danh sách mang tính minh họa; Redis bổ sung command qua các phiên bản. Với bất cứ command nào, cần xem **keyspec** và Redis Cluster support của phiên bản Redis/client đang sử dụng.

### 4.2. Không phải mọi command có nhiều arguments đều là multi-key

Ví dụ:

~~~redis
HSET user:{101}:profile name An city Hanoi level 4
~~~

Lệnh này có **một Redis key** là `user:{101}:profile`, còn `name`, `city` và `level` là field của cùng một Redis Hash.

Do vậy, `HSET` với nhiều field/value vẫn chỉ thao tác trên một key và không bị lỗi `CROSSSLOT` do những field ấy.

Tương tự:

~~~redis
LPUSH queue:tasks task1 task2 task3
SADD tags:product:101 red premium seasonal
ZADD ranking:daily 100 user101 90 user102
~~~

Các value/member trong một Redis List/Set/Sorted Set không phải các Redis keys riêng. Khi nghi ngờ một lệnh “có nhiều thứ”, hãy xác định chính xác **vị trí nào là key arguments**.

### 4.3. Một vài lệnh multi-key nhưng vẫn hoạt động

Câu nói “Redis Cluster cấm mọi lệnh nhiều key” là **không đúng**. Ví dụ:

~~~redis
MSET 'cart:{c-101}:count' 3 'cart:{c-101}:status' open
MGET 'cart:{c-101}:count' 'cart:{c-101}:status'
DEL 'cart:{c-101}:count' 'cart:{c-101}:status'
~~~

Tất cả keys cùng tag `c-101`, nên trên cluster bình thường chúng thuộc một slot. Mỗi lệnh native có semantics riêng trên node sở hữu slot đó.

**Không được suy luận** rằng do ba command trên đều chạy được nên chuỗi `MSET → MGET → DEL` trở thành một transaction. Mỗi command vẫn là một thao tác riêng nếu không dùng transaction/script.

## 5. Tái hiện lỗi CROSSSLOT bằng Redis CLI

Giả sử Redis Cluster đang chạy và một node có endpoint `127.0.0.1:7000` trong môi trường demo.

### 5.1. Một ví dụ lỗi

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 SET 'cart:{c-101}:count' 3
redis-cli -c -h 127.0.0.1 -p 7000 SET 'cart:{c-202}:count' 5

redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'cart:{c-101}:count'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'cart:{c-202}:count'
~~~

Nếu hai slot thực tế khác nhau, chạy:

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 MGET 'cart:{c-101}:count' 'cart:{c-202}:count'
~~~

Redis trả lỗi thường thấy:

~~~text
CROSSSLOT Keys in request don't hash to the same slot
~~~

Ví dụ dùng hai tag khác nhau để minh họa; **kiểm tra `CLUSTER KEYSLOT` trước** vì có khả năng hai tag khác nhau tình cờ trùng slot.

### 5.2. Đổi key schema để cùng slot

~~~bash
redis-cli -c -h 127.0.0.1 -p 7000 SET 'cart:{c-101}:count' 3
redis-cli -c -h 127.0.0.1 -p 7000 SET 'cart:{c-101}:status' open

redis-cli -c -h 127.0.0.1 -p 7000 MGET 'cart:{c-101}:count' 'cart:{c-101}:status'
~~~

Hai key có cùng tag nên `MGET` thành công nếu chúng thuộc đúng Redis String type. Đổi tên key **không phải** sửa dữ liệu tự động: nếu key cũ đã tồn tại và cần giữ, ứng dụng phải có quy trình migration/copy theo semantics Redis Cluster.

### 5.3. Lưu ý khi dùng redis-cli -c

Tùy chọn `-c` khiến redis-cli biết xử lý cluster redirection như `MOVED` hoặc `ASK`. Nó **không** thay đổi hash slot của key và **không** biến `MGET` xuyên slot thành một command hợp lệ.

Vì thế:

~~~text
redis-cli -c ... MGET key-slot-A key-slot-B
~~~

vẫn có thể `CROSSSLOT`. Đổi endpoint Redis node hoặc thêm `-c` không phải giải pháp cho yêu cầu multi-key xuyên slot.

## 6. CROSSSLOT khác MOVED, ASK và TRYAGAIN

Bốn thông điệp này xuất hiện ở môi trường cluster nhưng có nguyên nhân khác nhau.

| Thông điệp | Ý nghĩa chính | Hướng xử lý |
|---|---|---|
| `CROSSSLOT` | Các Redis key của **một command** không cùng slot | Thiết kế key dùng cùng tag, hoặc chia thành command độc lập nếu nghiệp vụ cho phép |
| `MOVED slot host:port` | Client đang gửi command tới node không sở hữu slot | Client cluster-aware cập nhật topology và gửi lại đúng node |
| `ASK slot host:port` | Slot/key đang di chuyển và cần chuyển hướng tạm thời | Cluster client xử lý ASKING/temporary redirect theo protocol |
| `TRYAGAIN` | Một thao tác tạm thời chưa thể hoàn tất, có thể trong quá trình resharding | Retry có giới hạn và backoff khi thích hợp; kiểm tra trạng thái cluster |

Không nên bắt tất cả các lỗi này rồi retry vô hạn:

- `MOVED`/`ASK` là cơ chế routing, bình thường client tương thích xử lý được.
- `TRYAGAIN` có thể là trạng thái tạm thời; retry có thể hữu ích.
- `CROSSSLOT` do key schema không tương thích thường **không hết** dù retry cùng command hàng nghìn lần.

### 6.1. Tại sao cùng slot vẫn có thể lỗi trong lúc migration?

Khi Redis Cluster đang resharding, một số multi-key command có thể gặp trạng thái tạm thời nếu các key cùng slot đang nằm ở tình trạng di chuyển đặc biệt giữa source/target. Điều này khác với lỗi `CROSSSLOT` do hai key cố định thuộc hai slot khác nhau.

Nếu gặp gián đoạn lúc resharding, kiểm tra:

- Slot ownership và cluster topology.
- Driver có xử lý MOVED/ASK đúng không.
- Lỗi có tạm thời hay lặp lại với mọi lần chạy.
- Key đang trong trạng thái migrated/importing hay không.

Không dùng việc cùng slot làm cam kết “không bao giờ có transient cluster errors”.

## 7. Spring Boot kết nối tới Redis Cluster

Một ứng dụng Spring Boot thường dùng `spring-boot-starter-data-redis` với Lettuce cluster-aware driver.

### 7.1. Dependencies

Ví dụ Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
~~~

Lettuce thường là client mặc định của Spring Boot Redis starter, nếu dự án không thay thế bằng Jedis hoặc cấu hình riêng.

### 7.2. application.yml cho Redis Cluster

~~~yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-node-1.internal:6379
          - redis-node-2.internal:6379
          - redis-node-3.internal:6379
        max-redirects: 5
      timeout: 2s
~~~

Hostnames chỉ là ví dụ. Trong môi trường thực tế cần dùng node addresses/endpoints của cluster và cấu hình ACL, password, TLS, topology refresh, read preference hoặc Sentinel/Cluster theo nhà cung cấp.

Với phiên bản Spring Boot khác, prefix cấu hình Redis có thể thay đổi. Các ví dụ ở đây theo cấu trúc `spring.data.redis` được sử dụng trong Spring Boot hiện đại.

### 7.3. RedisClusterConfiguration và connection factory

Có thể tự cấu hình:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class RedisClusterClientConfiguration {

    @Bean
    LettuceConnectionFactory redisConnectionFactory() {
        RedisClusterConfiguration cluster =
                new RedisClusterConfiguration(List.of(
                        "redis-node-1.internal:6379",
                        "redis-node-2.internal:6379",
                        "redis-node-3.internal:6379"));

        return new LettuceConnectionFactory(cluster);
    }
}
~~~

Đây là cách cấu hình **thay thế** cho auto-configuration mặc định, không cần đồng thời khai báo bean factory thủ công và cấu hình properties tương tự nếu không có lý do rõ ràng.

Kết nối đúng cluster chỉ giải quyết routing và xác thực. Nó **không nới lỏng** giới hạn của `MGET`, `MSET`, `EVAL`, `MULTI` hoặc các command native nhiều key.

## 8. Spring Data Redis: lỗi thường xuất hiện ở đâu?

Trong Spring Data Redis, các phương thức cấp cao có thể dẫn tới command Redis cần nhiều key. Ví dụ:

~~~java
List<String> keys = List.of(
        "cart:{c-101}:count",
        "cart:{c-202}:count");

List<String> values =
        stringRedisTemplate.opsForValue().multiGet(keys);
~~~

Nếu các key khác slot, khả năng xử lý phụ thuộc **API và implementation client cụ thể**:

- Nếu cuối cùng client gửi **một MGET native** với tất cả keys, Redis Cluster trả `CROSSSLOT`.
- Một số client/high-level APIs có thể thực hiện **scatter/gather**: chia key theo slot và gửi nhiều command, sau đó ghép kết quả. Khi đó lệnh gọi Java có thể thành công nhưng **không phải một native MGET nguyên tử xuyên slots**.
- Một số template/driver phiên bản có giới hạn pipelining hoặc cách dùng connection khác nhau khi phân phối nhiều slot.

Vì thế không thể kết luận “mọi `multiGet` với key khác slot đều chắc chắn throw” nếu chưa biết phương thức Spring Data Redis và Redis driver phiên bản thực tế. Nhưng cũng **không được** thấy code trả kết quả rồi suy ra Redis đã hỗ trợ atomic multi-key xuyên slot.

### 8.1. Phân biệt Java API và Redis command

| API ở ứng dụng | Có thể tương ứng | Hệ quả |
|---|---|---|
| `opsForValue().get(k)` | Một `GET` | Chỉ một key; cluster client route theo slot |
| `opsForValue().multiGet(keys)` | `MGET` hoặc xử lý theo nhiều slot tùy implementation | Kiểm tra native command/scatter semantics |
| `opsForValue().multiSet(map)` | `MSET` hoặc client decomposition | Nếu decomposed thì mất atomicity toàn nhóm |
| `delete(Collection<K>)` | `DEL` nhiều key hoặc phân nhóm tùy implementation | Không suy ra xóa toàn bộ atomic |
| `executePipelined(...)` | Nhiều command được gửi mà không chờ từng reply | Không bỏ qua CROSSSLOT cho một multi-key command |
| `multi()`/`exec()` | Redis transaction | Không thể đảm bảo atomic multi-slot |
| `execute(script, keys, ...)` | `EVAL`/`EVALSHA` | Cần kiểm tra keys/slot và luật Redis scripting |

Bảng thể hiện **phân tích về semantics**, không phải lời hứa mọi API luôn được triển khai bằng đúng một command ở mọi Spring Data Redis version.

### 8.2. Dấu hiệu trong exception

Một ứng dụng có thể thấy thông báo ở dạng:

~~~text
CROSSSLOT Keys in request don't hash to the same slot
~~~

được bọc trong exception của Spring Data Redis, Lettuce hoặc Redis client. Loại exception cụ thể phụ thuộc driver, version và call site; có thể bắt gặp `DataAccessException` hoặc một client exception ở cause.

Khi xử lý:

1. Ghi log tên operation, số lượng key và một tập key đã redaction nếu phù hợp.
2. Tìm câu `CROSSSLOT` trong exception chain.
3. Kiểm tra slots các key thật đã được serializer tạo ra.
4. Xác nhận call site gửi **một command nhiều key** hay high-level API khác.
5. Quyết định đổi schema key hoặc tách command tùy yêu cầu atomicity.

Không nuốt mọi `DataAccessException` và lặng lẽ trả cache miss, vì như vậy có thể che đi lỗi thiết kế key dẫn tới dữ liệu trả không đầy đủ.

## 9. Giải pháp A: dùng hash tag cho những key phải thao tác cùng nhau

Giả sử một đơn hàng có trạng thái, tổng tiền và thông tin thanh toán:

~~~text
order:{o-101}:status
order:{o-101}:total
order:{o-101}:payment
~~~

Một nhóm key cùng tag có thể được đọc:

~~~java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;

public class OrderReadService {

    private final StringRedisTemplate redis;

    public OrderReadService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> readOrderFields(String orderId) {
        String tag = "{" + orderId + "}";

        return redis.opsForValue().multiGet(List.of(
                "order:" + tag + ":status",
                "order:" + tag + ":total",
                "order:" + tag + ":payment"));
    }
}
~~~

Ở đây, cả ba Redis keys có cùng hash tag `{orderId}`. `multiGet` có điều kiện slot phù hợp để gửi native MGET.

### 9.1. Cẩn thận với orderId

Không nên đưa trực tiếp một ID từ input không tin cậy vào key rồi cho phép chèn `{` hoặc `}` có thể thay đổi cấu trúc tag. Nên:

- Validate ID theo định dạng giới hạn.
- Escape/encode những ký tự đặc biệt nếu ID cho phép tự do.
- Áp namespace theo môi trường, service và tenant phù hợp.
- Tránh tạo key dài không kiểm soát.

Ví dụ nếu orderId được tạo nội bộ dạng UUID, sử dụng UUID đã validate giúp giảm rủi ro. Tuy nhiên hai chuỗi UUID khác nhau vẫn có thể hash trùng slot do không gian slots hữu hạn; đó không phải vi phạm Redis.

### 9.2. Giữ tag ổn định qua mọi service

Nếu service A tạo:

~~~text
order:{o-101}:status
~~~

mà service B tạo:

~~~text
order:{order-o-101}:payment
~~~

thì việc đọc/ghi multi-key không còn bảo đảm cùng slot.

Hãy định nghĩa một hàm dựng key dùng chung ở ranh giới data-access, hoặc ít nhất có tài liệu key schema và ví dụ nhất quán. Tránh copy-paste chuỗi ghép key ở nhiều controller/service.

### 9.3. Gợi ý thiết kế theo aggregate

Một pattern hữu ích:

~~~text
customer:{customer-101}:profile
customer:{customer-101}:preferences

order:{order-101}:status
order:{order-101}:payment

session:{session-abc}:token
session:{session-abc}:metadata
~~~

Mỗi **aggregate** có nhóm key liên quan cần thao tác cùng nhau và dùng tag riêng. Cách này thường phân phối tải tốt hơn đặt tag theo toàn bộ tenant.

## 10. Giải pháp B: thực hiện nhiều command độc lập khi không cần atomicity

Nếu chỉ cần hiển thị hai thông tin độc lập của hai người dùng, **không cần** ép tất cả key cùng slot.

Ví dụ:

~~~text
user:101:name
user:102:name
~~~

Có thể đọc từng key rồi ghép lại:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public Map<String, String> readIndependentKeys(
        StringRedisTemplate redis, List<String> keys) {

    Map<String, String> result = new LinkedHashMap<>();

    for (String key : keys) {
        result.put(key, redis.opsForValue().get(key));
    }

    return result;
}
~~~

Mỗi `GET` chỉ liên quan một key nên cluster-aware client có thể route tới node sở hữu slot của key đó. Dù thế:

- Lệnh được gửi tuần tự trong vòng lặp, có thể chịu nhiều RTT.
- Không có snapshot nhất quán xuyên hai slot.
- Nếu lệnh thứ hai lỗi, lệnh đầu tiên đã được đọc.
- Khi đọc các key thay đổi liên tục, kết quả có thể phản ánh các thời điểm khác nhau.

Nếu application cần hiệu năng cao, có thể tổ chức các GET đồng thời hoặc theo nhóm bằng client hỗ trợ phân phối cluster-aware. Nhưng cần quản lý concurrency, connection load, timeout và thứ tự ghép kết quả.

### 10.1. ReactiveRedisTemplate và việc gom kết quả

Trong WebFlux:

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;
import reactor.util.function.Tuple2;

Mono<String> first =
        reactiveRedisTemplate.opsForValue().get("user:101:name");
Mono<String> second =
        reactiveRedisTemplate.opsForValue().get("user:102:name");

Mono<Tuple2<String, String>> combined = Mono.zip(first, second);
~~~

Ví dụ này dùng hai Redis `GET` độc lập, không có multi-key native command. Lưu ý `Mono.zip` có thể hoàn tất rỗng nếu một publisher không phát phần tử; khi một key không tồn tại cần chính sách fallback thích hợp để không mất dữ liệu còn lại.

Các Reactor publishers giúp compose I/O, nhưng **không tạo một Redis transaction xuyên slot**.

### 10.2. Scatter/gather là đánh đổi semantics

Một client có thể tự động:

1. Nhóm key theo slot.
2. Gửi một hoặc nhiều requests tới từng node.
3. Thu phản hồi.
4. Phục hồi thứ tự tương ứng với danh sách keys ban đầu.

Đó là **nhiều operations**, dù được trình bày như một method Java. Ưu điểm là ứng dụng dễ dùng; nhược điểm:

- Không có atomicity toàn bộ tập key.
- Một node lỗi có thể làm kết quả chỉ hoàn thành một phần.
- Có thể tăng số request và độ phức tạp retry.
- Dữ liệu ở các node có thể được đọc tại thời điểm khác nhau.

Nếu nghiệp vụ chỉ cần tổng hợp thông tin để hiển thị, scatter/gather có thể chấp nhận. Nếu cần kiểm soát nhất quán, nó không thay thế Redis transaction hoặc data model mới.

## 11. Giải pháp C: gộp nhiều field vào một Redis key

Đôi khi thay vì 5 Redis String keys riêng, một Redis Hash là mô hình phù hợp hơn.

Thay:

~~~text
user:101:name
user:101:email
user:101:city
~~~

bằng:

~~~redis
HSET user:101 name An email an@example.test city Hanoi
HGETALL user:101
~~~

Mọi field nằm trong **một Redis key** `user:101`. `HGETALL` chỉ thao tác trên một key, không bị ràng buộc slot của nhiều Redis keys.

Spring Data Redis:

~~~java
import java.util.Map;
import org.springframework.data.redis.core.StringRedisTemplate;

public class UserHashStore {

    private final StringRedisTemplate redis;

    public UserHashStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveUser(String id, String name, String city) {
        redis.opsForHash().putAll(
                "user:" + id,
                Map.of("name", name, "city", city));
    }

    public Map<Object, Object> loadUser(String id) {
        return redis.opsForHash().entries("user:" + id);
    }
}
~~~

Lợi ích:

- Một hash key thay vì nhiều string keys.
- `HGETALL`/`HMGET` lấy nhiều fields trong cùng một key.
- `HSET` cập nhật một số fields của key.
- Không cần hash tag để ghép nhiều fields trong cùng key.

Nhưng vẫn có những đánh đổi:

- TTL gắn với **cả Redis key** thông thường, không phải TTL độc lập cho từng hash field trong mọi phiên bản/kiểu triển khai.
- Một Hash quá lớn có thể làm thao tác `HGETALL` tốn nhiều băng thông.
- Nếu các field có vòng đời độc lập, gộp chúng có thể không phù hợp.
- Hệ thống vẫn cần serialization và quản lý thay đổi dữ liệu.

Redis có những khả năng hash-field expiration ở các phiên bản mới, nhưng không nên giả định Spring Data Redis và Redis deployment của bạn hỗ trợ mọi API đó; mô hình TTL key-level vẫn là cách suy luận an toàn phổ biến.

### 11.1. Khi nào gộp dữ liệu là hướng tốt?

Gộp cùng Redis Hash khi các field:

- Thuộc một aggregate và thường được đọc cùng nhau.
- Có cùng quyền sở hữu và vòng đời.
- Không cần expiration độc lập.
- Không tạo object quá lớn.
- Không cần giao dịch xuyên nhiều keys.

Nếu các field phải được cập nhật đồng thời theo semantics một Redis command, `HSET` nhiều field trên một key thường đơn giản hơn việc cố tạo Redis transaction cho nhiều String keys.

## 12. Transactions: MULTI/EXEC và WATCH trên Redis Cluster

Redis transaction cho phép các command trong `MULTI`/`EXEC` được thực thi liên tiếp, không có command của client khác xen vào giữa nhóm tại thời điểm thực thi. Redis Cluster không có transaction phân tán chung cho nhiều hash slots.

### 12.1. Giao dịch hợp lệ trong cùng slot

Ví dụ:

~~~redis
MULTI
SET 'account:{a-101}:balance' 900
SET 'account:{a-101}:updatedAt' '2026-11-13T03:00:00Z'
EXEC
~~~

Hai key cùng tag `a-101`. Với một connection tới đúng node sở hữu slot, transaction có thể thực thi nhóm command phù hợp.

### 12.2. Giao dịch nhiều slot không được bảo đảm

Ví dụ:

~~~redis
MULTI
DECRBY 'account:{a-101}:balance' 100
INCRBY 'account:{a-202}:balance' 100
EXEC
~~~

Hai account có tag khác nhau, thông thường thuộc hai slots. Redis Cluster không cung cấp một transaction `MULTI`/`EXEC` nguyên tử xuyên các slot đó. Tùy client/command handling, lỗi có thể xảy ra khi queue lệnh hoặc thực thi.

**Không chữa lỗi bằng cách gửi mỗi account update riêng** nếu nghiệp vụ yêu cầu chuyển tiền nguyên tử. Chia thành hai commands có thể tạo trạng thái tiền bị trừ nhưng chưa được cộng khi mạng lỗi.

Nếu đây là số dư thanh toán, nguồn chuẩn cần một hệ thống/giao thức hỗ trợ consistency thích hợp, như transaction database. Redis có thể là cache/bộ đếm tạm thời hoặc một phần thiết kế đã được kiểm soát.

### 12.3. WATCH cũng chịu giới hạn slot

`WATCH` hỗ trợ optimistic locking: client theo dõi key, đọc dữ liệu, rồi gửi `MULTI`/`EXEC` để cập nhật nếu key chưa bị sửa.

Khi WATCH hoặc transaction liên quan nhiều key trong cluster, các key tham gia cũng cần đáp ứng **cùng slot** để Redis có thể xử lý trên một shard.

~~~text
WATCH account:{a-101}:balance account:{a-101}:limit
... read/check ...
MULTI
... update same-slot keys ...
EXEC
~~~

Trong Spring Data Redis, `SessionCallback` giúp đảm bảo các thao tác transaction dùng cùng một Redis session/connection, nhưng **không làm các key khác slot tự biến thành cùng slot**.

### 12.4. Transaction Redis không rollback như SQL

Đừng hiểu “atomic” ở đây là rollback mọi command trong nhóm nếu có lỗi runtime. Redis transaction `MULTI`/`EXEC` không có automatic rollback kiểu RDBMS khi một command trong `EXEC` thất bại.

Cần phân biệt:

- **Không xen kẽ:** khi `EXEC` thực thi, các lệnh hợp lệ trong nhóm được thực thi liên tiếp.
- **Điều kiện cạnh tranh:** dùng `WATCH` hoặc Lua nếu cần kiểm tra giá trị trước cập nhật.
- **Rollback:** Redis không tự hoàn tác các command đã thực thi thành công khi command sau lỗi.
- **Phân tán nhiều slot:** cluster không cung cấp transaction đa shard nguyên tử chỉ bằng `MULTI`.

## 13. Lua script và Redis Function: cùng slot vẫn là giới hạn quan trọng

Lua/Redis Functions có thể gói logic điều kiện và cập nhật vào một lượt thực thi trên Redis server. Nhưng khi chạy trên Redis Cluster, các key tham gia một script/function phải tuân thủ quy tắc cluster và không được giả định có thể tùy ý thao tác key ở nhiều hash slots.

### 13.1. Ví dụ script cập nhật hai key cùng tag

Giả sử cần giới hạn quota và tăng bộ đếm hành động của một user:

~~~lua
local quotaKey = KEYS[1]
local counterKey = KEYS[2]
local limit = tonumber(ARGV[1])

local quotaUsed = tonumber(redis.call('GET', quotaKey) or '0')
if quotaUsed >= limit then
    return 0
end

redis.call('INCR', quotaKey)
redis.call('INCR', counterKey)
return 1
~~~

Gọi trong Redis CLI với keys cùng tag:

~~~redis
EVAL "local n=tonumber(redis.call('GET',KEYS[1]) or '0'); if n>=tonumber(ARGV[1]) then return 0 end; redis.call('INCR',KEYS[1]); redis.call('INCR',KEYS[2]); return 1" 2 'quota:{u-101}:used' 'quota:{u-101}:actions' 100
~~~

Hai Redis keys dùng chung `{u-101}` nên thuộc cùng slot. Script có thể thực hiện kiểm tra và cập nhật liên tiếp trong một lượt atomic server-side theo semantics của Lua scripting.

### 13.2. Chỉ định keys rõ ràng

Trong Redis scripting, các key được script truy cập nên được truyền qua danh sách `KEYS` tường minh. Không tự tạo tên key mới chỉ từ `ARGV` bên trong script rồi hy vọng cluster tự route tới node khác.

~~~text
KEYS[1] = quota:{u-101}:used
KEYS[2] = quota:{u-101}:actions
ARGV[1] = 100
~~~

Redis Cluster cần biết keys mà command/script tác động để route và kiểm tra ràng buộc slot. Truy cập key khác slot trong một script là một lựa chọn không hợp lệ đối với thao tác cluster thông thường.

### 13.3. Spring Data Redis gọi script

Spring Data Redis cung cấp `RedisScript` và `RedisTemplate.execute(...)` để gọi Lua.

Một ví dụ cấu trúc:

~~~java
import java.util.List;
import org.springframework.data.redis.core.script.DefaultRedisScript;

DefaultRedisScript<Long> script = new DefaultRedisScript<>();
script.setScriptText("""
    local used = tonumber(redis.call('GET', KEYS[1]) or '0')
    if used >= tonumber(ARGV[1]) then return 0 end
    redis.call('INCR', KEYS[1])
    redis.call('INCR', KEYS[2])
    return 1
    """);
script.setResultType(Long.class);

Long result = stringRedisTemplate.execute(
        script,
        List.of(
                "quota:{u-101}:used",
                "quota:{u-101}:actions"),
        "100");
~~~

Ví dụ Java dùng text block (Java 15+) và một `StringRedisTemplate` đã cấu hình. Việc dùng cùng tag đáp ứng yêu cầu slot. Với một số driver/Redis versions, lỗi có thể được bọc trong exception của Spring hoặc Redis client.

**Lưu ý:** Script atomic trên một Redis shard không tạo distributed transaction với database hoặc một shard Redis khác. Script chạy lâu còn có thể chặn xử lý command trên shard đó; nên giữ logic ngắn và không lạm dụng Lua cho mọi thao tác.

## 14. Pipeline không giải quyết CROSSSLOT

**Pipelining** giảm thời gian chờ giữa các command bằng cách gửi nhiều request trước khi đọc tất cả replies. Nó **không** thay đổi luật key placement.

Ví dụ pipeline gồm các command:

~~~text
GET user:101:name
GET user:102:name
GET user:103:name
~~~

Mỗi `GET` có một key. Một driver cluster-aware có thể định tuyến các request riêng tới các node phù hợp theo khả năng hỗ trợ pipeline, giúp giảm overhead. Nhưng không thể suy ra rằng mọi cách dùng `executePipelined(...)` trên một cluster đều hỗ trợ mọi tổ hợp node/connection.

Nếu pipeline chứa:

~~~text
MGET user:101:name user:102:name
~~~

thì đây vẫn là **một command multi-key**. Nếu hai keys khác slot, command native vẫn `CROSSSLOT`.

### 14.1. Pipeline, scatter/gather và transaction

| Kỹ thuật | Giảm round trips? | Truy cập key khác slot? | Atomicity cả nhóm? |
|---|---|---|---|
| Nhiều GET độc lập | Không tự động | Có, qua cluster-aware routing | Không |
| Pipeline các GET độc lập | Có thể, tùy client | Có nếu client hỗ trợ định tuyến/pipeline cluster | Không |
| MGET native | Có, một command | Chỉ khi keys cùng slot | Có semantics một command trên shard |
| High-level MGET scatter/gather | Có thể tối ưu | Có thể theo API/client | Không atomic xuyên slots |
| MULTI/EXEC | Không tự động giảm RTT | Không cho transaction đa slot | Có group execution trên cùng shard |
| Lua/Function | Một lượt server-side | Không tùy ý qua nhiều slot | Atomic trên shard khi thiết kế hợp lệ |

Việc chọn kỹ thuật phải bắt đầu từ yêu cầu dữ liệu, sau đó mới chọn tối ưu network.

## 15. Redis Repository và chỉ mục phụ trên Cluster

Spring Data Redis Repository có thể dùng `@RedisHash`, `@Id` và `@Indexed` để lưu entity, index và metadata. Khi chạy trên Redis Cluster, cần hiểu repository có thể phát ra **nhiều command trên nhiều key nội bộ**, không chỉ một key entity.

Ví dụ một entity:

~~~java
@RedisHash("products")
public class ProductEntity {
    @Id
    private String id;

    @Indexed
    private String category;
}
~~~

Repository có thể lưu entity trong Redis Hash và tạo index structures để hỗ trợ finder. Những key index và entity cần tuân thủ Redis Cluster routing/operations tương ứng.

### 15.1. Không tự suy luận mọi thao tác Repository đều atomic

Một `repository.save(entity)` nhìn giống một lời gọi Java duy nhất, nhưng không có nghĩa phía Redis chỉ thực thi một command atomic. Spring Data Redis Repository xử lý mapping, index và TTL theo cơ chế riêng; cluster placement có thể làm rõ ràng hơn các giới hạn của thao tác nhiều key.

Nếu ứng dụng cần cập nhật entity và index như một transaction atomic, phải kiểm tra hỗ trợ/semantics thực tế; không mặc định Redis Repository đảm bảo điều đó trên Cluster.

### 15.2. Hash tag trên các key do Repository sinh ra

Đừng tự đặt `@RedisHash("products:{tenant}")` rồi giả định mọi key phụ do Repository tạo ra sẽ dùng cùng tag theo ý muốn. Các key nội bộ có thể có conventions khác và repository logic không nhất thiết cho phép kiểm soát toàn bộ key placement dễ dàng.

Một hướng an toàn hơn là:

1. Xác định Redis Cluster có phù hợp với repository model hiện có không.
2. Kiểm tra những commands và keyspaces thực sự phát sinh.
3. Cân nhắc RedisTemplate với key schema tự kiểm soát cho thao tác cần cùng slot.
4. Tách query/index phức tạp sang datastore phù hợp nếu cần consistency mạnh.
5. Đọc tài liệu Spring Data Redis version cụ thể về Redis Cluster và repositories trước khi triển khai.

### 15.3. Redis Cache abstraction và cache key prefix

`RedisCacheManager` thường đặt tên key có dạng:

~~~text
products::101
products::102
~~~

Có prefix giống nhau **không có nghĩa hai keys cùng slot**. Nếu một chức năng cần MGET native nhiều cache keys, việc dùng chung cache name không tự đáp ứng slot constraint.

Tương tự, serializer có thể thay đổi bytes của key; khi tính slot, Redis hash **bytes thực** chứ không phải logical key object trong Java.

## 16. Vì sao một hash tag quá rộng gây hot spot?

Hash tag giải quyết tính đúng đắn của nhiều key cùng slot. Nhưng nếu tất cả key được đặt dưới cùng tag:

~~~text
order:{all}:o-101:status
order:{all}:o-102:status
order:{all}:o-103:status
...
~~~

thì toàn bộ keys đều tập trung vào **một hash slot**, và slot đó thuộc một primary node tại một thời điểm. Redis Cluster không thể phân tán tải của những keys ấy lên các primary node khác nhau khi vẫn giữ cùng slot.

Hậu quả có thể:

- Một node nóng CPU trong khi các node khác nhàn.
- Memory skew: một node giữ phần lớn dữ liệu.
- Network traffic dồn vào một connection/node.
- Một số hotspot của business gây nghẽn không tương xứng với tổng năng lực cluster.
- Thêm node không giúp phân phối một slot nóng ra nhiều node đồng thời.

### 16.1. Tag theo aggregate thay vì toàn hệ thống

Không tốt nếu muốn phân tán:

~~~text
product:{all}:p-101
product:{all}:p-102
product:{all}:p-103
~~~

Tốt hơn cho nhiều aggregate độc lập:

~~~text
product:{p-101}:core
product:{p-101}:stock

product:{p-102}:core
product:{p-102}:stock

product:{p-103}:core
product:{p-103}:stock
~~~

Mỗi product có nhóm key co-located, nhưng các product khác nhau có thể phân bố theo nhiều slots.

### 16.2. Tag theo tenant có phù hợp không?

~~~text
tenant:{t-01}:user:101
tenant:{t-01}:user:102
tenant:{t-01}:orders
~~~

Pattern này giúp nhiều key trong một tenant cùng slot, nhưng tenant lớn có thể trở thành hot spot. Nếu nghiệp vụ chỉ cần atomic theo từng đơn hàng, dùng tag theo `orderId` thường tốt hơn tag theo toàn tenant.

Lựa chọn tag nên dựa trên **ranh giới atomicity nhỏ nhất thật sự cần thiết**. Càng ép nhiều key cùng slot, càng giảm khả năng phân phối tải.

### 16.3. Không lạm dụng hash tag chỉ để "chữa lỗi"

Nếu một endpoint muốn đọc 100.000 user profiles độc lập, không nên cho tất cả keys cùng tag chỉ để chạy `MGET`. Phương án client-side batching/scatter phù hợp có thể tốt hơn vì không buộc dữ liệu nóng vào một shard.

## 17. Khi cần thao tác nhiều key không cùng slot nhưng nghiệp vụ vẫn phải đúng

Có những yêu cầu không thể giải chỉ bằng “đọc nhiều GET”:

- Chuyển số dư giữa hai tài khoản ở hai slots.
- Đặt hàng đồng thời trừ stock nhiều sản phẩm khác nhau.
- Di chuyển một phần tử qua hai Redis Lists ở hai slots.
- Ghi trạng thái và chỉ mục phân tán thuộc hai shard.

Nếu tính nguyên tử xuyên các keys là bắt buộc, có các lựa chọn thiết kế:

### 17.1. Co-locate các keys thực sự thuộc cùng một transaction

Nếu toàn bộ keys thường xuyên cập nhật đồng thời và không gây hot spot quá lớn, dùng một hash tag chung cho **nhóm cụ thể**. Sau đó dùng native multi-key command hoặc Lua/transaction theo semantics thích hợp.

Ví dụ nhiều key của một booking:

~~~text
booking:{b-101}:state
booking:{b-101}:hold
booking:{b-101}:expiresAt
~~~

### 17.2. Gộp dữ liệu vào một key

Một Redis Hash hoặc một JSON String có thể lưu một aggregate với một Redis key. Khi tất cả field nằm trong một key, một số thao tác trở thành một command đơn.

Nhưng phải cân nhắc: payload lớn, contention của aggregate, TTL và chi phí đọc/ghi toàn object.

### 17.3. Dùng nguồn chuẩn có transaction phù hợp

Nếu nghiệp vụ là tiền, tồn kho thực hay quyền truy cập quan trọng, relational database hoặc hệ thống có transaction/constraint phù hợp thường nên giữ trạng thái chuẩn. Redis có thể làm cache/index phụ và được làm mới bằng event/outbox.

Đừng cố mô phỏng distributed ACID transaction bằng hai Redis Lua scripts chạy trên hai shards. Hai scripts riêng không là một transaction nguyên tử toàn cục.

### 17.4. Saga/compensation khi chấp nhận eventual consistency

Một số workflow có thể chia thành các bước với:

1. Business operation ID/idempotency key.
2. Trạng thái từng bước được lưu bền vững.
3. Retry khi một bước thất bại.
4. Compensation khi cần hoàn tác nghiệp vụ.
5. Reconciliation nếu trạng thái không thống nhất.

Cách này phức tạp hơn một transaction và cần quyết định nghiệp vụ rõ ràng. Redis Cluster không tự cung cấp saga, distributed lock toàn hệ thống hoặc compensation.

### 17.5. Multi-key atomicity không đồng nghĩa exactly-once

Ngay cả khi keys cùng slot và một script thành công, client có thể timeout trước khi nhận reply. Retry một `INCR`/`LPUSH` không idempotent có thể thực hiện side effect hai lần. Phải thiết kế idempotency và trạng thái xác nhận khi dùng những thao tác quan trọng.

## 18. Chọn key schema trước khi viết code

Một phương pháp hữu ích là lập bảng **nhóm keys nào phải được cập nhật hoặc đọc nguyên tử**.

| Nghiệp vụ | Nhóm key | Có cần cùng slot? | Gợi ý |
|---|---|---|---|
| Xem profile của hai user độc lập | `user:101`, `user:102` | Không | GET riêng và tổng hợp |
| Cập nhật nhiều thuộc tính cùng một user | `user:{101}:profile`, `user:{101}:settings` | Có nếu muốn một native multi-key operation | Tag theo user hoặc gộp Hash |
| Đọc nhiều items trong giỏ | `cart:{c-101}:item:1`, `cart:{c-101}:item:2` | Có nếu dùng MGET native | Tag theo cart |
| Lấy nhiều danh mục không liên quan | `category:1`, `category:2` | Không bắt buộc | Scatter/gather hoặc cache một aggregate |
| Chuyển tiền hai account | `account:{a-101}`, `account:{a-202}` | Không thể áp transaction đa slot | Thiết kế DB transaction hoặc model mới |
| Một booking có state và hold | `booking:{b-101}:state`, `booking:{b-101}:hold` | Có nếu cần script/transaction | Tag theo booking |
| Ghi log của nhiều user | Nhiều stream keys | Không nếu mỗi XADD độc lập | Lệnh độc lập; xử lý lỗi từng lệnh |

Cách chọn tag tốt là đặt **ranh giới dữ liệu** trùng **ranh giới atomicity**. Nếu một nhóm quá lớn, phải cân nhắc chia workflow và chấp nhận eventual consistency có kiểm soát.

### 18.1. Key builder trong Java

Có thể tập trung quy tắc dựng key:

~~~java
public final class RedisClusterKeys {

    private RedisClusterKeys() {
    }

    public static String orderStatus(String orderId) {
        return "order:{" + validate(orderId) + "}:status";
    }

    public static String orderPayment(String orderId) {
        return "order:{" + validate(orderId) + "}:payment";
    }

    private static String validate(String id) {
        if (id == null || !id.matches("[a-zA-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid id");
        }
        return id;
    }
}
~~~

Hai methods dùng cùng validated ID nên luôn đưa về cùng hash tag. Nếu ID nghiệp vụ được phép có nhiều ký tự đặc biệt hoặc dạng binary, xây dựng encoding chuẩn thay vì cấm tùy ý.

### 18.2. Namespace và version

Ví dụ:

~~~text
app:v2:order:{o-101}:status
app:v2:order:{o-101}:payment
~~~

Dù prefix thay đổi, phần tag vẫn là `o-101` nên hai key cùng slot. Nếu cập nhật schema cần migration từ `v1` sang `v2`, nên có kế hoạch chuyển đổi vì đổi key name không tự chuyển nội dung.

## 19. Các trường hợp đặc biệt dễ bị bỏ sót

### 19.1. RENAME và COPY cũng cần xét cả source và destination

Một application dùng:

~~~redis
RENAME 'cache:{old}:profile' 'cache:{new}:profile'
~~~

Đây là một command thao tác trên hai Redis keys. Nếu hai tag tạo slots khác nhau, command không phải một thao tác rename hợp lệ xuyên slot trên Redis Cluster.

Nếu muốn di chuyển dữ liệu xuyên slot, cần quy trình copy/read-write/delete qua client và xử lý các trạng thái thất bại một phần. **Đừng coi chuỗi copy → delete là một rename nguyên tử**.

### 19.2. XREAD nhiều Streams

Một `XREAD STREAMS stream-A stream-B ...` là command có nhiều stream keys. Với Redis Cluster, các stream keys phải phù hợp slot constraints nếu thực hiện trong cùng command.

Thay vì gộp stream của mọi tenant vào một command, có thể:

- Dùng một stream chung nếu phù hợp kiến trúc và tải.
- Đặt các stream liên quan cùng tag nếu cần đọc nhiều stream trong một lệnh.
- Dùng nhiều subscriptions/consumers đọc riêng các streams thuộc khác slots.

Cần cân nhắc tải và độ tin cậy, không ép mọi stream vào một slot quá nóng chỉ để dùng một XREAD.

### 19.3. DEL nhiều key

~~~redis
DEL 'cache:{u-101}:a' 'cache:{u-202}:b'
~~~

Có thể lỗi `CROSSSLOT`. Một vòng lặp mỗi `DEL` một key có thể xóa cả hai nhưng không atomic xuyên slots. Nếu chỉ xóa cache có thể tái tạo, đây thường là sự đánh đổi chấp nhận được. Nếu xóa là một bước nghiệp vụ quan trọng, phải thiết kế idempotency và recovery.

### 19.4. Multi-key Set/Sorted Set commands

~~~redis
SINTER 'roles:{u-101}:assigned' 'roles:{u-101}:allowed'
~~~

Cùng tag, có thể thực thi trên một shard. Nhưng:

~~~redis
SINTER 'roles:{u-101}:assigned' 'roles:{u-202}:assigned'
~~~

không bảo đảm cùng slot. Muốn tính giao giữa dữ liệu của nhiều user, cân nhắc đọc Sets riêng rồi giao tại client hoặc đặt query model trong hệ thống phù hợp; nếu cần snapshot nhất quán xuyên users, đọc riêng không đáp ứng được.

### 19.5. Wildcard không làm các key cùng slot

Tên key:

~~~text
products:*
products:{*}:*
~~~

không phải cách ép keys cùng slot. Wildcard là pattern của những command như `SCAN`/`KEYS`, không phải hash tag chung cho tất cả keys đã có.

`{*}` khi là ký tự literal trong key sẽ được xem là tag `*`, nhưng nó **không có nghĩa match toàn bộ key** trong quy tắc hash slot. Tránh nhầm syntax pattern với hash tag.

### 19.6. SCAN ở Redis Cluster

`SCAN` thông thường làm việc trong phạm vi node/connection; để duyệt tất cả keys trong Cluster có thể phải chạy trên từng primary node hoặc dùng API cluster-aware thực hiện phân phối. Đây không phải một command multi-key bị CROSSSLOT, nhưng liên quan đến kỳ vọng “một Redis connection thấy toàn bộ keyspace”.

Không dùng `KEYS *` để quét production cluster lớn. Giới hạn số lượng key/cursor và đo tác động của scan.

### 19.7. Multi-key trong cluster khi có serializer lạ

Ứng dụng có thể dựng Java key `order:{o-101}:status` nhưng serialize bằng JDK binary format trước khi gửi Redis. Nếu bytes thực có những metadata/prefix, hình thức của chuỗi `{o-101}` có thể không còn như dự tính.

Hash slot được tính từ **serialized Redis key bytes**. Đối với key grouping có hash tag, ưu tiên `StringRedisSerializer` hoặc một serializer kiểm soát và giữ đúng bytes của tag.

## 20. Debug từ exception đến key schema

Giả sử log ứng dụng:

~~~text
org.springframework.dao.DataAccessException: ...
CROSSSLOT Keys in request don't hash to the same slot
~~~

Trình tự chẩn đoán:

**Bước 1 — Tìm đúng command hoặc API.**

- `multiGet` hay `multiSet`?
- `delete(Collection)`?
- Lua `execute` với danh sách keys?
- `WATCH`/`MULTI`/`EXEC`?
- Một thao tác repository có nhiều key?
- Một lệnh `XREAD` có nhiều streams?

**Bước 2 — Liệt kê các Redis key arguments của đúng command.**

Đừng liệt kê mọi field/value rồi hiểu nhầm là keys.

**Bước 3 — Kiểm tra key bytes và hash slots.**

~~~bash
redis-cli -c -h node-1.internal -p 6379 CLUSTER KEYSLOT 'order:{o-101}:status'
redis-cli -c -h node-1.internal -p 6379 CLUSTER KEYSLOT 'order:{o-101}:payment'
~~~

Nếu dữ liệu do serializer nhị phân tạo, dùng tooling thích hợp để xác định đúng bytes thay vì chỉ nhìn chuỗi Java trong debugger.

**Bước 4 — Xác định tính nguyên tử có bắt buộc không.**

- Không bắt buộc: gửi nhiều commands đơn lẻ/cluster-aware batching.
- Bắt buộc trên nhóm nhỏ: thiết kế hash tag chung hoặc một Redis Hash.
- Bắt buộc xuyên shard: cần thay đổi mô hình transaction/consistency.

**Bước 5 — Kiểm tra lại key schema ở mọi producer.**

Một service dùng `user:{101}:profile` và service khác dùng `user:101:settings` thì chỉ riêng việc sửa một code path là chưa đủ.

**Bước 6 — Theo dõi hạ tầng.**

Nếu slot cùng nhau mà vẫn lỗi tạm thời trong resharding, xem MOVED/ASK/TRYAGAIN, topology refresh và failover handling. Không gộp tất cả lỗi vào nhánh “CROSSSLOT fix”.

## 21. Testing với Redis Cluster thực thay vì standalone

Một lỗi phổ biến là viết unit/integration tests trên Redis standalone, nên lệnh `MGET key1 key2` luôn chạy được. Sau deploy cluster, cùng code mới `CROSSSLOT`.

### 21.1. Test điều kiện slot

Với một key builder:

~~~java
String status = RedisClusterKeys.orderStatus("o-101");
String payment = RedisClusterKeys.orderPayment("o-101");
~~~

Có thể kiểm tra bằng Redis Cluster thực:

~~~text
CLUSTER KEYSLOT status
CLUSTER KEYSLOT payment
~~~

Phải bằng nhau. Test này xác nhận key schema chứ không kiểm tra Spring method có transaction hay không.

### 21.2. Tổ chức test cases

| Test case | Mong đợi |
|---|---|
| Hai key cùng hash tag, `MGET` | Hoạt động, theo đúng data type |
| Hai key khác slot, raw `MGET` | `CROSSSLOT` |
| Hai independent `GET` khác slot | Hoạt động qua cluster-aware client |
| `MULTI` với same-slot keys | Hoạt động trong điều kiện hỗ trợ |
| `MULTI` với cross-slot keys | Không được dùng như distributed transaction |
| Lua with `KEYS` cùng slot | Có thể chạy nếu script/command hợp lệ |
| Lua with cross-slot keys | Bị giới hạn bởi cluster rules |
| Driver xử lý `MOVED` | Tự route/refresh topology theo cấu hình |
| Resharding/failover | Ứng dụng có retry/backoff và xử lý lỗi thích hợp |
| Serialization khác nhau | Phát hiện key/slot không còn như dự kiến |

Không cần chạy Redis Cluster benchmark ở production để kiểm tra các quy tắc này; môi trường integration test riêng hoặc staging gần giống topology thực tế tốt hơn.

### 21.3. Không tự động bắt mọi cross-slot và retry

Một retry policy phù hợp phân loại exception:

~~~text
CROSSSLOT do schema sai       -> fail fast, cảnh báo sửa data model
MOVED/ASK                     -> client cluster-aware xử lý routing
TRYAGAIN hoặc transient I/O   -> retry có giới hạn/backoff nếu operation an toàn
Timeout của lệnh không idempotent -> cần kiểm tra trạng thái/idempotency
~~~

Với lỗi `CROSSSLOT` do key placement cố định, thêm retry chỉ làm tăng lưu lượng lỗi và latency.

## 22. Hiệu năng và khả năng phân phối tải sau khi sửa CROSSSLOT

Giải quyết `CROSSSLOT` mới là điều kiện về tính hợp lệ. Một key schema tốt còn cần xét:

- Slot distribution giữa primary nodes.
- Dữ liệu/CPU dồn vào một nhóm hash tags.
- Workload read/write theo aggregate.
- Batch sizes và network round trips.
- Multi-key operations có gây lock contention/long execution không.
- Chi phí copy/reshape data model.
- Khả năng mở rộng khi thêm primary nodes.

### 22.1. Hash tag quá rộng

Nếu mọi key cùng `{global}`, Cluster về logic phải đặt chúng cùng slot. Hệ thống có nhiều node nhưng không khai thác phân phối cho nhóm key đó.

### 22.2. Hash tag quá hẹp

Nếu cần transaction trên ba key nhưng tag khác nhau, Redis trả `CROSSSLOT`. Phải chọn ranh giới co-location đúng với invariant nghiệp vụ.

### 22.3. Co-location không làm lệnh chạy nhanh hơn mặc định

Cùng slot giúp command hợp lệ; performance còn tùy payload, command complexity và node load. Một `MGET` với hàng nghìn values lớn có thể gây network spike và tail latency. Giới hạn batch, theo dõi P95/P99 và Redis memory là cần thiết.

### 22.4. Multi-key API tự scatter có thể thay đổi latency

Một high-level API được client tách thành nhiều per-slot requests có thể tốn thêm round trips và gây partial errors. Khi đo hiệu năng, cần biết code thực hiện native một lệnh hay nhiều lệnh được ghép kết quả.

## 23. Câu hỏi thường gặp

**Câu 1. Redis Cluster có cấm `MGET` không?**

Không. `MGET` hoạt động khi các key thuộc cùng hash slot. Nếu khác slot, native command sẽ bị `CROSSSLOT`.

**Câu 2. Hai key nằm trên cùng Redis node thì có chắc `MGET` được không?**

Không. Redis Cluster phân tích **hash slot**, không chỉ node hiện tại. Hai slot khác nhau có thể cùng node mà vẫn không hợp lệ trong một native multi-key command.

**Câu 3. Thêm `-c` cho redis-cli có sửa được `CROSSSLOT` không?**

Không. `-c` giúp xử lý redirections như MOVED/ASK, không thay đổi slot placement.

**Câu 4. Vì sao đặt cùng prefix `user:` vẫn lỗi?**

Prefix thông thường không điều khiển slot grouping. Dùng cùng hash tag, ví dụ `user:{101}:profile` và `user:{101}:settings`.

**Câu 5. Có thể thêm hash tag sau khi key đã tồn tại mà không cần migration không?**

Đổi tên key là đổi Redis key; dữ liệu cũ không tự xuất hiện dưới tên mới. Phải có migration/dual-read/backfill hoặc có thể rebuild từ nguồn chuẩn khi chỉ là cache.

**Câu 6. Hash tag có tự khiến hai lệnh SET atomic không?**

Không. Nó chỉ khiến hai key cùng slot. Cần một command có semantics phù hợp, transaction hoặc Lua khi muốn bảo vệ chuỗi cập nhật.

**Câu 7. Spring `multiGet` có luôn ném `CROSSSLOT` với key khác slot không?**

Không nên khẳng định cho mọi driver và version. Một số client APIs có thể scatter/gather; cần xem implementation. Nếu dùng native MGET thì vẫn có slot constraint và không có atomic multi-slot.

**Câu 8. Lua script có thể thực hiện transaction xuyên hai slots không?**

Không theo Redis Cluster thông thường. Script chạy trên một shard và các keys liên quan cần phù hợp cluster key-slot rules.

**Câu 9. Lệnh `HSET` ghi nhiều fields có bị `CROSSSLOT` không?**

Không vì các fields của một Redis Hash thuộc **một Redis key**. Chỉ có một key argument trong lệnh `HSET`.

**Câu 10. Thêm nhiều Redis nodes có sửa lỗi `CROSSSLOT` không?**

Không. Lỗi là do command dùng nhiều key khác slot; tăng nodes không thay hash slot của mỗi key.

**Câu 11. Cùng hash tag có làm giảm khả năng mở rộng không?**

Có thể. Tất cả keys dùng cùng tag rơi vào một slot, tạo hotspot nếu nhóm quá lớn/hot. Chỉ co-locate những keys thực sự cần atomic multi-key operations.

**Câu 12. Redis Repository có tự tránh toàn bộ `CROSSSLOT` không?**

Không nên giả định. Repository có thể tạo key/index/metadata nội bộ; cần kiểm tra support và data model của Spring Data Redis version thực tế.

**Câu 13. Khi nào nên đọc nhiều GET thay vì MGET?**

Khi keys độc lập, nằm ở nhiều slot và không cần snapshot atomic. Có thể dùng cluster-aware parallel fetching với giới hạn concurrency.

**Câu 14. Khi nào nên dùng Redis Hash thay vì nhiều String keys?**

Khi các fields thuộc cùng aggregate, có vòng đời tương tự, thường được đọc/cập nhật cùng nhau và không cần TTL độc lập.

**Câu 15. Lỗi `CROSSSLOT` có thể do serializer không?**

Có thể liên quan. Redis hash **bytes thực của key**. Nếu serializer làm thay đổi bytes hoặc hash tag, key-placement khác kỳ vọng. Ưu tiên StringRedisSerializer và key schema rõ ràng khi dùng tags.

**Câu 16. Transaction `MULTI`/`EXEC` có rollback kiểu SQL nếu một lệnh lỗi không?**

Không. Redis transaction có semantics atomic về sự xen kẽ thực thi nhưng không tự rollback những lệnh đã thành công khi lệnh sau lỗi runtime.

## 24. Checklist trước khi triển khai multi-key operations trên Cluster

1. **Xác định key arguments** của từng command thay vì nhìn vào số lượng tham số.
2. **Đo hash slots** bằng `CLUSTER KEYSLOT` với key bytes đúng.
3. **Xác định có cần atomicity** xuyên các keys không.
4. **Chọn hash tag** theo aggregate nhỏ nhất thực sự cần co-location.
5. **Tránh tag toàn cục** gây hot slot.
6. **Kiểm tra serializer** của Redis key khi dùng Spring Data Redis.
7. **Đảm bảo Spring driver cluster-aware** và topology refresh phù hợp.
8. **Phân biệt native multi-key command** với client scatter/gather.
9. **Không nhầm pipeline/parallel** với transaction.
10. **Với WATCH/MULTI/EXEC/Lua**, đảm bảo mọi key liên quan đáp ứng slot constraint.
11. **Với Repository**, kiểm tra keyspace/index/TTL và các lệnh phát sinh.
12. **Với key cũ**, có kế hoạch migration thay vì đổi prefix và giả định Redis tự chuyển.
13. **Test trên Redis Cluster thực**, không chỉ standalone.
14. **Phân loại CROSSSLOT/MOVED/ASK/TRYAGAIN** trước khi retry.
15. **Đo phân phối tải** và hotspot sau khi grouping keys.
16. **Thiết kế idempotency** khi operation có thể thành công dù client mất reply.
17. **Không dùng cache đa slot** thay cho nguồn giao dịch chuẩn khi tính đúng đắn là bắt buộc.

## 25. Tổng kết

**CROSSSLOT là thông báo một command cần nhiều Redis keys nhưng chúng không thuộc cùng hash slot.** Redis Cluster sử dụng 16.384 slots, tính từ `CRC16(key bytes) % 16384`, và hỗ trợ `{hash-tag}` để co-locate các key liên quan.

Với Spring Data Redis, cần phân biệt API Java với Redis command thực tế. Một số high-level methods có thể phân phối nhiều operations qua các slot, nhưng việc đó không làm `MGET`/`MULTI`/`EVAL` native trở thành atomic xuyên Cluster. `-c`, MOVED/ASK routing, pipelining hoặc ReactiveRedisTemplate cũng không xóa ràng buộc slot.

Ba hướng xử lý chính:

- **Cần native multi-key hoặc atomic group:** thiết kế cùng hash tag theo aggregate và dùng đúng Redis command/transaction/Lua.
- **Các key độc lập:** gửi các command riêng, hoặc dùng client hỗ trợ scatter/gather với giới hạn concurrency và chấp nhận không atomic.
- **Ranh giới nghiệp vụ phức tạp:** cân nhắc một Redis Hash, mô hình nguồn chuẩn có transaction hoặc giao thức eventual consistency được thiết kế rõ.

Quy tắc cuối cùng: **đưa những key thật sự phải đồng bộ về cùng một slot, nhưng không ép toàn bộ hệ thống về một slot chỉ để tránh lỗi.** Hash tag đúng giúp giữ tính hợp lệ của command mà vẫn bảo toàn khả năng phân tán tải của Redis Cluster.

## Tài liệu tham khảo

- Redis — [Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): 16.384 hash slots, CRC16, hash tags, routing, MOVED/ASK và multi-key restrictions.
- Redis — [Redis Cluster tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/): topology, slot mapping và vận hành Redis Cluster.
- Redis — [CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/): tính slot từ tên key.
- Redis — [MGET](https://redis.io/docs/latest/commands/mget/): lệnh đọc nhiều String keys.
- Redis — [MSET](https://redis.io/docs/latest/commands/mset/): lệnh ghi nhiều String keys và semantics.
- Redis — [Redis transactions](https://redis.io/docs/latest/develop/interact/transactions/): MULTI/EXEC, WATCH và giới hạn rollback.
- Redis — [Redis scripting](https://redis.io/docs/latest/develop/programmability/eval-intro/): EVAL, KEYS/ARGV và atomic server-side logic.
- Spring Data Redis — [Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html): Cluster configuration, slot operations và cluster-aware APIs.
- Spring Data Redis — [RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): template methods, serializers và connection handling.
- Spring Data Redis — [Redis Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): SessionCallback và transaction semantics.
