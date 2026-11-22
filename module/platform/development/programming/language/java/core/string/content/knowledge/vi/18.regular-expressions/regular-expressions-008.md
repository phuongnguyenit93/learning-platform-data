# Ký tự Unicode, ranh giới từ và cụm ký tự trong Java regex

## 1. Vì sao regex với Unicode khác regex chỉ xử lý ASCII?

Một `Java String` lưu chuỗi dưới dạng các **đơn vị mã UTF-16** (`char`). Trong Unicode, cần phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Code unit** | Một đơn vị UTF-16, là thứ `String.length()` đếm. | Emoji `😀` (U+1F600) cần **2** `char` (surrogate pair). |
| **Code point** | Một giá trị ký tự Unicode, có thể cần 1 hoặc 2 code unit UTF-16. | `e` + dấu sắc kết hợp U+0301 là **2** code point. |
| **Extended grapheme cluster** | Một cụm code point thường được người đọc cảm nhận là một đơn vị ký tự. | `e` + U+0301 thường là **1** cụm; emoji `👩‍💻` là một cụm ghép bằng ZWJ. |

Một ký tự nhìn thấy trên màn hình **không nhất thiết tương ứng với một `char` hay một code point**. Ngay cả một grapheme cluster cũng không bảo đảm chiếm đúng một ô hiển thị, vì độ rộng và cách kết xuất phụ thuộc font/giao diện.

Trong `java.util.regex.Pattern`, regex hiểu các thuộc tính Unicode qua `\p{...}` và `\P{...}`; nhận diện ranh giới từ bằng `\b`, `\B`; và hỗ trợ **extended grapheme cluster** bằng `\X` cùng ranh giới `\b{g}` (Java 9+). Đây là những khái niệm khác nhau và phục vụ mục đích khác nhau.

## 2. Viết regex trong chuỗi Java: hai lớp escape

Regex là một ngôn ngữ nằm **bên trong** chuỗi Java. Khi viết trực tiếp bằng Java string literal, dấu gạch chéo ngược trong regex phải được escape thêm lần nữa:

| Ý định | Regex | String literal trong Java |
| --- | --- | --- |
| Một chữ cái Unicode | `\p{L}` | `"\\p{L}"` |
| Ranh giới từ | `\b` | `"\\b"` |
| Một cụm grapheme | `\X` | `"\\X"` |
| Ranh giới grapheme | `\b{g}` | `"\\b{g}"` |
| Code point U+1F600 | `\x{1F600}` | `"\\x{1F600}"` |

**Cẩn thận:** `"\b"` trong mã Java biểu diễn **ký tự backspace**, không phải regex word boundary. Tương tự, `"\p{L}"` không phải string literal Java hợp lệ vì `\p` không phải escape của Java.

`Pattern.compile(regex).matcher(text).find()` tìm một đoạn khớp; `matcher.matches()` yêu cầu **toàn bộ vùng tìm kiếm** khớp. Với biểu thức dùng thường xuyên, nên biên dịch `Pattern` một lần để tái sử dụng.

## 3. Chọn ký tự theo thuộc tính Unicode

### 3.1. General category và nhãn Unicode

`\p{...}` khớp ký tự mang thuộc tính; `\P{...}` khớp ký tự **không** có thuộc tính tương ứng.

| Biểu thức | Ý nghĩa | Tình huống dùng |
| --- | --- | --- |
| `\p{L}` | Nhóm **Letter**: chữ cái thuộc nhiều ngôn ngữ. | Tìm chữ cái, thay vì giới hạn `[A-Za-z]`. |
| `\p{Lu}`, `\p{Ll}` | Chữ hoa / chữ thường theo Unicode category. | Kiểm tra loại chữ. |
| `\p{M}` | **Mark**, gồm các dấu kết hợp (`Mn`, `Mc`, `Me`). | Giữ dấu khi xử lý chuỗi ở dạng decomposed. |
| `\p{N}`, `\p{Nd}` | Số nói chung / chữ số thập phân. | Phân biệt `Ⅳ` thuộc nhóm số với chữ số thập phân. |
| `\p{Sc}` | Ký hiệu tiền tệ. | Phát hiện các ký hiệu như `€` hay `$`. |
| `\p{IsAlphabetic}` | Thuộc tính nhị phân Alphabetic. | Định nghĩa rộng hơn một số kiểu ký tự loại `L`. |
| `\P{L}` | Một code point không thuộc nhóm chữ cái. | Tìm ký tự nằm ngoài nhóm Letter. |

Ví dụ:

```java
Pattern letters = Pattern.compile("\\p{L}+");
Pattern lettersAndMarks = Pattern.compile("\\p{L}[\\p{L}\\p{M}]*");

System.out.println(letters.matcher("Việt").matches());       // true
System.out.println(letters.matcher("e\u0301").matches());     // false
System.out.println(lettersAndMarks.matcher("e\u0301").matches()); // true
```

`"Việt"` ở ví dụ đầu chứa chữ có dấu **dạng precomposed**. Còn `"e\u0301"` chứa chữ `e` và một **combining acute accent**. Nếu chỉ dùng `\p{L}+`, dấu kết hợp không thuộc nhóm Letter nên `matches()` trả `false`. Mẫu `\p{L}[\p{L}\p{M}]*` yêu cầu mở đầu bằng chữ và cho phép dấu sau đó; đây là ví dụ kỹ thuật chứ chưa phải định nghĩa đầy đủ của một từ trong ngôn ngữ tự nhiên.

### 3.2. Script khác block

- **Script** (`\p{IsLatin}`, `\p{sc=Greek}`, `\p{script=Hiragana}`) chỉ hệ chữ mà ký tự được gán.
- **Block** (`\p{InGreek}`, `\p{blk=Greek}`) là một **khoảng mã** Unicode, có thể chứa ký tự khác script hoặc ký tự chưa được gán.
- **Category** (`\p{L}`, `\p{Lu}`) phân loại theo tính chất ký tự, độc lập với script.

Ví dụ `\p{sc=Greek}+` diễn đạt **script Greek**; `\p{InGreek}+` diễn đạt các code point nằm trong **block Greek**. Hai tập này không thể thay thế cho nhau trong mọi tình huống. Khi lọc văn bản tiếng Việt, `\p{IsLatin}` cũng không tự động bảo đảm bao gồm mọi dấu kết hợp đi kèm, vì mark có thể mang script `Inherited`.

Java regex hỗ trợ phép giao/trừ tập trong character class, ví dụ `[\p{L}&&[^\p{Lu}]]` là ký tự loại Letter nhưng không thuộc category Uppercase Letter.

## 4. `\w`, `\d`, `\s` và chế độ Unicode

Mặc định theo Java 17, các lớp dựng sẵn chủ yếu dựa trên ASCII: `\w` tương đương `[a-zA-Z_0-9]`, `\d` là `[0-9]`, `\s` gồm các khoảng trắng ASCII thông dụng. Vì vậy `\w+` **không** tự động nhận toàn bộ chữ tiếng Việt.

Bật cờ `Pattern.UNICODE_CHARACTER_CLASS` (inline là `(?U)`) khi muốn các lớp dựng sẵn và các lớp POSIX dùng quy tắc Unicode:

```java
Pattern asciiWord = Pattern.compile("\\w+");
Pattern unicodeWord = Pattern.compile("\\w+", Pattern.UNICODE_CHARACTER_CLASS);
Pattern inlineUnicodeWord = Pattern.compile("(?U)\\w+");

System.out.println(asciiWord.matcher("đèn").matches());        // false
System.out.println(unicodeWord.matcher("đèn").matches());      // true
System.out.println(inlineUnicodeWord.matcher("đèn").matches()); // true
```

Trong Unicode mode, `\w` bao gồm chữ cái alphabetic, chữ số thập phân, combining marks, connector punctuation và một số ký tự điều khiển nối (`Join_Control`). Do đó `\w` **không đồng nghĩa** với “chữ cái”, “identifier Java hợp lệ” hay “từ có nghĩa”. Tùy yêu cầu:

- Chỉ chữ cái theo category: `\p{L}+`.
- Chữ kèm dấu kết hợp: `\p{L}[\p{L}\p{M}]*`.
- Token kiểu word, có thể chứa số, gạch dưới và mark: `(?U)\w+`.
- Kiểm tra identifier Java thực sự: cân nhắc `Character.isJavaIdentifierStart`/`isJavaIdentifierPart` trên **code point**, hoặc parser tương ứng; regex `\w+` chưa đủ.

Bật `UNICODE_CHARACTER_CLASS` cũng hàm ý `UNICODE_CASE`. Ngược lại, `Pattern.UNICODE_CASE` (inline `(?u)`) chỉ điều chỉnh cách so khớp **không phân biệt hoa/thường** khi kết hợp `CASE_INSENSITIVE`; `(?u)` tự nó không biến `\w` thành lớp Unicode. Phân biệt `u` chữ thường và `U` chữ hoa.

## 5. Ranh giới từ `\b` và `\B`

`\b` là **zero-width assertion**: kiểm tra một *vị trí* ở ranh giới từ, không tiêu thụ ký tự. `\B` kiểm tra vị trí **không** phải ranh giới từ.

```java
String text = "café_42, đèn!";
Matcher words = Pattern.compile("(?U)\\b\\w+\\b").matcher(text);
while (words.find()) {
    System.out.println(words.group());
}
```

Kết quả:

```text
café_42
đèn
```

Giải thích: `(?U)` chọn ngữ nghĩa Unicode của `\w`; `\b` ở hai đầu kiểm tra ranh giới, còn `\w+` **tiêu thụ** các ký tự của token. Gạch dưới và chữ số có thể nằm trong cùng một token, nên `café_42` là một kết quả. Muốn chỉ lấy chữ và dấu, cần mô tả tập ký tự riêng, không chỉ bao quanh `\w+` bằng `\b`.

**Không nhầm `\b` với trình phân tích từ cho ngôn ngữ tự nhiên**: dấu gạch nối, dấu nháy, hashtag, emoji, tiếng Thái không có khoảng trắng tách từ, hoặc tiếng Việt nhiều âm tiết đều cần quy tắc phân đoạn phù hợp. `\b` không quyết định một “từ” theo từ điển hay ngữ pháp. Sử dụng `(?U)` nhất quán giúp tránh các giả định ASCII không mong muốn khi ghép `\b` với `\w`; đừng dựa vào việc từng phiên bản JDK xử lý chi tiết ranh giới giống hệt một tokenizer ngôn ngữ.

## 6. Cụm grapheme với `\X` và `\b{g}`

Một **extended grapheme cluster** có thể gồm một hoặc nhiều code point: chữ + dấu kết hợp, chuỗi emoji ghép bằng zero-width joiner (ZWJ), hoặc cặp regional indicators tạo lá cờ.

| Regex | Vai trò | Có tiêu thụ ký tự? |
| --- | --- | --- |
| `\X` | Khớp **một cụm grapheme mở rộng**. | Có |
| `\b{g}` | Kiểm tra **ranh giới giữa các cụm grapheme**. | Không |
| `\b` | Kiểm tra ranh giới **word**. | Không |
| `.` | Khớp một đơn vị regex; **không** phải cách đáng tin để đếm cụm grapheme. | Có |

Ví dụ chuỗi `"e\u0301👩‍💻"` gồm **7 UTF-16 code unit**, **5 code point**, nhưng chỉ **2 grapheme cluster**: cụm `e + U+0301` và cụm emoji `woman technologist`. Với regex `\X`, hai lần `find()` trả hai cụm. `\b{g}` xác định vị trí UTF-16 ở các offset `0`, `2`, `7`. Trái lại, `\b` diễn đạt ranh giới từ và không dùng thay `\b{g}`.

Có thể dùng `\X` khi muốn đi qua chuỗi theo các đơn vị ký tự mà người dùng thường nhận biết, chẳng hạn kiểm tra giới hạn *số cụm grapheme* hoặc cắt chuỗi ở ranh giới cluster. Tuy vậy, phân cụm Unicode không thay thế xử lý hiển thị/phông chữ, cũng không bảo đảm một cluster là “một chữ” của ngôn ngữ học.

### 6.1. Vị trí `Matcher.start()`/`end()` vẫn là UTF-16

Ngay cả khi regex `\X` ghép cả emoji thành một cụm, các chỉ số `Matcher.start()`, `Matcher.end()`, `String.substring(...)` vẫn tính theo **UTF-16 code unit**, với `end()` là giới hạn loại trừ (*exclusive*). Đừng tăng một offset bằng 1 rồi cho rằng đã đi qua một code point hay một grapheme.

Muốn đếm code point: `s.codePointCount(0, s.length())`. Muốn đi qua code point: `s.codePoints()` hoặc `s.offsetByCodePoints(...)`. Muốn đi qua **grapheme**: dùng `Pattern.compile("\\X").matcher(s)` với `find()`. Không cắt chuỗi ở giữa surrogate pair hoặc cụm dấu/emoji khi mục tiêu là giữ nguyên ký tự người dùng thấy.

## 7. Ví dụ Java 17+ độc lập, chạy được

Lưu **nguyên chương trình** sau thành `UnicodeRegexDemo.java`. Mã dùng escape Unicode trong những chuỗi đặc biệt để thể hiện rõ cấu trúc ký tự và chạy nhất quán ngay cả khi terminal không thuận tiện nhập emoji.

```java
import java.text.Normalizer;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class UnicodeRegexDemo {
    public static void main(String[] args) {
        String decomposed = "e\u0301";
        String womanTechnologist = "\uD83D\uDC69\u200D\uD83D\uDCBB";
        String sample = decomposed + womanTechnologist;

        System.out.println("UTF-16 units: " + sample.length());
        System.out.println("Code points: "
                + sample.codePointCount(0, sample.length()));

        Matcher clusters = Pattern.compile("\\X").matcher(sample);
        while (clusters.find()) {
            System.out.printf("Grapheme: [%d,%d)%n",
                    clusters.start(), clusters.end());
        }

        Matcher boundaries = Pattern.compile("\\b{g}").matcher(sample);
        System.out.print("Grapheme boundaries:");
        while (boundaries.find()) {
            System.out.print(" " + boundaries.start());
        }
        System.out.println();

        System.out.println("ASCII word đ: "
                + Pattern.compile("\\w+").matcher("\u0111").matches());
        System.out.println("Unicode word đ: "
                + Pattern.compile("(?U)\\w+").matcher("\u0111").matches());
        System.out.println("NFD all letters: "
                + Pattern.compile("\\p{L}+").matcher(decomposed).matches());
        System.out.println("NFD letters and marks: "
                + Pattern.compile("\\p{L}[\\p{L}\\p{M}]*")
                        .matcher(decomposed).matches());

        Matcher words = Pattern.compile("(?U)\\b\\w+\\b")
                .matcher("caf\u00e9_42, \u0111\u00e8n!");
        while (words.find()) {
            System.out.println("Word: " + words.group());
        }

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println("NFC equals é: "
                + normalized.equals("\u00e9"));
    }
}
```

Biên dịch/chạy:

```bash
javac UnicodeRegexDemo.java
java UnicodeRegexDemo
```

Kết quả chuẩn (UTF-8 output):

```text
UTF-16 units: 7
Code points: 5
Grapheme: [0,2)
Grapheme: [2,7)
Grapheme boundaries: 0 2 7
ASCII word đ: false
Unicode word đ: true
NFD all letters: false
NFD letters and marks: true
Word: café_42
Word: đèn
NFC equals é: true
```

Ba phép đếm **7 / 5 / 2** lần lượt nói về code unit, code point và grapheme cluster. Các offset `[0,2)`, `[2,7)` thể hiện hai cụm, không phải hai `char`. Kết quả token tiếng Việt chứng minh chế độ Unicode cho `\w` trong regex này; hai phép kiểm tra NFD chứng minh lý do cần xét combining marks.

## 8. Chuẩn hóa Unicode, so khớp hoa/thường và giới hạn

### NFC và NFD: hai cách biểu diễn cùng hình thức chữ

`"é"` có thể là U+00E9 (precomposed) hoặc U+0065 + U+0301 (decomposed). Hai chuỗi đó có thể nhìn giống nhau nhưng không bằng nhau qua `String.equals()` và không nhất thiết khớp cùng một pattern literal. Khi cần so khớp một cách nhất quán, **chuẩn hóa cả dữ liệu lẫn tiêu chí tìm kiếm**:

```java
import java.text.Normalizer;

String a = "\u00E9";
String b = "e\u0301";
String left = Normalizer.normalize(a, Normalizer.Form.NFC);
String right = Normalizer.normalize(b, Normalizer.Form.NFC);
System.out.println(left.equals(right)); // true
```

`Normalizer.Form.NFC` thường phù hợp khi muốn chuẩn hóa về dạng kết hợp. `NFD` tách canonical decomposition. Java còn có `Pattern.CANON_EQ` để đối sánh tương đương chuẩn tắc, nhưng cờ này có thể gây chi phí đáng kể; nên kiểm soát chuẩn hóa đầu vào trước nếu mục tiêu là so khớp văn bản theo cùng một dạng lưu trữ.

### Unicode case folding

`Pattern.CASE_INSENSITIVE` riêng lẻ mặc định ưu tiên ASCII; thêm `Pattern.UNICODE_CASE` (hoặc `(?iu)`) để đối sánh hoa/thường theo Unicode. Đây là **case-insensitive matching**, không phải bước chuẩn hóa NFC/NFD và cũng không phải bảo đảm mọi phép chuyển chữ hoa/thường đặc thù từng locale. Các thao tác chuẩn hóa/case folding có thể làm thay đổi chuỗi và vị trí, nên cần chọn thứ tự xử lý nhất quán trước khi ghi nhận offset.

### Những sai lầm hay gặp

1. Dùng `String.length()` để giới hạn “số ký tự người dùng nhìn thấy”; thực tế nó đếm UTF-16 code unit. Nếu sản phẩm cần giới hạn grapheme, hãy đếm `\X`.
2. Dùng `\w+` mặc định rồi kết luận chữ có dấu “không hợp lệ”; thay bằng `(?U)\w+` hoặc biểu thức `\p{...}` đúng chính sách.
3. Dùng `\p{L}+` cho chữ decomposed mà quên `\p{M}`; dẫn tới mất/loại dấu kết hợp.
4. Dùng `\b` như bộ tách từ tiếng Việt/Thái hay như ranh giới emoji; mục tiêu đó cần logic ngôn ngữ hoặc `\b{g}`/`\X` tương ứng.
5. Lấy chỉ số `Matcher.start()` làm vị trí code point hoặc grapheme; thực tế là UTF-16.
6. Cho rằng NFC, cờ `(?U)` hay `(?iu)` loại được **ký tự giả mạo (confusables)** hoặc mọi zero-width character; kiểm tra nhận dạng/định danh cần chính sách riêng.
7. Ghép thẳng dữ liệu người dùng vào regex; nếu tìm nguyên văn, dùng `Pattern.quote(userInput)` để tránh metacharacter hoạt động ngoài ý muốn.

## 9. Chọn công cụ theo mục tiêu

| Mục tiêu | Cách làm gợi ý |
| --- | --- |
| Chỉ kiểm tra một code point thuộc loại chữ/số/dấu | `\p{L}`, `\p{Nd}`, `\p{M}` hoặc API `Character`. |
| Tìm token gồm chữ, số, dấu kết hợp và gạch dưới | `(?U)\b\w+\b` rồi bổ sung quy tắc nghiệp vụ. |
| Duyệt từng code point | `String.codePoints()`; giữ nguyên cặp surrogate. |
| Duyệt từng cụm ký tự mở rộng | `Matcher` với `\X`. |
| Xác định vị trí giữa cụm grapheme | Assertion `\b{g}`. |
| So khớp chuỗi có thể khác dạng tổ hợp dấu | Chuẩn hóa `Normalizer` về cùng NFC/NFD trước. |
| Chia từ theo quy tắc ngôn ngữ cụ thể | `BreakIterator.getWordInstance(locale)` để bắt đầu, hoặc thư viện NLP/ICU4J khi cần phân đoạn chính xác theo ngôn ngữ. |

**Ghi nhớ:** **thuộc tính Unicode** trả lời “ký tự thuộc nhóm nào?”, **word boundary** trả lời “vị trí này có phải ranh giới token theo quy tắc regex?”, còn **grapheme cluster** trả lời “những code point nào đi cùng nhau thành một cụm ký tự?”. Việc chọn đúng tầng giúp regex xử lý chính xác tiếng Việt có dấu, emoji và các hệ chữ khác.

### Tài liệu tham khảo

- [Java SE 17 — `java.util.regex.Pattern`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): Unicode Support, character classes, boundary matchers, `UNICODE_CHARACTER_CLASS`, `UNICODE_CASE`.
- [Java SE 17 — `java.text.Normalizer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFD và so khớp canonical equivalence.
- [Java SE 17 — `java.lang.String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): UTF-16, `codePointCount` và offset theo code point.
