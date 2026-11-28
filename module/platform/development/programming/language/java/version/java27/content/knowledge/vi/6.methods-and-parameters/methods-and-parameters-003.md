# Nạp chồng phương thức và cách chọn lời gọi phù hợp

Nạp chồng phương thức (*method overloading*) cho phép một lớp định nghĩa nhiều phương thức cùng tên nhưng nhận các danh sách tham số khác nhau. Khi gặp lời gọi, trình biên dịch xác định phương thức phù hợp dựa trên tên, số lượng và kiểu đối số, kiểu đích của một số biểu thức như lambda, cùng các quy tắc chuyển đổi kiểu của Java.

Trong Java 27, overload resolution vẫn là quá trình được thực hiện tại thời điểm biên dịch. Hiểu cách trình biên dịch chọn overload giúp bạn thiết kế API dễ dùng, tránh lời gọi mơ hồ và dự đoán chính xác phương thức nào được gọi.

## 1. Nạp chồng phương thức là gì?

Một lớp có thể cung cấp nhiều phiên bản của một thao tác với cùng tên, miễn là các phương thức có chữ ký khác nhau:

```java
class TextFormatter {
    String format(String value) {
        return value.strip();
    }

    String format(String value, boolean uppercase) {
        var result = value.strip();
        return uppercase ? result.toUpperCase() : result;
    }

    String format(int value) {
        return Integer.toString(value);
    }
}
```

Các lời gọi sau chọn phiên bản phù hợp theo đối số:

```java
var formatter = new TextFormatter();

formatter.format("  Java 27  ");
formatter.format("  Java 27  ", true);
formatter.format(27);
```

Cách thiết kế này hữu ích khi các thao tác có cùng ý nghĩa nhưng cần nhận các dạng dữ liệu hoặc số lượng thông tin khác nhau. Người dùng API có thể ghi nhớ một tên phương thức thay vì nhiều tên gần giống nhau.

Nạp chồng cũng áp dụng cho constructor. Một lớp có thể có nhiều constructor với danh sách tham số khác nhau để hỗ trợ nhiều cách khởi tạo đối tượng:

```java
class User {
    private final String name;
    private final int age;

    User(String name) {
        this(name, 0);
    }

    User(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
```

Lời gọi `new User("Lan")` chọn constructor một tham số; lời gọi `new User("Lan", 25)` chọn constructor hai tham số. Constructor không có kiểu trả về và không được kế thừa như phương thức thông thường.

## 2. Chữ ký phương thức và điều kiện để overload

Theo Java Language Specification, chữ ký phương thức gồm tên phương thức, các tham số kiểu (nếu có) và kiểu của các tham số hình thức. Khi so sánh các chữ ký generic, cần áp dụng quy tắc thích hợp về việc thích nghi tham số kiểu. Số lượng tham số và thứ tự kiểu tham số cũng tạo nên khác biệt.

Ví dụ, các phương thức sau có chữ ký khác nhau:

```java
void log(String message) {}

void log(String message, int level) {}

void log(int level, String message) {}
```

Những khác biệt sau không đủ để tạo overload:

| Khác biệt | Có tạo overload không? | Giải thích |
|---|---|---|
| Tên tham số | Không | Tên tham số không thuộc chữ ký |
| Kiểu trả về | Không | Chỉ đổi kiểu trả về không tạo chữ ký mới |
| Kiểu tham số | Có | Kiểu tham số khác nhau có thể tạo chữ ký khác |
| Số lượng tham số | Có | Danh sách tham số có độ dài khác nhau |
| Thứ tự kiểu tham số | Có | Ví dụ `(String, int)` và `(int, String)` |
| `throws` clause | Không | Khai báo ngoại lệ không phân biệt overload |

Không thể khai báo hai phương thức chỉ khác kiểu trả về:

```java
class InvalidCalculator {
    // int calculate(int value) { return value; }

    // Không hợp lệ: cùng chữ ký với phương thức trên
    // double calculate(int value) { return value; }
}
```

Nếu cần hai cách tính khác nhau, hãy thay đổi danh sách tham số hoặc chọn tên phương thức thể hiện rõ ý nghĩa. Đừng trông chờ trình biên dịch chọn theo kiểu biến nhận kết quả:

```java
// int result = calculate(10);
// double result = calculate(10);
// Hai khai báo trên không thể phân biệt một overload chỉ bằng kiểu trả về.
```

Một overload có thể khác kiểu tham số sau khi xét generic:

```java
void process(java.util.List<String> values) {}

void process(java.util.Set<String> values) {}
```

Hai phương thức này có kiểu tham số được xóa khác nhau (`List` và `Set`), nên có thể cùng tồn tại. Tuy nhiên, không thể tạo overload chỉ bằng cách đổi đối số kiểu generic:

```java
// Không hợp lệ: cả hai đều có erasure là process(List)
// void process(java.util.List<String> values) {}
// void process(java.util.List<Integer> values) {}
```

Java dùng type erasure cho generic. Vì vậy, các chữ ký có cùng erasure có thể gây *name clash* dù phần khai báo kiểu generic trông khác nhau. Khi thiết kế API generic, hãy kiểm tra chữ ký sau erasure, không chỉ nhìn vào đối số kiểu trong mã nguồn.

## 3. Trình biên dịch chọn overload như thế nào?

Khi biên dịch một lời gọi phương thức, Java thực hiện các bước chính:

1. Xác định kiểu khai báo hoặc kiểu biên dịch của biểu thức nhận lời gọi, nếu có.
2. Tìm các phương thức có thể truy cập với tên được gọi trong phạm vi thích hợp.
3. Xác định các phương thức áp dụng được với số lượng đối số và kiểu đối số.
4. Chọn phương thức cụ thể nhất (*most specific method*) trong số các phương thức áp dụng được.
5. Nếu không có phương thức phù hợp hoặc có nhiều phương thức tốt nhất không thể phân định, báo lỗi biên dịch.

Overload resolution dựa trên kiểu tại thời điểm biên dịch. Đối với phương thức instance đã được override, sau khi chữ ký được chọn, cơ chế dispatch động có thể quyết định phần triển khai nào chạy theo kiểu thực tế của đối tượng.

### Ưu tiên đối số khớp chính xác

```java
class Printer {
    void print(int value) {
        System.out.println("int");
    }

    void print(long value) {
        System.out.println("long");
    }

    void print(double value) {
        System.out.println("double");
    }
}
```

Với lời gọi:

```java
var printer = new Printer();

printer.print(10);    // int
printer.print(10L);   // long
printer.print(10.0);  // double
```

Khi có phương thức nhận đúng kiểu đối số, phương thức đó thường được ưu tiên hơn phương thức cần chuyển đổi kiểu. Nếu chỉ có `print(long)` và truyền `int`, Java có thể mở rộng `int` thành `long` để gọi.

### Thứ tự các giai đoạn áp dụng

Java không thử mọi kiểu chuyển đổi cùng lúc. Quy tắc gọi phương thức xét các giai đoạn theo thứ tự, dừng tại giai đoạn đầu tiên có phương thức áp dụng được:

| Giai đoạn | Loại chuyển đổi chính | Varargs |
|---|---|---|
| 1. Strict invocation | Khớp identity và mở rộng kiểu nguyên thủy/tham chiếu; có thể có unchecked conversion theo quy tắc JLS | Không dùng arity biến đổi |
| 2. Loose invocation | Cho phép boxing/unboxing cùng các chuyển đổi được phép trong loose invocation context | Không dùng arity biến đổi |
| 3. Variable arity | Áp dụng phương thức varargs khi các giai đoạn trước không tìm được phương thức | Có |

Một hệ quả quan trọng: phương thức cần mở rộng kiểu nguyên thủy có thể được chọn trước phương thức cần boxing, dù người đọc có thể nghĩ rằng kiểu wrapper gần với đối số hơn.

```java
class ConversionDemo {
    void accept(long value) {
        System.out.println("long");
    }

    void accept(Integer value) {
        System.out.println("Integer");
    }
}

var demo = new ConversionDemo();
demo.accept(5); // long
```

Với đối số literal `5` kiểu `int`, overload `accept(long)` áp dụng được ngay ở giai đoạn strict bằng widening primitive conversion. Overload `accept(Integer)` cần boxing và chỉ được xét ở giai đoạn loose. Giai đoạn đầu đã có ứng viên nên Java chọn `accept(long)`.

Nếu truyền một biến kiểu `Integer`, overload nhận `Integer` có thể khớp trực tiếp:

```java
Integer number = 5;
demo.accept(number); // Integer
```

Ví dụ này cho thấy kiểu của biểu thức đối số rất quan trọng, ngay cả khi giá trị runtime của chúng có vẻ tương tự nhau.

### Boxing, unboxing và widening

Các chuyển đổi thường gặp trong overload gồm:

- **Widening primitive:** ví dụ `int` sang `long`, `long` sang `float`, hoặc `float` sang `double`.
- **Widening reference:** ví dụ `String` sang `CharSequence` hoặc `Object`.
- **Boxing:** ví dụ `int` thành `Integer`.
- **Unboxing:** ví dụ `Integer` thành `int`.
- **Varargs:** gom nhiều đối số thành một mảng cho tham số có dấu `...`.

Không phải mọi chuỗi chuyển đổi đều hợp lệ. Chẳng hạn, Java không tự thực hiện widening primitive rồi boxing thành wrapper trong cùng một phép chuyển đổi để làm cho overload áp dụng được. Unchecked conversion có thể được áp dụng sau những chuyển đổi invocation được phép nếu kết quả là raw type, theo quy tắc của JLS. Hãy ưu tiên kiểu tham số rõ ràng, tránh thiết kế các overload mà lựa chọn phụ thuộc vào một chuỗi chuyển đổi khó nhận biết.

## 4. Chọn phương thức cụ thể nhất

Nếu nhiều phương thức cùng áp dụng được, Java so sánh mức độ cụ thể của các kiểu tham số. Phương thức có kiểu tham số cụ thể hơn có thể được ưu tiên so với phương thức nhận kiểu tổng quát hơn.

```java
class MessageSender {
    void send(Object value) {
        System.out.println("Object");
    }

    void send(CharSequence value) {
        System.out.println("CharSequence");
    }

    void send(String value) {
        System.out.println("String");
    }
}

var sender = new MessageSender();
sender.send("Hello"); // String
```

Với đối số kiểu `String`, cả ba overload đều có thể áp dụng bằng mở rộng tham chiếu. `String` là kiểu cụ thể nhất trong ba kiểu tham số, nên `send(String)` được chọn.

Nếu chỉ có `send(Object)` và `send(CharSequence)`, lời gọi với `String` chọn `send(CharSequence)`, bởi `String` triển khai `CharSequence` và `CharSequence` cụ thể hơn `Object` trong quan hệ kiểu này.

### Khi nào lời gọi bị mơ hồ?

Hai overload có thể cùng áp dụng nhưng không có overload nào cụ thể hơn overload còn lại:

```java
class AmbiguousFormatter {
    void format(String value) {
        System.out.println("String");
    }

    void format(Integer value) {
        System.out.println("Integer");
    }
}

// var formatter = new AmbiguousFormatter();
// formatter.format(null); // Lỗi biên dịch: lời gọi mơ hồ
```

Literal `null` có thể chuyển đổi sang mọi kiểu tham chiếu. Nhưng `String` và `Integer` không phải kiểu con của nhau, nên không có overload nào cụ thể hơn. Trình biên dịch không chọn dựa trên giá trị có thể có lúc chạy.

Nếu thực sự muốn gọi một overload cụ thể, hãy cung cấp kiểu rõ ràng bằng cách ép kiểu:

```java
var formatter = new AmbiguousFormatter();

formatter.format((String) null);
formatter.format((Integer) null);
```

Trong API công khai, nên cân nhắc tránh các overload nhận những kiểu tham chiếu không liên quan nếu người gọi thường truyền `null`. Một phương án khác là dùng tên phương thức riêng hoặc yêu cầu đối số không null bằng hợp đồng rõ ràng.

Một trường hợp khác là kiểu đối số triển khai nhiều interface không có quan hệ kế thừa:

```java
interface JsonValue {}
interface XmlValue {}

class DocumentValue implements JsonValue, XmlValue {}

class DocumentWriter {
    void write(JsonValue value) {}
    void write(XmlValue value) {}
}

// var writer = new DocumentWriter();
// writer.write(new DocumentValue()); // Mơ hồ
```

`DocumentValue` có thể chuyển đổi sang cả hai interface, nhưng `JsonValue` và `XmlValue` không cụ thể hơn nhau. Hãy thêm overload nhận `DocumentValue`, ép kiểu rõ ràng tại điểm gọi, hoặc điều chỉnh API để thể hiện ý định.

## 5. Nạp chồng với varargs

Varargs cho phép một phương thức nhận số lượng đối số thay đổi:

```java
class TagPrinter {
    void print(String value) {
        System.out.println("single: " + value);
    }

    void print(String... values) {
        System.out.println("many: " + String.join(", ", values));
    }
}

var tags = new TagPrinter();
tags.print("java");                  // single: java
tags.print("java", "jdk", "jshell"); // many: java, jdk, jshell
tags.print();                        // many:
```

Tham số `String... values` được biểu diễn bằng mảng `String[]`. Khi gọi với nhiều đối số, Java tạo mảng để truyền cho phương thức. Khi gọi với một đối số `String`, overload một tham số thông thường được xét ở giai đoạn fixed arity trước overload varargs ở giai đoạn variable arity.

Một phương thức varargs cũng có thể được gọi như phương thức nhận mảng:

```java
String[] values = {"java", "jdk"};
tags.print(values);
```

Khi thiết kế overload có varargs, cần nhớ rằng varargs chỉ được xét ở giai đoạn thứ ba của overload resolution. Một phương thức fixed-arity có thể được chọn trước, dù overload varargs có vẻ linh hoạt hơn.

## 6. Nạp chồng với kiểu tham số generic

Các phương thức nhận kiểu tham số generic có thể được overload nếu chữ ký của chúng khác nhau và không gây xung đột sau type erasure:

```java
import java.util.Collection;
import java.util.List;
import java.util.Set;

class CollectionInspector {
    void inspect(List<String> values) {
        System.out.println("List: " + values.size());
    }

    void inspect(Set<String> values) {
        System.out.println("Set: " + values.size());
    }

    void inspect(Collection<Integer> values) {
        System.out.println("Integer collection: " + values.size());
    }
}
```

Các overload trên khác kiểu tham số được xóa: `List`, `Set` và `Collection`. Tuy nhiên, khi truyền một đối tượng có kiểu cụ thể, cần xét kiểu khai báo của đối số và quan hệ kế thừa của các kiểu collection.

Không thể overload chỉ dựa trên đối số kiểu generic vì type erasure:

```java
class InvalidRepository {
    // void save(List<String> values) {}
    // void save(List<Integer> values) {}
    // Cả hai có cùng erasure: save(List)
}
```

Một phương thức generic và một phương thức không generic cũng có thể tạo xung đột nếu chữ ký sau khi áp dụng quy tắc type erasure trùng nhau. Khi compiler báo *name clash*, hãy xem thông báo về erasure và thiết kế lại danh sách tham số hoặc tên phương thức.

## 7. Nạp chồng với lambda và method reference

Lambda không có kiểu độc lập theo cách literal như `"text"` hay `10`. Kiểu của lambda được xác định từ kiểu hàm đích (*target type*) mà ngữ cảnh cung cấp. Vì vậy, khi overload nhận các kiểu functional interface khác nhau, trình biên dịch phải xét khả năng tương thích của lambda với từng kiểu đích.

Ví dụ, một lambda có thân chỉ in ra thông báo phù hợp với `Runnable`:

```java
class JobRunner {
    void run(Runnable job) {
        System.out.println("Runnable");
        job.run();
    }

    void run(java.util.concurrent.Callable<String> job) {
        System.out.println("Callable");
        try {
            System.out.println(job.call());
        } catch (Exception exception) {
            throw new RuntimeException(exception);
        }
    }
}

var runner = new JobRunner();
runner.run(() -> System.out.println("working"));
```

Lambda trên không trả về giá trị, nên phù hợp với `Runnable` và không phù hợp với `Callable<String>`.

Nếu lambda trả về một biểu thức có giá trị, nó có thể phù hợp với nhiều kiểu hàm đích tùy dạng thân lambda và chữ ký của functional interface. Ví dụ, lời gọi phương thức trả về giá trị là một statement expression, do đó lambda expression body có thể tương thích với cả kiểu hàm đích void-compatible lẫn value-compatible trong những trường hợp tương ứng:

```java
class Handler {
    void handle(java.util.function.Consumer<String> action) {}
    void handle(java.util.function.Function<String, String> action) {}
}

class Lookup {
    String fetch(String key) {
        return "value for " + key;
    }
}

var lookup = new Lookup();
var handler = new Handler();

// Cả hai functional interface có tham số String và không có quan hệ subtype.
// Lambda expression body là lời gọi phương thức có giá trị trả về,
// đồng thời là statement expression nên có thể tương thích với cả hai.
// handler.handle(key -> lookup.fetch(key)); // Lỗi biên dịch: mơ hồ

handler.handle(key -> { return lookup.fetch(key); }); // Function<String, String>
handler.handle(key -> { lookup.fetch(key); });        // Consumer<String>
```

Hai lambda block được viết rõ ý định: block có `return` trả về một giá trị; block chỉ thực hiện câu lệnh thì không trả về giá trị. Dạng expression body `key -> lookup.fetch(key)` có thể thỏa mãn cả hai kiểu tương thích và gây mơ hồ vì các functional interface không có quan hệ subtype và lambda có tham số được suy luận kiểu.

Method reference cũng được xét theo kiểu hàm đích. Khi có nhiều overload nhận functional interface khác nhau, hãy kiểm tra tham số, kiểu trả về và khả năng tương thích của method reference với từng interface. Nếu lựa chọn không rõ, dùng lambda có kiểu hoặc khai báo biến functional interface trước khi gọi:

```java
java.util.function.Function<String, String> task = lookup::fetch;
handler.handle(task);
```

Khi thiết kế API, tránh nhiều overload functional interface có hình dạng gần giống nhau nếu chúng khiến lambda phổ biến trở nên mơ hồ. Có thể dùng tên phương thức riêng, kiểu wrapper có ý nghĩa hoặc một functional interface chuyên biệt với hợp đồng rõ ràng.

## 8. Overloading và overriding khác nhau như thế nào?

Overloading và overriding đều liên quan đến nhiều phương thức cùng tên, nhưng cơ chế hoạt động khác nhau:

| Tiêu chí | Overloading (nạp chồng) | Overriding (ghi đè) |
|---|---|---|
| Mục đích | Cung cấp nhiều danh sách tham số cho một thao tác | Thay đổi triển khai phương thức kế thừa |
| Chữ ký | Khác nhau | Phải đáp ứng quy tắc override |
| Quyết định chính | Trình biên dịch chọn overload | Runtime dispatch chọn triển khai override |
| Quan hệ kế thừa | Không bắt buộc | Thường liên quan đến lớp con và lớp cha/interface |
| Kiểu trả về | Không dùng để phân biệt overload | Có thể dùng kiểu trả về hiệp biến theo quy tắc |

Ví dụ kết hợp cả hai cơ chế:

```java
class Animal {
    String sound() {
        return "unknown";
    }

    void describe(Animal animal) {
        System.out.println("Animal");
    }

    void describe(Dog dog) {
        System.out.println("Dog");
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

Animal pet = new Dog();

System.out.println(pet.sound()); // woof
pet.describe(pet);               // Animal
```

Ở lời gọi `pet.sound()`, chữ ký `sound()` được xác định tại biên dịch. Vì đây là phương thức instance được override, triển khai `Dog.sound()` được gọi theo đối tượng thực tế.

Ở lời gọi `pet.describe(pet)`, kiểu biên dịch của đối số `pet` là `Animal`, nên overload `describe(Animal)` được chọn. Việc đối tượng thực tế là `Dog` không làm overload `describe(Dog)` được chọn tự động. Overload resolution dựa trên kiểu biên dịch của biểu thức đối số.

## 9. Quy trình phân tích một lời gọi overload

Khi không chắc phương thức nào được chọn, hãy phân tích theo trình tự:

1. **Xác định kiểu biên dịch của từng đối số.** Không chỉ nhìn giá trị runtime; xem biến được khai báo bằng kiểu nào và biểu thức có kiểu trả về gì.
2. **Liệt kê các overload có thể truy cập.** Xem cả phương thức được kế thừa, generic method và các phương thức varargs.
3. **So khớp số lượng tham số.** Xác định overload fixed-arity và overload variable-arity.
4. **Xét chuyển đổi kiểu theo từng giai đoạn.** Strict invocation trước, loose invocation sau, cuối cùng mới variable arity.
5. **So sánh tính cụ thể.** Nếu nhiều phương thức áp dụng được, xác định phương thức nào most specific theo quy tắc Java.
6. **Kiểm tra tính mơ hồ.** Nếu không có một phương thức cụ thể nhất duy nhất, lời gọi không hợp lệ và cần điều chỉnh API hoặc biểu thức đối số.
7. **Phân biệt dispatch runtime.** Sau khi overload được chọn, nếu phương thức instance bị override, triển khai runtime phù hợp sẽ được thực thi.

Một cách kiểm tra hữu ích là gán biểu thức vào biến có kiểu tường minh hoặc ép kiểu đối số trong một ví dụ nhỏ để quan sát cách thay đổi kiểu biên dịch ảnh hưởng đến lựa chọn. Không nên dùng ép kiểu để che giấu một API mơ hồ trong mã sản phẩm; hãy sửa thiết kế khi nhiều lời gọi hợp lệ vẫn khó phân biệt.

## 10. Hướng dẫn thiết kế overload dễ dùng

Một nhóm overload tốt nên thể hiện cùng một ý nghĩa nghiệp vụ và có quy tắc lựa chọn dễ dự đoán.

- Dùng overload khi các phiên bản thực hiện cùng một thao tác nhưng khác dữ liệu đầu vào hoặc mức thông tin.
- Ưu tiên một overload có tham số mặc định thông qua constructor hoặc factory method khi điều đó làm ý định rõ hơn; Java không có cú pháp tham số mặc định cho phương thức.
- Tránh các overload chỉ khác nhau bởi các kiểu tham chiếu không liên quan nếu người gọi thường truyền `null`.
- Cẩn thận khi kết hợp overload nhận wrapper, primitive và varargs; các giai đoạn chuyển đổi có thể dẫn đến kết quả ít trực quan.
- Hạn chế overload nhận các functional interface có hình dạng tương tự vì lambda và method reference có thể trở nên mơ hồ.
- Không tạo overload generic có cùng erasure.
- Dùng tên phương thức riêng nếu hai thao tác khác ý nghĩa hoặc nếu việc phân giải overload quá khó đoán.
- Viết Javadoc mô tả khác biệt về ngữ nghĩa, điều kiện đầu vào, giá trị trả về và ngoại lệ của từng overload.

Nếu có nhiều tham số cùng kiểu, hãy cân nhắc một kiểu miền hoặc builder để tránh nhầm thứ tự đối số:

```java
// Hai tham số int cùng kiểu: lời gọi khó đọc
void transfer(String source, String target, int amount) {}

// Kiểu miền có tên giúp làm rõ ý nghĩa
record Money(long minorUnits, String currency) {}

void transfer(String source, String target, Money amount) {}
```

Một API dễ dùng giúp người gọi ít phải ghi nhớ quy tắc chuyển đổi và có thể hiểu lời gọi chỉ từ tên phương thức, kiểu tham số và tài liệu.

## 11. Bài tập tự kiểm tra

Giả sử các lớp và phương thức trong từng câu được khai báo như ví dụ.

**Câu 1.** Với các overload:

```java
void show(int value) {}
void show(long value) {}
void show(Integer value) {}
```

Lời gọi `show(7)` chọn phương thức nào?

**Câu 2.** Với các overload:

```java
void print(Object value) {}
void print(String value) {}
```

Lời gọi `print(null)` chọn phương thức nào?

**Câu 3.** Với các overload:

```java
void write(String value) {}
void write(Integer value) {}
```

Lời gọi `write(null)` có hợp lệ không?

**Câu 4.** Vì sao hai phương thức `save(List<String>)` và `save(List<Integer>)` không thể cùng tồn tại trong một lớp?

**Câu 5.** Với các overload `run(Runnable)` và `run(Callable<String>)`, lambda `() -> System.out.println("run")` phù hợp với overload nào?

**Câu 6.** Một biến có kiểu biên dịch `Animal` nhưng tham chiếu tới đối tượng `Dog`. Khi gọi overload `describe(Animal)` và `describe(Dog)`, kiểu nào được dùng để chọn overload?

**Đáp án gợi ý:**

1. `show(int)`: đối số `7` có kiểu `int`, khớp chính xác ở giai đoạn strict.
2. `print(String)`: `String` cụ thể hơn `Object` trong các kiểu tham chiếu áp dụng được cho null.
3. Không. Hai kiểu `String` và `Integer` không có quan hệ subtype với nhau nên lời gọi mơ hồ.
4. Vì type erasure khiến cả hai có cùng erasure `save(List)`.
5. `run(Runnable)`: lambda chỉ thực hiện câu lệnh và không trả về giá trị.
6. Kiểu biên dịch `Animal` của biểu thức đối số được dùng để chọn overload; kiểu runtime `Dog` không thay đổi quyết định đó.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — §8.4.2 Method Signature](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.2): cách xác định chữ ký phương thức.
- [Java Language Specification, Java SE 27 — §8.4.9 Overloading](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.9): quy tắc nạp chồng phương thức.
- [Java Language Specification, Java SE 27 — §15.12 Method Invocation Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.12): xác định phương thức được gọi và overload resolution.
- [Java Language Specification, Java SE 27 — §5.3 Method Invocation Contexts](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-5.html#jls-5.3): strict và loose invocation conversions.
- [Java Language Specification, Java SE 27 — §15.27 Lambda Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.27): kiểu hàm đích và khả năng tương thích của lambda.
- [Java Language Specification, Java SE 27 — §15.13 Method Reference Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.13): method reference và target typing.
- [Java Language Specification, Java SE 27 — §4.6 Type Erasure](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.6): ảnh hưởng của type erasure đến chữ ký generic.
