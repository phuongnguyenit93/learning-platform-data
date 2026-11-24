# Clock failure — Kiểm thử lỗi đồng hồ

Bài học thuộc chương **Failure Testing** của module bảo mật logic nghiệp vụ (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Nội dung tập trung vào những trường hợp nguồn thời gian bị sai, đứng, nhảy hoặc không đủ tin cậy, khiến hệ thống quyết định sai về thời hạn, quyền, giá và số lần thực hiện nghiệp vụ.

Một báo giá có thể hết hạn nhưng vẫn được dùng nếu đồng hồ worker chạy chậm. Một bản ghi idempotency có thể bị dọn sớm khi đồng hồ nhảy tiến, rồi cùng thao tác được thực hiện thêm lần nữa. Một quyết định phê duyệt cũ có thể tưởng như hợp lệ trở lại khi thời gian bị lùi.

Kiểm thử clock failure cần kiểm tra **quyết định nghiệp vụ và tác động sau lỗi**, không chỉ xác nhận timestamp đã thay đổi.

Sau bài học, bạn cần có thể:

- Phân biệt thời gian tuyệt đối, thời gian địa phương và nguồn đo khoảng thời gian.
- Xác định nguồn thời gian có thẩm quyền cho từng quy tắc.
- Mô phỏng nhảy tiến, nhảy lùi, đứng đồng hồ, sai lệch giữa node và lỗi đọc nguồn thời gian.
- Dùng Java `Clock` để viết test xác định, không cần sleep hoặc chỉnh đồng hồ máy phát triển.
- Kiểm tra hành vi khi không thể xác nhận độ tin cậy của thời gian.
- Bảo vệ bất biến về hết hạn, chuyển trạng thái, idempotency và transaction.
- Xác định phần cần kiểm thử tích hợp với database, queue và các hệ thống ngoài.

## 1. Clock failure có thể gây lỗi nghiệp vụ như thế nào?

Xét một báo giá có hiệu lực trong khoảng:

```text
validFrom = 10:00:00Z
expiresAt = 10:01:00Z

Hợp đồng:
  validFrom ≤ thời điểm quyết định < expiresAt
```

Nếu thời điểm tham chiếu thực tế đã là 10:01:10Z nhưng worker đọc 10:00:40Z, phép so sánh có thể đúng theo số liệu đầu vào nhưng sai với thời hạn cần bảo vệ.

Một số đường tác động:

| Quy tắc | Clock failure | Hậu quả có thể xảy ra |
|---|---|---|
| Báo giá phải còn hiệu lực | Worker chậm hoặc bị đứng | Chấp nhận giá đã hết hạn |
| Phê duyệt có thời hạn | Đồng hồ lùi | Quyết định cũ bị dùng lại |
| Chỉ dùng ưu đãi trong một cửa sổ | Node phát và node dùng lệch nhau | Mở sớm hoặc kéo dài ưu đãi |
| Retry không tạo tác động mới | Cleanup idempotency chạy sớm | Mất dấu thao tác đã thực hiện |
| Lease chỉ có một chủ thể hợp lệ | Node đánh giá hạn không nhất quán | Hai worker cùng nghĩ mình có quyền xử lý |
| Timeout phải kết thúc một lần thử | Dùng wall clock bị lùi để đo elapsed | Chờ quá lâu hoặc retry sai |
| Hạn mức theo ngày | Sai timezone hoặc ngày bị lặp | Đếm sai kỳ hoặc cấp lại hạn mức |
| Audit phải giải thích được diễn biến | Timestamp giữa node không nhất quán | Khó nối hành động với tác động |

Những hậu quả này là giả thuyết cần kiểm tra trong kiến trúc cụ thể. Không phải mọi lệch đồng hồ đều tự động gây tác động; còn phụ thuộc nguồn quyết định, guard, trạng thái bền vững và cơ chế lưu.

## 2. Ba khái niệm thời gian phải tách riêng

### 2.1. Thời gian tuyệt đối

Dùng để biểu diễn một điểm trên timeline, chẳng hạn:

- Báo giá hết hiệu lực lúc nào.
- Một ủy quyền bắt đầu và kết thúc lúc nào.
- Job được nhận hoặc giao dịch được ghi nhận khi nào.

Trong Java, thường dùng `Instant` cho timestamp tuyệt đối và `Duration` cho độ dài.

UTC là cách biểu diễn nhất quán, nhưng một timestamp ghi UTC vẫn có thể sai nếu nguồn đồng hồ sai. Đổi timezone không sửa được độ chính xác của thời gian.

### 2.2. Thời gian địa phương theo lịch

Dùng cho quy tắc như:

```text
Hạn mức tính theo ngày kinh doanh tại một timezone đã xác định.
Cửa sổ nhận yêu cầu đóng lúc 17:00 theo lịch của đơn vị vận hành.
```

Quy tắc này cần timezone và chính sách lịch rõ ràng. Một `LocalDateTime` không tự xác định duy nhất một instant khi thiếu timezone hoặc offset cần thiết.

Không mặc định timezone của máy chạy ứng dụng là timezone nghiệp vụ.

### 2.3. Nguồn đo khoảng thời gian

Dùng để đo một lần thử đã chạy bao lâu hoặc còn bao nhiêu ngân sách timeout trong tiến trình.

Java cung cấp `System.nanoTime()` để đo elapsed time. Giá trị này không phải epoch timestamp; chỉ chênh lệch giữa các lần đọc trong cùng JVM mới có ý nghĩa tương ứng. Không lưu giá trị đó làm hạn dùng chung giữa node hoặc dùng lại sau restart. [Java System: nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()).

Một thiết kế thường cần đồng thời:

```text
Instant / Clock:
  kiểm tra deadline tuyệt đối của nghiệp vụ

Nguồn elapsed time:
  giới hạn thời gian chờ của một lần xử lý cục bộ
```

Dùng nguồn elapsed time cho timeout không tự giải quyết tính đúng của hạn tuyệt đối trên báo giá.

## 3. Chốt hợp đồng thời gian trước khi gây lỗi

### 3.1. Xác định biên rõ ràng

Với cửa sổ nửa kín:

```text
[validFrom, expiresAt)
```

Kỳ vọng:

| Thời điểm | Kết quả |
|---|---|
| Trước validFrom | Chưa được dùng |
| Đúng validFrom | Có thể dùng nếu các guard khác đúng |
| Ngay trước expiresAt | Có thể dùng nếu các guard khác đúng |
| Đúng expiresAt | Đã hết hạn |
| Sau expiresAt | Đã hết hạn |

Độ chính xác của “ngay trước” phải phù hợp lớp đang kiểm tra. Policy dùng `Instant` có thể xét nano giây; dữ liệu qua database chỉ giữ mili giây cần ca tích hợp theo độ chính xác thực tế đó.

### 3.2. Chọn thời điểm quyết định có ý nghĩa

Một hệ thống có thể đánh giá hiệu lực tại:

- Lúc tiếp nhận command.
- Lúc worker bắt đầu thực hiện.
- Lúc ghi nhận quyết định bền vững.
- Lúc tạo tác động không thể đảo ngược.

Các lựa chọn không tương đương khi có queue hoặc I/O dài. Hợp đồng phải quy định rõ quyết định ở đâu có giá trị và bước nào cần kiểm tra lại.

Đọc một instant cho một quyết định giúp nhất quán nội bộ. Điều đó không đóng băng thời gian suốt transaction hoặc bảo đảm nguồn ngoài hoàn tất trước hạn.

Nếu chính sách yêu cầu kiểm tra lại sau một bước chờ dài, test phải đặt biến động thời gian đúng giữa hai bước đó.

### 3.3. Chọn nguồn có thẩm quyền

Với mỗi thời hạn, ghi rõ:

```text
Ai tạo deadline?
Ai được dùng deadline để quyết định?
Nguồn thời gian nào được tin?
Mức sai số nào được chấp nhận?
Khi không xác nhận được thời gian thì làm gì?
```

Không coi timestamp do client gửi là “hiện tại” của máy chủ. Timestamp trong message cũng cần nguồn gốc rõ: thời gian phát event, thời gian nhận và thời gian thực hiện có vai trò khác nhau.

Database hoặc dịch vụ thời gian tập trung có thể là nguồn quyết định theo thiết kế, nhưng chúng vẫn cần được giám sát và kiểm thử. Chuyển mọi phép so sánh vào database không có nghĩa nguồn thời gian tuyệt đối không thể sai.

## 4. Ma trận lỗi đồng hồ

| Loại lỗi | Mô phỏng | Điều cần kiểm tra |
|---|---|---|
| Offset cố định | Một node nhanh/chậm một khoảng | Các node có quyết định trái hợp đồng không |
| Nhảy tiến | Thời gian tăng đột ngột | Hết hạn hàng loạt, cleanup sớm, retry và tác động |
| Nhảy lùi | Thời gian giảm đột ngột | Tái kích hoạt quyền cũ, lặp kỳ hạn mức |
| Drift | Sai lệch tăng dần | Giám sát phát hiện và chính sách suy giảm |
| Đứng đồng hồ | Instant không đổi khi thời gian tham chiếu tiến | Deadline không bị giữ sống vô hạn |
| Đọc nguồn thất bại | Nguồn được bọc ném lỗi | Không bỏ kiểm tra rồi tiếp tục nghiệp vụ nhạy cảm |
| Nguồn không còn được xác nhận | Health signal suy giảm | Xử lý theo chính sách đã định |
| Sai timezone | Cùng instant, cách chuyển ngày khác | Không đổi hạn tuyệt đối; kỳ kinh doanh đúng lịch |
| Mất độ chính xác | Timestamp bị cắt/làm tròn | Biên hạn không lệch ngoài hợp đồng |
| Lệch giữa hệ thống | App, DB, worker, provider dùng giờ khác nhau | Không dựa vào giả định các nguồn luôn giống nhau |
| Restart/suspend | Thay đổi vòng đời và nguồn elapsed | Không tái dùng timestamp cục bộ sai ngữ nghĩa |

Phải tách lỗi không đọc được nguồn với lỗi đọc được một giá trị sai. Đồng hồ hệ thống thường vẫn trả timestamp khi dịch vụ đồng bộ thời gian gặp vấn đề; không giả định ứng dụng sẽ nhận exception để biết thời gian đã mất độ tin cậy.

## 5. Tách việc đọc thời gian khỏi logic nghiệp vụ bằng Java Clock

Java `Clock` cho phép thay nguồn thời gian, và các clock cố định hoặc có offset hỗ trợ kiểm thử. Tuy nhiên, `Clock` không bảo đảm giá trị trả về là thời gian hiện tại chính xác; đó là một abstraction để cung cấp thời gian. [Java Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html).

Thay vì để logic miền gọi thời gian toàn cục ở nhiều nơi:

```java
Instant now = Instant.now();
```

hãy truyền `Clock` hoặc truyền một thời điểm đã lấy từ nguồn phù hợp vào quyết định:

```java
Instant now = clock.instant();
```

Lợi ích:

- Test kiểm soát được từng bước thời gian.
- Không cần sleep để vượt qua thời hạn.
- Có thể kiểm tra cùng dữ liệu với nhiều nguồn clock.
- Dễ phát hiện chỗ còn dùng nguồn thời gian khác ngoài thiết kế.

Việc inject `Clock` không thay thế kiểm tra state machine, quyền theo đối tượng hoặc tính nguyên tử khi lưu.

## 6. Test double điều khiển được đồng hồ

Lớp dưới đây dùng cho môi trường test, với Java 17 trở lên. Nó hỗ trợ đặt thời gian, nhảy một khoảng và mô phỏng không đọc được nguồn.

Các view tạo bằng `withZone` chia sẻ cùng trạng thái nguồn, chỉ khác cách diễn giải timezone. Trạng thái dùng `AtomicReference` để một lần đọc nhận được một cặp instant/khả dụng nhất quán.

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

final class ControlledClock extends Clock {
    private record Reading(Instant instant, boolean available) {}

    private final AtomicReference<Reading> reading;
    private final ZoneId zone;

    ControlledClock(Instant initial, ZoneId zone) {
        this(
                new AtomicReference<>(
                        new Reading(Objects.requireNonNull(initial), true)),
                zone);
    }

    private ControlledClock(
            AtomicReference<Reading> reading, ZoneId zone) {
        this.reading = Objects.requireNonNull(reading);
        this.zone = Objects.requireNonNull(zone);
    }

    void set(Instant instant) {
        reading.set(new Reading(Objects.requireNonNull(instant), true));
    }

    void jump(Duration amount) {
        Objects.requireNonNull(amount);
        reading.updateAndGet(current -> new Reading(
                current.instant().plus(amount),
                current.available()));
    }

    void makeUnavailable() {
        reading.updateAndGet(current ->
                new Reading(current.instant(), false));
    }

    @Override
    public Instant instant() {
        Reading current = reading.get();
        if (!current.available()) {
            throw new DateTimeException("Test clock is unavailable");
        }
        return current.instant();
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        Objects.requireNonNull(newZone);
        return zone.equals(newZone)
                ? this
                : new ControlledClock(reading, newZone);
    }
}
```

`set` trong fixture này đồng thời khôi phục khả năng đọc. `jump` giữ trạng thái khả dụng hiện có. Đó là hợp đồng của test double, không phải mô tả cách một đồng hồ hệ điều hành thực tế hoạt động.

Một clock trả cùng instant trong test giúp mô phỏng frozen time, nhưng bản thân giá trị cố định chưa đủ để xác định lỗi trong production. Hai lần đọc gần nhau có thể bằng nhau do độ phân giải của nguồn.

## 7. Ví dụ gate thời gian cho báo giá

Giả sử nghiệp vụ yêu cầu:

- Báo giá chỉ dùng trong `[validFrom, expiresAt)`.
- Khi nguồn thời gian bị đánh dấu không tin cậy, thao tác nhạy cảm không được thực hiện.
- Khi không đọc được nguồn, trả một kết quả riêng để hệ thống xử lý.
- Gate chỉ quyết định về thời gian; các guard khác được thực hiện ở lớp miền tương ứng.

```java
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Instant;
import java.util.Objects;
import java.util.function.BooleanSupplier;

final class QuoteTimeGate {
    enum Decision {
        ALLOWED,
        NOT_YET_VALID,
        EXPIRED,
        TIME_UNTRUSTED,
        TIME_UNAVAILABLE
    }

    record Window(Instant validFrom, Instant expiresAt) {
        Window {
            Objects.requireNonNull(validFrom);
            Objects.requireNonNull(expiresAt);
            if (!validFrom.isBefore(expiresAt)) {
                throw new IllegalArgumentException(
                        "validFrom must be before expiresAt");
            }
        }
    }

    private final Clock clock;
    private final BooleanSupplier timeTrusted;

    QuoteTimeGate(Clock clock, BooleanSupplier timeTrusted) {
        this.clock = Objects.requireNonNull(clock);
        this.timeTrusted = Objects.requireNonNull(timeTrusted);
    }

    Decision evaluate(Window window) {
        Objects.requireNonNull(window);

        if (!timeTrusted.getAsBoolean()) {
            return Decision.TIME_UNTRUSTED;
        }

        final Instant now;
        try {
            now = clock.instant();
        } catch (DateTimeException failure) {
            return Decision.TIME_UNAVAILABLE;
        }

        if (now.isBefore(window.validFrom())) {
            return Decision.NOT_YET_VALID;
        }
        if (!now.isBefore(window.expiresAt())) {
            return Decision.EXPIRED;
        }
        return Decision.ALLOWED;
    }
}
```

Mã tách tình trạng nguồn thời gian khỏi kết quả hết hạn. Hệ thống có thể ánh xạ những kết quả này thành lỗi nghiệp vụ, tạm hoãn hoặc phản hồi phù hợp theo hợp đồng.

`timeTrusted` là cổng nhận health signal trong ví dụ, không phải một thuật toán phát hiện clock failure. Trong triển khai thật, dữ liệu health, độ mới và cách đọc cần được thiết kế rõ. Ví dụ cũng giả định adapter health trả được boolean; lỗi lấy health phải được ánh xạ theo chính sách, không âm thầm coi là tin cậy.

Gate không lưu lịch sử đã dùng/đã hết hạn, không kiểm soát version và không tạo transaction. Các bảo đảm đó cần được bổ sung ở lớp chịu trách nhiệm.

## 8. Unit test xác định cho biên, bước nhảy và nguồn lỗi

Đặt các lớp ví dụ trong cùng package. Test dùng JUnit Jupiter:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class QuoteTimeGateTest {
    private static final Instant START =
            Instant.parse("2030-01-01T10:00:00Z");

    private final ControlledClock clock =
            new ControlledClock(START, ZoneOffset.UTC);
    private final AtomicBoolean trusted = new AtomicBoolean(true);
    private final QuoteTimeGate gate =
            new QuoteTimeGate(clock, trusted::get);
    private final QuoteTimeGate.Window window =
            new QuoteTimeGate.Window(
                    START, START.plusSeconds(60));

    @Test
    void allowsExactlyAtTheStart() {
        clock.set(START);

        assertEquals(
                QuoteTimeGate.Decision.ALLOWED,
                gate.evaluate(window));
    }

    @Test
    void rejectsBeforeTheStart() {
        clock.set(START.minusNanos(1));

        assertEquals(
                QuoteTimeGate.Decision.NOT_YET_VALID,
                gate.evaluate(window));
    }

    @Test
    void allowsImmediatelyBeforeExpiry() {
        clock.set(window.expiresAt().minusNanos(1));

        assertEquals(
                QuoteTimeGate.Decision.ALLOWED,
                gate.evaluate(window));
    }

    @Test
    void expiresExactlyAtTheBoundary() {
        clock.set(window.expiresAt());

        assertEquals(
                QuoteTimeGate.Decision.EXPIRED,
                gate.evaluate(window));
    }

    @Test
    void forwardJumpCanMoveTheDecisionPastExpiry() {
        clock.jump(Duration.ofMinutes(5));

        assertEquals(
                QuoteTimeGate.Decision.EXPIRED,
                gate.evaluate(window));
    }

    @Test
    void anUnavailableSourceDoesNotAllowTheOperation() {
        clock.makeUnavailable();

        assertEquals(
                QuoteTimeGate.Decision.TIME_UNAVAILABLE,
                gate.evaluate(window));
    }

    @Test
    void anApparentlyValidTimestampDoesNotOverrideBadHealth() {
        clock.set(START.plusSeconds(120));
        clock.jump(Duration.ofSeconds(-100));
        trusted.set(false);

        assertEquals(
                QuoteTimeGate.Decision.TIME_UNTRUSTED,
                gate.evaluate(window));
    }

    @Test
    void aFrozenSourceIsRejectedWhenIndependentHealthIsLost() {
        clock.set(START.plusSeconds(10));
        assertEquals(
                QuoteTimeGate.Decision.ALLOWED,
                gate.evaluate(window));

        // Clock vẫn giữ cùng instant; health đến từ cơ chế độc lập.
        trusted.set(false);

        assertEquals(
                QuoteTimeGate.Decision.TIME_UNTRUSTED,
                gate.evaluate(window));
    }

    @Test
    void recoveryDoesNotExtendTheStoredDeadline() {
        trusted.set(false);
        assertEquals(
                QuoteTimeGate.Decision.TIME_UNTRUSTED,
                gate.evaluate(window));

        clock.set(window.expiresAt().plusSeconds(1));
        trusted.set(true);

        assertEquals(
                QuoteTimeGate.Decision.EXPIRED,
                gate.evaluate(window));
    }

    @Test
    void changingOnlyTheZoneDoesNotChangeAnInstantBasedDecision() {
        clock.set(START.plusSeconds(10));
        QuoteTimeGate anotherView = new QuoteTimeGate(
                clock.withZone(ZoneId.of("Asia/Ho_Chi_Minh")),
                trusted::get);

        assertEquals(
                gate.evaluate(window),
                anotherView.evaluate(window));
    }
}
```

### 8.1. Bộ test này chứng minh gì?

Nó kiểm tra chính sách của gate với thời gian và health do test cung cấp. Nó không chứng minh hệ thống giám sát thực tế phát hiện được đồng hồ đứng hoặc nhảy lùi.

Test frozen time cố ý cấp health signal mất tin cậy. Muốn kiểm tra cơ chế phát hiện, cần test riêng cho monitor với nguồn tham chiếu hoặc nguồn elapsed time điều khiển được.

### 8.2. Không được biến health thành cờ luôn true

Nếu adapter production luôn báo true, các test đơn vị vẫn có thể pass trong khi lỗi thực tế không bị nhận biết. Vì vậy, test tích hợp phải kiểm tra đường truyền trạng thái health và hành vi của service khi trạng thái đó thay đổi.

### 8.3. Kiểm tra không có tác động ở service

Ở lớp application service, bổ sung assert rằng các kết quả `TIME_UNTRUSTED`, `TIME_UNAVAILABLE` hoặc hết hạn theo hợp đồng không tạo:

- Chuyển trạng thái thành công.
- Khoản thu/chi.
- Bản ghi cấp quyền sử dụng.
- Event thành công không được phép.

Audit về việc từ chối có thể được ghi nếu đó là thiết kế. Không đánh đồng audit với tác động nghiệp vụ thành công.

## 9. Frozen clock và bài toán nguồn tham chiếu

### 9.1. Không thể xác nhận chính mình bằng cùng nguồn lỗi

Nếu cả logic hết hạn và health monitor đều chỉ hỏi cùng một wall clock bị đứng, hệ thống có thể thấy mọi thứ vẫn bình thường.

Cần một cơ sở kiểm tra khác phù hợp, chẳng hạn:

- So sánh mức tiến của wall clock với nguồn elapsed time trong cùng tiến trình.
- Theo dõi trạng thái và độ mới của thông tin đồng bộ thời gian.
- Đối chiếu nguồn thời gian được quản lý theo kiến trúc.
- Phát hiện sai lệch giữa các node theo chính sách.

So sánh wall clock với elapsed time giúp phát hiện một số bước nhảy hoặc tốc độ tiến bất thường. Nó không tự xác nhận offset tuyệt đối so với UTC nếu cả hai đều tiến bình thường nhưng wall clock đã lệch một khoảng cố định.

### 9.2. Health cũng có thời hạn sử dụng

Một kết quả “đồng hồ khỏe” từ lâu không nhất thiết còn áp dụng. Độ mới của health phải được kiểm tra bằng cơ chế không phụ thuộc hoàn toàn vào nguồn đang bị nghi ngờ.

Trong cùng tiến trình, có thể dùng nguồn elapsed time để giới hạn tuổi của mẫu health. Khi restart hoặc chuyển node, cần dựng lại ngữ cảnh theo thiết kế; không tái dùng giá trị tick cục bộ cũ.

Không tự đặt một ngưỡng rất nhỏ rồi coi mọi lần đọc bằng nhau là frozen. Ngưỡng cần phù hợp độ phân giải, khoảng quan sát, tải và đặc tính môi trường.

### 9.3. Khi không đủ tin cậy, giữ kết quả tường minh

Với thao tác cần chứng minh chưa hết hạn, hợp đồng có thể yêu cầu từ chối hoặc tạm hoãn khi thời gian không đáng tin.

Những thao tác chỉ đọc hoặc tác vụ không phụ thuộc thời hạn có thể có chính sách khác. Không cần biến mọi clock failure thành ngừng toàn bộ ứng dụng, nhưng phải tránh đường fallback vô điều kiện cho nghiệp vụ nhạy cảm.

Các fallback như dùng epoch 0, giữ mãi giá trị “lần cuối còn hợp lệ” hoặc bỏ qua guard đều cần được xem xét vì có thể kéo dài hiệu lực ngoài hợp đồng.

## 10. Sai số thời gian và vùng chưa thể kết luận

Giả sử kiến trúc có một ước lượng thời gian `t` và giới hạn sai số có cơ sở là `ε`:

```text
Thời điểm cần quyết định nằm trong [t - ε, t + ε]
```

Với cửa sổ hợp lệ `[validFrom, expiresAt)`, điều kiện bảo thủ để chắc chắn toàn bộ khoảng ước lượng còn hợp lệ là:

```text
t - ε ≥ validFrom
AND
t + ε < expiresAt
```

Nếu khoảng ước lượng cắt qua biên, kết quả có thể là “chưa xác nhận được hiệu lực” theo hợp đồng.

Ví dụ:

```text
t = 10:00:59.500Z
ε = 1 giây
expiresAt = 10:01:00Z

Khoảng có thể:
  10:00:58.500Z đến 10:01:00.500Z
```

Không đủ cơ sở để khẳng định yêu cầu chắc chắn chưa hết hạn. Việc tự cộng “grace period một giây” có thể cho phép dùng sau hạn; đó là thay đổi chính sách, không chỉ sửa sai số kỹ thuật.

Giới hạn `ε` phải đến từ mô hình tin cậy được xác định, không phải con số đoán để test xanh. Offset đo được từ một lần đồng bộ không tự chứng minh một giới hạn sai số tuyệt đối cho mọi thời điểm sau đó.

Các ca cần thử:

- Toàn khoảng nằm trong cửa sổ hợp lệ.
- Cận trên đúng bằng thời điểm hết hạn.
- Toàn khoảng ở trước hoặc sau cửa sổ.
- Sai số lớn hơn giới hạn chính sách.
- Không còn mẫu sai số đủ mới.
- Phép cộng/trừ thời gian gần giới hạn biểu diễn.

## 11. Timeout cục bộ phải độc lập với wall clock

### 11.1. Tránh đo elapsed bằng timestamp tuyệt đối

Một vòng chờ kiểu:

```text
deadline = wallClockNow + timeout
lặp khi wallClockNow < deadline
```

có thể bị kéo dài hoặc kết thúc sớm khi wall clock thay đổi.

Với ngân sách một lần thử trong cùng JVM, có thể dùng chênh lệch tick:

```java
long started = System.nanoTime();
long timeoutNanos = timeout.toNanos();

boolean expired =
        System.nanoTime() - started >= timeoutNanos;
```

Java khuyến nghị so sánh chênh lệch thay vì cộng `started + timeout` để tránh vấn đề tràn ở phép cộng. Phải giữ khoảng đo và cấu hình trong phạm vi biểu diễn phù hợp. [Java System: Measuring Elapsed Time](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()).

### 11.2. Inject nguồn tick để test

```java
import java.time.Duration;
import java.util.Objects;
import java.util.function.LongSupplier;

final class ElapsedBudget {
    private final LongSupplier ticker;
    private final long started;
    private final long timeoutNanos;

    ElapsedBudget(Duration timeout, LongSupplier ticker) {
        Objects.requireNonNull(timeout);
        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }
        this.ticker = Objects.requireNonNull(ticker);
        this.timeoutNanos = timeout.toNanos();
        this.started = ticker.getAsLong();
    }

    boolean expired() {
        return ticker.getAsLong() - started >= timeoutNanos;
    }
}
```

Một test không cần sleep:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ElapsedBudgetTest {
    @Test
    void expiresAtTheConfiguredElapsedBoundary() {
        AtomicLong ticks = new AtomicLong(100L);
        ElapsedBudget budget =
                new ElapsedBudget(Duration.ofNanos(10), ticks::get);

        ticks.set(109L);
        assertFalse(budget.expired());

        ticks.set(110L);
        assertTrue(budget.expired());
    }
}
```

Nguồn tick phải đáp ứng hợp đồng elapsed time. Lớp này không kiểm tra nguồn có tiến đúng hay không và không phải deadline bền vững sau restart.

Hành vi khi máy hoặc tiến trình bị suspend cần được kiểm tra trên nền tảng thực tế nếu nó ảnh hưởng mục tiêu timeout. Không mặc định mọi nguồn đo thời gian tính thời gian suspend giống nhau.

## 12. Nhảy lùi không được làm sống lại trạng thái đã kết thúc

Một gate chỉ so timestamp có thể trả:

```text
10:01:01Z → EXPIRED
đồng hồ lùi về 10:00:30Z → ALLOWED
```

Đây có thể là hành vi đúng của phép so sánh thuần với đầu vào mới nhưng không đủ cho một workflow có trạng thái hết hạn không thể đảo ngược.

Nếu hợp đồng quy định báo giá hoặc ủy quyền đã kết thúc không tự hoạt động lại, cần bảo vệ bằng trạng thái bền vững hoặc cơ chế tương đương:

```text
ACTIVE → EXPIRED
ACTIVE → USED
ACTIVE → CANCELLED

EXPIRED / USED / CANCELLED
  không tự quay lại ACTIVE vì timestamp lùi
```

Test chuỗi:

```text
Tạo đối tượng có hạn
→ ghi nhận hết hạn hoặc đã dùng theo hợp đồng
→ làm thời gian lùi
→ thử dùng lại
→ vẫn bị chặn, không tạo tác động mới
```

Ví dụ gate ở trên không triển khai state machine này. Cần kiểm thử aggregate/service/repository thật để xác nhận tính nguyên tử khi nhiều node tranh sử dụng.

Không tự áp cách lấy `max(now, previousNow)` cho toàn hệ thống mà bỏ qua thiết kế. Một giá trị nhảy quá xa vào tương lai có thể làm mốc đó mắc kẹt và gây từ chối kéo dài. Cơ chế watermark nếu dùng cần phạm vi, nguồn tin cậy, lưu trữ, cạnh tranh và chính sách phục hồi riêng.

## 13. Clock failure với queue, idempotency và lease

### 13.1. Job đến sau thời hạn

Chuỗi test:

```text
API nhận command khi báo giá còn hạn
→ job chờ trong queue
→ worker đọc clock lệch hoặc nhận job sau hạn
→ quyết định thực hiện
```

Expected phụ thuộc thời điểm có thẩm quyền đã chốt. Nếu yêu cầu còn hạn lúc thực hiện, kiểm tra worker không chỉ tin timestamp tiếp nhận.

Nếu message là event của quyết định đã commit, xử lý theo hợp đồng event; không tự bỏ một sự kiện lịch sử hợp lệ chỉ vì nó được giao muộn.

### 13.2. Dọn idempotency sớm

Kịch bản:

```text
Thao tác K đã tạo tác động thành công
→ clock cleanup nhảy tiến
→ bản ghi chống trùng bị xóa sớm
→ cùng thao tác được giao lại
```

Kiểm tra tác động không bị tạo lại. Một ràng buộc nghiệp vụ bền vững trên đối tượng có thể là lớp bảo vệ cần thiết bên cạnh TTL của key.

Ở chiều ngược lại, clock lùi có thể làm dữ liệu chống trùng giữ lâu hơn dự kiến, ảnh hưởng tài nguyên hoặc tái sử dụng key theo hợp đồng. Đừng chỉ kiểm tra một hướng.

### 13.3. Lease hết hạn và worker cũ tiếp tục chạy

Nếu worker A tin lease còn hạn còn worker B tin lease đã hết, có thể xuất hiện hai bên cùng thực hiện.

Kiểm thử không chỉ đọc trạng thái lease. Quan sát nơi ghi dữ liệu hoặc tạo tác động cuối:

- Worker cũ có bị từ chối khi đã mất quyền xử lý không?
- Version/fencing hoặc cơ chế tương ứng có được nơi nhận kiểm tra không?
- Tác động ngoài có idempotency hoặc giới hạn nghiệp vụ phù hợp không?

Chỉ gắn một số fencing vào request mà nơi ghi không thực thi nó chưa tạo bảo đảm.

## 14. Clock skew giữa app, database và provider

Dựng ít nhất hai nguồn clock có thể điều khiển:

```text
Clock A: node tạo yêu cầu
Clock B: node thực hiện
Clock C: nguồn quyết định hoặc dữ liệu tham chiếu trong test
```

Thử các tổ hợp:

| Node tạo | Node thực hiện | Mục tiêu |
|---|---|---|
| Bình thường | Chậm | Không dùng quá hạn theo nguồn quyết định |
| Nhanh | Bình thường | Không tạo deadline sai hoặc hiệu lực kéo dài |
| Chậm | Nhanh | Không từ chối trái hợp đồng mà không có trạng thái rõ |
| Đứng | Tiến bình thường | Phát hiện nguồn mất độ mới |
| Cùng offset sai | Cùng offset sai | Không nhầm đồng thuận giữa node với đúng thời gian tuyệt đối |

Nếu database là nguồn so thời hạn, kiểm tra kiểu dữ liệu, độ chính xác và ý nghĩa hàm thời gian của sản phẩm đang dùng. Thời gian được giữ cố định trong transaction và thời gian tại từng statement có thể có ngữ nghĩa khác nhau tùy hệ quản trị.

Provider có thể quyết định timeout hoặc hạn giao dịch bằng nguồn riêng. Test cần phân biệt hạn ứng dụng, hạn request và kết quả giao dịch thực tế. HTTP timeout không chứng minh provider chưa thực hiện tác động.

Không thể sửa mọi khác biệt bằng cách tăng tolerance vô hạn. Tolerance làm thay đổi cửa sổ hành vi và phải có chính sách rõ.

## 15. Timezone, DST và độ chính xác

### 15.1. Cùng instant không được đổi hạn tuyệt đối

Đổi cách hiển thị từ UTC sang một timezone khác không được làm báo giá tuyệt đối có thêm hiệu lực.

Test cùng `Instant` dưới nhiều `ZoneId` để phát hiện logic vô tình dùng ngày/giờ mặc định của máy.

### 15.2. Quy tắc theo lịch cần xử lý gap và overlap

Trong timezone có DST, một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần. Java `ZonedDateTime` có quy tắc xử lý các trường hợp gap/overlap, nhưng mặc định thư viện không thay thế quyết định nghiệp vụ về cách áp hạn mức hoặc lịch chạy. [Java ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html).

Với hạn mức theo ngày, cần xác định:

- Ngày được tính theo timezone nào.
- Mốc bắt đầu/kết thúc kỳ.
- Cách xử lý chuyển đổi lịch.
- Cách nhận diện kỳ bằng dữ liệu bền vững.
- Clock lùi có được mở lại kỳ cũ hay không.

Không coi một ngày theo lịch luôn là một `Duration` 24 giờ trong mọi timezone.

### 15.3. Chuỗi qua storage và serialization

Test:

```text
Tạo expiresAt
→ serialize
→ lưu database
→ đọc lại ở node khác
→ so tại đúng biên
```

Kiểm tra offset bị mất, trường epoch nhầm giây/mili giây, timestamp bị cắt và local time bị diễn giải bằng timezone khác.

Đây là lỗi tích hợp về ngữ nghĩa thời gian dù clock phần cứng có thể vẫn hoạt động bình thường.

## 16. Kịch bản failure test đầy đủ

Một quy trình thực hành:

1. **Chọn bất biến:** ví dụ báo giá hết hạn không tạo giao dịch mới.
2. **Chốt nguồn và điểm quyết định:** lúc nhận, lúc xử lý hoặc lúc ghi nhận theo hợp đồng.
3. **Dựng fixture:** actor, tenant, trạng thái, số tiền, version và deadline hợp lệ.
4. **Chạy đối chứng:** thời gian tin cậy, trong cửa sổ, nghiệp vụ thành công đúng một lần.
5. **Chèn một loại lỗi:** nhảy lùi, nhảy tiến, đứng hoặc nguồn không đọc được.
6. **Thực hiện thao tác:** giữ các guard khác đúng để cô lập vấn đề thời gian.
7. **Quan sát tác động:** dữ liệu lưu, event thành công, ledger/provider nếu thuộc phạm vi.
8. **Phục hồi nguồn:** kiểm tra cách trở lại hoạt động, không tự kéo dài deadline hoặc hồi sinh trạng thái.
9. **Đối soát:** mọi thao tác có kết quả, không mất truy vết hoặc tạo tác động trùng.
10. **Giữ regression case:** lưu trace và các mốc thời gian cụ thể.

Dùng nguồn clock test ở lớp có thể inject trước. Nếu cần kiểm thử thay đổi thời gian hệ thống, thực hiện trong môi trường cô lập có kế hoạch và đo cả các thành phần bị ảnh hưởng. Một thay đổi toàn máy có thể tác động đến database, broker, chứng thực và công cụ quan sát, làm nguyên nhân khó phân biệt.

### 16.1. Ca tích hợp: dùng báo giá một lần khi clock biến động

Ca này nối quyết định thời gian với quyền theo đối tượng, giá và transaction. Dùng application service cùng repository thật trong môi trường test; gate thuần ở phần 7 chỉ là một thành phần của đường xử lý.

Fixture cố định:

```text
Quote Q:
  tenant = T, buyer = U, amount = 100000 VND
  state = ACTIVE, version = 7
  validFrom = 2030-01-01T10:00:00Z
  expiresAt = 2030-01-01T10:01:00Z

Approval A:
  state = APPROVED
  gắn với Q, T, U, version 7 và amount 100000 VND

Command:
  actor = U, tenant = T, quoteId = Q, idempotencyKey = K
```

Chốt hợp đồng cho bài thực hành: cửa sổ hiệu lực được đánh giá tại bước service quyết định tiêu thụ báo giá, sau khi đã lấy dữ liệu cần thiết. Việc tiêu thụ báo giá, tiêu thụ phê duyệt, tạo đơn và lưu kết quả cho K phải nhất quán trong transaction theo thiết kế. Nếu dùng outbox, bản ghi yêu cầu phát event thành công thuộc cùng transaction. Thời điểm guard được đánh giá và thời điểm commit vật lý cần được phân biệt; ca này không đặt điều kiện provider phải hoàn tất trước `expiresAt`.

Để tái hiện đúng vị trí lỗi, đặt barrier do test điều khiển ngay trước bước quyết định. Đợi service đến barrier, đổi clock hoặc health rồi cho tiếp tục. Không dùng sleep để đoán rằng service đã đọc báo giá xong.

Mỗi hàng dưới đây dùng fixture mới, trừ hàng ghi rõ chạy tiếp sau một lần thành công. Clock tham chiếu và health do test điều khiển độc lập với clock đang bị gây lỗi.

| Chuỗi thử | Kết quả kỳ vọng theo hợp đồng |
|---|---|
| Nguồn tin cậy, quyết định tại `10:00:30Z` | Tạo một đơn giá 100000 VND; Q được dùng và A được tiêu thụ đúng một lần |
| Đọc Q lúc `10:00:59Z`, dừng ở barrier, nhảy đến đúng `10:01:00Z` | Từ chối hết hạn; không dùng lại kết quả kiểm tra từ trước barrier |
| Clock worker đứng ở `10:00:30Z`, nguồn tham chiếu tiến qua hạn và monitor báo mất tin cậy | Tạm hoãn hoặc từ chối theo chính sách; không tạo đơn |
| Tại barrier, nguồn clock không đọc được | Kết quả nguồn thời gian không khả dụng; không tiêu thụ Q hoặc A |
| Cùng instant còn hạn nhưng actor hoặc tenant không khớp fixture | Từ chối theo quyền đối tượng; clock tốt không thay thế kiểm tra quyền |
| Client gửi giá 1 VND hoặc sửa version báo giá nhưng giữ A cũ | Không tạo đơn sai giá hoặc dùng phê duyệt không còn gắn với dữ liệu được duyệt |
| Sau khi K thành công và kết quả đã commit, retry K lúc đã hết hạn | Trả kết quả đã lưu cho cùng command theo hợp đồng idempotency; không tạo đơn mới |
| Sau khi thành công, lùi clock về trước hạn rồi dùng Q với key khác | Trạng thái đã dùng vẫn chặn lần tiêu thụ thứ hai |

Đối với ca bị từ chối trước khi có quyết định thành công, đọc lại storage để xác nhận Q vẫn `ACTIVE`, A vẫn `APPROVED`, không có đơn và không có bản ghi outbox thành công. Audit từ chối hoặc bản ghi theo dõi lần thử có thể tồn tại theo thiết kế. Với ca thành công và các lần retry, tổng số đơn cho Q phải bằng một, số lần tiêu thụ A bằng một và số ý định phát event thành công bằng một. Nếu broker giao event nhiều lần, kiểm tra thêm số tác động cuối tại consumer; không suy ra số lần giao message từ số dòng outbox.

Ca retry sau hạn chỉ áp dụng khi K đã gắn với một kết quả thành công bền vững và cùng nội dung command. Key đang xử lý, kết quả chưa rõ hoặc key được dùng lại với payload khác cần nhánh xử lý riêng; không được mặc định chúng đều là thành công cũ.

## 17. Tiêu chí pass/fail và bằng chứng

### 17.1. Tính đúng nghiệp vụ

- Không dùng thời gian client để tự cấp thêm hiệu lực.
- Không thực hiện thao tác nhạy cảm khi điều kiện thời gian chưa được xác nhận theo chính sách.
- Biên bắt đầu và kết thúc được thực thi đúng.
- Trạng thái kết thúc không tự quay lại chỉ vì clock lùi.
- Cleanup và retry không tạo tác động trùng.
- Guard về quyền, đối tượng, version và hạn mức vẫn được áp dụng.
- Phục hồi clock không âm thầm đổi deadline đã lưu.

### 17.2. Hành vi khi suy giảm

- Phân biệt hết hạn, chưa đến hạn, nguồn không đọc được và nguồn không tin cậy.
- Có trạng thái tạm hoãn hoặc từ chối rõ theo hợp đồng.
- Không retry vô hạn một lỗi thời gian không thể tự khắc phục bằng retry nhanh.
- Không coi mọi exception là một quyết định nghiệp vụ hợp lệ.
- Có tín hiệu quan sát đủ để điều tra.

### 17.3. Bằng chứng cần lưu

```text
Loại lỗi và timeline chèn lỗi
Clock từng node và nguồn tham chiếu trong test
Health/uncertainty cùng độ mới
Deadline, timezone, độ chính xác và version dữ liệu
Thời điểm quyết định theo nguồn được chọn
Kết quả expected/actual
Operation ID và tác động bền vững
Thời điểm phục hồi và kết quả sau phục hồi
Giới hạn: unit, fake, database, queue hoặc provider sandbox
```

Không dùng duy nhất timestamp từ node đang lỗi để chứng minh thứ tự toàn bộ sự kiện. Kết hợp correlation, số thứ tự, version hoặc nguồn thời gian tham chiếu phù hợp.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Inject Clock rồi cho rằng đã giải quyết clock failure | Chỉ có điểm thay nguồn, chưa có chính sách tin cậy | Test health, sai lệch và tác động |
| Test chỉ dùng sleep | Chậm, không xác định, khó chạm biên | Điều khiển clock và nguồn elapsed |
| Cả monitor và nghiệp vụ dùng cùng nguồn bị đứng | Không nhận ra thời gian không tiến | Có cơ sở kiểm tra độc lập phù hợp |
| Dùng UTC như bảo đảm chính xác | Timestamp vẫn có thể lệch | Tách timezone và chất lượng nguồn |
| Dùng nanoTime làm deadline chia sẻ | Giá trị không có cùng gốc giữa JVM | Dùng đúng ngữ nghĩa từng nguồn |
| Dùng wall clock cho elapsed budget | Timeout sai khi clock nhảy | Dùng nguồn đo khoảng thời gian phù hợp |
| Mọi lỗi đọc clock đều được bỏ qua | Tạo đường cho nghiệp vụ không đủ điều kiện | Kết quả suy giảm tường minh |
| Cộng grace period để test pass | Kéo dài quyền ngoài hợp đồng | Xác định chính sách sai số và biên |
| Chỉ test timestamp, không test tác động | Có thể vẫn ghi đơn hoặc gửi tiền sai | Đối soát dữ liệu và tác động |
| Clock lùi làm đối tượng hết hạn hoạt động lại | Dùng lại quyền hoặc giá cũ | State machine/ràng buộc bền vững phù hợp |
| TTL idempotency là lớp bảo vệ duy nhất | Cleanup sớm mở đường xử lý trùng | Giữ bất biến đối tượng và kiểm tra vòng đời |
| Cho rằng transaction làm mọi đồng hồ nhất quán | Không bảo vệ thời gian của nguồn ngoài | Chốt điểm quyết định và test tích hợp |

## 19. Bài tập thực hành

### Bài tập 1: Biên hiệu lực

Dùng cửa sổ `[validFrom, expiresAt)` và viết các ca đúng đầu, trước đầu, ngay trước hạn, đúng hạn và sau hạn.

Bổ sung vòng lưu/đọc timestamp với độ chính xác mili giây và giải thích sự khác biệt với unit test nano giây.

### Bài tập 2: Frozen clock

Giữ wall clock cố định nhưng cho nguồn elapsed trong test tiến. Thiết kế expected cho monitor sau khoảng quan sát đã định.

Nêu vì sao monitor chỉ đọc cùng wall clock không đủ xác nhận độ mới.

### Bài tập 3: Nhảy lùi sau trạng thái kết thúc

Dựng đối tượng đã hết hạn hoặc đã dùng theo hợp đồng. Lùi clock về trước hạn rồi thử thực hiện lại.

Kiểm tra trạng thái bền vững và số tác động, thay vì chỉ gọi lại gate thuần.

### Bài tập 4: Idempotency cleanup

Một thao tác đã hoàn tất, rồi clock của tiến trình cleanup nhảy tiến. Mô tả cách kiểm tra retry không tạo tác động lần hai.

Phân biệt việc giữ key trong thời hạn với ràng buộc nghiệp vụ của đối tượng.

### Bài tập 5: Hai node lệch nhau

Node nhận và worker có clock khác nhau. Chốt nguồn có thẩm quyền, mô phỏng hai chiều lệch và định nghĩa expected.

Nếu không thể xác nhận thời gian trong giới hạn sai số, viết hành vi suy giảm thay vì tự nới thời hạn.

## 20. Tiêu chí tự kiểm tra bài làm

- Mỗi quy tắc thời gian có nguồn và thời điểm quyết định rõ.
- Đã phân biệt wall clock, lịch địa phương và elapsed time.
- Có test biên cùng test nhảy tiến, lùi, đứng và không đọc được.
- Health không bị coi là đúng chỉ vì clock trả một Instant.
- Mẫu suy giảm được kiểm tra với tác động nghiệp vụ thật ở lớp thích hợp.
- Phục hồi không hồi sinh trạng thái hoặc kéo dài deadline ngoài hợp đồng.
- Queue, cleanup, retry và restart được xét nếu có ảnh hưởng.
- Expected không dựa hoàn toàn vào cùng nguồn thời gian đang bị gây lỗi.
- Bằng chứng nối được thao tác, dữ liệu, nguồn thời gian và tác động.
- Những bảo đảm chưa được unit test chứng minh có kiểm thử tích hợp tương ứng.

Clock failure testing giúp kiểm tra điều kiện thời gian như một phần của hợp đồng nghiệp vụ. Kết quả cần đạt là hệ thống quyết định đúng khi nguồn còn đủ tin cậy, xử lý rõ khi không thể xác nhận và giữ nguyên các bất biến về quyền, trạng thái, tiền và số lần thực hiện.
