# ZoneId.systemDefault() và tác động của cấu hình môi trường

**ZoneId.systemDefault()** thuộc gói **java.time** trả về múi giờ mặc định của tiến trình JVM. Đây là lựa chọn tiện lợi khi yêu cầu thực sự là “theo múi giờ của máy đang chạy”, nhưng rất dễ gây lỗi trong ứng dụng phục vụ nhiều người dùng hoặc chạy qua các môi trường khác nhau. Cùng một chương trình có thể trả về **ngày địa phương khác nhau** khi chuyển từ laptop sang CI, container hoặc production dù cùng một **Instant**.

Bài này làm rõ cơ chế đọc múi giờ, ảnh hưởng của tùy chọn **-Duser.timezone**, cấu hình OS/container và thay đổi **TimeZone.setDefault(...)** lúc chạy. Các ví dụ Java 17+ có thể biên dịch, chạy độc lập và kiểm chứng được.

## 1. Múi giờ mặc định của JVM là gì?

~~~java
import java.time.ZoneId;

ZoneId zone = ZoneId.systemDefault();
~~~

Đây là đoạn minh họa cần đặt trong một phương thức hoặc chương trình Java; các ví dụ đầy đủ nằm ở phần sau.

Giá trị trả về có thể là **UTC**, **Asia/Ho_Chi_Minh**, **America/Los_Angeles** hoặc một ID vùng hợp lệ khác. **Không có một đáp án chung cho mọi máy**. Đặc biệt:

- **ZoneId** là danh tính vùng có quy tắc offset theo thời điểm; vùng **America/Los_Angeles** có thể dùng -08:00 hoặc -07:00 tùy ngày.
- **ZoneOffset** là độ lệch UTC cụ thể như **+07:00** hoặc **-08:00**, không chứa tên vùng và toàn bộ quy tắc DST.
- **Instant** là một thời điểm tuyệt đối; nó không mang tên vùng và không thay đổi khi được hiển thị qua ZoneId khác.
- **LocalDate**, **LocalTime** và **LocalDateTime** mang thành phần lịch/đồng hồ địa phương, không tự mang offset hay ZoneId.
- **ZonedDateTime** kết hợp một giá trị ngày giờ với ZoneId và offset hợp lệ theo quy tắc vùng.

**ZoneId.systemDefault() không xác định múi giờ của từng khách hàng hoặc cửa hàng**. Nó phản ánh mặc định của một tiến trình JVM, trong khi một server có thể phục vụ nhiều vùng thời gian.

## 2. Cơ chế và những nguồn cấu hình ảnh hưởng

**ZoneId.systemDefault()** lấy múi giờ mặc định từ **java.util.TimeZone** (về ý nghĩa tương đương **TimeZone.getDefault().toZoneId()**). Mặc định ban đầu thường xuất phát từ thuộc tính Java **user.timezone** và thông tin timezone mà JVM có thể đọc được từ môi trường hệ điều hành.

Có ba cơ chế cần phân biệt:

1. **Tùy chọn khởi động JVM**: **-Duser.timezone=Asia/Ho_Chi_Minh**, **-Duser.timezone=UTC**, v.v. Điều này chỉ định cấu hình ngay khi khởi động.
2. **Môi trường thực thi**: hệ điều hành, máy ảo, container hoặc biến **TZ** có thể ảnh hưởng cách JVM xác định múi giờ mặc định nếu không đặt rõ. Cách phát hiện và thứ tự ưu tiên có thể khác nhau theo JDK/nền tảng; phải kiểm tra giá trị JVM thực sự nhìn thấy.
3. **Thay đổi trong chương trình**: **TimeZone.setDefault(...)** có thể đổi timezone mặc định trong tiến trình; các lần gọi **ZoneId.systemDefault()** sau đó có thể nhận giá trị khác.

~~~text
Cấu hình JVM / hệ điều hành / container
                 |
                 v
      TimeZone mặc định của JVM
                 |
                 v
        ZoneId.systemDefault()
                 |
       +---------+----------+
       |                    |
       v                    v
 LocalDate.now()      ZonedDateTime.now()
 dùng ngày vùng đó    dùng giờ và vùng đó
~~~

Sơ đồ là mô tả khái niệm, không phải lời bảo đảm rằng mọi JVM đều đọc biến môi trường **TZ** theo một cách duy nhất.

Một ZoneId đã được lưu vào biến là giá trị ổn định của chính đối tượng đó; **gọi lại systemDefault()** sau khi mặc định toàn cục thay đổi mới có thể trả ZoneId mới.

## 3. Cùng Instant, khác ngày địa phương

Xét sự kiện xảy ra đúng **2026-01-01T01:00:00Z**. Nếu hiển thị tại ba vùng, kết quả là:

| ZoneId | Ngày giờ từ cùng một Instant |
|---|---|
| UTC | 2026-01-01T01:00 |
| Asia/Ho_Chi_Minh | 2026-01-01T08:00 |
| America/Los_Angeles | 2025-12-31T17:00 |

**2025-12-31** tại Los Angeles và **2026-01-01** tại UTC đều là cách trình bày **cùng một sự kiện**. Nếu ngày báo cáo doanh thu phải theo Los Angeles thì dùng UTC hoặc timezone mặc định khác sẽ tính sai nhóm ngày gần nửa đêm.

Tương tự, ngày sinh là **LocalDate** và không nên quy đổi qua UTC chỉ để lưu trữ. Ngày trong lịch của khách hàng và timestamp của sự kiện là hai ý nghĩa khác nhau.

## 4. Ví dụ Java 17+: thay timezone ngay khi khởi động

Tạo tệp **SystemDefaultZoneDemo.java**:

~~~java
import java.time.Instant;
import java.time.ZoneId;

public class SystemDefaultZoneDemo {
    public static void main(String[] args) {
        ZoneId systemZone = ZoneId.systemDefault();
        Instant event = Instant.parse("2026-01-01T01:00:00Z");

        System.out.println("defaultZone=" + systemZone);
        System.out.println("event=" + event);
        System.out.println("localDate=" +
                event.atZone(systemZone).toLocalDate());
        System.out.println("localDateTime=" +
                event.atZone(systemZone).toLocalDateTime());
    }
}
~~~

Biên dịch:

~~~bash
javac SystemDefaultZoneDemo.java
~~~

Chạy trong hai tiến trình JVM khác nhau:

~~~bash
java -Duser.timezone=UTC SystemDefaultZoneDemo
java -Duser.timezone=America/Los_Angeles SystemDefaultZoneDemo
~~~

Đầu ra của **lệnh thứ nhất**:

~~~text
defaultZone=UTC
event=2026-01-01T01:00:00Z
localDate=2026-01-01
localDateTime=2026-01-01T01:00
~~~

Đầu ra của **lệnh thứ hai**:

~~~text
defaultZone=America/Los_Angeles
event=2026-01-01T01:00:00Z
localDate=2025-12-31
localDateTime=2025-12-31T17:00
~~~

Điểm quan trọng:

- **event** không đổi. Đây vẫn là cùng một mốc trên trục thời gian.
- **defaultZone** là cấu hình JVM, thay đổi theo tham số khởi động.
- **localDate** có thể đổi **cả ngày và năm**.
- **localDateTime** phản ánh giờ đồng hồ của vùng đã chọn.

**-Duser.timezone** phải được truyền như đối số JVM trước tên class/JAR theo cú pháp lệnh Java; đừng nhầm nó với đối số của hàm main. Ví dụ khi chạy JAR: **java -Duser.timezone=UTC -jar app.jar**.

Tên vùng nên là ID hợp lệ, ưu tiên tên IANA như **America/Los_Angeles**. Với cấu hình không hợp lệ, cơ chế fallback của **TimeZone** có thể khiến ứng dụng vẫn chạy theo một mặc định khác; nên xác minh giá trị thực tế thay vì mặc nhiên coi mọi typo đều gây lỗi.

## 5. Những API now() bị ảnh hưởng như thế nào?

| API | Ý nghĩa và ảnh hưởng của timezone mặc định |
|---|---|
| **Instant.now()** | Lấy thời điểm từ đồng hồ hệ thống; Instant không chứa ZoneId |
| **LocalDate.now()** | Lấy ngày địa phương theo timezone mặc định |
| **LocalTime.now()** | Lấy giờ địa phương theo timezone mặc định |
| **LocalDateTime.now()** | Lấy ngày giờ tường theo timezone mặc định, không giữ ZoneId |
| **ZonedDateTime.now()** | Lấy ngày giờ cùng vùng/offset theo mặc định |
| **OffsetDateTime.now()** | Lấy ngày giờ cùng offset xác định từ mặc định |
| **LocalDate.now(zone)** | Lấy ngày theo ZoneId tường minh |
| **ZonedDateTime.now(clock)** | Lấy giá trị theo nguồn Clock và ZoneId của Clock |
| **Instant.now(clock)** | Lấy thời điểm theo Clock, có thể cố định để kiểm thử |

Tại một Instant cố định, **Instant** luôn giống nhau dù hiển thị qua timezone nào. Nhưng kết quả **LocalDate.now()** trên hai máy khác zone có thể khác ngày nếu được đọc cùng lúc gần ranh giới ngày.

Các hàm **now()** được gọi liên tiếp thực tế cũng đọc đồng hồ ở các mốc khác nhau. Nếu muốn nhiều phép tính dùng **cùng một thời điểm quan sát**, nên lấy Instant một lần:

~~~java
Instant sampled = Instant.now(clock);
LocalDate inTokyo = sampled.atZone(ZoneId.of("Asia/Tokyo"))
        .toLocalDate();
LocalDate inParis = sampled.atZone(ZoneId.of("Europe/Paris"))
        .toLocalDate();
~~~

Đây là đoạn minh họa với biến **clock** đã được cung cấp từ bên ngoài. Không có lý do nghiệp vụ nào buộc ngày của Tokyo và Paris phải giống nhau tại mọi Instant.

### Múi giờ của máy không phải múi giờ của người dùng

Nếu một nền tảng chạy trên container ở UTC, nhưng khách hàng tại Việt Nam cần “ngày hiện tại”, hãy dùng **LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))** hoặc một Clock dùng zone tương ứng, thay vì **LocalDate.now()**.

Nếu hệ thống có nhiều cửa hàng, hãy lưu **ZoneId của từng cửa hàng**. Đừng đổi default của toàn JVM mỗi khi xử lý một đơn hàng.

## 6. Thay đổi timezone mặc định khi JVM đang chạy

Một giá trị trong **ZoneId.systemDefault()** có thể thay đổi giữa hai lời gọi nếu có code gọi **TimeZone.setDefault(...)**. Trạng thái này ảnh hưởng phạm vi **toàn JVM**, không thuộc một request riêng.

Tạo tệp **ChangingDefaultZoneDemo.java**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.TimeZone;

public class ChangingDefaultZoneDemo {
    public static void main(String[] args) {
        TimeZone original = TimeZone.getDefault();

        try {
            TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
            ZoneId capturedZone = ZoneId.systemDefault();
            Clock capturedClock = Clock.systemDefaultZone();

            TimeZone.setDefault(
                    TimeZone.getTimeZone("America/Los_Angeles")
            );
            Instant event = Instant.parse("2026-01-01T01:00:00Z");

            System.out.println("capturedZone=" + capturedZone);
            System.out.println("currentDefault=" +
                    ZoneId.systemDefault());
            System.out.println("capturedClockZone=" +
                    capturedClock.getZone());
            System.out.println("event=" + event);
            System.out.println("utcDate=" +
                    event.atZone(capturedZone).toLocalDate());
            System.out.println("currentDate=" +
                    event.atZone(ZoneId.systemDefault()).toLocalDate());
        } finally {
            TimeZone.setDefault(original);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ChangingDefaultZoneDemo.java
java ChangingDefaultZoneDemo
~~~

Stdout:

~~~text
capturedZone=UTC
currentDefault=America/Los_Angeles
capturedClockZone=UTC
event=2026-01-01T01:00:00Z
utcDate=2026-01-01
currentDate=2025-12-31
~~~

**Giải thích:**

1. **capturedZone** là một ZoneId đã được lấy tại lúc mặc định là UTC; giá trị ấy không tự đổi.
2. **ZoneId.systemDefault()** lần sau phản ánh TimeZone mới.
3. **Clock.systemDefaultZone()** tạo Clock với ZoneId được lấy lúc khởi tạo; **capturedClock.getZone()** vẫn là UTC.
4. Giá trị của **event** vẫn là Instant cũ; chỉ cách suy ra ngày thay đổi.
5. **finally** khôi phục TimeZone để ví dụ không vô tình tác động mã chạy sau đó.

**Không dùng TimeZone.setDefault(...) để xử lý từng khách hàng.** Trong một server nhiều luồng, request A thay timezone mặc định có thể khiến request B hoặc thư viện khác đọc sai vùng. Tránh sửa trạng thái toàn tiến trình trong logic nghiệp vụ.

**System.setProperty("user.timezone", "...")** giữa lúc JVM đang chạy cũng không phải API đổi timezone nhất quán: TimeZone có thể đã xác định hoặc cache giá trị, trong khi các Clock/ZoneId đã tạo vẫn giữ vùng cũ. Cấu hình ở startup hoặc truyền ZoneId trực tiếp là cách dễ kiểm soát hơn.

## 7. Laptop, CI, Docker và production: vì sao khác nhau?

**Kịch bản điển hình:** developer chạy laptop có timezone Việt Nam và test kiểm tra **LocalDate.now()** là ngày hôm nay ở Việt Nam. Khi test chạy trên runner UTC, gần 00:00 tại Việt Nam kết quả có thể thuộc ngày hôm trước. Code không đổi nhưng giả định môi trường đã bị lộ.

| Môi trường | Nguồn cấu hình có thể thấy | Rủi ro |
|---|---|---|
| Laptop | Cấu hình timezone hệ điều hành | Developer vô tình coi timezone của mình là chuẩn |
| CI | Runner/container đặt UTC | Test gần ranh giới ngày thiếu ổn định |
| Container | Image/OS, TZ, lệnh khởi động Java | Timezone của container có thể khác host |
| Máy production | Thiết lập vận hành của server/JDK | Lịch xử lý hoặc ngày báo cáo bị dịch |
| JVM với -Duser.timezone | Giá trị gán tường minh khi startup | Ổn định hơn cho API ngầm đọc default |
| JVM gọi TimeZone.setDefault | Thay đổi ở runtime | Thư viện/luồng khác quan sát default mới |

**Đừng dựa riêng vào TZ hoặc timezone của host** để kết luận Java đang dùng vùng nào. Cách JVM phát hiện timezone phụ thuộc môi trường, hệ điều hành, bản JDK và cấu hình khác. Hãy quan sát chính JVM được triển khai.

### Chương trình kiểm tra thực tế

Tạo tệp **DefaultZoneProbe.java**:

~~~java
import java.time.ZoneId;
import java.util.TimeZone;

public class DefaultZoneProbe {
    public static void main(String[] args) {
        System.out.println("zoneId=" + ZoneId.systemDefault());
        System.out.println("timeZoneId=" +
                TimeZone.getDefault().getID());
        System.out.println("user.timezone=" +
                System.getProperty("user.timezone"));
    }
}
~~~

Chạy:

~~~bash
javac DefaultZoneProbe.java
java -Duser.timezone=Asia/Ho_Chi_Minh DefaultZoneProbe
~~~

Stdout kỳ vọng với cấu hình trên:

~~~text
zoneId=Asia/Ho_Chi_Minh
timeZoneId=Asia/Ho_Chi_Minh
user.timezone=Asia/Ho_Chi_Minh
~~~

Nếu có khác biệt bất ngờ, kiểm tra toàn bộ lệnh khởi động, JDK, timezone mặc định lúc runtime và code có gọi **TimeZone.setDefault** hay không. **System.getProperty("user.timezone")** không phải bằng chứng duy nhất về default hiện tại nếu đã có thay đổi runtime.

## 8. Thiết kế an toàn với ZoneId và Clock tường minh

**Thực hành tốt cho nghiệp vụ:** xác định riêng **nguồn “bây giờ”** và **vùng của chính sách**.

- **Clock** cung cấp thời gian hiện tại, thay được bằng Clock cố định khi test.
- **ZoneId** xác định vùng cần dùng để suy ra ngày/giờ nghiệp vụ.
- **Instant** lưu thời điểm sự kiện xảy ra, không cần gắn zone.
- **LocalDate** lưu ngày theo một lịch khi nghiệp vụ chỉ cần ngày.

Tạo tệp **BusinessDateDemo.java**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;

public class BusinessDateDemo {
    private final Clock clock;
    private final ZoneId businessZone;

    public BusinessDateDemo(Clock clock, ZoneId businessZone) {
        this.clock = Objects.requireNonNull(clock, "clock");
        this.businessZone =
                Objects.requireNonNull(businessZone, "businessZone");
    }

    public LocalDate currentBusinessDate() {
        Instant sampled = Instant.now(clock);
        return sampled.atZone(businessZone).toLocalDate();
    }

    public static void main(String[] args) {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-01-01T01:00:00Z"),
                ZoneOffset.UTC
        );

        BusinessDateDemo utc = new BusinessDateDemo(
                fixed, ZoneId.of("UTC")
        );
        BusinessDateDemo la = new BusinessDateDemo(
                fixed, ZoneId.of("America/Los_Angeles")
        );

        System.out.println("utc=" + utc.currentBusinessDate());
        System.out.println("losAngeles=" +
                la.currentBusinessDate());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BusinessDateDemo.java
java BusinessDateDemo
~~~

Stdout:

~~~text
utc=2026-01-01
losAngeles=2025-12-31
~~~

**Vì sao cách này ổn định?** Cả hai service dùng cùng **Clock.fixed** nên test không lệ thuộc thời gian thật hoặc timezone máy. Mỗi service áp dụng **businessZone** đúng chính sách của mình. Có thể triển khai production bằng **Clock.systemUTC()** và khai báo ZoneId theo cấu hình cửa hàng/người dùng, thay vì đọc mặc định môi trường ở mọi chỗ.

Khi chỉ cần ngày tại vùng cụ thể, có thể viết ngắn hơn:

~~~java
LocalDate todayAtStore = LocalDate.now(
        ZoneId.of("Asia/Ho_Chi_Minh")
);
~~~

Nhưng khi cần test tự động với một “bây giờ” đã xác định, **Clock.fixed** thích hợp hơn.

## 9. Những quy tắc kinh doanh bị ảnh hưởng mạnh bởi timezone

### 9.1. Báo cáo theo ngày

Yêu cầu “lọc các đơn phát sinh ngày 01/01 theo cửa hàng Los Angeles” phải tính **ranh giới ngày địa phương**, rồi quy sang hai Instant:

~~~java
ZoneId storeZone = ZoneId.of("America/Los_Angeles");
LocalDate businessDay = LocalDate.of(2026, 1, 1);

Instant start = businessDay.atStartOfDay(storeZone)
        .toInstant();
Instant endExclusive = businessDay.plusDays(1)
        .atStartOfDay(storeZone)
        .toInstant();
~~~

Đây là đoạn minh họa với các import thuộc gói **java.time**. Trong truy vấn, dùng khoảng:

~~~text
createdAt >= start AND createdAt < endExclusive
~~~

Mô hình **[start, endExclusive)** tránh phải tự tạo 23:59:59.999 và không giả định mọi ngày địa phương dài đúng 24 giờ. Tại một số vùng có DST, ngày địa phương có thể có 23 hoặc 25 giờ.

Nếu dùng **ZoneId.systemDefault()** cho cửa hàng ở LA, việc chuyển server từ LA sang UTC có thể khiến dữ liệu được tính cho sai ngày.

### 9.2. Hợp đồng hết hạn cuối ngày

“Hết hiệu lực cuối ngày 31/12 theo giờ của người ký” yêu cầu biết **LocalDate** và **ZoneId** chính sách. Nếu cuối ngày được bao gồm, thường lấy **đầu ngày kế tiếp ở zone đó** làm **endExclusive**. Không tự lấy nửa đêm UTC nếu ý nghĩa hợp đồng là ngày địa phương.

### 9.3. Lịch hẹn và DST

Giờ “09:00 mỗi thứ Hai tại Paris” cần **LocalTime + quy tắc lặp + ZoneId**, rồi mỗi lần diễn ra được giải quyết theo quy tắc vùng. Nếu dùng timezone mặc định của server, chuyển triển khai từ Paris sang UTC có thể làm sai lịch hẹn.

Ở nơi đổi giờ mùa hè, một LocalDateTime có thể nằm trong khoảng **gap** (không tồn tại) hoặc **overlap** (có hai offset). Việc chuyển sang Instant phải có chính sách rõ ràng; **ZoneId.systemDefault()** không tự biết vùng mà người dùng định đặt lịch.

### 9.4. Scheduler và cron

Một scheduler có thể dùng timezone được cấu hình riêng, hoặc mặc định theo môi trường. Cách xử lý DST, chạy bù sau downtime và giờ địa phương là hợp đồng của từng framework. Cần định rõ ZoneId ở lịch, kiểm tra framework đang dùng, và tránh giả định chỉ cần -Duser.timezone là tất cả scheduler sẽ chạy theo vùng mong muốn.

### 9.5. Log, audit và sự kiện

Lưu **createdAt** dưới dạng **Instant** phù hợp để ghi dấu thời điểm. Khi hiển thị hoặc báo cáo theo ngày, áp dụng đúng ZoneId. Các server khác nhau vẫn có thể có sai số đồng hồ, nên timestamp không tự bảo đảm thứ tự sự kiện tuyệt đối trong hệ thống phân tán.

## 10. API và cơ sở dữ liệu

Một payload minh họa:

~~~json
{
  "createdAt": "2026-01-01T01:00:00Z",
  "businessZone": "America/Los_Angeles",
  "businessDate": "2025-12-31"
}
~~~

Ở đây:

- **createdAt** là Instant (sự kiện đã xảy ra khi nào).
- **businessZone** là danh tính vùng cần cho chính sách.
- **businessDate** là ngày được diễn giải theo vùng đó, có thể là giá trị được tính từ hai trường trước.

Trong hệ thống thật, cần xác định trường nào là nguồn chân lý và trường nào là dữ liệu suy ra để tránh mâu thuẫn.

Không coi **LocalDateTime** trong cơ sở dữ liệu là UTC chỉ vì server chạy UTC. Một kiểu SQL **TIMESTAMP WITHOUT TIME ZONE** không tự có ZoneId. Kiểu như PostgreSQL **TIMESTAMPTZ** biểu diễn thời điểm nhưng không lưu nguyên tên ZoneId. Nếu phải giữ **Europe/Paris**, lưu vùng trong cột riêng. Driver/ORM/phiên kết nối có thể có quy tắc chuyển đổi timezone của chính chúng; cần thử vòng **ghi → đọc lại** ở ranh giới ngày.

Timezone của **database session** và timezone mặc định của **JVM** là hai cấu hình khác nhau. Thay đổi một cái không chứng minh cái còn lại đồng bộ, nên cần kiểm tra cả hai ở đường đi dữ liệu thực tế.

## 11. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Tưởng timezone mặc định luôn là Asia/Ho_Chi_Minh | Chạy CI/container có thể trả ngày khác | Cấu hình/kiểm tra JVM và truyền ZoneId nghiệp vụ |
| Dùng LocalDate.now() cho ngày chốt sổ cửa hàng | Ngày phụ thuộc server | Dùng LocalDate.now(storeZone) hoặc Clock |
| Lưu LocalDateTime.now() làm timestamp UTC | Mất offset và ZoneId | Lưu Instant |
| Hiển thị mọi người dùng theo systemDefault() | Giờ hiển thị sai vùng người dùng | Truyền ZoneId của người dùng |
| Đổi TimeZone.setDefault theo mỗi request | Trạng thái toàn cục ảnh hưởng request khác | Không đổi default; truyền ZoneId |
| Đọc một ZoneId rồi nghĩ nó tự cập nhật | Giá trị đã lấy vẫn là vùng cũ | Quản lý cấu hình rõ ràng |
| System.setProperty("user.timezone",...) ở runtime rồi mong mọi thư viện đổi ngay | Cache/Clock cũ có thể giữ vùng khác | Cấu hình ở startup |
| Giả định biến TZ luôn được JVM xử lý y hệt trên mọi nền tảng | Phụ thuộc JDK/OS | Quan sát ZoneId.systemDefault thực tế |
| Tưởng đổi zone sẽ đổi Instant | Nhầm thời điểm với hiển thị | Instant.atZone(zone) để hiển thị |
| Dùng offset +07:00 thay cho tên vùng lịch hẹn tương lai | Mất quy tắc timezone | Lưu ZoneId như Asia/Ho_Chi_Minh |
| Cộng 24 giờ để lấy cùng giờ ngày mai ở vùng DST | Sai giờ địa phương quanh chuyển DST | Thao tác lịch với ZonedDateTime/LocalDate |
| Cắt ngày báo cáo theo 00:00 UTC | Sai nhóm bản ghi ở vùng khác | Lấy start/endExclusive theo ZoneId |
| Test chỉ dùng giờ giữa trưa | Không phát hiện lệch ngày | Thử gần 00:00, đổi năm, DST |

## 12. Checklist khi triển khai và kiểm thử

1. **Ngày/giờ thuộc về vùng nào?** Người dùng, cửa hàng, hợp đồng, sự kiện hay UTC?
2. **Có chỗ nào dùng ZoneId.systemDefault() như vùng nghiệp vụ không?** Kiểm tra xem điều đó có chủ ý hay là phụ thuộc ngầm.
3. **Cấu hình mặc định JVM thực tế ở production là gì?** Ghi nhận trong lúc startup và khi điều tra sự cố.
4. **Có dùng TimeZone.setDefault tại runtime không?** Nếu có, xem rủi ro toàn tiến trình.
5. **Logic dùng Clock và ZoneId tường minh chưa?** Điều này giúp kiểm thử.
6. **Đã thử cùng Instant ở UTC và vùng khác ranh giới ngày chưa?**
7. **Ngày địa phương có thể dài 23/25 giờ vì DST không?** Dùng đầu ngày theo ZoneId phù hợp.
8. **API/database có bảo toàn ngữ nghĩa khi ghi và đọc lại không?**
9. **Lịch chạy định kỳ có zone và chính sách DST rõ không?**
10. **Có tách việc ghi sự kiện bằng Instant khỏi việc hiển thị theo ZoneId không?**

### Câu hỏi tự kiểm tra

**1. ZoneId.systemDefault() trả về timezone người đang dùng trình duyệt?**  
Không. Nó là timezone mặc định của JVM chạy ứng dụng.

**2. Nếu chạy -Duser.timezone=UTC và -Duser.timezone=America/Los_Angeles, một Instant cố định có khác?**  
Không. Chỉ kết quả diễn giải LocalDate/LocalDateTime theo vùng có thể khác.

**3. Vì sao LocalDate.now() có thể đổi ngày khi deploy?**  
Vì nó dùng timezone mặc định, mỗi môi trường có thể đặt vùng khác.

**4. Sau TimeZone.setDefault(...), ZoneId đã lưu trước đó tự đổi không?**  
Không. Gọi systemDefault lần mới có thể quan sát vùng mới.

**5. Nên chọn Clock.systemUTC() hay ZoneId.systemDefault() cho ngày báo cáo cửa hàng?**  
Dùng Clock.systemUTC() làm nguồn lấy Instant được; ngày báo cáo phải áp dụng **ZoneId cửa hàng tường minh**.

**6. Có nên dùng TimeZone.setDefault theo request không?**  
Không. Mặc định là trạng thái toàn JVM, có thể ảnh hưởng luồng khác.

**7. Cách tính báo cáo một ngày tại vùng có DST?**  
Lấy Instant đầu ngày địa phương và Instant đầu ngày kế tiếp làm khoảng **[start, endExclusive)** theo ZoneId.

**Ghi nhớ:** **ZoneId.systemDefault() phản ánh cấu hình môi trường của JVM**, vì thế code phụ thuộc nó có thể thay đổi hành vi giữa các máy. **Instant** là thời điểm tuyệt đối; **Clock** kiểm soát nguồn “bây giờ”; **ZoneId tường minh** kiểm soát ngày giờ theo nghiệp vụ. Hãy chọn vùng theo dữ liệu và hợp đồng nghiệp vụ thay vì để nơi triển khai quyết định ngầm.
