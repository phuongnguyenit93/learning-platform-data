# Biểu diễn ngày sinh, giờ mở cửa và lịch làm việc bằng java.time (Java 8+)

## 1. Chọn loại dữ liệu đúng trước khi viết code

Một ứng dụng quản lý khách hàng và cửa hàng có ba khái niệm rất khác nhau:

- Một người sinh ngày **29/02/2000**. Dữ liệu này là một **ngày lịch**, không phải một thời điểm UTC.
- Cửa hàng thường mở lúc **09:00** và đóng lúc **17:00**. Đó là **giờ trên đồng hồ địa phương**, áp dụng lặp lại.
- Cửa hàng làm việc thứ Hai đến thứ Sáu, nhưng thứ Sáu còn có ca **22:00–02:00** và một số ngày nghỉ. Đây là **quy tắc lịch hằng tuần**, không phải một timestamp đơn lẻ.

Bởi vậy không nên dùng một kiểu dữ liệu duy nhất cho mọi trường hợp. API **java.time** ra đời từ Java 8 và vẫn là hệ thống ngày giờ hiện hành để mô hình hóa các ý nghĩa này.

| Loại thông tin | Kiểu nên chọn | Có chứa zone? |
| --- | --- | --- |
| Ngày sinh, ngày lễ, ngày nghỉ cụ thể | **LocalDate** | Không |
| Giờ mở/đóng trong ngày | **LocalTime** | Không |
| Thứ áp dụng lịch tuần | **DayOfWeek** | Không |
| Kỷ niệm theo tháng–ngày | **MonthDay** | Không |
| Ngày và giờ trên đồng hồ, chưa xác định zone | **LocalDateTime** | Không |
| Quy tắc múi giờ của một cơ sở | **ZoneId** | Có quy tắc vùng |
| Ngày/giờ cụ thể đã xác định vùng | **ZonedDateTime** | Có |
| Thời điểm thực tuyệt đối | **Instant** | Không lưu tên vùng |
| Số năm/tháng/ngày theo lịch | **Period** | Không |
| Thời lượng trôi qua theo giây/nano | **Duration** | Không |

Đối với lịch tuần, thường cần kết hợp **DayOfWeek + các khoảng LocalTime + ZoneId + ngoại lệ LocalDate**. Khi muốn trả lời "ngay lúc này cửa hàng có mở không?", phải chuyển **Instant cần kiểm tra** sang giờ địa phương của cơ sở trước.

Bài có ba chương trình chạy được, đều đã kiểm thử: chương trình mô hình lịch đầy đủ trên JDK 17, một ví dụ tương thích Java 8 và một chương trình minh họa ranh giới DST. Các tính năng khai báo record (Java 16+) và collection factory **List.of/Set.of** (Java 9+) được đánh dấu rõ; các kiểu java.time chính đã có từ Java 8.

## 2. Ngày sinh: LocalDate, không phải Instant

**LocalDate** biểu diễn năm–tháng–ngày trong lịch ISO-8601 mà không chứa giờ, offset hay time zone.

~~~java
LocalDate birthDate = LocalDate.of(2000, 2, 29);
LocalDate parsed = LocalDate.parse("2000-02-29");

System.out.println(birthDate);              // 2000-02-29
System.out.println(birthDate.equals(parsed)); // true
~~~

Đây là ví dụ minh họa trong method đã import **java.time.LocalDate**. LocalDate bất biến: bạn có thể truyền nó giữa nhiều thành phần mà không cần sợ code khác sửa ngày trong instance.

**Không dùng Instant cho ngày sinh** nếu nghiệp vụ chỉ biết ngày trên giấy tờ. Ví dụ, gắn "2000-02-29T00:00:00Z" rồi hiển thị tại một vùng có offset âm có thể làm ngày thành 28/02. Điều đó đưa thêm một giả định giờ sinh UTC mà dữ liệu nguồn không hề có.

**Không dùng LocalDateTime chỉ để chứa ngày sinh**: nó thêm các thành phần giờ/phút giả tạo. Cần lưu **DATE** theo contract database/driver khi dữ liệu chỉ có ngày.

### Kiểm tra tính hợp lệ

~~~java
LocalDate.of(2000, 2, 29); // Hợp lệ.

// LocalDate.of(2025, 2, 29); // DateTimeException: ngày sai.
~~~

Các phép **of**, **parse** xác thực lịch. Không chấp nhận chuỗi ngày không xác định thứ tự tháng–ngày như "03/04/2025" từ một API nếu chưa thỏa thuận định dạng.

**Lưu ý lịch sử:** LocalDate dùng ISO proleptic Gregorian. Với dữ liệu lịch dân sự hiện đại đây thường là lựa chọn đúng; các bài toán nghiên cứu lịch cổ phải có quy tắc riêng.

## 3. Tuổi, ngày kỷ niệm và sinh nhật ngày 29/02

Nếu cần số năm tròn theo một ngày tham chiếu:

~~~java
LocalDate birthday = LocalDate.of(2000, 2, 29);
LocalDate today = LocalDate.of(2025, 5, 1);

int age = Period.between(birthday, today).getYears();
// 25
~~~

**Period.between** dùng số năm, tháng và ngày lịch, không đo tuổi bằng tổng giây chia cho 365 ngày. Khi lấy ngày hiện tại thực tế, cần xem ngày hiện tại theo **múi giờ liên quan đến nghiệp vụ**, chẳng hạn vùng của khách hàng/cơ sở.

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate localToday = LocalDate.now(businessZone);
~~~

**Trong test nên dùng Clock.fixed** để không phụ thuộc ngày chạy; ví dụ chính ở phần 9 thể hiện cách này.

Nếu chỉ cần tháng–ngày cho chương trình chúc mừng sinh nhật:

~~~java
MonthDay anniversary = MonthDay.from(birthday);
System.out.println(anniversary); // --02-29
~~~

**MonthDay** không giữ năm sinh. Với người sinh 29/02, năm không nhuận cần **chính sách nghiệp vụ rõ**: chọn 28/02 hoặc 01/03, hoặc một quy tắc khác. Không tự coi behavior của thư viện là quy tắc pháp lý.

~~~java
MonthDay leapDay = MonthDay.of(2, 29);

System.out.println(leapDay.atYear(2025));
// 2025-02-28
~~~

**MonthDay.atYear(2025)** điều chỉnh 29/02 thành 28/02 vì 2025 không nhuận. Nếu sản phẩm chọn 01/03, hãy triển khai trường hợp đặc biệt rõ ràng và kiểm thử. Một phép **LocalDate.plusYears** cũng có quy tắc điều chỉnh ngày không tồn tại trong năm đích; đừng dùng nó một cách vô thức thay cho chính sách sinh nhật.

**Ngày sinh** và **ngày kỷ niệm trong năm** có ý nghĩa khác nhau: một cái luôn chứa năm sinh, cái còn lại có thể cần điều chỉnh theo lịch hiện hành.

## 4. LocalTime để biểu diễn giờ mở cửa lặp lại

**LocalTime** lưu giờ–phút–giây–nano trong ngày, không chứa ngày hay múi giờ.

~~~java
LocalTime opens = LocalTime.of(9, 0);
LocalTime closes = LocalTime.parse("17:00");

System.out.println(opens);  // 09:00
System.out.println(closes); // 17:00
~~~

Quy tắc "mỗi ngày mở 09:00" phải giữ nguyên theo đồng hồ ở nơi cửa hàng hoạt động. Không chuyển nó vĩnh viễn thành "02:00Z" rồi cho rằng luôn đúng ở mọi năm: ZoneId có thể có quy tắc offset thay đổi theo thời gian.

### Giới hạn đầu vào: [start, end)

Đối với khoảng cùng ngày 09:00–17:00, nên mô tả ranh giới tường minh:

- **09:00** được tính là đang mở (bao gồm đầu khoảng).
- **16:59** được tính là đang mở.
- **17:00** không còn được tính là mở (không bao gồm cuối khoảng).
- **08:59** chưa mở.

~~~java
static boolean withinDay(
        LocalTime time, LocalTime start, LocalTime end) {
    return !time.isBefore(start) && time.isBefore(end);
}
~~~

Điều kiện trên chỉ đúng nếu **start < end trong cùng một ngày**. Không dùng trực tiếp cho 22:00–02:00, vì khi qua nửa đêm end nhỏ hơn start theo so sánh LocalTime.

### LocalTime không có giờ 24:00

Giờ hợp lệ là **00–23**. LocalTime.of(24, 0) không hợp lệ. Muốn kết thúc ở nửa đêm thì mô tả bằng **00:00 của ngày sau**. Muốn mở **24/7** hay đóng cả ngày, hãy có trạng thái **ALL_DAY/CLOSED** riêng, không tự suy ra từ start == end.

## 5. Lịch làm việc tuần: DayOfWeek và EnumMap

Cửa hàng có thể có mẫu lịch:

| Ngày | Các khoảng mở cửa |
| --- | --- |
| MONDAY | 09:00–17:00 |
| TUESDAY | 09:00–17:00 |
| WEDNESDAY | 09:00–17:00 |
| THURSDAY | 09:00–17:00 |
| FRIDAY | 09:00–17:00 và 22:00–02:00 |
| SATURDAY | Không có ca riêng |
| SUNDAY | Nghỉ |

**DayOfWeek** là enum được dùng làm khóa, và **LocalDate.getDayOfWeek()** trả thứ tương ứng.

~~~java
DayOfWeek day = LocalDate.of(2025, 4, 28).getDayOfWeek();
System.out.println(day); // MONDAY
~~~

**EnumMap<DayOfWeek, List<Window>>** là một cấu trúc phù hợp: một key là thứ trong tuần, value chứa nhiều cửa sổ giờ.

~~~java
Map<DayOfWeek, List<Window>> weekly =
        new EnumMap<>(DayOfWeek.class);
~~~

Ở đây **Window** là class/record ứng dụng định nghĩa. Một ngày có thể có **hai ca** để loại giờ nghỉ trưa: 09:00–12:00 và 13:00–17:00. Đừng dùng một khoảng 09:00–17:00 rồi cố tự thêm các ngoại lệ nghỉ trưa ở mọi phép đánh giá.

Theo thứ tự ISO, DayOfWeek.MONDAY.getValue() là 1 và SUNDAY là 7. Quy tắc ngày đầu tuần hiển thị cho người dùng có thể khác theo locale, nhưng enum này có nghĩa cố định. Lịch tuần là **mẫu lặp**, không phải một đối tượng LocalDateTime duy nhất.

## 6. Ca qua nửa đêm: cần xét cả ngày hôm trước

Ca **22:00 thứ Sáu đến 02:00 thứ Bảy** là một khoảng có hai phần:

~~~text
Thứ Sáu 22:00 --------- Thứ Bảy 00:00 --------- 02:00
      [phần ngày bắt đầu]      [phần ngày kế tiếp]
                                                  đóng
~~~

Nếu chỉ lấy weekly.get(SATURDAY), ta thấy thứ Bảy không có ca và trả sai tại **01:00 thứ Bảy**, vì ca bắt đầu thứ Sáu vẫn còn hiệu lực.

Với hai LocalTime start và end:

- Nếu **start < end**, toàn bộ khoảng nằm trong ngày bắt đầu và kiểm tra **start <= time < end**.
- Nếu **start > end**, khoảng qua nửa đêm. Ngày bắt đầu mở từ start trở đi; ngày sau mở từ 00:00 đến trước end.
- Nếu **start == end**, không đoán đây là 24 giờ hay khoảng rỗng; cần trạng thái rõ.

Mô hình có thể dùng một record (Java 17+):

~~~java
record Window(LocalTime start, LocalTime end) {
    Window {
        Objects.requireNonNull(start);
        Objects.requireNonNull(end);
        if (start.equals(end)) {
            throw new IllegalArgumentException(
                    "Define closed/all-day hours separately");
        }
    }

    boolean onOpeningDate(LocalTime time) {
        return !time.isBefore(start)
                && (start.isBefore(end) ? time.isBefore(end) : true);
    }

    boolean afterMidnight(LocalTime time) {
        return start.isAfter(end) && time.isBefore(end);
    }
}
~~~

**onOpeningDate** xử lý phần của ca thuộc ngày bắt đầu; **afterMidnight** kiểm tra phần sáng hôm sau của một ca bắt đầu ngày trước. **LocalTime.of(0,0)** là mốc đầu ngày mới, không phải một giờ 24:00 được lưu trong cùng ngày.

**Điểm đóng 02:00 không được tính là mở**, bởi vì afterMidnight dùng **isBefore(end)**. Đó là cách tránh chồng lấn giữa hai ca liên tiếp.

## 7. ZoneId: lịch giờ địa phương cần biết địa điểm

Một quy tắc LocalTime 09:00 chưa cho biết giờ theo múi giờ nào. Nếu người dùng ở nước khác hỏi cửa hàng có đang mở không, không dùng giờ của trình duyệt hay giờ mặc định của server để đánh giá.

~~~java
ZoneId storeZone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant now = Instant.parse("2025-04-28T02:00:00Z");

ZonedDateTime local = now.atZone(storeZone);
System.out.println(local.toLocalDate()); // 2025-04-28
System.out.println(local.toLocalTime()); // 09:00
~~~

**Instant** chỉ một thời điểm thật; **ZoneId** chứa những quy tắc chuyển đổi sang ngày giờ địa phương. Ở một số vùng, offset thay đổi theo mùa hoặc quyết định của quốc gia.

**Không đồng nhất ZoneOffset với ZoneId.** Offset +07:00 chỉ nói chênh lệch so UTC, còn ZoneId "Asia/Ho_Chi_Minh" đại diện vùng với dữ liệu/quy tắc thời gian. Khi xây lịch lặp lâu dài, nên ghi ZoneId của cơ sở thay vì cố định offset hiện tại rồi áp vào mọi năm.

Các bước đánh giá câu hỏi "đang mở không?" nên là:

1. Nhận thời điểm cần xét dưới dạng Instant.
2. Chuyển Instant sang ZonedDateTime theo ZoneId cửa hàng.
3. Lấy LocalDate, LocalTime và DayOfWeek địa phương.
4. Áp dụng quy tắc ngoại lệ ngày cụ thể, các khoảng cùng ngày và ca qua đêm của ngày trước.
5. Trả một boolean hoặc trạng thái giàu thông tin theo contract.

## 8. Ngày nghỉ, ca đặc biệt và thứ tự ưu tiên

Mẫu lịch tuần không giải quyết lễ, bảo trì, sự kiện hay nghỉ đột xuất. Dùng **LocalDate** để chỉ ngày ngoại lệ theo lịch địa phương.

~~~java
Set<LocalDate> closedDates =
        Set.of(LocalDate.of(2025, 4, 30));
~~~

**Set.of** có từ Java 9. Với Java 8, dùng HashSet hoặc cấu trúc khác phù hợp. Đây là ví dụ ngày cửa hàng chủ động nghỉ, không phải tuyên bố về quy tắc ngày lễ cho tất cả địa điểm.

### Chính sách ví dụ

- Nếu **ngày địa phương hiện tại** nằm trong closedDates, cửa hàng đóng cả ngày.
- Nếu không đóng, kiểm tra cửa sổ mở cửa bắt đầu ngày hiện tại.
- Nếu chưa mở, kiểm tra phần của ca qua đêm bắt đầu hôm qua, với điều kiện **hôm qua không bị đóng cả ngày**.
- Nếu cả hai nguồn ca không khớp, trả false.

**Với chính sách này, một ngày nghỉ đóng cả phần ca đêm kéo từ hôm trước**, kể cả hôm trước có lịch làm. Đây là quyết định của demo, không phải quy tắc bắt buộc của mọi cửa hàng. Nếu muốn ca hôm trước vẫn được tiếp tục sang ngày nghỉ, phải điều chỉnh thứ tự ưu tiên.

### Giờ đặc biệt một ngày

Nếu ngày X mở 10:00–14:00 thay vì 09:00–17:00, có thể thêm **Map<LocalDate,List<Window>> specialHours** và một quy tắc override. Tuy nhiên phải xử lý rõ ca đêm từ ngày hôm trước, vì thay lịch ngày X không tự quyết định có hủy phần nối qua nửa đêm không.

**Đặt ownership rõ:** giờ tuần, đóng cả ngày, giờ override, chính sách ca qua nửa đêm và điều kiện khẩn cấp nên có thứ tự xử lý được dokument hóa/test. Tránh hardcode các ngày lễ trong source Java nếu phạm vi cơ sở thay đổi thường xuyên.

## 9. Chương trình Java 17 đầy đủ: sinh nhật, lịch tuần và ca qua đêm

Chương trình dùng múi giờ cửa hàng **Asia/Ho_Chi_Minh**. Tất cả thời điểm thử đều là Instant cố định nên stdout không phụ thuộc ngày chạy.

Tạo tệp **BirthdayOpeningHoursDemo.java**:

~~~java
import java.time.*;
import java.util.*;

public class BirthdayOpeningHoursDemo {
    record Window(LocalTime start, LocalTime end) {
        Window {
            Objects.requireNonNull(start);
            Objects.requireNonNull(end);
            if (start.equals(end)) {
                throw new IllegalArgumentException(
                        "Define closed/all-day hours separately");
            }
        }

        boolean onOpeningDate(LocalTime time) {
            return !time.isBefore(start)
                    && (start.isBefore(end) ? time.isBefore(end) : true);
        }

        boolean afterMidnight(LocalTime time) {
            return start.isAfter(end) && time.isBefore(end);
        }
    }

    static boolean isOpen(Instant instant, ZoneId storeZone,
            Map<DayOfWeek, List<Window>> weekly,
            Set<LocalDate> closedDates) {
        ZonedDateTime local = instant.atZone(storeZone);
        LocalDate date = local.toLocalDate();
        if (closedDates.contains(date)) {
            return false;
        }
        LocalTime time = local.toLocalTime();
        for (Window w : weekly.getOrDefault(
                date.getDayOfWeek(), List.of())) {
            if (w.onOpeningDate(time)) {
                return true;
            }
        }
        LocalDate yesterday = date.minusDays(1);
        if (!closedDates.contains(yesterday)) {
            for (Window w : weekly.getOrDefault(
                    yesterday.getDayOfWeek(), List.of())) {
                if (w.afterMidnight(time)) {
                    return true;
                }
            }
        }
        return false;
    }

    static void show(String label, String timestamp, ZoneId zone,
            Map<DayOfWeek, List<Window>> weekly,
            Set<LocalDate> closedDates) {
        Instant instant = Instant.parse(timestamp);
        ZonedDateTime local = instant.atZone(zone);
        System.out.println(label + ": " + local.toLocalDate() + " "
                + local.toLocalTime() + " -> "
                + isOpen(instant, zone, weekly, closedDates));
    }

    public static void main(String[] args) {
        ZoneId storeZone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate birthDate = LocalDate.of(2000, 2, 29);
        Clock testClock = Clock.fixed(
                Instant.parse("2025-05-01T00:00:00Z"), storeZone);
        LocalDate today = LocalDate.now(testClock);

        System.out.println("birth date: " + birthDate);
        System.out.println("today: " + today);
        System.out.println("age: "
                + Period.between(birthDate, today).getYears());
        System.out.println("birthday month-day: "
                + MonthDay.from(birthDate));

        Map<DayOfWeek, List<Window>> weekly =
                new EnumMap<>(DayOfWeek.class);
        Window daytime = new Window(
                LocalTime.of(9, 0), LocalTime.of(17, 0));
        for (DayOfWeek day : List.of(DayOfWeek.MONDAY,
                DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY,
                DayOfWeek.THURSDAY, DayOfWeek.FRIDAY)) {
            weekly.put(day, List.of(daytime));
        }
        weekly.put(DayOfWeek.FRIDAY, List.of(
                daytime, new Window(
                        LocalTime.of(22, 0), LocalTime.of(2, 0))));
        Set<LocalDate> closedDates =
                Set.of(LocalDate.of(2025, 4, 30));

        show("monday opens", "2025-04-28T02:00:00Z",
                storeZone, weekly, closedDates);
        show("monday closes", "2025-04-28T10:00:00Z",
                storeZone, weekly, closedDates);
        show("holiday", "2025-04-30T03:00:00Z",
                storeZone, weekly, closedDates);
        show("friday late", "2025-05-02T15:00:00Z",
                storeZone, weekly, closedDates);
        show("saturday spill", "2025-05-02T18:00:00Z",
                storeZone, weekly, closedDates);
        show("saturday closes", "2025-05-02T19:00:00Z",
                storeZone, weekly, closedDates);
        show("saturday daytime", "2025-05-03T03:00:00Z",
                storeZone, weekly, closedDates);
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac BirthdayOpeningHoursDemo.java
java BirthdayOpeningHoursDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
birth date: 2000-02-29
today: 2025-05-01
age: 25
birthday month-day: --02-29
monday opens: 2025-04-28 09:00 -> true
monday closes: 2025-04-28 17:00 -> false
holiday: 2025-04-30 10:00 -> false
friday late: 2025-05-02 22:00 -> true
saturday spill: 2025-05-03 01:00 -> true
saturday closes: 2025-05-03 02:00 -> false
saturday daytime: 2025-05-03 10:00 -> false
~~~

### Ý nghĩa các kết quả

- **birth date** là LocalDate, không có giờ/offset; **Period.between** cho 25 năm tròn tại ngày test.
- **monday opens**: 02:00 UTC tương ứng 09:00 địa phương, đúng đầu khoảng nên mở.
- **monday closes**: 10:00 UTC tương ứng 17:00 địa phương, đúng cuối khoảng nên đóng.
- **holiday**: dù thứ Tư thường mở 09:00–17:00, ngày 30/04 trong closedDates khiến kết quả đóng.
- **friday late**: 22:00 thứ Sáu là đầu ca đêm nên mở.
- **saturday spill**: 01:00 thứ Bảy khớp phần kết thúc của ca thứ Sáu nên mở.
- **saturday closes**: 02:00 không còn trong khoảng, kết quả false.
- **saturday daytime**: không có ca ngày thứ Bảy và không còn phần ca đêm, nên đóng.

Chương trình không tạo một "Instant của ngày sinh". Nó cũng không lấy múi giờ hệ thống, không so chuỗi đồng hồ như các timestamp UTC và không cố biến mọi ca thành các mốc giờ cố định của tất cả các tuần.

## 10. Ví dụ độc lập chỉ dùng API Java 8

Với một cửa hàng chỉ mở trong cùng ngày, cách kiểm tra đơn giản hơn và có thể biên dịch trên Java 8 nguyên bản. Ví dụ này không có record hay các factory collection mới.

Tạo **BasicLocalHoursJava8.java**:

~~~java
import java.time.*;

public class BasicLocalHoursJava8 {
    public static void main(String[] args) {
        LocalDate birthDate = LocalDate.parse("2000-02-29");
        LocalTime opens = LocalTime.parse("09:00");
        LocalTime closes = LocalTime.parse("17:00");
        LocalTime visitor = LocalTime.parse("16:59");

        boolean inside =
                !visitor.isBefore(opens) && visitor.isBefore(closes);
        boolean atClosing =
                !closes.isBefore(opens) && closes.isBefore(closes);

        System.out.println("birth date: " + birthDate);
        System.out.println("open at 16:59: " + inside);
        System.out.println("open at 17:00: " + atClosing);
    }
}
~~~

Biên dịch bằng JDK 8 hoặc bản JDK hỗ trợ đích Java 8:

~~~bash
javac BasicLocalHoursJava8.java
java BasicLocalHoursJava8
~~~

Stdout:

~~~text
birth date: 2000-02-29
open at 16:59: true
open at 17:00: false
~~~

Đây là **mô hình cùng ngày start < end**. Không dùng nguyên điều kiện này cho lịch qua nửa đêm hoặc lịch cần ngoại lệ, DayOfWeek và ZoneId. Ví dụ đầy đủ phần 9 giải quyết những yêu cầu ấy.

## 11. Quy tắc lặp theo tuần khác sự kiện đã xác định ngày

**Quy tắc lặp**: "mỗi thứ Hai 09:00" dùng **DayOfWeek + LocalTime + ZoneId**. Nó có thể áp dụng trong nhiều tuần và năm.

**Sự kiện cụ thể**: "hẹn 09:00 ngày 05/05/2025 ở Paris" cần một **LocalDateTime** cộng **ZoneId** để xác định ngày giờ có vùng, rồi có thể chuyển sang Instant.

~~~java
LocalDate day = LocalDate.of(2025, 5, 5);
LocalTime time = LocalTime.of(9, 0);
ZoneId zone = ZoneId.of("Europe/Paris");

LocalDateTime wallTime = day.atTime(time);
ZonedDateTime appointment = wallTime.atZone(zone);
Instant instant = appointment.toInstant();
~~~

Đoạn minh họa này cần import java.time. Sau khi đã chọn ZoneId và xử lý các quy tắc chuyển đổi, Instant biểu diễn mốc tuyệt đối của sự kiện.

**Không dùng một Instant của thứ Hai rồi cộng 7 * 24 giờ cho mọi tuần trong một vùng có DST.** Một lịch mở cửa 09:00 theo đồng hồ địa phương có thể thay đổi offset UTC giữa mùa đông và mùa hè.

Nếu một lịch trong database biểu diễn **một ca đã được phân công cụ thể**, có thể lưu ngày bắt đầu LocalDate và local window, cùng ZoneId/chính sách DST, sau đó xác định Instant của từng ranh giới ca khi cần chấm công hoặc tạo cuộc hẹn.

## 12. DST: giờ local có thể không tồn tại hoặc xuất hiện hai lần

Một số ZoneId có **daylight saving time (DST)**. Khi đổi giờ, có thể có:

- **Gap**: một LocalDateTime trong vùng bị bỏ qua; ví dụ 02:30 không tồn tại trong đêm chuyển giờ mùa xuân.
- **Overlap**: một LocalDateTime xuất hiện hai lần, mỗi lần mang offset khác nhau; hai lần 02:30 không cùng một Instant.

Do đó **LocalDateTime không tự xác định một Instant duy nhất** ở các trường hợp này. Khi chuyển nó sang ZonedDateTime, thư viện có quy tắc mặc định; nghiệp vụ đặt lịch có thể cần chính sách khác.

Tạo tệp **LocalScheduleDstDemo.java** (Java 17+):

~~~java
import java.time.*;
import java.time.zone.*;

public class LocalScheduleDstDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        LocalDateTime spring =
                LocalDateTime.of(2025, 3, 30, 2, 30);
        System.out.println("gap offsets: "
                + paris.getRules().getValidOffsets(spring).size());
        System.out.println("gap resolved: " + spring.atZone(paris));

        LocalDateTime autumn =
                LocalDateTime.of(2025, 10, 26, 2, 30);
        System.out.println("overlap offsets: "
                + paris.getRules().getValidOffsets(autumn).size());

        ZonedDateTime earlier = autumn.atZone(paris);
        ZonedDateTime later =
                earlier.withLaterOffsetAtOverlap();

        System.out.println("earlier: " + earlier);
        System.out.println("later: " + later);
        System.out.println("same local fields: "
                + earlier.toLocalDateTime().equals(
                        later.toLocalDateTime()));
        System.out.println("same instant: "
                + earlier.toInstant().equals(later.toInstant()));

        MonthDay leapBirthday = MonthDay.of(2, 29);
        System.out.println("feb29 at non-leap year: "
                + leapBirthday.atYear(2025));
    }
}
~~~

Chạy:

~~~bash
javac LocalScheduleDstDemo.java
java LocalScheduleDstDemo
~~~

**Stdout đã xác minh với quy tắc múi giờ 2025:**

~~~text
gap offsets: 0
gap resolved: 2025-03-30T03:30+02:00[Europe/Paris]
overlap offsets: 2
earlier: 2025-10-26T02:30+02:00[Europe/Paris]
later: 2025-10-26T02:30+01:00[Europe/Paris]
same local fields: true
same instant: false
feb29 at non-leap year: 2025-02-28
~~~

**ZoneRules.getValidOffsets(LocalDateTime)** trả zero offset khi local time rơi vào gap, hai offset khi ở overlap và một offset trong trường hợp thông thường. **atZone** có cách tự điều chỉnh gap và chọn offset trong overlap; **withLaterOffsetAtOverlap** chọn offset muộn hơn.

**Hệ quả với giờ mở cửa**: quy tắc địa phương 02:00–03:00 có thể cắt qua một khoảng không tồn tại hoặc trùng giờ. Một thuật toán đánh giá ở mỗi **Instant** có thể đi qua cả hai lần xuất hiện của đồng hồ lặp. Hãy xác định cửa hàng có mở trong cả hai lần, một lần, hay dùng quy tắc chuyển ca riêng. Với chấm công, ghi **Instant** hoặc offset thực của từng lần vào/ra.

**Lưu ý tzdb:** dữ liệu múi giờ có thể thay đổi theo quyết định pháp lý tại từng nước. Ví dụ dùng ngày đã qua để minh họa; lịch tương lai cần kiểm thử với quy tắc múi giờ được triển khai thực tế.

## 13. Period và Duration: "một ngày" có thể khác 24 giờ

**Period** mô tả năm/tháng/ngày trên lịch. **Duration** mô tả thời gian elapsed theo giây/nano.

~~~java
ZonedDateTime start = ZonedDateTime.of(
        2025, 3, 29, 12, 0, 0, 0,
        ZoneId.of("Europe/Paris"));

ZonedDateTime calendarDay =
        start.plus(Period.ofDays(1));
ZonedDateTime after24Hours =
        start.plus(Duration.ofDays(1));
~~~

Khi Paris chuyển sang giờ mùa hè vào 30/03/2025, **calendarDay** có giờ địa phương **12:00** ngày hôm sau, còn **after24Hours** là **13:00** ngày hôm sau. Hai giá trị không cùng Instant.

Do đó:

- "Ngày mai vẫn mở lúc 09:00" là quy tắc lịch theo **LocalDate + LocalTime + ZoneId**.
- "Sau đúng 24 giờ" là yêu cầu elapsed time, nên dùng **Duration/Instant**.
- "Mỗi thứ Hai lúc 09:00" là quy tắc tuần, không phải phép cộng một số giây cố định.

Một ca làm việc thực tế qua DST phải làm rõ trả công theo **giờ elapsed**, **giờ trên lịch công bố**, hay một quy tắc lao động riêng. Không tự suy số giờ làm từ phép trừ hai LocalTime không có ngày.

## 14. Clock: test thời gian mà không phụ thuộc ngày thật

Các lời gọi **LocalDate.now()** hoặc **LocalTime.now()** không truyền tham số phụ thuộc hệ thống và có thể dùng default zone. Điều này khiến test khó lặp lại gần nửa đêm hoặc khi CI chạy ở một quốc gia khác.

**Clock** của java.time cho phép truyền nguồn thời gian vào service:

~~~java
ZoneId storeZone = ZoneId.of("Asia/Ho_Chi_Minh");

Clock clock = Clock.fixed(
        Instant.parse("2025-05-01T00:00:00Z"),
        storeZone);

LocalDate today = LocalDate.now(clock);
// 2025-05-01
~~~

Với production có thể dùng một Clock hệ thống thích hợp do ứng dụng khởi tạo; với test thì dùng fixed clock. Tại ranh giới xử lý, truyền **Instant at** vào một method isOpen rõ ràng còn khiến việc test các mốc 09:00/17:00/02:00 dễ hơn.

### Một sai lầm thường gặp

Hàm kiểm tra lịch gọi LocalDate.now() để lấy thứ, đồng thời gọi Instant.now() một lần khác để lấy giờ. Nếu chạy đúng lúc chuyển ngày, hai lần gọi có thể rơi vào hai thời điểm khác nhau. **Lấy một Instant duy nhất** rồi chuyển thành ZonedDateTime ở business zone trước khi lấy cả ngày, giờ và DayOfWeek.

## 15. Biểu diễn ca làm của nhân viên

Lịch tuần cho biết ca dự kiến; để tính giờ làm thực tế còn cần các dữ liệu khác:

| Nghiệp vụ | Cần biểu diễn thêm |
| --- | --- |
| Một ca cụ thể thứ Sáu này | LocalDate bắt đầu + Window/ZoneId |
| Giờ vào/ra thực tế | Instant của mỗi sự kiện, có thể lưu thêm zone/offset để audit |
| Ca 22:00–02:00 | Ngày bắt đầu và phần kết thúc ở ngày sau |
| Nghỉ giữa ca | Hai hay nhiều Window hoặc bản ghi nghỉ riêng |
| Ca xoay vòng 2 tuần | Ngày neo của chu kỳ, không chỉ DayOfWeek |
| Ngày nghỉ đặc biệt | LocalDate + policy override |
| Mở cả ngày / đóng cả ngày | Trạng thái riêng thay vì start==end |
| Đổi ca sau khi đã phân công | Version, lịch sử thay đổi và chính sách thông báo |
| Tính tổng giờ qua DST | Instant/Duration cùng quy tắc chấm công |

**Đối với giờ mở cửa**, một số Window chồng lấn vẫn có thể được kiểm tra bằng logic "khớp ít nhất một khoảng" để ra boolean. **Đối với số giờ làm**, chồng lấn có thể khiến tổng giờ bị đếm hai lần; cần validate hoặc hợp nhất các khoảng theo quy tắc nghiệp vụ.

Nếu cần ca dài hơn 24 giờ, một Window chỉ có hai LocalTime là không đủ thông tin: nên biểu diễn bằng các mốc có ngày hoặc mô hình ca nhiều ngày.

## 16. Lưu trong database và trao đổi qua API

Dữ liệu cần giữ đúng ý nghĩa:

- **Birth date:** LocalDate ↔ kiểu DATE thích hợp.
- **Opening time:** LocalTime ↔ kiểu TIME không có timezone, khi driver/DB hỗ trợ đúng.
- **Weekly schedule:** DayOfWeek + một danh sách Window.
- **Business zone:** ZoneId dưới dạng tên vùng chuẩn, như "Asia/Ho_Chi_Minh".
- **Closures and exceptions:** LocalDate, cùng mức ưu tiên và nguồn dữ liệu.
- **Check-in/out:** Instant hoặc một timestamp có ngữ nghĩa thời điểm rõ.

**Không khẳng định mọi loại SQL TIMESTAMP có cùng ngữ nghĩa trên mọi DB.** JDBC driver, TIMESTAMP WITH TIME ZONE và session timezone có thể khác giữa các nhà cung cấp. Kiểm thử mapping thực tế, không tự suy theo tên cột.

Ví dụ JSON có ý nghĩa rõ:

~~~json
{
  "birthDate": "2000-02-29",
  "businessZone": "Asia/Ho_Chi_Minh",
  "weeklyHours": {
    "MONDAY": [{"start": "09:00", "end": "17:00"}],
    "FRIDAY": [
      {"start": "09:00", "end": "17:00"},
      {"start": "22:00", "end": "02:00"}
    ]
  },
  "closedDates": ["2025-04-30"]
}
~~~

**Trong contract này**, start sau end biểu diễn ca qua nửa đêm. 22:00–02:00 không phải một khoảng vô nghĩa; ngữ nghĩa qua ngày được ứng dụng định nghĩa. Nếu API dùng start==end, phải quy định đó là lỗi, CLOSED hay ALL_DAY; đừng để hai hệ thống hiểu khác nhau.

Định dạng trao đổi như **yyyy-MM-dd** và **HH:mm** rõ nghĩa hơn những chuỗi ngôn ngữ phụ thuộc locale. Khi hiển thị cho người dùng, dùng **DateTimeFormatter** với locale/format phù hợp; không dùng chuỗi hiển thị như định dạng lưu trữ dữ liệu duy nhất.

## 17. Những lỗi phổ biến cần tránh

1. **Ngày sinh thành UTC midnight:** làm ngày hiển thị có thể thay đổi theo zone. Chỉ biết ngày thì dùng LocalDate.
2. **Giờ mở tuần thành Instant:** một Instant không mô tả được quy tắc lặp lại; dùng LocalTime/DayOfWeek/ZoneId.
3. **Dựa vào timezone mặc định của server:** đánh giá lịch theo businessZone rõ ràng.
4. **Chỉ xem DayOfWeek hôm nay:** bỏ sót phần ca đêm bắt đầu hôm qua.
5. **Không định nghĩa start==end:** dẫn tới người hiểu mở 24 giờ, người hiểu đóng.
6. **Dùng cận đóng cho giờ kết thúc:** có thể gây hai ca cùng tính thời điểm ranh giới.
7. **So LocalTime qua nửa đêm như cùng ngày:** 22:00 > 02:00 theo giá trị LocalTime; cần thông tin ngày.
8. **Cộng 7*24 giờ vào Instant cho lịch hằng tuần tại vùng DST:** có thể lệch giờ địa phương.
9. **Coi 29/02 xảy ra mọi năm:** phải có chính sách kỷ niệm ngày sinh của năm không nhuận.
10. **Không xét gap/overlap:** LocalDateTime có thể không tồn tại hoặc tương ứng hai Instant.
11. **Dùng ZoneOffset hiện tại thay ZoneId lâu dài:** offset không mang quy tắc vùng trong toàn năm.
12. **Dùng sleep hoặc đồng hồ thật trong unit test lịch:** thay bằng Clock.fixed hoặc Instant cố định.
13. **Đếm trùng các Window chồng lấn:** boolean "có mở không" khác tổng thời lượng.
14. **Coi mọi ngày lịch bằng 24 giờ thực:** Period và Duration khác nhau qua DST.

## 18. Checklist trước khi triển khai production

**Mô hình:** có ba dữ liệu riêng ngày sinh, giờ mở địa phương và lịch tuần? Có lưu ZoneId? Có phân biệt quy tắc tuần với ca cụ thể? Có thông tin ngày nghỉ và giờ mở đặc biệt?

**Ranh giới:** mở đầu inclusive và cuối exclusive? Có quy tắc 24h/closed? Nhiều khoảng trong cùng ngày được kiểm tra ra sao? Ca qua nửa đêm lấy lịch ngày trước như thế nào?

**Độ đúng:** ngày 29/02, ngày nhuận, ngày nghỉ, ngày đổi DST, ca gần 00:00, thời điểm 09:00, 16:59, 17:00, 02:00 có test? Có test các Instant từ nhiều múi giờ người dùng để xác minh cùng một trạng thái tại cửa hàng?

**Dữ liệu:** có validate input, xử lý null, format ngày/tháng, timestamp DB và timezone của session? Có cập nhật tzdb cho lịch tương lai? Có phân biệt ngày đóng hoàn toàn với khoảng giờ đặc biệt?

**Kiểm thử:** sử dụng Clock.fixed, Instant.parse có Z và ZoneId rõ ràng; tránh phụ thuộc giờ hiện tại và locale mặc định.

## 19. Bài tập và đáp án

### Bài 1 — Chọn đúng kiểu

**Đề:** ngày sinh 15/08/1990, giờ mở 08:30 từ thứ Hai đến thứ Sáu, mốc giao dịch 2025-05-01T03:00:00Z.

**Giải:** LocalDate cho ngày sinh, LocalTime cho giờ mở, DayOfWeek cho mẫu tuần, ZoneId cho địa điểm, Instant cho mốc giao dịch.

### Bài 2 — Giờ kết thúc có được tính là mở?

~~~java
LocalTime start = LocalTime.of(9, 0);
LocalTime end = LocalTime.of(17, 0);
LocalTime atStart = start;
LocalTime atEnd = end;
boolean first = !atStart.isBefore(start) && atStart.isBefore(end);
boolean last = !atEnd.isBefore(start) && atEnd.isBefore(end);
~~~

**Đáp án:** first = true; last = false. Đó là hợp đồng khoảng **[start,end)**.

### Bài 3 — Thứ Bảy 01:00 nhưng cửa chỉ có ca tối thứ Sáu?

**Đáp án:** vẫn mở nếu lịch thứ Sáu có ca 22:00–02:00, và không có policy ngoại lệ đóng cả ngày thứ Bảy. Phải kiểm tra ca của **ngày trước**.

### Bài 4 — Start bằng end là 24 giờ?

**Đáp án:** không có nghĩa mặc định. Ví dụ mẫu ném IllegalArgumentException; sản phẩm cần trạng thái CLOSED/ALL_DAY riêng.

### Bài 5 — Người sinh 29/02 có sinh nhật 29/02/2025 không?

**Đáp án:** không có ngày đó. MonthDay.of(2,29).atYear(2025) trả 28/02 theo hợp đồng API; sản phẩm có thể chọn 01/03 theo chính sách riêng.

### Bài 6 — Muốn kiểm tra một cửa hàng ở Paris tại một Instant từ khách hàng ở Tokyo?

**Đáp án:** chuyển Instant thành ZonedDateTime theo **Europe/Paris**, không lấy ngày/giờ tại Tokyo. Kiểm tra lịch LocalDate/LocalTime/DayOfWeek của Paris tại Instant đó.

### Bài 7 — Đếm số giờ một nhân viên đã làm trong ca qua DST?

**Đáp án:** nếu cần **thời lượng thực**, dùng Instant vào/ra và Duration.between. Nếu cần giờ công theo hợp đồng, phải có quy tắc nghiệp vụ riêng khi DST tạo giờ thiếu hoặc lặp.

### Bài 8 — Tại sao không dùng LocalDate.now() trực tiếp trong mọi test?

**Đáp án:** kết quả phụ thuộc ngày và múi giờ máy chạy. Dùng Clock.fixed hoặc truyền LocalDate/Instant tham chiếu để test lặp lại được.

## 20. Tóm tắt và tài liệu hiện hành

1. **LocalDate** cho ngày sinh/ngày nghỉ, không gắn thêm một mốc UTC giả.
2. **LocalTime** cho giờ mở/đóng, không mang ngày hoặc time zone.
3. **DayOfWeek + List<Window> + ZoneId** cho lịch làm việc lặp hằng tuần.
4. **Ngày nghỉ LocalDate** và **special hours** phải có thứ tự ưu tiên rõ với lịch tuần.
5. **Ca qua nửa đêm** cần kiểm tra phần ca của ngày hôm trước; 02:00 là cuối exclusive nếu khoảng tới 02:00.
6. **Instant** diễn tả một thời điểm thật; đánh giá lịch bằng cách chuyển nó sang ZonedDateTime của cửa hàng.
7. **ZoneId khác ZoneOffset**: tên vùng chứa quy tắc, offset cố định không đủ cho lịch xuyên mùa.
8. **DST** tạo gap và overlap, nên đôi khi LocalDateTime không quy về một Instant duy nhất.
9. **Period** là ngày lịch, **Duration** là số giây trôi qua; chúng khác nhau qua DST.
10. **MonthDay** phục vụ kỷ niệm hằng năm, ngày 29/02 cần policy ở năm không nhuận.
11. **Clock.fixed** cho test xác định. Các API java.time chính của bài có từ Java 8 và vẫn còn được sử dụng trong JDK hiện hành.

### Tài liệu Java SE 25 chính thức

- Package java.time, hướng dẫn chọn kiểu cho ngày sinh và giờ mở cửa: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/package-summary.html
- LocalDate: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html
- LocalTime: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalTime.html
- DayOfWeek: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/DayOfWeek.html
- MonthDay và ngày 29/02: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/MonthDay.html
- ZoneId và ZoneRules: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneId.html và https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRules.html
- ZonedDateTime với DST: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html
- Instant: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html
- Clock: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html
- Period và Duration: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Period.html và https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Duration.html
