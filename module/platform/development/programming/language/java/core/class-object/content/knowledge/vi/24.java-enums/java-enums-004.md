# Giới hạn tạo đối tượng và kế thừa của enum trong Java

> **Chủ đề:** Java Core → Class/Object → Enum  
> **Trọng tâm:** Giới hạn tạo instance, constructor và kế thừa của enum  
> **Phiên bản sử dụng trong ví dụ:** Java 17+

## 1. Enum là một kiểu class đặc biệt nhưng không phải class thông thường

Trong Java, `enum` (*enumeration class*) biểu diễn một **tập hữu hạn các giá trị có tên**, được công bố bởi những **enum constants** trong chính khai báo enum.

Ví dụ:

~~~java
enum TrafficLight {
    RED, YELLOW, GREEN
}
~~~

`RED`, `YELLOW` và `GREEN` là ba constants của `TrafficLight`. Mỗi constant là một object của một enum type, được khởi tạo theo cơ chế đặc biệt của Java khi class được khởi tạo. Chương trình có thể sử dụng những objects đó, nhưng **không được tự tạo thêm một TrafficLight bằng lệnh `new`**.

Một enum:

- **Không thể được khởi tạo tùy ý** ngoài những constants được khai báo.
- **Không có constructor public/protected** để code bên ngoài gọi.
- **Không thể khai báo `extends SomeClass`**, vì enum đã có superclass đặc biệt `java.lang.Enum<E>`.
- **Không thể làm superclass của một class do người dùng đặt tên** bằng `class Extra extends TrafficLight`.
- **Có thể triển khai interface** với `implements`, thường là cách đúng để tích hợp polymorphism.
- Có thể có **fields, methods, constructors, static members**, và logic riêng cho từng constant.
- Có trường hợp một constant có **class body riêng**; trình biên dịch tạo một anonymous subclass chuyên biệt cho constant đó. Đây là ngoại lệ được **ngôn ngữ kiểm soát**, không phải quyền mở rộng enum bằng những subclass tùy ý.

Điểm quan trọng nhất: **enum tự giới hạn tập instances được phép công bố**, và Java bảo vệ tính chất đó cả ở constructor, type hierarchy và một số cơ chế runtime.

Bài này trình bày những giới hạn ấy, nguyên nhân, các trường hợp biên, cách thiết kế tương đương khi cần extensibility, cùng các chương trình Java 17+ chạy độc lập.

## 2. Tập enum constants được xác định trong source

Với:

~~~java
enum Size {
    SMALL, MEDIUM, LARGE
}
~~~

tập named values của Size là `SMALL`, `MEDIUM`, `LARGE`. Bạn không thể gọi một public factory có sẵn của Java để thêm `EXTRA_LARGE` vào cùng enum ở runtime.

### 2.1. Mỗi constant là một object

~~~java
Size first = Size.SMALL;
Size second = Size.SMALL;
System.out.println(first == second); // true
~~~

`first` và `second` giữ reference tới **cùng enum constant instance**. Phép gán enum reference không clone object.

Khi khai báo:

~~~java
Size selected = Size.MEDIUM;
selected = Size.LARGE;
~~~

bạn chỉ **gán lại biến selected từ một existing constant sang existing constant khác**. Bạn không tạo thêm enum object.

### 2.2. Một enum constant không phải một primitive value

Enum là reference type. Vì thế:

~~~java
Size selected = null;
~~~

có thể hợp lệ tại compile time; `null` **không phải một enum constant mới**. Gọi `selected.name()` khi selected là null sẽ dẫn tới `NullPointerException`.

Điều này quan trọng khi viết validators, database mappings, JSON parsers và APIs nhận optional enum values.

### 2.3. Vì sao cố định số lượng instances lại có ích?

Một tập giá trị được kiểm soát có thể giúp:

- Sử dụng `==` để so identity của các named constants.
- Viết exhaustive `switch` dựa trên các named constants.
- Xây dựng `EnumSet` và `EnumMap` tối ưu cho một enum type.
- Tránh input tạo các trường hợp “lạ” không có trong business rules.
- Định nghĩa logic/metadata tập trung cho từng constant.
- Làm rõ rằng một biến mang loại `TrafficLight` chỉ đại diện RED/YELLOW/GREEN hoặc null, chứ không phải arbitrary subclass do plugins thêm.

**Giới hạn instance** là một feature thiết kế, không chỉ là hạn chế của compiler.

## 3. Cú pháp tạo constants và constructor của enum

Một enum có thể chứa fields và constructor:

~~~java
enum HttpGroup {
    SUCCESS(200, "OK"),
    NOT_FOUND(404, "Missing");

    private final int code;
    private final String label;

    HttpGroup(int code, String label) {
        this.code = code;
        this.label = label;
    }

    int code() {
        return code;
    }

    String label() {
        return label;
    }
}
~~~

Đây là **enum declaration fragment** (chưa có `main`). Các arguments sau constant name, như `SUCCESS(200, "OK")`, được dùng để khởi tạo constant tương ứng thông qua enum constructor.

### 3.1. Constructor được dùng ở đâu?

`SUCCESS(200, "OK")` và `NOT_FOUND(404, "Missing")` là enum constant declarations. Java xử lý việc tạo các instances đó khi enum class initialization diễn ra. Bạn **không** viết `new HttpGroup(200, "OK")`.

### 3.2. Constructor enum không được public/protected

Hợp lệ:

~~~java
enum State {
    STARTED;

    State() {             // Package-access syntax, enum-specific restriction.
    }
}
~~~

và:

~~~java
enum State {
    STARTED;

    private State() {     // Explicitly private.
    }
}
~~~

Hai declarations trên là **những lựa chọn riêng biệt**, không đặt đồng thời trong cùng một source file với cùng tên `State`.

Theo Java, enum constructor chỉ có thể là **private hoặc package-access về mặt khai báo**; nếu không có access modifier, nó được xử lý như constructor private theo rules đặc biệt của enum. Không được khai báo constructor enum là `public` hoặc `protected`.

Cố ý **không biên dịch**:

~~~java
enum InvalidState {
    STARTED;

    public InvalidState() {  // LỖI.
    }
}
~~~

và:

~~~java
enum InvalidState {
    STARTED;

    protected InvalidState() { // LỖI.
    }
}
~~~

Lý do: nếu external code tùy ý gọi constructor, enum sẽ không còn bảo đảm tập giá trị bị giới hạn.

### 3.3. Enum không tự kế thừa constructor từ superclass

Một enum constructor được khai báo như `State()`, `State(int code)`, v.v. Trình biên dịch cung cấp những tham số nội bộ cần thiết cho cơ chế `Enum<E>`, chẳng hạn name/ordinal. Bạn không gọi trực tiếp `super(name, ordinal)` từ enum constructor để biến nó thành class instance creation bình thường.

### 3.4. Các tham số của constructor vẫn hoạt động bình thường

Enum có thể overload constructor với những signature khác nhau:

~~~java
enum Severity {
    LOW(1),
    MEDIUM(2, "Check"),
    HIGH(3, "Urgent");

    private final int weight;
    private final String note;

    Severity(int weight) {
        this(weight, "Normal");
    }

    Severity(int weight, String note) {
        this.weight = weight;
        this.note = note;
    }
}
~~~

Đây là declaration fragment. Constant arguments quyết định constructor overload được chọn theo Java overload resolution. Tuy vậy, **chỉ enum constant declarations** có quyền tạo instances thông qua enum mechanism.

## 4. Giới hạn số lượng instances: không thể dùng `new`

Xem:

~~~java
enum Level {
    LOW, HIGH
}
~~~

Những dòng sau **cố ý không biên dịch**:

~~~java
Level a = new Level();
Level b = new Level("CUSTOM");
Level c = new Level() { };
~~~

Không có cú pháp cho phép một client viết `new Level()` để tạo một enum instance; việc gắn anonymous class body vào `new Level() { ... }` cũng không mở được loophole. Compiler từ chối enum instantiation theo rules của ngôn ngữ.

### 4.1. Không thể khắc phục bằng cách thêm constructor no-arg

Thêm:

~~~java
enum Level {
    LOW, HIGH;

    Level() {
    }
}
~~~

không làm `new Level()` bên ngoài trở thành hợp lệ. Constructor này chỉ tham gia tạo các enum constants.

### 4.2. Không thể khai báo một method thông thường trả object enum mới

Trong enum:

~~~java
static Level makeLow() {
    return LOW;
}
~~~

Hợp lệ vì **trả một constant đã tồn tại**. Nhưng:

~~~java
static Level makeCustom() {
    return new Level(); // LỖI: không thể tạo thêm.
}
~~~

không hợp lệ.

### 4.3. Factory có thể chọn constant, không thêm constant

~~~java
static Level fromWeight(int weight) {
    return weight > 5 ? HIGH : LOW;
}
~~~

Đây là method fragment nằm trong enum `Level`. Factory chỉ chọn giữa các constants có sẵn. Nếu business domain yêu cầu giá trị với arbitrary numeric weight, nên dùng một class/record khác thay vì cố tạo extra enum instances.

## 5. Chương trình hoàn chỉnh 1: identity, `values()` và `valueOf()`

Tạo tệp **`EnumIdentityDemo.java`**:

~~~java
import java.util.Arrays;

public class EnumIdentityDemo {
    enum Color {
        RED, GREEN, BLUE
    }

    public static void main(String[] args) {
        Color one = Color.RED;
        Color two = Color.RED;

        System.out.println("Same constant = " + (one == two));
        System.out.println("All = "
                + Arrays.toString(Color.values()));
        System.out.println("From name = " + Color.valueOf("GREEN"));
        System.out.println("Canonical = "
                + (Color.valueOf("RED") == Color.RED));

        Color[] array = Color.values();
        array[0] = Color.BLUE;

        System.out.println("Enum unchanged = "
                + (Color.values()[0] == Color.RED));
        System.out.println("Different arrays = "
                + (Color.values() != Color.values()));
        System.out.println("RED ordinal = " + Color.RED.ordinal());
    }
}
~~~

Biên dịch và chạy JDK 17+:

~~~bash
javac -encoding UTF-8 EnumIdentityDemo.java
java EnumIdentityDemo
~~~

**Stdout chính xác:**

~~~text
Same constant = true
All = [RED, GREEN, BLUE]
From name = GREEN
Canonical = true
Enum unchanged = true
Different arrays = true
RED ordinal = 0
~~~

### 5.1. `==` là lựa chọn thích hợp cho enum constants

Với references đến cùng enum constant, `==` so identity. Tập constants được kiểm soát giúp so sánh enum bằng identity rõ ràng. `Enum.equals` cũng dựa trên identity và là final.

### 5.2. `values()` không cho sửa tập constants

Compiler cung cấp `Color.values()` để trả về các constants theo **thứ tự khai báo**. Array được trả về có thể được sửa bởi caller, nhưng đó **không phải một API chỉnh sửa tập enum constants**. Demo gán `array[0] = Color.BLUE` rồi gọi `values()` mới; phần tử đầu vẫn là RED.

### 5.3. `valueOf()` không cấp phát instance tùy ý

`Color.valueOf("GREEN")` tra constant có tên chính xác GREEN. Nó không parse một enum mới từ chuỗi và không cho phép arbitrary names. Nếu truyền tên không tồn tại, `valueOf` ném `IllegalArgumentException`; với null name, các API lookup liên quan có thể ném `NullPointerException`.

### 5.4. `ordinal()` dùng làm gì?

`ordinal()` phản ánh vị trí constant trong thứ tự khai báo, bắt đầu từ 0. `RED.ordinal() == 0` trong ví dụ. Đây là chi tiết theo declaration order, **không nên dùng làm ID lưu trong database hoặc external protocol** vì thay thứ tự/chen constants có thể đổi ordinal.

## 6. Enum ngầm kế thừa `java.lang.Enum<E>`

Mỗi enum `E` có supertype đặc biệt `java.lang.Enum<E>` theo Java language rules. Đây là một generic abstract base class cung cấp API chung:

- `name()` — tên khai báo của constant.
- `ordinal()` — thứ tự khai báo.
- `compareTo(E other)` — so thứ tự enum natural order.
- `getDeclaringClass()` — enum class đã khai báo constant.
- `toString()` — mặc định tên, nhưng có thể override.
- `equals(Object)`, `hashCode()` — identity-based, final.
- Hỗ trợ cơ chế serialization được quy định riêng cho enums.

Một enum không thể chọn superclass khác.

### 6.1. Không được viết `extends` trong enum declaration

Cố ý **không biên dịch**:

~~~java
class Base {
}

enum Status extends Base {  // LỖI: enum declaration không có extends clause.
    READY
}
~~~

Cũng không hợp lệ:

~~~java
enum Status extends java.lang.Enum<Status> {
    READY
}
~~~

`Status` đã có superclass đặc biệt do ngôn ngữ quy định. Không cần và không được tự ghi `extends Enum<Status>`.

### 6.2. Vì sao Java không hỗ trợ multiple class inheritance ở đây?

Java classes có một superclass trong class hierarchy. Enum class đã có `Enum<E>` như superclass, nên không thể đồng thời kế thừa custom class như `BaseEntity` hay `AbstractStatus`.

Nếu cần chia sẻ một **contract** giữa enum và ordinary class, dùng interface. Nếu cần reuse behavior, dùng static utility, composition, default interface method phù hợp hoặc một business service.

### 6.3. Không được trực tiếp extends `Enum<E>` bằng ordinary class

Cố ý **không biên dịch**:

~~~java
class FakeStatus extends Enum<FakeStatus> {
    FakeStatus(String name, int ordinal) {
        super(name, ordinal);
    }
}
~~~

Dù `Enum` có protected constructor như một phần API cho cơ chế compiler, Java cấm user-defined class trực tiếp extends `java.lang.Enum`. Không thể dùng ordinary subclass để tạo một giá trị enum “thủ công”.

### 6.4. Một enum không thể extend enum khác

Cố ý **không biên dịch**:

~~~java
enum Weekday {
    MONDAY, TUESDAY
}

enum Holiday extends Weekday {
    CHRISTMAS
}
~~~

Không có inheritance hierarchy kiểu `Weekday <- Holiday` cho two enum declarations.

Nếu hai enums cần chia sẻ semantics, cả hai có thể implement cùng interface; client dùng interface type khi muốn polymorphism.

## 7. Người dùng không thể subclass một enum class

Giả sử:

~~~java
enum State {
    ACTIVE, INACTIVE
}
~~~

Bạn không thể viết:

~~~java
class SpecialState extends State { // LỖI.
}
~~~

Không được có ordinary named subclass của State. Điều này loại bỏ khả năng runtime xuất hiện một arbitrary subtype mà declaration của enum không kiểm soát.

### 7.1. Không thể dùng anonymous subclass từ bên ngoài

Cũng không hợp lệ:

~~~java
State extra = new State() {
};
~~~

Không thể tạo enum instance bằng `new`, nên không thể “lách” thông qua anonymous class body trong normal class instance creation syntax.

### 7.2. Thế `enum` luôn final theo nghĩa kỹ thuật?

Có một ngoại lệ quan trọng cần hiểu đúng từ Java language rules.

- Nếu **không** có enum constant nào khai báo class body riêng, enum class là **implicitly final**.
- Nếu **có ít nhất một constant-specific class body**, enum class là **implicitly sealed** theo quy tắc enum trong Java 17. Những direct subclasses được phép chỉ là **anonymous classes được tạo bởi compiler cho các enum constants có class bodies**.

Đây **không phải** cơ chế để developer tự khai báo `class Extra extends State`; tập permitted direct subclasses bị giới hạn theo enum declarations.

### 7.3. Không được gắn modifiers tùy ý để mở rộng enum

Không có API source-level như `non-sealed enum E` cho phép plugins thêm constants. Enum-specific final/sealed semantics do Java định nghĩa. Không dùng `permits` để mở rộng danh sách arbitrary descendants của một enum.

### 7.4. Runtime class có thể khác declaring enum class

Khi một constant có class body, `constant.getClass()` có thể là một anonymous subtype, nhưng `constant.getDeclaringClass()` vẫn trả về enum class khai báo constant. Đây là một nuance quan trọng nếu code dùng reflection/introspection.

## 8. Constant-specific class body: ngoại lệ do compiler kiểm soát

Java cho phép mỗi enum constant có class body:

~~~java
enum Operation {
    ADD {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    MULTIPLY {
        @Override
        int apply(int a, int b) {
            return a * b;
        }
    };

    abstract int apply(int a, int b);
}
~~~

Đây là declaration fragment. `ADD` và `MULTIPLY` có anonymous class bodies riêng; chúng override `apply` để cung cấp behavior khác nhau. Java compiler tạo các constant-specific subclasses theo language rules.

### 8.1. Vì sao vẫn không thể tạo subclass tùy ý?

Chỉ **enum constants nằm trong khai báo enum** được dùng kiểu constant-specific class body này. Bạn không thể đưa code từ bên ngoài đến một statement kiểu `new Operation() { ... }` hoặc `class Custom extends Operation`.

Tức là enum hỗ trợ **variation of behavior across a fixed set of constants**, chứ không hỗ trợ **open-ended inheritance by clients**.

### 8.2. Abstract instance method trong enum

Enum có thể khai báo abstract instance method như `abstract int apply(...)`, nhưng phải bảo đảm mỗi constant cung cấp concrete implementation thông qua class body theo Java requirements.

Cố ý không biên dịch:

~~~java
enum BrokenOperation {
    PLUS {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    MISSING;

    abstract int apply(int a, int b);
}
~~~

`MISSING` không có implementation cho abstract method. Compiler từ chối.

### 8.3. Có thể override method không abstract

Không nhất thiết mọi constant phải có class body. Enum có thể cung cấp default instance method và một constant override nó:

~~~java
enum Priority {
    LOW,
    HIGH {
        @Override
        String label() {
            return "urgent";
        }
    };

    String label() {
        return "normal";
    }
}
~~~

`LOW` dùng behavior mặc định; `HIGH` dùng behavior override. Vì HIGH có class body, enum có constant-specific anonymous subclass, nhưng không có named external subclass được phép.

### 8.4. `getClass()` và `getDeclaringClass()`

`Priority.LOW.getClass() == Priority.class` thường true vì LOW không có constant body. `Priority.HIGH.getClass() == Priority.class` false vì HIGH có body; nhưng `Priority.HIGH.getDeclaringClass() == Priority.class` vẫn true.

Khi muốn biết **enum type khai báo constant**, ưu tiên `getDeclaringClass()` thay vì giả định `getClass()` luôn là enum class.

## 9. Chương trình hoàn chỉnh 2: constant-specific subclass và interfaces

Tạo tệp **`EnumConstantBodyDemo.java`**:

~~~java
public class EnumConstantBodyDemo {
    interface BinaryRule {
        int apply(int a, int b);
    }

    enum Operation implements BinaryRule {
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

        public abstract int apply(int a, int b);
    }

    static int calculate(BinaryRule rule, int a, int b) {
        return rule.apply(a, b);
    }

    public static void main(String[] args) {
        System.out.println("ADD = "
                + Operation.ADD.apply(3, 4));
        System.out.println("MULTIPLY = "
                + calculate(Operation.MULTIPLY, 3, 4));

        System.out.println("Constant body class equals enum = "
                + (Operation.ADD.getClass() == Operation.class));
        System.out.println("Declaring enum = "
                + Operation.ADD.getDeclaringClass().getSimpleName());
        System.out.println("Both are enum constants = "
                + (Operation.values().length == 2));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumConstantBodyDemo.java
java EnumConstantBodyDemo
~~~

**Stdout chính xác:**

~~~text
ADD = 7
MULTIPLY = 12
Constant body class equals enum = false
Declaring enum = Operation
Both are enum constants = true
~~~

### 9.1. Đây là inheritance như thế nào?

Runtime class của `Operation.ADD` là constant-specific anonymous subclass do compiler tạo, **không** phải một tên mà developer có thể extends. Cả two constants vẫn thuộc tập enum constants cố định.

### 9.2. Vì sao interface mang lại polymorphism?

`BinaryRule` là interface. `Operation` triển khai BinaryRule, nên `calculate(BinaryRule rule, ...)` nhận enum constant thông qua interface type. Behavior `apply` khác nhau theo constant.

Khi muốn hệ thống có thêm một cách tính toán không phải enum constant, bạn có thể tạo một **ordinary class implements BinaryRule**, mà không cần hoặc không thể extends Operation.

### 9.3. Không xem enum constant body là public constructor

Không có operation nào trong demo tạo một ADD2 hoặc MULTIPLY2 mới. `values().length` vẫn là 2. Constant-specific body chỉ xác định behavior của một trong các constants đã được khai báo.

## 10. Interface là cách mở rộng hành vi hợp lệ

Java enum **có thể implement interfaces**:

~~~java
interface HasCode {
    int code();
}

enum Result implements HasCode {
    OK(200),
    ERROR(500);

    private final int code;

    Result(int code) {
        this.code = code;
    }

    @Override
    public int code() {
        return code;
    }
}
~~~

Đây là declaration fragment.

### 10.1. Một enum có thể implement nhiều interfaces

~~~java
enum Action implements Runnable, java.io.Serializable {
    EXECUTE;

    @Override
    public void run() {
        System.out.println("execute");
    }
}
~~~

Ví dụ trên hợp lệ về interface declarations; thêm `Serializable` thường thừa vì enums vốn có specialized serialization semantics, nhưng minh họa `implements`. Thường chỉ implement interface có ý nghĩa trong domain.

### 10.2. Interface không thêm enum constants

`Result implements HasCode` nghĩa là Result thỏa contract `HasCode.code()`. Nó không cho phép một class khác extends Result hoặc thêm `OTHER` vào Result.

Một ordinary class cũng có thể implement HasCode:

~~~java
record CustomResult(int code) implements HasCode {
}
~~~

Nhờ đó API nhận `HasCode` có thể chấp nhận both enum constants và các custom implementations.

### 10.3. Chọn interface để giữ code extensible

Nếu yêu cầu là “hệ thống có nhiều providers/plugins thêm status implementations mới”, enum không phù hợp làm root extensibility type. Interface hoặc abstract class có thể phù hợp hơn; enum vẫn có thể là một implementation chứa tập built-in values.

**Phân biệt mở rộng hành vi qua interface với mở rộng tập instances của chính enum.**

## 11. Chương trình hoàn chỉnh 3: enum cùng ordinary class implement interface

Tạo tệp **`EnumInterfaceExtensionDemo.java`**:

~~~java
import java.util.List;

public class EnumInterfaceExtensionDemo {
    interface HasCode {
        int code();
    }

    enum BuiltinStatus implements HasCode {
        READY(1),
        FAILED(2);

        private final int code;

        BuiltinStatus(int code) {
            this.code = code;
        }

        @Override
        public int code() {
            return code;
        }
    }

    record CustomStatus(int code) implements HasCode {
    }

    static String format(HasCode value) {
        return "code=" + value.code();
    }

    public static void main(String[] args) {
        List<HasCode> statuses = List.of(
                BuiltinStatus.READY,
                new CustomStatus(9),
                BuiltinStatus.FAILED);

        for (HasCode status : statuses) {
            System.out.println(format(status));
        }

        System.out.println("Built-in count = "
                + BuiltinStatus.values().length);
        System.out.println("Custom is built-in enum = "
                + (statuses.get(1) instanceof BuiltinStatus));
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 EnumInterfaceExtensionDemo.java
java EnumInterfaceExtensionDemo
~~~

**Stdout chính xác:**

~~~text
code=1
code=9
code=2
Built-in count = 2
Custom is built-in enum = false
~~~

### 11.1. Cách giữ API mở rộng được

`CustomStatus` là một record implements HasCode, không phải subclass of BuiltinStatus. Method `format(HasCode)` xử lý cả enum và record qua interface.

### 11.2. Tập enum constants không đổi

Dù List có ba HasCode objects, `BuiltinStatus.values().length` vẫn là 2. Giá trị CustomStatus(9) không trở thành enum constant mới.

### 11.3. Có thể dùng sealed interface để kiểm soát tập implementations

Java 17 hỗ trợ sealed classes/interfaces. Khi cần một hierarchy vừa có nhiều implementations vừa giới hạn rõ permitted types, có thể khai báo `sealed interface` với danh sách types permitted hợp lệ. Enum có thể là một implementation của sealed interface, nhưng **đây vẫn không phải enum kế thừa enum khác**.

Ví dụ ý tưởng:

~~~java
sealed interface Message permits OkMessage, ErrorMessage {
}

record OkMessage() implements Message {
}

record ErrorMessage() implements Message {
}
~~~

Đây là fragment Java 17 hợp lệ khi các top-level types trong cùng source context được khai báo phù hợp. Sealed interface cho phép nhiều implementation types theo permits; enum giữ một tập constants của chính nó.

## 12. Chương trình hoàn chỉnh 4: constructor parameters và lookup table

Tạo tệp **`EnumConstructorLookupDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class EnumConstructorLookupDemo {
    enum Phase {
        NEW(10, "New"),
        RUNNING(20, "Running"),
        DONE(30, "Done");

        private final int code;
        private final String label;

        private static final Map<Integer, Phase> BY_CODE;

        static {
            Map<Integer, Phase> map = new HashMap<>();
            for (Phase phase : values()) {
                map.put(phase.code, phase);
            }
            BY_CODE = Map.copyOf(map);
        }

        Phase(int code, String label) {
            this.code = code;
            this.label = label;
        }

        int code() {
            return code;
        }

        String label() {
            return label;
        }

        static Phase fromCode(int code) {
            Phase value = BY_CODE.get(code);
            if (value == null) {
                throw new IllegalArgumentException("Unknown code");
            }
            return value;
        }
    }

    public static void main(String[] args) {
        System.out.println("By code 20 = " + Phase.fromCode(20));
        System.out.println("NEW label = " + Phase.NEW.label());
        System.out.println("Count = " + Phase.values().length);
        System.out.println("Code DONE = " + Phase.DONE.code());

        try {
            Phase.fromCode(99);
        } catch (IllegalArgumentException ex) {
            System.out.println("Unknown rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 EnumConstructorLookupDemo.java
java EnumConstructorLookupDemo
~~~

**Stdout chính xác:**

~~~text
By code 20 = RUNNING
NEW label = New
Count = 3
Code DONE = 30
Unknown rejected
~~~

### 12.1. Constructor chỉ chạy cho declared constants

`Phase.NEW`, `RUNNING`, `DONE` nhận các code/label tương ứng. Call `fromCode(20)` tìm constant RUNNING có sẵn; nó không gọi constructor để tạo Phase mới.

### 12.2. Vì sao tạo Map sau khi constants đã được khởi tạo?

Enum constant declarations được xử lý trước các static fields/blocks thông thường trong enum class initialization order. Static block trong demo duyệt `values()` để xây lookup map sau khi constants đã sẵn sàng.

Java có **restriction đặc biệt**: constructor, instance initializer hoặc instance variable initializer của enum không được tham chiếu trực tiếp đến một static field của chính enum, trừ khi field ấy là constant variable. Quy tắc này giúp tránh một lớp lỗi initialization order.

Cố ý **không biên dịch**:

~~~java
enum Broken {
    A;

    static int count;

    Broken() {
        count++; // Illegal reference to static field from enum initializer.
    }
}
~~~

Thay vì làm vậy, xây computed static lookup sau khi constants được khởi tạo, hoặc quản lý mutable state trong external holder/service được thiết kế rõ.

### 12.3. Không dùng `ordinal` làm business code

Demo lưu `code=10/20/30` độc lập với position 0/1/2. Một external code/DB ID nên giữ stable theo contract; ordinal có thể đổi khi các constants được reorder. Dùng một explicit field và parser/lookup giống ví dụ khi cần persistence.

### 12.4. Kiểm tra duplicate code

Một production lookup cần xác định policy nếu hai constants có cùng code. `Map.put` đơn giản sẽ overwrite mapping trước. Có thể phát hiện duplicate bằng `putIfAbsent` rồi ném exception trong static initialization, hoặc dùng validation khác; điều này thuộc business invariant của enum, không liên quan quyền tạo enum object.

## 13. Reflection có tạo enum instances mới được không?

**Không theo public reflection API dùng `Constructor.newInstance`.** Java reflection kiểm tra và từ chối thao tác tạo enum object qua cơ chế này, kể cả khi code cố lấy constructor của enum.

Một số người nhìn thấy enum có constructor trong bytecode và cho rằng có thể dùng reflection để gọi nó như ordinary private constructor. Cách suy luận đó sai: **enum có runtime-level restrictions chuyên biệt**.

### 13.1. Vì sao không dùng reflection để thêm constants?

- `getEnumConstants()` và `values()` cung cấp **declared constants**.
- `Constructor.newInstance` không cho phép tạo enum instance mới.
- Tập constants của enum được compiler/runtime quản lý.
- Dùng unsafe internal/unsupported hacks có thể phá assumptions của JDK/frameworks và không phải Java language feature hay API ổn định.

**Không cần và không nên sử dụng các mẹo phá enum invariants** để triển khai custom statuses. Nếu cần runtime extensibility, dùng interface/registry hoặc một value class khác.

### 13.2. Không suy từ API `Class.newInstance()` cũ

Một số reflection APIs cũ bị deprecate hoặc có accessibility limitations. Chúng không biến enum thành một ordinary class có public no-args constructor. Việc có reflection không thay đổi type rules đối với enum.

### 13.3. Reflection vẫn có ích để *đọc* metadata

~~~java
System.out.println(Color.class.isEnum());
System.out.println(java.util.Arrays.toString(
        Color.class.getEnumConstants()));
~~~

Đây là fragment khi enum Color có sẵn. Reflection có thể kiểm tra enum type và các constants, nhưng không trao quyền bổ sung constants mới.

## 14. Clone và serialization: identity của enum được bảo vệ

Một enum constant khác ordinary mutable class object ở một số behavior của Java runtime.

### 14.1. `clone()` không tạo enum constant mới

`java.lang.Enum` cung cấp behavior ngăn cloning enum objects như một cách tạo arbitrary instances. Không thể dùng `someEnum.clone()` từ user code để nhân đôi một constant; method cloning liên quan của Enum có restricted/final semantics.

### 14.2. Java serialization có xử lý enum riêng

Với **Java native serialization**, enum được serialize/deserialized bằng cơ chế đặc biệt dựa trên enum type và constant name, không theo cách tạo arbitrary object state qua ordinary constructor. Khi đọc lại một valid serialized enum constant, runtime trả canonical constant tương ứng, thay vì tạo một enum instance mới tách biệt.

Điều này giúp identity `==` tiếp tục có ý nghĩa với enum trong cùng runtime class-loading context.

### 14.3. Serialization không tự bảo đảm mọi tương thích qua versions

Nếu constant name thay đổi hoặc bị xóa, deserialization của dữ liệu cũ có thể thất bại. Không nên xem enum serialized form hoặc ordinal như một external protocol được version độc lập. Khi lưu dữ liệu lâu dài, hãy quản lý stable codes/migration.

### 14.4. Enum không tự bất biến toàn bộ state

Mặc dù **set constants cố định**, enum class vẫn có thể chứa **mutable fields**. Cơ chế serialization enum không biến các mutable fields đó thành immutable data. Những fields đó còn có concurrency và lifecycle considerations riêng.

## 15. Chương trình hoàn chỉnh 5: serialization giữ canonical enum constant

Tạo tệp **`EnumSerializationDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

public class EnumSerializationDemo {
    enum Priority {
        LOW, HIGH
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes;

        try (ByteArrayOutputStream buffer =
                     new ByteArrayOutputStream();
             ObjectOutputStream output =
                     new ObjectOutputStream(buffer)) {
            output.writeObject(Priority.HIGH);
            output.flush();
            bytes = buffer.toByteArray();
        }

        Priority restored;
        try (ObjectInputStream input =
                     new ObjectInputStream(
                             new ByteArrayInputStream(bytes))) {
            restored = (Priority) input.readObject();
        }

        System.out.println("Restored = " + restored);
        System.out.println("Same constant = "
                + (restored == Priority.HIGH));
        System.out.println("Values count = "
                + Priority.values().length);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumSerializationDemo.java
java EnumSerializationDemo
~~~

**Stdout chính xác:**

~~~text
Restored = HIGH
Same constant = true
Values count = 2
~~~

Đọc qua `ObjectInputStream` không tạo constant thứ ba. `restored` tham chiếu đúng canonical Priority.HIGH constant khi deserialization diễn ra trong một class-loading context tương thích.

## 16. Enum final/sealed không đồng nghĩa immutable fields

Một hiểu lầm: “enum không cho new và không cho subclass nên mọi field của enum chắc chắn immutable”.

Điều này **không đúng**. Enum constants có fixed identity nhưng có thể có mutable fields:

~~~java
enum SessionCounter {
    INSTANCE;

    private int total;

    synchronized int next() {
        return ++total;
    }
}
~~~

`SessionCounter.INSTANCE` là một enum constant, nhưng `total` thay khi `next()` chạy.

### 16.1. Chương trình hoàn chỉnh 6: enum object có mutable field

Tạo tệp **`EnumMutableStateDemo.java`**:

~~~java
public class EnumMutableStateDemo {
    enum TicketCounter {
        SINGLE;

        private int issued;

        synchronized int issue() {
            return ++issued;
        }

        synchronized int issued() {
            return issued;
        }
    }

    public static void main(String[] args) {
        TicketCounter a = TicketCounter.SINGLE;
        TicketCounter b = TicketCounter.SINGLE;

        System.out.println("Same object = " + (a == b));
        System.out.println("First = " + a.issue());
        System.out.println("Second = " + b.issue());
        System.out.println("Total = " + a.issued());
        System.out.println("Constant count = "
                + TicketCounter.values().length);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumMutableStateDemo.java
java EnumMutableStateDemo
~~~

**Stdout chính xác:**

~~~text
Same object = true
First = 1
Second = 2
Total = 2
Constant count = 1
~~~

### 16.2. Vì sao có mutable state mà vẫn là enum?

`a` và `b` trỏ cùng TicketCounter.SINGLE constant. `issued` thay từ 0→1→2, nhưng vẫn chỉ có **một enum constant instance**. Không có tạo thêm TicketCounter object nào.

### 16.3. Cẩn thận với mutable enum singleton

Mutable fields trong enum thường là **shared state**, nên cần thread-safety và test isolation. Nếu enum đại diện fixed labels/states của business logic, giữ nó immutable (final fields, immutable nested data) thường đơn giản hơn. Nếu dùng enum singleton cho một service, vẫn phải thiết kế synchronization, lifecycle và dependency management.

## 17. `values()`, `valueOf()` và `name()` không phải factories tạo mới

Một enum compiler thường cung cấp các API:

| API | Vai trò | Có tạo enum instance mới không? |
| --- | --- | --- |
| `E.values()` | Trả array chứa references tới declared constants theo declaration order | Không |
| `E.valueOf(String)` | Tra constant theo exact declared name | Không |
| `Enum.valueOf(E.class, name)` | Tra constant theo enum class và name | Không |
| `constant.name()` | Trả declared identifier name | Không |
| `constant.ordinal()` | Trả position của constant | Không |
| `constant.getDeclaringClass()` | Trả enum class khai báo constant | Không |
| `constant.toString()` | Trả string representation, có thể overridden | Không |

### 17.1. `values()` có thể tạo array mới, không phải enum object mới

Câu “`values()` không tạo mới” cần nói chính xác: method thường tạo/trả một **array object mới** chứa references đến các **same enum constant instances**. Array là mutable container, còn enum constants không được thêm/xóa qua array đó.

### 17.2. `name()` và `toString()` khác nhau

Mặc định `toString()` trả name. Nhưng một enum có thể override toString để hiển thị label thân thiện; `name()` vẫn là declared constant name. Khi lưu stable identifier, cần cân nhắc explicit code field, vì đổi enum constant name ảnh hưởng persisted strings.

### 17.3. `valueOf()` phân biệt chữ hoa/chữ thường

`Mode.valueOf("READ")` tìm constant tên READ; `"read"` không được tự canonicalize. Nếu input case-insensitive, phải normalize có chủ đích và bắt invalid values theo domain policy.

### 17.4. Không dùng ordinal làm external key

Thêm một constant ở đầu enum thay đổi ordinals của constants sau. Nên sử dụng name hoặc stable code field phù hợp với requirement phiên bản dữ liệu, không viết database records dựa trên ordinal như một ID bất biến.

## 18. Switch expression và sự hữu ích của tập enum cố định

Java 17 cho phép `switch` expressions với enum constants:

~~~java
static String nextAction(TrafficLight light) {
    return switch (light) {
        case RED -> "stop";
        case YELLOW -> "slow";
        case GREEN -> "go";
    };
}
~~~

Đây là method fragment với enum TrafficLight đã có sẵn. Các cases bao phủ đủ constants, compiler có thể đánh giá switch expression là exhaustive.

### 18.1. Khi thêm constant mới trong source

Nếu sau này thêm `BLINKING` vào TrafficLight mà không cập nhật switch expression không có default, việc biên dịch lại có thể yêu cầu bổ sung case để đủ exhaustive. Đây là lợi ích từ tập values rõ ràng: người viết code được nhắc xét trường hợp mới.

### 18.2. Null không phải enum constant

Với switch expression trong Java 17, truyền null không tự khớp bất kỳ enum case bình thường nào và có thể gây NullPointerException. Nếu API cho phép null, validate null trước hoặc xử lý theo contract phù hợp.

### 18.3. Switch không cho runtime extension enum

Không thể “inject” một enum constant mới để gây một case ngoài tập đã khai báo theo Java source/runtime rules thông thường. Tuy vậy có thể **nâng phiên bản enum library** để thêm named constant mới; source compatibility và exhaustive switches cần được xem xét lúc build/deploy.

## 19. EnumSet và EnumMap dựa trên enum type cố định

Java cung cấp:

- `EnumSet<E extends Enum<E>>` — Set chuyên dụng cho enum constants của một enum type.
- `EnumMap<K extends Enum<K>, V>` — Map chuyên dụng sử dụng enum constants làm keys.

Chúng được thiết kế dựa trên tập constants đã được định nghĩa. Không thể thêm một “dynamic enum key” ngoài enum declaration vào cùng enum type.

### 19.1. Chương trình hoàn chỉnh 7: switch, EnumSet, EnumMap

Tạo tệp **`EnumCollectionsDemo.java`**:

~~~java
import java.util.EnumMap;
import java.util.EnumSet;

public class EnumCollectionsDemo {
    enum Permission {
        READ, WRITE, EXECUTE
    }

    static String action(Permission permission) {
        return switch (permission) {
            case READ -> "inspect";
            case WRITE -> "edit";
            case EXECUTE -> "run";
        };
    }

    public static void main(String[] args) {
        EnumSet<Permission> allowed =
                EnumSet.of(Permission.WRITE, Permission.READ);

        EnumMap<Permission, Integer> weight =
                new EnumMap<>(Permission.class);
        weight.put(Permission.EXECUTE, 3);
        weight.put(Permission.READ, 1);
        weight.put(Permission.WRITE, 2);

        System.out.println("Allowed = " + allowed);
        System.out.println("Weights = " + weight);
        System.out.println("READ action = "
                + action(Permission.READ));
        System.out.println("Contains EXECUTE = "
                + allowed.contains(Permission.EXECUTE));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 EnumCollectionsDemo.java
java EnumCollectionsDemo
~~~

**Stdout chính xác:**

~~~text
Allowed = [READ, WRITE]
Weights = {READ=1, WRITE=2, EXECUTE=3}
READ action = inspect
Contains EXECUTE = false
~~~

### 19.2. Vì sao EnumSet/EnumMap in đúng thứ tự?

`EnumSet` và `EnumMap` có iteration order theo **natural enum order**, tức declaration order. Vì Permission khai báo READ, WRITE, EXECUTE, output mang thứ tự này, dù insertion order khác. Đây không phải ngẫu nhiên theo HashMap.

### 19.3. Không trộn enum types

Một `EnumSet<Permission>` không chấp nhận arbitrary enum constant của một enum class khác như một element typed hợp lệ. `EnumMap` key cũng bị giới hạn vào một enum type được cung cấp lúc tạo map. Nếu cần một collection kết hợp nhiều domains, có thể dùng interface/record key abstraction khác.

### 19.4. Các enum collections không làm enum constants immutable

Nếu constant giữ mutable fields, collection vẫn chứa reference tới chính constant đó. EnumSet/EnumMap tối ưu membership và mapping, không bảo vệ thread safety hay state trong enum constants.

## 20. Enum constant class body và phép `getClass()`

Khi không có class body:

~~~java
enum Simple {
    A, B
}
~~~

Các constants thường có runtime class đúng enum class Simple. Với class body:

~~~java
enum Complex {
    A {
        @Override
        String text() {
            return "A!";
        }
    },
    B;

    String text() {
        return name();
    }
}
~~~

`Complex.A` có một constant-specific anonymous subclass runtime class, còn `Complex.B` không có subclass body. Không cần và không được viết class named extends Complex.

### 20.1. Cách kiểm tra type an toàn

Nếu cần biết constant thuộc enum nào, gọi `value.getDeclaringClass()` thay vì dựa vào `value.getClass()`. Với `Complex.A`, hai Class objects có thể khác, dù value vẫn là Complex constant.

### 20.2. Không suy ra subclass mới từ tên như `Complex$1`

Compiler có thể tạo class files có tên như `Complex$1` cho constant-specific bodies, nhưng naming/details là compiler implementation artifact. Không hard-code tên synthetic subclasses trong logic business hoặc reflection tests.

### 20.3. Khi dùng `getClass()` trong equals/type checks

Enum.equals final dùng identity nên không gặp vấn đề custom equals dựa trên getClass. Nhưng custom helper/reflection code có thể nhầm nếu yêu cầu `constant.getClass() == SomeEnum.class` cho mọi constant. Dùng `getDeclaringClass()` khi ý nghĩa là “declared enum class”.

## 21. Giới hạn constructor, superclass và methods kế thừa

Một enum có thể khai báo regular instance methods và override những methods được phép, nhưng không override các `final` methods của `java.lang.Enum`:

- `name()`: final.
- `ordinal()`: final.
- `equals(Object)`: final.
- `hashCode()`: final.
- `compareTo(E)`: final.
- `getDeclaringClass()`: final.

Ví dụ cố ý **không biên dịch**:

~~~java
enum Invalid {
    A;

    @Override
    public String name() {
        return "custom";
    }
}
~~~

`name()` không được override. Nếu cần display name, tạo method `displayName()` hoặc override `toString()` nếu muốn, với awareness về serialization/logging conventions.

### 21.1. `toString()` có thể được override

~~~java
enum Priority {
    LOW, HIGH;

    @Override
    public String toString() {
        return "Priority:" + name();
    }
}
~~~

Đây là declaration fragment hợp lệ. Tuy nhiên `Priority.LOW.name()` vẫn là `"LOW"`; không thể override name().

### 21.2. Constructors cũng không là inherited instance methods

Enum constructors tạo constants nội bộ; client không thể chọn constructor overload để instantiate arbitrary value. Việc enum có constructor có tham số **không làm enum thành một factory mở**.

### 21.3. Các methods inherited khác vẫn có contract

Enum là object nên cũng có APIs từ Object và Enum. Nhưng enum's identity/equality/ordering semantics được giới hạn để hoạt động ổn định với tập constants. Nếu bạn muốn một object tự có value-based equals/hash tùy nội dung thay đổi, enum thường không phải abstraction phù hợp.

## 22. Enum types có thể là nested members

Khi một enum được khai báo là **member của một class/interface**, nó **implicitly static** theo Java rules.

~~~java
class Application {
    enum Mode {
        DEV, PROD
    }
}
~~~

Nếu accessibility cho phép, bạn có thể dùng `Application.Mode.PROD` mà không cần tạo Application instance. Đây là **nested enum type**, không phải inner-class instance type cần `outer.new Inner()`.

### 22.1. Nested enum vẫn không được thêm instances

Việc là nested enum không thay đổi các constraints: không `new Application.Mode()` và không `class Custom extends Application.Mode`.

### 22.2. Member enum không có implicit enclosing instance

Vì member enum implicitly static, enum constructor/instance methods không được tự dùng `Application.this` như non-static member inner class. Nếu cần context data, truyền dữ liệu vào service method, hoặc dùng một context holder ngoài enum.

### 22.3. Đừng gắn enum vào từng instance owner khi muốn per-owner state

Nếu mỗi Application instance cần danh sách Mode tùy chỉnh, enum không đáp ứng runtime dynamic values. Có thể lưu List/Set của enum constants được hỗ trợ trên từng Application, hoặc dùng một domain class có configurable values.

## 23. Khi nào không nên dùng enum?

Không nên cố dùng enum nếu requirement là:

1. User tạo giá trị mới trong runtime.
2. Plugins thêm implementations hoặc action types không biết khi compile.
3. Giá trị từ database có thể mở rộng độc lập với deploy source code.
4. Mỗi instance cần arbitrary state và custom identity.
5. Nhiều subclasses cần kế thừa một base class tùy chỉnh.
6. Một object cần nhiều lifecycle/resource dependencies.
7. Bạn muốn deserialize một ID bất kỳ thành một object mới của cùng enum type.

Trong những tình huống đó, cân nhắc:

- **Record/value class** cho data values có thể tạo linh hoạt.
- **Interface** cho polymorphism/open implementations.
- **Abstract class** cho behavior sharing khi Java class inheritance phù hợp.
- **Sealed interface/class** để giới hạn variants nhưng với các representation types do bạn tự định nghĩa.
- **Registry/Map<String,Handler>** khi cần dynamic extensions.
- **Enum + metadata/business configuration** nếu tập enum types cố định nhưng cấu hình theo user khác nhau.

### 23.1. Phân biệt closed enum và open registry

Enum phù hợp khi tập values cố định theo mỗi version của code. Open registry phù hợp khi extensions được đăng ký lúc chạy.

Đừng tạo một enum constant giả như `CUSTOM` rồi nhồi mọi runtime custom value vào một mutable field của singleton CUSTOM nếu mỗi custom value cần independent identity. Một record `CustomType(String id)` và interface contract có thể rõ nghĩa hơn.

### 23.2. Khi cần type-safe values động

Một record:

~~~java
record StatusCode(String value) {
    StatusCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Invalid code");
        }
    }
}
~~~

có thể cho client tạo `new StatusCode("SCHEDULED")`, `new StatusCode("PAUSED")`. Đây là value type extensible bởi data, khác enum fixed constants. Validation/invariants phải do class này tự đảm nhiệm.

### 23.3. Khi cần mixed built-in và custom cases

Một interface `StatusLike` có thể được implement bởi enum BuiltinStatus và record CustomStatus. API nhận StatusLike sẽ không bị buộc chỉ nhận named enum constants; nhưng cũng mất một số guarantees/exhaustive switch của enum-only type. Chọn trade-off theo domain.

## 24. Lỗi compiler và runtime thường gặp

### 24.1. Lỗi: `new MyEnum()`

**Nguyên nhân:** enum instantiation bị cấm.  
**Cách sửa:** dùng `MyEnum.EXISTING_CONSTANT`, `valueOf` hoặc factory chọn constant; nếu cần instance mới, dùng class/record.

### 24.2. Lỗi: enum constructor public/protected

**Nguyên nhân:** enum constructor accessibility bị giới hạn.  
**Cách sửa:** dùng private hoặc omit modifier và truyền arguments trong constant declarations.

### 24.3. Lỗi: `enum X extends Base`

**Nguyên nhân:** enum không có custom extends clause vì ngầm extends Enum<X>.  
**Cách sửa:** implements interface hoặc dùng ordinary class hierarchy nếu cần extends Base.

### 24.4. Lỗi: `class Y extends X` với X là enum

**Nguyên nhân:** không được tự tạo named subclass của enum.  
**Cách sửa:** định nghĩa behavior constant-specific **trong enum** hoặc dùng interface/ordinary class.

### 24.5. Lỗi: `class Y extends Enum<Y>`

**Nguyên nhân:** chỉ compiler-generated enum type hợp lệ theo special language rules.  
**Cách sửa:** không subclass trực tiếp java.lang.Enum.

### 24.6. Lỗi: enum abstract method không được tất cả constants cài đặt

**Nguyên nhân:** một constant không có concrete implementation.  
**Cách sửa:** cho mỗi constant body implement method hoặc cung cấp default concrete method trong enum.

### 24.7. Lỗi: truy cập nonconstant static field từ enum constructor

**Nguyên nhân:** enum initialization order rule.  
**Cách sửa:** xây static lookup sau constants trong static initializer, dùng explicit immutable constant variables khi phù hợp, hoặc chuyển state sang một owner phù hợp.

### 24.8. Runtime: `valueOf("UNKNOWN")`

**Nguyên nhân:** không có declared constant tên UNKNOWN.  
**Cách sửa:** validate input, map stable codes và xử lý unknown values theo contract; không tìm cách “tạo UNKNOWN”.

### 24.9. Runtime: enum mutable field bị race

**Nguyên nhân:** shared singleton-like constant với mutable fields không đồng bộ.  
**Cách sửa:** dùng immutable fields hoặc synchronization/atomic types.

### 24.10. Lỗi thiết kế: dùng ordinal để lưu DB

**Nguyên nhân:** reorder enum constants làm thay value ordinal.  
**Cách sửa:** explicit stable code/name với migration policy.

### 24.11. Lỗi reflection: giả định có thể tạo enum object qua Constructor.newInstance

**Nguyên nhân:** reflection API từ chối enum instantiation.  
**Cách sửa:** dùng declared constants hoặc abstraction khác.

### 24.12. Lỗi introspection: `constant.getClass() == E.class` cho mọi constant

**Nguyên nhân:** constant-specific class bodies có anonymous subclasses.  
**Cách sửa:** dùng `getDeclaringClass()` khi muốn enum type.

## 25. Các câu hỏi kiểm tra hiểu sâu

**Câu 1.** Trong `enum Color {RED, GREEN}`, có thể tạo `new Color()` không?

**Đáp án:** Không. Chỉ declared enum constants được tạo theo enum initialization mechanism.

**Câu 2.** `Color.RED == Color.RED` trả gì?

**Đáp án:** True, vì cùng enum constant instance.

**Câu 3.** `Color.valueOf("RED")` có tạo object mới không?

**Đáp án:** Không; trả reference tới Color.RED có sẵn.

**Câu 4.** `Color.values()` có tạo enum constants mới không?

**Đáp án:** Không. Nó trả array chứa references tới constants; array có thể là object mới.

**Câu 5.** Tại sao enum constructor không được public?

**Đáp án:** Để client không có đường tạo additional enum instances tùy ý, giữ tập constants cố định.

**Câu 6.** Constructor không có modifier của enum có cho phép client gọi từ cùng package không?

**Đáp án:** Không. Enum constructors được xử lý theo restrictions đặc biệt; bạn không thể tạo enum bằng new dù trong cùng package.

**Câu 7.** Có thể `enum E extends CustomBase` không?

**Đáp án:** Không. Mỗi enum có special superclass `Enum<E>`.

**Câu 8.** Có thể `class E2 extends E` khi E là enum không?

**Đáp án:** Không, không có named client subclass của enum.

**Câu 9.** Có thể `class Fake extends java.lang.Enum<Fake>` không?

**Đáp án:** Không; Java cấm ordinary classes trực tiếp extends Enum.

**Câu 10.** Enum có thể implements interface không?

**Đáp án:** Có, cả nhiều interfaces khi hợp lệ.

**Câu 11.** Interface có thể được implement bởi cả enum và record không?

**Đáp án:** Có; đó là cách cho API hỗ trợ built-in enum values và custom implementations.

**Câu 12.** Một enum luôn implicitly final trong Java 17?

**Đáp án:** Không theo cách nói tuyệt đối: enum không có constant class bodies là implicitly final; có constant-specific class body là implicitly sealed, với permitted subclasses do compiler tạo cho constants ấy.

**Câu 13.** Người dùng có thể khai báo custom subclass khi enum implicitly sealed không?

**Đáp án:** Không. Subclasses được phép là constant-specific anonymous classes được sinh theo enum declaration.

**Câu 14.** `constant.getClass()` và `getDeclaringClass()` luôn giống nhau?

**Đáp án:** Không nếu constant có class body. getDeclaringClass trả enum type, getClass có thể là anonymous subclass.

**Câu 15.** Một abstract enum method có thể không được một constant cài đặt không?

**Đáp án:** Không, mọi constant phải có concrete implementation theo enum rules.

**Câu 16.** Có thể override `name()` của Enum không?

**Đáp án:** Không, method final. Dùng label riêng hoặc override toString khi hợp lệ.

**Câu 17.** Enum có thể override `toString()` không?

**Đáp án:** Có. Nhưng name() vẫn là declared identifier.

**Câu 18.** Khi cần database ID ổn định, nên dùng ordinal() không?

**Đáp án:** Tránh. Dùng explicit stable code theo persistence contract.

**Câu 19.** `EnumSet` chứa được một runtime custom constant chưa khai báo không?

**Đáp án:** Không, vì không có additional enum constant hợp lệ.

**Câu 20.** `EnumMap` iteration theo thứ tự nào?

**Đáp án:** Natural order của enum keys, tương ứng declaration order.

**Câu 21.** Enum constructors có thể nhận tham số không?

**Đáp án:** Có, arguments đặt sau tên constants như `OK(200)`.

**Câu 22.** Tạo một Map lookup trong static block của enum có hữu ích không?

**Đáp án:** Có, có thể map stable codes sang declared constants sau khi chúng khởi tạo.

**Câu 23.** Enum constructor có thể trực tiếp `count++` trên nonconstant static field của chính enum không?

**Đáp án:** Không theo special enum initialization restriction.

**Câu 24.** Reflection `Constructor.newInstance` cho phép tạo enum constant mới?

**Đáp án:** Không. Reflection có restriction đặc biệt đối với enum instantiation.

**Câu 25.** Deserialize cùng enum constant bằng Java serialization có tạo new enum instance không?

**Đáp án:** Không; special enum serialization trả canonical declared constant theo type/name khi valid.

**Câu 26.** Enum constant object có thể có mutable field không?

**Đáp án:** Có. Enum hạn chế tạo/extend instances, nhưng không tự bảo đảm deep immutability.

**Câu 27.** Enum mutable counter có tự thread-safe không?

**Đáp án:** Không. Cần synchronization hoặc atomic field/API phù hợp.

**Câu 28.** `enum` member của class có implicitly static không?

**Đáp án:** Có. Không cần enclosing class instance chỉ để dùng member enum constant.

**Câu 29.** Khi người dùng thêm trạng thái mới ở runtime, enum hay record phù hợp hơn?

**Đáp án:** Thường dùng record/value class hoặc registry/interface; enum thích hợp cho tập named constants cố định theo code version.

**Câu 30.** Điều quan trọng nhất khi thiết kế enum là gì?

**Đáp án:** Enum có tập named instances được ngôn ngữ kiểm soát; không thể new hoặc subclass tùy ý. Extensibility nên dùng interface/abstraction khác thay vì phá invariant của enum.

## 26. Checklist khi chọn enum cho một thiết kế

1. Domain có tập giá trị **hữu hạn, ổn định theo code** không?
2. Constants có thực sự là named cases hay cần arbitrary runtime instances?
3. Có đang cần subclass/custom extends logic mà enum không cho phép không?
4. Có thể tách extensibility vào interface không?
5. Có constructors private/package-access và constant arguments rõ ràng không?
6. Có `new EnumType(...)` hoặc named extends enum trong code cần sửa không?
7. Có hiểu enum implicit superclass Enum<E> không?
8. Nếu constant-specific class body, có hiểu runtime anonymous subclass/implicit sealed semantics không?
9. Các abstract methods có được mọi constants implement không?
10. Có dùng getDeclaringClass thay getClass khi cần declared enum type không?
11. Enum fields có immutable values và invariants phù hợp không?
12. Nếu enum có mutable fields, concurrency và test isolation có được xử lý không?
13. Có dùng explicit stable code thay ordinal cho database/protocol không?
14. Có xử lý unknown valueOf inputs một cách có chủ đích không?
15. Có tránh override final Enum methods không?
16. Có dùng EnumSet/EnumMap khi collection keys/values là enum và phù hợp không?
17. Có đang hiểu EnumSet/EnumMap iteration order đúng không?
18. Có tránh cố tạo additional enum constants bằng reflection/unsupported hacks không?
19. Có phân biệt enum constants với values() array references không?
20. Có validation khi lookup code collisions hoặc unknown codes không?
21. Có xem xét source/version compatibility khi thêm/đổi constants không?
22. Có tránh lưu serialized ordinal/internal synthetic class names không?
23. Có phân biệt business display label với name() không?
24. Nếu member enum, có nhớ nó implicitly static, không có outer instance không?
25. Nếu cần plugin-extensible values, có chọn interface/registry/value class thay enum không?

## 27. Kết luận

**Enum trong Java là một class có tập named instances do chính khai báo enum xác định.** Chương trình có thể tham chiếu, so sánh và sử dụng constants ấy, nhưng không được tạo thêm instances bằng `new`, không được gọi enum constructor từ client, không được tự extends `java.lang.Enum` và không được đặt enum làm superclass cho ordinary named classes.

Dù constructor của enum có thể nhận parameters, chúng chỉ phục vụ initialization của constants đã khai báo. Enum ngầm có superclass `Enum<E>` và vì vậy không có `extends CustomBase`; **`implements Interface`** là con đường tích hợp với polymorphism. Một enum constant có thể có **constant-specific anonymous class body** để cung cấp behavior riêng; ngoại lệ này nằm trong quyền kiểm soát của compiler và **không biến enum thành hierarchy mở**.

Java còn duy trì identity qua `valueOf`, `values`, reflection restrictions và specialized serialization. Đồng thời, **fixed instance identity không có nghĩa mutable fields tự bất biến hay thread-safe**. Khi yêu cầu là tập values cố định, enum là thiết kế mạnh. Khi cần tạo values mới hoặc cho bên thứ ba thêm implementations, hãy dùng interface, record/value class, sealed abstraction hoặc registry phù hợp thay vì tìm cách vượt các giới hạn của enum.
