# Kiểm thử text block trong Java: căn lề, tab, dấu nháy và dòng cuối

**Phạm vi:** Java 15 trở lên, trong đó text block (`"""`) đã là tính năng chính thức theo JEP 378. Text block tiếp tục được hỗ trợ trong các phiên bản Java hiện hành. Bài học tập trung vào cách xác định **giá trị thật của `String`** và viết phép kiểm thử bắt chính xác lỗi lệch căn lề, tab, dấu nháy, khoảng trắng và ký tự xuống dòng cuối.

Một text block không phải kiểu chuỗi mới: kết quả là `java.lang.String`. Vì vậy phép so sánh đáng tin cậy nhất cho nội dung cố định thường là `assertEquals(expected, actual)` (JUnit) hoặc `expected.equals(actual)` (Java thuần), với **expected được viết rõ ràng**.

## 1. Cách Java biến text block thành chuỗi

Text block bắt đầu bằng ba dấu nháy kép `"""`, có thể theo sau là khoảng trắng và **bắt buộc có xuống dòng** trước ký tự nội dung đầu tiên. Ví dụ hợp lệ:

```java
String value = """
    first
    second
    """;
```

Giá trị thực tế ở đây là `"first\nsecond\n"`. Dấu xuống dòng ngay sau `"""` **mở** không tạo một dòng rỗng đầu chuỗi. Nhưng khi dấu `"""` **đóng** đứng ở dòng riêng sau `second`, dòng `second` có ký tự xuống dòng `\n` ở cuối chuỗi.

Java thực hiện theo thứ tự:

1. **Chuẩn hóa xuống dòng:** các dạng xuống dòng của tệp nguồn CRLF và CR trong text block được chuẩn hóa thành LF (`\n`) trong chuỗi.
2. **Loại khoảng trắng ngẫu nhiên:** phần căn lề chung ở đầu dòng (incidental indentation) và khoảng trắng dư ở cuối mỗi dòng được loại theo quy tắc text block.
3. **Giải mã escape sequence:** ví dụ `\t` thành tab thật, `\s` thành một space và `\` ngay trước xuống dòng thành nối dòng không có ký tự LF.

Thứ tự này quyết định vì sao `\s` có thể giữ lại space cuối dòng và `\t` cho tab có chủ ý, trong khi khoảng trắng vô hình gõ trực tiếp ở cuối dòng có thể biến mất.

### Sai ngay từ cú pháp mở

```java
// KHÔNG hợp lệ: thiếu xuống dòng ngay sau dấu mở.
// String bad = """hello""";

// Hợp lệ:
String good = """
    hello"""; // giá trị "hello", không có LF cuối
```

Đây là tính năng Java ổn định từ phiên bản 15, không cần `--enable-preview` trong các JDK hỗ trợ Java 15 trở lên.

## 2. Kiểm thử căn lề: khoảng trắng nào được giữ?

Với cách viết thông dụng, compiler loại số ký tự whitespace chung ở bên trái theo dòng có mức thụt đầu nhỏ nhất và vị trí dấu `"""` đóng; các khoảng trắng **nhiều hơn mức chung** sẽ là một phần của chuỗi.

```java
String result = """
        alpha
          beta
        """;
```

Giá trị mong đợi:

```text
alpha
  beta
```

Biểu diễn chính xác trong Java là `"alpha\n  beta\n"`. Hai space trước `beta` là dữ liệu **cố ý**; tám space đầu mỗi dòng và của dấu đóng là cách căn lề mã nguồn.

### Di chuyển dấu đóng có thể đổi dữ liệu

```java
String retained = """
            left
              right
        """;
```

Kết quả chính xác: `"    left\n      right\n"`. Vì dấu đóng nằm bên trái các dòng nội dung 4 space, bốn space đầu nội dung **được giữ lại**.

Đừng nghĩ text block tự động luôn “xóa mọi space đầu dòng”. Nếu đang test chuỗi SQL, JSON, HTML hay văn bản có cấu trúc, đổi vị trí dấu `"""` đóng có thể làm thay đổi chuỗi thực tế. Kiểm thử bằng exact string khi chính xác khoảng trắng là một phần của hợp đồng dữ liệu.

### Tab căn lề không tương đương nhiều space

Compiler xử lý tab ở phần căn lề như **một ký tự whitespace**, không tính theo cột hiển thị 4 hay 8 space của IDE. Trộn tab thật với space thật trong căn lề mã nguồn dễ tạo chuỗi trông thẳng hàng trong editor nhưng khi chạy lại lệch.

Quy ước nên dùng:

- Giữ căn lề của text block nhất quán: chỉ space hoặc chỉ tab, tránh trộn.
- Khi **giá trị chuỗi cần có tab thật**, dùng escape `\t` ở vị trí dữ liệu thay vì phụ thuộc ký tự tab vô hình trong nguồn.
- Với payload yêu cầu số space cụ thể, biểu diễn expected bằng chuỗi truyền thống có space rõ ràng hoặc kiểm tra mã ký tự.

## 3. Kiểm thử tab: tab thật khác bốn dấu cách

```java
String row = """
    id\tvalue
    """;
```

Giá trị thực: `"id\tvalue\n"`, trong đó `\t` là **một ký tự U+0009**. Nó không biến thành bốn khoảng trắng, dù IDE/terminal có thể hiển thị nó như một vùng rộng. Cũng cần phân biệt:

| Nội dung cần kiểm tra | Biểu diễn expected trong Java | Ý nghĩa |
| --- | --- | --- |
| Một tab | `"a\tb"` | U+0009 nằm giữa `a` và `b` |
| Bốn space | `"a    b"` | Bốn ký tự U+0020 |
| Hai ký tự backslash rồi `t` | `"a\\tb"` | Dữ liệu là `\` và `t`, không có tab |
| Tab kèm LF cuối | `"a\tb\n"` | Tab ở giữa, LF cuối chuỗi |

Cả `System.out.print` lẫn ảnh chụp terminal đều **không đủ** để chứng minh hai chuỗi bằng nhau. Dùng `equals`/`assertEquals` hoặc so mã ký tự: `row.charAt(2) == '\t'` trong ví dụ `"id\tvalue\n"` (chỉ số 2 là tab).

Nếu text block chứa tab gõ trực tiếp trong tệp nguồn, tab có thể là dữ liệu hợp lệ, nhưng trong kiểm thử nên chủ động dùng `\t` để reviewer nhìn được ý định và editor không tự đổi khoảng trắng.

## 4. Kiểm thử dấu nháy: một, hai và ba dấu nháy kép

Trong nội dung text block, dấu nháy kép đơn hoặc đôi thường viết trực tiếp:

```java
String quote = """
    She said "yes".
    """;
```

Giá trị mong đợi: `"She said \"yes\".\n"`. Dấu `"` trong text block không buộc phải escape, còn `\"` trong **string literal thường** của expected là cú pháp Java để biểu diễn cùng ký tự nháy.

Khi nội dung cần **ba dấu nháy kép liên tiếp**, chúng có thể bị hiểu là dấu đóng text block. Escape dấu nháy kép đầu tiên trong cụm ba dấu:

```java
String tripleQuotes = """
    Here: \"""
    """;
```

Giá trị của ví dụ trên: `"Here: \"\"\"\n"`. Backslash trong `\"""` chỉ là một phần của **cú pháp nguồn** và không nằm trong chuỗi kết quả.

Các lưu ý quan trọng:

- Nếu bạn muốn kiểm tra dấu nháy kép thực tế, so sánh với ký tự `"`; đừng thêm backslash vào expected ở **runtime** chỉ vì nó xuất hiện trong mã nguồn.
- Dấu nháy đơn `'` không yêu cầu escape trong text block.
- Nếu chuỗi chứa mã Java, JSON hay shell, cần phân biệt quy tắc escape của **Java text block** với quy tắc escape của định dạng nằm bên trong; một backslash muốn tồn tại trong kết quả thường phải viết `\\` trong nguồn Java.
- Không chuẩn hóa/xóa dấu nháy trước khi assert; như vậy phép kiểm thử sẽ bỏ sót lỗi payload.

## 5. Dòng cuối: có `\n` hay không?

Đây là lỗi phổ biến nhất khi so sánh text block với expected hoặc snapshot.

### 5.1. Dấu đóng ở dòng riêng: thường có newline cuối

```java
String withFinalNewline = """
    one
    two
    """;
```

Expected chính xác: `"one\ntwo\n"`.

### 5.2. Dấu đóng ngay sau ký tự cuối: không có newline cuối

```java
String withoutFinalNewline = """
    one
    two""";
```

Expected chính xác: `"one\ntwo"`.

Hai giá trị nhìn gần như giống nhau khi in ra console, nhưng `withFinalNewline.equals(withoutFinalNewline)` trả về `false`. `withFinalNewline.endsWith("\n")` là `true`, còn `withoutFinalNewline.endsWith("\n")` là `false`.

### 5.3. Nối dòng bằng backslash ở cuối dòng nguồn

```java
String joined = """
    join\
    ed\
    """;
```

Expected chính xác: `"joined"`. Escape **backslash ngay trước line terminator** xóa line terminator ấy khỏi chuỗi; nó khác `\\` (tạo một backslash thật) và khác `\n` (tạo LF thật). Tránh đặt space hoặc ký tự khác sau dấu `\` được dùng để nối dòng.

### 5.4. Text block rỗng có độ dài bằng 0

```java
String empty = """
    """;
```

Expected: `""`; không phải `"\n"`. Điều này minh họa rằng newline bắt buộc sau dấu mở không tự tạo dòng rỗng nếu không có nội dung.

### 5.5. Xuống dòng chuẩn hóa là LF

Nếu mã nguồn được lưu với line ending Windows CRLF, giá trị text block bình thường vẫn có LF (`\n`), **không phải** CRLF (`\r\n`). Không dựng expected theo `System.lineSeparator()` nếu hợp đồng dữ liệu là text block nguyên bản. Chỉ chuyển LF sang line ending hệ điều hành khi đầu ra thực sự đòi hỏi điều đó.

`System.out.println(value)` còn tự thêm một line terminator vào luồng in, nên đếm dòng trên màn hình không phải cách tốt để kiểm tra ký tự cuối của `value`. Hãy kiểm tra `endsWith("\n")`, `length()` hoặc so sánh nguyên chuỗi.

## 6. Khoảng trắng cuối dòng và `\s`

Khoảng trắng gõ trực tiếp ở **cuối một dòng** của text block thường bị Java loại trong bước xử lý incidental whitespace. Nếu ứng dụng cần một space cuối dòng thực sự, dùng escape `\s` (có từ Java 15) vì escape được giải mã sau bước loại whitespace.

```java
String withSpace = """
    end\s
    """;
```

Giá trị mong đợi: `"end \n"`, gồm ba chữ `end`, **một space**, rồi **một LF**. Độ dài là 5 ký tự. Nếu expected là `"end\n"` (độ dài 4), phép kiểm thử phải FAIL.

Cũng có thể sử dụng `\040` (octal escape biểu diễn space), nhưng `\s` đọc dễ hiểu hơn trong Java hiện hành. Không dùng `\u0020` với mục tiêu giữ space cuối dòng: Unicode escape được xử lý rất sớm trong pipeline đọc mã nguồn, trước khi text block loại trailing whitespace.

Với văn bản snapshot quan trọng, nên chủ động thử riêng: không space cuối dòng, có một space cuối dòng, có tab cuối dòng, có và không LF cuối. Đừng dùng `trim()` hoặc `strip()` vào cả actual và expected để “làm hết lỗi”; chúng làm mất chính những khác biệt cần kiểm tra.

## 7. Chương trình kiểm thử độc lập, chạy được với Java 17+

Tạo tệp **`TextBlockChecks.java`** với toàn bộ mã dưới đây. Không cần thư viện bên ngoài; phương thức `check` ném `AssertionError` khi sai nên luôn kiểm tra kể cả không bật cờ `-ea`. Nội dung giữ nguyên các vị trí dấu `"""` vì chúng có ảnh hưởng đến giá trị chuỗi.

```java
public class TextBlockChecks {
    private static int total = 0;

    private static void check(String name, String actual, String expected) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + " mismatch");
        }
        total++;
        System.out.println("PASS " + name);
    }

    public static void main(String[] args) {
        String indentation = """
                red
                  blue
                """;
        check("indentation", indentation, "red\n  blue\n");

        String retained = """
                    left
                      right
                """;
        check("retained-indent", retained, "    left\n      right\n");

        String tab = """
                id\tvalue
                """;
        check("tab", tab, "id\tvalue\n");

        String quotes = """
                She said "yes".
                """;
        check("quotes", quotes, "She said \"yes\".\n");

        String tripleQuotes = """
                Here: \"""
                """;
        check("triple-quotes", tripleQuotes, "Here: \"\"\"\n");

        String withFinal = """
                one
                two
                """;
        check("final-newline", withFinal, "one\ntwo\n");

        String withoutFinal = """
                one
                two""";
        check("no-final-newline", withoutFinal, "one\ntwo");

        String withSpace = """
                end\s
                """;
        check("trailing-space", withSpace, "end \n");

        String joined = """
                join\
                ed\
                """;
        check("line-continuation", joined, "joined");

        String empty = """
                """;
        check("empty", empty, "");

        System.out.println("All " + total + " checks passed.");
    }
}
```

Chạy từ thư mục chứa tệp bằng JDK 17+:

```bash
javac -encoding UTF-8 TextBlockChecks.java
java TextBlockChecks
```

Đầu ra chính xác khi tất cả phép thử thành công:

```text
PASS indentation
PASS retained-indent
PASS tab
PASS quotes
PASS triple-quotes
PASS final-newline
PASS no-final-newline
PASS trailing-space
PASS line-continuation
PASS empty
All 10 checks passed.
```

Nếu lỗi xuất hiện ở một `check`, chương trình ném `AssertionError` và không in dòng tổng kết. Trong thực tế, để debug lỗi khoảng trắng, nên xây dựng hàm hiển thị ký tự đặc biệt dưới dạng `\n`, `\r`, `\t` và U+0020 hoặc in mã code point tại vị trí sai; chỉ in chuỗi thông thường có thể che giấu khác biệt. Cách kiểm thử đơn giản trên sử dụng `expected.equals(actual)` để khẳng định **toàn bộ nội dung và độ dài**, không chỉ một đoạn con.

## 8. Viết test JUnit Jupiter trong dự án có sẵn JUnit

Khi dự án đã dùng JUnit Jupiter (package `org.junit.jupiter.api`), có thể viết test ngắn hơn. Đoạn sau là **một lớp test cần dependency JUnit Jupiter của dự án**, không phải chương trình độc lập để biên dịch bằng `javac` không kèm thư viện.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class TextBlockJUnitTest {
    @Test
    void retainsOnlyIntentionalIndentation() {
        String actual = """
                a
                  b
                """;
        assertEquals("a\n  b\n", actual);
    }

    @Test
    void recognizesTabAndQuotes() {
        String actual = """
                "id"\t"score"
                """;
        assertEquals("\"id\"\t\"score\"\n", actual);
    }

    @Test
    void distinguishesFinalNewline() {
        String withFinal = """
                x
                """;
        String withoutFinal = """
                x""";
        assertEquals("x\n", withFinal);
        assertEquals("x", withoutFinal);
        assertTrue(withFinal.endsWith("\n"));
        assertFalse(withoutFinal.endsWith("\n"));
    }
}
```

Điểm quan trọng trong `assertEquals(expected, actual)`: **expected độc lập** với phép tạo actual. Nếu lấy `actual.strip()` làm expected, hoặc gọi `stripIndent()` lên cả hai vế cho “dễ pass”, test không còn bắt được lỗi căn lề/dòng cuối. Chỉ chuẩn hóa khi yêu cầu của nghiệp vụ **cho phép** bỏ qua khác biệt đó.

## 9. Một bảng đối chiếu nhanh khi review

| Nguồn Java | Giá trị thực tế (biểu diễn escaped) | Điều cần assert |
| --- | --- | --- |
| Text block có hai dòng nội dung, dấu đóng dòng riêng | `"a\nb\n"` | Có LF cuối |
| Text block có hai dòng, dấu đóng cùng dòng với `b` | `"a\nb"` | Không LF cuối |
| `a\tb` bên trong text block | `"a\tb"` | Một ký tự tab thật |
| `a\s` ngay trước LF | `"a \n"` | Space cuối dòng vẫn còn |
| Một dấu `"` giữa nội dung | `"\""` | Không có backslash ở dữ liệu |
| Cụm ba dấu nháy viết `\"""` trong text block | `"\"\"\""` | Ba dấu nháy thật |
| Backslash tiếp ngay LF nguồn | Hai dòng được nối liền | Không có LF ở chỗ nối |

Ghi chú: bảng dùng một số **mảnh cú pháp** thay vì những chương trình chạy độc lập; ví dụ đầy đủ và output kiểm thử đã có ở phần 7.

## 10. Các lỗi thường gặp khi kiểm thử và cách sửa

1. **Mong đợi sai newline cuối:** test viết `"hello"` nhưng actual là `"hello\n"`. Sửa expected theo hợp đồng, hoặc đặt dấu đóng ngay sau `hello` / dùng nối dòng nếu đầu ra cần không có LF.
2. **Di chuyển dấu đóng làm đổi căn lề:** snapshot thay đổi dù không sửa chữ. Kiểm tra cột dấu đóng và phần indent tối thiểu; khóa cách căn lề theo quy ước dự án.
3. **Trộn TAB và space ở source:** editor hiển thị thẳng hàng nhưng actual vẫn khác. Dùng một kiểu indent cho mã và `\t` khi muốn tab là dữ liệu.
4. **Đánh đồng TAB với nhiều space:** chuỗi trông tương tự, nhưng `equals` FAIL. So bằng đúng `\t` hoặc mã U+0009.
5. **Thấy dấu nháy trong test rồi thêm escape thừa:** `\"` trong string literal expected chỉ mô tả dấu nháy, không phải thêm ký tự `\` vào payload. Phân biệt cú pháp Java với dữ liệu thực.
6. **Ghi ba dấu nháy trực tiếp bên trong text block:** có thể kết thúc block sớm. Dùng `\"""` để bảo toàn nội dung mong muốn.
7. **Cố giữ trailing space bằng phím space:** compiler có thể bỏ. Dùng `\s` và assert chính xác `" \n"`.
8. **Dùng `trim()`/`strip()` trước assert:** xóa luôn lỗi cần phát hiện. So exact trước; nếu hợp đồng cho phép bỏ whitespace mới chuẩn hóa có chủ đích.
9. **Kiểm tra bằng `println`:** console không thể hiện rõ tab, space cuối và LF cuối; `println` còn tự thêm newline. Dùng `equals`, `length`, `endsWith` và diagnostic nhìn thấy ký tự ẩn.
10. **Dùng `String.lines()` để đếm LF cuối:** `lines()` trả nội dung theo dòng và không giữ ký tự line terminator, nên không thích hợp để chứng minh một chuỗi kết thúc bằng LF. Kiểm tra `endsWith("\n")` trực tiếp.

## 11. Checklist cho test của text block

- Nắm rõ expected theo **ký tự thực**, đặc biệt `\n`, `\t`, `\r`, space.
- Với căn lề, test cả mức indent chung bị bỏ và mức indent cố ý còn lại.
- Với dấu nháy, test nội dung có `"` và trường hợp ba dấu nháy liên tiếp nếu cần.
- Với dòng cuối, test cả có `\n` và không có `\n`; không dựa vào console.
- Với trailing whitespace, xác nhận space được giữ bởi `\s` nếu đó là yêu cầu.
- Dùng phép so sánh nguyên chuỗi, tránh chuẩn hóa âm thầm.
- Chạy test sau khi IDE auto-format hoặc sửa vị trí dấu đóng vì định dạng nguồn có thể ảnh hưởng đến giá trị text block.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao đoạn `String x = """` (xuống dòng) `hi` (xuống dòng) `""";` thường tạo chuỗi kết thúc bằng `\n`?  
**Đáp án:** Dòng nội dung `hi` thực sự kết thúc bởi LF trước dấu đóng trên dòng riêng; LF được giữ trong chuỗi.

**Câu 2.** Vì sao hai giá trị `"a\tb"` và `"a    b"` khác nhau khi assert, dù hiển thị trông tương tự?  
**Đáp án:** Bên đầu có một ký tự tab (U+0009), bên sau có bốn ký tự space (U+0020).

**Câu 3.** Vị trí dấu đóng có ảnh hưởng gì đến căn lề?  
**Đáp án:** Nó tham gia vào việc xác định incidental indentation. Dấu đóng đặt lệch sang trái có thể khiến một phần space đầu nội dung được giữ.

**Câu 4.** Dùng cách nào để giữ đúng một space cuối dòng khi so sánh text block?  
**Đáp án:** Dùng `\s` trước line terminator và assert expected chứa `" \n"` ở đoạn tương ứng.

**Câu 5.** Khi cần chuỗi chứa ba dấu nháy kép liên tiếp, nên viết thế nào trong text block?  
**Đáp án:** Escape dấu nháy kép đầu tiên của cụm ba dấu, ví dụ `\"""`, để tránh kết thúc block sớm.

## Tài liệu chính thức

- [Oracle — Programmer's Guide to Text Blocks, Java 25](https://docs.oracle.com/en/java/javase/25/text-blocks/index.html): cú pháp, căn lề, trailing spaces, tab, dấu nháy, xuống dòng cuối, escape và hướng dẫn trình bày.
- [Java SE 26 — Text Blocks](https://docs.oracle.com/en/java/javase/26/language/text-blocks.html): diễn giải cập nhật cho các quy tắc vẫn được áp dụng trong Java hiện hành.
- [Java Language Specification, `3.10.6 Text Blocks (SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): thứ tự chuẩn hóa newline, strip indentation, xử lý escape.
- [Oracle — Java 15 Text Blocks](https://docs.oracle.com/en/java/javase/15/text-blocks/index.html): xác nhận text block là tính năng chính thức từ Java 15.
