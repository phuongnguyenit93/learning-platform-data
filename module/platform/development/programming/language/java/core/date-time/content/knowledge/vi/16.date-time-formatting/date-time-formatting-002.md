# Sử dụng các bộ định dạng ISO có sẵn trong Java

Java cung cấp các hằng dựng sẵn của **DateTimeFormatter** để biểu diễn và phân tích ngày giờ theo định dạng ISO-8601. Thay vì tự viết pattern cho những định dạng thông dụng, ta có thể dùng **ISO_LOCAL_DATE**, **ISO_LOCAL_TIME**, **ISO_LOCAL_DATE_TIME**, **ISO_OFFSET_DATE_TIME**, **ISO_ZONED_DATE_TIME**, **ISO_INSTANT** và các formatter ISO liên quan.

Điểm quan trọng là chọn formatter khớp với **kiểu dữ liệu và ngữ nghĩa thời gian**. Chuỗi **2026-10-24T09:30** không chứa offset; **2026-10-24T09:30+07:00** chứa offset; còn **2026-10-24T02:30:00Z** biểu diễn một thời điểm UTC. Các chuỗi trông giống nhau không có nghĩa là thay thế được cho nhau.

Bài học sử dụng Java 17+, giải thích các bộ formatter ISO dựng sẵn, cách format và parse, sự khác biệt giữa local/offset/zone/instant, ISO tuần và thứ tự ngày trong năm, độ chính xác và những lỗi thường gặp khi tích hợp API.

## 1. ISO-8601 và DateTimeFormatter

ISO-8601 là một tiêu chuẩn quốc tế cho biểu diễn ngày giờ. Trong Java, lớp **java.time.format.DateTimeFormatter** cung cấp những formatter có sẵn cho nhiều dạng ISO. Formatter có thể dùng để:

- **format(temporal):** chuyển giá trị ngày giờ thành chuỗi.
- **parse(text):** phân tích chuỗi theo quy tắc formatter, thường thông qua phương thức parse của kiểu đích.
- Tái sử dụng cùng một formatter vì DateTimeFormatter là bất biến và an toàn khi dùng đồng thời trên nhiều luồng.

Ví dụ:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

LocalDate date = LocalDate.of(2026, 10, 24);
String text = DateTimeFormatter.ISO_LOCAL_DATE.format(date);
LocalDate parsed =
        LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE);
~~~

Kết quả văn bản là:

~~~text
2026-10-24
~~~

Đây là đoạn minh họa cần đặt trong một phương thức hoặc chương trình Java. Khi parse chuỗi ISO thành LocalDate, Java kiểm tra cả cú pháp lẫn tính hợp lệ của ngày. Chẳng hạn 30/02 không biến thành ngày hợp lệ chỉ vì có đúng hình thức chuỗi.

ISO không phải một pattern duy nhất. Các hằng dựng sẵn có hợp đồng khác nhau, và một số formatter chấp nhận thành phần tùy chọn. Nếu API yêu cầu phạm vi đầu vào hẹp hơn dạng ISO tiêu chuẩn, hãy định nghĩa rõ hợp đồng và kiểm thử các đầu vào ngoài phạm vi.

## 2. Các formatter ISO thường dùng

| Hằng DateTimeFormatter | Dữ liệu chính | Ví dụ |
|---|---|---|
| **ISO_LOCAL_DATE** | Ngày không offset | 2026-10-24 |
| **BASIC_ISO_DATE** | Ngày dạng cơ bản | 20261024 |
| **ISO_LOCAL_TIME** | Giờ không offset | 09:30:15.123 |
| **ISO_OFFSET_TIME** | Giờ có offset | 09:30:15.123+07:00 |
| **ISO_LOCAL_DATE_TIME** | Ngày giờ không offset | 2026-10-24T09:30:15.123 |
| **ISO_OFFSET_DATE_TIME** | Ngày giờ có offset | 2026-10-24T09:30:15.123+07:00 |
| **ISO_ZONED_DATE_TIME** | Ngày giờ có offset và vùng khi có | 2026-10-24T09:30:15.123+02:00[Europe/Paris] |
| **ISO_DATE** | Ngày, có thể kèm offset | 2026-10-24+07:00 |
| **ISO_TIME** | Giờ, có thể kèm offset | 09:30:15.123+07:00 |
| **ISO_DATE_TIME** | Ngày giờ có thể có offset/zone | 2026-10-24T09:30:15.123+02:00[Europe/Paris] |
| **ISO_INSTANT** | Instant theo UTC | 2026-10-24T02:30:15.123Z |
| **ISO_ORDINAL_DATE** | Năm và thứ tự ngày trong năm | 2026-297 |
| **ISO_WEEK_DATE** | Năm tuần ISO, tuần và thứ | 2026-W43-6 |

Đây là ví dụ định dạng tương ứng; một formatter có thể chấp nhận thêm các dạng hợp lệ trong phạm vi quy tắc của nó. **ISO_DATE**, **ISO_TIME** và **ISO_DATE_TIME** linh hoạt hơn nhóm LOCAL vì chúng có thể giữ offset hoặc vùng từ dữ liệu nguồn.

## 3. LOCAL, OFFSET, ZONED và INSTANT khác nhau thế nào?

Chọn formatter theo kiểu thời gian:

- **LocalDate, LocalTime, LocalDateTime:** không có offset hoặc ZoneId; dùng các hằng **ISO_LOCAL_***.
- **OffsetTime, OffsetDateTime:** có độ lệch UTC cụ thể như +07:00; dùng **ISO_OFFSET_TIME** hoặc **ISO_OFFSET_DATE_TIME**.
- **ZonedDateTime:** có ZoneId như Europe/Paris kèm offset có hiệu lực theo quy tắc vùng; dùng **ISO_ZONED_DATE_TIME** hoặc **ISO_DATE_TIME** khi phù hợp.
- **Instant:** điểm tuyệt đối trên trục thời gian; dùng **ISO_INSTANT**, thường xuất ra UTC với hậu tố Z.

Ví dụ:

~~~text
2026-10-24T09:30:15.123
2026-10-24T09:30:15.123+07:00
2026-10-24T09:30:15.123+02:00[Europe/Paris]
2026-10-24T02:30:15.123Z
~~~

Chuỗi đầu tiên chưa đủ thông tin để suy ra thời điểm UTC. Chuỗi thứ hai xác định được Instant từ offset nhưng không nhận diện vùng địa lý. Chuỗi thứ ba thể hiện tên vùng. Chuỗi thứ tư là Instant ở UTC.

**Không thể suy ra ZoneId chỉ từ offset.** Nhiều vùng có cùng offset tại một thời điểm và một vùng có thể đổi offset theo lịch sử hoặc DST.

## 4. Chương trình Java 17+ cho các formatter ISO

Tạo tệp **IsoFormattersDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;

public class IsoFormattersDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 10, 24);
        LocalTime time = LocalTime.of(9, 30, 15, 123_000_000);
        LocalDateTime local = LocalDateTime.of(date, time);
        OffsetTime offsetTime =
                OffsetTime.of(time, ZoneOffset.ofHours(7));
        OffsetDateTime offset = OffsetDateTime.of(local,
                ZoneOffset.ofHours(7));
        ZonedDateTime zoned =
                local.atZone(ZoneId.of("Europe/Paris"));
        Instant instant =
                Instant.parse("2026-10-24T02:30:15.123Z");

        System.out.println("localDate=" +
                DateTimeFormatter.ISO_LOCAL_DATE.format(date));
        System.out.println("basic=" +
                DateTimeFormatter.BASIC_ISO_DATE.format(date));
        System.out.println("localTime=" +
                DateTimeFormatter.ISO_LOCAL_TIME.format(time));
        System.out.println("localDateTime=" +
                DateTimeFormatter.ISO_LOCAL_DATE_TIME.format(local));
        System.out.println("offsetTime=" +
                DateTimeFormatter.ISO_OFFSET_TIME.format(offsetTime));
        System.out.println("offsetDateTime=" +
                DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(offset));
        System.out.println("zoned=" +
                DateTimeFormatter.ISO_ZONED_DATE_TIME.format(zoned));
        System.out.println("instant=" +
                DateTimeFormatter.ISO_INSTANT.format(instant));
        System.out.println("date=" +
                DateTimeFormatter.ISO_DATE.format(
                        offset.toLocalDate().atStartOfDay()
                                .atZone(ZoneOffset.ofHours(7))));
        System.out.println("time=" +
                DateTimeFormatter.ISO_TIME.format(offsetTime));
        System.out.println("dateTime=" +
                DateTimeFormatter.ISO_DATE_TIME.format(zoned));
        System.out.println("week=" +
                DateTimeFormatter.ISO_WEEK_DATE.format(date));
        System.out.println("ordinal=" +
                DateTimeFormatter.ISO_ORDINAL_DATE.format(date));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac IsoFormattersDemo.java
java IsoFormattersDemo
~~~

Stdout với Java 17+ và dữ liệu múi giờ tương ứng:

~~~text
localDate=2026-10-24
basic=20261024
localTime=09:30:15.123
localDateTime=2026-10-24T09:30:15.123
offsetTime=09:30:15.123+07:00
offsetDateTime=2026-10-24T09:30:15.123+07:00
zoned=2026-10-24T09:30:15.123+02:00[Europe/Paris]
instant=2026-10-24T02:30:15.123Z
date=2026-10-24+07:00
time=09:30:15.123+07:00
dateTime=2026-10-24T09:30:15.123+02:00[Europe/Paris]
week=2026-W43-6
ordinal=2026-297
~~~

Ngày 24/10/2026 là ngày thứ 297 của năm và là thứ Bảy. Với quy tắc vùng Paris áp dụng cho ngày đó, ví dụ hiển thị offset +02:00 và phần [Europe/Paris]. Nếu quy tắc vùng thay đổi trong dữ liệu timezone mới, đầu ra có offset có thể thay đổi theo dữ liệu JDK.

## 5. Parse bằng formatter dựng sẵn

Dùng phương thức parse của kiểu đích:

~~~java
LocalDate date = LocalDate.parse(
        "2026-10-24", DateTimeFormatter.ISO_LOCAL_DATE);

LocalDateTime local = LocalDateTime.parse(
        "2026-10-24T09:30:15.123",
        DateTimeFormatter.ISO_LOCAL_DATE_TIME);

OffsetDateTime offset = OffsetDateTime.parse(
        "2026-10-24T09:30:15.123+07:00",
        DateTimeFormatter.ISO_OFFSET_DATE_TIME);

Instant instant = Instant.parse("2026-10-24T02:30:15.123Z");
~~~

**LocalDate.parse** tạo ngày. **OffsetDateTime.parse** đọc ngày giờ kèm offset. **Instant.parse** phân tích biểu diễn Instant, không đoán múi giờ cho một LocalDateTime thiếu offset.

Nếu đưa chuỗi chỉ có ngày giờ local cho OffsetDateTime.parse hoặc Instant.parse, parser sẽ thất bại vì thiếu thông tin bắt buộc. Không nên tự nối chữ Z vào chuỗi để giả vờ chuyển nó sang UTC.

### Ví dụ round-trip

Tạo tệp **IsoParseRoundTripDemo.java**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;

public class IsoParseRoundTripDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.parse(
                "2026-10-24", DateTimeFormatter.ISO_LOCAL_DATE);
        LocalDateTime local = LocalDateTime.parse(
                "2026-10-24T09:30:15.123",
                DateTimeFormatter.ISO_LOCAL_DATE_TIME);
        OffsetDateTime offset = OffsetDateTime.parse(
                "2026-10-24T09:30:15.123+07:00",
                DateTimeFormatter.ISO_OFFSET_DATE_TIME);
        Instant instant = Instant.parse(
                "2026-10-24T02:30:15.123Z");

        System.out.println("date=" +
                DateTimeFormatter.ISO_LOCAL_DATE.format(date));
        System.out.println("local=" +
                DateTimeFormatter.ISO_LOCAL_DATE_TIME.format(local));
        System.out.println("offset=" +
                DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(offset));
        System.out.println("instant=" +
                DateTimeFormatter.ISO_INSTANT.format(instant));
        System.out.println("sameInstant=" +
                offset.toInstant().equals(instant));
    }
}
~~~

Chạy:

~~~bash
javac IsoParseRoundTripDemo.java
java IsoParseRoundTripDemo
~~~

Stdout:

~~~text
date=2026-10-24
local=2026-10-24T09:30:15.123
offset=2026-10-24T09:30:15.123+07:00
instant=2026-10-24T02:30:15.123Z
sameInstant=true
~~~

Round-trip giữ nguyên ý nghĩa nếu kiểu dữ liệu đúng. Khi OffsetDateTime được chuyển thành Instant rồi format bằng ISO_INSTANT, chuỗi sẽ chuẩn hóa sang UTC. Chuỗi khác ký tự nhưng vẫn có thể mô tả cùng một điểm thời gian.

## 6. BASIC_ISO_DATE so với ISO_LOCAL_DATE

Hai formatter tạo cách hiển thị khác nhau:

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);

System.out.println(
        DateTimeFormatter.ISO_LOCAL_DATE.format(date));
System.out.println(
        DateTimeFormatter.BASIC_ISO_DATE.format(date));
~~~

Stdout:

~~~text
2026-10-24
20261024
~~~

ISO_LOCAL_DATE có dấu phân cách, thường dễ đọc trong JSON và API hiện đại. BASIC_ISO_DATE biểu diễn ngày dạng cơ bản, phù hợp khi hợp đồng hoặc hệ thống cũ yêu cầu dạng yyyyMMdd. Không tự loại bỏ dấu gạch bằng xử lý chuỗi nếu formatter đã có sẵn cho dạng cần dùng.

BASIC_ISO_DATE có thể thể hiện thêm offset khi temporal đầu vào và định dạng cho phép. Nếu giao thức yêu cầu chính xác tám chữ số không offset, hãy quy định và kiểm thử rõ phạm vi đó.

## 7. ISO_DATE, ISO_TIME và ISO_DATE_TIME linh hoạt hơn

Các formatter này có thể giữ offset hoặc phần vùng từ giá trị đầu vào.

~~~java
OffsetDateTime odt = OffsetDateTime.of(
        2026, 10, 24, 9, 30, 0, 0, ZoneOffset.ofHours(7));

System.out.println(DateTimeFormatter.ISO_DATE.format(odt));
System.out.println(DateTimeFormatter.ISO_TIME.format(
        odt.toOffsetTime()));
System.out.println(DateTimeFormatter.ISO_DATE_TIME.format(odt));
~~~

Stdout:

~~~text
2026-10-24+07:00
09:30:00+07:00
2026-10-24T09:30:00+07:00
~~~

ISO_LOCAL_DATE_TIME không thể hiện offset. ISO_DATE_TIME là formatter linh hoạt, nhưng đừng dùng sự linh hoạt này một cách vô tình nếu hợp đồng yêu cầu mọi timestamp phải có offset. Hãy dùng kiểu đích và formatter đúng với thông tin cần giữ.

## 8. ISO_WEEK_DATE và ISO_ORDINAL_DATE

**ISO_WEEK_DATE** biểu diễn năm tuần ISO, tuần và ngày trong tuần; ví dụ **2026-W43-6**. Năm tuần ISO có thể khác năm lịch ở gần đầu hoặc cuối năm. Không sử dụng năm tuần ISO như năm lịch thông thường mà không hiểu quy tắc tuần.

**ISO_ORDINAL_DATE** biểu diễn năm và thứ tự ngày trong năm; ví dụ **2026-297** nghĩa là ngày thứ 297 tính từ đầu năm. Con số cuối không phải ngày trong tháng.

~~~java
LocalDate date = LocalDate.of(2026, 10, 24);
String week = DateTimeFormatter.ISO_WEEK_DATE.format(date);
String ordinal = DateTimeFormatter.ISO_ORDINAL_DATE.format(date);

LocalDate fromWeek =
        LocalDate.parse(week, DateTimeFormatter.ISO_WEEK_DATE);
LocalDate fromOrdinal =
        LocalDate.parse(ordinal, DateTimeFormatter.ISO_ORDINAL_DATE);
~~~

Với ngày hợp lệ này, cả hai dạng parse trở về cùng một LocalDate. Chúng hữu ích trong lịch sản xuất, báo cáo tuần, logistics hoặc hệ thống trao đổi dữ liệu chuyên biệt.

## 9. ISO_INSTANT và chuẩn hóa UTC

ISO_INSTANT dùng cho kiểu **Instant** và thường xuất UTC với hậu tố Z:

~~~java
Instant value = Instant.parse("2026-10-24T02:30:15.123Z");
String encoded = DateTimeFormatter.ISO_INSTANT.format(value);
~~~

Kết quả:

~~~text
2026-10-24T02:30:15.123Z
~~~

Khi chuyển OffsetDateTime có +07:00 thành Instant rồi format bằng ISO_INSTANT, chuỗi được chuẩn hóa về UTC:

~~~text
2026-10-24T09:30:15.123+07:00
          ↓ toInstant()
2026-10-24T02:30:15.123Z
~~~

Đó là cùng một thời điểm tuyệt đối. Không thể làm thao tác tương đương bằng cách nối chữ Z vào LocalDateTime, vì LocalDateTime chưa có thông tin offset.

## 10. Phần giây và độ chính xác

ISO formatter có thể biểu diễn phần giây thập phân khi giá trị có độ chính xác đó. Phần phân số thường không xuất hiện nếu giá trị không có phần lẻ khác 0; không mặc định formatter luôn in chín chữ số nano.

~~~java
LocalTime a = LocalTime.of(9, 30, 15);
LocalTime b = LocalTime.of(9, 30, 15, 123_000_000);
LocalTime c = LocalTime.of(9, 30, 15, 123_456_789);

System.out.println(DateTimeFormatter.ISO_LOCAL_TIME.format(a));
System.out.println(DateTimeFormatter.ISO_LOCAL_TIME.format(b));
System.out.println(DateTimeFormatter.ISO_LOCAL_TIME.format(c));
~~~

Stdout:

~~~text
09:30:15
09:30:15.123
09:30:15.123456789
~~~

Kiểu Java hỗ trợ nano giây nhưng không có nghĩa đồng hồ hệ thống hoặc cơ sở dữ liệu luôn có độ chính xác nano giây. Nếu API cần chính xác ba chữ số mili giây, phải xác định hợp đồng định dạng cụ thể.

## 11. Tái sử dụng formatter

Các formatter ISO dựng sẵn là bất biến và thread-safe. Có thể tái sử dụng một formatter trong nhiều lời gọi:

~~~java
private static final DateTimeFormatter DATE_FORMATTER =
        DateTimeFormatter.ISO_LOCAL_DATE;
~~~

Không cần xây dựng formatter mới cho mọi request. Nếu thật sự cần format tùy chỉnh, có thể dùng **DateTimeFormatter.ofPattern(...)**, nhưng với định dạng ISO thông dụng, các hằng có sẵn giúp tránh sai khác về dấu phân cách hoặc thành phần giờ.

Nếu pattern tùy chỉnh có locale, quy tắc parse hoặc trường năm đặc biệt, phải kiểm thử rõ. Dạng ISO dựng sẵn không có nghĩa mọi đầu vào đều tự hợp lệ hoặc phù hợp với mọi hợp đồng API.

## 12. Xử lý lỗi parse và validation

Một formatter không tự biến dữ liệu không hợp lệ thành giá trị đúng. Ví dụ, LocalDate.parse("2026-02-30", ISO_LOCAL_DATE) ném DateTimeParseException vì ngày không tồn tại.

Ví dụ xử lý ở ranh giới nhập liệu:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;

public class IsoValidationDemo {
    public static void main(String[] args) {
        String input = "2026-10-24";
        try {
            LocalDate date = LocalDate.parse(
                    input, DateTimeFormatter.ISO_LOCAL_DATE);
            System.out.println("parsed=" + date);
            System.out.println("roundTrip=" +
                    DateTimeFormatter.ISO_LOCAL_DATE.format(date));
        } catch (DateTimeParseException e) {
            System.out.println("invalid-date");
        }
    }
}
~~~

Stdout:

~~~text
parsed=2026-10-24
roundTrip=2026-10-24
~~~

Trong ứng dụng, có thể trả validation error phù hợp cho người dùng. Không nên bắt tất cả lỗi rồi thay bằng một ngày mặc định âm thầm. Với timestamp, cần xác nhận cả cú pháp **và** ngữ nghĩa: chuỗi local parse thành công vẫn có thể thiếu offset để làm hạn thanh toán hoặc thời điểm audit.

## 13. Những lỗi thường gặp

| Lỗi | Vấn đề | Cách sửa |
|---|---|---|
| Dùng ISO_LOCAL_DATE_TIME rồi coi chuỗi là UTC | LocalDateTime không có offset | Dùng kiểu có offset hoặc Instant |
| Parse chuỗi +07:00 thành LocalDateTime | Làm mất offset nguồn | Dùng ISO_OFFSET_DATE_TIME với OffsetDateTime |
| Dùng ISO_INSTANT cho LocalDateTime | Thiếu thông tin tạo Instant | Quy đổi bằng ZoneId/offset hợp lệ |
| Nối Z vào chuỗi local | Chỉ đổi văn bản, không chuyển thời gian | Dùng phép quy đổi đúng ngữ nghĩa |
| Coi +07:00 tương đương Asia/Ho_Chi_Minh | Offset không giữ quy tắc vùng | Lưu ZoneId khi cần |
| Dùng BASIC_ISO_DATE khi hợp đồng yêu cầu dấu gạch | Sai format API | Dùng ISO_LOCAL_DATE |
| Nhầm ISO_WEEK_DATE với năm/tháng/ngày thường | Quy tắc năm tuần khác năm lịch | Hiểu tuần ISO và parse đúng kiểu |
| Giả định luôn có chín chữ số phần giây | Formatter có thể bỏ phần 0 cuối | Xác định precision riêng nếu bắt buộc |
| Bắt mọi lỗi parse rồi trả ngày mặc định | Che dữ liệu sai | Validation tường minh |
| Tạo pattern riêng ở nhiều vị trí | Cách định dạng không nhất quán | Tái sử dụng hằng ISO hoặc formatter chung |

## 14. Checklist chọn formatter ISO

1. Giá trị nguồn là LocalDate, LocalTime, LocalDateTime, OffsetDateTime, ZonedDateTime hay Instant?
2. Hợp đồng cần offset, ZoneId hay chỉ thành phần lịch?
3. API cần dạng cơ bản yyyyMMdd hay dạng có dấu gạch yyyy-MM-dd?
4. Dữ liệu thuộc ngày thường, tuần ISO hay thứ tự ngày trong năm?
5. Độ chính xác giây thập phân cần đến đâu?
6. Parser có kiểm tra ngày hợp lệ và báo lỗi đầu vào rõ không?
7. Round-trip có giữ đúng ý nghĩa, offset và vùng cần thiết không?
8. Có thêm Z/offset bằng xử lý chuỗi thay vì chuyển đổi kiểu thời gian không?
9. Lịch tương lai có cần lưu ZoneId để giải quyết DST không?
10. Mã đã test dữ liệu hợp lệ, sai ngày, thiếu offset và phần giây chưa?

### Câu hỏi tự kiểm tra

**1. Formatter phù hợp với LocalDate là gì?**  
DateTimeFormatter.ISO_LOCAL_DATE.

**2. ISO_LOCAL_DATE_TIME có chứa múi giờ không?**  
Không. Nó chỉ biểu diễn ngày và giờ địa phương.

**3. Formatter nào dành cho Instant?**  
DateTimeFormatter.ISO_INSTANT.

**4. Chuỗi có +07:00 nên parse thành LocalDateTime để giữ offset?**  
Không. Dùng ISO_OFFSET_DATE_TIME và OffsetDateTime.

**5. Chuỗi 20261024 phù hợp với formatter nào?**  
BASIC_ISO_DATE.

**6. 2026-W43-6 và 2026-297 biểu diễn điều gì?**  
Lần lượt là ngày theo tuần ISO và ngày thứ 297 của năm.

**7. Vì sao không nối Z vào LocalDateTime?**  
Vì đó chỉ đổi chuỗi, không quy đổi thời gian; phải xác định ZoneId hoặc offset trước.

**Ghi nhớ:** Các formatter ISO dựng sẵn giúp định dạng thống nhất, nhưng phải chọn theo kiểu dữ liệu. **LOCAL** dành cho ngày giờ chưa gắn vùng; **OFFSET/ZONED** giữ độ lệch hoặc vùng; **ISO_INSTANT** dành cho thời điểm tuyệt đối. Parse và format đúng ngữ nghĩa ngay từ đầu tránh mất offset, hiểu sai UTC và lỗi trao đổi dữ liệu giữa các hệ thống.
