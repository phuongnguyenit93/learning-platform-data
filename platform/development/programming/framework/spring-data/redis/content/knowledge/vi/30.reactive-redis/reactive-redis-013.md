# Kiểm tra hỗ trợ giao dịch, scripting và topology của API phản ứng

**Spring Data Redis Reactive** cung cấp API không chặn (non-blocking) để ứng dụng Spring xử lý thao tác Redis qua các kiểu `Mono` và `Flux` của Reactor. Tuy nhiên, một ứng dụng có thể viết được mã reactive **không có nghĩa tất cả tính năng của `RedisTemplate` đồng bộ được ánh xạ tương đương** sang `ReactiveRedisTemplate`. Đặc biệt, cần kiểm tra kỹ ba nhóm năng lực:

1. **Giao dịch (transaction):** có thể tạo ranh giới `MULTI`/`EXEC`, `WATCH`, đồng bộ với Spring transaction hay không?
2. **Scripting:** có thể chạy Lua `EVAL`/`EVALSHA` trong reactive flow, truyền `KEYS`/`ARGV`, nhận kết quả và xử lý lỗi ra sao?
3. **Topology:** thao tác có chạy đúng trên standalone, Sentinel, Redis Cluster, master/replica và khi failover hay không?

Đây không chỉ là chuyện một phương thức Java có tồn tại. Một tính năng phải được đánh giá xuyên qua **phiên bản Spring Data Redis**, **Redis driver**, **cấu hình connection factory**, **topology triển khai** và **ngữ nghĩa server Redis**.

Mục tiêu thực tế là không biến sự có mặt của một lời gọi trong API thành lời hứa về atomicity, transaction management, định tuyến cụm hoặc bảo đảm xử lý đúng một lần.

## 1. Bốn tầng hỗ trợ cần xác minh

Một ứng dụng Reactive Redis đi qua các tầng:

```text
Spring WebFlux / Reactor application
                 |
                 v
     ReactiveRedisTemplate
     ReactiveStringRedisTemplate
                 |
                 v
      ReactiveRedisConnection
      ReactiveRedisConnectionFactory
                 |
                 v
        Lettuce reactive driver
                 |
                 v
     Redis Standalone / Sentinel
      Redis Cluster / Replicas
```

Mỗi tầng có trách nhiệm riêng:

| Tầng | Câu hỏi cần kiểm tra |
|---|---|
| **Reactor** | Publisher có được subscribe đúng lúc, có giữ thứ tự khi cần, có giới hạn concurrency và không chặn event loop không? |
| **Spring Data Redis reactive API** | Có phương thức reactive phù hợp cho nhóm lệnh định dùng không? Return type và serializer là gì? |
| **Driver/connection factory** | Driver có hỗ trợ reactive, reconnect, script cache, cluster routing, read preference và lifecycle như yêu cầu không? |
| **Redis server/topology** | Server có lệnh cần dùng không? Những khóa nào cùng hash slot? Có replica lag, failover hoặc ràng buộc phiên bản không? |

Ví dụ `ReactiveStringRedisTemplate.opsForValue().set(...)` trả `Mono<Boolean>`. Điều này xác nhận có API reactive cho một lệnh `SET` thông thường; **không xác nhận** rằng ba lệnh `SET` nối với nhau tạo thành một transaction.

Tương tự, `ReactiveRedisTemplate.execute(script, ...)` cho phép chạy Lua theo hợp đồng script executor, nhưng không có nghĩa script nhiều khóa có thể tự phân tán trên nhiều master của Redis Cluster.

## 2. Nền tảng Spring Data Redis Reactive

Một ứng dụng Spring Boot sử dụng WebFlux và Redis có thể khai báo dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Ứng dụng cần một `ReactiveRedisConnectionFactory` phù hợp. Trong cấu hình Redis Reactive phổ biến, **Lettuce** là driver cung cấp cơ chế kết nối reactive; không được giả định rằng một connection factory dành riêng cho driver đồng bộ khác cũng hỗ trợ Reactive Redis.

Spring Boot có thể tự cấu hình `ReactiveStringRedisTemplate` hoặc bean reactive tương ứng khi các điều kiện autoconfiguration được thỏa. Nếu tự khai báo bean, cần kiểm tra serializer và tránh tạo hai cấu hình connection factory không thống nhất.

Ví dụ sử dụng cơ bản:

```java
import java.time.Duration;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveStatusStore {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveStatusStore(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> putStatus(String orderId, String state) {
        return redis.opsForValue().set(
                "order:" + orderId + ":state",
                state,
                Duration.ofMinutes(5));
    }

    public Mono<String> getStatus(String orderId) {
        return redis.opsForValue()
                .get("order:" + orderId + ":state");
    }
}
```

`Mono<String>` từ `GET` có thể hoàn thành rỗng khi không có khóa; khác với phương thức đồng bộ trả `null`. Khi thiết kế API, phân biệt **giá trị rỗng**, **lỗi Redis** và **giá trị mặc định được ứng dụng tự chọn**.

### 2.1. Publisher là mô tả công việc, không phải kết quả đã thực thi

Trong Reactor, một `Mono` thường chỉ bắt đầu chạy khi có subscription:

```java
Mono<Boolean> command = redis.opsForValue()
        .set("order:1001:state", "READY");

// Không được hiểu rằng dòng trên đã chắc chắn gửi SET tới Redis.
// Subscription của caller mới kích hoạt execution theo mô hình reactive.
```

WebFlux thường subscribe vào publisher trả từ controller. Không nên gọi `subscribe()` thủ công trong service chỉ để “bắt đầu Redis command”, rồi trả một publisher khác không biểu diễn kết quả thật của lệnh đã chạy.

Sai về mặt thiết kế:

```java
public Mono<Void> updateOrder(String id) {
    redis.opsForValue()
            .set("order:" + id + ":state", "READY")
            .subscribe(); // Fire-and-forget, lỗi thoát khỏi flow.

    return Mono.empty();
}
```

Đúng hơn là trả một flow mà caller có thể chờ hoàn tất và nhận lỗi:

```java
public Mono<Void> updateOrder(String id) {
    return redis.opsForValue()
            .set("order:" + id + ":state", "READY")
            .then();
}
```

Một publisher **bị subscribe nhiều lần có thể gây nhiều thao tác ghi**. Với `INCR`, `LPUSH` hoặc side effect không idempotent, phải đặc biệt cẩn thận khi áp dụng `retry()`, `repeat()` hay chia sẻ cùng publisher giữa nhiều subscriber.

## 3. Ma trận năng lực: không đánh đồng từng API

Trước khi chọn giải pháp, có thể phân biệt:

| Năng lực | Trong Spring Data Redis reactive | Điểm cần xác minh |
|---|---|---|
| `GET`, `SET`, Hash, List, Set, Sorted Set | Có các thao tác reactive tương ứng phổ biến | Serializer, return type, driver/server version |
| `Mono.then(...)` để chạy tuần tự | Là cơ chế Reactor, không phải Redis transaction | Lỗi sau lệnh đầu không rollback |
| `@Transactional` trên reactive service | Có thể tham gia transaction của resource có reactive transaction manager phù hợp | **Không mặc định bao gồm Redis** |
| `MULTI`/`EXEC`/`WATCH` | Không được mặc định có tích hợp reactive tương đương `RedisTemplate.execute(SessionCallback)` | Kiểm tra API/driver/version và yêu cầu cùng connection |
| Lua `EVAL`/`EVALSHA` | Có đường chạy script qua reactive script executor trong các phiên bản hỗ trợ | Kết quả, script cache, serialization, lỗi, slot |
| Redis Cluster | Có thể truy cập qua Lettuce với cấu hình cluster thích hợp | Routing, slot, multi-key, topology refresh |
| Sentinel/failover | Có thể dùng cấu hình kết nối phù hợp | Reconnect và trạng thái kết quả không xác định khi lỗi |
| Replica reads | Tùy driver/cấu hình topology và read preference | Eventual consistency, không hứa read-your-writes |
| Pipelining/throughput reactive | Có thể phát nhiều lệnh không chặn và quản lý demand | Không phải transaction và không có bảo đảm all-or-nothing |

Điểm quan trọng không phải ghi nhớ một bảng “có/không” cho mọi phiên bản. Khi dự án nâng cấp Spring Data Redis, Lettuce hoặc Redis server, **phải đối chiếu hợp đồng API và hành vi của phiên bản thực tế**. Nếu reactive API không cung cấp một khả năng đồng bộ đầy đủ, không ép mô hình bằng cách gọi blocking API ngay trên event-loop thread.

## 4. Reactive sequencing không phải transaction

Giả sử hệ thống cần thay đổi trạng thái đơn hàng và thêm đơn vào một tập Redis.

```java
public Mono<Void> markReady(String orderId) {
    String statusKey = "order:" + orderId + ":status";

    return redis.opsForValue()
            .set(statusKey, "READY")
            .then(redis.opsForSet()
                    .add("orders:ready", orderId))
            .then();
}
```

`then(...)` mô tả thực hiện publisher kế tiếp sau khi publisher trước hoàn tất bình thường. Đây là **thứ tự ở phía ứng dụng**, không phải ranh giới giao dịch Redis.

```text
Client reactive                      Redis
      |                                |
      | ------- SET status ----------> |
      | <------ SET response --------- |
      |                                |
      | --- SADD orders:ready -------> |
      | <----- SADD response --------- |
      |                                |
```

Giữa hai command, client khác có thể đọc hoặc ghi dữ liệu. Nếu `SET` đã thành công nhưng `SADD` lỗi, Redis không tự hoàn tác `SET`.

### 4.1. Mono.when cũng không làm lệnh nguyên tử

```java
return Mono.when(
        redis.opsForValue().set(statusKey, "READY"),
        redis.opsForSet().add("orders:ready", orderId));
```

`Mono.when` phối hợp kết quả hoàn thành của nhiều publisher. Nó không đưa các lệnh vào một transaction và có thể kích hoạt các thao tác đồng thời. Không coi `when`, `zip`, `flatMap` hoặc `concatMap` là tên khác của `MULTI`/`EXEC`.

### 4.2. @Transactional không tự bao phủ Redis reactive

Trong Spring, `@Transactional` là một phần của cơ chế quản lý transaction theo tài nguyên. Một method reactive có thể dùng `ReactiveTransactionManager` cho R2DBC hoặc tài nguyên phù hợp, nhưng điều đó **không làm các lệnh `ReactiveRedisTemplate` tự động tham gia cùng một Redis transaction**.

```java
@Transactional
public Mono<Void> updateOrder(String id) {
    return redis.opsForValue().set("order:" + id, "READY")
            .then(redis.opsForSet().add("orders:ready", id))
            .then();
}
```

Đoạn trên **không được xem là bằng chứng** rằng hai thao tác Redis sẽ `MULTI`/`EXEC` hoặc cùng rollback. Ngay cả khi method còn cập nhật database R2DBC, transaction database cũng không tự trở thành distributed transaction nguyên tử với Redis.

Khi cần đồng bộ giữa database và Redis, kiến trúc thường cần xác định nguồn sự thật, outbox, event, retry idempotent hoặc quy trình bù. Không dùng annotation như một cách xóa bỏ ranh giới hai hệ thống.

## 5. Vấn đề cùng connection khi muốn MULTI/EXEC

Redis transaction `MULTI`/`EXEC` có trạng thái **gắn với connection**:

```text
Connection C1:
    MULTI
    SET key-a value-a
    SET key-b value-b
    EXEC

Connection C2:
    không tự tham gia transaction của C1
```

Trong imperative Spring Data Redis, `RedisTemplate.execute(SessionCallback)` là đường quen thuộc để giữ những thao tác dùng cùng connection và gọi `multi()`/`exec()`. Không được suy luận rằng `ReactiveRedisTemplate` có thể sử dụng nguyên xi `SessionCallback` đồng bộ hoặc mọi publisher riêng rẽ đều có chung một transaction session.

Một transaction Redis ở mức driver cần tối thiểu:

1. Cùng một connection cho `MULTI`, các lệnh queue và `EXEC`.
2. Không chia sẻ connection transaction bừa bãi với những lệnh của luồng khác.
3. Xử lý trạng thái `DISCARD` khi chưa gửi `EXEC` mà gặp lỗi.
4. Đọc kết quả tại `EXEC`, không dùng giá trị lệnh queue để quyết định nhánh.
5. Xử lý timeout/mất kết nối tại `EXEC` như trường hợp **có thể không biết chắc transaction đã chạy hay chưa**.
6. Xét Redis Cluster: transaction nhiều khóa phải tương thích hash slot.

Nếu requirement thực sự bắt buộc `WATCH`/`MULTI`/`EXEC`, cần **kiểm tra chính xác low-level reactive connection API và native driver** đang sử dụng. Không viết code giả định một API chưa được xác nhận tồn tại trong phiên bản của dự án.

### 5.1. Những lựa chọn khi reactive transaction không phù hợp

Có ba hướng thiết kế:

- **Dùng một lệnh Redis nguyên tử phù hợp** như `INCRBY`, `SET ... NX PX` hoặc `HINCRBY` nếu nghiệp vụ đủ hẹp.
- **Dùng Lua script qua reactive script executor** để kiểm tra điều kiện và cập nhật tại Redis trong một lần thực thi.
- **Dùng một adapter imperative có ranh giới rõ ràng** cho transaction `RedisTemplate.execute(SessionCallback)` nếu bắt buộc, nhưng cách này có blocking I/O, cần được cách ly khỏi event loop và phải kiểm soát thread pool/timeout.

Hướng thứ ba không biến thao tác blocking thành non-blocking. Nó chỉ là một điểm tương thích được điều phối an toàn, phải được đo tải và giám sát.

## 6. Vì sao Lua scripting thường phù hợp hơn trong luồng reactive?

Lua script đưa logic “đọc → kiểm tra → ghi” tới phía Redis server:

```text
Reactive application                  Redis primary
         |                                  |
         | ---- EVAL script -------------> |
         |                                  | GET inventory
         |                                  | kiểm tra đủ hàng
         |                                  | DECRBY inventory
         | <--- result ------------------- |
         |                                  |
```

Ứng dụng chỉ cần một lời gọi reactive, không phụ thuộc việc duy trì một chuỗi command trên cùng Redis connection ở phía client để đảm bảo khoảng đọc–ghi không bị lệnh khác chen ngang.

Redis thực thi script như một đơn vị không bị lệnh từ client khác chen giữa trên server thực thi. Điều này hữu ích khi cần:

- Trừ tồn kho khi số lượng còn đủ.
- Chỉ thay đổi trạng thái khi giá trị hiện tại đúng kỳ vọng.
- Đánh dấu một request đã xử lý để giảm lặp.
- Cập nhật một số cấu trúc Redis liên quan trong cùng ranh giới xử lý trên một primary.

**Lưu ý:** Tính nguyên tử về lịch thực thi **không có nghĩa rollback khi script lỗi sau ghi**. Nếu script đã `INCR` thành công rồi lệnh thứ hai lỗi, ghi trước đó vẫn có thể tồn tại. Khi chọn scripting, phải kiểm tra tất cả đầu vào và kiểu key trước mutation, giới hạn số bước ghi và có chính sách idempotency.

## 7. ReactiveRedisTemplate.execute(script): hình thức sử dụng

Spring Data Redis có khái niệm `RedisScript<T>`; `DefaultRedisScript<T>` chứa source Lua và kiểu kết quả. Với reactive API, các phiên bản hỗ trợ cung cấp đường thực thi script qua `ReactiveRedisTemplate.execute(...)` hoặc `ReactiveRedisOperations` tương ứng, trả publisher chứa kết quả.

### 7.1. Khai báo script thành bean

Ví dụ một script trừ tồn kho **chỉ khi số lượng đủ**. Để minh họa lỗi và giới hạn rollback rõ ràng, script chỉ thực hiện một mutation tại cuối luồng:

```lua
-- KEYS[1]: inventory key chứa số nguyên không âm
-- ARGV[1]: số lượng cần trừ, chuỗi số nguyên dương

local rawQuantity = ARGV[1]
if not rawQuantity or not string.match(rawQuantity, '^[0-9]+$') then
    return -1
end

local quantity = tonumber(rawQuantity)
if not quantity or quantity <= 0 or quantity > 1000000 then
    return -1
end

local stockRaw = redis.call('GET', KEYS[1])
if not stockRaw then
    return -2
end

local stock = tonumber(stockRaw)
if not stock or stock < 0 or stock ~= math.floor(stock) then
    return -3
end

if stock < quantity then
    return 0
end

redis.call('DECRBY', KEYS[1], rawQuantity)
return 1
```

Quy ước kết quả:

| Mã | Ý nghĩa |
|---:|---|
| `1` | Đã trừ tồn kho |
| `0` | Không đủ hàng, không ghi |
| `-1` | Số lượng yêu cầu không hợp lệ |
| `-2` | Chưa có khóa tồn kho |
| `-3` | Giá trị tồn kho không hợp lệ |

Lưu Lua trong `src/main/resources/redis/reserve-stock.lua` và tạo bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class ReactiveRedisScripts {

    @Bean
    public RedisScript<Long> reserveStockScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setLocation(
                new ClassPathResource("redis/reserve-stock.lua"));
        script.setResultType(Long.class);
        return script;
    }
}
```

`Long.class` được chọn vì script trả mã nguyên dạng số. Không thể dùng cùng kiểu kết quả cho mọi script: Lua có thể trả chuỗi, số, danh sách hoặc error reply; serializer và mapping cần phù hợp.

### 7.2. Service sử dụng ReactiveStringRedisTemplate

```java
import java.util.List;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveStockService {

    private final ReactiveStringRedisTemplate redis;
    private final RedisScript<Long> reserveStockScript;

    public ReactiveStockService(
            ReactiveStringRedisTemplate redis,
            RedisScript<Long> reserveStockScript) {
        this.redis = redis;
        this.reserveStockScript = reserveStockScript;
    }

    public Mono<ReserveResult> reserve(String sku, long quantity) {
        if (quantity <= 0 || quantity > 1_000_000L) {
            return Mono.error(new IllegalArgumentException(
                    "Quantity must be between 1 and 1,000,000"));
        }

        String key = "inventory:{" + sku + "}:available";

        return redis.execute(
                        reserveStockScript,
                        List.of(key),
                        Long.toString(quantity))
                .next()
                .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                                "Redis script returned no result")))
                .map(this::mapResult);
    }

    private ReserveResult mapResult(Long code) {
        return switch (code.intValue()) {
            case 1 -> ReserveResult.RESERVED;
            case 0 -> ReserveResult.INSUFFICIENT_STOCK;
            case -1 -> ReserveResult.INVALID_QUANTITY;
            case -2 -> ReserveResult.STOCK_NOT_FOUND;
            case -3 -> ReserveResult.INVALID_STOCK_VALUE;
            default -> throw new IllegalStateException(
                    "Unexpected script result: " + code);
        };
    }

    public enum ReserveResult {
        RESERVED,
        INSUFFICIENT_STOCK,
        INVALID_QUANTITY,
        STOCK_NOT_FOUND,
        INVALID_STOCK_VALUE
    }
}
```

Trong ví dụ, lời gọi reactive script executor được dùng như publisher; `.next()` chuyển phản hồi đầu tiên sang `Mono<Long>` vì script này dự kiến trả **một mã kết quả**. Nếu dự án sử dụng overload/return shape khác ở phiên bản Spring Data Redis cụ thể, cần theo đúng hợp đồng API tương ứng thay vì ép một cách dùng không tương thích.

### 7.3. Không gọi subscribe() bên trong service để kích hoạt script

Sai:

```java
public Mono<Boolean> reserveWrong(String sku) {
    redis.execute(reserveStockScript,
            List.of("inventory:{" + sku + "}:available"),
            "1").subscribe();

    return Mono.just(true);
}
```

Caller nhận `true` trước khi biết script thành công, bị từ chối hay Redis lỗi. Lỗi script cũng có thể xuất hiện ở luồng subscription riêng không được web request quan sát.

Đúng hơn: **trả trực tiếp publisher biểu diễn kết quả của script**, map mã nghiệp vụ và truyền lỗi tới ranh giới API để xử lý.

## 8. Script cache, EVAL và EVALSHA

Redis hỗ trợ:

- `EVAL`: gửi nội dung Lua để thực thi.
- `EVALSHA`: thực thi script đã được Redis biết đến qua SHA1 của nội dung.
- `SCRIPT LOAD`: nạp script vào script cache.

Script executor của Spring Data Redis có thể tối ưu bằng SHA và có đường xử lý fallback khi script chưa có trong cache, tùy overload và phiên bản. Điều cần kiểm tra trong hệ thống thật là: **những node nào có script cache, hành vi fallback khi `NOSCRIPT` và các tình huống failover**.

`NOSCRIPT` có nghĩa server/node được hỏi không có script tương ứng trong cache vào thời điểm gọi. Đây là một tình huống khác với **script đã chạy rồi lỗi sau mutation**.

Ví dụ thứ tự:

```text
Client gửi EVALSHA
         |
         v
Redis trả NOSCRIPT
         |
         v
Script executor nạp/gửi lại script theo cơ chế phù hợp
         |
         v
Redis thực thi và trả kết quả
```

Không xử lý mọi exception từ reactive script như một lỗi `NOSCRIPT` có thể retry ngay. Với timeout hoặc mất kết nối trong lúc `EVAL` chạy, client có thể **không biết script đã thực thi thành công hay chưa**.

**Không viết lại việc chạy script bằng `retry()` vô điều kiện nếu script có side effect không idempotent.** Ví dụ `DECRBY` có thể thực hiện hai lần khi lần đầu thành công nhưng phản hồi bị mất.

## 9. Tính nguyên tử của script và giới hạn rollback

Một lỗi rất phổ biến là suy luận “Lua script atomic” thành “nếu bất kỳ lệnh nào lỗi, mọi ghi bị hoàn tác”.

Xét script:

```lua
redis.call('INCR', KEYS[1])
redis.call('HSET', KEYS[2], 'state', 'READY')
return 1
```

Nếu `KEYS[2]` đang là Redis String, `HSET` có thể lỗi `WRONGTYPE`. Lệnh `INCR` trước đó đã thành công **không tự được rollback**.

```text
INCR count-key        -> thành công, count đã tăng
HSET wrongtype-key    -> lỗi
Script kết thúc lỗi   -> count vẫn có thể đã tăng
```

Để giảm rủi ro:

1. Validate `ARGV` trước mutation.
2. Đọc/kiểm tra key types trước những lệnh ghi có thể lỗi.
3. Kiểm tra điều kiện nghiệp vụ khi dữ liệu còn nguyên.
4. Giảm số mutation, ưu tiên một Redis command nếu đủ.
5. Sử dụng request ID và idempotency khi workflow có retry.
6. Nếu có nhiều bước ghi quan trọng, thiết kế cơ chế đối soát/trạng thái phục hồi.

`redis.pcall(...)` bắt lỗi command để Lua có thể tiếp tục xử lý; nó **không tạo savepoint và không rollback những ghi trước đó**. `redis.error_reply(...)` cũng không phải lệnh rollback.

Script nên ngắn, hữu hạn, không thực hiện vòng lặp lớn chặn Redis. Độ trễ script dài trên một primary ảnh hưởng cả những client khác cùng dùng node đó, dù phía Java gọi script qua một `Mono` non-blocking.

## 10. Cảnh báo về số nguyên và serialize trong Lua

Lua trong Redis và Java không nhất thiết biểu diễn mọi số nguyên theo cùng một cách ở phần tính toán. Không nên tùy tiện dùng `tonumber` cho các định danh hoặc số tiền nguyên 64-bit rất lớn rồi giả định không mất độ chính xác.

Trong ví dụ trừ tồn kho:

- Quantity bị giới hạn tối đa 1.000.000.
- Java gửi `Long.toString(quantity)`.
- Lua kiểm tra chuỗi chỉ gồm chữ số trước khi dùng `tonumber`.
- Inventory value được kiểm tra thuộc miền hợp lệ trước thao tác.

Đối với nghiệp vụ tài chính, hãy xác định miền số nguyên, tiền tệ và đơn vị nhỏ nhất, đồng thời đặt giới hạn chính xác. Cần cẩn trọng với chuỗi số ngoài miền Redis integer hoặc phép toán có thể overflow.

Về serialization:

```text
ReactiveStringRedisTemplate
    key serializer: string
    value serializer: string

ReactiveRedisTemplate<K, V> tùy chỉnh
    key/value/hash serializers theo cấu hình
```

Nếu một ứng dụng ghi giá trị với JDK serializer nhưng script lại gọi `GET` rồi `tonumber`, Lua sẽ không nhận một string số nguyên có thể chuyển đổi như dự kiến. Script cần hợp đồng representation tại Redis, không chỉ hợp đồng kiểu Java.

## 11. Topology 1: Redis Standalone

Standalone là mô hình dễ hiểu nhất:

```text
WebFlux application
        |
        v
Lettuce Reactive Connection
        |
        v
Redis primary (standalone)
        |
        +-- GET/SET
        +-- EVAL/EVALSHA
        +-- MULTI/EXEC theo mức hỗ trợ API/driver
```

Với một Redis server:

- Một lệnh Redis được xử lý trên instance đó.
- Lua script không bị command khác chen giữa khi đang thực thi.
- Các khóa đều được server quản lý, không gặp điều kiện cross-slot như Redis Cluster.
- Nếu Redis server chết hoặc kết nối mất, thao tác đang thực hiện có thể có kết quả không xác định từ phía client.
- Tính bền dữ liệu phụ thuộc RDB/AOF và cấu hình persistence; reactive API không làm thay đổi bảo đảm độ bền của server.

Ví dụ cấu hình Spring Boot:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

Không dùng cấu hình localhost làm cấu hình production nếu Redis thực tế ở cluster/cloud. Trong production, cần timeout, TLS, ACL/credential và health check phù hợp.

## 12. Topology 2: Sentinel và failover

Redis Sentinel theo dõi master/replica và hỗ trợ xác định primary hiện hành khi có failover. Reactive app có thể kết nối qua Lettuce cấu hình Sentinel phù hợp.

```text
       Reactive application
                 |
          Sentinel discovery
                 |
                 v
            Current primary
                 |
              replica(s)

Primary cũ lỗi
      |
      v
Sentinel chọn primary mới
      |
      v
Driver reconnect / cập nhật kết nối
```

Điều cần phân biệt:

1. **Có thể tự kết nối lại** không đồng nghĩa các command ở thời điểm failover được replay an toàn.
2. Một lệnh ghi hoặc script có thể đã chạy trên primary cũ nhưng phản hồi không tới client.
3. Một thay đổi đã được primary cũ xác nhận có thể chưa được replica nhận đầy đủ trước failover, tùy replication và chính sách độ bền.
4. Script cache tại primary mới có thể khác với primary cũ; cần xử lý `NOSCRIPT` theo cơ chế tương ứng.
5. Replica read có thể trả dữ liệu cũ so với primary.

Ví dụ cấu hình Sentinel:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: redis-primary
        nodes:
          - sentinel-1:26379
          - sentinel-2:26379
          - sentinel-3:26379
```

Đây là cấu hình minh họa hình dạng properties. Triển khai thực tế cần host có thật, bảo mật/TLS của Redis và Sentinel, version Spring Boot tương thích và chính sách kết nối phù hợp.

### 12.1. Không retry mù sau failover

Giả sử script trừ tồn kho chạy thành công nhưng connection bị reset trước khi trả mã `1`. Nếu WebFlux tự `retry(3)` lời gọi script, tồn kho có thể bị trừ nhiều lần.

Hệ thống nên gắn **operation ID** vào yêu cầu và thiết kế idempotency ở nơi có thể kiểm tra nguyên tử. Khi outcome không rõ, thực hiện read-after-recovery/đối soát theo quy tắc nghiệp vụ thay vì coi mọi timeout là “chưa thực thi”.

## 13. Topology 3: Redis Cluster và hash slot

Redis Cluster phân bổ khóa theo hash slot trên nhiều primary:

```text
Reactive application
        |
        v
Lettuce Cluster Client
        |
        +-- Slot group A -> Primary A
        +-- Slot group B -> Primary B
        +-- Slot group C -> Primary C
```

Lettuce có thể định tuyến các lệnh theo key và xử lý các phản hồi chuyển hướng như `MOVED`/`ASK` theo khả năng driver. Nhưng một script nhiều khóa **không trở thành distributed transaction trên nhiều primary**.

### 13.1. Script nhiều khóa phải tương thích slot

Ví dụ hệ thống muốn trừ tồn kho và ghi dấu request:

```text
inventory:sku-1:available
inventory:sku-1:processed
```

Hai khóa này không nhất thiết nằm cùng hash slot. Trên Redis Cluster, script hoặc multi-key operation có thể bị từ chối vì `CROSSSLOT` hoặc điều kiện key access tương ứng.

Sử dụng hash tag:

```text
inventory:{sku-1}:available
inventory:{sku-1}:processed
```

Hai khóa chia sẻ phần `{sku-1}` và vì vậy được ánh xạ vào cùng hash slot.

Ví dụ gọi:

```java
String stockKey = "inventory:{" + sku + "}:available";
String dedupKey = "inventory:{" + sku + "}:processed";

return reactiveRedisTemplate.execute(
        script,
        List.of(stockKey, dedupKey),
        requestId,
        Long.toString(quantity));
```

Script phải sử dụng các khóa khai báo qua `KEYS[1]` và `KEYS[2]`. Không nên tự ghép ra các tên khóa bổ sung khó kiểm soát bên trong script rồi kỳ vọng Redis Cluster có thể định tuyến chúng đến node bất kỳ.

### 13.2. Hash tag không được dùng một cách cực đoan

Không đặt mọi khóa trong ứng dụng vào một hash tag chung như `{all}` chỉ để mọi script nhiều khóa chạy được. Việc này có thể dồn tải của toàn hệ thống vào một slot/primary, giảm khả năng phân tán của cluster.

Hash tag nên phản ánh ranh giới aggregate hoặc đơn vị nhất quán cần xử lý cùng nhau, ví dụ một đơn hàng hoặc một SKU.

### 13.3. Cluster không bảo đảm thứ tự toàn cục

Hai lệnh trên hai primary khác nhau không có một thứ tự thực thi nguyên tử xuyên cluster chỉ vì chúng nằm trong cùng reactive flow:

```java
return redis.opsForValue().set(keyOnSlotA, "A")
        .then(redis.opsForValue().set(keyOnSlotB, "B"))
        .then();
```

Đây là thứ tự điều phối phía client; không có rollback xuyên primary. Nếu nghiệp vụ yêu cầu cả hai cập nhật cùng thành công hoặc cùng thất bại, phải xem lại ranh giới dữ liệu và hệ thống transaction phù hợp.

### 13.4. Ví dụ cấu hình Cluster

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
```

Danh sách node là các điểm khởi tạo kết nối (seed nodes). Định tuyến thực tế phụ thuộc topology mà driver khám phá được; các nút phải có địa chỉ quảng bá mà client có thể truy cập, nhất là trong môi trường container, Kubernetes hoặc mạng riêng.

Đừng chỉ kiểm tra `PING` một node rồi kết luận app đã cấu hình Cluster chính xác. Cần thử các key thuộc nhiều slot và script nhiều key có hash tag.

## 14. Topology 4: replica reads và eventual consistency

Một số hệ thống cấu hình Lettuce ưu tiên đọc từ replica để giảm tải primary. Việc sử dụng replica có thể làm tăng độ trễ nhìn thấy bản mới do replication không đồng bộ.

```text
Reactive client
     |
     +---- SET value ---> Primary
     |                        |
     |                 replicate async
     |                        |
     +---- GET value ---> Replica (có thể còn bản cũ)
```

Ví dụ:

```java
redis.opsForValue()
        .set("order:1001:state", "PAID")
        .then(redis.opsForValue()
                .get("order:1001:state"));
```

Dù hai publisher được nối tuần tự bằng `then`, nếu đường `GET` được định tuyến tới replica chưa cập nhật, giá trị đọc có thể chưa phản ánh lệnh `SET` vừa ghi. **Reactive sequencing không tạo read-your-writes consistency qua một replica bất đồng bộ.**

Nếu một script vừa cập nhật tồn kho, việc đọc từ replica ngay sau đó không phải cách chắc chắn để xác nhận giá trị mới. Với những quyết định cần độ mới nghiêm ngặt, hãy đọc từ primary hoặc dùng kết quả script/command theo hợp đồng phù hợp.

### 14.1. Cấu hình read preference là quyết định kiến trúc

Lettuce cung cấp các lựa chọn read preference, ví dụ ưu tiên replica trong một số topology. Cấu hình phải khớp mô hình master/replica hoặc cluster và khả năng discovery; chỉ đặt một flag read preference khi kết nối standalone không bảo đảm client tìm được replica đúng như mong đợi.

Cần xác định rõ:

- Read path nào được phép stale?
- Tối đa chấp nhận replica lag bao lâu?
- Fallback khi replica không sẵn sàng là gì?
- Đường nào bắt buộc đọc primary?
- Khi failover, driver cập nhật topology trong bao lâu?
- Đường scripting ghi có được gửi tới primary đúng slot không?

**Không định tuyến write script tới replica chỉ vì ứng dụng đang dùng read preference ưu tiên replica.** Khả năng định tuyến từng loại command phụ thuộc driver/server; kiểm tra rõ trong môi trường triển khai.

## 15. Một script nhiều key và ranh giới consistency

Giả sử hệ thống cần:

1. Kiểm tra `inventory:{sku-1}:available`.
2. Nếu còn đủ, giảm tồn kho.
3. Ghi `requestId` vào `inventory:{sku-1}:processed`.

Một script có thể thực thi các thao tác liên quan trên cùng primary khi cả hai key thuộc cùng hash slot. Nhưng vì có **nhiều mutation**, nếu mutation đầu thành công rồi mutation sau lỗi runtime, Redis không tự rollback mutation đầu.

Khi sử dụng hai khóa:

```text
inventory:{sku-1}:available  -> String
inventory:{sku-1}:processed  -> Set
```

Script nên:

- Kiểm tra quantity hợp lệ, nằm trong miền số nguyên an toàn.
- Kiểm tra kiểu tồn kho và kiểu Set trước mutation.
- Kiểm tra `requestId` đã được ghi nhận chưa.
- Kiểm tra số lượng còn đủ.
- Chỉ sau đó mới thực hiện thay đổi.
- Trả mã kết quả rõ ràng cho success, insufficient, duplicate và invalid data.
- Có phương án đối soát nếu bất kỳ lỗi runtime/timeout xảy ra sau mutation.

Điều này cho thấy **topology và lỗi script không phải hai chủ đề tách biệt**: một thiết kế chỉ chạy được khi các key cùng slot và cần xử lý lỗi ở mức dữ liệu/nghiệp vụ, không chỉ biết cách gọi API.

## 16. Tương tác của Reactive Redis với transaction database

Một API có thể cần:

```text
HTTP POST /orders/{id}/pay
        |
        v
R2DBC: cập nhật order thành PAID
        |
        v
Reactive Redis: xóa cache hoặc gửi notification
```

Nếu dùng:

```java
@Transactional
public Mono<Void> markPaid(String id) {
    return orderRepository.markPaid(id)
            .then(redis.delete("cache:order:" + id))
            .then();
}
```

phải xem đây là **hai tài nguyên có ranh giới riêng**, không phải một distributed transaction tự động. Database commit thành công nhưng Redis lỗi vẫn có thể khiến cache cũ tồn tại. Ngược lại, gọi Redis trước DB commit có thể làm cache thay đổi dù transaction database rollback.

Các mẫu kiến trúc thường phù hợp hơn:

- Để database là nguồn sự thật.
- Sau commit phát outbox event/CDC, consumer cập nhật Redis.
- Dùng TTL như giới hạn độ cũ nếu event invalidation bị bỏ lỡ.
- Dùng version trên cache value nếu nhiều writer có thể ghi lệch thứ tự.
- Dùng idempotency cho những tác động cần retry.
- Với dữ liệu không được phép stale, đọc lại nguồn authoritative trước quyết định cuối.

Scripting chỉ bảo vệ thao tác **bên trong Redis**, không bao bọc commit của R2DBC hay các dịch vụ ngoài Redis.

## 17. Tại sao không block() trên event loop?

Một cách “vá” khi thiếu API reactive transaction là gọi:

```java
public Mono<Void> updateWrong(String id) {
    String result = imperativeRedisTemplate.opsForValue()
            .get("order:" + id);
    // Hoặc gọi .block() để chờ lệnh Redis reactive.
    return Mono.empty();
}
```

Lời gọi đồng bộ chiếm thread đang xử lý; nếu nó chạy trên Reactor Netty event loop, nó có thể cản những request khác và gây độ trễ hệ thống. `block()` trực tiếp trong non-blocking execution context cũng không phải cách xử lý hợp lệ.

Nếu bắt buộc dùng một adapter imperative cho transaction Redis:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<TransactionResult> executeLegacyTransaction(String orderId) {
    return Mono.fromCallable(
            () -> imperativeService.updateWithSessionCallback(orderId))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Trong đó `imperativeService.updateWithSessionCallback(...)` là phương thức blocking do ứng dụng định nghĩa, và `TransactionResult` là kiểu trả về của ứng dụng.

Cách này chỉ **cách ly blocking work ra khỏi event-loop thread**; không biến transaction Redis thành reactive. Phải giới hạn lượng công việc được gửi vào scheduler, thời gian chờ kết nối và số connection/blocking thread đang dùng. Nếu tải lớn hoặc đường xử lý bắt buộc non-blocking end-to-end, hãy xem lại thiết kế hoặc dùng Lua/lệnh Redis phù hợp.

## 18. Hành vi lỗi của reactive flow

Trong Reactor, lỗi Redis thường được truyền qua tín hiệu `onError`. Có thể dùng `onErrorMap`, `timeout` và retry policy, nhưng phải hiểu ý nghĩa của side effect.

Ví dụ:

```java
return redis.execute(
                reserveStockScript,
                List.of(key),
                Long.toString(quantity))
        .next()
        .timeout(Duration.ofSeconds(2))
        .onErrorMap(
                error -> new StockCacheUnavailableException(
                        "Redis operation could not be confirmed", error));
```

Đây là cách báo lỗi rõ ràng; không trả `false` tùy tiện như thể Redis chắc chắn chưa thay đổi dữ liệu.

### 18.1. Client timeout không có nghĩa server hủy lệnh

```text
T0: Client gửi EVAL.
T1: Redis bắt đầu chạy script.
T2: Client timeout, hủy subscription.
T3: Redis có thể hoàn tất script và ghi dữ liệu.
T4: Client không nhận được kết quả.
```

`timeout` ở phía Reactor có thể hủy subscription phía ứng dụng; điều đó **không bảo đảm lệnh Redis đã gửi sẽ được rollback hoặc ngăn server hoàn tất**.

Nếu retry cùng script không idempotent, tác động có thể lặp. Cần một business operation ID và cơ chế nhận diện request đã áp dụng.

### 18.2. Đừng giấu lỗi ghi thành cache miss

Sai:

```java
return redis.opsForValue()
        .set("account:balance", "100")
        .onErrorReturn(false);
```

Một lỗi Redis connection được chuyển thành `false` sẽ làm mất sự khác biệt giữa “lệnh bị từ chối có chủ đích” với “không biết lệnh đã thực thi chưa”.

Với cache đọc có thể fail-open, fallback về nguồn dữ liệu có thể chấp nhận được. Với command có tác dụng phụ, fallback hoặc retry phải dựa trên hợp đồng nghiệp vụ, không dùng cùng một `onErrorResume` cho mọi đường đọc và ghi.

### 18.3. Repeat subscription có thể lặp side effect

```java
Mono<Long> increment =
        redis.opsForValue().increment("counter:orders");

return increment.retry(3);
```

Nếu lệnh `INCR` đã chạy nhưng lỗi xảy ra trước khi client nhận phản hồi, `retry(3)` có thể gửi thêm lần tăng. Retry nên được xem như một quyết định business, không chỉ tối ưu mạng.

## 19. Kiểm tra topology trước khi gọi script

Các bước kiểm tra trong môi trường triển khai thường là:

1. Xác định Spring Boot, Spring Data Redis và Lettuce đang thực sự được nạp.
2. Xác nhận `ReactiveRedisConnectionFactory` hoạt động và trỏ tới topology mong muốn.
3. Thử lệnh một-key như `SET`/`GET` qua reactive template.
4. Thử Lua đơn-key và kiểu trả về.
5. Với Redis Cluster, kiểm tra hash slot của mọi key trong script nhiều key.
6. Thử script trên những slot khác nhau để xác nhận định tuyến theo key.
7. Nếu có replica reads, xác định đường đọc nào có thể stale.
8. Thử failover/reconnect trong môi trường kiểm soát.
9. Phân biệt timeout, lỗi script, `NOSCRIPT` và lỗi cross-slot.
10. Kiểm tra client không dùng `block()` trên event loop.

Có thể tra slot của những khóa trên Redis Cluster bằng CLI:

```bash
redis-cli -c -h redis-node-1 -p 6379 \
  CLUSTER KEYSLOT 'inventory:{sku-1}:available'

redis-cli -c -h redis-node-1 -p 6379 \
  CLUSTER KEYSLOT 'inventory:{sku-1}:processed'
```

Hai kết quả phải tương ứng cùng slot nếu script cần truy cập cả hai khóa. `CLUSTER KEYSLOT` là lệnh cho môi trường cluster; không coi lỗi trên standalone là bằng chứng hệ thống không hỗ trợ reactive scripting.

### 19.1. Không lấy PING làm chứng cứ đủ

`PING` chỉ kiểm tra một phần khả năng kết nối. Một ứng dụng có thể PING thành công nhưng:

- Không có quyền ACL chạy `EVAL`.
- Không có quyền với key prefix cần dùng.
- Định tuyến script multi-key bị cross-slot.
- Replica read không đáp ứng freshness.
- Không xử lý được `NOSCRIPT` sau failover.
- Không có cơ chế transaction reactive đúng như nghiệp vụ yêu cầu.

Vì vậy, một bài kiểm tra hỗ trợ phải dùng **đúng nhóm thao tác** mà ứng dụng dự định triển khai.

## 20. Ma trận kiểm thử gợi ý cho reactive Redis

Khi thiết kế hệ thống, có thể chạy thử các tình huống sau trong môi trường kiểm soát để xác nhận hợp đồng API và hạ tầng:

| Tình huống | Điều cần xác minh |
|---|---|
| Không có subscription | Lệnh write chưa tự chạy theo cách ứng dụng dự đoán |
| Subscribe lại publisher có side effect | Lệnh có thể chạy nhiều lần; không xem publisher như kết quả ghi nhớ |
| `then` giữa hai lệnh ghi | Có thứ tự subscription/completion, không có rollback giữa hai lệnh |
| Lua script kiểm tra rồi ghi | Không bị client khác chen giữa tại Redis primary |
| Lua lỗi sau mutation | Ghi trước lỗi vẫn có thể tồn tại |
| `EVALSHA` gặp `NOSCRIPT` | Executor/driver có cơ chế xử lý theo phiên bản đã chọn |
| Lua multi-key cùng hash tag | Script được định tuyến trên slot phù hợp |
| Lua multi-key khác slot | Lỗi được báo rõ, không bị che thành thành công |
| Replica read ngay sau ghi primary | Có thể thấy dữ liệu stale theo cấu hình đọc |
| Failover giữa lệnh ghi/script | Client có thể không biết chắc kết quả, retry phải an toàn |
| Redis unavailable | WebFlux không block event loop và lỗi được phát qua publisher |
| Retry một `INCR` | Không tự ý chấp nhận side effect lặp |
| Database commit rồi Redis write lỗi | Có phương án invalidation/reconcile |
| Nhiều instance cùng gọi script | Kết quả cuối tuân thủ bất biến server-side theo thiết kế |

**Ví dụ dùng StepVerifier cho service script** (giả sử đã chuẩn bị dữ liệu Redis thử nghiệm và bean như mục 7):

```java
import reactor.test.StepVerifier;

StepVerifier.create(stockService.reserve("sku-1", 2))
        .expectNext(ReactiveStockService.ReserveResult.RESERVED)
        .verifyComplete();
```

`StepVerifier` là tiện ích kiểm thử của Reactor, không tự chứng minh đúng concurrency hay topology. Đối với script nhiều client, phải thử tương tranh thật; đối với cluster, phải chạy trên môi trường có cluster phù hợp.

## 21. Theo dõi vận hành reactive Redis

Các chỉ số nên quan sát đồng thời ở ba lớp:

### 21.1. Ứng dụng Reactor

- Latency p50/p95/p99 của API đọc/ghi Redis.
- Timeout, cancel, retry và số lần subscription khi có side effect.
- Số request đang chờ, concurrency của load path.
- Tỷ lệ fallback khi Redis không sẵn sàng.
- Độ trễ kết thúc business operation, không chỉ thời điểm publisher được tạo.

### 21.2. Lettuce/connection factory

- Thời gian kết nối và reconnect.
- Connection failures, redirects và node topology changes.
- Command timeout và số lệnh bị retry.
- Sự thay đổi địa chỉ primary khi Sentinel/Cluster failover.
- Read preference và tỷ lệ đọc từ replica khi cấu hình có hỗ trợ.

### 21.3. Redis server

```bash
redis-cli INFO commandstats
redis-cli INFO stats
redis-cli INFO memory
redis-cli SLOWLOG GET 10
```

`INFO commandstats` giúp quan sát các loại lệnh như `EVAL`/`EVALSHA` ở phạm vi instance; `SLOWLOG` chỉ ghi những command vượt ngưỡng thời gian xử lý phía Redis, không bao gồm toàn bộ thời gian mạng hoặc chờ scheduler. Trên Cluster, chỉ nhìn một node không phản ánh mọi shard.

Đối với script chạy lâu, cần giám sát tác động lên các command khác cùng primary. Scripting có thể tránh client round-trip nhưng **một script phức tạp chặn Redis lâu** sẽ khiến độ trễ của toàn node tăng.

Không đưa dữ liệu nhạy cảm vào log script `ARGV`, key hoặc payload theo cách không kiểm soát. Khi lỗi, đủ để ghi loại thao tác, script version, key namespace, mã outcome và correlation ID đã được thiết kế an toàn.

## 22. Những sai lầm dễ gặp

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Coi `Mono.then` là Redis transaction | Ghi một phần khi lệnh sau lỗi | Dùng lệnh nguyên tử/Lua hoặc transaction đúng phạm vi |
| Đặt `@Transactional` rồi tin Redis reactive tự tham gia | Không có atomic commit qua Redis và database | Xác định resource manager và kiến trúc outbox |
| Gọi `subscribe()` trong service rồi trả success | Caller không chờ kết quả thực, lỗi thất lạc | Trả publisher chứa command |
| Gọi `block()` trên event loop | Cản request khác, tăng latency | Giữ non-blocking hoặc tách adapter blocking |
| Dùng `retry()` vô điều kiện cho `INCR`/script ghi | Có thể áp dụng side effect hai lần | Idempotency và phân biệt outcome bất định |
| Hiểu “Lua atomic” là rollback mọi lệnh | Ghi trước lỗi vẫn có hiệu lực | Validate trước mutation, đối soát |
| Đặt khóa Lua ở nhiều slot trên Cluster | Cross-slot hoặc route error | Hash tag theo aggregate |
| Đọc replica ngay sau ghi rồi xem là chắc chắn mới | Có thể đọc bản cũ | Primary read hoặc cơ chế nhất quán phù hợp |
| Tin Redis failover sẽ replay command chính xác một lần | Có thể lặp hoặc thiếu ghi | Retry có hợp đồng và version/idempotency |
| Sử dụng serializer không khớp Lua | Script đọc byte format không mong đợi | Chốt representation giữa Java và Redis |
| Coi `PING` đủ để xác nhận feature support | Chưa kiểm tra transaction/script/topology | Thử đúng thao tác cần thiết |
| Chỉ đo độ trễ app mà không đo primary | Script dài làm chậm các client khác | Theo dõi Redis command latency, SLOWLOG |
| Không version hóa script và schema dữ liệu | App cũ/mới có thể xử lý khác nhau | Quản lý version và quá trình migration |
| Coi một script multi-key là transaction toàn cluster | Không có atomicity xuyên nhiều master | Gom key cùng slot hoặc thiết kế khác |

## 23. Cây quyết định khi chọn API reactive

```text
Nghiệp vụ cần thao tác Redis?
              |
              v
Có thể dùng một lệnh Redis nguyên tử?
         +----+----+
         |         |
        Có        Không
         |         |
         v         v
     Reactive    Cần kiểm tra rồi
     operation   cập nhật có điều kiện?
                      |
                 +----+----+
                 |         |
                Có        Không
                 |         |
                 v         v
           Cân nhắc Lua   Nhiều lệnh độc lập
                 |             |
                 |             v
                 |        Reactor chaining
                 |        (không atomic)
                 |
                 v
           Script cần nhiều key?
                 |
            +----+----+
            |         |
           Có        Không
            |         |
            v         |
       Cluster?       |
         |            |
         v            |
       Cùng hash slot?
         |            |
         +-----+------+
               |
               v
       Kiểm tra serializer, Lua result,
       lỗi sau mutation và idempotency
               |
               v
       Có Replica/Sentinel/Cluster?
               |
               v
       Kiểm tra routing, consistency,
       failover, retry và topology
               |
               v
       Có database khác trong flow?
               |
               v
       Xác định ranh giới giao dịch,
       nguồn sự thật và khôi phục
```

## 24. Tổng kết

Kiểm tra hỗ trợ **giao dịch, scripting và topology của API phản ứng** trong Spring Data Redis cần bắt đầu từ các bảo đảm thực, không phải tên phương thức.

- **Reactive chaining** (`then`, `flatMap`, `when`) tổ chức cách publisher được thực thi; nó **không tự tạo Redis transaction**.
- **Spring transaction** của database reactive không mặc nhiên quản lý Redis. Nếu cần `MULTI`/`EXEC`, phải kiểm tra cơ chế transaction và connection của phiên bản API/driver đang dùng hoặc chọn adapter phù hợp.
- **Lua scripting** là lựa chọn hữu ích để kiểm tra và cập nhật tại server trong một lời gọi reactive; tuy vậy script **không rollback những ghi đã thực hiện trước lỗi runtime**.
- **Standalone, Sentinel, Redis Cluster và replica reads** có khả năng, giới hạn và rủi ro khác nhau. Cluster yêu cầu thiết kế hash slot phù hợp cho script nhiều khóa; replica có thể trả dữ liệu cũ; failover tạo các kết quả không xác định từ phía client.
- **Retry và subscription** trong Reactor phải gắn với idempotency và hợp đồng nghiệp vụ, nhất là với các lệnh có tác dụng phụ.

Một thiết kế reactive đáng tin cậy phải xác nhận đồng thời: **đúng API, đúng connection/driver, đúng Redis topology, đúng ranh giới atomicity và đúng chiến lược phục hồi khi lỗi**. Khả năng non-blocking giúp tiết kiệm tài nguyên phía ứng dụng; nó không thay thế các nguyên tắc nhất quán dữ liệu của Redis và những hệ thống liên quan.

