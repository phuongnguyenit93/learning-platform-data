# Overload mới gây thay đổi lựa chọn phương thức hoặc lời gọi mơ hồ

Trong Java, một lời gọi phương thức được chọn khi biên dịch dựa trên kiểu tĩnh của receiver, kiểu tĩnh của đối số, các phương thức có thể truy cập và quy tắc overload resolution của ngôn ngữ. JVM không đợi đến lúc chạy để nhìn giá trị thực tế của đối số rồi chọn overload phù hợp. Sau khi compiler chọn được một chữ ký, bytecode ghi lại tham chiếu tới đúng tên và descriptor của phương thức đó.

Vì vậy, việc thêm một overload vào thư viện có thể làm thay đổi cách source code cũ được biên dịch lại. Một lời gọi trước đây hợp lệ có thể trở nên mơ hồ; một lời gọi vẫn biên dịch được có thể chuyển sang overload khác và tạo ra hành vi khác. Trong khi đó, binary đã biên dịch với phiên bản API cũ thường vẫn gọi đúng descriptor cũ nếu phương thức cũ được giữ lại.

Đây là một dạng source compatibility risk quan trọng khi nâng phiên bản thư viện hoặc framework. Nó cũng có thể xuất hiện khi một phiên bản JDK bổ sung overload mới vào API nền tảng, hoặc khi dự án thêm overload vào một class dùng chung mà nhiều module đang gọi.

## 1. Overload được chọn lúc biên dịch

### 1.1. Overloading và overriding là hai cơ chế khác nhau

**Overloading** là khai báo nhiều phương thức cùng tên trong một phạm vi nhưng có danh sách tham số khác nhau. Khác biệt có thể nằm ở số lượng tham số, kiểu tham số hoặc thứ tự kiểu tham số. Chỉ khác kiểu trả về không tạo thành overload hợp lệ.

```java
class MessageSender {
    void send(String text) { }
    void send(byte[] bytes) { }
    void send(String text, boolean urgent) { }
}
```

Compiler chọn overload phù hợp khi biên dịch từng lời gọi. Việc lựa chọn dựa trên kiểu tĩnh và các quy tắc áp dụng được, không dựa trên giá trị runtime của biến.

**Overriding** là class con cung cấp implementation thay thế cho một phương thức kế thừa với chữ ký tương thích. Khi chạy, dynamic dispatch chọn implementation override dựa trên class thực tế của object, nhưng chữ ký phương thức đã được xác định ở compile time.

Ví dụ:

```java
class Base {
    void handle(Object value) {
        System.out.println("Base Object");
    }
}

class Child extends Base {
    @Override
    void handle(Object value) {
        System.out.println("Child Object");
    }

    void handle(String value) {
        System.out.println("Child String");
    }
}

Base target = new Child();
target.handle("hello");
```

Compiler chỉ nhìn thấy các phương thức khả dụng qua kiểu tĩnh `Base`, nên chọn chữ ký `handle(Object)`. Khi chạy, JVM dispatch đến implementation `Child.handle(Object)`. Overload `Child.handle(String)` không được chọn vì kiểu tĩnh của receiver là `Base`.

Điểm phân biệt này quan trọng khi đánh giá thay đổi API: overload resolution là quyết định của compiler; overriding là lựa chọn implementation runtime cho descriptor đã được biên dịch.

### 1.2. Kiểu tĩnh của đối số quyết định overload

```java
class Converter {
    String convert(Object value) {
        return "object";
    }

    String convert(String value) {
        return "string";
    }
}

Converter converter = new Converter();
String text = "Java";
Object object = text;

converter.convert(text);   // convert(String)
converter.convert(object); // convert(Object)
```

Hai biến cùng chứa một object `String`, nhưng lời gọi thứ hai chọn `convert(Object)` vì kiểu khai báo của biến là `Object`. Compiler không dùng kiểu thực tế của object để quay lại chọn overload cụ thể hơn.

Do đó, khi API bổ sung overload, cần xem xét kiểu tĩnh tại các call site thực tế, bao gồm kiểu generic, kiểu của biểu thức lambda, kiểu trả về của method reference và kiểu suy luận từ `var`.

## 2. Compiler tìm overload theo những giai đoạn nào?

JLS quy định quá trình xác định phương thức áp dụng được (applicable method) rồi chọn phương thức cụ thể nhất (most specific method). Có thể hiểu tổng quát qua ba giai đoạn:

1. **Strict invocation:** tìm phương thức phù hợp mà không cần boxing/unboxing và không mở rộng varargs.
2. **Loose invocation:** nếu giai đoạn đầu không tìm được, cho phép các chuyển đổi như boxing, unboxing và một số chuyển đổi liên quan.
3. **Variable arity invocation:** nếu hai giai đoạn trước không có phương thức phù hợp, xét lời gọi varargs với số lượng đối số linh hoạt.

Compiler dừng ở giai đoạn đầu tiên tìm được tập phương thức áp dụng được, rồi chọn phương thức cụ thể nhất trong tập đó. Vì thế, không thể chỉ đếm số kiểu tham số có vẻ gần với đối số để đoán kết quả.

Ví dụ:

```java
class NumberHandler {
    void handle(long value) {
        System.out.println("long");
    }

    void handle(Integer value) {
        System.out.println("Integer");
    }
}

new NumberHandler().handle(10);
```

Với literal `10` có kiểu `int`, `handle(long)` có thể áp dụng bằng primitive widening ngay ở strict invocation. `handle(Integer)` cần boxing nên chỉ được xét ở giai đoạn loose invocation. Compiler chọn `handle(long)` ở giai đoạn đầu và không tiếp tục tìm overload ở giai đoạn sau.

Điều này cho thấy việc thêm một overload không nhất thiết làm thay đổi lựa chọn. Tác động phụ thuộc vào tập phương thức mới, kiểu tĩnh của đối số và giai đoạn mà phương thức trở thành applicable.

## 3. Thêm overload có thể khiến lời gọi cũ trở nên mơ hồ

### 3.1. Đối số `null` và hai kiểu không liên quan

Giả sử phiên bản thư viện đầu tiên có API:

```java
import java.util.Objects;

public class DestinationSender {
    public void send(String destination) {
        Objects.requireNonNull(destination);
        System.out.println("Send to text destination");
    }
}
```

Client gọi:

```java
DestinationSender sender = new DestinationSender();
sender.send(null);
```

Ở phiên bản đầu, chỉ có `send(String)`, nên lời gọi hợp lệ. Sau đó thư viện bổ sung overload:

```java
public void send(java.nio.file.Path destination) {
    Objects.requireNonNull(destination);
    System.out.println("Send to path destination");
}
```

`String` và `Path` đều là kiểu tham chiếu nhưng không có quan hệ subtype với nhau. Null literal có thể chuyển đổi sang cả hai kiểu. Không có phương thức nào cụ thể hơn phương thức còn lại, vì vậy source cũ khi biên dịch với phiên bản thư viện mới gặp lỗi:

```text
reference to send is ambiguous
  both method send(String) and method send(Path) match
```

Đây là source incompatibility: source từng biên dịch được nay không còn biên dịch được.

Có thể làm rõ ý định tại call site bằng cast:

```java
sender.send((String) null);
sender.send((Path) null);
```

Tuy nhiên, nếu `null` biểu thị một trạng thái nghiệp vụ, thiết kế tốt hơn có thể là dùng overload có tên khác, một value object hoặc một API biểu đạt rõ ý nghĩa thay vì yêu cầu mọi consumer phải thêm cast.

### 3.2. Overload nhận functional interface làm lambda mơ hồ

Lambda không có kiểu độc lập như một biến thông thường. Nó là poly expression và được kiểm tra theo kiểu functional interface mà compiler đang xét làm target type.

Phiên bản đầu của API:

```java
import java.util.function.Supplier;

public class TaskRunner {
    public void submit(Supplier<String> task) {
        System.out.println(task.get());
    }
}
```

Client gọi:

```java
new TaskRunner().submit(() -> "completed");
```

Sau đó API bổ sung:

```java
import java.util.concurrent.Callable;

public void submit(Callable<String> task) throws Exception {
    System.out.println(task.call());
}
```

`Supplier<String>` và `Callable<String>` đều là functional interface có function descriptor không nhận tham số và trả về `String`. Lambda `() -> "completed"` phù hợp với cả hai. Hai interface không phải subtype của nhau, nên compiler không có một overload cụ thể hơn duy nhất. Lời gọi cũ trở nên mơ hồ.

Client có thể chỉ định target type bằng biến trung gian hoặc cast:

```java
Supplier<String> supplier = () -> "completed";
new TaskRunner().submit(supplier);

new TaskRunner().submit((Supplier<String>) () -> "completed");
```

Việc thêm overload giữa các functional interface có shape giống nhau là rủi ro source compatibility đáng chú ý. Các trường hợp tương tự xuất hiện với `Runnable`, `Callable`, `Supplier`, `Function`, `Consumer`, callback interface tự định nghĩa và method reference.

### 3.3. Method reference cũng có thể mất khả năng phân giải duy nhất

Method reference được target-type theo overload đang xét. Ví dụ:

```java
class ActionRegistry {
    void register(java.util.function.Supplier<String> action) { }
}

class Actions {
    static String create() {
        return "created";
    }
}

new ActionRegistry().register(Actions::create);
```

Nếu API bổ sung một overload nhận functional interface khác cũng có function descriptor tương thích với `Actions::create`, compiler có thể không xác định được overload cụ thể nhất. Độ phức tạp tăng khi method reference trỏ tới chính một method đang overloaded, hoặc khi target interface có tham số/kiểu trả về khác nhau.

Khi thay đổi API nhận callback, hãy compile các call site mẫu có lambda và method reference, kể cả các call site không nằm trong repository của thư viện. Một API có thể compile nội bộ nhưng phá vỡ consumer source ở repository khác.

## 4. Thêm overload có thể làm thay đổi overload được chọn mà source vẫn compile

### 4.1. Overload mới cụ thể hơn

Phiên bản đầu:

```java
public class Formatter {
    public String format(Object value) {
        return "object:" + value;
    }
}
```

Client:

```java
Formatter formatter = new Formatter();
String result = formatter.format("Java");
```

Khi chỉ có `format(Object)`, compiler ghi nhận lời gọi tới descriptor `format(Object)`. Sau đó thư viện thêm:

```java
public String format(String value) {
    return "string:" + value;
}
```

Khi biên dịch lại client với thư viện mới, `String` cụ thể hơn `Object`, nên compiler chọn `format(String)`. Source vẫn compile, nhưng kết quả và side effect có thể thay đổi.

Ví dụ minh họa sự thay đổi:

| Phiên bản API | Overload được chọn cho biến kiểu `String` | Kết quả |
|---|---|---|
| Trước khi thêm overload | `format(Object)` | `object:Java` |
| Sau khi thêm overload và compile lại | `format(String)` | `string:Java` |

Nếu hai overload có logging, validation, caching, transaction hoặc quy tắc null khác nhau, thay đổi lựa chọn có thể gây regression nghiệp vụ dù compile và test đơn giản đều pass.

### 4.2. Overload varargs có thể thay đổi ý nghĩa của `null`

Phiên bản đầu:

```java
public class LoggerApi {
    public void log(Object value) {
        System.out.println("single value: " + value);
    }
}
```

Client:

```java
new LoggerApi().log(null);
```

Sau đó API thêm:

```java
public void log(Object... values) {
    System.out.println("number of values: " + values.length);
}
```

Trong quá trình overload resolution, khai báo varargs có thể được xem như một phương thức nhận một tham số mảng `Object[]` ở các giai đoạn fixed-arity. `Object[]` là subtype của `Object`, nên với null literal, overload varargs có thể cụ thể hơn `log(Object)`. Compiler có thể chọn overload varargs dưới dạng lời gọi fixed-arity và truyền `null` làm chính mảng, thay vì tạo mảng có một phần tử null.

Compiler thường phát cảnh báo về lời gọi varargs không chính xác kiểu. Nếu implementation truy cập `values.length`, chương trình có thể ném `NullPointerException`.

Client có thể làm rõ ý định:

```java
logger.log((Object) null);   // một đối tượng null
logger.log((Object[]) null); // chính mảng null
logger.log(new Object[]{null}); // mảng có một phần tử null
```

Ví dụ này đặc biệt quan trọng khi API có các overload nhận `Object`, `Object[]` hoặc varargs. Việc thêm overload có thể thay đổi cả method được gọi lẫn hình dạng đối số được truyền.

### 4.3. Overload kế thừa và thay đổi API của superclass

Overload có thể được thêm ở superclass hoặc interface mà client đang sử dụng. Khi source được biên dịch lại, tập method ứng viên có thể thay đổi dù class client không sửa. Ví dụ, một thư viện bổ sung overload vào base class dùng chung có thể ảnh hưởng đến các class con và call site thông qua kiểu base.

Khi phân tích, cần xem:

- Method được khai báo trực tiếp hay được kế thừa.
- Có method cùng tên trong superclass, interface hoặc class con không.
- Method mới là instance, static hay default method.
- Kiểu tĩnh của receiver tại call site là kiểu concrete hay interface/base type.
- Có generic type parameter hoặc bridge method được compiler tạo ra không.

Không suy luận từ tên method đơn thuần. Hãy kiểm tra toàn bộ tập method có thể truy cập tại call site và compile với đúng phiên bản API mới.

## 5. Generic inference và overload resolution

Generic method làm overload resolution phức tạp hơn vì compiler phải suy luận type argument, áp dụng bound và kiểm tra khả năng chuyển đổi. Việc thêm overload generic có thể làm thay đổi tập candidate hoặc khiến lời gọi trở nên không xác định duy nhất.

Ví dụ API ban đầu:

```java
class ValueReader {
    <T> T read(Object source) {
        return null;
    }
}
```

Sau đó thư viện bổ sung một overload khác có type parameter hoặc parameterized type phù hợp với call site. Compiler có thể suy luận type argument khác hoặc chọn overload khác. Nếu hai method có cùng erasure, Java còn có thể từ chối ngay khai báo vì name clash; generic không cho phép tạo overload chỉ khác nhau ở type argument bị xóa bởi type erasure.

Khi thay đổi API generic, kiểm tra:

- Type inference với argument có kiểu cụ thể, wildcard và raw type.
- Bound như `<T extends Number>` và quan hệ giữa các bound.
- Generic varargs và `@SafeVarargs`.
- Method invocation có target type từ assignment hoặc return context.
- Lambda/method reference là poly expression và có thể phụ thuộc target type.
- Erasure, bridge method và name clash.

Ví dụ, `List<String>` và `List<Integer>` không tạo được hai overload riêng vì sau type erasure đều có cùng erasure `List`. Muốn overload theo kiểu phần tử, API cần một thiết kế khác như tên method khác hoặc wrapper type riêng.

## 6. Overload resolution và các chuyển đổi kiểu

Khi đánh giá một thay đổi, hãy xem xét các kiểu chuyển đổi có thể làm một overload mới trở nên applicable:

| Chuyển đổi | Ví dụ | Ghi chú |
|---|---|---|
| Identity | `String` → `String` | Thường là lựa chọn ưu tiên trực tiếp |
| Primitive widening | `int` → `long` | Có thể được xét ở strict invocation |
| Reference widening | `String` → `Object` | Theo quan hệ subtype |
| Boxing | `int` → `Integer` | Được xét ở loose invocation |
| Unboxing | `Integer` → `int` | Có thể gây NPE nếu giá trị null khi thực thi |
| Widening reference sau boxing | `int` → `Integer` → `Number` | Có thể làm method generic/reference trở thành candidate |
| Variable arity | nhiều argument → mảng varargs | Chỉ xét ở giai đoạn variable arity nếu chưa có giai đoạn trước phù hợp |

Compiler không cộng điểm đơn giản cho mỗi kiểu chuyển đổi. Nó áp dụng các giai đoạn theo JLS và chọn phương thức cụ thể nhất. Vì thế, khi thêm overload, nên biên dịch các ví dụ thực tế thay vì chỉ dựa vào trực giác rằng “kiểu gần hơn sẽ được gọi”.

### 6.1. Primitive widening và boxing

```java
class NumericApi {
    void accept(long value) { }
    void accept(Integer value) { }
}

new NumericApi().accept(1);
```

Với literal `1` kiểu `int`, overload `accept(long)` có thể dùng primitive widening ở strict invocation. `accept(Integer)` cần boxing và chỉ được xét ở loose invocation. Do đó, overload `Integer` mới không nhất thiết được chọn chỉ vì nó có vẻ gần kiểu `int`.

Nếu thêm `accept(int)`, identity conversion sẽ làm method này được chọn. Nếu thêm `accept(Number)`, cần xét boxing và reference widening. Những thay đổi này có thể làm kết quả lựa chọn khác nhau tùy kiểu tĩnh của expression.

### 6.2. Null và kiểu tham chiếu

Null literal có thể chuyển đổi sang bất kỳ kiểu tham chiếu nào. Nếu một overload nhận subtype của overload khác, subtype thường cụ thể hơn. Nếu hai kiểu không liên quan, lời gọi có thể mơ hồ.

```java
void process(Object value) { }
void process(String value) { }

process(null); // process(String) vì String cụ thể hơn Object
```

Trong trường hợp:

```java
void process(String value) { }
void process(java.nio.file.Path value) { }

process(null); // ambiguous
```

Hai kiểu không có quan hệ subtype, nên compiler không thể chọn duy nhất.

### 6.3. Lambda và target typing

Lambda được kiểm tra theo functional interface mà compiler đang cân nhắc. Khi một API thêm overload nhận một functional interface khác có cùng shape, lời gọi lambda trước đó có thể trở nên mơ hồ.

```java
void run(java.util.function.Supplier<String> supplier) { }
void run(java.util.concurrent.Callable<String> callable) { }

run(() -> "done"); // ambiguous
```

Nếu API nhận callback, hãy cân nhắc dùng tên method khác để thể hiện semantics. `runAsync(Supplier<T>)` và `submit(Callable<T>)` rõ ràng hơn hai overload `run(...)` có functional interface gần giống nhau.

## 7. Source compatibility và binary compatibility

Một thay đổi overload cần được đánh giá trên hai góc nhìn.

**Source compatibility** là khả năng source cũ tiếp tục compile với API mới. Thêm overload có thể phá vỡ source compatibility vì:

- Lời gọi cũ trở nên ambiguous.
- Lời gọi vẫn compile nhưng chọn overload mới.
- Lambda hoặc method reference không còn có target type duy nhất.
- Generic inference chọn kiểu hoặc method khác.
- Varargs và null thay đổi hình dạng lời gọi.

**Binary compatibility** là khả năng bytecode đã biên dịch tiếp tục liên kết với API mới. Khi chỉ thêm một overload và giữ nguyên method cũ, binary cũ thường vẫn tham chiếu descriptor cũ. JVM không chạy lại overload resolution cho bytecode đã biên dịch.

Ví dụ, client đã biên dịch khi chỉ có `format(Object)` sẽ chứa tham chiếu tới method có descriptor tương ứng với `format(Ljava/lang/Object;)Ljava/lang/String;`. Sau khi thư viện thêm `format(String)`, bytecode cũ vẫn gọi descriptor `format(Object)` nếu method đó được giữ nguyên. Nếu compile lại source, compiler có thể chọn `format(String)`.

| Tình huống | Source cũ compile lại | Binary cũ chạy với thư viện mới |
|---|---|---|
| Thêm overload cụ thể hơn | Có thể chọn method khác | Thường tiếp tục gọi descriptor cũ |
| Thêm overload cùng mức phù hợp | Có thể trở nên ambiguous | Thường tiếp tục gọi descriptor cũ |
| Giữ method cũ nhưng thay implementation | Vẫn compile | Chạy implementation mới của method cũ |
| Xóa hoặc đổi descriptor method cũ | Có thể lỗi compile | Có thể lỗi linkage như `NoSuchMethodError` |

“Thường” ở đây giả định method cũ vẫn tồn tại, giữ descriptor và khả năng truy cập phù hợp, cùng các điều kiện binary compatibility khác. Thêm overload không bảo vệ được client nếu đồng thời xóa method cũ, thay đổi kiểu tham số/return type, thay đổi accessibility hoặc phá vỡ quan hệ kế thừa.

## 8. Vì sao thay đổi overload xuất hiện trong migration?

### 8.1. Nâng thư viện bên thứ ba

Nhà cung cấp có thể thêm overload để hỗ trợ kiểu dữ liệu mới, callback mới hoặc API mới. Ví dụ thư viện HTTP thêm overload nhận `Path`, `URI`, `InputStream` hoặc functional interface mới. Client source cũ có thể chứa `null`, lambda hoặc method reference và bị ảnh hưởng khi compile lại.

### 8.2. Nâng framework hoặc BOM

Framework có thể thêm overload vào class tiện ích, builder, callback registry, configuration API hoặc base class. Khi nâng BOM, nhiều module nhận version mới cùng lúc. Một call site không thay đổi có thể chọn overload khác do tập method đã thay đổi.

### 8.3. Nâng JDK

API nền tảng Java có thể bổ sung method overload hoặc interface/default method mới. Khi compiler release mới nhìn thấy API mới, source có thể chọn method khác. Khi vẫn target runtime cũ, dùng `--release` đúng mức có thể ngăn source tham chiếu API không có trong runtime đó. Nếu chuyển runtime hẳn lên phiên bản mới, cần đánh giá source compatibility của các API JDK mà ứng dụng gọi.

### 8.4. Nâng compiler hoặc source level

Compiler mới có thể triển khai các quy tắc ngôn ngữ mới, cải thiện type inference hoặc nhận biết thêm kiểu biểu thức. Khi source level thay đổi, một lời gọi có thể được phân tích theo quy tắc khác hoặc nhận target typing mới. Cần kiểm tra cả thay đổi trong JLS và release notes của compiler.

### 8.5. Thay đổi API nội bộ của dự án

Một nhóm có thể thêm overload vào service, utility hoặc base class dùng chung để hỗ trợ thêm kiểu đầu vào. Nếu API đó được nhiều module gọi, thay đổi nhỏ có thể gây lỗi trên các module khác mà tác giả không trực tiếp biên dịch. Điều này thường xảy ra trong repository multi-module hoặc thư viện nội bộ dùng chung.

## 9. Cách phát hiện overload resolution thay đổi

### 9.1. Tìm các call site nhạy cảm

Ưu tiên rà soát các lời gọi có:

- Null literal: `method(null)`.
- Lambda không khai báo kiểu tham số rõ ràng: `method(x -> ...)` hoặc `method(() -> ...)`.
- Method reference: `method(Type::name)` hoặc `method(object::name)`.
- Varargs: lời gọi có số lượng đối số biến đổi hoặc null ở vị trí cuối.
- Generic method: type inference, wildcard, raw type và overloaded generic method.
- Primitive/wrapper: boxing, unboxing và primitive widening.
- Kiểu receiver là superclass/interface nhưng object thực tế thuộc subclass.
- API nhận `Object`, `CharSequence`, `Serializable`, `Comparable` hoặc các interface không liên quan.

Tìm kiếm bằng IDE hoặc code search có thể khoanh vùng call site, nhưng không thay thế compile với version dependency mới. Một biểu thức lambda có thể chỉ trở nên ambiguous khi classpath mới được áp dụng.

### 9.2. Compile source cũ với API mới

Giữ một tập source fixture hoặc consumer sample đại diện cho cách API được sử dụng. Biên dịch chúng với version thư viện cũ và mới, cùng JDK/source level đã chốt. So sánh:

- Lời gọi nào compile trước đây nhưng lỗi ở phiên bản mới.
- Lời gọi nào chuyển sang overload khác.
- Lời gọi lambda/method reference nào trở nên ambiguous.
- Warning mới nào xuất hiện, nhất là varargs và unchecked conversion.
- Method descriptor mà compiler ghi vào bytecode.

Có thể dùng `javap -c -s` để quan sát lời gọi đã biên dịch:

```bash
javap -classpath build/classes -c -s com.example.Client
```

Output hiển thị instruction invocation và descriptor của method được gọi. So sánh output khi compile cùng source với hai version API giúp xác nhận compiler đã chọn overload nào.

### 9.3. Chạy regression test cho hành vi, không chỉ compile

Khi overload mới thay đổi lựa chọn nhưng source vẫn compile, test compile-only sẽ không phát hiện sự thay đổi semantics. Hãy kiểm tra:

- Kết quả trả về và exception.
- Validation và xử lý null.
- Logging, audit và metric.
- Transaction, retry, timeout và side effect.
- Chọn serializer/formatter/converter nào.
- Callback được gọi đồng bộ hay bất đồng bộ, số lần gọi và thứ tự.
- Overload mới có cách xử lý resource/lifecycle khác overload cũ không.

Nếu API được dùng bởi nhiều consumer, cần có contract test hoặc consumer compilation test cho các cách gọi quan trọng.

## 10. Thiết kế API để giảm rủi ro khi thêm overload

Nhà phát triển API có thể giảm source compatibility risk ngay từ thiết kế.

### 10.1. Tránh overload nhận các kiểu không liên quan khi null là đầu vào hợp lệ

Nếu hai overload nhận `String` và `Path`, null literal dễ gây ambiguity. Có thể cân nhắc:

```java
void sendToName(String name) { }
void sendToPath(Path path) { }
```

Tên method khác nhau giúp consumer thể hiện ý định và không cần ép kiểu chỉ để vượt qua compiler.

### 10.2. Tránh overload functional interface có shape tương tự

Thay vì:

```java
void execute(Supplier<String> action) { }
void execute(Callable<String> action) throws Exception { }
```

có thể thiết kế tên method biểu đạt hợp đồng khác nhau:

```java
void executeValue(Supplier<String> action) { }
void executeChecked(Callable<String> action) throws Exception { }
```

Tên riêng giúp tránh lambda/method reference trở nên ambiguous và làm rõ semantics cho người dùng API.

### 10.3. Thận trọng khi thêm overload varargs

Overload varargs có thể tương tác với overload mảng và overload nhận `Object`. Hãy thử các call site có null, mảng, một đối số và nhiều đối số. Nếu cần phân biệt “một giá trị null” với “mảng null”, nên cung cấp API rõ ràng hoặc dùng wrapper type.

### 10.4. Không thêm overload chỉ để thay đổi semantics ngầm

Nếu method cũ có hành vi đã được consumer dựa vào, không nên thêm overload cụ thể hơn với cùng tên chỉ để thay đổi cách xử lý kiểu dữ liệu. Có thể dùng method mới với tên rõ ràng, builder option hoặc một versioned API.

### 10.5. Giữ method cũ và migration path

Khi thay API, giữ method cũ trong giai đoạn chuyển tiếp nếu có thể, đánh dấu deprecated với hướng dẫn thay thế, thêm test tương thích và ghi rõ thời điểm dự kiến loại bỏ. Việc giữ method cũ giúp binary consumer tiếp tục liên kết, nhưng source consumer vẫn có thể gặp ambiguity nếu overload mới xung đột. Cần đánh giá call site trước khi phát hành.

## 11. Chiến lược sửa call site khi overload mới gây vấn đề

Nếu thư viện mới là bắt buộc, consumer có thể làm rõ kiểu đầu vào:

**Dùng biến có kiểu tường minh:**

```java
String destination = null;
sender.send(destination);
```

**Dùng cast để chỉ định overload:**

```java
sender.send((String) null);
```

**Khai báo target type cho lambda:**

```java
Supplier<String> task = () -> "done";
runner.submit(task);
```

**Dùng tên method mới nếu API cung cấp:**

```java
runner.submitCallable(() -> loadValue());
```

**Chuyển varargs thành mảng hoặc phần tử có kiểu rõ ràng:**

```java
logger.log((Object) null);
logger.log(new Object[]{null});
```

Cast là cách sửa cục bộ, nhưng cần dùng đúng kiểu mà nghiệp vụ mong muốn. Không nên cast bừa chỉ để build pass vì điều đó có thể buộc compiler chọn một overload có semantics khác. Hãy thêm test khẳng định method/hành vi được mong đợi.

## 12. Phân tích overload thay đổi trong dependency/framework migration

Khi nâng version thư viện, cần lưu API diff giữa version cũ và mới. Các công cụ như japicmp hoặc Revapi có thể hỗ trợ phát hiện thay đổi API binary/source ở mức khai báo. Tuy nhiên, việc thêm overload thường là binary compatible nếu method cũ vẫn giữ nguyên, nên báo cáo binary API diff có thể không coi đó là breaking change.

Vì vậy, quy trình đánh giá nên có hai lớp:

1. **API surface diff:** phát hiện method mới, method bị xóa, thay đổi modifier, generic signature, inheritance và descriptor.
2. **Consumer source compilation:** compile các call site đại diện bằng version API mới để phát hiện ambiguity hoặc đổi lựa chọn overload.

Với thư viện nội bộ, nên duy trì một consumer compatibility fixture gồm các cách gọi thường dùng: null, lambda, method reference, primitive/wrapper, generic, varargs và receiver có kiểu base. Mỗi lần thêm overload, chạy fixture này như một cổng kiểm tra.

Nếu không có consumer fixture, ít nhất hãy tìm kiếm call site có cùng tên method trong repository và compile toàn bộ module phụ thuộc. Nhưng với thư viện được dùng ngoài repository, cần thông báo migration note cho consumer vì nhóm không thể compile thay họ.

## 13. Ví dụ đầy đủ: overload `null` làm source cũ không compile

Giả sử version 1 của thư viện có:

```java
package com.example.api;

public class DestinationApi {
    public String resolve(String value) {
        return "text:" + value;
    }
}
```

Consumer:

```java
DestinationApi api = new DestinationApi();
String result = api.resolve(null);
```

Consumer compile thành công và bytecode chứa descriptor nhận `String`. Version 2 bổ sung:

```java
public String resolve(java.net.URI value) {
    return "uri:" + value;
}
```

Hai kiểu `String` và `URI` không có quan hệ subtype. Khi compile lại consumer với version 2, lời gọi `resolve(null)` trở nên ambiguous.

Một phương án sửa consumer:

```java
String result = api.resolve((String) null);
```

Nhưng nếu `null` vốn không phải input hợp lệ, API nên xác định hợp đồng null và consumer nên tránh truyền null. Nếu null có ý nghĩa nghiệp vụ, method mới nên dùng tên khác hoặc wrapper type để biểu đạt rõ loại đích.

Đối với binary consumer đã compile với version 1, nếu version 2 giữ `resolve(String)` cùng descriptor và accessibility, bytecode cũ tiếp tục liên kết tới method đó. Điều này cho thấy binary compatibility có thể được giữ trong khi source compatibility bị phá vỡ.

## 14. Ví dụ đầy đủ: lambda trở nên ambiguous sau khi thêm overload

Version 1:

```java
public class AsyncApi {
    public void execute(java.util.function.Supplier<String> action) {
        System.out.println(action.get());
    }
}
```

Consumer:

```java
new AsyncApi().execute(() -> "OK");
```

Version 2 thêm:

```java
public void execute(java.util.concurrent.Callable<String> action)
        throws Exception {
    System.out.println(action.call());
}
```

Lambda không có tham số và trả về `String` có thể phù hợp với cả `Supplier<String>` và `Callable<String>`. Hai functional interface không có quan hệ subtype, do đó compiler không thể chọn overload cụ thể nhất duy nhất.

Consumer có thể dùng:

```java
Supplier<String> action = () -> "OK";
new AsyncApi().execute(action);
```

Nhưng về thiết kế API, tách tên method sẽ dễ dùng và ổn định hơn:

```java
executeValue(() -> "OK");
executeChecked(() -> readWithCheckedException());
```

## 15. Checklist khi thêm overload hoặc nâng thư viện

- [ ] Đã lập danh sách method overload được thêm, sửa hoặc kế thừa từ version mới.
- [ ] Đã kiểm tra call site truyền null literal hoặc biến có kiểu null.
- [ ] Đã kiểm tra lambda và method reference theo target functional interface.
- [ ] Đã kiểm tra generic inference, wildcard, raw type và type erasure.
- [ ] Đã kiểm tra primitive widening, boxing/unboxing và varargs.
- [ ] Đã xác nhận kiểu tĩnh của receiver và argument tại call site quan trọng.
- [ ] Đã compile consumer fixture với cả version API cũ và mới.
- [ ] Đã so sánh bytecode descriptor bằng `javap` khi cần xác nhận overload được chọn.
- [ ] Đã chạy regression test để phát hiện đổi behavior dù source vẫn compile.
- [ ] Đã phân biệt source compatibility với binary compatibility.
- [ ] Đã xem xét API design thay thế như method name riêng hoặc wrapper type.
- [ ] Đã cập nhật migration note cho consumer ngoài repository nếu cần.

Việc thêm overload có thể giữ nguyên binary compatibility nhưng vẫn làm source cũ không compile hoặc chuyển sang hành vi khác sau khi compile lại. Đánh giá API change vì thế phải bao gồm cả source consumer và runtime behavior, đặc biệt với `null`, lambda, method reference, generic và varargs. Khi API được thiết kế rõ semantics, có consumer fixture và được kiểm tra với version mới, nhóm có thể phát hiện sớm các thay đổi overload trước khi chúng lan sang các module hoặc khách hàng sử dụng thư viện.
