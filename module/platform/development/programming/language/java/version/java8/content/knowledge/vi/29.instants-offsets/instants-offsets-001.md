# Instant và điểm trên trục thời gian trong Java

**Chủ đề:** Java 8 → Instant và offset → Instant và điểm trên trục thời gian.

**java.time.Instant** là kiểu biểu diễn **một thời điểm xác định trên trục thời gian** (timeline). Một Instant phù hợp để ghi thời điểm sự kiện xảy ra, thời điểm tạo bản ghi, dấu thời gian (timestamp), thời điểm hết hạn và các mốc cần so sánh độc lập với vị trí địa lý của người dùng.

Điểm cần nhớ: **Instant không lưu giờ địa phương, ngày của người dùng, múi giờ vùng (ZoneId) hay offset như những thuộc tính của bản thân nó**. Nó biểu diễn vị trí trên một time-line chuẩn. Muốn hiển thị **năm/tháng/ngày/giờ ở Hà Nội, Tokyo hoặc New York**, hãy **kết hợp Instant với ZoneId hoặc ZoneOffset** để chuyển thành kiểu ngày giờ tương ứng.

**Instant có từ Java 8 và vẫn là API hiện đại.** Các ví dụ độc lập trong bài chạy trên **Java 17+**; những cú pháp phụ trợ như **record** và **List.of(...)** được ghi rõ khi sử dụng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **Instant là một điểm trên timeline**, không phải ngày hoặc giờ địa phương.
2. Phân biệt **Instant**, **LocalDate**, **LocalDateTime**, **OffsetDateTime**, **ZonedDateTime** và **Duration**.
3. Tạo Instant bằng **now()**, **now(Clock)**, **parse(...)**, **ofEpochSecond(...)** và **ofEpochMilli(...)**.
4. Hiểu Java epoch, giá trị âm trước epoch và hai thành phần **epoch-seconds/nanoseconds**.
5. Đọc, so sánh, cộng trừ, cắt độ chính xác và tính thời gian giữa hai Instant.
6. Chuyển cùng một Instant sang các ngày giờ tại nhiều ZoneId, và chuyển một ngày-giờ địa phương hợp lệ trở lại Instant.
7. Tránh nhầm **giây với mili-giây**, nhầm **nanosecond precision** với độ chính xác của đồng hồ hệ điều hành hoặc timestamp database.
8. Dùng **Clock.fixed(...)** để viết test có thể lặp lại, và mô hình hóa khoảng thời gian **[startInclusive, endExclusive)**.
9. Hiểu tại sao **cộng 86.400 giây** không luôn tương đương **sang ngày lịch kế tiếp ở một múi giờ có DST**.
10. Chọn kiểu dữ liệu hợp lý cho API, lưu trữ, audit và nghiệp vụ.

## 2. Instant là một thời điểm, không phải ngày giờ hiển thị

Hình dung một timeline chung cho các hệ thống:

~~~text
Một trục thời gian
───────────●──────────────────────────────────────────────►
           │
           └── Instant: 2026-01-01T23:30:00Z

Cùng điểm trên timeline:
UTC                  2026-01-01 23:30
Asia/Ho_Chi_Minh     2026-01-02 06:30 (+07:00)
America/New_York     2026-01-01 18:30 (-05:00, mùa đông 2026)

Ba cách hiển thị, một thời điểm.
~~~

**2026-01-01T23:30:00Z** là cách biểu diễn ISO-8601 của một Instant. Chữ **Z** biểu thị **zero offset** trong cách hiển thị UTC. Chữ Z ở đây không có nghĩa Instant lưu thêm một ZoneId tên "UTC"; giá trị Instant biểu diễn điểm trên timeline.

Đối với một sự kiện như **yêu cầu thanh toán hoàn tất**, dữ liệu cần ghi thường là **thời điểm thật xảy ra**. Nếu chỉ lưu **LocalDateTime 2026-01-02T06:30**, không có thông tin zone/offset, ta **không thể** xác định chắc chắn đó là một Instant cụ thể.

### 2.1. Các kiểu java.time dùng cho những ý nghĩa khác nhau

| Kiểu | Dữ liệu mà nó mang | Ví dụ nhu cầu |
|---|---|---|
| **Instant** | Điểm trên timeline | Log, audit, createdAt, expiresAt |
| **LocalDate** | Ngày lịch ISO, không có giờ/zone | Ngày sinh, ngày hóa đơn |
| **LocalTime** | Giờ trong ngày, không có ngày/zone | Giờ mở cửa |
| **LocalDateTime** | Ngày và giờ địa phương, không có zone | Giờ lịch hẹn khi zone được quản lý riêng |
| **OffsetDateTime** | Ngày giờ với **UTC offset** | Giao tiếp dữ liệu ngày giờ kèm độ lệch |
| **ZonedDateTime** | Ngày giờ với **ZoneId và quy tắc zone** | Lịch hẹn tại một địa điểm có DST |
| **Duration** | Khoảng thời gian dựa trên giây và nano | Timeout 90 giây, chênh lệch giữa hai Instant |
| **Period** | Khoảng lịch theo năm/tháng/ngày | Gia hạn một tháng lịch |

**Không dùng kiểu phức tạp hơn khi nghiệp vụ chỉ cần loại đơn giản.** Ví dụ một **ngày sinh** không có một timestamp duy nhất; chọn LocalDate. Một **request được nhận lúc nào** cần điểm trên timeline; chọn Instant.

### 2.2. Instant thuộc miền thời gian UTC nhưng không mang timezone

Cách nói **"Instant là timestamp UTC"** thường hữu ích ở cấp ứng dụng, nhưng cần phân biệt:

- **Instant là một giá trị trên timeline**, có thể biểu diễn và serialize theo chuẩn UTC.
- **atZone(zone)** và **atOffset(offset)** là thao tác **xem cùng một Instant dưới một hệ tọa độ ngày giờ**.
- Instant **không ghi nhớ** nó được tạo từ New York, Hà Nội hay một zone khác.
- Đổi ZoneId khi hiển thị không làm thay đổi Instant gốc.

**Không tự lấy ngày trong chuỗi Instant UTC rồi dùng làm ngày địa phương của người dùng.** Ở ranh giới ngày, hai giá trị có thể khác nhau.

## 3. Mốc epoch: 1970-01-01T00:00:00Z

Java dùng **epoch** tại:

~~~text
1970-01-01T00:00:00Z
       epoch-second = 0
~~~

Một Instant có thể được mô tả bởi:

1. **epochSecond** — số giây nguyên **long** tính từ epoch; trước epoch là giá trị âm.
2. **nanoOfSecond** — phần nano của **giây hiện tại**, là số **int** trong khoảng **0..999_999_999**.

**Instant.ofEpochSecond(1, 250_000_000)** là thời điểm **1,25 giây sau epoch**. Nó không có gì liên quan đến ngày 1/1 theo múi giờ người dùng, trừ khi ta chọn một zone để chuyển đổi.

### 3.1. Những factory thông dụng

~~~java
Instant epoch = Instant.EPOCH;

Instant oneSecond =
        Instant.ofEpochSecond(1);

Instant oneAndQuarter =
        Instant.ofEpochSecond(1, 250_000_000);

Instant fromMillis =
        Instant.ofEpochMilli(1_250);

Instant parsed =
        Instant.parse("1970-01-01T00:00:01.250Z");
~~~

Đây là **đoạn minh họa**, cần import **java.time.Instant**.

**oneAndQuarter**, **fromMillis** và **parsed** cùng biểu diễn một điểm trên timeline. **Instant.EPOCH** có giá trị cố định bằng epoch, không phải Instant.now().

**Phân biệt đơn vị:** **ofEpochSecond(...)** nhận **giây**; **ofEpochMilli(...)** nhận **mili-giây**. Nếu API gửi số epoch dưới dạng long không có chú thích đơn vị, rất dễ đọc sai timestamp.

### 3.2. Một giây bằng bao nhiêu nano?

~~~text
1 second      = 1_000 milliseconds
1 second      = 1_000_000 microseconds
1 second      = 1_000_000_000 nanoseconds

250_000_000 ns = 250 ms = 0,25 s
~~~

**Instant lưu phần nano-of-second, không chỉ mili-giây**. Nhưng điều này **không đảm bảo đồng hồ dùng để tạo Instant có độ chính xác nano**. Độ phân giải đồng hồ thực tế phụ thuộc JDK, OS, hardware và nguồn dữ liệu; khi đưa qua database/API, độ chính xác có thể còn bị giới hạn.

### 3.3. Hai thành phần là biểu diễn chuẩn hóa

~~~java
Instant a = Instant.ofEpochSecond(1, 250_000_000);
Instant b = Instant.ofEpochSecond(0, 1_250_000_000);

// a.equals(b) == true
// a.getEpochSecond() == 1
// a.getNano() == 250_000_000
~~~

Đoạn này minh họa overload **ofEpochSecond(long, long)**: tham số **nanoAdjustment** có thể vượt 1 tỷ hoặc âm; factory sẽ chuẩn hóa để phần nano lưu trữ nằm trong **0..999_999_999**.

**Không** kết luận rằng **getNano()** trả tổng số nano từ epoch. Nó chỉ trả **phần lẻ trong một giây** của Instant.

## 4. Chương trình đầy đủ: epoch seconds và nano

Lưu thành **InstantBasicsDemo.java**:

~~~java
import java.time.Instant;

public class InstantBasicsDemo {
    public static void main(String[] args) {
        Instant epoch = Instant.EPOCH;
        Instant instant =
                Instant.ofEpochSecond(1, 250_000_000);

        System.out.println("epoch=" + epoch);
        System.out.println("instant=" + instant);
        System.out.println("seconds=" + instant.getEpochSecond());
        System.out.println("nanos=" + instant.getNano());
        System.out.println("millis=" + instant.toEpochMilli());
        System.out.println("sameAsMillis="
                + instant.equals(Instant.ofEpochMilli(1250)));

        Instant adjusted =
                instant.plusSeconds(90).minusMillis(250);

        System.out.println("adjusted=" + adjusted);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstantBasicsDemo.java
java InstantBasicsDemo
~~~

**Stdout:**

~~~text
epoch=1970-01-01T00:00:00Z
instant=1970-01-01T00:00:01.250Z
seconds=1
nanos=250000000
millis=1250
sameAsMillis=true
adjusted=1970-01-01T00:01:31Z
~~~

**Diễn giải:**

- **getEpochSecond()** trả 1 vì Instant nằm 1,25 giây sau epoch.
- **getNano()** trả 250 triệu nano vì đó là phần 0,25 giây.
- **toEpochMilli()** trả 1.250 mili-giây.
- **equals(...)** kiểm tra giá trị timeline và xác nhận hai cách tạo ra cùng Instant.
- **plusSeconds(90).minusMillis(250)** tạo Instant mới ở **91 giây sau epoch**. Không thay đổi đối tượng instant ban đầu.

## 5. Thời điểm trước epoch và giá trị âm

Instant không bị giới hạn vào những thời điểm sau năm 1970. Ví dụ:

~~~java
Instant before = Instant.ofEpochSecond(-1);
// 1969-12-31T23:59:59Z
~~~

**Trường hợp dễ sai:** một thời điểm **1 nanosecond trước epoch**:

~~~java
Instant justBefore =
        Instant.ofEpochSecond(-1, 999_999_999);

// toString(): 1969-12-31T23:59:59.999999999Z
// getEpochSecond(): -1
// getNano(): 999_999_999
// toEpochMilli(): -1
~~~

Các trường ở trên **không mâu thuẫn**. Giá trị biểu diễn chuẩn hóa của Instant trước epoch dùng **epochSecond âm** và **nanoOfSecond không âm**.

### 5.1. Vì sao chuyển epoch milliseconds âm cần cẩn thận?

Nếu bạn tự chuyển một số mili-giây âm thành epochSecond/nano bằng phép chia và số dư theo kiểu Java mà không xem xét phép làm tròn, bạn có thể xây một cặp số không chuẩn hóa hoặc xử lý sai thời điểm. **Ưu tiên Instant.ofEpochMilli(millis)**.

Khi cần chuyển ngược:

~~~java
long millis = instant.toEpochMilli();
~~~

Phương thức này có thể **mất phần nano nhỏ hơn 1ms**; với thời điểm ngay trước epoch, kết quả có thể là **-1** mili-giây vì giá trị bị đưa về millisecond trên trục thời gian. **Không tự viết công thức chỉ lấy getEpochSecond()*1000** nếu cần xét phần nano.

### 5.2. Ví dụ độc lập cho timestamp âm

Lưu thành **InstantNegativeEpochDemo.java**:

~~~java
import java.time.Instant;

public class InstantNegativeEpochDemo {
    public static void main(String[] args) {
        Instant before =
                Instant.ofEpochSecond(-1, 999_999_999);

        System.out.println("instant=" + before);
        System.out.println("seconds=" + before.getEpochSecond());
        System.out.println("nanos=" + before.getNano());
        System.out.println("millis=" + before.toEpochMilli());

        System.out.println("minusOneMilli="
                + Instant.ofEpochMilli(-1));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstantNegativeEpochDemo.java
java InstantNegativeEpochDemo
~~~

**Stdout:**

~~~text
instant=1969-12-31T23:59:59.999999999Z
seconds=-1
nanos=999999999
millis=-1
minusOneMilli=1969-12-31T23:59:59.999Z
~~~

**Phân biệt hai Instant:** thời điểm **-1 nano** và **-1 milli** không bằng nhau, dù phép **toEpochMilli()** của cả hai có thể là -1. Không bao giờ sử dụng một timestamp chỉ có mili-giây để kết luận hai Instant khác nhau ở mức nano là cùng thời điểm.

## 6. Lấy Instant hiện tại với Clock

Cách thông dụng:

~~~java
Instant now = Instant.now();
~~~

**Instant.now()** đọc nguồn thời gian của hệ thống. Nó trả một điểm trên timeline chứ **không cần biết timezone mặc định của người dùng** để biểu diễn giá trị. Dù người dùng ở đâu, cùng một Instant có thể hiển thị khác nhau khi kết hợp ZoneId.

**Tuy nhiên**, giá trị now() thay đổi theo lúc gọi. Đừng dùng đầu ra mẫu cố định cho **Instant.now()**, và đừng viết unit test yêu cầu nó đúng một timestamp cụ thể.

### 6.1. now(Clock): tiêm nguồn thời gian cho test

**Instant.now(Clock)** nhận đồng hồ do ứng dụng cung cấp; **Clock.fixed(...)** giúp cố định thời gian.

Lưu thành **InstantClockDemo.java**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;

public class InstantClockDemo {
    public static void main(String[] args) {
        Instant fixedTime =
                Instant.parse("2026-01-01T23:30:00Z");

        Clock clock = Clock.fixed(
                fixedTime,
                ZoneId.of("Asia/Ho_Chi_Minh")
        );

        System.out.println("instant=" + Instant.now(clock));
        System.out.println("zone=" + clock.getZone());
        System.out.println("again=" + Instant.now(clock));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstantClockDemo.java
java InstantClockDemo
~~~

**Stdout:**

~~~text
instant=2026-01-01T23:30:00Z
zone=Asia/Ho_Chi_Minh
again=2026-01-01T23:30:00Z
~~~

Điểm quan trọng:

- **Clock.fixed** luôn trả cùng một Instant.
- **Clock** có một ZoneId để phục vụ các phép chuyển đổi ngày giờ khác, nhưng **Instant.now(clock) vẫn trả Instant**, không mang region zone vào đối tượng kết quả.
- Clock.fixed rất hữu ích khi kiểm thử **createdAt**, **expiresAt** và các điều kiện hết hạn.
- **LocalDate.now(clock)** sẽ dùng zone của clock để xác định **ngày địa phương**; đó là phép tính khác với **Instant.now(clock)**.

### 6.2. Thiết kế dịch vụ có thể kiểm thử

Một service tạo dấu thời gian thường nên nhận Clock qua constructor:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public class EventTimeService {
    private final Clock clock;

    public EventTimeService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Instant createdAt() {
        return Instant.now(clock);
    }
}
~~~

Đây là **class có thể biên dịch độc lập**, nhưng không có **main(...)** nên không thể chạy trực tiếp bằng **java EventTimeService**. Trong production có thể truyền **Clock.systemUTC()**; trong test truyền **Clock.fixed(...)**. Không để unit test phụ thuộc đồng hồ máy chạy test.

**Không sử dụng Clock.fixed để giả lập một hệ thống thời gian thực có thay đổi**, trừ khi đó chính là mục tiêu kiểm thử. Khi cần đồng hồ tiến dần có kiểm soát, có thể tạo abstraction test clock thích hợp.

## 7. Immutable, thread-safe và so sánh theo giá trị

**Instant là immutable và value-based**:

~~~java
Instant original = Instant.parse("2026-01-01T00:00:00Z");

Instant next = original.plusSeconds(60);

// original vẫn là 2026-01-01T00:00:00Z
// next là 2026-01-01T00:01:00Z
~~~

Một lời gọi **plusSeconds()** không sửa Instant cũ; nó trả một Instant mới. Nếu muốn cập nhật **biến**, phải gán lại:

~~~java
deadline = deadline.plusSeconds(60);
~~~

**Không dùng == để so sánh hai Instant theo timeline**, cũng không dùng instance Instant làm monitor lock với **synchronized(instant)**. Dùng:

- **a.equals(b)**: cùng điểm trên timeline.
- **a.isBefore(b)**: a đứng trước b.
- **a.isAfter(b)**: a đứng sau b.
- **a.compareTo(b)**: số âm, 0, dương theo thứ tự timeline.

**compareTo** của Instant nhất quán với **equals**. Không cần tự so sánh riêng epoch-second và nano để viết một comparator cho Instant.

### 7.1. Phân biệt thứ tự và độ chính xác

Hai Instant có thể khác nhau chỉ **một nano**, nhưng nếu đưa chúng qua API chỉ lưu mili-giây thì hai giá trị có thể trùng nhau sau khi convert. Khi ứng dụng yêu cầu **thứ tự tuyệt đối của sự kiện**, chỉ dựa vào timestamp có cùng giá trị không phải bằng chứng về thứ tự xảy ra trong hệ thống phân tán; có thể cần **sequence number**, log offset hoặc đồng hồ logic tùy bài toán.

**Instant là mô hình thời điểm tốt**, nhưng không tự cung cấp đồng hồ toàn cục hoàn hảo giữa nhiều máy hoặc thứ tự nhân quả của mọi sự kiện.

## 8. Parse và serialize timestamp

**Instant.parse(text)** sử dụng formatter ISO_INSTANT. Các timestamp ISO có chỉ định offset hợp lệ có thể được quy đổi về cùng một Instant.

~~~java
Instant a = Instant.parse("2026-01-01T23:30:00Z");
Instant b = Instant.parse("2026-01-02T06:30:00+07:00");

// a.equals(b) == true
~~~

Cả hai cách viết trỏ tới cùng điểm thời gian. **Instant.toString()** biểu diễn theo dạng ISO UTC với chữ **Z**, và phần giây lẻ được định dạng theo độ chính xác cần biểu diễn; **không nhất thiết luôn có đúng ba chữ số millisecond**.

### 8.1. Parse không đoán timezone cho một ngày giờ không offset

~~~java
// Không đủ thông tin để parse trực tiếp thành Instant:
Instant.parse("2026-01-02T06:30:00");
~~~

Dữ liệu chỉ có ngày giờ địa phương; thiếu offset/zone nên không xác định được một Instant duy nhất. **Instant.parse(...)** sẽ ném **DateTimeParseException** cho trường hợp này.

**Cách đúng:** nếu đầu vào có ngày giờ cục bộ và một ZoneId được quy định, trước hết parse thành LocalDateTime, sau đó kết hợp zone:

~~~java
LocalDateTime local =
        LocalDateTime.parse("2026-01-02T06:30:00");

Instant event =
        local.atZone(
                ZoneId.of("Asia/Ho_Chi_Minh"))
                .toInstant();
~~~

Đây là **đoạn minh họa**, cần import **LocalDateTime, ZoneId, Instant**. **atZone(...)** phải giải quyết những trường hợp giờ địa phương không tồn tại hoặc lặp lại theo DST; hành vi mặc định của nó có quy tắc cụ thể. Với nghiệp vụ nhạy cảm, hãy xác thực chính sách xử lý gap/overlap thay vì tự giả định mọi giờ địa phương ánh xạ 1–1 sang một Instant.

### 8.2. Định dạng output chính xác theo hệ thống

Ở ranh giới REST/JSON, nếu trường mang ý nghĩa timestamp, ví dụ JSON:

~~~json
{
  "createdAt": "2026-01-01T23:30:00Z",
  "expiresAt": "2026-01-02T00:00:00Z"
}
~~~

Cần phân biệt **date-only field** và **timestamp field** trong schema. Thư viện JSON/ORM phải được cấu hình để giữ đúng semantics và precision của Instant; không cho rằng mọi serializer tự động giữ đủ 9 chữ số nano.

**Không gửi LocalDate như một Instant tại UTC midnight** chỉ để làm kiểu dữ liệu đồng nhất. Điều đó có thể gây lệch ngày khi user ở vùng có offset âm.

## 9. Chuyển Instant sang ZoneId hoặc ZoneOffset

Các phương thức phổ biến:

~~~java
ZonedDateTime byZone = instant.atZone(
        ZoneId.of("Asia/Ho_Chi_Minh"));

OffsetDateTime byOffset = instant.atOffset(
        ZoneOffset.ofHours(7));
~~~

Đây là **đoạn minh họa**, giả sử instant là Instant đã tạo, import **ZonedDateTime**, **OffsetDateTime**, **ZoneId**, **ZoneOffset**.

**Khác nhau:**

- **ZoneOffset** là độ lệch từ UTC, ví dụ **+07:00**, không mang lịch sử/quy tắc vùng.
- **ZoneId** như **America/New_York** hoặc **Asia/Ho_Chi_Minh** có thể được JDK liên kết với **quy tắc múi giờ** và lịch sử DST.
- **Instant.atZone(zone)** tạo **ZonedDateTime** biểu diễn cùng Instant theo zone vùng.
- **Instant.atOffset(offset)** tạo **OffsetDateTime** với cùng Instant ở offset đã chọn.
- **Đổi zone không dịch chuyển sự kiện sang thời điểm mới**; chỉ thay cách biểu diễn ngày/giờ địa phương.

### 9.1. Chương trình hoàn chỉnh: cùng một Instant, hai ngày lịch

Lưu thành **InstantZoneDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;

public class InstantZoneDemo {
    public static void main(String[] args) {
        Instant event =
                Instant.parse("2026-01-01T23:30:00Z");

        LocalDate utcDate =
                event.atZone(ZoneOffset.UTC).toLocalDate();

        LocalDate vietnamDate =
                event.atZone(
                        ZoneId.of("Asia/Ho_Chi_Minh"))
                        .toLocalDate();

        System.out.println("utcDate=" + utcDate);
        System.out.println("vietnamDate=" + vietnamDate);

        System.out.println("vietnamTime="
                + event.atZone(
                        ZoneId.of("Asia/Ho_Chi_Minh")));

        Instant vietnamStart =
                LocalDate.of(2026, 1, 2)
                        .atStartOfDay(
                                ZoneId.of("Asia/Ho_Chi_Minh"))
                        .toInstant();

        System.out.println("vietnamStart=" + vietnamStart);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstantZoneDemo.java
java InstantZoneDemo
~~~

**Stdout:**

~~~text
utcDate=2026-01-01
vietnamDate=2026-01-02
vietnamTime=2026-01-02T06:30+07:00[Asia/Ho_Chi_Minh]
vietnamStart=2026-01-01T17:00:00Z
~~~

**Giải thích:**

- Sự kiện có cùng Instant, nhưng **ngày ở UTC** là 1/1, còn **ngày ở Việt Nam** là 2/1.
- Đầu ngày 2/1 tại Việt Nam theo quy tắc vùng ở thời điểm ví dụ tương ứng **17:00Z ngày 1/1**.
- **Instant** cần cho câu hỏi "sự kiện xảy ra khi nào"; **LocalDate** cần cho câu hỏi "ngày của sự kiện ở khu vực nào".
- ZoneId nên được xác định từ nghiệp vụ, người dùng hoặc cấu hình. **Không lấy timezone mặc định server một cách ngầm định** khi nghiệp vụ cần múi giờ của người dùng.

### 9.2. Không tạo một Instant chỉ từ LocalDate

~~~java
LocalDate due = LocalDate.of(2026, 1, 2);

// SAI: LocalDate không có phương thức toInstant() độc lập.
// Instant x = due.toInstant();
~~~

Muốn hiểu "hết hạn đầu ngày" phải chọn zone và ranh giới thời gian:

~~~java
Instant boundary = due.atStartOfDay(
        ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
~~~

**atStartOfDay(zone)** trả thời điểm đầu ngày hợp lệ theo quy tắc vùng; có nơi không có đúng **00:00** vì chuyển offset. Không nên tự gắn **00:00Z** cho mọi ngày lịch.

## 10. Cộng trừ trên timeline: Duration và các đơn vị được hỗ trợ

**Instant.plusSeconds(...)**, **plusMillis(...)**, **plusNanos(...)**, **minusSeconds(...)** và **plus(Duration)** tạo một điểm thời gian mới.

~~~java
Instant start = Instant.parse("2026-01-01T10:00:00Z");

Instant timeout = start.plusSeconds(90);
Instant plusHalf = timeout.plusMillis(500);
~~~

**Duration** biểu diễn một độ dài dựa trên giây và nano, phù hợp với hai Instant:

~~~java
Duration elapsed = Duration.between(start, plusHalf);

// elapsed == PT1M30.5S
// elapsed.toMillis() == 90500
~~~

Đây là **đoạn minh họa**, cần import **Instant** và **Duration**.

### 10.1. Instant không có phép cộng tháng lịch

**Instant** không biết tháng của một múi giờ bất kỳ dài bao nhiêu. Vì vậy, cố gắng:

~~~java
instant.plus(1, ChronoUnit.MONTHS);
~~~

sẽ gây **UnsupportedTemporalTypeException**. Đây là **đoạn minh họa**, cần instant và import **ChronoUnit**.

Nếu muốn "một tháng lịch sau, cùng giờ địa phương tại một zone", cần:

1. Chuyển Instant sang **ZonedDateTime** ở zone nghiệp vụ.
2. Thực hiện phép cộng tháng trên ngày-giờ đã có zone.
3. Chuyển kết quả trở lại Instant.

Ví dụ:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant nextMonthAtLocalTime =
        instant.atZone(zone)
                .plusMonths(1)
                .toInstant();
~~~

**Không thay thế tháng lịch bằng 30 * 24 * 60 * 60 giây** trừ khi nghiệp vụ nói rõ "30 ngày cố định, mỗi ngày 24 giờ".

### 10.2. Instant.plus(1, DAYS) là 86.400 giây

Đối với **Instant**, **ChronoUnit.DAYS** là đơn vị thời lượng cố định **86.400 giây**, không phải quy tắc "sang ngày địa phương kế tiếp" trong một khu vực có DST.

~~~java
Instant later = instant.plus(1, ChronoUnit.DAYS);
~~~

**later** là điểm sau **86.400 giây** trên timeline. Khi phải tính ranh giới **ngày mai theo giờ vùng**, nên dùng **LocalDate.plusDays(1).atStartOfDay(zone).toInstant()** hoặc phép toán lịch trên ZonedDateTime được thiết kế theo yêu cầu.

## 11. DST: cùng một ngày lịch có thể dài 23 hoặc 25 giờ

Tại một số zone có chuyển giờ mùa hè (DST), hai đầu ngày liên tiếp có thể cách nhau 23 hoặc 25 giờ thực.

Ví dụ **America/New_York** năm 2024:

- Từ đầu **2024-03-10** tới đầu **2024-03-11**: **23 giờ thực**.
- Từ đầu **2024-11-03** tới đầu **2024-11-04**: **25 giờ thực**.

Dù vậy, đây đều là **hai ngày lịch liên tiếp**. Sự khác biệt đến từ quy tắc zone áp dụng cho giờ địa phương.

Lưu thành **InstantDstDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;

public class InstantDstDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");

        LocalDate date = LocalDate.of(2024, 3, 10);

        Instant start = date
                .atStartOfDay(newYork)
                .toInstant();

        Instant tomorrowStart = date.plusDays(1)
                .atStartOfDay(newYork)
                .toInstant();

        Instant afterFixedDay =
                start.plus(1, ChronoUnit.DAYS);

        System.out.println("start=" + start);
        System.out.println("nextStart=" + tomorrowStart);
        System.out.println("hours="
                + Duration.between(start, tomorrowStart)
                        .toHours());

        System.out.println("fixedDayAtZone="
                + afterFixedDay.atZone(newYork));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstantDstDemo.java
java InstantDstDemo
~~~

**Stdout:**

~~~text
start=2024-03-10T05:00:00Z
nextStart=2024-03-11T04:00:00Z
hours=23
fixedDayAtZone=2024-03-11T01:00-04:00[America/New_York]
~~~

**Giải thích:** **start.plus(1, DAYS)** cộng đúng **24 giờ** nên ở New York thành **01:00 ngày kế tiếp**, không phải 00:00. Nếu bài toán là **"bắt đầu ngày tiếp theo"**, tính ngày lịch bằng LocalDate và **atStartOfDay(zone)** mới thể hiện đúng yêu cầu.

**Chú ý:** offset của một vùng có thể thay đổi theo lịch sử và chính sách; không hard-code số giờ DST cho mọi năm và mọi địa điểm. Ví dụ này mô tả quy tắc lịch sử cụ thể năm 2024.

## 12. Chênh lệch và so sánh hai Instant

**Duration.between(start, end)** trả độ dài giữa hai điểm trên timeline:

~~~java
Instant start =
        Instant.parse("2026-01-01T10:00:00Z");

Instant end =
        Instant.parse("2026-01-01T10:01:30.500Z");

Duration elapsed = Duration.between(start, end);

// elapsed == PT1M30.5S
// elapsed.toMillis() == 90500
~~~

Đoạn này cần import **Instant** và **Duration**.

### 12.1. Trước, sau và bằng nhau

~~~java
boolean before = start.isBefore(end); // true
boolean after = start.isAfter(end);   // false
boolean same = start.equals(end);     // false
int order = start.compareTo(end);     // âm
~~~

**compareTo** chỉ cần hiểu dấu, không giả định kết quả luôn bằng -1 hoặc 1.

### 12.2. Ví dụ đầy đủ: Duration và thứ tự

Lưu thành **InstantTimelineDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class InstantTimelineDemo {
    public static void main(String[] args) {
        Instant start =
                Instant.parse("2026-01-01T10:00:00Z");

        Instant end =
                Instant.parse("2026-01-01T10:01:30.500Z");

        Duration elapsed = Duration.between(start, end);

        System.out.println("before=" + start.isBefore(end));
        System.out.println("duration=" + elapsed);
        System.out.println("millis=" + elapsed.toMillis());

        Instant precise =
                Instant.parse(
                        "2026-03-01T10:15:30.123456789Z");

        System.out.println("precise=" + precise);
        System.out.println("truncated="
                + precise.truncatedTo(ChronoUnit.MILLIS));

        System.out.println("samePoint="
                + Instant.parse(
                        "2026-01-02T06:30:00+07:00")
                        .equals(Instant.parse(
                                "2026-01-01T23:30:00Z")));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstantTimelineDemo.java
java InstantTimelineDemo
~~~

**Stdout:**

~~~text
before=true
duration=PT1M30.5S
millis=90500
precise=2026-03-01T10:15:30.123456789Z
truncated=2026-03-01T10:15:30.123Z
samePoint=true
~~~

**Giải thích:** **truncatedTo(MILLIS)** loại phần nhỏ hơn 1ms khỏi Instant. **samePoint=true** vì hai chuỗi timestamp có offset khác nhau nhưng cùng chỉ một điểm trên timeline.

## 13. Nanosecond precision và mất độ chính xác khi chuyển đổi

**Instant** hỗ trợ phần nano trong một giây, nhưng pipeline dữ liệu thường đi qua các lớp chỉ giữ được mili-giây hoặc micro-giây.

~~~text
Instant nguyên gốc:
2026-03-01T10:15:30.123456789Z

truncate về millisecond:
2026-03-01T10:15:30.123Z

Khác biệt:
456789 nanoseconds đã bị bỏ.
~~~

### 13.1. toEpochMilli() không bảo toàn mọi nano

~~~java
Instant precise =
        Instant.parse("2026-03-01T10:15:30.123456789Z");

long millis = precise.toEpochMilli();

Instant reconstructed = Instant.ofEpochMilli(millis);

// precise.equals(reconstructed) == false
~~~

**Mất chính xác** vì số nguyên milliseconds không biểu diễn được phần nanosecond lẻ. Đây không phải lỗi khi truyền dữ liệu, nhưng cần xác định **yêu cầu precision** của hệ thống.

### 13.2. truncatedTo là thao tác tạo bản sao

~~~java
Instant truncated =
        precise.truncatedTo(ChronoUnit.MILLIS);
~~~

**Instant ban đầu không bị sửa.** **truncatedTo** làm giảm độ chính xác theo một đơn vị thời gian phù hợp. Khi dùng **Instant.truncatedTo(DAYS)**, đây là ngày tính theo timeline tại mốc UTC/epoch, **không** phải phép cắt về đầu ngày theo múi giờ địa phương. Nếu cần ranh giới đầu ngày theo người dùng, dùng **date.atStartOfDay(zone).toInstant()**.

### 13.3. Độ phân giải clock khác precision của kiểu

- **Instant** có trường nano với độ phân giải biểu diễn 1ns.
- **Instant.now()** lấy thời gian từ clock thực tế, có độ phân giải/phương pháp nội suy tùy nền tảng.
- **Database** có thể chỉ lưu timestamp tới microsecond hoặc millisecond.
- **JSON serializer** có thể làm tròn hoặc thay đổi dạng chuỗi trong một số cấu hình.
- **System.currentTimeMillis()** cho số milliseconds từ epoch, không cho cùng khả năng biểu diễn nano.
- **System.nanoTime()** dùng để đo thời gian trôi qua, **không** phải epoch timestamp. Không chuyển giá trị nanoTime trực tiếp thành Instant.

**Không coi "chuỗi dài chín chữ số nano" là chứng cứ rằng timestamp thực sự được đo chính xác tới nano.**

## 14. Thời gian đo thực tế và vấn đề đồng hồ hệ thống

Một lưu ý quan trọng trong ứng dụng:

**Instant.now() là wall-clock time source**. Đồng hồ hệ thống có thể được điều chỉnh do đồng bộ thời gian, thay đổi cấu hình hoặc cơ chế nền tảng. Hai lần gọi now() không được đảm bảo cho giá trị tăng đều trong mọi tình huống.

Nếu mục tiêu là **đo elapsed time của một đoạn code**, thường nên dùng:

~~~java
long start = System.nanoTime();

// Thực hiện công việc cần đo ở đây.

long elapsedNanos = System.nanoTime() - start;
~~~

Đây là **đoạn minh họa**, không phải một benchmark hoàn chỉnh. **System.nanoTime()** thích hợp để tính chênh lệch trong cùng một JVM; giá trị tuyệt đối của nó không được định nghĩa theo epoch. Không gửi giá trị nanoTime như timestamp sang hệ thống khác.

Nếu mục tiêu là **ghi thời điểm một sự kiện**, dùng **Instant.now(clock)** (có thể tiêm clock để test). Nếu cần một thứ tự sự kiện hoàn toàn xác định trong hệ thống phân tán, ngoài timestamp còn có thể cần **ID**, **sequence number**, **log offset** hoặc cơ chế đồng bộ đồng hồ phù hợp.

### 14.1. Timestamp không tự là định danh duy nhất

Hai yêu cầu tạo gần nhau có thể có cùng Instant nếu đồng hồ/đường lưu trữ chỉ phân biệt đến millisecond. **Không tự dùng Instant.now().toString() làm khóa duy nhất** cho giao dịch hoặc bản ghi; nên dùng một định danh đúng nghĩa và dùng Instant cho thời gian.

### 14.2. Không lấy timestamp làm bằng chứng thứ tự nhân quả tuyệt đối

Trong hệ thống đa máy, clock có thể lệch nhau; sự kiện ở máy B có timestamp sớm hơn dù thực tế xảy ra sau sự kiện ở máy A. Instant giúp biểu diễn thời điểm quan sát, nhưng không tự đảm bảo đồng bộ clock hoặc causal ordering.

## 15. Mô hình hóa khoảng thời gian [startInclusive, endExclusive)

Đối với một khoảng chứa **các thời điểm** trên timeline, dùng ranh giới:

~~~text
[startInclusive, endExclusive)

start được tính trong khoảng;
end không được tính trong khoảng.
~~~

Điều kiện:

~~~java
boolean inWindow =
        !time.isBefore(startInclusive)
                && time.isBefore(endExclusive);
~~~

Đây là **đoạn minh họa**, các biến phải là Instant.

**Vì sao không dùng endInclusive tùy tiện?** End-exclusive giúp ghép các khoảng liền kề mà không trùng tại biên, và không cần trừ 1 millisecond/nanosecond (điều đó phụ thuộc độ chính xác của dữ liệu).

### 15.1. Ví dụ đầy đủ: kiểm tra phiên có hiệu lực

Lưu thành **InstantWindowDemo.java**:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public class InstantWindowDemo {
    record Window(Instant startInclusive, Instant endExclusive) {
        Window {
            Objects.requireNonNull(startInclusive);
            Objects.requireNonNull(endExclusive);

            if (!startInclusive.isBefore(endExclusive)) {
                throw new IllegalArgumentException(
                        "start must be before end");
            }
        }

        boolean contains(Instant time) {
            Objects.requireNonNull(time);

            return !time.isBefore(startInclusive)
                    && time.isBefore(endExclusive);
        }

        Duration length() {
            return Duration.between(
                    startInclusive, endExclusive);
        }
    }

    public static void main(String[] args) {
        Instant start =
                Instant.parse("2026-01-01T10:00:00Z");

        Window window = new Window(
                start,
                start.plusSeconds(90)
        );

        System.out.println("startIncluded="
                + window.contains(start));

        System.out.println("middleIncluded="
                + window.contains(start.plusSeconds(45)));

        System.out.println("endIncluded="
                + window.contains(start.plusSeconds(90)));

        System.out.println("length=" + window.length());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstantWindowDemo.java
java InstantWindowDemo
~~~

**Stdout:**

~~~text
startIncluded=true
middleIncluded=true
endIncluded=false
length=PT1M30S
~~~

**Giải thích:** Cửa sổ thời gian dài 90 giây **thực**, không bị ảnh hưởng bởi timezone của người dùng. Ranh giới cuối **không bao gồm** điểm end. Với yêu cầu "phiên còn hiệu lực đến trước thời điểm X", điều kiện **now.isBefore(expiresAt)** diễn đạt trực tiếp chính sách hết hạn.

**Lưu ý nghiệp vụ:** Nếu hệ thống cho phép start==end để biểu diễn khoảng rỗng, có thể điều chỉnh validation. Ví dụ này cố ý cấm khoảng rỗng/đảo ngược. Không suy rằng java.time tự buộc mọi interval phải có start<end.

## 16. Ứng dụng thực tế: createdAt, updatedAt và expiresAt

### 16.1. Tạo event timestamp

Một bản ghi sự kiện có thể gồm:

~~~java
record Event(String id, Instant occurredAt) {}
~~~

Đây là **mã minh họa Java 17+**, cần import **Instant** và một class chứa record hợp lệ. **occurredAt** biểu diễn **điểm trên timeline**. Có thể lưu thêm nguồn sự kiện, ID và các thông tin khác, nhưng không cần gắn timezone của người nhận để biểu diễn timestamp.

### 16.2. Hết hạn tính theo Duration

~~~java
Instant issuedAt = Instant.now(clock);
Instant expiresAt = issuedAt.plus(Duration.ofMinutes(15));

boolean valid = Instant.now(clock).isBefore(expiresAt);
~~~

Đoạn minh họa với **Clock clock** được truyền từ ngoài.

Nếu nghiệp vụ nói **"có hiệu lực đúng 15 phút kể từ khi phát hành"**, Duration là kiểu phù hợp. Nếu nói **"hết hạn lúc nửa đêm ngày mai theo New York"**, đó là quy tắc **ngày giờ địa phương**, cần ZoneId và ngày lịch; không thay bằng Duration cố định 24 giờ.

### 16.3. Đặt timestamp ở ranh giới hệ thống

Trong một request hoặc giao dịch, thường nên lấy **một Instant** nếu nhiều trường phải phản ánh cùng thời điểm:

~~~java
Instant now = Instant.now(clock);

entity.setCreatedAt(now);
entity.setUpdatedAt(now);
~~~

Đây là **mã minh họa** (entity và clock phụ thuộc ứng dụng). Nếu gọi now() hai lần riêng biệt, chúng có thể cho hai giá trị hơi khác nhau, không có gì sai nhưng có thể không phù hợp nếu nghiệp vụ yêu cầu cùng thời điểm cho lần tạo đầu tiên.

### 16.4. Đồng hồ ứng dụng và đồng hồ database

Nếu cả ứng dụng và database đều tự gán createdAt, cần xác định **nguồn thời gian có thẩm quyền**. Dùng Instant trong Java không khiến đồng hồ các thành phần tự đồng bộ. Đừng giả định timestamp Java và **CURRENT_TIMESTAMP** của database sẽ giống nhau tuyệt đối.

## 17. Lưu trữ và truyền timestamp qua API

### 17.1. Trên REST/JSON

Dạng ISO dễ đọc:

~~~json
{
  "eventId": "evt-001",
  "occurredAt": "2026-01-01T23:30:00Z"
}
~~~

Hoặc một API có thể dùng epoch milliseconds:

~~~json
{
  "eventId": "evt-001",
  "occurredAtEpochMillis": 1767310200000
}
~~~

Cần **ghi rõ đơn vị** trong schema. Một số hệ thống trả số **epoch seconds**, một số dùng **milliseconds**, microseconds hoặc nanoseconds. Không đoán đơn vị chỉ từ kiểu long. Nếu phải hiển thị ngày theo người dùng, chọn **ZoneId của người dùng** sau khi parse timestamp.

**Bổ sung:** số epoch-millis trong JSON ở ví dụ trên chỉ mang nghĩa timestamp sau khi API contract xác định rõ giá trị và đơn vị. Khi sử dụng mã thực, cần kiểm thử phép round-trip giữa chuỗi ISO và số epoch.

### 17.2. Trong cơ sở dữ liệu

Một số JDBC driver/ORM hỗ trợ ánh xạ **Instant** trực tiếp tới kiểu timestamp tương ứng, nhưng semantics của cột **TIMESTAMP**, **TIMESTAMP WITH TIME ZONE**, độ chính xác phần giây và cách chuyển zone phụ thuộc database, driver và cấu hình.

**Không có một lời hứa chung** rằng mọi hệ quản trị CSDL sẽ lưu/đọc **Instant** với đủ nanosecond và cùng cách áp timezone. Nên:

1. Chọn kiểu cột đáp ứng semantics của **một thời điểm tuyệt đối**.
2. Kiểm thử ghi/đọc cùng Instant qua driver và môi trường production.
3. Kiểm tra precision thật (nano, micro hay milli).
4. Quy định rõ timezone tại lớp chuyển đổi hoặc lưu trữ nếu database cần.
5. Không trộn timestamp sự kiện với cột **DATE** dành cho ngày lịch.
6. Dùng đồng hồ/time source có thẩm quyền; kiểm thử dữ liệu gần ranh giới ngày.

### 17.3. Epoch time không phải lúc nào cũng là thời gian hiển thị

Một timestamp dưới dạng long không cung cấp locale, ngày giờ hiển thị hoặc quy tắc DST. Client cần áp dụng **ZoneId/Locale** phù hợp. Nếu bạn chỉ lưu **LocalDateTime** thiếu zone như một "timestamp toàn cục", sau này rất khó xác định đúng Instant của các sự kiện lịch sử.

## 18. Phạm vi hỗ trợ, ngoại lệ và Java Time-Scale

**Instant.MIN**, **Instant.MAX** xác định miền giá trị được API hỗ trợ. Instant đủ rộng cho nhiều ứng dụng, nhưng không vô hạn. Các phép cộng trừ vượt phạm vi, hoặc phép chuyển sang một kiểu date-time không biểu diễn được năm tương ứng, có thể ném **DateTimeException** hoặc **ArithmeticException** tùy phương thức.

**toEpochMilli()** có thể ném **ArithmeticException** nếu số milliseconds vượt phạm vi **long**, dù bản thân Instant hợp lệ. Không cho rằng mọi Instant đều có thể encode không mất mát thành một long millisecond.

### 18.1. Không tự lấy các trường YEAR/MONTH từ Instant

~~~java
// SAI: Instant không trực tiếp hỗ trợ calendar YEAR.
// instant.get(ChronoField.YEAR);
~~~

Nếu cần năm/tháng/ngày của thời điểm, phải chọn một ZoneId hoặc ZoneOffset, sau đó đọc từ ZonedDateTime/OffsetDateTime:

~~~java
int year = instant.atZone(zone).getYear();
~~~

Đây là **đoạn minh họa**, các biến instant và zone phải được khai báo.

### 18.2. Leap seconds và độ chính xác vật lý

API java.time định nghĩa **Java Time-Scale** cho Instant và mô tả cách quan hệ với thời gian dân sự, bao gồm cách xử lý quanh leap second. **Đừng suy rằng mọi máy/JVM có thể quan sát hoặc đánh dấu riêng giây nhuận bằng chính đồng hồ hệ thống**, hay rằng số nanosecond ghi trong Instant luôn là đo đạc vật lý chính xác đến 1ns.

Với phần lớn ứng dụng cần timestamp, dùng API Instant và Duration đúng hợp đồng là lựa chọn phù hợp. Nếu xây hệ thống đo thời gian khoa học hoặc yêu cầu leap-second semantics nghiêm ngặt, cần xác định chuẩn thời gian và nguồn clock ở cấp hệ thống, không coi Instant.now() là đồng hồ nguyên tử.

## 19. Những lỗi thường gặp

### Lỗi 1 — Lưu LocalDateTime để thay Instant

~~~java
LocalDateTime createdAt = LocalDateTime.now();
~~~

Nếu mục tiêu là **mốc sự kiện toàn cục**, LocalDateTime thiếu zone/offset để diễn giải. Chọn **Instant.now(clock)**.

### Lỗi 2 — Nhầm epoch seconds và milliseconds

~~~java
long seconds = 1_000L;

// SAI nếu đây là epoch seconds:
Instant wrong = Instant.ofEpochMilli(seconds);

// ĐÚNG:
Instant correct = Instant.ofEpochSecond(seconds);
~~~

Sai đơn vị làm timestamp lệch nhiều bậc độ lớn. Schema và tên biến phải thể hiện đơn vị.

### Lỗi 3 — Nghĩ getNano là tổng nanoseconds từ epoch

~~~java
Instant time = Instant.ofEpochSecond(2, 500_000_000);

long seconds = time.getEpochSecond(); // 2
int nanos = time.getNano();           // 500000000
~~~

Hai thành phần có ý nghĩa riêng; **getNano** không bằng số nano tích lũy kể từ 1970.

### Lỗi 4 — Nhầm Instant và ZoneId

~~~java
Instant event = Instant.now();

// Không có event.getZone().
// Chỉ khi gọi event.atZone(zone) mới có biểu diễn ZonedDateTime.
~~~

ZoneId dùng để hiển thị hoặc chuyển sang ngày giờ địa phương, không gắn vào Instant.

### Lỗi 5 — Dùng Instant.parse cho LocalDateTime không offset

~~~java
// Không hợp lệ:
Instant.parse("2026-01-02T06:30:00");
~~~

Cần chuỗi timestamp có đủ offset hoặc chuyển LocalDateTime với ZoneId được quy định.

### Lỗi 6 — Cộng 24h để tìm đầu ngày mai ở mọi nơi

~~~java
Instant tomorrow = start.plus(Duration.ofHours(24));
~~~

Đúng nếu cần **24 giờ thực**, nhưng có thể sai nếu yêu cầu **đầu ngày địa phương kế tiếp** trong zone có DST.

### Lỗi 7 — Cộng MONTHS trực tiếp trên Instant

~~~java
// Không hỗ trợ:
instant.plus(1, ChronoUnit.MONTHS);
~~~

Chuyển sang ZonedDateTime khi nghiệp vụ cần cộng theo **tháng lịch**.

### Lỗi 8 — Mong Instant có setter

~~~java
instant.plusSeconds(60); // Không thay đổi instance cũ.
~~~

LocalDate/Instant và các class java.time phổ biến đều immutable; gán kết quả về biến khác hoặc chính biến đó.

### Lỗi 9 — So sánh object identity

~~~java
// Không dùng == để kiểm tra cùng timeline.
boolean same = a.equals(b);
~~~

Instant là value-based class; dùng equals/isBefore/isAfter.

### Lỗi 10 — Biến epoch-millis thành precision nano

~~~java
Instant reconstructed =
        Instant.ofEpochMilli(original.toEpochMilli());
~~~

Không chắc **original.equals(reconstructed)** nếu original có phần sub-millisecond.

### Lỗi 11 — Dùng Instant.now để đo benchmark

Thời gian hệ thống có thể bị điều chỉnh; dùng **System.nanoTime()** để tính elapsed-time của đoạn code trong cùng JVM (cùng với công cụ benchmark phù hợp nếu cần đo hiệu năng nghiêm túc).

### Lỗi 12 — Dùng timestamp làm primary key duy nhất

Hai sự kiện gần nhau có thể trùng timestamp ở độ chính xác mà clock/database hỗ trợ. Dùng ID riêng nếu nghiệp vụ cần uniqueness.

### Lỗi 13 — Hiển thị timestamp theo UTC mà gọi là "ngày của người dùng"

Có thể lệch ngày. Phải chuyển Instant sang **userZone** trước khi lấy LocalDate hoặc hiển thị thời gian.

### Lỗi 14 — Dùng số millis trong JSON không có schema

Một số ngôn ngữ/hệ thống mặc định seconds, một số mặc định milliseconds. Đặt tên rõ ràng và kiểm tra round-trip.

### Lỗi 15 — Giả định mọi Instant có thể chuyển toEpochMilli

Một Instant hợp lệ quá xa mốc epoch vẫn có thể vượt phạm vi long millisecond. Xem xét exception và miền dữ liệu của hệ thống.

### Lỗi 16 — Trộn business date với audit timestamp

**Ngày giao hàng** thuộc nghiệp vụ date-only có thể cần LocalDate. **Thời điểm sửa đơn hàng** cần Instant. Đừng ép hai kiểu này vào một field rồi phụ thuộc timezone hiển thị.

## 20. Checklist kiểm thử

Một bộ test hợp lý nên bao gồm:

1. **EPOCH**, số giây dương, số giây âm.
2. **ofEpochSecond** với nanoAdjustment lớn hơn 1 tỷ hoặc âm.
3. **ofEpochMilli** và **toEpochMilli**, kể cả phần nano không tròn mili-giây.
4. **Parse timestamp ISO** có **Z** và offset, xác nhận hai chuỗi biểu diễn cùng một Instant.
5. **Parse thiếu offset** phải bị từ chối khi định parse trực tiếp thành Instant.
6. **Clock.fixed** để kết quả now có thể lặp lại.
7. **Đổi ZoneId**: cùng Instant cho ngày UTC và Việt Nam khác nhau ở ranh giới ngày.
8. **Duration** cho khoảng vài giây, sub-second và khoảng âm.
9. **Ranh giới [start,end)**: start được tính, end không được tính.
10. **DST**: 24 giờ trên timeline khác một ngày lịch theo zone tại mốc chuyển giờ.
11. **Immutable**: plus/minus không thay object cũ.
12. **Giá trị rất xa epoch**: phương thức đổi millis có thể ném lỗi.
13. **Precision round-trip** giữa Java, JSON và database.
14. **Đồng hồ được tiêm**: không có test dựa vào ngày giờ thực hoặc timezone mặc định.
15. **Quy tắc expiry**: phân biệt 15 phút thực với "hết ngày theo múi giờ".
16. **Timezone của client**: không hiển thị nhầm ngày UTC thành ngày địa phương.

### 20.1. Quy ước kết quả test

Với những phép dựa trên **Instant.parse(...)** hoặc **Clock.fixed(...)**, có thể ghi stdout cố định như các ví dụ trong bài. Với **Instant.now()**, **không** ghi stdout cố định; cùng code chạy vào thời điểm khác nhau chắc chắn có thể cho giá trị khác.

## 21. Bài tập tự kiểm tra

**Câu 1.** Instant có chứa ZoneId hoặc ngày giờ địa phương không?

**Câu 2.** **Instant.EPOCH** có giá trị ISO nào? **getEpochSecond()** của nó là bao nhiêu?

**Câu 3.** Hai chuỗi **2026-01-01T23:30:00Z** và **2026-01-02T06:30:00+07:00** có trỏ tới cùng Instant không?

**Câu 4.** Khi gọi **Instant.ofEpochSecond(1, 250_000_000)**, giá trị getEpochSecond, getNano và toEpochMilli là gì?

**Câu 5.** **Instant.ofEpochSecond(-1, 999_999_999)** nằm trước hay sau epoch? **toEpochMilli()** của nó là bao nhiêu?

**Câu 6.** Vì sao **Instant.now()** không phù hợp để so sánh với một timestamp cố định trong unit test? Nên dùng API nào?

**Câu 7.** Khi ở UTC là **2026-01-01T23:30Z**, ngày tại **Asia/Ho_Chi_Minh** là ngày nào?

**Câu 8.** **Duration.between(a,b)** có thể tính từ hai Instant mà không cần ZoneId không?

**Câu 9.** Vì sao **Instant.plus(1, ChronoUnit.DAYS)** có thể khác **ngày tiếp theo theo lịch địa phương**?

**Câu 10.** Có nên lưu ngày sinh dưới dạng **Instant tại 00:00 UTC** khi nghiệp vụ chỉ cần date-only không?

**Câu 11.** Nếu một Instant có phần nano không tròn millisecond, **ofEpochMilli(toEpochMilli(...))** có bảo toàn toàn bộ Instant không?

**Câu 12.** **System.nanoTime()** có dùng trực tiếp làm epoch timestamp trong JSON được không?

**Câu 13.** **Instant.parse("2026-01-02T06:30:00")** có đủ thông tin để tạo Instant không?

**Câu 14.** Trong khoảng **[start,end)**, thời điểm đúng bằng end có được tính là nằm trong khoảng không?

**Câu 15.** Muốn tăng một tháng lịch theo giờ New York kể từ một Instant, làm thế nào?

**Câu 16.** Nếu đã có Instant, muốn hiển thị năm/tháng/ngày cho khách hàng ở Paris, cần thêm gì?

### Đáp án

1. **Không.** Instant là điểm trên timeline, không mang zone/offset như thuộc tính của nó.
2. **1970-01-01T00:00:00Z**, epochSecond bằng **0**.
3. **Có.** Chúng cùng một điểm thời gian, chỉ khác cách viết offset.
4. **1**, **250.000.000**, **1.250**.
5. **Trước epoch một nanosecond**; **toEpochMilli() == -1**.
6. Vì now() đọc đồng hồ thực và thay đổi theo thời điểm chạy. Dùng **Instant.now(Clock.fixed(...))** để test.
7. **2026-01-02**.
8. **Có.** Duration đo chênh lệch theo timeline, không cần ZoneId.
9. Vì **DAYS trên Instant = 86.400 giây**, còn ngày lịch tại zone có DST có thể dài 23 hoặc 25 giờ.
10. **Không nên.** Dùng **LocalDate** để tránh tự đưa timezone/timestamp vào một ngày lịch.
11. **Không.** Chuyển qua millisecond làm mất độ chính xác nhỏ hơn 1ms.
12. **Không.** nanoTime có gốc tùy ý và phục vụ đo elapsed time, không phải epoch.
13. **Không.** Thiếu offset/zone. Cần chọn zone hoặc cung cấp chuỗi có offset.
14. **Không**, vì endExclusive không thuộc khoảng.
15. Chuyển sang **ZonedDateTime** với **ZoneId.of("America/New_York")**, gọi **plusMonths(1)** rồi **toInstant()**.
16. Cần **ZoneId vùng** phù hợp, ví dụ **Europe/Paris**, rồi gọi **instant.atZone(zone)**.

## 22. Tóm tắt và tài liệu chính thức

**Instant là kiểu Java hiện đại để mô tả một điểm trên timeline.** Nó phù hợp cho timestamp sự kiện, audit, giao dịch, thời điểm hết hạn và khoảng Duration. Cấu trúc biểu diễn gồm **epoch seconds** và **nano-of-second**, vì vậy đừng nhầm các đơn vị seconds/milliseconds/nanoseconds khi lưu hoặc chuyển dữ liệu.

Những nguyên tắc quan trọng nhất:

- **Instant không phải LocalDateTime hay ZonedDateTime.** Nó không có ngày/giờ địa phương cho tới khi gắn một ZoneId/offset để chuyển đổi.
- **Instant.now(Clock)** cho phép test có thời gian cố định; Instant.now() đọc thời gian hệ thống.
- **Instant immutable**, so sánh bằng equals/isBefore/isAfter, và Duration đo khoảng giữa các Instant.
- **Instant.plus(1, DAYS)** tính đúng 86.400 giây; quy tắc "ngày mai tại một vùng" là phép tính lịch có zone và DST.
- **toEpochMilli() có thể mất phần nanosecond** hoặc tràn long nếu Instant quá xa epoch; timestamp cần schema đơn vị và precision.
- **LocalDate** dành cho ngày lịch; **Instant** dành cho thời điểm cụ thể.
- **Hệ thống phân tán** vẫn cần quản lý đồng hồ, sequence và transaction phù hợp; Instant không tự bảo đảm timestamp duy nhất hoặc thứ tự nhân quả.

Tài liệu Oracle Java API còn áp dụng:

- [Instant — Java SE 26: điểm trên timeline, epoch seconds/nanos, parse, now, conversion và arithmetic](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
- [java.time package — Java SE 26: mô hình ngày giờ và Java Time-Scale](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/package-summary.html)
- [Clock — Java SE 26: nguồn thời gian và Clock.fixed](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html)
- [Duration — Java SE 26: khoảng thời gian trên timeline](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Duration.html)
- [ZoneId — Java SE 26: quy tắc múi giờ vùng](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html)
- [ZonedDateTime — Java SE 26: thời gian địa phương và thay đổi zone](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html)
- [DateTimeFormatter — Java SE 26: ISO_INSTANT](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html)
