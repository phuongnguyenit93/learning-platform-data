# Kết hợp sealed với lớp abstract, record và enum trong Java 17+

> **Module:** Java Core — class/object  
> **Nhóm:** Lớp sealed  
> **Chủ đề:** Kết hợp sealed với lớp abstract, record và enum  
> **Môi trường:** Java 17+ với tính năng ngôn ngữ chuẩn; các chương trình chạy bằng `javac`/`java` thông thường, không cần bật preview.

## 1. Bản đồ tư duy: sealed kiểm soát cây kiểu, không kiểm soát toàn bộ object

`sealed` là modifier dùng để **giới hạn những class/interface nào được phép trực tiếp kế thừa hoặc triển khai một type**. Từ Java 17, sealed classes và sealed interfaces là tính năng chuẩn của Java.

Vấn đề của bài này không phải chỉ học cú pháp `sealed ... permits ...`, mà là cách nó tương tác với:

- **`abstract class`**: class chưa thể tạo instance trực tiếp, thường định nghĩa state/behavior dùng chung, và có thể chính nó là `sealed` hoặc `non-sealed`.
- **`record`**: class đặc biệt, final, ngầm extends `java.lang.Record`, không thể extends custom class; **có thể implements sealed interface**.
- **`enum`**: class đặc biệt, ngầm extends `java.lang.Enum<E>`, không thể extends custom class; **có thể implements sealed interface**. Nếu có constant-specific class bodies, enum có thêm đặc điểm implicit sealing riêng.
- **`interface`**: không mang instance state như ordinary class, cho phép một sealed root bao gồm nhiều kiểu concrete representation, rất hợp để kết hợp records, enums và class hierarchy.

**Kết luận thiết kế then chốt:** Khi bạn muốn một họ kiểu gồm **record + enum + abstract class**, hãy dùng **sealed interface làm root**. Record/enum không thể kế thừa một sealed abstract class vì cả hai không được extends arbitrary class.

Bức tranh tổng quát:

~~~text
sealed interface Event
    |
    +-- record TextEvent(...) implements Event        [ngầm final]
    |
    +-- enum SystemEvent implements Event             [final hoặc implicitly sealed]
    |
    +-- sealed abstract class Command implements Event
            |
            +-- final class RetryCommand extends Command
            |
            +-- final class StopCommand extends Command
~~~

Một sealed interface giới hạn **direct implementors**. Một sealed abstract class giới hạn **direct subclasses**. Những con được phép phải nói rõ chúng **dừng kế thừa** (`final`), **tiếp tục giới hạn** (`sealed`), hay **mở lại việc kế thừa** (`non-sealed`) — trừ những loại đặc biệt như record và enum có rules implicit.

## 2. Nhắc lại sealed, permits và direct subtype

Xem:

~~~java
sealed interface Message permits TextMessage, SystemMessage {
}

record TextMessage(String value) implements Message {
}

enum SystemMessage implements Message {
    START, STOP
}
~~~

Đây là declaration fragment. `Message` chỉ cho phép `TextMessage` và `SystemMessage` là **direct implementors** theo declaration đã nêu.

Một class khác trong source:

~~~java
final class OtherMessage implements Message {
}
~~~

**Cố ý không biên dịch**, vì OtherMessage không nằm trong permitted direct subtypes của Message.

### 2.1. Cần hiểu chữ “trực tiếp”

Nếu:

~~~java
sealed interface Animal permits Mammal {
}

non-sealed interface Mammal extends Animal {
}

final class Dog implements Mammal {
}
~~~

thì Dog không phải direct implementor của Animal; nó trực tiếp implements Mammal. Mammal đã `non-sealed`, vì vậy hierarchy tại nhánh này được mở theo rules thông thường. Animal vẫn chỉ permit direct subtype Mammal.

Điểm này quan trọng vì sealed root **không bảo đảm mọi descendant đều thuộc một tập đóng tuyệt đối** nếu một nhánh permitted là `non-sealed`.

### 2.2. Trực tiếp extends/implements sealed parent cần đúng trạng thái

Một ordinary permitted direct subtype phải khai báo trạng thái tiếp theo:

- `final`: không có subclass tiếp theo.
- `sealed`: tiếp tục chỉ rõ những direct subclasses/implementors được phép.
- `non-sealed`: bỏ giới hạn sealing cho nhánh đó.

Một ordinary class thuộc direct permitted hierarchy không thể vừa bỏ hết ba modifiers vừa kỳ vọng Java tự đoán. Với record/enum, implicit rules đáp ứng yêu cầu đặc biệt, nên không gắn `final`/`non-sealed` tùy tiện lên record/enum declarations.

### 2.3. Sealed không thay access control

`permits` quyết định **ai có quyền là direct subtype**, không tự làm private member thành public, không vượt package/module accessibility, và không thay thế `abstract`. Một sealed class vẫn có thể có `private` constructors/fields; một class abstract vẫn không thể khởi tạo trực tiếp.

### 2.4. Trong chương trình nào nên dùng?

Sealed phù hợp khi domain variants đã xác định theo phiên bản code: command types, algebraic data types, trạng thái quy trình, AST nodes, kết quả thành công/thất bại, giao thức nội bộ. Với plugin ecosystem cần mở rộng tùy ý, `non-sealed` branch hoặc root interface mở có thể phù hợp hơn.

## 3. Java 17: sealed interface là điểm ghép linh hoạt

Giả sử một API trả về ba loại event:

- Data object ngắn gọn: record `TextEvent`.
- Named predefined signals: enum `SystemSignal`.
- Một họ commands có logic chung: sealed abstract class `Command`.

Tất cả có thể implements một interface:

~~~java
sealed interface Event
        permits TextEvent, SystemSignal, Command {
    String describe();
}

record TextEvent(String text) implements Event {
    public String describe() {
        return "text:" + text;
    }
}

enum SystemSignal implements Event {
    START, STOP;

    public String describe() {
        return "signal:" + name();
    }
}

abstract sealed class Command implements Event
        permits RetryCommand, StopCommand {
}

final class RetryCommand extends Command {
    public String describe() {
        return "retry";
    }
}

final class StopCommand extends Command {
    public String describe() {
        return "stop";
    }
}
~~~

Đây là **tập type declarations minh họa**, không phải standalone class có `main`. Toàn bộ `TextEvent`, `SystemSignal` và `Command` là direct permitted subtypes của Event. RetryCommand và StopCommand là direct subclasses của Command, không direct subtypes của Event.

### 3.1. Vì sao record và enum hợp với interface?

Java cho phép record/enum implements interfaces. Record đã có superclass `java.lang.Record` và enum đã có superclass `java.lang.Enum<E>`, nên không thể extends `Command` hay một class custom khác. Interface giải quyết đúng constraint single-class inheritance.

### 3.2. Vì sao abstract class là một nhánh trung gian?

`Command` có thể đặt reusable state/constructor/validation/helper methods cho các command implementations. Nhưng vì Command không phải record hay enum, những subclasses của Command có thể dùng `extends Command` bình thường.

### 3.3. Quyền kế thừa không đi qua “đường tắt”

`final class PluginCommand extends Command` sẽ bị từ chối nếu không nằm trong permits list của Command. Việc `Command implements Event` không đủ quyền để một arbitrary class kế thừa Command.

## 4. Chương trình hoàn chỉnh 1 — một sealed root trộn ba loại

Tạo tệp **`SealedMixedFamilyDemo.java`**:

~~~java
public class SealedMixedFamilyDemo {
    sealed interface Event
            permits TextEvent, SystemSignal, Command {
        String describe();
    }

    record TextEvent(String text) implements Event {
        @Override
        public String describe() {
            return "text:" + text;
        }
    }

    enum SystemSignal implements Event {
        START, STOP;

        @Override
        public String describe() {
            return "signal:" + name();
        }
    }

    abstract static sealed class Command implements Event
            permits RetryCommand, StopCommand {
        protected final String target;

        Command(String target) {
            this.target = target;
        }
    }

    static final class RetryCommand extends Command {
        RetryCommand(String target) {
            super(target);
        }

        @Override
        public String describe() {
            return "retry:" + target;
        }
    }

    static final class StopCommand extends Command {
        StopCommand(String target) {
            super(target);
        }

        @Override
        public String describe() {
            return "stop:" + target;
        }
    }

    public static void main(String[] args) {
        Event[] events = {
            new TextEvent("hello"),
            SystemSignal.START,
            new RetryCommand("job-7"),
            new StopCommand("worker-2")
        };

        for (Event event : events) {
            System.out.println(event.describe());
        }

        System.out.println("Text is record = "
                + TextEvent.class.isRecord());
        System.out.println("Signal is enum = "
                + SystemSignal.class.isEnum());
        System.out.println("Command is sealed = "
                + Command.class.isSealed());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SealedMixedFamilyDemo.java
java SealedMixedFamilyDemo
~~~

**Stdout:**

~~~text
text:hello
signal:START
retry:job-7
stop:worker-2
Text is record = true
Signal is enum = true
Command is sealed = true
~~~

### 4.1. Vì sao TextEvent record compile?

`TextEvent` implements Event và được Event permit. Record ngầm final; nó không được phép và không cần ghi modifier `final` vào record declaration.

### 4.2. Vì sao SystemSignal enum compile?

Enum có thể implements Event. Đây là một enum không có constant-specific class bodies nên implicitly final, đáp ứng quy tắc direct permitted subtype. Các signal instances vẫn là START và STOP.

### 4.3. Vì sao Command vừa abstract vừa sealed?

`abstract` cấm tạo `new Command(...)`; `sealed` cấm các direct subclasses ngoài RetryCommand và StopCommand. Chúng kiểm soát **hai khía cạnh khác nhau**: instantiability và subclass permissions.

### 4.4. Vì sao các subclasses cuối là final?

RetryCommand và StopCommand chốt hai nhánh của cây Command, không cho arbitrary subclass tiếp theo. Khi một class trực tiếp extends sealed parent, nó cần final/sealed/non-sealed theo rules.

## 5. Abstract class với sealed: hai chức năng độc lập

`abstract` mô tả **không thể tạo instance trực tiếp** và có thể khai báo abstract methods. `sealed` mô tả **những direct subtypes được phép**.

Một class có thể vừa abstract vừa sealed:

~~~java
abstract sealed class Shape permits Circle, Square {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}

final class Square extends Shape {
    private final double side;

    Square(double side) {
        this.side = side;
    }

    @Override
    double area() {
        return side * side;
    }
}
~~~

Đây là fragment. `Shape` có contract chung và không tạo được trực tiếp. Chỉ Circle/Square được trực tiếp extends Shape.

### 5.1. Có thể sealed mà không abstract?

Có. Một sealed ordinary class không abstract vẫn có thể tự instantiate nếu constructor accessible:

~~~java
sealed class Base permits Child {
    Base() {
    }
}

final class Child extends Base {
}
~~~

Bạn có thể tạo `new Base()` ở scope có quyền truy cập constructor. `sealed` **không tự khiến class abstract**.

### 5.2. Có thể abstract mà không sealed?

Có. `abstract class OpenBase` có thể được extends bởi bất kỳ class hợp lệ theo package/access rules; compiler không cần `permits` trừ khi superclass sealed.

### 5.3. Có thể abstract final?

Không. `abstract` nghĩa là class cần được subclass để hoàn tất behavior; `final` cấm subclassing. Hai modifiers không tương thích. Nhưng `abstract sealed` là kết hợp có ý nghĩa: cần subclass song giới hạn subclasses.

### 5.4. Constructor của abstract sealed class

Abstract class có constructors để subclasses gọi `super(...)`. Điều đó không làm client tạo được abstract instance trực tiếp. Constructor còn có thể xác lập invariants chung; nhớ không gọi overridable methods trước khi subclass initialization hoàn tất.

### 5.5. Record/enum không được extends Shape

Nếu cố viết `record CircleRecord(double radius) extends Shape` hoặc `enum ShapeKind extends Shape`, syntax/type rules không cho phép. Sealed class chỉ thích hợp làm base của **ordinary classes**.

## 6. Tại sao record không thể kế thừa sealed abstract class?

Record là class đặc biệt, nhưng luôn ngầm có superclass `java.lang.Record`. Nó không thể ghi `extends CustomBase`, kể cả CustomBase là sealed, abstract, concrete hoặc nằm trong permits list.

Sai:

~~~java
abstract sealed class Node permits Literal {
}

record Literal(int value) extends Node {
}
~~~

Đây là **mã cố ý không biên dịch**. Record header không có extends clause như ordinary class; chỉ có thể dùng implements interfaces.

Ngay cả khi thay Node permits Literal, Java cũng không thể làm Literal thành direct subclass của Node vì một record không extends Node. `permits` không “ép” Java tạo một inheritance relationship không hợp lệ.

### 6.1. Cách sửa

Đưa contract chung thành **sealed interface**:

~~~java
sealed interface Node permits Literal, OperatorNode {
}

record Literal(int value) implements Node {
}

abstract non-sealed class OperatorNode implements Node {
}
~~~

Đây là fragments hợp lệ (với package/module visibility phù hợp). Literal record implements Node; OperatorNode abstract class cũng implements Node. Hai types đều là direct subtypes Node.

### 6.2. Record vẫn có thể chứa ordinary class như component

Record có thể chứa `Node`/`OperatorNode` references như dữ liệu, ví dụ `record Wrapper(Node content) implements Node` nếu Wrapper cũng được permits hợp lệ. Đây là **composition**, không phải Java class inheritance.

### 6.3. Vì sao lựa chọn sealed interface tốt hơn?

Sealed interface mô tả **domain category** chứ không ép mọi implementation dùng cùng superclass. Record, enum và ordinary classes đều có thể satisfy interface contract, kể cả khi mỗi loại phải tuân superclass rules riêng.

### 6.4. Abstract class có thể triển khai interface rồi làm ancestor trung gian

Một sealed interface có thể permit một abstract class. Abstract class đó có thể sealed, non-sealed hoặc được thiết kế với subclasses theo rules. Các record/enum khác **không cần** đi qua abstract class, mà implements root interface trực tiếp.

## 7. Enum cũng không được extends sealed abstract class

Enum declaration không hỗ trợ custom extends clause vì mỗi enum ngầm extends `java.lang.Enum<E>`.

Sai:

~~~java
abstract sealed class Message permits Status {
}

enum Status extends Message {
    OK, ERROR
}
~~~

Đây là **mã cố ý không biên dịch**. Enum không extends arbitrary class.

Đúng:

~~~java
sealed interface Message permits Status, Payload {
}

enum Status implements Message {
    OK, ERROR
}

record Payload(String text) implements Message {
}
~~~

### 7.1. Enum có những instances cố định

Khi implements sealed interface, Status vẫn chỉ có OK/ERROR constants như được khai báo. `sealed interface Message` không tự cho phép tạo thêm Status constants bằng `new`.

### 7.2. Enum có thể implement nhiều interfaces

Nếu cần thêm capability contract:

~~~java
interface Coded {
    String code();
}

enum Status implements Message, Coded {
    OK, ERROR;

    public String code() {
        return name();
    }
}
~~~

Đây là fragment giả định Message đã permits Status. Sealed constraints vẫn áp dụng với Message; interface Coded là contract độc lập.

### 7.3. Không nhầm enum's internal constant subclasses với mở rộng từ bên ngoài

Một enum constant có thể có class body riêng, tạo một compiler-controlled anonymous subtype của chính enum. Điều này không cho phép external code extends Status hoặc tự thêm constant.

## 8. Record là final, nhưng không nhất thiết deeply immutable

Với:

~~~java
record ApiResult(String message, java.util.List<String> notes) {
}
~~~

record implicitly final và phù hợp làm permitted direct implementation của sealed interface. Nhưng nếu notes là mutable ArrayList, record có thể quan sát state thay đổi qua reference aliases. Sealed giới hạn subtyping, còn record final giới hạn subclassing; **không điều nào tự deep-copy mutable references**.

### 8.1. Defensive copy tại record boundary

~~~java
record ApiResult(String message, java.util.List<String> notes) {
    ApiResult {
        notes = java.util.List.copyOf(notes);
    }
}
~~~

Compact canonical constructor làm snapshot List structure trước khi field được gán. Nếu list elements immutable Strings, data an toàn hơn trước mutation bên ngoài.

### 8.2. Không thể gắn `sealed` lên record để định nghĩa subclass tree

Record được ngôn ngữ quy định là final. Không dùng:

~~~java
sealed record Result(String data) permits MoreResult {
}
~~~

**Cố ý không biên dịch**. Nếu muốn một family các record variants, dùng sealed interface làm root rồi cho từng record implements.

### 8.3. Value-based equality của record khác identity của enum

Hai `new ApiResult("ok", List.of())` với cùng component values có thể equal theo generated `equals()`. Nhưng enum constants là canonical instances, dùng `==`. Việc cả hai implements cùng sealed interface không biến equals/identity semantics của từng loại thành một kiểu duy nhất.

## 9. Chương trình hoàn chỉnh 2 — sealed abstract class làm base cho ordinary classes

Tạo tệp **`SealedAbstractClassDemo.java`**:

~~~java
public class SealedAbstractClassDemo {
    abstract static sealed class Operation permits Save, Fetch {
        abstract String execute();
    }

    static final class Save extends Operation {
        @Override
        String execute() {
            return "save";
        }
    }

    static non-sealed class Fetch extends Operation {
        @Override
        String execute() {
            return "fetch";
        }
    }

    static final class CachedFetch extends Fetch {
        @Override
        String execute() {
            return "fetch-cached";
        }
    }

    public static void main(String[] args) {
        Operation save = new Save();
        Operation fetch = new CachedFetch();

        System.out.println("Save = " + save.execute());
        System.out.println("Fetch = " + fetch.execute());
        System.out.println("Operation sealed = "
                + Operation.class.isSealed());
        System.out.println("Fetch sealed = "
                + Fetch.class.isSealed());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 SealedAbstractClassDemo.java
java SealedAbstractClassDemo
~~~

**Stdout:**

~~~text
Save = save
Fetch = fetch-cached
Operation sealed = true
Fetch sealed = false
~~~

### 9.1. `Save` là nhánh đóng

Save final, không thể subclass nó.

### 9.2. `Fetch` là nhánh mở

Fetch là direct permitted subtype của Operation và tự khai báo `non-sealed`. Vì vậy `CachedFetch extends Fetch` được phép, dù CachedFetch không nằm trong `Operation.permits`.

### 9.3. Khi nào dùng `non-sealed`?

Khi root cần biết những loại extension points được phép xuất hiện trực tiếp, nhưng một nhánh phải cho bên thứ ba bổ sung implementations. Ví dụ root `Operation` permit loại `Fetch`, và plugins được phép mở rộng behavior dựa trên Fetch.

### 9.4. `non-sealed` không phải từ khóa trang trí

Một class không thể tự gắn non-sealed nếu không phải direct subtype thuộc sealed hierarchy phù hợp. Đó là modifier mang ý nghĩa “mở lại nhánh đã bị sealed parent kiểm soát”.

## 10. Abstract non-sealed: vẫn abstract nhưng không hạn chế subclasses

Một nhánh direct subtype của sealed interface có thể là **abstract non-sealed class**:

~~~java
sealed interface Shape permits Polygon, Circle {
}

record Circle(double radius) implements Shape {
}

abstract non-sealed class Polygon implements Shape {
    abstract int edges();
}

final class Triangle extends Polygon {
    @Override
    int edges() {
        return 3;
    }
}
~~~

Đây là fragment. `Polygon` abstract nên không tạo `new Polygon()`, nhưng non-sealed nên có thể được mở rộng bởi Triangle và những subclasses hợp lệ khác.

### 10.1. So sánh ba biến thể abstract

| Declaration | Tạo instance của type đó? | Mở rộng subclasses |
| --- | --- | --- |
| `abstract class A` | Không | Theo normal rules |
| `abstract sealed class A permits B` | Không | Chỉ direct subclasses được permit |
| `abstract non-sealed class A` (sau sealed parent) | Không | Nhánh subclassing được mở |
| `final class A` | Có nếu constructor accessible | Không được subclass |
| `sealed class A permits B` không abstract | Có nếu constructor accessible | Chỉ permit direct subclasses |

Một sealed abstract class có thể được dùng khi cần kiểm soát tuyệt đối nhánh trung gian. Một abstract non-sealed class phù hợp khi muốn các implementors của một branch tiếp tục có thể xuất hiện từ plugins.

### 10.2. Cảnh báo khi phân tích exhaustiveness

Nếu một permitted direct subtype là non-sealed, compiler biết nó là một nhánh cho phép nhiều descendants không được liệt kê trước. Một xử lý có pattern theo **type của nhánh non-sealed** có thể bao phủ tất cả descendants đó; không được mặc định rằng chỉ có những subclasses bạn biết hôm nay.

### 10.3. Hạn chế của accessible constructors

Dù non-sealed, một abstract superclass với inaccessible constructor có thể khiến clients không dễ extend. Modifiers về inheritance và constructor access là hai tầng kiểm soát riêng.

## 11. Chương trình hoàn chỉnh 3 — sealed interface với abstract non-sealed branch

Tạo tệp **`SealedAbstractBranchDemo.java`**:

~~~java
public class SealedAbstractBranchDemo {
    sealed interface Shape permits Circle, Polygon {
        double area();
    }

    record Circle(double radius) implements Shape {
        @Override
        public double area() {
            return 3.0 * radius * radius;
        }
    }

    abstract static non-sealed class Polygon implements Shape {
        protected final double side;

        Polygon(double side) {
            this.side = side;
        }
    }

    static final class Square extends Polygon {
        Square(double side) {
            super(side);
        }

        @Override
        public double area() {
            return side * side;
        }
    }

    public static void main(String[] args) {
        Shape circle = new Circle(2.0);
        Shape square = new Square(3.0);

        System.out.println("Circle area = " + circle.area());
        System.out.println("Square area = " + square.area());
        System.out.println("Circle is record = "
                + Circle.class.isRecord());
        System.out.println("Polygon sealed = "
                + Polygon.class.isSealed());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SealedAbstractBranchDemo.java
java SealedAbstractBranchDemo
~~~

**Stdout:**

~~~text
Circle area = 12.0
Square area = 9.0
Circle is record = true
Polygon sealed = false
~~~

### 11.1. Vì sao Polygon có thể tiếp tục có Square?

Polygon được Shape permit và khai báo non-sealed. Square extends Polygon, không phải direct implementor Shape, nên không cần nêu trong `Shape.permits`.

### 11.2. Circle record không cần final modifier

Record automatically final, là direct permitted implementation của Shape. Không thể extends Circle bằng ordinary class để có thêm behavior.

### 11.3. Vì sao dùng 3.0 thay Math.PI?

Demo cố tình dùng hệ số 3.0 để stdout deterministic/simple và tập trung vào sealed/abstract/record, không dạy công thức hình tròn trong kỹ thuật. Với nghiệp vụ hình học thật cần `Math.PI`, nhưng lúc đó output thập phân khác.

## 12. Trạng thái `final`, `sealed`, `non-sealed` cho direct subtypes

Một sealed parent yêu cầu ordinary direct subclass hoặc implementing class chọn đúng đường đi tiếp:

~~~java
sealed interface Command permits Simple, Group, Extension {
}

final class Simple implements Command {
}

sealed class Group implements Command permits GroupLeaf {
}

final class GroupLeaf extends Group {
}

non-sealed class Extension implements Command {
}
~~~

Đây là declaration fragment.

### 12.1. `final`

Chốt class branch. Một permitted final class không có subclasses. Record thuộc trạng thái final ngầm.

### 12.2. `sealed`

Tiếp tục hạn chế direct subtypes ở level kế. Cho phép nhiều tầng sealed hierarchies, ví dụ Command → Group → GroupLeaf. `permits` của Command liệt kê Group, **không** liệt kê GroupLeaf vì GroupLeaf không trực tiếp implements Command.

### 12.3. `non-sealed`

Mở hierarchy ở branch. Một non-sealed class có thể có subclasses theo inheritance rules chung; một non-sealed interface có thể được implementations tùy ý triển khai.

### 12.4. Không thể gắn `final` vào interface

Interface không được là `final`; một permitted interface phải là sealed hoặc non-sealed (theo circumstances), không có final modifier. Một final class hoặc record phù hợp cho nhánh đóng.

### 12.5. Có thể dùng `sealed` với interface không abstract modifier

Mọi interface vốn có tính abstract theo ngữ nghĩa (không instantiate bằng `new Interface()`). Viết `sealed interface I` là cách thường dùng. Không cần viết `abstract sealed interface` để làm nó “abstract hơn”.

### 12.6. Enum và record là exceptions có đặc tính implicit

Với record, declaration là implicitly final. Với enum, nếu không có constant class body thì implicitly final; nếu có constant class bodies thì implicitly sealed. Không cố thêm `final`/`sealed` modifier trực tiếp vào enum/record declarations.

## 13. Enum class body và khái niệm implicitly sealed

Một enum có thể chứa từng constant-specific class body để override behavior:

~~~java
enum Calculation {
    ADD {
        @Override
        int calculate(int a, int b) {
            return a + b;
        }
    },
    MULTIPLY {
        @Override
        int calculate(int a, int b) {
            return a * b;
        }
    };

    abstract int calculate(int a, int b);
}
~~~

Java tạo anonymous subclasses chuyên biệt cho các constants có class bodies. Trong Java 17 language model, một enum có ít nhất một constant-specific class body là **implicitly sealed**, và những permitted direct subclasses chỉ là anonymous classes ứng với constant-specific bodies.

### 13.1. Enum không có class bodies là implicitly final

~~~java
enum Direction {
    NORTH, SOUTH
}
~~~

Enum không có subclass cho constants, nên nó implicitly final. Không thể tạo arbitrary subclass of Direction.

### 13.2. Có enum class body không có nghĩa khách hàng được extends enum

Một enum có constant bodies được compiler xử lý đặc biệt. Bạn vẫn **không thể** viết `class MyOperation extends Calculation`, dù Calculation là implicitly sealed. Không có cơ chế `permits MyOperation` do user cung cấp cho enum.

### 13.3. Khi enum implements sealed interface

Một enum có thể là **direct permitted implementation** của sealed interface; subtype continuation rules của enum được quyết định bởi implicit enum final/sealed behavior, không cần `final class`/`non-sealed` modifier.

### 13.4. Phân biệt hai tầng sealing

Nếu `sealed interface Action permits Calculation` và Calculation là enum có constant bodies:

1. Action sealed giới hạn direct implementors tới Calculation.
2. Calculation implicitly sealed giới hạn direct subclasses của **chính enum** tới constant-specific anonymous classes.

Không nên gọi những constant bodies là “additional implementations of Action do plugins thêm” — chúng gắn với constants do enum định nghĩa, không mở runtime enum set.

## 14. Chương trình hoàn chỉnh 4 — sealed interface có enum với constant bodies

Tạo tệp **`SealedEnumBodiesDemo.java`**:

~~~java
public class SealedEnumBodiesDemo {
    sealed interface Action permits BuiltinAction, UserAction {
        String execute();
    }

    enum BuiltinAction implements Action {
        READ {
            @Override
            public String execute() {
                return "read";
            }
        },
        WRITE {
            @Override
            public String execute() {
                return "write";
            }
        };
    }

    record UserAction(String name) implements Action {
        @Override
        public String execute() {
            return "user:" + name;
        }
    }

    public static void main(String[] args) {
        Action read = BuiltinAction.READ;
        Action write = BuiltinAction.WRITE;
        Action user = new UserAction("export");

        System.out.println(read.execute());
        System.out.println(write.execute());
        System.out.println(user.execute());

        System.out.println("Action sealed = "
                + Action.class.isSealed());
        System.out.println("Enum sealed = "
                + BuiltinAction.class.isSealed());
        System.out.println("Declaring enum = "
                + BuiltinAction.READ.getDeclaringClass()
                        .getSimpleName());
        System.out.println("Constant runtime class is enum = "
                + (BuiltinAction.READ.getClass()
                        == BuiltinAction.class));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SealedEnumBodiesDemo.java
java SealedEnumBodiesDemo
~~~

**Stdout:**

~~~text
read
write
user:export
Action sealed = true
Enum sealed = true
Declaring enum = BuiltinAction
Constant runtime class is enum = false
~~~

### 14.1. Vì sao enum sealed = true?

BuiltinAction có READ và WRITE với constant-specific class bodies, nên implicitly sealed trong Java 17. Reflection `Class.isSealed()` cho biết trạng thái đó.

### 14.2. Vì sao getClass khác declaring class?

`BuiltinAction.READ` là instance của compiler-generated anonymous subclass, nhưng `getDeclaringClass()` vẫn trả BuiltinAction — enum class định nghĩa constant.

### 14.3. Không dùng tên synthetic subclass như một API

Tên runtime synthetic classes của constant-specific bodies có thể phụ thuộc compiler. Không dựa vào `BuiltinAction$1` hay tương tự để xử lý business logic.

### 14.4. Chú ý enum constant abstract methods

Nếu enum khai báo abstract instance method mà có một constant không override implementation, compiler sẽ từ chối. Ở demo này, interface Action yêu cầu execute(); mỗi constant-specific body cung cấp implementation, nên hợp lệ.

## 15. Java 17 reflection: ai được phép trực tiếp kế thừa?

Reflection có các APIs tiện dùng cho sealed classes/interfaces:

~~~java
SomeType.class.isSealed()
SomeType.class.getPermittedSubclasses()
~~~

`getPermittedSubclasses()` trả một `Class<?>[]` đại diện những direct permitted subclasses/implementors của sealed type. Nếu type không sealed, thường trả null theo API contract.

### 15.1. Direct permits không đồng nghĩa toàn bộ transitive descendants

Giả sử:

~~~text
sealed interface A permits B
non-sealed interface B extends A
class C implements B
~~~

`A.getPermittedSubclasses()` phản ánh B, không phải tự động liệt kê C, D, E ... có thể implements B trong tương lai.

### 15.2. Đừng dựa vào thứ tự không được yêu cầu

Khi muốn output deterministic, sort tên Class objects thay vì giả định reflection array luôn theo thứ tự người dùng mong đợi cho mọi công cụ/versions.

### 15.3. Non-sealed class là unsealed theo reflection

`isSealed()` trả false cho ordinary non-sealed class (nó không mang sealing restriction). Nó vẫn có thể là direct permitted subtype của một sealed parent.

### 15.4. Reflection không vượt quyền inheritance

Kể cả biết một Class trong permits list, bạn vẫn không được tự tạo một arbitrary additional direct subtype rồi thay list tại runtime theo public Java source semantics.

## 16. Chương trình hoàn chỉnh 5 — reflection kiểm tra sealed tree

Tạo tệp **`SealedReflectionDemo.java`**:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class SealedReflectionDemo {
    sealed interface Vehicle permits Bike, Car, Train, PluginVehicle {
    }

    record Bike(int wheels) implements Vehicle {
    }

    static final class Car implements Vehicle {
    }

    enum Train implements Vehicle {
        LOCAL
    }

    abstract static non-sealed class PluginVehicle
            implements Vehicle {
    }

    public static void main(String[] args) {
        Class<?>[] permitted =
                Vehicle.class.getPermittedSubclasses();

        System.out.println("Vehicle sealed = "
                + Vehicle.class.isSealed());
        System.out.println("Permitted = "
                + Arrays.stream(permitted)
                        .map(Class::getSimpleName)
                        .sorted()
                        .toList());
        System.out.println("Bike record = "
                + Bike.class.isRecord());
        System.out.println("Train enum = "
                + Train.class.isEnum());
        System.out.println("Car final = "
                + Modifier.isFinal(Car.class.getModifiers()));
        System.out.println("Plugin branch sealed = "
                + PluginVehicle.class.isSealed());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SealedReflectionDemo.java
java SealedReflectionDemo
~~~

**Stdout:**

~~~text
Vehicle sealed = true
Permitted = [Bike, Car, PluginVehicle, Train]
Bike record = true
Train enum = true
Car final = true
Plugin branch sealed = false
~~~

### 16.1. Vì sao reflection thấy PluginVehicle?

PluginVehicle là **direct permitted implementation** của Vehicle, dù class còn abstract và non-sealed. Reflection nhận diện direct subtype, không yêu cầu nó instantiable.

### 16.2. Vì sao không thấy mọi plugin subclasses?

PluginVehicle non-sealed mở branch, nên direct children của PluginVehicle là descendants của Vehicle chứ không direct implementations được Vehicle permit. Reflection của Vehicle chỉ liệt kê direct permitted types.

### 16.3. Record/enum metadata độc lập sealed metadata

`Bike.class.isRecord()` kiểm tra record type, `Train.class.isEnum()` kiểm tra enum type. `Vehicle.class.isSealed()` kiểm tra restriction của sealed interface. Đây là ba khía cạnh khác nhau cùng tồn tại trong một type hierarchy.

## 17. Exhaustive handling: Java 17 có gì và chưa có gì?

Một sealed type có **tập direct permitted branches** hữu hạn, vì vậy hữu ích cho exhaustive handling. Nhưng cần phân biệt feature availability theo Java version:

- Java 17 **đã chuẩn hóa sealed classes/interfaces**.
- Java 17 **đã hỗ trợ pattern matching cho `instanceof`** như một tính năng chuẩn.
- **Type patterns trong `switch` trên sealed hierarchies là preview ở Java 17**, không phải syntax Java 17 chuẩn khi chỉ dùng `javac File.java`.
- Tính năng switch patterns được chuẩn hóa ở Java 21; ví dụ Java 17 trong bài này **không dùng preview**.

Do đó để xử lý mixed sealed variants trong Java 17 ổn định, dùng `if / else if` kết hợp `instanceof` pattern variables.

### 17.1. Pattern matching với instanceof

~~~java
if (value instanceof DataEvent data) {
    return data.payload();
}
~~~

Pattern variable `data` tồn tại trong flow scope nơi compiler biết type test thành công.

### 17.2. Lưu ý khi thêm variant mới

Với chain `if / else if` trong Java 17, compiler **không tự bảo đảm exhaustive** đối với tất cả sealed variants như pattern switch exhaustive đã có trong những Java versions sau. Nếu bạn thêm một permitted subtype nhưng quên xử lý, có thể rơi vào fallback branch khi runtime.

### 17.3. Switch trên enum vẫn chuẩn trong Java 17

Một `switch` expression dùng enum constants và đầy đủ cases là Java 17 chuẩn. Đừng nhầm điều đó với `switch (sealedInterface) { case Type t -> ... }`, vốn là preview trong Java 17.

### 17.4. Có thể thiết kế visitor-style polymorphism

Một sealed interface có method `accept(Visitor)` và mỗi subtype triển khai method có thể cung cấp compile-time-oriented visitor API trong Java 17. Nhưng thêm variant mới vẫn cần cập nhật visitor contract, và design có boilerplate; chọn theo nhu cầu API.

## 18. Chương trình hoàn chỉnh 6 — instanceof patterns với record + enum

Tạo tệp **`SealedPatternDispatchDemo.java`**:

~~~java
public class SealedPatternDispatchDemo {
    sealed interface Notification permits Mail, Push, Alarm {
    }

    record Mail(String address) implements Notification {
    }

    record Push(int count) implements Notification {
    }

    enum Alarm implements Notification {
        FIRE
    }

    static String handle(Notification value) {
        if (value instanceof Mail mail) {
            return "mail:" + mail.address();
        }
        if (value instanceof Push push) {
            return "push:" + push.count();
        }
        if (value instanceof Alarm alarm) {
            return "alarm:" + alarm.name();
        }
        throw new IllegalArgumentException("Unexpected notification");
    }

    public static void main(String[] args) {
        System.out.println(handle(new Mail("a@example.org")));
        System.out.println(handle(new Push(3)));
        System.out.println(handle(Alarm.FIRE));
    }
}
~~~

Biên dịch/chạy **không cần `--enable-preview`**:

~~~bash
javac -encoding UTF-8 SealedPatternDispatchDemo.java
java SealedPatternDispatchDemo
~~~

**Stdout:**

~~~text
mail:a@example.org
push:3
alarm:FIRE
~~~

### 18.1. Vì sao else-if không bắt buộc?

Mỗi nhánh nếu match đều return. Các nhánh sau chỉ chạy nếu test trước false. Flow analysis với pattern variables làm cho `mail`, `push`, `alarm` có type được xác định đúng trong body.

### 18.2. Vì sao cuối cùng vẫn throw?

Bài không dùng Java 21 exhaustive pattern switch. Với Java 17 compiler, chain này không được chứng minh exhaustive theo sealed permits tự động; method cần một fallback. Cũng có thể muốn reject null bằng một message rõ hơn.

### 18.3. Trường hợp null

`null instanceof Type` trả false cho các type patterns, rồi rơi vào throw. Nếu API cho phép null, nên xử lý null riêng ngay đầu function, không lẫn nó với một business variant.

## 19. Quy tắc permits với module và package

Sealed hierarchy không chỉ là một danh sách tên types: còn có compile-time deployment constraints.

### 19.1. Named module

Nếu sealed parent nằm trong **named module**, các direct permitted subclasses/implementors phải ở **cùng module** theo Java sealed rules. Chúng có thể thuộc các packages khác nhau trong cùng module khi declaration/accessibility và permits đều hợp lệ.

### 19.2. Unnamed module

Nếu sealed parent nằm trong **unnamed module**, các direct permitted subtypes phải ở **cùng package**. Không thể arbitrarily cho class ở package khác implement một sealed parent trong classpath project chỉ vì ghi tên vào permits.

### 19.3. Cùng compilation unit có thể suy ra permits

Trong những trường hợp mọi direct subclasses được khai báo trong cùng compilation unit với sealed parent, có thể **omit `permits`** và để Java suy ra direct permitted types:

~~~java
sealed interface Message {
}

record Info(String value) implements Message {
}

final class ErrorMessage implements Message {
}
~~~

Đây là declaration fragment. Khi types cùng compilation unit và hợp lệ, compiler suy ra permitted direct implementations. Tuy vậy viết `permits` tường minh trong bài học thường giúp nhìn thấy hierarchy và kiểm soát thiết kế.

### 19.4. Nếu trải types ra nhiều files?

Nếu direct subtypes nằm ở những compilation units khác nhau, nên dùng explicit `permits TypeA, TypeB` và đảm bảo package/module rules. Các classes phải được biên dịch trong dependency/source context phù hợp.

### 19.5. Không tự động cập nhật permits qua runtime registration

Permits hierarchy là property của compiled type system, không phải registry mutable. Load một plugin không nằm trong allowed hierarchy không khiến sealed parent chấp nhận plugin class như direct implementation.

## 20. Thêm subtype mới và tương thích source/binary

Một sealed hierarchy là **closed theo compiled version** của root, không phải không bao giờ thay đổi. Developer có thể cập nhật source để thêm permitted variant mới:

~~~java
sealed interface Command
        permits Create, Update, Delete {
}
~~~

Thêm Delete trong bản sau là một **thay đổi API/model**. Nó có thể ảnh hưởng:

- Clients có exhaustive patterns/switch trên những Java versions hỗ trợ chúng.
- Visitors hoặc explicit if/else handlers.
- Serialized message formats.
- Schema validation và JSON discriminators.
- Testing của toàn bộ variants.
- Documentation và generated models.
- Việc các permitted classes/records/enums được đóng gói trong module/package đúng rule.

### 20.1. Binary compatibility cần cân nhắc riêng

Compiled bytecode mang sealed/permitted-subclass metadata. Nếu đổi permits list hoặc subtype status mà không rebuild/redeploy đúng components, có thể phát sinh class loading/linkage failures. Không xem thay đổi hierarchy là “chỉ thêm một case nên chắc chắn an toàn”.

### 20.2. Non-sealed branch là một extension point có chủ đích

Chọn `non-sealed` khi muốn branch mở. Nhưng một sealed root có non-sealed branch không còn bảo đảm toàn bộ runtime descendants finite; những algorithms dựa trên exhaustive enumeration cần tính điều đó.

### 20.3. Record và enum cũng có versioning

Thêm record variant mới vào permits list hoặc thêm enum constant vào một enum permitted branch đều là thay đổi domain. Nhưng hai việc khác nhau:

- **Thêm permitted record subtype**: mở rộng tập direct implementation classes của root.
- **Thêm enum constant**: giữ nguyên enum implementation type nhưng tăng số named constant instances.

Do đó cần review consumer behavior theo đúng loại change.

## 21. Thiết kế kết quả thành công/thất bại với sealed + record + enum

Một pattern phổ biến là sealed interface làm contract kết quả:

~~~java
sealed interface Outcome permits Success, Failure, Pending {
}

record Success(String value) implements Outcome {
}

record Failure(int code, String message) implements Outcome {
}

enum Pending implements Outcome {
    INSTANCE
}
~~~

Đây là declaration fragment.

### 21.1. Tại sao dùng record cho Success/Failure?

Mỗi success/failure có payload khác nhau và có thể có nhiều values runtime. Record tạo immutable-like value instances ngắn gọn với canonical constructor, accessors và generated equals/hashCode/toString.

### 21.2. Vì sao enum cho Pending?

Nếu Pending chỉ là một trạng thái named singleton-like không có payload riêng, enum constant `INSTANCE` có thể đại diện trạng thái này, không cần tạo nhiều object vô nghĩa. Có thể có enum nhiều constant states nếu domain cần.

### 21.3. Vì sao sealed interface thay vì abstract base?

Success/Failure records và Pending enum không thể extends custom abstract class. Sealed interface gộp chúng về một domain type chung mà không vi phạm superclass restrictions.

### 21.4. Chú ý null và validation

Record components có thể nhận null nếu bạn không validate. Với Success, có thể kiểm tra `Objects.requireNonNull(value)` trong compact constructor nếu domain cấm null; sealed không tự enforce payload invariants.

## 22. Chương trình hoàn chỉnh 7 — Outcome dùng records và enum

Tạo tệp **`SealedOutcomeDemo.java`**:

~~~java
public class SealedOutcomeDemo {
    sealed interface Outcome permits Success, Failure, Pending {
    }

    record Success(String value) implements Outcome {
    }

    record Failure(int code, String message) implements Outcome {
    }

    enum Pending implements Outcome {
        INSTANCE
    }

    static String summary(Outcome outcome) {
        if (outcome instanceof Success success) {
            return "success:" + success.value();
        }
        if (outcome instanceof Failure failure) {
            return "failure:" + failure.code()
                    + ":" + failure.message();
        }
        if (outcome == Pending.INSTANCE) {
            return "pending";
        }
        throw new IllegalArgumentException("Unknown outcome");
    }

    public static void main(String[] args) {
        System.out.println(summary(new Success("saved")));
        System.out.println(summary(new Failure(404, "missing")));
        System.out.println(summary(Pending.INSTANCE));

        System.out.println("Success record = "
                + Success.class.isRecord());
        System.out.println("Pending enum = "
                + Pending.class.isEnum());
        System.out.println("Outcome sealed = "
                + Outcome.class.isSealed());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 SealedOutcomeDemo.java
java SealedOutcomeDemo
~~~

**Stdout:**

~~~text
success:saved
failure:404:missing
pending
Success record = true
Pending enum = true
Outcome sealed = true
~~~

### 22.1. Enum Pending khác record Success

Pending.INSTANCE là một canonical enum constant. Hai `new Success("saved")` objects có thể equal theo generated record equals, nhưng không cùng identity theo `==`.

### 22.2. Vì sao `outcome == Pending.INSTANCE` hợp lệ?

`Outcome` là interface type có thể tham chiếu Pending constant, nên identity comparison với Pending.INSTANCE hợp lệ. Với enum constant đây là cách so sánh rõ.

### 22.3. Nếu Pending cần payload?

Nếu cần mỗi pending task có retryAt/jobId khác nhau, chuyển Pending thành record variant `record Pending(String jobId, Instant retryAt)`, không nhồi mutable per-request data vào một shared enum singleton.

## 23. Sealed abstract class có thể chia sẻ state mà record không kế thừa được

Giả sử mỗi dạng Retry và Stop command cần `requestId` field, validation và constructor chung. Abstract class hữu ích:

~~~java
abstract sealed class BaseCommand
        permits RetryCommand, StopCommand {
    private final String requestId;

    BaseCommand(String requestId) {
        this.requestId =
                java.util.Objects.requireNonNull(requestId);
    }

    final String requestId() {
        return requestId;
    }

    abstract String perform();
}
~~~

Đây là fragment. RetryCommand và StopCommand có thể extends BaseCommand, reuse requestId field, và implement perform.

### 23.1. Vấn đề nếu muốn thêm record command

Không thể viết `record Retry(String requestId) extends BaseCommand`. Thay vào đó dùng:

~~~java
sealed interface Command permits RecordCommand, BaseCommand {
    String requestId();
}

record RecordCommand(String requestId) implements Command {
}

abstract sealed class BaseCommand implements Command
        permits LegacyCommand {
    // Shared state, constructors, methods.
}

final class LegacyCommand extends BaseCommand {
    // Implementation.
}
~~~

Đây là conceptual fragment: BaseCommand sẽ cần implement/declare `requestId()` để thỏa Command contract (có thể giữ abstract), và LegacyCommand cần complete implementation. Cách này cho thấy **sealed interface contract ở root**, còn abstract class là tùy chọn implementation branch.

### 23.2. Không ép records giả lập inheritance bằng forwarding phức tạp

Nếu tất cả variants cần chia sẻ mutable state và lifecycle phức tạp, record có thể không phù hợp. Có thể dùng ordinary final classes dưới sealed abstract base. Ngược lại, nếu variants thuần data, interface + records thường ngắn gọn.

### 23.3. Composition là cách tái sử dụng không cần class inheritance

Một record có thể chứa một value object chung:

~~~java
record Metadata(String requestId) {
}

record Save(Metadata meta, String path) implements Command {
    @Override
    public String requestId() {
        return meta.requestId();
    }
}
~~~

Đây là fragment giả định Command permits Save và contract tương ứng. Record Save không extends Metadata; nó **chứa** Metadata, dùng composition để tái sử dụng data.

## 24. Lỗi thường gặp khi kết hợp sealed, abstract, record, enum

### 24.1. Cho record extends abstract class

~~~java
abstract sealed class Base permits R {
}
record R(int x) extends Base { // LỖI.
}
~~~

Record không thể extends arbitrary class. Sửa bằng sealed interface + record implements.

### 24.2. Cho enum extends abstract class

~~~java
abstract sealed class Base permits E {
}
enum E extends Base { A } // LỖI.
~~~

Enum ngầm extends Enum<E>; không có custom extends clause. Sửa bằng implements sealed interface.

### 24.3. Cho ordinary class implement sealed interface nhưng thiếu permits

~~~java
sealed interface Root permits Allowed {
}
record Allowed(int x) implements Root {
}
final class Surprise implements Root { // LỖI.
}
~~~

Surprise không được Root permit.

### 24.4. Quên `final/sealed/non-sealed` ở ordinary direct subtype

~~~java
sealed interface Root permits Node {
}
class Node implements Root { // LỖI: modifier trạng thái thiếu.
}
~~~

Node phải chọn final/sealed/non-sealed theo rules. Không suy ra final chỉ vì thiếu extends clause.

### 24.5. Cố ghi `sealed record`

~~~java
sealed record Value(int x) { // LỖI.
}
~~~

Record implicitly final; không thể khai báo sealed subclass hierarchy trực tiếp trên record.

### 24.6. Cố ghi `final enum`

~~~java
final enum State { A } // LỖI: enum modifiers không cho final như vậy.
~~~

Enum final/sealed semantics do compiler/ngôn ngữ quyết định.

### 24.7. Abstract permitted class dùng final

~~~java
abstract final class Broken {
}
~~~

Không thể vừa abstract vừa final. Dùng abstract sealed/non-sealed tùy quan hệ sealed parent và yêu cầu mở rộng.

### 24.8. Non-sealed thiếu sealed ancestor trực tiếp

~~~java
non-sealed class Open {
}
~~~

Không hợp lệ vì non-sealed modifier chỉ áp dụng đúng cấu trúc direct subtype của sealed parent.

### 24.9. Cho phép class ở package/module không hợp lệ

Permits phải tuân theo named module/unnamed module placement rules. Không chỉ thêm fully qualified name là xong.

### 24.10. Dùng Java 21 pattern switch ở Java 17 không bật preview

~~~java
return switch (value) {
    case MyRecord r -> r.field();
    case MyEnum e -> e.name();
};
~~~

Trong Java 17 syntax dạng type-pattern switch là preview và không compile trong chế độ standard mặc định. Bài học sử dụng `instanceof` pattern matching ổn định.

### 24.11. Nghĩ sealed root bảo đảm mọi descendants closed sau non-sealed

Một permitted non-sealed branch cho phép descendants mới. Cần biết rõ phần nào của hierarchy được đóng.

### 24.12. Nghĩ enum constants chính là permitted interface implementations

Nếu Root permit enum State, **direct implementing class** là State; constants State.A, State.B là **instances**, không phải thêm hai direct class declarations được Root permits liệt kê.

### 24.13. Nghĩ record component fields là hoàn toàn immutable object graph

Record fields final, nhưng mutable referents vẫn có thể sửa qua aliases. Dùng defensive copy/immutability nếu cần.

### 24.14. Nghĩ reflective isSealed đồng nghĩa isAbstract

Một ordinary class có thể sealed nhưng không abstract; một abstract class có thể non-sealed. Hai metadata properties độc lập.

### 24.15. Nghĩ records/enums có thể extends java.lang.Record/Enum thủ công

Record/enum rules đã xử lý superclass đặc biệt. Ordinary class không thể tự extends `java.lang.Record` hoặc `java.lang.Enum` để giả danh record/enum type.

## 25. Checklist thiết kế mixed sealed hierarchy

1. Root cần đóng tập **direct implementations** hay cần plugin extensibility?
2. Có các record và enum variants không? Nếu có, chọn sealed interface root.
3. Một nhánh có cần shared state/constructors không? Cân nhắc sealed abstract class cho branch đó.
4. Có cố dùng record/enum extends abstract class không? Nếu có, thiết kế lại.
5. Mỗi ordinary direct subtype đã là final/sealed/non-sealed chưa?
6. Record có được để implicit final thay vì ghi final modifier không?
7. Enum không có class body hay có constant-specific class body?
8. Nếu enum có class body, đã hiểu implicitly sealed và synthetic subclasses chưa?
9. Có đang dùng enum constant như một singleton-like state không?
10. Nếu variant cần arbitrary payload, đã chọn record/class thay enum chưa?
11. Các direct permitted types ở đúng module/package chưa?
12. Nếu mọi direct subtypes cùng compilation unit, có muốn permits inference không?
13. Với multi-file project, đã khai báo permits rõ và build đồng bộ chưa?
14. Có non-sealed branch nào khiến hierarchy không truly closed không?
15. Nếu có, handler/exhaustiveness assumptions có xét descendants mới không?
16. Java target thật sự ≥17 cho sealed classes chưa?
17. Type-pattern switch có phải Java 21+ syntax, hoặc Java 17 preview đã được bật có chủ đích không?
18. Trong Java 17, đã dùng instanceof patterns/visitor một cách tương thích chưa?
19. Reflective API có dùng isSealed/getPermittedSubclasses đúng direct level không?
20. Có metadata record.isRecord/enum.isEnum riêng khi cần không?
21. Record components có defensive copy nếu mutable không?
22. Abstract constructors có xác lập invariants mà tránh call overridable methods không?
23. Interfaces có contract methods và accessors phù hợp không?
24. Các record variants có value equality khác enum identity được hiểu rõ không?
25. Có tests cho tất cả variants, reflection hierarchy, unknown/null input không?
26. Khi thêm permitted subtype/enum constant, đã cập nhật serializers, handlers và schemas chưa?
27. Sealed modifiers có tương thích module/package và library versioning không?
28. Có tránh hardcode compiler-generated enum subclass names không?
29. Có cân nhắc composition thay class inheritance khi cần reuse state trong record không?
30. Có giải thích rõ lý do sealed cho team thay vì chỉ dùng để giảm boilerplate không?

## 26. Bài tập có đáp án

**Câu 1.** Có thể dùng `sealed interface Result permits Ok, Error` với `record Ok(...) implements Result` không?

**Đáp án:** Có. Record là implicitly final và có thể implement sealed interface khi được permit.

**Câu 2.** Có thể `record Ok(...) extends AbstractResult` không?

**Đáp án:** Không. Record implicitly extends java.lang.Record, không extends custom class.

**Câu 3.** Enum có thể implements sealed interface không?

**Đáp án:** Có khi được permit và placement hợp lệ.

**Câu 4.** Enum có thể extends sealed abstract class không?

**Đáp án:** Không. Enum implicitly extends java.lang.Enum<E>.

**Câu 5.** Nếu muốn một family chứa record, enum và abstract class, root nào phù hợp?

**Đáp án:** Sealed interface, với abstract class làm một permitted branch khi cần.

**Câu 6.** `abstract sealed class` khác `sealed class` ở đâu?

**Đáp án:** Abstract class không thể tạo instance trực tiếp; sealed chỉ giới hạn direct subtypes. Có thể kết hợp.

**Câu 7.** `abstract final class` hợp lệ không?

**Đáp án:** Không, vì abstract cần khả năng subclassing còn final cấm subclassing.

**Câu 8.** Direct permitted ordinary class phải có những modifiers gì?

**Đáp án:** Chọn `final`, `sealed` hoặc `non-sealed` theo yêu cầu.

**Câu 9.** Record có cần ghi final modifier khi implement sealed interface?

**Đáp án:** Không; record implicitly final và modifier final không được ghi như ordinary class modifier.

**Câu 10.** Enum không có constant class body là implicitly gì?

**Đáp án:** Implicitly final.

**Câu 11.** Enum có constant-specific class body là implicitly gì?

**Đáp án:** Implicitly sealed, với compiler-generated constant-specific anonymous subclasses.

**Câu 12.** Có thể mở enum cho client subclasses bằng permits không?

**Đáp án:** Không. Enum-specific subclassing chỉ theo declared constant bodies.

**Câu 13.** `non-sealed class Extension implements SealedRoot` có hợp lệ khi được permit không?

**Đáp án:** Có, nếu Extension là direct permitted subtype và syntax/placement hợp lệ.

**Câu 14.** Có thể có `class Plugin extends Extension` sau đó không?

**Đáp án:** Có nếu Extension non-sealed và normal access/inheritance rules cho phép.

**Câu 15.** Plugin có phải xuất hiện trong Root.permits không?

**Đáp án:** Không, nếu Plugin không direct implements/extends Root mà chỉ qua non-sealed Extension.

**Câu 16.** Có thể `non-sealed class Open` không có sealed direct parent không?

**Đáp án:** Không.

**Câu 17.** Sealed interface có bảo đảm mọi transitive descendant luôn được liệt kê không?

**Đáp án:** Không nếu có non-sealed branch.

**Câu 18.** Java 17 có sealed classes chuẩn chưa?

**Đáp án:** Có, sealed là tính năng chuẩn từ Java 17.

**Câu 19.** Type-pattern switch trên sealed interface có là tính năng chuẩn của Java 17 không?

**Đáp án:** Không, còn preview; muốn chạy không preview dùng instanceof patterns/dispatch khác.

**Câu 20.** Java 17 hỗ trợ pattern matching instanceof chuẩn không?

**Đáp án:** Có.

**Câu 21.** Class.isSealed dùng làm gì?

**Đáp án:** Kiểm tra Class object đại diện sealed class/interface theo runtime metadata.

**Câu 22.** getPermittedSubclasses liệt kê điều gì?

**Đáp án:** Direct permitted subtypes, không tự liệt kê mọi descendants sâu hơn.

**Câu 23.** Record component List có tự bất biến sâu vì record final không?

**Đáp án:** Không. Referent List/mutable elements cần ownership/copy policy.

**Câu 24.** Hai `new Success("ok")` records có thể equals true không?

**Đáp án:** Có theo generated equality dựa trên component fields khi values giống nhau.

**Câu 25.** Hai references `Pending.INSTANCE` đến enum constant có == true không?

**Đáp án:** Có.

**Câu 26.** Nếu một enum implements sealed interface, từng enum constant có phải một direct interface implementor type không?

**Đáp án:** Không. Direct implementation class là enum; constants là instances.

**Câu 27.** Abstract class có thể chứa constructor và shared state không?

**Đáp án:** Có. Subclasses gọi super constructor phù hợp; abstract class vẫn không instantiate trực tiếp.

**Câu 28.** Named module cho phép direct permitted types ở package khác module không?

**Đáp án:** Không. Direct permitted types phải cùng module với sealed parent; có thể khác package trong cùng named module khi rules khác cho phép.

**Câu 29.** Unnamed module yêu cầu điều gì với permitted direct types?

**Đáp án:** Chúng phải cùng package với sealed parent.

**Câu 30.** `sealed interface Root {}` có thể omit permits khi những direct implementations cùng compilation unit không?

**Đáp án:** Có thể, khi Java có đủ thông tin và các rules tương ứng được đáp ứng.

**Câu 31.** Thêm record variant mới vào sealed interface có giống thêm enum constant không?

**Đáp án:** Không. Một việc thêm direct implementation class, việc kia thêm named instance trong cùng enum implementation type.

**Câu 32.** `sealed` có cấm gọi constructor nếu class không abstract không?

**Đáp án:** Không tự động; constructor accessibility và abstract modifier quyết định khả năng instantiate.

**Câu 33.** Có thể dùng composition để chia sẻ data với record không?

**Đáp án:** Có; record giữ component references đến shared value objects thay vì extends custom superclass.

**Câu 34.** Dùng `getClass()` để xác định enum declaring type có class bodies luôn đúng không?

**Đáp án:** Không. Dùng enum constant `getDeclaringClass()`.

**Câu 35.** Vai trò khác nhau của sealed và enum?

**Đáp án:** Sealed giới hạn direct subtype hierarchy; enum xác định named constant instances và enum-specific subclassing, không phải cùng một cơ chế.

## 27. Bài tập thực hành

### Bài 1 — cây kết quả gồm record và enum

Tạo `sealed interface ApiResult permits Ok, Fail, Pending`. Hai record Ok/Fail giữ payload; Pending enum có constant INSTANCE. Viết handler Java 17 dùng instanceof patterns và == cho Pending.

**Gợi ý:** Không viết `record Ok(...) extends ApiResult`; record dùng `implements`.

### Bài 2 — abstract branch chia sẻ constructor state

Tạo sealed interface Action permits Builtin, ManualAction; Builtin là enum; ManualAction là abstract sealed class permits StartAction/StopAction. Chia sẻ final String id trong ManualAction, rồi triển khai concrete action methods.

**Gợi ý:** Ordinary direct subclasses cần final/sealed/non-sealed.

### Bài 3 — non-sealed extension point

Tạo sealed interface Handler permits CoreHandler, PluginHandler; CoreHandler final, PluginHandler abstract non-sealed. Tạo class CustomPluginHandler extends PluginHandler. Giải thích vì sao PluginHandler nằm trong permits nhưng CustomPluginHandler không.

**Gợi ý:** Root permits chỉ direct subtype.

### Bài 4 — enum constant bodies và reflection

Tạo sealed interface Operation permits MathOperation; enum MathOperation implements Operation có ADD/MULTIPLY với constant-specific implementations. Dùng `isSealed()` và `getDeclaringClass()` để kiểm tra.

**Gợi ý:** Enum implicitly sealed khi có constant class body.

### Bài 5 — xem lại API khi thêm variant

Thêm record Warning(String message) vào sealed Outcome và cập nhật permits. Kiểm tra tất cả handler logic, tests, serializers và consumer APIs. Nếu dùng Java 17 standard, đừng dùng type-pattern switch mà không bật preview.

**Gợi ý:** Thêm direct permitted type khác thêm enum constant ở một existing enum.

## 28. Kết luận

**`sealed` kiểm soát quyền trực tiếp kế thừa/triển khai type; `abstract` kiểm soát khả năng tạo instance trực tiếp; `record` và `enum` là các class đặc biệt với superclass/instantiation rules riêng.** Chúng kết hợp rất tốt khi được sắp xếp đúng vai trò.

Đối với một family chứa **record, enum và abstract class**, hãy dùng **sealed interface làm root**. Các record và enum implements interface và được permits; một abstract sealed/non-sealed class cũng có thể implements interface và làm branch cho ordinary subclasses. Một sealed abstract class **không thể làm superclass trực tiếp của record hoặc enum**, vì record ngầm extends Record, enum ngầm extends Enum.

Mỗi ordinary permitted direct subtype phải chọn `final`, `sealed` hoặc `non-sealed`. Record implicitly final; enum implicitly final nếu không có constant bodies, implicitly sealed nếu có constant-specific class bodies, nhưng enum-specific anonymous subclasses không làm enum mở cho external subclassing. Non-sealed branch mở rộng hierarchy trở lại, nên “sealed” không đồng nghĩa toàn bộ descendants luôn đóng.

Cuối cùng, hãy dùng Java 17 features đúng phiên bản: **sealed và `instanceof` patterns là chuẩn**, trong khi type-pattern `switch` ở Java 17 vẫn preview. Kiểm tra module/package permits, reflection direct subtypes, immutable payload design và API/version compatibility để tận dụng sealed hierarchy mà không phá tính mở rộng hoặc dữ liệu hiện có.
