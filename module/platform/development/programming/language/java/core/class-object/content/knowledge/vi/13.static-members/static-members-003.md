# Phương thức static và lời gọi qua tên lớp trong Java

## 1. Phương thức `static` là gì?

Trong Java, **phương thức static** (*static method*, hay phương thức lớp) là method được khai báo với modifier `static`. Nó gắn với **kiểu khai báo**, thay vì được gọi dựa trên một **đối tượng nhận lời gọi (receiver object)** như instance method.

Cú pháp thông thường:

```java
class ClassName {
    static ReturnType methodName(ParameterType parameter) {
        // Xử lý không cần receiver ngầm của ClassName.
        return /* giá trị phù hợp */;
    }
}
```

Đây là **khuôn mẫu cú pháp minh họa**, không phải mã hoàn chỉnh để biên dịch nguyên văn.

Điểm khác biệt trong cách gọi:

- **Static method**: `ClassName.methodName(arguments)` — cách gọi **khuyến nghị**, cho biết method thuộc API của kiểu.
- **Instance method**: `object.methodName(arguments)` — gọi hành vi trên một object cụ thể.
- Với static method, **không tồn tại `this` ngầm** của lớp khai báo method.
- Static method có thể truy cập **static members** phù hợp, dùng tham số, tạo object hoặc truy cập instance member qua **tham chiếu object tường minh**.
- Modifier `static` **không có nghĩa method chỉ chạy một lần**. Một static method có thể được gọi hàng nghìn lần; mỗi lời gọi thực thi thân method theo ngữ nghĩa Java.

Ví dụ quen thuộc: `Math.max(3, 7)`, `Integer.parseInt("42")`, `Arrays.sort(array)`, `Objects.requireNonNull(value)` đều là các lời gọi static method qua tên lớp. Việc gọi không cần tạo một `Math`, `Integer`, `Arrays` hoặc `Objects` instance.

**Ghi nhớ:** phương thức static là **hành vi được truy cập qua kiểu**, không phải “phương thức chỉ dùng biến static” hay “phương thức được chạy tự động”.

## 2. Khai báo và gọi một static method hoàn chỉnh

Tệp **`StaticMethodBasicsDemo.java`**:

```java
class Calculator {
    static int add(int a, int b) {
        return a + b;
    }

    static int square(int number) {
        return number * number;
    }

    static void printTitle() {
        System.out.println("Calculator");
    }
}

public class StaticMethodBasicsDemo {
    public static void main(String[] args) {
        Calculator.printTitle();

        int total = Calculator.add(10, 5);
        int result = Calculator.square(4);

        System.out.println("total=" + total);
        System.out.println("square=" + result);
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac StaticMethodBasicsDemo.java
java StaticMethodBasicsDemo
```

**Standard output:**

```text
Calculator
total=15
square=16
```

Giải thích:

1. `Calculator` là một class có ba static methods.
2. `Calculator.printTitle()` gọi method có kiểu trả về `void`, thực hiện in thông báo.
3. `Calculator.add(10,5)` trả một `int`; caller gán kết quả cho `total`.
4. `Calculator.square(4)` tính bình phương đối số.
5. Không có lệnh `new Calculator()` nào trong `main`; **không cần một Calculator object** để gọi ba static methods.

Thân static method vẫn có thể khai báo biến cục bộ, dùng `if`, vòng lặp, ném exception, gọi method khác và trả kết quả như một method bình thường. Điểm khác là **không có receiver `this` cho class chứa method**.

## 3. Vì sao nên viết `ClassName.method()`?

Java cho phép một số cú pháp gọi static method qua biểu thức object, ví dụ `calculator.add(...)`, nhưng điều đó **không biến static method thành instance method**. Viết `Calculator.add(...)` thường tốt hơn vì:

1. **Đúng ý nghĩa**: method thuộc class, không phụ thuộc danh tính của `calculator`.
2. **Dễ đọc**: người xem thấy ngay đây là static API.
3. **Tránh hiểu nhầm về đa hình**: static methods bị **hiding**, không override theo dynamic dispatch.
4. **Tránh đánh giá biểu thức qualifier vô ích**: nếu gọi qua một biểu thức có side effect, biểu thức ấy vẫn có thể được đánh giá dù kết quả object không được dùng làm receiver static.
5. **Dễ tìm API**: IDE và code review phân biệt rõ instance behavior với utility/factory static.

Ví dụ:

```java
Calculator calculator = new Calculator();

System.out.println(calculator.add(2, 3)); // Biên dịch được, không khuyến nghị.
System.out.println(Calculator.add(2, 3)); // Nên dùng.
```

Đây là **đoạn mã minh họa trong method**; giả sử `Calculator` là class có static `add` như ở mục trước. Hai dòng đều trả 5, nhưng ở dòng đầu `calculator` **không** được truyền vào `add` thành `this`.

Một số IDE/compiler warning gọi đây là truy cập static member bằng instance reference. Hãy sửa cho đúng ý nghĩa thay vì coi đây là lỗi cú pháp bắt buộc.

## 4. Phương thức static khác instance method ở đâu?

| Tiêu chí | Static method | Instance method |
| --- | --- | --- |
| Khai báo | Có `static` | Không có `static` |
| Lời gọi rõ nghĩa | `TypeName.method()` | `reference.method()` |
| Receiver object của class khai báo | **Không có** | Có object nhận lời gọi |
| `this` trực tiếp trong thân method | Không được | Có trong instance context thích hợp |
| Truy cập instance field bằng tên đơn | Không nếu không có receiver phù hợp | Có thể dùng field của `this` |
| Truy cập static field | Có, theo quyền truy cập | Có, nhưng nên dùng tên lớp khi cần rõ nghĩa |
| Override và runtime dispatch | **Không override** như instance method; có thể **hide** | Có thể override và dispatch động theo object |
| Tham gia interface contract | Static method không triển khai instance abstract method | Instance method có thể triển khai interface method |
| Cần tạo instance để gọi | Không | Có một receiver hợp lệ khi gọi |
| Mục đích phổ biến | Utility, factory, chuyển đổi, xử lý dựa trên input | Hành vi của đối tượng và state riêng |

### Ví dụ một lớp chứa cả hai loại method

```java
class Student {
    private final String name;
    private int score;
    private static int created;

    Student(String name) {
        this.name = name;
        created++;
    }

    void addScore(int points) {
        this.score += points;
    }

    String summary() {
        return name + ":" + score;
    }

    static int createdCount() {
        return created;
    }
}
```

Với `Student first = new Student("An");`:

- `first.addScore(10)`: **instance method**, receiver là `first`, sửa `score` của object này.
- `first.summary()`: **instance method**, đọc state của object nhận lời gọi.
- `Student.createdCount()`: **static method**, đọc static field `created` dùng chung cho lớp.
- `createdCount` không được tự tham chiếu `this.score` vì không có object cụ thể được chọn.

**Không nên** chuyển `score` thành static chỉ để static method đọc được. Nếu `score` thuộc riêng mỗi Student, giữ nó là instance field và cung cấp instance method hoặc truyền Student object vào static method khi hợp lý.

## 5. Static method không có `this`, nhưng vẫn thao tác được trên object

Một ngộ nhận thường gặp: “Trong static method không dùng `this` được, vậy static method không thể xử lý object”. Sai. Nó chỉ **không có object hiện tại ngầm định**; bạn có thể cung cấp object bằng tham số.

Ví dụ đầy đủ, tệp **`StaticAndInstanceDemo.java`**:

```java
class Box {
    private int value;

    Box(int value) {
        this.value = value;
    }

    void add(int amount) {
        this.value += amount;
    }

    int value() {
        return value;
    }

    static void addTo(Box target, int amount) {
        target.add(amount);
    }

    static int sum(Box left, Box right) {
        return left.value + right.value;
    }
}

public class StaticAndInstanceDemo {
    public static void main(String[] args) {
        Box a = new Box(10);
        Box b = new Box(20);

        a.add(2);
        Box.addTo(b, 5);

        System.out.println(a.value());
        System.out.println(b.value());
        System.out.println(Box.sum(a, b));
    }
}
```

```bash
javac StaticAndInstanceDemo.java
java StaticAndInstanceDemo
```

```text
12
25
37
```

**Cơ chế:**

- `a.add(2)`: instance method `add` có `this == a`, sửa object `a` từ 10 thành 12.
- `Box.addTo(b, 5)`: static method **không có `this`**; tham số `target` giữ giá trị tham chiếu tới object `b`, rồi gọi `target.add(5)` để sửa b từ 20 thành 25.
- `Box.sum(a,b)`: static method nhận **hai tham chiếu** và đọc state của hai object để trả 37.
- Các instance fields `value` vẫn riêng cho mỗi Box; việc một static method truy cập chúng **không làm field biến thành static**.

Lưu ý: `Box.addTo(null, 5)` trong ví dụ sẽ gặp `NullPointerException` khi cố gọi instance method trên `target` null. Static method có thể được gọi mà không có receiver của Box, nhưng **các object mà nó tự sử dụng** vẫn phải thỏa điều kiện riêng.

## 6. Lỗi biên dịch thường gặp: tham chiếu instance member trực tiếp trong static context

Xét khai báo cố ý sai:

```java
// class User {
//     String name = "guest";
//
//     static void show() {
//         System.out.println(this.name); // Sai: không có this.
//     }
// }
```

Vị trí `this.name` nằm trong thân static method nên compiler không thể chọn một `User` nào làm “đối tượng hiện tại”.

Ngay cả khi bỏ `this`, viết `System.out.println(name);` vẫn sai nếu `name` là **instance field**: không có receiver ngầm thích hợp.

Tương tự:

```java
class User {
    String name = "guest";

    void showName() {
        System.out.println(this.name);
    }

    static void show(User user) {
        // showName(); // Sai: instance method không có receiver.
        user.showName(); // Đúng nếu user không null.
    }
}
```

Đây là **khai báo biên dịch được**, vì dòng cố ý sai đã được comment. Method `show(User)` static nên dùng tham số `user` làm receiver tường minh cho instance method `showName()`.

### Ba hướng sửa theo bản chất nhu cầu

1. Nếu hành vi phụ thuộc state của **đối tượng hiện tại**, chuyển method thành **instance method** và gọi qua object.
2. Nếu hành vi xử lý **đối tượng do caller chọn**, giữ static method, nhận object làm **tham số** rồi truy cập qua tham chiếu ấy.
3. Nếu dữ liệu/hành vi thực sự thuộc **cấp lớp**, dùng static field hoặc static utility mà không cần instance.

Đừng chỉ thêm `static` vào mọi field để làm compiler hết báo lỗi; cách đó có thể vô tình khiến trạng thái vốn thuộc từng object bị **chia sẻ giữa mọi instances**.

## 7. `main` thường là static method

Trong cách viết chương trình Java truyền thống:

```java
public static void main(String[] args) {
    // Điểm vào chương trình.
}
```

`main` là static method được Java launcher gọi theo hợp đồng entry point tương ứng. Vì nó static, trong thân `main` **không có `this` của class chương trình**. Nó có thể gọi các static helpers trực tiếp nếu cùng class hoặc bằng tên lớp:

Tệp **`MainStaticDemo.java`**:

```java
public class MainStaticDemo {
    private int counter;

    static String heading() {
        return "Static Demo";
    }

    void increase() {
        counter++;
    }

    int counter() {
        return counter;
    }

    public static void main(String[] args) {
        System.out.println(MainStaticDemo.heading());

        // increase();     // Sai: thiếu receiver.
        // this.increase(); // Sai: main không có this.

        MainStaticDemo object = new MainStaticDemo();
        object.increase();
        object.increase();
        System.out.println(object.counter());
    }
}
```

```bash
javac MainStaticDemo.java
java MainStaticDemo
```

```text
Static Demo
2
```

Trong `main`:

- `MainStaticDemo.heading()` là lời gọi static rõ nghĩa.
- `object.increase()` là lời gọi instance trên object được tạo tường minh.
- `object.counter()` đọc field riêng của object.

Lớp có method `main` static **vẫn có thể chứa instance methods/fields**; không có quy tắc mọi method trong class chứa `main` đều phải static.

## 8. Gọi static method từ cùng class: tên đơn hay tên lớp?

Trong thân một class, Java thường cho gọi static method bằng tên đơn:

```java
class TextUtils {
    static String normalized(String input) {
        return input.trim().toLowerCase();
    }

    static boolean matches(String left, String right) {
        return normalized(left).equals(normalized(right));
    }
}
```

Đây là **khai báo class**, không có `main`. Tại `matches`, `normalized(left)` và `normalized(right)` phân giải thành static method cùng class. Chúng cũng có thể được viết `TextUtils.normalized(left)` để nhấn mạnh nơi khai báo.

**Quy tắc phong cách:**

- Trong cùng class, tên đơn như `normalized(...)` thường ngắn và dễ đọc khi không có xung đột.
- Khi gọi **class khác**, ưu tiên `ClassName.method(...)`.
- Nếu xảy ra shadowing/name resolution làm mã khó hiểu, dùng qualifier rõ ràng như `TextUtils.normalized(...)`.
- Đối với static fields dễ nhầm với instance fields, dùng `ClassName.FIELD` thường giúp làm rõ rằng dữ liệu thuộc cấp lớp.

Không có yêu cầu phải viết tên lớp trước **mọi** lời gọi static ở cùng class; điều quan trọng là biểu đạt chính xác và nhất quán.

## 9. Chương trình dùng static utility và static field

Tệp **`TicketUtilsDemo.java`**:

```java
class Ticket {
    private final String code;
    private static int count;

    Ticket(String code) {
        this.code = code;
        count++;
    }

    String code() {
        return code;
    }

    static int createdCount() {
        return count;
    }

    static String formatCode(String raw) {
        return raw.trim().toUpperCase();
    }
}

public class TicketUtilsDemo {
    public static void main(String[] args) {
        Ticket first = new Ticket(Ticket.formatCode(" a-1 "));
        Ticket second = new Ticket(Ticket.formatCode(" b-2 "));

        System.out.println(first.code());
        System.out.println(second.code());
        System.out.println("created=" + Ticket.createdCount());
    }
}
```

```bash
javac TicketUtilsDemo.java
java TicketUtilsDemo
```

```text
A-1
B-2
created=2
```

- `formatCode` là static: chỉ dựa vào input `raw`, không dùng state của một Ticket cụ thể.
- Constructor `Ticket` là **instance construction**, tăng static count khi tạo mỗi object.
- `createdCount` static: trả tổng số object Ticket được constructor này tạo trong chương trình minh họa.
- `first.code()` và `second.code()` instance: mỗi object có code riêng.

Nếu dùng `count++` trong chương trình đa luồng, cần đồng bộ/`AtomicInteger` khi muốn đếm chính xác. Modifier `static` làm biến dùng chung, **không tự tạo thread safety**.

## 10. Static method có thể gọi qua biến `null`: hợp lệ nhưng gây hiểu nhầm

Xét:

```java
class Utility {
    static String message() {
        return "shared";
    }
}
```

Một đoạn code trong method:

```java
Utility ref = null;

System.out.println(Utility.message()); // Cách nên dùng.
System.out.println(ref.message());     // Biên dịch được; không khuyến nghị.
```

Với static method, biểu thức `ref.message()` được biên dịch thành lời gọi static theo kiểu tĩnh `Utility`, **không sử dụng `ref` như receiver instance**. Do vậy việc `ref` null ở đoạn này **không** gây `NullPointerException` chỉ bởi lời gọi static method.

Trái lại, `ref.instanceMethod()` nếu `instanceMethod` là instance method sẽ cần receiver object và gây `NullPointerException` khi ref null, trừ khi còn có ngoại lệ khác xảy ra sớm hơn trong đánh giá biểu thức/đối số.

### Ví dụ runnable so sánh null static call và instance call

Tệp **`NullStaticCallDemo.java`**:

```java
class Greeter {
    static String shared() {
        return "shared";
    }

    String personal() {
        return "personal";
    }
}

public class NullStaticCallDemo {
    public static void main(String[] args) {
        Greeter greeter = null;

        System.out.println(greeter.shared());

        try {
            System.out.println(greeter.personal());
        } catch (NullPointerException ex) {
            System.out.println("instance receiver is null");
        }
    }
}
```

```bash
javac NullStaticCallDemo.java
java NullStaticCallDemo
```

```text
shared
instance receiver is null
```

**Kết luận:** đây là một hành vi ngôn ngữ để hiểu **static invocation khác virtual invocation**; **không dùng `nullRef.staticMethod()` làm phong cách lập trình**. Viết `Greeter.shared()` vừa an toàn về ý nghĩa vừa giúp người đọc tránh suy luận nhầm có receiver.

## 11. Biểu thức trước dấu chấm có thể vẫn được đánh giá

Lời gọi static qua một biểu thức không dùng đối tượng trả về làm receiver, nhưng **biểu thức đó vẫn có thể được đánh giá** và gây side effect.

Tệp **`StaticQualifierEvaluationDemo.java`**:

```java
class Message {
    static void ping() {
        System.out.println("ping");
    }
}

public class StaticQualifierEvaluationDemo {
    static Message findMessage() {
        System.out.println("evaluating qualifier");
        return null;
    }

    public static void main(String[] args) {
        findMessage().ping();
        Message.ping();
    }
}
```

```bash
javac StaticQualifierEvaluationDemo.java
java StaticQualifierEvaluationDemo
```

```text
evaluating qualifier
ping
ping
```

- Đầu tiên Java đánh giá biểu thức `findMessage()`, in `evaluating qualifier` và trả null.
- Method `ping` là static nên **không dereference giá trị null này** để lấy receiver instance; nó in `ping`.
- `Message.ping()` gọi trực tiếp qua tên class, không có bước đánh giá `findMessage()`, nên chỉ in `ping`.

Đây là lý do tránh `complexExpression().staticMethod()`: cách gọi đó có thể **vẫn thực hiện tính toán/side effect không cần thiết**, dù method được chọn hoàn toàn thuộc kiểu.

## 12. Static methods và kế thừa: hiding, không phải overriding

**Instance methods** có thể tham gia **dynamic dispatch**: implementation được chọn theo runtime class của receiver khi method được override hợp lệ.

**Static methods không được override theo nghĩa đó**. Khi một subclass khai báo static method có chữ ký phù hợp với static method có thể được thừa hưởng từ superclass, nó có thể **hide** (*che khuất*) method của superclass. Method được chọn dựa trên thông tin **kiểu và phân giải lời gọi tại compile time**, không dựa vào runtime object như virtual dispatch.

### Ví dụ tương phản hiding với overriding

Tệp **`StaticHidingDemo.java`**:

```java
class Parent {
    static String typeName() {
        return "Parent-static";
    }

    String describe() {
        return "Parent-instance";
    }
}

class Child extends Parent {
    static String typeName() {
        return "Child-static";
    }

    @Override
    String describe() {
        return "Child-instance";
    }
}

public class StaticHidingDemo {
    public static void main(String[] args) {
        Parent reference = new Child();
        Child child = new Child();

        System.out.println(Parent.typeName());
        System.out.println(Child.typeName());

        System.out.println(reference.typeName());
        System.out.println(reference.describe());

        System.out.println(child.typeName());
        System.out.println(child.describe());
    }
}
```

```bash
javac StaticHidingDemo.java
java StaticHidingDemo
```

```text
Parent-static
Child-static
Parent-static
Child-instance
Child-static
Child-instance
```

Phân tích:

1. `Parent.typeName()` được khai báo tại Parent, nên trả `Parent-static`.
2. `Child.typeName()` chọn method static tại Child, nên trả `Child-static`.
3. `reference` có kiểu tĩnh `Parent` nhưng runtime object là Child. `reference.typeName()` **vẫn chọn static method của Parent**, trả `Parent-static`. Cách gọi qua biến **không nên dùng** ngoài mục đích học ngôn ngữ.
4. `reference.describe()` là instance method override, runtime dispatch vào `Child.describe()`, trả `Child-instance`.
5. `child.typeName()` chọn static method Child dựa trên kiểu tĩnh `Child`; `child.describe()` gọi implementation Child.

**Thực hành đúng:** khi gặp nhiều static methods trùng tên qua kế thừa, dùng **`Parent.typeName()` hoặc `Child.typeName()`** để thể hiện chính xác method nào được chọn. Đừng mong static method “đa hình theo object”.

### Không được thay đổi static/instance để “override”

Nếu superclass có instance method `void work()`, subclass không được khai báo `static void work()` cùng chữ ký để override nó; ngược lại, cũng không được dùng instance method để override static method được inherited theo quy tắc liên quan. Đây là **lỗi compile-time**, không phải hai cách override khác nhau.

Annotation `@Override` không dùng cho static method hiding. Nếu viết `@Override` lên một static method muốn hide, compiler sẽ báo lỗi bởi static methods không được override như instance methods.

## 13. Không phải static method nào cũng được “kế thừa” theo cách giống instance method

Các static methods của class có thể được **kế thừa hoặc bị hide** theo những điều kiện Java áp dụng cho member inheritance. Vì vậy code như `Child.someInheritedStatic()` có thể hợp lệ nếu method static accessible và inherited, dù `Child` không khai báo method ấy.

Tuy nhiên, khi muốn chỉ đúng nơi định nghĩa API, hãy ưu tiên **tên lớp thực sự khai báo method** khi điều đó làm mã rõ hơn.

**Các ngoại lệ quan trọng:**

- `private static methods` không được thừa hưởng như accessible members bình thường. Một subclass khai báo method trùng chữ ký với private method của superclass không phải là hiding cùng cách với static member được kế thừa/accessible.
- Static methods trên **interface** có quy tắc riêng: chúng **không được implementer hoặc subinterface kế thừa theo cách có thể gọi qua tên của implementer/subinterface**; dùng **tên interface khai báo**.
- Access modifiers, package boundary và module boundary vẫn có hiệu lực khi truy cập static method.

Đừng khái quát rằng “mọi static method có thể gọi qua bất kỳ tên subclass nào” hoặc “mọi static method bị ẩn theo cùng quy tắc” mà không xét khả năng truy cập và nguồn khai báo.

## 14. Static methods trong interface: gọi qua chính tên interface

Java cho phép interface khai báo static methods có thân. Chúng thường đóng vai trò helper hoặc factory liên quan trực tiếp đến contract của interface.

Tệp **`InterfaceStaticDemo.java`**:

```java
interface Validator {
    boolean valid(String input);

    static boolean notBlank(String input) {
        return input != null && !input.isBlank();
    }
}

class NameValidator implements Validator {
    @Override
    public boolean valid(String input) {
        return Validator.notBlank(input) && input.length() >= 3;
    }
}

public class InterfaceStaticDemo {
    public static void main(String[] args) {
        Validator validator = new NameValidator();

        System.out.println(Validator.notBlank("Java"));
        System.out.println(validator.valid("An"));
        System.out.println(validator.valid("Linh"));

        // NameValidator.notBlank("Java"); // Không hợp lệ.
        // validator.notBlank("Java");     // Không hợp lệ.
    }
}
```

```bash
javac InterfaceStaticDemo.java
java InterfaceStaticDemo
```

```text
true
false
true
```

- `Validator.notBlank(...)` là **static interface method**, gọi qua tên **interface khai báo**.
- `valid(String)` là instance abstract method của interface. `NameValidator` triển khai instance method bằng `@Override`.
- `NameValidator.notBlank(...)` không hợp lệ vì static interface method **không được kế thừa** như class static method.
- `validator.notBlank(...)` cũng không phải cách gọi hợp lệ cho static method của interface; dùng `Validator.notBlank(...)`.

**Phân biệt:** `default` methods trên interface là instance methods có implementation; static methods không phải default methods và không được override như chúng.

## 15. Dùng static method trong một utility class

Một utility class nhóm các **hàm độc lập với instance state** và thường có constructor `private` để không cho caller tạo đối tượng vô nghĩa. Trong ví dụ này, `SlugUtils` cung cấp hai static methods và được gọi qua **tên lớp** — đúng trọng tâm của bài về static method.

Lưu file **`SlugUtilsDemo.java`**:

~~~java
final class SlugUtils {
    private SlugUtils() {}

    static String toSlug(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input required");
        }
        return input.trim().toLowerCase(
                java.util.Locale.ROOT).replace(' ', '-');
    }

    static boolean sameSlug(String left, String right) {
        return toSlug(left).equals(toSlug(right));
    }
}

public class SlugUtilsDemo {
    public static void main(String[] args) {
        System.out.println(SlugUtils.toSlug(" Java Core "));
        System.out.println(SlugUtils.sameSlug(
                " Hello World ", "hello world"));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SlugUtilsDemo.java
java SlugUtilsDemo
~~~

Stdout:

~~~text
java-core
true
~~~

`Locale.ROOT` tránh phụ thuộc locale mặc định khi chuẩn hóa chuỗi không phụ thuộc ngôn ngữ. Ở đây `toSlug` và `sameSlug` hoạt động theo arguments, không đọc state của một `SlugUtils` instance.

**Ranh giới với bài thiết kế utility class:** bài hiện tại minh họa cách **gọi static methods**. Bài **“Thiết kế lớp tiện ích với hàm khởi tạo private”** sẽ phân tích thêm constructor accessibility, `final`, API surface, anti-pattern mutable static fields, testability và trường hợp nên dùng instance service thay vì utility.

## 16. Static factory method: gọi qua tên lớp để tạo object

Một static method **vẫn có thể tạo instance**. Đây là mẫu **static factory method**, thường thấy trong Java:

- `List.of(...)`: trả list theo contract của API.
- `LocalDate.of(...)`: trả một giá trị ngày.
- `Integer.valueOf(...)`: trả Integer object/value theo API, có thể cache.
- `Optional.ofNullable(...)`: tạo Optional dựa trên tham chiếu có thể null.

**Không phải static factory nào cũng gọi `new` mỗi lần**: implementation có thể trả object cũ, cached object hoặc một subtype phù hợp theo contract.

Ví dụ tự xây dựng, tệp **`StaticFactoryDemo.java`**:

```java
final class UserId {
    private final String value;

    private UserId(String value) {
        this.value = value;
    }

    static UserId of(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("blank id");
        }
        return new UserId(raw.trim().toUpperCase());
    }

    String value() {
        return value;
    }
}

public class StaticFactoryDemo {
    public static void main(String[] args) {
        UserId id = UserId.of(" u-7 ");
        System.out.println(id.value());
    }
}
```

```bash
javac StaticFactoryDemo.java
java StaticFactoryDemo
```

```text
U-7
```

- `UserId.of(...)` là static method: caller gọi bằng tên lớp, không cần `UserId` có sẵn.
- `UserId(...)` là constructor private: chỉ mã được phép truy cập mới gọi được để tạo object.
- Instance method `value()` đọc trạng thái của object được factory trả về.
- Thiết kế này tập trung validation và chuẩn hóa đầu vào; không cho caller bỏ qua điều kiện bằng `new UserId(...)` từ code bên ngoài.

**Tránh nhầm:** static factory là **method static trả tham chiếu tới object**, không phải constructor; constructor không có return type và dùng cú pháp khác.

## 17. Method overload: static methods cũng có thể trùng tên, khác tham số

Một class có thể **overload** static methods bằng các danh sách tham số khác nhau:

```java
class Converter {
    static String text(int number) {
        return "int:" + number;
    }

    static String text(double number) {
        return "double:" + number;
    }

    static String text(String value) {
        return "text:" + value;
    }
}
```

Lời gọi `Converter.text(5)` chọn overload nhận `int`, `Converter.text(5.0)` nhận `double`, `Converter.text("A")` nhận `String`, theo các quy tắc overload resolution của Java.

### Ví dụ chạy

Tệp **`StaticOverloadDemo.java`**:

```java
class Formatter {
    static String format(int value) {
        return "int=" + value;
    }

    static String format(String value) {
        return "str=" + value;
    }
}

public class StaticOverloadDemo {
    public static void main(String[] args) {
        System.out.println(Formatter.format(12));
        System.out.println(Formatter.format("12"));
    }
}
```

```bash
javac StaticOverloadDemo.java
java StaticOverloadDemo
```

```text
int=12
str=12
```

**Lưu ý:**

- Không thể overload chỉ bằng **return type** khi tên và danh sách tham số giống nhau.
- Modifier `static` **không tạo chữ ký method khác**. Trong cùng class, không thể có cả `static void print(int x)` và `void print(int x)` với cùng chữ ký.
- Overload resolution chủ yếu diễn ra tại compile time dựa trên loại đối số và các quy tắc Java; không liên quan tới dynamic dispatch của instance override.

## 18. Generic static method và type parameters

Một static method có thể tự khai báo **type parameter**:

```java
class Identity {
    static <T> T keep(T value) {
        return value;
    }
}
```

Ở đây `<T>` được khai báo **riêng cho method**, nên `Identity.keep("Java")` trả `String` phù hợp, `Identity.keep(42)` trả `Integer` phù hợp qua boxing/inference.

### Ví dụ runnable

Tệp **`GenericStaticMethodDemo.java`**:

```java
class Values {
    static <T> T chooseFirst(T first, T second) {
        return first;
    }
}

public class GenericStaticMethodDemo {
    public static void main(String[] args) {
        String text = Values.chooseFirst("A", "B");
        Integer number = Values.chooseFirst(10, 20);

        System.out.println(text);
        System.out.println(number);
    }
}
```

```bash
javac GenericStaticMethodDemo.java
java GenericStaticMethodDemo
```

```text
A
10
```

**Cạm bẫy generic class:**

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    // static T bad() { return null; } // Sai: T là type parameter của class.
    static <U> U identity(U value) {
        return value;
    }
}
```

Một static member của generic class không được dùng **type parameter cấp instance của class** như `T` một cách trực tiếp. Nó không gắn với một particular `Box<String>` hay `Box<Integer>` instance. Nhưng static method có thể khai báo **type parameter riêng `<U>`**.

## 19. Static import: bỏ tên lớp ở chỗ gọi có chọn lọc

Java hỗ trợ `import static`:

```java
import static java.lang.Math.max;
import static java.lang.Math.min;
```

Nhờ đó có thể viết `max(3, 7)` thay vì `Math.max(3, 7)` trong scope thích hợp.

Tệp **`StaticImportDemo.java`**:

```java
import static java.lang.Math.max;
import static java.lang.Math.min;

public class StaticImportDemo {
    public static void main(String[] args) {
        System.out.println(max(3, 7));
        System.out.println(min(3, 7));
        System.out.println(Math.max(10, 4));
    }
}
```

```bash
javac StaticImportDemo.java
java StaticImportDemo
```

```text
7
3
10
```

**Điều cần phân biệt:**

- `import static` chỉ ảnh hưởng cách **phân giải tên** trong source file. Nó **không chuyển static method thành instance method**.
- Nó không tự chạy method, không copy mã và không tạo object.
- Cân nhắc tránh lạm dụng `import static ...*;` nếu các static members dễ trùng tên với phương thức/hằng khác khiến code khó đọc.
- Với helper dễ nhận ra như `Math.max` hoặc assertions trong test, static import có thể tăng độ rõ. Với API ít quen, `ClassName.method()` thường diễn đạt nơi khai báo dễ hơn.

## 20. Method reference tới static method

Static method có thể được dùng với **method reference** theo cú pháp `TypeName::methodName` khi khớp functional interface.

Tệp **`StaticMethodReferenceDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.IntBinaryOperator;

public class StaticMethodReferenceDemo {
    static String decorate(String text) {
        return "[" + text + "]";
    }

    public static void main(String[] args) {
        Function<String, String> formatter =
                StaticMethodReferenceDemo::decorate;

        IntBinaryOperator bigger = Math::max;

        System.out.println(formatter.apply("Java"));
        System.out.println(bigger.applyAsInt(4, 9));
    }
}
```

```bash
javac StaticMethodReferenceDemo.java
java StaticMethodReferenceDemo
```

```text
[Java]
9
```

- `StaticMethodReferenceDemo::decorate` chỉ static method nhận String, trả String, phù hợp với `Function<String,String>`.
- `Math::max` chỉ overload phù hợp với `IntBinaryOperator` nhận hai `int`, trả `int`.
- Cú pháp này không gọi method ngay khi tạo tham chiếu; lời gọi diễn ra khi chạy functional interface method (`apply` hoặc `applyAsInt`).

**Phân biệt:** `object::instanceMethod` là bound instance method reference, còn `Type::instanceMethod` có thể là unbound instance method reference khi functional interface cung cấp receiver làm đối số. Không phải **mọi** `Type::method` đều nhất thiết chỉ static; phải xét method và target functional type.

## 21. Thời điểm khởi tạo lớp và lời gọi static method

Một static method có thể được gọi mà không tạo instance, nhưng **lời gọi static method được khai báo bởi một class** thường là một trong những hoạt động kích hoạt **class initialization** trước khi thân method chạy theo quy tắc Java.

Tệp **`ClassInitStaticCallDemo.java`**:

```java
class Service {
    static {
        System.out.println("Service initialized");
    }

    static void work() {
        System.out.println("Service.work");
    }

    Service() {
        System.out.println("Service constructor");
    }
}

public class ClassInitStaticCallDemo {
    public static void main(String[] args) {
        System.out.println("begin");
        Service.work();
        Service.work();
        new Service();
    }
}
```

```bash
javac ClassInitStaticCallDemo.java
java ClassInitStaticCallDemo
```

```text
begin
Service initialized
Service.work
Service.work
Service constructor
```

- Lần gọi `Service.work()` đầu trong chương trình kích hoạt khởi tạo `Service` theo quy tắc, nên static initializer in một lần trước method.
- Lần gọi thứ hai **không chạy lại** static initializer, nhưng **thực thi lại** `work()` và in dòng thứ hai.
- Chỉ `new Service()` mới gọi constructor, nên in `Service constructor` ở cuối.

**Đừng nhầm:** “static initializer chạy một lần trong vòng đời khởi tạo class” khác hoàn toàn “static method chỉ chạy một lần”. Các class loaders/khởi tạo lớp và các tình huống class initialization lỗi có quy tắc sâu hơn, nhưng không cần suy từ ví dụ rằng method sẽ được memoize hoặc gọi tự động.

## 22. Static field và static method: dữ liệu dùng chung không có nghĩa an toàn đa luồng

Một static method có thể truy cập static field:

```java
class Sequence {
    private static int next;

    static int nextId() {
        return ++next;
    }
}
```

`Sequence.nextId()` thay đổi một biến **dùng chung trên cấp lớp**. Trong một luồng, kết quả các lần gọi tuần tự có thể là 1, 2, 3... nhưng trong nhiều thread, phép `++next` **không phải thao tác nguyên tử** theo yêu cầu cấp ID duy nhất.

Một phương án dùng atomic counter:

```java
import java.util.concurrent.atomic.AtomicInteger;

class Sequence {
    private static final AtomicInteger NEXT = new AtomicInteger();

    static int nextId() {
        return NEXT.incrementAndGet();
    }
}
```

Mã thứ hai là **phiên bản thay thế** của lớp `Sequence`, không để cùng lúc trong một source set. AtomicInteger hỗ trợ cập nhật nguyên tử theo contract. Trong môi trường cần ID duy nhất giữa nhiều JVM/process, một static counter nội bộ vẫn **không đủ**; phải có chiến lược phối hợp ngoài tiến trình.

### Không nhất thiết static method phải có static state

Rất nhiều static utilities tốt là **stateless**:

```java
static int clamp(int value, int low, int high) {
    if (low > high) {
        throw new IllegalArgumentException("low > high");
    }
    return Math.max(low, Math.min(value, high));
}
```

Đây là mảnh method đặt trong class. Nó chỉ dựa trên đối số, không truy cập mutable state chung. Vì vậy đừng đánh đồng “static” với “biến toàn cục” hoặc “singleton”.

## 23. `synchronized static` dùng monitor của class, không phải `this`

Một static synchronized method khóa **monitor của Class object** đại diện cho lớp khai báo method; nó không khóa receiver instance vì không có `this`.

Ví dụ:

```java
class SharedCounter {
    private static int total;

    static synchronized void increase() {
        total++;
    }

    static synchronized int total() {
        return total;
    }
}
```

Hai static synchronized methods cùng thuộc `SharedCounter` sử dụng monitor liên quan tới `SharedCounter.class`.

Một instance synchronized method lại khóa receiver object thích hợp. Vì vậy không thể giả định một `synchronized` instance method và một `static synchronized` method **đang khóa cùng monitor** để bảo vệ chung một static field.

### Ví dụ runnable đơn luồng

Tệp **`SynchronizedStaticDemo.java`**:

```java
class Counter {
    private static int count;

    static synchronized void increase() {
        count++;
    }

    static synchronized int count() {
        return count;
    }
}

public class SynchronizedStaticDemo {
    public static void main(String[] args) {
        Counter.increase();
        Counter.increase();
        System.out.println(Counter.count());
    }
}
```

```bash
javac SynchronizedStaticDemo.java
java SynchronizedStaticDemo
```

```text
2
```

Ví dụ chỉ minh họa **API và hành vi đơn luồng**; để kiểm chứng concurrency cần một bài riêng có nhiều threads và các bảo đảm Java Memory Model. Static method không tự synchronized nếu bạn không khai báo/thiết kế cơ chế đồng bộ phù hợp.

## 24. Access modifiers: gọi qua tên lớp còn cần quyền truy cập

Viết `ClassName.method()` không “bỏ qua” kiểm tra truy cập.

Các điều kiện có thể gồm:

- **Tên class** phải accessible từ vị trí caller (public/package-private, enclosing types và module boundary nếu dùng JPMS).
- **Static method** phải accessible theo modifier `public`, `protected`, package-private hoặc `private`.
- Những method nằm trong **interface** có quy tắc access riêng; static interface methods gọi qua tên interface khai báo.
- Nếu có overloads, chữ ký được chọn phải phù hợp với các đối số và ngữ cảnh quyền truy cập.

Ví dụ:

```java
package library;

public class Secrets {
    private static String internal() {
        return "hidden";
    }

    public static String display() {
        return internal();
    }
}
```

Từ package `app`, nếu có module/package access hợp lệ, `Secrets.display()` accessible; `Secrets.internal()` **không** accessible vì private. Việc method thuộc lớp và được gọi bằng tên lớp không làm method private trở thành public.

Một static method trên **package-private top-level class** cũng không tự accessible từ package khác chỉ vì method mang modifier public.

## 25. Có nên đánh dấu static cho mọi method không dùng field?

Không nhất thiết. Khi lựa chọn, xét **vai trò của method trong thiết kế**:

| Tình huống | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Hàm tính toán chỉ phụ thuộc đối số | `static` utility | Không có receiver state |
| Factory tạo object có validation | `static` factory | Không cần object có sẵn |
| Đọc/ghi state của object hiện tại | Instance method | Thuộc hành vi object |
| Hành vi có thể được subclass override | Instance method | Cần polymorphic dispatch |
| Interface yêu cầu mỗi implementation cung cấp hành vi | Instance method | Static không override interface instance method |
| Helper chỉ phục vụ một class | `private static` nếu không cần receiver, hoặc private instance nếu có | Access/thiết kế rõ ràng |
| Hành vi cấp lớp cần cập nhật shared data | Static method có kiểm soát concurrency | Dữ liệu và API chung, không gắn một object |
| Method tạm không dùng instance field nhưng có thể cần polymorphism/contract instance | Có thể vẫn để instance | Không ép static chỉ vì body hiện tại không đọc `this` |

Đừng biến static thành “tối ưu hiệu năng bắt buộc”. Java/JIT có thể tối ưu cả static và instance methods; lựa chọn nên bắt đầu từ **ngữ nghĩa API và khả năng mở rộng**. Static method làm một điểm phụ thuộc tĩnh vào kiểu cụ thể; trong hệ thống cần dependency injection/test double/đa implementation, instance abstraction hoặc interface có thể phù hợp hơn.

### Tránh mutable static state nếu không cần

Một static utility **stateless** dễ test và dùng lại. Nếu viết static method phụ thuộc hàng loạt static mutable fields, các bài test có thể ảnh hưởng lẫn nhau do dùng chung state; concurrency cũng khó. Khi state có vòng đời/danh tính rõ, cân nhắc object instance được truyền vào những thành phần cần dùng.

## 26. Những lỗi và ngộ nhận phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`static` method phải gọi bằng object” | Nên gọi `ClassName.method()`, không cần instance |
| “Static method chỉ chạy một lần” | Nó có thể chạy nhiều lần; static initializer mới có quy tắc khởi tạo lớp riêng |
| “Static method có `this` là class hiện tại” | Không có `this` ngầm trong static context |
| “Static method không thể truy cập object nào” | Có thể dùng object được truyền làm tham số hoặc object tạo/tìm được |
| “Thêm `static` cho instance field để static method đọc” | Chỉ đúng nếu dữ liệu thực sự dùng chung ở cấp lớp |
| “Gọi `obj.staticMethod()` nghĩa object là receiver” | Cú pháp có thể hợp lệ nhưng method vẫn static; nên gọi bằng tên lớp |
| “`nullRef.staticMethod()` chắc chắn ném NPE” | Không vì static invocation không dereference instance receiver; tránh cách viết ấy |
| “Qualifier expression không được đánh giá vì method static” | Nó vẫn có thể được đánh giá và gây side effect |
| “Static method được override như instance method” | Static method **hiding**, không dynamic dispatch |
| “`Parent ref = new Child(); ref.staticMethod()` gọi Child version” | Method static được chọn theo kiểu/ngữ cảnh compile-time, có thể là Parent version |
| “`@Override` phù hợp khi hide static method” | Không; `@Override` dành cho overriding instance method |
| “Static/instance modifier đủ để overload cùng chữ ký” | Không; chữ ký giống nhau trong cùng class gây lỗi |
| “Static interface method được implementer kế thừa” | Không; dùng tên interface khai báo |
| “Static method thực hiện instance interface contract” | Không; phải có implementation instance method phù hợp |
| “`import static` biến method thành method của caller” | Chỉ giúp dùng tên đơn theo import resolution |
| “`Type::method` lúc nào cũng static” | Có thể chỉ static hoặc unbound instance method, tùy declaration/functional target |
| “Static generic method dùng `T` của generic class” | Phải khai báo type parameter riêng nếu cần |
| “`static` biến việc cập nhật `count++` thành thread-safe” | Không; cần concurrency control tương ứng |
| “Static method nằm trong public class thì tự public” | Method có access modifier riêng |
| “Static factory là constructor” | Factory là method static trả object, không phải constructor |
| “Static method luôn cần dùng static field” | Method stateless chỉ xử lý arguments cũng rất phổ biến |
| “Static synchronized method khóa `this`” | Nó khóa Class monitor, không có receiver `this` |
| “Có thể gọi static method trên interface qua tên implementing class” | Không theo quy tắc static interface methods |

## 27. Truy vết nhanh cách chọn phương thức nào được gọi

Đọc chương trình và tự dự đoán output:

Tệp **`StaticCallTraceDemo.java`**:

```java
class Base {
    static String label() {
        return "Base";
    }

    String instance() {
        return "Base-instance";
    }
}

class Derived extends Base {
    static String label() {
        return "Derived";
    }

    @Override
    String instance() {
        return "Derived-instance";
    }
}

public class StaticCallTraceDemo {
    static String join(String left, String right) {
        return left + "/" + right;
    }

    public static void main(String[] args) {
        Base a = new Derived();
        Derived b = new Derived();

        System.out.println(Base.label());
        System.out.println(Derived.label());
        System.out.println(a.label());
        System.out.println(a.instance());
        System.out.println(join(b.label(), b.instance()));
    }
}
```

```bash
javac StaticCallTraceDemo.java
java StaticCallTraceDemo
```

```text
Base
Derived
Base
Derived-instance
Derived/Derived-instance
```

**Lời giải:**

1. `Base.label()` gọi static method khai báo ở Base → `Base`.
2. `Derived.label()` gọi static method khai báo ở Derived → `Derived`.
3. `a` có kiểu tĩnh Base, dù trỏ Derived object. `a.label()` là static invocation qua biểu thức nên chọn Base → `Base`. Cách dùng này có thể được thay bằng `Base.label()`.
4. `a.instance()` là lời gọi instance; runtime dispatch tới Derived override → `Derived-instance`.
5. `b.label()` static theo kiểu Derived; `b.instance()` instance dispatch tới Derived; `join(...)` là static method của lớp hiện tại, gọi bằng tên đơn trong cùng class; kết quả ghép là `Derived/Derived-instance`.

**Kỹ năng cần đạt:** gặp `x.m()` không đoán ngay rằng JVM chọn method theo runtime class của `x`. Trước hết xem **khai báo được phân giải là static hay instance**, sau đó mới dùng đúng quy tắc invocation.

## 28. Câu hỏi tự kiểm tra kèm đáp án

**Câu 1.** Phương thức `static int sum(int a,int b)` có cần tạo object trước khi gọi không?

**Đáp án:** Không. Gọi `ClassName.sum(2,3)` nếu method accessible.

**Câu 2.** Có thể viết `this.value++` trực tiếp trong static method không?

**Đáp án:** Không. Static context không có receiver `this`. Dùng object cụ thể hoặc chuyển hành vi về instance method khi đúng thiết kế.

**Câu 3.** `static void update(Box b) { b.add(1); }` có thể sửa Box của caller không?

**Đáp án:** Có, nếu `b` tham chiếu mutable Box object và `add` thay state. Tham số nhận bản sao giá trị tham chiếu; static method vẫn có thể thao tác object qua tham số.

**Câu 4.** Tại sao nên dùng `Math.max(3,7)` thay vì tạo một đối tượng Math?

**Đáp án:** `max` là static API gắn với `Math`, không cần receiver object và không có ý nghĩa instance riêng.

**Câu 5.** Với `Greeter g = null; g.shared()` khi `shared` static, NPE có bắt buộc xảy ra không?

**Đáp án:** Không. Static method không cần dereference receiver instance. Tuy nhiên nên viết `Greeter.shared()`.

**Câu 6.** `find().ping()` với `ping` static có bỏ qua lời gọi `find()` không?

**Đáp án:** Không. Biểu thức qualifier vẫn được đánh giá theo quy tắc ngôn ngữ, nên có thể có side effect.

**Câu 7.** Subclass khai báo static method cùng chữ ký với static superclass method có phải overriding không?

**Đáp án:** Không; đó là **method hiding** khi đủ điều kiện. Static invocation không dùng virtual dispatch như instance override.

**Câu 8.** Interface `Check` khai báo `static boolean ok(...)`; implementer `CheckImpl` có gọi `CheckImpl.ok(...)` được không?

**Đáp án:** Không phải cách hợp lệ để gọi static interface method đó. Dùng `Check.ok(...)`.

**Câu 9.** `import static Math.max;` có làm static method tự chạy không?

**Đáp án:** Không. Nó chỉ hỗ trợ phân giải tên; cú pháp nhập đầy đủ thường là `import static java.lang.Math.max;`.

**Câu 10.** `static` có đồng nghĩa “shared mutable field” không?

**Đáp án:** Không. Static method có thể hoàn toàn stateless; không bắt buộc có mutable static fields.

**Câu 11.** Static method có được overloaded không?

**Đáp án:** Có nếu parameter lists khác nhau. Không được overload chỉ bằng return type hoặc chỉ khác modifier `static`.

**Câu 12.** Generic static method có thể viết `static <T> T id(T x)` không?

**Đáp án:** Có. `T` là type parameter riêng của method. Không được mặc nhiên dùng class-level type parameter `T` của generic class trong static context.

**Câu 13.** Gọi static method lần thứ ba có chạy lại static initializer không?

**Đáp án:** Không theo quy trình class initialization thông thường sau khi lớp đã được khởi tạo thành công; nhưng static method vẫn thực thi ở mỗi lời gọi.

**Câu 14.** Một `static synchronized` method khóa monitor của object nào?

**Đáp án:** Monitor của `Class` object đại diện cho lớp khai báo method, không có `this` instance receiver.

**Câu 15.** Lớp public có private static method; code package khác được gọi `ClassName.privateMethod()` không?

**Đáp án:** Không. Quy tắc access của method vẫn được áp dụng riêng.

**Câu 16.** Khi nào nên dùng instance method dù thân hiện tại chưa đọc field?

**Đáp án:** Khi hành vi thuộc hợp đồng object hoặc cần khả năng override/đa hình phù hợp; không bắt buộc biến static chỉ vì hiện tại method chưa sử dụng `this`.

## 29. Checklist khi viết hoặc review một static method

- [ ] Method có thật sự **không cần một instance receiver ngầm**?
- [ ] Caller có thể gọi rõ ràng bằng `DeclaringType.method(...)`?
- [ ] Method cần truy cập instance state thì đã nhận object/được cung cấp reference rõ ràng?
- [ ] Không viết `this` hoặc gọi instance members bằng tên đơn từ static context?
- [ ] Có phân biệt **static method invocation** với **constructor** và **instance method**?
- [ ] Có tránh gọi static method qua biến instance, đặc biệt qua biến null hoặc biểu thức có side effect?
- [ ] Với inheritance, có hiểu **hiding vs overriding** và tránh `@Override` cho static method?
- [ ] Với interface static methods, có gọi qua **tên interface khai báo**?
- [ ] Overloads có chữ ký phân biệt hợp lệ, không chỉ khác return type/static?
- [ ] Generic static method có tự khai báo type parameter nếu cần?
- [ ] Nếu dùng `import static`, tên ngắn có dễ hiểu và tránh xung đột?
- [ ] Nếu dùng method reference, có xác nhận functional signature phù hợp?
- [ ] Nếu method đọc/ghi static mutable state, có chính sách test isolation và đồng bộ?
- [ ] Nếu static factory, có validate đầu vào và mô tả rõ đối tượng trả về?
- [ ] Quyền truy cập class/method có đúng phạm vi và module boundary không?
- [ ] Kết quả của static method có được dùng/kiểm tra hợp đồng thay vì giả định state chung?
- [ ] Đã chạy `javac`/`java` với đúng tệp public class và kiểm tra stdout thực tế khi có thể?

---

**Ghi nhớ:** **Phương thức static thuộc cấp lớp** và nên được gọi dưới dạng **`ClassName.method(args)`** hoặc tên interface khai báo, không cần tạo object làm receiver. Nó **không có `this`**, nhưng vẫn thao tác được trên các objects được truyền/tham chiếu tường minh. Lời gọi static qua object có thể hợp lệ song dễ hiểu nhầm; **static hiding khác instance overriding** và không dispatch động theo runtime receiver. `static` không có nghĩa gọi một lần, không tự tạo thread safety, và không biến mọi state thành dùng chung. Chọn static khi **ngữ nghĩa hành vi gắn với kiểu hoặc chỉ phụ thuộc input**, chọn instance khi hành vi cần receiver state hoặc hợp đồng đa hình của object.