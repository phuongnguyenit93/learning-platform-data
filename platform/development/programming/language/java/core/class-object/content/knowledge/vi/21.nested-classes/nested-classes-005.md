# Truy cập thành viên `private` và thành viên bao ngoài trong lớp lồng nhau (Java 17+)

Một lớp được khai báo bên trong lớp khác có thể truy cập các thành viên `private` của lớp bao ngoài theo **quy tắc truy cập giữa những khai báo lồng nhau**. Chiều ngược lại cũng có thể xảy ra: code của lớp bao ngoài được phép sử dụng các thành viên `private` của lớp lồng thuộc cùng ngữ cảnh lồng nhau. Tuy nhiên, **được phép truy cập** không có nghĩa là **tự có sẵn một đối tượng để truy cập**.

Ví dụ, `Outer.Nested` là static nested class: code trong `Nested` có thể truy cập `private static` của `Outer`, nhưng muốn đọc `private int value` của một object `Outer` cụ thể thì phải có tham chiếu như `target.value`. Ngược lại, một **non-static inner class** gắn với enclosing instance có thể dùng `Outer.this.value` để chỉ rõ object bao ngoài.

Đây là bài Java Core, module **class-object**, phần **Lớp lồng nhau**; mục tiêu là hiểu đồng thời **quyền truy cập `private`**, **enclosing instance**, **phân giải tên**, và **tổ chức API**. Các chương trình độc lập dùng Java **17+**, có lệnh chạy và stdout để đối chiếu. Những đoạn chỉ mang tính minh họa hoặc chỉ ra lỗi compile-time được ghi rõ, tránh nhầm với chương trình đầy đủ.

## 1. Hai câu hỏi cần tách biệt trước khi đọc code

Khi gặp `nested.someField`, hãy hỏi lần lượt:

1. **Quyền truy cập:** vị trí code này có được phép truy cập member `someField` hay không? Modifier `private`/package-private/`protected`/`public` và quan hệ nesting quyết định.
2. **Đối tượng nhận (receiver):** `someField` là static hay instance? Nếu là instance, ta đang truy cập trường của **object nào**? Có biến `nested`, `Outer.this`, `this`, tham số `target` hoặc biểu thức reference hợp lệ không?

Hai câu hỏi độc lập. Có thể đủ quyền nhưng **thiếu receiver**. Có thể có receiver nhưng **không đủ quyền**. Chúng không thể thay thế nhau.

Ví dụ:

~~~java
class Vault {
    private int code = 7;

    static class Reader {
        int read(Vault target) {
            return target.code;
        }
    }
}
~~~

Đây là định nghĩa hợp lệ. `Reader` được quyền đọc field `private code` của `Vault` vì quan hệ lồng nhau, và method nhận một `Vault target` làm receiver. Nếu bỏ tham số và viết `return code;` trong `Reader` thì không hợp lệ: `Reader` không tự mang enclosing Vault instance.

## 2. Bảng so sánh các hoàn cảnh truy cập

| Nơi viết biểu thức | `Outer.privateStatic` | `Outer.privateInstance` | Có `Outer.this`? |
| --- | --- | --- | --- |
| Trong method instance của `Outer` | Được | Qua `this`/tên đơn giản phù hợp | `this` là Outer, không cần qualified this |
| Trong static method của `Outer` | Được | Chỉ khi có `Outer target` | Không |
| Trong `Outer.Inner` non-static | Được | Được qua enclosing instance thích hợp | Có |
| Trong `Outer.Nested` static | Được | Chỉ khi có reference Outer tường minh | Không |
| Trong một class độc lập không có private-access relationship | Không | Không, kể cả có Outer reference | Không theo quan hệ ấy |

Bảng minh họa cách hiểu trong **một khai báo Outer bình thường** và members được truy cập có mặt đúng scope. Thực tế, tên đơn giản còn chịu ảnh hưởng của shadowing và inheritance; khi có trùng tên nên dùng biểu thức qualified rõ ràng.

## 3. `private` vẫn được bảo vệ khỏi code bên ngoài

`private` không đồng nghĩa “chỉ những dòng code trong đúng cặp ngoặc của class sở hữu được dùng”. Java cho phép access giữa các **khai báo thuộc cùng quan hệ lồng nhau** theo JLS, giúp một enclosing class và nested types phối hợp làm implementation nội bộ.

Tuy nhiên, một code bên ngoài không thuộc phạm vi được cấp quyền **không tự được truy cập private** chỉ vì biết tên class, biết package hoặc đã có object reference:

~~~java
class Account {
    private int balance = 10;

    static class Reader {
        int read(Account target) {
            return target.balance;
        }
    }
}

// Trong class độc lập không cùng quan hệ lồng:
// int n = new Account().balance; // Cố ý không hợp lệ.
~~~

Đoạn code trên là **minh họa**; dòng truy cập sai đã được comment. Bên ngoài có thể dùng public/package API mà Account chủ động công bố, chứ không được coi `private` là mất tác dụng vì có nested class.

**Điểm quan trọng về an toàn API:** một nested public method có quyền đọc private field và **trả nó ra** có thể làm dữ liệu lộ ra ngoài. Java enforce quyền truy cập theo vị trí khai báo, không tự suy đoán bí mật nghiệp vụ của dữ liệu được trả.

## 4. Chương trình hoàn chỉnh 1 — static nested đọc `private` qua receiver

Tạo **`PrivateAccessWithReceiverDemo.java`**:

~~~java
final class Account {
    private static final String UNIT = "VND";
    private final String owner;
    private int balance;

    Account(String owner, int balance) {
        this.owner = owner;
        this.balance = balance;
    }

    private String summary() {
        return owner + ":" + balance;
    }

    static class Reader {
        String describe(Account source) {
            return UNIT + "/" + source.summary();
        }

        int balanceOf(Account source) {
            return source.balance;
        }
    }
}

public class PrivateAccessWithReceiverDemo {
    public static void main(String[] args) {
        Account.Reader reader = new Account.Reader();
        Account a = new Account("An", 50);
        Account b = new Account("Binh", 80);

        System.out.println("a=" + reader.describe(a));
        System.out.println("b=" + reader.describe(b));
        System.out.println("a balance=" + reader.balanceOf(a));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PrivateAccessWithReceiverDemo.java
java PrivateAccessWithReceiverDemo
~~~

**Stdout:**

~~~text
a=VND/An:50
b=VND/Binh:80
a balance=50
~~~

Giải thích: `Reader` là **static nested class** của Account; tạo `new Account.Reader()` không tạo hoặc gắn với bất kỳ Account instance nào. Reader được quyền dùng `UNIT` và gọi method `private summary()` của Account. Nó nhận tham số `source` để chỉ rõ object có dữ liệu được đọc; cùng một Reader có thể đọc nhiều Accounts.

**Đừng nhầm** `source.balance` là hợp lệ vì field balance “không thực sự private”. Field vẫn private; quyền truy cập chỉ được Java cấp trong ngữ cảnh lồng nhau thích hợp.

## 5. Chiều ngược lại: Outer truy cập `private` của nested class

Không chỉ nested class đọc private members của Outer. Code của enclosing Outer cũng có thể truy cập private fields/methods/constructors do nested class khai báo, theo quan hệ nesting.

~~~java
class Envelope {
    private static class Payload {
        private final String text;

        private Payload(String text) {
            this.text = text;
        }

        private String reveal() {
            return text;
        }
    }

    String open(String input) {
        Payload value = new Payload(input);
        return value.reveal();
    }
}
~~~

Đây là định nghĩa class minh họa hợp lệ. `Payload` là private static nested class, `Payload(String)` là private constructor, `Payload.reveal()` cũng private. Method `Envelope.open` được phép gọi những members ấy vì nó là code của enclosing type.

Một class hoàn toàn độc lập không được trực tiếp tạo `new Envelope.Payload(...)`. Nếu caller chỉ cần mở envelope, hãy công bố đúng outer method thích hợp thay vì làm nested implementation thành public.

## 6. Chương trình hoàn chỉnh 2 — quyền `private` hai chiều

Tạo **`BidirectionalPrivateDemo.java`**:

~~~java
final class Box {
    private final String prefix = "BOX";

    private static final class Token {
        private final int value;

        private Token(int value) {
            this.value = value;
        }

        private String label() {
            return "T" + value;
        }
    }

    String build(int number) {
        Token token = new Token(number);
        return prefix + ":" + token.label()
                + ":" + token.value;
    }

    private String suffix() {
        return "END";
    }

    class Inside {
        private int count;

        private void increase() {
            count++;
        }

        String report() {
            return prefix + ":" + suffix() + ":" + count;
        }
    }

    String update(Inside inside) {
        inside.increase();
        return inside.report();
    }
}

public class BidirectionalPrivateDemo {
    public static void main(String[] args) {
        Box box = new Box();
        System.out.println("token=" + box.build(7));

        Box.Inside inner = box.new Inside();
        System.out.println("before=" + inner.report());
        System.out.println("after=" + box.update(inner));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BidirectionalPrivateDemo.java
java BidirectionalPrivateDemo
~~~

**Stdout chính xác:**

~~~text
token=BOX:T7:7
before=BOX:END:0
after=BOX:END:1
~~~

Ở đây, Box được phép gọi `Token` private constructor và private method. `Box.update` gọi `Inside.increase()` dù nó private. Chiều ngược lại, `Inside.report` gọi `Box.suffix()` và đọc `Box.prefix` (đều private).

`Inside` được gắn với `box` nhờ `box.new Inside()`, còn `Token` là static nested class và không có enclosing Box instance tự động.

## 7. `Outer.this`: chỉ đúng cho inner class có enclosing instance

Trong non-static inner member class, `this` là object của **inner class**. `Outer.this` là reference tới **đối tượng Outer bao ngoài** đã gắn với inner object, khi loại qualified this ấy hợp lệ.

~~~java
class Outer {
    private int value = 10;

    class Inner {
        private int value = 20;

        int innerValue() {
            return this.value;
        }

        int outerValue() {
            return Outer.this.value;
        }
    }
}
~~~

Đây là class minh họa hợp lệ. Từ bên ngoài code có quyền gọi, ta tạo:

~~~java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

Lời gọi `outer.new Inner()` tạo Inner **liên kết với outer**. `this.value` trong Inner là 20; `Outer.this.value` là 10.

`Outer.this` không phải “cách truy cập static field”, cũng không phải biến cục bộ do người dùng đặt tên. Đó là cú pháp qualified `this` theo quy tắc của Java, và nó **không khả dụng trong một static nested class** nếu không có enclosing instance phù hợp.

## 8. Chương trình hoàn chỉnh 3 — `this` và `Outer.this`

Tạo **`OuterThisDemo.java`**:

~~~java
final class Workspace {
    private final String name;
    private int completed;

    Workspace(String name) {
        this.name = name;
    }

    class Job {
        private int completed;

        void finish() {
            this.completed++;
            Workspace.this.completed++;
        }

        String report() {
            return name + ":job=" + this.completed
                    + ",workspace=" + Workspace.this.completed;
        }
    }

    int totalCompleted() {
        return completed;
    }
}

public class OuterThisDemo {
    public static void main(String[] args) {
        Workspace a = new Workspace("A");
        Workspace b = new Workspace("B");

        Workspace.Job first = a.new Job();
        Workspace.Job second = a.new Job();
        Workspace.Job third = b.new Job();

        first.finish();
        first.finish();
        second.finish();
        third.finish();

        System.out.println("first=" + first.report());
        System.out.println("second=" + second.report());
        System.out.println("third=" + third.report());
        System.out.println("A total=" + a.totalCompleted());
        System.out.println("B total=" + b.totalCompleted());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 OuterThisDemo.java
java OuterThisDemo
~~~

**Stdout:**

~~~text
first=A:job=2,workspace=3
second=A:job=1,workspace=3
third=B:job=1,workspace=1
A total=3
B total=1
~~~

Mỗi Job có field `completed` riêng. Hai Jobs `first`, `second` cùng enclosing Workspace `a`, nên cả hai cập nhật tổng riêng của `a`; `third` liên kết với Workspace `b`.

**Một outer object có thể có nhiều inner objects**, và mỗi inner object gắn với một enclosing instance được chỉ định khi tạo. Không có một biến `Outer.this` toàn cục dùng chung cho mọi inner objects.

## 9. Che khuất tên: biến cục bộ, field của Inner và field của Outer

**Scope resolution** và **private access** là hai câu hỏi độc lập. Nếu parameter, inner field và outer field cùng tên:

~~~java
class Screen {
    private int width = 100;
    class Panel {
        private int width = 50;
        void show(int width) {
            System.out.println(width);            // parameter
            System.out.println(this.width);       // Panel field
            System.out.println(Screen.this.width);// Screen field
        }
    }
}
~~~

`Screen.this.width` được phép đọc field private của Screen từ nested Panel theo nesting access rules. Còn việc chọn đúng object khi có tên trùng thuộc **lexical shadowing**; xem bài **Che khuất tên và định danh bằng Outer.this** để học multi-level, inheritance và lambda contexts.

## 10. Chương trình hoàn chỉnh 4 — ba tầng tên `value`

Tạo **`ShadowedOuterMemberDemo.java`**:

~~~java
class Container {
    private int value = 10;

    class Member {
        private int value = 20;

        void print(int value) {
            System.out.println("parameter=" + value);
            System.out.println("inner=" + this.value);
            System.out.println("outer=" + Container.this.value);
        }
    }
}

public class ShadowedOuterMemberDemo {
    public static void main(String[] args) {
        Container container = new Container();
        Container.Member member = container.new Member();
        member.print(30);
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 ShadowedOuterMemberDemo.java
java ShadowedOuterMemberDemo
~~~

**Stdout:**

~~~text
parameter=30
inner=20
outer=10
~~~

Mỗi biểu thức trỏ đến **một nơi lưu dữ liệu khác nhau**. Nếu thay `this.value` bằng `value` trong `print`, đó là tham số 30, không phải field 20.

Khi có trùng tên, viết `Outer.this.field` còn làm **ý đồ chọn đúng enclosing object** hiển thị rõ trong code review.

## 11. Static nested class: quyền private có, nhưng `Outer.this` không có

Xét:

~~~java
class Device {
    private static int shared = 7;
    private int personal = 9;

    static class Detail {
        int readShared() {
            return shared;
        }

        int readPersonal(Device device) {
            return device.personal;
        }

        // int invalid() { return personal; }
        // int alsoInvalid() { return Device.this.personal; }
    }
}
~~~

Đây là class minh họa hợp lệ vì các dòng cố ý sai đã được comment.

`Detail` được quyền đọc `Device.personal` thông qua **device instance** mà caller cung cấp; nó không tự có `Device.this`. `Device.shared` là static member nên có thể đọc bằng tên class hoặc tên đơn giản nếu không bị shadow.

Việc sửa `personal` thành `public` **không làm `return personal;` hợp lệ** trong static nested class khi không có receiver. Cùng một member có thể vừa được phép truy cập vừa yêu cầu object cụ thể.

## 12. Chương trình hoàn chỉnh 5 — static nested truy cập private static và instance

Tạo **`StaticNestedPrivateDemo.java`**:

~~~java
class Meter {
    private static final String UNIT = "kWh";
    private final int reading;

    Meter(int reading) {
        this.reading = reading;
    }

    static class Formatter {
        String format(Meter source) {
            return source.reading + " " + UNIT;
        }

        String unit() {
            return UNIT;
        }
    }
}

public class StaticNestedPrivateDemo {
    public static void main(String[] args) {
        Meter.Formatter formatter = new Meter.Formatter();
        System.out.println("unit=" + formatter.unit());

        Meter first = new Meter(5);
        Meter second = new Meter(11);

        System.out.println("first=" + formatter.format(first));
        System.out.println("second=" + formatter.format(second));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 StaticNestedPrivateDemo.java
java StaticNestedPrivateDemo
~~~

**Stdout:**

~~~text
unit=kWh
first=5 kWh
second=11 kWh
~~~

`Meter.Formatter` được tạo **trước** bất kỳ Meter instance nào, chứng minh nó không cần enclosing object. Method `format` nhận Meter instance cụ thể để truy cập `private reading`.

Nếu Formatter được yêu cầu luôn xử lý một Meter duy nhất, nó có thể chủ động lưu field `private final Meter target` trong constructor. Đó là **reference tường minh**, không phải enclosing reference được Java thêm ngầm.

## 13. Private constructor của nested class và factory ở lớp bao

Một lớp bao có thể giấu nested implementation bằng `private static class`, dùng private constructor của nó, rồi công bố một giao diện đơn giản.

~~~java
interface Parser {
    int parse(String text);
}

final class Parsers {
    private Parsers() {
    }

    static Parser decimal() {
        return new DecimalParser();
    }

    private static final class DecimalParser implements Parser {
        private DecimalParser() {
        }

        @Override
        public int parse(String text) {
            return Integer.parseInt(text);
        }
    }
}
~~~

Đây là các class/interface minh họa hợp lệ. `Parsers.decimal()` nằm trong enclosing class nên có thể gọi private constructor `DecimalParser()`, rồi trả object dưới interface `Parser`.

Caller không có quyền viết `new Parsers.DecimalParser()` từ một class độc lập dù biết nested type tồn tại. **Quyền private của type và quyền private của constructor** đều được Java kiểm tra; nested class không tự công khai toàn bộ members.

## 14. Chương trình hoàn chỉnh 6 — Outer xây private nested implementation

Tạo **`PrivateNestedFactoryDemo.java`**:

~~~java
interface Formatter {
    String apply(String text);
}

final class Formatters {
    private static final String SEPARATOR = ":";

    private Formatters() {
    }

    static Formatter labeled(String label) {
        return new LabeledFormatter(label);
    }

    private static final class LabeledFormatter
            implements Formatter {
        private final String label;

        private LabeledFormatter(String label) {
            this.label = label;
        }

        private String prefix() {
            return label + SEPARATOR;
        }

        @Override
        public String apply(String text) {
            return prefix() + text;
        }
    }
}

public class PrivateNestedFactoryDemo {
    public static void main(String[] args) {
        Formatter a = Formatters.labeled("INFO");
        Formatter b = Formatters.labeled("WARN");

        System.out.println(a.apply("start"));
        System.out.println(b.apply("stop"));
        System.out.println("same=" + (a == b));
        System.out.println("runtime="
                + a.getClass().getSimpleName());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 PrivateNestedFactoryDemo.java
java PrivateNestedFactoryDemo
~~~

**Stdout:**

~~~text
INFO:start
WARN:stop
same=false
runtime=LabeledFormatter
~~~

`LabeledFormatter` là private static nested implementation. Code ở ngoài dùng interface Formatter. Class này có quyền đọc `Formatters.SEPARATOR` dù field đó private static; enclosing class có quyền gọi private constructor của LabeledFormatter.

`getClass()` trả runtime class **LabeledFormatter**, dù source code bên ngoài không được trực tiếp tham chiếu tới private nested type bằng tên.

## 15. Hai nested classes cùng thuộc một enclosing class có thể truy cập private nhau

Quy tắc access của các khai báo lồng nhau không chỉ áp dụng riêng cặp **Outer ↔ Nested**. Các member nested classes trong cùng ngữ cảnh có thể làm việc với private members của nhau nếu các quan hệ lồng nhau và access rules đáp ứng.

~~~java
class Group {
    private static class Writer {
        private final String data = "secret";
    }

    private static class Reader {
        private String read(Writer writer) {
            return writer.data;
        }
    }
}
~~~

Đây là class minh họa hợp lệ. `Reader` không phải subclass của `Writer`; nó vẫn có thể dùng `writer.data` vì quan hệ lexical nesting theo Java, và vì **đã có receiver** `writer`.

Điều này không có nghĩa “mọi class cùng package đều được đọc field private của nhau”. Hai top-level classes độc lập trong cùng package **không tự nhận quyền này**.

## 16. Chương trình hoàn chỉnh 7 — private access giữa các lớp lồng ngang hàng

Tạo **`SiblingNestedPrivateDemo.java`**:

~~~java
final class Workflow {
    private static class Data {
        private final String label;
        private final int code;

        private Data(String label, int code) {
            this.label = label;
            this.code = code;
        }
    }

    private static class Presenter {
        private String present(Data source) {
            return source.label + "#" + source.code;
        }
    }

    static String present(String label, int code) {
        Data data = new Data(label, code);
        Presenter presenter = new Presenter();
        return presenter.present(data);
    }
}

public class SiblingNestedPrivateDemo {
    public static void main(String[] args) {
        System.out.println(Workflow.present("A", 7));
        System.out.println(Workflow.present("B", 9));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SiblingNestedPrivateDemo.java
java SiblingNestedPrivateDemo
~~~

**Stdout:**

~~~text
A#7
B#9
~~~

`Workflow` được phép tạo các private nested types và gọi private constructors. `Presenter.present` đọc các private fields của `Data` dù Presenter và Data là **siblings**, không có quan hệ extends.

Nếu đưa `Presenter` ra một top-level class hoàn toàn độc lập, private access ấy không tự được giữ nguyên; phải thiết kế API thích hợp.

## 17. Nested classes không tự kế thừa field/method của enclosing class

Khai báo `class Outer { class Inner { ... } }` là **lexical nesting**, không phải `Inner extends Outer`.

Ví dụ:

~~~java
class Root {
    private int code = 3;

    class Leaf {
        int codeFromEnclosingObject() {
            return Root.this.code;
        }
    }
}
~~~

Đây là định nghĩa minh họa. `Leaf` không phải subtype của Root, nên không thể mặc định truyền Leaf vào một method nhận Root. Nó có thể gọi `Root.this.code` vì **có enclosing Root object** và được cấp quyền private, không phải vì kế thừa.

Trường hợp `Root` có method `protected` hoặc `public` cũng không làm Leaf tự trở thành subclass. Cần phân biệt **inheritance graph** và **lexical nesting graph**.

## 18. Enclosing instance ở nhiều cấp: `Outer.this` và `Middle.this`

Ở nhiều tầng **non-static inner**, một inner class có thể nhắc tới những enclosing instances hợp lệ bằng `Outer.this`, `Middle.this` và `this`. Quyền `private` không ngăn một member nested class hợp lệ truy cập private members của enclosing classes; nhưng mỗi biểu thức phải chọn đúng **receiver**.

~~~java
class City {
    private String name = "City";
    class District {
        private String name = "District";
        class Street {
            String cityName() { return City.this.name; }
            String districtName() { return District.this.name; }
        }
    }
}
~~~

`City.District.Street` vẫn là một inner type có scope/owner riêng; tên class lồng nhau **không đồng nghĩa** Street extends City hay District. Cách phân giải ba tầng và shadowing được dạy chính tại B216.

## 19. Chương trình hoàn chỉnh 8 — nhiều mức enclosing instance

Tạo **`MultipleEnclosingLevelsDemo.java`**:

~~~java
class Region {
    private final String name;

    Region(String name) {
        this.name = name;
    }

    class Zone {
        private final String name;

        Zone(String name) {
            this.name = name;
        }

        class Cell {
            private final String name;

            Cell(String name) {
                this.name = name;
            }

            String path() {
                return Region.this.name + "/"
                        + Zone.this.name + "/"
                        + this.name;
            }
        }
    }
}

public class MultipleEnclosingLevelsDemo {
    public static void main(String[] args) {
        Region region = new Region("North");
        Region.Zone zone = region.new Zone("Z1");
        Region.Zone.Cell cell = zone.new Cell("C9");

        System.out.println(cell.path());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 MultipleEnclosingLevelsDemo.java
java MultipleEnclosingLevelsDemo
~~~

**Stdout:**

~~~text
North/Z1/C9
~~~

`Cell` đọc ba private `name` fields qua ba receivers **đúng loại**: `Region.this`, `Zone.this` và `this`. Không field nào cần đổi thành public để truy cập từ nơi có quan hệ nested hợp lệ.

Nếu ở giữa là một **static nested class**, đường `Outer.this` không tự kéo xuyên qua static boundary như với chuỗi inner classes ở đây; cần kiểm tra từng enclosing-instance context thực tế.

## 20. Static boundary: không thể gọi `Outer.this` vượt qua nơi không có instance

Qualified `Host.this` chỉ có nghĩa khi lexical environment thật sự có **Host enclosing instance**. Sau static nested boundary:

~~~java
class Host {
    private int id = 1;
    static class StaticLayer {
        class Inner {
            int read(Host host) { return host.id; }
            // int wrong() { return Host.this.id; } // Không hợp lệ
        }
    }
}
~~~

`Inner` có thể dùng `StaticLayer.this`, **không** tự có `Host.this`; nhưng `host.id` vẫn hợp lệ nhờ tham số receiver tường minh và nesting access cho private member. Đây là phân biệt **permission** với **enclosing-instance existence**; bài B216 trình bày qualified-this đầy đủ.

## 21. Local class và anonymous class: vừa private access vừa capture biến cục bộ

Một **local class** khai báo trong method và một **anonymous class** tạo từ expression có quy tắc scope riêng. Chúng có thể tham chiếu members của enclosing class khi có ngữ cảnh hợp lệ, đồng thời capture các biến local/parameter thuộc scope nhưng phải `final` hoặc **effectively final**.

Ví dụ:

~~~java
class Greeter {
    private final String prefix = "Hello ";

    Runnable action(String name) {
        String punctuation = "!";

        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println(
                        prefix + name + punctuation);
            }
        }

        return new LocalTask();
    }
}
~~~

Đây là một class minh họa hợp lệ, chưa có main. `LocalTask` có thể đọc private `prefix` của enclosing Greeter object; tham số `name` và local `punctuation` **effectively final**, nên được capture.

Không thể sửa `punctuation` sau khi tạo local class rồi mong vẫn capture hợp lệ theo luật Java. **Capture biến local** khác với việc **giữ enclosing instance** và khác với **quyền truy cập private** — ba quy tắc phối hợp nhưng không phải một.

## 22. Chương trình hoàn chỉnh 9 — local và anonymous classes truy cập outer private

Tạo **`LocalAnonymousPrivateDemo.java`**:

~~~java
final class GreetingService {
    private final String prefix;

    GreetingService(String prefix) {
        this.prefix = prefix;
    }

    Runnable localTask(String name) {
        String end = "!";

        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println(
                        prefix + name + end);
            }
        }

        return new LocalTask();
    }

    Runnable anonymousTask(String name) {
        String end = "?";

        return new Runnable() {
            @Override
            public void run() {
                System.out.println(
                        GreetingService.this.prefix
                        + name + end);
            }
        };
    }
}

public class LocalAnonymousPrivateDemo {
    public static void main(String[] args) {
        GreetingService service =
                new GreetingService("Hi ");
        service.localTask("An").run();
        service.anonymousTask("Binh").run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LocalAnonymousPrivateDemo.java
java LocalAnonymousPrivateDemo
~~~

**Stdout:**

~~~text
Hi An!
Hi Binh?
~~~

Cả hai đối tượng Runnable đều thực thi sau khi `localTask`/`anonymousTask` đã trả về. Chúng vẫn có các giá trị được capture theo hợp đồng Java.

Ở anonymous class, `this` là instance của anonymous Runnable, còn `GreetingService.this` chỉ đúng enclosing GreetingService object. Bài viết `GreetingService.this.prefix` để tránh nhầm receiver.

**Không nên coi local/anonymous classes như static nested classes**: vị trí khai báo và khả năng capture biến khiến cơ chế và giới hạn khác nhau.

## 23. Lambda: `this` có nghĩa khác anonymous class

Trong một lambda expression, `this` không tạo một scope object `this` mới như anonymous class. Trong một instance method của Outer, `this` bên trong lambda chỉ chính **Outer instance** theo quy tắc lexical.

~~~java
class LoggerOwner {
    private final String tag = "OWNER";

    Runnable lambda() {
        return () -> System.out.println(this.tag);
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(LoggerOwner.this.tag);
            }
        };
    }
}
~~~

Đây là class minh họa hợp lệ. Hai implementations cùng in tag, nhưng **`this`** trong lambda và anonymous class có ý nghĩa khác nhau. Anonymous class có thể dùng `LoggerOwner.this` để truy cập enclosing instance.

Đừng dựa vào tên runtime class do compiler/JVM sinh cho lambda hoặc anonymous class để nhận diện nghiệp vụ. Vị trí private access và lexical capture phù hợp hơn để hiểu hành vi.

## 24. Chương trình hoàn chỉnh 10 — khác nhau giữa lambda `this` và anonymous `this`

Tạo **`LambdaAnonymousThisDemo.java`**:

~~~java
final class Display {
    private final String title = "Screen";

    Runnable lambda() {
        return () -> {
            System.out.println("lambda owner="
                    + this.getClass().getSimpleName());
            System.out.println("lambda title=" + title);
        };
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                Object self = this;
                System.out.println("anonymous is Display="
                        + (self instanceof Display));
                System.out.println("anonymous outer title="
                        + Display.this.title);
            }
        };
    }
}

public class LambdaAnonymousThisDemo {
    public static void main(String[] args) {
        Display display = new Display();
        display.lambda().run();
        display.anonymous().run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 LambdaAnonymousThisDemo.java
java LambdaAnonymousThisDemo
~~~

**Stdout mong đợi:**

~~~text
lambda owner=Display
lambda title=Screen
anonymous is Display=false
anonymous outer title=Screen
~~~

Ở lambda, `this` chỉ Display instance đang tạo lambda. Ở anonymous class, `this` là anonymous Runnable object, không phải Display. Qualified `Display.this` mới chỉ enclosing Display instance.

**Điều cần phân biệt:** trong anonymous class, `this` có kiểu của lớp anonymous, nên biểu thức trực tiếp `this instanceof Display` không biên dịch khi `Display` là `final` và hai kiểu không thể tương thích. Ví dụ Java 17 ở trên đã gán `Object self = this;` trước khi dùng `self instanceof Display`; phép kiểm tra này biên dịch và trả về `false`, trong khi `Display.this` vẫn truy cập được đối tượng bao ngoài.

## 25. Java 11+ nestmates: liên hệ với bytecode và JVM

Từ Java 11, JVM có cơ chế **nest-based access control**: các classes có cùng **nest host** được coi là **nestmates**, có thể thực hiện private access ở mức JVM theo quy tắc nest. Class files có thể mang attributes `NestHost` và `NestMembers`.

Khi biên dịch Java 17, một compiler hiện đại có thể dùng cơ chế này để cho member classes truy cập private members mà không cần một số synthetic accessor methods từng thường xuất hiện trong bytecode được biên dịch nhắm đến JDK cũ.

Tuy nhiên:

- **Quyền truy cập ở Java source** được đặc tả bởi JLS, không phải do người dùng tự khai báo nestmates.
- **JVM nestmate relationship** được xác lập bởi metadata/class loading rules; hai class có tên giống nhau hoặc cùng package không tự là nestmates.
- Không suy rằng mọi dạng private access đều tạo một synthetic method, cũng không suy rằng bytecode giữa mọi phiên bản compiler luôn giống nhau.
- Không nên sửa các binary names hoặc dùng reflection để “hack” private access khi chỉ cần thiết kế API có quyền truy cập phù hợp.

Thông tin JVM này giúp hiểu **vì sao hai member classes có thể truy cập private nhau**, đặc biệt khi đọc bytecode, compiler output hoặc debug Java 17.

## 26. Chương trình hoàn chỉnh 11 — kiểm tra nestmate metadata bằng Reflection

Tạo **`NestmateMetadataDemo.java`**:

~~~java
class Family {
    class Child {
    }

    static class Helper {
    }
}

public class NestmateMetadataDemo {
    public static void main(String[] args) {
        Class<?> parent = Family.class;
        Class<?> child = Family.Child.class;
        Class<?> helper = Family.Helper.class;

        System.out.println("host="
                + child.getNestHost().getSimpleName());
        System.out.println("same host="
                + (helper.getNestHost() == parent));
        System.out.println("nestmates="
                + child.isNestmateOf(helper));
        System.out.println("member child="
                + child.isMemberClass());
        System.out.println("member helper="
                + helper.isMemberClass());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 NestmateMetadataDemo.java
java NestmateMetadataDemo
~~~

**Stdout với class files được tạo cùng nhau bởi `javac` Java 17:**

~~~text
host=Family
same host=true
nestmates=true
member child=true
member helper=true
~~~

Cả `Family.Child` và `Family.Helper` là member classes của Family; JVM xem chúng thuộc cùng nest trong kết quả biên dịch bình thường này. `Class.isNestmateOf` có từ Java 11.

**Lưu ý:** lấy `Family.Child.class` chỉ truy xuất class token; nó **không yêu cầu** phải tạo một Family instance. Điều đó đúng dù Child là non-static inner member class, vì metadata class và construction object là hai việc khác nhau.

## 27. Quyền private ở nguồn Java không phải quyền reflection tùy tiện

Ngay cả khi nested code theo JLS được quyền đọc private field của enclosing class, **code từ một class độc lập không tự có quyền như vậy**. Reflection có access checks riêng; Java module system còn có quy tắc *strong encapsulation*.

Ví dụ lý thuyết:

~~~java
// Đoạn minh họa, không phải chương trình độc lập.
// Field secret = SomeType.class.getDeclaredField("secret");
// secret.setAccessible(true);
~~~

Không nên khuyến khích dùng reflection để vượt quyền private chỉ vì muốn tiết kiệm một getter/factory. Trong Java 17, `setAccessible(true)` có thể bị từ chối (chẳng hạn `InaccessibleObjectException`) nếu module không mở package cho reflective access phù hợp.

Nesting **không phá vỡ** module boundaries trên toàn hệ thống. Thiết kế API bình thường nên sử dụng private helpers và public/package contracts có chủ đích thay vì dựa vào reflection để sửa trạng thái nội bộ.

## 28. Trường hợp interface và member types

Các kiểu khai báo bên trong interface có những quy tắc riêng. Một **member class** được khai báo trong interface là **ngầm định `public static`**, không phải một inner class phải gắn với “interface object”.

~~~java
interface Protocol {
    class Packet {
        private final String payload;

        Packet(String payload) {
            this.payload = payload;
        }

        String read() {
            return payload;
        }
    }
}
~~~

Đây là đoạn code hợp lệ. Trong cùng package, caller có thể tạo `new Protocol.Packet("data")` nếu constructor access cho phép. Một object implement `Protocol` **không cần** tồn tại để tạo Packet.

Đừng đánh đồng “member type bên trong interface” với “inner class có enclosing interface instance”; interface **không có instance field** kiểu như class thường, và nested member type ở đây là static.

## 29. Encapsulation: quyền private có thể bị lộ qua API nested public

Một helper cùng nest có thể đọc private field, nhưng việc công bố thông tin vẫn do **method được gọi** quyết định:

~~~java
final class User {
    private final String passwordHash;

    User(String passwordHash) {
        this.passwordHash = passwordHash;
    }

    public static class Debugger {
        public String unsafeReveal(User user) {
            return user.passwordHash;
        }
    }
}
~~~

Đây là code minh họa **hợp lệ nhưng cố ý phản ví dụ về thiết kế bảo mật**. Caller có thể tạo `new User.Debugger()` và gọi `unsafeReveal`, vì method public đã chủ động xuất private state.

Java không cho caller đọc `user.passwordHash` trực tiếp ở class khác, nhưng **private access không tự cấm nested public helper trả giá trị**. Đừng viết helper như vậy với secrets; nên công bố kết quả đã lọc, masking hoặc thông tin nghiệp vụ an toàn.

Đồng thời, `private` là **ngữ nghĩa truy cập trong ngôn ngữ**, không phải một phương án encryption hoặc chính sách data classification. Đối với dữ liệu nhạy cảm, luôn cân nhắc logging, serialization và quyền truy cập ở các tầng khác.

## 30. Lifetime: inner class có thể giữ enclosing instance

Một member inner object có enclosing owner association. Khi callback được long-lived registry giữ lại, strong-reference path có thể khiến owner tiếp tục reachable dù ứng dụng đã đóng màn hình:

~~~text
Registry → inner listener → enclosing controller
~~~

Quyền truy cập `private` không quyết định thời gian sống object; lifetime thuộc **GC reachability và subscription lifecycle**. Static nested helpers không tự giữ owner, nhưng vẫn có thể giữ một `private final Outer owner` tường minh. Chi tiết rủi ro, cách unregister, weak references, callback method references và heap diagnostics nằm ở bài **Tham chiếu ngầm tới đối tượng bao ngoài và nguy cơ giữ bộ nhớ**.

## 31. Chọn thiết kế truy cập private để không làm rối trách nhiệm

Nested classes thường phù hợp cho:

- **Builder** của immutable class: đọc constructor/fields private trong quá trình `build()` mà không cần Outer instance sẵn có nếu dùng static nested Builder.
- **Iterator** hoặc helper liên kết với **một collection instance**: non-static inner class có thể dùng enclosing instance khi sự gắn kết đó đúng và có chủ đích.
- **Private adapter**: static nested implementation chỉ được công bố qua interface.
- **Parser/validator** liên quan chặt đến một class: private static nested helper đọc private static constants hoặc nhận outer values.
- **Record-like result** được lồng để nhóm API và dùng constructor có kiểm soát.

Nên ưu tiên **quyền truy cập nhỏ nhất cần thiết**; không biến mọi nested class thành public. Khi một helper lớn hoặc được dùng rộng rãi ở nhiều nơi, tách thành top-level class với API rõ ràng có thể dễ bảo trì hơn.

Quan hệ nesting không biến hai classes thành **một trách nhiệm duy nhất** theo thiết kế. Chỉ nên lồng khi sự liên hệ có nghĩa và code giữ được khả năng đọc hiểu.

## 32. Những lỗi compile-time cần nhận diện

| Mã/tình huống | Vấn đề thật sự | Hướng sửa |
| --- | --- | --- |
| `Outer.Nested` đọc `private int x` bằng tên `x` | Static nested thiếu Outer instance | Nhận `Outer target` rồi dùng `target.x` |
| `Outer.Nested` dùng `Outer.this.x` | Không có enclosing Outer instance | Dùng reference tường minh |
| Code độc lập dùng `outer.secret` dù secret private | Không có private access | Dùng API Outer cho phép |
| Code độc lập `new Outer.PrivateNested()` | Nested type không visible | Outer factory/method |
| Outer viết `nested.privateField` nhưng receiver là kiểu khác | Sai receiver/member resolution | Dùng đúng kiểu nested object |
| Inner dùng `x` và lấy nhầm field của Inner | Shadowing | Dùng `Outer.this.x` |
| Trong inner, `this` được tưởng là Outer | `this` là inner receiver | Dùng `Outer.this` |
| Trong anonymous class, `this` bị tưởng là Outer | `this` là anonymous object | Dùng qualified Outer.this |
| Local class capture biến bị gán lại | Biến không effectively final | Tách một local final value |
| Static nested trong generic Outer dùng `T` của Outer | Type parameter của Outer không có sẵn trong static context | Khai báo `Nested<U>` |
| Code nghĩ lexical nesting là `extends` | Không có subtype relationship | Chỉ dùng extends nếu đúng mô hình |
| Đặt helper public và trả dữ liệu private | Lộ representation/sensitive data qua API | Giảm visibility, trả projection an toàn |
| Biến Outer reference thành static để nested đọc | Thay đổi state từ theo instance sang shared | Truyền đúng target object |
| Có `private` nhưng dùng reflection để bypass | Có thể gặp module access denial | Thiết kế public/package contract phù hợp |

Một lỗi thiếu receiver **không nên sửa** bằng cách làm instance field của Outer thành static: việc đó thay đổi state từ **riêng từng object** thành state **chung toàn class**.

## 33. Quy trình phân tích một biểu thức truy cập

Khi cần chứng minh một nested expression đúng/sai, làm theo thứ tự:

1. **Vị trí code**: đang trong Outer, static nested, non-static inner, local, anonymous hay top-level class độc lập?
2. **Khai báo owner** của member: field/method thuộc class nào?
3. **Modifier access**: member private, protected, package-private hay public?
4. **Quan hệ nesting**: code đang truy cập có thuộc cùng phạm vi cho private access theo JLS không?
5. **Static hay instance**: member có cần receiver object không?
6. **Enclosing instance**: inner class có `Outer.this` thích hợp hay chỉ có một `Nested.this`?
7. **Có shadowing không?** Tên đơn giản có bị local/parameter/field gần hơn che không?
8. **Reference là null không?** Access tới instance field/method qua null sẽ có lỗi runtime dù compiler cho phép.
9. **Type compile-time có phù hợp?** Kể cả đủ quyền, expression vẫn cần kiểu chứa member phù hợp.
10. **Hậu quả API**: một method public nested trả private data ra ngoài có thật sự nên làm?

Quy trình này giúp không “chữa” lỗi truy cập private bằng cách mở rộng toàn bộ visibility không cần thiết.

## 34. Bài tập tự luyện

**Câu 1.** `private` member trong Outer có thể được static nested class của chính Outer đọc không? Nếu là instance field, cần thêm gì?

**Câu 2.** Trong `Outer.Inner`, `this` và `Outer.this` là cùng một object không?

**Câu 3.** `Outer` có được gọi private constructor/method của nested class `Outer.Helper` không?

**Câu 4.** Hai static nested classes `Outer.A`, `Outer.B` có thể đọc private members của nhau trong cùng ngữ cảnh không? Có cần object receiver?

**Câu 5.** `Outer.Nested` chứa `return outerValue;` với `outerValue` là private instance field của Outer. Vì sao lỗi không được chữa bằng đổi `private` thành `public`?

**Câu 6.** `Outer.Inner` có field `x=20`, Outer có `x=10`, method Inner nhận tham số `x=30`. Viết ba biểu thức lấy ba giá trị ấy.

**Câu 7.** Nếu một helper nested không cần trạng thái Outer, nên cân nhắc static hay non-static? Vì sao?

**Câu 8.** Static nested helper cần làm việc với nhiều Outer objects khác nhau. Cách truyền dependency hợp lý là gì?

**Câu 9.** Một inner object được tạo bằng `outerA.new Inner()` có tự động đổi sang enclosing `outerB` nếu được đưa vào biến khác không?

**Câu 10.** Class được khai báo bên trong một interface có cần instance của một implementation interface để tạo không?

**Câu 11.** `Outer.Inner` non-static nằm trong `Outer<T>`; nó có thể dùng type parameter T của Outer không? Static nested tương ứng thì sao?

**Câu 12.** Local class trong method dùng một local variable bị gán lại sau đó. Compiler có cho capture không?

**Câu 13.** `this` trong anonymous Runnable method chỉ object nào? Trong lambda tạo bởi Outer instance method thì sao?

**Câu 14.** `NestHost`, `NestMembers` và `Class.isNestmateOf` giúp nghiên cứu điều gì trên Java 17?

**Câu 15.** Hai top-level classes khác nhau nhưng trong cùng package có được dùng private field của nhau không?

**Câu 16.** Static nested implementation private được outer factory trả dưới interface public; caller có được dùng hành vi interface không?

**Câu 17.** Nếu một public nested helper lấy private password hash rồi công bố chuỗi ấy, Java đã chặn việc tiết lộ chưa?

**Câu 18.** Nếu `Outer.StaticLayer.InnerInStatic` có inner instance của StaticLayer, có tự tồn tại `Outer.this` không?

**Câu 19.** Vì sao giữ một inner listener lâu dài có thể làm enclosing controller còn reachable?

**Câu 20.** Có nên làm trường `instanceBalance` thành static chỉ vì static nested helper cần đọc nó không?

### Đáp án tham khảo

1. Có quyền private access theo nesting. Với instance field vẫn phải có Outer receiver, ví dụ `target.field`.
2. Không. `this` là inner instance, `Outer.this` là enclosing Outer instance.
3. Có, khi đáp ứng nesting access rules; nhưng phải có receiver phù hợp cho instance method/field.
4. Có thể theo nesting rules; field instance vẫn phải đọc trên đối tượng A/B cụ thể.
5. Lỗi là **thiếu receiver**, không phải thiếu visibility.
6. `x` (30), `this.x` (20), `Outer.this.x` (10).
7. Static nested, vì không cần implicit enclosing reference và giúp ownership rõ hơn.
8. Truyền `Outer target` vào method/constructor; hoặc truyền chỉ dữ liệu cần dùng.
9. Không. Enclosing instance là quan hệ được gắn khi tạo inner object, không đổi do phép gán biến.
10. Không. Member class của interface là ngầm định static.
11. Inner member class có thể dùng T trong ngữ cảnh thích hợp; static nested không tự dùng T, phải khai báo parameter riêng.
12. Không. Captured local variable/parameter phải final hoặc effectively final.
13. Anonymous `this` là anonymous object; lambda `this` giữ ngữ nghĩa enclosing lexical context.
14. Tìm hiểu JVM nest-based private access và class metadata quan hệ nestmate.
15. Không, chỉ cùng package không cấp private access.
16. Có. Interface công bố hành vi; concrete implementation type có thể được giấu.
17. Chưa. Method công khai đã chủ động trả dữ liệu; private field không tự áp chính sách dữ liệu nghiệp vụ.
18. Không. Enclosing instance của inner đó là StaticLayer; StaticLayer không mang Outer instance ngầm.
19. Vì inner object thường có reference tới enclosing instance, ảnh hưởng object reachability.
20. Không. Điều đó thay đổi state sharing; hãy truyền đúng Outer receiver.

## 35. Checklist thực hành

- Xác định rõ member được khai báo trong class nào?
- Đã tách **quyền truy cập private** và **receiver object** chưa?
- Khi static nested đọc instance field Outer, đã có reference tường minh?
- Khi dùng `Outer.this`, đang ở một non-static inner context có enclosing instance hợp lệ?
- Có dùng `this` đúng cho inner/lambda/anonymous code?
- Nếu hai fields cùng tên, đã phân biệt parameter, `this.field`, `Outer.this.field`?
- Đã hiểu nested class không tự là subclass của Outer?
- Enclosing Outer có cố tình expose private state qua public nested methods không?
- Private nested constructor được dùng qua một outer factory khi cần giấu implementation?
- Nếu có nhiều nested sibling classes, có hiểu private access không đồng nghĩa cùng package access?
- Nếu local/anonymous class capture variable, biến có effectively final?
- Nếu outer generic, static nested tự khai báo type parameters riêng?
- Nếu nested object sống lâu, có hiểu ảnh hưởng của enclosing reference/explicit reference?
- Đã tránh thay instance field thành static chỉ để chữa thiếu receiver?
- Có kiểm tra cú pháp Java 17 bằng ví dụ chạy được và phân biệt snippet minh họa?
- Khi đọc bytecode, có hiểu nestmates Java 11+ mà không nhầm với source language access?
- Những private fields quan trọng có được bảo vệ qua **API được công bố** chứ không chỉ modifier?

## 36. Tài liệu Java 17 để đối chiếu

- [JLS 17 §6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): điều kiện truy cập members và classes, gồm private access.
- [JLS 17 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): scope và khả năng nhìn thấy tên.
- [JLS 17 §6.4 — Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4): trường hợp trùng tên.
- [JLS 17 §8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): enclosing instances.
- [JLS 17 §8.5 — Member Type Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.5): nested member types.
- [JLS 17 §8.5.1 — Static Member Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.5.1): static nested members.
- [JLS 17 §15.8.4 — Qualified this](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): cú pháp `Outer.this`.
- [JLS 17 §15.9 — Class Instance Creation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): `outer.new Inner()` và `new Outer.Nested()`.
- [JLS 17 §15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): lexical context và `this` trong lambda.
- [JLS 17 §8.1.3 và §14.3 — Local Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3): local class scope.
- [JVMS 17 §5.4.4 — Access Control](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): nestmate private access ở mức JVM.
- [Java SE 17 API — Class.getNestHost](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getNestHost()): nest host.
- [Java SE 17 API — Class.isNestmateOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isNestmateOf(java.lang.Class)): kiểm tra nestmates.

**Kết luận:** Quan hệ lồng nhau cho phép code của Outer và các nested types truy cập những `private` members tương ứng theo Java access rules. Nhưng **quyền truy cập không tạo ra receiver**: non-static inner class có enclosing instance và có thể dùng `Outer.this`, còn static nested class không có reference ấy, nên phải nhận `Outer target` để đọc instance state. Khi nhiều tên trùng nhau, dùng `this.field` và `Outer.this.field` để chọn đúng nơi lưu dữ liệu. Hãy bảo vệ cả **phạm vi truy cập** lẫn **những API public có khả năng đưa private state ra ngoài**.
