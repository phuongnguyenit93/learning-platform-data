# Đồng hồ thay thế và thời gian ảo cho mã hỗ trợ

## Thời gian là một dependency cần kiểm soát trong test

Nhiều hành vi của ứng dụng phụ thuộc vào thời điểm hiện tại: token hết hạn, đơn hàng quá hạn thanh toán, phiên đăng nhập timeout, báo cáo theo ngày, cửa sổ retry hoặc tác vụ chỉ chạy sau một khoảng chờ. Nếu code đọc trực tiếp giờ hệ thống, kết quả test sẽ phụ thuộc vào thời điểm test thực sự chạy.

Ví dụ:

~~~java
boolean isExpired(Instant expiresAt) {
    return Instant.now().isAfter(expiresAt);
}
~~~

Test cho method này phải tạo dữ liệu dựa trên đồng hồ thật. Khi test chạy chậm, qua nửa đêm hoặc sát thời điểm hết hạn, kết quả có thể thay đổi. Muốn kiểm tra chính xác thời điểm ngay trước, đúng tại và ngay sau deadline, cần điều khiển nguồn thời gian.

Trong Java, abstraction phù hợp cho thời gian lịch là **java.time.Clock**. Có thể inject Clock vào service thay vì gọi trực tiếp Instant.now(), LocalDate.now() hoặc ZonedDateTime.now() mà không truyền clock.

Với tác vụ reactive có delay, interval hoặc timeout, cần kiểm soát thêm scheduler. Reactor cung cấp **VirtualTimeScheduler** và **StepVerifier.withVirtualTime(...)** để tiến thời gian mô phỏng mà không phải chờ thật.

Hai cơ chế giải quyết hai câu hỏi khác nhau:

- Clock trả lời: “Thời điểm hiện tại của ứng dụng là khi nào?”
- Scheduler quyết định: “Tác vụ được chạy hoặc phát tín hiệu vào lúc nào?”

Thay Clock không tự làm timer chạy nhanh hơn. Virtual time của Reactor cũng không tự thay đổi giá trị trả về từ Clock hoặc giờ hệ điều hành.

## Đưa Clock vào code ứng dụng

### Khai báo Clock như một Spring bean

Có thể đăng ký một Clock dùng chung trong cấu hình:

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Clock.systemUTC() cung cấp thời gian hiện tại theo UTC. Việc dùng UTC cho Instant giúp các timestamp không phụ thuộc timezone mặc định của máy chạy. Khi cần ngày hoặc giờ nghiệp vụ theo một múi giờ cụ thể, hãy chuyển clock sang ZoneId tương ứng tại nơi thực hiện phép chuyển đổi.

Service nhận Clock qua constructor:

~~~java
import java.time.Clock;
import java.time.Instant;

import org.springframework.stereotype.Service;

@Service
class ReservationService {

    private final Clock clock;

    ReservationService(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

Phép so sánh ở đây xem reservation hết hạn tại đúng thời điểm deadline: nếu now bằng expiresAt thì isExpired trả về true. Nếu quy tắc nghiệp vụ yêu cầu còn hiệu lực trong toàn bộ thời điểm bằng deadline, có thể chọn phép so sánh khác; điều quan trọng là quy tắc biên được thể hiện rõ.

Không nên tạo Clock mới trong từng method. Inject một dependency giúp code production dùng giờ hệ thống và test có thể thay bằng đồng hồ cố định hoặc điều khiển được.

### Dùng clock cho các kiểu thời gian khác nhau

Các factory method của java.time hỗ trợ truyền Clock:

~~~java
Instant instant = Instant.now(clock);
LocalDate date = LocalDate.now(clock);
LocalTime time = LocalTime.now(clock);
ZonedDateTime dateTime = ZonedDateTime.now(clock);
~~~

Các lời gọi trên sử dụng thời điểm và timezone của Clock. Tránh dùng các overload không có tham số trong code cần kiểm thử thời gian, vì chúng quay lại đọc giờ hệ thống mặc định.

Với ngày nghiệp vụ, timezone là một phần của quy tắc. Ví dụ một báo cáo chốt ngày theo múi giờ của chi nhánh cần lấy LocalDate theo ZoneId của chi nhánh, không mặc định lấy UTC hoặc timezone của máy chủ:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate = LocalDate.now(clock.withZone(businessZone));
~~~

Clock.withZone(...) giữ cùng nguồn thời gian nhưng trả về clock có timezone được yêu cầu. Instant vẫn đại diện cùng một thời điểm; chỉ cách chuyển đổi sang LocalDate, LocalTime hoặc ZonedDateTime thay đổi.

## Những Clock có sẵn trong Java

| Factory | Hành vi | Trường hợp sử dụng |
| --- | --- | --- |
| Clock.systemUTC() | Đọc giờ hệ thống theo UTC | Timestamp và logic dựa trên Instant |
| Clock.system(zone) | Đọc giờ hệ thống với ZoneId chỉ định | Logic cần chuyển đổi lịch theo timezone |
| Clock.systemDefaultZone() | Dùng timezone mặc định của JVM | Chỉ khi hành vi thực sự phải theo cấu hình máy |
| Clock.fixed(instant, zone) | Luôn trả về cùng một Instant | Test tại một thời điểm xác định |
| Clock.offset(baseClock, duration) | Dịch thời điểm của clock gốc theo một độ lệch cố định | Tạo clock nhìn thấy thời gian ở tương lai hoặc quá khứ |
| Clock.tick(baseClock, duration) | Chỉ quan sát thời gian theo các nhịp được làm tròn | Code cần độ phân giải thời gian thấp hơn |

### Clock.fixed cho test xác định

Clock.fixed(...) là lựa chọn đơn giản nhất khi test cần một thời điểm không đổi:

~~~java
Instant now = Instant.parse("2026-04-15T10:00:00Z");
Clock clock = Clock.fixed(now, ZoneOffset.UTC);

assertThat(clock.instant()).isEqualTo(now);
assertThat(Instant.now(clock)).isEqualTo(now);
~~~

Mọi lần đọc clock đều trả về cùng Instant. Vì vậy test có thể kiểm tra chính xác một nhánh trước deadline, đúng deadline hoặc sau deadline mà không bị ảnh hưởng bởi thời gian chạy test.

Ví dụ kiểm tra quy tắc hết hạn:

~~~java
@Test
void expiresReservationAtTheDeadline() {
    Instant deadline = Instant.parse("2026-04-15T10:00:00Z");
    Clock clock = Clock.fixed(deadline, ZoneOffset.UTC);
    ReservationService service = new ReservationService(clock);

    assertThat(service.isExpired(deadline)).isTrue();
}
~~~

Để kiểm tra ngay trước deadline, tạo một fixed clock sớm hơn một đơn vị thời gian phù hợp:

~~~java
Clock justBeforeDeadline = Clock.fixed(
        deadline.minusNanos(1),
        ZoneOffset.UTC
);
~~~

Với Clock.fixed, thời gian không tự tiến lên khi test chờ. Nếu cần mô phỏng nhiều bước thời gian trong cùng một test, dùng một đồng hồ điều khiển được hoặc tạo nhiều fixed clock cho từng bước.

### Clock.offset để dịch thời gian

Clock.offset(baseClock, duration) tạo clock có thời gian bằng thời gian của clock gốc cộng thêm một Duration:

~~~java
Clock productionClock = Clock.systemUTC();
Clock tomorrowView = Clock.offset(productionClock, Duration.ofDays(1));
~~~

Nếu clock gốc tiếp tục tiến, clock offset cũng tiến theo, nhưng luôn lệch một khoảng cố định. Offset hữu ích khi một thành phần cần quan sát một mốc tương đối. Với test cần giá trị tuyệt đối và lặp lại được, Clock.fixed thường rõ ràng hơn.

### Clock.tick để giới hạn độ phân giải

Clock.tick(baseClock, duration) tạo clock chỉ quan sát các mốc thời gian theo nhịp được chỉ định, ví dụ mỗi giây hoặc mỗi phút:

~~~java
Clock secondClock = Clock.tick(Clock.systemUTC(), Duration.ofSeconds(1));
~~~

Clock.tick phù hợp khi ứng dụng chỉ cần độ phân giải thời gian nhất định. Nó không phải công cụ mô phỏng timer và không làm tác vụ chạy theo nhịp nhanh hơn. Không dùng nó để đo chính xác thời gian đã trôi qua hoặc thay cho scheduler.

## Tạo đồng hồ có thể tiến thời gian trong test

Clock.fixed không thể advance. Nếu một test cần kiểm tra nhiều trạng thái theo thời gian, có thể tạo một Clock nhỏ dành riêng cho test. Dùng AtomicReference giúp các thread đọc cùng một giá trị nhất quán và việc cập nhật được an toàn khi có tác vụ bất đồng bộ.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

final class AdjustableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    AdjustableClock(Instant initial, ZoneId zone) {
        this(new AtomicReference<>(Objects.requireNonNull(initial)),
                Objects.requireNonNull(zone));
    }

    private AdjustableClock(
            AtomicReference<Instant> current,
            ZoneId zone) {
        this.current = current;
        this.zone = zone;
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return new AdjustableClock(current, Objects.requireNonNull(zone));
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    void advance(Duration duration) {
        current.updateAndGet(value -> value.plus(duration));
    }

    void set(Instant instant) {
        current.set(Objects.requireNonNull(instant));
    }
}
~~~

Đây là test fixture, không phải clock mặc định cho production. advance(...) thay đổi thời điểm mà mọi consumer đang dùng cùng instance nhìn thấy. withZone(...) tạo view khác timezone nhưng vẫn chia sẻ cùng nguồn Instant.

Test có thể điều khiển ranh giới hết hạn trong một method:

~~~java
@Test
void becomesExpiredWhenTheClockReachesTheDeadline() {
    Instant start = Instant.parse("2026-04-15T09:59:59Z");
    Instant deadline = Instant.parse("2026-04-15T10:00:00Z");
    AdjustableClock clock = new AdjustableClock(start, ZoneOffset.UTC);
    ReservationService service = new ReservationService(clock);

    assertThat(service.isExpired(deadline)).isFalse();

    clock.advance(Duration.ofSeconds(1));

    assertThat(service.isExpired(deadline)).isTrue();
}
~~~

Test không phải chờ một giây thật. Nó thay đổi giá trị của clock ngay lập tức, nên chạy nhanh và lặp lại được.

Nếu không cần một clock mutable, tránh tự viết abstraction lớn. Clock.fixed thường đủ cho test đơn vị. Chỉ dùng AdjustableClock khi test thực sự cần tiến hoặc lùi qua nhiều mốc thời gian.

## Kiểm tra timezone và ngày chuyển tiếp

Instant biểu diễn một thời điểm toàn cầu; LocalDate và LocalDateTime là giá trị lịch không tự mang timezone. Cùng một Instant có thể tương ứng với hai ngày lịch khác nhau ở hai múi giờ.

Để test quy tắc ngày, cố định cả Instant và ZoneId:

~~~java
Instant instant = Instant.parse("2026-04-15T23:30:00Z");

Clock utcClock = Clock.fixed(instant, ZoneOffset.UTC);
Clock tokyoClock = utcClock.withZone(ZoneId.of("Asia/Tokyo"));

assertThat(LocalDate.now(utcClock))
        .isEqualTo(LocalDate.of(2026, 4, 15));
assertThat(LocalDate.now(tokyoClock))
        .isEqualTo(LocalDate.of(2026, 4, 16));
~~~

Điều này giúp phát hiện lỗi dùng timezone mặc định của máy khi tính ngày chốt sổ, ngày hết hạn hoặc ngày gửi thông báo.

Với timezone có daylight saving time, thời điểm chuyển sang giờ mùa hè hoặc quay về giờ chuẩn có thể làm local time nhảy tới hoặc lặp lại. Hãy test bằng Instant cụ thể ở hai phía của mốc chuyển đổi và ZoneId có quy tắc DST tương ứng. Tránh tự cộng một giờ vào LocalDateTime để mô phỏng DST; hãy để ZoneRules của timezone thực hiện phép chuyển đổi.

Nếu nghiệp vụ yêu cầu thời điểm chính xác, lưu và so sánh Instant. Chỉ chuyển sang ZonedDateTime hoặc LocalDate khi cần áp dụng quy tắc lịch theo vùng. LocalDateTime không đủ thông tin để xác định duy nhất một thời điểm khi có nhiều timezone hoặc DST.

## Thời gian ảo cho Reactor

Clock điều khiển các lời gọi lấy giờ hiện tại. Các operator như Mono.delay, Flux.interval, timeout hoặc delayElements lại phụ thuộc scheduler. Trong Reactor, VirtualTimeScheduler cho phép tiến scheduler clock mà không phải đợi thời gian thực.

Reactor Test cung cấp StepVerifier.withVirtualTime(...) để cài đặt virtual scheduler cho publisher trong kịch bản kiểm thử:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void emitsThreeTicksWithoutWaitingThreeRealSeconds() {
    StepVerifier.withVirtualTime(
                    () -> Flux.interval(Duration.ofSeconds(1)).take(3))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectNext(0L, 1L, 2L)
            .verifyComplete();
}
~~~

Flux.interval phát phần tử đầu tiên sau một giây, sau đó mỗi giây phát thêm một phần tử. thenAwait(Duration.ofSeconds(3)) tiến virtual scheduler qua ba giây, khiến cả ba phần tử được phát mà test không cần Thread.sleep.

### Tạo publisher bên trong supplier

Publisher phải được tạo bên trong supplier truyền cho withVirtualTime:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(2))
        .thenAwait(Duration.ofSeconds(2))
        .expectNext(0L, 1L)
        .verifyComplete();
~~~

Không tạo publisher có timer trước rồi mới đưa biến đó vào supplier:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));

StepVerifier.withVirtualTime(() -> ticks)
        .thenAwait(Duration.ofSeconds(2))
        .expectNext(0L, 1L)
        .thenCancel()
        .verify();
~~~

Trong ví dụ sai về mặt thiết lập virtual time, Flux.interval đã chọn scheduler khi publisher được tạo. Khi supplier được gọi, publisher đã giữ scheduler cũ nên việc cài virtual scheduler không điều khiển được timer đó. Hãy tạo các operator phụ thuộc scheduler bên trong supplier.

### Dùng scheduler được inject rõ ràng

Với service nhận Scheduler qua constructor, có thể cung cấp VirtualTimeScheduler cho chính service. Khi đó StepVerifier cần sử dụng cùng scheduler:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;

class HeartbeatService {

    private final Scheduler scheduler;

    HeartbeatService(Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    Flux<Long> heartbeats() {
        return Flux.interval(Duration.ofSeconds(1), scheduler).take(2);
    }
}
~~~

Test:

~~~java
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

@Test
void advancesTheInjectedScheduler() {
    VirtualTimeScheduler scheduler = VirtualTimeScheduler.create();

    try {
        HeartbeatService service = new HeartbeatService(scheduler);

        StepVerifier.withVirtualTime(
                        service::heartbeats,
                        () -> scheduler,
                        Long.MAX_VALUE)
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(2))
                .expectNext(0L, 1L)
                .verifyComplete();
    } finally {
        scheduler.dispose();
    }
}
~~~

Khi scheduler được tạo và inject riêng, test phải bảo đảm publisher và StepVerifier cùng dùng instance VirtualTimeScheduler đó. dispose() trong finally giải phóng scheduler sau test, kể cả khi assertion thất bại.

## Clock và virtual scheduler không tự tiến cùng nhau

Một pipeline có thể vừa chờ timer vừa đọc thời gian nghiệp vụ:

~~~java
Mono<Instant> timestampAfterDelay(
        Clock clock,
        Scheduler scheduler) {
    return Mono.delay(Duration.ofSeconds(5), scheduler)
            .map(ignored -> clock.instant());
}
~~~

Nếu chỉ tiến VirtualTimeScheduler, timer sẽ phát sau năm giây ảo nhưng Clock.systemUTC() vẫn trả về giờ hệ thống thật. Nếu chỉ advance một AdjustableClock, giá trị now thay đổi nhưng Mono.delay vẫn chưa phát cho đến khi scheduler được tiến.

Khi test cần điều khiển cả hai, hãy inject cả Clock và Scheduler rồi tiến từng dependency một cách rõ ràng:

~~~java
AdjustableClock clock = new AdjustableClock(
        Instant.parse("2026-04-15T10:00:00Z"),
        ZoneOffset.UTC
);
VirtualTimeScheduler scheduler = VirtualTimeScheduler.create();

try {
    Mono<Instant> result = timestampAfterDelay(clock, scheduler);

    StepVerifier.withVirtualTime(
                    () -> result,
                    () -> scheduler,
                    Long.MAX_VALUE)
            .expectSubscription()
            .then(() -> clock.advance(Duration.ofSeconds(5)))
            .thenAwait(Duration.ofSeconds(5))
            .expectNext(Instant.parse("2026-04-15T10:00:05Z"))
            .verifyComplete();
} finally {
    scheduler.dispose();
}
~~~

Ví dụ này minh họa thứ tự điều khiển: test cập nhật Clock rồi mới tiến scheduler để timer phát tín hiệu. Trong code thực tế, cần tạo publisher bên trong supplier nếu việc tạo publisher có thể chụp scheduler mặc định. Với scheduler được inject tường minh như trên, bảo đảm service sử dụng đúng instance virtual.

Không nên mong đợi một lệnh thenAwait(...) tự cập nhật Clock. Nó chỉ điều khiển scheduler mà StepVerifier đang dùng.

## Phân biệt thời gian lịch với thời gian đo khoảng trôi qua

Clock biểu diễn thời gian lịch (wall-clock time). Giá trị của system clock có thể được điều chỉnh bởi hệ điều hành, đồng bộ NTP hoặc thay đổi cấu hình. Vì vậy, nó không phải lựa chọn phù hợp để đo chính xác một khoảng thời gian đã trôi qua.

Ví dụ không nên dùng Instant.now() hai lần để đo timeout nội bộ nếu hệ thống có thể thay đổi giờ giữa hai lần đọc:

~~~java
long started = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - started;
~~~

System.nanoTime() được thiết kế cho phép đo thời lượng tương đối trong cùng JVM. Giá trị của nó không phải timestamp lịch và không thể chuyển thành ngày giờ. Dùng Clock cho deadline nghiệp vụ hoặc timestamp cần lưu; dùng monotonic source như System.nanoTime() cho thời gian thực thi, timeout nội bộ và đo hiệu năng.

Trong code có thể test, cân nhắc bọc cả monotonic source sau một interface riêng nếu cần kiểm soát elapsed time. Không ép Clock gánh nhiệm vụ của một bộ đo thời gian đơn điệu.

## Spring TaskScheduler và @Scheduled

VirtualTimeScheduler của Reactor điều khiển các operator Reactor dùng scheduler tương ứng. Nó không tự động thay thế scheduler mà Spring dùng để chạy method @Scheduled hoặc tác vụ được đăng ký với TaskScheduler.

Tương tự, thay Clock bean không làm một tác vụ @Scheduled được gọi ngay. Clock cung cấp thời điểm mà code quan sát; TaskScheduler quyết định thời điểm task được kích hoạt.

Với mã hỗ trợ lịch chạy, hãy tách hai trách nhiệm:

- Phần nghiệp vụ tính deadline, ngày đến hạn hoặc có nên thực hiện công việc hay không nhận Clock qua constructor.
- Phần điều phối thời điểm chạy sử dụng TaskScheduler hoặc cơ chế scheduling tương ứng.

Test đơn vị có thể gọi trực tiếp phương thức nghiệp vụ với Clock.fixed hoặc AdjustableClock để kiểm tra điều kiện thời gian. Test tích hợp cho scheduling cần điều khiển scheduler, trigger hoặc tín hiệu hoàn tất; không chỉ thay Clock rồi chờ annotation @Scheduled chạy.

Ví dụ service tách quyết định nghiệp vụ khỏi cơ chế kích hoạt:

~~~java
class CleanupService {

    private final Clock clock;

    CleanupService(Clock clock) {
        this.clock = clock;
    }

    boolean shouldRemove(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }

    void runCleanup() {
        // Thực hiện thao tác dọn dữ liệu.
    }
}
~~~

Test có thể kiểm tra shouldRemove(...) tại nhiều mốc thời gian mà không phải khởi động thread scheduler. Một test khác mới cần xác nhận trigger hoặc cơ chế scheduling gọi runCleanup() đúng lịch.

## Những lỗi thường gặp

### Gọi Instant.now() trực tiếp trong service

Code phụ thuộc giờ hệ thống thật, khiến test khó tái hiện ranh giới thời gian. Inject Clock và dùng Instant.now(clock) hoặc clock.instant().

### Dùng Clock.fixed rồi mong thời gian tự trôi

Clock.fixed luôn trả cùng Instant. Nếu cần mô phỏng nhiều thời điểm, tạo clock mới cho từng bước hoặc dùng AdjustableClock trong test.

### Dùng virtual scheduler để thay giờ nghiệp vụ

VirtualTimeScheduler chỉ điều khiển timer của scheduler. Các lời gọi Instant.now(), LocalDate.now() hoặc Clock.systemUTC() vẫn đọc thời gian lịch của chúng.

### Tạo Flux.interval trước withVirtualTime

Publisher có thể đã giữ scheduler thật trước khi StepVerifier cài virtual scheduler. Tạo publisher phụ thuộc timer bên trong supplier của withVirtualTime.

### Tạo scheduler riêng nhưng không đưa nó vào virtual test

Một scheduler đã được tạo tường minh không tự động bị thay thế chỉ vì test dùng withVirtualTime. Inject VirtualTimeScheduler vào service và cung cấp đúng instance cho StepVerifier.

### Dùng Thread.sleep để chờ timer

Sleep làm test chậm và phụ thuộc lịch chạy của máy. Với Reactor, dùng thenAwait hoặc expectNoEvent trên virtual scheduler; với code dựa trên Clock, điều chỉnh clock trực tiếp.

### Dùng Clock để đo elapsed time

Giờ hệ thống có thể nhảy. Dùng System.nanoTime() hoặc một monotonic abstraction cho timeout và thời lượng thực thi.

### Dùng timezone mặc định cho quy tắc nghiệp vụ

Test có thể chạy trên máy có timezone khác. Chỉ định ZoneId rõ ràng và cố định Instant khi kiểm tra ngày, giờ hoặc DST.

### Quên dispose scheduler tự tạo

VirtualTimeScheduler riêng nên được dispose sau test. Đặt trong finally để scheduler được dọn ngay cả khi assertion thất bại.

## Chọn công cụ theo loại thời gian cần điều khiển

| Nhu cầu | Công cụ | Cách kiểm soát |
| --- | --- | --- |
| Kiểm tra token hoặc reservation hết hạn | Clock | Inject Clock.fixed tại trước, đúng và sau deadline |
| Kiểm tra ngày nghiệp vụ theo timezone | Clock + ZoneId | Cố định Instant và chỉ định zone |
| Tiến thời gian nhiều bước trong một test | AdjustableClock | Gọi advance(...) hoặc set(...) |
| Mô phỏng giờ tương đối lệch khỏi giờ gốc | Clock.offset | Tạo clock có Duration offset |
| Kiểm tra Mono.delay hoặc Flux.interval | VirtualTimeScheduler | StepVerifier.withVirtualTime và thenAwait |
| Kiểm tra reactive service có Scheduler riêng | Scheduler được inject + VirtualTimeScheduler | Cấp cùng scheduler cho service và StepVerifier |
| Kiểm tra @Scheduled hoặc TaskScheduler | Cơ chế scheduler của Spring | Điều khiển trigger/scheduler hoặc kiểm tra riêng phần nghiệp vụ |
| Đo thời lượng hoặc timeout nội bộ | Monotonic time source | System.nanoTime() hoặc abstraction tương ứng |

## Quy trình xây dựng test thời gian xác định

1. Xác định code đang hỏi thời điểm hiện tại, chờ timer hay đo khoảng trôi qua.
2. Inject Clock cho logic lịch và Scheduler cho các tác vụ có lịch chạy.
3. Chọn Clock.fixed cho một mốc cố định; chỉ tạo AdjustableClock nếu cần thay đổi thời gian trong test.
4. Cố định ZoneId khi kiểm tra LocalDate, LocalTime, ZonedDateTime hoặc quy tắc DST.
5. Với Reactor, tạo publisher bên trong supplier của withVirtualTime hoặc inject VirtualTimeScheduler rõ ràng.
6. Tiến Clock và scheduler độc lập theo đúng thứ tự mà hành vi cần kiểm tra.
7. Assert cả ranh giới thời gian (trước, tại và sau deadline) lẫn kết quả nghiệp vụ.
8. Dispose scheduler tự tạo và bảo đảm không để task hoặc subscription nền còn chạy sau test.

Đồng hồ thay thế làm cho quyết định nghiệp vụ dựa trên thời điểm có thể tái hiện; thời gian ảo làm cho các timer reactive có thể được kiểm tra nhanh và xác định. Khi tách Clock khỏi Scheduler, test biết chính xác dependency nào đang được điều khiển và tránh nhầm việc thay đổi giờ lịch với việc kích hoạt một tác vụ.
