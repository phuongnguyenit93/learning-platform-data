# Khoảng thời gian tạm dừng và dữ liệu thời gian được lưu trong ảnh

Khi một tiến trình Java được checkpoint bằng CRaC, trạng thái bộ nhớ của tiến trình được lưu để có thể khôi phục về sau. Những giá trị thời gian mà ứng dụng đã đặt trong object hoặc field cũng là một phần của trạng thái đó. Tuy nhiên, **thời gian của thế giới bên ngoài không bị đóng băng cùng heap**. Trong lúc tiến trình tạm dừng, đồng hồ thực vẫn tiếp tục chạy, token có thể hết hạn, deadline có thể trôi qua và lịch chạy có thể trở nên quá hạn.

Điều này tạo ra một khác biệt quan trọng giữa hai thứ:

- **Dữ liệu thời gian đã được lưu trong checkpoint image:** timestamp, deadline, TTL, `Instant`, `Date`, `LocalDateTime`, bộ đếm hoặc trạng thái timer mà ứng dụng đã ghi vào bộ nhớ.
- **Nguồn thời gian được đọc khi tiến trình hoạt động:** wall clock qua `System.currentTimeMillis()` hoặc `Instant.now()`, và nguồn đo thời gian trôi qua qua `System.nanoTime()`.

Khi restore, các giá trị object đã lưu được phục hồi như trạng thái bộ nhớ. Những lần đọc đồng hồ mới phản ánh nguồn thời gian của môi trường tại thời điểm restore. Vì vậy, một deadline đã tính trước checkpoint có thể đã hết hạn, trong khi một timer hoặc bộ đếm được lưu trong heap có thể không phản ánh đúng khoảng thời gian tiến trình đã ngừng hoạt động.

## 1. Điều gì được lưu trong checkpoint image?

Hãy xem checkpoint image như một ảnh chụp trạng thái tiến trình tại một thời điểm. Nếu ứng dụng đang giữ các giá trị sau trong heap, chúng có thể được khôi phục cùng tiến trình:

```java
Instant createdAt = Instant.now();
Date legacyCreatedAt = new Date();
LocalDateTime localStart = LocalDateTime.now();
long deadlineEpochMillis = System.currentTimeMillis() + 30_000;
long startedNanos = System.nanoTime();
Duration retryDelay = Duration.ofSeconds(10);
```

Các giá trị trên là dữ liệu thông thường trong bộ nhớ. Sau restore:

- `createdAt` vẫn biểu diễn thời điểm đã được tạo trước checkpoint.
- `legacyCreatedAt` vẫn giữ epoch milliseconds cũ.
- `localStart` vẫn giữ ngày và giờ địa phương đã ghi, nhưng bản thân nó không chứa múi giờ.
- `deadlineEpochMillis` vẫn là deadline đã tính trước checkpoint; nó không tự được cộng thêm khoảng thời gian tạm dừng.
- `startedNanos` vẫn là số nguyên đã lưu, nhưng không nên mặc định có thể dùng nó để đo thời gian bao gồm khoảng tạm dừng.
- `retryDelay` vẫn biểu diễn một khoảng thời gian 10 giây; nó không tự biến thành thời điểm chạy tiếp theo.

Checkpoint không biến các timestamp trong object thành timestamp mới. Nếu một field chứa `Instant` tại 10:00 và tiến trình được restore lúc 10:20, field đó vẫn biểu diễn 10:00. Ứng dụng phải tự so sánh nó với thời gian hiện tại và quyết định việc cần làm.

| Dữ liệu trong heap | Hành vi cần hiểu sau restore |
|---|---|
| `Instant`, `Date`, epoch milliseconds | Giữ thời điểm đã ghi; không tự cập nhật thành hiện tại |
| `LocalDateTime` | Giữ các trường ngày/giờ cũ; không chứa thông tin múi giờ |
| `Duration` | Giữ độ dài khoảng thời gian; không cho biết khoảng đó đã trôi qua bao lâu |
| Deadline tính từ wall clock | Vẫn giữ deadline cũ; cần so sánh với thời gian hiện tại |
| Giá trị lấy từ `System.nanoTime()` | Là số đo từ một nguồn monotonic; không dùng như timestamp lịch hoặc deadline bền vững qua checkpoint |
| Trạng thái scheduler/timer | Có thể được phục hồi cùng tiến trình; cần đánh giá deadline và chính sách chạy bù |

## 2. Phân biệt wall clock và monotonic clock

Java cung cấp nhiều API thời gian vì các bài toán khác nhau cần những loại đồng hồ khác nhau.

### Wall clock: thời điểm trên lịch

`System.currentTimeMillis()` trả về số milliseconds kể từ Unix epoch. `Instant.now()` cũng đọc thời gian hiện tại theo đồng hồ hệ thống, biểu diễn theo UTC. Chúng phù hợp để ghi nhận thời điểm sự kiện, lưu deadline tuyệt đối hoặc so sánh với thời điểm hết hạn do hệ thống bên ngoài cấp.

```java
Instant checkpointRequestedAt = Instant.now();
long epochMillis = System.currentTimeMillis();
```

Wall clock có thể được điều chỉnh bởi NTP, quản trị viên hoặc cấu hình hệ thống. Vì thế, nó không phải đồng hồ đo duration hoàn hảo: đồng hồ có thể nhảy tiến hoặc lùi. Khi cần một thời điểm có thẩm quyền như thời hạn token, lease hoặc transaction, nên dựa vào nguồn thời gian được hệ thống cấp quyền quản lý, chẳng hạn database hoặc dịch vụ phát hành lease.

### Monotonic clock: đo khoảng thời gian trôi qua

`System.nanoTime()` được thiết kế để đo thời gian đã trôi qua. Giá trị trả về có origin tùy ý, không phải epoch timestamp và không thể chuyển thành ngày giờ thực tế. Cách sử dụng đúng là lấy hiệu giữa hai lần đọc trong cùng một đoạn hoạt động:

```java
long started = System.nanoTime();
performOperation();
long elapsedNanos = System.nanoTime() - started;

System.out.println("Elapsed nanos: " + elapsedNanos);
```

Không nên lưu `started` vào database, dùng nó làm thời điểm hết hạn có thể chia sẻ giữa nhiều tiến trình, hoặc so sánh với `System.currentTimeMillis()`. Đặc biệt, không nên mặc định một giá trị `nanoTime` đã lưu trong checkpoint có thể dùng để tính chính xác thời gian bao gồm giai đoạn tiến trình bị tạm dừng. Cách nguồn monotonic của hệ điều hành xử lý khoảng thời gian đó phụ thuộc nền tảng và cơ chế checkpoint/restore.

| Nhu cầu | Nguồn thời gian nên dùng |
|---|---|
| Ghi thời điểm một sự kiện xảy ra | `Instant.now()` hoặc clock có thẩm quyền |
| Lưu thời điểm hết hạn của token/lease | Thời điểm tuyệt đối do issuer/database quản lý |
| Đo thời gian thực thi một đoạn code đang chạy | Hiệu giữa hai lần `System.nanoTime()` |
| Tính thời gian tạm dừng từ checkpoint đến restore | Timestamp wall clock được ghi trước checkpoint và đọc lại sau restore; cân nhắc clock skew |
| Lên lịch một sự kiện theo giờ địa phương | Thời điểm/múi giờ nghiệp vụ được xác định rõ, rồi chuyển thành instant khi cần |

## 3. Đo khoảng thời gian tiến trình đã tạm dừng

Nếu cần biết gần đúng tiến trình đã ngừng hoạt động bao lâu, có thể ghi một `Instant` ngay trước checkpoint và so sánh với thời gian hiện tại sau restore.

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class PauseTimeResource implements Resource {

    private final Clock clock;
    private Instant checkpointBoundary;

    public PauseTimeResource(Clock clock) {
        this.clock = clock;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) {
        checkpointBoundary = clock.instant();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) {
        Instant restoredAt = clock.instant();
        Duration approximatePause = Duration.between(
                checkpointBoundary,
                restoredAt);

        if (approximatePause.isNegative()) {
            // Wall clock đã lùi; cần ghi nhận và áp dụng chính sách phù hợp.
            handleClockMovedBackward(checkpointBoundary, restoredAt);
            return;
        }

        recordPauseDuration(approximatePause);
    }

    private void handleClockMovedBackward(Instant before, Instant after) {
        // Ghi nhận clock anomaly; không dùng duration âm như thời gian tạm dừng.
    }

    private void recordPauseDuration(Duration duration) {
        // Ghi metric/log với nhãn instance phù hợp.
    }
}
```

`Clock` được inject để có thể kiểm thử. `checkpointBoundary` là một timestamp được lưu trong trạng thái của resource; sau restore, `clock.instant()` đọc thời điểm hiện tại. Hiệu giữa hai giá trị cho một ước lượng khoảng thời gian tạm dừng.

Phép tính này có giới hạn:

- Wall clock có thể bị điều chỉnh trong thời gian tiến trình tạm dừng.
- Nếu restore trên host khác, hai host có thể lệch đồng hồ.
- `beforeCheckpoint()` được gọi trong chuỗi callback, nên timestamp ghi tại đó là mốc gần đúng; nó không nhất thiết đúng chính xác thời điểm snapshot hoàn tất.
- Nếu cần thời gian có thẩm quyền cho quyết định bảo mật hoặc lease, nên hỏi hệ thống cấp lease/token thay vì tin vào phép trừ đồng hồ local.

Nếu cần đo thời gian chính xác theo một hệ thống phân tán, hãy lưu timestamp ở một nguồn thời gian thống nhất hoặc nhờ coordinator ghi nhận thời điểm checkpoint/restore. Không nên dùng một biến `nanoTime` local để đo khoảng thời gian giữa hai host.

## 4. Xử lý deadline đã trôi qua trong lúc checkpoint

Một deadline thường được tính như sau:

```java
Instant expiresAt = clock.instant().plus(Duration.ofMinutes(5));
```

Nếu checkpoint được tạo ngay sau đó và restore 8 phút sau, deadline vẫn là thời điểm cũ và đã hết hạn. Ứng dụng cần đánh giá lại thay vì khởi động lại bộ đếm 5 phút.

```java
Duration remaining = Duration.between(clock.instant(), expiresAt);

if (remaining.isNegative() || remaining.isZero()) {
    expireOperation();
} else {
    scheduleWithDelay(remaining);
}
```

Đoạn mã trên thể hiện cách tính. Trong code thực tế, `expireOperation()` và `scheduleWithDelay()` cần xử lý concurrency, retry và việc trạng thái nghiệp vụ đã thay đổi ở nơi khác hay chưa.

### Timeout của request hoặc workflow

Nếu một công việc có deadline tuyệt đối, hãy lưu deadline đó thay vì chỉ lưu số giây còn lại tại thời điểm checkpoint. Sau restore, tính lại thời gian còn lại. Nếu đã quá hạn, hủy hoặc chuyển sang trạng thái timeout theo nghiệp vụ.

```java
public final class OperationDeadline {

    private final Clock clock;
    private final Instant deadline;

    public OperationDeadline(Clock clock, Duration allowedTime) {
        this.clock = clock;
        this.deadline = clock.instant().plus(allowedTime);
    }

    public Duration remaining() {
        Duration value = Duration.between(clock.instant(), deadline);
        return value.isNegative() ? Duration.ZERO : value;
    }

    public boolean isExpired() {
        return !clock.instant().isBefore(deadline);
    }
}
```

Nếu deadline được lưu trong database hoặc workflow store, sau restore nên đọc trạng thái mới nhất từ nguồn sự thật. Một bản checkpoint có thể chứa một trạng thái operation cũ trong khi hệ thống bên ngoài đã hoàn tất hoặc hủy operation đó.

### Lease và lock phân tán

Lease thường được cấp với một thời điểm hết hạn tuyệt đối. Khi tiến trình bị tạm dừng lâu hơn thời hạn lease, một instance khác có thể đã lấy quyền sở hữu. Restore không tự gia hạn lease và cũng không chứng minh tiến trình vẫn là owner.

Sau restore:

1. Đọc trạng thái lease từ hệ thống điều phối.
2. Xác minh lease còn hiệu lực và vẫn thuộc instance hiện tại.
3. Nếu đã hết hạn, đăng ký hoặc acquire lease mới theo giao thức.
4. Chỉ thực hiện công việc độc quyền sau khi quyền sở hữu được xác nhận.

Không dùng một boolean `isLeader = true` trong heap làm bằng chứng quyền leader vẫn còn. Giá trị đó có thể được lưu trong image nhưng lease ở hệ thống bên ngoài đã hết hạn.

## 5. TTL của cache, token và session

TTL thường được biểu diễn bằng thời điểm hết hạn hoặc thời điểm tạo cộng với thời lượng sống. Nếu chỉ lưu `remainingTtlSeconds` trong heap, khoảng thời gian đó có thể bị đóng băng về mặt logic trong lúc tiến trình không chạy.

Ví dụ không an toàn:

```java
// Chỉ lưu số giây còn lại tại lúc checkpoint.
long remainingSeconds = 120;
```

Nếu tiến trình restore sau 10 phút, biến vẫn có thể chứa 120. Nếu ứng dụng dùng lại nguyên giá trị đó, dữ liệu đã hết hạn có thể được coi là còn sống thêm 2 phút.

Nên lưu thời điểm hết hạn:

```java
Instant expiresAt = clock.instant().plus(Duration.ofMinutes(2));

boolean isExpired(Instant expiration, Clock clock) {
    return !clock.instant().isBefore(expiration);
}
```

Với cache:

- Giữ cache bất biến nếu dữ liệu không thay đổi trong thời gian cần dùng.
- Với cache có TTL, kiểm tra expiration sau restore trước khi trả dữ liệu.
- Với cache phụ thuộc dữ liệu bên ngoài, kiểm tra version hoặc invalidation state.
- Nếu cache chứa dữ liệu nhạy cảm hoặc quyền truy cập, làm mới khi có nghi ngờ về độ mới.

Với token và session:

- Dùng trường `expires_at` hoặc thông tin hết hạn do issuer cấp.
- Refresh hoặc xác thực lại sau restore khi token gần hết hạn hoặc đã hết hạn.
- Không giả định token trong heap còn hiệu lực chỉ vì object token được phục hồi.
- Với nhiều bản restore, tránh chia sẻ một token đại diện cho một session độc quyền nếu issuer không cho phép.

## 6. Timer và scheduler sau restore

Scheduler có thể lưu trong heap các task, delay và trạng thái lập lịch. Nhưng trong khoảng tiến trình tạm dừng, không có thread ứng dụng nào thực thi callback. Sau restore, hành vi của timer phụ thuộc implementation, clock source và cơ chế checkpoint/restore cụ thể. Một số task có thể trở nên quá hạn và chạy ngay; task khác có thể tiếp tục với delay còn lại; timer native hoặc thread quản lý riêng có thể cần được tạo lại.

Không nên dựa vào hành vi ngầm của `ScheduledExecutorService` để xác định chính sách nghiệp vụ. Hãy quyết định rõ điều gì cần xảy ra với các lịch bị trễ:

- **Skip:** bỏ qua lần chạy đã quá hạn và chờ chu kỳ kế tiếp.
- **Coalesce:** nếu nhiều lần chạy đã trễ, chỉ chạy một lần để cập nhật trạng thái hiện tại.
- **Catch up:** chạy bù các lần đã bỏ lỡ, nhưng cần giới hạn số lần và tốc độ.
- **Expire:** hủy công việc nếu deadline đã qua.

Ví dụ, một job đồng bộ cache mỗi phút không nhất thiết phải chạy bù 20 lần sau khi tiến trình tạm dừng 20 phút. Nó có thể chỉ cần một lần đồng bộ toàn bộ trạng thái mới nhất. Ngược lại, một workflow xử lý từng sự kiện có thể cần tiếp tục từ offset bền vững để không bỏ sót sự kiện.

### Pause và resume scheduler bằng Resource

```java
public final class SchedulerResource implements Resource {

    private final Clock clock;
    private final JobScheduler scheduler;
    private Instant nextRunAt;

    public SchedulerResource(Clock clock, JobScheduler scheduler) {
        this.clock = clock;
        this.scheduler = scheduler;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        scheduler.stopAcceptingNewJobs();
        scheduler.drainInFlightJobs();
        nextRunAt = scheduler.nextRunAt();
        scheduler.pauseAndReleaseTimers();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        Instant now = clock.instant();
        if (nextRunAt != null && !nextRunAt.isAfter(now)) {
            scheduler.handleMissedRun(nextRunAt, now);
        } else if (nextRunAt != null) {
            scheduler.scheduleAt(nextRunAt);
        }
    }
}
```

`JobScheduler` là abstraction minh họa. `handleMissedRun()` phải triển khai một trong các chính sách skip/coalesce/catch-up/expire. Nếu scheduler đã có CRaC integration, hãy sử dụng integration đó và tránh đăng ký callback trùng. Nếu lịch chạy cần tồn tại qua nhiều instance, lưu lịch và trạng thái thực thi trong hệ thống bền vững thay vì chỉ dựa vào scheduler trong heap.

### Fixed rate và fixed delay

Lịch fixed rate hướng tới các mốc chạy theo chu kỳ; fixed delay tính khoảng chờ sau khi một lần chạy kết thúc. Sau một khoảng tạm dừng dài, việc chạy bù hoặc dồn nhiều lần có thể tạo tải đột biến. Hãy kiểm tra semantics của scheduler cụ thể và áp dụng chính sách bỏ qua/coalesce/catch-up rõ ràng. Với tác vụ phân tán, cần lease hoặc cơ chế điều phối để nhiều bản restore không chạy cùng một job độc quyền.

## 7. Timestamp lịch và múi giờ

Không phải mọi kiểu thời gian Java đều biểu diễn cùng một thứ:

| Kiểu | Ý nghĩa | Lưu ý khi restore |
|---|---|---|
| `Instant` | Một điểm thời gian trên timeline UTC | Phù hợp lưu timestamp và deadline tuyệt đối |
| `Date` | Một epoch-millisecond instant kiểu cũ | Giữ thời điểm cũ; cân nhắc chuyển sang `Instant` |
| `LocalDateTime` | Ngày/giờ không có zone hoặc offset | Không đủ để xác định một instant duy nhất |
| `OffsetDateTime` | Ngày/giờ kèm offset UTC | Xác định được instant, nhưng offset không đại diện đầy đủ quy tắc vùng |
| `ZonedDateTime` | Ngày/giờ gắn với `ZoneId` | Hữu ích cho lịch nghiệp vụ theo vùng; quy tắc múi giờ có thể thay đổi theo database timezone |
| `Duration` | Khoảng thời gian theo giây/nanos | Không phải thời điểm bắt đầu hoặc kết thúc |
| `Period` | Khoảng theo năm/tháng/ngày lịch | Có ý nghĩa lịch, không luôn tương đương số giây cố định |

Ví dụ, nếu lưu lịch “09:00 mỗi ngày tại Asia/Ho_Chi_Minh”, hãy lưu rõ `LocalTime` cùng `ZoneId` và quy tắc lịch. Nếu lưu “hết hạn lúc một thời điểm cụ thể”, hãy lưu `Instant`. Đừng lưu `LocalDateTime` rồi giả định host restore có cùng múi giờ mặc định.

Giờ mùa hè (DST), thay đổi timezone database và cấu hình `user.timezone` có thể ảnh hưởng cách diễn giải giờ địa phương. Với lịch định kỳ theo múi giờ nghiệp vụ, cần xác định cách xử lý giờ không tồn tại hoặc bị lặp khi chuyển DST. Với timestamp audit hoặc deadline, dùng UTC instant để tránh sự mơ hồ.

## 8. Nhiều bản restore từ cùng một image

Khi một checkpoint image được dùng để khởi chạy nhiều tiến trình, mọi bản restore có thể bắt đầu với cùng các giá trị timestamp, deadline, counter và trạng thái scheduler đã lưu. Điều đó có thể dẫn đến:

- Nhiều replica cùng cho rằng một lease vẫn thuộc về mình.
- Nhiều scheduler cùng chạy một job đã quá hạn.
- Nhiều token/session được dùng lại dù chỉ được cấp cho một instance.
- Nhiều bản sao cùng thực hiện một tác vụ catch-up.
- Một timestamp `createdAt` giống nhau bị hiểu nhầm là thời điểm tạo của từng replica mới.

Hãy phân biệt timestamp của **checkpoint artifact**, timestamp của **lần restore**, và timestamp của **instance hiện tại**. Sau restore, mỗi instance có thể cần ghi `restoredAt` mới, xin instance ID mới và đăng ký lease mới. Nếu cần theo dõi nguồn gốc, có thể giữ `checkpointCreatedAt` như metadata bất biến, đồng thời tạo `instanceStartedAt` hoặc `restoredAt` mới.

Không dùng một biến thời gian trong heap để điều phối tính duy nhất giữa nhiều bản sao. Dùng database, coordinator, distributed lock hoặc lease service có thẩm quyền.

## 9. Clock skew và thay đổi đồng hồ

Phép tính thời gian dựa trên wall clock có thể bị ảnh hưởng bởi clock skew. Ví dụ, host tạo checkpoint nhanh hơn 30 giây so với host restore. Khi lấy hiệu hai timestamp, khoảng tạm dừng có thể bị âm hoặc lệch đáng kể.

Các nguyên tắc xử lý:

- Đồng bộ đồng hồ host bằng NTP hoặc cơ chế thời gian của nền tảng.
- Với lease/token, tin vào thời điểm hết hạn và xác thực từ issuer/database thay vì tự suy ra quyền sở hữu từ đồng hồ local.
- Phát hiện và ghi nhận trường hợp thời gian lùi hoặc nhảy bất thường.
- Không biến duration âm thành một khoảng chờ lớn do overflow hoặc chuyển đổi đơn vị sai.
- Dùng `Clock` injection để kiểm thử các tình huống đồng hồ tiến, lùi và restore muộn.
- Với tác vụ quan trọng, lưu timestamp và trạng thái nghiệp vụ trong cùng nguồn sự thật nếu cần tính nhất quán.

`Instant` tránh mơ hồ múi giờ nhưng vẫn lấy từ wall clock. Nó không tự loại bỏ clock skew. Tính chính xác phụ thuộc vào nguồn thời gian được dùng.

## 10. Mẫu thiết kế cho timeout trong cùng một lần chạy và qua checkpoint

Một timeout trong một đoạn xử lý ngắn có thể dùng `System.nanoTime()`:

```java
long timeoutNanos = TimeUnit.SECONDS.toNanos(5);
long started = System.nanoTime();

while (!conditionMet()) {
    if (System.nanoTime() - started >= timeoutNanos) {
        throw new TimeoutException("Operation timed out");
    }
    waitForProgress();
}
```

Đây là cách đo elapsed time trong đoạn thực thi hiện tại. Nếu thao tác có thể bị gián đoạn bởi checkpoint và cần tính cả thời gian tạm dừng, hãy lưu deadline tuyệt đối hoặc trạng thái timeout bền vững:

```java
Instant deadline = clock.instant().plusSeconds(5);

void resumeOperation() {
    if (!clock.instant().isBefore(deadline)) {
        throw new OperationExpiredException();
    }

    Duration remaining = Duration.between(clock.instant(), deadline);
    continueWithTimeout(remaining);
}
```

Một số thao tác cần cả hai loại thời gian: dùng `Instant` để quyết định deadline qua checkpoint, sau đó dùng `nanoTime` để đo thời gian thực thi từng lần retry hoặc từng đoạn I/O trong một lần chạy. Đừng dùng một loại đồng hồ cho mọi mục đích.

## 11. Kiểm thử hành vi thời gian qua checkpoint/restore

Không nên chỉ kiểm thử restore ngay sau khi tạo checkpoint. Cần tạo các khoảng tạm dừng khác nhau để xác nhận deadline, TTL và scheduler phản ứng đúng.

Các tình huống nên kiểm thử:

1. Restore ngay sau checkpoint, khi mọi token và cache vẫn còn hạn.
2. Restore sau khi một deadline đã hết hạn.
3. Restore sau khi token hoặc lease đã hết hạn.
4. Restore khi cache TTL đã trôi qua.
5. Restore khi một scheduler có nhiều lần chạy bị bỏ lỡ.
6. Restore khi wall clock bị điều chỉnh tiến hoặc lùi trong môi trường kiểm thử.
7. Restore trên host có clock skew trong giới hạn được giả định.
8. Khởi chạy nhiều bản restore từ cùng image và xác nhận job/lease không bị nhân bản ngoài ý muốn.
9. Checkpoint khi task đang chờ timeout và xác minh timeout sau restore theo đúng chính sách.

Ghi log các mốc `beforeCheckpoint`, `checkpointBoundary`, `afterRestore`, `restoredAt`, `deadline`, `remainingDuration` và `readiness`. Gắn instance ID mới cho mỗi lần restore. Không ghi token hoặc dữ liệu xác thực vào log. Các metric hữu ích gồm pause duration, số deadline hết hạn khi restore, số task bị skip/catch-up, số lease phải acquire lại và thời gian từ restore đến readiness.

Nên dùng `Clock.fixed()` trong unit test để kiểm tra logic deadline mà không phải chờ thật. Với kiểm thử tích hợp, cần thực hiện checkpoint/restore trong runtime và hệ điều hành tương thích để quan sát timer, scheduler và clock source thực tế.

## 12. Kết luận

Checkpoint image lưu các giá trị thời gian mà ứng dụng đã ghi trong bộ nhớ, nhưng không làm thời gian thực dừng lại. Sau restore, `Instant`, `Date`, deadline và TTL trong heap vẫn là các giá trị cũ; wall clock đọc mới phản ánh thời điểm hiện tại. `System.nanoTime()` phù hợp để đo elapsed time trong một đoạn thực thi, nhưng không nên dùng làm timestamp lịch hoặc deadline bền vững qua checkpoint.

Với timeout, token, cache, lease và scheduler, hãy xác định rõ liệu thời gian tạm dừng có được tính vào thời hạn hay không. Dùng deadline tuyệt đối và nguồn thời gian có thẩm quyền khi cần tính cả khoảng dừng; tính lại thời gian còn lại sau restore; chọn chính sách skip, coalesce, catch-up hoặc expire cho lịch bị trễ. Khi một image tạo ra nhiều bản restore, tạo timestamp và định danh mới cho từng instance, đồng thời xác lập lại lease và quyền sở hữu qua hệ thống bên ngoài. Như vậy, ứng dụng sẽ không vô tình dùng dữ liệu thời gian cũ như thể tiến trình chưa từng tạm dừng.
