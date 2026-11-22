# Phân biệt phép biến đổi `String` giữ nguyên ý nghĩa với phép làm mất dữ liệu

Một chương trình có thể cần chuẩn hóa tên người dùng trước khi tìm kiếm, loại bỏ khoảng trắng thừa, đổi chữ hoa/chữ thường hoặc thay một ký tự. Những thao tác này thường được gọi chung là *biến đổi chuỗi* (*string transformation*). Tuy nhiên, chúng không có cùng tính chất: có phép biến đổi **giữ nguyên toàn bộ dữ liệu để khôi phục**, có phép chỉ **giữ ý nghĩa theo một quy tắc cụ thể**, và có phép **loại bỏ thông tin vĩnh viễn**.

Ví dụ, `"Cafe\u0301"` (chữ `e` và dấu sắc kết hợp) và `"Caf\u00E9"` (chữ `é` dựng sẵn) là hai biểu diễn Unicode tương đương về mặt chuẩn hóa chính tắc. Chuẩn hóa NFC có thể biến dạng thứ nhất thành dạng thứ hai, nhưng các đơn vị mã ban đầu **không còn giống hệt**. Ngược lại, việc xóa dấu trong tên riêng có thể khiến nhiều tên khác nhau thành cùng một kết quả: không thể từ chuỗi mới đoán chính xác chuỗi ban đầu.

Bài học này giúp bạn xác định rõ **thông tin nào phải được giữ lại**, **thế nào là “cùng ý nghĩa” trong bài toán**, và **khi nào nên giữ bản gốc cùng với chuỗi đã chuẩn hóa**.

## 1. Hai câu hỏi khác nhau: giữ nguyên dữ liệu hay giữ nguyên ý nghĩa?

Giả sử có phép biến đổi `T` từ `String` đầu vào sang `String` đầu ra. Trước khi đánh giá `T`, hãy hỏi:

1. **Giữ nguyên dữ liệu (*lossless / reversible*)?** Từ kết quả và thông tin cần thiết kèm theo, có khôi phục **chính xác** dãy dữ liệu gốc hay không? Nếu `T(x) == T(y)` với hai đầu vào khác nhau mà không lưu thêm thông tin, phép biến đổi không thể đảo ngược hoàn toàn.
2. **Giữ nguyên ý nghĩa (*semantic equivalence*)?** Sau biến đổi, dữ liệu có còn được coi là “giống nhau” theo **quy tắc nghiệp vụ đã xác định** hay không?

Hai câu hỏi **không đồng nghĩa**. Một phép biến đổi có thể không phục hồi được nguyên văn, nhưng vẫn bảo toàn ý nghĩa cho một tác vụ cụ thể như tìm kiếm không phân biệt hoa/thường. Ngược lại, có thể mã hóa dữ liệu theo một dạng khác rồi giải mã chính xác, dù biểu diễn trung gian không được dùng trực tiếp như văn bản.

### Ba mức độ thường gặp

| Mức độ | Ví dụ | Điều đảm bảo và giới hạn |
| --- | --- | --- |
| **Bảo toàn dữ liệu, có thể hoàn nguyên** | Mã hóa byte UTF-8 thành Base64 rồi giải mã với đúng quy trình | Có thể lấy lại dãy byte ban đầu; nếu mã hóa `String`, cần bảo đảm chuỗi hợp lệ với encoding đã chọn và không bị thay thế ký tự lỗi. |
| **Bảo toàn ý nghĩa theo quy tắc, có thể đổi biểu diễn** | Chuẩn hóa Unicode dạng NFC để so khớp văn bản tương đương chính tắc | Có thể đổi dãy đơn vị mã UTF-16; không hứa khôi phục nguyên văn đầu vào. |
| **Có thể mất thông tin hoặc thay đổi ý nghĩa** | Xóa dấu, xóa khoảng trắng, cắt chuỗi, thay nhiều ký tự thành một | Các đầu vào khác nhau có thể cho cùng đầu ra hoặc thông tin cần thiết bị loại bỏ. |

**Không tồn tại một định nghĩa “giữ nguyên ý nghĩa” áp dụng cho mọi ứng dụng.** `" A "` và `"A"` có thể tương đương trong ô tìm kiếm, nhưng **khác nhau** nếu đang lưu mật khẩu, nội dung mã nguồn, dữ liệu văn bản cần kiểm toán hoặc một định danh có quy tắc phân biệt khoảng trắng.

## 2. `String` immutable không có nghĩa phép biến đổi là lossless

Đối tượng `String` của Java bất biến: khi gọi `strip()`, `replace()`, `toLowerCase()` hoặc `substring()`, nội dung của đối tượng gốc không bị sửa. Phương thức trả về kết quả chuỗi, có thể là đối tượng mới hoặc chính đối tượng hiện tại nếu nội dung không đổi.

```java
String original = "  Java  ";
String transformed = original.strip();

System.out.println("original = [" + original + "]");
System.out.println("transformed = [" + transformed + "]");
```

Kết quả:

```text
original = [  Java  ]
transformed = [Java]
```

**Chuỗi gốc vẫn còn nguyên** trong biến `original`, nhưng riêng `transformed` không chứa thông tin về số khoảng trắng đã bị bỏ. Nếu chương trình chỉ lưu `transformed` rồi loại bỏ `original`, sự khác biệt ở hai đầu đã bị mất.

Nói cách khác:

- **Tính bất biến**: thao tác không chỉnh sửa đối tượng `String` đã tồn tại.
- **Tính đảo ngược**: có thể khôi phục chính xác dữ liệu đầu vào từ đầu ra không?
- **Tính tương đương ngữ nghĩa**: ứng dụng có coi đầu ra và đầu vào là cùng một giá trị không?

Đây là ba thuộc tính độc lập cần phân biệt khi thiết kế dữ liệu.

## 3. Chuẩn hóa Unicode: giữ tương đương chính tắc nhưng đổi biểu diễn

Unicode cho phép một số văn bản có nhiều biểu diễn. Chẳng hạn:

- `"\u00E9"`: ký tự `é` dựng sẵn, một UTF-16 code unit.
- `"e\u0301"`: ký tự `e` theo sau bởi dấu sắc kết hợp, hai UTF-16 code units.

Hai biểu diễn này là **canonically equivalent** theo Unicode; với `String.equals()`, chúng vẫn **không bằng nhau** vì `equals()` so sánh dãy đơn vị mã chính xác.

Java có lớp `java.text.Normalizer`:

- `Normalizer.Form.NFC`: biểu diễn chuẩn hóa kết hợp theo quy tắc chính tắc.
- `Normalizer.Form.NFD`: biểu diễn chuẩn hóa phân rã theo quy tắc chính tắc.
- `Normalizer.Form.NFKC` và `NFKD`: chuẩn hóa tương thích, có thể hợp nhất nhiều ký tự **vốn mang khác biệt về hình thức hoặc ý nghĩa sử dụng**.

Ví dụ:

```java
String decomposed = "Cafe\u0301";
String composed = "Caf\u00E9";

String nfc = java.text.Normalizer.normalize(
        decomposed, java.text.Normalizer.Form.NFC);

System.out.println(decomposed.equals(composed)); // false
System.out.println(nfc.equals(composed));        // true
```

Chuẩn hóa NFC/NFD thường phù hợp để so sánh theo **tương đương chính tắc**. Tuy nhiên, dù người dùng xem đó là cùng chữ, dãy code units có thể thay đổi; nếu hệ thống cần lưu chính xác dữ liệu đã nhập, vẫn phải giữ **giá trị gốc**.

### Trường hợp cần đặc biệt thận trọng: NFKC / NFKD

Chuẩn hóa tương thích có thể xóa những phân biệt mà ứng dụng cần giữ. Ví dụ ký tự số được khoanh `①` có thể được chuẩn hóa dạng NFKC thành `1`:

```java
String circled = "\u2460"; // ①
String compatibility = java.text.Normalizer.normalize(
        circled, java.text.Normalizer.Form.NFKC);

System.out.println(compatibility);           // 1
System.out.println(circled.equals(compatibility)); // false
```

Nếu văn bản là nội dung cần in chính xác, một biểu tượng liệt kê, công thức hoặc mã nhận diện đặc biệt, thay `①` thành `1` có thể thay đổi thông tin hữu ích. Đừng chọn NFKC chỉ vì muốn “chuẩn hóa mạnh hơn”; hãy xác định hợp đồng dữ liệu trước.

**Lưu ý:** Chuẩn hóa Unicode không đồng nghĩa chuyển hết về ASCII, bỏ dấu, dịch ngôn ngữ hay tự phát hiện ký tự người dùng nhìn giống nhau. Một số ký tự trông tương tự nhưng không tương đương theo chuẩn Unicode.

## 4. Đổi chữ hoa/thường: thuận tiện cho tra cứu, có thể mất dữ liệu

`toLowerCase()` và `toUpperCase()` thường dùng để tạo **khóa tìm kiếm**:

```java
String displayName = "Java API";
String lookupKey = displayName.toLowerCase(java.util.Locale.ROOT);

System.out.println(displayName); // Java API
System.out.println(lookupKey);   // java api
```

Trong hệ thống tìm kiếm được định nghĩa **không phân biệt chữ hoa/thường**, hai giá trị có thể cùng một ý nghĩa tra cứu. Nhưng `lookupKey` không giữ thông tin chữ nào vốn được viết hoa. Ví dụ các chuỗi `"Java"`, `"JAVA"` và `"java"` có thể biến thành cùng khóa `"java"`. Do đó đây **không phải phép biến đổi đảo ngược** từ kết quả đơn lẻ.

Ngoài ra, chuyển hoa/thường có quy tắc Unicode và phụ thuộc ngôn ngữ:

```java
String capitalI = "I";
System.out.println(
    capitalI.toLowerCase(java.util.Locale.ROOT)); // i
System.out.println(
    capitalI.toLowerCase(java.util.Locale.forLanguageTag("tr"))); // ı
```

Với tiếng Thổ Nhĩ Kỳ, `I` chuyển thường có thể thành `ı` (chữ i không chấm), khác với quy tắc dùng `Locale.ROOT`. Một số phép đổi chữ còn có thể làm **thay đổi số code points**.

Cách chọn:

- Dùng `Locale.ROOT` khi cần quy tắc độc lập ngôn ngữ để tạo khóa kỹ thuật **và** quy tắc đó thật sự phù hợp dữ liệu.
- Dùng locale tương ứng khi xử lý văn bản người dùng theo ngôn ngữ cụ thể.
- Cân nhắc `equalsIgnoreCase()` khi mục đích chỉ là so sánh bỏ qua hoa/thường theo hợp đồng Java, nhưng **đừng đồng nhất nó với toàn bộ thuật toán Unicode case folding hoặc so khớp ngôn ngữ tự nhiên**.
- Đừng tự động `toLowerCase()` khi lưu mã định danh, mật khẩu hoặc chữ ký số nếu hợp đồng yêu cầu giữ nguyên chữ hoa/thường.

## 5. Loại khoảng trắng: khi nào là làm sạch, khi nào là xóa dữ liệu?

Các API thường gặp:

| API | Tác động | Rủi ro về thông tin |
| --- | --- | --- |
| `strip()` (Java 11+) | Bỏ ký tự whitespace ở **đầu và cuối** theo `Character.isWhitespace` | Mất chính xác số và loại whitespace đã bỏ. |
| `trim()` | Bỏ các đơn vị mã ở đầu/cuối có giá trị không lớn hơn U+0020 | Tiêu chí khác `strip()`; không phải quy tắc Unicode whitespace tổng quát. |
| `stripLeading()` / `stripTrailing()` | Chỉ bỏ ở một phía | Có thể xóa khoảng trắng có nghĩa ở phía đó. |
| `replace("  ", " ")` | Thay đúng hai dấu cách liên tiếp bằng một dấu cách mỗi lần khớp | Mất phân biệt một hay hai dấu cách; không phải thuật toán gộp mọi loại whitespace. |
| `replaceAll(regex, replacement)` | Thay các chuỗi khớp biểu thức chính quy | Có thể xóa nhiều ký tự khác nhau; cần hiểu cú pháp regex và escape. |

Ví dụ `"  A  B  ".strip()` trả `"A  B"`. Việc bỏ hai dấu cách hai bên có thể chấp nhận được nếu đó là lỗi nhập liệu; nhưng nếu văn bản thuộc định dạng cố định theo cột, khoảng trắng đầu/cuối có thể là một phần dữ liệu.

Nếu tiếp tục `"A  B".replace("  ", " ")`, kết quả là `"A B"`. Không còn cách phân biệt chắc chắn nó xuất phát từ `"A  B"` hay `"A B"` nếu chỉ còn đầu ra `"A B"`.

Không nên mặc định “whitespace vô nghĩa”. Với một đoạn mã nguồn, tệp văn bản, chuỗi trong báo cáo hoặc mật khẩu, khoảng trắng có thể mang ý nghĩa quan trọng. Với trường tên hiển thị, tìm kiếm hoặc tag, quy tắc loại bỏ whitespace có thể phù hợp **nếu sản phẩm đã xác định rõ**.

### Phân biệt `isEmpty()` và `isBlank()`

`isEmpty()` kiểm tra `length() == 0`; `isBlank()` kiểm tra chuỗi rỗng hoặc chỉ chứa code points mà `Character.isWhitespace()` coi là whitespace. Hai hàm chỉ **kiểm tra**, không biến đổi chuỗi.

```java
String spaces = " \t";
System.out.println(spaces.isEmpty()); // false
System.out.println(spaces.isBlank()); // true
```

Trong nhiều biểu mẫu, `isBlank()` thích hợp để phát hiện đầu vào chỉ chứa whitespace. Nhưng tiêu chí `Character.isWhitespace()` không bao trùm tất cả ký tự có hình dạng giống khoảng trắng (chẳng hạn một số non-breaking spaces); nếu cần chuẩn hóa toàn bộ khoảng trắng trong văn bản quốc tế, phải đặc tả thêm chính sách.

## 6. Cắt, xóa, thay thế và rút gọn: các phép biến đổi dễ mất dữ liệu

Những phương thức như `substring()`, `replace()`, `replaceAll()` có thể giúp tạo định dạng mới, nhưng tính đảo ngược **không được đảm bảo**.

### Cắt chuỗi

```java
String code = "ORDER-2026-001";
String suffix = code.substring(code.length() - 3);

System.out.println(suffix); // 001
```

Nếu chỉ lưu `"001"`, không thể biết mã gốc là `"ORDER-2026-001"`, `"USER-001"` hay một giá trị khác. Đây là phép **chỉ giữ một phần thông tin**. Một ví dụ khác là giới hạn hiển thị bằng `substring(0, max)`; nó có thể bỏ đi phần nội dung cần thiết.

**Chỉ số `substring()` tính theo UTF-16 code units**. Không cắt tùy tiện giữa hai phần của surrogate pair (ví dụ nhiều emoji), vì điều đó có thể tạo chuỗi chứa surrogate đơn lẻ. Nếu mục tiêu là giới hạn số ký tự người dùng nhìn thấy, cần xử lý grapheme clusters, không chỉ `length()`.

### Xóa hoặc hợp nhất ký tự

```java
String withDash = "AB-12";
String noDash = withDash.replace("-", "");

System.out.println(noDash); // AB12
```

Từ `"AB12"` không thể xác định liệu đầu vào đã chứa dấu gạch ngang hay chưa, hoặc dấu đó ở vị trí nào. Việc xóa dấu chỉ giữ “ý nghĩa” nếu **quy tắc mã** nói dấu phân cách không mang ý nghĩa và không cần khôi phục.

Ví dụ xóa dấu tiếng Việt để tìm kiếm cũng có thể làm nhiều từ khác nhau trở thành cùng một khóa. Bỏ dấu có thể phù hợp cho **chỉ mục tìm kiếm phụ**, nhưng không nên thay dữ liệu gốc nếu tên riêng và dấu thanh có ý nghĩa.

### `replace()` khác `replaceAll()`

`String.replace(CharSequence, CharSequence)` tìm chuỗi con **nguyên văn**; `replaceAll(String regex, String replacement)` hiểu đối số thứ nhất là **biểu thức chính quy**.

```java
String value = "a.b";
System.out.println(value.replace(".", ""));    // ab
System.out.println(value.replaceAll(".", "")); // chuỗi rỗng
```

Với `replaceAll(".", "")`, dấu chấm trong regex có nghĩa là khớp gần như mọi ký tự đơn, nên toàn bộ các ký tự `a.b` bị loại. Đây là lỗi điển hình khi nhầm chuỗi nguyên văn với regex.

Hãy kiểm tra kỹ quy tắc thay thế (đặc biệt khi tham số đến từ người dùng), vì một regex hoặc replacement không đúng có thể xóa nhiều nội dung ngoài dự kiến. Thao tác xóa dữ liệu cần được xem là một quyết định nghiệp vụ có chủ đích.

## 7. Mã hóa và giải mã có thể hoàn nguyên, nhưng phải xác định miền dữ liệu

Một phép mã hóa như Base64 chỉ đổi biểu diễn của **dãy byte**: khi mã hóa và giải mã đúng cách, các byte được giữ nguyên. Đối với `String`, cần chọn charset nhất quán (thường là UTF-8) trước và sau bước Base64.

```text
String → UTF-8 bytes → Base64 text
                    ← decode Base64 ←
String ← UTF-8 bytes ←
```

Với một `String` chứa dãy Unicode well-formed và không có lỗi chuyển mã, bước này có thể khôi phục chính xác văn bản ban đầu. Nhưng Java `String` có thể chứa surrogate đơn lẻ không hợp lệ; một encoder UTF-8 mặc định có thể **thay thế** dữ liệu lỗi, khiến hành trình chuyển mã không còn hoàn nguyên. Nếu yêu cầu lưu toàn bộ **mọi** dãy UTF-16 code units có thể có trong Java (bao gồm cả chuỗi lỗi), phải chọn biểu diễn/protocol và chính sách lỗi hỗ trợ mục tiêu đó.

Base64 **không phải mã hóa bảo mật**; bất cứ ai có chuỗi Base64 đều có thể giải mã. Nó chỉ là dạng biểu diễn có thể khôi phục byte.

So sánh với:

- **Hash** là phép ánh xạ một chiều theo mục đích sử dụng, không phải công cụ khôi phục văn bản gốc.
- **Cắt chuỗi** loại bỏ nội dung nên không thể khôi phục khi không còn bản gốc.
- **Chuẩn hóa Unicode** có thể làm nhiều biểu diễn gốc khác nhau thành một dạng chuẩn; hữu ích cho so sánh nhưng không bảo đảm tái tạo chuỗi nguyên trạng.
- **Chuyển hoa/thường** có thể phục vụ tra cứu nhưng làm mất thông tin cách viết nếu không lưu riêng.

## 8. Ví dụ Java 17+ số 1: chuẩn hóa, xóa khoảng trắng và hợp nhất giá trị

Tạo tệp `StringTransformationDemo.java`:

```java
import java.text.Normalizer;
import java.util.Locale;

public class StringTransformationDemo {
    public static void main(String[] args) {
        String decomposed = "Cafe\u0301";
        String composed = "Caf\u00E9";

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);

        System.out.println("rawEquals = " + decomposed.equals(composed));
        System.out.println(
                "nfcEquals = " + normalized.equals(composed));
        System.out.println("rawLength = " + decomposed.length());
        System.out.println("nfcLength = " + normalized.length());

        String input = "  A  B  ";
        String stripped = input.strip();
        String collapsed = stripped.replace("  ", " ");

        System.out.println("inputLength = " + input.length());
        System.out.println("stripped = [" + stripped + "]");
        System.out.println("collapsed = [" + collapsed + "]");

        String display = "Java";
        String lookup = display.toLowerCase(Locale.ROOT);
        System.out.println("display = " + display);
        System.out.println("lookup = " + lookup);

        String compat = Normalizer.normalize(
                "\u2460", Normalizer.Form.NFKC);
        System.out.println("nfkcCircledOne = " + compat);
        System.out.println("nfkcSameText = " + "\u2460".equals(compat));
    }
}
```

Biên dịch và chạy:

```bash
javac StringTransformationDemo.java
java StringTransformationDemo
```

Kết quả:

```text
rawEquals = false
nfcEquals = true
rawLength = 5
nfcLength = 4
inputLength = 8
stripped = [A  B]
collapsed = [A B]
display = Java
lookup = java
nfkcCircledOne = 1
nfkcSameText = false
```

Giải thích:

- `Normalizer.Form.NFC` (được dùng qua `Normalizer.Form.NFC` trong mã) chuyển biểu diễn Unicode chính tắc về một dạng để so sánh. Nội dung hiển thị tương đương, nhưng độ dài theo UTF-16 giảm từ 5 xuống 4.
- `strip()` và `replace()` đều **không sửa** đối tượng `String input`; chúng trả kết quả không còn chứa một phần thông tin whitespace.
- Chuyển `Java` thành `java` giúp tạo khóa tra cứu theo quy tắc bỏ hoa/thường, nhưng không thể từ `java` biết bản gốc viết hoa chữ nào.
- NFKC chuyển `①` thành `1`. Vì hai biểu diễn có thể quan trọng khác nhau trong văn bản gốc, phép này cần lựa chọn có chủ đích.

## 9. Ví dụ Java 17+ số 2: phép hoàn nguyên và phép tạo va chạm

Tạo tệp `RoundTripVsLossDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;

public class RoundTripVsLossDemo {
    public static void main(String[] args) {
        String original = "A\nB,\uD83D\uDE00";

        byte[] bytes = original.getBytes(StandardCharsets.UTF_8);
        String encoded = Base64.getEncoder().encodeToString(bytes);
        byte[] decodedBytes = Base64.getDecoder().decode(encoded);
        String restored = new String(decodedBytes, StandardCharsets.UTF_8);

        System.out.println(
                "sameBytes = " + Arrays.equals(bytes, decodedBytes));
        System.out.println("sameString = " + original.equals(restored));

        String first = "A,B";
        String second = "AB";
        String transformedFirst = first.replace(",", "");
        String transformedSecond = second.replace(",", "");

        System.out.println(
                "originalsEqual = " + first.equals(second));
        System.out.println(
                "transformedEqual = "
                + transformedFirst.equals(transformedSecond));
    }
}
```

Biên dịch và chạy:

```bash
javac RoundTripVsLossDemo.java
java RoundTripVsLossDemo
```

Kết quả:

```text
sameBytes = true
sameString = true
originalsEqual = false
transformedEqual = true
```

Ý nghĩa:

- Dãy byte UTF-8 được Base64 mã hóa/giải mã và giữ lại **đúng từng byte**, nên với chuỗi Unicode hợp lệ trong ví dụ, `String` được khôi phục chính xác.
- `"A,B"` và `"AB"` vốn là **hai đầu vào khác nhau**; sau khi xóa dấu phẩy, cả hai thành `"AB"`. Đây là **va chạm do biến đổi** (*collision*). Từ đầu ra `"AB"` không thể biết ban đầu có dấu phẩy hay không.

Nếu có khả năng nhiều đầu vào khác nhau cùng thành một đầu ra, đừng dùng đầu ra đó như một bản ghi dữ liệu gốc có khả năng khôi phục, trừ khi bạn **lưu thêm đủ thông tin để phân biệt**.

## 10. Thiết kế quy trình lưu trữ và tra cứu an toàn

Một cách làm phổ biến là lưu **giá trị gốc** và sinh thêm **giá trị chuẩn hóa phục vụ tác vụ**:

```text
Dữ liệu nhập ──────────────► original (lưu để hiển thị / kiểm toán)
           │
           └─► kiểm tra chính sách ─► chuẩn hóa có chủ đích
                                      │
                                      └─► searchKey (tìm kiếm / chỉ mục)
```

Ví dụ minh họa bằng một hàm tạo khóa tìm kiếm:

```java
import java.text.Normalizer;
import java.util.Locale;

public final class SearchKey {
    private SearchKey() {}

    public static String of(String value) {
        if (value == null) {
            throw new IllegalArgumentException("value must not be null");
        }
        return Normalizer.normalize(value, Normalizer.Form.NFC)
                .strip()
                .toLowerCase(Locale.ROOT);
    }
}
```

Tệp `SearchKey.java` trên biên dịch được bằng `javac SearchKey.java` và không có `main()`; nó là **lớp tiện ích**, được gọi từ chương trình khác.

Giải thích quy trình:

1. **Kiểm tra `null`** thay vì mặc định coi `null` là `""`: tùy nghiệp vụ, hai trạng thái này có thể khác nhau.
2. **Chuẩn hóa NFC** để biểu diễn Unicode tương đương chính tắc được xử lý nhất quán.
3. **`strip()`** bỏ khoảng trắng biên theo chính sách đã chọn. Không dùng nếu khoảng trắng biên có ý nghĩa.
4. **`toLowerCase(Locale.ROOT)`** tạo khóa không phân biệt một số khác biệt hoa/thường theo một quy tắc độc lập locale người chạy. Nó không phải giải pháp tổng quát cho mọi ngôn ngữ và mọi tiêu chuẩn so khớp Unicode.

Đây chỉ là **ví dụ quy tắc cho chức năng tìm kiếm**. Không tự động áp dụng chuỗi biến đổi này cho mật khẩu, chữ ký số, nội dung tài liệu chính xác hoặc định danh có quy tắc so khớp khác. Nếu lưu khóa để index, cần lưu/đối chiếu bản gốc và xác định rõ chính sách xử lý trường hợp **nhiều bản gốc cùng khóa**.

### Có nên áp dụng biến đổi trước hay sau khi kiểm tra dữ liệu?

Phụ thuộc điều kiện kiểm tra. Ví dụ, một trường bắt buộc “không blank” có thể kiểm tra giá trị nhập rồi quyết định có cho phép `strip()`. Nhưng nếu một định danh cấm khoảng trắng hoàn toàn, tự `strip()` trước rồi chấp nhận có thể che mất lỗi nhập.

**Không dùng chuẩn hóa để che lỗi dữ liệu chưa được định nghĩa.** Hãy viết rõ: cái gì được tự sửa, cái gì phải báo lỗi, cái gì được lưu nguyên trạng và cái gì chỉ dùng để tìm kiếm.

## 11. Các thuộc tính cần kiểm thử khi viết hàm biến đổi chuỗi

Bên cạnh ví dụ input/output, có thể kiểm tra:

| Thuộc tính | Câu hỏi kiểm thử |
| --- | --- |
| **Giữ nguyên bản gốc** | Sau khi gọi API, biến `String` và nội dung gốc còn nguyên không? |
| **Hoàn nguyên** | Nếu yêu cầu lossless, `decode(encode(s)).equals(s)` có đúng cho **toàn miền đầu vào được hỗ trợ** không? |
| **Không có va chạm không mong muốn** | Có hai đầu vào khác nhau `a`, `b` mà `T(a).equals(T(b))` không? Nếu có, nghiệp vụ có chấp nhận gộp chúng không? |
| **Tính idempotent** | Khi mong đợi chuẩn hóa ổn định, `T(T(s)).equals(T(s))` có đúng không? |
| **Unicode** | Có xử lý dấu kết hợp, emoji, ký tự ngoài BMP, khoảng trắng đặc biệt và locale không? |
| **Biên** | `null`, `""`, toàn whitespace, chuỗi rất dài, dấu phân cách lặp lại được xử lý theo chính sách nào? |
| **Chuẩn so sánh** | Cần so sánh nguyên văn, NFC, bỏ hoa/thường, so sánh theo locale hay so sánh theo một quy tắc nghiệp vụ khác? |

Tính **idempotent** chỉ nói rằng áp dụng nhiều lần cho cùng kết quả như áp dụng một lần; nó **không chứng minh phép biến đổi không mất dữ liệu**. Ví dụ `strip()` thường idempotent nhưng vẫn xóa khoảng trắng đầu/cuối. Tương tự, một phép biến đổi có thể đảo ngược được trên một miền dữ liệu hẹp, nhưng làm mất thông tin nếu mở rộng sang các ký tự khác.

## 12. Các lỗi tư duy và cách tránh

1. **“`String` immutable nên `replace()` không làm mất thông tin.”** Sai. Đối tượng gốc không bị thay đổi, nhưng kết quả có thể làm mất dữ liệu nếu không lưu đầu vào.
2. **“Cứ chuẩn hóa là bảo toàn mọi ý nghĩa.”** Sai. NFC/NFD là chuẩn hóa theo tương đương chính tắc, còn NFKC/NFKD có thể gộp những phân biệt mà ứng dụng muốn giữ.
3. **“Chữ thường chỉ là cách hiển thị khác của chữ hoa, luôn đảo ngược được.”** Sai. Nhiều cách viết hoa/thường có thể cho cùng dạng chuẩn hóa; quy tắc còn phụ thuộc locale.
4. **“Khoảng trắng luôn vô nghĩa.”** Sai. Khoảng trắng có thể là dữ liệu trong mật khẩu, nội dung mã nguồn, CSV, văn bản hoặc định dạng có quy tắc cố định.
5. **“Chỉ cần bỏ dấu là tìm kiếm tiếng Việt sẽ luôn đúng.”** Không chắc. Bỏ dấu gây va chạm giữa từ khác nhau; ngôn ngữ tự nhiên còn có quy tắc phát âm, phân đoạn và so khớp riêng.
6. **“`replaceAll(".", "")` chỉ xóa dấu chấm.”** Sai. Dấu `.` trong regex thường khớp gần như mọi ký tự; dùng `replace(".", "")` để thay dấu chấm nguyên văn.
7. **“Base64 là mã hóa bảo mật.”** Sai. Base64 là biểu diễn có thể giải mã dễ dàng, không bảo đảm bí mật.
8. **“`getBytes(UTF_8)` rồi tạo lại `String` sẽ luôn hoàn nguyên mọi dãy UTF-16.”** Không đúng với đầu vào chứa surrogate lỗi và cơ chế thay thế dữ liệu mã hóa mặc định.
9. **“Một phép biến đổi idempotent chắc chắn lossless.”** Sai. Cắt và strip có thể idempotent nhưng làm mất dữ liệu.
10. **“Một khóa tìm kiếm bằng nhau nghĩa là hai bản gốc giống hệt.”** Sai nếu quy tắc tạo khóa gộp nhiều đầu vào, chẳng hạn bỏ hoa/thường, bỏ dấu hoặc whitespace.

## 13. Bài tập tự kiểm tra

**Bài 1.** Kết quả của `" A ".strip()` là `"A"`. Phép biến đổi có giữ nguyên dãy ký tự không?

Không. Hai dấu cách đầu/cuối bị bỏ; nếu chỉ còn `"A"`, không thể biết đầu vào có khoảng trắng hay không. Trong một biểu mẫu xem whitespace biên là không đáng kể, nó có thể **giữ nguyên ý nghĩa theo quy tắc của biểu mẫu**, nhưng vẫn không giữ nguyên dữ liệu.

**Bài 2.** `"Cafe\u0301"` và `"Caf\u00E9"` có `String.equals()` là `true` không? Sau khi chuẩn hóa cả hai bằng NFC thì sao?

Trước chuẩn hóa, `equals()` là `false` do khác dãy UTF-16. Sau NFC, chúng so sánh bằng nhau theo `equals()`. Điều đó không có nghĩa bạn có thể từ chuỗi NFC tái tạo chính xác biểu diễn đầu vào trước chuẩn hóa.

**Bài 3.** `"ADMIN"` và `"admin"` cùng biến thành `"admin"` sau `toLowerCase(Locale.ROOT)`. Có nên dùng kết quả ấy làm dữ liệu hiển thị chính?

Chỉ khi sản phẩm **muốn mất phân biệt hoa/thường khi hiển thị**. Nếu cần giữ kiểu viết tên, nên lưu giá trị gốc và chỉ dùng chuỗi chuyển thường làm khóa tìm kiếm.

**Bài 4.** Hai mã `"AB-12"` và `"AB12"` cùng thành `"AB12"` sau khi xóa dấu gạch ngang. Có đủ thông tin để khôi phục mã gốc không?

Không. Có **va chạm** vì hai đầu vào khác nhau cùng một đầu ra. Việc xóa dấu chỉ an toàn cho định danh nếu hợp đồng hệ thống chấp nhận hai dạng là cùng mã và không cần khôi phục dạng nhập.

**Bài 5.** Một dữ liệu cần được lưu để in lại **từng ký tự y nguyên**, nhưng hệ thống cũng muốn tìm kiếm không phân biệt hoa/thường. Thiết kế nào phù hợp?

Lưu **bản gốc** phục vụ hiển thị/in lại; tạo riêng **khóa tìm kiếm được chuẩn hóa theo chính sách rõ ràng**. Khi kết quả tìm kiếm có nhiều bản gốc cùng khóa, phải có cách phân biệt chúng trong dữ liệu chính.

## Kết luận

Đừng đánh giá phép biến đổi chuỗi chỉ bằng việc đầu ra “trông có vẻ giống” đầu vào. Hãy xác định rõ:

- **Phải phục hồi đúng dữ liệu gốc?** Chọn biểu diễn/quy trình có khả năng hoàn nguyên trên toàn miền dữ liệu hỗ trợ, kiểm tra round-trip và giữ đúng encoding.
- **Chỉ cần tương đương cho một tác vụ?** Định nghĩa quy tắc tương đương đó (Unicode, hoa/thường, khoảng trắng, dấu phân cách, locale) rồi chuẩn hóa nhất quán.
- **Có thể làm mất thông tin?** Giữ bản gốc hoặc chủ động chấp nhận mất mát theo yêu cầu nghiệp vụ; kiểm thử va chạm và dữ liệu ở biên.

Bởi `String` là immutable, các biến đổi trả kết quả riêng mà không sửa đối tượng gốc. Nhưng **immutable không có nghĩa mọi kết quả là lossless**: tính đúng đắn nằm ở hợp đồng dữ liệu và mục tiêu của từng phép biến đổi.

## Tài liệu tham khảo

- [Java SE 21 API — `java.lang.String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `strip`, `trim`, `toLowerCase`, `replace`, `replaceAll`, `substring`, `equals`.
- [Java SE 21 API — `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html): NFC, NFD, NFKC, NFKD và Unicode normalization.
- [Java SE 21 API — `java.nio.charset.StandardCharsets`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn, gồm UTF-8.
- [Java SE 21 API — `java.util.Base64`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Base64.html): biểu diễn/giải mã Base64 cho byte.
