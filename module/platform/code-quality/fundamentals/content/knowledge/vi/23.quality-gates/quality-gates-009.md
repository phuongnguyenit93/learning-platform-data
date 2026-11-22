# Chẩn đoán, xử lý và theo dõi kiểm tra không ổn định

Một pipeline có thể chạy cùng một commit ba lần và cho ba kết quả khác nhau: lần đầu test thất bại, lần hai thành công, lần ba lại đỏ ở một test khác. Khi điều đó xảy ra thường xuyên, nhóm mất niềm tin vào cổng chất lượng. Người phát triển bắt đầu chạy lại cho đến khi xanh, reviewer khó biết lỗi mới có thật hay không, còn lỗi sản phẩm có thể bị chìm giữa những cảnh báo nhiễu.

**Kiểm tra không ổn định (flaky check)** là kiểm tra có kết quả thay đổi giữa những lần chạy trong điều kiện được kỳ vọng là tương đương, dù mã nguồn và đầu vào liên quan không thay đổi. Hiện tượng này có thể xuất phát từ test, build, môi trường chạy hoặc phụ thuộc bên ngoài. Việc một lần chạy lại thành công chưa chứng minh vấn đề đã được giải quyết.

Bài học thuộc chương **Cổng chất lượng** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu module — hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không** — bài này trình bày cách nhận diện, chẩn đoán, xử lý và theo dõi kiểm tra không ổn định. Trọng tâm là khôi phục độ tin cậy của bằng chứng CI, giữ khả năng phát hiện lỗi thật và quản lý ngoại lệ có thời hạn.

## 1. Kiểm tra không ổn định là gì?

Một kiểm tra được xem là không ổn định khi **cùng một thay đổi, cùng điều kiện đầu vào và cùng môi trường được kiểm soát**, kết quả có lúc đạt, có lúc thất bại mà không có thay đổi liên quan giải thích được.

Ví dụ:

- Một unit test đôi khi thất bại vì hai test cùng sửa một biến static.
- Một integration test đôi khi timeout khi database khởi động chậm.
- Một test dựa vào thời gian hiện tại thất bại gần thời điểm nửa đêm.
- Một kiểm tra giao diện đôi khi không tìm thấy phần tử vì phụ thuộc thời điểm render.
- Một bước build đôi khi tải dependency thất bại do registry hoặc mạng không ổn định.
- Một kiểm tra chất lượng dùng dữ liệu từ API bên ngoài cho kết quả khác nhau giữa các lần chạy.

Không phải mọi lần CI thất bại rồi chạy lại thành công đều là flaky. Có thể lần chạy đầu dùng commit khác, cache cũ, dependency mới được phát hành, dịch vụ đã phục hồi hoặc dữ liệu test đã thay đổi. Cần xác định **điều kiện nào thực sự được giữ cố định** trước khi kết luận.

### 1.1. Phân biệt flaky check với những loại thất bại khác

| Hiện tượng | Đặc điểm | Cách tiếp cận |
| --- | --- | --- |
| **Lỗi sản phẩm có thể tái hiện** | Cùng điều kiện dẫn đến cùng lỗi | Sửa nguyên nhân trong mã hoặc cấu hình sản phẩm |
| **Flaky test** | Test có lúc qua, lúc fail trong điều kiện tương đương | Điều tra tính không xác định, trạng thái dùng chung, timing và dữ liệu |
| **Lỗi môi trường CI** | Runner, mạng, dung lượng, registry hoặc dịch vụ hạ tầng có vấn đề | Thu thập log môi trường và xử lý hạ tầng |
| **Thay đổi đầu vào ngoài dự kiến** | Fixture, API hoặc dữ liệu phụ thuộc đã thay đổi | Cố định hợp đồng/dữ liệu hoặc cập nhật test theo yêu cầu |
| **Lỗi cấu hình build** | Phiên bản JDK, biến môi trường, profile hoặc dependency khác nhau | Chuẩn hóa và ghi nhận cấu hình |
| **Test không có oracle rõ** | Kết quả mong đợi phụ thuộc giả định chưa xác nhận | Làm rõ đặc tả và expected trước khi đánh giá tính ổn định |
| **Lỗi chỉ xảy ra dưới tải hoặc thứ tự nhất định** | Có điều kiện kích hoạt cụ thể, đôi khi khó tái hiện | Kiểm tra concurrency, tài nguyên và trạng thái hệ thống |

Một lỗi chỉ xuất hiện khi hai request chạy đồng thời có thể là **bug thật phụ thuộc timing**, không nên gắn nhãn flaky rồi bỏ qua. Nếu production cũng có thể gặp điều kiện đó, test đã phát hiện một rủi ro cần sửa.

### 1.2. “Không tái hiện được” chưa đồng nghĩa “flaky”

Một bug có thể hiếm, cần trạng thái dữ liệu đặc biệt hoặc phụ thuộc lịch chạy. Một lần thử không tái hiện chỉ cho biết **lần thử đó chưa kích hoạt điều kiện**.

Cần ghi:

- Commit và artifact đã chạy.
- Test hoặc bước CI nào thất bại.
- Runner, JDK, OS, cấu hình và thời điểm.
- Seed, thứ tự test, mức song song nếu có.
- Log, stack trace, screenshot hoặc artifact liên quan.
- Những thay đổi môi trường giữa lần fail và lần pass.

Sau đó mới xác định có đủ bằng chứng để phân loại là flaky hay cần điều tra tiếp.

## 2. Vì sao flaky check làm suy yếu cổng chất lượng?

Cổng chất lượng (quality gate) dùng kết quả kiểm tra để quyết định thay đổi có đủ điều kiện merge, phát hành hoặc triển khai hay không. Nếu kết quả không đáng tin, cổng có thể gây hai loại sai lầm:

- **Chặn nhầm:** thay đổi tốt bị giữ lại vì test fail ngẫu nhiên hoặc runner gặp sự cố.
- **Cho qua nhầm:** người phát triển chạy lại đến khi xanh, bỏ qua lỗi thật hoặc cấu hình retry che khuất tín hiệu.

Một cổng liên tục đỏ vì nhiễu khiến người dùng quen với việc bỏ qua cảnh báo. Khi đó, một lỗi bảo mật, regression hoặc test thực sự có giá trị cũng dễ bị xem như “lại là CI”.

### 2.1. Tác động tới từng nhóm

| Nhóm | Tác động |
| --- | --- |
| Người viết mã | Mất thời gian chạy lại, khó biết thay đổi của mình có gây lỗi không |
| Reviewer | Không phân biệt được lỗi mới, lỗi nền và lỗi môi trường |
| Người bảo trì CI | Phải xử lý cảnh báo lặp, rerun và build bị kẹt |
| Release manager | Không biết một lần pass sau retry có đủ tin cậy để phát hành |
| Người dùng sản phẩm | Lỗi thật có thể lọt qua khi nhóm đã quen bỏ qua tín hiệu đỏ |

Vì vậy, xử lý flaky check không chỉ là làm cho CI ít đỏ. Mục tiêu là **mỗi kết quả xanh hoặc đỏ đều có ý nghĩa đủ rõ để hỗ trợ quyết định**.

## 3. Những nguồn gây mất ổn định thường gặp

### 3.1. Phụ thuộc thời gian và tốc độ thực thi

Các test dùng `Thread.sleep` để chờ một việc “chắc đã xong” rất dễ phụ thuộc tải máy và lịch scheduler.

~~~java
@Test
void waitsForBackgroundWork() throws InterruptedException {
    worker.start();
    Thread.sleep(100);
    assertTrue(worker.isFinished());
}
~~~

Nếu worker hoàn tất trong 20 ms, test qua; nếu runner đang bận và worker cần 150 ms, test fail. Tăng sleep lên 2 giây có thể giảm xác suất fail nhưng làm suite chậm và **không loại bỏ nguyên nhân race**.

Những dấu hiệu khác:

- Chờ một khoảng thời gian cố định thay vì chờ điều kiện.
- Dùng `Instant.now()` hoặc `LocalDate.now()` trong test biên ngày/giờ.
- So sánh timestamp với độ chính xác không phù hợp.
- Giả định tác vụ nền hoàn tất ngay sau khi gọi.
- Timeout quá ngắn so với môi trường CI được hỗ trợ.

### 3.2. Trạng thái dùng chung giữa các test

Test có thể độc lập khi chạy riêng nhưng can thiệp nhau khi chạy cả suite:

- Biến static hoặc singleton mutable.
- System properties hoặc environment được thay đổi mà không khôi phục.
- Locale, timezone hoặc default charset bị đổi.
- Một test xóa dữ liệu mà test khác đang sử dụng.
- Cache toàn cục không được reset.
- Cùng dùng một thư mục, port hoặc tên tài nguyên cố định.

Đặc biệt, bật chạy song song có thể làm lỗi lộ ra. **Tắt parallel execution chỉ che điều kiện kích hoạt** nếu production cũng dùng nhiều thread hoặc test thực sự cần chạy độc lập.

### 3.3. Phụ thuộc thứ tự chạy

Một test có thể vô tình dựa vào test trước đã tạo dữ liệu, khởi tạo singleton hoặc cấu hình hệ thống. Khi runner đổi thứ tự, chạy riêng hoặc chia test thành shard, kết quả thay đổi.

Một suite tốt nên bảo đảm mỗi test:

- Tự tạo dữ liệu cần thiết.
- Thiết lập trạng thái rõ ràng.
- Dọn tài nguyên do chính nó sở hữu.
- Không phụ thuộc test khác chạy trước.
- Có thể chạy riêng và trong suite mà cho cùng kết quả.

### 3.4. Dữ liệu không cố định hoặc không cô lập

Các nguồn thường gặp:

- API ngoài trả dữ liệu thay đổi.
- Database dùng chung với người khác hoặc test khác.
- Fixture phụ thuộc ngày hiện tại.
- ID sinh ngẫu nhiên nhưng không ghi seed.
- Dữ liệu sản phẩm được cập nhật song song.
- Thứ tự truy vấn không có `ORDER BY` nhưng test lại so sánh một danh sách theo thứ tự cố định.

Nếu thứ tự không thuộc hợp đồng, test nên so sánh theo tập hợp hoặc sắp xếp bằng tiêu chí rõ. Nếu thứ tự là yêu cầu, cần bảo đảm nguồn dữ liệu thực sự định nghĩa nó.

### 3.5. Tài nguyên và môi trường CI

Một test có thể thất bại vì:

- Hết dung lượng đĩa hoặc inode.
- Thiếu RAM, CPU bị tranh chấp hoặc GC kéo dài.
- Port cố định đang được tiến trình khác sử dụng.
- File handle hoặc connection không được đóng.
- Container/database chưa sẵn sàng.
- Registry hoặc dependency proxy tạm thời không truy cập được.
- Khác biệt JDK, OS, timezone, locale hoặc charset.
- Cache build hỏng hoặc artifact cũ được tái sử dụng sai.

Không nên tự động sửa mã sản phẩm khi bằng chứng chỉ ra runner thiếu tài nguyên. Ngược lại, không nên gán lỗi vào “hạ tầng” nếu test đang giữ kết nối hoặc tạo tài nguyên không được dọn dẹp.

### 3.6. Hệ thống bất đồng bộ và giao diện

Test UI, message queue và background worker dễ không ổn định nếu giả định một thời điểm hoàn tất cụ thể.

Ví dụ:

- Click xong lập tức tìm phần tử mà không đợi trạng thái render.
- Gửi message rồi kiểm tra consumer ngay khi chưa có xác nhận xử lý.
- Gọi API rồi giả định cache hoặc read replica đã cập nhật tức thì.
- Dùng retry không có deadline rõ ràng nên test đôi khi chờ quá lâu.

Cách giải quyết là chờ **điều kiện có ý nghĩa**, có timeout hợp lý và log trạng thái khi hết hạn; không dùng sleep cố định làm đồng bộ.

## 4. Quy trình chẩn đoán có kiểm soát

Khi nhận một cảnh báo không ổn định, nên theo một quy trình để giữ bằng chứng.

### Bước 1 — Ghi nhận chính xác lần thất bại

Lưu commit SHA, job, test name, runner, thời điểm, command, cấu hình và log. Nếu có seed hoặc thứ tự chạy, giữ lại. Không chỉ ghi “CI đỏ”.

### Bước 2 — Xác nhận cùng một đầu vào

Đảm bảo các lần chạy so sánh cùng commit, cùng dependency lock, cùng fixture, cùng profile và cùng loại runner. Nếu đầu vào khác nhau, kết quả khác nhau chưa chứng minh flaky.

### Bước 3 — Chạy lại có giới hạn

Thực hiện một số lần lặp có kiểm soát để ước lượng tần suất, giữ kết quả từng lần và không dừng ngay khi có một lần pass. Việc lặp cần giới hạn để không gây tải vô ích hoặc che một lỗi đang có tác động.

### Bước 4 — Cô lập test và chạy trong suite

So sánh:
- Test chạy riêng.
- Test chạy cùng class/package.
- Test chạy toàn suite.
- Test chạy song song và tuần tự.
- Test chạy trên runner khác nhưng cùng cấu hình phần mềm.

Nếu chỉ fail trong suite, ưu tiên tìm state hoặc thứ tự dùng chung. Nếu chỉ fail ở runner cụ thể, so sánh môi trường và tài nguyên.

### Bước 5 — Thu hẹp điều kiện kích hoạt

Dùng seed cố định, giữ thứ tự, giảm số test, bật log chi tiết, kiểm tra timing, hoặc tạo dữ liệu tối thiểu. Mỗi lần chỉ thay đổi một yếu tố để biết yếu tố nào làm kết quả đổi.

### Bước 6 — Xác định nguyên nhân gốc hoặc ghi rõ điều chưa biết

Phân loại thành lỗi test, lỗi sản phẩm, môi trường, dependency, dữ liệu hoặc chưa đủ bằng chứng. Nếu chưa biết, giữ trạng thái điều tra; không đánh dấu FP hoặc “đã xử lý” chỉ vì rerun xanh.

### Bước 7 — Sửa và xác minh trong điều kiện từng gây lỗi

Sau khi sửa, chạy lại:
- Test riêng.
- Test trong suite và thứ tự liên quan.
- Chế độ song song nếu đó là điều kiện được hỗ trợ.
- Các lần lặp có kiểm soát.
- Integration/CI job trên runner đại diện.

### Bước 8 — Theo dõi sau khi đóng

Ghi commit sửa, bằng chứng và người sở hữu. Theo dõi cùng test/job trong một khoảng thời gian hoặc số lần chạy đủ đại diện; nếu lỗi tái xuất hiện, mở lại điều tra.

## 5. Dùng dữ liệu để tái hiện, không chỉ “rerun until green”

Một lần rerun thành công không cho biết xác suất lỗi đã giảm. Khi cần đo, hãy lưu chuỗi kết quả của cùng một test ở điều kiện được kiểm soát.

Ví dụ một báo cáo:

| Lần chạy | Commit | Runner | Test | Kết quả |
| ---: | --- | --- | --- | --- |
| 1 | `abc123` | `linux-jdk17-a` | `OrderRaceTest` | Fail |
| 2 | `abc123` | `linux-jdk17-a` | `OrderRaceTest` | Pass |
| 3 | `abc123` | `linux-jdk17-a` | `OrderRaceTest` | Fail |
| 4 | `abc123` | `linux-jdk17-a` | `OrderRaceTest` | Pass |
| 5 | `abc123` | `linux-jdk17-a` | `OrderRaceTest` | Fail |

Đây là dữ liệu **giả định** để minh họa. Nếu cùng commit, môi trường và test mà kết quả luân phiên, đó là tín hiệu mạnh cần điều tra trạng thái hoặc timing.

### 5.1. Ghi seed và thứ tự

Với test sinh dữ liệu ngẫu nhiên, lưu seed để có thể tái tạo cùng dữ liệu. Nếu framework randomize thứ tự test, lưu thứ tự thực tế khi fail. Không chỉ lưu một seed chung nếu test có nhiều nguồn random độc lập.

### 5.2. Tái hiện trên runner tương đương

“Máy local qua” không phủ định lỗi CI. Máy local có thể nhanh hơn, timezone khác, có database khác, hoặc không chạy song song. Cố gắng tái hiện trong container/runner cùng image, JDK, biến môi trường và giới hạn tài nguyên.

### 5.3. Không diễn giải quá mức một chuỗi pass ngắn

Nếu test chạy 10 lần không fail, điều đó không chứng minh xác suất flaky bằng 0. Một lỗi chỉ xuất hiện khi tải cao, một thứ tự hiếm hoặc tại thời điểm cụ thể có thể chưa được kích hoạt.

Khi báo cáo, nói rõ **đã chạy bao nhiêu lần, trong điều kiện nào và chưa kiểm tra điều gì**. Không chuyển “chưa tái hiện” thành “đã chứng minh ổn định”.

## 6. Ví dụ Java/JUnit 5: sửa phụ thuộc vào thời gian

Một test kiểm tra thời hạn khuyến mãi có thể gọi trực tiếp đồng hồ hệ thống:

~~~java
import java.time.LocalDate;

final class Promotion {
    static boolean isActive(LocalDate endDate) {
        return !LocalDate.now().isAfter(endDate);
    }
}
~~~

Test dùng ngày cố định nhưng gọi `LocalDate.now()`. Khi test chạy sát nửa đêm, timezone hoặc thời điểm thực thi có thể làm kết quả thay đổi.

### 6.1. Đưa Clock vào như một phụ thuộc có ý nghĩa

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.util.Objects;

final class Promotion {
    static boolean isActive(LocalDate endDate, Clock clock) {
        Objects.requireNonNull(endDate, "endDate");
        Objects.requireNonNull(clock, "clock");
        return !LocalDate.now(clock).isAfter(endDate);
    }
}
~~~

Test dùng clock cố định:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class PromotionTest {
    private static final Clock FIXED_CLOCK = Clock.fixed(
            Instant.parse("2026-11-16T10:00:00Z"),
            ZoneOffset.UTC);

    @Test
    void isActiveOnEndDate() {
        assertTrue(Promotion.isActive(
                LocalDate.of(2026, 11, 16), FIXED_CLOCK));
    }

    @Test
    void isInactiveAfterEndDate() {
        Clock afterEnd = Clock.fixed(
                Instant.parse("2026-11-17T00:00:00Z"),
                ZoneOffset.UTC);

        assertFalse(Promotion.isActive(
                LocalDate.of(2026, 11, 16), afterEnd));
    }
}
~~~

Điểm cải thiện là **thời gian trở thành đầu vào có thể kiểm soát**, không phải test phải chạy đúng vào một thời điểm. Ở ứng dụng thật, cần thống nhất timezone nghiệp vụ (UTC hay timezone địa phương) và cách xác định ngày hết hạn. Test cố định clock không tự quyết định chính sách timezone đúng.

## 7. Ví dụ Java/JUnit 5: loại bỏ trạng thái dùng chung giữa test

Một lớp test có biến static mutable:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class SharedEventsFlakyTest {
    private static final List<String> EVENTS = new ArrayList<>();

    @BeforeEach
    void reset() {
        EVENTS.clear();
    }

    @Test
    void recordsCreatedEvent() {
        EVENTS.add("created");
        assertEquals(List.of("created"), EVENTS);
    }

    @Test
    void recordsPaidEvent() {
        EVENTS.add("paid");
        assertEquals(List.of("paid"), EVENTS);
    }
}
~~~

Khi chạy tuần tự, mỗi test có thể qua vì `reset` chạy trước từng test. Khi chạy song song, một test có thể `clear` hoặc `add` trong lúc test kia đang kiểm tra, gây kết quả không xác định và thậm chí lỗi đồng thời của `ArrayList`.

### 7.1. Giải pháp: sở hữu trạng thái theo test

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class IsolatedEventsTest {
    @Test
    void recordsCreatedEvent() {
        List<String> events = new ArrayList<>();

        events.add("created");

        assertEquals(List.of("created"), events);
    }

    @Test
    void recordsPaidEvent() {
        List<String> events = new ArrayList<>();

        events.add("paid");

        assertEquals(List.of("paid"), events);
    }
}
~~~

Ví dụ thứ hai dùng danh sách riêng cho mỗi test. Trong ứng dụng thật, nếu state thuộc một service, cần xác định scope và quyền sở hữu state; chỉ thay biến test chưa sửa được một singleton mutable trong mã sản phẩm.

### 7.2. Nếu cần chia sẻ fixture bất biến

Fixture bất biến có thể dùng chung an toàn hơn, miễn các test không sửa đối tượng hoặc tham chiếu mutable bên trong. Nếu cần cache, database hoặc server dùng chung, phải có cơ chế namespace, transaction, reset và đồng bộ được định nghĩa rõ.

**Đừng chọn cách tắt chạy song song như bản sửa mặc định.** Chỉ tắt song song nếu framework hoặc tài nguyên thật sự không thể cô lập và quyết định đó có giới hạn, chủ sở hữu cùng kế hoạch xem lại.

## 8. Ví dụ đồng bộ bất đồng bộ bằng điều kiện thay vì sleep

Giả sử một worker xử lý tác vụ nền và test cần chờ tín hiệu hoàn tất. Có thể dùng `CountDownLatch` trong ví dụ nhỏ:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

final class TaskRunner {
    private final CountDownLatch finished = new CountDownLatch(1);

    void runAsync() {
        Thread worker = new Thread(() -> {
            try {
                // Thực hiện công việc.
            } finally {
                finished.countDown();
            }
        });
        worker.start();
    }

    boolean awaitFinished(long timeout, TimeUnit unit)
            throws InterruptedException {
        return finished.await(timeout, unit);
    }
}
~~~

Test có thể chờ điều kiện với timeout:

~~~java
@Test
void completesWithinAllowedTime() throws InterruptedException {
    TaskRunner runner = new TaskRunner();

    runner.runAsync();

    assertTrue(runner.awaitFinished(2, TimeUnit.SECONDS));
}
~~~

Đây chỉ là **minh họa cơ chế đồng bộ**. Nếu worker có kết quả hoặc exception, nên truyền kết quả qua `Future`, `CompletableFuture` hoặc một abstraction phù hợp để test kiểm tra cả thành công lẫn lỗi. Timeout là giới hạn để test không treo vô hạn; nó không nên được dùng để che một worker có thể không bao giờ hoàn tất.

## 9. Những kỹ thuật ổn định test thường hữu ích

| Nguyên nhân | Hướng xử lý |
| --- | --- |
| Phụ thuộc thời gian thực | Tiêm `Clock`, dùng thời điểm cố định và timezone rõ |
| Sleep để đợi | Chờ condition/event/future với timeout có giới hạn |
| Random không kiểm soát | Ghi seed, cho phép phát lại seed, giữ dữ liệu test nhỏ |
| Thứ tự test | Tạo fixture riêng, không phụ thuộc test trước |
| State static/singleton | Cô lập state, reset đúng cách hoặc thiết kế đối tượng không giữ state |
| Tệp/port dùng chung | Tạo thư mục tạm và port động, dọn tài nguyên sau test |
| Database chia sẻ | Schema/namespace riêng, transaction hoặc fixture độc lập |
| API bên ngoài | Dùng fake/stub cho unit test; contract/integration test riêng có kiểm soát |
| Truy vấn không xác định thứ tự | Thêm `ORDER BY` khi thứ tự thuộc hợp đồng hoặc so sánh không thứ tự khi không thuộc hợp đồng |
| Container chưa sẵn sàng | Health check hoặc wait strategy theo trạng thái thật |
| Timeout quá ngắn | Xác định SLO và điều kiện runner; timeout đủ dư nhưng không vô hạn |
| Resource leak | `try-with-resources`, teardown và kiểm tra tài nguyên sau lỗi |
| Cache build sai | Phân biệt cache key, kiểm tra invalidation và có cách chạy clean build |

### 9.1. Dùng test double đúng phạm vi

Unit test nên cô lập hệ thống ngoài để kiểm tra logic một cách lặp lại. Nhưng nếu mọi integration test đều được thay bằng mock, nhóm có thể không phát hiện hợp đồng database hoặc API đã đổi.

Một bộ kiểm tra cân bằng có thể gồm:

- **Unit tests:** nhanh, dữ liệu thuần, ít phụ thuộc môi trường.
- **Integration tests:** xác minh adapter, database, filesystem và framework.
- **Contract tests:** kiểm tra tương thích giữa consumer và provider.
- **End-to-end tests:** một số luồng quan trọng chạy qua hệ thống gần thực tế.

Không cần biến tất cả test thành end-to-end. Mỗi loại cần một mục tiêu rõ, để khi fail nhóm biết nên điều tra lớp nào.

## 10. Phân biệt lỗi test, lỗi sản phẩm và lỗi môi trường

Khi CI thất bại, hãy dùng bằng chứng để phân loại. Một bảng ghi nhận có thể gồm:

| Nhóm | Dấu hiệu | Bằng chứng cần tìm |
| --- | --- | --- |
| **Test defect** | Fixture dùng chung, assertion yếu, sleep, cleanup thiếu | Test source, thứ tự chạy, seed, stack trace |
| **Product defect** | Hành vi sai dưới điều kiện hợp lệ hoặc đồng thời thực tế | Reproducer, log ứng dụng, test tái hiện |
| **Environment failure** | Runner thiếu tài nguyên, DNS/registry lỗi, service không sẵn sàng | Runner metrics, network log, container health |
| **Dependency failure** | Provider bên ngoài đổi hành vi hoặc dependency tải không ổn định | Version lock, changelog, contract và response |
| **Configuration drift** | JDK/profile/locale khác giữa job | Environment variables, build config, image digest |
| **Unknown** | Chưa đủ dữ liệu để kết luận | Tiếp tục thu thập bằng chứng, giữ trạng thái điều tra |

Một lần timeout không tự chứng minh test flaky. Có thể hệ thống thực sự vượt SLA hoặc deadlock. Nếu cùng điều kiện gây timeout cho người dùng production, đó là **tín hiệu chất lượng sản phẩm**.

### 10.1. Không đổ lỗi cho runner quá sớm

Runner chậm hơn có thể làm lộ một race condition đã tồn tại. Tăng timeout có thể giúp CI qua, nhưng nếu logic vẫn phụ thuộc timing, test chưa chắc ổn định. Cần hỏi:

- Hệ thống có hợp đồng hoàn tất trong khoảng thời gian đó không?
- Timeout là giới hạn test hay SLO sản phẩm?
- Runner có thiếu tài nguyên bất thường?
- Có tác vụ bị block hoặc lock không được giải phóng?
- Lỗi có tái hiện khi tải tăng trong môi trường thật không?

## 11. Retry: biện pháp chẩn đoán hay cách che lỗi?

Retry có thể hữu ích để thu thập bằng chứng hoặc vượt qua lỗi hạ tầng tạm thời. Nhưng **retry không phải bản sửa flaky test**.

Nếu test fail lần đầu rồi pass lần hai, pipeline chỉ nên ghi nhận **đã có một lần thất bại**. Nếu báo cáo cuối chỉ hiện xanh mà không lưu lần fail, nhóm mất dữ liệu quan trọng.

### 11.1. Khi retry có thể hợp lý

- Registry dependency có lỗi tạm thời và job đã có chính sách retry giới hạn.
- Một dịch vụ kiểm thử ngoài có SLA/response transient được ghi nhận.
- Nhóm đang chẩn đoán mức độ không ổn định bằng cách lặp có kiểm soát.
- Hệ thống có cơ chế retry chính thức với deadline, backoff và idempotency.

### 11.2. Khi retry che khuất vấn đề

- Test có race condition.
- Assertion sai do state dùng chung.
- Một lần fail có thể làm dữ liệu bị ghi dở hoặc side effect trùng.
- Retry khiến build qua mà không lưu lịch sử.
- Người phát triển chạy lặp đến khi xanh rồi merge.
- Retry không có giới hạn làm job kéo dài hoặc tăng tải hệ thống.

### 11.3. Nếu cổng cho phép retry, hãy lưu cả kết quả ban đầu

Ví dụ trạng thái báo cáo:

| Kết quả lần đầu | Kết quả retry | Trạng thái nên thể hiện |
| --- | --- | --- |
| Pass | Không cần | Pass |
| Fail | Pass | **Recovered after retry / flaky signal** |
| Fail | Fail | Failed |
| Timeout | Không retry được | Infrastructure/unknown theo bằng chứng |
| Fail do regression tái hiện | Pass do dữ liệu khác | Không được coi là đã giải quyết |

Chính sách cuối cùng tùy mức rủi ro. Với test bảo mật, migration, integrity hoặc release-critical, một lần fail có thể cần **chặn phát hành cho đến khi có kết luận**, ngay cả khi retry xanh. Với một bước hạ tầng transient có bằng chứng và retry an toàn, hệ thống có thể tiếp tục nhưng phải giữ cảnh báo và số liệu.

## 12. Quarantine: cách ly tạm thời có kiểm soát

Khi một test không ổn định và đang chặn cả nhóm, có thể cần **quarantine** — tạm chuyển test khỏi cổng chặn chính để tiếp tục thu thập bằng chứng. Đây là biện pháp containment, không phải trạng thái hoàn thành.

Một test được quarantine cần có:

- Tên test và module cụ thể.
- Lý do dựa trên lần fail có log.
- Người hoặc nhóm sở hữu.
- Ticket điều tra và tiêu chí đóng.
- Ngày bắt đầu và thời hạn xem lại.
- Cách test vẫn được chạy và báo cáo ngoài gate.
- Rủi ro còn lại khi gate không dùng kết quả đó.

### 12.1. Không quarantine rộng hơn cần thiết

Không tắt cả package hoặc toàn bộ integration suite nếu chỉ một test bị flaky. Quarantine **đúng test hoặc đúng bước**, giữ các test liên quan khác chạy bình thường.

Không nên quarantine:
- Một nhóm test bảo mật quan trọng chỉ vì có false alarm chưa điều tra.
- Một migration test có thể phát hiện mất dữ liệu.
- Toàn bộ suite sau một lỗi không xác định.
- Test mới thất bại do regression vừa xuất hiện.

Nếu test bị cách ly, nó vẫn cần được chạy ở một job riêng hoặc chế độ quan sát để không mất tín hiệu.

### 12.2. Quarantine phải có ngày hết hạn

Một ngoại lệ không có thời hạn dễ trở thành cấu hình vĩnh viễn. Cần định kỳ xem lại:
- Test đã được sửa chưa?
- Ticket còn người phụ trách không?
- Mức ảnh hưởng có thay đổi?
- Có thể đưa lại vào required gate không?
- Có test thay thế đủ bằng chứng chưa?

Nếu hết hạn mà chưa xử lý, cần escalation hoặc quyết định có thẩm quyền; không tự động xóa quarantine mà không xem tác động, cũng không tự gia hạn vô hạn.

## 13. Thiết kế quality gate có khả năng phân biệt tín hiệu

Một cổng chất lượng đáng tin cần quy định **check nào bắt buộc, check nào cảnh báo, cách xử lý transient failure và ai quyết định ngoại lệ**.

Ví dụ mô hình:

~~~mermaid
flowchart TD
    A[Pull request / commit] --> B[Build và static checks]
    B --> C[Unit tests]
    C --> D[Integration / contract tests]
    D --> E[Security và policy checks]
    E --> F{Tất cả required checks đạt?}
    F -- Có --> G[Đủ điều kiện theo gate]
    F -- Không --> H[Phân loại failure]
    H --> I{Transient có bằng chứng?}
    I -- Có --> J[Retry giới hạn, giữ lịch sử]
    I -- Không --> K[Chặn và điều tra]
    J --> L{Kết quả sau retry}
    L -- Pass --> M[Pass có cảnh báo / theo policy]
    L -- Fail --> K
    M --> N[Theo dõi flaky signal]
~~~

Sơ đồ minh họa luồng quyết định, không quy định mọi tổ chức phải có đúng các job hoặc nhãn trạng thái này.

### 13.1. Required check và informational check

- **Required:** kết quả phải đạt hoặc có quyết định ngoại lệ rõ ràng trước merge/release.
- **Informational:** cung cấp tín hiệu hữu ích nhưng chưa trực tiếp chặn.
- **Quarantined:** vẫn được chạy và theo dõi, nhưng không tham gia quyết định chặn chính theo phạm vi đã ghi.
- **Skipped / not applicable:** phải có lý do; không được hiểu như pass nếu check đáng lẽ phải chạy.

Cần phân biệt **pass**, **skipped**, **not run**, **failed** và **recovered after retry**. Gộp tất cả thành xanh khiến dashboard mất ý nghĩa.

### 13.2. Không cho qua khi check bắt buộc chưa chạy

Nếu build bị lỗi trước khi test khởi chạy, trạng thái “test không có failure” không có nghĩa test pass. Cổng phải biết job có thực sự thực thi đủ hay không.

Một gate nên xác định:
- Các job bắt buộc và điều kiện kích hoạt.
- Khi nào check được phép skip.
- Thời gian chờ và timeout.
- Retry giới hạn và lưu kết quả từng lần.
- Quyền phê duyệt ngoại lệ.
- Cách xử lý khi CI provider hoặc runner outage.
- Bằng chứng phải có trước khi cho merge hoặc phát hành.

### 13.3. Không hạ chuẩn bảo mật chỉ vì CI không ổn định

Nếu security scanner không chạy do lỗi mạng hoặc cấu hình, đó là **thiếu bằng chứng kiểm tra**, không phải “không phát hiện vấn đề”. Quy trình release cần xác định ai có thể quyết định tiếp tục, kiểm soát thay thế nào và trong phạm vi nào.

## 14. Theo dõi độ ổn định bằng chỉ số có định nghĩa

Không thể cải thiện điều chưa quan sát được. Nhưng metric cần có định nghĩa rõ và mẫu số phù hợp.

| Chỉ số | Cách hiểu | Điều cần tránh |
| --- | --- | --- |
| **Flaky test rate** | Tỷ lệ test có ít nhất một lần kết quả không ổn định trong cửa sổ đo | Chia số test flaky cho tổng số lần chạy mà không nêu định nghĩa |
| **Failure rate** | Tỷ lệ lần chạy thất bại của một test/job | Gộp lỗi sản phẩm, test và môi trường thành một nhóm |
| **Retry recovery rate** | Tỷ lệ lần fail ban đầu chuyển pass sau retry | Coi recovered là bằng chứng đã sửa |
| **Time to diagnose** | Thời gian từ lần phát hiện đến phân loại nguyên nhân có căn cứ | Đếm cả thời gian chờ không được ghi rõ |
| **Quarantine age** | Thời gian test ở trạng thái cách ly | Để ngoại lệ tồn tại mà không có owner |
| **Gate false-block rate** | Tỷ lệ lần gate chặn vì lỗi được xác nhận là không liên quan đến thay đổi | Gán nhãn false block khi chưa điều tra |
| **Missed regression** | Lỗi lọt qua gate và được phát hiện sau đó | Quy kết toàn bộ lỗi production cho CI |
| **Rerun volume** | Số lần chạy lại và thời gian runner tiêu tốn | Khuyến khích rerun nhiều để làm đẹp tỷ lệ pass |

### 14.1. Định nghĩa flaky test rate

Một cách định nghĩa ở cấp test trong một cửa sổ:

`Flaky test rate = số test có cả pass và fail / số test được chạy đủ số lần quan sát`

Một cách khác ở cấp lần chạy:

`Flaky run rate = số lần chạy được xác định là flaky / tổng số lần chạy`

Hai metric trả lời câu hỏi khác nhau. Khi báo cáo, phải ghi **đơn vị đếm, cửa sổ, số lần lặp tối thiểu và cách phân loại**. Test chỉ chạy một lần không đủ dữ liệu để đánh giá tính ổn định theo cách này.

### 14.2. Theo dõi theo nhóm nguyên nhân

Có thể phân loại failure:
- Test state/concurrency.
- Timing/timeout.
- Dữ liệu/fixture.
- Dependency/network.
- Runner/resource.
- Configuration/build.
- Product regression.
- Unknown.

Theo dõi nhóm nào tăng giúp nhóm đầu tư đúng chỗ. Nếu phần lớn failure đến từ runner hết dung lượng, refactor unit test sẽ không giải quyết vấn đề chính.

### 14.3. Metric không phải KPI đánh giá cá nhân

Không dùng số flaky test để xếp hạng người viết test hoặc người sửa nhiều nhất. Nguồn gây lỗi có thể đến từ thiết kế hệ thống, hạ tầng và hợp đồng ngoài. Mục tiêu là **giảm chi phí và rủi ro cho toàn đội**, không tạo động cơ che giấu failure hoặc né test quan trọng.

## 15. Ghi nhận một sự cố flaky check

Một ticket hữu ích có thể theo cấu trúc:

~~~markdown
### FLAKY-009 — <tên test hoặc check>

Trạng thái: Detected / Investigating / Contained / Fixed / Monitoring / Closed
Owner:
Ngày phát hiện và thời điểm xem lại:

Phạm vi:
- Repository, commit, job, test name:
- Runner, image, JDK/OS, cấu hình:
- Số lần chạy, số pass/fail, thứ tự và seed:

Bằng chứng:
- Log/stack trace/artifact:
- Điều kiện tái hiện:
- Khác biệt giữa lần pass và fail:
- Test riêng, suite, parallel và runner khác:

Phân loại:
- Test / product / environment / dependency / config / unknown:
- Nguyên nhân gốc đã xác nhận hay giả thuyết:

Tác động:
- Gate bị chặn bao nhiêu lần:
- Thời gian runner/review bị tiêu tốn:
- Rủi ro nếu tạm quarantine:

Xử lý:
- Thay đổi cụ thể:
- Test hoặc kiểm tra dùng để xác minh:
- Retry/quarantine có giới hạn và lý do:

Theo dõi:
- Metric và cửa sổ quan sát:
- Điều kiện đưa lại vào required gate:
- Ngày hết hạn quarantine:
- Owner xác nhận đóng:
~~~

Không cần tạo ticket dài cho mọi lỗi runner đơn lẻ. Nhưng một test liên tục được rerun hoặc quarantine cần có **lịch sử và người chịu trách nhiệm** để tránh bị quên.

## 16. Ví dụ chính sách retry và quarantine

Đoạn YAML sau chỉ minh họa cách diễn đạt chính sách ở mức khái niệm, không phải cấu hình của CI provider cụ thể:

~~~yaml
qualityGate:
  required:
    - compile
    - unit-tests
    - security-scan

  retry:
    maxAttempts: 2
    preserveFirstFailure: true
    recoveredResult: "pass-with-flaky-warning"

  quarantine:
    scope: "single-test"
    requireOwner: true
    requireIssue: true
    expiryDays: 14
    runSeparately: true

  release:
    missingRequiredCheck: "block"
    securityScanUnavailable: "manual-risk-decision"
~~~

Các giá trị `2` và `14` là ví dụ, không phải ngưỡng chuẩn. Nhóm cần quyết định theo độ quan trọng của test, chi phí chạy và rủi ro release. Với kiểm tra an toàn hoặc dữ liệu quan trọng, policy có thể nghiêm ngặt hơn.

Một cấu hình có giá trị phải có **cơ chế thực thi thực tế**. Viết YAML tài liệu mà CI không đọc hoặc không kiểm tra trạng thái không tạo ra quality gate.

## 17. Quy trình đưa test trở lại required gate

Quarantine không kết thúc khi test “đã sửa trên máy local”. Cần có bằng chứng:

1. **Nguyên nhân đã xác định:** ví dụ state static dùng chung hoặc phụ thuộc thời gian thực.
2. **Bản sửa xử lý gốc:** không chỉ tăng sleep hoặc retry.
3. **Test độc lập:** chạy riêng cho kết quả ổn định.
4. **Test trong suite:** không phụ thuộc thứ tự.
5. **Chạy song song:** nếu hệ thống và CI hỗ trợ parallel, xác nhận hành vi.
6. **Lặp có kiểm soát:** nhiều lần trên commit và môi trường đại diện; lưu kết quả.
7. **Tích hợp:** job, fixture, container và cleanup hoạt động như dự kiến.
8. **Theo dõi:** không xuất hiện failure cùng nguyên nhân trong cửa sổ đã chọn.
9. **Review gate:** owner đồng ý đưa lại vào required checks và xóa quarantine.

Không có số lần lặp nào bảo đảm tuyệt đối test không bao giờ flaky. Hãy chọn số lần và điều kiện dựa trên **mức rủi ro và tần suất lỗi trước đó**, đồng thời ghi rõ giới hạn bằng chứng.

## 18. Những sai lầm thường gặp

**“CI fail rồi pass khi rerun, vậy có thể merge.”** Không tự động. Cần giữ lần fail, phân loại và áp dụng policy của gate; một regression thật có thể bị che bởi dữ liệu hoặc timing khác.

**“Tăng sleep là sửa flaky test.”** Thường chỉ kéo dài thời gian và giảm xác suất lỗi. Nên đồng bộ theo điều kiện hoặc event có ý nghĩa.

**“Tắt parallel là giải pháp lâu dài.”** Nó có thể che state dùng chung và giảm năng lực phát hiện race. Chỉ dùng khi có lý do, phạm vi và kế hoạch xem lại.

**“Quarantine nghĩa là bỏ test.”** Không. Test vẫn phải được chạy và theo dõi ngoài gate, có owner, issue và hạn hết hiệu lực.

**“Test flaky thì chắc chắn test sai.”** Không. Test có thể phát hiện một bug sản phẩm phụ thuộc concurrency hoặc timing thực tế.

**“Runner chậm nên tăng mọi timeout.”** Timeout lớn có thể che deadlock, resource leak và vi phạm SLO. Cần tìm nguyên nhân và chọn deadline có căn cứ.

**“Không có log lỗi là không có vấn đề.”** Thiếu log chỉ làm giảm khả năng chẩn đoán. Cần cải thiện observability và lưu artifact đủ dùng.

**“Một lần chạy 100 lần đều pass chứng minh ổn định tuyệt đối.”** Không. Chỉ có thể báo đã quan sát 100 lần trong điều kiện đã mô tả.

**“Test unit nào cũng phải mock mọi thứ.”** Không. Mock quá nhiều có thể khiến test không xác minh integration contract; cần chọn đúng cấp kiểm thử.

**“Retry recovered là pass bình thường.”** Không nên xóa lịch sử fail. Cần giữ trạng thái recovered và metric flaky.

**“Quarantine security scan khi dịch vụ ngoài lỗi là an toàn.”** Không. Khi required check chưa chạy, gate đang thiếu bằng chứng; cần quyết định rủi ro có thẩm quyền và biện pháp thay thế.

**“Flaky rate thấp thì có thể bỏ qua.”** Một test hiếm fail nhưng bảo vệ migration hoặc phân quyền có thể có hậu quả rất lớn. Ưu tiên cần xét tác động, không chỉ tần suất.

## 19. Bài tập vận dụng

### Tình huống A — Test chỉ fail khi chạy cả suite

Một unit test chạy riêng 50 lần đều pass, nhưng thỉnh thoảng fail khi chạy toàn bộ suite. Test dùng một biến static để giữ danh sách sự kiện.

**Câu hỏi:** nên kiểm tra điều gì trước?

**Gợi ý:** xem thứ tự và chế độ parallel, test nào cùng truy cập static state, lifecycle của fixture và cleanup. Cô lập state theo test; không chỉ tắt parallel rồi đóng issue.

### Tình huống B — Test timeout trên runner CI

Một integration test chờ database trong 5 giây. Local luôn qua, CI đôi khi timeout; log cho thấy container còn đang khởi động.

**Câu hỏi:** sửa test hay hạ tầng?

**Gợi ý:** kiểm tra health/readiness của container, tài nguyên runner và thời gian khởi động. Dùng wait strategy dựa trên trạng thái DB sẵn sàng với deadline hợp lý; không chỉ tăng sleep cố định. Nếu runner quá tải, cần bằng chứng hạ tầng riêng.

### Tình huống C — Rerun che regression

Một test thanh toán fail lần đầu do duplicate transaction, nhưng pass ở lần retry vì dữ liệu đầu vào đã được xử lý và trạng thái thay đổi.

**Câu hỏi:** có nên cho gate pass sau retry?

**Gợi ý:** không coi lần pass là bằng chứng lỗi đã hết. Kiểm tra tính idempotent, fixture isolation và trạng thái sau lần fail; test cần tạo dữ liệu mới hoặc reset đúng cách. Duplicate transaction có thể là bug sản phẩm nghiêm trọng.

### Tình huống D — Test dựa vào ngày hiện tại

Một test kiểm tra khuyến mãi hết hạn hôm nay. Test đôi khi fail khi chạy ở runner UTC và đôi khi pass ở máy developer timezone địa phương.

**Câu hỏi:** nên làm gì?

**Gợi ý:** đưa `Clock` và timezone nghiệp vụ thành đầu vào rõ ràng, dùng thời gian cố định trong test và kiểm tra ranh giới ngày. Không chỉnh ngày hệ thống toàn runner để làm test xanh.

### Tình huống E — Security scan không khởi chạy

Job security scan bị bỏ qua do token dịch vụ hết hạn. Pipeline hiển thị tổng thể xanh vì job được đánh dấu skipped.

**Câu hỏi:** cổng chất lượng có thể xem là đạt không?

**Gợi ý:** không nếu scan là required. Phân biệt skipped với pass, khôi phục credential và chạy lại; nếu cần ngoại lệ phát hành, phải có quyết định rủi ro và kiểm soát thay thế được phê duyệt.

### Tình huống F — Test bị quarantine ba tháng

Một test UI bị quarantine với ticket cũ nhưng không còn owner. Mỗi lần release, test vẫn chạy ở job không chặn và thỉnh thoảng fail.

**Câu hỏi:** cần làm gì?

**Gợi ý:** chỉ định owner, xác định test còn bảo vệ luồng quan trọng không, tìm nguyên nhân, đặt hạn xem lại. Nếu test không còn giá trị, thay bằng test ổn định có bằng chứng tương đương rồi mới loại bỏ; không để ngoại lệ vô thời hạn.

### Tình huống G — Tăng timeout làm test ổn định hơn

Sau khi tăng timeout từ 2 giây lên 60 giây, tỷ lệ fail giảm nhưng pipeline kéo dài và có một số test treo gần một phút.

**Câu hỏi:** có thể coi đây là bản sửa hoàn tất không?

**Gợi ý:** chưa. Tìm xem điều kiện hoàn tất nào bị chậm, có deadlock hoặc resource leak không, runner có bị quá tải không. Dùng wait theo điều kiện và deadline theo hợp đồng; theo dõi cả thời gian và failure rate.

## 20. Checklist vận hành kiểm tra không ổn định

### Khi một check thất bại

- **Đầu vào:** commit, artifact, dependency và fixture có giống lần so sánh không?
- **Môi trường:** runner, image, JDK, OS, timezone, locale và tài nguyên là gì?
- **Bằng chứng:** có log, stack trace, screenshot, seed, thứ tự và thời điểm?
- **Phạm vi:** test chạy riêng, trong suite, song song và trên runner tương đương ra sao?
- **Phân loại:** test defect, product defect, environment, dependency, config hay unknown?
- **Tái hiện:** có giới hạn số lần lặp và giữ kết quả từng lần không?

### Khi sửa

- **Nguyên nhân:** bản sửa xử lý gốc hay chỉ tăng sleep/timeout/retry?
- **Cô lập:** state, fixture, file, port, database và cache có được quản lý?
- **Đồng bộ:** test chờ condition/event/future với timeout có giới hạn?
- **Tính đúng:** expected dựa trên đặc tả và có kiểm tra lỗi/biên?
- **Phạm vi:** các test liên quan và điều kiện từng gây fail đã được chạy lại?

### Khi dùng quarantine hoặc retry

- **Phạm vi:** chỉ cách ly đúng test/check cần thiết?
- **Owner:** có nhóm hoặc người chịu trách nhiệm?
- **Hạn:** có ngày hết hạn và mốc review?
- **Quan sát:** test vẫn chạy và kết quả được lưu?
- **Retry:** có giới hạn, giữ lần fail ban đầu và không che side effect?
- **Gate:** skipped, recovered, quarantined và pass được phân biệt?

### Khi đóng sự cố

- **Bằng chứng:** có commit sửa, kết quả lặp, test suite và môi trường đại diện?
- **Theo dõi:** metric có cho thấy vấn đề giảm trong cửa sổ đủ phù hợp?
- **Khôi phục gate:** test đã được đưa lại vào required checks khi đủ căn cứ?
- **Tài liệu:** nguyên nhân, giới hạn và bài học có thể tra cứu?
- **Ngăn tái phát:** có thay đổi cấu hình hoặc hướng dẫn chung cần cập nhật?

## 21. Kết luận

**Một kiểm tra chỉ có giá trị khi nhóm có thể tin vào ý nghĩa của kết quả.** Khi test lúc qua lúc fail, không nên dừng ở thao tác rerun; cần xác định điều kiện, thu thập bằng chứng, phân biệt lỗi test với lỗi sản phẩm và môi trường, rồi sửa nguyên nhân gốc.

Retry có giới hạn và quarantine có thể giúp duy trì luồng làm việc trong thời gian điều tra, nhưng phải giữ lịch sử, có owner và ngày xem lại. Cổng chất lượng cần phân biệt rõ pass, fail, skipped và recovered để không biến thiếu bằng chứng thành tín hiệu xanh.

Trong **CODE_QUALITY_FUNDAMENTALS**, chẩn đoán, xử lý và theo dõi kiểm tra không ổn định giúp quy trình phát triển **đáng tin cậy hơn nhờ phát hiện lỗi thật, dễ hiểu hơn nhờ trạng thái và nguyên nhân rõ ràng, và dễ thay đổi hơn nhờ mỗi ngoại lệ có phạm vi, trách nhiệm cùng điều kiện kết thúc**.
