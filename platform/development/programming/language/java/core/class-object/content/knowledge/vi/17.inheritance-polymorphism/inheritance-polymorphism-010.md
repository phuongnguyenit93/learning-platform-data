# Nhận diện lớp `abstract` và giới hạn khi tạo đối tượng trực tiếp trong Java

## 1. Kết luận cốt lõi: lớp abstract không được tạo instance trực tiếp

Trong Java, **lớp trừu tượng (*abstract class*)** là một class được khai báo với từ khóa `abstract`. Nó có thể mô tả **hợp đồng và hành vi chung** cho các class con, đồng thời có thể để lại những thao tác mà các lớp con phải hoàn thiện.

Ví dụ:

```java
abstract class Animal {
    abstract String sound();
}
```

Điều **không hợp lệ**:

```java
// Animal animal = new Animal();
// Sai khi bỏ comment: Animal là abstract class,
// không thể tạo instance trực tiếp bằng new Animal().
```

Điều **hợp lệ**:

```java
class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

Animal animal = new Dog(); // Mảnh code đặt trong method hợp lệ.
```

Biến `animal` có **kiểu tĩnh `Animal`**, nhưng object được tạo thực sự có runtime class `Dog`, một class **cụ thể (*concrete*)**. Java cho phép điều này nhờ **upcasting và đa hình**.

**Phân biệt:**

- **Khai báo biến tham chiếu kiểu abstract class:** được.
- **Dùng abstract class làm tham số/kiểu trả về/kiểu phần tử mảng:** được.
- **Tạo object trực tiếp bằng `new AbstractClass()`:** không được.
- **Tạo object bằng `new ConcreteSubclass()` rồi gán vào abstract-typed reference:** được.
- **Dùng anonymous subclass có implementation đầy đủ:** có thể được, dù cú pháp bắt đầu bằng `new AbstractClass() { ... }`; đó **không phải** tạo trực tiếp một instance của abstract class.

Bài học tập trung vào cách **nhận diện abstract class và giới hạn khởi tạo đối tượng**, không đánh đồng abstract class với interface, utility class hay class chỉ có constructor private.

## 2. Cú pháp khai báo `abstract class`

Khuôn mẫu:

```java
abstract class BaseName {
    // Có thể có instance fields và static fields.
    // Có thể có constructors.
    // Có thể có abstract và concrete methods.
}
```

Nếu khai báo class public ở top level:

```java
public abstract class Shape {
    public abstract double area();
}
```

thì tệp source thông thường phải tên **`Shape.java`**. Nếu chỉ học trong một file demo có một public main class, có thể khai báo abstract class khác là **package-private**, rồi tạo các concrete subclasses trong cùng compilation unit.

Từ khóa `abstract` là **modifier của class**, không phải là kiểu dữ liệu độc lập và không cần có constructor đặc biệt để kích hoạt.

### Dấu hiệu nhận diện từ source

1. Trong khai báo có `abstract class X` → X là abstract class.
2. Nếu class chứa một abstract method được khai báo hợp lệ, bản thân class **phải** được khai báo abstract.
3. Class có thể abstract **dù không khai báo abstract method nào**.
4. Một class không ghi `abstract` nhưng chưa triển khai đầy đủ các abstract instance methods bắt buộc của superclass/interface sẽ **không biên dịch được**, chứ không tự động trở thành abstract.
5. `interface X` là interface type, **không phải** một `abstract class`, dù một số quy tắc reflection/modifier của interface có khía cạnh abstract.

**Không suy từ tên:** Một class tên `AbstractService` nhưng không có modifier `abstract` vẫn có thể là concrete class; ngược lại, tên `Device` có thể hoàn toàn là abstract nếu declaration nói vậy.

## 3. Ví dụ Java 17+ hoàn chỉnh: abstract class, concrete subclass và đa hình

Tạo **`AbstractBasicsDemo.java`**:

```java
abstract class Animal {
    private final String name;

    Animal(String name) {
        this.name = name;
        System.out.println("Animal constructor");
    }

    abstract String sound();

    String description() {
        return name + ":" + sound();
    }
}

final class Dog extends Animal {
    Dog(String name) {
        super(name);
        System.out.println("Dog constructor");
    }

    @Override
    String sound() {
        return "woof";
    }
}

public class AbstractBasicsDemo {
    public static void main(String[] args) {
        Animal animal = new Dog("Milo");

        System.out.println(animal.description());
        System.out.println(animal instanceof Animal);
        System.out.println(animal.getClass().getSimpleName());

        // Animal invalid = new Animal("Milo");
        // Không hợp lệ: không được instantiate Animal trực tiếp.
    }
}
```

Biên dịch và chạy:

```bash
javac AbstractBasicsDemo.java
java AbstractBasicsDemo
```

**Standard output:**

```text
Animal constructor
Dog constructor
Milo:woof
true
Dog
```

Giải thích:

1. `Animal` là abstract vì có modifier `abstract` và method `sound()` chưa có body.
2. `Dog` là concrete subclass, cung cấp implementation `sound()` bằng `@Override`.
3. `new Dog("Milo")` được phép; constructor chain chạy `Animal(String)` rồi `Dog(String)`.
4. `Animal animal = ...` là upcast reference, không tạo một Animal instance riêng.
5. `animal.description()` là concrete method được kế thừa từ Animal. Khi bên trong method gọi `sound()`, Java dispatch đến `Dog.sound()`.
6. `animal.getClass()` trả runtime class Dog, không phải Animal.
7. Nếu bỏ comment dòng `new Animal("Milo")`, compiler báo lỗi vì Animal là abstract.

**Ý chính:** abstract class vẫn có **constructor và instance state**, nhưng chỉ được khởi tạo như một phần của việc tạo một concrete descendant object.

## 4. Vì sao Java cấm `new AbstractClass()`?

Giả sử:

```java
abstract class Shape {
    abstract double area();
}
```

Nếu Java cho tạo một object `Shape` trực tiếp, implementation nào sẽ được thực thi khi gọi `area()`? Class Shape chưa có implementation cho method đó.

Java giải quyết bằng ràng buộc **compile time**: không cho trực tiếp tạo instance của abstract class, **kể cả khi object ấy chưa định gọi abstract method**.

Ví dụ:

```java
// Shape one = new Shape(); // Lỗi compile-time.
```

Thông báo của `javac` có thể tương tự “Shape is abstract; cannot be instantiated”; wording cụ thể tùy compiler/phiên bản. Đó không phải exception runtime từ constructor Shape; code **không vượt qua compilation**.

Một trường hợp quan trọng: **Ngay cả abstract class không có abstract method nào cũng không được new trực tiếp**. Lý do lúc ấy không nhất thiết là “thiếu implementation”, mà vì modifier `abstract` bản thân nó quy định class không thể được instantiated trực tiếp.

## 5. Lớp abstract có thể không có abstract method

Tạo **`AbstractWithoutAbstractMethodDemo.java`**:

```java
abstract class Ticket {
    private final String code;

    Ticket(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}

final class VipTicket extends Ticket {
    VipTicket(String code) {
        super(code);
    }
}

public class AbstractWithoutAbstractMethodDemo {
    public static void main(String[] args) {
        Ticket ticket = new VipTicket("VIP-7");

        System.out.println(ticket.code());
        System.out.println(ticket instanceof Ticket);

        // Ticket invalid = new Ticket("X");
        // Không hợp lệ dù Ticket không khai báo abstract method.
    }
}
```

```bash
javac AbstractWithoutAbstractMethodDemo.java
java AbstractWithoutAbstractMethodDemo
```

```text
VIP-7
true
```

Ở đây:

- `Ticket` được đánh dấu abstract để thể hiện **không muốn client tạo loại Ticket tổng quát**.
- `Ticket` chỉ có concrete method `code()`, hoàn toàn hợp lệ.
- `VipTicket` là concrete subclass; không có abstract method còn nợ nên không phải override gì.
- `new VipTicket(...)` hoạt động, còn `new Ticket(...)` vẫn bị cấm.

**Quy tắc nhận diện chính xác:** Abstract class **có thể** khai báo abstract methods, **không bắt buộc** phải có một abstract method.

## 6. Abstract method là gì?

Một **abstract method** khai báo chữ ký method nhưng **không có method body** trong class khai báo. Dạng quen thuộc:

```java
abstract class Calculator {
    abstract int compute(int a, int b);
}
```

Ký tự `;` kết thúc declaration; không có `{ ... }`.

Sai:

```java
// abstract class Calculator {
//     abstract int compute(int a, int b) {
//         return a + b;
//     }
// }
```

Không được vừa khai báo `abstract` vừa viết body cho **cùng method**. Nếu cần implementation chung, bỏ `abstract` ở method và cung cấp body.

### Một abstract class được phép có cả abstract và concrete methods

```java
abstract class Document {
    abstract String content();

    String preview() {
        return "[" + content() + "]";
    }
}
```

`content()` là abstract, sẽ được một concrete subclass triển khai. `preview()` là concrete và có thể gọi `content()` bằng dynamic dispatch trên runtime receiver.

**Vì sao hữu ích:** class cha định nghĩa **hợp đồng và workflow chung**, subclass chỉ điền phần còn thiếu thay vì lặp cùng logic ở mọi loại tài liệu.

## 7. Concrete subclass phải hoàn thiện abstract methods còn thiếu

Tạo **`ConcreteImplementationDemo.java`**:

```java
abstract class Shape {
    abstract int area();

    String summary() {
        return "area=" + area();
    }
}

final class Rectangle extends Shape {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    @Override
    int area() {
        return width * height;
    }
}

public class ConcreteImplementationDemo {
    public static void main(String[] args) {
        Shape shape = new Rectangle(3, 4);

        System.out.println(shape.summary());
        System.out.println(shape.area());
    }
}
```

```bash
javac ConcreteImplementationDemo.java
java ConcreteImplementationDemo
```

```text
area=12
12
```

Giải thích:

- `Shape.area()` không có implementation.
- `Rectangle.area()` cung cấp implementation phù hợp và có thể dùng `@Override`.
- `Shape.summary()` là concrete method ở lớp cha; nó gọi `area()` trên object thực tế.
- Biến `shape` có kiểu Shape, nhưng method `area()` dispatch tới Rectangle khi runtime receiver là Rectangle.

Nếu bạn bỏ `Rectangle.area()` mà vẫn giữ `Rectangle` concrete, compiler sẽ từ chối vì Rectangle chưa triển khai abstract method bắt buộc.

### Không cần tự viết override ở mọi tầng

Nếu một superclass trung gian đã triển khai abstract method và class con kế thừa implementation ấy, concrete class con **không bắt buộc viết override lại**. Điều kiện là không còn abstract methods chưa được triển khai và mọi method-contract khác đều hợp lệ.

## 8. Abstract subclass có thể tiếp tục trì hoãn implementation

Một class con cũng được khai báo abstract để **chưa cần hoàn thiện tất cả abstract methods ngay tại tầng đó**.

Tạo **`AbstractHierarchyDemo.java`**:

```java
abstract class Device {
    abstract String kind();

    String description() {
        return "device:" + kind();
    }
}

abstract class MobileDevice extends Device {
    abstract int version();
}

final class Phone extends MobileDevice {
    @Override
    String kind() {
        return "phone";
    }

    @Override
    int version() {
        return 17;
    }
}

public class AbstractHierarchyDemo {
    public static void main(String[] args) {
        MobileDevice device = new Phone();

        System.out.println(device.description());
        System.out.println(device.version());
    }
}
```

```bash
javac AbstractHierarchyDemo.java
java AbstractHierarchyDemo
```

```text
device:phone
17
```

- `Device` khai báo abstract `kind()`.
- `MobileDevice` vẫn abstract nên có thể để `kind()` chưa được triển khai, đồng thời thêm abstract `version()`.
- `Phone` concrete, nên phải đáp ứng cả hai methods còn thiếu.
- Caller vẫn có thể sử dụng `MobileDevice` làm **kiểu tham chiếu**, nhưng object được tạo là Phone.

**Sai lầm thường gặp:** “Class con bắt buộc override ngay mọi abstract method của cha”. Đúng hơn: **class con concrete** phải có implementation phù hợp; **class con abstract** có thể hoãn việc ấy.

## 9. `@Override` không thay thế từ khóa `abstract`

`@Override` là annotation giúp compiler xác nhận một method thật sự override hoặc triển khai method tương thích từ superclass/interface.

```java
abstract class Base {
    abstract String name();
}

class Derived extends Base {
    @Override
    String name() {
        return "derived";
    }
}
```

Nếu gõ nhầm `names()` thành tên khác, `@Override` giúp phát hiện lỗi sớm. Không có `@Override` vẫn có thể override hợp lệ, nhưng nên dùng khi thích hợp.

Điều quan trọng:

- `abstract` trên method: **chưa có body**, subclass phải cung cấp implementation theo quy tắc.
- `@Override` trên concrete method: **đang triển khai/ghi đè** hợp đồng tương ứng.
- `@Override` không tự làm class trở thành abstract.
- Không thể làm một abstract method trở thành concrete chỉ bằng cách thêm annotation mà vẫn không viết method body.

### Quyền truy cập khi override

Một subclass không được **thu hẹp access** của inherited method trong một override hợp lệ. Ví dụ method superclass là `protected` thì overriding method không thể là `private`. Method từ public interface thường phải được triển khai bằng **public instance method** phù hợp.

Hãy kiểm signature, return type, checked exceptions và access theo quy tắc override của Java; không chỉ kiểm tên method.

## 10. Lớp abstract vẫn có constructor

“Không tạo được instance trực tiếp” **không có nghĩa** “abstract class không có constructor”. Constructor của abstract class được thực hiện trong **chuỗi khởi tạo một concrete subclass object**.

Tạo **`AbstractConstructorDemo.java`**:

```java
abstract class Account {
    private final String id;

    protected Account(String id) {
        this.id = id;
        System.out.println("Account constructor: " + id);
    }

    final String id() {
        return id;
    }

    abstract String type();
}

final class SavingsAccount extends Account {
    SavingsAccount(String id) {
        super(id);
        System.out.println("SavingsAccount constructor");
    }

    @Override
    String type() {
        return "savings";
    }
}

public class AbstractConstructorDemo {
    public static void main(String[] args) {
        Account account = new SavingsAccount("A-1");

        System.out.println(account.id());
        System.out.println(account.type());
    }
}
```

```bash
javac AbstractConstructorDemo.java
java AbstractConstructorDemo
```

```text
Account constructor: A-1
SavingsAccount constructor
A-1
savings
```

Constructor `Account(String)` chạy **trước** phần thân constructor `SavingsAccount(String)`, nhưng không hề có biểu thức `new Account("A-1")` hợp lệ để tạo Account trực tiếp.

**Giải thích:** Constructor khai báo trong abstract class là một phần của việc xây dựng instance của subclass. Nó có thể kiểm input, khởi tạo instance fields, thực hiện common initialization, nhưng không có nghĩa Abstract class trở thành concrete.

### Không có constructor không tham số tự động nếu đã khai báo constructor khác

Nếu base class chỉ khai báo `Account(String)`, constructor ở subclass phải gọi `super(id)` hoặc chuyển tiếp tới constructor hợp lệ. Viết constructor subclass không có invocation đầu tiên trong Java 17 sẽ dẫn đến **implicit `super()`**; nếu superclass không có no-arg constructor accessible, compilation fail.

## 11. Constructor của abstract class có thể nhận arguments và kiểm invariant

Một superclass abstract thường giữ dữ liệu chung:

```java
abstract class Employee {
    private final String name;

    protected Employee(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        this.name = name;
    }

    public final String name() {
        return name;
    }

    public abstract int salary();
}
```

Đây là một **class declaration hợp lệ**, không có `main`. Nó minh họa:

- Constructor `protected`: subclass thích hợp có thể gọi `super(name)`.
- `private final` field: object giữ tên sau validation.
- `final` concrete method `name()`: subclass không được override.
- `abstract` method `salary()`: một concrete descendant phải có implementation theo quy tắc.

**Nơi đặt contract:** Nếu mọi Employee bắt buộc có tên hợp lệ, validation ở superclass constructor giúp tránh việc các subclasses quên kiểm tra. Nhưng chỉ khi constructor superclass có thể được gọi hợp lệ và không gây side effects thiếu kiểm soát.

## 12. Có thể gọi abstract method từ concrete method của lớp cha

Lớp abstract có thể định nghĩa một phần thuật toán hoàn chỉnh, rồi dùng abstract method để lấy “bước triển khai” từ subclass.

Tạo **`TemplateMethodDemo.java`**:

```java
abstract class ReportGenerator {
    final void generate() {
        System.out.println("prepare");
        String body = createBody();
        System.out.println("report=" + body);
        System.out.println("finish");
    }

    protected abstract String createBody();
}

final class SalesReport extends ReportGenerator {
    @Override
    protected String createBody() {
        return "sales:100";
    }
}

public class TemplateMethodDemo {
    public static void main(String[] args) {
        ReportGenerator generator = new SalesReport();
        generator.generate();
    }
}
```

```bash
javac TemplateMethodDemo.java
java TemplateMethodDemo
```

```text
prepare
report=sales:100
finish
```

Đây là ý tưởng **Template Method**:

- `ReportGenerator.generate()` là concrete `final` method giữ quy trình.
- `createBody()` là abstract hook.
- `SalesReport` triển khai hook theo nhu cầu.
- Caller thấy một API `generate` ổn định, nhưng runtime behavior của `createBody` phụ thuộc concrete subclass.

**Phân biệt:** Template Method dùng inheritance/overriding. Nếu muốn thay chiến lược qua object được truyền vào, có thể dùng composition/delegation và Strategy; không phải mọi tình huống cần abstract class.

## 13. Cảnh báo: gọi overridable abstract method từ constructor lớp cha

Một abstract class có thể gọi abstract method trong một concrete method. Nhưng **gọi abstract/overridable method trong superclass constructor** rất dễ làm lộ trạng thái subclass chưa được khởi tạo đầy đủ.

Tạo **`AbstractConstructorDispatchDemo.java`**:

```java
abstract class Parent {
    Parent() {
        printState();
    }

    abstract void printState();
}

final class Child extends Parent {
    private int number = 42;

    @Override
    void printState() {
        System.out.println("number=" + number);
    }
}

public class AbstractConstructorDispatchDemo {
    public static void main(String[] args) {
        Child child = new Child();
        child.printState();
    }
}
```

```bash
javac AbstractConstructorDispatchDemo.java
java AbstractConstructorDispatchDemo
```

```text
number=0
number=42
```

**Tại sao lần đầu là 0?**

1. Object được cấp phát với default value `0` cho `number`.
2. Constructor chain vào `Parent()` trước khi Child instance field initializer chạy.
3. Parent gọi `printState()`, dynamic dispatch tới `Child.printState()`.
4. Child initializer `number=42` chưa chạy, nên in `number=0`.
5. Sau khi Parent constructor trả về, Child initializer chạy và gán 42.
6. Lời gọi sau khi tạo xong object in `number=42`.

**Khuyến nghị:** Tránh gọi overridable methods từ constructor, nhất là abstract hooks yêu cầu subclass state. Hoàn tất object construction rồi mới thực hiện behavior có thể dispatch ra subclass. Không để `this` escape sớm qua callback, registry hoặc thread.

## 14. Các abstract modifiers không thể kết hợp tùy tiện

Một số tổ hợp **không hợp lệ** do mâu thuẫn giữa “phải được subclass hoàn thiện” và “không được override/kế thừa theo cách ấy”.

| Khai báo | Hợp lệ? | Vì sao |
| --- | --- | --- |
| `abstract class Base { }` | Có | Lớp trừu tượng không bắt buộc có abstract methods |
| `final class Base { }` | Có | Lớp cụ thể không cho subclass |
| `abstract final class Base { }` | **Không** | Abstract class cần cho phép subclass cung cấp implementation; final cấm subclass |
| `abstract void work();` trong abstract class | Có | Khai báo abstract instance method |
| `private abstract void work();` | **Không** | Private method không thể được override theo inheritance contract cần thiết |
| `static abstract void work();` | **Không** | Static methods không được override như abstract instance methods |
| `final abstract void work();` | **Không** | Final method không thể override |
| `synchronized abstract void work();` | **Không** | Abstract method không có body để dùng synchronized method implementation theo kiểu ấy |
| `native abstract void work();` | **Không** | Tổ hợp method modifiers bị cấm |
| `abstract void work() { }` | **Không** | Abstract method không có body |
| `abstract class Base { static int x() { return 1; } }` | Có | Abstract class vẫn có concrete static methods |
| `abstract class Base { final int x() { return 1; } }` | Có | Abstract class vẫn có concrete final methods |

Bảng dùng **mảnh khai báo độc lập**; những dòng đánh dấu không hợp lệ không phải code để copy vào ví dụ runnable.

**Không nên hiểu “lớp abstract” nghĩa là “mọi method trong lớp đều abstract”.** Modifier `abstract` trên class quyết định class không thể tạo instance trực tiếp; từng method có thể concrete, abstract, static, final theo điều kiện riêng.

## 15. Static methods và fields trong abstract class vẫn dùng được

Không được `new AbstractClass()` **không cấm gọi static methods** được truy cập hợp lệ từ class ấy.

Tạo **`AbstractStaticDemo.java`**:

```java
abstract class MathOperation {
    static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    abstract int apply(int a, int b);
}

final class Addition extends MathOperation {
    @Override
    int apply(int a, int b) {
        return MathOperation.add(a, b);
    }
}

public class AbstractStaticDemo {
    public static void main(String[] args) {
        System.out.println(MathOperation.add(2, 3));

        MathOperation operation = new Addition();
        System.out.println(operation.apply(4, 5));
    }
}
```

```bash
javac AbstractStaticDemo.java
java AbstractStaticDemo
```

```text
5
9
```

- `MathOperation.add` static: gọi trực tiếp qua tên class abstract, không cần object.
- `MathOperation.apply` abstract: cần concrete implementation khi gọi trên instance.
- `Addition` concrete, override `apply` rồi tái sử dụng static helper.
- Không có một `MathOperation` object được tạo trực tiếp.

**Static method không phải instance abstract method.** Không viết `static abstract` với ý định subclass sẽ override động; nếu cần runtime polymorphism, dùng instance abstract method.

## 16. Abstract class có thể có `private` helper, nhưng không có `private abstract` method

Một abstract class được phép có **private concrete method** để dùng nội bộ:

```java
abstract class Pipeline {
    final String process(String input) {
        return normalize(input) + ":" + transform(input);
    }

    private String normalize(String input) {
        return input.trim();
    }

    protected abstract String transform(String input);
}
```

`normalize` là private concrete instance method, có body hợp lệ. `transform` là protected abstract instance method để subclass triển khai.

**Vì sao `private abstract` vô nghĩa theo ngôn ngữ?** Abstract instance method đặt ra nghĩa vụ được override/implement; private method không được kế thừa/override theo cơ chế cần thiết. Compiler không cho tổ hợp đó.

**Lưu ý:** Đừng dùng `private` helper trong superclass rồi mong subclass “override” nó; method cùng tên/chữ ký ở subclass không phải override private superclass method.

## 17. Abstract class khác interface ở đâu?

Cả hai đều cho phép khai báo contract và dùng kiểu tham chiếu để đạt đa hình, nhưng khác nhau ở cấu trúc và quyền khai báo.

| Tiêu chí | Abstract class | Interface |
| --- | --- | --- |
| Cú pháp | `abstract class Base` | `interface Contract` |
| Superclass | Tối đa một class trực tiếp, mặc định Object nếu là ordinary class | Không có class superclass chain như class |
| Nhiều supertypes trực tiếp | Chỉ một superclass class; có thể implements nhiều interfaces | Có thể extends nhiều interfaces |
| Instance fields | Có, kể cả mutable state | Interface fields là `public static final` |
| Constructors | Có, gọi qua subclass construction | Không có instance constructors |
| Abstract instance methods | Có thể khai báo | Interface thường khai báo abstract methods (có default/static/private methods theo rules) |
| Concrete instance methods | Có | Có `default` methods với quy tắc riêng |
| Static methods | Có | Có, static interface methods không kế thừa theo cách class static members |
| Instantiation trực tiếp | Cấm khi abstract | Không thể `new Interface()` trực tiếp |
| Anonymous implementation | Có thể `new AbstractBase() { ... }` nếu hợp lệ | Có thể `new Interface() { ... }` |
| Khi nào thường dùng? | Shared state/implementation và quan hệ is-a | Hợp đồng capability giữa nhiều unrelated types |

**Cảnh báo:** Đừng nói “interface là abstract class không có fields”. Interface có quy tắc ngôn ngữ riêng, và Java hiện đại cho phép default/static/private interface methods theo các điều kiện cụ thể.

Cũng không thể vì muốn kế thừa hai abstract classes mà viết `extends A, B`. Java chỉ cho một class superclass trực tiếp; có thể dùng nhiều interfaces hoặc composition.

## 18. Ví dụ: abstract class triển khai interface nhưng để phần việc cho subclass

Tạo **`AbstractImplementsInterfaceDemo.java`**:

```java
interface Printable {
    void print();
}

abstract class BaseReport implements Printable {
    private final String title;

    BaseReport(String title) {
        this.title = title;
    }

    String title() {
        return title;
    }

    // BaseReport chưa triển khai print(), nhưng vẫn hợp lệ
    // vì bản thân class đã được khai báo abstract.
}

final class Report extends BaseReport {
    Report(String title) {
        super(title);
    }

    @Override
    public void print() {
        System.out.println("Report:" + title());
    }
}

public class AbstractImplementsInterfaceDemo {
    public static void main(String[] args) {
        Printable printable = new Report("Q3");
        printable.print();
    }
}
```

```bash
javac AbstractImplementsInterfaceDemo.java
java AbstractImplementsInterfaceDemo
```

```text
Report:Q3
```

Giải thích:

- `BaseReport implements Printable` nhưng vẫn abstract nên **được phép chưa triển khai `print()`**.
- `Report` concrete nên phải cung cấp `public void print()`; method triển khai interface method public không được giảm quyền truy cập.
- Caller dùng `Printable` interface reference để gọi implementation phù hợp.
- Object được tạo là Report, không phải một BaseReport hoặc Printable instance trực tiếp.

**Lỗi thường gặp:** Bỏ `abstract` ở BaseReport nhưng vẫn chưa implement `Printable.print()`. Lúc đó compiler báo BaseReport phải khai báo abstract hoặc implement method bắt buộc.

## 19. Anonymous subclass: cú pháp `new AbstractBase() { ... }` vẫn hợp lệ

Một điểm rất dễ gây ngộ nhận:

```java
abstract class Operation {
    abstract int apply(int a, int b);
}
```

**Không được**:

```java
// Operation x = new Operation();
```

**Nhưng có thể**:

```java
Operation sum = new Operation() {
    @Override
    int apply(int a, int b) {
        return a + b;
    }
};
```

Ở ví dụ thứ hai, biểu thức **khai báo và tạo một anonymous subclass concrete** của Operation, với implementation `apply`. Nó không trực tiếp instantiate Operation.

### Ví dụ runnable

Tệp **`AnonymousAbstractDemo.java`**:

```java
abstract class Operation {
    abstract int apply(int left, int right);
}

public class AnonymousAbstractDemo {
    public static void main(String[] args) {
        Operation sum = new Operation() {
            @Override
            int apply(int left, int right) {
                return left + right;
            }
        };

        System.out.println(sum.apply(4, 5));
        System.out.println(sum.getClass().isAnonymousClass());
        System.out.println(
                sum.getClass().getSuperclass().getSimpleName());
    }
}
```

```bash
javac AnonymousAbstractDemo.java
java AnonymousAbstractDemo
```

```text
9
true
Operation
```

- `sum` là một biến kiểu Operation.
- Runtime class của object là một **anonymous subclass** được compiler tạo.
- `isAnonymousClass()` cho biết runtime class là anonymous class.
- Superclass trực tiếp của anonymous class là Operation theo cấu trúc ở ví dụ.

**Giới hạn:** Anonymous class vẫn phải đáp ứng abstract methods, constructor/access requirements và các quy tắc kế thừa. Nó không phải “lỗ hổng” tạo abstract instance. Nếu không triển khai đủ abstract methods của class cha, compilation fail.

## 20. Abstract-typed reference, parameter và return type đều được

Lớp abstract có thể được dùng làm **kiểu** trong Java dù không có direct instances.

Ví dụ:

```java
abstract class Shape {
    abstract int area();
}

final class Square extends Shape {
    private final int side;

    Square(int side) {
        this.side = side;
    }

    @Override
    int area() {
        return side * side;
    }
}
```

Có thể dùng:

```java
Shape shape = new Square(3);
```

hoặc:

```java
static int printArea(Shape shape) {
    return shape.area();
}
```

và method trả về abstract-typed reference:

```java
static Shape unitSquare() {
    return new Square(1);
}
```

Các đoạn là **mảnh code minh họa**, giả định khai báo trong class/method hợp lệ. Tham số và return type `Shape` không yêu cầu tạo object Shape; chúng mô tả **supertype contract**.

**Quy tắc chung:** Một type abstract hoàn toàn có thể xuất hiện ở API boundary để cho phép caller cung cấp bất cứ concrete subtype phù hợp nào.

## 21. Dùng static factory trong abstract class để trả concrete object

Một abstract class có thể có static factory method tạo object của concrete subtype:

Tệp **`AbstractFactoryDemo.java`**:

```java
abstract class Message {
    private final String text;

    protected Message(String text) {
        this.text = text;
    }

    final String text() {
        return text;
    }

    abstract String render();

    static Message plain(String text) {
        return new PlainMessage(text);
    }
}

final class PlainMessage extends Message {
    PlainMessage(String text) {
        super(text);
    }

    @Override
    String render() {
        return text();
    }
}

public class AbstractFactoryDemo {
    public static void main(String[] args) {
        Message message = Message.plain("Hello");

        System.out.println(message.render());
        System.out.println(message.getClass().getSimpleName());
    }
}
```

```bash
javac AbstractFactoryDemo.java
java AbstractFactoryDemo
```

```text
Hello
PlainMessage
```

- `Message.plain` là static method được khai báo ở abstract class; gọi bằng **tên lớp**, không cần Message instance.
- Method trả một `Message` reference nhưng object được tạo là concrete `PlainMessage`.
- `Message` constructor vẫn chạy như một phần constructor chain của PlainMessage.
- Static factory có thể ẩn concrete implementation khỏi nhiều callers, dù ví dụ đặt tất cả classes trong cùng package.

**Không nhầm:** Có static factory trả `Message` không làm abstract class cho phép `new Message()`.

## 22. Mảng có component type là abstract class vẫn hợp lệ

Mảng Java là một **object riêng**, chứa các slot tham chiếu. Bạn có thể tạo mảng với component type abstract class mà **không tạo các phần tử abstract**.

Tệp **`AbstractArrayDemo.java`**:

```java
abstract class Shape {
    abstract int area();
}

final class Rectangle extends Shape {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    @Override
    int area() {
        return width * height;
    }
}

public class AbstractArrayDemo {
    public static void main(String[] args) {
        Shape[] shapes = new Shape[2];

        System.out.println(shapes[0] == null);

        shapes[0] = new Rectangle(3, 4);
        shapes[1] = new Rectangle(5, 2);

        for (Shape shape : shapes) {
            System.out.println(shape.area());
        }
    }
}
```

```bash
javac AbstractArrayDemo.java
java AbstractArrayDemo
```

```text
true
12
10
```

Vì sao `new Shape[2]` được phép trong khi `new Shape()` bị cấm?

- `new Shape[2]` tạo **array object**, không tạo Shape instance nào.
- Hai slots ban đầu đều null.
- Sau đó các slots được gán references tới **Rectangle objects**.
- Mỗi `shape.area()` trong enhanced for loop gọi implementation của runtime concrete subtype.

**Không được** suy từ cú pháp `new Shape[2]` rằng Java đã tạo hai abstract Shape objects.

## 23. `null` có thể gán cho biến kiểu abstract class

Một biến có type là abstract class vẫn là **biến kiểu tham chiếu** và có thể chứa `null`:

```java
Shape shape = null;
```

Điều đó hợp lệ bất kể Shape abstract hay concrete.

Nhưng:

```java
// shape.area(); // Ném NullPointerException khi thực thi nếu shape null.
```

Không có receiver object để gọi instance method. Đây là vấn đề **null dereference**, không phải lỗi “tạo object abstract”.

Nếu thiết kế không chấp nhận null, hãy validate bằng `Objects.requireNonNull(shape)` hoặc một hợp đồng phù hợp. Modifier `abstract` không khiến mọi reference tự non-null.

## 24. `Class` object và reflection có thể đại diện abstract class

Bạn không thể `new AbstractClass()`, nhưng vẫn có thể:

```java
Class<Shape> type = Shape.class;
```

Đó là một **Class object mô tả kiểu Shape**, không phải instance của Shape.

Java Reflection cho phép kiểm modifiers:

Tệp **`AbstractReflectionDemo.java`**:

```java
import java.lang.reflect.Modifier;

abstract class Base {
    abstract void perform();
}

final class Concrete extends Base {
    @Override
    void perform() {
    }
}

interface RunnableTask {
    void run();
}

public class AbstractReflectionDemo {
    public static void main(String[] args) {
        System.out.println(
                Modifier.isAbstract(Base.class.getModifiers()));
        System.out.println(
                Modifier.isAbstract(Concrete.class.getModifiers()));
        System.out.println(Base.class.isInterface());
        System.out.println(RunnableTask.class.isInterface());
        System.out.println(
                Modifier.isAbstract(RunnableTask.class.getModifiers()));
    }
}
```

```bash
javac AbstractReflectionDemo.java
java AbstractReflectionDemo
```

```text
true
false
false
true
true
```

**Điểm quan trọng:** `Modifier.isAbstract(...)` có thể trả true cho một **interface** vì cách modifier flags được biểu diễn theo reflection. Vì vậy muốn phân loại “abstract **class**” phải kiểm cả tính chất **không phải interface** như `!type.isInterface()` hoặc API loại type thích hợp, chứ không chỉ nhìn mỗi flag abstract.

`Class<?>`/`Class<T>` object tồn tại để mô tả type; lấy metadata không tự tạo instance của type ấy.

## 25. Reflection cũng không làm abstract class instantiate trực tiếp được

Đừng nghĩ có thể lách quy tắc bằng cách tìm `Constructor` qua reflection rồi tạo abstract object như một concrete class thông thường.

Các reflection APIs tuân theo các giới hạn về abstract class; nỗ lực tạo instance trực tiếp qua `Constructor.newInstance` có thể thất bại với `InstantiationException` theo contract khi declaring class abstract (cùng với những vấn đề access/exception khác).

Mã minh họa mang tính khái niệm:

```java
// Class<?> type = Shape.class;
// Object result = type.getDeclaredConstructor().newInstance();
// Không phải chiến lược hợp lệ để tạo Shape abstract instance.
```

Đoạn này không phải chương trình runnable; còn phụ thuộc Shape có constructor nào và quyền truy cập reflection. **Không khẳng định chính xác loại lỗi đầu tiên trong mọi hoàn cảnh** nếu constructor không tồn tại hoặc không accessible.

Nếu cần tạo một đối tượng sử dụng được, phải lựa chọn **concrete subtype**, factory, dependency injection hoặc một mechanism tạo implementation đáp ứng hợp đồng.

## 26. Abstract class khác class chỉ có constructor `private`

Một class concrete có thể **không cho code bên ngoài gọi constructor** vì constructor là private:

```java
final class Utility {
    private Utility() {
    }

    static int square(int value) {
        return value * value;
    }
}
```

`Utility` **không abstract**; rào cản `new Utility()` từ class khác đến từ **quyền truy cập constructor**, không phải modifier `abstract`.

So sánh:

| Tình huống | Vì sao `new X()` không hợp lệ từ caller? |
| --- | --- |
| `abstract class X`, có constructor accessible | X abstract: không thể instantiate trực tiếp |
| `final class X { private X() {} }` | Constructor không accessible từ caller khác |
| `class X { X(int a) {} }`, caller dùng `new X()` | Không có constructor phù hợp không tham số |
| `interface X`, caller dùng `new X()` | Interface không có direct instance construction |
| `enum X { A }`, caller dùng `new X()` | Enum constants có construction được kiểm soát bởi ngôn ngữ |
| `record X(int a) {}`, caller dùng `new X()` | Không có constructor chữ ký đó nếu chưa được khai báo phù hợp |

**Đừng gộp mọi thông báo “không thể new” thành abstract class.** Phải nhận diện đúng modifier, type category, chữ ký constructor và quyền truy cập.

## 27. Abstract class và quan hệ kế thừa đơn của Java

Một concrete class có thể extends **một** abstract class; một abstract class khác cũng chỉ có tối đa một direct class superclass.

Ví dụ:

```java
abstract class Base {
    abstract void work();
}

abstract class Intermediate extends Base {
}

final class Concrete extends Intermediate {
    @Override
    void work() {
        System.out.println("done");
    }
}
```

Chuỗi:

```text
Object
  |
  Base (abstract)
  |
  Intermediate (abstract)
  |
  Concrete (final, concrete)
```

`Concrete` không trực tiếp extends cả Base lẫn Intermediate; nó chỉ có Intermediate là direct superclass. Concrete kế thừa **nghĩa vụ method** từ Base qua Intermediate.

Nếu muốn một type kết hợp nhiều behaviors, có thể:

- `implements` nhiều interfaces.
- Dùng composition/delegation cho collaborator objects.
- Thiết kế một class hierarchy với một superclass có trách nhiệm rõ.

**Không thể** viết `class C extends AbstractA, AbstractB` khi cả hai là classes. Tính abstract không tạo ngoại lệ cho quy tắc đơn kế thừa class.

## 28. Khi nào abstract class là lựa chọn hợp lý?

Một abstract class thường hữu ích nếu:

1. Có **quan hệ is-a thực sự** giữa base type và concrete subtypes.
2. Cần dùng chung **instance state** hoặc constructor validation.
3. Có nhiều **concrete methods** muốn tái sử dụng.
4. Cần cung cấp **template algorithm** với abstract hooks.
5. Muốn ngăn client tạo một khái niệm quá tổng quát nhưng vẫn có concrete children hợp lệ.
6. Muốn quản lý common invariants của hierarchy.

Ví dụ:

- `Shape` abstract; `Rectangle` và `Circle` concrete.
- `Account` abstract giữ ID chung, concrete subclasses hiện thực nghiệp vụ.
- `ReportGenerator` abstract giữ workflow, subclasses cung cấp body.
- `InputStream` trong Java API là một abstract base class cung cấp chung nhiều hành vi stream, với concrete implementations.

### Khi nào nên cân nhắc interface thay thế?

Nếu chỉ cần **hợp đồng khả năng**, không cần common instance fields hoặc constructor, interface có thể linh hoạt hơn:

```java
interface Flyable {
    void fly();
}
```

Một class vẫn có thể extends class cha riêng và implements Flyable cùng các interfaces khác. Dùng abstract class chỉ để bắt buộc một method mà không có shared implementation/state có thể chiếm slot superclass duy nhất không cần thiết.

### Khi nào nên cân nhắc composition?

Nếu A chỉ **dùng** B để làm việc chứ không phải là một loại B, đừng `extends B` chỉ để tái sử dụng code. Dùng field component và delegation:

```java
class Car {
    private final Engine engine = new Engine();

    void start() {
        engine.start();
    }
}

class Engine {
    void start() {
        System.out.println("engine started");
    }
}
```

Đây là class declarations hợp lệ, không có `main`. Car có Engine (*has-a*), không phải subtype của Engine.

## 29. Abstract class vẫn có các members thông thường

Một abstract class có thể chứa:

- Instance fields (bao gồm `private final` hoặc mutable fields).
- Static fields và constants.
- Constructors (có thể `protected`, package-private, public hoặc private trong những thiết kế đặc biệt).
- Concrete instance methods.
- Abstract instance methods.
- Static methods, private helpers.
- Static initialization blocks và instance initialization blocks.
- Nested classes hoặc nested interfaces khi hợp lệ.

Ví dụ:

```java
abstract class Storage {
    private final String name;
    private static int createdCount;

    protected Storage(String name) {
        this.name = name;
        createdCount++;
    }

    String name() {
        return name;
    }

    static int createdCount() {
        return createdCount;
    }

    abstract int size();
}
```

Không có `main` trong đoạn khai báo, nhưng code hợp lệ. Nếu tạo các concrete subclasses của Storage, constructors superclass có thể tăng shared counter như được viết.

**Không nhầm:** `abstract` không làm mọi field mặc nhiên `final`, không làm class thread-safe và không biến static fields thành instance fields. Đó là các vấn đề thiết kế độc lập.

## 30. Modifier `sealed` có thể kết hợp với abstract class trong Java 17

Java 17 hỗ trợ `sealed` hierarchy, cho phép giới hạn những direct subclasses có quyền kế thừa.

Tạo **`SealedAbstractDemo.java`**:

```java
abstract sealed class Event permits LoginEvent, LogoutEvent {
    abstract String kind();
}

final class LoginEvent extends Event {
    @Override
    String kind() {
        return "LOGIN";
    }
}

final class LogoutEvent extends Event {
    @Override
    String kind() {
        return "LOGOUT";
    }
}

public class SealedAbstractDemo {
    public static void main(String[] args) {
        Event login = new LoginEvent();
        Event logout = new LogoutEvent();

        System.out.println(login.kind());
        System.out.println(logout.kind());
    }
}
```

```bash
javac SealedAbstractDemo.java
java SealedAbstractDemo
```

```text
LOGIN
LOGOUT
```

Giải thích:

- `Event` vừa `abstract` vừa `sealed`: không instantiate trực tiếp, và danh sách direct subclasses được kiểm soát.
- `LoginEvent` và `LogoutEvent` được `permits` và khai báo `final` phù hợp.
- Cả hai concrete classes override abstract method `kind()`.
- `sealed` không có nghĩa “có thể tạo instance abstract class” và cũng không có nghĩa “đa kế thừa classes”.

**Phân biệt tổ hợp:** `abstract sealed class` có thể hợp lệ; `abstract final class` là mâu thuẫn và bị cấm.

## 31. Những loại Java đặc biệt không nên nhầm với abstract class thường

### Interface

`interface Runnable { ... }` là interface. Không thể `new Runnable()` trực tiếp, nhưng không phải vì nó được khai báo bằng `abstract class`.

### Enum

Một `enum Status { NEW, DONE }` không cho caller dùng `new Status()`; enum instances được tạo theo quy tắc enum constants. Đây là kiểu đặc biệt và không phải “abstract class bình thường”.

### Record

Một `record Point(int x, int y) {}` là record class với quy tắc constructor/component riêng; record không khai báo `abstract` và có superclass `java.lang.Record`. Record thường có thể được tạo trực tiếp qua canonical constructor phù hợp như `new Point(1,2)`.

### Array

Một `AbstractBase[] array = new AbstractBase[3]` là **array object**, không phải ba abstract instances. Cú pháp array creation hợp lệ dù component type abstract.

### Primitive

`int` và `boolean` không phải class. Không có chuyện chúng abstract hay concrete subclasses của Object.

**Kỹ năng nhận diện:** đọc đúng loại declaration (`class`, `interface`, `enum`, `record`) trước khi suy luận về abstract/constructor.

## 32. Lỗi compile-time thường gặp và cách sửa

| Code / tình huống | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| `new AbstractBase()` | Base abstract | Tạo concrete subclass, dùng factory hoặc anonymous concrete subclass |
| Concrete subclass không triển khai abstract method còn thiếu | Chưa đáp ứng hợp đồng | Override với signature phù hợp hoặc khai báo subclass abstract |
| Class khai báo abstract method nhưng class không abstract | Thiếu modifier ở class | Ghi `abstract class` hoặc cung cấp body cho method |
| `abstract void run() { }` | Abstract method không có body | Bỏ body hoặc bỏ `abstract` |
| `abstract final class X` | Hai class modifiers mâu thuẫn | Quyết định X có được subclass không |
| `private abstract void run();` | Private không phù hợp override nghĩa vụ | Dùng protected/package/public khi phù hợp |
| `static abstract void run();` | Static không được override như instance | Dùng instance abstract hoặc concrete static |
| `final abstract void run();` | Final cấm override | Bỏ một modifier theo ý định |
| Override method nhưng giảm visibility | Vi phạm override rules | Giữ hoặc mở rộng access |
| Implements interface public method bằng package-private method | Implementation thiếu quyền public | Khai báo `public` |
| Dùng `new Base()` trong base factory | Vẫn instantiate abstract trực tiếp | Factory trả concrete subtype |
| Lấy `Base.class` rồi nghĩ có Base instance | Class object là metadata, không phải instance Base | Tạo concrete subtype |
| Dùng `Modifier.isAbstract` đơn lẻ để kết luận là abstract class | Interface có thể mang abstract flag | Kiểm `!type.isInterface()`/category |
| Gọi abstract hook trong constructor | Subclass fields có thể chưa init | Tránh virtual calls khi constructing |
| Viết hai `extends` class | Java đơn kế thừa class | Một superclass + interfaces/composition |
| Cho rằng abstract class không thể có constructor | Hiểu nhầm direct instantiation | Constructor chạy qua concrete subclass |
| Cho rằng abstract class bắt buộc có abstract methods | Không đúng | Dùng modifier abstract để ngăn direct instances khi có lý do |
| Dùng `new AbstractBase[5]` rồi tưởng tạo năm instances | Chỉ tạo mảng slots null | Tạo từng concrete object nếu cần |

## 33. Bài thực hành tổng hợp: dự đoán và giải thích output

Tạo **`AbstractTraceDemo.java`**:

```java
abstract class Worker {
    private final String name;

    Worker(String name) {
        this.name = name;
        System.out.println("Worker(" + name + ")");
    }

    final String name() {
        return name;
    }

    abstract int score();

    String summary() {
        return name() + ":" + score();
    }
}

abstract class SkilledWorker extends Worker {
    SkilledWorker(String name) {
        super(name);
        System.out.println("SkilledWorker()");
    }

    abstract String specialty();
}

final class Developer extends SkilledWorker {
    Developer(String name) {
        super(name);
        System.out.println("Developer()");
    }

    @Override
    int score() {
        return 95;
    }

    @Override
    String specialty() {
        return "Java";
    }
}

public class AbstractTraceDemo {
    public static void main(String[] args) {
        Worker worker = new Developer("An");

        System.out.println(worker.summary());
        System.out.println(worker.getClass().getSimpleName());

        if (worker instanceof SkilledWorker skilled) {
            System.out.println(skilled.specialty());
        }
    }
}
```

```bash
javac AbstractTraceDemo.java
java AbstractTraceDemo
```

**Output:**

```text
Worker(An)
SkilledWorker()
Developer()
An:95
Developer
Java
```

### Lời giải theo trình tự

1. Biểu thức `new Developer("An")` tạo object thuộc concrete class Developer.
2. Constructor chain chạy `Worker(String)`, `SkilledWorker(String)` rồi `Developer(String)`; hai lớp cha abstract **vẫn có constructors** chạy.
3. Biến `worker` có static type Worker, nhưng reference trỏ **Developer object**.
4. `worker.summary()` là concrete method của Worker; khi gọi abstract `score()`, runtime dispatch vào `Developer.score()`.
5. `getClass().getSimpleName()` trả runtime class Developer.
6. Pattern `instanceof SkilledWorker skilled` thành công vì Developer extends SkilledWorker; sau đó gọi concrete implementation `Developer.specialty()`.

**Không có lời gọi nào tạo object bằng `new Worker()` hay `new SkilledWorker()`**. Constructor hai lớp abstract được thực hiện trong quá trình tạo một instance thuộc concrete descendant Developer.

## 34. Bài tập thực hành có lời giải

**Bài 1.** Viết `abstract class Payment` có method `abstract int fee()` và concrete `String describe()`. Viết `CardPayment` concrete trả phí 5. Có được `Payment payment = new CardPayment()` không?

*Đáp án:* Được. Object là CardPayment; reference type Payment. Không được `new Payment()` trực tiếp.

**Bài 2.** Class `abstract class Base {}` có thể instantiate trực tiếp không? Lý do?

*Đáp án:* Không. Modifier `abstract` tự nó cấm trực tiếp tạo instance, dù class không có abstract method.

**Bài 3.** Abstract class có thể có constructor với tham số không?

*Đáp án:* Có. Concrete subclass gọi constructor superclass thích hợp qua `super(args)`.

**Bài 4.** `final class Child extends Base` với Base abstract có hợp lệ không?

*Đáp án:* Có nếu Child triển khai đủ abstract methods còn thiếu và kế thừa hợp lệ. Final ở Child chỉ cấm subclass của Child.

**Bài 5.** `abstract final class X` có hợp lệ không?

*Đáp án:* Không. Hai class modifiers mâu thuẫn.

**Bài 6.** Nếu abstract method khai báo `protected abstract void work();`, overriding method subclass có thể `private` không?

*Đáp án:* Không. Không được thu hẹp visibility khi override.

**Bài 7.** Abstract class implements interface nhưng chưa cài method có compile được không?

*Đáp án:* Có thể, nếu class tiếp tục abstract và các quy tắc declaration được thỏa. Concrete subclass vẫn phải có implementation phù hợp.

**Bài 8.** `new AbstractBase[10]` có hợp lệ không?

*Đáp án:* Có. Chỉ tạo array object với các slots null, không tạo AbstractBase instances.

**Bài 9.** `new AbstractBase() { @Override ... }` có phải tạo instance của abstract base trực tiếp không?

*Đáp án:* Không. Nó tạo một anonymous subclass concrete (nếu đã implement đủ abstract methods).

**Bài 10.** `AbstractBase.class` có hợp lệ không?

*Đáp án:* Có. Đây là Class metadata, không tạo abstract instance.

**Bài 11.** `Modifier.isAbstract(SomeInterface.class.getModifiers())` có thể true không?

*Đáp án:* Có. Dùng thêm `Class.isInterface()` khi phân biệt interface với abstract class.

**Bài 12.** Trong abstract class, `static int add(...)` có được gọi bằng tên lớp mà không tạo instance không?

*Đáp án:* Có. Static method không cần abstract class instance.

**Bài 13.** Superclass constructor gọi abstract hook bị override trong Child; lúc ấy các field initializers Child đã chạy chưa?

*Đáp án:* Chưa theo constructor chain bình thường. Override có thể nhìn thấy default values của Child fields, nên nên tránh kiểu gọi này.

**Bài 14.** Có thể dùng `abstract` cho constructor không?

*Đáp án:* Không. Constructors không phải abstract methods và không được khai báo abstract. Chúng thực hiện khởi tạo instance theo constructor chain.

**Bài 15.** `abstract class Service` có thể giữ mutable instance state không?

*Đáp án:* Có. Abstract quyết định direct instantiation, không tự quyết định mutability.

**Bài 16.** Hai abstract classes A, B có thể là direct superclasses của một class C không?

*Đáp án:* Không. Java vẫn là single class inheritance; có thể dùng interfaces hoặc composition khi thiết kế yêu cầu nhiều capabilities.

**Bài 17.** Một `final` concrete method trong abstract superclass có cần override ở subclass không?

*Đáp án:* Không, và cũng không được override. Concrete method đã có implementation dùng chung.

**Bài 18.** Nếu muốn chỉ cung cấp contract cho nhiều unrelated classes, dùng gì?

*Đáp án:* Cân nhắc interface, vì class có thể implements nhiều interfaces bên cạnh một superclass phù hợp.

## 35. Checklist khi đọc và viết abstract class

- [ ] Tôi đã nhìn vào **modifier `abstract` trên class declaration**, không đoán từ tên?
- [ ] Tôi phân biệt abstract class với interface, enum, record và concrete class có private constructor?
- [ ] Tôi biết `new AbstractBase()` trực tiếp là compile-time error?
- [ ] Tôi biết abstract-typed reference, parameter và return type vẫn hợp lệ?
- [ ] Nếu dùng `new AbstractBase() { ... }`, tôi hiểu đó là anonymous subclass?
- [ ] Concrete subclasses có triển khai đủ abstract instance methods còn thiếu?
- [ ] Các overrides có đúng signature, access, checked exceptions và `@Override` khi phù hợp?
- [ ] Tôi không viết abstract method có body?
- [ ] Tôi không kết hợp abstract với private/static/final/synchronized/native theo những tổ hợp bị cấm?
- [ ] Tôi không kết hợp `abstract final` trên class?
- [ ] Tôi hiểu abstract class có constructors và chúng chạy qua concrete subclass construction?
- [ ] Nếu superclass chỉ có constructor tham số, subclass đã gọi `super(args)` hợp lệ?
- [ ] Tôi tránh gọi overridable abstract hooks trong constructor?
- [ ] Tôi biết abstract class có thể không có abstract method nào?
- [ ] Tôi biết abstract class có thể chứa concrete, final, static, private helpers và fields?
- [ ] Tôi không nhầm abstract class với “class có trạng thái bất biến”?
- [ ] Tôi biết `Base.class`/`Class<?>` không phải Base instance?
- [ ] Tôi biết mảng `Base[]` không tạo abstract elements?
- [ ] Tôi dùng reflection flags kèm kiểm loại type khi cần nhận diện?
- [ ] Tôi chọn abstract class khi cần is-a/shared state/implementation, interface khi cần capability contract?
- [ ] Tôi đã soát tên tệp public class, Java 17 syntax, `javac`/`java` và stdout của những ví dụ runnable?

---

**Ghi nhớ cuối bài:** Lớp được khai báo **`abstract class` không thể tạo instance trực tiếp bằng `new AbstractClass()`**, bất kể có abstract methods hay không. Tuy nhiên, nó **vẫn là một type hợp lệ** cho biến tham chiếu, tham số, return type, mảng, static API và class metadata. Object thật sự thường được tạo bằng **concrete subclass** hoặc một **anonymous concrete subclass** triển khai đầy đủ các abstract instance methods. Abstract class có thể chứa fields, constructors và concrete methods; constructor của nó vẫn chạy qua constructor chain khi tạo subclass object. Hãy phân biệt rạch ròi **hạn chế direct instantiation** với **quyền truy cập constructor**, interface semantics và mọi vấn đề mutability/concurrency. Đó là nền tảng để dùng kế thừa và đa hình an toàn trong Java.