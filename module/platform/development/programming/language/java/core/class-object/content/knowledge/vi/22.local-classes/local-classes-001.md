# Khai báo lớp có tên trong phương thức hoặc khối lệnh trong Java

**Local class (lớp cục bộ)** là một class **có tên**, được khai báo **bên trong một block**, chẳng hạn thân method, constructor, instance initializer hoặc static initializer. Tên class này chỉ có phạm vi trong block tương ứng, theo quy tắc lexical scope của Java.

~~~java
class GreetingService {
    String greet(String name) {
        class Formatter {
            String format() {
                return "Xin chào, " + name;
            }
        }

        Formatter formatter = new Formatter();
        return formatter.format();
    }
}
~~~

`Formatter` là một **local class**: nó có tên, có thể có constructor/fields/methods và có thể tạo nhiều instances. Nhưng declaration của `Formatter` **không trở thành member class của GreetingService**; code bên ngoài `greet` không thể dùng `GreetingService.Formatter`.

Trong ví dụ, `Formatter.format()` đọc parameter `name` từ method bao ngoài. Đây là **variable capture**. Java chỉ cho local class capture một local variable hoặc parameter nếu biến đó **final hoặc effectively final** và thỏa điều kiện definite assignment ở chỗ dùng.

Bài học thuộc **Java Core — Class & Object / Lớp cục bộ**, áp dụng **Java 17+**. Các ví dụ chạy độc lập có filename, lệnh `javac`/`java` và stdout để đối chiếu. Những snippets chỉ minh họa được nêu rõ.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích local class là **class có tên trong block**, không phải top-level/member class.
2. Viết và instantiate local class bên trong một method.
3. Biết tên local class bắt đầu có phạm vi từ declaration và không dùng được bên ngoài block.
4. Phân biệt local class declaration với instance creation expression.
5. Hiểu mỗi `new Local()` có thể tạo một object mới, nhưng các lần gọi method vẫn dùng cùng local class declaration/runtime type.
6. Biết local class có fields, methods, constructors, initializers, inheritance và interfaces.
7. Hiểu local class có thể truy cập local variables/parameters **final hoặc effectively final** của enclosing block.
8. Biết gán lại captured local variable làm mất effectively final và gây compile error.
9. Phân biệt **gán lại captured reference** với **mutate object mà reference đang trỏ**.
10. Hiểu cách captured variables tiếp tục được sử dụng sau khi enclosing method return.
11. Biết local class trong **instance context** có thể truy cập enclosing instance state.
12. Phân biệt `this` bên trong local class với `Outer.this` khi có enclosing Outer instance.
13. Biết local class trong **static context** không tự có `Outer.this`.
14. Hiểu shadowing và name resolution giữa local class fields, parameters và outer members.
15. Khai báo local class trong constructor hoặc initializer block.
16. Phân biệt local class với **member inner**, **static nested**, **anonymous class** và **lambda**.
17. Dùng local class để implement interface và trả object qua public type phù hợp.
18. Hiểu generic method type parameters và local class type parameters.
19. Biết quy tắc Java 17 về static declarations bên trong local classes.
20. Phân biệt local class với **local record** và **local enum** có ngữ nghĩa static.
21. Hiểu reflection metadata `isLocalClass()`, `getEnclosingMethod()` và tên binary.
22. Đánh giá lợi ích, giới hạn API, lifetime của captured references và test behavior.

## 2. Khái niệm lớp cục bộ

Ví dụ:

~~~java
class Outer {
    void execute() {
        class Local {
            void run() {
                System.out.println("run");
            }
        }

        new Local().run();
    }
}
~~~

`Local` là một **named class declaration**, nhưng chỉ có tên trong scope của `execute` sau declaration. Nó không phải một field, không phải method và không phải class member của Outer.

**Ba tầng riêng biệt:**

~~~text
Outer source declaration
    |
    +--- method execute() body
              |
              +--- declaration: class Local { ... }
              |
              +--- invocation: new Local()
                                      |
                                      v
                               Local object #1
~~~

- **Declaration:** định nghĩa type Local và code của nó.
- **Instantiation:** `new Local()` tạo object.
- **Scope:** nơi source code được phép dùng simple name `Local`.

Một method có thể gọi nhiều lần, tạo nhiều Local objects. Java không định nghĩa một class mới với identity khác cho mỗi lần gọi method; local class được compile thành class metadata có phạm vi source lexical, và instances được tạo khi runtime thực thi `new`.

## 3. Ví dụ đầu tiên: khai báo và gọi local class

Tạo **`LocalGreetingDemo.java`**:

~~~java
public class LocalGreetingDemo {
    static String greet(String name) {
        class Formatter {
            String format() {
                return "Xin chao, " + name;
            }
        }

        Formatter formatter = new Formatter();
        return formatter.format();
    }

    public static void main(String[] args) {
        System.out.println(greet("Mai"));
        System.out.println(greet("An"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalGreetingDemo.java
java LocalGreetingDemo
~~~

Stdout:

~~~text
Xin chao, Mai
Xin chao, An
~~~

Mỗi `greet(...)` call có parameter `name` riêng. Mỗi `new Formatter()` tạo object mới; method của Formatter được phép đọc `name` vì name không bị gán lại sau khi được nhận.

## 4. Local class được khai báo trong block nào?

Local class declaration có thể xuất hiện trong **block**, ví dụ:

- Block của một instance method.
- Block của static method.
- Block của constructor.
- Instance initializer block.
- Static initializer block.
- Một nested block `{ ... }`, `if` block, `try` block hoặc những block có syntax phù hợp.

Tên class chỉ được dùng trong **lexical scope** áp dụng cho declaration đó. Ví dụ:

~~~java
void example() {
    {
        class InBlock {
        }

        InBlock value = new InBlock();
    }

    // InBlock other = new InBlock(); // Lỗi: ngoài scope.
}
~~~

Bản thân object của local class có thể **sống lâu hơn block**, nếu reference được trả về hoặc được lưu dưới một kiểu có thể truy cập từ ngoài, chẳng hạn một interface. Scope của **tên** và lifetime của **object** là hai vấn đề khác nhau.

## 5. Chương trình chạy: phạm vi block

Tạo **`LocalBlockDemo.java`**:

~~~java
public class LocalBlockDemo {
    public static void main(String[] args) {
        System.out.println("begin");

        {
            class Job {
                String describe() {
                    return "inside block";
                }
            }

            Job job = new Job();
            System.out.println(job.describe());
        }

        System.out.println("end");
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalBlockDemo.java
java LocalBlockDemo
~~~

Stdout:

~~~text
begin
inside block
end
~~~

Sau dấu `}` của nested block, simple name `Job` không còn thuộc scope bên ngoài. Tuy vậy JVM đã có thể tạo Job instance khi block chạy; scope giới hạn **truy cập tên trong source code**, không tự động gọi destructor cho object.

## 6. Phạm vi của tên local class bắt đầu từ declaration

Giống các declarations cục bộ khác, **vị trí khai báo** quan trọng.

~~~java
void example() {
    // Local value = new Local(); // Sai: Local chưa được khai báo.

    class Local {
    }

    Local value = new Local();    // Hợp lệ.
}
~~~

Bạn không thể tùy ý đưa `class Local` xuống cuối method rồi sử dụng trước như thể đó là member class được tìm thấy ở toàn class body.

### Không thể ghi qualified name như member class

~~~java
class Outer {
    void method() {
        class Local {
        }
    }
}

// Outer.Local value; // Không hợp lệ: Local không là member type.
~~~

Nếu cần API trả về type cho caller bên ngoài, trả về **interface/supertype có thể truy cập**, không expose local class name.

## 7. Local class có thể có state và constructor

Ví dụ:

~~~java
void report() {
    class Row {
        private final int index;

        Row(int index) {
            this.index = index;
        }

        int index() {
            return index;
        }
    }

    Row first = new Row(1);
    Row second = new Row(2);
}
~~~

Mỗi Row object có instance field `index` riêng, constructor của nó được gọi khi `new Row(...)`. Local class **không phải lambda**, nên có đầy đủ nhiều cơ chế class thường dùng, dù declaration scope hẹp.

### Chương trình chạy

Tạo **`LocalConstructorDemo.java`**:

~~~java
public class LocalConstructorDemo {
    static void show() {
        class Row {
            private final int index;

            Row(int index) {
                this.index = index;
            }

            String label() {
                return "row-" + index;
            }
        }

        Row first = new Row(1);
        Row second = new Row(2);

        System.out.println(first.label());
        System.out.println(second.label());
        System.out.println("same object=" + (first == second));
    }

    public static void main(String[] args) {
        show();
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalConstructorDemo.java
java LocalConstructorDemo
~~~

Stdout:

~~~text
row-1
row-2
same object=false
~~~

## 8. Local class và `final` / effectively final

Một local class có thể tham chiếu local variable hoặc method parameter trong surrounding lexical scope khi biến **final hoặc effectively final**.

**Explicit final:**

~~~java
final int base = 10;

class Adder {
    int add(int value) {
        return base + value;
    }
}
~~~

**Effectively final:**

~~~java
int base = 10; // Không khai báo final, nhưng không gán lại.

class Adder {
    int add(int value) {
        return base + value;
    }
}
~~~

**Effectively final** nghĩa là biến không bị gán lại theo quy tắc definite assignment và effective-final của Java. Điều đó cho phép capture dù developer không viết keyword `final`.

Lưu ý: captured value là giá trị của local variable/parameter theo semantics; nếu là object reference, **giá trị được capture là reference** tới object đó, không phải deep copy object.

## 9. Chương trình chạy: capture hai local values

Tạo **`CaptureLocalDemo.java`**:

~~~java
public class CaptureLocalDemo {
    static int calculate(int input) {
        final int base = 10;
        int factor = 2;

        class Calculator {
            int apply() {
                return base + factor * input;
            }
        }

        return new Calculator().apply();
    }

    public static void main(String[] args) {
        System.out.println("result=" + calculate(3));
        System.out.println("next=" + calculate(5));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CaptureLocalDemo.java
java CaptureLocalDemo
~~~

Stdout:

~~~text
result=16
next=20
~~~

`base` explicit final; `factor` và `input` không bị gán lại nên effectively final. Local class Calculator đọc cả ba. Mỗi method invocation có bộ argument/local values riêng.

## 10. Điều gì làm mất effectively final?

Khi một local variable đã được gán rồi lại reassign, nó không còn effectively final:

~~~java
void example() {
    int count = 1;
    count = 2;

    class Reader {
        int read() {
            // return count; // Lỗi biên dịch khi capture count.
            return 0;
        }
    }
}
~~~

Đây là **snippet cố ý tránh dòng lỗi bằng comment**. Nếu bỏ comment ở `return count`, javac báo captured local variable phải final hoặc effectively final.

### Không phải mọi phép ++ đều vô hại

~~~java
int count = 0;
// count++; // Nếu cần capture count ở local class thì điều này làm mất effectively final.
~~~

Increment/compound assignment là modification của **local variable value**, nên vi phạm effective-final requirement. Ngay cả nếu modification xảy ra **sau class declaration**, compiler vẫn xét toàn bộ scope applicable.

### Tại sao có quy tắc này?

Local variables thường thuộc method invocation lifecycle; local class instance có thể sống lâu hơn invocation. Việc capture stable values giúp tránh một số nhầm lẫn về “local variable sống và được cập nhật đồng thời”. Java cho phép captured reference trỏ tới mutable object, nhưng biến tham chiếu được capture không được reassign.

## 11. Mutation của object vẫn có thể hợp lệ

Phân biệt:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();

class Appender {
    void add(String name) {
        names.add(name); // Sửa List object, không gán lại biến names.
    }
}
~~~

`names` là effectively final vì không bị gán sang List khác. Method `names.add` sửa **object được tham chiếu**, nên compile hợp lệ.

Nhưng:

~~~java
// names = new ArrayList<>(); // Nếu có dòng này, names không còn effectively final.
~~~

**Effectively final không đồng nghĩa immutable**. Nó chỉ áp dụng cho biến được capture.

## 12. Chương trình chạy: capture mutable reference

Tạo **`CapturedMutableDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CapturedMutableDemo {
    static List<String> build() {
        List<String> names = new ArrayList<>();

        class Collector {
            void add(String name) {
                names.add(name);
            }
        }

        Collector collector = new Collector();
        collector.add("Mai");
        collector.add("An");

        return names;
    }

    public static void main(String[] args) {
        System.out.println(build());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CapturedMutableDemo.java
java CapturedMutableDemo
~~~

Stdout:

~~~text
[Mai, An]
~~~

`names` reference không bị gán lại; List contents vẫn thay đổi. Nếu nhiều threads cùng mutate List thông qua captured references, effective-final không tự bảo đảm thread safety.

## 13. Local class có thể sống lâu hơn enclosing method

Ví dụ method trả về interface:

~~~java
static Runnable makeTask(String text) {
    class PrintTask implements Runnable {
        @Override
        public void run() {
            System.out.println(text);
        }
    }

    return new PrintTask();
}
~~~

Sau khi `makeTask("Java")` trả về, caller giữ một `Runnable`. Local class name `PrintTask` không visible với caller, nhưng **object vẫn tồn tại và method run() vẫn dùng captured text**.

Chính vì vậy capture không thể dựa vào việc method local stack variable “còn đang hoạt động” theo mô hình quá đơn giản. Compiler/JVM thực hiện semantics capture thích hợp để object hoạt động sau khi method đã return.

## 14. Chương trình chạy: trả local class qua interface

Tạo **`LocalRunnableDemo.java`**:

~~~java
public class LocalRunnableDemo {
    static Runnable makeTask(String message) {
        class PrintTask implements Runnable {
            @Override
            public void run() {
                System.out.println(message);
            }
        }

        return new PrintTask();
    }

    public static void main(String[] args) {
        Runnable first = makeTask("Java");
        Runnable second = makeTask("Objects");

        first.run();
        second.run();

        System.out.println("same class=" +
                (first.getClass() == second.getClass()));
        System.out.println("same object=" + (first == second));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalRunnableDemo.java
java LocalRunnableDemo
~~~

Stdout:

~~~text
Java
Objects
same class=true
same object=false
~~~

Có **hai PrintTask instances**, nhưng chúng được tạo từ cùng declaration của local class tại một vị trí source. Chúng có same runtime class metadata trong cùng class-loader context; captured message khác nhau theo từng method invocation.

## 15. Chương trình chạy: method parameter được capture

Một method parameter không bị reassign được phép được local class capture.

Tạo **`CapturedParameterDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class CapturedParameterDemo {
    static IntUnaryOperator makeAdder(int offset) {
        class Adder implements IntUnaryOperator {
            @Override
            public int applyAsInt(int value) {
                return value + offset;
            }
        }

        return new Adder();
    }

    public static void main(String[] args) {
        IntUnaryOperator plusTen = makeAdder(10);
        IntUnaryOperator plusTwenty = makeAdder(20);

        System.out.println(plusTen.applyAsInt(5));
        System.out.println(plusTwenty.applyAsInt(5));
    }
}
~~~

~~~bash
javac -encoding UTF-8 CapturedParameterDemo.java
java CapturedParameterDemo
~~~

Stdout:

~~~text
15
25
~~~

Mỗi Adder lưu/nhận access đến captured offset của invocation tạo nó. Public API chỉ lộ interface `IntUnaryOperator`; tên class `Adder` vẫn local.

## 16. Local class và enclosing instance

Nếu local class được khai báo trong **instance method** của một outer class, nó có thể tham chiếu instance members của enclosing outer:

~~~java
class Document {
    private String title;

    String render() {
        class Renderer {
            String output() {
                return title;
            }
        }

        return new Renderer().output();
    }
}
~~~

Trong `Renderer.output()`, `title` được lấy từ **enclosing Document instance**. Nếu bạn muốn nhấn mạnh owner cụ thể, có thể dùng `Document.this.title` trong instance context hợp lệ.

Điều này khác với capture một method local variable: outer field không cần effectively final. Nếu outer mutable và thay title sau đó, local class có thể quan sát giá trị mới.

## 17. `this` và `Outer.this` bên trong local class

Trong một instance method của local class:

- `this` là local class object.
- `Outer.this` là enclosing Outer object, khi declaration có enclosing Outer instance.
- Một parameter tên trùng field có thể shadow field.
- `Outer.this.member` nói rõ field của outer.

Tạo **`LocalOuterThisDemo.java`**:

~~~java
public class LocalOuterThisDemo {
    static final class Document {
        private String title;

        Document(String title) {
            this.title = title;
        }

        String render(String prefix) {
            class Renderer {
                String output() {
                    return prefix + ":" + Document.this.title;
                }

                boolean hasDocument() {
                    return Document.this != null;
                }
            }

            Renderer renderer = new Renderer();
            return renderer.output() +
                    " attached=" + renderer.hasDocument();
        }
    }

    public static void main(String[] args) {
        Document document = new Document("Java");
        System.out.println(document.render("doc"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalOuterThisDemo.java
java LocalOuterThisDemo
~~~

Stdout:

~~~text
doc:Java attached=true
~~~

Local Renderer capture `prefix` (parameter effectively final) và truy cập `Document.this.title` (outer instance field). Đây là **hai nguồn dữ liệu khác nhau** dù code đều ở trong cùng local class.

## 18. Local class trong static context

Static method không có enclosing outer **instance**. Local class khai báo trong static method vẫn là named local class và có thể capture effectively final local variables/parameters:

~~~java
class Utility {
    static Runnable task(String text) {
        class Worker implements Runnable {
            @Override
            public void run() {
                System.out.println(text);
            }
        }
        return new Worker();
    }
}
~~~

Nhưng nó không thể tham chiếu `Utility.this` vì static context không có receiver object.

### Chương trình chạy

Tạo **`StaticLocalClassDemo.java`**:

~~~java
public class StaticLocalClassDemo {
    private static final String PREFIX = "job:";

    static Runnable task(String name) {
        class Worker implements Runnable {
            @Override
            public void run() {
                System.out.println(PREFIX + name);
            }
        }

        return new Worker();
    }

    public static void main(String[] args) {
        Runnable job = task("compile");
        job.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticLocalClassDemo.java
java StaticLocalClassDemo
~~~

Stdout:

~~~text
job:compile
~~~

Static local Worker được phép truy cập static constant PREFIX và capture effectively final parameter name. Không có `StaticLocalClassDemo.this` trong Worker khai báo từ static method.

## 19. Local class trong constructor

Bạn có thể khai báo local class trong constructor block và dùng nó để thực hiện validation hoặc tính toán nội bộ. Nhưng **không nên gọi overridable methods hoặc publish `this` từ constructor trước khi hoàn tất state initialization**.

Tạo **`ConstructorLocalClassDemo.java`**:

~~~java
public class ConstructorLocalClassDemo {
    static final class Interval {
        private final int length;

        Interval(int length) {
            class Validator {
                boolean valid() {
                    return length > 0;
                }
            }

            if (!new Validator().valid()) {
                throw new IllegalArgumentException("length must be positive");
            }
            this.length = length;
        }

        int length() {
            return length;
        }
    }

    public static void main(String[] args) {
        Interval interval = new Interval(7);
        System.out.println("length=" + interval.length());

        try {
            new Interval(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorLocalClassDemo.java
java ConstructorLocalClassDemo
~~~

Stdout:

~~~text
length=7
rejected=length must be positive
~~~

Constructor local Validator đọc constructor parameter length. Đây là ví dụ hợp lệ nhưng với validation đơn giản, code direct `if (length <= 0)` có thể ngắn và dễ đọc hơn. Dùng local class khi thực sự có cấu trúc/hành vi đáng được đặt tên, không tạo class chỉ để thay một biểu thức điều kiện.

## 20. Local class trong instance initializer block

Một instance initializer block chạy trong quá trình xây dựng object, ở thứ tự do Java specification quy định. Bạn có thể khai báo local class trong block:

Tạo **`InstanceInitializerLocalDemo.java`**:

~~~java
public class InstanceInitializerLocalDemo {
    static final class Holder {
        private final String text;

        {
            class Initializer {
                String make() {
                    return "ready";
                }
            }
            text = new Initializer().make();
        }

        String text() {
            return text;
        }
    }

    public static void main(String[] args) {
        Holder holder = new Holder();
        System.out.println(holder.text());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstanceInitializerLocalDemo.java
java InstanceInitializerLocalDemo
~~~

Stdout:

~~~text
ready
~~~

Local class `Initializer` chỉ visible trong initializer block. Cách này có thể hợp lệ nhưng thường không cần thiết nếu một helper method đơn giản là đủ. Hiểu constructor chaining, field initializer và instance block order trước khi dùng phức tạp.

## 21. Local class trong static initializer block

Static initializer block cũng là block hợp lệ để khai báo một named local class.

Tạo **`StaticInitializerLocalDemo.java`**:

~~~java
public class StaticInitializerLocalDemo {
    private static final String STATUS;

    static {
        class Initializer {
            String create() {
                return "initialized";
            }
        }
        STATUS = new Initializer().create();
    }

    public static void main(String[] args) {
        System.out.println(STATUS);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticInitializerLocalDemo.java
java StaticInitializerLocalDemo
~~~

Stdout:

~~~text
initialized
~~~

Không có enclosing instance của StaticInitializerLocalDemo trong static initializer. Local class vẫn có thể tạo object và sử dụng những values có scope hợp lệ trong block.

## 22. Local class có thể extends class hoặc implements interface

Một local class là class đúng nghĩa, nên nó có thể **extend một class** (không final) hoặc **implement interfaces** theo Java inheritance rules.

Ví dụ:

~~~java
abstract class Task {
    abstract String description();
}

void process() {
    class LocalTask extends Task implements Runnable {
        @Override
        String description() {
            return "local";
        }

        @Override
        public void run() {
            System.out.println(description());
        }
    }

    new LocalTask().run();
}
~~~

Đây là snippet minh họa; định nghĩa Task/method context cần đặt trong một class hợp lệ. Local class không phải subclass của **enclosing outer** chỉ vì nó được khai báo trong outer method. `extends` và lexical nesting là hai quan hệ độc lập.

### Chương trình chạy

Tạo **`LocalInheritanceDemo.java`**:

~~~java
public class LocalInheritanceDemo {
    static abstract class BaseTask {
        abstract String label();
    }

    static Runnable newTask(String text) {
        class LocalTask extends BaseTask implements Runnable {
            @Override
            String label() {
                return text;
            }

            @Override
            public void run() {
                System.out.println("task=" + label());
            }
        }

        return new LocalTask();
    }

    public static void main(String[] args) {
        Runnable task = newTask("review");
        task.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalInheritanceDemo.java
java LocalInheritanceDemo
~~~

Stdout:

~~~text
task=review
~~~

## 23. Local class không thể có các access modifiers của class member

Một local class declaration không dùng access modifiers như `public`, `protected` hoặc `private`, cũng không dùng `static` modifier theo cách khai báo một member class:

~~~java
void process() {
    // private class Local {} // Sai.
    // public class Local {}  // Sai.
    // static class Local {}  // Sai đối với local class declaration.

    class Local {             // Hợp lệ.
    }
}
~~~

Đây là snippet minh họa cố ý comment các dòng không hợp lệ.

Có thể dùng những modifiers hợp lệ với local class theo JLS, chẳng hạn `final` hoặc `abstract` ở tình huống tương ứng. Local class không trở thành public member type vì method bao ngoài public.

### Truy cập từ ngoài bằng gì?

Trả một object qua supertype/interface có thể truy cập:

~~~java
Runnable create() {
    class LocalTask implements Runnable {
        public void run() {
            System.out.println("done");
        }
    }
    return new LocalTask();
}
~~~

Caller nhận Runnable, không dùng được tên LocalTask ngoài block.

## 24. Scope và shadowing

Nếu method parameter và local class field trùng tên, local class method có thể dùng qualification để rõ đích:

~~~java
int number = 10;

class Local {
    private int number = 20;

    String describe(int number) {
        return number + ":" + this.number;
    }
}
~~~

Trong `describe(30)`, parameter number là 30, `this.number` là 20. Nếu local class nằm trong instance method của Outer và Outer có field cùng tên, `Outer.this.number` trỏ outer instance field khi context hợp lệ.

### Chương trình chạy

Tạo **`LocalShadowingDemo.java`**:

~~~java
public class LocalShadowingDemo {
    static String make() {
        int number = 10;

        class Local {
            private int number = 20;

            String describe(int number) {
                return "parameter=" + number +
                        ", field=" + this.number;
            }

            String captured() {
                return "outer local=" + number;
            }
        }

        Local value = new Local();
        return value.describe(30) + "; " + value.captured();
    }

    public static void main(String[] args) {
        System.out.println(make());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalShadowingDemo.java
java LocalShadowingDemo
~~~

Stdout:

~~~text
parameter=30, field=20; outer local=20
~~~

Ở method `captured()`, tên number **ưu tiên instance field của Local**, nên trả 20 — **không** truy cập local variable number=10 cùng tên ở method bao ngoài. Không có cú pháp `OuterMethod.this.number` dành cho một local variable bị shadowed.

Nếu muốn dùng captured outer local, hãy chọn tên không trùng, hoặc đổi thiết kế để truyền value vào constructor/field mang tên khác.

## 25. Tránh hiểu nhầm shadowing local variable và member field

Một field của local class có thể shadow surrounding local variable với cùng tên. Muốn buộc đọc local variable không bị shadow, bạn có thể đổi tên hoặc đưa qua constructor:

~~~java
int outerNumber = 10;

class Local {
    private final int innerNumber;

    Local(int innerNumber) {
        this.innerNumber = innerNumber;
    }

    String describe() {
        return outerNumber + "/" + innerNumber;
    }
}
~~~

Các tên rõ nghĩa thường tốt hơn cố dùng qualification phức tạp. Local variables trong một enclosing method **không** có đối tượng receiver như `this` để tham chiếu theo cùng cách với outer instance fields.

## 26. Scope của local class trong các nhánh

Có thể khai báo local class trong từng nhánh block, nhưng tên mỗi declaration chỉ visible trong block đó:

~~~java
void perform(boolean special) {
    if (special) {
        class Result {
            String value() {
                return "special";
            }
        }
        System.out.println(new Result().value());
    } else {
        class Result {
            String value() {
                return "normal";
            }
        }
        System.out.println(new Result().value());
    }
}
~~~

Đây là snippet minh họa. Hai `Result` declarations nằm trong hai scopes riêng, không phải một runtime class thống nhất được parameterized bởi boolean. Nếu muốn cùng một kiểu chung cho cả hai nhánh, tạo interface/top-level/member class hoặc trả một common supertype phù hợp.

### Đọc code dễ hơn

Không nên nhân bản nhiều local class implementations chỉ để tránh một `if` trong một method nhỏ. Local class có ích khi logic riêng thực sự phức tạp và chỉ liên quan đến block ấy.

## 27. Local class và generic method type parameter

Một local class có thể sử dụng type parameter từ method bao ngoài trong phù hợp context:

~~~java
static <T> String describe(T value) {
    class Description {
        String text() {
            return "value=" + value;
        }
    }
    return new Description().text();
}
~~~

`T` là method type parameter ở compile time; local class sử dụng value là effectively final.

### Chương trình chạy

Tạo **`LocalGenericMethodDemo.java`**:

~~~java
public class LocalGenericMethodDemo {
    static <T> String describe(T value) {
        class Description {
            String text() {
                return "value=" + value;
            }
        }

        return new Description().text();
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(17));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalGenericMethodDemo.java
java LocalGenericMethodDemo
~~~

Stdout:

~~~text
value=Java
value=17
~~~

Type erasure có nghĩa runtime Class object của local Description không được tạo riêng cho `T=String` hoặc `T=Integer` mỗi lần gọi.

## 28. Local class cũng có generic type parameter của riêng nó

Ví dụ:

~~~java
void example() {
    class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    Holder<String> words = new Holder<>("Java");
    Holder<Integer> numbers = new Holder<>(17);
}
~~~

Local class Holder có type parameter T, độc lập với type parameters của outer method/class nếu có. Sau khi block kết thúc, tên Holder không còn visible trong source context khác, nhưng objects có thể được dùng qua supertype/interface nếu cần.

### Chương trình chạy

Tạo **`GenericLocalClassDemo.java`**:

~~~java
public class GenericLocalClassDemo {
    static void run() {
        class Holder<T> {
            private final T value;

            Holder(T value) {
                this.value = value;
            }

            T get() {
                return value;
            }
        }

        Holder<String> first = new Holder<>("Java");
        Holder<Integer> second = new Holder<>(17);

        System.out.println("first=" + first.get());
        System.out.println("second=" + second.get());
        System.out.println("same runtime class=" +
                (first.getClass() == second.getClass()));
    }

    public static void main(String[] args) {
        run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericLocalClassDemo.java
java GenericLocalClassDemo
~~~

Stdout:

~~~text
first=Java
second=17
same runtime class=true
~~~

## 29. Java 17: static declarations trong local class

Một tài liệu cũ có thể nói inner/local classes không được có static members ngoại trừ constant variables. **Từ Java SE 16, restrictions về static declarations trong inner classes đã được nới bỏ**.

Trong Java 17, một local class có thể có static method/field theo ngôn ngữ hiện hành. Điều này **không biến local class thành member class**, cũng không làm tên class accessible ngoài enclosing block.

### Chương trình chạy với Java 17

Tạo **`StaticMembersLocalDemo.java`**:

~~~java
public class StaticMembersLocalDemo {
    public static void main(String[] args) {
        class LocalMath {
            static int doubleOf(int value) {
                return value * 2;
            }
        }

        System.out.println(LocalMath.doubleOf(7));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 StaticMembersLocalDemo.java
java StaticMembersLocalDemo
~~~

Stdout:

~~~text
14
~~~

Dù có static method, `LocalMath` vẫn được khai báo **local trong main method** và không dùng được bằng `StaticMembersLocalDemo.LocalMath` từ code bên ngoài. Static method không có receiver `this` và không thể capture surrounding instance/local context như một instance method.

## 30. Local record trong Java 17: tên cục bộ nhưng không capture enclosing state

`Record` có thể khai báo trong block nhưng mang ngữ nghĩa **implicitly static**, không phải ordinary local class. Trong record body, không thể trực tiếp dùng `Outer.this` hoặc capture local variable từ enclosing method; truyền dữ liệu qua components/constructor:

~~~java
void calculate(int input) {
    record Pair(int first, int second) {
        int total() { return first + second; }
    }

    Pair value = new Pair(input, 3); // Truyền input, không capture.
    System.out.println(value.total());
}
~~~

Đây là **method fragment**, không phải chương trình độc lập. Record components mặc định final nhưng nếu mang mutable objects thì chưa chắc deep immutable. Bài chuyên **Local enum và local record được ngầm định static** trình bày đầy đủ các quy tắc về constructors, generic context, value semantics và capture restrictions.

## 31. Local enum: các trạng thái có tên trong phạm vi hẹp

Một enum khai báo trong method/block chỉ có tên khả dụng trong block liên quan:

~~~java
void run() {
    enum State { NEW, DONE }
    State current = State.NEW;
    System.out.println(current.name());
}
~~~

Đây là **method fragment**. Local enum có ngữ nghĩa **implicitly static** và các constants cố định, không có `Outer.this` hay trực tiếp capture local variables như ordinary local class. Không dùng `new State()` để tạo enum constant. Những chi tiết về constructors, identity, switch và runtime behavior thuộc bài chuyên local enum/record.

## 32. Local class so với anonymous class

**Local named class**:

~~~java
class Handler implements Runnable {
    @Override
    public void run() {
        System.out.println("run");
    }
}

Runnable handler = new Handler();
~~~

**Anonymous class**:

~~~java
Runnable handler = new Runnable() {
    @Override
    public void run() {
        System.out.println("run");
    }
};
~~~

Cả hai có thể implement interface. Khác biệt:

- Local named class có **tên trong block**, có thể tạo nhiều instances bằng `new Handler()` và khai báo constructors.
- Anonymous class declaration không có simple class name để gọi constructor theo cách bình thường; instance creation diễn ra trong expression.
- Anonymous class thường phù hợp one-off implementation, local named class phù hợp behavior có tên/structure/reuse trong block.
- Cả hai có thể capture effectively final locals từ lexical context theo quy tắc thích hợp.

## 33. Local class so với lambda

Với functional interface, lambda thường ngắn hơn:

~~~java
Runnable job = () -> System.out.println("run");
~~~

So sánh:

| Khía cạnh | Local class | Anonymous class | Lambda |
| --- | --- | --- | --- |
| Có tên trong source block | Có | Không | Không |
| Có constructor khai báo riêng | Có | Không theo thông thường | Không |
| Có nhiều instance fields/methods tự do | Có | Có trong anonymous class body | Không |
| Có class body extends/implements tùy ý | Có | Có anonymous subclass/implementation | Không |
| Capture effectively final locals | Có | Có | Có |
| `this` trong body | Local instance | Anonymous instance | Enclosing instance (lexical) |
| Thích hợp logic dài có state riêng | Có | Có thể | Thường kém phù hợp |
| Thích hợp callback một dòng | Có nhưng dài | Có nhưng dài | Thường phù hợp |

**Điểm rất dễ nhầm:** `this` trong lambda **không** chỉ “lambda instance” như `this` trong anonymous/local class body. Lambda xử lý `this` theo lexical context của nơi nó được viết.

## 34. Chương trình chạy: local và anonymous metadata

Tạo **`LocalVsAnonymousDemo.java`**:

~~~java
public class LocalVsAnonymousDemo {
    static Runnable local() {
        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println("local");
            }
        }

        return new LocalTask();
    }

    static Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous");
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = local();
        Runnable b = anonymous();

        a.run();
        b.run();

        System.out.println("a is local=" +
                a.getClass().isLocalClass());
        System.out.println("b is anonymous=" +
                b.getClass().isAnonymousClass());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalVsAnonymousDemo.java
java LocalVsAnonymousDemo
~~~

Stdout:

~~~text
local
anonymous
a is local=true
b is anonymous=true
~~~

Local class có tên `LocalTask` trong method; anonymous class là type không có tên source class declaration. Không hardcode generated binary class names vì compiler/JVM có thể khác nhau.

## 35. Reflection metadata của local class

Java reflection cung cấp:

- `type.isLocalClass()`: type có phải local class không.
- `type.isAnonymousClass()`: type có phải anonymous class không.
- `type.isMemberClass()`: type có phải member class không.
- `type.getEnclosingMethod()`: enclosing method nếu class được khai báo ở method theo metadata.
- `type.getEnclosingConstructor()`: enclosing constructor khi class được khai báo ở constructor.
- `type.getEnclosingClass()`: enclosing class nếu có.
- `type.getDeclaringClass()`: declaring class với member class; local class không phải member class nên thường null.

**Không nhầm:** `getEnclosingClass()` trả **Class object mô tả type**. Nó không lấy một instance object cụ thể đang được capture.

## 36. Chương trình chạy: quan sát local class metadata

Tạo **`LocalClassMetadataDemo.java`**:

~~~java
public class LocalClassMetadataDemo {
    static Class<?> localType() {
        class Worker {
        }

        return Worker.class;
    }

    public static void main(String[] args) {
        Class<?> type = localType();

        System.out.println("simple=" + type.getSimpleName());
        System.out.println("local=" + type.isLocalClass());
        System.out.println("member=" + type.isMemberClass());
        System.out.println("anonymous=" + type.isAnonymousClass());
        System.out.println("enclosing method=" +
                type.getEnclosingMethod().getName());
        System.out.println("enclosing class=" +
                (type.getEnclosingClass() ==
                        LocalClassMetadataDemo.class));
        System.out.println("declaring null=" +
                (type.getDeclaringClass() == null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalClassMetadataDemo.java
java LocalClassMetadataDemo
~~~

Stdout:

~~~text
simple=Worker
local=true
member=false
anonymous=false
enclosing method=localType
enclosing class=true
declaring null=true
~~~

Phân biệt **enclosing method/class declaration metadata** với việc một local class object có capture một particular variable/outer instance nào đó. Reflection `Class` không cung cấp một generic API `getCapturedLocals()` có semantics như đọc “mọi local variables hiện tại”.

## 37. Generated binary name là implementation detail

Compiler thường tạo file bytecode có naming pattern như `Outer$1Local.class` cho local class, nhưng code production không nên phụ thuộc chính xác vào số thứ tự `1` hoặc binary name generated.

Nếu bạn muốn hỏi type identity ở runtime, dùng `obj.getClass()` hoặc `Local.class` bên trong nơi tên Local còn visible. Nếu cần reflection metadata, dùng `isLocalClass()`, `getEnclosingMethod()` và related APIs thay vì parse generated name.

Một local class vẫn là runtime class được JVM định nghĩa; không vì scope nhỏ mà nó là “một object được interpreter dựng trong method” không có type metadata.

## 38. Có cần tạo class mới mỗi lần gọi method?

Không. Mỗi invocation của method có thể tạo **instance mới** của local class, nhưng declaration của local class không phải là một class definition độc lập được tạo lại theo từng method call.

Ví dụ `LocalRunnableDemo`: hai Runnable objects khác identity nhưng `getClass() ==` true. Captured values (message) khác nhau giữa instances, còn runtime class metadata thì giống nhau trong cùng class-loader identity.

### Khi class loading có thể xảy ra?

Thời điểm class loading/linking/initialization do JVM semantics quyết định. Đừng cố suy ra “mỗi lần vào method đều load class lại” hoặc “local class không cần class file”. Nội dung học cần nắm: **declaration scope khác lifetime instance và runtime type identity**.

## 39. Local class không tự tạo class-level API public

Dù method bao ngoài được khai báo `public`, local class vẫn là local declaration:

~~~java
public Runnable create() {
    class PrivateImplementation implements Runnable {
        @Override
        public void run() {
            System.out.println("hello");
        }
    }

    return new PrivateImplementation();
}
~~~

Caller gọi `create()` sẽ nhận Runnable, không trực tiếp gọi `new PrivateImplementation()` bên ngoài method. Đây là cách che giấu implementation detail hiệu quả.

Nếu class cần tái sử dụng ở nhiều methods hoặc modules, một `private static nested class` hoặc top-level class có thể phù hợp hơn việc copy-paste cùng local declaration vào nhiều blocks.

## 40. Captured references và memory retention

Một returned local-class object có thể giữ access đến captured objects:

~~~java
static Runnable task(SomeResource resource) {
    class Runner implements Runnable {
        public void run() {
            resource.execute();
        }
    }
    return new Runner();
}
~~~

Đoạn là pseudocode minh họa vì `SomeResource` chưa được định nghĩa. Nếu Runner được lưu trong global registry lâu dài, resource có thể bị giữ reachable lâu hơn dự tính.

Tương tự, nếu local class được khai báo trong instance method và dùng outer state, object có thể giữ enclosing outer reachable. Hãy quản lý **register/unregister**, callback lifetime và ownership giống như với anonymous/inner member classes.

### Thận trọng khi đổi sang lambda

Lambda capture cũng có thể giữ references khi cần. Chuyển local class sang lambda **không tự chữa mọi memory-retention problem**; phải thiết kế lifecycle và dependencies phù hợp.

## 41. Thread safety khi capture mutable data

Effectively final chỉ hạn chế **reassignment của local variable**. Nếu captured reference trỏ một mutable object, các threads vẫn có thể đụng data races.

Ví dụ:

~~~java
java.util.List<String> shared = new java.util.ArrayList<>();
class Job implements Runnable {
    public void run() {
        shared.add("x");
    }
}
~~~

Nếu có nhiều threads chạy Job trên cùng ArrayList mà không synchronization, code không có thread-safety guarantee chỉ vì shared variable effectively final.

### Chương trình chạy: atomic shared state

Tạo **`AtomicCaptureDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCaptureDemo {
    static Runnable counterTask(AtomicInteger counter) {
        class IncrementTask implements Runnable {
            @Override
            public void run() {
                counter.incrementAndGet();
            }
        }

        return new IncrementTask();
    }

    public static void main(String[] args) {
        AtomicInteger count = new AtomicInteger();
        Runnable task = counterTask(count);

        task.run();
        task.run();

        System.out.println("count=" + count.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicCaptureDemo.java
java AtomicCaptureDemo
~~~

Stdout:

~~~text
count=2
~~~

`counter` parameter effectively final, nhưng object AtomicInteger thay đổi nội bộ qua thread-safe method. Capture và concurrency synchronization là hai vấn đề khác nhau.

## 42. Vì sao không thể tùy ý thay local class bằng member class?

Local class có access đến **local variables/parameters** từ block nơi được khai báo. Member class được khai báo ở class body, **không** nằm trong scope của một method parameter cụ thể.

Ví dụ:

~~~java
void process(String message) {
    class Printer {
        String text() {
            return message;
        }
    }
}
~~~

Nếu chuyển Printer ra class body như member class, `message` không còn in scope. Phải đưa nó qua constructor/field:

~~~java
class Printer {
    private final String message;

    Printer(String message) {
        this.message = message;
    }

    String text() {
        return message;
    }
}
~~~

Local class giúp code gần data flow; member/static nested class giúp reuse rõ và quản lý dependencies explicit.

## 43. Khi nào nên dùng local class?

Dùng local class có lợi khi:

- Một đoạn logic có **tên ngữ nghĩa rõ**, chỉ dùng trong một method/block.
- Implementation cần nhiều methods/fields hoặc constructor nhỏ.
- Muốn implement interface để trả một object nhưng giấu implementation type.
- Logic cần capture một vài effectively final values và ít phụ thuộc ngoài.
- Local implementation đáng đọc hơn anonymous class hoặc lambda phức tạp.
- Không có nhu cầu reuse trực tiếp từ methods khác.

Ví dụ: method tạo một customized comparator với vài helper methods, một iterable adapter gắn với snapshot dữ liệu cục bộ, callback có nhiều bước nhưng chỉ dùng tại một điểm.

### Khi nào tránh?

- Logic chỉ một biểu thức → lambda/helper method có thể dễ đọc hơn.
- Cần dùng class từ nhiều methods → private static nested/top-level class rõ hơn.
- Local class quá lớn, làm method dài/khó test.
- Có nhiều captured mutable dependencies khó thấy → constructor injection/explicit dependencies rõ hơn.
- API public thực sự cần expose type → local name không phù hợp.
- Có concurrency/lifecycle phức tạp → tách type riêng với ownership contract.

## 44. Bảng so sánh nhanh

| Khái niệm | Scope/type | Capture outer local variables? | Có tên tái sử dụng trong block? |
| --- | --- | --- | --- |
| Local named class | Block chứa declaration | Có, final/effectively final | Có |
| Member inner class | Class body không static | Không capture local của một method cụ thể | Có ở member type scope |
| Static nested class | Class body có static | Không | Có |
| Anonymous class | Expression | Có, final/effectively final | Không |
| Lambda | Expression với functional interface | Có, final/effectively final | Không |
| Local record | Block, implicitly static | Không capture local qua body | Có |
| Local enum | Block, implicitly static | Không capture enclosing instance state | Có |

Đây là bảng khái niệm chính, không thay thế các quy tắc access/definite assignment và type inference cụ thể của Java.

## 45. Checklist kiểm tra khi gặp compile error

**Bước 1 — Tên local class còn trong scope?** Không dùng trước declaration hoặc sau block.

**Bước 2 — Đã dùng access modifier không hợp lệ?** Local class không `public/private/protected/static` declaration modifier theo cách member class.

**Bước 3 — Captured local variable có effectively final?** Tìm reassignment, increment hoặc compound assignment trong scope.

**Bước 4 — Local/parameter đã definitely assigned trước khi dùng?** Capture không bỏ qua quy tắc definite assignment.

**Bước 5 — Có shadowing không?** `this.field` của local class có thể che tên local variable trong enclosing method.

**Bước 6 — Đang ở static context?** Không dùng `Outer.this` khi không có enclosing Outer instance.

**Bước 7 — Method override có đủ visibility?** Implement `Runnable.run()` phải `public`.

**Bước 8 — Local record/enums có đang cố capture?** Chúng implicitly static, hãy truyền values qua components/constructor hoặc method parameters.

**Bước 9 — Compile target đúng?** Các static declarations trong inner/local class và local records/enums cần xét Java version; bài này dùng Java 17.

**Bước 10 — Object được return qua accessible type chưa?** Không cố dùng local class name như public return type ở class scope.

## 46. Bài tập 1 — Scope của tên class

~~~java
static void run() {
    {
        class Helper {}
        Helper first = new Helper();
    }

    // Helper second = new Helper();
}
~~~

**Đáp án:** Nếu bỏ comment ở dòng cuối, code không biên dịch vì `Helper` không còn trong lexical scope. Local class declaration không phải member của outer type.

## 47. Bài tập 2 — Gán lại captured variable

~~~java
static void run() {
    int number = 5;
    number++;

    class Reader {
        int read() {
            // return number;
            return 0;
        }
    }
}
~~~

**Đáp án:** `number` không effectively final vì có ++, nên nếu bỏ comment ở `return number` sẽ có compile error. Sửa bằng cách không reassign number hoặc truyền giá trị vào constructor của Reader.

## 48. Bài tập 3 — Mutation khác reassignment

~~~java
static void run() {
    java.util.List<String> names =
            new java.util.ArrayList<>();

    class Writer {
        void write() {
            names.add("Java");
        }
    }

    new Writer().write();
}
~~~

**Đáp án:** Hợp lệ, vì `names` reference không bị reassign; mutation của List object không phá effective final của local variable. Tuy nhiên List vẫn mutable.

## 49. Bài tập 4 — Runtime class của hai instances

Một method khai báo `class Local implements Runnable` rồi return `new Local()`. Caller gọi method hai lần. `a == b` và `a.getClass() == b.getClass()` lần lượt thế nào?

**Đáp án:** Thường `a == b` false vì hai `new Local()` tạo objects riêng; `a.getClass() == b.getClass()` true trong same runtime class-loader identity vì chúng dùng cùng local class declaration.

## 50. Bài tập 5 — Static context

Local class trong static method có thể dùng `Outer.this.name` không?

**Đáp án:** Không có enclosing Outer instance trong static context, nên không dùng `Outer.this`. Nếu cần value, truyền Outer reference explicit hoặc khai báo local class trong instance method.

## 51. Bài tập 6 — Local record có capture không?

~~~java
static int compute(int input) {
    record Pair(int a, int b) {}
    Pair value = new Pair(input, 2);
    return value.a() + value.b();
}
~~~

**Đáp án:** Hợp lệ. Record không trực tiếp capture input; code truyền input làm một component vào constructor. Đây là cách đúng để dùng data from surrounding scope với local record.

## 52. Bài tập 7 — Anonymous và lambda `this`

Tại sao `this` bên trong lambda không giống `this` trong method của local class?

**Đáp án:** Lambda sử dụng lexical `this` của enclosing context, còn method của local class là instance method nên `this` trỏ local class object. Không dùng lambda syntax như “anonymous class rút gọn” trong mọi trường hợp.

## 53. Bài tập 8 — Quyết định thiết kế

Một parser helper dài 30 methods, dùng ở năm methods và không capture locals. Có nên giữ local class copy lại trong năm blocks?

**Đáp án:** Thường không. Đặt helper thành `private static nested class`, top-level class hoặc dedicated parser service giúp reuse, test và ownership rõ hơn. Local class phù hợp logic nhỏ, cục bộ, gắn với một block.

## 54. Sai lầm phổ biến

| Hiểu nhầm | Điều đúng |
| --- | --- |
| “Class nằm trong method là member class.” | Là local class declaration. |
| “Local class không có tên.” | Anonymous class mới không có simple named declaration. |
| “Mỗi lần chạy method tạo một class type mới.” | Tạo instances mới từ một declaration/runtime class. |
| “Tên local class dùng được từ mọi method.” | Chỉ trong lexical scope. |
| “Local class phải được declare cuối file.” | Khai báo ngay trong block phù hợp. |
| “Local class không có constructor/fields.” | Có thể có như ordinary class. |
| “Captured variable bắt buộc viết final.” | Effectively final cũng đủ. |
| “Có thể ++ captured int local.” | Không, mất effectively final. |
| “Effectively final nghĩa object immutable.” | Object referenced vẫn có thể mutable. |
| “Captured variables chết ngay khi method returns.” | Returned object vẫn dùng captured values. |
| “Static method có Outer.this.” | Không có enclosing outer instance. |
| “this trong local class là outer object.” | this là local instance; Outer.this nếu context hợp lệ. |
| “Private outer state không đọc được từ local class.” | Có thể truy cập theo nesting/access rules. |
| “Outer local variable bị shadowed đọc qua Outer.this.” | Outer.this dành cho outer instance members, không cho method locals. |
| “Local class có thể public/private như member class.” | Không dùng access modifiers đó. |
| “Local record có thể capture như local class.” | Local record implicitly static. |
| “Java 17 cấm mọi static members trong inner local class.” | Restriction cũ đã thay đổi từ Java 16. |
| “getEnclosingClass() trả outer object.” | Trả Class metadata. |
| “Generated binary name ổn định để parse.” | Không nên phụ thuộc compiler-generated name. |
| “Chuyển local class sang lambda luôn tránh memory leak.” | Captured references và lifecycle vẫn quan trọng. |

## 55. Checklist cuối bài

- [ ] Tôi khai báo được named local class bên trong method/block.
- [ ] Tôi phân biệt local class declaration và `new Local()`.
- [ ] Tôi biết tên local class chỉ có lexical scope.
- [ ] Tôi không dùng local class name trước declaration.
- [ ] Tôi biết objects có thể sống lâu hơn block qua interface return.
- [ ] Tôi biết mỗi new tạo instance, không tạo Java class identity mới mỗi method call.
- [ ] Tôi viết được local class constructor/fields/methods.
- [ ] Tôi biết captured locals/parameters phải final hoặc effectively final.
- [ ] Tôi phân biệt reassign local và mutate referenced object.
- [ ] Tôi hiểu capture local value không đồng nghĩa deep copy mutable object.
- [ ] Tôi trả local class object qua accessible interface.
- [ ] Tôi biết local class trong instance method có thể dùng Outer.this.
- [ ] Tôi biết static local class không có enclosing outer instance.
- [ ] Tôi hiểu `this` trong local class, anonymous class và lambda khác nhau.
- [ ] Tôi nhận diện được shadowing của local class fields.
- [ ] Tôi biết local class có thể được khai báo trong constructor/initializer.
- [ ] Tôi biết local class có thể extends/implements.
- [ ] Tôi không dùng public/private/protected/static như class member modifiers trên local class.
- [ ] Tôi biết local class có thể có generic type parameter.
- [ ] Tôi biết Java 17 cho phép static methods trong inner/local class.
- [ ] Tôi phân biệt local class với local record/enum implicitly static.
- [ ] Tôi dùng Class.isLocalClass và getEnclosingMethod đúng ý nghĩa.
- [ ] Tôi không phụ thuộc compiler-generated binary name.
- [ ] Tôi hiểu captured references có thể kéo dài object lifetime.
- [ ] Tôi thiết kế concurrency/lifecycle khi local instance thoát method.
- [ ] Tôi biết khi nào dùng lambda, anonymous, member/static nested hoặc top-level type.
- [ ] Tôi giải thích được kết quả stdout của các chương trình Java 17+.

**Kết luận:** **Local class là class có tên được khai báo trong một block**, thường là method hoặc constructor, và tên của nó chỉ sử dụng được trong scope tương ứng. Nó vẫn có constructors, fields, methods, inheritance, instances và Class metadata như một Java class thực sự. Điểm mạnh nổi bật là truy cập được **final/effectively final local variables và parameters** của surrounding block, đồng thời có thể truy cập enclosing instance state trong instance context. Dùng local class khi implementation có tên, state và behavior riêng nhưng chỉ cần trong một phạm vi hẹp; nếu code phải reuse rộng, hãy cân nhắc một member/static nested/top-level class để trách nhiệm và API rõ ràng hơn.
