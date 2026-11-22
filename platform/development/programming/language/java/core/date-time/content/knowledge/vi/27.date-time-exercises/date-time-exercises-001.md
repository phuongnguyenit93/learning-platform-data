# Xây dựng bộ nhập ngày nghiêm ngặt và thông báo lỗi rõ ràng

## 1. Một bộ nhập ngày phải có hợp đồng trước khi có parser

Chấp nhận chuỗi rồi tạo được một đối tượng chưa đủ. Bộ nhập cần nói rõ định dạng nào được nhận, ngày có phải tồn tại thật trong lịch hay không, và khi thất bại người dùng cần sửa điều gì.

Trong bài thực hành này, chọn hợp đồng cụ thể:

- Nhập đúng `dd/MM/uuuu`: hai chữ số ngày, hai chữ số tháng, bốn chữ số năm, ngăn bằng `/`.
- Chỉ nhận chữ số ASCII `0–9`, không có khoảng trắng đầu/cuối hoặc ký tự dư.
- Ngày phải hợp lệ trong lịch ISO; không tự điều chỉnh 31/4 thành 30/4 hoặc 29/2 năm thường thành 28/2.
- Miền năm của ứng dụng là 0001–9999.
- Thành công trả `LocalDate`; thất bại trả mã lỗi và thông báo có thể hiểu được.

Đây là hợp đồng của bài, không phải giới hạn chung của `LocalDate`: kiểu này còn hỗ trợ năm 0, năm âm và miền lớn hơn. Chọn miền năm riêng giúp ví dụ không âm thầm áp đặt ràng buộc nghiệp vụ vào thư viện.

## 2. Tách ba lớp kiểm tra

```text
Chuỗi nhập
  → có dữ liệu và đúng hình thức?
  → có phải ngày tồn tại trong lịch?
  → có thỏa quy tắc ứng dụng?
  → LocalDate hoặc lỗi rõ ràng
```

| Lớp | Ví dụ lỗi | Phản hồi phù hợp |
| --- | --- | --- |
| Bắt buộc | `null`, chuỗi trống | Yêu cầu nhập ngày |
| Hình thức | `1/2/2024`, `2024-02-01` | Chỉ rõ định dạng được nhận |
| Ngày lịch | `31/04/2024`, `29/02/2023` | Báo ngày không tồn tại |
| Miền ứng dụng | `01/01/0000` | Báo giới hạn năm |

Regex có thể kiểm tra hình thức, nhưng không nên tự gánh toàn bộ quy tắc tháng, ngày và năm nhuận. `LocalDate` cùng một formatter phân giải nghiêm ngặt đảm nhận việc kiểm tra lịch. [LocalDate.parse](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDate.html#parse(java.lang.CharSequence,java.time.format.DateTimeFormatter))

## 3. Chọn uuuu và ResolverStyle.STRICT

`DateTimeFormatter.ofPattern` mặc định dùng cách phân giải `SMART`. Với ngày trong tháng, cách đó có thể sửa một số giá trị vượt ngày cuối tháng thành ngày cuối hợp lệ. Bộ nhập yêu cầu không sửa ngày nên phải chọn `withResolverStyle(ResolverStyle.STRICT)`.

`STRICT` kiểm tra sự tương thích của năm, tháng và ngày; `LENIENT` cho phép diễn giải tràn theo quy tắc, còn `SMART` chọn một số điều chỉnh hợp lý. Chúng không thay thế nhau trong một hợp đồng nhập liệu. [ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html)

Trong mẫu ngày ISO này, dùng `uuuu` cho năm. `yyyy` là năm trong niên đại; khi phân giải nghiêm ngặt và không có thông tin niên đại, nó có thể không đủ để tạo ngày như người viết mong đợi. Cũng không dùng `YYYY`: đó là năm theo tuần.

`Locale.ROOT` làm rõ parser này không theo quy cách ngôn ngữ mặc định của máy. Hợp đồng chữ số và độ rộng được kiểm tra riêng ở đầu vào. Formatter là đối tượng bất biến và an toàn luồng, nên có thể giữ một hằng dùng chung. [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)

## 4. Không trả ngày giả hoặc thông báo kỹ thuật nguyên văn

Nếu đầu vào sai, không trả `LocalDate.now()`, epoch hoặc một ngày cuối tháng đã sửa. Những giá trị đó có thể tiếp tục được lưu như dữ liệu thật.

Cũng không cần đưa nguyên văn stack trace hoặc `DateTimeParseException.getMessage()` cho người dùng. Có thể giữ mã lỗi ổn định cho mã gọi và thông báo tiếng Việt cho giao diện:

| Mã | Thông báo |
| --- | --- |
| `REQUIRED` | Vui lòng nhập ngày. |
| `FORMAT` | Nhập đúng dd/MM/uuuu, ví dụ 29/02/2024. |
| `INVALID_DATE` | Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận. |
| `YEAR_RANGE` | Năm phải nằm trong khoảng 0001–9999. |

Mã lỗi và câu hiển thị là hai thành phần khác nhau. Giao diện có thể dịch câu mà không cần đổi logic xử lý hoặc phân tích chuỗi thông báo.

## 5. Chương trình Java hoàn chỉnh

Lưu thành `StrictDateInputDemo.java`. Hai kiểu kết quả tách biệt tránh trường hợp đối tượng vừa có giá trị thành công vừa chứa lỗi.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;
import java.util.regex.Pattern;

public class StrictDateInputDemo {
    private static final Pattern SHAPE =
            Pattern.compile("[0-9]{2}/[0-9]{2}/[0-9]{4}");
    private static final DateTimeFormatter FORMATTER =
            DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT)
                    .withResolverStyle(ResolverStyle.STRICT);

    enum ErrorCode { REQUIRED, FORMAT, INVALID_DATE, YEAR_RANGE }
    sealed interface Result permits Parsed, Rejected {}
    record Parsed(LocalDate date) implements Result {}
    record Rejected(ErrorCode code, String message) implements Result {}

    static Result parseDate(String raw) {
        if (raw == null || raw.isBlank()) {
            return new Rejected(ErrorCode.REQUIRED, "Vui lòng nhập ngày.");
        }
        if (!SHAPE.matcher(raw).matches()) {
            return new Rejected(ErrorCode.FORMAT,
                    "Nhập đúng dd/MM/uuuu, ví dụ 29/02/2024.");
        }

        final LocalDate date;
        try {
            date = LocalDate.parse(raw, FORMATTER);
        } catch (DateTimeParseException ex) {
            return new Rejected(ErrorCode.INVALID_DATE,
                    "Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận.");
        }

        if (date.getYear() < 1 || date.getYear() > 9999) {
            return new Rejected(ErrorCode.YEAR_RANGE,
                    "Năm phải nằm trong khoảng 0001–9999.");
        }
        return new Parsed(date);
    }

    static void show(String raw) {
        String label = raw == null ? "<null>" : "\"" + raw + "\"";
        Result result = parseDate(raw);
        if (result instanceof Parsed parsed) {
            System.out.println(label + " -> OK: " + parsed.date());
        } else if (result instanceof Rejected rejected) {
            System.out.println(label + " -> " + rejected.code() + ": "
                    + rejected.message());
        }
    }

    public static void main(String[] args) {
        String[] inputs = {
                null, "", "29/02/2024", "29/02/2023", "31/04/2024",
                "1/2/2024", "2024-02-29", "29/02/2024 ",
                "01/01/0000", "29/02/2000", "29/02/2100", "01/13/2024"
        };
        for (String input : inputs) {
            show(input);
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên, lưu tệp bằng UTF-8:

```shell
javac -encoding UTF-8 --release 17 StrictDateInputDemo.java
java "-Dfile.encoding=UTF-8" StrictDateInputDemo
```

Stdout chính xác:

```text
<null> -> REQUIRED: Vui lòng nhập ngày.
"" -> REQUIRED: Vui lòng nhập ngày.
"29/02/2024" -> OK: 2024-02-29
"29/02/2023" -> INVALID_DATE: Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận.
"31/04/2024" -> INVALID_DATE: Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận.
"1/2/2024" -> FORMAT: Nhập đúng dd/MM/uuuu, ví dụ 29/02/2024.
"2024-02-29" -> FORMAT: Nhập đúng dd/MM/uuuu, ví dụ 29/02/2024.
"29/02/2024 " -> FORMAT: Nhập đúng dd/MM/uuuu, ví dụ 29/02/2024.
"01/01/0000" -> YEAR_RANGE: Năm phải nằm trong khoảng 0001–9999.
"29/02/2000" -> OK: 2000-02-29
"29/02/2100" -> INVALID_DATE: Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận.
"01/13/2024" -> INVALID_DATE: Ngày không tồn tại; hãy kiểm tra ngày, tháng và năm nhuận.
```

`matches()` yêu cầu toàn chuỗi khớp hình thức; `LocalDate.parse` tạo ngày từ toàn bộ đầu vào. Tháng 13 có đúng hình thức hai chữ số nhưng sai miền lịch, nên rơi vào `INVALID_DATE`, không phải `FORMAT`.

Chuỗi toàn khoảng trắng được xem là thiếu dữ liệu; một chuỗi có ngày kèm khoảng trắng là sai hình thức theo hợp đồng đã chọn. Nếu sản phẩm muốn cho phép khoảng trắng bao quanh, hãy thêm một bước chuẩn hóa được công bố và kiểm tra rõ ràng thay vì thay đổi âm thầm.

## 6. Phân loại lỗi đủ rõ nhưng không đoán quá mức

Một lỗi khi phân giải ngày có thể do quan hệ giữa nhiều trường. Ví dụ 29/2 chỉ sai trong một số năm. Thông báo “ngày không tồn tại; kiểm tra ngày, tháng và năm nhuận” chính xác hơn việc luôn kết luận một ký tự cụ thể sai.

`DateTimeParseException` có chuỗi đã phân tích và chỉ số lỗi, hữu ích để chẩn đoán. Tuy nhiên chỉ số đó không luôn tương ứng với một ô ngày/tháng/năm duy nhất cần sửa, nhất là lỗi ở giai đoạn kết hợp các trường. Không hứa “ký tự tại vị trí này chắc chắn là nguyên nhân” cho mọi lỗi lịch. [DateTimeParseException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeParseException.html)

Bộ parser bắt đúng ngoại lệ phân tích chuỗi tại ranh giới đầu vào. Không bắt mọi `Exception` rồi gắn tất cả thành “ngày sai”, vì lỗi cấu hình formatter hoặc lỗi lập trình cần được phát hiện riêng.

Thứ tự kiểm tra cũng là một phần của phản hồi: ví dụ `31/02/0000` thất bại khi kiểm tra ngày trước khi xét giới hạn năm. Nếu ứng dụng cần báo nhiều lỗi cùng lúc, phải thiết kế chính sách tổng hợp lỗi riêng; không suy ngược từ một thông báo đơn.

## 7. Quy tắc nghiệp vụ đặt sau khi đã có LocalDate

Parser chung không nên tự cấm mọi ngày tương lai: ngày hẹn có thể ở tương lai, còn ngày sinh thường không được ở tương lai. Sau khi nhận `Parsed`, lớp nghiệp vụ kiểm tra theo ngữ cảnh.

Đoạn minh họa trong một phương thức:

```java
LocalDate birthDate = parsedDate; // Giá trị đã parse thành công.
LocalDate today = LocalDate.of(2025, 6, 15);
if (birthDate.isAfter(today)) {
    // Trả mã nghiệp vụ riêng: ngày sinh không được sau hôm nay.
}
```

Trong ứng dụng thật, xác định hôm nay bằng đồng hồ và múi giờ nghiệp vụ rõ ràng; khi kiểm tra dùng một ngày cố định hoặc `Clock` được truyền vào. Không đưa phụ thuộc đồng hồ vào parser nếu parser chỉ chịu trách nhiệm đọc một ngày.

Không cần đổi ngày vừa parse sang `Instant`: đầu vào chưa có giờ hoặc múi giờ. Giữ `LocalDate` qua các tầng mà ý nghĩa vẫn là ngày lịch.

## 8. Kiểm tra trước khi đưa vào luồng nhập thực tế

- Ngày thường hợp lệ, ngày cuối tháng và 29/2 năm nhuận.
- Ngày không tồn tại, tháng 00/13, ngày 00 và ngoại lệ năm thế kỷ như 2000/2100.
- Thiếu số 0, dấu phân cách khác, ký tự dư, khoảng trắng và chữ số ngoài hợp đồng.
- Năm 0000, năm 0001 và 9999 để xác nhận ranh giới ứng dụng.
- Chạy dưới locale mặc định khác để bảo đảm hợp đồng không đổi.

Có thể dùng cùng parser cho nhiều hàng của tệp nhập và trả lỗi gắn với vị trí hàng/trường. Phần đó là lớp điều phối đầu vào; parser ngày vẫn chỉ nhận chuỗi và trả một kết quả.

Nếu muốn chấp nhận nhiều định dạng, công bố danh sách và cách xử lý mơ hồ. Đừng thử cả `dd/MM/uuuu` và `MM/dd/uuuu` rồi lấy kết quả đầu tiên cho `01/02/2024`: hai cách hiểu đều có thể là ngày hợp lệ.

## 9. Bài mở rộng

1. Cho phép khoảng trắng bao quanh nhưng vẫn cấm khoảng trắng bên trong ngày; giữ parser lịch nghiêm ngặt.
2. Thêm một lớp kiểm tra khoảng ngày được phép, với mã lỗi khác lỗi định dạng.
3. Kiểm tra `31/12/9999` và `01/01/0001` thành công, `01/01/0000` thất bại theo hợp đồng.
4. Thay `STRICT` bằng `SMART` trong một thí nghiệm riêng để quan sát vì sao bộ nhập không được tự sửa ngày.

Kết quả cần giữ là một ngày đúng hoặc một lỗi có ý nghĩa; không có trường hợp đầu vào sai được âm thầm biến thành một ngày khác.