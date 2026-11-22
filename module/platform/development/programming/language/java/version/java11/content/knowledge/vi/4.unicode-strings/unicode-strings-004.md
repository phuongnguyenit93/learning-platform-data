# Character.isWhitespace và dữ liệu cần kiểm thử (Java 11+)

**Chủ đề cha: Chuỗi Unicode.** Bài này giải thích chính xác Java nhận diện *whitespace* theo mã điểm Unicode (*code point*) nào, các trường hợp dễ nhầm với khoảng trắng không ngắt dòng và ký tự vô hình, cùng cách thiết kế dữ liệu kiểm thử cho `Character.isWhitespace`, `String.isBlank`, `String.strip`. Mọi ví dụ Java bên dưới tương thích JDK 11 trở lên; các tiêu chí phân loại được đối chiếu với API Java chính thức.

## 1. Whitespace trong Java là một quy tắc cụ thể

Ký tự trông như khoảng trắng trên màn hình **không nhất thiết** được `Character.isWhitespace` xem là whitespace. API có hai overload:

```java
Character.isWhitespace(char ch);
Character.isWhitespace(int codePoint);
```

- `char` là **một đơn vị mã UTF-16**, không nhất thiết là một ký tự Unicode hoàn chỉnh. Overload `char` không xử lý một code point ngoài BMP (U+10000 trở lên) như một đơn vị.
- `int codePoint` là lựa chọn tổng quát khi xử lý văn bản Unicode. Kết hợp với `String.codePoints()`, `codePointAt()` hoặc `Character.charCount()` khi cần duyệt đúng code point.
- Cả hai trả về `boolean`; không thực hiện thao tác xóa, thay thế hoặc chuẩn hóa chuỗi.

Theo hợp đồng `Character.isWhitespace(int)`, kết quả `true` khi mã điểm là:

1. Một ký tự Unicode thuộc loại `SPACE_SEPARATOR`, `LINE_SEPARATOR` hoặc `PARAGRAPH_SEPARATOR`, **trừ** ba non-breaking spaces U+00A0, U+2007, U+202F.
2. Một trong các control characters U+0009 (TAB), U+000A (LF), U+000B (vertical tab), U+000C (form feed), U+000D (CR).
3. Một trong U+001C, U+001D, U+001E, U+001F (các separator controls).

Ba non-breaking spaces không bị loại khỏi Unicode, mà là **ngoại lệ có chủ đích của định nghĩa Java whitespace**. Quy tắc này vẫn đúng trong các phiên bản Java hiện đại.

### So sánh `isWhitespace` và `isSpaceChar`

`Character.isSpaceChar(int)` trả về `true` cho các Unicode general categories `SPACE_SEPARATOR`, `LINE_SEPARATOR`, `PARAGRAPH_SEPARATOR`. Nó **có** nhận ba non-breaking spaces nói trên, nhưng **không** nhận TAB, LF, CR hoặc các separator controls thông thường. Vì thế hai hàm không thể thay thế cho nhau.

**Đừng đồng nhất** ba khái niệm: Java `Character.isWhitespace`; `Character.isSpaceChar` (các nhóm Unicode space/line/paragraph separator); và thuộc tính Unicode `White_Space` dùng trong một số thư viện/regex. Chúng có điểm giao nhau nhưng không tương đương.

## 2. Bảng code point cần có trong bộ kiểm thử

Tên Unicode và mã `U+....` giúp tạo dữ liệu rõ ràng hơn cách nhập ký tự vô hình trực tiếp vào bài test.

| Code point | Ý nghĩa | `isWhitespace` | `isSpaceChar` | Lý do nên thử |
| --- | --- | :---: | :---: | --- |
| U+0009 | HORIZONTAL TAB | true | false | Khoảng trắng dạng điều khiển |
| U+000A | LINE FEED (LF) | true | false | Xuống dòng Unix |
| U+001C | FILE SEPARATOR | true | false | Ngoại lệ điều khiển riêng của Java |
| U+0020 | SPACE | true | true | Trường hợp chuẩn ASCII |
| U+0085 | NEXT LINE (NEL) | false | false | Có thể được hiểu là whitespace trong quy ước khác |
| U+00A0 | NO-BREAK SPACE (NBSP) | false | true | Hay xuất hiện khi copy từ HTML |
| U+1680 | OGHAM SPACE MARK | true | true | Ký tự Unicode space khác ASCII |
| U+2003 | EM SPACE | true | true | Thử whitespace Unicode ngoài U+0020 |
| U+2007 | FIGURE SPACE | false | true | Một non-breaking space khác |
| U+200B | ZERO WIDTH SPACE | false | false | Vô hình nhưng không thuộc Java whitespace |
| U+2028 | LINE SEPARATOR | true | true | Phân tách dòng Unicode |
| U+2029 | PARAGRAPH SEPARATOR | true | true | Phân tách đoạn Unicode |
| U+202F | NARROW NO-BREAK SPACE | false | true | Non-breaking space hẹp |
| U+3000 | IDEOGRAPHIC SPACE | true | true | Khoảng trắng thường gặp trong dữ liệu CJK |
| U+FEFF | ZERO WIDTH NO-BREAK SPACE/BOM | false | false | Có thể xuất hiện ở đầu dữ liệu khi xử lý encoding |
| U+1F600 | GRINNING FACE | false | false | Code point ngoài BMP: kiểm tra duyệt UTF-16 đúng cách |

Trong bảng, `true` và `false` là kết quả mong đợi của Java 11 đối với **từng code point**, không phải kết quả hiển thị trên font hay trình duyệt. Bộ kiểm thử nên giữ nguyên mã điểm dưới dạng số như `0x00A0` để tránh biên tập viên tự thay thế khoảng trắng.

Lưu ý: U+200B (*zero width space*) và U+FEFF (*BOM/zero width no-break space*) không tự được `isWhitespace` nhận diện. Nếu dữ liệu có các ký tự này, cần quyết định chính sách làm sạch riêng, không gộp tùy tiện vào khoảng trắng chuẩn.

## 3. Liên hệ với `String` trong Java 11

Java 11 cung cấp các API xử lý chuỗi sử dụng cùng định nghĩa whitespace của `Character.isWhitespace(int)`:

- `text.isBlank()`: `true` nếu chuỗi **rỗng** hoặc mọi code point trong chuỗi đều là Java whitespace.
- `text.strip()`: loại bỏ các Java whitespace ở **hai đầu** chuỗi; giữ nguyên ký tự ở giữa.
- `text.stripLeading()` / `text.stripTrailing()`: chỉ xử lý đầu trái/đầu phải tương ứng.
- `text.trim()`: vẫn là API hợp lệ, nhưng dùng tiêu chí riêng: loại bỏ các ký tự có giá trị UTF-16 `<= U+0020` ở hai đầu, nên không tương đương với `strip()` khi gặp Unicode whitespace như U+2003.
- `text.isEmpty()`: chỉ kiểm tra độ dài chuỗi bằng 0, không có nghĩa giống `isBlank()`.

Đặc biệt, chuỗi chỉ chứa NBSP `"\u00A0"`: `isBlank()` là `false` và `strip()` giữ lại NBSP, vì `Character.isWhitespace(0x00A0)` là `false`. Hành vi này đúng theo API, không phải lỗi của `strip`.

### Ví dụ chạy độc lập: `WhitespaceBehaviorDemo.java`

```java
public class WhitespaceBehaviorDemo {
    public static void main(String[] args) {
        String emSpace = "\u2003";
        String nbsp = "\u00A0";
        String padded = emSpace + "Java" + emSpace;

        System.out.println("EM SPACE whitespace: "
                + Character.isWhitespace(0x2003));
        System.out.println("NBSP whitespace: "
                + Character.isWhitespace(0x00A0));
        System.out.println("NBSP spaceChar: "
                + Character.isSpaceChar(0x00A0));

        System.out.println("empty isBlank: " + "".isBlank());
        System.out.println("mixed isBlank: " + ("\t" + emSpace).isBlank());
        System.out.println("NBSP isBlank: " + nbsp.isBlank());

        System.out.println("strip EM SPACE: " + padded.strip().equals("Java"));
        System.out.println("trim EM SPACE: " + padded.trim().equals("Java"));
        System.out.println("strip NBSP length: " + nbsp.strip().length());

        System.out.println("internal preserved: "
                + ("A" + emSpace + "B").strip().equals("A" + emSpace + "B"));
    }
}
```

Biên dịch/chạy bằng JDK 11 trở lên:

```bash
javac --release 11 -encoding UTF-8 WhitespaceBehaviorDemo.java
java WhitespaceBehaviorDemo
```

Stdout:

```text
EM SPACE whitespace: true
NBSP whitespace: false
NBSP spaceChar: true
empty isBlank: true
mixed isBlank: true
NBSP isBlank: false
strip EM SPACE: true
trim EM SPACE: false
strip NBSP length: 1
internal preserved: true
```

Ví dụ cho thấy `strip()` phù hợp khi hợp đồng xử lý dữ liệu là “loại Java whitespace ở hai đầu”; nó không tự biến NBSP thành SPACE, cũng không xóa EM SPACE ở giữa một chuỗi có nội dung.

## 4. Bộ regression test có thể chạy bằng Java thuần

Đừng dùng mắt để xác nhận test: khoảng trắng có thể trông giống hệt nhau. Hãy kiểm tra **giá trị số của code point**, cả kết quả phân loại và hành vi cấp chuỗi.

Ví dụ sau dùng các phép kiểm tra tự ném `AssertionError`, vì Java `assert` có thể bị vô hiệu hóa nếu JVM không được chạy với `-ea`. Không cần thư viện test ngoài nên có thể chạy ngay với JDK 11.

### `WhitespaceRegressionTest.java`

```java
public final class WhitespaceRegressionTest {
    private static int checks = 0;

    private static void expect(boolean expected, boolean actual, String label) {
        checks++;
        if (expected != actual) {
            throw new AssertionError(label
                    + ": expected=" + expected + ", actual=" + actual);
        }
    }

    private static String describe(String text) {
        StringBuilder result = new StringBuilder();
        text.codePoints().forEach(cp -> {
            if (result.length() > 0) {
                result.append(' ');
            }
            result.append(String.format("U+%04X", cp));
        });
        return result.toString();
    }

    private static void checkCodePoint(int cp, boolean white, boolean space) {
        String name = String.format("U+%04X", cp);
        expect(white, Character.isWhitespace(cp), name + " isWhitespace");
        expect(space, Character.isSpaceChar(cp), name + " isSpaceChar");
    }

    private static void checkText(
            String label, String source, boolean blank, String stripped) {
        expect(blank, source.isBlank(), label + " isBlank");
        checks++;
        String actual = source.strip();
        if (!stripped.equals(actual)) {
            throw new AssertionError(label + " strip"
                    + ": expected " + describe(stripped)
                    + ", actual " + describe(actual));
        }
    }

    public static void main(String[] args) {
        checkCodePoint(0x0009, true, false);  // TAB
        checkCodePoint(0x000A, true, false);  // LF
        checkCodePoint(0x001C, true, false);  // FILE SEPARATOR
        checkCodePoint(0x0020, true, true);   // SPACE
        checkCodePoint(0x0085, false, false); // NEL
        checkCodePoint(0x00A0, false, true);  // NBSP
        checkCodePoint(0x1680, true, true);   // OGHAM SPACE MARK
        checkCodePoint(0x2003, true, true);   // EM SPACE
        checkCodePoint(0x2007, false, true);  // FIGURE SPACE
        checkCodePoint(0x200B, false, false); // ZERO WIDTH SPACE
        checkCodePoint(0x2028, true, true);   // LINE SEPARATOR
        checkCodePoint(0x2029, true, true);   // PARAGRAPH SEPARATOR
        checkCodePoint(0x202F, false, true);  // NARROW NBSP
        checkCodePoint(0x3000, true, true);   // IDEOGRAPHIC SPACE
        checkCodePoint(0xFEFF, false, false); // BOM
        checkCodePoint(0x1F600, false, false);// emoji, supplementary cp

        String emoji = new String(Character.toChars(0x1F600));

        checkText("empty", "", true, "");
        checkText("whitespace sequence", " \t\u2003", true, "");
        checkText("EM SPACE outside text", "\u2003Java\u2003", false, "Java");
        checkText("NBSP only", "\u00A0", false, "\u00A0");
        checkText("NBSP then EM SPACE", "\u00A0\u2003", false, "\u00A0");
        checkText("EM SPACE inside text", "A\u2003B", false, "A\u2003B");
        checkText("BOM only", "\uFEFF", false, "\uFEFF");
        checkText("supplementary emoji", emoji, false, emoji);

        System.out.println("PASS: " + checks + " assertions");
    }
}
```

```bash
javac --release 11 -encoding UTF-8 WhitespaceRegressionTest.java
java WhitespaceRegressionTest
```

Khi tất cả kỳ vọng khớp với Java 11, stdout là:

```text
PASS: 48 assertions
```

Có 16 code points, mỗi điểm kiểm tra hai API (32 assertions), cộng 8 chuỗi, mỗi chuỗi kiểm tra `isBlank` và `strip` (16 assertions). Nếu bất kỳ trường hợp nào sai, chương trình ném `AssertionError` với tên test/mã điểm để sửa. Bài test này cũng là “living specification” cho việc chuẩn hóa dữ liệu theo quy tắc Java hiện hành.

## 5. Duyệt đúng code point thay vì chỉ duyệt `char`

Trong UTF-16, một ký tự ngoài BMP như U+1F600 được biểu diễn bằng **hai `char` (surrogate pair)**. `text.length()` tính số đơn vị UTF-16, không phải lúc nào cũng bằng số Unicode code points. Nếu cần phân loại Unicode tổng quát, tránh giả định một lần tăng `i++` là đã sang ký tự tiếp theo.

Dùng stream:

```java
boolean onlyJavaWhitespace =
        text.codePoints().allMatch(Character::isWhitespace);
```

Đoạn trên dùng biến `text` đã có trong ngữ cảnh và cho cùng logic với `text.isBlank()` cho một chuỗi Java không null. Stream rỗng cho kết quả `allMatch` là `true`, phù hợp quy ước `"".isBlank() == true`.

Hoặc duyệt thủ công khi cần chỉ số:

```java
for (int offset = 0; offset < text.length(); ) {
    int codePoint = text.codePointAt(offset);
    boolean white = Character.isWhitespace(codePoint);
    System.out.printf("U+%04X: %s%n", codePoint, white);
    offset += Character.charCount(codePoint);
}
```

Đây là **đoạn minh họa** nằm trong một phương thức có biến `text` kiểu `String`. Nếu `text = "\u2003\u00A0"`, output là:

```text
U+2003: true
U+00A0: false
```

Chỉ số `offset` tăng theo `Character.charCount(codePoint)` (1 hoặc 2 UTF-16 units), tránh tách một supplementary code point làm hai mục. Với dữ liệu chứa surrogate không ghép cặp, cần thêm test nếu hệ thống cho phép chuỗi UTF-16 không chuẩn từ đầu vào bên ngoài.

## 6. Thiết kế dữ liệu kiểm thử theo hành vi nghiệp vụ

Chỉ có `" "` và `"\t"` là quá ít. Tối thiểu nên có các nhóm sau:

1. **Giá trị rỗng và không rỗng:** `""`, `"A"`, `"A B"`, `"A\u2003B"`. Kiểm tra `isBlank` và việc `strip` không làm mất whitespace bên trong.
2. **ASCII và xuống dòng:** SPACE, TAB, LF, CR, kết hợp `" \t\n"`, cả khoảng trắng hai bên và giữa từ. Nếu hệ thống xử lý CRLF, phải thử chuỗi có `"\r\n"` (hai code points).
3. **Khoảng trắng Unicode được Java nhận:** ví dụ U+1680, U+2003, U+2028, U+2029, U+3000. Không dựa trên độ rộng hiển thị.
4. **Các non-breaking spaces được Java loại khỏi `isWhitespace`:** U+00A0, U+2007, U+202F. Thử từng ký tự đứng riêng, ở đầu/cuối, lẫn với EM SPACE, và nằm giữa các chữ.
5. **Ký tự vô hình không phải Java whitespace:** U+200B, U+FEFF, nếu có trong nguồn; kỳ vọng chúng **không** tự biến mất khi gọi `strip()`.
6. **Điều khiển khác biệt giữa các định nghĩa:** U+001C có `isWhitespace == true`, trong khi U+0085 có `isWhitespace == false`. Bảo đảm không lẫn quy tắc Java với Unicode White_Space hay phân tách dòng của thư viện khác.
7. **Code point bổ sung và dữ liệu Unicode bất thường:** dùng U+1F600 để buộc logic duyệt code point đúng; bổ sung trường hợp surrogate không ghép cặp nếu dữ liệu đầu vào có thể chứa nó.
8. **`null` so với chuỗi rỗng:** `null` không phải đối tượng `String`; gọi `null.isBlank()` gây `NullPointerException`. Xử lý chính sách `null` riêng và viết test cho nó.

Đối với một API nhận tên người dùng, mã đơn hàng, văn bản tiếng Việt hoặc dữ liệu sao chép từ HTML/CSV, hãy viết rõ yêu cầu: “trống” nghĩa là *Java whitespace* hay bao gồm cả NBSP? Chọn định nghĩa trước, rồi chốt dữ liệu kiểm thử theo định nghĩa đó. Không thể kết luận mọi ký tự không nhìn thấy đều vô nghĩa: NBSP có chức năng chống ngắt dòng, còn một số ký tự vô hình có ý nghĩa trong hệ chữ viết/emoji.

### Ví dụ chính sách riêng: xem NBSP cũng là khoảng trắng

Nếu yêu cầu sản phẩm quy định các Unicode *space separators* (kể cả NBSP) là khoảng trắng đối với kiểm tra ô nhập rỗng, có thể tạo một predicate **được đặt tên rõ** thay vì gán cho nó ý nghĩa mặc định của Java:

**`PolicyBlankDemo.java`**

```java
public class PolicyBlankDemo {
    static boolean isBlankIncludingNonBreakingSpaces(String value) {
        return value != null
                && value.codePoints().allMatch(cp ->
                    Character.isWhitespace(cp) || Character.isSpaceChar(cp));
    }

    public static void main(String[] args) {
        System.out.println(isBlankIncludingNonBreakingSpaces("\u00A0"));
        System.out.println(isBlankIncludingNonBreakingSpaces("\u2007"));
        System.out.println(isBlankIncludingNonBreakingSpaces("\u200B"));
        System.out.println(isBlankIncludingNonBreakingSpaces(null));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 PolicyBlankDemo.java
java PolicyBlankDemo
```

```text
true
true
false
false
```

Đây là **quy ước nghiệp vụ tự định nghĩa**, không phải cách `String.isBlank()` mặc định hoạt động. Nó chỉ nhận hợp của hai bộ ký tự nói trên; **không** đồng nghĩa “tất cả ký tự vô hình” hay toàn bộ thuộc tính Unicode `White_Space`. `null` được quy định là `false` trong ví dụ, còn chuỗi rỗng là `true` nhờ `allMatch` trên stream rỗng. Nếu dữ liệu cần biến đổi cả hai đầu chuỗi theo quy ước này, phải viết hàm strip tương ứng thay vì vẫn gọi `String.strip()` (vốn chỉ dùng Java whitespace).

## 7. Cẩn thận với regular expression

Các biểu thức thường trông giống nhau nhưng không có cùng tiêu chí:

| Biểu thức Java regex | Cách diễn giải |
| --- | --- |
| `"\\s"` | Mặc định: lớp whitespace của regex (chủ yếu ASCII SPACE và các điều khiển TAB/LF/CR/vertical tab/form feed) |
| `"(?U)\\s"` | Bật `UNICODE_CHARACTER_CLASS`: dựa trên Unicode `White_Space`, có thể nhận NBSP mà `Character.isWhitespace` không nhận |
| `"\\p{javaWhitespace}"` | Phân loại theo chính `Character.isWhitespace` trong regex |

Trong Java source, `"\\s"` có **hai dấu backslash ở dạng source** vì một dấu phải được escape để regex nhận `\s`. Đừng tự cho rằng `replaceAll("\\s+", " ")` tương đương `strip()`: regex có thể dùng định nghĩa whitespace khác và thường thay cả ở giữa chuỗi.

Khi mục tiêu là kiểm tra ô nhập toàn whitespace theo **định nghĩa Java**, `String.isBlank()` thường rõ nhất; khi chỉ cần loại whitespace ở hai đầu, `String.strip()` thường rõ nhất. Dùng regex khi thật sự cần một pattern phức tạp, và kiểm thử các trường hợp NBSP, U+2003, U+0085 để khóa semantics.

## 8. Kiểm thử, quan sát và lỗi phổ biến

- **Test dữ liệu theo code point, không theo ảnh chụp hoặc mắt nhìn.** Trong nhật ký gỡ lỗi, in mã số như `U+00A0` và độ dài/chuỗi escape thay vì chỉ in một ô trống có thể bị hiểu nhầm.
- **Không nhầm Java whitespace với toàn bộ Unicode White_Space.** Nhất là U+00A0, U+2007, U+202F, U+0085; đó là các test phân biệt rất có giá trị.
- **Không dùng `trim()` như một bằng chứng rằng hệ thống đã làm sạch whitespace Unicode.** Hãy nêu API và định nghĩa được yêu cầu, so sánh `strip` trong test nếu đang xử lý Unicode.
- **Không xóa toàn bộ ký tự vô hình theo cảm tính.** U+200B, U+FEFF và các code points liên quan cần chính sách riêng tùy nguồn dữ liệu; việc thay đổi tùy tiện có thể làm mất ý nghĩa hoặc phá hủy văn bản.
- **Không dùng `charAt(i)` để suy ra một `char` luôn là một Unicode character.** Với supplementary code points, ưu tiên `codePoints()` hoặc `codePointAt()` cùng `charCount()`.
- **Không dùng `assert` mà không bật `-ea` rồi nghĩ đã chạy test.** Với bản demo độc lập ở trên, mỗi case sai sẽ ném `AssertionError`; trong dự án thật dùng test runner (JUnit) đang được dự án hỗ trợ.
- **Đừng giả định `strip()` xóa whitespace ở giữa hoặc `isBlank()` chấp nhận `null`.** Cả hai ý định đó phải được mã hóa thành yêu cầu khác.
- **Pin JDK và test lại khi nâng cấp phiên bản/nguồn Unicode.** Bộ thuộc tính ký tự Unicode được thư viện Java hỗ trợ có thể tiến hóa cùng phiên bản JDK; các hành vi có ảnh hưởng đến dữ liệu phải được khóa bằng regression tests thay vì dựa vào render của một font.

## 9. Tự kiểm tra hiểu bài

**Câu 1.** Tại sao `"\u00A0".isBlank()` trả về `false` dù NBSP nhìn giống SPACE?

**Câu 2.** `"\u2003A\u2003".strip()` và `"\u2003A\u2003".trim()` có bằng nhau không?

**Câu 3.** Khi muốn xét chuỗi chỉ gồm code points thuộc Java whitespace, `text.codePoints().allMatch(Character::isWhitespace)` có xử lý chuỗi rỗng như `text.isBlank()` không?

**Câu 4.** Nếu yêu cầu nghiệp vụ nhận NBSP là khoảng trắng, có nên nói `Character.isWhitespace(0x00A0) == true` để đơn giản hóa logic không?

**Đáp án:** 1. Vì NBSP là một trong ba ngoại lệ non-breaking space của `isWhitespace`, nên `isBlank` không coi nó là Java whitespace. 2. Không: `strip` loại U+2003 ở hai đầu, còn `trim` không loại được U+2003. 3. Có, với chuỗi không null: `allMatch` trên stream rỗng trả `true`. 4. Không: giữ nguyên hợp đồng API, tạo predicate riêng và test rõ chính sách.

## Nguồn tham khảo chính thức

- [Java 11 — Character.isWhitespace(int) và Character.isSpaceChar(int)](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Character.html).
- [Java 11 — String: isBlank, strip, stripLeading, stripTrailing, trim](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html).
- [Java 11 — Pattern: các lớp `\s`, `\p{javaWhitespace}` và UNICODE_CHARACTER_CLASS](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/regex/Pattern.html).
