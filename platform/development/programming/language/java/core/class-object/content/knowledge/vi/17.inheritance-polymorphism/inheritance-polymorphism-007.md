# Điều phối phương thức đối tượng theo lớp thực tế trong Java

**Điều phối phương thức động** (*dynamic method dispatch*, *virtual method invocation*) là cơ chế Java lựa chọn **implementation của instance method được override** dựa trên **lớp thực tế của đối tượng tại thời điểm chạy**, chứ không đơn thuần dựa vào kiểu khai báo của biến đang giữ tham chiếu.

Ví dụ:

```java
Animal animal = new Dog();
animal.speak();
```

Khi `Animal` khai báo một instance method `speak()` có thể được override, còn `Dog` override method đó, lời gọi `animal.speak()` sẽ chạy **`Dog.speak()`**. Biến `animal` vẫn có **kiểu khai báo `Animal`**, nhưng đối tượng nó trỏ tới thuộc **lớp runtime `Dog`**.

Đây là nền tảng của **đa hình động** trong Java: client viết code theo một superclass hoặc interface nhưng có thể nhận những object thuộc các lớp triển khai khác nhau.

Tuy nhiên, cần hiểu **hai giai đoạn khác nhau**:

1. **Lúc biên dịch:** compiler dùng **kiểu tĩnh của biểu thức receiver**, tên method, danh sách đối số, quyền truy cập và các quy tắc overloading để xác định lời gọi có hợp lệ và chọn **chữ ký method** nào.
2. **Lúc chạy:** đối với một **instance method có dispatch động**, JVM dùng **runtime class của receiver** để chọn implementation override phù hợp nhất theo quy tắc Java.

**Không phải mọi lần viết `object.method()` đều là dynamic dispatch.** Static methods bị **hiding**, fields bị **hiding**, overloading được giải quyết ở compile time, private methods không override như public/protected methods, còn `super.method()` chỉ định implementation superclass một cách đặc biệt.

Bài học dành cho **Java 17+**. Mỗi ví dụ chạy độc lập đều có tên tệp, lệnh `javac`/`java` và stdout; đoạn minh họa cố ý lỗi được comment hoặc nêu rõ.

## 1. Kiểu khai báo và lớp runtime: hai thông tin phải tách riêng

Giả sử:

```java
class Animal {
    void speak() {
        System.out.println("Animal");
    }
}

class Dog extends Animal {
    @Override
    void speak() {
        System.out.println("Dog");
    }
}
```

Khi viết:

```java
Animal pet = new Dog();
```

ta có:

| Khái niệm | Trong ví dụ |
| --- | --- |
| **Kiểu khai báo** của biến `pet` | `Animal` |
| **Kiểu của biểu thức `new Dog()`** | `Dog` |
| **Lớp runtime** của object mà `pet` trỏ tới | `Dog` |
| **Method `speak()` thấy được qua `Animal`** | `Animal.speak()` |
| **Implementation của `pet.speak()` được gọi** | `Dog.speak()` |

Compiler cho phép phép gán vì `Dog` là subtype của `Animal`. Phép gán này thường gọi là **upcasting**; trong trường hợp này không cần viết cast tường minh.

Sau phép gán, `pet` **không trở thành một object `Animal` mới**. Object vẫn là object `Dog`. Kiểu biến chỉ giới hạn cách code có thể **sử dụng object qua tham chiếu đó**.

### Vì sao phải tách hai thông tin?

Hai lời gọi:

```java
Animal first = new Animal();
Animal second = new Dog();

first.speak();
second.speak();
```

có cùng kiểu receiver tại compile time (`Animal`) và cùng method signature được nhìn thấy, nhưng có thể chạy **hai implementation khác nhau** vì hai receiver objects có runtime classes khác nhau.

Đó chính là sự khác nhau giữa **kiểm tra kiểu tĩnh** và **điều phối động**.

## 2. Ví dụ Java 17 hoàn chỉnh: dispatch theo object runtime

Lưu thành **`DynamicDispatchDemo.java`**:

```java
class Animal {
    void speak() {
        System.out.println("Animal speaks");
    }
}

class Dog extends Animal {
    @Override
    void speak() {
        System.out.println("Dog barks");
    }
}

class Cat extends Animal {
    @Override
    void speak() {
        System.out.println("Cat meows");
    }
}

public class DynamicDispatchDemo {
    public static void main(String[] args) {
        Animal first = new Animal();
        Animal second = new Dog();
        Animal third = new Cat();

        first.speak();
        second.speak();
        third.speak();
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 DynamicDispatchDemo.java
java DynamicDispatchDemo
```

**Stdout chính xác:**

```text
Animal speaks
Dog barks
Cat meows
```

Giải thích:
- `first` trỏ object `Animal` → dùng `Animal.speak()`.
- `second` trỏ object `Dog` → JVM chọn override `Dog.speak()`.
- `third` trỏ object `Cat` → JVM chọn override `Cat.speak()`.
- Ba biến cùng khai báo kiểu `Animal` nhưng implementation được gọi **không nhất thiết giống nhau**.
- Annotation `@Override` giúp compiler kiểm tra method thật sự override hợp lệ, nhưng **không phải thứ tạo ra dynamic dispatch**; override vẫn có ngữ nghĩa tương ứng nếu bỏ annotation.

## 3. Một reference có thể trỏ tới object lớp con khác vào các thời điểm khác nhau

```java
Animal animal = new Dog();
animal.speak();

animal = new Cat();
animal.speak();
```

Hai lời gọi trên tương ứng chạy `Dog.speak()` rồi `Cat.speak()`. Biến `animal` không thay kiểu khai báo; chỉ **giá trị tham chiếu** được gán lại.

Sơ đồ:

```text
Ban đầu:
animal : Animal ─────► Dog object
                      Dog.speak()

Sau phép gán:
animal : Animal ─────► Cat object
                      Cat.speak()
```

**Kiểu tĩnh của biến không thay đổi qua phép gán.** Object runtime được tham chiếu có thể thay đổi nếu biến được phép gán lại và object mới là một subtype tương thích.

Nếu `animal` được khai báo `final Animal animal = new Dog();`, bạn không thể gán lại `animal = new Cat();`, nhưng một lần gọi `animal.speak()` vẫn dispatch tới `Dog.speak()`: **final reference không tắt đa hình**.

## 4. Compiler giải quyết những gì trước khi JVM dispatch?

Xét:

```java
Animal animal = new Dog();
animal.speak();
```

Ở compile time, Java cần trả lời:
- Biểu thức `animal` có **kiểu tĩnh** gì?
- Từ kiểu đó có thể truy cập method `speak()` với các đối số đã cho không?
- Có bao nhiêu overload phù hợp và overload nào được chọn?
- Method có bị giới hạn bởi access control không?
- Kiểu trả về nào được dùng cho biểu thức lời gọi?
- Có cần chuyển kiểu đối số, boxing/unboxing hoặc áp dụng varargs không?

Chỉ sau khi lời gọi đã hợp lệ và được liên kết đến **chữ ký phù hợp**, việc chọn **instance implementation** mới có thể diễn ra tại runtime.

**Quan trọng:** runtime class không cho bạn gọi tùy ý một method chỉ tồn tại ở subclass mà kiểu tĩnh của receiver không khai báo hoặc không kế thừa.

```java
class Dog extends Animal {
    void fetch() {
        System.out.println("Fetch");
    }
}

Animal animal = new Dog();
// animal.fetch(); // SAI nếu Animal không khai báo fetch().
```

Lỗi nằm ở **compile-time member lookup**. Object runtime là `Dog` không làm compiler bỏ qua kiểu `Animal`.

## 5. Chương trình: kiểu tĩnh giới hạn API, runtime chọn implementation

Lưu **`StaticViewRuntimeDemo.java`**:

```java
class Vehicle {
    String describe() {
        return "Vehicle";
    }
}

class ElectricCar extends Vehicle {
    @Override
    String describe() {
        return "ElectricCar";
    }

    int batteryPercent() {
        return 80;
    }
}

public class StaticViewRuntimeDemo {
    public static void main(String[] args) {
        Vehicle vehicle = new ElectricCar();

        System.out.println(vehicle.describe());

        // vehicle.batteryPercent();
        // SAI: batteryPercent() không có trong kiểu Vehicle.

        ElectricCar car = (ElectricCar) vehicle;
        System.out.println(car.batteryPercent());
    }
}
```

```bash
javac -encoding UTF-8 StaticViewRuntimeDemo.java
java StaticViewRuntimeDemo
```

Stdout:

```text
ElectricCar
80
```

Ở đây:
- `describe()` có trong contract `Vehicle`; implementation được dispatch theo runtime object.
- `batteryPercent()` chỉ có ở `ElectricCar`; muốn gọi phải có receiver expression có kiểu tĩnh đủ cụ thể, ví dụ biến `car` sau phép cast hợp lệ.
- Phép cast **không tạo đối tượng mới** và **không đổi runtime class** của object; nó chỉ cho compiler một view kiểu khác, kèm kiểm tra tương thích ở runtime khi cần.

## 6. Overriding: điều kiện để dispatch động thay implementation

Một method trong subclass được coi là override khi thỏa các quy tắc ngôn ngữ, bao gồm những yêu cầu liên quan tới:
- Cùng tên và chữ ký phù hợp (*override-equivalent signatures*).
- Loại method có khả năng override: **instance method**, không phải static method.
- Method superclass không `final`, và method cần được kế thừa/override được theo access rules.
- Quyền truy cập của subclass không bị thu hẹp trái quy tắc.
- Kiểu trả về tương thích (*return-type substitutability*, có thể covariant).
- Checked exceptions khai báo tương thích với overridden method.
- Các quy tắc generic, erasure và bridge methods khi liên quan.

Annotation `@Override` được khuyến khích:

```java
class Base {
    protected String label() {
        return "Base";
    }
}

class Child extends Base {
    @Override
    public String label() {
        return "Child";
    }
}
```

`Child.label()` hợp lệ vì tăng mức visibility từ `protected` lên `public` được phép. Nếu đổi thành `private String label()`, compiler từ chối do giảm accessibility của method bị override.

**Không phải chỉ có `public` mới được override.** `protected` và package-private methods có thể được override khi thỏa điều kiện package/access; `private` không được override theo cùng cơ chế.

## 7. Lớp con không override thì tìm implementation ở đâu?

Runtime dispatch không nhất thiết chọn method viết **ngay trong runtime class**. JVM dùng implementation override **phù hợp gần nhất** trong hierarchy/class–interface method resolution theo semantics Java.

Ví dụ:

```java
class Parent {
    void say() {
        System.out.println("Parent");
    }
}

class Middle extends Parent {
    @Override
    void say() {
        System.out.println("Middle");
    }
}

class Child extends Middle {
    // Không override say().
}
```

Với `Parent value = new Child(); value.say();`, kết quả là `Middle`. Runtime class `Child` **kế thừa** implementation `Middle.say()`.

Điều này tinh tế hơn câu “Java gọi method của runtime class”: cần hiểu là **Java chọn implementation ứng với runtime class theo chuỗi override**, có thể được kế thừa từ superclass.

### Chương trình hoàn chỉnh

Lưu **`InheritedOverrideDemo.java`**:

```java
class Parent {
    String source() {
        return "Parent";
    }
}

class Middle extends Parent {
    @Override
    String source() {
        return "Middle";
    }
}

class Child extends Middle {
}

public class InheritedOverrideDemo {
    public static void main(String[] args) {
        Parent first = new Parent();
        Parent second = new Middle();
        Parent third = new Child();

        System.out.println(first.source());
        System.out.println(second.source());
        System.out.println(third.source());
    }
}
```

```bash
javac -encoding UTF-8 InheritedOverrideDemo.java
java InheritedOverrideDemo
```

Stdout:

```text
Parent
Middle
Middle
```

## 8. Overloading khác overriding: hai giai đoạn không được nhầm

**Overloading:** cùng tên method, **khác danh sách tham số** theo chữ ký. Compiler lựa chọn overload dựa vào **kiểu tĩnh của đối số** và các quy tắc resolution.

**Overriding:** subclass định nghĩa lại **instance method có cùng chữ ký tương ứng**, và runtime có thể lựa chọn implementation dựa vào **lớp thực tế của receiver**.

Ví dụ:

```java
class Printer {
    void print(Animal animal) {
        System.out.println("Animal overload");
    }

    void print(Dog dog) {
        System.out.println("Dog overload");
    }
}

Printer printer = new Printer();
Animal value = new Dog();

printer.print(value); // Chọn print(Animal), không phải print(Dog).
```

Dù object của `value` là `Dog`, compiler thấy **kiểu tĩnh của đối số `value` là `Animal`**, nên chọn overload phù hợp với `Animal`.

Đừng mô tả overloading là “đa hình runtime”. Nó có thể được gọi là compile-time polymorphism ở cách phân loại phổ thông, nhưng **overload selection** vẫn dựa trên static typing.

## 9. Ví dụ trọng tâm: overload tĩnh, override động trong cùng lời gọi

Lưu **`OverloadOverrideDemo.java`**:

```java
class Animal {
}

class Dog extends Animal {
}

class Handler {
    String handle(Animal animal) {
        return "Handler: Animal";
    }

    String handle(Dog dog) {
        return "Handler: Dog";
    }
}

class SpecialHandler extends Handler {
    @Override
    String handle(Animal animal) {
        return "Special: Animal";
    }

    @Override
    String handle(Dog dog) {
        return "Special: Dog";
    }
}

public class OverloadOverrideDemo {
    public static void main(String[] args) {
        Handler handler = new SpecialHandler();

        Animal first = new Dog();
        Dog second = new Dog();

        System.out.println(handler.handle(first));
        System.out.println(handler.handle(second));
        System.out.println(handler.handle((Animal) second));
    }
}
```

```bash
javac -encoding UTF-8 OverloadOverrideDemo.java
java OverloadOverrideDemo
```

**Stdout:**

```text
Special: Animal
Special: Dog
Special: Animal
```

Phân tích thật chậm:

1. `handler` có kiểu khai báo `Handler`, runtime receiver là `SpecialHandler`.
2. `first` có kiểu khai báo `Animal`, mặc dù object là `Dog`. Compiler chọn signature `handle(Animal)`.
3. JVM dispatch signature `handle(Animal)` tới override `SpecialHandler.handle(Animal)` → in `Special: Animal`.
4. `second` có kiểu tĩnh `Dog`. Compiler chọn `handle(Dog)`, runtime chọn override ở `SpecialHandler` → `Special: Dog`.
5. Cast `(Animal) second` làm **kiểu tĩnh của biểu thức đối số** là `Animal`. Compiler chọn `handle(Animal)`, dù object vẫn là Dog → `Special: Animal`.

**Công thức:** *overload chọn chữ ký bằng static types; override chọn implementation bằng runtime receiver*. Không nên đảo vai trò của hai giai đoạn.

## 10. Kiểu runtime của **đối số** không tự chọn overload

Đây là trường hợp rất dễ dự đoán sai:

```java
void examine(Object value) {
    System.out.println("Object");
}

void examine(String value) {
    System.out.println("String");
}
```

Với:

```java
Object object = "Java";
examine(object); // Chọn examine(Object).
```

Dù runtime object là `String`, **static type của đối số** vẫn là `Object`. Compiler không chạy đến lúc runtime rồi mới “tìm overload cụ thể hơn”.

Nếu bạn thật sự muốn lựa chọn hành vi theo runtime subtype của đối số, thiết kế options:
- Dùng **method override trên chính đối tượng tham gia** (đưa hành vi về đúng receiver nếu contract cho phép).
- Dùng pattern matching `instanceof` hoặc sealed hierarchy khi tập biến thể rõ.
- Dùng **Visitor/double dispatch** nếu bài toán là chọn thuật toán dựa trên hai kiểu runtime và độ phức tạp phù hợp.
- Dùng strategy registry theo loại event/domain nếu cần extensibility ngoài hierarchy.

Không nên giả định JVM tự làm multiple dispatch cho một lời gọi overload thông thường của Java.

## 11. Lời gọi qua interface vẫn dispatch động

Interface định nghĩa một **contract**. Caller không cần biết concrete implementation.

```java
interface PaymentMethod {
    String pay(int amount);
}

class CardPayment implements PaymentMethod {
    @Override
    public String pay(int amount) {
        return "CARD " + amount;
    }
}

class CashPayment implements PaymentMethod {
    @Override
    public String pay(int amount) {
        return "CASH " + amount;
    }
}
```

Nếu:

```java
PaymentMethod method = new CardPayment();
System.out.println(method.pay(100));
```

thì implementation của `CardPayment` được gọi.

**Điểm quan trọng:** Java interface method dispatch không phải chọn implementation bằng “tên interface cố định”. Object runtime có quyền cung cấp implementation phù hợp của method contract.

### Ví dụ interface runnable

Lưu **`InterfaceDispatchDemo.java`**:

```java
interface Messenger {
    String send(String text);
}

final class EmailMessenger implements Messenger {
    @Override
    public String send(String text) {
        return "EMAIL: " + text;
    }
}

final class SmsMessenger implements Messenger {
    @Override
    public String send(String text) {
        return "SMS: " + text;
    }
}

public class InterfaceDispatchDemo {
    private static void deliver(Messenger messenger) {
        System.out.println(messenger.send("Hello"));
    }

    public static void main(String[] args) {
        deliver(new EmailMessenger());
        deliver(new SmsMessenger());
    }
}
```

```bash
javac -encoding UTF-8 InterfaceDispatchDemo.java
java InterfaceDispatchDemo
```

Stdout:

```text
EMAIL: Hello
SMS: Hello
```

Phương thức `deliver` chỉ biết interface `Messenger`; nó không có `if`/`instanceof` để dò concrete class. Điều phối động giúp mở rộng bằng implementation mới.

## 12. Interface default methods cũng tham gia lựa chọn implementation

Java cho phép interface có **default instance method**:

```java
interface Greeter {
    default String hello() {
        return "Hello from interface";
    }
}
```

Nếu một class implements interface mà không override `hello()`, instance có thể dùng default implementation theo quy tắc interface method resolution.

```java
class BasicGreeter implements Greeter {
}
```

`new BasicGreeter().hello()` dùng default method `Greeter.hello()`.

Nếu class override:

```java
class FriendlyGreeter implements Greeter {
    @Override
    public String hello() {
        return "Hi from class";
    }
}
```

thì lời gọi qua `Greeter` có thể dispatch tới `FriendlyGreeter.hello()`.

**Lưu ý:** interface static methods **không** giống default instance methods: chúng không tham gia instance override dispatch như `hello()`.

## 13. Class method ưu tiên hơn interface default method khi phù hợp

Java có quy tắc giải quyết xung đột default methods, thường tóm tắt bằng ý **class wins over interface defaults** khi tồn tại implementation class method phù hợp.

Ví dụ:

```java
interface Greeter {
    default String hello() {
        return "Interface";
    }
}

class Parent {
    public String hello() {
        return "Parent";
    }
}

class Child extends Parent implements Greeter {
}
```

`new Child().hello()` dùng `Parent.hello()`, không dùng default của `Greeter`.

Khi hai unrelated interfaces cùng cung cấp default method có chữ ký xung đột, implementing class có thể phải **override giải quyết tường minh**. Không nên giả định Java tùy ý chọn interface được viết trước trong `implements`.

### Chương trình Java 17 runnable

Lưu **`DefaultMethodDispatchDemo.java`**:

```java
interface Greeter {
    default String hello() {
        return "Interface";
    }
}

class Parent {
    public String hello() {
        return "Parent";
    }
}

class Child extends Parent implements Greeter {
}

class CustomGreeter implements Greeter {
    @Override
    public String hello() {
        return "Custom";
    }
}

public class DefaultMethodDispatchDemo {
    public static void main(String[] args) {
        Greeter first = new Child();
        Greeter second = new CustomGreeter();

        System.out.println(first.hello());
        System.out.println(second.hello());
    }
}
```

```bash
javac -encoding UTF-8 DefaultMethodDispatchDemo.java
java DefaultMethodDispatchDemo
```

Stdout:

```text
Parent
Custom
```

Trong lời gọi `first.hello()`, `Child` kế thừa class implementation `Parent.hello()` phù hợp nên không chọn default implementation của `Greeter`. Trong lời gọi `second.hello()`, class `CustomGreeter` cung cấp override riêng.

## 14. Giải quyết xung đột hai default methods

Đoạn **sai nếu không override**:

```java
interface Left {
    default String name() {
        return "Left";
    }
}

interface Right {
    default String name() {
        return "Right";
    }
}

// class Both implements Left, Right { }
// SAI: inherited unrelated defaults conflict.
```

Cách sửa: class phải cung cấp một implementation rõ ràng:

```java
class Both implements Left, Right {
    @Override
    public String name() {
        return Left.super.name() + "+" + Right.super.name();
    }
}
```

`Left.super.name()` và `Right.super.name()` là **qualified interface super invocation** trong ngữ cảnh instance phù hợp; chúng không phải dynamic dispatch tùy tiện sang interface nào cũng được. Cú pháp có những quy tắc ràng buộc về direct superinterfaces và quan hệ kế thừa.

### Ví dụ runnable

Lưu **`DefaultConflictDemo.java`**:

```java
interface Left {
    default String name() {
        return "Left";
    }
}

interface Right {
    default String name() {
        return "Right";
    }
}

class Both implements Left, Right {
    @Override
    public String name() {
        return Left.super.name() + "/" + Right.super.name();
    }
}

public class DefaultConflictDemo {
    public static void main(String[] args) {
        Left value = new Both();
        System.out.println(value.name());
    }
}
```

```bash
javac -encoding UTF-8 DefaultConflictDemo.java
java DefaultConflictDemo
```

Stdout:

```text
Left/Right
```

Compiler xác định hợp đồng và subclass method cụ thể; runtime gọi `Both.name()` khi receiver thực tế là `Both`. Bên trong override, code **cố ý chỉ định** hai interface default implementations để kết hợp.

## 15. Static method **không** điều phối theo lớp runtime

Một static method thuộc về **class/interface theo cách khai báo**, không có dynamic dispatch dựa vào runtime instance. Nếu subclass khai báo static method cùng tên/chữ ký phù hợp, đó là **method hiding**, không phải overriding.

```java
class Parent {
    static String kind() {
        return "Parent";
    }
}

class Child extends Parent {
    static String kind() {
        return "Child";
    }
}
```

```java
Parent reference = new Child();
System.out.println(reference.kind());
```

Kết quả là `Parent`, bởi compiler liên kết static method call dựa trên kiểu phù hợp của expression `reference` (`Parent`), **không** theo runtime class `Child`.

**Phong cách khuyến nghị:**

```java
Parent.kind();
Child.kind();
```

Không nên gọi static method qua object reference, dù Java có thể cho phép, vì rất dễ khiến người đọc tưởng lời gọi sẽ dispatch đa hình.

## 16. Ví dụ runnable: static hiding khác instance overriding

Lưu **`StaticVersusInstanceDemo.java`**:

```java
class Parent {
    static String staticLabel() {
        return "Parent static";
    }

    String instanceLabel() {
        return "Parent instance";
    }
}

class Child extends Parent {
    static String staticLabel() {
        return "Child static";
    }

    @Override
    String instanceLabel() {
        return "Child instance";
    }
}

public class StaticVersusInstanceDemo {
    public static void main(String[] args) {
        Parent value = new Child();

        System.out.println(value.staticLabel());
        System.out.println(value.instanceLabel());
        System.out.println(Parent.staticLabel());
        System.out.println(Child.staticLabel());
    }
}
```

```bash
javac -encoding UTF-8 StaticVersusInstanceDemo.java
java StaticVersusInstanceDemo
```

**Stdout:**

```text
Parent static
Child instance
Parent static
Child static
```

- `value.staticLabel()` được chọn theo kiểu tĩnh `Parent`; đây là cách gọi nên tránh trong code mới.
- `value.instanceLabel()` dùng runtime object `Child` và gọi override.
- `Parent.staticLabel()`/`Child.staticLabel()` chỉ định trực tiếp class chứa implementation static mong muốn.

**Cảnh báo:** static method không được override bằng instance method cùng chữ ký trong subclass, và instance method không được thay bằng static method cùng chữ ký như một override/hiding hợp lệ. Compiler từ chối các kiểu “chuyển static ↔ instance” không đúng.

## 17. Field access không tham gia dynamic method dispatch

Nếu subclass khai báo field trùng tên superclass, biểu thức `reference.field` được phân giải bằng quy tắc **field access** của compiler — không theo runtime class như overridable instance method. Một cast có thể thay **kiểu tĩnh của biểu thức**, từ đó đổi field được chọn, nhưng **không chuyển object thành instance khác**.

Để quan sát sự khác biệt này trong bài về runtime dispatch, xem ngay chương trình `FieldVsMethodDemo` ở mục 18: cùng một `new Child()`, `reference.label` đọc Parent field trong khi `reference.getLabel()` dispatch đến Child override.

Không thiết kế polymorphism bằng fields; nên đặt state `private`, cung cấp overridable instance methods hoặc interface contract có ý nghĩa. **Bài về field/static hiding** phân tích sâu các quy tắc hiding và lookup; bài này chỉ nhấn mạnh chúng **không thuộc phạm vi dynamic method dispatch**.

## 18. Ví dụ field vs method: một object, hai hành vi chọn khác nhau

Lưu **`FieldVsMethodDemo.java`**:

```java
class Parent {
    String label = "Parent field";

    String getLabel() {
        return "Parent method";
    }
}

class Child extends Parent {
    String label = "Child field";

    @Override
    String getLabel() {
        return "Child method";
    }
}

public class FieldVsMethodDemo {
    public static void main(String[] args) {
        Parent reference = new Child();

        System.out.println(reference.label);
        System.out.println(reference.getLabel());

        Child child = (Child) reference;
        System.out.println(child.label);
        System.out.println(child.getLabel());
    }
}
```

```bash
javac -encoding UTF-8 FieldVsMethodDemo.java
java FieldVsMethodDemo
```

**Stdout:**

```text
Parent field
Child method
Child field
Child method
```

Giải thích:
- `reference.label` → field của `Parent` vì compiler thấy `Parent`.
- `reference.getLabel()` → override của `Child` vì runtime receiver là `Child`.
- `child.label` → field của `Child` vì kiểu tĩnh sau cast là `Child`.
- `child.getLabel()` → vẫn `Child` vì runtime object không đổi.

**Lưu ý:** một cast thành `Parent` không “chuyển object thành Parent” hay làm mất phần Child. Nó chỉ đổi **kiểu biểu thức** ở compile time.

## 19. `super.method()` là lời gọi implementation superclass có chủ đích

Trong subclass instance method, cú pháp `super.method()` cho phép gọi implementation superclass phù hợp **mà không chọn override ở chính subclass làm đích trực tiếp**.

Ví dụ:

```java
class Parent {
    String describe() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String describe() {
        return "Child->" + super.describe();
    }
}
```

Khi `Child.describe()` được gọi:
- Runtime dispatch chọn `Child.describe()`.
- Trong body này, `super.describe()` chỉ định implementation từ superclass.
- Kết quả là `Child->Parent`.

**Không nhầm** `super.describe()` với `((Parent)this).describe()`:
- `super.describe()` là special superclass invocation.
- `((Parent)this).describe()` vẫn là một lời gọi virtual method thông thường qua receiver là object `Child`; vì thế có thể dispatch quay lại `Child.describe()` và dẫn đến recursion nếu dùng để thay `super`.

### Ví dụ runnable

Lưu **`SuperDispatchDemo.java`**:

```java
class Parent {
    String describe() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String describe() {
        return "Child/" + super.describe();
    }
}

public class SuperDispatchDemo {
    public static void main(String[] args) {
        Parent value = new Child();

        System.out.println(value.describe());
        System.out.println(((Child) value).describe());
    }
}
```

```bash
javac -encoding UTF-8 SuperDispatchDemo.java
java SuperDispatchDemo
```

Stdout:

```text
Child/Parent
Child/Parent
```

Không có lời gọi `super` từ một static method của class theo nghĩa receiver instance: static context không có `this`/`super` implicit của class đó.

## 20. `private` method không bị override theo cách thông thường

`private` instance method của superclass **không được kế thừa để override**. Nếu subclass khai báo method cùng tên và tham số có thể trùng, đó có thể là **một method riêng**, không phải override superclass private method.

```java
class Parent {
    private void secret() {
        System.out.println("Parent secret");
    }

    void perform() {
        secret();
    }
}

class Child extends Parent {
    void secret() {
        System.out.println("Child secret");
    }
}
```

`Child.secret()` không override `Parent.secret()`; `Parent.perform()` vẫn gọi private method của Parent.

### Ví dụ runnable

Lưu **`PrivateMethodDispatchDemo.java`**:

```java
class Parent {
    private void secret() {
        System.out.println("Parent secret");
    }

    void perform() {
        secret();
    }
}

class Child extends Parent {
    void secret() {
        System.out.println("Child secret");
    }
}

public class PrivateMethodDispatchDemo {
    public static void main(String[] args) {
        Child child = new Child();

        child.perform();
        child.secret();
    }
}
```

```bash
javac -encoding UTF-8 PrivateMethodDispatchDemo.java
java PrivateMethodDispatchDemo
```

Stdout:

```text
Parent secret
Child secret
```

Đây là một lý do nên tránh phát biểu “bất cứ subclass method trùng tên đều override”. **Access/inheritance** là một phần của điều kiện.

## 21. `final` method khóa override

Một instance method được đánh dấu `final` không thể bị subclass override hợp lệ.

```java
class Parent {
    final String category() {
        return "FIXED";
    }
}

class Child extends Parent {
    // String category() { return "OTHER"; }
    // SAI nếu bỏ comment: cannot override final method.
}
```

Với object `Child`, `category()` vẫn có thể được **kế thừa và gọi**; chỉ không có subclass override khác thay implementation.

`final` trên method **không** cấm overload:

```java
class Child extends Parent {
    String category(int id) {
        return "ID=" + id;
    }
}
```

`category(int)` là một signature khác, không override `category()`.

### `final class` cũng làm hierarchy kết thúc

Một class `final` không thể có subclass. Nhưng object của final class vẫn có thể được tham chiếu qua interface/superclass khác, và các calls qua interface tiếp tục làm việc theo contract.

`final` không biến instance method thành static. Nó chỉ giới hạn những implementations tương lai có thể override.

## 22. Chương trình: final method kế thừa và method khác override được

Lưu **`FinalMethodDispatchDemo.java`**:

```java
class Parent {
    final String fixed() {
        return "Parent fixed";
    }

    String flexible() {
        return "Parent flexible";
    }
}

class Child extends Parent {
    @Override
    String flexible() {
        return "Child flexible";
    }
}

public class FinalMethodDispatchDemo {
    public static void main(String[] args) {
        Parent value = new Child();

        System.out.println(value.fixed());
        System.out.println(value.flexible());
    }
}
```

```bash
javac -encoding UTF-8 FinalMethodDispatchDemo.java
java FinalMethodDispatchDemo
```

Stdout:

```text
Parent fixed
Child flexible
```

**Đừng nhầm:** Java không thực hiện một “runtime search arbitrary override” đối với method final. Contract cuối cùng của method đã được khóa, dù lời gọi vẫn có receiver instance và quyền sử dụng phụ thuộc static typing.

## 23. Abstract methods: không có implementation ở lớp cha nhưng vẫn dispatch động

Một `abstract` instance method định nghĩa một phần contract nhưng không có body ở chính lớp khai báo abstract.

```java
abstract class Notification {
    abstract String channel();
}
```

Concrete subclass triển khai:

```java
final class Email extends Notification {
    @Override
    String channel() {
        return "EMAIL";
    }
}
```

Lời gọi:

```java
Notification notification = new Email();
System.out.println(notification.channel());
```

vẫn sử dụng dynamic dispatch để thực thi `Email.channel()`. Việc `Notification.channel` không có body **không phải ngoại lệ** đối với dispatch; nó là ví dụ đặc trưng của đa hình.

**Một object không thể được tạo trực tiếp từ abstract class** bằng `new Notification()`, nhưng biến kiểu `Notification` có thể giữ subtype concrete phù hợp.

### Template Method: final điều phối, abstract bước tùy biến

```java
abstract class Task {
    final void run() {
        System.out.println("start");
        execute();
        System.out.println("finish");
    }

    protected abstract void execute();
}
```

`run()` là final, không thể bị override; nhưng `execute()` là method abstract được dispatch động theo runtime subtype.

Đây là cách dùng polymorphism có kiểm soát: base class giữ invariant trình tự, subtype chỉ thay extension point cụ thể.

## 24. Runnable Template Method: một lời gọi, nhiều implementation

Lưu **`TemplateDispatchDemo.java`**:

```java
abstract class Task {
    final void run() {
        System.out.println("start");
        execute();
        System.out.println("finish");
    }

    protected abstract void execute();
}

final class EmailTask extends Task {
    @Override
    protected void execute() {
        System.out.println("send email");
    }
}

final class FileTask extends Task {
    @Override
    protected void execute() {
        System.out.println("save file");
    }
}

public class TemplateDispatchDemo {
    public static void main(String[] args) {
        Task first = new EmailTask();
        Task second = new FileTask();

        first.run();
        second.run();
    }
}
```

```bash
javac -encoding UTF-8 TemplateDispatchDemo.java
java TemplateDispatchDemo
```

Stdout:

```text
start
send email
finish
start
save file
finish
```

Vì `run()` không override được, hai runtime objects đều chạy cùng khung `start/finish`; khi đến `execute()`, JVM chọn implementation của subtype tương ứng.

**Lưu ý:** một hook overridable có thể ném exception hoặc tạo side effects. `final run` không tự bảo đảm mọi business invariant nếu contract hook không đủ chặt.

## 25. Covariant return type: override vẫn dispatch động

Java cho phép subclass override một method với **reference return type cụ thể hơn** khi đáp ứng quy tắc *return-type substitutability*.

Ví dụ:

```java
class AnimalFactory {
    Animal create() {
        return new Animal();
    }
}

class DogFactory extends AnimalFactory {
    @Override
    Dog create() {
        return new Dog();
    }
}
```

Với `AnimalFactory factory = new DogFactory();`, lời gọi `factory.create()` dispatch tới `DogFactory.create()` và tạo `Dog`.

Nhưng tại compile time, biểu thức `factory.create()` thường được kiểm tra theo **kiểu trả về nhìn qua `AnimalFactory`**, tức `Animal`:

```java
Animal animal = factory.create(); // Hợp lệ.
// Dog dog = factory.create();     // Cần cast/kiểu factory cụ thể.
```

Covariant returns **không thay quy tắc kiểm tra kiểu tĩnh của caller**.

### Chương trình Java 17

Lưu **`CovariantReturnDemo.java`**:

```java
class Animal {
    String name() {
        return "Animal";
    }
}

class Dog extends Animal {
    @Override
    String name() {
        return "Dog";
    }
}

class Factory {
    Animal create() {
        return new Animal();
    }
}

class DogFactory extends Factory {
    @Override
    Dog create() {
        return new Dog();
    }
}

public class CovariantReturnDemo {
    public static void main(String[] args) {
        Factory general = new DogFactory();
        DogFactory specific = new DogFactory();

        Animal first = general.create();
        Dog second = specific.create();

        System.out.println(first.name());
        System.out.println(second.name());
    }
}
```

```bash
javac -encoding UTF-8 CovariantReturnDemo.java
java CovariantReturnDemo
```

Stdout:

```text
Dog
Dog
```

Hai calls thực thi `DogFactory.create()`. Khác nhau là **kiểu compile-time của expression** `general.create()` và `specific.create()`; dynamic dispatch của `name()` cũng dựa trên runtime object Dog.

## 26. Cast không thay đổi object runtime class

Giả sử:

```java
Animal animal = new Dog();
Dog dog = (Dog) animal;
```

Cả hai references có thể trỏ đến **cùng một object `Dog`**. Phép cast không clone, copy, downgrade hay “đổi nhãn lớp thực tế”.

Khi:

```java
((Animal) dog).speak();
```

Nếu `Dog` override `speak()`, lời gọi vẫn dispatch tới `Dog.speak()`. Cast receiver sang `Animal` không buộc chạy implementation của `Animal`.

Muốn gọi superclass implementation từ instance method của subclass, dùng `super.speak()` trong ngữ cảnh hợp lệ, không dùng `((Animal)this).speak()`.

### Downcast sai ném `ClassCastException`

```java
Animal animal = new Cat();
// Dog dog = (Dog) animal; // Ném ClassCastException lúc chạy.
```

Compiler có thể cho phép cast nếu hai loại có quan hệ kiểu phù hợp, nhưng runtime check từ chối nếu object thực tế không phải subtype thích hợp.

Cách an toàn hơn khi cần subtype-specific API: Java 17 có **pattern matching for `instanceof`**.

## 27. `instanceof` pattern matching trong Java 17

```java
if (animal instanceof Dog dog) {
    dog.fetch();
}
```

Điều kiện vừa kiểm tra runtime type, vừa tạo biến pattern `dog` với kiểu `Dog` trong phạm vi hợp lệ.

### Chương trình runnable

Lưu **`InstanceofDispatchDemo.java`**:

```java
class Animal {
    String sound() {
        return "unknown";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }

    String fetch() {
        return "fetching";
    }
}

class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}

public class InstanceofDispatchDemo {
    private static void inspect(Animal animal) {
        System.out.println(animal.sound());

        if (animal instanceof Dog dog) {
            System.out.println(dog.fetch());
        }
    }

    public static void main(String[] args) {
        inspect(new Dog());
        inspect(new Cat());
    }
}
```

```bash
javac -encoding UTF-8 InstanceofDispatchDemo.java
java InstanceofDispatchDemo
```

Stdout:

```text
woof
fetching
meow
```

`inspect` gọi `sound()` theo contract `Animal` và nhận behavior polymorphic; chỉ khi cần method `fetch()` không có trong Animal contract, chương trình mới kiểm tra subtype.

**Không nên lạm dụng `instanceof`** chỉ để tự dispatch mọi behavior vốn có thể đặt thành một polymorphic method trong superclass/interface. Nếu nhiều nhánh subtype xuất hiện khắp code, abstraction có thể cần thiết kế lại.

## 28. `null` không có runtime object để dispatch

Một reference variable có thể có giá trị `null`:

```java
Animal animal = null;
animal.speak(); // NullPointerException lúc chạy.
```

Compiler có thể chấp nhận lời gọi vì kiểu tĩnh `Animal` cung cấp method `speak()`, nhưng runtime không có **receiver object** hợp lệ để thực hiện instance method invocation.

Đây là vấn đề khác với compile-time method resolution:
- **Compile-time:** `Animal.speak()` là lời gọi hợp lệ.
- **Runtime:** receiver null → không thể gọi instance method trên object.

### Ví dụ runnable có bắt lỗi

Lưu **`NullReceiverDemo.java`**:

```java
class Animal {
    String sound() {
        return "sound";
    }
}

public class NullReceiverDemo {
    public static void main(String[] args) {
        Animal animal = null;

        try {
            System.out.println(animal.sound());
        } catch (NullPointerException error) {
            System.out.println("No receiver");
        }
    }
}
```

```bash
javac -encoding UTF-8 NullReceiverDemo.java
java NullReceiverDemo
```

Stdout:

```text
No receiver
```

**Không dùng NullPointerException như nhánh điều kiện thông thường** trong production nếu có thể kiểm tra null rõ ràng hoặc thiết kế non-null contract.

Một static method có thể bị gọi qua expression cú pháp giống receiver instance (`reference.staticMethod()`), nhưng đó **không** phải instance dispatch. Tránh cách gọi đó để không trộn các quy tắc null/static và dynamic dispatch.

## 29. Constructors không override động

Constructor không phải instance method có thể override. Khi viết:

```java
Animal animal = new Dog();
```

Java xác định loại object cần tạo từ **class name trong biểu thức `new Dog()`**, không “dynamic dispatch constructor” dựa trên kiểu biến `Animal`.

Trong quá trình khởi tạo object Dog, các constructors trên chuỗi superclass được gọi theo `this(...)`/`super(...)` và quy tắc initialization, nhưng **constructor không tham gia overriding polymorphism** giống `speak()`.

```java
// Animal animal = new Dog();
```

không có nghĩa runtime sẽ tùy ý tìm một constructor khác theo `Animal`.

### Bẫy nghiêm trọng: constructor superclass gọi overridable method

Dù constructors không override, chúng **có thể gọi instance methods có override**, và dynamic dispatch vẫn xảy ra **trước khi subclass hoàn tất initialization**.

## 30. Dispatch trong constructor: thấy field subclass chưa khởi tạo

Lưu **`ConstructorDispatchDemo.java`**:

```java
class Parent {
    Parent() {
        System.out.println("Parent constructor");
        describe();
    }

    void describe() {
        System.out.println("Parent describe");
    }
}

class Child extends Parent {
    private String state = initializeState();

    {
        System.out.println("Child block");
    }

    Child() {
        System.out.println("Child constructor");
    }

    private String initializeState() {
        System.out.println("Child field initializer");
        return "READY";
    }

    @Override
    void describe() {
        System.out.println("Child describe: " + state);
    }
}

public class ConstructorDispatchDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac -encoding UTF-8 ConstructorDispatchDemo.java
java ConstructorDispatchDemo
```

**Stdout chính xác:**

```text
Parent constructor
Child describe: null
Child field initializer
Child block
Child constructor
```

Từng bước:

1. `new Child()` phân bổ object có state cho Parent/Child, fields nhận **giá trị mặc định** ban đầu.
2. Constructor `Parent` chạy trước phase instance initializer của `Child`.
3. `Parent()` gọi `describe()`; vì đây là overridable instance method, runtime receiver là `Child`, nên JVM gọi `Child.describe()`.
4. `Child.describe()` đọc field `state` lúc này còn `null`.
5. Sau khi constructor Parent hoàn tất, `Child` mới chạy initializer đặt `state = "READY"`, block và constructor body.

**Nguyên tắc thiết kế:** tránh gọi overridable methods từ constructors hoặc làm lộ `this` trước khi object khởi tạo đầy đủ. Dùng private/final helpers đúng scope, constructor đơn giản, hoặc method initialization sau construction nếu cần.

Đánh dấu một method final có thể ngăn subclass override, nhưng vẫn phải xem **nó có dùng state đã sẵn sàng chưa**, không được suy ra final tự làm mọi code an toàn.

## 31. Instance method reference và lambda vẫn tuân theo receiver runtime

Method reference có nhiều dạng:

- `receiver::instanceMethod`: *bound instance method reference*, nhận receiver object có sẵn.
- `TypeName::instanceMethod`: *unbound instance method reference* khi được gán cho functional interface phù hợp, receiver đến từ tham số lời gọi.
- `TypeName::staticMethod`: static method reference, không dispatch instance như hai trường hợp trên.

Nếu `Animal.speak()` được override trong `Dog`, một lời gọi được tạo bằng method reference instance phù hợp vẫn có thể chạy override của runtime object Dog.

### Chương trình runnable

Lưu **`MethodReferenceDispatchDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.Supplier;

class Animal {
    String sound() {
        return "Animal";
    }
}

class Dog extends Animal {
    @Override
    String sound() {
        return "Dog";
    }
}

public class MethodReferenceDispatchDemo {
    public static void main(String[] args) {
        Animal animal = new Dog();

        Supplier<String> bound = animal::sound;
        Function<Animal, String> unbound = Animal::sound;

        System.out.println(bound.get());
        System.out.println(unbound.apply(animal));

        animal = new Animal();
        System.out.println(bound.get());
        System.out.println(unbound.apply(animal));
    }
}
```

```bash
javac -encoding UTF-8 MethodReferenceDispatchDemo.java
java MethodReferenceDispatchDemo
```

**Stdout:**

```text
Dog
Dog
Dog
Animal
```

Giải thích:
- `bound` được tạo từ receiver expression `animal` lúc nó trỏ tới Dog object; method reference **giữ receiver đã được đánh giá**.
- `unbound` nhận receiver qua tham số mỗi lần `apply`, nên lần cuối dùng Animal object mới.
- Biến `animal` được gán lại không thay receiver object đã ràng buộc trước đó của `bound`.
- Trong cả hai dạng instance invocation, override vẫn được lựa chọn theo runtime class của receiver dùng trong lần gọi.

**Quan trọng:** không nhầm **thời điểm lựa chọn receiver** với **quy tắc chọn implementation**.

## 32. Generic interfaces vẫn có dynamic dispatch

Generic methods/classes không làm mất polymorphism:

```java
interface Transformer<T> {
    T transform(T value);
}
```

Một concrete implementation:

```java
final class UppercaseTransformer
        implements Transformer<String> {
    @Override
    public String transform(String value) {
        return value.toUpperCase(java.util.Locale.ROOT);
    }
}
```

Client có thể dùng:

```java
Transformer<String> transformer = new UppercaseTransformer();
System.out.println(transformer.transform("java")); // JAVA
```

Compiler kiểm tra type parameter `String` của contract, và method invocation dispatch tới runtime implementation tương ứng.

### Type erasure và bridge methods

Trong Java generics, compiler có thể tạo **synthetic bridge methods** để duy trì overriding behavior sau **type erasure**.

Ví dụ `Transformer<T>.transform(T)` có erasure tương tự `transform(Object)`; implementation `UppercaseTransformer.transform(String)` cần cầu nối thích hợp để các calls qua erased interface vẫn tìm được correct implementation.

Đó là chi tiết triển khai do **compiler/JVM** hỗ trợ. Bạn không cần tự viết `transform(Object)` trong implementation; cố viết cùng tên sau erasure có thể gây name clash.

## 33. Ví dụ runnable generics dispatch

Lưu **`GenericDispatchDemo.java`**:

```java
import java.util.Locale;

interface Transformer<T> {
    T transform(T value);
}

final class UppercaseTransformer
        implements Transformer<String> {
    @Override
    public String transform(String value) {
        return value.toUpperCase(Locale.ROOT);
    }
}

final class SuffixTransformer
        implements Transformer<String> {
    @Override
    public String transform(String value) {
        return value + "!";
    }
}

public class GenericDispatchDemo {
    private static void show(
            Transformer<String> transformer, String text) {
        System.out.println(transformer.transform(text));
    }

    public static void main(String[] args) {
        show(new UppercaseTransformer(), "java");
        show(new SuffixTransformer(), "java");
    }
}
```

```bash
javac -encoding UTF-8 GenericDispatchDemo.java
java GenericDispatchDemo
```

Stdout:

```text
JAVA
java!
```

Ví dụ minh họa generic interface trong API tĩnh kết hợp **dynamic dispatch** đến hai runtime implementations. Tên/chữ ký erased và bridge behavior là chuyện compiler hỗ trợ; source client vẫn làm việc với `Transformer<String>`.

## 34. Runtime object từ collection: polymorphism trong vòng lặp

Một application thường xử lý một collection có nhiều subtypes:

```java
List<Shape> shapes = List.of(
        new Circle(...),
        new Rectangle(...),
        new Triangle(...));
```

Lời gọi:

```java
for (Shape shape : shapes) {
    System.out.println(shape.area());
}
```

mỗi lần sẽ dispatch tới implementation tương ứng theo runtime class của **object được lấy ra từ list**, miễn method `area()` thuộc contract `Shape`.

Một `List<Shape>` **không** bắt buộc mọi phần tử đều có runtime class đúng bằng `Shape`. Nó có thể giữ những subtype hợp lệ.

### Chương trình Java 17 có output ổn định

Lưu **`CollectionDispatchDemo.java`**:

```java
import java.util.List;

interface Shape {
    int area();
}

record Rectangle(int width, int height) implements Shape {
    @Override
    public int area() {
        return width * height;
    }
}

record Square(int edge) implements Shape {
    @Override
    public int area() {
        return edge * edge;
    }
}

public class CollectionDispatchDemo {
    public static void main(String[] args) {
        List<Shape> shapes = List.of(
                new Rectangle(3, 4),
                new Square(5),
                new Rectangle(2, 6));

        for (Shape shape : shapes) {
            System.out.println(shape.area());
        }
    }
}
```

```bash
javac -encoding UTF-8 CollectionDispatchDemo.java
java CollectionDispatchDemo
```

Stdout:

```text
12
25
12
```

Records là **final classes** theo Java 17, nhưng vẫn có thể implements `Shape` và cung cấp implementation interface methods. Một class final không thể bị subclass, song object của nó **vẫn tham gia polymorphism qua interface**.

## 35. Dynamic dispatch và interface segregation

Nếu client thường phải downcast từ một interface quá rộng hoặc quá hẹp:

```java
if (animal instanceof Dog dog) {
    dog.fetch();
}
```

hãy hỏi:
- `fetch` có thật sự là hành vi cần thiết của **mọi `Animal`**? Nếu có, vì sao chưa có trong contract?
- Nếu chỉ một số animals có khả năng fetch, có nên có interface `Fetchable`?
- Có nên client nhận interface `Fetchable` thay vì `Animal` khi đúng use case?
- Tập variants có đóng để dùng sealed types/pattern matching không?

Ví dụ:

```java
interface Fetchable {
    void fetch();
}

class Dog extends Animal implements Fetchable {
    @Override
    public void fetch() {
        System.out.println("fetch");
    }
}
```

Nếu service chỉ cần `fetch()`, method có thể nhận `Fetchable`. Runtime dispatch sẽ chạy implementation của receiver mà không ép client phải biết cụ thể `Dog`.

**Thiết kế contract đúng** thường mang lại lợi ích lớn hơn việc rải `instanceof`/casts để mô phỏng dynamic dispatch bằng tay.

## 36. Polymorphism không đồng nghĩa multiple inheritance

Java class chỉ có **một superclass class trực tiếp**, nhưng có thể implements **nhiều interfaces**.

```java
interface Printable {
    void print();
}

interface Savable {
    void save();
}

final class Report implements Printable, Savable {
    @Override
    public void print() {
        System.out.println("print");
    }

    @Override
    public void save() {
        System.out.println("save");
    }
}
```

`Report` là runtime concrete class cho cả hai interface roles. Một reference `Printable` có thể gọi `print()`; một reference `Savable` có thể gọi `save()`. Cả hai được chọn theo runtime implementation của object Report.

Nếu một biến chỉ có kiểu `Printable`, không được gọi `save()` qua biến đó nếu `Printable` không khai báo method ấy. Cần một reference có kiểu `Savable` phù hợp, ví dụ qua thiết kế API hoặc pattern `instanceof` khi cần.

## 37. Dispatch trong lambda callback và Strategy pattern

Một strategy interface giúp client thay algorithm mà không biết concrete class:

```java
interface DiscountPolicy {
    int apply(int amount);
}
```

Lớp service giữ một reference:

```java
final class Checkout {
    private final DiscountPolicy policy;

    Checkout(DiscountPolicy policy) {
        this.policy = policy;
    }

    int total(int amount) {
        return policy.apply(amount);
    }
}
```

`policy.apply(...)` là instance interface invocation: compiler biết contract `DiscountPolicy`, runtime chọn implementation của policy object.

Nếu chọn:
- `FixedDiscount` runtime → fixed amount behavior.
- `PercentageDiscount` runtime → percentage behavior.
- Lambda triển khai functional interface `DiscountPolicy` → chạy logic lambda phù hợp.

**Composition + interface polymorphism** là một tổ hợp rất phổ biến. Checkout **dùng** policy, không phải **là** policy.

### Chương trình runnable Strategy

Lưu **`StrategyDispatchDemo.java`**:

```java
interface DiscountPolicy {
    int apply(int amount);
}

final class FixedDiscount implements DiscountPolicy {
    private final int off;

    FixedDiscount(int off) {
        this.off = off;
    }

    @Override
    public int apply(int amount) {
        return Math.max(0, amount - off);
    }
}

final class Checkout {
    private final DiscountPolicy policy;

    Checkout(DiscountPolicy policy) {
        this.policy = policy;
    }

    int total(int amount) {
        return policy.apply(amount);
    }
}

public class StrategyDispatchDemo {
    public static void main(String[] args) {
        Checkout fixed = new Checkout(new FixedDiscount(20));
        Checkout percent = new Checkout(
                amount -> amount - amount / 10);

        System.out.println(fixed.total(100));
        System.out.println(percent.total(100));
    }
}
```

```bash
javac -encoding UTF-8 StrategyDispatchDemo.java
java StrategyDispatchDemo
```

Stdout:

```text
80
90
```

Logic callback được gọi qua interface contract. Kết quả khác vì **runtime policy objects khác nhau**, không cần subclass của Checkout. Ví dụ chỉ minh họa dispatch và strategy, chưa xử lý ràng buộc miền số tiền hoặc phần trăm trong production.

## 38. Dispatch và equality: `equals` được override có thể ảnh hưởng collection

`Object.equals(Object)` là instance method có thể được override theo các quy tắc Java. Khi gọi:

```java
Object left = new UserId("A");
Object right = new UserId("A");

left.equals(right);
```

implementation của runtime class `UserId` có thể được dùng nếu class override `equals`.

Ví dụ object identity vs value equality:

```java
record UserId(String value) {
}
```

Record sinh `equals/hashCode` theo components; với `UserId("A")` và `UserId("A")`, `equals` trả true.

**Lưu ý:** một implementation `equals` phải tuân thủ các yêu cầu reflexive, symmetric, transitive, consistent và non-null theo Java API contract để làm việc tốt với collections. Overriding sai có thể làm `HashSet`/`HashMap` cho kết quả bất ngờ.

### Ví dụ runnable

Lưu **`EqualsDispatchDemo.java`**:

```java
record UserId(String value) {
}

public class EqualsDispatchDemo {
    public static void main(String[] args) {
        Object first = new UserId("A");
        Object second = new UserId("A");
        Object third = new UserId("B");

        System.out.println(first.equals(second));
        System.out.println(first.equals(third));
        System.out.println(first == second);
    }
}
```

```bash
javac -encoding UTF-8 EqualsDispatchDemo.java
java EqualsDispatchDemo
```

Stdout:

```text
true
false
false
```

`first.equals(second)` dispatch tới behavior equality của runtime record class, trong khi `first == second` so sánh **object identity/reference values**, không gọi `equals`.

**Không nhầm:** `==` trên references không phải method invocation nên không dynamic dispatch.

## 39. `toString()` cũng là đa hình

`Object.toString()` có thể được override để biểu diễn object dễ đọc hơn.

```java
record Point(int x, int y) {
}
```

Với `Object point = new Point(2, 3);`, `point.toString()` dispatch tới implementation record tương ứng dù biến khai báo kiểu `Object`.

Có thể làm rõ hơn bằng class tự override:

```java
class Item {
    private final int id;

    Item(int id) {
        this.id = id;
    }

    @Override
    public String toString() {
        return "Item#" + id;
    }
}
```

Trong `System.out.println(object)`, Java có cơ chế chuyển object thành string và có thể gọi `toString`; việc output phụ thuộc override là một ứng dụng quen thuộc của polymorphism.

### Ví dụ runnable

Lưu **`ToStringDispatchDemo.java`**:

```java
class Item {
    private final int id;

    Item(int id) {
        this.id = id;
    }

    @Override
    public String toString() {
        return "Item#" + id;
    }
}

public class ToStringDispatchDemo {
    public static void main(String[] args) {
        Object value = new Item(7);

        System.out.println(value.toString());
        System.out.println(value);
    }
}
```

```bash
javac -encoding UTF-8 ToStringDispatchDemo.java
java ToStringDispatchDemo
```

Stdout:

```text
Item#7
Item#7
```

## 40. `getClass()` phản ánh lớp runtime nhưng không phải method override

`Object.getClass()` là `final` native instance method theo API Java. Một subclass không thể override `getClass()`.

Tuy vậy:

```java
Object value = new Dog();
System.out.println(value.getClass().getSimpleName());
```

trả tên lớp runtime của object, trong ví dụ class thông thường là `Dog`.

**Đừng nhầm:**
- `getClass()` trả thông tin về **runtime class**.
- Dynamic dispatch của method `speak()` chọn implementation override theo runtime object.
- Chỉ vì `getClass()` trả runtime class **không** có nghĩa subclass đã override `getClass()`; method này là final.

### Phân biệt `getClass()` và `instanceof`

`value instanceof Animal` trả true nếu runtime object tương thích với `Animal`, kể cả subtype.

`value.getClass() == Animal.class` chỉ true nếu runtime class **chính xác là `Animal`** trong trường hợp class object bình thường, không phải Dog subclass.

Khi viết code polymorphic, thường **không nên** kiểm tra equality của runtime class chỉ để vô hiệu hóa subtype. Hãy dựa vào contract trừ khi yêu cầu domain thực sự là exact-type check.

## 41. Java 17 sealed hierarchy: runtime dispatch trong tập subtype giới hạn

Java 17 có **sealed classes/interfaces** giúp kiểm soát những direct implementations/subclasses hợp lệ:

```java
sealed interface Result permits Success, Failure {
    String message();
}

record Success(String value) implements Result {
    @Override
    public String message() {
        return "OK " + value;
    }
}

record Failure(String reason) implements Result {
    @Override
    public String message() {
        return "ERROR " + reason;
    }
}
```

Caller:

```java
Result value = new Success("saved");
System.out.println(value.message()); // OK saved
```

vẫn dùng interface method dispatch. `sealed` giới hạn hierarchy theo kiểu được khai báo, **không đổi cơ chế chọn instance method**.

### Chương trình runnable

Lưu **`SealedDispatchDemo.java`**:

```java
sealed interface Result permits Success, Failure {
    String message();
}

record Success(String value) implements Result {
    @Override
    public String message() {
        return "OK " + value;
    }
}

record Failure(String reason) implements Result {
    @Override
    public String message() {
        return "ERROR " + reason;
    }
}

public class SealedDispatchDemo {
    public static void main(String[] args) {
        Result first = new Success("saved");
        Result second = new Failure("invalid");

        System.out.println(first.message());
        System.out.println(second.message());
    }
}
```

```bash
javac -encoding UTF-8 SealedDispatchDemo.java
java SealedDispatchDemo
```

Stdout:

```text
OK saved
ERROR invalid
```

Records là final classes, nhưng vẫn triển khai instance method của `Result` và tham gia dynamic dispatch qua interface.

## 42. JVM bytecode invocation: hiểu ý tưởng, tránh học thuộc máy móc

Compiler Java thường phát ra các dạng bytecode invocation tương ứng với ngữ nghĩa lời gọi:

| Dạng invocation | Vai trò thường gặp |
| --- | --- |
| `invokevirtual` | Gọi instance method với virtual dispatch trên class receiver |
| `invokeinterface` | Gọi instance method qua interface contract |
| `invokestatic` | Gọi static method, không có instance receiver dispatch |
| `invokespecial` | Những lời gọi đặc biệt như constructor, private method, `super` call |
| `invokedynamic` | Cơ chế dynamic call site; Java có thể dùng để triển khai lambda và các tính năng runtime khác |

**Cảnh báo quan trọng:** không nên xem bảng là quy tắc “hễ thấy `invokevirtual` thì chắc chắn method cuối cùng có override” hay “mọi Java lambda luôn tạo chính xác một class theo cách duy nhất”. JVM và javac có thể tối ưu/biểu diễn khác nhau trong giới hạn semantics.

Ở mức ngôn ngữ Java, điều cần ghi nhớ là:
- **Instance override** có thể được chọn theo runtime class.
- **Static invocation** không dispatch theo runtime object.
- **Explicit superclass invocation** chọn implementation superclass theo cách đặc biệt.
- **Overload resolution** đã diễn ra ở compile time.

Nếu muốn xem bytecode của chương trình runnable đã biên dịch, có thể dùng:

```bash
javap -c DynamicDispatchDemo
```

Lệnh này in bytecode disassembly; bài không đưa stdout cụ thể của `javap` vì output có thể chứa thông tin phụ thuộc compiler và chi tiết class file. Dùng nó để nghiên cứu, không làm thay đổi rules của Java source.

## 43. JVM có thể tối ưu dispatch nhưng không đổi kết quả

JIT compiler của JVM có thể:
- **Inline** method implementations khi có bằng chứng phù hợp.
- **Devirtualize** call sites khi biết runtime classes có thể xuất hiện.
- Dùng profiling và speculative optimizations để tăng hiệu năng.
- Recompile/deoptimize khi những giả định tối ưu thay đổi.

Nhưng các tối ưu phải bảo toàn **observable behavior** của chương trình theo Java semantics.

**Không nên khẳng định**:
- “Gọi qua interface luôn chậm hơn gọi qua concrete class.”
- “Thêm `final` chắc chắn làm mọi method call nhanh hơn.”
- “Dynamic dispatch luôn tạo reflection lookup bằng tên method ở mỗi lần gọi.”

Những phát biểu đó không mô tả chính xác Java/JVM hiện đại. Hãy chọn thiết kế dựa vào API, LSP, extensibility và kiểm thử; nếu performance quyết định, đo bằng benchmark đáng tin trong workload thật.

## 44. Dynamic dispatch không phải reflection

Reflection có thể tìm method theo metadata ở runtime, ví dụ dùng `Class.getMethod` và `Method.invoke`. Đây là một **cơ chế API khác** với lời gọi `animal.speak()` thông thường.

Một lời gọi:

```java
animal.speak();
```

được compiler kiểm tra kiểu và ràng buộc phương thức ở compile time theo quy tắc Java; JVM thực hiện instance dispatch thích hợp. Chương trình **không cần** tự viết reflection để polymorphism hoạt động.

Reflection có các đặc tính khác:
- Có thể truy xuất metadata theo tên.
- Có checked exceptions/`InvocationTargetException` khi dùng Method.invoke.
- Chịu ràng buộc accessibility/module system.
- Có chi phí và cơ chế vận hành khác.

**Đừng dùng reflection chỉ để “gọi đúng method của subclass”** khi interface/overriding là đủ.

## 45. Những giới hạn của runtime polymorphism

Dynamic dispatch không tự giải quyết mọi nhu cầu thiết kế:

**Không hỗ trợ**:
- Gọi method chỉ tồn tại ở subtype qua biến base nếu không có cast/contract tương ứng.
- Chọn overload chỉ vì **runtime class của arguments** cụ thể hơn.
- Thay dynamic class của object đang tồn tại.
- Phá ràng buộc access modifier.
- Override final instance method hoặc private method như một inherited override.
- Dispatch static method/field theo runtime object.
- Tự làm object mutable trở nên immutable.
- Tự xử lý null receiver.

Khi thấy code đầy casts hoặc ``if (obj instanceof X)``, hãy xem abstraction đã biểu diễn đúng **hành vi chung** chưa. Nhưng vẫn có những bài toán như serialization đa loại, visitor, pattern matching trên sealed types, hoặc domain-specific routing mà kiểm tra subtype có chủ đích là hợp lý.

## 46. Những lỗi Java thường gặp và cách giải

| Triệu chứng | Nguyên nhân thật | Hướng sửa |
| --- | --- | --- |
| `Animal a = new Dog(); a.fetch();` lỗi biên dịch | Kiểu `Animal` không có method `fetch()` | Dùng interface đúng role, downcast an toàn hoặc đổi API |
| Gọi `Animal a = new Dog(); a.speak();` mà kỳ vọng Animal version | Instance override dispatch theo runtime Dog | Gọi `super.speak()` trong subclass khi cần |
| `obj.staticMethod()` gọi method superclass | Static hiding chọn theo static type | Gọi `ClassName.staticMethod()` rõ ràng |
| `obj.field` đọc field superclass | Field access không virtual | Dùng getter polymorphic hoặc tránh field hiding |
| Overload chọn `handle(Animal)` dù argument là Dog runtime | Overload resolution dùng static type của argument | Điều chỉnh signature/cast có chủ đích, hoặc thiết kế polymorphism |
| Bỏ `@Override` để tránh lỗi override final | Annotation không phải nguyên nhân | Không override final method |
| Subclass private method trùng tên nhưng parent vẫn chạy private version | Private method không được override theo kiểu kế thừa thường | Dùng protected/public contract nếu thực sự cần override |
| `((Parent)this).work()` cứ gọi Child override | Cast không đổi runtime class và vẫn virtual dispatch | Dùng `super.work()` trong instance method hợp lệ |
| `Dog dog = (Dog) new Cat();` gây lỗi | Runtime object không tương thích Dog | `instanceof` pattern hoặc đổi model |
| Receiver null gây `NullPointerException` | Không có runtime object để invoke | Kiểm tra non-null hoặc thay contract |
| Constructor Parent gọi Child override đọc field null | Dispatch chạy trước Child initializer | Không gọi overridable method từ constructor |
| Interface default bị method class ưu tiên | Class implementation wins theo resolution rules | Hiểu hierarchy hoặc override rõ |
| Hai unrelated default methods xung đột | Không thể chọn mặc định chỉ dựa thứ tự implements | Override giải quyết tường minh |
| Method return type covariant nhưng base call vẫn type Animal | Compile-time expression type theo base signature | Dùng subtype reference/cast khi cần |
| Generic bridge method gây bối rối khi decompile | Type erasure cần giữ overriding | Dựa vào source generic contract; đừng tự viết bridge |
| Nghĩ final class không tham gia đa hình | Final chỉ ngăn subclass của class đó | Có thể implements interface và dispatch qua interface |
| Nghĩ runtime dispatch bằng reflection từng lần | JVM virtual invocation có cơ chế riêng | Không cần reflection cho polymorphism |
| Dùng `instanceof` khắp code để gọi behavior | Abstraction có thể đặt sai nơi | Đưa common behavior vào interface/base method |
| Thấy hai methods cùng tên nên nghĩ override | Có thể overload/hiding/private method | Xem signature, static/instance, visibility, return, exception |
| Tưởng compiler không quan tâm overload vì có runtime type | Compile time giải quyết trước invocation | Phân biệt compile-time và runtime stages |

## 47. Phương pháp tự giải bài “in ra gì?”

Khi gặp code đa hình, làm theo **thứ tự cố định**:

1. **Vẽ class/interface hierarchy**. Đánh dấu `extends`, `implements`.
2. **Xác định kiểu tĩnh của receiver expression**. Ví dụ `Animal a` → `Animal`.
3. **Xác định runtime object của receiver** tại điểm gọi. Ví dụ `a = new Dog()` → Dog.
4. **Nhìn tên method và arguments**. Có nhiều overload không? Kiểu tĩnh từng argument là gì?
5. **Chọn signature hợp lệ ở compile time**, kiểm tra access và applicable overloads.
6. **Xem loại member**: static method? instance method? field? constructor? special `super` call?
7. **Nếu instance method override-được**, đi theo runtime class để chọn implementation override phù hợp; có thể kế thừa implementation từ superclass trung gian.
8. **Đọc body implementation được gọi**; bên trong có thể lại gọi virtual methods khác.
9. **Kiểm tra `null`/cast/runtime exceptions**, đặc biệt trong constructors và initializers.
10. **Viết stdout từng dòng** dựa trên thứ tự thực thi và dấu xuống dòng của `print/println`.

### Mẫu bảng cho người học

| Expression | Static receiver type | Runtime receiver | Signature compile-time | Implementation runtime |
| --- | --- | --- | --- | --- |
| `a.speak()` | `Animal` | `Dog` | `speak()` của contract Animal | `Dog.speak()` |
| `a.toString()` | `Animal` | `Dog` | `toString()` kế thừa từ Object | Override theo runtime object nếu có |
| `a.staticLabel()` | `Animal` | `Dog` | Static label của Animal | Không runtime virtual dispatch |
| `a.field` | `Animal` | `Dog` | Field của Animal | Field access không dispatch |
| `handler.handle(a)` | `Handler` | `SpecialHandler` | `handle(Animal)` vì a static Animal | `SpecialHandler.handle(Animal)` nếu override |
| `((Animal) dog).speak()` | `Animal` sau cast | `Dog` | `speak()` nhìn qua Animal | `Dog.speak()` |
| `super.speak()` trong Dog | Special super invocation | `Dog` object | Superclass method chọn đặc biệt | Implementation superclass được chỉ định |

## 48. Bài tập 1 — Cùng kiểu biến, object khác nhau

```java
class A {
    String value() { return "A"; }
}

class B extends A {
    @Override
    String value() { return "B"; }
}

class C extends A {
    @Override
    String value() { return "C"; }
}

A x = new B();
A y = new C();
System.out.println(x.value());
System.out.println(y.value());
```

**Đáp án:**

```text
B
C
```

Method signature nhìn qua A giống nhau, runtime receivers khác nhau nên implementation khác nhau.

## 49. Bài tập 2 — Subclass không override

```java
class A {
    String value() { return "A"; }
}

class B extends A {
    @Override
    String value() { return "B"; }
}

class C extends B {
}

A ref = new C();
System.out.println(ref.value());
```

**Đáp án:** `B`. `C` kế thừa implementation `B.value()`, không tự buộc JVM quay về `A.value()`.

## 50. Bài tập 3 — Overload theo đối số

```java
class Animal { }
class Dog extends Animal { }

class Printer {
    void show(Animal a) { System.out.println("Animal"); }
    void show(Dog d) { System.out.println("Dog"); }
}

Animal animal = new Dog();
new Printer().show(animal);
```

**Đáp án:** `Animal`. Compiler chọn overload theo **kiểu tĩnh của argument `animal`**, không runtime Dog.

## 51. Bài tập 4 — Overload kết hợp override

```java
class A { }
class B extends A { }

class Parent {
    String work(A value) { return "P-A"; }
    String work(B value) { return "P-B"; }
}

class Child extends Parent {
    @Override
    String work(A value) { return "C-A"; }
}

Parent p = new Child();
A arg = new B();
System.out.println(p.work(arg));
```

**Đáp án:** `C-A`. Overload signature `work(A)` được compiler chọn vì `arg` có static type A; override `Child.work(A)` được gọi vì receiver object runtime Child.

## 52. Bài tập 5 — Static hiding

```java
class Parent {
    static String name() { return "Parent"; }
}

class Child extends Parent {
    static String name() { return "Child"; }
}

Parent ref = new Child();
System.out.println(ref.name());
```

**Đáp án:** `Parent`. Static method không virtual-dispatch theo Child runtime; tránh gọi qua instance reference trong code production.

## 53. Bài tập 6 — Field hiding

```java
class Parent {
    String label = "P";
}

class Child extends Parent {
    String label = "C";
}

Parent ref = new Child();
System.out.println(ref.label);
System.out.println(((Child) ref).label);
```

**Đáp án:**

```text
P
C
```

Field lookup dựa vào kiểu tĩnh của expression, không theo runtime class.

## 54. Bài tập 7 — Cast không đổi dispatch

```java
class Parent {
    String name() { return "P"; }
}

class Child extends Parent {
    @Override
    String name() { return "C"; }
}

Child child = new Child();
System.out.println(((Parent) child).name());
```

**Đáp án:** `C`. Cast thay static view, không thay runtime object Child.

## 55. Bài tập 8 — `super` là lựa chọn đặc biệt

```java
class Parent {
    String name() { return "P"; }
}

class Child extends Parent {
    @Override
    String name() {
        return super.name() + "C";
    }
}

System.out.println(new Child().name());
```

**Đáp án:** `PC`. Runtime chọn Child override; bên trong `super.name()` gọi implementation Parent.

## 56. Bài tập 9 — Private method

```java
class Parent {
    private String name() { return "P"; }

    String read() { return name(); }
}

class Child extends Parent {
    String name() { return "C"; }
}

System.out.println(new Child().read());
```

**Đáp án:** `P`. `Child.name()` không override private `Parent.name()`. `Parent.read()` gọi private method Parent.

## 57. Bài tập 10 — Constructor virtual call

```java
class Parent {
    Parent() { show(); }
    void show() { System.out.println("P"); }
}

class Child extends Parent {
    int number = 5;

    @Override
    void show() {
        System.out.println(number);
    }
}

new Child();
```

**Đáp án:** `0`. Runtime chọn Child override khi Parent constructor gọi show, nhưng initializer `number = 5` chưa chạy.

## 58. Bài tập 11 — Final method

```java
class Parent {
    final String type() { return "fixed"; }
}

class Child extends Parent {
}

System.out.println(new Child().type());
```

**Đáp án:** `fixed`. Final method có thể được kế thừa/gọi nhưng không override được.

## 59. Bài tập 12 — Interface runtime dispatch

```java
interface Task {
    String run();
}

class EmailTask implements Task {
    public String run() { return "email"; }
}

class FileTask implements Task {
    public String run() { return "file"; }
}

Task task = new EmailTask();
System.out.println(task.run());

task = new FileTask();
System.out.println(task.run());
```

**Đáp án:**

```text
email
file
```

Biến kiểu interface trỏ tới runtime implementations khác nhau; lời gọi được dispatch tương ứng.

## 60. Bài tập 13 — Default interface và class wins

```java
interface Label {
    default String get() { return "I"; }
}

class Parent {
    public String get() { return "P"; }
}

class Child extends Parent implements Label {
}

Label value = new Child();
System.out.println(value.get());
```

**Đáp án:** `P`. Implementation class method được ưu tiên so với default method trong trường hợp hợp lệ này.

## 61. Bài tập 14 — Covariant return

```java
class Parent {
    Number count() { return 1; }
}

class Child extends Parent {
    @Override
    Integer count() { return 2; }
}

Parent ref = new Child();
Number value = ref.count();
System.out.println(value);
```

**Đáp án:** `2`. Runtime chọn Child override trả Integer, nhưng compile-time return type nhìn qua Parent là Number.

## 62. Bài tập 15 — Method reference đã gắn receiver

```java
class Parent {
    String label() { return "P"; }
}

class Child extends Parent {
    @Override
    String label() { return "C"; }
}

Parent x = new Child();
java.util.function.Supplier<String> f = x::label;
x = new Parent();

System.out.println(f.get());
System.out.println(x.label());
```

**Đáp án:**

```text
C
P
```

`f` giữ receiver object Child lúc tạo method reference; gán lại biến `x` không thay bound receiver.

## 63. Bài tập 16 — Kiểu compile-time không biết method subclass

```java
class Animal {
    void speak() { }
}

class Dog extends Animal {
    void fetch() { }
}

Animal animal = new Dog();
// animal.fetch();
```

**Đáp án:** Nếu bỏ comment, lỗi biên dịch vì `fetch` không có trong contract nhìn qua `Animal`. Có thể dùng `instanceof Dog dog` để gọi `dog.fetch()` hoặc thiết kế interface `Fetchable` nếu use case yêu cầu.

## 64. Bài tập 17 — `null` và runtime receiver

```java
class Animal {
    String sound() { return "A"; }
}

Animal value = null;
// value.sound();
```

**Đáp án:** Nếu bỏ comment và chạy, phát sinh `NullPointerException` (khi lời gọi instance được đánh giá) vì receiver null. Đây không phải lỗi compiler khi method hợp lệ về kiểu.

## 65. Bài tập 18 — Record implements interface

```java
interface Identified {
    String id();
}

record User(String id) implements Identified {
}

Identified ref = new User("A");
System.out.println(ref.id());
```

**Đáp án:** `A`. Record final vẫn cung cấp implementation `id()` theo record component accessor và tham gia interface method dispatch.

## 66. Checklist kiểm tra chương trình đa hình

1. Đã xác định **kiểu khai báo** của receiver expression chưa?
2. Đã xác định **runtime class** của object receiver tại điểm gọi chưa?
3. Method có **hiện diện/được truy cập qua static type** của receiver không?
4. Có **overloads** nào cùng tên không? Đã chọn signature bằng **kiểu tĩnh arguments** chưa?
5. Member là **instance method**, **static method** hay **field**?
6. Nếu là instance, có override hợp lệ theo signature/access/return/exception rules không?
7. Runtime class có override riêng hay kế thừa override của superclass trung gian?
8. Method có **`final`** không? Nếu có, subclass có bị khóa override?
9. Method ở superclass có **`private`** không? Đừng suy ra method cùng tên của subclass là override.
10. Có `super.method()`/`Interface.super.method()` special invocation không?
11. Có một **interface default method** cạnh tranh với class method hoặc interface default khác không?
12. **Cast** có được dùng chỉ để thay kiểu nhìn thấy không? Nhớ cast không đổi object.
13. Có **null receiver** hoặc downcast không hợp lệ gây exception runtime không?
14. Có **constructor gọi overridable method** khi subclass chưa hoàn tất initialization không?
15. Có generic type erasure/covariant return làm syntax compile-time khác phần runtime bridge?
16. Có gọi static methods **qua object reference** gây nhầm về runtime dispatch không?
17. Có field hiding cùng tên giữa các classes không? Nên dùng methods/encapsulation?
18. Có đang dùng `instanceof` lặp lại để tự điều phối hành vi mà polymorphism giải quyết được không?
19. Có cần interface role nhỏ hơn để tránh downcast subclass-specific API không?
20. Có kỳ vọng performance sai rằng virtual dispatch luôn chậm/luôn reflection không?
21. Đã kiểm tra **stdout** từng dòng với cả static resolution và dynamic implementation chưa?
22. Khi thay implementation bằng subclass mới, hợp đồng LSP của base/interface có còn đúng không?

## Ghi nhớ

- **Kiểu tĩnh quyết định API/chữ ký method hợp lệ tại compile time**; **runtime class của receiver** quyết định implementation của **instance method override**.
- **Overloading** được chọn theo kiểu tĩnh của đối số; runtime type của argument **không** tự khiến compiler chọn overload khác.
- **Instance methods** qua superclass/interface tham chiếu có thể dispatch tới override trong concrete subtype, kể cả khi subtype không viết override riêng mà kế thừa từ lớp trung gian.
- **Static methods** dùng hiding/static binding, **fields** dùng hiding/field resolution theo static type; không polymorphic như instance methods.
- **Cast** không thay runtime object; cast lên superclass không ép gọi method implementation superclass. `super.method()` là cơ chế riêng.
- **Private** methods không override theo quan hệ kế thừa thông thường; **final** methods khóa override; **abstract** methods cần implementation hợp lệ.
- **Default interface methods**, **covariant returns**, **generic bridge methods**, **record/sealed types** đều phải tuân thủ mô hình contract + runtime invocation của Java.
- **Constructor không override**, nhưng một overridable method gọi từ constructor có thể dispatch sang subclass trước khi subclass state sẵn sàng.
- **Null receiver** không có object để invoke; dynamic dispatch không bỏ qua access control hay compile-time type checking.
- Viết code đa hình theo một **interface/base contract có ý nghĩa**, giữ LSP và dùng composition/strategies khi muốn thay cộng tác viên; đừng thay thế polymorphism bằng một mạng lưới casts/`instanceof` không cần thiết.
