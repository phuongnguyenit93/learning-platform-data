# Time rule testing: Kiểm thử quy tắc nghiệp vụ phụ thuộc thời gian

## 1. Kiểm thử thời gian phải chứng minh điều gì?

Kiểm thử quy tắc thời gian không dừng ở việc kiểm tra phép so sánh `now < expiresAt`. Mục tiêu là chứng minh hệ thống thực thi đúng quyền và trạng thái tại mốc đã quy định, kể cả khi có retry, chờ khóa, thông điệp đến muộn hoặc đồng hồ bất thường.

Ví dụ một khách giữ hai sản phẩm trong năm phút. Các câu hỏi cần kiểm thử gồm:

- Đến đúng hạn, API có từ chối xác nhận không?
- Nếu worker chưa thu hồi, khách có lợi dụng trạng thái `HELD` để xác nhận muộn không?
- Nếu request đến trước hạn nhưng chờ khóa đến sau hạn, hệ thống xét theo mốc nào?
- Nếu xác nhận cạnh tranh với thu hồi, tài nguyên có vừa được cam kết vừa được hoàn lại không?
- Nếu khách sửa timestamp, múi giờ hoặc gửi lại request cũ, họ có được thêm thời gian không?
- Nếu lần đầu đã thành công nhưng mất phản hồi, retry sau hạn có nhận đúng kết quả cũ không?

Đầu ra của kiểm thử cần bao gồm **quyết định và tác động nghiệp vụ**: trạng thái cuối, bộ đếm tài nguyên, số lần nhận quyền lợi, bản ghi idempotency và sự kiện. Một mã HTTP đúng chưa đủ chứng minh dữ liệu đúng.

Trong phạm vi bảo mật logic nghiệp vụ, thời gian luôn được xét cùng business invariants, state machine, quyền theo đối tượng và ranh giới transaction.

## 2. Viết hợp đồng kiểm thử trước khi chọn công cụ

Một bộ test ổn định bắt đầu từ mô tả có thể kiểm chứng, không bắt đầu từ `sleep`.

Giả sử nghiệp vụ giữ chỗ có hợp đồng:

| Nội dung | Quy tắc minh họa |
| --- | --- |
| Nguồn thời gian quyết định | Nguồn có thẩm quyền tại nơi cập nhật dữ liệu |
| Mốc lấy thời gian | Sau khi lấy đủ khóa cần thiết |
| Xác nhận lượt giữ | Chỉ khi `state == HELD` và `decision_at < expires_at` |
| Đúng thời điểm hết hạn | Không được xác nhận |
| Gia hạn | Phải còn hạn, đúng quyền và chưa vượt trần |
| Lượt đã hết hạn | Không được hồi sinh bằng xác nhận hay gia hạn |
| Retry thành công | Trả kết quả đã commit nếu cùng ý định |
| Thu hồi | Chỉ một chuyển trạng thái được hoàn tài nguyên |
| Dữ liệu client | Không được quyết định “bây giờ” hoặc tự thay đổi hạn |
| Tác động bên ngoài | Thực hiện theo cơ chế chịu được xử lý lặp |

Nếu quy tắc là chương trình ưu đãi, có thể dùng cửa sổ:

~~~text
starts_at <= decision_at < ends_at
~~~

Nếu quy tắc bảo vệ yêu cầu **được tiếp nhận trước hạn**, hợp đồng phải chỉ rõ nơi ghi nhận tiếp nhận, cách bảo vệ timestamp, thời gian được xử lý muộn và cách giữ quota. Không dùng bộ test của hợp đồng “quyết định sau khóa” để đánh giá một hợp đồng khác.

Cũng cần nói rõ một quyết định được chấp nhận trước hạn có thể commit sau hạn hay không. Trong các ví dụ transaction của bài này, mốc quyết định được đọc sau khóa, các khóa được giữ đến commit và quyết định hợp lệ trước hạn có thể commit sau hạn. Nếu nghiệp vụ yêu cầu mốc khác, tiêu chí kiểm thử phải thay đổi tương ứng.

### Các bất biến dùng xuyên suốt

Với pool tài nguyên trong mô hình chưa có quy trình hoàn trả sau xác nhận:

~~~text
held_units >= 0
committed_units >= 0
held_units + committed_units <= capacity

held_units = tổng units của allocation có state HELD
committed_units = tổng units của allocation có state CONFIRMED
~~~

Ở đây `held_units` bao gồm lượt đã quá hạn nhưng chưa được transaction thu hồi. Quyền xác nhận đã mất hiệu lực, còn kế toán tài nguyên chỉ thay đổi khi thu hồi commit.

Các bất biến khác:

1. Lượt `EXPIRED` không quay về `HELD` hoặc `CONFIRMED`.
2. Một lượt chỉ được hoàn tài nguyên một lần.
3. Một quyền lợi giới hạn một lần chỉ có tối đa một lần cấp hợp lệ.
4. Timestamp do client sửa không thay đổi quyết định có thẩm quyền.
5. Retry không tạo thêm tài nguyên, kéo dài hạn hoặc tiêu hao thêm quyền lợi.
6. Người không có quyền trên đối tượng không được đổi trạng thái dù thời gian hợp lệ.

## 3. Xây dựng kết quả kỳ vọng độc lập với implementation

Kết quả kỳ vọng của test phải xuất phát từ hợp đồng. Nếu test gọi chính hàm đang kiểm thử để tính expected, test chỉ lặp lại implementation.

Ví dụ cửa sổ `[09:00, 10:00)`:

| Thời điểm quyết định | Kết quả kỳ vọng |
| --- | --- |
| 08:59:59.999 | Từ chối vì chưa bắt đầu |
| 09:00:00.000 | Chấp nhận xét các điều kiện còn lại |
| 09:30:00.000 | Chấp nhận xét các điều kiện còn lại |
| 09:59:59.999 | Chấp nhận xét các điều kiện còn lại |
| 10:00:00.000 | Từ chối vì đã kết thúc |
| 10:00:00.001 | Từ chối vì đã kết thúc |

Bảng này giả định độ chính xác kiểm thử là mili giây. Khi kiểm tra lưu trữ có độ chính xác khác, phải chọn bước thời gian phù hợp với hợp đồng thực tế.

Nên bổ sung cả dữ liệu không hợp lệ:

- Thời điểm bắt đầu bằng thời điểm kết thúc.
- Thời điểm kết thúc trước bắt đầu.
- Thiếu múi giờ ở trường bắt buộc là một thời điểm tuyệt đối.
- Thời lượng âm hoặc quá lớn so với chính sách.
- Hạn gia hạn vượt trần vòng đời.
- Giá trị ngày giờ không thể phân tích theo định dạng được hỗ trợ.

Phân biệt lỗi xác thực dữ liệu với lỗi hết hiệu lực nghiệp vụ. Test không nên chỉ chấp nhận “có lỗi bất kỳ”, vì một lỗi parse không chứng minh hệ thống đã chặn được xác nhận sau hạn.

## 4. Chọn tầng kiểm thử phù hợp

| Tầng | Điều cần chứng minh | Điều tầng này chưa chứng minh |
| --- | --- | --- |
| Unit test chính sách | Toán tử biên, cửa sổ, giới hạn gia hạn, cách tính kỳ | Khóa và tính nguyên tử của cơ sở dữ liệu |
| Test service với clock điều khiển được | Đọc thời gian đúng điểm, dùng cùng mốc, kiểm tra quyền và trạng thái | Hành vi thật của adapter thời gian và hệ quản trị |
| Integration test | Kiểu thời gian, độ chính xác lưu trữ, transaction, ràng buộc chống trùng | Toàn bộ đường HTTP, gateway và consumer |
| Test tranh chấp đồng thời | Kết quả cuối của các thứ tự xác nhận, gia hạn, thu hồi | Mọi lịch thực thi có thể có |
| Test API hoặc luồng đầu cuối | Client không thể sửa thời gian hoặc đi vòng quy trình | Mọi lỗi nội bộ nếu không kiểm tra dữ liệu |
| Test phục hồi và lỗi | Worker restart, sự kiện trùng, đồng hồ bất thường | Độ tin cậy tuyệt đối của đồng hồ ngoài thực tế |

Không bắt mọi trường hợp chạy qua toàn bộ hệ thống. Các phép so sánh thời gian thuần nên có test nhanh, chính xác; tranh chấp dữ liệu cần transaction thật; ranh giới tin cậy cần đi qua đường vào thực tế.

### Tách các loại đồng hồ

- **Đồng hồ thời gian lịch:** dùng với thời điểm kết thúc, ngày nghiệp vụ và audit.
- **Đồng hồ đo khoảng thời gian:** dùng đo timeout hoặc thời lượng nội bộ.
- **Scheduler điều khiển tác vụ:** quyết định khi callback hoặc timer được kích hoạt.

Đổi clock nghiệp vụ chưa chắc làm scheduler chạy. Đẩy scheduler ảo tiến lên cũng chưa chắc đổi thời gian của cơ sở dữ liệu. Bộ test phải điều khiển đúng thành phần và kiểm tra các adapter riêng.

Không dùng giá trị tuyệt đối của `System.nanoTime()` làm deadline lưu bền vững hoặc so sánh giữa các JVM. Nó phục vụ đo khoảng thời gian trong cùng JVM.

## 5. Unit test ranh giới bằng Java Time và JUnit

Ví dụ một chính sách thuần:

~~~java
import java.time.Instant;
import java.util.Objects;

public record TimeWindow(Instant startsAt, Instant endsAt) {
    public TimeWindow {
        Objects.requireNonNull(startsAt);
        Objects.requireNonNull(endsAt);
        if (!startsAt.isBefore(endsAt)) {
            throw new IllegalArgumentException("Invalid time window");
        }
    }

    public boolean allows(Instant decisionAt) {
        Objects.requireNonNull(decisionAt);
        return !decisionAt.isBefore(startsAt)
            && decisionAt.isBefore(endsAt);
    }
}
~~~

Ví dụ kiểm thử tham số hóa theo phong cách JUnit:

~~~java
import java.time.Instant;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TimeWindowTest {
    private final TimeWindow window = new TimeWindow(
        Instant.parse("2026-11-22T09:00:00Z"),
        Instant.parse("2026-11-22T10:00:00Z")
    );

    @ParameterizedTest
    @CsvSource({
        "2026-11-22T08:59:59.999Z, false",
        "2026-11-22T09:00:00.000Z, true",
        "2026-11-22T09:30:00.000Z, true",
        "2026-11-22T09:59:59.999Z, true",
        "2026-11-22T10:00:00.000Z, false",
        "2026-11-22T10:00:00.001Z, false"
    })
    void checksBusinessBoundary(String value, boolean expected) {
        assertEquals(expected, window.allows(Instant.parse(value)));
    }
}
~~~

Đoạn code cần phiên bản Java hỗ trợ record và các dependency JUnit thích hợp khi đưa vào dự án.

Trường hợp đúng tại hạn đặc biệt quan trọng. Nếu đổi `decisionAt.isBefore(endsAt)` thành `!decisionAt.isAfter(endsAt)`, test tại `10:00:00.000Z` phải thất bại.

Tương tự, test đúng thời điểm bắt đầu phải phát hiện việc vô tình đổi điều kiện bắt đầu từ bao gồm thành loại trừ.

## 6. Điều khiển thời gian mà không sửa đồng hồ hệ điều hành

Với service chọn đồng hồ ứng dụng làm nguồn có thẩm quyền, có thể truyền `Clock` vào constructor:

~~~java
public final class EligibilityService {
    private final Clock clock;

    public EligibilityService(Clock clock) {
        this.clock = clock;
    }

    public boolean isEligible(TimeWindow window) {
        Instant decisionAt = clock.instant();
        return window.allows(decisionAt);
    }
}
~~~

Một test tại đúng hạn dùng:

~~~java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-22T10:00:00Z"),
    ZoneOffset.UTC
);

EligibilityService service = new EligibilityService(fixed);
assertFalse(service.isEligible(window));
~~~

Các đoạn minh họa này cần import Java Time và assertion tương ứng. Không cần chờ đến ngày giờ thật.

Nếu cần diễn tiến nhiều bước, có thể dùng clock thay đổi được trong mã hỗ trợ kiểm thử:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableTestClock extends Clock {
    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public MutableTestClock(Instant initial, ZoneId zone) {
        this(
            new AtomicReference<>(Objects.requireNonNull(initial)),
            Objects.requireNonNull(zone)
        );
    }

    private MutableTestClock(
        AtomicReference<Instant> current,
        ZoneId zone
    ) {
        this.current = current;
        this.zone = zone;
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new MutableTestClock(
            current, Objects.requireNonNull(newZone)
        );
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    public void advance(Duration delta) {
        current.updateAndGet(t -> t.plus(delta));
    }

    public void set(Instant value) {
        current.set(Objects.requireNonNull(value));
    }
}
~~~

`withZone` chia sẻ cùng mốc hiện tại, vì đổi múi giờ biểu diễn không được tạo một dòng thời gian độc lập.

Clock này cho phép mô phỏng tiến và lùi thời gian. Nó an toàn ở mức thao tác đọc/ghi giá trị, nhưng không tự điều phối thứ tự các thread trong test. Với test đồng thời vẫn cần latch hoặc barrier.

Mỗi test nên có clock riêng. Không thay một singleton toàn cục trong lúc các test khác đang chạy song song.

Nếu production chọn thời gian cơ sở dữ liệu, thay `Clock` của ứng dụng không kiểm chứng được nguồn đó. Cần test adapter cơ sở dữ liệu riêng và bảo đảm service đọc đúng nguồn trong transaction.

Không thêm header hoặc endpoint công khai để khách thay clock nhằm phục vụ kiểm thử.

## 7. Kiểm thử diễn tiến trạng thái qua thời gian

Dùng một timeline rõ ràng thay vì các phép chờ ngẫu nhiên:

~~~text
T0:
  tạo lượt giữ 2 đơn vị
  state = HELD
  expires_at = T0 + 5 phút
  held_units tăng 2

T0 + 4 phút 59,999 giây:
  xác nhận được phép nếu quyền và điều kiện khác đúng

T0 + 5 phút:
  xác nhận hoặc gia hạn mới bị từ chối
~~~

Mỗi nhánh nên bắt đầu từ fixture riêng. Nếu test đã xác nhận thành công trước hạn, sau đó gọi lại tại hạn thì đó là test retry trên `CONFIRMED`, không còn là test xác nhận một lượt `HELD` hết hạn.

### Hai kiểu thu hồi cần phân biệt

Một API có thể chỉ từ chối lượt quá hạn và để worker thu hồi sau, hoặc tự thu hồi trong transaction. Bộ test phải chọn rõ hợp đồng của ứng dụng.

Trong kịch bản minh họa dưới đây, API tự thu hồi khi gặp lượt giữ quá hạn:

~~~text
Given:
  pool.capacity = 10
  pool.held_units = 2
  pool.committed_units = 0
  allocation.state = HELD
  allocation.units = 2
  allocation.expires_at = T

When:
  clock = T
  đúng chủ sở hữu gọi confirm

Then:
  kết quả nghiệp vụ = ALLOCATION_EXPIRED
  allocation.state = EXPIRED
  pool.held_units = 0
  pool.committed_units = 0
  đúng một sự kiện thu hồi được ghi vào outbox
  không có biên nhận xác nhận thành công
~~~

Test này phải đọc dữ liệu sau khi transaction kết thúc. Nếu service vừa ghi thu hồi vừa ném exception làm rollback, mã lỗi có thể đúng nhưng các khẳng định trạng thái và bộ đếm sẽ thất bại.

Nếu hợp đồng chọn thu hồi sau bằng worker, expected phải là không tăng `committed_units`, chưa hoàn `held_units` tại API và hoàn đúng một lần khi worker chạy. Không viết assertion chấp nhận tùy ý cả hai kết quả, vì nó che việc triển khai chưa rõ hợp đồng.

### Các chuỗi bắt buộc

- Tạo → hết hạn → xác nhận: từ chối, không hồi sinh.
- Tạo → gia hạn hợp lệ → vượt hạn cũ nhưng chưa tới hạn mới → xác nhận: được xét theo hạn mới.
- Tạo → hết hạn → gia hạn: từ chối.
- Tạo → hủy → nhận thông điệp hết hạn cũ: không hoàn tài nguyên thêm lần nữa.
- Tạo → xác nhận → thời gian vượt hạn cũ: không tự hủy cam kết đã hoàn tất.
- Tạo → gia hạn đến trần → retry hoặc gia hạn thêm: không vượt tổng tuổi thọ.
- Tạo → hết hạn → đồng hồ quay lùi: trạng thái cuối vẫn đóng.

Với hợp đồng dùng một mốc cho mỗi quyết định, có thể dùng test double trả các giá trị khác nhau qua từng lần đọc để phát hiện việc kiểm tra bằng một mốc nhưng ghi audit bằng mốc khác. Assertion chính vẫn nên là điều kiện và audit cùng sử dụng `decision_at` đã chọn, thay vì chỉ đếm số lần gọi một hàm.

## 8. Kiểm thử nguồn thời gian và lưu trữ thật

### 8.1. Không đồng nhất mock với bằng chứng tích hợp

Mock `TimeSource` cho ra một thời điểm đúng giúp kiểm tra chính sách. Nó chưa chứng minh implementation production:

- Dùng đúng kết nối transaction.
- Đọc giờ sau khi lấy đủ khóa.
- Không đọc từ replica hoặc máy khác ngoài hợp đồng.
- Không dùng hàm có ngữ nghĩa thời gian khác.
- Lưu và đọc lại hạn mà không sai múi giờ hoặc độ chính xác.

Cần có test adapter thực hiện truy vấn thật và kiểm tra cách nó tham gia transaction. Nếu adapter mở kết nối mới, kết quả có thể không gắn với ranh giới kiểm tra và cập nhật mà thiết kế yêu cầu.

### 8.2. Kiểm thử transaction chạy lâu

Trong PostgreSQL, `CURRENT_TIMESTAMP`, `now()` và `transaction_timestamp()` phản ánh thời điểm bắt đầu transaction; `clock_timestamp()` phản ánh thời gian tại lúc gọi.

Với hợp đồng xét sau khóa, một regression test cần phát hiện việc vô tình thay hàm đọc giờ thực bằng thời gian bắt đầu transaction.

Có thể chia thành hai lớp:

1. **Test service có điều phối:** giữ khóa, cho request chờ, điều khiển nguồn thời gian thử nghiệm và chứng minh thời gian được lấy sau khi khóa đã sẵn sàng.
2. **Test adapter thật:** xác minh hàm thời gian và kết nối thực tế trong hệ quản trị đang dùng.

Với một bài kiểm thử đầu cuối rủi ro cao cần đi qua hạn thật:

~~~text
T1 giữ khóa cần thiết.
T2 bắt đầu trước expires_at và thực sự chờ khóa.
Test quan sát thời gian từ nguồn có thẩm quyền cho đến khi đã đến hạn.
T1 nhả khóa.
T2 lấy khóa, đọc thời gian và quyết định.
Expected: không xác nhận một lượt HELD đã hết hạn.
~~~

Đảm bảo T2 đã thực sự chờ khóa bằng cơ chế quan sát của cơ sở dữ liệu hoặc test hook phù hợp. Không chỉ khởi động một thread rồi mặc nhiên cho rằng nó đã đến câu lệnh khóa.

Lần chờ vượt hạn thực phải có timeout hữu hạn, dùng nguồn đo thời lượng phù hợp và chỉ áp dụng cho số ít test tích hợp cần thiết. Đây là chờ một điều kiện quan sát được, khác với `sleep(5000)` rồi hy vọng đủ lâu. Phần lớn test biên vẫn nên dùng thời gian điều khiển được.

### 8.3. Round-trip dữ liệu thời gian

Test nên ghi rồi đọc lại:

- Thời điểm UTC.
- Dữ liệu đầu vào có offset khác nhưng biểu diễn cùng một instant.
- Giá trị có phần lẻ sát độ chính xác lưu trữ.
- Hạn gần ngày mới theo múi giờ nghiệp vụ.
- Dữ liệu không hợp lệ theo hợp đồng API.

Ví dụ `2026-11-22T10:00:00+07:00` và `2026-11-22T03:00:00Z` biểu diễn cùng thời điểm. Nếu API hỗ trợ cả hai dạng, sau chuẩn hóa chúng phải tạo cùng quyết định.

So sánh instant sau chuẩn hóa, không đòi chuỗi định dạng phải giống nhau. Nhưng cũng không tự bỏ phần lẻ trong assertion nếu chính sách yêu cầu giữ độ chính xác đó.

Sau readback, chạy lại kiểm tra biên bằng hạn thực sự lưu. Một hạn bị làm tròn khi ghi có thể khiến test trên object trong bộ nhớ đúng, còn dữ liệu production cho kết quả khác.

## 9. Kiểm thử tranh chấp xác nhận, thu hồi và gia hạn

Khởi chạy nhiều thread cùng lúc rồi chạy lặp hàng trăm lần chỉ cung cấp một phần bằng chứng. Nên tạo các thứ tự có chủ đích.

Trong mô hình minh họa, mọi đường ghi khóa pool trước, allocation sau. Test fixture, worker và API cũng phải tuân thủ thứ tự này.

### 9.1. Xác nhận thắng

~~~text
A: khóa pool và allocation
A: đọc decision_at trước expires_at
A: quyết định xác nhận, dừng tại test barrier trước commit

B: thử thu hồi, phải chờ khóa

Thời gian đi qua expires_at
A: commit
B: lấy khóa, đọc lại state = CONFIRMED, không thu hồi
~~~

Expected với pool một đơn vị:

~~~text
allocation.state = CONFIRMED
held_units = 0
committed_units = 1
số lần thu hồi tài nguyên = 0
~~~

Theo hợp đồng đã chọn, việc A commit sau hạn không làm quyết định trước hạn thành sai. Test phải tránh vô tình áp đặt một hợp đồng thời gian khác.

### 9.2. Thu hồi thắng

~~~text
A: sau hạn, khóa và chuyển HELD -> EXPIRED
B: thử xác nhận, chờ khóa
A: hoàn held_units và commit
B: đọc lại EXPIRED, từ chối
~~~

Expected:

~~~text
allocation.state = EXPIRED
held_units = 0
committed_units = 0
số lần thu hồi tài nguyên = 1
số biên nhận xác nhận thành công = 0
~~~

### 9.3. Hai worker thu hồi cùng lượt

Cho hai worker cùng tìm thấy một ứng viên. Chỉ một worker được chuyển `HELD -> EXPIRED`; worker còn lại đọc trạng thái cuối hoặc không cập nhật được hàng nào.

Khẳng định:

- Bộ đếm chỉ giảm một lần.
- Không có giá trị âm hoặc khả dụng lớn hơn dung lượng.
- Chỉ một sự kiện nghiệp vụ thu hồi được tạo cho chuyển đổi đó.
- Retry cùng sự kiện ở consumer không tạo thêm tác động.

Nếu outbox có cơ chế phát lại, số lần giao thông điệp có thể lớn hơn một. Không nhầm số lần giao với số sự kiện nghiệp vụ hoặc số lần tác động có hiệu lực.

### 9.4. Gia hạn thắng lịch cũ

~~~text
A: tìm thấy ứng viên theo hạn cũ nhưng chưa khóa để thu hồi
B: gia hạn hợp lệ, cập nhật expires_at và generation, commit
A: khóa, đọc lại hạn hiện tại
A: không thu hồi lượt vẫn còn hiệu lực
~~~

Nếu thu hồi thắng trước, gia hạn phải thất bại trên trạng thái `EXPIRED`. Không cho phép nó cập nhật hạn rồi phục hồi lượt giữ.

### Điều phối test an toàn

Có thể dùng `CountDownLatch`, `CyclicBarrier` hoặc test hook có phạm vi kiểm thử. Luôn:

- Chạy bằng kết nối/transaction độc lập.
- Đặt timeout cho các lần chờ.
- Bảo đảm nhả barrier và kết thúc worker khi test lỗi.
- Thu thập exception trong thread phụ để test chính không bỏ sót lỗi.
- Kiểm tra dữ liệu sau khi các transaction đã hoàn tất.

Nếu test gặp deadlock, cần phân biệt deadlock do thiết kế khóa production với deadlock do test barrier giữ một bên trong khi chờ sự kiện không thể xảy ra.

## 10. Scheduler, thông điệp trùng và sự kiện đến muộn

### 10.1. Timer đánh thức sớm

Cho một thông điệp thu hồi đến trước `expires_at`. Consumer phải kiểm tra lại thời gian và không thu hồi sớm.

Sau đó chuyển clock đến hạn và kích hoạt xử lý lại hoặc chạy bộ quét đối soát. Test cần chứng minh cuối cùng tài nguyên được thu hồi, không chỉ chứng minh lần xử lý sớm là no-op.

Nếu consumer bỏ qua thông điệp sớm nhưng không còn lịch mới và không có bộ quét, lượt giữ có thể tồn đọng vô hạn.

### 10.2. Thông điệp của thế hệ cũ

~~~text
Ban đầu:
  generation = 7
  expires_at = T1

Sau gia hạn:
  generation = 8
  expires_at = T2, với T2 > T1

Thông điệp đến:
  expected_generation = 7
  expected_expires_at = T1
~~~

Expected: không dùng lịch cũ để kết thúc lượt còn hạn theo lịch mới. Consumer cần kiểm tra generation hoặc coi thông điệp chỉ là tín hiệu rồi quyết định theo trạng thái và hạn hiện tại.

Test thêm thông điệp cũ đến sau khi lượt đã kết thúc. Nó phải là no-op, không đổi bộ đếm.

### 10.3. Worker dừng và chạy lại

Tạo một nhóm lượt giữ, đưa thời gian qua hạn khi worker không chạy, sau đó khởi động lại worker hoặc gọi bộ quét.

Kiểm tra:

- Các lượt quá hạn được tìm lại từ dữ liệu bền vững.
- Không cần timer cũ trong bộ nhớ còn sống.
- Chạy lại bộ quét không hoàn tài nguyên thêm.
- Lượt đã xác nhận hoặc gia hạn hợp lệ không bị thu hồi nhầm.
- Từng lô xử lý vẫn giữ các bất biến.

### 10.4. Callback mang thời gian quá khứ

Một webhook thanh toán đến sau hạn có thể khai sự kiện xảy ra trước hạn. Bộ test cần tách:

- Nguồn không xác thực hoặc dữ liệu bị sửa: bị từ chối theo cơ chế xác thực.
- Sự kiện hợp lệ nhưng trùng ID: không xử lý thêm tác động.
- Sự kiện hợp lệ đến muộn: xử lý theo chính sách sự kiện muộn.
- Tài nguyên đã được cấp lại: không xác nhận chồng chỉ vì timestamp cũ.

Nếu chính sách bảo vệ yêu cầu đã tiếp nhận đúng hạn, hãy test chứng cứ tiếp nhận bị đổi đối tượng, chủ thể hoặc nội dung. Một dấu thời gian hợp lệ không được tái sử dụng cho ý định khác.

## 11. Kiểm thử ngày nghiệp vụ, múi giờ và lịch

### 11.1. Ranh giới ngày của chính sách

Với quyền nhận một lần mỗi ngày theo `Asia/Ho_Chi_Minh`, chọn hai instant ở hai phía của nửa đêm địa phương, không chọn nửa đêm UTC.

Test cần chứng minh:

1. Hai request trong cùng ngày nghiệp vụ chỉ nhận một lần.
2. Đến đúng ngày nghiệp vụ mới, chính sách cho phép quyền của ngày mới nếu các điều kiện khác đúng.
3. Gửi `businessDate` giả không đổi kỳ được tính trên server.
4. Đổi múi giờ thiết bị không tạo kỳ mới.
5. Nếu múi giờ hồ sơ hoặc chi nhánh được đổi, chính sách chuyển tiếp không cho cấp lại quyền trái phép.

Ràng buộc chống trùng theo kỳ cần được kiểm thử đồng thời. Hai request trong cùng kỳ không được cùng vượt qua bước “chưa có bản ghi”.

### 11.2. Ngày không dài đúng 24 giờ

Với lịch có thay đổi giờ mùa hè, ngày nghiệp vụ có thể dài 23 hoặc 25 giờ. Một ví dụ kiểm thử Java Time dùng dữ liệu lịch sử:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
LocalDate date = LocalDate.of(2024, 3, 10);

Instant start = date.atStartOfDay(zone).toInstant();
Instant nextStart = date.plusDays(1).atStartOfDay(zone).toInstant();

assertEquals(Duration.ofHours(23), Duration.between(start, nextStart));
~~~

Mục tiêu của ví dụ là phát hiện cách tính ngày mới bằng `start + 24 giờ`. Cần dùng dữ liệu múi giờ và chính sách lịch mà môi trường triển khai hỗ trợ.

Test thêm một ngày dài 25 giờ và một ngày bình thường. Nếu dữ liệu đầu vào là giờ địa phương có thể không tồn tại hoặc bị lặp khi đổi giờ, phải có expected rõ: từ chối, chọn offset cụ thể hoặc dịch chuyển theo chính sách. Không để hành vi mặc định của thư viện âm thầm trở thành quy tắc kinh doanh.

### 11.3. Cuối tháng, năm nhuận và lịch làm việc

Với thời hạn “một tháng”, “ba ngày làm việc” hoặc “đến cuối ngày”, bổ sung:

- Ngày cuối tháng có độ dài khác nhau.
- Ngày 29 tháng 2 của năm nhuận.
- Cuối năm và đầu năm.
- Ngày nghỉ theo lịch kinh doanh.
- Thay đổi phiên bản lịch hoặc múi giờ.

Không dùng cùng một expected cho thời lượng 30 ngày và một tháng theo lịch. Đây là hai hợp đồng khác nhau.

Nếu chính sách phụ thuộc lịch ngày nghỉ có thể thay đổi, fixture cần cố định phiên bản lịch. Test gọi dữ liệu lịch đang thay đổi từ môi trường ngoài sẽ khó tái hiện.

## 12. Retry và idempotency qua ranh giới thời gian

Đây là nơi test chỉ “trước hạn thành công, sau hạn thất bại” dễ bỏ sót lỗi.

| Kịch bản | Expected |
| --- | --- |
| Lần đầu commit trước hạn, phản hồi mất, retry sau hạn cùng key và ý định | Trả kết quả đã commit, không cấp thêm |
| Lần đầu rollback, retry sau hạn | Xét lại bằng trạng thái và thời gian của lần thử mới theo hợp đồng |
| Cùng key nhưng đổi allocation, số lượng hoặc thao tác | Từ chối, không mượn kết quả cũ |
| Retry gia hạn sau khi mất phản hồi | Không kéo dài hạn thêm lần nữa |
| Retry tạo lượt giữ đã hết hạn | Không tự tạo lượt mới hoặc hạn mới bằng key cũ |
| Retry thu hồi | Không hoàn tài nguyên thêm |
| Hai request cùng key chạy đồng thời | Chỉ một tác động nghiệp vụ có hiệu lực |

Ngoài response, cần khẳng định số lượng allocation, redemption hoặc confirmation thực sự được ghi. Một server có thể trả cùng response nhưng vẫn tạo tác động trùng phía sau.

Chính sách có lưu kết quả từ chối hay không cũng cần test. Nếu một request trước thời điểm bắt đầu bị từ chối, retry khi chương trình mở có thể được xét mới hoặc tiếp tục trả kết quả cũ tùy hợp đồng. Không để cache hoặc thời gian sống của key quyết định hành vi một cách tình cờ.

Khi idempotency hết thời gian lưu, test theo khoảng retry được hỗ trợ. Xóa key quá sớm có thể làm request cũ bị hiểu là ý định mới. Không coi việc thử lại sau khi key bị xóa là an toàn chỉ vì phép so sánh thời gian vẫn đúng.

## 13. Kiểm thử người dùng thao túng dữ liệu thời gian

Các test bảo mật cần đi qua đường vào mà người dùng thực sự kiểm soát.

Ví dụ một request giả định gửi thêm các trường không có quyền quyết định:

~~~json
{
  "allocationId": "hold-123",
  "clientNow": "2026-11-22T09:59:00Z",
  "expiresAt": "2026-11-23T10:00:00Z",
  "businessDate": "2026-11-21",
  "ownerId": "another-user",
  "state": "HELD"
}
~~~

Đây là dữ liệu phục vụ test trên hệ thống được phép kiểm thử, không phải mô tả một API cụ thể.

Tùy hợp đồng API, trường không được hỗ trợ có thể bị từ chối hoặc bỏ qua. Dù chọn cách nào, test phải chứng minh chúng không thay đổi thời gian có thẩm quyền, hạn, chủ sở hữu hay state machine.

Các biến thể cần kiểm tra:

- Client gửi thời gian trước hạn khi server đã qua hạn.
- Client gửi offset khác để cố làm lệch ngày.
- Client đổi header như `X-Request-Time` hoặc `X-Business-Time`.
- Client gửi trực tiếp timestamp vốn chỉ gateway nội bộ được phép ghi.
- Người dùng có quyền trên một allocation thử dùng ID allocation khác.
- Người dùng thuộc tenant khác gửi cùng thời điểm và cùng key.
- Người dùng gửi PATCH entity để sửa hạn thay vì gọi thao tác gia hạn.
- Tài khoản có quyền quản trị hạn chế thử vượt trần hoặc hồi sinh trạng thái cuối.

Expected về quyền không thay đổi chỉ vì đang trong cửa sổ hợp lệ. Đối tượng của người khác vẫn phải được bảo vệ.

Nếu hệ thống tin timestamp do gateway cung cấp, test đường đi phải chứng minh giá trị giả từ ngoài bị loại bỏ, nguồn gọi nội bộ được xác thực và không có đường truy cập vòng cho phép giả mạo cùng dữ liệu.

Với nhận quyền lợi theo ngày, kiểm thử hành vi đổi cấu hình được phép cũng quan trọng. Một endpoint đổi múi giờ có thể hợp lệ về quyền nhưng vẫn tạo lỗ hổng nếu hệ thống coi mỗi múi giờ mới là một kỳ nhận độc lập.

## 14. Kiểm thử lỗi và đồng hồ bất thường

### 14.1. Đồng hồ quay lùi

Kịch bản:

~~~text
T0: tạo lượt giữ
T1: đến hạn, thu hồi commit, state = EXPIRED
T2: nguồn thời gian trả về mốc trước T1
T3: gọi confirm hoặc renew
~~~

Expected: trạng thái cuối không hồi sinh; không tăng cam kết và không gia hạn.

Nếu việc quay lùi xảy ra trước khi một lượt được kết thúc, kết quả phụ thuộc chính sách xử lý độ tin cậy của nguồn thời gian. Không tự đặt expected rằng mọi hệ thống đều phải biết thời gian thật khi nguồn có thẩm quyền đã sai. Cần test cơ chế phát hiện hoặc tạm dừng theo chính sách vận hành của ứng dụng.

### 14.2. Đồng hồ nhảy tiến

Đưa thời gian vượt xa hạn rồi cho worker hoặc API xử lý. Sau đó chỉnh lại clock thử nghiệm.

Kiểm tra:

- Các thay đổi đã commit không tự biến mất.
- Không tự cấp lại quyền do thời gian quay về.
- Nếu hệ thống có chế độ tạm dừng quyết định nhạy cảm, nó được kích hoạt đúng chính sách.
- Bản ghi audit đủ giải thích quyết định dùng mốc nào.

Mục tiêu là kiểm thử cách phản ứng với nguồn lỗi, không chứng minh clock giả trong test có thể làm đồng hồ production chính xác.

### 14.3. Không đọc được nguồn thời gian

Cho adapter báo lỗi hoặc timeout. Test cần chứng minh:

- Không lấy timestamp từ request để thay thế.
- Không cấp quyền bằng một giá trị mặc định như đầu epoch hoặc hạn vô tận.
- Những thay đổi chưa commit cùng rollback.
- Chính sách fallback, nếu có, được giới hạn và audit rõ.
- Có thể retry an toàn khi nguồn phục hồi.

Không áp đặt một quy tắc chung cho mọi thao tác. Đọc thông tin, hủy, xác nhận và thu hồi có rủi ro khác nhau; expected phải dựa trên hợp đồng cụ thể.

### 14.4. Lỗi tại các điểm trong transaction

Chèn lỗi có kiểm soát tại các điểm:

| Điểm lỗi | Điều cần khẳng định |
| --- | --- |
| Sau kiểm tra hạn, trước ghi dữ liệu | Không có tác động nghiệp vụ đã commit |
| Sau đổi trạng thái, trước đổi bộ đếm | Cả trạng thái và bộ đếm rollback |
| Sau đổi bộ đếm, trước ghi outbox | Không có cập nhật một phần |
| Sau ghi idempotency, trước commit | Key và tác động cùng rollback |
| Sau commit, trước trả response | Retry trả kết quả cũ, không thực hiện thêm |
| Khi consumer xử lý lại outbox | Tác động ngoài có tính idempotent theo giao thức |

Một lỗi mất kết nối tại lúc commit có thể khiến caller không biết transaction đã commit hay chưa. Test cần bao phủ cả kết quả thực tế có thể xảy ra: nếu đã commit thì retry đọc kết quả cũ; nếu chưa commit thì lần thử mới xét lại theo hợp đồng. Không suy luận “không nhận response” đồng nghĩa “không có tác động”.

Test cũng cần xác nhận transaction retry lấy lại thời gian. Nếu lần đầu đúng hạn nhưng rollback, lần retry sau hạn không được tái sử dụng `decision_at` cũ để cấp quyền.

## 15. Kiểm thử theo mô hình và các thuộc tính

Các ví dụ cụ thể bắt lỗi tại mốc đã chọn. Kiểm thử theo mô hình giúp tìm lỗi trong những chuỗi dài hơn.

Có thể xây dựng mô hình nhỏ gồm:

~~~text
state: HELD | CONFIRMED | CANCELLED | EXPIRED
expires_at
max_hold_until
units
pool capacity và các bộ đếm
kết quả theo idempotency key
danh tính người gọi và quyền trên đối tượng
~~~

Sinh các lệnh như:

~~~text
create
advance_time
set_time_back
confirm
renew
cancel
deliver_expiration_message
retry_previous_request
fail_before_commit
restart_worker
~~~

Mô hình kỳ vọng phải được viết từ hợp đồng, đơn giản hơn hệ thống thật và không gọi lại implementation đang kiểm thử để tự tính expected.

### Các thuộc tính hữu ích

1. Sau mỗi chuỗi đã hoàn tất transaction, tổng tài nguyên không vượt dung lượng.
2. Không có bộ đếm âm.
3. Trạng thái cuối không quay về trạng thái giữ tạm.
4. Giao lại cùng một thông điệp không làm hoàn tài nguyên thêm.
5. Retry cùng ý định đã commit không tăng số tác động có hiệu lực.
6. Gia hạn thành công không vượt `max_hold_until`.
7. Người không có quyền không được đổi allocation.
8. Timestamp do khách cung cấp không thay thế thời gian có thẩm quyền.
9. Dữ liệu audit cho quyết định sử dụng đúng mốc và phiên bản chính sách.
10. Sau phục hồi và xử lý hết công việc đến hạn, không còn lượt quá hạn thuộc phạm vi cần thu hồi mà bị bỏ quên.

Thuộc tính cuối cần giới hạn rõ: giả định worker tiếp tục chạy, nguồn thời gian khả dụng và hệ thống không liên tục tạo thêm việc. Không thể yêu cầu một lần quét hữu hạn xử lý vô hạn công việc mới.

Một request bị từ chối không luôn có nghĩa mọi dữ liệu giữ nguyên. Với hợp đồng tự thu hồi khi phát hiện quá hạn, response lỗi nghiệp vụ đi kèm chuyển `HELD -> EXPIRED` đã commit. Mô hình phải thể hiện điều đó.

### Kiểm thử biến đổi đầu vào

Với chính sách cửa sổ tuyệt đối không phụ thuộc lịch, có thể dịch đồng thời `starts_at`, `ends_at` và `decision_at` cùng một khoảng; kết quả phải giữ nguyên nếu vẫn nằm trong miền thời gian hợp lệ.

Với hai chuỗi biểu diễn cùng instant nhưng khác offset, quyết định trên cửa sổ tuyệt đối phải giống nhau.

Không áp dụng máy móc những thuộc tính này cho ngày nghỉ, tháng theo lịch hoặc chính sách múi giờ. Dịch thêm 24 giờ có thể đi sang ngày nghiệp vụ khác.

Khi một chuỗi sinh ngẫu nhiên thất bại, lưu seed và chuỗi lệnh đã rút gọn để tái hiện. Một lỗi với ba bước “gia hạn → thông điệp cũ → xác nhận” dễ sửa hơn log hàng nghìn thao tác không có thứ tự rõ ràng.

## 16. Đánh giá sức mạnh của test bằng thay đổi có chủ đích

Có nhiều test chạy thành công chưa chắc bộ test phát hiện được lỗi quan trọng. Có thể thử thay đổi có chủ đích trong phạm vi kiểm thử hoặc dùng công cụ mutation testing phù hợp.

| Thay đổi sai giả định | Test nào cần thất bại? |
| --- | --- |
| Cho phép `decision_at == expires_at` | Test đúng tại hạn |
| Bỏ kiểm tra thời gian, chỉ giữ state | Test quá hạn khi worker chưa chạy |
| Đọc thời gian trước khóa | Test request chờ khóa qua hạn |
| Dùng thời gian bắt đầu transaction thay giờ sau khóa | Regression test transaction chạy lâu |
| Dùng `Instant.now()` trực tiếp thay nguồn đã truyền vào | Test điều khiển clock và kiểm tra nguồn |
| Tin `clientNow` hoặc `expiresAt` trong request | Test ranh giới tin cậy |
| Bỏ kiểm tra chủ sở hữu | Test ID của người hoặc tenant khác |
| Gia hạn từ `EXPIRED` | Test không hồi sinh |
| Mỗi retry renew lại cộng thời lượng | Test retry gia hạn |
| Luôn hoàn bộ đếm khi nhận thông điệp | Test thu hồi trùng |
| Tính ngày mới bằng 24 giờ cố định | Test ngày thay đổi giờ mùa hè |
| Tách ghi trạng thái và bộ đếm thành hai transaction | Test lỗi giữa hai lần ghi |
| Đánh giá lại thành công cũ bằng thời gian retry | Test mất response rồi retry sau hạn |

Không cần mọi thay đổi đều có một test riêng nếu một test tốt đã phát hiện được nhiều lỗi. Nhưng một thay đổi quan trọng không làm test nào thất bại là tín hiệu cần xem xét thiếu assertion, thiếu kịch bản hoặc expected chưa độc lập.

Các thay đổi này phục vụ đánh giá test trong môi trường phát triển; không đưa phiên bản cố ý sai vào hệ thống đang phục vụ người dùng.

## 17. Giữ bộ test ổn định và dễ chẩn đoán

Một số nguyên tắc vận hành:

- Dùng thời điểm cố định cho test chính sách; tránh phụ thuộc ngày chạy test.
- Mỗi test có dữ liệu, clock và namespace idempotency riêng.
- Chỉ dùng transaction thật khi cần chứng minh tích hợp hoặc đồng thời.
- Có timeout hữu hạn cho thread, truy vấn và barrier.
- Thu thập exception của worker phụ và dọn tài nguyên ngay cả khi assertion lỗi.
- Cố định cấu hình múi giờ của fixture; không dựa vào múi giờ máy CI.
- Với quy tắc lịch, quản lý phiên bản dữ liệu lịch/múi giờ mà môi trường dùng.
- Chạy test đồng thời theo các thứ tự có chủ đích trước khi bổ sung stress test.

Khi có test chập chờn, ghi lại timeline:

~~~text
request bắt đầu
transaction bắt đầu
bắt đầu chờ khóa
lấy đủ khóa
decision_at
trạng thái và hạn được đọc
kết quả ghi
commit hoặc rollback
kết quả consumer nếu có
~~~

Phân biệt thời gian đo cục bộ để chẩn đoán độ trễ với `decision_at` có thẩm quyền. Không sắp xếp tuyệt đối sự kiện từ nhiều máy chỉ bằng đồng hồ cục bộ có thể lệch.

Chạy lại một test lỗi có thể giúp chẩn đoán, nhưng “chạy lại thì xanh” không chứng minh lỗi đã được giải quyết. Cần xác định giả định sai: thiếu đồng bộ, dùng clock thật, chia sẻ state hay có một cuộc đua production.

Test chỉ tăng `sleep` thường che triệu chứng. Hướng sửa là chờ điều kiện quan sát được, điều khiển lịch thực thi hoặc chuyển phần chính sách sang clock có thể kiểm soát.

## 18. Tiêu chí hoàn tất kiểm thử quy tắc thời gian

Một bản ghi kết quả nên cho biết:

- Hợp đồng và phiên bản chính sách được kiểm tra.
- Nguồn thời gian, mốc quyết định và độ chính xác.
- Các mốc biên đã chạy.
- Những thứ tự đồng thời đã tạo.
- Các trường do người dùng kiểm soát đã thử sửa.
- Trạng thái và bất biến đã đối chiếu sau commit.
- Cơ chế retry, sự kiện muộn và phục hồi đã kiểm tra.
- Phạm vi còn chưa được kiểm chứng.

Ví dụ cách mô tả một kết quả, sau khi thực sự chạy test tương ứng:

~~~text
Kịch bản: xác nhận chờ khóa qua hạn
Hợp đồng: decision_at được đọc sau khi lấy đủ khóa
Dữ liệu: allocation HELD, units = 1, expires_at = T
Thứ tự: T1 giữ khóa; T2 chờ; nguồn thời gian qua T; T1 nhả khóa
Kỳ vọng: không có xác nhận mới sau hạn
Bằng chứng cần lưu: decision_at, trạng thái cuối, held/committed,
                   confirmation, outbox và kết quả transaction
~~~

Không báo “đã kiểm thử thời gian” chỉ vì unit test phép so sánh thành công. Mức bảo đảm phải tương ứng với bằng chứng: chính sách thuần, adapter thật, transaction, đồng thời hay toàn bộ đường vào.

Một bộ kiểm thử tốt phải phát hiện được cả sai toán tử biên lẫn sai quy trình: lấy giờ quá sớm, tin thời gian do khách gửi, hồi sinh trạng thái cuối, xử lý lặp tạo thêm quyền và cập nhật tài nguyên không nguyên tử.
