# Khóa phân tán bằng SET có điều kiện và thời hạn thuê

Trong hệ thống Spring Boot có nhiều instance, một số công việc chỉ nên được **một instance thực hiện tại một thời điểm**: chạy tác vụ tổng hợp theo lịch, đồng bộ một lô hàng, khởi tạo tài nguyên đắt đỏ hay hạn chế nhiều worker cùng nạp một cache key. Các khóa Java như `synchronized` và `ReentrantLock` chỉ bảo vệ những thread **trong cùng một JVM**, không ngăn được pod A và pod B xử lý đồng thời.

Một mẫu ứng dụng thông dụng trong Spring Data Redis là tạo **khóa phân tán có thời hạn thuê (lease)** bằng một lệnh Redis: `SET key token NX PX ttl`. `NX` bảo đảm chỉ tạo khóa nếu key chưa tồn tại; `PX` gắn thời hạn tồn tại ngay trong chính lệnh tạo key. Worker lấy được khóa sẽ nhận một **owner token** duy nhất cho lượt sở hữu đó. Khi xử lý xong, worker chỉ được xóa khóa nếu token trong Redis vẫn khớp.

Mẫu này giúp giảm xử lý trùng và tránh khóa tồn tại vĩnh viễn khi process chết. Tuy nhiên, **lease hết hạn không ngăn worker cũ tiếp tục chạy**; Redis failover với replication bất đồng bộ cũng có những rủi ro riêng. Bài học vì thế giải thích cả cách triển khai lẫn ranh giới an toàn khi khóa bảo vệ side effect quan trọng.

## 1. Vì sao cần khóa phân tán?

Giả sử ba instance cùng nhận tín hiệu “đồng bộ tồn kho SKU-42”:

~~~text
                           Scheduler / Event
                                 |
                 +---------------+---------------+
                 |               |               |
                 v               v               v
              App A            App B            App C
                 |               |               |
                 +---------------+---------------+
                                 |
                                 v
                         inventory:SKU-42
                                 |
                                 v
                   Có thể ghi hoặc gửi API trùng
~~~

Nếu dùng một Redis lock key có tên ổn định theo tài nguyên, ví dụ `lock:inventory:SKU-42`:

~~~text
App A: SET lock:inventory:SKU-42 token-A NX PX 30000 → OK
App B: SET lock:inventory:SKU-42 token-B NX PX 30000 → nil
App C: SET lock:inventory:SKU-42 token-C NX PX 30000 → nil

App A bắt đầu xử lý.
App B/C bỏ qua, đợi có giới hạn hoặc xếp lại công việc.
~~~

Điểm quan trọng là **key khóa phải đại diện cho cùng một tài nguyên** ở mọi instance. Nếu mỗi request tự sinh một tên khóa hoàn toàn mới thì không có sự cạnh tranh, nên khóa không còn tác dụng đồng bộ.

## 2. Những tính chất cần phân biệt

| Tính chất | Mong muốn | Khóa Redis có lease hỗ trợ đến đâu? |
| --- | --- | --- |
| Mutual exclusion | Trên cùng một primary, một key đang tồn tại chỉ có một người tạo mới thành công bằng `NX` | Có trong phạm vi một Redis primary xử lý lệnh nguyên tử |
| Liveness | Worker chết không giữ khóa mãi | TTL tự làm key hết hạn |
| Ownership | Worker cũ không xóa nhầm khóa mới | Token duy nhất và giải phóng có so sánh nguyên tử |
| Bounded wait | Không chờ vô hạn khi khóa bận | Cần deadline/backoff ở ứng dụng |
| Atomic side effect | Cập nhật database hoặc API bên ngoài không bị nhân đôi | **Không được bảo đảm chỉ bởi Redis lease** |
| Failover safety | Không tồn tại hai worker cùng tin rằng chúng đã lấy khóa qua các đời primary | Có rủi ro với replication bất đồng bộ |

Không nên lấy một khóa “thường chạy đúng trong thử nghiệm” làm bằng chứng rằng nghiệp vụ quan trọng luôn đúng trong mọi trường hợp pause, network partition, failover hoặc timeout.

## 3. Lệnh chuẩn: `SET key token NX PX ttl`

Ví dụ Redis CLI:

~~~redis
SET lock:report:monthly "76d4c7f4-f0a1-4c48-b67a-bc7f6a1b0a61" NX PX 30000
~~~

Các thành phần:

- `lock:report:monthly`: tên key khóa theo công việc.
- Chuỗi UUID: token duy nhất cho lần acquire này.
- `NX`: chỉ ghi khi key **chưa tồn tại**.
- `PX 30000`: gắn TTL 30.000 mili giây (30 giây).
- Phản hồi `OK`: worker đã tạo khóa.
- Phản hồi nil: khóa đang tồn tại, worker **không có quyền** xử lý.

Có thể dùng `EX 30` thay cho `PX 30000` khi phù hợp với độ phân giải giây:

~~~redis
SET lock:report:monthly "another-token" NX EX 30
~~~

Nếu cùng key vẫn còn lease từ lần acquire trước, lệnh thứ hai không thành công. Để xem tình trạng phục vụ chẩn đoán:

~~~redis
GET lock:report:monthly
PTTL lock:report:monthly
~~~

`PTTL` trả thời gian còn lại theo mili giây; `-1` nghĩa là key tồn tại **không có TTL**, còn `-2` nghĩa là key không còn tồn tại. Giá trị này là một snapshot; nó không phải bằng chứng khóa sẽ tiếp tục thuộc về worker sau đó.

### Vì sao phải gắn TTL ngay trong SET?

Một cách làm cũ là:

~~~redis
SETNX lock:report:monthly token-A
EXPIRE lock:report:monthly 30
~~~

Nếu process chết giữa `SETNX` và `EXPIRE`, key có thể tồn tại vô thời hạn. Những worker khác không thể lấy khóa trừ khi có cơ chế dọn ngoài. Lệnh `SET ... NX PX ...` kết hợp **kiểm tra chưa tồn tại, tạo key và TTL** vào một thao tác Redis nguyên tử, loại bỏ khoảng lỗi giữa hai lệnh trên.

Tương tự, dùng `GET` để kiểm tra key rồi gọi `SET` không nguyên tử:

~~~text
A: GET lock:key → nil
B: GET lock:key → nil
A: SET lock:key token-A
B: SET lock:key token-B
~~~

Cả A và B đều có thể tin mình đã chiếm được tài nguyên. Điều kiện `NX` phải được Redis áp dụng **cùng lúc** với việc ghi key.

## 4. Token sở hữu khóa: vì sao không dùng giá trị cố định?

Nếu tất cả worker đều lưu `"locked"` hoặc tên pod cố định, một lượt chạy cũ không thể phân biệt khóa của mình với khóa được worker khác tạo sau khi lease trước hết hạn.

Mỗi lần lấy khóa cần sinh token mới:

~~~text
Lần acquire A-1 → token 7e0b-...-b512
Lần acquire B-1 → token 933c-...-800a
Lần acquire A-2 → token 6f1a-...-dd40
~~~

Trong Java, `UUID.randomUUID().toString()` thường phù hợp để tạo token khác nhau giữa các lượt acquire. Token **không nên** lấy bằng một giá trị không đổi như tên server, tên thread hay chỉ một user ID.

Token xác định **người sở hữu một lease**, không phải một thứ tự ưu tiên. UUID không cho biết owner nào mới hơn; khi cần ngăn worker cũ ghi đè vào tài nguyên đích sau expiry, sẽ cần cơ chế fencing hoặc version riêng.

## 5. Giải phóng khóa: so sánh token rồi xóa nguyên tử

Một lỗi nguy hiểm:

~~~text
T0      A lấy lock với token-A, TTL 10 giây
T10     Lock A hết hạn
T11     B lấy lock với token-B
T12     A xử lý xong và gọi DEL lock:key
T13     C lấy lock dù B vẫn còn đang chạy
~~~

`DEL` vô điều kiện của A đã xóa nhầm khóa của B. Muốn tránh điều đó, chỉ xóa khóa nếu token trong Redis khớp với token của lease hiện tại:

~~~text
Nếu GET(lock) == token-của-mình:
    DEL(lock)
Ngược lại:
    không xóa
~~~

Không tách `GET` rồi `DEL` thành hai lệnh, bởi khóa có thể hết hạn và được người khác lấy **giữa hai thao tác**. Dùng Lua script:

~~~lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
~~~

Chạy trực tiếp trong Redis CLI:

~~~redis
EVAL "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0" 1 lock:report:monthly token-A
~~~

Lua script chạy nguyên tử trong Redis đối với những thao tác trong script. Kết quả `1` nghĩa là đã xóa key có token phù hợp; `0` nghĩa là key vắng mặt hoặc thuộc owner khác. Đừng tự động diễn giải `0` là lỗi Redis: đó có thể là dấu hiệu một lease đã hết hạn bình thường.

## 6. Cài đặt `RedisLeaseLock` bằng Spring Data Redis

Spring Data Redis cung cấp `StringRedisTemplate.opsForValue().setIfAbsent(key, value, Duration)` để gửi `SET` có điều kiện và TTL. `DefaultRedisScript<Long>` hỗ trợ gửi Lua script so khớp token rồi xóa, hoặc gia hạn TTL an toàn.

Ví dụ dành cho Java 21 và Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

### 6.1. Toàn bộ lớp khóa

~~~java
package com.example.redis.lock;

import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

@Component
public class RedisLeaseLock {

    private static final DefaultRedisScript<Long> RELEASE =
        releaseScript();

    private static final DefaultRedisScript<Long> RENEW =
        renewScript();

    private final StringRedisTemplate redis;

    public RedisLeaseLock(StringRedisTemplate redis) {
        this.redis = Objects.requireNonNull(redis);
    }

    public record Lease(String key, String token) {
        public Lease {
            Objects.requireNonNull(key);
            Objects.requireNonNull(token);
        }
    }

    public Optional<Lease> tryAcquire(
            String resourceId, Duration ttl) {
        if (resourceId == null || resourceId.isBlank()) {
            throw new IllegalArgumentException("resourceId is required");
        }
        long millis = checkedMillis(ttl);
        String key = "lock:job:" + resourceId;
        String token = UUID.randomUUID().toString();

        Boolean acquired = redis.opsForValue().setIfAbsent(
            key, token, Duration.ofMillis(millis)
        );

        return Boolean.TRUE.equals(acquired)
            ? Optional.of(new Lease(key, token))
            : Optional.empty();
    }

    public boolean release(Lease lease) {
        Objects.requireNonNull(lease);
        Long result = redis.execute(
            RELEASE, List.of(lease.key()), lease.token()
        );
        return Long.valueOf(1L).equals(result);
    }

    public boolean renew(Lease lease, Duration ttl) {
        Objects.requireNonNull(lease);
        long millis = checkedMillis(ttl);
        Long result = redis.execute(
            RENEW, List.of(lease.key()),
            lease.token(), Long.toString(millis)
        );
        return Long.valueOf(1L).equals(result);
    }

    private static long checkedMillis(Duration ttl) {
        Objects.requireNonNull(ttl, "ttl");
        long millis = ttl.toMillis();
        if (millis <= 0) {
            throw new IllegalArgumentException(
                "Lease TTL must be at least 1 millisecond"
            );
        }
        return millis;
    }

    private static DefaultRedisScript<Long> releaseScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText("""
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end
            return 0
            """);
        script.setResultType(Long.class);
        return script;
    }

    private static DefaultRedisScript<Long> renewScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText("""
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('PEXPIRE', KEYS[1], ARGV[2])
            end
            return 0
            """);
        script.setResultType(Long.class);
        return script;
    }
}
~~~

### 6.2. Ý nghĩa các phương thức

- `tryAcquire` chọn key theo tài nguyên, sinh token UUID cho lượt acquire, rồi gọi `setIfAbsent` kèm TTL.
- `Optional.empty()` nghĩa là Redis trả kết quả không lấy được khóa; không được bắt đầu side effect trong nhánh này.
- `release` xóa key chỉ khi token đang lưu vẫn khớp, nhờ Lua script nguyên tử.
- `renew` chỉ kéo dài TTL cho **lease còn được sở hữu**, không gia hạn nhầm khóa của người đến sau.
- `checkedMillis` từ chối TTL âm, bằng không hoặc nhỏ hơn một mili giây sau khi làm tròn.
- `Long.class` tương ứng giá trị số `0` hoặc `1` do script trả về.

Lớp dùng `StringRedisTemplate` mặc định, nơi key và các đối số script được mã hóa theo string serializer. Nếu ứng dụng tùy biến serializer, phải bảo đảm token trong `SET` và token gửi tới Lua dùng cùng định dạng.

**Điểm quan trọng về kết quả không xác định:** nếu lệnh `SET NX PX` bị timeout sau khi client gửi đi, server **có thể đã tạo key** nhưng phản hồi không về tới ứng dụng. Đây không phải trường hợp “khóa bận” bình thường. Lỗi kết nối cần được log/đối soát theo khả năng và không được biến thành quyền sở hữu giả.

Hàm `tryAcquire` trên được thiết kế cho lời gọi trực tiếp, không cho kết quả lập tức bên trong Redis pipeline hoặc `MULTI`; ở các chế độ đó, một số API template có thể trả `null` khi lệnh còn đang được xếp hàng.

## 7. Sử dụng khóa trong một service

Ví dụ ba pod cùng chạy tác vụ đồng bộ tồn kho định kỳ. Một pod lấy được lease sẽ làm việc, pod còn lại bỏ qua lượt này:

~~~java
package com.example.redis.lock;

import java.time.Duration;
import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventorySyncJob {

    private static final Logger log =
        LoggerFactory.getLogger(InventorySyncJob.class);

    private final RedisLeaseLock locks;
    private final InventorySyncService inventory;

    public InventorySyncJob(
            RedisLeaseLock locks,
            InventorySyncService inventory) {
        this.locks = locks;
        this.inventory = inventory;
    }

    public void runOnce() {
        Optional<RedisLeaseLock.Lease> acquired =
            locks.tryAcquire("inventory", Duration.ofSeconds(30));

        if (acquired.isEmpty()) {
            log.info("Inventory sync already running");
            return;
        }

        RedisLeaseLock.Lease lease = acquired.get();
        try {
            inventory.synchronize();
        } finally {
            try {
                if (!locks.release(lease)) {
                    log.warn("Lease is no longer owned: {}", lease.key());
                }
            } catch (RuntimeException cleanupError) {
                log.error(
                    "Cannot confirm lease release: {}",
                    lease.key(), cleanupError
                );
            }
        }
    }
}
~~~

`InventorySyncService` là service nghiệp vụ minh họa, không phải API của Spring Data Redis. `finally` bảo đảm thử release cả khi code đồng bộ ném exception. Nếu process bị kill cứng, `finally` không chạy; TTL giúp key cuối cùng tự hết hạn.

Mã trên **giả định công việc thường hoàn thành trong giới hạn lease**. Nếu có khả năng xử lý lâu hơn, cần xem xét gia hạn và bảo vệ side effect khỏi worker cũ.

Một lỗi cleanup khi Redis mất kết nối không đồng nghĩa rằng Redis chắc chắn chưa xóa key. Vì vậy không nên retry `DEL` mù hoặc xóa bằng lệnh vô điều kiện; TTL và token là cơ chế phục hồi an toàn hơn cho lock key.

## 8. Lease hết hạn trong lúc worker vẫn còn chạy

TTL giải quyết tình huống worker chết:

~~~text
T0      A lấy khóa, TTL 30 giây
T5      A crash
T30     Redis key hết hạn
T31     B có thể lấy khóa và tiếp tục
~~~

Nhưng worker đôi khi không chết mà chỉ bị ngừng thực thi tạm thời vì GC pause, CPU starvation, mất mạng, container freeze hoặc một lời gọi HTTP/database treo:

~~~text
T0      A lấy khóa, TTL 10 giây
T2      A bắt đầu chuẩn bị một cập nhật
T3      A bị pause dài
T10     Redis làm khóa A hết hạn
T11     B lấy khóa mới
T12     B cập nhật dữ liệu thành công
T15     A chạy tiếp, vẫn cố cập nhật dữ liệu
~~~

Tại thời điểm `T15`, A đã mất quyền sở hữu Redis lock. Nhưng Redis **không thể tự ngăn** CPU của A gọi database hoặc API bên ngoài. Bởi vậy, lease **không đủ để chứng minh side effect chỉ được áp dụng bởi một worker hợp lệ** trong mọi điều kiện.

Vấn đề này cần được giải quyết bằng idempotency, version/transaction tại tài nguyên đích hoặc fencing token khi nghiệp vụ yêu cầu.

## 9. Gia hạn lease khi công việc có thể kéo dài

Khi thời gian xử lý dài và khó dự đoán, một lựa chọn là gia hạn TTL khi worker vẫn còn sở hữu khóa. Nhưng không thể gia hạn bằng `EXPIRE lock:key 30` vô điều kiện: nếu khóa A đã hết hạn và B đã lấy lại, A sẽ gia hạn **nhầm khóa của B**.

Do đó, chỉ gia hạn khi token còn khớp:

~~~lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
~~~

Script thực hiện so sánh token và `PEXPIRE` nguyên tử. Phương thức `RedisLeaseLock.renew(...)` trong ví dụ đã sử dụng cơ chế này.

~~~java
RedisLeaseLock.Lease lease =
    locks.tryAcquire(
        "report:month-2026-11",
        Duration.ofSeconds(30)
    ).orElseThrow(() ->
        new IllegalStateException("Report already running")
    );

boolean extended = locks.renew(
    lease, Duration.ofSeconds(30)
);

if (!extended) {
    // Khóa không còn mang token của lease hiện tại.
    // Không thể xem worker này vẫn còn quyền sở hữu.
}
~~~

### Heartbeat phải được thiết kế có giới hạn

Nếu cần tự gia hạn, một worker có thể chạy heartbeat định kỳ, chẳng hạn mỗi 10 giây với TTL 30 giây. Nhưng cần lưu ý:

1. Chu kỳ gia hạn phải **ngắn hơn TTL đủ nhiều** để chịu được biến động network và scheduling.
2. Luôn gia hạn bằng **cùng token**, không phát token mới trong khi lease cũ vẫn hoạt động.
3. Nếu `renew(...)` trả `false`, worker đã mất lease; phải dừng bắt đầu thêm side effect không được bảo vệ.
4. Nếu Redis timeout trong lúc renew, trạng thái sở hữu có thể **không xác định**; nên chuyển sang chế độ bảo thủ thay vì giả định vẫn giữ khóa.
5. Cần giới hạn tổng thời gian chạy hoặc có deadline nghiệp vụ để một job treo không được gia hạn vô thời hạn.
6. Heartbeat, xử lý nghiệp vụ và release phải có **lifecycle chung**: không để heartbeat tiếp tục chạy sau khi công việc kết thúc.
7. Phải ghi nhận metric gia hạn thành công, thất bại, mất khóa và thời gian job vượt TTL.

### Vì sao heartbeat không bảo đảm tính đúng tuyệt đối?

Nếu JVM bị tạm dừng lâu hơn TTL, cả worker lẫn heartbeat đều có thể bị dừng. Redis sẽ hết hạn key, worker khác lấy khóa, rồi worker cũ tỉnh lại. Heartbeat **không thu hồi được side effect đã gửi** và không thể ép process cũ ngừng thực thi trong một hệ thống phân tán.

Khi công việc dài và có tác động quan trọng, hãy dùng fencing/versioning tại tài nguyên đích, thay vì chỉ tăng TTL rất lớn hoặc tạo heartbeat không giới hạn.

## 10. Fencing token: ngăn stale worker ghi đè dữ liệu mới

Owner token UUID giúp kiểm tra quyền **giải phóng Redis key**. Nó không cho phép database biết worker A hay B có lease mới hơn. Đối với side effect quan trọng, có thể kết hợp **fencing token** — một số thế hệ tăng đơn điệu theo mỗi lần cấp quyền xử lý.

~~~text
           Redis lease                     Tài nguyên được bảo vệ

Worker A lấy khóa, fence=41
       |
       +-------- A bị pause -------------------------+
       |                                             |
       v                                             |
Khóa A hết hạn                                       |
       |                                             |
       v                                             |
Worker B lấy khóa, fence=42                          |
       |                                             |
       +---- ghi kèm fence=42 ----------------------->| chấp nhận
                                                     | lastFence=42
Worker A tỉnh lại                                    |
       +---- ghi kèm fence=41 ----------------------->| từ chối
~~~

Một bảng PostgreSQL minh họa:

~~~sql
CREATE TABLE inventory_projection (
    sku VARCHAR(100) PRIMARY KEY,
    quantity BIGINT NOT NULL,
    last_fence BIGINT NOT NULL DEFAULT 0
);
~~~

Khi nhận cập nhật, nơi lưu dữ liệu kiểm tra số thế hệ:

~~~sql
UPDATE inventory_projection
SET quantity = :quantity,
    last_fence = :fence
WHERE sku = :sku
  AND last_fence < :fence;
~~~

Nếu `fence=41` đến sau khi bản ghi đã được cập nhật bởi `fence=42`, câu lệnh cập nhật sẽ tác động 0 row. Service cần xem đây là một thao tác stale và không coi đó là thành công.

Để an toàn, việc kiểm tra version và ghi dữ liệu phải được database thực hiện nguyên tử như một câu `UPDATE` có điều kiện hoặc transaction tương đương. Nếu chỉ `SELECT last_fence` rồi `UPDATE` độc lập, lại xuất hiện race condition giữa hai thao tác.

### Cấp fencing token ở đâu?

Fencing token cần được cấp bằng một nguồn có tính chất **tăng đơn điệu phù hợp với yêu cầu nhất quán**. Có thể dùng sequence hoặc transaction của database bảo vệ tài nguyên và xác định một số thế hệ mới sau khi đã lấy lease.

Không nên mặc định `INCR fence:inventory` trên Redis có bảo đảm tăng đơn điệu tuyệt đối qua mọi tình huống failover: Redis replication bất đồng bộ có thể mất bản ghi tăng counter trên primary cũ, khiến counter ở primary mới tụt lại. Nếu dùng Redis làm nguồn fence, phải phân tích rõ cơ chế durability/failover và khả năng cấp trùng thế hệ.

Fencing **chỉ có tác dụng khi hệ thống nhận side effect thực sự kiểm tra fence**. Nếu một API bên ngoài không hỗ trợ version hoặc idempotency key, việc gửi thêm số fence trong request nhưng bên nhận bỏ qua không có giá trị bảo vệ.

### So sánh các lớp bảo vệ

| Cơ chế | Bảo vệ điều gì? | Giới hạn |
| --- | --- | --- |
| `SET NX PX` | Một key khóa đang tồn tại không bị tạo lại trên cùng primary | Lease có thể hết hạn; failover bất đồng bộ có rủi ro |
| Token UUID | Không xóa/gia hạn khóa của owner khác | Không có thứ tự thế hệ |
| Fencing token | Từ chối thao tác cũ nếu tài nguyên đích kiểm tra đúng | Cần nguồn cấp số và nơi lưu dữ liệu nhất quán |
| Idempotency key | Không áp dụng lặp một sự kiện logic | Không tự giải quyết thứ tự giữa những sự kiện khác nhau |
| Optimistic locking / transaction | Ngăn race hoặc vi phạm ràng buộc trong database | Chỉ bảo vệ tài nguyên trong phạm vi transaction |

Nhiều hệ thống chỉ cần **unique constraint** hoặc **optimistic locking** mà không cần lock Redis. Redis lease hữu ích khi muốn điều phối công việc dài hoặc tránh xử lý trùng tốn kém, nhưng không nên thay thế ràng buộc nghiệp vụ ở nơi lưu dữ liệu.

## 11. Khi không lấy được khóa: đợi có giới hạn và backoff

`SET NX PX` là phép **try-lock**, không tự đợi cho đến khi key biến mất. Khi thất bại, ứng dụng có thể:

- **Bỏ qua lượt chạy:** phù hợp với scheduled job mà instance khác đang xử lý.
- **Trả trạng thái bận:** API trả mã phù hợp với hợp đồng của hệ thống.
- **Đợi rồi thử lại:** chỉ khi workload có thể chờ ngắn; phải có giới hạn.
- **Đưa vào hàng đợi:** khi công việc phải được thực hiện sau nhưng không cần giữ một thread HTTP chờ.

Không dùng busy waiting:

~~~java
// Anti-pattern: gọi Redis liên tục và có thể chờ vô hạn.
while (locks.tryAcquire(
        "inventory", Duration.ofSeconds(30)).isEmpty()) {
    // Không backoff, không deadline.
}
~~~

Ví dụ một chiến lược thử lại hữu hạn với jitter:

~~~java
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;

public Optional<RedisLeaseLock.Lease> acquireWithRetry(
        RedisLeaseLock locks,
        String resourceId,
        Duration leaseTtl) throws InterruptedException {

    final int maxAttempts = 5;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        Optional<RedisLeaseLock.Lease> lease =
            locks.tryAcquire(resourceId, leaseTtl);

        if (lease.isPresent()) {
            return lease;
        }

        if (attempt < maxAttempts) {
            long delayMillis =
                ThreadLocalRandom.current().nextLong(40, 121);
            Thread.sleep(delayMillis);
        }
    }

    return Optional.empty();
}
~~~

Mẫu này giới hạn tối đa năm lần thử và bốn lần chờ, không chờ vô hạn. Nó dùng thread đồng bộ nên chỉ phù hợp ở boundary chấp nhận blocking. Với Spring WebFlux, tránh `Thread.sleep` trên event-loop; dùng publisher với `Mono.delay` hoặc cơ chế retry bất đồng bộ, đồng thời giới hạn số lượt và timeout toàn request.

Số lần thử và jitter phải được chọn theo SLA. Nếu hàng trăm instance cùng thử ngay sau khi TTL hết, các khoảng chờ ngẫu nhiên có thể giảm sự tập trung nhưng không loại bỏ hoàn toàn tải cạnh tranh.

**Đừng retry mù khi acquire gặp timeout.** Khóa có thể đã được Redis tạo dù phản hồi không về. Retry nên phân biệt trường hợp `NX` trả false với lỗi kết nối có trạng thái không chắc chắn.

## 12. Redis Sentinel, replication và tính an toàn của khóa

Các thao tác acquire, release và renew cần thực thi tại **Redis primary**. Không dùng replica read để quyết định đang sở hữu khóa, vì replica có thể chưa nhận trạng thái mới nhất.

Kịch bản đáng lưu ý với replication bất đồng bộ:

~~~text
T0     A: SET lock:key token-A NX PX 30000 → OK trên primary P
T1     P chưa replicate key sang replica R
T2     P gặp sự cố
T3     R được thăng cấp thành primary mới
T4     R chưa có lock:key
T5     B: SET lock:key token-B NX PX 30000 → OK trên R
T6     A và B đều có thể tin mình đã lấy khóa hợp lệ
~~~

Sentinel giúp ứng dụng tìm primary mới, nhưng nó không biến Redis replication thành một giao thức cấp khóa tuyến tính hóa xuyên mọi lần failover. Nếu hệ thống yêu cầu tuyệt đối không có hai worker cùng áp dụng side effect, cần một lớp bảo vệ tại tài nguyên đích hoặc cơ chế điều phối có bảo đảm nhất quán phù hợp.

Một số ứng dụng dùng lệnh xác nhận replication như `WAIT` hoặc các cơ chế persistence để giảm rủi ro mất cập nhật. Những công cụ đó có thể hữu ích, nhưng **không đồng nghĩa có bảo đảm đồng thuận tuyệt đối** hoặc loại bỏ toàn bộ tình huống split-brain trong mọi điều kiện mạng. Phải hiểu chính xác hạ tầng và các giới hạn durability trước khi tuyên bố lock là an toàn nghiêm ngặt.

### Redlock có phải chỉ là chạy lệnh trên vài replica?

Không. **Redlock** là một thuật toán phối hợp nhiều Redis primary độc lập với yêu cầu quorum và giới hạn thời gian để xác định một lượt cấp khóa. Nó khác hẳn việc gửi `SET NX PX` lên các replica của cùng một primary rồi xem đó là nhiều phiếu độc lập.

Các giả định thời gian và bảo đảm an toàn của Redlock đã là chủ đề thảo luận kỹ thuật. Nếu nghiệp vụ cần strict correctness, nên xuất phát từ yêu cầu của tài nguyên và cân nhắc fencing/transaction/coordination service với bảo đảm thích hợp, thay vì chỉ thêm nhiều Redis node và kỳ vọng bài toán tự được giải quyết.

### Redis Cluster

Một lock key đơn như `lock:job:inventory` nằm trên một hash slot. Các lệnh `SET` và Lua script chỉ truy cập key đó có thể chạy trên shard chứa key, với client cluster-aware.

Nếu Lua script thao tác nhiều key, các key trên Redis Cluster thường phải thuộc cùng hash slot để đáp ứng ràng buộc lệnh đa key. Hash tag có thể đồng vị trí key liên quan, nhưng lạm dụng hash tag sẽ tạo điểm nóng trên một shard.

## 13. Khóa nhiều tài nguyên và deadlock

Không nên dùng nhiều Redis lock tách rời mà bỏ qua nguy cơ chờ vòng:

~~~text
Worker A giữ lock:account:1, đợi lock:account:2
Worker B giữ lock:account:2, đợi lock:account:1
~~~

Không worker nào có thể tiến lên trước khi lease hết. Nếu bắt buộc lấy nhiều khóa:

1. Sắp xếp các tài nguyên theo **một thứ tự thống nhất** và luôn lấy khóa theo thứ tự đó.
2. Giới hạn thời gian thử lấy đủ khóa.
3. Nếu không lấy được một khóa, giải phóng những lease đã có bằng thao tác kiểm tra token.
4. Không thực hiện side effect không thể bù trừ khi vẫn chưa lấy đủ tập khóa.
5. Cân nhắc dùng một khóa cấp aggregate hoặc một transaction database thay vì tự quản lý nhiều lease.

Ngay cả khi tránh được deadlock, các lease riêng biệt vẫn có thể hết hạn ở những thời điểm khác nhau. Nếu một nghiệp vụ yêu cầu nhiều tài nguyên phải được cập nhật nguyên tử, Redis lock đơn giản không thay thế một giao dịch có ràng buộc nhất quán tương ứng.

## 14. Kiểm thử tích hợp bằng Redis thật

Muốn chứng minh `SET NX PX` và Lua release hoạt động đúng, nên kiểm thử với Redis thật. Một mock `StringRedisTemplate` chỉ chứng minh rằng code Java đã gọi một phương thức, không chứng minh Redis đã thực hiện **kiểm tra điều kiện và cập nhật key nguyên tử**.

Ví dụ dùng Spring Boot 3.x, JUnit 5, AssertJ, Testcontainers và Awaitility:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.awaitility:awaitility'
}
~~~

Test minh họa:

~~~java
package com.example.redis.lock;

import java.time.Duration;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@Testcontainers
@SpringBootTest(classes = RedisLeaseLockTest.TestApp.class)
class RedisLeaseLockTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProps(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    @Test
    void onlyOneOwnerCanAcquireAtATime() {
        RedisLeaseLock instanceA = new RedisLeaseLock(redis);
        RedisLeaseLock instanceB = new RedisLeaseLock(redis);

        String resource = "test-exclusive-" + UUID.randomUUID();
        String key = "lock:job:" + resource;

        try {
            RedisLeaseLock.Lease owner = instanceA.tryAcquire(
                resource, Duration.ofSeconds(30)
            ).orElseThrow();

            Optional<RedisLeaseLock.Lease> contender =
                instanceB.tryAcquire(
                    resource, Duration.ofSeconds(30)
                );

            assertThat(contender).isEmpty();
            assertThat(redis.opsForValue().get(key))
                .isEqualTo(owner.token());

            Long remaining = redis.getExpire(
                key, TimeUnit.MILLISECONDS
            );
            assertThat(remaining)
                .isNotNull()
                .isGreaterThan(0L)
                .isLessThanOrEqualTo(30_000L);

            assertThat(instanceA.release(owner)).isTrue();
            assertThat(instanceB.tryAcquire(
                resource, Duration.ofSeconds(30)
            )).isPresent();
        } finally {
            redis.delete(key);
        }
    }

    @Test
    void staleOwnerDoesNotDeleteReplacementLock() {
        RedisLeaseLock locks = new RedisLeaseLock(redis);
        String resource = "test-stale-" + UUID.randomUUID();
        String key = "lock:job:" + resource;

        try {
            RedisLeaseLock.Lease stale = locks.tryAcquire(
                resource, Duration.ofSeconds(30)
            ).orElseThrow();

            // Mô phỏng tình huống lease cũ đã hết hạn.
            // Thao tác xóa này chỉ có trong TEST.
            redis.delete(key);

            redis.opsForValue().set(
                key, "replacement-owner",
                Duration.ofSeconds(30)
            );

            assertThat(locks.release(stale)).isFalse();
            assertThat(redis.opsForValue().get(key))
                .isEqualTo("replacement-owner");
            assertThat(locks.renew(
                stale, Duration.ofSeconds(30)
            )).isFalse();
        } finally {
            redis.delete(key);
        }
    }

    @Test
    void expiredLeaseEventuallyAllowsNewAcquire() {
        RedisLeaseLock locks = new RedisLeaseLock(redis);
        String resource = "test-expiry-" + UUID.randomUUID();
        String key = "lock:job:" + resource;

        try {
            RedisLeaseLock.Lease first = locks.tryAcquire(
                resource, Duration.ofMillis(250)
            ).orElseThrow();

            // Chờ bằng điều kiện, không suy luận kết quả từ
            // một lần Thread.sleep cố định sát mốc TTL.
            await()
                .atMost(Duration.ofSeconds(5))
                .pollInterval(Duration.ofMillis(40))
                .until(() ->
                    Boolean.FALSE.equals(redis.hasKey(key))
                );

            RedisLeaseLock.Lease second = locks.tryAcquire(
                resource, Duration.ofSeconds(10)
            ).orElseThrow();

            assertThat(second.token()).isNotEqualTo(first.token());
            assertThat(locks.release(first)).isFalse();
            assertThat(locks.release(second)).isTrue();
        } finally {
            redis.delete(key);
        }
    }
}
~~~

Các bài test dùng key có UUID nên ít có nguy cơ đụng dữ liệu khi chạy song song. `finally` dọn đúng key do test tạo, tránh `FLUSHDB` hoặc `FLUSHALL` ảnh hưởng dữ liệu khác.

Ba trường hợp tương ứng với:

1. **Mutual exclusion khi key còn sống:** instance A lấy được; instance B không lấy được, rồi có thể lấy sau khi A release.
2. **Ownership check:** token cũ không xóa/gia hạn được key của owner mới.
3. **TTL và recovery:** một khóa ngắn tự hết hạn và lượt acquire mới có thể thành công.

Đoạn test thứ hai xóa key có chủ đích **chỉ để mô phỏng hết hạn**, không phải kỹ thuật giải phóng khóa nên dùng trong production.

Một Redis Testcontainer đơn lẻ **không chứng minh an toàn qua Redis Sentinel failover**. Nếu yêu cầu đó quan trọng, cần môi trường thử nghiệm nhiều Redis/Sentinel, giả lập mất primary ngay sau acquire và quan sát side effect tại tài nguyên đích.

### Kiểm thử tính đúng của nghiệp vụ

Kiểm tra callback chỉ chạy đúng một lần **không đủ** để đánh giá tính an toàn của lease. Các trường hợp cần quan sát riêng:

- Worker A lấy khóa rồi pause quá TTL, worker B lấy khóa mới.
- Worker B cập nhật database với fence cao hơn.
- Worker A tỉnh lại và cố cập nhật bằng fence cũ.
- Database từ chối cập nhật stale của A.
- Retry cùng eventId không làm cập nhật số dư/tồn kho hai lần.

Đây mới là kiểm thử chứng minh rằng nghiệp vụ chịu được việc **hai worker từng tin mình được phép làm việc** ở những thời điểm khác nhau.

## 15. Theo dõi khóa trong production

Mỗi loại công việc có khóa nên được giám sát bằng metric thay vì chỉ nhìn vào số key Redis đang tồn tại.

| Chỉ số | Tác dụng |
| --- | --- |
| Acquire success count | Tần suất công việc được nhận |
| Acquire contention count | Có nhiều worker cạnh tranh cùng tài nguyên không |
| Acquire latency và wait p95/p99 | Độ trễ điều phối |
| Hold duration | Công việc có gần vượt TTL không |
| Renew success/failure | Phát hiện gia hạn chậm hoặc mất quyền sở hữu |
| Release trả `0` | Khóa đã biến mất hoặc token không còn khớp |
| Redis connection/command timeout | Phân biệt hạ tầng lỗi với khóa bận |
| Stale write rejected | Số cập nhật bị fencing/version chặn |
| Duplicate effect prevented | Hiệu quả của idempotency key |

Không nên gắn nhãn metric theo từng `resourceId` nếu hệ thống có hàng triệu tài nguyên. Dùng tên loại công việc, nhóm tài nguyên hoặc trạng thái có cardinality hữu hạn.

Để kiểm tra một key cụ thể trong quá trình điều tra:

~~~redis
GET lock:job:inventory
PTTL lock:job:inventory
~~~

`GET` và `PTTL` phục vụ **chẩn đoán**, không phải quy trình cấp quyền mới. Không tự xóa khóa từ một kết quả `GET` đã đọc trước đó; token có thể thay đổi giữa hai command.

Nếu cần thống kê key theo prefix, tránh `KEYS lock:*` trong đường xử lý production với keyspace lớn. `SCAN` phù hợp hơn cho tác vụ quản trị có kiểm soát, nhưng nó không thay thế metric acquire/release và cũng không tạo snapshot nguyên tử của mọi khóa.

### Không để cleanup che lỗi nghiệp vụ

Một job có thể thất bại đồng thời ở bước cập nhật dữ liệu và bước release. Cần giữ được lỗi gốc, đồng thời log lỗi release:

~~~text
inventory.synchronize() ném lỗi nghiệp vụ
         |
         v
finally gọi release
         |
         +-- Redis khả dụng → giải phóng khóa nếu token còn đúng
         |
         +-- Redis lỗi → log/metric, không DEL vô điều kiện
         |
         v
Lỗi nghiệp vụ ban đầu vẫn được báo cáo
~~~

Đây là lý do ví dụ service bắt và log riêng ngoại lệ của cleanup. Nếu dự án cần báo lỗi cleanup như một failure bổ sung, hãy gắn nó vào hệ thống quan sát mà không thay thế nguyên nhân thất bại ban đầu.

## 16. Các lỗi thiết kế phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Lock không bao giờ hết hạn | `SETNX` và `EXPIRE` tách rời, hoặc quên TTL | Dùng một lệnh `SET NX PX` |
| Hai worker đều chạy | Không kiểm tra kết quả `NX` hoặc dùng key khác nhau | Chọn key ổn định theo tài nguyên; chỉ xử lý nếu acquire thành công |
| Worker A xóa khóa B | Gọi `DEL` vô điều kiện | So khớp owner token và `DEL` trong Lua |
| Token cũ trông giống token mới | Dùng tên pod/thread cố định làm token | Sinh UUID mới cho từng lượt acquire |
| Worker cũ ghi dữ liệu sau khi TTL hết | Lease không tự ngăn thread cũ chạy | Fencing/version/transaction tại tài nguyên đích |
| Renew kéo dài khóa của owner khác | Gia hạn `EXPIRE` không kiểm tra token | Dùng Lua so khớp token và `PEXPIRE` |
| Job giữ khóa nhiều giờ không kết thúc | Heartbeat không có deadline tổng | Giới hạn thời gian, timeout và kiểm soát trạng thái |
| Redis command timeout bị coi là khóa bận | Lệnh có thể đã đến Redis nhưng response bị mất | Phân biệt `false` với lỗi connection/trạng thái không xác định |
| Nhiều instance spam Redis khi tranh khóa | Busy waiting không backoff | Giới hạn attempt, deadline và jitter |
| Redis primary chết rồi xuất hiện hai owner | Lock chưa kịp replicate | Đánh giá HA, fencing và yêu cầu correctness |
| Worker đọc lock từ replica rồi quyết định | Replica có thể có dữ liệu cũ | Acquire/release/renew trên primary |
| Lua trên Redis Cluster báo cross-slot | Script dùng nhiều key ở các hash slot khác nhau | Thiết kế key theo hash slot và cluster constraint |
| Retry làm thao tác tăng/append hai lần | Side effect không lũy đẳng | Idempotency key hoặc ràng buộc nghiệp vụ |
| Không thể tra cứu vì nhiều resource dùng cùng key | Key quá tổng quát hoặc thiếu namespace | Đặt quy ước key đầy đủ, có scope tenant/job |
| Lock được dùng để “bảo vệ” một giao dịch DB đã có khóa hàng | Tăng complexity không cần thiết | Ưu tiên transaction/unique constraint tại database khi đủ |

## 17. Khi nào nên chọn cách khác?

Redis lock là một lựa chọn coordination, không phải mặc định cho mọi bài toán đồng thời.

| Bài toán | Cách giải quyết nên xem xét |
| --- | --- |
| Tăng một counter trên Redis | `INCR` nguyên tử; không cần `GET` rồi khóa và `SET` |
| Chỉ tạo một order theo khóa nghiệp vụ | Unique constraint và transaction database |
| Cập nhật entity có version | Optimistic locking hoặc conditional update |
| Chỉ một worker xử lý một tác vụ queue | Consumer group/queue với idempotency và cơ chế ACK |
| Ngăn nhiều request nạp một cache key | Single-flight hoặc Redis lease tùy số instance, kèm giới hạn upstream |
| Tác vụ chạy trùng không gây hại | Làm handler lũy đẳng, có thể không cần mutex |
| Yêu cầu strict correctness qua network partition | Coordination có bảo đảm nhất quán phù hợp và fencing tại nơi ghi |
| Một quy trình cập nhật nhiều bảng PostgreSQL | Database transaction thích hợp thay vì chỉ đặt một Redis lock |

Redis lease phù hợp khi ứng dụng đã có Redis, tài nguyên có key khóa rõ ràng và lợi ích chính là **giảm xử lý trùng có chi phí**. Với nghiệp vụ nhạy cảm như chuyển tiền, phân bổ hạn mức hoặc ghi đè một cấu hình tối quan trọng, cần xem lock chỉ là **một lớp điều phối bổ sung**, không phải ràng buộc correctness duy nhất.

## 18. Tổng kết

Mẫu khóa phân tán bằng Spring Data Redis gồm bốn bước:

1. **Acquire:** `SET key uniqueToken NX PX ttl` hoặc `StringRedisTemplate.opsForValue().setIfAbsent(key, token, Duration)`.
2. **Work:** Chỉ worker nhận `true` mới bắt đầu công việc, với thời gian xử lý phù hợp lease.
3. **Release:** Chỉ xóa key nếu token vẫn khớp, thực hiện kiểm tra và `DEL` nguyên tử bằng Lua script.
4. **Recovery:** TTL cho phép key hết hạn nếu worker chết; khi cần công việc dài, chỉ gia hạn lease còn thuộc token của mình.

Ranh giới an toàn quan trọng là **lease có thể hết hạn trong khi worker cũ vẫn chạy**. Redis failover với replication bất đồng bộ có thể tạo thêm những tình huống ownership không chắc chắn, còn client timeout không chứng minh lệnh chưa từng được thực thi. Vì vậy, bên cạnh Redis lock, hãy dùng **idempotency, transaction, version hoặc fencing token được kiểm tra bởi tài nguyên đích** khi tính đúng đắn của side effect là yêu cầu bắt buộc.

Khi hiểu rõ các giới hạn này, `SET NX PX` kết hợp owner token và Lua là một công cụ đơn giản, hữu ích để điều phối nhiều instance Spring Boot — mà không nhầm nó với một giao dịch phân tán tuyệt đối.
