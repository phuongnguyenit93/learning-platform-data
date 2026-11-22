# Trường, phương thức và hàm khởi tạo của enum trong Java

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích `enum` là một loại class đặc biệt, trong đó các tên ở đầu body là **enum constants**, mỗi constant là một instance được tạo theo cơ chế do Java quản lý.
- Phân biệt **field của từng constant** với **static field dùng chung** và với chính các constant được Java khai báo ngầm là `public static final`.
- Khai báo enum có instance fields, instance methods, static methods, constructors và initializer blocks; hiểu khi nào phải có dấu `;` sau danh sách constants.
- Truyền arguments cho enum constructors ngay tại khai báo constant, dùng constructor overloads và `this(...)` chaining để xác định state khác nhau cho từng constant.
- Hiểu enum constructor là `private` tường minh hoặc ngầm định; không được khai báo `public`/`protected`, không được gọi `super(...)` tường minh và không thể gọi constructor từ code bên ngoài bằng `new`.
- Nắm **thứ tự khởi tạo**: constant objects được xây theo thứ tự khai báo trong quá trình enum class initialization; instance field/instance initializer chạy trước phần thân constructor; explicit static fields/blocks của enum chạy sau các constant declarations.
- Giải thích và sửa quy tắc JLS đặc thù: enum constructor, instance field initializer, instance initializer **không được tham chiếu static field của chính enum**, trừ khi đó là một **constant variable**.
- Sử dụng constant-specific class bodies để override/triển khai methods riêng của từng constant, và hiểu vì sao không khai constructor bên trong constant-specific body.
- Sử dụng `values()`, `valueOf(String)`, `name()`, `ordinal()`, `toString()`, `equals()`, `==` và `switch` đúng mục đích.
- Xây enum có private fields, validation, defensive copying và hành vi bất biến; nhận diện rủi ro khi enum chứa mutable state vì constants được dùng chung.
- Biết dùng `EnumSet`/`EnumMap`, interfaces, bảng tra cứu `static` và các lựa chọn thiết kế khi một enum bắt đầu có quá nhiều trách nhiệm.
- Đọc/biên dịch những chương trình Java 17+ tự chạy được, đối chiếu stdout và tự trả lời bài tập.

> **Phiên bản:** Mọi ví dụ chạy độc lập trong README đều hướng tới JDK 17 trở lên. Các đoạn cố tình sai để giải thích lỗi biên dịch được ghi rõ là **không phải chương trình hoàn chỉnh có thể biên dịch**. Các chi tiết chuẩn được tham chiếu từ Java Language Specification (JLS) Java SE 17, đặc biệt `8.9`, `8.9.2` và `8.9.3`.

## 1. Enum là class, constants là những instances có tên

Cú pháp cơ bản:

~~~java
enum Direction {
    NORTH, SOUTH, EAST, WEST
}
~~~

`Direction` không chỉ là một danh sách số nguyên. Nó là một **enum class** đặc biệt do Java quản lý. Các tên `NORTH`, `SOUTH`, `EAST`, `WEST` là **enum constants**, có kiểu `Direction`, được tạo trong quá trình khởi tạo enum class. Về mặt ngôn ngữ, mỗi tên constant tương ứng một field `public static final Direction` do compiler khai báo ngầm.

Các thuộc tính quan trọng:

1. Không thể viết `new Direction()` từ application code.
2. Không thể tự thêm một constant instance mới sau khi class đã được định nghĩa.
3. `Direction.NORTH == Direction.NORTH` là `true` vì cùng enum constant identity.
4. Các enum constants thuộc cùng class declaration được tạo một lần theo class initialization lifecycle; gọi `values()` không dựng lại các objects.
5. Bạn vẫn có thể định nghĩa instance fields và methods trong enum body, giống nhiều khả năng của một class thường.
6. Enum trực tiếp kế thừa `java.lang.Enum<Direction>` theo cơ chế ngôn ngữ; source enum declaration không có `extends` clause tùy ý.
7. Enum có thể `implements` interfaces, nhưng không khai báo type parameters riêng theo dạng `enum E<T>`.

### 1.1. Tên constant không phải biến local

Ví dụ:

~~~java
Direction selected = Direction.NORTH;
~~~

`selected` là một reference variable của caller, còn `Direction.NORTH` là constant object có identity ổn định. Gán `selected = Direction.SOUTH` chỉ thay reference được giữ trong biến, **không tạo một enum instance mới**.

Không nên nhầm từ khóa `final` của implicit constant field với việc **mọi field bên trong enum object đều bất biến**. Enum vẫn có thể chứa mutable instance fields — mặc dù nhiều thiết kế nên tránh điều đó.

## 2. Enum có trường (fields) riêng của từng constant

Một enum có thể khai báo constructor và một private instance field:

~~~java
enum Coin {
    PENNY(1), NICKEL(5), DIME(10), QUARTER(25);

    private final int cents;

    private Coin(int cents) {
        this.cents = cents;
    }

    public int cents() {
        return cents;
    }
}
~~~

Phân tích:

- `PENNY(1)` là constant declaration có constructor argument `1`.
- `Coin(int cents)` nhận argument riêng cho mỗi constant.
- `this.cents = cents` thiết lập instance field `cents` **trên chính object constant đang được tạo**.
- `private final` nói field không được gán lại sau khi initialized; với `int` primitive, điều này giữ giá trị ổn định.
- `cents()` là **instance method**. Gọi `Coin.DIME.cents()` trả 10.
- Dấu `;` sau constant `QUARTER(25)` là cần khi phía sau danh sách constants còn các declarations của fields/methods/constructors/blocks.

### 2.1. Chương trình độc lập đầu tiên

Lưu **`EnumFieldsDemo.java`**:

~~~java
public class EnumFieldsDemo {
    enum Coin {
        PENNY(1), NICKEL(5), DIME(10), QUARTER(25);

        private final int cents;

        Coin(int cents) {
            if (cents <= 0) {
                throw new IllegalArgumentException("cents");
            }
            this.cents = cents;
        }

        int cents() {
            return cents;
        }

        String label() {
            return name() + "=" + cents + "c";
        }
    }

    public static void main(String[] args) {
        System.out.println(Coin.PENNY.label());
        System.out.println(Coin.QUARTER.label());

        int total = 0;
        for (Coin coin : Coin.values()) {
            total += coin.cents();
        }
        System.out.println("all cents=" + total);
    }
}
~~~

Chạy:

~~~bash
javac EnumFieldsDemo.java
java EnumFieldsDemo
~~~

Stdout:

~~~text
PENNY=1c
QUARTER=25c
all cents=41
~~~

Mỗi Coin constant có `cents` riêng, nhưng cùng chạy implementation `label()`. Field là `final int` nên không có phương thức để thay số cents sau khi constants được tạo.

### 2.2. Vì sao dùng field thay vì `ordinal()` để lưu dữ liệu nghiệp vụ?

`ordinal()` phản ánh **vị trí khai báo** của constant, bắt đầu từ 0. Nó có thể đổi khi sắp xếp hoặc thêm constants. Đồng xu không có giá trị tiền dựa trên thứ tự khai báo. Hãy dùng `private final int cents`, `code` hoặc `id` rõ ý nghĩa nghiệp vụ, không suy ra từ ordinal.

## 3. Dấu chấm phẩy sau danh sách constants

Trong enum body, khai báo constants đứng trước các body declarations khác.

~~~java
enum State {
    NEW, ACTIVE, DONE;  // Cần dấu ; nếu còn declarations.

    private final long createdAt = 0L;

    boolean terminal() {
        return this == DONE;
    }
}
~~~

Nếu enum body **chỉ có constants**, dấu `;` có thể được bỏ:

~~~java
enum SimpleState {
    NEW, ACTIVE, DONE
}
~~~

Nếu cần một static method, private constructor, field hoặc instance initializer sau constants, viết dấu `;` để phân tách.

### 3.1. Dấu phẩy và constructor arguments

~~~java
enum Priority {
    LOW(1),
    MEDIUM(5),
    HIGH(10);

    private final int score;

    Priority(int score) {
        this.score = score;
    }
}
~~~

Arguments sau từng constant được chọn theo overload resolution của constructor enum; chúng **không** biến enum constants thành các biến số nguyên. `LOW` vẫn là `Priority` object, trong đó `score` là 1.

## 4. Hàm khởi tạo của enum: quyền truy cập đặc biệt

Theo JLS `8.9.2`:

- Constructor có thể ghi `private EnumName(...)`.
- Nếu bỏ access modifier ở constructor declaration, constructor ấy cũng được coi là **private**.
- Constructor enum **không được** là `public` hoặc `protected`.
- Không thể khai báo lời gọi superclass constructor tường minh như `super(...)` bên trong enum constructor.
- Nếu bạn không khai báo constructor nào, compiler tự khai một **default private no-arg constructor** của enum.
- Code thông thường không được `new EnumName(...)`. Việc tạo constants do compiler/JVM khởi tạo enum type đảm nhận.

### 4.1. Các khai báo sai (minh họa, đã comment)

~~~java
enum Invalid {
    A(1);

    // public Invalid(int n) { }      // Sai: public enum constructor.
    // protected Invalid(int n) { }   // Sai: protected enum constructor.
    // Invalid(int n) { super(); }    // Sai: explicit superclass call.
}

// Invalid another = new Invalid(1); // Sai: enum cannot be instantiated with new.
~~~

**Không dùng những dòng bị comment làm code chạy.** Lỗi compiler có thể được diễn đạt khác nhau tùy JDK/IDE, nhưng nguyên nhân là các quy tắc riêng của enum, không phải do private field `n` hay dấu `;`.

### 4.2. `java.lang.Enum` đã nhận name/ordinal thế nào?

Compiler cung cấp cơ chế truyền thông tin tên constant và ordinal cho superclass `java.lang.Enum`; bạn **không** viết `super("A", 0)` thủ công. Không dựa vào bytecode constructor signature tổng hợp như một API mà application có thể gọi.

Constructor enum dùng để gán **state do bạn tự khai báo**, validate argument và thực hiện các công việc phù hợp với thời điểm class initialization. Nó không phải cách mở cổng tạo tùy ý enum instances.

## 5. Constructor overloading cho constants khác nhau

Enum constructors có thể được overload như constructor của class thường. Mỗi constant gọi overload phù hợp với arguments mà nó khai báo.

### 5.1. Chương trình runnable

Lưu **`EnumConstructorOverloadDemo.java`**:

~~~java
public class EnumConstructorOverloadDemo {
    enum Priority {
        LOW,
        MEDIUM(5),
        HIGH(9, "urgent");

        private final int score;
        private final String description;

        Priority() {
            this(1, "normal");
        }

        Priority(int score) {
            this(score, "custom");
        }

        private Priority(int score, String description) {
            this.score = score;
            this.description = description;
        }

        String describe() {
            return name() + ":" + score + ":" + description;
        }
    }

    public static void main(String[] args) {
        for (Priority priority : Priority.values()) {
            System.out.println(priority.describe());
        }
    }
}
~~~

Chạy:

~~~bash
javac EnumConstructorOverloadDemo.java
java EnumConstructorOverloadDemo
~~~

Output:

~~~text
LOW:1:normal
MEDIUM:5:custom
HIGH:9:urgent
~~~

Chú ý:

- `LOW` không có parentheses → constructor argument list rỗng → `Priority()`.
- `MEDIUM(5)` → `Priority(int)`.
- `HIGH(9,"urgent")` → `Priority(int,String)`.
- `this(...)` **được dùng để nối các constructors cùng enum class** (chaining), khác với việc gọi `super(...)` bị cấm.
- Mỗi constant có final state riêng, dù các constructors dùng chung implementation cuối.
- Không cần khai báo constructor `public` để các constants gọi nó: declarations của constants nằm trong chính enum class.

### 5.2. Default constructor vs no-arg overloaded constructor

Nếu enum chỉ là:

~~~java
enum SimpleMode {
    FAST, SAFE
}
~~~

Java tự cung cấp default private no-arg constructor. Nhưng nếu bạn tự khai **chỉ** constructor có parameter:

~~~java
enum Size {
    SMALL(1), LARGE(3);

    private Size(int value) {
    }
}
~~~

thì constants phải có argument list khớp constructor có thể gọi. Viết thêm `MEDIUM` (không đối số) ở đây sẽ không tự có một no-arg overload mới. Muốn constant đó hợp lệ, khai constructor không tham số riêng hoặc đưa arguments vào constant.

## 6. Enum instance methods dùng state của chính constant

Một enum thường nên thể hiện ý nghĩa bằng **methods có tên rõ ràng**, thay vì buộc caller lấy raw field rồi viết một chuỗi `if`.

Ví dụ:

~~~java
enum Role {
    READER(false), EDITOR(true);

    private final boolean canWrite;

    Role(boolean canWrite) {
        this.canWrite = canWrite;
    }

    boolean permitsWrite() {
        return canWrite;
    }
}
~~~

`permitsWrite()` encapsulate field `canWrite`. Nếu sau này rule phức tạp hơn, caller vẫn dùng API method thay vì phụ thuộc representation nội bộ.

### 6.1. Chương trình đầy đủ

Lưu **`EnumInstanceMethodDemo.java`**:

~~~java
public class EnumInstanceMethodDemo {
    enum Role {
        VIEWER(false),
        EDITOR(true),
        ADMIN(true);

        private final boolean mayEdit;

        Role(boolean mayEdit) {
            this.mayEdit = mayEdit;
        }

        boolean mayEdit() {
            return mayEdit;
        }

        String action() {
            return mayEdit ? "WRITE" : "READ";
        }
    }

    public static void main(String[] args) {
        for (Role role : Role.values()) {
            System.out.println(role.name() + ":" +
                    role.action() + ":" + role.mayEdit());
        }
    }
}
~~~

Chạy:

~~~bash
javac EnumInstanceMethodDemo.java
java EnumInstanceMethodDemo
~~~

Output:

~~~text
VIEWER:READ:false
EDITOR:WRITE:true
ADMIN:WRITE:true
~~~

Getter/method được gọi **trên enum constant**, không trên một object mới do caller tạo. Các methods có thể là `public` nếu API module cần dùng bên ngoài, còn ví dụ nested enum trong cùng class demo có package-private methods là đủ.

## 7. Khởi tạo enum constants xảy ra khi nào?

Enum constants là static fields của enum class, và constructor của từng constant được gọi khi enum class **được khởi tạo** (*class initialization*), không phải mỗi khi bạn đọc `SomeEnum.VALUE`.

Theo JLS, class initialization có rules riêng về *active use*. Chẳng hạn, lần đầu đánh giá một enum constant field có thể kích hoạt initialization của enum class nếu nó chưa được initialized.

**Phân biệt:**

- `new EnumClass(...)` từ source là không hợp lệ.
- `EnumClass.ONE` có thể là first active use làm class init chạy.
- Khi class init chạy, enum constant declarations được xử lý **theo textual order**.
- Constructor của enum chạy cho **mỗi constant** khi constant object được tạo.
- Sau đó gọi instance method trên constant không gọi constructor lần nữa.
- Classloader/class lifecycle và JVM class initialization synchronization bảo đảm initialization có quy tắc; không dùng enum constructor để viết side effects nhiều threads một cách tùy tiện.

### 7.1. Chương trình quan sát thứ tự

Lưu **`EnumClassInitializationDemo.java`**:

~~~java
public class EnumClassInitializationDemo {
    enum Stage {
        START(1),
        FINISH(2);

        private final int code;

        Stage(int code) {
            this.code = code;
            System.out.println("constructor " + name() +
                    " code=" + code);
        }

        int code() {
            return code;
        }

        static {
            System.out.println("static block constants=" +
                    Stage.values().length);
        }
    }

    public static void main(String[] args) {
        System.out.println("before first use");
        System.out.println("start code=" + Stage.START.code());
        System.out.println("finish code=" + Stage.FINISH.code());
    }
}
~~~

Chạy:

~~~bash
javac EnumClassInitializationDemo.java
java EnumClassInitializationDemo
~~~

Output:

~~~text
before first use
constructor START code=1
constructor FINISH code=2
static block constants=2
start code=1
finish code=2
~~~

Đây là output trong chương trình độc lập, với lần active use đầu tiên xảy ra sau `println("before first use")`. Constructors cho START và FINISH chạy trước static block được khai báo sau constants. Lần dùng FINISH tiếp theo **không tái thực hiện constructor**.

**Không suy từ một ví dụ này rằng mọi JVM class được khởi tạo ngay khi class file được load**; class loading/linking và class initialization là các khái niệm khác nhau.

## 8. Thứ tự instance field initializers, instance blocks và constructor body

Enum constants là instances của enum class; cơ chế instance initialization có nhiều điểm giống class thông thường:

1. Object được cấp phát, instance fields ban đầu nhận default values.
2. Constructor chain của superclass được xử lý theo rules, ở đây Java xử lý `Enum` superclass.
3. Instance field initializers và instance initializer blocks của enum chạy xen kẽ **theo thứ tự source**.
4. Phần thân của enum constructor tiếp tục xử lý state của constant.
5. Constant object được tạo xong và gán vào field constant tương ứng.
6. Sau khi constants hoàn tất, explicit enum static field initializers và static initializer blocks chạy theo textual order.

Vì thế, một instance block có thể đọc field đã gán trước đó; còn đọc field được gán bởi initializer nằm sau block có thể thấy default value.

### 8.1. Chương trình kiểm chứng

Lưu **`EnumInstanceInitializationOrderDemo.java`**:

~~~java
public class EnumInstanceInitializationOrderDemo {
    enum Phase {
        PREPARE(3),
        EXECUTE(7);

        private int score = log("field", 1);

        {
            System.out.println("block sees=" + score);
            score += 2;
        }

        Phase(int extra) {
            System.out.println("ctor extra=" + extra +
                    " score=" + score);
            score += extra;
        }

        int score() {
            return score;
        }
    }

    static int log(String phase, int value) {
        System.out.println(phase + "=" + value);
        return value;
    }

    public static void main(String[] args) {
        System.out.println("prepare=" + Phase.PREPARE.score());
        System.out.println("execute=" + Phase.EXECUTE.score());
    }
}
~~~

Chạy:

~~~bash
javac EnumInstanceInitializationOrderDemo.java
java EnumInstanceInitializationOrderDemo
~~~

Output:

~~~text
field=1
block sees=1
ctor extra=3 score=3
field=1
block sees=1
ctor extra=7 score=3
prepare=6
execute=10
~~~

Phân tích:

- Khi tạo PREPARE, `score` mặc định 0, field initializer gán 1, instance block đọc 1 rồi tăng thành 3.
- Constructor PREPARE nhận extra=3, in score=3, tăng thành 6.
- Khi tạo EXECUTE, **instance field score riêng** lại bắt đầu qua 0→1→3, rồi constructor cộng 7 thành 10.
- Hai constants được xây từ cùng field/initializer declarations, nhưng giữ instance values khác nhau.

**Khác static initializer:** block `static { ... }` chạy **một lần cho enum class**, không chạy riêng cho từng constant; block `{ ... }` ở body enum chạy cho từng object constant.

## 9. Quy tắc JLS khó: không đọc static field chưa phải constant variable khi tạo enum constants

Vì enum constants được tạo **trước những static fields bạn tự khai báo phía dưới**, dễ xuất hiện chu kỳ initialization. JLS `8.9.2` quy định:

> Trong constructor, instance initializer hoặc instance variable initializer của enum declaration, việc tham chiếu static field của **chính enum class** là compile-time error, **trừ khi field ấy là constant variable**.

Không nên hiểu nhầm rằng mọi field có `static final` đều là *constant variable*. Theo `4.12.4`, constant variable phải là `final` có kiểu primitive hoặc String và được khởi tạo bằng một **constant expression**.

### 9.1. Trường hợp hợp lệ: constant variable

~~~java
enum Mode {
    A(1), B(2);

    private static final int FACTOR = 10;
    private final int scaled;

    Mode(int n) {
        scaled = n * FACTOR;  // Hợp lệ: FACTOR là constant variable.
    }
}
~~~

`FACTOR` có `static final int` với constant expression `10`. Compiler có thể dùng giá trị constant expression ngay trong enum constructor khi constants được tạo.

### 9.2. Trường hợp không hợp lệ: `static final Map`

~~~java
enum BadLookup {
    A, B;

    private static final java.util.Map<String, BadLookup> INDEX =
            new java.util.HashMap<>();

    BadLookup() {
        // INDEX.put(name(), this);
        // Compile-time error nếu uncomment:
        // tham chiếu non-constant static field của chính enum
        // trong enum constructor.
    }
}
~~~

Ngay cả `static final Map` cũng **không phải constant variable**: Map là reference type khác String và giá trị được tạo tại runtime. Nếu cứ cho phép constructor dùng INDEX, INDEX còn chưa được khởi tạo lúc A/B constructors đang chạy.

### 9.3. Trường hợp `static final Integer` cũng không phải constant variable

~~~java
enum BadBoxed {
    A;

    private static final Integer BASE = Integer.valueOf(10);

    BadBoxed() {
        // int x = BASE; // Sai nếu bỏ comment:
        // BASE không phải constant variable.
    }
}
~~~

`Integer` không phải primitive type hay String, mặc dù reference được gán `final`. `static final` không tự động tạo constant-variable exception.

### 9.4. Cách sửa phù hợp

- Để state riêng trên từng constant, truyền giá trị qua **constructor arguments**.
- Với giá trị compile-time primitive/String, dùng **constant variable**.
- Với shared runtime map/list cache, khởi tạo qua **static initializer sau khi constants đã được tạo**.
- Với logic tra cứu do người dùng gọi sau class initialization, đặt trong **static method** đọc map đã khởi tạo.
- Không dùng một helper method gọi từ constructor nhằm che một initialization cycle; compiler không phát hiện hết circular dependencies qua method indirection, nhưng runtime vẫn có thể thấy null/partial state.

## 10. Chương trình: constant-variable exception hợp lệ

Lưu **`EnumConstantVariableDemo.java`**:

~~~java
public class EnumConstantVariableDemo {
    enum Multiplier {
        SMALL(2), LARGE(5);

        private static final int FACTOR = 10;
        private final int product;

        Multiplier(int input) {
            product = input * FACTOR;
        }

        int product() {
            return product;
        }
    }

    public static void main(String[] args) {
        System.out.println("small=" + Multiplier.SMALL.product());
        System.out.println("large=" + Multiplier.LARGE.product());
    }
}
~~~

Chạy:

~~~bash
javac EnumConstantVariableDemo.java
java EnumConstantVariableDemo
~~~

Output:

~~~text
small=20
large=50
~~~

`FACTOR` được khai báo sau constants trong body, nhưng là constant variable, được phép dùng khi constructor chạy. Điều này là ngoại lệ có **cơ sở từ JLS**, không nên suy rộng sang `static final Map` hay `static final Integer`.

## 11. Xây bảng tra cứu static sau khi mọi constants đã được tạo

Một yêu cầu thực tế: tìm enum constant từ business code, HTTP code, short label hoặc ID. Không dùng constructor để thêm `this` vào một static map của **chính enum class**. Thay vào đó:

1. Constructor chỉ gán các **instance fields** của từng constant.
2. Sau constants, khai báo static map.
3. Trong static block chạy sau khi constants được xây, lặp `values()` để điền map.
4. Cung cấp static method như `fromCode(int)` để tra cứu sau class initialization.

### 11.1. Chương trình đầy đủ

Lưu **`EnumLookupDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class EnumLookupDemo {
    enum HttpStatus {
        OK(200), NOT_FOUND(404);

        private final int code;
        private static final Map<Integer, HttpStatus> BY_CODE;

        HttpStatus(int code) {
            this.code = code;
        }

        int code() {
            return code;
        }

        static {
            Map<Integer, HttpStatus> mapping = new HashMap<>();
            for (HttpStatus status : values()) {
                HttpStatus previous = mapping.put(status.code(), status);
                if (previous != null) {
                    throw new IllegalStateException("duplicate code");
                }
            }
            BY_CODE = Map.copyOf(mapping);
        }

        static HttpStatus fromCode(int code) {
            return BY_CODE.get(code);
        }
    }

    public static void main(String[] args) {
        System.out.println("200=" + HttpStatus.fromCode(200));
        System.out.println("404=" + HttpStatus.fromCode(404));
        System.out.println("500=" + HttpStatus.fromCode(500));
    }
}
~~~

Chạy:

~~~bash
javac EnumLookupDemo.java
java EnumLookupDemo
~~~

Output:

~~~text
200=OK
404=NOT_FOUND
500=null
~~~

Vì static block ở sau enum constant declarations, `values()` ở đó lấy đầy đủ constants. `Map.copyOf` tạo unmodifiable map snapshot từ mapping, tránh cho caller mutate map nội bộ. Ví dụ `fromCode` trả null khi không thấy key; API production có thể thích hợp hơn với `Optional<HttpStatus>` hoặc exception tùy domain.

**Không gọi `HttpStatus.fromCode(...)` từ enum constructor để đoán rằng static map đã sẵn sàng**; bạn sẽ gặp vòng khởi tạo, thiếu state hoặc lỗi runtime trong các thiết kế không được JLS cấm trực tiếp.

## 12. Static methods của enum và instance methods khác nhau thế nào?

Một enum có thể có cả hai:

~~~java
enum Mode {
    FAST, SAFE;

    boolean fast() {
        return this == FAST; // Instance method: cần receiver.
    }

    static Mode parse(String text) {
        return valueOf(text); // Static method: gọi trên enum class.
    }
}
~~~

Sử dụng:

~~~java
boolean x = Mode.FAST.fast();
Mode y = Mode.parse("SAFE");
~~~

- `FAST.fast()` có receiver là constant FAST.
- `Mode.parse(...)` thuộc class; không cần một receiver enum object do caller cung cấp.
- `valueOf(String)` là static method đặc biệt được khai báo ngầm cho từng enum type.
- Nếu `text` không khớp tên constant, `valueOf` ném `IllegalArgumentException` (null cũng có exception semantics riêng).

Các đoạn trên là snippets hợp lệ trong class/scope phù hợp, không phải file có main độc lập.

### 12.1. `values()` trả một array mới

`Mode.values()` trả `Mode[]` chứa constants theo thứ tự khai báo. Array trả về có thể thay reference phần tử bởi caller, nhưng không làm đổi enum constant fields `Mode.FAST`/`Mode.SAFE` hay tạo constants mới.

Không nên lưu/cho phép caller sửa một internal array do chính mình quản lý nếu không có defensive contract. Với enum `values()`, API cung cấp cách lấy tập constants; enum identity vẫn giữ.

## 13. Chương trình: API static và instance rõ ràng

Lưu **`EnumStaticAndInstanceMethodsDemo.java`**:

~~~java
public class EnumStaticAndInstanceMethodsDemo {
    enum Mode {
        FAST, SAFE;

        boolean isFast() {
            return this == FAST;
        }

        static Mode parse(String name) {
            return valueOf(name.trim().toUpperCase(
                    java.util.Locale.ROOT));
        }
    }

    public static void main(String[] args) {
        Mode parsed = Mode.parse(" safe ");

        System.out.println("parsed=" + parsed);
        System.out.println("fast?=" + parsed.isFast());
        System.out.println("same constant=" +
                (Mode.valueOf("SAFE") == parsed));

        Mode[] copy = Mode.values();
        copy[0] = Mode.SAFE;

        System.out.println("copy first=" + copy[0]);
        System.out.println("original first=" + Mode.values()[0]);
    }
}
~~~

Chạy:

~~~bash
javac EnumStaticAndInstanceMethodsDemo.java
java EnumStaticAndInstanceMethodsDemo
~~~

Output:

~~~text
parsed=SAFE
fast?=false
same constant=true
copy first=SAFE
original first=FAST
~~~

`parse` chọn normalization có chủ đích, còn `valueOf` gốc yêu cầu tên constant đúng nguyên văn. Dù sửa array `copy`, enum constants và thứ tự `values()` của class không đổi.

## 14. Constant-specific class bodies: mỗi constant có hành vi riêng

Thay vì viết `switch(this)` trong mọi method, enum có thể khai báo **class body ngay sau một constant** để override method:

~~~java
enum Operation {
    ADD {
        @Override
        int calculate(int x, int y) {
            return x + y;
        }
    },
    MULTIPLY {
        @Override
        int calculate(int x, int y) {
            return x * y;
        }
    };

    abstract int calculate(int x, int y);
}
~~~

Đây là idiom *constant-specific method implementation*. Theo JLS `8.9.1`, body của constant tạo một **anonymous subclass** riêng của enum class cho constant đó, nhưng không được tự khai constructor trong constant body.

### 14.1. Chương trình đầy đủ

Lưu **`EnumConstantSpecificMethodDemo.java`**:

~~~java
public class EnumConstantSpecificMethodDemo {
    enum Operation {
        ADD {
            @Override
            int calculate(int x, int y) {
                return x + y;
            }
        },
        MULTIPLY {
            @Override
            int calculate(int x, int y) {
                return x * y;
            }
        };

        abstract int calculate(int x, int y);
    }

    public static void main(String[] args) {
        System.out.println("add=" + Operation.ADD.calculate(2, 3));
        System.out.println("multiply=" +
                Operation.MULTIPLY.calculate(2, 3));
        System.out.println("declaring type=" +
                (Operation.ADD.getDeclaringClass() == Operation.class));
        System.out.println("constant subclass=" +
                (Operation.ADD.getClass() != Operation.class));
    }
}
~~~

Chạy:

~~~bash
javac EnumConstantSpecificMethodDemo.java
java EnumConstantSpecificMethodDemo
~~~

Output:

~~~text
add=5
multiply=6
declaring type=true
constant subclass=true
~~~

Điểm cần hiểu:

- `Operation` là enum class, `ADD` và `MULTIPLY` có constant-specific bodies.
- `calculate` được khai báo abstract trong enum class; **mỗi constant** phải cung cấp implementation.
- `getDeclaringClass()` của enum constant trả enum class khai báo nó, kể cả khi runtime class của constant là một anonymous subclass.
- `getClass()` của ADD trong ví dụ không bằng `Operation.class` vì có constant-specific class body.
- Không dùng `getClass() == Operation.class` để kiểm tra enum declaring type khi có constant-specific subclasses.

### 14.2. Constructors vẫn thuộc enum class

Nếu enum constructor nhận parameters, mỗi constant có class body vẫn truyền arguments tới **enum constructor** bình thường:

~~~java
enum Calculator {
    ADD(1) {
        @Override
        int apply(int a, int b) {
            return a + b;
        }
    },
    MULTIPLY(2) {
        @Override
        int apply(int a, int b) {
            return a * b;
        }
    };

    private final int id;

    Calculator(int id) {
        this.id = id;
    }

    int id() {
        return id;
    }

    abstract int apply(int a, int b);
}
~~~

Đây là standalone **enum snippet** đặt trong file/scope hợp lệ; nó không có `main` riêng. `ADD(1)` và `MULTIPLY(2)` chọn constructor `Calculator(int)`, nhưng những class bodies sau constants không khai các constructors mới. Chúng chỉ cung cấp behavior override.

## 15. Nếu một constant không triển khai abstract method thì sao?

Nếu enum class có abstract method, JLS yêu cầu enum có ít nhất một constant và **mọi constant phải có constant-specific body với concrete implementation** của method abstract đó.

~~~java
enum InvalidOperation {
    ADD {
        @Override
        int apply(int x, int y) {
            return x + y;
        }
    },
    // SUBTRACT; // Sai nếu không triển khai abstract apply().

    MULTIPLY {
        @Override
        int apply(int x, int y) {
            return x * y;
        }
    };

    abstract int apply(int x, int y);
}
~~~

Các dòng bị comment minh họa lỗi. Nếu một constant có behavior mặc định, đừng khai method abstract; hãy cung cấp **concrete implementation trong enum class** và chỉ override ở constants đặc biệt.

### 15.1. Khi nào constant-specific behavior có giá trị?

- Tập chiến lược hữu hạn, mỗi constant tự định nghĩa cách tính.
- Tránh các khối switch trùng lặp nếu logic thuộc về chính constant.
- Compile-time enforcement buộc đủ các implementations đối với abstract method.
- Caller dùng `operation.calculate(x,y)` qua common API.

Nếu mỗi constant body rất dài, có nhiều phụ thuộc/side effects và bắt đầu giống một service, có thể dùng enum như **ID/selector** rồi delegate sang classes/services khác với lifetime rõ hơn.

## 16. `name()`, `toString()` và field hiển thị

`Enum.name()` trả **tên khai báo gốc** của constant, ví dụ `PENDING`. `name()` là final, không override được. `toString()` theo mặc định trả cùng tên, nhưng có thể override để cho label hiển thị.

~~~java
enum Status {
    PENDING("Waiting"), DONE("Finished");

    private final String label;

    Status(String label) {
        this.label = label;
    }

    @Override
    public String toString() {
        return label;
    }
}
~~~

Nếu `Status.PENDING.toString()` trả `Waiting`, điều đó không đổi `Status.PENDING.name()` là `PENDING`. `valueOf("PENDING")` vẫn hợp lệ; `valueOf("Waiting")` **không** tự tìm theo toString.

### 16.1. Chương trình runnable

Lưu **`EnumNameVsToStringDemo.java`**:

~~~java
public class EnumNameVsToStringDemo {
    enum Status {
        PENDING("Waiting"),
        DONE("Finished");

        private final String label;

        Status(String label) {
            this.label = label;
        }

        @Override
        public String toString() {
            return label;
        }

        String label() {
            return label;
        }
    }

    public static void main(String[] args) {
        Status value = Status.PENDING;

        System.out.println("name=" + value.name());
        System.out.println("toString=" + value);
        System.out.println("label=" + value.label());
        System.out.println("parse=" + Status.valueOf("PENDING"));

        try {
            Status.valueOf("Waiting");
        } catch (IllegalArgumentException expected) {
            System.out.println("display label is not enum name");
        }
    }
}
~~~

Chạy:

~~~bash
javac EnumNameVsToStringDemo.java
java EnumNameVsToStringDemo
~~~

Output:

~~~text
name=PENDING
toString=Waiting
label=Waiting
parse=Waiting
display label is not enum name
~~~

`parse` ở ví dụ in `Waiting` vì `System.out.println(Status.valueOf(...))` gọi `toString()` của Status object. Nếu muốn hiển thị tên gốc, in `Status.valueOf("PENDING").name()`.

**Lời khuyên thiết kế:** nếu dữ liệu enum được lưu như code ổn định trong cơ sở dữ liệu/API, cân nhắc private final business code field thay vì coi `ordinal()` hoặc label bản dịch là ID. Nếu rename constant source, `name()` cũng đổi; versioning cần xử lý theo domain.

## 17. `ordinal()`, `equals()`, `hashCode()` và identity

Enum constants là instances hữu hạn, có identity duy nhất trong phạm vi enum class/classloader. Điều này dẫn tới:

- So hai constants cùng enum bằng `==` là idiom dễ đọc, kiểm tra identity.
- `Enum.equals` final dùng identity semantics, không phải so private fields theo value.
- `Enum.hashCode` không override được như một value object tùy ý.
- `name()` và `ordinal()` là final methods của Enum.
- `ordinal()` được dùng chủ yếu cho một số cấu trúc data đặc thù, không nên lưu như business ID ổn định.
- `getDeclaringClass()` phản ánh enum class gốc, kể cả constant-specific subclass.
- Enum `compareTo` phản ánh thứ tự khai báo, nhưng không tùy ý so constants của hai enum types không tương thích.

### 17.1. Chương trình identity và ordinal

Lưu **`EnumIdentityDemo.java`**:

~~~java
public class EnumIdentityDemo {
    enum State {
        CREATED, RUNNING, STOPPED;

        boolean terminal() {
            return this == STOPPED;
        }
    }

    public static void main(String[] args) {
        State a = State.RUNNING;
        State b = State.valueOf("RUNNING");

        System.out.println("same reference=" + (a == b));
        System.out.println("equals=" + a.equals(b));
        System.out.println("running ordinal=" + a.ordinal());
        System.out.println("stopped terminal=" +
                State.STOPPED.terminal());
        System.out.println("ordered=" +
                (State.CREATED.compareTo(State.RUNNING) < 0));
    }
}
~~~

Chạy:

~~~bash
javac EnumIdentityDemo.java
java EnumIdentityDemo
~~~

Output:

~~~text
same reference=true
equals=true
running ordinal=1
stopped terminal=true
ordered=true
~~~

Nếu reorder constants, `ordinal()` và ordering có thể đổi. Đó là một lý do không dùng ordinal làm persistent database code. `equals` và `==` cho cùng enum constant đều true vì cùng object.

## 18. Enum method có thể triển khai interface

Enum class không thể `extends` một superclass tùy ý, nhưng có thể `implements` một hoặc nhiều interfaces. Instance methods của enum có thể thực hiện hợp đồng interface, kể cả generic interface phù hợp.

### 18.1. Chương trình đầy đủ

Lưu **`EnumInterfaceMethodDemo.java`**:

~~~java
public class EnumInterfaceMethodDemo {
    interface Transformer {
        int apply(int input);
    }

    enum Scale implements Transformer {
        DOUBLE(2),
        TRIPLE(3);

        private final int multiplier;

        Scale(int multiplier) {
            this.multiplier = multiplier;
        }

        @Override
        public int apply(int input) {
            return input * multiplier;
        }
    }

    static void execute(Transformer transformer, int value) {
        System.out.println("result=" + transformer.apply(value));
    }

    public static void main(String[] args) {
        execute(Scale.DOUBLE, 5);
        execute(Scale.TRIPLE, 5);

        System.out.println("same enum=" +
                (Scale.valueOf("DOUBLE") == Scale.DOUBLE));
    }
}
~~~

Chạy:

~~~bash
javac EnumInterfaceMethodDemo.java
java EnumInterfaceMethodDemo
~~~

Output:

~~~text
result=10
result=15
same enum=true
~~~

Interface giúp caller phụ thuộc vào **behavior contract**, không cần biết field `multiplier`. Enum constructor chỉ khởi tạo multiplier một lần cho mỗi Scale constant.

### 18.2. Không viết generic enum declaration

Một enum không thể được khai như `enum Scale<T>`. Nhưng enum có thể implement một **generic interface với type arguments xác định**, ví dụ `enum Color implements Converter<String>` khi Converter được khai báo thích hợp.

## 19. Enum với `switch` và fields/methods

Có lúc dùng `switch` expression bên trong method enum dễ hiểu hơn constant-specific class bodies, nhất là khi behavior nhỏ:

~~~java
enum TrafficLight {
    RED(30), YELLOW(4), GREEN(25);

    private final int seconds;

    TrafficLight(int seconds) {
        this.seconds = seconds;
    }

    String instruction() {
        return switch (this) {
            case RED -> "STOP";
            case YELLOW -> "CAUTION";
            case GREEN -> "GO";
        };
    }
}
~~~

Tất cả logic nhỏ nằm trong one method; mỗi constant vẫn có `seconds` private final field.

### 19.1. Chương trình runnable

Lưu **`EnumSwitchAndFieldsDemo.java`**:

~~~java
public class EnumSwitchAndFieldsDemo {
    enum TrafficLight {
        RED(30), YELLOW(4), GREEN(25);

        private final int seconds;

        TrafficLight(int seconds) {
            this.seconds = seconds;
        }

        String instruction() {
            return switch (this) {
                case RED -> "STOP";
                case YELLOW -> "CAUTION";
                case GREEN -> "GO";
            };
        }

        int seconds() {
            return seconds;
        }
    }

    public static void main(String[] args) {
        for (TrafficLight light : TrafficLight.values()) {
            System.out.println(light.name() + ":" +
                    light.instruction() + ":" + light.seconds());
        }
    }
}
~~~

Chạy:

~~~bash
javac EnumSwitchAndFieldsDemo.java
java EnumSwitchAndFieldsDemo
~~~

Output:

~~~text
RED:STOP:30
YELLOW:CAUTION:4
GREEN:GO:25
~~~

Một thay đổi enum thêm constant mới cần cập nhật `switch` expression để bảo đảm đầy đủ các cases theo yêu cầu biên dịch. Chọn switch hay constant-specific polymorphism tùy độ phức tạp và cách cần mở rộng behavior.

## 20. Mutable fields trong enum: hợp lệ nhưng dễ gây lỗi

Nguyên tắc quan trọng: enum constants là objects **dùng chung**, không phải fresh instances mỗi khi method được gọi. Nếu một constant có mutable instance field, mọi alias tới constant đó cùng nhìn state đang bị sửa.

~~~java
enum Feature {
    CACHE;

    private int hits;

    void hit() {
        hits++;
    }

    int hits() {
        return hits;
    }
}
~~~

Đây là code hợp lệ về cú pháp, nhưng đồng thời chứa **shared mutable state**. Với nhiều threads, `hits++` không atomic và có thể dẫn đến lost updates/data races.

### 20.1. Chương trình cho thấy reference aliasing

Lưu **`EnumMutableStateDemo.java`**:

~~~java
public class EnumMutableStateDemo {
    enum Feature {
        CACHE;

        private int hits;

        void hit() {
            hits++;
        }

        int hits() {
            return hits;
        }
    }

    public static void main(String[] args) {
        Feature first = Feature.CACHE;
        Feature second = Feature.valueOf("CACHE");

        System.out.println("same object=" + (first == second));

        first.hit();
        second.hit();

        System.out.println("first hits=" + first.hits());
        System.out.println("second hits=" + second.hits());
    }
}
~~~

Chạy:

~~~bash
javac EnumMutableStateDemo.java
java EnumMutableStateDemo
~~~

Output:

~~~text
same object=true
first hits=2
second hits=2
~~~

Chỉ vì instance field `hits` là **không static** không có nghĩa mỗi biến `first`/`second` nhận riêng một `Feature` object. Cả hai aliases đều chỉ `Feature.CACHE` và sửa cùng field.

### 20.2. Khi thực sự cần shared mutable state?

Một enum singleton có thể giữ một thread-safe shared service/counter nếu đó là thiết kế có chủ đích. Hãy dùng synchronization, atomic classes, lifecycle và testing thích hợp. Tuy nhiên, với enum biểu thị **giá trị domain**, ưu tiên **private final immutable fields**, còn mutable business state nên nằm trong service/aggregate được quản lý tách biệt.

## 21. Defensive copying với mutable fields trong enum

`final` chỉ khóa **reference field**, không làm object được trỏ tới bất biến. Nếu một enum constant nhận array và lưu raw reference, array có thể bị mutate qua accessor hoặc alias khác.

### 21.1. Bản sao defensive cho array field

Lưu **`EnumDefensiveCopyDemo.java`**:

~~~java
import java.util.Arrays;

public class EnumDefensiveCopyDemo {
    enum Palette {
        BASIC(new int[] {1, 2, 3}),
        EXTENDED(new int[] {4, 5});

        private final int[] colors;

        Palette(int[] colors) {
            this.colors = colors.clone();
        }

        int[] copyColors() {
            return colors.clone();
        }

        int checksumForDemo() {
            return Arrays.stream(colors).sum();
        }
    }

    public static void main(String[] args) {
        int[] received = Palette.BASIC.copyColors();
        received[0] = 99;

        System.out.println("received=" +
                Arrays.toString(received));
        System.out.println("stored sum=" +
                Palette.BASIC.checksumForDemo());
        System.out.println("extended sum=" +
                Palette.EXTENDED.checksumForDemo());
    }
}
~~~

Chạy:

~~~bash
javac EnumDefensiveCopyDemo.java
java EnumDefensiveCopyDemo
~~~

Output:

~~~text
received=[99, 2, 3]
stored sum=6
extended sum=9
~~~

Enum constructor sao chép input array, accessor trả copy thay vì raw internal representation. `Arrays.stream` chỉ dùng để demo tổng, không phải cryptographic checksum. Với `List<MutableItem>`, copy list structure chưa chắc đủ: mutable elements có thể cần được chuyển sang immutable values hoặc copy thích hợp.

**Đặc biệt:** arrays được tạo trực tiếp làm arguments cho enum constants và không lộ ra ở snippet này, nhưng defensive copy vẫn là API discipline hữu ích khi constructor signature nhận mutable references.

## 22. EnumSet và EnumMap tận dụng tập constants hữu hạn

Java cung cấp `EnumSet<E extends Enum<E>>` và `EnumMap<K extends Enum<K>,V>` để làm việc với enum keys/sets theo cách chuyên dụng.

`EnumSet` đại diện một tập các constants của cùng enum class. `EnumMap` dùng enum constants làm keys và quản lý values. Cả hai dùng enum identity/domain; nếu dùng mutable values trong EnumMap, những values ấy **không tự trở thành immutable**.

### 22.1. Chương trình runnable

Lưu **`EnumCollectionsDemo.java`**:

~~~java
import java.util.EnumMap;
import java.util.EnumSet;

public class EnumCollectionsDemo {
    enum Permission {
        READ(1),
        WRITE(2),
        EXECUTE(4);

        private final int mask;

        Permission(int mask) {
            this.mask = mask;
        }

        int mask() {
            return mask;
        }
    }

    public static void main(String[] args) {
        EnumSet<Permission> granted =
                EnumSet.of(Permission.READ, Permission.WRITE);

        int combined = 0;
        for (Permission permission : granted) {
            combined |= permission.mask();
        }

        EnumMap<Permission, Integer> limits =
                new EnumMap<>(Permission.class);
        limits.put(Permission.READ, 2);
        limits.put(Permission.WRITE, 1);
        limits.put(Permission.EXECUTE, 0);

        System.out.println("mask=" + combined);
        System.out.println("can write=" +
                granted.contains(Permission.WRITE));
        System.out.println("execute limit=" +
                limits.get(Permission.EXECUTE));
    }
}
~~~

Chạy:

~~~bash
javac EnumCollectionsDemo.java
java EnumCollectionsDemo
~~~

Output:

~~~text
mask=3
can write=true
execute limit=0
~~~

Đây là ví dụ domain permission có `mask` private final, nên bit mask không bị suy từ `ordinal()`. Constants vẫn là objects kiểu Permission, dùng trong EnumSet/EnumMap mà không tạo lại instances.

## 23. Phương thức có thể dùng `name()`, nhưng label nghiệp vụ nên tách riêng

Nếu enum tên `HTTP_404` được đổi trong code, `name()` cũng đổi. Nếu một giao thức bên ngoài yêu cầu một code bền vững, constructor có thể nhận code tường minh:

~~~java
enum ResultCode {
    SUCCESS("ok"),
    NOT_FOUND("not_found");

    private final String wireCode;

    ResultCode(String wireCode) {
        this.wireCode = wireCode;
    }

    String wireCode() {
        return wireCode;
    }
}
~~~

Caller có thể serialize `wireCode()` sang JSON/database thay vì dùng `ordinal()`, và tạo static lookup nếu muốn parse theo wire code. Không nên dùng `toString()` nếu nó phục vụ localization/display text có thể thay đổi.

### 23.1. Constructor validation

Enum constructor có thể reject input bất hợp lệ qua unchecked exception. Nhưng nhớ rằng điều này xảy ra **lúc enum class init**; lỗi có thể khiến initialization thất bại, làm phần code đầu tiên truy cập enum gặp `ExceptionInInitializerError` hoặc hậu quả liên quan `NoClassDefFoundError` về sau tùy path.

Vì constants là declarations cố định trong source, thông thường phát hiện lỗi cấu hình constants từ test/build sớm tốt hơn là để production mới kích hoạt class initialization.

### 23.2. Đừng đoán `toString()` = `name()` khi có override

Mặc định `toString()` của Enum trả tên, nhưng enum có thể override. Khi parse qua `valueOf(String)`, input phải là **name** của constant, không phải arbitrary display label. Nếu parse external codes, tự tạo method `fromWireCode(String)` với semantics, xử lý null/unknown rõ ràng.

## 24. Enum method được kế thừa và không được override tùy ý

Mọi enum kế thừa từ `java.lang.Enum`. Một số methods do platform quy định là `final`:

- `name()`
- `ordinal()`
- `equals(Object)`
- `hashCode()`
- `compareTo(...)`
- `getDeclaringClass()`
- `clone()` được thiết kế ngăn clone enum constants.

Ngược lại, `toString()` có thể được override. Bạn cũng có thể viết methods domain riêng như `isTerminal()`, `price()`, `apply()`, `description()`.

Các method `values()` và `valueOf(String)` được compiler khai báo ngầm cho enum; không tự khai fields/methods trùng signatures với members sinh ngầm. Điều này giữ API enum nhất quán.

### 24.1. Không clone enums để tạo constant thứ hai

Enum instances là objects hữu hạn theo declaration. Nếu bạn cần **nhiều instances có runtime data khác nhau**, không nên ép enum thành mutable per-request object. Hãy dùng enum làm **loại/chiến lược** và một record/class giữ data của từng request:

~~~java
enum Channel {
    EMAIL, SMS
}

record Message(Channel channel, String text) {
}
~~~

Mảnh trên hợp lệ trong Java 17 ở một file/scope thích hợp. Mỗi Message record instance có data riêng, còn Channel constants được chia sẻ an toàn khi chúng không mang state mutable.

## 25. Gọi static method của enum khi enum đang khởi tạo: cẩn thận vòng phụ thuộc

Ngay cả khi một helper method hợp lệ về name resolution, nó có thể đọc **partial state** khi class chưa initialize xong. Không dùng constructor để gọi một static lookup method mà lookup lại dựa vào map chưa được xây.

Ví dụ không nên làm:

~~~java
enum BadDesign {
    A, B;

    private static final java.util.Map<String, BadDesign> TABLE =
            new java.util.HashMap<>();

    BadDesign() {
        // register(this); // Tránh gọi helper đọc TABLE ở đây.
    }

    private static void register(BadDesign value) {
        TABLE.put(value.name(), value);
    }
}
~~~

Những dòng comment là để minh họa anti-pattern. Nếu bỏ comment, gọi helper từ constructor có thể dẫn tới `NullPointerException` do `TABLE` chưa được initialized lúc A/B constructors đang chạy. **Đừng nói compiler chắc chắn bắt được mọi vòng phụ thuộc qua helper methods**: quy tắc JLS về direct static field reference ngăn một lớp lỗi, nhưng runtime initialization cycles phức tạp vẫn có thể xảy ra.

**Đúng:** static block điền TABLE sau constants như mục 11. Không cần mutable map toàn cục nếu chỉ có vài constants và một vòng `for(values())` trong static method là đủ hiệu năng.

## 26. Dùng enum constructor để thực hiện side effects có nên không?

Enum constructors chạy trong class initialization, thường chỉ một lần trong vòng đời enum class/classloader. Việc constructor:

- Ghi I/O,
- Mở network resources,
- Khởi tạo shared service,
- Đăng ký callback vào long-lived registry,
- Tạo thread,
- Kích hoạt loading của các classes có phụ thuộc vòng,

có thể làm behavior initialization khó dự đoán, khó test và khó cleanup. Một enum thường thích hợp với **immutable metadata** như code, label, priority, strategy.

Nếu một constant cần một mutable service, thường giữ service ở dependency container/application lifecycle và enum biểu thị key hoặc chuyển strategy qua interface. Đây không phải giới hạn cú pháp của Java mà là thiết kế giảm coupling và side effects.

### 26.1. Lựa chọn constructor validation

Tốt:

~~~java
enum Size {
    SMALL(1), LARGE(3);

    private final int factor;

    Size(int factor) {
        if (factor <= 0) {
            throw new IllegalArgumentException("factor");
        }
        this.factor = factor;
    }
}
~~~

Không tốt: constructor chạy code phụ thuộc network availability, kết nối database hoặc file system để tự điền final field khi một constant bất kỳ được truy cập lần đầu.

## 27. Enum là singleton cho từng constant — nhưng cần hiểu đúng phạm vi

Mỗi constant có một instance được JVM quản lý cho enum class trong classloader context thích hợp. Vì vậy:

- `Mode.FAST` được chia sẻ qua các callers.
- `Mode.FAST.getClass()` có thể là một constant-specific anonymous subclass nếu có class body; `getDeclaringClass()` là enum class gốc.
- Code đọc/ghi mutable field trên `FAST` không có per-request isolation.
- Không dùng raw Java reflection hay serialization hacks để cố tạo thêm enum constants: đây không phải public supported construction model.
- Nếu yêu cầu object mới cho mỗi nghiệp vụ, dùng record/class kết hợp enum field thay vì thêm state thay đổi tùy request lên constant.

### 27.1. Ví dụ enum constant kết hợp record request

Lưu **`EnumWithRecordDemo.java`**:

~~~java
public class EnumWithRecordDemo {
    enum Kind {
        BASIC(1), PREMIUM(2);

        private final int multiplier;

        Kind(int multiplier) {
            this.multiplier = multiplier;
        }

        int multiplier() {
            return multiplier;
        }
    }

    record Order(Kind kind, int amount) {
        int total() {
            return amount * kind.multiplier();
        }
    }

    public static void main(String[] args) {
        Order a = new Order(Kind.BASIC, 10);
        Order b = new Order(Kind.PREMIUM, 10);

        System.out.println("basic=" + a.total());
        System.out.println("premium=" + b.total());
        System.out.println("same kind object=" +
                (a.kind() == Kind.BASIC));
        System.out.println("different order objects=" + (a != b));
    }
}
~~~

Chạy:

~~~bash
javac EnumWithRecordDemo.java
java EnumWithRecordDemo
~~~

Output:

~~~text
basic=10
premium=20
same kind object=true
different order objects=true
~~~

Kind constants là immutable configuration/strategy values; mỗi Order record instance giữ amount khác nhau mà không mutate một global enum constant.

**Lưu ý số học:** đây chỉ là minh họa với số nguyên nhỏ; production money calculations cần kiểu số/quy tắc rounding/overflow thích hợp.

## 28. Debugging enum initialization và constructors

Khi code liên quan constructor enum có lỗi, hãy hỏi theo trình tự:

1. Constant declaration có arguments phù hợp overloaded constructor không?
2. Có dấu `;` để bắt đầu enum body declarations không?
3. Constructor access có đúng private hoặc package-default (được coi private) không?
4. Có gọi `super(...)` tường minh bị cấm không?
5. Có direct static field reference tới chính enum trong constructor/instance initializer mà không phải constant variable không?
6. Có method helper gián tiếp đọc static map chưa khởi tạo không?
7. Static map/list có được xây **sau** constants và tránh initialization cycle không?
8. Constructor có ném exception vì constant source value sai không?
9. Field initializer và instance block có dependency thứ tự sai không?
10. Có mutable field trên constant dẫn tới kết quả khác giữa các tests/threads không?
11. Có override `toString()` làm log khác `name()` không?
12. Có constant-specific class body khiến `getClass()` khác enum declaring class không?
13. Có đang dùng ordinal cho ID hoặc logic mà reorder constants làm thay kết quả không?
14. Có method signatures bị trùng với `values()`/`valueOf(String)` hoặc cố override final methods của Enum không?
15. Có dùng enum cho dữ liệu runtime nhiều instances vốn nên là class/record không?

### 28.1. Tránh kiểm thử kết quả bằng static initialization side effects toàn cục

Một unit test khởi tạo enum ở test method A có thể khiến constructor logs chỉ xuất hiện ở A, còn test B không thấy, do enum đã initialized trước đó. Đừng viết test giả định enum constructors chạy lại mỗi lần truy cập constant. Kiểm tra **trạng thái/method contract** thay vì count class-initialization logs nếu không kiểm soát classloader.

## 29. Chương trình tự kiểm thử hợp đồng (không cần JUnit)

Lưu **`EnumMembersContractTest.java`**:

~~~java
public class EnumMembersContractTest {
    enum Level {
        LOW(1), HIGH(5);

        private final int weight;

        Level(int weight) {
            if (weight <= 0) {
                throw new IllegalArgumentException("weight");
            }
            this.weight = weight;
        }

        int score(int base) {
            return base * weight;
        }
    }

    static void check(boolean ok, String description) {
        if (!ok) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        check(Level.values().length == 2, "size");
        check(Level.valueOf("LOW") == Level.LOW, "identity");
        check(Level.LOW.score(3) == 3, "low score");
        check(Level.HIGH.score(3) == 15, "high score");
        check(Level.LOW.ordinal() == 0, "declaration order");
        check(Level.LOW.getDeclaringClass() == Level.class,
                "declaring class");

        System.out.println("all enum member checks passed");
    }
}
~~~

Chạy:

~~~bash
javac EnumMembersContractTest.java
java EnumMembersContractTest
~~~

Output:

~~~text
all enum member checks passed
~~~

Method `check` gọi thực sự dù Java assertions `assert` bị tắt mặc định khi không bật `-ea`. Các checks này xác nhận fields/constructors/methods/identity theo một source declaration cụ thể; nó không cố đo nội bộ constructor bytecode hoặc classloader behavior.

## 30. Bảng so sánh: fields và methods nào thuộc enum class, constant, caller?

| Thành phần | Phạm vi/ý nghĩa | Ví dụ |
| --- | --- | --- |
| Enum constant | Một named instance được khởi tạo khi enum class init | `Priority.HIGH` |
| Implicit constant field | `public static final EnumType`, do compiler khai báo ngầm | `Priority.HIGH` field |
| Instance field | Một field nằm trên mỗi constant object | `private final int weight` |
| Instance method | Chạy với receiver một constant; dùng `this` | `HIGH.score(10)` |
| Static field | Dữ liệu thuộc enum class, shared | `private static final Map BY_CODE` |
| Constant variable | `final` primitive/String khởi tạo constant expression | `static final int FACTOR=10` |
| Static method | Gọi trên enum class, không cần constant receiver | `HttpStatus.fromCode(404)` |
| Enum constructor | Khởi tạo từng constant; private/implicit private | `Priority(int weight)` |
| Instance initializer | Chạy khi từng constant object được tạo | `{ count++; }` |
| Static initializer | Chạy khi enum class được initialized, sau constant declarations | `static { fillLookup(); }` |
| Constant-specific body | Anonymous subclass của enum cho một constant | `ADD { int calculate(...) {...} }` |
| Caller reference | Biến được gán một constant, không tạo constant mới | `Priority p = Priority.HIGH` |

**Phân biệt “per constant instance” và “per caller variable”:** vì `HIGH` là một object được chia sẻ, field instance `weight` nằm trên HIGH object, **không** được nhân bản cho mỗi biến tham chiếu tới HIGH.

## 31. Lỗi thường gặp và cách sửa

| Hiểu sai / thao tác sai | Đúng theo Java 17 |
| --- | --- |
| “Enum chỉ chứa constants, không có fields/methods.” | Enum có fields, constructors, instance/static methods và initializer blocks. |
| “`HIGH(9)` nghĩa tạo object mới mỗi khi dùng HIGH.” | Constant object được tạo khi enum class init, không phải mỗi lần đọc field. |
| “Constructor enum nên `public` để caller tạo thêm values.” | Public/protected enum constructors bị cấm; không `new` enum từ caller. |
| “Không khai constructor thì enum không có constructor.” | Compiler cung cấp default private no-arg constructor. |
| “Constructor enum có thể tự `super(...)`.” | Explicit superclass constructor invocation bị cấm. |
| “Dấu `;` sau enum constants luôn tùy ý.” | Cần khi còn body declarations. |
| “`static final Map` là constant variable.” | Không; Map không phải primitive/String constant expression. |
| “Constructor có thể thêm `this` vào static map của enum.” | Direct reference tới own non-constant static field bị cấm; xây map sau constants. |
| “Dùng helper method để đọc map từ constructor là an toàn.” | Có thể che initialization cycle, gây null/partial state. |
| “Static block và instance block cùng chạy mỗi constant.” | Instance block chạy theo mỗi constant; static block theo enum class. |
| “Tất cả static fields đã sẵn trước enum constants.” | Explicit static initializers sau constant declarations. |
| “Một constructor overload có parameter tự tạo no-arg overload.” | Không; cần khai riêng no-arg nếu constants dùng empty args. |
| “`this(...)` chaining của constructors bị cấm như `super(...)`.” | `this(...)` hợp lệ theo quy tắc constructor chaining. |
| “Mỗi enum constant bắt buộc có class body.” | Không; chỉ cần body cho behavior riêng hoặc abstract-method implementation. |
| “Constant-specific body có constructor riêng.” | Không; body là anonymous class, không khai constructor. |
| “Abstract enum method có thể bỏ qua ở một constant.” | Mọi constant phải implement concrete method theo JLS. |
| “`getClass()` của constant luôn bằng enum.class.” | Có thể khác khi constant-specific body; dùng `getDeclaringClass()`. |
| “`toString()` luôn bằng `name()`.” | toString có thể override; name final. |
| “`valueOf` nhận translated display label.” | Nó nhận tên constant khai báo, phân biệt hoa/thường. |
| “`ordinal()` là business ID ổn định.” | Phụ thuộc thứ tự declarations, không dùng để persist ID. |
| “Instance fields của enum được nhân bản theo mỗi caller reference.” | Mỗi constant chỉ có object/shared instance field riêng; aliases nhìn cùng state. |
| “`private final List/array` tự deep immutable.” | Reference final, mutable elements vẫn có thể thay đổi; defensive-copy khi cần. |
| “Enum không implement interface.” | Enum có thể implements interfaces. |
| “Enum tự khai generic type parameter `enum E<T>`.” | Enum declaration không có type parameter list. |
| “Test gọi constructor enum lại mỗi lần.” | Constructor chạy khi constant được khởi tạo, không được caller gọi lại. |

## 32. Bài tập ngắn có đáp án

**Câu 1.** `enum Size { SMALL, LARGE }` có constructor không?  
**Đáp án:** Có default private no-arg constructor được compiler khai báo ngầm.

**Câu 2.** `enum Coin { A(1); private Coin(int n) {...} }` tạo A bằng cách nào?  
**Đáp án:** Compiler tạo enum constant A khi enum class initialized và truyền 1 vào constructor.

**Câu 3.** Viết `public Coin(int n)` có hợp lệ không?  
**Đáp án:** Không, enum constructor không được public/protected.

**Câu 4.** Enum constructor không viết access modifier được coi là gì?  
**Đáp án:** `private` theo JLS.

**Câu 5.** Có thể gọi `super("A",0)` trong enum constructor?  
**Đáp án:** Không, explicit superclass constructor call bị cấm.

**Câu 6.** Có thể overload enum constructors và dùng `this(...)`?  
**Đáp án:** Có, đúng constructor chaining rules.

**Câu 7.** Khi enum có fields/methods sau constants, cần dấu gì?  
**Đáp án:** `;` ngay sau constants.

**Câu 8.** `private final int weight` trong enum thuộc đâu?  
**Đáp án:** Mỗi constant object có field instance riêng.

**Câu 9.** `static final int FACTOR=10` có dùng từ enum constructor được không?  
**Đáp án:** Được nếu đó là constant variable được khởi tạo từ constant expression.

**Câu 10.** `static final Integer BOXED=Integer.valueOf(10)` có là constant variable không?  
**Đáp án:** Không, Integer không phải primitive/String constant-variable type.

**Câu 11.** `static final Map` dùng trực tiếp từ enum constructor được không?  
**Đáp án:** Không, direct own non-constant static field reference bị JLS cấm ở constructor/instance initializers.

**Câu 12.** Vậy static lookup map nên xây lúc nào?  
**Đáp án:** Trong static initializer sau khi enum constants đã được tạo.

**Câu 13.** Constant objects được tạo theo thứ tự nào?  
**Đáp án:** Thứ tự khai báo constants khi enum class initialized.

**Câu 14.** Static initializer chạy cho từng constant không?  
**Đáp án:** Không, nó chạy một lần theo class initialization.

**Câu 15.** Instance initializer và instance field initializer chạy lúc nào so với body constructor?  
**Đáp án:** Theo source order trước phần thân constructor của constant, sau superclass chain.

**Câu 16.** `new EnumType()` từ application code được không?  
**Đáp án:** Không.

**Câu 17.** `values()` có tạo lại enum constants?  
**Đáp án:** Không; trả array mới chứa references tới các constants có sẵn.

**Câu 18.** `valueOf("PENDING")` dùng `toString()` hay `name()`?  
**Đáp án:** Tra theo constant name, không theo translated/custom toString.

**Câu 19.** Có override `name()` được không?  
**Đáp án:** Không, name final trong Enum.

**Câu 20.** Có override `toString()` được không?  
**Đáp án:** Có, để hiển thị label khác tên constant nếu cần.

**Câu 21.** Có override `equals` hoặc `hashCode` để so field values không?  
**Đáp án:** Không, Enum quy định final identity semantics cho các methods đó.

**Câu 22.** `ordinal()` có an toàn làm mã database không?  
**Đáp án:** Không nên, thay thứ tự/thêm constant làm ordinal đổi.

**Câu 23.** Nếu enum có abstract method thì một constant không có class body có hợp lệ?  
**Đáp án:** Không, mọi constants phải có implementation.

**Câu 24.** Constant-specific class body được khai constructor riêng không?  
**Đáp án:** Không, nó là anonymous class body.

**Câu 25.** Vì sao `getClass()` của ADD có class body có thể không bằng `Operation.class`?  
**Đáp án:** ADD có một anonymous subclass runtime class, nhưng declaring enum vẫn Operation.

**Câu 26.** Nếu hai biến tham chiếu `Feature.CACHE`, sửa mutable field qua biến thứ nhất có thể thấy qua biến thứ hai?  
**Đáp án:** Có, cùng một enum constant object.

**Câu 27.** Enum có thể implement `Transformer` interface?  
**Đáp án:** Có, rồi dùng enum constant qua interface reference.

**Câu 28.** Enum có generic type parameters như `enum Box<T>` không?  
**Đáp án:** Không, nhưng có thể implement generic interface với type arguments cụ thể.

**Câu 29.** `EnumSet` và `EnumMap` có ích gì?  
**Đáp án:** Cấu trúc collection chuyên dụng cho tập enum constants và enum keys.

**Câu 30.** Nếu một enum constant cần data runtime riêng mỗi request, nên làm gì?  
**Đáp án:** Dùng record/class riêng chứa enum key và per-request fields, không mutate global constant.

**Câu 31.** `final int[] colors` đủ làm enum immutable sâu chưa?  
**Đáp án:** Chưa; clone input/output nếu cần tách array mutable representation.

**Câu 32.** Constructor enum nên mở network/database connection mặc định không?  
**Đáp án:** Thường không; nên giữ constructor nhẹ, gán metadata/validate và quản lý services theo lifecycle khác.

**Câu 33.** Nếu class initialization thất bại do enum constructor throw, có thể cứ gọi constant khác để sửa?  
**Đáp án:** Không; enum class initialization có thể thất bại, subsequent uses trong classloader có hậu quả; sửa cấu hình/code.

**Câu 34.** Bài học cốt lõi về enum fields, methods, constructors?  
**Đáp án:** Constants là các instances hữu hạn, constructor private gán state cho từng constant; methods cung cấp behavior; shared static state chỉ khởi tạo sau constants theo JLS restrictions.

## 33. Checklist thiết kế enum có trạng thái

- [ ] Enum constants biểu diễn một tập giá trị hữu hạn và tương đối ổn định?
- [ ] Arguments của từng constant khớp constructors (kể cả overloads)?
- [ ] Body có fields/methods thì đã có `;` sau constants?
- [ ] Constructor không viết `public`/`protected` hoặc `super(...)` tường minh?
- [ ] Các instance fields chứa immutable values phù hợp hay có mutable aliases?
- [ ] Validation của constant arguments có đơn giản, deterministic, không cần external resource?
- [ ] Các fields cần giữ ổn định có `private final` và defensive copying phù hợp?
- [ ] Instance field initializers/blocks và constructor body có dependency order đúng?
- [ ] Constructor/instance initializers không trực tiếp đọc non-constant static field của chính enum?
- [ ] Có helper method gián tiếp gây circular static initialization không?
- [ ] Static lookup table được xây sau constants, phát hiện duplicate code?
- [ ] Static methods và instance methods đặt đúng trách nhiệm?
- [ ] Constant-specific behaviors có thực sự gọn hơn switch không?
- [ ] Nếu abstract method, mọi constants đã implement đúng?
- [ ] Có method cần `toString()` để hiển thị hay nên có `label()` riêng?
- [ ] Persistence/API đang dùng business code ổn định thay `ordinal()`?
- [ ] `valueOf` được dùng đúng với exact constant name, có xử lý input unknown?
- [ ] Có rủi ro shared mutable state khi enums được dùng qua nhiều threads?
- [ ] Có áp dụng `EnumSet`/`EnumMap` nếu phù hợp?
- [ ] Đã có tests identity, constructor state, methods, initialization order (nếu cần)?
- [ ] Nếu type cần per-request state/instances không giới hạn, đã cân nhắc record/class thay enum?

## 34. Tài liệu tham khảo

- Java Language Specification Java SE 17, [`8.9 — Enum Classes`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9): bản chất enum và tập constants.
- JLS Java SE 17, [`8.9.1 — Enum Constants`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.1): constructor arguments và constant-specific class bodies.
- JLS Java SE 17, [`8.9.2 — Enum Body Declarations`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.2): constructor visibility, explicit superclass call prohibition, own static field reference restriction.
- JLS Java SE 17, [`8.9.3 — Enum Members`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9.3): implicit constant fields, `values()`, `valueOf(String)`.
- JLS Java SE 17, [`4.12.4 — final Variables`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): khái niệm *constant variable*.
- JLS Java SE 17, [`12.4 — Initialization of Classes and Interfaces`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): active use/class initialization rules.
- JLS Java SE 17, [`12.5 — Creation of New Class Instances`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): instance initialization order.
- Java API SE 17, [`java.lang.Enum`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html): `name`, `ordinal`, `compareTo`, `getDeclaringClass` và identity semantics.
- Java API SE 17, [`java.util.EnumSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumSet.html): tập constants chuyên dụng.
- Java API SE 17, [`java.util.EnumMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html): map enum keys chuyên dụng.
- Java API SE 17, [`java.util.Map.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): unmodifiable lookup map snapshots.

## Kết luận

**Enum không chỉ là danh sách constants**: nó là một class đặc biệt, trong đó **mỗi constant là một instance được Java tạo trong lúc enum class initialization**. Constructor `private` hoặc ngầm định private nhận arguments khai báo ở mỗi constant, thiết lập instance fields và validation. Enum có instance/static methods, initializer blocks, interfaces, constant-specific anonymous subclasses và static lookup tables.

Ba điều cần nhớ nhất:

1. **Constructor enum không dành cho caller:** không `new` từ bên ngoài, không public/protected constructor và không `super(...)` tường minh. Constructor overloading với `this(...)` là hợp lệ.
2. **Khởi tạo đúng thứ tự:** constants được tạo theo thứ tự khai báo; instance fields/blocks chạy trước constructor body cho mỗi constant, explicit static initializers chạy sau constants. Không đọc non-constant own static field trực tiếp trong enum constructor/instance initializer; xây static lookup map sau constants.
3. **Fields nên đại diện state ổn định và methods đại diện behavior:** ưu tiên `private final` immutable data, chống mutable aliases khi cần, dùng business codes thay ordinal cho lưu trữ và tránh để enum constants trở thành global mutable objects.

Khi thiết kế theo các nguyên tắc ấy, enum trở thành một dạng *type-safe set of named instances with behavior* — gọn hơn các integer/string constants, khó tạo trạng thái không hợp lệ hơn và dễ kiểm thử trong Java 17+.
