# `implements` và vai trò hợp đồng của `interface` trong Java

Trong Java, **interface** là một kiểu tham chiếu mô tả **những khả năng hoặc hành vi mà các class triển khai phải cung cấp**. Từ khóa **`implements`** tuyên bố một class nhận trách nhiệm hiện thực các phương thức trừu tượng của interface theo quy tắc Java.

Ví dụ:

~~~java
interface Printable {
    void print();
}

class Report implements Printable {
    @Override
    public void print() {
        System.out.println("Report printed");
    }
}
~~~

Interface `Printable` nói: “Một object thuộc kiểu này có thể được yêu cầu `print()`.” Class `Report` quyết định **in cái gì và bằng cách nào**. Caller có thể làm việc với kiểu `Printable`, không cần biết class cụ thể.

Tuy nhiên, **hợp đồng (contract)** không chỉ là tên và chữ ký phương thức. Compiler kiểm tra **hình thức** như kiểu tham số, return type và quyền truy cập; còn những cam kết như “không trừ số dư khi giao dịch thất bại” hay “sort không làm mất phần tử” phải được **mô tả, lập trình và kiểm thử**. Một class biên dịch thành công vẫn có thể vi phạm hợp đồng ngữ nghĩa.

Bài này thuộc Java Core — **Class & Object / Kế thừa và đa hình**. Ví dụ dùng **Java 17+**, có filename, lệnh biên dịch và kết quả stdout khi được trình bày như chương trình độc lập. Đoạn mã minh họa hoặc đoạn cố ý không biên dịch được ghi rõ để tránh hiểu nhầm.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `interface` như một **kiểu** và **bản mô tả hợp đồng hành vi**.
2. Viết `class X implements Y` đúng cú pháp và hiểu trách nhiệm class triển khai.
3. Phân biệt khai báo abstract method trong interface với method implementation trong class.
4. Hiểu vì sao method triển khai phải có quyền truy cập tương thích (thường là `public`).
5. Dùng **interface reference** để gọi method qua **runtime polymorphism**.
6. Triển khai **nhiều interfaces** trong cùng class mà không kế thừa nhiều superclass.
7. Phân biệt `implements` với `extends` của class và interface.
8. Hiểu `default`, `static`, `private` methods và giải quyết xung đột default implementations.
9. Biết các fields trong interface là `public static final` theo ngữ nghĩa khai báo.
10. Hiểu **functional interfaces** và lambda expression không đồng nghĩa mọi interface đều là functional.
11. Thiết kế generic interfaces và dùng các implementation hoán đổi được.
12. Nắm các giới hạn của `throws`, return types, override và method visibility.
13. Nhận diện **Liskov Substitution Principle**, tiền/hậu điều kiện và bất biến.
14. Biết lúc nào interface hữu ích cho dependency injection, testing và bảo trì API.
15. Tránh tạo interfaces chỉ vì muốn “cho mọi class đều có một interface”.
16. Hiểu Java 17 `sealed interface` và mối quan hệ với `permits`.
17. Kiểm tra hợp đồng bằng test dùng chung cho nhiều implementations.

## 2. Interface là gì?

Một interface khai báo một tập **member contracts** mà các implementing types có thể cung cấp:

~~~java
interface Notifier {
    void send(String message);
}
~~~

Method `send` ở đây **ngầm là `public abstract`**: nó không có body. Class cụ thể triển khai method sẽ cung cấp body:

~~~java
class ConsoleNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println(message);
    }
}
~~~

`ConsoleNotifier` là một **subtype** của `Notifier`. Một biến kiểu `Notifier` có thể giữ reference tới `ConsoleNotifier`.

### Hợp đồng gồm nhiều mức độ

- **Chữ ký/type contract:** `send` nhận một `String`, trả `void`.
- **Visibility/access contract:** method được công khai để caller gọi qua interface.
- **Exception contract:** checked exceptions chỉ được khai báo phù hợp với method interface.
- **Behavioral contract:** `send` cần thể hiện việc gửi thông báo theo một nghĩa được tài liệu hóa.
- **State/invariant contract:** nếu có state, implementation giữ những điều kiện liên quan.
- **Performance/concurrency contract:** chỉ có nếu API hoặc tài liệu thật sự hứa; interface không tự làm method thread-safe hoặc nhanh.

Compiler bảo vệ chủ yếu phần **type-level**. Phần ngữ nghĩa phải được developer và tests kiểm chứng.

## 3. Cú pháp `implements`

Một class triển khai một interface:

~~~java
class EmailSender implements Sender {
    // Hiện thực các abstract methods của Sender.
}
~~~

Triển khai nhiều interfaces:

~~~java
class SmartDevice implements Switchable, Monitorable, Resettable {
    // Hiện thực các abstract methods cần thiết.
}
~~~

Nếu một class vừa kế thừa superclass vừa triển khai interfaces:

~~~java
class Employee extends Person implements Identifiable, Printable {
}
~~~

**Thứ tự đúng:** `extends SuperClass` rồi `implements Interface1, Interface2`.

Java chỉ cho một class có **tối đa một superclass trực tiếp** bằng `extends` (ngoại trừ Object là gốc), nhưng có thể triển khai **nhiều interfaces**. Điều này cho phép phối hợp nhiều khả năng mà không cần multiple inheritance của class implementation/state.

### Class phải triển khai đủ những gì?

Một class **concrete** phải có implementation cho các abstract methods liên quan mà nó chưa được thừa hưởng một implementation phù hợp. Nếu chưa triển khai đầy đủ, class phải được khai báo `abstract` hoặc compiler báo lỗi.

~~~java
interface RunnableTask {
    void run();
}

// Không hợp lệ nếu bỏ abstract mà không định nghĩa run().
abstract class TaskBase implements RunnableTask {
}
~~~

Một subclass concrete có thể hoàn tất phần còn lại.

## 4. Ví dụ chạy đầu tiên: interface reference và runtime dispatch

Tạo file **`InterfacePolymorphismDemo.java`**:

~~~java
public class InterfacePolymorphismDemo {
    interface Greeter {
        String greet(String name);
    }

    static final class VietnameseGreeter implements Greeter {
        @Override
        public String greet(String name) {
            return "Xin chào, " + name;
        }
    }

    static final class EnglishGreeter implements Greeter {
        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

    static void show(Greeter greeter) {
        System.out.println(greeter.greet("Mai"));
    }

    public static void main(String[] args) {
        Greeter first = new VietnameseGreeter();
        Greeter second = new EnglishGreeter();

        show(first);
        show(second);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfacePolymorphismDemo.java
java InterfacePolymorphismDemo
~~~

Stdout:

~~~text
Xin chào, Mai
Hello, Mai
~~~

Cùng method `show(Greeter greeter)` nhận hai objects của hai implementation classes. Tại runtime, `greeter.greet(...)` gọi **implementation phù hợp với actual object**.

**Hai điểm cần phân biệt:**

1. Biến `first` được khai báo kiểu `Greeter`, nhưng actual object là `VietnameseGreeter`.
2. Compiler cho phép gọi những methods hiện diện trong contract `Greeter`. Không thể tùy ý gọi method riêng của VietnameseGreeter qua một reference chỉ biết kiểu Greeter nếu không có phép chuyển kiểu hợp lệ.

Đây là ví dụ điển hình của **programming to an interface**.

## 5. `@Override` và quyền truy cập `public`

Với interface:

~~~java
interface Operation {
    int execute(int value);
}
~~~

Implementation hợp lệ:

~~~java
class DoubleOperation implements Operation {
    @Override
    public int execute(int value) {
        return value * 2;
    }
}
~~~

Nhưng:

~~~java
class Incorrect implements Operation {
    // int execute(int value) { return value * 2; }
    // Lỗi nếu bỏ comment: quyền truy cập yếu hơn public.
    @Override
    public int execute(int value) {
        return value * 2;
    }
}
~~~

Trong interface, abstract instance method thường ngầm là **public abstract**. Method khi implement **không thể hạ** quyền truy cập thành package-private hoặc protected.

`@Override` rất nên dùng vì compiler xác minh rằng method thực sự override/implement member phù hợp. Nếu gõ sai tên hoặc tham số, annotation giúp phát hiện sớm.

### Vì sao không viết thiếu `public`?

Trong một class, method **không có access modifier** là package-private, không phải public. Vì vậy:

~~~java
// int execute(int value) { ... }
~~~

không thỏa quyền công khai mà interface yêu cầu. Thêm `public` là sửa đúng, không phải mở quyền ngẫu nhiên.

## 6. Method signature: tên, tham số và return type

Một class phải thực hiện method theo chữ ký phù hợp.

Interface:

~~~java
interface Calculator {
    long calculate(int x, int y);
}
~~~

Đúng:

~~~java
class AddCalculator implements Calculator {
    @Override
    public long calculate(int x, int y) {
        return (long) x + y;
    }
}
~~~

Sai nếu thay `calculate(int,int)` bằng `calculate(long,long)`: đó là **overload** khác danh sách tham số, không phải method implement contract. Nếu class concrete không có implementation cho `calculate(int,int)`, compiler báo lỗi.

### Return type có thể covariant

Với reference return types, Java có thể cho phép implementation trả subtype phù hợp:

~~~java
interface Maker {
    Number make();
}

class IntegerMaker implements Maker {
    @Override
    public Integer make() {
        return 10;
    }
}
~~~

`Integer` là subtype của `Number`. Với primitive return types, không áp dụng quy tắc covariant theo cùng cách: đổi `long` thành `int` khi override method `long calculate(...)` không phải một implementation hợp lệ.

## 7. Ví dụ chạy: một contract, nhiều thuật toán

Tạo file **`StrategyInterfaceDemo.java`**:

~~~java
public class StrategyInterfaceDemo {
    interface DiscountPolicy {
        long apply(long originalCents);
    }

    static final class NoDiscount implements DiscountPolicy {
        @Override
        public long apply(long originalCents) {
            if (originalCents < 0) {
                throw new IllegalArgumentException("negative price");
            }
            return originalCents;
        }
    }

    static final class FixedDiscount implements DiscountPolicy {
        private final long discountCents;

        FixedDiscount(long discountCents) {
            if (discountCents < 0) {
                throw new IllegalArgumentException("negative discount");
            }
            this.discountCents = discountCents;
        }

        @Override
        public long apply(long originalCents) {
            if (originalCents < 0) {
                throw new IllegalArgumentException("negative price");
            }
            return Math.max(0, originalCents - discountCents);
        }
    }

    static void printResult(DiscountPolicy policy) {
        System.out.println("price=" + policy.apply(1_000));
    }

    public static void main(String[] args) {
        printResult(new NoDiscount());
        printResult(new FixedDiscount(250));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrategyInterfaceDemo.java
java StrategyInterfaceDemo
~~~

Stdout:

~~~text
price=1000
price=750
~~~

Caller nhận `DiscountPolicy`. Logic giảm giá được thay bằng implementation khác mà không phải thay code của `printResult`.

**Giới hạn của demo:** Đây chỉ là quy tắc giảm cố định theo `long` cents. Hệ thống thanh toán thật phải xác định currency, giới hạn, cách làm tròn, tràn số và quy tắc nghiệp vụ. Hai implementations đều tuân theo ví dụ contract “input không âm, output không âm và không lớn hơn original”, còn compiler **không tự chứng minh** contract đó.

## 8. Kiểu biến interface giới hạn các phương thức thấy được

Cho:

~~~java
interface Worker {
    void work();
}

class Developer implements Worker {
    @Override
    public void work() {
        System.out.println("coding");
    }

    public void debug() {
        System.out.println("debugging");
    }
}
~~~

Nếu:

~~~java
Worker worker = new Developer();
worker.work();
// worker.debug(); // Không biên dịch với declared type Worker.
~~~

Method `debug` chỉ khai báo trong Developer, không nằm trong interface Worker.

Nếu thực sự cần method riêng, có thể dùng **checked cast**:

~~~java
if (worker instanceof Developer developer) {
    developer.debug();
}
~~~

Java 17 hỗ trợ pattern variable trong `instanceof`. Tuy nhiên việc thường xuyên ép kiểu về implementation cụ thể là dấu hiệu caller có thể đang **phụ thuộc quá nhiều vào class cụ thể**, làm mất lợi ích của interface abstraction.

### Interface reference không che mất runtime identity

`Worker worker = new Developer()` không tạo “một Worker object riêng”. Reference vẫn trỏ **cùng Developer instance**, và virtual invocation dùng method runtime tương ứng.

## 9. `implements` không tạo bản sao object hay state

Ví dụ:

~~~java
interface Named {
    String name();
}

class Student implements Named {
    private String name;

    Student(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}
~~~

Nếu:

~~~java
Student student = new Student("Mai");
Named named = student;
~~~

thì `student == named` là true. Đó là **hai biến tham chiếu cùng một Student object**, không có object interface độc lập.

Vì interface không có instance fields của riêng nó, `implements` không “gắn thêm một vùng instance state của interface” vào object theo nghĩa có một bản field instance khai báo trong interface. Những abstract methods chỉ là trách nhiệm mà class phải đáp ứng.

## 10. Interface kế thừa interface bằng `extends`

Interface có thể kế thừa interface khác:

~~~java
interface Readable {
    String read();
}

interface Writable {
    void write(String value);
}

interface ReadWrite extends Readable, Writable {
}
~~~

`ReadWrite` kết hợp hai contracts. Class:

~~~java
class MemoryDocument implements ReadWrite {
    private String value = "";

    @Override
    public String read() {
        return value;
    }

    @Override
    public void write(String value) {
        this.value = java.util.Objects.requireNonNull(value);
    }
}
~~~

phải đáp ứng cả `read` và `write`.

**Cú pháp quan trọng:** Interface **extends** interfaces, class **implements** interfaces. Không viết `interface ReadWrite implements Readable`.

Một interface có thể `extends` **nhiều interfaces**. Điều này khác class chỉ `extends` một superclass trực tiếp.

## 11. Ví dụ chạy: nhiều interface capabilities

Tạo file **`MultipleInterfacesDemo.java`**:

~~~java
public class MultipleInterfacesDemo {
    interface Printable {
        void print();
    }

    interface Saveable {
        void save();
    }

    static final class Document implements Printable, Saveable {
        private final String title;

        Document(String title) {
            this.title = title;
        }

        @Override
        public void print() {
            System.out.println("print: " + title);
        }

        @Override
        public void save() {
            System.out.println("save: " + title);
        }
    }

    static void printOnly(Printable item) {
        item.print();
    }

    static void saveOnly(Saveable item) {
        item.save();
    }

    public static void main(String[] args) {
        Document doc = new Document("README");
        printOnly(doc);
        saveOnly(doc);
    }
}
~~~

~~~bash
javac -encoding UTF-8 MultipleInterfacesDemo.java
java MultipleInterfacesDemo
~~~

Stdout:

~~~text
print: README
save: README
~~~

Một Document object có thể được quan sát như `Printable` hoặc `Saveable`. Hai references không tạo hai bản dữ liệu title. Mỗi method nhận **đúng capability nó cần**, giảm coupling với cả class Document.

### Interface Segregation Principle

Một interface nhỏ, tập trung vào hành vi có nghĩa thường dễ dùng hơn interface bắt mọi implementation phải cung cấp hàng chục methods không liên quan. Tuy nhiên đừng tách cực đoan thành vô số interfaces một method chỉ vì muốn áp dụng nguyên tắc. Hãy nhóm theo **use case, trách nhiệm và tính nhất quán của contract**.

## 12. Abstract class triển khai interface chưa đầy đủ

Một abstract class có thể chưa implement tất cả abstract methods:

~~~java
interface Processor {
    void validate();
    void process();
}

abstract class BaseProcessor implements Processor {
    @Override
    public void validate() {
        System.out.println("validated");
    }

    // process() chưa được implement ở lớp abstract này.
}

class ConcreteProcessor extends BaseProcessor {
    @Override
    public void process() {
        System.out.println("processed");
    }
}
~~~

ConcreteProcessor nhận implementation `validate` từ superclass, tự implement `process`. Nó vẫn thực hiện contract Processor.

Một class concrete không được bỏ thiếu abstract method, trừ khi kế thừa implementation phù hợp từ superclass hoặc interface default method trong những trường hợp có hiệu lực.

### Interface và abstract class giải quyết hai nhu cầu

- Interface xác định một **khả năng và contract có thể được nhiều class không liên quan cùng implement**.
- Abstract class có thể chia sẻ **instance state, constructors và protected helper methods** giữa các subclasses có quan hệ is-a thực sự.

Không dùng interface chỉ để thay thế một superclass có mutable state chung. Interface fields là static constants, không phải per-instance state.

## 13. Fields trong interface là constants, không phải instance fields

Bên trong interface:

~~~java
interface Limits {
    int MAX_RETRIES = 3;
}
~~~

Field `MAX_RETRIES` ngầm có modifiers **`public static final`**, tương đương ý nghĩa:

~~~java
interface Limits {
    public static final int MAX_RETRIES = 3;
}
~~~

Nó **không** là instance field dành riêng cho mỗi implementing object.

### Không thể gán lại interface field

~~~java
// Limits.MAX_RETRIES = 5; // Lỗi: final variable.
~~~

Một implementing class không có “bản MAX_RETRIES riêng” chỉ vì implements Limits. Nếu class cần config theo instance, khai báo field trong class:

~~~java
class Retrier {
    private final int maxRetries;

    Retrier(int maxRetries) {
        this.maxRetries = maxRetries;
    }
}
~~~

### Interface constant có rủi ro coupling

Đưa các static constants unrelated vào một interface chỉ để classes `implements Constants` và lấy tên ngắn là một **constant interface anti-pattern**. Ưu tiên một utility/config class phù hợp và truy cập qualified name `Limits.MAX_RETRIES`. Interface nên mô tả **capability**, không chỉ là túi hằng số.

## 14. Các loại methods trong interface (Java 17)

| Loại | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Abstract instance | `void send();` | Implementing class phải cung cấp body nếu chưa được thừa hưởng |
| `default` instance | `default String label() { ... }` | Interface cung cấp implementation mặc định có thể override |
| `static` | `static int max() { ... }` | Phương thức thuộc interface, gọi bằng tên interface |
| `private` instance | `private void helper() { ... }` | Helper chỉ dùng trong code của chính interface |
| `private static` | `private static int parse() { ... }` | Static helper riêng bên trong interface |

**Không có constructor trong interface.** Không thể `new InterfaceName()` để tạo instance trực tiếp. Anonymous class hoặc lambda có thể tạo object thuộc implementation type với functional interface, nhưng không biến interface thành class có constructor của riêng nó.

### Mặc định của abstract method

~~~java
interface Action {
    void run(); // public abstract ngầm định.
}
~~~

Có thể khai báo `public abstract void run();` tường minh, nhưng thường không cần.

Không nhầm `default` method với default access (package-private): `default` là **interface method có body và cơ chế kế thừa đặc biệt**, còn abstract methods của interface mặc nhiên public.

## 15. Default methods: bổ sung hành vi mặc định

~~~java
interface Named {
    String name();

    default String decoratedName() {
        return "[" + name() + "]";
    }
}
~~~

Một implementing class chỉ cần implement `name()`; `decoratedName()` đã có implementation mặc định và có thể dùng `name()` động (dynamic dispatch) của actual object.

### Ví dụ chạy

Tạo file **`DefaultMethodDemo.java`**:

~~~java
public class DefaultMethodDemo {
    interface Named {
        String name();

        default String decoratedName() {
            return "[" + name() + "]";
        }
    }

    static final class Person implements Named {
        private final String name;

        Person(String name) {
            this.name = name;
        }

        @Override
        public String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Named named = new Person("Mai");

        System.out.println(named.name());
        System.out.println(named.decoratedName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefaultMethodDemo.java
java DefaultMethodDemo
~~~

Stdout:

~~~text
Mai
[Mai]
~~~

**Không kết luận:** default method “tự động đúng” cho mọi implementing class. Nếu default behavior áp đặt giả định mà một implementation không thể đáp ứng, class nên override hoặc contract của interface phải được thiết kế lại.

Default methods đặc biệt hữu ích để thêm một operation dựa trên những abstract methods hiện có mà không bắt buộc mọi implementation viết lại cùng một logic. Nhưng API evolution cần cẩn thận vì default methods có thể xung đột với các interfaces khác.

## 16. Static interface methods không được gọi như instance default methods

~~~java
interface TextTools {
    static String upper(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

Gọi:

~~~java
String result = TextTools.upper("java");
~~~

Không gọi `new SomeImplementation().upper(...)` chỉ vì class implements TextTools. Static interface methods gắn với interface khai báo, **không được thừa hưởng như instance methods**.

### Ví dụ chạy

Tạo **`StaticInterfaceMethodDemo.java`**:

~~~java
import java.util.Locale;

public class StaticInterfaceMethodDemo {
    interface Formatter {
        String format(String value);

        static String normalized(String value) {
            return value.strip().toUpperCase(Locale.ROOT);
        }
    }

    static final class SimpleFormatter implements Formatter {
        @Override
        public String format(String value) {
            return "[" + Formatter.normalized(value) + "]";
        }
    }

    public static void main(String[] args) {
        Formatter formatter = new SimpleFormatter();
        System.out.println(formatter.format(" java "));
        System.out.println(Formatter.normalized(" hello "));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticInterfaceMethodDemo.java
java StaticInterfaceMethodDemo
~~~

Stdout:

~~~text
[JAVA]
HELLO
~~~

Static method ở đây là helper đi cùng contract. Nó không yêu cầu class implement một method khác.

## 17. Private methods trong interface dùng để tái sử dụng implementation nội bộ

Từ Java 9, interface có thể khai báo private methods với body:

~~~java
interface Greeting {
    String name();

    default String formal() {
        return wrap("Dear " + name());
    }

    default String casual() {
        return wrap("Hi " + name());
    }

    private String wrap(String text) {
        return "<" + text + ">";
    }
}
~~~

`wrap` phục vụ hai default methods, không là member public để caller gọi, và không phải abstract method cần implementing class implement.

### Ví dụ chạy

Tạo **`PrivateInterfaceMethodDemo.java`**:

~~~java
public class PrivateInterfaceMethodDemo {
    interface Message {
        String content();

        default String markdown() {
            return decorate("**", content(), "**");
        }

        default String quoted() {
            return decorate("\"", content(), "\"");
        }

        private static String decorate(
                String before, String value, String after) {
            return before + value + after;
        }
    }

    record Note(String content) implements Message {}

    public static void main(String[] args) {
        Message m = new Note("Java");
        System.out.println(m.markdown());
        System.out.println(m.quoted());
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrivateInterfaceMethodDemo.java
java PrivateInterfaceMethodDemo
~~~

Stdout:

~~~text
**Java**
"Java"
~~~

Record `Note` implements `Message` nhờ accessor `content()` được tạo ra bởi record, có kiểu `String` và public. Không cần viết lại method chỉ để đáp ứng abstract accessor. `private static decorate` chỉ thực thi từ code trong interface, không hiển thị cho caller.

## 18. Xung đột hai default methods

Nếu hai unrelated interfaces cùng cung cấp default method có chữ ký tương ứng, implementing class có thể phải **override và tự chọn behavior**.

~~~java
interface Left {
    default String value() {
        return "left";
    }
}

interface Right {
    default String value() {
        return "right";
    }
}
~~~

Không thể viết một class concrete `implements Left, Right` rồi mặc nhiên chờ Java chọn ngẫu nhiên một method. Phải giải quyết conflict:

~~~java
class Both implements Left, Right {
    @Override
    public String value() {
        return Left.super.value() + "+" + Right.super.value();
    }
}
~~~

`Left.super.value()` và `Right.super.value()` gọi default implementations cụ thể từ implementing class khi hợp lệ.

### Ví dụ chạy

Tạo **`DefaultConflictDemo.java`**:

~~~java
public class DefaultConflictDemo {
    interface Left {
        default String label() {
            return "L";
        }
    }

    interface Right {
        default String label() {
            return "R";
        }
    }

    static final class Both implements Left, Right {
        @Override
        public String label() {
            return Left.super.label() + Right.super.label();
        }
    }

    public static void main(String[] args) {
        Both object = new Both();
        System.out.println(object.label());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefaultConflictDemo.java
java DefaultConflictDemo
~~~

Stdout:

~~~text
LR
~~~

**Thông điệp:** Java hỗ trợ multiple interface inheritance, nhưng không tự động cho phép “hai implementations cùng tên tự kết hợp” mà không có luật giải quyết rõ.

## 19. Quy tắc ưu tiên: class method và specificity

Khi xem default method, nhớ những quy tắc tổng quát:

1. **Method cụ thể phù hợp từ class/superclass thường thắng interface default method** khi được thừa hưởng theo các quy tắc.
2. Với hierarchy interfaces, **default method cụ thể hơn** có thể được lựa chọn so với inherited default method ít cụ thể hơn.
3. Khi hai unrelated defaults xung đột, class phải override để giải quyết.

### Ví dụ class ưu tiên

Tạo file **`ClassWinsDefaultDemo.java`**:

~~~java
public class ClassWinsDefaultDemo {
    interface Speaker {
        default String speak() {
            return "interface";
        }
    }

    static class Base {
        public String speak() {
            return "class";
        }
    }

    static final class Child extends Base implements Speaker {
    }

    public static void main(String[] args) {
        Speaker speaker = new Child();
        System.out.println(speaker.speak());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassWinsDefaultDemo.java
java ClassWinsDefaultDemo
~~~

Stdout:

~~~text
class
~~~

`Child` nhận method `speak` từ Base, nên việc gọi qua reference Speaker vẫn dispatch đến implementation `Base.speak()` thích hợp.

**Cẩn thận:** “Class wins” là một lối nhớ ngắn, không thay thế toàn bộ JLS rules về abstract/concrete methods, visibility, generic erasure và inheritance. Khi signatures phức tạp, hãy kiểm tra compiler và đặc tả Java.

## 20. Object methods và interface

Mọi class trong Java cuối cùng có các methods liên quan Object như `toString()`, `equals(Object)` và `hashCode()`. Interface cũng tương tác với những methods này, nhưng không nên tùy tiện tạo default implementation override một method của Object.

Đoạn cố ý không hợp lệ:

~~~java
interface Bad {
    // default String toString() {
    //     return "bad";
    // }
}
~~~

Một default method trong interface mà override-equivalent với non-private method của Object không được phép theo quy tắc Java.

Một implementation class có thể override Object methods một cách bình thường để thể hiện equality/representation theo contract:

~~~java
final class Id {
    private final String value;

    Id(String value) {
        this.value = value;
    }

    @Override
    public String toString() {
        return value;
    }
}
~~~

Nếu một interface **đề cập** identity/equality về mặt contract, cần tài liệu rõ và implementations nhất quán, đặc biệt khi object dùng làm key trong Map/Set.

## 21. Functional interface và lambda

Một **functional interface** có đúng **một abstract method** theo quy tắc của Java, dù có thể chứa nhiều default/static/private methods. Nó có thể là **target type** của lambda expression hoặc method reference.

~~~java
@FunctionalInterface
interface Transformer {
    String transform(String input);

    default String twice(String input) {
        return transform(transform(input));
    }
}
~~~

`@FunctionalInterface` không bắt buộc nhưng hữu ích vì compiler kiểm tra interface đáp ứng tiêu chí functional. Nếu thêm một abstract method độc lập khác, compiler phát hiện sai.

### Ví dụ chạy

Tạo file **`FunctionalInterfaceDemo.java`**:

~~~java
public class FunctionalInterfaceDemo {
    @FunctionalInterface
    interface Transformer {
        String transform(String input);

        default String twice(String input) {
            return transform(transform(input));
        }
    }

    public static void main(String[] args) {
        Transformer addX = text -> text + "X";

        System.out.println(addX.transform("A"));
        System.out.println(addX.twice("A"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FunctionalInterfaceDemo.java
java FunctionalInterfaceDemo
~~~

Stdout:

~~~text
AX
AXX
~~~

Lambda được Java gán vào functional interface `Transformer`. Không phải mọi interface đều cho lambda: nếu có hai abstract methods khác nhau cần implement thì lambda đơn lẻ không đủ.

**Một lưu ý:** Abstract methods có chữ ký tương ứng những public methods của `Object` được xử lý đặc biệt khi xác định functional interface; không đơn giản đếm mọi dòng method declaration. Hãy dùng `@FunctionalInterface` để compiler kiểm tra chính xác.

## 22. Interface reference và collections

Một collection có thể khai báo theo kiểu interface để lưu nhiều implementations:

~~~java
java.util.List<Notifier> notifiers = new java.util.ArrayList<>();
notifiers.add(new ConsoleNotifier());
notifiers.add(new FileNotifier());
~~~

Khi duyệt:

~~~java
for (Notifier notifier : notifiers) {
    notifier.send("hello");
}
~~~

method được dispatch đến implementation của từng object.

Đây là mã minh họa; `Notifier`, `ConsoleNotifier`, `FileNotifier` phải có declarations tương ứng. Kiểu `List<Notifier>` không yêu cầu các elements thuộc cùng một concrete class — chỉ cần mỗi element có kiểu tương thích `Notifier`.

### Nhưng generic invariance cần nhớ

`List<ConsoleNotifier>` **không tự là subtype** của `List<Notifier>` trong Java generic types, dù ConsoleNotifier implements Notifier. Nếu được phép coi List<ConsoleNotifier> là List<Notifier>, caller có thể thêm FileNotifier vào danh sách chỉ được phép chứa ConsoleNotifier.

Để chỉ **đọc các subtype implementations**, có thể dùng:

~~~java
void broadcast(java.util.List<? extends Notifier> targets) {
    for (Notifier target : targets) {
        target.send("hello");
    }
}
~~~

Wildcard `? extends Notifier` phù hợp với consumer method chỉ cần đọc ra các Notifier references để gọi `send`, không thêm phần tử tùy ý vào list.

## 23. Generic interface: hợp đồng tái sử dụng theo kiểu

Một interface có thể generic:

~~~java
interface Repository<T, ID> {
    T findById(ID id);
    void save(T entity);
}
~~~

Một implementation cụ thể:

~~~java
class InMemoryBookRepository
        implements Repository<Book, String> {
    @Override
    public Book findById(String id) {
        // Lookup by id.
        return null;
    }

    @Override
    public void save(Book entity) {
        // Store entity.
    }
}
~~~

Đây là mảnh code minh họa (cần class Book và implementation lưu trữ thật). Khi implements `Repository<Book, String>`, method signatures được chuyên biệt hóa theo `Book` và `String` theo quy tắc generics.

### Ví dụ chạy đủ: generic Box contract

Tạo **`GenericInterfaceDemo.java`**:

~~~java
public class GenericInterfaceDemo {
    interface Box<T> {
        void put(T value);
        T get();
    }

    static final class MemoryBox<T> implements Box<T> {
        private T value;

        @Override
        public void put(T value) {
            this.value = value;
        }

        @Override
        public T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> message = new MemoryBox<>();
        Box<Integer> count = new MemoryBox<>();

        message.put("Java");
        count.put(17);

        System.out.println("message=" + message.get());
        System.out.println("count=" + count.get());
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericInterfaceDemo.java
java GenericInterfaceDemo
~~~

Stdout:

~~~text
message=Java
count=17
~~~

Một generic interface giúp tái dùng contract mà compiler vẫn kiểm tra kiểu phần tử. Tuy nhiên generics trong Java có **type erasure**; `Box<String>` và `Box<Integer>` không phải hai runtime interface classes khác nhau chỉ vì type arguments.

## 24. Checked exceptions và `throws` trong implementation

Interface method có thể tuyên bố checked exceptions:

~~~java
interface Reader {
    String read() throws java.io.IOException;
}
~~~

Implementation có thể:

- Ném `IOException` theo declaration phù hợp.
- Ném một checked subtype của IOException.
- Không khai báo checked exception nào.

Nhưng không được tùy ý mở rộng checked exceptions ngoài contract của overridden method:

~~~java
class MemoryReader implements Reader {
    @Override
    public String read() {
        return "memory";
    }
}
~~~

**Không hợp lệ nếu** implementation đổi thành `read() throws Exception`, vì `Exception` rộng hơn IOException và không thỏa luật overriding về checked exceptions.

### Một điểm tinh tế

Một method interface **không khai báo checked exception** không ngăn implementation ném unchecked exceptions như `IllegalArgumentException` hoặc `IllegalStateException`. Nhưng người thiết kế API nên tài liệu hóa những error conditions có giá trị dự đoán, thay vì giấu toàn bộ hành vi lỗi khỏi caller.

## 25. Ví dụ chạy: contract checked exception

Tạo file **`CheckedExceptionInterfaceDemo.java`**:

~~~java
import java.io.IOException;

public class CheckedExceptionInterfaceDemo {
    interface DataSource {
        String load() throws IOException;
    }

    static final class MemorySource implements DataSource {
        @Override
        public String load() {
            return "cached";
        }
    }

    static final class FailingSource implements DataSource {
        @Override
        public String load() throws IOException {
            throw new IOException("unavailable");
        }
    }

    static void show(DataSource source) {
        try {
            System.out.println(source.load());
        } catch (IOException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        show(new MemorySource());
        show(new FailingSource());
    }
}
~~~

~~~bash
javac -encoding UTF-8 CheckedExceptionInterfaceDemo.java
java CheckedExceptionInterfaceDemo
~~~

Stdout:

~~~text
cached
error=unavailable
~~~

Vì `show` gọi qua reference `DataSource`, compiler yêu cầu code xử lý hoặc khai báo `IOException` ngay cả khi actual object có thể là MemorySource không ném checked exception. **Declared interface type** định hình nghĩa vụ compile-time của caller.

## 26. Contract ngữ nghĩa: compiler không chứng minh phương thức “đúng”

Xem:

~~~java
interface Sorter {
    void sort(int[] values);
}
~~~

Một class có thể viết:

~~~java
class BrokenSorter implements Sorter {
    @Override
    public void sort(int[] values) {
        java.util.Arrays.fill(values, 0);
    }
}
~~~

Chữ ký hợp lệ, compiler chấp nhận. Nhưng nếu contract yêu cầu:

- Sau khi sort, array được sắp xếp không giảm.
- Không làm mất hoặc thêm phần tử (giữ multiset ban đầu).
- Không thay độ dài array.

thì `BrokenSorter` **vi phạm hợp đồng** vì thay toàn bộ elements thành 0. Đoạn mã trên chỉ để phân biệt **syntactic contract** với **behavioral contract**.

### Viết contract đủ rõ

Một interface nên ghi những điều có ý nghĩa:

- **Preconditions:** input có được null không? Có giới hạn kích thước không?
- **Postconditions:** kết quả/observable state sau thành công.
- **Failure behavior:** khi input sai hoặc I/O lỗi, điều gì xảy ra?
- **Mutation ownership:** method được thay đối tượng input không?
- **Invariants:** những điều luôn đúng qua các operations.
- **Concurrency guarantees:** thread-safe, nonblocking hoặc không có cam kết.
- **Ordering/idempotence:** kết quả có phụ thuộc thứ tự và có thể gọi lặp không?

Compiler chỉ xác minh một phần của những quy tắc này; tests và review cần xác minh phần còn lại.

## 27. Behavioral substitutability và nguyên tắc Liskov

**Liskov Substitution Principle (LSP)** trong bối cảnh interface: một implementing class phải có thể được dùng tại nơi interface được kỳ vọng **mà không làm hỏng những giả định hợp lệ của caller**.

Ví dụ, interface:

~~~java
interface Queue<E> {
    void enqueue(E item);
    E dequeue();
}
~~~

Nếu contract nói `enqueue` của non-null item thêm vào cuối queue, `dequeue` trả phần tử vào sớm nhất khi không rỗng, một implementation nhận item rồi lặng lẽ bỏ đi sẽ vi phạm hành vi dù signatures đúng.

### Những dấu hiệu vi phạm

- Implementation bất ngờ ném `UnsupportedOperationException` cho operation mà contract cam kết hỗ trợ.
- Thắt chặt precondition không được contract cho phép.
- Không giữ postcondition hoặc invariant mà caller dựa vào.
- Thay ý nghĩa dữ liệu trả về.
- Đổi semantics của ordering hoặc atomicity trái tài liệu.

Một interface quá rộng có thể ép implementation có khả năng thiếu hỗ trợ thật. Khi đó cân nhắc **tách interface theo capability** thay vì implement method bằng exception vô điều kiện.

## 28. Contract test dùng chung cho nhiều implementations

Một cách kiểm chứng hành vi là viết **cùng bộ test logic** cho mọi implementation.

Tạo file **`ContractTestDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ContractTestDemo {
    interface Stack {
        void push(int value);
        int pop();
        boolean isEmpty();
    }

    static final class ArrayStack implements Stack {
        private final List<Integer> items = new ArrayList<>();

        @Override
        public void push(int value) {
            items.add(value);
        }

        @Override
        public int pop() {
            if (items.isEmpty()) {
                throw new IllegalStateException("empty stack");
            }
            return items.remove(items.size() - 1);
        }

        @Override
        public boolean isEmpty() {
            return items.isEmpty();
        }
    }

    static final class LinkedStack implements Stack {
        private final java.util.ArrayDeque<Integer> items =
                new java.util.ArrayDeque<>();

        @Override
        public void push(int value) {
            items.push(value);
        }

        @Override
        public int pop() {
            if (items.isEmpty()) {
                throw new IllegalStateException("empty stack");
            }
            return items.pop();
        }

        @Override
        public boolean isEmpty() {
            return items.isEmpty();
        }
    }

    static void verify(Stack stack) {
        if (!stack.isEmpty()) {
            throw new AssertionError("new stack must be empty");
        }
        stack.push(10);
        stack.push(20);

        if (stack.pop() != 20 || stack.pop() != 10) {
            throw new AssertionError("LIFO violated");
        }

        if (!stack.isEmpty()) {
            throw new AssertionError("stack must be empty");
        }
    }

    public static void main(String[] args) {
        verify(new ArrayStack());
        System.out.println("ArrayStack PASS");

        verify(new LinkedStack());
        System.out.println("LinkedStack PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ContractTestDemo.java
java ContractTestDemo
~~~

Stdout:

~~~text
ArrayStack PASS
LinkedStack PASS
~~~

Cùng một hàm `verify(Stack)` nhận hai implementations. Nó kiểm tra **LIFO** và trạng thái rỗng sau push/pop. Nếu thay implementation bằng một class sai semantics, test có thể phát hiện.

**Hạn chế:** Một vài assertions không thể chứng minh mọi tình huống. Test thêm empty pop behavior, push nhiều phần tử, duplicates, boundary, concurrency nếu contract yêu cầu. Với dự án thật có thể dùng JUnit parameterized tests hoặc một abstract contract-test suite.

## 29. Interface cho dependency injection

Một service dùng dependency theo interface:

~~~java
interface EmailGateway {
    void deliver(String to, String message);
}

class RegistrationService {
    private final EmailGateway gateway;

    RegistrationService(EmailGateway gateway) {
        this.gateway = java.util.Objects.requireNonNull(gateway);
    }

    void register(String email) {
        gateway.deliver(email, "Welcome");
    }
}
~~~

`RegistrationService` không cần biết email được gửi qua SMTP, cloud provider hay một fake in-memory. Nó chỉ cần một `EmailGateway` tuân thủ contract.

Trong test, có thể cung cấp fake implementation để tránh gửi email thật.

### Lợi ích thực tế

1. **Thay thế implementation** mà service không thay đổi.
2. **Cô lập tests** khỏi mạng/file/database khi có fake phù hợp.
3. **Quản lý lifecycle** bằng constructor injection thay vì static global fields.
4. **Giảm coupling** tới implementation details.
5. Dễ đưa thêm logging/retry adapter nếu contract cho phép.

Không có nghĩa mỗi class phải có interface riêng chỉ để dễ mock. Hãy tạo abstraction tại **boundary có nhiều implementation hợp lý hoặc có nhu cầu thay thế rõ ràng**.

## 30. Ví dụ chạy: fake implementation trong kiểm thử

Tạo **`InterfaceInjectionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class InterfaceInjectionDemo {
    interface Notifier {
        void notifyUser(String message);
    }

    static final class MemoryNotifier implements Notifier {
        private final List<String> messages = new ArrayList<>();

        @Override
        public void notifyUser(String message) {
            messages.add(message);
        }

        List<String> messagesSnapshot() {
            return List.copyOf(messages);
        }
    }

    static final class RegistrationService {
        private final Notifier notifier;

        RegistrationService(Notifier notifier) {
            this.notifier = Objects.requireNonNull(notifier);
        }

        void register(String userName) {
            if (userName == null || userName.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            notifier.notifyUser("Welcome " + userName);
        }
    }

    public static void main(String[] args) {
        MemoryNotifier fake = new MemoryNotifier();
        RegistrationService service = new RegistrationService(fake);

        service.register("Mai");
        service.register("An");

        System.out.println(fake.messagesSnapshot());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceInjectionDemo.java
java InterfaceInjectionDemo
~~~

Stdout:

~~~text
[Welcome Mai, Welcome An]
~~~

`RegistrationService` chỉ biết contract `Notifier`; việc quan sát fake messages là chuyện ở test wiring, không phải service phụ thuộc fake implementation. Trong production có thể truyền implementation khác thực sự gửi thông báo.

**Không nhầm:** Một fake implementation phải vẫn mô phỏng những semantics cần thiết để test đáng tin; nếu fake bỏ qua logic retry, authorization hoặc error conditions quan trọng, cần integration tests với hệ thống thật.

## 31. Interface so với abstract class

| Tiêu chí | Interface | Abstract class |
| --- | --- | --- |
| Mục đích nổi bật | Capability/contract dùng cho nhiều types | Base class chia sẻ implementation/state |
| Class thực hiện | `implements` | `extends` |
| Một class có thể dùng nhiều? | Implements nhiều interfaces | Extends một superclass trực tiếp |
| Constructor | Không | Có |
| Instance fields | Không khai báo instance field trong interface | Có |
| Constants | Interface fields là public static final | Có thể có các loại fields |
| Method không có body | Abstract methods | Abstract methods |
| Method có body | default/static/private theo quy tắc | Concrete instance/static methods |
| Protected member | Không dùng protected interface member | Có thể dùng protected |
| Phù hợp | Contracts không phụ thuộc hierarchy | Hành vi/chung state giữa subclasses |

### Quy tắc chọn

- “A **là một loại** B và thực sự kế thừa state/hành vi chung”: cân nhắc class inheritance.
- “A có khả năng thực hiện B nhưng không nhất thiết thuộc cùng family class”: cân nhắc interface.
- “A **có một** B được dùng để làm việc”: cân nhắc composition/dependency injection.

Không thiết kế interface chỉ để thay việc kế thừa một helper có state; cũng không ép các class không liên quan cùng extends một abstract base class khi chỉ cần chung capability.

## 32. Interface và record, enum

Records có thể implements interfaces; ví dụ:

~~~java
interface HasId {
    String id();
}

record Product(String id, String name) implements HasId {
}
~~~

Record component accessor `id()` đáp ứng method `HasId.id()`. Record không extends một class ứng dụng tùy ý; nó có cơ chế kế thừa riêng nhưng vẫn triển khai interfaces được.

Enums cũng có thể implements interfaces:

~~~java
interface Action {
    String label();
}

enum Direction implements Action {
    NORTH, SOUTH;

    @Override
    public String label() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

Đây là hai đoạn khai báo độc lập để minh họa khả năng implementation. Một enum constant có thể có implementation hành vi riêng thông qua constant-specific class bodies trong những thiết kế phù hợp.

## 33. Ví dụ chạy: record và enum cùng một interface

Tạo **`RecordEnumInterfaceDemo.java`**:

~~~java
public class RecordEnumInterfaceDemo {
    interface Labelled {
        String label();
    }

    record Tag(String label) implements Labelled {}

    enum Priority implements Labelled {
        LOW, HIGH;

        @Override
        public String label() {
            return name().toLowerCase(java.util.Locale.ROOT);
        }
    }

    static void print(Labelled item) {
        System.out.println(item.label());
    }

    public static void main(String[] args) {
        print(new Tag("Java"));
        print(Priority.HIGH);
    }
}
~~~

~~~bash
javac -encoding UTF-8 RecordEnumInterfaceDemo.java
java RecordEnumInterfaceDemo
~~~

Stdout:

~~~text
Java
high
~~~

Cùng contract `Labelled` được một record và một enum implement theo hai cách khác nhau. Interface không ép mọi implementing type phải là “normal class với constructor” hoặc có cùng internal fields.

## 34. Sealed interface trong Java 17

Java 17 hỗ trợ **sealed interfaces**, cho phép giới hạn các types trực tiếp được phép kế thừa/triển khai:

~~~java
sealed interface Result permits Success, Failure {
}

record Success(String value) implements Result {
}

record Failure(String message) implements Result {
}
~~~

Các records final ngầm nên là các permitted direct implementing types hợp lệ. Không phải bất cứ class nào bên ngoài danh sách `permits` cũng được trực tiếp `implements Result`.

### Vì sao dùng sealed interface?

Khi domain có một **tập trường hợp đóng**: kết quả thành công/thất bại, những loại command hoặc shape hợp lệ, sealed giúp giới hạn extensibility.

**Cẩn thận:**

- Permitted subclasses/implementations phải tuân theo quy tắc module/package và `final`, `sealed` hoặc `non-sealed` khi áp dụng.
- Sealed **không làm instances immutable**. Một permitted final class vẫn có thể chứa mutable state.
- Java 17 đã có `instanceof` pattern matching; **pattern matching switch cho sealed types** có trạng thái preview trong Java 17, không dùng như Java 17 code thường nếu không bật flags phù hợp. Để chương trình dễ chạy, dùng `instanceof` pattern.

## 35. Ví dụ chạy: sealed interface và `instanceof`

Tạo **`SealedInterfaceDemo.java`**:

~~~java
public class SealedInterfaceDemo {
    sealed interface Result permits Success, Failure {
    }

    record Success(String value) implements Result {
    }

    record Failure(String message) implements Result {
    }

    static String show(Result result) {
        if (result instanceof Success success) {
            return "OK: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "ERROR: " + failure.message();
        }
        throw new IllegalStateException("unexpected result");
    }

    public static void main(String[] args) {
        System.out.println(show(new Success("saved")));
        System.out.println(show(new Failure("invalid")));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SealedInterfaceDemo.java
java SealedInterfaceDemo
~~~

Stdout:

~~~text
OK: saved
ERROR: invalid
~~~

Sealed Result khai báo rõ hai permitted direct implementations. Phần xử lý kiểu dùng Java 17 `instanceof` patterns, không yêu cầu preview switch feature. Về mặt contract, Result đại diện tập trường hợp có chủ đích, khác interface mở cho plugin implementations tùy ý.

## 36. Những compiler errors thường gặp

| Mã/ý định | Vấn đề | Cách sửa |
| --- | --- | --- |
| `class A implements I` thiếu abstract method | Concrete class chưa hoàn tất contract | Implement method hoặc khai báo class abstract |
| Implementation method package-private | Interface method là public | Ghi `public` |
| Sai tên method | Không override đúng member | Dùng `@Override` và khớp chữ ký |
| Chỉ overload `process(long)` khi interface đòi `process(int)` | Method khác | Implement đúng parameters |
| Return primitive khác | Return type không phù hợp | Dùng return type hợp lệ |
| Thêm `throws Exception` khi interface chỉ cho `IOException` | Checked exception rộng hơn | Thu hẹp/sửa contract |
| `new SomeInterface()` | Interface không có direct instances | Dùng implementation, anonymous class hoặc lambda phù hợp |
| `interface B implements A` | Interface dùng `extends` | Sửa cú pháp |
| `class C extends A, B` với hai classes | Java không multiple class inheritance | Dùng một superclass + interfaces/composition |
| Hai unrelated defaults cùng chữ ký | Ambiguous/conflicting inherited defaults | Override giải quyết rõ |
| Gọi interface static method qua instance | Không được thừa hưởng như instance | Gọi `I.method()` |
| Gán lại interface field | Interface field final | Giữ constant immutable, chuyển state vào class |
| Tưởng interface có instance field | Không có khai báo instance fields trong interface | Lưu state trong implementing class |
| Lambda dùng interface có nhiều abstract methods | Không phải functional interface | Dùng anonymous/concrete class hoặc tách contract |
| `@FunctionalInterface` nhưng không đủ điều kiện | Compiler báo | Đảm bảo single abstract method contract |
| Class không được sealed interface permits | Bị giới hạn hierarchy | Thêm permitted type theo quy tắc hoặc thiết kế lại |
| Gọi method riêng của implementation qua interface reference | Declared type không thấy member | Phụ thuộc contract đúng hoặc checked cast khi có lý do |

Compiler message cụ thể thay đổi theo javac version. Hãy đối chiếu **member đang khai báo ở interface**, **member implementation thực sự**, và **subtype/override rules** thay vì thử sửa tên ngẫu nhiên.

## 37. Anti-pattern: interface rỗng, interface quá rộng và interface cho một class

Không phải interface nào cũng tự tạo architecture tốt.

### Interface quá rộng

~~~java
interface MegaService {
    void sendEmail();
    void generatePdf();
    void chargeCard();
    void renderChart();
}
~~~

Nếu implementation chỉ thực sự làm một việc, nó có thể phải triển khai các methods vô nghĩa và ném `UnsupportedOperationException`, vi phạm kỳ vọng caller.

**Cách cải thiện:** Tách thành các capability interfaces theo use cases và inject chính interface cần dùng.

### Interface chỉ để nhân đôi mọi public method của một class

Nếu một class chỉ có một implementation, không có external boundary/test seam, không có khả năng hoán đổi và hợp đồng không độc lập, interface `FooInterface` chỉ mirror `Foo` có thể tăng số file/coupling không cần thiết.

Không phải “chỉ có một implementation thì luôn sai”. Một payment gateway boundary dù chỉ có một implementation hiện tại vẫn có thể đáng trừu tượng hóa vì đó là **external dependency hoặc stable contract**. Quyết định dựa trên lý do thay thế, testability và kiến trúc, không phải số lượng classes hiện tại.

### Marker interface

Một interface **không có method** như `java.io.Serializable` có thể được dùng để biểu thị một marker contract có semantics đặc biệt của nền tảng/framework. Nhưng với metadata tùy ý, annotations hoặc explicit capabilities thường dễ hiểu hơn; đừng mặc định tạo marker interface cho mọi tính chất.

## 38. Thiết kế hợp đồng tốt theo tình huống

Giả sử thiết kế `Storage`:

~~~java
interface Storage {
    void save(String key, byte[] data);
    byte[] load(String key);
}
~~~

Trước khi viết implementation, hãy quyết định:

- Có cho `key == null` hoặc blank không?
- `load` khi key không tồn tại trả null, Optional hay ném exception?
- `save` có ghi đè key cũ không?
- Có bảo vệ dữ liệu input/output mutable `byte[]` bằng copy không?
- Lỗi I/O biểu diễn checked hay unchecked exception?
- Concurrent readers/writers có được hỗ trợ không?
- `save` xong thì `load` ngay có được dữ liệu giống không?
- Persistence có được bảo đảm qua process restart không?
- Cùng byte array reference được caller sửa sau khi save có thay dữ liệu stored không?

Nếu không xác định các câu hỏi này, hai classes đều `implements Storage` có thể **hành xử rất khác** và không thay thế nhau được trong chương trình.

### Hợp đồng rõ cho phép test chung

Một lựa chọn cụ thể: “`save` giữ snapshot dữ liệu; `load` trả bản sao; key không tồn tại ném `NoSuchElementException`; mọi key nonblank; không có bảo đảm multi-thread.”

Khi ấy MemoryStorage và FileStorage có thể được kiểm thử bằng cùng suite (ngoài các tiêu chí liên quan durability của file implementation).

## 39. Ví dụ đầy đủ: interface Storage với defensive copy

Tạo **`StorageContractDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.NoSuchElementException;

public class StorageContractDemo {
    interface Storage {
        void save(String key, byte[] data);
        byte[] load(String key);
    }

    static final class MemoryStorage implements Storage {
        private final Map<String, byte[]> entries = new HashMap<>();

        private static void checkKey(String key) {
            if (key == null || key.isBlank()) {
                throw new IllegalArgumentException("key required");
            }
        }

        @Override
        public void save(String key, byte[] data) {
            checkKey(key);
            if (data == null) {
                throw new IllegalArgumentException("data required");
            }
            entries.put(key, data.clone());
        }

        @Override
        public byte[] load(String key) {
            checkKey(key);
            byte[] data = entries.get(key);
            if (data == null) {
                throw new NoSuchElementException("missing: " + key);
            }
            return data.clone();
        }
    }

    public static void main(String[] args) {
        Storage storage = new MemoryStorage();
        byte[] input = {1, 2, 3};

        storage.save("A", input);
        input[0] = 9;

        byte[] result = storage.load("A");
        result[1] = 8;

        System.out.println("input=" + Arrays.toString(input));
        System.out.println("result=" + Arrays.toString(result));
        System.out.println("stored=" +
                Arrays.toString(storage.load("A")));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StorageContractDemo.java
java StorageContractDemo
~~~

Stdout:

~~~text
input=[9, 2, 3]
result=[1, 8, 3]
stored=[1, 2, 3]
~~~

Bài này minh họa **ngữ nghĩa hợp đồng vượt qua cú pháp**: `Storage.save/load` thao tác trên mutable `byte[]`. Nếu một implementation giữ nguyên input reference hoặc trả nguyên internal array, người gọi có thể thay dữ liệu lưu trữ sau `save` mà không cần gọi lại `save`, trái chính sách snapshot đã chọn.

Class `MemoryStorage` dùng `clone()` để copy mảng primitive khi nhận và khi trả; tính chất ấy **không tự xuất hiện chỉ vì implements interface**. Với reference arrays hoặc object graphs, clone là shallow copy; cần contract riêng.

## 40. Kế thừa interface và tính ổn định API

Khi phát hành một interface trong thư viện, nhiều classes của người khác có thể đang implement nó. Thêm một **abstract method** mới có thể buộc mọi implementation cập nhật, tạo tác động tương thích.

Thêm `default` method có body đôi khi giúp tiến hóa API ít phá vỡ hơn, nhưng vẫn có thể gây:

- Xung đột với default method interface khác.
- Xung đột/override rules với methods trong class hierarchy.
- Hành vi mặc định không phù hợp semantics của một implementation.
- Vấn đề biên dịch hoặc liên kết khi các phiên bản thư viện và client khác nhau.
- Sự hiểu nhầm nếu default method giả định một invariant không được contract bảo đảm.

### Những nguyên tắc tiến hóa contract

1. Thiết kế các abstract methods ít nhưng đủ biểu đạt capability.
2. Mô tả rõ input, output, exceptions, side effects và concurrency guarantees.
3. Nếu cần thêm capability lớn, cân nhắc **interface mới kế thừa interface cũ** thay vì thay API cũ.
4. Test implementation cũ và mới với contract tests.
5. Tránh expose mutable fields qua interface constants.
6. Cân nhắc backward compatibility ở source và binary levels.

Interface là một **lời hứa ổn định cho callers và implementers**. Thay đổi nó có thể tác động hai nhóm khác nhau.

## 41. Một class có thể có cả method overload và implement interface

Ví dụ:

~~~java
interface Reader {
    String read();
}

class FileReader implements Reader {
    @Override
    public String read() {
        return "all";
    }

    public String read(int limit) {
        return "first " + limit;
    }
}
~~~

`read()` đáp ứng interface Reader. `read(int)` là overload khác, chỉ thấy qua declared type `FileReader` (hoặc một interface khác khai báo signature ấy).

Khi một method bị overload:

~~~java
void show(Readable value) { ... }
void show(Object value) { ... }
~~~

việc chọn overload phụ thuộc vào **compile-time types**, còn implementation của một instance method được override phụ thuộc actual receiver object lúc runtime. Đây là hai cơ chế khác nhau: **overload resolution** và **dynamic dispatch**.

Trong học đa hình, đừng coi việc cùng tên method tự động là override/implement. Chữ ký phải tương thích.

## 42. Bài tập 1 — Interface và hai implementations

Yêu cầu viết interface `Shape`:

~~~java
interface Shape {
    double area();
}
~~~

Tạo `Rectangle` nhận width/height dương, `Circle` nhận radius dương, mỗi class `implements Shape`. Sau đó viết method:

~~~java
static void show(Shape shape) {
    System.out.println(shape.area());
}
~~~

Gọi với hai loại shape khác nhau. Chỉ sử dụng method `area()` trong `show`, không ép kiểu về Rectangle/Circle. Kiểm tra nhập liệu âm hoặc bằng 0.

**Trọng tâm:** Caller làm việc với **capability area**, còn mỗi implementation định nghĩa công thức của nó.

## 43. Bài tập 2 — Tìm lỗi `public`/signature

Cho:

~~~java
interface Report {
    void generate(String format);
}

class PdfReport implements Report {
    // void generate(String format) { ... }
}
~~~

Nếu bỏ comment và viết body, vì sao vẫn lỗi? **Đáp án:** Method interface `generate` là public; method trong class thiếu modifier nên package-private. Sửa thành:

~~~java
@Override
public void generate(String format) {
    System.out.println(format);
}
~~~

Tiếp theo thử đổi tham số thành `Object format`; đó là overload không implement đúng signature `generate(String)`.

## 44. Bài tập 3 — Interface reference và method riêng

~~~java
interface Animal {
    void sound();
}

class Dog implements Animal {
    @Override
    public void sound() {
        System.out.println("woof");
    }

    public void fetch() {
        System.out.println("fetch");
    }
}
~~~

Cho `Animal pet = new Dog();`. Vì sao `pet.sound()` hợp lệ còn `pet.fetch()` không biên dịch?

**Đáp án:** Compile-time type Animal chỉ có `sound()`; runtime Dog object quyết định implementation của sound. `fetch` là method riêng của Dog, không thuộc Animal contract. Chỉ dùng checked cast/`instanceof` nếu use case thật sự cần capability riêng đó.

## 45. Bài tập 4 — Hai interface default trùng tên

Cho `Left` và `Right` cùng có `default String label()`. Viết class `Both implements Left, Right` sao cho `label()` trả `"L+R"`.

**Đáp án gợi ý:**

~~~java
@Override
public String label() {
    return Left.super.label() + "+" + Right.super.label();
}
~~~

Đây là method body đặt trong Both. Bài tập giúp phân biệt multiple interface inheritance với multiple class inheritance và xung đột default implementations.

## 46. Bài tập 5 — Contract test và implementation sai

Cho interface:

~~~java
interface Counter {
    void increment();
    int value();
}
~~~

Hợp đồng: `value()` ban đầu bằng 0; mỗi lần `increment()` thành công làm tăng đúng 1, không thay đổi khi chỉ đọc.

Hãy viết hai implementations: một dùng `int`, một dùng `AtomicInteger`. Viết **một** function `verify(Counter c)` kiểm tra hợp đồng cho cả hai.

**Câu hỏi thêm:** `AtomicInteger` có nghĩa `Counter` contract tự động hứa thread-safe không? **Không.** Nếu muốn mọi implementations đều thread-safe, phải mô tả điều đó trong contract và kiểm thử concurrency riêng.

## 47. Bài tập 6 — Thiết kế interface theo capability

Một hệ thống có email sender, PDF printer, audit logger, payment processor. Hãy cân nhắc:

**Phương án A:** Một interface `EverythingService` với bốn methods khiến mọi class phải implement tất cả.

**Phương án B:** `Notifier`, `Printable`, `AuditSink`, `PaymentGateway` theo những khả năng rõ ràng.

**Đáp án:** Phương án B thường phù hợp hơn khi caller chỉ cần một capability và implementations có trách nhiệm riêng. Nhưng số interfaces cần phản ánh boundaries thật; không chia thành hàng chục abstractions vô nghĩa chỉ để tuân theo mẫu.

## 48. Bài tập 7 — Record implements interface

Cho:

~~~java
interface HasCode {
    String code();
}
~~~

Viết:

~~~java
record Product(String code, long price) implements HasCode {
}
~~~

Giải thích vì sao record `Product` có thể đáp ứng `code()` dù không viết method này: **record component accessor `code()`** được sinh phù hợp chữ ký method public trong interface.

Bài mở rộng: thêm compact constructor kiểm tra `code` nonblank và `price >= 0`. Nhớ compile-time contract không tự kiểm tra invariant giá/ID.

## 49. Bài tập 8 — Đọc lỗi sealed interface

Cho sealed interface `Result` chỉ `permits Success, Failure`. Tại sao một class `Pending implements Result` không có trong permits có thể bị compiler từ chối?

**Đáp án:** `sealed` định nghĩa các permitted **direct** subclasses/implementations theo quy tắc Java 17. Muốn mở trường hợp Pending phải điều chỉnh hierarchy/permits và tuân theo yêu cầu `final`/`sealed`/`non-sealed` cho permitted declarations. Cân nhắc thay đổi này có phá contract của callers đang giả định chỉ có Success/Failure hay không.

## 50. Bài tập 9 — Phân biệt hợp đồng cú pháp và ngữ nghĩa

Một interface:

~~~java
interface MoneyTransfer {
    void transfer(long amount);
}
~~~

Một class implements method nhưng trừ tiền trước rồi báo lỗi nếu số dư âm.

**Câu hỏi:** Vì sao compiler vẫn có thể chấp nhận class? Vì sao implementation có thể sai?

**Đáp án:** Signature tương thích, nhưng operation có thể phá invariant “số dư không âm” và “giao dịch thất bại không làm mất tiền”. Hãy định nghĩa preconditions, postconditions và failure behavior; validate toàn bộ điều kiện trước khi cập nhật hoặc dùng transaction thích hợp. Contract có ích khi được **kiểm tra bằng cả code và tests**, không chỉ chữ ký.

## 51. Câu hỏi thường gặp

### 51.1. Interface có tạo object được không?

Không instantiate trực tiếp một interface như concrete class. Nhưng một variable interface type có thể tham chiếu instance của implementing class, anonymous class hoặc object được tạo từ lambda khi target là functional interface.

### 51.2. Class implements hai interfaces có hai objects không?

Không. Một class instance có thể được nhìn qua nhiều interface types, nhưng đó là **một runtime object**.

### 51.3. Interface có constructor hoặc instance state không?

Không có constructor hoặc instance fields theo cách class có. Fields được khai báo trong interface là public static final; per-instance state phải do implementing class quản lý.

### 51.4. Nếu class không implements hết methods?

Class concrete không biên dịch nếu còn abstract method bắt buộc chưa được thực hiện/thừa hưởng implementation phù hợp. Có thể khai báo class `abstract` để subclasses hoàn tất.

### 51.5. Interface method có bắt buộc `public` khi implement?

Đối với abstract interface methods public, implementation phải có quyền truy cập public (hoặc một inherited public method hợp lệ). Dùng `@Override` và khai báo `public` để tránh lỗi.

### 51.6. Tại sao method khác return type lại không implement được?

Override cần return-type compatibility; reference types có thể covariant trong các trường hợp phù hợp, nhưng không tự đổi primitive return type tùy ý.

### 51.7. `default` method có phải lúc nào cũng chạy?

Không. Một class có thể override nó; một concrete superclass method phù hợp có thể được ưu tiên; các xung đột giữa unrelated defaults có thể yêu cầu explicit override.

### 51.8. Interface static method có được kế thừa bởi class không?

Không theo cách instance methods/default methods được thừa hưởng. Thông thường gọi `InterfaceName.staticMethod()`.

### 51.9. Có nên interface cho mọi class?

Không. Ưu tiên interface khi có capability/contract hữu ích, nhu cầu polymorphism, test seam hoặc stable dependency boundary rõ. Một interface mirror duy nhất không có vai trò riêng có thể làm dự án phức tạp hơn.

### 51.10. `implements` và `extends` có khác nhau trong runtime dispatch không?

Class triển khai interface và class kế thừa/override instance method đều có thể tham gia runtime polymorphism; nhưng hierarchy rules, method inheritance và state sharing khác nhau. `implements` không biến class thành subclass trực tiếp của một implementation class.

### 51.11. Có thể dùng lambda thay class implements không?

Chỉ khi target interface là **functional interface** và body lambda đáp ứng abstract method contract. Không dùng lambda để instantiate một interface với nhiều abstract operations khác nhau.

### 51.12. Interface đảm bảo thread safety không?

Không. Thread safety phải được contract quy định rõ và mọi implementations liên quan phải đáp ứng bằng immutable state, synchronization, atomic operations hoặc ownership phù hợp.

## 52. Checklist cuối bài

- [ ] Tôi giải thích được interface là một reference type và behavioral contract.
- [ ] Tôi biết `implements` trong class và `extends` trong interface.
- [ ] Tôi phân biệt compile-time method availability và runtime method dispatch.
- [ ] Tôi biết class concrete phải implement abstract methods cần thiết.
- [ ] Tôi dùng `@Override` và `public` đúng khi triển khai.
- [ ] Tôi nhận diện overload không phải override/implement.
- [ ] Tôi hiểu covariant reference returns và checked exceptions constraints.
- [ ] Tôi có thể dùng một interface reference cho nhiều implementations.
- [ ] Tôi biết một class implements nhiều interfaces nhưng extends tối đa một superclass.
- [ ] Tôi hiểu interface fields là public static final, không phải per-instance state.
- [ ] Tôi dùng `default` method và biết khi nào bị override.
- [ ] Tôi gọi `static` method qua tên interface.
- [ ] Tôi hiểu `private` helper methods trong interface Java 17.
- [ ] Tôi giải quyết được xung đột hai default methods.
- [ ] Tôi hiểu superclass concrete method có thể được ưu tiên so với default.
- [ ] Tôi phân biệt abstract class và interface khi chọn architecture.
- [ ] Tôi biết functional interface và viết lambda đúng target type.
- [ ] Tôi hiểu generic interface và vì sao `List<Concrete>` không tự là `List<Interface>`.
- [ ] Tôi có thể dùng record/enum implements một interface.
- [ ] Tôi hiểu sealed interface và giới hạn direct implementations ở Java 17.
- [ ] Tôi biết compiler kiểm tra chữ ký, không tự chứng minh behavioral correctness.
- [ ] Tôi viết được preconditions, postconditions, invariants và error behavior.
- [ ] Tôi hiểu substitutability của nhiều implementations theo cùng một contract.
- [ ] Tôi viết được contract test dùng chung cho hai implementations.
- [ ] Tôi dùng constructor injection qua interface khi có boundary cần hoán đổi.
- [ ] Tôi biết lợi ích và rủi ro của thêm method vào public library interface.
- [ ] Tôi không tạo interface quá rộng hoặc abstraction không có lý do rõ.
- [ ] Tôi chạy được các ví dụ Java 17+ kèm stdout đúng như bài.

**Kết luận:** `implements` không chỉ là cú pháp để class được coi là subtype của một interface. Nó là tuyên bố class cung cấp **những khả năng mà caller có quyền kỳ vọng**. Interface giúp tách **“cần làm gì”** khỏi **“làm bằng cách nào”**, tạo nền tảng cho đa hình, dependency injection, contract tests và thiết kế module ít phụ thuộc. Tuy nhiên, một chữ ký hợp lệ chưa bảo đảm đúng nghiệp vụ: **tính thay thế được giữa các implementations phụ thuộc vào việc mọi class cùng tôn trọng hợp đồng ngữ nghĩa**, xử lý lỗi, invariant và giới hạn đã công bố.
