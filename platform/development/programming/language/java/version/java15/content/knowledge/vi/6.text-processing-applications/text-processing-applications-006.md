# So sánh kết quả chuỗi chính xác và chuẩn hóa có chủ đích trong Java

> **Bối cảnh:** Chủ đề “Ứng dụng văn bản” thuộc module Java 15, nhưng bài thực hành dùng API Java **đã chuẩn hóa và vẫn còn hiệu lực** trên JDK 17, 21, 25 và các dòng JDK hiện đại. Trọng tâm là chọn đúng **tiêu chí so sánh**: so sánh chính xác toàn bộ `String` khi từng ký tự có ý nghĩa, hoặc chuẩn hóa **có mục đích rõ ràng** khi đặc tả cho phép một số khác biệt biểu diễn.

## 1. Hai loại yêu cầu cần phân biệt

Giả sử hệ thống tạo một email, đoạn JSON, bản ghi log hoặc kết quả text block. Hai chuỗi có thể **trông giống nhau trên màn hình** nhưng khác nhau ở:

- Khoảng trắng đầu dòng hoặc cuối dòng.
- Một hay nhiều dấu cách liên tiếp.
- Dấu xuống dòng `\n` (LF) so với `\r\n` (CRLF).
- Có hoặc không có newline cuối tài liệu.
- Chữ có dấu ở dạng Unicode **composed** hoặc **decomposed**.
- Khác biệt chữ hoa/chữ thường, tab so với spaces, hoặc ký tự không nhìn thấy.

Từ đó có hai chính sách:

| Chính sách | Ý nghĩa | Ví dụ phù hợp |
| --- | --- | --- |
| **So sánh chính xác (exact)** | Hai giá trị `String` phải chứa cùng chuỗi đơn vị mã UTF-16 theo cùng thứ tự | Kiểm thử định dạng đầu ra cố định, kiểm tra delimiter, xác nhận newline, chuỗi định danh mà quy tắc yêu cầu so khớp tuyệt đối |
| **So sánh sau chuẩn hóa đã quy định** | Trước khi so sánh, áp dụng **cùng một hàm chuẩn hóa đã xác định** cho hai phía; chỉ bỏ qua các khác biệt mà hợp đồng dữ liệu công nhận là tương đương | Tài liệu văn bản cho phép LF/CRLF, dữ liệu Unicode cần canonical equivalence, nhãn nhập liệu cho phép khoảng trắng ở hai đầu |

**Không có “chuẩn hóa tốt nhất” cho mọi chuỗi.** Nếu dấu cách hoặc newline là một phần của dữ liệu có ý nghĩa, xóa chúng để một phép thử chạy qua sẽ che giấu lỗi. Ngược lại, với đầu vào được đặc tả là không phân biệt CRLF và LF, so sánh chính xác có thể báo khác biệt biểu diễn không quan trọng.

## 2. So sánh chính xác bằng `equals()`

`String.equals(Object)` trả về `true` khi đối số cũng là `String` và có **đúng cùng dãy ký tự UTF-16**; độ dài và từng vị trí phải bằng nhau.

```java
String expected = "OK\n";
String actual = "OK";
boolean same = expected.equals(actual); // false
```

Chỉ một ký tự xuống dòng cuối đã khiến hai chuỗi khác nhau.

Phân biệt ba cách thường gặp:

```java
String x = new String("Ready");
String y = "Ready";

System.out.println(x.equals(y));                  // true
System.out.println(x == y);                       // false
System.out.println(java.util.Objects.equals(x,y)); // true
```

- **`equals`** kiểm tra **nội dung** theo quy tắc chính xác của `String`.
- **`==`** kiểm tra hai biến có trỏ đến **cùng đối tượng** hay không. Việc hai literal có thể dùng chung đối tượng nhờ intern **không** biến `==` thành công cụ so sánh nội dung.
- **`Objects.equals(a, b)`** kiểm tra nội dung nhưng **an toàn khi có `null`**: hai giá trị `null` cho `true`, một phía `null` và một phía không `null` cho `false`.
- Nếu `expected` chắc chắn không `null`, `expected.equals(actual)` đơn giản và dễ đọc. Nếu cả hai có thể `null`, dùng `Objects.equals(expected, actual)`.

`String.equalsIgnoreCase` phục vụ **so sánh không phân biệt hoa/thường** với quy tắc của Java; nó **không** đồng nghĩa “so sánh văn bản đã chuẩn hóa hoàn toàn”, không xử lý dấu xuống dòng/space và không tự thực hiện Unicode NFC. Chỉ dùng khi yêu cầu thật sự cần bỏ qua hoa/thường.

### Đơn vị mã UTF-16, code point và byte không phải một

Java lưu và thao tác `String` qua UTF-16. Với ký tự ngoài Basic Multilingual Plane, một **Unicode code point** có thể chiếm **hai đơn vị mã UTF-16**. Vì vậy:

- `String.length()` đếm đơn vị mã UTF-16, **không** phải số ký tự người đọc nhìn thấy.
- Vị trí từ `charAt(i)` cũng là vị trí đơn vị mã UTF-16.
- `String.equals` so sánh các đơn vị mã UTF-16 theo thứ tự.
- Hai file có byte khác nhau vì encoding hoặc BOM vẫn có thể được giải mã thành cùng nội dung `String` trong một số trường hợp. Nếu hợp đồng yêu cầu byte bằng nhau, hãy kiểm tra **byte** bằng API phù hợp thay vì chỉ dùng `String.equals`.

Đối với kiểm thử xuất dữ liệu, cần phân biệt “giá trị văn bản giống nhau” và “tệp xuất ra giống nhau từng byte”. Đây là hai hợp đồng khác nhau.

## 3. Text block có thể tạo newline và khoảng trắng ngoài dự kiến

**Text block** là tính năng Java đã ổn định từ Java 15. Nó thuận tiện cho tài liệu nhiều dòng, nhưng giá trị cuối cùng phụ thuộc vào vị trí dấu đóng `"""`, thụt lề và ký tự kết thúc dòng.

```java
String actual = """
        Name: Ana
        Role: Dev
        """;
```

Khi dấu đóng ở một dòng riêng, `actual` có giá trị tương đương:

```java
String same = "Name: Ana\nRole: Dev\n";
```

Tuy nhiên chuỗi sau **khác** `actual` vì thiếu newline cuối:

```java
String expected = "Name: Ana\nRole: Dev";
```

Text block còn có các quy tắc đang được sử dụng hiện nay:

1. **Chuẩn hóa line terminator của mã nguồn:** trong text block, `CR`, `CRLF` và `LF` của mã nguồn được chuẩn hóa thành `LF` (`\n`) khi biên dịch.
2. **Loại incidental indentation:** trình biên dịch bỏ phần lề mang tính trình bày mã nguồn, nhưng giữ thụt lề có ý nghĩa tương đối giữa các dòng.
3. **Xử lý trailing spaces:** các khoảng trắng cuối dòng dạng incidental thường bị loại bỏ; nếu cần giữ phải dùng escape phù hợp, ví dụ `\s`.
4. **Dòng đóng riêng thường để lại newline cuối:** nếu không muốn, có thể đặt dấu đóng sát dòng nội dung cuối hoặc sử dụng escape nối dòng `\<line-terminator>` theo tài liệu Java.

Chính vì vậy, khi so sánh kết quả text block với một chuỗi mong đợi, phải xác định **giá trị cuối cùng thực tế** rồi chọn so sánh chính xác hoặc chính sách chuẩn hóa rõ ràng. **Đừng** tự động gọi `strip()` hoặc `stripIndent()` để làm test qua nếu khoảng trắng cần được giữ.

## 4. Chương trình Java 17+ kiểm tra sự khác biệt vô hình

Tạo tệp **`ExactTextDemo.java`** (giữ nguyên phần thụt lề của text block):

```java
import java.util.Objects;

public class ExactTextDemo {
    private static String visible(String value) {
        return value.replace(" ", "·")
                .replace("\t", "<TAB>")
                .replace("\r", "<CR>")
                .replace("\n", "<LF>");
    }

    private static int firstDifference(String a, String b) {
        int commonLength = Math.min(a.length(), b.length());
        for (int i = 0; i < commonLength; i++) {
            if (a.charAt(i) != b.charAt(i)) {
                return i;
            }
        }
        return a.length() == b.length() ? -1 : commonLength;
    }

    public static void main(String[] args) {
        String expected = "Name: Ana\nRole: Dev";
        String actual = """
                Name: Ana
                Role: Dev
                """;

        System.out.println("equal=" + expected.equals(actual));
        System.out.println("expected=[" + visible(expected) + "]");
        System.out.println("actual=[" + visible(actual) + "]");
        System.out.println("firstDiffUtf16="
                + firstDifference(expected, actual));
        System.out.println("nullSafe=" + Objects.equals(null, null));
        System.out.println("withFinalLF="
                + (expected + "\n").equals(actual));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 ExactTextDemo.java
java ExactTextDemo
```

**Stdout chính xác:**

```text
equal=false
expected=[Name:·Ana<LF>Role:·Dev]
actual=[Name:·Ana<LF>Role:·Dev<LF>]
firstDiffUtf16=19
nullSafe=true
withFinalLF=true
```

Ở đây `·` biểu thị **một space**, còn `<LF>` biểu thị **một ký tự line feed**. `visible` chỉ hỗ trợ quan sát, không thay đổi bản thân `expected` hay `actual`.

`firstDifference` trả **chỉ số UTF-16 đầu tiên khác nhau**, bắt đầu từ 0. Nếu một chuỗi là tiền tố của chuỗi kia, nó trả độ dài của chuỗi ngắn hơn; nếu bằng nhau trả `-1`. Ví dụ này `expected` có 19 đơn vị mã và `actual` có thêm một `\n` ở vị trí 19.

**Mẹo khi debug:** in độ dài cùng một bản biểu diễn có dấu như trên thường hữu ích hơn in hai chuỗi thông thường rồi nhìn bằng mắt. Với lỗi Unicode khó xác định, in mã điểm Unicode/code unit tại vị trí khác biệt; lưu ý chỉ số UTF-16 không nhất thiết là vị trí ký tự trực quan.

## 5. Chuẩn hóa có chủ đích: mỗi thao tác phải có lý do

**Chuẩn hóa** là một phép biến đổi dữ liệu trước khi so sánh. Nó chỉ đúng khi tiêu chuẩn nghiệp vụ hoặc định dạng đầu ra **cho phép** các giá trị trước và sau biến đổi được coi là tương đương.

### 5.1. Thống nhất line ending

Với tài liệu cho phép CRLF, CR và LF là cùng một ranh giới dòng, có thể quy về LF:

```java
static String normalizeLineEndings(String text) {
    return text.replace("\r\n", "\n").replace("\r", "\n");
}
```

Đây là **đoạn phương thức** phải đặt bên trong một lớp Java (không phải chương trình độc lập). Thứ tự hai phép thay thế có ý nghĩa: đổi `CRLF` **trước**, sau đó đổi `CR` lẻ, để không tạo hai `LF` từ một `CRLF`.

Điều mà hàm này **không** làm:

- Không xóa khoảng trắng đầu hay cuối mỗi dòng.
- Không bỏ newline cuối văn bản.
- Không tự gộp nhiều dòng trống.
- Không xử lý các dấu phân cách dòng Unicode như `U+2028` nếu hợp đồng chưa yêu cầu.

Vì vậy `"a\n"` vẫn **khác** `"a"` sau chuẩn hóa line ending. Nếu muốn coi hai giá trị ấy tương đương, phải **ghi rõ** chính sách “bỏ đúng một newline cuối” hoặc chính sách khác, rồi thực hiện riêng.

### 5.2. Chuẩn hóa Unicode theo NFC

Một chữ có dấu như `é` có thể xuất hiện theo nhiều cách biểu diễn Unicode: **một code point dựng sẵn** (`U+00E9`) hoặc **chữ `e` cộng dấu kết hợp** (`U+0065 U+0301`). Chúng trông tương tự nhưng `String.equals` có thể trả `false`.

Java cung cấp `java.text.Normalizer` để đưa văn bản về dạng chuẩn Unicode:

```java
import java.text.Normalizer;

static String normalizeUnicodeNfc(String text) {
    return Normalizer.normalize(text, Normalizer.Form.NFC);
}
```

Đoạn trên là **phương thức minh họa** đặt trong class có import. **NFC (Canonical Composition)** thường phù hợp khi chính sách so sánh xem các cách mã hóa canonically equivalent là một giá trị. `NFD` là dạng canonical decomposition và có thể dùng nếu hợp đồng chọn nó.

**Không tự động đổi sang NFKC/NFKD** cho mọi bài toán: đó là *compatibility normalization*, có thể làm thay đổi những dạng ký tự mà miền dữ liệu cần phân biệt (chẳng hạn ký hiệu hoặc dạng trình bày). NFC cũng không tự bỏ dấu tiếng Việt, không tự chuyển hoa sang thường, không thay dấu cách và không chuẩn hóa line ending.

### 5.3. Khoảng trắng đầu/cuối và khoảng trắng nội bộ

Các thao tác khác nhau có ngữ nghĩa khác nhau:

| API/cách xử lý | Biến đổi | Khi phù hợp |
| --- | --- | --- |
| `s.strip()` | Loại các ký tự whitespace theo `Character.isWhitespace` ở **hai đầu chuỗi** | Nhãn/giá trị nhập liệu cho phép bỏ whitespace ở ranh giới |
| `s.stripLeading()` | Bỏ whitespace đầu chuỗi | Dữ liệu được phép bỏ khoảng trắng đầu nhưng vẫn cần giữ cuối |
| `s.stripTrailing()` | Bỏ whitespace cuối chuỗi, **kể cả newline cuối nếu thuộc loại whitespace** | Chỉ khi hợp đồng không cần phần cuối ấy |
| `s.stripIndent()` | Loại incidental indentation của các dòng và xử lý trailing whitespace theo quy tắc API | Văn bản nhiều dòng được mô tả là cần chuẩn hóa thụt lề, không phải thay thế chung cho `strip` |
| `s.replace("  ", " ")` | Thay **đúng hai spaces** bằng một space trong mỗi lần thay thế | Một biến đổi cụ thể nếu được yêu cầu; không đồng nghĩa gộp toàn bộ whitespace |
| `s.replaceAll("\\s+", " ")` | Gộp các nhóm ký tự khớp regex `\\s` thành một space, **có thể làm mất xuống dòng** | Chỉ khi thật sự muốn bỏ phân biệt các ranh giới khoảng trắng đó và hiểu regex mode |

Không nên tự động “gọt sạch” mọi chuỗi bằng `strip` và `replaceAll`. Với thơ, mã nguồn, YAML, văn bản căn cột, chữ ký số hoặc nội dung nơi xuống dòng mang ý nghĩa, làm vậy có thể phá dữ liệu.

Java `strip` dùng khái niệm whitespace theo `Character.isWhitespace`, không đồng nhất với mọi loại space trong Unicode. Đặc biệt, một số **non-breaking space** không bị xử lý như dấu cách thông thường. Nếu ứng dụng cần quy tắc riêng với `U+00A0`, hãy đặc tả rõ và xử lý riêng.

### 5.4. Hoa/thường và locale

Nếu bài toán chỉ phân biệt token ASCII theo quy tắc không phân biệt chữ hoa:

```java
String canonical = input.strip()
        .toLowerCase(java.util.Locale.ROOT);
```

Đây là **snippet** với biến `input` đã khai báo. Cần chọn quy tắc này chỉ khi miền dữ liệu cho phép: ví dụ một nhóm tên lệnh do ứng dụng kiểm soát. Đối với tên riêng, văn bản tự nhiên hoặc sắp xếp theo ngôn ngữ, **locale, case mapping và collation** có quy tắc phức tạp hơn; `toLowerCase(Locale.ROOT)` không phải phép so sánh ngôn ngữ tổng quát.

Một chuỗi “đọc được giống nhau” không có nghĩa mọi khác biệt như hoa/thường, dấu hoặc khoảng trắng đều có thể bỏ qua.

## 6. Chương trình chuẩn hóa có chính sách rõ ràng

Trong ví dụ này, **hợp đồng của tài liệu** cho phép khác biệt line ending (`CRLF`/`CR`/`LF`) và các dạng **Unicode NFC-equivalent**, nhưng **không cho phép** khác biệt về số spaces hoặc sự tồn tại của newline cuối.

Tạo tệp **`NormalizeTextDemo.java`**:

```java
import java.text.Normalizer;

public class NormalizeTextDemo {
    private static String normalizeDocument(String text) {
        String lf = text.replace("\r\n", "\n").replace("\r", "\n");
        return Normalizer.normalize(lf, Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        String expected = "Café\nOK\n";
        String received = "Cafe" + (char) 0x0301 + "\r\nOK\r\n";

        System.out.println("exact=" + expected.equals(received));
        System.out.println("normalized="
                + normalizeDocument(expected)
                        .equals(normalizeDocument(received)));

        System.out.println("spacesMatter="
                + normalizeDocument("A B")
                        .equals(normalizeDocument("A  B")));

        System.out.println("lastNewlineMatters="
                + normalizeDocument("A\n")
                        .equals(normalizeDocument("A")));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 NormalizeTextDemo.java
java NormalizeTextDemo
```

**Stdout chính xác:**

```text
exact=false
normalized=true
spacesMatter=false
lastNewlineMatters=false
```

Giải thích:

- `expected` chứa chữ `é` dựng sẵn và `LF`; `received` chứa `e` + dấu kết hợp `U+0301` và `CRLF`.
- Phép `equals` ban đầu trả `false`, vì chuỗi đơn vị mã khác nhau.
- Sau khi áp dụng **cùng một pipeline** `normalizeDocument`, hai chuỗi bằng nhau: `true`.
- Hai spaces so với một space vẫn khác; newline cuối có hay không cũng vẫn khác. Đây là **chủ đích** của chính sách, không phải lỗi của hàm.

Nếu yêu cầu mới cho phép bỏ qua đúng **một newline cuối**, hãy bổ sung một bước minh bạch cho **cả hai vế**, ví dụ:

```java
static String removeOneFinalLf(String text) {
    return text.endsWith("\n")
            ? text.substring(0, text.length() - 1)
            : text;
}
```

Đoạn phương thức này giả định **line endings đã được chuẩn hóa về LF trước đó**. Nó chỉ xóa **một** `LF` cuối, không xóa mọi dòng trống hay spaces. Chỉ dùng khi chính sách thực sự nói rõ “một newline cuối là tùy chọn”.

## 7. Chọn phép so sánh cho từng tình huống thực tế

| Tình huống | Đề xuất | Lý do |
| --- | --- | --- |
| Kiểm thử chuỗi được API cam kết chính xác | `expected.equals(actual)` | Thấy được lỗi spacing, delimiter và newline |
| Kiểm thử text block dùng làm HTML/SQL/JSON fixture | So sánh exact trước; nếu cần, xác định chính sách riêng cho fixture | Text block đã có bước bỏ thụt lề/chuẩn hóa xuống dòng khi biên dịch; đừng xóa thêm tùy tiện |
| Đọc tài liệu từ nhiều hệ điều hành, hợp đồng coi CRLF và LF tương đương | Chuẩn hóa CRLF/CR → LF trên **hai phía**, rồi `equals` | Bỏ qua sự khác biệt chỉ về cách mã hóa xuống dòng |
| Chuỗi tiếng Việt nhập từ nhiều nguồn, hợp đồng coi canonical Unicode tương đương | `Normalizer.normalize(s, NFC)` cho cả hai phía | Xử lý cách kết hợp dấu khác nhau mà giữ ý nghĩa canonical |
| So khớp mã định danh yêu cầu giữ nguyên mọi ký tự | Exact; không strip/case-fold nếu chưa được quy định | Tránh vô tình gộp hai định danh khác nhau |
| So sánh nhãn giao diện cho phép bỏ spaces ở hai đầu | `strip()` cho cả hai phía, sau khi đã xác định chính sách | Loại đúng phần whitespace ở ranh giới được phép bỏ |
| So sánh dữ liệu JSON theo cấu trúc | Parse JSON và so sánh giá trị theo đặc tả cần thiết, hoặc so sánh exact nếu giao thức yêu cầu cùng serialization | Thứ tự khóa/spacing có thể khác mà ý nghĩa cấu trúc giống; ngược lại thứ tự mảng và kiểu dữ liệu có thể quan trọng |
| Kiểm tra chữ ký số, payload theo bytes, tệp cần giống từng byte | So sánh byte/kiểm tra theo giao thức; không tùy tiện chuẩn hóa text | Một ký tự newline hoặc thay đổi encoding có thể làm thay đổi bytes và chữ ký |

### Text block + `String.formatted`: phân biệt hai cơ chế

Ví dụ:

```java
String actual = """
        Name: %s
        Level: %d
        """.formatted("Ana", 3);
```

Đầu tiên, trình biên dịch Java xử lý text block thành một `String` có lề và newline theo quy tắc cú pháp. Sau đó, `formatted` thay `%s`, `%d` bằng đối số và trả về chuỗi mới.

Giá trị kỳ vọng chính xác:

```java
String expected = "Name: Ana\nLevel: 3\n";
```

Khi tạo expected cho kiểm thử, **đừng quên** newline cuối. Nếu định dạng số phụ thuộc locale (`%,.2f`, v.v.) và cần kết quả lặp lại trên mọi máy, hãy chỉ định `Locale` qua `String.format(Locale, template, ...) `; `String.formatted` không có overload nhận locale riêng.

## 8. Quy trình chẩn đoán khi hai chuỗi khác nhau

Thay vì nhìn hai chuỗi rồi đoán, làm theo thứ tự sau:

1. **Xác nhận điều kiện so sánh:** kết quả có phải giống từng ký tự không? Các khác biệt nào được hợp đồng cho phép bỏ qua?
2. **So sánh exact trước:** gọi `equals()` hoặc `Objects.equals()` nếu có khả năng `null`.
3. **Đo và hiển thị:** kiểm tra `length()`, escape các ký tự khó nhìn (`\\r`, `\\n`, tab, spaces) và tìm vị trí khác đầu tiên.
4. **Xác định nguyên nhân:** ví dụ newline cuối từ text block, CRLF của dữ liệu ngoài, indentation, chuỗi Unicode dạng decomposed, lỗi format specifier hoặc encoding.
5. **Sửa nguồn tạo dữ liệu** nếu hợp đồng yêu cầu exact. Chỉ thêm chuẩn hóa nếu hợp đồng cho phép khác biệt đó.
6. **Viết test đối chứng:** một cặp cần được coi là bằng nhau sau chuẩn hóa **và** một cặp vẫn phải khác. Ví dụ test ở chương 6 kiểm tra spaces và newline cuối vẫn có ý nghĩa.

Có thể viết một assertion không dùng thư viện ngoài:

```java
static void requireExact(String expected, String actual) {
    if (!java.util.Objects.equals(expected, actual)) {
        throw new AssertionError("Text differs");
    }
}
```

Đây là **phương thức minh họa** đặt trong class. Nó phát tín hiệu test fail nếu chuỗi khác, nhưng không in toàn bộ nội dung có thể nhạy cảm. Với tài liệu lớn, log đầu vào thật có thể chứa thông tin riêng tư; khi debug nên chỉ lưu vị trí và loại khác biệt, hoặc một bản được làm sạch theo yêu cầu ứng dụng.

**Không dùng các thao tác sau như mẹo chữa test thất bại không có đặc tả:** `strip()` toàn bộ tài liệu, `replaceAll("\\s+", " ")` để xóa newline, `equalsIgnoreCase()` cho mọi văn bản, hoặc ép mọi dữ liệu qua NFKC. Những thao tác ấy có thể che lỗi thật và làm sai nội dung.

## 9. Lỗi phổ biến và cách sửa

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Hai dòng in ra nhìn giống nhau nhưng `equals` là `false` | Khác space, tab, CR/LF, newline cuối hoặc Unicode | Dùng bản hiển thị ký tự vô hình và vị trí khác đầu tiên |
| `"A\n"` khác `"A"` | `equals` xét cả newline cuối | Quyết định newline cuối là bắt buộc hay tùy chọn, rồi sửa expected/actual hoặc quy định chuẩn hóa |
| Nội dung text block bị lệch lề | Dấu đóng `"""` và incidental indentation ảnh hưởng chuỗi | Kiểm tra vị trí dấu đóng và spaces ở từng dòng |
| `String.lines()` cho các dòng trông giống nhau nhưng chuỗi gốc khác | `lines()` không giữ nguyên terminator từng dòng trong phần tử trả về | Muốn so sánh exact, so sánh chuỗi gốc; đừng dựa chỉ vào danh sách dòng đã tách |
| Văn bản có dấu tiếng Việt trông giống nhưng khác `equals` | Unicode composed và decomposed | Chuẩn hóa hai phía về NFC **nếu** hợp đồng coi chúng tương đương |
| Chuẩn hóa rồi mọi test đều “PASS” nhưng tài liệu sai | Hàm chuẩn hóa xóa nhiều hơn quy định | Thu hẹp chính sách, thêm test âm tính với khoảng trắng/newline phải giữ |
| Dữ liệu sai sau `stripIndent()` lần nữa | Chuỗi đã được text block compiler xử lý hoặc indentation có ý nghĩa | Không chuẩn hóa thêm nếu không được yêu cầu |
| `==` khi so sánh hai `String` cho kết quả khó hiểu | Kiểm tra identity của đối tượng | Dùng `equals` hoặc `Objects.equals` |
| Kết quả text giống nhưng file checksum khác | Encoding, BOM hoặc line endings làm byte khác | Phân biệt so sánh text và so sánh bytes; chọn đúng hợp đồng |

## 10. Bài tập tự luyện và đáp án

**Bài 1.** Hai chuỗi `"Hello\n"` và `"Hello"` có bằng nhau theo `equals` không?

**Đáp án:** Không, chuỗi thứ nhất có thêm một ký tự LF.

**Bài 2.** Một text block:

```java
String value = """
        first
        second
        """;
```

có bằng `"first\nsecond"` không?

**Đáp án:** Không. Text block như trên có thêm `\n` ở cuối, tương đương `"first\nsecond\n"`.

**Bài 3.** Vì sao hai chuỗi đại diện cùng chữ “é” vẫn có thể khác nhau theo `equals`?

**Đáp án:** Một chuỗi có thể chứa `U+00E9`, chuỗi kia chứa `U+0065` rồi `U+0301`. Muốn coi hai biểu diễn canonical ấy bằng nhau, có thể chuẩn hóa cả hai về NFC trước khi so sánh.

**Bài 4.** Ứng dụng chấp nhận CRLF và LF là một ranh giới dòng, nhưng không chấp nhận mất newline cuối. Nên viết chính sách thế nào?

**Đáp án:** Trên **cả hai phía**, lần lượt thay `"\r\n"` thành `"\n"`, rồi `"\r"` thành `"\n"`; giữ nguyên newline cuối; sau đó `equals`. Không gọi `stripTrailing()`.

**Bài 5.** `"A  B"` (hai spaces) có nên được coi bằng `"A B"` (một space) không?

**Đáp án:** Chỉ khi đặc tả miền dữ liệu nói rằng khoảng trắng liên tiếp không mang ý nghĩa. Nếu là định dạng căn cột, đoạn code hoặc nội dung văn bản nguyên bản, phải giữ khác biệt.

**Bài 6.** Vì sao không nên dùng `strip()` để “sửa” test so sánh văn bản đã ký?

**Đáp án:** Vì `strip()` xóa các whitespace ở ranh giới, có thể thay đổi giá trị văn bản/bytes được ký. So sánh và xác minh chữ ký phải tuân thủ quy tắc canonicalization của giao thức, không tự áp dụng biến đổi ngoài đặc tả.

### Checklist

- [ ] Tôi dùng `equals` để so sánh **nội dung chính xác**, tránh `==` để so sánh hai giá trị `String`.
- [ ] Tôi đã kiểm tra khoảng trắng, `CR`, `LF`, `CRLF` và newline cuối trước khi kết luận hai chuỗi bằng nhau.
- [ ] Tôi hiểu text block trong Java chuẩn hóa line ending và incidental indentation **lúc biên dịch**.
- [ ] Tôi chỉ chuẩn hóa những khác biệt **được đặc tả cho phép**.
- [ ] Tôi biết cách dùng NFC cho canonical Unicode equivalence và biết giới hạn của nó.
- [ ] Tôi áp dụng **cùng pipeline** lên expected và actual trước khi so sánh sau chuẩn hóa.
- [ ] Tôi kiểm thử cả trường hợp phải bằng nhau **và trường hợp phải khác nhau** sau chuẩn hóa.
- [ ] Tôi phân biệt việc so sánh `String` và so sánh **bytes** của tài liệu/tệp.

## Tài liệu chính thức còn áp dụng

1. [Java SE 25 — `String` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): `equals`, `length`, `strip`, `stripIndent`, `lines`, `formatted`.
2. [Java SE 25 — `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Normalizer.html): NFC, NFD, NFKC và NFKD.
3. [Oracle — Text Blocks (Java 25)](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html): newline cuối, thụt lề, xử lý whitespace và line terminator.
4. [Java SE 25 — `Objects.equals`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)): so sánh nội dung có hỗ trợ giá trị `null`.
5. [Unicode Standard Annex #15 — Unicode Normalization Forms](https://unicode.org/reports/tr15/): giải thích canonical equivalence và các dạng chuẩn Unicode.

**Kết luận thực hành:** So sánh **chính xác** là điểm khởi đầu khi kiểm thử kết quả văn bản. Chỉ chuyển sang **so sánh sau chuẩn hóa** khi bạn có quy tắc rõ ràng về những khác biệt được phép bỏ qua; phải dùng chung quy tắc ấy cho hai phía và giữ nguyên các khác biệt còn có ý nghĩa.