# `final` trên phương thức và lớp trong Java

Trong Java, từ khóa **`final`** có ý nghĩa khác nhau tùy vị trí khai báo. Đối với **phương thức**, nó ngăn lớp con **override** phương thức theo các quy tắc kế thừa. Đối với **lớp**, nó ngăn tạo lớp con bằng `extends`. Đây là hai cơ chế giúp tác giả API xác định **điểm được phép mở rộng** và **hợp đồng hành vi không được thay bằng implementation của lớp con**.

Hai ví dụ ngắn:

```java
class Account {
    public final String type() {
        return "ACCOUNT";
    }
}

class SavingsAccount extends Account {
    // public String type() { return "SAVINGS"; }
    // SAI nếu bỏ comment: không được override final method.
}
```

```java
final class SecurityToken {
    private final String value;

    SecurityToken(String value) {
        this.value = value;
    }
}

// class CustomToken extends SecurityToken { }
// SAI nếu bỏ comment: không thể kế thừa final class.
```

**Ghi nhớ ngay:**

- `final` trên **instance method**: subclass không thể cung cấp **override** cho method đó.
- `final` trên **static method**: subclass không được **hide** static method có chữ ký tương ứng theo quy tắc ngôn ngữ; static method vốn không override động.
- `final` trên **class**: class ấy không thể có subclass theo cơ chế kế thừa Java thông thường.
- `final` **không** cấm gọi phương thức, không cấm tạo instance của một class bình thường có constructor hợp lệ, và không cấm **overload** tên method với danh sách tham số khác.
- `final` trên method/class **không đồng nghĩa object bất biến**, **không thay access modifier** và **không tự làm code thread-safe**.

Bài học dùng **Java 17+**. Những đoạn có dòng bị comment với nhãn lỗi là **ví dụ cố ý sai nếu bỏ comment**; các chương trình hoàn chỉnh có tên tệp và lệnh `javac`/`java` riêng đều được trình bày theo hướng có thể biên dịch và chạy độc lập.

## 1. Trước hết: override, overload, hiding và extends

Để hiểu đúng `final`, cần phân biệt bốn thuật ngữ:

| Thuật ngữ | Ý nghĩa ngắn | Ví dụ |
| --- | --- | --- |
| **Overriding** | Lớp con cung cấp implementation của một instance method được kế thừa có cùng chữ ký phù hợp | `Child.work()` override `Parent.work()` |
| **Overloading** | Nhiều method cùng tên nhưng **danh sách tham số khác** theo quy tắc chữ ký | `print(int)` và `print(String)` |
| **Static method hiding** | Lớp con khai báo static method tương ứng, làm ẩn static method từ superclass, khi được phép | `Child.label()` và `Parent.label()` |
| **Class inheritance** | Class con mở rộng class cha bằng `extends` | `class Child extends Parent` |

Khi method **final**, điều bị khóa là **khả năng override hoặc hide tương ứng**, không phải mọi sự xuất hiện của tên method đó. Khi class **final**, điều bị khóa là **class inheritance từ class này**, không phải việc class ấy được sử dụng như một kiểu, chứa state hay implements interface.

### Một ví dụ đối chiếu không có final

```java
class Parent {
    String describe() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String describe() {
        return "Child";
    }
}
```

Với:

```java
Parent value = new Child();
System.out.println(value.describe()); // Child
```

Lời gọi có thể chọn implementation override ở runtime theo object `Child`.

Nếu `Parent.describe()` khai báo `final`, `Child` **không được khai báo override** này. Còn `Parent.describe()` vẫn được gọi từ một object `Child` như phương thức kế thừa.

## 2. `final` trên instance method: ngăn override, không ngăn kế thừa

Giả sử superclass có:

```java
class Base {
    public final String identity() {
        return "Base";
    }
}
```

Một subclass hợp lệ:

```java
class Derived extends Base {
    void extra() {
        System.out.println(identity());
    }
}
```

`Derived` **vẫn kế thừa và được gọi** `identity()`. Nó chỉ không được thay implementation:

```java
class InvalidDerived extends Base {
    // @Override
    // public String identity() {
    //     return "Derived";
    // }
    // SAI nếu bỏ comment: overridden method is final.
}
```

**Không nên nói “final method không được kế thừa”.** Đúng hơn là **không được override**. Một method final phù hợp có thể được kế thừa, được gọi qua biến lớp cha hay lớp con, và được dùng trong các lớp con không khai báo lại nó.

### Vì sao cấm override?

Khi một class cung cấp method final, tác giả class muốn giữ nguyên implementation của method đó trong những subclass hợp lệ. Việc này hữu ích khi:

- Method duy trì một bước quan trọng trong **invariant** của đối tượng.
- Một thuật toán chung cần giữ **thứ tự thực hiện** hoặc kiểm tra.
- API cần một hành vi đồng nhất ở mọi subtype.
- Thiết kế chỉ cho subclass mở rộng bằng **hook method được lựa chọn**, không cho thay entry point.

Tuy vậy, **final không thay thế kiểm tra đầu vào, phân quyền hay kiểm soát mutation**. Nó chỉ là một ràng buộc trong quan hệ kế thừa ở cấp ngôn ngữ.

## 3. Ví dụ Java 17 hoàn chỉnh: kế thừa nhưng không override final method

Lưu toàn bộ thành **`FinalMethodDemo.java`**:

```java
class Document {
    private final String title;

    Document(String title) {
        this.title = title;
    }

    public final String category() {
        return "DOCUMENT";
    }

    public String description() {
        return title;
    }
}

class Report extends Document {
    Report(String title) {
        super(title);
    }

    @Override
    public String description() {
        return "Report: " + super.description();
    }

    // @Override
    // public String category() { return "REPORT"; }
    // SAI nếu bỏ comment: category() là final.
}

public class FinalMethodDemo {
    public static void main(String[] args) {
        Document first = new Document("Guide");
        Document second = new Report("Sales");

        System.out.println(first.category());
        System.out.println(second.category());
        System.out.println(first.description());
        System.out.println(second.description());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 FinalMethodDemo.java
java FinalMethodDemo
```

**Stdout chính xác:**

```text
DOCUMENT
DOCUMENT
Guide
Report: Sales
```

Phân tích:
1. `Report` được quyền `extends Document` vì class `Document` **không final**.
2. `category()` của `Document` là final. Cả object `Document` lẫn `Report` dùng implementation đó và in `DOCUMENT`.
3. `description()` không final, nên `Report` override được và thay hành vi.
4. Biến `second` có kiểu khai báo `Document` nhưng object runtime là `Report`; lời gọi `description()` dispatch đến implementation `Report`.
5. `super.description()` trong instance method `Report.description()` gọi implementation cha một cách hợp lệ.

**Kết luận:** `final` khóa **một method cụ thể**, không khóa toàn bộ class hay mọi method khác.

## 4. `final` không cản **overloading**

Overloading là khai báo cùng tên method nhưng **danh sách tham số khác**:

```java
class Formatter {
    public final String format(int value) {
        return "integer=" + value;
    }
}

class ExtendedFormatter extends Formatter {
    public String format(String value) {
        return "text=" + value;
    }
}
```

Đây là code hợp lệ vì `format(String)` **không override** `format(int)`. Hai chữ ký khác nhau.

### Ví dụ runnable

Lưu **`FinalOverloadDemo.java`**:

```java
class Formatter {
    public final String format(int value) {
        return "int: " + value;
    }
}

class TextFormatter extends Formatter {
    public String format(String value) {
        return "text: " + value;
    }
}

public class FinalOverloadDemo {
    public static void main(String[] args) {
        TextFormatter formatter = new TextFormatter();

        System.out.println(formatter.format(7));
        System.out.println(formatter.format("Java"));

        Formatter baseView = formatter;
        System.out.println(baseView.format(9));

        // baseView.format("Java");
        // SAI nếu bỏ comment: Formatter không khai báo overload String.
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 FinalOverloadDemo.java
java FinalOverloadDemo
```

Stdout:

```text
int: 7
text: Java
int: 9
```

**Điểm cần phân biệt:**

- `TextFormatter.format(String)` hợp lệ vì chỉ là **overload**.
- `Formatter.format(int)` vẫn là **final**, không thể bị override.
- Việc compiler chọn overload phụ thuộc kiểu tĩnh và quy tắc resolution; vì `baseView` có kiểu `Formatter`, compiler không tự dùng overload chỉ tồn tại trong `TextFormatter`.
- Modifier `final` không làm method call trở thành phép tìm method dựa hoàn toàn vào kiểu runtime.

### Có thể overload ngay trong cùng class không?

Có:

```java
class Reader {
    final void read(int id) {
    }

    void read(String key) {
    }
}
```

`read(int)` final và `read(String)` không final. Đây là hai phương thức khác chữ ký, mỗi phương thức có hợp đồng modifier riêng.

## 5. `final` và `@Override`

Annotation `@Override` yêu cầu compiler kiểm tra rằng method đang khai báo thực sự **override hoặc implement một method tương ứng hợp lệ** theo quy tắc.

Ví dụ:

```java
class Base {
    public final void send() {
    }
}

class Child extends Base {
    // @Override
    // public void send() { }
    // SAI nếu bỏ comment: không được override final method.
}
```

Bỏ `@Override` khỏi method của `Child` **không khắc phục** lỗi:

```java
// public void send() { } // Vẫn sai trong Child.
```

**Lỗi nằm ở hành vi override bị cấm**, không phải vì compiler “không thích” annotation.

Ngược lại, khi cần override method được phép, `@Override` là cách thực hành tốt để phát hiện chữ ký bị gõ sai hoặc thay đổi API superclass.

## 6. Dynamic dispatch và `final`

Với **instance method không final**, lựa chọn implementation có thể phụ thuộc runtime object (dynamic dispatch).

```java
class Animal {
    String sound() {
        return "?";
    }
}

class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}
```

`Animal a = new Cat(); a.sound();` gọi `Cat.sound()`.

Khi `Animal.sound()` được đánh dấu final, **lớp con không thể định nghĩa implementation override hợp lệ**:

```java
class Animal {
    final String sound() {
        return "?";
    }
}

class Cat extends Animal {
    // Không thể override sound().
}
```

Compiler/JVM có thông tin rằng implementation đó không thể bị thay bằng override của subclass. Tuy nhiên không nên suy ra rằng mọi lời gọi tới final method luôn được JIT inline hoặc luôn nhanh hơn method không final: tối ưu phụ thuộc JVM, profiling và nhiều điều kiện khác.

### Final là hợp đồng API, không phải cam kết tốc độ

Đặt `final` vì bạn thực sự muốn **khóa điểm mở rộng**. Đừng thêm nó một cách máy móc chỉ với mục tiêu “tăng tốc” mà không đo hiệu năng trên workload thật.

Trong JVM hiện đại, nhiều lời gọi không final cũng có thể được tối ưu nhờ phân tích kiểu và speculative optimization.

## 7. Thiết kế template method: khóa quy trình, cho phép mở rộng có kiểm soát

Một mẫu hợp lý là để **method điều phối** thành final, còn **các bước tùy biến** là protected/abstract hoặc các hook không final.

Ví dụ:

```java
abstract class Processor {
    public final String process(String input) {
        String normalized = input.trim();
        return transform(normalized);
    }

    protected abstract String transform(String normalized);
}
```

Subclass **không** thay được method `process` (nên không bỏ qua bước `trim` theo cách override), nhưng có thể triển khai `transform`.

### Chương trình Java 17 hoàn chỉnh

Lưu **`FinalTemplateDemo.java`**:

```java
import java.util.Locale;

abstract class Processor {
    public final String process(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input required");
        }

        String normalized = input.trim();
        return transform(normalized);
    }

    protected abstract String transform(String text);
}

class UpperProcessor extends Processor {
    @Override
    protected String transform(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}

class DashProcessor extends Processor {
    @Override
    protected String transform(String text) {
        return text.replace(" ", "-");
    }
}

public class FinalTemplateDemo {
    public static void main(String[] args) {
        Processor upper = new UpperProcessor();
        Processor dash = new DashProcessor();

        System.out.println(upper.process("  hello java  "));
        System.out.println(dash.process("  hello java  "));
    }
}
```

```bash
javac -encoding UTF-8 FinalTemplateDemo.java
java FinalTemplateDemo
```

**Stdout:**

```text
HELLO JAVA
hello-java
```

Phân tích:
- `Processor.process` là final và luôn kiểm tra null, trim chuỗi đầu vào rồi gọi `transform`.
- `UpperProcessor` và `DashProcessor` không override `process`; chúng chỉ override `transform`.
- Từ khóa `final` bảo vệ **cấu trúc thuật toán** khỏi thay thế trực tiếp bằng subclass.
- Method `transform` vẫn chạy implementation của subclass tương ứng do dynamic dispatch.

**Lưu ý thiết kế:** dù `process` final, hook `transform` có thể ném exception hoặc gây side effect. Không nên khẳng định final tự bảo đảm mọi invariant nếu subclass hook có khả năng phá chúng.

### Khi nào template method không phù hợp?

Nếu subclass không cần kế thừa và bạn chỉ muốn cắm một hàm xử lý, **composition** hoặc một functional interface có thể đơn giản hơn. `final` là công cụ kiểm soát kế thừa, không bắt buộc mọi thiết kế extensibility dùng subclass.

## 8. `final` trên class: cấm `extends`

Khai báo:

```java
public final class Token {
    private final String value;

    public Token(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
```

Với `Token`:
- Caller có thể **tạo instance** bằng constructor public nếu class được truy cập hợp lệ.
- Caller có thể gọi instance method public `value()`.
- Không class nào được khai báo `extends Token` bằng cú pháp kế thừa thông thường.
- `Token` vẫn có thể implement interfaces khi khai báo, sử dụng helper methods, fields, constructors, static factory, v.v.

Ví dụ **không hợp lệ**:

```java
// class AdvancedToken extends Token { }
// SAI: cannot inherit from final Token.
```

Đừng diễn giải “final class không thể bị kế thừa” thành “final class không có instance”, “không có constructor” hoặc “không thể được sử dụng làm kiểu của biến”. Đây là những điều hoàn toàn khác.

## 9. Ví dụ runnable: tạo và sử dụng một final class

Lưu **`FinalClassDemo.java`**:

```java
final class Ticket {
    private final int id;

    Ticket(int id) {
        this.id = id;
    }

    int id() {
        return id;
    }

    String label() {
        return "Ticket-" + id;
    }
}

public class FinalClassDemo {
    public static void main(String[] args) {
        Ticket first = new Ticket(10);
        Ticket second = new Ticket(20);

        System.out.println(first.label());
        System.out.println(second.id());

        // class SpecialTicket extends Ticket { }
        // SAI nếu đưa thành khai báo class: Ticket là final.
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 FinalClassDemo.java
java FinalClassDemo
```

Stdout:

```text
Ticket-10
20
```

Điểm cần quan sát: `Ticket` final **vẫn được khởi tạo hai lần**. Hai instance có state riêng và method riêng theo ngữ nghĩa class. Modifier final chỉ khóa **đường kế thừa**.

### Final class vẫn có thể có constructor private

```java
final class Utility {
    private Utility() {
    }

    static int twice(int value) {
        return value * 2;
    }
}
```

`final` ở đây ngăn subclass, còn private constructor giới hạn việc tạo instance từ lớp độc lập bên ngoài. Hai modifier thực hiện **hai mục tiêu khác nhau**.

## 10. Một final class vẫn có thể `implements` interface

`final` trên class cấm **lớp con**, không cấm **class này cam kết cung cấp hành vi qua interface**.

Ví dụ:

```java
interface Describable {
    String describe();
}

final class Book implements Describable {
    private final String title;

    Book(String title) {
        this.title = title;
    }

    @Override
    public String describe() {
        return "Book: " + title;
    }
}
```

`Book` là final nhưng vẫn triển khai `Describable`. Caller có thể sử dụng biến kiểu interface:

```java
Describable item = new Book("Java");
System.out.println(item.describe()); // Book: Java
```

### Chương trình hoàn chỉnh

Lưu **`FinalImplementsDemo.java`**:

```java
interface Named {
    String name();
}

final class Course implements Named {
    private final String name;

    Course(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}

public class FinalImplementsDemo {
    public static void main(String[] args) {
        Named first = new Course("Java Core");
        Named second = new Course("OOP");

        System.out.println(first.name());
        System.out.println(second.name());
        System.out.println(first instanceof Course);
    }
}
```

```bash
javac -encoding UTF-8 FinalImplementsDemo.java
java FinalImplementsDemo
```

Stdout:

```text
Java Core
OOP
true
```

**Quan trọng:** `final class Course implements Named` **không** biến interface `Named` thành final. Một class khác vẫn có thể implements `Named` theo quy tắc của interface. Điều bị cấm chỉ là `class AdvancedCourse extends Course`.

### Tính đa hình qua interface vẫn tồn tại

Một biến kiểu `Named` có thể tham chiếu object `Course` hoặc object của class khác implements `Named`. Runtime dispatch tới implementation của object vẫn hoạt động. Vì thế `final` trên class không xóa bỏ mọi dạng polymorphism.

## 11. Final class có thể kế thừa class khác không?

**Có.** Một final class có thể **extends một superclass không final và truy cập được**, nhưng chính final class đó **không được có subclass tiếp theo**.

```java
class BaseService {
    String category() {
        return "BASE";
    }
}

final class BillingService extends BaseService {
    @Override
    String category() {
        return "BILLING";
    }
}
```

Mô hình:

```text
BaseService (không final)
       |
       | extends
       v
BillingService (final)
       X
       |
 Không được extends từ BillingService
```

Không có quy tắc “một class được đánh dấu final không thể viết extends”. Hạn chế là **không ai được mở rộng class final sau đó**.

### Có thể override inherited method khi chính subclass được khai báo final

`BillingService` vẫn có thể override method `category()` của `BaseService` vì `BaseService.category` không final và việc override hợp lệ. Từ khóa final trên `BillingService` không cấm **class đó override method kế thừa**; nó cấm **những class con trong tương lai kế thừa BillingService**.

## 12. `final class` không tự biến tất cả method thành `final` về cú pháp

Ví dụ:

```java
final class Counter {
    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
```

Không có subclass hợp lệ để override `increment()` hay `value()` vì class `Counter` là final.

Tuy nhiên, method declarations không bắt buộc phải ghi thêm `final`. Nói đúng là **không thể override chúng thông qua subclass của Counter**, chứ không phải Java tự thay mọi modifier khai báo thành chữ `final` trong source.

Việc thêm `final` vào từng method của final class thường **thừa về mục tiêu chặn subclass override**; có thể được dùng để thể hiện một hợp đồng cụ thể nhưng nên tránh lạm dụng gây rối.

## 13. Final class không đồng nghĩa immutable object

Đây là bẫy lớn trong thiết kế OOP.

```java
final class Counter {
    private int value;

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}
```

Class `Counter` final, nhưng object `Counter` **mutable** vì instance field `value` thay đổi.

### Ví dụ Java 17 chứng minh

Lưu **`FinalNotImmutableDemo.java`**:

```java
final class Counter {
    private int value;

    Counter(int initial) {
        value = initial;
    }

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}

public class FinalNotImmutableDemo {
    public static void main(String[] args) {
        final Counter counter = new Counter(5);

        counter.increment();
        counter.increment();

        System.out.println(counter.value());

        // counter = new Counter(0); // SAI: biến counter final.
        // class ChildCounter extends Counter { } // SAI: class Counter final.
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 FinalNotImmutableDemo.java
java FinalNotImmutableDemo
```

Stdout:

```text
7
```

Ở đây có **hai dạng final đồng thời**:
1. `final Counter counter`: biến local `counter` không được gán tham chiếu mới.
2. `final class Counter`: không được kế thừa `Counter`.

Nhưng `Counter.value` **không final**, method `increment()` thay đổi state nên object mutable.

### Muốn immutable object cần thêm điều kiện

Một thiết kế immutable thường cần kết hợp:
- Giữ state không thể sửa ngoài hợp đồng (thường private fields).
- Field/value initialization hợp lệ.
- Không cung cấp mutator thay trạng thái quan sát được.
- Không làm lộ mutable internal arrays/collections/objects.
- Defensive copy hoặc immutable components khi cần.
- Cẩn thận kế thừa để subclass không phá hợp đồng; `final class` có thể hỗ trợ mục tiêu này, nhưng không đủ một mình.

**`String` là ví dụ tiêu biểu của class final với ngữ nghĩa immutable, nhưng không phải mọi final class đều giống String.** Các class mutable `StringBuilder` và `StringBuffer` cũng được khai báo final trong Java, nên final không tự làm dữ liệu bất biến.

## 14. `final` method cũng không tự ngăn thay trạng thái object

Một phương thức được đánh dấu final vẫn có thể **mutate instance fields**:

```java
class Wallet {
    private int balance;

    public final void deposit(int amount) {
        balance += amount;
    }

    int balance() {
        return balance;
    }
}
```

`deposit` final **không có nghĩa method “chỉ đọc”**. Nó vẫn sửa field `balance`. Chỉ subclass không được thay implementation `deposit` bằng một override.

Nếu method cần bảo vệ invariant, nó nên validate:

```java
public final void deposit(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("positive amount required");
    }
    balance += amount;
}
```

Nhưng vẫn phải cân nhắc tràn số, đồng bộ và hợp đồng nghiệp vụ. `final` **không thay thế validation**.

## 15. `final` và `private`: hai ràng buộc khác nhau

Một method `private` thông thường không được subclass override theo nghĩa đa hình, vì method private **không được kế thừa để override** như public/protected instance method.

Ví dụ:

```java
class Base {
    private void helper() {
        System.out.println("Base helper");
    }

    void run() {
        helper();
    }
}

class Child extends Base {
    public void helper() {
        System.out.println("Child helper");
    }
}
```

`Child.helper()` là method riêng của subclass, **không override** `Base.helper()`.

### Chương trình runnable

Lưu **`PrivateNotOverrideDemo.java`**:

```java
class Base {
    private final void helper() {
        System.out.println("Base helper");
    }

    void run() {
        helper();
    }
}

class Child extends Base {
    public void helper() {
        System.out.println("Child helper");
    }
}

public class PrivateNotOverrideDemo {
    public static void main(String[] args) {
        Child child = new Child();

        child.run();
        child.helper();
    }
}
```

```bash
javac -encoding UTF-8 PrivateNotOverrideDemo.java
java PrivateNotOverrideDemo
```

Stdout:

```text
Base helper
Child helper
```

**Vì sao hợp lệ dù `Base.helper()` có `final`?** Đây là method private của `Base`; `Child.helper()` **không phải override** của method ấy vì private member không tham gia quan hệ overriding tương ứng. `Base.run()` vẫn gọi method private `Base.helper()`.

Điều này khác hoàn toàn với một `public final` hay `protected final` instance method được kế thừa: subclass không thể khai báo lại cùng chữ ký như override.

### Có nên viết `private final`?

`private final void helper()` có thể hợp lệ nhưng thường **không cần thiết cho mục tiêu chống override**, vì private method vốn không được override. Việc thêm `final` chủ yếu tạo sự nhấn mạnh trong source mà không cung cấp lợi ích khóa override như ở public/protected methods.

**Không nhầm private method với một method final không private.**

## 16. Quyền truy cập của method final vẫn được kiểm tra

`final` không phải access modifier. Một method có thể là:

```java
class Example {
    public final void publicAction() {
    }

    protected final void protectedAction() {
    }

    final void packageAction() {
    }

    private final void privateAction() {
    }
}
```

Các mức truy cập vẫn giữ ý nghĩa riêng:

- `public` có thể được gọi từ nơi đủ điều kiện nhìn thấy kiểu và member.
- `protected` có quy tắc cùng package và subclass ngoài package.
- Không ghi modifier → **package-private**.
- `private` giới hạn trực tiếp theo quy tắc của Java, gồm ngữ cảnh cùng nest phù hợp.

`final` chỉ thêm ràng buộc đối với **override/hiding khi có quan hệ tương ứng**, không tự làm method public hay private.

### Ghi chú nâng cao về package-private

Một method package-private ở package A **không được subclass ở package B kế thừa/override theo cách public/protected methods được xử lý**. Khi xem `final` ở tình huống này, phải kết hợp **quy tắc accessibility và inheritance**, không kết luận chỉ vì hai method giống tên/chữ ký thì luôn là override.

Đối với API cho subclass ngoài package, dùng `protected` hoặc `public` nếu thật sự cần cho phép các class con truy cập.

## 17. `final` trên static method: ngăn static hiding, không phải override động

Static method vốn **không** sử dụng dynamic dispatch như instance method. Khi superclass và subclass khai báo static methods cùng chữ ký trong ngữ cảnh hợp lệ, đó thường là **method hiding**, không phải overriding.

Ví dụ khi không final:

```java
class Parent {
    static String label() {
        return "Parent";
    }
}

class Child extends Parent {
    static String label() {
        return "Child";
    }
}
```

`Parent.label()` và `Child.label()` cho kết quả theo tên lớp. Gọi static qua object như `Parent ref = new Child(); ref.label();` tuy có thể biên dịch nhưng gợi ý sai về dynamic dispatch; nên tránh.

### Khi static method là final

```java
class Parent {
    public static final String label() {
        return "Parent";
    }
}

class Child extends Parent {
    // public static String label() { return "Child"; }
    // SAI nếu bỏ comment: không được hide static final method.
}
```

Trong trường hợp này subclass không được khai báo static method cùng chữ ký nhằm hide `Parent.label`.

**Phân biệt từ ngữ:**
- Với instance method: final cấm **override**.
- Với static method: final cấm **hide** khi có quan hệ thành viên thích hợp.

### Ví dụ runnable static final method

Lưu **`StaticFinalMethodDemo.java`**:

```java
class Base {
    public static final String version() {
        return "1.0";
    }

    public static String description() {
        return "BASE";
    }
}

class Derived extends Base {
    public static String description() {
        return "DERIVED";
    }

    // public static String version() { return "2.0"; }
    // SAI nếu bỏ comment: Base.version là final.
}

public class StaticFinalMethodDemo {
    public static void main(String[] args) {
        System.out.println(Base.version());
        System.out.println(Base.description());
        System.out.println(Derived.description());
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 StaticFinalMethodDemo.java
java StaticFinalMethodDemo
```

Stdout:

```text
1.0
BASE
DERIVED
```

`description()` không final nên `Derived` có thể hide bằng static method; `version()` final nên không thể hide theo cùng cách. Không có instance runtime dispatch ở đây.

## 18. Có thể đặt `final` trên constructor không?

**Không.** Constructor không được kế thừa và không bị override như instance method, nên Java không cho khai báo `final` trên constructor.

Ví dụ **sai**:

```java
class Item {
    // final Item() { } // SAI: constructor không nhận modifier final.
}
```

Một constructor có thể là `public`, `protected`, package-private hoặc `private` theo quy tắc, nhưng `final` không phải constructor modifier hợp lệ.

Nếu muốn ngăn **class con**, đánh dấu **class** là `final`:

```java
final class Item {
    Item() {
    }
}
```

Nếu muốn **hạn chế ai được tạo object trực tiếp**, cân nhắc constructor `private`/package-private/protected hoặc một factory API. Đây là các mục tiêu khác nhau.

### Constructor trong final class vẫn hoạt động

`final` class có thể có nhiều constructors, gọi `this(...)`, khởi tạo fields và tạo nhiều instances. Điều duy nhất về kế thừa là không được tạo subclass hợp lệ để gọi các superclass constructors của final class.

## 19. `final` và `abstract` có thể đi cùng nhau không?

Đối với **class** hoặc cùng một **method**, `final` và `abstract` xung đột khi dùng để điều khiển kế thừa theo những khai báo thông thường:

- `abstract class` tồn tại để được subclass cụ thể hóa trước khi tạo instance.
- `final class` cấm tạo subclass.
- `abstract method` yêu cầu có implementation từ subclass thích hợp.
- `final method` cấm override.

Ví dụ không hợp lệ:

```java
// abstract final class InvalidType { }
// SAI: abstract class và final class xung đột.
```

```java
abstract class Parent {
    // abstract final void work();
    // SAI nếu bỏ comment: abstract method không thể final.
}
```

### Nhưng abstract class **có thể chứa final concrete method**

```java
abstract class Base {
    public final void start() {
        System.out.println("Start");
    }

    protected abstract void execute();
}
```

`Base` là abstract, không final. Method `start()` **có implementation cụ thể** và final, còn `execute()` là abstract. Đây là cách thiết kế hợp lệ và thường gặp trong template method pattern.

**Đừng nhầm:** xung đột là đánh dấu *chính class* vừa final vừa abstract, hoặc *chính method* vừa final vừa abstract; một abstract class có final concrete methods là hoàn toàn hợp lệ.

## 20. Lớp con có thể làm một method thành final khi override

Một superclass cung cấp method được phép override. Subclass trung gian có thể **override và đánh dấu implementation của mình là final**, khiến các subclass sâu hơn không được thay tiếp.

```java
class Base {
    String label() {
        return "Base";
    }
}

class Middle extends Base {
    @Override
    final String label() {
        return "Middle";
    }
}

class Leaf extends Middle {
    // String label() { return "Leaf"; }
    // SAI nếu bỏ comment: Middle.label() final.
}
```

Đây là một lựa chọn khi hierarchy cần **mở một lần rồi khóa tiếp** ở một mức.

### Chương trình Java 17 hoàn chỉnh

Lưu **`FinalOverrideChainDemo.java`**:

```java
class Base {
    String label() {
        return "Base";
    }
}

class Middle extends Base {
    @Override
    final String label() {
        return "Middle";
    }
}

class Leaf extends Middle {
    String extra() {
        return "Leaf extra";
    }
}

public class FinalOverrideChainDemo {
    public static void main(String[] args) {
        Base base = new Base();
        Base middle = new Middle();
        Base leaf = new Leaf();

        System.out.println(base.label());
        System.out.println(middle.label());
        System.out.println(leaf.label());
        System.out.println(((Leaf) leaf).extra());
    }
}
```

```bash
javac -encoding UTF-8 FinalOverrideChainDemo.java
java FinalOverrideChainDemo
```

Stdout:

```text
Base
Middle
Middle
Leaf extra
```

`Leaf` vẫn được phép extends `Middle` vì class `Middle` không final. Nhưng `Leaf` không được override `label()` nữa. Điều này cho thấy **final method và final class là hai mức khóa khác nhau**.

## 21. Một subclass có thể triển khai abstract method thành `final`

Khi superclass có abstract method:

```java
abstract class Shape {
    abstract double area();
}
```

Một subclass cụ thể có thể cung cấp **implementation final**:

```java
class FixedSquare extends Shape {
    private final double edge;

    FixedSquare(double edge) {
        this.edge = edge;
    }

    @Override
    final double area() {
        return edge * edge;
    }
}
```

`FixedSquare.area()` hoàn thành yêu cầu abstract method của `Shape` rồi khóa khả năng các subclass tiếp theo override implementation ấy.

Nếu `FixedSquare` không được đánh dấu final class, các subclass của nó có thể có thêm methods/fields khác, nhưng không được override `area()`.

### Lựa chọn giữa final method và final class

- Dùng **final method** khi muốn tiếp tục cho phép mở rộng class nhưng **không cho thay một hành vi cốt lõi**.
- Dùng **final class** khi **không cho tạo thêm subclass** của chính class đó.
- Nếu cả hai đều không cần khả năng subclass, final class thường giúp loại bỏ toàn bộ vấn đề override; không cần gắn final trên mọi method chỉ để ngăn kế thừa.

## 22. Final class và `sealed` trong Java 17

Từ Java 17, **sealed classes/interfaces** cho phép tác giả định nghĩa **tập direct subclasses hoặc implementations được phép**.

Ví dụ:

```java
sealed interface Payment permits Cash, Card {
}

final class Cash implements Payment {
}

non-sealed class Card implements Payment {
}
```

`Cash` được khai báo final: nó là một **nhánh kết thúc** trong hierarchy. `Card` được khai báo non-sealed: nó cho phép hierarchy tiếp tục mở rộng theo những quy tắc khác.

Đối với subclass trực tiếp của sealed class/interface, Java yêu cầu khai báo dạng phù hợp, thường là:
- `final`: không cho nhánh con mở rộng tiếp;
- `sealed`: tiếp tục giới hạn direct subtypes qua `permits`;
- `non-sealed`: bỏ giới hạn sealed cho nhánh đó.

### Chương trình Java 17 hoàn chỉnh

Lưu **`SealedFinalDemo.java`**:

```java
sealed interface Payment permits Cash, Card {
    String label();
}

final class Cash implements Payment {
    @Override
    public String label() {
        return "CASH";
    }
}

non-sealed class Card implements Payment {
    @Override
    public String label() {
        return "CARD";
    }
}

class GiftCard extends Card {
    @Override
    public String label() {
        return "GIFT_CARD";
    }
}

public class SealedFinalDemo {
    public static void main(String[] args) {
        Payment first = new Cash();
        Payment second = new Card();
        Payment third = new GiftCard();

        System.out.println(first.label());
        System.out.println(second.label());
        System.out.println(third.label());

        // class OtherCash extends Cash { }
        // SAI nếu thêm như class: Cash là final.
    }
}
```

```bash
javac -encoding UTF-8 SealedFinalDemo.java
java SealedFinalDemo
```

**Stdout:**

```text
CASH
CARD
GIFT_CARD
```

**Ý nghĩa:** `Payment` sealed không phải “mọi subtype đều final”. Nó kiểm soát **direct permitted subtypes**. Một nhánh có thể final, nhánh khác sealed hoặc non-sealed theo quy tắc.

### `sealed` và `final` không phải hai modifier dùng đồng thời cho cùng class

Không viết `sealed final class X` theo ý nghĩa “chỉ cho phép một số subclass và cấm mọi subclass” — hai yêu cầu xung đột trên cùng kiểu. Chọn một mô hình:
- Không cho subclass → `final class`.
- Cho một tập subtype được phép → `sealed class`/`sealed interface`.
- Cho mở rộng không giới hạn bởi sealed boundary → class thường hoặc `non-sealed` subclass hợp lệ.

Không cần áp dụng sealed hierarchy nếu bài toán chỉ yêu cầu một kiểu value object đơn giản không được kế thừa.

## 23. Record là lớp ngầm định final

Trong Java 17, **record class** được **ngầm định final**. Nó không được subclass bằng `extends`.

```java
record Point(int x, int y) {
}
```

Không thể:

```java
// class Point3D extends Point { }
// SAI: không được extends record Point.
```

Record cũng có superclass đặc biệt là `java.lang.Record` theo định nghĩa ngôn ngữ, chứ không được khai báo `extends SomeClass` khác theo cú pháp class thông thường.

### Record vẫn có thể implements interface

```java
interface Located {
    int x();
}

record Point(int x, int y) implements Located {
}
```

Vì record có accessor `x()` public phù hợp, nó có thể đáp ứng interface method đó theo quy tắc Java.

### Chương trình runnable

Lưu **`FinalRecordClassDemo.java`**:

```java
interface Named {
    String name();
}

record Item(String name) implements Named {
}

public class FinalRecordClassDemo {
    public static void main(String[] args) {
        Named value = new Item("Java");

        System.out.println(value.name());
        System.out.println(value instanceof Item);
    }
}
```

```bash
javac -encoding UTF-8 FinalRecordClassDemo.java
java FinalRecordClassDemo
```

Stdout:

```text
Java
true
```

**Đừng đồng nhất “record là final class” với “mọi record deeply immutable”.** Nếu record component chứa mảng hoặc object mutable, object được tham chiếu ấy vẫn có thể bị thay đổi qua alias. Khả năng kế thừa và mức độ bất biến của state là **hai vấn đề độc lập**.

## 24. Interface không được tuyên bố `final`

Một interface là hợp đồng kiểu được những class khác implements hoặc những interface khác extends theo quy tắc Java. Không dùng `final` để khai báo interface thông thường:

```java
// final interface Printable { }
// SAI: final không phải modifier hợp lệ cho interface.
```

Nếu muốn giới hạn các implementations/subinterfaces, Java 17 có thể dùng **sealed interface** và `permits`, rồi chọn các subtype hợp lệ.

### Không đặt `final` trên interface methods

Trong interface, phương thức public abstract, default, static hoặc private có những tập modifier riêng. Không thể đơn giản thêm `final` vào interface method:

```java
interface Printable {
    void print();

    default void run() {
        print();
    }

    // final default void runAgain() { } // SAI
}
```

Một **class triển khai interface** vẫn có thể khai báo implementation method là final:

```java
class Printer implements Printable {
    @Override
    public final void print() {
        System.out.println("Print");
    }
}
```

Nếu class `Printer` không final, những subclass của nó vẫn không được override `print()`. Method final của class là ràng buộc do **class triển khai**, không phải vì interface method tự final.

## 25. Final method có thể hiện thực hợp đồng interface

Một instance method `public final` có thể thỏa yêu cầu của interface:

```java
interface Executable {
    void execute();
}

class BaseExecutor implements Executable {
    @Override
    public final void execute() {
        System.out.println("Execute");
    }
}

class WorkerExecutor extends BaseExecutor {
    // public void execute() { }
    // SAI nếu bỏ comment: final inherited implementation.
}
```

`WorkerExecutor` vẫn là subtype của `Executable` thông qua superclass và được gọi method `execute()` bình thường.

### Ví dụ Java 17 hoàn chỉnh

Lưu **`FinalInterfaceMethodDemo.java`**:

```java
interface Executable {
    void execute();
}

class BaseExecutor implements Executable {
    @Override
    public final void execute() {
        System.out.println("Base execution");
    }
}

class WorkerExecutor extends BaseExecutor {
    void extra() {
        System.out.println("Worker extra");
    }
}

public class FinalInterfaceMethodDemo {
    public static void main(String[] args) {
        Executable first = new BaseExecutor();
        Executable second = new WorkerExecutor();

        first.execute();
        second.execute();
        ((WorkerExecutor) second).extra();
    }
}
```

```bash
javac -encoding UTF-8 FinalInterfaceMethodDemo.java
java FinalInterfaceMethodDemo
```

Stdout:

```text
Base execution
Base execution
Worker extra
```

Class `WorkerExecutor` **không override `execute()`**; nó kế thừa implementation final. Nhưng object của nó vẫn thỏa interface `Executable`.

## 26. `final` không thay đổi access modifier hoặc module exports

Một final class có thể là:

```java
public final class PublicApi {
}
```

hoặc package-private:

```java
final class InternalImplementation {
}
```

- `public` và package-private quyết định ai được phép sử dụng kiểu theo Java access rules.
- `final` quyết định có được khai báo subclass hay không.

Tương tự `public final void work()` là public final method; `private final void helper()` có private access. Không có quan hệ “final thì tự private”.

### Nếu dùng Java modules

Một `public final class` nằm trong package **không được module export** vẫn có thể không truy cập trực tiếp được từ module khác.

`final` không mở package và không thay ``requires`/`exports`/`opens` trong JPMS. Đây là tầng **module boundary**, độc lập với kế thừa.

Khi xem một lỗi import, cần xác định nó do visibility của kiểu/module hay do yêu cầu kế thừa class final, không sửa modifier final tùy tiện.

## 27. `final` trên nested class

**Member nested class** cũng có thể là final:

```java
class Outer {
    static final class Nested {
        String value() {
            return "Nested";
        }
    }
}
```

`Outer.Nested` là một static nested class, không có enclosing `Outer` instance ngầm định. Từ khóa final ngăn subclass của `Nested`, còn `static` quyết định quan hệ với instance outer.

### Non-static inner class cũng có thể final

```java
class Outer {
    final class Inner {
        String text() {
            return "Inner";
        }
    }
}
```

`Inner` là non-static member inner class: để tạo từ bên ngoài trong ngữ cảnh cho phép, cần outer instance như `outer.new Inner()`. Nó final nên không được subclass.

**Static và final là hai trục riêng**:
- `static nested`: không cần enclosing instance.
- `final nested`: không cho kế thừa nested type đó.

### Chương trình runnable

Lưu **`FinalNestedDemo.java`**:

```java
public class FinalNestedDemo {
    static final class Nested {
        String label() {
            return "Nested";
        }
    }

    final class Inner {
        String label() {
            return "Inner";
        }
    }

    public static void main(String[] args) {
        Nested nested = new Nested();
        FinalNestedDemo outer = new FinalNestedDemo();
        Inner inner = outer.new Inner();

        System.out.println(nested.label());
        System.out.println(inner.label());
    }
}
```

```bash
javac -encoding UTF-8 FinalNestedDemo.java
java FinalNestedDemo
```

Stdout:

```text
Nested
Inner
```

Việc cả hai nested classes final không ngăn tạo thể hiện của chúng trong ngữ cảnh truy cập hợp lệ.

## 28. `final` class có cản anonymous subclass không?

**Có.** Một anonymous class khai báo theo cú pháp `new SomeClass() { ... }` là một dạng **subclass** của `SomeClass`, nên không thể dùng cách đó để mở rộng một class final.

Ví dụ:

```java
final class Service {
    void run() {
    }
}

// Service service = new Service() {
//     @Override
//     void run() { }
// };
// SAI: anonymous subclass của final class.
```

Nhưng tạo object trực tiếp **không có class body** vẫn hợp lệ nếu constructor truy cập được:

```java
Service service = new Service();
service.run();
```

### Phân biệt anonymous class implementing interface

Có thể viết:

```java
Runnable action = new Runnable() {
    @Override
    public void run() {
        System.out.println("Running");
    }
};
```

Ở đây anonymous class **implements interface `Runnable`**, không subclass một final class. Interface và final class có vai trò khác nhau.

Nếu framework sử dụng subclass-based proxy để can thiệp hành vi, final class/final methods có thể ảnh hưởng khả năng tạo proxy kiểu subclass. Một số framework/công cụ có kỹ thuật khác như delegation hoặc instrumentation; không nên kết luận mọi công cụ mock đều không bao giờ xử lý được final types.

## 29. `Object.getClass()` là ví dụ method final trong JDK

Class `java.lang.Object` khai báo method:

```java
public final native Class<?> getClass();
```

Method `getClass()` trả đối tượng `Class` biểu diễn **runtime class** của receiver. Đây là một final method của superclass chung cho các lớp Java, nên subclass không thể override `getClass()`.

Ví dụ:

```java
class Sample {
}
```

```java
Object value = new Sample();
System.out.println(value.getClass().getSimpleName());
```

Kết quả thường là `Sample` với class thông thường có tên đúng như đoạn minh họa. `getClass()` có method implementation được bảo đảm không bị subclass override, dù nó phản ánh runtime class của object.

**Đừng nhầm:** final method không nhất thiết luôn trả một giá trị cố định; `getClass()` final nhưng kết quả phụ thuộc object receiver.

Một số methods khác của `Object` cũng final theo đặc tả, nhưng bạn nên dựa vào JDK API thay vì tự suy diễn method nào “chắc chắn final”.

## 30. Method final vẫn có thể gọi method override được

Một method final có thể chứa lời gọi đến một method khác **không final**. Khi chạy với subclass receiver, lời gọi bên trong vẫn có thể dispatch động.

Ví dụ:

```java
class Parent {
    public final String build() {
        return "Result=" + value();
    }

    protected String value() {
        return "base";
    }
}

class Child extends Parent {
    @Override
    protected String value() {
        return "child";
    }
}
```

Với `Parent p = new Child(); p.build();`, kết quả là `Result=child`.

Method `build` **không bị override**: nó thực hiện implementation duy nhất của `Parent`. Nhưng nó gọi method `value` (một hook có thể override), nên **kết quả đầu ra vẫn phụ thuộc runtime subclass**.

### Chương trình runnable

Lưu **`FinalCallsVirtualDemo.java`**:

```java
class Parent {
    public final String build() {
        return "Result=" + value();
    }

    protected String value() {
        return "base";
    }
}

class Child extends Parent {
    @Override
    protected String value() {
        return "child";
    }
}

public class FinalCallsVirtualDemo {
    public static void main(String[] args) {
        Parent parent = new Parent();
        Parent child = new Child();

        System.out.println(parent.build());
        System.out.println(child.build());
    }
}
```

```bash
javac -encoding UTF-8 FinalCallsVirtualDemo.java
java FinalCallsVirtualDemo
```

Stdout:

```text
Result=base
Result=child
```

**Rút ra:** final khóa override của **method được đánh dấu final**, không biến mọi lời gọi bên trong nó thành static binding. Vì vậy cần hiểu toàn bộ extension points nếu một invariant bắt buộc phải được bảo vệ.

## 31. Thiết kế API: khi nào chọn final method?

Nên cân nhắc **final method** khi:

1. Có một **entry point** cần luôn chạy kiểm tra, normalization hoặc kiểm soát vòng đời không được subclass bỏ qua bằng override.
2. Class là một **base class có chủ đích cho extension**, nhưng chỉ một số hooks được phép thay.
3. API có ràng buộc hợp đồng bắt buộc và lớp con vẫn cần được mở rộng bằng những method khác.
4. Muốn ngăn subclass thay đổi một implementation sau khi đã được cố định trong hierarchy.

Ví dụ một base class cho quy trình validate rồi thực thi:

```java
abstract class Job {
    public final void run() {
        validate();
        execute();
    }

    private void validate() {
        // Kiểm tra điều kiện chung.
    }

    protected abstract void execute();
}
```

Tuy nhiên, nếu `execute` có thể gây side effect phá invariant, `final run` không giải quyết hoàn toàn. Bạn cần thiết kế hợp đồng hook, exception handling, synchronization và ownership phù hợp.

### Khi nào không nên final method?

- Bạn **thực sự muốn subclass thay implementation của method đó**.
- Framework cần override cụ thể để cung cấp behavior hoặc proxy theo thiết kế của bạn.
- Method là extension point công khai và hành vi override là một phần hợp đồng API.
- Bạn chưa xác định rõ vì sao cần khóa override; thêm final không có căn cứ có thể làm thư viện khó mở rộng.

Một khi phát hành public API, việc đổi một method từ override-được sang final có thể làm **mã subclass đang tồn tại không biên dịch hoặc không liên kết tương thích**, nên cần cân nhắc tương thích nguồn và nhị phân.

## 32. Thiết kế API: khi nào chọn final class?

Nên cân nhắc **final class** khi:

1. Class là **value object** hoặc kiểu biểu diễn không dự kiến mở rộng bằng kế thừa.
2. Bạn muốn giữ quyền kiểm soát invariant mà subclass không thể thay qua kế thừa.
3. Class là **utility**, implementation detail hoặc đối tượng có vòng đời rõ, không được thiết kế làm superclass.
4. Bạn cung cấp extensibility qua **interface/composition** thay vì ép người dùng extends một implementation cụ thể.
5. Muốn đơn giản hóa giả định về loại runtime object của class theo thiết kế.

Nhưng final class có thể gây trở ngại khi:
- Người dùng cần subclass để mở rộng framework.
- Một framework sử dụng proxy bằng subclass.
- Các bài kiểm thử/mock dựa vào subclass-based overriding thay vì interface hoặc instrumentation.
- Bạn muốn thư viện hỗ trợ mở rộng bằng inheritance có chủ đích.

**Không có một quy tắc “mọi class phải final” áp dụng cho mọi ứng dụng.** Hãy xác định chiến lược extensibility rõ ràng.

### Composition thay cho inheritance

Nếu muốn cho người dùng thay thuật toán trong khi giữ một service class final, có thể inject một interface:

```java
interface Formatter {
    String format(String input);
}

final class DisplayService {
    private final Formatter formatter;

    DisplayService(Formatter formatter) {
        this.formatter = formatter;
    }

    String display(String value) {
        return formatter.format(value);
    }
}
```

Subclass của `DisplayService` không được tạo, nhưng hành vi format có thể thay qua **object implements Formatter**.

### Ví dụ chạy được

Lưu **`FinalCompositionDemo.java`**:

```java
import java.util.Locale;

interface Formatter {
    String format(String text);
}

final class DisplayService {
    private final Formatter formatter;

    DisplayService(Formatter formatter) {
        this.formatter = formatter;
    }

    String display(String text) {
        return formatter.format(text);
    }
}

public class FinalCompositionDemo {
    public static void main(String[] args) {
        Formatter upper = text -> text.toUpperCase(Locale.ROOT);
        Formatter bracket = text -> "[" + text + "]";

        DisplayService first = new DisplayService(upper);
        DisplayService second = new DisplayService(bracket);

        System.out.println(first.display("java"));
        System.out.println(second.display("java"));
    }
}
```

```bash
javac -encoding UTF-8 FinalCompositionDemo.java
java FinalCompositionDemo
```

Stdout:

```text
JAVA
[java]
```

`DisplayService` final nhưng nhận các implementations khác nhau của `Formatter`. Đây là ví dụ “**đóng implementation bằng final class, mở behavior bằng interface/composition**”.

## 33. Final class, abstract class và sealed class: bảng quyết định

| Nhu cầu | Lựa chọn Java thường gặp | Ý nghĩa |
| --- | --- | --- |
| Không ai được subclass class này | `final class` | Khóa toàn bộ class inheritance |
| Cần base class có method trừu tượng | `abstract class` | Subclass phải hoàn thành contract để thành concrete |
| Chỉ một nhóm lớp được phép kế thừa trực tiếp | `sealed class` với `permits` | Giới hạn trực tiếp permitted subtypes |
| Cho phép mở rộng class nhưng khóa một method | `final instance method` | Class vẫn subclass-được; method bị khóa override |
| Cho phép thay vài bước thuật toán | `final template method` + non-final/abstract hooks | Giữ quy trình chính, cho phép extension có kiểm soát |
| Muốn caller chọn nhiều chiến lược mà không extends implementation | Interface + composition | Mở rộng bằng đối tượng cộng tác |
| Một record dữ liệu đơn giản | `record` | Tự ngầm final, có value-oriented API nhưng không tự deep immutable |

Chọn theo **mục tiêu của hệ thống**, không chỉ để loại bỏ một lỗi compile nhất thời.

## 34. Những kết luận sai phổ biến

| Kết luận sai | Điều đúng |
| --- | --- |
| “Final method không được gọi từ subclass” | Được gọi/kế thừa nếu truy cập hợp lệ; chỉ không được override |
| “Final method cấm mọi method cùng tên” | Overload với chữ ký khác vẫn hợp lệ |
| “Chỉ cần bỏ `@Override` là override final được” | Không, lỗi nằm ở attempt override |
| “Static final method có dynamic dispatch” | Static method không override động; final có thể ngăn hiding |
| “Private final method khiến subclass không được khai báo cùng tên” | Private method không được kế thừa để override như method public/protected; cùng tên ở subclass có thể là method riêng |
| “Final class không thể khởi tạo” | Có thể tạo object nếu constructor truy cập được |
| “Final class không thể implements interface” | Hoàn toàn có thể |
| “Final class không thể extends bất kỳ class nào” | Có thể extends superclass không final; không thể bị subclass tiếp |
| “Mọi method của final class phải ghi final” | Không bắt buộc; class final đã không thể có subclass |
| “Final class là immutable” | Không; mutable fields/mutators vẫn có thể tồn tại |
| “Final method là read-only” | Không; method final vẫn có thể cập nhật state |
| “Final là access modifier” | Không; `public`/`protected`/package-private/`private` là khía cạnh khác |
| “Constructor có thể final vì không muốn override” | Constructor không override và không được dùng modifier final |
| “Abstract final class giúp subclass triển khai có kiểm soát” | Hai modifier xung đột trên cùng class |
| “Interface method có thể final như class method” | Interface không hỗ trợ final method modifier kiểu đó |
| “Một lớp sealed và final cùng lúc cho an toàn hơn” | Hai trạng thái xung đột trên cùng class |
| “Record final nên chứa mảng immutable” | Record class final nhưng mảng component vẫn có thể mutable |
| “Final chắc chắn làm mọi lời gọi nhanh hơn” | Không có cam kết hiệu năng như vậy |
| “Final ngăn mọi framework mock/proxy” | Phụ thuộc kỹ thuật; các proxy subclass bị hạn chế, nhưng có kỹ thuật khác |
| “Final method gọi hook thì hook cũng bị khóa” | Hook không final vẫn có thể override và dispatch động |

## 35. Bài tập tự kiểm tra có đáp án

### Bài 1 — Overriding một final method

```java
class A {
    final void work() {
    }
}

class B extends A {
    // void work() { }
}
```

**Câu hỏi:** bỏ comment `B.work()` có hợp lệ không?

**Đáp án:** **Không.** `B.work()` sẽ override `A.work()` vốn final. Bỏ `@Override` không làm thay đổi bản chất quan hệ override.

### Bài 2 — Overload với một method final

```java
class A {
    final void work(int id) {
    }
}

class B extends A {
    void work(String name) {
    }
}
```

**Đáp án:** hợp lệ. `work(String)` và `work(int)` là hai chữ ký khác nhau. `B` kế thừa `A.work(int)` và thêm overload riêng.

### Bài 3 — Final class có constructor không?

```java
final class Key {
    Key() {
    }
}
```

**Đáp án:** Có. `new Key()` hợp lệ từ ngữ cảnh có quyền gọi constructor (ví dụ cùng package). Nhưng `class SubKey extends Key` không hợp lệ.

### Bài 4 — Final class implements interface

```java
interface Named {
    String name();
}

final class User implements Named {
    @Override
    public String name() {
        return "An";
    }
}
```

**Đáp án:** hợp lệ. Final class không được subclass, nhưng hoàn toàn có thể implement interface và được dùng qua biến kiểu `Named`.

### Bài 5 — Final class vẫn có mutable field?

```java
final class Box {
    int value;
}

Box box = new Box();
box.value = 5;
box.value = 8;
System.out.println(box.value);
```

**Đáp án:** in `8` trong ngữ cảnh truy cập field hợp lệ. `final class` chỉ khóa kế thừa, không tự biến instance fields thành final hoặc private.

### Bài 6 — Final instance method được gọi qua subclass?

```java
class Base {
    final String label() {
        return "Base";
    }
}

class Child extends Base {
}

System.out.println(new Child().label());
```

**Đáp án:** in `Base`. Method final vẫn được kế thừa/gọi. Subclass chỉ không được override.

### Bài 7 — Static final hiding

```java
class Base {
    static final String version() {
        return "1";
    }
}

class Child extends Base {
    // static String version() { return "2"; }
}
```

**Đáp án:** bỏ comment gây lỗi vì `Child` cố hide static final method tương ứng. Static không có overriding động, nhưng final vẫn có giới hạn với hiding.

### Bài 8 — Override và `final` ở lớp trung gian

```java
class Base {
    String value() {
        return "A";
    }
}

class Middle extends Base {
    @Override
    final String value() {
        return "B";
    }
}

class Leaf extends Middle {
}
```

**Đáp án:** `new Leaf().value()` trả `B`. `Middle` được override method không final của `Base` rồi khóa việc override tiếp ở `Leaf`.

### Bài 9 — Final method gọi một hook

```java
class Parent {
    final String message() {
        return text();
    }

    String text() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    String text() {
        return "child";
    }
}
```

**Đáp án:** `new Child().message()` trả `child`. `message()` final không thể override, nhưng nó gọi `text()` không final nên virtual dispatch vẫn chọn `Child.text()`.

### Bài 10 — Constructor final?

```java
class A {
    // final A() { }
}
```

**Đáp án:** cú pháp constructor mang `final` không hợp lệ. Constructor không được kế thừa/override; nếu muốn ngăn subclass thì khai báo `final class A`.

### Bài 11 — Abstract class có final method được không?

```java
abstract class Base {
    final void validate() {
        System.out.println("OK");
    }

    abstract void work();
}
```

**Đáp án:** hợp lệ. `Base` abstract, `validate()` concrete và final; chỉ `work()` là abstract cần được triển khai phù hợp.

### Bài 12 — Record và `final`

```java
record Point(int x, int y) {
}
```

**Đáp án:** class `Point` ngầm định final, không được extends. Nhưng vẫn có thể khởi tạo `new Point(1, 2)` và có thể implements interface khi khai báo.

### Bài 13 — Sealed hierarchy

```java
sealed interface Result permits Success, Failure {
}

final class Success implements Result {
}

non-sealed class Failure implements Result {
}
```

**Đáp án:** `Success` kết thúc nhánh, không có subclass. `Failure` có thể được subclass theo quy tắc của class bình thường vì `non-sealed`. Các declared direct implementations đã được liệt kê trong permits của `Result`.

### Bài 14 — Final class và collection mutable

```java
final class Basket {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    void add(String name) {
        items.add(name);
    }

    int size() {
        return items.size();
    }
}
```

**Đáp án:** `Basket` không được subclass, field `items` không được gán lại nhưng list vẫn có thể thêm/xóa theo API. Không thể suy ra object immutable/thread-safe.

### Bài 15 — Final hay interface + composition?

Bạn muốn cung cấp một lớp `ReportService` không dự kiến cho subclass, nhưng caller cần chọn giữa formatter CSV và JSON.

**Đáp án gợi ý:** dùng `final class ReportService` phụ thuộc một `Formatter` interface, để caller truyền implementation phù hợp. Cách này mở rộng hành vi bằng composition mà không buộc extends `ReportService`.

## 36. Checklist khi dùng `final` trên method/class

1. **Bạn muốn khóa method hay toàn bộ hierarchy?** Chọn `final method` hoặc `final class` theo phạm vi mong muốn.
2. **Method đang final là instance hay static?** Instance liên quan overriding; static liên quan hiding.
3. **Method có cần được subclass gọi không?** Final method vẫn kế thừa/gọi được nếu access hợp lệ.
4. **Có cần overload không?** Final không cấm overload khác chữ ký.
5. **Có đang dùng `@Override` để cố viết lại method final?** Bỏ annotation không giải quyết.
6. **Có hook không final trong một final template method không?** Hiểu rằng hook vẫn dispatch động.
7. **Lớp final có cần khởi tạo instance không?** Final không cấm constructor thông thường.
8. **Lớp final có cần implement interface không?** Vẫn hợp lệ, miễn thỏa interface contract.
9. **Lớp final có thể extends class cha không?** Có, nếu class cha không final và các quy tắc khác thỏa.
10. **Phân biệt final class và immutable object:** đã kiểm soát mutable state/alias chưa?
11. **Phân biệt final method và pure/read-only method:** method final vẫn có thể sửa dữ liệu.
12. **Nếu method private, có cần thêm final không?** Private không được override theo cách thông thường.
13. **Nếu method package-private**, đã xem package/access rules trước khi kết luận subclass override chưa?
14. **Nếu superclass method static**, đang nói hiding hay overriding?
15. **Nếu thiết kế abstract base class**, final concrete methods hợp lệ, nhưng abstract final trên chính method thì không.
16. **Nếu thiết kế sealed hierarchy**, direct subclasses có modifier phù hợp chưa? Đừng đồng thời sealed và final trên cùng class.
17. **Nếu dùng record**, nhớ record ngầm định final nhưng component mutable vẫn có thể làm lộ state.
18. **Nếu dùng interface**, không đánh dấu interface hoặc các interface methods thành final; dùng sealed interface hay final implementation class theo nhu cầu.
19. **Nếu framework cần proxy/subclass**, final class hoặc final method có ảnh hưởng không? Có API qua interface/delegation phù hợp chưa?
20. **Nếu đổi public API đã phát hành**, đã đánh giá compatibility của việc khóa override/subclass?
21. **Nếu mục tiêu là hiệu năng**, đã benchmark chưa? Không coi final là lệnh bảo đảm inline.
22. **Nếu báo lỗi compiler**, phân biệt lỗi extends final class, override final instance method, hide static final method hoặc access/type mismatch.
23. **Nếu chương trình có mutable shared state**, đã xử lý validation, encapsulation và thread safety riêng chưa?
24. **Nếu muốn cung cấp điểm mở rộng an toàn**, hãy mô tả rõ những method được phép override và những invariant mà final method phải giữ.

## Ghi nhớ

- **`final` trên instance method ngăn overriding**, không ngăn **gọi/kế thừa** method và không ngăn **overloading** bằng chữ ký khác.
- **`final` trên static method ngăn hiding hợp lệ ở subclass**, không biến static method thành dynamic-dispatch method.
- **`final class` ngăn mọi class khác extends class ấy**, nhưng chính class ấy **có thể extends superclass**, **implements interface**, có constructor và tạo nhiều objects.
- **`final` trên class và method không bảo đảm immutable state**. Mutable fields, mutable components và side effects vẫn có thể tồn tại.
- **`private`/`public` và `final` độc lập**: access modifier quyết định khả năng truy cập, `final` quyết định khả năng thay behavior qua kế thừa.
- **Constructor không thể final**, và **abstract + final** không dùng đồng thời cho cùng một class/method khi chúng xung đột.
- **Final method có thể gọi non-final hook**: chính method final không override được, nhưng hook vẫn có thể dispatch theo subclass.
- Trong **sealed hierarchy** của Java 17, `final` giúp kết thúc nhánh được cho phép. **Record** cũng là class ngầm định final.
- Chọn `final` để biểu đạt **hợp đồng mở rộng rõ ràng**, không chỉ để “cho chắc” hoặc kỳ vọng tốc độ; nếu cần mở behavior mà không mở inheritance, hãy dùng **interface + composition**.
