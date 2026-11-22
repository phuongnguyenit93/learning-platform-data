# Java 15 — Method reference `CharSequence::isEmpty` trong pipeline

## 1. Vấn đề và mục tiêu

Khi xử lý một tập hợp chuỗi qua `Stream`, ứng dụng thường phải phân biệt phần tử **rỗng** với phần tử có nội dung. Từ Java 15, giao diện `java.lang.CharSequence` có phương thức mặc định `isEmpty()`. Điều này cho phép viết **method reference** `CharSequence::isEmpty` ngay trong một pipeline thay vì lặp lại điều kiện `sequence.length() == 0`.

API này vẫn được hỗ trợ trên các JDK hiện đại. Nó đặc biệt hữu ích khi các phần tử không chỉ là `String` mà còn có thể là `StringBuilder`, `StringBuffer`, `CharBuffer` hoặc một kiểu khác triển khai `CharSequence`.

Mục tiêu của bài:

1. Hiểu chính xác `CharSequence.isEmpty()` kiểm tra điều gì và từ phiên bản Java nào có thể sử dụng.
2. Biết `CharSequence::isEmpty` là **method reference tới phương thức instance chưa gắn đối tượng** (*unbound instance method reference*) và được chuyển thành `Predicate` trong `Stream.filter(...)` như thế nào.
3. Sử dụng đúng `filter(CharSequence::isEmpty)` để **chọn phần tử rỗng**, hoặc `filter(Predicate.not(CharSequence::isEmpty))` để **giữ phần tử không rỗng**.
4. Phân biệt `isEmpty()` với `String.isBlank()`, xử lý `null`, dữ liệu có thể thay đổi và khác biệt giữa các kiểu `CharSequence`.
5. Viết và kiểm thử một pipeline biên dịch được trên Java 17+; đồng thời hiểu cách dùng trực tiếp API Java 15 khi cần.

## 2. Cơ sở API: `CharSequence.isEmpty()` từ Java 15

`CharSequence` là giao diện cho một dãy giá trị `char` có thể đọc được. Hai thành phần liên quan là:

~~~java
int length();
default boolean isEmpty() {
    return length() == 0;
}
~~~

Đây là **mô tả rút gọn của hợp đồng API** chứ không phải một tệp Java độc lập. `isEmpty()` là phương thức mặc định được bổ sung vào `CharSequence` từ **Java 15**. Theo hợp đồng, triển khai mặc định trả `true` nếu `length() == 0` và `false` trong trường hợp khác. `String.isEmpty()` đã tồn tại trước Java 15; điểm mới có ý nghĩa ở đây là gọi được ở **mức giao diện `CharSequence`**.

Ví dụ ý nghĩa:

| Giá trị `CharSequence` | `length()` | `isEmpty()` | Giải thích |
| --- | ---: | --- | --- |
| `""` | 0 | `true` | Hoàn toàn không có ký tự |
| `"Java"` | 4 | `false` | Có nội dung |
| `"   "` | 3 | `false` | Có ba ký tự space; rỗng khác với chỉ chứa khoảng trắng |
| `"\n"` | 1 | `false` | Newline cũng là một ký tự trong chuỗi |
| `new StringBuilder()` | 0 | `true` | Builder chưa chứa ký tự |
| `new StringBuilder(100)` | 0 | `true` | Dung lượng cấp trước (`capacity`) khác độ dài nội dung (`length`) |
| `new StringBuffer("15")` | 2 | `false` | Kiểu cụ thể khác nhưng vẫn là `CharSequence` |

`length()` là số đơn vị `char` (UTF-16 code units), không nhất thiết là số Unicode code points hay số chữ người đọc thấy. Tuy nhiên, để quyết định *rỗng hay không rỗng*, chỉ cần kiểm tra `length() == 0`.

### 2.1. Vì sao dùng tên giao diện thay vì tên `String`?

Các dòng sau minh họa phương thức nhận một `Predicate<CharSequence>`:

~~~java
Predicate<CharSequence> empty = CharSequence::isEmpty;
Predicate<CharSequence> equivalent = value -> value.isEmpty();
~~~

Đây là **đoạn mã trong class/phương thức có import `java.util.function.Predicate`**, không phải chương trình độc lập. Hai predicate trên cùng kiểm tra một đối tượng `CharSequence` khác `null`.

Với `Stream<CharSequence>`, kiểu `String::isEmpty` không phải lựa chọn tổng quát vì pipeline có thể chứa `StringBuilder` và `StringBuffer`. Ngược lại, `CharSequence::isEmpty` có thể dùng trên `Stream<String>` vì mọi `String` đều triển khai `CharSequence`.

## 3. Method reference hoạt động như thế nào?

Cú pháp `TypeName::instanceMethod` không gắn trước một đối tượng cụ thể. Khi pipeline gọi predicate với từng phần tử, **phần tử đó trở thành receiver**:

~~~java
.filter(CharSequence::isEmpty)
~~~

tương đương về mặt ý nghĩa với:

~~~java
.filter(sequence -> sequence.isEmpty())
~~~

Nếu kiểu stream là `Stream<CharSequence>`, `filter(...)` nhận `Predicate<? super CharSequence>`. Method reference `CharSequence::isEmpty` được suy luận thành một predicate nhận `CharSequence` và trả về `boolean`. Đây là một dạng *target typing* của method reference.

**Quy tắc quan trọng:** `filter` chỉ giữ phần tử mà predicate trả về **`true`**. Vì vậy:

- `filter(CharSequence::isEmpty)` **giữ phần tử rỗng**; thích hợp để đếm hoặc phát hiện dữ liệu rỗng.
- `filter(Predicate.not(CharSequence::isEmpty))` **giữ phần tử không rỗng**; thích hợp cho một bước loại bỏ đầu vào rỗng.
- `filter(sequence -> !sequence.isEmpty())` cũng giữ phần tử không rỗng, hữu ích khi điều kiện cần giải thích thêm hoặc kết hợp nhiều thao tác.

`Predicate.not(...)` là API còn được hỗ trợ, có từ Java 11. Nó đảo kết quả của predicate. Việc dùng `Predicate.not(CharSequence::isEmpty)` giúp pipeline thể hiện ý “giữ lại khi không rỗng” một cách rõ ràng.

Một method reference **không gọi phương thức ngay tại lúc xây dựng pipeline**. `Stream.filter` là thao tác trung gian (*intermediate operation*); predicate được đánh giá khi có thao tác terminal như `count()`, `toList()` hoặc `collect(...)` yêu cầu dữ liệu. Điều này đặc biệt quan trọng khi một `CharSequence` là đối tượng mutable.

## 4. Ví dụ độc lập Java 17+: lọc dữ liệu hỗn hợp trong Stream

Lưu toàn bộ mã sau vào tệp **`CharSequencePipelineDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;
import java.util.stream.Stream;

public class CharSequencePipelineDemo {
    public static void main(String[] args) {
        List<CharSequence> values = List.of(
                "", "Java", new StringBuilder(),
                new StringBuilder("API"), "   ",
                new StringBuffer("15"), "\n");

        long emptyCount = values.stream()
                .filter(CharSequence::isEmpty)
                .count();

        List<String> nonEmpty = values.stream()
                .filter(Predicate.not(CharSequence::isEmpty))
                .map(CharSequence::toString)
                .map(s -> "<" + s.replace("\n", "\\n") + ">")
                .toList();

        List<String> nonBlank = values.stream()
                .filter(Predicate.not(CharSequence::isEmpty))
                .map(CharSequence::toString)
                .filter(Predicate.not(String::isBlank))
                .toList();

        List<CharSequence> withNull =
                Arrays.asList(null, "", new StringBuilder("ok"), null, "hi");
        List<String> nullSafe = withNull.stream()
                .filter(Objects::nonNull)
                .filter(Predicate.not(CharSequence::isEmpty))
                .map(CharSequence::toString)
                .toList();

        long stringStreamEmptyCount = Stream.of("", "a", " ")
                .filter(CharSequence::isEmpty)
                .count();

        System.out.println("emptyCount=" + emptyCount);
        System.out.println("nonEmpty=" + nonEmpty);
        System.out.println("nonBlank=" + nonBlank);
        System.out.println("nullSafe=" + nullSafe);
        System.out.println("stringStreamEmpty=" + stringStreamEmptyCount);
    }
}
~~~

Biên dịch, chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 CharSequencePipelineDemo.java
java CharSequencePipelineDemo
~~~

**Stdout đã được kiểm chứng:**

~~~text
emptyCount=2
nonEmpty=[<Java>, <API>, <   >, <15>, <\n>]
nonBlank=[Java, API, 15]
nullSafe=[ok, hi]
stringStreamEmpty=1
~~~

### 4.1. Phân tích từng kết quả

**`emptyCount=2`:** Có hai đối tượng thật sự rỗng: `""` và `new StringBuilder()`. `"   "` và `"\n"` không rỗng vì độ dài của chúng khác 0.

**`nonEmpty=[<Java>, <API>, <   >, <15>, <\n>]`:** Predicate đã được phủ định, nên cả khoảng trắng và newline vẫn đi qua bộ lọc. Phương thức `map(CharSequence::toString)` chuẩn hóa kiểu kết quả thành `String`; biểu diễn `<...>` giúp nhìn rõ khoảng trắng, và `replace("\n", "\\n")` biến ký tự LF thành hai ký tự hiển thị `\` và `n`. Đoạn `<\n>` trong stdout **không phải xuống dòng thật**.

**`nonBlank=[Java, API, 15]`:** Sau khi chuyển phần tử thành `String`, bộ lọc `String::isBlank` loại cả chuỗi rỗng, các space và newline; còn lại ba giá trị có ký tự không phải whitespace.

**`nullSafe=[ok, hi]`:** Dòng `filter(Objects::nonNull)` đã loại các phần tử `null` trước khi gọi method reference instance. Chuỗi rỗng được loại ở bộ lọc tiếp theo.

**`stringStreamEmpty=1`:** Method reference có receiver kiểu `CharSequence` vẫn dùng được với `Stream<String>`; chỉ chuỗi `""` được giữ trong bước đếm.

Đoạn code tạo **stream mới** qua mỗi lần gọi `values.stream()`. Một `Stream` đã thực hiện terminal operation không được dùng lại để chạy một pipeline khác.

### 4.2. Tại sao `.toList()` dùng JDK 17 trở lên?

`Stream.toList()` xuất hiện từ Java 16, nên ví dụ hiện đại dùng `--release 17`. Phương thức này trả về **List không thể chỉnh sửa cấu trúc** (*unmodifiable list*); gọi `add` hay `remove` trên list kết quả sẽ ném `UnsupportedOperationException`. Nếu cần một `ArrayList` có thể thay đổi, dùng đoạn sau trong một phương thức Java với các import thích hợp:

~~~java
List<String> mutableResult = values.stream()
        .filter(Predicate.not(CharSequence::isEmpty))
        .map(CharSequence::toString)
        .collect(java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));
~~~

Tính không thể sửa cấu trúc của `List` không đồng nghĩa tất cả đối tượng phần tử đều immutable. Trong ví dụ chính, `map(CharSequence::toString)` tạo đầu ra `String` bất biến; nếu giữ nguyên các `StringBuilder` trong list thì nội dung của builder vẫn có thể thay đổi.

## 5. Biên dịch trực tiếp với chuẩn Java 15

Phần bổ sung `CharSequence.isEmpty()` từ Java 15 không phụ thuộc `Stream.toList()`. Nếu ứng dụng đang có **mã nguồn phải tương thích Java 15**, có thể dùng `collect(Collectors.toList())`, vốn vẫn là API chuẩn và còn được hỗ trợ.

Lưu vào tệp **`CharSequenceJava15Demo.java`**:

~~~java
import java.util.List;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class CharSequenceJava15Demo {
    public static void main(String[] args) {
        List<CharSequence> values =
                List.of("", "Java", new StringBuilder("15"), " ");
        List<String> nonEmpty = values.stream()
                .filter(Predicate.not(CharSequence::isEmpty))
                .map(CharSequence::toString)
                .collect(Collectors.toList());
        System.out.println(nonEmpty.stream()
                .map(s -> "<" + s + ">")
                .collect(Collectors.joining(", ")));
    }
}
~~~

Dùng JDK có hỗ trợ biên dịch mục tiêu Java 15:

~~~bash
javac --release 15 CharSequenceJava15Demo.java
java CharSequenceJava15Demo
~~~

Kết quả:

~~~text
<Java>, <15>, < >
~~~

`" "` được giữ lại vì nó có độ dài 1. Đoạn này cho thấy `CharSequence::isEmpty` hoạt động ngay trên API Java 15; việc dùng `.toList()` trong ví dụ hiện đại là **khả năng bổ sung của `Stream` ở Java 16+**, không phải yêu cầu của phương thức `isEmpty()`.

`Collectors.toList()` **không cam kết** kiểu list hoặc khả năng chỉnh sửa của list trả về; khi cần list mutable chắc chắn, hãy dùng `Collectors.toCollection(ArrayList::new)`.

## 6. `isEmpty()` và `isBlank()` không giống nhau

Hai điều kiện phục vụ hai quy tắc dữ liệu khác nhau:

| Giá trị | `isEmpty()` | `String.isBlank()` | Ý nghĩa |
| --- | --- | --- | --- |
| `""` | `true` | `true` | Không có ký tự |
| `" "` | `false` | `true` | Có space nhưng không có ký tự nội dung |
| `"\t\n"` | `false` | `true` | Chỉ có whitespace |
| `" Java "` | `false` | `false` | Có ký tự nội dung |
| `"0"` | `false` | `false` | Chuỗi “0” là dữ liệu, không phải rỗng |

`String.isBlank()` kiểm tra chuỗi có rỗng hoặc chỉ gồm code points được coi là whitespace theo `Character.isWhitespace`. Đây là phương thức của **`String`**, không phải của giao diện `CharSequence`. Do đó với `Stream<CharSequence>` chứa cả builder, đoạn sau là một lựa chọn rõ ràng:

~~~java
stream.filter(Objects::nonNull)
      .map(CharSequence::toString)
      .filter(Predicate.not(String::isBlank))
~~~

Đây là **đoạn pipeline minh họa**, giả sử biến `stream` có kiểu `Stream<CharSequence>`. Việc chuyển thành `String` giúp thống nhất kiểu và nghĩa của predicate. Nếu cần giữ lại chính các đối tượng `StringBuilder` thay vì chuyển sang `String`, phải xây dựng predicate kiểm tra whitespace trên `CharSequence` bằng logic riêng phù hợp hợp đồng nghiệp vụ.

Với dữ liệu chỉ cần loại **chuỗi độ dài 0**, `Predicate.not(CharSequence::isEmpty)` là đủ. Với dữ liệu nhập biểu mẫu yêu cầu phải có **ký tự không phải khoảng trắng**, `String.isBlank()` thích hợp hơn sau khi đã đưa dữ liệu về `String`. `isEmpty()` **không trim** và **không tự sửa** dữ liệu.

## 7. Ba tình huống dễ làm pipeline sai

### 7.1. Có `null` trong stream

`CharSequence::isEmpty` là lời gọi phương thức trên chính phần tử. Nếu một phần tử là `null`, khi predicate được đánh giá, chương trình ném `NullPointerException`. Không có cơ chế kiểm tra null tự động trong method reference.

Cách có chủ đích nếu `null` phải bị loại:

~~~java
List<String> result = withNull.stream()
        .filter(Objects::nonNull)
        .filter(Predicate.not(CharSequence::isEmpty))
        .map(CharSequence::toString)
        .toList();
~~~

Đây là đoạn trong chương trình chính, đã được kiểm chứng. **Thứ tự filter quan trọng:** phải lọc `null` trước phép gọi `isEmpty()`. Nếu yêu cầu nghiệp vụ là “`null` tương đương rỗng”, một predicate rõ nghĩa có thể là:

~~~java
Predicate<CharSequence> emptyOrNull =
        value -> value == null || value.isEmpty();
~~~

Đoạn này là **khai báo tại nơi có import `Predicate`**, không phải chương trình độc lập. Nó dùng short-circuit `||`, nên không gọi `isEmpty()` trên `null`. Nếu cần đếm giá trị rỗng *bao gồm null*, dùng `filter(emptyOrNull)`; nếu chỉ cần loại null rồi giữ giá trị có nội dung, dùng hai bước filter trong ví dụ chính. Hai yêu cầu mang nghĩa khác nhau, cần quyết định trước.

`List.of(...)` không cho phép phần tử null; để minh họa dữ liệu nguồn có null, ví dụ chính dùng `Arrays.asList(...)`. Hãy chọn collection phù hợp với ràng buộc null thực tế của dữ liệu.

### 7.2. `CharSequence` có thể thay đổi nội dung theo thời điểm

`String` bất biến, nhưng `StringBuilder` và `StringBuffer` có thể thay đổi sau khi tạo. Method reference kiểm tra độ dài **tại lúc predicate chạy**. Do Stream trung gian là lazy, một builder rỗng tại lúc lắp pipeline có thể đã có nội dung lúc terminal operation thực sự đánh giá nó.

Ví dụ:

~~~java
StringBuilder builder = new StringBuilder();
java.util.stream.Stream<CharSequence> pending =
        java.util.stream.Stream.<CharSequence>of(builder)
                .filter(CharSequence::isEmpty);

builder.append("changed");
long emptyNow = pending.count(); // 0
~~~

Đây là **đoạn mã trong một phương thức**, không phải một chương trình độc lập. Predicate thấy builder đã có nội dung khi `count()` chạy. Một khi terminal operation kết thúc, stream đã tiêu thụ.

Không nên đồng thời sửa mutable `CharSequence` trong khi pipeline đang đọc, nhất là `parallelStream()`; kết quả kiểm tra có thể không nhất quán và phụ thuộc đồng bộ hóa của kiểu cụ thể. Nếu cần xử lý một bản chụp nội dung tại một thời điểm, chuyển sang `String` trước khi đưa vào pipeline hoặc dùng cơ chế snapshot đồng bộ thích hợp.

### 7.3. `distinct()` trên các triển khai `CharSequence` khác nhau

Hợp đồng `CharSequence` **không áp đặt chung quy tắc `equals`/`hashCode` cho mọi triển khai**. `StringBuilder` và `StringBuffer` không so sánh nội dung giống `String` bằng `equals`. Vì `Stream.distinct()` dựa vào so sánh bằng nhau của phần tử, các đối tượng có cùng chữ có thể không được gộp.

Lưu **`DistinctCharSequenceDemo.java`** để kiểm chứng:

~~~java
import java.util.List;

public class DistinctCharSequenceDemo {
    public static void main(String[] args) {
        List<CharSequence> values =
                List.of("ok", new StringBuilder("ok"), new StringBuffer("ok"));
        System.out.println("rawDistinct=" + values.stream().distinct().count());
        System.out.println("stringDistinct=" + values.stream()
                .map(CharSequence::toString).distinct().count());

        StringBuilder reserved = new StringBuilder(100);
        System.out.println("reservedEmpty=" +
                ((CharSequence) reserved).isEmpty());
        reserved.append("x");
        System.out.println("afterAppendEmpty=" +
                ((CharSequence) reserved).isEmpty());
    }
}
~~~

~~~bash
javac --release 17 DistinctCharSequenceDemo.java
java DistinctCharSequenceDemo
~~~

Kết quả:

~~~text
rawDistinct=3
stringDistinct=1
reservedEmpty=true
afterAppendEmpty=false
~~~

Hai dòng đầu cho thấy cần `map(CharSequence::toString)` **trước `distinct()`** nếu yêu cầu là loại bản ghi trùng **nội dung ký tự**, không phụ thuộc loại đối tượng. Hai dòng sau nhấn mạnh `isEmpty` kiểm tra `length()` tại thời điểm gọi, không kiểm tra `capacity()` của builder.

## 8. Method reference này dùng ở đâu ngoài `filter`?

`CharSequence::isEmpty` có thể được dùng khi API chấp nhận một functional interface tương thích, điển hình là `Predicate<CharSequence>`.

**Kiểm tra có phần tử rỗng hay không:**

~~~java
boolean hasEmpty = values.stream().anyMatch(CharSequence::isEmpty);
~~~

`anyMatch` có thể dừng khi tìm thấy phần tử đầu tiên khớp. Nếu stream rỗng, kết quả `false`.

**Kiểm tra tất cả phần tử đều không rỗng:**

~~~java
boolean allNonEmpty = values.stream()
        .noneMatch(CharSequence::isEmpty);
~~~

`noneMatch` trả `true` khi không tìm thấy phần tử rỗng; với stream rỗng, nó cũng trả `true`. Nếu cần “danh sách phải có phần tử **và** không có phần tử rỗng”, phải kiểm tra thêm điều kiện không rỗng cho danh sách/nguồn, thay vì chỉ dựa vào `noneMatch`.

**Kiểm tra một giá trị tùy chọn:**

~~~java
java.util.Optional<CharSequence> candidate =
        java.util.Optional.of((CharSequence) "");
boolean presentAndEmpty =
        candidate.filter(CharSequence::isEmpty).isPresent();
~~~

`presentAndEmpty` bằng `true`: Optional chứa một đối tượng không null và đối tượng ấy rỗng. Ngược lại, `Optional.empty().filter(...)` vẫn rỗng; predicate không được gọi. Các ví dụ ở đây là **đoạn mã minh họa trong method**, yêu cầu nguồn `values` phù hợp.

**Đếm hay lọc từ `Stream<String>`:** `CharSequence::isEmpty` vẫn hợp lệ vì kiểu phần tử `String` triển khai `CharSequence`. Bạn có thể chọn `String::isEmpty` nếu chỉ làm việc với chuỗi `String`, nhưng dùng `CharSequence::isEmpty` giúp code biểu đạt điều kiện trên giao diện rộng hơn.

## 9. Khi nào dùng method reference, khi nào dùng lambda?

Chọn theo ý nghĩa và khả năng đọc:

| Mục tiêu | Gợi ý |
| --- | --- |
| Chọn đúng các phần tử độ dài 0 | `filter(CharSequence::isEmpty)` |
| Loại phần tử độ dài 0 | `filter(Predicate.not(CharSequence::isEmpty))` |
| Loại null và phần tử độ dài 0 | `filter(Objects::nonNull).filter(Predicate.not(CharSequence::isEmpty))` |
| Loại chuỗi chỉ chứa whitespace | `map(CharSequence::toString).filter(Predicate.not(String::isBlank))` |
| Điều kiện cần thêm tham số hoặc logic nghiệp vụ | `filter(value -> value.length() > minimumLength)` với `minimumLength` có sẵn |
| Kiểm tra hay chuyển đổi kiểu phức tạp | Dùng lambda hoặc phương thức có tên rõ nghĩa, rồi method reference tới phương thức đó |

Method reference làm code ngắn hơn khi đã có sẵn một phương thức diễn đạt đúng yêu cầu. Không nên cố ép mọi predicate thành method reference nếu điều kiện nghiệp vụ cần giải thích. Ví dụ, loại khoảng trắng, chuẩn hóa chữ hoa/thường, xác thực dữ liệu và lọc giá trị rỗng là những hành động riêng; `isEmpty()` không thay thế các quy tắc đó.

**Tính ngắn gọn không đảm bảo hiệu năng cao hơn.** `value -> value.isEmpty()` và `CharSequence::isEmpty` đều mô tả một lời gọi phương thức; lựa chọn chính là tính rõ nghĩa. Nếu pipeline rất nhạy về hiệu năng, cần đo đạc trên dữ liệu thật, tránh tự suy đoán từ cú pháp.

## 10. Sai lầm thường gặp

1. **Viết `filter(CharSequence::isEmpty)` rồi chờ các phần tử rỗng bị loại.** Thực tế `filter` giữ phần tử có predicate là `true`. Muốn bỏ phần tử rỗng, phủ định predicate.
2. **Coi `"   "` hoặc `"\n"` là rỗng.** `isEmpty` chỉ đúng khi `length == 0`. Nếu yêu cầu bỏ nội dung toàn whitespace, dùng `String.isBlank` trên `String`.
3. **Đặt `CharSequence::isEmpty` trước phép loại null.** Null receiver làm phát sinh `NullPointerException` khi pipeline thực thi.
4. **Gán `String::isEmpty` cho pipeline chứa cả builder.** `Stream<CharSequence>` có thể chứa nhiều kiểu không phải `String`. Dùng `CharSequence::isEmpty` hoặc chuẩn hóa kiểu trước.
5. **Dùng `toList()` rồi thử `add`.** `Stream.toList()` trả list không thể sửa cấu trúc. Nếu cần list mutable, chọn collector tạo collection cụ thể.
6. **Gọi lại terminal operation trên cùng `Stream`.** Tạo stream mới từ nguồn hoặc lưu kết quả vào collection khi cần sử dụng nhiều lần.
7. **Dùng `distinct()` trước khi chuẩn hóa các triển khai `CharSequence`.** Quy tắc equality khác nhau có thể làm các chuỗi cùng nội dung bị coi là khác.
8. **Dựa vào trạng thái của builder tại lúc tạo pipeline.** Pipeline lazy và mutable input có thể đổi trạng thái trước lúc đánh giá.
9. **Dùng `--release 14` với `CharSequence::isEmpty` rồi nghĩ method reference sai cú pháp.** API được thêm từ Java 15, nên mục tiêu biên dịch thấp hơn không có phương thức này trên giao diện.
10. **Nhầm `CharSequence.isEmpty` với một phép xác thực dữ liệu.** Nó không kiểm tra encoding, whitespace-only, độ dài tối thiểu, pattern hay sự phù hợp nghiệp vụ; cần các predicate bổ sung khi yêu cầu có những điều kiện đó.

## 11. Checklist áp dụng vào dự án

Trước khi hoàn thành một pipeline, hãy xác định:

- **Kiểu đầu vào:** `Stream<String>` hay `Stream<CharSequence>`? Có các loại mutable như `StringBuilder` không?
- **Ngữ nghĩa mong muốn:** rỗng tuyệt đối (`length == 0`), toàn whitespace, hay có tối thiểu N ký tự hữu ích?
- **Nguồn có null không:** nếu có, xử lý null rõ ràng trước lời gọi instance.
- **Loại đối tượng đầu ra:** nếu dùng `CharSequence::toString`, đầu ra là nội dung `String`; nếu giữ builder, phải cân nhắc mutation.
- **Khả năng sử dụng list kết quả:** `Stream.toList()` không hỗ trợ chỉnh sửa cấu trúc.
- **Phiên bản Java:** `CharSequence.isEmpty` có từ Java 15, `Predicate.not` từ Java 11, `Stream.toList` từ Java 16. Ví dụ chính biên dịch trên Java 17+.
- **Kiểm thử biên:** chuỗi rỗng, chuỗi space, newline, null (nếu nguồn cho phép), StringBuilder rỗng, StringBuilder có nội dung và giá trị trùng chữ nhưng khác kiểu.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `Stream.of("", "A", " ").filter(CharSequence::isEmpty).count()` bằng bao nhiêu?  
**Đáp án:** `1`. Chỉ `""` có độ dài 0.

**Câu 2.** Đoạn `filter(Predicate.not(CharSequence::isEmpty))` có loại `"   "` không?  
**Đáp án:** Không. Chuỗi có ba ký tự nên `isEmpty() == false` và phủ định cho `true`.

**Câu 3.** Có thể gọi `CharSequence::isEmpty` trên phần tử `StringBuilder` không?  
**Đáp án:** Có. Builder triển khai `CharSequence`; `isEmpty` phản ánh `length()` hiện tại, không phải `capacity()`.

**Câu 4.** Nếu pipeline có `null`, cần làm gì trước khi gọi `CharSequence::isEmpty`?  
**Đáp án:** Dùng `filter(Objects::nonNull)` trước hoặc xây predicate xử lý null có chủ đích.

**Câu 5.** Vì sao ba giá trị `"ok"`, `new StringBuilder("ok")` và `new StringBuffer("ok")` có thể không gộp bằng `distinct()`?  
**Đáp án:** `CharSequence` không bắt buộc cùng quy tắc `equals/hashCode`; muốn so sánh nội dung nhất quán, chuyển từng phần tử thành `String` trước khi `distinct()`.

**Câu 6.** `CharSequence::isEmpty` có sẵn khi biên dịch mục tiêu Java 14 không?  
**Đáp án:** Không. Phương thức mặc định của giao diện được thêm từ Java 15.

**Câu 7.** Tại sao ví dụ hiện đại dùng `javac --release 17` dù chủ đề thuộc Java 15?  
**Đáp án:** Vì ví dụ dùng thêm `Stream.toList()` có từ Java 16; API `CharSequence.isEmpty` tự nó có từ Java 15, như ví dụ thứ hai đã chứng minh.

## 13. Tài liệu chính thức

- [Java SE 26 — `CharSequence.isEmpty()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/CharSequence.html#isEmpty()) — định nghĩa default method, `length()==0`, và mốc `Since: 15`.
- [Java SE 15 — `CharSequence`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/CharSequence.html) — xác nhận API trong Java 15.
- [Java SE 26 — `Stream.filter(...)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#filter(java.util.function.Predicate)) — hợp đồng predicate, đặc tính intermediate operation.
- [Java SE 26 — `Predicate.not(...)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Predicate.html#not(java.util.function.Predicate)) — phủ định predicate (`Since: 11`).
- [Java SE 26 — `Stream.toList()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList()) — trả list unmodifiable (`Since: 16`).
- [Java SE 26 — `String.isBlank()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#isBlank()) — phân biệt dữ liệu rỗng với chuỗi chỉ gồm whitespace.
