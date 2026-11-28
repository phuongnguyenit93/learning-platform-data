# Clock và thiết kế xử lý thời gian có thể kiểm thử

Trong Java 27, các quy tắc như **“mã xác thực hết hạn sau 5 phút”**, **“hôm nay là ngày nào tại Hà Nội”** hay **“đơn hàng đã quá hạn chưa”** đều phụ thuộc vào thời điểm hiện tại. Nếu logic nghiệp vụ gọi trực tiếp **Instant.now()**, **LocalDate.now()** hoặc **System.currentTimeMillis()** ở nhiều vị trí, bài kiểm thử có thể cho kết quả khác nhau theo thời gian thực, múi giờ máy chạy hoặc khoảnh khắc chuyển ngày.

**java.time.Clock** giải quyết vấn đề này bằng cách biến nguồn cung cấp thời gian thành một **phụ thuộc có thể thay thế**. Khi chạy thật, ứng dụng dùng đồng hồ hệ thống. Khi kiểm thử, ta có thể cung cấp một đồng hồ trả về thời điểm cố định, một đồng hồ dịch chuyển sang tương lai hoặc một đồng hồ có múi giờ chỉ định. Logic nghiệp vụ không phải thay đổi.

Bài học này tập trung vào các API còn áp dụng trong Java 27, đặc biệt là **Clock**, **Instant**, **LocalDate**, **ZonedDateTime**, **Duration**, **ZoneId** và **InstantSource**. Không dùng các API ngày giờ kiểu cũ hoặc tính năng preview.

## 1. Vấn đề của việc đọc thời gian trực tiếp

Xét một method kiểm tra mã có hết hạn hay không:

~~~java
import java.time.Instant;

static boolean expired(Instant deadline) {
    return !Instant.now().isBefore(deadline);
}
~~~

Mã trên chạy được, nhưng có một phụ thuộc ẩn: **đồng hồ thực của máy chạy ứng dụng**.

Khi viết kiểm thử, ta không kiểm soát được chính xác thời điểm **Instant.now()** trả về. Một bài kiểm thử liên quan đến ranh giới hết hạn có thể đúng lúc này và sai vài mili giây sau. Nếu cần kiểm tra cả tình huống “trước hạn”, “đúng hạn” và “sau hạn”, việc chèn **Thread.sleep** là chậm và không chắc chắn.

Cách cải thiện:

~~~java
import java.time.Clock;
import java.time.Instant;

static boolean expired(Instant deadline, Clock clock) {
    Instant now = clock.instant();
    return !now.isBefore(deadline);
}
~~~

Giờ đây, method không tự quyết định phải đọc đồng hồ nào. Người gọi có thể truyền:

~~~java
Clock production = Clock.systemUTC();

Clock testClock = Clock.fixed(
    Instant.parse("2026-11-27T10:00:00Z"),
    java.time.ZoneOffset.UTC
);
~~~

Cùng một hàm **expired**, nhưng ứng dụng kiểm thử chủ động quyết định **now**. Đây là nền tảng của *deterministic testing* — kiểm thử cho kết quả ổn định với cùng dữ liệu đầu vào.

### 1.1. Sơ đồ phụ thuộc

~~~mermaid
flowchart LR
    A["Logic nghiệp vụ"] --> B["java.time.Clock"]
    B --> C["Clock.systemUTC() khi chạy thật"]
    B --> D["Clock.fixed(...) khi kiểm thử"]
    B --> E["Clock.offset(...) cho kịch bản tương lai"]
~~~

Thay đổi quan trọng nằm ở thiết kế: **thời gian hiện tại được truyền vào qua một giao diện** thay vì bị gọi trực tiếp tại nơi ra quyết định.

## 2. Hiểu ba khái niệm: Instant, múi giờ và giờ địa phương

Muốn sử dụng **Clock** đúng, cần phân biệt ba lớp thông tin khác nhau.

| Khái niệm | Kiểu Java | Ý nghĩa |
|---|---|---|
| Một thời điểm tuyệt đối trên trục thời gian | **Instant** | Dùng cho thời điểm tạo dữ liệu, hạn hết hạn, sự kiện hệ thống |
| Quy tắc giờ theo vùng địa lý | **ZoneId** | Ví dụ **Asia/Ho_Chi_Minh**, **Europe/Berlin** |
| Ngày/giờ địa phương | **LocalDate**, **LocalTime**, **ZonedDateTime** | Dùng cho lịch nghiệp vụ, ngày thanh toán hoặc hiển thị |

**Instant** không lưu múi giờ. Một thời điểm duy nhất có thể được hiển thị thành các ngày giờ khác nhau ở các khu vực khác nhau.

~~~java
import java.time.Instant;
import java.time.ZoneId;

Instant moment = Instant.parse("2026-12-31T17:30:00Z");

System.out.println(moment.atZone(ZoneId.of("UTC")));
System.out.println(moment.atZone(ZoneId.of("Asia/Ho_Chi_Minh")));
~~~

Kết quả:

~~~text
2026-12-31T17:30Z[UTC]
2027-01-01T00:30+07:00[Asia/Ho_Chi_Minh]
~~~

Hai dòng diễn tả **cùng một Instant**, nhưng Việt Nam đã sang ngày 01/01/2027.

Vì vậy, với quy tắc **“sang ngày mới là đến hạn”**, phải xác định rõ **ngày mới theo múi giờ nào**. Dùng múi giờ mặc định của máy chủ có thể làm sai quy tắc khi chuyển môi trường triển khai.

### 2.1. Clock lưu gì?

Một **Clock** cung cấp hai thứ:

1. **clock.instant()**: thời điểm do đồng hồ trả về.
2. **clock.getZone()**: múi giờ dùng khi chuyển thời điểm đó thành ngày/giờ địa phương.

Các factory của **Clock** có thể trả về đồng hồ hệ thống, đồng hồ cố định hoặc đồng hồ biến đổi từ đồng hồ khác. Một Clock không nhất thiết phải phản ánh thời gian thực: đồng hồ **fixed** có chủ đích đứng yên.

## 3. Các factory method quan trọng của Clock

Java SE 27 cung cấp nhiều cách tạo Clock.

| Factory hoặc method | Hành vi | Khi nên dùng |
|---|---|---|
| **Clock.systemUTC()** | Đọc đồng hồ hệ thống; dùng UTC khi chuyển sang thời gian địa phương | Mốc sự kiện, hạn hết hạn và ứng dụng server |
| **Clock.system(ZoneId)** | Đọc đồng hồ hệ thống với múi giờ được chỉ định | Quy tắc ngày/giờ theo một vùng cụ thể |
| **Clock.systemDefaultZone()** | Đọc đồng hồ hệ thống với múi giờ mặc định của môi trường | Chỉ khi yêu cầu thực sự gắn với múi giờ máy chạy |
| **Clock.fixed(Instant, ZoneId)** | Luôn trả về một **Instant** không đổi | Kiểm thử xác định, ranh giới thời gian |
| **Clock.offset(Clock, Duration)** | Cộng một khoảng **Duration** vào thời điểm do Clock gốc trả về | Mô phỏng trước/sau một mốc |
| **Clock.tick(Clock, Duration)** | Trả về các thời điểm được cắt về nhịp đã chỉ định | Hiển thị/nhóm dữ liệu theo độ phân giải |
| **Clock.tickSeconds(ZoneId)** | Đồng hồ hệ thống chỉ hiển thị theo giây tròn | Giao diện hoặc dữ liệu không cần phần lẻ giây |
| **Clock.tickMinutes(ZoneId)** | Đồng hồ hệ thống chỉ hiển thị theo phút tròn | Hiển thị hoặc gom nhóm theo phút |
| **Clock.tickMillis(ZoneId)** | Đồng hồ hệ thống chỉ hiển thị theo mili giây tròn | Khi cần hiển thị đến mili giây |
| **clock.withZone(ZoneId)** | Lấy Clock khác với cùng đặc tính nguồn thời gian nhưng dùng múi giờ khác | So sánh cùng thời điểm tại các vùng |
| **clock.millis()** | Thời điểm tính bằng mili giây từ epoch | Tương thích với API cần **long**; thường ưu tiên **Instant** |

### 3.1. Đồng hồ chạy thật: systemUTC và system(zone)

Khi xử lý những dấu thời gian lưu trong cơ sở dữ liệu hoặc API:

~~~java
Clock clock = Clock.systemUTC();

Instant createdAt = clock.instant();
Instant expiresAt = createdAt.plusSeconds(300);
~~~

**Clock.systemUTC()** là mặc định tốt khi logic chỉ cần một thời điểm. **UTC** ở đây là múi giờ dùng để diễn giải thời điểm, không phải nguồn đồng hồ khác với các vùng còn lại.

Khi tính ngày nghiệp vụ tại Việt Nam:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock clock = Clock.system(businessZone);

LocalDate businessDate = LocalDate.now(clock);
~~~

**Clock.systemDefaultZone()** có thể làm hành vi phụ thuộc cấu hình máy người phát triển, CI hoặc server. Tốt hơn là khai báo múi giờ nghiệp vụ rõ ràng trong cấu hình ứng dụng.

### 3.2. Đồng hồ cố định: fixed

~~~java
Clock clock = Clock.fixed(
    Instant.parse("2026-11-27T10:15:30Z"),
    ZoneId.of("Asia/Ho_Chi_Minh")
);

System.out.println(clock.instant());
System.out.println(LocalDate.now(clock));
System.out.println(LocalDate.now(clock));
~~~

Kết quả:

~~~text
2026-11-27T10:15:30Z
2026-11-27
2026-11-27
~~~

Thời điểm cố định không tiến lên dù bạn gọi **clock.instant()** nhiều lần, hoặc chương trình thực sự chạy lâu hơn. Vì thế, không thể dùng **Thread.sleep** để “đẩy thời gian” của **Clock.fixed**.

Đây chính là đặc điểm giúp kiểm thử không bị ảnh hưởng bởi tốc độ CPU hoặc scheduler.

### 3.3. Đồng hồ dịch chuyển: offset

~~~java
Clock base = Clock.fixed(
    Instant.parse("2026-11-27T10:00:00Z"),
    ZoneOffset.UTC
);

Clock oneHourLater = Clock.offset(base, Duration.ofHours(1));
Clock oneDayEarlier = Clock.offset(base, Duration.ofDays(-1));

System.out.println(base.instant());
System.out.println(oneHourLater.instant());
System.out.println(oneDayEarlier.instant());
~~~

Kết quả:

~~~text
2026-11-27T10:00:00Z
2026-11-27T11:00:00Z
2026-11-26T10:00:00Z
~~~

Nếu Clock gốc là **fixed**, Clock offset cũng không tự chạy theo thời gian thực. Nó chỉ luôn trả thời điểm gốc cộng một **Duration**.

Nếu Clock gốc là **systemUTC()**, kết quả của **Clock.offset** vẫn tiếp tục tiến lên theo đồng hồ hệ thống, nhưng luôn dịch đi một khoảng cố định.

### 3.4. Đồng hồ có nhịp: tick

~~~java
Clock base = Clock.fixed(
    Instant.parse("2026-11-27T10:00:46Z"),
    ZoneOffset.UTC
);

Clock everyThirtySeconds =
    Clock.tick(base, Duration.ofSeconds(30));

System.out.println(everyThirtySeconds.instant());
~~~

Kết quả:

~~~text
2026-11-27T10:00:30Z
~~~

**tick** không đánh thức chương trình sau mỗi khoảng thời gian. Nó chỉ giới hạn độ phân giải thời gian trả về bằng cách cắt về một nhịp. Triển khai có thể dùng cache nên thời điểm đổi nhịp có thể quan sát chậm hơn so với Clock gốc.

Không dùng **Clock.tick** như bộ hẹn giờ, lịch chạy tác vụ hoặc đồng hồ yêu cầu đo thời gian chính xác cao. Các tick duration phải đáp ứng ràng buộc của API; chẳng hạn độ dài tick âm là không hợp lệ và một số khoảng dưới mili giây phải chia hết một giây.

## 4. Dùng Clock với các kiểu java.time

Bộ API **java.time** có những overload nhận **Clock**, giúp test các loại thời gian khác nhau mà không giả lập môi trường hệ điều hành.

~~~java
Clock clock = Clock.fixed(
    Instant.parse("2026-11-27T10:15:30Z"),
    ZoneId.of("Asia/Ho_Chi_Minh")
);

Instant instant = Instant.now(clock);
LocalDate date = LocalDate.now(clock);
LocalTime time = LocalTime.now(clock);
LocalDateTime dateTime = LocalDateTime.now(clock);
ZonedDateTime zoned = ZonedDateTime.now(clock);
OffsetDateTime offsetDateTime = OffsetDateTime.now(clock);
~~~

| Kiểu kết quả | Ý nghĩa | Kết quả với Clock ví dụ |
|---|---|---|
| **Instant** | Thời điểm tuyệt đối | **2026-11-27T10:15:30Z** |
| **LocalDate** | Ngày theo zone | **2026-11-27** |
| **LocalTime** | Giờ trong ngày theo zone | **17:15:30** |
| **LocalDateTime** | Ngày và giờ, không lưu zone | **2026-11-27T17:15:30** |
| **ZonedDateTime** | Ngày giờ kèm zone | **2026-11-27T17:15:30+07:00[Asia/Ho_Chi_Minh]** |
| **OffsetDateTime** | Ngày giờ kèm offset cụ thể | **2026-11-27T17:15:30+07:00** |

Khi chỉ cần dấu thời gian để lưu và so sánh, **Instant** thường phù hợp hơn **LocalDateTime**, vì **LocalDateTime** không chứa thông tin cần thiết để xác định một thời điểm tuyệt đối trên toàn cầu.

Khi cần “hôm nay” theo lịch, dùng **LocalDate.now(clock)** với Clock có múi giờ nghiệp vụ.

**Lưu ý:** Không gọi **LocalDate.now()** không tham số ở giữa một module đã áp dụng Clock injection; điều đó tạo lại phụ thuộc ẩn vào đồng hồ và múi giờ hệ thống.

## 5. Dependency injection: truyền Clock qua constructor

Cách thiết kế dễ kiểm thử là **constructor injection**: một dịch vụ nhận **Clock** khi được khởi tạo và giữ nó trong field **final**.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class AuditService {
    private final Clock clock;

    public AuditService(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public Instant occurredAt() {
        return clock.instant();
    }
}
~~~

Khi chạy thật:

~~~java
AuditService auditService = new AuditService(Clock.systemUTC());
~~~

Khi kiểm thử:

~~~java
Clock fake = Clock.fixed(
    Instant.parse("2026-11-27T12:00:00Z"),
    ZoneOffset.UTC
);

AuditService auditService = new AuditService(fake);

if (!auditService.occurredAt().equals(
        Instant.parse("2026-11-27T12:00:00Z"))) {
    throw new AssertionError("Thời gian không như mong đợi");
}
~~~

Không cần thay đổi **AuditService** giữa hai môi trường. Bài kiểm thử không phải gọi sleep hoặc chỉnh thời gian máy tính.

### 5.1. Chọn phạm vi của Clock

Có thể đưa một **Clock** vào từng service cần thời gian. Trong ứng dụng lớn, tạo Clock ở **composition root** (nơi lắp ghép các dependency, ví dụ cấu hình ứng dụng) rồi truyền cho các service liên quan.

~~~java
Clock appClock = Clock.systemUTC();

AuditService audit = new AuditService(appClock);
TokenService tokens = new TokenService(appClock);
~~~

Cách này làm chính sách “thời gian hiện tại lấy từ đâu” nhất quán trong hệ thống. Khi cần múi giờ riêng cho một nghiệp vụ, nên thể hiện **ZoneId** độc lập thay vì giả định mọi hoạt động đều dùng múi giờ của Clock chung.

Tránh hai dạng:

~~~java
// Phụ thuộc ẩn: không dễ thay thế khi kiểm thử.
private static final Instant STARTED_AT = Instant.now();

// Mỗi lần gọi lại tự chọn đồng hồ hệ thống.
static Instant getDeadline() {
    return Instant.now().plusSeconds(300);
}
~~~

Trong hai trường hợp trên, thay Clock của bài test sẽ không ảnh hưởng đến những chỗ đọc thời gian trực tiếp.

## 6. Ví dụ đầy đủ: kiểm thử mã truy cập có hạn sử dụng

Bài toán: mã truy cập có hiệu lực **5 phút** kể từ lúc phát hành. Ta thống nhất quy tắc ranh giới:

> Mã **hết hạn khi now lớn hơn hoặc bằng expiresAt**. Ngay đúng thời điểm expiresAt, mã đã không còn hợp lệ.

Lưu ví dụ sau vào **ClockTokenDemo.java**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public class ClockTokenDemo {

    record AccessToken(
        String id,
        Instant issuedAt,
        Instant expiresAt
    ) {
        AccessToken {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(issuedAt, "issuedAt");
            Objects.requireNonNull(expiresAt, "expiresAt");

            if (id.isBlank() || !expiresAt.isAfter(issuedAt)) {
                throw new IllegalArgumentException("Token không hợp lệ");
            }
        }
    }

    static final class TokenService {
        private final Clock clock;

        TokenService(Clock clock) {
            this.clock = Objects.requireNonNull(clock, "clock");
        }

        AccessToken issue(String id, Duration validity) {
            Objects.requireNonNull(validity, "validity");
            if (validity.isZero() || validity.isNegative()) {
                throw new IllegalArgumentException(
                    "Thời hạn phải lớn hơn 0"
                );
            }

            Instant issuedAt = clock.instant();
            Instant expiresAt = issuedAt.plus(validity);
            return new AccessToken(id, issuedAt, expiresAt);
        }

        boolean isExpired(AccessToken token) {
            Objects.requireNonNull(token, "token");
            Instant now = clock.instant();
            return !now.isBefore(token.expiresAt());
        }
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-27T10:00:00Z");

        Clock frozen = Clock.fixed(start, ZoneOffset.UTC);
        AccessToken token = new TokenService(frozen).issue(
            "T-01", Duration.ofMinutes(5)
        );

        Clock before = Clock.offset(
            frozen, Duration.ofMinutes(4)
        );
        Clock exactlyAtDeadline = Clock.offset(
            frozen, Duration.ofMinutes(5)
        );
        Clock after = Clock.offset(
            frozen, Duration.ofMinutes(6)
        );

        boolean beforeExpired =
            new TokenService(before).isExpired(token);
        boolean exactExpired =
            new TokenService(exactlyAtDeadline).isExpired(token);
        boolean afterExpired =
            new TokenService(after).isExpired(token);

        System.out.println("Issued: " + token.issuedAt());
        System.out.println("Expires: " + token.expiresAt());
        System.out.println("Before: " + beforeExpired);
        System.out.println("At deadline: " + exactExpired);
        System.out.println("After: " + afterExpired);

        if (beforeExpired || !exactExpired || !afterExpired) {
            throw new AssertionError("Sai quy tắc hết hạn");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 27:

~~~bash
javac ClockTokenDemo.java
java ClockTokenDemo
~~~

Kết quả:

~~~text
Issued: 2026-11-27T10:00:00Z
Expires: 2026-11-27T10:05:00Z
Before: false
At deadline: true
After: true
~~~

Đây là **kiểm thử xác định**, vì toàn bộ thời điểm đều đến từ những Clock do test chủ động tạo. Không cần đợi năm phút và không phụ thuộc thời điểm người chạy bấm nút.

### 6.1. Những gì ví dụ thể hiện

1. **TokenService** không gọi **Instant.now()** trực tiếp.
2. Thời điểm phát hành được lấy bằng **clock.instant()** đúng một lần.
3. **expiresAt** được tính từ chính thời điểm đó bằng **Duration**.
4. **Clock.fixed** tạo điểm bắt đầu kiểm thử ổn định.
5. **Clock.offset** mô phỏng các mốc trước, đúng và sau hạn.
6. Ba trường hợp kiểm tra điều kiện biên bằng cùng dữ liệu token.
7. Quy tắc dấu **>=** được thể hiện rõ bằng **!now.isBefore(expiresAt)**.

Với dịch vụ tạo token thật, việc phát hành phải lưu record hoặc dữ liệu tương đương ở nơi an toàn, phù hợp yêu cầu hệ thống. Ví dụ này chỉ minh họa **thời gian và kiểm thử**, không tự biến một chuỗi token thành cơ chế xác thực bảo mật hoàn chỉnh.

### 6.2. Vì sao không lấy now hai lần?

Không nên viết:

~~~java
// Tránh: đọc đồng hồ hai lần cho hai mốc của cùng giao dịch.
Instant issuedAt = clock.instant();
Instant expiresAt = clock.instant().plus(Duration.ofMinutes(5));
~~~

Với Clock chạy thật, thời gian có thể tiến lên giữa hai lần gọi, khiến hiệu lực thực tế không đúng chính xác khoảng mong muốn tính từ **issuedAt**.

Ưu tiên:

~~~java
Instant issuedAt = clock.instant();
Instant expiresAt = issuedAt.plus(Duration.ofMinutes(5));
~~~

Một operation nên chụp **một thời điểm tham chiếu** khi những quyết định cần có tính nhất quán.

## 7. Kiểm thử ranh giới ngày và múi giờ

Nếu yêu cầu là **“báo cáo hôm nay tại Hà Nội”**, thì dùng **LocalDate.now(clock)** với múi giờ của Hà Nội, không phải ngày UTC hoặc ngày mặc định của server.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

Instant instant = Instant.parse("2026-12-31T17:30:00Z");

Clock utc = Clock.fixed(instant, ZoneId.of("UTC"));
Clock vietnam = Clock.fixed(
    instant, ZoneId.of("Asia/Ho_Chi_Minh")
);

System.out.println(LocalDate.now(utc));
System.out.println(LocalDate.now(vietnam));
~~~

Kết quả:

~~~text
2026-12-31
2027-01-01
~~~

Bằng một kiểm thử, ta có thể chứng minh hệ thống xử lý đúng khoảnh khắc chuyển năm tại Việt Nam.

### 7.1. withZone không làm thay đổi thời điểm

~~~java
Clock vietnam = Clock.fixed(
    Instant.parse("2026-12-31T17:30:00Z"),
    ZoneId.of("Asia/Ho_Chi_Minh")
);

Clock utc = vietnam.withZone(ZoneId.of("UTC"));

System.out.println(vietnam.instant().equals(utc.instant()));
System.out.println(LocalDate.now(vietnam));
System.out.println(LocalDate.now(utc));
~~~

Kết quả:

~~~text
true
2027-01-01
2026-12-31
~~~

**withZone** trả Clock mới có cách diễn giải ngày/giờ khác, không “đẩy” một **Instant** sang thời điểm khác. Đây là khác biệt quan trọng với **Clock.offset**.

### 7.2. Không dùng múi giờ ngầm định cho luật nghiệp vụ

Mã dễ sai:

~~~java
static boolean canPublish(LocalDate publishDate) {
    return !publishDate.isAfter(LocalDate.now());
}
~~~

Mã tốt hơn:

~~~java
static boolean canPublish(
    LocalDate publishDate,
    Clock businessClock
) {
    LocalDate today = LocalDate.now(businessClock);
    return !publishDate.isAfter(today);
}
~~~

Với việc phát hành theo một quốc gia hoặc doanh nghiệp, múi giờ kinh doanh nên được cấu hình tường minh. Nếu cùng hệ thống phục vụ nhiều vùng, **ZoneId** có thể được chọn từ cấu hình người dùng hoặc đơn vị kinh doanh đã được kiểm tra tính hợp lệ.

## 8. Duration, Period và thay đổi giờ mùa hè (DST)

Hai quy tắc “sau 24 giờ” và “cùng giờ ngày mai” **không luôn tương đương** ở vùng có thay đổi giờ mùa hè (*Daylight Saving Time – DST*).

- **Duration.ofHours(24)** diễn đạt khoảng thời gian 24 giờ trên trục thời gian.
- **plusDays(1)** trên **ZonedDateTime** diễn đạt cộng một ngày theo lịch địa phương, có xét quy tắc múi giờ.

Ví dụ kiểm thử khi châu Âu chuyển sang giờ mùa hè, với **Europe/Berlin**:

~~~java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

ZoneId berlin = ZoneId.of("Europe/Berlin");

ZonedDateTime start = ZonedDateTime.of(
    2026, 3, 28, 12, 0, 0, 0, berlin
);

ZonedDateTime nextCalendarDay = start.plusDays(1);
ZonedDateTime after24Hours = start.plus(Duration.ofHours(24));

System.out.println(start);
System.out.println(nextCalendarDay);
System.out.println(after24Hours);
~~~

Kết quả:

~~~text
2026-03-28T12:00+01:00[Europe/Berlin]
2026-03-29T12:00+02:00[Europe/Berlin]
2026-03-29T13:00+02:00[Europe/Berlin]
~~~

Ngày 29/03/2026 tại Berlin là ngày chuyển sang giờ mùa hè. Do đó, khoảng từ 12:00 ngày 28 đến 12:00 ngày 29 theo giờ địa phương chỉ dài **23 giờ** trên trục thời gian, không phải 24 giờ.

**Quy tắc thiết kế:**

- Với token hết hạn sau **5 phút**, timeout sau **30 giây**, cache TTL: ưu tiên **Instant** và **Duration**.
- Với lịch họp lúc **09:00 mỗi ngày**, đến hạn vào **đầu ngày làm việc kế tiếp**: dùng **LocalDate/ZonedDateTime** và quy tắc lịch tại **ZoneId** phù hợp.
- Với phép cộng tháng/năm theo lịch, cân nhắc **Period** hoặc **plusMonths/plusYears**, vì độ dài tháng không cố định.

**Clock** cho phép khóa mốc “hiện tại” khi kiểm thử; còn **ZoneId**, **Duration** và **Period** cho phép biểu diễn đúng ý nghĩa của quy tắc thời gian.

## 9. Đồng hồ thời gian thực không phải đồng hồ đo thời lượng đơn điệu

Một ngộ nhận phổ biến là có thể đo thời gian chạy chính xác bằng hiệu giữa hai lần **clock.instant()**.

~~~java
// Không nên dùng như đồng hồ đo timeout có yêu cầu đơn điệu.
Instant started = clock.instant();
doWork();
Duration elapsed = Duration.between(started, clock.instant());
~~~

Đồng hồ hệ thống có thể bị điều chỉnh, đồng bộ lại hoặc có độ phân giải hữu hạn. Tài liệu **Clock** và **Instant** không đảm bảo thời điểm trả về tiến lên đều đặn hoặc đơn điệu. Với **Clock.fixed**, hiệu hai lần đọc thậm chí luôn là 0.

Khi đo **thời lượng đã trôi qua** trong cùng một tiến trình, có thể dùng **System.nanoTime()**:

~~~java
long started = System.nanoTime();

doWork();

long elapsedNanos = System.nanoTime() - started;
System.out.println("Elapsed nanos: " + elapsedNanos);
~~~

**System.nanoTime()** được thiết kế để đo hiệu thời gian giữa các lần gọi, không phải để tạo timestamp theo UTC. Giá trị tuyệt đối của nó không tương ứng với epoch 1970 và không nên lưu làm thời gian sự kiện.

| Câu hỏi | Lựa chọn |
|---|---|
| Sự kiện xảy ra vào lúc nào? | **Instant** từ Clock |
| Hôm nay tại Hà Nội là ngày nào? | **LocalDate.now(clockWithBusinessZone)** |
| Mã đã đến hạn theo timestamp chưa? | So sánh **Instant** |
| Đo tác vụ chạy mất bao nhiêu thời gian? | Hiệu **System.nanoTime()** |
| Chạy một công việc sau khoảng chờ? | Cơ chế lập lịch/hẹn giờ thích hợp, không phải **Clock.tick** |

Khi thiết kế hệ thống cần mô phỏng cả việc chờ, timeout và bộ lập lịch trong test, có thể cần thêm một abstraction cho **scheduler** hoặc **ticker**. Chỉ inject Clock không khiến các lời gọi chờ thực như **Thread.sleep** được mô phỏng tự động.

## 10. Tách thời gian khỏi hiệu ứng phụ của logic nghiệp vụ

Một cải tiến tiếp theo là phân biệt **lấy thời gian** với **ra quyết định dựa trên thời gian**.

Thiết kế trực tiếp, phù hợp dịch vụ nhỏ:

~~~java
static boolean overdue(Instant dueAt, Clock clock) {
    return !clock.instant().isBefore(dueAt);
}
~~~

Thiết kế tách decision function để dễ thử nhiều giá trị:

~~~java
static boolean overdueAt(Instant dueAt, Instant now) {
    return !now.isBefore(dueAt);
}

static boolean overdue(Instant dueAt, Clock clock) {
    Instant now = clock.instant();
    return overdueAt(dueAt, now);
}
~~~

Bản thân **overdueAt** là hàm thuần theo dữ liệu đầu vào: không truy cập hệ thống, không phụ thuộc múi giờ, không gây hiệu ứng phụ. Nó có thể được kiểm tra bằng những trường hợp xác định mà không cần fake Clock.

**Clock injection** phù hợp khi logic cần lấy thời gian nhiều lần trong một service. **Truyền Instant now** phù hợp khi logic chỉ cần một mốc đã được lấy ở ranh giới gọi. Hai cách bổ sung cho nhau.

### 10.1. Một thời điểm cho toàn bộ transaction logic

Khi xử lý một yêu cầu, nếu cần kiểm tra nhiều quy tắc cùng lúc:

~~~java
Instant now = clock.instant();

boolean expired = !now.isBefore(token.expiresAt());
boolean published = !now.isBefore(article.publishAt());
boolean eventStarted = !now.isBefore(event.startsAt());
~~~

Dùng một **now** làm các quyết định nhất quán trong phạm vi thao tác đó. Nếu mỗi điều kiện tự đọc Clock, một yêu cầu chạy đúng gần ranh giới có thể quan sát hai “thời điểm hiện tại” khác nhau.

### 10.2. Đưa Clock vào interface nghiệp vụ, không vào dữ liệu lưu trữ

Nên phân biệt:

- **Clock**: nguồn thời gian dành cho logic chạy.
- **Instant createdAt / expiresAt**: dữ liệu lưu và trao đổi.
- **ZoneId businessZone**: chính sách diễn giải ngày/giờ của nghiệp vụ.

Không nên lưu nguyên một đối tượng Clock vào bản ghi cơ sở dữ liệu thay cho mốc thời gian cụ thể. Clock có thể là đồng hồ chạy thật, fixed, offset hoặc một custom implementation; nó không thay thế dữ liệu sự kiện.

## 11. Khi chỉ cần Instant: InstantSource

Từ Java 17, JDK có **java.time.InstantSource**. **Clock** triển khai interface này. Nếu service chỉ cần mốc thời gian mà không quan tâm múi giờ, có thể nhận **InstantSource** thay vì Clock:

~~~java
import java.time.Instant;
import java.time.InstantSource;
import java.util.Objects;

final class EventStampService {
    private final InstantSource timeSource;

    EventStampService(InstantSource timeSource) {
        this.timeSource = Objects.requireNonNull(timeSource);
    }

    Instant stamp() {
        return timeSource.instant();
    }
}
~~~

Chạy thật:

~~~java
EventStampService service =
    new EventStampService(InstantSource.system());
~~~

Kiểm thử:

~~~java
Instant fixedTime = Instant.parse("2026-11-27T10:00:00Z");

EventStampService service =
    new EventStampService(InstantSource.fixed(fixedTime));

if (!service.stamp().equals(fixedTime)) {
    throw new AssertionError("Sai mốc thời gian");
}
~~~

**InstantSource** có các factory **system**, **fixed**, **offset**, **tick** và method **withZone** tạo Clock khi cần. Dùng nó để biểu đạt ý định rõ: service **chỉ cần Instant**, không cần truy cập **ZoneId**.

| Nhu cầu | Kiểu phụ thuộc phù hợp |
|---|---|
| Chỉ cần thời điểm UTC/epoch, không cần quy tắc ngày địa phương | **InstantSource** |
| Cần **LocalDate.now(clock)** hoặc chuyển Instant theo múi giờ | **Clock** |
| Chỉ cần một mốc thời gian đã được tính ở nơi gọi | **Instant** làm tham số |

Cả **Clock** và **InstantSource** đều là API chính thức của Java 27; không cần thư viện fake clock bên ngoài cho những kiểm thử đơn giản.

## 12. Kiểm thử theo bảng trường hợp biên

Đừng chỉ kiểm thử trường hợp “sau hạn một giờ”. Các lỗi thời gian thường xảy ra **ngay tại ranh giới**.

Xét mốc hết hạn **2026-11-27T10:05:00Z**:

| Thời điểm kiểm tra | Kết quả mong đợi nếu now >= expiresAt |
|---|---|
| 2026-11-27T10:04:59.999999999Z | Chưa hết hạn |
| 2026-11-27T10:05:00Z | Hết hạn |
| 2026-11-27T10:05:00.000000001Z | Hết hạn |
| 2026-11-27T10:06:00Z | Hết hạn |

Với Clock fixed, có thể kiểm tra từng hàng độc lập:

~~~java
Instant deadline = Instant.parse("2026-11-27T10:05:00Z");

Clock before = Clock.fixed(
    deadline.minusNanos(1), ZoneOffset.UTC
);
Clock at = Clock.fixed(deadline, ZoneOffset.UTC);
Clock after = Clock.fixed(
    deadline.plusNanos(1), ZoneOffset.UTC
);

if (!before.instant().isBefore(deadline)) {
    throw new AssertionError("Trước hạn phải hợp lệ");
}

if (at.instant().isBefore(deadline)) {
    throw new AssertionError("Đúng hạn phải hết hiệu lực");
}

if (after.instant().isBefore(deadline)) {
    throw new AssertionError("Sau hạn phải hết hiệu lực");
}
~~~

Ví dụ dùng các câu lệnh kiểm tra cơ bản để không lệ thuộc thư viện kiểm thử. Trong dự án thực, các trường hợp có thể được viết thành parameterized tests của framework kiểm thử đang sử dụng.

### 12.1. Những kịch bản khác nên có

- Trước, đúng và sau hạn theo nano giây hoặc mili giây.
- Chuyển từ cuối ngày sang ngày mới tại múi giờ nghiệp vụ.
- Cuối tháng: 31/01 sang tháng 02; năm nhuận và năm không nhuận.
- Thời điểm chuyển năm, như **31/12** sang **01/01**.
- Giờ bị bỏ qua và giờ bị lặp lại tại vùng có DST.
- Múi giờ của người dùng khác múi giờ server.
- Clock fixed và Clock offset cho kết quả khác nhau đúng như mong đợi.
- Nhiều điều kiện cùng dùng một Instant “now” trong một operation.

## 13. Khi cần điều khiển thời gian tiến dần trong test

**Clock.fixed** luôn đứng yên. Nếu bài kiểm thử cần mô phỏng nhiều lời gọi trên **cùng một instance dịch vụ** và chủ động tiến thời gian, có thể:

1. Tạo dịch vụ mới với **Clock.offset(fixed, duration)** ở mỗi giai đoạn.
2. Truyền **Instant now** trực tiếp cho decision function.
3. Tạo một fake Clock có thể thay đổi, nếu hợp đồng thực sự yêu cầu trạng thái thời gian tiến dần trong cùng dịch vụ.

Ví dụ một fake Clock đơn giản nhưng có đồng bộ cho nhiều luồng:

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

    AdjustableClock(Instant start, ZoneId zone) {
        this(new AtomicReference<>(Objects.requireNonNull(start)), zone);
    }

    private AdjustableClock(
        AtomicReference<Instant> current,
        ZoneId zone
    ) {
        this.current = current;
        this.zone = Objects.requireNonNull(zone);
    }

    void advance(Duration delta) {
        Objects.requireNonNull(delta, "delta");
        current.updateAndGet(instant -> instant.plus(delta));
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new AdjustableClock(current, newZone);
    }
}
~~~

Sử dụng trong test:

~~~java
AdjustableClock fake = new AdjustableClock(
    Instant.parse("2026-11-27T10:00:00Z"),
    ZoneOffset.UTC
);

TokenService service = new TokenService(fake);
AccessToken token = service.issue(
    "T-01", Duration.ofMinutes(5)
);

System.out.println(service.isExpired(token)); // false

fake.advance(Duration.ofMinutes(5));
System.out.println(service.isExpired(token)); // true
~~~

Trong ví dụ này, **TokenService** và **AccessToken** là các kiểu được định nghĩa ở phần 6; nếu chạy riêng cần đặt đoạn dùng fake vào cùng phạm vi hoặc điều chỉnh các khai báo cho phù hợp.

Custom Clock phải bảo đảm các method **instant()**, **getZone()** và **withZone()** nhất quán, triển khai thread-safe khi dùng đồng thời. Với **AtomicReference** trong ví dụ, các bản Clock tạo bởi **withZone** dùng chung trạng thái thời điểm nhưng có múi giờ riêng.

Chỉ viết fake Clock riêng khi cần. Với hầu hết kiểm thử ranh giới độc lập, **Clock.fixed** và **Clock.offset** đơn giản, ít lỗi hơn.

## 14. Quy tắc thiết kế ứng dụng thực tế

### 14.1. Tạo Clock tại ranh giới cấu hình

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
Clock businessClock = Clock.system(businessZone);

BillingService billing = new BillingService(businessClock);
~~~

Trong ví dụ định hướng thiết kế này, **BillingService** là service nghiệp vụ của ứng dụng, không phải lớp có sẵn trong JDK. Khi tạo instance để kiểm thử, thay **businessClock** bằng Clock fixed có cùng múi giờ.

Nếu chương trình có nhiều múi giờ người dùng, nên truyền **ZoneId** riêng theo ngữ cảnh yêu cầu và tránh cấu hình một Clock toàn cục dùng sai vùng cho mọi khách hàng.

### 14.2. Ghi sự kiện bằng Instant, diễn giải ngày theo ZoneId

~~~java
Instant eventAt = clock.instant();

ZoneId userZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate dateForUser = eventAt.atZone(userZone).toLocalDate();
~~~

Như vậy, cùng một sự kiện có thể hiển thị đúng cho nhiều múi giờ mà không làm mất mốc thời gian tuyệt đối.

### 14.3. Đặt ngữ nghĩa của ranh giới thành quy tắc rõ ràng

Đối với một hạn chót, hai cách diễn giải thường gặp:

- **Còn hiệu lực nếu now < deadline**; hết hiệu lực tại **now == deadline**.
- **Còn hiệu lực nếu now <= deadline**; hết hiệu lực chỉ khi **now > deadline**.

Cả hai đều có thể là yêu cầu nghiệp vụ hợp lệ. Hãy chọn một quy tắc, viết nó thành method có tên rõ ràng và kiểm thử ngay điểm bằng nhau.

### 14.4. Không coi đồng hồ hệ thống là nguồn thời gian đáng tin cậy cho bảo mật

Clock injection làm code dễ kiểm thử, nhưng không giải quyết vấn đề xác thực độ tin cậy của nguồn thời gian. Trong một hệ thống có yêu cầu bảo mật cao, đồng hồ máy chủ có thể bị lệch và hệ thống phân tán có thể có sai khác thời gian.

Cần xử lý hợp đồng về **clock skew**, nguồn đồng hồ đáng tin cậy, độ trễ mạng và nơi lưu dấu thời gian. Không để client tự chọn mốc **now** làm cơ sở quyết định quyền truy cập ở server.

## 15. Những lỗi và hiểu nhầm thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Gọi **Instant.now()** rải rác trong service | Khó test, thời gian quan sát không nhất quán | Inject Clock hoặc truyền **Instant now** |
| Sử dụng **LocalDate.now()** không tham số trong nghiệp vụ nhiều múi giờ | Ngày phụ thuộc múi giờ máy chạy | Dùng **LocalDate.now(clock)** với zone xác định |
| Tạo Clock fixed rồi dùng **Thread.sleep** để chờ fake time tiến | Thời gian fake không thay đổi | Dùng offset, fake clock có advance hoặc test theo Instant |
| Nhầm **withZone** là cộng/trừ số giờ vào Instant | Sai ý nghĩa thời gian | withZone đổi cách diễn giải, **offset** đổi Instant |
| Dùng **Clock.tick** để hẹn giờ hoặc bảo đảm độ chính xác | Nhịp chỉ thay đổi giá trị trả về, có thể có cache | Dùng scheduler/ticker phù hợp |
| Dùng **clock.instant()** để benchmark | Clock không bảo đảm đơn điệu | Dùng hiệu **System.nanoTime()** |
| Trừ **LocalDateTime** để đo TTL qua DST | Có thể lệch với thời lượng thực | Dùng **Instant** và **Duration** |
| Dùng **Duration.ofDays(1)** cho “cùng giờ ngày mai” ở vùng DST | Có thể thành 13:00 thay vì 12:00 | Dùng **ZonedDateTime.plusDays(1)** |
| Đọc Clock nhiều lần trong một transaction | Có thể quan sát thời điểm khác nhau | Chụp một Instant tham chiếu |
| Không kiểm thử thời điểm đúng deadline | Lỗi sai một dấu **>=** hoặc **>** | Kiểm thử trước / bằng / sau hạn |
| Dựa vào **ZoneId.systemDefault()** trong server | Hành vi thay đổi theo môi trường triển khai | Chỉ định ZoneId từ cấu hình nghiệp vụ |
| Giữ Clock làm dữ liệu timestamp | Không biểu diễn một thời điểm đã xảy ra | Lưu **Instant** |
| Để client gửi “thời gian hiện tại” nhằm xác định hết hạn token | Rủi ro tin nguồn thời gian không đáng tin | Dựa trên thời gian do phía tin cậy quyết định |
| Viết custom Clock không thread-safe | Test không ổn định khi chạy song song | Ưu tiên factory chuẩn hoặc dùng đồng bộ đúng cách |

## 16. Bài thực hành đề xuất

Thiết kế một **ReservationService** nhận **Clock** qua constructor. Một chỗ đặt được giữ tối đa 15 phút. Dữ liệu đặt chỗ là record:

~~~java
record Reservation(
    String reservationId,
    Instant reservedAt,
    Instant expiresAt
) {}
~~~

Yêu cầu:

1. Method **reserve(id)** lấy thời gian từ Clock và đặt **expiresAt = now.plus(Duration.ofMinutes(15))**.
2. Method **isExpired(reservation)** trả **true** khi **now >= expiresAt**.
3. Không có lời gọi trực tiếp **Instant.now()** trong service.
4. Viết test dùng **Clock.fixed**, kiểm tra còn hiệu lực ở phút 14, hết hiệu lực đúng phút 15 và sau phút 16.
5. Thêm method **reservationDate(ZoneId)** để trả về ngày địa phương của **reservedAt** theo múi giờ được cung cấp.
6. Kiểm tra đặt chỗ lúc **2026-12-31T17:30:00Z** có ngày đặt chỗ là **2027-01-01** tại **Asia/Ho_Chi_Minh**.

Gợi ý cho method ngày địa phương:

~~~java
LocalDate reservationDate(
    Reservation reservation,
    ZoneId zone
) {
    return reservation.reservedAt()
        .atZone(zone)
        .toLocalDate();
}
~~~

Mục tiêu bài thực hành là thiết kế một service mà mọi thời điểm đều có thể tái tạo trong kiểm thử, đồng thời xử lý đúng mốc tuyệt đối và ngày/giờ địa phương.

## 17. Ghi nhớ

- **Clock** là nguồn thời gian có thể inject, giúp tách code nghiệp vụ khỏi đồng hồ hệ thống.
- **Clock.systemUTC()** phù hợp cho các mốc thời gian server; **Clock.system(zone)** phục vụ các quy tắc ngày/giờ gắn với múi giờ cụ thể.
- **Clock.fixed(instant, zone)** trả mãi một Instant, là công cụ kiểm thử ranh giới quan trọng.
- **Clock.offset(base, duration)** dịch thời điểm của Clock gốc; không đồng nghĩa với đổi múi giờ.
- **Clock.withZone(zone)** đổi cách diễn giải ngày/giờ mà giữ cùng nguồn thời điểm.
- **Clock.tick** dùng cho độ phân giải quan sát, không phải bộ lập lịch.
- **Instant.now(clock)** và **LocalDate.now(clock)** giúp tận dụng Clock injection trực tiếp trong API java.time.
- Với TTL và hạn hết hiệu lực sau một khoảng thời lượng, ưu tiên **Instant + Duration**.
- Với ngày/giờ lịch địa phương, cần **ZoneId** và đôi khi phải phân biệt **Duration** với **Period** hoặc **plusDays**.
- Khi kiểm tra deadline, phải xác định rõ giá trị bằng deadline có bị coi là hết hạn không.
- Đo thời lượng chạy bằng hiệu **System.nanoTime()**, không dùng Clock như đồng hồ đơn điệu.
- Nếu chỉ cần một mốc thời gian, có thể inject **InstantSource**, interface chính thức từ Java 17 và vẫn áp dụng trên Java 27.
- Những bài kiểm thử tốt nên kiểm tra trước, đúng và sau hạn mà không cần **Thread.sleep** hay chỉnh thời gian hệ thống.

## Tài liệu tham khảo

- [Java SE 27 API — Clock](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Clock.html)
- [Java SE 27 API — InstantSource](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/InstantSource.html)
- [Java SE 27 API — Instant](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html)
- [Java SE 27 API — LocalDate](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/LocalDate.html)
- [Java SE 27 API — ZonedDateTime](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZonedDateTime.html)
- [Java SE 27 API — ZoneId](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/ZoneId.html)
- [Java SE 27 API — Duration](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Duration.html)
- [Java SE 27 API — Period](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Period.html)
- [Java SE 27 API — System.nanoTime()](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html#nanoTime())
