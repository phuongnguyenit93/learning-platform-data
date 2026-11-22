# ResolverStyle.STRICT, SMART và LENIENT

## 1. Đọc được các con số chưa có nghĩa là có một ngày hợp lệ

Chuỗi `2023-02-29` có hình thức năm-tháng-ngày rất rõ: năm là 2023, tháng là 2, ngày trong tháng là 29. Tuy nhiên, năm 2023 không nhuận nên ngày đó không tồn tại trong lịch ISO. Ứng dụng phải quyết định **từ chối**, **điều chỉnh về cuối tháng** hay **cho phần vượt tràn sang tháng sau**.

`ResolverStyle` là lựa chọn chính sách khi Java kết hợp các trường đã đọc thành một ngày/giờ. Hiểu lựa chọn này giúp tránh tình trạng bộ phân tích trả về một giá trị hợp lệ nhưng khác ngày người dùng đã nhập.

Ba lựa chọn là:

| Chế độ | Ý định | Với `2023-02-29` trong lịch ISO |
|---|---|---|
| `STRICT` | Chỉ tạo ngày khi các trường thực sự hợp lệ cùng nhau | Báo lỗi |
| `SMART` | Áp dụng điều chỉnh thích hợp theo từng trường | Thành `2023-02-28` |
| `LENIENT` | Cho phép tính toán với giá trị vượt phạm vi theo quy tắc của trường | Thành `2023-03-01` |

Không nên hiểu `SMART` là “luôn đúng ý người dùng” hay `LENIENT` là “chuỗi nào cũng nhận”. Chúng là những hợp đồng khác nhau, phải chọn theo chức năng đang xây dựng.

## 2. Hai giai đoạn của việc phân tích chuỗi

Để biết `ResolverStyle` can thiệp ở đâu, tách quy trình thành hai giai đoạn:

```text
Chuỗi đầu vào
    |
    v
1. Đọc văn bản theo mẫu
   "2023-02-29" -> YEAR=2023, MONTH_OF_YEAR=2, DAY_OF_MONTH=29
    |
    v
2. Kết hợp và kiểm tra các trường theo ResolverStyle
    |
    +--> LocalDate hợp lệ
    |
    +--> DateTimeParseException
```

**Giai đoạn 1** quan tâm đến ký tự, dấu phân cách, độ rộng trường, tên tháng và các thành phần có trong mẫu. **Giai đoạn 2** giải quyết quan hệ giữa các trường: tháng đó có bao nhiêu ngày, năm có nhuận hay không, giờ vượt 24 có được chuyển sang ngày sau hay không.

`DateTimeFormatter.withResolverStyle(...)` cấu hình giai đoạn 2. Nó không tự đổi dấu `/` thành `-`, không tự xóa khoảng trắng, không đổi tên tháng sang ngôn ngữ khác và không tự nới mọi quy định số chữ số trong giai đoạn 1.

Điều này giải thích tại sao một bộ định dạng mẫu `uuuu-MM-dd` dùng `LENIENT` vẫn có thể từ chối `2023/02/09` hoặc `2023-2-9`.

## 3. Cấu hình một cách tường minh

Ví dụ khai báo trong một phương thức Java:

```java
DateTimeFormatter base = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT);
DateTimeFormatter strict = base.withResolverStyle(ResolverStyle.STRICT);
DateTimeFormatter smart = base.withResolverStyle(ResolverStyle.SMART);
DateTimeFormatter lenient = base.withResolverStyle(ResolverStyle.LENIENT);
```

`DateTimeFormatter` bất biến; mỗi lời gọi `withResolverStyle` trả về một bộ định dạng mới. Gọi rồi bỏ giá trị trả về không làm thay đổi `base`. Có thể tái sử dụng các bộ định dạng đã tạo mà không cần khóa đồng bộ.

Bộ định dạng tạo bằng `ofPattern` mặc định dùng `SMART`. Trong khi đó, các hằng ISO thông dụng như `DateTimeFormatter.ISO_LOCAL_DATE` sử dụng `STRICT`; đừng suy ra rằng mọi bộ định dạng đều có cùng mặc định. Có thể kiểm tra lựa chọn hiện tại bằng `getResolverStyle()`.

Dùng như sau:

```java
LocalDate valid = LocalDate.parse("2024-02-29", strict);
```

Các đoạn trên cần import từ `java.time`, `java.time.format` và `java.util`. Chương trình đầy đủ có ở phần 7.

## 4. STRICT: giữ nguyên ý nghĩa ngày đã nhập hoặc báo lỗi

Trong lịch ISO, `STRICT` kiểm tra giá trị từng trường và tính hợp lệ khi ghép chúng lại. Ngày 29/02/2024 hợp lệ; ngày 29/02/2023 không hợp lệ. Nó cũng không nhận tháng 15 hoặc ngày 0.

Với đầu vào do người dùng khai báo như ngày sinh, ngày ký hợp đồng hay ngày hóa đơn, việc âm thầm chuyển một ngày không tồn tại sang ngày khác thường làm mất ý nghĩa dữ liệu. Nếu quy định của chức năng yêu cầu đúng ngày đã nhập, `STRICT` là lựa chọn phù hợp.

### Vì sao STRICT với yyyy vẫn lỗi dù ngày có thật?

Trong mẫu `yyyy-MM-dd`, ký tự `y` biểu diễn **năm trong kỷ nguyên** (`YEAR_OF_ERA`). Để xác định ngày một cách nghiêm ngặt còn cần biết kỷ nguyên (`ERA`); riêng ba trường đó có thể chưa đủ để tạo `LocalDate`.

Với ngày lịch ISO thông thường, dùng `uuuu-MM-dd`: `u` biểu diễn năm trực tiếp (`YEAR`), vì vậy không cần suy đoán kỷ nguyên. Ví dụ:

```java
DateTimeFormatter strict = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

Nếu yêu cầu thực sự cần mẫu có năm trong kỷ nguyên, cần thiết kế đủ dữ liệu như kỷ nguyên hoặc giá trị mặc định thích hợp. Đừng chữa lỗi bằng cách bỏ `STRICT` khi yêu cầu vốn cần kiểm tra nghiêm ngặt. Cũng không dùng `YYYY`: đó là năm theo tuần, không phải năm lịch đang xét.

## 5. SMART: điều chỉnh có giới hạn, tùy từng trường

Với bộ ba năm-tháng-ngày trong lịch ISO, `SMART` yêu cầu ngày trong tháng nằm trong phạm vi 1–31. Nếu con số nằm trong phạm vi đó nhưng tháng cụ thể không có ngày ấy, nó điều chỉnh về ngày cuối tháng.

Ví dụ:

- `2023-02-29` trở thành `2023-02-28`.
- `2023-04-31` trở thành `2023-04-30`.
- `2023-02-32` vẫn báo lỗi vì 32 nằm ngoài phạm vi 1–31.
- `2023-15-10` vẫn báo lỗi vì tháng 15 không hợp lệ.

Như vậy, `SMART` không phải chế độ cho mọi giá trị vượt phạm vi tràn sang đơn vị lớn hơn. Cần kiểm tra quy tắc của trường đang dùng thay vì mặc định rằng “thông minh” nghĩa là tự sửa tất cả lỗi nhập.

Một ví dụ khác là giờ `24:00`: khi phân tích cả ngày và giờ, `SMART` chấp nhận đúng mốc cuối ngày này và chuyển thành `00:00` ngày sau. Nhưng `24:30` vẫn lỗi trong `SMART`. Ví dụ chạy đầy đủ bên dưới minh họa trực tiếp khác biệt này.

Chỉ dùng sự điều chỉnh đó khi chức năng chấp nhận. Nếu cần thông báo cho người dùng rằng ngày nhập không tồn tại, `SMART` có thể che mất tín hiệu lỗi mà bạn cần.

## 6. LENIENT: tính phần vượt phạm vi thay vì chỉ kiểm tra giới hạn

Với năm-tháng-ngày ISO, có thể hình dung `LENIENT` bắt đầu ở đầu năm, cộng số tháng trừ 1, rồi cộng số ngày trừ 1. Phần vượt được cộng hoặc trừ theo lịch.

Ví dụ `2023-02-32`:

```text
2023-01-01
    + 1 tháng
= 2023-02-01
    + 31 ngày
= 2023-03-04
```

Ví dụ khác:

| Chuỗi | Kết quả LENIENT | Cách hiểu |
|---|---|---|
| `2023-02-29` | `2023-03-01` | Sau ngày 28/02 thêm 1 ngày |
| `2023-15-10` | `2024-03-10` | Tháng 15 đi sang năm sau |
| `2023-02-00` | `2023-01-31` | Ngày 0 là một ngày trước đầu tháng |

Những kết quả này có thể hữu ích khi định dạng nguồn được thiết kế để dùng giá trị vượt phạm vi như một phép tính, hoặc khi nhập dữ liệu cũ có quy tắc điều chỉnh đã thống nhất. Không nên dùng chúng như cách “bỏ qua lỗi” cho mọi dữ liệu nhập thông thường.

`LENIENT` cũng không đảm bảo luôn thành công. Văn bản vẫn phải đọc được theo mẫu; dữ liệu còn có thể thiếu trường, mâu thuẫn hoặc vượt giới hạn biểu diễn của kiểu ngày giờ.

## 7. Chương trình so sánh chạy được

Lưu đoạn sau vào `ResolverStyleDemo.java`. Mã dùng Java 17 trở lên và không cần thư viện ngoài.

```java
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ResolverStyleDemo {
    public static void main(String[] args) {
        DateTimeFormatter base =
                DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);
        System.out.println("default=" + base.getResolverStyle());
        String[] dates = {
                "2023-02-29", "2024-02-29", "2023-02-32",
                "2023-15-10", "2023-02-00"
        };

        for (String text : dates) {
            for (ResolverStyle style : ResolverStyle.values()) {
                System.out.println(style + " " + text + " -> "
                        + parseDate(text, base.withResolverStyle(style)));
            }
        }

        DateTimeFormatter strict = base.withResolverStyle(ResolverStyle.STRICT);
        DateTimeFormatter yearOfEra = DateTimeFormatter
                .ofPattern("yyyy-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        System.out.println("yyyy=" + parseDate("2024-02-29", yearOfEra));
        System.out.println("uuuu=" + parseDate("2024-02-29", strict));
        System.out.println("width=" + parseDate("2023-2-9",
                base.withResolverStyle(ResolverStyle.LENIENT)));
        System.out.println("separator=" + parseDate("2023/02/09",
                base.withResolverStyle(ResolverStyle.LENIENT)));

        DateTimeFormatter dateTime = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm", Locale.ROOT);
        for (ResolverStyle style : ResolverStyle.values()) {
            for (String time : new String[]{"24:00", "24:30"}) {
                String text = "2023-02-28 " + time;
                try {
                    LocalDateTime value = LocalDateTime.parse(
                            text, dateTime.withResolverStyle(style));
                    System.out.println(style + " " + time + " -> " + value);
                } catch (DateTimeParseException e) {
                    System.out.println(style + " " + time + " -> ERROR");
                }
            }
        }
    }

    static String parseDate(String text, DateTimeFormatter formatter) {
        try {
            return LocalDate.parse(text, formatter).toString();
        } catch (DateTimeParseException e) {
            return "ERROR";
        }
    }
}
```

Biên dịch và chạy:

```shell
javac ResolverStyleDemo.java
java ResolverStyleDemo
```

Kết quả chuẩn:

```text
default=SMART
STRICT 2023-02-29 -> ERROR
SMART 2023-02-29 -> 2023-02-28
LENIENT 2023-02-29 -> 2023-03-01
STRICT 2024-02-29 -> 2024-02-29
SMART 2024-02-29 -> 2024-02-29
LENIENT 2024-02-29 -> 2024-02-29
STRICT 2023-02-32 -> ERROR
SMART 2023-02-32 -> ERROR
LENIENT 2023-02-32 -> 2023-03-04
STRICT 2023-15-10 -> ERROR
SMART 2023-15-10 -> ERROR
LENIENT 2023-15-10 -> 2024-03-10
STRICT 2023-02-00 -> ERROR
SMART 2023-02-00 -> ERROR
LENIENT 2023-02-00 -> 2023-01-31
yyyy=ERROR
uuuu=2024-02-29
width=ERROR
separator=ERROR
STRICT 24:00 -> ERROR
STRICT 24:30 -> ERROR
SMART 24:00 -> 2023-03-01T00:00
SMART 24:30 -> ERROR
LENIENT 24:00 -> 2023-03-01T00:00
LENIENT 24:30 -> 2023-03-01T00:30
```

Trong chương trình, `ERROR` là nhãn do mã ví dụ in khi bắt `DateTimeParseException`, không phải nguyên văn thông báo của Java. Không so sánh toàn bộ thông điệp ngoại lệ trong ví dụ, vì mục tiêu là so sánh kết quả phân tích.

Các dòng `width` và `separator` cho thấy cùng một lựa chọn `LENIENT` không làm nới lỏng mẫu văn bản. Các dòng cuối dùng `LocalDateTime` để quan sát cả ngày bị chuyển sang hôm sau; nếu chỉ lấy `LocalTime`, bạn sẽ không nhìn thấy đầy đủ tác động lên ngày.

## 8. Phân biệt parseStrict/parseLenient với ResolverStyle

Tên gần giống nhau nhưng các API điều khiển khác nhau:

| API | Giai đoạn tác động | Câu hỏi trọng tâm |
|---|---|---|
| `DateTimeFormatterBuilder.parseStrict()` / `parseLenient()` | Đọc văn bản thành các trường | Mức linh hoạt khi khớp số, dấu và độ rộng theo bộ phân tích |
| `DateTimeFormatter.withResolverStyle(...)` | Giải quyết các trường thành ngày/giờ | Xử lý một bộ trường như tháng 2, ngày 29 ra sao? |
| `parseCaseInsensitive()` / `parseCaseSensitive()` | Khớp văn bản có chữ | Có phân biệt chữ hoa/thường không? |

Mặc định của builder là đọc văn bản nghiêm ngặt; mặc định của bộ định dạng tạo bằng `ofPattern` lại là giải quyết trường theo `SMART`. Hai điều này không mâu thuẫn vì thuộc hai giai đoạn khác nhau.

Nếu thiết kế đầu vào cho phép tháng/ngày một hoặc hai chữ số, hãy dùng mẫu hoặc builder phù hợp cho giai đoạn đọc. Không bật `ResolverStyle.LENIENT` để giải quyết một yêu cầu thuần về hình thức chuỗi.

Ngược lại, gọi `parseStrict()` trong builder mà không chọn chính sách giải quyết trường phù hợp chưa đủ để bảo đảm ngày 29/02 của năm không nhuận bị từ chối khi tạo `LocalDate`.

## 9. Chính sách phân tích không thay thế điều kiện nghiệp vụ

Một ngày hợp lệ theo lịch vẫn có thể không hợp lệ cho chức năng đang làm. Ví dụ, ngày hết hạn phải nằm sau ngày cấp, hoặc ngày sinh không được nằm trong tương lai. `STRICT` không biết các điều kiện ấy.

Quy trình tiếp nhận dữ liệu nên rõ ràng:

1. Xác định mẫu văn bản và ngôn ngữ được chấp nhận.
2. Chọn `ResolverStyle` theo chính sách điều chỉnh/từ chối của chức năng.
3. Phân tích thành đúng kiểu ngày giờ.
4. Kiểm tra các điều kiện nghiệp vụ trên giá trị đã tạo.
5. Nếu có điều chỉnh theo `SMART` hoặc `LENIENT`, xác định có cần cho người dùng thấy kết quả sau điều chỉnh hay không.

Khi gặp lỗi, giữ được chuỗi nguồn để báo lại ngữ cảnh. Có thể dùng `DateTimeParseException.getParsedString()` và `getErrorIndex()` để hỗ trợ chẩn đoán, nhưng không nên diễn giải mọi vị trí lỗi thành một thông báo nghiệp vụ hoàn chỉnh. Chẳng hạn, lỗi thiếu kỷ nguyên trong mẫu `yyyy` khác với việc người dùng nhập sai ngày.

Không tự thử lần lượt `STRICT`, rồi `SMART`, rồi `LENIENT` đến khi có kết quả trừ khi đó là quy tắc được chủ động thiết kế. Cách thử như vậy có thể biến ngày không tồn tại thành một ngày khác mà lớp gọi không biết.

## 10. Tự thực hành

Với cùng mẫu `uuuu-MM-dd`, dự đoán ba kết quả cho `2023-04-31` rồi chạy lại:

```text
STRICT  -> ERROR
SMART   -> 2023-04-30
LENIENT -> 2023-05-01
```

Sau đó đổi sang ngày hợp lệ `2023-04-30`: cả ba chế độ đều cho `2023-04-30`. Hãy giải thích vì sao sự khác biệt giữa các chế độ không nhất thiết xuất hiện với mọi đầu vào.

Cuối cùng, thử bỏ việc gán giá trị trả về của `withResolverStyle(STRICT)`, rồi in `base.getResolverStyle()`. Kết quả vẫn là `SMART`, giúp kiểm tra lại tính bất biến của bộ định dạng.

Tài liệu tham khảo: [ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html), [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) và [DateTimeFormatterBuilder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatterBuilder.html) trong Java SE 21.
