# Enum hiện thực interface trong Java 17+

Một **enum trong Java là một kiểu class đặc biệt**, có tập hằng số cố định và có thể **`implements` một hoặc nhiều interface**. Nhờ đó, mỗi enum constant không chỉ là một giá trị tượng trưng mà còn có thể cung cấp **hành vi đa hình** theo cùng một hợp đồng (*contract*).

Cú pháp cơ bản:

~~~java
interface Describable {
    String description();
}

enum Status implements Describable {
    NEW, ACTIVE, DONE;

    @Override
    public String description() {
        return "Status: " + name();
    }
}
~~~

`Status` hiện thực `Describable`: tất cả ba constants đều dùng implementation chung của `description()`. Khi cần hành vi khác nhau cho từng constant, có thể dùng **constant-specific class body**:

~~~java
interface BinaryOperation {
    int apply(int left, int right);
}

enum Operation implements BinaryOperation {
    ADD {
        @Override
        public int apply(int left, int right) {
            return left + right;
        }
    },
    MULTIPLY {
        @Override
        public int apply(int left, int right) {
            return left * right;
        }
    }
}
~~~

`Operation.ADD` và `Operation.MULTIPLY` đều là `BinaryOperation`, nhưng `apply` được dispatch theo constant cụ thể.

Bài thuộc **Java Core — Class & Object / Enum**, áp dụng **Java 17+**. Mọi ví dụ chạy độc lập ghi rõ tên file, lệnh `javac`/`java` và stdout; snippets không đầy đủ được nêu là minh họa. Trọng tâm duy nhất là **enum hiện thực interface**, đồng thời làm rõ các quan hệ enum, class body, generic interface, default methods và thiết kế ứng dụng.

## 1. Mục tiêu bài học

Bạn sẽ học cách:

- Viết `enum E implements Contract` đúng cú pháp Java.
- Hiểu interface contract và các yêu cầu override/visibility.
- Phân biệt một implementation chung trong enum body với implementation riêng trong từng constant.
- Dùng enum value thông qua biến kiểu interface và hiểu dynamic dispatch.
- Dùng `@Override` để compiler kiểm tra signature.
- Hiểu enum có thể implements **nhiều interfaces**, nhưng không extends class do bạn chọn.
- Dùng interface default/static methods và giải quyết default-method conflicts.
- Áp dụng generic interfaces như `Function<String,String>`, `Comparator<String>` và `Predicate<String>`.
- Xây dựng strategy, policy, command, state-dependent behavior bằng enum.
- Hiểu enum constructors, instance fields và constant-specific class bodies kết hợp với interface thế nào.
- Phân biệt enum abstract method và interface abstract method.
- Chọn giữa enum implementation, named class, anonymous class và lambda.
- Sử dụng `values()`, `valueOf`, `EnumSet`, `EnumMap` khi enum cũng là interface implementation.
- Hiểu `name()`, `ordinal()`, `getDeclaringClass()` và runtime class của constant-specific bodies.
- Đánh giá identity, immutability, shared mutable state và thread safety.
- Đọc các lỗi compiler thường gặp, checked exceptions và generic type restrictions.
- Thiết kế API trả interface nhưng vẫn cho code cần finite domain dùng enum trực tiếp.
- Kiểm thử từng constant theo interface contract và dự đoán output.

## 2. Enum là class đặc biệt, không chỉ là hằng số int

~~~java
enum Priority {
    LOW, MEDIUM, HIGH
}
~~~

Mỗi `Priority.LOW` là một enum constant object. Java tự cung cấp các cơ chế như:

- Các constants được khai báo theo thứ tự cố định.
- `Priority.values()` trả array chứa toàn bộ constants theo declaration order.
- `Priority.valueOf("LOW")` tìm constant theo tên chính xác.
- `name()` trả tên khai báo, như `"LOW"`.
- `ordinal()` trả vị trí 0-based trong declaration order.
- Các enum objects có unique identity trong mỗi declaring enum type.
- Mỗi enum type implicitly extends `java.lang.Enum<E>`.

Dù enum tự có đặc điểm đặc biệt, nó vẫn có thể khai báo fields, methods, constructors (không public/protected), override methods hợp lệ, và **implements interfaces** như class khác.

Không được tự `new Priority()` từ client; các enum constants là những instances do enum declaration xác định.

## 3. Interface contract là gì?

Một interface định nghĩa những operations mà implementing types phải cung cấp.

~~~java
interface Label {
    String text();
}
~~~

Một enum implement contract:

~~~java
enum Stage implements Label {
    START, FINISH;

    @Override
    public String text() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

`Stage` có hai constants, nhưng code dùng `Label` không cần biết chúng thuộc enum hay named class:

~~~java
Label label = Stage.START;
String text = label.text();
~~~

**Điểm mạnh:** Caller phụ thuộc vào interface `Label`, không cần tự kiểm tra `if (stage == Stage.START)` trong mọi method.

**Giới hạn:** Contract interface không tự có `values()`, `name()` hoặc `ordinal()`. Những operations là từ enum/Enum, không phải từ mọi implementation của interface.

## 4. Chương trình chạy: enum implement một interface

Tạo file **`EnumInterfaceBasicsDemo.java`**:

~~~java
public class EnumInterfaceBasicsDemo {
    interface Label {
        String text();
    }

    enum Stage implements Label {
        START, FINISH;

        @Override
        public String text() {
            return name().toLowerCase(java.util.Locale.ROOT);
        }
    }

    static void print(Label label) {
        System.out.println("label=" + label.text());
    }

    public static void main(String[] args) {
        print(Stage.START);
        print(Stage.FINISH);

        Label current = Stage.START;
        System.out.println("same object=" +
                (current == Stage.START));
        System.out.println("enum name=" + Stage.START.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumInterfaceBasicsDemo.java
java EnumInterfaceBasicsDemo
~~~

Stdout:

~~~text
label=start
label=finish
same object=true
enum name=START
~~~

`print(Label)` nhận bất cứ implementation nào của Label. Khi truyền Stage.START, method vẫn gọi behavior từ enum Stage qua interface reference.

## 5. Cú pháp khai báo: `implements` đặt sau tên enum

Cấu trúc:

~~~java
enum EnumName implements InterfaceA, InterfaceB {
    FIRST, SECOND;

    // fields, constructors, methods...
}
~~~

Phần `implements` nằm **trước dấu `{`**. Các constants được liệt kê đầu tiên; nếu enum còn members (fields, constructors, methods), dùng dấu `;` để phân cách sau danh sách constants.

Ví dụ:

~~~java
interface Coded {
    int code();
}

enum HttpState implements Coded {
    OK(200), NOT_FOUND(404);

    private final int code;

    HttpState(int code) {
        this.code = code;
    }

    @Override
    public int code() {
        return code;
    }
}
~~~

Constructor `HttpState(int)` được gọi khi constants `OK(200)` và `NOT_FOUND(404)` được khởi tạo. Không được khai báo enum constructor `public` hoặc `protected`. Client cũng không thể `new HttpState(200)`.

## 6. Chương trình chạy: enum constructor và interface

Tạo **`EnumConstructorInterfaceDemo.java`**:

~~~java
public class EnumConstructorInterfaceDemo {
    interface Coded {
        int code();
    }

    enum HttpState implements Coded {
        OK(200), NOT_FOUND(404);

        private final int statusCode;

        HttpState(int statusCode) {
            this.statusCode = statusCode;
        }

        @Override
        public int code() {
            return statusCode;
        }
    }

    public static void main(String[] args) {
        Coded success = HttpState.OK;
        Coded failure = HttpState.NOT_FOUND;

        System.out.println(success.code());
        System.out.println(failure.code());

        for (HttpState state : HttpState.values()) {
            System.out.println(state.name() + "=" + state.code());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumConstructorInterfaceDemo.java
java EnumConstructorInterfaceDemo
~~~

Stdout:

~~~text
200
404
OK=200
NOT_FOUND=404
~~~

Các interface methods được implement bởi cùng class enum nhưng đọc **field riêng của mỗi constant**.

## 7. Vì sao cần `public` khi implement interface method?

Methods abstract bình thường trong interface là `public` (và abstract, trừ các trường hợp đặc biệt của interface). Vì vậy implementing enum method phải có ít nhất `public` accessibility:

~~~java
interface Action {
    void run();
}

enum Job implements Action {
    BUILD;

    @Override
    public void run() {
        System.out.println("building");
    }
}
~~~

Không thể giảm accessibility:

~~~java
// enum Invalid implements Action {
//     BUILD;
//     @Override
//     void run() {} // Compile error: giảm visibility của public Action.run().
// }
~~~

Luôn thêm `@Override` cho implementation để compiler phát hiện sai tên/signature hoặc return type không tương thích.

## 8. Implementation chung: mọi constant dùng một method

Nếu hành vi giống nhau ngoại trừ dữ liệu, đặt implementation vào **enum body**:

~~~java
interface Displayable {
    String display();
}

enum Role implements Displayable {
    READER("read"), WRITER("write");

    private final String label;

    Role(String label) {
        this.label = label;
    }

    @Override
    public String display() {
        return "[" + label + "]";
    }
}
~~~

Không cần constant-specific bodies cho READER và WRITER. Mỗi instance có field label khác nhau; method `display()` được định nghĩa **một lần**.

**Ưu tiên cách này khi behavior chủ yếu là dữ liệu + một công thức chung.** Nếu mỗi constant có thuật toán khác nhau, constant-specific overriding phù hợp hơn.

## 9. Chương trình chạy: shared implementation đọc field

Tạo **`SharedImplementationDemo.java`**:

~~~java
public class SharedImplementationDemo {
    interface Displayable {
        String display();
    }

    enum Role implements Displayable {
        READER("read"), WRITER("write");

        private final String label;

        Role(String label) {
            this.label = label;
        }

        @Override
        public String display() {
            return "[" + label + "]";
        }
    }

    public static void main(String[] args) {
        for (Role role : Role.values()) {
            Displayable value = role;
            System.out.println(value.display());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SharedImplementationDemo.java
java SharedImplementationDemo
~~~

Stdout:

~~~text
[read]
[write]
~~~

Mỗi constant là Displayable. Interface call chọn `Role.display` và method này đọc field label tương ứng.

## 10. Constant-specific class body: mỗi constant một thuật toán

Cú pháp:

~~~java
enum Operator implements IntOperation {
    ADD {
        @Override
        public int apply(int x, int y) {
            return x + y;
        }
    },
    MULTIPLY {
        @Override
        public int apply(int x, int y) {
            return x * y;
        }
    };
}
~~~

Các dấu `{ ... }` sau mỗi constant tạo **constant-specific class body**. Về mặt type semantics, constants có class bodies thuộc các anonymous subclasses chuyên biệt của enum type và có thể override instance methods.

Đây **không phải** anonymous class được tạo bởi cú pháp `new Interface() { ... }` thông thường. Bạn vẫn đang khai báo **các enum constants**, không được tạo enum instances tùy ý bằng `new`.

### Khi nào dùng?

- Mỗi enum value có một strategy khác nhau.
- Mỗi constant phải hoàn thành một abstract behavior contract.
- Số strategy là tập hữu hạn, đã biết lúc compile.
- Muốn tránh chuỗi `switch` lặp lại ở nhiều nơi.

## 11. Chương trình chạy: toán tử đa hình

Tạo **`EnumOperationDemo.java`**:

~~~java
public class EnumOperationDemo {
    interface IntOperation {
        int apply(int left, int right);
    }

    enum Operation implements IntOperation {
        ADD {
            @Override
            public int apply(int left, int right) {
                return left + right;
            }
        },
        MULTIPLY {
            @Override
            public int apply(int left, int right) {
                return left * right;
            }
        };
    }

    static int calculate(IntOperation operation,
                         int left, int right) {
        return operation.apply(left, right);
    }

    public static void main(String[] args) {
        System.out.println("add=" +
                calculate(Operation.ADD, 3, 4));
        System.out.println("multiply=" +
                calculate(Operation.MULTIPLY, 3, 4));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumOperationDemo.java
java EnumOperationDemo
~~~

Stdout:

~~~text
add=7
multiply=12
~~~

Caller `calculate(IntOperation)` không cần biết enum constant cụ thể, cũng không cần `switch`; dispatch xảy ra theo actual operation instance.

## 12. Abstract method trong enum kết hợp interface

Enum có thể tự khai báo abstract instance method, yêu cầu constant-specific class bodies cung cấp implementation:

~~~java
interface TextProvider {
    String text();
}

enum Message implements TextProvider {
    HELLO {
        @Override
        public String text() {
            return "Hello";
        }
    },
    GOODBYE {
        @Override
        public String text() {
            return "Goodbye";
        }
    };

    @Override
    public abstract String text();
}
~~~

Ở đây `text()` là method trong interface và cũng được enum khai báo abstract. Mỗi constant-specific subclass phải implement method.

**Không bắt buộc** lặp lại abstract method ở enum body nếu từng constant đã cung cấp implementation hợp lệ cho interface contract. Nhưng khai báo abstract ở enum body có thể làm **quy tắc “mỗi constant phải tự triển khai”** nổi bật và được compiler kiểm tra.

### Compiler đảm bảo tính đầy đủ

Nếu thêm constant `UNKNOWN` mà không có body implement `text()`, compile sẽ fail vì concrete enum constant không đáp ứng abstract requirement.

## 13. Chương trình chạy: abstract enum method

Tạo **`AbstractEnumMethodDemo.java`**:

~~~java
public class AbstractEnumMethodDemo {
    interface TextProvider {
        String text();
    }

    enum Message implements TextProvider {
        HELLO {
            @Override
            public String text() {
                return "Hello";
            }
        },
        GOODBYE {
            @Override
            public String text() {
                return "Goodbye";
            }
        };

        @Override
        public abstract String text();
    }

    public static void main(String[] args) {
        for (Message message : Message.values()) {
            System.out.println(message.text());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AbstractEnumMethodDemo.java
java AbstractEnumMethodDemo
~~~

Stdout:

~~~text
Hello
Goodbye
~~~

Một constant mới không implement abstract method sẽ bị javac phát hiện trước khi chạy chương trình.

## 14. Kết hợp shared implementation với override riêng

Không phải mọi constant đều cần class body. Enum có thể cung cấp một method chung, rồi chỉ một số constants override:

~~~java
interface Description {
    String describe();
}

enum Mode implements Description {
    NORMAL,
    SILENT {
        @Override
        public String describe() {
            return "No output";
        }
    };

    @Override
    public String describe() {
        return "Normal output";
    }
}
~~~

`Mode.NORMAL.describe()` dùng implementation chung. `Mode.SILENT.describe()` dispatch vào override của constant-specific class body.

Điều này phù hợp khi đa số enum constants dùng behavior mặc định và một vài constants có ngoại lệ thật sự.

## 15. Chương trình chạy: default trong enum body, override riêng

Tạo **`EnumOverrideFallbackDemo.java`**:

~~~java
public class EnumOverrideFallbackDemo {
    interface Description {
        String describe();
    }

    enum Mode implements Description {
        NORMAL,
        SILENT {
            @Override
            public String describe() {
                return "No output";
            }
        };

        @Override
        public String describe() {
            return "Normal output";
        }
    }

    public static void main(String[] args) {
        for (Mode mode : Mode.values()) {
            Description behavior = mode;
            System.out.println(mode.name() + ":" +
                    behavior.describe());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumOverrideFallbackDemo.java
java EnumOverrideFallbackDemo
~~~

Stdout:

~~~text
NORMAL:Normal output
SILENT:No output
~~~

Caller thấy cùng method `Description.describe`. Dispatch dựa vào actual enum constant/class behavior.

## 16. Interface-typed reference và giới hạn member access

~~~java
interface Action {
    void execute();
}

enum Task implements Action {
    BUILD;

    @Override
    public void execute() {
        System.out.println("build");
    }
}
~~~

Khi viết:

~~~java
Action action = Task.BUILD;
action.execute();
~~~

Compile hợp lệ. Nhưng:

~~~java
// action.name();  // Compile error: Action không có name().
~~~

Dù runtime object là Task enum constant, **declared type** Action quyết định methods accessible qua reference.

Nếu business code cần tên enum, nên:
- giữ biến kiểu `Task` ở boundary nơi finite enum domain quan trọng;
- hoặc thêm một method như `code()` vào contract Action nếu mọi implementations cần cung cấp code;
- hoặc kiểm tra type rõ ràng ở boundary có lý do, không lạm dụng cast trong core logic.

## 17. Chương trình chạy: interface reference không đánh mất enum identity

Tạo **`InterfaceReferenceDemo.java`**:

~~~java
public class InterfaceReferenceDemo {
    interface Action {
        String execute();
    }

    enum Task implements Action {
        BUILD, TEST;

        @Override
        public String execute() {
            return "run:" + name().toLowerCase(
                    java.util.Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        Action action = Task.BUILD;

        System.out.println(action.execute());
        System.out.println("same instance=" +
                (action == Task.BUILD));

        Task original = Task.valueOf("TEST");
        System.out.println(original.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceReferenceDemo.java
java InterfaceReferenceDemo
~~~

Stdout:

~~~text
run:build
same instance=true
TEST
~~~

Reference kiểu Action không tạo một wrapper/copy object. Nó giữ reference tới chính singleton-like enum constant Task.BUILD.

## 18. Một enum có thể implements nhiều interfaces

Java cho phép:

~~~java
enum Command implements Runnable, Describable {
    START;

    @Override
    public void run() {
        System.out.println("start");
    }

    @Override
    public String description() {
        return "Start command";
    }
}
~~~

Các interfaces phải nằm trong comma-separated list sau `implements` và mọi abstract methods phải được đáp ứng.

**Nhưng enum không thể đồng thời extends thêm một class tùy ý**, vì enum implicitly extends `Enum<Command>`. Dùng interfaces để chia nhỏ hợp đồng về hành vi.

## 19. Chương trình chạy: hai interfaces

Tạo **`EnumMultipleInterfacesDemo.java`**:

~~~java
public class EnumMultipleInterfacesDemo {
    interface Describable {
        String description();
    }

    enum Command implements Runnable, Describable {
        START, STOP;

        @Override
        public void run() {
            System.out.println("run:" + name());
        }

        @Override
        public String description() {
            return "Command " + name();
        }
    }

    public static void main(String[] args) {
        Runnable runnable = Command.START;
        Describable info = Command.START;

        runnable.run();
        System.out.println(info.description());
        System.out.println("same constant=" +
                (runnable == info));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumMultipleInterfacesDemo.java
java EnumMultipleInterfacesDemo
~~~

Stdout:

~~~text
run:START
Command START
same constant=true
~~~

Một enum instance có thể được nhìn qua nhiều interface references; vẫn là cùng một object.

## 20. Interface default method: enum được thừa hưởng implementation

Một interface có thể cung cấp default method:

~~~java
interface Described {
    String code();

    default String display() {
        return "[" + code() + "]";
    }
}
~~~

Enum chỉ cần implement `code()` nếu không muốn override `display()`:

~~~java
enum Level implements Described {
    LOW, HIGH;

    @Override
    public String code() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}
~~~

`Level.LOW.display()` được phép và trả `[low]`. Default method giúp thêm shared behavior cho mọi implementations của Described mà không cần lặp logic.

### Không nhầm default với abstract

Default method đã có body, nên không bắt buộc override trong enum. Abstract interface method không có implementation tương thích thì enum phải tự triển khai.

## 21. Chương trình chạy: default method từ interface

Tạo **`EnumDefaultMethodDemo.java`**:

~~~java
public class EnumDefaultMethodDemo {
    interface Described {
        String code();

        default String display() {
            return "[" + code() + "]";
        }
    }

    enum Level implements Described {
        LOW, HIGH;

        @Override
        public String code() {
            return name().toLowerCase(
                    java.util.Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        Described first = Level.LOW;
        Described second = Level.HIGH;

        System.out.println(first.display());
        System.out.println(second.display());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumDefaultMethodDemo.java
java EnumDefaultMethodDemo
~~~

Stdout:

~~~text
[low]
[high]
~~~

Default dispatch vẫn là ordinary polymorphism: default method `display` gọi `code` do actual implementation cung cấp.

## 22. Hai interfaces có default method trùng signature

Xét:

~~~java
interface ShortLabel {
    default String label() {
        return "short";
    }
}

interface LongLabel {
    default String label() {
        return "long";
    }
}
~~~

Nếu enum implements cả hai, Java không thể tự chọn một trong hai default methods không quan hệ. Enum phải **override method** để giải quyết conflict:

~~~java
enum DisplayMode implements ShortLabel, LongLabel {
    COMPACT;

    @Override
    public String label() {
        return ShortLabel.super.label() + "/" +
                LongLabel.super.label();
    }
}
~~~

`ShortLabel.super.label()` và `LongLabel.super.label()` là **interface-qualified super invocation**; cú pháp này khác `Enum.super` và chỉ dùng khi hợp lệ theo rules.

## 23. Chương trình chạy: giải quyết default-method conflict

Tạo **`DefaultConflictDemo.java`**:

~~~java
public class DefaultConflictDemo {
    interface ShortLabel {
        default String label() {
            return "short";
        }
    }

    interface LongLabel {
        default String label() {
            return "long";
        }
    }

    enum Mode implements ShortLabel, LongLabel {
        COMPACT;

        @Override
        public String label() {
            return ShortLabel.super.label() + "/" +
                    LongLabel.super.label();
        }
    }

    public static void main(String[] args) {
        System.out.println(Mode.COMPACT.label());
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefaultConflictDemo.java
java DefaultConflictDemo
~~~

Stdout:

~~~text
short/long
~~~

Nếu bỏ override trong Mode, declaration sẽ không biên dịch vì conflict giữa hai inherited defaults. Chọn một behavior rõ ràng hoặc kết hợp có chủ đích.

## 24. Static method của interface không trở thành enum static method

Ví dụ:

~~~java
interface Codes {
    static String normalize(String text) {
        return text.strip().toUpperCase(
                java.util.Locale.ROOT);
    }
}
~~~

Dù `Mode implements Codes`, client dùng:

~~~java
String code = Codes.normalize(" low ");
~~~

Không nên viết `Mode.normalize(" low ")` và giả định inherited static interface method: **static methods của interface không được kế thừa theo cách instance/default methods được kế thừa**.

Nếu cần utility này trong enum implementation, gọi chính tên interface `Codes.normalize(...)` hoặc tổ chức một helper phù hợp.

## 25. Chương trình chạy: interface static utility

Tạo **`InterfaceStaticUtilityDemo.java`**:

~~~java
public class InterfaceStaticUtilityDemo {
    interface Codes {
        static String normalize(String value) {
            return value.strip().toUpperCase(
                    java.util.Locale.ROOT);
        }
    }

    enum Mode implements Codes {
        LOW, HIGH;

        String normalized() {
            return Codes.normalize(name());
        }
    }

    public static void main(String[] args) {
        System.out.println(Codes.normalize(" low "));
        System.out.println(Mode.HIGH.normalized());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceStaticUtilityDemo.java
java InterfaceStaticUtilityDemo
~~~

Stdout:

~~~text
LOW
HIGH
~~~

`Codes.normalize` là interface static method. `Mode.HIGH.normalized` là enum instance method của Mode.

## 26. Generic interface: enum có thể cố định type arguments

Enum declaration không tự nhận generic type parameters như một generic class declaration `class Box<T>`. Nhưng enum có thể implement **parameterized interface**:

~~~java
enum TextTransform
        implements java.util.function.Function<String, String> {
    TRIM {
        @Override
        public String apply(String value) {
            return value.strip();
        }
    },
    UPPER {
        @Override
        public String apply(String value) {
            return value.toUpperCase(
                    java.util.Locale.ROOT);
        }
    };
}
~~~

Mọi constants của TextTransform là `Function<String,String>`. Khi truyền một constant vào code đòi Function, compiler kiểm tra input/output types.

### Không suy ra “mỗi constant có generic type parameter riêng”

Một enum type không thể trở thành `TextTransform<T>` với từng constant có T khác tùy ý. Muốn nhiều heterogeneous behaviors với type parameters khác, có thể cần named generic strategy classes/factories hoặc những enums riêng.

## 27. Chương trình chạy: enum implement Function

Tạo **`EnumFunctionDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.function.Function;

public class EnumFunctionDemo {
    enum TextTransform implements Function<String, String> {
        TRIM {
            @Override
            public String apply(String value) {
                return value.strip();
            }
        },
        UPPER {
            @Override
            public String apply(String value) {
                return value.toUpperCase(Locale.ROOT);
            }
        };
    }

    public static void main(String[] args) {
        List<String> source = List.of(" java ", " core ");

        Function<String, String> transform =
                TextTransform.TRIM;

        System.out.println(source.stream()
                .map(transform)
                .toList());

        System.out.println(source.stream()
                .map(TextTransform.UPPER)
                .toList());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EnumFunctionDemo.java
java EnumFunctionDemo
~~~

Stdout:

~~~text
[java, core]
[ JAVA ,  CORE ]
~~~

Stream.map chấp nhận Function; enum constants là implementations. `toList()` được hỗ trợ ở Java 16+, phù hợp Java 17.

## 28. Enum implement Comparator<T>

Một enum có thể cung cấp các chiến lược sắp xếp hữu hạn qua `Comparator<String>`:

~~~java
enum SortMode implements java.util.Comparator<String> {
    LENGTH {
        @Override
        public int compare(String a, String b) {
            return Integer.compare(a.length(), b.length());
        }
    },
    ALPHABETICAL {
        @Override
        public int compare(String a, String b) {
            return a.compareTo(b);
        }
    };
}
~~~

Comparator chỉ yêu cầu `compare` như SAM (cùng các default/helpers), nên lambda cũng là một lựa chọn. Enum phù hợp khi tên chiến lược (`LENGTH`, `ALPHABETICAL`) là các lựa chọn được chia sẻ và có domain identity ổn định.

### Nguyên tắc comparator

Comparator phải nhất quán với các yêu cầu như antisymmetry, transitivity và khả năng xử lý input hợp lệ. Với integer quantities, dùng `Integer.compare` thay vì `a.length()-b.length()` trong code tổng quát để tránh pattern subtraction dễ gây overflow.

## 29. Chương trình chạy: hai comparator constants

Tạo **`EnumComparatorDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class EnumComparatorDemo {
    enum SortMode implements Comparator<String> {
        LENGTH {
            @Override
            public int compare(String a, String b) {
                return Integer.compare(a.length(), b.length());
            }
        },
        ALPHABETICAL {
            @Override
            public int compare(String a, String b) {
                return a.compareTo(b);
            }
        };
    }

    public static void main(String[] args) {
        List<String> words = new ArrayList<>(
                List.of("pear", "kiwi", "apple", "fig"));

        words.sort(SortMode.LENGTH);
        System.out.println("length=" + words);

        words.sort(SortMode.ALPHABETICAL);
        System.out.println("alphabetical=" + words);
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumComparatorDemo.java
java EnumComparatorDemo
~~~

Stdout:

~~~text
length=[fig, pear, kiwi, apple]
alphabetical=[apple, fig, kiwi, pear]
~~~

`List.sort` là stable sort: hai words dài 4 giữ thứ tự tương đối pear trước kiwi sau length sort. SortMode đồng thời là enum constants và Comparator implementations.

## 30. Enum implement Predicate<T>

`Predicate<String>` có abstract method `boolean test(String)`. Enum constants có thể cung cấp rule khác nhau:

~~~java
enum TextRule implements java.util.function.Predicate<String> {
    NON_BLANK {
        @Override
        public boolean test(String value) {
            return value != null && !value.isBlank();
        }
    },
    STARTS_WITH_J {
        @Override
        public boolean test(String value) {
            return value != null && value.startsWith("J");
        }
    };
}
~~~

Đây là một ví dụ **Strategy pattern với enum**: cùng interface cho nhiều rules hữu hạn.

### Khi nào không dùng enum?

Nếu rule phụ thuộc configuration từng request/user và có hàng nghìn biến thể runtime, tạo class/factory nhận constructor parameters có thể tự nhiên hơn enum constants cố định. Enum constants không phải nơi tạo một object mới cho mỗi input request.

## 31. Chương trình chạy: Predicate strategy

Tạo **`EnumPredicateDemo.java`**:

~~~java
import java.util.function.Predicate;

public class EnumPredicateDemo {
    enum TextRule implements Predicate<String> {
        NON_BLANK {
            @Override
            public boolean test(String value) {
                return value != null && !value.isBlank();
            }
        },
        STARTS_WITH_J {
            @Override
            public boolean test(String value) {
                return value != null && value.startsWith("J");
            }
        };
    }

    static boolean accepts(Predicate<String> rule,
                           String text) {
        return rule.test(text);
    }

    public static void main(String[] args) {
        System.out.println(accepts(TextRule.NON_BLANK, "Java"));
        System.out.println(accepts(TextRule.NON_BLANK, "   "));
        System.out.println(accepts(TextRule.STARTS_WITH_J, "Java"));
        System.out.println(accepts(TextRule.STARTS_WITH_J, "Core"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumPredicateDemo.java
java EnumPredicateDemo
~~~

Stdout:

~~~text
true
false
true
false
~~~

Caller nhận Predicate<String> và không biết đó là enum hay lambda. Enum có tên rõ ràng cho từng behavior để log/config/select ở boundary.

## 32. Interface default combinators với enum Predicate

`Predicate<T>` có default methods như `and`, `or` và `negate`, cho phép kết hợp rules:

~~~java
java.util.function.Predicate<String> combined =
        TextRule.NON_BLANK.and(TextRule.STARTS_WITH_J);
~~~

**Quan trọng:** `combined` có kiểu Predicate<String> nhưng không nhất thiết là một enum constant hay `TextRule`; nó là một composed predicate được tạo qua default method. Không cast bừa về TextRule.

Cần tách:
- *Named finite rule*: `TextRule.NON_BLANK` (enum constant).
- *Composed runtime rule*: `NON_BLANK.and(STARTS_WITH_J)` (Predicate object theo contract).

Nếu business config chỉ được phép chọn một trong các named rules, giữ type enum ở config boundary thay vì cho phép arbitrary composed predicates.

## 33. Chương trình chạy: composition qua default method

Tạo **`EnumPredicateCompositionDemo.java`**:

~~~java
import java.util.function.Predicate;

public class EnumPredicateCompositionDemo {
    enum Rule implements Predicate<String> {
        NON_BLANK {
            @Override
            public boolean test(String s) {
                return s != null && !s.isBlank();
            }
        },
        STARTS_J {
            @Override
            public boolean test(String s) {
                return s != null && s.startsWith("J");
            }
        };
    }

    public static void main(String[] args) {
        Predicate<String> combined =
                Rule.NON_BLANK.and(Rule.STARTS_J);

        System.out.println("Java=" + combined.test("Java"));
        System.out.println("Core=" + combined.test("Core"));
        System.out.println("blank=" + combined.test("  "));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumPredicateCompositionDemo.java
java EnumPredicateCompositionDemo
~~~

Stdout:

~~~text
Java=true
Core=false
blank=false
~~~

`and` đến từ Predicate default method. Constant Rule không cần tự viết lại combinator.

## 34. Enum implement Runnable hoặc custom Command

Với một tập lệnh hữu hạn, enum constants có thể hiện thực interface Command:

~~~java
interface Command {
    void execute();
}

enum BasicCommand implements Command {
    START {
        @Override
        public void execute() {
            System.out.println("start");
        }
    },
    STOP {
        @Override
        public void execute() {
            System.out.println("stop");
        }
    };
}
~~~

Đây là dạng Command/Strategy đơn giản. Nếu `execute()` cần dependencies (database, HTTP client, request context), truyền chúng thành method parameters hoặc đưa chúng vào một **execution context** có contract rõ ràng, thay vì lưu mutable request state toàn cục bên trong enum constant.

## 35. Chương trình chạy: command có context truyền vào

Tạo **`EnumCommandDemo.java`**:

~~~java
public class EnumCommandDemo {
    interface Command {
        void execute(Context context);
    }

    static final class Context {
        private int counter;

        void increase() {
            counter++;
        }

        void decrease() {
            counter--;
        }

        int counter() {
            return counter;
        }
    }

    enum CounterCommand implements Command {
        INCREMENT {
            @Override
            public void execute(Context context) {
                context.increase();
            }
        },
        DECREMENT {
            @Override
            public void execute(Context context) {
                context.decrease();
            }
        };
    }

    public static void main(String[] args) {
        Context context = new Context();

        CounterCommand.INCREMENT.execute(context);
        CounterCommand.INCREMENT.execute(context);
        CounterCommand.DECREMENT.execute(context);

        System.out.println("count=" + context.counter());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumCommandDemo.java
java EnumCommandDemo
~~~

Stdout:

~~~text
count=1
~~~

Enum constants chỉ định logic; mutable context được tạo riêng cho workflow. Đây thường là thiết kế tốt hơn việc đặt một mutable `counter` field dùng chung trong enum constant.

## 36. Interface contract chứa checked exception

Enum implements interface methods phải tuân thủ `throws` declarations:

~~~java
interface Loader {
    String load() throws java.io.IOException;
}
~~~

Enum implementation có thể khai báo `throws IOException` hoặc không ném exception, tùy constant:

~~~java
enum Source implements Loader {
    INLINE {
        @Override
        public String load() {
            return "data";
        }
    },
    FAILING {
        @Override
        public String load() throws java.io.IOException {
            throw new java.io.IOException("missing");
        }
    };
}
~~~

Caller qua Loader reference vẫn phải xử lý IOException vì method interface contract khai báo checked exception.

Nếu interface method **không** khai báo checked exception tương thích, implementing enum method không được tự ý thêm throws IOException rộng hơn.

## 37. Chương trình chạy: IOException contract

Tạo **`EnumCheckedExceptionDemo.java`**:

~~~java
import java.io.IOException;

public class EnumCheckedExceptionDemo {
    interface Loader {
        String load() throws IOException;
    }

    enum Source implements Loader {
        INLINE {
            @Override
            public String load() {
                return "data";
            }
        },
        FAILING {
            @Override
            public String load() throws IOException {
                throw new IOException("missing");
            }
        };
    }

    public static void main(String[] args) {
        for (Source source : Source.values()) {
            Loader loader = source;
            try {
                System.out.println(source.name() + ":" +
                        loader.load());
            } catch (IOException ex) {
                System.out.println(source.name() + ":" +
                        ex.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumCheckedExceptionDemo.java
java EnumCheckedExceptionDemo
~~~

Stdout:

~~~text
INLINE:data
FAILING:missing
~~~

Có hai constant behaviors nhưng một `Loader` exception contract rõ ràng.

## 38. `values()` và `valueOf` vẫn thuộc enum type

Khi một enum implements interface, Java **không** thêm `values()` hoặc `valueOf(String)` vào interface ấy.

~~~java
Action operation = Operation.ADD;
// operation.values(); // Sai.
// operation.valueOf("ADD"); // Sai.
~~~

Dùng đúng enum type:

~~~java
Operation[] operations = Operation.values();
Operation chosen = Operation.valueOf("ADD");
~~~

Nếu business code muốn duyệt tất cả enum constants, cần biết **enum type** hoặc nhận collection choices từ nơi cấu hình. Một arbitrary Action implementation không nhất thiết thuộc một enum hữu hạn.

### `valueOf` có nhạy chữ hoa/thường?

Có. `Operation.valueOf("ADD")` khớp tên declaration chính xác; `"add"` không khớp tự động. Nếu input từ người dùng, validate/normalize ở boundary có policy rõ thay vì giả định valueOf tự trim/case-fold.

## 39. Chương trình chạy: duyệt constants qua interface

Tạo **`EnumValuesInterfaceDemo.java`**:

~~~java
public class EnumValuesInterfaceDemo {
    interface NamedAction {
        String label();
    }

    enum Action implements NamedAction {
        START, STOP;

        @Override
        public String label() {
            return name().toLowerCase(
                    java.util.Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        for (Action action : Action.values()) {
            NamedAction behavior = action;
            System.out.println(behavior.label());
        }

        Action chosen = Action.valueOf("STOP");
        System.out.println("chosen=" + chosen.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumValuesInterfaceDemo.java
java EnumValuesInterfaceDemo
~~~

Stdout:

~~~text
start
stop
chosen=STOP
~~~

Boundary biết finite enum domain nên dùng `Action.values()`; phía thực thi chung dùng interface NamedAction.

## 40. `EnumSet` khi enum implements interface

`EnumSet<E>` là collection tối ưu cho enum constants cùng declaring enum type. Nó yêu cầu E là enum type, không phải một arbitrary interface.

~~~java
java.util.EnumSet<Permission> permissions =
        java.util.EnumSet.of(Permission.READ, Permission.WRITE);
~~~

Nếu interface được đặt tên `Check`, bạn không thể `EnumSet<Check>` chỉ vì Permission implements Check — Check không thỏa enum type bound.

**Thiết kế:** Dùng EnumSet<Permission> để mô tả tập lựa chọn hữu hạn; trong logic kiểm tra hành vi, mỗi Permission vẫn có thể là Check interface.

## 41. Chương trình chạy: EnumSet và behavior

Tạo **`EnumSetInterfaceDemo.java`**:

~~~java
import java.util.EnumSet;

public class EnumSetInterfaceDemo {
    interface PermissionCheck {
        boolean allows(String operation);
    }

    enum Permission implements PermissionCheck {
        READ {
            @Override
            public boolean allows(String operation) {
                return "read".equals(operation);
            }
        },
        WRITE {
            @Override
            public boolean allows(String operation) {
                return "write".equals(operation);
            }
        };
    }

    public static void main(String[] args) {
        EnumSet<Permission> granted =
                EnumSet.of(Permission.READ, Permission.WRITE);

        for (Permission permission : granted) {
            PermissionCheck check = permission;
            System.out.println(permission.name() + ":" +
                    check.allows("write"));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumSetInterfaceDemo.java
java EnumSetInterfaceDemo
~~~

Stdout:

~~~text
READ:false
WRITE:true
~~~

EnumSet duyệt theo natural order của enum declarations. Các elements vẫn là Permission constants thực thi PermissionCheck.

## 42. `EnumMap`: key là enum type, value có thể là interface

`EnumMap<E,V>` yêu cầu key E là enum type:

~~~java
java.util.EnumMap<TaskKind, TaskHandler> handlers =
        new java.util.EnumMap<>(TaskKind.class);
~~~

Interface-typed values cho phép map từ finite enum choices sang reusable/customizable implementations, bao gồm named classes, lambda hoặc enum constants khác.

Pattern này hữu ích khi **danh sách lựa chọn đóng**, nhưng behavior implementation có thể được cấu hình hoặc thay tại runtime. Không bắt buộc nhét mọi algorithm trực tiếp vào enum body.

## 43. Chương trình chạy: EnumMap liên kết interface strategy

Tạo **`EnumMapStrategyDemo.java`**:

~~~java
import java.util.EnumMap;
import java.util.function.IntUnaryOperator;

public class EnumMapStrategyDemo {
    enum TaskKind {
        DOUBLE, SQUARE
    }

    public static void main(String[] args) {
        EnumMap<TaskKind, IntUnaryOperator> handlers =
                new EnumMap<>(TaskKind.class);

        handlers.put(TaskKind.DOUBLE, value -> value * 2);
        handlers.put(TaskKind.SQUARE, value -> value * value);

        System.out.println("double=" +
                handlers.get(TaskKind.DOUBLE).applyAsInt(4));
        System.out.println("square=" +
                handlers.get(TaskKind.SQUARE).applyAsInt(4));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumMapStrategyDemo.java
java EnumMapStrategyDemo
~~~

Stdout:

~~~text
double=8
square=16
~~~

Đây là **phương án thay thế** enum implements interface trực tiếp. Chọn enum method khi behavior ổn định thuộc intrinsic choice; chọn EnumMap với interface values khi cần pluggable implementation.

## 44. Constant-specific bodies ảnh hưởng runtime Class metadata

Nếu enum constant có class body:

~~~java
enum Style {
    SIMPLE,
    CUSTOM {
        @Override
        String label() {
            return "custom";
        }
    };

    String label() {
        return "simple";
    }
}
~~~

`SIMPLE.getClass()` thường là `Style.class`, còn `CUSTOM.getClass()` là class của constant-specific anonymous subclass.

Muốn biết **declaring enum class** ổn định, dùng `getDeclaringClass()` thay vì `getClass()`:

~~~java
Style.CUSTOM.getDeclaringClass() == Style.class // true
~~~

Điều này quan trọng cho reflection, enum registries và code không muốn phụ thuộc vào generated class names.

## 45. Chương trình chạy: `getClass` khác `getDeclaringClass`

Tạo **`EnumDeclaringClassDemo.java`**:

~~~java
public class EnumDeclaringClassDemo {
    interface Described {
        String description();
    }

    enum Style implements Described {
        SIMPLE,
        CUSTOM {
            @Override
            public String description() {
                return "custom";
            }
        };

        @Override
        public String description() {
            return "simple";
        }
    }

    public static void main(String[] args) {
        System.out.println("simple plain class=" +
                (Style.SIMPLE.getClass() == Style.class));
        System.out.println("custom plain class=" +
                (Style.CUSTOM.getClass() == Style.class));
        System.out.println("custom declaring class=" +
                (Style.CUSTOM.getDeclaringClass() ==
                        Style.class));
        System.out.println("custom description=" +
                Style.CUSTOM.description());
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumDeclaringClassDemo.java
java EnumDeclaringClassDemo
~~~

Stdout:

~~~text
simple plain class=true
custom plain class=false
custom declaring class=true
custom description=custom
~~~

**Không viết** business logic như `constant.getClass() == Style.class` rồi coi tất cả constants là một exact runtime class khi có constant-specific class bodies.

## 46. `name()` và `ordinal()` không phải interface contract mặc định

`name()` là final instance method được kế thừa từ `Enum`, trả identifier đã khai báo. `ordinal()` trả vị trí declaration.

Ví dụ:

~~~java
enum Mode {
    FIRST, SECOND
}
~~~

- `Mode.FIRST.name()` → `"FIRST"`.
- `Mode.FIRST.ordinal()` → `0`.

Nếu interface có method `String code()`, enum có thể implement bằng `name()`, nhưng không phải lúc nào đó cũng là API tốt.

### Độ bền dữ liệu

- `ordinal()` có thể đổi khi reorder constants; không dùng như persistent database ID.
- `name()` đổi nếu rename constant; nếu external protocol cần ổn định, khai báo `code` field explicit.
- `toString()` có thể override; không dùng nó thay `name()` khi cần exact enum declaration identity.

## 47. Chương trình chạy: stable interface code khác `name()`

Tạo **`StableEnumCodeDemo.java`**:

~~~java
public class StableEnumCodeDemo {
    interface Coded {
        String code();
    }

    enum PaymentState implements Coded {
        WAITING("W"), SETTLED("S");

        private final String code;

        PaymentState(String code) {
            this.code = code;
        }

        @Override
        public String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        for (PaymentState state : PaymentState.values()) {
            Coded value = state;
            System.out.println(state.name() + ":" +
                    value.code() + ":" + state.ordinal());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 StableEnumCodeDemo.java
java StableEnumCodeDemo
~~~

Stdout:

~~~text
WAITING:W:0
SETTLED:S:1
~~~

`code()` là external/domain contract, tách khỏi tên và thứ tự enum constants.

## 48. Có nên implement `Comparable` trong enum?

Mọi enum E đã kế thừa behavior `Comparable<E>` thông qua `java.lang.Enum<E>` và có natural ordering theo declaration order. `compareTo` của Enum là final và không thể override để thay đổi thứ tự tự nhiên.

Nếu cần business ordering như theo priority score, dùng:
- `Comparator<E>` explicit;
- một enum khác implements `Comparator<SpecificType>`;
- `sortKey()` field trong enum cùng Comparator so sánh key.

Không tìm cách khai báo lại `Comparable<Other>` tùy ý để đổi ordering của bản thân enum; có thể xung đột generic inheritance với `Comparable<E>`.

## 49. Chương trình chạy: natural enum order và custom comparator

Tạo **`EnumOrderingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class EnumOrderingDemo {
    enum Priority {
        LOW(30), MEDIUM(20), HIGH(10);

        private final int rank;

        Priority(int rank) {
            this.rank = rank;
        }

        int rank() {
            return rank;
        }
    }

    public static void main(String[] args) {
        List<Priority> values = new ArrayList<>(
                List.of(Priority.HIGH, Priority.LOW, Priority.MEDIUM));

        values.sort(Comparator.naturalOrder());
        System.out.println("natural=" + values);

        values.sort(Comparator.comparingInt(Priority::rank));
        System.out.println("by rank=" + values);
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumOrderingDemo.java
java EnumOrderingDemo
~~~

Stdout:

~~~text
natural=[LOW, MEDIUM, HIGH]
by rank=[HIGH, MEDIUM, LOW]
~~~

Natural enum ordering dựa trên declaration order; custom comparator dựa trên rank field explicit.

## 50. Shared mutable state trong enum: cẩn trọng

Enum constants được tạo bởi class initialization và có identity ổn định. Nhưng **enum instance fields có thể mutable** nếu bạn cho phép.

~~~java
enum Counter {
    INSTANCE;

    int value;

    void increment() {
        value++;
    }
}
~~~

Nếu dùng Counter.INSTANCE từ nhiều threads, `value++` không atomic. Việc “enum singleton” không làm mọi method tự thread-safe.

### Khi dùng enum làm stateless strategy

Ưu tiên:
- final configuration fields được set trong enum constructor;
- methods tính toán trên parameters;
- truyền per-request context làm arguments;
- dùng immutable data snapshots;
- concurrency primitives nếu thực sự cần shared mutable state.

Đừng lưu request-specific user/session data trong enum constants.

## 51. Chương trình chạy: AtomicInteger trong enum khi cần shared counter

Tạo **`EnumAtomicCounterDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class EnumAtomicCounterDemo {
    interface Counter {
        int incrementAndGet();
    }

    enum GlobalCounter implements Counter {
        INSTANCE;

        private final AtomicInteger value = new AtomicInteger();

        @Override
        public int incrementAndGet() {
            return value.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        Counter counter = GlobalCounter.INSTANCE;

        System.out.println(counter.incrementAndGet());
        System.out.println(counter.incrementAndGet());
        System.out.println("same object=" +
                (counter == GlobalCounter.INSTANCE));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumAtomicCounterDemo.java
java EnumAtomicCounterDemo
~~~

Stdout:

~~~text
1
2
same object=true
~~~

AtomicInteger có atomic increments. Ví dụ chạy tuần tự, nên stdout xác định; trong multithreaded tests cần đồng bộ lúc đọc kết quả cuối.

## 52. Enum constants và object identity

Đối với một enum type, mỗi declared constant có một object identity ổn định. So sánh `==` là lựa chọn chuẩn:

~~~java
Operation a = Operation.ADD;
Operation b = Operation.valueOf("ADD");
System.out.println(a == b);
~~~

Kết quả true khi `Operation` là enum type chứa ADD.

Khi reference có declared type interface, bạn vẫn đang giữ same object reference. Không cần tạo copy để chuyển từ enum type sang interface:

~~~java
IntOperation strategy = Operation.ADD;
~~~

### `equals`

Enum.equals là final và dùng identity semantics tương ứng. Đừng override equals/hashCode trên enum để tạo “value equality” khác. Nếu domain cần một object có nhiều dynamic fields và value-based equality, record/named immutable class có thể phù hợp hơn enum.

## 53. Enum implement interface khác named class hoặc lambda ở điểm nào?

| Đặc tính | Enum implements interface | Named class implements interface | Lambda |
| --- | --- | --- | --- |
| Số instances | Cố định bởi enum constants | Tạo nhiều bằng `new`/factory | Theo lambda evaluation semantics |
| Named choices | Có | Theo class/object design | Không tự có enum-style names |
| Interface polymorphism | Có | Có | Có nếu functional interface |
| Multiple abstract methods | Có thể implement | Có thể implement | Không trực tiếp |
| Per-instance constructor args từ caller | Không | Có | Không theo class constructor syntax |
| Constant-specific overrides | Có | Qua subclasses/instances | Không có class body |
| Generic type parameters trên declaring type | Enum không generic | Có thể generic | Dựa target functional type |
| `values()`/`valueOf` | Có trên enum type | Không tự có | Không |
| EnumSet/EnumMap key | Có | Không | Không |
| Behavioral extensibility từ plugin runtime | Hạn chế bởi finite constants | Rộng hơn | Rộng hơn khi target phù hợp |
| Shared mutable state risk | Có | Có | Có qua capture |

Nếu các choices là **tập hữu hạn, có ý nghĩa domain**, enum strategy là lựa chọn mạnh. Nếu choices được cấu hình động hoặc cần dependency per instance, named strategies/lambda có thể linh hoạt hơn.

## 54. Khi nào enum strategy tốt hơn `switch`?

Giả sử mỗi nơi gọi có:

~~~java
switch (operation) {
    case ADD -> left + right;
    case MULTIPLY -> left * right;
}
~~~

Switch expression trên enum hữu ích và rõ nếu logic ngắn, thực hiện **ở một nơi**, cần compiler check exhaustiveness và không có contract interface cho plugin.

Enum implements interface với constant-specific methods có lợi khi:
- nhiều nơi cần cùng behavior;
- muốn caller chỉ biết interface;
- mỗi enum constant sở hữu thuật toán tự nhiên;
- giảm lặp switch ở nhiều modules;
- muốn test behaviors của toàn bộ constants bằng một contract.

**Không bắt buộc “mọi enum có switch đều sai”.** Nếu behavior không thuộc domain enum hoặc chỉ là mapping một lần, switch có thể dễ đọc hơn.

## 55. Chương trình chạy: so sánh switch với đa hình

Tạo **`EnumSwitchVsPolymorphismDemo.java`**:

~~~java
public class EnumSwitchVsPolymorphismDemo {
    interface BinaryOp {
        int apply(int a, int b);
    }

    enum Mode implements BinaryOp {
        ADD {
            @Override
            public int apply(int a, int b) {
                return a + b;
            }
        },
        MULTIPLY {
            @Override
            public int apply(int a, int b) {
                return a * b;
            }
        };
    }

    static int withSwitch(Mode mode, int a, int b) {
        return switch (mode) {
            case ADD -> a + b;
            case MULTIPLY -> a * b;
        };
    }

    static int polymorphic(BinaryOp op, int a, int b) {
        return op.apply(a, b);
    }

    public static void main(String[] args) {
        System.out.println("switch=" +
                withSwitch(Mode.ADD, 3, 4));
        System.out.println("interface=" +
                polymorphic(Mode.MULTIPLY, 3, 4));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EnumSwitchVsPolymorphismDemo.java
java EnumSwitchVsPolymorphismDemo
~~~

Stdout:

~~~text
switch=7
interface=12
~~~

Cả hai hợp lệ trong Java 17. Chọn abstraction level theo phạm vi reuse và độ phức tạp, không thay switch bằng enum method như một luật máy móc.

## 56. Dùng interface để tách module API khỏi enum implementation

Ví dụ module API công bố:

~~~java
public interface DiscountPolicy {
    long apply(long cents);
}
~~~

Module implementation có thể dùng:

~~~java
enum StandardDiscount implements DiscountPolicy {
    NONE, TEN_PERCENT;

    @Override
    public long apply(long cents) {
        return switch (this) {
            case NONE -> cents;
            case TEN_PERCENT -> cents - cents / 10;
        };
    }
}
~~~

Các đoạn này là minh họa thuộc các file/package phù hợp.

Client chỉ cần `DiscountPolicy` để áp dụng behavior. Nhưng khi client phải liệt kê standard choices hoặc parse string code, nó cần biết cụ thể `StandardDiscount` (hoặc một service liệt kê choices).

**Thiết kế API:** Nếu plugins ngoài module cũng cần implements DiscountPolicy, hãy tránh làm interface contract phụ thuộc vào enum-only methods như `name()`.

## 57. Chương trình chạy: interface contract với named alternative

Tạo **`EnumAndNamedImplementationDemo.java`**:

~~~java
public class EnumAndNamedImplementationDemo {
    interface DiscountPolicy {
        long apply(long cents);
    }

    enum StandardDiscount implements DiscountPolicy {
        NONE {
            @Override
            public long apply(long cents) {
                return cents;
            }
        },
        TEN_PERCENT {
            @Override
            public long apply(long cents) {
                return cents - cents / 10;
            }
        };
    }

    static final class FixedDiscount implements DiscountPolicy {
        private final long reduction;

        FixedDiscount(long reduction) {
            if (reduction < 0) {
                throw new IllegalArgumentException("reduction");
            }
            this.reduction = reduction;
        }

        @Override
        public long apply(long cents) {
            return Math.max(0, cents - reduction);
        }
    }

    static long calculate(DiscountPolicy policy, long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("cents");
        }
        return policy.apply(cents);
    }

    public static void main(String[] args) {
        System.out.println("enum=" +
                calculate(StandardDiscount.TEN_PERCENT, 1000));
        System.out.println("named=" +
                calculate(new FixedDiscount(75), 1000));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumAndNamedImplementationDemo.java
java EnumAndNamedImplementationDemo
~~~

Stdout:

~~~text
enum=900
named=925
~~~

Interface giúp core calculation chấp nhận cả **finite enum strategy** và **stateful named class**. Đây là lợi thế quan trọng của việc thiết kế interface độc lập.

## 58. Enum và lambda cùng implement functional interface

Một enum constant implements `Function<T,R>` hoặc `Predicate<T>` có thể được truyền vào nơi chấp nhận lambda. Ví dụ:

~~~java
java.util.function.IntUnaryOperator op =
        NumberTransform.DOUBLE;
~~~

hoặc:

~~~java
java.util.function.IntUnaryOperator op =
        value -> value * 2;
~~~

Phân biệt:
- Enum có constant name, finite known strategies, shared stable object identity.
- Lambda có behavior linh hoạt, có thể capture runtime values và không có enum constants list.
- Khi algorithm chứa config khác nhau trên từng request, lambda/factory hoặc named class có thể phù hợp hơn.
- Interface typed APIs cho phép chọn cách implementation mà không đổi caller signature.

## 59. Chương trình chạy: enum và lambda trong một API

Tạo **`EnumLambdaInterchangeDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class EnumLambdaInterchangeDemo {
    enum NumberTransform implements IntUnaryOperator {
        DOUBLE {
            @Override
            public int applyAsInt(int value) {
                return value * 2;
            }
        },
        SQUARE {
            @Override
            public int applyAsInt(int value) {
                return value * value;
            }
        };
    }

    static int transform(IntUnaryOperator strategy, int input) {
        return strategy.applyAsInt(input);
    }

    public static void main(String[] args) {
        System.out.println("enum=" +
                transform(NumberTransform.DOUBLE, 4));

        int offset = 3;
        System.out.println("lambda=" +
                transform(value -> value + offset, 4));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumLambdaInterchangeDemo.java
java EnumLambdaInterchangeDemo
~~~

Stdout:

~~~text
enum=8
lambda=7
~~~

Code tiêu thụ IntUnaryOperator không cần biết implementation có phải enum hay lambda. `offset` là effectively final local được lambda capture.

## 60. Enum implements interface không đổi Java inheritance rules

Java enum:
- implicitly extends `java.lang.Enum<E>`;
- không có explicit `extends SomeClass` clause tùy ý;
- có thể implement multiple interfaces;
- không thể bị subclasses tùy ý từ ngoài bằng `extends MyEnum`;
- không được tạo thêm instances bằng `new`.

Constant-specific class bodies cung cấp anonymous subclasses *do enum declaration tạo nên*, nhưng không có nghĩa ứng dụng được phép subclass enum từ bất kỳ file nào.

### Lỗi thường gặp

~~~java
// enum Wrong extends SomeBase implements Action { ONE } // Sai: enum không extends tùy ý.
// class Extra extends MyEnum { }                    // Sai: không được subclass enum.
~~~

Nếu cần extensible hierarchy từ plugins, dùng interface + named classes/records phù hợp, chứ không ép một enum làm framework base class có subclasses tùy ý.

## 61. Dùng enum constant trong interface-typed collection

Một `List<SomeInterface>` có thể chứa enum constants cùng các other implementations:

~~~java
java.util.List<DiscountPolicy> policies = java.util.List.of(
        StandardDiscount.NONE,
        StandardDiscount.TEN_PERCENT,
        new FixedDiscount(75)
);
~~~

Đây là conceptual snippet dựa trên types của ví dụ trước. Collection giữ references tới những objects implement cùng interface.

**Khác EnumSet:** `List<DiscountPolicy>` không bắt buộc elements là enum; còn `EnumSet<StandardDiscount>` chỉ chứa constants của declaring enum type.

Dùng common interface collections khi behavior có thể đến từ nhiều implementation types. Dùng EnumSet/EnumMap khi khai thác finite enum keys/domain.

## 62. Equality và `hashCode` qua interface

Với enum constants, identity semantics mạnh và ổn định. Với interface typed refs:

~~~java
DiscountPolicy a = StandardDiscount.NONE;
DiscountPolicy b = StandardDiscount.NONE;
System.out.println(a == b); // true
~~~

Nhưng nếu `DiscountPolicy` có named class instances hoặc lambdas, equality/identity có thể khác. Không thể giả định **mọi interface implementation** đều là singleton/value-equal.

### Thiết kế

Nếu business logic cần code identity (ví dụ `"NONE"`), thêm method `String code()` vào domain interface hoặc lưu enum code bên ngoài. Đừng phụ thuộc vào `implementation.getClass().getName()` hay `System.identityHashCode` làm business key.

## 63. Reflection khi enum implements interface

Tại runtime:

~~~java
Action.class.isAssignableFrom(Task.class)
~~~

true nếu Task implements Action. Trong khi:

~~~java
Task.class.isEnum()
~~~

true với declaring enum class. Nhưng với constant-specific class body, `Task.CONSTANT.getClass().isEnum()` có thể false vì runtime class là một subclass of enum, không phải declaring enum class. Dùng:

~~~java
Task.CONSTANT.getDeclaringClass().isEnum()
~~~

để kiểm tra declaring enum type đúng semantics.

### Java Class API không phải business metadata

Đừng parse synthetic class names của constant bodies để suy ra strategy identity. Dùng `name()` hoặc stable explicit code() field.

## 64. Chương trình chạy: reflection xác nhận interface và enum declaration

Tạo **`EnumReflectionDemo.java`**:

~~~java
public class EnumReflectionDemo {
    interface Action {
        void execute();
    }

    enum Task implements Action {
        RUN {
            @Override
            public void execute() {
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("implements Action=" +
                Action.class.isAssignableFrom(Task.class));
        System.out.println("declaring enum=" + Task.class.isEnum());
        System.out.println("constant runtime enum=" +
                Task.RUN.getClass().isEnum());
        System.out.println("declaring matches=" +
                (Task.RUN.getDeclaringClass() == Task.class));
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumReflectionDemo.java
java EnumReflectionDemo
~~~

Stdout:

~~~text
implements Action=true
declaring enum=true
constant runtime enum=false
declaring matches=true
~~~

Constant-specific RUN có own anonymous subclass class metadata; `getDeclaringClass` vẫn trả Task.class.

## 65. Enum constructor và initialization pitfalls

Enum constants được initialize trong class initialization. Đặc biệt cẩn trọng khi enum constructors truy cập static fields không phải compile-time constants của chính enum: Java có restrictions để tránh illegal forward references/circular initialization.

### Lựa chọn an toàn

- Khởi tạo constant configuration qua constructor arguments.
- Dùng final instance fields để giữ code/label/config.
- Tránh thực hiện IO, threading, đăng ký callbacks hoặc truy cập các global mutable services trong enum constructors.
- Đừng publish partially initialized `this`.
- Nếu initialization có thể thất bại, xử lý theo documented service startup policy.

Ví dụ enum strategy nên thuần khi có thể:

~~~java
enum Multiplier implements java.util.function.IntUnaryOperator {
    DOUBLE(2), TRIPLE(3);

    private final int factor;

    Multiplier(int factor) {
        this.factor = factor;
    }

    @Override
    public int applyAsInt(int value) {
        return factor * value;
    }
}
~~~

Đây là snippet hợp lệ và dễ kiểm thử: constants có immutable factor configuration.

## 66. Chương trình chạy: parameterized enum strategy

Tạo **`ParameterizedEnumStrategyDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class ParameterizedEnumStrategyDemo {
    enum Multiplier implements IntUnaryOperator {
        DOUBLE(2), TRIPLE(3);

        private final int factor;

        Multiplier(int factor) {
            this.factor = factor;
        }

        @Override
        public int applyAsInt(int value) {
            return Math.multiplyExact(value, factor);
        }
    }

    public static void main(String[] args) {
        IntUnaryOperator doubleOp = Multiplier.DOUBLE;
        IntUnaryOperator tripleOp = Multiplier.TRIPLE;

        System.out.println("double=" + doubleOp.applyAsInt(5));
        System.out.println("triple=" + tripleOp.applyAsInt(5));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParameterizedEnumStrategyDemo.java
java ParameterizedEnumStrategyDemo
~~~

Stdout:

~~~text
double=10
triple=15
~~~

Mọi constants dùng cùng algorithm nhưng khác immutable factor, nên không cần constant-specific class bodies.

## 67. Null handling trong enum interface methods

Enum constants không phải null; nhưng **arguments** truyền vào interface methods có thể null trừ khi contract cấm.

Ví dụ:

~~~java
enum Formatter implements java.util.function.UnaryOperator<String> {
    TRIM;

    @Override
    public String apply(String input) {
        return java.util.Objects.requireNonNull(
                input, "input").strip();
    }
}
~~~

API phải định nghĩa rõ:
- trả empty string với null?
- từ chối bằng NullPointerException/IllegalArgumentException?
- hay biểu diễn thiếu giá trị bằng Optional?

Không nên để mỗi constant tự đưa ra null policy khác nhau khi chúng phải cùng thỏa một common interface contract, trừ khi domain nói rõ sự khác biệt.

## 68. Chương trình chạy: consistent argument validation

Tạo **`EnumNullValidationDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.UnaryOperator;

public class EnumNullValidationDemo {
    enum Formatter implements UnaryOperator<String> {
        TRIM, UPPER;

        @Override
        public String apply(String input) {
            String checked = Objects.requireNonNull(input, "input");

            return switch (this) {
                case TRIM -> checked.strip();
                case UPPER -> checked.toUpperCase(
                        java.util.Locale.ROOT);
            };
        }
    }

    public static void main(String[] args) {
        System.out.println(Formatter.TRIM.apply(" Java "));

        try {
            Formatter.UPPER.apply(null);
        } catch (NullPointerException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EnumNullValidationDemo.java
java EnumNullValidationDemo
~~~

Stdout:

~~~text
Java
rejected=input
~~~

Có thể implement chung bằng switch khi null validation áp dụng cho mọi constant. Nếu các thuật toán phức tạp, constant-specific methods có thể dễ mở rộng hơn.

## 69. Unit tests: mọi constant phải tuân thủ interface contract

Với enum `Strategy implements Function<X,Y>`, tests nên:

1. Duyệt `Strategy.values()` để kiểm tra mọi constant.
2. Kiểm tra result với input thông thường.
3. Kiểm tra boundary values và negative/null inputs theo contract.
4. Kiểm tra overflow, precision, locale, encoding nếu logic có liên quan.
5. Kiểm tra exception type và message theo API.
6. Kiểm tra shared mutable state/cross-request behavior nếu enum có state.
7. Kiểm tra interface default methods/composition.
8. Kiểm tra persistence-code stability khi external protocol dùng code().
9. Kiểm tra mọi enum constant được register trong mapping/selection.
10. Không test generated synthetic class name của constant bodies.

**Không đủ:** chỉ test `Operation.ADD` rồi tin các constants khác đã implement correctly. Compiler kiểm tra signature, không thể chứng minh arithmetic/business semantics của method body.

## 70. Chương trình chạy: contract tests cho toàn enum

Tạo **`EnumContractTestDemo.java`**:

~~~java
public class EnumContractTestDemo {
    interface IntOperation {
        int apply(int left, int right);
    }

    enum Operation implements IntOperation {
        ADD {
            @Override
            public int apply(int left, int right) {
                return left + right;
            }
        },
        MULTIPLY {
            @Override
            public int apply(int left, int right) {
                return left * right;
            }
        };
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        check(Operation.ADD.apply(2, 3) == 5, "ADD");
        check(Operation.MULTIPLY.apply(2, 3) == 6, "MULTIPLY");

        for (Operation operation : Operation.values()) {
            IntOperation polymorphic = operation;
            check(polymorphic.apply(1, 1) >= 1,
                    operation.name());
        }

        System.out.println("specific cases PASS");
        System.out.println("interface contract PASS");
    }
}
~~~

~~~bash
javac -encoding UTF-8 EnumContractTestDemo.java
java EnumContractTestDemo
~~~

Stdout:

~~~text
specific cases PASS
interface contract PASS
~~~

Đây là compact executable assertions. Trong dự án thật, JUnit parameterized tests có thể duyệt enum constants và kiểm tra case tables nhiều hơn.

## 71. Không dùng enum khi tập implementations cần mở rộng động

Enum là finite type do source declaration xác định. Không thể thêm enum constants tại runtime bằng cấu hình file, database row hay plugin JAR mà vẫn giữ đúng enum semantics.

Nếu business yêu cầu:
- người dùng tự tạo policy;
- plugin mới triển khai behavior;
- mỗi customer có config khác nhau;
- strategy có complex constructor dependencies;
- nhiều runtime instances mỗi strategy;

thì định nghĩa **interface contract**, rồi cung cấp named implementations/factories/service registration. Enum có thể biểu diễn **standard built-in choices**, không nhất thiết là toàn bộ universe behaviors.

### Kết hợp

`DiscountPolicy` interface + `StandardDiscount` enum + `ConfigurableDiscount` class là mô hình thường linh hoạt hơn việc cố nhét mọi rule vào enum constant.

## 72. Checklist chọn enum implements interface

Trước khi thiết kế, kiểm tra:

- Tập choices có hữu hạn, ổn định và thuộc domain không?
- Mỗi choice có hành vi đủ rõ để gắn trực tiếp vào enum không?
- Có một interface contract đúng cho mọi choices không?
- Caller có lợi nếu không cần biết enum type cụ thể không?
- Behavior chỉ khác dữ liệu hay thực sự cần override từng constant?
- Có cần implements nhiều interfaces không?
- Default methods có giúp shared behavior không?
- Có conflict giữa default methods cần giải quyết không?
- Checked exceptions được định nghĩa rõ không?
- Generic type arguments có thống nhất cho mọi constants không?
- Có shared mutable state nguy hiểm không?
- Tên/ordinal của enum có bị dùng làm external ID không?
- Logic có cần runtime plugins/configurable instances không?
- Testing có bao phủ mọi constants và boundaries không?
- EnumSet/EnumMap có giúp biểu diễn finite choices không?
- Code dùng reflection có biết constant-specific runtime class khác declaring enum class không?

Nếu nhiều câu trả lời cho thấy cần dynamic configuration, hãy cân nhắc named strategy classes hoặc EnumMap mapping sang implementations khác.

## 73. Lỗi compiler hay gặp

| Vấn đề | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `enum E extends Base` | Enum implicitly extends Enum<E> | Bỏ extends; dùng interface/composition |
| `enum E implements I` nhưng thiếu abstract method | Contract chưa được thực thi | Implement method chung hoặc từng constant |
| Method implement interface thiếu `public` | Giảm visibility | Khai báo `public` |
| Sai @Override method signature | Không override contract | Khớp tên, args, return type |
| Constant có body nhưng không implement enum abstract method | Constant phải concrete | Override trong mỗi body |
| Hai interface defaults cùng signature | Inheritance conflict | Override và resolve rõ |
| Gọi `EnumType.interfaceStaticMethod` | Static interface methods không inherited | `InterfaceName.method` |
| `new EnumType()` | Không được instantiate enum tùy ý | Dùng constants |
| Cast interface-typed value sang enum không chắc chắn | Có thể là implementation khác | Xác định type trước hoặc giữ enum at boundary |
| `EnumSet<MyInterface>` | EnumSet requires enum type | `EnumSet<MyEnum>` |
| Dùng `name()` qua interface không khai báo name() | Declared type giới hạn API | Dùng enum type hoặc domain code() |
| `enum MyEnum<T>` | Enum declarations không generic như classes | Implement parameterized interface cố định |
| Override `Enum.compareTo` | Enum.compareTo final | Dùng Comparator |
| Refactor constant body nhưng dựa `getClass()==Enum.class` | Constant body tạo subclass | Dùng `getDeclaringClass()` |
| Thêm IOException trong implementation không được contract cho | Checked exception override restriction | Sửa throws contract/handle |
| Mutate enum field đồng thời không synchronization | Singleton constant không thread-safe tự động | Immutable state/Atomic/synchronization |

## 74. Anti-patterns cần tránh

**Một enum khổng lồ phụ thuộc mọi service:** Mỗi constant gọi HTTP, SQL, UI và global config khiến code khó test, init/lifecycle phức tạp. Tách service dependencies.

**Dùng ordinal làm database key:** Thay đổi declaration order làm ý nghĩa dữ liệu cũ đổi.

**Lạm dụng name/toString làm public API protocol:** Cần code field ổn định.

**Nhét request state trong enum constants:** Mọi requests share cùng constant object, gây data races/data leakage giữa workflows.

**Ép interface gọi enum-only APIs:** Không mọi implementation của interface đều là enum.

**Dùng `instanceof`/cast liên tục sau khi nhận interface:** Có thể interface thiếu operation cần thiết; xem lại API contract.

**Né tất cả switch:** Switch expression trên enum có thể rõ và kiểm tra exhaustive; không cần mỗi one-line mapping biến thành constant-specific class body.

**Kiểm tra runtime class bằng `getClass()==EnumType.class`:** Sai cho constants có specific bodies; dùng `getDeclaringClass()`.

**Không test individual algorithms:** Interface method signatures hợp lệ không đảm bảo logic của từng constant đúng.

## 75. Bài tập 1 — Ghi đúng cú pháp

Một interface:

~~~java
interface Action {
    void run();
}
~~~

Hãy khai báo enum Job có constants BUILD, CLEAN và cùng in tên constant.

**Đáp án:**

~~~java
enum Job implements Action {
    BUILD, CLEAN;

    @Override
    public void run() {
        System.out.println(name());
    }
}
~~~

`Job.BUILD.run()` in BUILD. `Job.CLEAN.run()` in CLEAN. Method implementation dùng chung.

## 76. Bài tập 2 — Mỗi constant khác behavior

`interface Operation { int apply(int a,int b); }` và enum ADD/MULTIPLY.

**Đáp án gợi ý:** Dùng constant-specific bodies override `public int apply(int,int)`; ADD trả a+b, MULTIPLY trả a*b. Cũng có thể implement chung bằng switch khi logic rất ngắn. Test cả hai.

## 77. Bài tập 3 — Visibility

~~~java
interface Task {
    void execute();
}

enum Job implements Task {
    RUN;

    // void execute() {} // Sai.
}
~~~

**Đáp án:** Implementation phải `public void execute()`, tốt nhất có `@Override`. Interface abstract method `execute()` là public.

## 78. Bài tập 4 — Interface default method

Interface có `String code()` và default `String display(){ return "["+code()+"]"; }`. Enum implements code.

**Đáp án:** Không bắt buộc override display trong enum; default method đã có implementation. `enumConstant.display()` gọi default method và qua `code()` nhận đúng constant behavior.

## 79. Bài tập 5 — Hai interfaces trùng default

Interfaces A và B đều có default `String label()`. Enum implements cả hai.

**Đáp án:** Enum phải override label để giải quyết conflict. Có thể gọi `A.super.label()` hoặc `B.super.label()` trong override theo Java interface-super syntax hợp lệ.

## 80. Bài tập 6 — Enum và generic interface

Có thể khai báo `enum Transform implements Function<String,String>` không?

**Đáp án:** Có. Mọi constants cùng implement Function<String,String> contract. Nhưng khai báo kiểu `enum Transform<T>` như một generic class là không hợp lệ.

## 81. Bài tập 7 — Interface variable

~~~java
Runnable callback = SomeEnum.RUN;
~~~

Giả sử SomeEnum implements Runnable. Có gọi `callback.name()` trực tiếp không?

**Đáp án:** Không, Runnable không có `name()`. Runtime object vẫn là enum constant, nhưng declared type của reference là Runnable.

## 82. Bài tập 8 — EnumSet

Có `enum Permission implements Check { READ, WRITE; ... }`. Nên viết `EnumSet<Check>` hay `EnumSet<Permission>`?

**Đáp án:** `EnumSet<Permission>`, vì EnumSet generic parameter phải là enum type. Check interface không thỏa bound `E extends Enum<E>`.

## 83. Bài tập 9 — Constant-specific metadata

`enum X { A, B { @Override String text(){...} }; String text(){...} }`. `X.B.getClass()==X.class` có bắt buộc true không?

**Đáp án:** Không; B có constant-specific class body, runtime class của B khác declaring enum class X. `X.B.getDeclaringClass()==X.class` true.

## 84. Bài tập 10 — Enum strategy và shared state

Một enum implements Counter, có `int value` và `value++`. Nhiều threads gọi cùng constant.

**Đáp án:** Không thread-safe chỉ vì là enum. Dùng immutable/per-request state, AtomicInteger hoặc synchronization thích hợp nếu shared mutable counter là yêu cầu thật.

## 85. Bài tập 11 — Lựa chọn giải pháp

Một discount policy có bốn loại cố định, mỗi loại tính theo công thức riêng, không có per-user config.

**Đáp án gợi ý:** Enum implements DiscountPolicy với constant-specific bodies hoặc shared implementation + immutable fields. Nếu các loại được thêm theo plugin hoặc runtime config, named implementations/registry có thể phù hợp hơn.

## 86. Bài tập 12 — Test contract

Tại sao compiler chấp nhận enum implements interface nhưng vẫn cần unit tests cho mọi constant?

**Đáp án:** Compiler đảm bảo signatures/types/access contracts, không đảm bảo mỗi implementation dùng đúng công thức, null policy, overflow/precision hay exception semantics. Duyệt `values()` và test per-constant scenarios.

## 87. Tổng hợp quy tắc ghi nhớ

- **Enum có thể implements interface(s)** với `enum E implements I1, I2`.
- **Enum không tự extends class tùy ý** vì nó đã có implicit superclass Enum<E>.
- **Interface contract** có thể được implement chung ở enum body hoặc riêng cho constants.
- **Constant-specific body** tạo override riêng cho behavior và ảnh hưởng runtime class metadata.
- **Interface default methods** được kế thừa nếu không conflict/override.
- **Static interface methods** gọi qua interface name, không inherited như instance methods.
- **Generic interfaces** có thể được enum implement với type arguments cố định.
- **EnumSet/EnumMap** yêu cầu enum type làm element/key, không chỉ interface type.
- **Enum values()/valueOf** là enum APIs, không thuộc một arbitrary interface.
- **Enum constants là fixed instances**, không tạo thêm bằng `new`.
- **Đa hình qua interface** giúp caller phụ thuộc contract thay vì specific constant.
- **Enum state dùng chung trong thời gian dài**: ưu tiên immutable, chú ý concurrency.
- **getDeclaringClass()** thích hợp xác định enum type khi có constant-specific bodies.
- **Test đầy đủ** mọi constant để bảo đảm behavior hợp đồng.

## 88. Checklist cuối bài

- [ ] Tôi viết được `enum E implements I` đúng cú pháp.
- [ ] Tôi hiểu enum là một class đặc biệt có constants cố định.
- [ ] Tôi biết enum implicitly extends Enum<E>.
- [ ] Tôi biết enum có thể implements nhiều interfaces.
- [ ] Tôi dùng đúng `public` và `@Override` khi implement interface method.
- [ ] Tôi phân biệt method chung và constant-specific overrides.
- [ ] Tôi biết enum abstract method có thể buộc mọi constants implement riêng.
- [ ] Tôi biết interface default method có thể được enum thừa hưởng.
- [ ] Tôi giải quyết được default-method conflict.
- [ ] Tôi biết static interface method không được inherited như instance method.
- [ ] Tôi truyền enum constant qua interface typed method.
- [ ] Tôi phân biệt interface APIs và enum-only APIs.
- [ ] Tôi biết `values()`/`valueOf` chỉ có trên declaring enum type.
- [ ] Tôi biết enum constructors truyền config cho mỗi constant.
- [ ] Tôi không dùng `new` tạo enum objects.
- [ ] Tôi implement được generic Function/Predicate/Comparator interfaces bằng enum.
- [ ] Tôi biết composed Predicate không nhất thiết vẫn là enum constant.
- [ ] Tôi dùng EnumSet<EnumType> và EnumMap<EnumType,V> đúng.
- [ ] Tôi không dùng ordinal như durable external ID.
- [ ] Tôi hiểu `getClass` và `getDeclaringClass` khác nhau với specific bodies.
- [ ] Tôi không override Enum.compareTo/equals/hashCode final methods.
- [ ] Tôi biết enum constants có stable identity.
- [ ] Tôi hiểu enum mutable fields không tự thread-safe.
- [ ] Tôi dùng per-request context thay vì lưu session state trên enum.
- [ ] Tôi biết checked exceptions phải tuân thủ interface contract.
- [ ] Tôi phân biệt finite enum strategy với runtime plugin implementations.
- [ ] Tôi biết khi nào switch rõ hơn constant-specific methods.
- [ ] Tôi test mọi constant và boundary conditions.
- [ ] Tôi có thể dự đoán stdout của các chương trình Java 17+ ở trên.

**Kết luận:** **Enum hiện thực interface** là cách kết hợp một **tập lựa chọn hữu hạn, có tên rõ ràng** với **hợp đồng hành vi đa hình**. Bạn có thể implement method một lần trong enum body, hoặc override theo từng constant-specific class body. Interface cho phép code gọi chung mà không phụ thuộc implementation, trong khi enum cung cấp `values()`, `EnumSet`, `EnumMap` và identity ổn định. Chọn enum strategy cho các lựa chọn domain đóng; chọn named classes/lambda/registry khi behavior cần cấu hình hoặc mở rộng ở runtime. Luôn giữ enum state đơn giản, contract rõ, và kiểm thử behavior của **từng constant**.
