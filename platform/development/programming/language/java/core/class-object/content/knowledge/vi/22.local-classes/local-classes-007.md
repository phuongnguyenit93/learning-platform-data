# Local enum và local record được ngầm định static trong Java

## Mục tiêu bài học

Kết thúc bài học, bạn có thể:

- Khai báo **local enum** và **local record** trong thân phương thức, constructor hoặc một block hợp lệ của Java 17.
- Giải thích chính xác từ **ngầm định `static`** (*implicitly static*) đối với hai kiểu này: chúng **không phải inner classes**, không nhận một enclosing instance ngầm và không tự bắt (*capture*) các biến local, tham số hoặc biến kiểu (*type parameter*) của phương thức bao quanh.
- Phân biệt chúng với **local normal class** (lớp cục bộ khai báo bằng `class`), vốn là inner class và có thể sử dụng biến local `final`/effectively final cùng enclosing instance khi điều kiện ngôn ngữ cho phép.
- Hiểu nghịch lý bề ngoài: được định nghĩa **ở trong block** nhưng vẫn **ngầm định static**; `static` ở đây nói về quan hệ với môi trường bao ngoài, **không** biến tất cả members hoặc instances của enum/record thành static.
- Nắm quy tắc **không viết từ khóa `static` tường minh** ở khai báo local enum/local record, cũng không thêm các access modifiers `public`/`protected`/`private` vào chính khai báo local type.
- Biết khi nào được dùng thành viên static của lớp bao ngoài, và khi nào phải **truyền dữ liệu tường minh** vào record constructor hoặc enum method.
- Khai thác record components, compact constructor, validation, accessors, `equals`/`hashCode`/`toString` và các enum constants, constructor, methods, `switch`, `values()` trong local scope.
- Hiểu ranh giới phạm vi (*scope*) của type name, tính ổn định của enum constants giữa các lần gọi method, khác biệt giữa object identity và value equality.
- Sử dụng local record như immutable data carrier một cách cẩn thận: `final` component field **không làm** nested array/list mutable trở nên bất biến sâu.
- Phân tích lỗi biên dịch thường gặp, sửa thiết kế và viết chương trình Java 17+ độc lập với stdout đáng tin.

> **Phiên bản:** Bài sử dụng Java 17 trở lên. Local records trở thành tính năng chính thức từ Java 16 (JEP 395). Java 17 cho phép khai báo local enum, local record và local interface trong block theo đặc tả Java SE 17. Các source snippets có chủ đích minh họa lỗi sẽ được comment hoặc ghi rõ **không phải chương trình độc lập có thể biên dịch**.

## 1. Local type là gì?

Một khai báo type cục bộ (*local type declaration*) nằm **trực tiếp trong một block**, không phải member của lớp hay package. Ví dụ, trong `main` có thể khai báo:

~~~java
public class Example {
    public static void main(String[] args) {
        enum Mode {
            FAST, SAFE
        }

        record Point(int x, int y) {
        }

        Mode mode = Mode.FAST;
        Point point = new Point(2, 3);
        System.out.println(mode);
        System.out.println(point);
    }
}
~~~

Hai kiểu `Mode` và `Point` chỉ có tên **hữu dụng trong scope của block** đó, nhưng chúng vẫn được Java compiler biên dịch thành các class files thích hợp. `Mode.FAST` là enum constant; `new Point(2,3)` là record object. Tên local type không thể được dùng tùy ý như một package-level hoặc member type từ nơi khác.

### 1.1. “Local” nói về phạm vi khai báo

- `Mode` được khai báo trong block của method.
- `Point` cũng được khai báo trong block ấy.
- Source code ở method khác không thể viết `new Example.Point(2,3)` vì Point **không phải member class của Example**.
- Một local type có **tên đơn** trong scope (`Point`, `Mode`); nó khác anonymous class không có type name do lập trình viên khai báo.
- Scope và shadowing tuân JLS `6.3/`6.4, và local class/interface declarations tuân JLS `14.3.

### 1.2. “Implicitly static” nói về enclosing context

`static` ngầm định **không** có nghĩa bản thân local record không thể có instances, instance methods hoặc fields. Nó có nghĩa:

1. Local enum/record là nested types thuộc nhóm **không phải inner classes**.
2. Chúng **không có một enclosing instance của class bao quanh** được cấp tự động.
3. Chúng **không có quyền truy cập ngầm** vào biến local, parameters, instance fields/methods và type variables của method/class bao quanh như local normal class có thể.
4. Chúng có thể làm việc với static members có quyền truy cập phù hợp, và có thể nhận **giá trị/reference tường minh** qua constructor hoặc method parameters.

Đây chính là ý nghĩa cần hiểu của tiêu đề bài: **local về vị trí**, nhưng **static về quan hệ với enclosing instance và capture**.

## 2. Chương trình đầu tiên: khai báo local enum và local record

Lưu **`LocalTypesFirstDemo.java`**:

~~~java
public class LocalTypesFirstDemo {
    public static void main(String[] args) {
        enum Level {
            LOW, MEDIUM, HIGH
        }

        record Score(String name, int points) {
            boolean passed() {
                return points >= 60;
            }
        }

        Level selected = Level.MEDIUM;
        Score lan = new Score("Lan", 75);
        Score minh = new Score("Minh", 45);

        System.out.println("level=" + selected);
        System.out.println("lan=" + lan);
        System.out.println("lan passed=" + lan.passed());
        System.out.println("minh passed=" + minh.passed());
    }
}
~~~

Chạy:

~~~bash
javac LocalTypesFirstDemo.java
java LocalTypesFirstDemo
~~~

**Stdout:**

~~~text
level=MEDIUM
lan=Score[name=Lan, points=75]
lan passed=true
minh passed=false
~~~

**Đọc kỹ:**

- `Level` và `Score` được định nghĩa **bên trong method**, không phải fields hoặc member classes của `LocalTypesFirstDemo`.
- Enum có ba **constants**. Sử dụng `Level.MEDIUM` không cần `new Level()`.
- Record có hai **components**: `String name` và `int points`. Java 17 sinh canonical constructor, component accessors `name()`/`points()`, `equals`, `hashCode` và `toString`.
- `passed()` là **instance method của record**, hoàn toàn hợp lệ dù local record implicitly static.
- Không có reference ngầm tới một `LocalTypesFirstDemo` instance, mà `main` là static method cũng không có `this`.

## 3. Bốn loại local declarations dễ bị nhầm

Trong Java 17, một block có thể chứa nhiều hình thức type declaration.

| Khai báo trong block | Inner class? | Implicitly static? | Capture effectively final local? | Có enclosing outer instance ngầm? |
| --- | --- | --- | --- | --- |
| `class Local { }` thông thường | Có | Không | Có, trong điều kiện quy định | Có thể có từ instance context |
| `enum LocalEnum { A }` | Không | **Có** | **Không** | **Không** |
| `record LocalRecord(int x) { }` | Không | **Có** | **Không** | **Không** |
| `interface LocalInterface { ... }` | Không | **Có** | **Không** | **Không** |

**Lưu ý bảng:** local normal class có thể capture effectively final local variables; việc có enclosing instance của một outer class phụ thuộc **nó được khai báo trong instance hay static context**. Trong static method, không có instance `this` của outer class để capture.

### 3.1. Local normal class không phải local record

~~~java
void process(int input) {
    int bonus = 10;

    class LocalCalculator {
        int calculate() {
            return input + bonus;
        }
    }

    // record LocalResult(int value) {
    //     int calculate() { return input + bonus; } // Sai.
    // }
}
~~~

`LocalCalculator` có thể dùng `input` và `bonus` vì chúng effectively final. Local record `LocalResult` không thể trực tiếp truy cập chúng theo cách ấy vì record implicitly static.

**Khắc phục:** lấy giá trị từ component mà record **được truyền tường minh** trong constructor, ví dụ `new LocalResult(input + bonus)`.

### 3.2. Tại sao không xem record là “class cục bộ có nhiều code sinh sẵn”?

Record cung cấp value-oriented state representation cùng các phương thức sinh tự động, nhưng còn có **ràng buộc static nesting** và **không capture enclosing locals**. Việc chuyển `class Local` thành `record Local(...)` có thể thay đổi cú pháp, API, inheritance, mutability và khả năng truy cập các biến của phương thức.

## 4. Local enum, local record đều không viết `static` tường minh

**Đúng:**

~~~java
void demo() {
    enum Mode { FAST, SAFE }
    record Point(int x, int y) { }
}
~~~

**Sai khi là local declarations trong block:**

~~~java
void invalid() {
    // static enum Mode { FAST, SAFE } // Compile-time error.
    // static record Point(int x, int y) { } // Compile-time error.
}
~~~

JLS `14.3 cấm `static` modifier xuất hiện **tường minh** ở local class/interface declarations, kể cả trường hợp type đã **implicitly static**. Các access modifiers `public`, `protected`, `private` cũng không được áp dụng cho **chính local declaration**.

Đừng suy luận rằng “ngầm định static” đồng nghĩa “được hoặc phải viết `static`”. Với một **member record/enum** được khai báo trong thân Outer thì các quy tắc member khác; ở đây đề bài là **local**.

### 4.1. Vị trí và cú pháp khác member enum/record

~~~java
class Outer {
    enum MemberMode { A, B }
    record MemberPoint(int x, int y) { }

    void method() {
        enum LocalMode { C, D }
        record LocalPoint(int x, int y) { }
    }
}
~~~

- `Outer.MemberMode` và `Outer.MemberPoint` là **member types**.
- `LocalMode` và `LocalPoint` là **local types** của block method; ngoài method không truy cập bằng `Outer.LocalMode` hoặc `Outer.LocalPoint`.
- Cả enum/record **member** và enum/record **local** đều là nested static về semantics, nhưng cách **truy cập tên** khác nhau.

## 5. Chương trình: local normal class có capture, local record nhận data

Lưu **`LocalCaptureContrastDemo.java`**:

~~~java
public class LocalCaptureContrastDemo {
    public static void main(String[] args) {
        int base = 10; // Effectively final.

        class Adder {
            int add(int value) {
                return base + value;
            }
        }

        record Sum(int left, int right) {
            int value() {
                return left + right;
            }
        }

        Adder adder = new Adder();
        Sum sum = new Sum(base, 5);

        System.out.println("class result=" + adder.add(5));
        System.out.println("record result=" + sum.value());
        System.out.println("record left=" + sum.left());
    }
}
~~~

Chạy:

~~~bash
javac LocalCaptureContrastDemo.java
java LocalCaptureContrastDemo
~~~

Output:

~~~text
class result=15
record result=15
record left=10
~~~

Trong `Adder.add`, `base` là **captured local variable** của enclosing method. Vì Java capture chỉ các locals final/effectively final theo quy tắc, `base` không được gán lại sau đó trong ví dụ.

Trong `Sum.value`, `left` và `right` là **record component fields**. Dòng `new Sum(base,5)` truyền **giá trị** của base vào constructor. Record không capture biến `base` bằng cách bí mật lưu enclosing frame/owner.

### 5.1. Nếu base thay đổi thì sao?

Nếu thêm:

~~~java
// base++;
~~~

sau khi khai báo local class `Adder` có tham chiếu `base`, method có thể bị compiler từ chối vì biến không còn effectively final. Đó là quy tắc **capture của local normal class**; local record đã chọn cách nhận dữ liệu qua constructor không phải chịu cùng kiểu capture ấy.

Nếu muốn tính toán với state mutable, hãy thiết kế **dữ liệu nào đi vào constructor/method ở thời điểm nào**, thay vì kỳ vọng local record đọc biến enclosing method trực tiếp.

## 6. Local record không có `Outer.this`

Một local record được khai báo trong instance method của `Outer` vẫn **không phải inner class** và không có enclosing Outer instance ngầm.

~~~java
class Outer {
    private int multiplier = 3;

    void run(int amount) {
        // record Result(int number) {
        //     int multiplied() {
        //         return multiplier * number; // Sai: instance field ngầm.
        //     }
        // }

        record Result(int number, int multiplier) {
            int multiplied() {
                return multiplier * number;
            }
        }

        System.out.println(new Result(amount, multiplier).multiplied());
    }
}
~~~

Cách đúng là **đưa state cần thiết thành component** `multiplier`, rồi khởi tạo bằng `new Result(amount, multiplier)` trong method. Chính instance method `run` có quyền đọc `multiplier` của Outer; local record tự nó chỉ biết component được truyền.

### 6.1. Không dùng `Outer.this` để lách ràng buộc

Trong code instance method của một local normal class, `Outer.this` có thể là qualified-this hợp lệ. Nhưng trong body local record, không có enclosing Outer instance để `Outer.this` tham chiếu. Muốn record method làm việc với Outer, hãy truyền reference Outer tường minh vào method/constructor; đồng thời cân nhắc lifetime/ownership và bất biến sâu của record.

## 7. Chương trình: record chỉ dùng dữ liệu đã truyền

Lưu **`RecordOuterAccessDemo.java`**:

~~~java
public class RecordOuterAccessDemo {
    private final int multiplier;

    public RecordOuterAccessDemo(int multiplier) {
        this.multiplier = multiplier;
    }

    int calculate(int amount) {
        record Calculation(int amount, int multiplier) {
            int result() {
                return amount * multiplier;
            }
        }

        Calculation value = new Calculation(amount, multiplier);
        return value.result();
    }

    public static void main(String[] args) {
        RecordOuterAccessDemo service = new RecordOuterAccessDemo(4);

        System.out.println("first=" + service.calculate(3));
        System.out.println("second=" + service.calculate(5));
    }
}
~~~

Chạy:

~~~bash
javac RecordOuterAccessDemo.java
java RecordOuterAccessDemo
~~~

Output:

~~~text
first=12
second=20
~~~

- `calculate` có `this` là `RecordOuterAccessDemo` instance và được đọc field `multiplier`.
- Local record `Calculation` không ngầm giữ service instance.
- `Calculation.result()` chỉ đọc `amount` và `multiplier` từ chính record object.
- Nếu business cần truy cập live service trong record, có thể truyền service reference tường minh, nhưng lúc ấy record giữ một reference tới service; không tự suy ra sẽ tránh mọi vấn đề ownership/memory.

## 8. Local enum cũng không capture biến local

Một enum được định nghĩa trong block vẫn là **enum type** với các constants cố định. Nó không nhận enclosing method frame/locals như local normal class.

**Sai:**

~~~java
void invalid(int threshold) {
    // enum Decision {
    //     ACCEPT;
    //
    //     boolean allowed(int n) {
    //         return n >= threshold; // Sai: threshold từ method ngoài.
    //     }
    // }
}
~~~

**Đúng:** làm method của enum nhận threshold một cách **tường minh**:

~~~java
void valid(int threshold) {
    enum Decision {
        ACCEPT;

        boolean allowed(int n, int limit) {
            return n >= limit;
        }
    }

    System.out.println(Decision.ACCEPT.allowed(10, threshold));
}
~~~

Các đoạn trên minh họa bên trong một enclosing class phù hợp; chúng **không có method main riêng**.

### 8.1. Enum constant constructor khác record constructor

Enum constants được khai báo trong chính enum body, ví dụ `LOW(5)`/`HIGH(10)`, cùng private constructors nội bộ. Caller **không** dùng `new LocalEnum(...)`.

Record thì khác: caller có thể `new LocalRecord(componentValues...)` từ đúng scope/type access. Cú pháp khởi tạo phù hợp **không ảnh hưởng** việc cả hai được implicitly static.

## 9. Chương trình: truyền method arguments cho local enum

Lưu **`LocalEnumMethodDemo.java`**:

~~~java
public class LocalEnumMethodDemo {
    static void demonstrate(int input, int limit) {
        enum Rule {
            AT_LEAST {
                boolean test(int value, int bound) {
                    return value >= bound;
                }
            },
            ABOVE {
                boolean test(int value, int bound) {
                    return value > bound;
                }
            };

            abstract boolean test(int value, int bound);
        }

        System.out.println("at least=" +
                Rule.AT_LEAST.test(input, limit));
        System.out.println("above=" +
                Rule.ABOVE.test(input, limit));
    }

    public static void main(String[] args) {
        demonstrate(10, 10);
        demonstrate(11, 10);
    }
}
~~~

Chạy:

~~~bash
javac LocalEnumMethodDemo.java
java LocalEnumMethodDemo
~~~

Output:

~~~text
at least=true
above=false
at least=true
above=true
~~~

`Rule` không đọc trực tiếp `input` hay `limit` từ method `demonstrate`. Thay vào đó, cả hai là **explicit method arguments** trong `test(input,limit)`. Enum constants có class bodies cung cấp implementation riêng cho `test`; đó là polymorphism của enum constants, không phải capture.

### 9.1. Tại sao không khai báo static local enum để xử lý lỗi capture?

Vì local enum đã implicitly static, viết thêm `static enum Rule` là compile-time error. Giải pháp đúng là **đổi đường dữ liệu**, không thêm modifier.

## 10. Static members của Outer vẫn truy cập được

Giả sử một enclosing class có static constant hoặc static method:

~~~java
class Outer {
    private static final int SCALE = 2;

    void example() {
        record Measure(int value) {
            int scaled() {
                return value * SCALE;
            }
        }

        System.out.println(new Measure(3).scaled());
    }
}
~~~

Vì `SCALE` là static member, local record có thể truy cập nó khi access phù hợp. Điều này **không** tạo enclosing Outer instance. Nếu `SCALE` là instance field, cùng source expression trong body record không được phép truy cập ngầm.

Tương tự, local enum có thể tham chiếu static members của enclosing class theo quy tắc name resolution/access.

**Cẩn trọng:** static **mutable** fields có thể thay đổi giữa các lần gọi; “implicitly static” không đảm bảo logic phụ thuộc static mutable state là thread-safe hay side-effect-free.

## 11. Chương trình: local enum và record đọc static field

Lưu **`LocalStaticContextDemo.java`**:

~~~java
public class LocalStaticContextDemo {
    private static final String PREFIX = "APP";
    private static final int BONUS = 5;

    void show(int points) {
        enum Category {
            NORMAL, BONUS
        }

        record Entry(int points) {
            String label() {
                return PREFIX + ":" + points;
            }

            int withBonus() {
                return points + BONUS;
            }
        }

        Entry entry = new Entry(points);
        Category category = Category.BONUS;

        System.out.println("category=" + category);
        System.out.println("label=" + entry.label());
        System.out.println("total=" + entry.withBonus());
    }

    public static void main(String[] args) {
        new LocalStaticContextDemo().show(10);
    }
}
~~~

Chạy:

~~~bash
javac LocalStaticContextDemo.java
java LocalStaticContextDemo
~~~

Output:

~~~text
category=BONUS
label=APP:10
total=15
~~~

Trong `Entry.label()`, `PREFIX` là **static field của enclosing class**. `BONUS` cũng static. Không phải `Entry` capture `this` hay truyền ngầm một `LocalStaticContextDemo` object vào constructor.

### 11.1. Sự khác nhau giữa static field và local constant

Một biến local được viết `final int limit=5;` trong enclosing method **vẫn là local variable**; nó không trở thành static field chỉ vì giá trị là compile-time constant. Local enum/record **không capture local variables**, kể cả local final constants. Đừng trộn hai khái niệm này.

## 12. Type parameters của phương thức: không được dùng ngầm bên trong local record

Ví dụ một generic method:

~~~java
<T> void method(T input) {
    // record Bad(T value) { } // Sai: T thuộc generic method ngoài.

    record Box<U>(U value) { } // Đúng: U là type parameter của Box.

    Box<T> box = new Box<>(input); // T dùng ở code method bên ngoài.
    System.out.println(box.value());
}
~~~

Tại sao?

- `T` được khai báo bởi method `method`.
- Local record implicitly static nên **body/signature của record không dùng trực tiếp type variable T** của enclosing method.
- `Box<U>` tự khai báo type parameter `U`, hoàn toàn hợp lệ.
- Bên ngoài local record declaration nhưng vẫn trong `method`, `T` đang ở trong scope nên `Box<T> box = ...` được dùng.
- Dữ liệu `input` được **truyền tường minh** tới constructor, không capture.

Tương tự, một local enum không được tham chiếu enclosing generic method type parameter. Bản thân enum **không khai báo type parameters** như `enum Mode<T>`.

### 12.1. Với generic Outer<T> thì sao?

Nếu method nằm trong `class Outer<T>`, local record/enum không được dùng `T` của generic Outer trực tiếp trong phần type declaration chỉ vì code nằm trong class. Muốn data generic, local record có thể khai báo riêng `record Data<U>(U value)` và bên ngoài tạo `Data<T>`.

## 13. Chương trình: generic local record tự khai báo type parameter

Lưu **`GenericLocalRecordDemo.java`**:

~~~java
public class GenericLocalRecordDemo {
    static <T> void display(T input) {
        record Box<U>(U value) {
            String describe() {
                return String.valueOf(value);
            }
        }

        Box<T> box = new Box<>(input);
        System.out.println("boxed=" + box.describe());
    }

    public static void main(String[] args) {
        display("Java");
        display(17);
    }
}
~~~

Chạy:

~~~bash
javac GenericLocalRecordDemo.java
java GenericLocalRecordDemo
~~~

Output:

~~~text
boxed=Java
boxed=17
~~~

`U` thuộc về record. `T` chỉ được dùng tại nơi **khởi tạo `Box<T>`** trong body generic method. Đây là cách giữ type safety mà không phá tính implicitly static.

### 13.1. Đối chiếu với local normal class

Một local normal class trong generic method có thể sử dụng enclosing type parameter theo quy tắc hợp lệ, nhưng local enum/record không thể dựa vào enclosing generic context như vậy. Khi di chuyển code từ local class sang local record, hãy kiểm tra cả **capture variables** lẫn **type parameters**.

## 14. Enum constants là instances có tên, không được `new` từ bên ngoài

Local enum:

~~~java
enum Direction {
    NORTH, SOUTH, EAST, WEST
}
~~~

Sử dụng:

~~~java
Direction north = Direction.NORTH;
Direction parsed = Direction.valueOf("SOUTH");
Direction[] choices = Direction.values();
~~~

- `Direction.NORTH` là enum constant tồn tại theo lifecycle của enum class.
- Caller không viết `new Direction()`.
- `Direction.values()` tạo array biểu diễn các constants ở thời điểm gọi; sửa array nhận về không thay chính tập constants nội bộ của enum.
- `valueOf` phân biệt hoa/thường theo tên constant, không tự normalize input.
- `switch` expression trên enum hoạt động bình thường trong scope.

### 14.1. Local scope không tạo bộ enum constants mới mỗi lần gọi method

Từ “local” chỉ nơi type name được khai báo. Nó không có nghĩa mỗi lần method gọi sẽ định nghĩa một enum **kiểu mới** hoặc tạo lại constants mới theo mỗi invocation. Enum constants là members của enum class, class được JVM load/initialize theo classloader lifecycle.

Điều này khác với `new Record(...)`: mỗi lần `new` tạo record object mới thông thường.

## 15. Chương trình: enum constants xuyên nhiều lần gọi method

Lưu **`LocalEnumIdentityDemo.java`**:

~~~java
public class LocalEnumIdentityDemo {
    static Object token() {
        enum Token {
            SINGLE
        }
        return Token.SINGLE;
    }

    static Object value(int number) {
        record Number(int number) {
        }
        return new Number(number);
    }

    public static void main(String[] args) {
        Object a = token();
        Object b = token();

        Object first = value(7);
        Object second = value(7);

        System.out.println("same enum constant=" + (a == b));
        System.out.println("same record object=" + (first == second));
        System.out.println("equal record value=" +
                first.equals(second));
    }
}
~~~

Chạy:

~~~bash
javac LocalEnumIdentityDemo.java
java LocalEnumIdentityDemo
~~~

Output:

~~~text
same enum constant=true
same record object=false
equal record value=true
~~~

`Token` có local scope, nhưng `SINGLE` là cùng một enum constant giữa các calls. `Number` là local record type cố định đối với declaration, còn mỗi `new Number(7)` tạo object khác; `equals` do record sinh ra so giá trị component number nên true.

Dùng `==` với enum constants là idiom hợp lệ để so identity. Với record value objects, thông thường dùng `equals` khi muốn so giá trị, không dùng `==`.

## 16. Local enum có constructor và instance members riêng

“Implicitly static” không ngăn local enum khai báo **instance fields**, **constructors**, **instance methods**. Static status nói về outer relation, không ngăn enum instances có state riêng.

Ví dụ enum strategy với hai rates:

~~~java
enum Rate {
    STANDARD(10),
    REDUCED(5);

    private final int percent;

    Rate(int percent) {
        this.percent = percent;
    }

    int percent() {
        return percent;
    }
}
~~~

Đây là snippet nên đặt **trong một method/block hợp lệ**. Enum constructor không được gọi bằng `new Rate(10)` từ caller; `STANDARD(10)` và `REDUCED(5)` khai báo arguments cho constants trong enum body.

### 16.1. Tại sao không lấy biến method làm enum constructor argument?

Một local enum không được capture method parameters. Viết `STANDARD(rateFromOuterMethod)` trong enum declaration sẽ cố truy cập enclosing local, là lỗi. Nếu rate phụ thuộc runtime, enum method có thể nhận rate hoặc trả strategy được apply trên input; hoặc chọn record nếu cần mỗi object có value khác nhau.

## 17. Chương trình: local enum có constructor riêng

Lưu **`LocalEnumPolicyDemo.java`**:

~~~java
public class LocalEnumPolicyDemo {
    static void calculate(int price) {
        enum Rate {
            STANDARD(10),
            REDUCED(5);

            private final int percent;

            Rate(int percent) {
                this.percent = percent;
            }

            int taxed(int amount) {
                return amount + amount * percent / 100;
            }

            int percent() {
                return percent;
            }
        }

        System.out.println("standard percent=" +
                Rate.STANDARD.percent());
        System.out.println("standard total=" +
                Rate.STANDARD.taxed(price));
        System.out.println("reduced total=" +
                Rate.REDUCED.taxed(price));
    }

    public static void main(String[] args) {
        calculate(200);
    }
}
~~~

Chạy:

~~~bash
javac LocalEnumPolicyDemo.java
java LocalEnumPolicyDemo
~~~

Output:

~~~text
standard percent=10
standard total=220
reduced total=210
~~~

Enum field `percent` thuộc về enum constant instances. `price` thuộc enclosing method và chỉ vào enum method qua `taxed(price)`. Giá trị `percent` được đưa vào từ enum declarations, không từ capture local.

Đây là mô hình đơn giản hóa số nguyên; thuế/tiền trong hệ thống thực cần quy tắc làm tròn, precision, currency và overflow phù hợp.

## 18. Local record có constructor validation và methods

Một record thường đại diện **dữ liệu không đổi theo API của components**. Với local record:

~~~java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }

    int length() {
        return end - start + 1;
    }
}
~~~

- `start`, `end` là components và final fields tương ứng.
- Compact constructor `Range { ... }` validate values trước khi object được xây hoàn chỉnh.
- `length()` là instance method, hợp lệ trong implicitly static record.
- Không thể khai báo additional **instance fields** không phải record components theo Java record restrictions.
- Không thể `extends SomeBase` vì record extends `java.lang.Record` theo ngữ nghĩa; record có thể `implements` interfaces.

Đừng nhầm khả năng có methods/compact constructors với quyền dùng local variables bên ngoài. Những methods chỉ có state được cấp hợp lệ (components/parameters/static data).

## 19. Chương trình: validation của local record

Lưu **`LocalRecordValidationDemo.java`**:

~~~java
public class LocalRecordValidationDemo {
    public static void main(String[] args) {
        record Range(int start, int end) {
            Range {
                if (start > end) {
                    throw new IllegalArgumentException(
                            "start must be <= end");
                }
            }

            int length() {
                return end - start + 1;
            }
        }

        Range a = new Range(2, 5);
        System.out.println("range=" + a);
        System.out.println("length=" + a.length());

        try {
            new Range(8, 3);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid range rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac LocalRecordValidationDemo.java
java LocalRecordValidationDemo
~~~

Output:

~~~text
range=Range[start=2, end=5]
length=4
invalid range rejected
~~~

Constructor validation ở local record vẫn giống cơ chế record nói chung. Vì exception được catch với thông báo tự in, stdout không phụ thuộc stack trace/exception message.

**Lưu ý:** `length()` có nguy cơ overflow nếu dùng extreme values; ví dụ cố ý dùng small ints. Code production nên chọn kiểu/kiểm tra số học phù hợp với domain.

## 20. Local record `equals`, `hashCode`, `toString` tự sinh

Record cung cấp value-oriented methods dựa trên component fields. Ví dụ:

~~~java
record Key(String name, int version) {
}
~~~

Hai Key instances khác nhau có thể `equals` true nếu components equal; hợp đồng `hashCode` yêu cầu khi equal thì hash bằng nhau.

Đây là một lý do local record hữu ích để tạo **dữ liệu trung gian** trong phương thức thay vì viết thủ công local normal class nhiều boilerplate.

Tuy nhiên, **records không deep immutable tự động**. Nếu component là `int[]`, accessor trả array reference nếu không override, array mutable, generated equality mặc định không so nội dung mảng như `Arrays.equals`. Cần lựa chọn representation và defensive copy.

### 20.1. Chương trình: equality theo components

Lưu **`LocalRecordEqualityDemo.java`**:

~~~java
public class LocalRecordEqualityDemo {
    public static void main(String[] args) {
        record Key(String name, int version) {
        }

        Key a = new Key("A", 1);
        Key b = new Key("A", 1);
        Key c = new Key("A", 2);

        System.out.println("same object=" + (a == b));
        System.out.println("equal values=" + a.equals(b));
        System.out.println("equal hashes=" +
                (a.hashCode() == b.hashCode()));
        System.out.println("different version=" + a.equals(c));
        System.out.println("text=" + a);
    }
}
~~~

Chạy:

~~~bash
javac LocalRecordEqualityDemo.java
java LocalRecordEqualityDemo
~~~

Output:

~~~text
same object=false
equal values=true
equal hashes=true
different version=false
text=Key[name=A, version=1]
~~~

Nếu cần snapshot giá trị để làm key trong `HashMap`, local record với **immutable component values** là lựa chọn gọn. Nhưng nếu key chứa mutable component, equality/hash có thể biến đổi hoặc có array identity semantics khó mong đợi.

## 21. Vì sao static context không đồng nghĩa deep immutability?

Local record được implicitly static, nhưng vẫn có thể giữ reference tới mutable data nếu **được truyền tường minh**:

~~~java
void demo(int[] source) {
    record Payload(int[] data) {
    }

    Payload payload = new Payload(source);
    source[0] = 9;
    // payload.data()[0] cũng quan sát 9.
}
~~~

`Payload` không capture `source` ngầm; record constructor đã nhận reference `source` **tường minh**. `data` field final chỉ ngăn gán lại reference bên trong object theo rules, không khóa các elements của array.

Bài học: **không capture outer context** và **giữ mutable reference như một component** là hai chuyện khác nhau. Implicit static không phải cơ chế “deep freeze”.

### 21.1. Cách làm immutable snapshot đủ sâu cho `int[]`

~~~java
record Frozen(int[] values) {
    Frozen {
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }
}
~~~

Vẫn nên cân nhắc custom `equals`/`hashCode` nếu muốn content-value semantics của array, vì record-generated methods không tự gọi `Arrays.equals` cho array components. Trường hợp đơn giản hơn thường là dùng một immutable List of immutable elements khi contract cho phép.

## 22. Chương trình: local record có defensive copies

Lưu **`LocalRecordArrayDemo.java`**:

~~~java
import java.util.Arrays;

public class LocalRecordArrayDemo {
    public static void main(String[] args) {
        record Sample(int[] values) {
            Sample {
                values = values.clone();
            }

            @Override
            public int[] values() {
                return values.clone();
            }

            int sum() {
                return Arrays.stream(values).sum();
            }
        }

        int[] source = {1, 2, 3};
        Sample sample = new Sample(source);

        source[0] = 9;
        int[] read = sample.values();
        read[1] = 8;

        System.out.println("source=" + Arrays.toString(source));
        System.out.println("read copy=" + Arrays.toString(read));
        System.out.println("stored sum=" + sample.sum());
    }
}
~~~

Chạy:

~~~bash
javac LocalRecordArrayDemo.java
java LocalRecordArrayDemo
~~~

Output:

~~~text
source=[9, 2, 3]
read copy=[1, 8, 3]
stored sum=6
~~~

Đây là ví dụ tập trung vào **ngăn mutate internal array qua input/output aliases**. Nó **không** định nghĩa lại array-content equality; các record instances vẫn dùng generated component equality, nên `Sample` với array ở đây không phải value object đầy đủ cho mọi tình huống `HashSet`/`HashMap` cần so contents.

Nếu yêu cầu so nội dung array, có thể override `equals`/`hashCode` nhất quán và kiểm thử. Không gộp deep immutability và value equality thành một khái niệm.

## 23. Local enum kết hợp `switch` expression

Local enum hoàn toàn tương thích với `switch` statement/expression. Java 17 hỗ trợ switch expression tiêu chuẩn:

~~~java
enum Command {
    ADD, SUBTRACT
}

int answer = switch (command) {
    case ADD -> a + b;
    case SUBTRACT -> a - b;
};
~~~

Đây là **mảnh code minh họa** cần `command`, `a`, `b` được khai báo trong block phù hợp. Vì enum constants là tập hữu hạn, compiler kiểm tra tính exhaustiveness theo rules tương ứng.

### 23.1. Chương trình switch expression đầy đủ

Lưu **`LocalEnumSwitchDemo.java`**:

~~~java
public class LocalEnumSwitchDemo {
    public static void main(String[] args) {
        enum Operation {
            ADD, SUBTRACT, MULTIPLY
        }

        int a = 8;
        int b = 3;

        for (Operation op : Operation.values()) {
            int result = switch (op) {
                case ADD -> a + b;
                case SUBTRACT -> a - b;
                case MULTIPLY -> a * b;
            };
            System.out.println(op + "=" + result);
        }
    }
}
~~~

Chạy:

~~~bash
javac LocalEnumSwitchDemo.java
java LocalEnumSwitchDemo
~~~

Output:

~~~text
ADD=11
SUBTRACT=5
MULTIPLY=24
~~~

Thứ tự `Operation.values()` là thứ tự các enum constants được khai báo. Không phụ thuộc HashMap ordering hay thread scheduling nên output xác định.

Nếu sau này thêm một enum constant mới mà không bổ sung case thích hợp, source `switch` expression có thể cần được cập nhật để đảm bảo exhaustiveness.

## 24. Scope: type name chỉ tồn tại trong block hợp lệ

Một local enum/record có phạm vi **theo source-code block**. Không thể truy cập type name đó từ một method bên cạnh bằng tên `Outer.LocalRecord`.

Ví dụ:

~~~java
class Example {
    void first() {
        record Temp(int n) {
        }

        Temp temp = new Temp(1); // Hợp lệ.
    }

    void second() {
        // Temp t = new Temp(2); // Không thấy local type Temp.
    }
}
~~~

Local record không trở thành nested **member** class chỉ vì compiler tạo một `.class` file bên trong cùng compilation unit. File name/bytecode name là chi tiết triển khai, không làm thay đổi Java source-level scope.

### 24.1. Khai báo trong block nhỏ hơn

~~~java
void demo() {
    {
        enum State { OPEN, CLOSED }
        State state = State.OPEN;
        System.out.println(state);
    }

    // State another = State.CLOSED; // Ngoài scope.
}
~~~

Nếu type chỉ cần ở một nhánh xử lý nhỏ, đặt nó trong block phù hợp giúp giảm phạm vi tên và làm rõ mục đích của type.

### 24.2. Không dùng local record làm API public trực tiếp

Một method có thể trả `Object` hoặc một interface/supertype accessible chứa instance của local record, nhưng callers ngoài method **không thể nhắc tới tên local record trực tiếp**.

Nếu type là một phần quan trọng của API công khai nhiều nơi cần tạo/dùng, hãy cân nhắc member record hoặc top-level record thay vì local record.

## 25. Dùng local record như implementation detail sau interface

Một local record có thể `implements` interface accessible ở scope ngoài và được trả dưới kiểu interface đó.

### 25.1. Chương trình runnable

Lưu **`LocalRecordInterfaceDemo.java`**:

~~~java
public class LocalRecordInterfaceDemo {
    interface Description {
        String text();
    }

    static Description create(String name, int count) {
        record DescriptionValue(
                String name, int count) implements Description {
            @Override
            public String text() {
                return name + ":" + count;
            }
        }

        return new DescriptionValue(name, count);
    }

    public static void main(String[] args) {
        Description a = create("A", 2);
        Description b = create("B", 3);

        System.out.println(a.text());
        System.out.println(b.text());
    }
}
~~~

Chạy:

~~~bash
javac LocalRecordInterfaceDemo.java
java LocalRecordInterfaceDemo
~~~

Output:

~~~text
A:2
B:3
~~~

Caller dùng interface `Description` mà không cần biết implementation type `DescriptionValue` nằm trong body method `create`. `DescriptionValue` nhận cả `name` và `count` tường minh, không capture method parameters.

**Lưu ý:** return type là interface do outer class khai báo, phù hợp scope. Nếu caller cần truy cập component accessors `name()`/`count()` cụ thể, interface này chưa công bố các methods đó; phải thiết kế API thích hợp.

## 26. Các khai báo local không được có access modifier ngoài block

Sai:

~~~java
void invalid() {
    // public record Point(int x, int y) { } // Compile-time error.
    // private enum Mode { A } // Compile-time error.
    // protected record Pair(int a, int b) { } // Compile-time error.
}
~~~

Vì khai báo local type nằm **trong block**, không phải member type để `public/protected/private` mang ý nghĩa member visibility thông thường.

Nếu muốn type public, đặt nó thành member/top-level declaration với access phù hợp.

### 26.1. `final` trên record và enum

Records vốn implicitly final theo Java record semantics; enums cũng có quy tắc final/sealed đặc biệt theo enum constant class bodies. Không thêm modifiers tùy tiện. Đặc biệt, local declaration còn có các hạn chế modifiers riêng như `static`, `sealed`, `non-sealed`.

Nội dung thiết yếu cần nhớ của bài là: **ngầm định static nhưng không khai báo static tường minh**; đừng dùng modifiers để sửa lỗi thiếu dữ liệu enclosing context.

## 27. Static nesting và lifetime: không giữ outer tự động

Local normal class được khai báo trong instance method có thể sử dụng outer `this` và effectively final locals; object của nó có thể giữ references cần thiết. Ngược lại, local enum/record implicitly static không có enclosing instance ngầm.

Điều này có ích nếu bạn muốn tạo data carrier mà **không vô tình giữ nguyên enclosing service/controller object** trong một callback hoặc cache.

Nhưng:

~~~java
record Holder(Service service) {
}
~~~

là local record **có component reference tới Service**, nếu được truyền tường minh. Nó vẫn có thể giữ Service reachable trong GC reference graph. Tính implicitly static **không cấm** strong references explicit.

### 27.1. Không xem local type là “chỉ tồn tại trong stack”

- Scope của **tên kiểu** là lexical.
- Lifetime của **object instance** phụ thuộc references và GC reachability, không phụ thuộc vào việc method đã return.
- Enum constants có class-level lifecycle theo JVM/classloader, không được tạo mới mỗi lần gọi block.
- Record instances có thể được đưa vào collection, callback hoặc trả dưới interface/Object và sống lâu hơn method đã tạo chúng.

Do đó, local không đồng nghĩa ephemeral object, và static không đồng nghĩa leak-proof.

## 28. Chương trình: local record sống ngoài method qua interface

Lưu **`LocalRecordLifetimeDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LocalRecordLifetimeDemo {
    interface View {
        String render();
    }

    static View build(String label) {
        record Snapshot(String text) implements View {
            @Override
            public String render() {
                return text;
            }
        }

        return new Snapshot(label);
    }

    public static void main(String[] args) {
        List<View> saved = new ArrayList<>();

        saved.add(build("first"));
        saved.add(build("second"));

        for (View item : saved) {
            System.out.println(item.render());
        }
    }
}
~~~

Chạy:

~~~bash
javac LocalRecordLifetimeDemo.java
java LocalRecordLifetimeDemo
~~~

Output:

~~~text
first
second
~~~

Dù `Snapshot` được khai báo trong `build`, record object được lưu qua interface `View` trong `saved` và tiếp tục sử dụng sau khi mỗi invocation `build` kết thúc.

Điều này không vi phạm local scope: method `main` không trực tiếp viết tên type `Snapshot`. Nó chỉ dùng public/interface-level contract `View`.

## 29. Nested local record trong generic context: phân biệt type declaration với construction

Xét:

~~~java
class Container<T> {
    void save(T item) {
        record Snapshot<U>(U data) {
        }

        Snapshot<T> snapshot = new Snapshot<>(item);
        System.out.println(snapshot.data());
    }
}
~~~

- `T` thuộc class `Container<T>`.
- Local record declaration tự khai báo `U` và sử dụng `U` trong components.
- Code sau khai báo record (trong instance method) có thể dùng `T` để **tham số hóa Snapshot**: `Snapshot<T>`.
- Local record body không có quyền trực tiếp nhắc tới `T` của Outer để khai báo component kiểu `T`.
- Không có enclosing `Container<T>` object được truyền ngầm cho `Snapshot`.

**Đây là khác biệt đặc trưng của implicitly static local types.**

### 29.1. Khi local enum cần type-generic behavior?

Enum không thể khai báo generic type parameters cho chính enum. Nếu logic cần nhận data thuộc kiểu `T` từ enclosing generic method, cho enum method nhận `Object`/interface phù hợp hoặc đặt transformation ở generic method/caller. Không cố viết `enum Operation<T>`.

## 30. So sánh local enum/record với lambda và anonymous class

Các constructs có thể cùng xuất hiện trong một method, nhưng không cùng cơ chế capture:

| Construct | Có tên type khai báo trong source? | Bắt enclosing local variables? | Có enclosing outer implicit? |
| --- | --- | --- | --- |
| Local normal class `class Task` | Có | Có thể nếu effectively final | Có thể nếu instance context |
| Local enum `enum Mode` | Có | Không | Không |
| Local record `record Data` | Có | Không | Không |
| Anonymous class `new Runnable(){...}` | Không | Có thể | Có thể theo context |
| Lambda `() -> ...` | Không tự khai báo một named class type | Có thể | `this` có lexical meaning, có thể capture receiver |
| Static nested member class | Có tên member type | Không capture locals | Không |

Nếu cần một callback đọc local variable effectively final, lambda hoặc local normal class có thể thích hợp. Nếu chỉ cần một **snapshot data value**, local record thường biểu đạt rõ hơn: components phải được truyền tường minh.

Không khẳng định rằng lambda luôn tạo object/class file theo một bytecode pattern cố định; representation là chi tiết runtime/compiler.

## 31. Lỗi biên dịch: đọc đúng nguyên nhân

### 31.1. Sai vì direct local variable access

~~~java
void demo(int offset) {
    // record Bad(int value) {
    //     int total() { return value + offset; } // Sai.
    // }
}
~~~

**Nguyên nhân:** `offset` là enclosing method parameter, local record không capture.  
**Sửa:** khai báo `record Good(int value, int offset)` và tạo `new Good(value,offset)`.

### 31.2. Sai vì instance field access

~~~java
class Owner {
    int x = 2;

    void demo() {
        // enum Mode {
        //     A;
        //     int x() { return Owner.this.x; } // Sai.
        // }
    }
}
~~~

**Nguyên nhân:** local enum implicitly static, không có enclosing Owner instance.  
**Sửa:** truyền Owner reference vào enum method, hoặc truyền giá trị int mong muốn; tránh giữ owner nếu chỉ cần snapshot int.

### 31.3. Sai vì method type variable

~~~java
<T> void demo(T input) {
    // record Data(T value) { } // Sai.
    record Data<U>(U value) { }
    Data<T> data = new Data<>(input);
}
~~~

**Nguyên nhân:** local record không dùng type parameter `T` enclosing context trong declaration.  
**Sửa:** record tự khai báo `U`.

### 31.4. Sai vì modifier `static` explicit

~~~java
void demo() {
    // static enum Mode { A } // Sai.
    // static record Data(int n) { } // Sai.
}
~~~

**Nguyên nhân:** JLS `14.3 không cho viết `static` trên local type declaration, dù type implicitly static.  
**Sửa:** bỏ modifier.

### 31.5. Sai vì access modifier

~~~java
void demo() {
    // public record Data(int n) { } // Sai.
}
~~~

**Nguyên nhân:** local declarations không là public member declarations.  
**Sửa:** bỏ modifier; hoặc chuyển type sang member/top-level nếu cần public API.

### 31.6. Sai vì type name ngoài scope

~~~java
void make() {
    record Data(int n) { }
}

// Data d = new Data(1); // Không có Data trong scope ở đây.
~~~

**Nguyên nhân:** local type name không thành member type.  
**Sửa:** dùng type trong scope, hoặc trả dưới interface/supertype, hoặc chuyển declaration ra member-level.

## 32. Quy trình chọn loại type cho code trong method

Nếu muốn khai báo một type nhỏ trong method, hỏi:

1. Có một tập constants cố định, cần identity enum và `switch`? → **Local enum**.
2. Có vài giá trị cần đi chung và value semantics? → **Local record**.
3. Cần capture effectively final method variables/enclosing state? → **Local normal class** hoặc lambda/anonymous class phù hợp.
4. Cần type xuất hiện trong nhiều methods hoặc public API? → **Member/top-level enum hoặc record**.
5. Cần dữ liệu runtime từ enclosing method nhưng vẫn muốn local record? → **Truyền values qua canonical constructor**.
6. Cần dùng operation với runtime threshold trong local enum? → **Truyền threshold vào enum method**.
7. Cần generic method type parameter bên trong local record? → **Tạo record có type parameter riêng `U`**, instantiate bằng `Box<T>` ngoài declaration.
8. Có mutable arrays/lists? → **Defensive copies/value representation** nếu cần immutable snapshot.
9. Có nested state hoặc services lớn? → **Cân nhắc ownership/lifetime**, không vô tình giữ explicit reference.
10. Có code chạy trước Java 16? → **Kiểm tra version/toolchain**; đừng dùng cú pháp Java 17 với source level quá cũ.

**Quy tắc ngắn:** nếu thấy local enum/record đang cố đọc “biến của method bên ngoài”, đó thường là dấu hiệu bạn cần **đặt biến ấy thành input tường minh**.

## 33. Chương trình tích hợp: local enum + record không capture state

Lưu **`LocalTypesIntegrationDemo.java`**:

~~~java
import java.util.List;

public class LocalTypesIntegrationDemo {
    static void summarize(List<Integer> inputs, int threshold) {
        enum Verdict {
            PASS, FAIL
        }

        record Result(int input, int threshold, Verdict verdict) {
            String text() {
                return input + "/" + threshold + "=" + verdict;
            }
        }

        for (int input : inputs) {
            Verdict verdict = input >= threshold
                    ? Verdict.PASS : Verdict.FAIL;

            Result result = new Result(input, threshold, verdict);
            System.out.println(result.text());
        }
    }

    public static void main(String[] args) {
        summarize(List.of(3, 5, 8), 5);
    }
}
~~~

Chạy:

~~~bash
javac LocalTypesIntegrationDemo.java
java LocalTypesIntegrationDemo
~~~

Output:

~~~text
3/5=FAIL
5/5=PASS
8/5=PASS
~~~

**Phân tích:**

- Method `summarize` nhận `inputs` và `threshold`.
- Local enum `Verdict` giữ hai constants, không capture `threshold`.
- So sánh `input >= threshold` được thực hiện **ở ngoài local enum**, trong method scope.
- Local record `Result` giữ ba components được cung cấp **tường minh** qua constructor.
- Record method `text` chỉ đọc components của chính nó.
- Nếu cần sử dụng `Result` trong code khác, hãy chuyển record ra member/top-level scope hoặc expose một interface phù hợp.

Đây là pattern hữu ích cho dữ liệu trung gian của pipelines, tính toán phân loại, validation và transformation mà không làm phình public class API.

## 34. Kiểm thử sự khác nhau bằng assertions thực thi luôn

Lưu **`LocalTypesContractTest.java`**:

~~~java
public class LocalTypesContractTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static Object constant() {
        enum Token {
            ONE
        }
        return Token.ONE;
    }

    public static void main(String[] args) {
        record Item(String name, int count) {
        }

        Item a = new Item("A", 1);
        Item b = new Item("A", 1);

        check(a != b, "separate record identity");
        check(a.equals(b), "record value equality");
        check(a.hashCode() == b.hashCode(), "hash contract");

        check(constant() == constant(), "enum singleton constant");

        int local = 7;
        record Snapshot(int value) {
        }
        check(new Snapshot(local).value() == 7,
                "explicit constructor input");

        System.out.println("local enum and record checks passed");
    }
}
~~~

Chạy:

~~~bash
javac LocalTypesContractTest.java
java LocalTypesContractTest
~~~

Output:

~~~text
local enum and record checks passed
~~~

Method `check` được gọi luôn, không phụ thuộc Java `assert` vốn tắt mặc định nếu không chạy với `-ea`. Test kiểm tra identity/value behavior, không dùng reflection tên compiler-generated class hay dự đoán GC.

## 35. Những quan niệm sai phổ biến

| Hiểu sai | Kết luận đúng |
| --- | --- |
| “Local enum là inner class vì nằm trong method.” | Local enum **implicitly static**, không phải inner class. |
| “Local record có enclosing instance vì nằm trong instance method.” | Không; record **implicitly static**. |
| “Implicitly static nghĩa phải viết `static`.” | Sai: local declaration **không được** viết `static` explicit. |
| “Static record không tạo object được.” | Vẫn tạo `new LocalRecord(...)` được trong scope. |
| “Static enum không có instance methods.” | Enum constants có methods, fields/constructors theo enum rules. |
| “Local record tự capture local params.” | Không; truyền qua components/constructor. |
| “Local enum có thể dùng effectively final locals vì local class có thể.” | Không; local enum khác local normal class. |
| “`final int n` trong method là static field.” | Không. Final local vẫn là local variable. |
| “Local record không thể đọc static fields.” | Có thể đọc static members accessible của enclosing class. |
| “Generic method `T` dùng trực tiếp trong local record declaration.” | Không; local record khai báo generic `U` riêng. |
| “Enum hỗ trợ generic parameters như `enum E<T>`.” | Không. |
| “Local enum constants được tạo mới mỗi lần gọi method.” | Không; enum constants gắn với enum class lifecycle. |
| “Local record type được tạo mới mỗi lần chạy loop.” | Type declaration là một type; `new` tạo instance mới, không định nghĩa class mới mỗi iteration. |
| “Record copy sâu array component.” | Không; array mutable, cần defensive copy nếu cần snapshot. |
| “Record luôn so array theo contents.” | Không; generated array component equality theo identity. |
| “Local type name dùng được từ method khác bằng `Outer.Name`.” | Không; local type không phải member type. |
| “Local record không thể implement interface.” | Có thể implement accessible interface. |
| “Local enum phải tạo bằng `new`.” | Không; dùng named constants. |
| “Local record có thể extends class tùy ý.” | Không; record extends `java.lang.Record` theo semantics. |
| “Implicitly static ⇒ dữ liệu bất biến sâu, thread-safe.” | Không. Static relation ≠ immutable nested graph/thread safety. |
| “Local type object không sống quá method.” | Object có thể sống lâu nếu reference còn reachable. |
| “Truyền một Owner reference vào record sẽ không bao giờ giữ Owner.” | Nếu component giữ Owner reference, GC graph vẫn có thể giữ Owner. |
| “Local enum dùng switch thì thứ tự constants do hash random.” | `values()` theo thứ tự khai báo constants. |
| “Lỗi capture có thể sửa bằng modifier `private`.” | Không. Local type modifiers/capture rules khác nhau. |

## 36. Checklist khi code review local enum/record

- [ ] Code đang dùng JDK và `--release`/`--source` phù hợp Java 17+?
- [ ] `enum`/`record` được khai báo trong một block hợp lệ?
- [ ] Khai báo có vô tình ghi `static` tường minh không?
- [ ] Có access modifiers `public`/`protected`/`private` không hợp lệ không?
- [ ] Có đang coi chúng là inner classes không?
- [ ] Body local record/enum có cố trực tiếp đọc local variables/method parameters không?
- [ ] Có cố dùng instance field, instance method hoặc `Outer.this` từ local enum/record không?
- [ ] Dữ liệu method có được truyền qua constructor/components hoặc explicit method args không?
- [ ] Có dùng static members của enclosing class mà quên thread-safety nếu mutable không?
- [ ] Trong generic method/outer, local record có type variable riêng `U` khi cần không?
- [ ] Type name có bị dùng ngoài lexical scope không?
- [ ] Có cần nâng type lên member/top-level nếu callers khác phải nhắc tên type không?
- [ ] Local enum constants có được so bằng `==`/switch` đúng mục đích không?
- [ ] Local record có validation, equality và hash behavior phù hợp domain không?
- [ ] Components dạng arrays/lists/custom objects có mutable không?
- [ ] Nếu data snapshot, có defensive-copy cả input/output mutable references không?
- [ ] Code có nhầm “static” với singleton, immutable hoặc không cấp phát objects không?
- [ ] Các ví dụ có class/file name khớp và runnable với `javac`/`java` không?

## 37. Bài tập luyện tập và lời giải

**Câu 1.** `enum LocalMode { A, B }` trong method có phải inner class không?  
**Đáp án:** Không. Local enum implicitly static.

**Câu 2.** `record LocalPair(int a,int b)` trong method có phải inner class không?  
**Đáp án:** Không. Local record implicitly static.

**Câu 3.** Vì sao không viết `static record R(int n)` trong method?  
**Đáp án:** Local type declaration không được ghi modifier `static` tường minh theo JLS `14.3.

**Câu 4.** Local normal class có thể capture `final int bonus` của method không?  
**Đáp án:** Có trong các điều kiện hợp lệ (local final/effectively final), khác local enum/record.

**Câu 5.** Local record có thể truy cập `bonus` trực tiếp vì bonus effectively final không?  
**Đáp án:** Không, không capture enclosing local.

**Câu 6.** Cách đưa bonus vào local record?  
**Đáp án:** Thêm component `bonus` và truyền `new R(value,bonus)`.

**Câu 7.** Local enum method muốn dùng threshold runtime của caller thì làm sao?  
**Đáp án:** Thêm method parameter và gọi `Rule.A.test(value,threshold)`.

**Câu 8.** Local enum có instance fields không?  
**Đáp án:** Có, như enum constant state `percent` trong constructor.

**Câu 9.** Local record có thể khai báo instance method không?  
**Đáp án:** Có, như `sum()`/`passed()`.

**Câu 10.** Local enum muốn dùng `Outer.this.name` từ instance method bao ngoài được không?  
**Đáp án:** Không, không có enclosing Outer instance ngầm.

**Câu 11.** Local record muốn dùng instance field của Outer thì truyền thế nào?  
**Đáp án:** Truyền value field hoặc Outer reference tường minh theo contract, không dùng implicit capture.

**Câu 12.** Static field accessible của Outer có được đọc trong local record không?  
**Đáp án:** Có theo static access rules.

**Câu 13.** `final int local = 7` có phải static member không?  
**Đáp án:** Không, vẫn là local variable.

**Câu 14.** Generic method `<T> void run(T x)` có thể khai báo `record R(T x)` không?  
**Đáp án:** Không, T thuộc enclosing generic method.

**Câu 15.** Sửa bài trên bằng cách nào?  
**Đáp án:** `record R<U>(U x){}` và trong method `R<T> r = new R<>(x)`.

**Câu 16.** Local enum `enum E<T>` có hợp lệ không?  
**Đáp án:** Không; enum declarations không có generic type parameters riêng.

**Câu 17.** Hai lần gọi method trả `Token.ONE` của cùng local enum declaration có giống reference không?  
**Đáp án:** Có trong cùng classloader/class lifecycle thông thường.

**Câu 18.** Hai lần `new LocalRecord(1)` có cùng reference không?  
**Đáp án:** Không, hai object allocations riêng; có thể `equals` true.

**Câu 19.** `LocalRecord` nằm trong method có được gọi là `Outer.LocalRecord` từ method khác không?  
**Đáp án:** Không, nó không phải member type.

**Câu 20.** Có thể return local record object dưới interface không?  
**Đáp án:** Có nếu local record implements interface ấy và return type accessible.

**Câu 21.** Local record có thể dùng compact constructor để validate không?  
**Đáp án:** Có.

**Câu 22.** Local record `record D(int[] arr)` có deep immutable tự động không?  
**Đáp án:** Không; array reference được giữ, elements mutable nếu không defensive-copy.

**Câu 23.** Vì sao clone array input thôi vẫn chưa đủ bảo vệ accessor?  
**Đáp án:** Getter trả raw array nội bộ vẫn lộ mutation; cần defensive output copy nếu snapshot.

**Câu 24.** Generated `equals` của record với `int[]` có so nội dung array như `Arrays.equals` không?  
**Đáp án:** Không. Array component mặc định dựa trên reference identity.

**Câu 25.** `LocalEnum.values()` có thứ tự constants không?  
**Đáp án:** Có, theo thứ tự khai báo enum constants.

**Câu 26.** Local record type được định nghĩa lại mỗi lần chạy vòng lặp không?  
**Đáp án:** Không; runtime tạo instances khi có `new`, không định nghĩa type mới mỗi iteration.

**Câu 27.** `static` ngầm định có nghĩa record không còn bất kỳ instance member nào không?  
**Đáp án:** Không, record vẫn có component fields và instance methods.

**Câu 28.** Local enum/record có thể khai báo `public` ở local type declaration không?  
**Đáp án:** Không.

**Câu 29.** Nếu type cần được chia sẻ qua nhiều methods, nên đặt ở đâu?  
**Đáp án:** Xem xét member hoặc top-level enum/record thay vì local.

**Câu 30.** Có thể dùng local record làm giá trị tạm trong pipeline?  
**Đáp án:** Có, đặc biệt khi components được truyền tường minh và type không cần lộ ra API.

**Câu 31.** Local record có thể giữ Owner object nếu truyền Owner vào component không?  
**Đáp án:** Có; implicitly static chỉ loại bỏ enclosing reference ngầm, không ngăn explicit references.

**Câu 32.** Muốn local enum khác nhau ở mỗi invocation thì sao?  
**Đáp án:** Enum constants không tái tạo theo invocation; nếu cần value runtime thay đổi, dùng record/class instance hoặc truyền runtime data vào methods.

**Câu 33.** JDK 17 có cần bật `--enable-preview` để dùng local record không?  
**Đáp án:** Không, local records đã là tính năng chính thức từ Java 16.

**Câu 34.** Khác biệt ngắn gọn nhất giữa local normal class và local record/enum?  
**Đáp án:** Local normal class là inner class và có thể capture context phù hợp; local record/enum implicitly static, **không capture enclosing locals/instance**.

## 38. Tài liệu tham khảo

- Java Language Specification, Java SE 17, [`14.3 — Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3): local declarations, modifiers và implicitly static local enum/record.
- Java Language Specification, [`8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): loại nào là inner, loại nào không.
- Java Language Specification, [`8.9 — Enum Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9): enum declarations, constants và implicitly static nested enum.
- Java Language Specification, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record components, constructors, methods và static nested status.
- Java Language Specification, [`6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): lexical scope của type declarations.
- Java Language Specification, [`6.5.5.1 — Simple Type Names](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5.5.1): hạn chế tham chiếu type names/type variables từ static context.
- Java Language Specification, [`6.5.6.1 — Simple Expression Names](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5.6.1): giới hạn truy cập các biến enclosing.
- Oracle Java 17 Language Guide, [Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): local records implicitly static, examples.
- OpenJDK JEP 395, [Records](https://openjdk.org/jeps/395): records được chuẩn hóa trong Java 16.
- Java Language Specification, [`15.28 — Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): local final constant khác static field.
- Java API, [`java.lang.Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): base class và value methods của records.
- Java API, [`java.lang.Enum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html): enum base class và methods.

## Kết luận

**Local enum và local record đều được ngầm định static trong Java 17** dù chúng được khai báo bên trong method/block. Điều này không biến chúng thành member static của enclosing class; tên kiểu vẫn có **local scope**, và khai báo **không được** ghi từ khóa `static` tường minh.

Sự khác biệt quan trọng so với local normal class là **không capture enclosing method variables, parameters, generic type variables hay Outer instance**. Khi cần runtime data, truyền qua record components/constructor hoặc các arguments của enum methods; khi chỉ cần static data, dùng static members accessible một cách rõ ràng.

Local enum phù hợp cho tập constants cố định và `switch`/strategy; local record phù hợp cho dữ liệu trung gian có value semantics và constructor validation. Đừng nhầm implicitly static với “không thể tạo instances”, “tự deep immutable”, “singleton mỗi invocation” hay “tự tránh mọi memory retention”. Hiểu đúng **scope + static relation + explicit data flow** sẽ giúp sử dụng cả hai kiểu cục bộ an toàn, rõ ràng trong Java hiện đại.
