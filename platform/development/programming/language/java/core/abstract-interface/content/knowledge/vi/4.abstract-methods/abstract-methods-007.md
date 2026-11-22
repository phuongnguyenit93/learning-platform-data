# Overload phương thức abstract trong Java

## 1. Khái niệm: phương thức abstract có được overload không?

**Có.** Trong Java, một lớp trừu tượng (`abstract class`) hoặc một giao diện (`interface`) có thể khai báo nhiều phương thức **cùng tên nhưng khác danh sách tham số**. Đó là **nạp chồng phương thức (method overloading)**, kể cả khi các phương thức này chưa có phần thân.

Ví dụ:

```java
abstract class Parser {
    public abstract String parse(int number);
    public abstract String parse(String text);
    public abstract String parse(String text, boolean strict);
}
```

Đây là **ba phương thức abstract được overload hợp lệ**:

- `parse(int)` xử lý đầu vào kiểu số nguyên.
- `parse(String)` xử lý chuỗi.
- `parse(String, boolean)` xử lý chuỗi với thêm cờ cấu hình.

Mỗi chữ ký (signature) khác nhau bởi **số lượng, kiểu hoặc thứ tự kiểu tham số**. Các phương thức cùng tên này là những hợp đồng **riêng biệt**. Một lớp con cụ thể phải hiện thực tất cả các phương thức abstract chưa được hiện thực mà nó kế thừa, nếu không chính lớp đó cũng phải khai báo `abstract` (trừ các tình huống phương thức đã được đáp ứng bằng triển khai kế thừa phù hợp).

Điểm cần nhớ: `abstract` nói về việc **chưa cung cấp triển khai**, trong khi `overload` nói về **nhiều chữ ký cùng tên**. Hai đặc tính hoàn toàn có thể xuất hiện đồng thời.

## 2. Phân biệt overload, override và abstract

| Thuộc tính | Overload (nạp chồng) | Override (ghi đè) |
| --- | --- | --- |
| Quan hệ giữa phương thức | Cùng tên, **khác danh sách tham số** | Phương thức ở kiểu con cung cấp triển khai cho phương thức kế thừa có **chữ ký tương ứng** |
| Mục đích | Hỗ trợ nhiều dạng đầu vào/dạng gọi | Thay thế hoặc bổ sung cách thực hiện hợp đồng được kế thừa |
| Có thể xảy ra ở đâu? | Ngay trong một lớp/interface hoặc giữa các thành viên kế thừa | Giữa kiểu con và kiểu cha/giao diện |
| Cơ chế chọn | Thường được xác định **lúc biên dịch**, dựa trên kiểu tĩnh và đối số của lời gọi | Với phương thức thể hiện có thể ghi đè, triển khai được chọn **lúc chạy** theo lớp thực tế của đối tượng |
| `@Override` | Không dùng chỉ vì có thêm một overload | Nên dùng trên phương thức thật sự ghi đè/hiện thực |
| Trường hợp phương thức abstract | Nhiều khai báo `abstract` cùng tên, khác tham số | Lớp con cụ thể thường dùng `@Override` để cung cấp thân phương thức |

Ví dụ khác nhau:

```java
abstract class Analyzer {
    abstract String analyze(String input);
    abstract String analyze(byte[] input); // overload analyze(String)
}

final class DefaultAnalyzer extends Analyzer {
    @Override
    String analyze(String input) {         // override analyze(String)
        return input;
    }

    @Override
    String analyze(byte[] input) {         // override analyze(byte[])
        return Integer.toString(input.length);
    }
}
```

Đoạn trên là ví dụ định nghĩa kiểu, không có `main()`; hãy xem chương trình hoàn chỉnh ở phần tiếp theo để chạy trực tiếp.

Hai phương thức của `Analyzer` **nạp chồng** nhau. Mỗi phương thức cùng chữ ký ở `DefaultAnalyzer` lại **ghi đè** khai báo abstract tương ứng. Một phương thức có thể cùng lúc *là một overload trong tập cùng tên* và *là một override đối với chữ ký được kế thừa*.

## 3. Chương trình Java 17+ hoàn chỉnh

Ví dụ này thể hiện cả ba trường hợp: hai overload abstract, một overload có sẵn thân hàm, và lớp con hiện thực hai hợp đồng còn thiếu.

Tạo tệp **`AbstractOverloadDemo.java`**:

```java
abstract class Printer {
    protected final String prefix;

    protected Printer(String prefix) {
        this.prefix = prefix;
    }

    // Overload 1: chưa triển khai.
    public abstract String print(int value);

    // Overload 2: chưa triển khai.
    public abstract String print(String value);

    // Overload 3: đã có triển khai, gọi lại overload String.
    public String print(boolean value) {
        return print(Boolean.toString(value));
    }
}

final class ConsolePrinter extends Printer {
    public ConsolePrinter(String prefix) {
        super(prefix);
    }

    @Override
    public String print(int value) {
        return prefix + "#" + value;
    }

    @Override
    public String print(String value) {
        return prefix + "[" + value.trim() + "]";
    }
}

public class AbstractOverloadDemo {
    public static void main(String[] args) {
        Printer printer = new ConsolePrinter("item:");

        System.out.println(printer.print(12));
        System.out.println(printer.print(" Java "));
        System.out.println(printer.print(true));
    }
}
```

Chạy:

```bash
javac AbstractOverloadDemo.java
java AbstractOverloadDemo
```

Đầu ra:

```text
item:#12
item:[Java]
item:[true]
```

**Giải thích từng lời gọi:**

1. `printer.print(12)`: đối số `12` có kiểu `int`; trình biên dịch chọn chữ ký `print(int)`. Khi chạy, đối tượng thực sự là `ConsolePrinter`, nên dùng phần triển khai `ConsolePrinter.print(int)`.
2. `printer.print(" Java ")`: đối số là `String`; chọn `print(String)` và thực thi triển khai ở `ConsolePrinter`. `trim()` loại khoảng trắng đầu/cuối.
3. `printer.print(true)`: chọn `print(boolean)`, **không phải phương thức abstract**. Phương thức này chuyển `true` thành `"true"`, rồi gọi `print(String)`. Lời gọi bên trong vẫn được phân phối đến `ConsolePrinter.print(String)`.

Từ đó thấy rằng **overload của một tên có thể gồm cả phương thức abstract và phương thức concrete**. Tất cả là những cách gọi khác nhau của một ý niệm thao tác chung.

Ngoài ra, `protected final String prefix` là trạng thái được khởi tạo qua constructor của lớp cha. Không thể tạo `new Printer(...)` trực tiếp vì `Printer` là lớp trừu tượng, nhưng đối tượng `ConsolePrinter` vẫn chứa phần trạng thái do `Printer` khai báo.

## 4. Quy tắc tạo các overload hợp lệ

### 4.1. Khác số lượng, kiểu hoặc thứ tự tham số

Ví dụ trong **cùng một** lớp trừu tượng:

```java
abstract class TaskRouter {
    abstract void route(String id);
    abstract void route(String id, int priority);
    abstract void route(int priority, String id);
    abstract void route(long numericId);
}
```

Bốn chữ ký khác nhau là hợp lệ. Tên biến tham số **không** phải yếu tố phân biệt chữ ký: đổi `route(String id)` thành `route(String name)` không tạo overload mới.

### 4.2. Chỉ thay đổi kiểu trả về là không hợp lệ

```java
abstract class InvalidReturn {
    abstract String find(int id);
    // abstract int find(int id); // LỖI BIÊN DỊCH: cùng tên và tham số.
}
```

Kiểu trả về **không đủ** để phân biệt hai overload. Ngược lại, khi **override**, Java cho phép kiểu trả về tham chiếu hiệp biến (covariant return type) trong những điều kiện hợp lệ. Đừng dùng quy tắc trả về của override để giải thích overload.

### 4.3. Chỉ thay đổi visibility, tên tham số, modifier hoặc throws cũng không đủ

```java
abstract class InvalidThrows {
    abstract void save(String text);
    // abstract void save(String text) throws java.io.IOException;
    // LỖI BIÊN DỊCH nếu bỏ comment: hai phương thức có cùng chữ ký.
}
```

Thêm `throws`, đổi tên `text`, hoặc thay `public/protected` không tạo chữ ký mới. Với phương thức abstract trong lớp, cách xác định visibility ảnh hưởng tới việc có thể hiện thực/gọi phương thức ra sao, nhưng không tạo overload.

### 4.4. Varargs và mảng không tạo hai chữ ký riêng

```java
abstract class InvalidVarargs {
    abstract void log(String... lines);
    // abstract void log(String[] lines); // LỖI: cùng chữ ký sau quy đổi.
}
```

`String...` cho phép truyền nhiều đối số tại vị trí gọi nhưng về hình thức tham số là mảng `String[]`; không thể khai báo thêm overload `log(String[])`.

### 4.5. Generic type erasure có thể gây xung đột

```java
import java.util.List;

abstract class InvalidErasure {
    abstract void accept(List<String> values);
    // abstract void accept(List<Integer> values);
    // LỖI: cả hai cùng bị xóa kiểu về List (name clash).
}
```

Dù `List<String>` khác `List<Integer>` ở mức kiểu generic, cả hai có cùng erasure `List`, nên **không thể** dùng chúng làm hai overload chỉ khác đối số kiểu generic. Hãy đặt tên phương thức khác, dùng kiểu tham số thực sự khác, hoặc thiết kế một hợp đồng generic phù hợp.

### 4.6. Các dạng tham số khác vẫn hợp lệ

`process(int)` và `process(Integer)` là hai overload hợp lệ do `int` khác `Integer`; `process(Number)` và `process(Object)` cũng khác tham số. Tuy nhiên, hợp lệ khi khai báo **không** có nghĩa mọi cách gọi đều không mơ hồ. Cơ chế chọn được trình bày ngay dưới.

## 5. Java chọn overload bằng cách nào?

Tại thời điểm biên dịch, trình biên dịch sử dụng **kiểu tĩnh của biểu thức nhận lời gọi**, các phương thức có thể truy cập, số lượng/kiểu đối số và quy tắc tương thích/chọn phương thức phù hợp nhất.

Có thể ghi nhớ thứ tự đơn giản hóa của các giai đoạn tìm kiếm phương thức áp dụng được:

1. Ưu tiên lời gọi theo **khả năng tương thích chặt** mà không cần boxing/unboxing hay xử lý varargs mở rộng; bao gồm ví dụ nới rộng kiểu nguyên thủy (`int` → `long`) và nới rộng kiểu tham chiếu.
2. Nếu chưa tìm được, mới xét tương thích **mở rộng** cho boxing/unboxing.
3. Nếu vẫn chưa có phương thức phù hợp, mới xét **varargs** như danh sách đối số biến thiên.

Trong mỗi giai đoạn, Java phải chọn được phương thức phù hợp nhất theo quy tắc *most specific*; nếu không có ứng viên duy nhất, lời gọi có thể **lỗi biên dịch vì mơ hồ**. Đây là một mô tả học tập: Java Language Specification còn xét nhiều chi tiết về generic, suy luận kiểu, lambda và khả năng truy cập.

### Ví dụ chạy được: widening, boxing, varargs

Tạo tệp **`OverloadResolutionDemo.java`**:

```java
abstract class Selection {
    abstract String choose(long value);
    abstract String choose(Integer value);
    abstract String choose(int... values);
}

final class SelectionImpl extends Selection {
    @Override
    String choose(long value) {
        return "long";
    }

    @Override
    String choose(Integer value) {
        return "Integer";
    }

    @Override
    String choose(int... values) {
        return "varargs(" + values.length + ")";
    }
}

public class OverloadResolutionDemo {
    public static void main(String[] args) {
        Selection selection = new SelectionImpl();

        System.out.println(selection.choose(5));
        System.out.println(selection.choose(Integer.valueOf(5)));
        System.out.println(selection.choose(5, 6));
    }
}
```

```bash
javac OverloadResolutionDemo.java
java OverloadResolutionDemo
```

```text
long
Integer
varargs(2)
```

- `choose(5)`: đối số `int`, phương thức `choose(long)` nhận chuyển đổi primitive widening và được chọn trước boxing sang `Integer` hoặc mở rộng varargs.
- `choose(Integer.valueOf(5))`: đối số đã là `Integer`, nên phương thức `choose(Integer)` phù hợp trực tiếp.
- `choose(5, 6)`: hai đối số không thể khớp hai overload chỉ có một tham số; lời gọi đi vào `choose(int...)`, nhận mảng có hai phần tử.

**Không nên** hiểu rằng “overload abstract sẽ được chọn khi chạy theo lớp thực tế”. Việc chọn chữ ký và việc chọn triển khai được thực hiện ở **hai bước khác nhau**.

## 6. Overload được chọn tĩnh, override được phân phối động

Tạo tệp **`StaticTypeDispatchDemo.java`**:

```java
abstract class Receiver {
    public abstract String accept(Object value);
}

final class ReceiverImpl extends Receiver {
    @Override
    public String accept(Object value) {
        return "Object:" + value;
    }

    // Overload mới chỉ xuất hiện trong kiểu con.
    public String accept(String value) {
        return "String:" + value;
    }
}

public class StaticTypeDispatchDemo {
    public static void main(String[] args) {
        Receiver asBase = new ReceiverImpl();
        ReceiverImpl asChild = new ReceiverImpl();
        Object text = "hello";

        System.out.println(asBase.accept("hello"));
        System.out.println(asChild.accept("hello"));
        System.out.println(asChild.accept(text));
    }
}
```

```bash
javac StaticTypeDispatchDemo.java
java StaticTypeDispatchDemo
```

```text
Object:hello
String:hello
Object:hello
```

Phân tích:

- `asBase.accept("hello")`: biến được khai báo kiểu `Receiver`; ở kiểu đó **chỉ có** `accept(Object)`. Chữ ký được chọn lúc biên dịch là `accept(Object)`; khi chạy, `ReceiverImpl.accept(Object)` thực thi.
- `asChild.accept("hello")`: biến có kiểu `ReceiverImpl`, nhìn thấy cả hai overload; `accept(String)` phù hợp hơn `accept(Object)`.
- `asChild.accept(text)`: dù `text` đang tham chiếu đến một đối tượng `String`, **kiểu tĩnh** của biến là `Object`; chọn `accept(Object)`.

Nếu yêu cầu mọi đối tượng được nhìn qua `Receiver` vẫn gọi được `accept(String)` theo nghĩa một chữ ký riêng biệt, hãy đưa overload ấy vào hợp đồng `Receiver` và hiện thực nó tại các lớp con. Đừng chỉ thêm overload vào một lớp con rồi mặc định rằng mọi biến kiểu cha sẽ nhìn thấy nó.

## 7. Lớp con phải triển khai những overload nào?

Giả sử:

```java
abstract class MessageProcessor {
    abstract String process(String text);
    abstract String process(int number);

    String process(boolean flag) {
        return Boolean.toString(flag);
    }
}
```

Một lớp con **concrete** phải bảo đảm hai hợp đồng `process(String)` và `process(int)` được hiện thực. Nó **không bắt buộc** override `process(boolean)` vì phương thức này đã có thân hàm.

Một lớp con vẫn được khai báo `abstract` để trì hoãn việc hiện thực một hay nhiều phương thức:

```java
abstract class TextMessageProcessor extends MessageProcessor {
    @Override
    String process(String text) {
        return text.strip();
    }
    // process(int) vẫn abstract, lớp này vẫn là abstract.
}

final class CompleteMessageProcessor extends TextMessageProcessor {
    @Override
    String process(int number) {
        return Integer.toString(number);
    }
}
```

Đây là đoạn định nghĩa các lớp, có thể dùng trong một chương trình khác; không tự có `main()`. `CompleteMessageProcessor` là concrete vì hợp đồng `process(String)` đã có từ lớp cha trực tiếp và `process(int)` đã được cung cấp.

### Một lỗi rất dễ mắc: vô tình overload thay vì override

```java
abstract class ParentHandler {
    abstract void handle(Number value);
}

// Ví dụ CỐ Ý SAI, không biên dịch nếu bỏ comment:
// final class WrongHandler extends ParentHandler {
//     void handle(Integer value) { } // OVERLOAD, không hiện thực handle(Number).
// }
```

Dù `Integer extends Number`, `handle(Integer)` **không** override `handle(Number)` vì danh sách tham số khác. Lớp `WrongHandler` phải khai báo `abstract` hoặc hiện thực đúng `handle(Number)`.

Dùng `@Override` ngay trên phương thức định ghi đè giúp trình biên dịch phát hiện nhầm chữ ký:

```java
// @Override
// void handle(Integer value) { } // Lỗi: không override phương thức của cha.
```

Chú ý: `@Override` chỉ kiểm tra ghi đè/hiện thực hợp đồng. Nó không có tác dụng “khai báo overload” cho hai phương thức cùng tên.

## 8. Overload phương thức abstract trong interface

Trong interface, phương thức thể hiện khai báo **không có thân hàm** (và không phải `default`/`private`/`static`) mặc định là `public abstract`. Vì vậy có thể overload giống abstract class:

```java
interface Encoder {
    String encode(String text);
    String encode(byte[] data);
}
```

Một lớp hiện thực cả hai hợp đồng:

```java
final class PlainEncoder implements Encoder {
    @Override
    public String encode(String text) {
        return text;
    }

    @Override
    public String encode(byte[] data) {
        return java.util.Base64.getEncoder().encodeToString(data);
    }
}
```

Hai đoạn trên ghép lại là các khai báo kiểu hợp lệ; nếu muốn chạy độc lập, thêm lớp có `main()` sử dụng `new PlainEncoder()`. Triển khai dùng **`public`** vì phương thức interface là public; giảm xuống package-private/protected/private sẽ lỗi biên dịch.

Với `interface`, cũng có thể **trộn** overload abstract và overload `default` có triển khai. Việc hỗ trợ overload **không** giúp interface có constructor hay instance field. Chọn interface khi muốn công bố nhiều cách gọi của cùng một khả năng, còn các lớp hiện thực có thể xử lý theo cách riêng.

Nếu một lớp hiện thực **nhiều interface** cùng khai báo hợp đồng trùng chữ ký, phương thức hiện thực phù hợp có thể đáp ứng cùng lúc nhiều hợp đồng. Nếu hai interface mang các phương thức `default` xung đột, việc giải quyết xung đột default method là một vấn đề kế thừa riêng, không phải bản chất của overloading.

## 9. Các tình huống cần thận trọng

### 9.1. `null` có thể dẫn đến overload mơ hồ

```java
abstract class NullableRouter {
    abstract void submit(String text);
    abstract void submit(Integer number);
}

// NullableRouter router = ...;
// router.submit(null); // LỖI BIÊN DỊCH: không xác định được overload nào.
```

Cả `String` và `Integer` đều nhận `null`, nhưng hai kiểu không có quan hệ kiểu con với nhau nên không có ứng viên cụ thể hơn. Có thể chỉ định rõ khi thực sự cần:

```java
// router.submit((String) null);
// router.submit((Integer) null);
```

Đây là các lời gọi minh họa, yêu cầu biến `router` hợp lệ và lớp triển khai xử lý `null` đúng cách. **Ép kiểu để chọn overload không tự làm `null` trở nên an toàn với logic phương thức.**

Nếu có `submit(Object)` và `submit(String)`, đối số `null` thường chọn `submit(String)` vì `String` cụ thể hơn `Object`.

### 9.2. Overload tương tự có thể làm API khó đoán

Khai báo đồng thời `load(int)`, `load(long)`, `load(Integer)`, `load(Number)`, `load(int...)` hoàn toàn có thể hợp lệ nhưng gây bất ngờ khi truyền literal, `null`, biến đã boxing hoặc mảng. Nhiều overload dễ nhầm còn khiến người đọc không biết sự khác biệt nghiệp vụ.

Chỉ overload khi các cách gọi **cùng mục đích** và khác nhau tự nhiên ở kiểu/số tham số. Nếu ngữ nghĩa khác hẳn, đặt tên như `loadById(...)`, `loadFromFile(...)` giúp rõ ý hơn. Một overload quá nhiều tham số tùy chọn có thể thay bằng đối tượng cấu hình có kiểu rõ ràng.

### 9.3. Override một overload không thay thế các overload khác

Nếu kiểu cha có `execute(String)` và `execute(int)`, thì cung cấp thân cho `execute(String)` không đồng nghĩa đã đáp ứng `execute(int)`. Mỗi chữ ký phải được xét riêng, kể cả khi chúng cùng tên.

### 9.4. Kiểu trả về và checked exceptions được kiểm tra theo chữ ký đã chọn

Sau khi trình biên dịch chọn overload, kiểu kết quả và ngoại lệ kiểm tra (`checked exceptions`) được xác định từ khai báo phương thức được chọn trong ngữ cảnh kiểu tĩnh. Bạn không thể dựa vào kiểu trả về hay `throws` để phân biệt hai khai báo cùng danh sách tham số.

### 9.5. Quy tắc giới hạn của phương thức abstract vẫn áp dụng

Trong lớp, phương thức `abstract` không có thân và không thể đồng thời là `private`, `static` hay `final`, vì điều đó mâu thuẫn với yêu cầu phương thức có thể được lớp con hiện thực. Có thể overload một tên bằng **những phương thức concrete hợp lệ**, nhưng không biến cùng một chữ ký thành cả abstract lẫn concrete trong một lớp.

Constructor có thể được overload ngay cả trong abstract class, nhưng **constructor không phải phương thức abstract** và không thể được khai báo `abstract`.

## 10. Thiết kế API có overload abstract tốt

Một thiết kế hợp lý thường theo các bước:

1. Xác định hành vi chung, ví dụ `serialize(...)`, `parse(...)`, `render(...)`; chỉ tạo overload khi những tham số khác nhau có **ý nghĩa rõ ràng**.
2. Xác định đầu vào chính (canonical form) để tránh các lớp con phải lặp logic; chẳng hạn khai báo một phương thức abstract nhận đối tượng yêu cầu, còn overload concrete chuyển đổi từ `String` hoặc tham số đơn giản thành đối tượng yêu cầu.
3. Nếu nhiều overload đều trừu tượng, giải thích hợp đồng và **yêu cầu riêng** của từng chữ ký; lớp con phải duy trì các bất biến và hành vi mong đợi.
4. Dùng `@Override` khi hiện thực, kiểm tra visibility (`public` với interface), loại tham số chính xác và generic erasure.
5. Viết ví dụ với biến khai báo bằng **kiểu hợp đồng** (abstract class/interface), vì đây là cách mã gọi phổ biến và bộc lộ những overload mà người dùng API thực sự nhìn thấy.
6. Kiểm tra lời gọi biên giới: `null`, số nguyên literal, wrapper, varargs, phân cấp `Object`/`String` và các đối số có kiểu cha.

Cân nhắc đánh đổi: nhiều overload abstract có thể buộc mọi implementer hỗ trợ quá nhiều kiểu dữ liệu. Thay vào đó, một phương thức abstract cốt lõi và vài overload concrete/default đóng vai trò adapter thường giảm sự lặp lại.

## 11. Bài tập tự kiểm tra

**Câu 1.** Hai khai báo dưới đây có phải overload không?

```java
abstract int count(String text);
abstract int count(String text, boolean ignoreCase);
```

**Đáp án:** Có. Tên giống nhau, số tham số khác nhau. Cả hai có thể cùng là abstract, và lớp con concrete cần hiện thực các hợp đồng chưa có triển khai.

**Câu 2.** `abstract String read(int id)` và `abstract Object read(int id)` có hợp lệ trong cùng một lớp không?

**Đáp án:** Không. Danh sách tham số giống nhau, chỉ khác kiểu trả về. Đây không phải overload.

**Câu 3.** Một lớp cha abstract khai báo `handle(Number)`; lớp con chỉ định nghĩa `handle(Integer)`. Đã hiện thực hợp đồng chưa?

**Đáp án:** Chưa. Đó là overload, không phải override. Lớp con concrete vẫn phải cung cấp `handle(Number)` (hoặc kế thừa triển khai hợp lệ).

**Câu 4.** Trong ví dụ `StaticTypeDispatchDemo`, vì sao `asBase.accept("hello")` trả về `Object:hello`?

**Đáp án:** Kiểu tĩnh `Receiver` chỉ khai báo `accept(Object)`; overload `accept(String)` chỉ được giới thiệu ở `ReceiverImpl`. Trình biên dịch chọn chữ ký `accept(Object)`, sau đó JVM gọi phần override tương ứng của đối tượng.

**Câu 5.** `choose(5)` có thể chọn `choose(long)` dù tồn tại `choose(Integer)` không?

**Đáp án:** Có. Với `int` literal, nới rộng `int` → `long` được xem xét trước boxing `int` → `Integer` trong các giai đoạn áp dụng overload.

## Kết luận

- **Phương thức abstract có thể overload** nếu các khai báo cùng tên có danh sách tham số phân biệt hợp lệ.
- **Overload** chọn chữ ký để gọi; **override** cung cấp triển khai cho chữ ký đã được kế thừa. Lựa chọn overload phụ thuộc kiểu tĩnh lúc biên dịch, sau đó cơ chế phân phối động có thể chọn phần triển khai override lúc chạy.
- Lớp con concrete cần đáp ứng **từng** overload abstract chưa được hiện thực.
- Chú ý trường hợp chỉ khác kiểu trả về, `throws`, trùng erasure generic, varargs/mảng, `null` mơ hồ và boxing/widening.
- Một API tốt dùng overload có chủ đích, với hợp đồng nhất quán và các ví dụ gọi được qua abstract class/interface.
