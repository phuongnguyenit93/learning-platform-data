# 7.7 Gắn receiver hoặc đối số tham chiếu bằng bindTo

`MethodHandle.bindTo(Object x)` tạo một **method handle mới** bằng cách gắn trước một giá trị tham chiếu `x` vào **tham số đầu tiên** của method handle hiện tại. Từ lần gọi tiếp theo, người gọi không phải truyền tham số đó nữa. Đây là kỹ thuật thường dùng để gắn sẵn *receiver* cho phương thức instance; nó cũng dùng được để gắn đối số tham chiếu đầu tiên của phương thức static hoặc của một handle đã được biến đổi.

Điều cần nhớ ngay: **`bindTo` gắn tham số đầu tiên có kiểu tham chiếu**, không phải cơ chế chỉ dành riêng cho receiver. Nếu tham số đầu tiên có kiểu nguyên thủy như `int`, `bindTo` không áp dụng trực tiếp. Nếu cần gắn đối số ở vị trí bất kỳ hoặc gắn primitive, dùng `MethodHandles.insertArguments`.

Bài này sử dụng Java 17+ và đặt `bindTo` trong ngữ cảnh `MethodHandle`, `MethodType`, `MethodHandles.Lookup`, `invokeExact` và các phép biến đổi handle.

## 1. Hình dung về việc gắn tham số

Giả sử có phương thức instance:

~~~java
class Greeter {
    String greet(String name) {
        return "Hello " + name;
    }
}
~~~

Một handle được tạo bằng `findVirtual` để gọi `Greeter.greet(String)` sẽ có kiểu tương đương:

~~~text
Trước khi bind:
  MethodHandle: (Greeter, String) -> String
                 receiver  name

Gắn receiver bằng bindTo(greeter):
  MethodHandle: (String) -> String
                 name

Khi gọi handle mới, receiver đã được giữ bên trong handle.
~~~

Phương thức nguồn chỉ khai báo một tham số `name`. Nhưng **handle chưa gắn** cho lời gọi virtual cần receiver như tham số đầu tiên; `bindTo(greeter)` loại tham số receiver khỏi **chữ ký gọi của handle mới**. Đây có thể xem như một dạng *partial application*: cố định một đầu vào, thu được hàm còn lại ít một đối số.

Với phương thức static:

~~~java
static String surround(String prefix, String content) {
    return prefix + content;
}
~~~

Handle ban đầu có kiểu `(String, String)String` và **không có receiver**. `bindTo("prefix: ")` vẫn hợp lệ vì tham số đầu tiên `prefix` là tham chiếu `String`; handle mới có kiểu `(String)String`. Do đó, ý nghĩa của tham số được gắn phụ thuộc vào **chữ ký handle**, không phụ thuộc tên phương thức.

## 2. Hợp đồng chính xác của MethodHandle.bindTo

Cú pháp:

~~~java
MethodHandle bound = original.bindTo(value);
~~~

Kết quả và điều kiện:

1. `original.type()` phải có **ít nhất một tham số**. Tham số ở vị trí `0` phải là **reference type** như `String.class`, `Object.class` hoặc một class/interface khác, không được là primitive.
2. `value` phải chuyển được sang lớp tham số đầu tiên bằng phép kiểm tra kiểu tham chiếu. Nếu không tương thích, `ClassCastException` có thể phát sinh **ngay khi gắn**.
3. Handle trả về bỏ **đúng tham số đầu tiên** trong danh sách tham số; kiểu trả về và thứ tự các tham số còn lại được giữ nguyên. Ví dụ từ `(Greeter,String,int)String` sang `(String,int)String` sau khi gắn một `Greeter`.
4. **Handle gốc không bị sửa.** `bindTo` trả một handle khác. Các lời gọi đến `original` vẫn phải cung cấp đủ tham số như trước.
5. Giá trị đã gắn được lưu như một **tham chiếu tới đối tượng**, không có nghĩa là tạo bản sao đối tượng. Nếu receiver thay đổi trạng thái, các lần gọi sau của handle đã gắn có thể nhìn thấy thay đổi đó.
6. `bindTo` không gọi phương thức đích ngay. Việc thực thi phương thức và các ngoại lệ từ phần thân phương thức xảy ra khi `invokeExact`, `invoke` hoặc một đường gọi handle khác được thực hiện.

Nếu một handle không có tham số hoặc tham số đầu tiên là primitive, gọi `bindTo` gây `IllegalArgumentException`. Kiểu tham chiếu không phù hợp gây `ClassCastException` khi bind. Đừng nhầm hai nhóm lỗi này với `WrongMethodTypeException` xuất hiện ở thời điểm **gọi** một handle bằng chữ ký call site không đúng.

Với `null`: vì `bindTo` làm việc với tham chiếu, giá trị `null` có thể được gắn khi tham số đầu là kiểu tham chiếu. Tuy nhiên, nếu đó là receiver của phương thức instance cần truy cập đối tượng, lời gọi thực tế thường dẫn tới `NullPointerException`. Cũng không nên sử dụng `bindTo(null)` để diễn đạt một receiver hợp lệ.

## 3. Lấy đúng MethodHandle bằng Lookup trước khi bind

`bindTo` là phương thức của `MethodHandle`, vì vậy trước tiên cần có handle hợp lệ. Với một phương thức instance:

~~~java
class Greeter {
    public String greet(String name) {
        return "Hello " + name;
    }
}

// Minh họa; đặt trong phương thức có xử lý ReflectiveOperationException:
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodType declaredType =
        MethodType.methodType(String.class, String.class);
MethodHandle handle =
        lookup.findVirtual(Greeter.class, "greet", declaredType);
~~~

Lúc **tìm phương thức** bằng `findVirtual`, `declaredType` mô tả kiểu của phương thức được khai báo: `(String)String`. Khi **nhận handle**, `handle.type()` là `(Greeter,String)String` vì handle cần thêm receiver `Greeter` ở đầu.

Tiếp theo:

~~~java
Greeter greeter = new Greeter();
MethodHandle bound = handle.bindTo(greeter);

// Trước: handle.type() có 2 tham số, gồm Greeter và String.
// Sau:   bound.type() có 1 tham số, String.
String result = (String) bound.invokeExact("Ada");
~~~

Dòng `(String) bound.invokeExact("Ada")` có ý nghĩa về kiểu: `invokeExact` là lời gọi *signature-polymorphic*, nên **kiểu của đối số lẫn kiểu kết quả mà compiler suy ra ở call site** phải khớp chính xác với `bound.type()`. Gán vào biến `Object` thay vì ép `(String)` sẽ yêu cầu kiểu trả về `Object`; với handle thực tế trả `String`, `invokeExact` sẽ ném `WrongMethodTypeException`.

Nếu có thể chấp nhận chuyển đổi kiểu được `asType` hỗ trợ, `invoke` linh hoạt hơn `invokeExact`. Nhưng cả hai đều gọi handle **sau khi receiver đã được gắn**, không cần truyền receiver lần nữa.

### Đọc MethodType để tự kiểm tra

Đừng chỉ đoán kiểu handle qua chữ ký source. Hãy kiểm tra:

~~~java
System.out.println(handle.type().parameterCount());  // 2
System.out.println(bound.type().parameterCount());   // 1
System.out.println(bound.type().parameterType(0));   // class java.lang.String
System.out.println(bound.type().returnType());       // class java.lang.String
~~~

Bốn dòng trên là **đoạn minh họa** cần các biến `handle` và `bound` phù hợp. `parameterCount()`, `parameterType(i)` và `returnType()` trả thông tin từ `MethodType` của **handle hiện tại**. Đây là cách gỡ lỗi hiệu quả hơn suy luận từ tên method gốc khi handle đã qua nhiều adapter.

## 4. Ví dụ đầy đủ 1: bind receiver và đối số tham chiếu static

Tạo file **BindToDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Locale;

public class BindToDemo {
    static class Greeter {
        private final String prefix;

        Greeter(String prefix) {
            this.prefix = prefix;
        }

        public String greet(String name) {
            return prefix + " " + name;
        }
    }

    static class LoudGreeter extends Greeter {
        LoudGreeter(String prefix) {
            super(prefix);
        }

        @Override
        public String greet(String name) {
            return super.greet(name).toUpperCase(Locale.ROOT);
        }
    }

    public static String decorate(String prefix, String value) {
        return prefix + "[" + value + "]";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType oneString =
                MethodType.methodType(String.class, String.class);

        MethodHandle unbound = lookup.findVirtual(
                Greeter.class, "greet", oneString);
        Greeter hello = new Greeter("Hello");

        System.out.println("unbound parameters: " +
                unbound.type().parameterCount());
        System.out.println("first parameter: " +
                unbound.type().parameterType(0).getSimpleName());

        String direct = (String) unbound.invokeExact(hello, "An");
        System.out.println("unbound call: " + direct);

        MethodHandle bound = unbound.bindTo(hello);
        System.out.println("bound parameters: " +
                bound.type().parameterCount());

        String greeting = (String) bound.invokeExact("Binh");
        System.out.println("bound call: " + greeting);

        // unbound vẫn còn kiểu gốc, cần truyền receiver.
        Greeter welcome = new Greeter("Welcome");
        String unchanged =
                (String) unbound.invokeExact(welcome, "Minh");
        System.out.println("original unchanged: " + unchanged);

        // bindTo giữ đúng receiver instance, virtual dispatch vẫn hoạt động.
        Greeter loud = new LoudGreeter("Hello");
        MethodHandle loudBound = unbound.bindTo(loud);
        String shouted = (String) loudBound.invokeExact("Mai");
        System.out.println("virtual dispatch: " + shouted);

        // static method không có receiver; bindTo gắn đối số đầu.
        MethodHandle decorate = lookup.findStatic(
                BindToDemo.class, "decorate",
                MethodType.methodType(
                        String.class, String.class, String.class));
        MethodHandle withPrefix = decorate.bindTo("tag");

        System.out.println("static parameters after bind: " +
                withPrefix.type().parameterCount());
        String tagged = (String) withPrefix.invokeExact("OK");
        System.out.println("static bound: " + tagged);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BindToDemo.java
java BindToDemo
~~~

Stdout:

~~~text
unbound parameters: 2
first parameter: Greeter
unbound call: Hello An
bound parameters: 1
bound call: Hello Binh
original unchanged: Welcome Minh
virtual dispatch: HELLO MAI
static parameters after bind: 1
static bound: tag[OK]
~~~

**Vì sao từng kết quả đúng?**

- `unbound.type()` có hai tham số: receiver `Greeter` và tên `String`. `getSimpleName()` của kiểu tham số đầu là `Greeter`.
- `unbound.invokeExact(hello, "An")` nhận receiver tường minh; `bound.invokeExact("Binh")` chỉ nhận tên vì `hello` đã được gắn.
- `unbound` vẫn được gọi được với `welcome` sau khi đã tạo `bound`: `bindTo` không sửa handle gốc.
- `LoudGreeter` override `greet`. Handle `findVirtual` vẫn gọi theo virtual dispatch của receiver thực, kể cả khi receiver đã được gắn vào handle. Vì vậy kết quả được in hoa.
- `decorate` là static method có chữ ký `(String,String)String`. `bindTo("tag")` gắn tham số `prefix`, dù phương thức này **không có `this`**; handle mới có đúng một tham số `value`.

Ví dụ này cũng phân biệt rõ hai điều: **bind receiver** là trường hợp rất phổ biến, còn **bind leading reference argument** mới là hợp đồng tổng quát của `bindTo`.

## 5. bindTo khác insertArguments như thế nào?

`MethodHandles.insertArguments(target, pos, values...)` cũng tạo handle mới với các giá trị được gắn trước, nhưng tổng quát hơn:

| Tiêu chí | `handle.bindTo(value)` | `MethodHandles.insertArguments(target, pos, values...)` |
| --- | --- | --- |
| Vị trí có thể gắn | Chỉ tham số đầu tiên (index 0) | Vị trí `pos` được chỉ định |
| Số giá trị trong một lời gọi | Một giá trị | Có thể gắn liên tiếp nhiều giá trị |
| Kiểu giá trị có thể gắn | Chỉ khi tham số đầu là reference type | Có thể là reference hoặc primitive (qua boxing của API varargs) |
| Đối tượng kết quả | Handle mới | Handle mới |
| Handle gốc | Không bị thay đổi | Không bị thay đổi |
| Tình huống điển hình | Gắn receiver hoặc leading reference argument | Gắn tham số ở giữa, cuối, nhiều đối số, hoặc primitive |

Với method static:

~~~java
static String surround(String left, String content, String right) {
    return left + content + right;
}
~~~

Handle của nó có kiểu `(String,String,String)String`. Ta có thể cố định bên phải rồi cố định bên trái:

~~~java
// Giả sử "surround" là MethodHandle tìm bằng findStatic tương ứng:
MethodHandle withClose =
        MethodHandles.insertArguments(surround, 2, "]");
MethodHandle withBrackets = withClose.bindTo("[");
String result = (String) withBrackets.invokeExact("text"); // [text]
~~~

**Cách đọc vị trí:** `insertArguments(surround, 2, "]")` gắn **tham số thứ ba** của handle gốc (index 2), tạo handle `(String,String)String`. Sau đó `bindTo("[")` gắn tham số đầu `left` của handle mới, tạo `(String)String`. Ở đây không có receiver; hai giá trị gắn được dùng để tạo hàm chỉ còn nhận phần nội dung.

### Primitive: vì sao bindTo không đủ?

Một handle `(int,int)int` không thể `bindTo(7)` dù Java tự autobox `7` thành `Integer` khi gọi `bindTo(Object)`: **tham số đầu của handle vẫn là primitive `int`**, nên `bindTo` ném `IllegalArgumentException`.

Thay vào đó:

~~~java
// add có MethodType (int,int)int:
MethodHandle addSeven =
        MethodHandles.insertArguments(add, 0, 7);
int answer = (int) addSeven.invokeExact(5); // 12
~~~

`insertArguments` xử lý việc đưa giá trị primitive từ argument list và kiểm tra kiểu phù hợp của từng slot. `addSeven.type()` trở thành `(int)int`.

Để gắn nhiều đối số, ví dụ `(String,int,String)String`, có thể cung cấp nhiều giá trị liên tiếp sau `pos`, nhưng phải nhớ các tham số phía sau sẽ **đổi vị trí** trong handle đã biến đổi. Khi chuỗi adapter dài, thường nên đặt tên biến khác nhau cho từng bước và kiểm tra `type()`.

## 6. Ví dụ đầy đủ 2: state của receiver, vị trí gắn và lỗi primitive

Tạo file **BindingDetailsDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class BindingDetailsDemo {
    static class Counter {
        private int calls;

        public String next(String label) {
            calls++;
            return label + ":" + calls;
        }
    }

    public static String surround(
            String left, String content, String right) {
        return left + content + right;
    }

    public static int add(int a, int b) {
        return a + b;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle unboundCounter = lookup.findVirtual(
                Counter.class,
                "next",
                MethodType.methodType(String.class, String.class));

        Counter counter = new Counter();
        MethodHandle count = unboundCounter.bindTo(counter);
        String first = (String) count.invokeExact("run");
        String second = (String) count.invokeExact("run");
        System.out.println("counter first: " + first);
        System.out.println("counter second: " + second);

        MethodHandle surroundHandle = lookup.findStatic(
                BindingDetailsDemo.class, "surround",
                MethodType.methodType(
                        String.class,
                        String.class, String.class, String.class));

        MethodHandle closeFixed =
                MethodHandles.insertArguments(surroundHandle, 2, "]");
        MethodHandle brackets = closeFixed.bindTo("[");
        String wrapped = (String) brackets.invokeExact("value");
        System.out.println("brackets: " + wrapped);

        MethodHandle addHandle = lookup.findStatic(
                BindingDetailsDemo.class, "add",
                MethodType.methodType(int.class, int.class, int.class));

        try {
            addHandle.bindTo(7);
            System.out.println("unreachable");
        } catch (IllegalArgumentException expected) {
            System.out.println("primitive bindTo: IllegalArgumentException");
        }

        MethodHandle addSeven =
                MethodHandles.insertArguments(addHandle, 0, 7);
        int sum = (int) addSeven.invokeExact(5);
        System.out.println("insertArguments: " + sum);

        try {
            unboundCounter.bindTo("not a Counter");
            System.out.println("unreachable");
        } catch (ClassCastException expected) {
            System.out.println("wrong receiver: ClassCastException");
        }

        System.out.println("original params: " +
                unboundCounter.type().parameterCount());
        System.out.println("bound params: " +
                count.type().parameterCount());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BindingDetailsDemo.java
java BindingDetailsDemo
~~~

Stdout:

~~~text
counter first: run:1
counter second: run:2
brackets: [value]
primitive bindTo: IllegalArgumentException
insertArguments: 12
wrong receiver: ClassCastException
original params: 2
bound params: 1
~~~

Phân tích:

1. `count` đã giữ **tham chiếu tới đúng đối tượng `counter`**. Hai lần gọi làm tăng cùng field `calls`; `bindTo` không sao chép đối tượng và không biến method có state thành hàm thuần.
2. Với `surround`, gắn `right` bằng `insertArguments` rồi gắn `left` bằng `bindTo` tạo hàm còn một đối số `content`.
3. `addHandle` có tham số đầu `int`. Gọi `bindTo(7)` lỗi ngay ở bước tạo handle vì `int` không phải reference type; đây là `IllegalArgumentException`, không phải `WrongMethodTypeException`.
4. `insertArguments(addHandle, 0, 7)` có thể gắn primitive; handle mới nhận một `int` và trả `int`.
5. `unboundCounter` đòi receiver thuộc `Counter`, nên cố gắn một `String` gây `ClassCastException` ngay lúc bind.
6. `unboundCounter` vẫn có hai tham số sau tất cả lần biến đổi; `count` chỉ còn một tham số.

Nếu không cần xử lý đối tượng có trạng thái, bạn cũng có thể bind một tham chiếu bất biến như `String`. Điểm cốt lõi vẫn là **giá trị tham chiếu đầu tiên được gắn**, không phải kết quả lời gọi được tính trước.

## 7. Quan hệ giữa bindTo, invokeExact, invoke, asType và method reference

### bindTo thay đổi kiểu handle; không gọi sẵn phương thức

Giả sử `MethodHandle mh` có kiểu `(Greeter,String)String`, còn `Greeter greeter` là receiver hợp lệ:

~~~java
MethodHandle bound = mh.bindTo(greeter);
// bound.type() == (String)String (ý nghĩa chữ ký)
String value = (String) bound.invokeExact("Ada");
~~~

`bindTo` **không tính trước** `greet("Ada")`, bởi lúc bind chưa biết tên `"Ada"`. Nó chỉ cố định receiver. Khi gọi handle mới, body của method vẫn được thực thi theo trạng thái hiện tại.

### asType thích nghi chữ ký, bindTo cố định giá trị

`bound.asType(MethodType.methodType(Object.class, Object.class))` tạo adapter có kiểu `(Object)Object` để caller có thể gọi `invokeExact((Object) "Ada")` và nhận `Object`. Nó không gắn một receiver hay argument. Ngược lại, `bindTo` loại đi một tham số bằng cách đưa **giá trị cụ thể** vào handle.

Nếu một tham số đầu vốn là primitive, có thể tạo adapter nhận `Integer`/`Object` để phục vụ nhu cầu API nhất định, nhưng điều đó có thể thêm boxing/unboxing và kiểm tra ở runtime. Khi mục tiêu chỉ là cố định primitive, `insertArguments` thường dễ đọc hơn.

### invoke và invokeExact đều dùng kiểu handle sau khi bind

Một lời gọi sai thường gặp là tiếp tục truyền receiver đã được bind:

~~~java
// Chỉ minh họa lỗi; bound có kiểu (String)String.
// String wrong = (String) bound.invokeExact(greeter, "Ada");
~~~

Lời gọi này không đúng vì handle chỉ còn một tham số. Cần gọi `bound.invokeExact("Ada")` với return type phù hợp. Nếu dùng `invoke`, JVM có thể thử thích nghi **kiểu** của các tham số còn lại, nhưng **không tự bù lại** tham số receiver đã bị loại bỏ.

### Gần với method reference, nhưng không giống hệt

Về ý tưởng, `greeter::greet` là method reference đã gắn receiver để chuyển thành một functional interface phù hợp, còn `Greeter::greet` dạng unbound có thể cần receiver làm tham số đầu của functional interface. `bindTo` thể hiện ý tưởng “gắn receiver” tương tự nhưng hoạt động ở tầng `java.lang.invoke`, nơi chữ ký được mô tả bằng `MethodType` và lời gọi dùng `MethodHandle`. Đừng thay thế bừa các API này: cú pháp lambda/method reference cho compiler kiểm tra kiểu chức năng trực tiếp; handle thích hợp khi đích gọi được chọn hoặc biến đổi ở runtime.

## 8. bindTo có ảnh hưởng tới quyền truy cập và virtual dispatch không?

**Lookup và quyền truy cập:** `MethodHandles.Lookup` xác minh quyền khi tạo handle ban đầu. `bindTo` không cấp thêm quyền truy cập vào method private hoặc class bị module đóng. Nó chỉ bind một tham số của handle đã có. Nếu cần tìm private method hợp lệ, hãy giải quyết ngữ cảnh lookup và các quy tắc Java module system trước khi bind.

**Virtual dispatch:** `findVirtual` tạo handle cho cơ chế dispatch của method instance. Khi `bindTo` giữ một receiver có runtime class là subclass, phương thức override vẫn có thể được chọn theo dispatch của runtime receiver. Ví dụ `LoudGreeter` trong chương trình trên chứng minh điều này. Bind không ép method trở thành một bản sao cố định của phần thân `Greeter.greet`.

**Không đổi identity của receiver:** `bound` giữ cùng receiver object (có thể truyền tới nhiều nơi), nên sửa trạng thái đối tượng ở chỗ khác vẫn ảnh hưởng tới lời gọi qua handle. `bindTo` không bảo đảm thread safety, không chặn concurrent modification, không tự đồng bộ hóa. Nếu receiver là đối tượng mutable có nhiều luồng cùng truy cập, cần bảo vệ trạng thái theo hợp đồng của đối tượng, không thể dựa vào việc bind.

**Vòng đời:** Handle giữ tham chiếu tới bound object chừng nào handle và các cấu trúc giữ nó còn sống. Cache một handle bound receiver trong phạm vi dài có thể vô tình giữ sống receiver và các object mà receiver tham chiếu. Với những đối tượng sống ngắn, cân nhắc cache **unbound handle** và truyền receiver tại thời điểm gọi thay vì giữ mỗi receiver trong một cache toàn cục.

## 9. Dùng bindTo trong một luồng xử lý thật

Ví dụ một ứng dụng có nhiều `Formatter`. Khi khởi tạo tuyến xử lý, ứng dụng chọn receiver theo cấu hình rồi gọi nhiều lần:

~~~java
interface Formatter {
    String format(String input);
}

class UpperFormatter implements Formatter {
    public String format(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Có thể tìm handle `Formatter.format(String)` một lần, sau đó `bindTo(selectedFormatter)` để tạo một callback có kiểu `(String)String`. Phần chọn đối tượng chỉ thực hiện khi cấu hình thay đổi; vòng lặp xử lý chỉ truyền chuỗi dữ liệu. Tuy nhiên, khi cấu hình cần chọn lại receiver, phải tạo **handle mới** hoặc giữ unbound handle để chuyển receiver, bởi handle đã bound tiếp tục gọi receiver cũ.

Đánh giá thiết kế:

- **Khi thích hợp:** người gọi đã có receiver cố định và gọi lặp lại cùng thao tác, xây pipeline động hoặc kết hợp handles với `filterArguments`, `filterReturnValue` và các adapter khác.
- **Khi không cần:** mã ứng dụng biết rõ kiểu và method ngay lúc biên dịch; cách gọi `formatter.format(text)` hoặc `formatter::format` thường đơn giản hơn.
- **Khi receiver thay đổi theo request:** giữ unbound handle hoặc tạo handle phù hợp cho từng receiver có vòng đời rõ ràng; tránh bind rồi đặt vào singleton cache mà không quản lý vòng đời.
- **Khi cần tối ưu:** đo đạc với JIT warmup và luồng gọi thực. Không thể kết luận `bindTo` luôn nhanh hơn gọi thông thường hoặc `Method.invoke` cho mọi JVM và trường hợp.

## 10. Lỗi dễ gặp và cách khắc phục

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `IllegalArgumentException` ngay ở `bindTo` | Handle không có tham số hoặc tham số đầu là primitive | Xem `type().parameterCount()` và `parameterType(0)`; dùng `insertArguments` cho primitive |
| `ClassCastException` lúc bind | Giá trị được gắn không phù hợp reference type ở index 0 | Kiểm tra class của đối tượng so với tham số đầu của handle |
| `WrongMethodTypeException` ở `invokeExact` | Vẫn truyền receiver sau bind, sai kiểu đối số hoặc **sai kiểu kết quả** | In `bound.type()`; cung cấp chính xác các tham số còn lại và cast/gán return type phù hợp |
| `NullPointerException` khi gọi handle bound receiver | Receiver là `null` hoặc logic bên trong method dereference giá trị null | Kiểm tra receiver trước khi bind và hợp đồng null của method |
| Không thấy kết quả khi bind | `bindTo` chỉ tạo handle mới; chưa gọi phương thức | Gọi `invokeExact`/`invoke` trên handle mới |
| Sau khi bind không gọi handle cũ được như handle mới | `bindTo` không sửa handle gốc | Dùng biến `bound` riêng và cung cấp đúng signature mỗi handle |
| Gắn sai đối số của static method | `bindTo` luôn cố định argument index 0 | Kiểm tra thứ tự tham số; dùng `insertArguments` với `pos` cần thiết |
| Muốn bind tham số thứ hai hoặc `int` | `bindTo` không hỗ trợ vị trí tùy ý/primitive | Dùng `MethodHandles.insertArguments` |
| Thay receiver mà handle vẫn gọi object cũ | Bound handle đã giữ receiver tại thời điểm tạo | Tạo handle bound mới hoặc dùng unbound handle |
| Dữ liệu có vẻ bị “đóng băng” | Hiểu nhầm bind là tính trước kết quả | Nhớ rằng bind giữ **tham chiếu**, method chạy mỗi lượt |
| Receiver mutable bị race giữa nhiều luồng | `bindTo` không cung cấp đồng bộ hóa | Thiết kế bảo vệ thread safety cho receiver |
| Cache gây giữ đối tượng lâu | Handle bound giữ tham chiếu tới receiver | Quản lý cache/lifetime, dùng unbound handle khi hợp lý |

**Lưu ý về ngoại lệ đích:** Nếu method được gọi qua handle ném `IOException`, `IllegalStateException` hoặc exception khác, exception đó được chuyển tiếp trực tiếp theo hợp đồng `MethodHandle.invokeExact`/`invoke`. `bindTo` không thay thế cơ chế này bằng `InvocationTargetException` như `java.lang.reflect.Method.invoke`. Vì `invokeExact` và `invoke` khai báo `throws Throwable`, ví dụ độc lập dùng `main(...) throws Throwable` để thể hiện đầy đủ hợp đồng; ứng dụng thực tế nên xử lý ngoại lệ theo ngữ cảnh.

## 11. Tự kiểm tra với đáp án

**Câu 1.** Handle chưa bound có `type() == (Greeter,String)String`. Sau `bindTo(greeter)`, chữ ký còn lại là gì?  
**Đáp án:** `(String)String`. Receiver đã được cố định nên không xuất hiện ở tham số gọi nữa.

**Câu 2.** `bindTo` có dùng được với handle của method static không?  
**Đáp án:** Có, nếu tham số đầu tiên của handle có kiểu tham chiếu. Khi đó nó gắn đối số đầu của static method; static method không có receiver.

**Câu 3.** Handle `(int,int)int`, `bindTo(5)` có hợp lệ?  
**Đáp án:** Không. Tham số đầu là primitive `int`, nên `bindTo` gây `IllegalArgumentException`. Dùng `MethodHandles.insertArguments(handle, 0, 5)`.

**Câu 4.** Sau khi tạo `bound = unbound.bindTo(greeter)`, có thể gọi `unbound.invokeExact(greeter, "A")` tiếp không?  
**Đáp án:** Có. `unbound` giữ nguyên chữ ký và thao tác ban đầu.

**Câu 5.** `bindTo(greeter)` có khiến `greeter.greet(...)` chạy trước không?  
**Đáp án:** Không. Body thực thi khi gọi handle mới, nên kết quả còn phụ thuộc tham số chưa gắn và trạng thái receiver lúc gọi.

**Câu 6.** Handle có `type() == (String)String`. Vì sao `Object out = bound.invokeExact("x")` có thể gây lỗi?  
**Đáp án:** Kiểu trả về call site là `Object`, không khớp `String` của handle; `invokeExact` cần khớp chính xác cả return type.

**Câu 7.** Nếu muốn gắn đối số thứ ba của `(String,int,String)String`, dùng gì?  
**Đáp án:** `MethodHandles.insertArguments(handle, 2, "suffix")` vì `bindTo` chỉ gắn tham số đầu.

**Câu 8.** Bound handle gắn `LoudGreeter` nhưng tìm bằng `findVirtual(Greeter.class, ...)` có gọi override không?  
**Đáp án:** Có, khi method là virtual và receiver thực có override phù hợp; `bindTo` không làm mất cơ chế virtual dispatch.

**Câu 9.** Cache lâu dài một handle `bound` có thể có hậu quả gì?  
**Đáp án:** Receiver bị giữ tham chiếu theo vòng đời handle/cache. Cần quản lý lifetime hoặc cache unbound handle nếu receiver thay đổi liên tục.

## 12. Ghi nhớ

- `bindTo(Object)` **cố định tham số có kiểu tham chiếu đầu tiên** của một `MethodHandle` và trả về **handle mới** có ít một tham số.
- Với handle instance `findVirtual` chưa bound, tham số đầu thường là **receiver**; sau bind, lời gọi chỉ cần các đối số còn lại.
- Với handle static, tham số đầu là đối số nghiệp vụ, vẫn có thể bind như bình thường.
- `bindTo` không hỗ trợ handle bắt đầu bằng primitive, không chọn được vị trí tùy ý; dùng `MethodHandles.insertArguments` cho các tình huống đó.
- `bindTo` giữ tham chiếu, **không tạo bản sao receiver**, không chạy method trước, không sửa handle gốc và không tự cung cấp thread safety.
- `invokeExact` phải khớp `MethodType` **mới** của bound handle, kể cả kiểu trả về; `invoke` cho phép một số chuyển đổi kiểu nhưng không tự khôi phục tham số đã bound.
- Cần kiểm tra `handle.type()` trước và sau biến đổi; đây là công cụ quan trọng nhất để hiểu sai lệch chữ ký khi kết hợp các handle.

Với `bindTo`, ta chuyển từ khả năng gọi “cần receiver hoặc giá trị tham chiếu đầu vào” thành một khả năng gọi đã được cấu hình với giá trị đó. Khi dùng đúng, cách này giúp diễn đạt rõ các lời gọi động có ngữ cảnh cố định mà vẫn giữ quyền kiểm soát kiểu, thời điểm thực thi và vòng đời receiver.
