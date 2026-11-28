# Giới hạn giả định về thứ tự và độ chính xác đồng hồ

> **Mốc cập nhật: 27-11-2026.** Java SE 26 bổ sung `UUID.ofEpochMillis(long)` để tạo UUIDv7. API này là API ổn định (Since 26), không phải Preview hay Incubator. Khi dùng timestamp và UUIDv7, cần phân biệt độ chính xác biểu diễn, độ phân giải thực tế, độ đúng so với UTC và tính đơn điệu của đồng hồ. Timestamp mô tả thời điểm gần đúng; nó không tự tạo thứ tự nhân quả hoặc thứ tự toàn cục giữa các thread và máy chủ.

## 1. Mục tiêu

Ứng dụng thường ghi timestamp vào log, database, event và identifier. Một giả định dễ mắc phải là hai sự kiện có timestamp lớn hơn thì chắc chắn xảy ra sau nhau, hoặc timestamp có phần nanosecond thì đồng hồ thực sự đo chính xác đến nanosecond.

Các giả định đó không được bảo đảm.

Sau bài này, bạn có thể:

- Phân biệt wall clock và monotonic clock.
- Phân biệt precision, resolution, accuracy và monotonicity.
- Chọn đúng giữa `Instant`, `Clock`, `InstantSource`, `System.currentTimeMillis()` và `System.nanoTime()`.
- Hiểu vì sao hai event có thể có cùng timestamp hoặc timestamp bị lùi.
- Dùng UUIDv7 mới trong JDK 26 với `UUID.ofEpochMillis()`.
- Biết giới hạn thứ tự của UUIDv7 khi tạo nhiều ID trong cùng millisecond hoặc trên nhiều máy.
- Thiết kế sequence/offset riêng khi cần thứ tự tuyệt đối hoặc thứ tự nhân quả.
- Kiểm thử logic thời gian bằng clock injection thay vì phụ thuộc đồng hồ máy thật.

## 2. Bốn thuộc tính thời gian thường bị nhầm lẫn

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Precision (độ chính xác biểu diễn) | Giá trị có thể biểu diễn đến đơn vị nhỏ nhất nào? | `Instant` lưu nano-of-second. |
| Resolution / granularity (độ phân giải) | Bao lâu đồng hồ mới có thể trả về một giá trị khác? | `currentTimeMillis()` có thể chỉ đổi sau vài millisecond hoặc lâu hơn. |
| Accuracy (độ đúng so với thời gian tham chiếu) | Giá trị gần UTC hoặc nguồn thời gian chuẩn đến mức nào? | Đồng hồ VM có thể lệch so với NTP/PTP. |
| Monotonicity (tính đơn điệu) | Giá trị có luôn tăng hoặc không bao giờ lùi không? | Wall clock có thể lùi khi đồng bộ hoặc chỉnh giờ. |

### 2.1. Precision không đồng nghĩa với resolution

Một kiểu dữ liệu có thể lưu nanosecond nhưng nguồn thời gian chỉ cập nhật mỗi millisecond hoặc mỗi vài millisecond.

Ví dụ, `Instant` có trường nano-of-second từ 0 đến 999,999,999. Điều đó chỉ nói về khả năng biểu diễn của object. Nó không bảo đảm `Instant.now()` đọc được thời gian thật với độ phân giải 1 nanosecond.

Tương tự, `System.nanoTime()` trả về một số có đơn vị nanosecond và cung cấp nanosecond precision, nhưng Javadoc nói rõ điều đó không có nghĩa resolution cũng là một nanosecond.

### 2.2. Accuracy khác monotonicity

Một đồng hồ có thể chạy đơn điệu nhưng lệch UTC vài giây. Ngược lại, đồng hồ được đồng bộ gần UTC có thể bị điều chỉnh lùi hoặc tiến để sửa sai lệch.

Ví dụ:

- Host A nhanh hơn UTC 80 ms.
- Host B chậm hơn UTC 40 ms.
- Event thực tế xảy ra ở B trước, nhưng timestamp của A vẫn lớn hơn.

Đồng bộ thời gian giúp giảm sai lệch; nó không biến các đồng hồ độc lập thành một đồng hồ toàn cục hoàn hảo.

## 3. Wall clock và monotonic clock

### 3.1. Wall clock: thời gian trên lịch

Wall clock biểu diễn thời điểm theo một mốc thời gian chung, thường là Unix Epoch:

- `1970-01-01T00:00:00Z` là mốc Epoch.
- `System.currentTimeMillis()` trả số millisecond từ Epoch.
- `Instant.now()` trả một instant từ system clock.
- `Clock.systemUTC()` cung cấp wall-clock time theo UTC.

Wall clock phù hợp cho:

- Timestamp của log và event.
- Thời điểm tạo/cập nhật record.
- Thời hạn nghiệp vụ như ngày hết hạn.
- Hiển thị lịch sử hoạt động.
- Tạo UUIDv7 có thành phần thời gian.

Wall clock có thể nhảy tiến hoặc lùi khi hệ điều hành đồng bộ NTP, quản trị viên chỉnh giờ, VM được resume/migrate hoặc nguồn thời gian của máy thay đổi. Vì vậy, không dùng wall clock để đo thời lượng thực thi hoặc quyết định thứ tự nhân quả.

### 3.2. High-resolution source: đo thời lượng

`System.nanoTime()` cung cấp giá trị từ một nguồn thời gian có độ phân giải cao của JVM. Giá trị bắt đầu từ một origin tùy ý, không phải Unix Epoch và không liên quan đến thời gian lịch.

Dùng nó để đo khoảng thời gian:

~~~java
long start = System.nanoTime();

doWork();

long elapsedNanos = System.nanoTime() - start;
System.out.println("Elapsed: " + elapsedNanos + " ns");
~~~

Để kiểm tra timeout, so sánh hiệu giữa hai lần đọc:

~~~java
long start = System.nanoTime();
long timeoutNanos = 2_000_000_000L;

while (System.nanoTime() - start < timeoutNanos) {
    poll();
}
~~~

Cách tính `now - start` tránh lỗi overflow có thể gặp nếu cộng timeout vào mốc bắt đầu rồi so sánh hai giá trị tuyệt đối.

Không dùng giá trị tuyệt đối của `nanoTime()` để:

- Lưu timestamp vào database.
- So sánh thời điểm giữa hai JVM.
- Gửi sang máy khác.
- Chuyển thành `Instant`.
- Tạo ID cần giải mã thành thời gian UTC.

Origin của `nanoTime()` chỉ có ý nghĩa trong cùng một JVM instance; origin của JVM khác có thể khác.

### 3.3. Chọn API theo mục đích

| Nhu cầu | API nên dùng | Không nên dùng |
|---|---|---|
| Ghi thời điểm event | `Instant.now(clock)` | `System.nanoTime()` |
| Đo thời lượng, latency | `System.nanoTime()` | `Instant.now().toEpochMilli()` |
| Tạo UUIDv7 từ thời gian hiện tại | `UUID.ofEpochMillis(clock.millis())` | `nanoTime()` |
| Kiểm thử thời gian | `Clock.fixed(...)` hoặc `InstantSource.fixed(...)` | Chờ đồng hồ thật đến một thời điểm cụ thể |
| Thời gian lịch theo vùng | `ZonedDateTime` với `ZoneId` rõ ràng | `LocalDateTime` như một timestamp toàn cầu |
| Timeout trong cùng process | `nanoTime() - start` | So sánh `currentTimeMillis()` tuyệt đối |

## 4. System.currentTimeMillis() và System.nanoTime()

### 4.1. currentTimeMillis()

~~~java
long epochMillis = System.currentTimeMillis();
~~~

Giá trị là số millisecond kể từ `1970-01-01T00:00:00Z`.

Javadoc cảnh báo rằng dù đơn vị trả về là millisecond, granularity phụ thuộc hệ điều hành và có thể lớn hơn. Một số hệ điều hành có thể đo thời gian theo đơn vị hàng chục millisecond.

Vì vậy, hai lần gọi liên tiếp có thể trả cùng một số. Giá trị cũng có thể lùi nếu wall clock được điều chỉnh.

### 4.2. nanoTime()

~~~java
long tick = System.nanoTime();
~~~

Giá trị dùng cho elapsed time và có origin tùy ý. Javadoc quy định:

- Đơn vị trả về là nanosecond.
- Có nanosecond precision nhưng không bảo đảm nanosecond resolution.
- Giá trị tuyệt đối không phải timestamp.
- Chỉ hiệu giữa hai giá trị trong cùng JVM có ý nghĩa.
- Hiệu giữa hai lần đọc cách nhau hơn khoảng 292 năm có thể overflow `long`.

### 4.3. Ví dụ hai API không thể thay thế nhau

~~~java
import java.time.Instant;

public class ClockDifference {
    public static void main(String[] args) {
        long wallMillis = System.currentTimeMillis();
        long nanoTimeReading = System.nanoTime();

        Instant eventTime = Instant.ofEpochMilli(wallMillis);

        System.out.println("Event time: " + eventTime);
        System.out.println("nanoTime reading: " + nanoTimeReading);
    }
}
~~~

`eventTime` có thể lưu hoặc gửi sang hệ thống khác vì nó dựa trên Epoch. `nanoTimeReading` chỉ có ý nghĩa khi lấy hiệu với một lần đọc khác trong cùng JVM.

## 5. Instant có nanosecond nhưng đồng hồ không hứa nanosecond

`Instant` là một điểm trên timeline. Bên trong, nó lưu:

- `long` epoch-seconds.
- `int` nano-of-second trong khoảng 0 đến 999,999,999.

Ví dụ:

~~~java
Instant timestamp = Instant.parse("2026-11-27T10:15:30.123456789Z");

System.out.println(timestamp.getEpochSecond());
System.out.println(timestamp.getNano());
~~~

Giá trị trên biểu diễn được 9 chữ số phần thập phân. Nhưng nếu lấy thời gian bằng `Instant.now()`, độ phân giải và độ đúng phụ thuộc system clock.

Javadoc của `Instant` cũng nói implementation JSR-310 không bắt buộc cung cấp clock có độ đúng dưới một giây, hoặc clock chạy đơn điệu/mượt. Đây là lý do không được dùng số chữ số của timestamp để suy ra chất lượng đồng hồ.

### 5.1. Java Time-Scale và leap seconds

Java Time-Scale chia mỗi ngày thành đúng 86.400 giây. Trong giai đoạn dựa trên UTC, Java Time-Scale sử dụng UTC-SLS: nếu có leap second, phần điều chỉnh được trải đều trên 1.000 giây cuối ngày để giữ mỗi ngày có 86.400 giây theo mô hình Java.

Ứng dụng thông thường nên dùng `Instant` và `ZoneId` theo hợp đồng Java Time API, không tự cộng/trừ leap second bằng phép tính thủ công. Implementation của `Clock` không bắt buộc phải thực hiện chính xác UTC-SLS slew hoặc nhận biết leap second; cách xử lý phải được implementation tài liệu hóa.

## 6. Clock và InstantSource: tiêm nguồn thời gian vào ứng dụng

`Clock` và `InstantSource` là abstraction cho phép ứng dụng nhận nguồn thời gian từ bên ngoài. Đây là API ổn định từ các phiên bản Java trước, vẫn áp dụng trong JDK 26/27.

- Dùng `InstantSource` khi chỉ cần lấy instant.
- Dùng `Clock` khi cần cả instant và time-zone.
- Dùng `Clock.systemUTC()` cho timestamp không phụ thuộc múi giờ mặc định.
- Dùng `Clock.fixed()` cho kiểm thử.
- Dùng `Clock.offset()` để mô phỏng thời gian trong quá khứ/tương lai.
- Dùng `Clock.tick()` khi nghiệp vụ chủ động muốn cắt thời gian về một tick.

### 6.1. Inject Clock thay vì gọi Instant.now() khắp nơi

~~~java
import java.time.Clock;
import java.time.Instant;

final class AuditService {
    private final Clock clock;

    AuditService(Clock clock) {
        this.clock = clock;
    }

    Instant createdAt() {
        return Instant.now(clock);
    }
}
~~~

Khởi tạo production:

~~~java
AuditService service = new AuditService(Clock.systemUTC());
~~~

Kiểm thử với thời điểm cố định:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-27T08:00:00Z"),
        java.time.ZoneOffset.UTC
);

AuditService service = new AuditService(fixedClock);

if (!service.createdAt().equals(
        Instant.parse("2026-11-27T08:00:00Z"))) {
    throw new AssertionError("Unexpected event time");
}
~~~

Test không phụ thuộc thời gian thực, không phải sleep và không bị flaky khi chạy sát ranh giới ngày/tháng.

### 6.2. InstantSource khi không cần time-zone

~~~java
import java.time.Instant;
import java.time.InstantSource;

final class EventRecorder {
    private final InstantSource timeSource;

    EventRecorder(InstantSource timeSource) {
        this.timeSource = timeSource;
    }

    Instant recordTime() {
        return timeSource.instant();
    }
}
~~~

`InstantSource.system()` sử dụng system clock tốt nhất hiện có. Javadoc lưu ý implementation chuẩn dựa trên cùng underlying system clock với `System.currentTimeMillis()`, có thể có precision nhỏ hơn millisecond nếu nền tảng hỗ trợ, nhưng không bảo đảm nhiều về accuracy. Nếu nghiệp vụ cần nguồn thời gian chính xác hơn, ứng dụng phải tích hợp nguồn ngoài phù hợp, ví dụ time service dựa trên NTP.

### 6.3. Clock.tick() không tăng độ chính xác

~~~java
Clock secondClock = Clock.tickSeconds(ZoneOffset.UTC);
Clock millisecondClock = Clock.tickMillis(ZoneOffset.UTC);
~~~

`tickSeconds()` cắt phần nano và giây về tick nguyên giây. `tickMillis()` cắt về millisecond. Các implementation có thể cache tick; thời điểm bắt đầu một tick quan sát được có thể muộn hơn thời điểm đọc trực tiếp từ clock nền.

Dùng tick clock để chuẩn hóa timestamp theo yêu cầu nghiệp vụ hoặc giảm số mức thời gian hiển thị. Không dùng nó để tăng độ phân giải hoặc tạo thứ tự event.

## 7. Vì sao timestamp không bảo đảm thứ tự event?

### 7.1. Nhiều event có thể cùng timestamp

Nếu đồng hồ chỉ thay đổi mỗi millisecond, nhiều event trong cùng millisecond sẽ nhận cùng timestamp:

~~~text
Event A: 2026-11-27T10:15:30.123Z
Event B: 2026-11-27T10:15:30.123Z
Event C: 2026-11-27T10:15:30.123Z
~~~

Không thể suy ra A xảy ra trước B chỉ từ timestamp. Việc gọi `Instant.now()` nhiều lần không tự cấp một sequence number.

### 7.2. Timestamp có thể lùi

Ví dụ clock được chỉnh từ 10:15:31 về 10:15:29:

~~~text
Event A: 10:15:30.900Z
Event B: 10:15:29.200Z
~~~

Event B được xử lý sau A nhưng timestamp nhỏ hơn. Đây là điều có thể xảy ra với wall clock; code không được giả định thời gian luôn tăng.

### 7.3. Nhiều máy có clock skew

Hai node có nguồn thời gian riêng:

~~~text
Node A clock: +80 ms
Node B clock: -40 ms
~~~

Nếu event B xảy ra sau event A theo thời gian thực nhưng node B chậm hơn, timestamp B có thể nhỏ hơn timestamp A. Đồng bộ NTP/PTP giúp giảm clock skew, nhưng không tạo total order tuyệt đối.

### 7.4. Thứ tự thực thi khác thứ tự quan sát

Trong hệ thống concurrent, thread A có thể lấy timestamp trước rồi bị tạm dừng; thread B lấy timestamp sau nhưng hoàn tất ghi database trước. Timestamp ghi nhận lúc bắt đầu xử lý không nhất thiết phản ánh thứ tự commit hoặc thứ tự consumer nhìn thấy dữ liệu.

Cần xác định rõ ứng dụng muốn lưu loại thời gian nào:

- Event time: thời điểm sự kiện được cho là xảy ra.
- Processing time: thời điểm ứng dụng xử lý.
- Ingestion time: thời điểm hệ thống nhận dữ liệu.
- Commit/order sequence: thứ tự được hệ thống lưu trữ hoặc phân phối xác nhận.

Đừng dùng một trường `createdAt` để đại diện cho tất cả các khái niệm đó.

## 8. UUIDv7 trong Java 26

Java SE 26 bổ sung API:

~~~java
UUID id = UUID.ofEpochMillis(timestamp);
~~~

Phương thức `UUID.ofEpochMillis(long)` tạo UUID phiên bản 7 theo RFC 9562 từ Unix Epoch timestamp tính bằng millisecond. Đây là API Java SE ổn định, có từ JDK 26.

### 8.1. Cấu trúc UUIDv7

UUIDv7 có 128 bit:

| Thành phần | Số bit | Ý nghĩa |
|---|---:|---|
| Unix timestamp | 48 | Millisecond kể từ `1970-01-01T00:00:00Z`, leap seconds excluded. |
| Version | 4 | Giá trị 7. |
| Random A | 12 | Dữ liệu ngẫu nhiên hoặc phần bổ sung cho monotonicity theo RFC. |
| Variant | 2 | Variant RFC 9562. |
| Random B | 62 | Dữ liệu ngẫu nhiên hoặc counter theo thuật toán generator. |

Timestamp nằm ở 48 bit đầu, nên UUIDv7 có tính chất time-ordered ở độ phân giải millisecond. Điều này hữu ích cho index locality và truy vấn theo khoảng thời gian khi database lưu UUID theo thứ tự byte phù hợp.

### 8.2. Tạo UUIDv7 bằng API JDK 26

~~~java
import java.time.Clock;
import java.util.UUID;

public final class UuidV7Example {
    private UuidV7Example() {}

    public static UUID newId(Clock clock) {
        long epochMillis = clock.millis();
        return UUID.ofEpochMillis(epochMillis);
    }

    public static void main(String[] args) {
        UUID id = newId(Clock.systemUTC());

        System.out.println(id);
        System.out.println("version = " + id.version());
        System.out.println("variant = " + id.variant());
    }
}
~~~

Các đặc điểm của `UUID.ofEpochMillis()`:

- Nhận Unix Epoch millisecond.
- Đưa timestamp vào 48 bit đầu.
- Đặt version/variant theo UUIDv7.
- Dùng random data từ cryptographically strong pseudo-random number generator cho 74 bit còn lại.
- Từ chối timestamp âm hoặc lớn hơn `(1L << 48) - 1`.
- Có từ Java 26 (`Since: 26`).

Không cần bật `--enable-preview` để gọi API này.

### 8.3. UUIDv7 sắp xếp theo thời gian đến mức nào?

UUIDv7 giúp các ID được tạo ở các millisecond khác nhau có phần timestamp sắp theo thời gian. Nhưng `UUID.ofEpochMillis()` tạo phần còn lại bằng random data.

Nếu hai ID được tạo trong cùng một millisecond:

~~~text
ID A: timestamp = 1234567890000, random tail = ...
ID B: timestamp = 1234567890000, random tail = ...
~~~

Phần random tail không mã hóa thứ tự tạo. So sánh hai UUID cùng millisecond có thể cho thứ tự bất kỳ.

Nếu system clock lùi, timestamp truyền vào lần tạo sau có thể nhỏ hơn timestamp trước. Javadoc yêu cầu caller tự bảo đảm timestamp monotonic nếu cần các UUIDv7 sinh sau lớn hơn UUID trước.

Do đó:

- UUIDv7 có khả năng sắp xếp gần theo thời gian.
- UUIDv7 không mặc định là sequence tăng dần trong cùng millisecond.
- UUIDv7 không bảo đảm thứ tự nhân quả.
- UUIDv7 từ nhiều node không bảo đảm total order nếu clock skew.
- UUIDv7 không thay thế sequence/offset do database hoặc message broker cấp.

### 8.4. Lấy timestamp từ UUIDv7

`UUID.timestamp()` trong Java được định nghĩa cho UUIDv1. Gọi nó với UUIDv7 sẽ ném `UnsupportedOperationException`.

Nếu cần đọc 48-bit Unix millisecond timestamp từ UUIDv7, kiểm tra version và variant trước:

~~~java
import java.util.UUID;

static long uuidV7EpochMillis(UUID id) {
    if (id.version() != 7 || id.variant() != 2) {
        throw new IllegalArgumentException("Expected RFC UUIDv7");
    }

    return id.getMostSignificantBits() >>> 16;
}
~~~

Đây là cách giải mã dựa trên bit layout UUIDv7 của RFC 9562. API `UUID.timestamp()` không phải accessor của UUIDv7.

## 9. Monotonicity của UUIDv7 và giới hạn của JDK factory

RFC 9562 cho phép generator dùng phần bit còn lại của UUIDv7 theo một số cách:

- Random bits để tăng tính duy nhất.
- Counter được seed cẩn thận để tăng thứ tự trong cùng timestamp tick.
- Một phần sub-millisecond timestamp nếu nguồn thời gian có độ phân giải cao hơn.

Tuy nhiên, `UUID.ofEpochMillis()` của JDK 26/27 sử dụng random data cho phần 74 bit còn lại. Phương thức không nhận counter và không giữ trạng thái giữa các lần gọi.

Vì vậy, code sau tạo UUIDv7 hợp lệ nhưng không cam kết monotonic:

~~~java
UUID first = UUID.ofEpochMillis(System.currentTimeMillis());
UUID second = UUID.ofEpochMillis(System.currentTimeMillis());
~~~

Hai lần gọi có thể dùng cùng millisecond; random suffix quyết định phần còn lại. Nếu clock lùi, timestamp của ID thứ hai cũng có thể lùi.

### 9.1. Khi cần thứ tự trong một process

Nếu nghiệp vụ cần thứ tự tuyệt đối trong một process, lưu sequence riêng thay vì suy ra thứ tự từ UUID:

~~~java
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

record OrderedEvent(
        Instant occurredAt,
        long sequence,
        UUID id) {}

final class EventFactory {
    private final AtomicLong sequence = new AtomicLong();

    OrderedEvent create() {
        Instant now = Instant.now();
        long order = sequence.incrementAndGet();

        return new OrderedEvent(
                now,
                order,
                UUID.ofEpochMillis(now.toEpochMilli())
        );
    }
}
~~~

Trong ví dụ, `sequence` là thứ tự cấp phát trong phạm vi một instance `EventFactory`. Nó không phải thứ tự toàn cục và sẽ bắt đầu lại khi process tạo instance mới, trừ khi state được lưu/đồng bộ ở nơi khác.

### 9.2. Khi cần monotonic UUID timestamp trong một generator

Một generator có thể giữ timestamp cuối cùng và không cấp timestamp nhỏ hơn giá trị đã cấp:

~~~java
import java.time.Clock;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

final class LocalMonotonicUuidV7 {
    private final Clock clock;
    private final AtomicLong lastMillis = new AtomicLong(-1L);

    LocalMonotonicUuidV7(Clock clock) {
        this.clock = clock;
    }

    UUID next() {
        long wallMillis = clock.millis();

        long allocatedMillis = lastMillis.updateAndGet(previous ->
                Math.max(wallMillis, Math.addExact(previous, 1L))
        );

        return UUID.ofEpochMillis(allocatedMillis);
    }
}
~~~

Cách này bảo đảm timestamp được cấp tăng nghiêm ngặt trong cùng instance generator, kể cả khi wall clock đứng yên hoặc lùi. Tuy nhiên, mỗi UUID được tạo trong cùng một millisecond thực có thể đẩy timestamp cấp phát tiến thêm một millisecond. Nếu tốc độ tạo ID cao, timestamp nhân tạo sẽ chạy xa thời gian thực. Cách này chỉ minh họa một trade-off, không phải generator UUIDv7 tổng quát phù hợp mọi production workload.

Với hệ thống có throughput cao, cần monotonic UUIDv7 theo RFC, hãy dùng generator có cơ chế counter/monotonic random được thiết kế và kiểm thử riêng. Nếu chỉ cần thứ tự xử lý, sequence hoặc offset là cách rõ ràng hơn.

### 9.3. Thứ tự trên nhiều node

Một `AtomicLong` trong JVM không phối hợp với process khác. Hai node có thể:

- Cấp cùng timestamp millisecond.
- Có clock skew khác nhau.
- Restart và mất trạng thái sequence.
- Tạo ID theo thứ tự khác với thứ tự commit hoặc publish.

Nếu cần total order cho dữ liệu dùng chung, dùng cơ chế cấp thứ tự có thẩm quyền như:

- Database sequence hoặc commit log.
- Message broker partition offset.
- Một sequencer service.
- Logical clock hoặc Hybrid Logical Clock (HLC) khi bài toán phân tán cần kết hợp physical time và logical counter.

Các cơ chế logical clock/HLC cần implementation và protocol riêng; JDK không tự biến `Instant` hoặc UUIDv7 thành đồng hồ phân tán.

## 10. Chọn loại ID theo mục đích

| Loại ID | Đặc điểm | Trường hợp dùng |
|---|---|---|
| UUIDv4 | Random 128-bit theo cơ chế của JDK. | ID không cần sắp xếp theo thời gian; muốn tránh để lộ thời điểm tạo. |
| UUIDv7 | Timestamp millisecond ở đầu, phần còn lại random trong `UUID.ofEpochMillis()`. | ID có tính time-sortable gần đúng, thuận tiện cho index và truy vấn lịch sử. |
| Database sequence | Thứ tự cấp phát trong phạm vi database/sequence. | Cần thứ tự do database quản lý. |
| Message broker offset | Thứ tự record trong một partition. | Cần thứ tự tiêu thụ trong partition. |
| Logical sequence / HLC | Kết hợp logical counter với thông tin thời gian. | Cần so sánh quan hệ xảy ra trước trong hệ phân tán theo protocol cụ thể. |

UUIDv1 và UUIDv6 chủ yếu hữu ích khi cần tương thích hệ thống cũ. Với hệ thống mới không có yêu cầu tương thích UUIDv1, RFC 9562 khuyến nghị cân nhắc UUIDv7.

### 10.1. UUIDv7 có làm lộ thời gian không?

Có. Timestamp nằm trong 48 bit đầu, vì vậy người nhận UUIDv7 có thể suy ra millisecond tạo ID gần đúng.

Không dùng UUIDv7 như:

- Access token.
- Password reset token.
- Secret key.
- Bằng chứng xác thực quyền truy cập.
- Cơ chế chống replay độc lập.

Random tail giúp uniqueness, nhưng ID vẫn công khai phần thời gian. Nếu cần secret không đoán được để cấp quyền, dùng token ngẫu nhiên chuyên dụng và kiểm tra quyền ở server.

## 11. Time zone không phải clock accuracy

Các kiểu thời gian có mục đích khác nhau:

| Kiểu | Ý nghĩa |
|---|---|
| `Instant` | Một điểm trên timeline, không mang múi giờ. |
| `LocalDateTime` | Ngày/giờ địa phương, chưa xác định được instant nếu không có zone/offset. |
| `OffsetDateTime` | Ngày/giờ cùng UTC offset. |
| `ZonedDateTime` | Ngày/giờ theo quy tắc của `ZoneId`, bao gồm thay đổi DST. |
| `Duration` | Khoảng thời gian theo giây/nanosecond. |
| `Period` | Khoảng thời gian theo ngày/tháng/năm lịch. |

Ví dụ, `2026-11-27T09:00` không có zone chưa đủ để xác định một instant duy nhất. Nếu đó là giờ hẹn tại một địa điểm, lưu thêm `ZoneId` như `Asia/Ho_Chi_Minh` hoặc offset phù hợp.

Thay đổi time zone hoặc daylight saving time làm thay đổi cách hiển thị local date-time; nó không làm cho đồng hồ vật lý chính xác hơn hoặc làm event xảy ra sớm/muộn hơn.

## 12. Tránh overflow khi tính thời gian

Tính toán thời gian cần xét cả giới hạn số nguyên và giới hạn của `Instant`.

Với elapsed timeout, dùng phép trừ `nanoTime()`:

~~~java
long start = System.nanoTime();
long timeout = 5_000_000_000L;

if (System.nanoTime() - start >= timeout) {
    throw new IllegalStateException("Timed out");
}
~~~

Không viết:

~~~java
if (System.nanoTime() >= start + timeout) {
    // Có thể sai khi phép cộng overflow.
}
~~~

Với timestamp lịch, dùng `Instant` và `Duration` thay vì tự cộng số millisecond không kiểm soát:

~~~java
Instant deadline = Instant.now(clock).plus(Duration.ofMinutes(15));
~~~

Java 26 bổ sung `Instant.plusSaturating(Duration)`, trả về `Instant.MIN` hoặc `Instant.MAX` khi phép cộng vượt phạm vi biểu diễn thay vì ném lỗi do vượt giới hạn. Đây là xử lý overflow của phép toán, không làm clock chính xác hơn và cũng không bảo đảm timestamp monotonic.

## 13. Kiểm thử các tình huống clock bất thường

Đừng chỉ test với system clock chạy bình thường. Nên kiểm tra:

- Clock đứng yên: nhiều lần đọc cùng timestamp.
- Clock lùi: timestamp mới nhỏ hơn timestamp trước.
- Clock nhảy tiến: deadline có vẻ đã qua sớm hơn dự kiến.
- Nhiều event cùng millisecond.
- Hai node có clock offset khác nhau.
- Test qua ranh giới ngày, tháng, năm và daylight saving time.
- UUIDv7 timestamp âm hoặc vượt 48-bit range.
- UUIDv7 nhiều lần cùng timestamp.
- Sequence reset sau process restart.

Ví dụ test clock lùi bằng `Clock` tùy biến:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

final class ScriptedClock extends Clock {
    private final List<Instant> instants;
    private final ZoneId zone;
    private final AtomicInteger index = new AtomicInteger();

    ScriptedClock(List<Instant> instants) {
        this(instants, ZoneId.of("UTC"));
    }

    private ScriptedClock(List<Instant> instants, ZoneId zone) {
        if (instants.isEmpty()) {
            throw new IllegalArgumentException("At least one instant is required");
        }
        this.instants = List.copyOf(instants);
        this.zone = zone;
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return new ScriptedClock(instants, zone);
    }

    @Override
    public Instant instant() {
        int current = Math.min(index.getAndIncrement(), instants.size() - 1);
        return instants.get(current);
    }
}
~~~

Dùng clock này để kiểm tra code không giả định timestamp luôn tăng:

~~~java
Clock scripted = new ScriptedClock(List.of(
        Instant.parse("2026-11-27T10:00:01Z"),
        Instant.parse("2026-11-27T10:00:00Z")
));

Instant first = Instant.now(scripted);
Instant second = Instant.now(scripted);

if (!second.isBefore(first)) {
    throw new AssertionError("Test clock did not move backward");
}
~~~

Trong unit test, `Clock.fixed()` thường đủ. Custom clock hữu ích khi cần mô phỏng nhiều lần đọc với thời gian tăng, đứng yên hoặc lùi.

## 14. Những giả định cần tránh

| Giả định sai | Thực tế |
|---|---|
| `Instant` có nano nên `Instant.now()` chính xác đến nano. | Object lưu nano; system clock có thể có resolution thô hơn và accuracy không được bảo đảm. |
| `currentTimeMillis()` luôn tăng. | Wall clock có thể đứng yên hoặc lùi. |
| `nanoTime()` là Unix timestamp. | Origin tùy ý trong JVM, chỉ dùng hiệu để đo elapsed time. |
| `nanoTime()` có nanosecond precision nghĩa là resolution 1 ns. | Javadoc phân biệt rõ precision và resolution. |
| Timestamp lớn hơn luôn có nghĩa event xảy ra sau. | Clock skew, adjustment và concurrency có thể đảo thứ tự quan sát. |
| UUIDv7 luôn tăng ở mỗi lần gọi `UUID.ofEpochMillis()`. | Timestamp do caller cung cấp; random tail không tạo sequence trong cùng millisecond. |
| UUIDv7 từ nhiều máy tạo total order. | Clock của các node có thể lệch nhau. |
| UUIDv7 là secret token. | Timestamp công khai; ID không thay thế cơ chế authorization. |
| `UUID.timestamp()` đọc được timestamp UUIDv7. | Phương thức đó chỉ dành cho UUIDv1. |
| `Clock.tickMillis()` tạo đồng hồ chính xác hơn. | Nó cắt giá trị về millisecond và có thể cache. |
| Đồng bộ NTP tạo một đồng hồ toàn cục tuyệt đối. | Đồng bộ làm giảm skew, vẫn còn sai số và độ trễ. |

## 15. Bài tập thực hành

1. Ghi 10.000 giá trị `System.currentTimeMillis()` liên tiếp; đếm số giá trị trùng nhau.
2. Ghi 10.000 giá trị `System.nanoTime()`; quan sát bước thay đổi, không giả định mỗi bước là 1 ns.
3. Đo thời lượng một đoạn code bằng `nanoTime()` và so sánh với cách lấy hai `Instant`.
4. Inject `Clock.systemUTC()` vào service và thay bằng `Clock.fixed()` trong test.
5. Dùng custom clock trả về thời gian lùi để kiểm tra logic expiration và ordering.
6. Tạo UUIDv7 bằng `UUID.ofEpochMillis(Instant.now().toEpochMilli())`; kiểm tra `version()` và `variant()`.
7. Tạo nhiều UUIDv7 trong cùng millisecond; xác nhận timestamp giống nhau nhưng thứ tự phần random không đại diện cho thứ tự tạo.
8. Đọc timestamp UUIDv7 từ 48 bit đầu và so sánh với giá trị đầu vào.
9. Gọi `UUID.timestamp()` với UUIDv7; quan sát `UnsupportedOperationException`.
10. Thử timestamp âm và timestamp lớn hơn `(1L << 48) - 1`; xác nhận `IllegalArgumentException`.
11. Tạo hai clock giả lập hai node có offset khác nhau; mô phỏng event xảy ra trước nhưng timestamp lớn hơn.
12. Thiết kế record event có `occurredAt`, `sequence` và `id`; giải thích mỗi field giải quyết loại thứ tự nào.
13. So sánh UUIDv4 và UUIDv7 về khả năng sort, tính lộ thời gian và mục đích sử dụng.
14. Đo elapsed timeout bằng `nanoTime()` trong khi thay đổi wall clock của test clock; xác nhận timeout không phụ thuộc wall clock.
15. Viết quy tắc chọn `Instant`, `ZonedDateTime`, `Clock`, `nanoTime` và UUIDv7 cho một service thực tế.

Bảng ghi kết quả:

| Thử nghiệm | Điều cần quan sát | Kết luận |
|---|---|---|
| `currentTimeMillis()` lặp nhanh | Timestamp trùng | Millisecond không bảo đảm unique. |
| `nanoTime()` lặp nhanh | Bước thay đổi thực tế | Precision khác resolution. |
| Clock lùi | Instant giảm | Wall clock không monotonic. |
| Hai node lệch clock | Timestamp đảo thứ tự | Không có total order toàn cục. |
| UUIDv7 cùng millisecond | Random tail khác nhau | Không đảm bảo thứ tự trong tick. |
| UUIDv7 với timestamp monotonic | Timestamp field tăng | Caller chịu trách nhiệm monotonicity. |
| Sequence tăng | Thứ tự cấp phát trong phạm vi sequence | Dùng sequence khi cần thứ tự xác định. |

## 16. Checklist trước khi thiết kế

- [ ] Đã xác định cần event time, processing time, ingestion time hay elapsed duration.
- [ ] Dùng `Instant` cho timestamp trên timeline.
- [ ] Dùng `Clock`/`InstantSource` để inject nguồn thời gian và test.
- [ ] Dùng `System.nanoTime()` để đo elapsed time trong cùng JVM.
- [ ] Không so sánh `nanoTime()` tuyệt đối giữa JVM hoặc máy khác nhau.
- [ ] Không suy ra accuracy/resolution từ số chữ số nano của `Instant`.
- [ ] Đã chấp nhận khả năng wall clock đứng yên hoặc lùi.
- [ ] Không suy ra causal order chỉ từ timestamp.
- [ ] Dùng sequence, broker offset hoặc logical clock khi cần thứ tự xác định.
- [ ] Dùng UUIDv7 JDK 26+ khi cần ID time-sortable ở độ phân giải millisecond.
- [ ] Không giả định `UUID.ofEpochMillis()` tự sinh monotonic sequence.
- [ ] Đã xem xét clock skew và timestamp leakage khi dùng UUIDv7.
- [ ] Không dùng UUID làm secret hoặc access token.
- [ ] Đã kiểm thử clock lùi, clock đứng yên, timestamp trùng và nhiều node.

## Tài liệu tham khảo chính thức

- [JDK 26 Release Notes — UUIDv7 support](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
- [UUID API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/UUID.html)
- [UUID API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/UUID.html)
- [System API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html)
- [Instant API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html)
- [Clock API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html)
- [InstantSource API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/InstantSource.html)
- [RFC 9562: Universally Unique IDentifiers (UUIDs), Sections 5.7 and 6](https://www.rfc-editor.org/rfc/rfc9562.html)

