# Phân biệt ranh giới từ với các đoạn dấu câu hoặc khoảng trắng trong Java

## 1. Một ranh giới từ không có nghĩa đoạn tiếp theo luôn là một từ

Giả sử ứng dụng hiển thị câu:

```text
Hello, world! 42 days.
```

Người đọc có thể nhận ra các từ `Hello`, `world`, `days` và số `42`. Nhưng ở mức xử lý văn bản, các phần khác như dấu phẩy, dấu chấm than, dấu chấm và khoảng trắng **cũng chiếm vị trí trong chuỗi**.

Java cung cấp `java.text.BreakIterator.getWordInstance(locale)` để tìm **vị trí ranh giới theo quy tắc từ** của ngôn ngữ. Điều thường khiến người mới nhầm lẫn là: **mỗi đoạn nằm giữa hai ranh giới liên tiếp không bắt buộc là một từ**. Nó có thể là:

- từ hoặc đoạn chứa chữ cái;
- đoạn số, chẳng hạn `42` hoặc `3.14` tùy quy tắc;
- dấu câu, chẳng hạn `,`, `!`, `.`;
- khoảng trắng, tab hay các đoạn phân cách khác;
- ký hiệu hoặc nội dung không được xem là một từ theo chính sách ứng dụng.

Nói cách khác, `BreakIterator` phát hiện **ranh giới**, chứ `getWordInstance` không phải một hàm trả sẵn `List<String>` chỉ gồm các từ có nghĩa.

Đây là khác biệt quan trọng khi xây bộ đếm từ, tìm kiếm, chọn từ bằng double-click, tô sáng, tách văn bản theo locale và xử lý tiếng Việt hoặc ngôn ngữ không phân cách từ bằng dấu cách theo cách đơn giản.

## 2. Ba khái niệm phải phân biệt

| Khái niệm | Ý nghĩa | Ví dụ trong `Hello, world!` |
| --- | --- | --- |
| **Ranh giới từ (word boundary)** | Vị trí có thể bắt đầu hoặc kết thúc một đơn vị theo quy tắc phân đoạn từ | Trước/sau `Hello`, trước/sau dấu phẩy, trước/sau `world` |
| **Đoạn giữa hai ranh giới (segment)** | Chuỗi con từ index bắt đầu tới index kết thúc | `Hello`, `,`, ` `, `world`, `!` |
| **Từ/token ứng dụng muốn giữ** | Đoạn được chọn **sau khi áp dụng chính sách lọc** | `Hello`, `world`; tùy bài toán có nhận số hoặc ký hiệu |

Ví dụ, khi `BreakIterator` trả ranh giới tại index 5, index 6 và index 7 cho phần `Hello, `, các đoạn tương ứng là:

```text
[0, 5)  "Hello"
[5, 6)  ","
[6, 7)  " "
```

Các index ở đây là **offset UTF-16**, theo đúng cách đánh chỉ số của `String.substring(begin, end)`. Khoảng `[start, end)` lấy ký tự từ `start` đến trước `end`. Mỗi ranh giới chỉ đánh dấu vị trí; **không gắn nhãn đoạn là từ, dấu câu hay khoảng trắng**.

Điều quan trọng hơn là phân đoạn “từ” khác với khái niệm **từ vựng/ngữ nghĩa**. Ví dụ tiếng Việt `học sinh` có khoảng trắng giữa hai âm tiết nhưng có thể là một đơn vị từ vựng trong ngữ cảnh. Một thuật toán word boundary không tự thực hiện đầy đủ phân tích ngữ nghĩa, từ ghép, tên riêng hay phân tích ngôn ngữ tự nhiên.

## 3. BreakIterator: công cụ xác định vị trí ngắt văn bản

`BreakIterator` là lớp trừu tượng trong `java.text`:

```java
import java.text.BreakIterator;
import java.util.Locale;

BreakIterator iterator =
        BreakIterator.getWordInstance(Locale.US);
iterator.setText("Hello, world! 42 days.");
```

Đây là snippet. Java có nhiều factory cùng kiểu iterator nhưng phục vụ các đơn vị khác nhau:

| Factory | Loại ranh giới cần tìm | Ví dụ ứng dụng |
| --- | --- | --- |
| `getWordInstance(locale)` | Ranh giới **theo từ**, bao gồm các đoạn nằm giữa từ | Chọn từ, tìm từ, tô sáng |
| `getSentenceInstance(locale)` | Ranh giới **câu** | Chia đoạn để đọc/tổng hợp câu |
| `getLineInstance(locale)` | Vị trí có thể **ngắt dòng** | Bố cục văn bản khi có giới hạn chiều rộng |
| `getCharacterInstance(locale)` | Ranh giới **ký tự theo phân đoạn văn bản** | Di chuyển con trỏ, chọn cụm ký tự |

**Không thay `getWordInstance` bằng `getCharacterInstance`** chỉ vì các từ được tạo từ ký tự: một từ có thể gồm nhiều ký tự; một ký tự hiển thị lại có thể gồm nhiều code point. Tương tự, `getLineInstance` cho biết các vị trí thích hợp để xuống dòng, không có nghĩa mỗi đoạn giữa hai ranh giới là một từ.

Tài liệu Java nhấn mạnh `BreakIterator` được thiết kế chủ yếu cho **ngôn ngữ tự nhiên**, không phải tokenizer để phân tích mã nguồn của một ngôn ngữ lập trình. Đối với Java source code, JSON, URL, email, SQL hay tên biến, cần parser/lexer có ngữ pháp tương ứng.

## 4. Các API xác định ranh giới: first, next, previous, following

Một iterator giữ **trạng thái vị trí hiện tại**. Những API phổ biến:

| Phương thức/hằng | Công dụng |
| --- | --- |
| `setText(text)` | Đặt văn bản cần xử lý và đặt vị trí đầu |
| `first()` | Chuyển về ranh giới đầu tiên, trả vị trí đó |
| `last()` | Chuyển tới ranh giới cuối cùng |
| `next()` | Tới ranh giới kế tiếp; `DONE` nếu hết |
| `previous()` | Tới ranh giới trước; `DONE` nếu hết |
| `current()` | Lấy vị trí ranh giới hiện tại |
| `following(offset)` | Tìm ranh giới **nằm sau** offset |
| `preceding(offset)` | Tìm ranh giới **nằm trước** offset |
| `isBoundary(offset)` | Xác định offset có phải ranh giới không |
| `BreakIterator.DONE` | Giá trị sentinel khi không còn ranh giới hợp lệ |
| `getText()` | Lấy `CharacterIterator` văn bản đã đặt |

Vòng lặp đúng để lấy **mọi đoạn liên tiếp**:

```java
int start = iterator.first();

for (int end = iterator.next();
     end != BreakIterator.DONE;
     start = end, end = iterator.next()) {

    String segment = text.substring(start, end);
    // Ở đây segment CÓ THỂ là từ, số, dấu câu hoặc khoảng trắng.
}
```

Đoạn này là snippet và giả sử đã có `iterator` cùng `text`. Không gọi `iterator.next()` để lấy “từ tiếp theo” rồi mặc nhiên coi đoạn đó là một từ. Phải đánh giá nội dung đoạn nếu mục tiêu là trích các từ.

Lưu ý `following`/`preceding` tìm **boundary**, không tìm “chữ cái gần nhất”; kết quả có thể là biên của dấu câu hoặc khoảng trắng. Chúng cũng thay đổi vị trí hiện tại của iterator. Khi cần tìm từ bắt đầu sau một offset, phải duyệt qua các đoạn và **bỏ qua đoạn không thỏa điều kiện từ**.

## 5. Ví dụ Java 17+ hoàn chỉnh: giữ cả ranh giới rồi lọc từ

Tạo file **`WordSegmentsDemo.java`**:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class WordSegmentsDemo {
    public static void main(String[] args) {
        String text = "Hello, world! 42 days.";

        BreakIterator boundary =
                BreakIterator.getWordInstance(Locale.US);
        boundary.setText(text);

        List<String> segments = new ArrayList<>();
        List<String> wordLike = new ArrayList<>();

        int start = boundary.first();
        for (int end = boundary.next();
             end != BreakIterator.DONE;
             start = end, end = boundary.next()) {

            String part = text.substring(start, end);
            segments.add("[" + part + "]");

            if (part.codePoints()
                    .anyMatch(Character::isLetterOrDigit)) {
                wordLike.add(part);
            }
        }

        System.out.println("Segments: " + segments);
        System.out.println("Words/numbers: " + wordLike);
        System.out.println("Word count: " + wordLike.size());
        System.out.println("Whitespace split: "
                + Arrays.toString(text.split("\\s+")));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 WordSegmentsDemo.java
java WordSegmentsDemo
```

**Stdout trong môi trường JDK 24 với Locale.US:**

```text
Segments: [[Hello], [,], [ ], [world], [!], [ ], [42], [ ], [days], [.]]
Words/numbers: [Hello, world, 42, days]
Word count: 4
Whitespace split: [Hello,, world!, 42, days.]
```

**Diễn giải từng bước:**

1. `getWordInstance(Locale.US)` thiết lập quy tắc ngắt theo locale cụ thể, không phụ thuộc default locale của JVM.
2. Vòng lặp lấy **toàn bộ** đoạn giữa các ranh giới. Các đoạn `[,]`, `[ ]`, `[!]` và `[.]` chứng minh đầu ra của iterator **không chỉ có từ**.
3. `Character.isLetterOrDigit` trên `codePoints()` là **quy tắc lọc của ứng dụng**: giữ đoạn chứa ít nhất một chữ cái hoặc chữ số. Do đó `42` được giữ.
4. `wordLike.size()` bằng 4 trong ví dụ này, không bằng số `segments`. Đừng gọi `segments.size()` là “số từ”.
5. `String.split("\\s+")` chỉ cắt tại **khoảng trắng phù hợp regex**, nên `Hello,`, `world!` và `days.` vẫn dính dấu câu. Nó **không tương đương** phân đoạn theo word boundaries.

Code dùng `codePoints()` thay vì duyệt `charAt` để tránh chỉ xét nửa surrogate khi có chữ cái hoặc chữ số ngoài BMP. Tuy nhiên, “đoạn có ít nhất một chữ/số” chỉ là một **heuristic**; cách ứng dụng định nghĩa token có thể khác và cần được nêu rõ.

**Lưu ý khi so sánh stdout:** cách chia từ của `BreakIterator` phụ thuộc locale provider và dữ liệu Unicode/JDK. Đây là output của bộ dữ liệu ví dụ trong môi trường thử nghiệm, không phải đặc tả bất biến cho mọi provider hoặc phiên bản JDK.

## 6. Tại sao không chỉ String.split("\\s+")?

`String.split("\\s+")` chia chuỗi ở vị trí **khớp biểu thức whitespace**. Trong Java regex mặc định, `\\s` nhận một lớp whitespace có định nghĩa cụ thể; khi dùng `Pattern.UNICODE_CHARACTER_CLASS`/cờ `(?U)`, phạm vi ký tự phù hợp có thể mở rộng. Tuy nhiên dù cấu hình thế nào, **chỉ chia tại whitespace không thể xử lý đầy đủ dấu câu hoặc cấu trúc từ**.

Ví dụ:

```text
can't, e-mail: 3.14!
```

Chia theo dấu cách có thể cho:

```text
["can't,", "e-mail:", "3.14!"]
```

Các dấu `,`, `:`, `!` vẫn dính vào token. Nếu sau đó bạn tự xóa **tất cả dấu câu**, `can't` có thể thành `cant` hoặc bị tách tùy cách xử lý; `e-mail` mất dấu nối, `3.14` mất dấu thập phân. Dấu câu **không phải lúc nào cũng chỉ là rác**.

Một bước xử lý thực tế có thể là:

1. Dùng `BreakIterator` để lấy boundary theo ngôn ngữ.
2. Phân loại mỗi đoạn theo mục tiêu: chữ/số, khoảng trắng, dấu câu, ký hiệu.
3. Quyết định giữ/bỏ dấu câu tùy ngữ cảnh (tìm kiếm, NLP, parser dữ liệu…).
4. Lưu lại offset nếu cần đánh dấu phần gốc hoặc phục hồi vị trí tìm kiếm.

Đừng viết `replaceAll("\\p{Punct}", "")` vô điều kiện cho dữ liệu tiếng Việt, mã sản phẩm hoặc số thập phân chỉ vì muốn “đếm từ”. Một regex đơn giản có thể không đủ nhận biết dấu câu Unicode, ký tự kết hợp, ngữ pháp từ ghép và dấu phân cách phụ thuộc locale.

## 7. So sánh BreakIterator với regex word boundary và whitespace

Ba phương án hay bị coi là tương đương thực tế có mục đích khác nhau:

| Công cụ | Đầu ra | Đặc điểm |
| --- | --- | --- |
| `BreakIterator.getWordInstance(locale)` | Các **vị trí ngắt** trong chuỗi | Có quy tắc dựa trên locale; đoạn giữa biên có thể là từ hoặc ký hiệu |
| `String.split("\\s+")` | Mảng chuỗi sau khi tách ở whitespace | Đơn giản nhưng giữ dấu câu dính với token |
| `Pattern.compile("\\b\\w+\\b")` | Các match có ký tự “word” giữa word boundaries của regex | Không cùng bộ quy tắc với BreakIterator, có thể tách contractions, số thập phân, dấu nối |
| `Pattern.compile("\\X")` | Các **extended grapheme clusters** | Đếm/duyệt cụm ký tự hiển thị, **không** tìm từ |
| `BreakIterator.getSentenceInstance(locale)` | Ranh giới câu | Không phải ranh giới từ |

Cần phân biệt ký hiệu `\b` trong **Java regex** với backspace trong Java string literal. Viết:

```java
Pattern.compile("\\b\\w+\\b"); // regex word-boundary + word chars
```

Không viết `"\b"` khi ý muốn là regex word boundary: Java sẽ tạo ký tự backspace. Ngoài ra, `\\w` trong Java regex mặc định không có cùng quy tắc với `Character.isLetterOrDigit` cho toàn Unicode; cờ `UNICODE_CHARACTER_CLASS` thay đổi phạm vi một số lớp ký tự nhưng **không biến regex thành BreakIterator theo locale**.

### Ví dụ chạy được thứ hai: dấu câu *ở trong* một đơn vị

Tạo file **`BoundaryComparisonDemo.java`**:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.regex.MatchResult;

public class BoundaryComparisonDemo {
    public static void main(String[] args) {
        String text = "can't, e-mail: 3.14!";

        BreakIterator boundary =
                BreakIterator.getWordInstance(Locale.US);
        boundary.setText(text);

        List<String> segments = new ArrayList<>();
        List<String> wordLike = new ArrayList<>();

        for (int start = boundary.first(), end = boundary.next();
             end != BreakIterator.DONE;
             start = end, end = boundary.next()) {

            String part = text.substring(start, end);
            segments.add("[" + part + "]");
            if (part.codePoints()
                    .anyMatch(Character::isLetterOrDigit)) {
                wordLike.add(part);
            }
        }

        List<String> regexMatches = Pattern
                .compile("\\b\\w+\\b")
                .matcher(text)
                .results()
                .map(MatchResult::group)
                .toList();

        System.out.println("Boundary segments: " + segments);
        System.out.println("Word-like segments: " + wordLike);
        System.out.println("Whitespace split: "
                + Arrays.toString(text.split("\\s+")));
        System.out.println("Regex matches: " + regexMatches);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 BoundaryComparisonDemo.java
java BoundaryComparisonDemo
```

**Ví dụ stdout trên JDK 24 / Locale.US:**

```text
Boundary segments: [[can't], [,], [ ], [e-mail], [:], [ ], [3.14], [!]]
Word-like segments: [can't, e-mail, 3.14]
Whitespace split: [can't,, e-mail:, 3.14!]
Regex matches: [can, t, e, mail, 3, 14]
```

Kết quả minh họa việc word boundary của `BreakIterator` có thể **giữ** apostrophe trong contraction, dấu nối trong từ ghép và dấu chấm trong số thập phân theo quy tắc locale. Trong khi đó regex `\\b\\w+\\b` chỉ khớp từng dãy `\\w` và `split("\\s+")` giữ luôn dấu câu ở cuối. Không có phương pháp nào “đúng cho mọi mục đích” nếu bạn chưa định nghĩa rõ thế nào là một token.

**Quan trọng:** Các chuỗi `can't`, `e-mail`, `3.14` trong ví dụ là tình huống minh họa phụ thuộc quy tắc word-break của JDK/provider. Sản phẩm có thể yêu cầu chính sách khác, ví dụ coi `e-mail` là hai từ hoặc số `3.14` là một literal. Khi cần parser số, URL, email hoặc mã nguồn, không để `BreakIterator` tự quyết định tính hợp lệ của cú pháp.

## 8. Làm sao phân loại một đoạn là từ, dấu câu, khoảng trắng?

Lọc `Character.isLetterOrDigit` chỉ nhằm có một ví dụ **đơn giản** để loại đoạn toàn dấu câu/khoảng trắng. Với sản phẩm thực tế, các lớp đoạn có thể được xác định rõ hơn:

| Nhóm đoạn | Heuristic có thể dùng | Hạn chế |
| --- | --- | --- |
| Có chữ/số | `segment.codePoints().anyMatch(Character::isLetterOrDigit)` | Giữ cả chữ và số; không tự xác thực từ vựng |
| Chỉ khoảng trắng | `segment.codePoints().allMatch(Character::isWhitespace)` | `isWhitespace` không bao trùm mọi ký tự hiển thị như dấu cách theo mọi định nghĩa Unicode |
| Chỉ dấu câu | Kiểm tra `Character.getType(cp)` với các category punctuation | Unicode punctuation có nhiều category; ký hiệu toán/tiền khác punctuation |
| Chứa emoji/ký hiệu | Kiểm tra code point/category hoặc bộ quy tắc biểu tượng | Emoji có thể gồm nhiều code point, variation selector và ZWJ |
| Word token cần giữ | Kết hợp word boundaries với policy riêng | Tùy ngôn ngữ, dữ liệu và mục tiêu |

Ví dụ một hàm lấy **đoạn chứa chữ/số** không mang theo trạng thái toàn cục:

```java
static boolean hasLetterOrDigit(String segment) {
    return segment.codePoints()
            .anyMatch(Character::isLetterOrDigit);
}
```

Đây là **snippet phương thức** đặt trong lớp Java. Nếu chỉ muốn các từ chứa chữ cái mà không nhận số, dùng `Character::isLetter`. Nếu muốn nhận số thập phân, phần trăm, email hoặc hashtags là token, phải có chính sách phân loại riêng.

Không suy ra “segment không có chữ/số ⇒ nó chắc chắn là whitespace”. Nó có thể là emoji, dấu câu, ký hiệu tiền tệ hoặc đoạn chứa chỉ dấu Unicode kết hợp. Cũng không suy ra “segment có chữ ⇒ chắc chắn là một từ độc lập”; một đoạn có thể được xem là thành phần của một tên riêng hoặc từ ghép nhiều âm tiết.

### Giữ các đoạn thay vì vứt ngay

Khi tính năng cần **tô sáng kết quả tìm kiếm**, **chọn văn bản** hoặc **khôi phục chuỗi gốc**, hãy lưu cả vị trí `start` và `end` của mỗi segment. Nếu chỉ giữ `wordLike`, toàn bộ dấu câu/khoảng trắng sẽ biến mất và khó tái tạo chính xác câu gốc.

Một DTO có thể gồm `startInclusive`, `endExclusive`, `text`, `kind`. Sau khi xác định segment có phải word token hay không, có thể xử lý tùy mục tiêu mà không đánh mất vị trí ban đầu.

## 9. Độ lệch chỉ số: BreakIterator trả UTF-16 offsets

Giá trị trả về bởi `first()`, `next()`, `following()` và `preceding()` dùng index trong đối tượng văn bản. Với `String` trong Java, các index tương ứng đơn vị **UTF-16 code unit**, không phải số Unicode code point hoặc grapheme cluster.

Ví dụ:

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";
System.out.println(text.length()); // 4 code units
System.out.println(text.codePointCount(0, text.length())); // 3 code points
```

Đây là snippet. Emoji ở giữa chiếm hai `char`, nên chỉ số bắt đầu của `B` là `3`, không phải `2`. Vì vậy khi cắt segment dùng **trực tiếp**:

```java
String part = text.substring(start, end);
```

Không chuyển `start`/`end` thành “code point count” rồi đem giá trị đó dùng lại làm offset của `substring`. Nếu muốn biểu diễn vị trí dưới dạng code point index, cần có bước quy đổi có chủ đích, ví dụ `codePointCount(0, start)`; ngược lại `offsetByCodePoints` đổi vị trí theo code points về UTF-16 index.

Tương tự, một dấu tiếng Việt có thể tồn tại dạng ký tự precomposed hoặc dạng base character + combining mark. `BreakIterator` làm việc trên một dãy code units với quy tắc Unicode/locale; việc tự cắt bằng số byte hoặc số `char` tùy tiện có thể khiến dấu kết hợp bị tách ra khỏi chữ.

## 10. Phân tích tiếng Việt, ngôn ngữ không cách từ và Unicode

### 10.1. Tiếng Việt: khoảng trắng không luôn tương ứng một từ vựng

Trong tiếng Việt, khoảng trắng thường phân tách **âm tiết**, trong khi nhiều từ vựng gồm hai hay nhiều âm tiết, ví dụ `học sinh`, `công nghệ`, `bàn ghế` trong ngữ cảnh thích hợp. Vì vậy:

- `split("\\s+")` thường tách theo các đoạn có khoảng trắng, **không bảo đảm** tách đúng từ vựng.
- `getWordInstance(Locale.forLanguageTag("vi-VN"))` cung cấp ranh giới văn bản theo locale/provider, **không đồng nghĩa với một mô hình phân tích từ ghép tiếng Việt chuyên dụng**.
- Nếu sản phẩm cần word tokenization cho tìm kiếm/NLP với cụm từ nhiều âm tiết, cân nhắc một **bộ tách từ tiếng Việt** được đánh giá trên dữ liệu thực tế.

### 10.2. Tiếng Thái, Trung Quốc, Nhật Bản

Một số ngôn ngữ không sử dụng khoảng trắng như phương tiện phân cách từ phổ biến. `split("\\s+")` có thể trả **cả câu dài** thay vì các đơn vị nhỏ. `BreakIterator` áp dụng cơ chế word-boundary theo locale và provider, nhưng chất lượng phân đoạn phụ thuộc dữ liệu từ điển/quy tắc được JDK hỗ trợ. Nếu ứng dụng đòi độ chính xác NLP cao, cần thử dữ liệu thực tế và có thể dùng thư viện/tokenizer chuyên biệt.

Không đưa ra một output bất biến cho việc tách từ tiếng Thái/Trung/Nhật khi không cố định phiên bản JDK, Unicode data và provider. Điều bền vững là phải **chọn locale rõ ràng** và **định nghĩa mục tiêu tokenization**.

### 10.3. Dấu kết hợp và Unicode normalization

Hai chuỗi `"\u00E9"` và `"e\u0301"` có thể hiện giống nhau nhưng khác số code point/UTF-16 units. `BreakIterator` phân tích ranh giới của văn bản đầu vào, không có nghĩa nó tự ghi đè text thành `NFC` hoặc `NFD`. Nếu sản phẩm dùng một chính sách normalization, hãy áp dụng theo **hợp đồng dữ liệu**, và cẩn thận vì normalization có thể làm đổi offset.

**Cảnh báo về ánh xạ vị trí:** nếu normalize hoặc lowercase một chuỗi rồi tìm word boundaries trên **chuỗi mới**, các offset có thể **không tương ứng** với chuỗi gốc do độ dài thay đổi. Đừng lấy offset của chuỗi đã biến đổi để `substring` trên chuỗi gốc mà không ánh xạ lại.

## 11. Bẫy khi đếm từ

Câu hỏi “chuỗi có bao nhiêu từ?” có thể có nhiều đáp án nếu chính sách khác nhau:

| Chính sách | Ví dụ `Hello, world! 42 days.` | Kết quả |
| --- | --- | --- |
| Đếm mọi segment của word-boundary iterator | 10 đoạn trong môi trường demo | **10**; không phải số từ |
| Giữ segment có chữ hoặc số | `Hello`, `world`, `42`, `days` | **4** |
| Chỉ giữ segment có chữ | `Hello`, `world`, `days` | **3** |
| Tách bằng `\\s+` | `Hello,`, `world!`, `42`, `days.` | **4**, nhưng chứa dấu câu |
| Đếm token theo từ vựng NLP | Tùy quy tắc ngôn ngữ | Cần mô hình/tiêu chí riêng |

Ví dụ `"   "` có thể sinh một đoạn khoảng trắng khi phân tích boundaries, nhưng phải có **0 từ** theo chính sách chỉ nhận chữ/số. Chuỗi trống có thể không có đoạn giữa các ranh giới, nhưng vẫn có ranh giới bắt đầu/kết thúc theo API. Đừng lấy `iterator.next()` gọi được bao nhiêu lần rồi suy ra số từ mà không kiểm tra nội dung.

Nếu cần báo cáo số từ đáng tin trong một sản phẩm, định nghĩa hợp đồng: có tính số thuần túy không, số thập phân có được giữ nguyên không, dấu nối/apostrophe xử lý ra sao, emoji có tính là token không, từ ghép tiếng Việt tính thế nào. Sau đó mới chọn thuật toán và bộ kiểm thử.

## 12. Các lỗi phổ biến và cách sửa

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Xem mọi `substring(start,end)` là từ | Iterator chỉ trả ranh giới | Lọc/phân loại từng đoạn theo policy |
| Đếm số ranh giới là số từ | Có cả punctuation/whitespace | Đếm đúng các đoạn được chấp nhận |
| Chỉ `split("\\s+")` rồi nghĩ đã bỏ dấu câu | split không loại dấu không phải whitespace | Phân tích token/dấu câu riêng |
| Cắt ở mọi dấu câu | Có thể phá `can't`, `3.14`, `e-mail` | Chọn rule theo ngữ cảnh và locale |
| Xem regex `\\b` là BreakIterator word boundary | Regex và BreakIterator có luật khác | Dùng API phù hợp, kiểm thử cùng dữ liệu |
| Dùng `getCharacterInstance` để lấy từ | Grapheme/character khác word | Chọn `getWordInstance` |
| Truyền `Locale.getDefault()` ngầm | Kết quả khác giữa máy hoặc người dùng | Truyền locale tường minh |
| Cắt string theo code point index thay cho UTF-16 index | `substring` đếm code units | Dùng offset BreakIterator trực tiếp hoặc chuyển đổi đúng |
| Gộp từ tiếng Việt bằng khoảng trắng | Từ vựng có thể nhiều âm tiết | Dùng tokenizer chuyên biệt khi cần NLP |
| Nghĩ mọi số/dấu câu đều là từ hoặc đều không phải từ | Định nghĩa token chưa rõ | Quy định phân loại và viết test |
| Normalize rồi áp offset lên chuỗi gốc | Normalization có thể đổi chiều dài | Lưu ánh xạ index hoặc phân đoạn đúng chuỗi cần tô sáng |
| Dùng BreakIterator để tokenize mã Java/JSON | Không phải lexical grammar parser | Dùng lexer/parser theo ngữ pháp |
| Dùng cùng iterator mutable trên nhiều luồng | Iterator giữ trạng thái hiện tại và text | Tạo instance riêng/copy cho mỗi tác vụ |
| Hardcode exact output phân đoạn cho mọi JDK | Unicode/locale rules có thể cập nhật | Test/gắn phiên bản provider và dữ liệu thực tế |

## 13. Thiết kế hàm lấy từ có offset

Khi xây chức năng tô sáng, nên giữ cả chỉ số lẫn nội dung. Ví dụ dưới đây là **một snippet phương thức** Java 17+ (không phải một class chạy độc lập); cần import `BreakIterator`, `Locale`, `List`, `ArrayList`:

```java
record WordSpan(int start, int end, String text) {}

static List<WordSpan> findWordLikeSpans(
        String source, Locale locale) {

    BreakIterator it = BreakIterator.getWordInstance(locale);
    it.setText(source);

    List<WordSpan> spans = new ArrayList<>();

    for (int start = it.first(), end = it.next();
         end != BreakIterator.DONE;
         start = end, end = it.next()) {

        String segment = source.substring(start, end);
        if (segment.codePoints()
                .anyMatch(Character::isLetterOrDigit)) {
            spans.add(new WordSpan(start, end, segment));
        }
    }
    return spans;
}
```

Trong chương trình thực tế, `record WordSpan` đặt trong lớp hoặc ở top-level thích hợp, không khai báo local record trước một method bên trong một method Java. Các trường `start/end` là UTF-16 offsets trên **source chưa biến đổi**. Khi tô sáng, dùng chính `source.substring(start,end)` để đối chiếu, không dùng một chuỗi đã normalize/lowercase khác.

Hàm trên **không** nhận diện mọi từ vựng phức tạp; đây là một lớp lọc cơ bản để loại đoạn không có chữ/số và giữ span. Ưu điểm là dễ kiểm thử, không mất dấu câu trong nguồn và có thể thay bộ phân loại khi mục tiêu thay đổi.

## 14. Kiểm thử ranh giới từ đúng cách

Một bộ kiểm thử nên kiểm tra cả **tính đầy đủ của các đoạn** và **chính sách phân loại**, chứ không chỉ một con số word count.

| Nhóm dữ liệu | Ví dụ | Điều cần xác minh |
| --- | --- | --- |
| ASCII cơ bản | `Hello, world!` | Dấu phẩy, khoảng trắng, chấm than có đoạn riêng khi rule tách như vậy |
| Không có khoảng trắng | `one,two` | Có thể tách tại dấu câu; whitespace split không đủ |
| Dấu trong từ | `can't`, `e-mail` | Token có thể giữ apostrophe/hyphen theo rule |
| Dấu trong số | `3.14`, `1,000` | Xác định policy về số và phân cách thập phân/nghìn |
| Nhiều khoảng trắng | `a   b` và tab/newline | Không đếm whitespace thành từ |
| Chuỗi chỉ dấu câu | `...?!` | Theo policy chữ/số, word count bằng 0 |
| Chuỗi trống | `""` | Không có token; không out-of-bounds |
| Tiếng Việt | `học sinh, công nghệ` | Phân biệt âm tiết với từ vựng và chữ có dấu |
| Emoji/ZWJ | `hi 😀!` | Emoji có thể là symbol riêng, không tự coi là word |
| Chinese/Thai | Câu không có spaces | Không dựa vào split whitespace |
| Unicode normalization | `é` vs `e + U+0301` | Ranh giới và offsets theo nguồn, không lẫn chuỗi biến đổi |
| Nhiều locale | `en-US`, `vi-VN` và locale sản phẩm | Hành vi tương ứng dữ liệu/rule thực tế |
| Nhiều JDK/providers | Bộ test cố định với runtime mục tiêu | Ghi nhận thay đổi do Unicode/locale data |

### Bất biến hữu ích

Với vòng lặp lấy **tất cả** đoạn liên tiếp như trong `WordSegmentsDemo`:

1. Mọi đoạn có `0 <= start < end <= text.length()` với nguồn không trống (đối với các boundary khác nhau).
2. `start` của đoạn hiện tại là `end` của đoạn trước.
3. Nối tất cả `text.substring(start,end)` **không thêm ký tự** phải cho đúng nguồn ban đầu.
4. Nếu lọc đoạn có chữ/số, các `WordSpan` phải nằm trong phạm vi của nguồn, có thứ tự tăng và không chồng lấn.
5. Số đoạn được lọc **không được** suy ra chỉ bằng `text.split(...)` hoặc bằng số lần iterator chạy.

Những kiểm tra này bảo vệ tính toàn vẹn offset ngay cả khi quy tắc ngắt cụ thể thay đổi theo provider.

## 15. Câu hỏi ôn tập

**Câu 1.** Vì sao `getWordInstance(locale)` có thể trả đoạn chứa dấu chấm than hoặc khoảng trắng?

**Đáp án:** Nó trả **các ranh giới theo từ**, chứ không lọc sẵn từ. Đoạn giữa hai ranh giới có thể là dấu câu hoặc khoảng trắng cần giữ lại khi duyệt toàn văn bản.

**Câu 2.** Với `"Hello, world!"`, dùng `split("\\s+")` có tự bỏ `,` và `!` không?

**Đáp án:** Không. Nó chỉ tách ở whitespace; các token có thể là `"Hello,"` và `"world!"`.

**Câu 3.** Có nên đếm mọi segment giữa ranh giới làm số từ không?

**Đáp án:** Không. Cần chính sách lọc, ví dụ chỉ đoạn chứa chữ hoặc số; nếu chỉ muốn chữ, dùng `Character::isLetter`. Đây chỉ là heuristic, không thay phân tích từ vựng chuyên sâu.

**Câu 4.** Đâu là khác biệt giữa `BreakIterator.getWordInstance` và regex `\\b\\w+\\b`?

**Đáp án:** BreakIterator dùng quy tắc word boundaries theo locale/provider; regex `\\b` dựa trên khái niệm word/non-word character của engine, không cùng quy tắc ngôn ngữ và có thể tách `can't` hoặc `3.14` thành nhiều match.

**Câu 5.** Tại sao với tiếng Việt `học sinh` không đơn giản đồng nghĩa “hai từ” dù có một khoảng trắng?

**Đáp án:** Khoảng trắng tiếng Việt thường ngăn cách âm tiết; đơn vị từ vựng có thể gồm nhiều âm tiết. Word boundary ở cấp văn bản không tự giải quyết phân tích từ ghép theo nghĩa ngôn ngữ học.

**Câu 6.** Chỉ số trả về từ BreakIterator có thể dùng trực tiếp cho `String.substring` không?

**Đáp án:** Có, khi iterator được đặt trên **chính String nguồn** tương ứng; đó là UTF-16 offsets. Không được coi các offset ấy là code point index hay áp chúng lên một chuỗi đã chuẩn hóa có độ dài khác.

**Câu 7.** Nếu cần tô sáng, chỉ giữ List các word-like string đã lọc có đủ không?

**Đáp án:** Không. Nên giữ cả `start/end` trên chuỗi nguồn và có thể giữ các đoạn bị lọc dưới dạng thông tin riêng, để ánh xạ chính xác vị trí và không làm mất dấu câu/khoảng trắng.

**Câu 8.** Có thể dùng word BreakIterator để xác định cú pháp hợp lệ của một địa chỉ email/URL không?

**Đáp án:** Không. BreakIterator phục vụ phân đoạn văn bản ngôn ngữ tự nhiên; xác thực email/URL cần parser/đặc tả cú pháp riêng.

## 16. Ghi nhớ

- **Word boundary ≠ word token.** `getWordInstance` trả vị trí ranh giới, và các đoạn giữa biên có thể là **từ, số, dấu câu hoặc khoảng trắng**.
- Duyệt đúng bằng `first()` và `next()`, cắt `substring(start,end)` rồi **lọc/phân loại theo chính sách ứng dụng**.
- `split("\\s+")` chỉ tách theo khoảng trắng và thường giữ dấu câu dính với token; regex `\\b\\w+\\b` không phải quy tắc word segmentation theo locale.
- Định nghĩa rõ có tính **số, dấu nối, apostrophe, emoji, từ ghép tiếng Việt** là word token hay không.
- Các offset `BreakIterator` cho `String` là **UTF-16 index**, không phải byte hoặc code point index; giữ offset cùng nguồn để tô sáng.
- Với ứng dụng đa ngôn ngữ, chọn `Locale` tường minh, kiểm thử trên Unicode/JDK/provider mục tiêu và dùng NLP tokenizer chuyên biệt khi cần phân đoạn từ vựng.

**Tài liệu chính thức:**

- [Java SE 21 — BreakIterator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/BreakIterator.html)
- [Java SE 21 — Pattern](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html)
- [Java SE 21 — String](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html)
- [Unicode UAX #29 — Text Segmentation](https://www.unicode.org/reports/tr29/)
