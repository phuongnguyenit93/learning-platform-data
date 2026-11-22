# CharSequence.isEmpty và hợp đồng độ dài bằng không trong Java 15

> **Mục tiêu:** Hiểu đúng phương thức `CharSequence.isEmpty()` được bổ sung từ Java 15, hợp đồng `length() == 0`, cách sử dụng thống nhất với `String`, `StringBuilder`, `StringBuffer`, `CharBuffer` và các kiểu `CharSequence` tự định nghĩa; phân biệt chuỗi rỗng với `null`, chuỗi chỉ có khoảng trắng, ký tự vô hình và trường hợp buffer đã đọc hết. Toàn bộ kiến thức và ví dụ sử dụng **API ổn định, còn áp dụng trên Java hiện đại**, không cần preview hay cách viết đã lỗi thời.

## 1. Vì sao có `CharSequence.isEmpty()`?

`CharSequence` là giao diện dùng chung cho những đối tượng biểu diễn một dãy ký tự, bao gồm `String`, `StringBuilder`, `StringBuffer`, `CharBuffer` và các implementation riêng. Trước Java 15, khi một biến được khai báo bằng kiểu `CharSequence`, kiểm tra rỗng thường viết:

~~~java
static boolean empty(CharSequence value) {
    return value.length() == 0;
}
~~~

Từ **Java 15**, giao diện có phương thức:

~~~java
default boolean isEmpty() {
    return length() == 0;
}
~~~

Đây là bản chất của **hợp đồng mặc định** theo Java API: một `CharSequence` là rỗng nếu và chỉ nếu số phần tử `char` của nó bằng **0**. `isEmpty()` có thể được gọi trực tiếp trên biến khai báo kiểu `CharSequence` và dùng làm method reference trong stream.

~~~java
CharSequence text = new StringBuilder();
System.out.println(text.isEmpty()); // true
~~~

**Cần phân biệt mốc phiên bản:** `String.isEmpty()` đã có từ **Java 6**. Điều đáng học ở **Java 15** là đưa phép kiểm tra này lên **giao diện chung `CharSequence`** bằng một `default method`. Vì vậy người viết hàm nhận `CharSequence` không phải tự ép kiểu về `String` hoặc chuyển nó thành `String` chỉ để kiểm tra độ dài.

## 2. Hợp đồng chính xác: `isEmpty()` tương ứng với `length() == 0`

Javadoc quy định:

- `CharSequence.length()` trả về số **đơn vị `char` 16 bit** trong dãy ký tự, tức số **UTF-16 code units**.
- Triển khai mặc định của `CharSequence.isEmpty()` trả về `length() == 0`.
- Nếu `length()` lớn hơn `0`, `isEmpty()` trả về `false` theo hợp đồng, ngay cả khi toàn bộ ký tự đều là khoảng trắng hoặc ký tự không nhìn thấy.
- Phương thức không nhận tham số, không trả về nội dung và **không xóa ký tự**. Nó chỉ kiểm tra trạng thái hiện tại của dãy.

Bảng kiểm tra:

| Dãy ký tự tại thời điểm gọi | `length()` | `isEmpty()` | Lý do |
| --- | ---: | --- | --- |
| `""` | 0 | `true` | Không có `char` nào |
| `" "` | 1 | `false` | Một dấu cách là một ký tự |
| `"\t\n"` | 2 | `false` | Một tab và một newline |
| `"0"` | 1 | `false` | Chữ số 0 là một ký tự, không phải chiều dài 0 |
| `"\0"` | 1 | `false` | Ký tự NUL vẫn chiếm một `char` |
| `"😀"` | 2 | `false` | Emoji này dùng hai UTF-16 code units, dù là một Unicode code point |

**Rỗng là khái niệm cấu trúc:** nó không đồng nghĩa “không có chữ có thể nhìn thấy”, “không có nội dung nghiệp vụ” hoặc “không có dữ liệu cần xử lý”. Nếu yêu cầu thực sự là “không chứa gì ngoài khoảng trắng”, xem mục về `String.isBlank()` bên dưới.

**Không nhầm với Unicode code point:** `length()` đếm `char` 16 bit, không đếm số Unicode code points, grapheme clusters hoặc độ rộng hiển thị. Với `"😀"`, `length() == 2` và `codePointCount(0, length()) == 1`; cả hai cách đếm đều dẫn đến kết luận dãy **không rỗng**.

## 3. `String`, `StringBuilder` và `StringBuffer` dùng như thế nào?

Vì các kiểu này triển khai `CharSequence`, một API chung có thể kiểm tra chúng bằng `isEmpty()`:

~~~java
CharSequence a = "";
CharSequence b = new StringBuilder();
CharSequence c = new StringBuffer("Java");

System.out.println(a.isEmpty()); // true
System.out.println(b.isEmpty()); // true
System.out.println(c.isEmpty()); // false
~~~

| Kiểu | Có thể thay đổi nội dung? | Ý nghĩa `isEmpty()` |
| --- | --- | --- |
| `String` | Không; là chuỗi bất biến | `length() == 0` của chuỗi đã tạo |
| `StringBuilder` | Có | `length() == 0` tại thời điểm kiểm tra |
| `StringBuffer` | Có; hỗ trợ đồng bộ hóa ở các phương thức của nó | `length() == 0` tại thời điểm kiểm tra |
| Biến kiểu `CharSequence` trỏ đến các đối tượng trên | Phụ thuộc object thực tế | Dựa trên hợp đồng của implementation thực tế |

Ví dụ với builder:

~~~java
StringBuilder builder = new StringBuilder();
System.out.println(builder.isEmpty()); // true

builder.append("Java");
System.out.println(builder.isEmpty()); // false

builder.setLength(0);
System.out.println(builder.isEmpty()); // true
~~~

**Điểm quan trọng:** `StringBuilder` có thể **trống về nội dung nhưng còn bộ nhớ dự trữ**. `builder.isEmpty()` không kiểm tra `capacity()` và không cho biết builder đã giải phóng bộ nhớ hay chưa. Cùng một đối tượng có thể chuyển từ rỗng sang không rỗng sau `append()` và quay lại rỗng sau `setLength(0)`.

Đối với `StringBuffer`, các thao tác riêng lẻ có hỗ trợ đồng bộ hóa nhưng một chuỗi thao tác “kiểm tra rồi xử lý” không tự động trở thành một giao dịch nguyên tử:

~~~java
if (!buffer.isEmpty()) {
    // Nếu nhiều luồng cùng sửa buffer, trạng thái có thể đã đổi ở đây.
}
~~~

Khi cần logic đa luồng dựa trên trạng thái nhất quán, phải thiết kế việc đồng bộ hóa hoặc tạo snapshot thích hợp. `isEmpty()` là phép kiểm tra trạng thái, **không** khóa nội dung lại.

## 4. Phân biệt `isEmpty()`, `isBlank()` và `null`

Ba khái niệm này thường bị dùng thay nhau nhưng mang ý nghĩa khác:

- **`null`:** không có đối tượng `CharSequence` để gọi phương thức. Gọi `value.isEmpty()` trên `null` sẽ ném `NullPointerException`.
- **Rỗng (`isEmpty()`):** đối tượng tồn tại và `length() == 0`.
- **Chỉ có khoảng trắng (`String.isBlank()`):** đối tượng là `String` và mọi code point trong chuỗi được xem là khoảng trắng theo `Character.isWhitespace`, hoặc chuỗi không có ký tự nào. `isBlank()` có từ Java 11 và vẫn là API được dùng hiện nay.

~~~java
String empty = "";
String spaces = " \t";

System.out.println(empty.isEmpty());  // true
System.out.println(empty.isBlank());  // true
System.out.println(spaces.isEmpty()); // false
System.out.println(spaces.isBlank()); // true
~~~

`CharSequence` **không khai báo `isBlank()`**. Nếu hàm nhận bất kỳ `CharSequence` nào và nghiệp vụ muốn kiểm tra chuỗi trống hoặc toàn khoảng trắng, cách dễ hiểu là chuyển thành `String` **khi thực sự cần**:

~~~java
static boolean missingOrBlank(CharSequence value) {
    return value == null || value.toString().isBlank();
}
~~~

Đoạn trên là **một phương thức đặt trong class**, không phải chương trình hoàn chỉnh. `value.toString()` có thể tạo bản sao dữ liệu; với đối tượng có thể thay đổi, thời điểm tạo chuỗi cũng quan trọng. Ngoài ra, định nghĩa “khoảng trắng” của `String.isBlank()` không phải mọi ký tự trông có vẻ trắng trong mọi ngôn ngữ, mà theo `Character.isWhitespace`.

Khi chỉ yêu cầu không có ký tự nào, **không cần `toString()`**:

~~~java
static boolean absentOrEmpty(CharSequence value) {
    return value == null || value.isEmpty();
}
~~~

Biểu thức dùng **short-circuit `||`**: nếu `value == null` đúng thì Java không gọi vế phải. Đây là cách an toàn khi API nhận giá trị có thể `null`. Hãy đặt tên hàm đúng nghĩa: “không có object hoặc chuỗi rỗng” khác với “không có nội dung có ích”.

## 5. `CharBuffer`: rỗng nghĩa là không còn ký tự để đọc

`java.nio.CharBuffer` cũng là `CharSequence`, nhưng cần đặc biệt chú ý: `length()` của `CharBuffer` được xác định bằng số ký tự **còn lại giữa `position()` và `limit()`**, tương đương `remaining()`. Vì vậy:

~~~java
java.nio.CharBuffer buffer =
        java.nio.CharBuffer.wrap("abc");

System.out.println(buffer.isEmpty());   // false
System.out.println(buffer.length());    // 3

buffer.position(buffer.limit());

System.out.println(buffer.isEmpty());   // true
System.out.println(buffer.length());    // 0
System.out.println(buffer.capacity());  // 3
~~~

Sau khi di chuyển `position` tới `limit`, bộ đệm đã **hết phần còn lại** nên `isEmpty() == true` dù `capacity() == 3` và vùng lưu trữ chưa chắc đã bị xóa. Điều này không có nghĩa chuỗi gốc `"abc"` biến mất.

Đối với tác vụ đọc buffer, có thể dùng `buffer.hasRemaining()` để diễn đạt ý định “còn phần tử cho vòng lặp đọc”:

~~~java
while (buffer.hasRemaining()) {
    char next = buffer.get();
    // Xử lý next
}
~~~

**Chọn theo ngữ cảnh:** `CharBuffer.isEmpty()` cho biết phần dãy ký tự hiện đang được nhìn qua buffer có độ dài bằng 0; `hasRemaining()` thường trực quan hơn trong một vòng lặp tiêu thụ buffer. Không dùng `capacity() == 0` để xác định bộ đệm đang hết dữ liệu. Các thao tác thay đổi `position/limit` có thể làm `isEmpty()` đổi kết quả mà không sửa byte/char trong bộ nhớ đệm.

## 6. Một chương trình đầy đủ: nhiều implementation cùng một hợp đồng

Tạo file **CharSequenceEmptyDemo.java**, dùng **Java 17+**. Trong ví dụ này, `Slice` là implementation tự định nghĩa bằng `record`; nó chỉ triển khai các phương thức cơ bản của `CharSequence` và **thừa hưởng default `isEmpty()`**. Record là cú pháp Java đã chính thức từ JDK 16 nên phù hợp với mức Java 17+ của chương trình.

~~~java
import java.nio.CharBuffer;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;

public class CharSequenceEmptyDemo {
    record Slice(String source, int start, int end) implements CharSequence {
        Slice {
            Objects.requireNonNull(source);
            Objects.checkFromToIndex(start, end, source.length());
        }

        @Override
        public int length() {
            return end - start;
        }

        @Override
        public char charAt(int index) {
            Objects.checkIndex(index, length());
            return source.charAt(start + index);
        }

        @Override
        public CharSequence subSequence(int from, int to) {
            Objects.checkFromToIndex(from, to, length());
            return new Slice(source, start + from, start + to);
        }

        @Override
        public String toString() {
            return source.substring(start, end);
        }
    }

    static boolean absentOrEmpty(CharSequence value) {
        return value == null || value.isEmpty();
    }

    public static void main(String[] args) {
        CharSequence empty = "";
        CharSequence spaces = " \t";
        CharSequence emoji = "😀";

        System.out.println("empty=" + empty.isEmpty());
        System.out.println("spacesEmpty=" + spaces.isEmpty());
        System.out.println("spacesBlank=" + spaces.toString().isBlank());
        System.out.println("emojiLength=" + emoji.length());
        System.out.println("emojiCodePoints="
                + emoji.toString().codePointCount(0, emoji.length()));

        StringBuilder builder = new StringBuilder();
        System.out.println("builderBefore=" + builder.isEmpty());
        builder.append("Java");
        System.out.println("builderAfter=" + builder.isEmpty());

        CharBuffer buffer = CharBuffer.wrap("abc");
        System.out.println("bufferBefore=" + buffer.isEmpty()
                + ",length=" + buffer.length());
        buffer.position(buffer.limit());
        System.out.println("bufferAfter=" + buffer.isEmpty()
                + ",length=" + buffer.length()
                + ",capacity=" + buffer.capacity());

        List<CharSequence> values = List.of(
                "", new StringBuilder(), " \t", "Java");
        List<String> nonEmpty = values.stream()
                .filter(Predicate.not(CharSequence::isEmpty))
                .map(CharSequence::toString)
                .toList();
        System.out.println("nonEmptySize=" + nonEmpty.size());
        System.out.println("firstNonEmptyBlank="
                + nonEmpty.get(0).isBlank());

        System.out.println("sliceEmpty="
                + new Slice("Java", 2, 2).isEmpty());
        System.out.println("sliceValue="
                + new Slice("Java", 1, 3));
        System.out.println("nullOrEmpty=" + absentOrEmpty(null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 CharSequenceEmptyDemo.java
java CharSequenceEmptyDemo
~~~

Kết quả chuẩn đã đối chiếu bằng chương trình chạy thực tế:

~~~text
empty=true
spacesEmpty=false
spacesBlank=true
emojiLength=2
emojiCodePoints=1
builderBefore=true
builderAfter=false
bufferBefore=false,length=3
bufferAfter=true,length=0,capacity=3
nonEmptySize=2
firstNonEmptyBlank=true
sliceEmpty=true
sliceValue=av
nullOrEmpty=true
~~~

**Cách giải thích:**

1. `empty` chứa 0 `char` nên rỗng; `spaces` chứa dấu cách và tab nên không rỗng, dù chuyển sang `String` để gọi `isBlank()` thì là blank.
2. Emoji trong ví dụ có **hai UTF-16 code units** nhưng chỉ một code point. `isEmpty()` không phụ thuộc cách đếm Unicode code point vì kết quả vẫn khác 0.
3. `StringBuilder` chuyển từ rỗng thành không rỗng sau `append("Java")` mà không tạo builder mới.
4. `CharBuffer` có thể rỗng về phần dữ liệu **còn lại để đọc** dù `capacity` vẫn bằng 3.
5. Stream lọc bỏ hai phần tử rỗng (`""` và `new StringBuilder()`) nhưng **giữ chuỗi chỉ có khoảng trắng**. Vì thế `nonEmptySize=2` và `firstNonEmptyBlank=true`.
6. `new Slice("Java", 2, 2)` có khoảng xem `[2,2)`, độ dài 0 nên nhận `isEmpty() == true` từ default method mà **không cần tự override**. `new Slice("Java",1,3)` biểu diễn `"av"`.
7. `absentOrEmpty(null)` trả `true` nhờ chặn `null` trước khi gọi phương thức.

## 7. Kết hợp `CharSequence::isEmpty` với Stream API

Khi danh sách có nhiều loại `CharSequence` và muốn loại các phần tử rỗng, dùng method reference:

~~~java
List<CharSequence> inputs = List.of(
        "", new StringBuilder(), "  ", "ok");

List<String> accepted = inputs.stream()
        .filter(Predicate.not(CharSequence::isEmpty))
        .map(CharSequence::toString)
        .toList();
~~~

Ở đây:

- Kiểu của luồng đầu vào là `Stream<CharSequence>`, nên method reference **`CharSequence::isEmpty`** kiểm tra đúng giao diện chung.
- `Predicate.not(...)` (Java 11+) đảo vị từ, tức **giữ** phần tử không rỗng.
- `map(CharSequence::toString)` tạo biểu diễn `String`, vì kết quả có thể cần được lưu hoặc sử dụng ngoài vòng đời của các đối tượng mutable.
- `toList()` (Java 16+) tạo danh sách không cho phép sửa cấu trúc; cú pháp này phù hợp Java 17+.
- **Chuỗi chỉ có dấu cách vẫn được giữ lại**, vì `isEmpty()` chỉ kiểm tra độ dài bằng 0.

**Dữ liệu có thể `null`?** `List.of(...)` **không cho phép phần tử `null`**. Với nguồn có thể chứa `null`, cần lọc null trước:

~~~java
List<String> accepted = source.stream()
        .filter(Objects::nonNull)
        .filter(Predicate.not(CharSequence::isEmpty))
        .map(CharSequence::toString)
        .toList();
~~~

Đoạn trên giả định biến `source` có kiểu `List<CharSequence>` (hoặc một collection tương thích) và đã import `java.util.Objects`, `java.util.function.Predicate`; đây **không phải chương trình độc lập**. Nếu chính sách nghiệp vụ xem `null` là lỗi dữ liệu, hãy kiểm tra và báo lỗi thay vì âm thầm loại bỏ.

Nếu muốn **loại cả phần tử blank**, có thể dùng `.filter(cs -> !cs.toString().isBlank())` sau bước lọc null. Khi ấy yêu cầu đã chuyển từ “không rỗng” sang “có nội dung ngoài khoảng trắng”; cần thể hiện rõ trong tên hàm và test.

## 8. Tự định nghĩa `CharSequence`: thực hiện đúng hợp đồng

Một class hoặc record tự viết `implements CharSequence` thường cung cấp ít nhất bốn phương thức trừu tượng/được kế thừa phù hợp: `length()`, `charAt(int)`, `subSequence(int,int)` và `toString()`. Từ Java 15, `isEmpty()` đã có default implementation; không bắt buộc viết lại.

Ví dụ `Slice` ở mục 6 giữ một dãy ký tự bằng `source` và cặp chỉ số `start/end`, nên:

- `length()` trả đúng `end - start`; kết quả không âm vì constructor đã kiểm tra `start <= end`.
- `charAt(i)` dùng chỉ số **tương đối với Slice**, rồi cộng `start` để tìm ký tự trong nguồn.
- `subSequence(from,to)` tạo vùng con tương ứng; khi `from == to` thì kết quả rỗng.
- `toString()` trả đúng các ký tự trong vùng xem, không cần kéo theo những ký tự ngoài vùng.
- `isEmpty()` mặc định gọi `length() == 0`, nên tính rỗng nhất quán với các phương thức còn lại.

**Khi nào override `isEmpty()`?** Có thể override nếu có lý do đặc biệt và triển khai vẫn thỏa `isEmpty() == (length() == 0)`. Không nên override để định nghĩa “rỗng” thành “toàn dấu cách” hay “không có ký tự nhìn thấy”, vì điều đó làm sai hợp đồng chung, gây bất ngờ khi object được dùng qua kiểu `CharSequence`.

Nếu implementation có nội dung **động**, `length()` và `isEmpty()` có thể cho kết quả khác nhau ở hai thời điểm khi dữ liệu đang bị thay đổi. Gọi `isEmpty()` một lần **không đảm bảo** một lệnh `charAt(0)` tiếp theo luôn hợp lệ. Khi yêu cầu snapshot nhất quán hoặc truy cập đa luồng, cần quản lý đồng bộ hóa và vòng đời dữ liệu theo implementation cụ thể.

## 9. Các trường hợp nên và không nên dùng

| Tình huống thực tế | Cách kiểm tra phù hợp | Vì sao |
| --- | --- | --- |
| Input `CharSequence` bắt buộc có ít nhất một `char` | `value != null && !value.isEmpty()` | Kiểm tra cả object và độ dài |
| Input `String` phải chứa ký tự không phải whitespace | `value != null && !value.isBlank()` | `isEmpty()` không loại được `" \t"` |
| Hàm tiện ích nhận nhiều loại chuỗi | `sequence.isEmpty()` sau khi xác định không null | Không ép kiểu, không chuyển sang `String` |
| Danh sách `CharSequence` không có null, cần bỏ phần tử rỗng | `filter(Predicate.not(CharSequence::isEmpty))` | Dùng trực tiếp method reference trên interface |
| `StringBuilder` trước/sau thêm nội dung | `builder.isEmpty()` | Trạng thái thay đổi theo thời điểm, không phụ thuộc capacity |
| Đọc `CharBuffer` theo vị trí hiện tại | `buffer.hasRemaining()` hoặc `!buffer.isEmpty()` | Đo **remaining**, không phải kích thước bộ nhớ |
| Cần số code points hoặc grapheme clusters | Dùng API Unicode/phân đoạn phù hợp | `length()` chỉ đếm UTF-16 code units |
| Cần biết object có `null` hay không | `value == null` | `null` không phải một `CharSequence` rỗng |

**Điểm thiết kế API:** Nếu mục tiêu chỉ là thao tác với dãy ký tự, khai báo tham số kiểu `CharSequence` giúp hàm chấp nhận nhiều implementation. Tuy nhiên, không đổi mọi tham số `String` thành `CharSequence` một cách máy móc: `String` bất biến, còn `CharSequence` có thể trỏ tới dữ liệu mutable; yêu cầu nghiệp vụ về ổn định nội dung, equality hoặc lưu trữ dài hạn cần được cân nhắc.

## 10. Những hiểu nhầm phổ biến

1. **“`isEmpty()` được thêm mới cho tất cả kiểu chuỗi từ Java 15.”** Sai: `String.isEmpty()` đã tồn tại từ Java 6; Java 15 bổ sung default method trên `CharSequence`.
2. **“`isEmpty()` trả `true` khi toàn khoảng trắng.”** Sai: `" "` và `"\t"` có chiều dài lớn hơn 0. Dùng `String.isBlank()` cho nghiệp vụ blank.
3. **“`null.isEmpty()` là một cách hợp lệ để kiểm tra thiếu dữ liệu.”** Sai: gọi phương thức trên `null` gây `NullPointerException`.
4. **“`length()` đếm ký tự người dùng nhìn thấy.”** Sai: nó đếm `char` 16 bit, khác code point hoặc grapheme.
5. **“`CharBuffer.isEmpty() == true` chứng tỏ vùng nhớ trống hoặc capacity bằng 0.”** Sai: có thể chỉ là `position == limit`.
6. **“`StringBuilder.isEmpty()` cho cùng kết quả suốt vòng đời.”** Sai: builder mutable, có thể thêm/bớt ký tự.
7. **“Cần gọi `toString()` rồi `String.isEmpty()`.”** Thường không cần; `CharSequence.isEmpty()` đã làm đúng việc kiểm tra độ dài, tránh chuyển đổi không cần thiết.
8. **“`CharSequence` là bất biến và an toàn cho mọi thao tác đa luồng.”** Sai: điều này phụ thuộc implementation thực tế. `isEmpty()` không cung cấp bảo đảm nguyên tử cho các bước theo sau.
9. **“Mọi implementation có thể override `isEmpty()` theo định nghĩa tùy ý.”** Không nên: vẫn phải tôn trọng ý nghĩa độ dài bằng 0 của giao diện.
10. **“Chỉ cần lọc `isEmpty()` là dữ liệu input đã hợp lệ.”** Sai: không rỗng không đồng nghĩa đúng định dạng, đúng độ dài byte, đúng charset, hoặc không chứa ký tự điều khiển.

## 11. Bài thực hành và tiêu chí đánh giá

**Bài 1 — Phân biệt rỗng và blank.** Dự đoán `isEmpty()` và `isBlank()` của `""`, `" "`, `"\t\n"` và `"Java"`. **Đạt** khi chỉ đúng mọi trường hợp và giải thích vì sao `" \t"` là nonempty nhưng blank.

**Bài 2 — Kế thừa default method.** Tạo implementation `CharSequence` cho một slice của chuỗi gốc, cài đặt đúng `length`, `charAt`, `subSequence`, `toString` nhưng **không override `isEmpty()`**. **Đạt** khi vùng con `[start,start)` cho `true` và vùng có ít nhất một `char` cho `false`.

**Bài 3 — Dữ liệu mutable.** Tạo `StringBuilder` rỗng, kiểm tra `isEmpty()`, thêm chữ, kiểm tra lại, gọi `setLength(0)` rồi kiểm tra lần cuối. **Đạt** khi kết quả lần lượt là `true`, `false`, `true` và biết tại sao `capacity()` không liên quan.

**Bài 4 — Dữ liệu buffer.** Tạo `CharBuffer.wrap("abc")`, đưa `position` tới `limit`. **Đạt** khi hiểu `isEmpty() == true` nhưng `capacity() == 3`; phân biệt phần remaining và bộ nhớ gốc.

**Bài 5 — Stream đa kiểu.** Tạo `List<CharSequence>` gồm `String`, `StringBuilder` và chuỗi whitespace; dùng `CharSequence::isEmpty` để loại phần tử rỗng. **Đạt** khi biết `"  "` vẫn được giữ; sau đó dùng `String.isBlank()` nếu bài toán muốn loại whitespace-only.

**Bài 6 — Null và Unicode.** Viết `absentOrEmpty(CharSequence)` không ném NPE, rồi kiểm tra `"😀".length()` và `codePointCount`. **Đạt** khi kết quả 2 và 1 được giải thích là UTF-16 code units so với code points, và `isEmpty() == false`.

## 12. Nguồn chính thức để kiểm chứng

- [Java SE 15 API — CharSequence](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/CharSequence.html): xác nhận `isEmpty()` là `default method` có từ Java 15 và triển khai mặc định `length() == 0`.
- [Java SE 25 API — CharSequence](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/CharSequence.html): hợp đồng hiện hành và định nghĩa `length()` bằng số `char` 16 bit.
- [Java SE 25 API — String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html): phân biệt `isEmpty()` và `isBlank()`, hợp đồng ký tự Unicode.
- [Java SE 25 API — CharBuffer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/CharBuffer.html): `length() == remaining()`, `isEmpty()` khi không còn phần tử.
- [Oracle — JDK 15 Release Notes](https://www.oracle.com/java/technologies/javase/15all-relnotes.html): ghi nhận việc thêm default `CharSequence.isEmpty()`.

**Ghi nhớ:** Với mọi `CharSequence` tuân thủ hợp đồng Java, **`isEmpty()` nghĩa là `length() == 0`**, không phải “nhìn có vẻ trống”. Đối tượng có thể là `String` bất biến, builder mutable hoặc `CharBuffer` với phần remaining bằng 0. Muốn kiểm tra nội dung nghiệp vụ, hãy định nghĩa rõ xử lý `null`, whitespace, Unicode và biến đổi trạng thái, rồi chọn API phù hợp.
