# Truyền đối số tới hàm khởi tạo của lớp cha khi tạo lớp vô danh trong Java

Trong Java, **lớp vô danh** (*anonymous class*) cho phép tạo một subclass hoặc một implementation của interface ngay tại biểu thức tạo đối tượng, không cần đặt tên class trong mã nguồn. Khi lớp vô danh **kế thừa một class có constructor nhận tham số**, Java cho phép đặt các đối số vào cặp ngoặc của biểu thức `new SuperClass(arguments) { ... }`. Những đối số này được dùng để chọn và gọi **constructor của lớp cha**, không phải constructor tự định nghĩa trong thân lớp vô danh.

Ví dụ nhỏ nhất:

```java
abstract class Greeting {
    protected final String name;

    Greeting(String name) {
        this.name = name;
    }

    abstract String say();
}

public class Main {
    public static void main(String[] args) {
        Greeting greeting = new Greeting("An") {
            @Override
            String say() {
                return "Xin chào " + name;
            }
        };

        System.out.println(greeting.say());
    }
}
```

Lưu thành `Main.java`, chạy:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Stdout:

```text
Xin chào An
```

Ở đây:

- `Greeting` là **abstract superclass** với constructor `Greeting(String name)`.
- `new Greeting("An") { ... }` vừa khai báo một **anonymous subclass**, vừa tạo một instance của subclass ấy.
- `"An"` là đối số được chuyển vào **constructor `Greeting(String)`** để khởi tạo phần trạng thái của superclass.
- Method `say()` được override nhằm hoàn thiện subclass concrete.
- **Không** có khai báo constructor mang tên của anonymous class trong phần `{ ... }`.

Bài học dành cho **Java 17+**, tập trung vào cú pháp, overload resolution, thứ tự đánh giá đối số và khởi tạo object, kiểm tra access/checked exceptions, anonymous subclass của inner class, khác biệt khi implements interface, generics, initializer blocks, lỗi biên dịch thường gặp, các tình huống thiết kế thực tế và bài tập tự kiểm tra.

## 1. Phân biệt “constructor của lớp cha” và “constructor của lớp vô danh”

Một anonymous class **không có tên khai báo trong source**, nên bạn không thể tự định nghĩa constructor theo cú pháp:

```java
new Greeting("An") {
    // Greeting(String name) { ... } // Không phải cách khai báo constructor ở đây.
};
```

Trong biểu thức `new Greeting("An") { ... }`, trình biên dịch xác định constructor phù hợp của `Greeting` bằng những quy tắc chọn constructor áp dụng cho class instance creation. Anonymous class có **constructor do compiler tạo ra** để thực hiện quá trình khởi tạo, trong đó phần constructor của superclass được gọi với đối số phù hợp.

**Không nên hiểu** là có hai đối tượng, một `Greeting` và một anonymous wrapper. Chỉ có **một object của anonymous subclass**, phần superclass của object đó được khởi tạo bởi constructor `Greeting`.

### Cách hình dung

```text
Biểu thức: new Greeting("An") { override say() }
            │
            ├─ tạo anonymous subclass của Greeting
            ├─ lựa chọn Greeting(String) theo "An"
            ├─ tạo một object subclass
            ├─ thực hiện constructor superclass
            ├─ thực hiện khởi tạo của anonymous subclass
            └─ trả tham chiếu kiểu Greeting
```

`Greeting greeting` là **kiểu của biến tham chiếu**. Runtime object là một subtype vô danh của Greeting. Khi gọi `greeting.say()`, dynamic dispatch chọn implementation override trong anonymous class.

## 2. Cú pháp quan trọng

Dạng tổng quát khi superclass là một class có tên:

```java
SuperType reference = new SuperType(arg1, arg2) {
    // Fields, instance initializers, overridden methods...
};
```

Các thành phần:

| Phần cú pháp | Ý nghĩa |
| --- | --- |
| `SuperType` ngay sau `new` | Class được anonymous class kế thừa |
| `(arg1, arg2)` | Danh sách đối số để chọn constructor superclass |
| `{ ... }` | Body khai báo anonymous subclass |
| `SuperType reference` | Kiểu tĩnh mà caller dùng để truy cập API |
| `@Override` | Kiểm tra method có thật sự override/implement |
| `super.someMethod()` trong override | Gọi method implementation của superclass khi hợp lệ |

Phân biệt với dạng không có class body:

```java
new SuperType(arg1, arg2);
```

Dạng này tạo trực tiếp instance `SuperType`, nên chỉ hợp lệ khi SuperType concrete và constructor phù hợp. Dạng có `{ ... }` tạo **anonymous subclass**, có thể dùng với một abstract superclass nếu implementation đáp ứng các abstract methods.

### Phân biệt với constructor call `super(...)`

`super(arguments);` là **explicit constructor invocation** viết trong constructor body của **một named subclass** theo quy tắc Java. Trong anonymous class, bạn **không được tự khai báo constructor** để đặt `super(arguments);` bên trong. Thay vào đó truyền argument ở **biểu thức `new Base(arguments) { ... }`**.

## 3. Ví dụ đầu tiên: superclass giữ dữ liệu từ constructor

Lưu **`AnonymousConstructorBasic.java`**:

```java
abstract class Shape {
    private final String color;

    Shape(String color) {
        this.color = color;
    }

    public String description() {
        return "color=" + color;
    }

    abstract int area();
}

public class AnonymousConstructorBasic {
    public static void main(String[] args) {
        Shape square = new Shape("blue") {
            @Override
            int area() {
                return 4 * 4;
            }
        };

        System.out.println(square.description());
        System.out.println(square.area());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousConstructorBasic.java
java AnonymousConstructorBasic
```

Stdout:

```text
color=blue
16
```

Constructor của `Shape` nhận màu và khởi tạo private field `color`. Anonymous subclass **không truy cập trực tiếp private field** từ code của subclass, nhưng vẫn gọi được public inherited method `description()`. Anonymous subclass override `area()` để hoàn thiện abstract method.

**Bài học:** truyền tham số cho constructor superclass hoạt động bình thường với **abstract superclass**. Java không yêu cầu bạn có thể `new Shape("blue")` trực tiếp.

## 4. Khi nào nên dùng anonymous subclass nhận đối số?

Một anonymous subclass hợp lý khi:

- Có một **superclass** với constructor thiết lập invariant hoặc dependency.
- Chỉ cần một **implementation đặc biệt ở một điểm sử dụng**.
- Subclass override một vài methods trong phạm vi ngắn, dễ hiểu.
- Không cần tái sử dụng implementation dưới một class name riêng.
- Superclass cho phép kế thừa và constructor có thể truy cập từ ngữ cảnh này.

Ví dụ thực tế:
- Chuyên biệt hóa một `Processor` trừu tượng với tham số cấu hình.
- Cung cấp một callback object kế thừa base adapter có state.
- Dùng test fixture đặc biệt kế thừa một abstract base có constructor.
- Override một method của component framework có constructor tham số, nếu API framework hỗ trợ subclassing.

Nếu logic dài, dùng ở nhiều nơi hoặc cần constructor/state phức tạp, **named subclass** thường dễ test và bảo trì hơn anonymous class.

## 5. Constructor overload resolution

Superclasses có thể có nhiều constructors:

```java
class Item {
    Item(int value) {
        // ...
    }

    Item(String name) {
        // ...
    }
}
```

Khi viết:

```java
new Item(7) { };
new Item("A") { };
```

trình biên dịch sẽ xét **kiểu của biểu thức đối số tại compile time**, tìm constructor phù hợp và chọn overload theo quy tắc method/constructor invocation của Java.

Không phải anonymous class có một constructor riêng do bạn tùy ý chọn trong body. Lựa chọn superclass constructor đã được quyết định bởi **biểu thức `new`**.

### Quy tắc quan trọng

- Số lượng và kiểu đối số phải phù hợp với constructor có thể truy cập.
- Nếu nhiều constructor cùng khả dụng, Java áp dụng overload resolution.
- Có thể dùng widening, boxing/unboxing, varargs theo quy tắc cụ thể và thứ tự các pha lựa chọn.
- Nếu không có constructor phù hợp: compile error.
- Nếu có hai ứng viên đều tối ưu mà không chọn được ứng viên đặc hiệu nhất: ambiguous constructor call.
- Runtime value không thể tự chuyển lựa chọn overload đã được compiler quyết định theo static type.

## 6. Runnable: chọn constructor theo kiểu đối số

Lưu **`AnonymousOverloadDemo.java`**:

```java
class Message {
    private final String chosen;

    Message(int number) {
        chosen = "int:" + number;
    }

    Message(String text) {
        chosen = "String:" + text;
    }

    String describe() {
        return chosen;
    }
}

public class AnonymousOverloadDemo {
    public static void main(String[] args) {
        Message first = new Message(7) {
        };

        Message second = new Message("A") {
        };

        System.out.println(first.describe());
        System.out.println(second.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousOverloadDemo.java
java AnonymousOverloadDemo
```

Stdout:

```text
int:7
String:A
```

Constructor được chọn do `7` có kiểu `int` và `"A"` có kiểu `String`. Hai anonymous object không nhất thiết cùng anonymous class ở runtime, nhưng cả hai có superclass `Message` và sử dụng constructor phù hợp.

## 7. Widening, boxing và thứ tự lựa chọn

Xét:

```java
class Base {
    Base(long value) {
        System.out.println("long");
    }

    Base(Integer value) {
        System.out.println("Integer");
    }
}
```

Với `new Base(7) { }`, `7` là int literal. Trong overload resolution, primitive widening từ `int` sang `long` có thể được ưu tiên trong giai đoạn trước boxing sang `Integer`.

Với `new Base(Integer.valueOf(7)) { }`, đối số có kiểu `Integer`, nên constructor `Base(Integer)` là khớp trực tiếp.

### Runnable

Lưu **`AnonymousWideningDemo.java`**:

```java
class NumericBase {
    NumericBase(long value) {
        System.out.println("long");
    }

    NumericBase(Integer value) {
        System.out.println("Integer");
    }
}

public class AnonymousWideningDemo {
    public static void main(String[] args) {
        NumericBase first = new NumericBase(7) {
        };

        NumericBase second =
                new NumericBase(Integer.valueOf(7)) {
                };

        System.out.println(first != second);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousWideningDemo.java
java AnonymousWideningDemo
```

Stdout:

```text
long
Integer
true
```

Lưu ý: đây là hệ quả overload resolution Java, **không phải quy tắc riêng của anonymous classes**. Anonymous syntax chỉ dùng kết quả chọn constructor đó.

## 8. Constructor mơ hồ với `null`

Đoạn sau **cố ý không biên dịch**:

```java
class Base {
    Base(String value) {
    }

    Base(Integer value) {
    }
}

Base object = new Base(null) {
};
```

Hai overload `Base(String)` và `Base(Integer)` đều nhận `null`, nhưng `String` và `Integer` không có quan hệ kiểu khiến một constructor rõ ràng đặc hiệu hơn constructor kia. Compiler không thể chọn.

Cách giải quyết bằng **cast định hướng kiểu đối số**:

```java
Base first = new Base((String) null) {
};

Base second = new Base((Integer) null) {
};
```

Đây là các snippets minh họa trong cùng một phạm vi có `Base`; khi compile, không đặt đoạn ambiguous `new Base(null)` chưa sửa vào tệp runnable.

### Bài học

Không nên cho rằng anonymous class body hoặc override methods giúp compiler “đoán” superclass constructor. **Overload của constructor được chọn từ argument list**; method overrides trong body không gỡ ambiguity của `null`.

## 9. Đối số là biểu thức, không chỉ literal

Constructor arguments có thể là biểu thức Java bình thường:

```java
new ServiceConfig(prefix + suffix, calculatePort()) {
    // ...
};
```

Trước khi constructor superclass có thể chạy, các expressions cần được đánh giá theo quy tắc evaluation của Java.

### Những thứ có thể xảy ra khi đánh giá đối số

- Gọi một method và nhận giá trị.
- Tạo objects trung gian.
- Thực hiện arithmetic hoặc string concatenation.
- Ném runtime exception trước khi constructor chạy.
- Thực hiện side effects như ghi log hoặc tăng counter.
- Truyền một reference hiện có, **không tự sao chép sâu** object mà reference trỏ đến.

### Side effect trong argument list

Không nên phụ thuộc side effects phức tạp trong constructor arguments vì code trở nên khó đọc. Java có thứ tự đánh giá rõ ràng, nhưng thiết kế tốt thường tách các tính toán quan trọng thành biến tên rõ trước biểu thức `new`.

## 10. Thứ tự đánh giá đối số: trái sang phải

Java đánh giá các argument expressions **theo thứ tự từ trái sang phải**. Sau khi đánh giá thành công và có các giá trị phù hợp, constructor được gọi theo cơ chế class instance creation.

Lưu **`AnonymousArgumentOrderDemo.java`**:

```java
class PairBase {
    PairBase(int left, int right) {
        System.out.println("constructor:" + left + "," + right);
    }
}

public class AnonymousArgumentOrderDemo {
    static int evaluate(String label, int value) {
        System.out.println("evaluate:" + label);
        return value;
    }

    public static void main(String[] args) {
        PairBase value = new PairBase(
                evaluate("left", 1),
                evaluate("right", 2)) {
        };

        System.out.println("created:" + (value != null));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousArgumentOrderDemo.java
java AnonymousArgumentOrderDemo
```

Stdout:

```text
evaluate:left
evaluate:right
constructor:1,2
created:true
```

Không tự đảo thứ tự in của các argument expressions. Nếu một argument expression ném exception, các bước sau đó có thể không xảy ra; constructor superclass không được thực hiện thành công.

## 11. Nếu constructor superclass không nhận đối số?

Nếu superclass có constructor không tham số truy cập được, anonymous syntax vẫn dùng cặp ngoặc trống:

```java
class Base {
    Base() {
        System.out.println("base");
    }
}

Base instance = new Base() {
};
```

Ở đây `()` là lời yêu cầu constructor no-arg thích hợp của Base.

Nếu chỉ có:

```java
class Base {
    Base(int value) {
    }
}
```

thì `new Base() { }` **không biên dịch** do không có matching no-arg constructor; phải dùng `new Base(123) { }` hoặc sửa thiết kế superclass.

### Constructor mặc định có được sinh tự động?

Nếu class **không khai báo constructor nào**, Java có quy tắc sinh default constructor. Nhưng một khi bạn đã khai báo một constructor nhận tham số, trình biên dịch **không tự sinh thêm no-arg constructor** chỉ để anonymous subclass sử dụng.

## 12. Runnable: chỉ có constructor nhận đối số

Lưu **`AnonymousRequiredArgumentDemo.java`**:

```java
class RequiredBase {
    private final int id;

    RequiredBase(int id) {
        this.id = id;
    }

    int id() {
        return id;
    }
}

public class AnonymousRequiredArgumentDemo {
    public static void main(String[] args) {
        RequiredBase first = new RequiredBase(42) {
        };

        System.out.println(first.id());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousRequiredArgumentDemo.java
java AnonymousRequiredArgumentDemo
```

Stdout:

```text
42
```

Nếu bỏ `42` để viết `new RequiredBase() { }` thì sẽ bị compiler từ chối; superclass không có constructor không tham số phù hợp.

## 13. Access modifier của constructor superclass

Ngay cả khi argument types phù hợp, constructor superclass phải **truy cập được** tại điểm khởi tạo anonymous class theo Java access rules.

| Constructor superclass | Điều cần xét |
| --- | --- |
| `public` | Có thể gọi từ code có thể truy cập type, còn phụ thuộc module/type |
| Package-private | Giới hạn truy cập package theo rules |
| `protected` | Có các quy tắc package/subclass cụ thể; không mặc nhiên gọi được từ mọi nơi |
| `private` | Không dùng được từ code không có quyền private/nest access |
| Không có matching constructor | Compile error dù class body có override hoàn chỉnh |

**Lưu ý quan trọng về `protected`:** constructors được bảo vệ không hoạt động giống một method public. Với subclass ở package khác, cách truy cập và dạng biểu thức tạo object phải thỏa JLS; không nên tổng quát “anonymous class extends được thì mọi protected constructor luôn gọi được”.

### Không lách access bằng anonymous body

Việc thêm:

```java
new SecretBase(7) {
    // override someMethod...
};
```

không làm constructor private trở thành public. Java kiểm tra access và constructor selection trước khi tạo object.

## 14. Ví dụ compile-negative: constructor private

Giả sử có **hai top-level classes độc lập**, không phải các nestmates:

```java
class SecretBase {
    private SecretBase(int id) {
    }
}

class Client {
    void create() {
        // new SecretBase(7) { }; // Không được gọi private constructor.
    }
}
```

Đây là snippet minh họa access error. Compiler không cho Client gọi constructor private của SecretBase.

Cách xử lý:
- Dùng public/protected/package-private constructor **nếu thiết kế thật sự cho phép**.
- Dùng factory API do SecretBase công bố nếu caller chỉ cần một object.
- Nếu superclass **cố tình cấm subclassing**, đừng ép anonymous subclass; chọn composition/strategy.
- Trong nested/nestmate contexts, các quyền private access có thể khác; vì vậy không phát biểu “private constructor không bao giờ truy cập được ở bất kỳ vị trí nào”.

### Phân biệt constructor visibility và class visibility

Dù constructor public, nếu superclass type không accessible với caller, biểu thức cũng không hợp lệ. Ngược lại, type public nhưng constructor không accessible vẫn bị chặn.

## 15. Lớp cha `final` không thể có anonymous subclass

Một anonymous class được viết bằng `new FinalBase(...) { ... }` là **một subclass** của FinalBase.

Vì vậy:

```java
final class FinalBase {
    FinalBase(int value) {
    }
}

// new FinalBase(3) { }; // Compile error.
```

Không hợp lệ ngay cả khi anonymous body **rỗng**. Chỉ cần có `{ }` sau `new FinalBase(3)` là đã yêu cầu anonymous subclass.

Ngược lại:

```java
FinalBase value = new FinalBase(3);
```

là tạo **trực tiếp** FinalBase instance, hợp lệ nếu constructor/type accessible.

### Các loại class vốn final

- `String` là final.
- Record classes là final.
- Enum classes có những hạn chế subclass/constructor đặc thù, không dùng anonymous `new EnumType(...) { }` để tạo arbitrary enum instance.
- Một superclass `sealed` chỉ cho phép direct subclasses được khai báo phù hợp trong permitted hierarchy; anonymous subclass tùy ý không thể vượt rào đó.

**Câu hỏi đầu tiên không chỉ là “constructor có nhận tham số không?” mà còn là “superclass có cho phép kế thừa không?”.**

## 16. Anonymous subclass của abstract class

Đây là use case tự nhiên:

```java
abstract class Processor {
    private final String name;

    Processor(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    abstract int process(int input);
}
```

Một anonymous subclass có thể truyền `name` vào superclass constructor và implement abstract method `process`:

```java
Processor twice = new Processor("twice") {
    @Override
    int process(int input) {
        return input * 2;
    }
};
```

Trong trường hợp này **không có cách `new Processor("twice")` trực tiếp** vì Processor abstract. Cặp `{ ... }` vừa khai báo một concrete anonymous subtype và cung cấp implementation để có object.

### Runnable

Lưu **`AnonymousAbstractProcessorDemo.java`**:

```java
abstract class Processor {
    private final String label;

    Processor(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }

    abstract int process(int input);
}

public class AnonymousAbstractProcessorDemo {
    public static void main(String[] args) {
        Processor twice = new Processor("twice") {
            @Override
            int process(int input) {
                return input * 2;
            }
        };

        System.out.println(twice.label());
        System.out.println(twice.process(9));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousAbstractProcessorDemo.java
java AnonymousAbstractProcessorDemo
```

Stdout:

```text
twice
18
```

Đối số `"twice"` đi vào constructor `Processor(String)`; behavior `process` đến từ subclass vô danh.

## 17. Constructor arguments khi anonymous class implements interface

Hai cú pháp trông tương tự nhưng **ngữ nghĩa khác nhau**:

**Anonymous subclass của class:**

```java
new AbstractProcessor("A") {
    @Override
    void execute() {
        // ...
    }
};
```

**Anonymous implementation của interface:**

```java
new Runnable() {
    @Override
    public void run() {
        // ...
    }
};
```

Với `Runnable` là interface, không có constructor `Runnable(String)` để nhận đối số. Anonymous class implementing Runnable có superclass Object phù hợp và interface target Runnable.

Vì vậy viết:

```java
// new Runnable("A") { ... } // Không hợp lệ.
```

là sai. Nếu callback cần tham số như `"A"`, có thể:
- Dùng một **effectively-final local variable** được capture.
- Định nghĩa **instance field** và instance initializer trong anonymous class.
- Viết named class implementing Runnable với constructor nhận tham số.
- Dùng lambda capture nếu Runnable là functional interface và semantics phù hợp.

## 18. Runnable: interface không nhận constructor arguments nhưng capture dữ liệu

Lưu **`AnonymousInterfaceCaptureDemo.java`**:

```java
public class AnonymousInterfaceCaptureDemo {
    static Runnable makeTask(String message) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("task:" + message);
            }
        };
    }

    public static void main(String[] args) {
        Runnable first = makeTask("A");
        Runnable second = makeTask("B");

        first.run();
        second.run();
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousInterfaceCaptureDemo.java
java AnonymousInterfaceCaptureDemo
```

Stdout:

```text
task:A
task:B
```

`message` là method parameter của `makeTask`, được anonymous class capture theo quy tắc effectively final. Nó **không phải argument gửi vào constructor `Runnable`**, bởi Runnable là interface và không có constructor ấy.

## 19. Khởi tạo riêng phần anonymous subclass: instance fields và initializers

Dù không có explicit constructor mang tên anonymous class, body vẫn có thể chứa **instance fields** và **instance initializer blocks**:

```java
Base value = new Base(7) {
    private final String tag;

    {
        tag = "configured";
    }

    @Override
    String describe() {
        return super.describe() + ":" + tag;
    }
};
```

Ý nghĩa:
- `Base(7)` khởi tạo superclass.
- Instance variable initializers/initializer blocks của anonymous subclass thực hiện sau phần khởi tạo superclass theo trình tự Java.
- Instance initializer có thể dùng để thiết lập state riêng của subclass.
- Không khai báo `AnonymousClassName(...)` vì không có class name.
- Static methods/fields theo rules hiện hành là vấn đề khác với constructor; **static initializer không thay thế instance initializer**.

### Đừng nhầm initializer với constructor

Instance initializer là một block không có tên, ví dụ `{ tag = "configured"; }`. Nó không có danh sách parameters riêng để caller truyền vào bằng syntax `new Base(7, "tag")` trừ khi superclass có constructor phù hợp với những arguments ấy.

Nếu muốn nhiều tham số configuration riêng của implementation, **named subclass với constructor rõ ràng** thường phù hợp hơn.

## 20. Runnable: constructor superclass rồi initializer của anonymous class

Lưu **`AnonymousInitializerOrderDemo.java`**:

```java
class Base {
    Base(int id) {
        System.out.println("base:" + id);
    }

    String describe() {
        return "base";
    }
}

public class AnonymousInitializerOrderDemo {
    public static void main(String[] args) {
        Base instance = new Base(7) {
            private final String tag;

            {
                tag = "ready";
                System.out.println("anonymous-initializer");
            }

            @Override
            String describe() {
                return super.describe() + ":" + tag;
            }
        };

        System.out.println(instance.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousInitializerOrderDemo.java
java AnonymousInitializerOrderDemo
```

Stdout:

```text
base:7
anonymous-initializer
base:ready
```

Superclass constructor chạy trước instance initializer của anonymous subclass; sau đó lời gọi `describe()` sử dụng method override.

### Chú ý thứ tự fields và initializer blocks

Trong một class, instance field initializers và instance initializer blocks được thực hiện theo thứ tự văn bản thích hợp trong giai đoạn khởi tạo subclass. Không nên đổi vị trí nếu việc khởi tạo có side effects phụ thuộc nhau.

## 21. Một thứ tự đầy đủ: đánh giá arguments, superclass, anonymous initializer, method

Lưu **`AnonymousFullOrderDemo.java`**:

```java
class OrderedBase {
    OrderedBase(int number) {
        System.out.println("base-constructor:" + number);
    }

    String label() {
        return "base";
    }
}

public class AnonymousFullOrderDemo {
    private static int argument() {
        System.out.println("evaluating-argument");
        return 5;
    }

    public static void main(String[] args) {
        OrderedBase value = new OrderedBase(argument()) {
            private final String suffix = "ready";

            {
                System.out.println("anonymous-initializer");
            }

            @Override
            String label() {
                return super.label() + "-" + suffix;
            }
        };

        System.out.println(value.label());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousFullOrderDemo.java
java AnonymousFullOrderDemo
```

Stdout:

```text
evaluating-argument
base-constructor:5
anonymous-initializer
base-ready
```

**Bốn thời điểm khác nhau:**
1. `argument()` chạy để tạo constructor argument.
2. Constructor `OrderedBase(int)` khởi tạo superclass portion.
3. Anonymous subclass khởi tạo `suffix` và thực hiện initializer block.
4. Caller gọi `label()` qua dynamic dispatch sau khi object hoàn tất construction.

Dùng ví dụ này để dự đoán output thay vì cho rằng mọi dòng trong body anonymous chạy ngay khi compiler gặp `new`.

## 22. Cảnh báo nghiêm trọng: constructor superclass gọi overridable method

Superclass constructor có thể gọi một method được subclass override. Java dùng **dynamic dispatch** ngay cả trong constructor, trong khi instance fields của anonymous subclass **chưa được khởi tạo theo initializer của subclass**.

Điều này có thể làm override nhìn thấy field giá trị mặc định như `null` hoặc `0`.

**Đây không phải lỗi riêng anonymous class**: mọi subclass có thể gặp vấn đề khi superclass constructor gọi overridable method.

### Runnable: quan sát trạng thái chưa khởi tạo

Lưu **`AnonymousConstructorDispatchDemo.java`**:

```java
class DispatchBase {
    DispatchBase() {
        System.out.println("during-constructor:" + describe());
    }

    String describe() {
        return "base";
    }
}

public class AnonymousConstructorDispatchDemo {
    public static void main(String[] args) {
        DispatchBase instance = new DispatchBase() {
            private String state = "ready";

            @Override
            String describe() {
                return state;
            }
        };

        System.out.println("after-constructor:"
                + instance.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousConstructorDispatchDemo.java
java AnonymousConstructorDispatchDemo
```

Stdout:

```text
during-constructor:null
after-constructor:ready
```

Trong `DispatchBase()`, lời gọi `describe()` dispatch đến override của anonymous subclass, nhưng `state` chưa chạy initializer `"ready"` nên vẫn `null`. Sau khi object hoàn tất, nó thành `"ready"`.

### Quy tắc thiết kế

**Tránh gọi overridable instance methods từ constructors** khi method dựa vào subclass state. Có thể:
- Chỉ gọi private/final/static helper không override được nếu phù hợp.
- Hoãn callback tới sau khi construction hoàn tất.
- Đưa invariant validation vào constructor bằng dữ liệu đã có.
- Dùng factory/configuration API rõ để tránh override-before-initialization hazard.

## 23. Gọi method superclass bằng `super.method()`

Anonymous class có thể override một instance method rồi gọi bản superclass:

```java
Base value = new Base("A") {
    @Override
    String render() {
        return "[" + super.render() + "]";
    }
};
```

`super.render()` là **method invocation** hợp lệ trong instance method override khi superclass có method phù hợp và access cho phép.

**Không nhầm `super.render()` với `super("A");`**:
- `super.render()` gọi inherited superclass method.
- `super("A");` là constructor invocation, chỉ xuất hiện trong constructor body hợp lệ của named class, không thể đặt tùy tiện trong body/initializer anonymous class.

### Runnable

Lưu **`AnonymousSuperMethodDemo.java`**:

```java
class TextBase {
    private final String text;

    TextBase(String text) {
        this.text = text;
    }

    String render() {
        return text;
    }
}

public class AnonymousSuperMethodDemo {
    public static void main(String[] args) {
        TextBase base = new TextBase("hi");

        TextBase decorated = new TextBase("hi") {
            @Override
            String render() {
                return "[" + super.render() + "]";
            }
        };

        System.out.println(base.render());
        System.out.println(decorated.render());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousSuperMethodDemo.java
java AnonymousSuperMethodDemo
```

Stdout:

```text
hi
[hi]
```

## 24. Constructor argument chuyển reference, không tự clone object

Giả sử superclass constructor nhận `List<String>`:

```java
class ConfigBase {
    final java.util.List<String> settings;

    ConfigBase(java.util.List<String> settings) {
        this.settings = settings;
    }
}
```

Viết `new ConfigBase(sourceList) { ... }` chỉ truyền **một reference** làm argument. Nếu ConfigBase lưu direct alias, caller vẫn có thể sửa list ấy.

Việc anonymous class kế thừa ConfigBase **không tự thêm defensive copy**, không làm list immutable, cũng không cung cấp thread safety.

### Nếu cần snapshot

Constructor superclass nên chủ động quyết định:

```java
ConfigBase(java.util.List<String> settings) {
    this.settings = java.util.List.copyOf(settings);
}
```

Với immutable String elements và nguồn hợp lệ, đây là một snapshot cấu trúc phù hợp. Nếu elements mutable, `List.copyOf` vẫn chỉ shallow.

**Ownership policy thuộc contract của class và constructor**, không thuộc keyword anonymous.

## 25. Runnable: quan sát alias qua constructor

Lưu **`AnonymousMutableArgumentDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class ListBase {
    private final List<String> values;

    ListBase(List<String> values) {
        this.values = values;
    }

    String display() {
        return values.toString();
    }
}

public class AnonymousMutableArgumentDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        ListBase object = new ListBase(source) {
        };

        System.out.println(object.display());

        source.add("B");
        System.out.println(object.display());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousMutableArgumentDemo.java
java AnonymousMutableArgumentDemo
```

Stdout:

```text
[A]
[A, B]
```

Superclass giữ list reference được truyền vào. Anonymous subclass không thay đổi alias semantics.

## 26. Truyền arguments khác với capture effectively-final local variables

Hai cơ chế cần tách:

**Constructor argument:**

```java
String prefix = "A";
Base value = new Base(prefix) {
};
prefix = "B";
```

Có thể hợp lệ nếu anonymous body **không capture** biến `prefix`. Argument `prefix` được **đánh giá tại thời điểm tạo object**, rồi được chuyển cho constructor. Sau đó gán lại biến `prefix` không thay đổi argument đã truyền.

**Local-variable capture:**

```java
String prefix = "A";

Base value = new Base(prefix) {
    @Override
    String render() {
        return prefix; // Capture biến enclosing method.
    }
};

prefix = "B"; // Không còn effectively final: lỗi biên dịch.
```

Khi body anonymous trực tiếp tham chiếu local variable từ enclosing scope, variable đó phải final/effectively final theo rules.

**Điểm chính:** biến được dùng **trong argument list** không tự trở thành captured variable của anonymous body. Cần xem cả **phạm vi cú pháp nơi biến được tham chiếu**.

## 27. Runnable: argument value trước/sau gán lại biến

Lưu **`AnonymousArgumentVersusCaptureDemo.java`**:

```java
class LabelBase {
    private final String label;

    LabelBase(String label) {
        this.label = label;
    }

    String label() {
        return label;
    }
}

public class AnonymousArgumentVersusCaptureDemo {
    public static void main(String[] args) {
        String variable = "first";

        LabelBase snapshot = new LabelBase(variable) {
        };

        variable = "second";

        System.out.println(snapshot.label());
        System.out.println(variable);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousArgumentVersusCaptureDemo.java
java AnonymousArgumentVersusCaptureDemo
```

Stdout:

```text
first
second
```

Không có reference tới `variable` trong anonymous class body, nên việc biến local bị gán lại không vi phạm capture rule. Argument `"first"` đã được chuyển cho constructor trước khi biến đổi sang `"second"`.

## 28. Checked exceptions từ superclass constructor

Nếu constructor superclass khai báo checked exception, biểu thức `new SuperType(args) { ... }` phải tuân theo quy tắc exception checking.

Ví dụ:

```java
abstract class ReaderBase {
    ReaderBase(String source) throws java.io.IOException {
        if (source.isBlank()) {
            throw new java.io.IOException("empty");
        }
    }

    abstract String kind();
}
```

Tạo anonymous subclass:

```java
new ReaderBase("") {
    @Override
    String kind() {
        return "anonymous";
    }
};
```

Lời gọi constructor có thể ném `IOException`, vì vậy enclosing code phải catch hoặc declare `throws IOException` (hoặc supertypes phù hợp), trừ khi đã có xử lý tương ứng.

### Không “xóa” checked exception bằng override method

Việc anonymous body override `kind()` không thay đổi `throws IOException` của constructor superclass. Checked exception xuất phát từ **construction**, không phải abstract method được override.

## 29. Runnable: xử lý checked exception trong constructor

Lưu **`AnonymousCheckedConstructorDemo.java`**:

```java
import java.io.IOException;

abstract class ReaderBase {
    ReaderBase(String source) throws IOException {
        if (source.isBlank()) {
            throw new IOException("empty-source");
        }
    }

    abstract String kind();
}

public class AnonymousCheckedConstructorDemo {
    public static void main(String[] args) {
        try {
            ReaderBase value = new ReaderBase("") {
                @Override
                String kind() {
                    return "anonymous";
                }
            };

            System.out.println(value.kind());
        } catch (IOException error) {
            System.out.println("caught:" + error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousCheckedConstructorDemo.java
java AnonymousCheckedConstructorDemo
```

Stdout:

```text
caught:empty-source
```

Constructor ném exception trước khi object được tạo thành công; dòng gọi `value.kind()` không chạy. Catch block xử lý exception theo contract.

## 30. Nếu argument expression ném exception trước constructor

Trước khi constructor superclass chạy, Java phải đánh giá expressions trong argument list. Nếu chúng ném exception, construction bị dừng trước khi tới constructor.

Lưu **`AnonymousArgumentExceptionDemo.java`**:

```java
class BaseWithLog {
    BaseWithLog(int number) {
        System.out.println("constructor:" + number);
    }
}

public class AnonymousArgumentExceptionDemo {
    static int argument() {
        System.out.println("argument-start");
        throw new IllegalStateException("bad-input");
    }

    public static void main(String[] args) {
        try {
            BaseWithLog value =
                    new BaseWithLog(argument()) {
                    };

            System.out.println(value);
        } catch (IllegalStateException error) {
            System.out.println("caught:" + error.getMessage());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousArgumentExceptionDemo.java
java AnonymousArgumentExceptionDemo
```

Stdout:

```text
argument-start
caught:bad-input
```

Không có `constructor:...` vì argument expression ném exception trước khi constructor thực thi. Cú pháp anonymous class không “nuốt” exception.

## 31. Varargs constructor của superclass

Superclass có thể khai báo varargs constructor:

```java
class Labels {
    Labels(String... labels) {
        // ...
    }
}
```

Bạn có thể viết:

```java
new Labels("A", "B", "C") {
};
```

Anonymous class vẫn dùng quy tắc chọn constructor của Java, bao gồm varargs khi phù hợp.

### Runnable

Lưu **`AnonymousVarargsDemo.java`**:

```java
import java.util.Arrays;

class LabelsBase {
    private final String[] labels;

    LabelsBase(String... labels) {
        this.labels = labels.clone();
    }

    String describe() {
        return Arrays.toString(labels);
    }
}

public class AnonymousVarargsDemo {
    public static void main(String[] args) {
        LabelsBase value = new LabelsBase("A", "B", "C") {
        };

        System.out.println(value.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousVarargsDemo.java
java AnonymousVarargsDemo
```

Stdout:

```text
[A, B, C]
```

Lời gọi constructor nhận 3 string arguments theo varargs. Bên trong `LabelsBase` chủ động clone array để không giữ alias trực tiếp; việc clone là quyết định của superclass, không phải tính năng của anonymous syntax.

## 32. Anonymous subclass của inner class có enclosing instance riêng

Một **non-static member inner class** cần một enclosing instance của outer class khi khởi tạo. Nếu bạn tạo **anonymous subclass của inner class ấy từ code ngoài**, thường phải chỉ rõ owner:

```java
Outer outer = new Outer();
Outer.Inner value = outer.new Inner(args) {
    @Override
    void act() {
        // ...
    }
};
```

Có hai thông tin khác nhau:
- `outer` là **enclosing instance** gắn với inner superclass.
- `args` là **constructor arguments** được dùng để chọn/gọi constructor của Inner.

**Không trộn hai thứ** thành một parameter duy nhất. `outer.new Inner(3) { ... }` truyền enclosing owner qua qualifier và truyền `3` qua argument list.

### Khi ở instance method của Outer

Có thể không cần qualifier tường minh vì có enclosing Outer instance sẵn, ví dụ `new Inner(3) { ... }` trong một instance method phù hợp. Từ static context không có implicit Outer instance nên cần cung cấp owner.

## 33. Runnable: anonymous subclass của member inner superclass

Lưu **`AnonymousInnerSuperclassDemo.java`**:

```java
public class AnonymousInnerSuperclassDemo {
    private final String ownerName;

    AnonymousInnerSuperclassDemo(String ownerName) {
        this.ownerName = ownerName;
    }

    class Inner {
        private final int id;

        Inner(int id) {
            this.id = id;
        }

        String describe() {
            return ownerName + "#" + id;
        }
    }

    public static void main(String[] args) {
        AnonymousInnerSuperclassDemo owner =
                new AnonymousInnerSuperclassDemo("A");

        AnonymousInnerSuperclassDemo.Inner value =
                owner.new Inner(7) {
                    @Override
                    String describe() {
                        return "[" + super.describe() + "]";
                    }
                };

        System.out.println(value.describe());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousInnerSuperclassDemo.java
java AnonymousInnerSuperclassDemo
```

Stdout:

```text
[A#7]
```

`owner.new Inner(7)` cấp enclosing instance và constructor argument. Anonymous subclass có thể override inherited instance method, gọi `super.describe()`, và trả kết quả được trang trí.

### Trường hợp cần cẩn trọng

Với nested class ở package/type khác, access rules vẫn áp dụng. Qualifier phải có đúng static type thích hợp. Anonymous subclass không giúp vượt private/protected/module boundaries.

## 34. Kiểu tĩnh của reference và methods mới trong anonymous class

Ví dụ:

```java
Base value = new Base(7) {
    void onlyHere() {
        System.out.println("local behavior");
    }
};
```

`value` có **static type Base**. Nếu Base không khai báo `onlyHere()`, thì `value.onlyHere()` không hợp lệ khi gọi qua reference Base.

Anonymous class có thể định nghĩa methods riêng nhưng không có tên source type để caller dễ dùng làm API.

**Ngoại lệ ngữ cảnh `var`:** Java 10+ có các quy tắc type inference khiến `var` có thể giữ một anonymous class type trong một số trường hợp; vì vậy phát biểu chính xác là **qua reference được khai báo kiểu Base/interface**, chỉ có thể gọi những members mà static type đó cung cấp. Không tuyệt đối hóa rằng method riêng của anonymous class “không bao giờ gọi được”.

### Hướng thiết kế

Nếu caller cần những methods mới trong nhiều chỗ, một named subclass hoặc interface rõ hơn thường tốt hơn anonymous implementation. Anonymous class nên chủ yếu override một contract mà caller đã biết.

## 35. Generic superclass và đối số constructor

Anonymous class có thể kế thừa một generic superclass cụ thể:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}
```

Tạo subclass vô danh với type argument:

```java
Holder<String> item = new Holder<String>("Java") {
    @Override
    String value() {
        return super.value() + " 17";
    }
};
```

Giá trị `"Java"` được chuyển cho constructor `Holder(T)` sau type substitution thích hợp. Tham số kiểu `T` định hình type checking ở source, còn bytecode có erasure semantics của Java generics.

### `<>` diamond với anonymous class ở Java 17

Từ Java 9, có thể dùng diamond operator trong class instance creation của anonymous class khi các điều kiện inference/denotability hợp lệ:

```java
Holder<String> item = new Holder<>("Java") {
};
```

Điều này **không** có nghĩa mọi anonymous+diamond đều hợp lệ bất kể nội dung body. Một số hạn chế về methods và inferred types vẫn áp dụng. Nếu ví dụ generic phức tạp bị lỗi inference, kiểm tra compiler diagnostic và dùng type arguments tường minh khi rõ ràng hơn.

## 36. Runnable: generic anonymous superclass

Lưu **`AnonymousGenericSuperclassDemo.java`**:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class AnonymousGenericSuperclassDemo {
    public static void main(String[] args) {
        Holder<String> text = new Holder<String>("Java") {
            @Override
            String value() {
                return super.value() + " 17";
            }
        };

        Holder<Integer> number = new Holder<>(42) {
        };

        System.out.println(text.value());
        System.out.println(number.value());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousGenericSuperclassDemo.java
java AnonymousGenericSuperclassDemo
```

Stdout:

```text
Java 17
42
```

Đối số `"Java"` đi vào constructor generic superclass với `T=String`; đối số `42` được boxing/inference thích hợp cho `Holder<Integer>`. Anonymous body có thể override method, hoặc rỗng khi superclass đã concrete.

## 37. Constructor không phải method để override

Một superclass có:

```java
class Parent {
    Parent(String name) {
        // ...
    }
}
```

Subclass **không override constructor**. Constructors không được inherited theo nghĩa method members thông thường. Trong anonymous class, bạn cũng không “override” `Parent(String)` bằng cách viết một method tên Parent.

Đây là ba hoạt động khác nhau:
- **Constructor invocation**: `new Parent("A") { ... }` chọn/gọi constructor Parent.
- **Method overriding**: `@Override String label() { ... }` thay behavior một inherited instance method.
- **Instance initialization**: `{ ... }` trong anonymous class thiết lập state riêng sau superclass initialization thích hợp.

Nếu superclass constructor thiết lập invariant quan trọng, anonymous subclass **không bỏ qua** bước đó. Ngược lại, nếu superclass constructor không thể truy cập, subclass không thể tự bịa constructor thay thế để vượt rào.

## 38. `this` và `super` trong anonymous body

Trong instance method của anonymous class:
- `this` là **anonymous object** hiện tại.
- `super.someMethod()` tham chiếu superclass implementation hợp lệ.
- `Outer.this` trong ngữ cảnh có enclosing instance phù hợp là một **object khác** so với anonymous instance.
- `super(args)` không phải một expression gọi constructor trong method body; explicit constructor invocation cần vị trí constructor body hợp lệ, mà anonymous source class không khai báo constructor.

### Không nhầm với lambda

`this` trong lambda có lexical meaning của enclosing context, không phải anonymous object `this`. Nếu refactor anonymous class thành lambda để giảm dòng, behavior có thể đổi nếu code phụ thuộc `this` hoặc `super`.

### Không kết luận từ tên class sinh ra

`this.getClass().getName()` có thể cho một tên compiler-generated của anonymous class, nhưng không nên cố định nó thành stdout kỳ vọng giữa các toolchains hoặc thiết kế API quanh tên ấy.

## 39. Runnable: `this` là anonymous instance

Lưu **`AnonymousThisDemo.java`**:

```java
class BaseWithId {
    private final int id;

    BaseWithId(int id) {
        this.id = id;
    }

    String identify() {
        return "base:" + id;
    }
}

public class AnonymousThisDemo {
    public static void main(String[] args) {
        BaseWithId value = new BaseWithId(9) {
            @Override
            String identify() {
                return super.identify()
                        + ",subclass="
                        + (getClass() != BaseWithId.class);
            }
        };

        System.out.println(value.identify());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AnonymousThisDemo.java
java AnonymousThisDemo
```

Stdout:

```text
base:9,subclass=true
```

Runtime class khác chính xác `BaseWithId.class` vì object được tạo thuộc anonymous subclass. Nhưng cách viết không cần đoán tên binary `$1` của anonymous implementation.

## 40. Khi tham số là mutable object

Constructor có thể nhận một `StringBuilder`, `ArrayList` hoặc object khác mà caller tiếp tục dùng. Việc truyền reference vào constructor **không tạo immutable snapshot**.

Nếu superclass lưu reference:
- Caller mutate source object → superclass/anonymous instance có thể quan sát mutation.
- Anonymous subclass mutate source qua API superclass → caller có thể thấy đổi.
- Dùng `final` cho field reference không làm referent immutable.
- Trong concurrency, cần synchronization/safe publication riêng.

### Nên copy ở đâu?

Nếu mục tiêu của superclass là giữ một value snapshot:
- Copy ở constructor superclass hoặc factory rõ trách nhiệm.
- Không lộ internal mutable reference qua getter.
- Với elements mutable nested, cân nhắc deep copy đúng scope.

Nếu mục tiêu của superclass là giữ một live service/dependency, **không copy bừa**; document ownership/lifecycle.

Đây là chính sách thiết kế state, không phải vấn đề thêm dấu ngoặc vào anonymous expression.

## 41. Constructor forwarding với subclass có tên để so sánh

Nếu cùng behavior cần dùng nhiều lần, một named subclass cho constructor rõ ràng:

```java
abstract class Base {
    Base(String name) {
        // ...
    }

    abstract void execute();
}

final class Named extends Base {
    Named(String name) {
        super(name);
    }

    @Override
    void execute() {
        // ...
    }
}
```

Ở **named subclass constructor**, bạn có thể viết `super(name)` làm explicit constructor invocation. Ở anonymous subclass, bạn viết:

```java
Base instance = new Base("A") {
    @Override
    void execute() {
        // ...
    }
};
```

Không có named constructor để khai báo `super(name)` trong anonymous body.

### Chọn cách nào?

| Nhu cầu | Anonymous subclass | Named subclass |
| --- | --- | --- |
| Override gọn tại một call site | Phù hợp | Có thể hơi dài |
| Constructor riêng nhận nhiều loại config | Hạn chế | Rõ hơn |
| Logic cần reuse | Dễ lặp code | Phù hợp |
| Cần test class riêng | Khó gọi tên trực tiếp | Dễ hơn |
| Nhiều fields/invariants riêng | Instance initializer có thể dùng nhưng phức tạp | Constructor rõ |
| API public cần type riêng | Ít phù hợp | Phù hợp |
| Một abstract superclass có constructor tham số | `new Base(args){...}` | `extends Base` với `super(args)` |

**Không lạm dụng anonymous class chỉ để giảm số file** nếu logic có trách nhiệm riêng.

## 42. Runnable: named và anonymous cùng gọi superclass constructor

Lưu **`NamedVsAnonymousConstructorDemo.java`**:

```java
abstract class ActionBase {
    private final String name;

    ActionBase(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    abstract String execute();
}

final class NamedAction extends ActionBase {
    NamedAction(String name) {
        super(name);
    }

    @Override
    String execute() {
        return "named:" + name();
    }
}

public class NamedVsAnonymousConstructorDemo {
    public static void main(String[] args) {
        ActionBase named = new NamedAction("A");

        ActionBase anonymous = new ActionBase("B") {
            @Override
            String execute() {
                return "anonymous:" + name();
            }
        };

        System.out.println(named.execute());
        System.out.println(anonymous.execute());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NamedVsAnonymousConstructorDemo.java
java NamedVsAnonymousConstructorDemo
```

Stdout:

```text
named:A
anonymous:B
```

NamedAction chuyển tham số qua `super(name)` trong constructor có tên. Anonymous subclass chuyển `"B"` tại `new ActionBase("B") { ... }`. Kết quả cùng loại: superclass portion được khởi tạo với state từ đối số.

## 43. Mối quan hệ với access của protected constructor

Một protected constructor có thể phục vụ subclassing, nhưng các access rules không đơn giản như “thấy type là gọi được constructor”.

Ví dụ trong cùng package, protected member/constructor thường accessible theo package rules phù hợp:

```java
class Base {
    protected Base(int id) {
    }
}

class Client {
    void create() {
        Base value = new Base(1) {
        };
    }
}
```

Đây là snippet **trong cùng package** minh họa. Trường hợp khác package cần xét:
- Lớp nào là subclass của Base?
- Constructor access qua cú pháp nào?
- Qualified/unqualified new expression có hợp lệ?
- Module/package exports?
- Có nested access hay không?

**Không suy đoán rằng `protected` là `public`**. Nếu compiler báo access error, giải thích theo cấu trúc package/subclass và khai báo, không “chữa” bằng cast đối số.

## 44. Constructor có overload varargs và `null`

Sự có mặt của varargs làm constructor selection cần cẩn thận:

```java
class Base {
    Base(String single) {
    }

    Base(String... many) {
    }
}
```

Với `new Base("A") { }`, constructor fixed arity `Base(String)` có thể được chọn trước varargs invocation. Nhưng với `new Base((String[]) null) { }`, nó hướng tới constructor varargs theo một `String[]` argument.

Trong một số overload combinations, `null` vẫn gây ambiguity. Không nên chọn overload dựa vào “mình muốn ctor nào” mà bỏ qua static argument types.

### Gợi ý

- Đặt constructor signatures ít gây ambiguity.
- Có factory methods tên rõ nếu overload set phức tạp.
- Thêm cast chỉ khi thật sự cần quyết định một kiểu argument cụ thể.
- Dùng unit tests compile với đúng `--release` khi API có overload và generics/varargs.

## 45. Cách xử lý constructor exceptions ở API callback

Trong frameworks, anonymous subclass thường được tạo một lần và đăng ký:

```java
Processor callback = new Processor(config) {
    @Override
    void onEvent() {
        // ...
    }
};
registry.register(callback);
```

Đây là snippet về thiết kế, không phải chương trình chạy độc lập. Hai bước cần phân biệt:

1. **Construction:** chọn và gọi superclass constructor, có thể ném exception, validation failure hoặc side effect.
2. **Callback execution:** framework gọi `onEvent` sau này, có lifecycle/threading riêng.

Đừng trộn lỗi construction với lỗi callback. Nếu constructor thất bại, callback chưa được đăng ký trong luồng thông thường. Nếu callback chạy thread khác, object state/thread safety cần contract riêng.

## 46. Capture của anonymous class có thể giữ enclosing object sống lâu

Nếu anonymous class được tạo trong instance method và truy cập state của owner, nó có thể giữ reference đến enclosing instance:

```java
class Screen {
    private final String id = "screen";

    Runnable listener() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(id);
            }
        };
    }
}
```

Nếu listener được lưu trong một long-lived event bus và không unregister, Screen có thể bị giữ reachable lâu hơn mong đợi.

Constructor argument trong anonymous subclass cũng có thể làm object lưu long-lived dependencies. Vì vậy **enclosing instance capture** và **argument reference retention** là hai đường khác nhau có thể ảnh hưởng lifecycle.

Giải pháp:
- Chỉ capture state cần thiết.
- Truyền immutable values nếu phù hợp.
- Unregister/close đúng lifecycle.
- Với callback chỉ cần một behavior ngắn, cân nhắc lambda hoặc static helper nhưng vẫn review captured references.

## 47. Chọn API rõ hơn khi cần nhiều parameters riêng của anonymous implementation

Anonymous class không có constructor nguồn riêng, nên cách cấu hình thường là:
- Parameters của superclass constructor.
- Local variables captured effectively final.
- Instance fields initialized từ expressions/captured values.
- Instance initializer block.
- Methods gọi sau construction.

Khi quá nhiều config, constructor riêng của named subclass hoặc composition thường tốt hơn vì:
- Validation tập trung.
- Invariants rõ.
- Error handling dễ.
- Reuse và test dễ.
- Không phụ thuộc vào side effects rải trong anonymous initializer.

Ví dụ nếu implementation có 8 config parameters, 5 fields và 4 overrides, đó là dấu hiệu nên cân nhắc tách type có tên.

## 48. Checklist xác định constructor được gọi

Khi đọc `new Parent(a,b) { ... }`, đi theo thứ tự:

1. `Parent` là **class**, không phải interface chứ?
2. `Parent` có cho phép subclassing không (không final, ràng buộc sealed hợp lệ)?
3. `Parent` là generic class hay raw type?
4. Danh sách constructors được khai báo là gì?
5. Có default no-arg constructor không, hay đã khai báo constructor khác?
6. Constructors nào accessible ở caller?
7. Các argument expressions có static types gì?
8. Chúng có được evaluate từ trái sang phải mà không ném exception không?
9. Overload nào được chọn theo widening/boxing/varargs?
10. Có ambiguity, ví dụ `null` giữa unrelated reference types, không?
11. Constructor có checked `throws` phải catch/declare không?
12. Superclass constructor có gọi overridable method nguy hiểm không?
13. Anonymous subclass có implement đủ abstract methods không?
14. Fields/instance initializer của anonymous class phụ thuộc state nào?
15. Nếu superclass là member inner class, enclosing instance được cung cấp thế nào?
16. Reference khai báo kiểu Base có nhìn thấy anonymous-only methods không?
17. Có captured variables phải effectively final không?
18. Có alias mutable state được giữ bởi superclass không?
19. Có lifecycle/callback threading cần xem sau construction không?
20. Nếu logic phức tạp, named subclass có rõ hơn không?

**Chỉ sau khi trả lời những câu hỏi này** mới nên kết luận anonymous creation expression có compile, constructor nào chạy và stdout ra sao.

## 49. Bài tập 1 — Xác định đối số đi đâu

```java
abstract class Base {
    Base(String name) {
        System.out.println(name);
    }

    abstract void run();
}

Base value = new Base("A") {
    @Override
    void run() {
    }
};
```

**Đáp án:** `"A"` được chuyển vào constructor `Base(String)`, in `A` khi tạo object. Anonymous class implement `run`, không tự khai báo constructor.

## 50. Bài tập 2 — Anonymous class tự viết constructor?

```java
Base object = new Base("A") {
    Base(String name) {
        super(name);
    }
};
```

**Đáp án:** Không hợp lệ. Anonymous class không có source constructor mang tên `Base`. `Base` là superclass, không phải tên anonymous class. Dùng `new Base("A") { ... }` để chuyển arguments.

## 51. Bài tập 3 — No-arg constructor không tồn tại

```java
class Base {
    Base(int value) {
    }
}

Base value = new Base() {
};
```

**Đáp án:** Không biên dịch vì không có matching no-arg constructor. Đổi thành `new Base(3) { }` hoặc thêm no-arg constructor phù hợp vào Base theo design.

## 52. Bài tập 4 — Overload từ kiểu `int`

Superclasses có `Base(int)` và `Base(String)`. `new Base(7) { }` gọi constructor nào?

**Đáp án:** `Base(int)`, vì argument `7` là int literal.

## 53. Bài tập 5 — Ambiguous null

Superclasses có `Base(String)` và `Base(Integer)`. `new Base(null) { }` hợp lệ không?

**Đáp án:** Không, ambiguous khi không có một overload đặc hiệu hơn. Cast `(String) null` hoặc `(Integer) null` nếu muốn chọn cụ thể.

## 54. Bài tập 6 — Private superclass constructor

Class không liên quan cố `new SecretBase(1) { }` trong khi `SecretBase(int)` là private.

**Đáp án:** Không được gọi constructor private đó. Anonymous subclass không tự vượt access control. Xem xét access/factory hoặc thay thiết kế.

## 55. Bài tập 7 — Final superclass

```java
final class Box {
    Box(int n) {
    }
}

Box box = new Box(1) {
};
```

**Đáp án:** Không hợp lệ vì class `Box` final, không thể có anonymous subclass. `new Box(1)` không body là trường hợp khác và có thể hợp lệ.

## 56. Bài tập 8 — Abstract superclass constructor

Một abstract superclass `Base` có constructor `Base(String)` và abstract method `run()`.

**Đáp án:** Có thể tạo anonymous subclass bằng `new Base("A") { @Override void run() {...} }` nếu constructor accessible và mọi abstract requirements được implement.

## 57. Bài tập 9 — Interface với arguments

```java
Runnable r = new Runnable("A") {
    @Override
    public void run() {
    }
};
```

**Đáp án:** Không hợp lệ. `Runnable` là interface, không có constructor nhận String. Dùng `new Runnable() { ... }` với captured variable hoặc named implementation có constructor riêng.

## 58. Bài tập 10 — Interface capture parameter

```java
static Runnable make(String message) {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println(message);
        }
    };
}
```

**Đáp án:** Hợp lệ nếu `message` effectively final. Nó được **capture**, không truyền vào Runnable constructor.

## 59. Bài tập 11 — Thứ tự đánh giá

`new Base(f(), g()) { }` với `f()` và `g()` đều in tên của mình trước khi trả int.

**Đáp án:** Java đánh giá `f()` trước `g()`. Constructor chạy sau khi đánh giá arguments thành công.

## 60. Bài tập 12 — Argument ném exception

`f()` trong `new Base(f()) { }` ném `IllegalStateException` trước khi trả về.

**Đáp án:** Constructor Base chưa chạy; biểu thức construction dừng và exception lan theo quy tắc Java, trừ khi catch ở outer code.

## 61. Bài tập 13 — Checked exception của constructor

`Base() throws IOException` và caller dùng `new Base() { }` trong method không catch/declare.

**Đáp án:** Không hợp lệ nếu `IOException` không được xử lý. Anonymous override methods không tự loại bỏ checked exception từ constructor.

## 62. Bài tập 14 — Instance initializer

```java
Base value = new Base(3) {
    {
        System.out.println("init");
    }
};
```

**Đáp án:** Constructor superclass chạy trước instance initializer của anonymous subclass. Initializer không phải explicit constructor có tên.

## 63. Bài tập 15 — Constructor gọi overridable method

Superclass constructor gọi `describe()`; anonymous override dùng field được khởi tạo `String text = "ready"`.

**Đáp án:** Override có thể nhìn thấy `text == null` ở thời điểm superclass constructor gọi nó, vì subclass field initializer chưa chạy. Tránh dispatch tới overridable methods trong constructors nếu logic phụ thuộc subclass state.

## 64. Bài tập 16 — `super.method()` hợp lệ?

Anonymous subclass override `render` và bên trong gọi `super.render()`.

**Đáp án:** Hợp lệ nếu inherited method accessible và không có ràng buộc khác. Đây là **gọi method superclass**, không phải constructor invocation `super(...)`.

## 65. Bài tập 17 — `super(3)` trong instance initializer?

```java
new Base(3) {
    {
        // super(3); // Không hợp lệ.
    }
};
```

**Đáp án:** Không được dùng explicit constructor invocation ở instance initializer block. Constructor superclass được chọn nhờ `new Base(3)`.

## 66. Bài tập 18 — Inner superclass cần gì thêm?

`Outer.Inner` là non-static member inner class với constructor `Inner(int id)`, caller đang có `Outer owner`.

**Đáp án:** Có thể dùng `owner.new Inner(7) { ... }` trong ngữ cảnh truy cập hợp lệ. `owner` là enclosing instance; `7` là constructor argument.

## 67. Bài tập 19 — Generics

`Holder<T>` có constructor `Holder(T value)`. Tạo `Holder<String>` bằng anonymous subclass.

**Đáp án:** `new Holder<String>("Java") { ... }` là cách viết rõ ràng. Trên Java 17, `new Holder<>("Java") { ... }` có thể hợp lệ theo quy tắc diamond/inference phù hợp.

## 68. Bài tập 20 — Varargs

Superclass có constructor `Base(String... values)`. `new Base("A","B") { }` truyền mấy phần tử?

**Đáp án:** Một varargs array chứa hai String elements cho constructor trong lời gọi dạng này.

## 69. Bài tập 21 — Constructor argument và reassignment

```java
String label = "A";
Base value = new Base(label) {
};
label = "B";
```

**Đáp án:** Có thể hợp lệ. `label` chỉ được dùng làm argument, không bị anonymous body capture. Constructor nhận value/reference tương ứng với `"A"` tại thời điểm tạo.

## 70. Bài tập 22 — Capture làm mất effectively final

```java
String label = "A";
Base value = new Base(label) {
    @Override
    String render() {
        return label;
    }
};
label = "B";
```

**Đáp án:** Không hợp lệ nếu override capture `label` vì nó bị gán lại. Argument evaluation và local-variable capture là hai cơ chế khác.

## 71. Bài tập 23 — Có tạo hai objects, Base và anonymous wrapper, không?

**Đáp án:** Không. Một `new Base(3) { ... }` tạo một **anonymous subclass object** với superclass portion được khởi tạo; không phải hai Java objects độc lập theo mô hình “base bên trong wrapper”.

## 72. Bài tập 24 — Runtime type và static type

`Base value = new Base(7) { void extra() { } };`. Có gọi `value.extra()` không?

**Đáp án:** Không, vì static type `Base` không khai báo `extra`. Nếu anonymous body override methods thuộc Base thì gọi được thông qua Base reference. Trường hợp local `var` có type inference riêng cần phân tích riêng, không làm thay đổi kết luận cho biến khai báo `Base`.

## 73. Bài tập 25 — Anonymous class vs named subclass

Một implementation có 12 fields, validation phức tạp, cần dùng nhiều nơi và có unit tests riêng.

**Đáp án:** Named subclass với constructor tường minh thường phù hợp hơn. Anonymous class không có source constructor name và dễ làm phân tán initialization logic.

## 74. Bài tập 26 — Mutable object argument

`Base` nhận mutable `List<String>` rồi giữ trực tiếp reference; anonymous subclass được tạo bằng `new Base(source) { }`. Caller mutate source.

**Đáp án:** Base có thể quan sát thay đổi nếu giữ alias. Constructor argument không tự defensive-copy, và keyword anonymous không bổ sung immutability.

## 75. Bài tập 27 — Sealed hierarchy

Superclass được khai báo sealed và anonymous subclass không thuộc permitted direct subclasses.

**Đáp án:** Không thể tùy ý tạo anonymous subclass để vượt sealed restrictions. Chọn permitted named subtype/strategy theo API.

## 76. Bài tập 28 — Khác biệt lifetime callback

Một anonymous subclass của listener base được tạo, constructor nhận service reference, rồi callback được đăng ký global.

**Đáp án:** Cần xem constructor giữ reference nào, anonymous body capture enclosing state nào, và callback unregister ra sao. Construction thành công không đảm bảo lifecycle/memory safety.

## 77. Bài tập 29 — Constructor của superclass in trước hay initializer của anonymous?

**Đáp án:** Superclass constructor chạy trước anonymous subclass instance initializer. Constructor argument expressions còn được đánh giá trước cả constructor nếu không gặp exception.

## 78. Bài tập 30 — Phán đoán đúng/sai

Xét các mệnh đề:

1. Anonymous class có thể gọi constructor nhận tham số của superclass.
2. Có thể tự khai báo `Anonymous(int x)` constructor trong anonymous class body.
3. Với interface, `new Runnable("x") { ... }` có thể gọi Runnable constructor.
4. Anonymous class là subtype của superclass được ghi sau `new`.
5. `super.render()` và `super("x")` cùng là method call trong anonymous body.
6. Việc constructor superclass ném IOException phải được catch/declare.
7. Constructor argument reference luôn được deep-copy.
8. `owner.new Inner(args) { ... }` có thể cần cả enclosing instance và constructor arguments.

**Đáp án:** 1 đúng; 2 sai; 3 sai; 4 đúng; 5 sai; 6 đúng; 7 sai; 8 đúng.

## 79. Những sai lầm phổ biến khi học anonymous superclass constructors

| Nhận định sai | Thực tế | Cách sửa |
| --- | --- | --- |
| “Anonymous class không có constructor nên không nhận arguments được” | Nó chuyển arguments tới constructor superclass ở biểu thức `new` | `new Base(args) { ... }` |
| “Có thể viết constructor mang tên Base trong anonymous body” | Anonymous class không có source constructor name | Dùng superclass argument list hoặc named subclass |
| “`new Interface(args) { ... }` giống `new Base(args) { ... }`” | Interface không có constructors | Dùng `new Interface() { ... }` và capture/field/implementation khác |
| “Có thể override constructor” | Constructors không override như instance methods | Override methods, gọi ctor qua `new` |
| “`super(args)` nằm trong instance initializer cũng được” | Explicit constructor invocation có vị trí riêng | Đặt arguments tại `new Base(args)` |
| “Chỉ cần constructor nhận đúng kiểu là đủ” | Còn access, abstract methods, subclassability, throws | Kiểm tra toàn bộ compile constraints |
| “Constructor private tự accessible vì anonymous subclass” | Anonymous class không vượt access control | Thiết kế access/factory đúng |
| “Final class có thể tạo subclass vô danh nếu body rỗng” | Body `{ }` vẫn là subclass declaration | Dùng `new FinalBase(args)` không body |
| “Constructor được chọn theo runtime class của argument” | Overload resolution dựa trên compile-time types | Xác định static types/casts |
| “`null` luôn chọn một ctor rõ ràng” | Có thể ambiguous giữa unrelated reference types | Cast/factory |
| “Constructor args chạy theo thứ tự tùy JVM” | Java có evaluation order trái sang phải | Đọc theo Java evaluation rules |
| “Anonymous instance initializer chạy trước Base ctor” | Superclass initialized trước subclass initializer | Dự đoán đúng thứ tự |
| “Superclass ctor gọi override thì subclass fields đã sẵn sàng” | Có thể còn default values | Không gọi overridable methods trong ctor |
| “Checked exception do ctor sẽ biến mất nếu override method” | Constructor exception checking độc lập | Catch/declare |
| “Đối số List tự copy” | Reference alias được truyền | Defensive-copy khi contract yêu cầu |
| “Biến local dùng làm constructor arg phải effectively final” | Chỉ dùng trong arg không tự bị capture | Phân biệt expression vs body capture |
| “Anonymous subclass của inner class không cần owner” | Inner superclass thường cần enclosing instance | `owner.new Inner(args) { ... }` |
| “Anonymous-only method luôn gọi được qua Base ref” | Static type Base giới hạn method lookup | Interface/named class |
| “Tên class `$1` là contract” | Generated binary naming không nên được coi cố định | Dùng API/types |
| “Anonymous class luôn tốt hơn named subclass” | Complexity/reuse/testability có thể cao hơn | Named subclass hoặc composition |

## 80. Checklist trước khi viết `new Base(args) { ... }`

- [ ] `Base` là class đúng loại, không phải interface được truyền constructor args?
- [ ] `Base` không final và không bị sealed restrictions ngăn anonymous subclass?
- [ ] Có matching accessible superclass constructor với argument list?
- [ ] Static types của arguments đã được kiểm tra overload resolution?
- [ ] Không có overload ambiguity, đặc biệt với `null` và varargs?
- [ ] Constructors của Base có giữ invariants và xử lý invalid arguments?
- [ ] Constructor có ném checked exceptions cần catch/declare?
- [ ] Arguments được đánh giá không có side effects bất ngờ?
- [ ] Anonymous body implement đủ abstract methods?
- [ ] Dùng `@Override` để bắt lỗi chữ ký method?
- [ ] Không cố tự khai báo constructor hoặc viết `super(args)` trong initializer?
- [ ] Nếu cần subclass-specific state, instance initializer đủ rõ hay nên tạo named subclass?
- [ ] Constructor superclass có gọi overridable method trước khi subclass state sẵn sàng?
- [ ] Nếu superclass là inner class, có enclosing owner đúng?
- [ ] Nếu dùng generics/diamond, compiler Java 17 suy luận type đúng?
- [ ] Local variables được **capture trong body** có final/effectively final?
- [ ] Mutable arguments có cần copy/ownership rõ không?
- [ ] Reference static type có cung cấp methods caller cần?
- [ ] Có dependency/resource nào bị giữ quá lâu sau đăng ký callback?
- [ ] Tên file, public class và lệnh `javac --release 17` đã nhất quán?
- [ ] Ví dụ **compile-negative** đã được tách khỏi các file runnable?
- [ ] Stdout có tránh phụ thuộc compiler-generated class names và thread scheduling?

## 81. Ghi nhớ trọng tâm

1. Khi **anonymous class extends một class**, cú pháp `new SuperClass(arguments) { ... }` truyền đối số tới **constructor của superclass**, không phải constructor tự khai báo trong anonymous body.
2. Anonymous class không có tên source và không được viết constructor theo tên của superclass; trình biên dịch xử lý constructor forwarding.
3. Constructor selection chịu **overload resolution, accessibility, abstract/final/sealed restrictions và checked exceptions** như các lời gọi constructor hợp lệ khác.
4. **Đánh giá argument expressions** diễn ra trước lời gọi constructor; sau phần khởi tạo superclass mới tới subclass instance initialization.
5. Không gọi overridable methods từ superclass constructor khi subclass fields chưa sẵn sàng.
6. `super.someMethod()` trong anonymous override khác với `super(arguments)` constructor invocation.
7. `new Runnable() { ... }` triển khai interface; `Runnable` không có constructor nhận args. Dùng effectively-final captures hoặc named implementation nếu cần cấu hình.
8. Nếu superclass là **non-static member inner class**, cú pháp có thể cần `owner.new Inner(arguments) { ... }`: owner reference và ctor arguments có vai trò riêng.
9. Constructor arguments **không tự deep-copy** các objects mutable; cần quy định ownership riêng.
10. Nếu implementation đủ lớn để cần constructor riêng, invariants phức tạp hoặc reuse, **named subclass** thường là lựa chọn dễ duy trì hơn.

**Câu hỏi kiểm tra ngắn:** Với `new Base(10) { @Override void run() { ... } }`, số `10` được dùng ở đâu? — Nó được đánh giá tại call site và chuyển tới **constructor `Base` được compiler chọn**. Anonymous class body quyết định phần subclass implementation, không khai báo lại constructor ấy.

## Nguồn quy tắc Java

- **JLS Java SE 17 §15.9 — Class Instance Creation Expressions:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9
- **JLS Java SE 17 §15.9.5 — Anonymous Class Declarations:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5
- **JLS Java SE 17 §8.8 — Constructor Declarations:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8
- **JLS Java SE 17 §8.8.7.1 — Explicit Constructor Invocations:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1
- **JLS Java SE 17 §12.5 — Creation of New Class Instances:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5
