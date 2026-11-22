# Chronology và lịch ISO, Nhật, Hijrah, Minguo, Thái trong Java

## 1. Mục tiêu và bức tranh tổng quan

Một thời điểm trên trục thời gian không nhất thiết chỉ có một cách ghi **năm–tháng–ngày**. Ngày Gregorian/ISO `2024-01-01` có thể được biểu diễn theo lịch niên hiệu Nhật Bản, lịch Dân Quốc (Minguo), Phật lịch Thái Lan hoặc lịch Hijrah của Hồi giáo. Tất cả đều có thể chỉ cùng **một ngày vật lý**, nhưng các trường **năm, era, tháng và ngày** có thể mang giá trị/ý nghĩa khác nhau.

Từ Java 8, gói `java.time.chrono` cung cấp API làm việc với nhiều **calendar system**:

- `IsoChronology` — lịch ISO-8601, là nền tảng của `LocalDate`, `LocalDateTime`, `ZonedDateTime`.
- `JapaneseChronology` — lịch niên hiệu Nhật, số năm theo era.
- `HijrahChronology` — lịch âm Hijrah, bản mặc định của JDK là biến thể Umm al-Qura.
- `MinguoChronology` — lịch Dân Quốc, năm ROC 1 tương ứng năm ISO 1912.
- `ThaiBuddhistChronology` — Phật lịch Thái, năm hiện hành có quan hệ `ISO year + 543`.

Bài học sẽ giúp bạn:

1. Hiểu `Chronology`, `ChronoLocalDate`, `Era` và `EPOCH_DAY`.
2. Dùng từng lịch đúng phạm vi; chuyển **cùng ngày** giữa ISO, Nhật, Hijrah, Minguo và Thái.
3. Phân biệt **năm proleptic**, **year-of-era** và ngày bắt đầu era.
4. Xác định khi nào các ngày ở hai lịch được coi là cùng ngày, và vì sao `equals` khác `isEqual`.
5. Tìm calendar theo ID/BCP 47 locale extension, dùng formatter theo chronology khi cần.
6. Hiểu tháng âm Hijrah khác tháng ISO và dữ liệu có **biến thể, phiên bản, phạm vi**.
7. Cộng ngày, liên kết giờ/múi giờ đúng loại chronology.
8. Thiết kế dữ liệu: ưu tiên **ngày ISO cho lưu trữ và trao đổi**; lịch bản địa chủ yếu để hiển thị hoặc xử lý nghiệp vụ có chủ đích.
9. Viết ví dụ **Java 17+ chạy được**, có đầu ra đã kiểm chứng; không dựa vào API legacy.

**Nguyên tắc quan trọng nhất từ tài liệu Oracle:** phần lớn hệ thống ứng dụng nên dùng các class ISO thuộc `java.time` để lưu trữ/giao tiếp qua database, mạng và dịch vụ; sử dụng `java.time.chrono` khi thực sự cần lịch phi ISO. Tách *ngày vật lý* khỏi *cách ghi lịch* giúp giảm lỗi và tránh dùng nhầm quy tắc lịch âm, niên hiệu hoặc các thay đổi chính sách.

## 2. Các thành phần API và mối liên hệ

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| `Chronology` | Hợp đồng cho quy tắc của một calendar system | `JapaneseChronology.INSTANCE` |
| `ChronoLocalDate` | Ngày không có giờ/zone theo một chronology | `JapaneseDate`, `HijrahDate`, `LocalDate` |
| `ChronoLocalDateTime` | Ngày và giờ địa phương theo chronology | `japanese.atTime(LocalTime.NOON)` |
| `ChronoZonedDateTime` | Ngày giờ theo chronology gắn một zone | `chronoDateTime.atZone(ZoneId.of("Asia/Tokyo"))` |
| `Era` | Phân đoạn lớn của dòng lịch | `JapaneseEra.REIWA` |
| `ChronoPeriod` | Khoảng gồm năm/tháng/ngày trong một chronology | `MinguoChronology.INSTANCE.period(1, 0, 0)` |
| `ChronoField.EPOCH_DAY` | Số ngày từ ISO epoch, độc lập cách ghi lịch | `2024-01-01` có epoch day 19723 |
| `Chronology.date(TemporalAccessor)` | Dựng ngày của lịch đích từ dữ liệu temporal đủ thông tin | `JapaneseChronology.INSTANCE.date(isoDate)` |
| `LocalDate.from(TemporalAccessor)` | Lấy biểu diễn ISO của cùng ngày | `LocalDate.from(japaneseDate)` |

Hầu hết class nêu trên đều là **immutable, thread-safe**; dùng phương thức `plus`, `minus`, `with` trả giá trị mới. `Chronology` và các ngày khác lịch không có nghĩa đồng hồ UTC đã đổi: calendar system chỉ xác định cách **phân chia, đánh số và gọi tên các ngày**.

**Không dùng `Calendar`/`Date` kiểu cũ** làm phương án chính để xử lý lịch phi ISO trong code mới. `java.time` và `java.time.chrono` là API hiện hành, có các phép chuyển rõ ràng và bất biến.

## 3. `EPOCH_DAY`: chìa khóa quy chiếu cùng một ngày

Mỗi `ChronoLocalDate` chuẩn có thể được chuyển về một **epoch day**: số ngày tính từ `1970-01-01` theo ISO. Hai biểu diễn ở các lịch khác nhau chỉ cùng một ngày nếu giá trị `toEpochDay()` bằng nhau, không phụ thuộc cách đặt tên năm/era.

Ví dụ `LocalDate.of(2024, 1, 1).toEpochDay()` là **19723**. Khi convert `LocalDate` sang các chronology, epoch day **không đổi**; khác biệt nằm ở nhãn lịch.

Lưu thành `ChronologyOverviewDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.Chronology;
import java.time.chrono.HijrahChronology;
import java.time.chrono.IsoChronology;
import java.time.chrono.JapaneseChronology;
import java.time.chrono.MinguoChronology;
import java.time.chrono.ThaiBuddhistChronology;
import java.util.List;

public class ChronologyOverviewDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2024, 1, 1);
        List<Chronology> calendars = List.of(
                IsoChronology.INSTANCE,
                JapaneseChronology.INSTANCE,
                HijrahChronology.INSTANCE,
                MinguoChronology.INSTANCE,
                ThaiBuddhistChronology.INSTANCE);

        for (Chronology chronology : calendars) {
            ChronoLocalDate date = chronology.date(iso);
            boolean sameEpochDay =
                    date.toEpochDay() == iso.toEpochDay();
            boolean roundTrip =
                    LocalDate.from(date).equals(iso);
            System.out.println(chronology.getId() +
                    " | epochDaySame=" + sameEpochDay +
                    " | roundTrip=" + roundTrip);
        }
    }
}
```

Chạy:

```bash
javac ChronologyOverviewDemo.java
java ChronologyOverviewDemo
```

Stdout:

```text
ISO | epochDaySame=true | roundTrip=true
Japanese | epochDaySame=true | roundTrip=true
Hijrah-umalqura | epochDaySame=true | roundTrip=true
Minguo | epochDaySame=true | roundTrip=true
ThaiBuddhist | epochDaySame=true | roundTrip=true
```

**Vì sao không in nguyên ngày Hijrah vào stdout ví dụ này?** Biến thể Hijrah được hỗ trợ dựa trên dữ liệu lịch của JDK, có thể có điều chỉnh theo bản phân phối/phiên bản. Kiểm tra **cùng epoch day và round-trip** bền vững hơn việc cố định cả nhãn ngày âm vào một bài kiểm thử sẽ chạy nhiều môi trường.

**Lưu ý phạm vi:** Không phải chronology nào cũng hỗ trợ mọi `LocalDate` có thể biểu diễn; ví dụ lịch Nhật trong JDK có giới hạn lịch sử, lịch Hijrah có dữ liệu trong một khoảng năm nhất định. Nếu cố convert ngày ngoài phạm vi, API có thể ném `DateTimeException`. Ví dụ `2024-01-01` được chọn trong phạm vi thông dụng của các lịch đã nêu, không có nghĩa mọi năm trong `LocalDate` đều chuyển đổi được.

## 4. `IsoChronology`: nền tảng ổn định cho dữ liệu ứng dụng

`IsoChronology.INSTANCE` biểu diễn lịch ISO-8601 dựa trên lịch Gregorian kéo dài theo phép toán (proleptic Gregorian). Đây là hệ lịch mặc định của các class phổ biến:

- `LocalDate`, `LocalTime`, `LocalDateTime`.
- `OffsetDateTime`, `ZonedDateTime` khi biểu diễn ngày giờ ISO.
- `Instant` là một điểm trên timeline, không mang chronology địa phương.
- `DateTimeFormatter.ISO_LOCAL_DATE` và các formatter ISO theo contract.

Đối với phần lớn ứng dụng, lưu ngày dạng `LocalDate` khi dữ liệu là **ngày không có giờ**, dùng `Instant` khi là **thời điểm tuyệt đối**, rồi format theo chronology/locale cho giao diện nếu có yêu cầu.

`LocalDate` thực thi `ChronoLocalDate` nên có thể tham gia các API tổng quát theo chronology. Nhưng bạn **không nên** cố thiết kế tất cả hàm domain dưới dạng `ChronoLocalDate` khi hệ thống chỉ dùng ISO: mã generic có thể khó nhận diện loại lịch, làm phép cộng năm/tháng hoặc parse ngày không như mong đợi.

Lưu `IsoAndEpochDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.Chronology;
import java.time.chrono.IsoChronology;
import java.time.temporal.ChronoField;

public class IsoAndEpochDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2024, 1, 1);

        System.out.println("chronology = " +
                Chronology.from(iso).getId());
        System.out.println("instance = " +
                (Chronology.from(iso) == IsoChronology.INSTANCE));
        System.out.println("epochDay = " + iso.toEpochDay());
        System.out.println("epochField = " +
                iso.getLong(ChronoField.EPOCH_DAY));
        System.out.println("roundTrip = " +
                LocalDate.ofEpochDay(iso.toEpochDay()));
    }
}
```

```bash
javac IsoAndEpochDemo.java
java IsoAndEpochDemo
```

```text
chronology = ISO
instance = true
epochDay = 19723
epochField = 19723
roundTrip = 2024-01-01
```

**EPOCH_DAY đo theo ngày**, không phải epoch milliseconds/seconds. Đừng biến nó thành `Instant` bằng cách giả định một ngày luôn là 24 giờ địa phương và nhân tùy tiện với 86.400: ngày địa phương ở vùng có thay đổi offset có thể dài/ngắn khác 24 giờ thực. Nếu cần timestamp, phải bổ sung giờ và zone/offset phù hợp theo nghiệp vụ.

## 5. Lịch Nhật: `JapaneseChronology` và `JapaneseEra`

`JapaneseChronology` được dùng trong lịch niên hiệu của Nhật Bản. Cấu trúc tháng/ngày và quy tắc năm nhuận tương ứng ISO, nhưng **tên era và số năm trong era** thay đổi theo ngày bắt đầu niên hiệu.

Ví dụ theo các mốc đã xảy ra:

- `2019-04-30` (ISO) thuộc **Heisei 31**.
- `2019-05-01` (ISO) thuộc **Reiwa 1**.
- `2024-01-01` (ISO) thuộc **Reiwa 6**.

Khác với lịch được đánh số năm liên tục, `YEAR_OF_ERA` của Nhật **được đặt lại khi bước sang era**. Trong khi đó, `ChronoField.YEAR` (proleptic year) ở Nhật tương ứng năm ISO theo Java API.

Với năm 2019, **không được** dùng mỗi `yearOfEra=1` mà không có `era` để quyết định một ngày: Heisei 1 và Reiwa 1 không cùng khoảng. Các phép tạo ngày bằng `JapaneseDate.of(era,yearOfEra,month,day)` phải **hợp lệ trong chính era đó**; ngày 30/04/2019 không thuộc Reiwa.

Lưu `JapaneseEraBoundaryDemo.java`:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.chrono.JapaneseDate;
import java.time.chrono.JapaneseEra;
import java.time.temporal.ChronoField;

public class JapaneseEraBoundaryDemo {
    private static void show(LocalDate iso) {
        JapaneseDate japanese = JapaneseDate.from(iso);
        System.out.println(iso + " -> era=" +
                japanese.getEra() + ", yearOfEra=" +
                japanese.get(ChronoField.YEAR_OF_ERA) +
                ", isoYear=" +
                japanese.get(ChronoField.YEAR));
    }

    public static void main(String[] args) {
        show(LocalDate.of(2019, 4, 30));
        show(LocalDate.of(2019, 5, 1));
        show(LocalDate.of(2024, 1, 1));

        JapaneseDate valid = JapaneseDate.of(
                JapaneseEra.REIWA, 1, 5, 1);
        System.out.println("valid = " +
                LocalDate.from(valid));

        try {
            JapaneseDate.of(JapaneseEra.REIWA, 1, 4, 30);
            System.out.println("unexpected");
        } catch (DateTimeException ex) {
            System.out.println("invalid era date rejected");
        }
    }
}
```

```bash
javac JapaneseEraBoundaryDemo.java
java JapaneseEraBoundaryDemo
```

```text
2019-04-30 -> era=Heisei, yearOfEra=31, isoYear=2019
2019-05-01 -> era=Reiwa, yearOfEra=1, isoYear=2019
2024-01-01 -> era=Reiwa, yearOfEra=6, isoYear=2024
valid = 2019-05-01
invalid era date rejected
```

**Giới hạn lịch sử:** Java hỗ trợ lịch Nhật kể từ phần lịch Gregorian tương ứng **Meiji 6, ngày 01/01/1873**; ngày trước đó không thuộc phạm vi được hỗ trợ của `JapaneseChronology`. Không giả sử có thể chuyển mọi ngày ISO từ thời cổ đại thành JapaneseDate. Danh sách niên hiệu có thể được cập nhật khi Nhật công bố niên hiệu mới; không tự hardcode “era mới nhất luôn là Reiwa” trong ứng dụng lâu dài.

### 5.1. Era và năm proleptic không phải cùng trường

`japanese.get(ChronoField.YEAR_OF_ERA)` trả số năm trong niên hiệu; `japanese.get(ChronoField.YEAR)` trả năm proleptic theo chronology (ở Nhật JDK trùng năm ISO). `getEra()` trả `JapaneseEra`. Khi cần định danh một ngày lịch Nhật, phải có **era + yearOfEra + month + day**, hoặc dùng `EPOCH_DAY`/ISO date nếu mục tiêu là lưu một ngày xác định.

Ngay cả với ngày Nhật, `2024-02-29` vẫn là năm nhuận ISO vì calendar này dùng cùng cấu trúc ngày tháng ISO. Đừng sao chép phép tính này sang Hijrah, nơi quy luật độ dài tháng/năm hoàn toàn khác.

## 6. Lịch Dân Quốc: `MinguoChronology`

Lịch Minguo được dùng trong các ngữ cảnh của Đài Loan. Quan hệ được định nghĩa trong JDK:

- `1912-01-01` ISO = **Minguo ROC 1-01-01**.
- `2024-01-01` ISO = **Minguo ROC 113-01-01**.
- Với era hiện hành, năm Minguo proleptic bằng **năm ISO − 1911**.
- Tháng, ngày, leap year theo lịch ISO.

Hệ này có các era `MinguoEra.ROC` và `MinguoEra.BEFORE_ROC`. Nếu chuyển sang trước năm 1912, không thể cứ dùng một số âm rồi trình bày nó thành “ROC năm âm”; phải tuân theo quy tắc proleptic year/era và cách hiển thị của chronology.

Lưu `MinguoCalendarDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.MinguoChronology;
import java.time.chrono.MinguoDate;
import java.time.chrono.MinguoEra;
import java.time.temporal.ChronoField;

public class MinguoCalendarDemo {
    public static void main(String[] args) {
        MinguoDate first = MinguoDate.of(1, 1, 1);
        MinguoDate year113 = MinguoDate.of(113, 1, 1);

        System.out.println("ROC1ISO = " +
                LocalDate.from(first));
        System.out.println("ROC113ISO = " +
                LocalDate.from(year113));
        System.out.println("era = " +
                year113.getEra());
        System.out.println("yearOfEra = " +
                year113.get(ChronoField.YEAR_OF_ERA));
        System.out.println("yearField = " +
                year113.get(ChronoField.YEAR));
        System.out.println("eraMatch = " +
                (year113.getEra() == MinguoEra.ROC));
        System.out.println("leap113 = " +
                MinguoChronology.INSTANCE.isLeapYear(113));
    }
}
```

```bash
javac MinguoCalendarDemo.java
java MinguoCalendarDemo
```

```text
ROC1ISO = 1912-01-01
ROC113ISO = 2024-01-01
era = ROC
yearOfEra = 113
yearField = 113
eraMatch = true
leap113 = true
```

`MinguoChronology` là **ISO-based** ở cấu trúc tháng/ngày/năm nhuận, nhưng dữ liệu “năm 113” không phải “năm ISO 113”. Với API công cộng, không để client đoán chronology từ độ lớn của year; hợp đồng dữ liệu phải nêu rõ lịch và era hoặc gửi ngày ISO.

## 7. Phật lịch Thái: `ThaiBuddhistChronology`

`ThaiBuddhistChronology` biểu diễn lịch Phật giáo Thái Lan. Trong chronology của Java:

- Năm Thai Buddhist proleptic bằng **năm ISO + 543**.
- Tháng và ngày khớp với ISO.
- Quy tắc năm nhuận khớp với ISO.
- Với era hiện hành, `ThaiBuddhistEra.BE` thể hiện Buddhist Era; còn era trước là `BEFORE_BE`.

Ví dụ:

- `2024-01-01` ISO = **Thai Buddhist BE 2567-01-01**.
- `1941-01-01` ISO = **Thai Buddhist BE 2484-01-01**.

**Không áp dụng công thức +543 cho mọi lịch khác** (nhất là Hijrah), và không dùng con số này để suy ra chính sách văn hóa/lịch sử ngoài contract của Java. Tính nhất quán của phép chuyển trong JDK là điều ta cần.

Lưu `ThaiBuddhistCalendarDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.chrono.ThaiBuddhistDate;
import java.time.chrono.ThaiBuddhistEra;
import java.time.temporal.ChronoField;

public class ThaiBuddhistCalendarDemo {
    public static void main(String[] args) {
        ThaiBuddhistDate thai =
                ThaiBuddhistDate.from(LocalDate.of(2024, 1, 1));

        System.out.println("ISO = " + LocalDate.from(thai));
        System.out.println("year = " +
                thai.get(ChronoField.YEAR));
        System.out.println("yearOfEra = " +
                thai.get(ChronoField.YEAR_OF_ERA));
        System.out.println("era = " + thai.getEra());
        System.out.println("eraMatch = " +
                (thai.getEra() == ThaiBuddhistEra.BE));
        System.out.println("leap2567 = " +
                ThaiBuddhistChronology.INSTANCE.isLeapYear(2567));
        System.out.println("builtSame = " +
                ThaiBuddhistDate.of(2567, 1, 1)
                        .isEqual(thai));
    }
}
```

```bash
javac ThaiBuddhistCalendarDemo.java
java ThaiBuddhistCalendarDemo
```

```text
ISO = 2024-01-01
year = 2567
yearOfEra = 2567
era = BE
eraMatch = true
leap2567 = true
builtSame = true
```

**Điểm quan trọng khi format:** Nếu muốn in một ngày theo Phật lịch Thái, dùng chronology Thái cho formatter và một locale thích hợp; nhưng khi lưu vào database là ISO calendar, dùng `LocalDate.from(thaiDate)`. Giao diện có thể hiển thị năm 2567 mà vẫn truy vấn theo ngày ISO 2024 chính xác.

## 8. Lịch Hijrah: âm lịch, nhiều biến thể và phạm vi dữ liệu

`HijrahChronology` là hệ lịch Hồi giáo dựa trên tháng âm lịch. Biến thể dựng sẵn phổ biến trên JDK là **`HijrahChronology.INSTANCE`**, với chronology ID `Hijrah-umalqura` và calendar type `islamic-umalqura`.

**Khác biệt cốt lõi với ISO/Japanese/Minguo/ThaiBuddhist:**

- Tháng Hijrah thường có **29 hoặc 30 ngày**.
- Năm Hijrah có **354 hoặc 355 ngày**.
- Ngày bắt đầu tháng có thể thay đổi theo **biến thể lịch** (tính toán hoặc quan sát) và dữ liệu đã được công bố.
- Năm/tháng/ngày Hijrah **không** thể tính bằng cộng một hằng số năm vào ISO.
- Phạm vi năm được hỗ trợ của JDK cho từng biến thể là hữu hạn và được cấu hình bởi dữ liệu, nên không phải mọi ngày `LocalDate` đều chuyển được.

`HijrahChronology.INSTANCE` **không đại diện cho mọi lịch Hồi giáo ở mọi quốc gia/địa phương**. `HijrahDate` được xây từ biến thể đã chọn; muốn đối chiếu lịch được tổ chức cụ thể công nhận, phải xác nhận biến thể và dữ liệu được sử dụng.

Đây là điểm dễ gây sai nghiệp vụ trong lịch sinh hoạt tôn giáo, lễ hội, hồ sơ có ngày Hijrah và các quy định địa phương. Khi cùng một ngày ISO có cách ghi Hijrah khác nhau giữa các nguồn, đừng kết luận một hệ thống “sai” nếu chưa kiểm tra biến thể và dữ liệu.

Lưu `HijrahCalendarDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.HijrahChronology;
import java.time.chrono.HijrahDate;
import java.time.chrono.Chronology;
import java.time.temporal.ChronoField;

public class HijrahCalendarDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2024, 1, 1);
        HijrahDate hijrah = HijrahDate.from(iso);

        System.out.println("id = " +
                HijrahChronology.INSTANCE.getId());
        System.out.println("calendarType = " +
                HijrahChronology.INSTANCE.getCalendarType());
        System.out.println("roundTrip = " +
                LocalDate.from(hijrah));
        System.out.println("sameEpochDay = " +
                (hijrah.toEpochDay() == iso.toEpochDay()));
        System.out.println("monthIs29Or30 = " +
                (hijrah.lengthOfMonth() == 29 ||
                 hijrah.lengthOfMonth() == 30));
        System.out.println("yearIs354Or355 = " +
                (hijrah.lengthOfYear() == 354 ||
                 hijrah.lengthOfYear() == 355));
        System.out.println("sameChronology = " +
                (Chronology.from(hijrah) ==
                 HijrahChronology.INSTANCE));
    }
}
```

```bash
javac HijrahCalendarDemo.java
java HijrahCalendarDemo
```

```text
id = Hijrah-umalqura
calendarType = islamic-umalqura
roundTrip = 2024-01-01
sameEpochDay = true
monthIs29Or30 = true
yearIs354Or355 = true
sameChronology = true
```

Ví dụ xác minh **hợp đồng tháng/năm âm** và bảo toàn ngày vật lý mà không “đóng đinh” ngày Hijrah cụ thể trong stdout. Việc format ngày Hijrah cần chọn chính xác calendar type/locale và kiểm thử trên các JDK/tzdb/chronology data đang được triển khai.

### 8.1. Giới hạn và version của dữ liệu Hijrah

Tài liệu Oracle mô tả các biến thể có thể được định nghĩa bằng dữ liệu cấu hình lịch, gồm ID, type, điểm neo ISO và độ dài từng tháng trong một khoảng năm. Nguồn dữ liệu này có thể được bổ sung/điều chỉnh trong các phiên bản JDK hoặc từ cấu hình nhà cung cấp.

Do đó:

- `HijrahDate.from(isoDate)` có thể ném `DateTimeException` nếu ngoài phạm vi.
- Không hardcode một biên dưới/biên trên chung cho mọi JDK và mọi biến thể.
- Với hệ thống cần kiểm toán, lưu **ngày ISO tương ứng**, định danh Hijrah variant và phiên bản dữ liệu đã dùng nếu cần tái tạo cách hiển thị lịch sử.
- Nếu app dùng lịch tôn giáo hoặc sự kiện được cơ quan riêng quy định, hãy so sánh với nguồn lịch có thẩm quyền thích hợp thay vì giả định `Hijrah-umalqura` là lựa chọn duy nhất.

Lưu ý kỹ thuật: `Chronology.getAvailableChronologies()` có thể trả thêm các calendar của provider. Không dựa vào số lượng cố định “chắc chắn đúng năm hệ” trên mọi môi trường.

## 9. Tạo ngày bằng `Chronology` hoặc class cụ thể

Khi biết compile-time kiểu lịch, thường nên dùng class cụ thể:

```java
JapaneseDate japanese = JapaneseDate.from(iso);
MinguoDate minguo = MinguoDate.from(iso);
ThaiBuddhistDate thai = ThaiBuddhistDate.from(iso);
HijrahDate hijrah = HijrahDate.from(iso);
```

*Đây là snippet, với `iso` kiểu `LocalDate` và import tương ứng. Chỉ hoạt động khi ngày nằm trong phạm vi của chronology đích.*

Khi nguồn input chọn chronology lúc chạy, có thể dùng:

```java
Chronology calendar = Chronology.of("Japanese");
ChronoLocalDate result = calendar.date(iso);
LocalDate stable = LocalDate.from(result);
```

*Snippet yêu cầu `iso`, `Chronology` và `ChronoLocalDate`, `LocalDate` đã được khai báo/import.*

Các dạng khác:

- `chronology.date(year, month, day)` dùng **proleptic-year** của chronology, không phải một số `year-of-era` bất kỳ.
- `chronology.date(era, yearOfEra, month, day)` cho phép truyền era khi cần.
- `chronology.dateEpochDay(iso.toEpochDay())` dựng ngày cùng epoch day.
- `chronology.dateNow(clock)` tạo ngày hiện tại theo clock đã tiêm để test; không nên hardcode “bây giờ” trong unit test.

**Không nhầm `date(2024, 1, 1)` của JapaneseChronology với `date(2024, 1, 1)` của ThaiBuddhistChronology.** Số 2024 là **proleptic-year của lịch được chọn**, nên chúng có thể tương ứng **hai ngày ISO khác nhau**.

## 10. Chọn chronology theo ID hoặc BCP 47 locale extension

`Chronology.of(String)` tìm calendar theo ID hoặc calendar type được hỗ trợ. `Chronology.ofLocale(Locale)` cho phép dùng Unicode locale extension `u-ca-...` để chỉ rõ calendar.

Ví dụ định danh thường gặp:

| Chronology | ID | Calendar type / `u-ca` |
| --- | --- | --- |
| ISO | `ISO` | `iso8601` |
| Japanese | `Japanese` | `japanese` |
| Hijrah Umm al-Qura | `Hijrah-umalqura` | `islamic-umalqura` |
| Minguo | `Minguo` | `roc` |
| Thai Buddhist | `ThaiBuddhist` | `buddhist` |

`Locale.JAPAN` hoặc việc chọn ngôn ngữ `ja` không nhất thiết tự ép chronology Nhật niên hiệu. Nếu muốn **rõ loại lịch**, sử dụng `u-ca-japanese` hoặc `withChronology(JapaneseChronology.INSTANCE)` khi định dạng.

Lưu `ChronologyLookupDemo.java`:

```java
import java.time.chrono.Chronology;
import java.time.chrono.IsoChronology;
import java.util.List;
import java.util.Locale;

public class ChronologyLookupDemo {
    public static void main(String[] args) {
        List<String> locales = List.of(
                "ja-JP-u-ca-japanese",
                "zh-TW-u-ca-roc",
                "th-TH-u-ca-buddhist",
                "en-US-u-ca-islamic-umalqura");

        for (String tag : locales) {
            Locale locale = Locale.forLanguageTag(tag);
            System.out.println(tag + " -> " +
                    Chronology.ofLocale(locale).getId());
        }

        System.out.println("idMinguo = " +
                Chronology.of("Minguo").getId());
        System.out.println("plainJapanISO = " +
                (Chronology.ofLocale(Locale.JAPAN)
                        == IsoChronology.INSTANCE));
    }
}
```

```bash
javac ChronologyLookupDemo.java
java ChronologyLookupDemo
```

```text
ja-JP-u-ca-japanese -> Japanese
zh-TW-u-ca-roc -> Minguo
th-TH-u-ca-buddhist -> ThaiBuddhist
en-US-u-ca-islamic-umalqura -> Hijrah-umalqura
idMinguo = Minguo
plainJapanISO = true
```

**Điểm thực tiễn:** Locale có hai khía cạnh khác nhau:

1. **Ngôn ngữ và quy tắc hiển thị**: ví dụ tên tháng/era bằng tiếng Nhật.
2. **Calendar system**: chỉ khi có calendar extension `u-ca-...` hoặc chỉ định chronology rõ.

Đừng suy ra hệ lịch từ quốc gia/ngôn ngữ mà không có yêu cầu của người dùng. Với hệ thống đa ngôn ngữ, nên có lựa chọn calendar rõ ràng và lưu thành setting.

## 11. `YEAR`, `YEAR_OF_ERA` và `ERA`

Ba khái niệm cần phân biệt trong API `ChronoField`:

- `YEAR`: năm proleptic của chronology, có thể âm/0 tùy lịch.
- `YEAR_OF_ERA`: số năm trong một era, thường bắt đầu từ 1.
- `ERA`: phần tử chỉ era, như `JapaneseEra.REIWA` hoặc `MinguoEra.ROC`.

Ví dụ:

| Ngày ISO | Chronology | ERA | YEAR_OF_ERA | YEAR |
| --- | --- | --- | ---: | ---: |
| `2019-05-01` | Japanese | Reiwa | 1 | 2019 |
| `2024-01-01` | Japanese | Reiwa | 6 | 2024 |
| `2024-01-01` | Minguo | ROC | 113 | 113 |
| `2024-01-01` | ThaiBuddhist | BE | 2567 | 2567 |

Trong lịch Nhật, `YEAR` và `YEAR_OF_ERA` dễ khác nhau nhiều. Khi định dạng niên hiệu, phải giữ `ERA`. Nếu chỉ lưu `YEAR_OF_ERA` vào một cột chung tên `year`, rất dễ làm hỏng báo cáo hoặc chuyển đổi năm.

Đặc biệt, pattern `yyyy` trong `DateTimeFormatter` là **year-of-era**; `uuuu` là **proleptic year**. Khi parse STRICT mà không có era rõ ràng, `yyyy` có thể không resolve đủ dữ liệu. Với lịch Nhật, formatter niên hiệu cần **era** (chẳng hạn pattern `G y-MM-dd`), chronology và locale phù hợp.

`Chronology.eraOf(int)` có thể cung cấp Era từ mã số, nhưng ý nghĩa mã tùy chronology, không hoán đổi mã era giữa các lịch. Dùng enum/class era của chronology tương ứng hoặc API query theo đúng dữ liệu.

## 12. So sánh ngày khác chronology: `equals` không phải `isEqual`

Giả sử:

```text
ISO             2024-01-01
Japanese        Reiwa 6-01-01
Minguo          ROC 113-01-01
ThaiBuddhist    BE 2567-01-01
```

Đó có thể là **cùng epoch day**, nhưng **không phải cùng object giá trị theo cùng chronology**.

- `ChronoLocalDate.equals(...)` xét cả ngày và chronology.
- `ChronoLocalDate.isEqual(other)` xét **cùng epoch day** bất kể chronology.
- `ChronoLocalDate.isBefore/isAfter` xét thứ tự ngày trên timeline.
- `ChronoLocalDate.compareTo` so timeline trước, sau đó **chronology** để nhất quán với `equals`: hai lịch khác nhau cùng ngày có thể có kết quả `compareTo != 0`.
- `ChronoLocalDate.timeLineOrder()` cung cấp Comparator chỉ xét **epoch day**.

Điều này ảnh hưởng `TreeSet`, `TreeMap`, sort và dedup. Nếu một tập cần giữ **cả hai biểu diễn** của cùng ngày, so sánh toàn bộ ngày/chronology. Nếu muốn **mỗi ngày thực chỉ một phần tử**, dùng `timeLineOrder()` hoặc chuẩn hóa `LocalDate` trước.

Lưu `ChronoDateComparisonDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.JapaneseDate;
import java.time.chrono.MinguoDate;
import java.util.Set;
import java.util.TreeSet;

public class ChronoDateComparisonDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2024, 1, 1);
        JapaneseDate japanese = JapaneseDate.from(iso);
        MinguoDate minguo = MinguoDate.from(iso);

        System.out.println("equalsISO = " +
                japanese.equals(iso));
        System.out.println("sameDay = " +
                japanese.isEqual(iso));
        System.out.println("before = " +
                japanese.isBefore(minguo));
        System.out.println("compareToZero = " +
                (japanese.compareTo(iso) == 0));
        System.out.println("timelineZero = " +
                (ChronoLocalDate.timeLineOrder()
                        .compare(japanese, minguo) == 0));

        Set<ChronoLocalDate> byFullValue = new TreeSet<>();
        byFullValue.add(iso);
        byFullValue.add(japanese);
        byFullValue.add(minguo);

        Set<ChronoLocalDate> byEpochDay =
                new TreeSet<>(ChronoLocalDate.timeLineOrder());
        byEpochDay.add(iso);
        byEpochDay.add(japanese);
        byEpochDay.add(minguo);

        System.out.println("fullValueSize = " +
                byFullValue.size());
        System.out.println("epochDaySize = " +
                byEpochDay.size());
    }
}
```

```bash
javac ChronoDateComparisonDemo.java
java ChronoDateComparisonDemo
```

```text
equalsISO = false
sameDay = true
before = false
compareToZero = false
timelineZero = true
fullValueSize = 3
epochDaySize = 1
```

**Bẫy:** Nếu một ứng dụng lưu nhiều chronology trong `TreeMap<ChronoLocalDate, V>` mà dùng comparator timeLineOrder, các key khác lịch nhưng cùng epoch day được coi là **một key**. Đây là lựa chọn đúng nếu muốn gộp cùng ngày, nhưng có thể làm mất thông tin “nhãn lịch gốc” nếu nhu cầu là lưu cả hai phiên bản.

### 12.1. Tại sao không so sánh `YEAR`/`MONTH`/`DAY` trực tiếp?

Vì `2024` trong ISO khác `2024` trong Buddhist/Minguo, và lịch Hijrah có mô hình tháng khác. Nếu muốn so **ngày vật lý**, dùng `EPOCH_DAY`/`isEqual`; nếu muốn so **các nhãn theo cùng một hệ lịch**, đảm bảo cả hai đối tượng có chronology giống nhau trước khi so các trường.

## 13. Làm toán với `ChronoLocalDate`: dùng quy tắc của đúng lịch

`ChronoLocalDate.plus(amount, ChronoUnit.DAYS/MONTHS/YEARS)` thực hiện phép cộng theo chronology của object.

- Cộng một `DAYS` tiến một ngày trên timeline, nên epoch day tăng tương ứng.
- Cộng `MONTHS`/`YEARS` dùng **độ dài tháng/năm theo calendar system**, khác nhau đặc biệt với Hijrah.
- Khi muốn “cộng đúng 30 ngày thực” đừng dùng `plus(1, MONTHS)`, vì tháng ISO có 28–31 ngày, tháng Hijrah thông thường 29–30 ngày.
- Khi muốn “cùng ngày tháng năm sau” phải xác định **lịch** nào là nguồn sự thật.

Lưu `ChronologyArithmeticDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.HijrahDate;
import java.time.chrono.JapaneseDate;
import java.time.chrono.MinguoDate;
import java.time.chrono.ThaiBuddhistDate;
import java.time.temporal.ChronoUnit;

public class ChronologyArithmeticDemo {
    public static void main(String[] args) {
        LocalDate leapEve = LocalDate.of(2024, 2, 28);

        ChronoLocalDate japanese =
                JapaneseDate.from(leapEve).plus(1, ChronoUnit.DAYS);
        ChronoLocalDate minguo =
                MinguoDate.from(leapEve).plus(1, ChronoUnit.DAYS);
        ChronoLocalDate thai =
                ThaiBuddhistDate.from(leapEve)
                        .plus(1, ChronoUnit.DAYS);

        System.out.println("japaneseISO = " +
                LocalDate.from(japanese));
        System.out.println("minguoISO = " +
                LocalDate.from(minguo));
        System.out.println("thaiISO = " +
                LocalDate.from(thai));

        HijrahDate hijrah =
                HijrahDate.from(LocalDate.of(2024, 1, 1));
        long monthLength = hijrah.lengthOfMonth();
        HijrahDate firstOfMonth = hijrah.with(
                java.time.temporal.ChronoField.DAY_OF_MONTH, 1);
        ChronoLocalDate nextMonth = firstOfMonth.plus(
                1, ChronoUnit.MONTHS);

        System.out.println("hijrahMonthLengthValid = " +
                (monthLength == 29 || monthLength == 30));
        System.out.println("hijrahMonthSpanMatches = " +
                (nextMonth.toEpochDay()
                 - firstOfMonth.toEpochDay()
                 == firstOfMonth.lengthOfMonth()));
    }
}
```

```bash
javac ChronologyArithmeticDemo.java
java ChronologyArithmeticDemo
```

```text
japaneseISO = 2024-02-29
minguoISO = 2024-02-29
thaiISO = 2024-02-29
hijrahMonthLengthValid = true
hijrahMonthSpanMatches = true
```

**Lưu ý:** `HijrahDate` có thể có 29 hoặc 30 ngày trong tháng đang xét, tùy dữ liệu cấu hình. Ta kiểm tra tổng số epoch day từ đầu tháng hiện tại đến đầu tháng sau bằng `lengthOfMonth()`, chứ không hardcode 29/30 cố định cho tháng thứ sáu.

### 13.1. `ChronoPeriod` và đơn vị tháng/năm

`ChronoPeriod` biểu diễn khoảng năm/tháng/ngày gắn với một chronology. Nó **không** tương đương một `Duration` cố định theo giây. Không dùng một khoảng “1 tháng Hijrah” để tính trên ngày ISO mà không xác định cách chuyển chronology.

`Chronology.period(years,months,days)` sinh ra ChronoPeriod theo chronology cụ thể; khi cộng vào ngày, đảm bảo ngày và period dùng cùng hệ lịch. Các phép tính giữa hai ngày thuộc hai chronology khác nhau nên quy về một chronology/ISO trước để tránh assumptions sai.

## 14. Ngày theo chronology và giờ/múi giờ là hai lớp khác nhau

Ngày Hijrah/Japanese/Minguo/ThaiBuddhist không tự xác định **một instant UTC**. Một `ChronoLocalDate` chỉ có ngày; muốn thành thời điểm phải bổ sung giờ và zone.

Một mô hình phù hợp là:

```text
ChronoLocalDate (calendar-specific date)
       + LocalTime
       -> ChronoLocalDateTime (chưa có ZoneId)
       + ZoneId / ZoneOffset
       -> ChronoZonedDateTime
       -> Instant (timeline)
```

`ChronoZonedDateTime` dùng quy tắc `ZoneId`; vấn đề DST gap/overlap vẫn có thể xảy ra khi chọn local time, bất kể chronology. Đừng nhầm quy tắc âm lịch hoặc era với thay đổi UTC offset.

Lưu `ChronoZonedTimeDemo.java`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.chrono.ChronoLocalDateTime;
import java.time.chrono.ChronoZonedDateTime;
import java.time.chrono.JapaneseDate;

public class ChronoZonedTimeDemo {
    public static void main(String[] args) {
        JapaneseDate date =
                JapaneseDate.from(LocalDate.of(2024, 1, 1));
        ChronoLocalDateTime<?> localDateTime =
                date.atTime(LocalTime.NOON);
        ChronoZonedDateTime<?> inTokyo =
                localDateTime.atZone(ZoneId.of("Asia/Tokyo"));
        Instant instant = inTokyo.toInstant();

        System.out.println("calendar = " +
                inTokyo.getChronology().getId());
        System.out.println("zone = " + inTokyo.getZone());
        System.out.println("instant = " + instant);
        System.out.println("isoDate = " +
                LocalDate.from(inTokyo));
        System.out.println("roundTripEpochDay = " +
                (LocalDate.from(date).toEpochDay()
                 == LocalDate.from(inTokyo).toEpochDay()));
    }
}
```

```bash
javac ChronoZonedTimeDemo.java
java ChronoZonedTimeDemo
```

```text
calendar = Japanese
zone = Asia/Tokyo
instant = 2024-01-01T03:00:00Z
isoDate = 2024-01-01
roundTripEpochDay = true
```

Ngày `2024-01-01` lúc **12:00 ở Tokyo** có UTC offset `+09:00` tại ngày đó, vì vậy instant là `03:00Z`. Việc dùng JapaneseDate **không** tự mang zone Nhật; `ZoneId.of("Asia/Tokyo")` được cung cấp riêng. Nếu một sự kiện có cùng ngày âm/lịch Nhật nhưng diễn ra tại các vùng khác nhau, instant có thể khác vì giờ và zone khác.

## 15. Format/parse theo chronology: `DateTimeFormatter.withChronology`

`DateTimeFormatter` có phương thức `withChronology(Chronology)` để **ghi đè chronology dùng khi format/parse** theo hợp đồng formatter. `withLocale(Locale)` chọn ngôn ngữ cho tên era/tháng, không tự bảo đảm calendar system đổi theo ý bạn.

Ví dụ lịch Nhật cần **tên era + năm trong era**. Pattern `G y-MM-dd` dùng ký hiệu era `G` và year-of-era `y`. Với `ResolverStyle.STRICT`, việc cung cấp era rõ ràng là rất quan trọng: năm trong era mà không có era có thể không đủ để resolve ngày một cách chính xác.

Lưu `ChronologyFormatterDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.JapaneseChronology;
import java.time.chrono.JapaneseDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ChronologyFormatterDemo {
    public static void main(String[] args) {
        JapaneseDate source =
                JapaneseDate.from(LocalDate.of(2019, 5, 1));

        DateTimeFormatter formatter = DateTimeFormatter
                .ofPattern("G y-MM-dd", Locale.JAPAN)
                .withChronology(JapaneseChronology.INSTANCE)
                .withResolverStyle(ResolverStyle.STRICT);

        String text = formatter.format(source);
        JapaneseDate restored =
                JapaneseDate.from(formatter.parse(text));

        System.out.println("sourceEra = " +
                source.getEra());
        System.out.println("hasEraText = " +
                !text.isBlank());
        System.out.println("roundTrip = " +
                restored.equals(source));
        System.out.println("isoAfter = " +
                LocalDate.from(restored));
        System.out.println("formatterChronology = " +
                formatter.getChronology().getId());
    }
}
```

```bash
javac ChronologyFormatterDemo.java
java ChronologyFormatterDemo
```

```text
sourceEra = Reiwa
hasEraText = true
roundTrip = true
isoAfter = 2019-05-01
formatterChronology = Japanese
```

**Vì sao không cố định chữ Nhật `令和` trong stdout?** Tên era và cách diễn đạt có thể phụ thuộc Locale, provider dữ liệu địa phương hóa và phiên bản Java. Đoạn test kiểm tra **round-trip chính xác** và ngày ISO sau khi parse, trong khi giao diện sản phẩm vẫn có thể hiển thị chuỗi đã format.

### 15.1. Locale không tự nói hết nghiệp vụ

- `G` yêu cầu tên era có cách hiển thị hợp ngôn ngữ; `Locale.JAPAN` giúp tên era tiếng Nhật.
- `y` là YEAR_OF_ERA; `u` là proleptic year; không tráo hai trường.
- `DateTimeFormatter.withChronology` có thể ảnh hưởng cả format và parse; hãy xác định kết quả cần là `JapaneseDate` hay `LocalDate`.
- `LocalDate.parse(text, japaneseFormatter)` nếu thành công sẽ convert các trường được resolve sang ngày ISO; nếu ý định giữ thông tin lịch Nhật và era, dùng `JapaneseDate.from(formatter.parse(text))`/`Chronology.date(...)`.
- Cần test với ngày đầu/cuối era, năm nhuận và input không hợp lệ của chronology.

**Không coi `DateTimeFormatter.ISO_LOCAL_DATE` là formatter cho mọi calendar.** Một giá trị cần trình bày theo lịch Thái/Hijrah phải có chronology và format riêng; việc sử dụng ISO formatter là tốt khi muốn truyền **ngày ISO chuẩn**.

## 16. Chuyển đổi dữ liệu để lưu trữ và giao tiếp

Giả sử giao diện cho người dùng chọn lịch Thái:

1. User nhập **2567-01-01** trong Phật lịch Thái, xác định rõ chronology và era.
2. Ứng dụng resolve thành `ThaiBuddhistDate.of(2567,1,1)`.
3. Chuyển về ISO `LocalDate.from(thaiDate)` để lưu ngày vật lý **2024-01-01**.
4. Khi trả về giao diện, convert ISO date sang chronology đã chọn để hiển thị.
5. Nếu cần giữ thông tin *người dùng đã chọn lịch gì*, lưu thêm ID chronology (và biến thể/metadata cần thiết) trong setting hoặc metadata nghiệp vụ.

Tương tự, với lịch Hijrah, phải biết **biến thể** đã dùng để nhập/chuyển. Chỉ gửi trường `year=1445,month=6,day=19` mà không ghi chronology ID có thể dẫn tới giải thích sai. Nếu data nằm ngoài phạm vi được JDK hỗ trợ, phải có chính sách báo lỗi/chọn nguồn lịch phù hợp, không âm thầm sử dụng ISO hoặc hệ lịch khác.

Lưu `CalendarPersistenceDemo.java`:

```java
import java.time.LocalDate;
import java.time.chrono.Chronology;
import java.time.chrono.MinguoDate;
import java.time.chrono.ThaiBuddhistDate;

public class CalendarPersistenceDemo {
    public static void main(String[] args) {
        ThaiBuddhistDate entered =
                ThaiBuddhistDate.of(2567, 1, 1);

        LocalDate storedISO = LocalDate.from(entered);
        String calendarId = entered.getChronology().getId();

        Chronology requested = Chronology.of(calendarId);
        ThaiBuddhistDate shownAgain =
                ThaiBuddhistDate.from(
                        requested.date(storedISO));

        MinguoDate sameDayOtherCalendar =
                MinguoDate.from(storedISO);

        System.out.println("storedISO = " + storedISO);
        System.out.println("calendarId = " + calendarId);
        System.out.println("displayYear = " +
                shownAgain.get(
                        java.time.temporal.ChronoField.YEAR_OF_ERA));
        System.out.println("sameDayMinguo = " +
                shownAgain.isEqual(sameDayOtherCalendar));
        System.out.println("roundTrip = " +
                entered.equals(shownAgain));
    }
}
```

```bash
javac CalendarPersistenceDemo.java
java CalendarPersistenceDemo
```

```text
storedISO = 2024-01-01
calendarId = ThaiBuddhist
displayYear = 2567
sameDayMinguo = true
roundTrip = true
```

Đây là **mẫu khái niệm cho date-only data**. Khi lưu timestamp một sự kiện thực, cần lưu `Instant` hoặc biểu diễn UTC có đầy đủ zone/offset; `LocalDate` không tự chỉ ra một instant. Nếu lưu lịch lặp lại (“mỗi tháng âm ngày 1”), phải giữ **quy tắc lịch** và zone, không chỉ chụp một ngày ISO của lần đầu.

### 16.1. Tránh mất dữ liệu era hoặc chronology khi xuất JSON

Có ít nhất ba thứ cần phân biệt:

- **Ngày timeline**: ví dụ `"2024-01-01"` theo ISO.
- **Nhãn lịch**: `"ThaiBuddhist"`, `"Japanese"`, `"Hijrah-umalqura"`.
- **Năm/era gốc**: ví dụ `"Reiwa 6"` hoặc `"ROC 113"` nếu cần hiển thị chính xác ý định ban đầu.

Khi API chỉ truyền `"year":113` mà không có chronology, phía nhận không thể biết đó là Minguo hay ISO. Khi chỉ lưu ISO date mà không lưu setting lịch của user, vẫn có thể tái dựng ngày theo lịch đích, nhưng không thể biết lịch nào user đã chọn trong giao diện nếu không có thông tin khác.

**Lịch Hijrah cần chú ý thêm:** để tái hiện chính xác một nhãn ngày âm theo lịch đã tính tại thời điểm giao dịch, có thể phải lưu variant và version của dữ liệu, vì cách ánh xạ có thể thay đổi khi nâng cấp dữ liệu nhà cung cấp.

## 17. Xử lý lỗi và giới hạn phạm vi

### 17.1. Ngày Nhật quá xa trong quá khứ

Oracle Java chỉ hỗ trợ Japanese chronology kể từ Meiji 6/1873 theo mô hình lịch Gregorian hiện hành. Đừng tự giả định dữ liệu cũ ở một era bất kỳ đều có thể tạo bằng `JapaneseDate.from(...)`.

### 17.2. Calendar ID không tồn tại

`Chronology.of("UnknownCalendar")` không âm thầm trở về ISO; nó có thể ném `DateTimeException`. Tương tự, `Chronology.ofLocale(locale)` với calendar extension không được hỗ trợ có thể lỗi. Cần validate giá trị chọn từ API/UI, và trình bày danh sách lịch được hỗ trợ thay vì tự đoán.

### 17.3. Ngày Hijrah nằm ngoài phạm vi

Một `HijrahDate` có thể thất bại do tháng/năm ngoài bảng dữ liệu của biến thể. Không tự diễn giải lỗi này thành “ngày không tồn tại ở mọi lịch Hồi giáo”; đúng hơn là **JDK/variant hiện dùng không thể tạo nó**.

### 17.4. Đừng trộn chronology trong cùng phép toán

Một `ChronoPeriod` Minguo không tự trở thành `ChronoPeriod` ThaiBuddhist. Khi làm phép cộng/trừ trên ngày khác chronology, sẽ có bước kiểm tra tương thích. Chọn một chronology làm nguồn tính toán hoặc chuẩn hóa về ISO ngày trước.

Lưu `ChronologyValidationDemo.java`:

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.chrono.Chronology;
import java.time.chrono.JapaneseDate;

public class ChronologyValidationDemo {
    public static void main(String[] args) {
        try {
            JapaneseDate.from(LocalDate.of(1872, 12, 31));
            System.out.println("unexpected historical success");
        } catch (DateTimeException ex) {
            System.out.println("japanese historical date rejected");
        }

        try {
            Chronology.of("UnknownCalendar");
            System.out.println("unexpected chronology success");
        } catch (DateTimeException ex) {
            System.out.println("unknown chronology rejected");
        }

        System.out.println("japaneseModern = " +
                LocalDate.from(
                        JapaneseDate.from(
                                LocalDate.of(2024, 1, 1))));
    }
}
```

```bash
javac ChronologyValidationDemo.java
java ChronologyValidationDemo
```

```text
japanese historical date rejected
unknown chronology rejected
japaneseModern = 2024-01-01
```

**Nguyên tắc xử lý exception:** phân biệt “đầu vào calendar ID không hỗ trợ”, “ngày ngoài phạm vi”, “ngày không hợp lệ trong era” và “sai format”. Không nên bắt mọi `DateTimeException` rồi thay bằng ngày hôm nay, vì có thể gây lỗi nghiệp vụ khó phát hiện.

## 18. Chọn cách biểu diễn theo yêu cầu sản phẩm

| Yêu cầu | Kiểu nên ưu tiên | Ghi chú |
| --- | --- | --- |
| Ngày sinh, ngày xuất hóa đơn chỉ cần một ngày | `LocalDate` ISO | Nếu UI dùng lịch khác, convert lúc nhập/xuất |
| Một sự kiện đã xảy ra tại thời điểm cụ thể | `Instant` | Calendar không thay thế timestamp |
| Ngày theo niên hiệu Nhật | `JapaneseDate` và `JapaneseEra` | Era start/end phải hợp lệ |
| Số năm Dân Quốc | `MinguoDate` | 2024 ISO = ROC 113 |
| Ngày Phật lịch Thái | `ThaiBuddhistDate` | ISO year +543 theo API |
| Ngày Hijrah Umm al-Qura | `HijrahDate` | Dữ liệu theo variant, cần xét phạm vi |
| UI tự chọn nhiều loại lịch | `Chronology` + `ChronoLocalDate` | Chỉ mở rộng generic khi thật sự cần |
| Ghi vào DB/nói chuyện giữa services | `LocalDate`/`Instant` ISO | Ghi thêm metadata chronology nếu cần |
| Lịch hàng tháng theo calendar không ISO | Lưu chronology ID + quy tắc + zone | Không giả định mỗi tháng là 30 ngày |
| So “cùng một ngày” qua nhiều lịch | `toEpochDay()`, `isEqual()` | Không so số YEAR/MONTH trực tiếp |
| So “hai object lịch có cùng cấu trúc/nhãn” | `equals()` | Xét cả chronology |
| In tên era bằng locale | `DateTimeFormatter.withChronology` | Kiểm chứng locale và formatter |

Một tiêu chí thiết kế quan trọng: **nhu cầu hiển thị** khác **nhu cầu tính toán**. Có thể hỗ trợ lịch Nhật/Thái/Hijrah ở giao diện mà vẫn dùng `LocalDate` ISO làm dữ liệu nền. Chỉ khi nghiệp vụ thật sự tính lịch theo tháng/ngày/era khác ISO mới nên giữ chronology ở domain logic.

## 19. Bài tập thực hành có lời giải

**Bài 1.** Lấy `LocalDate.of(2024,1,1)`. Convert sang `JapaneseDate`, `MinguoDate` và `ThaiBuddhistDate`. In `YEAR_OF_ERA` và xác nhận cả ba có cùng `toEpochDay()`.

**Bài 2.** Với `JapaneseDate` 30/04/2019 và 01/05/2019, giải thích vì sao `YEAR_OF_ERA` chuyển từ 31 sang 1 nhưng ngày thực vẫn tăng liên tiếp một ngày. Có hợp lệ nếu tạo Reiwa 1 vào 30/04/2019 không?

**Bài 3.** Tạo ngày Hijrah tương ứng ISO `2024-01-01`, kiểm tra `lengthOfMonth()` là 29 hoặc 30, convert trở lại ISO. Vì sao không nên hardcode “mọi tháng Hijrah luôn 30 ngày”?

**Bài 4.** Dùng `Chronology.ofLocale(Locale.forLanguageTag("th-TH-u-ca-buddhist"))` và so với `ThaiBuddhistChronology.INSTANCE`.

**Bài 5.** Đưa một `JapaneseDate` và một `MinguoDate` cùng epoch day vào `TreeSet` mặc định, sau đó vào `TreeSet` dùng `ChronoLocalDate.timeLineOrder()`. Giải thích vì sao kích thước tập có thể khác nhau.

**Bài 6.** Chọn thiết kế lưu trữ cho app lịch lặp lại “ngày 1 tháng Hijrah” và một event đã xảy ra. Nêu khi nào cần lưu variant, zone hoặc Instant thay vì chỉ LocalDate.

### 19.1. Lời giải Java

Lưu `ChronologyPractice.java`:

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.Chronology;
import java.time.chrono.HijrahDate;
import java.time.chrono.JapaneseDate;
import java.time.chrono.MinguoDate;
import java.time.chrono.ThaiBuddhistDate;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class ChronologyPractice {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2024, 1, 1);
        JapaneseDate japanese = JapaneseDate.from(iso);
        MinguoDate minguo = MinguoDate.from(iso);
        ThaiBuddhistDate thai = ThaiBuddhistDate.from(iso);
        HijrahDate hijrah = HijrahDate.from(iso);

        System.out.println("japaneseYearOfEra = " +
                japanese.get(ChronoField.YEAR_OF_ERA));
        System.out.println("minguoYearOfEra = " +
                minguo.get(ChronoField.YEAR_OF_ERA));
        System.out.println("thaiYearOfEra = " +
                thai.get(ChronoField.YEAR_OF_ERA));

        System.out.println("sameDay = " +
                japanese.isEqual(minguo) + ", " +
                thai.isEqual(hijrah));
        System.out.println("hijrahISO = " +
                LocalDate.from(hijrah));

        Chronology selected = Chronology.ofLocale(
                Locale.forLanguageTag(
                        "th-TH-u-ca-buddhist"));
        ChronoLocalDate byLocale = selected.date(iso);
        System.out.println("selectedCalendar = " +
                selected.getId());
        System.out.println("backToISO = " +
                LocalDate.from(byLocale));
    }
}
```

```bash
javac ChronologyPractice.java
java ChronologyPractice
```

```text
japaneseYearOfEra = 6
minguoYearOfEra = 113
thaiYearOfEra = 2567
sameDay = true, true
hijrahISO = 2024-01-01
selectedCalendar = ThaiBuddhist
backToISO = 2024-01-01
```

Gợi ý bài 5: `TreeSet` mặc định so `ChronoLocalDate.compareTo()` có tie-break theo chronology, nên có thể giữ hai đối tượng cùng epoch day. `timeLineOrder()` bỏ tie-break, nên gộp chúng thành một ngày. Bài 6 cần tách **ngày event đã xảy ra** (Instant/timeline) khỏi **quy tắc lịch lặp lại** (chronology variant, local day/month, zone và policy).

## 20. Checklist kiểm tra code

- Tôi đang làm việc với **ISO LocalDate** hay một `ChronoLocalDate` lịch khác? Có suy luận sai từ tên trường `YEAR` không?
- Có dùng **epoch day** hoặc `isEqual()` khi so ngày khác chronology không?
- Có phân biệt `YEAR_OF_ERA` và `YEAR`, lưu `ERA` khi cần không?
- Với lịch Nhật, có kiểm tra ngày bắt đầu era và giới hạn lịch sử của API không?
- Với Minguo, đã áp dụng năm ROC đúng theo API, không nhầm `1912 = ROC 1` với `1911 = ROC 1`?
- Với Thái, đã dùng chronology thay vì tự cộng `+543` ở nhiều nơi rồi làm rơi era/ngày ISO?
- Với Hijrah, đã xác định rõ biến thể Umm al-Qura hoặc lịch được tổ chức công nhận, phạm vi và version dữ liệu?
- Có giả định tháng Hijrah cũng 28–31 ngày như ISO không? Nếu có, phải sửa.
- Formatter có được cấu hình `withChronology`, `Locale` và era phù hợp không?
- `Chronology.ofLocale` có thật sự nhận extension `u-ca` mong muốn không?
- Với JSON/DB, đã thống nhất ngày **ISO** và giữ calendar ID/variant metadata khi cần chưa?
- Khi ghép giờ và zone, có kiểm tra DST gap/overlap riêng không?
- Khi dùng `ChronoPeriod`, ngày và period có cùng calendar không?
- Có dùng `TreeSet`/`TreeMap` comparator timeLineOrder làm mất biểu diễn khác chronology ngoài ý muốn?
- Các sample/test có output ổn định, không hardcode những ngày Hijrah mà JDK data có thể thay đổi không?
- Có tránh các lớp ngày giờ legacy và dùng API `java.time` hiện hành không?

## 21. Nguồn tài liệu chính thức

- Oracle Java SE 26 — `Chronology`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/Chronology.html
- Oracle Java SE 26 — `ChronoLocalDate`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/ChronoLocalDate.html
- Oracle Java SE 26 — `IsoChronology`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/IsoChronology.html
- Oracle Java SE 26 — `JapaneseChronology` và `JapaneseDate`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/JapaneseChronology.html
- Oracle Java SE 26 — `JapaneseEra`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/JapaneseEra.html
- Oracle Java SE 26 — `HijrahChronology`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/HijrahChronology.html
- Oracle Java SE 26 — `MinguoChronology`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/MinguoChronology.html
- Oracle Java SE 26 — `ThaiBuddhistChronology`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/ThaiBuddhistChronology.html
- Oracle Java SE 26 — `ChronoZonedDateTime`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/chrono/ChronoZonedDateTime.html
- Oracle Java SE 26 — `DateTimeFormatter`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Oracle Java SE 26 — `java.time` package: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/package-summary.html

**Kết luận:** `Chronology` không tạo một timeline thứ hai; nó đưa ra **quy tắc đặt tên và chia các ngày**. ISO, Nhật, Hijrah, Minguo và Thái có thể biểu diễn cùng một `EPOCH_DAY` dù năm/era/tháng khác nhau. Ưu tiên `LocalDate`/`Instant` ISO ở ranh giới lưu trữ và mạng; dùng chronology cụ thể ở nơi có yêu cầu rõ về lịch, kèm era, variant và dữ liệu cần thiết. Khi so ngày khác lịch, hỏi “**cùng ngày vật lý hay cùng biểu diễn?**” trước khi chọn `isEqual` hoặc `equals`.