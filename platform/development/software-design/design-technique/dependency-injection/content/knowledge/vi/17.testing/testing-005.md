# Truyền clock, nguồn sinh số hoặc bộ lập lịch để kiểm soát tính không xác định

Trong chương **Kiểm thử** của module **Dependency Injection**, một trong những lợi ích thực tế nhất của **constructor injection** là khả năng tách hành vi nghiệp vụ khỏi những giá trị không thể dự đoán trước. Thời gian hiện tại, số ngẫu nhiên và lịch chạy tác vụ đều có thể làm một bài test hôm nay thành công nhưng ngày mai thất bại, dù mã nghiệp vụ không đổi.

Thay vì gọi `Instant.now()`, `new Random()` hoặc `Executors.newScheduledThreadPool(...)` ngay trong service, ta có thể **truyền nguồn thời gian, nguồn số và bộ lập lịch từ bên ngoài**. **Composition root** chọn implementation dùng trong ứng dụng; bài test cấp phiên bản có thể điều khiển và quan sát. Đó là cách áp dụng **Dependency Injection (DI)** và **Inversion of Control (IoC)** bằng Java thuần trước khi dùng DI container.

Mục tiêu không phải thay mọi lời gọi JDK bằng một interface tự tạo. Java đã có `java.time.Clock`; với phép sinh số hoặc lập lịch, ta chỉ thêm hợp đồng nhỏ khi hành vi đó thực sự cần được kiểm soát. Kết quả lý tưởng là **test xác định, nhanh, không dùng `Thread.sleep` và không phụ thuộc máy đang chạy vào giờ nào**.

Sau bài học, bạn sẽ có thể:

- Nhận diện tính không xác định từ **wall-clock time**, sinh số giả ngẫu nhiên và lịch thực thi tác vụ.
- Tiêm `Clock`, kiểm tra chính xác ranh giới thời gian và chọn múi giờ hợp lý.
- Tiêm nguồn sinh số có hợp đồng rõ, phân biệt fake có giá trị định sẵn với pseudo-random có seed.
- Thiết kế `TaskScheduler` nhỏ, dùng **virtual time** để kiểm tra tác vụ mà không chờ thời gian thật.
- Tách kiểm thử nghiệp vụ, kiểm thử adapter lập lịch và kiểm thử tích hợp; quản lý vòng đời executor.
- Tránh ngộ nhận rằng kiểm soát randomness/timing trong unit test đồng nghĩa hệ thống production được bảo đảm an toàn hoặc tin cậy.

## 1. Ba nguồn không xác định thường gặp

Giả sử ứng dụng thuê xe có ba yêu cầu: ghi lại thời điểm khách giữ xe, phân về một trong ba quầy tiếp nhận và gửi lời nhắc sau 10 phút.

Một phiên bản khó kiểm thử:

```java
final class FragileReservationService {
    // Chỉ là ví dụ minh họa rủi ro, không phải class chạy độc lập.
    Reservation hold(String id) {
        java.time.Instant createdAt = java.time.Instant.now();
        int desk = new java.util.Random().nextInt(3) + 1;
        // Tạo executor/timer ở đây để gửi nhắc sau 10 phút...
        // Lưu reservation và trả về...
        return null;
    }
}
```

Ba vấn đề khác nhau đang bị trộn vào nghiệp vụ:

| Nguồn | Điều không thể đoán chắc trong test | Hướng kiểm soát |
| --- | --- | --- |
| `Instant.now()` hoặc `LocalDate.now()` | Giá trị phụ thuộc thời điểm chạy, ngày, múi giờ hệ thống | Tiêm `Clock`; test dùng `Clock.fixed(...)` hoặc clock có thể tiến thời gian |
| `new Random()`, `ThreadLocalRandom.current()` | Kết quả thay đổi giữa các lượt chạy, khó ép nhánh hiếm | Tiêm nguồn sinh số hoặc strategy; fake trả dãy giá trị định sẵn |
| `ScheduledExecutorService` / timer thật | Thread được lập lịch nhưng có thể chạy trễ; test phải chờ | Tiêm scheduler; fake cho phép tiến **thời gian ảo** và chạy task đến hạn |

Đối tượng nào **cần đọc thời gian hoặc thực hiện quyết định ngẫu nhiên** mới nên nhận dependency tương ứng. Không phải mọi class trong hệ thống đều cần cả ba. Việc truyền source chỉ có ích nếu logic thực sự dùng source được tiêm, không lén gọi lại API toàn cục bên trong.

## 2. Truyền `Clock` thay vì đọc đồng hồ toàn cục

Java cung cấp sẵn `java.time.Clock`. Một service chỉ quan tâm thời điểm hiện tại có thể nhận trực tiếp kiểu này:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

final class HoldExpiryPolicy {
    private final Clock clock;
    private final Duration lifetime;

    HoldExpiryPolicy(Clock clock, Duration lifetime) {
        this.clock = Objects.requireNonNull(clock);
        this.lifetime = Objects.requireNonNull(lifetime);
        if (lifetime.isZero() || lifetime.isNegative()) {
            throw new IllegalArgumentException("lifetime must be positive");
        }
    }

    Instant expiresAt() {
        return clock.instant().plus(lifetime);
    }

    boolean hasExpired(Instant deadline) {
        return !clock.instant().isBefore(deadline);
    }
}
```

**Composition root trong production** có thể truyền `Clock.systemUTC()`. Trong test, ta khóa thời gian tại một thời điểm cụ thể:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-01-15T08:00:00Z"),
        java.time.ZoneOffset.UTC);
HoldExpiryPolicy policy =
        new HoldExpiryPolicy(fixed, Duration.ofMinutes(30));

if (!policy.expiresAt().equals(
        Instant.parse("2026-01-15T08:30:00Z"))) {
    throw new AssertionError("Unexpected expiry");
}
```

Ví dụ hai khối ở trên được đọc liên tiếp để minh họa API; phần 5 có chương trình đầy đủ tự chứa. Không cần chờ 30 phút: `Clock.fixed` sẽ luôn trả về thời điểm đã chọn.

### 2.1. Ranh giới thời gian phải có hợp đồng

Nếu một lượt giữ xe có hạn `08:30:00Z`, xác định rõ thời điểm **bằng** hạn có hết hiệu lực hay không. Trong bài này dùng quy tắc:

```text
now < expiresAt  : còn hiệu lực
now >= expiresAt : hết hiệu lực
```

Trong Java, `!now.isBefore(expiresAt)` biểu diễn trường hợp hết hạn. Kiểm thử nên gồm **ngay trước**, **đúng bằng** và **ngay sau** thời điểm hết hạn; không chỉ chọn một thời điểm ở giữa.

### 2.2. `Instant`, múi giờ và ngày địa phương

Đối với deadline, thời điểm ghi nhận và audit, `Instant` thường là biểu diễn phù hợp vì chỉ một điểm trên trục thời gian. Nếu quy tắc nghiệp vụ là "đến 18:00 theo giờ Hà Nội" hoặc "tính theo ngày địa phương", ta cần `ZoneId` và các kiểu `LocalDate`/`ZonedDateTime` phù hợp:

```java
Clock businessClock = Clock.system(
        java.time.ZoneId.of("Asia/Ho_Chi_Minh"));
java.time.LocalDate businessDate =
        java.time.LocalDate.now(businessClock);
```

Trong test, truyền `Clock.fixed(instant, zone)` để kiểm soát **cả thời điểm và múi giờ**. Tránh dùng `LocalDateTime.now()` ngầm lấy timezone mặc định của máy rồi so sánh như thể nó là một `Instant`. Các quy tắc ngày giờ địa phương còn phải xét chuyển ngày và, ở những vùng liên quan, daylight saving time.

### 2.3. Đồng hồ thời gian thực khác đồng hồ đo thời lượng

`Clock.instant()` và `System.currentTimeMillis()` diễn đạt thời gian thực trên lịch (*wall-clock time*). Đồng hồ máy có thể bị điều chỉnh, do đó chúng không phải lựa chọn lý tưởng để đo **thời gian trôi qua** của một thao tác. Trong Java, `System.nanoTime()` phù hợp hơn cho đo elapsed time trong cùng tiến trình; giá trị tuyệt đối của nó không phải timestamp để lưu vào database.

Khi kiểm thử timeout hoặc retry, nên tách rõ **hạn nghiệp vụ theo thời điểm** với **khoảng trễ thực thi**. Với scheduler thật, độ chính xác, độ trễ OS và độ lệch clock vẫn phải được xử lý bằng hợp đồng và kiểm thử tích hợp.

## 3. Truyền nguồn sinh số: kiểm tra kết quả, không cầu may

Giả sử khách được phân ngẫu nhiên vào **quầy 1, 2 hoặc 3**. Đây là ví dụ về quyết định nghiệp vụ có yếu tố ngẫu nhiên nhưng **không phải mã xác thực bí mật**. Thay vì cho service tự tạo `Random`, có thể định nghĩa hợp đồng tối thiểu:

```java
@FunctionalInterface
interface IntRandomSource {
    // Hợp đồng: bound > 0, kết quả thuộc [0, bound).
    int nextInt(int bound);
}
```

Một adapter production có thể dùng `java.util.Random`; một fake trong test trả dãy `2, 0, 1` để buộc các nhánh quầy `3, 1, 2`. Nhờ đó bài test có thể dự đoán chính xác quầy được chọn và kiểm tra điều kiện biên, thay vì chấp nhận "một quầy bất kỳ".

### 3.1. Fake giá trị định sẵn hay Random có seed?

| Kỹ thuật | Mục đích phù hợp | Hạn chế |
| --- | --- | --- |
| Fake trả `2` khi `nextInt(3)` | Kiểm thử một nhánh nghiệp vụ cụ thể, có kỳ vọng rõ | Không mô phỏng phân phối xác suất |
| Fake trả chuỗi định sẵn | Kiểm tra trình tự nhiều lần gọi, các nhánh hiếm | Phụ thuộc vào thứ tự gọi nếu không thiết kế hợp đồng tốt |
| `new Random(seed)` | Có thể tái hiện một chuỗi giả ngẫu nhiên khi cùng thuật toán và cách gọi | Dễ tạo test giòn nếu khẳng định chi tiết chuỗi thay vì hành vi |
| Generator production thông thường | Phân bố giá trị cho chức năng không yêu cầu bảo mật | Không phù hợp tạo token hoặc bí mật xác thực |
| `SecureRandom` | Nguồn ngẫu nhiên có đặc tính mật mã khi thiết kế bảo mật yêu cầu | Vẫn phải thiết kế token đủ entropy, chống đoán, rate limit và quản lý bí mật |

**Không dùng seed cố định của `Random` cho mã OTP, token đăng nhập, khóa hoặc bí mật bảo mật.** Để kiểm thử luồng liên quan đến token, có thể tiêm một token generator có hợp đồng rõ và fake nó trong unit test; production phải sử dụng nguồn sinh bảo mật phù hợp. Không để lựa chọn fake/seed của môi trường test rò sang hệ thống thật.

### 3.2. Kiểm soát không đồng nghĩa thay đổi hợp đồng

Nếu `nextInt(bound)` hứa trả kết quả từ `0` đến `bound - 1` thì fake cũng phải tuân thủ. Fake luôn trả `-1` khi bound dương có thể khiến test "đạt" bằng dữ liệu mà adapter thật không thể tạo, tạo cảm giác an toàn giả. Fake nên kiểm tra giới hạn và báo lỗi rõ khi test yêu cầu nhiều giá trị hơn chuỗi đã chuẩn bị.

Nếu quyết định quan trọng là "chọn chính sách nào cho khách doanh nghiệp", không nên dùng randomness chỉ để né việc mô hình hóa quy tắc. Khi đó một policy selector theo dữ liệu nghiệp vụ là lựa chọn rõ hơn.

## 4. Truyền bộ lập lịch và dùng thời gian ảo

Một service cần gửi lời nhắc sau 10 phút. Nếu nó tự tạo `ScheduledExecutorService` trong constructor, test có thể phải đợi 10 phút hoặc dựa vào `Thread.sleep` với timeout. Cách này làm bài test **chậm, dễ flake và khó quan sát thứ tự task**.

Tách một hợp đồng đủ hẹp:

```java
@FunctionalInterface
interface TaskScheduler {
    // delay phải >= 0; job sẽ được lên lịch sau khoảng delay.
    void schedule(java.time.Duration delay, Runnable job);
}
```

Đây là interface cho việc **đặt lịch tác vụ**, không phải service locator, cũng không buộc consumer biết thread pool hoạt động ra sao. Trong production, adapter có thể gọi `ScheduledExecutorService.schedule(...)`. Trong unit test, **virtual scheduler** giữ các job trong hàng đợi; test gọi `advanceBy(Duration.ofMinutes(10))` để tiến đồng hồ và thực thi đúng những job đã tới hạn.

### 4.1. Đồng hồ test và scheduler test phải nhất quán

Nếu service tính `expiresAt` từ một clock, trong khi fake scheduler tiến một bộ đếm thời gian hoàn toàn khác, test có thể chạy reminder khi `Clock.instant()` chưa thay đổi. Nếu callback còn kiểm tra deadline, kết quả sẽ sai hoặc khó hiểu.

Một cách thiết kế rõ là cho **clock thay đổi được** và **virtual scheduler** dùng **cùng một nguồn thời gian ảo**. Khi test gọi `advanceBy(...)`, scheduler:

1. Xác định thời điểm mục tiêu.
2. Lấy lần lượt các task đến hạn theo `dueTime`; nếu trùng hạn thì giữ thứ tự đăng ký.
3. Đặt clock tại thời điểm đến hạn rồi chạy callback.
4. Cuối cùng đặt clock tại thời điểm mục tiêu.

Như vậy callback nhìn thấy thời gian có nghĩa tại thời điểm nó chạy. Bài test không cần thread hoặc sleep thật. Nếu callback ném exception, fake có thể để lỗi nổi lên ngay tại `advanceBy` để test chẩn đoán trực tiếp.

### 4.2. Tác vụ được lên lịch không phải nguồn sự thật duy nhất

Thực tế một scheduler có thể **chạy trễ**, bị restart, bị hủy hoặc không thực thi vì ứng dụng đã dừng. Do đó, tính hợp lệ của một reservation nên dựa trên `expiresAt` được lưu và thời gian hiện tại, **không phụ thuộc duy nhất vào việc callback hết hạn đã chạy**.

Ví dụ sắp tới dùng task để **gửi lời nhắc**; quy tắc **hết hạn** được kiểm tra trực tiếp qua `Reservation.isExpiredAt(now)`. Với yêu cầu bền vững cao như phát email chắc chắn được xử lý, cần thêm durable queue/outbox, retry và idempotency; một scheduler trong bộ nhớ hoặc fake scheduler không tự cung cấp những bảo đảm này.

## 5. Ví dụ Java 11 tự chứa: Clock, Random và Scheduler qua constructor

Ứng dụng mẫu triển khai luồng giữ xe:

- Thời điểm giữ xe được lấy từ `Clock`.
- Một lượt giữ xe hết hạn sau **30 phút**, kiểm tra theo `Instant`.
- Nguồn sinh số chọn **một trong ba quầy**.
- Scheduler gửi **lời nhắc sau 10 phút**, nếu lượt giữ vẫn còn hiệu lực.
- Composition root kiểm thử dùng `AdjustableClock`, `FixedSequenceRandom` và `VirtualTaskScheduler`; không dùng mạng, database hoặc thread thật.

Lưu toàn bộ mã sau vào `DeterministicDependenciesDemo.java`. Biên dịch và chạy với **Java 11 trở lên**:

```bash
javac DeterministicDependenciesDemo.java
java DeterministicDependenciesDemo
```

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.PriorityQueue;
import java.util.Random;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class DeterministicDependenciesDemo {
    // 1. Hợp đồng của các nguồn không xác định.
    @FunctionalInterface
    interface IntRandomSource {
        int nextInt(int exclusiveBound);
    }

    @FunctionalInterface
    interface TaskScheduler {
        void schedule(Duration delay, Runnable job);
    }

    @FunctionalInterface
    interface ReminderSink {
        void remind(String reservationId);
    }

    interface ReservationRepository {
        void save(Reservation reservation);
        Optional<Reservation> find(String reservationId);
    }

    // 2. Entity bất biến; quy tắc hết hạn dựa trên thời điểm tuyệt đối.
    static final class Reservation {
        final String id;
        final Instant createdAt;
        final Instant expiresAt;
        final int desk;

        Reservation(String id, Instant createdAt, Instant expiresAt, int desk) {
            this.id = Objects.requireNonNull(id);
            this.createdAt = Objects.requireNonNull(createdAt);
            this.expiresAt = Objects.requireNonNull(expiresAt);
            if (desk < 1 || desk > 3 || !expiresAt.isAfter(createdAt)) {
                throw new IllegalArgumentException("Invalid reservation");
            }
            this.desk = desk;
        }

        boolean isExpiredAt(Instant now) {
            return !Objects.requireNonNull(now).isBefore(expiresAt);
        }
    }

    // 3. Application service nhận đầy đủ phụ thuộc từ ngoài.
    static final class ReservationService {
        static final Duration HOLD_LIFETIME = Duration.ofMinutes(30);
        static final Duration REMINDER_DELAY = Duration.ofMinutes(10);

        private final Clock clock;
        private final IntRandomSource random;
        private final TaskScheduler scheduler;
        private final ReservationRepository repository;
        private final ReminderSink reminders;

        ReservationService(
                Clock clock,
                IntRandomSource random,
                TaskScheduler scheduler,
                ReservationRepository repository,
                ReminderSink reminders) {
            this.clock = Objects.requireNonNull(clock);
            this.random = Objects.requireNonNull(random);
            this.scheduler = Objects.requireNonNull(scheduler);
            this.repository = Objects.requireNonNull(repository);
            this.reminders = Objects.requireNonNull(reminders);
        }

        Reservation hold(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("Reservation ID required");
            }

            Instant now = clock.instant(); // Chụp một snapshot thời gian.
            int desk = random.nextInt(3) + 1;
            Reservation reservation =
                    new Reservation(id, now, now.plus(HOLD_LIFETIME), desk);
            repository.save(reservation);

            scheduler.schedule(REMINDER_DELAY, () -> {
                // Callback dùng đồng hồ được inject; không gọi Instant.now().
                repository.find(id)
                        .filter(found -> !found.isExpiredAt(clock.instant()))
                        .ifPresent(found -> reminders.remind(found.id));
            });
            return reservation;
        }
    }

    // 4. Adapter production cho số giả ngẫu nhiên thông thường.
    static final class JdkRandomSource implements IntRandomSource {
        private final Random random;

        JdkRandomSource(Random random) {
            this.random = Objects.requireNonNull(random);
        }

        @Override
        public int nextInt(int exclusiveBound) {
            return random.nextInt(exclusiveBound);
        }
    }

    // Adapter production cho scheduling; chủ sở hữu executor nằm ở root.
    static final class ExecutorTaskScheduler implements TaskScheduler {
        private final ScheduledExecutorService executor;

        ExecutorTaskScheduler(ScheduledExecutorService executor) {
            this.executor = Objects.requireNonNull(executor);
        }

        @Override
        public void schedule(Duration delay, Runnable job) {
            Objects.requireNonNull(delay);
            Objects.requireNonNull(job);
            if (delay.isNegative()) {
                throw new IllegalArgumentException("Delay must be >= 0");
            }
            executor.schedule(job, delay.toMillis(), TimeUnit.MILLISECONDS);
        }
    }

    // 5. Adapter bộ nhớ cho ví dụ đơn luồng.
    static final class MemoryRepository implements ReservationRepository {
        private final Map<String, Reservation> data = new HashMap<>();

        @Override
        public void save(Reservation reservation) {
            Objects.requireNonNull(reservation);
            if (data.putIfAbsent(reservation.id, reservation) != null) {
                throw new IllegalArgumentException("Duplicate reservation ID");
            }
        }

        @Override
        public Optional<Reservation> find(String reservationId) {
            return Optional.ofNullable(data.get(reservationId));
        }
    }

    // 6. Clock có thể điều khiển, giữ chung mốc thời gian khi withZone().
    static final class AdjustableClock extends Clock {
        private final AtomicReference<Instant> current;
        private final ZoneId zone;

        AdjustableClock(Instant start) {
            this(new AtomicReference<>(Objects.requireNonNull(start)),
                    ZoneOffset.UTC);
        }

        private AdjustableClock(
                AtomicReference<Instant> current, ZoneId zone) {
            this.current = Objects.requireNonNull(current);
            this.zone = Objects.requireNonNull(zone);
        }

        @Override
        public ZoneId getZone() {
            return zone;
        }

        @Override
        public Clock withZone(ZoneId newZone) {
            return new AdjustableClock(current, newZone);
        }

        @Override
        public Instant instant() {
            return current.get();
        }

        void set(Instant instant) {
            current.set(Objects.requireNonNull(instant));
        }
    }

    // 7. Fake scheduler: chạy đồng bộ khi test chủ động tiến thời gian.
    static final class VirtualTaskScheduler implements TaskScheduler {
        static final class Job implements Comparable<Job> {
            final Instant dueAt;
            final long sequence;
            final Runnable action;

            Job(Instant dueAt, long sequence, Runnable action) {
                this.dueAt = dueAt;
                this.sequence = sequence;
                this.action = action;
            }

            @Override
            public int compareTo(Job other) {
                int byDueTime = dueAt.compareTo(other.dueAt);
                return byDueTime != 0
                        ? byDueTime
                        : Long.compare(sequence, other.sequence);
            }
        }

        private final AdjustableClock clock;
        private final PriorityQueue<Job> pending = new PriorityQueue<>();
        private long nextSequence;

        VirtualTaskScheduler(AdjustableClock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        @Override
        public void schedule(Duration delay, Runnable job) {
            Objects.requireNonNull(delay);
            Objects.requireNonNull(job);
            if (delay.isNegative()) {
                throw new IllegalArgumentException("Delay must be >= 0");
            }
            pending.add(new Job(
                    clock.instant().plus(delay), nextSequence++, job));
        }

        void advanceBy(Duration duration) {
            Objects.requireNonNull(duration);
            if (duration.isNegative()) {
                throw new IllegalArgumentException("Cannot rewind time");
            }
            Instant target = clock.instant().plus(duration);
            while (!pending.isEmpty()
                    && !pending.peek().dueAt.isAfter(target)) {
                Job job = pending.remove();
                clock.set(job.dueAt);
                job.action.run();
            }
            clock.set(target);
        }

        int pendingCount() {
            return pending.size();
        }
    }

    // 8. Fake nguồn số: bắt lỗi nếu test dùng hết dãy hoặc sai hợp đồng.
    static final class FixedSequenceRandom implements IntRandomSource {
        private final int[] values;
        private int position;

        FixedSequenceRandom(int... values) {
            this.values = values.clone();
        }

        @Override
        public int nextInt(int exclusiveBound) {
            if (exclusiveBound <= 0) {
                throw new IllegalArgumentException("Invalid bound");
            }
            if (position == values.length) {
                throw new AssertionError("Unexpected random call");
            }
            int value = values[position++];
            if (value < 0 || value >= exclusiveBound) {
                throw new AssertionError("Fake value is outside [0, bound)");
            }
            return value;
        }
    }

    static void check(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    // 9. Composition root của test: các nguồn đều do test kiểm soát.
    public static void main(String[] args) {
        Instant start = Instant.parse("2026-01-15T08:00:00Z");
        AdjustableClock clock = new AdjustableClock(start);
        VirtualTaskScheduler scheduler = new VirtualTaskScheduler(clock);
        FixedSequenceRandom random = new FixedSequenceRandom(2, 0);
        MemoryRepository repository = new MemoryRepository();
        List<String> remindedIds = new ArrayList<>();

        ReservationService service = new ReservationService(
                clock, random, scheduler, repository, remindedIds::add);

        Reservation first = service.hold("BK-001");
        check(first.createdAt.equals(start), "Created time");
        check(first.expiresAt.equals(start.plus(Duration.ofMinutes(30))),
                "Expiry time");
        check(first.desk == 3, "Random desk should be 3");
        check(scheduler.pendingCount() == 1, "One reminder scheduled");

        // Kiểm tra chính xác ranh giới mà không dùng Thread.sleep().
        Clock justBeforeExpiry = Clock.fixed(
                first.expiresAt.minusNanos(1), ZoneOffset.UTC);
        Clock atExpiry = Clock.fixed(first.expiresAt, ZoneOffset.UTC);
        check(!first.isExpiredAt(justBeforeExpiry.instant()),
                "Reservation not yet expired");
        check(first.isExpiredAt(atExpiry.instant()),
                "Reservation expired exactly at deadline");

        scheduler.advanceBy(Duration.ofMinutes(9));
        check(remindedIds.isEmpty(), "Reminder must not run at minute 9");
        System.out.println("Phut 9: 0 loi nhac");

        scheduler.advanceBy(Duration.ofMinutes(1));
        check(remindedIds.equals(List.of("BK-001")),
                "Reminder must run at minute 10");
        System.out.println("Phut 10: 1 loi nhac");

        // Tại phút 10, một lượt mới nhận nguồn số tiếp theo là 0.
        Reservation second = service.hold("BK-002");
        check(second.desk == 1, "Random desk should be 1");
        check(second.createdAt.equals(start.plus(Duration.ofMinutes(10))),
                "Second reservation time");

        // Tới phút 31: reminder của BK-002 đến hạn ở phút 20.
        scheduler.advanceBy(Duration.ofMinutes(21));
        check(remindedIds.equals(List.of("BK-001", "BK-002")),
                "Both reminders should have run");
        check(first.isExpiredAt(clock.instant()), "First must be expired");
        check(!second.isExpiredAt(clock.instant()),
                "Second must still be valid");
        check(scheduler.pendingCount() == 0, "No remaining reminders");
        System.out.println("Phut 31: BK-001 het han, BK-002 con han");

        check(repository.find("BK-001").orElseThrow() == first,
                "First reservation was saved");
        check(repository.find("BK-002").orElseThrow() == second,
                "Second reservation was saved");
        System.out.println("Kiem thu khong can cho thoi gian that: PASS");
    }
}
```

Kết quả dự kiến:

```text
Phut 9: 0 loi nhac
Phut 10: 1 loi nhac
Phut 31: BK-001 het han, BK-002 con han
Kiem thu khong can cho thoi gian that: PASS
```

Không có `Thread.sleep`, database hoặc yêu cầu HTTP thật. Thời gian ảo bắt đầu lúc **08:00 UTC**. `BK-001` hết hạn lúc **08:30**, `BK-002` được tạo lúc **08:10** và hết hạn **08:40**. Khi tiến đến phút 31, lượt thứ nhất đã hết hạn còn lượt thứ hai vẫn hợp lệ.

### 5.1. Đọc vai trò của từng dependency

| Phụ thuộc | Production có thể cấp | Test đã cấp |
| --- | --- | --- |
| `Clock` | `Clock.systemUTC()` hoặc clock theo zone nghiệp vụ | `AdjustableClock`/`Clock.fixed` |
| `IntRandomSource` | `JdkRandomSource(new Random())` cho phân quầy không bảo mật | `FixedSequenceRandom(2, 0)` |
| `TaskScheduler` | `ExecutorTaskScheduler` với `ScheduledExecutorService` | `VirtualTaskScheduler` dùng chung clock ảo |
| `ReservationRepository` | JDBC adapter hoặc repository thực | `MemoryRepository` đơn giản |
| `ReminderSink` | Email, message producer hoặc notification adapter | `List<String>::add` để ghi nhận lời gọi |

`ReservationService` không cần biết mình đang chạy trong test hay production. **Constructor thể hiện mọi nguồn không xác định mà nó sử dụng**. Thay triển khai ở composition root không làm thay đổi thuật toán giữ xe.

### 5.2. Điều bài test kiểm tra, và điều chưa kiểm tra

Test xác nhận thời điểm tạo, thời điểm hết hạn, quầy được chọn, thứ tự gửi nhắc và việc task chưa đến hạn không chạy. Nó còn kiểm tra ranh giới **ngay trước** và **đúng bằng** deadline.

Tuy nhiên, nó **chưa** chứng minh task chạy đúng thời gian khi OS bận, không chứng minh khả năng đồng thời của repository và không chứng minh lời nhắc còn tồn tại sau khi ứng dụng restart. `MemoryRepository` dùng `HashMap` cho ví dụ đơn luồng; `VirtualTaskScheduler` chạy callback trên chính thread test. Những thuộc tính về đồng thời và độ bền cần kiểm thử riêng với adapter thực tế.

## 6. Composition root trong production và ownership của scheduler

Ở ứng dụng thật, việc chọn nguồn thời gian, số và scheduler diễn ra một lần ở composition root hoặc module assembler:

```java
// Minh họa wiring bên ngoài consumer, dùng các kiểu ở phần 5.
Clock clock = Clock.systemUTC();
IntRandomSource random =
        new JdkRandomSource(new java.util.Random());

ScheduledExecutorService pool =
        java.util.concurrent.Executors.newScheduledThreadPool(2);
TaskScheduler scheduler = new ExecutorTaskScheduler(pool);

// ReservationRepository repository = ...;
// ReminderSink sink = ...;
// ReservationService service = new ReservationService(
//         clock, random, scheduler, repository, sink);
//
// Khi shutdown: ngừng nhận yêu cầu, xử lý các job đã nhận theo chính sách,
// rồi shutdown/awaitTermination pool và các tài nguyên mà job đang sử dụng.
```

Đoạn trên chỉ minh họa cách tạo adapter; không phải chương trình production hoàn chỉnh, vì không tạo repository/sink thật hay thực hiện đường shutdown. **`ReservationService` không sở hữu `ScheduledExecutorService`** và không tự gọi `shutdown()` sau mỗi yêu cầu. Runtime/composition root quản lý vòng đời của pool, đồng thời xác định thứ tự dừng nhận request, xử lý task đang chạy rồi đóng các network/database client mà task có thể còn sử dụng.

Với `ScheduledExecutorService`, `shutdown()` chỉ ngừng nhận task mới; còn task đã đặt lịch có thể được tiếp tục hoặc bị hủy tùy implementation và chính sách shutdown được cấu hình. `awaitTermination(...)` chờ executor kết thúc trong thời hạn; `shutdownNow()` chỉ cố gắng ngắt/hủy công việc. **Không được xem việc gọi shutdown là bằng chứng mọi reminder đều đã được gửi.**

### 6.1. Những khác biệt giữa scheduler thật và giả

| Thuộc tính | Virtual scheduler trong test | Scheduler thật |
| --- | --- | --- |
| Thời điểm chạy | Chính xác theo thời gian ảo và quy tắc fake | Có độ trễ thực thi và ảnh hưởng từ tải, thread, OS |
| Thread | Chạy đồng bộ trong test | Có thể chạy trên worker thread khác |
| Thứ tự task trùng deadline | Fake cố định thứ tự đăng ký | Không nên dựa vào thứ tự nếu API không cam kết |
| Tác vụ mới được đặt trong callback | Fake thêm vào hàng đợi ảo | Bị chi phối bởi executor và chính sách nhận task |
| Lỗi trong callback | Có thể nổi ngay tại `advanceBy` | Phải được theo dõi bằng Future, logging/handler phù hợp |
| Restart/durable delivery | Chỉ tồn tại trong bộ nhớ test | Executor trong bộ nhớ cũng không tự có tính bền vững |

Trong `ExecutorTaskScheduler` ở ví dụ, `delay.toMillis()` đổi Duration sang mili giây; độ chính xác nhỏ hơn mili giây có thể bị làm tròn. Duration cực lớn còn có thể gây lỗi tràn khi chuyển đổi. Adapter production cần xác định giới hạn delay, xử lý kết quả Future nếu cần cancellation, và nêu rõ cách báo lỗi từ task.

## 7. Kiểm thử thứ gì ở lớp nào?

Tách mục tiêu test để không biến mọi unit test thành kiểm thử scheduler hoặc network:

| Lớp kiểm thử | Công cụ | Mục tiêu |
| --- | --- | --- |
| **Quy tắc thời gian** | `Clock.fixed(...)` hoặc gọi hàm với `Instant` đã chọn | Kiểm tra deadline, biên bằng và trước/sau |
| **Thuật toán sử dụng randomness** | `FixedSequenceRandom`, fake theo kịch bản | Kiểm tra nhánh và bất biến của kết quả |
| **Luồng lên lịch** | Virtual scheduler + adjustable clock | Kiểm tra delay, thứ tự callback, điều kiện không chạy sớm |
| **Logic application service** | Fake repository, fake sink và các nguồn có kiểm soát | Kiểm tra side effect đúng, input sai và xử lý lỗi |
| **Adapter `ScheduledExecutorService`** | Test với executor thật, timeout ngắn có kiểm soát | Kiểm tra thread, cancellation, lỗi task và shutdown |
| **End-to-end/integration** | Adapter mạng/database/queue thật hoặc test environment phù hợp | Kiểm tra retry, tính bền vững, transaction, clock skew và vận hành |

Với một hàm thuần nhận `Instant now` làm tham số, đôi khi **không cần inject cả `Clock`**:

```java
static boolean isExpired(Instant now, Instant deadline) {
    return !now.isBefore(deadline);
}
```

Nếu caller đã sở hữu snapshot thời gian của giao dịch, truyền `Instant` vào một hàm thuần có thể còn đơn giản hơn. `Clock` phù hợp khi một service cần **tự đọc thời điểm hiện tại** nhưng muốn nguồn thời gian có thể thay trong test. Chọn đúng mức trừu tượng thay vì thêm wrapper máy móc cho mọi API JDK.

## 8. Các giới hạn quan trọng của tính xác định

### 8.1. Nguồn ngẫu nhiên có seed không thay test cho concurrency

Một `Random` với seed cố định giúp tái hiện chuỗi sinh số trong một số điều kiện, nhưng **không làm lịch chạy thread trở nên xác định**. Nếu nhiều thread cùng gọi một generator chia sẻ, thứ tự tiêu thụ số có thể khác nhau giữa các lần chạy dù seed giống nhau. Khi kiểm tra logic dựa trên từng request, nên truyền generator có scope phù hợp hoặc fake theo kịch bản; khi kiểm tra race condition, cần test đồng thời và thiết kế đồng bộ riêng.

### 8.2. Virtual time không tự chứng minh thread-safety

Fake scheduler chạy đồng bộ dễ kiểm tra logic, nhưng có thể bỏ sót race condition hoặc vấn đề visibility giữa thread thật. Nếu tác vụ chạy đồng thời và truy cập mutable state như `HashMap`, production cần repository/adapters thread-safe hoặc transaction đúng cách. Test virtual giúp kiểm tra **quy tắc về thời điểm**, không chứng minh mọi cam kết thực thi đồng thời.

### 8.3. Deadline thật không nên phụ thuộc duy nhất vào timer

Nếu một tác vụ "đánh dấu hết hạn" bị lỡ khi ứng dụng restart, một reservation quá hạn vẫn cần được coi là không hợp lệ. Mã sử dụng `Instant expiresAt` và `Clock` nên xác định tính hợp lệ **khi đọc hoặc xử lý yêu cầu**. Timer dùng cho notification, cleanup hoặc tác vụ phụ trợ; nếu cần xử lý chắc chắn phải có dữ liệu bền vững, cơ chế retry/outbox hoặc scheduler bền vững phù hợp.

### 8.4. Lỗi sau khi ghi dữ liệu nhưng trước khi lên lịch

Trong `ReservationService.hold`, repository được gọi trước `scheduler.schedule`. Nếu scheduler từ chối tác vụ sau khi reservation đã lưu, có thể tạo trạng thái **đã giữ xe nhưng chưa có reminder**. Bài học không dùng transaction để che tình huống này. Với yêu cầu reminder đáng tin cậy, nên xem xét **transactional outbox**, enqueue bền vững, retry và idempotency. DI chỉ giúp thay adapter và kiểm thử các nhánh lỗi; nó **không tự biến hai thao tác I/O thành một giao dịch nguyên tử**.

## 9. Những lỗi thường gặp khi kiểm soát tính không xác định

| Lỗi | Hệ quả | Hướng cải thiện |
| --- | --- | --- |
| Gọi `Instant.now()` rải rác trong cùng một use case | Các bước có thể dùng timestamp khác nhau, test khó cố định | Tiêm `Clock` và lấy một snapshot `now` khi cần nhất quán |
| Dùng `LocalDate.now()` với múi giờ mặc định của máy | Test khác kết quả khi chạy ở vùng khác | Truyền `Clock`/`ZoneId` theo quy tắc nghiệp vụ |
| Dùng `Thread.sleep(...)` để chờ task trong unit test | Test chậm và dễ flake | Virtual scheduler và kiểm tra kết quả sau `advanceBy` |
| Tự tạo `new Random()` trong phương thức nghiệp vụ | Không ép được nhánh cụ thể | Tiêm nguồn sinh số hoặc strategy |
| Tin rằng `Random(seed)` phù hợp tạo token bảo mật | Có thể dự đoán bí mật | Dùng nguồn mật mã đúng trong production, fake ở test |
| Fake trả giá trị nằm ngoài hợp đồng của generator | Test thông qua dữ liệu không thể xảy ra thật | Fake xác thực bound và số lần gọi |
| Tiến clock ảo nhưng không tiến scheduler ảo | Callback quan sát thời gian sai | Dùng cùng nguồn thời gian và một API advance rõ |
| Virtual scheduler giả định thứ tự giống hệt thread pool thật | Bỏ sót tương tranh và khác biệt execution order | Tách unit test timing khỏi integration/concurrency test |
| Service gọi `executor.shutdown()` sau một request | Các consumer khác không còn dùng được executor | Composition root/runtime sở hữu shutdown |
| Dựa vào reminder để quyết định reservation đã hết hạn | Restart hoặc task chạy trễ làm sai nghiệp vụ | Kiểm tra deadline bằng `Clock` và trạng thái lưu bền vững |
| Coi kết quả test deterministic là bằng chứng delivery đáng tin cậy | Bỏ sót lỗi mạng, queue, transaction và retry | Bổ sung integration và failure-path tests |

## 10. Bài tập tự đánh giá

**Bài 1 — Kiểm tra ranh giới.** Reservation hết hạn lúc `2026-01-15T08:30:00Z`. Theo hợp đồng bài học, nó còn hiệu lực ở `08:29:59.999999999Z` không? Có còn hiệu lực tại đúng `08:30:00Z` không?

*Gợi ý:* Còn hiệu lực ngay trước deadline, hết hiệu lực tại thời điểm bằng deadline. Trong code: `!now.isBefore(expiresAt)` biểu diễn hết hạn.

**Bài 2 — Clock nào?** Một service kiểm tra hạn thanh toán theo timestamp UTC, còn một báo cáo nhóm doanh thu theo ngày tại Việt Nam. Hai trường hợp nên sử dụng kiểu thời gian nào?

*Gợi ý:* Với deadline dùng `Instant` và `Clock` phù hợp. Với quy tắc theo ngày địa phương, dùng `LocalDate` theo `ZoneId.of("Asia/Ho_Chi_Minh")`, tránh lấy timezone ngầm của máy.

**Bài 3 — Random có hợp đồng.** Một fake `nextInt(3)` trả `3` để thử quầy thứ tư. Điều gì sai?

*Gợi ý:* `nextInt(3)` chỉ cho kết quả `0`, `1`, `2`. Fake phải giữ đúng hợp đồng; nếu muốn kiểm tra dữ liệu sai, nên kiểm thử riêng validation ở ranh giới nhận dữ liệu.

**Bài 4 — Không chờ thời gian thật.** Có yêu cầu gửi reminder sau 15 phút. Làm sao kiểm tra rằng reminder chưa chạy ở phút 14 nhưng đã chạy ở phút 15 mà không dùng `Thread.sleep`?

*Gợi ý:* Inject `TaskScheduler`, dùng virtual scheduler, `advanceBy(Duration.ofMinutes(14))` rồi kiểm tra không có event; tiến thêm 1 phút và kiểm tra đúng một event.

**Bài 5 — Scope và thread-safety.** Một singleton service giữ `Random` và scheduler dùng chung. Nếu hai request đồng thời tiêu thụ cùng một nguồn số, liệu seed cố định có đảm bảo hai request luôn nhận cùng kết quả khi chạy test lần nữa?

*Gợi ý:* Không, vì thứ tự các thread gọi nguồn số có thể khác. Cần phân biệt repeatability của generator với repeatability của lịch chạy và chọn scope/fake phù hợp.

**Bài 6 — Nhắc trễ.** Scheduler gửi lời nhắc sau 45 phút, nhưng reservation hết hạn sau 30 phút. Nên làm gì?

*Gợi ý:* Callback kiểm tra lại thời điểm hiện tại và trạng thái reservation trước khi gửi; tránh nhắc cho lượt đã hết hạn. Đừng coi lịch chạy là chính xác tuyệt đối.

**Bài 7 — Executor shutdown.** Trong production, một service tự gọi `shutdownNow()` sau khi đặt lịch reminder. Điều gì có thể xảy ra?

*Gợi ý:* Task chưa chạy có thể bị hủy, task đang chạy có thể bị ngắt và các service khác không đặt thêm task được. Vòng đời executor thuộc composition root/runtime.

**Bài 8 — Test dự đoán được nhưng mạng vẫn lỗi.** Unit test với fake reminder chạy đúng trong virtual time. Có thể kết luận email thật được gửi chắc chắn trong 10 phút không?

*Gợi ý:* Không. Cần kiểm thử adapter, queue, mạng, retry, idempotency và các cam kết độ trễ vận hành. Virtual time chỉ xác minh logic lập lịch của use case.

## 11. Checklist trước khi kết thúc một bài test có thời gian/ngẫu nhiên

- Consumer đã nhận **`Clock` hoặc snapshot `Instant`** thay vì gọi thời gian toàn cục trong logic cần kiểm thử chưa?
- Quy tắc mốc thời gian đã định nghĩa **bằng deadline có hết hạn hay không** chưa?
- Múi giờ nghiệp vụ đã được chỉ rõ, không phụ thuộc timezone của máy chạy test chưa?
- Sinh số có **hợp đồng về bound, tính bảo mật và scope** không? Fake có giữ đúng hợp đồng không?
- Service có nhận scheduler qua constructor nếu nó cần đặt lịch tác vụ không?
- Test có tiến **clock và scheduler ảo nhất quán**, không dùng `Thread.sleep` hoặc chờ job thật không?
- Test đã bao gồm trường hợp **chưa đến hạn, đúng hạn, trễ hạn, tạo lỗi hoặc callback lỗi** theo nhu cầu chưa?
- Có tách logic hết hạn khỏi việc task callback thực sự được chạy không?
- Composition root/runtime có sở hữu thread pool và quản lý shutdown đúng vòng đời không?
- Có kiểm thử tích hợp cho execution order, concurrency, queue/network failure và tính bền vững khi các yếu tố đó quan trọng không?

**Truyền clock, nguồn sinh số và bộ lập lịch** qua constructor giúp đưa những yếu tố khó dự đoán vào **ranh giới có thể thay thế và kiểm thử**. Unit test chọn thời gian, chuỗi số và thời điểm thực thi, còn composition root chọn adapter production và quản lý vòng đời. Cách làm này kết hợp được **DI, IoC, kiểm thử Java thuần và thiết kế scope** trước khi dùng DI container, đồng thời giữ rõ giới hạn: *test xác định giúp chứng minh logic trong các kịch bản đã chọn, không tự chứng minh độ tin cậy của hệ thống thực tế*.
