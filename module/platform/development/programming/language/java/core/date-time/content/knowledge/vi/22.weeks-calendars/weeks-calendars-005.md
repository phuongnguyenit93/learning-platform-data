# Chronology và mối quan hệ giữa hệ lịch với ngày ISO

## Cùng một ngày, các hệ lịch có thể gọi bằng những trường khác nhau

Một ngày được ghi là `2024-06-15` theo lịch ISO có thể mang năm `2567` trong lịch Phật giáo Thái. Nếu chỉ thấy con số 2567 rồi tạo `LocalDate.of(2567, 6, 15)`, ta đã tạo một ngày ISO khác, không phải chuyển hệ lịch cho ngày ban đầu.

Sự khác biệt nằm ở **hệ lịch (chronology)**: các quy tắc tổ chức và đặt tên ngày bằng năm, tháng, ngày, kỷ nguyên cùng những trường liên quan.

Trong Java, `LocalDate` luôn dùng hệ lịch ISO. Đổi ngôn ngữ hiển thị không biến đối tượng ấy thành một ngày thuộc hệ lịch khác. Khi cần hỗ trợ nhiều hệ lịch, phải xác định rõ lúc nào đang đổi cách biểu diễn cùng một ngày và lúc nào đang tạo ngày từ các trường của một hệ lịch.

## 1. Vai trò của `Chronology`

`Chronology` là giao diện mô tả một hệ lịch và cung cấp cách tạo ngày theo quy tắc của hệ lịch đó. Các triển khai dựng sẵn bao gồm ISO, Japanese, Minguo, Thai Buddhist và Hijrah. [Tài liệu `Chronology`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/Chronology.html)

Một hệ lịch quyết định ý nghĩa của các trường, chẳng hạn:

- `YEAR`: năm theo cách đánh số liên tục của hệ lịch đó.
- `YEAR_OF_ERA`: năm trong một kỷ nguyên.
- `ERA`: kỷ nguyên.
- `MONTH_OF_YEAR`: tháng trong năm.
- `DAY_OF_MONTH`: ngày trong tháng.
- Quy tắc năm nhuận và độ dài tháng.

Không được mặc định mọi hệ lịch có cùng số tháng, cùng cách đánh số năm hay cùng quan hệ giữa năm và kỷ nguyên.

Có thể phân biệt hai loại đối tượng:

```text
Chronology
    = quy tắc hệ lịch + các phương thức tạo/chuyển ngày

ChronoLocalDate hoặc kiểu ngày cụ thể
    = một giá trị ngày theo hệ lịch ấy
```

Ví dụ `ThaiBuddhistChronology.INSTANCE` đại diện quy tắc; `ThaiBuddhistDate` đại diện một ngày theo quy tắc đó.

## 2. `LocalDate` đã chọn ISO một cách rõ ràng

`LocalDate` không phải “ngày tự đổi hệ lịch theo máy”. Nó giữ một ngày theo hệ ISO, không kèm giờ và múi giờ.

Điều đó giúp mã thông thường có giả định ổn định khi làm việc với năm–tháng–ngày. Ví dụ:

```java
LocalDate iso = LocalDate.of(2024, 6, 15);
```

Đoạn minh họa này tạo ngày ISO 15/06/2024. Nó không có nghĩa “ngày 15 tháng 6 năm 2024 trong bất kỳ hệ lịch nào”.

Đối với phần lớn ứng dụng, dùng `LocalDate` ở mô hình chính và chuyển đổi có chủ đích tại nơi nhập/hiển thị là hướng đơn giản. `ChronoLocalDate` dành cho trường hợp thực sự cần ngày với hệ lịch thay đổi; việc dùng nó khắp ứng dụng đòi hỏi kiểm soát các giả định lịch chặt chẽ hơn. [Khuyến nghị sử dụng `ChronoLocalDate`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/ChronoLocalDate.html)

Chỉ chọn giao diện tổng quát không làm thuật toán tự đúng cho mọi hệ lịch. Một phép tính giả định “thêm 12 tháng luôn là thêm một năm” vẫn cần được xem xét khi hệ lịch đầu vào chưa biết trước.

## 3. Chiếc cầu chuyển đổi: ngày tuyệt đối theo `epochDay`

Các ngày được hỗ trợ có thể liên hệ qua `EPOCH_DAY`: số ngày tương đối với ngày ISO 01/01/1970, trong đó ngày gốc có giá trị `0`.

Hai biểu diễn thuộc hai hệ lịch có thể có các trường năm/tháng/ngày khác nhau nhưng cùng `epochDay`. Khi chuyển đúng, chúng trỏ đến cùng vị trí trên trục ngày.

```text
Ngày ISO 2024-06-15
          │
          │ cùng epochDay
          ▼
Ngày Thai Buddhist 2567-06-15
```

Đổi hệ lịch là bảo toàn ngày mà giá trị đại diện, không phải giữ nguyên toàn bộ con số của các trường.

Các lời gọi thường dùng:

```java
ThaiBuddhistDate thai = ThaiBuddhistDate.from(iso);
LocalDate isoAgain = LocalDate.from(thai);
```

Hoặc qua giao diện `Chronology`:

```java
ChronoLocalDate converted =
        ThaiBuddhistChronology.INSTANCE.date(iso);
```

Đây là các đoạn minh họa với `iso` đã có và cần các import tương ứng.

`epochDay` là chỉ số **ngày**, không phải số giây/mili giây của một `Instant`. Một ngày chưa có giờ và múi giờ vẫn chưa xác định duy nhất thời điểm toàn cầu.

## 4. Chương trình hoàn chỉnh

Lưu dưới tên `ChronologyIsoDemo.java`. Chương trình dùng Java 17 trở lên:

```java
import java.time.LocalDate;
import java.time.chrono.ChronoLocalDate;
import java.time.chrono.Chronology;
import java.time.chrono.JapaneseDate;
import java.time.chrono.MinguoDate;
import java.time.chrono.ThaiBuddhistChronology;
import java.time.chrono.ThaiBuddhistDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.time.temporal.ChronoField;
import java.util.Locale;

public class ChronologyIsoDemo {
    public static void main(String[] args) {
        LocalDate iso = LocalDate.of(2024, 6, 15);
        ThaiBuddhistDate thai = ThaiBuddhistDate.from(iso);
        MinguoDate minguo = MinguoDate.from(iso);
        JapaneseDate japanese = JapaneseDate.from(iso);

        System.out.println("iso=" + iso);
        System.out.println("isoChronology=" + iso.getChronology().getId());
        System.out.println("thaiChronology=" + thai.getChronology().getId());
        System.out.println("thaiYear=" + thai.get(ChronoField.YEAR));
        System.out.println("minguoYear=" + minguo.get(ChronoField.YEAR));
        System.out.println("japaneseYear=" + japanese.get(ChronoField.YEAR));
        System.out.println("japaneseYearOfEra="
                + japanese.get(ChronoField.YEAR_OF_ERA));

        System.out.println("sameEpochDay="
                + (iso.toEpochDay() == thai.toEpochDay()));
        System.out.println("backToIso=" + LocalDate.from(thai));
        System.out.println("sameDay=" + thai.isEqual(iso));
        System.out.println("equalsAcrossCalendars=" + thai.equals(iso));
        System.out.println("naturalComparisonIsZero="
                + (thai.compareTo(iso) == 0));

        Chronology chronology = Chronology.of("ThaiBuddhist");
        ChronoLocalDate fromFields = chronology.date(2567, 6, 15);
        ChronoLocalDate fromIso = chronology.date(iso);

        System.out.println("createdFromThaiFields=" + LocalDate.from(fromFields));
        System.out.println("convertedFromIso=" + LocalDate.from(fromIso));

        LocalDate copiedAsIso = LocalDate.of(
                thai.get(ChronoField.YEAR),
                thai.get(ChronoField.MONTH_OF_YEAR),
                thai.get(ChronoField.DAY_OF_MONTH));
        System.out.println("copiedFieldsAsIso=" + copiedAsIso);
        System.out.println("copiedFieldsSameDay=" + copiedAsIso.isEqual(iso));

        DateTimeFormatter thaiText =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT)
                        .withChronology(ThaiBuddhistChronology.INSTANCE)
                        .withResolverStyle(ResolverStyle.STRICT);

        System.out.println("formattedThai=" + thaiText.format(iso));
        LocalDate parsedIso =
                thaiText.parse("2567-06-15", LocalDate::from);
        System.out.println("parsedThaiToIso=" + parsedIso);

        JapaneseDate before =
                JapaneseDate.from(LocalDate.of(2019, 4, 30));
        JapaneseDate after =
                JapaneseDate.from(LocalDate.of(2019, 5, 1));

        System.out.println("japaneseBefore="
                + before.get(ChronoField.YEAR)
                + "/era=" + before.get(ChronoField.ERA)
                + "/yearOfEra=" + before.get(ChronoField.YEAR_OF_ERA));
        System.out.println("japaneseAfter="
                + after.get(ChronoField.YEAR)
                + "/era=" + after.get(ChronoField.ERA)
                + "/yearOfEra=" + after.get(ChronoField.YEAR_OF_ERA));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ChronologyIsoDemo.java
java ChronologyIsoDemo
```

Stdout:

```text
iso=2024-06-15
isoChronology=ISO
thaiChronology=ThaiBuddhist
thaiYear=2567
minguoYear=113
japaneseYear=2024
japaneseYearOfEra=6
sameEpochDay=true
backToIso=2024-06-15
sameDay=true
equalsAcrossCalendars=false
naturalComparisonIsZero=false
createdFromThaiFields=2024-06-15
convertedFromIso=2024-06-15
copiedFieldsAsIso=2567-06-15
copiedFieldsSameDay=false
formattedThai=2567-06-15
parsedThaiToIso=2024-06-15
japaneseBefore=2019/era=2/yearOfEra=31
japaneseAfter=2019/era=3/yearOfEra=1
```

## 5. Tạo từ trường và chuyển từ ngày là hai thao tác khác nhau

Hai lời gọi trong chương trình cùng cho ngày ISO 15/06/2024 sau khi quy đổi:

```java
chronology.date(2567, 6, 15);
chronology.date(iso);
```

Nhưng đầu vào và ý nghĩa khác nhau:

- `date(2567, 6, 15)` diễn giải các số theo hệ lịch Thai Buddhist đã chọn.
- `date(iso)` lấy ngày mà giá trị ISO đang đại diện rồi chuyển cách biểu diễn.

Đoạn `copiedAsIso` cố ý minh họa lỗi: chép năm 2567 từ ngày Thai Buddhist vào hàm tạo `LocalDate` làm ra ngày ISO năm 2567. Nó không cùng ngày với nguồn ban đầu.

Nếu nhận dữ liệu gồm các trường và mã hệ lịch, hãy dùng hệ lịch đó để dựng ngày trước khi chuyển về ISO. Nếu đầu vào đã là một đối tượng ngày đáng tin cậy, dùng API chuyển đổi thay vì tự chép trường.

Tránh tự cộng/trừ một hằng số năm như một phương pháp tổng quát. Một hệ lịch có thể dùng kỷ nguyên, tháng khác cấu trúc hoặc dữ liệu quy đổi có giới hạn. Việc một ví dụ Thai Buddhist có quan hệ năm đơn giản không chứng minh mọi hệ lịch đều như vậy.

## 6. “Cùng ngày” khác với `equals` và thứ tự tự nhiên

Chương trình cho:

```text
sameDay=true
equalsAcrossCalendars=false
naturalComparisonIsZero=false
```

`ChronoLocalDate.isEqual` so sánh vị trí ngày, bỏ qua khác biệt hệ lịch. `equals` tính cả hệ lịch. Thứ tự tự nhiên `compareTo` của các ngày khác hệ lịch còn dùng hệ lịch để phân biệt khi vị trí ngày bằng nhau. [Tài liệu so sánh của `ChronoLocalDate`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/ChronoLocalDate.html)

Điều này quan trọng khi:

- Kiểm tra một lần chuyển đổi có bảo toàn ngày không.
- Dùng ngày làm khóa của tập hợp hoặc bảng ánh xạ.
- Sắp xếp dữ liệu có nhiều hệ lịch.
- Khử trùng lặp theo “cùng ngày thực tế”.

Nếu yêu cầu là một khóa ngày thống nhất, chuyển về `LocalDate` hoặc dùng `epochDay` theo hợp đồng rõ ràng. Nếu cần giữ danh tính hệ lịch, đừng loại bỏ nó chỉ để phép `equals` thành true.

Không dùng `==` để so sánh giá trị ngày.

## 7. Năm trong kỷ nguyên không phải lúc nào cũng là năm ISO

Ví dụ Japanese trong chương trình đi qua ranh giới:

```text
2019-04-30: YEAR=2019, ERA=2, YEAR_OF_ERA=31
2019-05-01: YEAR=2019, ERA=3, YEAR_OF_ERA=1
```

Ngày lịch tiến một ngày; năm theo trục liên tục vẫn là 2019. Nhưng kỷ nguyên đổi từ Heisei sang Reiwa và năm trong kỷ nguyên quay về 1.

Vì vậy, một dữ liệu “năm 1, tháng 5, ngày 1” theo lịch Nhật còn cần thông tin kỷ nguyên để được hiểu đúng. Không thể chỉ lấy `YEAR_OF_ERA` rồi coi nó là năm ISO.

`JapaneseDate` dùng cấu trúc tháng/ngày tương ứng ISO trong phạm vi hỗ trợ nhưng khác cách đánh số theo kỷ nguyên; nó không hỗ trợ tùy ý mọi ngày lịch sử. [Tài liệu `JapaneseDate`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/JapaneseDate.html)

Tương tự, `ThaiBuddhistDate` là kiểu cho hệ lịch Phật giáo Thái được Java mô hình hóa; tên hệ lịch phải được hiểu theo triển khai cụ thể. [Tài liệu `ThaiBuddhistDate`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/ThaiBuddhistDate.html)

Không coi `HijrahDate`, lịch Phật giáo Thái hoặc một kiểu lịch khác có sẵn là “âm lịch Việt Nam”. Muốn hỗ trợ một lịch cụ thể phải kiểm tra đúng quy tắc và dữ liệu mà triển khai cung cấp.

## 8. Hệ lịch, ngôn ngữ và múi giờ là ba trục cấu hình

| Thành phần | Quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| `Chronology` | Cách tổ chức/đánh số ngày | ISO, Thai Buddhist, Japanese |
| `Locale` | Ngôn ngữ và quy ước hiển thị/phân tích liên quan | Tên tháng, chữ chỉ kỷ nguyên |
| `ZoneId` | Quy tắc liên hệ giờ địa phương với thời điểm | `Asia/Ho_Chi_Minh` |

Đổi `Locale` có thể đổi chữ hiển thị, không phải một phép chuyển hệ lịch của đối tượng ngày.

Đổi `ZoneId` tác động việc diễn giải thời điểm và ngày giờ địa phương; nó không đồng nghĩa đổi hệ lịch.

Ví dụ cùng `Instant` có thể rơi vào hai ngày địa phương khác nhau ở hai vùng. Sau khi chọn vùng và xác định ngày địa phương ISO, ta mới có thể chuyển cách biểu diễn ngày ấy sang hệ lịch khác nếu cần.

Trình tự khái niệm:

```text
Instant + ZoneId
        ↓
Ngày/giờ địa phương, trong đó có LocalDate ISO
        ↓ chọn hệ lịch
Ngày tương ứng theo chronology cần hiển thị
        ↓ chọn ngôn ngữ và định dạng
Văn bản cho người dùng
```

Không thay thế bước chọn vùng bằng bước chọn ngôn ngữ hoặc hệ lịch.

## 9. Định dạng có hệ lịch và phân tích về ngày ISO

Bộ `thaiText` trong chương trình dùng:

```java
.withChronology(ThaiBuddhistChronology.INSTANCE)
```

Khi định dạng ngày ISO 15/06/2024, nó chuyển sang biểu diễn Thai Buddhist và in `2567-06-15`.

Khi phân tích chuỗi `2567-06-15`, cùng cấu hình diễn giải trường năm theo Thai Buddhist, rồi truy vấn `LocalDate::from` cho ngày ISO tương ứng.

Điểm cần giữ rõ là cấu hình hệ lịch phải đi cùng hợp đồng chuỗi. Cùng văn bản `2567-06-15`, nếu dùng `LocalDate.parse` mặc định, nghĩa của năm là ISO và kết quả khác.

Nếu định dạng theo kỷ nguyên, cân nhắc cả `G` và `y`; nếu dùng năm theo trục của hệ lịch, `u` có ý nghĩa khác. Với tên tháng/kỷ nguyên dạng chữ, chọn `Locale` của dữ liệu rõ ràng. Khi cần nhập liệu chặt chẽ, cấu hình quy tắc phân giải và kiểm tra giá trị kiểu đích thay vì chỉ kiểm tra đọc được ký tự.

## 10. Thiết kế ranh giới dữ liệu rõ ràng

Với ứng dụng chủ yếu dùng ISO nhưng có giao diện nhiều hệ lịch, có thể tổ chức:

```text
Đầu vào theo hệ lịch nguồn
        ↓ phân tích/kiểm tra với chronology nguồn
Ngày theo hệ lịch nguồn
        ↓ chuyển đổi bảo toàn ngày
LocalDate ISO dùng trong xử lý
        ↓ chuyển đổi khi cần
Biểu diễn theo hệ lịch đích để hiển thị
```

Nếu nguồn chỉ gửi ba con số năm/tháng/ngày mà không nói hệ lịch, bên nhận không nên đoán bằng kích thước của năm. Hãy nhận mã hệ lịch rõ ràng hoặc quy định cố định theo từng giao diện.

Chuyển đổi có thể thất bại khi ngày nằm ngoài phạm vi của một hệ lịch. Đừng mặc định mọi `LocalDate` trong toàn bộ phạm vi Java đều đổi được sang mọi chronology.

Nếu cần truy vết cách người dùng đã nhập, giữ thêm hệ lịch và thông tin biểu diễn nguồn phù hợp. Chỉ lưu ISO có thể bảo toàn ngày nhưng không bảo toàn toàn bộ cách gọi ngày ban đầu.

Với phép cộng tháng/năm theo lịch nguồn, hãy quyết định thực hiện trước hay sau chuyển đổi dựa trên ý nghĩa nghiệp vụ. Phép cộng một tháng theo một lịch bất kỳ không được mặc định tương đương phép cộng một tháng ISO.

## 11. Kiểm chứng và tự thực hành

Các kiểm tra có ích gồm:

- Chuyển ISO sang hệ lịch đích rồi quay lại, ngày ISO phải được bảo toàn trong phạm vi hỗ trợ.
- So sánh `epochDay` hoặc `isEqual`, không chỉ so sánh con số năm.
- Đi qua một ranh giới kỷ nguyên nếu hệ lịch có kỷ nguyên.
- Phân tích văn bản với đúng và sai hệ lịch để phát hiện sự khác biệt ý nghĩa.
- Kiểm tra ngày ngoài phạm vi hỗ trợ và cách báo lỗi.
- Xác nhận hợp đồng dùng ngày, chưa nhầm thành giây hay mili giây của thời điểm.

Câu hỏi tự kiểm tra:

1. `LocalDate.of(2567, 6, 15)` có tự hiểu năm Phật lịch không?
2. Để đổi một `ThaiBuddhistDate` về ngày ISO tương ứng, nên chép trường hay dùng API chuyển đổi?
3. Hai ngày khác hệ lịch cùng `epochDay` có nhất thiết `equals` không?
4. Đổi ngôn ngữ hiển thị có tự đổi hệ lịch của một `LocalDate` không?
5. Chỉ có ngày theo một chronology đã đủ tạo `Instant` chưa?

Gợi ý đáp án:

1. Không; nó tạo ngày ISO năm 2567.
2. Dùng `LocalDate.from(thaiDate)` hoặc API chuyển đổi tương ứng.
3. Không; `equals` xét cả hệ lịch. `isEqual` phù hợp khi hỏi cùng vị trí ngày.
4. Không.
5. Chưa; cần thông tin giờ và vùng/offset phù hợp để xác định thời điểm.

Hãy xem chronology là quy tắc mang ý nghĩa cho các trường ngày, dùng API chuyển đổi để bảo toàn cùng ngày và giữ ranh giới giữa hệ lịch, ngôn ngữ với múi giờ.
