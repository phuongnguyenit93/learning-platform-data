# Clock và vai trò của đồng hồ đối với ghi nhận hoặc công bố

Metrics có thể phản ánh trạng thái hiện tại, số sự kiện tích lũy hoặc thời lượng của một thao tác. Với các phép đo liên quan đến thời gian, Micrometer cần một nguồn thời gian nhất quán để biết thao tác bắt đầu khi nào, kết thúc khi nào và một khoảng thống kê đã trôi qua bao lâu. Abstraction Clock cung cấp nguồn thời gian đó cho registry và các meter.

Clock không phải là một meter và cũng không quyết định backend sẽ scrape hay nhận dữ liệu vào thời điểm nào. Nó cung cấp hai loại thời gian có mục đích khác nhau: thời gian lịch (wall time) và thời gian đơn điệu (monotonic time). Hiểu đúng hai loại này giúp tránh lỗi đo duration khi đồng hồ hệ điều hành bị điều chỉnh, đồng thời giúp kiểm thử metrics mà không phải chờ thời gian thực.

## 1. Clock trong Micrometer là gì?

Micrometer định nghĩa interface Clock để các thành phần đo lường lấy thời gian thông qua một abstraction thống nhất. Clock có hai phép đọc quan trọng:

- wallTime(): thời gian lịch hiện tại, thường được biểu diễn bằng milliseconds kể từ Unix epoch.
- monotonicTime(): bộ đếm thời gian đơn điệu, thường được biểu diễn bằng nanoseconds; chỉ hiệu giữa hai lần đọc mới có ý nghĩa để đo khoảng thời gian.

Registry cung cấp Clock mà nó sử dụng thông qua API clock(). Các meter cần đo thời lượng có thể dựa vào clock của registry, thay vì tự tạo một nguồn thời gian khác. Clock mặc định của hệ thống thường là Clock.SYSTEM.

Clock giúp tách logic đo lường khỏi nguồn thời gian cụ thể. Trong ứng dụng thật, registry thường dùng đồng hồ hệ thống. Trong kiểm thử, có thể truyền một clock giả để tiến thời gian có kiểm soát và xác minh kết quả một cách xác định.

## 2. Phân biệt wall time và monotonic time

Hai loại thời gian phục vụ hai mục đích khác nhau:

| Thuộc tính | wallTime | monotonicTime |
| --- | --- | --- |
| Ý nghĩa | Thời điểm theo lịch, có thể quy đổi thành ngày giờ. | Bộ đếm tiến về phía trước để đo khoảng thời gian. |
| Mốc tham chiếu | Unix epoch. | Mốc tùy ý do hệ thống cung cấp; không phải timestamp lịch. |
| Đơn vị trong Clock API | Milliseconds. | Nanoseconds. |
| Có thể bị chỉnh lùi hoặc nhảy tiến? | Có, ví dụ đồng bộ NTP, chỉnh giờ hệ điều hành hoặc thay đổi cấu hình thời gian. | Được thiết kế để không bị ảnh hưởng bởi việc chỉnh giờ lịch; chỉ dùng hiệu giữa các lần đọc. |
| Dùng cho | Timestamp, thời điểm refresh gần nhất, thời gian lịch. | Duration, latency, timeout và khoảng thời gian của tác vụ. |

### Ví dụ về wall time

Giả sử một tác vụ đồng bộ hoàn tất lúc 2026-11-23 10:15:00 UTC. Một timestamp dựa trên wall time có thể được chuyển thành ngày giờ để người vận hành biết lần đồng bộ thành công gần nhất diễn ra khi nào.

### Ví dụ về monotonic time

Một request bắt đầu tại monotonic time A và kết thúc tại monotonic time B. Duration được tính bằng B - A. Không cần biết A tương ứng với ngày giờ nào; chỉ cần hiệu của hai lần đọc.

Không dùng monotonicTime như timestamp để hiển thị ngày giờ. Ngược lại, không nên dùng wallTime để đo duration vì đồng hồ lịch có thể nhảy khi hệ điều hành được đồng bộ hoặc điều chỉnh.

## 3. Vì sao đo duration cần đồng hồ đơn điệu?

Đồng hồ lịch có thể thay đổi trong lúc một thao tác đang chạy. Ví dụ:

1. Request bắt đầu lúc wall time 10:00:00.
2. Hệ điều hành điều chỉnh đồng hồ lùi 30 giây.
3. Request kết thúc lúc wall time 10:00:05.

Nếu lấy timestamp cuối trừ timestamp đầu, kết quả có thể âm hoặc ngắn hơn thời gian thực đã trôi qua. Điều này làm sai Timer, timeout hoặc số liệu latency.

Monotonic clock được thiết kế cho phép tính hiệu thời gian. Dù wall clock bị điều chỉnh, hiệu monotonic vẫn tiếp tục phản ánh khoảng thời gian đã trôi qua theo đồng hồ đơn điệu.

Nanoseconds là đơn vị biểu diễn của monotonicTime, không có nghĩa mọi nền tảng đều đo được với độ chính xác một nanosecond. Độ phân giải và độ chính xác thực tế phụ thuộc hệ điều hành, JVM và phần cứng. Hãy xem đây là đơn vị để biểu diễn khoảng thời gian nhỏ, không phải cam kết về độ chính xác vật lý.

## 4. Timer sử dụng Clock của registry

Timer đo số lần thực hiện và thời lượng của các thao tác. Khi dùng Timer.Sample, Micrometer lấy thời điểm bắt đầu từ Clock của registry và dùng cùng nguồn thời gian khi dừng sample.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    private final MeterRegistry registry;
    private final Timer invoiceTimer;

    public InvoiceService(MeterRegistry registry) {
        this.registry = registry;
        this.invoiceTimer = Timer.builder("invoice.generate")
                .description("Time spent generating an invoice")
                .register(registry);
    }

    public Invoice generate(InvoiceCommand command) {
        Timer.Sample sample = Timer.start(registry);
        try {
            return generateInvoice(command);
        } finally {
            sample.stop(invoiceTimer);
        }
    }

    private Invoice generateInvoice(InvoiceCommand command) {
        // Perform invoice generation.
        return new Invoice();
    }
}
~~~

Sample giữ mốc bắt đầu theo clock của registry. Khi stop, thời lượng được ghi vào Timer. Dùng try/finally để thao tác vẫn được ghi nhận khi có exception; nếu chỉ ghi nhận thành công, hãy xác định rõ đó là một metric riêng có ngữ nghĩa khác.

Không cần tự gọi System.currentTimeMillis() để tính thời gian request. Cách dùng Timer.Sample vừa rõ ý nghĩa, vừa cho phép kiểm thử điều khiển clock của registry.

### Đo trực tiếp bằng monotonicTime

Trong trường hợp cần tích hợp một thuật toán đo thời gian tùy chỉnh, có thể đọc clock từ registry:

~~~java
long startedAt = registry.clock().monotonicTime();
try {
    performOperation();
} finally {
    long elapsedNanos = registry.clock().monotonicTime() - startedAt;
    operationTimer.record(elapsedNanos, TimeUnit.NANOSECONDS);
}
~~~

Đây là cách dùng đúng monotonic clock cho duration. Tuy nhiên, Timer.Sample thường dễ đọc và ít có nguy cơ quên dùng cùng một nguồn thời gian. Chỉ tự tính hiệu khi có lý do cụ thể, chẳng hạn cần giữ mốc bắt đầu trong một context riêng hoặc kết hợp với logic đo lường đặc thù.

## 5. LongTaskTimer cũng đo khoảng thời gian bằng Clock

LongTaskTimer theo dõi các tác vụ đang hoạt động. Khi gọi start(), sample ghi nhận mốc bắt đầu; trong lúc sample còn hoạt động, meter có thể công bố số tác vụ và thời lượng đã trôi qua. Khi gọi stop(), sample rời khỏi tập đang hoạt động.

~~~java
LongTaskTimer.Sample sample = longTaskTimer.start();
try {
    runLongImport();
} finally {
    sample.stop();
}
~~~

Khoảng thời gian đang chạy cần được tính bằng monotonic clock để không bị ảnh hưởng bởi việc chỉnh giờ hệ điều hành. LongTaskTimer sử dụng clock gắn với registry; vì vậy khi kiểm thử, clock giả được truyền vào registry cũng giúp điều khiển thời gian của sample.

Với tác vụ bất đồng bộ, dừng sample khi công việc thực sự hoàn tất trong worker. Không dừng ngay sau khi submit task, và không để sample tiếp tục hoạt động sau khi công việc đã kết thúc.

## 6. Clock và registry theo step

Một số registry dùng mô hình step. Thay vì chỉ giữ số liệu tích lũy trong toàn bộ vòng đời tiến trình, chúng xuất số liệu theo những khoảng thời gian cấu hình được gọi là step. Ví dụ, step có thể dài một phút; số liệu của từng bước được chốt hoặc chuyển sang bước tiếp theo theo cơ chế của registry.

Clock cung cấp cơ sở thời gian cho các meter và cơ chế step cần xác định khoảng thời gian đã trôi qua hoặc ranh giới bước. Chi tiết dùng wall time hay monotonic time và cách căn chỉnh ranh giới phụ thuộc implementation của registry.

Cần phân biệt ba khái niệm:

- **Clock** cung cấp thời gian để tính duration và xác định thời gian nội bộ của meter/registry.
- **Step** xác định cửa sổ thống kê mà registry sử dụng để tổng hợp hoặc xuất số liệu.
- **Scheduler** thực thi công việc định kỳ, ví dụ gọi thao tác publish theo chu kỳ.

Clock không tự khởi chạy một tác vụ publish. Việc gửi dữ liệu định kỳ còn phụ thuộc scheduler, cấu hình step và vòng đời của registry. Không nên suy ra rằng thay Clock là đã thay đổi lịch gửi dữ liệu.

## 7. Clock trong mô hình pull và push

Vai trò của Clock khi xuất metrics còn phụ thuộc cách backend nhận dữ liệu:

| Mô hình | Cách dữ liệu được thu thập | Vai trò của Clock |
| --- | --- | --- |
| Pull, ví dụ Prometheus | Backend chủ động scrape endpoint theo chu kỳ của nó. | Clock của registry hỗ trợ đo duration và giá trị time-based; lịch scrape do Prometheus cấu hình và điều khiển. |
| Push, ví dụ các registry gửi dữ liệu định kỳ | Ứng dụng hoặc registry gửi dữ liệu theo chu kỳ cấu hình. | Clock có thể tham gia xác định thời gian đo và ranh giới step; scheduler/registry quản lý lúc thực hiện publish. |
| SimpleMeterRegistry trong kiểm thử | Không tự gửi dữ liệu đến backend. | Clock giúp kiểm thử thời gian đo mà không cần chờ thực. |

Với Prometheus, nếu scrape interval là 15 giây, chính Prometheus quyết định thời điểm gọi endpoint. Thay Clock của ứng dụng không làm Prometheus scrape nhanh hơn hoặc chậm hơn. Với registry push theo step, thay đổi cấu hình step hoặc scheduler mới là các thao tác liên quan trực tiếp đến nhịp xuất dữ liệu; Clock là nguồn thời gian mà implementation dùng trong quá trình tính toán.

## 8. Dùng Clock giả để kiểm thử không cần sleep

Kiểm thử thời gian bằng Thread.sleep() thường chậm và dễ dao động do scheduler của hệ điều hành. Micrometer cung cấp MockClock để tiến thời gian theo ý muốn.

Ví dụ với SimpleMeterRegistry:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class ClockTest {

    @Test
    void timerUsesTheRegistryClock() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        Timer timer = registry.timer("invoice.generate");

        Timer.Sample sample = Timer.start(registry);
        clock.add(250, TimeUnit.MILLISECONDS);
        sample.stop(timer);

        assertThat(timer.count()).isEqualTo(1);
        assertThat(timer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(250.0);
    }
}
~~~

MockClock cho phép test tiến đồng hồ đúng 250 milliseconds. Timer ghi nhận duration theo clock đã truyền vào registry, nên test không phải đợi 250 milliseconds ngoài đời thực.

Constructor của registry và API MockClock có thể khác giữa các phiên bản Micrometer. Hãy dùng API tương ứng với dependency của dự án; nguyên tắc vẫn là tạo registry bằng clock giả và điều khiển clock đó trong test.

## 9. Kiểm thử wall time và monotonic time

Có thể kiểm tra hai khái niệm riêng biệt:

~~~java
MockClock clock = new MockClock();

long wallBefore = clock.wallTime();
long monotonicBefore = clock.monotonicTime();

clock.add(2, TimeUnit.SECONDS);

long wallElapsedMillis = clock.wallTime() - wallBefore;
long monotonicElapsedNanos = clock.monotonicTime() - monotonicBefore;

assertThat(wallElapsedMillis).isEqualTo(2_000);
assertThat(monotonicElapsedNanos).isEqualTo(2_000_000_000L);
~~~

Đoạn mã minh họa rằng hai phép đọc có đơn vị và mục đích khác nhau. Trong test của ứng dụng, nên ưu tiên xác minh hành vi observable của Timer hoặc LongTaskTimer thay vì phụ thuộc quá nhiều vào chi tiết nội bộ của Clock.

Một số kịch bản kiểm thử hữu ích:

1. Tiến MockClock một khoảng xác định rồi xác nhận Timer ghi nhận đúng duration.
2. Bắt đầu LongTaskTimer.Sample, tiến clock và xác nhận thời lượng đang hoạt động tăng.
3. Dừng sample rồi xác nhận active task count giảm.
4. Kiểm tra mã nghiệp vụ không dùng wall time để tính duration.
5. Kiểm tra timestamp lịch sử dụng wall time và được diễn giải theo đơn vị rõ ràng.

## 10. Không trộn Clock của registry với nguồn thời gian riêng

Một lỗi khó phát hiện là Timer.Sample dùng clock của registry nhưng phần đo tùy chỉnh lại dùng System.nanoTime() hoặc System.currentTimeMillis(). Trong kiểm thử, MockClock chỉ điều khiển thời gian của registry; các lời gọi trực tiếp đến đồng hồ hệ thống vẫn chạy theo thời gian thực.

Ví dụ không nhất quán:

~~~java
long started = System.currentTimeMillis();
Timer.Sample sample = Timer.start(registry);
~~~

Ở đây hai mốc bắt đầu thuộc hai nguồn thời gian khác nhau. Nếu một phần logic dùng mốc thứ nhất để tính duration còn Timer.Sample dùng mốc thứ hai, kết quả có thể khó kiểm thử và không đồng nhất.

Hãy chọn một nguồn thời gian theo mục đích:

- Với duration của meter, dùng Timer.Sample hoặc registry.clock().monotonicTime().
- Với timestamp lịch, dùng registry.clock().wallTime() hoặc một Clock nghiệp vụ được inject rõ ràng.
- Với lịch chạy công việc, dùng scheduler và cấu hình thời gian của scheduler.

Nếu nghiệp vụ cần một Clock riêng để kiểm soát thời gian ngày tháng, ví dụ tính hạn thanh toán hoặc ngày chốt sổ, có thể inject java.time.Clock vào lớp nghiệp vụ. Đừng dùng nguồn thời gian nghiệp vụ đó để thay thế monotonic clock cho latency.

## 11. Độ phân giải, độ chính xác và chi phí đọc thời gian

Đơn vị nanoseconds không bảo đảm đồng hồ có độ phân giải một nanosecond. Trên một số nền tảng, nhiều lần đọc liên tiếp có thể trả về cùng giá trị hoặc chỉ thay đổi theo bước lớn hơn một nanosecond.

Một vài nguyên tắc:

- Dùng monotonic time cho duration và so sánh hiệu giữa hai lần đọc.
- Không diễn giải giá trị monotonic tuyệt đối thành thời gian trong ngày.
- Không giả định một đơn vị nanosecond đồng nghĩa với độ chính xác nanosecond.
- Tránh đọc clock nhiều lần không cần thiết trong đường xử lý rất nóng.
- Không giữ một timestamp monotonic qua lần khởi động JVM hoặc truyền nó sang máy khác để so sánh.

Đối với tác vụ cực ngắn, chi phí gọi clock có thể chiếm tỷ trọng đáng kể trong phép đo. Hãy đo lường overhead trong môi trường thực tế và chọn mức instrumentation phù hợp với mục tiêu.

## 12. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng currentTimeMillis để tính latency | Đồng hồ lịch có thể nhảy, tạo duration sai hoặc âm. | Dùng Timer.Sample hoặc monotonicTime. |
| Dùng monotonicTime để hiển thị ngày giờ | Giá trị không có mốc epoch nên không thể đổi thành timestamp lịch. | Dùng wallTime cho thời điểm lịch. |
| Cho rằng Clock quyết định thời điểm Prometheus scrape | Hiểu sai trách nhiệm giữa ứng dụng và backend pull. | Scrape interval do Prometheus cấu hình. |
| Cho rằng đổi Clock sẽ đổi lịch push | Nhầm nguồn thời gian với scheduler. | Cấu hình scheduler và step của registry. |
| Trộn MockClock với System.nanoTime | Kiểm thử không còn điều khiển được toàn bộ phép đo. | Dùng registry.clock() hoặc Timer.Sample nhất quán. |
| Dùng nanoseconds như cam kết độ chính xác | Đánh giá sai khả năng đo của nền tảng. | Phân biệt đơn vị biểu diễn với độ phân giải thực tế. |
| Dùng timestamp epoch làm duration | Trộn thời điểm tuyệt đối với khoảng thời gian. | Tính hiệu từ monotonic clock. |
| Dùng Thread.sleep trong unit test thời gian | Test chậm và dễ flaky. | Dùng MockClock để tiến thời gian xác định. |

## 13. Checklist khi làm việc với Clock

- [ ] Đã xác định cần thời điểm lịch hay khoảng thời gian.
- [ ] Duration được tính bằng monotonic clock.
- [ ] Timestamp lịch được lấy bằng wall time.
- [ ] Timer.Sample hoặc registry.clock() được dùng nhất quán.
- [ ] Không trộn System.currentTimeMillis với monotonic duration.
- [ ] Đã phân biệt Clock, step window và scheduler.
- [ ] Đã hiểu scrape interval của pull backend do backend điều khiển.
- [ ] Đã dùng MockClock cho kiểm thử thời gian thay vì Thread.sleep khi phù hợp.
- [ ] Đơn vị và giới hạn độ phân giải được ghi rõ khi diễn giải kết quả.
- [ ] Không lưu hoặc so sánh monotonic timestamp giữa các tiến trình hay máy khác nhau.

Clock cung cấp nền tảng thời gian nhất quán cho các phép đo của Micrometer. Wall time trả lời câu hỏi một sự kiện xảy ra vào lúc nào; monotonic time trả lời một thao tác đã kéo dài bao lâu. Registry có thể dùng Clock trong việc ghi nhận và quản lý cửa sổ thống kê, còn scheduler và backend quyết định nhịp công bố hoặc thu thập dữ liệu. Giữ rõ ba trách nhiệm này giúp metrics chính xác hơn và kiểm thử ổn định hơn.

## Tài liệu tham khảo

- [Micrometer Clock API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Clock.html)
- [Micrometer Timer API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/Timer.html)
- [Micrometer MeterRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MeterRegistry.html)
