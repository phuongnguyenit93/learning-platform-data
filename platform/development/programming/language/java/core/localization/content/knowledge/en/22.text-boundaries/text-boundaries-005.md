# Vì sao dấu cách không đủ để tách từ cho mọi ngôn ngữ

Trong nhiều ví dụ Java nhập môn, lập trình viên tách từ bằng `text.split(" ")` hoặc `text.split("\\s+")`. Cách này có thể hữu ích nếu dữ liệu đầu vào **được đặc tả rõ là danh sách các mục cách nhau bởi dấu cách**, nhưng **không phải thuật toán phân đoạn từ đa ngôn ngữ**. Một “từ” trong ngôn ngữ tự nhiên không nhất thiết được bao quanh bởi ký tự U+0020 SPACE.

Những trường hợp cần phân biệt:

- **Tiếng Trung, Nhật, Thái và một số hệ chữ khác** có thể viết chuỗi chứa nhiều từ mà **không đặt dấu cách giữa từng từ**.
- **Tiếng Việt** thường có khoảng trắng giữa các **tiếng/âm tiết**, nhưng một **từ vựng** có thể gồm nhiều tiếng như “học sinh”, “công nghệ thông tin”. Tách theo dấu cách không đồng nghĩa xác định từ theo nghĩa từ vựng.
- **Dấu câu** có thể nằm sát chữ, ví dụ `Hello,world!`, không cần dấu cách nhưng vẫn có các ranh giới đáng quan tâm.
- **Apostrophe, dấu nối và chữ viết tắt** không phải lúc nào cũng là chỗ tách từ: `don't`, `l'amour`, `e-mail`, `U.S.A.` cần chính sách riêng tùy bài toán.
- **Khoảng trắng Unicode** không chỉ có U+0020; U+00A0 NO-BREAK SPACE, U+202F NARROW NO-BREAK SPACE và U+3000 IDEOGRAPHIC SPACE có mục đích khác nhau.
- **Dấu kết hợp, emoji và surrogate pairs** nhắc rằng ranh giới code unit, code point, grapheme cluster và ranh giới từ là **các lớp khác nhau**.

Trong Java 17+, `java.text.BreakIterator` cung cấp các trình xác định ranh giới **từ**, **câu**, **ký tự** và **dòng** theo locale. Tuy nhiên, `BreakIterator` cũng không phải bảo đảm rằng mọi chuỗi từ được tách theo đúng từ điển, ngữ nghĩa hay yêu cầu NLP của mọi ngôn ngữ. Bài học này phân biệt **tách trường dữ liệu**, **tách theo khoảng trắng**, **xác định ranh giới từ** và **word segmentation theo ngôn ngữ**, rồi hướng dẫn chọn API phù hợp.

## 1. Trước hết, “từ” có thể mang nhiều nghĩa

Trong lập trình, từ “word” thường được dùng cho ít nhất bốn bài toán khác nhau:

| Mục tiêu | Đơn vị thật sự cần tách | Ví dụ |
| --- | --- | --- |
| Đọc một dòng gồm các mã cách nhau bởi dấu cách | **Trường dữ liệu** theo delimiter | `red blue green` |
| Cho phép người dùng nhấn đúp để chọn | **Đoạn văn bản có ranh giới từ** | Chọn `world` trong `Hello, world!` |
| Đếm từ vựng trong một câu | **Đơn vị từ theo ngôn ngữ** | Cụm “học sinh” có thể là một đơn vị từ vựng |
| Tạo token cho tìm kiếm/AI | **Token theo quy tắc của hệ thống tìm kiếm hoặc mô hình** | Token có thể là từ, n-gram, subword hoặc ký tự |

Không có một phép `split(" ")` nào đồng thời giải quyết cả bốn mục tiêu. Một chuỗi có ba nhóm cách nhau bởi dấu cách **không bắt buộc** có ba từ vựng. Ngược lại, một câu viết liền trong tiếng Trung có thể gồm nhiều từ nhưng **không có dấu cách nội bộ**.

**Câu hỏi đầu tiên khi thiết kế:** “Tôi muốn tách theo **dấu phân cách của giao thức**, hay muốn nhận diện **từ trong ngôn ngữ tự nhiên**?” Nếu là giao thức có delimiter xác định, sử dụng `split` theo đặc tả có thể chính xác. Nếu là văn bản tự nhiên đa ngôn ngữ, cần giải pháp theo quy tắc ranh giới văn bản và có thể cần từ điển/mô hình ngôn ngữ.

## 2. `String.split(" ")` thực sự làm gì?

`String.split(String regex)` nhận **biểu thức chính quy**, không nhận một thuật toán tìm từ. Chuỗi `" "` ở đây là regex khớp đúng một ký tự **U+0020 SPACE**.

Ví dụ runnable **`SpaceOnlyDemo.java`**:

~~~java
import java.util.Arrays;

public class SpaceOnlyDemo {
    public static void main(String[] args) {
        String input = "Hello,world! Java 17.";

        System.out.println(
                Arrays.toString(input.split(" ")));
        System.out.println(
                Arrays.toString("one  two".split(" ")));
    }
}
~~~

~~~bash
javac SpaceOnlyDemo.java
java SpaceOnlyDemo
~~~

Kết quả:

~~~text
[Hello,world!, Java, 17.]
[one, , two]
~~~

Giải thích:

- `Hello,world!` vẫn nguyên một trường vì dấu phẩy và dấu chấm than không khớp regex dấu cách.
- `Java` và `17.` được tách vì chúng nằm ở hai bên U+0020.
- Hai dấu cách liên tiếp ở `one  two` tạo **một phần tử rỗng** ở giữa khi tách theo từng dấu cách đơn.
- `String.split(regex)` mặc định bỏ **các trường rỗng ở cuối** do thuật toán split với limit bằng 0; nó không đồng nhất với một bộ CSV parser hay tokenizer văn bản.

Đây là kết quả của **tách theo ký tự phân cách**, không phải kết quả của phân tích ngôn ngữ. Nếu yêu cầu ứng dụng là xử lý lệnh đơn giản do máy tạo với delimiter U+0020, đó có thể là lựa chọn đúng; nếu đầu vào là văn bản tự nhiên thì không.

## 3. `split("\\s+")` tốt hơn cho một số whitespace, nhưng chưa đủ

Trong Java source:

~~~java
String[] parts = input.split("\\s+");
~~~

Có **hai lớp cú pháp**:

1. `"\\s+"` là **Java string literal** chứa một dấu backslash thật trước `s`.
2. Regex engine hiểu `\s+` là **một hoặc nhiều ký tự whitespace theo quy tắc regex hiện hành**.

Dùng `+` tránh tạo phần tử rỗng giữa nhiều delimiter liên tiếp. Nhưng với Java regex mặc định, `\s` có tập whitespace **không bao trùm toàn bộ Unicode White_Space**. Ví dụ những khoảng trắng không ngắt và khoảng trắng ý niệm được dùng khi trình bày văn bản đa ngôn ngữ có thể không khớp.

Để bật lớp ký tự Unicode cho regex, Java hỗ trợ `Pattern.UNICODE_CHARACTER_CLASS` hoặc cờ inline `(?U)`:

~~~java
String[] parts = input.split("(?U)\\s+");
~~~

Cách này có thể xử lý nhiều loại whitespace Unicode hơn, **nhưng vẫn chỉ tách tại whitespace**. Nó không biết một câu tiếng Trung có bao nhiêu từ, không biết “học sinh” có nên được xem là một token hay không, và không quyết định ngữ nghĩa của apostrophe/dấu nối.

## 4. Các khoảng trắng Unicode và ý nghĩa của chúng

Unicode có nhiều ký tự khoảng trắng vì nhiều lý do trình bày, ngôn ngữ và kiểm soát xuống dòng:

| Code point | Tên | Tình huống |
| --- | --- | --- |
| U+0020 | SPACE | Dấu cách thông thường |
| U+0009 | CHARACTER TABULATION | Tab giữa các trường/dòng |
| U+000A | LINE FEED | Ngắt dòng |
| U+00A0 | NO-BREAK SPACE | Giữ các thành phần cùng một dòng |
| U+202F | NARROW NO-BREAK SPACE | Khoảng trắng hẹp không ngắt; thường xuất hiện trong dữ liệu định dạng |
| U+3000 | IDEOGRAPHIC SPACE | Dấu cách rộng kiểu CJK |
| U+2009 | THIN SPACE | Khoảng trắng mảnh |
| U+200B | ZERO WIDTH SPACE | Ký tự đặc biệt không có chiều rộng hiển thị; cần xét riêng, **không coi là whitespace regex thông thường** |

Đừng nhìn màn hình rồi suy ra mọi khoảng trống là U+0020. Trong dữ liệu tiền tệ, số lớn, ngày giờ và văn bản bản địa hóa, người dùng có thể gặp U+00A0 hoặc U+202F mà font hiển thị gần như dấu cách thường.

### Ví dụ so sánh regex mặc định và Unicode

Tạo **`UnicodeWhitespaceDemo.java`**:

~~~java
import java.util.Arrays;

public class UnicodeWhitespaceDemo {
    public static void main(String[] args) {
        String text = "one" + (char) 0x00A0
                + "two" + (char) 0x202F
                + "three" + (char) 0x3000
                + "four";

        System.out.println(
                Arrays.toString(text.split("\\s+")));
        System.out.println(
                Arrays.toString(text.split("(?U)\\s+")));

        System.out.println(
                Character.isWhitespace(0x00A0));
        System.out.println(
                Character.isSpaceChar(0x00A0));
    }
}
~~~

~~~bash
javac UnicodeWhitespaceDemo.java
java UnicodeWhitespaceDemo
~~~

Kết quả trong JDK 17 dùng regex Unicode như mô tả:

~~~text
[one two three　four]
[one, two, three, four]
false
true
~~~

Dòng đầu có các ký tự khoảng trắng Unicode nằm **bên trong một phần tử**; chúng có thể khó phân biệt trên console. Dòng hai tách ra bốn trường. Hai dòng cuối cho thấy `Character.isWhitespace` và `Character.isSpaceChar` cũng **không phải cùng một tập thuộc tính**; U+00A0 là một ví dụ.

**Kết luận của ví dụ không phải “hãy luôn tách ở mọi Unicode whitespace”.** Trong số có nhóm như `1 234` hoặc cụm tên riêng có khoảng trắng không ngắt, tách tại đó có thể phá vỡ ý nghĩa vốn cần được giữ. Hãy xác định whitespace là **delimiter của dữ liệu**, hay chỉ là **ký tự trình bày**.

## 5. Ngôn ngữ có thể có nhiều từ nhưng không đặt dấu cách giữa chúng

Tiếng Trung, Nhật, Thái, Lào, Khmer và một số hệ chữ khác có **quy tắc sử dụng khoảng trắng không giống cách viết câu tiếng Anh**. Ví dụ tiếng Trung có thể viết nhiều từ liền nhau trong một câu mà không sử dụng U+0020 ở mỗi ranh giới từ.

Trong tiếng Nhật, nhiều đơn vị chữ Hán, Hiragana và Katakana có thể xuất hiện sát nhau; ranh giới từ có thể phụ thuộc cách phân tích hình thái và ngữ cảnh.

Trong tiếng Thái, khoảng trắng thường được dùng cho các ranh giới lớn hơn là giữa từng từ trong nhiều kiểu văn bản, nên một câu dài có thể không có khoảng trắng giữa các đơn vị từ vựng. Các hệ chữ khác có sự kết hợp riêng giữa dấu cách, dấu ngắt câu và dấu kết hợp.

**Hệ quả của `split(" ")`:** nếu chuỗi không có U+0020, kết quả đơn giản là **một phần tử duy nhất**, dù người đọc nhận thấy nhiều từ.

Ví dụ code minh họa độc lập **`NoSpaceDemo.java`**:

~~~java
import java.util.Arrays;

public class NoSpaceDemo {
    public static void main(String[] args) {
        String chinese = new String(new int[]{
                0x6211, 0x559C, 0x6B22, 0x7F16, 0x7A0B
        }, 0, 5);

        String[] parts = chinese.split(" ");

        System.out.println(parts.length);
        System.out.println(
                chinese.codePointCount(0, chinese.length()));
    }
}
~~~

~~~bash
javac NoSpaceDemo.java
java NoSpaceDemo
~~~

Kết quả:

~~~text
1
5
~~~

Dòng đầu chỉ cho biết văn bản không có dấu cách U+0020; **không** cho biết câu có một từ. Dòng hai cho biết **năm Unicode code points**, cũng **không** có nghĩa năm từ. Một “từ” có thể dài một hoặc nhiều code point tùy ngôn ngữ và cách phân tích.

Đây là lý do các hệ thống tìm kiếm, bộ gõ, kiểm tra chính tả và xử lý ngôn ngữ tự nhiên thường cần **bộ phân đoạn theo ngôn ngữ** thay vì `split`.

## 6. Tiếng Việt: khoảng trắng thường tách tiếng, không nhất thiết tách từ vựng

Tiếng Việt là ví dụ rất gần với lập trình viên Việt Nam: văn bản thường dùng dấu cách giữa **các tiếng/âm tiết**, nhưng một **từ** theo nghĩa từ vựng có thể gồm nhiều tiếng.

Ví dụ:
- “học sinh”;
- “sinh viên”;
- “công nghệ”;
- “công nghệ thông tin”;
- “thành phố”.

Nếu tách `"học sinh"` bằng U+0020, ta có hai phần `"học"` và `"sinh"`. Nhưng trong nhiều ngữ cảnh NLP, “học sinh” được xem là một **đơn vị từ vựng**.

Vấn đề không chỉ ở bảng chữ cái Unicode; ngay cả khi tách hoàn hảo tất cả dấu cách, **nhiệm vụ ghép tiếng thành từ vẫn chưa giải quyết**. Việc quyết định “sinh viên” là một từ, hay phát hiện các cụm danh từ khác, cần từ điển/ngữ cảnh và đôi khi là mô hình thống kê.

Cũng không được tuyên bố mọi chuỗi nhiều tiếng ghép lại đều là một từ: **ranh giới từ vựng là một bài toán ngôn ngữ**, không phải chỉ nhìn số lượng khoảng trắng.

### Khi nào tách theo dấu cách vẫn đúng?

Nếu bài toán là **đếm số tiếng cách nhau bởi khoảng trắng** trong một định dạng văn bản tiếng Việt đã chuẩn hóa, một quy tắc split có thể phù hợp. Nhưng kết quả phải được gọi đúng là “số đoạn sau khi tách khoảng trắng”, không tự đổi nhãn thành “số từ vựng chính xác”.

Với tìm kiếm tiếng Việt, tokenization thường phải giải quyết từ đa âm tiết, dấu thanh, chuẩn hóa Unicode, tên riêng và các kiểu chữ viết tắt.

## 7. Dấu câu tạo ranh giới mà không cần dấu cách

Xét:

~~~text
Hello,world!Java
~~~

Dù không có U+0020, người đọc vẫn phân biệt các thành phần `Hello`, dấu phẩy, `world`, dấu chấm than, `Java`.

`split(" ")` trả lại nguyên chuỗi. `split("\\s+")` cũng vậy. **Khoảng trắng không phải tín hiệu duy nhất của ranh giới từ.**

Nhưng “tách theo mọi dấu câu” cũng không đúng trong mọi ngữ cảnh:
- `don't`: apostrophe có thể là một phần của một từ.
- `l'amour`: apostrophe đóng vai trò trong chính tả tiếng Pháp.
- `e-mail` hoặc `COVID-19`: dấu nối có thể nằm trong một đơn vị cần giữ nguyên.
- `3.14` và `1,234`: dấu chấm/phẩy nằm trong số, không luôn là ranh giới token.
- Địa chỉ email và URL có nhiều dấu câu nhưng không nên bị tách bừa nếu chúng là đơn vị dữ liệu.

**Tách từ không đơn thuần là “split trên mọi non-letter”.** Nếu chia tại mọi ký tự không phải `Character.isLetter`, ta có thể phá số, dấu kết hợp, từ có apostrophe và những token chuyên ngành.

## 8. Bốn loại ranh giới phải phân biệt

Trong xử lý Unicode có nhiều cấp độ phân đoạn:

| Loại | Câu hỏi | Ví dụ API |
| --- | --- | --- |
| UTF-16 code unit | Vị trí `char` thứ mấy? | `String.charAt` |
| Unicode code point | Code point Unicode tiếp theo là gì? | `String.codePoints` |
| Grapheme/character boundary | Đâu là một cụm ký tự người dùng thường thao tác như một ký tự? | `BreakIterator.getCharacterInstance`, một số regex hỗ trợ grapheme |
| Word boundary | Đâu là ranh giới đoạn được coi là từ trong văn bản? | `BreakIterator.getWordInstance` |
| Sentence boundary | Đâu là ranh giới câu? | `BreakIterator.getSentenceInstance` |
| Line-break opportunity | Có thể ngắt dòng ở đâu? | `BreakIterator.getLineInstance` |

**Một code point không nhất thiết là một ký tự hiển thị**: chữ cái có thể đi với dấu kết hợp, emoji có thể gồm nhiều code point và zero-width joiner. **Một ký tự hiển thị không nhất thiết là một từ**. **Một từ không nhất thiết là một token NLP**.

Ví dụ chữ `é` có thể là một code point U+00E9 hoặc hai code point U+0065 + U+0301. Nếu cắt bừa giữa chúng, dấu kết hợp có thể bị tách khỏi chữ. Vấn đề này thuộc **ranh giới ký tự/grapheme**, khác với tách từ.

Do đó khi cần di chuyển con trỏ, tô sáng từ, đếm từ, hoặc cắt chuỗi theo quota, phải chọn cấp độ phù hợp, không dùng một thuật toán cho mọi nhiệm vụ.

## 9. `java.text.BreakIterator`: bộ xác định ranh giới theo locale

Java cung cấp:

~~~java
BreakIterator.getWordInstance(Locale locale);
BreakIterator.getSentenceInstance(Locale locale);
BreakIterator.getCharacterInstance(Locale locale);
BreakIterator.getLineInstance(Locale locale);
~~~

Đây là **snippet**, cần import `java.text.BreakIterator` và `java.util.Locale`.

`BreakIterator` thực hiện **boundary analysis** theo dữ liệu và quy tắc mà JDK/locale provider hỗ trợ. Nó trả các **vị trí ranh giới** trong văn bản, không trả sẵn danh sách “từ vựng chắc chắn đúng”.

Với `getWordInstance`, những đoạn mà iterator trả ra có thể gồm:
- chữ hoặc số;
- dấu câu;
- dấu cách;
- những ký hiệu không tạo thành từ.

Vì thế số lượng đoạn iterator tạo ra **không phải luôn là số từ**. Ta phải quyết định cách lọc/đọc các đoạn theo nhu cầu, và cần đặc biệt cẩn thận với ngôn ngữ không phân cách từ bằng khoảng trắng.

## 10. Ví dụ Java 17+ dùng `BreakIterator` thay split

Tạo **`WordBoundaryDemo.java`**:

~~~java
import java.text.BreakIterator;
import java.util.Locale;

public class WordBoundaryDemo {
    public static void main(String[] args) {
        String text = "Hello, world! Java 17.";

        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.ENGLISH);
        iterator.setText(text);

        int wordLikeSegments = 0;
        StringBuilder reconstruction = new StringBuilder();

        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {

            String segment = text.substring(start, end);
            reconstruction.append(segment);

            if (segment.codePoints()
                    .anyMatch(Character::isLetterOrDigit)) {
                wordLikeSegments++;
            }
        }

        System.out.println(
                reconstruction.toString().equals(text));
        System.out.println(wordLikeSegments);
    }
}
~~~

~~~bash
javac WordBoundaryDemo.java
java WordBoundaryDemo
~~~

Với bộ quy tắc `Locale.ENGLISH` của JDK 17 thông dụng, kết quả:

~~~text
true
4
~~~

Lời gọi `iterator.setText(text)` xác định chuỗi cần phân tích. `iterator.first()` trả ranh giới đầu; `next()` trả ranh giới kế; `BreakIterator.DONE` báo kết thúc.

Bộ lọc `anyMatch(Character::isLetterOrDigit)` chỉ là **chính sách minh họa** để đếm các đoạn giống từ. Nó **không** biến `BreakIterator` thành bộ nhận diện từ vựng cho mọi ngôn ngữ. Trong ví dụ, bốn đoạn có chữ/số là `Hello`, `world`, `Java` và `17`.

**Đừng bỏ qua những đoạn còn lại khi cần tái dựng câu:** `reconstruction` chứng minh ghép **tất cả** các đoạn theo thứ tự tạo lại đúng văn bản gốc, gồm dấu câu và khoảng trắng. Còn nếu chỉ lấy đoạn có letter/digit, ta đang **lọc token**, không phải giữ nguyên văn bản.

## 11. Một phiên bản in ranh giới để hiểu iterator

Tạo **`BoundarySegmentsDemo.java`**:

~~~java
import java.text.BreakIterator;
import java.util.Locale;

public class BoundarySegmentsDemo {
    public static void main(String[] args) {
        String input = "Hello, world!";

        BreakIterator iterator =
                BreakIterator.getWordInstance(Locale.ENGLISH);
        iterator.setText(input);

        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {

            String segment = input.substring(start, end);
            System.out.println("[" + segment + "]");
        }
    }
}
~~~

~~~bash
javac BoundarySegmentsDemo.java
java BoundarySegmentsDemo
~~~

Ví dụ kết quả với JDK 17 và provider thông dụng:

~~~text
[Hello]
[,]
[ ]
[world]
[!]
~~~

Đầu ra minh họa rằng **iterator trả cả dấu câu và khoảng trắng**. Trong hệ thống thực tế, chi tiết ranh giới có thể phụ thuộc provider/dữ liệu locale, đặc biệt với các script phức tạp, nên đừng hardcode mọi quy tắc của một phiên bản JDK thành chân lý đa ngôn ngữ.

`BreakIterator` trả **offset UTF-16**: `substring(start, end)` là cách hợp lệ để trích chính đoạn đã được iterator chỉ ra. Không tự coi `start`/`end` là số code point hoặc số ký tự người dùng nhìn thấy.

## 12. Locale ảnh hưởng cách phân đoạn, nhưng không biến mọi ngôn ngữ thành bài toán đã giải

Có thể lấy iterator cho locale cụ thể:

~~~java
BreakIterator english =
        BreakIterator.getWordInstance(Locale.ENGLISH);

BreakIterator thai =
        BreakIterator.getWordInstance(
                Locale.forLanguageTag("th-TH"));

BreakIterator japanese =
        BreakIterator.getWordInstance(Locale.JAPANESE);
~~~

Đây là **snippet**. Việc truyền locale giúp runtime áp dụng các quy tắc/dữ liệu phân đoạn phù hợp **nếu được hỗ trợ**.

Tuy nhiên, không có hợp đồng `BreakIterator.getWordInstance` nào đảm bảo luôn:
- chọn đúng ranh giới từ theo từ điển của mọi ngôn ngữ;
- hiểu mọi từ ghép tiếng Việt theo nghĩa từ vựng;
- giải quyết mọi nhập nhằng giữa nhiều cách phân đoạn tiếng Trung/Nhật/Thái;
- trích đúng tên riêng, thuật ngữ y khoa, token của bộ tìm kiếm;
- dùng cùng một bộ từ điển/mô hình trên mọi JDK/provider.

Ngay cả với cùng locale, dữ liệu của runtime hoặc triển khai service provider có thể khác. Khi cần **chất lượng NLP thực tế**, đánh giá trên tập văn bản và mục tiêu ngôn ngữ cụ thể, có thể dùng **bộ tokenizer theo ngôn ngữ, dictionary segmenter hoặc mô hình NLP**.

**Nguyên tắc:** `BreakIterator` hữu ích cho **boundary analysis**, nhưng không thay thế đầy đủ **linguistic word segmentation**.

## 13. Tại sao chỉ tách theo chữ cái/số cũng chưa đủ?

Một cách tự viết tokenizer thường dùng:

~~~java
boolean isWordChar(int codePoint) {
    return Character.isLetterOrDigit(codePoint);
}
~~~

Đây là **snippet trong class**. Nó có một số ưu điểm so với regex ASCII, vì `Character.isLetterOrDigit` biết nhiều category Unicode. Nhưng nó vẫn có giới hạn:

1. Một **combining mark** riêng lẻ không phải letter/digit, dù nó thuộc một ký tự có dấu.
2. Apostrophe/dấu nối có thể là thành phần của từ trong một số ngôn ngữ hoặc miền dữ liệu.
3. URL/email và số có dấu phân cách cần phân tích riêng.
4. Chữ tượng hình trong văn bản CJK có thể gồm nhiều code point và nhiều từ **liền nhau**; tất cả các code point đều là letter không cho biết ranh giới.
5. Từ ghép tiếng Việt có dấu cách giữa các tiếng, nên luật letter/digit vẫn không tự gom các tiếng thành từ.
6. Emoji, hashtag và mention có thể là token theo ứng dụng nhưng không khớp luật letter/digit đơn giản.

Nếu nhiệm vụ chỉ là “lọc những đoạn có chữ hoặc số sau `BreakIterator`”, heuristic này có thể đáp ứng. Nhưng nếu sản phẩm cần **tokenizer tìm kiếm**, **đếm từ vựng chính xác**, hoặc **xác thực định danh**, phải thiết kế thêm quy tắc.

## 14. Dấu kết hợp, UTF-16 và rủi ro cắt sai biên

Java lưu `String` bằng các đơn vị UTF-16. Có những ký tự ngoài BMP cần **hai `char`**, và có những grapheme cluster gồm **nhiều code point**.

Ví dụ một chuỗi gồm chữ `e` và dấu kết hợp U+0301:

~~~java
String accent = "e" + (char) 0x0301;

System.out.println(accent.length());
System.out.println(accent.codePointCount(
        0, accent.length()));
~~~

Đây là **snippet trong method**. Kết quả:

~~~text
2
2
~~~

Hai code point nhưng thường hiển thị thành một chữ có dấu. **Cắt giữa hai code point** có thể tách dấu ra khỏi chữ. Với những emoji dạng chuỗi có zero-width joiner, nhiều code point có thể được người dùng coi là một biểu tượng.

Nếu cần **dịch con trỏ hoặc chọn một ký tự hiển thị**, hãy cân nhắc `BreakIterator.getCharacterInstance(locale)` hoặc cơ chế grapheme segmentation phù hợp với Unicode version được hỗ trợ. Java regex `\X` và `\b{g}` cũng cung cấp các cấu trúc liên quan extended grapheme clusters trong Java 17.

**Grapheme boundary khác word boundary.** Không được dùng `String.codePoints().count()` để suy ra số từ, và không được dùng vị trí code unit để khẳng định có bao nhiêu chữ người dùng nhìn thấy.

## 15. Phân biệt word boundary và sentence boundary

`BreakIterator` có các factory riêng:

- `getWordInstance(locale)`: ranh giới liên quan **từ**;
- `getSentenceInstance(locale)`: ranh giới **câu**;
- `getLineInstance(locale)`: những vị trí **có thể ngắt dòng**;
- `getCharacterInstance(locale)`: ranh giới **ký tự** theo thuật toán của provider.

Ví dụ dấu chấm có thể:
- kết thúc một câu;
- nằm trong chữ viết tắt `Dr.`;
- là dấu thập phân trong `3.14`;
- xuất hiện trong URL/domain;
- xuất hiện liên tiếp trong `...`.

Vì vậy, cách `text.split("\\.")` không phải một bộ tách câu hoàn chỉnh; dùng dấu chấm làm mọi ranh giới có thể phá số, tên riêng và chữ viết tắt. `BreakIterator.getSentenceInstance(locale)` xử lý boundary analysis có ngữ cảnh, nhưng vẫn cần đánh giá với dữ liệu và ngôn ngữ của sản phẩm.

### Ví dụ phân đoạn câu mà không hardcode số câu

Tạo **`SentenceBoundaryDemo.java`**:

~~~java
import java.text.BreakIterator;
import java.util.Locale;

public class SentenceBoundaryDemo {
    public static void main(String[] args) {
        String input = "Dr. Lee paid 3.14. Then left.";

        BreakIterator iterator =
                BreakIterator.getSentenceInstance(Locale.ENGLISH);
        iterator.setText(input);

        StringBuilder restored = new StringBuilder();
        int segments = 0;

        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {
            restored.append(input, start, end);
            segments++;
        }

        System.out.println(restored.toString().equals(input));
        System.out.println(segments > 0);
    }
}
~~~

~~~bash
javac SentenceBoundaryDemo.java
java SentenceBoundaryDemo
~~~

Kết quả:

~~~text
true
true
~~~

Chương trình không khẳng định một số câu cố định vì hành vi với chữ viết tắt có thể khác theo provider và từ điển. Điều được kiểm tra là iterator trả các đoạn không rỗng và việc ghép chúng vẫn tái dựng nguyên văn input. Muốn đếm câu theo nghiệp vụ, cần kiểm thử chất lượng phân đoạn với các chữ viết tắt và văn bản thực tế.

## 16. Regex `\\b` không thay thế bộ tách từ ngôn ngữ tự nhiên

Trong Java regex, `\b` là một **word boundary assertion**, không phải lệnh tách từ theo ngôn ngữ. Nó chỉ xác định ranh giới theo quy tắc regex, không hiểu mọi từ ghép tiếng Việt hay các bài toán phân đoạn script không dấu cách.

Ngoài ra phải phân biệt **hai tầng escape**:

~~~java
String regex = "\\b";
~~~

Dòng trên tạo regex có backslash + `b`. Nếu viết `"\b"` trong Java string literal, `\b` là **backspace character** của Java, không phải token word boundary của regex.

`\w`, `\d`, `\s` cũng có các tập ký tự cụ thể. `Pattern.UNICODE_CHARACTER_CLASS` hoặc inline flag `(?U)` làm những predefined character classes trở thành Unicode-aware hơn, nhưng **chuyển tập ký tự không tự giải quyết segmentation bằng từ điển**.

Ví dụ `\b` có thể hữu ích để tìm ranh giới của một chuỗi đã biết trong một miền dữ liệu đơn giản, nhưng không nên gọi nó là “universal tokenizer” cho tiếng Trung, Nhật, Thái hay tiếng Việt.

## 17. Kiểm tra khoảng trắng bằng Unicode property

Nếu nghiệp vụ chỉ cần **tách một danh sách các trường được phân cách bằng Unicode White_Space**, có thể dùng một regex đã nêu rõ chính sách:

~~~java
String[] fields = input.split("(?U)\\s+");
~~~

Hoặc dùng Unicode property do Java regex hỗ trợ:

~~~java
String[] fields = input.split("\\p{IsWhite_Space}+");
~~~

Đây là **snippet**, trong đó `input` là `String` đã có. Hai cách có thể xử lý nhiều ký tự whitespace Unicode hơn `"\\s+"` mặc định của Java.

Tuy nhiên, trước khi dùng:
1. Xác định có muốn coi **NBSP** là delimiter hay không.
2. Xác định cách xử lý **dấu cách ở đầu/cuối chuỗi**.
3. Quy định có giữ **trường rỗng** hay không.
4. Xác định cách xử lý **zero-width space** và các ký tự định dạng không thuộc cùng thuộc tính.
5. Không áp dụng phép này để tuyên bố số từ của văn bản tự nhiên khi ngôn ngữ không dùng whitespace để ngăn mọi từ.

Việc tăng độ bao phủ Unicode của regex chỉ giải quyết **tập dấu phân cách**, không giải quyết **ngữ nghĩa của từ**.

## 18. Đếm từ: điều gì nên được báo cáo?

Các sản phẩm thường yêu cầu “word count”. Nhưng từ đó cần định nghĩa:

- **Đếm nhóm tách bởi whitespace:** dễ tính, nhanh, có thể phù hợp cho trường dữ liệu đơn giản, nhưng **không công bằng giữa các ngôn ngữ**.
- **Đếm các đoạn giống từ do `BreakIterator` trả về:** tốt hơn cho một số chức năng chỉnh sửa văn bản, nhưng kết quả phụ thuộc locale/provider và quy tắc lọc punctuation.
- **Đếm từ vựng theo NLP tokenizer:** cần mô hình/quy tắc theo từng ngôn ngữ, có thể thay đổi theo phiên bản, và không nhất thiết khớp cách đếm của người đọc.
- **Đếm grapheme clusters hoặc ký tự:** là tiêu chí khác, có thể thích hợp cho giới hạn SMS/UI nhưng không phải word count.

Một nhà cung cấp dịch vụ dịch thuật có thể tính giá dựa trên số từ ở một số ngôn ngữ, số ký tự ở ngôn ngữ khác. Không nên đặt cùng một quota “100 từ” dựa trên whitespace cho mọi ngôn ngữ mà không công bố rõ cách đếm.

Nếu giới hạn input của ứng dụng cần **độ dài**, thường nên đo byte/code point/grapheme tùy hợp đồng hơn là dùng số phần tử sau `split(" ")`.

## 19. Đầu vào trống và nhiều delimiter

Một lỗi phổ biến của đếm theo split:

~~~java
int count = text.split("\\s+").length;
~~~

Dòng này có nhiều góc cạnh:
- Một chuỗi rỗng có thể tạo mảng có phần tử rỗng tùy overload/ngữ nghĩa của `split`.
- Chuỗi toàn whitespace có thể dẫn đến kết quả khác kỳ vọng.
- Dấu cách đầu/cuối có thể ảnh hưởng phần tử rỗng; mặc định các phần tử rỗng **ở cuối** bị bỏ.
- Các whitespace Unicode không được regex mặc định nhận diện có thể ở lại trong một phần tử.
- Văn bản không có dấu cách có thể bị tính là một “từ” dù thực tế có nhiều từ.

Nếu mục tiêu là **danh sách trường có whitespace delimiter**, hãy định nghĩa cách xử lý input trống và trim/strip riêng. Với `strip()` của Java, cần biết nó dựa trên `Character.isWhitespace` và có thể không loại bỏ mọi ký tự Unicode như NBSP.

**Đừng dùng một mẹo `length` của mảng split làm thước đo ngôn ngữ học.**

## 20. Phân biệt dữ liệu có delimiter với văn bản tự nhiên

**Trường hợp A — giao thức có delimiter rõ ràng:**

~~~text
CSV, TSV, command line arguments, danh sách ID phân cách bởi ký tự xác định
~~~

Ở đây cần parser **đúng giao thức**. CSV có quy tắc dấu nháy, escape, dòng mới; tự split trên dấu phẩy cũng có thể sai. TSV có các ràng buộc khác, và command line có quoting riêng.

**Trường hợp B — văn bản tự nhiên:**

~~~text
Một câu tiếng Việt, tiếng Thái, tiếng Trung, tiếng Nhật, tiếng Ả Rập...
~~~

Ở đây cần boundary analysis/segmentation theo ngôn ngữ và mục tiêu. Không nên dùng parser CSV cho văn bản tự nhiên hoặc dùng word tokenizer để phân tách các trường CSV.

Một người viết `Hello world` có khoảng trắng, nhưng một mã `user@example.com` có dấu câu và không nên bị tách thành nhiều “từ” nếu nghiệp vụ muốn coi email là một đơn vị.

Chọn đúng **đơn vị dữ liệu** sẽ giải quyết phần lớn nhầm lẫn trước cả khi chọn API Java.

## 21. Một helper Java 17+ lấy đoạn word-like nhưng giữ locale tường minh

Tạo **`WordLikeSegments.java`**:

~~~java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class WordLikeSegments {
    private WordLikeSegments() {}

    public static List<String> extract(
            String input, Locale locale) {

        if (input == null || locale == null) {
            throw new IllegalArgumentException(
                    "input and locale must not be null");
        }

        BreakIterator iterator =
                BreakIterator.getWordInstance(locale);
        iterator.setText(input);

        List<String> result = new ArrayList<>();

        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {

            String part = input.substring(start, end);

            if (part.codePoints()
                    .anyMatch(Character::isLetterOrDigit)) {
                result.add(part);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> words = extract(
                "Hello, world! Java 17.",
                Locale.ENGLISH);

        System.out.println(words);
    }
}
~~~

~~~bash
javac WordLikeSegments.java
java WordLikeSegments
~~~

Kết quả với quy tắc JDK 17 tiếng Anh thông dụng:

~~~text
[Hello, world, Java, 17]
~~~

Đây là **word-like segment extraction**, không phải từ điển tiếng Anh và càng không phải tokenizer vạn năng. Nó còn **bỏ dấu câu và khoảng trắng**, nên không thể tái dựng đầy đủ văn bản chỉ bằng `result`; nếu cần giữ vị trí/câu gốc, phải lưu start/end offsets và phân loại riêng các đoạn.

Hàm tạo `BreakIterator` theo mỗi lần gọi để tránh chia sẻ trạng thái mutable giữa các request. Với hiệu năng cao, hãy đo thực tế trước khi tối ưu, và đảm bảo locale/provider nhất quán với chính sách sản phẩm.

## 22. Nâng cấp helper: giữ offset và phân loại đoạn

Khi người dùng bôi đen văn bản hoặc ứng dụng cần gắn highlight, chỉ lưu chuỗi token có thể chưa đủ. Cần giữ **vị trí ban đầu**:

~~~java
public record Segment(int start, int end, String text) {}
~~~

Đây là snippet đặt trong class hoặc file Java thích hợp. `start` và `end` từ `BreakIterator` là offset UTF-16, phù hợp với `String.substring(start, end)` của Java.

Nên lưu:
- text gốc;
- start/end của từng segment;
- loại segment (`word-like`, punctuation, whitespace, symbol...);
- locale và phiên bản quy tắc nếu cần tái lập quá trình tách.

Đừng trộn chỉ số **code point** với offset **UTF-16** khi frontend/backend dùng cách đếm khác nhau. Ví dụ một emoji ngoài BMP có thể chiếm hai UTF-16 code units; nếu đem offset dạng code point dùng trực tiếp với `substring`, dễ highlight sai.

Khi UI dùng một API khác có offset theo UTF-8 byte hoặc grapheme cluster, cần chuyển đổi tọa độ rõ ràng và kiểm tra các trường hợp surrogate pair/dấu kết hợp.

## 23. Từ có dấu, normalization và việc ghép đoạn

Văn bản tiếng Việt có thể chứa chữ dựng sẵn hoặc chữ cái + combining mark:

~~~text
é
e + U+0301
~~~

`java.text.Normalizer` có thể đưa những biểu diễn canonical-equivalent về một form nhất quán, ví dụ NFC. Tuy nhiên, **normalization không tách từ**. Nó chỉ xử lý dạng biểu diễn Unicode.

Một pipeline phân tích văn bản có thể:

~~~text
Nhận văn bản Unicode
    ↓
Xác định locale/ngôn ngữ và mục tiêu tokenization
    ↓
Normalize theo policy (nếu có)
    ↓
Phân đoạn từ bằng BreakIterator/tokenizer phù hợp
    ↓
Lọc/phân loại/ghép token theo nghiệp vụ
    ↓
Lưu vị trí hoặc mapping về chuỗi gốc nếu cần highlight
~~~

Nếu normalization thay độ dài chuỗi, offset trên văn bản đã normalize **không nhất thiết trùng** offset trên bản gốc. Đừng áp dụng offset của bản đã chuẩn hóa trực tiếp lên bản gốc nếu đã có thay đổi code unit.

Nếu ứng dụng cần hiển thị chính xác các ký tự đầu vào, có thể lưu cả bản gốc và văn bản chuẩn hóa dùng cho tìm kiếm, kèm cơ chế ánh xạ vị trí.

## 24. Search tokenization và ngữ nghĩa từ ghép

Với một hệ thống tìm kiếm đa ngôn ngữ, bộ tokenizer cần cân nhắc:

1. **Ngôn ngữ và script**: Chinese word segmentation, Japanese morphological segmentation, Thai/Lao/Khmer dictionary-based segmentation, Vietnamese compound-word segmentation.
2. **Normalization**: Unicode NFC/NFKC theo chính sách, dấu tiếng Việt, fullwidth forms, trường hợp cần giữ/kéo dài token.
3. **Case handling**: locale-sensitive case mapping và case folding không được gộp tùy tiện.
4. **Số và đơn vị**: `3.14`, `1 234`, đơn vị đo hoặc ký hiệu tiền.
5. **Tên riêng và từ viết tắt**: `TP.HCM`, `U.S.A.`, thương hiệu có dấu nối.
6. **URL, email, hashtag, mention**: có thể cần giữ thành một token.
7. **Emoji và ký tự biểu tượng**: một số sản phẩm cần index các biểu tượng, không chỉ chữ/số.
8. **Bản cập nhật từ điển/mô hình**: khi thay phiên bản tokenizer, cần kiểm thử lại quality và khả năng tương thích index.

Ví dụ “công nghệ thông tin” có thể cần giữ thành một cụm hoặc tạo n-gram để tìm kiếm; không có một đáp án tokenization duy nhất cho mọi truy vấn.

**Đừng nhầm việc tách câu thành danh sách token với việc hiểu nghĩa câu.** Tokenization là một bước, còn phân tích từ loại, thực thể, tách nghĩa và tìm kiếm ngữ nghĩa là những bước khác.

## 25. Java core và thư viện chuyên dụng

Java core đã có `BreakIterator` và Unicode regex đủ cho nhiều nhiệm vụ:
- di chuyển con trỏ theo ranh giới;
- phân đoạn câu/từ ở mức quy tắc chuẩn;
- hỗ trợ các tính năng chỉnh sửa văn bản;
- lọc các đoạn giống từ theo một heuristic;
- phân tách trường dữ liệu theo delimiter được đặc tả.

Nếu sản phẩm cần chất lượng cao cho tiếng Nhật, Trung, Thái, tiếng Việt hoặc chuyên ngành, có thể cân nhắc **bộ phân đoạn chuyên dụng theo ngôn ngữ**, từ điển/mô hình NLP hoặc thư viện Unicode/i18n như ICU4J. Nhưng cần đánh giá **đúng khả năng, phiên bản và dữ liệu của thư viện được chọn**; không giả định thay thư viện là sẽ giải quyết mọi nhập nhằng ngôn ngữ.

Đừng tự khẳng định `BreakIterator.getWordInstance(Locale.forLanguageTag("th-TH"))` luôn trả về những từ đúng theo từ điển tiếng Thái. Kết quả có thể phụ thuộc locale provider và tập dữ liệu được dùng; cần kiểm thử thực nghiệm trên runtime mục tiêu.

## 26. Thread safety và locale

`BreakIterator` là iterator **có trạng thái**: `setText` và việc di chuyển `first`/`next` thay đổi trạng thái phân tích. Vì vậy không nên chia sẻ một instance đang hoạt động giữa nhiều luồng/request mà không đồng bộ.

Ví dụ không nên:

~~~java
// Không chia sẻ mutable iterator này cho nhiều request:
static final BreakIterator SHARED =
        BreakIterator.getWordInstance(Locale.ENGLISH);
~~~

Nếu request A gọi `SHARED.setText(textA)` còn request B gọi `SHARED.setText(textB)`, vị trí và văn bản của A có thể bị thay đổi ngay trong quá trình A đang xử lý. Nên tạo iterator riêng cho mỗi thao tác hoặc dùng bản sao/cơ chế quản lý vòng đời an toàn.

Tương tự, locale của người dùng phải rõ ràng. Không đổi `Locale.setDefault(...)` theo từng request vì default locale là trạng thái chung của JVM. Hãy truyền `Locale` vào `getWordInstance(locale)`, và quyết định có cần một **ngôn ngữ phân tích** riêng với **locale hiển thị** không, nhất là khi văn bản nguồn và người dùng thuộc những ngôn ngữ khác nhau.

## 27. Cách kiểm thử bộ tách từ đa ngôn ngữ

Một bộ test nghiêm túc nên có ít nhất:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Tiếng Anh có dấu câu sát chữ | `split(" ")` bỏ sót ranh giới; tokenizer có xử lý đúng ý muốn không? |
| Các dấu cách liên tiếp/tab/newline | Chính sách trường rỗng và delimiter |
| NBSP/NARROW NBSP/IDEOGRAPHIC SPACE | Regex mặc định và Unicode khác nhau |
| Tiếng Trung/Nhật không dấu cách giữa các từ | Không nhầm code point count với word count |
| Tiếng Thái/Lào/Khmer | Đánh giá trên dữ liệu từ vựng của ngôn ngữ thực tế |
| Tiếng Việt đa âm tiết | Các cụm “học sinh”, “công nghệ thông tin” |
| Apostrophe/dấu nối/viết tắt | `don't`, `l'amour`, `e-mail`, `TP.HCM` |
| Số thập phân và nhóm số | `3.14`, `1,234`, số có NBSP |
| Dấu kết hợp và emoji | Không cắt hỏng code point/grapheme |
| Chuỗi rỗng/toàn whitespace | Đếm và lọc đúng theo hợp đồng |
| Highlight với offsets | Offset UTF-16 khớp chuỗi gốc |
| JDK/provider đổi phiên bản | Ranh giới token có thể thay đổi |
| Nhiều request đồng thời | Không chia sẻ `BreakIterator` mutable |
| Nhiều ngôn ngữ trộn trong một câu | Không giả định một locale xử lý hoàn hảo |

Để đánh giá NLP segmentation, cần **gold-standard test corpus** hoặc nhãn đúng được xác nhận bởi người dùng/ngôn ngữ, thay vì chỉ so sánh số token. Có thể đo precision/recall/F1 theo ranh giới từ nếu miền dữ liệu đòi hỏi.

## 28. Bài tập Java: phân biệt “split theo whitespace” và “word-like segments”

Tạo **`SegmentationCompare.java`**:

~~~java
import java.text.BreakIterator;
import java.util.Arrays;
import java.util.Locale;

public class SegmentationCompare {
    static int countWordLike(String input, Locale locale) {
        BreakIterator iterator =
                BreakIterator.getWordInstance(locale);
        iterator.setText(input);

        int count = 0;
        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {

            String segment = input.substring(start, end);
            if (segment.codePoints()
                    .anyMatch(Character::isLetterOrDigit)) {
                count++;
            }
        }
        return count;
    }

    public static void main(String[] args) {
        String text = "Hello, world! Java 17.";

        System.out.println(
                Arrays.toString(text.split(" ")));
        System.out.println(countWordLike(text, Locale.ENGLISH));

        String noSpaces = "Hello,world";
        System.out.println(noSpaces.split(" ").length);
    }
}
~~~

~~~bash
javac SegmentationCompare.java
java SegmentationCompare
~~~

Kết quả theo bộ quy tắc JDK 17 tiếng Anh thông dụng:

~~~text
[Hello,, world!, Java, 17.]
4
1
~~~

Lưu ý cách hiển thị `Arrays.toString` thêm dấu phẩy để phân cách phần tử mảng; vì phần tử đầu là `Hello,`, nên trong output có hai dấu phẩy đứng gần nhau (`Hello,,`) là **đúng cú pháp hiển thị mảng**, không phải lỗi parse.

Đoạn `noSpaces` không chứa U+0020 nên `split(" ").length == 1`, dù giữa `Hello` và `world` có dấu phẩy. Bộ `BreakIterator` nhìn nhận được ranh giới khác với dấu cách khi phù hợp.

## 29. Sai lầm thường gặp

1. **“Mỗi dấu cách phân tách một từ.”** Không đúng cho nhiều ngôn ngữ và cả những văn bản có dấu câu đặc biệt.
2. **“Không có dấu cách nghĩa là chỉ có một từ.”** Sai với nhiều hệ chữ viết CJK/Đông Nam Á.
3. **“Tiếng Việt có khoảng trắng nên tách từ đã xong.”** Không: từ vựng có thể gồm nhiều tiếng cách nhau bởi dấu cách.
4. **“`split("\\s+")` là Unicode word segmentation.”** Không: nó chỉ tách tại tập whitespace của regex.
5. **“`(?U)\\s+` giải quyết mọi ngôn ngữ.”** Nó mở rộng bộ ký tự delimiter, không biết ranh giới từ.
6. **“Dấu câu luôn ngăn cách từ.”** Apostrophe, dấu nối, dấu chấm trong số/URL có vai trò khác nhau.
7. **“`BreakIterator` chỉ trả các từ.”** Nó trả **ranh giới**; dấu câu/whitespace có thể là đoạn riêng.
8. **“`BreakIterator` luôn đúng như từ điển cho mọi locale.”** Chất lượng phụ thuộc runtime, dữ liệu và mục tiêu.
9. **“`Character.isLetterOrDigit` xác định mọi token đúng nghĩa.”** Không nhận diện cấu trúc đa từ, dấu kết hợp và token chuyên ngành.
10. **“Một code point luôn là một ký tự hiển thị.”** Grapheme cluster có thể chứa nhiều code point.
11. **“Offset của BreakIterator là số code point.”** API trên `String` làm việc theo offset UTF-16.
12. **“Cứ bỏ mọi whitespace Unicode là không thay đổi ý nghĩa.”** Khoảng trắng không ngắt có thể giữ các cụm quan trọng.
13. **“Dùng `\b` regex thay BreakIterator là tương đương.”** Word boundary regex không phải linguistic segmentation.
14. **“Chuỗi đã NFC thì tự phân đoạn từ đúng.”** Unicode normalization xử lý biểu diễn, không phân định từ.
15. **“Có thể chia sẻ một `BreakIterator` cho mọi request.”** Iterator có trạng thái mutable.
16. **“Word count là đại lượng tuyệt đối không phụ thuộc ngôn ngữ.”** Cần công bố phép đếm và mục tiêu của sản phẩm.

## 30. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `"Hello,world".split(" ")` chỉ trả một phần tử?

**Đáp án:** Vì chuỗi không chứa U+0020; dấu phẩy không khớp delimiter dấu cách.

**Câu 2.** Bật `(?U)` trong Java regex có tạo bộ tách từ tiếng Thái chính xác không?

**Đáp án:** Không. Nó làm các lớp ký tự như `\s` hiểu Unicode hơn, nhưng vẫn không xác định từ theo từ điển tiếng Thái.

**Câu 3.** Tại sao “học sinh” trong tiếng Việt không nên bị mặc định coi là hai từ vựng?

**Đáp án:** Khoảng trắng trong tiếng Việt thường phân cách các tiếng; “học sinh” có thể là một đơn vị từ vựng nhiều tiếng.

**Câu 4.** `BreakIterator.getWordInstance` trả về những gì?

**Đáp án:** Những vị trí ranh giới theo quy tắc locale/provider. Các đoạn bao gồm cả punctuation và whitespace, không chỉ từ.

**Câu 5.** Tại sao dùng `Character.isLetterOrDigit` để đếm từ có thể sai?

**Đáp án:** Nó chỉ phân loại code point; không hiểu dấu nối, apostrophe, từ ghép hoặc segmentation không có dấu cách.

**Câu 6.** Khi cần bôi đen một đoạn theo offset của `BreakIterator`, nên dùng offset theo code point hay UTF-16?

**Đáp án:** `BreakIterator` dùng offset phù hợp `String.substring`, tức **chỉ số UTF-16 code unit**.

**Câu 7.** U+00A0 và U+202F cần chú ý gì?

**Đáp án:** Đây là khoảng trắng không ngắt; chúng có thể không được regex `\s` mặc định của Java khớp và có ý nghĩa trình bày đặc biệt.

**Câu 8.** `Normalizer` có thay thế tokenizer hay không?

**Đáp án:** Không; nó chuẩn hóa biểu diễn Unicode, không tự phân tích ranh giới từ theo nghĩa ngôn ngữ.

**Câu 9.** Nếu xử lý một danh sách ID có delimiter `;` được hợp đồng xác định rõ, có cần tokenizer NLP không?

**Đáp án:** Không nhất thiết. Dùng parser/split phù hợp với đặc tả delimiter, escaping và trường rỗng của dữ liệu.

**Câu 10.** Để đếm token tìm kiếm cho văn bản tiếng Nhật chuyên ngành, có thể chỉ dùng `split(" ")` không?

**Đáp án:** Không. Cần lựa chọn/đánh giá bộ phân đoạn phù hợp với ngôn ngữ và mục tiêu tìm kiếm.

## 31. Quy trình lựa chọn giải pháp trong dự án Java

1. **Xác định nhiệm vụ**: tách trường theo giao thức, đếm cụm whitespace, word boundary UI, word segmentation NLP, hay tokenization tìm kiếm.
2. **Kiểm tra cấu trúc input**: có dùng dấu cách làm delimiter thật không? Có quote, dấu câu, NBSP, emoji, kết hợp nhiều script không?
3. **Chọn bộ quy tắc rõ ràng**: `String.split` cho delimiter đơn giản; regex Unicode cho whitespace policy; `BreakIterator` cho boundary analysis; tokenizer từ điển/mô hình cho yêu cầu từ vựng.
4. **Truyền locale tường minh** khi dùng `BreakIterator`, không đổi default JVM theo request.
5. **Duy trì dữ liệu gốc nếu cần highlight**: ranh giới trả offset trên chuỗi được phân tích; normalization hoặc biến đổi văn bản có thể thay offsets.
6. **Xử lý code point/grapheme an toàn** trong các chức năng cắt văn bản, con trỏ và giới hạn độ dài.
7. **Đặt tên kết quả đúng nghĩa**: “số trường”, “số đoạn giống từ”, “số token NLP” và “số từ vựng” không mặc nhiên bằng nhau.
8. **Kiểm thử văn bản đa ngôn ngữ thật** và các trường hợp biên, nhất là CJK, Thái, Việt, dấu câu và Unicode whitespace.
9. **Ghi rõ phiên bản JDK/provider/tokenizer** nếu tính nhất quán của word count hoặc search index ảnh hưởng nghiệp vụ.

**Ghi nhớ:** Dấu cách là **một ký tự hoặc một nhóm ký tự phân cách**, còn **từ** là một đơn vị ngôn ngữ có thể được viết và xác định theo nhiều quy tắc. `split(" ")` chỉ giải quyết delimiter U+0020; regex `\s` giải quyết một tập whitespace; `BreakIterator` tìm ranh giới văn bản theo locale; và nhiều ngôn ngữ/bài toán vẫn cần **bộ phân đoạn từ chuyên biệt**. Không nhầm các lớp này để tránh sai số từ, tìm kiếm sai và xử lý văn bản Unicode thiếu chính xác.

**Tài liệu Java SE 17:** [BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html), [Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), [String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html).