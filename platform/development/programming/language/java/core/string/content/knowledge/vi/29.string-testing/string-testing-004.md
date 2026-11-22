# Kiểm thử `trim`, `strip`, NBSP và các loại xuống dòng trong Java

## 1. Vấn đề: “khoảng trắng” không có một định nghĩa duy nhất

Trong ứng dụng Java, dữ liệu nhận từ biểu mẫu, CSV, file, API, clipboard hoặc văn bản đa ngôn ngữ có thể chứa nhiều ký tự trông giống khoảng trắng. Hai chuỗi nhìn trên màn hình gần như giống nhau vẫn có thể khác về giá trị Unicode và hành vi của `trim()`, `strip()` hoặc phép tách dòng.

Ba khái niệm cần phân biệt:

- **Khoảng trắng theo `String.trim()`:** các `char` ở **hai đầu** có giá trị không lớn hơn `U+0020`. Đây là quy tắc lịch sử, không phải toàn bộ Unicode whitespace.
- **Khoảng trắng theo `String.strip()`:** các code point ở **hai đầu** được `Character.isWhitespace(int)` xem là whitespace. Quy tắc rộng hơn cho nhiều ký tự Unicode, nhưng **cố ý không bao gồm** ba loại khoảng trắng không ngắt: NBSP (`U+00A0`), FIGURE SPACE (`U+2007`), NARROW NO-BREAK SPACE (`U+202F`).
- **Dấu kết thúc dòng:** tùy API có thể là LF, CR, CRLF hoặc các dấu xuống dòng Unicode như NEL, LINE SEPARATOR và PARAGRAPH SEPARATOR. Xóa whitespace đầu/cuối và *tách dòng* là hai bài toán khác nhau.

Khi kiểm thử, cần làm rõ mình muốn **bỏ whitespace ở hai đầu**, **phân tách các dòng**, hay **chuẩn hóa ký tự xuống dòng**. Không được coi ba việc này là tương đương.

## 2. `trim()` và `strip()`: cơ chế và ví dụ

`String.trim()` có từ các phiên bản Java cũ; nó trả về chuỗi bỏ dãy `char` có giá trị `<= U+0020` ở **đầu** và **cuối**. Những ký tự nằm giữa chuỗi không bị đụng tới. Vì tiêu chí dựa trên mã `char`, `trim()` có thể loại bỏ cả một số ký tự điều khiển không nhất thiết được người dùng gọi là dấu cách.

`String.strip()` (Java 11+) loại bỏ các code point đầu/cuối thỏa `Character.isWhitespace(int)`. Đây thường là lựa chọn phù hợp hơn với văn bản Unicode, nhưng cũng **không** có nghĩa là “loại bỏ mọi ký tự nhìn có vẻ trống”.

| Đầu/cuối chuỗi là | Mã | `trim()` | `strip()` | Giải thích |
| --- | --- | --- | --- | --- |
| SPACE thông thường | `U+0020` | Loại bỏ | Loại bỏ | Cả hai nhận diện. |
| TAB, LF, CR | `U+0009`, `U+000A`, `U+000D` | Loại bỏ | Loại bỏ | Các ký tự điều khiển trong cả hai tập. |
| EM SPACE | `U+2003` | Giữ | Loại bỏ | `Character.isWhitespace` trả `true`. |
| IDEOGRAPHIC SPACE | `U+3000` | Giữ | Loại bỏ | Một ví dụ không phải ASCII được `strip` loại bỏ. |
| NBSP (NO-BREAK SPACE) | `U+00A0` | Giữ | **Giữ** | `Character.isWhitespace` trả `false`. |
| FIGURE SPACE | `U+2007` | Giữ | **Giữ** | Thuộc nhóm non-breaking theo API. |
| NARROW NO-BREAK SPACE | `U+202F` | Giữ | **Giữ** | Thuộc nhóm non-breaking theo API. |
| LINE SEPARATOR | `U+2028` | Giữ | Loại bỏ | Là whitespace theo `Character.isWhitespace`, nhưng không phải delimiter của `String.lines()`. |
| NEL (NEXT LINE) | `U+0085` | Giữ | Giữ | Được regex `\R` nhận diện là line break, không nằm trong định nghĩa Java whitespace của `strip`. |

**Điểm rất dễ nhầm:** `Character.isSpaceChar(codePoint)` và `Character.isWhitespace(codePoint)` là hai phép kiểm tra **khác nhau**. NBSP, FIGURE SPACE và NARROW NO-BREAK SPACE được `isSpaceChar` nhận diện nhưng bị loại trừ có chủ đích khỏi `isWhitespace`. Vì `strip` dựa vào `isWhitespace`, chúng không bị `strip` xóa.

Các API hữu ích khác (Java 11+):

- `stripLeading()`: chỉ loại bỏ whitespace theo `Character.isWhitespace` ở **đầu**.
- `stripTrailing()`: chỉ loại bỏ ở **cuối**.
- `isBlank()`: trả `true` nếu chuỗi rỗng hoặc toàn bộ code point là Java whitespace. Ví dụ chuỗi chỉ chứa NBSP **không** được xem là blank bằng `isBlank()`.
- `String.stripIndent()` / text blocks giải quyết thụt lề trong những ngữ cảnh khác; không thay cho việc xác định ký tự cần làm sạch trong dữ liệu đầu vào.

Đối với dữ liệu nghiệp vụ, nếu đặc tả yêu cầu loại bỏ **cả NBSP** ở hai đầu, hãy viết quy tắc rõ ràng và kiểm thử riêng. Không âm thầm đổi định nghĩa “blank” trên toàn ứng dụng chỉ vì một giao diện người dùng hiển thị NBSP giống SPACE.

## 3. Dấu xuống dòng: LF, CR, CRLF và Unicode

Các dòng văn bản không nhất thiết sử dụng cùng chuỗi ký tự kết thúc:

| Tên | Biểu diễn Java / mã Unicode | Thường gặp |
| --- | --- | --- |
| LF (Line Feed) | `"\n"` / `U+000A` | File Unix/Linux, nhiều API, Git |
| CR (Carriage Return) | `"\r"` / `U+000D` | Dữ liệu cũ, một số nguồn giao tiếp |
| CRLF | `"\r\n"` / `U+000D U+000A` | Nhiều file/định dạng Windows và giao thức |
| VT (Vertical Tab) | `U+000B` | Dữ liệu điều khiển/format đặc biệt |
| FF (Form Feed) | `"\f"` / `U+000C` | Phân trang hoặc dữ liệu cũ |
| NEL (Next Line) | `U+0085` | Một số nguồn Unicode/cũ |
| LINE SEPARATOR | `U+2028` | Dấu phân cách dòng Unicode |
| PARAGRAPH SEPARATOR | `U+2029` | Dấu phân cách đoạn Unicode |

**Phân biệt API:**

- `String.lines()` (Java 11+) **chỉ** tách tại LF, CR, CRLF. `"\r\n"` là **một** dấu kết thúc dòng. Dòng trả về không chứa ký tự xuống dòng.
- `String.lines()` **không** tách tại `U+0085`, `U+2028` hoặc `U+2029`. Nó cũng không tạo một dòng rỗng bổ sung sau ký tự kết thúc dòng cuối cùng; chuỗi rỗng tạo **zero lines**.
- Trong `java.util.regex.Pattern`, biểu thức `\R` nhận diện một chuỗi xuống dòng: `\r\n` hoặc một ký tự trong nhóm LF, VT, FF, CR, NEL, LS, PS. Trong **chuỗi Java** phải viết `"\\R"` để truyền ký hiệu regex `\R`.
- `text.split("\\R", -1)` tách theo nhóm dấu xuống dòng Unicode và **giữ cả phần tử trống ở cuối** nhờ giới hạn âm `-1`. Nếu dùng overload `split("\\R")` (limit = 0), các phần tử rỗng ở cuối sẽ bị loại bỏ.
- `text.replaceAll("\\R", "\n")` chuẩn hóa các chuỗi kết thúc dòng được regex nhận diện thành LF. Đừng áp dụng bừa lên dữ liệu nhị phân, chuỗi được ký số hoặc những format mà dạng xuống dòng nguyên gốc mang ý nghĩa riêng.

**Đặc biệt:** `\s`, `\h`, `\v`, `\R` và `Character.isWhitespace` có các định nghĩa riêng; dùng `split("\\s+")` để xử lý xuống dòng hoặc NBSP mà không kiểm tra cờ regex có thể cho kết quả ngoài dự kiến. `\R` biểu diễn **cả một chuỗi kết thúc dòng**, trong đó CRLF được xử lý cùng nhau, nên là lựa chọn rõ ràng khi muốn tách nhiều kiểu xuống dòng.

## 4. Bài kiểm thử Java 17+ chạy độc lập

Tạo file **`StringWhitespaceChecks.java`**, lưu mã nguồn bằng UTF-8. Chương trình dùng các phép so sánh thực tế thay vì dựa vào mắt thường; hàm `cp(int)` tạo ký tự từ code point để NBSP và các dấu xuống dòng ẩn không bị editor tự thay thế.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class StringWhitespaceChecks {
    private static int passed;

    private static void check(String name, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    name + " | expected=" + expected + ", actual=" + actual);
        }
        passed++;
    }

    private static String cp(int value) {
        return new String(Character.toChars(value));
    }

    public static void main(String[] args) {
        String em = cp(0x2003);
        String nbsp = cp(0x00A0);
        String figure = cp(0x2007);
        String narrow = cp(0x202F);
        String ls = cp(0x2028);
        String ps = cp(0x2029);
        String nel = cp(0x0085);

        // Kiểm thử trim/strip tại hai đầu.
        String ascii = " \tA\r\n ";
        check("trim ASCII", "A", ascii.trim());
        check("strip ASCII", "A", ascii.strip());

        String emWrapped = em + "A" + em;
        check("trim keeps EM SPACE", emWrapped, emWrapped.trim());
        check("strip removes EM SPACE", "A", emWrapped.strip());

        String nbspWrapped = nbsp + "A" + nbsp;
        check("trim keeps NBSP", nbspWrapped, nbspWrapped.trim());
        check("strip keeps NBSP", nbspWrapped, nbspWrapped.strip());

        String figureWrapped = figure + "A" + figure;
        String narrowWrapped = narrow + "A" + narrow;
        check("strip keeps FIGURE SPACE", figureWrapped, figureWrapped.strip());
        check("strip keeps NARROW NBSP", narrowWrapped, narrowWrapped.strip());

        check("NBSP isWhitespace", false, Character.isWhitespace(0x00A0));
        check("NBSP isSpaceChar", true, Character.isSpaceChar(0x00A0));
        check("FIGURE SPACE isWhitespace",
                false, Character.isWhitespace(0x2007));
        check("NARROW NBSP isWhitespace",
                false, Character.isWhitespace(0x202F));
        check("EM SPACE isWhitespace", true, Character.isWhitespace(0x2003));

        check("stripLeading", "A" + em, emWrapped.stripLeading());
        check("stripTrailing", em + "A", emWrapped.stripTrailing());
        check("trim does not change internal whitespace",
                "A \t B", (" A \t B ").trim());

        // Kiểm thử các kiểu xuống dòng.
        String crLfOnly = "a\r\nb\nc\rd";
        check("String.lines CRLF LF CR",
                List.of("a", "b", "c", "d"),
                crLfOnly.lines().toList());

        String unicodeLineBreaks = "a" + ls + "b" + ps + "c" + nel + "d";
        check("lines keeps Unicode separators",
                List.of(unicodeLineBreaks),
                unicodeLineBreaks.lines().toList());
        check("regex R splits Unicode separators",
                List.of("a", "b", "c", "d"),
                Arrays.asList(unicodeLineBreaks.split("\\R", -1)));

        String mixed = "A\r\nB\nC\rD" + ls + "E" + nel + "F" + ps + "G";
        check("regex R splits mixed line endings",
                List.of("A", "B", "C", "D", "E", "F", "G"),
                Arrays.asList(mixed.split("\\R", -1)));
        check("split negative limit keeps trailing empty",
                List.of("x", ""),
                Arrays.asList("x\n".split("\\R", -1)));
        check("String.lines does not add trailing empty",
                List.of("x"), "x\n".lines().toList());
        check("String.lines keeps actual blank line",
                List.of("a", "", "b"), "a\n\nb".lines().toList());
        check("empty string has no lines",
                List.of(), "".lines().toList());

        String lsWrapped = ls + "A" + ls;
        check("trim keeps LINE SEPARATOR", lsWrapped, lsWrapped.trim());
        check("strip removes LINE SEPARATOR", "A", lsWrapped.strip());

        check("normalize all recognized line endings",
                "A\nB\nC\nD\nE\nF\nG",
                mixed.replaceAll("\\R", "\n"));

        System.out.println("PASS: " + passed + " checks");
    }
}
```

Biên dịch, chạy:

```bash
javac -encoding UTF-8 StringWhitespaceChecks.java
java StringWhitespaceChecks
```

**Stdout khi tất cả kiểm thử đạt** trên Java 17+:

```text
PASS: 27 checks
```

Nếu hành vi khác với kỳ vọng, `check` ném `AssertionError` kèm tên kiểm thử đầu tiên bị lỗi và chương trình dừng trước khi in dòng `PASS`. Những giá trị như NBSP, LS, NEL được tạo bằng code point nên không lệ thuộc việc terminal có thể hiển thị chúng hay không.

### Điểm học được từ bộ kiểm thử

- SPACE và TAB ở biên được cả `trim` và `strip` xóa; EM SPACE chỉ bị `strip` xóa.
- NBSP và hai biến thể non-breaking không bị cả `trim` lẫn `strip` xóa. `isSpaceChar` có thể là `true` trong khi `isWhitespace` là `false`.
- `String.lines()` xử lý CR/LF/CRLF; `"\\R"` xử lý thêm dấu xuống dòng Unicode.
- Dòng rỗng **ở giữa** các dấu kết thúc dòng có thể là dữ liệu có nghĩa; dòng rỗng phát sinh **sau** một dấu kết thúc cuối cùng được `String.lines()` và `split` với limit `-1` xử lý khác nhau.
- Chuẩn hóa xuống dòng nên là một bước có chủ đích, độc lập với việc làm sạch whitespace ở biên.

## 5. Thiết kế kiểm thử theo ma trận thay vì chỉ thử dấu cách thông thường

Đừng chỉ test `" text ".trim()` rồi suy ra mọi dữ liệu đều an toàn. Hãy bao phủ ít nhất các chiều sau:

| Trục kiểm thử | Ca cần có | Điều xác minh |
| --- | --- | --- |
| Vị trí | Đầu, cuối, cả hai đầu, ở giữa chuỗi | Chỉ vị trí định xóa bị thay đổi. |
| Độ dài | Chuỗi rỗng, chỉ whitespace, nhiều ký tự liên tiếp | Không mất dữ liệu ngoài phạm vi. |
| Whitespace ASCII | SPACE, TAB, LF, CR, CRLF | `trim`/`strip` xử lý đúng đầu/cuối. |
| Whitespace Unicode | EM SPACE, IDEOGRAPHIC SPACE, LINE SEPARATOR | Phân biệt `trim` và `strip`. |
| Non-breaking | NBSP, FIGURE SPACE, NARROW NBSP | Các ký tự được giữ theo đúng hợp đồng. |
| Kiểu xuống dòng | LF, CR, CRLF, NEL, LS, PS | Lựa chọn đúng giữa `lines` và regex `\R`. |
| Dòng rỗng | Hai dấu kết thúc liền nhau, đầu chuỗi, cuối chuỗi | Không bỏ/thêm dòng do hiểu nhầm `split`/`lines`. |
| Dữ liệu Unicode | Tiếng Việt, emoji, ký tự kết hợp | Không vô tình xóa/sửa nội dung bên trong. |

Với JUnit 5, có thể chuyển các dòng `check` thành các ca `@ParameterizedTest` hoặc `@MethodSource`, dùng `assertEquals(expected, actual)` và đặt tên ca có cả code point (ví dụ `U+00A0`). Đây là hướng mở rộng test suite; chương trình ở trên chạy độc lập bằng JDK 17+ và **không cần thêm dependency**.

Một số kiểm thử cần chạy trên nhiều môi trường, đặc biệt khi dữ liệu đọc từ file hoặc HTTP. Tuy nhiên, nếu chuỗi `String` đã có đúng các code point, quy tắc `trim`, `strip` và `lines` phải theo hợp đồng API, không được phụ thuộc tùy tiện vào dấu xuống dòng của hệ điều hành.

## 6. Khi đọc file hoặc nhận dữ liệu từ bên ngoài

Một file Windows thường có CRLF, file Unix thường có LF; nhưng không phải mọi file đều tuân theo quy ước môi trường chạy. Không nên dùng `System.lineSeparator()` để đoán delimiter của file bất kỳ. `System.lineSeparator()` cho biết dấu xuống dòng **mặc định của nền tảng hiện tại**, chủ yếu có ích khi **tạo** văn bản cho nền tảng đó; nó không tự phát hiện loại xuống dòng của dữ liệu nguồn.

Ví dụ thao tác chuẩn hóa **minh họa** (đặt trong hàm đã có biến `text`):

```java
String normalized = text.replaceAll("\\R", "\n");
List<String> lines = Arrays.asList(normalized.split("\n", -1));
```

Đoạn trên dùng `java.util.Arrays` và `java.util.List`. `-1` bảo toàn phần tử rỗng cuối cùng nếu văn bản kết thúc bằng LF. Đây là lựa chọn khi dữ liệu nghiệp vụ cần lưu thông tin về dấu kết thúc dòng cuối; nếu không cần, có thể chọn chính sách khác và viết kiểm thử tương ứng.

Khi làm sạch đầu/cuối từng trường:

```java
String cleaned = field.strip();  // NBSP vẫn được giữ
```

Đây là **một quy tắc theo Java whitespace**, không phải bộ lọc tổng quát cho mọi khoảng trắng. Nếu yêu cầu sản phẩm nói “NBSP cũng được xóa”, có thể xây một hàm theo predicate công khai:

```java
// Mã minh họa: dùng bên trong một class và truyền vào String hợp lệ.
static boolean isBoundarySpace(int cp) {
    return Character.isWhitespace(cp)
            || cp == 0x00A0
            || cp == 0x2007
            || cp == 0x202F;
}

static String stripIncludingNbsp(String value) {
    int start = 0;
    int end = value.length();
    while (start < end) {
        int cp = value.codePointAt(start);
        if (!isBoundarySpace(cp)) break;
        start += Character.charCount(cp);
    }
    while (start < end) {
        int cp = value.codePointBefore(end);
        if (!isBoundarySpace(cp)) break;
        end -= Character.charCount(cp);
    }
    return value.substring(start, end);
}
```

Đoạn minh họa sử dụng **code point**, nên không cắt đôi surrogate pair. Hàm chỉ xóa ở hai đầu, bảo toàn phần nội dung giữa chuỗi. Chính sách xóa NBSP là lựa chọn của ứng dụng và cần kiểm thử riêng; không gán nó cho hành vi mặc định của `String.strip()`.

Nếu dữ liệu được giải mã sai charset trước khi vào `String`, `strip` hoặc `trim` không thể chữa mojibake. Cần biết encoding thật của file/giao thức (thường dùng UTF-8 khi do mình định nghĩa), giải mã đúng rồi mới xử lý whitespace.

## 7. Các lỗi phổ biến cần phát hiện sớm

**Lỗi 1 — cho rằng `strip()` loại bỏ NBSP.** Dữ liệu sao chép từ website hoặc tài liệu có thể chứa `U+00A0` ở đầu/cuối; `strip()` vẫn trả về chuỗi còn NBSP. Kiểm tra code point thực tế thay vì nhìn vào khoảng trắng trên màn hình.

**Lỗi 2 — dùng `trim()` thay `strip()` cho whitespace Unicode.** `trim()` giữ `U+2003` và `U+3000`. Nếu đầu vào cần xử lý các dấu cách này, `strip()` thường thích hợp hơn.

**Lỗi 3 — lấy `String.lines()` để tách mọi loại xuống dòng Unicode.** `lines()` chỉ có ba loại delimiter LF/CR/CRLF. Dùng `split("\\R", -1)` hoặc parser chuyên dụng nếu đặc tả yêu cầu NEL, LS, PS.

**Lỗi 4 — nghĩ CRLF là hai dòng rỗng.** `String.lines()` và regex `\R` đều nhận CRLF là **một** terminator, nên `"A\r\nB"` có hai dòng `A` và `B`.

**Lỗi 5 — quên tham số `-1` của `split`.** `"A\n".split("\\R")` bỏ phần tử rỗng cuối, còn `split("\\R", -1)` giữ. Cần quyết định đầu ra mong muốn trước khi viết test.

**Lỗi 6 — xóa toàn bộ whitespace mà không xét ngữ nghĩa.** Trong tên, địa chỉ, văn bản pháp lý, số lượng có dấu phân cách hoặc dữ liệu có định dạng, NBSP và dòng rỗng có thể mang ý nghĩa trình bày. Tự động thay mọi whitespace bằng SPACE có thể làm thay đổi dữ liệu cần bảo toàn.

**Lỗi 7 — kiểm tra bằng console.** Ký tự U+00A0, U+2003, LF và CR khó phân biệt khi in trực tiếp. Dùng biểu diễn `U+XXXX` hoặc test `codePointAt`/`equals`; không kết luận chỉ từ hình thức.

**Lỗi 8 — phụ thuộc nền tảng khi sinh dữ liệu test.** Viết literal `"\n"`/`"\r\n"` hoặc tạo code point là cách kiểm thử deterministic. Tránh tạo dữ liệu tham chiếu bằng `System.lineSeparator()` khi mục tiêu là so sánh các loại xuống dòng xuyên hệ điều hành.

## 8. Checklist khi đưa vào sản phẩm

1. Xác định rõ chính sách: loại bỏ whitespace kiểu `trim`, kiểu `strip`, hay thêm NBSP/nhóm ký tự riêng.
2. Liệt kê code point cần hỗ trợ, đặc biệt `U+00A0`, `U+2007`, `U+202F`, `U+2003`, `U+0085`, `U+2028`, `U+2029`.
3. Chọn API tách dòng theo yêu cầu: `lines()` cho CR/LF/CRLF; `"\\R"` khi cần các kiểu Unicode rộng hơn.
4. Quyết định chính sách giữ/bỏ dòng rỗng cuối; nếu dùng `split`, đặt limit tường minh.
5. Test cả dữ liệu ở đầu, giữa và cuối chuỗi, bao gồm chuỗi rỗng và nhiều delimiter liên tiếp.
6. Khi chuẩn hóa, chỉ thay ký tự có chủ đích và giữ bản gốc nếu dữ liệu quan trọng.

## Tài liệu chính thức

- [Java 17 `String.trim`, `strip`, `lines`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).
- [Java 17 `Character.isWhitespace` và `Character.isSpaceChar`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html).
- [Java 17 `Pattern`: `\R`, ký tự kết thúc dòng và `split`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html).
