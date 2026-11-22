# Collectors.joining(): ghép chuỗi với dấu phân cách trong Java Stream

## 1. Mục tiêu của bài học

Khi một Stream chứa nhiều chuỗi, ta thường muốn thu tất cả phần tử thành **một chuỗi kết quả**: danh sách tên cách nhau bởi dấu phẩy, đường dẫn nối bằng dấu gạch chéo, hoặc nội dung hiển thị nằm trong dấu ngoặc vuông. Java cung cấp collector `java.util.stream.Collectors.joining(...)` cho nhu cầu này.

Ví dụ:

```text
Stream:  "Lan"  "Minh"  "An"
                    |
         joining(", ")
                    v
String:  "Lan, Minh, An"
```

Điểm cần nắm:

- `joining()` nối các phần tử liên tiếp, không chèn dấu phân cách.
- `joining(delimiter)` chèn delimiter **giữa** các phần tử, không tự thêm ở đầu/cuối.
- `joining(delimiter, prefix, suffix)` thêm phần mở đầu và kết thúc quanh chuỗi được ghép.
- `joining` là **collector** dùng ở terminal operation `collect(...)`; nó không phải một phép biến đổi `map` và không thay đổi nguồn.
- Phần tử đưa vào `joining` phải có kiểu tương thích `CharSequence`, ví dụ `String`. Với Stream số hoặc object nghiệp vụ, cần chuyển phần tử thành chuỗi trước.
- Trình tự kết quả phụ thuộc **encounter order** của stream; nếu nghiệp vụ yêu cầu thứ tự xác định, cần tạo một thứ tự rõ ràng trước khi nối.

Bài thuộc phần **thu thập kết quả** của Java functional programming: thay vì tự mở biến chuỗi rồi cộng trong vòng lặp, ta biểu diễn phép nối bằng collector có hợp đồng rõ ràng.

## 2. Ba overload chính và ý nghĩa

Các chữ ký mang tính khái quát của API:

```java
Collectors.joining()
Collectors.joining(CharSequence delimiter)
Collectors.joining(
        CharSequence delimiter,
        CharSequence prefix,
        CharSequence suffix)
```

Đây là **mô tả lời gọi API**, không phải các phương thức tự định nghĩa trong một chương trình Java. Cả ba tạo một collector nhận các phần tử `CharSequence` và kết thúc bằng một giá trị `String`.

Với dữ liệu `["A", "B", "C"]`:

| Collector | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `joining()` | `"ABC"` | Nối trực tiếp |
| `joining(",")` | `"A,B,C"` | Dấu phẩy nằm giữa phần tử |
| `joining(", ")` | `"A, B, C"` | Dấu phẩy và khoảng trắng |
| `joining(" / ")` | `"A / B / C"` | Dấu phân cách tùy chọn |
| `joining(", ", "[", "]")` | `"[A, B, C]"` | Thêm prefix và suffix |
| `joining(" - ", "<", ">")` | `"<A - B - C>"` | Format bao quanh tùy ý |

Delimiter không được thêm vào cuối chuỗi. Ví dụ có ba phần tử sẽ có đúng hai lần chèn `", "`; có một phần tử sẽ không có delimiter nào.

Khác với `Stream<String>.toList()`, kết quả sau `collect(joining(...))` là **một `String`**, không phải list chứa từng phần tử. String kết quả là immutable theo hợp đồng của Java.

## 3. Ví dụ độc lập Java 17+: tất cả overload, một phần tử và stream rỗng

Tạo tệp `JoiningBasicsDemo.java`:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class JoiningBasicsDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh", "An");

        System.out.println("plain=" +
                names.stream().collect(Collectors.joining()));

        System.out.println("comma=" +
                names.stream().collect(Collectors.joining(", ")));

        System.out.println("bracket=" +
                names.stream()
                        .collect(Collectors.joining(" | ", "[", "]")));

        System.out.println("one=" +
                Stream.of("Lan")
                        .collect(Collectors.joining(", ", "[", "]")));

        System.out.println("empty=" +
                Stream.<String>empty()
                        .collect(Collectors.joining(", ")));

        System.out.println("empty framed=" +
                Stream.<String>empty()
                        .collect(Collectors.joining(", ", "[", "]")));
    }
}
```

Biên dịch/chạy trên JDK 17+:

```bash
javac JoiningBasicsDemo.java
java JoiningBasicsDemo
```

Kết quả chuẩn:

```text
plain=LanMinhAn
comma=Lan, Minh, An
bracket=[Lan | Minh | An]
one=[Lan]
empty=
empty framed=[]
```

Giải thích:

1. `names.stream()` tạo một Stream có encounter order giống thứ tự trong `List`.
2. Mỗi lời gọi `collect(Collectors.joining(...))` thu các phần tử vào một chuỗi. Mỗi lần ở đây đều tạo **stream mới** từ `names`, không sử dụng lại stream đã tiêu thụ.
3. `joining(", ")` không tự đặt dấu phẩy ở đầu hoặc cuối.
4. Với **một phần tử**, `joining(", ", "[", "]")` vẫn trả `"[Lan]"`; delimiter không xuất hiện vì không có cặp phần tử cần phân cách.
5. Với **stream rỗng**, `joining(", ")` trả chuỗi rỗng `""`. Khi có prefix/suffix, chuỗi trả về chỉ chứa prefix và suffix, ở đây là `"[]"`.
6. Phương thức `Stream.<String>empty()` dùng type witness `<String>` để thể hiện rõ kiểu phần tử; trong nhiều ngữ cảnh compiler có thể tự suy luận kiểu.

**Điểm hay bị bỏ sót:** `joining(",", "[", "]")` trên stream rỗng **không** trả chuỗi rỗng; nó trả `"[]"`, rất thuận tiện khi muốn hiển thị khung rõ ràng.

## 4. `joining` là terminal collection, không phải intermediate operation

Các operation của Stream thường chia thành:

- **Intermediate:** `map`, `filter`, `distinct`, `sorted`, ... tạo ra pipeline mới và thường được đánh giá lười.
- **Terminal:** `collect`, `count`, `toList`, ... kích hoạt xử lý pipeline để tạo kết quả hoặc side effect theo hợp đồng.

Do đó:

```java
String joined = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .collect(Collectors.joining(", "));
```

Đây là đoạn mã trong phương thức, giả định `names` là `List<String>` và đã import `Collectors`. Các bước là:

```text
Nguồn List<String>
    └─ stream()             Stream<String>
       └─ filter(...)       Stream<String>
          └─ map(...)       Stream<String>
             └─ collect(joining(", ")) -> String
```

Collector thực hiện nối **sau khi** các phần tử đã qua các thao tác lọc và biến đổi được phát tới collector. Nếu cần hiển thị đối tượng theo một định dạng cụ thể, việc chuyển thành chuỗi nên được thực hiện trước collector.

Lưu ý: một đối tượng `Stream` **chỉ dùng cho một pipeline tiêu thụ**; không thể lấy cùng `Stream` để gọi `collect(joining())` hai lần. Với collection nguồn, gọi `names.stream()` mỗi lần để tạo stream mới.

## 5. Dữ liệu không phải String: chuyển thành CharSequence trước khi nối

`Collectors.joining(...)` nhận phần tử kiểu `CharSequence` (thường là `String`). Vì vậy không thể trực tiếp nối `Stream<Integer>` hoặc `Stream<Product>` mà không chuyển đổi theo ý định hiển thị.

Sai kiểu:

```java
// Phản ví dụ cố ý KHÔNG biên dịch nếu numbers là Stream<Integer>:
String text = numbers.collect(Collectors.joining(", "));
```

Để sửa, thêm `map` cho ra String:

```java
String text = numbers
        .map(n -> Integer.toString(n))
        .collect(Collectors.joining(", "));
```

Hai đoạn trên là **ví dụ trong ngữ cảnh biến `numbers` có kiểu `Stream<Integer>`**, không phải chương trình độc lập. Đối với primitive `IntStream`, phương thức `mapToObj(...)` chuyển thành một object stream:

```java
String numbersText = java.util.stream.IntStream.of(3, 1, 4)
        .mapToObj(Integer::toString)
        .collect(Collectors.joining(" - "));
```

Kết quả `"3 - 1 - 4"`. Đây là đoạn mã nằm trong phương thức đã import `Collectors`. `IntStream.map(...)` chỉ trả `IntStream`, không đổi số thành String; cần `mapToObj(...)` khi muốn dùng collector ghép chuỗi.

### Chương trình đầy đủ: ghép dữ liệu sau lọc, sắp xếp và biến đổi

Lưu `JoiningPipelineDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class JoiningPipelineDemo {
    record Employee(String name, String team, boolean active) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("Lan", "Dev", true),
                new Employee("Minh", "Ops", false),
                new Employee("An", "Dev", true),
                new Employee("Lan", "Ops", true),
                new Employee("Hoa", "Dev", true)
        );

        String activeNames = employees.stream()
                .filter(Employee::active)
                .map(Employee::name)
                .distinct()
                .sorted()
                .collect(Collectors.joining(" | "));

        Map<String, String> namesByTeam = employees.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.joining(" / ")
                        )
                ));

        System.out.println("active=" + activeNames);
        System.out.println("Dev=" + namesByTeam.get("Dev"));
        System.out.println("Ops=" + namesByTeam.get("Ops"));
    }
}
```

Chạy:

```bash
javac JoiningPipelineDemo.java
java JoiningPipelineDemo
```

Output:

```text
active=An | Hoa | Lan
Dev=Lan / An / Hoa
Ops=Lan
```

Phân tích:

- `filter(Employee::active)` chỉ giữ nhân viên đang hoạt động.
- `map(Employee::name)` chuyển `Stream<Employee>` thành `Stream<String>`, là kiểu hợp lệ cho `joining`.
- `distinct()` loại các tên trùng nhau theo `equals`; `sorted()` đảm bảo thứ tự alphabet của String trước khi ghép.
- `groupingBy(...)` chia các bản ghi theo team; `Collectors.mapping(Employee::name, joining(" / "))` là **downstream collector** biến từng Employee thành String rồi ghép tên trong nhóm.
- `TreeMap::new` quy định Map có thứ tự theo khóa nếu cần duyệt theo team, nhưng ví dụ in riêng hai khóa để không phụ thuộc cách render Map. Với nguồn `List` có thứ tự và collector ở đây, các tên trong mỗi nhóm giữ thứ tự encounter order.
- Nếu chỉ cần một chuỗi của toàn bộ nhân viên, không cần `groupingBy`; collector `joining` là đủ.

**Tư duy quan trọng:** kiểu dữ liệu chảy qua mỗi stage quyết định bạn đặt `map` ở đâu. Trước `map(Employee::name)` là `Employee`, sau đó là `String`; collector ghép nhận chuỗi chứ không tự hiểu phải lấy thuộc tính nào từ Employee.

## 6. Dấu phân cách, prefix và suffix phải nằm ở đúng vị trí

Với mã:

```java
String result = Stream.of("red", "green", "blue")
        .collect(Collectors.joining(", ", "[", "]"));
```

kết quả là:

```text
[red, green, blue]
```

Vị trí ký tự:

```text
prefix       delimiter   delimiter      suffix
  [    red      ,      green     ,      blue    ]
```

Không có delimiter ở đầu, cũng không có delimiter ngay trước suffix. Vì vậy, không cần xử lý thủ công “nếu phần tử cuối thì bỏ dấu phẩy”.

Mỗi tham số đều là `CharSequence`:

- `delimiter`: dấu nối giữa **các phần tử**; có thể là dấu phẩy, khoảng trắng, dấu xuống dòng hoặc một chuỗi nhiều ký tự.
- `prefix`: chuỗi đứng trước nội dung được nối.
- `suffix`: chuỗi đứng sau nội dung được nối.

Ví dụ:

```java
String lines = Stream.of("first", "second")
        .collect(Collectors.joining("\n", "START\n", "\nEND"));
```

Kết quả thực tế chứa dấu xuống dòng:

```text
START
first
second
END
```

Đây là đoạn minh họa đặt trong phương thức đã import `Stream` và `Collectors`. Dấu `\n` là ký tự newline; khi xuất ra console, hệ thống có thể hiển thị nó thành những dòng tách biệt. Nếu cần separator theo quy tắc hệ điều hành, cân nhắc `System.lineSeparator()`; với file format cần newline cố định, nên sử dụng đúng ký tự mà định dạng yêu cầu.

Lưu ý: `joining` **không tự escape** delimiter nằm bên trong dữ liệu. Nếu tên là `"a,b"` và delimiter là dấu phẩy, nó vẫn giữ nguyên dấu phẩy trong tên. Muốn xuất CSV, SQL, JSON hoặc định dạng máy đọc, cần áp dụng đúng quy tắc **escape/quote** của định dạng, không coi `joining(",")` là bộ tạo CSV/JSON đầy đủ.

## 7. Stream rỗng: không có phần tử nhưng vẫn có kết quả

Ba trường hợp khác nhau:

| Nguồn | Collector | Kết quả |
| --- | --- | --- |
| Rỗng | `joining()` | `""` |
| Rỗng | `joining(";")` | `""` |
| Rỗng | `joining(";", "(", ")")` | `"()"` |
| Chứa một chuỗi rỗng `""` | `joining(";")` | `""` |
| Chứa hai chuỗi rỗng `"", ""` | `joining(";")` | `";"` |
| Chứa một phần tử `"A"` | `joining(";")` | `"A"` |

Đặc biệt, **chuỗi kết quả rỗng không nhất thiết chứng minh rằng stream không có phần tử**. Stream với đúng một phần tử là chuỗi rỗng cũng tạo kết quả `""` khi không có prefix/suffix. Nếu phải phân biệt các trạng thái này, cần giữ thông tin số phần tử ở một cấu trúc khác thay vì chỉ nhìn String đã ghép.

Trong API thực tế, có thể xử lý trường hợp không có bản ghi theo hợp đồng hiển thị, chẳng hạn trả `"Không có dữ liệu"` khi input rỗng. Nhưng `joining` tự nó không thêm nhãn dự phòng đó; bạn cần thiết kế bước xử lý kết quả sau collect hoặc lựa chọn một format khác.

## 8. Giá trị null: không được giả định tự bỏ qua

Với một stream chứa null, `joining` **không tự động bỏ qua phần tử đó**. Với implementation theo hợp đồng của `StringJoiner`, giá trị null có thể được biểu diễn như chữ `"null"` khi ghép. Nếu nghiệp vụ không muốn hiện chữ này, hãy **quy định chính sách null** rõ ràng: loại bỏ, thay bằng nhãn, hoặc từ chối dữ liệu.

Các factory như `List.of(...)` không nhận phần tử null. Để làm ví dụ về dữ liệu có thể null, dùng một list cho phép null.

Tạo tệp `JoiningNullDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class JoiningNullDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>();
        values.add("A");
        values.add(null);
        values.add("B");

        String raw = values.stream()
                .collect(Collectors.joining(", "));

        String skipNull = values.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.joining(", "));

        String placeholder = values.stream()
                .map(value -> value == null ? "(missing)" : value)
                .collect(Collectors.joining(" | "));

        System.out.println("raw=" + raw);
        System.out.println("skip=" + skipNull);
        System.out.println("placeholder=" + placeholder);
    }
}
```

Chạy:

```bash
javac JoiningNullDemo.java
java JoiningNullDemo
```

Output:

```text
raw=A, null, B
skip=A, B
placeholder=A | (missing) | B
```

Các cách xử lý ở trên mang ý nghĩa nghiệp vụ khác nhau:

1. **Giữ nguyên:** chữ `null` được đưa vào chuỗi nối. Với nhiều hệ thống, điều này gây nhầm lẫn vì không phân biệt được dữ liệu null với một chuỗi thật có nội dung `"null"`.
2. **Lọc bỏ:** `filter(Objects::nonNull)` loại hoàn toàn phần tử null. Hợp lý khi null chỉ là “không có tên”.
3. **Thay thế:** `map(...)` đổi null thành placeholder xác định. Hợp lý khi cần giữ số vị trí đầu vào hoặc tạo thông điệp rõ.
4. **Từ chối:** nếu null là dữ liệu lỗi, hãy validate và ném exception phù hợp trước khi xuất kết quả, thay vì âm thầm lọc.

Cần phân biệt **phần tử null** với **tham số delimiter/prefix/suffix null**. Các overload của `Collectors.joining` yêu cầu tham số cấu hình hợp lệ và có thể ném `NullPointerException` khi truyền null; đừng dùng null làm delimiter để mong Java hiểu là chuỗi trống. Nếu không cần dấu phân cách, dùng `joining()` hoặc `joining("")`.

## 9. Thứ tự phần tử ảnh hưởng trực tiếp đến chuỗi kết quả

`Collectors.joining(", ")` không tự sắp xếp phần tử. Nếu nguồn là một `List` có encounter order, chuỗi theo thứ tự đó:

```java
String first = List.of("Z", "A", "M").stream()
        .collect(Collectors.joining(", "));

String second = List.of("Z", "A", "M").stream()
        .sorted()
        .collect(Collectors.joining(", "));
```

Đây là hai đoạn khai báo trong phương thức có import `List` và `Collectors`. Kết quả:

```text
first  = Z, A, M
second = A, M, Z
```

Với nguồn **không có encounter order** hoặc khi chủ động gọi `unordered()`, không nên dựa vào một thứ tự ghép cố định. Đặc biệt, nguồn như `HashSet` không cung cấp thứ tự duyệt ổn định theo nghiệp vụ. Nếu yêu cầu là chuỗi hiển thị có thứ tự xác định, hãy gọi `sorted()` với comparator phù hợp trước khi collect.

Với **ordered stream**, collector `joining` bảo toàn thứ tự encounter của các phần tử trong kết quả, kể cả khi pipeline có thể được thực thi song song. Tuy nhiên, đừng suy từ chuỗi cuối cùng rằng các side effect như `peek(System.out::println)` chắc chắn xảy ra theo thứ tự đó trong parallel stream. Muốn debug, kiểm tra kết quả đầu ra, không dùng thứ tự log làm nguồn chân lý.

Một điểm khác: `distinct()` hoạt động theo quy tắc equality; `sorted()` có thể làm thay đổi thứ tự trước khi ghép; `filter()` có thể làm số lượng dấu phân cách giảm vì loại phần tử. Khi thay đổi vị trí các stage, cần biết **dữ liệu cuối cùng** nào sẽ đến collector.

## 10. Kết hợp `joining` với các collector khác

### 10.1. `mapping(..., joining(...))` khi grouping

Khi gom theo khóa:

```java
Map<String, String> byTeam = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::team,
                Collectors.mapping(
                        Employee::name,
                        Collectors.joining(", ")
                )
        ));
```

Đoạn minh họa giả định có kiểu `Employee` chứa `team()` và `name()`, một collection `employees`, cùng import `Map`, `Collectors`. Các chuỗi tên được nối **trong từng nhóm**. Đây là một kiểu downstream collector: `groupingBy` phân nhóm và `mapping` chuyển loại phần tử trước khi `joining` tạo kết quả mỗi nhóm.

Lưu ý thứ tự các **khóa** của Map do loại Map và nhà cung cấp Map quyết định; bản thân `groupingBy` không hứa trả Map có key order đặc biệt. Nếu muốn key sort theo thứ tự, chọn supplier như `TreeMap::new`; nếu cần giữ encounter order của tên trong một nhóm, kiểm tra thêm nguồn và các thao tác upstream.

### 10.2. `filtering(..., joining(...))` làm downstream

Từ Java 9, `Collectors.filtering(predicate, downstream)` có thể lọc các phần tử **bên trong collector**, ví dụ khi cần giữ nhóm ngay cả khi không có phần tử thỏa lọc:

```java
Collectors.groupingBy(
        Employee::team,
        Collectors.filtering(
                Employee::active,
                Collectors.mapping(
                        Employee::name,
                        Collectors.joining(", ")
                )
        )
)
```

Đây là **biểu thức collector minh họa**, trong ngữ cảnh lớp `Employee` phù hợp. Nó khác với `stream.filter(...).collect(groupingBy(...))`: lọc trước `groupingBy` có thể khiến một khóa không được tạo nếu không còn phần tử nào của khóa; dùng downstream filtering có thể giữ nhóm đã được thấy trước filtering, nhưng giá trị ghép của nhóm đó có thể là chuỗi rỗng.

### 10.3. Thêm prefix/suffix cho từng nhóm

Khi muốn một giá trị như `"[An, Hoa]"` cho mỗi nhóm, đưa prefix/suffix vào downstream:

```java
Collectors.mapping(
        Employee::name,
        Collectors.joining(", ", "[", "]")
)
```

Ở nhóm không có tên để thu, giá trị thu được là `"[]"` thay vì `""`. Việc chọn format nào là quyết định của API hiển thị.

## 11. So với `String.join` và `StringJoiner`

Cùng mục tiêu ghép chuỗi, Java có ba API thường gặp:

| API | Khi nên dùng | Kết quả |
| --- | --- | --- |
| `Collectors.joining(delimiter)` | Đang có `Stream<? extends CharSequence>` hoặc pipeline cần filter/map/sort trước khi nối | `String` qua `collect` |
| `String.join(delimiter, elements...)` hoặc `String.join(delimiter, Iterable)` | Đã có mảng/collection `CharSequence`, không cần xử lý Stream | `String` trực tiếp |
| `StringJoiner` | Muốn thêm phần tử theo các bước trong code imperative, có delimiter/prefix/suffix | Đối tượng builder, lấy chuỗi qua `toString()` |

Ví dụ với list tên sẵn có:

```java
String result = String.join(", ", List.of("Lan", "An"));
```

Kết quả là `"Lan, An"`. Cần import `List`; không cần tạo Stream để làm việc này. `String.join` không có overload riêng cho prefix và suffix như collector ba tham số.

Dùng `StringJoiner`:

```java
StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.add("Lan");
joiner.add("An");
String output = joiner.toString();
```

Kết quả `"[Lan, An]"`. Đoạn minh họa này cần import `java.util.StringJoiner`.

`joining` bên trong cũng sử dụng cơ chế tích lũy chuỗi phù hợp, nhưng khi dùng Stream bạn nên tập trung vào hợp đồng Collector thay vì phụ thuộc vào implementation. Trong pipeline, `joining` giúp tránh tự quản lý biến mutable và phân cách dấu phẩy bằng index.

## 12. Không thay bằng nối chuỗi thủ công thiếu cẩn thận

Một cách làm dễ sai:

```java
String text = names.stream()
        .reduce("", (acc, item) -> acc + ", " + item);
```

Đây là đoạn code trong phương thức giả sử `names` là collection String. Với `["Lan","An"]`, kết quả là `", Lan, An"`: có dấu phân cách **thừa ở đầu**. Muốn tự sửa bằng điều kiện accumulator rỗng sẽ khiến code phức tạp hơn và dễ nhầm khi phần tử thực sự là chuỗi rỗng.

Hơn nữa, `String` immutable. Nhiều lần cộng chuỗi trong phép reduce có thể tạo nhiều đối tượng trung gian và mang chi phí không cần thiết. `Collectors.joining(", ")` biểu đạt đúng mục tiêu, cung cấp cách tích lũy thích hợp và có cơ chế kết hợp partial results khi Stream framework cần.

Trong một số bài toán, có thể sử dụng `StringBuilder` thủ công; tuy nhiên nó cần quản lý dấu phân cách và trạng thái. Với pipeline vốn đang là Stream, `joining` là lựa chọn thường rõ ràng nhất.

**Không dùng một `StringBuilder` hoặc `StringJoiner` dùng chung rồi thay đổi chúng từ `parallelStream().forEach(...)`.** Điều này gây phụ thuộc vào thứ tự, có rủi ro race nếu object không thread-safe, và làm mất lợi ích của Collector đúng hợp đồng.

## 13. Hiệu năng, parallel stream và dữ liệu lớn

`joining` thường dễ bảo trì và phù hợp cho dữ liệu đầu vào vừa phải. Nhưng nó tạo **một chuỗi kết quả cuối cùng**, nên cần đủ bộ nhớ cho nội dung ghép. Với hàng triệu bản ghi hay chuỗi cực dài, hãy cân nhắc **streaming output** ra file/writer theo định dạng cần thiết thay vì giữ toàn bộ trong RAM; khi đó cách viết và xử lý dấu phân cách cần được thiết kế riêng.

Một số điểm hiệu năng:

1. `joining` tránh việc tự cộng `String` liên tiếp trong một vòng reduce thiếu tối ưu.
2. `map`, `filter`, `sorted`, `distinct` đặt trước collector có thể làm thay đổi lượng dữ liệu và chi phí, đôi khi sorting tốn đáng kể.
3. Với parallel stream, collector/framework có thể tạo các phần kết quả rồi kết hợp; điều này không có nghĩa nối chuỗi tự động nhanh hơn sequential. Chi phí phân vùng, nối/ghép và bộ nhớ có thể lớn.
4. Với stream có encounter order, kết quả chuỗi cần bảo toàn thứ tự đó. Nếu nguồn không ordered, không được dựa vào thứ tự ghép cố định.
5. Đầu vào, delimiter và phần tử dài đều đóng góp vào độ dài String. Việc tạo một chuỗi rất lớn có giới hạn bộ nhớ/khả năng của JVM.
6. Nếu chỉ cần nối một list nhỏ đã có, `String.join` có thể ngắn gọn hơn việc dựng Stream.

Ưu tiên **đúng định dạng và đúng thứ tự** trước, sau đó mới đo hiệu năng trên dữ liệu đại diện.

## 14. Lỗi thường gặp và cách tránh

1. **Nhầm `joining` là thao tác trên String có sẵn.** Nó là một Collector: cần `stream.collect(Collectors.joining(...))`.
2. **Gọi `joining(", ")` trực tiếp trên `Stream<Integer>`.** Sai kiểu; chuyển sang String bằng `map(n -> Integer.toString(n))` hoặc `mapToObj(...)` cho primitive stream.
3. **Tự chèn dấu phân cách trước/sau bằng reduce.** Dễ có dấu thừa; dùng `joining(delimiter)` để chỉ chèn giữa các phần tử.
4. **Quên rằng stream rỗng cho chuỗi rỗng.** Nếu có prefix/suffix thì kết quả là prefix + suffix, ví dụ `"[]"`.
5. **Tưởng chuỗi kết quả rỗng nghĩa là không có phần tử.** Một phần tử `""` cũng có thể tạo chuỗi rỗng.
6. **Mặc định null sẽ bị bỏ qua.** Cần chọn rõ `filter(Objects::nonNull)`, `map` placeholder hoặc validate.
7. **Sắp xếp không rõ ràng.** Collector không tự `sorted()`; với nguồn unordered, kết quả ghép có thể thay thứ tự.
8. **Dùng `joining(",")` để tạo CSV/JSON hoàn chỉnh.** Không có cơ chế escape hoặc quote tự động; phải dùng quy tắc formatter hoặc thư viện đúng chuẩn.
9. **Sử dụng lại cùng Stream sau collect.** Một Stream đã tiêu thụ không dùng lại; tạo Stream mới từ nguồn.
10. **Nhầm `joining` với `toList`.** `joining` tạo String, mất ranh giới phần tử ở mức cấu trúc dữ liệu.
11. **Tin rằng nhóm trong `groupingBy` luôn có thứ tự khóa cố định.** Lựa chọn Map supplier phù hợp nếu cần in theo khóa.
12. **Gắn side effect vào mapper chỉ để đếm phần tử.** Stream có thể tối ưu hoặc chạy song song; hãy thiết kế thống kê riêng thay vì dựa vào số lần log.
13. **Cho rằng parallel nhanh hơn.** Ghép chuỗi là công việc phải tổ chức lại dữ liệu; benchmark khi thực sự cần.
14. **Trộn nhãn định dạng và dữ liệu đầu vào.** Prefix, suffix, delimiter nên là quyết định format rõ ràng; tên phần tử có thể chứa delimiter và cần escaping trong định dạng máy đọc.

## 15. Bài tự kiểm tra

Cho đoạn code trong một phương thức Java 17, với import `List`, `Stream` và `Collectors`:

```java
List<String> words = List.of("pear", "apple", "kiwi");

String a = words.stream()
        .collect(Collectors.joining("|"));

String b = words.stream()
        .sorted()
        .collect(Collectors.joining(", ", "<", ">"));

String c = words.stream()
        .filter(w -> w.length() > 4)
        .collect(Collectors.joining("-"));

String d = Stream.<String>empty()
        .collect(Collectors.joining(";", "[", "]"));

String e = words.stream()
        .map(String::length)
        .map(String::valueOf)
        .collect(Collectors.joining(","));
```

Câu hỏi:

1. Giá trị của `a` và `b` là gì?
2. Tại sao `c` không có dấu phân cách khi chỉ một phần tử thỏa?
3. Kết quả `d` có phải String rỗng không?
4. `e` ghép kiểu dữ liệu gì ở stage cuối, và có kết quả nào?
5. Nếu bỏ `map(String::valueOf)` khỏi pipeline tạo `e`, điều gì xảy ra?

**Đáp án:**

1. `a = "pear|apple|kiwi"`. Sau `sorted()` theo natural order, `b = "<apple, kiwi, pear>"`.
2. Chỉ `"apple"` có độ dài lớn hơn 4, nên `c = "apple"`. Không có cặp phần tử để chèn `"-"`.
3. `d = "[]"`, vì prefix và suffix vẫn được giữ với stream rỗng.
4. `map(String::length)` cho `Stream<Integer>` có các giá trị 4, 5, 4; `map(String::valueOf)` biến thành chuỗi, nên `e = "4,5,4"`.
5. Nếu không chuyển số về chuỗi, `joining(",")` không chấp nhận `Integer` làm `CharSequence`; chương trình không biên dịch.

## 16. Quy tắc kết luận

Khi muốn **thu thập các chuỗi thành một giá trị có dấu phân cách**, cách viết thông dụng là:

```java
String text = source.stream()
        .filter(/* điều kiện phù hợp */)
        .map(/* chuyển mỗi phần tử thành String */)
        .collect(Collectors.joining(", ", "[", "]"));
```

Đây là **sơ đồ cú pháp minh họa**, các comment trong `filter`/`map` cần được thay bằng lambda hoặc method reference hợp lệ trong code thật.

Hãy kiểm tra lần lượt:

- **Kiểu đầu vào:** trước `joining` phải là phần tử tương thích `CharSequence`.
- **Phần tử thực sự được nối:** kết quả của `map/filter/distinct/sorted`, không phải lúc nào cũng là phần tử gốc.
- **Thứ tự:** collector theo encounter order; muốn ổn định hãy xác định nguồn hoặc `sorted()`.
- **Định dạng:** delimiter chỉ ở giữa, prefix/suffix bao quanh toàn bộ, stream rỗng vẫn có thể trả prefix + suffix.
- **Null và escaping:** chọn chính sách xử lý rõ ràng theo yêu cầu đầu ra.
- **Loại kết quả:** `collect(joining(...))` trả `String`; không sửa collection đầu vào.

**Ghi nhớ:** `Collectors.joining(", ")` là cách tập trung, an toàn về dấu phân cách để ghép các phần tử chuỗi trong Stream; `Collectors.joining(", ", "[", "]")` thêm khung; `map(...)` và các stage trước đó quyết định **dữ liệu nào** được ghép. Nó là công cụ thu thập kết quả, không phải bộ định dạng mọi chuẩn xuất dữ liệu.

**Tài liệu tham khảo:** Java SE API `java.util.stream.Collectors.joining`, `Collectors.mapping`, `Collectors.groupingBy`, `java.util.stream.Stream.collect`, `java.lang.String.join` và `java.util.StringJoiner`.