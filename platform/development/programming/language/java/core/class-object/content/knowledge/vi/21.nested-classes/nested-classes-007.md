# Thành viên static trong inner class: quy tắc hiện hành từ Java 16

> **Phạm vi:** Java Core → Class/Object → Lớp lồng nhau. Mã chạy với JDK 17+; quy tắc ngôn ngữ về `static` trong inner class được nới lỏng **từ Java 16**.

## 1. Điều cần nhớ trước tiên

Từ **Java SE 16**, một **inner class** có thể khai báo các **static members** và **static initializers** mà trước đó không được phép. Điều này gồm, tùy loại khai báo phù hợp với cú pháp Java:

- Static fields, kể cả fields **không phải compile-time constants**.
- Static methods.
- Static initialization blocks (`static { ... }`).
- Static nested member classes.
- Những member types vốn **implicitly static**, như member interface, enum và record (với versions Java hỗ trợ các loại đó).

**Nhưng inner class không vì thế biến thành static nested class.** Một *non-static member inner class* vẫn cần một enclosing instance khi bạn tạo instance của chính nó từ bên ngoài enclosing object.

Ví dụ hợp lệ với Java 17:

~~~java
class Outer {
    class Inner {
        static int count = 0;       // Hợp lệ từ Java 16.
        static void reset() {       // Hợp lệ từ Java 16.
            count = 0;
        }
        static {
            count = 10;             // Hợp lệ từ Java 16.
        }
        static class Helper {       // Hợp lệ từ Java 16.
        }
    }
}
~~~

Đây là **đoạn khai báo minh họa**, chưa có `main`. Trước Java 16, không thể đặt các declarations kiểu này trực tiếp trong một inner class, ngoại trừ trường hợp **static final constant variables** đáp ứng các điều kiện ngôn ngữ.

Một cách nói dễ nhớ:

**Java 15 trở về trước: static member trong inner class bị hạn chế mạnh. Java 16 trở đi: inner class được khai báo static members, nhưng bản thân nó vẫn là inner class.**

Bài này phân tích chính xác định nghĩa inner class; phân biệt static nested và non-static inner; thay đổi trước/sau Java 16; constant variable; cách truy cập static member; static context; static initialization và shared state; member, local, anonymous inner classes; nested enum/interface/record; quyền truy cập, inheritance và method hiding; compilation/source release; cùng những lỗi phổ biến. Các ví dụ chạy độc lập có filename, `javac`, `java` và kết quả đối chiếu.

## 2. Phân biệt nested class và inner class

### 2.1. Nested class là gì?

Một class được khai báo bên trong phạm vi class hoặc interface khác là **nested class**. Theo cách học Java thường gặp, có hai nhánh quan trọng:

1. **Static nested class** — member class được khai báo `static`; không có enclosing instance của outer class do tư cách static nested type.
2. **Inner class** — nested class không được khai báo `static` và không implicitly static; bao gồm non-static member inner class, local class và anonymous class trong những trường hợp được ngôn ngữ phân loại tương ứng.

Ví dụ:

~~~java
class Library {
    static class Shelf {
        // Static nested member class.
    }

    class Book {
        // Non-static member inner class.
    }
}
~~~

`Shelf` và `Book` đều là nested types, nhưng chỉ `Book` là **non-static member inner class**.

### 2.2. Cách khởi tạo khác nhau

Giả sử:

~~~java
Library library = new Library();
Library.Shelf shelf = new Library.Shelf();
Library.Book book = library.new Book();
~~~

Đây là fragment được đặt trong method có quyền truy cập constructor. `Shelf` có thể được tạo bằng `new Library.Shelf()` vì nó là static nested class. `Book` cần `library.new Book()` vì là non-static member inner class và cần **enclosing Library instance**.

Lưu ý: nếu đã ở trong một instance method phù hợp của Library, có thể viết `new Book()`, bởi enclosing Library instance đã có trong ngữ cảnh đó.

### 2.3. Có static member không quyết định loại class

Sau Java 16:

~~~java
class Library {
    class Book {
        static int totalCreated;
    }
}
~~~

`Book` **vẫn là inner class**. Sự hiện diện của `static int totalCreated` không làm constructor Book mất yêu cầu enclosing Library instance.

Phân loại inner hay static nested phụ thuộc vào **khai báo lớp** và rules ngôn ngữ, không phụ thuộc việc lớp đó có bao nhiêu static methods hoặc fields.

## 3. Quy tắc trước Java 16: ngoại lệ constant variable

Trước Java 16, inner class có thể khai báo **static final constant variables**, nhưng không được phép khai báo các static members tùy ý hoặc static initializer.

Một **constant variable** theo định nghĩa Java là một `final` variable có kiểu primitive hoặc `String`, được khởi tạo bằng **constant expression** (`4.12.4` và `15.29` trong ngữ cảnh Java hiện hành). Những điều kiện này phải được thỏa **đồng thời**.

Các declarations từng hợp lệ trong non-static inner class trước Java 16:

~~~java
class OldRule {
    class Inner {
        static final int MAX = 16;
        static final long TIMEOUT = 2L * 1000;
        static final String PREFIX = "java" + "-core";
        static final boolean ENABLED = true;
    }
}
~~~

Đây là class minh họa và các expressions là compile-time constants.

### 3.1. Có `final` chưa chắc là constant variable

Không phải mọi `static final` đều là constant variable:

~~~java
class ModernRules {
    class Inner {
        static final Integer BOXED = 100;
        static final String GENERATED = makeLabel();
        static final int RUNTIME = Integer.parseInt("7");

        static String makeLabel() {
            return "dynamic";
        }
    }
}
~~~

Các fields `BOXED`, `GENERATED` và `RUNTIME` đều **không là constant variables** theo nghĩa compile-time constant:

- `Integer` là reference type, không phải primitive hoặc String.
- `makeLabel()` là method call, không phải constant expression.
- `Integer.parseInt("7")` là method call, không phải constant expression.

Đoạn khai báo này hợp lệ với Java 17, nhưng không tương thích với restriction trước Java 16 trong inner class.

### 3.2. `static final String` cũng có thể không là constant

~~~java
static final String A = "hello";             // Constant variable.
static final String B = "he" + "llo";       // Constant variable.
static final String C = new String("hello"); // Không là constant variable.
~~~

Tất cả có cùng Java type String và đều final, nhưng `new String(...)` không phải constant expression. Trước Java 16, chỉ A và B phù hợp ngoại lệ.

### 3.3. Vì sao quy tắc cũ dễ gây hiểu nhầm?

Nhiều giáo trình Java cũ rút gọn thành câu:

> “Inner class không thể chứa static member, ngoại trừ static final constants.”

Câu đó **đúng về lịch sử đối với ngôn ngữ trước Java 16**, nhưng **không đúng nếu dùng như quy tắc tuyệt đối cho Java 17+**.

Khi đọc code hoặc giải đáp lỗi từ các bài cũ, hãy xem **source level mà dự án dùng**, không chỉ JDK cài trên máy.

## 4. Java 16 thay đổi gì, và không thay đổi gì?

| Câu hỏi | Trước Java 16 | Java 16 trở đi |
| --- | --- | --- |
| `static final int A = 1;` trong inner class | Cho phép | Cho phép |
| `static int counter;` trong inner class | Không cho phép | Cho phép |
| `static final String NAME = compute();` | Không cho phép nếu không là constant variable | Cho phép |
| `static void helper()` | Không cho phép | Cho phép |
| `static { ... }` trong inner class | Không cho phép | Cho phép |
| `static class Helper` bên trong inner class | Không cho phép | Cho phép |
| Member enum/record/interface implicitly static bên trong inner | Bị hạn chế theo rules về static declarations và hỗ trợ phiên bản | Cho phép theo rules của loại tương ứng |
| Tạo instance non-static inner class bằng `new Outer.Inner()` từ bên ngoài mà không có outer instance | Không | Vẫn không |
| Static method trong inner class truy cập trực tiếp `Outer.this` | Không | Vẫn không |
| Static member là dữ liệu riêng cho mỗi Outer object | Không | Vẫn không |

Điểm thay đổi là **quyền khai báo static members**, không phải bản chất `this`, outer instance, class initialization hoặc access control.

### 4.1. Java 16 là mốc ngôn ngữ

Java 16 là mốc của thay đổi restrictions. Java 17 là LTS và áp dụng rules mới. Trong codebase phải tương thích Java 8, 11 hoặc 15, không thể chỉ vì developer đang chạy JDK 17 mà tự tiện dùng cú pháp/static declarations này.

### 4.2. “Static” có hai vị trí khác nhau

So sánh:

~~~java
class Outer {
    static class Nested {   // Chính nested class là static.
    }

    class Inner {           // Chính class này KHÔNG static.
        static int value;   // Nhưng member field này là static.
    }
}
~~~

`Outer.Nested` không cần enclosing Outer instance để được tạo. `Outer.Inner` vẫn cần, dù field `value` là static.

## 5. Chương trình hoàn chỉnh 1: static field, method, initializer và nested helper

Tạo tệp **`InnerStaticMembersDemo.java`**:

~~~java
public class InnerStaticMembersDemo {
    static final class Campus {
        private final String city;

        Campus(String city) {
            this.city = city;
        }

        class Student {
            static int created;

            static {
                created = 100;
            }

            static String category() {
                return "inner-member";
            }

            static class Helper {
                static String format(int number) {
                    return "#" + number;
                }
            }

            private final int number;

            Student(int number) {
                this.number = number;
                created++;
            }

            String badge() {
                return city + ":" + number;
            }
        }
    }

    public static void main(String[] args) {
        System.out.println("Initial = " + Campus.Student.created);

        Campus hanoi = new Campus("Hanoi");
        Campus hue = new Campus("Hue");

        Campus.Student one = hanoi.new Student(1);
        Campus.Student two = hue.new Student(2);

        System.out.println("First = " + one.badge());
        System.out.println("Second = " + two.badge());
        System.out.println("Created = " + Campus.Student.created);
        System.out.println("Category = " + Campus.Student.category());
        System.out.println("Helper = "
                + Campus.Student.Helper.format(12));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 InnerStaticMembersDemo.java
java InnerStaticMembersDemo
~~~

**Stdout:**

~~~text
Initial = 100
First = Hanoi:1
Second = Hue:2
Created = 102
Category = inner-member
Helper = #12
~~~

### 5.1. Giải thích initialization

`Campus.Student.created` là static field thuộc **Student class**, không phải field riêng của Student instances. Lần truy cập active đầu tiên yêu cầu khởi tạo class khi chưa được khởi tạo, nên static initializer gán `created = 100`.

Sau đó tạo hai Student objects, mỗi constructor tăng field static. Giá trị cuối là 102.

### 5.2. Vì sao badge đọc được `city`?

`badge()` là **instance method** của inner Student. Mỗi Student instance được tạo với enclosing Campus object: `hanoi.new Student(1)` hoặc `hue.new Student(2)`. Trong instance context, method có thể dùng outer state `city` theo Java access rules.

Vì vậy object one in `Hanoi` và object two in `Hue` có badges khác nhau.

### 5.3. Vì sao static category không đọc city trực tiếp?

`category()` là **static method**, không có Student `this` hoặc một enclosing Campus instance được chọn tự động. Nó trả string constant nên hợp lệ. Nếu viết `return city;` ở đây, compiler sẽ báo lỗi truy cập instance member từ static context.

### 5.4. Nested Helper thuộc loại nào?

`Helper` được khai báo `static class` **bên trong** một inner class. Với Java 17, khai báo này hợp lệ và Helper là static nested member type của Student. Ta gọi `Campus.Student.Helper.format(12)` mà không cần tạo Student hay Campus instance.

**Điều này không biến Student thành static nested class**.

## 6. Static state dùng chung giữa các enclosing objects

Một hiểu nhầm là static field trong inner class thuộc mỗi outer instance:

~~~java
Outer first = new Outer();
Outer second = new Outer();
~~~

Nếu cả hai cùng tạo Inner objects, `Outer.Inner.counter` vẫn là **một class variable của Inner** trong một class initialization context, không phải hai counters độc lập cho first và second.

Nói chính xác hơn, static data gắn với **mỗi runtime class** do class loader định nghĩa. Trong những class loaders khác nhau, có thể có các runtime classes khác nhau mang tên tương tự; không nên gọi một static field là “một biến duy nhất trên toàn bộ mọi JVM/class loader”.

### 6.1. Nếu cần counter riêng từng Outer, dùng instance field ở Outer

~~~java
class Shop {
    private int customerCount;

    class Customer {
        Customer() {
            customerCount++;
        }
    }
}
~~~

Đây là class minh họa. `customerCount` là field riêng của **mỗi Shop instance**; Customer constructor thuộc inner instance context nên tăng counter của enclosing Shop.

Ngược lại, đặt `static int customerCount` trong Customer sẽ biến nó thành class-wide state cho Customer, không còn counter riêng cho mỗi Shop.

### 6.2. Static mutable state cần chú ý concurrency

Một `static int count` được tăng bằng `count++` **không atomic**. Nếu nhiều threads cùng tạo Inner objects, code như `count++` có thể mất updates. Ví dụ 1 chỉ chạy tuần tự nên không gặp vấn đề đó.

Trong ứng dụng concurrent, tùy yêu cầu dùng `AtomicInteger`, lock, LongAdder hoặc phối hợp synchronization phù hợp:

~~~java
static final java.util.concurrent.atomic.AtomicInteger CREATED =
        new java.util.concurrent.atomic.AtomicInteger();

static void markCreated() {
    CREATED.incrementAndGet();
}
~~~

Đây là fragment, không phải toàn bộ class. Static không đồng nghĩa thread-safe và không đồng nghĩa immutable.

## 7. Static context không có `this` của Inner hay enclosing Outer

Một instance của non-static member inner class thường có một enclosing instance; trong instance method có thể tham chiếu:

- `this`: instance của Inner đang chạy method.
- `Outer.this`: instance của Outer bao quanh Inner, trong ngữ cảnh cho phép.
- Các instance fields/methods của Outer nếu khả dụng theo scope/access rules.

Một **static method/initializer** của Inner không có `this` instance. Nó cũng không thể tự chọn một `Outer.this` từ nhiều outer objects có thể tồn tại.

### 7.1. Những đoạn không biên dịch

Giả sử:

~~~java
class Outer {
    private int value = 7;

    class Inner {
        private int own = 4;

        static int invalidA() {
            return own;              // SAI: own là instance field.
        }

        static int invalidB() {
            return value;            // SAI: value thuộc Outer instance.
        }

        static Outer invalidC() {
            return Outer.this;       // SAI: qualified this trong static context.
        }
    }
}
~~~

Đây là **mã cố ý sai để phân tích compile errors; không chạy**. Static methods không nhận một Inner hay Outer object ngầm định; compiler không thể biết lấy instance value nào.

### 7.2. Cách hợp lệ: truyền instance tường minh

~~~java
class Outer {
    private final int value;

    Outer(int value) {
        this.value = value;
    }

    class Inner {
        private final int own;

        Inner(int own) {
            this.own = own;
        }

        static int combine(Outer outer, Inner inner) {
            return outer.value + inner.own;
        }
    }
}
~~~

Đây là class fragment. `combine` vẫn static, nhưng các references `outer` và `inner` là **parameters tường minh**. Nó truy cập private fields từ nested lexical context theo rules Java.

Trong code production, có thể cần validate rằng `inner` thật sự gắn với `outer` nếu business contract yêu cầu. Việc truyền hai references bất kỳ không tự chứng minh chúng thuộc cùng object graph.

### 7.3. Chương trình hoàn chỉnh 2: instance context và static context

Tạo tệp **`StaticContextDemo.java`**:

~~~java
import java.util.Objects;

public class StaticContextDemo {
    static final class Outer {
        private final String region;

        Outer(String region) {
            this.region = Objects.requireNonNull(region);
        }

        class Inner {
            private final int index;

            Inner(int index) {
                this.index = index;
            }

            String instanceSummary() {
                return region + ":" + index;
            }

            static String summary(Outer outer, int index) {
                return outer.region + ":" + index;
            }

            static String readFrom(Inner inner) {
                return inner.instanceSummary();
            }
        }
    }

    public static void main(String[] args) {
        Outer east = new Outer("East");
        Outer west = new Outer("West");
        Outer.Inner item = east.new Inner(7);

        System.out.println("Instance = " + item.instanceSummary());
        System.out.println("Static explicit = "
                + Outer.Inner.summary(west, 11));
        System.out.println("Static with inner = "
                + Outer.Inner.readFrom(item));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StaticContextDemo.java
java StaticContextDemo
~~~

**Stdout:**

~~~text
Instance = East:7
Static explicit = West:11
Static with inner = East:7
~~~

Instance method dùng enclosing East. Static method `summary(west, 11)` dùng outer object được truyền tường minh là West. Method `readFrom(item)` đọc instance qua parameter item; không có implicit `this` trong static method.

## 8. Lời gọi static member qua type, không qua instance

Cách khuyến nghị:

~~~java
Outer.Inner.reset();
int count = Outer.Inner.counter;
~~~

Đây là fragments giả định declarations tồn tại. Tên `Outer.Inner` ở đây là **type name**. Việc truy cập static member qua type **không yêu cầu khởi tạo một Outer hay Inner object** (mặc dù class initialization semantics vẫn có thể áp dụng).

Trong Java, một số static members có thể được gọi qua instance reference, nhưng cách đó làm người đọc hiểu nhầm chúng thuộc riêng instance và IDE/compiler có thể cảnh báo. Nên viết:

~~~java
Outer.Inner.utility();
~~~

thay vì:

~~~java
inner.utility(); // Không nên nếu utility là static.
~~~

Không nên suy luận `inner.utility()` là dynamic dispatch tới subtype implementation. Static method resolution dựa trên compile-time declarations.

### 8.1. Type name không đồng nghĩa được tạo instance dễ dàng

Hai câu sau nói về hai việc khác nhau:

~~~java
Outer.Inner.utility();       // Dùng static method qua type.
Outer.Inner inner = outer.new Inner(); // Cần outer instance để tạo Inner.
~~~

Trường hợp static member có thể được tham chiếu không qua enclosing instance **không làm thay đổi constructor invocation rules** của non-static inner class.

### 8.2. Nếu static method cần một inner object

Có thể truyền chính inner reference:

~~~java
static String describe(Inner obj) {
    return obj.toString();
}
~~~

hoặc tạo outer instance và sau đó inner instance tường minh. Static method không thể dùng `new Inner()` như thể có sẵn enclosing Outer instance nếu đang ở static context không có outer object phù hợp.

## 9. Initialization: static block khác instance initializer/constructor

**Static initialization** xảy ra khi runtime class được khởi tạo theo Java class initialization rules; không chạy lại với mọi instance.

**Instance initialization** chạy trong quá trình tạo từng object sau khi class initialization áp dụng phù hợp. Nếu một inner class có static block và constructor, hai phạm vi này độc lập.

### 9.1. Chương trình hoàn chỉnh 3: static initializer chạy một lần

Tạo tệp **`InnerInitializationDemo.java`**:

~~~java
public class InnerInitializationDemo {
    static final class Owner {
        class Inner {
            static int initialValue = initialize();

            static int initialize() {
                System.out.println("Inner initialized");
                return 40;
            }

            Inner() {
                System.out.println("Inner instance");
            }
        }
    }

    public static void main(String[] args) {
        System.out.println("Start");
        System.out.println("Read = " + Owner.Inner.initialValue);

        Owner owner = new Owner();
        owner.new Inner();
        owner.new Inner();

        System.out.println("Again = " + Owner.Inner.initialValue);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InnerInitializationDemo.java
java InnerInitializationDemo
~~~

**Stdout:**

~~~text
Start
Inner initialized
Read = 40
Inner instance
Inner instance
Again = 40
~~~

**Vì sao?** Lần active use `Owner.Inner.initialValue` khởi tạo class Inner và thực thi `initialize()` một lần. Hai lần tạo Inner objects chỉ chạy constructor `Inner()` tương ứng.

### 9.2. Static block được phép làm gì?

Nó có thể gán static fields và gọi static methods, nhưng không có implicit Inner `this`/Outer `this`. Nếu cần dữ liệu từ enclosing instance, phải nhận dữ liệu qua thiết kế phù hợp **sau khi** object tồn tại, không đọc trực tiếp một Outer field từ static initialization code.

### 9.3. Compile-time constants có hành vi initialization đáng chú ý

Đọc một `static final int MAX = 16` là constant variable có thể được compile-time inlined trong code gọi và **không nhất thiết kích hoạt class initialization** như truy cập một static field nonconstant. Vì vậy đừng dùng constant field read để kiểm chứng thời điểm chạy static initializer. Demo dùng field `initialValue = initialize()` nên đó không phải constant variable.

### 9.4. Class loader và multiple runtimes

“Khởi tạo một lần” nên hiểu **mỗi lần initialization của một runtime class**. Nếu cùng class name được load bởi những defining class loaders khác nhau, mỗi class có static state riêng. Trong ứng dụng bình thường chỉ có một definition tương ứng, nhưng câu “một static field duy nhất trong toàn bộ JVM cho mọi class loader” là quá mạnh.

### 9.5. Static initialization có thể thất bại

Nếu static initializer hoặc static field initializer ném unchecked exception/error trong quá trình khởi tạo, class initialization thất bại theo JVM rules và những lần sử dụng sau có thể gặp errors liên quan đến class initialization. Đừng dùng static blocks để làm công việc side-effectful dễ thất bại mà không có error policy rõ; không cần “static object được tạo sẵn” để khởi tạo Inner.

## 10. Member inner class, local class và anonymous class

Từ “inner class” không chỉ là member class `Outer.Inner`. Một local class được khai báo trong method/block và anonymous class từ class instance creation expression cũng thuộc các dạng inner class theo ngôn ngữ trong hoàn cảnh thông thường.

Các restrictions về static declarations được nới từ Java 16 **không chỉ liên quan tên của một non-static member class**. Tuy nhiên, mỗi loại có những cú pháp và phạm vi tên riêng:

- **Member inner class:** có member type name, ví dụ `Outer.Inner`.
- **Local class:** chỉ có tên class trong local lexical scope; bản thân local declaration không viết `static class Local`.
- **Anonymous class:** không có source-level simple class name để gọi static member từ bên ngoài bằng `SomeName.member`; thông thường static members được dùng trong body hoặc qua reflection khi thật sự cần.

### 10.1. Local class có thể khai báo static members từ Java 16

Trong method:

~~~java
void calculate() {
    int offset = 5;

    class Local {
        static int factor = 2;

        static int twice(int input) {
            return input * factor;
        }

        int evaluated() {
            return twice(offset);
        }
    }

    System.out.println(new Local().evaluated());
}
~~~

Đây là method fragment. Static method `twice` không sử dụng captured local variable `offset` trực tiếp; instance method `evaluated` được phép tham chiếu effectively final `offset` của enclosing method theo rules về local-variable capture.

### 10.2. Anonymous class cũng có instance body và static declarations phù hợp

Java anonymous class không có tên khai báo để bạn viết lời gọi qualified static method từ caller theo type name. Nhưng trong Java 17, bạn có thể định nghĩa static method/field trong anonymous class body theo ngôn ngữ hiện hành.

### 10.3. Chương trình hoàn chỉnh 4: local và anonymous inner class

Tạo tệp **`LocalAnonymousStaticDemo.java`**:

~~~java
public class LocalAnonymousStaticDemo {
    public static void main(String[] args) {
        int offset = 5;

        class Local {
            static int factor = 2;

            static int times(int x) {
                return x * factor;
            }

            int evaluate() {
                return times(offset);
            }
        }

        System.out.println("Local = " + new Local().evaluate());
        System.out.println("Local factor = " + Local.factor);

        Runnable runner = new Runnable() {
            static int calls;

            static String label() {
                return "anonymous";
            }

            @Override
            public void run() {
                calls++;
                System.out.println(label() + " calls = " + calls);
            }
        };

        runner.run();
        runner.run();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LocalAnonymousStaticDemo.java
java LocalAnonymousStaticDemo
~~~

**Stdout:**

~~~text
Local = 10
Local factor = 2
anonymous calls = 1
anonymous calls = 2
~~~

### 10.4. Giải thích chính xác

- Local có static field `factor` và static method `times`; điều này hợp lệ với Java 17.
- Instance method `evaluate` dùng effectively final local `offset` bằng 5, nên `times(5) = 10`.
- Anonymous class implementation của Runnable có static field `calls`. Trong ví dụ chỉ có **một anonymous class instance**, nên hai lời gọi run tăng 1, rồi 2.
- `calls` là class state của **anonymous class đã được tạo ra**, không phải field của `Runnable` interface.
- Không thể gọi `Runnable.calls`, vì type `Runnable` không khai báo field đó; tên anonymous subclass không có source-level simple name để gọi từ ngoài.

### 10.5. Không được khai báo local class với static modifier

Cú pháp:

~~~java
void method() {
    static class Local { }  // SAI: local class declaration không dùng static.
}
~~~

**Cố ý không biên dịch.** Sự khác biệt: **static members bên trong Local** có thể hợp lệ; nhưng **local class declaration bản thân** không thể được đánh dấu `static` để biến nó thành static member type. Đây là lỗi dễ xảy ra khi nghe “inner class nay được phép static” mà không phân biệt declaration levels.

## 11. Nested enum, interface, record và static nested type

Một số nested member types là **implicitly static** theo rules của Java. Trong Java 17, một inner class có thể chứa chúng vì restrictions cũ đã được nới.

Ví dụ các declarations hợp lệ:

~~~java
class Container {
    class Inner {
        enum State {
            READY, RUNNING
        }

        interface Formatter {
            String format(String input);
        }

        record Coordinate(int x, int y) {
        }

        static class Helper {
            static int doubleOf(int value) {
                return value * 2;
            }
        }
    }
}
~~~

Đây là declaration fragment. State, Formatter, Coordinate và Helper đều là **member types** bên trong Inner; các loại trên không tự đòi một `Container.Inner` instance chỉ để truy cập hoặc tạo instance của chính chúng theo semantics static type.

### 11.1. Records và enums có tính implicitly static

Một member record hoặc enum là implicitly static. Điều này quan trọng vì chúng không mang implicit enclosing Inner instance giống non-static inner objects. Từ Java 16, có thể đặt member records/enums bên trong một inner class theo rules của ngôn ngữ hiện hành.

Điều đó **khác** việc record tự mang mọi form của deep immutability; record component có thể chứa mutable List, Date hoặc arrays nếu thiết kế cho phép. Đó là một vấn đề object state riêng.

### 11.2. Member interface cũng implicitly static

Một member interface được khai báo trong class có semantics implicitly static. Không cần `new Outer().new Inner()` để định nghĩa hoặc tham chiếu type đó. Việc implement interface có thể dùng lambda nếu interface là functional interface phù hợp.

### 11.3. Chương trình hoàn chỉnh 5: các nested types trong inner class

Tạo tệp **`InnerStaticTypesDemo.java`**:

~~~java
public class InnerStaticTypesDemo {
    static final class Container {
        class Inner {
            enum State {
                READY, RUNNING
            }

            interface Formatter {
                String format(String input);
            }

            record Coordinate(int x, int y) {
            }

            static class Helper {
                static int doubleOf(int value) {
                    return value * 2;
                }
            }
        }
    }

    public static void main(String[] args) {
        Container.Inner.Coordinate point =
                new Container.Inner.Coordinate(2, 3);

        Container.Inner.State state =
                Container.Inner.State.READY;

        Container.Inner.Formatter formatter =
                input -> "[" + input + "]";

        System.out.println("Point = " + point);
        System.out.println("State = " + state);
        System.out.println("Formatted = "
                + formatter.format("Java"));
        System.out.println("Double = "
                + Container.Inner.Helper.doubleOf(4));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 InnerStaticTypesDemo.java
java InnerStaticTypesDemo
~~~

**Stdout:**

~~~text
Point = Coordinate[x=2, y=3]
State = READY
Formatted = [Java]
Double = 8
~~~

### 11.4. Không tạo Container.Inner object trong demo

Tất cả operations trong main tham chiếu **static member types** của Container.Inner. Điều đó không đòi tạo một instance của Inner. Tuy nhiên, để tạo **chính một instance Inner**, vẫn cần một Container instance:

~~~java
Container outer = new Container();
Container.Inner inner = outer.new Inner();
~~~

Đây là fragment được đặt trong scope phù hợp với các type declarations ở demo. Nó là phép khởi tạo **Inner** khác hẳn phép tạo `Container.Inner.Coordinate`.

## 12. Static method hiding không phải overriding

Từ Java 16, inner classes có thể khai báo static methods, vì vậy rules về hiding của static methods cũng trở nên trực tiếp liên quan.

**Instance method overriding** có dynamic dispatch dựa trên runtime type (khi hội đủ các điều kiện). **Static method hiding** được resolved theo compile-time declared type, không theo dynamic dispatch.

### 12.1. Chương trình hoàn chỉnh 6: static hiding và instance overriding

Tạo tệp **`InnerStaticHidingDemo.java`**:

~~~java
public class InnerStaticHidingDemo {
    static final class Outer {
        class Base {
            static String kind() {
                return "base";
            }

            String action() {
                return "base-action";
            }
        }

        class Derived extends Base {
            static String kind() {
                return "derived";
            }

            @Override
            String action() {
                return "derived-action";
            }
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Base polymorphic = outer.new Derived();

        System.out.println("Base static = " + Outer.Base.kind());
        System.out.println("Derived static = " + Outer.Derived.kind());
        System.out.println("Instance dispatch = "
                + polymorphic.action());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 InnerStaticHidingDemo.java
java InnerStaticHidingDemo
~~~

**Stdout:**

~~~text
Base static = base
Derived static = derived
Instance dispatch = derived-action
~~~

### 12.2. Vì sao static methods không được annotate `@Override`?

`Derived.kind()` khai báo một static method có cùng signature với static method được kế thừa theo những rules áp dụng, nên nó **hides**, không overrides. Nếu đặt `@Override` lên method static, compiler báo lỗi vì không có instance overriding tương ứng.

Ngược lại, `Derived.action()` là instance method thực sự override Base.action, nên lời gọi qua biến có static type `Outer.Base` vẫn dispatch đến Derived.action ở runtime.

### 12.3. Không thể override static method bằng instance method

Một subclass không thể đơn giản khai báo instance method có cùng signature để override một static method của superclass; đó là sự xung đột giữa static và instance method declarations. Tương tự, static method không override instance method cùng signature.

## 13. Access modifiers với static members trong inner class

Cho dù static members đã được cho phép từ Java 16, **quyền truy cập** vẫn phải tuân theo Java access rules:

- `private static`: chỉ truy cập từ scopes được cho phép theo nested-class private access rules.
- Package-private: trong package phù hợp.
- `protected static`: theo protected access rules của Java, nhất là khi subclass nằm ở package khác.
- `public static`: theo khả năng truy cập đến declaring class/type và modules.

Nếu `Inner` là private member class, đặt `public static void helper()` trong đó **không tự làm helper có thể gọi từ code ngoài khi declaring type không accessible**.

### 13.1. Static member không vượt qua access của containing type

~~~java
class Outer {
    private class Inner {
        public static void helper() {
        }
    }
}
~~~

Đây là class fragment. Helper public trong Inner, nhưng code bên ngoài không thể tham chiếu `Outer.Inner` nếu Inner private không accessible từ nơi đó.

### 13.2. Outer và nested classes có thể truy cập private members theo rules

Java hỗ trợ private access giữa enclosing và nested types trong lexical nesting context, theo rules JLS. Static method trong inner class không vì là static mà mất mọi đặc quyền lexical access; tuy nhiên vẫn phải có **object reference tường minh** nếu muốn truy cập **instance state** từ static context.

Access permission và sự tồn tại của `this` là **hai vấn đề khác nhau**.

### 13.3. Package và module

Với named modules, kể cả public class và public static member, việc truy cập từ module khác còn phụ thuộc package có được export/readable phù hợp không. Java 16 thay đổi restriction static-in-inner, **không xóa encapsulation do package/module access**.

## 14. Static initializers có những hạn chế chung của static context

Một static initializer trong inner class là hợp lệ từ Java 16:

~~~java
class Outer {
    class Inner {
        static int value;

        static {
            value = 42;
        }
    }
}
~~~

Nhưng vẫn phải tuân theo rules của static initialization:

- Không dùng implicit Inner `this`.
- Không dùng `Outer.this` trực tiếp trong static context.
- Không đọc instance field của Inner/Outer mà không có instance.
- Không gọi instance method không qua receiver phù hợp.
- Không tự bảo đảm thread safety của static mutable fields.
- Không phụ thuộc một enclosing outer instance cụ thể vì nhiều outer objects có thể tạo Inner objects của cùng runtime class.

### 14.1. Thứ tự static fields và initializer blocks

Static field initializers và static initializer blocks chạy trong quá trình class initialization theo **textual order** áp dụng (cùng các default-value/preparation rules). Cẩn thận forward references và circular initialization dependencies; Java không cho mọi biến chưa được khai báo theo mọi cách sử dụng trong initializer.

Chọn một initialization flow đơn giản, tránh gọi phức tạp sang nhiều classes phụ thuộc nhau nếu không có nhu cầu.

### 14.2. Exception trong static initializer

Không thể viết một checked exception tùy ý chạy thoát ra từ static initializer như từ một method có `throws`. Cần xử lý exceptions theo compile-time rules. Unchecked failure khi class initialization có thể dẫn tới `ExceptionInInitializerError` hoặc các lỗi initialization tiếp theo theo circumstances.

Đừng dựa vào chính xác full error message/stacktrace như một stdout chung cho mọi JDK; compiler/runtime diagnostics có thể thay đổi.

## 15. Khác biệt giữa static method và enclosing-instance capture

Một inner instance có thể tham chiếu dữ liệu của enclosing instance theo ngữ cảnh. Compiler/JVM có thể biểu diễn mối liên kết đó bằng implementation mechanisms như synthetic fields/constructor parameters, nhưng **không nên dựa vào tên field synthetic** như `this$0` trong business code hay tests.

Static fields/methods của Inner không gắn với một enclosing Outer object cụ thể. Một static method cần dữ liệu outer phải:

1. Nhận outer instance qua parameter.
2. Nhận một immutable snapshot/ID của dữ liệu cần xử lý.
3. Gọi một static service có contract riêng.
4. Hoặc chuyển logic sang một **instance method** nếu bản chất method thật sự gắn với Inner/Outer instance.

### 15.1. Không nhầm enclosing access với static outer field

Một inner static method **có thể truy cập static field/method** của Outer nếu access rules cho phép:

~~~java
class Outer {
    private static int version = 17;

    class Inner {
        static int currentVersion() {
            return version;
        }
    }
}
~~~

`version` là class variable của Outer, không đòi Outer instance. Code hợp lệ từ Java 16 đối với declaration Inner.currentVersion; việc đọc Outer.version từ static context là bình thường.

### 15.2. Static methods được phép nhận Inner object để thao tác trên instance

~~~java
static int lengthOfName(Inner value) {
    return value.name.length();
}
~~~

Đây là fragment giả định class Inner có `name` phù hợp. Điểm mấu chốt là receiver `value` **được chỉ ra tường minh**, thay vì implicit `this`.

## 16. Toolchain: `--release`, source level và lỗi khi chạy dự án cũ

Đừng suy ra “máy đang có java 17 nên code chắc chắn dùng Java 17 language rules”. Build có thể ép:

- Maven Compiler Plugin với `--release 11`.
- Gradle Java toolchain và options.release mức cũ.
- IDE project language level Java 8/11/15.
- Một `javac --release 15` invocation trên JDK hỗ trợ target đó.

Với source level trước Java 16, static nonconstant declarations trong inner class **không thuộc ngôn ngữ được hỗ trợ**, dù JDK đang cài là bản mới.

### 16.1. Cách biên dịch với release hiện hành

Ví dụ file `InnerStaticMembersDemo.java` có thể biên dịch bằng JDK 17:

~~~bash
javac --release 17 -encoding UTF-8 InnerStaticMembersDemo.java
java InnerStaticMembersDemo
~~~

Bản `javac -encoding UTF-8 ...` không chỉ rõ release sẽ dùng source level mặc định của compiler đang chạy; với JDK 17, đó là Java 17 semantics.

### 16.2. Minh họa mã trước/sau

Với source level 15 hoặc sớm hơn, class sau **không hợp lệ**:

~~~java
class Host {
    class Inner {
        static int counter;
        static void reset() {
            counter = 0;
        }
    }
}
~~~

Với Java 17 source level, declaration này **hợp lệ**. Compiler diagnostics chính xác có thể khác giữa phiên bản; đừng viết một stdout kỳ vọng cố định cho thử nghiệm **cố ý không biên dịch**.

### 16.3. Compatibility hai chiều

- Source dùng static declarations được nới lỏng muốn compile cho Java 11/15 cần **thiết kế lại**, không chỉ thay bytecode target.
- Compiling và running trên các JVM versions là hai vấn đề liên quan nhưng khác: một class file build cho release mới có thể không chạy trên JVM cũ.
- Java 16+ syntax không được “dịch ngược” một cách kỳ diệu bằng `-target 11` nếu source language level vẫn không hợp lệ theo build configuration.

Nếu dự án bắt buộc tương thích Java 11, có thể chuyển helper thành **static nested class ở trực tiếp Outer level** hoặc một top-level utility class, hoặc giữ các static final constant variables theo restriction cũ.

## 17. Refactoring code cũ

Trước Java 16, khi inner class cần nonconstant static state hoặc static helper, người ta thường di chuyển chúng ra:

~~~java
class Outer {
    private static final class Helper {
        static int counter;
        static void reset() {
            counter = 0;
        }
    }

    class Inner {
        void action() {
            Helper.counter++;
        }
    }
}
~~~

Đây là fragment hợp lệ cho source cũ phù hợp: `Helper` là **static nested class của Outer**, không phải static member của Inner. Java 16+ cho phép chuyển `counter`/`reset()` trực tiếp vào Inner, nhưng việc refactor có đáng làm không còn tùy:

- API name/type compatibility: từ `Outer.Helper.counter` sang `Outer.Inner.counter` là thay đổi names và possibly accessibility.
- Semantic ownership: counter thực sự của Inner instances toàn class hay của Outer instance?
- Cohesion: helper đặt trong Inner có làm thiết kế rõ hơn không?
- Binary/source compatibility với consumers và build release?
- Unit tests/reflection/serialization hooks?
- Concurrency của shared mutable state?

**Không nên refactor chỉ vì syntax mới cho phép.** Static state trong inner class hợp lệ nhưng có thể làm class vừa giữ enclosing-instance behavior vừa giữ global state, khiến API khó đọc nếu trách nhiệm không được phân tách.

## 18. Sự khác nhau giữa static member và constant variable

| Declaration | Constant variable? | Static member? | Inner class Java 15 | Inner class Java 17 |
| --- | --- | --- | --- | --- |
| `static final int A = 1;` | Có | Có | Hợp lệ | Hợp lệ |
| `static final String B = "x"+"y";` | Có | Có | Hợp lệ | Hợp lệ |
| `static final double PI = 3.14;` | Có | Có | Hợp lệ | Hợp lệ |
| `static final Integer C = 1;` | Không | Có | Không hợp lệ | Hợp lệ |
| `static final String D = helper();` | Không | Có | Không hợp lệ | Hợp lệ |
| `static int count = 1;` | Không | Có | Không hợp lệ | Hợp lệ |
| `static final int R = Integer.parseInt("1");` | Không | Có | Không hợp lệ | Hợp lệ |
| `static void reset() {}` | Không áp dụng | Có | Không hợp lệ | Hợp lệ |
| `static { count++; }` | Không áp dụng | Static initializer | Không hợp lệ | Hợp lệ |
| `static class Helper {}` | Không áp dụng | Static member type | Không hợp lệ | Hợp lệ |

**Không phải static final field nào cũng là constant variable.** Để là constant variable, cần final, kiểu primitive/String và initialized by constant expression. Đây là ba ý quan trọng khi giải thích code cũ.

## 19. Trắc nghiệm lỗi biên dịch: những bẫy điển hình

### 19.1. Bẫy 1 — tưởng static member cần Outer instance

~~~java
class Outer {
    class Inner {
        static int value = 7;
    }
}
~~~

Cách dùng đúng từ một accessible scope:

~~~java
System.out.println(Outer.Inner.value);
~~~

Không cần new Outer().new Inner() chỉ để đọc static field. Nhưng nếu muốn tạo Inner object, vẫn phải có outer instance.

### 19.2. Bẫy 2 — tưởng static method dùng Outer.this

~~~java
class Outer {
    private int count = 3;

    class Inner {
        static int read() {
            return Outer.this.count; // Cố ý lỗi.
        }
    }
}
~~~

**Không biên dịch** vì qualified this không dùng được ở static context. Dùng instance method, hoặc truyền Outer reference tường minh.

### 19.3. Bẫy 3 — static final initialized bằng method

~~~java
class Outer {
    class Inner {
        static final int COUNT = Integer.parseInt("3");
    }
}
~~~

Hợp lệ Java 17, không là compile-time constant. Đừng suy từ `static final` mà kết luận được dùng theo ngoại lệ của Java 15.

### 19.4. Bẫy 4 — local class được phép thành `static class`

~~~java
void m() {
    static class Local {} // Cố ý lỗi.
}
~~~

Java 16 cho phép **static members của Local**, không cho phép modifier static ngay trên local class declaration.

### 19.5. Bẫy 5 — anonymous class có tên để gọi static method

~~~java
Runnable action = new Runnable() {
    static void helper() {}
    @Override
    public void run() {
        helper();
    }
};
~~~

Đây là fragment hợp lệ trong Java 17. Nhưng `Runnable.helper()` không hợp lệ vì Runnable interface không khai báo method này. Anonymous class không có simple name của chính nó trong source code để gọi helper từ bên ngoài bằng `AnonymousType.helper()`.

### 19.6. Bẫy 6 — static method bị override

Nếu Derived class cũng khai báo static method cùng signature với Base static method, nó **hides** thay vì overrides. `@Override` không được dùng trên static method.

### 19.7. Bẫy 7 — class-wide state bị hiểu là per-parent state

Nếu Outer A và Outer B tạo Inner objects, một `Inner.staticCounter` **không riêng biệt cho mỗi outer instance**. Nếu cần counts per Outer, đặt field ở Outer instance.

## 20. Nguyên tắc thiết kế static fields trong inner class

Một static member **có thể hợp lệ** nhưng không nhất thiết **nên được dùng**.

### 20.1. Khi phù hợp

- Immutable constants/logical metadata thuộc loại Inner.
- Static utilities không phụ thuộc instance state.
- Static nested helper type chỉ liên quan đến Inner về mặt khái niệm.
- Class-wide caches/counters có scope rõ, được đồng bộ phù hợp.
- Nested records/enums dùng làm value types/constants bên trong implementation của Inner.

### 20.2. Khi nên cân nhắc thiết kế khác

- Method phải dùng liên tục Outer.this hoặc Inner.this: có thể nên là **instance method**.
- Counter/cache mong đợi riêng từng enclosing Outer object: static field đặt sai scope.
- Static mutable state gây khó test và concurrency races: cân nhắc inject service, immutable values hoặc explicit owners.
- Static type hoặc helper được dùng phổ biến ở ngoài Inner: có thể đặt ở một static nested type của Outer hoặc top-level class để API dễ hiểu hơn.
- Hệ thống cần tương thích Java trước 16: static declarations nonconstant trong inner không biên dịch với source level cũ.

### 20.3. Đặt tên và API clarity

Dù `Outer.Inner.Helper` là một legal type path, cây qualification quá sâu có thể làm API khó đọc. Nếu Helper thật sự độc lập và reusable, top-level utility hoặc `Outer.Helper` có thể thích hợp. Nếu Helper chỉ là implementation detail, giữ private/package-private khi phù hợp.

### 20.4. Testability của static mutable state

Static caches/counters tồn tại qua nhiều instances và nhiều tests trong cùng class-loading context. Nếu tests kỳ vọng mỗi test bắt đầu từ 0 nhưng không reset static state, thứ tự tests có thể ảnh hưởng kết quả. Dùng thiết kế test isolation hoặc explicit reset controlled, tránh phụ thuộc thứ tự thực thi.

## 21. Static members và generic type parameters

Một inner class có thể generic và giữ instance type parameter:

~~~java
class Outer<T> {
    class Inner<U> {
        U value;
    }
}
~~~

Các type parameters `T` và `U` là một phần type-level generic context của instances, nhưng **static context không có một type-argument binding riêng theo từng instance**. Vì vậy static members không được dùng enclosing/class type variables như thể chúng là một type cụ thể được chọn sẵn.

Ví dụ cố ý lỗi:

~~~java
class Outer<T> {
    class Inner<U> {
        static U cached;    // Cố ý lỗi: non-static type variable U.
        static T build() {  // Cố ý lỗi: non-static type variable T.
            return null;
        }
    }
}
~~~

Java không cho phép static member của một generic class tùy tiện tham chiếu non-static type variables từ parameterized enclosing declarations. Có thể khai báo **method-level type parameter** riêng:

~~~java
class Outer<T> {
    class Inner<U> {
        static <X> X identity(X value) {
            return value;
        }
    }
}
~~~

`X` là type parameter của chính static method, không phải generic argument của một Outer/Inner instance.

### 21.1. Static field không có một bản cho mỗi generic instantiation

`Outer<String>.Inner<Integer>` và `Outer<Long>.Inner<Double>` không làm JVM tạo một static field riêng cho từng type-argument combination. Generics chủ yếu được triển khai qua erasure, còn static fields thuộc runtime class.

Đừng coi `Inner<U>.staticCache` là cache tự chia theo U; nếu cần phân vùng theo type, phải quản lý explicit key/type token hoặc một class/object owner riêng.

## 22. Reflection và kiểm tra static modifiers

Nếu cần kiểm tra một member có static không, `java.lang.reflect.Modifier.isStatic(...)` trả lời theo modifiers được reflection expose:

~~~java
boolean staticField =
        java.lang.reflect.Modifier.isStatic(
                Outer.Inner.class
                        .getDeclaredField("counter")
                        .getModifiers());
~~~

Đây là fragment: method gọi reflection có thể cần xử lý `NoSuchFieldException`; `counter`/types phải tồn tại.

**Phân biệt:** Reflection cho phép kiểm tra staticness của một member, nhưng không biến Inner thành static nested type. `Outer.Inner.class` cũng là một class literal; chỉ việc lấy Class object không tạo một Inner instance.

### 22.1. Compiler-generated synthetic members

Compiler có thể sinh artifacts cho inner classes (ví dụ liên kết enclosing instance), nhưng tên và implementation details của synthetic fields không phải API application ổn định. Đừng kiểm thử semantics static/inner bằng cách suy đoán một tên synthetic field cụ thể.

## 23. Compatibility và bảo trì nhiều Java versions

Một library công khai nested types cho consumers cần cân nhắc:

- Source compatibility với code biên dịch ở language levels cũ.
- Binary compatibility nếu đổi vị trí field/method từ helper sang Inner.
- Reflection callers và serialized descriptors nếu API thay names.
- JVM target/runtime class-file version.
- Module/package visibility.
- Test/build pipeline có thực sự dùng compiler source level mong đợi không.
- Code samples/documentation có ghi yêu cầu **Java 16+** rõ không.

**Không phải cứ có JDK 17 installed là build tự dùng Java 17 source level.** Các dự án vẫn có thể đặt `--release 8`, `--release 11` hoặc `--release 15` để hỗ trợ sản phẩm cũ.

Nếu cần một cách viết chạy với cả source 11 và 17, giữ static mutable members/utilities trong top-level class hoặc một **static nested member class** ở vị trí được phép, thay vì trong non-static inner class.

## 24. Checklist đánh giá code hiện hành

1. Lớp đang xét là **non-static member inner**, static nested, local hay anonymous?
2. Có đang đọc giáo trình áp dụng Java trước 16 không?
3. Dự án thực sự biên dịch bằng `--release`/source level nào?
4. `static final` field có thật sự là **constant variable** không?
5. Có static initializer trong inner class không? Source level ≥16 chứ?
6. Có static method cần enclosing instance state không?
7. Static method đã nhận reference tường minh thay vì dùng `this` hoặc `Outer.this` chưa?
8. Static field cần global-per-class hay per-Outer-instance semantics?
9. Static mutable state đã có concurrency policy chưa?
10. Có gọi static member qua type name, tránh gây hiểu nhầm per-instance không?
11. Có static nested helper, enum, interface, record bên trong Inner không?
12. Các implicit static types có được dùng mà không tạo Outer/Inner instance khi thích hợp không?
13. Khi **tạo Inner instance**, đã có enclosing Outer instance chưa?
14. Access modifiers và enclosing type accessibility có phù hợp không?
15. Static methods trong inheritance có được hiểu là **hiding**, không overriding không?
16. Code có `@Override` sai trên static method không?
17. Có generic type parameter bị tham chiếu từ static context trái rules không?
18. Có nhận ra static fields không riêng cho từng generic type-argument combination không?
19. Có phụ thuộc vào static initialization timing qua constant-variable inlining không?
20. Tests có tránh dùng initialization output không được bảo đảm order không?
21. Có đang dựa vào compiler-generated synthetic field name không?
22. Có refactor API mà không xem source/binary compatibility không?
23. Có private static member nhưng exposing class lại inaccessible từ nơi gọi không?
24. Local class có bị gắn modifier static trái syntax không?
25. Anonymous class static member có bị gọi nhầm qua interface/supertype không?
26. Có source-level tests chạy với Java 17 và compatibility build khi cần không?
27. Có cảnh báo rằng quy tắc trước Java 16 đã lỗi thời trong documentation không?

## 25. Bài tập tự kiểm tra có đáp án

**Câu 1.** Từ Java version nào inner class được phép khai báo static fields/methods/initializers không giới hạn vào constant variables?

**Đáp án:** Từ Java 16; bài viết dùng Java 17+.

**Câu 2.** Inner class có static method có trở thành static nested class không?

**Đáp án:** Không. Class declaration vẫn non-static inner; tạo instance còn cần enclosing outer instance.

**Câu 3.** Trước Java 16, `static final int MAX = 10;` trong inner class có hợp lệ không?

**Đáp án:** Có, đây là static final constant variable kiểu primitive với constant expression.

**Câu 4.** Trước Java 16, `static final Integer LIMIT = 10;` có hợp lệ không?

**Đáp án:** Không theo ngoại lệ constant variable, vì Integer là reference type chứ không phải primitive/String.

**Câu 5.** `static final String NAME = helper();` có là constant variable không?

**Đáp án:** Không nếu helper() là method call; nó không phải constant expression.

**Câu 6.** `static int count;` trong inner class Java 17 có hợp lệ không?

**Đáp án:** Có. Đây là static field nonconstant được phép từ Java 16.

**Câu 7.** `static { count = 1; }` trong inner class Java 17 có hợp lệ không?

**Đáp án:** Có, static initialization block được phép.

**Câu 8.** Static method của Inner có tự dùng `Outer.this` không?

**Đáp án:** Không, vì static context không có enclosing instance được chọn.

**Câu 9.** Instance method của Inner có thể đọc field private của Outer enclosing instance không?

**Đáp án:** Có khi lexical/access context phù hợp; inner instance có enclosing Outer instance.

**Câu 10.** Đọc `Outer.Inner.counter` có cần tạo Inner instance không?

**Đáp án:** Không, đó là static member access qua type; class initialization có thể áp dụng theo API rules.

**Câu 11.** Muốn tạo non-static Outer.Inner từ code ngoài Outer thì viết thế nào?

**Đáp án:** Tạo Outer instance trước rồi `outer.new Inner()` khi constructors/types accessible.

**Câu 12.** Static field trong Inner có riêng cho mỗi Outer object không?

**Đáp án:** Không. Nó thuộc Inner runtime class trong class loader context, không phải enclosing Outer instance.

**Câu 13.** Có thể đặt `static class Helper` bên trong non-static Inner từ Java 16 không?

**Đáp án:** Có; Helper là static nested member class của Inner.

**Câu 14.** Nested record bên trong Inner có bắt buộc có Inner instance để tạo không?

**Đáp án:** Không; member record implicitly static theo Java 17 rules.

**Câu 15.** Nested enum bên trong Inner có được đặt ở Java 17 không?

**Đáp án:** Có; enum member declaration là implicitly static.

**Câu 16.** Member interface của Inner có implicitly static không?

**Đáp án:** Có; nó là member type và không cần Inner instance cho bản thân type.

**Câu 17.** Local class khai báo trong method có thể chứa `static int count;` ở Java 17 không?

**Đáp án:** Có theo rules hiện hành.

**Câu 18.** Có thể viết `static class Local` trực tiếp trong method không?

**Đáp án:** Không; local class declaration không có static modifier kiểu member declaration.

**Câu 19.** Anonymous class body có static method Java 17 không?

**Đáp án:** Có, nhưng anonymous class không có một source-level simple name để gọi method đó theo kiểu `AnonymousType.method()` từ code bên ngoài.

**Câu 20.** `Runnable.helper()` có gọi được helper static khai báo riêng trong một anonymous Runnable subclass không?

**Đáp án:** Không, nếu chính interface Runnable không khai báo helper. Method thuộc anonymous class, không thuộc supertype Runnable.

**Câu 21.** Static method trong subclass cùng signature với static method superclass là override hay hiding?

**Đáp án:** Hiding; không dùng `@Override`.

**Câu 22.** Static method có dynamic dispatch theo runtime type của instance không?

**Đáp án:** Không theo cách instance overriding; static resolution dựa trên declared type.

**Câu 23.** Có thể dùng `Inner<T>.staticValue` như một static state khác cho mỗi T không?

**Đáp án:** Không. Static fields gắn với runtime class, không tự tách theo các type arguments.

**Câu 24.** Static method trong generic Inner có thể dùng generic class parameter U trực tiếp trong signature không?

**Đáp án:** Không theo cách lấy U từ một instance type parameter; static method có thể khai báo type parameter riêng như `static <X> X id(X x)`.

**Câu 25.** Đọc compile-time constant field có luôn kích hoạt static initialization không?

**Đáp án:** Không. Constant variables có thể được compile-time inlined và không đòi initialization như nonconstant static field active use.

**Câu 26.** `count++` trên static int có thread-safe không?

**Đáp án:** Không tự động; ++ là read-modify-write không atomic theo nhu cầu multi-thread.

**Câu 27.** Project chạy JDK 17 nhưng biên dịch với `--release 11` có dùng static nonconstant field trong inner class không?

**Đáp án:** Không, vì source rules bị giới hạn theo release 11.

**Câu 28.** `public static` member trong `private Inner` có tự publicly accessible không?

**Đáp án:** Không. Member accessibility còn phụ thuộc việc enclosing type có accessible không.

**Câu 29.** Có thể dùng static fields trong inner class để ghi per-Outer counter không?

**Đáp án:** Không nếu mỗi Outer cần counter riêng; dùng instance field của Outer.

**Câu 30.** Khi nào nên để static utility trong Inner thay vì top-level/static nested helper của Outer?

**Đáp án:** Khi utility thuộc đúng conceptual responsibility của Inner, không cần instance state, accessibility/compatibility rõ ràng và không gây thiết kế khó hiểu.

## 26. Kết luận

**Thành viên static trong inner class đã được Java cho phép rộng hơn từ Java 16.** Hãy cập nhật kiến thức cũ: restriction “inner class chỉ có static final compile-time constants” không còn đúng cho Java 17+. Một non-static member inner class có thể có static fields, static methods, static initialization blocks và static nested member types; local và anonymous inner classes cũng có các static declarations phù hợp theo quy tắc hiện hành.

Điều **không đổi** là bản chất inner class: một instance non-static inner class vẫn có enclosing outer instance, trong khi **static members không thuộc về một Inner/Outer instance cụ thể**. Static contexts không tự có `this` hoặc `Outer.this`; static methods không override theo dynamic dispatch; class initialization và thread-safety vẫn theo rules chung của Java.

Khi thiết kế và bảo trì ứng dụng, hãy phân biệt ba câu hỏi: **loại nested class là gì? member có static hay không? source level mà compiler đang dùng là version nào?** Trả lời đúng cả ba sẽ giúp sử dụng tính năng Java 16+ mà không nhầm semantics hoặc vô tình làm hỏng tương thích với Java cũ.
