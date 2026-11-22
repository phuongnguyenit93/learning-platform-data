# Chuyển đổi hệ lịch để hiển thị và giới hạn khi trao đổi dữ liệu

## 1. Đổi cách gọi một ngày không phải đổi sang một ngày khác

Một ngày có thể được mô tả theo nhiều hệ lịch. Chẳng hạn, ngày ISO `2024-02-29` có năm Phật lịch Thái là 2567 và thuộc năm 6 của niên hiệu Reiwa trong lịch Nhật Bản. Các thành phần nhìn thấy khác nhau nhưng vẫn có thể chỉ **cùng một ngày trên dòng ngày**.

Trong Java, `Chronology` mô tả hệ lịch; các kiểu như `ThaiBuddhistDate` hoặc `JapaneseDate` giữ ngày theo hệ lịch tương ứng. Việc chuyển đổi hỗ trợ trình bày cho người dùng, nhưng cần tách rõ khỏi hợp đồng trao đổi dữ liệu giữa các hệ thống.

Nếu một API chờ ngày ISO mà nhận chuỗi năm 2567 không kèm ngữ cảnh, nó có thể hiểu là năm ISO 2567. Cùng một chuỗi chữ số không tự giải thích nó thuộc lịch nào. Vì vậy không dùng chuỗi hiển thị tùy theo hệ lịch như một giao thức trao đổi ngầm.

## 2. Tách ba lựa chọn: hệ lịch, ngôn ngữ và múi giờ

| Lựa chọn | Quyết định điều gì? | API tiêu biểu |
|---|---|---|
| Hệ lịch | Cách xác định năm, tháng, ngày, kỷ nguyên | `Chronology`, `withChronology(...)` |
| Ngôn ngữ/vùng | Tên tháng, thứ, kỷ nguyên và cách trình bày theo vùng | `Locale`, `withLocale(...)` |
| Múi giờ | Một thời điểm rơi vào giờ/ngày địa phương nào | `ZoneId`, `withZone(...)` |

Đổi `Locale` không đồng nghĩa tự đổi hệ lịch cho mọi bộ định dạng. Nếu yêu cầu phải dùng lịch cụ thể, hãy chọn `Chronology` tường minh. Đổi hệ lịch cũng không tự chuyển múi giờ.

`LocalDate` là ngày ISO không có giờ và múi giờ. Khi đã có một ngày ISO xác định, chuyển sang hệ lịch khác là biểu diễn ngày ấy theo quy tắc khác. Nếu đầu vào là `Instant`, trước tiên cần quyết định múi giờ để xác định ngày địa phương phục vụ việc hiển thị. Hai nơi có thể còn ở hai ngày khác nhau tại cùng một thời điểm.

Đừng dùng phép chuyển hệ lịch để giải quyết bài toán múi giờ, hoặc dùng một ngôn ngữ giao diện để tự suy ra hệ lịch và vùng giờ của dữ liệu nghiệp vụ.

## 3. Chuyển bằng thông tin ngày, không sao chép các trường số

Cách chuyển ngày ISO đã có:

```java
LocalDate iso = LocalDate.of(2024, 2, 29);
ThaiBuddhistDate buddhist = ThaiBuddhistDate.from(iso);
JapaneseDate japanese = JapaneseDate.from(iso);
```

Các phương thức `from` đọc thông tin ngày để tạo ngày tương đương trong hệ đích. Cách khác là dùng `Chronology.date(temporal)` hoặc `dateEpochDay(...)` khi đã có một điểm ngày tương ứng.

Không chuyển bằng cách lấy `getYear()`, `getMonthValue()`, `getDayOfMonth()` rồi truyền nguyên ba số ấy cho một hệ lịch khác. Phép đó tạo một ngày có **nhãn trường tương tự**, không nhất thiết cùng ngày.

Ví dụ, “năm 2024” trong ISO và “năm 2024” trong Phật lịch Thái không phải cùng năm. Một số hệ có cấu trúc tháng hoặc kỷ nguyên khác; không được coi phép cộng một hằng số năm là thuật toán tổng quát cho mọi chuyển đổi.

### Cùng ngày nhưng không equals

Các kiểu lịch có thể so sánh trên dòng ngày bằng `isEqual`, hoặc đối chiếu `toEpochDay()`. Ngày epoch là số ngày tính từ ngày mốc ISO 1970-01-01, không phải số mili giây của một thời điểm.

`equals` còn xét biểu diễn/hệ lịch của đối tượng. Vì vậy một `LocalDate` và một `ThaiBuddhistDate` cùng ngày có thể có `isEqual(...) == true` nhưng `equals(...) == false`. Đừng dùng sự khác biệt này để kết luận phép chuyển đã dịch ngày.

Nếu tập hợp hoặc khóa dữ liệu phải gom các biểu diễn cùng ngày, hãy chuẩn hóa về hợp đồng chung trước khi dùng làm khóa. Không trộn tùy tiện các kiểu lịch rồi chờ mọi phép so sánh coi chúng là cùng một giá trị.

## 4. Hiển thị qua bộ định dạng có chronology

Không bắt buộc chuyển biến nguồn sang một kiểu khác chỉ để tạo nhãn hiển thị. `DateTimeFormatter.withChronology(...)` cho phép bộ định dạng chuyển ngày sang hệ lịch được chọn trước khi xuất các trường:

```java
DateTimeFormatter display = DateTimeFormatter
        .ofPattern("G yyyy-MM-dd", Locale.ENGLISH)
        .withChronology(ThaiBuddhistChronology.INSTANCE);
String label = display.format(iso);
```

Đây là đoạn minh họa trong một phương thức Java. `G` là kỷ nguyên; `y` là năm trong kỷ nguyên. Với ví dụ này, nhãn là `BE 2567-02-29` trong môi trường được kiểm chứng bên dưới. Đối tượng `iso` vẫn giữ ngày ISO ban đầu.

Với lịch Nhật Bản, năm theo niên hiệu cần đi cùng kỷ nguyên như Reiwa hoặc Heisei. Một số đơn lẻ `6` không đủ xác định một năm nếu không biết niên hiệu nào.

Không mặc định ký hiệu `u` và `y` có thể thay nhau cho mọi kiểu lịch. `u` là năm kéo dài của hệ lịch, còn `y` là năm trong kỷ nguyên. Với lịch Nhật, năm kéo dài có thể trùng năm ISO trong khi năm theo niên hiệu khác. Chọn trường theo dữ liệu muốn biểu diễn và đủ thông tin để đọc lại.

Các tên kỷ nguyên/tháng là dữ liệu ngôn ngữ; chúng có thể thay đổi theo locale và phiên bản JDK. Bộ định dạng hiển thị cần được kiểm tra trên môi trường triển khai nếu thiết kế yêu cầu chính xác từng ký tự.

## 5. Đọc lại phải biết cùng hệ lịch và đủ trường

Chuỗi `BE 2567-02-29` được đọc bằng bộ định dạng đã chọn Phật lịch Thái, không phải bộ định dạng ngày ISO thông thường:

```java
ThaiBuddhistDate parsed = display.parse(text, ThaiBuddhistDate::from);
LocalDate isoAgain = LocalDate.from(parsed);
```

Ở đây `display` phải được cấu hình phù hợp, và `text` là chuỗi theo đúng hợp đồng đó. Nếu dùng `ResolverStyle.STRICT`, các trường cần được cung cấp đủ và tạo thành ngày hợp lệ trong hệ lịch đang dùng.

Phép chuyển về `LocalDate` bảo toàn ngày tương ứng trong ISO. Nó không có nghĩa chuỗi gốc đã là ISO, và cũng không giữ nguyên tên kỷ nguyên hoặc cách viết người dùng đã nhập.

Nếu nhận dữ liệu lịch Nhật, chỉ có năm-niên hiệu mà thiếu kỷ nguyên sẽ mơ hồ. Nếu dùng những hệ lịch có biến thể hoặc dữ liệu bảng giới hạn, phải biết biến thể và phạm vi được hỗ trợ. Không tự thử nhiều hệ lịch rồi chọn kết quả đầu tiên đọc được: nhiều hệ có thể chấp nhận cùng các con số nhưng tạo những ngày khác nhau.

## 6. Chương trình chạy đầy đủ

Lưu đoạn sau vào `CalendarDisplayDemo.java`. Chương trình dùng Java 17 trở lên và không cần thư viện ngoài.

```java
import java.time.DateTimeException;
import java.time.LocalDate;
import java.time.chrono.JapaneseChronology;
import java.time.chrono.JapaneseDate;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.chrono.ThaiBuddhistDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class CalendarDisplayDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2024, 2, 29);
        ThaiBuddhistDate buddhist = ThaiBuddhistDate.from(iso);
        JapaneseDate japanese = JapaneseDate.from(iso);

        System.out.println("iso=" + iso);
        System.out.println("buddhistYear="
                + buddhist.get(ChronoField.YEAR));
        System.out.println("japaneseYearOfEra="
                + japanese.get(ChronoField.YEAR_OF_ERA));
        System.out.println("sameEpochDay="
                + (iso.toEpochDay() == buddhist.toEpochDay()));
        System.out.println("isEqual=" + iso.isEqual(buddhist));
        System.out.println("equals=" + iso.equals(buddhist));

        DateTimeFormatter thaiDisplay = DateTimeFormatter
                .ofPattern("G yyyy-MM-dd", Locale.ENGLISH)
                .withChronology(ThaiBuddhistChronology.INSTANCE)
                .withResolverStyle(ResolverStyle.STRICT);

        DateTimeFormatter japaneseDisplay = DateTimeFormatter
                .ofPattern("G y-MM-dd", Locale.ENGLISH)
                .withChronology(JapaneseChronology.INSTANCE)
                .withResolverStyle(ResolverStyle.STRICT);

        String displayed = thaiDisplay.format(iso);
        System.out.println("display=" + displayed);
        System.out.println("japaneseDisplay=" + japaneseDisplay.format(iso));
        System.out.println("sameDisplay=" + displayed.equals(
                thaiDisplay.format(buddhist)));

        ThaiBuddhistDate parsed = thaiDisplay.parse(
                displayed, ThaiBuddhistDate::from);
        System.out.println("roundTripIso=" + LocalDate.from(parsed));

        System.out.println("wireFromIso="
                + DateTimeFormatter.ISO_LOCAL_DATE.format(iso));
        System.out.println("wireFromBuddhist="
                + DateTimeFormatter.ISO_LOCAL_DATE.format(buddhist));

        try {
            JapaneseDate.from(LocalDate.of(1800, 1, 1));
        } catch (DateTimeException e) {
            System.out.println("unsupportedJapaneseDate=ERROR");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac CalendarDisplayDemo.java
java CalendarDisplayDemo
```

Kết quả đã kiểm chứng trên Zulu OpenJDK 24.0.2:

```text
iso=2024-02-29
buddhistYear=2567
japaneseYearOfEra=6
sameEpochDay=true
isEqual=true
equals=false
display=BE 2567-02-29
japaneseDisplay=Reiwa 6-02-29
sameDisplay=true
roundTripIso=2024-02-29
wireFromIso=2024-02-29
wireFromBuddhist=2024-02-29
unsupportedJapaneseDate=ERROR
```

Tên kỷ nguyên ở hai dòng hiển thị phụ thuộc dữ liệu ngôn ngữ/JDK; phần chuyển đổi và cách kiểm tra ngày cần được đối chiếu theo hợp đồng API. `ERROR` là nhãn do chương trình in khi bắt ngoại lệ, không phải thông điệp mặc định của Java.

Các điểm chính của kết quả:

- Năm và năm trong kỷ nguyên thay đổi nhưng `sameEpochDay` vẫn là `true`.
- `sameDisplay` cho thấy bộ định dạng có chronology có thể trình bày từ nguồn ISO hoặc từ kiểu ngày đích tương ứng.
- `roundTripIso` quay lại đúng ngày gốc bằng phép chuyển dựa trên ngày, không dựa trên việc trừ thủ công năm.
- `ISO_LOCAL_DATE` có chronology ISO ghi đè, nên định dạng ngày Phật lịch Thái thành ngày ISO tương ứng. Không suy rộng hành vi này cho mọi pattern tự tạo.
- Ngày lịch Nhật ngoài phạm vi thư viện hỗ trợ bị từ chối; không tự kéo dài dữ liệu niên hiệu về mọi ngày trong quá khứ.

## 7. Thiết kế hợp đồng trao đổi dữ liệu

### Khi hệ lịch khác chỉ phục vụ hiển thị

Có thể giữ ngày chuẩn trong nghiệp vụ và API là ISO, còn lựa chọn hệ lịch hiển thị nằm trong cấu hình giao diện. Ví dụ dữ liệu trao đổi:

```json
{
  "date": "2024-02-29",
  "displayCalendar": "ThaiBuddhist"
}
```

Trong hợp đồng minh họa này, trường `date` luôn là ngày ISO; `displayCalendar` chỉ yêu cầu cách trình bày. Phải công bố ý nghĩa ấy, không chờ bên nhận tự đoán dựa vào tên trường.

Nếu truyền một thời điểm thay vì ngày dân sự, dùng hợp đồng thời điểm/độ lệch/múi giờ phù hợp. Chuỗi ngày ISO không tự là một `Instant` và không cần bị đổi sang nửa đêm UTC chỉ để lưu trữ.

### Khi hệ lịch nguồn là dữ liệu nghiệp vụ

Nếu chức năng cần biết người dùng đã khai báo ngày theo hệ lịch nào, chỉ giữ một chuỗi ISO có thể chưa đủ để khôi phục ý nghĩa nguồn. Hợp đồng có thể cần thêm:

- Mã hệ lịch và biến thể được hỗ trợ.
- Các trường gốc như kỷ nguyên, năm trong kỷ nguyên, tháng, ngày theo quy tắc xác định.
- Ngày ISO tương ứng nếu hai bên thống nhất dùng để đối chiếu.
- Thông tin phiên bản dữ liệu lịch khi kết quả phụ thuộc nguồn dữ liệu hoặc biến thể.

Không gửi `"2567-02-29"` rồi mặc định bên nhận hiểu là Phật lịch Thái. Cũng không coi chuỗi `toString()` của một lớp Java là hợp đồng JSON phổ quát mà mọi ngôn ngữ đều đọc được.

Nếu bên nhận không hỗ trợ một hệ lịch, cần thống nhất chuẩn hóa có bảo toàn ý nghĩa hoặc từ chối rõ ràng. Không thay âm thầm bằng một hệ gần giống, vì “đọc được các số” khác với “cùng một ngày”.

## 8. Giới hạn của chuyển đổi và phép tính

### Phạm vi lịch không đồng nhất

Các hệ lịch có thể có phạm vi ngày hoặc dữ liệu khác nhau. `JapaneseDate` hỗ trợ ngày từ 01/01/1873 trở đi, không phải toàn bộ miền rất rộng của `LocalDate`. Các lịch có dữ liệu bảng hoặc biến thể cũng cần được kiểm tra riêng trước khi nhận một khoảng ngày lớn.

Việc cùng có trường năm-tháng-ngày không chứng minh mọi phép cộng đều tương đương giữa hai hệ lịch. “Thêm một tháng” thực hiện trong hệ lịch A có thể không cho cùng kết quả với chuyển sang B rồi thêm một tháng ở B. Nếu lịch khác chỉ dùng để hiển thị, giữ phép tính ở hệ chuẩn của nghiệp vụ và chuyển tại biên trình bày. Nếu nghiệp vụ dựa trên lịch nguồn, phải thiết kế phép tính theo đúng lịch đó.

### Không đồng nhất các lịch có tên gọi gần nhau

Phật lịch Thái trong Java không phải lịch âm Việt Nam. Một hệ Hijrah cụ thể cũng không đại diện tự động cho mọi biến thể lịch Hồi giáo. Những tính năng như tháng nhuận, quy tắc quan sát hoặc dữ liệu công bố cần nguồn và mô hình phù hợp; không lấy một chronology sẵn có làm bộ chuyển tổng quát cho lịch chưa được hỗ trợ.

### Giữ rõ ngày và thời điểm

`toEpochDay()` giúp quy chiếu ngày, không phải thời gian chính xác đến giây. Nếu cần gắn giờ và múi giờ, cần xử lý riêng những quy tắc của ngày-giờ tại vùng đó. Không nhân số ngày epoch với 86.400 rồi mặc định đã có thời điểm đúng cho mọi ngày địa phương.

## 9. Tự thực hành

1. Đổi ngày ISO thành `2024-03-01` và kiểm tra vòng chuyển ISO → Phật lịch Thái → ISO giữ nguyên ngày.
2. Đổi locale hiển thị rồi quan sát tên kỷ nguyên thay đổi; xác nhận `toEpochDay()` vẫn không đổi.
3. Thử đọc chuỗi Phật lịch Thái bằng đúng bộ định dạng có chronology và bằng một bộ định dạng ISO. Giải thích vì sao cùng chữ số năm không mang cùng ý nghĩa.
4. Thiết kế dữ liệu cho hai yêu cầu riêng: “chỉ hiển thị lịch Nhật” và “phải giữ nguyên khai báo lịch Nhật của người dùng”. Chỉ ra trường thông tin nào là lựa chọn giao diện, trường nào phải được bảo toàn như dữ liệu nguồn.

Tham khảo: [Chronology](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/Chronology.html), [JapaneseDate](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/JapaneseDate.html) và [DateTimeFormatter — withChronology](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html#withChronology(java.time.chrono.Chronology)) trong Java SE 21.
