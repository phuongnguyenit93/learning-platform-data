# Vì sao số `char` không luôn bằng số ký tự người dùng nhìn thấy?

Một nút “xóa ký tự”, bộ đếm trong ô nhập tên và phần xem trước 30 ký tự thường phải làm việc với **cụm ký tự người dùng cảm nhận**, trong khi `String.length()` của Java chỉ trả số **UTF-16 code unit**. Bài này chuyển sự khác biệt đó thành một chính sách xử lý văn bản có thể kiểm thử trong sản phẩm.

## 1. Một giới hạn, nhiều cách hiểu

Xét ba nội dung nhập:

- `😊`: 2 `char` nhưng 1 code point và thường 1 cụm hiển thị vì emoji ngoài BMP được UTF-16 mã hóa bằng cặp surrogate.
- `e\u0301`: 2 `char`, 2 code point nhưng thường 1 cụm vì dấu kết hợp đi cùng chữ cơ sở.
- `👩‍💻`: 5 `char`, 3 code point nhưng 1 extended grapheme cluster nhờ chuỗi ZWJ.

Vì vậy, thay `length()` bằng `codePointCount()` chỉ giải quyết trường hợp surrogate pair; vẫn có thể cắt giữa các thành phần của cùng một emoji hoặc giữa chữ và dấu. Khi xử lý từng ký tự hiển thị, ta cần **grapheme boundaries**.

Extended grapheme cluster theo Unicode Standard Annex #29 là đơn vị phân đoạn gần với kỳ vọng của người dùng. Nó **không đồng nghĩa** một glyph, một ô terminal hoặc một độ rộng pixel. Phông chữ có thể không ghép một emoji ZWJ thành một biểu tượng, và ngôn ngữ phức tạp còn chịu ảnh hưởng của shaping/biên tập văn bản.

## 2. Đặc tả đầu vào trước khi viết code

Giả sử form có hai ràng buộc: tối đa **6 grapheme cluster** cho một nhãn ngắn và tối đa **18 byte UTF-8** cho payload. Ta cần trả lời riêng:

| Câu hỏi | Quy tắc sản phẩm |
| --- | --- |
| “Một ký tự” là gì? | Một extended grapheme cluster theo Unicode segmentation |
| Giới hạn máy chủ là gì? | Số grapheme và byte UTF-8 phải cùng thỏa |
| Chuẩn hóa Unicode trước khi đếm không? | Có hay không phải do hợp đồng API quyết định; ví dụ dưới đây **giữ nguyên** đầu vào |
| Surrogate lẻ xử lý thế nào? | Từ chối vì đầu vào không well-formed UTF-16 |
| Khi quá giới hạn? | Giữ phần tiền tố dài nhất chứa các cluster trọn vẹn và không vượt giới hạn byte |
| Sự nhất quán đa nền tảng? | Kiểm thử client và server trên bộ chuỗi mẫu, cố định/kiểm soát phiên bản Unicode khi cần |

Lưu ý: **cắt để tạo preview** và **xác thực dữ liệu để lưu** có thể khác nhau. Với tên tài khoản, việc tự cắt có thể gây mất dữ liệu hoặc trùng tên; nên trả lỗi rõ ràng thay vì im lặng cắt. Với preview, việc lấy tiền tố trọn cluster thường là lựa chọn phù hợp.

## 3. Tìm ranh giới grapheme trong Java

Java 17+ hỗ trợ `Pattern.compile("\\X")` để khớp từng extended grapheme cluster. `Matcher.find()` đi qua các cụm theo thứ tự; `Matcher.end()` trả **UTF-16 offset** ngay sau cụm vừa khớp. Có thể dùng offset này trong `substring(0, end)` mà không cần tự cộng độ dài emoji.

Khi có thêm giới hạn byte, mỗi cluster UTF-16 **well-formed** có thể mã hóa sang UTF-8 và cộng số byte để quyết định có nhận cluster đó không. Ta không cắt theo số byte tùy ý, vì thao tác đó có thể cắt giữa dãy UTF-8 của một code point.

### Ví dụ đầy đủ: preview thỏa cả số cluster và số byte

Tệp `GraphemePreviewPolicy.java`, JDK 17+:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemePreviewPolicy {
    private static final Pattern CLUSTER = Pattern.compile("\\X");

    static String preview(String text, int maxClusters, int maxUtf8Bytes) {
        if (text == null) {
            throw new IllegalArgumentException("text is null");
        }
        if (maxClusters < 0 || maxUtf8Bytes < 0) {
            throw new IllegalArgumentException("negative limit");
        }

        // Java codePoints() có thể phát surrogate lẻ; từ chối trước khi encode.
        if (text.codePoints().anyMatch(
                cp -> cp >= 0xD800 && cp <= 0xDFFF)) {
            throw new IllegalArgumentException("unpaired surrogate");
        }

        Matcher matcher = CLUSTER.matcher(text);
        int usedBytes = 0;
        int endUtf16 = 0;
        int usedClusters = 0;

        while (usedClusters < maxClusters && matcher.find()) {
            int clusterBytes = matcher.group()
                    .getBytes(StandardCharsets.UTF_8).length;

            if (clusterBytes > maxUtf8Bytes - usedBytes) {
                break;
            }

            usedBytes += clusterBytes;
            usedClusters++;
            endUtf16 = matcher.end();
        }
        return text.substring(0, endUtf16);
    }

    public static void main(String[] args) {
        String text = "Vi\u1EC7t \uD83D\uDC69\u200D\uD83D\uDCBB!";

        System.out.println(preview(text, 6, 18)
                .equals("Vi\u1EC7t \uD83D\uDC69\u200D\uD83D\uDCBB"));
        System.out.println(preview(text, 6, 17).equals("Vi\u1EC7t "));
        System.out.println(preview(text, 5, 50).equals("Vi\u1EC7t "));
        System.out.println(preview(text, 0, 50).isEmpty());
        System.out.println(preview("\uD83D\uDC69\u200D\uD83D\uDCBB", 1, 10)
                .isEmpty());
    }
}
~~~

~~~bash
javac -encoding UTF-8 GraphemePreviewPolicy.java
java GraphemePreviewPolicy
~~~

Stdout:

~~~text
true
true
true
true
true
~~~

“Việt ” chứa **5 cluster và 7 byte UTF-8**; `👩‍💻` là cluster thứ sáu, thêm **11 byte**, vừa đúng giới hạn 18 byte. Với ngân sách 17 byte, chương trình phải dừng **trước toàn bộ emoji**. Không được lấy riêng emoji người phụ nữ rồi bỏ ZWJ và laptop để đủ byte, vì điều đó đổi nội dung biểu tượng.

Ví dụ này mã hóa từng cluster thành mảng byte tạm; với nhãn ngắn, cách làm đơn giản và dễ kiểm tra. Nếu xử lý văn bản cực dài hoặc chạy với tần suất lớn, có thể tối ưu bằng encoder tăng dần và đo hiệu năng. Thuật toán chỉ bảo toàn grapheme theo **quy tắc mà JDK đang hỗ trợ**; không bảo đảm mọi nền tảng hiển thị giống nhau.

## 4. Kiểm thử thực tế trên nhiều loại văn bản

| Mẫu đầu vào | Điểm dễ sai | Phép thử nên có |
| --- | --- | --- |
| `A😀B` | UTF-16 offset của B là 3 | Không cắt high/low surrogate ở giữa |
| `e\u0301` và `\u00E9` | Hai dãy code point khác nhau | Cùng một cluster nhưng `equals()` chưa chắc bằng nhau |
| `Vi\u1EC7t` và dạng NFD | Dấu tiếng Việt được tách | Đếm cluster theo quy tắc, byte theo biểu diễn thật |
| `🇻🇳` | Hai regional indicator tạo cờ | Không cắt riêng regional indicator đầu |
| `👍🏽` | Base emoji + skin tone | Không tách modifier |
| `👩‍💻` | Emoji + ZWJ + emoji | Không chẻ chuỗi nối thành các biểu tượng riêng |
| High surrogate đứng lẻ | `String` vẫn tạo được, nhưng UTF-16 lỗi | Thông báo lỗi thay vì âm thầm thay byte |
| Văn bản có ký tự điều khiển | Grapheme count không phải quy tắc cho phép nội dung | Kiểm tra thêm chính sách ký tự được phép |

Thêm kiểm thử tại **đúng ranh giới**: hạn mức 0, vừa khít, kém 1 byte, ít hơn 1 cluster và chuỗi rỗng. Nếu client dùng JavaScript còn server dùng Java, hãy kiểm tra bằng các chuỗi Unicode cụ thể thay vì mặc định hai runtime luôn phân đoạn giống nhau. Với input method (IME) tiếng Việt, cân nhắc trạng thái **đang soạn thảo/composition** trước khi áp đặt giới hạn tức thì, để không ngăn người dùng hoàn tất dấu.

## 5. Chuẩn hóa, con trỏ và chỉnh sửa văn bản

`Normalizer.normalize(text, Normalizer.Form.NFC)` có thể làm các dãy tương đương chuẩn nhất quán khi so sánh hoặc tìm kiếm, nhưng **thay đổi code unit và offset**. Nếu lưu vị trí con trỏ trước chuẩn hóa rồi dùng offset cũ sau chuẩn hóa, vị trí có thể sai. Vì thế cần định nghĩa rõ thứ tự: nhận đầu vào, chuẩn hóa (nếu hợp đồng yêu cầu), tính giới hạn, lưu dữ liệu và cập nhật vị trí con trỏ.

Trình sửa văn bản tương tác còn cần tính tới vùng chọn, phím Backspace/Delete, văn bản hai chiều, IME và quy tắc shaping. `\\X` cung cấp **ranh giới cluster**, không tự cung cấp đầy đủ một text editor. Một grapheme cluster cũng không phải đơn vị số cột terminal; canh lề văn bản vẫn cần công cụ đo độ rộng phù hợp.

## 6. Checklist ra quyết định

Trước khi dùng `length()` làm “số ký tự”, xác định mục đích: chỉ số `String` theo UTF-16, xử lý từng code point, giới hạn theo grapheme, giới hạn byte hay chiều rộng giao diện. Sau đó chọn API tương ứng và thử tối thiểu ba lớp ca: **surrogate pair**, **dấu kết hợp**, **emoji nhiều code point**. Nếu phải lưu Unicode nghiêm ngặt, kiểm tra surrogate lẻ trước encode.

### Tự kiểm tra

1. `"👩‍💻".length()` bằng bao nhiêu? **5**, dù chỉ một cluster theo quy tắc hỗ trợ trình tự đó.
2. `"e\u0301".codePointCount(0, 2)` bằng bao nhiêu? **2**, còn grapheme count thường là **1**.
3. Một cụm emoji cần 11 byte UTF-8 nhưng ngân sách còn 10 byte: có được lấy nửa cụm không? **Không**, theo chính sách preview đã định.
4. Đếm theo grapheme có tự giới hạn số byte hoặc đo độ rộng pixel không? **Không**; đây là ba phép đo độc lập.
5. Tại sao phải thử cùng bộ mẫu trên client/server? Vì quy tắc Unicode và phiên bản dữ liệu phân đoạn của các runtime có thể khác nhau.

Nguồn kỹ thuật: [Unicode Text Segmentation — UAX #29](https://www.unicode.org/reports/tr29/), [Java `Pattern`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), [Java `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).