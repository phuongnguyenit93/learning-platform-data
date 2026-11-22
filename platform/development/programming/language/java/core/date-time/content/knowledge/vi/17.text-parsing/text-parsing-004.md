# Kiểm tra ngày không hợp lệ và sự khác biệt giữa các chế độ

## 1. Ngày nhập sai phải bị từ chối hay được điều chỉnh?

Giả sử người dùng nhập `2025-02-31` cho ngày giao hàng. Chuỗi có đúng bốn chữ số năm, hai chữ số tháng và hai chữ số ngày; nhưng tháng 2 năm 2025 không có ngày 31. Nếu chương trình nhận chuỗi này rồi lưu thành ngày 28 tháng 2 hoặc ngày 3 tháng 3, dữ liệu đã thay đổi so với nội dung người dùng nhập.

Trong `java.time`, cách xử lý những trường ngày–tháng như vậy phụ thuộc vào **chế độ phân giải** `ResolverStyle`. Có ba lựa chọn: `STRICT`, `SMART`, `LENIENT`. Chọn chế độ là chọn quy tắc xử lý dữ liệu, không chỉ là chọn mức độ dễ chịu của thông báo lỗi.

Cần tách hai câu hỏi:

1. Chuỗi có đúng cú pháp mà bộ định dạng nhận hay không?
2. Những con số đọc được có kết hợp thành ngày hợp lệ, hoặc được điều chỉnh thành ngày nào?

Theo [Java SE 21 — ResolverStyle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/ResolverStyle.html), việc đọc chuỗi và việc phân giải các trường là hai giai đoạn; `ResolverStyle` điều khiển giai đoạn phân giải. Vì vậy, đổi sang `LENIENT` không có nghĩa mọi chuỗi sai đều được chấp nhận.

## 2. Phân biệt lỗi cú pháp với ngày không tồn tại

Với mẫu `uuuu-MM-dd`, hãy xét các đầu vào:

| Đầu vào | Vấn đề cần xét |
| --- | --- |
| `2025/02/28` | Dấu phân cách không đúng mẫu |
| `2025-2-28` | Phần tháng không đủ độ rộng của mẫu đang dùng |
| `2025-02-29` | Hình thức đúng, nhưng 2025 không phải năm nhuận |
| `2025-04-31` | Hình thức đúng, nhưng tháng 4 chỉ có 30 ngày |
| `2025-13-10` | Tháng vượt phạm vi thông thường |
| `2024-02-29` | Ngày tồn tại trong lịch ISO |

Một biểu thức chính quy chỉ kiểm tra hình thức như bốn chữ số, dấu `-`, hai chữ số không đủ để quyết định ngày tồn tại. Giới hạn ngày phụ thuộc cả tháng lẫn năm. Ngay cả kiểm tra `1 <= day <= 31` cũng chưa phát hiện được ngày 31 tháng 4.

Trong bài này, kết quả được phân tích thành `LocalDate` theo lịch ISO. Không suy rộng các chi tiết về ngày cuối tháng sang mọi hệ lịch hoặc mọi cách tổ hợp trường ngày khác nhau.

## 3. Ba chế độ xử lý năm–tháng–ngày

### `STRICT`: yêu cầu ngày thực sự tồn tại

`STRICT` phù hợp khi ý nghĩa của thao tác là xác nhận nguyên vẹn ngày đã nhập. Ví dụ, `2025-02-29` phải thất bại thay vì được sửa; `2024-02-29` phải thành công. Ngoài tháng trong phạm vi 1–12 và ngày trong phạm vi thông thường, tổ hợp năm–tháng–ngày phải hợp lệ.

Nếu nhập sai ngày sinh, ngày hóa đơn hoặc lịch hẹn và yêu cầu nghiệp vụ là báo lỗi để nhập lại, hãy cấu hình rõ chế độ này. Bản thân `STRICT` chưa kiểm tra được những quy định như “không cho đặt lịch trong quá khứ”: một ngày có thể tồn tại trong lịch nhưng không được phép trong nghiệp vụ.

### `SMART`: có thể kéo ngày về cuối tháng

Với các trường năm, tháng, ngày của lịch ISO, `SMART` có thể nhận ngày nằm trong khoảng 1–31 nhưng vượt ngày cuối cùng của tháng rồi chọn ngày cuối tháng. Các quy tắc phân giải này được mô tả trong [Java SE 21 — IsoChronology.resolveDate()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/chrono/IsoChronology.html#resolveDate(java.util.Map,java.time.format.ResolverStyle)).

Các ví dụ của bài cho thấy:

```text
2025-02-29 → 2025-02-28
2025-02-31 → 2025-02-28
2025-04-31 → 2025-04-30
```

Không hiểu `SMART` là “chấp nhận mọi số rồi sửa”: tháng 13, ngày 0 hoặc ngày 32 vẫn bị từ chối trong cách phân giải đang xét. Điểm quan trọng khi đánh giá dữ liệu là **parse thành công có thể đi kèm việc đổi ngày**.

### `LENIENT`: cho phép cộng dồn phần vượt phạm vi

Với cùng dạng năm–tháng–ngày, `LENIENT` xử lý phần tháng/ngày như lượng dịch chuyển. Có thể hình dung bắt đầu từ ngày 1 tháng 1 của năm đã đọc, dịch `tháng - 1` tháng, rồi dịch `ngày - 1` ngày.

Chẳng hạn, `2025-02-31` tương ứng ngày 1 tháng 2 năm 2025 cộng 30 ngày, nên thành `2025-03-03`. Tháng 13 của năm 2025 đi sang tháng 1 năm 2026. Ngày 0 của tháng 1 năm 2025 lùi về ngày cuối tháng 12 năm 2024.

Chỉ dùng cách xử lý này khi nguồn dữ liệu có chủ đích biểu diễn phần vượt hoặc ứng dụng thật sự cho phép điều chỉnh. Nó không chứng minh rằng chuỗi đầu vào đã mô tả một ngày hợp lệ theo nghĩa thông thường. `LENIENT` cũng không đảm bảo luôn thành công: cú pháp, dữ liệu thiếu hoặc vượt giới hạn biểu diễn vẫn có thể gây lỗi.

## 4. Thí nghiệm có thể chạy: cùng đầu vào, ba kết quả

Lưu mã sau vào `InvalidDateModesDemo.java`. Chương trình dùng Java 17 trở lên, không có thư viện ngoài:

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class InvalidDateModesDemo {
    private static String parse(String text, DateTimeFormatter formatter) {
        try {
            return LocalDate.parse(text, formatter).toString();
        } catch (DateTimeParseException ex) {
            return "ERROR";
        }
    }

    public static void main(String[] args) {
        DateTimeFormatter base = DateTimeFormatter
                .ofPattern("uuuu-MM-dd", Locale.ROOT);
        System.out.println("pattern default = " + base.getResolverStyle());
        System.out.println("ISO default = "
                + DateTimeFormatter.ISO_LOCAL_DATE.getResolverStyle());

        String[] inputs = {
            "2024-02-29", "2025-02-29", "2025-02-31",
            "2025-04-31", "2025-02-32", "2025-13-10",
            "2025-00-10", "2025-01-00", "2025-2-03"
        };
        System.out.println("input | STRICT | SMART | LENIENT");
        for (String input : inputs) {
            System.out.println(input + " | "
                    + parse(input, base.withResolverStyle(ResolverStyle.STRICT))
                    + " | "
                    + parse(input, base.withResolverStyle(ResolverStyle.SMART))
                    + " | "
                    + parse(input, base.withResolverStyle(ResolverStyle.LENIENT)));
        }

        DateTimeFormatter yearOfEra = DateTimeFormatter
                .ofPattern("yyyy-MM-dd", Locale.ROOT)
                .withResolverStyle(ResolverStyle.STRICT);
        System.out.println("yyyy strict = " + parse("2025-02-28", yearOfEra));
        System.out.println("uuuu strict = " + parse("2025-02-28",
                base.withResolverStyle(ResolverStyle.STRICT)));
        System.out.println("ISO invalid = "
                + parse("2025-02-29", DateTimeFormatter.ISO_LOCAL_DATE));
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 InvalidDateModesDemo.java
java InvalidDateModesDemo
```

Kết quả:

```text
pattern default = SMART
ISO default = STRICT
input | STRICT | SMART | LENIENT
2024-02-29 | 2024-02-29 | 2024-02-29 | 2024-02-29
2025-02-29 | ERROR | 2025-02-28 | 2025-03-01
2025-02-31 | ERROR | 2025-02-28 | 2025-03-03
2025-04-31 | ERROR | 2025-04-30 | 2025-05-01
2025-02-32 | ERROR | ERROR | 2025-03-04
2025-13-10 | ERROR | ERROR | 2026-01-10
2025-00-10 | ERROR | ERROR | 2024-12-10
2025-01-00 | ERROR | ERROR | 2024-12-31
2025-2-03 | ERROR | ERROR | ERROR
yyyy strict = ERROR
uuuu strict = 2025-02-28
ISO invalid = ERROR
```

`ERROR` là chuỗi do hàm hỗ trợ trong ví dụ tự trả về khi gặp `DateTimeParseException`, không phải kết quả của thư viện. Hàm này giúp so sánh ma trận; trong mã ứng dụng, cần giữ hoặc chuyển đổi lỗi thành kết quả nhập liệu có ý nghĩa, không tiếp tục coi `ERROR` là ngày hợp lệ.

Quan sát ba hàng quan trọng:

- `2025-02-31`: `SMART` dừng tại cuối tháng 2, còn `LENIENT` chuyển sang tháng 3. Hai chế độ không điều chỉnh theo cùng cách.
- `2025-02-32`: ngay cả `SMART` cũng từ chối, cho thấy giới hạn 1–31 khác với giới hạn ngày thật của từng tháng.
- `2025-2-03`: cả ba thất bại vì bộ đọc cú pháp của mẫu đang dùng yêu cầu tháng có hai chữ số. Chỉ thay `ResolverStyle` không nới lỏng quy tắc này.

## 5. Hai bẫy khiến kết quả kiểm tra khác dự kiến

### Không phải bộ định dạng nào cũng mặc định `STRICT`

Hai dòng đầu của chương trình cho thấy bộ định dạng tạo bằng `ofPattern("uuuu-MM-dd", Locale.ROOT)` mặc định là `SMART`, trong khi `ISO_LOCAL_DATE` là `STRICT`. Do đó, hai cách viết sau có thể xử lý ngày sai khác nhau dù trông như cùng đọc định dạng năm–tháng–ngày:

```java
// Minh họa trong một phương thức; đã import các lớp java.time và java.time.format.
LocalDate.parse("2025-02-29"); // DateTimeParseException
LocalDate.parse("2025-02-29",
        DateTimeFormatter.ofPattern("uuuu-MM-dd")); // 2025-02-28
```

Khi dùng mẫu tự tạo để xác nhận ngày người dùng nhập, hãy chỉ rõ `.withResolverStyle(ResolverStyle.STRICT)` thay vì suy đoán mặc định.

`DateTimeFormatter` là bất biến. `withResolverStyle()` trả về bộ định dạng kết quả; lời gọi không sửa đối tượng cũ. Cần gán hoặc sử dụng giá trị trả về:

```java
DateTimeFormatter input = DateTimeFormatter
        .ofPattern("uuuu-MM-dd", java.util.Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT);
```

### `yyyy` và `uuuu` mang ý nghĩa khác nhau

Trong mẫu, `u` biểu diễn năm trực tiếp, còn `y` biểu diễn năm trong một kỷ nguyên. Với `yyyy-MM-dd` và `STRICT`, chuỗi `2025-02-28` không cung cấp kỷ nguyên; vì thế ví dụ không tạo được `LocalDate` dù ngày 28 tháng 2 năm 2025 có thật. Đổi sang `uuuu-MM-dd` giải quyết đúng nhu cầu đọc năm ISO trong bài.

Vì vậy, khi bật `STRICT` rồi thấy mọi ngày đều bị từ chối, hãy kiểm tra mẫu và các trường còn thiếu trước khi kết luận chế độ này quá nghiêm. Nếu đầu vào thật sự có kỷ nguyên, cần mô tả kỷ nguyên trong bộ định dạng thay vì thay đổi ý nghĩa dữ liệu. Cũng không dùng `YYYY` thay cho `uuuu`: `Y` là năm theo tuần.

## 6. Không trộn lẫn các tầng kiểm tra

Một quy trình nhập ngày rõ ràng có thể đi theo thứ tự:

```text
Xác định dữ liệu có bắt buộc không
              ↓
Đọc đúng mẫu và tiêu thụ toàn bộ chuỗi
              ↓
Phân giải thành LocalDate theo chế độ đã chọn
              ↓
Kiểm tra giới hạn nghiệp vụ trên ngày kết quả
```

Ví dụ, ứng dụng đặt lịch cần vừa từ chối `2025-02-31` vừa từ chối ngày nằm ngoài khoảng nhận lịch. `STRICT` giải quyết yêu cầu đầu; phép so sánh `isBefore()`/`isAfter()` trên ngày đã phân tích giải quyết yêu cầu sau. Không cần tự viết lại thuật toán năm nhuận hoặc bảng số ngày mỗi tháng.

Lời gọi trực tiếp `LocalDate.of(year, month, day)` cũng yêu cầu ngày tồn tại và không nhận tham số `ResolverStyle`. Các chế độ trong bài thuộc việc phân giải dữ liệu do bộ định dạng đọc được; không phải công tắc toàn cục làm mọi cách tạo ngày trở nên linh hoạt.

Các cấu hình như `DateTimeFormatterBuilder.parseLenient()` hoặc `parseStrict()` điều khiển cách đọc cú pháp ở phần tương ứng của bộ dựng. Chúng khác với `withResolverStyle()` điều khiển phân giải trường. Nếu cần chấp nhận tháng một hoặc hai chữ số, hãy thiết kế quy tắc đọc phù hợp; đừng trông chờ `ResolverStyle.LENIENT` tự thay mẫu `MM`.

## 7. Áp dụng và kiểm tra lại quyết định

Khi yêu cầu là kiểm tra ngày nhập nguyên vẹn, cấu hình `STRICT` rồi bắt `DateTimeParseException` ở ranh giới nhập liệu để yêu cầu sửa dữ liệu. Nếu dùng `SMART` hoặc `LENIENT`, phải hiểu giá trị kết quả có thể khác đầu vào; quyết định điều chỉnh cần xuất phát từ yêu cầu nguồn dữ liệu hoặc nghiệp vụ.

Không dùng cách “parse theo `LENIENT`, không lỗi tức là ngày hợp lệ” cho một biểu mẫu cần phát hiện ngày sai. Cũng không cần parse rồi so sánh `toString()` với chuỗi gốc để thay thế mọi kiểm tra: định dạng xuất có thể khác định dạng nhập. Hãy chọn chế độ và hợp đồng định dạng ngay từ đầu.

Với lỗi phân tích, thông báo nguyên văn của ngoại lệ hữu ích khi chẩn đoán nhưng không nên trở thành điều kiện điều khiển chương trình. Ngày không tồn tại, thiếu trường do mẫu `yyyy` và sai dấu phân cách có thể cùng biểu hiện bằng `DateTimeParseException`; cần đọc ngữ cảnh đầu vào và cấu hình để sửa đúng nguyên nhân.

Bài tập: dự đoán ba chế độ cho `2024-02-30`. `STRICT` từ chối; `SMART` cho `2024-02-29`; `LENIENT` cho `2024-03-01`. Sau đó thử `2025-04-00`: hai chế độ đầu từ chối, còn `LENIENT` cho `2025-03-31`. Giải thích được hai trường hợp này là bạn đã phân biệt việc giữ ngày nhập, kéo về cuối tháng và cộng dồn phần vượt.
