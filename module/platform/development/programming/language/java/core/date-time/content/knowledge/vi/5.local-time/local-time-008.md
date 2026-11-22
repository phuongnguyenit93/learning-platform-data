# Mô hình hóa giờ mở cửa và khoảng giờ đi qua nửa đêm với LocalTime trong Java

## 1. Bài toán và mục tiêu

Một cửa hàng mở **09:00–17:00** và quán ăn mở **22:00–02:00 sáng hôm sau** cùng được mô tả bằng hai giờ đồng hồ, nhưng cách kiểm tra chúng khác nhau. Trong khoảng 22:00–02:00, cả **23:00 hôm nay** và **01:00 ngày mai** đều có thể là lúc cửa hàng đang mở.

**LocalTime** trong **java.time** diễn tả giờ, phút, giây và nano trên đồng hồ trong một ngày, nhưng **không chứa ngày, múi giờ hoặc UTC offset**. Vì vậy, để mô hình hóa lịch mở cửa, cần có quy tắc xác định giờ bắt đầu, giờ kết thúc, việc đi qua nửa đêm và ngày bắt đầu ca. Nếu hỏi một thời điểm thực tế, phải kết hợp thêm ngày và ZoneId.

Sau bài học bạn sẽ:

- Chọn quy tắc biên giờ mở/đóng rõ ràng.
- Kiểm tra khoảng giờ thông thường và khoảng đi qua nửa đêm bằng LocalTime.
- Xử lý **00:00**, cặp giờ mở và đóng bằng nhau, lịch mở 24 giờ và lịch đóng cửa.
- Gắn khoảng giờ sau nửa đêm với đúng **ngày bắt đầu ca** khi lịch hoạt động theo thứ trong tuần.
- Tính ngày-giờ đóng cửa và thời lượng ca danh nghĩa.
- Nhận biết khi LocalTime chưa đủ, đặc biệt với giờ mùa hè (DST), nghỉ lễ và tính giờ làm thực tế.

## 2. LocalTime mô tả giờ đồng hồ, không phải một thời điểm

Tạo và so sánh giờ:

~~~java
LocalTime opening = LocalTime.of(22, 0);
LocalTime closing = LocalTime.of(2, 0);
LocalTime check = LocalTime.parse("23:15");

System.out.println(opening); // 22:00
System.out.println(closing); // 02:00
System.out.println(check);   // 23:15
~~~

Đây là **đoạn trích minh họa**: cần import **java.time.LocalTime** và đặt trong phương thức. **LocalTime** là immutable. Phép **plusHours**, **minusMinutes** trả về đối tượng mới và có thể quay vòng qua 00:00, nhưng không ghi số ngày đã vượt qua.

Ví dụ **LocalTime.of(23, 0).plusHours(3)** trả **02:00**, không nói đó là 02:00 của ngày nào. Nếu cần giữ ngày, hãy dùng **LocalDateTime**.

| Kiểu | Lưu gì? | Ý nghĩa trong bài toán mở cửa |
| --- | --- | --- |
| **LocalTime** | Giờ, phút, giây, nano | 22:00 hoặc 02:00 trong lịch lặp |
| **LocalDate** | Ngày theo lịch ISO | Ngày bắt đầu một ca cụ thể |
| **DayOfWeek** | Thứ trong tuần | Ca được phép bắt đầu vào thứ nào |
| **LocalDateTime** | Ngày và giờ địa phương | 22:00 thứ Hai hoặc 02:00 thứ Ba |
| **ZoneId** | Vùng và quy tắc offset theo thời gian | Múi giờ của địa điểm |
| **ZonedDateTime** | Ngày giờ tại vùng cụ thể | Diễn giải ca trong múi giờ có DST |
| **Instant** | Mốc tuyệt đối trên dòng thời gian | Check-in, check-out, timestamp sự kiện |
| **Duration** | Khoảng dựa trên giây/nano | Thời lượng thực giữa hai Instant |

**LocalTime.MIDNIGHT** là **00:00**; **LocalTime.NOON** là **12:00**. LocalTime nhận giờ từ 0 đến 23: không thể tạo trực tiếp **24:00** bằng LocalTime.of(24, 0). Nếu khoảng đóng đúng nửa đêm, hãy biểu diễn bằng **00:00 ngày hôm sau** khi dựng LocalDateTime.

## 3. Chọn quy tắc nửa mở [giờ mở, giờ đóng)

Thông thường nên dùng **khoảng nửa mở**: một cửa hàng được xem là mở tại giờ bắt đầu và đóng đúng tại mốc kết thúc.

- Với **09:00–17:00**, **09:00** là mở.
- **16:59:59.999999999** vẫn là mở.
- **17:00** là đóng.

Quy tắc **[start, end)** có lợi khi hai ca nối nhau, chẳng hạn 09:00–12:00 và 12:00–17:00: điểm 12:00 thuộc ca thứ hai, không được tính hai lần. Nếu nghiệp vụ yêu cầu phục vụ tại đúng giờ đóng, phải quy định lại điều kiện biên; không để mỗi module tự chọn.

### Ba trường hợp phải tách riêng

| Quan hệ hai mốc | Ví dụ | Diễn giải | Kiểm tra giờ t |
| --- | --- | --- | --- |
| **start < end** | 09:00–17:00 | Khoảng trong cùng ngày | t >= start **và** t < end |
| **start > end** | 22:00–02:00 | Đi qua nửa đêm | t >= start **hoặc** t < end |
| **start = end** | 00:00–00:00 | Dữ liệu mơ hồ | Phải có chính sách riêng |

Với **start < end**, dùng phép **AND**. Với **start > end**, cần **OR** vì khoảng hoạt động gồm đoạn cuối ngày và đầu ngày hôm sau. Với **start = end**, hai cách hiểu “đóng cả ngày” và “mở đủ 24 giờ” đều có thể xuất hiện trong hệ thống thực, nên không được suy diễn từ hai mốc bằng nhau.

Một mô hình minh bạch:

- **CLOSED**: không có khung hoạt động hoặc có trạng thái đóng riêng.
- **ALL_DAY**: mở đủ 24 giờ, có trạng thái riêng.
- **NORMAL_WINDOW**: hai mốc mở/đóng khác nhau, thời lượng danh nghĩa lớn hơn 0 và nhỏ hơn 24 giờ.

Trong ví dụ Java bên dưới, constructor **từ chối hai mốc bằng nhau**. Việc này buộc người nhập chọn rõ mở 24 giờ hay đóng cả ngày. Với cửa hàng hoạt động liên tục qua nhiều ngày, nên có kiểu trạng thái ALL_DAY hoặc mô hình khoảng ngày-giờ cụ thể.

## 4. Hàm chứa giờ: hai nhánh đơn giản

~~~java
static boolean contains(
        LocalTime opens, LocalTime closes, LocalTime t) {
    if (opens.equals(closes)) {
        throw new IllegalArgumentException(
                "Use explicit CLOSED or ALL_DAY status");
    }
    if (opens.isBefore(closes)) {
        return !t.isBefore(opens) && t.isBefore(closes);
    }
    return !t.isBefore(opens) || t.isBefore(closes);
}
~~~

Đoạn trên là **phương thức minh họa**: cần đặt trong class và import LocalTime. Vì LocalTime không định nghĩa các toán tử so sánh >= và < trong Java, ta dùng **isBefore**, **isAfter** hoặc **equals**.

Lỗi thường gặp là dùng điều kiện:

~~~java
// SAI cho khoảng đi qua nửa đêm.
boolean open = !t.isBefore(opens) && t.isBefore(closes);
~~~

Nếu mở **22:00** và đóng **02:00**, không có giờ nào vừa >= 22:00 vừa < 02:00 trên cùng một vòng đồng hồ. Kết quả luôn false. Với ca qua đêm phải dùng **OR** ở nhánh thứ hai.

### Bảng kiểm tra biên

| Khoảng | Giờ đang xét | Kết quả |
| --- | --- | --- |
| 09:00–17:00 | 08:59 | Đóng |
| 09:00–17:00 | 09:00 | Mở |
| 09:00–17:00 | 16:59 | Mở |
| 09:00–17:00 | 17:00 | Đóng |
| 22:00–02:00 | 21:59 | Đóng |
| 22:00–02:00 | 22:00 | Mở |
| 22:00–02:00 | 23:59 | Mở |
| 22:00–02:00 | 00:00 | Mở |
| 22:00–02:00 | 01:59 | Mở |
| 22:00–02:00 | 02:00 | Đóng |
| 22:00–02:00 | 12:00 | Đóng |
| 22:00–00:00 | 23:00 | Mở |
| 22:00–00:00 | 00:00 | Đóng |

Giờ nửa đêm **00:00** có thể được bao gồm trong khoảng 22:00–02:00, vì thời điểm đóng là **02:00**. Nhưng khoảng 22:00–00:00 kết thúc **đúng 00:00 ngày sau**, nên 00:00 không còn thuộc khoảng.

## 5. Ca qua nửa đêm thuộc về ngày nào?

Chỉ kiểm tra **LocalTime** là chưa đủ cho lịch hoạt động theo thứ. Giả sử quán chỉ mở **thứ Hai 22:00 đến thứ Ba 02:00**.

- **Thứ Hai 23:00**: mở.
- **Thứ Ba 01:00**: mở, vì vẫn thuộc ca bắt đầu tối thứ Hai.
- **Thứ Ba 23:00**: đóng nếu không có ca bắt đầu thứ Ba, dù 23:00 nằm trong khung giờ 22:00–02:00 khi bỏ qua ngày.
- **Thứ Ba 02:00**: đóng vì là điểm cuối bị loại.

Nên quy định các ngày trong tuần là **ngày bắt đầu ca** (opening date, anchor date). Khi giờ đang xét nằm trong khoảng qua nửa đêm:

1. Nếu **t >= opens**, ngày bắt đầu ca là ngày của LocalDateTime đang xét.
2. Nếu **t < closes**, ngày bắt đầu ca là **ngày hôm trước**.
3. Nếu **t** không nằm trong khung, kết quả là không mở theo khung này.

Ví dụ ca 22:00–02:00:

| Thời điểm kiểm tra | Thuộc khung giờ? | Ngày bắt đầu ca |
| --- | --- | --- |
| Thứ Hai 26/10/2026 23:00 | Có | 26/10/2026 |
| Thứ Ba 27/10/2026 00:00 | Có | 26/10/2026 |
| Thứ Ba 27/10/2026 01:00 | Có | 26/10/2026 |
| Thứ Ba 27/10/2026 02:00 | Không | Không áp dụng |
| Thứ Ba 27/10/2026 23:00 | Có nếu chỉ xét giờ | 27/10/2026: không thuộc lịch chỉ mở thứ Hai |

Lưu ý lịch nghỉ lễ có thể được áp dụng theo **ngày bắt đầu ca** hoặc **ngày lịch thực tế đang diễn ra**. Ví dụ luật bắt buộc đóng cửa từ 00:00 ngày lễ có thể cắt ngang ca tối hôm trước. Chính sách này phải được định nghĩa độc lập với thao tác LocalTime.

## 6. Ví dụ Java 17+ hoàn chỉnh

Lưu mã vào file **OpeningHoursDemo.java**:

~~~java
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;

public class OpeningHoursDemo {
    record DailyWindow(LocalTime opens, LocalTime closes) {
        DailyWindow {
            Objects.requireNonNull(opens, "opens");
            Objects.requireNonNull(closes, "closes");

            if (opens.equals(closes)) {
                throw new IllegalArgumentException(
                        "Choose explicit CLOSED or ALL_DAY mode");
            }
        }

        boolean crossesMidnight() {
            return opens.isAfter(closes);
        }

        // Giờ mở được tính, giờ đóng không được tính.
        boolean contains(LocalTime value) {
            Objects.requireNonNull(value, "value");

            if (!crossesMidnight()) {
                return !value.isBefore(opens)
                        && value.isBefore(closes);
            }
            return !value.isBefore(opens)
                    || value.isBefore(closes);
        }

        // Chỉ gọi khi giờ đang xét thuộc khoảng này.
        LocalDate openingDateFor(LocalDateTime at) {
            if (!contains(at.toLocalTime())) {
                throw new IllegalArgumentException(
                        "Outside the opening window");
            }

            if (crossesMidnight()
                    && at.toLocalTime().isBefore(closes)) {
                return at.toLocalDate().minusDays(1);
            }
            return at.toLocalDate();
        }

        // operatingDays là ngày bắt đầu ca trong tuần.
        boolean isOpenOn(
                LocalDateTime at, Set<DayOfWeek> operatingDays) {
            return contains(at.toLocalTime())
                    && operatingDays.contains(
                            openingDateFor(at).getDayOfWeek());
        }

        LocalDateTime closingDateTimeFor(LocalDate openingDate) {
            LocalDate endDate = crossesMidnight()
                    ? openingDate.plusDays(1)
                    : openingDate;
            return LocalDateTime.of(endDate, closes);
        }

        // Độ dài DANH NGHĨA trên đồng hồ, chưa xét DST.
        Duration nominalDuration() {
            Duration value = Duration.between(opens, closes);
            return crossesMidnight()
                    ? value.plusDays(1)
                    : value;
        }
    }

    public static void main(String[] args) {
        DailyWindow office = new DailyWindow(
                LocalTime.of(9, 0), LocalTime.of(17, 0));
        DailyWindow night = new DailyWindow(
                LocalTime.of(22, 0), LocalTime.of(2, 0));

        System.out.println("Office 09:00: " +
                office.contains(LocalTime.of(9, 0)));
        System.out.println("Office 17:00: " +
                office.contains(LocalTime.of(17, 0)));
        System.out.println("Night 23:00: " +
                night.contains(LocalTime.of(23, 0)));
        System.out.println("Night 01:00: " +
                night.contains(LocalTime.of(1, 0)));
        System.out.println("Night 02:00: " +
                night.contains(LocalTime.of(2, 0)));
        System.out.println("Nominal night duration: " +
                night.nominalDuration());

        Set<DayOfWeek> mondayOnly =
                EnumSet.of(DayOfWeek.MONDAY);
        LocalDateTime monday2300 =
                LocalDateTime.of(2026, 10, 26, 23, 0);
        LocalDateTime tuesday0100 =
                LocalDateTime.of(2026, 10, 27, 1, 0);
        LocalDateTime tuesday2300 =
                LocalDateTime.of(2026, 10, 27, 23, 0);

        System.out.println("Monday 23:00: " +
                night.isOpenOn(monday2300, mondayOnly));
        System.out.println("Tuesday 01:00: " +
                night.isOpenOn(tuesday0100, mondayOnly));
        System.out.println("Tuesday 23:00: " +
                night.isOpenOn(tuesday2300, mondayOnly));
        System.out.println("Opening date for Tuesday 01:00: " +
                night.openingDateFor(tuesday0100));
        System.out.println("Closing date-time for Monday shift: " +
                night.closingDateTimeFor(
                        LocalDate.of(2026, 10, 26)));
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 OpeningHoursDemo.java
java OpeningHoursDemo
~~~

**Đầu ra chuẩn:**

~~~text
Office 09:00: true
Office 17:00: false
Night 23:00: true
Night 01:00: true
Night 02:00: false
Nominal night duration: PT4H
Monday 23:00: true
Tuesday 01:00: true
Tuesday 23:00: false
Opening date for Tuesday 01:00: 2026-10-26
Closing date-time for Monday shift: 2026-10-27T02:00
~~~

Phân tích:

- Hai ca dùng cùng kiểu **DailyWindow**, nhưng **crossesMidnight()** chọn công thức khác nhau.
- Biên mở được tính, biên đóng không được tính.
- **PT4H** là bốn giờ danh nghĩa, được tính sau khi bù một ngày cho khoảng 22:00–02:00.
- **26/10/2026** là thứ Hai, nên ca bắt đầu 22:00 thứ Hai vẫn phục vụ lúc **01:00 thứ Ba**.
- **23:00 thứ Ba** không nằm trong lịch chỉ mở thứ Hai.
- **closingDateTimeFor(2026-10-26)** trả **2026-10-27T02:00**: ngày đóng đã sang ngày kế tiếp. Đây vẫn là **LocalDateTime**, chưa xác định timezone hay Instant.

Đoạn code từ chối hai giờ bằng nhau; để bổ sung **CLOSED** và **ALL_DAY** trong ứng dụng thực, dùng trạng thái nghiệp vụ riêng, không thay đổi ngầm ý nghĩa của cặp giờ.

## 7. Duration giữa hai LocalTime có thể âm

**Duration.between(LocalTime.of(22, 0), LocalTime.of(2, 0))** trả **PT-20H**, vì đối số được xét trong cùng một ngày đồng hồ. Java không tự suy ra là “02:00 của ngày mai”.

~~~java
LocalTime opens = LocalTime.of(22, 0);
LocalTime closes = LocalTime.of(2, 0);

Duration raw = Duration.between(opens, closes);  // PT-20H
Duration nominal = raw.plusDays(1);              // PT4H
~~~

Đây là đoạn trích cần import java.time.* và đặt trong phương thức.

Với khoảng thường **09:00–17:00**, Duration.between trả **PT8H**, không cần cộng ngày. Với **start = end**, Duration bằng **PT0S**, nhưng điều đó **không thể phân biệt** đóng cả ngày và mở 24 giờ; trạng thái riêng là cần thiết.

Độ dài danh nghĩa ở trên hợp lệ với **một khung giờ lặp có thời lượng dưới 24 giờ**. Khi cần mô hình hóa một ca kéo dài 26 giờ, chỉ hai LocalTime không đủ: phải lưu thêm ngày kết thúc hoặc một Duration riêng.

### Giờ trên mặt đồng hồ khác giờ thực trôi qua

Ở vùng có chuyển giờ mùa hè, một ca 22:00–03:00 có thể dài 4, 5 hoặc 6 giờ thực tùy ngày. **Duration** giữa hai **Instant** cụ thể mới thể hiện đúng thời lượng trên timeline.

## 8. Khi nào phải gắn ZoneId và xét DST?

Giờ mở cửa theo đồng hồ thường là quy tắc **tại địa điểm kinh doanh**, nên lưu **ZoneId** IANA, ví dụ **Asia/Ho_Chi_Minh** hoặc **America/New_York**.

**ZoneId** chứa các quy tắc offset theo ngày; **ZoneOffset** chỉ là độ lệch cố định với UTC tại một thời điểm. Không nên lưu duy nhất **-04:00** để biểu thị giờ mở cửa New York quanh năm vì vùng này có DST.

Tại New York vào **08/03/2026**, đồng hồ nhảy từ gần **02:00** sang **03:00**. Xét ca từ 22:00 ngày 07/03 đến 03:00 ngày 08/03:

- Thời lượng danh nghĩa trên đồng hồ: **5 giờ**.
- Thời lượng thực theo UTC: **4 giờ** do giờ từ 02:00 đến trước 03:00 không tồn tại.

Đoạn trích sau đặt trong phương thức và import java.time.*:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime starts = LocalDateTime.of(
        2026, 3, 7, 22, 0).atZone(zone);
ZonedDateTime ends = LocalDateTime.of(
        2026, 3, 8, 3, 0).atZone(zone);
Duration actual = Duration.between(
        starts.toInstant(), ends.toInstant());
// actual = PT4H
~~~

Vào ngày chuyển DST ngược, cùng một giờ như **01:30** có thể xảy ra hai lần với hai offset, tạo ra hai Instant khác nhau. Trong **gap**, một giờ địa phương có thể không tồn tại. **LocalDateTime.atZone(zone)** có quy tắc chọn/điều chỉnh mặc định; ứng dụng tính lương hoặc xác nhận đặt chỗ nên có chính sách rõ ràng thay vì ngầm dựa vào mặc định.

**ZoneRules.getValidOffsets(localDateTime)** cho biết 0, 1 hoặc 2 offset hợp lệ; các trường hợp cần thiết có thể kiểm tra **ZoneRules.getTransition(localDateTime)** và quyết định từ chối giờ, dời giờ hoặc chọn offset sớm/muộn. Sau khi hai mốc được giải quyết thành Instant, dùng Duration.between để đo giờ thực.

Một quy tắc mở cửa **LocalTime 09:00** tại địa điểm sẽ vẫn là 09:00 theo đồng hồ vùng qua thay đổi DST, nhưng Instant tương ứng có thể đổi. Vì thế không dùng một Instant cố định để lưu quy tắc “mở mỗi ngày lúc 09:00”.

## 9. Lịch nhiều khoảng trong một ngày

Lịch cửa hàng có thể như sau:

~~~text
Thứ Hai:
  09:00–12:00
  13:00–17:00
  22:00–02:00 (đóng thứ Ba)
~~~

**09:00–02:00** không thay thế được cả ba khung vì như vậy sẽ cho rằng cửa hàng phục vụ lúc **12:30**, dù đang nghỉ trưa. Nên lưu **danh sách các khung**; với từng khung, kiểm tra giờ và ngày bắt đầu ca. Nếu **ít nhất một khung hợp lệ** và không bị ngoại lệ đóng cửa ghi đè, địa điểm được xem là mở.

Các vấn đề cần có quy tắc bổ sung:

- **Khung chồng nhau:** nếu cùng cửa hàng, có thể cần chuẩn hóa/hợp nhất hoặc báo lỗi; nếu khác quầy, có thể được phép chồng.
- **Ngày bắt đầu ca:** ca tối thứ Hai 22:00–02:00 phải còn có hiệu lực sáng thứ Ba.
- **Ngày nghỉ lễ:** quy định nghỉ theo ngày bắt đầu ca hay thời điểm đang xét; một lệnh đóng từ 00:00 có thể cắt ngang ca tối hôm trước.
- **Ngoại lệ lịch:** lễ Tết, sửa chữa, khai trương, lịch theo mùa nên là các mục có **ngày cụ thể** hoặc phạm vi ngày hiệu lực.
- **Nhiều địa điểm:** mỗi cơ sở phải có ZoneId và lịch của riêng nó.
- **Lịch 24/7:** dùng kiểu **ALL_DAY** hoặc chính sách mở liên tục, không dựa vào cặp 00:00–00:00 khó hiểu.

Khi sắp xếp các ca **thực tế** qua ngày, hãy chuyển từng ca thành cặp **LocalDateTime** hoặc **ZonedDateTime** với ngày cụ thể. Chỉ sắp xếp theo LocalTime sẽ đưa 01:00 trước 22:00 dù nó thuộc **phần sau của cùng ca đêm**.

## 10. Mô hình dữ liệu và API

Một cấu hình minh họa:

~~~json
{
  "zone": "Asia/Ho_Chi_Minh",
  "openingDays": ["MONDAY", "TUESDAY", "FRIDAY"],
  "windows": [
    { "opens": "09:00", "closes": "12:00" },
    { "opens": "13:00", "closes": "17:00" },
    { "opens": "22:00", "closes": "02:00" }
  ],
  "boundaryRule": "start-inclusive-end-exclusive",
  "overnightOwnership": "opening-date",
  "equalTimeRule": "reject; use CLOSED or ALL_DAY"
}
~~~

Đây là **JSON minh họa hợp đồng**, không phải định dạng chuẩn có sẵn của Java.

Nên chuẩn hóa:

1. **opens**, **closes** theo ISO **HH:mm**, hoặc HH:mm:ss nếu cần chính xác đến giây.
2. Các ngày trong tuần biểu thị **ngày bắt đầu ca**, không mặc định là ngày kiểm tra.
3. Trạng thái **CLOSED** và **ALL_DAY** được truyền tường minh.
4. ZoneId IANA của địa điểm được lưu riêng với LocalTime.
5. Quy tắc xử lý nghỉ lễ, DST gap/overlap, hiệu lực lịch được tài liệu hóa.
6. Timestamp ghi nhận check-in/check-out dùng **Instant**; bản ghi lịch lặp dùng LocalTime.

Cột SQL **TIME** thường được ánh xạ tới LocalTime, nhưng nó không chứa ngày, không chứa ZoneId và không biểu diễn việc “giờ đóng ở ngày kế tiếp”. Nếu dùng JDBC/ORM, kiểm tra mapping thực tế và lưu thêm ngày ca/ngày trong tuần cùng các quy tắc nghiệp vụ.

## 11. Kiểm tra input và định dạng

**LocalTime.parse("22:00")** hỗ trợ biểu diễn ISO thông dụng. Nếu nhận giờ bằng văn bản, có thể cấu hình formatter:

~~~java
DateTimeFormatter format =
        DateTimeFormatter.ofPattern("HH:mm");
LocalTime opens = LocalTime.parse("22:00", format);
LocalTime closes = LocalTime.parse("02:00", format);
~~~

Đây là đoạn trích; cần import LocalTime và java.time.format.DateTimeFormatter, đặt trong một phương thức. Nếu đầu vào sai như **25:00** hoặc **12:90**, LocalTime.parse ném **DateTimeParseException**.

Lưu ý **HH** dùng giờ 0–23, **mm** là phút, **MM** là tháng. Không so sánh giờ theo chuỗi thiếu chuẩn như “9:00” và “22:00” bởi thứ tự từ điển không nhất thiết khớp thứ tự đồng hồ.

Nếu giao diện chỉ nhận chính xác đến phút, áp dụng cùng một quy tắc cho mọi khung; khi hệ thống so với timestamp có giây/nano, điều kiện nửa mở vẫn chính xác: **01:59:59.999999999** là trước 02:00; **02:00:00** là đóng.

## 12. Dùng Clock để kiểm tra “đang mở” theo đúng địa điểm

Giờ của máy chủ có thể khác giờ cửa hàng. Vì vậy:

- Lấy **Instant.now(clock)** từ Clock được cấu hình/inject.
- Dùng **instant.atZone(storeZone)** để lấy ngày và giờ địa phương của cơ sở.
- Từ **ZonedDateTime**, lấy **toLocalDateTime()** để xét danh sách khung giờ và ngày bắt đầu ca.
- Sau khi xác định lịch hợp lệ, áp dụng chính sách ngoại lệ/ngày lễ.

Ví dụ đoạn trích sau khi đã có đối tượng DailyWindow, các import cần thiết và một Clock:

~~~java
Instant current = Instant.now(clock);
ZoneId storeZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime storeNow =
        current.atZone(storeZone).toLocalDateTime();
boolean open = window.isOpenOn(storeNow, openingDays);
~~~

Khi kiểm thử, dùng **Clock.fixed(...)** để có kết quả lặp lại được. Nếu kiểm tra tiền lương hoặc thời gian chờ, lấy Instant ở hai mốc cụ thể; nếu chỉ kiểm tra lịch mở theo đồng hồ, LocalDateTime của địa điểm là phù hợp.

## 13. Lỗi thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng AND cho ca 22:00–02:00 | Luôn đóng | Nhánh qua đêm dùng OR |
| Bao gồm cả giờ đóng | Đúng 02:00 vẫn báo mở | Dùng khoảng **[start, end)** |
| Gán 00:00–00:00 là mở 24 giờ mà không có hợp đồng | Hệ thống khác hiểu là đóng cả ngày | Dùng CLOSED/ALL_DAY riêng |
| Dùng trực tiếp Duration.between(22:00, 02:00) để tính 4 giờ | Thực ra ra -20 giờ | Cộng 1 ngày danh nghĩa khi đã biết qua đêm |
| Xét thứ của thời điểm kiểm tra | Thứ Ba 01:00 bị loại khỏi ca thứ Hai | Tìm **ngày bắt đầu ca** |
| Dùng LocalTime.plusHours để lấy giờ đóng ngày mai | Mất thông tin ngày | Dùng LocalDateTime và ngày kết thúc |
| Dùng UTC offset cố định cho lịch lặp New York | Lệch giờ khi DST đổi | Lưu ZoneId |
| Xem Duration danh nghĩa là thời lượng tính công thực | Sai qua DST | Đo Duration giữa Instant |
| Gộp các ca có nghỉ trưa thành một khoảng | Báo mở khi cửa hàng nghỉ | Lưu danh sách khung |
| Bỏ qua ngày lễ hoặc ngày đóng đột xuất | Kết luận “mở” sai | Áp dụng lớp ngoại lệ |
| Cố lưu 24:00 trong LocalTime | Giá trị không hợp lệ | Dùng 00:00 ngày kế tiếp |
| So giờ dưới dạng chuỗi không chuẩn | So sánh sai | Parse thành LocalTime |
| Dùng LocalTime thay timestamp | Không biết ngày/zone | Dùng Instant khi ghi sự kiện |

## 14. Trường hợp kiểm thử khuyến nghị

| Trường hợp | Dữ liệu | Mong đợi theo chính sách bài học |
| --- | --- | --- |
| Trước mở | 09:00–17:00, 08:59 | Đóng |
| Đúng mở | 09:00–17:00, 09:00 | Mở |
| Đúng đóng | 09:00–17:00, 17:00 | Đóng |
| Trước nửa đêm | 22:00–02:00, 23:59 | Mở |
| Sau nửa đêm | 22:00–02:00, 00:01 | Mở |
| Đúng giờ đóng qua đêm | 22:00–02:00, 02:00 | Đóng |
| Đóng lúc nửa đêm | 22:00–00:00, 00:00 | Đóng |
| Ca thứ Hai, thứ Ba 01:00 | 22:00–02:00, MONDAY | Mở |
| Ca thứ Hai, thứ Ba 23:00 | 22:00–02:00, MONDAY | Đóng |
| Hai giờ bằng nhau | 00:00–00:00 | Yêu cầu CLOSED/ALL_DAY |
| Giờ đầu vào sai | 25:00 | Báo lỗi |
| Khoảng nghỉ trưa | 09:00–12:00 và 13:00–17:00, hỏi 12:30 | Đóng |
| Có ngày nghỉ bất thường | Ca hợp lệ theo tuần nhưng ngày nghỉ | Theo chính sách ngoại lệ |
| Bắt đầu DST | Ca qua giờ bị bỏ qua | Kiểm tra quy tắc zone và độ dài thực |
| Kết thúc DST | Ca qua giờ bị lặp | Kiểm tra lựa chọn offset |

Đặc biệt kiểm tra **đúng biên**, **ngày đầu ca**, **nửa đêm**, **lịch nhiều ca** và **DST** nếu địa điểm có áp dụng chuyển giờ.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao kiểm tra giờ mở bằng AND luôn sai với 22:00–02:00?**

Vì không có giờ trong một ngày đồng hồ vừa >= 22:00 vừa < 02:00. Phải chọn **OR** cho trường hợp đi qua nửa đêm.

**2. Ca 22:00–00:00 có bao gồm đúng 00:00 không?**

Không. Theo khoảng **[open, close)**, 00:00 là thời điểm đóng của ngày kế tiếp.

**3. Ca chỉ mở tối thứ Hai 22:00–02:00 có mở lúc 01:00 thứ Ba không?**

Có, vì 01:00 thứ Ba vẫn thuộc ca bắt đầu thứ Hai. Cần tính ngày bắt đầu ca trước khi đối chiếu DayOfWeek.

**4. Khoảng 00:00–00:00 có chắc là mở 24 giờ không?**

Không. Mốc bằng nhau không đủ phân biệt đóng cả ngày và mở cả ngày. Dùng trạng thái riêng.

**5. LocalTime.of(23, 0).plusHours(3) có tự trả ngày hôm sau không?**

Không. Kết quả chỉ là LocalTime **02:00**. Muốn giữ thông tin ngày phải kết hợp LocalDate/LocalDateTime.

**6. Duration.between(22:00, 02:00) trả mấy giờ?**

**-20 giờ**, không tự hiểu qua ngày. Với ca qua đêm có độ dài danh nghĩa dưới 24 giờ, cộng thêm một ngày danh nghĩa để có **4 giờ**.

**7. Một ca 22:00–03:00 tại New York có luôn dài đúng 5 giờ thực không?**

Không. Qua ngày bắt đầu/kết thúc DST, thời lượng thực có thể khác. Cần ngày cụ thể, ZoneId, chính sách giải quyết giờ mơ hồ và hai Instant.

## Tài liệu tham khảo chính thức

- [Java SE 17 — LocalTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html): biểu diễn giờ, phép so sánh và cộng/trừ.
- [Java SE 17 — LocalDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html): ngày và giờ địa phương.
- [Java SE 17 — DayOfWeek](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/DayOfWeek.html): lịch theo thứ trong tuần.
- [Java SE 17 — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html): đo khoảng thời gian.
- [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html): gắn vùng và xác định thời điểm.
- [Java SE 17 — ZoneRules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/zone/ZoneRules.html): valid offsets, gap và overlap.
