# Local record trong phương thức và giới hạn truy cập biến bên ngoài

## 1. Local record là gì?

Java cho phép khai báo một record ngay bên trong một block, thường là trong thân phương thức hoặc constructor. Kiểu này được gọi là *local record*. Nó hữu ích khi một thuật toán cần một kiểu dữ liệu nhỏ để gom nhóm các giá trị trung gian, nhưng kiểu đó chỉ có ý nghĩa trong phạm vi xử lý hiện tại.

~~~java
import java.util.List;

class CsvParser {
    void parse() {
        record Row(String name, int age) {}

        List<Row> rows = List.of(
            new Row("An", 20),
            new Row("Binh", 22)
        );

        rows.forEach(System.out::println);
    }
}
~~~

`Row` chỉ được khai báo bên trong phương thức `parse()`. Code bên ngoài phương thức không thể dùng tên `Row` để khai báo biến hoặc tham số. Mỗi record instance vẫn là một object Java bình thường, có constructor, accessor và các phương thức giá trị của record.

Local record là tính năng ổn định của Java, có thể sử dụng từ Java 16. Nó đặc biệt hữu ích khi cần một kiểu dữ liệu có tên, có cấu trúc và có equality theo component cho một bước xử lý cục bộ.

Mục tiêu bài học:

- Khai báo và sử dụng local record trong method, constructor hoặc block.
- Hiểu phạm vi tên của local record.
- Hiểu vì sao local record ngầm định là static.
- Phân biệt việc truyền dữ liệu vào component với việc capture biến bên ngoài.
- Nhận biết local record không có enclosing instance và không truy cập trực tiếp instance member của outer object.
- So sánh local record với local class và lambda.
- Chọn giữa local record, member record và top-level record.

## 2. Cú pháp và phạm vi của local record

Cú pháp khai báo giống record thông thường:

~~~java
record LocalName(Type component1, Type component2) {
    // Constructor và phương thức nếu cần
}
~~~

Điểm khác biệt là vị trí khai báo. Local record phải nằm trong một block, chẳng hạn thân method hoặc constructor:

~~~java
class ReportBuilder {
    void build() {
        record Summary(String title, int rowCount) {
            boolean isEmpty() {
                return rowCount == 0;
            }
        }

        Summary summary = new Summary("Monthly report", 12);
        System.out.println(summary.isEmpty());
    }
}
~~~

Tên `Summary` chỉ có phạm vi trong block nơi nó được khai báo và các phần còn lại của block đó. Không thể dùng tên local record ở một method khác:

~~~java
class ReportBuilder {
    void build() {
        record Summary(String title, int rowCount) {}
        Summary summary = new Summary("Monthly report", 12);
    }

    void export() {
        // Không hợp lệ: Summary không nằm trong scope của export().
        // Summary summary = new Summary("Report", 12);
    }
}
~~~

Local record cũng có thể được khai báo trong constructor:

~~~java
class ImportJob {
    ImportJob(String source, int lineCount) {
        record InputInfo(String source, int lineCount) {}

        InputInfo info = new InputInfo(source, lineCount);
        System.out.println(info);
    }
}
~~~

Có thể đặt local record trong một block lồng, khi chỉ cần kiểu đó trong một đoạn nhỏ hơn:

~~~java
import java.util.List;

class Analyzer {
    void analyze(List<String> values) {
        if (!values.isEmpty()) {
            record FirstValue(String value, int length) {}

            String first = values.get(0);
            FirstValue result = new FirstValue(first, first.length());
            System.out.println(result);
        }
    }
}
~~~

Khi ra khỏi block khai báo, tên local record không còn khả dụng. Điều này giúp giới hạn phạm vi kiểu và tránh tạo thêm kiểu top-level hoặc member type không cần thiết.

## 3. Local record ngầm định là static

Local record ngầm định là static. Nó không được gắn với một instance của class bao ngoài và không có tham chiếu enclosing instance.

~~~java
class ReportService {
    private final String region = "APAC";

    void create() {
        record Report(String title, String region) {}

        // Method bên ngoài có thể đọc field của object hiện tại.
        Report report = new Report("Sales", this.region);
        System.out.println(report);
    }
}
~~~

Trong ví dụ, method `create()` đọc `this.region` rồi truyền giá trị đó vào constructor của `Report`. Sau khi được tạo, `Report` chỉ biết component `title` và `region` của chính nó.

Không thể truy cập trực tiếp `ReportService.this` hoặc field instance `region` từ bên trong local record:

~~~java
class ReportService {
    private final String region = "APAC";

    void create() {
        record Report(String title) {
            String fullTitle() {
                // Không hợp lệ: local record không có enclosing instance.
                // return ReportService.this.region + " - " + title;
                return title;
            }
        }
    }
}
~~~

`Report` chỉ biết những gì được khai báo trong component, tham số phương thức hoặc những thành viên static có thể truy cập. Đây là hệ quả của tính static ngầm định.

## 4. Local record không capture local variable hoặc tham số của method

Đây là điểm quan trọng nhất cần nhớ. Local class thông thường và lambda có thể capture local variable final hoặc effectively final trong phạm vi cho phép. Local record thì không capture biến cục bộ của method bao quanh.

Ví dụ không hợp lệ:

~~~java
class LabelBuilder {
    void build(String prefix, String value) {
        record Label(String value) {
            String text() {
                // Không hợp lệ: prefix là biến của method bên ngoài.
                // return prefix + value;
                return value;
            }
        }
    }
}
~~~

Dù `prefix` không bị thay đổi sau khi khởi tạo, local record vẫn không capture nó. Tính effectively final không làm thay đổi quy tắc này.

Có hai cách phổ biến để cung cấp dữ liệu cần thiết.

### Cách 1: Truyền biến vào component

Nếu giá trị cần trở thành một phần của dữ liệu record, hãy khai báo component tương ứng:

~~~java
class LabelBuilder {
    void build(String prefix, String value) {
        record Label(String prefix, String value) {
            String text() {
                return prefix + value;
            }
        }

        Label label = new Label(prefix, value);
        System.out.println(label.text());
    }
}
~~~

`prefix` và `value` ở đây là component của `Label`. Chúng được truyền qua constructor, không phải được capture từ method.

### Cách 2: Truyền biến vào phương thức

Nếu giá trị chỉ cần dùng trong một phép tính và không cần lưu vào record, hãy truyền nó thành tham số method:

~~~java
class LabelBuilder {
    void build(String prefix, String value) {
        record Label(String value) {
            String textWith(String prefix) {
                return prefix + value;
            }
        }

        Label label = new Label(value);
        System.out.println(label.textWith(prefix));
    }
}
~~~

Cách này giữ record chỉ chứa dữ liệu riêng của nó. `prefix` chỉ được sử dụng trong lần gọi `textWith()`.

Chọn component khi giá trị thuộc về trạng thái của record; chọn tham số method khi giá trị chỉ là ngữ cảnh tạm thời cho một thao tác.

## 5. Local record không capture enclosing instance

Ngay cả khi local record được khai báo trong instance method, nó cũng không có `this` của outer object. Phương thức bên ngoài có thể đọc field instance, sau đó truyền giá trị vào record:

~~~java
import java.util.List;

class CsvImporter {
    private final String sourceName;

    CsvImporter(String sourceName) {
        this.sourceName = sourceName;
    }

    void importRows(List<String> names) {
        record ImportedRow(String source, String name) {}

        for (String name : names) {
            ImportedRow row = new ImportedRow(sourceName, name);
            System.out.println(row);
        }
    }
}
~~~

`sourceName` được đọc trong ngữ cảnh của `CsvImporter`. Local record `ImportedRow` không tự giữ tham chiếu đến object `CsvImporter`. Nó chỉ giữ một giá trị String được truyền vào component `source`.

Nếu chỉ truyền một component cần thiết như `sourceName`, record có cấu trúc rõ ràng và không phụ thuộc vòng đời của outer object. Nếu truyền cả outer object làm component, record sẽ giữ tham chiếu đó như dữ liệu tường minh; cần cân nhắc khả năng object bao ngoài mutable và vòng đời của nó.

## 6. Local record có thể khai báo phương thức và triển khai interface

Local record không chỉ chứa component. Nó có thể khai báo constructor, accessor tùy chỉnh, phương thức instance và triển khai interface như các record khác.

~~~java
interface NamedRow {
    String displayName();
}

class UserImporter {
    void importUser(String firstName, String lastName) {
        record UserRow(String firstName, String lastName)
                implements NamedRow {

            UserRow {
                firstName = firstName.strip();
                lastName = lastName.strip();
            }

            @Override
            public String displayName() {
                return firstName + " " + lastName;
            }
        }

        UserRow row = new UserRow(firstName, lastName);
        System.out.println(row.displayName());
    }
}
~~~

`UserRow` được giới hạn trong method `importUser()`, nhưng vẫn có thể triển khai interface `NamedRow` được khai báo ở phạm vi bên ngoài. Compact canonical constructor chuẩn hóa component; phương thức `displayName()` tính giá trị từ các component.

Local record cũng có thể dùng generic type parameter riêng:

~~~java
class PairProcessor {
    void process() {
        record Pair<L, R>(L left, R right) {}

        Pair<String, Integer> pair = new Pair<>("OK", 200);
        System.out.println(pair.left() + " " + pair.right());
    }
}
~~~

Các type parameter `L` và `R` thuộc chính local record. Nếu cần một kiểu tổng quát, hãy khai báo type parameter ngay trên record thay vì phụ thuộc vào biến hoặc instance bên ngoài.

## 7. So sánh local record với local class và lambda

Local record, local class và lambda đều có thể xuất hiện trong một method, nhưng phục vụ mục đích khác nhau.

| Đặc điểm | Local record | Local class | Lambda |
| --- | --- | --- | --- |
| Mục đích chính | Gom nhóm dữ liệu có cấu trúc và semantics giá trị. | Định nghĩa một kiểu cục bộ có hành vi và có thể giữ trạng thái riêng. | Cung cấp implementation ngắn cho functional interface. |
| Có tên kiểu riêng | Có | Có | Không khai báo class name tường minh. |
| Có component/accessor tự sinh | Có | Không | Không |
| Có thể capture local variable effectively final | Không | Có | Có |
| Có enclosing instance của outer class | Không | Có nếu là local inner class trong instance context | Lambda không tạo enclosing instance mới; `this` tham chiếu enclosing instance. |
| Equality theo dữ liệu | Có mặc định theo component | Không tự có; mặc định theo identity | Không nên dựa vào equality của lambda. |
| Dùng làm kiểu dữ liệu trung gian | Rất phù hợp | Có thể, nếu cần trạng thái/hành vi riêng | Không phù hợp để thay thế data carrier. |

Ví dụ local class có thể capture biến:

~~~java
class Formatter {
    void format(String prefix) {
        class LocalFormatter {
            String apply(String value) {
                return prefix + value;
            }
        }

        LocalFormatter formatter = new LocalFormatter();
        System.out.println(formatter.apply("Java"));
    }
}
~~~

Lambda cũng có thể capture biến effectively final:

~~~java
class Formatter {
    void format(String prefix) {
        java.util.function.Function<String, String> formatter =
            value -> prefix + value;

        System.out.println(formatter.apply("Java"));
    }
}
~~~

Local record không dùng cơ chế capture này. Nó phù hợp khi cần biểu diễn dữ liệu có tên, còn local class hoặc lambda có thể phù hợp hơn khi cần hành vi đóng trên biến cục bộ.

## 8. Dùng local record trong xử lý collection và stream

Local record hữu ích khi một method cần nhóm nhiều giá trị thành một phần tử có cấu trúc, ví dụ kết quả phân tích, nhóm dữ liệu hoặc thống kê trung gian.

Ví dụ gom tên và độ dài:

~~~java
import java.util.List;

class NameAnalyzer {
    void analyze(List<String> names) {
        record NameInfo(String name, int length) {}

        List<NameInfo> result = names.stream()
            .map(name -> new NameInfo(name, name.length()))
            .toList();

        result.forEach(System.out::println);
    }
}
~~~

`NameInfo` giúp mỗi phần tử có tên component rõ nghĩa thay vì dùng một cặp giá trị không có cấu trúc. `Stream.toList()` có từ Java 16 và trả về danh sách không sửa đổi.

Ví dụ nhóm dữ liệu theo khóa:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

class SalesAnalyzer {
    void summarize(List<Sale> sales) {
        record KeyTotal(String region, long total) {}

        Map<String, Long> totals = sales.stream()
            .collect(Collectors.groupingBy(
                Sale::region,
                Collectors.summingLong(Sale::amount)
            ));

        List<KeyTotal> result = totals.entrySet().stream()
            .map(entry -> new KeyTotal(entry.getKey(), entry.getValue()))
            .toList();

        result.forEach(System.out::println);
    }

    record Sale(String region, long amount) {}
}
~~~

Trong ví dụ, `KeyTotal` chỉ cần cho bước tạo báo cáo trong method `summarize()`. Nếu nhiều method hoặc nhiều class cần dùng kiểu này, nên cân nhắc chuyển nó thành member record hoặc top-level record.

## 9. Local record có thể được trả ra ngoài qua interface

Vì tên local record chỉ có scope trong method, method khác không thể khai báo kiểu trả về trực tiếp là local record đó. Nếu cần trả kết quả ra ngoài method, có thể dùng interface hoặc kiểu công khai khác làm hợp đồng.

~~~java
import java.util.List;

interface ParsedRow {
    String name();
    int age();
}

class Parser {
    List<ParsedRow> parse() {
        record Row(String name, int age) implements ParsedRow {}

        return List.of(
            new Row("An", 20),
            new Row("Binh", 22)
        );
    }
}
~~~

Caller có thể nhận kết quả qua interface:

~~~java
List<ParsedRow> rows = new Parser().parse();

for (ParsedRow row : rows) {
    System.out.println(row.name() + ": " + row.age());
}
~~~

Caller không cần biết tên local record `Row`. Nó chỉ phụ thuộc vào hợp đồng `ParsedRow`.

Nếu caller cần dùng constructor, pattern matching theo kiểu cụ thể, reflection theo một kiểu có tên ổn định hoặc lưu kiểu đó trong API công khai, hãy khai báo record ở phạm vi member hoặc top-level thay vì local.

## 10. Khi nào nên dùng local record, member record hoặc top-level record?

| Tình huống | Lựa chọn phù hợp |
| --- | --- |
| Kiểu chỉ phục vụ một method hoặc một block | Local record. |
| Nhiều method trong cùng class cần dùng kiểu đó | Member nested record. |
| Kiểu thuộc về một interface hoặc domain type cụ thể | Nested record trong interface/class/record. |
| Kiểu được nhiều package hoặc module sử dụng | Top-level record. |
| Cần capture biến cục bộ effectively final | Cân nhắc local class hoặc lambda; local record không capture. |
| Cần giữ trạng thái instance mutable riêng hoặc field bổ sung | Class thông thường có thể phù hợp hơn. |
| Cần dữ liệu trung gian có component và equality theo giá trị | Local record. |

Không nên chọn local record chỉ vì muốn giảm số file. Lợi ích chính là giới hạn scope của kiểu khi nó thực sự chỉ có ý nghĩa trong một thao tác. Khi kiểu trở thành một phần hợp đồng giữa nhiều thành phần, hãy nâng nó lên phạm vi rộng hơn.

## 11. Ví dụ hoàn chỉnh: phân tích dòng dữ liệu trong một method

Ví dụ sau dùng local record để biểu diễn dòng dữ liệu đã phân tích. Kiểu `ParsedLine` chỉ tồn tại trong method `parseLines()`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class Demo {
    private final String source;

    Demo(String source) {
        this.source = Objects.requireNonNull(source, "source");
    }

    List<String> parseLines(List<String> input) {
        record ParsedLine(String source, int lineNumber, String content) {
            ParsedLine {
                source = Objects.requireNonNull(source, "source");
                content = Objects.requireNonNull(content, "content").strip();
                if (lineNumber < 1) {
                    throw new IllegalArgumentException("lineNumber must be positive");
                }
            }

            String display() {
                return source + ":" + lineNumber + ": " + content;
            }
        }

        List<ParsedLine> parsed = new ArrayList<>();

        for (int i = 0; i < input.size(); i++) {
            // Method bên ngoài đọc this.source rồi truyền vào component.
            parsed.add(new ParsedLine(source, i + 1, input.get(i)));
        }

        return parsed.stream()
            .map(ParsedLine::display)
            .toList();
    }

    public static void main(String[] args) {
        Demo demo = new Demo("users.csv");

        List<String> lines = List.of(
            "An,20",
            "Binh,22"
        );

        demo.parseLines(lines).forEach(System.out::println);
    }
}
~~~

Biên dịch và chạy bằng JDK 16 trở lên:

~~~bash
javac --release 16 Demo.java
java Demo
~~~

Điểm cần quan sát:

1. `ParsedLine` chỉ được khai báo trong method `parseLines()`.
2. Local record không capture `this` hoặc field `source` của `Demo`.
3. Method bên ngoài đọc `source` rồi truyền giá trị đó qua component cùng tên.
4. Compact canonical constructor xác thực và chuẩn hóa dữ liệu.
5. Instance method `display()` hoạt động trên các component của local record.
6. Sau khi chuyển thành `List<String>`, method trả về kiểu công khai mà caller có thể sử dụng mà không cần biết local type.

## 12. Lỗi thường gặp và cách khắc phục

1. **Cho rằng local record capture biến effectively final:** không đúng; truyền biến thành component hoặc tham số method.
2. **Truy cập `Outer.this` trong local record:** local record không có enclosing instance; đọc giá trị trong method bên ngoài rồi truyền vào.
3. **Dùng tên local record ở method khác:** tên chỉ có scope trong block khai báo; nâng kiểu thành member hoặc top-level nếu cần chia sẻ.
4. **Nghĩ local record chỉ được khai báo trong instance method:** có thể khai báo trong method, constructor hoặc block phù hợp.
5. **Dùng local record để thay lambda:** record biểu diễn dữ liệu; lambda biểu diễn hành vi của functional interface.
6. **Nhầm component với biến capture:** component là dữ liệu được truyền vào constructor; biến capture là biến bên ngoài được giữ ngầm bởi local class/lambda.
7. **Cố dùng type parameter của outer generic class như thể local record có outer instance:** local record có tính static ngầm định; khai báo type parameter riêng hoặc truyền giá trị theo kiểu phù hợp.
8. **Đưa local record vào API công khai:** caller không thể tham chiếu tên local type; dùng interface hoặc chuyển record lên member/top-level scope.

## 13. Bài tập thực hành

1. Viết method `parse()` có local record `Token(String text, int position)`. Tạo một danh sách token từ chuỗi đầu vào.
2. Viết local record `Summary(String prefix, String value)` và truyền tham số method `prefix` vào constructor. Giải thích vì sao đây không phải capture.
3. Thử tham chiếu biến local effectively final từ bên trong local record. Giải thích vì sao compiler từ chối.
4. Khai báo local record trong constructor và dùng nó để xác thực dữ liệu đầu vào.
5. So sánh local record và local class khi cả hai cần dùng một biến `prefix` của method.
6. Viết interface `RowView`, sau đó khai báo local record triển khai interface và trả kết quả qua `List<RowView>`.
7. Dùng local record trong Stream pipeline để nhóm tên và độ dài, sau đó chuyển kết quả thành danh sách.
8. Xác định khi nào local record nên được chuyển thành member nested record hoặc top-level record.

## Ghi nhớ

Local record là record được khai báo trong một block, thường là method hoặc constructor, và tên của nó chỉ có scope trong block đó. Local record ngầm định là static, nên không capture local variable hoặc tham số method, không giữ enclosing instance và không thể truy cập trực tiếp `Outer.this` hay field instance của outer object. Muốn dùng dữ liệu bên ngoài, hãy đọc dữ liệu trong method bao quanh rồi truyền vào constructor như component, hoặc truyền vào tham số của phương thức local record. So với local class và lambda, local record phù hợp để gom nhóm dữ liệu có tên, accessor và equality theo component; local class và lambda có thể capture biến effectively final. Khi kiểu cần xuất hiện trong chữ ký API hoặc được dùng ở nhiều method, hãy chuyển nó thành member record hoặc top-level record. Đây là quy tắc ổn định của Java record từ Java 16, vẫn áp dụng trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Local Class and Interface Declarations, mục 14.3](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-14.html#jls-14.3)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Java Language Specification – Inner Classes and Enclosing Instances, mục 8.1.3](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.1.3)
