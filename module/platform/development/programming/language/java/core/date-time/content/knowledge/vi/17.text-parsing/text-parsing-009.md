# Đọc vị trí lỗi từ DateTimeParseException

## 1. Từ “ngày không hợp lệ” đến thông tin chẩn đoán có ích

Khi đọc một chuỗi ngày giờ thất bại, chỉ báo “sai định dạng” thường chưa đủ để người dùng hoặc lập trình viên biết cần sửa gì. Với `java.time`, `DateTimeParseException` mang theo **chuỗi đang được phân tích** và **chỉ số nơi bộ phân tích phát hiện lỗi**.

Ví dụ, với mẫu `uuuu-MM-dd`, chuỗi `2026/10/25` có dấu `/` ở nơi mẫu đòi dấu `-`. Vị trí được báo là chỉ số 4:

```text
chỉ số: 0123456789
chuỗi:  2026/10/25
            ^
```

Chỉ số này bắt đầu từ 0. Nó là một đầu mối để tìm lỗi, nhưng không luôn xác định duy nhất ký tự cần sửa. Với ngày không tồn tại như `2023-02-29`, các trường đã được đọc thành công; lỗi chỉ xuất hiện khi kết hợp chúng thành một ngày. Trường hợp đó có thể được báo tại đầu chuỗi, dù các chữ số năm không sai.

Bài này tập trung vào cách đọc thông tin ngoại lệ và trình bày vị trí một cách đúng nghĩa, thay vì đoán nguyên nhân chỉ từ con số.

## 2. Những thông tin cần lấy khi bắt ngoại lệ

| Phương thức | Dữ liệu nhận được | Cách sử dụng |
|---|---|---|
| `getParsedString()` | Chuỗi mà bộ phân tích đang đọc | Đối chiếu đúng nguồn gắn với chỉ số lỗi |
| `getErrorIndex()` | Chỉ số nơi phát hiện lỗi | Đánh dấu vị trí hoặc đưa vào báo cáo chẩn đoán |
| `getMessage()` | Mô tả chi tiết của ngoại lệ | Đọc để hiểu nguyên nhân trong quá trình gỡ lỗi |
| `getCause()` | Nguyên nhân gốc, nếu có | Tìm thêm ngữ cảnh, nhất là lỗi khi giải quyết các trường |

Ví dụ minh họa trong một phương thức Java:

```java
try {
    LocalDate.parse(text, formatter);
} catch (DateTimeParseException e) {
    String parsed = e.getParsedString();
    int index = e.getErrorIndex();
    String detail = e.getMessage();
    Throwable cause = e.getCause();
    // Dùng dữ liệu này để tạo thông báo hoặc hỗ trợ gỡ lỗi.
}
```

Đoạn trên chỉ minh họa cách lấy dữ liệu: `text` và `formatter` phải được truyền hoặc khai báo ở ngữ cảnh sử dụng. Chương trình độc lập có ở phần 5.

Không cần phân tích ngược `getMessage()` để tìm chỉ số: đã có `getErrorIndex()`. Cũng không coi toàn bộ thông điệp tiếng Anh của JDK là một giao thức ổn định để phân loại lỗi bằng cách so khớp chuỗi. Khi cần thông báo tiếng Việt, giữ thông điệp kỹ thuật cho chẩn đoán và viết lời hướng dẫn phù hợp với hợp đồng đầu vào của ứng dụng.

## 3. Đọc chỉ số đúng cách

### Chỉ số bắt đầu từ 0, không phải số cột bắt đầu từ 1

Với chuỗi ASCII một dòng `2026/10/25`, `getErrorIndex() == 4` trỏ tới dấu `/` đầu tiên. Nếu giao diện hiển thị số thứ tự vị trí bắt đầu từ 1, có thể mô tả là vị trí thứ 5, nhưng cần ghi rõ quy ước.

Không báo “vị trí 4” rồi đặt con trỏ vào ký tự thứ tư theo cách đếm của người dùng. Hãy thống nhất thuật ngữ như “chỉ số 4, tính từ 0” hoặc chuyển đổi nhất quán cho giao diện.

### Chỉ số có thể nằm ngay sau ký tự cuối cùng

Với đầu vào `2026-10-`, phần ngày chưa xuất hiện. Bộ phân tích có thể báo chỉ số 8, bằng độ dài chuỗi:

```text
2026-10-
        ^
```

Đây là vị trí kết thúc đầu vào, không phải một ký tự đang tồn tại để gọi `charAt(8)`. Chuỗi rỗng cũng có thể báo chỉ số 0, đồng thời bằng độ dài 0.

Khi cần lấy ký tự ở vị trí lỗi, phải kiểm tra `0 <= index && index < parsed.length()`. Nếu chỉ muốn đặt con trỏ tại ranh giới sau chuỗi thì trường hợp `index == parsed.length()` vẫn có ý nghĩa. Kiểm tra giới hạn trước khi dùng chỉ số giúp phần báo lỗi không tự ném thêm ngoại lệ.

### Chỉ số thuộc chuỗi Java, không phải cột hiển thị tổng quát

Chỉ số chuỗi trong Java tính theo các đơn vị mã UTF-16. Với các ví dụ số và dấu ASCII, một đơn vị tương ứng một ký tự nhìn thấy, nên có thể tạo dòng con trỏ bằng `" ".repeat(index)`.

Với emoji, ký tự tổ hợp, tab hoặc chuỗi nhiều dòng, một chỉ số không nhất thiết tương ứng một ô rộng trên màn hình. Để tô sáng trong giao diện, hãy dùng cơ chế chọn đoạn của thành phần nhập liệu và quy ước chỉ số mà nó yêu cầu. Nếu cần số dòng/cột, phải chuyển đổi từ chỉ số trên đúng chuỗi, thay vì coi nó trực tiếp là số cột.

## 4. Vị trí phát hiện lỗi khác với nguyên nhân nghiệp vụ

Xét bộ định dạng nghiêm ngặt `uuuu-MM-dd` dùng trong chương trình ở phần sau:

| Đầu vào | Chỉ số quan sát | Cách đọc đúng |
|---|---|---|
| `2026/10/25` | `4` | Dấu phân cách không khớp tại đây |
| `2026-XX-25` | `5` | Bộ phân tích không đọc được trường tháng bắt đầu tại đây |
| `2026-10-` | `8` | Đầu vào kết thúc trước khi có đủ trường ngày |
| `2026-10-25extra` | `10` | Ngày đã đọc xong nhưng còn phần dư |
| `2023-02-29` | `0` | Lỗi khi kết hợp trường thành ngày; không được kết luận năm bị sai cú pháp |
| Chuỗi rỗng | `0` | Không có dữ liệu để đọc ngay từ đầu |

Các chỉ số trên gắn với **bộ định dạng, kiểu kết quả và cách phân tích cụ thể trong ví dụ**. Thay mẫu, phần tùy chọn hoặc cách gọi có thể làm thay đổi vị trí phát hiện. Một trường chứa nhiều ký tự cũng có thể được báo ở đầu trường, không phải chính ký tự cuối cùng gây vấn đề.

Có hai loại tình huống cần phân biệt:

- **Lỗi đọc hình thức:** ký tự, số lượng chữ số, tên tháng hoặc dấu phân cách không khớp.
- **Lỗi giải quyết trường:** đã đọc được các số nhưng chúng không tạo thành ngày/giờ hợp lệ, hoặc chưa đủ thông tin để tạo kiểu kết quả yêu cầu.

Không thể suy ra hai loại này chỉ bằng quy tắc “chỉ số 0 là sai năm, chỉ số 5 là sai tháng”. Cần đọc thêm thông điệp, nguyên nhân nếu có và cấu hình bộ định dạng.

Ví dụ, thiếu kỷ nguyên khi dùng `yyyy` với `ResolverStyle.STRICT` có thể khiến việc tạo `LocalDate` thất bại dù các số là một ngày quen thuộc. Trong mẫu ngày ISO thông thường, dùng `uuuu` để biểu diễn trường năm trực tiếp; đừng tự đổi ngày người dùng nhập chỉ vì lỗi được báo ở chỉ số 0.

## 5. Chương trình đọc và đánh dấu vị trí lỗi

Lưu đoạn sau vào `ParseErrorPositionDemo.java`. Mã dùng Java 17 trở lên, không cần thư viện ngoài. Phần đánh dấu bằng dấu `^` được thiết kế cho các chuỗi ASCII một dòng trong ví dụ.

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.Locale;

public class ParseErrorPositionDemo {
    private static final DateTimeFormatter FORMAT = DateTimeFormatter
            .ofPattern("uuuu-MM-dd", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT);

    public static void main(String[] args) {
        for (String text : new String[]{
                "2026-10-25", "2026/10/25", "2026-XX-25",
                "2026-10-", "2026-10-25extra", "2023-02-29", ""
        }) {
            inspect(text);
        }
    }

    private static void inspect(String text) {
        try {
            LocalDate date = LocalDate.parse(text, FORMAT);
            System.out.println("OK " + date);
        } catch (DateTimeParseException e) {
            String parsed = e.getParsedString();
            int index = e.getErrorIndex();
            System.out.println("ERROR index=" + index
                    + " length=" + parsed.length());
            System.out.println(parsed);

            if (index >= 0 && index <= parsed.length()) {
                System.out.println(" ".repeat(index) + "^");
                System.out.println(index == parsed.length()
                        ? "position=end-of-input"
                        : "position=UTF-16 index " + index);
            } else {
                System.out.println("position=outside-input");
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac ParseErrorPositionDemo.java
java ParseErrorPositionDemo
```

Kết quả chuẩn; các khoảng trắng trước dấu `^` và dòng trống gần cuối là có chủ đích:

```text
OK 2026-10-25
ERROR index=4 length=10
2026/10/25
    ^
position=UTF-16 index 4
ERROR index=5 length=10
2026-XX-25
     ^
position=UTF-16 index 5
ERROR index=8 length=8
2026-10-
        ^
position=end-of-input
ERROR index=10 length=15
2026-10-25extra
          ^
position=UTF-16 index 10
ERROR index=0 length=10
2023-02-29
^
position=UTF-16 index 0
ERROR index=0 length=0

^
position=end-of-input
```

Chương trình dùng `ResolverStyle.STRICT` để ngày 29/02/2023 thực sự gây lỗi. Nếu giữ mặc định `SMART` của `ofPattern`, trường hợp ấy có thể được điều chỉnh về 28/02 và không đi vào nhánh `catch`. Khi kiểm tra cách báo lỗi, luôn xác nhận chính sách phân tích đang dùng.

`LocalDate.parse(text, FORMAT)` yêu cầu xử lý hết chuỗi. Nhờ vậy, phần `extra` không bị lặng lẽ bỏ qua. Những API phân tích cấp thấp có `ParsePosition` có hợp đồng khác; không suy ra rằng chúng luôn tạo cùng ngoại lệ hoặc cùng cách báo phần dư.

Nhánh `outside-input` là cách phòng vệ của hàm trình bày trước một chỉ số không dùng được. Chương trình này không tạo ra trường hợp đó; không nên thay mọi chỉ số lạ thành 0 rồi báo rằng ký tự đầu tiên sai.

## 6. Gắn vị trí với đúng phiên bản của đầu vào

Giả sử lớp tiếp nhận gọi `strip()` để bỏ khoảng trắng hai đầu trước khi đọc ngày. Ngoại lệ sẽ lưu chuỗi đã truyền vào bộ phân tích, tức chuỗi sau khi cắt khoảng trắng. Chỉ số của nó không còn trực tiếp trỏ đến cùng vị trí trong chuỗi gốc.

Ví dụ:

```text
Chuỗi gốc:       "  2026/10/25  "
Chuỗi được đọc:  "2026/10/25"
Chỉ số lỗi:      4 trên chuỗi được đọc
```

Muốn tô sáng trên ô nhập gốc, cần ánh xạ vị trí qua phép biến đổi, hoặc hiển thị đúng chuỗi `getParsedString()` bên cạnh lỗi. Với phép biến đổi phức tạp như đổi Unicode hay xóa ký tự giữa chuỗi, không thể luôn chỉ cộng một độ lệch cố định.

Nếu thử nhiều bộ định dạng, mỗi ngoại lệ còn thuộc một lần thử cụ thể. Khi báo lỗi, giữ cả mẫu đã thử và chuỗi thực sự được phân tích, thay vì chỉ giữ ngoại lệ cuối rồi khẳng định đó là nguyên nhân duy nhất. Số chỉ số lớn hơn không tự chứng minh một bộ định dạng là lựa chọn đúng cho dữ liệu.

## 7. Cách chuyển thông tin kỹ thuật thành thông báo dễ hiểu

Với biểu mẫu đã quy định ngày `uuuu-MM-dd`, một thông báo chung hữu ích có thể là: “Không đọc được ngày. Hãy nhập theo dạng 2026-10-25 và dùng một ngày có thật.” Khi có thông tin chắc chắn về lỗi dấu phân cách, có thể bổ sung vị trí để người dùng đối chiếu.

Giữ riêng các dữ liệu như tên trường, mẫu dự kiến, chỉ số lỗi và mô tả kỹ thuật để hỗ trợ gỡ lỗi. Không cần đưa toàn bộ stack trace ra giao diện nhập liệu. Nếu chuỗi nhập là dữ liệu cá nhân, chỉ lưu phần cần thiết theo chính sách của ứng dụng; vị trí lỗi vẫn có thể được báo mà không phải ghi toàn bộ dữ liệu vào mọi bản ghi nhật ký.

Bắt đúng `DateTimeParseException` quanh thao tác phân tích giúp tránh biến các lỗi lập trình khác thành thông báo “ngày sai”. Chẳng hạn, `null` cần được kiểm tra như đầu vào thiếu; không mặc định nó luôn sinh cùng ngoại lệ và có chỉ số lỗi để tô sáng.

Sau khi phân tích thành công, kiểm tra nghiệp vụ như ngày bắt đầu không được sau ngày kết thúc. Một thất bại nghiệp vụ kiểu đó không nhất thiết thuộc về một ký tự trong chuỗi, vì vậy không gán tùy tiện chỉ số 0 rồi tạo cảm giác đây là lỗi cú pháp.

## 8. Tự thực hành

Thêm ba đầu vào sau vào chương trình và dự đoán trước khi chạy:

1. `2026-10-25 `: chuỗi có một khoảng trắng cuối, nên thao tác đọc toàn bộ chuỗi báo phần dư bắt đầu ở chỉ số 10.
2. `2026-10`: thiếu dấu phân cách và trường ngày tiếp theo, vị trí phát hiện là chỗ chuỗi kết thúc, chỉ số 7.
3. `2024-02-29`: là ngày nhuận hợp lệ nên không có ngoại lệ.

Với mỗi lỗi, trả lời riêng: vị trí được báo thuộc chuỗi nào, có ký tự tại vị trí ấy hay đã hết chuỗi, và dữ liệu hiện có đã đủ để kết luận nguyên nhân hay chưa. Ba câu trả lời này giúp dùng `getErrorIndex()` như thông tin chẩn đoán chính xác thay vì một phép đoán.

Tham khảo: [DateTimeParseException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeParseException.html) và [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) trong Java SE 21.
