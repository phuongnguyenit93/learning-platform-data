# Lấy giá trị số và tên hiển thị theo Locale

## 1. Một giá trị có nhiều cách biểu diễn

Với ngày `2024-03-18`, ta có thể cần:

- Số tháng `3` để truyền dữ liệu theo hợp đồng.
- Hằng `Month.MARCH` để viết điều kiện rõ nghĩa.
- Nhãn `March` cho giao diện tiếng Anh.
- Nhãn `tháng 3` cho giao diện tiếng Việt.
- Số thứ `1` theo ISO và nhãn `Thứ Hai` để hiển thị.

Các biểu diễn này phục vụ mục đích khác nhau. **Giá trị nghiệp vụ** nên được giữ bằng kiểu phù hợp hoặc số theo quy ước rõ ràng. **Tên hiển thị** được tạo ở lớp trình bày theo ngôn ngữ và ngữ cảnh.

`Locale` lựa chọn ngôn ngữ/vùng dùng để lấy nhãn. Nó không đổi tháng Ba thành một tháng khác và không đổi số ISO của thứ Hai từ `1` sang số khác.

Trong bài này, các ví dụ sử dụng lịch ISO của `java.time`, tập trung vào `Month` và `DayOfWeek`. Những kiểu biểu diễn từng phần như `Year`, `YearMonth` và `MonthDay` cũng có các phương thức đọc số tương ứng, nhưng không phải tất cả đều có phương thức `getDisplayName`.

## 2. Đọc số bằng phương thức có ý nghĩa nghiệp vụ

### 2.1. Month: tháng từ 1 đến 12

[Month](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Month.html) là enum đại diện 12 tháng. Số chuẩn lấy qua `getValue()`:

| Hằng | `getValue()` |
| --- | --- |
| `Month.JANUARY` | `1` |
| `Month.MARCH` | `3` |
| `Month.DECEMBER` | `12` |

Chuyển từ số thành enum bằng `Month.of(number)`. Giá trị ngoài `1..12`, chẳng hạn `0` hoặc `13`, gây `DateTimeException`; phương thức không tự quấn số về tháng hợp lệ.

Nếu đã có ngày hoặc kỳ, có thể đọc trực tiếp:

```java
LocalDate date = LocalDate.of(2024, 3, 18);

Month month = date.getMonth();          // MARCH
int monthNumber = date.getMonthValue(); // 3

YearMonth period = YearMonth.from(date);
int periodMonth = period.getMonthValue(); // 3
```

Trong mã nghiệp vụ, `Month.MARCH` thường thể hiện ý nghĩa rõ hơn một số `3` rời rạc. Khi giao tiếp với một hệ thống dùng số tháng, `getValue()` chuyển đổi theo quy ước đã biết.

### 2.2. DayOfWeek: thứ Hai là 1, Chủ nhật là 7

[DayOfWeek](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html) dùng số ISO:

| Hằng | `getValue()` |
| --- | --- |
| `MONDAY` | `1` |
| `TUESDAY` | `2` |
| `WEDNESDAY` | `3` |
| `THURSDAY` | `4` |
| `FRIDAY` | `5` |
| `SATURDAY` | `6` |
| `SUNDAY` | `7` |

`DayOfWeek.of(1)` là `MONDAY`, không phải Chủ nhật. Số ngoài `1..7` bị từ chối.

Một locale có thể có quy ước ngày bắt đầu tuần khác, nhưng `DayOfWeek.getValue()` vẫn dùng ISO. Đổi locale của nhãn không đổi quy tắc đánh số này. Nếu cần đánh số thứ theo tuần địa phương, đó là yêu cầu riêng, có thể xét `WeekFields`; không sửa nghĩa của `getValue()`.

Khi chuyển dữ liệu từ API cũ hoặc hệ thống ngoài, hãy kiểm tra hợp đồng. Ví dụ `Calendar.DAY_OF_WEEK` trong API cũ dùng Chủ nhật là `1`, khác `DayOfWeek`. Không đưa trực tiếp số của hai hệ vào cùng hàm rồi cho rằng chúng tương đương.

### 2.3. Year và các phần ngày khác

Một số cách đọc thường gặp:

| Kiểu | Phương thức | Ý nghĩa |
| --- | --- | --- |
| `Year` | `getValue()` | Giá trị năm |
| `YearMonth` | `getYear()` | Năm của kỳ |
| `YearMonth` | `getMonthValue()` | Số tháng `1..12` |
| `MonthDay` | `getMonthValue()` | Số tháng `1..12` |
| `MonthDay` | `getDayOfMonth()` | Ngày trong tháng |
| `LocalDate` | `getDayOfWeek()` | Enum thứ trong tuần |

Không thấy tên `getValue` rồi mặc định mọi kiểu đều dùng `1..12`. Miền và ý nghĩa luôn theo kiểu đang đọc.

## 3. ordinal() là vị trí enum, không phải số trên lịch

`ordinal()` là vị trí khai báo của hằng enum, bắt đầu từ `0`:

```java
Month.MARCH.getValue();       // 3
Month.MARCH.ordinal();        // 2

DayOfWeek.MONDAY.getValue();  // 1
DayOfWeek.MONDAY.ordinal();   // 0
```

API của `Month` và `DayOfWeek` yêu cầu dùng `getValue()` cho biểu diễn số nghiệp vụ. Dù với các enum này `ordinal() + 1` tình cờ khớp số chuẩn, dùng trực tiếp `getValue()` mới thể hiện đúng hợp đồng.

`name()` và `toString()` của hai enum này cũng không phải dịch vụ dịch ngôn ngữ:

```java
Month.MARCH.name();      // MARCH
DayOfWeek.MONDAY.name(); // MONDAY
```

Đây là tên hằng trong mã. Đổi chúng thành chữ thường chỉ tạo `march` hoặc `monday`, không tạo tên tiếng Việt. Không xây giao diện đa ngôn ngữ bằng `name().toLowerCase(...)`.

Nếu cần dùng vị trí từ `0` cho một mảng nội bộ, phải ghi rõ đang chuyển sang chỉ số mảng, chẳng hạn `month.getValue() - 1`. Không đưa chỉ số đó vào API hoặc dữ liệu lưu trữ rồi gọi nó là “số tháng”.

## 4. Lấy tên hiển thị bằng getDisplayName()

Cả `Month` và `DayOfWeek` đều có:

```java
String getDisplayName(TextStyle style, Locale locale);
```

Ví dụ:

```java
Locale vi = Locale.forLanguageTag("vi-VN");

String monthLabel =
        Month.MARCH.getDisplayName(TextStyle.FULL, vi);
String dayLabel =
        DayOfWeek.MONDAY.getDisplayName(TextStyle.FULL, vi);
```

`Locale.forLanguageTag("vi-VN")` lựa chọn tiếng Việt tại Việt Nam. `Locale.ENGLISH` lựa chọn tiếng Anh. Với những nhu cầu phân biệt vùng, có thể dùng locale cụ thể như `en-US` hoặc `en-GB` thay vì chỉ ngôn ngữ.

`Locale` không phải `ZoneId`. Nó điều khiển cách biểu đạt văn bản, không chuyển ngày giờ sang múi giờ khác. Muốn tên tháng của một thời điểm tại vùng nghiệp vụ, cần chuyển thời điểm sang vùng đó để lấy ngày/tháng trước, rồi mới tạo nhãn.

Không dựa ngầm vào `Locale.getDefault()` nếu giao diện đã có lựa chọn ngôn ngữ của người dùng. Môi trường máy chủ và người dùng có thể dùng hai locale khác nhau.

Đầu vào `style` và `locale` phải có giá trị hợp lệ; `null` không có nghĩa là “cứ dùng mặc định” trong hợp đồng các lời gọi này. Cũng không nên giả định tên của mọi locale luôn có ánh xạ văn bản riêng: API có thể trả biểu diễn số khi không tìm được tên tương ứng.

## 5. TextStyle: độ dài và ngữ cảnh sử dụng

[TextStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/TextStyle.html) có ba mức độ dài, mỗi mức có dạng thường và dạng độc lập:

| Dạng thường | Dạng độc lập | Mục đích |
| --- | --- | --- |
| `FULL` | `FULL_STANDALONE` | Tên đầy đủ |
| `SHORT` | `SHORT_STANDALONE` | Tên rút gọn |
| `NARROW` | `NARROW_STANDALONE` | Tên rất ngắn cho chỗ hẹp |

### 5.1. FULL, SHORT và NARROW không phải quy tắc cắt chuỗi

Trong dữ liệu tiếng Anh thông thường:

- `Month.MARCH` với `FULL` là `March`.
- Với `SHORT` là `Mar`.
- Với `NARROW` là `M`.

`SHORT` không bảo đảm đúng ba ký tự cho mọi ngôn ngữ. `NARROW` cũng không bảo đảm một ký tự Java hoặc một độ rộng hiển thị cố định trong mọi hệ chữ.

Không tự lấy `fullName.substring(0, 3)` để làm tên rút gọn. Cách viết tắt thuộc dữ liệu ngôn ngữ, không phải một phép cắt văn bản phổ quát. Với văn bản Unicode, cắt tùy tiện còn có thể làm hỏng đơn vị hiển thị hoặc tách sai ký tự.

Chọn `TextStyle` theo không gian và ý nghĩa của giao diện, rồi kiểm tra nhãn thực tế ở những locale được hỗ trợ. Nhãn dài trong tiếng Việt không nhất thiết có độ dài tương tự nhãn tiếng Anh.

### 5.2. NARROW có thể trùng nhau

Tên hẹp được thiết kế cho nơi ít chỗ, không phải để làm mã định danh. Trong tiếng Anh, January và June đều có thể hiển thị là `J`; July cũng có thể trùng.

Vì thế:

- Không dùng tên `NARROW` làm khóa của `Map` nhận diện tháng.
- Không gửi tên hẹp làm giá trị duy nhất của một lựa chọn.
- Nếu giao diện chỉ hiện một chữ, cần ngữ cảnh bổ sung hoặc tên đầy đủ cho phần mô tả truy cập.

Hai nhãn giống nhau không làm hai tháng bằng nhau. Giá trị `Month` hoặc số chuẩn vẫn phân biệt chúng.

### 5.3. STANDALONE là dạng độc lập, không phải kiểu chữ khác

Một số ngôn ngữ thay đổi dạng tên tháng khi đứng trong một ngày đầy đủ so với khi đứng riêng làm tiêu đề hoặc mục chọn. Tiếng Anh thường không thể hiện khác biệt nên nếu chỉ thử tiếng Anh, có thể tưởng hai dạng luôn giống nhau.

Ví dụ với dữ liệu tiếng Nga trong môi trường kiểm chứng:

- `Month.MARCH.getDisplayName(TextStyle.FULL, ru)` cho `марта`, dạng gắn với ngữ cảnh ngày.
- `Month.MARCH.getDisplayName(TextStyle.FULL_STANDALONE, ru)` cho `март`, dạng độc lập.

Đó là khác biệt ngôn ngữ, không phải yêu cầu đổi chữ hoa, chữ đậm hay kích thước phông. Với danh sách chọn tháng hoặc tiêu đề tháng đứng riêng, dạng `STANDALONE` có thể phù hợp hơn. Khi định dạng cả ngày, nên để bộ định dạng ngày áp dụng ngữ cảnh tương ứng.

`TextStyle.FULL.asStandalone()` cho dạng độc lập cùng mức độ dài; `asNormal()` chuyển ngược về dạng thường. Các phương thức này không dịch chuỗi đã tạo sẵn; chúng chọn kiểu dùng khi lấy nhãn.

## 6. Chương trình Java 17+ đầy đủ

Lưu thành `DatePartDisplayDemo.java`:

```java
import java.time.DateTimeException;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.Month;
import java.time.Year;
import java.time.YearMonth;
import java.time.format.TextStyle;
import java.util.Locale;

public class DatePartDisplayDemo {
    static void invalid(String label, Runnable operation) {
        try {
            operation.run();
        } catch (DateTimeException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2024, 3, 18);
        Month month = date.getMonth();
        DayOfWeek day = date.getDayOfWeek();
        Locale vi = Locale.forLanguageTag("vi-VN");

        System.out.println("month value = " + month.getValue());
        System.out.println("month ordinal = " + month.ordinal());
        System.out.println("month enum name = " + month.name());
        System.out.println("date month value = " + date.getMonthValue());
        System.out.println("year-month value = "
                + YearMonth.from(date).getMonthValue());
        System.out.println("year value = " + Year.from(date).getValue());

        System.out.println("day value = " + day.getValue());
        System.out.println("day ordinal = " + day.ordinal());
        System.out.println("month of 3 = " + Month.of(3));
        System.out.println("day of 1 = " + DayOfWeek.of(1));

        System.out.println("month en full = "
                + month.getDisplayName(TextStyle.FULL, Locale.ENGLISH));
        System.out.println("month en short = "
                + month.getDisplayName(TextStyle.SHORT, Locale.ENGLISH));
        System.out.println("month en narrow = "
                + month.getDisplayName(TextStyle.NARROW, Locale.ENGLISH));
        System.out.println("month vi full = "
                + month.getDisplayName(TextStyle.FULL, vi));
        System.out.println("day vi full = "
                + day.getDisplayName(TextStyle.FULL, vi));
        System.out.println("day en full = "
                + day.getDisplayName(TextStyle.FULL, Locale.ENGLISH));
        System.out.println("day en short = "
                + day.getDisplayName(TextStyle.SHORT, Locale.ENGLISH));

        Locale ru = Locale.forLanguageTag("ru");
        System.out.println("month ru contextual = "
                + month.getDisplayName(TextStyle.FULL, ru));
        System.out.println("month ru standalone = "
                + month.getDisplayName(TextStyle.FULL_STANDALONE, ru));

        String january = Month.JANUARY.getDisplayName(
                TextStyle.NARROW, Locale.ENGLISH);
        String june = Month.JUNE.getDisplayName(
                TextStyle.NARROW, Locale.ENGLISH);
        System.out.println("January narrow = " + january);
        System.out.println("June narrow = " + june);
        System.out.println("narrow collision = " + january.equals(june));

        invalid("month zero", () -> Month.of(0));
        invalid("day eight", () -> DayOfWeek.of(8));
        System.out.println("original date = " + date);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 DatePartDisplayDemo.java
java DatePartDisplayDemo
```

Stdout sau được kiểm chứng trên môi trường OpenJDK 24 với dữ liệu locale của môi trường đó. Mã chỉ dùng API tương thích Java 17:

```text
month value = 3
month ordinal = 2
month enum name = MARCH
date month value = 3
year-month value = 3
year value = 2024
day value = 1
day ordinal = 0
month of 3 = MARCH
day of 1 = MONDAY
month en full = March
month en short = Mar
month en narrow = M
month vi full = tháng 3
day vi full = Thứ Hai
day en full = Monday
day en short = Mon
month ru contextual = марта
month ru standalone = март
January narrow = J
June narrow = J
narrow collision = true
month zero -> DateTimeException
day eight -> DateTimeException
original date = 2024-03-18
```

Các giá trị số theo hợp đồng ISO là phần ổn định của ví dụ. Cách viết tên địa phương, dấu câu hoặc viết tắt có thể thay đổi theo dữ liệu locale và phiên bản môi trường Java. Khi chạy trên một JDK khác, khác biệt nhãn cần được xem xét theo dữ liệu ngôn ngữ, không tự kết luận phép tính lịch bị sai.

Nếu terminal hiện ô vuông hoặc ký tự lỗi ở các dòng tiếng Việt/tiếng Nga, hãy kiểm tra mã hóa đầu ra và phông của terminal. Đó không phải bằng chứng `getValue()` hoặc quy tắc xác định tháng/thứ đã thay đổi.

## 7. Tách giá trị lưu trữ khỏi nhãn giao diện

Một mục chọn tháng có thể có dạng:

```java
record MonthOption(int value, String label) {}
```

Đây là bản ghi minh họa cho dữ liệu giao diện. `value` giữ số tháng chuẩn, còn `label` là tên theo ngôn ngữ và kiểu hiển thị đang chọn.

Ví dụ tạo danh sách, giả sử đã có `locale` và các import tương ứng:

```java
List<MonthOption> options = Arrays.stream(Month.values())
        .map(month -> new MonthOption(
                month.getValue(),
                month.getDisplayName(
                        TextStyle.FULL_STANDALONE, locale)))
        .toList();
```

Cần `java.util.List` và `java.util.Arrays` cho đoạn này. Mã tạo danh sách theo thứ tự tháng; không sắp xếp theo bảng chữ cái của nhãn.

Khi đổi ngôn ngữ từ VI sang EN, tạo lại nhãn theo locale mới nhưng giữ `value`. Lựa chọn tháng 3 vẫn là tháng 3; nó không nên mất lựa chọn chỉ vì chữ `tháng 3` đổi thành `March`.

Đối với API hoặc dữ liệu lưu:

- Dùng số tháng `1..12` nếu hợp đồng chọn số.
- Dùng mã enum nếu hợp đồng công bố rõ mã đó.
- Dùng `YearMonth` hoặc biểu diễn năm–tháng khi cần xác định một kỳ cụ thể, không chỉ tháng trong năm.
- Không dùng nhãn dịch làm mã định danh lâu dài.

Nếu lưu bộ nhớ đệm cho nhãn, khóa cần phản ánh giá trị, `TextStyle` và `Locale`. Chỉ dùng số tháng làm khóa sẽ khiến nhãn tiếng Việt bị tái sử dụng nhầm cho người dùng tiếng Anh hoặc ngược lại.

## 8. Khi cần định dạng cả ngày

`getDisplayName` phù hợp khi lấy riêng tên tháng hoặc tên thứ. Khi muốn một chuỗi gồm cả thứ, ngày, tháng và năm, dùng `DateTimeFormatter` để các thành phần được định dạng cùng ngữ cảnh.

Ví dụ minh họa với `date` và `vi` đã khai báo:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("EEEE, d MMMM uuuu", vi);
String formattedDate = date.format(formatter);
```

Đoạn này cần `java.time.format.DateTimeFormatter`. Các ký hiệu quan trọng:

| Ký hiệu | Vai trò |
| --- | --- |
| `EEEE` | Tên thứ đầy đủ |
| `d` | Ngày trong tháng |
| `MMMM` | Tên tháng đầy đủ trong ngữ cảnh định dạng |
| `LLLL` | Tên tháng đầy đủ theo dạng độc lập |
| `uuuu` | Năm theo lịch mở rộng |

Không tự ghép `getDisplayName(FULL_STANDALONE, ...)` vào mọi chuỗi ngày rồi cho rằng đúng ngữ pháp cho tất cả ngôn ngữ. Dạng độc lập hữu ích ở tiêu đề riêng, còn một ngày đầy đủ có ngữ cảnh khác.

Việc ghép chuỗi theo một mẫu cố định cũng khác với yêu cầu chọn thứ tự ngày/tháng theo quy ước vùng. Khi ứng dụng cần định dạng ngày theo phong cách địa phương đầy đủ, có thể dùng các khả năng định dạng địa phương của `DateTimeFormatter`; đó là bước trình bày tiếp theo, không thay đổi dữ liệu ngày gốc.

## 9. Số chuẩn, thứ tự hiển thị và ngày đầu tuần

Một lịch giao diện có thể muốn bắt đầu bằng Chủ nhật. Điều đó không làm `DayOfWeek.SUNDAY.getValue()` đổi từ `7` thành `1`.

Có ba quyết định riêng:

1. Giá trị số của thứ theo ISO.
2. Thứ tự sắp các cột trong giao diện.
3. Tên hiển thị của từng cột theo locale.

Để xếp từ một ngày đầu tuần đã chọn, có thể duyệt bảy lần bằng `DayOfWeek.plus` và tạo nhãn cho từng thứ:

```java
DayOfWeek firstDay = DayOfWeek.SUNDAY;

for (int index = 0; index < 7; index++) {
    DayOfWeek day = firstDay.plus(index);
    String label = day.getDisplayName(TextStyle.SHORT, locale);
    // Dung day.getValue() lam gia tri ISO, label de hien thi.
}
```

Đây là đoạn minh họa cho cách tổ chức, với `locale` được chọn trước. Cột đầu là Chủ nhật nhưng giá trị ISO của cột đó vẫn là `7`. Nếu nhận thứ đầu tuần từ cấu hình địa phương, hãy xác định cấu hình riêng thay vì suy ra từ tên nhãn.

Tương tự, thay đổi ngôn ngữ giao diện không tự xác định thứ Bảy hoặc Chủ nhật là ngày nghỉ. Lịch làm việc là chính sách nghiệp vụ khác; tên hiển thị không chứa quy tắc ngày nghỉ.

## 10. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách làm phù hợp |
| --- | --- | --- |
| Dùng `ordinal()` làm số tháng | Tháng 1 thành 0 | Dùng `getValue()` |
| Coi `DayOfWeek.of(1)` là Chủ nhật | Sai thứ | Đọc rõ quy ước ISO |
| Dùng trực tiếp số `Calendar.DAY_OF_WEEK` cho `DayOfWeek.of` | Trộn quy ước đánh số | Chuyển đổi có chủ đích |
| Dùng `name()` làm nhãn dịch | Chỉ hiện tên hằng tiếng Anh | Dùng `getDisplayName` |
| Cắt ba ký tự từ tên đầy đủ để viết tắt | Sai ngôn ngữ hoặc Unicode | Chọn `TextStyle.SHORT` |
| Dùng `NARROW` làm mã duy nhất | Nhãn tháng có thể trùng | Giữ enum hoặc số chuẩn |
| Dùng locale mặc định của máy cho mọi người dùng | Sai ngôn ngữ giao diện | Truyền locale của người dùng |
| Coi locale là múi giờ | Lấy sai ngày/tháng gần ranh giới | Chọn zone trước, locale sau |
| Dùng dạng độc lập trong mọi ngữ cảnh | Có thể sai ngữ pháp | Chọn dạng theo cách sử dụng |
| Lưu nhãn thay cho dữ liệu tháng | Khó đổi ngôn ngữ và so sánh | Tách value khỏi label |

## 11. Tự kiểm chứng và thực hành

1. Duyệt `Month.values()` và in `getValue()`. Kiểm tra đủ các số `1..12`, không có `0`.
2. Duyệt `DayOfWeek.values()`. Xác nhận thứ Hai là `1`, Chủ nhật là `7` và các giá trị không đổi khi chỉ thay locale của nhãn.
3. So sánh `name()`, `getDisplayName(FULL, vi)` và `getDisplayName(FULL, Locale.ENGLISH)` cho cùng một tháng.
4. Tạo danh sách 12 mục chọn có số chuẩn và nhãn. Đổi ngôn ngữ nhưng giữ nguyên mục đã chọn.
5. Tìm nhãn `NARROW` bị trùng trong tiếng Anh. Giải thích tại sao nhãn hẹp vẫn có ích trong một lịch đã có ngữ cảnh, nhưng không phù hợp làm mã định danh.
6. So sánh `FULL` và `FULL_STANDALONE` với tiếng Anh rồi với tiếng Nga. Ghi lại rằng việc hai dạng giống nhau ở một locale không chứng minh chúng giống nhau ở mọi locale.
7. Thử `Month.of(0)`, `Month.of(13)` và `DayOfWeek.of(8)`. Các đầu vào sai phải bị báo lỗi thay vì tự sửa.
8. Tạo thứ tự cột bắt đầu từ Chủ nhật và vẫn giữ số ISO của từng cột. Không thay `getValue()` bằng chỉ số cột.
9. Nếu hệ thống nhận một `Instant`, mô tả hai bước cần thực hiện trước khi hiện tên tháng cho người dùng: chọn vùng để xác định tháng, rồi chọn locale để lấy nhãn.
10. Thiết kế kiểm chứng: kiểm tra cứng giá trị số theo hợp đồng; chỉ so sánh nhãn địa phương chính xác khi đã cố định môi trường dữ liệu locale cần dùng.

Khi tách được số chuẩn, hằng enum và nhãn theo locale, chương trình có thể đổi ngôn ngữ hoặc cách trình bày mà vẫn giữ nguyên ý nghĩa của ngày tháng.
