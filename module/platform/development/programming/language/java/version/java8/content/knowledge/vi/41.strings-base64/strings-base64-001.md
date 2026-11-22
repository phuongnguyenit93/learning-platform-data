# String.join và ghép chuỗi theo dấu phân cách (Java 8+)

`String.join` là phương thức `static` của `java.lang.String`, có từ **Java 8** và vẫn được hỗ trợ trên Java hiện đại. Nó nhận một **dấu phân cách** và nhiều phần tử `CharSequence`, sau đó tạo một `String` mới, đặt dấu phân cách **giữa** các phần tử theo thứ tự được duyệt. Nhiệm vụ tưởng chừng nhỏ này liên quan trực tiếp đến định dạng hiển thị, xuất dữ liệu, báo cáo, sinh nhãn, đường dẫn logic và xây chuỗi từ các collection.

Bài này giải thích hai overload của `String.join`, cách xử lý danh sách rỗng, phần tử rỗng và `null`; cách kết hợp với `StringJoiner`, `Stream`/`Collectors.joining`; khác biệt giữa thứ tự của collection và thứ tự callback; việc dùng dấu phân cách khi dữ liệu có chứa chính dấu đó; và cách tránh các lỗi hiệu năng hoặc bảo mật khi ghép chuỗi. Nội dung chính phù hợp **Java 8+**. Những API bổ sung sau Java 8 được ghi rõ phiên bản khi đề cập; không dùng API đã lỗi thời hoặc legacy làm giải pháp ưu tiên.

## 1. Bài toán: ghép nhiều giá trị thành một chuỗi

Giả sử ta có ba tên:

~~~text
Java
Stream
API
~~~

Muốn hiển thị trên một dòng cách nhau bằng `" - "`:

~~~java
String result = String.join(" - ", "Java", "Stream", "API");
System.out.println(result);
// Java - Stream - API
~~~

Dấu `" - "` được chèn **hai lần**, đúng giữa ba phần tử; không có dấu thừa ở đầu hoặc cuối. Với dữ liệu dạng `List`:

~~~java
List<String> languages = Arrays.asList("Java", "Kotlin", "Scala");
String result = String.join(", ", languages);
// Java, Kotlin, Scala
~~~

Hai cách trên đều dùng `String.join`, nhưng Java chọn **overload** khác nhau. `String.join` không phải phép nối mơ hồ theo `Object.toString()`: phần tử phải tương thích `CharSequence`, ví dụ `String` hoặc `StringBuilder`.

### Imports

`String` nằm trong `java.lang` nên không cần import riêng. Với danh sách, stream và joiner:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collectors;
import java.util.stream.Stream;
~~~

## 2. Hai overload `String.join` có từ Java 8

Chữ ký API:

~~~java
public static String join(
        CharSequence delimiter,
        CharSequence... elements)

public static String join(
        CharSequence delimiter,
        Iterable<? extends CharSequence> elements)
~~~

Cả hai trả về một **String mới**. Chúng tạo bản sao nội dung các `CharSequence` tại thời điểm ghép; kết quả không biến thành một “view” tự cập nhật khi collection hoặc phần tử được thay đổi về sau.

| Tham số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `delimiter` | Chuỗi ký tự chèn **giữa** các phần tử | Có thể dài nhiều ký tự; `""` là hợp lệ |
| `elements` dạng varargs | Không, một hoặc nhiều `CharSequence` truyền trực tiếp hoặc dưới dạng array | Chấp nhận `String[]`, `CharSequence[]` |
| `elements` dạng Iterable | Một tập phần tử có thể duyệt: `List`, `Set`... | Thứ tự kết quả theo thứ tự iterator cung cấp |
| Giá trị trả về | Một `String` | Không sửa collection nguồn |
| `delimiter == null` | Không hợp lệ | `NullPointerException` |
| Chính array/Iterable `elements == null` | Không hợp lệ | `NullPointerException` |
| **Một phần tử** là `null` | Được chấp nhận | Thêm đúng chữ `"null"` |

### 2.1. Overload varargs

~~~java
String a = String.join("/", "2026", "11", "06");
// 2026/11/06

String b = String.join("", "J", "a", "v", "a");
// Java

String c = String.join("::", "alpha", "beta");
// alpha::beta
~~~

Varargs là cú pháp tiện lợi để truyền các phần tử dạng tham số liên tiếp. Một array `String[]` cũng có thể được truyền:

~~~java
String[] parts = {"home", "images", "avatar"};
String joined = String.join("/", parts);
// home/images/avatar
~~~

Dấu phân cách không nhất thiết là một ký tự. `" / "`, `" - "`, `"::"`, `"\n"` đều có thể là delimiter. `String.join` chỉ **nối nội dung**: nó không xác nhận các thành phần là path hợp lệ, URL hợp lệ, SQL hợp lệ hoặc record CSV đúng cú pháp.

### 2.2. Overload Iterable

~~~java
List<String> fruits = Arrays.asList("táo", "cam", "nho");

String joined = String.join(", ", fruits);
// táo, cam, nho
~~~

`Iterable<? extends CharSequence>` cho phép dùng với `List<String>`, `List<StringBuilder>` hoặc một loại container khác có phần tử `CharSequence`. Kết quả dựa trên thứ tự được iterator duyệt.

Ví dụ `LinkedHashSet`:

~~~java
Set<String> ordered = new LinkedHashSet<>(
        Arrays.asList("first", "second", "third"));

String label = String.join(">", ordered);
// first>second>third
~~~

`LinkedHashSet` giữ thứ tự chèn; `HashSet` **không cam kết** thứ tự duyệt ổn định. Nếu nghiệp vụ yêu cầu thứ tự cụ thể, hãy dùng `List`, một set có thứ tự hợp đồng thích hợp, hoặc sắp xếp trước khi nối.

### 2.3. Khi `String.join` không nhận được kiểu đầu vào

`String.join(",", List<Integer>)` **không biên dịch** vì `Integer` không triển khai `CharSequence`. Chuyển từng giá trị thành chuỗi:

~~~java
List<Integer> ids = Arrays.asList(10, 20, 30);

String text = ids.stream()
        .map(String::valueOf)
        .collect(Collectors.joining(","));
// 10,20,30
~~~

Với mảng số nguyên primitive, dùng `IntStream.of(...).mapToObj(String::valueOf)` hoặc thuật toán tương đương. Không nên dùng raw type/ép kiểu không an toàn để “thuyết phục” `String.join` nhận `Integer`.

## 3. Quy tắc dấu phân cách: không có dấu đầu/cuối mặc định

Với các phần tử `["a", "b", "c"]`:

| Delimiter | Lời gọi | Kết quả |
| --- | --- | --- |
| `","` | `join(",", "a","b","c")` | `"a,b,c"` |
| `", "` | `join(", ", "a","b","c")` | `"a, b, c"` |
| `"|"` | `join("|", "a","b","c")` | `"a|b|c"` |
| `" / "` | `join(" / ", "a","b","c")` | `"a / b / c"` |
| `""` | `join("", "a","b","c")` | `"abc"` |
| `"\n"` | `join("\n", "a","b","c")` | Ba dòng văn bản |

`String.join` **không thêm dấu phân cách ở đầu hoặc cuối**. Nếu cần cả prefix và suffix, dùng `StringJoiner` hoặc `Collectors.joining(delimiter, prefix, suffix)`:

~~~java
String wrapped = Stream.of("a", "b", "c")
        .collect(Collectors.joining(", ", "[", "]"));
// [a, b, c]
~~~

Không phải thêm dấu thủ công sau vòng lặp rồi cắt ký tự cuối, đặc biệt khi delimiter dài nhiều ký tự hoặc danh sách rỗng.

### Dấu phân cách rỗng khác phần tử rỗng

~~~java
String noSeparator = String.join("", "A", "B", "C");
// ABC

String emptyMiddle = String.join(",", "A", "", "C");
// A,,C

String twoEmpty = String.join(",", "", "");
// ","
~~~

Trong `emptyMiddle`, vẫn có **ba phần tử**; phần tử ở giữa chỉ là chuỗi độ dài 0. `String.join` không tự bỏ các phần tử rỗng.

## 4. Danh sách rỗng, chuỗi rỗng và `null`

Ba trường hợp này có ngữ nghĩa khác nhau; cần kiểm tra riêng:

~~~java
String noElements = String.join(
        ";", Collections.<String>emptyList());
// "" (chuỗi rỗng).

String oneEmpty = String.join(",", "");
// "" (vẫn là một phần tử).

String twoEmpty = String.join(",", "", "");
// "," (hai phần tử, một dấu phân cách).
~~~

Cả trường hợp không có phần tử và một phần tử `""` cùng trả `""`. **Chuỗi kết quả không chứa đủ thông tin để phân biệt hai trường hợp ban đầu**. Đây là lý do không dùng `String.join` để serialization nếu cần round-trip chính xác mà không có encoding/escaping rõ.

### 4.1. Phần tử null trở thành chữ `"null"`

Theo đặc tả hiện hành:

~~~java
String value = String.join("|", Arrays.asList("A", null, ""));
// "A|null|"
~~~

Lưu ý: đây là **chuỗi bốn ký tự `"null"`**, không phải một `null` được giữ như dữ liệu typed. Nếu sau đó tách lại, không thể tự biết `"null"` là giá trị gốc null hay chính literal `"null"`.

### 4.2. Delimiter null hay container null sẽ ném lỗi

~~~java
// SAI: delimiter không được null.
// String.join(null, "a", "b") -> NullPointerException.

// SAI: chính mảng elements null.
// String.join(",", (CharSequence[]) null) -> NullPointerException.

// SAI: chính Iterable null.
// String.join(",", (Iterable<String>) null) -> NullPointerException.
~~~

Điều này **khác** việc một phần tử trong array/Iterable là null. Không viết code dựa vào việc mọi null đều được tự đổi thành chuỗi `"null"`; chỉ **individual element** có behavior đó.

### 4.3. Bỏ null, thay thế null hoặc từ chối null

Nếu business muốn **bỏ phần tử null**:

~~~java
List<String> values = Arrays.asList("A", null, "B");

String text = values.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.joining("|"));
// A|B
~~~

Cần `import java.util.Objects;`. Nếu muốn dùng một placeholder rõ ràng:

~~~java
String text = values.stream()
        .map(s -> s == null ? "(missing)" : s)
        .collect(Collectors.joining("|"));
// A|(missing)|B
~~~

Nếu null là dữ liệu không hợp lệ, hãy **validate và trả lỗi** thay vì lặng lẽ chuyển thành `"null"` hoặc bỏ qua. Việc lựa chọn “skip/null marker/error” phải dựa trên hợp đồng nghiệp vụ, không phải lựa chọn ngẫu nhiên.

## 5. `StringJoiner`: thêm dần, có prefix/suffix

`java.util.StringJoiner` là lớp Java 8 được thiết kế để dựng chuỗi phân cách bằng các lần `add`:

~~~java
StringJoiner joiner = new StringJoiner("; ", "[", "]");
joiner.add("java").add("stream").add("api");

String result = joiner.toString();
// [java; stream; api]
~~~

Các tham số constructor:

~~~java
new StringJoiner(delimiter)
new StringJoiner(delimiter, prefix, suffix)
~~~

`delimiter` đứng **giữa** các phần tử; `prefix` xuất hiện trước phần tử đầu, `suffix` xuất hiện sau phần tử cuối. Kết quả được tạo khi gọi `toString()`, có thể tiếp tục `add` trước lần chuyển đổi kế tiếp.

### 5.1. Khi chưa thêm phần tử

~~~java
StringJoiner joiner = new StringJoiner(";", "[", "]");
String emptyDefault = joiner.toString();
// "[]"
~~~

Với prefix/suffix, trạng thái **chưa thêm phần tử** mặc định hiển thị `prefix + suffix`. Nếu không có prefix và suffix, `new StringJoiner(";").toString()` trả `""`.

Dùng `setEmptyValue(...)` để thay hiển thị của trạng thái **chưa thêm gì**:

~~~java
joiner.setEmptyValue("<none>");
String beforeAdd = joiner.toString();
// "<none>"

joiner.add("java");
String afterAdd = joiner.toString();
// "[java]"
~~~

`setEmptyValue` không có nghĩa “phần tử rỗng sẽ được thay bằng chuỗi này”. Một lần gọi `add("")` cũng làm joiner **không còn empty theo trạng thái** dù nội dung thêm vào có độ dài 0.

### 5.2. `StringJoiner.add(null)`

`add(null)` thêm literal `"null"`, giống quy tắc từng phần tử của `String.join`:

~~~java
StringJoiner j = new StringJoiner("|");
j.add("A").add(null).add("B");
// "A|null|B"
~~~

Trước khi dựa vào behavior này, quyết định xem dữ liệu của bạn cần giữ null, bỏ null hay từ chối null. Bản thân Joiner không giữ metadata về null typed.

### 5.3. `merge` hai joiner

~~~java
StringJoiner left = new StringJoiner(",");
StringJoiner right = new StringJoiner(",");

left.add("a");
right.add("b").add("c");
left.merge(right);
// left.toString() = "a,b,c".
~~~

`merge(other)` đưa nội dung `other` vào receiver mà **không mang theo prefix/suffix của other**. Nếu other đang trống theo trạng thái, merge không có tác dụng. Với **delimiter khác nhau**, nội dung joined của other được coi là **một phần tử** mới của receiver; đừng coi merge là thao tác luôn trải phẳng mọi phần tử độc lập bất kể delimiter.

`StringJoiner` là một builder mutable; **không tự thread-safe**. Đừng cho nhiều thread cùng gọi `add` trên một instance khi không có đồng bộ phù hợp. Dùng mỗi thread một joiner hoặc dùng `Collectors.joining` để stream framework quản lý container trung gian theo hợp đồng.

### 5.4. `length()`

`StringJoiner.length()` trả độ dài **biểu diễn chuỗi hiện tại**, tương đương độ dài `toString()`, kể cả prefix/suffix và emptyValue. Đây là số **UTF-16 code units**, không nhất thiết là số ký tự Unicode người dùng nhìn thấy (grapheme clusters). Không dùng trực tiếp `length()` để đếm chữ hiển thị hoặc độ rộng pixel.

## 6. `Collectors.joining` cho pipeline Stream

Khi cần `filter`, `map`, `sorted` hoặc xử lý tập dữ liệu trước khi ghép, `Collectors.joining` là công cụ tự nhiên:

~~~java
List<String> names = Arrays.asList("java", "stream", "api");

String output = names.stream()
        .filter(s -> !s.equals("stream"))
        .map(String::toUpperCase)
        .collect(Collectors.joining(" | "));
// JAVA | API
~~~

Những overload chính của `Collectors`, đều có từ Java 8:

| API | Cách ghép | Ví dụ |
| --- | --- | --- |
| `Collectors.joining()` | Không có delimiter | `"J", "a", "v", "a"` → `"Java"` |
| `Collectors.joining(delimiter)` | Delimiter giữa các phần tử | `"a", "b"` → `"a,b"` nếu delimiter là comma |
| `Collectors.joining(delimiter,prefix,suffix)` | Có dấu bao quanh | `"a", "b"` → `"[a,b]"` với comma, `[`, `]` |

Ví dụ:

~~~java
String compact = Stream.of("J", "a", "v", "a")
        .collect(Collectors.joining());
// Java

String bracketed = Stream.of("java", "stream")
        .map(String::toUpperCase)
        .collect(Collectors.joining(" | ", "{", "}"));
// {JAVA | STREAM}
~~~

`Collectors.joining` dùng `CharSequence`; nếu stream trả `Integer` hay object nghiệp vụ, hãy chuyển thành `String` trong `map`, **không ép kiểu collector để nhận sai loại dữ liệu**.

### 6.1. Nối số và giá trị khác kiểu String

~~~java
String numbers = IntStream.of(10, 20, 30)
        .mapToObj(String::valueOf)
        .collect(Collectors.joining(","));
// 10,20,30
~~~

Đây là pipeline hợp lệ với `IntStream` và `Collectors` trong Java 8. Nếu phần tử là `BigDecimal`, ngày giờ hoặc enum, chuyển sang biểu diễn text theo policy ứng dụng (ví dụ formatter và locale/zone phù hợp) trước khi join. Không mặc định `String.valueOf` luôn là format phù hợp để xuất dữ liệu cho khách hàng.

### 6.2. `String.join` hay `Collectors.joining`?

Chọn theo nguồn dữ liệu và mục tiêu:

- Đã có `String[]` hoặc `List<String>`, chỉ cần nối: **`String.join(delimiter, elements)`** là ngắn gọn.
- Đang xử lý `Stream` qua `filter`/`map`/`sorted`: **`collect(Collectors.joining(delimiter))`**.
- Cần thêm dần trong vòng lặp có điều kiện, prefix/suffix hoặc custom empty result: **`StringJoiner`**.
- Cần xây format phức tạp hơn chỉ ghép danh sách (nhánh điều kiện, escaping nhiều lớp, token logic): có thể chọn `StringBuilder` hoặc một serializer/parser chuyên dụng.

Không mặc định một cách luôn có hiệu năng tốt nhất; benchmark dữ liệu thực khi hiệu năng đáng quan tâm.

### 6.3. `Collectors.joining` và nguồn rỗng

~~~java
String a = Stream.<String>empty()
        .collect(Collectors.joining(","));
// "".

String b = Stream.<String>empty()
        .collect(Collectors.joining(",", "[", "]"));
// "[]".
~~~

Ở trạng thái không có phần tử, collector có prefix/suffix mặc định trả `prefix + suffix`. Đây là hành vi tương tự `StringJoiner` chưa có phần tử. Nếu muốn emptyValue tùy biến như `"<none>"`, dùng `StringJoiner.setEmptyValue` hoặc kiểm tra kết quả dựa trên input theo đúng nhu cầu; `Collectors.joining` không có tham số emptyValue riêng.

## 7. Thứ tự phần tử và parallel stream

`String.join` với `Iterable` dựa trên **iterator order**. Do đó:

~~~java
List<String> sequence = Arrays.asList("first", "second", "third");
String result = String.join(" > ", sequence);
// first > second > third
~~~

Với `HashSet`, **không bảo đảm thứ tự**:

~~~java
Set<String> values = new HashSet<>(
        Arrays.asList("first", "second", "third"));

String unstableDisplay = String.join(" > ", values);
// Thứ tự phụ thuộc vào iterator của HashSet.
~~~

Nếu cần thứ tự ổn định:

~~~java
String sorted = values.stream().sorted()
        .collect(Collectors.joining(" > "));
~~~

Hoặc dùng `LinkedHashSet` nếu yêu cầu là giữ **thứ tự chèn**, `TreeSet` nếu yêu cầu là **thứ tự so sánh**. Không dựa vào một lần chạy `HashSet.toString()` cho biết thứ tự hợp đồng.

### 7.1. Parallel có làm đổi thứ tự nối chuỗi?

Với một **ordered stream** từ `List`:

~~~java
List<String> source = Arrays.asList("a", "b", "c");

String result = source.parallelStream()
        .collect(Collectors.joining(","));
// a,b,c
~~~

`Collectors.joining` giữ **encounter order** khi pipeline có ràng buộc thứ tự. Trong parallel stream, các tác vụ xử lý có thể chạy xen kẽ trên nhiều thread, nhưng collector vẫn có thể hợp kết quả theo đúng encounter order của nguồn. **Thứ tự callback thực thi ≠ thứ tự phần tử của kết quả**.

Nếu gọi `unordered()` hoặc nguồn vốn không có encounter order, thứ tự ghép không có hợp đồng giữ thứ tự nguồn. Không dùng `parallel().forEach(builder::append)` trên một `StringBuilder` chia sẻ: đây là mutable side effect không thread-safe và không có thứ tự được bảo đảm.

### 7.2. Không thêm `parallel()` chỉ vì nhiều dòng

Nối nhiều chuỗi cần cấp phát bộ nhớ cho kết quả cuối cùng. Parallel stream có chi phí partition, combiner và đồng bộ; với dữ liệu nhỏ hoặc ít xử lý trước join, sequential thường đơn giản hơn. Hãy đo benchmark đại diện nếu thực sự cân nhắc tối ưu, không suy từ “parallel là nhanh”.

## 8. Nối chuỗi khác serialization có thể đọc ngược

Một phép join đơn thuần **không thoát (escape) delimiter** có trong dữ liệu. Ví dụ:

~~~java
List<String> source = Arrays.asList("A,B", "C");
String text = String.join(",", source);
// A,B,C
~~~

Nếu tách bằng dấu phẩy, ta không thể biết nguồn ban đầu có 2 phần tử `["A,B", "C"]` hay 3 phần tử `["A", "B", "C"]`. Thêm `null` và chuỗi `""` càng làm mất khả năng round-trip.

### 8.1. Không dùng `String.join` trực tiếp để xuất CSV

CSV có quy tắc riêng cho dấu phẩy, dấu nháy kép và newline nằm trong một field. Ví dụ:

~~~java
List<String> fields = Arrays.asList(
        "Alice, Jr.", "He said \"OK\"", "line\nbreak");

String raw = String.join(",", fields);
// Không đúng CSV an toàn cho mọi field.
~~~

Một hàm escape **tối thiểu** theo kiểu CSV dùng dấu phẩy, dấu nháy kép:

~~~java
static String csvField(String value) {
    if (value == null) return "";
    boolean quote = value.indexOf(',') >= 0
            || value.indexOf('"') >= 0
            || value.indexOf('\n') >= 0
            || value.indexOf('\r') >= 0;
    return quote ? "\"" + value.replace("\"", "\"\"") + "\"" : value;
}
~~~

Khi gọi:

~~~java
String csv = fields.stream()
        .map(MyClass::csvField)
        .collect(Collectors.joining(","));
~~~

`MyClass::csvField` là **minh họa**: thay `MyClass` bằng tên lớp tự định nghĩa có method trên, hoặc dùng chương trình hoàn chỉnh bên dưới. Khi field chứa delimiter, double quote hoặc xuống dòng, phải **quote** field và nhân đôi double quote bên trong. Thực tế nên dùng thư viện CSV đáng tin, xử lý header, record separator, charset, rule về null, schema và chống spreadsheet formula injection theo yêu cầu bảo mật; ví dụ tự viết chỉ diễn đạt nguyên tắc cơ bản, **không phải CSV library đầy đủ**.

### 8.2. Không xây SQL từ dữ liệu bằng nối chuỗi

~~~java
// Không an toàn: không dùng String.join để nhúng giá trị từ người dùng.
String inClause = String.join(",", userSuppliedIds);
~~~

Ngay cả khi dấu phân cách đúng, SQL injection và xử lý escaping/type vẫn tồn tại. Dùng **prepared statements** với tham số bind, phương pháp hỗ trợ danh sách/tham số của database driver hoặc ORM. `String.join` phù hợp nối các **placeholder hoặc token đã được hệ thống xác thực**, không phải thay thế cơ chế tham số hóa SQL.

### 8.3. Không dùng để escape URL, JSON hoặc shell

Dấu phân cách trong `String.join` không biết cú pháp URL, JSON, HTML, CSV hoặc shell. Ví dụ nối `"/"` giữa các đoạn path **không tự URL-encode**, không normalize separator và không xử lý path traversal. Với URL dùng các API URI/URL encoding phù hợp; với JSON dùng serializer; với filesystem dùng `Path.resolve(...)`; với shell tốt hơn truyền argument array qua API process thay vì tự tạo một command string.

## 9. `String.join` và `String.split` không phải hai hàm đảo nhau tổng quát

Ngay cả với dữ liệu không chứa delimiter, `String.split(regex)` dùng **biểu thức chính quy**, không phải delimiter literal giống `join`:

~~~java
String joined = String.join("|", "A", "B", "C");
// A|B|C.

// Phải escape regex metacharacter "|":
String[] parts = joined.split("\\|");
// ["A", "B", "C"].
~~~

Nếu bạn gọi `joined.split("|")`, `|` được hiểu theo **regex alternation**, không phải ký tự `|` literal. Dùng `Pattern.quote(delimiter)` khi delimiter là một chuỗi literal động:

~~~java
String[] parts = joined.split(Pattern.quote("|"), -1);
~~~

Đoạn này cần `import java.util.regex.Pattern;`. Tham số `limit = -1` giúp giữ **trailing empty fields**, vì `split(regex)` mặc định có thể loại phần tử rỗng ở cuối. Tuy nhiên, kể cả dùng `Pattern.quote` và `-1`, dữ liệu có delimiter **bên trong phần tử** hoặc null vẫn không thể round-trip chính xác nếu không có cơ chế escaping/format riêng.

Ví dụ:

~~~java
String s = String.join(",", "A", "", "B");
// A,,B — có một field rỗng ở giữa.

String endEmpty = String.join(",", "A", "");
// A, — field cuối rỗng.

String[] a = endEmpty.split(",", -1);
// ["A", ""].
~~~

Đừng nhầm `split` với parser CSV: regex split không hiểu dấu nháy kép bảo vệ dấu phẩy trong CSV.

## 10. So sánh với `StringBuilder` và nối `+` trong vòng lặp

Trước khi có `String.join`, người ta thường dùng vòng lặp:

~~~java
StringBuilder builder = new StringBuilder();

for (String part : parts) {
    if (builder.length() > 0) {
        builder.append(", ");
    }
    builder.append(part);
}

String output = builder.toString();
~~~

**Cách này có một lỗi tiềm ẩn:** nếu phần tử đầu là `""` thì `builder.length() == 0` vẫn đúng ở phần tử tiếp theo, khiến thiếu delimiter. Cần dùng cờ `first` riêng:

~~~java
StringBuilder builder = new StringBuilder();
boolean first = true;

for (String part : parts) {
    if (!first) builder.append(", ");
    builder.append(part);
    first = false;
}
~~~

Dù hợp lệ, nếu chỉ nối dữ liệu với delimiter thì `String.join(", ", parts)` rõ ràng hơn và giảm lỗi. `StringBuilder` phù hợp khi có nhiều nhánh điều kiện, giá trị không đồng dạng, escape phức tạp hoặc cần xây một cấu trúc text lớn có kiểm soát.

### Tránh `result += element` trong vòng lặp lớn

~~~java
String result = "";
for (String part : parts) {
    result += part; // Có thể cấp phát chuỗi trung gian lặp lại.
}
~~~

Vì `String` bất biến, cách ghép cộng dồn có thể sinh nhiều chuỗi trung gian và có chi phí lớn khi lượng dữ liệu tăng. Compiler/JVM có tối ưu, nhưng đừng mặc định cách này phù hợp cho một danh sách lớn. `String.join`/`StringJoiner`/`StringBuilder` thường làm rõ ý định hơn.

Không có API nào tự giải quyết output quá lớn: cuối cùng kết quả vẫn là một `String` cần đủ bộ nhớ. Nếu muốn ghi hàng triệu phần tử ra file/network, nên cân nhắc **ghi theo luồng** bằng `Writer`/`BufferedWriter` thay vì tạo String khổng lồ trong RAM.

## 11. Hiệu năng, bộ nhớ và độ dài Unicode

Về mặt khái niệm, một phép join phải đi qua các phần tử và tạo bản sao ký tự cần thiết cho output. Chi phí phụ thuộc tổng độ dài phần tử, số dấu phân cách và số phần tử. Với dữ liệu nhỏ, ưu tiên API **đúng và dễ đọc**; với dữ liệu lớn, đo trên benchmark thích hợp.

### 11.1. `String.join` không giới hạn kết quả tự động

Nếu ghép rất nhiều giá trị vào một chuỗi duy nhất, output có thể rất lớn. Ngay cả khi input đến từ stream, `collect(joining(...))` vẫn cần tạo một `String` cuối cùng chứa toàn bộ kết quả. Nếu cần giới hạn kích thước, áp policy kiểm tra số phần tử/tổng độ dài trước khi ghép hoặc chuyển sang ghi streaming.

### 11.2. Unicode không đồng nghĩa mỗi glyph có độ dài 1

~~~java
String emoji = "😀";
int codeUnits = emoji.length();
// Trong UTF-16, một emoji ngoài BMP thường chiếm 2 code units.
~~~

`StringJoiner.length()` và `String.length()` đo **UTF-16 code units**, không phải số grapheme hay độ rộng hiển thị. Với nhãn hiển thị nhiều ngôn ngữ, không dùng số code units để tự suy số chữ nhìn thấy. Trong `String.join`, delimiter cũng là `CharSequence` Unicode, không giới hạn ASCII.

### 11.3. Thứ tự xử lý và dữ liệu mutable

`String.join` tạo kết quả mới từ dữ liệu nó đọc. Đừng mutate một `List` đang bị thread khác duyệt trong lúc join; hành vi có thể không ổn định hoặc gây exception, tùy collection. Nếu yêu cầu output nhất quán, dùng input snapshot/immutable hoặc đồng bộ hóa theo thiết kế.

## 12. Chương trình Java hoàn chỉnh — từ varargs đến CSV escaping

Tạo file **`StringJoinLessonDemo.java`**. Toàn bộ API Java trong ví dụ có từ Java 8. Chương trình dùng dữ liệu cố định nên các dòng kết quả độc lập với ngày giờ và locale của máy. Mã đã được biên dịch bằng JDK 17 với `--release 17` và có **13 phép kiểm tra**; chỉ in `all checks passed` nếu mọi điều kiện đều đạt.

~~~java
import java.util.*;
import java.util.stream.*;

public final class StringJoinLessonDemo {
    static void check(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    static String csvField(String value) {
        if (value == null) return "";
        boolean quote = value.indexOf(',') >= 0
                || value.indexOf('"') >= 0
                || value.indexOf('\n') >= 0
                || value.indexOf('\r') >= 0;
        return quote ? "\"" + value.replace("\"", "\"\"") + "\"" : value;
    }

    public static void main(String[] args) {
        String varargs = String.join(" - ", "Java", "Stream", "API");
        List<String> fruit = Arrays.asList("táo", "cam", "nho");
        String iterable = String.join(", ", fruit);
        String empty = String.join(";", Collections.<String>emptyList());
        String withNull = String.join("|", Arrays.asList("A", null, ""));
        String filtered = fruit.stream().filter(s -> !s.equals("cam"))
                .collect(Collectors.joining(" / "));

        System.out.println("varargs: " + varargs);
        System.out.println("iterable: " + iterable);
        System.out.println("empty: <" + empty + ">");
        System.out.println("null and empty: <" + withNull + ">");
        System.out.println("filtered: " + filtered);
        System.out.println("no delimiter: " + String.join("", "A", "B", "C"));

        StringJoiner joiner = new StringJoiner("; ", "[", "]");
        System.out.println("joiner empty default: " + joiner);
        joiner.setEmptyValue("<none>");
        System.out.println("joiner empty custom: " + joiner);
        joiner.add("java").add(null);
        System.out.println("joiner populated: " + joiner);
        System.out.println("joiner length: " + joiner.length());

        StringJoiner left = new StringJoiner(",");
        StringJoiner right = new StringJoiner(",");
        left.add("a");
        right.add("b").add("c");
        left.merge(right);
        System.out.println("merged: " + left);

        String bracketed = Stream.of("java", "stream")
                .map(String::toUpperCase)
                .collect(Collectors.joining(" | ", "{", "}"));
        String joinedInts = IntStream.of(10, 20, 30)
                .mapToObj(String::valueOf)
                .collect(Collectors.joining(","));
        System.out.println("collector: " + bracketed);
        System.out.println("numbers: " + joinedInts);
        String compact = Stream.of("J", "a", "v", "a")
                .collect(Collectors.joining());
        System.out.println("joining without delimiter: " + compact);

        LinkedHashSet<String> ordered = new LinkedHashSet<>(
                Arrays.asList("first", "second", "third"));
        System.out.println("linked set: " + String.join(">", ordered));

        List<String> fields = Arrays.asList("Alice, Jr.", "He said \"OK\"", "line\nbreak");
        String unsafeCsv = String.join(",", fields);
        String safeCsv = fields.stream().map(StringJoinLessonDemo::csvField)
                .collect(Collectors.joining(","));
        System.out.println("raw CSV line breaks: " + unsafeCsv.contains("\n"));
        System.out.println("escaped CSV: " + safeCsv.replace("\n", "\\n"));

        boolean nullDelimiterRejected = false;
        try {
            String.join(null, "a", "b");
        } catch (NullPointerException ex) {
            nullDelimiterRejected = true;
        }
        System.out.println("null delimiter rejected: " + nullDelimiterRejected);

        check(varargs.equals("Java - Stream - API"), "varargs");
        check(iterable.equals("táo, cam, nho"), "iterable");
        check(empty.isEmpty(), "empty iterable");
        check(withNull.equals("A|null|"), "null element");
        check(filtered.equals("táo / nho"), "collector filter");
        check(joiner.toString().equals("[java; null]"), "StringJoiner");
        check(joiner.length() == "[java; null]".length(), "length");
        check(left.toString().equals("a,b,c"), "merge");
        check(bracketed.equals("{JAVA | STREAM}"), "collector with wrappers");
        check(joinedInts.equals("10,20,30"), "nonstring mapping");
        check(compact.equals("Java"), "joining no delimiter");
        check(safeCsv.equals("\"Alice, Jr.\",\"He said \"\"OK\"\"\",\"line\nbreak\""),
                "CSV quoting");
        check(nullDelimiterRejected, "null delimiter");
        System.out.println("all checks passed");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 StringJoinLessonDemo.java
java StringJoinLessonDemo
~~~

**Stdout đầy đủ đã kiểm tra:**

~~~text
varargs: Java - Stream - API
iterable: táo, cam, nho
empty: <>
null and empty: <A|null|>
filtered: táo / nho
no delimiter: ABC
joiner empty default: []
joiner empty custom: <none>
joiner populated: [java; null]
joiner length: 12
merged: a,b,c
collector: {JAVA | STREAM}
numbers: 10,20,30
joining without delimiter: Java
linked set: first>second>third
raw CSV line breaks: true
escaped CSV: "Alice, Jr.","He said ""OK""","line\nbreak"
null delimiter rejected: true
all checks passed
~~~

### Giải thích output

1. `varargs` và `iterable` là hai overload khác nhau, cùng giữ nguyên thứ tự phần tử nguồn.
2. `empty: <>` cho thấy một `Iterable` rỗng được ghép thành String rỗng; cặp `< >` chỉ là ký hiệu in để phân biệt String rỗng.
3. `null and empty: <A|null|>` minh họa phần tử null biến thành chữ `"null"`, phần tử `""` sau cùng vẫn tạo dấu `|` trước nó.
4. `filtered` cho thấy pipeline dùng `filter` rồi `Collectors.joining`, không cần chuyển thành List ở giữa.
5. `joiner empty default` là `[]`, nhưng sau `setEmptyValue("<none>")` ở trạng thái chưa thêm gì, giá trị là `<none>`; sau `add`, prefix/suffix quay lại theo cơ chế bình thường.
6. `joiner populated` giữ dấu `"; "` giữa các phần tử; `length()` đo độ dài chuỗi hiển thị, ở đây là 12 UTF-16 code units.
7. `merged` ghép hai joiner tương thích delimiter, tạo `a,b,c`; không thêm prefix/suffix dư.
8. `collector` có filter/map dễ tổ hợp, `numbers` chuyển dữ liệu int sang String trước khi join; `joining without delimiter` ghép liên tục thành `Java`.
9. `LinkedHashSet` giữ thứ tự chèn; không được suy kết quả tương tự với `HashSet` không có order được bảo đảm.
10. Dữ liệu CSV thô có newline trong field, vì thế join trực tiếp không đủ. Bản đã escape quote bằng cách nhân đôi `"` và bao field cần thiết trong `"..."`. Để stdout hiển thị trên **một dòng**, chương trình thay newline bằng literal `\n` khi in.
11. `null delimiter rejected` xác nhận delimiter null ném `NullPointerException`.
12. `all checks passed` được in sau **13 phép check**; các ví dụ null, collection rỗng, prefix/suffix, merge, Unicode, numbers và escape đều đã được kiểm thử.

Đây là ví dụ học tập, không phải công cụ CSV import/export tổng quát. Trong ứng dụng dữ liệu hoặc an ninh, hãy chọn serializer/CSV library có policy encoding, line ending, quote, escaping và formula injection phù hợp.

## 13. Ví dụ áp dụng: tên, danh sách quyền và nhãn báo cáo

### 13.1. Hiển thị tên nhóm

~~~java
List<String> names = Arrays.asList("An", "Bình", "Chi");

String label = String.join(", ", names);
// An, Bình, Chi
~~~

Nếu một tên chứa dấu phẩy, chuỗi kết quả chỉ là **nhãn hiển thị**, không đủ an toàn để khôi phục danh sách tên ban đầu bằng `split(",")`. Cần giữ danh sách typed ở tầng dữ liệu, không coi nhãn là schema lưu trữ.

### 13.2. Danh sách quyền theo thứ tự ổn định

~~~java
Set<String> permissions = new HashSet<>(
        Arrays.asList("READ", "WRITE", "EXPORT"));

String display = permissions.stream()
        .sorted()
        .collect(Collectors.joining(" | "));
// EXPORT | READ | WRITE
~~~

Sorting là quyết định để output ổn định; không dựa vào iterator không xác định của `HashSet`. Nếu thứ tự quyền do sản phẩm định nghĩa khác alphabetic, dùng comparator rõ ràng thay vì `sorted()` mặc định.

### 13.3. Nối dòng thông báo

~~~java
List<String> lines = Arrays.asList(
        "Processing completed",
        "Saved: 3 records",
        "Errors: 0");

String message = String.join(System.lineSeparator(), lines);
~~~

`System.lineSeparator()` có thể là `\r\n` hoặc `\n` theo môi trường. Nó hợp lý khi tạo text cho hệ thống hiện tại, **nhưng không hợp lý nếu một giao thức/tệp yêu cầu line ending cố định**. Với format được chuẩn hóa, truyền delimiter được quy định tường minh, ví dụ `"\n"`.

### 13.4. Tạo biểu diễn bracketed

~~~java
String label = Stream.of("A", "B", "C")
        .collect(Collectors.joining(";", "<", ">"));
// <A;B;C>
~~~

Khi không có phần tử, kết quả là `<>`, **không** phải `""`. Nếu ứng dụng muốn `"<empty>"` thay thế, dùng `StringJoiner.setEmptyValue("<empty>")`, hoặc quyết định trước khi join.

## 14. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Tự thêm delimiter ở mọi vòng lặp | Dấu thừa ở cuối hoặc đầu | Dùng `String.join` |
| Cắt dấu phân cách cuối bằng `substring` | Sai khi danh sách rỗng hoặc delimiter dài | `StringJoiner`/`String.join` |
| Kiểm tra `StringBuilder.length()>0` để biết đã có phần tử | Thất bại nếu phần tử trước là `""` | Cờ `first` hoặc `StringJoiner` |
| Cho rằng `String.join` tự bỏ phần tử rỗng | `"A", "", "B"` thành `"A,,B"` | `filter` tường minh nếu muốn |
| Cho rằng `String.join` tự bỏ null | Phần tử null thành literal `"null"` | `filter(Objects::nonNull)` hoặc map/validate |
| Cho rằng truyền container null cũng thành `"null"` | `NullPointerException` | Kiểm tra container và delimiter trước |
| Truyền `List<Integer>` trực tiếp | Không thỏa `Iterable<? extends CharSequence>` | `map(String::valueOf)` rồi `Collectors.joining` |
| Dùng `HashSet` và trông chờ output luôn có thứ tự | Không có encounter order được hứa | `List`, `LinkedHashSet`, `TreeSet` hoặc sort |
| Dùng `parallel().forEach(sharedBuilder::append)` | Race và thứ tự không xác định | Collector có hợp đồng/collect theo thứ tự |
| Coi `setEmptyValue` dùng cho một phần tử `""` | Không, joiner đã có phần tử | Phân biệt chưa add và đã add |
| Nghĩ `merge` luôn trải phẳng kể cả delimiter khác | Other có thể được thêm như một phần tử text | Kiểm tra hợp đồng `merge` |
| Dùng `String.join` trực tiếp tạo CSV với field chứa dấu phẩy | Phá cấu trúc record | CSV serializer/escaping |
| Ghép SQL từ dữ liệu do người dùng cung cấp | Nguy cơ SQL injection | Prepared statements và bind |
| Ghép path bằng `"/"` trên mọi hệ điều hành | Không xử lý filesystem/path rules | `Path.resolve` |
| Ghép URL segments mà không encode | Sai URI hoặc injection | URI/URL encoding đúng ngữ cảnh |
| Tin `String.split` luôn đảo được `String.join` | Dữ liệu có delimiter, null, empty làm mất thông tin | Dùng format/escaping có round-trip |
| Dùng `split("|")` để tách literal `|` | `|` là ký tự regex đặc biệt | `Pattern.quote("|")` |
| Quên `split(...,-1)` khi cần trailing empty field | Bị mất dữ liệu rỗng cuối | Truyền `limit=-1` |
| Dùng `+=` trong loop rất lớn | Có thể tạo nhiều chuỗi trung gian | `StringBuilder`/`StringJoiner` |
| Nối hàng triệu phần tử vào một String | Áp lực RAM và giới hạn String | Ghi streaming khi phù hợp |
| Dùng `String.length()` làm số glyph hiển thị | UTF-16 length khác grapheme count | Chọn API Unicode theo yêu cầu |
| Dùng `String.join` để tự động serialize objects | Không xử lý schema, quoting, escaping | Chọn serializer đúng loại |

## 15. Bài tập kèm đáp án

### Bài 1 — Tạo chuỗi từ varargs

Nối `"a"`, `"b"`, `"c"` bằng dấu `" - "`.

**Đáp án:**

~~~java
String result = String.join(" - ", "a", "b", "c");
// a - b - c
~~~

### Bài 2 — Nối List

Một `List<String>` gồm `"Hà"`, `"Mai"`, `"Nam"`. Ghép bằng `", "`.

**Đáp án:**

~~~java
String result = String.join(", ", Arrays.asList("Hà", "Mai", "Nam"));
// Hà, Mai, Nam
~~~

### Bài 3 — Mảng/danh sách rỗng

`String.join(";", Collections.<String>emptyList())` trả về gì?

**Đáp án:** `""`, một chuỗi rỗng. Không có phần tử thì không có delimiter. Nếu dùng collector có prefix/suffix, output rỗng sẽ khác: `Collectors.joining(",", "[", "]")` trả `"[]"` cho stream rỗng.

### Bài 4 — Phần tử null

`String.join("|", Arrays.asList("A", null, "B"))` có ném lỗi không?

**Đáp án:** Không. Phần tử null thành literal `"null"`, kết quả là `"A|null|B"`. Nhưng delimiter null hoặc **chính Iterable** null sẽ ném `NullPointerException`.

### Bài 5 — Bỏ null trước khi nối

Từ `["A", null, "B"]`, muốn `A|B`.

**Đáp án:**

~~~java
String result = values.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.joining("|"));
// A|B.
~~~

`values` là List ở đề bài và cần `import java.util.Objects;`. Nếu null phải hiển thị như “chưa có dữ liệu” thay vì bị bỏ, thay bằng placeholder có chủ đích.

### Bài 6 — Nối số

Từ `[10,20,30]`, muốn `"10,20,30"`.

**Đáp án:**

~~~java
String result = IntStream.of(10, 20, 30)
        .mapToObj(String::valueOf)
        .collect(Collectors.joining(","));
~~~

Không truyền `List<Integer>` trực tiếp cho `String.join`.

### Bài 7 — Dấu bao quanh

Nối `"x"` và `"y"` bằng comma, output cần `"[x,y]"`.

**Đáp án:**

~~~java
String result = Stream.of("x", "y")
        .collect(Collectors.joining(",", "[", "]"));
~~~

Hoặc tạo `new StringJoiner(",", "[", "]")` rồi gọi `add("x").add("y")`.

### Bài 8 — Empty value của StringJoiner

Tạo `StringJoiner(";", "[", "]")`, gọi `setEmptyValue("<none>")` rồi `add("")`. `toString()` là `"<none>"` hay `"[]"`?

**Đáp án:** `"[]"` vì đã có **một lần add**; emptyValue chỉ áp dụng khi chưa có phần tử nào được thêm. Phần tử vừa thêm là chuỗi độ dài 0, nhưng joiner không còn trạng thái empty.

### Bài 9 — Thứ tự HashSet

Một `HashSet<String>` gồm `READ`, `WRITE`, `EXPORT`. Làm sao có output theo alphabetic?

**Đáp án:**

~~~java
String sorted = permissions.stream()
        .sorted()
        .collect(Collectors.joining(" | "));
// EXPORT | READ | WRITE
~~~

`permissions` là Set ở đề bài. Không dựa vào iteration order của `HashSet`.

### Bài 10 — Tách lại dữ liệu có dấu phân cách

Nguồn là `["A,B", "C"]`. Ghép dấu phẩy thành `"A,B,C"`. Có thể đảo lại bằng `split(",")` không?

**Đáp án:** Không, vì dấu phẩy bên trong `"A,B"` bị nhầm với delimiter. Muốn round-trip phải dùng định dạng có quoting/escaping và parser tương ứng.

### Bài 11 — Split literal pipe

`String.join("|", "A", "B")` cho `"A|B"`. Tách chính xác theo literal `|` bằng regex thế nào?

**Đáp án:**

~~~java
String[] tokens = "A|B".split(Pattern.quote("|"), -1);
~~~

Cần `java.util.regex.Pattern`. `split("|")` không đúng vì `|` là metacharacter trong regex.

### Bài 12 — CSV có dấu phẩy và dấu nháy

Một field là `He said "OK"`. `String.join(",", fields)` có tự escape không?

**Đáp án:** Không. Field CSV phải được quote khi cần, double quote trong field phải nhân đôi. Dùng thư viện CSV khi triển khai thực tế; `String.join` chỉ đặt delimiter, không thực thi CSV grammar.

### Bài 13 — Vấn đề StringBuilder

Vì sao dùng `builder.length() > 0` để quyết định có thêm delimiter có thể sai?

**Đáp án:** Nếu phần tử đầu là chuỗi rỗng, sau khi thêm nó builder vẫn có length 0. Phần tử thứ hai được thêm mà thiếu delimiter. Dùng biến `first` hoặc `StringJoiner`.

### Bài 14 — Parallel joining

`List.of("a", "b", "c").parallelStream().collect(Collectors.joining(","))` có đảm bảo thứ tự output không?

**Đáp án:** Với một **ordered stream** từ List, joining giữ encounter order, kết quả là `"a,b,c"`. Tuy nhiên `List.of` chỉ xuất hiện từ **Java 9**, không có trong Java 8; nếu dự án target Java 8, thay bằng `Arrays.asList("a", "b", "c")`. Điều này minh họa cần phân biệt **phiên bản API tạo input** với **hợp đồng joining**.

## 16. Checklist trước khi sử dụng

- [ ] Đầu vào là array/Iterable `CharSequence` hay Stream cần xử lý?
- [ ] Đã chọn `String.join`, `StringJoiner` hoặc `Collectors.joining` phù hợp?
- [ ] `delimiter` được xác định rõ, có thể là chuỗi nhiều ký tự hoặc chuỗi rỗng?
- [ ] Đã quyết định với collection rỗng và phần tử `""`?
- [ ] Đã quyết định riêng cách xử lý phần tử null: giữ literal `"null"`, bỏ, thay placeholder hay từ chối?
- [ ] Đã bảo đảm delimiter và chính container elements không null?
- [ ] Với non-String elements, đã format/map sang String theo domain?
- [ ] Nếu order có ý nghĩa, source có encounter order/iterator order phù hợp?
- [ ] Với `HashSet`, đã sort hoặc dùng collection có hợp đồng order nếu cần?
- [ ] Không dùng `parallel().forEach` để mutate chung một `StringBuilder`?
- [ ] Khi dùng `StringJoiner.setEmptyValue`, đã phân biệt trạng thái chưa add và phần tử rỗng?
- [ ] Nếu cần prefix/suffix, dùng `StringJoiner`/`Collectors.joining` thay tự cắt delimiter?
- [ ] Dữ liệu có thể chứa delimiter, quote hoặc newline? Nếu có, dùng serializer/escaping đúng định dạng?
- [ ] Không dùng join đơn thuần để sinh SQL, URL, JSON hoặc command từ dữ liệu chưa xác thực?
- [ ] Nếu cần round-trip, đã thiết kế encoding/parser, không mặc định `split` là inverse?
- [ ] Nếu dùng `split`, nhớ regex syntax, `Pattern.quote` và trailing empty fields?
- [ ] Với danh sách rất lớn, đã đánh giá chi phí tạo toàn bộ String?
- [ ] Đã phân biệt Java 8 `String.join`/`Collectors.joining` với các API mới như `List.of` (Java 9+) và `Stream.toList` (Java 16+)?
- [ ] Ví dụ, stdout, dữ liệu Unicode và hành vi null đã được kiểm thử?

**Ghi nhớ:** `String.join(delimiter, elements)` nối các phần tử `CharSequence` và chỉ chèn dấu **giữa** phần tử; `StringJoiner` hỗ trợ thêm dần cùng prefix/suffix/emptyValue; `Collectors.joining` tiện cho pipeline `Stream`. Các công cụ này **không tự xác thực, escape hoặc serialize dữ liệu phức tạp**. Để tránh lỗi, phải làm rõ nguồn order, null, empty, charset/định dạng và giới hạn output.

### Tài liệu API chính thức còn được hỗ trợ

- [`String.join` — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html): overload varargs/Iterable, `NullPointerException` với delimiter/collection null và literal `"null"` cho phần tử null.
- [`StringJoiner` — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/StringJoiner.html): prefix/suffix, `add`, `merge`, `setEmptyValue` và `length`.
- [`Collectors` — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): ba dạng `joining`, stream reduction và result order.
- [`Stream` — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): `filter`, `map`, `collect`, ordered/parallel processing.
- [`Pattern` — Oracle Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/regex/Pattern.html): `quote` để coi delimiter là regex literal.
