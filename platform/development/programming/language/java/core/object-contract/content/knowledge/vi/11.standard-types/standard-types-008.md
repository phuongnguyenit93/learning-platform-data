# Đối tượng giá trị của java.time và yêu cầu đọc đúng hợp đồng từng kiểu

## 1. Vì sao không thể đánh đồng mọi phép “bằng nhau” trong java.time?

Các kiểu quen thuộc trong **java.time** như **LocalDate**, **LocalTime**, **LocalDateTime**, **Instant**, **OffsetDateTime**, **ZonedDateTime**, **Duration**, **Period**, **YearMonth** được thiết kế để mô tả **giá trị thời gian**. Nhiều kiểu trong số này là **value-based classes**: hai instance bằng nhau theo hợp đồng của kiểu có thể được sử dụng thay thế nhau. Không dựa vào danh tính object bằng toán tử **==**, **System.identityHashCode** hay dùng một instance làm khóa đồng bộ **synchronized**. Hãy dùng **equals** và **hashCode** theo đúng tài liệu của kiểu.

Điều khó nhất không nằm ở việc gọi equals, mà là xác định **“cùng giá trị” nghĩa là gì**:

- **Cùng ngày lịch**: 2026-10-23 có bằng 2026-10-23 không? **LocalDate.equals** giải quyết.
- **Cùng thời điểm tuyệt đối**: 09:00 tại UTC+07 có phải 02:00 UTC không? **Instant.equals** hoặc phép so dòng thời gian **isEqual** trên kiểu có offset/zone giải quyết.
- **Cùng biểu diễn ngày giờ và offset**: 09:00+07 có bằng 02:00Z không? **OffsetDateTime.equals** trả false, dù hai giá trị chỉ cùng một thời điểm.
- **Cùng vùng múi giờ có tên**: **Europe/Paris** và **UTC** không phải cùng **ZoneId**, kể cả khi một mốc thời gian cụ thể có thể có cùng offset.
- **Cùng khoảng thời lượng** hay **cùng số lượng đơn vị lịch**: **Duration** tính trên giây/nanogiây, **Period** tính trên năm/tháng/ngày; chúng là hai mô hình khác nhau.

**Quy tắc chung từ Object** vẫn áp dụng:

1. **Phản xạ:** a.equals(a) là true.
2. **Đối xứng:** a.equals(b) có kết quả như b.equals(a).
3. **Bắc cầu:** a bằng b và b bằng c thì a bằng c.
4. **Nhất quán:** cùng trạng thái giá trị thì kết quả không thay đổi.
5. **Khác null:** a.equals(null) là false.
6. **Liên hệ hash:** nếu a.equals(b) true thì a.hashCode() phải bằng b.hashCode(); hash bằng nhau chưa đủ để kết luận equals.

Một so sánh như **isEqual**, **isBefore** hoặc **isAfter** có thể trả về kết quả khác **equals** mà hoàn toàn không vi phạm hợp đồng. Chúng trả lời **câu hỏi khác**.

## 2. Bảng đọc hợp đồng theo từng loại giá trị

| Kiểu java.time | Giá trị mà equals xem xét | Điều không nên suy diễn |
| --- | --- | --- |
| **LocalDate** | Ngày ISO: năm, tháng, ngày | Không gắn múi giờ và không xác định riêng một Instant |
| **LocalTime** | Giờ, phút, giây, nano trong ngày | Không phải thời điểm toàn cầu |
| **LocalDateTime** | Ngày và giờ địa phương, đến nano | Không có offset/zone, nên không đủ để nhận diện một thời điểm |
| **Instant** | Vị trí trên dòng thời gian UTC (giây epoch và nano) | Không lưu múi giờ địa phương hay định dạng người dùng |
| **OffsetDateTime** | Ngày-giờ địa phương **và UTC offset** | Cùng Instant chưa chắc equals |
| **OffsetTime** | Giờ địa phương **và UTC offset** | Không mang ngày; **isEqual** dựa trên giờ tính tương ứng theo UTC trong ngày chuẩn |
| **ZonedDateTime** | Ngày-giờ địa phương, offset và **ZoneId** | Cùng Instant chưa chắc equals; cùng offset chưa chắc cùng zone |
| **ZoneId** | ID múi giờ (ví dụ Europe/Paris) | Hai ID có quy tắc/offset hiện tại giống nhau vẫn có thể khác giá trị |
| **ZoneOffset** | Độ lệch cố định so với UTC, tính bằng giây | Không mô tả toàn bộ quy tắc chuyển giờ mùa hè của region |
| **Duration** | Độ dài theo giây và nanogiây | Không phải số ngày lịch/tháng lịch |
| **Period** | Số năm, tháng và ngày theo hệ ISO | Không đại diện cho một số giây cố định |
| **Year**, **YearMonth**, **MonthDay** | Các thành phần lịch đúng như tên gọi | Không tự đại diện cho ngày-giờ đầy đủ |

**Đọc đúng từng kiểu trước khi chọn làm khóa.** Với **LocalDateTime**, một lần tăng đồng hồ địa phương lúc đổi giờ có thể tạo các biểu diễn giống nhau tại hai Instant khác nhau. Với **OffsetDateTime**, offset là một phần của equals. Với **ZonedDateTime**, ZoneId cũng là một phần của equals. Với **Instant**, biểu diễn theo múi giờ đã bị loại bỏ, chỉ còn mốc tuyệt đối.

Phép so sánh **equals** của các kiểu này không tự động chuyển đổi một kiểu thành kiểu khác: **Instant** và **OffsetDateTime** có thể nói về cùng thời điểm nhưng không phải hai giá trị cùng kiểu theo Object.equals. Muốn so cùng thời điểm, chuyển thành **Instant** trước khi so.

## 3. Value-based: dùng giá trị, không phụ thuộc danh tính

Java có thể tạo ra nhiều instance mang cùng giá trị. Với các lớp value-based, **không có bảo đảm về danh tính object** mà chương trình nên dựa vào. Vì vậy:

~~~java
LocalDate a = LocalDate.of(2026, 10, 23);
LocalDate b = LocalDate.parse("2026-10-23");

// Đúng: so giá trị ngày.
boolean sameDate = a.equals(b);

// Sai về mặt ý nghĩa: == hỏi danh tính tham chiếu;
// không phải tiêu chí so giá trị java.time.
// boolean sameDate = (a == b);
~~~

Đây chỉ là **đoạn mã minh họa** đặt trong phương thức có import **java.time.LocalDate**, không phải file độc lập. Dù **==** tình cờ true trong một trường hợp nào đó, chương trình vẫn không được dựa vào điều này.

### Ví dụ đầy đủ: các đối tượng cùng giá trị trong tập hợp hash

Tạo file **BasicTimeValueDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.HashSet;
import java.util.Set;

public class BasicTimeValueDemo {
    public static void main(String[] args) {
        LocalDate first = LocalDate.of(2026, 10, 23);
        LocalDate second = LocalDate.parse("2026-10-23");

        System.out.println("date equals: " + first.equals(second));
        System.out.println("date hash equals: " +
            (first.hashCode() == second.hashCode()));

        Set<LocalDate> dates = new HashSet<>();
        dates.add(first);
        dates.add(second);
        System.out.println("unique dates: " + dates.size());

        LocalDateTime midnight =
            LocalDateTime.of(2026, 10, 23, 0, 0);
        System.out.println("date equals date-time: " +
            first.equals(midnight));

        Instant absolute = Instant.parse("2026-10-23T02:30:00Z");
        OffsetDateTime fromOffset =
            OffsetDateTime.parse("2026-10-23T09:30:00+07:00");
        System.out.println("same instant: " +
            absolute.equals(fromOffset.toInstant()));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac BasicTimeValueDemo.java
java BasicTimeValueDemo
~~~

Kết quả chính xác:

~~~text
date equals: true
date hash equals: true
unique dates: 1
date equals date-time: false
same instant: true
~~~

**Giải thích:** LocalDate.of và LocalDate.parse tạo cùng ngày ISO; equals true, hashCode bằng nhau và HashSet chỉ lưu một giá trị logic. Nhưng **LocalDate** không thể bằng **LocalDateTime** bằng Object.equals, dù LocalDateTime diễn tả nửa đêm của chính ngày đó. **OffsetDateTime.toInstant()** chuyển ngày-giờ có offset sang mốc tuyệt đối, nên so với Instant.parse trả true.

Các lớp java.time chuẩn đã cài đặt equals/hashCode phù hợp. Khi dùng trực tiếp làm khóa HashMap hoặc phần tử HashSet, thường **không cần tự cài lại equals/hashCode cho chúng**.

## 4. Cùng Instant nhưng không equals: OffsetDateTime

**OffsetDateTime** mang cả **local date-time** và **ZoneOffset**. Hai biểu diễn sau cùng chỉ một thời điểm:

~~~text
2026-10-23T09:00:00+07:00
2026-10-23T02:00:00Z
~~~

Trong phép **equals**, chúng khác nhau: giờ địa phương khác và offset khác. Nhưng **isEqual** trả true khi hai giá trị biểu diễn cùng mốc trên dòng thời gian. **toInstant()** cũng cho hai Instant bằng nhau.

Tạo file **OffsetEqualityDemo.java**:

~~~java
import java.time.OffsetDateTime;
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;

public class OffsetEqualityDemo {
    public static void main(String[] args) {
        OffsetDateTime vietnam =
            OffsetDateTime.parse("2026-10-23T09:00:00+07:00");
        OffsetDateTime utc =
            OffsetDateTime.parse("2026-10-23T02:00:00Z");

        System.out.println("equals: " + vietnam.equals(utc));
        System.out.println("isEqual: " + vietnam.isEqual(utc));
        System.out.println("instant equals: " +
            vietnam.toInstant().equals(utc.toInstant()));
        System.out.println("compareTo zero: " +
            (vietnam.compareTo(utc) == 0));

        Set<OffsetDateTime> offsets = new HashSet<>();
        offsets.add(vietnam);
        offsets.add(utc);

        Set<Instant> instants = new HashSet<>();
        instants.add(vietnam.toInstant());
        instants.add(utc.toInstant());

        System.out.println("offset keys: " + offsets.size());
        System.out.println("instant keys: " + instants.size());
    }
}
~~~

Lệnh:

~~~bash
javac OffsetEqualityDemo.java
java OffsetEqualityDemo
~~~

Kết quả:

~~~text
equals: false
isEqual: true
instant equals: true
compareTo zero: false
offset keys: 2
instant keys: 1
~~~

**Điểm quan trọng về compareTo:** **OffsetDateTime.compareTo** trước hết so mốc trên dòng thời gian; nếu mốc giống nhau, nó xét thêm ngày-giờ địa phương để giữ thứ tự **nhất quán với equals**. Vì vậy, **compareTo == 0** không đồng nghĩa với **isEqual** trong trường hợp hai offset khác nhau. Nếu chỉ muốn hỏi “cùng mốc tuyệt đối?”, dùng **isEqual** hoặc so **toInstant()**.

Nếu dùng **HashSet<OffsetDateTime>**, cả hai biểu diễn được giữ vì equals false. Nếu nghiệp vụ muốn loại trùng theo mốc sự kiện tuyệt đối, dùng **HashSet<Instant>** hoặc khóa được chuyển đổi về Instant.

## 5. ZonedDateTime: cùng lúc vẫn có thể khác ZoneId

**ZonedDateTime** chứa đủ **LocalDateTime + ZoneOffset + ZoneId**. ZoneId thường là tên vùng có quy tắc lịch sử và chuyển giờ, ví dụ **Europe/Paris**. Hai ZonedDateTime có cùng Instant nhưng khác ZoneId không được coi bằng nhau theo equals.

Ví dụ đầy đủ **ZonedEqualityDemo.java**:

~~~java
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class ZonedEqualityDemo {
    public static void main(String[] args) {
        ZonedDateTime paris = ZonedDateTime.of(
            2026, 1, 15, 9, 0, 0, 0, ZoneId.of("Europe/Paris")
        );

        ZonedDateTime sameInstantUtc =
            paris.withZoneSameInstant(ZoneId.of("UTC"));

        ZonedDateTime sameLocalUtc =
            paris.withZoneSameLocal(ZoneId.of("UTC"));

        System.out.println("instant version equals: " +
            paris.equals(sameInstantUtc));
        System.out.println("instant version isEqual: " +
            paris.isEqual(sameInstantUtc));
        System.out.println("instant version compares zero: " +
            (paris.compareTo(sameInstantUtc) == 0));

        System.out.println("local version same wall time: " +
            paris.toLocalDateTime()
                 .equals(sameLocalUtc.toLocalDateTime()));
        System.out.println("local version same instant: " +
            paris.toInstant().equals(sameLocalUtc.toInstant()));
    }
}
~~~

Chạy:

~~~bash
javac ZonedEqualityDemo.java
java ZonedEqualityDemo
~~~

Kết quả:

~~~text
instant version equals: false
instant version isEqual: true
instant version compares zero: false
local version same wall time: true
local version same instant: false
~~~

**withZoneSameInstant(zone)** chuyển vùng múi giờ nhưng **giữ nguyên thời điểm tuyệt đối**, điều chỉnh đồng hồ địa phương. **withZoneSameLocal(zone)** giữ **ngày-giờ nhìn trên đồng hồ** trong khả năng có thể, rồi xác định lại offset/mốc tuyệt đối theo zone mới. Trường hợp không có chuyển đổi DST như giờ UTC ở ví dụ thì ngày-giờ địa phương được giữ chính xác. Hai phương thức phục vụ **hai yêu cầu khác nhau**.

**ZonedDateTime.compareTo** cũng đưa các tiêu chí bổ sung vào thứ tự để kết quả bằng 0 nhất quán với equals; cùng Instant không bảo đảm compareTo trả 0. Không dùng compareTo == 0 thay **isEqual** khi tiêu chí nghiệp vụ chỉ là cùng thời điểm.

### ZoneId và ZoneOffset là hai loại thông tin

- **ZoneOffset** là một độ lệch cố định, ví dụ +07:00, +01:00 hoặc Z.
- **ZoneId** có thể là một vùng như Europe/Paris, có quy tắc offset thay đổi theo thời gian, hoặc một ID mang ý nghĩa offset cố định.
- Hai ZoneId có thể có cùng offset tại một Instant nhưng **khác ID** và khác chính sách thời gian ở những mốc khác.

Ví dụ:

~~~java
ZoneId named = ZoneId.of("UTC");
ZoneId numeric = ZoneOffset.UTC;

// named.equals(numeric) là false: "UTC" khác ID "Z".
// named.getRules().getOffset(Instant.EPOCH)
//     .equals(ZoneOffset.UTC) là true.
~~~

Đây là **đoạn minh họa**, cần import **java.time.ZoneId**, **java.time.ZoneOffset**, **java.time.Instant** nếu đặt vào file Java riêng.

Nếu nghiệp vụ cần lưu **múi giờ do người dùng chọn** để hiển thị hoặc lịch họp tương lai, giữ **ZoneId**. Nếu chỉ cần so thứ tự/cùng mốc sự kiện đã xảy ra, **Instant** thường là khóa phù hợp hơn.

## 6. LocalDate, LocalTime, LocalDateTime không tự mang thời điểm tuyệt đối

**LocalDate** biểu diễn ngày trên lịch ISO; **LocalTime** biểu diễn giờ trong một ngày; **LocalDateTime** kết hợp hai phần. Không kiểu nào tự chứa ZoneId hay offset.

Ví dụ **2026-10-23T09:00** có thể được hiểu là 09:00 tại Hà Nội, Tokyo hoặc London, tương ứng các Instant khác nhau. Vì vậy:

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

public class LocalTimeMeaningDemo {
    public static void main(String[] args) {
        LocalDateTime wall =
            LocalDateTime.parse("2026-10-23T09:00:00");

        Instant vietnam = wall
            .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
            .toInstant();

        Instant tokyo = wall
            .atZone(ZoneId.of("Asia/Tokyo"))
            .toInstant();

        System.out.println("same local datetime: " +
            wall.equals(LocalDateTime.parse("2026-10-23T09:00:00")));
        System.out.println("same instant: " + vietnam.equals(tokyo));
    }
}
~~~

Lưu vào file **LocalTimeMeaningDemo.java**, chạy:

~~~bash
javac LocalTimeMeaningDemo.java
java LocalTimeMeaningDemo
~~~

Kết quả:

~~~text
same local datetime: true
same instant: false
~~~

**Cẩn trọng vào thời điểm chuyển DST:** Một LocalDateTime có thể **không tồn tại** tại một zone (giờ đồng hồ bị nhảy qua) hoặc **xuất hiện hai lần** (giờ đồng hồ bị lặp lại). **LocalDateTime.atZone(zone)** có quy tắc mặc định để giải quyết gap/overlap; quy tắc mặc định đó chưa chắc phù hợp nghiệp vụ. Nếu yêu cầu phân biệt hai lần diễn ra cùng giờ đồng hồ, cần lưu offset hoặc Instant đã được xác định rõ.

**Không dùng LocalDateTime.equals để nhận diện duy nhất một sự kiện toàn cầu** trừ khi miền dữ liệu đã cố ý quy định local date-time và zone theo một chính sách duy nhất, nhất quán.

## 7. isEqual trên kiểu theo lịch và khác hệ lịch

Ngoài khác biệt về offset/zone, java.time còn có các hệ lịch (chronology) khác ngoài ISO. **LocalDate** là ngày ISO, trong khi **JapaneseDate**, **HijrahDate**, **ThaiBuddhistDate** thuộc các chronology khác nhau.

Với giao diện **ChronoLocalDate**, phương thức **isEqual(ChronoLocalDate)** hỏi liệu hai giá trị đại diện cùng ngày trên dòng ngày (epoch day) hay không. Trong khi đó equals vẫn bao gồm **ngữ nghĩa hệ lịch** của kiểu cụ thể.

Ví dụ **ChronologyEqualityDemo.java**:

~~~java
import java.time.LocalDate;
import java.time.chrono.JapaneseDate;

public class ChronologyEqualityDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2026, 10, 23);
        JapaneseDate japanese = JapaneseDate.from(iso);

        System.out.println("equals: " + iso.equals(japanese));
        System.out.println("isEqual: " + iso.isEqual(japanese));
        System.out.println("same epoch day: " +
            (iso.toEpochDay() == japanese.toEpochDay()));
    }
}
~~~

Chạy:

~~~bash
javac ChronologyEqualityDemo.java
java ChronologyEqualityDemo
~~~

Kết quả:

~~~text
equals: false
isEqual: true
same epoch day: true
~~~

**Ý nghĩa:** Hai giá trị cùng ngày vật lý nhưng biểu diễn trong **hai hệ lịch khác nhau**. Muốn tìm cùng ngày bất kể chronology, so **toEpochDay()**, hoặc dùng **ChronoLocalDate.isEqual**. Muốn giữ giá trị theo đúng chronology thì không đổi equals thành “cùng epoch day” một cách tùy tiện.

Nếu dựng khóa Map hoặc Set từ nhiều chronology, hãy quyết định trước muốn phân nhóm theo **cùng chronology + ngày** hay **cùng epoch day**. Với mục tiêu thứ hai, dùng khóa canonical dạng **long epochDay** sẽ rõ ràng và nhất quán hơn.

## 8. Duration và Period: hai hợp đồng cho hai khái niệm khác nhau

**Duration** biểu diễn lượng thời gian theo giây/nanogiây; **Period** biểu diễn các thành phần lịch năm, tháng, ngày theo ISO. Phép equals phản ánh **cấu trúc giá trị** của mỗi loại:

- **Duration.ofMinutes(60)** bằng **Duration.ofHours(1)** vì cả hai biểu diễn cùng 3600 giây.
- **Period.ofMonths(12)** **không equals** **Period.ofYears(1)**: một giá trị có 0 năm/12 tháng, giá trị kia có 1 năm/0 tháng. **normalized()** có thể chuẩn hóa phần tháng về năm.
- **Period.ofDays(1)** không thể mặc định coi tương đương **Duration.ofDays(1)** vì một ngày lịch đi qua vùng đổi giờ có thể dài 23 hoặc 25 giờ; Duration một ngày là 86400 giây.

Tạo file **DurationPeriodDemo.java**:

~~~java
import java.time.Duration;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DurationPeriodDemo {
    public static void main(String[] args) {
        System.out.println("duration equal: " +
            Duration.ofMinutes(60).equals(Duration.ofHours(1)));

        Period months = Period.ofMonths(12);
        Period year = Period.ofYears(1);
        System.out.println("period equal: " + months.equals(year));
        System.out.println("normalized equal: " +
            months.normalized().equals(year));

        ZonedDateTime start = ZonedDateTime.of(
            2026, 3, 28, 12, 0, 0, 0, ZoneId.of("Europe/Paris")
        );

        ZonedDateTime calendarDay = start.plus(Period.ofDays(1));
        ZonedDateTime fixedDay = start.plus(Duration.ofDays(1));

        System.out.println("calendar day hour: " + calendarDay.getHour());
        System.out.println("fixed day hour: " + fixedDay.getHour());
        System.out.println("calendar elapsed hours: " +
            Duration.between(start.toInstant(),
                             calendarDay.toInstant()).toHours());
        System.out.println("fixed elapsed hours: " +
            Duration.between(start.toInstant(),
                             fixedDay.toInstant()).toHours());
    }
}
~~~

Chạy:

~~~bash
javac DurationPeriodDemo.java
java DurationPeriodDemo
~~~

Kết quả với quy tắc múi giờ Europe/Paris cho ngày chuyển sang giờ mùa hè năm 2026:

~~~text
duration equal: true
period equal: false
normalized equal: true
calendar day hour: 12
fixed day hour: 13
calendar elapsed hours: 23
fixed elapsed hours: 24
~~~

Ở Paris, ngày 29/03/2026 chuyển sang giờ mùa hè. Cộng **Period.ofDays(1)** đi tới 12 giờ trưa ngày lịch kế tiếp, với thời gian thực trôi qua là 23 giờ. Cộng **Duration.ofDays(1)** giữ 24 giờ tuyệt đối, dẫn đến 13 giờ địa phương ngày kế tiếp. Kết quả không mâu thuẫn: hai đối tượng đại diện **hai loại đại lượng khác nhau**.

**Không dùng Period để biểu diễn timeout, thời lượng phiên chạy hoặc số giây xử lý.** Dùng Duration cho thời lượng máy đo được. Dùng Period cho chính sách năm/tháng/ngày lịch, ví dụ “gia hạn một tháng” hoặc “ngày tiếp theo tại địa phương”. **Không đổi Duration sang Period hoặc ngược lại** nếu chưa cung cấp đầy đủ điểm bắt đầu, zone và quy tắc nghiệp vụ.

## 9. Độ chính xác, chuẩn hóa và biểu diễn văn bản

Các giá trị thời gian thường có phần nano. **Instant.equals** và **LocalDateTime.equals** xem xét phần nano chính xác; hai mốc cách nhau 1 nanogiây không bằng nhau.

~~~java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public class PrecisionDemo {
    public static void main(String[] args) {
        Instant base = Instant.parse("2026-10-23T00:00:00Z");
        Instant later = base.plusNanos(1);

        System.out.println("raw equals: " + base.equals(later));
        System.out.println("same whole second: " +
            base.truncatedTo(ChronoUnit.SECONDS)
                .equals(later.truncatedTo(ChronoUnit.SECONDS)));
    }
}
~~~

Lưu file **PrecisionDemo.java** và chạy:

~~~bash
javac PrecisionDemo.java
java PrecisionDemo
~~~

Kết quả:

~~~text
raw equals: false
same whole second: true
~~~

**Ràng buộc thiết kế:** Nếu dữ liệu từ database chỉ lưu tới mili giây, còn nguồn khác tới nano giây, phải định nghĩa trước **độ chính xác chuẩn**. Hãy chuẩn hóa giá trị **trước khi lưu và trước khi làm khóa**, với quy tắc cắt hoặc làm tròn phù hợp. Không viết equals tùy biến coi hai mốc “gần nhau” là bằng nhau theo ngưỡng sai số, ví dụ cách nhau dưới 1 giây: quan hệ kiểu đó có thể **không bắc cầu**.

### Định dạng chuỗi không phải giá trị

**toString()**, **DateTimeFormatter** và **parse** liên quan tới biểu diễn văn bản. Hai chuỗi khác nhau có thể biểu diễn cùng Instant, ví dụ có offset khác nhau. Nếu muốn so **Instant**, parse đúng kiểu rồi chuẩn hóa. Không so chuỗi đã định dạng như một cách thay thế cho equals, đặc biệt khi định dạng có thể bỏ qua offset, zone hoặc phần giây.

Không suy ra **equals** từ kết quả **format(...)** trừ khi quy tắc nghiệp vụ cố ý chọn một biểu diễn văn bản chuẩn duy nhất, không mất dữ liệu cần thiết.

## 10. Chọn khóa cho HashMap, HashSet và record

Các kiểu java.time bất biến thường là **khóa tốt** vì equals/hashCode của chúng ổn định theo giá trị. Nhưng chọn **đúng kiểu khóa** quyết định thế nào là một phần tử trùng.

| Bài toán | Khóa phù hợp | Vì sao |
| --- | --- | --- |
| Sự kiện toàn cầu cùng thời điểm | **Instant** | Bỏ qua offset và zone hiển thị |
| Ngày nghỉ địa phương không kèm giờ | **LocalDate** cùng quy ước lịch/zone | Giá trị là ngày, không phải Instant |
| Bản ghi giữ nguyên offset ban đầu | **OffsetDateTime** | Offset là thành phần của giá trị |
| Lịch họp phải nhớ zone được chọn | **ZonedDateTime** hoặc cấu trúc chứa **LocalDateTime + ZoneId + chính sách DST** | Phải phân biệt quy tắc vùng và cách diễn giải giờ địa phương |
| Khoảng thời gian máy đo được | **Duration** | Theo giây và nano |
| Chu kỳ tính theo ngày/tháng/năm lịch | **Period** | Theo đơn vị lịch |
| Thống kê theo tháng | **YearMonth** | Chỉ cần năm và tháng |

### Ví dụ đầy đủ: khóa sự kiện dùng Instant chuẩn hóa

Tạo file **EventKeyDemo.java**:

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;

public class EventKeyDemo {
    record EventKey(String resourceId, Instant startedAt) {}

    public static void main(String[] args) {
        OffsetDateTime local =
            OffsetDateTime.parse("2026-10-23T09:00:00+07:00");
        OffsetDateTime utc =
            OffsetDateTime.parse("2026-10-23T02:00:00Z");

        EventKey first = new EventKey("room-7", local.toInstant());
        EventKey second = new EventKey("room-7", utc.toInstant());

        Map<EventKey, String> events = new HashMap<>();
        events.put(first, "confirmed");

        System.out.println("same key: " + first.equals(second));
        System.out.println("lookup: " + events.get(second));
        System.out.println("size: " + events.size());
    }
}
~~~

Chạy:

~~~bash
javac EventKeyDemo.java
java EventKeyDemo
~~~

Kết quả:

~~~text
same key: true
lookup: confirmed
size: 1
~~~

Record **EventKey** tự sinh equals/hashCode theo các component, trong đó **String** và **Instant** đều có hợp đồng giá trị ổn định. Hai OffsetDateTime khác biểu diễn được chuẩn hóa thành cùng Instant, nên hai khóa bằng nhau.

**Tuy nhiên, nếu business cần phân biệt offset ban đầu**, khóa chỉ chứa Instant đã cố ý **làm mất thông tin đó**. Lúc này cần lưu riêng offset, zone hoặc biểu diễn ban đầu. Việc chuẩn hóa phải theo đúng tiêu chí của bài toán, không phải lúc nào cũng chuyển hết sang UTC là đủ.

### Trường hợp record chứa java.time

Record có component **LocalDate**, **Instant**, **ZoneId**, **Duration**... thường dùng được equals/hashCode sinh tự động. Nhưng phải tự hỏi record đang mô tả **cùng bản ghi dữ liệu** hay **cùng thời điểm**. Ví dụ record gồm **Instant** và **ZoneId** sẽ coi hai record có cùng Instant nhưng zone khác nhau là **khác giá trị**, vì tất cả component đều tham gia so sánh.

## 11. Các sai lầm thường gặp

### 11.1. Dùng == thay equals

Không dựa vào identity với value-based classes. Kể cả khi hai biến tình cờ trỏ cùng object, **==** không biểu diễn tiêu chí tương đương theo hợp đồng thời gian.

### 11.2. Xem isEqual và equals là đồng nghĩa

**OffsetDateTime** và **ZonedDateTime** có thể **isEqual true** nhưng **equals false**. Một bên xét cùng Instant, bên kia xét đầy đủ giá trị chứa offset/zone. Khi chọn cấu trúc dữ liệu, HashMap/HashSet dùng **equals/hashCode**, không âm thầm dùng isEqual.

### 11.3. Tưởng mọi compareTo == 0 chỉ dựa vào Instant

**OffsetDateTime.compareTo** và **ZonedDateTime.compareTo** giữ thứ tự nhất quán với equals; nếu hai giá trị biểu diễn cùng Instant nhưng có offset/zone khác nhau, compareTo có thể khác 0. Đừng dùng TreeSet theo thứ tự tự nhiên để suy ra nó loại trùng chỉ theo cùng Instant.

### 11.4. Xem LocalDateTime là Instant

LocalDateTime không lưu zone, nên không thể biết mốc UTC nếu chưa xác định zone/offset và xử lý gap/overlap. Một ngày-giờ địa phương không đủ cho việc định danh sự kiện tuyệt đối xuyên múi giờ.

### 11.5. Dùng ZoneOffset thay ZoneId khi cần quy tắc tương lai

Offset +07:00 chỉ là độ lệch cố định. Một vùng có thể đổi offset theo mùa hoặc theo quyết định pháp luật. Với lịch hẹn tương lai theo giờ địa phương của vùng, lưu ZoneId và chính sách giải quyết DST; khi cần mốc tuyệt đối, xác định Instant theo quy tắc thời gian tương ứng.

### 11.6. Cho rằng Period một ngày luôn bằng Duration 24 giờ

Qua DST, ngày lịch có thể dài 23 hoặc 25 giờ. Tùy yêu cầu, chọn cộng bằng Period hoặc Duration.

### 11.7. Bỏ qua nano khi gom dữ liệu

Một số nguồn lưu thời gian tới giây, mili hoặc micro, nguồn khác tới nano. Equals vẫn phân biệt phần nano; nếu muốn gom theo giây cần **chuẩn hóa rõ ràng** trước.

### 11.8. Tự cài equals theo sai tiêu chí

Đối với kiểu domain chứa Instant, OffsetDateTime hay ZoneId, **record equals tự động** có thể là đúng nếu mọi component đều thuộc giá trị. Nếu domain muốn so khác, ví dụ chỉ theo eventId, cần mô hình khóa domain riêng. Tránh sửa equals dựa vào phép “xấp xỉ thời gian” không bắc cầu.

## 12. Checklist kiểm tra khi làm việc với java.time

1. **Xác định chính xác loại đại lượng:** ngày, giờ địa phương, mốc tuyệt đối, offset, zone, thời lượng hay kỳ lịch.
2. **Đọc hợp đồng của đúng kiểu:** những trường nào tham gia equals/hashCode? Có API khác như isEqual hoặc toInstant đáp ứng tiêu chí thật sự không?
3. **Kiểm tra phân biệt kiểu:** LocalDate khác LocalDateTime; Instant khác OffsetDateTime; Duration khác Period; dữ liệu cùng ý nghĩa trừu tượng chưa chắc là cùng giá trị kiểu Java.
4. **Định nghĩa khóa trước khi đưa vào HashMap/HashSet:** cùng bản ghi có cần giữ offset, ZoneId, chronology, độ chính xác nano và zone do người dùng chọn không?
5. **Xử lý zone và DST:** một local date-time không tồn tại hoặc tồn tại hai lần thì quy tắc chọn Instant là gì? Có cần lưu offset được chọn không?
6. **Thống nhất precision và chronology:** nếu dùng nhiều nguồn/hệ lịch, chuyển đổi về khóa canonical có chủ đích.
7. **Kiểm tra bằng dữ liệu đối chứng:** hai OffsetDateTime cùng Instant khác offset; hai ZonedDateTime cùng Instant khác zone; hai LocalDateTime cùng giờ ở hai vùng; Duration và Period qua ngày DST; hai Instant lệch 1 nano.
8. **Xác minh hợp đồng hash:** các khóa equals true phải có hash bằng nhau, nhưng hai hash bằng nhau không chứng minh equals true.

**Ghi nhớ cốt lõi:** Các kiểu **java.time là giá trị theo những hợp đồng khác nhau**. **equals/hashCode** trả lời liệu hai object có cùng **giá trị của đúng kiểu đó** hay không. **isEqual** trên kiểu phù hợp hoặc **toInstant()** trả lời liệu chúng có cùng **mốc trên dòng thời gian** hay không. **LocalDateTime** chưa có mốc tuyệt đối; **Period** không phải **Duration**; **ZoneId** không phải **ZoneOffset**. Chọn kiểu và phép so khớp với ý nghĩa nghiệp vụ trước khi gom nhóm, tra cứu hay loại trùng.
