# BreakIterator cho ký tự, từ, câu và vị trí ngắt dòng trong Java

## 1. Vì sao không thể tách văn bản đa ngôn ngữ chỉ bằng chỉ số hoặc dấu cách?

Trong Java, `String` lưu văn bản dưới dạng các **đơn vị mã UTF-16** (*code units*). Một từ hay một ký tự mà người dùng cảm nhận trên màn hình không nhất thiết chiếm đúng một phần tử UTF-16:

- Chữ có dấu có thể được biểu diễn bằng một code point dựng sẵn hoặc nhiều code points kết hợp.
- Emoji ngoài BMP thường chiếm hai UTF-16 code units; emoji phức hợp có thể chứa nhiều code points và ký tự nối.
- Không phải ngôn ngữ nào cũng có dấu cách giữa các từ.
- Ranh giới câu khác ranh giới dấu chấm: dấu chấm còn có thể xuất hiện trong chữ viết tắt hoặc số.
- Ngắt dòng đúng chỗ không phải chỉ tìm ký tự `\n`; bố cục cần biết **những vị trí có thể xuống dòng**.

Vì vậy, mã kiểu:

```java
String first = text.substring(0, 1);
String[] words = text.split(" ");
String[] sentences = text.split("\\.");
```

có thể sai ngữ nghĩa hoặc cắt giữa các thành phần Unicode. Đó là **mảnh mã minh họa**, không phải lời khuyên áp dụng. `substring(0,1)` chỉ lấy một code unit, `split(" ")` chỉ hiểu dấu cách ASCII, `split("\\.")` giả định dấu chấm luôn kết thúc câu.

Java có `java.text.BreakIterator` để tìm **các ranh giới của văn bản theo loại và theo `Locale`**. Các loại chính là:

1. `getCharacterInstance(locale)` — ranh giới các cụm ký tự được xem như ký tự trong một mô hình phân đoạn.
2. `getWordInstance(locale)` — ranh giới từ và các đoạn khác.
3. `getSentenceInstance(locale)` — ranh giới câu.
4. `getLineInstance(locale)` — các **cơ hội ngắt dòng**.

`BreakIterator` không thực hiện toàn bộ công việc của bộ tokenizer ngôn ngữ, bộ phát hiện emoji hiện đại, engine hiển thị hoặc layout engine. Nó cung cấp những **vị trí ranh giới** mà chương trình có thể duyệt và sử dụng theo nhu cầu.

## 2. Khởi tạo BreakIterator theo loại và Locale

`BreakIterator` là lớp trừu tượng; thông thường nhận một instance từ factory:

```java
import java.text.BreakIterator;
import java.util.Locale;

BreakIterator characters =
        BreakIterator.getCharacterInstance(Locale.US);
BreakIterator words =
        BreakIterator.getWordInstance(Locale.US);
BreakIterator sentences =
        BreakIterator.getSentenceInstance(Locale.US);
BreakIterator lines =
        BreakIterator.getLineInstance(Locale.US);
```

Những cách khởi tạo không tham số như `getWordInstance()` sử dụng **default locale của JVM**. Trong ứng dụng phục vụ người dùng từ nhiều vùng, không nên để locale mặc định của server âm thầm quyết định phân đoạn của từng người dùng.

Sau khi tạo instance, **bắt buộc truyền văn bản**:

```java
words.setText("Hello, world!");
```

`BreakIterator` giữ trạng thái văn bản và vị trí duyệt. Khi đổi sang chuỗi khác, gọi `setText(...)` lại. Có thể dùng một iterator cho các chuỗi khác nhau theo trình tự nhưng không nên sử dụng cùng instance mutable cho nhiều luồng chạy đồng thời.

Mỗi factory trả một iterator có **chiến lược phân đoạn khác nhau**, không phải chỉ là bốn tên gọi của một thuật toán giống nhau. Các kết quả cụ thể có thể thay đổi theo `Locale`, JDK, nhà cung cấp dữ liệu locale và phiên bản dữ liệu Unicode.

## 3. Mô hình ranh giới: chỉ số bắt đầu và kết thúc

Khi duyệt một chuỗi, `BreakIterator` trả về **các chỉ số ranh giới**, không trực tiếp trả `String` cho mỗi từ/câu.

Giả sử có chuỗi:

```text
Hello, world!
```

Các ranh giới là các vị trí **giữa** ký tự, bao gồm vị trí bắt đầu 0 và vị trí cuối bằng `text.length()`. Một đoạn văn bản được biểu diễn bằng khoảng:

```text
[start, end)
```

- `start` **bao gồm** ký tự tại vị trí đó.
- `end` **không bao gồm** ký tự tại vị trí đó.
- Lấy đoạn bằng `text.substring(start, end)`.
- Chiều dài đoạn theo UTF-16 là `end - start`.

Ví dụ `"Hello"` là `[0,5)`; dấu phẩy nằm tại `[5,6)` và một khoảng trắng sau đó ở `[6,7)`.

Bốn API liên quan đến duyệt:

| Phương thức | Ý nghĩa |
|---|---|
| `first()` | Đặt và trả chỉ số ranh giới đầu tiên |
| `last()` | Đặt và trả chỉ số ranh giới cuối cùng |
| `next()` | Sang ranh giới sau; trả `BreakIterator.DONE` nếu hết |
| `previous()` | Về ranh giới trước; trả `DONE` nếu hết |
| `current()` | Trả ranh giới hiện tại, không tự di chuyển |
| `following(offset)` | Ranh giới **sau** chỉ số cho trước |
| `preceding(offset)` | Ranh giới **trước** chỉ số cho trước |
| `isBoundary(offset)` | Kiểm tra một vị trí có phải ranh giới không |
| `setText(String)` | Thay toàn bộ văn bản đầu vào |

`BreakIterator.DONE` là giá trị sentinel, không phải một offset hợp lệ để đưa vào `substring`. Phải kiểm tra nó trước khi cắt chuỗi.

Các chỉ số dùng trong ví dụ có cùng đơn vị với `String.length()` và `substring(...)`: **UTF-16 code units**, không phải byte UTF-8, số code points hay số grapheme nhìn thấy.

## 4. Mẫu duyệt chuẩn từ trái sang phải

Cấu trúc thường dùng:

```java
iterator.setText(text);
int start = iterator.first();

for (int end = iterator.next();
     end != BreakIterator.DONE;
     start = end, end = iterator.next()) {

    String segment = text.substring(start, end);
    // Xử lý segment theo loại iterator.
}
```

Đây là **mảnh mã minh họa**, giả định `iterator` và `text` đã được tạo trong phương thức.

Quy trình:

1. `first()` lấy ranh giới đầu tiên.
2. `next()` cho ranh giới kế tiếp.
3. Cặp `start, end` xác định một đoạn `[start,end)`.
4. Sau xử lý, `start` trở thành `end` trước đó.
5. Lặp tới `DONE`.

Lý do cần dùng `end = iterator.next()` thay vì `start + 1` là một đoạn có thể chứa nhiều code units; ranh giới phải đến từ **quy tắc phân đoạn**, không phải phép cộng chỉ số tùy ý.

Có thể duyệt ngược:

```java
for (int end = iterator.last(), start = iterator.previous();
     start != BreakIterator.DONE;
     end = start, start = iterator.previous()) {

    String segment = text.substring(start, end);
}
```

Mẫu ngược phù hợp khi cần tìm từ/cuối câu gần con trỏ, nhưng vẫn phải xử lý `DONE` và không nhầm thứ tự `start/end`.

## 5. Character BreakIterator: ký tự cảm nhận và Unicode

### Code unit, code point và cụm ký tự khác nhau

Trong Java, ít nhất ba khái niệm cần phân biệt:

- **UTF-16 code unit:** đơn vị 16 bit; `String.length()` đếm đơn vị này.
- **Unicode code point:** một giá trị Unicode, có thể chiếm một hoặc hai UTF-16 code units.
- **Cụm ký tự/ngữ tố hiển thị (*grapheme cluster*):** đơn vị mà người dùng thường cảm nhận như một ký tự, có thể bao gồm nhiều code points.

Chẳng hạn:

```java
String s = "a\u0301b";
System.out.println(s.length()); // 3
```

Trong chuỗi này, `a` + dấu sắc kết hợp có thể tạo thành một cụm hiển thị; chữ `b` là cụm tiếp theo. Nếu phân tách từng code unit, bạn sẽ tách dấu sắc khỏi chữ cơ sở.

`BreakIterator.getCharacterInstance(locale)` cho các ranh giới **character** nhằm hỗ trợ phân đoạn gần hơn với đơn vị văn bản mà người dùng cảm nhận, thay vì luôn bước từng code unit.

### Ví dụ Java 17+ độc lập: chữ với dấu kết hợp

Lưu `CharacterBreakDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class CharacterBreakDemo {
    public static void main(String[] args) {
        String text = "a\u0301b";
        BreakIterator iterator =
                BreakIterator.getCharacterInstance(Locale.US);
        iterator.setText(text);

        System.out.println("length=" + text.length());

        for (int start = iterator.first(),
                 end = iterator.next();
             end != BreakIterator.DONE;
             start = end, end = iterator.next()) {

            System.out.printf(
                    "[%d,%d)=%s%n",
                    start, end, text.substring(start, end));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac CharacterBreakDemo.java
java CharacterBreakDemo
```

Kết quả đã kiểm chứng:

```text
length=3
[0,2)=á
[2,3)=b
```

Đoạn đầu gồm hai code units `a` và dấu kết hợp, nhưng có thể hiển thị như một ký tự có dấu. Việc sử dụng ranh giới character phù hợp hơn `substring(0,1)` khi bạn cần di chuyển con trỏ hoặc cắt đoạn văn bản hiển thị.

### Emoji và giới hạn phân đoạn trong JDK

Với một emoji đơn giản nằm ngoài BMP, `String.length()` có thể bằng 2 trong khi `codePointCount(...)` bằng 1. Ví dụ Java với surrogate pair được viết bằng escape:

```java
String emoji = "\uD83D\uDE42"; // U+1F642
System.out.println(emoji.length()); // 2
System.out.println(
        emoji.codePointCount(0, emoji.length())); // 1
```

Nhiều triển khai `BreakIterator` nhận ra cặp surrogate thông thường và không chia giữa hai code units. Tuy nhiên, **không được tuyên bố API này hoàn hảo cho mọi cụm emoji hiện đại**. Emoji có thể chứa skin-tone modifiers, dấu nối zero-width joiner, regional indicators và các chuỗi phức hợp; mức hỗ trợ phụ thuộc dữ liệu/phiên bản phân đoạn của runtime.

Nếu editor chuyên nghiệp, UI xử lý emoji phức tạp hoặc bộ đếm grapheme cần đúng tiêu chuẩn Unicode cập nhật, hãy kiểm thử bằng dữ liệu thực và cân nhắc thư viện segmentation chuyên dụng như ICU4J. Đừng dùng `codePointCount()` như một giải pháp tương đương grapheme segmentation: **code point không phải grapheme cluster**.

## 6. Word BreakIterator: từ và các đoạn không phải từ

`getWordInstance(locale)` tạo ranh giới dạng **word**. Nó không chỉ trả danh sách các từ có nghĩa; các đoạn gồm dấu câu, khoảng trắng hoặc số cũng có thể xuất hiện.

Với:

```text
Hello, world! 42.
```

Các đoạn quan sát trong môi trường JDK dùng cho bài:

| Vùng `[start,end)` | Segment |
|---|---|
| `[0,5)` | `Hello` |
| `[5,6)` | `,` |
| `[6,7)` | Khoảng trắng |
| `[7,12)` | `world` |
| `[12,13)` | `!` |
| `[13,14)` | Khoảng trắng |
| `[14,16)` | `42` |
| `[16,17)` | `.` |

**Không** gọi mọi đoạn `substring(start,end)` của word iterator là một “từ” trong bộ tokenizer. Nếu ứng dụng muốn lọc chỉ các đoạn chứa chữ hoặc số, cần thêm bước kiểm tra.

Ví dụ:

```java
boolean containsLetterOrDigit =
        segment.codePoints().anyMatch(
                Character::isLetterOrDigit);
```

Đây chỉ là bộ lọc thô, phù hợp cho demo. Một **tokenizer** sản phẩm có thể phải giữ dấu nháy, dấu gạch nối, số thập phân, emoji, hashtag, tên riêng hoặc đơn vị theo grammar riêng.

### Ví dụ Java 17+ độc lập về phân đoạn từ

Lưu `WordBreakDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class WordBreakDemo {
    public static void main(String[] args) {
        String text = "Hello, world! 42.";
        BreakIterator words =
                BreakIterator.getWordInstance(Locale.US);
        words.setText(text);

        for (int start = words.first(), end = words.next();
             end != BreakIterator.DONE;
             start = end, end = words.next()) {

            String segment = text.substring(start, end);
            String printable = segment.replace(" ", "_");

            System.out.printf(
                    "[%d,%d)=%s%n", start, end, printable);
        }
    }
}
```

Chạy:

```bash
javac WordBreakDemo.java
java WordBreakDemo
```

Output:

```text
[0,5)=Hello
[5,6)=,
[6,7)=_
[7,12)=world
[12,13)=!
[13,14)=_
[14,16)=42
[16,17)=.
```

Trong output, dấu `_` chỉ là **ký hiệu thay thế để dễ nhìn** cho một dấu cách ASCII; văn bản gốc chưa bị sửa.

### Ngôn ngữ không tách từ bằng dấu cách

Với tiếng Thái, tiếng Trung, tiếng Nhật hoặc các hệ chữ khác, ý niệm ranh giới “từ” có thể cần từ điển, mô hình phân đoạn hoặc quy tắc đặc biệt. `BreakIterator` theo locale là điểm bắt đầu, không bảo đảm độ chính xác như tokenizer ngôn ngữ chuyên dụng hoặc kết quả của các công cụ tìm kiếm. Thậm chí các JDK/locale provider khác nhau có thể cho ranh giới khác nhau.

Đối với tiếng Việt, dấu cách thường chia **âm tiết** nhưng không phải lúc nào chia **từ ghép**. Ví dụ `"học sinh"` có khoảng trắng giữa hai tiếng nhưng có thể được xem là một đơn vị từ vựng theo tác vụ. Nếu cần tìm kiếm, tách từ NLP hay chỉ mục, phải chọn bộ tokenizer phù hợp thay vì mặc định word BreakIterator đã hiểu mọi từ ghép tiếng Việt.

## 7. Sentence BreakIterator: điểm kết thúc câu

`BreakIterator.getSentenceInstance(locale)` nhận diện ranh giới câu dựa trên quy tắc phân đoạn câu. Nó không chỉ thực hiện `text.split("\\.")`.

Ví dụ:

```text
Hello world! How are you? Fine.
```

Với `Locale.US`, các đoạn được quan sát:

```text
[0,13)=Hello world!_
[13,26)=How are you?_
[26,31)=Fine.
```

Dấu `_` ở đây dùng để biểu diễn **khoảng trắng cuối mỗi câu**. Điều này rất quan trọng: các khoảng mà sentence iterator trả lại có thể **bao gồm cả khoảng trắng sau dấu câu**, vì ranh giới được xác định theo văn bản, không phải theo yêu cầu trim mọi câu.

### Ví dụ Java 17+ hoàn chỉnh

Lưu `SentenceBreakDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class SentenceBreakDemo {
    public static void main(String[] args) {
        String text = "Hello world! How are you? Fine.";
        BreakIterator sentences =
                BreakIterator.getSentenceInstance(Locale.US);
        sentences.setText(text);

        for (int begin = sentences.first(),
                 end = sentences.next();
             end != BreakIterator.DONE;
             begin = end, end = sentences.next()) {

            String segment =
                    text.substring(begin, end).replace(" ", "_");
            System.out.printf(
                    "[%d,%d)=%s%n", begin, end, segment);
        }
    }
}
```

Chạy:

```bash
javac SentenceBreakDemo.java
java SentenceBreakDemo
```

Output:

```text
[0,13)=Hello_world!_
[13,26)=How_are_you?_
[26,31)=Fine.
```

Chương trình không bỏ ký tự nào của chuỗi gốc: các đoạn ghép liên tục theo thứ tự sẽ tái tạo đúng văn bản ban đầu, vì iterator chỉ cung cấp **các điểm ngắt**.

### Bẫy dấu chấm viết tắt

Các chuỗi như `"Dr. Smith arrived."` hoặc `"Version 1.2 is ready."` có dấu chấm nhưng không phải dấu nào cũng kết thúc câu. Sentence BreakIterator được thiết kế tốt hơn việc split thẳng theo dấu chấm, nhưng việc nhận diện chữ viết tắt, tên riêng và ngữ cảnh có thể vẫn không hoàn hảo.

Nếu một ứng dụng cần sentence segmentation cho NLP hoặc trích xuất văn bản pháp lý/y tế, nên bổ sung test theo domain và cân nhắc engine chuyên dụng thay vì mặc định ranh giới từ BreakIterator luôn chính xác về mặt ngữ nghĩa.

## 8. Line BreakIterator: vị trí có thể xuống dòng, không phải các dòng sẵn có

`BreakIterator.getLineInstance(locale)` trả ranh giới **ngắt dòng tiềm năng** (*line break opportunities*) theo quy tắc ngôn ngữ và cách phân tách văn bản. Nó **không** tính chiều rộng font, kích thước container hay số pixel.

Ví dụ:

```text
Hello world again.
```

Với `Locale.US`, những đoạn được quan sát:

```text
[0,6)=Hello_
[6,12)=world_
[12,18)=again.
```

Các vị trí ngắt hợp lệ được báo là 6, 12 và 18, theo phân đoạn trong ví dụ; dấu `_` đại diện cho khoảng trắng. Nếu ứng dụng có vùng vẽ rất rộng, có thể không xuống dòng tại 6 hay 12. Nếu vùng hẹp, engine layout cần chọn một cơ hội ngắt thích hợp dựa trên số đo glyph và chính sách bố cục.

### Ví dụ Java 17+ độc lập

Lưu `LineBreakDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class LineBreakDemo {
    public static void main(String[] args) {
        String text = "Hello world again.";
        BreakIterator lines =
                BreakIterator.getLineInstance(Locale.US);
        lines.setText(text);

        for (int start = lines.first(), end = lines.next();
             end != BreakIterator.DONE;
             start = end, end = lines.next()) {

            System.out.printf(
                    "[%d,%d)=%s%n",
                    start,
                    end,
                    text.substring(start, end).replace(" ", "_"));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac LineBreakDemo.java
java LineBreakDemo
```

Output:

```text
[0,6)=Hello_
[6,12)=world_
[12,18)=again.
```

**Không nên coi các đoạn của line iterator là kết quả dàn trang**. Chỉ số ngắt dòng còn phải kết hợp với:

- Chiều rộng vùng hiển thị và font thực tế.
- Độ rộng glyph, shaping, ligature và hướng viết.
- Ngắt dòng bắt buộc do `\n`, `\r\n` hoặc các ký tự điều khiển xuống dòng.
- Quy tắc không được ngắt trước/sau một số dấu câu.
- Chính sách xử lý từ dài không có vị trí ngắt phù hợp.
- Quy tắc hyphenation nếu hệ thống có hỗ trợ.

Với Swing/JavaFX hoặc công cụ layout, ưu tiên cơ chế layout của thư viện UI. BreakIterator giúp **tìm ứng viên ngắt**, không thay cho engine render.

## 9. Một ví dụ Java 17+ dùng chung bộ duyệt ranh giới

Có thể tránh lặp mã trong ứng dụng bằng cách viết một phương thức nhận `BreakIterator` đã tạo:

```java
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;

public class BoundarySegments {
    public static List<String> segments(
            String text, BreakIterator iterator) {

        iterator.setText(text);
        List<String> result = new ArrayList<>();

        for (int begin = iterator.first(), end = iterator.next();
             end != BreakIterator.DONE;
             begin = end, end = iterator.next()) {

            result.add(text.substring(begin, end));
        }

        return result;
    }
}
```

Đây là một class Java hợp lệ biên dịch được, chứa phương thức tiện ích, nhưng **không có `main`** và không thể chạy trực tiếp bằng `java BoundarySegments`. Nó được gọi từ class khác hoặc unit test:

```java
List<String> parts = BoundarySegments.segments(
        "Hello world!",
        BreakIterator.getWordInstance(Locale.US));
```

Nếu muốn đoạn gọi trên chạy trong class riêng, cần import `List`, `Locale` và `BreakIterator`.

Với method này, **đoạn trả về có thể là dấu câu hoặc khoảng trắng**. Không đặt tên kết quả là `wordsOnly` khi dùng word iterator. Nếu cần thông tin offset để highlight hoặc đặt con trỏ, nên trả một kiểu dữ liệu `Segment(start,end,text)` thay vì chỉ trả chuỗi.

### Thiết kế kiểu Segment rõ ràng

Trong Java 17 có thể khai báo record:

```java
record Segment(int start, int end, String text) {}
```

Khi tạo danh sách, thêm `new Segment(begin, end, text.substring(begin,end))`. Record giúp code bên ngoài có thể truy cập các vị trí bằng `start()`, `end()` và `text()` mà không phải tự cộng lại độ dài các segment.

Nếu dữ liệu được chuẩn hóa Unicode hoặc thay dấu cách trước khi phân đoạn, các offset chỉ hợp lệ đối với **chuỗi cụ thể đã đưa vào iterator**, không tự động trùng với raw input ban đầu.

## 10. Tìm ranh giới gần vị trí con trỏ: following, preceding, isBoundary

Ngoài duyệt toàn bộ, một editor hoặc form nhập liệu thường cần:

- Tìm điểm kết thúc từ sau vị trí con trỏ.
- Nhảy về đầu từ trước vị trí con trỏ.
- Kiểm tra vị trí con trỏ có nằm đúng ranh giới phân đoạn không.

Các phương thức:

```java
int after = iterator.following(offset);
int before = iterator.preceding(offset);
boolean boundary = iterator.isBoundary(offset);
```

Ý nghĩa cần nhớ:

- `following(offset)` trả ranh giới **lớn hơn** offset, không chỉ lớn hơn hoặc bằng.
- `preceding(offset)` trả ranh giới **nhỏ hơn** offset.
- `isBoundary(offset)` cho biết offset có phải ranh giới; hãy lưu ý phương thức này có thể thay đổi vị trí nội bộ của iterator theo hợp đồng API.
- Khi không còn ranh giới theo hướng yêu cầu, trả `BreakIterator.DONE`; không chuyển sentinel này sang `substring`.

### Ví dụ Java 17+ độc lập

Lưu `BoundaryNavigationDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class BoundaryNavigationDemo {
    public static void main(String[] args) {
        BreakIterator it =
                BreakIterator.getWordInstance(Locale.US);
        it.setText("Hello, world! 42.");

        System.out.println("following0=" + it.following(0));
        System.out.println("preceding8=" + it.preceding(8));
        System.out.println("isBoundary5=" + it.isBoundary(5));
        System.out.println("isBoundary6=" + it.isBoundary(6));
    }
}
```

Chạy:

```bash
javac BoundaryNavigationDemo.java
java BoundaryNavigationDemo
```

Kết quả kiểm chứng:

```text
following0=5
preceding8=7
isBoundary5=true
isBoundary6=true
```

Với chuỗi ví dụ, vị trí 7 bắt đầu từ `world`. `preceding(8)` trả `7`, tức ranh giới ngay trước offset 8. `following(0)` trả `5`, tức sau `Hello`.

**Cẩn thận trạng thái:** sau khi gọi `following`, `preceding` hay `isBoundary`, vị trí hiện tại của iterator có thể thay đổi. Nếu sau đó muốn duyệt từ đầu, hãy gọi `first()`; nếu muốn duyệt từ cuối, gọi `last()`. Không tiếp tục dựa vào `current()` cũ mà không kiểm tra.

## 11. Không nhầm ranh giới với phân tích ngữ nghĩa

Bốn loại iterator giải quyết những mức khác nhau:

| Mục tiêu | Iterator phù hợp | Chưa tự giải quyết |
|---|---|---|
| Di chuyển qua các cụm ký tự | Character | Mọi emoji grapheme sequence hiện đại, shaping/rendering |
| Chia văn bản thành các đoạn từ/dấu câu | Word | Full tokenizer, từ ghép/ngữ pháp |
| Tìm các điểm ngắt câu | Sentence | Hiểu ngữ nghĩa và mọi chữ viết tắt |
| Tìm cơ hội xuống dòng | Line | Đo chiều rộng và layout thực tế |

Chẳng hạn một ứng dụng soạn thảo có thể dùng:

- Character boundaries để xử lý nhảy con trỏ/selection.
- Word boundaries để chọn từ khi double-click.
- Sentence boundaries để chọn hoặc xử lý một câu.
- Line boundaries để giúp layout tìm điểm ngắt.

Nhưng **cùng một offset** có thể là ranh giới ở chế độ này mà không phải ranh giới ở chế độ khác. Không dùng các ranh giới word như đại diện cho ký tự, hoặc các ranh giới line để đo độ dài từ.

## 12. Unicode normalization và offset

Chuẩn hóa Unicode có thể biến đổi độ dài chuỗi. Ví dụ:

```java
String raw = "a\u0301";
String nfc = java.text.Normalizer.normalize(
        raw, java.text.Normalizer.Form.NFC);

System.out.println(raw.length()); // 2
System.out.println(nfc.length()); // 1
```

Đây là mảnh code minh họa. Nếu chạy BreakIterator trên `nfc`, các ranh giới chỉ tương ứng với **chuỗi nfc**. Không được dùng chúng trực tiếp để cắt `raw` nếu đã thay đổi độ dài hoặc thứ tự mã Unicode.

Một pipeline xử lý văn bản cần quyết định:

1. Giữ raw text hay dùng normalized text để render.
2. BreakIterator chạy trên phiên bản nào.
3. Search index và highlight dùng cùng phiên bản hay có bảng ánh xạ offset.
4. Selection và con trỏ được lưu theo hệ chỉ số nào.

Một số lỗi UI chỉ xuất hiện với dấu tiếng Việt ở dạng combining, nên cần test cả dạng dựng sẵn lẫn dạng phân rã.

## 13. Ranh giới phân đoạn phụ thuộc Locale và runtime

`BreakIterator` có các overload dùng `Locale`:

```java
Locale vietnamese = Locale.forLanguageTag("vi-VN");
BreakIterator wordIterator =
        BreakIterator.getWordInstance(vietnamese);
```

Nhưng có hai điều phải tách biệt:

**Một:** truyền locale giúp implementation chọn các quy tắc phân đoạn tương ứng khi có hỗ trợ.

**Hai:** kết quả phân đoạn **không được đảm bảo đồng nhất mọi JDK/provider** và không tự trở thành một bộ tách từ chuẩn ngữ nghĩa cho mọi ngôn ngữ.

Các dữ liệu/chương trình xử lý văn bản dài hạn cần:

- Ghi rõ locale được chọn.
- Test bằng từ/câu thật ở ngôn ngữ mục tiêu.
- Kiểm tra khi nâng cấp JDK hoặc thay provider locale.
- Với bài toán NLP tiếng Việt, xem xét bộ phân tích tiếng Việt riêng thay vì coi không gian giữa các âm tiết luôn là ranh giới từ.
- Với emoji và grapheme phức tạp, kiểm tra phiên bản Unicode được runtime hỗ trợ.

Đừng hardcode các offset demo như `[0,5)` thành quy tắc tổng quát. Chúng chỉ là kết quả cụ thể cho chuỗi cụ thể.

## 14. Giới hạn về hiệu năng và trạng thái

`BreakIterator` là một **iterator có trạng thái**. Mỗi `setText` gắn văn bản mới; `next()` và `previous()` thay đổi vị trí. Vì vậy:

- Không chia sẻ cùng một instance đang thay `setText` giữa nhiều thread mà không quản lý đồng bộ.
- Với từng tác vụ ngắn, tạo instance theo loại và locale hoặc quản lý bản sao riêng.
- Nếu cần chạy trên nhiều chuỗi trong một luồng, có thể tái sử dụng instance và gọi `setText` lại, nhưng không giả định `current()` vẫn hợp lệ cho chuỗi cũ.
- Tránh gọi `setText` ở giữa một vòng duyệt.
- Khi lọc từ, luôn kiểm tra `end != DONE` trước khi cắt chuỗi.

Với văn bản rất dài, việc lưu danh sách tất cả đoạn vào bộ nhớ có thể không cần thiết; có thể xử lý streaming từng `[start,end)`. Nhưng nếu UI cần thao tác tìm ngược/tiến nhiều lần và offset của nhiều đoạn, cache có thể cải thiện hiệu năng trong một số thiết kế.

Không mặc định kết quả phân đoạn ở phiên bản runtime này sẽ là dữ liệu ổn định để lưu vĩnh viễn. Nếu bạn lưu offset lâu dài mà văn bản có thể chỉnh sửa/normalize, phải có cơ chế cập nhật offset.

## 15. Lỗi thường gặp

**1. Tưởng `BreakIterator.getCharacterInstance` luôn bước đúng một `char`.** Các cụm có combining mark có thể chứa nhiều code units.

**2. Tưởng một code point luôn tương đương một grapheme cluster.** Emoji phức tạp hoặc dấu kết hợp có thể gồm nhiều code points.

**3. Tưởng word iterator chỉ trả từ có chữ.** Nó còn trả dấu câu, khoảng trắng, số và các đoạn khác.

**4. Tách từ tiếng Việt bằng dấu cách rồi coi mỗi phần là một từ vựng.** Dấu cách có thể ngăn các âm tiết của một từ ghép.

**5. Tách câu bằng `split("\\.")`.** Không xử lý đầy đủ dấu chấm viết tắt, câu có dấu hỏi/chấm than, và quy tắc locale.

**6. Coi line BreakIterator là engine xuống dòng theo pixel.** Nó chỉ trả cơ hội ngắt, không đo font/container.

**7. Quên `setText` trước khi duyệt.** Iterator không tự biết văn bản hiện tại của ứng dụng.

**8. Không xử lý `DONE`.** Sentinel không thể dùng làm endIndex trong `substring`.

**9. Nhầm `[start,end)` thành khoảng gồm cả end.** `String.substring(start,end)` dùng end-exclusive.

**10. Dùng ranh giới trên văn bản đã normalize để cắt bản raw.** Offset có thể không còn tương ứng.

**11. Dùng default locale không kiểm soát.** Hành vi có thể khác giữa server hoặc người dùng.

**12. Cho rằng BreakIterator luôn xác định chính xác mọi emoji và văn bản đặc thù.** Unicode segmentation và dữ liệu locale còn có giới hạn triển khai.

**13. Tiếp tục dùng current() cũ sau following/preceding/isBoundary.** Iterator có trạng thái thay đổi.

**14. Dùng offset UTF-16 như offset byte UTF-8 hoặc grapheme index.** Cần chuyển đổi chỉ số theo API đích.

**15. Tái sử dụng một instance mutable giữa các request đồng thời.** Có nguy cơ dữ liệu văn bản và ranh giới bị lẫn nhau.

## 16. Checklist kiểm thử

| Tình huống | Điều cần xác nhận |
|---|---|
| Chuỗi ASCII đơn giản | Ghép tất cả segment phải khôi phục đúng chuỗi |
| Chữ có combining mark, như `a\u0301` | Character iterator có thể giữ cụm dấu chung với chữ |
| Emoji một code point ngoài BMP | Không cắt tùy tiện giữa surrogate pair; kiểm tra runtime |
| Emoji nhiều code points/ZWJ | Cần test kỹ, có thể cần ICU4J |
| Dấu câu và khoảng trắng | Word iterator vẫn trả segment không phải từ |
| Các câu nối bằng `!`, `?`, `.` | Sentence boundaries và khoảng trắng sau câu |
| Chữ viết tắt | Không tách máy móc theo dấu chấm |
| Văn bản chứa `\n` hoặc `\r\n` | Phân biệt forced line breaks với các cơ hội ngắt |
| Ngôn ngữ không có dấu cách giữa các từ | Kiểm tra chất lượng theo locale |
| Văn bản đã normalize NFC so với raw NFD | Offset có thể khác |
| Index gần đầu/cuối văn bản | `following/preceding` trả `DONE` đúng lúc |
| Chuỗi rỗng | Không tạo segment và không gọi substring với DONE |
| Phân đoạn trên nhiều thread | Không chia sẻ iterator mutable sai cách |

Một bất biến hữu ích trong unit test: nếu duyệt liên tiếp từ `first()` tới `DONE`, các khoảng `[start,end)` phải nối nhau theo thứ tự và ghép lại thành đúng văn bản đầu vào, miễn là API áp dụng cho toàn bộ chuỗi ban đầu. Test này giúp phát hiện mất khoảng trắng hoặc dấu câu do code xử lý của chính ứng dụng.

## 17. Hỏi đáp tự kiểm tra

**Câu 1.** Bốn factory chính của BreakIterator là gì?

**Đáp án:** `getCharacterInstance`, `getWordInstance`, `getSentenceInstance` và `getLineInstance`, có overload nhận `Locale`.

**Câu 2.** Word BreakIterator có chỉ trả về từ có chữ cái không?

**Đáp án:** Không. Nó có thể trả cả khoảng trắng, dấu câu và các đoạn số; cần lọc theo yêu cầu ứng dụng.

**Câu 3.** Trong chuỗi `"Hello, world! 42."`, đoạn `Hello` nằm ở khoảng nào?

**Đáp án:** `[0,5)`. End index 5 không được tính trong đoạn.

**Câu 4.** `BreakIterator.DONE` được dùng như thế nào?

**Đáp án:** Giá trị đánh dấu không còn ranh giới khi gọi `next()` hoặc `previous()`, phải kiểm tra trước khi cắt chuỗi.

**Câu 5.** Line iterator có tự xuống dòng khi khung hiển thị chỉ rộng 80 pixel không?

**Đáp án:** Không. Nó báo những vị trí có thể ngắt, còn việc chọn phụ thuộc font, chiều rộng và engine bố cục.

**Câu 6.** Vì sao `"a\u0301b"` không nên luôn cắt bằng `substring(0,1)` để lấy ký tự đầu?

**Đáp án:** Vì ký tự đầu hiển thị có thể gồm `a` và combining acute, chiếm hai code units.

**Câu 7.** Có được dùng offset của BreakIterator sau NFC để cắt văn bản raw NFD không?

**Đáp án:** Không bảo đảm. Normalization có thể làm đổi độ dài/offset; cần dùng cùng chuỗi hoặc có ánh xạ.

**Câu 8.** Khi nào cần cân nhắc ICU4J hoặc tokenizer chuyên dụng?

**Đáp án:** Khi ứng dụng yêu cầu phân đoạn emoji/grapheme mới, tách từ ngôn ngữ phức tạp, hoặc NLP có độ chính xác cao vượt giới hạn BreakIterator mặc định.

## 18. Ghi nhớ

`BreakIterator` cung cấp **các ranh giới văn bản theo Locale** ở bốn mức: ký tự, từ, câu và cơ hội ngắt dòng. Vòng duyệt chuẩn sử dụng `first()`, `next()` và `BreakIterator.DONE`, rồi trích mỗi đoạn bằng `substring(start,end)` theo chỉ số UTF-16.

Điểm cốt lõi là **ranh giới không đồng nghĩa ý nghĩa**: “word” không chỉ chứa từ, “sentence” không nhất thiết bỏ khoảng trắng, “line” không phải bố cục hiển thị, và “character” cần kiểm chứng với Unicode grapheme phức tạp. Để xây dựng ứng dụng Java đa ngôn ngữ đúng, hãy chọn loại iterator/locale theo nhiệm vụ và kiểm thử bằng văn bản thực tế của người dùng.

**Tài liệu chính thức:** [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html) · [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html) · [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html) · [Unicode Standard Annex #29 — Text Segmentation](https://www.unicode.org/reports/tr29/) · [Unicode Standard Annex #14 — Line Breaking](https://www.unicode.org/reports/tr14/).
