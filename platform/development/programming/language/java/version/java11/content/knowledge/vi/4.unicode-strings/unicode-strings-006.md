# Quy tắc LF, CR, CRLF và dòng kết thúc trong Java 11

**Chủ đề cha:** Chuỗi Unicode  
**Mục tiêu:** Hiểu chính xác ba kiểu kết thúc dòng thông dụng, cách Java 11 tách dòng và biểu diễn dòng cuối, phân biệt dấu kết thúc dòng với ký tự/encoding, đồng thời xử lý dữ liệu văn bản qua các hệ điều hành mà không vô tình mất thông tin.

LF, CR và CRLF vẫn là kiến thức thiết yếu của Java hiện đại. Lỗi do trộn kiểu xuống dòng thường xuất hiện trong kiểm thử, xử lý tệp, giao tiếp với dịch vụ, Git, import dữ liệu và so sánh chuỗi. Bài này sử dụng API chuẩn hoạt động được trên Java 11 và vẫn phù hợp trên các JDK mới, không dựa vào cách xử lý văn bản đã lỗi thời.

## 1. LF, CR và CRLF là gì?

| Ký hiệu | Mã Unicode | Java string literal | Ý nghĩa trong văn bản | Số ký tự |
|---|---|---|---|---:|
| LF (Line Feed) | U+000A | `"\n"` | Dấu xuống dòng dạng LF | 1 |
| CR (Carriage Return) | U+000D | `"\r"` | Dấu về đầu dòng, cũng được xem là một dấu kết thúc dòng khi xử lý văn bản | 1 |
| CRLF | U+000D rồi U+000A | `"\r\n"` | Một chuỗi kết thúc dòng gồm CR và LF liên tiếp | 2 |
| EOF (End of File) | Không phải ký tự Unicode | Không có escape riêng | Trạng thái hết dữ liệu, **không phải** dấu kết thúc dòng | 0 |

**Điểm cốt lõi:** `\r\n` gồm **hai ký tự** nhưng khi Java tách dòng văn bản theo quy tắc LF/CR/CRLF, cặp liền nhau được tính là **một dấu kết thúc dòng**. Không tách CRLF thành hai dấu ngắt độc lập.

Trong Java source code, `"\n"` biểu diễn **một ký tự LF thực tế** trong chuỗi lúc chạy; dấu `\` và chữ `n` chỉ là cú pháp escape để viết mã. Tương tự, `"\r"` là CR, `"\r\n"` là CR theo sau LF. Trái lại, `"\\n"` chứa hai ký tự hiển thị được: dấu gạch chéo ngược và chữ `n`. Phân biệt điều này rất quan trọng khi đọc log hoặc debug chuỗi.

Ví dụ về mặt khái niệm, ký hiệu trong khối sau chỉ để nhìn thấy dấu xuống dòng, **không phải** tệp chứa ký tự `\` và `n`:

```text
A\nB        : LF giữa A và B
A\rB        : CR giữa A và B
A\r\nB      : CRLF giữa A và B
A           : không có dấu kết thúc sau A
A\n         : A có dấu kết thúc dòng ở cuối
```

**Không đồng nhất Unicode với encoding:** LF/CR được xác định bằng code point U+000A/U+000D. Khi ghi dưới UTF-8, chúng có byte `0A` / `0D`, còn CRLF có `0D 0A`. Với encoding khác như UTF-16, cách mã hóa ra byte khác đi. Sự tồn tại của LF/CRLF trong chuỗi Java `String` là vấn đề **ký tự**; còn byte trên đĩa/phía mạng phụ thuộc charset.

## 2. Dấu kết thúc dòng khác gì “dòng cuối”?

Có ba khái niệm thường bị trộn lẫn:

- **Nội dung dòng:** phần văn bản nằm giữa hai dấu kết thúc, không bao gồm `\r`/`\n` khi đã tách bằng `String.lines()`.
- **Dấu kết thúc dòng:** một trong LF, CR hoặc CRLF đứng sau nội dung dòng, hoặc đứng sau một dòng rỗng.
- **Hết chuỗi/hết tệp (EOF):** chạm vị trí cuối dữ liệu. EOF có thể đến **ngay sau một dấu kết thúc**, hoặc đến sau ký tự nội dung **không có dấu kết thúc**.

Vì thế:

- `"A"`: có một dòng `A` **không có** dấu kết thúc.
- `"A\n"`: có một dòng `A` **có** dấu kết thúc LF.
- `"A\r\n"`: có một dòng `A` **có** dấu kết thúc CRLF.
- `"A\n\n"`: có dòng `A`, rồi một **dòng rỗng có LF kết thúc**; không tự sinh dòng thứ ba sau LF cuối cùng.
- `""`: văn bản rỗng, không có dòng nào khi gọi `String.lines()`.
- `"\n"`: có **một dòng rỗng** được kết thúc bởi LF.

Trong một số chương trình biên tập văn bản, người dùng có thể nhìn thấy con trỏ ở “dòng trống kế tiếp” sau LF cuối. Đó là lựa chọn hiển thị/biên tập; **không phải** lý do để giả định `String.lines()` sẽ trả thêm một phần tử rỗng cuối.

### Bảng chân trị của `String.lines()` trong Java 11

| Chuỗi gốc (viết bằng Java literal) | Các phần tử của `lines()` | Số dòng | Có ký tự kết thúc ở cuối? |
|---|---|---:|---|
| `""` | Không phần tử | 0 | Không |
| `"A"` | `["A"]` | 1 | Không |
| `"A\n"` | `["A"]` | 1 | Có, LF |
| `"A\r"` | `["A"]` | 1 | Có, CR |
| `"A\r\n"` | `["A"]` | 1 | Có, CRLF |
| `"A\nB"` | `["A", "B"]` | 2 | Không |
| `"A\n\nB"` | `["A", "", "B"]` | 3 | Không |
| `"A\n\n"` | `["A", ""]` | 2 | Có, LF |
| `"\n"` | `[""]` | 1 | Có, LF |
| `"\r\n"` | `[""]` | 1 | Có, CRLF |

**Hệ quả:** `lines().count()` là số phần tử mà API nhận diện theo quy tắc của nó, **không phải** phép đếm nguyên xi số ký tự `\n`, càng không đủ để trả lời văn bản có kết thúc bằng newline hay không. Hai chuỗi `"A"` và `"A\n"` cùng cho một phần tử `"A"`, nhưng khác nhau khi so sánh byte, diff hoặc xử lý định dạng đòi hỏi dấu kết thúc cuối.

## 3. Quy tắc chính xác của `String.lines()` (Java 11)

`String.lines()`, được đưa vào Java 11, trả về `Stream<String>`. Nó coi ba trường hợp sau là dấu kết thúc dòng:

1. Một LF đơn lẻ: `\n`.
2. Một CR đơn lẻ: `\r`.
3. Một cặp CR ngay trước LF: `\r\n`.

Khi tách dòng, dấu kết thúc bị **loại khỏi** mỗi chuỗi con. Một LF/CR/CRLF ở cuối không tạo phần tử rỗng giả sau cùng. Nhưng **dòng rỗng thực sự nằm giữa hai dấu kết thúc** vẫn là một phần tử rỗng. Chuỗi đầu vào rỗng tạo stream rỗng.

API tách ở mức `String`, không tự mở tệp, không chuyển đổi charset và không bảo toàn thông tin “dòng này kết thúc bằng LF hay CRLF”. Nó phù hợp khi nhiệm vụ cần **nội dung của từng dòng**, ví dụ phân tích văn bản nhiều dòng hoặc bỏ các dòng trắng theo nghiệp vụ.

### Ví dụ 1 — kiểm tra các ca biên bằng chương trình chạy được

Lưu toàn bộ chương trình dưới tên **`LineBreakDemo.java`**:

```java
import java.util.stream.Collectors;

public class LineBreakDemo {
    private static void inspect(String label, String text) {
        var values = text.lines()
                .map(line -> "<" + line + ">")
                .collect(Collectors.toList());

        boolean terminated = text.endsWith("\n") || text.endsWith("\r");

        System.out.println(label + ": count=" + values.size()
                + ", values=" + values + ", terminated=" + terminated);
    }

    public static void main(String[] args) {
        inspect("empty", "");
        inspect("noTerm", "A");
        inspect("LF", "A\n");
        inspect("CR", "A\r");
        inspect("CRLF", "A\r\n");
        inspect("middle", "A\n\nB");
        inspect("doubleEnd", "A\n\n");
        inspect("onlyLF", "\n");
    }
}
```

Biên dịch và chạy trên JDK 11 hoặc JDK mới hơn có hỗ trợ target 11:

```bash
javac --release 11 -encoding UTF-8 LineBreakDemo.java
java LineBreakDemo
```

Kết quả đã kiểm tra:

```text
empty: count=0, values=[], terminated=false
noTerm: count=1, values=[<A>], terminated=false
LF: count=1, values=[<A>], terminated=true
CR: count=1, values=[<A>], terminated=true
CRLF: count=1, values=[<A>], terminated=true
middle: count=3, values=[<A>, <>, <B>], terminated=false
doubleEnd: count=2, values=[<A>, <>], terminated=true
onlyLF: count=1, values=[<>], terminated=true
```

Dấu `<...>` trong danh sách là ký hiệu **do chương trình thêm vào khi in kết quả**, để dễ nhận ra phần tử rỗng `<>`; chúng không thuộc nội dung dòng. Cột `terminated` kiểm tra riêng xem cuối chuỗi có ký tự CR hoặc LF. Nó vẫn `true` với CRLF vì chuỗi kết thúc bằng LF.

### Khi cần biết cụ thể kiểu kết thúc cuối

Không thể suy từ `String.lines()` đã tách, vì dấu kết thúc bị bỏ. Hãy kiểm tra trên **chuỗi gốc** trước khi chuẩn hóa:

```java
static String finalTerminator(String raw) {
    if (raw.endsWith("\r\n")) return "CRLF";
    if (raw.endsWith("\n")) return "LF";
    if (raw.endsWith("\r")) return "CR";
    return "NONE";
}
```

Đây là **đoạn phương thức** cần đặt trong một class; nó không phải chương trình chạy độc lập. **Kiểm tra CRLF trước LF** vì chuỗi kết thúc bằng CRLF cũng kết thúc bằng ký tự LF. Với `""` hoặc `"A"`, kết quả là `NONE`. Nếu yêu cầu là bảo toàn **từng dấu kết thúc ở mọi vị trí**, phải giữ nguyên chuỗi đầu vào hoặc viết bộ quét ghi nhận nội dung và terminator của từng dòng; kiểm tra ký tự cuối chỉ cho biết terminator cuối.

## 4. Vì sao Unicode line separator không đồng nghĩa với LF/CR/CRLF?

Unicode có các code point khác liên quan ngắt dòng, ví dụ:

- U+0085 — NEXT LINE (NEL).
- U+2028 — LINE SEPARATOR (LS).
- U+2029 — PARAGRAPH SEPARATOR (PS).

**Trong Java 11, `String.lines()` chỉ nhận diện LF, CR và CRLF theo hợp đồng API**, không tách theo U+0085, U+2028 hay U+2029. Không nên suy luận rằng “chuỗi Unicode” đồng nghĩa với “mọi code point Unicode mang ý nghĩa xuống dòng đều được `lines()` xử lý”.

Nếu bài toán thực sự cần chia theo một tập ký tự ngắt dòng Unicode rộng hơn, regex của Java có `\R`, nghĩa là *Unicode linebreak sequence*, bao gồm CRLF và các dấu ngắt khác theo tài liệu `java.util.regex.Pattern`. Cú pháp string literal để dùng regex đó là `"\\R"`: hai dấu gạch chéo trong mã Java tạo một dấu gạch chéo đưa tới regex engine.

### Ví dụ 2 — khác biệt giữa `lines()` và `split("\\R", -1)`

Lưu chương trình sau thành **`UnicodeLineDemo.java`**:

```java
public class UnicodeLineDemo {
    public static void main(String[] args) {
        String unicodeLineSeparator = "A" + (char) 0x2028 + "B";

        System.out.println("String.lines: "
                + unicodeLineSeparator.lines().count());

        System.out.println("Regex split: "
                + unicodeLineSeparator.split("\\R", -1).length);

        System.out.println("Empty split: "
                + "".split("\\R", -1).length);

        System.out.println("Final split: "
                + "A\r\n".split("\\R", -1).length);
    }
}
```

```bash
javac --release 11 -encoding UTF-8 UnicodeLineDemo.java
java UnicodeLineDemo
```

```text
String.lines: 1
Regex split: 2
Empty split: 1
Final split: 2
```

Giải thích từng dòng kết quả:

- U+2028 nằm giữa `A` và `B`. `String.lines()` trả **một** dòng vì nó không coi U+2028 là terminator; regex `\R` chia thành **hai** phần.
- `split("\\R", -1)` trên `""` trả mảng gồm **một chuỗi rỗng**, khác với stream rỗng từ `"".lines()`.
- Tham số limit `-1` bảo toàn **phần tử rỗng ở cuối**: `"A\r\n"` tách thành `["A", ""]`. Đây là kết quả của **tách chuỗi theo delimiter**; không được tự đồng nhất phần tử rỗng cuối với một dòng nội dung bổ sung theo quy tắc `String.lines()`.

**Chọn công cụ theo yêu cầu thực sự:** `lines()` cho nội dung dòng kiểu LF/CR/CRLF; `split("\\R", -1)` cho phân tách trên tập Unicode linebreak rộng hơn và giữ segment cuối; bộ quét riêng cho trường hợp cần bảo toàn chính xác từng loại separator và vị trí của chúng.

## 5. Đọc văn bản từ tệp: charset và line ending là hai việc độc lập

Trong Java 11, các API thường dùng:

| API | Dữ liệu thu được | Thông tin terminator giữ được? | Khi dùng |
|---|---|---|---|
| `Files.readString(path, UTF_8)` | Toàn bộ `String`, còn nguyên `\r`/`\n` trong nội dung | Có, nếu giữ chuỗi gốc | Tệp đủ nhỏ để nạp RAM |
| `Files.lines(path, UTF_8)` | `Stream<String>` theo dòng | Không; separator đã bị bỏ | Tệp lớn, pipeline xử lý tuần tự |
| `BufferedReader.readLine()` | Một dòng hoặc `null` khi EOF | Không | Cần đọc tuần tự và tự điều khiển vòng lặp |
| `String.lines()` | `Stream<String>` từ `String` có sẵn | Không; separator đã bị bỏ | Đầu vào đã là chuỗi |
| `Files.writeString(path, text, UTF_8)` | Ghi chuỗi ra tệp | Có; ghi theo các ký tự CR/LF hiện có trong chuỗi | Ghi văn bản có kiểm soát |

`Files.readString` và `Files.writeString` trong Java 11 mặc định UTF-8 khi dùng overload không truyền charset; ghi tường minh `StandardCharsets.UTF_8` thường giúp người khác đọc và duy trì mã rõ hơn. Việc đọc/ghi đúng charset **không tự đổi** CRLF thành LF hay ngược lại.

`Files.lines(...)` và `BufferedReader.readLine()` hiểu LF, CR và CRLF là dấu kết thúc dòng theo quy tắc của API và loại chúng khỏi dòng trả về. Stream từ `Files.lines` có tài nguyên I/O, phải đóng bằng `try-with-resources`. Không giữ stream mở sau khi kết thúc phương thức.

Đoạn mã dưới đây là **trích đoạn trong một phương thức** khi `path` đã tồn tại và đã import `Files`, `StandardCharsets`:

```java
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.count();
    System.out.println(count);
}
```

Nếu cần **biết chuỗi gốc có newline cuối hay không**, hãy đọc nguyên văn hoặc dùng bộ đọc cấp ký tự có lưu trạng thái dấu kết thúc. Không dùng riêng `BufferedReader.readLine()` hoặc `Files.lines()` rồi đoán lại kiểu separator, vì thông tin đó đã mất.

**Ví dụ thông dụng:** một tệp `A\r\nB\n` có hai dòng nội dung theo `lines()`, nhưng chứa một CRLF và một LF. Đọc qua API theo dòng rồi nối lại bằng `"\n"` sẽ không tái tạo byte/ký tự ban đầu, dù nội dung từng dòng vẫn giống.

## 6. Chủ động chọn line ending khi tạo đầu ra

Mỗi môi trường có quy ước hiển thị/ghi văn bản; ứng dụng nên chọn theo **hợp đồng đầu ra**, không giả định mọi nền tảng dùng một kiểu.

- `System.lineSeparator()` trả dấu phân cách dòng theo môi trường chạy JDK (thường LF trên Unix/Linux/macOS và CRLF trên Windows). Nó phù hợp với văn bản dành riêng cho hệ thống/công cụ địa phương.
- `System.out.println(...)` và `BufferedWriter.newLine()` sử dụng quy tắc xuống dòng của môi trường. Không thể dùng chúng như bằng chứng rằng dữ liệu nguồn chứa LF hay CRLF.
- `writer.write("\n")` hoặc `Files.writeString(path, "A\nB\n", UTF_8)` ghi **LF rõ ràng**, bất kể máy chạy.
- Khi giao thức hoặc định dạng dữ liệu quy định LF hay CRLF cụ thể, phải tạo đúng chuỗi đó bằng yêu cầu kỹ thuật; không thay bằng `System.lineSeparator()` tùy máy.
- Không tùy tiện đổi separator của tệp ngoại vi vốn phải giữ byte/định dạng gốc (chữ ký số, checksum, snapshot, nội dung diff, dữ liệu trao đổi có quy tắc nghiêm ngặt).

**Phân biệt ba nơi khác nhau:** line ending của file `.java` chứa source code, dấu `"\n"` nằm trong giá trị chuỗi lúc chạy, và line ending mà `println` ghi ra terminal **không bắt buộc giống nhau**. Trình biên dịch hiểu escape trong string literal; hệ điều hành/editor quyết định cách lưu tệp mã nguồn; terminal có thể hiển thị thêm quy tắc riêng.

Nếu một API cần “một dòng kết thúc bằng LF”, viết `"value\n"`. Nếu cần “một dòng không có ký tự kết thúc”, viết `"value"`. Đừng thêm hoặc bỏ ký tự cuối chỉ vì `lines().count()` cho cùng một giá trị.

## 7. Chuẩn hóa CRLF/CR thành LF mà vẫn giữ newline cuối

Có một số tình huống muốn chuẩn hóa dữ liệu **văn bản tự do** về LF để dễ so sánh, xử lý hoặc viết snapshot. Với quy tắc LF/CR/CRLF, phép chuẩn hóa có thể thực hiện:

```java
String normalized = original.replace("\r\n", "\n")
        .replace('\r', '\n');
```

Thứ tự rất quan trọng cho cách hiểu và chứng minh tính đúng: trước tiên thay **mỗi cặp CRLF** bằng một LF, sau đó thay **CR đứng riêng** bằng LF. Phép biến đổi không thêm hoặc xóa dấu kết thúc logic: `"A\r\n"` thành `"A\n"`; `"A\r"` thành `"A\n"`; `"A"` vẫn là `"A"`; `"A\r\n\r\n"` thành `"A\n\n"`. Các chuỗi LF có sẵn không đổi; chạy chuẩn hóa lần nữa cho cùng kết quả.

Phương pháp này chỉ chuẩn hóa **CR, LF, CRLF**. Nó không diễn giải U+0085/U+2028/U+2029 thành LF; không tự chuẩn hóa Unicode normalization form; không thao tác bytes nhị phân. Với tệp lớn, cân nhắc xử lý kiểu stream/buffer để không giữ toàn bộ tệp trong RAM.

### Ví dụ 3 — đọc, chuẩn hóa và ghi UTF-8

Lưu thành **`NormalizeTextDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class NormalizeTextDemo {
    private static String visible(String value) {
        return value.replace("\\", "\\\\")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("line-ending-", ".txt");

        try {
            Files.writeString(path, "A\r\nB\rC\n", StandardCharsets.UTF_8);

            String original = Files.readString(path, StandardCharsets.UTF_8);
            String normalized = original.replace("\r\n", "\n")
                    .replace('\r', '\n');

            Files.writeString(path, normalized, StandardCharsets.UTF_8);

            System.out.println("before: " + visible(original));
            System.out.println("after : " + visible(normalized));
            System.out.println("lines : " + normalized.lines().count());
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 NormalizeTextDemo.java
java NormalizeTextDemo
```

Đầu ra đã được kiểm tra; các ký hiệu `\r`/`\n` trong output được tạo bởi phương thức `visible` để nhìn thấy ký tự điều khiển:

```text
before: A\r\nB\rC\n
after : A\nB\nC\n
lines : 3
```

Trong ví dụ, tệp tạm được tạo tự động và xóa bằng `finally`. Chương trình bảo toàn **sự có mặt của một newline cuối**, đồng thời chuẩn hóa ba loại separator thành LF. Với tệp thật của người dùng, chỉ ghi đè khi đó là yêu cầu đã được xác nhận; nên giữ bản sao hoặc sử dụng chiến lược ghi an toàn nếu mất dữ liệu có hậu quả.

### Vì sao không chuẩn hóa bằng `lines().collect(joining("\n"))`?

Giả sử `raw = "A\n\n"`:

- `raw.lines()` tạo hai phần tử `"A"` và `""`.
- `Collectors.joining("\n")` ghép chúng thành `"A\n"`.
- Chuỗi mới **thiếu một LF** so với chuỗi gốc, làm mất thông tin về dòng rỗng có dấu kết thúc cuối.

Tương tự, `"A\n"` qua `lines()` rồi `joining("\n")` thành `"A"`, mất newline cuối. Do vậy, pipeline tách dòng là cách tốt để xử lý **nội dung dòng**, nhưng không phải công cụ mặc định để bảo toàn cấu trúc EOL. Nếu yêu cầu chuẩn hóa nguyên văn, hãy biến đổi trực tiếp ký tự CRLF/CR như trên hoặc dùng parser có bảo toàn separator.

## 8. Kịch bản thường gặp và quyết định phù hợp

### 8.1 Nhận văn bản đa dòng từ form/API

Dữ liệu copy/paste có thể chứa LF, CRLF hoặc CR. Nếu hệ thống lưu dạng chuẩn, hãy xác định một chính sách, ví dụ chuẩn hóa CRLF/CR thành LF ở biên nhập **sau khi xác thực dữ liệu là văn bản thông thường**. Sau đó validation nội dung (số dòng, độ dài, không cho phép dòng trống...) chạy trên dạng đã chuẩn hóa, giúp kết quả nhất quán.

Nếu trường dữ liệu chỉ cho phép một dòng (tên tài khoản, mã định danh, header value...), kiểm tra và từ chối ký tự CR/LF khi không hợp lệ. Không vô tình cho phép chèn CR/LF vào log, header hoặc định dạng có cú pháp điều khiển riêng.

### 8.2 So sánh tệp, tạo snapshot và kiểm thử

`assertEquals("A\n", actual)` phân biệt `"A\n"` với `"A\r\n"` và `"A"`. Khi test thất bại, in ký tự đặc biệt dưới dạng escape hoặc kiểm tra code point/byte thay vì chỉ nhìn terminal. Nếu thông số hệ thống **cho phép** các kiểu line ending tương đương, chuẩn hóa hai phía trước khi so sánh. Nếu đang kiểm tra chính xác payload/giao thức, **không** chuẩn hóa vì sẽ che lỗi có thật.

Đối với snapshot văn bản, thống nhất charset và line ending trong repo/test giúp kết quả ít phụ thuộc hệ điều hành. Khi thật sự cần “luôn có LF cuối tệp”, kiểm tra riêng bằng `endsWith("\n")`; nếu yêu cầu phân biệt LF với CRLF, dùng bộ phân loại `finalTerminator(...)`.

### 8.3 Làm việc nhóm với Git

Git có thể chuyển đổi line ending trong file văn bản khi checkout/check-in theo cấu hình. Quy tắc repo có thể được mô tả bằng `.gitattributes` để tránh đổi EOL ngoài ý muốn, chẳng hạn:

```gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
```

Đây chỉ là **ví dụ chính sách**: chọn thiết lập phù hợp dự án. Các khác biệt LF/CRLF ngoài ý muốn làm diff rối, ảnh hưởng script hoặc snapshot. Tuy nhiên, điều này không thay đổi quy tắc `String.lines()` khi chương trình đã nhận một chuỗi. Kiểm tra cả nội dung repository và working tree khi phân tích lỗi khác hệ điều hành.

### 8.4 Khi nào bảo toàn EOL gốc?

Bảo toàn nguyên văn khi cần đối chiếu checksum, chữ ký, byte-for-byte, định dạng do bên ngoài áp đặt, hoặc tệp người dùng muốn chỉnh sửa mà không thay đổi những dòng khác. Chỉ dùng `String.lines()`/`BufferedReader.readLine()` là chưa đủ cho trường hợp này vì chúng bỏ separator. Nếu cần chỉnh riêng một dòng nhưng giữ EOL khác nhau trên từng dòng, thiết kế parser trả cả `text` và `terminator` (LF/CR/CRLF/NONE), rồi serialize bằng đúng terminator đã lưu.

## 9. Những lỗi phổ biến và cách tránh

| Lỗi | Vì sao sai | Cách làm đúng |
|---|---|---|
| Tưởng CRLF tạo hai dòng | CRLF là một dấu kết thúc gồm hai ký tự | Nhận diện cặp `\r\n` trước khi xử lý từng ký tự |
| Đếm số `\n` rồi coi bằng `lines().count()` | CR đơn lẻ cũng kết thúc dòng; EOF không tạo phantom line | Dùng `lines()` để đếm dòng nội dung theo API, kiểm tra EOL riêng |
| Nghĩ `"A\n"` có hai phần tử khi gọi `lines()` | Dấu cuối không tạo phần tử rỗng mới | Kết quả là một phần tử `"A"` |
| Loại bỏ mọi dòng trống và nghĩ dữ liệu vẫn nguyên vẹn | Thay đổi số dòng và cấu trúc văn bản | Chỉ lọc rỗng khi yêu cầu nghiệp vụ cho phép |
| Dùng `split("\n")` với dữ liệu CRLF | `\r` có thể còn dính vào cuối phần tử | Dùng `lines()` cho LF/CR/CRLF, hoặc parser đúng hợp đồng |
| Dùng `split("\\R")` rồi ngỡ giữ trailing empty | `split` mặc định limit `0` bỏ phần tử rỗng cuối | Dùng `split("\\R", -1)` khi muốn giữ phần tử rỗng cuối |
| Tưởng `String.lines()` tách U+2028 | Java 11 chỉ nhận LF/CR/CRLF | Nếu cần Unicode linebreak rộng hơn, dùng regex `\R` hoặc quy tắc riêng |
| Ghép lại bằng `joining("\n")` và tuyên bố giữ nguyên tệp | Mất loại EOL gốc và có thể mất newline cuối | Bảo toàn raw text hoặc lưu separator riêng |
| Dùng `System.lineSeparator()` trong mọi định dạng | Kết quả phụ thuộc môi trường, có thể trái hợp đồng | Dùng LF/CRLF cố định khi định dạng yêu cầu |
| Đọc tệp lớn bằng `Files.readString` rồi `lines()` | Có thể tốn nhiều RAM | Dùng stream/buffer và đóng tài nguyên |
| Suy kết luận từ terminal hiển thị | Terminal/editor có thể không phân biệt CR, LF, CRLF | In escape hoặc kiểm tra byte/char chính xác |
| Sửa newline trên tệp nhị phân hoặc tệp có chữ ký | Byte thay đổi làm hỏng dữ liệu/hợp đồng | Xác nhận loại dữ liệu và yêu cầu trước khi chuẩn hóa |

## 10. Bài tập tự luyện

**Bài 1 — dự đoán đầu ra.** Với từng chuỗi `""`, `"\r\n"`, `"A\rB\n"` và `"A\n\n"`, hãy dự đoán số phần tử của `lines()`, phần tử rỗng có hay không và chuỗi kết thúc bằng loại delimiter nào. Sau đó kiểm chứng bằng `LineBreakDemo`.

**Đáp án:** lần lượt là 0; 1 dòng rỗng với CRLF cuối; 2 dòng `A`/`B` với LF cuối; 2 dòng `A`/rỗng với LF cuối. Không có trường hợp nào tự sinh dòng sau terminator cuối.

**Bài 2 — làm rõ ý nghĩa của “dòng cuối”.** Tại sao `"A"` và `"A\n"` cho cùng `List<String>` khi thu thập từ `lines()`, nhưng có thể khác kết quả checksum? **Đáp án:** `lines()` bỏ ký tự kết thúc; checksum tính trên dữ liệu gốc nên LF bổ sung làm dữ liệu khác.

**Bài 3 — chuẩn hóa có kiểm soát.** Đầu vào `"A\r\nB\rC\n"` muốn nhận dạng LF/CRLF/CR rồi đưa về LF, nhưng **không mất newline cuối**. Hãy nêu kết quả. **Đáp án:** `"A\nB\nC\n"`. Sau chuẩn hóa có ba dòng và vẫn có một LF kết thúc.

**Bài 4 — khác biệt Unicode.** Xét chuỗi tạo bởi `"A" + (char) 0x2028 + "B"`. `lines().count()` và `split("\\R", -1).length` khác nhau thế nào? **Đáp án:** lần lượt 1 và 2 trên Java 11, vì `String.lines()` không tách U+2028, còn regex `\R` có nhận diện.

**Bài 5 — tình huống dự án.** Một test chạy được trên Linux nhưng thất bại trên Windows vì API tạo file có `System.lineSeparator()` và snapshot cố định LF. Cách sửa tùy **hợp đồng dữ liệu**: nếu snapshot được quy định LF, tạo LF một cách tường minh; nếu thực sự cho phép EOL nền tảng, chuẩn hóa dữ liệu trong assertion và kiểm tra riêng hành vi nghiệp vụ. Không “vá” bằng xóa mọi newline mà làm mất ý nghĩa.

## 11. Tài liệu API chính thức

- [Java SE 11 — String](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html): hợp đồng `lines()`, `isBlank()` và thao tác chuỗi.
- [Java SE 11 — Pattern](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/regex/Pattern.html): `\R` (Unicode linebreak matcher), cú pháp regex.
- [Java SE 11 — Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): `readString`, `writeString`, `lines`.
- [Java SE 11 — BufferedReader](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/BufferedReader.html): `readLine()` và các dấu kết thúc dòng.
- [Java SE 11 — System](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/System.html): `lineSeparator()`.

**Ghi nhớ khi áp dụng:** Hãy xác định bạn cần **nội dung dòng** hay **văn bản nguyên vẹn kể cả dấu kết thúc**. `String.lines()` là công cụ đúng cho nhu cầu thứ nhất; đọc và giữ chuỗi gốc hoặc parser giữ terminator mới đáp ứng nhu cầu thứ hai. Việc chuẩn hóa LF/CRLF chỉ nên thực hiện khi quy tắc dữ liệu cho phép.