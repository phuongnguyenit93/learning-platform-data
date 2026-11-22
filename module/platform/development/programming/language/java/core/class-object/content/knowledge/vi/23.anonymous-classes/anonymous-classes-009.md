# Lựa chọn lớp có tên, lớp vô danh hoặc lambda trong Java 17+

Cùng một hành vi trong Java có thể được thể hiện bằng **lớp có tên (named class)**, **lớp vô danh (anonymous class)** hoặc **biểu thức lambda (lambda expression)**. Ba lựa chọn có thể phục vụ cùng một interface, nhưng **không hoàn toàn tương đương** về type system, object identity, `this`/`super`, state, cách khởi tạo, kế thừa, phạm vi sử dụng và khả năng bảo trì.

Bài học này đưa ra **phương pháp ra quyết định** thay vì chỉ thay đoạn mã dài bằng đoạn mã ngắn.

Ví dụ: một tác vụ `Runnable` in thông báo.

**Lớp có tên:**

~~~java
final class PrintTask implements Runnable {
    private final String text;

    PrintTask(String text) {
        this.text = text;
    }

    @Override
    public void run() {
        System.out.println(text);
    }
}
~~~

**Lớp vô danh:**

~~~java
String text = "Java";
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(text);
    }
};
~~~

**Lambda:**

~~~java
String text = "Java";
Runnable task = () -> System.out.println(text);
~~~

Ba đoạn minh họa cùng triển khai behavior “in Java”, nhưng khác cách đóng gói và tổ chức. Named class có constructor nhận dependency explicit; anonymous class tạo class không tên tại expression; lambda mô tả implementation của **functional interface** với target type.

Bài thuộc **Java Core — class-object / Lớp vô danh**, dùng **Java 17+**. Các chương trình hoàn chỉnh đều có tên file, lệnh `javac`/`java` và stdout dự kiến; các snippets không độc lập được chỉ rõ bằng ngữ cảnh.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Giải thích được bản chất của named class, anonymous class và lambda.
2. Biết khi nào lambda được phép dùng: **functional interface/SAM** và target typing.
3. Biết lambda **không** trực tiếp extends abstract/concrete class bất kỳ.
4. Biết anonymous class có thể implements interface hoặc extends class không final và thỏa inheritance rules.
5. Biết named class có thể chia sẻ implementation qua nhiều sites/modules.
6. Chọn theo số abstract methods, constructor, fields, instance initialization và behavior.
7. Phân biệt explicit state fields với captured references và local values.
8. Phân biệt `this`/`super` trong anonymous class với lexical `this`/`super` của lambda.
9. Nắm capture final/effectively-final ở anonymous, local named và lambda.
10. Biết gán lại captured local khác mutate object được tham chiếu.
11. Đọc đúng overload resolution và tình huống lambda thiếu target type hoặc ambiguous.
12. Dùng method references như lựa chọn rút gọn khi thích hợp.
13. Hiểu type identity của anonymous/named instances và các giới hạn đảm bảo identity của lambda.
14. Chọn API public, test doubles, event listeners và callbacks theo lifetime.
15. Xử lý checked exceptions theo SAM/override contracts.
16. Tránh class body khổng lồ ở call site và lambda nhiều side effects.
17. Refactor giữa ba hình thức nhưng vẫn giữ được semantics.
18. Thiết kế test cho behavior, captured state và unsubscribe bằng đúng reference.
19. Hiểu Java 17 về records, sealed/final types và interfaces mặc định.
20. Có checklist giúp chọn cách triển khai trước khi viết code.

## 2. Trước hết: ba cách viết đại diện cho điều gì?

### Lớp có tên

~~~java
final class PriceFormatter implements Formatter {
    // fields, constructors, methods...
}
~~~

Một named class có **source-level name**, có thể khai báo top-level hoặc nested/member/local theo vị trí. Tái sử dụng bằng tên/type, constructor và reference của class đó nếu access rules cho phép.

### Lớp vô danh

~~~java
Formatter formatter = new Formatter() {
    @Override
    public String format(int cents) {
        return cents + " cents";
    }
};
~~~

Anonymous class expression vừa khai báo một class **không tên trong source** vừa tạo instance. Nó có **class body**, own `this`, fields/methods/initializers phù hợp, và được nhìn qua một base type.

### Lambda

~~~java
Formatter formatter = cents -> cents + " cents";
~~~

Lambda là **biểu thức có target type là functional interface**, không phải một declaration viết theo syntax `class ...`. JVM được phép chọn cách biểu diễn instance thích hợp; đừng giả định mỗi lambda luôn tạo anonymous class với tên/identity cố định.

**Khác biệt cốt lõi:** “Ngắn hơn” chưa đủ. Hãy hỏi type contract, state, lifecycle và khả năng đọc.

## 3. Ví dụ chạy: cả ba cùng thực thi một interface

Tạo **`ThreeStylesDemo.java`**:

~~~java
public class ThreeStylesDemo {
    interface Formatter {
        String format(String value);
    }

    static final class NamedFormatter implements Formatter {
        private final String prefix;

        NamedFormatter(String prefix) {
            this.prefix = prefix;
        }

        @Override
        public String format(String value) {
            return prefix + value;
        }
    }

    public static void main(String[] args) {
        Formatter named = new NamedFormatter("N:");
        String prefix = "A:";
        Formatter anonymous = new Formatter() {
            @Override
            public String format(String value) {
                return prefix + value;
            }
        };
        Formatter lambda = value -> "L:" + value;

        System.out.println(named.format("Java"));
        System.out.println(anonymous.format("Java"));
        System.out.println(lambda.format("Java"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThreeStylesDemo.java
java ThreeStylesDemo
~~~

Stdout:

~~~text
N:Java
A:Java
L:Java
~~~

Cả ba được dùng qua interface Formatter. NamedFormatter nhận prefix qua constructor; anonymous captures effectively-final local prefix; lambda tạo implementation ngắn với constant prefix.

## 4. Bảng quyết định trong 30 giây

| Nhu cầu | Thường chọn | Vì sao |
| --- | --- | --- |
| Một behavior ngắn cho functional interface | **Lambda** | Nhỏ gọn, nổi bật logic |
| Dùng một method của object đã tồn tại | **Method reference** | Trực tiếp và rõ |
| Override một method của abstract/concrete class | **Anonymous** hoặc **named** | Lambda không extends class |
| Implement interface có nhiều abstract methods | **Anonymous** hoặc **named** | Lambda chỉ dùng functional interface |
| Stateful callback nhiều fields/helper methods | **Named**, hoặc anonymous nhỏ | Explicit state, lifecycle |
| Cần constructor với validation và dependencies | **Named** | Constructor, invariants, testability |
| Implementation chỉ dùng một nơi, nhiều method nhỏ | **Anonymous** hoặc local named | Giữ code gần call site |
| Logic cần dùng ở nhiều files/modules | **Named** | Tái sử dụng, tên và API |
| Generic implementation phức tạp | **Named** | Type parameters, lỗi compiler dễ xử lý |
| Public stable extension point | **Named type** + interface | Không dựa vào generated class |
| Callback dài, nhiều nhánh và side effects | **Named/local named** | Dễ đọc và kiểm thử |
| Comparator thuần một dòng | **Lambda/method reference** | Đơn giản |
| Framework cần concrete class/constructor theo reflection | **Named** | Stable declaration |
| Long-lived listener capture owner lớn | Tùy cách viết, **ưu tiên ownership rõ** | Syntax không tự ngăn retention |

Đây là hướng dẫn thiết kế, không phải luật compiler. Chọn theo **semantics cần bảo toàn**; không biến mọi callback thành lambda chỉ vì ít dòng hơn.

## 5. Điều kiện tiên quyết của lambda: functional interface

Lambda chỉ có thể được sử dụng trong ngữ cảnh có **target functional interface type**, nghĩa là interface có đúng **một abstract method contract** sau khi xét các quy tắc về Object methods, overrides, inherited methods và default/static/private methods.

Ví dụ:

~~~java
@FunctionalInterface
interface Calculator {
    int compute(int x, int y);
}
~~~

Có thể dùng:

~~~java
Calculator plus = (x, y) -> x + y;
~~~

### `@FunctionalInterface` làm gì?

Annotation yêu cầu compiler kiểm tra interface hợp lệ cho lambda. Không bắt buộc phải ghi annotation mới dùng lambda, nhưng nên ghi trên **interface được chủ ý thiết kế là functional**.

### Default/static methods có làm mất tính functional?

Không nhất thiết. Chúng không tăng số abstract method contracts cần implement. Một functional interface có thể khai báo thêm default và static methods.

~~~java
@FunctionalInterface
interface Transformer {
    String apply(String text);

    default String twice(String text) {
        return apply(apply(text));
    }

    static String identity(String text) {
        return text;
    }
}
~~~

## 6. Ví dụ chạy: functional interface có default/static methods

Tạo **`FunctionalInterfaceDemo.java`**:

~~~java
public class FunctionalInterfaceDemo {
    @FunctionalInterface
    interface Transformer {
        String apply(String value);

        default String twice(String value) {
            return apply(apply(value));
        }

        static String identity(String value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Transformer addStar = value -> value + "*";

        System.out.println(addStar.apply("A"));
        System.out.println(addStar.twice("A"));
        System.out.println(Transformer.identity("A"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FunctionalInterfaceDemo.java
java FunctionalInterfaceDemo
~~~

Stdout:

~~~text
A*
A**
A
~~~

Lambda cung cấp implementation `apply`. Default `twice` gọi `apply` hai lần. Static `identity` thuộc interface, không phải thêm abstract contract.

## 7. Interface có hai abstract methods: không dùng lambda

~~~java
interface Validator {
    boolean isValid(String input);
    String errorMessage(String input);
}
~~~

Không phải functional interface vì có hai abstract methods riêng. Viết:

~~~java
// Validator v = input -> input != null; // Compile error.
~~~

Thay bằng **anonymous class**:

~~~java
Validator v = new Validator() {
    @Override
    public boolean isValid(String input) {
        return input != null && !input.isBlank();
    }

    @Override
    public String errorMessage(String input) {
        return isValid(input) ? "" : "blank";
    }
};
~~~

Hoặc chọn **named class** nếu implementation này được tái sử dụng/kiểm thử nhiều nơi.

## 8. Chương trình chạy: interface nhiều abstract methods

Tạo **`MultiMethodDecisionDemo.java`**:

~~~java
public class MultiMethodDecisionDemo {
    interface Validator {
        boolean isValid(String text);
        String errorMessage(String text);
    }

    public static void main(String[] args) {
        Validator validator = new Validator() {
            @Override
            public boolean isValid(String text) {
                return text != null && !text.isBlank();
            }

            @Override
            public String errorMessage(String text) {
                return isValid(text) ? "" : "blank";
            }
        };

        System.out.println(validator.isValid("Java"));
        System.out.println(validator.errorMessage("  "));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MultiMethodDecisionDemo.java
java MultiMethodDecisionDemo
~~~

Stdout:

~~~text
true
blank
~~~

Lambda không là phương án trực tiếp ở trường hợp này; anonymous/named class là lựa chọn đúng. Nếu muốn lambda, cần **thiết kế lại API** thành những functional interfaces riêng, không cố ép kiểu interface đang có.

## 9. Kế thừa abstract class: chọn anonymous hoặc named

Một lambda không thể trực tiếp extends một abstract class, ngay cả khi class chỉ có một abstract method:

~~~java
abstract class BaseJob {
    abstract void execute();
}

// BaseJob job = () -> {}; // Không hợp lệ: BaseJob là class.
~~~

Có thể tạo anonymous subclass:

~~~java
BaseJob job = new BaseJob() {
    @Override
    void execute() {
        System.out.println("execute");
    }
};
~~~

Hoặc một named subclass:

~~~java
final class PrintJob extends BaseJob {
    @Override
    void execute() {
        System.out.println("execute");
    }
}
~~~

**Đừng nhầm:** “Chỉ có một abstract method” không tự biến **class** thành functional interface. Lambda target phải là functional **interface**.

## 10. Ví dụ chạy: lambda không thay anonymous subclass

Tạo **`AbstractClassChoiceDemo.java`**:

~~~java
public class AbstractClassChoiceDemo {
    static abstract class BaseJob {
        private final String name;

        BaseJob(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        abstract void execute();
    }

    static final class NamedJob extends BaseJob {
        NamedJob(String name) {
            super(name);
        }

        @Override
        void execute() {
            System.out.println("named:" + name());
        }
    }

    public static void main(String[] args) {
        BaseJob named = new NamedJob("A");

        BaseJob anonymous = new BaseJob("B") {
            @Override
            void execute() {
                System.out.println("anonymous:" + name());
            }
        };

        named.execute();
        anonymous.execute();
    }
}
~~~

~~~bash
javac -encoding UTF-8 AbstractClassChoiceDemo.java
java AbstractClassChoiceDemo
~~~

Stdout:

~~~text
named:A
anonymous:B
~~~

Anonymous expression truyền "B" vào constructor của BaseJob. Với nhiều constructor parameters, validation hoặc đa dạng subclass behavior, named class thường dễ quản lý.

## 11. Extends concrete class để custom behavior

Anonymous subclass cũng có thể extends **concrete class không final**, override virtual methods:

~~~java
class Greeter {
    String greet() { return "Hello"; }
}

Greeter custom = new Greeter() {
    @Override
    String greet() { return "Xin chao"; }
};
~~~

Lambda không thay thế `new Greeter(){...}` vì Greeter là class, không là functional interface.

**Nhưng hãy cân nhắc composition:** Thay vì override một concrete class chỉ để đổi cách in thông báo, một `Greeter` nhận `Supplier<String>` hoặc `Function<String,String>` có thể ít phụ thuộc inheritance hơn.

## 12. Constructor state và dependency injection

Named class có constructor riêng với parameters, validation, final fields:

~~~java
final class PrefixFormatter implements Formatter {
    private final String prefix;

    PrefixFormatter(String prefix) {
        this.prefix = java.util.Objects.requireNonNull(prefix);
    }

    @Override
    public String format(String text) {
        return prefix + text;
    }
}
~~~

Đây là snippet minh họa cần interface Formatter ở cùng context. Nếu object có state lâu dài, invariants và lifecycle, constructor giúp dependencies **explicit**.

Anonymous class không được khai báo **named constructor** riêng. Nó có thể:
- truyền args tới constructor của superclass qua `new Base(args) { ... }`;
- có instance field initializers/instance initializer blocks;
- capture values từ lexical context.

Lambda không có class body để khai báo instance constructors/fields theo cú pháp named class.

## 13. Chương trình chạy: named class với invariant

Tạo **`NamedClassStateDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.Function;

public class NamedClassStateDemo {
    static final class Prefixer implements Function<String, String> {
        private final String prefix;

        Prefixer(String prefix) {
            this.prefix = Objects.requireNonNull(prefix, "prefix");
        }

        @Override
        public String apply(String value) {
            return prefix + value;
        }
    }

    public static void main(String[] args) {
        Function<String, String> formatter = new Prefixer("id:");
        System.out.println(formatter.apply("42"));

        try {
            new Prefixer(null);
        } catch (NullPointerException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NamedClassStateDemo.java
java NamedClassStateDemo
~~~

Stdout:

~~~text
id:42
rejected=prefix
~~~

Named class làm invariant “prefix không null” rõ tại construction. Với lambda/anonymous, bạn có thể kiểm tra tham số trước khi tạo callback, nhưng không có constructor riêng được khai báo như trên.

## 14. Captured value thay cho constructor: khi nào phù hợp?

Anonymous class và lambda có thể đọc final/effectively-final locals:

~~~java
String prefix = "id:";

java.util.function.Function<String, String> a =
        new java.util.function.Function<String, String>() {
            @Override
            public String apply(String text) {
                return prefix + text;
            }
        };

java.util.function.Function<String, String> b =
        text -> prefix + text;
~~~

`prefix` là local reference không bị reassigned, nên cả hai forms capture được. Nếu `prefix` là immutable String, sharing reference là an toàn cho logical state.

Nếu muốn:
- thay prefix cho từng invocation;
- quản lý validation/ownership/resource;
- tạo class dùng ở nhiều methods;

thì named class constructor giúp contract minh bạch hơn. Capture không luôn thay thế dependency injection một cách dễ kiểm tra.

## 15. Quy tắc final/effectively final dùng cho lambda và anonymous

Một local variable/parameter dùng từ lambda hoặc anonymous body phải **final hoặc effectively final**, cùng áp dụng với local named class.

Hợp lệ:

~~~java
int factor = 3;

java.util.function.IntUnaryOperator triple =
        value -> factor * value;
~~~

Sai:

~~~java
int factor = 3;
factor = 4;

// IntUnaryOperator f = value -> factor * value; // Compile error.
~~~

**Phải phân biệt:**
- `factor = 4` reassign local variable → mất effectively final.
- `mutableObject.change()` chỉ mutate object → local reference vẫn effectively final, dù phải xét thread safety.

## 16. Chương trình chạy: capture một mutable holder

Tạo **`CapturedStateDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class CapturedStateDemo {
    public static void main(String[] args) {
        AtomicInteger counter = new AtomicInteger();

        Runnable lambda = () ->
                System.out.println("lambda=" +
                        counter.incrementAndGet());

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("anonymous=" +
                        counter.incrementAndGet());
            }
        };

        lambda.run();
        anonymous.run();
        lambda.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 CapturedStateDemo.java
java CapturedStateDemo
~~~

Stdout:

~~~text
lambda=1
anonymous=2
lambda=3
~~~

Hai callbacks share cùng **AtomicInteger object**. `counter` variable effectively final, nhưng state được mutate qua object. Đừng suy ra mọi captured state đều độc lập giữa callbacks.

## 17. State thuộc chính callback hay thuộc object được capture?

**Anonymous class instance field**:

~~~java
Runnable callback = new Runnable() {
    private int calls;

    @Override
    public void run() {
        System.out.println(++calls);
    }
};
~~~

Mỗi anonymous object giữ calls riêng. Một lambda không có cú pháp khai báo một **instance field của lambda object**. Lambda block có thể khai báo local variable nhưng local đó được tạo lại mỗi invocation:

~~~java
Runnable callback = () -> {
    int calls = 0;
    System.out.println(++calls);
};
~~~

Khi chạy nhiều lần, callback trên in 1 mỗi lần, không phải giữ state 1,2,3.

**Lựa chọn:** Cần small per-callback private mutable field → anonymous hoặc named. Cần shared mutable state explicit → dependency holder + concurrency design. Cần stateless transform → lambda.

## 18. Chương trình chạy: anonymous field khác lambda local

Tạo **`CallbackStateComparisonDemo.java`**:

~~~java
public class CallbackStateComparisonDemo {
    public static void main(String[] args) {
        Runnable anonymous = new Runnable() {
            private int calls;

            @Override
            public void run() {
                calls++;
                System.out.println("anonymous=" + calls);
            }
        };

        Runnable lambda = () -> {
            int calls = 0;
            calls++;
            System.out.println("lambda=" + calls);
        };

        anonymous.run();
        anonymous.run();
        lambda.run();
        lambda.run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 CallbackStateComparisonDemo.java
java CallbackStateComparisonDemo
~~~

Stdout:

~~~text
anonymous=1
anonymous=2
lambda=1
lambda=1
~~~

Nếu chuyển anonymous callback sang lambda mà bỏ private field calls, **behavior thay đổi**. Muốn giữ state, hãy đưa nó vào named class hoặc explicit mutable holder.

## 19. `this` của anonymous class khác `this` của lambda

Trong anonymous class, `this` ở instance method trỏ **anonymous object**.

Trong lambda, `this` được hiểu theo **lexical enclosing context**, giống `this` tại chỗ lambda được viết. Ở instance method của Outer, `this` trong lambda là Outer.

Trong static context, không có enclosing `this` để dùng bên trong lambda. Ngược lại, anonymous class được khai báo trong static method vẫn có own instance `this` trong method của nó.

Đây là **khác biệt ngữ nghĩa**, không phải chỉ do compiler tối ưu.

## 20. Một tình huống quyết định: `this` được dùng để hủy đăng ký callback

Trường hợp có ích khi chọn anonymous class thay vì lambda là callback cần truyền **chính reference của nó** vào API:

~~~java
void register(Runnable callback) { /* lưu reference callback */ }
void unregister(Runnable callback) { /* bỏ đúng reference callback */ }

void install() {
    register(new Runnable() {
        @Override
        public void run() {
            unregister(this);
        }
    });
}
~~~

Đây là **snippet** trong một class cung cấp `register` và `unregister` thật sự. `this` bên trong `run()` là anonymous `Runnable`, nên việc truyền reference đó tới `unregister` là đúng về type. Nếu đổi cơ học callback thành `() -> unregister(this)`, `this` sẽ có nghĩa **enclosing owner** tại nơi viết lambda, không phải chính callback; tùy owner type, code có thể không compile hoặc bỏ sai registration.

**Cách an toàn khi cần lambda:** giữ một reference `Runnable listener` ổn định bên ngoài, rồi dùng chính nó để đăng ký/hủy đăng ký theo lifecycle; đừng tạo lambda mới khi hủy. Nếu business logic có lifecycle/identity phức tạp, một named class có `close()` hoặc explicit unsubscribe thường dễ test hơn. Bài so sánh phạm vi và `this` đã cung cấp chương trình quan sát receiver; tại đây tiêu chí là **khả năng bảo toàn registration identity trong refactor**.

## 21. `super` và inheritance semantics

Trong anonymous subclass của Base, `super.method()` gọi implementation từ **superclass Base**.

Trong lambda viết ở instance method, `super` khi hợp lệ tham chiếu lexical enclosing class's superclass (không phải “superclass của lambda object”).

Ví dụ:

~~~java
class Base {
    String label() {
        return "base";
    }
}

class Child extends Base {
    Runnable callback() {
        return () -> System.out.println(super.label());
    }
}
~~~

Lambda trên nằm trong instance method của Child và dùng lexical `super`. Anonymous class:

~~~java
Runnable r = new Runnable() {
    public void run() {
        // super.label(); // Không gọi Child's Base.label theo cách này.
    }
};
~~~

Ở anonymous Runnable implementation, direct superclass về class hierarchy là Object, không có `label()`. Muốn gọi method của outer Child's superclass trong context hợp lệ, cần syntax qualified `Child.super.label()`, hoặc một outer helper method có tên rõ hơn.

## 22. Chương trình chạy: anonymous super của base class

Tạo **`SuperOverrideDemo.java`**:

~~~java
public class SuperOverrideDemo {
    static class Greeter {
        String greet() {
            return "Hello";
        }
    }

    public static void main(String[] args) {
        Greeter custom = new Greeter() {
            @Override
            String greet() {
                return super.greet() + ", Java";
            }
        };

        System.out.println(custom.greet());
        System.out.println("superclass Greeter=" +
                (custom.getClass().getSuperclass() ==
                        Greeter.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SuperOverrideDemo.java
java SuperOverrideDemo
~~~

Stdout:

~~~text
Hello, Java
superclass Greeter=true
~~~

Nếu chuyển sang lambda, nó phải implement một functional interface có method tương ứng; không còn inheritance relationship với Greeter theo nghĩa trực tiếp.

## 23. Target typing: lambda không tự có một standalone type

Lambda cần compiler biết functional interface target. Ví dụ:

~~~java
java.util.function.Function<String, Integer> len =
        text -> text.length();
~~~

Compiler dùng `Function<String,Integer>` để suy ra type của `text` và kiểu trả về.

Sai:

~~~java
// Object obj = text -> text.length(); // Object không là functional interface.
// var fn = text -> text.length();      // Không có target type.
~~~

Đúng:

~~~java
var fn = (java.util.function.Function<String, Integer>)
        (text -> text.length());
~~~

Hoặc đơn giản gán trực tiếp cho Function declaration. Java `var` không tự suy ra một functional interface bất kỳ từ lambda không có target.

### Anonymous và named khác

`new Runnable() {...}` tự có type ở expression vì phần `new` nêu interface/base type. `new NamedRunner()` cũng nêu class name. Lambda phụ thuộc target typing mạnh hơn.

## 24. Chương trình chạy: target typing và Function

Tạo **`TargetTypingDemo.java`**:

~~~java
import java.util.function.Function;

public class TargetTypingDemo {
    static void printLength(Function<String, Integer> length,
                            String value) {
        System.out.println(length.apply(value));
    }

    public static void main(String[] args) {
        Function<String, Integer> len = text -> text.length();

        printLength(len, "Java");
        printLength(text -> text.length(), "OpenAI");
    }
}
~~~

~~~bash
javac -encoding UTF-8 TargetTypingDemo.java
java TargetTypingDemo
~~~

Stdout:

~~~text
4
6
~~~

Method parameter `Function<String,Integer>` cung cấp target type cho lambda tại call site. Vì vậy có thể truyền lambda trực tiếp khi compiler resolve được overload phù hợp.

## 25. Overload ambiguity: cùng lambda khớp hai functional interfaces

Nếu có hai unrelated functional interfaces với cùng SAM shape:

~~~java
@FunctionalInterface
interface Left {
    String get();
}

@FunctionalInterface
interface Right {
    String get();
}

static void select(Left x) {}
static void select(Right x) {}
~~~

Expression `select(() -> "A")` có thể ambiguous vì cả hai overload đều nhận shape phù hợp. Named class/anonymous class với explicit target type thường tránh ambiguous ở call site.

Giải pháp: khai báo variable typed hoặc cast lambda sang functional interface chủ định.

## 26. Chương trình chạy: giải quyết overload bằng target explicit

Tạo **`LambdaOverloadDemo.java`**:

~~~java
public class LambdaOverloadDemo {
    @FunctionalInterface
    interface Left {
        String get();
    }

    @FunctionalInterface
    interface Right {
        String get();
    }

    static void select(Left left) {
        System.out.println("left=" + left.get());
    }

    static void select(Right right) {
        System.out.println("right=" + right.get());
    }

    public static void main(String[] args) {
        // select(() -> "A"); // Ambiguous.

        select((Left) () -> "A");

        Right right = () -> "B";
        select(right);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LambdaOverloadDemo.java
java LambdaOverloadDemo
~~~

Stdout:

~~~text
left=A
right=B
~~~

Đừng tự thay anonymous class bằng lambda trong một overloaded call site mà không compile-test. Type inference và overload resolution có thể làm behavior/call binding thay đổi hoặc gây lỗi.

## 27. Method reference: biến thể gọn hơn lambda

Nếu lambda chỉ gọi một method có sẵn:

~~~java
java.util.function.Function<String, Integer> length =
        value -> value.length();
~~~

có thể dùng:

~~~java
java.util.function.Function<String, Integer> length =
        String::length;
~~~

Các dạng phổ biến:

- `Type::staticMethod`
- `existingObject::instanceMethod`
- `Type::instanceMethod` (receiver là argument)
- `Type::new` (constructor reference)
- `ArrayType::new` (array constructor reference)

Method reference vẫn là **poly expression** cần functional target type thích hợp. Không phải mọi lambda body nhiều statements đều có method-reference tương đương rõ nghĩa.

## 28. Chương trình chạy: method reference hoặc lambda?

Tạo **`MethodReferenceDecisionDemo.java`**:

~~~java
import java.util.List;
import java.util.function.Function;
import java.util.function.Supplier;

public class MethodReferenceDecisionDemo {
    public static void main(String[] args) {
        Function<String, Integer> size = String::length;
        Supplier<List<String>> empty = List::of;

        System.out.println("size=" + size.apply("Java"));
        System.out.println("empty=" + empty.get());

        Function<Integer, Integer> square = n -> n * n;
        System.out.println("square=" + square.apply(5));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MethodReferenceDecisionDemo.java
java MethodReferenceDecisionDemo
~~~

Stdout:

~~~text
size=4
empty=[]
square=25
~~~

`String::length` rõ nghĩa hơn viết lại boilerplate; `n -> n*n` là logic transformation thực sự nên lambda thích hợp. `List::of` ở đây là method reference chọn overload zero-argument theo Supplier target, trả immutable empty List.

## 29. Generic typing và SAM: đừng để raw types lọt vào API

Nên dùng parameterized functional interface:

~~~java
java.util.function.Function<String, Integer> parse =
        Integer::parseInt;
~~~

Tránh raw `Function` làm mất compile-time generic checking và dễ phát sinh runtime casts/unchecked warnings.

Với named implementation, class có thể khai báo type parameter:

~~~java
final class Identity<T>
        implements java.util.function.Function<T, T> {
    @Override
    public T apply(T value) {
        return value;
    }
}
~~~

Lambda không tự có named generic class declaration như Identity<T>, nhưng có thể được dùng ở những invocation có target generic type đã biết.

## 30. Chương trình chạy: generic named và generic factory lambda

Tạo **`GenericChoiceDemo.java`**:

~~~java
import java.util.function.Function;

public class GenericChoiceDemo {
    static final class Identity<T> implements Function<T, T> {
        @Override
        public T apply(T value) {
            return value;
        }
    }

    static <T> Function<T, T> identityLambda() {
        return value -> value;
    }

    public static void main(String[] args) {
        Function<String, String> named = new Identity<>();
        Function<Integer, Integer> lambda = identityLambda();

        System.out.println(named.apply("Java"));
        System.out.println(lambda.apply(17));
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericChoiceDemo.java
java GenericChoiceDemo
~~~

Stdout:

~~~text
Java
17
~~~

Named type dùng lại ở nhiều nơi; generic factory lambda cũng có thể type-safe nếu method/API cung cấp target type rõ.

## 31. Checked exceptions: phương án nào giúp hơn?

Không có lựa chọn nào xóa checked-exception rules:

- Named implementation of Runnable.run() không được tự thêm `throws IOException` nếu contract không cho.
- Anonymous implementation of Runnable cũng vậy.
- Lambda target Runnable không được ném checked IOException chưa xử lý.
- Nếu target là `Callable<T>` (cho phép `throws Exception`), code có thể ném checked exception theo contract.

Ví dụ:

~~~java
java.util.concurrent.Callable<String> job =
        () -> {
            throw new java.io.IOException("missing");
        };
~~~

Ở call site, `Callable.call()` khai báo `throws Exception`, nên caller phải catch/declare.

**Đừng chọn anonymous class để “né compiler”**. Hãy thiết kế đúng functional interface/call contract hoặc xử lý exception tại boundary.

## 32. Chương trình chạy: checked exception với Callable

Tạo **`CheckedExceptionChoiceDemo.java`**:

~~~java
import java.io.IOException;
import java.util.concurrent.Callable;

public class CheckedExceptionChoiceDemo {
    public static void main(String[] args) {
        Callable<String> task =
                () -> { throw new IOException("missing"); };

        try {
            System.out.println(task.call());
        } catch (Exception ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CheckedExceptionChoiceDemo.java
java CheckedExceptionChoiceDemo
~~~

Stdout:

~~~text
error=missing
~~~

Cùng code có thể dùng anonymous `new Callable<String>() { ... }` hoặc named class implements Callable. Type contract quyết định checked exception hợp lệ.

## 33. Java 17: `final` và `sealed` type restrictions

Anonymous subclass không được extends một **final class**:

~~~java
final class FinalService {
}

// FinalService service = new FinalService() {}; // Compile error.
~~~

Lambda cũng không trực tiếp extends FinalService vì lambda cần functional interface.

Với **sealed class/interface** (Java 17), direct subclasses/implementations phải theo permits restrictions. Anonymous class không tự miễn quy tắc sealed:

~~~java
sealed interface Result permits Ok, Error {}

final class Ok implements Result {}

final class Error implements Result {}

// Result value = new Result() {}; // Không được là direct anonymous implementation.
~~~

Nếu cần extensibility, thiết kế permitted/non-sealed extension points hoặc dùng composition; không coi anonymous/lambda như cách bypass mô hình đóng.

## 34. Anonymous class khi interface có default methods

Functional interface có default methods vẫn có thể dùng lambda:

~~~java
@FunctionalInterface
interface Greeting {
    String name();

    default String message() {
        return "Hello, " + name();
    }
}

Greeting lambda = () -> "Mai";
~~~

Anonymous class cũng có thể implement `name()` và override default `message()` nếu muốn custom logic. Nếu cần override **nhiều methods**, anonymous hoặc named có thể phù hợp hơn lambda vì lambda chỉ cung cấp SAM implementation.

## 35. Chương trình chạy: override default method

Tạo **`DefaultMethodOverrideChoiceDemo.java`**:

~~~java
public class DefaultMethodOverrideChoiceDemo {
    @FunctionalInterface
    interface Greeting {
        String name();

        default String message() {
            return "Hello, " + name();
        }
    }

    public static void main(String[] args) {
        Greeting lambda = () -> "Mai";

        Greeting anonymous = new Greeting() {
            @Override
            public String name() {
                return "An";
            }

            @Override
            public String message() {
                return "Hi, " + name();
            }
        };

        System.out.println(lambda.message());
        System.out.println(anonymous.message());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefaultMethodOverrideChoiceDemo.java
java DefaultMethodOverrideChoiceDemo
~~~

Stdout:

~~~text
Hello, Mai
Hi, An
~~~

Một lambda không có class body để override riêng cả name và message; muốn custom behavior nhiều methods, dùng anonymous/named class hoặc đổi contract.

## 36. `Object` methods có làm interface mất SAM?

Một functional interface có thể khai báo abstract method trùng public instance method của Object mà vẫn functional theo JLS rules vì các Object-method signatures này không được tính như abstract contracts riêng theo cách đơn giản.

Ví dụ:

~~~java
@FunctionalInterface
interface Labeler {
    String label(String value);

    boolean equals(Object other);
}
~~~

Lambda chỉ implement `label`; `equals` có semantics thông qua Object behavior/runtime implementation. Không nên custom equals/hashCode của lambda object vì lambda identity/representation không có đảm bảo bạn nên dựa vào.

**Nếu equality/identity là thành phần business contract**, named immutable value class hoặc record chứa dữ liệu + explicit policy sẽ phù hợp hơn callback lambda.

## 37. Identity: không suy ra caching của lambda

Anonymous class instance creation expression `new Interface() { ... }` tạo object mới mỗi lần expression chạy (nếu creation thành công). Named class `new Named()` cũng tạo object mới.

Lambda **không có guarantee** rằng mỗi evaluation tạo một object mới, hoặc hai evaluations sẽ luôn trả cùng object. JVM có thể reuse instances, đặc biệt non-capturing lambdas, theo Java language semantics.

Do đó:

~~~java
Runnable a = () -> {};
Runnable b = () -> {};
// Không xây contract bằng a == b.
~~~

Nếu lifecycle code cần **một handle cụ thể để unsubscribe**, hãy **lưu chính callback reference đã đăng ký**, bất kể là lambda, anonymous hay named.

Đừng kiểm tra `lambda.getClass().isAnonymousClass()` rồi kết luận object thuộc anonymous class: lambda implementation không có guarantee đó.

## 38. Chương trình chạy: giữ callback reference chính xác

Tạo **`ListenerIdentityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListenerIdentityDemo {
    static final class Bus {
        private final List<Runnable> listeners = new ArrayList<>();

        void subscribe(Runnable listener) {
            listeners.add(listener);
        }

        void unsubscribe(Runnable listener) {
            listeners.remove(listener);
        }

        void publish() {
            for (Runnable listener : List.copyOf(listeners)) {
                listener.run();
            }
        }
    }

    public static void main(String[] args) {
        Bus bus = new Bus();
        Runnable listener = () -> System.out.println("event");

        bus.subscribe(listener);
        bus.publish();

        bus.unsubscribe(listener);
        System.out.println("unsubscribed");
        bus.publish();
    }
}
~~~

~~~bash
javac -encoding UTF-8 ListenerIdentityDemo.java
java ListenerIdentityDemo
~~~

Stdout:

~~~text
event
unsubscribed
~~~

Dùng đúng `listener` reference cho cả subscribe/unsubscribe. Viết lại `() -> System.out.println("event")` ở chỗ unsubscribe có thể không chỉ cùng object đã đăng ký; không được dựa vào identity của các lambda expressions độc lập.

## 39. Tên class và debugging/logging

Named class có source name rõ, stack trace thường giúp xác định trách nhiệm của implementation dễ hơn. Anonymous class có generated binary name có thể chứa ký tự `$` và số thứ tự theo compiler. Lambda runtime representation có thể khác theo JVM/implementation.

Không xây business logic bằng:

~~~java
callback.getClass().getName().contains("Lambda")
~~~

hoặc parse `Outer$1`. Những generated names không ổn định và không phải API contract.

**Gợi ý:** Nếu một callback quan trọng cần log/metrics, đặt **label/domain identifier tường minh** qua named class hoặc wrapper, thay vì suy ra behavior từ runtime class name.

## 40. Scope và reuse của named class

Named class không đồng nghĩa phải tạo **public top-level class**. Bạn có nhiều mức visibility:

- Top-level package-private class hoặc public class ở file/module thích hợp.
- `private static nested class` dùng trong outer class.
- `private inner member class` cần enclosing outer instance.
- Local named class trong method/block.

### Lựa chọn tinh gọn

Nếu implementation chỉ dùng một method nhưng có nhiều methods/fields, **local named class** có thể dễ đọc hơn anonymous khổng lồ. Nếu implementation dùng cả class nhưng không cần outer state, chọn **private static nested class**. Nếu public API cần class type, chọn một **named accessible type** theo package/module design.

Không suy nghĩ kiểu “named class = thêm rất nhiều file”; lựa chọn vị trí declaration giúp cân bằng scope và readability.

## 41. Chương trình chạy: local named class thay anonymous dài

Tạo **`LocalNamedChoiceDemo.java`**:

~~~java
public class LocalNamedChoiceDemo {
    interface Report {
        String title();
        String body();
    }

    static Report build(String project) {
        class SimpleReport implements Report {
            private final String title;

            SimpleReport(String title) {
                this.title = title;
            }

            @Override
            public String title() {
                return title;
            }

            @Override
            public String body() {
                return "Project=" + project;
            }
        }

        return new SimpleReport("Summary");
    }

    public static void main(String[] args) {
        Report report = build("Java");
        System.out.println(report.title());
        System.out.println(report.body());
    }
}
~~~

~~~bash
javac -encoding UTF-8 LocalNamedChoiceDemo.java
java LocalNamedChoiceDemo
~~~

Stdout:

~~~text
Summary
Project=Java
~~~

SimpleReport là local named class, có constructor và hai methods; implementation vẫn ẩn sau interface Report. Nó capture parameter project effectively final nhưng quản lý title qua constructor field.

## 42. Code có nhiều tầng lambda lồng nhau: readability

Ví dụ functional pipeline:

~~~java
java.util.function.Function<String, java.util.function.Function<Integer, String>>
        repeat = text -> count -> text.repeat(count);
~~~

Hợp lệ nhưng có thể khó đọc khi generic types, error handling, state và branching tăng. Nếu body biến thành hàng chục dòng với nested conditionals, exception handling và logging, **tách thành named method** hoặc named class có semantic title.

### Quy tắc review

Hỏi:

1. Khi xem call site, đọc được mục đích sau vài giây không?
2. Nếu throw exception, stack trace/chỗ xử lý có rõ không?
3. Có hidden captured mutable dependencies không?
4. Có test riêng được không?
5. Method reference hoặc lambda ngắn có làm logic rõ hơn không?
6. Cần reuse/extend contract không?

Cách diễn đạt tốt nhất không nhất thiết ít dòng nhất.

## 43. Refactor anonymous sang lambda: điều kiện an toàn

Bạn có thể cân nhắc refactor:

~~~java
Runnable callback = new Runnable() {
    @Override
    public void run() {
        perform();
    }
};
~~~

thành:

~~~java
Runnable callback = () -> perform();
~~~

nếu những điều kiện sau đúng:

- Target là **functional interface**.
- Anonymous class chỉ cung cấp đúng SAM implementation, không có override thêm cần giữ.
- Không có anonymous-specific instance fields/initializers/helpers có behavior.
- Body không dựa vào `this`/`super` với meaning anonymous receiver.
- Không phụ thuộc vào exact instance identity/class metadata/generation semantics.
- Capture/lifecycle/thread safety được giữ.
- Checked exceptions và overload target typing vẫn hợp lệ.

**Nên thêm tests** trước/sau khi refactor, nhất là nếu callback đăng ký với UI/executor hoặc truyền cho overloaded methods.

## 44. Refactor lambda sang named class: khi phức tạp tăng

Bắt đầu từ:

~~~java
java.util.function.Predicate<Order> valid =
        order -> order.total() > 0;
~~~

Đây là snippet minh họa; cần `Order` definition.

Khi business logic có nhiều rules, metrics, config và error messages, chuyển thành:

~~~java
final class OrderValidator
        implements java.util.function.Predicate<Order> {
    private final int minimum;

    OrderValidator(int minimum) {
        this.minimum = minimum;
    }

    @Override
    public boolean test(Order order) {
        return order.total() >= minimum;
    }
}
~~~

Named class có constructor boundary, methods và dễ mở rộng testing. Hoặc giữ functional interface nhưng chuyển lambda logic sang **named static method** rồi method reference `Rules::isValid`. Không bắt buộc chọn class cho mọi logic tăng thêm một vài dòng.

## 45. Case study: thiết kế policy thanh toán bằng named strategy

Khi behavior cần có tên trong domain và validation:

Tạo **`StrategyChoiceDemo.java`**:

~~~java
public class StrategyChoiceDemo {
    interface Discount {
        int apply(int cents);
    }

    static final class PercentDiscount implements Discount {
        private final int percent;

        PercentDiscount(int percent) {
            if (percent < 0 || percent > 100) {
                throw new IllegalArgumentException("percent");
            }
            this.percent = percent;
        }

        @Override
        public int apply(int cents) {
            if (cents < 0) {
                throw new IllegalArgumentException("cents");
            }
            return cents - cents * percent / 100;
        }
    }

    public static void main(String[] args) {
        Discount permanent = new PercentDiscount(20);
        Discount promotion = cents -> cents - 50;

        System.out.println("permanent=" + permanent.apply(1000));
        System.out.println("promotion=" + promotion.apply(1000));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrategyChoiceDemo.java
java StrategyChoiceDemo
~~~

Stdout:

~~~text
permanent=800
promotion=950
~~~

Named PercentDiscount có reusable invariant percent 0..100. Lambda promotion minh họa one-off fixed adjustment; nếu phải xử lý negatives/capping/concurrency thì nó cần contract chặt hơn. **Một đoạn lambda ngắn không tự bảo đảm business correctness**.

## 46. Case study: callback nhiều methods không ép thành lambda

Nếu interface có lifecycle methods:

~~~java
interface Listener {
    void onOpen();
    void onClose();
}
~~~

Dùng anonymous:

~~~java
Listener listener = new Listener() {
    public void onOpen() {
        System.out.println("open");
    }

    public void onClose() {
        System.out.println("close");
    }
};
~~~

Hoặc named class khi logic đủ lớn. Không thể dùng một lambda vì hai abstract methods. Nếu library cung cấp adapter class hay default implementations, một anonymous subclass hoặc alternative functional hooks có thể làm code ngắn hơn, nhưng **đó là thay đổi API contract**.

## 47. Chương trình chạy: lifecycle listener nhiều methods

Tạo **`LifecycleListenerDemo.java`**:

~~~java
public class LifecycleListenerDemo {
    interface Listener {
        void onOpen();
        void onClose();
    }

    static void simulate(Listener listener) {
        listener.onOpen();
        listener.onClose();
    }

    public static void main(String[] args) {
        Listener listener = new Listener() {
            @Override
            public void onOpen() {
                System.out.println("open");
            }

            @Override
            public void onClose() {
                System.out.println("close");
            }
        };

        simulate(listener);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LifecycleListenerDemo.java
java LifecycleListenerDemo
~~~

Stdout:

~~~text
open
close
~~~

Anonymous class giữ lifecycle logic tại call site. Nếu nhiều modules cần chung implementation, named Listener class giúp tránh duplication.

## 48. Testing: test behavior qua interface, không test hình thức

Nếu API nhận `Function`, `Predicate`, `Runnable` hoặc domain interface, hãy **kiểm thử observable behavior**:

- Inputs → outputs đúng.
- Side effects/lifecycle đúng contract.
- Exception type/message khi input invalid.
- Độc lập giữa instances khi có state.
- Thread safety khi được hứa.
- Không leak shared references.
- Constructor/initializers giữ invariants.
- Listener được unsubscribe đúng.

Không nên test `getClass().getName()` để ép implementation phải anonymous hay lambda trừ khi chính library định nghĩa contract phản xạ đặc biệt và có lý do cụ thể.

### Ví dụ test qua interface

Tạo **`ChoiceContractTestDemo.java`**:

~~~java
import java.util.function.Function;

public class ChoiceContractTestDemo {
    static final class NamedPrefix implements Function<String, String> {
        private final String prefix;

        NamedPrefix(String prefix) {
            this.prefix = prefix;
        }

        @Override
        public String apply(String input) {
            return prefix + input;
        }
    }

    static void check(Function<String, String> f, String expected) {
        String result = f.apply("Java");
        if (!expected.equals(result)) {
            throw new AssertionError(expected + " != " + result);
        }
    }

    public static void main(String[] args) {
        check(new NamedPrefix("N:"), "N:");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ChoiceContractTestDemo.java
java ChoiceContractTestDemo
~~~

**Chú ý:** Đoạn trên có chủ ý giữ một **test fixture sai**: output thực tế là `N:Java` nhưng expected `N:`; chạy chương trình sẽ ném AssertionError. Khi viết test thật, expected phải là `N:Java`. Đoạn này minh họa vì sao cần test observable result thay vì nhìn code. Sửa testcase trước khi sử dụng trong dự án.

## 49. Ví dụ chạy: contract tests đúng cho cả ba forms

Tạo **`ThreeFormsContractDemo.java`**:

~~~java
import java.util.function.Function;

public class ThreeFormsContractDemo {
    static final class NamedPrefix implements Function<String, String> {
        private final String prefix;

        NamedPrefix(String prefix) {
            this.prefix = prefix;
        }

        @Override
        public String apply(String input) {
            return prefix + input;
        }
    }

    static void check(Function<String, String> formatter,
                      String expected) {
        String actual = formatter.apply("Java");
        if (!expected.equals(actual)) {
            throw new AssertionError(expected + " != " + actual);
        }
    }

    public static void main(String[] args) {
        Function<String, String> named = new NamedPrefix("N:");
        Function<String, String> anonymous =
                new Function<String, String>() {
                    @Override
                    public String apply(String input) {
                        return "A:" + input;
                    }
                };
        Function<String, String> lambda =
                input -> "L:" + input;

        check(named, "N:Java");
        check(anonymous, "A:Java");
        check(lambda, "L:Java");

        System.out.println("named PASS");
        System.out.println("anonymous PASS");
        System.out.println("lambda PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThreeFormsContractDemo.java
java ThreeFormsContractDemo
~~~

Stdout:

~~~text
named PASS
anonymous PASS
lambda PASS
~~~

Ba implementations khác source form nhưng cùng type contract `Function<String,String>`. Test cần đo **kết quả thực**, không đòi type identity như một implementation detail.

## 50. Serialization và long-lived contracts

Không mặc định lambda hoặc anonymous class object có serialized form ổn định, cũng không mặc định implement `Serializable`.

- `Runnable`/`Function` không tự extends Serializable.
- Một lambda có thể serializable khi target type phù hợp, nhưng format/compatibility/security là một hợp đồng khác.
- Named class có tên ổn định hơn nhưng **không tự thành serializable**; cần explicit Serializable contract và đúng object graph.
- Captured/enclosing references có thể không serializable.
- Persist business intent thường nên lưu **immutable command/DTO data**, không persist arbitrary callback implementation.

Nếu persistence/framework reflection là yêu cầu chính, thiết kế named types và schema trước, thay vì dùng anonymous/lambda và trông chờ generated class names.

## 51. Performance và allocation: đừng tối ưu bằng phỏng đoán

Thường thấy lập luận “lambda nhanh hơn anonymous class” hoặc “named class tốn bộ nhớ hơn” như một quy tắc tuyệt đối. Không đủ cơ sở cho mọi JVM/JDK/workload.

- JVM JIT, escape analysis, inlining và capture có thể ảnh hưởng kết quả.
- Non-capturing lambda có thể được reuse, nhưng không có identity promise để dựa vào.
- Anonymous `new` có Java object creation semantics.
- State/lifetime/allocation của captured values rất quan trọng.
- Hot-loop API design và side effects có thể quan trọng hơn syntax.

**Khuyến nghị:** Chọn theo readability/correctness trước; với code thực sự performance-sensitive, profile/JMH benchmark trong môi trường mục tiêu. Không sửa implementation form chỉ vì đoán nhanh hơn.

## 52. API boundaries: nơi gọi nên biết gì?

Một public API thường không nên yêu cầu concrete anonymous class identity. Nếu chỉ cần hành vi, nhận interface:

~~~java
static void submit(Runnable job) {
    job.run();
}
~~~

Caller tùy ý truyền:
- `new NamedJob()`;
- `new Runnable() { ... }`;
- `() -> ...`.

Nếu contract có nhiều operations và lifecycle, dùng domain interface có tên hoặc abstract class rõ hơn generic Runnable. Nếu object có mutable state/invariants/business identity, named concrete type là lựa chọn thiết kế hợp lý.

## 53. Cách nhận biết code nên refactor

**Đổi lambda thành method reference** khi body chỉ forward đúng method và không thêm logic cần thể hiện.

**Đổi anonymous thành lambda** khi nó implements đúng SAM, không cần anonymous own state/this/super, và semantics không đổi.

**Đổi lambda thành named method/class** khi body dài, có nhiều branches, validations, side effects hoặc dependencies không rõ.

**Đổi anonymous thành local named class** khi muốn tên ngữ nghĩa, constructor/state, nhiều instances cùng implementation trong một method.

**Đổi local named thành static nested/top-level named class** khi cần reuse ở nhiều nơi hoặc cần test independently.

**Không đổi chỉ vì “style guide bảo mọi callback phải là lambda”.** Type restrictions và behavior thực tế quyết định.

## 54. Các lỗi phổ biến khi chuyển đổi

| Thao tác refactor | Lỗi dễ gặp | Cách tránh |
| --- | --- | --- |
| Anonymous → lambda | `this` đổi từ anonymous sang outer | Xem lại receiver, dùng explicit self reference/other design |
| Anonymous → lambda | Mất fields và instance initializer | Named class hoặc explicit holder |
| Anonymous → lambda | Interface không phải functional | Giữ anonymous/named hoặc đổi API |
| Anonymous subclass → lambda | Lambda không extends class | Giữ subclass/composition |
| Lambda → method reference | Chọn method overload khác | Kiểm tra target typing và test |
| Lambda → anonymous | Anonymous `this` khác | Không copy expression theo máy móc |
| Lambda → named class | Captured dependencies bị biến thành implicit global | Đưa vào constructor final fields |
| Named → anonymous | Mất reuse và stable type name | Chỉ áp dụng one-off implementation |
| Named → lambda | Bỏ validation/constructor semantics | Đặt validation ở boundary tương đương |
| Callback → lambda | Dựa vào lambda equality/identity | Lưu callback reference |
| Callback → bất kỳ form | Không unregister | Ownership/lifecycle rõ |
| Refactor overload | Ambiguous target type | Explicit variable/cast, compile-test |
| Raw generics | Unchecked warnings/type safety | Parameterized interfaces |
| Đổi Runnable → Callable | Checked exceptions/call signature khác | Xét contract và result type |
| State holder mutable | Data race | Synchronization/immutable design |

## 55. Quy trình chọn trong thực tế

**Bước 1 — Xác định contract cần đáp ứng.** Là functional interface, interface nhiều methods hay một abstract/concrete superclass?

**Bước 2 — Xác định behavior độ dài và độ phức tạp.** Một expression thuần, nhiều statements, helper methods hay domain invariants?

**Bước 3 — Xác định state.** Stateless, per-instance mutable state, hay capture một shared dependency? Có constructor validation cần thiết không?

**Bước 4 — Xác định phạm vi sử dụng.** Một call site hay nhiều methods/modules?

**Bước 5 — Xác định `this`/`super` semantics.** Có cần callback object làm receiver? Có cần gọi base class behavior?

**Bước 6 — Xác định API overload/generics/checked exceptions.** Lambda có target type rõ không?

**Bước 7 — Xác định lifecycle.** Callback có thể sống lâu hơn owner? Có unsubscribe đúng instance không?

**Bước 8 — Đặt tên logic nếu giúp đọc và debug.** Named method/class không phải thất bại về độ ngắn.

**Bước 9 — Viết test observable behavior.** Đặc biệt test state/repetition, exceptions, null và type constraints.

**Bước 10 — Chỉ cân nhắc performance sau profile.**

## 56. Sơ đồ quyết định

~~~text
Cần implement một hành vi?
    |
    +-- Phải extends class (abstract/concrete)?
    |       |
    |       +-- Có --> Anonymous subclass nếu ngắn, một chỗ;
    |                     named subclass nếu state lớn/reuse.
    |
    +-- Interface có nhiều abstract methods?
    |       |
    |       +-- Có --> Anonymous hoặc named implementation.
    |
    +-- Functional interface một SAM?
            |
            +-- Body chỉ gọi method có sẵn?
            |       |
            |       +-- Có --> Method reference (nếu rõ nghĩa).
            |
            +-- State riêng, constructor, this, helpers?
            |       |
            |       +-- Có --> Named hoặc anonymous class.
            |
            +-- Reuse/cross-module/public stable type?
            |       |
            |       +-- Có --> Named class hoặc named helper method.
            |
            +-- Ngắn, một nơi, target type rõ?
                    |
                    +-- Có --> Lambda.
~~~

Sơ đồ là heuristic; cả performance, DI/frameworks, sealed types và team conventions có thể ảnh hưởng lựa chọn. Những giới hạn ngôn ngữ (lambda chỉ target functional interface, final/sealed subclass rules, checked exceptions) vẫn bắt buộc.

## 57. Bài tập 1 — Chọn lambda hay anonymous?

`Runnable` callback chỉ in "done", không có state, không reuse.

**Đáp án gợi ý:** Lambda `() -> System.out.println("done")` vì Runnable là functional interface và body ngắn. Anonymous class vẫn hợp lệ nhưng dài hơn.

## 58. Bài tập 2 — Abstract class có một method

Một `abstract class Reader { abstract String read(); }` có một abstract method. Có thể `Reader r = () -> "A";` không?

**Đáp án:** Không. Reader là **class**, không phải functional interface. Dùng `new Reader() { @Override String read() { return "A"; } }` hoặc named subclass.

## 59. Bài tập 3 — Interface hai abstract methods

`interface Listener { void open(); void close(); }` cần implement cả hai.

**Đáp án:** Anonymous class hoặc named class, không thể dùng một lambda trực tiếp vì interface không functional. Nếu library muốn lambda, phải thiết kế API nhận hai functional callbacks hoặc adapter khác.

## 60. Bài tập 4 — Named class hay lambda?

Một calculation policy dùng nhiều modules, cần kiểm tra percentage 0..100 và có mutable per-customer config.

**Đáp án:** Thường chọn named class/interface design với explicit constructor/config/invariants. Lambda có thể làm việc về mặt code nếu contract là SAM, nhưng khó thấy ownership và validation nếu state ngày càng nhiều.

## 61. Bài tập 5 — Anonymous `this`

~~~java
Runnable r = new Runnable() {
    public void run() {
        System.out.println(this.getClass().isAnonymousClass());
    }
};
~~~

**Đáp án:** In true khi gọi r.run(): `this` là anonymous object. Nếu chuyển thành lambda trong instance method, `this` đổi sang outer receiver; đây không phải semantics-preserving refactor.

## 62. Bài tập 6 — Captured mutable state

~~~java
int[] counter = {0};
Runnable r = () -> counter[0]++;
~~~

**Đáp án:** Hợp lệ nếu reference variable counter không bị reassigned, vì lambda capture array reference effectively final và mutate element. Nhưng đây không phải automatically thread-safe; với shared concurrency chọn AtomicInteger hoặc explicit synchronized design.

## 63. Bài tập 7 — Identity

Hai lambda expressions viết ở hai source locations đều có body `() -> {}`. Có được khẳng định `a == b` false không?

**Đáp án:** Không nên dựa vào identity của lambda evaluations. Lambda identity/reuse là implementation detail được phép linh hoạt; lưu reference nếu cần identity cho lifecycle.

## 64. Bài tập 8 — Method reference

`Function<String,Integer> f = s -> s.length();` có thể viết thế nào?

**Đáp án:** `Function<String,Integer> f = String::length;`. Phải có target type để compiler biết parameter/return types.

## 65. Bài tập 9 — Overload

Có hai overload `select(Left)` và `select(Right)`, mỗi interface có `String get()`. `select(() -> "A")` có thể bị gì?

**Đáp án:** Ambiguous. Dùng `select((Left) () -> "A")` hoặc assign lambda cho một biến `Left` rồi truyền vào. Không đổ lỗi cho “lambda không hợp lệ”; lỗi là chưa phân biệt overload target.

## 66. Bài tập 10 — Constructor của anonymous subclass

Base có constructor `Base(int limit)` nhưng không có no-arg constructor. Có `new Base() { ... }` được không?

**Đáp án:** Không, cần cung cấp args phù hợp: `new Base(5) { ... }` và override required methods. Lambda không thay thế được extends Base nếu Base là class.

## 67. Bài tập 11 — Callback cần unsubscribe

Một UI component đăng ký `() -> handle()` vào một EventBus, sau đó muốn remove.

**Đáp án:** Lưu chính Runnable listener reference đã subscribe, dùng same reference để unsubscribe. Đừng viết expression lambda mới rồi coi nó chắc chắn bằng callback cũ.

## 68. Bài tập 12 — Test contract

Một API nhận `Predicate<String>`. Ba implementations (named/anonymous/lambda) cùng trả true khi String không blank. Nên test điều gì?

**Đáp án:** Test inputs valid/blank/null theo contract, output và exceptions, side effects nếu có. Không test `getClass().getName()` để ép implementation style.

## 69. Sai lầm thường gặp

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Lambda thay mọi anonymous class.” | Chỉ khi target là functional interface và semantics phù hợp. |
| “Một abstract method trong abstract class dùng lambda được.” | Lambda cần functional **interface**. |
| “Anonymous class chỉ implements interface.” | Có thể extends concrete/abstract non-final class. |
| “Named class luôn public, phải file riêng.” | Có top-level/package-private/nested/local forms. |
| “Lambda có constructor và instance fields riêng.” | Không có class body tương tự named/anonymous. |
| “Effectively final nghĩa object immutable.” | Chỉ giới hạn reassignment của biến captured. |
| “Anonymous `this` và lambda `this` giống nhau.” | Anonymous own this; lambda lexical this. |
| “Chuyển anonymous sang lambda luôn giữ behavior.” | Có thể khác state, this, identity, target typing. |
| “Lambda không cần target type.” | Cần functional interface target. |
| “`var f = x -> x;` luôn tự suy ra type.” | Thiếu target functional type. |
| “Lambda object luôn mới mỗi evaluation.” | Identity/reuse không được bảo đảm như thế. |
| “Lambda luôn nhanh hơn.” | Phụ thuộc JVM/workload, cần benchmark. |
| “Functional interface không thể có default methods.” | Có thể, nếu còn SAM. |
| “Interface nhiều abstract methods dùng lambda.” | Không. |
| “Interface method implementation có thể giảm public.” | Không. |
| “Anonymous có constructor named.” | Không, chỉ args cho superclass và instance initializers. |
| “final/sealed restrictions không áp dụng anonymous.” | Vẫn áp dụng. |
| “Method reference và lambda luôn tương đương mọi side effect.” | Cần xem evaluation/overloads và semantics. |
| “Callback register rồi quên unregister vẫn ổn.” | Có thể giữ owner/resources reachable. |
| “Anonymous/named/lambda tự xử lý checked exceptions.” | Đều theo target/override contract. |
| “getClass().getName() là stable business ID.” | Không với generated anonymous/lambda implementations. |
| “Không cần contract tests vì code một dòng.” | Logic vẫn cần kiểm chứng. |

## 70. Checklist cuối bài

- [ ] Tôi phân biệt named class, anonymous class và lambda expression.
- [ ] Tôi biết lambda cần functional interface target.
- [ ] Tôi biết `@FunctionalInterface` giúp compiler kiểm tra SAM.
- [ ] Tôi biết interface default/static methods không tự phá SAM.
- [ ] Tôi biết abstract class một method không là lambda target.
- [ ] Tôi biết anonymous class có thể implements interface hoặc extends class.
- [ ] Tôi biết concrete/final/sealed inheritance restrictions.
- [ ] Tôi biết named class có constructor/invariants và reuse rõ.
- [ ] Tôi biết anonymous body có fields/helper methods/initializers.
- [ ] Tôi biết lambda block không có anonymous instance fields.
- [ ] Tôi phân biệt per-instance state và captured mutable holder.
- [ ] Tôi biết captured locals phải final/effectively final.
- [ ] Tôi hiểu mutable referenced object vẫn có thể đổi.
- [ ] Tôi phân biệt `this` của anonymous với lambda lexical this.
- [ ] Tôi biết `super` trong anonymous subclass khác lambda lexical super.
- [ ] Tôi biết lambda cần target typing, kể cả khi dùng overloaded methods.
- [ ] Tôi biết cast/typed variable có thể giải overload ambiguity.
- [ ] Tôi dùng method reference khi nó rõ nghĩa hơn lambda.
- [ ] Tôi tránh raw generic functional interfaces.
- [ ] Tôi không xem lambda identity là ổn định.
- [ ] Tôi lưu listener reference cho unsubscribe.
- [ ] Tôi biết checked exception tùy interface/SAM contract.
- [ ] Tôi biết type được expose ở public API quan trọng hơn syntax.
- [ ] Tôi dùng local named class khi behavior phức tạp nhưng chỉ dùng trong block.
- [ ] Tôi cân nhắc static nested named class nếu reuse nội bộ outer.
- [ ] Tôi không parse generated class names.
- [ ] Tôi không giả định mọi lambda nhanh hơn named/anonymous.
- [ ] Tôi kiểm soát lifecycle và thread safety của captured references.
- [ ] Tôi refactor theo tests, không chỉ theo số dòng.
- [ ] Tôi có thể giải thích stdout và compile errors trong bài.

**Kết luận:** Chọn **lambda** khi cần một behavior ngắn cho **functional interface** với target type rõ và không cần own instance state hay inheritance. Chọn **anonymous class** khi cần một implementation one-off có class body, nhiều methods của interface hoặc override một **class** ngay tại call site. Chọn **named class** khi behavior có trách nhiệm đủ lớn, được tái sử dụng, cần constructors/invariants, stable type/API hoặc lifecycle rõ ràng. **Hình thức chỉ là công cụ**; type contract, captured state, `this`/`super`, checked exceptions, ownership và testability mới quyết định lựa chọn đúng.
