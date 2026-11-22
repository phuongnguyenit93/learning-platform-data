# Giới hạn chuyển đổi hệ lịch theo ý nghĩa nghiệp vụ

## 1. Vì sao chuyển đổi chronology có thể làm sai nghiệp vụ?

Trong Java, `LocalDate` là ngày theo ISO-8601; `java.time.chrono` cung cấp thêm hệ lịch Thai Buddhist, Nhật Bản, Dân quốc và Hijrah. Cùng ngày ISO `2024-06-10` có thể được biểu diễn là `ThaiBuddhist BE 2567-06-10`, `Japanese Reiwa 6-06-10`, `Minguo ROC 113-06-10` hoặc `Hijrah-umalqura AH 1445-12-04` trong dữ liệu JDK được kiểm thử.

Có ba bài toán **không được đánh đồng**:

1. **Đổi cách biểu diễn cùng ngày thực tế:** chuyển ISO sang Thai Buddhist/Japanese/Hijrah dựa trên một `EPOCH_DAY` chung. Ngày trên timeline được giữ nguyên.
2. **Diễn giải bộ số năm–tháng–ngày:** lấy `YEAR`/`MONTH_OF_YEAR`/`DAY_OF_MONTH` của lịch A rồi tạo ngày trong lịch B. Điều này thường tạo **một ngày khác**, dù code không ném lỗi.
3. **Chuyển một quy tắc nghiệp vụ:** “cộng một tháng Hijrah”, “cùng ngày lễ âm lịch năm sau” hay “hạn sau 30 ngày” không phải phép đổi biểu diễn; chúng yêu cầu **giữ đúng hệ lịch và phép toán được hợp đồng định nghĩa**.

Bài học làm rõ `TemporalAccessor`, `Chronology`, `ChronoLocalDate`, `Clock`, `EPOCH_DAY`, calendar arithmetic, era, hỗ trợ miền ngày, lưu trữ và kiểm thử. Đây là các API từ Java 8 **vẫn áp dụng trong Java hiện đại**. Các ví dụ được chạy thử với **JDK 17+** và không dùng công nghệ legacy.

**Nguyên tắc quan trọng:** Một phép chuyển đổi Java thành công chỉ chứng minh dữ liệu có thể biểu diễn; nó **không chứng minh** rằng bạn đã giữ đúng ý nghĩa ngày sinh, lịch kỷ niệm, ngày lễ hay thời hạn pháp lý.

## 2. Nhóm API và phạm vi thông tin

| API | Mang thông tin gì? | Hạn chế cần nhớ |
| --- | --- | --- |
| `LocalDate` | Ngày ISO, không giờ/zone | Không phải timestamp |
| `Chronology` | Hệ lịch, era, factory và phép tính | Không tự cho biết timezone |
| `ChronoLocalDate` | Ngày trong hệ lịch cụ thể | Calendar khác nhau có semantics năm/tháng/era khác |
| `ThaiBuddhistDate` | Ngày Phật lịch | Năm BE không phải năm ISO |
| `JapaneseDate` | Ngày niên hiệu Nhật | Cần era + year-of-era khi nhập theo niên hiệu |
| `MinguoDate` | Ngày Dân quốc | Khác đánh số năm ISO |
| `HijrahDate` | Ngày theo biến thể Hijrah | Độ dài tháng và phạm vi calendar phụ thuộc biến thể/dữ liệu |
| `ChronoField.EPOCH_DAY` | Chỉ số ngày chung từ ISO 1970-01-01 | Không có giờ hoặc zone |
| `ChronoLocalDate.timeLineOrder()` | So ngày theo epoch-day | Không xét tên chronology |
| `Clock` + `ZoneId` | Mốc hiện tại và timezone áp dụng | “Hôm nay” không giống nhau tại mọi vùng |
| `Instant` | Mốc thời gian trên timeline UTC | Không mang nhãn ngày của người dùng |
| `DateTimeFormatter.withChronology` | Format/parse có chronology | Chuỗi thiếu calendar ID vẫn có thể bị hiểu sai |

`ChronoLocalDate` dành cho globalization nâng cao. Oracle khuyến nghị đa số ứng dụng dùng `LocalDate` ISO trong lõi dữ liệu và chỉ đổi sang hệ lịch địa phương ở ranh giới nhập/xuất, trừ khi **toàn bộ nghiệp vụ thực sự hoạt động theo một calendar khác**.

### 2.1. Những điểm khác biệt giữa calendar

- `ThaiBuddhistChronology` và `MinguoChronology` có cấu trúc tháng/ngày dựa trên ISO, nhưng cách đánh số năm khác.
- `JapaneseChronology` có era; số năm thuộc niên hiệu đặt lại khi có era mới.
- `HijrahChronology` có tháng âm lịch thường dài 29 hoặc 30 ngày, với những variant được hỗ trợ qua dữ liệu lịch trong runtime.
- Một chronology có thể không hỗ trợ mọi epoch-day mà `LocalDate` ISO hỗ trợ.
- Một tháng trong lịch Hijrah không nhất thiết có cùng số ngày với tháng ISO tương ứng.

## 3. Chuyển cùng ngày bằng EPOCH_DAY

`EPOCH_DAY` là số ngày tính từ `1970-01-01` ISO (ngày đó bằng 0). Định nghĩa này chung cho `java.time.chrono` để các chronology có thể chuyển **cùng ngày thực tế**.

```java
// Mã minh họa: đã import java.time.* và java.time.chrono.*.
LocalDate iso = LocalDate.of(2024, 6, 10);

ChronoLocalDate thai =
    ThaiBuddhistChronology.INSTANCE.date(iso);

ChronoLocalDate japanese =
    JapaneseChronology.INSTANCE.date(iso);

boolean same =
    iso.toEpochDay() == thai.toEpochDay()
    && iso.toEpochDay() == japanese.toEpochDay();
```

Các cách chuyển đúng về cùng ngày:

```java
// Đoạn minh họa; targetChronology đã được xác định.
ChronoLocalDate target = targetChronology.date(iso);

ChronoLocalDate sameByEpoch =
    targetChronology.dateEpochDay(iso.toEpochDay());

LocalDate backToIso = LocalDate.from(target);

LocalDate backByEpoch =
    LocalDate.ofEpochDay(target.toEpochDay());
```

`Chronology.date(TemporalAccessor)` thường sử dụng `EPOCH_DAY`. Đây **không phải** việc chép các field số sang calendar đích.

**Giới hạn:** Nếu lịch đích không hỗ trợ epoch-day đang xét, việc gọi factory có thể ném `DateTimeException`. Đừng tự sửa ngày sang giá trị gần nhất mà không có chính sách nghiệp vụ.

### Ví dụ 1 — SameDayDemo.java

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.HijrahChronology;
import java.time.chrono.JapaneseChronology;
import java.time.chrono.MinguoChronology;
import java.time.chrono.ThaiBuddhistChronology;

public class SameDayDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2024, 6, 10);

        ChronoLocalDate thai =
            ThaiBuddhistChronology.INSTANCE.date(iso);

        ChronoLocalDate japanese =
            JapaneseChronology.INSTANCE.date(iso);

        ChronoLocalDate minguo =
            MinguoChronology.INSTANCE.date(iso);

        ChronoLocalDate hijrah =
            HijrahChronology.INSTANCE.date(iso);

        System.out.println("iso=" + iso);
        System.out.println("thai=" + thai);
        System.out.println("japanese=" + japanese);
        System.out.println("minguo=" + minguo);
        System.out.println("hijrah=" + hijrah);

        boolean same =
            iso.toEpochDay() == thai.toEpochDay()
            && iso.toEpochDay() == japanese.toEpochDay()
            && iso.toEpochDay() == minguo.toEpochDay()
            && iso.toEpochDay() == hijrah.toEpochDay();

        System.out.println("epochAllEqual=" + same);
        System.out.println("backIso=" +
            LocalDate.ofEpochDay(thai.toEpochDay()));
    }
}
```

```bash
javac SameDayDemo.java
java SameDayDemo
```

Stdout trong JDK đã thử:

```text
iso=2024-06-10
thai=ThaiBuddhist BE 2567-06-10
japanese=Japanese Reiwa 6-06-10
minguo=Minguo ROC 113-06-10
hijrah=Hijrah-umalqura AH 1445-12-04
epochAllEqual=true
backIso=2024-06-10
```

Kết quả `epochAllEqual=true` là bất biến quan trọng. Những số năm/tháng/ngày khác nhau **không phải các ngày khác nhau** trong ví dụ. Ngày Hijrah và phạm vi được hỗ trợ có thể phụ thuộc variant/dữ liệu calendar trong JDK: cần xác định nguồn lịch khi đó là yêu cầu pháp lý hoặc nghiệp vụ.

## 4. Không sao chép YEAR/MONTH/DAY sang lịch khác

Nếu lấy ngày Thai Buddhist tương ứng ISO 2024-06-10, field `YEAR` có giá trị `2567`. Nếu gọi:

```java
// Sai về ngữ nghĩa khi muốn giữ cùng ngày ISO.
LocalDate wrong = LocalDate.of(2567, 6, 10);
```

bạn tạo **năm ISO 2567**, hoàn toàn không phải ngày ISO 2024-06-10. Java có thể chạy thành công, vì kết quả vẫn là ngày ISO hợp lệ.

Cần phân biệt:

- `ThaiBuddhistChronology.INSTANCE.date(2567,6,10)`: tạo đúng **ngày Phật lịch** khi input đã khai là ThaiBuddhist.
- `LocalDate.from(thaiBuddhistDate)`: chuyển **cùng ngày thực tế** về ISO.
- `LocalDate.of(2567,6,10)`: tạo **ngày ISO tương ứng các con số được truyền**.

Không tự suy luận calendar chỉ vì số năm lớn hoặc vì ngôn ngữ người dùng.

### Ví dụ 2 — FieldMisuseDemo.java

```java
import java.time.LocalDate;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.chrono.ThaiBuddhistDate;
import java.time.temporal.ChronoField;

public class FieldMisuseDemo {
    public static void main(String[] args) {
        ThaiBuddhistDate thai =
            ThaiBuddhistChronology.INSTANCE.date(
                LocalDate.of(2024, 6, 10)
            );

        int year = thai.get(ChronoField.YEAR);
        int month = thai.get(ChronoField.MONTH_OF_YEAR);
        int day = thai.get(ChronoField.DAY_OF_MONTH);

        LocalDate wrong =
            LocalDate.of(year, month, day);

        LocalDate right =
            LocalDate.from(thai);

        System.out.println("thaiFields=" +
            year + "-" + month + "-" + day);

        System.out.println("wrongISO=" + wrong);
        System.out.println("rightISO=" + right);

        System.out.println("sameDateWrong=" +
            (wrong.toEpochDay() == thai.toEpochDay()));

        System.out.println("sameDateRight=" +
            (right.toEpochDay() == thai.toEpochDay()));

        System.out.println("explicitThai=" +
            ThaiBuddhistChronology.INSTANCE.date(
                2567, 6, 10
            ));
    }
}
```

```bash
javac FieldMisuseDemo.java
java FieldMisuseDemo
```

Stdout:

```text
thaiFields=2567-6-10
wrongISO=2567-06-10
rightISO=2024-06-10
sameDateWrong=false
sameDateRight=true
explicitThai=ThaiBuddhist BE 2567-06-10
```

**Bài học:** Parse và tạo ngày trong **chronology nguồn**, rồi mới chuyển theo `EPOCH_DAY`. Với những calendar có era hoặc tháng khác ISO, chép các field càng nguy hiểm hơn.

## 5. So sánh khác chronology: equals, isEqual và compareTo

`ChronoLocalDate` cung cấp các phép so có ngữ nghĩa khác nhau:

| API | Quy tắc |
| --- | --- |
| `a.isEqual(b)` | Cùng **epoch-day**, bỏ qua chronology |
| `a.isBefore(b)`/`isAfter(b)` | Trước/sau trên local timeline |
| `a.equals(b)` | Cùng giá trị và **cùng chronology** |
| `a.compareTo(b)` | So ngày, rồi so chronology nếu cùng ngày |
| `ChronoLocalDate.timeLineOrder()` | Comparator chỉ so epoch-day |

Không dùng `equals` để kết luận hai ngày từ hai calendar có cùng ngày thực tế hay không. Đồng thời, nếu business cần lưu **hai nhãn calendar** khác nhau cho audit, không nên gộp chỉ vì chúng cùng epoch-day.

### Ví dụ 3 — CrossChronologyCompareDemo.java

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.ThaiBuddhistDate;

public class CrossChronologyCompareDemo {
    public static void main(String[] args) {
        ChronoLocalDate iso =
            LocalDate.of(2024, 6, 10);

        ChronoLocalDate thai =
            ThaiBuddhistDate.from(iso);

        System.out.println("isEqual=" +
            iso.isEqual(thai));

        System.out.println("equals=" +
            iso.equals(thai));

        System.out.println("sameEpoch=" +
            (iso.toEpochDay() == thai.toEpochDay()));

        System.out.println("compareToIsZero=" +
            (iso.compareTo(thai) == 0));

        System.out.println("timeLineOrderIsZero=" +
            (ChronoLocalDate.timeLineOrder()
                .compare(iso, thai) == 0));
    }
}
```

```bash
javac CrossChronologyCompareDemo.java
java CrossChronologyCompareDemo
```

Stdout:

```text
isEqual=true
equals=false
sameEpoch=true
compareToIsZero=false
timeLineOrderIsZero=true
```

**Ảnh hưởng tới Set/Map:** `HashSet<ChronoLocalDate>` dựa trên `equals` và có thể giữ hai chronology ở cùng ngày. `TreeSet` dùng `timeLineOrder()` có thể coi chúng cùng khóa và bỏ một. Nếu yêu cầu “mỗi ngày thực tế chỉ một bản ghi”, dùng ISO `LocalDate` hoặc `EPOCH_DAY` làm khóa; nếu yêu cầu “mỗi biểu diễn lịch là một bản ghi”, giữ metadata chronology.

## 6. Era: năm-of-era không tự xác định ngày

Với `JapaneseChronology`, niên hiệu đổi thì `YEAR_OF_ERA` bắt đầu lại. Ví dụ:

```text
2019-04-30 ISO -> Japanese Heisei 31-04-30
2019-05-01 ISO -> Japanese Reiwa 1-05-01
```

Lưu mỗi năm-of-era `1` sẽ gây mơ hồ. Phải lưu hoặc suy ra **ERA** theo contract. `Chronology.date(int prolepticYear, ...)` không tự hiểu tham số là `yearOfEra`; nếu input thuộc niên hiệu, dùng overload nhận `JapaneseEra` rõ ràng.

### Ví dụ 4 — JapaneseEraDemo.java

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.chrono.JapaneseChronology;
import java.time.chrono.JapaneseDate;
import java.time.chrono.JapaneseEra;
import java.time.temporal.ChronoField;

public class JapaneseEraDemo {
    public static void main(String[] args) {
        JapaneseDate before =
            JapaneseDate.from(
                LocalDate.of(2019, 4, 30)
            );

        JapaneseDate after =
            JapaneseDate.from(
                LocalDate.of(2019, 5, 1)
            );

        System.out.println("before=" + before);
        System.out.println("after=" + after);

        System.out.println("yearOfEra=" +
            after.get(ChronoField.YEAR_OF_ERA));

        System.out.println("back=" +
            LocalDate.from(after));

        try {
            JapaneseChronology.INSTANCE.date(
                JapaneseEra.REIWA,
                1, 4, 30
            );
            System.out.println("invalidEra=ACCEPTED");
        } catch (DateTimeException ex) {
            System.out.println("invalidEra=REJECTED");
        }
    }
}
```

```bash
javac JapaneseEraDemo.java
java JapaneseEraDemo
```

Stdout:

```text
before=Japanese Heisei 31-04-30
after=Japanese Reiwa 1-05-01
yearOfEra=1
back=2019-05-01
invalidEra=REJECTED
```

**Ứng dụng:** Nếu văn bản pháp lý/hành chính ghi ngày theo niên hiệu, chuyển sang ISO giúp liên thông dữ liệu nhưng không nên bỏ era nguồn nếu cần chứng minh nội dung đã khai. Không tự lấy một năm-of-era nhỏ rồi cộng hằng số để đoán năm ISO.

## 7. “Một tháng” là khái niệm theo calendar

Một lỗi dễ xảy ra trong nghiệp vụ tính hạn: ngày nguồn theo Hijrah đã được chuyển sang ISO, rồi code gọi `iso.plusMonths(1)` mặc dù hợp đồng nói **một tháng Hijrah**.

Vì các chronology có độ dài tháng khác nhau:

- `LocalDate.plusMonths(1)`: cộng theo **ISO**.
- `HijrahDate.plus(1, ChronoUnit.MONTHS)`: cộng theo **Hijrah**.
- `plusDays(30)`: cộng **30 ngày**, không nhất thiết bằng một tháng của bất kỳ lịch nào.
- Ngày cuối tháng có thể đòi điều chỉnh/validation theo quy tắc calendar đích.

### Ví dụ 5 — CalendarArithmeticDemo.java

```java
import java.time.LocalDate;
import java.time.chrono.HijrahDate;
import java.time.temporal.ChronoUnit;

public class CalendarArithmeticDemo {
    public static void main(String[] args) {
        LocalDate iso =
            LocalDate.of(2024, 1, 1);

        HijrahDate hijrah =
            HijrahDate.from(iso);

        LocalDate isoNext =
            iso.plusMonths(1);

        HijrahDate hijrahNext =
            hijrah.plus(1, ChronoUnit.MONTHS);

        LocalDate hijrahNextAsIso =
            LocalDate.from(hijrahNext);

        System.out.println("iso=" + iso);
        System.out.println("hijrah=" + hijrah);
        System.out.println("isoNext=" + isoNext);

        System.out.println("hijrahNextAsIso=" +
            hijrahNextAsIso);

        System.out.println("different=" +
            !isoNext.equals(hijrahNextAsIso));

        System.out.println("hijrahNext=" +
            hijrahNext);

        System.out.println("plusOneDayEquals=" +
            iso.plusDays(1).equals(
                LocalDate.from(
                    hijrah.plus(1, ChronoUnit.DAYS)
                )
            ));
    }
}
```

```bash
javac CalendarArithmeticDemo.java
java CalendarArithmeticDemo
```

Stdout đã kiểm thử trên `Hijrah-umalqura` của JDK:

```text
iso=2024-01-01
hijrah=Hijrah-umalqura AH 1445-06-19
isoNext=2024-02-01
hijrahNextAsIso=2024-01-31
different=true
hijrahNext=Hijrah-umalqura AH 1445-07-19
plusOneDayEquals=true
```

Ở đây cùng ngày 01/01/2024 nhưng phép cộng một tháng đưa tới **01/02/2024 theo ISO** và **31/01/2024 khi cộng theo Hijrah**. Cả hai đều là phép toán hợp lệ, nhưng **chỉ một cách** có thể đúng với quy tắc nghiệp vụ đã được yêu cầu.

Khi giao dịch/tôn giáo/pháp lý đòi Hijrah, phải xác định biến thể lịch và nguồn dữ liệu áp dụng. Một kết quả tính từ JDK không tự thay thế quyết định ngày lễ hoặc lịch được cơ quan có thẩm quyền công bố.

## 8. Clock/ZoneId: “hôm nay” thay đổi theo địa phương

`Chronology.dateNow(Clock)` trả ngày “hôm nay” theo chronology và **timezone của Clock**. Một `Instant` cố định có thể là ngày 10/06 tại UTC nhưng đã sang 11/06 tại TP.HCM:

```text
2024-06-10T23:30:00Z

UTC:                 ISO 2024-06-10
Asia/Ho_Chi_Minh:    ISO 2024-06-11
```

Sự khác nhau này ảnh hưởng ngày hết hạn, cut-off, ngày sinh đủ tuổi, giờ áp dụng luật và tính “hôm nay” theo lịch địa phương.

- `dateNow()` dùng clock/timezone mặc định hệ thống, không lý tưởng cho test tái lập.
- `dateNow(ZoneId)` dùng zone cụ thể nhưng system clock.
- `dateNow(Clock)` dùng nguồn thời gian inject, phù hợp để test có kiểm soát.

### Ví dụ 6 — ClockChronologyDemo.java

```java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.chrono.ThaiBuddhistChronology;

public class ClockChronologyDemo {
    public static void main(String[] args) {
        Instant instant =
            Instant.parse("2024-06-10T23:30:00Z");

        Clock utc = Clock.fixed(
            instant, ZoneOffset.UTC
        );

        Clock hcm = Clock.fixed(
            instant,
            ZoneId.of("Asia/Ho_Chi_Minh")
        );

        System.out.println("utcIso=" +
            LocalDate.now(utc));

        System.out.println("hcmIso=" +
            LocalDate.now(hcm));

        System.out.println("utcThai=" +
            ThaiBuddhistChronology.INSTANCE.dateNow(utc));

        System.out.println("hcmThai=" +
            ThaiBuddhistChronology.INSTANCE.dateNow(hcm));

        System.out.println("clockInstantSame=" +
            Instant.now(utc).equals(Instant.now(hcm)));
    }
}
```

```bash
javac ClockChronologyDemo.java
java ClockChronologyDemo
```

Stdout:

```text
utcIso=2024-06-10
hcmIso=2024-06-11
utcThai=ThaiBuddhist BE 2567-06-10
hcmThai=ThaiBuddhist BE 2567-06-11
clockInstantSame=true
```

Không clock nào sai: **cùng Instant nhưng ngày tại hai vùng khác nhau**. Khi tính hạn theo vùng người dùng hay cơ quan, phải ghi rõ `ZoneId` thay vì lấy timezone server.

**Giới hạn:** `EPOCH_DAY` là date-only; nó không xác định một timestamp. Nếu phải biết thời điểm 09:00 địa phương, còn cần `LocalTime`, `ZoneId` và chính sách DST gap/overlap.

## 9. Instant: cùng sự kiện nhưng khác tên ngày

`Instant` là mốc thời gian tuyệt đối. Với cùng `Instant` và `ZoneId`, có thể dựng một `ZonedDateTime` ISO hoặc `ChronoZonedDateTime` của chronology khác:

```java
// Mã minh họa.
Instant time = Instant.parse("2024-06-10T13:00:00Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime iso = time.atZone(zone);

ChronoZonedDateTime<?> thai =
    ThaiBuddhistChronology.INSTANCE
        .zonedDateTime(time, zone);
```

Hai biểu diễn có thể in năm khác nhau, nhưng `toInstant()` phải trỏ về cùng thời điểm. Calendar là cách mô tả ngày, **không phải bản thân timestamp**.

### Ví dụ 7 — InstantChronologyDemo.java

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.chrono.ChronoZonedDateTime;
import java.time.chrono.ThaiBuddhistChronology;

public class InstantChronologyDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse(
            "2024-06-10T13:00:00Z"
        );

        ZoneId zone =
            ZoneId.of("Asia/Ho_Chi_Minh");

        ChronoZonedDateTime<?> thai =
            ThaiBuddhistChronology.INSTANCE
                .zonedDateTime(instant, zone);

        ZonedDateTime iso =
            instant.atZone(zone);

        System.out.println("iso=" + iso);
        System.out.println("thai=" + thai);

        System.out.println("sameInstant=" +
            iso.toInstant().equals(thai.toInstant()));

        System.out.println("sameEpochDay=" +
            (iso.toLocalDate().toEpochDay()
                == thai.toLocalDate().toEpochDay()));
    }
}
```

```bash
javac InstantChronologyDemo.java
java InstantChronologyDemo
```

Stdout:

```text
iso=2024-06-10T20:00+07:00[Asia/Ho_Chi_Minh]
thai=ThaiBuddhist BE 2567-06-10T20:00+07:00[Asia/Ho_Chi_Minh]
sameInstant=true
sameEpochDay=true
```

**Bài học:** Đổi chronology của một timestamp để hiển thị không đổi sự kiện. Nhưng điều đó **không tự tạo ra quy tắc lặp theo Hijrah** hoặc một lịch hẹn tương lai: cần business rule riêng và ZoneId đúng.

## 10. Formatter phải biết nguồn chronology khi parse

`DateTimeFormatter.withChronology(...)` định nghĩa chronology khi format/parse. Nếu format ISO 2024-06-10 qua ThaiBuddhistChronology, chuỗi là `2567-06-10`. Khi parse chuỗi đó với **cùng formatter** rồi lấy `LocalDate`, kết quả là ISO `2024-06-10`.

Nếu bên nhận parse `2567-06-10` như ISO, nó có thể hiểu là ngày của năm ISO 2567, một lỗi **không ném exception**.

Locale extension cũng có thể yêu cầu calendar: `Locale.forLanguageTag("th-TH-u-ca-buddhist")` chọn ThaiBuddhist qua `Chronology.ofLocale` trong ví dụ.

### Ví dụ 8 — ChronologyFormatterDemo.java

```java
import java.time.LocalDate;
import java.time.chrono.Chronology;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.chrono.ThaiBuddhistDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ChronologyFormatterDemo {
    public static void main(String[] args) {
        LocalDate iso =
            LocalDate.of(2024, 6, 10);

        DateTimeFormatter formatter =
            DateTimeFormatter.ofPattern("uuuu-MM-dd")
                .withResolverStyle(ResolverStyle.STRICT)
                .withChronology(
                    ThaiBuddhistChronology.INSTANCE
                );

        System.out.println("shownThai=" +
            formatter.format(iso));

        System.out.println("asISO=" +
            LocalDate.parse("2567-06-10", formatter));

        System.out.println("thaiDate=" +
            ThaiBuddhistDate.from(
                formatter.parse("2567-06-10")
            ));

        Chronology chronology =
            Chronology.ofLocale(
                Locale.forLanguageTag(
                    "th-TH-u-ca-buddhist"
                )
            );

        System.out.println("localeChrono=" +
            chronology.getId());
    }
}
```

```bash
javac ChronologyFormatterDemo.java
java ChronologyFormatterDemo
```

Stdout:

```text
shownThai=2567-06-10
asISO=2024-06-10
thaiDate=ThaiBuddhist BE 2567-06-10
localeChrono=ThaiBuddhist
```

`uuuu` là proleptic year; `yyyy` là year-of-era; `G` là era và `Y` là week-based year. Nếu parse ngày Nhật ghi theo era, giữ đầy đủ era/year-of-era. Locale dùng cho hiển thị không tự thay thế **calendar ID được business xác nhận**.

## 11. Giới hạn ngày: không phải mọi ISO date đều chuyển được

`LocalDate` ISO có miền ngày rất rộng. Các chronology khác có thể giới hạn hơn:

- `JapaneseChronology` hỗ trợ từ giai đoạn Gregorian được dùng trong niên hiệu Meiji 6 trở đi.
- `HijrahChronology` có dữ liệu tháng/năm theo variant trong một khoảng được runtime hỗ trợ, không bảo đảm mọi ngày lịch sử hoặc tương lai xa.
- Kết quả calendar có thể phụ thuộc dữ liệu/variant của JDK; khi pháp lý/tôn giáo yêu cầu một nguồn khác, phải chọn nguồn được chấp nhận.

Không tự “nội suy” một ngày Hijrah ngoài vùng hỗ trợ bằng phép cộng hằng số nếu nhà cung cấp ngày báo lỗi.

### Ví dụ 9 — RangeFailureDemo.java

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.chrono.HijrahChronology;
import java.time.chrono.JapaneseDate;

public class RangeFailureDemo {
    public static void main(String[] args) {
        LocalDate historic =
            LocalDate.of(1600, 1, 1);

        try {
            HijrahChronology.INSTANCE.date(historic);
            System.out.println("oldHijrah=SUPPORTED");
        } catch (DateTimeException ex) {
            System.out.println("oldHijrah=REJECTED");
        }

        try {
            JapaneseDate.from(
                LocalDate.of(1800, 1, 1)
            );
            System.out.println("oldJapan=SUPPORTED");
        } catch (DateTimeException ex) {
            System.out.println("oldJapan=REJECTED");
        }
    }
}
```

```bash
javac RangeFailureDemo.java
java RangeFailureDemo
```

Stdout trong JDK đã thử:

```text
oldHijrah=REJECTED
oldJapan=REJECTED
```

Khi bị từ chối, API nên báo `DATE_OUTSIDE_SUPPORTED_RANGE` hoặc thông tin lỗi phù hợp, **không tự đổi sang lịch khác rồi tiếp tục** mà không thông báo. Kiểm tra `chronology.range(field)` có thể hỗ trợ kiểm tra phạm vi tổng quát, nhưng một tổ hợp ngày chỉ được xác nhận bằng factory/parse đúng chronology.

## 12. Thiết kế theo ý nghĩa nghiệp vụ

| Yêu cầu | Điều phải giữ | Cách làm |
| --- | --- | --- |
| Hiển thị ISO dưới năm Buddhist | **Cùng ngày thực tế** | `ThaiBuddhistDate.from(iso)` |
| Người dùng nhập 2567-06-10 Phật lịch | **Calendar ID và nghĩa năm** | Tạo bằng ThaiBuddhistChronology rồi `LocalDate.from` |
| Người dùng nhập Reiwa 1 | **Era + year-of-era** | `JapaneseChronology.date(JapaneseEra.REIWA,...)` |
| Cùng một ngày trong 2 chronology | **Epoch-day** | `isEqual` hoặc `toEpochDay()` |
| Cùng bản ghi nguyên văn | **Calendar ID + fields nguồn** | So metadata và giá trị theo schema |
| Cộng 1 tháng Hijrah | **Quy tắc tháng Hijrah** | Thực hiện trên `HijrahDate` |
| Cộng 1 tháng ISO | **Quy tắc tháng ISO** | `LocalDate.plusMonths(1)` |
| Cộng đúng 30 ngày | **30 ngày, không phải tháng** | Chọn phép cộng ngày theo contract |
| Kỷ niệm hằng năm theo Hijrah | **Ngày-tháng và năm Hijrah** | Lưu recurrence rule và tạo từng occurrence theo chronology |
| “Hôm nay” theo TP.HCM | **ZoneId của nghiệp vụ** | `dateNow(clock)` hoặc `LocalDate.now(clock)` |
| Timestamp giao dịch | **Instant** | Lưu `Instant` và chỉ thay calendar khi hiển thị |
| Ngày lễ chính thức | **Nguồn được phép công bố** | Dùng lịch/nguồn pháp lý được domain phê duyệt |

### 12.1. Lưu trữ ISO-first và metadata khi cần audit

Nhiều API/database thuận tiện với ISO date. Có thể lưu:

```json
{
  "isoDate": "2024-06-10",
  "sourceCalendarId": "ThaiBuddhist",
  "sourceEra": "BE",
  "sourceYear": 2567,
  "sourceMonth": 6,
  "sourceDay": 10
}
```

Đây là schema **ứng dụng minh họa**, không phải format JSON được định nghĩa bởi `java.time`. Nếu không cần bảo tồn thông tin nhập nguồn, ISO date có thể đủ; nếu cần audit văn bản pháp lý, giữ calendar ID/era và bộ field gốc theo hợp đồng.

Một quy tắc lặp Hijrah cần lưu `calendarId`, `month`, `dayOfMonth`, quy tắc năm/tháng, chính sách ngày không tồn tại, và nếu có giờ thì thêm `ZoneId`, local time và chính sách DST. Không chỉ lưu ngày ISO đầu tiên rồi `plusYears(1)`.

### 12.2. Tuổi, thời hạn và ngày lễ

- **Ngày sinh:** Chuyển đúng ngày nguồn sang ISO vẫn không tự quyết định “đủ 18 tuổi” phải tính theo năm của lịch nào. Cần business/legal rule.
- **Hạn hợp đồng:** Phân biệt “30 ngày”, “một tháng ISO” và “một tháng Hijrah”; kết quả có thể lệch nhau.
- **Ngày lễ âm lịch:** Calendar library có thể tính theo variant; một số quy định cần ngày được cơ quan/nguồn có thẩm quyền công bố.
- **Lịch hẹn:** Ngày theo chronology không tự xác định Instant; cần local time và zone để resolve, kể cả DST.

## 13. Validation và lỗi nghiệp vụ

Luồng xử lý input có thể gồm:

1. Xác định `calendarId`/variant/era từ schema.
2. Validate năm, tháng, ngày **theo chronology nguồn**.
3. Tạo bằng `Chronology.date(...)`; bắt `DateTimeException` khi input sai hoặc ngoài phạm vi.
4. Nếu cần cùng ngày ISO, chuyển qua `LocalDate.from(...)`.
5. Thực hiện phép cộng tháng/năm/recurrence **trong chronology được nghiệp vụ chọn**.
6. Nếu cần giờ thật, chọn ZoneId/local time và xử lý DST.
7. Lưu ISO date/Instant cùng metadata gốc nếu audit yêu cầu.
8. Trả mã lỗi ổn định; không dùng chuỗi `ex.getMessage()` làm API contract.

Mã lỗi ví dụ có thể là `UNKNOWN_CALENDAR`, `UNSUPPORTED_VARIANT`, `INVALID_ERA`, `INVALID_CALENDAR_DATE`, `DATE_OUTSIDE_SUPPORTED_RANGE`, `BUSINESS_RULE_FAILED`, `AMBIGUOUS_LOCAL_TIME`. Đây là mã **ứng dụng tự định nghĩa**, không phải enum Java.

## 14. Sai lầm và cách phòng tránh

- **Chép YEAR/MONTH/DAY giữa lịch:** Dùng EPOCH_DAY khi mục tiêu là cùng ngày.
- **Bỏ era:** Giữ `ERA` khi năm theo niên hiệu.
- **Cộng ISO month cho luật Hijrah:** Cộng trong chronology của luật, rồi convert.
- **Đồng nhất equals và isEqual:** Chọn equality theo yêu cầu bản ghi/timeline.
- **Dùng compareTo để gộp ngày:** `compareTo` xét chronology, có thể không trả 0.
- **Dùng HashSet để loại ngày trùng epoch-day:** Chuẩn hóa ISO/epoch-day khi unique theo timeline.
- **Coi mọi ngày ISO convert được sang mọi calendar:** Kiểm tra miền hỗ trợ.
- **Nghĩ mọi biến thể Hijrah giống nhau:** Xác nhận variant/data source.
- **Dựa vào system default zone khi tính hôm nay:** Truyền Clock/ZoneId rõ.
- **Coi epoch-day là timestamp:** Bổ sung local time và ZoneId khi cần Instant.
- **Parse Buddhist string bằng ISO:** Cấu hình chronology nguồn.
- **Dùng Locale như luật pháp lý:** Locale không tự quyết định jurisdiction/variant.
- **Lặp ngày Hijrah bằng ISO plusYears:** Sinh occurrence theo calendar đích.
- **Bỏ metadata gốc khi cần audit:** Giữ calendar ID, era và fields theo yêu cầu.
- **Không test thay đổi JDK/calendar data:** Kiểm tra lại các ngày biên/variant.
- **Coi formatter thành công là dữ liệu nghiệp vụ đúng:** Validation và business rule là hai lớp khác nhau.

## 15. Checklist kiểm thử

| Trường hợp | Kỳ vọng |
| --- | --- |
| ISO → Thai/Japanese/Minguo/Hijrah → ISO | Cùng epoch-day khi hỗ trợ |
| Thai YEAR 2567 đưa trực tiếp vào `LocalDate.of` | **Không** cùng ngày 2024 |
| ISO vs Thai cùng ngày | `isEqual=true`, `equals=false` |
| `compareTo` vs `timeLineOrder` | Có thể khác khi chronology khác |
| Biên Heisei/Reiwa 2019 | Era đúng, Reiwa 1-04-30 bị từ chối |
| ISO + 1 tháng vs Hijrah + 1 tháng | Có thể ra ngày khác |
| Cùng Instant UTC vs HCM gần nửa đêm | Ngày local khác |
| Chuyển Instant sang ISO/Thai cùng zone | `toInstant()` không đổi |
| Parse `2567-06-10` bằng formatter Thai | ISO `2024-06-10` |
| ISO date 1800 sang Japanese | Bị từ chối do phạm vi |
| ISO date 1600 sang Hijrah-umalqura | Có thể bị từ chối do dữ liệu |
| Lịch kỷ niệm Hijrah năm sau | Tạo theo Hijrah, không lấy ISO `plusYears` |

Nếu test phụ thuộc ngày hiện tại, inject `Clock.fixed`. Nếu test phụ thuộc calendar variant, ghi rõ variant/JDK để kết quả có thể tái hiện. Những ví dụ có `Hijrah-umalqura` ở trên được kiểm tra với dữ liệu của JDK thử nghiệm; khi deploy, cần quản lý dữ liệu/phiên bản phù hợp.

## 16. Câu hỏi ôn tập

**1.** `ThaiBuddhistDate.from(LocalDate.of(2024,6,10))` có đổi epoch-day không?

**Đáp án:** Không.

**2.** `LocalDate.of(2567,6,10)` có nghĩa là ngày ISO 2024-06-10 không?

**Đáp án:** Không. Nó là ngày ISO năm 2567.

**3.** Khi nào dùng `Chronology.dateEpochDay`?

**Đáp án:** Khi muốn biểu diễn cùng ngày thực tế trong chronology đích.

**4.** `isEqual` khác `equals` thế nào?

**Đáp án:** `isEqual` so epoch-day; `equals` còn xét chronology.

**5.** `compareTo` có luôn trả 0 cho hai ngày cùng epoch-day không?

**Đáp án:** Không, nó còn xét chronology.

**6.** Vì sao cần ERA với ngày theo niên hiệu Nhật?

**Đáp án:** Year-of-era được đặt lại khi đổi niên hiệu.

**7.** Cộng một tháng ISO và Hijrah có luôn tương đương không?

**Đáp án:** Không, lịch có quy tắc tháng khác nhau.

**8.** Ngày Hijrah kỷ niệm năm sau nên tính bằng `LocalDate.plusYears(1)` không?

**Đáp án:** Không nếu nghiệp vụ giữ ngày-tháng Hijrah.

**9.** Cùng Instant có thể tương ứng hai ngày địa phương khác nhau không?

**Đáp án:** Có, phụ thuộc ZoneId.

**10.** `EPOCH_DAY` có đủ để xác định cuộc họp 09:00 ở Paris không?

**Đáp án:** Không, cần thời gian, zone và chính sách DST.

**11.** Vì sao ngày ISO 1800 có thể không đổi sang JapaneseDate được?

**Đáp án:** Ngoài miền lịch Nhật được hỗ trợ.

**12.** Có nên lưu chỉ `"2567-06-10"` mà không nói chronology?

**Đáp án:** Không, nếu nó có thể được hiểu là Buddhist hoặc ISO.

**13.** Ngày lễ Hijrah tính từ thư viện có luôn là nguồn chính thức cho mọi nơi?

**Đáp án:** Không, còn phụ thuộc biến thể và công bố được chấp nhận.

**14.** Khi cần unique theo ngày thực tế, có thể dùng gì?

**Đáp án:** ISO `LocalDate` hoặc `EPOCH_DAY`, tùy schema.

**15.** `Clock.fixed` có giúp kiểm thử đổi lịch không?

**Đáp án:** Có, nếu ngày hiện tại phụ thuộc timezone thì kết quả sẽ tái lập.

## 17. Tài liệu Java hiện hành

- [Oracle Java SE 26 — Chronology](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/Chronology.html): `date`, `dateEpochDay`, `dateNow(Clock)` và `ofLocale`.
- [Oracle Java SE 26 — ChronoLocalDate](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/ChronoLocalDate.html): `EPOCH_DAY`, `isEqual`, `equals` và `timeLineOrder`.
- [Oracle Java SE 26 — JapaneseChronology](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/JapaneseChronology.html): niên hiệu và miền hỗ trợ.
- [Oracle Java SE 26 — ThaiBuddhistChronology](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/ThaiBuddhistChronology.html): Phật lịch.
- [Oracle Java SE 26 — HijrahChronology](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/HijrahChronology.html): biến thể và dữ liệu ngày/tháng.
- [Oracle Java SE 26 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html): định dạng, parse theo chronology.
- [Oracle Java SE 26 — Clock](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Clock.html): nguồn thời gian có thể inject.
- [Oracle Java SE 26 — java.time](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/package-summary.html): ưu tiên ISO cho liên thông hệ thống.

**Ghi nhớ:** `Chronology.date`/`dateEpochDay` có thể giữ **cùng ngày trên timeline**, không giữ nguyên các con số năm-tháng-ngày, era, variant, quy tắc cộng tháng hoặc nghĩa một ngày lễ. Nghiệp vụ nào tính theo calendar nào phải dùng đúng calendar đó; phần lớn dữ liệu ngày liên thông có thể lưu dạng ISO với metadata nguồn khi cần, và chỉ tạo timestamp sau khi đã xác định giờ cùng ZoneId.