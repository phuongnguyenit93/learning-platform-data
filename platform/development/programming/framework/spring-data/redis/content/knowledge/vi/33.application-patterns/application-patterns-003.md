# Gia hạn khóa, mất quyền sở hữu và giới hạn an toàn khi failover trong Spring Data Redis

Một mẫu ứng dụng phổ biến là chỉ cho **một worker tại một thời điểm** thực hiện công việc trên cùng tài nguyên: tổng hợp báo cáo, xử lý một đơn hàng, đồng bộ số dư hoặc chạy một tác vụ định kỳ trên nhiều instance. Redis có thể làm nơi phối hợp bằng cách tạo một **khóa có thời hạn (lease)**. Nhưng hệ thống phân tán luôn đặt ra ba tình huống khó:

1. **Công việc chưa xong khi TTL gần hết:** worker có nên gia hạn khóa không, và gia hạn thế nào để không gia hạn nhầm khóa của worker khác?
2. **Worker mất quyền sở hữu:** sau khi tạm dừng quá lâu, mất kết nối hoặc gia hạn thất bại, worker cũ có thể vẫn tiếp tục chạy và ghi dữ liệu. Làm sao ngăn tác dụng phụ của nó?
3. **Redis master failover:** khóa vừa tạo có thể chưa kịp nhân bản sang replica. Nếu replica được nâng thành master, một worker khác có thể lấy khóa trong khi worker đầu tiên vẫn nghĩ mình sở hữu.

Giải pháp cơ bản dùng `SET key token NX PX ttl`, token ngẫu nhiên riêng cho từng lần lấy khóa, và script Lua so sánh token trước khi `PEXPIRE` hoặc `DEL`. Cách này giải quyết nhiều lỗi do cạnh tranh **trên một Redis master đang hoạt động**, nhưng **không tự cung cấp cam kết mutual exclusion tuyệt đối qua asynchronous failover**, cũng không vô hiệu hóa những tác vụ đã bắt đầu chạy khi lease hết hạn.

Bài học xây dựng một mẫu lock service bằng Spring Data Redis, phân tích quy trình heartbeat/renewal, cơ chế **fencing token**, các kịch bản failover, chiến lược kiểm thử và thời điểm nên dùng một hệ thống điều phối có bảo đảm mạnh hơn.

## 1. Khóa Redis là lease, không phải quyền sở hữu vĩnh viễn

Giả sử hai instance cùng muốn xử lý `invoice-913`:

```text
Worker A                      Redis                        Worker B
   |                            |                             |
   | SET lock:invoice:913       |                             |
   | token-A NX PX 30000        |                             |
   |--------------------------->|                             |
   |<---------------------------| OK                          |
   |                            |                             |
   | bắt đầu công việc          |                             |
   |                            |<----------------------------|
   |                            | SET ... token-B NX PX 30000 |
   |                            |---------------------------->|
   |                            |        không lấy được       |
   |                            |                             |
   | hoàn thành; unlock an toàn |                             |
```

Khóa có ba thành phần logic:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| **Resource key** | `lock:invoice:913` | Tên tài nguyên cần loại trừ cạnh tranh |
| **Owner token** | Một UUID ngẫu nhiên | Xác định lần lấy khóa đang giữ lease |
| **Lease TTL** | 30.000 ms | Thời hạn khóa tự hết hạn nếu không được gia hạn |

TTL là cơ chế tự giải phóng khi worker chết, không phải bảo đảm rằng worker chắc chắn ngừng thực thi lúc TTL chạm 0. JVM có thể bị pause bởi GC, OS scheduler, network freeze hoặc mất kết nối trong khi công việc bên ngoài vẫn tiếp tục.

### Ba tính chất khác nhau

| Tính chất | Câu hỏi cần trả lời |
|---|---|
| **Mutual exclusion** | Có thể có hai worker được chấp nhận là chủ khóa cùng lúc không? |
| **Liveness** | Nếu chủ khóa chết, worker khác có thể tiếp tục sau một thời gian không? |
| **Fencing / bảo vệ tài nguyên đích** | Một worker **đã mất quyền sở hữu** có bị từ chối khi vẫn cố ghi vào DB hoặc dịch vụ ngoài không? |

`SET NX PX` và kiểm tra token hỗ trợ mutual exclusion trong điều kiện một Redis primary hoạt động bình thường. TTL hỗ trợ liveness. **Fencing** là vấn đề riêng: cần được kiểm tra ngay tại **tài nguyên chịu tác dụng phụ**, không thể suy ra chỉ từ sự tồn tại của Redis key.

## 2. Lấy khóa đúng cách: SET NX PX và token duy nhất

Redis cung cấp lệnh nguyên tử:

```redis
SET lock:invoice:913 "token-A-random" NX PX 30000
```

Trong đó:

- `NX`: chỉ đặt key nếu nó chưa tồn tại.
- `PX 30000`: đặt TTL 30 giây, đơn vị mili giây.
- Giá trị `token-A-random`: định danh riêng của **lần lấy khóa**, không phải chuỗi cố định như `"locked"`.

Kết quả:

```text
OK       -> Lấy khóa thành công trên Redis node xử lý lệnh.
(nil)    -> Key đã tồn tại, không lấy được.
```

Để quan sát:

```redis
GET lock:invoice:913
PTTL lock:invoice:913
```

`PTTL` trả số mili giây còn lại; `-1` nghĩa là key không có TTL, `-2` nghĩa là key không tồn tại. Một key lock không có TTL ngoài ý muốn có thể gây tắc nghẽn lâu dài.

### 2.1. Vì sao không dùng SETNX rồi EXPIRE riêng?

Mẫu dễ mắc lỗi:

```redis
SETNX lock:invoice:913 token-A
EXPIRE lock:invoice:913 30
```

Nếu ứng dụng chết sau `SETNX` nhưng trước `EXPIRE`, key có thể tồn tại mà không có TTL. Vì thế nên dùng **một lệnh** `SET ... NX PX/EX` để ghép điều kiện lấy khóa với thời hạn.

### 2.2. Vì sao token phải sinh mới cho mỗi lần lấy?

Giả sử worker A dùng token cố định `"worker-A"`. Nó bị pause quá 30 giây; lease hết hạn rồi chính worker A hoặc một tiến trình khác có cùng định danh lấy khóa mới. Khi A cũ chạy lại, việc chỉ so sánh với `"worker-A"` có thể coi nhầm khóa mới là khóa của lần cũ.

Token phải gắn với **một acquisition attempt thành công**, không chỉ gắn với tên máy, tên thread hoặc instance ID. Một UUID v4 ngẫu nhiên thường là lựa chọn đơn giản. Nếu nhận dạng chủ sở hữu nhằm chống giả mạo giữa các bên không đáng tin, hãy xét cả yêu cầu bảo mật/token đủ entropy và ACL Redis; Redis lock không phải hệ thống phân quyền.

### 2.3. Không lấy khóa bằng GET rồi SET

Mẫu sau có race condition:

```text
Worker A: GET lock -> nil
Worker B: GET lock -> nil
Worker A: SET lock token-A
Worker B: SET lock token-B
```

Cả A và B có thể tưởng mình lấy khóa. `NX` là điều kiện được Redis thực thi trong **cùng lệnh SET**, loại bỏ race giữa kiểm tra và ghi ở một node.

## 3. Không bao giờ unlock bằng DEL vô điều kiện

Đây là lỗi gây mất quyền sở hữu phổ biến:

```text
t0:   Worker A lấy lock với token-A, TTL 30s.
t1:   A bắt đầu xử lý chậm.
t30:  Lock của A hết hạn.
t31:  Worker B lấy cùng key với token-B.
t32:  A chạy lại và gửi DEL lock:invoice:913.
t33:  Lock của B bị xóa dù B vẫn đang xử lý.
t34:  Worker C lại có thể lấy lock.
```

Nếu dùng `DEL key` trực tiếp trong `finally`, A có thể xóa khóa của B. Đúng là **chỉ xóa nếu token trên Redis vẫn bằng token mà A đã tạo**.

### 3.1. Lua compare-and-delete

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
```

Gọi:

```redis
EVAL "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end" 1 lock:invoice:913 token-A
```

Kết quả:

- `1`: khóa vẫn thuộc token này, đã xóa thành công.
- `0`: key không còn tồn tại hoặc token đã thay đổi; **không xóa khóa của người khác**.

Không thay script bằng hai lệnh `GET` rồi `DEL` tách rời, vì khóa có thể hết hạn và được lấy lại **giữa** hai lệnh. Lua thực hiện kiểm tra và xóa liên tiếp mà không bị một lệnh Redis client khác chen vào.

### 3.2. Lệnh compare-and-delete ở phiên bản Redis mới

Redis **8.4+** cung cấp một lựa chọn native:

```redis
DELEX lock:invoice:913 IFEQ token-A
```

Nó xóa có điều kiện nếu giá trị khớp, phù hợp với mục tiêu compare-and-delete. Trong hệ thống vẫn dùng Redis phiên bản cũ, script Lua là cách tương thích rộng hơn. Cần xác nhận hỗ trợ của server và driver; không copy lệnh `DELEX` vào Redis 7.x rồi kỳ vọng nó chạy.

## 4. Gia hạn lease phải kiểm tra đúng owner

Giả sử công việc dự kiến 20 giây nhưng đôi lúc mất 2 phút. Nếu giữ TTL 30 giây và không gia hạn, worker A có thể bị mất lease trước khi hoàn tất. Một cơ chế heartbeat có thể gia hạn thời hạn của key **khi token vẫn khớp**.

### 4.1. Không dùng EXPIRE/PEXPIRE trần

Ví dụ sai:

```redis
PEXPIRE lock:invoice:913 30000
```

Nếu lock của A đã hết hạn và B đã tạo lock mới, A gửi `PEXPIRE` có thể **gia hạn khóa của B** mà không biết mình đã mất quyền. Điều này không bảo vệ bất kỳ quy tắc ownership nào.

### 4.2. Lua compare-and-extend

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2]))
else
    return 0
end
```

Tham số:

```text
KEYS[1]  = lock:invoice:913
ARGV[1]  = token-A
ARGV[2]  = 30000   (TTL mới, milliseconds)
```

Kết quả:

| Giá trị | Diễn giải |
|---|---|
| `1` | Token khớp, đã đặt lại TTL từ thời điểm thực thi trên Redis |
| `0` | Key không còn hoặc token khác: **không được tiếp tục coi mình sở hữu khóa** |
| Timeout/exception | Không biết chắc có gia hạn thành công hay không; phải chuyển trạng thái local thành **không chắc chắn**, dừng các tác dụng phụ thiếu bảo vệ |

Script đảm bảo kiểm tra token và đặt lại expiration là một thao tác nguyên tử **trên node đang xử lý**. Nó **không** bảo đảm worker sẽ không bao giờ mất lease, và không khắc phục việc trạng thái lock bị mất khi master failover sang replica chưa nhận bản ghi.

### 4.3. Điều kiện gia hạn hợp lệ

Worker chỉ nên coi lần gia hạn thành công khi:

1. Có một lần lấy khóa thành công trước đó và đang giữ token của lần đó.
2. Redis thực thi compare-and-extend với kết quả xác nhận thành công.
3. Phản hồi đến trong khoảng ngân sách thời gian mà worker vẫn có cơ sở tin rằng lease chưa bị quá hạn.
4. Chưa có lỗi local khiến worker đã đánh dấu **lost ownership**.

Nếu script trả `0`, không nên “tiếp tục làm rồi xin lại khóa” trong cùng critical section. Phải coi công việc hiện tại bị mất quyền, ngừng/không commit, và tạo **một lần xử lý mới có owner token mới** theo chính sách retry của nghiệp vụ.

## 5. Thiết kế lịch gia hạn: heartbeat không phải phép màu

Ví dụ lease TTL = 30 giây:

```text
t0     SET NX PX 30000 thành công
t10    compare-and-PEXPIRE -> TTL trở lại 30s
t20    compare-and-PEXPIRE -> TTL trở lại 30s
t30    compare-and-PEXPIRE -> TTL trở lại 30s
...
tN     Công việc xong -> compare-and-DEL
```

Một lựa chọn phổ biến là gia hạn mỗi **TTL/3** (ví dụ mỗi 10 giây với TTL 30 giây), thay vì chờ còn 1–2 giây mới gửi. Đây là gợi ý để có khoảng dự phòng, **không phải công thức bảo đảm an toàn** trong mọi latency và pause.

### 5.1. Các khoảng thời gian cần phân biệt

| Thời gian | Ý nghĩa |
|---|---|
| **Lease TTL** | Redis cho phép key tồn tại trong bao lâu kể từ lần cấp/gia hạn |
| **Renewal interval** | Khoảng chờ giữa các lần heartbeat dự kiến |
| **Network timeout** | Mất bao lâu trước khi client kết luận chưa nhận phản hồi |
| **Scheduling delay** | Heartbeat bị trễ vì thread pool, GC pause, CPU throttling |
| **Critical section duration** | Thời gian nghiệp vụ thực sự cần khóa |
| **Safety margin** | Khoảng dự phòng trước khi lease có thể hết hạn |

Một lịch gia hạn tưởng là 10 giây có thể xảy ra trễ 20 giây vì ứng dụng stop-the-world, container bị treo hoặc network lag. Vì thế thời hạn thực tế phải xét **worst-case latency**, không chỉ trung bình.

### 5.2. Không giữ lease vô hạn mà không giới hạn công việc

Một background worker treo mãi nhưng heartbeat vẫn chạy có thể giữ khóa hàng giờ:

```text
Nghiệp vụ treo  --->  heartbeat vẫn gia hạn  ---> worker khác không bao giờ vào
```

Đặt **maximum lease age / maximum job duration** hoặc giới hạn tổng thời gian gia hạn nếu nghiệp vụ yêu cầu. Khi quá ngưỡng, dừng gia hạn, đánh dấu job không còn hợp lệ và khởi động quy trình recovery. Cần cân nhắc nếu job đang có side effect không thể dừng: chỉ ngừng renew không thể làm side effect đó tự biến mất.

### 5.3. Dùng monotonic time để đo thời gian local

Trong Java, `System.nanoTime()` phù hợp để đo **khoảng thời gian đã trôi qua** cho deadline local; `System.currentTimeMillis()` chịu ảnh hưởng thay đổi đồng hồ hệ thống. Tuy nhiên:

- Deadline local không hoàn toàn tương đương TTL Redis, vì có thời gian truyền lệnh và xử lý phản hồi.
- Redis là nơi quyết định key còn tồn tại hay đã hết hạn.
- Dù dùng monotonic clock, worker cũng không được tự chứng minh quyền sở hữu vĩnh viễn bằng đồng hồ của mình.

Một ứng dụng thận trọng có thể tính ngân sách lease từ **trước khi gửi lệnh SET**, trừ network latency và safety margin, thay vì bắt đầu đếm khi nhận phản hồi. Cách tính này giúp **fail closed** nếu lệnh lấy khóa mất nhiều thời gian.

## 6. Mẫu Spring Data Redis: acquire, renew và release

Ví dụ sau dùng Spring Boot 3.x/Java 17, `StringRedisTemplate` và Redis server có hỗ trợ các lệnh `SET NX PX`, `GET`, `PEXPIRE`, `DEL`. Nó minh họa một lease **trên một Redis primary ở thời điểm hoạt động bình thường**; không nên xem là hệ thống distributed lock fault-tolerant tuyệt đối.

Dependency Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

`application.yml` cho Redis test:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

### 6.1. Cài đặt RedisLeaseService

```java
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class RedisLeaseService {

    public record Lease(String key, String token, Duration ttl) {
    }

    private static final DefaultRedisScript<Long> RENEW_SCRIPT =
            script("""
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                    return redis.call('PEXPIRE', KEYS[1],
                        tonumber(ARGV[2]))
                end
                return 0
                """);

    private static final DefaultRedisScript<Long> RELEASE_SCRIPT =
            script("""
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                    return redis.call('DEL', KEYS[1])
                end
                return 0
                """);

    private final StringRedisTemplate redis;

    public RedisLeaseService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static DefaultRedisScript<Long> script(String text) {
        DefaultRedisScript<Long> result = new DefaultRedisScript<>();
        result.setScriptText(text);
        result.setResultType(Long.class);
        return result;
    }

    public Optional<Lease> tryAcquire(String resource, Duration ttl) {
        if (resource == null || !resource.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid resource ID");
        }

        if (ttl == null || ttl.isNegative() || ttl.isZero()
                || ttl.toMillis() <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        String key = "lock:invoice:" + resource;
        String token = UUID.randomUUID().toString();

        Boolean acquired =
                redis.opsForValue().setIfAbsent(key, token, ttl);

        if (acquired == null) {
            throw new IllegalStateException(
                    "Lock result unknown; do not run critical section");
        }

        if (acquired) {
            return Optional.of(new Lease(key, token, ttl));
        }
        return Optional.empty();
    }

    public boolean renew(Lease lease) {
        Long result = redis.execute(
                RENEW_SCRIPT,
                List.of(lease.key()),
                lease.token(),
                Long.toString(lease.ttl().toMillis()));

        if (result == null) {
            throw new IllegalStateException("Renewal result unknown");
        }
        return result == 1L;
    }

    public boolean release(Lease lease) {
        Long result = redis.execute(
                RELEASE_SCRIPT,
                List.of(lease.key()),
                lease.token());

        if (result == null) {
            throw new IllegalStateException("Release result unknown");
        }
        return result == 1L;
    }
}
```

Lưu ý:

1. `StringRedisTemplate` dùng kiểu key/value String dễ đối chiếu với Redis CLI.
2. `setIfAbsent(key, token, ttl)` ánh xạ ý tưởng `SET NX PX/EX`: đặt token và expiration trong một thao tác.
3. Mỗi lần `tryAcquire` tạo một UUID mới; không tái sử dụng token của lease cũ.
4. `renew` và `release` sử dụng script với **một key**; Redis thực hiện kiểm tra token và thay đổi key trong một lần gọi.
5. `false` từ `tryAcquire` nghĩa là có người đang giữ khóa, **khác** tình huống timeout/exception không rõ Redis có nhận lệnh hay không.
6. Nếu `renew` trả `false` hoặc exception, caller phải **đánh dấu mất hoặc không chắc quyền sở hữu**, không chỉ ghi log rồi tiếp tục.

Ví dụ không cài đặt chức năng retry tự động ở tầng service. Việc chờ rồi xin khóa lại cần biết giới hạn thời gian nghiệp vụ, backoff và tình huống request có tác dụng phụ đã xảy ra.

### 6.2. Dùng đúng try/finally cho công việc ngắn

Với công việc **được chứng minh luôn kết thúc nhanh hơn TTL trong điều kiện vận hành chấp nhận được**, có thể dùng:

```java
import java.time.Duration;
import java.util.Optional;

public void generateInvoice(String invoiceId) {
    Optional<RedisLeaseService.Lease> maybeLease =
            leaseService.tryAcquire(invoiceId, Duration.ofSeconds(30));

    if (maybeLease.isEmpty()) {
        return; // Instance khác đang xử lý.
    }

    RedisLeaseService.Lease lease = maybeLease.get();
    try {
        invoiceService.generateIdempotently(invoiceId);
    } finally {
        try {
            boolean released = leaseService.release(lease);
            if (!released) {
                log.warn("Lock no longer owned for {}", invoiceId);
            }
        } catch (RuntimeException error) {
            log.warn("Could not confirm lock release", error);
        }
    }
}
```

`leaseService`, `invoiceService` và `log` trong ví dụ là các dependency của class chứa method. `generateIdempotently(...)` là phương thức nghiệp vụ **phải tự cài đặt idempotency**, không phải API Spring Data Redis.

**Quan trọng:** mẫu `try/finally` bảo đảm chương trình **cố gắng release**, không bảo đảm `invoiceService` dừng trước khi TTL hết hạn. Nếu runtime của công việc có thể kéo dài bất kỳ, phải bổ sung gia hạn và cơ chế bảo vệ tài nguyên đích.

## 7. Mẫu heartbeat bằng ScheduledExecutorService

Một heartbeat thường chạy tách khỏi luồng xử lý chính:

```text
Thread nghiệp vụ:          |--------- xử lý invoice ---------|
Thread renewal:             | renew | renew | renew | renew |
Redis lease:            SET NX PX --PEXPIRE--PEXPIRE--PEXPIRE
```

Đây là **mẫu kiến trúc** cho một background task ngắn đến trung bình, không phải một trình quản lý lock có bảo đảm an toàn đầy đủ. Giả sử service có một `ScheduledExecutorService` được quản lý lifecycle:

```java
import java.time.Duration;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class LeaseHeartbeat {

    private final RedisLeaseService locks;
    private final ScheduledExecutorService scheduler;

    public LeaseHeartbeat(
            RedisLeaseService locks,
            ScheduledExecutorService scheduler) {
        this.locks = locks;
        this.scheduler = scheduler;
    }

    public Handle start(RedisLeaseService.Lease lease) {
        AtomicBoolean lost = new AtomicBoolean(false);

        long intervalMs = Math.max(
                1L, lease.ttl().toMillis() / 3L);

        ScheduledFuture<?> future =
                scheduler.scheduleWithFixedDelay(() -> {
                    if (lost.get()) {
                        return;
                    }
                    try {
                        if (!locks.renew(lease)) {
                            lost.set(true);
                        }
                    } catch (RuntimeException error) {
                        // Không biết lease còn hiệu lực hay không:
                        // fail closed thay vì giả định đã gia hạn.
                        lost.set(true);
                    }
                }, intervalMs, intervalMs,
                   TimeUnit.MILLISECONDS);

        return new Handle(lost, future);
    }

    public record Handle(
            AtomicBoolean lost,
            ScheduledFuture<?> future) implements AutoCloseable {

        public boolean ownershipUncertainOrLost() {
            return lost.get();
        }

        @Override
        public void close() {
            future.cancel(false);
        }
    }
}
```

Ví dụ trên cố ý **fail closed** sau lỗi renewal: đánh dấu `lost` và không có một luồng tự động “tin lại” chỉ vì lần sau Redis sẵn sàng. Nếu muốn chính sách phục hồi tinh vi hơn, phải định nghĩa rõ state machine và deadline.

### 7.1. Cần thấy giới hạn của ví dụ heartbeat

- `scheduleWithFixedDelay` chỉ chạy sau khi lần trước kết thúc và đợi thêm khoảng delay; nếu Redis chậm, nhịp thực tế có thể trễ.
- `future.cancel(false)` không ngắt một lần renewal **đang chạy**. Nếu task shutdown, compare-and-PEXPIRE sau khi unlock sẽ thấy key không còn và trả 0; không gia hạn nhầm khóa của người khác.
- `AtomicBoolean lost` chỉ thông báo trạng thái tới luồng nghiệp vụ. Nó **không ngắt** HTTP request, SQL transaction hoặc side effect đang chạy.
- Kể cả khi `lost == false`, lease vẫn có thể hết hạn giữa hai lần kiểm tra local nếu JVM pause, Redis failover hoặc network partition.
- Ví dụ chưa triển khai **local monotonic deadline**, maximum job duration, fencing token, persisted job state, lifecycle của scheduler hay cảnh báo. Các yếu tố đó cần bổ sung cho production.

### 7.2. Phối hợp heartbeat và công việc

Luồng chính có thể sử dụng:

```java
RedisLeaseService.Lease lease =
        locks.tryAcquire(invoiceId, Duration.ofSeconds(30))
                .orElseThrow(() ->
                        new IllegalStateException("Invoice is locked"));

try (LeaseHeartbeat.Handle heartbeat = heartbeats.start(lease)) {
    invoiceService.prepareDraft(invoiceId);

    if (heartbeat.ownershipUncertainOrLost()) {
        throw new IllegalStateException("Lease lost before commit");
    }

    // Vẫn cần kiểm tra fencing/idempotency tại resource đích.
    invoiceService.commitWithFencing(invoiceId, fencingToken);
} finally {
    locks.release(lease);
}
```

`fencingToken` là một giá trị **riêng** được cấp bởi cơ chế fencing đáng tin cậy, không phải UUID token của Redis lock. Đoạn ví dụ không thể chạy độc lập cho tới khi ứng dụng cung cấp `invoiceService`, `heartbeats`, `locks` và bộ cấp fencing token.

**Không nên tuyên bố điều kiện `if (!lost)` ở trên loại trừ mọi cuộc đua.** Worker có thể mất lease **sau lúc kiểm tra** nhưng trước khi ghi DB. Chỉ một kiểm tra có hiệu lực ở tài nguyên đích (fencing/version/transactional guard) mới có thể chặn các bản ghi của owner lỗi thời theo chính sách thích hợp.

## 8. Mất quyền sở hữu: trạng thái cần xử lý như một sự kiện nghiêm trọng

Có nhiều lý do một worker không còn là owner:

1. Key tự hết hạn vì TTL.
2. Một tiến trình quản trị xóa hoặc thay giá trị key.
3. Worker khác lấy được key sau expiration.
4. Redis failover làm mất bản ghi khóa trên master mới.
5. Renewal trả 0 vì token không còn khớp.
6. Renewal timeout nên worker **không có bằng chứng** rằng lease đã được kéo dài.

Mất quyền sở hữu không nhất thiết tương đương `GET key` đã trả một token khác trong mọi thời điểm. Đôi khi **trạng thái không rõ** là đủ để ngừng làm một công việc có tính phá hủy.

### 8.1. Một state machine đơn giản

```text
      +-----------+
      |  NEW      |
      +-----+-----+
            |
            | SET NX PX thành công
            v
      +-----------+
      |  HELD     |---- renew thành công ----+
      +-----+-----+                         |
            ^                               |
            +-------------------------------+
            |
            +---- xử lý xong -> compare-and-DEL -> RELEASED
            |
            +---- renew=0 / lease expired -> LOST
            |
            +---- timeout / failover -> UNCERTAIN

LOST / UNCERTAIN:
  Không tự trở lại HELD trong cùng critical section.
  Ngăn commit không có fencing, ghi trạng thái cần recovery.
```

Một worker mất quyền có thể:

- Hủy tác vụ có khả năng cancel (best effort).
- Đánh dấu job là **cần retry/reconciliation**.
- Không bắt đầu thêm side effect.
- Tra cứu trạng thái một giao dịch ngoài có kết quả chưa rõ.
- Kết thúc luồng hiện tại và để một lượt làm việc mới lấy lock mới.

### 8.2. Điều không thể bảo đảm chỉ bằng cancellation

Một worker có thể đang chờ response từ cổng thanh toán. Khi nhận tín hiệu mất lease, ứng dụng hủy `Future` hoặc interrupt thread, nhưng request HTTP **có thể đã được bên ngoài xử lý**. Cancellation chỉ yêu cầu ngừng công việc nếu còn có thể, không phải một cơ chế undo.

Vì vậy, đối với payment, inventory, ledger hay tạo hóa đơn duy nhất, cần idempotency key, trạng thái bền vững và cơ chế bảo vệ ở nơi thực thi side effect. Redis lock chỉ hỗ trợ **phối hợp giảm cạnh tranh**.

## 9. Stale owner: worker cũ sống lại sau khi TTL hết hạn

Xem một chuỗi sự kiện:

```text
Thời gian      Worker A              Redis               Worker B
---------------------------------------------------------------------------
t0            SET token-A PX30s ---> OK
t1            đọc trạng thái
t2            JVM pause dài
t30                                 key hết hạn
t31                                                       SET token-B -> OK
t32                                                       bắt đầu cập nhật DB
t35           JVM A tiếp tục
t36           A vẫn muốn cập nhật DB
```

Ngay cả khi compare-and-PEXPIRE và compare-and-DEL đã viết đúng, A vẫn có thể gọi `UPDATE` ở database sau khi lease hết hạn. Hai Lua script không ngăn A gọi DB vì Redis không kiểm soát tài nguyên đích.

**Câu hỏi đúng không chỉ là “làm sao ngăn A xóa lock của B?” mà còn là “làm sao ngăn A ghi đè kết quả của B?”**

Một câu trả lời phổ biến là **fencing token**.

## 10. Owner token và fencing token là hai thứ khác nhau

### 10.1. Owner token

Ví dụ:

```text
token-A = d5f8f6e4-... (UUID)
token-B = a21a17b0-... (UUID)
```

Token ngẫu nhiên dùng để chứng minh client đang nắm đúng **giá trị lock key**, phục vụ so sánh trong Lua khi renew/release. Hai UUID không có thứ tự thời gian đáng tin cậy. Không thể nói token `a21...` “mới hơn” `d5f...` chỉ vì so sánh chuỗi.

### 10.2. Fencing token

Fencing token phải là một số/phiên bản **tăng đơn điệu theo mỗi lần được cấp quyền** cho cùng tài nguyên:

```text
Lần owner A được cấp quyền: fencing = 41
Lần owner B được cấp quyền: fencing = 42
Lần owner C được cấp quyền: fencing = 43
```

Tài nguyên đích cần từ chối những thao tác đến từ fencing version **cũ hơn** version đã được chấp nhận hoặc phiên bản cấp quyền hiện hành, theo mô hình nhất quán đang sử dụng.

```text
Owner A (fence 41) -----> Resource database
      (bị pause)

Owner B (fence 42) -----> Resource database
                           lưu version mới 42

Owner A (fence 41) -----> Resource database
                           REJECT: 41 < 42
```

Với phiên bản monotonic và resource guard thích hợp, A không thể ghi đè trạng thái sau khi DB đã chấp nhận phiên bản mới hơn.

### 10.3. SQL guard minh họa

Một bảng:

```sql
CREATE TABLE invoice_state (
    invoice_id       VARCHAR(100) PRIMARY KEY,
    current_status   VARCHAR(50) NOT NULL,
    last_fence       BIGINT NOT NULL DEFAULT 0
);
```

Tài nguyên đích có thể kiểm tra phiên bản trong cùng lệnh cập nhật:

```sql
UPDATE invoice_state
   SET current_status = :new_status,
       last_fence = :incoming_fence
 WHERE invoice_id = :invoice_id
   AND last_fence <= :incoming_fence;
```

Ứng dụng phải kiểm tra số row được cập nhật. Nếu `last_fence` đã là `42` mà A gửi `41`, câu lệnh cập nhật `0` row và bị từ chối.

Điều kiện `<=` minh họa một owner cùng fence có thể thực hiện nhiều cập nhật trong lease của mình; trong nghiệp vụ cần exactly-once cho **từng thao tác**, cần kết hợp `operationId`/idempotency và ràng buộc khác.

**Giới hạn của ví dụ:** kiểm tra `last_fence` chặn owner cũ **sau khi** một thao tác mang fence mới đã được chấp nhận. Nếu yêu cầu cứng là owner A phải bị từ chối **ngay thời điểm B được cấp quyền**, dù B chưa kịp ghi, tài nguyên đích phải đối chiếu **version cấp quyền hiện hành** từ một nguồn nhất quán mạnh. Chỉ kiểm tra “version lớn nhất đã ghi” không thể chứng minh điều này trong mọi interleaving.

### 10.4. Fencing token phải được cấp từ nguồn đáng tin

Không đủ nếu chỉ làm:

```redis
INCR global:fencing:invoice:913
```

trên một Redis master có replication bất đồng bộ rồi tuyên bố token **không bao giờ lùi**. Sau failover, một lần `INCR` có thể bị mất nếu replica chưa nhận cập nhật, dẫn tới cấp lại số cũ hoặc số nhỏ hơn.

Hơn nữa, **thứ tự cấp fence phải gắn với thứ tự cấp quyền**. Nếu A lấy Redis lock rồi bị pause **trước khi xin fence**, B có thể lấy lock mới và xin fence trước; A sau đó xin một fence lớn hơn mặc dù thực tế là owner cũ. Vì vậy không thể tùy tiện tách hai việc “lấy lock” và “tăng một counter” rồi suy luận fencing đúng.

Đối với dữ liệu tài chính hoặc thao tác không được phép có stale writer, hãy cân nhắc:

- Một transaction database quản lý **lock grant epoch/version** và cập nhật tài nguyên trong cùng hệ có tính nhất quán phù hợp.
- Một hệ thống điều phối có cấp **monotonic fencing token** cùng thứ tự cấp quyền, ví dụ cơ chế lock/lease có phiên bản từ dịch vụ coordination được thiết kế cho mục tiêu này.
- Một ràng buộc kiểm tra version **tại tài nguyên đích** thay vì tin hoàn toàn vào bộ nhớ hoặc heartbeat của worker.

Redis lock vẫn có thể dùng như lớp giảm tải/giảm cạnh tranh ở phía trước, nhưng không nên là **bằng chứng duy nhất** để commit dữ liệu có yêu cầu an toàn mạnh.

## 11. Mất an toàn khi Sentinel/Cluster failover

Redis Sentinel và Redis Cluster thường dựa trên **replication bất đồng bộ**. Một khóa vừa ghi trên master có thể chưa đến replica.

### 11.1. Chuỗi vi phạm mutual exclusion

```text
                     Redis master M1         Replica R1
                           |                    |
t0  Worker A:
    SET lock token-A
    NX PX 30000 ---------->| OK                 |
                           |                    |
t1  M1 chưa replicate lock |                    | (chưa có key)

t2  M1 gặp sự cố           X                    |
                                                |
t3  Sentinel/Cluster nâng R1 thành master mới  |
                                                v
t4  Worker B:
    SET lock token-B NX PX 30000 -------------> R1: OK

t5  Worker A vẫn tin lần SET ban đầu còn hiệu lực.
    Worker B cũng vừa lấy khóa trên master mới.
    ==> Có thể đồng thời hoạt động trên cùng tài nguyên.
```

Đây là **cửa sổ vi phạm an toàn** của mô hình lấy lock từ một master được bảo vệ bằng replica bất đồng bộ. Token khác nhau và Lua đúng vẫn không thể sửa việc master mới **không có bản ghi token-A**.

### 11.2. Sentinel giúp availability, không tự biến lock thành consensus

Sentinel giám sát và bầu chọn master mới, hỗ trợ khôi phục việc phục vụ dữ liệu. Nhưng quá trình đó không khiến mỗi lệnh ghi lock trở thành một commit được đồng thuận bởi quorum trước khi trả về ứng dụng.

Với Spring Boot có thể khai báo:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - redis-s1.example:26379
          - redis-s2.example:26380
          - redis-s3.example:26381
```

Khi đổi master, `LettuceConnectionFactory`/`JedisConnectionFactory` có thể tìm endpoint mới, nhưng nếu trạng thái lock bị mất trước khi replicate, việc kết nối mới thành công **không chứng minh lease cũ vẫn an toàn**.

### 11.3. Cluster cũng không tự giải quyết

Redis Cluster chia key theo hash slot. Lock key cụ thể thuộc **một slot**, và tại một thời điểm có một master chịu trách nhiệm ghi cho slot đó:

```text
lock:invoice:913 -> hash slot s -> Master B -> Replica B'
```

Khi B failover sang B', nếu bản ghi lock chưa được nhân bản, vấn đề an toàn tương tự Sentinel vẫn có thể xảy ra. Phân phối key trên 16.384 slot giúp scale, **không** biến một lock key thành quorum-based distributed lock.

Nếu ứng dụng cần thực hiện một transaction/script với **nhiều lock key**, còn có ràng buộc `CROSSSLOT`; phải đặt chúng cùng slot hoặc thiết kế lại. Nhưng đưa tất cả lock key vào một hash tag duy nhất có thể tạo hot slot và vẫn không khắc phục bản chất failover bất đồng bộ.

## 12. WAIT, WAITAOF và chính sách replication giúp được gì?

Redis có các cơ chế làm tăng độ tin cậy thực tế của bản ghi, nhưng phải hiểu giới hạn:

### 12.1. WAIT

```redis
SET lock:invoice:913 token-A NX PX 30000
WAIT 1 500
```

Ý nghĩa: `WAIT 1 500` chờ tối đa **500 ms** để ít nhất một replica xác nhận đã nhận những lệnh ghi trước đó **trên cùng connection**. Kết quả trả về là số replica đã xác nhận, kể cả khi timeout; ứng dụng phải tự kiểm tra nó có đạt ngưỡng mong muốn không.

**WAIT không tạo strong consistency hoặc linearizable lock.** Redis vẫn có thể promote replica khác chưa nhận bản ghi hoặc xảy ra trường hợp mất write dù đã nhận ACK từ một số replica. Đây là lựa chọn giảm rủi ro, không phải một chứng nhận lock có thể bảo vệ nghiệp vụ giao dịch quan trọng tuyệt đối.

Trong Spring, những lời gọi `StringRedisTemplate` độc lập không nhất thiết duy trì cùng một kết nối cho `SET` và `WAIT`. Nếu muốn thử nghiệm semantics của `WAIT`, phải quản lý connection/session cẩn thận và kiểm tra API/driver đang dùng; không đặt hai lời gọi rời nhau rồi chắc chắn WAIT đã chờ bản ghi khóa đúng.

### 12.2. WAITAOF và persistence

Redis có `WAITAOF` ở những phiên bản hỗ trợ, giúp chờ ghi AOF cục bộ/replica theo tham số, với các giới hạn riêng. Nó có thể cải thiện độ bền của ghi trong một số kịch bản, nhưng **không biến Redis replication/failover thành hệ thống coordination có fencing và consensus**.

RDB/AOF, `min-replicas-to-write` và `min-replicas-max-lag` cũng là cấu hình vận hành giúp giảm một số rủi ro, song không thay thế việc phân tích trường hợp partition, promotion và stale worker.

### 12.3. Phân biệt cải thiện xác suất với bảo đảm

| Giải pháp | Có ích cho | Không tự giải quyết |
|---|---|---|
| `SET NX PX` | Lấy khóa atomic trên primary | Failover mất trạng thái khóa |
| Token ngẫu nhiên + Lua | Chỉ owner hiện tại renew/unlock | Owner cũ tiếp tục ghi DB |
| Heartbeat | Công việc dài không mất lease nếu renew kịp | GC pause, network freeze, failover |
| `WAIT` | Tăng xác suất bản ghi đã tới replica | Consensus/linearizable lock |
| AOF/`WAITAOF` | Giảm mất ghi theo chính sách persistence | Ownership sau partition và stale writer |
| Fencing tại resource đích | Từ chối phiên bản cũ theo thứ tự cấp quyền được tin cậy | Cần có nguồn version đáng tin và enforcement thực tế |
| Idempotency | Tránh nhân đôi tác dụng phụ do retry | Không tự tạo mutual exclusion giữa các task khác nhau |

## 13. Redlock: lựa chọn có điều kiện, không phải bảo đảm mặc định

Tài liệu Redis mô tả **Redlock** cho mô hình gồm nhiều master Redis **độc lập**, không phải một primary và các replica của nó. Một client cố gắng lấy cùng lock key với cùng random token trên nhiều master; chỉ xem là lấy được nếu đạt **quorum** và thời gian lấy khóa đủ nhỏ so với TTL. Khi gia hạn cũng cần gia hạn thành công đủ quorum trong thời hạn hợp lệ.

Ví dụ khái niệm:

```text
   Redis độc lập A       Redis độc lập B       Redis độc lập C
         |                     |                     |
         +---------- Worker W ----------------------+
                            |
                    acquire quorum
                     (ví dụ 2/3)
```

**Không nhầm** ba replica của một Redis Cluster shard với ba master độc lập của mô hình Redlock. Các replica của một shard chia sẻ lịch sử replication; failover trong shard không biến lock của nó thành một quorum lock độc lập.

Redlock dựa trên những giả định về thời gian, clock drift, mức độ độc lập của các node, thời gian xử lý và pause của client. Có những thảo luận chuyên môn về giới hạn an toàn của nó trong các tình huống delay/pause/partition. Vì vậy:

- Nếu chỉ cần giảm xử lý trùng cho job **có idempotency**, một lock Redis đơn giản có thể phù hợp.
- Nếu cần tính sẵn sàng cao hơn cho lock service và chấp nhận các giả định của thuật toán, có thể đánh giá Redlock bằng thử nghiệm và phân tích rủi ro.
- Nếu yêu cầu cứng là **không bao giờ có stale writer**, đặc biệt với payment/ledger, ưu tiên một cơ chế có fencing và enforcement bởi tài nguyên đích, hoặc một coordination system phù hợp với yêu cầu nhất quán.

Không nên viết “dùng Redlock là chắc chắn không có race condition trong mọi trường hợp”. Mỗi thuật toán phải được đánh giá dựa trên mô hình lỗi và SLA thực tế.

## 14. RedisLockRegistry và thư viện hỗ trợ gia hạn

Không phải mọi chức năng lock đều nằm trong `Spring Data Redis` cốt lõi. **Spring Integration** có thành phần `RedisLockRegistry` để cấp khóa phân tán theo API lock, và một số thư viện bên thứ ba như Redisson cung cấp lock abstraction có cơ chế renewal/watchdog.

Theo các phiên bản Spring Integration gần đây:

- `RedisLockRegistry` cho phép phối hợp khóa giữa nhiều instance, với expiration mặc định có thể cấu hình.
- Từ **Spring Integration 6.4**, `setRenewalTaskScheduler(...)` cho phép tự động gia hạn theo lịch khi khóa đang được giữ.
- Các phiên bản mới hơn cung cấp API TTL/renewal bổ sung; tên phương thức và khả năng native Redis CAS/CAD có thể khác theo phiên bản.

Ưu điểm của việc dùng thư viện phù hợp là giảm mã tự viết cho acquire/release, renewal scheduler và local lock lifecycle. Nhưng **tự động gia hạn không tự cấp fencing token** và không xóa đi giới hạn an toàn của replication bất đồng bộ.

Khi chọn thư viện, kiểm tra:

1. Redis version/Spring Boot BOM và driver Lettuce/Jedis.
2. Cách phân biệt key ownership và điều kiện unlock.
3. Có trả tín hiệu khi mất lease/renewal thất bại không?
4. Một job bị JVM pause có thể tiếp tục sau expiry thế nào?
5. Redis Cluster/Sentinel và multi-key script có giới hạn nào?
6. Có cách lấy fencing token đáng tin và kiểm tra tại resource đích không?
7. Có bounded retry, timeout, metrics và shutdown lifecycle không?

Thư viện giúp triển khai primitive; hệ thống vẫn phải chịu trách nhiệm với **sự đúng đắn của nghiệp vụ**.

## 15. Mẫu ứng dụng: xử lý job có trạng thái bền vững

Giả sử một ứng dụng xử lý báo cáo `report-913`, có ba instance:

```text
Scheduler instance 1 ---+
Scheduler instance 2 ---+--> Redis lease
Scheduler instance 3 ---+         |
                                  v
                             Worker đã chọn
                                  |
                                  v
                           Database job_state
                                  |
                                  v
                            Tạo báo cáo
                                  |
                                  v
                         Lưu kết quả idempotent
```

Một thiết kế thận trọng:

1. Lấy lease theo `reportId` để **giảm** số worker cùng bắt đầu.
2. Đọc trạng thái job bền vững (`NEW`, `RUNNING`, `DONE`, `FAILED`).
3. Dùng một cơ chế version/claim đáng tin ở database để xác định **lượt xử lý** và chống stale writer.
4. Trước mỗi side effect quan trọng, kiểm tra/áp dụng fencing/idempotency tại nơi sở hữu dữ liệu.
5. Heartbeat gia hạn Redis lease trong khi công việc còn hợp lệ.
6. Nếu renewal thất bại, ngừng commit không có bảo vệ và chuyển việc còn lại sang recovery.
7. Sau khi hoàn tất, ghi `DONE` có điều kiện theo version, rồi compare-and-delete Redis lock.

Trong mô hình này, **database là nguồn sự thật về kết quả**, còn Redis giúp hạn chế xử lý trùng và tranh chấp. Nếu Redis failover làm hai worker cùng tưởng mình nắm lock, điều kiện ở database quyết định ai thực sự được cập nhật kết quả.

### 15.1. Claim trong database với phiên bản

Ví dụ bảng:

```sql
CREATE TABLE report_jobs (
    report_id       VARCHAR(100) PRIMARY KEY,
    state           VARCHAR(20) NOT NULL,
    generation      BIGINT NOT NULL DEFAULT 0,
    owner_id        VARCHAR(100),
    lease_until     TIMESTAMP,
    result_location TEXT
);
```

Một phương pháp là cấp generation tăng trong một transaction SQL có khóa dòng:

```sql
BEGIN;

SELECT generation, state, lease_until
  FROM report_jobs
 WHERE report_id = :report_id
 FOR UPDATE;

-- Ứng dụng kiểm tra có được phép claim theo trạng thái/lease không.
-- Nếu được, tăng generation và ghi owner mới trong transaction.

UPDATE report_jobs
   SET generation = generation + 1,
       owner_id = :owner_id,
       state = 'RUNNING',
       lease_until = :new_lease_until
 WHERE report_id = :report_id;

COMMIT;
```

Đây là **ý tưởng thuật toán**, không phải đoạn SQL đầy đủ có thể chạy mà không có phần kiểm tra điều kiện. Việc kiểm tra quyền claim phải diễn ra dưới cơ chế cô lập/khóa transaction thích hợp; nếu tùy tiện bỏ bước kiểm tra và luôn tăng generation, nhiều worker vẫn có thể liên tục chiếm quyền.

Khi ghi kết quả:

```sql
UPDATE report_jobs
   SET state = 'DONE',
       result_location = :result_location
 WHERE report_id = :report_id
   AND generation = :generation
   AND owner_id = :owner_id
   AND state = 'RUNNING';
```

Nếu owner cũ cố cập nhật với generation đã lỗi thời, câu lệnh ảnh hưởng `0` hàng. Ứng dụng phải kiểm tra row count và không xem đó là thành công.

Tùy nghiệp vụ, cần kiểm tra cả `lease_until` theo **đồng hồ database** trong transaction và bổ sung ràng buộc trên tài nguyên phụ thuộc. Một SQL row guard chỉ bảo vệ các ghi vào bảng đó, không tự bảo vệ một email đã gửi hoặc một API thanh toán ở hệ thống ngoài.

### 15.2. Vì sao không thể dựa vào Redis lease để đảm bảo thanh toán đúng một lần?

Một số nguyên nhân:

- Hai worker có thể đều xử lý khi master failover.
- Worker cũ có thể chạy lại sau TTL.
- Một HTTP request gửi đi có thể thành công nhưng timeout ở client.
- Unlock có điều kiện bảo vệ **key Redis**, không bảo vệ giao dịch ở đối tác.

Vì thế giao dịch ngoài cần idempotency key được bên nhận tôn trọng và quy trình reconciliation; kết quả nên được lưu ở hệ thống có transaction phù hợp.

## 16. Retry lấy khóa: tránh thundering herd và starvation

Nếu 100 worker cùng xin `lock:invoice:913` và nhận thất bại, không nên tạo vòng lặp vô hạn `SET NX PX` mỗi mili giây.

Một retry policy có thể:

- Đặt **tổng thời gian chờ tối đa** hoặc số lần thử.
- Dùng exponential backoff với jitter (ví dụ tăng từ 50 ms đến trần 1 giây).
- Ngừng thử khi job đã hoàn tất bởi worker khác.
- Dùng cancellation nếu request không còn cần kết quả.
- Không giữ hàng nghìn thread ngủ chờ khóa.

```text
tryAcquire()
    |
    +-- acquired --> chạy critical section
    |
    +-- busy --> backoff + jitter
    |              |
    |              +--> kiểm tra state job, rồi retry nếu cần
    |
    +-- timeout/unknown --> không coi là busy đơn thuần
                           cần đối chiếu trạng thái/TTL
```

**Chưa nhận response của `SET NX PX` không giống như Redis chắc chắn trả nil.** Nếu command thành công nhưng phản hồi mất, ứng dụng có thể đã tạo lock mà không biết. TTL giúp key tự hết hạn; việc retry phải có giới hạn và không mặc định task được phép chạy.

Nếu lease holder crash, worker khác sẽ phải đợi TTL hoặc cơ chế phục hồi; điều đó là đánh đổi liveness. Đặt TTL quá dài làm recovery chậm; TTL quá ngắn làm tăng nguy cơ mất lease khi công việc bình thường bị trễ.

## 17. TTL, expiration và những chi tiết vận hành

### 17.1. Mỗi lần gia hạn đặt lại thời hạn từ hiện tại

`PEXPIRE key 30000` trong script gia hạn đặt TTL mới **30 giây từ lúc lệnh chạy ở Redis**, không cộng thêm 30 giây vào TTL cũ. Nếu muốn bảo đảm hết hạn tuyệt đối của một job sau một thời hạn tối đa, cần lưu **maximum deadline** riêng và không tiếp tục renew sau mốc đó.

### 17.2. Không nên bỏ expiration

`PERSIST lock:invoice:913` hoặc một lệnh `SET key newValue` không kèm `KEEPTTL`/expiration có thể khiến key không còn TTL. Một job crash lúc đó có thể để lại khóa không tự giải phóng.

Nếu có code bên ngoài lock service được phép sửa cùng key, phải kiểm soát chặt key namespace và ACL/ownership API. Một khóa được bảo vệ tốt nên chỉ có một lớp service sở hữu các thao tác tạo/gia hạn/xóa.

### 17.3. Redis key hết hạn không đồng nghĩa callback ngay lúc đó

Redis xử lý expiration theo cơ chế của server; thời điểm key trở nên không còn hợp lệ với các lệnh truy cập không đòi hỏi phải phát một event chính xác tại mili giây hết hạn.

Không dùng Redis keyspace notification như một đồng hồ chính xác để chuyển quyền sở hữu hoặc dừng tác vụ. Notification có thể bị mất và việc listener nhận chậm không thay đổi semantics của TTL.

### 17.4. Time zone không dùng để đo TTL

TTL tính theo khoảng thời gian; logic heartbeat nên dùng `Duration` và đơn vị millis rõ ràng. Không tự dùng giờ local hoặc cron time zone để tính “còn 10 giây” của lease. Time zone hữu ích cho lịch tác vụ nhưng không có vai trò trong tính nguyên tử của lock.

## 18. Kiểm thử hành vi cơ bản với Redis CLI

Các kịch bản sau chỉ nên chạy trên Redis **test** và dùng key riêng `lab:364:lock`.

### Bài 1 — Chỉ một người lấy được khóa

Terminal A:

```redis
SET lab:364:lock owner-A NX PX 30000
```

Terminal B (ngay sau đó):

```redis
SET lab:364:lock owner-B NX PX 30000
```

Kỳ vọng A nhận `OK` và B nhận nil. Sau `30` giây nếu A không renew/release, B có thể lấy khóa ở một lần thử mới.

### Bài 2 — Chỉ token đúng mới gia hạn

Đặt lại key:

```redis
SET lab:364:lock owner-A NX PX 30000
```

Chạy script renew với owner-A:

```redis
EVAL "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2])) else return 0 end" 1 lab:364:lock owner-A 30000
PTTL lab:364:lock
```

Kỳ vọng nhận `1` và TTL trở lại gần 30.000 ms.

Chạy cùng script với owner-B:

```redis
EVAL "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[2])) else return 0 end" 1 lab:364:lock owner-B 30000
```

Kỳ vọng nhận `0`. Token B không được kéo dài khóa của A.

### Bài 3 — Worker cũ không xóa khóa mới

1. A tạo key `lab:364:lock` với token A và TTL ngắn, chẳng hạn 2 giây.
2. Đợi TTL hết hạn và để B lấy key bằng token B.
3. A gọi **compare-and-delete** với token A.
4. Kỳ vọng script trả `0`.
5. `GET lab:364:lock` vẫn trả token B.

Không dùng `DEL` vô điều kiện trong bài này, vì đó chính là thao tác cần chứng minh là nguy hiểm.

### Bài 4 — Gia hạn thất bại và task phải ngừng commit

1. Worker A lấy khóa 10 giây.
2. Mô phỏng worker bị pause quá 10 giây.
3. B lấy khóa mới.
4. A thử gia hạn với token cũ; script trả `0`.
5. A phải đánh dấu lease `LOST`, không tiếp tục commit dữ liệu nghiệp vụ theo niềm tin cũ.

Khi chạy bằng Java, có thể mô phỏng tạm dừng có kiểm soát. Không cố dùng GC gây pause tùy ý trên môi trường production.

## 19. Kiểm thử failover Sentinel/Cluster có kiểm soát

Kiểm thử không chỉ xem key còn tồn tại sau failover. Phải quan sát **hai worker có thể cùng thực hiện side effect hay không**.

### 19.1. Bộ kịch bản

| ID | Tình huống | Điều cần quan sát |
|---|---|---|
| F01 | Hai worker cùng xin khóa lúc Cluster ổn định | Chỉ một `SET NX` thành công trên primary |
| F02 | Worker đang làm, heartbeat gia hạn thành công | PTTL liên tục được đặt lại; owner token không đổi |
| F03 | Gia hạn với token sai | Kết quả `0`; TTL của owner thật không bị kéo dài |
| F04 | Worker A bị pause vượt TTL, B lấy khóa | A không xóa hoặc gia hạn khóa của B |
| F05 | Worker A mất lease nhưng vẫn muốn ghi DB | DB/fencing guard từ chối stale write |
| F06 | Redis timeout khi renew | Worker chuyển sang `UNCERTAIN`; không mặc định vẫn giữ lock |
| F07 | Sentinel failover sau khi A vừa lấy khóa | Khả năng master mới thiếu key; cần phát hiện double ownership |
| F08 | Redis Cluster failover của shard chứa lock key | Kiểm tra chủ slot mới và trạng thái lock |
| F09 | Worker A ghi side effect xong nhưng unlock timeout | Không giả định tác vụ chưa thành công; idempotency giúp retry |
| F10 | Job bị treo nhưng heartbeat vẫn chạy | Kiểm tra max job duration và chính sách dừng |
| F11 | Mất phản hồi SET thành công | Không cho job chạy nếu chưa xác nhận quyền |
| F12 | Ứng dụng restart sau crash | Lock tự hết hạn, job được reconcile từ nguồn dữ liệu bền vững |

### 19.2. Kiểm thử Sentinel

Trên môi trường Sentinel test, dùng:

```bash
redis-cli -h 127.0.0.1 -p 26379 \
  SENTINEL get-master-addr-by-name mymaster
```

Trong lúc A đã giữ lock và đang thực hiện một job được kiểm soát, có thể yêu cầu failover:

```bash
redis-cli -h 127.0.0.1 -p 26379 \
  SENTINEL FAILOVER mymaster
```

Lệnh chỉ dành cho môi trường test; nó tác động vai trò master. Sau failover:

- Hỏi Sentinel lại địa chỉ master.
- Quan sát token và `PTTL` trên master mới.
- Quan sát renewal exception, kết quả `0` và khoảng gián đoạn.
- Cho B thử lấy khóa và đo xem có cùng lúc commit không.
- Kiểm tra ràng buộc fencing/idempotency tại nguồn dữ liệu thực tế.

Vì việc lock write bị mất replication phụ thuộc timing, **một lần failover không tái hiện lỗi** không chứng minh thuật toán chắc chắn an toàn.

### 19.3. Kiểm thử Redis Cluster

Trước tiên tìm slot của key:

```redis
CLUSTER KEYSLOT lab:364:lock
CLUSTER SHARDS
```

Xác định master và replica phục vụ slot đó. Có thể dùng `CLUSTER FAILOVER` trên **replica test** thích hợp để mô phỏng đổi vai trò; không dùng lệnh trên node ngẫu nhiên và không chạy trên production chỉ để làm lab.

Những điều cần xác nhận:

1. Slot của lock key không đổi, nhưng master sở hữu slot có thể thay đổi.
2. Driver Lettuce/Jedis phục hồi connection/topology phù hợp.
3. Worker nhận tín hiệu lỗi/unknown đúng cách.
4. Worker mới có thể thử lấy lock trên master mới.
5. Guard ở database không cho stale owner ghi đè dữ liệu đúng.

Redis Cluster không phải phép thử bảo đảm strong consistency của lock; toàn bộ kịch bản failover phải được đánh giá theo **tác động nghiệp vụ**, không chỉ lệnh Redis trả kết quả gì.

## 20. Metrics, logging và cảnh báo

Mỗi lần lấy/gia hạn/trả khóa nên có ngữ cảnh:

```text
resourceId
workerId / instanceId
acquisitionId (owner token, không log đầy đủ nếu cần giữ bí mật)
fencingVersion (nếu có)
leaseTtlMs
renewalLatencyMs
renewalOutcome
elapsedJobMs
jobId / correlationId
redisTopology
```

Một số metric nên đo:

| Metric | Ý nghĩa |
|---|---|
| `lock.acquire.success` | Tỷ lệ lấy khóa thành công |
| `lock.acquire.busy` | Mức tranh chấp theo resource |
| `lock.acquire.unknown` | Lần lấy khóa không rõ kết quả vì timeout |
| `lock.renew.success` | Heartbeat gia hạn thành công |
| `lock.renew.failure` | Lỗi do token không khớp/key không tồn tại |
| `lock.renew.unknown` | Không nhận phản hồi gia hạn |
| `lock.lease.lost` | Số critical section phải dừng do mất quyền |
| `lock.release.not_owner` | Worker cố release khi không còn là owner |
| `lock.critical_section.duration` | Phân bố thời lượng công việc |
| `lock.fencing.rejected` | Số stale write bị tài nguyên đích từ chối |
| `redis.failover.count` | Tần suất topology thay đổi |

Tên trong bảng là **gợi ý instrumentation**, không phải metric được Spring Data Redis tạo sẵn. Đừng ghi raw token hoặc payload nhạy cảm vào hệ thống log chia sẻ nếu không cần. Có thể log một phần hash của token để đối chiếu mà vẫn hạn chế rò rỉ.

### Cảnh báo vận hành quan trọng

- Gia hạn thất bại tăng đột biến khi Redis failover.
- Lease bị mất trong lúc job đang chạy.
- Có hai instance cùng tuyên bố xử lý một `resourceId`.
- Số lần fencing rejection tăng.
- Critical section thường xuyên lâu hơn TTL dự kiến.
- Một key lock có `PTTL = -1`.
- Scheduler heartbeat chậm hoặc backlog nhiều nhiệm vụ.
- Lock chưa giải phóng nhưng job nguồn đã hoàn tất từ lâu.

Không dựa vào một metric “khóa vẫn còn” để kết luận kết quả giao dịch chính xác; cần metric từ database hoặc dịch vụ chịu tác dụng phụ.

## 21. Những lỗi triển khai phổ biến

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Dùng `SETNX` rồi `EXPIRE` tách rời | Crash giữa hai lệnh làm lock không có TTL | `SET NX PX` |
| Dùng một token cố định cho worker | Lease mới có thể bị nhầm với lease cũ | Sinh token mới cho từng lần acquire |
| `DEL lock` trong `finally` | Worker cũ xóa khóa worker mới | Lua compare-and-delete hoặc `DELEX IFEQ` khi hỗ trợ |
| `PEXPIRE` không kiểm tra token | Gia hạn lock của owner khác | Lua compare-and-PEXPIRE |
| Renewal trả `0` vẫn tiếp tục xử lý | Stale owner tạo side effect | Dừng commit, mark LOST, fencing tại resource |
| Timeout renew được coi là thành công | Có thể làm việc sau expiry | Mark UNCERTAIN, fail closed |
| Heartbeat cứ chạy khi job đã treo | Giữ khóa vô hạn | Max job duration và lifecycle cleanup |
| `Thread.interrupt()` được coi là rollback | External side effect vẫn có thể hoàn tất | Idempotency và resource guard |
| Dùng UUID làm fencing token | UUID không có thứ tự cấp quyền | Monotonic version từ nguồn đủ mạnh |
| Dùng `INCR` trên Redis async failover làm fence tuyệt đối | Counter có thể bị rollback sau promotion | Fencing từ hệ thống đủ nhất quán |
| Nhận `WAIT 1` là lock linearizable | WAIT không phải consensus | Đánh giá fault model và resource-level enforcement |
| Sentinel failover được coi là an toàn tuyệt đối | Replica mới có thể thiếu lock key | Chấp nhận rủi ro hoặc dùng cơ chế mạnh hơn |
| Gắn toàn bộ lock cùng `{all}` trên Cluster | Hot slot/hot master | Hash tag theo đơn vị nghiệp vụ nếu thực sự cần |
| Retry `SET NX` liên tục không backoff | Redis chịu tải tăng, thundering herd | Bounded retry + jitter |
| Không kiểm tra row count của guarded SQL update | Stale write thất bại nhưng ứng dụng vẫn báo thành công | Kiểm tra kết quả và đánh dấu conflict |
| Kiểm tra owner chỉ bằng `GET` trước khi ghi DB | Lock có thể hết hạn ngay sau GET | Enforce version tại DB, không dùng GET như bằng chứng tuyệt đối |

## 22. Khi nào nên chọn công nghệ khác?

Một Redis lease có compare-and-delete/extend thường phù hợp để **giảm xử lý trùng** cho:

- Scheduled job có thể chạy lại an toàn.
- Tác vụ dựng cache hoặc tạo báo cáo có tính idempotent.
- Tác vụ đồng bộ mà kết quả có thể reconciliation sau lỗi.
- Giảm cạnh tranh trên một resource nhưng hệ thống vẫn có business guard khác.

Nếu yêu cầu nghiêm ngặt rằng **không một stale owner nào được phép tạo tác dụng phụ**, nhất là:

- Chuyển tiền, ghi sổ tài chính.
- Cập nhật hàng tồn kho cần tính đúng tuyệt đối.
- Điều khiển thiết bị/cơ sở hạ tầng có side effect không thể hoàn tác.
- Phân công quyền ghi duy nhất trong điều kiện partition/failover phức tạp.

thì không nên chỉ dựa vào Redis TTL và renewal. Cân nhắc:

- SQL transaction và row/version lock cho dữ liệu đã lưu trong RDBMS.
- Một coordination service có semantics lease/lock và fencing phù hợp yêu cầu nhất quán.
- Một cơ chế ghi có điều kiện tại resource đích, idempotency key và dữ liệu trạng thái bền vững.

Không có giải pháp chỉ gồm vài Redis commands mà có thể bảo đảm mọi tính chất đúng đắn của một hệ thống phân tán khi client bị pause, mạng phân vùng và master bị failover.

## 23. Câu hỏi tự kiểm tra

**1. Vì sao `SET lock token NX PX 30000` tốt hơn `SETNX` rồi `EXPIRE`?** Vì tạo key và TTL trong cùng một lệnh, tránh cửa sổ crash khiến khóa không có thời hạn.

**2. Vì sao mỗi lần lấy khóa phải có token mới?** Để phân biệt khóa của lượt xử lý cũ và mới, tránh worker cũ renew/unlock nhầm một lượt được cấp lại.

**3. Gia hạn chỉ bằng `PEXPIRE` có an toàn không?** Không. Worker đã mất quyền có thể gia hạn khóa hiện do worker khác giữ.

**4. Lua compare-and-PEXPIRE trả `0` nghĩa là gì?** Token không còn khớp hoặc key không còn; worker không có quyền gia hạn và phải ngừng coi mình là owner.

**5. Nếu renew timeout nhưng sau đó Redis vẫn có key token cũ thì có thể cứ làm tiếp không?** Không thể mặc nhiên. Phải xét local deadline, thời điểm phản hồi, các lần failover và policy; với side effect nhạy cảm nên fail closed và enforce fencing ở nơi ghi.

**6. Vì sao `DEL` trong `finally` sai?** Worker có thể chạy lại sau expiration và xóa khóa mới của worker khác.

**7. Fencing token khác UUID owner token ở đâu?** Owner token là giá trị ngẫu nhiên để chứng minh quyền trên lock key; fencing token có thứ tự tăng để tài nguyên đích từ chối yêu cầu stale.

**8. Dùng Redis `INCR` làm fencing token đã tuyệt đối an toàn qua failover chưa?** Chưa: replication bất đồng bộ có thể mất lần tăng và làm thứ tự/giá trị token không đáng tin.

**9. Sentinel và Cluster có bảo đảm lock key đã được replicate trước failover không?** Không phải mặc định; có thể có cửa sổ failover gây hai worker đều tưởng mình giữ khóa.

**10. `WAIT` có biến Redis thành strong consistent coordination system không?** Không. Nó cải thiện xác suất replica có bản ghi, không bảo đảm thuật toán lock tuyến tính trong mọi kịch bản.

## 24. Kết luận

Một khóa Redis dùng để điều phối công việc cần được coi là **lease có thể mất**, không phải quyền sở hữu vĩnh viễn. Mẫu cơ bản là `SET key uniqueToken NX PX ttl`; gia hạn bằng **compare-and-PEXPIRE**, trả khóa bằng **compare-and-delete**, luôn dùng token mới cho mỗi lượt lấy. Renewal cần chạy sớm với khoảng dự phòng, có timeout và **fail-closed** khi quyền sở hữu không rõ.

Tuy nhiên, Lua và heartbeat chỉ bảo vệ thao tác lên **lock key** trong điều kiện Redis node thực thi lệnh còn là nguồn trạng thái thích hợp. Chúng không ngăn một JVM bị pause rồi sống lại tiếp tục ghi DB, và không giải quyết cửa sổ **replication bất đồng bộ khi Sentinel/Cluster failover**.

Với tác dụng phụ quan trọng, hãy bảo vệ **ngay tại tài nguyên đích** bằng fencing/version guard, idempotency và transaction phù hợp. Redis lock giúp giảm cạnh tranh và tăng hiệu quả; nguồn dữ liệu nghiệp vụ vẫn phải có cơ chế quyết định tính đúng đắn khi hệ thống trải qua timeout, retry, mất kết nối hoặc failover.

## Tài liệu tham khảo

- [Redis — Distributed Locks](https://redis.io/docs/latest/develop/use/patterns/distributed-locks/): `SET NX PX`, random token, unlock an toàn, Redlock, giới hạn replication và gia hạn khóa.
- [Redis — SET](https://redis.io/docs/latest/commands/set/): `NX`, `PX`, expiration và các tùy chọn conditional update.
- [Redis — PEXPIRE](https://redis.io/docs/latest/commands/pexpire/): thay đổi TTL theo mili giây.
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/): kiểm tra thời gian sống còn lại của key.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): thực thi script Lua trên Redis.
- [Redis — DELEX](https://redis.io/docs/latest/commands/delex/): compare-and-delete native khi phiên bản server hỗ trợ.
- [Redis — WAIT](https://redis.io/docs/latest/commands/wait/): chờ xác nhận replication và giới hạn consistency.
- [Redis — WAITAOF](https://redis.io/docs/latest/commands/waitaof/): chờ AOF persistence trong các phiên bản hỗ trợ.
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/): failover, master discovery và replication.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): slot ownership, replica promotion và mô hình consistency của Cluster.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): thực thi thao tác Redis với template.
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `DefaultRedisScript` và Lua qua `RedisTemplate.execute`.
- [Spring Integration — RedisLockRegistry](https://docs.spring.io/spring-integration/reference/redis.html): lock registry, TTL và gia hạn theo scheduler ở những phiên bản phù hợp.
