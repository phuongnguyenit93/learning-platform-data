# Xây dựng bộ làm sạch đầu vào theo chính sách tường minh trong Java

Khi nhận dữ liệu từ biểu mẫu, API, tệp CSV hoặc nguồn bên ngoài, lập trình viên thường viết một chuỗi thao tác như `trim()`, thay nhiều khoảng trắng bằng một, đổi thành chữ thường hoặc xóa ký tự lạ. Cách làm này dễ tạo lỗi khi mỗi trường dữ liệu có **ý nghĩa và yêu cầu khác nhau**: tên đăng nhập, tên hiển thị, mật khẩu, địa chỉ email, nội dung bài viết và đường dẫn tệp không thể dùng chung một quy tắc.

Bộ làm sạch đầu vào (*input cleaner*) đáng tin cậy phải nêu rõ **dữ liệu nào được chấp nhận, biến đổi nào được phép, trường hợp nào phải từ chối và thứ tự áp dụng**. Bài thực hành xây dựng bộ làm sạch Java 17+ với chính sách bất biến cho hai loại đầu vào:

- **Tên đăng nhập (username):** chuẩn hóa Unicode theo NFKC, bỏ khoảng trắng ở hai đầu, đổi chữ thường độc lập ngôn ngữ, chỉ chấp nhận chữ ASCII, số và dấu gạch dưới theo cấu trúc xác định.
- **Tên hiển thị (display name):** chuẩn hóa NFC, gom nhiều khoảng trắng thành một, cho phép chữ cái và dấu kết hợp Unicode, giữ nguyên chữ hoa/thường; không tự ý loại bỏ ký tự sai mà báo lỗi.

Đây là **ví dụ chính sách cho một ứng dụng cụ thể**, không phải bộ lọc được phép áp dụng nguyên xi cho mọi ngôn ngữ, tên người hoặc hệ thống.

## 1. Phân biệt làm sạch, chuẩn hóa, xác thực và mã hóa đầu ra

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| **Chuẩn hóa (normalization)** | Đưa những biểu diễn được ứng dụng coi là tương đương về một dạng thống nhất. | Chuyển chuỗi có dấu kết hợp sang dạng NFC. |
| **Làm sạch (cleaning/canonicalization)** | Áp dụng các phép biến đổi được chính sách công bố rõ ràng. | Thu gọn khoảng trắng trong tên hiển thị thành một dấu cách. |
| **Xác thực (validation)** | Kiểm tra dữ liệu sau khi biến đổi có phù hợp hợp đồng của trường không. | Tên đăng nhập phải khớp `[a-z][a-z0-9_]{2,15}`. |
| **Mã hóa/escape theo ngữ cảnh đầu ra** | Bảo vệ dữ liệu khi đưa vào HTML, JSON, URL, câu lệnh SQL, shell và các ngữ cảnh khác. | Escape văn bản khi hiển thị HTML; dùng tham số cho câu lệnh SQL. |

**Làm sạch đầu vào không thay thế cơ chế bảo vệ ở nơi sử dụng dữ liệu.** Ví dụ, một chuỗi đã khớp quy tắc tên hiển thị vẫn phải được escape khi chèn vào HTML; mọi truy vấn SQL nhận dữ liệu từ người dùng nên dùng prepared statement/tham số thay cho nối chuỗi. Tránh đặt tên một hàm chung kiểu `sanitizeEverything()` và giả định rằng đầu ra an toàn trong mọi ngữ cảnh.

Cũng cần phân biệt:

- **Từ chối dữ liệu lỗi:** Báo cho người gọi biết chính xác loại vi phạm, không tự làm mất thông tin.
- **Biến đổi dữ liệu hợp lệ theo quy tắc:** Ví dụ bỏ khoảng trắng ở đầu/cuối được sản phẩm chấp nhận.
- **Sửa lỗi tùy tiện:** Ví dụ âm thầm bỏ mọi ký tự không thuộc allowlist có thể biến `ad!min` thành `admin`; hai định danh khác nhau có thể trở thành một. Ví dụ này chọn **từ chối** để tránh trường hợp đó.

## 2. Viết chính sách trước khi viết thuật toán

Chính sách nên xác định từng chiều quyết định:

| Quyết định | Username | Display name |
| --- | --- | --- |
| Đầu vào `null` | Từ chối | Từ chối |
| Unicode normalization | `Normalizer.Form.NFKC` | `Normalizer.Form.NFC` |
| Khoảng trắng ở đầu/cuối | Bỏ bằng `strip()` | Bỏ bằng `strip()` sau khi thu gọn |
| Khoảng trắng bên trong | Không thay đổi; mẫu ký tự cuối cùng sẽ từ chối | Quy đổi chuỗi khoảng trắng về một dấu cách ASCII |
| Chữ hoa/chữ thường | `toLowerCase(Locale.ROOT)` | Giữ nguyên |
| Điều khiển/định dạng Unicode bất thường | Từ chối | Từ chối, ngoại trừ khoảng trắng được phép quy đổi |
| Chuỗi không hợp lệ về cấu trúc UTF-16 | Từ chối | Từ chối |
| Độ dài sau biến đổi | 3–16 code point | 1–40 code point |
| Ký tự được phép | `[a-z][a-z0-9_]{2,15}` | Chữ cái và dấu kết hợp Unicode, các từ cách nhau một dấu cách |

Giải thích phạm vi:

- Với username, `[a-z][a-z0-9_]{2,15}` yêu cầu ký tự đầu tiên là chữ thường ASCII, sau đó có từ 2 đến 15 ký tự thuộc `a-z`, `0-9` hoặc `_`. Tổng chiều dài là 3–16.
- Với display name, biểu thức `[\p{L}][\p{L}\p{M}]*(?: [\p{L}][\p{L}\p{M}]*)*` sử dụng nhóm Unicode Letter/Mark. Nó cố ý **không cho phép** chữ số, dấu gạch nối, dấu nháy, emoji hay nhiều cách viết tên khác. Ứng dụng thực tế phải điều chỉnh allowlist theo đối tượng người dùng; không nên dùng chính sách minh họa để tuyên bố tên của người dùng là “không hợp lệ”.
- `NFC` gộp các biểu diễn Unicode tương đương theo quy tắc chuẩn hóa dạng canonical; `NFKC` còn áp dụng biến đổi compatibility, ví dụ chữ Latin fullwidth `Ａ` thành `A`. NFKC có thể thay đổi ý nghĩa hiển thị của một số ký tự: chỉ dùng nếu hợp đồng định danh muốn coi các biểu diễn đó là tương đương.
- `Locale.ROOT` tránh kết quả chữ hoa/chữ thường thay đổi theo locale máy chạy. Đây là *lowercasing*, không phải thuật toán Unicode *case folding* đầy đủ. Với username vốn chỉ nhận ASCII sau xử lý, quy tắc minh họa đủ rõ.
- Bài này tính độ dài bằng **Unicode code point**, không dùng độ dài UTF-16 của `String.length()`. Code point vẫn không luôn bằng một ký tự mà con người cảm nhận (grapheme cluster); khi giới hạn tên hiển thị theo “ký tự nhìn thấy”, cần chọn định nghĩa khác phù hợp.

## 3. Xác định thứ tự pipeline

Một pipeline có thể kiểm chứng cần chạy theo thứ tự đã công bố:

~~~text
Input String
    |
    v
1. Kiểm tra null và giới hạn dữ liệu thô ở biên hệ thống
    |
    v
2. Chuẩn hóa Unicode NFC hoặc NFKC theo chính sách
    |
    v
3. Duyệt code point; xử lý khoảng trắng hoặc từ chối control/format/surrogate
    |
    v
4. Bỏ khoảng trắng đầu/cuối khi chính sách cho phép
    |
    v
5. Đổi chữ thường bằng Locale.ROOT nếu là username
    |
    v
6. Kiểm tra độ dài và allowlist trên giá trị kết quả
    |
    +---- không đạt ----> REJECT: trả lỗi có thể xử lý
    |
    v
7. Trả chuỗi đã làm sạch để dùng trong nghiệp vụ
~~~

**Vì sao phải kiểm tra sau biến đổi?** `ＮＡＭＥ` có thể biến thành `NAME` qua NFKC rồi thành `name` qua lowercase; cấu trúc và độ dài phải được đánh giá trên giá trị **thực sự được lưu hoặc so sánh**. Cũng nên giới hạn kích thước yêu cầu/chuỗi thô **trước** khi gọi các thao tác tốn CPU/bộ nhớ, tránh phải xử lý một chuỗi đầu vào không giới hạn chỉ để cuối cùng báo quá dài. Ví dụ Java bên dưới tập trung vào quy tắc trường dữ liệu; giới hạn kích thước thông điệp cần được cấu hình ở tầng nhận dữ liệu của ứng dụng.

Các quyết định đặc biệt theo trường phải tường minh. Chẳng hạn, pipeline tên hiển thị cho phép biến tab hoặc xuống dòng thành dấu cách; trường HTTP header hay một định danh dòng đơn có thể cần **từ chối CR/LF** ngay từ đầu. Không tái sử dụng chính sách tên hiển thị cho các ngữ cảnh đó.

## 4. Chương trình Java 17+ hoàn chỉnh

Lưu đoạn sau thành **InputCleanerDemo.java** (UTF-8). `record Policy` tập trung tất cả lựa chọn thành một đối tượng cấu hình, hai hằng `USERNAME` và `DISPLAY_NAME` là các hợp đồng đầu vào riêng biệt. `Pattern` được biên dịch một lần cho mỗi hợp đồng, còn `Matcher` được tạo mới khi kiểm tra từng chuỗi.

~~~java
import java.text.Normalizer;
import java.util.Locale;
import java.util.regex.Pattern;

public class InputCleanerDemo {
    record Policy(
            Normalizer.Form normalization,
            boolean trim,
            boolean collapseWhitespace,
            boolean lowercaseRoot,
            int minCodePoints,
            int maxCodePoints,
            Pattern allowed) {}

    static final Policy USERNAME = new Policy(
            Normalizer.Form.NFKC, true, false, true, 3, 16,
            Pattern.compile("[a-z][a-z0-9_]{2,15}"));

    static final Policy DISPLAY_NAME = new Policy(
            Normalizer.Form.NFC, true, true, false, 1, 40,
            Pattern.compile(
                "[\\p{L}][\\p{L}\\p{M}]*(?: [\\p{L}][\\p{L}\\p{M}]*)*"));

    static boolean whitespace(int codePoint) {
        return Character.isWhitespace(codePoint)
                || Character.isSpaceChar(codePoint);
    }

    static String clean(String raw, Policy policy) {
        if (raw == null) {
            throw new IllegalArgumentException("null");
        }

        String normalized =
                Normalizer.normalize(raw, policy.normalization());
        StringBuilder builder = new StringBuilder();
        boolean previousSpace = false;

        for (int offset = 0; offset < normalized.length();) {
            int cp = normalized.codePointAt(offset);
            offset += Character.charCount(cp);

            if (policy.collapseWhitespace() && whitespace(cp)) {
                if (!previousSpace) builder.append(' ');
                previousSpace = true;
                continue;
            }

            // Reject control/format characters and malformed UTF-16.
            if (Character.isISOControl(cp)
                    || Character.getType(cp) == Character.FORMAT
                    || (cp >= 0xD800 && cp <= 0xDFFF)) {
                throw new IllegalArgumentException(
                        "control/format/surrogate");
            }

            builder.appendCodePoint(cp);
            previousSpace = false;
        }

        String value = builder.toString();
        if (policy.trim()) value = value.strip();
        if (policy.lowercaseRoot()) {
            value = value.toLowerCase(Locale.ROOT);
        }

        int size = value.codePointCount(0, value.length());
        if (size < policy.minCodePoints()
                || size > policy.maxCodePoints()) {
            throw new IllegalArgumentException("length");
        }
        if (!policy.allowed().matcher(value).matches()) {
            throw new IllegalArgumentException("not allowed");
        }
        return value;
    }

    static void show(String label, String value, Policy policy) {
        try {
            System.out.println(
                    label + " -> " + clean(value, policy));
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    label + " -> REJECT (" + ex.getMessage() + ")");
        }
    }

    public static void main(String[] args) {
        show("username fullwidth",
                "  \uFF21lice_12  ", USERNAME);
        show("username invalid", "abc!", USERNAME);
        show("username control", "al\0ice", USERNAME);

        show("display NFC",
                "  Ca\u0300   phe\u0302  ", DISPLAY_NAME);
        show("display whitespace",
                "  Cà  \t phê \n", DISPLAY_NAME);
        show("display emoji", "Lan 🙂", DISPLAY_NAME);
        show("display empty", " \t  ", DISPLAY_NAME);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 InputCleanerDemo.java
java InputCleanerDemo
~~~

Đầu ra:

~~~text
username fullwidth -> alice_12
username invalid -> REJECT (not allowed)
username control -> REJECT (control/format/surrogate)
display NFC -> Cà phê
display whitespace -> Cà phê
display emoji -> REJECT (not allowed)
display empty -> REJECT (length)
~~~

**Phân tích từng tình huống:**

1. `\uFF21` là chữ Latin `Ａ` ở dạng fullwidth; NFKC chuyển thành `A`, `strip()` bỏ khoảng trắng hai đầu, sau đó `Locale.ROOT` chuyển thành `alice_12`. Tên này hợp lệ theo regex username.
2. `abc!` đủ độ dài, nhưng dấu `!` không nằm trong allowlist nên bị từ chối; chương trình **không tự biến** thành `abc`.
3. `al\0ice` chứa ký tự điều khiển NUL; việc kiểm tra `Character.isISOControl` từ chối trước khi kiểm tra regex.
4. Chuỗi `Ca\u0300   phe\u0302` chứa các dấu kết hợp; NFC chuẩn hóa thành `Cà   phê` rồi bộ gom khoảng trắng tạo `Cà phê`.
5. Chuỗi tên hiển thị có tab và xuống dòng được gộp thành một dấu cách vì **chính sách riêng của display name cho phép**. Không suy ra rằng mọi loại input đều được phép chuyển CR/LF như vậy.
6. Emoji `🙂` không nằm trong regex Letter/Mark được chọn; input bị từ chối rõ ràng, không bị xóa ngầm. Sản phẩm hỗ trợ emoji trong tên phải thay đổi chính sách.
7. Chuỗi chỉ gồm khoảng trắng trở thành chuỗi rỗng; kiểm tra độ dài phát hiện và từ chối.

## 5. Giải thích các quyết định kỹ thuật quan trọng

### Unicode normalization: NFC và NFKC

`java.text.Normalizer.normalize(input, form)` trả một chuỗi theo dạng chuẩn hóa được yêu cầu. Với `NFC`, các chuỗi ký tự tương đương theo chuẩn Unicode canonical được đưa về dạng thống nhất (khi có dạng ghép). Với `NFKC`, các ký tự compatibility còn được biến đổi rộng hơn. Điều này hữu ích với định danh nhưng có thể làm **hai đầu vào ban đầu khác nhau trở thành một giá trị**.

Nếu username được dùng làm khóa tra cứu hoặc ràng buộc unique trong cơ sở dữ liệu, hệ thống phải thực hiện chuẩn hóa **trước kiểm tra trùng lặp và trước khi lưu khóa định danh**, theo cùng một chính sách ở mọi đường vào dữ liệu. Khi thay đổi chính sách trong tương lai, cần đánh giá va chạm với các username đã tồn tại; không thể đơn giản đổi cách chuẩn hóa mà coi dữ liệu cũ không ảnh hưởng.

Normalization **không** giải quyết mọi ký tự giống nhau về hình dáng (*confusables*, ví dụ một số chữ Latin và Cyrillic), cũng không thay thế kiểm tra nghiệp vụ. Với các định danh công khai hoặc có giá trị bảo mật, cần cân nhắc chống nhầm lẫn ký tự ở cấp sản phẩm.

### Khoảng trắng không chỉ là ký tự `' '`

`String.strip()` loại bỏ hai đầu dựa trên `Character.isWhitespace`, khác `trim()` vốn có quy tắc cũ dựa trên giá trị ký tự. Một số khoảng trắng Unicode như non-breaking space không được `isWhitespace` nhận diện. Ví dụ đã chọn `Character.isWhitespace(cp) || Character.isSpaceChar(cp)` để nhận diện rộng hơn **trong chính sách thu gọn khoảng trắng**, đổi về dấu cách ASCII rồi mới `strip()`.

Bộ gom dùng `codePointAt`, `Character.charCount` và `StringBuilder.appendCodePoint` để không cắt đôi surrogate pair hợp lệ. Ký tự UTF-16 surrogate lẻ bị từ chối thay vì được tự động biến thành ký tự thay thế. Trường hợp `Character.FORMAT` cũng bị từ chối, gồm một số dấu điều khiển định dạng vô hình. Tuy nhiên, một số hệ chữ dùng các ký tự định dạng như zero-width joiner một cách hợp lệ; chính sách này cần được nới/điều chỉnh nếu sản phẩm hỗ trợ chúng. Không áp dụng lệnh xóa toàn bộ ký tự định dạng một cách không xét ngữ cảnh.

### Dùng allowlist sau khi xử lý

`Pattern.matcher(value).matches()` xác nhận **toàn bộ giá trị** phù hợp regex, khác `find()` chỉ tìm một đoạn khớp. Đây là lý do chuỗi `abc!` không được nhận dù có đoạn `abc` phù hợp. Regex là một phần của hợp đồng dữ liệu và phải đi kèm kiểm tra độ dài; không nên coi một regex duy nhất là đủ để bảo vệ hệ thống.

Quy tắc ký tự tên hiển thị ở ví dụ chỉ là tập con để minh họa. Tên thực tế có thể chứa dấu nối, dấu nháy, chữ số, chữ viết có quy tắc phức tạp hoặc emoji. Người thiết kế phải quyết định rõ cần chấp nhận những dạng nào, bổ sung kiểm thử cho các hệ chữ đó và ghi lại lý do từ chối.

### Khi nào nên báo lỗi thay vì âm thầm sửa?

Trong demo, các biến đổi được phép đều ghi thành thuộc tính của `Policy`. Các trường hợp ngoài chính sách được từ chối bằng `IllegalArgumentException` và nhãn nguyên nhân ổn định ở mức minh họa: `null`, `control/format/surrogate`, `length`, `not allowed`. Ứng dụng production nên chuyển lỗi này thành **mã lỗi có cấu trúc** (ví dụ enum/record kết quả) rồi trả thông báo phù hợp cho người dùng. Tránh phơi bày nguyên chuỗi nhạy cảm trong log hoặc error response.

Bởi việc biến đổi có thể gây mất phân biệt giữa nhiều input, đôi khi cần lưu **giá trị gốc** cho mục đích nghiệp vụ có quyền truy cập phù hợp và dùng **giá trị chuẩn hóa** để so sánh/tìm kiếm. Không giữ giá trị gốc nếu trường đó là bí mật hoặc chính sách bảo mật không cho phép.

## 6. Kiểm thử: những ca cần có ngoài ví dụ chạy tay

Bộ làm sạch nên có automated tests cho từng chính sách, nhất là tại ranh giới Unicode và chiều dài. Tập ca kiểm thử nên bao phủ:

| Nhóm tình huống | Input/điều kiện | Mong đợi |
| --- | --- | --- |
| Giá trị không có | `null` | Từ chối, không ném `NullPointerException` ngoài dự kiến. |
| Trống sau xử lý | `" \t "` cho display name | Từ chối vì độ dài nhỏ hơn 1. |
| Dạng Unicode tương đương | `"Ca\u0300"` và `"Cà"` trong display name | Cùng kết quả `"Cà"` sau NFC. |
| Dạng compatibility | `"\uFF21lice_12"` cho username | Thành `"alice_12"` sau NFKC và lowercase. |
| Ký tự không được phép | `"abc!"` cho username | Từ chối; không tự cắt `!`. |
| Control/format | NUL, tab trong username, ký tự định dạng ẩn | Từ chối theo chính sách username. |
| Khoảng trắng nhiều loại | Space, tab, xuống dòng, non-breaking space trong display name | Gom thành một dấu cách; loại bỏ ở hai đầu. |
| Độ dài | 2, 3, 16, 17 ký tự ASCII của username theo cấu trúc | Đúng các ranh giới, không sai lệch `<`/`<=`. |
| Unicode ngoài BMP | Emoji/supplementary code point | Xử lý nguyên code point; cuối cùng chấp nhận/từ chối theo policy. |
| Thay đổi chính sách | Cùng input, hai policy khác nhau | Kết quả theo từng policy; không có ngoại lệ “ẩn”. |
| Tính ổn định | `clean(clean(x, p), p)` với dữ liệu được chấp nhận | Kết quả bằng `clean(x, p)` đối với chính sách minh họa. |

Cần kiểm tra thêm giới hạn dữ liệu thô ở API, tải lớn và hành vi đối với đầu vào không tin cậy. Lưu ý kiểm thử **idempotence** nêu trên là tính chất được kỳ vọng của pipeline này, không phải thuộc tính tự động của mọi phép chuẩn hóa/làm sạch; chính sách mới cần tự chứng minh lại.

## 7. Đưa vào ứng dụng: điểm đặt và giới hạn trách nhiệm

Tại lớp biên nhận dữ liệu (controller, DTO mapper, import parser), chọn chính sách theo **trường dữ liệu** thay vì gọi một hàm chung không có ngữ cảnh:

~~~java
// Đoạn minh họa trong ứng dụng đã có InputCleanerDemo.
String username = InputCleanerDemo.clean(
        requestUsername, InputCleanerDemo.USERNAME);
String displayName = InputCleanerDemo.clean(
        requestDisplayName, InputCleanerDemo.DISPLAY_NAME);
~~~

Đoạn này là minh họa, **không phải chương trình chạy độc lập**: `requestUsername` và `requestDisplayName` do controller cung cấp. Chính sách trong lớp demo là package-private; khi tách thành thư viện ở package khác, công khai API thích hợp và kiểm soát phiên bản chính sách. Nên tổ chức việc validate ở một nơi dùng chung để tất cả lối vào (web, batch, migration) áp dụng nhất quán.

Đối với **mật khẩu**, không trim, lowercase, NFKC hoặc âm thầm thay thế ký tự trừ khi giao thức xác thực đã định nghĩa chính xác phép biến đổi và áp dụng nhất quán; đổi chuỗi đầu vào có thể đổi bí mật mà người dùng muốn sử dụng. Đối với **email, URL, tên tệp, địa chỉ đường dẫn, văn bản HTML**, cần parser, luật chuẩn hóa và biện pháp bảo vệ theo riêng từng loại. Ví dụ, chặn path traversal đòi hỏi kiểm soát đường dẫn sau khi resolve trong thư mục được phép; gom khoảng trắng không giải quyết được vấn đề.

Với chuỗi dùng trong **SQL**, hãy dùng tham số của `PreparedStatement` hoặc ORM; với **HTML**, escape theo ngữ cảnh khi xuất; với **lệnh shell**, tránh nối lệnh từ chuỗi người dùng; với **log**, xử lý ký tự điều khiển và dữ liệu nhạy cảm theo chính sách ghi log. Không gán cho `clean()` trách nhiệm thay thế các cơ chế đó.

## 8. Các lỗi thiết kế thường gặp

| Sai lầm | Rủi ro | Hướng khắc phục |
| --- | --- | --- |
| Dùng chung một quy tắc cho username, tên hiển thị, mật khẩu và nội dung | Mất dữ liệu, đổi ý nghĩa hoặc từ chối dữ liệu hợp lệ. | Chính sách tường minh theo từng trường và hợp đồng sản phẩm. |
| `replaceAll("[^a-z0-9]", "")` để xóa ký tự không hợp lệ | Có thể tạo va chạm định danh và che mất lỗi nhập. | Từ chối khi không thuộc allowlist; chỉ biến đổi đã thỏa thuận. |
| Kiểm tra regex trước normalize/lowercase, sau đó lưu chuỗi đã đổi | Dữ liệu cuối cùng có thể không còn cùng tính chất đã kiểm tra. | Xác thực trên biểu diễn cuối cùng sau tất cả phép biến đổi. |
| Dùng `String.length()` và cho rằng đó là số ký tự hiển thị | UTF-16 surrogate pair và grapheme cluster khiến số đếm khác. | Chọn code point hoặc grapheme cluster theo yêu cầu thật. |
| Dùng `toLowerCase()` phụ thuộc locale cho định danh | Có thể cho kết quả khác ở môi trường khác nhau. | Dùng `Locale.ROOT` nếu chính sách cho phép lowercase độc lập locale. |
| Áp dụng NFKC mặc định cho mọi chuỗi | Compatibility folding có thể thay đổi ý nghĩa dữ liệu. | Chọn NFC/NFKC theo từng loại dữ liệu và test va chạm. |
| Xóa hết ký tự Unicode thuộc loại FORMAT | Làm hỏng tên/văn bản trong một số hệ chữ. | Chỉ từ chối/biến đổi nếu hợp đồng trường cho phép. |
| Tin chuỗi đã clean là tự động an toàn cho HTML/SQL/URL | Các bề mặt tấn công có cơ chế diễn giải khác nhau. | Dùng prepared statements, output escaping và parser theo ngữ cảnh. |
| Chỉ giới hạn độ dài sau khi xử lý một input khổng lồ | Có thể tiêu tốn CPU/bộ nhớ không cần thiết. | Giới hạn kích thước thô ở ingress, rồi mới normalize và validate. |
| Không kiểm tra trùng sau chuẩn hóa username | Hai biểu diễn khác nhau có thể trùng một khóa định danh. | Chuẩn hóa trước uniqueness check và áp dụng nhất quán khi lưu/truy vấn. |

## 9. Bài tập mở rộng

1. Thêm chính sách **mã sản phẩm**: chỉ cho phép chữ ASCII in hoa, số và dấu gạch ngang, chiều dài 6–20; không thu gọn khoảng trắng bên trong. Viết kiểm thử input đúng/sai, cùng input sau normalize.
2. Thay `IllegalArgumentException` bằng `record CleanResult(String value, String errorCode)` hoặc mô hình lỗi có kiểu, bảo đảm người gọi nhận được mã lý do rõ ràng và không vô tình sử dụng chuỗi sai.
3. Tách chính sách display name hỗ trợ tên có dấu gạch nối và dấu nháy, viết kiểm thử đa ngôn ngữ trước khi mở rộng regex.
4. Thêm giới hạn độ dài chuỗi thô trước `Normalizer.normalize`, đồng thời ghi rõ giới hạn này áp dụng cho số code unit hay byte khi nhận qua HTTP.
5. Tạo kiểm thử tính ổn định `clean(clean(input, policy), policy)` và kiểm thử va chạm sau NFKC đối với tập định danh mẫu.

**Ghi nhớ:** Một bộ làm sạch đầu vào tốt bắt đầu từ **chính sách công khai về phép biến đổi và lỗi**, sau đó mới đến API Java. Chuẩn hóa đúng thứ tự, duyệt Unicode an toàn, kiểm tra độ dài và allowlist trên giá trị kết quả, từ chối trường hợp ngoài chính sách, và dùng biện pháp bảo vệ đúng ngữ cảnh khi lưu/hiển thị/sử dụng dữ liệu.