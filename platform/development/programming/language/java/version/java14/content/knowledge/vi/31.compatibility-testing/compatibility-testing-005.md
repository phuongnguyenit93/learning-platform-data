# Kiểm thử chuỗi theo ký tự, xuống dòng và khoảng trắng để bảo đảm tương thích Java

## 1. Vì sao một chuỗi “nhìn giống nhau” vẫn có thể làm bài test thất bại?

Khi nâng cấp JDK, chuyển hệ điều hành, sửa text block, đọc file cấu hình hoặc kiểm thử kết quả của một công cụ tạo code, điều khó thấy nhất thường không phải nội dung chữ **đang được hiển thị**, mà là những ký tự vô hình bên trong chuỗi:

- Một dòng kết thúc bằng **LF** (`\n`, U+000A) thay vì **CRLF** (`\r\n`, U+000D U+000A).
- Có hoặc không có một ký tự xuống dòng ở **cuối cùng**.
- Một ký tự **tab** (`\t`, U+0009) thay cho bốn dấu cách (`U+0020`).
- Dấu cách **cuối dòng** bị xóa bởi formatter hoặc `stripIndent()`.
- Hai cách viết Unicode trông giống nhau nhưng có dãy code point khác nhau.
- Một emoji là **hai UTF-16 code units** dù thường được nhìn như một ký tự.
- File chứa đúng văn bản nhưng lại có **byte encoding** khác.

Ví dụ hai chuỗi dưới đây có thể trông như cùng một dòng ở giao diện nhưng **không bằng nhau**:

```java
String a = "ready\n";
String b = "ready\r\n";

System.out.println(a.equals(b)); // false
```

Đây là đoạn trong một phương thức. `a` chứa một LF; `b` chứa CR rồi LF. Cả hai đều biểu thị “xuống dòng” trong nhiều hệ thống, nhưng dãy ký tự không giống nhau. Nếu một giao thức quy định **CRLF chính xác**, việc tự ý đổi về LF sẽ là lỗi. Nếu ứng dụng chỉ cần nội dung các dòng và quy ước được phép chuẩn hóa, so sánh sau normalization có thể hợp lý.

**Mục tiêu của bài:** tạo phép thử đủ chặt để xác minh **chuỗi thực tế theo từng đơn vị ký tự, xuống dòng và khoảng trắng**, đồng thời không tạo lỗi giả khi cùng một hợp đồng cho phép khác biệt nền tảng.

**Ngữ cảnh phiên bản Java 14:** Text blocks từng được thử nghiệm ở Java 13–14, nhưng đã trở thành tính năng **chính thức từ Java 15** (JEP 378). Những bài test cần bảo trì hiện nay nên dùng cú pháp **ổn định trên Java 17+**, không tiếp tục dựa vào chế độ preview của Java 14. Các API liên quan như `String.lines()` (Java 11), `String.stripIndent()` (Java 15), `StandardCharsets.UTF_8` và `Normalizer` vẫn áp dụng trên JDK hiện đại.

## 2. Trước khi kiểm thử, phải chọn đúng “hợp đồng bằng nhau”

Không phải mọi trường hợp đều cần một kiểu so sánh duy nhất. Hãy ghi rõ tiêu chí chấp nhận trước khi viết assertion.

| Hợp đồng | Cần giống nhau ở mức nào? | Cách thử phù hợp | Ví dụ |
| --- | --- | --- | --- |
| **Chuỗi chính xác** (*exact string*) | Tất cả UTF-16 code units, gồm CR/LF, dấu cách, tab | `expected.equals(actual)` hoặc `assertEquals` với expected chính xác | Snapshot sinh source, mã thông báo, dữ liệu cần từng ký tự |
| **Nội dung dòng được phép chuẩn hóa** | Cho phép LF/CRLF/CR tương đương theo yêu cầu | Chuẩn hóa terminators có chủ đích, sau đó so sánh | Trình hiển thị log đa nền tảng nếu contract cho phép |
| **Unicode canonical equivalence** | Cho phép các chuỗi Unicode tương đương sau NFC/NFD | `Normalizer.normalize` theo chính sách rõ ràng | So sánh tên người/nhãn có normalization quy định |
| **Dữ liệu byte chính xác** | Từng byte của file/network payload trùng nhau | `Arrays.equals(byte[],byte[])`, `assertArrayEquals` | Protocol, checksum, file nhị phân, UTF-8 golden bytes |
| **Thông điệp người dùng** | Nội dung hiển thị có ý nghĩa tương đương | Test theo hành vi/rendering và quy tắc domain | Giao diện, đa ngôn ngữ, accessibility |

**Quy tắc quyết định:** nếu chưa biết khoảng trắng hoặc newline có mang nghĩa hay không, **đừng tự động gọi `trim()`, `strip()`, `stripIndent()` hoặc thay CRLF bằng LF trước mọi assertion**. Đó có thể là cách khiến test bị “PASS giả” vì đã xóa dấu hiệu lỗi thực sự.

Ví dụ:

```java
String expected = "amount=10\n";
String actual   = "amount=10 \n";

System.out.println(expected.equals(actual));          // false
System.out.println(expected.strip().equals(actual.strip())); // true
```

Trên hai chuỗi này, `strip()` loại bỏ khoảng trắng ở cuối và có thể làm chúng bằng nhau, **che giấu sự khác biệt cần phát hiện**. Chỉ dùng phép chuẩn hóa khi đặc tả sản phẩm cho phép làm vậy.

## 3. Java `String` thực chất đếm những gì?

Trong Java, `String` được biểu diễn logic như một dãy **UTF-16 code units**. Vì vậy:

- `length()` trả **số UTF-16 code units**, không phải số byte UTF-8 và không phải số ký tự hiển thị.
- `charAt(i)` trả một **`char` (UTF-16 code unit)** tại chỉ số `i`.
- `codePointCount(begin,end)` đếm **Unicode code points**, kết hợp các surrogate pair hợp lệ.
- `codePoints()` duyệt code point, hữu ích khi cần so sánh ở mức Unicode scalar/code point.
- `getBytes(StandardCharsets.UTF_8)` tạo **byte[] UTF-8**; độ dài có thể khác `String.length()`.
- `equals` kiểm tra sự bằng nhau của nội dung `String`, **không tự chuẩn hóa Unicode hay newline**.

Ví dụ:

```java
String value = "A" + new String(Character.toChars(0x1F4A1));

System.out.println(value.length()); // 3 UTF-16 code units
System.out.println(value.codePointCount(0, value.length())); // 2 code points
```

Giả sử mã ở trong một phương thức. `0x1F4A1` là code point của biểu tượng bóng đèn; nó được biểu diễn bằng **hai `char` UTF-16**. Cộng với chữ `A`, ta được `length()==3` nhưng `codePointCount()==2`.

**Thêm một mức nữa:** code point cũng **không luôn** tương đương “ký tự người dùng nhìn thấy” (*grapheme cluster*). Ví dụ `e` và dấu sắc kết hợp có thể tạo một hình chữ hiển thị nhưng chứa hai code points. Khi muốn đo vị trí con trỏ/ngắt cụm chữ theo quy tắc Unicode, cần logic grapheme segmentation tương ứng; `charAt` không giải quyết được.

### Bảng một số ký tự khó nhìn

| Ký tự | Java literal | Unicode | Ghi chú |
| --- | --- | --- | --- |
| Space thường | `" "` | U+0020 | Không nhìn thấy ở cuối dòng |
| Tab ngang | `"\t"` | U+0009 | Không tương đương cố định bốn spaces |
| Line Feed (LF) | `"\n"` | U+000A | Một UTF-16 code unit |
| Carriage Return (CR) | `"\r"` | U+000D | Một UTF-16 code unit |
| CRLF | `"\r\n"` | U+000D U+000A | **Hai** UTF-16 code units |
| Non-breaking space | `"\u00A0"` | U+00A0 | Trông gần giống space thường nhưng khác |
| Dấu sắc kết hợp | `"\u0301"` | U+0301 | Có thể nối với chữ đứng trước |
| Zero-width space | `"\u200B"` | U+200B | Không nên tự cho là “trống vô hại” |
| Dấu chấm đầu dòng | `"•"` | U+2022 | Là một code point độc lập |

**Lưu ý về `\u...` trong mã nguồn Java:** Unicode escapes được xử lý sớm trong quá trình đọc source theo Java Language Specification. Để viết LF trong một string literal, dùng `"\n"` thay vì cố đưa `\u000A` vào phần text literal; Unicode escape sớm có thể tạo xuống dòng thật và làm lỗi cú pháp. Với text blocks, `\s` có vai trò đặc biệt để bảo toàn dấu cách cuối dòng, giải thích ở phần sau.

## 4. Kiểm tra ký tự tại vị trí khác nhau đầu tiên

`String.equals` cho câu trả lời **đúng/sai**, nhưng khi hai chuỗi dài khác nhau chỉ ở dấu trắng, thông báo `expected/actual` mặc định có thể khó đọc.

Một bộ kiểm thử tốt nên biết:

1. Vị trí khác nhau đầu tiên theo **UTF-16 code unit index**.
2. Giá trị ở vị trí đó dưới dạng **U+XXXX** hoặc `<END>` nếu một bên đã hết.
3. Độ dài expected/actual; phân biệt một bên thiếu ký tự cuối.
4. Với output nhiều dòng, có thể bổ sung **số dòng và vị trí trong dòng**, tính CR/LF đúng theo hợp đồng.
5. Khi cần bit-exact, hiển thị **byte hex** riêng với char/code point hex.

Hàm cơ bản:

```java
static int firstMismatch(String expected, String actual) {
    int limit = Math.min(expected.length(), actual.length());
    for (int i = 0; i < limit; i++) {
        if (expected.charAt(i) != actual.charAt(i)) {
            return i;
        }
    }
    return expected.length() == actual.length() ? -1 : limit;
}
```

Hợp đồng: trả **`-1`** nếu giống nhau, hoặc **vị trí UTF-16 code unit đầu tiên khác nhau**. Nếu một chuỗi là tiền tố của chuỗi còn lại, trả độ dài của chuỗi ngắn hơn (vị trí bên ngắn đã hết).

Đây là phương thức hoàn chỉnh để đặt trong một class, **không phải file độc lập**. Nó cố ý làm việc theo UTF-16 vì `String.equals` cũng so sánh nội dung `String` ở mức này.

Hàm biến một `char` thành ký hiệu dễ quan sát:

```java
static String at(String text, int index) {
    return index >= text.length()
            ? "<END>"
            : String.format("U+%04X", (int) text.charAt(index));
}
```

Nếu hai chuỗi:

```java
String expected = "item \n";
String actual = "item\n";
```

thì vị trí khác đầu tiên là **index 4** (đếm từ 0). Expected có **space U+0020**, actual có **LF U+000A**. Không cần đoán bằng mắt liệu dòng có một hay nhiều dấu cách.

**Giới hạn:** với ký tự nằm ngoài BMP, một Unicode code point có thể gồm hai `char`. Nếu muốn báo lỗi theo **code point index**, cần thuật toán riêng dùng `codePoints()`/`offsetByCodePoints`, không được in chỉ số `charAt` rồi gọi nó là vị trí code point.

## 5. Ví dụ Java 17+ độc lập và có thể chạy ngay

Chương trình sau kiểm tra **toàn bộ ba trục**: ký tự, xuống dòng, khoảng trắng. Nó cố ý thêm test Unicode và file UTF-8 để minh họa giới hạn tương thích khi đổi OS/JDK.

Mỗi assertion “exact” thất bại sẽ ném `AssertionError` kèm **chỉ số UTF-16** và code unit expected/actual. Chương trình chỉ in các dấu mốc `PASS` khi dữ liệu thực sự khớp.

### Tệp `Main.java`

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.util.Arrays;

public class Main {
    static int firstMismatch(String expected, String actual) {
        int limit = Math.min(expected.length(), actual.length());
        for (int i = 0; i < limit; i++) {
            if (expected.charAt(i) != actual.charAt(i)) {
                return i;
            }
        }
        return expected.length() == actual.length() ? -1 : limit;
    }

    static String at(String text, int index) {
        return index >= text.length()
                ? "<END>"
                : String.format("U+%04X", (int) text.charAt(index));
    }

    static void assertExact(String label, String expected, String actual) {
        int difference = firstMismatch(expected, actual);
        if (difference >= 0) {
            throw new AssertionError(label + " at UTF16 index " + difference
                    + ": expected " + at(expected, difference)
                    + " but was " + at(actual, difference));
        }
        System.out.println(label + "=PASS");
    }

    static String normalizeEol(String input) {
        return input.replace("\r\n", "\n").replace('\r', '\n');
    }

    public static void main(String[] args) throws Exception {
        String block = """
                alpha\s
                beta
                """;
        assertExact("TEXT_BLOCK", "alpha \nbeta\n", block);

        String joined = """
                A\
                B
                """;
        assertExact("LINE_CONTINUATION", "AB\n", joined);

        String lf = "x\ny\n";
        String crlf = "x\r\ny\r\n";
        System.out.println("CRLF_DIFFERS=" + !lf.equals(crlf));
        System.out.println("FIRST_EOL_MISMATCH=" + firstMismatch(lf, crlf));
        assertExact("EOL_NORMALIZED", lf, normalizeEol(crlf));
        assertExact("MIXED_EOL_NORMALIZED", "x\ny\nz\n",
                normalizeEol("x\ry\r\nz\n"));

        System.out.println("TRAILING_SPACE_DIFFERS=" +
                !"item \n".equals("item\n"));
        assertExact("TRAILING_SPACE", "item \n", "item" + " " + "\n");

        System.out.println("TAB_DIFFERS_FROM_SPACES=" +
                !"a\tb".equals("a    b"));
        assertExact("TAB", "a\u0009b", "a\tb");

        String astral = "A" + new String(Character.toChars(0x1F4A1));
        System.out.println("UTF16_UNITS=" + astral.length());
        System.out.println("CODE_POINTS=" +
                astral.codePointCount(0, astral.length()));

        String combining = "e\u0301";
        String precomposed = "\u00E9";
        System.out.println("RAW_UNICODE_DIFFERS=" +
                !combining.equals(precomposed));
        System.out.println("NFC_EQUAL=" + Normalizer.normalize(
                combining, Normalizer.Form.NFC).equals(precomposed));
        System.out.println("UTF8_BYTES_GT_UTF16_UNITS=" +
                (precomposed.getBytes(StandardCharsets.UTF_8).length
                        > precomposed.length()));

        System.out.println("LINES_DROP_TERMINATOR=" +
                ("x\n".lines().count() == 1L
                        && "x\n".lines().findFirst()
                                .orElseThrow().equals("x")));

        Path file = Files.createTempFile("exact-text-", ".txt");
        try {
            Files.writeString(file, block, StandardCharsets.UTF_8);
            assertExact("UTF8_FILE", block,
                    Files.readString(file, StandardCharsets.UTF_8));
            System.out.println("UTF8_FILE_BYTES=" + Arrays.equals(
                    block.getBytes(StandardCharsets.UTF_8),
                    Files.readAllBytes(file)));
        } finally {
            Files.deleteIfExists(file);
        }

        int index = firstMismatch("item \n", "item\n");
        System.out.println("WHITESPACE_DIFF_INDEX=" + index);
        System.out.println("WHITESPACE_EXPECTED=" + at("item \n", index));
        System.out.println("WHITESPACE_ACTUAL=" + at("item\n", index));
    }
}
```

### Lệnh biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

**Đầu ra chính xác đã kiểm chứng** khi chạy với JDK hiện đại:

```text
TEXT_BLOCK=PASS
LINE_CONTINUATION=PASS
CRLF_DIFFERS=true
FIRST_EOL_MISMATCH=1
EOL_NORMALIZED=PASS
MIXED_EOL_NORMALIZED=PASS
TRAILING_SPACE_DIFFERS=true
TRAILING_SPACE=PASS
TAB_DIFFERS_FROM_SPACES=true
TAB=PASS
UTF16_UNITS=3
CODE_POINTS=2
RAW_UNICODE_DIFFERS=true
NFC_EQUAL=true
UTF8_BYTES_GT_UTF16_UNITS=true
LINES_DROP_TERMINATOR=true
UTF8_FILE=PASS
UTF8_FILE_BYTES=true
WHITESPACE_DIFF_INDEX=4
WHITESPACE_EXPECTED=U+0020
WHITESPACE_ACTUAL=U+000A
```

Chương trình được **biên dịch bằng `javac --release 17` và chạy thành công**; cả 21 dòng trên đã khớp. Việc in LF/CRLF theo nhãn Boolean và giá trị Unicode giúp đầu ra minh bạch, tránh phụ thuộc terminal hiển thị dấu trắng như thế nào.

## 6. Hiểu từng nhóm kết quả của chương trình

### Nhóm 1 — Text block và dấu cách ở cuối dòng

`TEXT_BLOCK=PASS` cho biết text block từ source:

```java
String block = """
        alpha\s
        beta
        """;
```

có nội dung chính xác tương đương:

```java
String expected = "alpha \nbeta\n";
```

Một dấu **space** đứng ngay sau `alpha` **được giữ lại nhờ `\s`**. Sau `alpha ` có LF, sau `beta` cũng có LF. Đường biên cuối chuỗi rất quan trọng: nếu bỏ LF ở cuối expected, phép so sánh exact sẽ thất bại.

`LINE_CONTINUATION=PASS` cho thấy:

```java
String joined = """
        A\
        B
        """;
```

trả về `"AB\n"`, do `\` ở cuối dòng **ngăn chèn line terminator** tại đó. Đây là ví dụ chính xác về **ký tự trong String sau biên dịch**, không phải chỉ là hai dòng trong editor.

### Nhóm 2 — LF, CRLF và việc chuẩn hóa có chủ đích

- `CRLF_DIFFERS=true`: `"x\ny\n"` và `"x\r\ny\r\n"` không bằng nhau theo `String.equals`.
- `FIRST_EOL_MISMATCH=1`: sau chữ `x`, expected có LF nhưng actual có CR.
- `EOL_NORMALIZED=PASS`: khi đặc tả cho phép, thay CRLF bằng LF sẽ làm hai văn bản dòng trở nên tương đương.
- `MIXED_EOL_NORMALIZED=PASS`: hàm còn xử lý một CR đứng riêng và CRLF lẫn nhau.

**Lưu ý:** chuẩn hóa chỉ phù hợp khi hợp đồng cho phép. Một header HTTP hoặc file có yêu cầu newline chính xác không được sửa bằng cách thay toàn bộ `\r\n` thành `\n` rồi báo PASS.

### Nhóm 3 — Dấu cách, tab và thông báo vị trí lỗi

- `TRAILING_SPACE_DIFFERS=true`: `"item \n"` khác `"item\n"`.
- `TRAILING_SPACE=PASS`: expected và actual có cùng space U+0020 trước LF.
- `TAB_DIFFERS_FROM_SPACES=true`: tab U+0009 khác bốn space U+0020, dù editor có thể render gần giống.
- `TAB=PASS`: `"a\u0009b"` và `"a\tb"` có cùng dãy UTF-16 code units.
- Ba dòng cuối cho thấy dấu cách bị thiếu tại **UTF-16 index 4**, expected `U+0020` nhưng actual `U+000A`.

Đừng sửa test sai bằng cách gọi `replace("\t", "    ")` nếu format file/giao thức yêu cầu tab thật. Nếu ứng dụng có quy tắc thụt đầu dòng cho phép nhiều cách trình bày, hãy mô tả quy tắc tương đương và viết một phép thử **đúng theo đặc tả**.

### Nhóm 4 — Unicode và việc đếm “ký tự”

- `UTF16_UNITS=3` và `CODE_POINTS=2` là đúng cho `"A"` cộng một ký tự supplementary.
- `RAW_UNICODE_DIFFERS=true`: `"e\u0301"` và `"\u00E9"` khác dãy code units.
- `NFC_EQUAL=true`: hai biểu diễn đó tương đương sau Unicode normalization dạng NFC.
- `UTF8_BYTES_GT_UTF16_UNITS=true`: `é` chiếm một UTF-16 code unit nhưng hai byte UTF-8.

**Unicode normalization là quyết định theo nghiệp vụ**. Với chữ ký số, hash, key, ID chính xác hoặc file cần bit-for-bit, không được tự động normalize rồi coi bytes vốn khác nhau là giống nhau. Khi sản phẩm **định nghĩa** canonical equivalence, hãy normalize **trước khi lưu và trước khi so sánh** theo một quy tắc nhất quán.

### Nhóm 5 — Đọc từng dòng không giữ lại newline

`LINES_DROP_TERMINATOR=true` xác minh:

```java
"x\n".lines().count() == 1L
```

và phần tử dòng duy nhất là `"x"`, **không bao gồm `\n`**. Vì vậy `String.lines()` hữu ích để xử lý **nội dung từng dòng**, nhưng **không đủ để phục dựng nguyên văn** mọi CR, LF, CRLF và dấu kết thúc file.

### Nhóm 6 — Tệp UTF-8

Hai dòng `UTF8_FILE=PASS` và `UTF8_FILE_BYTES=true` cho thấy:

1. Ghi `block` vào một tệp tạm qua `Files.writeString(file, block, UTF_8)`.
2. Đọc lại bằng `Files.readString(file, UTF_8)` và so sánh nguyên chuỗi.
3. Kiểm tra các byte file đúng bằng `block.getBytes(UTF_8)`.
4. Xóa tệp tạm trong `finally` để không để lại dữ liệu test.

Đây là hai phép xác minh **khác nhau**: String equality và byte equality. Một ứng dụng có thể đọc được text nhưng vẫn có format byte khác (ví dụ BOM, charset, line ending), nên nếu cần compatibility của artifact, phải kiểm tra cả byte layer.

## 7. Text block: các quy tắc phải đưa vào test

Text blocks được chuẩn hóa ở JDK 15 (JEP 378). Java 14 từng có phiên bản preview, nhưng đối với codebase hiện hành nên dùng cú pháp ổn định và test với Java 17+ hoặc những JDK thực sự được sản phẩm hỗ trợ.

### 7.1. Một newline sau dấu mở

Text block bắt đầu bằng bộ dấu nháy kép `"""` rồi tới một **line terminator bắt buộc**. Nội dung được lấy từ các dòng tiếp theo. Ví dụ:

```java
String value = """
        hello
        """;
```

tạo chuỗi `"hello\n"`. Đừng nhầm “bắt buộc xuống dòng sau opening delimiter” với việc String phải **bắt đầu** bằng newline: newline đóng vai trò phân cách cú pháp, không tự chèn một LF đầu nội dung.

### 7.2. Có hay không có newline cuối

```java
String withFinalLf = """
        hello
        """;

String withoutFinalLf = """
        hello""";
```

`withFinalLf` chứa `"hello\n"`, còn `withoutFinalLf` chứa `"hello"`. Vị trí của dấu đóng có thể làm khác nhau **một ký tự vô hình nhưng quan trọng**. Dùng `assertEquals("hello\n", withFinalLf)` và `assertEquals("hello", withoutFinalLf)` để kiểm tra đúng hợp đồng.

### 7.3. Incidental indentation bị loại bỏ

Text block loại bỏ phần thụt đầu dòng được coi là *incidental white space* theo quy tắc ngôn ngữ để code vẫn có thể được thụt theo bố cục Java source mà giá trị chuỗi không chứa những dấu cách dư đó.

```java
String sql = """
        SELECT id, name
          FROM customers
         WHERE active = true
        """;
```

Giá trị nhận được giữ **tương quan thụt lề có ý nghĩa** giữa các dòng. Khi làm golden test, đừng chép số space ở **trước nội dung trong file `.java`** vào expected mà chưa tính quy tắc strip incidental indentation.

Đặc biệt, vị trí dấu đóng `"""` cũng tham gia tính mức thụt lề; di chuyển nó có thể thay đổi giá trị String. Lúc sửa formatter hoặc refactor text block, chạy lại test so sánh **nội dung String thực tế**, không chỉ review diff mã nguồn.

### 7.4. Trailing spaces và `\s`

Bình thường, khoảng trắng cuối dòng trong text block được coi là incidental và loại bỏ. Nếu cần giữ một dấu space cụ thể:

```java
String text = """
        alpha\s
        beta
        """;
```

Giá trị là `"alpha \nbeta\n"`. `\s` trong **Java string/text block** là một **escape đại diện cho U+0020**, không phải “mọi loại whitespace”.

**Cẩn thận:** `\s` trong ngữ cảnh **regex** là khái niệm khác. Muốn truyền regex whitespace class đến `Pattern`, thường cần viết `"\\s"` trong Java source. Đừng nhầm hai tầng escape khác nhau.

Một cách khác là `\040` (octal escape cho space), nhưng `\s` diễn đạt rõ hơn khi mục tiêu là giữ một dấu cách cuối dòng trong Java hiện đại. Tránh dùng `\u0020` để thay `\s` trong source text block: Unicode escapes được xử lý sớm, nên dấu cách có thể bị xem là trailing incidental whitespace và bị loại bỏ.

### 7.5. Backslash + newline là line continuation

```java
String text = """
        Java\
        17
        """;
```

trả `"Java17\n"`. Dấu backslash ở cuối dòng khiến newline đó **không nằm trong String**. Đây là ví dụ quan trọng cho compatibility test: hai dòng source không đồng nghĩa hai dòng trong String kết quả.

### 7.6. Line terminators trong text block được chuẩn hóa thành LF

Compiler chuẩn hóa các line terminators của **source text block** thành LF `\n`. Do đó cùng một text block chứa các dòng nguồn được lưu dưới CRLF trên Windows hoặc LF trên Linux vẫn có thể tạo String với LF tương ứng.

**Không áp dụng quy tắc này cho mọi String lấy từ file hoặc mạng.** Khi đọc một tệp bằng `Files.readString`, các CR/LF trong nội dung tệp không được tự động chuẩn hóa thành LF theo quy tắc text block. Chỉ **cú pháp text block của source Java** có bước xử lý đó.

**Không dùng chế độ preview của Java 14 trong ví dụ này:** cú pháp đã chuẩn từ JDK 15; việc test phiên bản Java 14 (nếu có yêu cầu bảo trì riêng) phải xét bộ quy tắc preview của thời điểm đó, không coi là cách viết ổn định nên khuyến nghị hiện nay.

## 8. Xuống dòng: LF, CRLF, CR và `System.lineSeparator()`

Ở mức String, Java phân biệt rõ:

```java
String lf = "a\nb\n";
String crlf = "a\r\nb\r\n";
String cr = "a\rb\r";
```

Dãy UTF-16 không giống nhau. Việc terminal/editor có thể hiển thị thành hai dòng là vấn đề **rendering**, không thay đổi dữ liệu String.

### 8.1. Chọn quy tắc theo mục đích

**Văn bản nội bộ đã quy định LF:** kiểm tra exact với `"\n"`, kể cả khi chạy Windows.

**Văn bản xuất cho nền tảng host:** nếu đặc tả thật sự yêu cầu newline nền tảng, dùng `System.lineSeparator()`, và khi test hãy tính expected từ cùng quy ước chứ không hardcode CRLF cho mọi OS.

**Giao thức đòi CRLF:** dùng `"\r\n"` tường minh; không dùng `System.lineSeparator()` vì nó có thể là LF trên Linux/macOS.

**So sánh nội dung dòng khi EOL không quan trọng:** có thể chuẩn hóa có chủ đích bằng:

```java
static String normalizeEol(String input) {
    return input.replace("\r\n", "\n").replace('\r', '\n');
}
```

Thứ tự rất quan trọng: thay **CRLF trước**, rồi CR lẻ. Nếu thay CR bằng LF trước, CRLF sẽ thành **hai LF**, thay đổi số dòng.

### 8.2. Giữ riêng kiểm thử format và kiểm thử nội dung

Một cách thiết kế tốt là có **hai assertion**:

- `assertEquals(expectedNormalized, normalizeEol(actual))` để xác minh nội dung khi EOL được phép khác.
- `assertEquals(expectedWireBytes, Files.readAllBytes(file))` nếu sản phẩm đồng thời yêu cầu format byte chính xác.

Đừng normalize toàn bộ golden snapshot trong cùng hàm helper rồi quên rằng một file xuất cho đối tác phải chứa CRLF.

### 8.3. `String.lines()` không giữ lại delimiters

`String.lines()` chấp nhận LF, CR, CRLF làm line terminator và trả stream các dòng **đã bỏ terminator**. Nó không tạo dòng rỗng **mới** sau một terminator cuối cùng:

```java
System.out.println("x\n".lines().count()); // 1
System.out.println("".lines().count());    // 0
```

Vì vậy `String.lines()` rất phù hợp khi quan tâm “mỗi dòng có nội dung gì” nhưng không phù hợp khi quan tâm “chuỗi có bao nhiêu ký tự CR/LF, có LF cuối file hay không”. Dùng `String.equals` hoặc byte comparison cho mục tiêu exact.

### 8.4. `String.indent(0)` và `stripIndent()` cũng có tác động

`String.indent(0)` **không nhất thiết giữ nguyên mọi line ending**; API chuẩn hóa các line terminators trong quá trình tạo kết quả. `String.stripIndent()` loại bỏ incidental indentation/trailing whitespace theo quy tắc của API, đồng thời chuẩn hóa các line terminators.

Đừng dùng hai phương thức này làm “bước xử lý vô hại” trong một phép kiểm tra cần dữ liệu String giống nguyên gốc. Chỉ dùng khi bạn **chủ ý muốn một định dạng normalized**.

## 9. Khoảng trắng: space, tab, NBSP và dấu cách cuối dòng

### 9.1. Space khác tab, kể cả khi hiển thị cùng cột

```java
String withTab = "col1\tcol2";
String withSpaces = "col1    col2";

System.out.println(withTab.equals(withSpaces)); // false
```

Tab là **U+0009**, spaces là nhiều **U+0020**. Editor có thể cấu hình tab width 2, 4 hoặc 8 cột, nên hai chuỗi có thể nhìn giống nhau trong một giao diện và khác nhau ở giao diện khác. Một file TSV yêu cầu tab thật; thay nó bằng spaces sẽ làm sai format cột.

### 9.2. Trailing whitespace có thể là dữ liệu hợp lệ

```java
String expected = "name \n";
String actual = "name\n";
```

Nếu ứng dụng sản xuất một định dạng **cố định chiều rộng**, hoặc nếu bài học đang kiểm thử `\s` trong text block, dấu cách cuối có thể là phần cần giữ. Dùng `equals` exact để phát hiện.

Nếu hệ thống chỉ hiển thị thông điệp và thỏa thuận rằng bỏ dấu cách đầu/cuối là đúng, có thể normalize **sau khi yêu cầu đã nêu rõ**. Không nên trộn quy tắc “bỏ whitespace thừa” với bài test phải bảo toàn định dạng nguồn.

### 9.3. `trim()` và `strip()` không có cùng ngữ nghĩa

- `trim()` là API lâu đời, xóa các ký tự đầu/cuối trong một phạm vi liên quan mã ký tự không lớn hơn U+0020; nó **không** là Unicode whitespace normalizer tổng quát.
- `strip()` dùng `Character.isWhitespace` và xử lý Unicode theo quy tắc API; không phải mọi ký tự trông như khoảng trắng (chẳng hạn một số non-breaking spaces) đều nhất thiết bị xóa.
- `stripIndent()` làm việc theo **các dòng**, xóa incidental indentation/trailing spaces; nó không chỉ tương đương `strip()` trên toàn chuỗi.
- `isBlank()` kiểm tra một String rỗng hoặc chỉ gồm whitespace theo `Character.isWhitespace`; điều đó khác việc “chuỗi có số byte bằng 0”.

**Không nên thử whitespace bằng phép thay `" "` với `""`** vì nó có thể xóa các spaces có nghĩa, thậm chí nối hai token thành một token khác.

### 9.4. Invisible Unicode characters

Non-breaking space `U+00A0`, zero-width space `U+200B`, combining marks và các ký tự định hướng văn bản có thể khiến một chuỗi **trông giống hệt** chuỗi khác. Khi debug:

1. In code units/code points dưới dạng hex.
2. Ghi độ dài UTF-16 và, nếu cần, code point count.
3. So sánh raw trước khi chuẩn hóa.
4. Xác định đặc tả có cho phép Unicode normalization nào hay không.
5. Không giả định “ký tự không nhìn thấy” là vô hại: nó có thể ảnh hưởng ID, ký số, xử lý search hoặc security.

## 10. Unicode: kết quả hiển thị không chứng minh byte bằng nhau

Hai chuỗi:

```java
String combining = "e\u0301"; // chữ e + combining acute
String precomposed = "\u00E9"; // é là một code point

System.out.println(combining.equals(precomposed)); // false
```

trông gần như cùng một chữ **é** nhưng một bên chứa hai Unicode code points, một bên chứa một code point.

Nếu **yêu cầu sản phẩm định nghĩa canonical equivalence**, dùng:

```java
import java.text.Normalizer;

boolean equivalent = Normalizer.normalize(
        combining, Normalizer.Form.NFC).equals(
        Normalizer.normalize(precomposed, Normalizer.Form.NFC));
System.out.println(equivalent); // true
```

Ví dụ là đoạn **trong một phương thức** với hai biến đã khai báo. `Normalizer.Form.NFC` chọn canonical composition. Không dùng Unicode normalization để âm thầm thay đổi payload có chữ ký, mã kiểm tra hoặc những key mà hợp đồng đòi byte nguyên dạng.

### Code point không hoàn toàn là grapheme

Chuỗi chứa emoji có thể gồm nhiều code points, ví dụ emoji có skin tone modifier, zero-width joiner hoặc regional indicator. Một code point không đồng nghĩa một glyph hay “chữ được người dùng nhìn thấy”. Với test UX thực sự, cần xem xét quy tắc phân đoạn grapheme và rendering/font trên nền tảng đích.

**Đối với bài kiểm thử compatibility của Java String**, hãy nêu rõ test đang so sánh **UTF-16 units, Unicode code points, canonical Unicode strings hay byte encoding**, thay vì gọi chung tất cả là “so sánh ký tự”.

## 11. File, charset và sự khác nhau giữa text và bytes

Nếu chuỗi đúng trong memory nhưng kết quả file khác nhau giữa máy, cần xem **tầng encoding**.

### 11.1. Ghi và đọc với charset xác định

```java
Path file = Path.of("out.txt");
String value = "Xin chào\n";
Files.writeString(file, value, StandardCharsets.UTF_8);

String actual = Files.readString(file, StandardCharsets.UTF_8);
byte[] bytes = Files.readAllBytes(file);
```

Đây là snippet trong phương thức có khai báo `throws IOException` hoặc xử lý checked exception, với import `Path`, `Files` và `StandardCharsets`. `Files.writeString`/`readString` được đưa vào Java 11 và vẫn là lựa chọn phổ biến. **Chúng không tự chuyển mọi CRLF thành LF** theo quy tắc text block; byte ghi ra phản ánh chuỗi và charset đã chọn.

Nếu cần kiểm tra file chính xác:

```java
if (!java.util.Arrays.equals(
        value.getBytes(StandardCharsets.UTF_8), bytes)) {
    throw new AssertionError("file bytes differ");
}
```

### 11.2. Tại sao không dùng charset mặc định?

Java 18 (JEP 400) chuẩn hóa UTF-8 làm charset mặc định cho nhiều API và môi trường, nhưng project có thể chạy JDK 17 hoặc cấu hình runtime đặc biệt. Việc dựa vào **default charset** vẫn dễ gây sai khác không mong muốn khi chạy nhiều JDK/OS.

Đối với tệp và giao thức do bạn thiết kế, hãy chỉ định **`StandardCharsets.UTF_8` tường minh**. Với dữ liệu dùng định dạng khác theo yêu cầu thực tế, chỉ định charset đó; đừng ép UTF-8 cho tệp đã quy định encoding khác.

### 11.3. BOM, newline và golden files

Một file UTF-8 có **BOM** `EF BB BF` ở đầu và một file UTF-8 không BOM có thể cùng hiển thị nội dung cơ bản, nhưng **bytes khác nhau**. Dùng byte-level assertion khi hợp đồng quy định BOM. Khi đọc bằng parser, phải có chính sách xử lý BOM rõ ràng thay vì giả định Java sẽ luôn loại bỏ nó.

Tương tự, Git và editor có thể chuyển CRLF ↔ LF trong file test, khiến một **golden file** thay đổi trong khi Java logic không đổi. Nên đặt quy tắc newline cho fixtures trong repository, ghi tài liệu encoding và có phép thử byte-exact cho những artifact mà newline là một phần giao thức.

## 12. Viết test JUnit cho ba loại tương thích

Mẫu JUnit Jupiter dưới đây **cần dependency JUnit Jupiter** từ build tool; đây **không phải chương trình Java SE standalone** và không phải code đã được chạy như ví dụ `Main.java`.

```java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import org.junit.jupiter.api.Test;

class StringCompatibilityTest {
    @Test
    void exactTextBlock() {
        String actual = """
                first\s
                second
                """;
        assertEquals("first \nsecond\n", actual);
    }

    @Test
    void exactWireBytes() {
        byte[] actual = "A\r\n".getBytes(StandardCharsets.UTF_8);
        assertArrayEquals(new byte[] {65, 13, 10}, actual);
    }

    @Test
    void allowedEolNormalization() {
        String windows = "x\r\ny\r\n";
        String unix = "x\ny\n";
        assertEquals(unix, normalizeEol(windows));
    }

    static String normalizeEol(String input) {
        return input.replace("\r\n", "\n").replace('\r', '\n');
    }
}
```

Ba test có **ba hợp đồng** khác nhau:

- `exactTextBlock` bắt cả dấu cách cuối dòng và LF cuối text block.
- `exactWireBytes` bắt đúng byte CRLF, không chuẩn hóa.
- `allowedEolNormalization` chỉ áp dụng normalization trong trường hợp chủ động cho phép.

Đối với test có thể bị fail do whitespace, kết hợp `assertEquals` của JUnit với helper báo **vị trí sai và code unit hex**. Một thư viện assertion có so sánh diff trực quan rất hữu ích nhưng không thay thế việc xác định “dấu trắng có mang ý nghĩa hay không”.

### Không thay assertion bằng kiểm tra “contains”

```java
String actual = "done \n";

// Test yếu nếu yêu cầu exact:
assertTrue(actual.contains("done"));

// Test đúng nếu contract yêu cầu không có space cuối:
assertEquals("done\n", actual);
```

Test `contains` sẽ PASS dù có dấu cách dư, ký tự điều khiển hoặc nội dung ngoài mong đợi. Chọn mức kiểm tra đúng với yêu cầu đầu ra.

## 13. Compatibility matrix: chạy ở đâu, so sánh gì?

Đối với một dự án Java chạy trên nhiều môi trường, ma trận tối thiểu tùy sản phẩm có thể gồm:

| Môi trường | Điều cần xác minh |
| --- | --- |
| JDK 17 trên Windows | Text block, UTF-8, file output, đường dẫn và CRLF do ứng dụng tự tạo |
| JDK 17 hoặc 21 trên Linux | Kết quả cùng logic, LF và các file golden đúng contract |
| JDK hiện hành được hỗ trợ trong CI | Không có thay đổi ngoài ý muốn khi nâng JDK |
| macOS (nếu sản phẩm hỗ trợ) | Same Unicode/string behavior, nhưng file/console rendering và locale được kiểm tra |
| Artifact đọc từ mạng/đối tác | Exact charset, byte length, BOM, CRLF và escaping theo protocol |
| Input Unicode nhiều ngôn ngữ | Combining characters, supplementary code points, whitespace đặc biệt |
| File được editor/formatter chạm tới | Trailing spaces, tab, indentation, line ending, final newline |

**Không cần khẳng định mọi JDK sẽ có stdout bằng nhau trong mọi điều kiện**, nhất là nếu code phụ thuộc locale, default charset, timezone hoặc line separator. Thay vào đó, phải cố định các lựa chọn thuộc hợp đồng: charset, locale cần dùng, newline protocol và kiểm tra phiên bản Java thực tế.

Với text blocks, dùng **Java 17+ hoặc bản JDK hiện hành mà project hỗ trợ**. Nếu dự án phải chạy trên Java 14 nguyên bản, syntax text block trong Java 14 là preview nên **không được coi như feature đã chuẩn ở Java 14**. Có thể giữ phần expected bằng Java string literals với `\n`, rồi chạy các phép so sánh tương ứng; không xây mới ứng dụng chỉ phụ thuộc preview cũ.

## 14. Làm sao báo lỗi dễ chẩn đoán mà không làm rối test log?

Với kết quả String lớn, in nguyên hai khối văn bản thường khiến khoảng trắng sai bị mất dấu. Nên tạo báo cáo tập trung:

```text
Case: trailing-space check
Expected UTF-16 length: 6
Actual UTF-16 length:   5
First difference:       index 4
Expected unit:          U+0020
Actual unit:            U+000A
```

Đây là ví dụ báo cáo tự giải thích cho `"item \n"` và `"item\n"`. Hợp đồng test có thể bổ sung **số dòng/column** và hex window quanh vị trí sai để hỗ trợ các chuỗi dài. Nếu cần phân tích một emoji, báo rõ đơn vị index là UTF-16 và có thể bổ sung code point index.

### Đừng rò dữ liệu nhạy cảm trong thông báo assertion

Nếu input chứa mật khẩu, token, số tài khoản, dữ liệu sức khỏe hoặc thông tin người dùng, **không log toàn chuỗi expected/actual**. Hãy log nhãn test, vị trí, loại khác biệt, số lượng ký tự và thông tin đã được che/redact phù hợp. Dù về mặt debug rất hữu ích, byte hex của toàn bộ payload vẫn có thể tiết lộ dữ liệu nhạy cảm.

### Khi nào nên lưu golden file?

Golden file hợp lý khi đầu ra là **artifact định dạng ổn định** như SQL template, JSON text được quy định format, source generator, text-based protocol hoặc tài liệu snapshot. Cần kiểm soát:

- Charset và BOM.
- LF/CRLF/CR đúng theo contract.
- Có/không có newline cuối.
- Trailing spaces/tabs.
- Unicode normalization policy.
- Phiên bản format/schema.
- Cách tool chain hoặc editor thay đổi file.
- Lý do chấp nhận mỗi khi cập nhật golden file.

**Đừng tự động ghi đè snapshot khi test fail**. Trước khi chấp nhận khác biệt, xem liệu đó là thay đổi yêu cầu có chủ đích hay regression bị che giấu.

## 15. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| So sánh bằng mắt ở console | Console có thể hiển thị LF/CRLF, tab, NBSP tương tự nhau | In code unit/code point/byte hex |
| Dùng `trim()`/`strip()` cho mọi assertion | Có thể xóa khoảng trắng quan trọng | So sánh exact trước, chỉ normalize theo contract |
| Xem một `char` là một ký tự Unicode hoàn chỉnh | Supplementary code point gồm hai UTF-16 units | Dùng `codePoints()` khi cần |
| Dùng `String.length()` làm byte length UTF-8 | UTF-8 dùng 1–4 bytes/code point; UTF-16 khác | Mã hóa rồi lấy `byte[].length` |
| Coi Unicode giống hình là `String.equals` | Combining vs precomposed có code units khác | Quy định NFC/NFD nếu phép so sánh cho phép |
| Coi tab tương đương bốn spaces | Tab là U+0009, số space là U+0020 | Test từng ký tự |
| Quên LF cuối text block | Closing delimiter ở dòng mới thường để lại LF | Assert expected có `\n` |
| Quên `\s` ở trailing space text block | Incidental trailing spaces bị compiler strip | Dùng `\s` để bảo toàn space khi có ý nghĩa |
| Di chuyển closing delimiter text block tùy ý | Mức incidental indentation có thể thay đổi | Chạy exact string regression tests |
| Dùng `String.lines()` để kiểm tra raw newline | `lines()` bỏ delimiter và không thêm dòng rỗng cuối | So sánh String/bytes nguyên bản |
| Dùng `indent(0)` như phép biến đổi trung tính | Có thể chuẩn hóa line terminators | Chỉ dùng khi cần normalize |
| Gọi `replace("\r", "\n")` trước `replace("\r\n", "\n")` | Biến CRLF thành hai LF | Chuẩn hóa CRLF trước CR lẻ |
| Dùng `System.lineSeparator()` cho protocol yêu cầu CRLF | Line separator phụ thuộc nền tảng | Dùng `"\r\n"` khi protocol yêu cầu |
| Tưởng text block Java 14 đã là final | Java 14 chỉ có preview; chuẩn từ Java 15 | Dùng JDK 17+ stable syntax |
| Dựa vào default charset trong file tests | Có thể khác giữa JDK/OS/config | Chỉ định `UTF_8` hoặc encoding quy định |
| Chỉ test chuỗi sau khi decode file | Bytes khác vẫn có thể tạo text được chấp nhận | Thêm byte-level assertion nếu cần |
| Dùng `contains` thay exact comparison | Bỏ lọt ký tự thừa/trailing newline | Dùng `assertEquals` hoặc helper exact |
| Xóa mọi whitespace để “fix” test | Có thể làm sai thông điệp/format | Xác định contract rồi điều chỉnh nguồn |

## 16. Bài tập thực hành

**Bài 1.** Một text block ghi:

```java
String value = """
        x
        """;
```

`value.equals("x")` hay `value.equals("x\n")` là đúng?

**Đáp án:** `value.equals("x\n")`, vì dấu đóng nằm ở dòng sau nội dung, nên chuỗi có LF cuối. Để không có LF cuối, dùng cách đặt dấu đóng thích hợp hoặc chủ động chỉnh source theo contract rồi test exact.

**Bài 2.** Một file test được lưu CRLF trên Windows và LF trên Linux. Trong trường hợp nào có thể normalize?

**Đáp án:** Khi yêu cầu cho phép cùng nội dung logic của dòng bất kể terminator. Nếu file là wire protocol hoặc định dạng byte yêu cầu CRLF, **không normalize** khi xác minh bytes.

**Bài 3.** `"a\tb"` và `"a    b"` có thể coi là bằng nhau vì editor hiển thị cùng khoảng cách không?

**Đáp án:** Không theo String equality. Muốn coi tương đương phải có một quy tắc tab expansion cụ thể; đối với TSV và dữ liệu có cấu trúc, hai chuỗi thường **khác format**.

**Bài 4.** Vì sao test của `"x\n".lines().count()` ra `1`, không phải `2`?

**Đáp án:** `lines()` trả dòng đã bỏ terminator; API không tạo một dòng rỗng mới sau terminator cuối.

**Bài 5.** Hai chuỗi `"e\u0301"` và `"\u00E9"` có `equals` trả true không? Khi nào có thể coi chúng tương đương?

**Đáp án:** `equals` trả false vì dãy code units khác nhau. Có thể coi tương đương nếu đặc tả quy định normalization (ví dụ NFC) và ứng dụng áp dụng cùng chính sách trước so sánh.

**Bài 6.** Khi xuất file UTF-8, phép thử `Files.readString(file, UTF_8).equals(expected)` đã đủ để chứng minh byte-level compatibility chưa?

**Đáp án:** Chưa chắc. Nếu có hợp đồng về BOM, byte order, newline bytes hoặc format nhị phân, phải kiểm tra `Files.readAllBytes(file)` với expected bytes.

**Bài 7.** Mismatch đầu tiên của `"item \n"` so với `"item\n"` là gì?

**Đáp án:** Tại UTF-16 index `4`, expected `U+0020` (space) và actual `U+000A` (LF). Độ dài lần lượt là `6` và `5`.

**Bài 8.** Muốn duy trì mã chạy Java 17+ nhưng vẫn đặt tên module “Java 14”, có nên viết sample bật preview flag của Java 14 không?

**Đáp án:** Không. Bài giữ kiến thức được giới thiệu trong giai đoạn Java 14 và cách dùng **đang chuẩn hóa/đang được hỗ trợ hiện nay**. Với text blocks hãy dùng cú pháp final từ Java 15 trên JDK 17+; không hướng dẫn preview flag cũ như cách phát triển mới.

## 17. Checklist kiểm thử chuỗi tương thích

1. **Đầu ra phải bằng nhau ở tầng nào:** UTF-16 units, Unicode code points, text sau normalization hay byte payload?
2. **Newline có quan trọng không:** LF, CRLF, CR, thiếu/newline cuối?
3. **Khoảng trắng có ý nghĩa không:** space, tab, trailing spaces, indentation, blank lines, NBSP?
4. **Text block có thay đổi giá trị khi chỉnh thụt dòng/dấu đóng không?**
5. **Có dùng `\s` hoặc line continuation `\` đúng mục đích không?**
6. **Chương trình có dùng `strip/trim/stripIndent/indent/lines` trước test và làm mất dữ liệu cần so sánh không?**
7. **Unicode normalization nào được yêu cầu, nếu có?**
8. **Đã phân biệt code unit/code point/grapheme/UTF-8 byte chưa?**
9. **File/test fixture có charset, BOM và line endings cố định chưa?**
10. **Test có báo code point/code unit hex tại vị trí sai đầu tiên không?**
11. **Có chạy trên các JDK/OS thực sự được sản phẩm hỗ trợ không?**
12. **Có bảo vệ dữ liệu nhạy cảm trong test logs không?**
13. **Những quy tắc “bỏ qua khác biệt” có được viết rõ từ đặc tả, thay vì chỉ để làm test PASS không?**

**Kết luận:** Kiểm thử chuỗi tương thích không đơn giản là xem “hai đoạn văn có giống nhau trên màn hình không”. Trong Java, `String.equals` kiểm tra nội dung UTF-16 thực tế; CR/LF, tab, space, khoảng trắng cuối dòng và Unicode normalization có thể thay đổi kết quả. **Text blocks đã chuẩn từ Java 15**, có quy tắc LF và incidental whitespace riêng. Hãy dùng **exact comparison** làm điểm xuất phát, chuẩn hóa **chỉ khi hợp đồng cho phép**, và kiểm tra **bytes** khi sản phẩm yêu cầu định dạng tệp/giao thức chính xác.

### Tài liệu tham khảo chính thức còn áp dụng

- [JEP 378 — Text Blocks (chuẩn từ Java 15)](https://openjdk.org/jeps/378).
- [Oracle — Programmer's Guide to Text Blocks](https://docs.oracle.com/en/java/javase/15/text-blocks/index.html).
- [Java SE 21 — String: length, lines, stripIndent, indent, codePoints](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html).
- [Java SE 21 — Character và Unicode code points](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html).
- [Java SE 21 — Normalizer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/Normalizer.html).
- [Java SE 21 — Files.writeString/readString/readAllBytes](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html).
- [JEP 400 — UTF-8 by Default từ Java 18](https://openjdk.org/jeps/400).
- [Java Language Specification — Lexical Structure, Unicode Escapes and String/Text Block Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html).
