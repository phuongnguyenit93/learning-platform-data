# Pattern.splitWithDelimiters và tái sử dụng regular expression

Java 21 bổ sung `Pattern.splitWithDelimiters`, cho phép tách chuỗi theo regular expression nhưng vẫn giữ lại các đoạn khớp với biểu thức chính quy trong kết quả. Tính năng này hữu ích khi cần phân tích chuỗi mà vẫn phải giữ dấu phân cách để xử lý tiếp, chẳng hạn tách biểu thức thành token và toán tử, phân tích log hoặc chia văn bản thành các phần xen kẽ với dấu câu.

Khi một regular expression được dùng nhiều lần, nên biên dịch nó thành `Pattern` một lần rồi tái sử dụng. `Pattern` là immutable và an toàn khi chia sẻ giữa nhiều thread; mỗi lần tách hoặc mỗi thao tác cần trạng thái khớp sẽ sử dụng matcher riêng. Cách tổ chức này vừa tránh biên dịch lặp lại, vừa giữ được ranh giới rõ ràng giữa cấu hình regex và trạng thái của một lần xử lý.

## 1. split() và splitWithDelimiters() khác nhau thế nào?

`Pattern.split(input, limit)` tách chuỗi theo các đoạn khớp regex và loại bỏ các delimiter khỏi kết quả. `Pattern.splitWithDelimiters(input, limit)` cũng tách theo regex nhưng thêm từng delimiter đã khớp vào mảng kết quả, xen giữa các phần văn bản.

Ví dụ:

```java
import java.util.Arrays;
import java.util.regex.Pattern;

Pattern separator = Pattern.compile("[,;]");
String input = "red,green;blue";

System.out.println(Arrays.toString(separator.split(input, 0)));
// [red, green, blue]

System.out.println(Arrays.toString(
        separator.splitWithDelimiters(input, 0)));
// [red, ,, green, ;, blue]
```

Kết quả của `splitWithDelimiters` có thứ tự:

1. Phần văn bản trước delimiter đầu tiên.
2. Delimiter khớp đầu tiên.
3. Phần văn bản giữa delimiter thứ nhất và thứ hai.
4. Delimiter khớp tiếp theo.
5. Tiếp tục xen kẽ cho đến phần văn bản cuối cùng.

Delimiter trong kết quả là toàn bộ chuỗi con khớp với pattern. Nếu regex có capturing group, các group không được đưa thành các phần tử riêng; chỉ toàn bộ match được giữ lại.

## 2. Khi nào nên giữ delimiter?

Giữ delimiter hữu ích khi bước tiếp theo cần biết không chỉ các token mà còn cả ký hiệu nối giữa chúng.

Ví dụ, khi tách một chuỗi biểu thức đơn giản:

```java
Pattern operator = Pattern.compile("[+*/-]");
String expression = "12+7*3-2";

String[] parts = operator.splitWithDelimiters(expression, 0);
System.out.println(Arrays.toString(parts));
// [12, +, 7, *, 3, -, 2]
```

Kết quả giữ được cả toán hạng và toán tử. Một bước phân tích tiếp theo có thể duyệt mảng để phân loại token, tạo node cú pháp hoặc áp dụng quy tắc nghiệp vụ.

`splitWithDelimiters` không phải parser hoàn chỉnh. Ví dụ trên chỉ tách theo ký tự toán tử, chưa xử lý thứ tự ưu tiên, dấu ngoặc, số âm, chuỗi literal hoặc escape. Với ngôn ngữ có cú pháp phức tạp, hãy dùng tokenizer/parser phù hợp thay vì mở rộng một regex đơn lẻ thành bộ phân tích cú pháp.

## 3. Cách dùng Pattern.splitWithDelimiters

Phương thức có dạng:

```java
String[] splitWithDelimiters(CharSequence input, int limit)
```

- `input`: chuỗi cần tách; có thể là `String` hoặc một `CharSequence` khác.
- `limit`: giới hạn số lần pattern được áp dụng và ảnh hưởng đến việc giữ chuỗi rỗng ở cuối.
- Kết quả: mảng `String` chứa các đoạn văn bản và delimiter theo thứ tự xuất hiện.

Ví dụ với dấu phân cách nhiều ký tự:

```java
Pattern arrow = Pattern.compile("->");
String input = "source->transform->destination";

String[] tokens = arrow.splitWithDelimiters(input, -1);
System.out.println(Arrays.toString(tokens));
// [source, ->, transform, ->, destination]
```

Pattern có thể khớp delimiter là một ký tự hoặc một chuỗi nhiều ký tự. Vì vậy, nếu cần giữ nguyên delimiter gồm nhiều ký tự, hãy đặt cả delimiter trong cùng một pattern match.

## 4. Hiểu chính xác tham số limit

`limit` quyết định số lần pattern được áp dụng. Khi delimiter được giữ lại, số phần tử trong mảng có thể nhiều hơn số phần văn bản.

| Giá trị `limit` | Số lần áp dụng pattern | Hành vi với phần cuối |
|---|---|---|
| `limit > 0` | Tối đa `limit - 1` lần | Phần còn lại sau delimiter cuối cùng được giữ trong phần tử cuối |
| `limit == 0` | Nhiều lần nhất có thể | Loại bỏ các chuỗi rỗng ở cuối kết quả |
| `limit < 0` | Nhiều lần nhất có thể | Giữ các chuỗi rỗng ở cuối kết quả |

Với `limit` dương, mảng có tối đa `2 * limit - 1` phần tử vì mỗi lần khớp có thể đóng góp một đoạn văn bản và một delimiter, sau đó còn phần văn bản cuối cùng.

### limit dương

```java
Pattern comma = Pattern.compile(",");
String input = "one,two,three,four";

System.out.println(Arrays.toString(
        comma.splitWithDelimiters(input, 2)));
// [one, ,, two,three,four]
```

Với `limit = 2`, pattern được áp dụng tối đa một lần. Kết quả gồm phần trước delimiter, delimiter đó và toàn bộ phần còn lại. `limit = 1` không áp dụng pattern lần nào, nên kết quả chỉ có nguyên chuỗi đầu vào.

### limit bằng 0 và số âm

```java
Pattern comma = Pattern.compile(",");
String input = "one,two,";

System.out.println(Arrays.toString(
        comma.splitWithDelimiters(input, 0)));
// [one, ,, two, ,]

System.out.println(Arrays.toString(
        comma.splitWithDelimiters(input, -1)));
// [one, ,, two, ,, ]
```

Với `limit = 0`, chuỗi rỗng ở cuối bị loại bỏ, nhưng delimiter đã khớp vẫn được giữ lại. Với `limit = -1`, phần văn bản rỗng sau delimiter cuối cùng cũng được giữ.

Nếu cần phân biệt rõ một trường cuối rỗng với việc không có trường cuối, hãy dùng `limit` âm. Nếu chỉ quan tâm các token có nội dung, `limit = 0` thường thuận tiện hơn.

## 5. Chuỗi rỗng, delimiter liên tiếp và zero-width match

Các trường hợp biên ảnh hưởng đến cấu trúc kết quả và cần được kiểm tra khi thiết kế regex.

### Delimiter liên tiếp

```java
Pattern comma = Pattern.compile(",");
String input = "a,,b";

System.out.println(Arrays.toString(
        comma.splitWithDelimiters(input, -1)));
// [a, ,, , ,, b]
```

Hai delimiter liên tiếp tạo ra một phần văn bản rỗng ở giữa. Các phần tử rỗng này có ý nghĩa: chúng cho biết trong đầu vào có hai dấu phân cách đứng cạnh nhau.

### Delimiter ở đầu chuỗi

```java
Pattern comma = Pattern.compile(",");
String input = ",alpha,beta";

System.out.println(Arrays.toString(
        comma.splitWithDelimiters(input, -1)));
// [, ,, alpha, ,, beta]
```

Một match có độ rộng dương ngay đầu chuỗi tạo ra phần văn bản rỗng ở trước delimiter. Điều này giúp giữ đúng vị trí delimiter trong chuỗi gốc.

### Zero-width match

Pattern có thể khớp tại một vị trí mà không tiêu thụ ký tự nào, ví dụ lookahead. Một zero-width match ở đầu input không tạo phần tử văn bản rỗng đứng trước nó. Quy tắc này tránh việc sinh ra một chuỗi rỗng dẫn đầu chỉ vì pattern khớp tại vị trí đầu tiên mà không tiêu thụ ký tự.

Ví dụ dùng lookahead để tách trước chữ số:

```java
Pattern beforeDigit = Pattern.compile("(?=\\d)");
String input = "A1B2";

System.out.println(Arrays.toString(
        beforeDigit.splitWithDelimiters(input, -1)));
```

Đây là zero-width delimiter nên các phần tử delimiter được giữ lại dưới dạng chuỗi rỗng. Với pattern zero-width, cần xem kỹ kết quả và kiểm tra các trường hợp input rỗng, match ở đầu hoặc cuối để tránh cấu trúc token khó hiểu. Trong nhiều bài toán, delimiter có độ rộng dương sẽ dễ kiểm soát hơn.

Nếu pattern không khớp input, kết quả là mảng chỉ có một phần tử chứa toàn bộ input. Với input rỗng, kết quả cũng chứa một chuỗi rỗng, trừ trường hợp pattern khớp chuỗi rỗng ngay đầu input theo quy tắc zero-width nói trên.

## 6. Tái sử dụng Pattern thay vì compile regex liên tục

`Pattern.compile(regex)` tạo một đối tượng biểu diễn regular expression đã biên dịch. Nếu cùng regex được sử dụng cho nhiều input, hãy tạo pattern một lần và giữ nó để tái sử dụng.

Không nên:

```java
String[] splitLine(String line) {
    return Pattern.compile("[,;]")
            .splitWithDelimiters(line, 0);
}
```

Mỗi lần gọi `splitLine` lại biên dịch cùng một regex.

Nên:

```java
private static final Pattern FIELD_DELIMITER =
        Pattern.compile("[,;]");

String[] splitLine(String line) {
    return FIELD_DELIMITER.splitWithDelimiters(line, 0);
}
```

`Pattern` là immutable và thread-safe. Có thể dùng chung một instance `static final` cho nhiều request hoặc nhiều thread mà không cần đồng bộ hóa việc gọi `splitWithDelimiters`.

Tái sử dụng `Pattern` đặc biệt hữu ích khi regex phức tạp, được áp dụng thường xuyên hoặc nằm trong đường xử lý có throughput cao. Nó tránh chi phí compile lặp lại và giúp regex trở thành cấu hình rõ ràng của thành phần xử lý.

## 7. Pattern an toàn để chia sẻ, Matcher thì không

`Pattern` mô tả biểu thức đã biên dịch. `Matcher` giữ trạng thái của một lần khớp cụ thể như vị trí hiện tại, nhóm khớp và kết quả lần tìm gần nhất.

- Một `Pattern` có thể được chia sẻ giữa nhiều thread.
- Một `Matcher` không được thiết kế để nhiều thread cùng sử dụng đồng thời.
- Mỗi lần gọi `pattern.matcher(input)` tạo matcher riêng cho input đó.
- Các phương thức `split` và `splitWithDelimiters` thực hiện thao tác tách từ pattern, không yêu cầu ứng dụng chia sẻ matcher toàn cục.

Ví dụ khi cần dùng matcher cho nhiều lần tìm:

```java
private static final Pattern ID_PATTERN =
        Pattern.compile("ID-[A-Z]{2}-\\d{4}");

boolean containsId(String input) {
    return ID_PATTERN.matcher(input).find();
}
```

Mỗi lần gọi `containsId` tạo một `Matcher` mới. Không lưu matcher trong field static rồi dùng lại giữa các request, vì trạng thái của lần tìm trước có thể ảnh hưởng lần tìm sau và không an toàn khi chạy đồng thời.

## 8. Dùng String.splitWithDelimiters khi chỉ cần một lần tách

Java 21 cũng cung cấp `String.splitWithDelimiters(String regex, int limit)`. Đây là cách gọi thuận tiện khi không cần giữ một `Pattern` để tái sử dụng:

```java
String input = "north|south|west";

String[] parts = input.splitWithDelimiters("\\|", -1);
System.out.println(Arrays.toString(parts));
// [north, |, south, |, west]
```

Khi regex được dùng nhiều lần, `Pattern` vẫn phù hợp hơn vì có thể compile một lần. `String.splitWithDelimiters` không thay đổi semantics của `limit`; nó là phương thức tiện ích trên `String` sử dụng regular expression.

## 9. Delimiter literal và Pattern.quote

Đối số của `Pattern.compile` là regular expression, không phải chuỗi delimiter literal. Những ký tự như `.`, `|`, `*`, `+`, `?`, `(`, `)` và `[` có ý nghĩa đặc biệt trong regex.

Nếu delimiter do người dùng hoặc cấu hình cung cấp và cần được hiểu như văn bản nguyên nghĩa, dùng `Pattern.quote`:

```java
String delimiter = "||";
Pattern literalDelimiter = Pattern.compile(Pattern.quote(delimiter));

String input = "left||middle||right";
String[] parts = literalDelimiter.splitWithDelimiters(input, -1);

System.out.println(Arrays.toString(parts));
// [left, ||, middle, ||, right]
```

Không nối trực tiếp delimiter tùy ý vào regex. `Pattern.quote` tránh việc ký tự đặc biệt bị diễn giải thành toán tử regex và giúp xử lý đầu vào cấu hình an toàn hơn.

## 10. Unicode và lớp ký tự trong regular expression

Chuỗi Java lưu dữ liệu dưới dạng UTF-16. Một ký tự Unicode ngoài Basic Multilingual Plane có thể chiếm hai `char` (một surrogate pair), còn một ký tự hiển thị có thể được tạo từ nhiều code point, ví dụ chữ cái kết hợp dấu.

Regex làm việc theo quy tắc Unicode của `Pattern`, nhưng các lớp ký tự viết tắt như `\s`, `\w` và `\d` cần được hiểu theo flag đang bật. Mặc định, các lớp predefined và POSIX có hành vi tương thích ASCII; nếu cần phân loại Unicode, có thể bật `UNICODE_CHARACTER_CLASS` bằng flag `(?U)` hoặc `Pattern.UNICODE_CHARACTER_CLASS`.

Ví dụ tách theo nhóm khoảng trắng Unicode:

```java
Pattern whitespace = Pattern.compile("(?U)\\s+");
String input = "Java\u00A021\tUnicode";

String[] parts = whitespace.splitWithDelimiters(input, -1);
System.out.println(Arrays.toString(parts));
```

Trong ví dụ, `\u00A0` là non-breaking space và `\t` là tab. Flag `(?U)` làm `\s` nhận diện lớp khoảng trắng theo Unicode, phù hợp hơn khi xử lý văn bản có nhiều loại whitespace.

Regex không tự chuẩn hóa Unicode. Hai chuỗi nhìn giống nhau có thể dùng cách mã hóa khác nhau, chẳng hạn một ký tự dựng sẵn hoặc một chữ cái cộng combining mark. Nếu nghiệp vụ yêu cầu so sánh hoặc tách theo dạng chuẩn Unicode, cân nhắc chuẩn hóa bằng `java.text.Normalizer` trước khi xử lý.

```java
import java.text.Normalizer;

String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
```

Không nhầm code point với grapheme cluster: một ký tự mà người dùng nhìn thấy có thể gồm nhiều code point. Nếu yêu cầu là xử lý đơn vị ký tự hiển thị, cần một cách phân đoạn grapheme phù hợp thay vì giả định mỗi `char` hoặc mỗi code point là một ký tự hoàn chỉnh.

## 11. Hiệu năng và an toàn khi dùng regex

Tái sử dụng `Pattern` tránh compile lại regex, nhưng không làm mọi regex trở nên nhanh hoặc an toàn. Thời gian thực thi còn phụ thuộc cấu trúc biểu thức và kích thước input.

Một số nguyên tắc:

1. Compile regex cố định một lần và tái sử dụng `Pattern`.
2. Dùng pattern đơn giản, rõ ràng; tránh các nhóm lặp lồng nhau có thể gây backtracking lớn.
3. Nếu delimiter là literal, dùng `Pattern.quote` thay vì ghép chuỗi regex tùy tiện.
4. Kiểm tra input lớn hoặc không đáng tin cậy; Java regex không cung cấp timeout tổng quát cho một lần match.
5. `limit` giới hạn số lần áp dụng pattern, không giới hạn độ dài input và không phải cơ chế chống ReDoS.
6. Đo hiệu năng với dữ liệu đại diện nếu regex nằm trên đường xử lý nóng.

Nếu cần tách định dạng dữ liệu có quy tắc escape, quote hoặc nested structure, hãy dùng parser chuyên dụng. Ví dụ CSV có dấu phẩy bên trong trường được quote không thể được phân tích đúng bằng cách split đơn giản theo dấu phẩy.

## 12. Ví dụ tổng hợp: phân tích log nhưng vẫn giữ dấu phân cách

Giả sử log dùng dấu `|` để phân chia các trường và bước tiếp theo cần giữ lại separator để tái dựng hoặc đánh dấu vị trí:

```java
import java.util.Arrays;
import java.util.regex.Pattern;

public final class LogTokenizer {
    private static final Pattern PIPE = Pattern.compile("\\|");

    private LogTokenizer() {
    }

    public static String[] tokenize(String line) {
        return PIPE.splitWithDelimiters(line, -1);
    }

    public static void main(String[] args) {
        String line = "2026-11-16|INFO|order-created|orderId=42";
        System.out.println(Arrays.toString(tokenize(line)));
    }
}
```

Kết quả giữ nguyên từng dấu `|` giữa các trường. `PIPE` được compile một lần và dùng lại cho mọi dòng log. Vì `Pattern` immutable, cùng tokenizer có thể được gọi từ nhiều thread mà không chia sẻ một `Matcher` mutable.

Ví dụ này chỉ minh họa việc giữ delimiter. Nếu cần parse log có escaping hoặc trường chứa chính ký tự `|`, hãy định nghĩa format có quoting/escaping và dùng parser tương ứng.

## 13. Tổng kết

`Pattern.splitWithDelimiters` trong Java 21 tách chuỗi theo regular expression và giữ lại toàn bộ delimiter đã khớp xen giữa các phần văn bản. Tham số `limit` điều khiển số lần khớp; với limit dương, pattern được áp dụng tối đa `limit - 1` lần và mảng có tối đa `2 * limit - 1` phần tử. `limit = 0` bỏ chuỗi rỗng ở cuối, còn limit âm giữ chúng.

Để xử lý hiệu quả, hãy compile regex thành `Pattern` một lần rồi tái sử dụng. `Pattern` immutable và thread-safe; tạo `Matcher` riêng cho mỗi lần tìm hoặc xử lý trạng thái khớp. Với dữ liệu Unicode, chú ý lớp ký tự như `\s`, chuẩn hóa Unicode khi nghiệp vụ yêu cầu và không nhầm code point với ký tự hiển thị. Tái sử dụng pattern giúp tránh compile lặp lại, nhưng vẫn cần thiết kế regex an toàn và kiểm tra input thực tế.

## Tài liệu tham khảo

- [Java SE 21 API — Pattern.splitWithDelimiters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html#splitWithDelimiters(java.lang.CharSequence,int)) — semantics của delimiter, limit, trailing empty strings và zero-width match.
- [Java SE 21 API — String.splitWithDelimiters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#splitWithDelimiters(java.lang.String,int)) — phương thức tiện ích trên String được bổ sung trong Java 21.
- [Java SE 21 API — Pattern](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html) — compile, flags, Unicode character classes, Pattern immutability và thread safety.
- [Java SE 21 API — Matcher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Matcher.html) — trạng thái match và lưu ý Matcher không thread-safe.
- [Java SE 21 API — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html) — chuẩn hóa chuỗi Unicode.
