# Tra thuộc tính ký tự bằng Character

Java cung cấp lớp `java.lang.Character` để tra cứu thuộc tính Unicode của một ký tự: loại chữ, chữ hoa/thường, chữ số, khoảng trắng, tên Unicode, script, block, hướng hiển thị và khả năng dùng trong identifier. Các method này giúp xử lý văn bản đa ngôn ngữ theo dữ liệu Unicode của JDK, thay vì tự kiểm tra bằng các khoảng ký tự ASCII.

Điểm quan trọng nhất khi dùng `Character` là phân biệt **UTF-16 code unit (`char`)** với **Unicode code point (`int`)**. Một ký tự ngoài Basic Multilingual Plane (BMP) chiếm hai `char`, nhưng vẫn là một code point. Các method nhận `int codePoint` mới xử lý đầy đủ supplementary characters. Trong JDK 26 và 27, dữ liệu thuộc tính của `Character` dựa trên **Unicode 17.0**; API là Java SE ổn định, không cần preview flag.

## 1. char, code point và ký tự người dùng nhìn thấy

Java lưu `String` dưới dạng chuỗi UTF-16 code unit. Một `char` là một đơn vị 16 bit của UTF-16, không phải lúc nào cũng là một ký tự Unicode hoàn chỉnh.

- Code point trong BMP, từ U+0000 đến U+FFFF, thường được biểu diễn bằng một `char`.
- Code point supplementary, từ U+10000 đến U+10FFFF, được biểu diễn bằng một cặp surrogate gồm high surrogate và low surrogate.
- Một grapheme cluster có thể gồm nhiều code point, ví dụ chữ cái cộng combining mark hoặc emoji ghép bằng ZWJ.

Ví dụ:

```java
String text = "A😀";

System.out.println(text.length());                  // 3 UTF-16 code units
System.out.println(text.codePointCount(0, text.length())); // 2 code points

int emoji = text.codePointAt(1);
System.out.printf("U+%X%n", emoji);                 // U+1F600
System.out.println(Character.isEmoji(emoji));       // true
```

`String.length()` đếm `char`, không đếm code point. Nếu duyệt bằng `charAt(i)` hoặc `chars()`, một supplementary character sẽ xuất hiện thành hai giá trị surrogate. Khi cần phân tích thuộc tính Unicode, hãy duyệt bằng `String.codePoints()` hoặc `codePointAt()`.

```java
String text = "A𝄞😀";

text.codePoints().forEach(codePoint -> {
    System.out.printf("U+%X%n", codePoint);
});
```

Không nên dùng các overload chỉ nhận `char` nếu dữ liệu có thể chứa supplementary character. Ví dụ `Character.isLetter(char)` không thể nhận diện một chữ cái supplementary qua từng surrogate riêng lẻ; `Character.isLetter(int)` xử lý được code point hoàn chỉnh.

## 2. Lấy loại ký tự bằng getType

`Character.getType(int codePoint)` trả về general category của code point theo Unicode. Kết quả là một hằng `int` của `Character`, chẳng hạn `UPPERCASE_LETTER`, `DECIMAL_DIGIT_NUMBER` hoặc `OTHER_SYMBOL`.

Các nhóm category chính:

| Nhóm | Các category thường gặp | Ý nghĩa |
| --- | --- | --- |
| `L` — Letter | `Lu`, `Ll`, `Lt`, `Lm`, `Lo` | Chữ hoa, chữ thường, titlecase, modifier letter và chữ khác |
| `M` — Mark | `Mn`, `Mc`, `Me` | Dấu kết hợp không chiếm khoảng, dấu kết hợp chiếm khoảng và enclosing mark |
| `N` — Number | `Nd`, `Nl`, `No` | Chữ số thập phân, số dạng chữ và số khác |
| `P` — Punctuation | `Pc`, `Pd`, `Ps`, `Pe`, `Pi`, `Pf`, `Po` | Dấu nối, dấu gạch, ngoặc, dấu nháy và dấu câu khác |
| `S` — Symbol | `Sm`, `Sc`, `Sk`, `So` | Ký hiệu toán học, tiền tệ, modifier và symbol khác |
| `Z` — Separator | `Zs`, `Zl`, `Zp` | Dấu phân cách khoảng trắng, dòng và đoạn |
| `C` — Other | `Cc`, `Cf`, `Cs`, `Co`, `Cn` | Control, format, surrogate, private use và unassigned |

Ví dụ:

```java
int type = Character.getType('A');
System.out.println(type == Character.UPPERCASE_LETTER); // true

int combiningAcute = Character.getType(0x0301);
System.out.println(combiningAcute == Character.NON_SPACING_MARK); // true

int supplementaryLetter = Character.getType(0x2F81A);
System.out.println(supplementaryLetter == Character.OTHER_LETTER); // true
```

`getType()` hữu ích khi cần phân loại chi tiết hơn các predicate như `isLetter()` hoặc `isDigit()`. Không nên tự gán ý nghĩa nghiệp vụ chỉ dựa vào một category nếu quy tắc cần tuân theo một chuẩn khác, ví dụ quy tắc tên người, mã sản phẩm hoặc định dạng số.

## 3. Phân biệt letter, alphabetic và digit

Các method `isLetter`, `isAlphabetic`, `isLetterOrDigit` và `isDigit` có phạm vi khác nhau.

| Method | Điều kiện chính | Ví dụ |
| --- | --- | --- |
| `isLetter(int)` | Category thuộc nhóm chữ `L` | `A`, `đ`, chữ CJK |
| `isAlphabetic(int)` | Chữ, `LETTER_NUMBER` hoặc có Unicode property `Other_Alphabetic` | Bao gồm một số ký tự alphabetic không thuộc category `L` |
| `isDigit(int)` | Category `DECIMAL_DIGIT_NUMBER` (`Nd`) | `0`, chữ số Ả Rập-Ấn `١`, chữ số Devanagari |
| `isLetterOrDigit(int)` | Letter hoặc decimal digit | Chữ và chữ số thập phân |

Ví dụ với số La Mã mười hai `Ⅻ` (U+216B):

```java
int romanTwelve = 0x216B;

System.out.println(Character.getType(romanTwelve)
        == Character.LETTER_NUMBER);       // true
System.out.println(Character.isLetter(romanTwelve));      // false
System.out.println(Character.isAlphabetic(romanTwelve));  // true
System.out.println(Character.isDigit(romanTwelve));       // false
System.out.println(Character.getNumericValue(romanTwelve)); // 12
```

`isAlphabetic` rộng hơn `isLetter`; `isDigit` chỉ kiểm tra chữ số thập phân chứ không phải mọi ký tự có giá trị số. Khi xác định tên hoặc nội dung văn bản, hãy chọn predicate theo quy tắc thực tế thay vì coi mọi thứ có numeric value là digit.

## 4. Tra giá trị số bằng digit và getNumericValue

Hai method thường bị nhầm:

- `Character.digit(codePoint, radix)` kiểm tra code point có thể biểu diễn một chữ số trong cơ số đã cho hay không. Nếu hợp lệ, trả giá trị digit; nếu không hợp lệ, trả `-1`.
- `Character.getNumericValue(codePoint)` trả giá trị số gắn với ký tự Unicode. Nó có thể nhận ra số La Mã hoặc chữ cái A–Z dùng trong hệ cơ số cao hơn.

Ví dụ:

```java
int arabicIndicOne = 0x0661; // ARABIC-INDIC DIGIT ONE: ١
int romanFifty = 0x216C;     // ROMAN NUMERAL FIFTY: Ⅼ

System.out.println(Character.isDigit(arabicIndicOne));          // true
System.out.println(Character.digit(arabicIndicOne, 10));        // 1
System.out.println(Character.getNumericValue(arabicIndicOne));  // 1

System.out.println(Character.isDigit(romanFifty));              // false
System.out.println(Character.digit(romanFifty, 10));            // -1
System.out.println(Character.getNumericValue(romanFifty));      // 50
```

`getNumericValue` có hai giá trị đặc biệt:

- `-1`: ký tự không có numeric value.
- `-2`: ký tự có numeric value nhưng không thể biểu diễn bằng số nguyên không âm, ví dụ một phân số Unicode.

Với parser số, `digit(codePoint, radix)` thường phù hợp hơn vì nó kiểm tra chữ số trong cơ số mong muốn. Không dùng `getNumericValue()` để parse một chuỗi số mà không tự kiểm tra dấu, dấu thập phân, nhóm chữ số và quy tắc locale.

## 5. Tra khoảng trắng: isWhitespace và isSpaceChar

`Character.isWhitespace(int)` kiểm tra whitespace theo định nghĩa của Java. `Character.isSpaceChar(int)` kiểm tra ba general category Unicode: `SPACE_SEPARATOR`, `LINE_SEPARATOR` và `PARAGRAPH_SEPARATOR`.

Hai method không tương đương. Đặc biệt, các non-breaking space như U+00A0, U+2007 và U+202F được xem là space character nhưng không được `isWhitespace()` xem là Java whitespace.

```java
int normalSpace = 0x0020;
int noBreakSpace = 0x00A0;
int lineSeparator = 0x2028;

System.out.println(Character.isWhitespace(normalSpace)); // true
System.out.println(Character.isSpaceChar(normalSpace));  // true

System.out.println(Character.isWhitespace(noBreakSpace)); // false
System.out.println(Character.isSpaceChar(noBreakSpace));  // true

System.out.println(Character.isWhitespace(lineSeparator)); // true
System.out.println(Character.isSpaceChar(lineSeparator));  // true
```

Chọn method theo mục tiêu:

- Khi cần nhận biết whitespace theo quy tắc Java, dùng `isWhitespace`.
- Khi cần nhận biết các ký tự thuộc nhóm Unicode separator, dùng `isSpaceChar`.
- Khi chuẩn hóa input người dùng, không giả định `trim()` hoặc một predicate whitespace đơn lẻ xử lý mọi loại khoảng trắng giống nhau. Xác định rõ có cần giữ non-breaking space hay không.

Không dùng `Character.isSpace(char)` trong mã mới: method này đã deprecated từ lâu và được thay bằng `isWhitespace(char)`. Với supplementary code point, dùng overload nhận `int`.

## 6. Tra tên, trạng thái được gán và thuộc tính cơ bản

Các method sau hữu ích khi hiển thị thông tin chẩn đoán:

| Method | Ý nghĩa |
| --- | --- |
| `getName(int)` | Tên Unicode của code point; trả `null` nếu code point unassigned |
| `isDefined(int)` | Kiểm tra code point đã được gán trong dữ liệu Unicode mà JDK sử dụng |
| `isValidCodePoint(int)` | Kiểm tra giá trị nằm trong khoảng code point U+0000 đến U+10FFFF |
| `isUpperCase(int)` / `isLowerCase(int)` | Kiểm tra thuộc tính chữ hoa/chữ thường |
| `isTitleCase(int)` | Kiểm tra titlecase |
| `isMirrored(int)` | Kiểm tra thuộc tính mirrored trong Unicode |

Ví dụ:

```java
int codePoint = 0x1F600;

System.out.println(Character.isValidCodePoint(codePoint)); // true
System.out.println(Character.isDefined(codePoint));        // true
System.out.println(Character.getName(codePoint));          // GRINNING FACE
System.out.println(Character.isEmoji(codePoint));           // true
```

`isValidCodePoint` chỉ kiểm tra miền số của code point; nó không có nghĩa code point đã được gán hoặc có glyph trên font hiện tại. Dùng `isDefined` khi cần biết JDK có dữ liệu gán cho code point đó hay chưa. `getName` có thể trả `null`, vì vậy cần xử lý trường hợp này trong code hiển thị/log.

Một chi tiết khác: miền số mà `isValidCodePoint` kiểm tra cũng bao gồm các giá trị surrogate U+D800 đến U+DFFF. Nếu đang xác thực dữ liệu Unicode scalar value từ input bên ngoài, cần loại riêng khoảng surrogate; một scalar value không thể là surrogate.

## 7. Phân biệt UnicodeScript và UnicodeBlock

`Character.UnicodeScript.of(int)` trả về script của code point, ví dụ `LATIN`, `GREEK`, `CYRILLIC`, `HAN`, `ARABIC`. Ba giá trị đặc biệt thường gặp:

- `COMMON`: ký tự được dùng chung giữa nhiều script, như dấu câu hoặc chữ số.
- `INHERITED`: ký tự kế thừa script từ ký tự lân cận, thường gặp ở combining marks.
- `UNKNOWN`: script chưa được xác định trong dữ liệu Unicode hiện hành.

`Character.UnicodeBlock.of(int)` trả về block chứa code point, ví dụ `BASIC_LATIN`, `LATIN_1_SUPPLEMENT` hoặc `CJK_UNIFIED_IDEOGRAPHS`. Method có thể trả `null` nếu code point không thuộc block được định nghĩa.

```java
int latinA = 'A';
int han = 0x4E2D; // 中

System.out.println(Character.UnicodeScript.of(latinA)); // LATIN
System.out.println(Character.UnicodeBlock.of(latinA));  // BASIC_LATIN

System.out.println(Character.UnicodeScript.of(han)); // HAN
System.out.println(Character.UnicodeBlock.of(han));  // CJK_UNIFIED_IDEOGRAPHS
```

Script và block không phải cùng một khái niệm:

| UnicodeScript | UnicodeBlock |
| --- | --- |
| Mô tả hệ chữ/nhóm chữ viết | Mô tả vùng code point liên tục trong bảng mã |
| Một script có thể trải qua nhiều block | Một block có thể chứa ký tự dùng chung hoặc ký tự thuộc nhiều script |
| Có `COMMON`, `INHERITED`, `UNKNOWN` | Có thể không có block và trả `null` |

Không dùng `UnicodeBlock` để suy luận ngôn ngữ của người dùng. Ví dụ một block có thể chứa nhiều ký tự được dùng trong nhiều ngôn ngữ; script cũng không đồng nghĩa với ngôn ngữ.

## 8. Kiểm tra hướng hiển thị và ký tự mirrored

Với văn bản kết hợp chữ Latin, Arabic, Hebrew và chữ số, Unicode Bidirectional Algorithm (Bidi) xác định thứ tự hiển thị. `Character.getDirectionality(int)` trả về thuộc tính bidi class của một code point, ví dụ:

- `DIRECTIONALITY_LEFT_TO_RIGHT` cho ký tự có hướng trái sang phải.
- `DIRECTIONALITY_RIGHT_TO_LEFT` cho ký tự có hướng phải sang trái.
- `DIRECTIONALITY_RIGHT_TO_LEFT_ARABIC` cho ký tự thuộc nhóm Arabic strong RTL.
- `DIRECTIONALITY_EUROPEAN_NUMBER` hoặc `DIRECTIONALITY_ARABIC_NUMBER` cho nhóm chữ số.
- `DIRECTIONALITY_WHITESPACE` và các giá trị neutral cho ký tự phân cách hoặc không có hướng mạnh.

`Character.isMirrored(int)` kiểm tra ký tự có thuộc tính mirrored hay không, ví dụ dấu ngoặc có thể được hiển thị theo chiều tương ứng trong văn bản RTL.

```java
int latin = 'A';
int arabicLetter = 0x0627; // ARABIC LETTER ALEF
int leftParenthesis = '(';

System.out.println(Character.getDirectionality(latin)
        == Character.DIRECTIONALITY_LEFT_TO_RIGHT); // true
System.out.println(Character.getDirectionality(arabicLetter)
        == Character.DIRECTIONALITY_RIGHT_TO_LEFT_ARABIC); // true
System.out.println(Character.isMirrored(leftParenthesis)); // true
```

`getDirectionality` chỉ trả thuộc tính của từng code point; nó không tự sắp xếp lại cả chuỗi. Khi hiển thị văn bản hỗn hợp LTR/RTL, hãy để thư viện giao diện hoặc bidi engine thực hiện Unicode Bidirectional Algorithm. Không tự đảo chuỗi dựa trên `getDirectionality`.

## 9. Tra thuộc tính Emoji

Từ Java 21, `Character` có các method như `isEmoji`, `isEmojiPresentation`, `isEmojiModifier`, `isEmojiModifierBase`, `isEmojiComponent` và `isExtendedPictographic`. Các method này nhận một code point `int` và kiểm tra Unicode Emoji property tương ứng.

```java
int grinningFace = 0x1F600;
int heart = 0x2764;

System.out.println(Character.isEmoji(grinningFace));             // true
System.out.println(Character.isEmojiPresentation(grinningFace)); // true
System.out.println(Character.isEmoji(heart));                    // true
System.out.println(Character.isEmojiPresentation(heart));        // false
```

Một code point có thuộc tính `Emoji` không đồng nghĩa nó luôn được hiển thị bằng glyph emoji mặc định; `Emoji_Presentation` là thuộc tính riêng. Một emoji người dùng nhìn thấy cũng có thể là chuỗi nhiều code point, ví dụ emoji có skin tone, cờ quốc gia hoặc chuỗi nghề nghiệp ghép bằng zero-width joiner (ZWJ). `Character.isEmoji(int)` không phân tích toàn bộ chuỗi emoji hay grapheme cluster.

## 10. Kiểm tra ký tự có thể dùng trong Java identifier

`Character.isJavaIdentifierStart(int)` kiểm tra một code point có thể đứng đầu Java identifier hay không. `isJavaIdentifierPart(int)` kiểm tra code point có thể xuất hiện ở vị trí tiếp theo.

```java
int letter = 'A';
int underscore = '_';
int digit = '7';

System.out.println(Character.isJavaIdentifierStart(letter));     // true
System.out.println(Character.isJavaIdentifierStart(underscore)); // true
System.out.println(Character.isJavaIdentifierStart(digit));      // false
System.out.println(Character.isJavaIdentifierPart(digit));       // true
```

Các method này chỉ kiểm tra từng code point. Nếu muốn kiểm tra toàn bộ chuỗi theo hình dạng identifier, phải xác nhận code point đầu bằng `isJavaIdentifierStart` và các code point còn lại bằng `isJavaIdentifierPart`.

Trong module `java.compiler`, `javax.lang.model.SourceVersion` cung cấp kiểm tra cấp chuỗi:

```java
import javax.lang.model.SourceVersion;

String name = "đơnHàng2026";

boolean identifierOrKeyword = SourceVersion.isIdentifier(name);
boolean keyword = SourceVersion.isKeyword(name);
boolean usableAsIdentifier = identifierOrKeyword && !keyword;

System.out.println(usableAsIdentifier);
```

Lưu ý: `SourceVersion.isIdentifier()` trả `true` cho cả identifier hợp lệ lẫn keyword, boolean literal và `null` literal; vì vậy nếu cần một tên có thể dùng làm identifier, hãy loại keyword bằng `isKeyword()` hoặc dùng parser/compiler cho ngữ cảnh ngôn ngữ đầy đủ. Contextual keyword còn phụ thuộc vị trí cú pháp.

Không dùng các method cũ `isJavaLetter()` và `isJavaLetterOrDigit()` trong mã mới: chúng đã deprecated và được thay bằng `isJavaIdentifierStart()`/`isJavaIdentifierPart()`.

## 11. Ví dụ tổng hợp: in thuộc tính từng code point

Ví dụ sau duyệt một chuỗi và in tên, category, script, block, các thuộc tính chữ/số/khoảng trắng, numeric value và emoji property. Mọi thao tác đều dùng `int codePoint`, nên hỗ trợ supplementary characters.

```java
public class CharacterInspector {
    private CharacterInspector() {}

    static String categoryName(int type) {
        return switch (type) {
            case Character.UPPERCASE_LETTER -> "UPPERCASE_LETTER";
            case Character.LOWERCASE_LETTER -> "LOWERCASE_LETTER";
            case Character.TITLECASE_LETTER -> "TITLECASE_LETTER";
            case Character.MODIFIER_LETTER -> "MODIFIER_LETTER";
            case Character.OTHER_LETTER -> "OTHER_LETTER";
            case Character.NON_SPACING_MARK -> "NON_SPACING_MARK";
            case Character.COMBINING_SPACING_MARK -> "COMBINING_SPACING_MARK";
            case Character.DECIMAL_DIGIT_NUMBER -> "DECIMAL_DIGIT_NUMBER";
            case Character.LETTER_NUMBER -> "LETTER_NUMBER";
            case Character.OTHER_NUMBER -> "OTHER_NUMBER";
            case Character.SPACE_SEPARATOR -> "SPACE_SEPARATOR";
            case Character.LINE_SEPARATOR -> "LINE_SEPARATOR";
            case Character.PARAGRAPH_SEPARATOR -> "PARAGRAPH_SEPARATOR";
            case Character.MATH_SYMBOL -> "MATH_SYMBOL";
            case Character.CURRENCY_SYMBOL -> "CURRENCY_SYMBOL";
            case Character.OTHER_SYMBOL -> "OTHER_SYMBOL";
            case Character.FORMAT -> "FORMAT";
            case Character.CONTROL -> "CONTROL";
            case Character.UNASSIGNED -> "UNASSIGNED";
            default -> "CATEGORY_" + type;
        };
    }

    static void inspect(String text) {
        text.codePoints().forEach(cp -> {
            String name = Character.getName(cp);
            Character.UnicodeBlock block = Character.UnicodeBlock.of(cp);
            Character.UnicodeScript script = Character.UnicodeScript.of(cp);

            System.out.printf(
                    "U+%04X %-32s type=%-24s script=%-12s block=%-28s "
                            + "letter=%-5s alphabetic=%-5s digit=%-5s "
                            + "white=%-5s space=%-5s numeric=%-3d emoji=%s%n",
                    cp,
                    name == null ? "(unassigned)" : name,
                    categoryName(Character.getType(cp)),
                    script,
                    block == null ? "(none)" : block,
                    Character.isLetter(cp),
                    Character.isAlphabetic(cp),
                    Character.isDigit(cp),
                    Character.isWhitespace(cp),
                    Character.isSpaceChar(cp),
                    Character.getNumericValue(cp),
                    Character.isEmoji(cp)
            );
        });
    }

    public static void main(String[] args) {
        inspect("A đ 中 ١ Ⅻ 😀");
    }
}
```

Kết quả sẽ có một dòng cho mỗi code point, không phải mỗi UTF-16 `char`. Với ký tự không có numeric value, cột `numeric` là `-1`; với ký tự có giá trị số không thể biểu diễn bằng số nguyên không âm, kết quả là `-2`.

## 12. Unicode version ảnh hưởng kết quả tra cứu

Các thuộc tính trong `Character` dựa trên Unicode Character Database đi kèm JDK. Khi Unicode bổ sung ký tự mới hoặc thay đổi property, kết quả `isDefined`, `getType`, `getName`, `isEmoji`, `UnicodeScript` và các method liên quan có thể khác giữa các JDK release.

| Java release | Unicode version được `Character` sử dụng |
| --- | --- |
| JDK 25 | Unicode 16.0 |
| JDK 26 | Unicode 17.0 |
| JDK 27 | Unicode 17.0 |

Nếu ứng dụng cần xử lý một code point mới được thêm vào Unicode 17, chạy trên JDK 25 có thể trả `UNASSIGNED`, còn JDK 26/27 nhận diện theo dữ liệu Unicode 17.0. Vì vậy, khi kiểm thử hoặc nâng cấp JDK, cần kiểm tra lại các quy tắc phân loại văn bản nếu nghiệp vụ phụ thuộc Unicode properties.

`Character` thuộc module `java.base`, package `java.lang`, được tự động import. Không cần `--enable-preview` hoặc `--add-modules` để dùng API này. `SourceVersion` thuộc module `java.compiler`; nếu ứng dụng chạy runtime image tùy chỉnh bằng `jlink` và sử dụng `SourceVersion`, cần bảo đảm image có module `java.compiler`.

## 13. Những lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Duyệt `String` bằng `charAt()` rồi gọi `isLetter(char)` | Supplementary character bị tách thành hai surrogate | Dùng `codePoints()` và overload nhận `int` |
| Dùng `length()` để đếm ký tự Unicode | `length()` đếm UTF-16 code unit | Dùng `codePointCount()` nếu cần số code point |
| Xem `isAlphabetic` và `isLetter` là giống nhau | `isAlphabetic` bao gồm `LETTER_NUMBER` và `Other_Alphabetic` | Chọn đúng predicate hoặc kiểm tra `getType()` |
| Xem `isDigit` là mọi ký tự có numeric value | Roman numeral và phân số Unicode không thuộc decimal digit | Dùng `getNumericValue` hoặc `digit` theo mục tiêu |
| Dùng `isWhitespace` để tìm mọi loại space | Non-breaking spaces không được method này xem là whitespace | Cân nhắc `isSpaceChar` và quy tắc input |
| Dùng UnicodeBlock để nhận diện ngôn ngữ | Block là vùng code point, không phải script/ngôn ngữ | Dùng `UnicodeScript` khi cần thuộc tính script |
| Dùng `getDirectionality` để đảo chuỗi RTL | Method chỉ trả bidi class từng code point | Để bidi engine thực hiện Unicode Bidirectional Algorithm |
| Dùng `isEmoji` để nhận diện emoji hiển thị hoàn chỉnh | Emoji có thể là chuỗi nhiều code point | Xử lý grapheme/emoji sequence theo Unicode Emoji spec |
| Dùng `isJavaIdentifierStart` cho toàn chuỗi | Method chỉ kiểm tra một code point đầu | Duyệt toàn chuỗi hoặc dùng `SourceVersion`/compiler API |
| Giả định mọi JDK dùng cùng Unicode database | Unicode version thay đổi theo Java release | Ghi rõ JDK/Unicode version trong test và deployment |

## Ghi nhớ

- `Character` cung cấp các thuộc tính Unicode như category, alphabetic, digit, whitespace, script, block, numeric value, directionality và emoji.
- `char` là UTF-16 code unit; `int codePoint` đại diện đầy đủ Unicode code point. Dùng overload `int` để hỗ trợ supplementary characters.
- Duyệt chuỗi bằng `String.codePoints()` thay vì giả định mỗi `char` là một ký tự hoàn chỉnh.
- `getType()` trả general category; `isLetter`, `isAlphabetic`, `isDigit` có quy tắc khác nhau.
- `getNumericValue()` và `digit(codePoint, radix)` phục vụ hai mục tiêu khác nhau.
- `isWhitespace()` loại trừ một số non-breaking spaces mà `isSpaceChar()` vẫn nhận diện.
- `UnicodeScript` mô tả script; `UnicodeBlock` mô tả block code point.
- `getDirectionality()` không thay thế Unicode Bidirectional Algorithm; `isEmoji()` không nhận diện cả grapheme sequence.
- JDK 26/27 dùng Unicode 17.0; kết quả tra thuộc tính phụ thuộc Unicode data của JDK.
- `Character` là API ổn định trong `java.base`, không cần preview flag.

## Tài liệu tham khảo

- [Character, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html) — Unicode 17.0, code point, general category và các method tra thuộc tính.
- [Character, Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Character.html) — xác nhận Unicode 17.0 và API tiếp tục có trong JDK 27.
- [Character.UnicodeScript, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.UnicodeScript.html) — các giá trị script và method `of(int)`.
- [Character.UnicodeBlock, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.UnicodeBlock.html) — tra block và trường hợp trả `null`.
- [SourceVersion, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/lang/model/SourceVersion.html) — kiểm tra identifier, keyword và qualified name.
- [Unicode Character Database](https://www.unicode.org/reports/tr44/) — định nghĩa dữ liệu Unicode và general category.
- [Unicode Standard Annex #24 — Unicode Script Property](https://www.unicode.org/reports/tr24/) — định nghĩa Unicode Script.
- [Unicode Standard Annex #9 — Unicode Bidirectional Algorithm](https://www.unicode.org/reports/tr9/) — thuật toán hiển thị văn bản hỗn hợp LTR/RTL.
- [Unicode Technical Standard #51 — Unicode Emoji](https://www.unicode.org/reports/tr51/) — Emoji property và chuỗi emoji.
