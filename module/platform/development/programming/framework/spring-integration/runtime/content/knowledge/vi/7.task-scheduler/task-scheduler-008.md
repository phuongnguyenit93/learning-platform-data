# Clock, time zone và kiểm thử lịch

Một poller có thể chạy đúng chu kỳ nhưng vẫn sai giờ nghiệp vụ nếu ứng dụng dùng múi giờ của máy chủ thay vì múi giờ của nơi vận hành. Lịch cron còn chịu ảnh hưởng của thay đổi giờ mùa hè (Daylight Saving Time - DST), thời gian chạy của lần poll trước và cách scheduler xử lý những lần kích hoạt bị lỡ.

Để lịch chạy ổn định và kiểm thử được, cần phân biệt thời điểm tuyệt đối, múi giờ, đồng hồ cung cấp thời gian và quy tắc trigger. Trong Java, `Instant` biểu diễn một điểm trên timeline; `ZoneId` biểu diễn quy tắc múi giờ; `Clock` cung cấp thời điểm hiện tại theo một zone; còn `CronTrigger` tính lần chạy kế tiếp theo biểu thức lịch.

## 1. Instant, LocalDateTime, ZoneId và Clock

Các kiểu thời gian trong `java.time` có mục đích khác nhau:

| Kiểu | Ý nghĩa | Ví dụ sử dụng |
|---|---|---|
| `Instant` | Một thời điểm tuyệt đối trên UTC timeline | Lưu timestamp, so sánh thời điểm giữa các hệ thống |
| `LocalDateTime` | Ngày và giờ trên đồng hồ địa phương, không có múi giờ | Dữ liệu lịch chưa gắn địa điểm hoặc zone |
| `ZoneId` | Quy tắc múi giờ, bao gồm offset và lịch sử thay đổi | `Asia/Ho_Chi_Minh`, `Europe/Berlin` |
| `ZonedDateTime` | Ngày giờ địa phương gắn với `ZoneId` | Diễn giải “09:00 giờ địa phương” thành một thời điểm |
| `Clock` | Nguồn cung cấp thời điểm hiện tại và zone | Inject thời gian vào code để kiểm thử xác định |

Không nên dùng `LocalDateTime` làm timestamp trao đổi giữa các dịch vụ vì giá trị đó không cho biết offset hoặc instant tương ứng. Nếu cần ghi nhận thời điểm một message được nhận hoặc xử lý, thường lưu `Instant`. Nếu cần mô tả một lịch như “chạy lúc 09:00 mỗi ngày làm việc tại Việt Nam”, lưu cả biểu thức cron và ID múi giờ như `Asia/Ho_Chi_Minh`.

Ví dụ tạo clock:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Clock utcClock = Clock.systemUTC();
Clock businessClock = Clock.system(businessZone);

Instant now = Instant.now(utcClock);
LocalDate todayInBusinessZone = LocalDate.now(businessClock);
~~~

`Clock` có thể được inject vào service thay vì gọi trực tiếp `Instant.now()` hoặc `LocalDate.now()` ở nhiều nơi. Khi kiểm thử, thay clock hệ thống bằng `Clock.fixed(...)` hoặc `Clock.offset(...)` để kiểm soát thời điểm hiện tại.

## 2. Múi giờ của lịch không nhất thiết là múi giờ máy chủ

`TaskScheduler` cung cấp `Clock` thông qua `getClock()`. Clock mặc định của scheduler thường dùng system clock và múi giờ mặc định của JVM. `CronTrigger` không nhận zone riêng sẽ dùng zone từ `TriggerContext.getClock()`. Vì vậy, nếu triển khai cùng một ứng dụng trên máy chủ có cấu hình timezone khác nhau, lịch cron dựa trên mặc định có thể chạy vào giờ địa phương khác nhau.

Có hai cách đặt múi giờ rõ ràng:

1. Cấu hình `Clock` của `TaskScheduler` để các trigger dùng clock đó có zone nhất quán.
2. Truyền `TimeZone` hoặc `ZoneId` cụ thể cho `CronTrigger`/DSL poller khi từng lịch có múi giờ riêng.

Ví dụ cấu hình scheduler có zone rõ ràng:

~~~java
@Bean
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("integration-scheduler-");
    scheduler.setClock(Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")));
    return scheduler;
}
~~~

`setClock(...)` đặt clock mà scheduler dùng cho việc tính lịch. Đây là cách đặt zone mặc định cho các trigger dựa vào `TriggerContext` của scheduler. Nếu một poller có lịch theo zone riêng, hãy truyền zone trực tiếp cho trigger để ý định đó không phụ thuộc cấu hình toàn cục.

Với Spring Integration Java DSL, có thể truyền `TimeZone` cho `Pollers.cron`:

~~~java
@Configuration
public class ReportFlowConfiguration {

    private final TimeZone reportTimeZone =
            TimeZone.getTimeZone(ZoneId.of("Asia/Ho_Chi_Minh"));

    @Bean
    IntegrationFlow weekdayReportFlow(ReportService reportService) {
        return IntegrationFlow.from(reportService::loadPendingReports,
                        endpoint -> endpoint.poller(
                                Pollers.cron("0 0 9 * * MON-FRI", reportTimeZone)))
                .handle(reportService, "sendDailyReport")
                .get();
    }
}
~~~

Biểu thức trên dùng cron của Spring với sáu trường: giây, phút, giờ, ngày trong tháng, tháng và thứ trong tuần. `0 0 9 * * MON-FRI` có nghĩa là 09:00:00 từ thứ Hai đến thứ Sáu theo múi giờ đã truyền. Đây là lịch theo giờ trên đồng hồ địa phương, không phải khoảng cách cố định 24 giờ tính từ lần chạy trước.

Có thể cấu hình trực tiếp `CronTrigger` nếu muốn dùng API trigger:

~~~java
CronTrigger trigger = new CronTrigger(
        "0 0 9 * * MON-FRI",
        ZoneId.of("Asia/Ho_Chi_Minh"));

PollerSpec poller = Pollers.trigger(trigger);
~~~

Hãy dùng ID zone IANA như `Asia/Ho_Chi_Minh` hoặc `Europe/Berlin`. Tránh hard-code offset như `UTC+7` cho lịch dài hạn nếu quy tắc của địa điểm có thể thay đổi theo luật. `ZoneId.of(...)` cũng giúp phát hiện ID không hợp lệ ngay lúc cấu hình.

## 3. Cron, fixed delay và fixed rate mô tả những loại lịch khác nhau

Không phải mọi lịch đều cần múi giờ:

| Trigger | Mô tả | Ví dụ phù hợp |
|---|---|---|
| Fixed delay | Chạy lại sau một khoảng thời gian tính từ lúc lần thực thi trước hoàn tất | Kiểm tra queue định kỳ, nghỉ 10 giây sau mỗi lần xử lý |
| Fixed rate | Duy trì nhịp kích hoạt theo khoảng thời gian đều | Đo trạng thái định kỳ mỗi 30 giây |
| Cron | Chạy tại các thời điểm theo lịch ngày/giờ địa phương | Gửi báo cáo lúc 09:00 ngày làm việc |

Ví dụ:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(10));
Pollers.fixedRate(Duration.ofSeconds(30));
Pollers.cron("0 0 9 * * MON-FRI", timeZone);
~~~

Fixed delay và fixed rate dùng `Duration`; chúng mô tả khoảng thời gian trôi qua, không phải giờ địa phương. Thay đổi timezone máy chủ không biến fixed delay 24 giờ thành “09:00 mỗi ngày”. Nếu yêu cầu là một giờ cố định theo lịch địa phương, dùng cron với zone rõ ràng.

Với fixed rate, nếu công việc kéo dài hơn chu kỳ, cách thực thi tiếp theo phụ thuộc scheduler và chính sách thực thi. Với cron, `CronTrigger` mặc định trong Spring dùng lenient execution: lần kế tiếp được tính từ thời điểm hoàn tất lần trước, do đó các mốc cron có thể bị bỏ qua khi task chạy quá lâu. Từ Spring Framework 6.1.3 có `CronTrigger.forFixedExecution(...)` để tính theo lần scheduled trước và bù các lần kích hoạt bị lỡ trong thời gian scheduler còn giữ trigger context; điều này có thể tạo các lần chạy muộn liên tiếp sau khi task bị chậm. Trạng thái trigger context không tự được lưu bền vững qua JVM restart. Chỉ chọn fixed execution khi nghiệp vụ thực sự cần catch-up.

## 4. Daylight Saving Time và lịch địa phương

Một số múi giờ thay đổi offset theo mùa. Khi đồng hồ chuyển sang giờ mùa hè, một khoảng giờ địa phương có thể không tồn tại. Khi đồng hồ quay lại giờ chuẩn, một khoảng giờ có thể xuất hiện hai lần.

Ví dụ với `Europe/Berlin`, lịch chạy lúc 02:30 có thể gặp hai tình huống:

- **Spring forward:** ngày chuyển giờ, đồng hồ nhảy qua một số giờ địa phương; 02:30 có thể không tồn tại.
- **Fall back:** đồng hồ quay lại, 02:30 có thể xuất hiện hai lần với hai offset khác nhau.

Đừng giả định một biểu thức cron ở mọi timezone luôn tạo ra đúng một lần chạy trong mỗi ngày địa phương. Hành vi tại gap/overlap còn phụ thuộc cách `CronExpression` tính `ZonedDateTime`, loại trigger và chính sách thực thi. Hãy kiểm thử quanh các mốc chuyển DST của những zone mà ứng dụng hỗ trợ.

Nếu lịch nghiệp vụ không chấp nhận bỏ lỡ hoặc chạy lặp, cần định nghĩa rõ quy tắc: bỏ qua giờ không tồn tại, chạy ở thời điểm hợp lệ kế tiếp, chọn lần xuất hiện đầu hay lần thứ hai trong overlap, hoặc đảm bảo một lần thực hiện theo ngày nghiệp vụ bằng idempotency key. Scheduler chỉ tạo trigger; tính duy nhất của nghiệp vụ vẫn nên được bảo vệ ở tầng xử lý.

Một cách bảo vệ là lưu khóa chạy theo ngày nghiệp vụ và định danh lịch:

~~~java
LocalDate businessDate = LocalDate.now(clock.withZone(businessZone));
String executionKey = "daily-report:" + businessDate;

if (executionRepository.tryMarkStarted(executionKey)) {
    reportService.generateFor(businessDate);
}
~~~

`tryMarkStarted` cần được triển khai bằng thao tác nguyên tử, ví dụ unique constraint hoặc insert-if-absent trong database. Kiểm tra bằng `if` rồi insert tách rời có thể cho phép hai instance cùng chạy khi chúng nhận trigger gần như đồng thời.

## 5. Cấu hình clock cho TaskScheduler

Khi ứng dụng có nhiều lịch cron dùng cùng một zone, có thể cấu hình clock của scheduler làm mặc định:

~~~java
@Configuration
public class SchedulerConfiguration {

    @Bean
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("si-scheduler-");
        scheduler.setClock(Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")));
        return scheduler;
    }
}
~~~

Khi dùng `Pollers.cron(expression)` mà không truyền timezone, `CronTrigger` lấy zone từ clock của `TriggerContext`, tức clock do scheduler cung cấp. Khi dùng `Pollers.cron(expression, timeZone)`, zone đã được chỉ định trực tiếp cho trigger. Cách thứ hai dễ đọc hơn khi lịch thuộc về một địa điểm cụ thể; cách thứ nhất hữu ích khi muốn đặt một quy tắc chung cho toàn bộ scheduler.

`TaskScheduler` có thể được dùng chung bởi nhiều poller và tác vụ khác. Đặt pool size phù hợp với số tác vụ schedule và đặc tính thực thi. Nếu một scheduled task chạy lâu trên thread scheduler, nó có thể làm trễ các tác vụ khác khi pool quá nhỏ. Nếu poller chuyển công việc sang executor khác, cần phân biệt scheduler thread với worker thread của poller.

## 6. Kiểm thử trigger một cách xác định

Không nên kiểm thử lịch cron bằng cách chờ tới 09:00 thật hoặc dựa vào timezone của máy phát triển. Hãy kiểm thử phép tính lần chạy kế tiếp bằng clock cố định.

Ví dụ dùng `CronTrigger` và `SimpleTriggerContext`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.support.CronTrigger;
import org.springframework.scheduling.support.SimpleTriggerContext;

class ReportScheduleTests {

    @Test
    void calculatesNextWeekdayRunInVietnamTime() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-20T01:00:00Z"), zone);

        CronTrigger trigger = new CronTrigger(
                "0 0 9 * * MON-FRI", zone);
        SimpleTriggerContext context = new SimpleTriggerContext(clock);

        Instant nextExecution = trigger.nextExecution(context);

        assertEquals(Instant.parse("2026-11-20T02:00:00Z"), nextExecution);
    }
}
~~~

Clock cố định trong ví dụ tương ứng 08:00 ngày thứ Sáu 20/11/2026 tại `Asia/Ho_Chi_Minh`. Lần chạy kế tiếp là 09:00 cùng ngày, tương ứng 02:00 UTC. Phép kiểm thử không cần sleep và không phụ thuộc timezone mặc định của máy chạy test.

Nếu cần kiểm thử riêng biểu thức cron mà không cần `TaskScheduler`, có thể dùng `CronExpression` trực tiếp với `ZonedDateTime` làm mốc. Điều đó giúp kiểm tra các ngày trong tuần, cuối tháng, ngày lễ theo lịch tự định nghĩa hoặc các thời điểm chuyển DST.

## 7. Clock cố định không phải đồng hồ giả lập scheduler

`Clock.fixed(...)` giúp code đọc thời gian và trigger calculation trả về cùng một instant trong suốt bài test. Nó không tự làm thời gian của JVM hoặc thread scheduler chạy nhanh hơn. Nếu dùng clock cố định cho `ThreadPoolTaskScheduler`, các phép tính lịch có thể tiếp tục nhìn thấy cùng một thời điểm trong khi executor vẫn chờ theo thời gian thực của hệ điều hành.

Vì vậy, nên chia kiểm thử thành các lớp:

1. **Unit test thời gian nghiệp vụ:** inject `Clock.fixed` để kiểm tra ngày nghiệp vụ, cutoff time và idempotency key.
2. **Unit test trigger:** dùng `CronTrigger.nextExecution(...)` cùng `SimpleTriggerContext(clock)` để kiểm tra instant tiếp theo.
3. **Test DST và timezone:** dùng các instant cố định trước/sau gap hoặc overlap, xác nhận quy tắc mong muốn.
4. **Integration test scheduler:** dùng chu kỳ ngắn, `CountDownLatch`/Awaitility hoặc scheduler giả để kiểm tra task được kích hoạt và flow được gọi. Đặt timeout rõ ràng, không chờ lịch production hàng giờ.
5. **Test khởi động lại:** xác minh lịch có được đăng ký lại và chính sách catch-up/skip có đúng yêu cầu sau downtime.

Một integration test với lịch 100 ms chỉ chứng minh scheduler kích hoạt trong điều kiện test đó. Nó không chứng minh cron chạy đúng sau DST, khi JVM thay đổi timezone hoặc khi task kéo dài hơn chu kỳ.

## 8. Kiểm thử DST và các biên lịch

Với từng `ZoneId` được hỗ trợ, tạo bộ test cho các tình huống sau:

- Thời điểm ngay trước và sau nửa đêm để kiểm tra chuyển ngày.
- Ngày cuối tháng và tháng ngắn để kiểm tra lịch theo ngày.
- Ngày cuối tuần và ngày đầu tuần để kiểm tra biểu thức thứ.
- Mốc bắt đầu DST, khi một giờ địa phương không tồn tại.
- Mốc kết thúc DST, khi một giờ địa phương xuất hiện hai lần.
- Task chạy lâu hơn khoảng cách giữa hai lần cron để kiểm tra lenient hay fixed execution.
- Ứng dụng restart sau khi bỏ lỡ một hoặc nhiều mốc lịch; xác minh có lưu lần scheduled gần nhất và khôi phục trigger context hay không.

Ví dụ tạo instant quanh một ngày chuyển DST:

~~~java
ZoneId berlin = ZoneId.of("Europe/Berlin");

Instant beforeTransition = Instant.parse("2026-03-29T00:30:00Z");
Instant afterTransition = Instant.parse("2026-03-29T01:30:00Z");

ZonedDateTime before = beforeTransition.atZone(berlin);
ZonedDateTime after = afterTransition.atZone(berlin);
~~~

So sánh `before` và `after` để xác nhận offset địa phương đã thay đổi theo rule database của JDK. Với lịch thực tế, hãy kiểm thử kết quả `nextExecution` cho từng instant và ghi rõ mong muốn khi giờ lịch không tồn tại hoặc xuất hiện hai lần.

Không hard-code offset mùa hè hoặc mùa đông. `ZoneId` dùng timezone database đi kèm JDK; khi luật timezone thay đổi, cần cập nhật JDK/runtime để có rule mới. Với hệ thống chạy lâu, nên ghi log cả instant và zoned time khi điều tra lịch bị lệch.

## 9. Lenient execution, fixed execution và downtime

Cron không chỉ xác định “mấy giờ chạy”; nó còn cần quy tắc xử lý khi lần trước chưa hoàn tất hoặc ứng dụng đã ngừng trong lúc có nhiều mốc lịch.

| Chính sách | Cách tính lần kế tiếp | Hệ quả |
|---|---|---|
| Lenient execution (mặc định của `CronTrigger`) | Dựa trên thời điểm hoàn tất lần trước | Mốc cron xảy ra trong lúc task còn chạy có thể bị bỏ qua |
| Fixed execution (`CronTrigger.forFixedExecution`, Spring Framework 6.1.3+) | Dựa trên thời điểm scheduled trước đó trong trigger context hiện tại | Các mốc bị lỡ khi task chạy lâu được chạy bù, có thể tạo nhiều lần chạy muộn liên tiếp |

Ví dụ dùng fixed execution trong Java DSL:

~~~java
@Bean
IntegrationFlow catchUpFlow(ReportService reportService) {
    CronTrigger trigger = CronTrigger.forFixedExecution("0 0 9 * * MON-FRI");

    return IntegrationFlow.from(reportService::loadPendingReports,
                    endpoint -> endpoint.poller(Pollers.trigger(trigger)))
            .handle(reportService, "sendDailyReport")
            .get();
}
~~~

Factory `forFixedExecution` trong Spring Framework 6.1.3+ sử dụng zone từ `TaskScheduler` clock. Nếu cần zone cụ thể, cấu hình clock của scheduler bằng `Clock.system(zone)` và xác minh poller đang dùng scheduler đó. Với lịch cần explicit timezone trực tiếp, `Pollers.cron(expression, timeZone)` tạo cron trigger theo zone chỉ định và dùng semantics lenient mặc định.

Nếu cần catch-up qua cả JVM restart, ứng dụng phải lưu bền vững mốc scheduled gần nhất rồi khôi phục bằng `CronTrigger.resumeFixedExecution(expression, resumptionTimestamp)` (hoặc chính sách resume lenient tương ứng). Chỉ gọi `forFixedExecution(...)` sau khi restart sẽ khởi tạo trigger từ clock hiện tại nếu context chưa có timestamp trước đó; nó không tự biết các mốc đã bị lỡ trong downtime. Việc lưu và cập nhật timestamp cần nhất quán với kết quả nghiệp vụ để tránh chạy thiếu hoặc chạy trùng.

Catch-up có thể hữu ích cho việc đồng bộ dữ liệu cần xử lý đủ từng mốc, nhưng có thể gây tải đột biến sau downtime. Nếu chỉ cần trạng thái mới nhất, bỏ qua các mốc cũ và chạy một lần có thể hợp lý hơn. Dù chọn chính sách nào, tác vụ vẫn nên idempotent và có khóa nghiệp vụ để tránh chạy trùng khi nhiều instance cùng khởi động.

## 10. Đồng bộ đồng hồ và quan sát lịch runtime

`Clock.system(...)` dựa trên đồng hồ hệ thống. Trong môi trường production, cần đồng bộ giờ máy chủ bằng NTP hoặc cơ chế quản trị thời gian của nền tảng. Nếu đồng hồ hệ thống bị nhảy đáng kể, các phép tính dựa trên wall clock và trigger có thể bị ảnh hưởng.

Để chẩn đoán lịch, ghi nhận:

- Cron expression và `ZoneId` thực tế của trigger.
- `Instant` được tính cho lần chạy kế tiếp.
- Scheduled time, actual start time và completion time của lần chạy gần nhất.
- Thời gian thực thi, số lần bị bỏ qua hoặc chạy bù nếu có.
- Trạng thái scheduler, số task active và lỗi khi submit/thực thi task.
- Phiên bản Spring Framework/Spring Integration và timezone database của JDK.

Không dùng `LocalDateTime` đơn độc trong log khi cần đối chiếu giữa nhiều máy chủ. Ghi ISO-8601 có offset hoặc UTC instant, ví dụ `2026-11-20T09:00:00+07:00` và `2026-11-20T02:00:00Z`. Khi đo thời lượng thực thi, dùng Micrometer Timer hoặc monotonic time như `System.nanoTime()` thay vì trừ hai wall-clock timestamp có thể bị điều chỉnh.

## 11. Checklist thiết kế và kiểm thử lịch

- [ ] Chọn `Instant` cho timestamp và `ZoneId` cho lịch địa phương.
- [ ] Inject `Clock` vào code nghiệp vụ thay vì gọi `now()` trực tiếp ở nhiều nơi.
- [ ] Không phụ thuộc múi giờ mặc định của JVM cho lịch production.
- [ ] Dùng cron khi yêu cầu là giờ/ngày địa phương; dùng `Duration` cho khoảng thời gian trôi qua.
- [ ] Truyền zone rõ ràng qua `Pollers.cron(expression, timeZone)` hoặc cấu hình clock của scheduler.
- [ ] Kiểm tra cron của Spring có sáu trường, bắt đầu bằng giây.
- [ ] Kiểm thử ngày cuối tháng, ngày trong tuần và các mốc DST.
- [ ] Chọn lenient hay fixed execution theo chính sách task chạy lâu; nếu cần catch-up qua JVM restart, lưu và khôi phục scheduled timestamp.
- [ ] Dùng `Clock.fixed` cho unit test trigger; không xem nó là đồng hồ giả lập thread scheduler.
- [ ] Kiểm thử idempotency khi nhiều instance cùng chạy lịch.
- [ ] Ghi log cả instant, zone, scheduled time và actual time để điều tra lệch lịch.

Khi tách bạch clock, timezone và trigger, lịch Spring Integration sẽ có ý nghĩa nhất quán giữa môi trường phát triển, staging và production. Kiểm thử bằng instant cố định giúp xác nhận phép tính lịch; kiểm thử DST, downtime và tính idempotent giúp xác nhận hành vi vận hành mà một unit test đơn lẻ không thể bao quát.

## Tài liệu tham khảo

- [Spring Integration API: Pollers](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/dsl/Pollers.html)
- [Spring Framework API: CronTrigger](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronTrigger.html)
- [Spring Framework API: SimpleTriggerContext](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/SimpleTriggerContext.html)
- [Spring Framework API: TaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework API: ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
