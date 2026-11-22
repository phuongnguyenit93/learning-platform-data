# Xác định chính sách làm sạch trước khi kiểm tra đầu vào trong Java

## 1. Vì sao phải thiết kế chính sách trước?

Một chuỗi trông giống như `"  Alice  "` không có cùng cách xử lý trong mọi trường. Với **tên hiển thị**, việc bỏ khoảng trắng ở hai đầu có thể hợp lý. Với **mã tài khoản**, khoảng trắng có thể khiến mã sai định dạng và cần bị từ chối. Với **mật khẩu**, chính khoảng trắng ấy có thể là một phần của bí mật và không được tự ý xóa.

Vì thế, câu hỏi đầu tiên không phải là dùng `strip()` hay `trim()`, mà là: **trường dữ liệu này cho phép thay đổi những ký tự nào trước khi kiểm tra tính hợp lệ?**

Sau bài học, người học có thể:

1. Phân biệt `null`, chuỗi rỗng `""`, chuỗi trắng (*blank*) và chuỗi có nội dung.
2. Hiểu `isBlank()`, `isEmpty()`, `strip()`, `trim()` cùng những giới hạn Unicode của từng API.
3. Lựa chọn thứ tự **kiểm tra thô → biến đổi được phép → kiểm tra dạng cuối**, hoặc không biến đổi nếu yêu cầu bắt buộc giữ nguyên.
4. Xây dựng hợp đồng cho tên hiển thị, mã định danh, mật khẩu và nội dung tự do.
5. Kiểm thử ký tự ẩn, dữ liệu thô quá lớn, `null`, khoảng trắng nội bộ và chuỗi Unicode.
6. Viết mã Java 17+ không làm mất dữ liệu hoặc vô tình hợp thức hóa input sai.

## 2. Bốn tình huống khác nhau: null, empty, blank, content

| Giá trị | Ý nghĩa | `isEmpty()` | `isBlank()` | `strip()` |
| --- | --- | --- | --- | --- |
| `null` | Không có đối tượng String | Ném NPE khi gọi | Ném NPE khi gọi | Ném NPE khi gọi |
| `""` | Chuỗi có độ dài 0 | `true` | `true` | `""` |
| `"   "` | Ba dấu cách ASCII | `false` | `true` | `""` |
| `"\t\n"` | Tab và newline | `false` | `true` | `""` |
| `"  Java  "` | Văn bản có khoảng trắng hai đầu | `false` | `false` | `"Java"` |
| `"A B"` | Dấu cách bên trong nội dung | `false` | `false` | `"A B"` |

`isEmpty()` chỉ kiểm tra `length() == 0`, còn `isBlank()` kiểm tra chuỗi rỗng hoặc chỉ chứa những code point được `Character.isWhitespace()` coi là whitespace. `strip()` loại whitespace này ở **hai đầu**, không tự thay đổi các ký tự ở giữa.

`String` là immutable: kết quả của `strip()` phải được gán, trả về hoặc dùng tiếp. Gọi `raw.strip();` rồi bỏ qua giá trị trả về không thay đổi `raw`.

~~~java
String raw = "  Java  ";
raw.strip();
System.out.println("[" + raw + "]");   // [  Java  ]

String clean = raw.strip();
System.out.println("[" + clean + "]"); // [Java]
~~~

Không được tự động coi `null` và `""` như nhau. Trong một API cập nhật, `null` có thể có nghĩa là xóa giá trị, `""` có thể là giá trị rỗng có chủ đích, còn thuộc tính không xuất hiện có thể mang nghĩa giữ nguyên giá trị cũ.

## 3. Phân tích mục đích từng trường dữ liệu

Một **bảng quyết định** giúp tránh sử dụng một hàm làm sạch chung cho toàn bộ ứng dụng:

| Loại trường | Làm sạch được phép | Kiểm tra hợp lệ | Điều cần tránh |
| --- | --- | --- | --- |
| Tên hiển thị | Có thể `strip()` hai đầu, NFC nếu quy định | Không blank, cấm ký tự không phù hợp, giới hạn độ dài | Tự bỏ dấu, lowercase hoặc gộp khoảng trắng nội bộ khi chưa được phép |
| Mã tài khoản chính xác | Không biến đổi, trừ khi đặc tả quy định canonicalization | Khớp regex/format đúng từng ký tự | Tự sửa mã sai thành mã hợp lệ |
| Mật khẩu | Mặc định bảo toàn input trong chính sách minh họa | Giới hạn độ dài, kiểm tra theo chính sách xác thực | `strip()`, `trim()`, đổi case, tự cắt ngắn |
| Từ khóa tìm kiếm | Có thể `strip()` hoặc gộp khoảng trắng | Blank tương ứng bỏ lọc hay báo lỗi? | Làm mất ký tự có ý nghĩa trong truy vấn |
| Ghi chú nhiều dòng | Có thể chuẩn hóa newline nếu sản phẩm cần | Giới hạn kích thước, ký tự cấm phù hợp | Xóa tab, dấu xuống dòng, thụt lề không chủ ý |
| Mã giao thức/chữ ký | Chỉ theo quy định của chuẩn | So sánh đúng biểu diễn đã thỏa thuận | Tự ý normalize làm hỏng chữ ký hoặc định danh |

Với mỗi trường, **hợp đồng** phải công bố: có chấp nhận `null` hay không; chuỗi blank được hiểu ra sao; phép biến đổi nào được phép; giới hạn kích thước theo đơn vị nào; ký tự đặc biệt được cho phép; dữ liệu cuối được lưu, tìm kiếm và hiển thị như thế nào.

Nếu nhiều tầng xử lý khác nhau, phải dùng cùng hợp đồng. Ví dụ lúc đăng ký `strip()` mã nhưng lúc đăng nhập lại so mã thô có thể tạo bất nhất khó tìm.

## 4. Thứ tự xử lý và nguyên tắc validate trên dạng đúng

Với **trường cho phép bỏ khoảng trắng đầu/cuối**, một pipeline có thể là:

~~~text
Input thô
   │
   ├─ Kiểm tra null / giới hạn kích thước thô
   ▼
Áp dụng đúng thao tác được phép
   ├─ strip()
   ├─ NFC (nếu hợp đồng yêu cầu)
   └─ chuyển đổi khác đã định nghĩa
   ▼
Kiểm tra giá trị kết quả
   ├─ blank hoặc empty?
   ├─ giới hạn độ dài sau biến đổi?
   ├─ ký tự bị cấm?
   └─ đúng định dạng nghiệp vụ?
   ▼
Dùng/lưu giá trị đã kiểm tra
~~~

Với mã phải khớp nguyên dạng hoặc mật khẩu, bỏ hẳn bước biến đổi: **đầu vào thô → kiểm tra nguyên dạng → sử dụng nguyên dạng**.

### Tại sao không chỉ kiểm tra trước khi làm sạch?

~~~java
String raw = "  A  ";
System.out.println(raw.length());         // 5
System.out.println(raw.strip().length()); // 1
~~~

Nếu tên được yêu cầu tối thiểu 3 đơn vị độ dài **sau làm sạch**, việc chỉ kiểm tra `raw.length() >= 3` là sai. Chúng ta phải kiểm tra trên giá trị thực sự sẽ lưu.

### Tại sao vẫn nên chặn kích thước thô trước khi làm sạch?

Một chuỗi chứa hàng triệu dấu cách có thể thành `""` sau `strip()`. Nếu chỉ kiểm tra độ dài cuối, hệ thống đã phải nhận và xử lý lượng dữ liệu thô lớn. Đặt hạn mức byte của request và/hoặc giới hạn số đơn vị ký tự thô ở ranh giới nhận dữ liệu, trước những phép biến đổi tốn tài nguyên.

**Không có thứ tự chung cho mọi trường.** Đối với input được phép chuẩn hóa trước, kiểm tra sau normalize là hợp lý. Với trường bắt buộc đúng cú pháp nguyên dạng, hãy từ chối ngay nếu sai. Mỗi đường đi phải được nêu rõ trong contract.

## 5. strip(), trim(), isBlank() và các kiểu khoảng trắng Unicode

Các API Java tương tự nhau nhưng không hoàn toàn trùng nhau:

- `strip()` và các biến thể `stripLeading()`, `stripTrailing()` dùng `Character.isWhitespace()`.
- `isBlank()` kiểm tra theo định nghĩa `Character.isWhitespace()`.
- `trim()` theo đặc tả cũ loại các ký tự ở đầu/cuối có giá trị code unit nhỏ hơn hoặc bằng `U+0020`.
- Các ký tự Unicode trông như dấu cách không nhất thiết được `Character.isWhitespace()` phân loại như nhau.
- Regex `\\s` của `Pattern` còn phụ thuộc cờ; không tự cho rằng nó có đúng tập ký tự của `strip()`.

| Ký tự | Mã Unicode | Lưu ý |
| --- | --- | --- |
| Dấu cách ASCII | U+0020 | `strip()` loại bỏ khi ở đầu/cuối |
| Tab, xuống dòng | U+0009, U+000A | `strip()` loại ở đầu/cuối, không xóa bên trong |
| IDEOGRAPHIC SPACE | U+3000 | `Character.isWhitespace()` trả `true` |
| NO-BREAK SPACE (NBSP) | U+00A0 | `Character.isWhitespace()` trả `false` |
| ZERO WIDTH SPACE | U+200B | Không được `isBlank()` xem là whitespace |

~~~java
System.out.println("\u3000".isBlank()); // true
System.out.println("\u00A0".isBlank()); // false
System.out.println("\u200B".isBlank()); // false
~~~

Một chuỗi gồm NBSP có thể **được coi là không blank** dù gần như không nhìn thấy. Nếu trường đơn dòng không chấp nhận NBSP hoặc zero-width, cần kiểm tra riêng theo **chính sách trường đó**, không dựa duy nhất vào `!isBlank()`.

Đừng tự động xóa toàn bộ ký tự "vô hình": một số dấu kết hợp và ký tự định dạng có ý nghĩa trong tiếng Việt hoặc văn bản quốc tế.

### Xử lý whitespace bên trong

Nếu yêu cầu gộp nhiều **dấu cách ASCII** liên tiếp thành một:

~~~java
String raw = "An   Bình";
String compact = raw.replaceAll(" +", " ");
System.out.println(compact); // An Bình
~~~

Mẫu `" +"` chỉ áp dụng dấu cách ASCII, không tự xử lý tab, NBSP hay tất cả Unicode whitespace. Nếu cần tập ký tự rộng hơn, định nghĩa và kiểm thử tập đó. Với nội dung nhiều dòng, mã nguồn, văn bản giữ thụt lề hoặc địa chỉ, gộp khoảng trắng có thể làm mất thông tin quan trọng.

## 6. Phân biệt cleaning, normalization, validation và escaping

| Việc | Ví dụ | Mục đích |
| --- | --- | --- |
| Cleaning | `strip()` | Bỏ thành phần được phép ở biên |
| Unicode normalization | `Normalizer.normalize(s, NFC)` | Thống nhất biểu diễn Unicode theo hợp đồng |
| Validation | Độ dài, ký tự cấm, mẫu hợp lệ | Quyết định chấp nhận hay từ chối |
| Output encoding | HTML escaping, SQL parameterization | Bảo vệ hệ thống khi sử dụng dữ liệu ở ngữ cảnh cụ thể |

Hai chuỗi trông gần giống nhau có thể có biểu diễn Unicode khác nhau:

~~~java
String decomposed = "Cafe\u0301";
String nfc = java.text.Normalizer.normalize(
        decomposed, java.text.Normalizer.Form.NFC);
System.out.println(decomposed.equals("Café")); // false
System.out.println(nfc.equals("Café"));        // true
~~~

NFC **không phải** bỏ dấu tiếng Việt, không phải lọc nội dung nguy hiểm và không phải bước bắt buộc cho mọi trường. Nhiều giao thức và hệ thống xác thực yêu cầu giữ nguyên dãy ký tự.

Đổi chữ hoa/thường có quy tắc phụ thuộc locale nếu dùng overload mặc định. Khi một **mã kỹ thuật** được quy định không phân biệt case, có thể dùng quy tắc canonicalization cụ thể như `toLowerCase(Locale.ROOT)`; với tên người, mật khẩu hoặc nội dung có ý nghĩa, không tự động chuyển đổi chỉ để tiện so sánh.

Làm sạch đầu vào không thay thế việc dùng **parameterized SQL**, escape đúng ngữ cảnh đầu ra, kiểm soát đường dẫn, hạn mức tài nguyên hay phân quyền. Cũng không biến mọi chuỗi sai thành chuỗi an toàn.

## 7. Ba chính sách cụ thể: tên hiển thị, mã tài khoản và mật khẩu

### 7.1. Tên hiển thị

Hợp đồng **minh họa**:

1. Từ chối `null` và input thô dài hơn 200 UTF-16 code units.
2. Áp dụng `strip()` hai đầu và chuẩn hóa `NFC`.
3. Từ chối chuỗi sau xử lý là blank.
4. Từ chối ký tự điều khiển ISO, NBSP (U+00A0) và ZERO WIDTH SPACE (U+200B) theo quy tắc riêng của ví dụ.
5. Giới hạn tối đa 40 Unicode code points sau làm sạch.
6. Giữ nguyên các dấu cách giữa các từ, kể cả nhiều dấu cách liên tiếp.

Quy tắc cấm NBSP/zero-width và giữ lại khoảng trắng nội bộ là quyết định **minh họa**, có thể không phù hợp với mọi ngôn ngữ hay sản phẩm. Một hệ thống hỗ trợ tên đa ngôn ngữ cần cân nhắc grapheme cluster, dấu kết hợp và quy tắc nhập liệu thực tế.

### 7.2. Mã tài khoản

Giả sử quy định mã gồm 3–12 ký tự ASCII: bắt đầu bằng chữ thường, các ký tự sau có thể là chữ thường, số hoặc dấu gạch dưới:

~~~java
boolean valid = input != null
        && input.matches("[a-z][a-z0-9_]{2,11}");
~~~

`"alice"` hợp lệ, còn `" alice "`, `"Alice"`, `"a b"` phải bị từ chối. Không âm thầm `strip()` hoặc `toLowerCase()` để biến mã sai thành đúng, trừ khi đặc tả sản phẩm chủ đích cho phép và mọi tầng dùng cùng quy tắc.

### 7.3. Mật khẩu

Trong ví dụ minh họa này, chính sách mật khẩu là:

- Giữ nguyên từng ký tự nhập vào, kể cả khoảng trắng đầu/cuối.
- Không `trim()`, `strip()`, lowercase, bỏ dấu hoặc chuẩn hóa Unicode.
- Kiểm tra độ dài đã quy định mà không tự cắt ngắn.
- Dùng đúng biểu diễn đã chấp nhận trong quá trình đăng ký và xác thực.

Một hệ thống xác thực cụ thể có thể quy định chính sách Unicode riêng; nếu dùng chuẩn hóa, phải thiết kế đồng bộ cho toàn bộ vòng đời thông tin xác thực và nêu rõ cho người dùng.

## 8. Ví dụ hoàn chỉnh, chạy trên Java 17+

Tạo file **`InputCleaningPolicyDemo.java`**:

~~~java
import java.text.Normalizer;

public class InputCleaningPolicyDemo {
    record Result(boolean valid, String value, String reason) {}

    static Result displayName(String raw) {
        if (raw == null) {
            return new Result(false, null, "NULL");
        }
        if (raw.length() > 200) {
            return new Result(false, null, "RAW_TOO_LONG");
        }

        String clean = Normalizer.normalize(
                raw.strip(), Normalizer.Form.NFC);

        if (clean.isBlank()) {
            return new Result(false, null, "BLANK");
        }

        boolean forbidden = clean.codePoints().anyMatch(cp ->
                Character.isISOControl(cp)
                || cp == 0x00A0
                || cp == 0x200B);

        if (forbidden) {
            return new Result(false, null, "DISALLOWED_CHARACTER");
        }
        if (clean.codePointCount(0, clean.length()) > 40) {
            return new Result(false, null, "TOO_LONG");
        }
        return new Result(true, clean, "OK");
    }

    static Result accountId(String raw) {
        if (raw == null) {
            return new Result(false, null, "NULL");
        }
        if (!raw.matches("[a-z][a-z0-9_]{2,11}")) {
            return new Result(false, null, "FORMAT");
        }
        return new Result(true, raw, "OK");
    }

    static Result password(String raw) {
        if (raw == null) {
            return new Result(false, null, "NULL");
        }
        // Quy tắc minh họa: 8..64 đơn vị UTF-16.
        if (raw.length() < 8 || raw.length() > 64) {
            return new Result(false, null, "LENGTH");
        }
        return new Result(true, raw, "OK");
    }

    public static void main(String[] args) {
        Result name = displayName(" \u3000An   Bình\u3000 ");
        System.out.println("name.valid=" + name.valid());
        System.out.println("name.value=[" + name.value() + "]");
        System.out.println("name.spacesKept="
                + name.value().contains("   "));

        Result id = accountId(" alice ");
        System.out.println("id.valid=" + id.valid());
        System.out.println("id.reason=" + id.reason());

        Result secret = password(" pass1234 ");
        System.out.println("password.valid=" + secret.valid());
        System.out.println("password.kept="
                + " pass1234 ".equals(secret.value()));

        Result blank = displayName(" \t\u3000 ");
        System.out.println("blank.reason=" + blank.reason());

        Result newline = displayName(" A\nB ");
        System.out.println("newline.reason=" + newline.reason());

        Result nbsp = displayName("\u00A0");
        System.out.println("nbsp.reason=" + nbsp.reason());
        System.out.println("nbsp.isBlank=" + "\u00A0".isBlank());
        System.out.println("ideographic.isBlank="
                + "\u3000".isBlank());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 InputCleaningPolicyDemo.java
java InputCleaningPolicyDemo
~~~

Stdout:

~~~text
name.valid=true
name.value=[An   Bình]
name.spacesKept=true
id.valid=false
id.reason=FORMAT
password.valid=true
password.kept=true
blank.reason=BLANK
newline.reason=DISALLOWED_CHARACTER
nbsp.reason=DISALLOWED_CHARACTER
nbsp.isBlank=false
ideographic.isBlank=true
~~~

**Diễn giải:** tên được bỏ dấu cách và IDEOGRAPHIC SPACE ở hai đầu, nhưng ba dấu cách ở giữa vẫn nguyên. Mã chứa padding bị từ chối. Mật khẩu giả được giữ nguyên; chương trình chỉ in trạng thái, không in bí mật. Input toàn whitespace trả về `BLANK`. Newline nội bộ và NBSP bị kiểm tra riêng; `isBlank()` vốn không coi NBSP là whitespace.

`record Result` có sẵn trong Java 17. Trong dự án thực tế, có thể thay bằng kiểu kết quả validation của framework, nhưng phải giữ quy tắc quan trọng: **không sử dụng `value` nếu `valid` là `false`**.

## 9. Trường tùy chọn, PATCH và trạng thái vắng mặt

Trong API cập nhật, có ít nhất ba trạng thái khác nhau:

1. **Không gửi thuộc tính:** thường có thể nghĩa là giữ nguyên giá trị đã lưu.
2. **Gửi thuộc tính có `null`:** có thể nghĩa là yêu cầu xóa hoặc bị từ chối.
3. **Gửi thuộc tính `""` / blank:** có thể nghĩa là xóa, lưu rỗng hoặc báo lỗi.

Không thể suy ra thuộc tính có **xuất hiện trong request hay không** chỉ từ một tham chiếu `String` đã bị chuyển về `null`. Hãy giữ trạng thái hiện diện riêng hoặc thiết kế DTO/PATCH model phù hợp.

Đoạn minh họa (giả sử hai biến đã được giải quyết từ request):

~~~java
if (!fieldPresent) {
    // Không sửa nickname cũ.
} else if (input == null) {
    // Áp dụng chính sách cho null được gửi rõ ràng.
} else {
    // Làm sạch/kiểm tra chuỗi theo hợp đồng.
}
~~~

Đây là một ví dụ *fragment*, không phải chương trình độc lập. Ý nghĩa từng trường hợp phải nằm trong hợp đồng API và có bài kiểm thử riêng.

## 10. Giới hạn độ dài và Unicode: đừng dùng từ "ký tự" mơ hồ

Các đơn vị đo khác nhau:

- `String.length()`: số **UTF-16 code units**.
- `String.codePointCount(0, length())`: số **Unicode code points**.
- `getBytes(StandardCharsets.UTF_8).length`: số **byte UTF-8**.
- Số **grapheme clusters**: gần với đơn vị ký tự người dùng nhìn thấy, có thể chứa nhiều code points.

Ví dụ:

~~~java
String emoji = "😀";
System.out.println(emoji.length()); // 2
System.out.println(
        emoji.codePointCount(0, emoji.length())); // 1
System.out.println(emoji.getBytes(
        java.nio.charset.StandardCharsets.UTF_8).length); // 4
~~~

Nếu sản phẩm nói "40 ký tự", đội phát triển phải chỉ ra đó là code points, grapheme hay đơn vị khác. Kiểm tra raw byte để chặn payload lớn có mục đích khác giới hạn độ dài tên hiển thị. Cần tối thiểu một vài test có tiếng Việt tổ hợp và emoji để tránh nhầm `char` với ký tự hiển thị.

## 11. Lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `strip()` trên `null` | `NullPointerException` | Kiểm tra và xác định contract cho `null` |
| Gọi `strip()` nhưng không nhận kết quả | Giá trị nguồn không đổi | Gán hoặc `return` giá trị mới |
| Chỉ dùng `isEmpty()` | Dấu cách được coi là dữ liệu không rỗng | Dùng blank rule phù hợp |
| Cho rằng `isBlank()` phát hiện mọi ký tự "vô hình" | NBSP/zero-width lọt qua | Quy định tập ký tự được phép |
| Tự động `strip()` mật khẩu | Thay bí mật của người dùng | Bảo toàn đầu vào theo chính sách đã công bố |
| Hạ chữ/bỏ dấu mọi mã trước validation | Có thể hợp thức hóa mã sai hoặc làm trùng giá trị | Quy định canonicalization rõ ràng |
| Gộp whitespace nội bộ của mọi văn bản | Mất thụt lề, xuống dòng, ý nghĩa | Chỉ gộp khi trường cho phép |
| Kiểm tra độ dài raw thay vì bản đã làm sạch | Bỏ lọt tên không đủ độ dài | Kiểm tra dạng cuối được lưu |
| Chỉ kiểm tra độ dài sau `strip()` | Vẫn nhận input thô cực lớn | Đặt giới hạn tại tầng nhận dữ liệu |
| Coi `trim()` và `strip()` hoàn toàn tương đương | Sai với một số Unicode whitespace | Chọn và test API đúng |
| Tin rằng regex `\\s` là Unicode mọi nơi | Bỏ sót nhóm ký tự | Xác minh flag và tập regex |
| Coi làm sạch là thay thế bảo vệ SQL/XSS | Rủi ro ở tầng sử dụng | Parameterized SQL, output encoding đúng ngữ cảnh |

Một quy tắc làm sạch lý tưởng còn nên **idempotent** khi nghiệp vụ cho phép: chạy hai lần cho cùng nội dung như chạy một lần. Ví dụ `"  A  ".strip().strip()` có nội dung bằng `"  A  ".strip()`. Các pipeline tùy biến nhiều bước phải được kiểm thử để không tiếp tục làm biến dạng dữ liệu mỗi lần chạy.

## 12. Ma trận kiểm thử tối thiểu

| Trường hợp | Ví dụ | Điều cần xác minh |
| --- | --- | --- |
| Thiếu dữ liệu | `null` | Không NPE ngoài chủ đích |
| Rỗng | `""` | Chính sách reject/accept/convert |
| Dấu cách ASCII | `"   "` | `strip` và `isBlank` |
| Blank Unicode | `"\u3000"` | Hành vi Unicode đã biết |
| NBSP | `"\u00A0"` | Không nhầm với blank theo Java |
| Zero-width | `"\u200B"` | Chính sách riêng cho ký tự ẩn |
| Padding | `"  Alice  "` | Bản gốc và bản xử lý |
| Whitespace nội bộ | `"An   Bình"` | Có/không gộp đúng contract |
| Newline nội bộ | `"A\nB"` | Đơn dòng có từ chối không? |
| Dấu kết hợp | `"Cafe\u0301"` | NFC có được phép không? |
| Emoji | `"A😀B"` | Đơn vị đo độ dài phù hợp |
| Input cực lớn | Hàng nghìn ký tự | Giới hạn thô và cuối |
| Mã có case khác | `"Alice"` | Có sửa ngầm hay từ chối? |
| Mật khẩu có khoảng trắng | `" pass1234 "` | Phải giữ nguyên |

Kiểm tra thêm **tính nhất quán** giữa UI, backend, API, dữ liệu lưu và thao tác tìm kiếm. Các tầng không nên tự áp dụng những bước chuẩn hóa khác nhau lên cùng một trường.

## 13. Bài tập áp dụng

1. **Phân loại:** dự đoán kết quả `isBlank()`, `isEmpty()` và `strip()` cho `null`, `""`, `"  "`, `"\u3000"`, `"\u00A0"`. Giải thích vì sao `null` phải kiểm tra riêng.
2. **Đổi thứ tự validation:** tên phải tối thiểu ba code points sau `strip()`. Hãy cho thấy `"  A  "` có thể qua bước kiểm tra độ dài raw nhưng không qua bước kiểm tra dạng cuối.
3. **Hai chính sách trái ngược:** viết `validateDisplayName()` có `strip()` và `validateAccountId()` không tự sửa. Thử cùng input `" alice "`.
4. **Mật khẩu:** nhập một passphrase giả có khoảng trắng ở hai đầu. Xác nhận hàm validation không xóa hoặc thay bất cứ ký tự nào.
5. **Unicode:** so `Character.isWhitespace(0x00A0)`, `Character.isSpaceChar(0x00A0)` và `"\u00A0".isBlank()`. Vì sao chúng không nhất thiết cùng kết quả?
6. **Giới hạn kép:** thiết kế raw limit 200 UTF-16 units và final limit 40 code points; kiểm thử chuỗi dài toàn dấu cách và chuỗi emoji.
7. **PATCH:** quy định rõ không gửi nickname, gửi `null` và gửi `""`. Viết ba test để đảm bảo không bị nhập làm một trạng thái.
8. **Idempotence:** kiểm tra `normalizeName(normalizeName(s)).equals(normalizeName(s))` trên nhiều input; phân tích nếu thất bại.

## 14. Checklist trước khi đưa vào ứng dụng

- Trường có ý nghĩa gì? Người dùng nhập văn bản tự do, mã chính xác, bí mật hay nội dung đa dòng?
- Cho phép biến đổi **phần nào** của dữ liệu? Chỉ hai đầu hay cả bên trong?
- `null`, `""` và blank có ý nghĩa giống nhau không?
- `strip()`/`trim()` có đúng định nghĩa whitespace đã chọn không? NBSP, zero-width được xử lý như thế nào?
- Có chuẩn hóa Unicode hay đổi case không? Có làm mất thông tin/ngữ nghĩa không?
- Validate trên giá trị thô, dạng cuối hay cả hai?
- Giới hạn theo UTF-16, code point, grapheme hay byte? Có hạn mức payload trước xử lý?
- Có từ chối ký tự điều khiển hoặc đầu vào sai thay vì sửa ngầm không?
- Có giữ riêng trạng thái thuộc tính **không được gửi** trong PATCH không?
- Đã kiểm thử nhất quán giữa tạo, cập nhật, xác thực, lưu và đọc dữ liệu chưa?

**Quy tắc cốt lõi:** trước khi kiểm tra đầu vào, hãy **xác định chính sách làm sạch của từng trường**. Chỉ biến đổi phần dữ liệu được phép và kiểm tra trên đúng dạng mà ứng dụng sẽ sử dụng. **Không blank** chưa chắc **hợp lệ**; và làm sạch không có nghĩa là an toàn ở mọi ngữ cảnh.

## 15. Tài liệu tham khảo

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `strip()`, `trim()`, `isBlank()`, `isEmpty()`, `length()`, `matches()`.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): `isWhitespace()`, `isSpaceChar()`, `isISOControl()`, Unicode code points.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): biểu diễn NFC/NFD/NFKC/NFKD.
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): `\\s`, cờ Unicode regex và nhóm ký tự.
- [Java SE 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): byte UTF-8 khi tính giới hạn dữ liệu trao đổi.
