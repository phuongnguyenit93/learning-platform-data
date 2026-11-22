# ZonedDateTime và quy tắc lịch địa phương trong Java

**Chủ đề:** Java 8 → Múi giờ → ZonedDateTime và quy tắc lịch địa phương.

**java.time.ZonedDateTime** biểu diễn **ngày và giờ địa phương đi kèm một múi giờ vùng (ZoneId)**, cùng **UTC offset hợp lệ tại thời điểm đó**. Nhờ có quy tắc múi giờ, một ZonedDateTime có thể quy đổi thành **Instant**, đồng thời giữ được thông tin lịch địa phương cần cho lịch hẹn, giờ mở cửa, phiên làm việc và những sự kiện diễn ra theo thời gian dân sự.

Ví dụ tại Việt Nam:

~~~text
2026-01-02T09:30+07:00[Asia/Ho_Chi_Minh]
│          │     │      └── ZoneId: khu vực có quy tắc lịch sử
│          │     └───────── Offset có hiệu lực tại thời điểm này
│          └─────────────── Giờ địa phương
└────────────────────────── Ngày địa phương theo lịch ISO
~~~

Cùng thời điểm có thể hiển thị **03:30 tại Paris** vào ngày 2/1/2026; khác giờ đồng hồ nhưng không khác Instant. Điểm cần nắm sâu hơn là: **không phải mọi ngày-giờ địa phương đều có đúng một Instant**. Khi zone thay đổi offset (chuyển giờ mùa hè, thay đổi chính sách), một giờ địa phương có thể **không tồn tại (gap)** hoặc **xảy ra hai lần (overlap)**.

**ZonedDateTime thuộc java.time từ Java 8 và vẫn dùng trong Java hiện đại.** Các ví dụ độc lập được viết cho **Java 17+**. Kiến thức bên dưới dựa trên đặc tả Java hiện hành, không dùng API ngày giờ cũ làm giải pháp mặc định.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **LocalDateTime**, **ZoneId**, **ZoneOffset**, **ZonedDateTime**, **OffsetDateTime** và **Instant**.
2. Tạo ZonedDateTime từ ngày-giờ địa phương hoặc Instant; đọc **getZone()**, **getOffset()**, **toInstant()**.
3. Giải thích ba trạng thái của **ZoneRules.getValidOffsets(localDateTime)**: có **một**, **không có**, hoặc **hai offset**.
4. Hiểu cách mặc định của **atZone(...)**, **ZonedDateTime.of(...)** khi gặp gap/overlap, và biết cách chọn offset hoặc từ chối dữ liệu không rõ ràng.
5. So sánh **withZoneSameInstant(...)** và **withZoneSameLocal(...)**; tránh vô tình thay đổi thời điểm của sự kiện.
6. Phân biệt phép tính **plusDays/plusMonths** trên lịch địa phương và **plusHours/Duration** trên timeline.
7. Dùng **Clock.fixed(...)** để kiểm thử, **DateTimeFormatter** để parse/format, và Instant cho dấu thời gian sự kiện.
8. Thiết kế dữ liệu lịch hẹn có múi giờ, hiểu sự thay đổi của quy tắc timezone và tránh dùng offset cố định thay cho vùng.
9. Nhận diện những lỗi liên quan đến DST, trùng giờ, thiếu giờ, sắp xếp, so sánh, serialization và lưu trữ.

## 2. ZonedDateTime gồm những gì?

Về mô hình, ZonedDateTime kết hợp:

- **LocalDateTime:** ngày-giờ địa phương theo lịch ISO, ví dụ **2026-01-02T09:30**.
- **ZoneId:** tên vùng có quy tắc múi giờ, ví dụ **Asia/Ho_Chi_Minh**, **Europe/Paris** hoặc **America/New_York**.
- **ZoneOffset:** độ lệch UTC cụ thể có hiệu lực tại ngày giờ đó, ví dụ **+07:00** hoặc **-05:00**.

Trong ZonedDateTime, **offset có vai trò xác định Instant**, nhất là khi một LocalDateTime xuất hiện hai lần trong overlap. ZoneId còn cung cấp thông tin cho các phép tính lịch trong tương lai và quy tắc vùng.

### 2.1. So sánh các kiểu java.time

| Kiểu Java | Có ngày? | Có giờ? | Có ZoneId vùng? | Xác định một Instant? |
|---|---|---|---|---|
| **LocalDate** | Có | Không | Không | Không |
| **LocalTime** | Không | Có | Không | Không |
| **LocalDateTime** | Có | Có | Không | **Không**, nếu thiếu offset/zone |
| **OffsetDateTime** | Có | Có | Không, chỉ có offset | **Có** |
| **ZonedDateTime** | Có | Có | **Có** | **Có** |
| **Instant** | Không lưu các trường ngày/giờ địa phương | Không | Không | **Chính là** điểm trên timeline |

**Ví dụ sử dụng:**

- **Ngày sinh:** LocalDate, không tự gán múi giờ.
- **Giờ mở cửa 09:00 mỗi ngày:** LocalTime, kèm zone riêng ở cấp cửa hàng.
- **Lịch họp 09:00 tại Paris:** LocalDateTime/LocalTime và ZoneId, có quy tắc xử lý DST.
- **Mốc tạo đơn hàng:** Instant, không phụ thuộc múi giờ người xem.
- **Ngày-giờ một sự kiện ở Tokyo:** ZonedDateTime, khi cần cả lịch địa phương lẫn khả năng đổi sang Instant.
- **Timestamp có offset từ hệ thống ngoài:** OffsetDateTime nếu chỉ có offset và không có vùng timezone.

### 2.2. ZoneId khác ZoneOffset

**ZoneOffset** là một độ lệch cố định như **+07:00** hoặc **-04:00**. **ZoneId** vùng như **America/New_York** là định danh liên kết tới các quy tắc offset qua lịch sử và tương lai.

~~~text
ZoneOffset.ofHours(7)              -> +07:00 (độ lệch cố định)
ZoneId.of("Asia/Ho_Chi_Minh")     -> vùng với quy tắc timezone
ZoneId.of("America/New_York")     -> vùng có DST trong nhiều năm
~~~

**Không thay tên vùng bằng offset** chỉ vì chúng đang có cùng độ lệch tại thời điểm hiện tại. Chẳng hạn New York có thể là **-05:00** trong mùa đông và **-04:00** trong mùa hè. Nếu đặt lịch tương lai theo giờ địa phương của New York, lưu mỗi **-05:00** sẽ làm mất quy tắc tự đổi offset.

**ZoneId.of("UTC")** hoặc **ZoneOffset.UTC** phù hợp khi nghiệp vụ thật sự dùng UTC; không mặc định mọi lịch hẹn trên thế giới đều là UTC.

## 3. Tạo ZonedDateTime và đọc các trường

Các cách tạo cơ bản:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime a = ZonedDateTime.of(
        2026, 1, 2, 9, 30, 0, 0, zone);

ZonedDateTime b = LocalDateTime.of(
        2026, 1, 2, 9, 30).atZone(zone);

Instant event = Instant.parse(
        "2026-01-02T02:30:00Z");

ZonedDateTime c = event.atZone(zone);
~~~

Đây là **đoạn minh họa**, cần import **java.time.\*** trong một chương trình hợp lệ. Với dữ liệu và quy tắc múi giờ của ví dụ, **a**, **b**, **c** đều biểu diễn cùng ngày-giờ và cùng Instant.

Những phương thức nên biết:

| API | Kết quả | Ý nghĩa |
|---|---|---|
| **ZonedDateTime.of(localDateTime, zone)** | ZonedDateTime | Giải quyết ngày-giờ cục bộ theo zone rules |
| **localDateTime.atZone(zone)** | ZonedDateTime | Cách viết tiện lợi, có cùng chính sách giải quyết mặc định |
| **instant.atZone(zone)** | ZonedDateTime | Xem một Instant đã biết theo múi giờ vùng |
| **ZonedDateTime.ofInstant(instant, zone)** | ZonedDateTime | Tạo từ điểm timeline và zone |
| **zdt.getZone()** | ZoneId | Vùng múi giờ |
| **zdt.getOffset()** | ZoneOffset | Offset cụ thể đang dùng |
| **zdt.toLocalDateTime()** | LocalDateTime | Ngày giờ địa phương, bỏ zone/offset |
| **zdt.toLocalDate()** | LocalDate | Ngày địa phương |
| **zdt.toLocalTime()** | LocalTime | Giờ địa phương |
| **zdt.toInstant()** | Instant | Điểm tuyệt đối trên timeline |

**Điểm dễ nhầm:** **toLocalDateTime()** là phép chiếu dữ liệu từ ZonedDateTime sang ngày-giờ **không có zone**. Nếu chỉ lưu kết quả LocalDateTime rồi xóa thông tin ZoneId và offset, sau này có thể không khôi phục chính xác Instant tại những thời điểm DST overlap.

### 3.1. Chương trình đầy đủ: tạo và chuyển múi giờ

Lưu thành **ZonedDateTimeBasicsDemo.java**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ZonedDateTimeBasicsDemo {
    public static void main(String[] args) {
        ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
        ZoneId paris = ZoneId.of("Europe/Paris");

        ZonedDateTime appointment = ZonedDateTime.of(
                2026, 1, 2, 9, 30, 0, 0, vietnam);

        Instant instant = appointment.toInstant();

        System.out.println("appointment=" + appointment);
        System.out.println("date=" + appointment.toLocalDate());
        System.out.println("time=" + appointment.toLocalTime());
        System.out.println("zone=" + appointment.getZone());
        System.out.println("offset=" + appointment.getOffset());
        System.out.println("instant=" + instant);

        ZonedDateTime parisView =
                appointment.withZoneSameInstant(paris);

        System.out.println("parisSameInstant=" + parisView);
        System.out.println("samePoint="
                + instant.equals(parisView.toInstant()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ZonedDateTimeBasicsDemo.java
java ZonedDateTimeBasicsDemo
~~~

**Stdout:**

~~~text
appointment=2026-01-02T09:30+07:00[Asia/Ho_Chi_Minh]
date=2026-01-02
time=09:30
zone=Asia/Ho_Chi_Minh
offset=+07:00
instant=2026-01-02T02:30:00Z
parisSameInstant=2026-01-02T03:30+01:00[Europe/Paris]
samePoint=true
~~~

**Diễn giải:** Cùng sự kiện ở Việt Nam lúc 09:30 tương ứng 03:30 tại Paris trong mùa đông. Giá trị Instant không đổi, vì **withZoneSameInstant** chỉ chuyển cách hiển thị của **cùng một điểm trên timeline**.

## 4. Quy tắc múi giờ: tại sao một giờ địa phương có thể không duy nhất?

**ZoneId.getRules()** trả một **ZoneRules** chứa các quy tắc offset của vùng. Chuyển từ **Instant → giờ địa phương** tương đối rõ ràng: tại một Instant có một offset hợp lệ cho zone.

Nhưng từ **LocalDateTime → Instant** có thể phức tạp:

~~~text
LocalDateTime + ZoneId
         │
         ▼
ZoneRules.getValidOffsets(localDateTime)
         │
         ├── 1 offset → NORMAL: giờ địa phương tồn tại một lần
         │
         ├── 0 offset → GAP: giờ địa phương không tồn tại
         │
         └── 2 offsets → OVERLAP: giờ địa phương lặp hai lần
~~~

**Gap:** đồng hồ tiến lên, ví dụ bỏ qua khoảng 02:00–02:59. Trong khoảng ấy **không có Instant hợp lệ** tương ứng với local time được nhập.

**Overlap:** đồng hồ lùi, ví dụ 01:00–01:59 xảy ra hai lần. Cùng **2024-11-03T01:30 tại New York** có thể tương ứng **hai Instant cách nhau 1 giờ**.

**Normal:** phần lớn ngày trong năm chỉ có một offset hợp lệ.

### 4.1. Vì sao API không thể cứ lấy offset hiện tại?

Offset có thể thay đổi theo **ngày và vùng**. Nếu hệ thống đang ở tháng 1 nhưng bạn đặt cuộc họp vào tháng 7 tại New York, offset tháng 1 không đủ để diễn giải lịch tháng 7.

**Không dùng ZoneId.systemDefault() một cách tùy tiện cho giờ của khách hàng** nếu nghiệp vụ đã biết người dùng ở khu vực khác. ZoneId mặc định của máy chạy ứng dụng không nhất thiết là ZoneId của sự kiện.

**Nên dùng region ZoneId được truyền theo nghiệp vụ** và quy tắc múi giờ hiện hành của JDK.

## 5. GAP: giờ địa phương không tồn tại

Vào ngày **10/3/2024**, New York chuyển từ giờ tiêu chuẩn **-05:00** sang giờ mùa hè **-04:00**. Đồng hồ nhảy từ khoảng **01:59:59** sang **03:00:00**. Vì thế thời điểm cục bộ:

~~~text
2024-03-10 02:30 tại America/New_York
~~~

**không tồn tại** theo quy tắc vùng ở ngày đó.

Theo hợp đồng của ZonedDateTime, khi tạo từ LocalDateTime có gap, cách giải quyết mặc định **đẩy ngày-giờ cục bộ tiến lên bằng độ dài gap**. Với gap một giờ:

~~~text
Nhập:      2024-03-10T02:30
Zone:      America/New_York
Kết quả:   2024-03-10T03:30-04:00[America/New_York]
~~~

Đây là chính sách mặc định của API, **không có nghĩa quy tắc nghiệp vụ của bạn nhất thiết muốn tự dời lịch hẹn**.

### 5.1. Ví dụ đầy đủ: phát hiện và giải quyết gap

Lưu thành **ZonedDateTimeGapDemo.java**:

~~~java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRules;

public class ZonedDateTimeGapDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");

        LocalDateTime missing =
                LocalDateTime.of(2024, 3, 10, 2, 30);

        ZoneRules rules = newYork.getRules();

        System.out.println("validOffsets="
                + rules.getValidOffsets(missing));

        System.out.println("isGap="
                + rules.getTransition(missing).isGap());

        ZonedDateTime resolved = missing.atZone(newYork);
        System.out.println("resolved=" + resolved);

        try {
            ZonedDateTime.ofStrict(
                    missing,
                    ZoneOffset.ofHours(-5),
                    newYork);
        } catch (DateTimeException exception) {
            System.out.println("strict=DateTimeException");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ZonedDateTimeGapDemo.java
java ZonedDateTimeGapDemo
~~~

**Stdout:**

~~~text
validOffsets=[]
isGap=true
resolved=2024-03-10T03:30-04:00[America/New_York]
strict=DateTimeException
~~~

**Giải thích:**

- **getValidOffsets(...)** trả danh sách rỗng vì **02:30 không hợp lệ** trong zone ngày đó.
- **getTransition(...).isGap()** là true; chỉ gọi **getTransition(...).isGap()** sau khi xác nhận đang ở thời điểm có transition, vì phương thức getTransition có thể trả **null** khi bình thường.
- **missing.atZone(newYork)** dùng cách giải quyết mặc định: chuyển lên **03:30**.
- **ZonedDateTime.ofStrict(...)** đòi offset đưa vào phải hợp lệ cho đúng ngày-giờ/zone. Vì gap không có offset hợp lệ nên ném **DateTimeException**.

### 5.2. Nên tự dịch giờ hay từ chối đặt lịch?

Tùy yêu cầu nghiệp vụ:

- **Lịch nhắc việc ít nghiêm ngặt:** có thể chấp nhận chính sách dời sang giờ hợp lệ gần nhất, nhưng cần thông báo rõ nếu giờ người dùng nhập đã đổi.
- **Đặt vé, đặt phòng, giao dịch tài chính, biểu mẫu đặt giờ hẹn:** nên phát hiện gap và yêu cầu người dùng chọn giờ khác hoặc áp dụng một chính sách nghiệp vụ đã công bố.
- **Tự động hóa chạy lúc 02:30 mỗi ngày:** phải quyết định điều gì xảy ra vào ngày 02:30 không tồn tại: bỏ lịch, chạy lúc 03:00, chạy lúc 03:30 hoặc một quy tắc khác.

**Không giả định mọi ngày có đầy đủ 24 giờ địa phương**; vùng có thể thay đổi offset vì DST hoặc quy định hành chính.

## 6. OVERLAP: một giờ địa phương có hai Instant

Ngày **3/11/2024**, New York lùi từ offset **-04:00** về **-05:00**. Vì vậy **01:30** xảy ra **hai lần**:

~~~text
2024-11-03T01:30-04:00[America/New_York]
     ↳ Instant: 2024-11-03T05:30:00Z

2024-11-03T01:30-05:00[America/New_York]
     ↳ Instant: 2024-11-03T06:30:00Z
~~~

Cùng LocalDateTime, cùng ZoneId, **nhưng hai Instant khác nhau một giờ**.

Theo hợp đồng tạo ZonedDateTime từ LocalDateTime:

- Khi **không có offset cũ** và cũng không có lựa chọn ưu tiên, thường chọn **offset sớm hơn** của overlap (thường là offset mùa hè).
- Khi **chuyển đổi/điều chỉnh từ một ZonedDateTime đã có**, có thể giữ **offset trước đó** nếu vẫn hợp lệ. Nếu không giữ được, mới dùng offset sớm hơn.
- **withEarlierOffsetAtOverlap()** và **withLaterOffsetAtOverlap()** cho phép chọn rõ hai nhánh.
- **ofStrict(localDateTime, offset, zone)** chọn offset được chỉ định, đồng thời kiểm tra nó hợp lệ.

### 6.1. Ví dụ đầy đủ: hai cách giải quyết overlap

Lưu thành **ZonedDateTimeOverlapDemo.java**:

~~~java
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class ZonedDateTimeOverlapDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");

        LocalDateTime repeated =
                LocalDateTime.of(2024, 11, 3, 1, 30);

        List<ZoneOffset> offsets =
                newYork.getRules().getValidOffsets(repeated);

        System.out.println("validOffsets=" + offsets);

        ZonedDateTime normalChoice =
                repeated.atZone(newYork);

        ZonedDateTime earlier =
                normalChoice.withEarlierOffsetAtOverlap();

        ZonedDateTime later =
                normalChoice.withLaterOffsetAtOverlap();

        System.out.println("earlier=" + earlier);
        System.out.println("later=" + later);
        System.out.println("earlierInstant="
                + earlier.toInstant());
        System.out.println("laterInstant="
                + later.toInstant());

        long hoursBetween = Duration.between(
                earlier.toInstant(),
                later.toInstant()).toHours();

        System.out.println("hoursBetween=" + hoursBetween);

        ZonedDateTime strictLater =
                ZonedDateTime.ofStrict(
                        repeated,
                        ZoneOffset.ofHours(-5),
                        newYork);

        System.out.println("strictLater=" + strictLater);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ZonedDateTimeOverlapDemo.java
java ZonedDateTimeOverlapDemo
~~~

**Stdout:**

~~~text
validOffsets=[-04:00, -05:00]
earlier=2024-11-03T01:30-04:00[America/New_York]
later=2024-11-03T01:30-05:00[America/New_York]
earlierInstant=2024-11-03T05:30:00Z
laterInstant=2024-11-03T06:30:00Z
hoursBetween=1
strictLater=2024-11-03T01:30-05:00[America/New_York]
~~~

**Diễn giải:** Nếu người dùng chỉ nhập **2024-11-03 01:30** tại New York, hệ thống **chưa biết họ muốn lần 01:30 thứ nhất hay thứ hai**. Có thể yêu cầu chọn offset hoặc định nghĩa chính sách, thay vì âm thầm coi giờ địa phương là một timestamp duy nhất.

**withEarlierOffsetAtOverlap/withLaterOffsetAtOverlap** trả đối tượng mới; ZonedDateTime là immutable.

### 6.2. ofStrict và getValidOffsets

**ZonedDateTime.ofStrict(local, offset, zone)** dùng khi ứng dụng đã có offset do người dùng chọn, hoặc một nguồn dữ liệu cung cấp. API kiểm tra offset đó thật sự hợp lệ theo ZoneRules. Nó giúp ngăn việc khôi phục sai một Instant từ một cặp ngày giờ và offset không phù hợp với vùng.

**Không gọi ofStrict với một offset "đang đúng hôm nay"** để áp cho mọi ngày. Luôn tính offset hợp lệ tại **ngày giờ cụ thể**.

### 6.3. ofLocal có preferredOffset

Đối với tình huống cần ưu tiên offset nhưng cho phép fallback theo quy tắc bình thường, **ZonedDateTime.ofLocal(localDateTime, zone, preferredOffset)** là API thích hợp. Nếu preferredOffset hợp lệ trong overlap thì nó được chọn; nếu không, API chọn offset theo quy tắc giải quyết bình thường.

**Khác biệt:** **ofStrict** có thể **từ chối offset không hợp lệ**, còn **ofLocal** có thể tự giải quyết theo quy tắc mặc định. Chọn API theo yêu cầu dữ liệu.

## 7. ZoneRules: kiểm tra trước khi đặt lịch

**ZoneRules** trả lời những câu hỏi mà một LocalDateTime thuần không trả lời được:

~~~java
ZoneId zone = ZoneId.of("America/New_York");

List<ZoneOffset> validOffsets =
        zone.getRules().getValidOffsets(localDateTime);
~~~

Đây là **đoạn minh họa**, cần import **ZoneId**, **ZoneOffset**, **LocalDateTime** và **List**.

| validOffsets.size() | Ý nghĩa | Cách xử lý gợi ý |
|---|---|---|
| **1** | Giờ địa phương hợp lệ, không mơ hồ | Có thể dùng **ofStrict** với offset duy nhất |
| **0** | Gap: giờ không tồn tại | Từ chối, yêu cầu sửa, hoặc dịch giờ theo chính sách rõ ràng |
| **2** | Overlap: giờ lặp lại | Yêu cầu chọn offset hoặc áp quy tắc chọn trước/sau |
| Khác | Không phải trường hợp thông thường theo mô hình zone rules | Không tự giả định; kiểm tra hợp đồng và dữ liệu |

**ZoneRules.getOffset(LocalDateTime)** trả một offset được xem là "phù hợp nhất", nhưng khi gap/overlap **không có một đáp án duy nhất đúng**. Nếu lịch hẹn cần giải quyết chính xác, hãy dùng **getValidOffsets(...)** và **getTransition(...)**.

**getTransition(local)** trả thông tin chuyển offset khi local nằm trong khoảng chuyển. Không mặc định method này luôn trả non-null.

### 7.1. Ví dụ thiết kế nghiêm ngặt: từ chối giờ thiếu hoặc lặp

Một hệ thống có thể chọn quy tắc: **chỉ chấp nhận thời điểm người dùng nhập nếu có đúng một offset hợp lệ**. Khi gặp gap hoặc overlap, yêu cầu người dùng chọn lại hoặc bổ sung offset.

Lưu thành **StrictLocalScheduleDemo.java**:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.List;

public class StrictLocalScheduleDemo {
    static ZonedDateTime resolveStrict(
            LocalDateTime local,
            ZoneId zone) {

        List<ZoneOffset> offsets =
                zone.getRules().getValidOffsets(local);

        if (offsets.size() != 1) {
            throw new IllegalArgumentException(
                    "invalidOrAmbiguous");
        }

        return ZonedDateTime.ofStrict(
                local,
                offsets.get(0),
                zone);
    }

    static String tryResolve(
            LocalDateTime local,
            ZoneId zone) {

        try {
            return resolveStrict(local, zone).toString();
        } catch (IllegalArgumentException exception) {
            return "REJECTED";
        }
    }

    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");

        System.out.println("normal="
                + tryResolve(
                        LocalDateTime.of(2024, 3, 11, 9, 0),
                        newYork));

        System.out.println("gap="
                + tryResolve(
                        LocalDateTime.of(2024, 3, 10, 2, 30),
                        newYork));

        System.out.println("overlap="
                + tryResolve(
                        LocalDateTime.of(2024, 11, 3, 1, 30),
                        newYork));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrictLocalScheduleDemo.java
java StrictLocalScheduleDemo
~~~

**Stdout:**

~~~text
normal=2024-03-11T09:00-04:00[America/New_York]
gap=REJECTED
overlap=REJECTED
~~~

**Giải thích:** Với các ngày trong ví dụ, 09:00 ngày 11/3 là thời điểm hợp lệ. Giờ **02:30 ngày 10/3** không tồn tại, còn **01:30 ngày 3/11** bị lặp, nên ví dụ từ chối cả hai.

**Đây là một chính sách ứng dụng có chủ ý**, không phải yêu cầu mặc định của ZonedDateTime. Một ứng dụng khác có thể cần hỗ trợ overlap bằng cách cho người dùng chọn offset và gọi **ofStrict** với offset đó.

## 8. withZoneSameInstant và withZoneSameLocal: hai bài toán khác nhau

Đây là cặp API dễ gây nhầm nhất:

- **withZoneSameInstant(targetZone)**: giữ nguyên **Instant**, thay cách hiển thị giờ địa phương và offset theo zone đích.
- **withZoneSameLocal(targetZone)**: cố giữ nguyên **LocalDateTime**, nhưng diễn giải nó theo zone đích; **Instant thường thay đổi**. Nếu giờ không hợp lệ trong zone đích, có thể điều chỉnh theo quy tắc gap/overlap.

Ví dụ khởi đầu:

~~~text
2026-01-02T09:30+07:00[Asia/Ho_Chi_Minh]
Instant = 2026-01-02T02:30:00Z
~~~

Chuyển sang Paris:

~~~text
withZoneSameInstant(Europe/Paris)
    2026-01-02T03:30+01:00[Europe/Paris]
    Instant vẫn là 02:30Z.

withZoneSameLocal(Europe/Paris)
    2026-01-02T09:30+01:00[Europe/Paris]
    Instant thành 08:30Z.
~~~

**Chuyển múi giờ cho một sự kiện đã xảy ra:** thường dùng **withZoneSameInstant**.

**Diễn giải lại giờ địa phương như giờ của vùng khác:** dùng **withZoneSameLocal** khi đó thật sự là chủ ý, chẳng hạn sửa zone của lịch hẹn trong khi giữ giờ đồng hồ người dùng nhập.

### 8.1. Chương trình đầy đủ: giữ Instant hay giữ LocalDateTime?

Lưu thành **ZoneConversionDemo.java**:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ZoneConversionDemo {
    public static void main(String[] args) {
        ZonedDateTime original = ZonedDateTime.of(
                2026, 1, 2, 9, 30, 0, 0,
                ZoneId.of("Asia/Ho_Chi_Minh"));

        ZoneId paris = ZoneId.of("Europe/Paris");

        ZonedDateTime sameInstant =
                original.withZoneSameInstant(paris);

        ZonedDateTime sameLocal =
                original.withZoneSameLocal(paris);

        System.out.println("original=" + original);
        System.out.println("sameInstant=" + sameInstant);
        System.out.println("sameLocal=" + sameLocal);

        System.out.println("instantPreserved="
                + original.toInstant()
                        .equals(sameInstant.toInstant()));

        System.out.println("instantAfterSameLocal="
                + original.toInstant()
                        .equals(sameLocal.toInstant()));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ZoneConversionDemo.java
java ZoneConversionDemo
~~~

**Stdout:**

~~~text
original=2026-01-02T09:30+07:00[Asia/Ho_Chi_Minh]
sameInstant=2026-01-02T03:30+01:00[Europe/Paris]
sameLocal=2026-01-02T09:30+01:00[Europe/Paris]
instantPreserved=true
instantAfterSameLocal=false
~~~

**Không dùng withZoneSameLocal khi hiển thị log cho người dùng ở nơi khác**; nó có thể biến sự kiện thành một thời điểm mới. Mục đích hiển thị timestamp là giữ **cùng Instant**.

### 8.2. atZone từ Instant luôn xác định rõ

Khi đầu vào đã là **Instant**, gọi:

~~~java
ZonedDateTime visible =
        instant.atZone(ZoneId.of("Europe/Paris"));
~~~

là phép xem một thời điểm đã xác định theo vùng; không cần chọn giữa hai Instant trong overlap. Khi **LocalDateTime → ZonedDateTime**, mới cần giải quyết việc ngày giờ cục bộ có thể thiếu hoặc lặp.

## 9. Phép tính lịch và phép tính thời lượng: plusDays khác plusHours

Trên ZonedDateTime có hai kiểu thao tác:

**Phép tính ngày lịch (local timeline):**

- **plusYears**, **plusMonths**, **plusWeeks**, **plusDays**.
- Điều chỉnh trường ngày-giờ địa phương, sau đó giải quyết offset theo zone rules.
- Có thể tạo khoảng chênh lệch Instant không đúng bội số 24 giờ do DST.

**Phép tính thời lượng (instant timeline):**

- **plusHours**, **plusMinutes**, **plusSeconds**, **plusNanos**.
- Cộng theo thời lượng trên timeline, rồi tính lại giờ địa phương/offset.
- **plusHours(24)** tương ứng 24 giờ thực, không nhất thiết là cùng giờ đồng hồ vào ngày mai.

### 9.1. Ví dụ DST: một ngày sau khác 24 giờ sau

Lưu thành **ZonedDateTimeArithmeticDemo.java**:

~~~java
import java.time.Duration;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ZonedDateTimeArithmeticDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");

        ZonedDateTime beforeDst = ZonedDateTime.of(
                2024, 3, 9, 12, 0, 0, 0, newYork);

        ZonedDateTime plusDay = beforeDst.plusDays(1);
        ZonedDateTime plus24Hours = beforeDst.plusHours(24);

        System.out.println("before=" + beforeDst);
        System.out.println("plusDay=" + plusDay);
        System.out.println("plus24Hours=" + plus24Hours);

        System.out.println("hoursForDay="
                + Duration.between(
                        beforeDst.toInstant(),
                        plusDay.toInstant()).toHours());

        System.out.println("hoursFor24Hours="
                + Duration.between(
                        beforeDst.toInstant(),
                        plus24Hours.toInstant()).toHours());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ZonedDateTimeArithmeticDemo.java
java ZonedDateTimeArithmeticDemo
~~~

**Stdout:**

~~~text
before=2024-03-09T12:00-05:00[America/New_York]
plusDay=2024-03-10T12:00-04:00[America/New_York]
plus24Hours=2024-03-10T13:00-04:00[America/New_York]
hoursForDay=23
hoursFor24Hours=24
~~~

**Giải thích:**

- **plusDays(1)** giữ quy tắc **"cùng giờ địa phương vào ngày kế tiếp"** trong trường hợp này, nên khoảng thời gian thật là **23 giờ**.
- **plusHours(24)** tiến đúng 24 giờ trên timeline nên đồng hồ địa phương thành **13:00** vì một giờ đã bị nhảy qua.
- **plusDays(1)** không hứa mọi kết quả đều giữ nguyên giờ địa phương: nếu giờ đích rơi vào gap, ZonedDateTime áp dụng quy tắc điều chỉnh giờ hợp lệ.

### 9.2. Period và Duration

**Period.ofDays(1)** là một **khoảng lịch**, thường được áp dụng qua phép cộng ngày trên ZonedDateTime. **Duration.ofDays(1)** là **86.400 giây** theo Duration.

~~~java
ZonedDateTime a = beforeDst.plus(Period.ofDays(1));
ZonedDateTime b = beforeDst.plus(Duration.ofDays(1));
~~~

Đây là **đoạn minh họa**, trước đó cần khai báo **beforeDst** và import **Period**, **Duration**. Trong ví dụ DST ở trên, **a** có hành vi giống plusDays(1), còn **b** giống plusHours(24).

**Không gộp khái niệm "một ngày lịch" và "24 giờ thực"** khi viết hợp đồng thanh toán, lịch nhắc việc, SLA hoặc hết hạn.

### 9.3. plusMonths và plusYears

**plusMonths(1)** hoặc **plusYears(1)** trên ZonedDateTime thực hiện phép tính theo **các trường lịch địa phương**, sau đó áp ZoneRules. Nếu tháng đích không có ngày trong tháng cũ, quy tắc ngày cuối tháng được áp dụng tương tự LocalDate.

Nếu bài toán là **"hẹn hàng tháng vào ngày cuối cùng"**, cần thiết kế rõ quy tắc end-of-month. Việc cộng liên tiếp từ 31/1 có thể dẫn tới "29/2 rồi 29/3" chứ không tự giữ ngày cuối mỗi tháng.

### 9.4. Cộng và trừ trong overlap

Khi thay đổi local date-time của một ZonedDateTime vào vùng overlap, API **ưu tiên giữ offset đang có nếu offset ấy vẫn hợp lệ**, nếu không sẽ dùng offset sớm hơn theo hợp đồng. Vì vậy hai chuỗi phép tính trên ZonedDateTime có thể chọn hai phía overlap khác nhau nếu trạng thái offset trước đó khác nhau.

Nếu cần điều kiện chính xác **"lần 01:30 thứ hai"**, nên thể hiện rõ offset hoặc Instant, không suy ra chỉ từ LocalDateTime.

## 10. atStartOfDay và ranh giới ngày theo múi giờ

Để tìm **đầu một ngày địa phương** trong vùng:

~~~java
LocalDate day = LocalDate.of(2024, 3, 10);
ZoneId zone = ZoneId.of("America/New_York");

ZonedDateTime start = day.atStartOfDay(zone);
~~~

Đây là **đoạn minh họa**, cần import **LocalDate**, **ZoneId**, **ZonedDateTime**.

**LocalDate.atStartOfDay(zone)** xác định **thời điểm đầu ngày hợp lệ sớm nhất** trong vùng. Nó không luôn là đúng **00:00** ở mọi khu vực và mọi ngày lịch sử: nếu vùng nhảy offset ngay nửa đêm thì 00:00 có thể bị bỏ qua.

Để xác định khoảng ngày địa phương **[startDay, nextDay)** theo timeline:

~~~java
Instant startInstant =
        day.atStartOfDay(zone).toInstant();

Instant endInstant =
        day.plusDays(1)
                .atStartOfDay(zone)
                .toInstant();
~~~

**Không thay bằng** **startInstant.plus(Duration.ofDays(1))** nếu mục tiêu là "đến đầu ngày kế tiếp tại vùng đó", vì độ dài ngày trong zone có thể không là 24 giờ.

### 10.1. Khoảng ngày nên có biên đầu bao gồm và biên cuối loại trừ

~~~text
[startInclusive, endExclusive)

Sự kiện thuộc ngày địa phương D nếu:
  eventInstant >= startOfDay(D, zone)
  eventInstant <  startOfDay(D + 1, zone)
~~~

Điều kiện này tránh phải tính **"23:59:59.999999999"** và không phụ thuộc độ chính xác mà database lưu được.

**Lưu ý vùng lịch sử hiếm gặp:** Có vùng từng bỏ qua **cả một ngày lịch** khi thay đổi múi giờ. Trong trường hợp ấy, hai ranh giới ngày có thể trùng nhau và khoảng ngày có thể rỗng. Một hệ thống có yêu cầu lịch sử hoặc toàn cầu nên kiểm tra tính hợp lệ của phạm vi ngày theo ZoneRules chứ không mặc định mọi ngày đều tồn tại.

## 11. ZonedDateTime.now(Clock) và kiểm thử có thời gian cố định

Những cách đọc ngày giờ hiện tại:

~~~java
ZonedDateTime systemDefault = ZonedDateTime.now();

ZonedDateTime inVietnam = ZonedDateTime.now(
        ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime fromClock = ZonedDateTime.now(clock);
~~~

Đây là **đoạn minh họa**, cần khai báo **Clock clock** và import các kiểu tương ứng.

- **now()** dựa vào hệ thống và ZoneId mặc định của JVM.
- **now(ZoneId)** dùng zone được truyền và đồng hồ thực.
- **now(Clock)** dùng Clock được tiêm (gồm Instant và ZoneId), rất hữu ích cho unit test.
- Kết quả thay đổi theo thời điểm chạy nếu dùng đồng hồ thật; **không gán stdout cố định cho now()**.

### 11.1. Ví dụ đầy đủ: Clock.fixed

Lưu thành **ZonedDateTimeClockDemo.java**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ZonedDateTimeClockDemo {
    public static void main(String[] args) {
        Instant fixedInstant =
                Instant.parse("2026-01-01T23:30:00Z");

        Clock clock = Clock.fixed(
                fixedInstant,
                ZoneId.of("Asia/Ho_Chi_Minh"));

        ZonedDateTime now = ZonedDateTime.now(clock);

        System.out.println("now=" + now);
        System.out.println("instant=" + now.toInstant());
        System.out.println("again=" + ZonedDateTime.now(clock));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ZonedDateTimeClockDemo.java
java ZonedDateTimeClockDemo
~~~

**Stdout:**

~~~text
now=2026-01-02T06:30+07:00[Asia/Ho_Chi_Minh]
instant=2026-01-01T23:30:00Z
again=2026-01-02T06:30+07:00[Asia/Ho_Chi_Minh]
~~~

**Giải thích:** Clock cố định Instant nên các lần gọi cho cùng thời gian. Region zone của Clock quyết định biểu diễn ngày giờ địa phương; Instant vẫn là **2026-01-01T23:30:00Z**.

**Khuyến nghị:** Service làm việc với thời gian nên nhận Clock/ZoneId qua dependency injection khi phù hợp. Tránh ẩn zone từ server vào những phép tính liên quan đến người dùng.

## 12. Parse, format và hai phần offset/ZoneId trong dữ liệu

Một chuỗi ZonedDateTime theo dạng ISO có thể có cấu trúc:

~~~text
2026-01-02T09:30:00+07:00[Asia/Ho_Chi_Minh]
      local date/time  offset  [region zone]
~~~

**Offset** cần để xác định Instant. **Region ZoneId** giúp giữ quy tắc timezone. Vì thế chuỗi chỉ chứa **2026-01-02T09:30** không đủ thông tin.

### 12.1. Parse bằng API chuẩn

~~~java
ZonedDateTime parsed = ZonedDateTime.parse(
        "2026-01-02T09:30:00+07:00[Asia/Ho_Chi_Minh]");
~~~

Đây là **đoạn minh họa**, cần import **ZonedDateTime**. Formatter mặc định là **DateTimeFormatter.ISO_ZONED_DATE_TIME**.

**ZonedDateTime.toString()** thường in date-time, offset và ZoneId nếu đó là region zone; nhưng định dạng hiển thị sẽ bỏ một số trường có giá trị 0 theo tiêu chuẩn ISO. Không cố định số ký tự hoặc kỳ vọng giây luôn được in.

### 12.2. Formatter có ZoneId và offset

Lưu thành **ZonedDateTimeFormattingDemo.java**:

~~~java
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class ZonedDateTimeFormattingDemo {
    public static void main(String[] args) {
        ZonedDateTime time = ZonedDateTime.parse(
                "2026-01-02T09:30:00+07:00[Asia/Ho_Chi_Minh]");

        DateTimeFormatter formatter =
                DateTimeFormatter.ofPattern(
                        "dd/MM/uuuu HH:mm VV XXX",
                        Locale.ROOT);

        System.out.println("parsed=" + time);
        System.out.println("formatted=" + time.format(formatter));
        System.out.println("instant=" + time.toInstant());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ZonedDateTimeFormattingDemo.java
java ZonedDateTimeFormattingDemo
~~~

**Stdout:**

~~~text
parsed=2026-01-02T09:30+07:00[Asia/Ho_Chi_Minh]
formatted=02/01/2026 09:30 Asia/Ho_Chi_Minh +07:00
instant=2026-01-02T02:30:00Z
~~~

**Ghi nhớ về pattern:**

- **uuuu** là proleptic year; **yyyy** là year-of-era.
- **MM** biểu diễn tháng, **mm** biểu diễn phút.
- **HH** là giờ 0–23.
- **VV** là zone ID, ví dụ Asia/Ho_Chi_Minh.
- **XXX** là offset được định dạng như +07:00 hoặc Z.
- **z** là tên zone dạng văn bản có thể phụ thuộc Locale; không dùng tên viết tắt không rõ ràng để nhận diện vùng một cách duy nhất.

### 12.3. Offset đúng hay sai với ZoneId?

Nếu dữ liệu gửi cả **offset** và **region ZoneId**, cả hai mang thông tin khác nhau. Ở một vùng DST, offset hợp lệ cho local datetime có thể thay đổi theo mùa hoặc chính sách. Khi độ chính xác lịch sử quan trọng, cần **xác thực sự nhất quán** thay vì chỉ parse chuỗi rồi tin rằng offset nhập luôn phù hợp với ngày/zone.

**ZonedDateTime.ofStrict(local, offset, zone)** là API để xác minh một offset cụ thể có hợp lệ với local date-time/zone hay không. Nó đặc biệt hữu ích với dữ liệu người dùng chọn trong overlap.

**Không giả định parser bắt buộc từ chối mọi chuỗi có offset và ZoneId không phù hợp** theo cách mà ofStrict làm. Đọc hợp đồng parser/formatter; với validation nghiệp vụ, kiểm tra riêng cặp local time – zone – offset.

## 13. Equals, isEqual, isBefore và compareTo

ZonedDateTime vừa mang thông tin **cách biểu diễn ngày giờ**, vừa xác định **Instant**. Vì vậy có hai câu hỏi khác nhau:

1. **Hai giá trị có cùng ngày-giờ cục bộ, offset và zone không?** Dùng **equals(...)** khi cần so đối tượng ZonedDateTime theo các thành phần của nó.
2. **Hai giá trị có cùng một điểm trên timeline không?** Dùng **isEqual(...)** hoặc **toInstant().equals(...)**.

**isBefore(...)** và **isAfter(...)** dựa trên quan hệ thời điểm trên timeline.

~~~text
UTC:                 2026-01-01T23:30Z
Asia/Ho_Chi_Minh:    2026-01-02T06:30+07[Asia/Ho_Chi_Minh]

Hai giờ địa phương khác nhau.
Cùng Instant.
~~~

### 13.1. Ví dụ đầy đủ: cùng Instant không đồng nghĩa equals

Lưu thành **ZonedDateTimeEqualityDemo.java**:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class ZonedDateTimeEqualityDemo {
    public static void main(String[] args) {
        Instant instant =
                Instant.parse("2026-01-01T23:30:00Z");

        ZonedDateTime utc =
                instant.atZone(ZoneOffset.UTC);

        ZonedDateTime vietnam =
                instant.atZone(
                        ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("equals=" + utc.equals(vietnam));
        System.out.println("isEqual=" + utc.isEqual(vietnam));
        System.out.println("sameInstant="
                + utc.toInstant()
                        .equals(vietnam.toInstant()));

        System.out.println("compareToZero="
                + (utc.compareTo(vietnam) == 0));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ZonedDateTimeEqualityDemo.java
java ZonedDateTimeEqualityDemo
~~~

**Stdout:**

~~~text
equals=false
isEqual=true
sameInstant=true
compareToZero=false
~~~

**Giải thích:** **equals** xét các thành phần ngày giờ và zone; **isEqual** xét cùng điểm trên timeline. **compareTo** của ZonedDateTime có thứ tự so sánh đủ chi tiết để nhất quán với equals, không chỉ so Instant. Vì vậy cùng Instant nhưng biểu diễn ở hai zone khác nhau có thể cho **compareTo != 0**.

**Khi sort nhật ký sự kiện theo thời gian xảy ra**, hãy so **toInstant()**:

~~~java
events.sort(Comparator.comparing(
        event -> event.occurredAt().toInstant()));
~~~

Đây là **đoạn minh họa**, giả sử events là List của đối tượng có occurredAt kiểu ZonedDateTime, và đã import Comparator. Nếu cần tách thứ tự giữa các sự kiện có cùng Instant, bổ sung khóa thứ hai (sequence/id) theo nghiệp vụ.

**Không vô tình lấy compareTo của ZonedDateTime làm phép kiểm tra "cùng Instant"**; khi đó cần **isEqual**.

## 14. ZonedDateTime immutable và value-based

Giống các class chính của java.time, **ZonedDateTime immutable và thread-safe**. Các phương thức **plusDays**, **minusHours**, **withZoneSameInstant**, **withZoneSameLocal**, **withEarlierOffsetAtOverlap**... đều trả một giá trị mới, không sửa instance cũ.

~~~java
ZonedDateTime original = ZonedDateTime.of(
        2026, 1, 2, 9, 30, 0, 0,
        ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime changed = original.plusDays(1);

// original vẫn là 2026-01-02T09:30+07...
// changed có ngày 2026-01-03...
~~~

Đây là đoạn minh họa.

**Lỗi thường gặp:**

~~~java
meeting.plusDays(1); // Bỏ kết quả trả về.
~~~

Giá trị meeting **không đổi**. Muốn cập nhật biến:

~~~java
meeting = meeting.plusDays(1);
~~~

**Không dùng == để so hai ZonedDateTime** theo giá trị hoặc dùng ZonedDateTime làm khóa monitor cho synchronized. Dùng equals, isEqual hoặc so Instant theo mục tiêu cụ thể.

## 15. Tzdb và quy tắc timezone có thể thay đổi

Các region ZoneId được liên kết với **quy tắc múi giờ**. Những quy tắc này được cung cấp qua **ZoneRules** và cơ sở dữ liệu timezone của môi trường JDK, thường dựa trên thông tin lịch sử và quyết định hành chính.

Điểm thực tế:

- Một nước/vùng có thể thay đổi chính sách DST hoặc offset trong tương lai.
- Sau khi JDK được cập nhật tzdb, phép giải quyết **LocalDateTime + ZoneId** của một sự kiện tương lai có thể thay đổi offset dự kiến.
- Một **Instant đã ghi nhận** vẫn là điểm thời gian, dù cách trình bày theo zone được cập nhật khi thông tin lịch sử/quy tắc đổi.
- **Chỉ lưu offset** làm mất region rules cần cho lịch hẹn định kỳ hoặc ràng buộc "09:00 giờ địa phương".
- **Chỉ lưu LocalDateTime** làm mất zone cần để giải quyết Instant.

**Thiết kế lưu trữ cần phản ánh mục tiêu:**

| Dữ liệu nghiệp vụ | Nên lưu gì? |
|---|---|
| Sự kiện đã thực sự xảy ra | **Instant** (và metadata zone nếu cần giải thích cách hiển thị) |
| Một lần hẹn đã chốt tại một thời điểm cụ thể | **Instant** + thông tin zone/local time phục vụ hiển thị/kiểm toán khi cần |
| Lịch họp "09:00 mỗi thứ Hai tại New York" | **LocalTime + ngày/quy tắc lặp + ZoneId**, áp quy tắc giải quyết DST khi tạo từng lần |
| Người dùng nhập giờ bị lặp và chọn offset cụ thể | Lưu **LocalDateTime + ZoneId + offset được chọn** hoặc Instant đã giải quyết; giữ đủ thông tin để giải thích quyết định |
| Ngày giao hàng không có giờ | **LocalDate**, zone chỉ dùng khi cần suy ra ranh giới thời gian |

**Không có một mô hình lưu trữ duy nhất đúng cho mọi tình huống.** Một hệ thống tài chính cần timestamp bất biến; một lịch tái diễn thường cần giờ địa phương và zone để phản ánh quy tắc vùng cập nhật trong tương lai.

### 15.1. Định dạng lưu thông tin vùng

Chuỗi ISO có suffix **[Europe/Paris]** hữu ích khi truyền dữ liệu Java–Java, nhưng **không được giả định mọi API bên ngoài hiểu region zone nằm trong ngoặc vuông**. Nếu tích hợp rộng, có thể tách rõ:

~~~json
{
  "localDateTime": "2026-01-02T09:30:00",
  "zoneId": "Asia/Ho_Chi_Minh",
  "offset": "+07:00",
  "instant": "2026-01-02T02:30:00Z"
}
~~~

Đây là **JSON minh họa**. Chỉ lưu những trường ứng dụng thật sự cần, và quy định cách xử lý khi dữ liệu redundant mâu thuẫn. **Không tự coi giá trị offset từ client là đáng tin tuyệt đối**: dùng ZoneRules xác nhận khi cần.

### 15.2. Database và ORM

Khi lưu ZonedDateTime qua JDBC/ORM, **ngữ nghĩa của các kiểu TIMESTAMP, TIMESTAMP WITH TIME ZONE và độ chính xác dữ liệu phụ thuộc database/driver**. Một số hệ thống chỉ lưu **Instant/UTC** hoặc offset, không lưu **region ZoneId** ban đầu. Do đó cần kiểm thử round-trip với đúng database và ORM cấu hình production.

**Không khẳng định một cột tên "TIMESTAMP WITH TIME ZONE" luôn bảo toàn zone ID vùng như Europe/Paris** ở tất cả các hệ quản trị. Nếu nghiệp vụ cần giữ region ZoneId, lưu/ánh xạ nó rõ ràng.

## 16. Ví dụ nghiệp vụ: lịch hẹn định kỳ theo giờ địa phương

Giả sử một cửa hàng tại New York muốn mở lịch kiểm kê vào **09:00 giờ địa phương** mỗi ngày. Điều quan trọng là **09:00 theo đồng hồ vùng**, không phải cứ cộng 24 giờ cố định vào Instant của hôm trước.

Một cách diễn đạt ý định:

~~~java
ZoneId storeZone = ZoneId.of("America/New_York");
LocalTime localTime = LocalTime.of(9, 0);

LocalDate day = LocalDate.of(2024, 3, 9);

ZonedDateTime first = day.atTime(localTime)
        .atZone(storeZone);

ZonedDateTime next = day.plusDays(1)
        .atTime(localTime)
        .atZone(storeZone);
~~~

Đây là đoạn minh họa, cần import các kiểu java.time tương ứng.

**Đầu ra kỳ vọng theo quy tắc New York năm 2024:**

~~~text
first = 2024-03-09T09:00-05:00[America/New_York]
next  = 2024-03-10T09:00-04:00[America/New_York]
~~~

Hai lần đều chạy lúc 09:00 theo đồng hồ địa phương, nhưng vì chuyển DST, khoảng giữa hai Instant là **23 giờ**.

**Nếu muốn tác vụ chạy đúng mỗi 24 giờ thực**, đó là yêu cầu khác và nên dùng Instant/Duration. Đừng làm mờ ranh giới "định kỳ theo lịch dân sự" và "định kỳ theo elapsed duration".

### 16.1. Khi giờ đặt lịch nằm trong gap/overlap

**Ví dụ 09:00** thường không rơi vào giờ chuyển DST trong ví dụ New York, nhưng một lịch định kỳ vào **02:30** có thể gặp gap, còn lịch **01:30** có thể gặp overlap.

Chọn chính sách trước:

- **GAP:** bỏ lần chạy, dịch tới thời điểm hợp lệ, hay từ chối cấu hình?
- **OVERLAP:** chạy một lần (earlier/later offset), chạy hai lần, hay yêu cầu chọn?
- **Timezone thay đổi chính sách:** dùng quy tắc mới khi tạo lịch tiếp theo hay giữ những Instant đã được chốt?
- **Retry:** nếu job thất bại, chạy lại phải tránh thực thi lặp các hành động không idempotent.

**ZonedDateTime chỉ giải quyết thời gian**, không tự cung cấp scheduler, chính sách retry hoặc transaction cho hệ thống.

## 17. Những lỗi thường gặp

### Lỗi 1 — coi ZoneId chỉ là offset hiện tại

~~~java
// Không phù hợp với lịch theo New York qua các mùa:
ZoneOffset fixed = ZoneOffset.ofHours(-5);
~~~

Nếu nghiệp vụ dùng vùng New York, chọn **ZoneId.of("America/New_York")** để nhận zone rules.

### Lỗi 2 — tự cho rằng một LocalDateTime luôn có một Instant

Vào overlap có **hai offset**; vào gap có **không offset**. Kiểm tra **getValidOffsets** hoặc định nghĩa chính sách rõ.

### Lỗi 3 — quên atZone có thể chỉnh giờ trong gap

~~~java
LocalDateTime local =
        LocalDateTime.of(2024, 3, 10, 2, 30);

ZonedDateTime zdt =
        local.atZone(ZoneId.of("America/New_York"));
~~~

Kết quả **03:30**, không còn 02:30. Nếu ứng dụng cần xác thực thời gian người dùng nhập, không thể chỉ gọi atZone rồi mặc định mọi thứ giữ nguyên.

### Lỗi 4 — overlap nhưng không phân biệt lần đầu và lần sau

~~~java
LocalDateTime repeated =
        LocalDateTime.of(2024, 11, 3, 1, 30);
~~~

Không đủ để biết người dùng chọn 01:30 offset **-04** hay **-05**. Dùng **getValidOffsets**, **withEarlierOffsetAtOverlap/withLaterOffsetAtOverlap**, **ofStrict** theo chính sách.

### Lỗi 5 — dùng withZoneSameLocal để hiển thị một Instant ở zone khác

**withZoneSameLocal** có thể thay Instant. Khi chuyển cách hiển thị của sự kiện đã xảy ra, dùng **withZoneSameInstant**.

### Lỗi 6 — cho rằng plusDays(1) luôn bằng cộng 24 giờ

ZonedDateTime xử lý **ngày lịch**, còn **plusHours(24)** xử lý **thời lượng**. DST có thể làm độ dài một ngày 23/25 giờ.

### Lỗi 7 — cộng tháng bằng 30 ngày

**plusMonths(1)** dùng quy tắc tháng lịch; **Duration.ofDays(30)** là một độ dài cố định. Chúng không tương đương.

### Lỗi 8 — định dạng giờ địa phương nhưng bỏ ZoneId/offset rồi lưu như timestamp

~~~java
String localOnly = zdt.toLocalDateTime().toString();
~~~

Giá trị này đã mất zone và offset. Ở overlap có thể không khôi phục lại đúng Instant. Nếu cần timestamp, lưu **Instant** hoặc dữ liệu đầy đủ theo hợp đồng.

### Lỗi 9 — dùng equals để hỏi "có cùng một thời điểm không?"

Hai ZonedDateTime ở hai zone khác nhau có thể là cùng Instant nhưng **equals==false**. Dùng **isEqual** hoặc so toInstant().

### Lỗi 10 — nghĩ compareTo chỉ xét Instant

**ZonedDateTime.compareTo** còn xét các thành phần để có thứ tự nhất quán với equals. Khi sort theo timeline, dùng **Comparator.comparing(ZonedDateTime::toInstant)** hoặc so các Instant cụ thể.

### Lỗi 11 — đọc ZoneId.systemDefault trong nghiệp vụ đa khu vực

Server đặt UTC còn khách hàng ở New York/Vietnam; ngày địa phương từ cùng Instant có thể khác. Truyền zone đúng theo người dùng/địa điểm.

### Lỗi 12 — tin dữ liệu offset từ client mà không kiểm tra

Một chuỗi có thể kết hợp local time/offset/zone không phù hợp. Nếu chính sách đòi kiểm tra nghiêm ngặt, dùng **ZoneRules.getValidOffsets** và **ofStrict**.

### Lỗi 13 — gọi getTransition(...).isGap() mà không kiểm tra null

Với local datetime bình thường, **getTransition(...)** có thể trả **null**. Kiểm tra trước hoặc bắt đầu bằng **getValidOffsets(...)**.

### Lỗi 14 — nghĩ ZonedDateTime tự xử lý mọi lịch hẹn định kỳ

Class này không quyết định chạy một lần hay hai lần ở overlap, không cung cấp scheduler hay transaction. Ứng dụng phải có chính sách.

### Lỗi 15 — dùng đối tượng làm lock hoặc so ==

ZonedDateTime immutable/value-based; không dựa vào object identity. Dùng **equals/isEqual** đúng mục tiêu, và dùng cơ chế đồng bộ riêng.

### Lỗi 16 — ghi cứng timezone abbreviation như EST/PST

Tên viết tắt có thể mơ hồ hoặc không phản ánh lịch sử DST. Ưu tiên region ZoneId như **America/New_York**. Khi xử lý đầu vào từ bên ngoài, quy định rõ ID hợp lệ và cách ánh xạ.

### Lỗi 17 — tin rằng tzdb không bao giờ thay đổi

Quy tắc múi giờ là dữ liệu do quy định hành chính và được JDK cập nhật. Với lịch tương lai, hiểu ranh giới giữa **Instant đã chốt** và **giờ địa phương cần giữ ổn định**.

### Lỗi 18 — giả định ZonedDateTime parse rồi có zone id giống dữ liệu gốc

Nhiều parser/schema chỉ hỗ trợ offset hoặc normalize timestamp. Cần chọn định dạng đủ thông tin và test round-trip đúng thành phần (Instant, ZoneId, offset) mà ứng dụng cần giữ.

## 18. Checklist kiểm thử

Khi xây hệ thống múi giờ, nên có test cho:

1. **Giờ bình thường:** đúng một offset cho LocalDateTime trong ZoneId.
2. **Gap:** zero valid offsets, quy tắc mặc định dời giờ, chính sách của ứng dụng khi từ chối.
3. **Overlap:** two valid offsets, hai Instant khác nhau, lựa chọn earlier/later.
4. **ofStrict:** offset đúng thành công; offset không hợp lệ thất bại.
5. **withZoneSameInstant:** Instant phải giữ nguyên sau đổi zone.
6. **withZoneSameLocal:** ngày giờ địa phương được giữ khi hợp lệ; Instant có thể đổi.
7. **plusDays vs plusHours:** kiểm tra ngày chuyển DST.
8. **plusMonths/plusYears:** ngày cuối tháng và quy tắc clip khi cần.
9. **Clock.fixed:** ngày giờ hiện tại trong test ổn định.
10. **Parse/format:** giữ zone, offset và Instant cần thiết khi round-trip.
11. **ZoneRules transitions:** getTransition chỉ được đọc khi không null.
12. **Equality:** cùng Instant nhưng khác zone có isEqual true, equals false.
13. **Ranh giới ngày:** startOfDay của ngày kế tiếp không mặc định đúng 24 giờ sau.
14. **Timezone vùng:** ID thuộc danh sách hợp lệ, tránh các tên viết tắt mơ hồ.
15. **Database:** precision và timezone/region ID thực sự được lưu theo contract.
16. **Lịch sử/tương lai:** có test với dữ liệu DST lịch sử và theo quy tắc môi trường đang hỗ trợ.
17. **Dữ liệu dùng chung:** loại dữ liệu immutable; không phụ thuộc identity của object.
18. **Lịch định kỳ:** chính sách gap/overlap và retry rõ ràng, không tự chọn ngầm.

### 18.1. Test nên có giá trị xác định

Các ví dụ trong bài cố định **2024** hoặc **2026**, nên có stdout dự đoán được theo timezone rules tương ứng. Không viết unit test so một giá trị cố định với **ZonedDateTime.now()** đọc đồng hồ thật. Dùng **Clock.fixed** để kiểm soát kết quả.

**Chú ý:** quy tắc zone có thể cập nhật khi JDK/tzdb đổi, đặc biệt với lịch tương lai. Test cần ghi rõ giả thiết về vùng/ngày thay vì coi kết quả offset là chân lý bất biến cho mọi bản tzdb trong mọi thời kỳ.

## 19. Bài tập tự kiểm tra

**Câu 1.** ZonedDateTime khác LocalDateTime ở điểm nào? Có thể chuyển ZonedDateTime sang Instant không?

**Câu 2.** ZoneId **America/New_York** có phải luôn là offset **-05:00** không?

**Câu 3.** Khi ZoneRules.getValidOffsets(local).size() trả **0**, trường hợp này được gọi là gì?

**Câu 4.** Khi size() trả **2**, người dùng chỉ nhập LocalDateTime + ZoneId đã đủ xác định một Instant chưa?

**Câu 5.** Trong gap New York **2024-03-10T02:30**, **local.atZone(newYork)** mặc định thành giờ nào?

**Câu 6.** Trong overlap New York **2024-11-03T01:30**, hai offset hợp lệ là gì và chúng cách nhau bao lâu trên timeline?

**Câu 7.** **ZonedDateTime.ofStrict(...)** khác với **LocalDateTime.atZone(...)** khi gặp gap ra sao?

**Câu 8.** **withZoneSameInstant(paris)** và **withZoneSameLocal(paris)** khác gì?

**Câu 9.** Nếu bắt đầu **2024-03-09T12:00 tại New York**, kết quả **plusDays(1)** và **plusHours(24)** khác nhau thế nào?

**Câu 10.** Vì sao **LocalDate.atStartOfDay(zone)** không nên được thay bằng ghép UTC 00:00?

**Câu 11.** Cùng Instant hiển thị ở UTC và Việt Nam, **equals** có thể false nhưng **isEqual** có thể true không?

**Câu 12.** Tại sao một lịch hẹn 09:00 hàng ngày ở vùng có DST không nên được tạo bằng cách cộng 86.400 giây vào Instant trước đó?

**Câu 13.** Muốn phát hiện local datetime rơi vào gap hoặc overlap trước khi lưu, dùng API nào?

**Câu 14.** Khi có cùng local datetime trong overlap nhưng người dùng chọn lần thứ hai, dùng API nào để chỉ định offset?

**Câu 15.** Nếu ứng dụng muốn "createdAt của sự kiện", nên ưu tiên Instant hay LocalDateTime không zone?

**Câu 16.** Nếu một API chỉ trả offset +01:00, có khôi phục chắc chắn được region ZoneId ban đầu như Europe/Paris không?

**Câu 17.** Nếu Java/tzdb được cập nhật theo quy định múi giờ mới, phép giải quyết lịch tương lai từ LocalDateTime + ZoneId có thể thay đổi không?

**Câu 18.** Khi parse chuỗi ngày giờ có cả offset và region ZoneId, làm thế nào để kiểm tra offset được truyền thật sự hợp lệ với local date-time và zone?

### Đáp án

1. **ZonedDateTime có ZoneId và offset hợp lệ**, đủ để xác định Instant; LocalDateTime chỉ có ngày và giờ cục bộ.
2. **Không.** New York có thể đổi offset theo DST và lịch sử quy tắc vùng.
3. **Gap**, giờ địa phương không tồn tại.
4. **Chưa.** Overlap có **hai offset**, nên phải chọn chính sách hoặc offset cụ thể.
5. **2024-03-10T03:30-04:00[America/New_York]** theo cách giải quyết mặc định.
6. **-04:00** và **-05:00**, hai Instant cách nhau **1 giờ**.
7. **ofStrict** từ chối offset không hợp lệ bằng DateTimeException; **atZone** mặc định dời giờ qua gap.
8. **SameInstant** giữ điểm thời gian, đổi giờ hiển thị; **SameLocal** cố giữ giờ địa phương và có thể đổi Instant.
9. **plusDays(1)** thành **2024-03-10T12:00-04:00**, cách **23h**; **plusHours(24)** thành **13:00-04:00**, cách đúng **24h**.
10. Vì đầu ngày theo zone có offset/vùng và thậm chí có thể rơi vào gap; UTC midnight thường không phải đầu ngày tại địa điểm đó.
11. **Có.** equals xét các thành phần ZonedDateTime, isEqual xét cùng Instant.
12. Vì một ngày lịch có thể dài 23/25 giờ; cần tính ngày kế tiếp tại zone và giờ địa phương.
13. **zone.getRules().getValidOffsets(local)**, kết hợp **getTransition(local)** nếu có chuyển offset.
14. **withLaterOffsetAtOverlap()** hoặc **ofStrict(local, chosenOffset, zone)**.
15. **Instant** để lưu điểm trên timeline, có thể dùng ZonedDateTime khi cần kèm semantics vùng.
16. **Không.** Offset không phải định danh vùng; nhiều vùng có thể có cùng offset.
17. **Có.** Chính sách vùng/tzdb có thể thay đổi; cần quy định cách cập nhật lịch và mốc đã chốt.
18. Dùng **ZoneRules.getValidOffsets(local)** kiểm tra offset được cung cấp, hoặc **ZonedDateTime.ofStrict(local, offset, zone)** để từ chối cặp không hợp lệ.

## 20. Tổng kết và tài liệu chính thức

**ZonedDateTime là mô hình "ngày giờ địa phương + ZoneId + offset hợp lệ"**, cho phép vừa giữ cách biểu diễn lịch của người dùng, vừa xác định một Instant. Giá trị cốt lõi của ZoneId là **bộ quy tắc múi giờ**, không chỉ là độ lệch UTC đang có.

Những nguyên tắc cần nhớ:

- **Instant → ZonedDateTime** theo ZoneId là phép chuyển rõ ràng vì một Instant xác định một offset hợp lệ cho zone.
- **LocalDateTime → ZonedDateTime** có thể gặp **normal (1 offset)**, **gap (0 offset)** hoặc **overlap (2 offsets)**.
- **atZone/of** có quy tắc tự giải quyết gap/overlap; **ofStrict/getValidOffsets** hỗ trợ kiểm soát nghiêm ngặt khi cần.
- **withZoneSameInstant** giữ Instant, còn **withZoneSameLocal** cố giữ giờ địa phương và có thể đổi Instant.
- **plusDays/plusMonths** tính theo lịch địa phương, **plusHours/Duration** tính theo timeline; hai khái niệm khác nhau quanh DST.
- **equals** khác **isEqual** khi so hai ZonedDateTime ở các vùng khác nhau nhưng cùng Instant.
- **ZonedDateTime immutable**, có thể dùng với **Clock.fixed** để kiểm thử ổn định.
- **Múi giờ vùng có quy tắc lịch sử và có thể thay đổi trong tương lai**; thiết kế dữ liệu lịch hẹn và log cần phân biệt giữ wall time hay giữ Instant.

**Tài liệu Oracle Java API vẫn còn áp dụng:**

- [ZonedDateTime — Java SE 26: normal/gap/overlap, ofStrict, đổi zone và phép tính lịch](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZonedDateTime.html)
- [ZoneRules — Java SE 26: getValidOffsets, getTransition, quy tắc offset](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneRules.html)
- [ZoneId — Java SE 26: vùng múi giờ và danh tính timezone](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneId.html)
- [ZoneOffset — Java SE 26: độ lệch UTC](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/ZoneOffset.html)
- [ZoneOffsetTransition — Java SE 26: gap/overlap transition](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/ZoneOffsetTransition.html)
- [Instant — Java SE 26: điểm trên timeline](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
- [LocalDateTime — Java SE 26: local date-time và atZone](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDateTime.html)
- [Clock — Java SE 26: now(Clock), fixed clock và kiểm thử](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html)
- [DateTimeFormatter — Java SE 26: ISO_ZONED_DATE_TIME và format pattern](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html)
