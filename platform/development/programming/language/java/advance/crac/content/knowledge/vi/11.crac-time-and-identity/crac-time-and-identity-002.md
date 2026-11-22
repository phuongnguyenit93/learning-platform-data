# Đồng hồ thời gian thực, nanoTime và cách tính lại thời lượng

Ứng dụng Java thường cần biết hai loại thời gian khác nhau: **thời điểm hiện tại trên lịch** và **khoảng thời gian đã trôi qua**. Hai khái niệm này có vẻ gần nhau nhưng JVM cung cấp các nguồn đồng hồ với mục đích khác nhau:

- Đồng hồ thời gian thực, thường truy cập qua Instant.now() hoặc System.currentTimeMillis(), cho biết thời điểm theo epoch. Nó phù hợp với timestamp, thời hạn nghiệp vụ và lịch hẹn.
- Đồng hồ đơn điệu, truy cập qua System.nanoTime(), phù hợp để đo thời lượng và timeout trong một tiến trình đang chạy. Giá trị của nó không phải timestamp và không thể chuyển thành ngày giờ.

Sự phân biệt này quan trọng với CRaC (Coordinated Restore at Checkpoint). Khi tiến trình được checkpoint, ứng dụng tạm dừng nhưng thời gian bên ngoài vẫn tiếp tục trôi qua. Một deadline, token, cache TTL hoặc lịch chạy có thể đã hết hạn khi tiến trình restore. Nếu giữ nguyên một bộ đếm hoặc timer được tạo trước checkpoint mà không tính lại, ứng dụng có thể xử lý công việc quá muộn, chạy tác vụ sớm hoặc coi một credential đã hết hạn là còn hiệu lực.

Bài này giải thích cách chọn đồng hồ, đo elapsed time bằng nanoTime và tính lại thời lượng sau restore theo chính sách thời gian của ứng dụng.

## 1. Hai khái niệm thời gian cần phân biệt

### 1.1. Thời gian thực (wall-clock time)

Wall-clock time biểu diễn một thời điểm trên dòng thời gian dân sự. Trong Java, kiểu phù hợp để biểu diễn thời điểm là Instant.

Ví dụ:

~~~java
import java.time.Instant;

Instant now = Instant.now();
System.out.println(now);
~~~

Instant biểu diễn một thời điểm theo UTC trên timeline, thường được dùng cho:

- Thời điểm tạo bản ghi.
- Thời điểm nhận request.
- Thời điểm hết hạn của token.
- Deadline nghiệp vụ.
- Thời điểm checkpoint và restore.
- Dấu thời gian cần lưu vào database hoặc event log.

Có thể lấy millisecond epoch bằng:

~~~java
long epochMillis = System.currentTimeMillis();
~~~

Giá trị này tính số millisecond từ mốc Unix epoch (1970-01-01T00:00:00Z). Nó có ý nghĩa như một timestamp, nhưng độ phân giải và độ chính xác thực tế phụ thuộc hệ điều hành và clock source.

Wall clock có thể được điều chỉnh. Ví dụ, NTP đồng bộ lại đồng hồ, quản trị viên thay đổi giờ hệ thống, VM được điều chỉnh thời gian hoặc clock bị nhảy do cấu hình sai. Vì vậy, hai lần gọi currentTimeMillis() có thể không tạo ra một khoảng chênh lệch phản ánh chính xác thời gian thực sự đã trôi qua; giá trị sau thậm chí có thể nhỏ hơn giá trị trước.

### 1.2. Thời gian đơn điệu (monotonic time)

System.nanoTime() cung cấp một nguồn thời gian có độ phân giải cao để đo khoảng thời gian đã trôi qua:

~~~java
long started = System.nanoTime();

// Thực hiện công việc cần đo.

long elapsedNanos = System.nanoTime() - started;
~~~

Giá trị nanoTime có một mốc gốc tùy ý. Không được hiểu nó là số nanosecond từ năm 1970 hoặc chuyển nó thành ngày giờ. Chỉ hiệu số giữa hai lần đọc trong cùng một miền đồng hồ mới có ý nghĩa.

Đồng hồ đơn điệu được thiết kế để đo thời lượng mà không bị ảnh hưởng bởi việc chỉnh wall clock như đồng bộ NTP hoặc đổi giờ hệ thống. Độ chính xác thực tế không đồng nghĩa độ phân giải trả về: API trả đơn vị nanosecond nhưng phần cứng/hệ điều hành có thể có độ phân giải thấp hơn.

### 1.3. So sánh nhanh

| Tiêu chí | Wall clock: Instant/currentTimeMillis | Monotonic: nanoTime |
|---|---|---|
| Ý nghĩa | Thời điểm trên timeline | Bộ đếm thời gian đơn điệu |
| Mốc gốc | Unix epoch với Instant/currentTimeMillis | Mốc tùy ý |
| Dùng để | Timestamp, ngày hết hạn, deadline nghiệp vụ | Elapsed time, timeout trong tiến trình |
| Có thể nhảy lùi/tiến do chỉnh giờ | Có | Không bị ảnh hưởng bởi chỉnh wall clock |
| Chuyển thành ngày giờ | Có, với Instant | Không |
| Lưu để so sánh sau process restart | Có thể lưu Instant | Không nên lưu nanoTime |
| Phù hợp với checkpoint/restore | Dùng để tính thời điểm và hạn còn lại | Dùng cho đo thời lượng trong một khoảng chạy có kiểm soát |

Không có một nguồn đồng hồ phù hợp cho mọi trường hợp. Cần xác định câu hỏi của ứng dụng là “bây giờ là lúc nào?” hay “đã trôi qua bao lâu?”.

## 2. Dùng nanoTime đúng cách

### 2.1. Đo thời lượng bằng phép trừ

Cách thông dụng:

~~~java
long start = System.nanoTime();

doWork();

long elapsed = System.nanoTime() - start;

System.out.println(
        "Elapsed: " + elapsed + " ns");
~~~

Đổi đơn vị bằng TimeUnit:

~~~java
import java.util.concurrent.TimeUnit;

long elapsedNanos = System.nanoTime() - start;
long elapsedMillis =
        TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

Hoặc dùng Duration để biểu diễn kết quả:

~~~java
import java.time.Duration;

long start = System.nanoTime();

doWork();

Duration elapsed =
        Duration.ofNanos(System.nanoTime() - start);

System.out.println(elapsed.toMillis() + " ms");
~~~

Duration ở đây chỉ là cách đóng gói khoảng thời gian đã đo. Nó không biến nanoTime thành timestamp.

### 2.2. Kiểm tra timeout bằng hiệu số

Giả sử một thao tác có timeout 2 giây:

~~~java
long timeoutNanos =
        TimeUnit.SECONDS.toNanos(2);

long started = System.nanoTime();

while (!operationCompleted()) {
    long elapsed = System.nanoTime() - started;

    if (elapsed >= timeoutNanos) {
        throw new IllegalStateException("Operation timed out");
    }

    doSmallUnitOfWork();
}
~~~

Nên dùng phép trừ giữa hai giá trị nanoTime thay vì cộng timeout vào mốc bắt đầu rồi so sánh:

~~~java
// Không nên dùng cách cộng mốc để kiểm tra:
if (System.nanoTime() >= started + timeoutNanos) {
    // timeout
}
~~~

Phép cộng có thể overflow. Cách so sánh hiệu số được Java khuyến nghị cho khoảng thời gian nhỏ hơn khoảng 2^63 nanosecond, tương đương xấp xỉ 292 năm.

### 2.3. Không so sánh nanoTime với một mốc cố định

Không viết logic kiểu:

~~~java
if (System.nanoTime() > 1_000_000_000L) {
    // ...
}
~~~

Giá trị nanoTime không có mốc gốc cố định và có thể âm. Chỉ so sánh hiệu số giữa hai lần đọc có liên quan.

Không lưu nanoTime vào database với ý nghĩa “thời điểm bắt đầu”, không gửi nó qua API và không dùng nó làm timestamp trong log. Nếu cần log timestamp, dùng Instant; nếu cần log elapsed, ghi số duration cùng đơn vị.

## 3. Điều gì xảy ra với thời gian khi CRaC checkpoint?

Checkpoint lưu trạng thái tiến trình và làm tiến trình ngừng thực thi trong một khoảng thời gian. Trong lúc đó:

- JVM không xử lý request hoặc chạy Java code bình thường.
- Host và các dịch vụ bên ngoài vẫn có thể tiếp tục chạy.
- Database vẫn xử lý session và timeout.
- Token, lease, certificate hoặc cache entry có thể hết hạn.
- Một deadline nghiệp vụ vẫn có thể đến hạn.
- Scheduler trong tiến trình không thể thực thi task trong khi tiến trình bị dừng.

Vì vậy, thời lượng từ góc nhìn ứng dụng có thể được định nghĩa theo hai cách:

1. **Thời gian thực đã trôi qua**, bao gồm cả khoảng tiến trình bị checkpoint.
2. **Thời gian CPU/hoạt động của ứng dụng**, không tính khoảng tiến trình bị dừng.

Hai cách định nghĩa này phục vụ những mục tiêu khác nhau.

### 3.1. Đồng hồ đơn điệu trên Linux và khoảng checkpoint

Trên Linux, CLOCK_MONOTONIC thường là nguồn mà JVM dùng để triển khai System.nanoTime(). Clock này tăng đều khi hệ thống đang chạy và không bị chỉnh bởi thay đổi wall clock. Nó không tính thời gian hệ thống bị suspend. CLOCK_BOOTTIME có semantics khác: nó bao gồm cả thời gian hệ thống suspend.

Checkpoint một tiến trình bằng CRIU không giống suspend toàn bộ máy. Trong trường hợp host tiếp tục hoạt động, đồng hồ monotonic của host thông thường vẫn tiếp tục tiến trong khi tiến trình bị đóng băng. Tuy nhiên, chi tiết nguồn clock, cách restore timer và hành vi có thể khác theo OS, JDK build, CRIU và nền tảng triển khai.

Do đó, không nên xây dựng logic nghiệp vụ dựa trên giả định rằng một giá trị nanoTime được lưu trước checkpoint chắc chắn sẽ có semantics giống nhau trên mọi môi trường sau restore. Hãy kiểm tra hành vi của đúng tổ hợp runtime nếu cần đo khoảng thời gian bao gồm thời gian checkpoint.

### 3.2. Quyết định khoảng dừng có được tính vào duration hay không

| Nhu cầu | Có tính thời gian checkpoint? | Cách biểu diễn |
|---|---|---|
| Đo thời gian xử lý một request | Thường không; request nên được drain trước checkpoint | Đo nanoTime trong lúc request thực sự chạy |
| Đo tổng thời gian một quy trình nghiệp vụ | Thường có | Lưu startedAt/deadline bằng Instant |
| Timeout cho một thao tác đang chạy | Tùy policy; tốt nhất không checkpoint khi thao tác còn dở | Drain/cancel trước checkpoint hoặc lưu deadline tuyệt đối |
| TTL cache | Có | Lưu expiresAt bằng Instant hoặc dùng TTL từ cache server |
| Thời hạn token/credential | Có | Dùng expiresAt từ issuer hoặc nguồn xác thực |
| Benchmark CPU/đo latency | Không nên tính khoảng tiến trình bị dừng vào thời gian chạy | Dừng phép đo trước checkpoint, bắt đầu phép đo mới sau restore |

Trước khi viết code, hãy xác định rõ khoảng checkpoint có được tính là thời gian đã trôi qua trong nghiệp vụ hay không.

## 4. Lưu deadline bằng Instant, không lưu nanoTime

Nếu một deadline cần tồn tại qua checkpoint, hãy lưu một thời điểm tuyệt đối:

~~~java
import java.time.Instant;

Instant expiresAt = Instant.now().plusSeconds(300);
~~~

Khi cần biết thời gian còn lại:

~~~java
import java.time.Duration;
import java.time.Instant;

Duration remaining =
        Duration.between(Instant.now(), expiresAt);

if (remaining.isNegative() || remaining.isZero()) {
    expire();
} else {
    continueWork(remaining);
}
~~~

Cách này cho phép tính lại thời gian còn lại sau restore. Nếu checkpoint kéo dài 10 phút trong khi deadline chỉ còn 5 phút, thời gian còn lại sau restore sẽ âm và ứng dụng có thể xử lý trạng thái expired.

### 4.1. Tạo một kiểu deadline có thể kiểm thử

Không gọi Instant.now() rải rác trong logic nghiệp vụ. Inject Clock để có thể kiểm thử thời gian:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class Deadline {

    private final Instant expiresAt;

    public Deadline(Instant expiresAt) {
        this.expiresAt = expiresAt;
    }

    public static Deadline after(
            Clock clock,
            Duration duration) {
        return new Deadline(clock.instant().plus(duration));
    }

    public Instant expiresAt() {
        return expiresAt;
    }

    public Duration remaining(Clock clock) {
        Duration remaining =
                Duration.between(clock.instant(), expiresAt);

        return remaining.isNegative()
                ? Duration.ZERO
                : remaining;
    }

    public boolean isExpired(Clock clock) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

Sử dụng:

~~~java
Clock clock = Clock.systemUTC();

Deadline deadline =
        Deadline.after(clock, Duration.ofMinutes(5));

Duration remaining = deadline.remaining(clock);
~~~

Có thể lưu expiresAt vào database hoặc cấu trúc dữ liệu được ứng dụng checkpoint giữ lại. Khi restore, dùng Clock hiện tại để tính lại remaining.

### 4.2. Deadline tuyệt đối và thay đổi wall clock

Instant giải quyết việc lưu một thời điểm qua checkpoint/process restart, nhưng wall clock có thể bị chỉnh. Nếu đồng hồ host bị nhảy tiến, deadline có thể bị coi là hết hạn sớm; nếu bị nhảy lùi, thời hạn có thể kéo dài hơn dự kiến.

Với deadline cần độ tin cậy cao, hãy dùng một nguồn thời gian có thẩm quyền phù hợp với nghiệp vụ, ví dụ:

- Thời hạn do issuer của token cung cấp.
- Expiration/lease do database hoặc dịch vụ điều phối quản lý.
- Server time của hệ thống sở hữu dữ liệu.
- Một time service đã được đồng bộ và có policy xử lý clock skew.

Đừng tự sửa timestamp nhận từ hệ thống khác bằng timezone của máy. Instant đã là thời điểm UTC; timezone chỉ được áp dụng khi hiển thị hoặc tính lịch dân sự.

## 5. Tính lại thời gian còn lại sau restore

Có hai cách phổ biến, tùy dữ liệu cần lưu.

### 5.1. Lưu deadline tuyệt đối

Đây là cách đơn giản khi nghiệp vụ đã có thời điểm hết hạn:

~~~java
Instant expiresAt = ...; // Được lưu cùng trạng thái ứng dụng.

@Override
public void afterRestore(Context<? extends Resource> context) {
    Duration remaining =
            Duration.between(Instant.now(), expiresAt);

    if (remaining.isNegative() || remaining.isZero()) {
        handleExpired();
    } else {
        scheduleWith(remaining);
    }
}
~~~

Ưu điểm:

- Không cần lưu một bộ đếm nanoTime.
- Khoảng checkpoint tự được tính vào thời gian còn lại.
- Có thể lưu deadline trong database hoặc message.
- Dễ kiểm thử với Clock cố định.

Hạn chế: phụ thuộc wall clock và nguồn thời gian hiện tại. Nếu giờ máy không đáng tin, deadline cần được kiểm tra với nguồn thời gian có thẩm quyền.

### 5.2. Lưu remaining trước checkpoint và trừ thời gian đã dừng

Có trường hợp ứng dụng muốn giữ một duration còn lại, ví dụ thời gian cho phép của một workflow. Trước checkpoint, lưu remaining và thời điểm bắt đầu checkpoint:

~~~java
Instant checkpointAt = clock.instant();
Duration remainingAtCheckpoint = currentRemaining;
~~~

Sau restore:

~~~java
Duration paused =
        Duration.between(checkpointAt, clock.instant());

Duration remaining =
        remainingAtCheckpoint.minus(paused);

if (remaining.isNegative()) {
    remaining = Duration.ZERO;
}
~~~

Ví dụ:

| Thời điểm | Giá trị |
|---|---:|
| Trước checkpoint | Còn 8 phút |
| Thời gian tiến trình dừng | 3 phút |
| Sau restore | Còn 5 phút |

Cách này hữu ích khi logic nghiệp vụ lưu duration thay vì deadline. Tuy nhiên, nó vẫn dùng wall clock để tính khoảng dừng. Nếu wall clock nhảy lùi hoặc tiến trong lúc checkpoint, kết quả có thể sai. Với deadline có sẵn, lưu expiresAt thường dễ hiểu hơn.

### 5.3. Khi muốn loại trừ thời gian checkpoint

Nếu mục tiêu là đo thời gian ứng dụng thực sự hoạt động, không tính thời gian checkpoint, hãy dừng phép đo trước checkpoint và bắt đầu một đoạn đo mới sau restore:

~~~java
private long activeSegmentStartedAt;

public void startSegment() {
    activeSegmentStartedAt = System.nanoTime();
}

public Duration finishSegment() {
    long elapsed =
            System.nanoTime() - activeSegmentStartedAt;

    return Duration.ofNanos(elapsed);
}

@Override
public void beforeCheckpoint(Context<? extends Resource> context) {
    accumulatedActiveTime =
            accumulatedActiveTime.plus(finishSegment());
}

@Override
public void afterRestore(Context<? extends Resource> context) {
    startSegment();
}
~~~

Ví dụ trên minh họa cách tách các đoạn đo. Trong implementation thực tế, cần bảo vệ accumulatedActiveTime bằng lock hoặc cơ chế đồng bộ thích hợp và không gọi finishSegment() nếu chưa có segment đang chạy.

Kết quả là tổng thời gian hoạt động được cộng từ các đoạn trước và sau checkpoint; thời gian tiến trình bị dừng không nằm trong phép đo.

## 6. Tính lại timeout và ScheduledExecutorService

ScheduledExecutorService thường nhận một delay tương đối:

~~~java
scheduler.schedule(task, 30, TimeUnit.SECONDS);
~~~

Delay này phù hợp trong một khoảng chạy liên tục. Khi checkpoint, thread scheduler không thể chạy task. Sau restore, không nên mặc định task sẽ chạy đúng thời điểm nghiệp vụ mong muốn nếu nó phụ thuộc vào thời gian còn lại trước checkpoint.

### 6.1. Dùng deadline làm nguồn sự thật

Thay vì chỉ giữ một delay 30 giây, hãy giữ deadline:

~~~java
Instant runAt = clock.instant().plusSeconds(30);
~~~

Trước checkpoint, dừng scheduler và giữ runAt. Sau restore, tính lại:

~~~java
Duration delay =
        Duration.between(clock.instant(), runAt);

if (delay.isNegative()) {
    delay = Duration.ZERO;
}

scheduler.schedule(
        task,
        delay.toMillis(),
        TimeUnit.MILLISECONDS);
~~~

Nếu thời gian checkpoint dài hơn 30 giây, task được lên lịch với delay bằng 0. Ứng dụng vẫn cần quyết định task hết hạn phải chạy ngay, bỏ qua hay được gộp với lần chạy kế tiếp.

### 6.2. Resource quản lý scheduler

Một skeleton CRaC Resource:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public final class DeadlineScheduler implements Resource {

    private final Clock clock;
    private final Runnable task;

    private Instant nextRunAt;
    private ScheduledExecutorService scheduler;
    private ScheduledFuture<?> scheduled;

    public DeadlineScheduler(Clock clock, Runnable task) {
        this.clock = clock;
        this.task = task;

        Core.getGlobalContext().register(this);

        startScheduler();
    }

    public synchronized void setNextRunAt(Instant nextRunAt) {
        this.nextRunAt = nextRunAt;
        reschedule();
    }

    private synchronized void startScheduler() {
        scheduler = Executors.newSingleThreadScheduledExecutor();
        reschedule();
    }

    private synchronized void reschedule() {
        if (scheduler == null || nextRunAt == null) {
            return;
        }

        if (scheduled != null) {
            scheduled.cancel(false);
            scheduled = null;
        }

        Duration delay =
                Duration.between(clock.instant(), nextRunAt);

        long delayMillis =
                Math.max(0L, delay.toMillis());

        scheduled = scheduler.schedule(
                task,
                delayMillis,
                TimeUnit.MILLISECONDS);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) {
        if (scheduler != null) {
            if (scheduled != null) {
                scheduled.cancel(false);
                scheduled = null;
            }
            scheduler.shutdownNow();
            scheduler = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) {
        startScheduler();
    }
}
~~~

Đây là skeleton để minh họa cách lưu thời điểm chạy và tạo scheduler mới. Ứng dụng thực tế cần bổ sung:

- Hủy ScheduledFuture cũ khi reschedule để không tạo nhiều bản task.
- Đảm bảo task không chạy đồng thời với callback đang đóng scheduler.
- Xử lý exception của task và cập nhật nextRunAt sau khi hoàn tất.
- Quyết định task đã quá hạn chạy ngay hay bỏ qua.
- Chọn chính sách shutdown/awaitTermination thay vì luôn hủy ngay.
- Xử lý trường hợp callback restore được gọi nhưng dependency của task chưa sẵn sàng.

Với công việc định kỳ như báo cáo hàng ngày, nên tính lần chạy kế tiếp theo lịch và ZoneId thay vì cộng một số giây cố định vào thời điểm trước đó.

## 7. TTL, token, lease và cache sau restore

Nhiều dữ liệu có thời hạn tồn tại. Nếu chỉ lưu “còn 60 giây” bằng nanoTime hoặc một bộ đếm trong RAM, ứng dụng có thể giữ dữ liệu quá hạn sau checkpoint.

### 7.1. Cache TTL

Một cache entry nên có expiresAt:

~~~java
record CacheEntry<T>(T value, Instant expiresAt) {
    boolean isExpired(Clock clock) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

Khi đọc cache sau restore, kiểm tra expiresAt trước khi trả dữ liệu. Không chỉ dựa vào một scheduled eviction task, vì task có thể đã không chạy trong lúc tiến trình checkpoint.

Nếu cache được cung cấp bởi Redis hoặc một cache server khác có TTL phía server, hãy ưu tiên để hệ thống đó quản lý expiration. Khi ứng dụng restore, cache server đã tự tính thời gian hết hạn theo đồng hồ của nó.

### 7.2. Token và credential

Token thường có claim expiration hoặc trường expires_at. Sau restore, kiểm tra thời hạn trước khi sử dụng:

~~~java
if (!clock.instant().isBefore(token.expiresAt())) {
    tokenProvider.refresh();
}
~~~

Không dùng nanoTime để biểu diễn thời hạn token. Thời hạn do issuer cấp thường là thời điểm tuyệt đối và cần được so sánh với một nguồn wall clock có kiểm soát clock skew.

Nếu refresh token cũng hết hạn hoặc bị thu hồi trong thời gian checkpoint, ứng dụng cần xử lý việc xác thực lại theo policy bảo mật. Không giả định credential còn hợp lệ chỉ vì object token vẫn tồn tại trong heap.

### 7.3. Distributed lease và lock

Lease phân tán có thể được cấp bởi database, coordination service hoặc hệ thống lock. Trong thời gian ứng dụng checkpoint, lease có thể hết hạn và được cấp cho instance khác.

Sau restore:

- Không tiếp tục dùng lease cũ chỉ vì object lease còn tồn tại.
- Kiểm tra lease với hệ thống sở hữu lease.
- Gia hạn hoặc acquire lại theo protocol.
- Xác minh fencing token/version trước khi ghi dữ liệu.
- Không giả định instance vẫn là owner sau một khoảng dừng dài.

Với distributed lock, fencing token thường an toàn hơn việc chỉ so sánh timestamp ở client. Hệ thống lưu dữ liệu cần từ chối thao tác của owner cũ khi token của owner mới đã cao hơn.

### 7.4. Rate limiter và token bucket

Token bucket thường cần lưu thời điểm refill lần cuối. Nếu dùng nanoTime rồi giữ giá trị đó qua checkpoint, logic refill sau restore có thể không đúng với ý nghĩa mong muốn.

Có thể lưu lastRefillAt bằng Instant và tính elapsed sau restore, nhưng phải quyết định có cho phép bucket tích lũy token trong thời gian checkpoint hay không. Nếu không muốn một instance được cấp nhiều token sau khi tạm dừng, hãy giới hạn lượng refill hoặc đồng bộ state với rate limiter dùng chung.

## 8. Wall clock bị chỉnh và cách chống sai lệch

Wall clock là nguồn cần thiết cho timestamp và deadline qua checkpoint, nhưng có thể thay đổi.

Ví dụ:

~~~text
12:00:00  Lưu expiresAt = 12:05:00
12:02:00  Checkpoint
12:04:00  Restore
12:04:00  Còn khoảng 1 phút

Nếu đồng hồ bị chỉnh:
12:04:00 → 11:55:00
Ứng dụng có thể tính còn 10 phút

Hoặc:
12:04:00 → 12:10:00
Ứng dụng có thể coi deadline đã hết hạn
~~~

Các biện pháp phù hợp:

- Dùng NTP hoặc cơ chế đồng bộ thời gian của nền tảng.
- Dùng UTC Instant để lưu timestamp, không lưu giờ địa phương thiếu timezone.
- Với expiration có tính bảo mật, dựa vào thời hạn do issuer hoặc server authoritative cung cấp.
- Với lease và lock phân tán, để hệ thống sở hữu lease quyết định trạng thái.
- Với logic nhạy cảm clock skew, đặt ngưỡng sai lệch và xử lý trường hợp thời gian không đáng tin.
- Không dùng nanoTime thay thế wall clock cho deadline xuyên qua process hoặc host.

Timezone và daylight saving time là vấn đề hiển thị/lịch dân sự, không phải cách sửa wall clock. Nếu cần lịch như “9 giờ sáng theo giờ Việt Nam”, dùng ZonedDateTime và ZoneId:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZonedDateTime localSchedule =
        ZonedDateTime.now(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Khi lưu một thời điểm đã xác định, lưu Instant. Khi lưu một quy tắc lịch lặp theo giờ địa phương, lưu LocalTime/ZoneId hoặc cấu trúc lịch tương ứng để tính lần chạy tiếp theo đúng quy tắc DST.

## 9. Đo hiệu năng qua checkpoint

Đo latency hoặc benchmark cần tách rõ thời gian thực thi của code và thời gian tiến trình bị dừng.

### 9.1. Đo một đoạn xử lý

~~~java
long started = System.nanoTime();

handleRequest();

long elapsed = System.nanoTime() - started;
recordLatency(elapsed);
~~~

Đoạn này chỉ có ý nghĩa cho một lần xử lý trong cùng một đoạn thực thi. Nếu request đang chạy khi checkpoint, tốt nhất drain hoặc hoàn tất request trước checkpoint thay vì để một phép đo dở dang tiếp tục sau restore.

### 9.2. Đo thời gian startup đến READY

Nếu muốn đo từ lúc process bắt đầu đến lúc ứng dụng READY, có thể dùng Instant hoặc wall-clock timestamp. Nếu muốn đo thời gian startup code thực sự chạy và loại trừ thời gian tiến trình bị checkpoint, hãy cộng các segment nanoTime riêng.

Hai phép đo trả lời hai câu hỏi khác nhau:

| Chỉ số | Ý nghĩa |
|---|---|
| Wall-clock startup duration | Từ lúc bắt đầu đến lúc READY theo thời gian thực |
| Active startup duration | Tổng thời gian ứng dụng thực sự chạy startup code |
| Restore-to-ready duration | Từ lúc restore bắt đầu đến lúc readiness thành công |
| Checkpoint-to-restore duration | Khoảng thời gian bên ngoài giữa checkpoint và restore |

Khi báo cáo hiệu năng CRaC, nên ghi rõ đang đo chỉ số nào. Nếu chỉ ghi “startup 200 ms” mà không nói có tính thời gian checkpoint hay không, kết quả khó so sánh.

## 10. Kiểm thử thời gian mà không cần chờ thật

Java Clock cho phép tách logic thời gian khỏi system clock. Có thể dùng Clock.fixed để kiểm thử deadline:

~~~java
import java.time.Duration;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-01T10:00:00Z"),
        ZoneOffset.UTC);

Deadline deadline =
        Deadline.after(fixedClock, Duration.ofMinutes(5));

System.out.println(deadline.remaining(fixedClock)); // PT5M
~~~

Để mô phỏng restore sau 7 phút, tạo clock mới với thời điểm tương ứng:

~~~java
Clock restoredClock = Clock.fixed(
        Instant.parse("2026-01-01T10:07:00Z"),
        ZoneOffset.UTC);

System.out.println(deadline.remaining(restoredClock)); // PT0S
System.out.println(deadline.isExpired(restoredClock));  // true
~~~

Cách này giúp kiểm tra:

- Deadline còn hạn hay đã hết hạn.
- TTL cache sau khoảng checkpoint.
- Token hết hạn trong lúc tiến trình dừng.
- Scheduler cần chạy ngay hay chờ.
- Wall clock nhảy tiến hoặc lùi.
- Chính sách xử lý khi remaining duration âm.

Với logic nanoTime, tạo một abstraction nhỏ cho monotonic ticker để test có thể tăng thời gian có kiểm soát. Không cố gắng dùng Clock.fixed để giả lập nanoTime vì hai API biểu diễn hai loại đồng hồ khác nhau.

## 11. Các lỗi thường gặp khi xử lý thời gian trong CRaC

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Lưu nanoTime vào checkpoint làm deadline tuyệt đối | Giá trị không có ý nghĩa như timestamp | Lưu Instant/deadline hoặc remaining duration với policy rõ ràng |
| Dùng currentTimeMillis để benchmark latency ngắn | Kết quả bị ảnh hưởng bởi độ phân giải và clock adjustment | Dùng nanoTime |
| Giữ ScheduledFuture cũ và tin task sẽ chạy đúng giờ | Task có thể trễ hoặc trạng thái scheduler không phù hợp sau restore | Lưu deadline và tạo lịch mới sau restore |
| Không kiểm tra token sau restore | Request có thể dùng credential đã hết hạn | Kiểm tra expiresAt và refresh |
| Coi lease cũ vẫn hợp lệ | Hai instance có thể cùng nghĩ mình sở hữu tài nguyên | Reacquire/renew và kiểm tra fencing token |
| Tính duration từ wall clock mà không xét clock skew | Thời lượng âm hoặc quá lớn | Dùng monotonic cho elapsed trong process; authoritative clock cho deadline |
| Cộng timeout vào nanoTime rồi so sánh | Có nguy cơ overflow | So sánh hiệu số |
| Dùng LocalDateTime để lưu thời điểm toàn cục | Không xác định được instant nếu thiếu timezone | Lưu Instant hoặc OffsetDateTime |
| Để timer chạy trong khi callback đang shutdown | Race condition hoặc task truy cập resource đã đóng | Dừng nhận task, cancel và đồng bộ lifecycle |

## 12. Quy trình thiết kế thời gian cho ứng dụng CRaC

Khi một thành phần dùng timeout, deadline hoặc timer, hãy làm rõ các bước sau:

1. Xác định đây là thời điểm tuyệt đối hay khoảng thời gian đã trôi qua.
2. Nếu là timestamp/deadline, biểu diễn bằng Instant và lưu cùng trạng thái cần checkpoint.
3. Nếu là elapsed time trong một đoạn thực thi, đo bằng System.nanoTime() và dùng phép trừ.
4. Quyết định thời gian tiến trình bị checkpoint có được tính vào nghiệp vụ hay không.
5. Trước checkpoint, dừng hoặc drain timer/task đang sử dụng resource sắp đóng.
6. Ghi lại deadline hoặc remaining duration theo policy đã chọn.
7. Sau restore, tính lại remaining từ nguồn thời gian phù hợp.
8. Kiểm tra token, lease, cache và credential có thể hết hạn trong lúc dừng.
9. Tạo lại scheduler hoặc timer cần thiết.
10. Chỉ mở traffic sau khi dependency và trạng thái thời gian đã được xác nhận.

Với deadline nghiệp vụ, ưu tiên lưu thời điểm hết hạn tuyệt đối. Với timeout cục bộ trong một lần xử lý, dùng nanoTime. Với đo hiệu năng qua nhiều giai đoạn chạy, cộng các segment monotonic và loại trừ khoảng checkpoint nếu mục tiêu là đo thời gian hoạt động. Với lease hoặc expiration do hệ thống bên ngoài quản lý, xác nhận lại trạng thái với chính hệ thống đó sau restore.

Khi tách rõ wall clock và monotonic clock, ứng dụng tránh được việc dùng một giá trị thời gian sai mục đích. CRaC có thể khôi phục trạng thái bộ nhớ, nhưng không làm cho deadline nghiệp vụ, session database, token hoặc lease bên ngoài tự động còn hiệu lực. Những giá trị phụ thuộc thời gian cần được tính lại hoặc xác nhận lại trước khi ứng dụng tiếp tục công việc.

