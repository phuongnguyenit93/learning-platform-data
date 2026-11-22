# Thứ tự khởi tạo lớp cha, trường đối tượng, khối khởi tạo và thân hàm khởi tạo trong Java

## 1. Mục tiêu: đọc được thứ tự khi viết `new Child()`

Một object trong Java không được tạo ra bằng cách “chạy thân constructor từ dòng đầu đến dòng cuối” đơn giản như nhiều người mới học hình dung. Khi một lớp kế thừa lớp khác, quy trình còn liên quan đến:

- **Khởi tạo lớp (*class initialization*)**: các static field initializers và static initializer blocks cần chạy theo quy tắc trước khi class được sử dụng chủ động.
- **Giá trị mặc định của các instance fields**: bộ nhớ cho object được cấp phát và các trường bắt đầu ở giá trị mặc định của kiểu.
- **Constructor của lớp cha**: quá trình khởi tạo instance của superclass diễn ra trước khi các instance initializers của subclass chạy.
- **Instance field initializers của lớp con**: các biểu thức gán giá trị ban đầu cho trường đối tượng.
- **Instance initialization blocks của lớp con**: những khối `{ ... }` trực tiếp trong thân class, không có từ khóa `static`.
- **Thân constructor của lớp con**: các lệnh sau `super(...)` hoặc `this(...)` trong constructor được chọn.

Ví dụ:

```java
class Parent {
    Parent() {
        System.out.println("Parent constructor");
    }
}

class Child extends Parent {
    int age = 10;

    {
        System.out.println("Child instance block");
    }

    Child() {
        System.out.println("Child constructor");
    }
}
```

Khi chạy `new Child()`, thứ tự không phải “Child constructor trước vì gọi Child”. Trước khi phần thân `Child()` chạy, constructor của `Parent` và những initializers của `Child` phải thực thi theo quy tắc.

**Kết luận cần nắm ngay:** Với trường hợp bình thường, **constructor lớp cha hoàn tất → field initializers và instance blocks của lớp con chạy theo thứ tự source → phần thân constructor lớp con chạy**. Nếu có nhiều tầng kế thừa, quy tắc này áp dụng lặp theo chuỗi constructor.

Các ngoại lệ và chi tiết như `this(...)`, đối số `super(...)`, static initialization, lời gọi method bị override từ superclass constructor, và exception trong quá trình tạo object sẽ được giải thích lần lượt.

## 2. Phân biệt hai tiến trình: khởi tạo lớp và khởi tạo đối tượng

Không thể dự đoán output nếu trộn lẫn *class initialization* với *instance initialization*.

| Thành phần | Thuộc về | Khi nào chạy? |
| --- | --- | --- |
| `static int count = init();` | Class | Trong quá trình khởi tạo class, một lần cho mỗi runtime class được initialize thành công |
| `static { ... }` | Class | Trong quá trình khởi tạo class, theo thứ tự source |
| `int id = initId();` | Mỗi object | Mỗi lần instance tương ứng được khởi tạo |
| `{ ... }` (không có `static`) | Mỗi object | Mỗi lần instance được khởi tạo, theo thứ tự source cùng instance field initializers |
| `Parent(...)` constructor | Superclass subobject | Trong constructor chain khi tạo instance subclass |
| `Child(...)` constructor body | Subclass | Sau superclass construction và instance initializers của Child trong chuỗi gọi hợp lệ |

Một class có thể được khởi tạo từ trước vì gọi static method, đọc non-constant static field hoặc một số thao tác khác. Vì vậy ở lần `new Child()`, **có thể không còn static initializer nào phải chạy**.

Trong ví dụ chạy ở một tiến trình mới, ta thường thấy static initialization trước việc khởi tạo instance lần đầu. Nhưng **static block không chạy lại** ở mỗi lần tạo object.

### Sơ đồ cho trường hợp Child extends Parent

```text
Lần đầu chủ động sử dụng Child:
    Class initialization Parent (nếu cần)
        └── static field initializers / static blocks của Parent
    Class initialization Child (nếu cần)
        └── static field initializers / static blocks của Child

Sau đó tạo object Child:
    Các instance fields bắt đầu ở giá trị mặc định
        ↓
    Gọi constructor chain của Parent
        ├── instance field initializers của Parent
        ├── instance initialization blocks của Parent
        └── thân constructor Parent
        ↓
    Instance field initializers và blocks của Child
       (theo thứ tự xuất hiện trong source)
        ↓
    Thân constructor Child
        ↓
    Có thể dùng object sau khi constructor trả về thành công
```

Sơ đồ này minh họa **constructor chain đơn giản** không có `this(...)` forwarding giữa nhiều overload, không có exception và không có các side effects từ việc đánh giá arguments. Phần sau sẽ bổ sung các chi tiết ấy.

## 3. Chương trình đầu tiên: in thứ tự từ lớp cha đến lớp con

Tạo tệp **`ParentChildOrderDemo.java`**:

```java
class Parent {
    static {
        System.out.println("P.static");
    }

    private int parentValue = print("P.field", 10);

    {
        System.out.println("P.instanceBlock");
    }

    Parent() {
        System.out.println("P.constructor");
    }

    static int print(String label, int value) {
        System.out.println(label);
        return value;
    }
}

class Child extends Parent {
    static {
        System.out.println("C.static");
    }

    private int childValue = print("C.field", 20);

    {
        System.out.println("C.instanceBlock");
    }

    Child() {
        System.out.println("C.constructor");
    }
}

public class ParentChildOrderDemo {
    public static void main(String[] args) {
        System.out.println("main.before");
        new Child();
        System.out.println("main.after");
    }
}
```

Biên dịch và chạy trên **JDK 17+**:

```bash
javac ParentChildOrderDemo.java
java ParentChildOrderDemo
```

**Standard output:**

```text
main.before
P.static
C.static
P.field
P.instanceBlock
P.constructor
C.field
C.instanceBlock
C.constructor
main.after
```

**Đọc output theo từng giai đoạn:**

1. `main.before` xuất hiện trước khi tạo Child.
2. Lệnh `new Child()` kích hoạt initialization của `Parent` rồi `Child` nếu cả hai chưa được initialize: in `P.static`, `C.static`.
3. Trong instance construction, `Parent` field initializer in `P.field`.
4. Parent instance block in `P.instanceBlock`.
5. Constructor body của Parent in `P.constructor`.
6. Sau khi phần Parent hoàn tất, field initializer của Child in `C.field`.
7. Child instance block in `C.instanceBlock`.
8. Constructor body của Child in `C.constructor`.
9. Khi `new Child()` hoàn tất, main in `main.after`.

`parentValue` và `childValue` được giữ để minh họa instance fields; Java cho phép chúng không được dùng ở phần còn lại của ví dụ. Lời gọi `print` không làm đảo thứ tự, vì helper chỉ in thông báo và trả giá trị.

## 4. Tại sao constructor lớp cha chạy trước?

Một `Child` object cũng mang phần state và hành vi kế thừa từ `Parent`. Trước khi thân constructor của Child chạy, Java phải thực hiện quy trình khởi tạo thích hợp đối với superclass.

Với constructor không ghi invocation đầu tiên trong Java 17:

```java
class Parent {
    Parent() {
        System.out.println("Parent()");
    }
}

class Child extends Parent {
    Child() {
        System.out.println("Child()");
    }
}
```

Compiler hiểu constructor `Child()` như có lời gọi ngầm tới **`super()`** ở đầu:

```java
Child() {
    super(); // Minh họa lời gọi được chèn ngầm.
    System.out.println("Child()");
}
```

Đây là **phiên bản minh họa tương đương về mặt ý nghĩa**, không khai báo hai constructors cùng chữ ký trong cùng một class.

Nếu constructor cha có thể được gọi mà không có đối số, việc không viết `super()` thường hợp lệ. Nếu superclass không có constructor không tham số accessible, subclass phải gọi một constructor thích hợp bằng `super(args)`; nếu không, compilation fail.

**Lưu ý:** Constructor không phải method thông thường; `super(...)` gọi **một constructor** thuộc superclass, không phải `super.someMethod(...)`.

## 5. Quy tắc Java 17: `this(...)` hoặc `super(...)` là lời gọi constructor đầu tiên

Trong Java 17, explicit constructor invocation `this(...)` hoặc `super(...)`, nếu có, phải là **câu lệnh đầu tiên trong constructor body** theo cú pháp áp dụng.

Ví dụ hợp lệ:

```java
class Parent {
    Parent(int id) {
        System.out.println("Parent: " + id);
    }
}

class Child extends Parent {
    Child(int id) {
        super(id);
        System.out.println("Child: " + id);
    }
}
```

Đoạn cố ý sai:

```java
// Child(int id) {
//     System.out.println("before super");
//     super(id); // Sai trong Java 17: không phải statement đầu tiên.
// }
```

**Không đặt instance statements trước `super(...)`** với các ví dụ Java 17. Một số phiên bản Java mới hơn có thay đổi ngôn ngữ liên quan *flexible constructor bodies*, nên khi học theo phiên bản phải xem đúng version. Tài liệu này sử dụng **Java 17** để tránh lẫn quy tắc phiên bản.

Bên trong constructor, bạn có thể chọn **một** explicit constructor invocation đầu tiên:

- `super(args)` để gọi constructor trực tiếp của superclass.
- `this(args)` để chuyển tiếp đến một constructor khác **trong cùng class**.

Không thể vừa gọi `this(...)` vừa gọi `super(...)` như hai lời gọi đứng cạnh nhau trong cùng constructor body. Với `this(...)`, constructor đích sẽ tiếp tục chuỗi tới superclass đúng quy tắc.

## 6. Instance field initializers và instance blocks chạy theo thứ tự source

Trong **cùng một class**, các instance field initializers và instance initialization blocks được xử lý theo **thứ tự xuất hiện trong source**.

Tệp **`InstanceSourceOrderDemo.java`**:

```java
public class InstanceSourceOrderDemo {
    private int first = mark("field-first", 1);

    {
        System.out.println("block-A");
    }

    private int second = mark("field-second", 2);

    {
        System.out.println("block-B");
    }

    InstanceSourceOrderDemo() {
        System.out.println("constructor");
    }

    private static int mark(String label, int value) {
        System.out.println(label);
        return value;
    }

    public static void main(String[] args) {
        new InstanceSourceOrderDemo();
    }
}
```

```bash
javac InstanceSourceOrderDemo.java
java InstanceSourceOrderDemo
```

```text
field-first
block-A
field-second
block-B
constructor
```

Dù `mark` là static method được khai báo cuối file, các initializer có thể gọi nó. Phần thân method được định nghĩa ở đâu không làm nó tự động chạy trước.

**Cách nhớ:** Java không “chạy tất cả field initializers trước rồi mới tới tất cả instance blocks”. Chúng **đan xen theo thứ tự textual/source** trong một class.

### Thay thứ tự khai báo có thể thay output

Nếu bạn chuyển block `{ System.out.println("block-B"); }` lên trước khai báo `second`, output cũng đổi tương ứng. Điều này có ý nghĩa khi initializer đọc state vừa được gán hoặc tạo resource phụ thuộc nhau.

## 7. Giá trị mặc định có trước những giá trị được initializer gán

Khi object được cấp phát, instance fields bắt đầu với **giá trị mặc định**:

| Field type | Default value |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` |
| `float`, `double` | `0.0` |
| `char` | Ký tự `'\u0000'` |
| `boolean` | `false` |
| Kiểu tham chiếu | `null` |

Các giá trị này xuất hiện **trước** khi instance field initializers và constructor body gán các giá trị tùy chỉnh. Compiler/JVM bảo đảm trường có trạng thái mặc định phù hợp theo ngữ nghĩa, không phải cho phép code dùng local variables chưa khởi tạo.

**Khác biệt:** local variables **không được tự động khởi tạo mặc định** như instance fields. Một local `int n;` phải được definite assigned trước khi đọc.

### Không đoán rằng khai báo field có initializer nghĩa field luôn có giá trị đó trong mọi giai đoạn

Ví dụ:

```java
class Child {
    int score = 10;
}
```

Sau khi constructor chain và field initializer hoàn tất bình thường, `score` là 10. Nhưng **trong lúc superclass constructor đang chạy**, phần initializer của subclass **chưa thực thi**. Nếu một phương thức subclass bị gọi quá sớm từ constructor superclass, nó có thể quan sát `score=0`.

Đây là một cạm bẫy quan trọng sẽ có chương trình minh họa ở mục sau.

## 8. Lớp cha gọi method bị override: lớp con có thể còn state mặc định

Một tình huống cần đánh dấu khi vẽ thứ tự khởi tạo là superclass constructor gọi method có thể override:

```java
class Parent {
    Parent() { show(); }
    void show() { }
}
class Child extends Parent {
    private String text = "ready";
    @Override void show() { System.out.println(text); }
}
```

**Snippet** này cho thấy: trong `new Child()`, `Parent()` chạy trước Child field initializer; `show()` được dispatch tới override của Child nên có thể in `null`. Sau superclass constructor mới đến initializer đặt `text="ready"` và thân constructor Child. Việc gọi method trực tiếp hay qua helper trung gian không tự làm subclass sẵn sàng sớm hơn.

Khi giải thứ tự khởi tạo, đánh dấu đây là **callback chạy giữa constructor chain**, không ghi “mọi field con đã được khởi tạo” ở thời điểm constructor cha bắt đầu. Với phân tích sâu về rủi ro, exceptions, `final`/`private` dispatch và cách sửa bằng lifecycle/factory, xem bài chuyên biệt về gọi phương thức ghi đè khi đối tượng chưa khởi tạo xong. Trong bài này, mục tiêu là nhận ra **vị trí của lời gọi** trong sơ đồ `super(...)` → field initializer → instance block → constructor body.

## 9. Lớp cha và lớp con có field cùng tên: không có “override field”

Instance fields không override như methods. Một subclass có thể khai báo field cùng tên với superclass, nhưng đây là **field hiding**, không phải dynamic dispatch.

Tệp **`FieldHidingInitializationDemo.java`**:

```java
class Parent {
    int count = init("Parent.count", 1);

    Parent() {
        System.out.println("Parent constructor: " + count);
    }

    static int init(String label, int value) {
        System.out.println(label);
        return value;
    }
}

class Child extends Parent {
    int count = init("Child.count", 2);

    Child() {
        System.out.println("Child constructor: " + count);
        System.out.println("Parent field: " + super.count);
    }
}

public class FieldHidingInitializationDemo {
    public static void main(String[] args) {
        Child child = new Child();
        Parent parentRef = child;

        System.out.println("child.count=" + child.count);
        System.out.println("parentRef.count=" + parentRef.count);
    }
}
```

```bash
javac FieldHidingInitializationDemo.java
java FieldHidingInitializationDemo
```

```text
Parent.count
Parent constructor: 1
Child.count
Child constructor: 2
Parent field: 1
child.count=2
parentRef.count=1
```

Hai fields `Parent.count` và `Child.count` đều tồn tại riêng trong Child object. Parent initializer gán field Parent, rồi Child initializer gán field Child. Khi truy cập field thông thường, field được chọn theo **kiểu/biểu thức tại compile time**, khác virtual method dispatch.

Vì vậy ở output cuối:

- `child.count` có static type Child và đọc Child field là 2.
- `parentRef.count` có static type Parent và đọc Parent field là 1.

**Không nhầm field hiding với “Child initializer thay đổi Parent field”**. Hai fields có cùng tên nhưng khác declaration.

## 10. Constructor với `super(args)`: đánh giá đối số trước khi chạy thân constructor cha

Một chi tiết quan trọng: nếu constructor Child có explicit `super(expression)`, Java phải **đánh giá những biểu thức đối số** thích hợp trước khi lời gọi constructor Parent thực hiện thân.

Tệp **`SuperArgumentOrderDemo.java`**:

```java
class Parent {
    Parent(int value) {
        System.out.println("Parent constructor: " + value);
    }
}

class Child extends Parent {
    private int amount = log("Child.field", 20);

    {
        System.out.println("Child.block");
    }

    Child() {
        super(log("super.argument", 7));
        System.out.println("Child.constructor");
    }

    private static int log(String text, int result) {
        System.out.println(text);
        return result;
    }
}

public class SuperArgumentOrderDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac SuperArgumentOrderDemo.java
java SuperArgumentOrderDemo
```

```text
super.argument
Parent constructor: 7
Child.field
Child.block
Child.constructor
```

Đọc thứ tự:

1. Biểu thức `log("super.argument", 7)` được đánh giá để tạo đối số truyền vào `Parent(int)`.
2. Sau đó thân `Parent(int)` chạy.
3. Khi superclass constructor đã hoàn tất bình thường, Child field initializer và Child instance block chạy theo thứ tự source.
4. Cuối cùng Child constructor body chạy.

**Đừng diễn giải cứng nhắc “một lệnh bất kỳ trong Parent luôn chạy trước mọi thao tác xuất hiện trong constructor Child”**. Các biểu thức để cung cấp arguments cho `super(...)` là một phần quan trọng của thứ tự đánh giá.

Trong Java 17, không dùng `this` hoặc instance members của Child ở những vị trí constructor invocation không được phép. Dùng static helper/arguments hợp lệ như `log(...)` ở ví dụ trên.

## 11. Truyền tham số vào superclass constructor không thay thứ tự khởi tạo instance fields

Xét:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
        System.out.println("Person: " + name);
    }
}

class Employee extends Person {
    private int level = initLevel();

    Employee(String name, int level) {
        super(name);
        this.level = level;
        System.out.println("Employee: " + this.level);
    }

    private int initLevel() {
        System.out.println("Employee.field initialized");
        return 1;
    }
}
```

Đây là **khai báo lớp hợp lệ**, không có `main`.

Nếu tạo `new Employee("An", 3)`:

1. Constructor Person gán `name` rồi in.
2. Instance initializer của field `Employee.level` chạy, tạm đặt `level=1`.
3. Constructor body của Employee chạy, gán `level=3` rồi in.

Thứ tự dẫn tới việc một field có initializer **có thể bị constructor gán lại**. Điều này hợp lệ khi field không final; nhưng nên tránh khởi tạo tốn kém ở field initializer nếu constructor luôn thay ngay bằng một giá trị khác.

Đối với `final` field, phải bảo đảm assignment tuân thủ quy tắc definite assignment và không viết lại sau khi đã gán bởi initializer.

## 12. `this(...)`: nhiều constructor cùng lớp, nhưng instance initializers chỉ chạy một lượt

Khi một constructor chuyển tiếp sang constructor khác bằng `this(...)`, **không phải mỗi constructor body đều khiến toàn bộ instance field initializers chạy lại**.

Tệp **`ThisConstructorChainDemo.java`**:

```java
class Parent {
    Parent() {
        System.out.println("Parent()");
    }
}

class Child extends Parent {
    private int value = initializeValue();

    {
        System.out.println("Child.block");
    }

    Child() {
        this(5);
        System.out.println("Child()");
    }

    Child(int number) {
        super();
        this.value = number;
        System.out.println("Child(int): " + number);
    }

    private static int initializeValue() {
        System.out.println("Child.field");
        return 1;
    }
}

public class ThisConstructorChainDemo {
    public static void main(String[] args) {
        Child child = new Child();
    }
}
```

```bash
javac ThisConstructorChainDemo.java
java ThisConstructorChainDemo
```

```text
Parent()
Child.field
Child.block
Child(int): 5
Child()
```

Cơ chế:

1. `new Child()` chọn constructor không tham số.
2. Constructor này bắt đầu bằng `this(5)`, nên chuyển sang `Child(int)`.
3. `Child(int)` gọi `super()`; Parent constructor chạy.
4. Child instance field initializer và instance block chạy **một lượt**.
5. Thân `Child(int)` gán field và in `Child(int): 5`.
6. Quay lại sau `this(5)`, thân còn lại của `Child()` in `Child()`.

Có hai **constructor bodies** của Child trong chuỗi gọi, nhưng chỉ **một Child object** đang được tạo; instance initializers của Child **không bị chạy hai lần**.

### Constructor chaining không thể tạo vòng lặp

Ví dụ cố ý sai:

```java
// class Broken {
//     Broken() { this(1); }
//     Broken(int x) { this(); }
// }
```

Hai constructors gọi nhau vô hạn theo biểu đồ `this(...)`, nên compiler bác bỏ **recursive constructor invocation**. Java không cho tạo vòng constructor delegation kiểu này.

## 13. Constructor overload được chọn theo lời gọi, không theo thứ tự khai báo

Một class có nhiều overloaded constructors:

```java
class Order {
    Order() {
        this("UNKNOWN");
    }

    Order(String code) {
        System.out.println("Order: " + code);
    }
}
```

Đây là đoạn khai báo hợp lệ. Gọi `new Order()` đi qua cả `Order()` và `Order(String)` vì có `this(...)`. Gọi `new Order("A1")` vào thẳng `Order(String)`.

Thứ tự khai báo hai constructors trong source **không làm thay đổi constructor overload resolution**. Loại và số lượng arguments quyết định chữ ký constructor được chọn theo quy tắc Java.

Tương tự, thứ tự field initializers không phụ thuộc **constructor nào được chọn**: chúng chạy cho mỗi instance được khởi tạo bình thường, sau superclass construction và trước phần thân constructor thích hợp, trừ những đường đi thất bại trước đó.

## 14. Nhiều tầng kế thừa: Grandparent → Parent → Child

Với chuỗi `Grandparent → Parent → Child`, quy tắc chạy từng tầng:

- Class initialization (nếu chưa thực hiện): từ superclass cần thiết tới subclass.
- Instance construction: mỗi tầng superclass hoàn tất constructor chain và những instance initializers của nó trước khi bước tới tầng con.
- Constructor body lớp con nằm sau phần initializers của chính lớp con.

Tệp **`ThreeLevelInitializationDemo.java`**:

```java
class Grandparent {
    int a = print("G.field", 1);

    {
        System.out.println("G.block");
    }

    Grandparent() {
        System.out.println("G.constructor");
    }

    static int print(String text, int value) {
        System.out.println(text);
        return value;
    }
}

class Parent extends Grandparent {
    int b = print("P.field", 2);

    {
        System.out.println("P.block");
    }

    Parent() {
        System.out.println("P.constructor");
    }
}

class Child extends Parent {
    int c = print("C.field", 3);

    {
        System.out.println("C.block");
    }

    Child() {
        System.out.println("C.constructor");
    }
}

public class ThreeLevelInitializationDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac ThreeLevelInitializationDemo.java
java ThreeLevelInitializationDemo
```

```text
G.field
G.block
G.constructor
P.field
P.block
P.constructor
C.field
C.block
C.constructor
```

Các static blocks không được khai báo trong ví dụ, để tập trung vào **instance sequence**. Nếu thêm static blocks ở các lớp chưa initialized, chúng sẽ được xử lý theo quy tắc **class initialization trước instance initialization**.

**Sơ đồ tổng quát:**

```text
new Child()
   ├── Grandparent instance fields / blocks
   ├── Grandparent constructor body
   ├── Parent instance fields / blocks
   ├── Parent constructor body
   ├── Child instance fields / blocks
   └── Child constructor body
```

Từ “Grandparent” ở đây là một lớp do ví dụ đặt tên, không phải keyword Java. Java luôn có class gốc cuối cùng là `Object` nếu superclass chain phù hợp; `Object` cũng tham gia constructor chain nhưng không có output trong ví dụ.

## 15. Thứ tự khi tạo hai object liên tiếp

Static initialization của class thường chỉ diễn ra một lần thành công cho runtime class đó, nhưng instance construction được thực hiện **mỗi lần tạo object**.

Tệp **`TwoObjectsOrderDemo.java`**:

```java
class Device {
    static {
        System.out.println("Device.static");
    }

    private int serial = initialize();

    {
        System.out.println("Device.block");
    }

    Device() {
        System.out.println("Device.constructor");
    }

    private static int initialize() {
        System.out.println("Device.field");
        return 1;
    }
}

public class TwoObjectsOrderDemo {
    public static void main(String[] args) {
        System.out.println("first");
        new Device();

        System.out.println("second");
        new Device();
    }
}
```

```bash
javac TwoObjectsOrderDemo.java
java TwoObjectsOrderDemo
```

```text
first
Device.static
Device.field
Device.block
Device.constructor
second
Device.field
Device.block
Device.constructor
```

**Vì sao output là vậy?**

- `Device.static` in chỉ ở lần initialize đầu.
- `Device.field`, `Device.block` và `Device.constructor` in cho mỗi object Device.
- Tên `serial` là instance field; hai Device objects có fields riêng, dù cùng dùng initializer `initialize()`.

Không nên lấy hai lượt gọi `new` và nghĩ hai lượt static block sẽ chạy; chúng thuộc hai cấp độ khởi tạo khác nhau.

## 16. Static field initializers và static blocks: theo thứ tự source riêng

Trong một class, static field initializers và static blocks chạy theo thứ tự xuất hiện trong source **khi class initialize**. Chúng không đợi instance construction.

Tệp **`StaticAndInstanceSeparationDemo.java`**:

```java
class Sample {
    static int config = log("S.staticField", 10);

    static {
        System.out.println("S.staticBlock");
    }

    int value = log("S.instanceField", 20);

    {
        System.out.println("S.instanceBlock");
    }

    Sample() {
        System.out.println("S.constructor");
    }

    static int log(String label, int number) {
        System.out.println(label);
        return number;
    }
}

public class StaticAndInstanceSeparationDemo {
    public static void main(String[] args) {
        System.out.println("before class use");
        System.out.println("config=" + Sample.config);
        System.out.println("before object");
        new Sample();
    }
}
```

```bash
javac StaticAndInstanceSeparationDemo.java
java StaticAndInstanceSeparationDemo
```

```text
before class use
S.staticField
S.staticBlock
config=10
before object
S.instanceField
S.instanceBlock
S.constructor
```

Đọc `Sample.config` là một active use của non-constant static field, kích hoạt Sample class initialization. Khi `new Sample()` xuất hiện sau đó, Sample đã initialize thành công, nên chương trình chỉ cần đi vào các bước **tạo instance**.

**Không nhầm** `static int config = ...` với `int value = ...`; chúng nằm ở hai quy trình khác nhau dù đều là field initializers.

## 17. Một field không có initializer vẫn có default value

Nếu khai báo:

```java
class Product {
    private int count;
    private boolean ready;
    private String note;
}
```

Khi tạo `new Product()`, các fields `count`, `ready`, `note` nhận default values `0`, `false`, `null`. Không có requirement phải viết một initializer cho mọi field.

Constructor hoặc method có thể thay chúng về sau. Nhưng đừng nhầm việc có default value với trạng thái **hợp lệ của miền nghiệp vụ**. Nếu `note` không được phép null, constructor nên validate/assign trước khi object được công bố.

## 18. Lời gọi constructor có thể thất bại trước khi instance initializer của lớp con chạy

Nếu superclass constructor ném exception, quá trình tạo object subclass không hoàn tất bình thường. Các instance initializers của subclass **chưa đến lượt chạy**, trừ side effects đã xảy ra ở việc đánh giá arguments hoặc một đường thực thi khác được phép trước đó.

Tệp **`SuperclassFailureDemo.java`**:

```java
class Parent {
    Parent() {
        System.out.println("Parent.constructor");
        throw new IllegalStateException("parent failed");
    }
}

class Child extends Parent {
    private int value = printValue();

    {
        System.out.println("Child.block");
    }

    Child() {
        System.out.println("Child.constructor");
    }

    static int printValue() {
        System.out.println("Child.field");
        return 1;
    }
}

public class SuperclassFailureDemo {
    public static void main(String[] args) {
        try {
            new Child();
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }
}
```

```bash
javac SuperclassFailureDemo.java
java SuperclassFailureDemo
```

```text
Parent.constructor
caught: parent failed
```

Không có `Child.field`, `Child.block`, `Child.constructor` trong output: Parent constructor ném lỗi trước khi các bước ấy chạy.

**Phân biệt:** class initialization của Child (nếu có static blocks) vẫn có thể đã diễn ra trước instance construction. Ví dụ này không có static blocks nên output chỉ nói về **instance constructor chain**.

## 19. Exception trong instance field initializer hoặc instance block

Nếu một instance initializer ném exception, những initializers **sau nó** và constructor body của class ấy **không chạy**, trừ khi exception được xử lý bên trong initializer và không thoát ra.

Tệp **`InstanceInitializerFailureDemo.java`**:

```java
class Parent {
    Parent() {
        System.out.println("Parent.constructor");
    }
}

class Child extends Parent {
    private int first = log("Child.first", 1);

    {
        System.out.println("Child.block");
        if (shouldFail()) {
            throw new IllegalStateException("block failed");
        }
    }

    private int second = log("Child.second", 2);

    Child() {
        System.out.println("Child.constructor");
    }

    static boolean shouldFail() {
        return true;
    }

    static int log(String text, int value) {
        System.out.println(text);
        return value;
    }
}

public class InstanceInitializerFailureDemo {
    public static void main(String[] args) {
        try {
            new Child();
        } catch (IllegalStateException ex) {
            System.out.println("caught: " + ex.getMessage());
        }
    }
}
```

```bash
javac InstanceInitializerFailureDemo.java
java InstanceInitializerFailureDemo
```

```text
Parent.constructor
Child.first
Child.block
caught: block failed
```

**Giải thích:** Khối khởi tạo dùng `shouldFail()` để quyết định tại thời điểm chạy. Trình biên dịch không chứng minh được rằng nhánh ném exception luôn được thực thi, nên instance initializer có khả năng hoàn tất bình thường theo quy tắc Java. Với `shouldFail()` trả `true` ở chương trình này, khi chạy, khối in `Child.block` rồi ném `IllegalStateException`; chương trình bắt exception trong `main` và in đúng stdout ở trên. Phần khởi tạo `Child.second` và thân constructor `Child()` không chạy.

## 20. Instance initialization blocks phù hợp lúc nào?

Instance block là những khối đứng trực tiếp trong thân class, không có tên và không có `static`:

```java
class Example {
    {
        System.out.println("instance block");
    }
}
```

Chúng hữu ích khi có logic khởi tạo chung phải chạy trước phần thân các constructors, bất kể constructor overload nào được chọn, hoặc khi local/anonymous class có giới hạn thiết kế nhất định.

Tuy nhiên với code ứng dụng thông thường, các lựa chọn rõ hơn thường là:

- **Field initializer** cho giá trị đơn giản: `private final List<String> items = new ArrayList<>();`.
- **Constructor** cho việc validate và khởi tạo phụ thuộc arguments.
- **Private helper method** được constructor gọi khi logic dài và có ý nghĩa riêng.
- **Static factory** khi cần kiểm soát construction, subtype hoặc validation phức tạp.

Instance block không phải “bắt buộc phải có” trong class. Đừng cố chuyển mọi initialization logic sang block chỉ để tránh viết constructor.

### Ví dụ block có thể dùng chung qua nhiều overloads

```java
class Session {
    private final java.util.List<String> events =
            new java.util.ArrayList<>();

    {
        events.add("created");
    }

    Session() {
    }

    Session(String name) {
        events.add("name=" + name);
    }
}
```

Đây là khai báo hợp lệ. Mỗi Session object được khởi tạo với list mới, rồi block thêm `created`. Constructor nhận `name` thêm dữ liệu sau block. Với case này cũng có thể đưa thêm `created` ngay vào một helper/constructor, nên lựa chọn dựa trên khả năng đọc.

## 21. Thứ tự giữa initializer và thân constructor có thể ảnh hưởng invariant

Giả sử:

```java
class User {
    private String name = "anonymous";

    User(String name) {
        this.name = name;
    }
}
```

Khi tạo `new User("An")`, field initializer gán `"anonymous"`, rồi constructor body gán `"An"`. Nếu constructor không validate `name`, caller có thể truyền null và làm field mất tính hợp lệ mong muốn.

Cách thiết kế rõ hơn:

```java
class User {
    private final String name;

    User(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        this.name = name;
    }
}
```

Ở đây field `name` là blank final instance field, được constructor gán đúng một lần sau validation. Bạn không cần gán giá trị mặc định chỉ để “lớp có field initializer”.

**Bài học:** xác định **nguồn dữ liệu cuối cùng** của mỗi field (field declaration hay constructor arguments) giúp tránh gán hai lần không cần thiết và giảm nguy cơ side effects.

## 22. `final` instance field: phải hoàn tất khởi tạo hợp lệ trước khi constructor trả về

Với blank final field:

```java
class Ticket {
    private final String code;

    Ticket(String code) {
        this.code = code;
    }
}
```

Java yêu cầu final instance field được definitely assigned theo quy tắc trước khi constructor hoàn tất bình thường. Không được viết lại `code` từ instance method như một field bình thường.

Sai:

```java
// class Ticket {
//     private final String code = "A";
//     Ticket() {
//         code = "B"; // Lỗi: final field đã được gán.
//     }
// }
```

**Liên hệ thứ tự:** nếu final field đã có initializer tại khai báo, nó được gán trong bước field initialization trước thân constructor; không thể gán lại tại thân constructor.

### Không phải “field là final nên nó có giá trị cuối từ lúc superclass constructor chạy”

Ngay cả khi Child khai báo `private final int count = 42;`, khi superclass constructor gọi overridable method của Child, initializer đó chưa chạy. Trong lời gọi quá sớm, override có thể quan sát giá trị mặc định `0` theo quy tắc liên quan. Final không cho phép bỏ qua thứ tự construction.

**Đừng dùng superclass constructor để phụ thuộc vào fields của subclass**, kể cả fields final.

## 23. Anonymous class và instance initialization block

Một anonymous class không có constructor declaration mang tên lớp để bạn tự viết, nhưng có thể chứa instance initializer block.

Ví dụ:

Tệp **`AnonymousInitializationDemo.java`**:

```java
interface Action {
    void run();
}

public class AnonymousInitializationDemo {
    public static void main(String[] args) {
        Action action = new Action() {
            private final String label = initialize();

            {
                System.out.println("anonymous.block");
            }

            private String initialize() {
                System.out.println("anonymous.field");
                return "ready";
            }

            @Override
            public void run() {
                System.out.println("run=" + label);
            }
        };

        action.run();
    }
}
```

```bash
javac AnonymousInitializationDemo.java
java AnonymousInitializationDemo
```

```text
anonymous.field
anonymous.block
run=ready
```

Trong một anonymous class:

- Nó là một class riêng được tạo ra từ expression.
- Field initializer và instance block chạy khi anonymous object được tạo.
- Không có constructor source declaration có tên lớp, nên initialization block là một cách viết setup logic cho anonymous class.
- Method `run()` chỉ chạy khi được gọi qua `action.run()`, không phải khi tạo object, trừ khi constructor/initializer tự gọi nó.

**Lưu ý:** nên ưu tiên lambda thay anonymous class cho các functional interfaces khi không cần object state/initializer đặc thù. Hai cú pháp có ngữ nghĩa class/`this` khác nhau, không nên xem lambda là “anonymous class được viết ngắn”.

## 24. Mặc định khi class không khai báo constructor

Nếu class không có constructor declaration nào, compiler có thể tạo **default constructor** phù hợp, với lời gọi superclass no-arg constructor theo quy tắc.

Tệp **`DefaultConstructorOrderDemo.java`**:

```java
class Parent {
    Parent() {
        System.out.println("Parent()");
    }
}

class Child extends Parent {
    private int number = print();

    {
        System.out.println("Child.block");
    }

    static int print() {
        System.out.println("Child.field");
        return 5;
    }
}

public class DefaultConstructorOrderDemo {
    public static void main(String[] args) {
        new Child();
    }
}
```

```bash
javac DefaultConstructorOrderDemo.java
java DefaultConstructorOrderDemo
```

```text
Parent()
Child.field
Child.block
```

`Child` không viết constructor tường minh. Compiler cung cấp default constructor; Parent no-arg constructor chạy, sau đó Child field initializer và block chạy. Không có thân constructor tự viết nên không có dòng in từ Child constructor body.

Nếu Parent chỉ có `Parent(int)` mà không có no-arg constructor accessible, default constructor của Child không thể tự gọi `super()` hợp lệ; compiler sẽ báo lỗi, bạn cần khai báo constructor Child có `super(argument)`.

## 25. Khi nào static initialization của Parent/Child đã hoàn tất từ trước?

Không phải mọi lần `new Child()` đều tạo output gồm static blocks. Xét:

Tệp **`AlreadyInitializedDemo.java`**:

```java
class Parent {
    static {
        System.out.println("Parent.static");
    }

    Parent() {
        System.out.println("Parent.constructor");
    }

    static void touch() {
        System.out.println("Parent.touch");
    }
}

class Child extends Parent {
    static {
        System.out.println("Child.static");
    }

    Child() {
        System.out.println("Child.constructor");
    }
}

public class AlreadyInitializedDemo {
    public static void main(String[] args) {
        Parent.touch();
        System.out.println("before child");
        new Child();
        System.out.println("again");
        new Child();
    }
}
```

```bash
javac AlreadyInitializedDemo.java
java AlreadyInitializedDemo
```

```text
Parent.static
Parent.touch
before child
Child.static
Parent.constructor
Child.constructor
again
Parent.constructor
Child.constructor
```

Phân tích:

- `Parent.touch()` kích hoạt Parent initialization rồi chạy method.
- Lần đầu `new Child()` khởi tạo Child; Parent đã initialize nên `Parent.static` không lặp. Sau đó Parent/Child constructors chạy.
- Lần hai `new Child()` chỉ chạy constructors; hai classes đều initialized.

**Ghi nhớ:** muốn đoán một static block có chạy không, phải biết **class đã được initialize trước thao tác hiện tại chưa**. Không thể chỉ nhìn vào `new` cuối method và đoán static blocks chắc chắn xuất hiện ngay đó.

## 26. Field initializer chứa method call có thể gây tác dụng phụ

Một field initializer không bắt buộc chỉ là literal:

```java
class ConnectionSettings {
    private final String host = readHost();

    private static String readHost() {
        System.out.println("read settings");
        return "localhost";
    }
}
```

Mỗi lần tạo `ConnectionSettings` instance, initializer `readHost()` chạy (trừ nếu constructor chain ném lỗi sớm) và có thể có side effects. Điều này là hệ quả của **field initializer chạy trên mỗi instance**, không phải phép tối ưu được cache tự động.

Nếu initializer mở file, gọi network hoặc đăng ký callback, nó có thể thất bại **trước thân constructor** và làm logic khó kiểm soát. Nên chọn vị trí initialization dựa trên:

- Ai cần biết error?
- Có dependency nào cần truyền qua constructor arguments?
- Có cần điều kiện validate trước khi thực hiện side effect?
- Có cần đóng/rollback tài nguyên khi bước sau thất bại?
- Có cần thay implementation trong tests không?

Với operations có thể thất bại, factory hoặc service có contract lỗi rõ có thể dễ bảo trì hơn một initializer phức tạp ẩn trong field declaration.

## 27. Mỗi instance có những object riêng từ field initializer, trừ khi cố ý dùng static

Nếu field initializer chứa `new ArrayList<>()`:

```java
class Bucket {
    final java.util.List<String> items =
            new java.util.ArrayList<>();
}
```

Mỗi `new Bucket()` thường tạo một list object mới cho instance ấy. Hai Bucket objects không tự dùng chung `items` chỉ vì khai báo field nằm cùng một chỗ trong source.

Ngược lại:

```java
class Bucket {
    static final java.util.List<String> ITEMS =
            new java.util.ArrayList<>();
}
```

Đây là static field tham chiếu một list dùng chung trên cấp runtime class, không tự được tạo lại khi `new Bucket()` thêm lần nữa.

**Lưu ý:** `final` trên field tham chiếu không tự làm list immutable, dù field là instance final hay static final.

## 28. Thời điểm đánh giá `new Child(argumentExpression)`

Để dự đoán output trong Java, phải xét **đánh giá biểu thức caller** trước khi constructor chạy.

Ví dụ:

```java
Child child = new Child(makeValue());
```

Nếu `makeValue()` có side effect, nó có thể in thông báo **trước những phần constructor bodies**. Tuy nhiên, quy tắc class initialization, thứ tự đánh giá receiver/arguments và những side effects xảy ra ở class dependencies cũng ảnh hưởng output thực tế.

Không nên khẳng định quy tắc tuyệt đối “dòng đầu của static block Parent luôn là dòng output đầu tiên bất cứ khi nào source chứa `new Child(...)`”, bởi caller có thể in hoặc thực thi các biểu thức khác trước.

Trong các ví dụ chủ đề này, hãy đánh dấu rõ output do:

1. Lệnh trong `main`.
2. Class initializers.
3. Biểu thức đối số `new`/`super`/`this`.
4. Constructor chain của superclass.
5. Field initializers/instance blocks.
6. Constructor body của subclass.
7. Lệnh sau khi `new` hoàn tất.

Thứ tự source Java được xác định bởi các quy tắc cụ thể, không chỉ bởi việc một đoạn nằm ở class cha hay con.

## 29. Giao diện (*interface*) không có instance constructor

Một class có thể `implements Interface`, nhưng **interface không có constructor chạy trong chuỗi instance construction**.

Ví dụ:

```java
interface Named {
    String name();
}

class Person implements Named {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}
```

Khi tạo Person, constructor chain dựa trên **class superclass hierarchy** (cuối cùng tới `Object`), không chạy “constructor của Named” vì interface không có constructor instance.

Các **static fields của interface** và một số quy tắc initialization liên quan superinterfaces/default methods có thể ảnh hưởng **class initialization**, nhưng đó là một chủ đề tách biệt với **instance constructor chain**.

**Không xem `implements` là một cạnh `extends` mang constructor.**

## 30. Không tạo object khi chỉ tạo mảng tham chiếu

Tạo mảng:

```java
Child[] children = new Child[3];
```

chỉ tạo **array object** chứa ba slots tham chiếu mặc định `null`, **không gọi ba constructors Child** và không chạy instance field initializers của Child cho từng slot.

Tệp **`ArrayVsObjectDemo.java`**:

```java
class Child {
    int value = log();

    Child() {
        System.out.println("Child.constructor");
    }

    static int log() {
        System.out.println("Child.field");
        return 1;
    }
}

public class ArrayVsObjectDemo {
    public static void main(String[] args) {
        System.out.println("make array");
        Child[] items = new Child[2];

        System.out.println(items[0] == null);
        items[0] = new Child();
        System.out.println(items[1] == null);
    }
}
```

```bash
javac ArrayVsObjectDemo.java
java ArrayVsObjectDemo
```

```text
make array
true
Child.field
Child.constructor
true
```

Chỉ `new Child()` cho slot 0 mới bắt đầu construction của một Child instance. `items[1]` vẫn null và chưa có bất kỳ object thứ hai được tạo.

## 31. Phân biệt constructor, method cùng tên và initialization block

Constructor declaration có **tên trùng tên class** và **không có return type**:

```java
class Sample {
    Sample() {
        System.out.println("constructor");
    }
}
```

Nếu viết:

```java
class Sample {
    void Sample() {
        System.out.println("ordinary method");
    }
}
```

thì `void Sample()` là **method bình thường**, không phải constructor. Compiler có thể cung cấp default constructor vì class chưa có constructor declaration.

Instance initialization block là:

```java
class Sample {
    {
        System.out.println("instance block");
    }
}
```

Static block là:

```java
class Sample {
    static {
        System.out.println("static block");
    }
}
```

Bốn khai báo `Sample` ở mục này là **những minh họa độc lập**, không đặt đồng thời cùng tên trong một source set. Chúng chạy ở những thời điểm rất khác nhau. Phân loại cú pháp đúng là bước đầu trước khi dự đoán thứ tự.

## 32. Mẫu ứng dụng: khởi tạo immutable object theo tham số constructor

Một trường hợp thực tế: class có superclass kiểm tra ID chung, subclass thêm thông số riêng.

Tệp **`ValidatedObjectDemo.java`**:

```java
class Entity {
    private final String id;

    Entity(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id required");
        }
        this.id = id;
    }

    String id() {
        return id;
    }
}

final class Product extends Entity {
    private final int price;

    Product(String id, int price) {
        super(id);
        if (price < 0) {
            throw new IllegalArgumentException("negative price");
        }
        this.price = price;
    }

    int price() {
        return price;
    }
}

public class ValidatedObjectDemo {
    public static void main(String[] args) {
        Product product = new Product("P-1", 250);

        System.out.println(product.id());
        System.out.println(product.price());

        try {
            new Product("", 50);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid id");
        }
    }
}
```

```bash
javac ValidatedObjectDemo.java
java ValidatedObjectDemo
```

```text
P-1
250
invalid id
```

Thiết kế này:

- `Entity` constructor bảo vệ invariant ID trước khi phần khởi tạo Product hoàn tất.
- `Product` constructor kiểm tra giá sau khi superclass constructor trả về bình thường.
- `Product.price` là blank final field, được gán một lần trong constructor phù hợp.
- Class Product `final` nhằm thể hiện value/entity concrete type không hỗ trợ subclass trong ví dụ.
- Nếu `id` rỗng, superclass constructor ném exception, việc tạo Product không trả về instance thành công.

**Một giới hạn quan trọng:** Nếu validation của Product.price phải thực hiện **trước bất cứ side effects nào của Entity constructor**, hãy thiết kế factory/pre-validation hoặc cách phân chia trách nhiệm phù hợp. Trong Java 17, không thể đặt statement tùy ý trước `super(id)` trong cùng constructor body.

## 33. Một thiết kế cần tránh: để `this` thoát ra ngoài trong constructor

Ngay cả trước khi constructor lớp con hoàn tất, code có thể vô tình **công bố tham chiếu `this`** cho nơi khác.

Ví dụ nguy hiểm:

```java
class Base {
    static java.util.List<Base> registry =
            new java.util.ArrayList<>();

    Base() {
        registry.add(this);
    }
}

class Child extends Base {
    private String ready = "yes";
}
```

Nếu `Base()` lưu `this` vào registry, object được đăng ký **trước** khi initializer `Child.ready="yes"` chạy. Code khác truy cập registry ngay lúc ấy có thể quan sát object chưa hoàn thành, hoặc nguy hiểm hơn trong môi trường đa luồng.

Hướng thiết kế an toàn hơn:

- Tránh callback/registration/thread start trong constructor khi có nguy cơ dùng object chưa hoàn chỉnh.
- Hoàn tất construction và validation trước, rồi service/factory bên ngoài mới đăng ký object.
- Đừng gọi overridable methods từ superclass constructor.
- Nếu cần công bố object giữa nhiều threads, còn cần **safe publication** phù hợp Java Memory Model.

**Đóng gói không thể chỉ dựa vào `private` fields** nếu chính constructor cho external code thấy `this` trước khi invariant được thiết lập.

## 34. Ngộ nhận phổ biến về thứ tự khởi tạo

| Ngộ nhận | Điều đúng |
| --- | --- |
| “Constructor lớp con chạy trước vì gọi `new Child`” | Superclass constructor chain được thực hiện trước phần thân constructor Child |
| “Toàn bộ code trong class Parent chạy trước toàn bộ code Child” | Phải tách static vs instance, đánh giá arguments, và active uses |
| “Static initializer chạy mỗi lần `new`” | Class initialization thành công không lặp ở mỗi instance |
| “Field initializer của Child chạy trước Parent constructor” | Không; phần khởi tạo Parent precedes Child instance initializers |
| “Mọi field initializers luôn chạy hết rồi mới tới blocks” | Field initializers và instance blocks đan xen theo source order |
| “Instance block chỉ chạy nếu không có constructor” | Nó chạy trong instance construction phù hợp, bất kể có overload constructors |
| “`this(...)` làm field initializers chạy lần nữa” | Delegation không lặp instance initializers cho cùng object |
| “`super(...)` có thể đặt ở cuối constructor trong Java 17” | Explicit constructor invocation phải ở đầu theo Java 17 |
| “Không ghi `super()` thì bỏ qua Parent constructor” | Compiler chèn implicit superclass constructor invocation nếu hợp lệ |
| “Subclass luôn có thể gọi no-arg constructor cha” | Có thể thiếu/inaccessible no-arg constructor; phải chọn constructor hợp lệ |
| “Lớp cha gọi override thì fields Child đã gán” | Override có thể thấy default values khi Child chưa initialized |
| “`final` field Child chắc chắn có giá trị cuối trong Parent constructor” | Không, thứ tự instance initialization vẫn áp dụng |
| “Hai fields cùng tên Parent/Child là một field” | Field hiding tạo distinct declarations |
| “Exception Parent constructor vẫn cho Child block chạy” | Nếu constructor cha không hoàn tất, Child initializers chưa tới lượt |
| “Array `new Child[3]` tạo ba Child objects” | Chỉ tạo array; slots mặc định null |
| “`static` và instance blocks giống nhau” | Khác thời điểm và số lượt thực thi |
| “Lời gọi method có tên class và return type void là constructor” | Đó là method, không phải constructor |
| “Một class dùng `implements` sẽ gọi constructor của interface” | Interface không có instance constructor |
| “Mọi phương thức gọi trong constructor đều an toàn” | Overridable method call có thể thấy subclass state chưa sẵn sàng |
| “Đổi thứ tự declaration constructors làm đổi thứ tự khởi tạo fields” | Không; source order của fields/blocks mới quyết định |
| “Không dùng field có initializer tức JVM không gán giá trị nào” | Fields bắt đầu ở default values |
| “Field `static final` và field instance `final` cùng vòng đời” | Static field gắn class initialization, instance field gắn mỗi object |

## 35. Bài thực hành tổng hợp: dự đoán output trước khi chạy

Tạo **`FullInitializationTraceDemo.java`**:

```java
class A {
    static {
        System.out.println("A.S");
    }

    int x = emit("A.F", 1);

    {
        System.out.println("A.B");
    }

    A(int n) {
        System.out.println("A.C=" + n);
    }

    static int emit(String label, int result) {
        System.out.println(label);
        return result;
    }
}

class B extends A {
    static {
        System.out.println("B.S");
    }

    int y = emit("B.F", 2);

    {
        System.out.println("B.B");
    }

    B() {
        this(5);
        System.out.println("B.C0");
    }

    B(int n) {
        super(emit("ARG", n));
        System.out.println("B.C1=" + n);
    }
}

public class FullInitializationTraceDemo {
    public static void main(String[] args) {
        System.out.println("START");
        new B();
        System.out.println("AGAIN");
        new B(9);
    }
}
```

```bash
javac FullInitializationTraceDemo.java
java FullInitializationTraceDemo
```

**Output chính xác:**

```text
START
A.S
B.S
ARG
A.F
A.B
A.C=5
B.F
B.B
B.C1=5
B.C0
AGAIN
ARG
A.F
A.B
A.C=9
B.F
B.B
B.C1=9
```

### Phân tích lượt thứ nhất

1. Main in `START`.
2. `new B()` làm initialize A rồi B: `A.S`, `B.S`.
3. `B()` gọi `this(5)`.
4. `B(int)` chuẩn bị lời gọi `super(emit("ARG", n))`: `ARG` in ra, kết quả 5 truyền cho A.
5. A field initializer `x` in `A.F`, A instance block in `A.B`, A constructor body in `A.C=5`.
6. B field initializer `y` in `B.F`, B instance block in `B.B`.
7. B(int) constructor body in `B.C1=5`.
8. Quay lại B() constructor body in `B.C0`.

### Phân tích lượt thứ hai

1. Main in `AGAIN`.
2. A và B **đã initialized**, static blocks không in lại.
3. `new B(9)` gọi trực tiếp B(int), đánh giá `super(...)` argument → `ARG`.
4. A fields/block/constructor in `A.F`, `A.B`, `A.C=9`.
5. B fields/block/constructor in `B.F`, `B.B`, `B.C1=9`.
6. Không có `B.C0` vì không đi qua overload `B()`.

**Kỹ năng cốt lõi:** tách rõ **class initialization (một lần)**, **constructor delegation**, **super arguments**, **parent instance sequence**, **child instance sequence** và **constructor bodies**.

## 36. Bài tập nhanh kèm đáp án

**Câu 1.** Với `class Child extends Parent` và `new Child()`, thân constructor nào chạy trước?

**Đáp án:** Thân superclass constructor chain của Parent trước thân Child constructor, nhưng có thể có biểu thức đối số `super(...)` được đánh giá trước khi thân Parent constructor bắt đầu.

**Câu 2.** Trong Child, `int a = f();` đứng trước `{ g(); }`. Gọi gì trước?

**Đáp án:** `f()` từ field initializer trước `g()` từ instance block, sau khi superclass construction cho Child đã hoàn tất.

**Câu 3.** Nếu đặt instance block trước field initializer trong source thì sao?

**Đáp án:** Instance block chạy trước field initializer đó, tuân theo textual order.

**Câu 4.** `new Child()` lần thứ hai có chạy lại Child static block không?

**Đáp án:** Không nếu cùng runtime class đã initialize thành công; instance initializers và constructors vẫn chạy để tạo instance mới.

**Câu 5.** Có phải mọi Child instance field đều có giá trị khai báo khi Parent constructor gọi overridable method Child?

**Đáp án:** Không. Child initializers chưa chạy nên override có thể thấy default values.

**Câu 6.** `Child() { this(1); ... }` làm Child field initializer chạy mấy lần cho một object?

**Đáp án:** Một lần, trong constructor chain thích hợp, không chạy lại cho mỗi overload body.

**Câu 7.** Nếu superclass chỉ có `Parent(int)`, subclass không khai báo constructor nào có compile được không?

**Đáp án:** Không nếu implicit `super()` không hợp lệ vì không có no-arg Parent constructor accessible.

**Câu 8.** Java 17 có cho `System.out.println("x"); super();` trong constructor không?

**Đáp án:** Không, explicit constructor invocation phải là first statement.

**Câu 9.** Hai fields cùng tên ở Parent và Child có phải method override không?

**Đáp án:** Không. Fields bị hide, mỗi declaration riêng; field access dựa trên kiểu/nguồn declaration, không virtual dispatch.

**Câu 10.** `new Child[2]` chạy Child constructor mấy lần?

**Đáp án:** Không lần nào; chỉ tạo array object chứa hai slots null.

**Câu 11.** Nếu Parent constructor throw trước khi return, Child instance block có chạy không?

**Đáp án:** Không trong constructor chain ấy; tạo Child thất bại trước khi đến Child initializers.

**Câu 12.** Instance field `int n;` không có initializer nhận giá trị gì khi object mới cấp phát?

**Đáp án:** Default `0`, sau đó có thể bị initializer/constructor sửa.

**Câu 13.** Mọi instance field initializers có chạy đúng một lần trong mỗi constructor body của `this(...)` chain không?

**Đáp án:** Không. Chúng chạy một lần cho object, trước thân constructor đích thích hợp sau superclass phase, không lặp ở từng body.

**Câu 14.** Static class initializer có được gọi từ constructor body bằng tên method tự chọn không?

**Đáp án:** Static initialization do JVM quản lý theo active-use rules; không có source method `<clinit>` do người viết gọi như ordinary method.

**Câu 15.** Một instance initialization block có dùng `this` để truy cập object đang tạo không?

**Đáp án:** Có trong instance context thích hợp, nhưng object có thể chưa hoàn tất constructor body và chưa được công bố an toàn. Tránh gọi code có thể để `this` escape hoặc phụ thuộc vào fields chưa sẵn sàng.

**Câu 16.** Thứ tự giữa superclass static block và subclass static block khi lần đầu initialize subclass thông thường là gì?

**Đáp án:** Superclass được initialize theo dependency trước subclass; các static initializers trong từng class chạy theo thứ tự source của class đó.

**Câu 17.** Class implement interface có phải chạy “interface constructor” khi tạo object không?

**Đáp án:** Không. Interface không có instance constructor.

**Câu 18.** Constructor delegation có thể gọi `this(...)` và `super(...)` đồng thời trong cùng constructor không?

**Đáp án:** Không. Mỗi constructor có một explicit constructor invocation phù hợp ở đầu (hoặc implicit `super()`); chuỗi delegation đi tới superclass qua constructor đích.

## 37. Checklist kiểm tra thứ tự khởi tạo trong code thật

- [ ] Đã xác định class đang được tạo và **toàn bộ superclass chain**?
- [ ] Phân biệt static initializers với instance initializers?
- [ ] Xác định class nào **đã initialize trước đó** trong tiến trình?
- [ ] Nếu có static blocks, đã xét thứ tự source trong từng class?
- [ ] Các constructor dùng implicit `super()`, explicit `super(args)` hay `this(args)`?
- [ ] Các biểu thức đối số `super(...)`/`this(...)` có side effects không?
- [ ] Constructor superclass được gọi có đúng chữ ký và accessible không?
- [ ] Đã liệt kê instance field initializers và blocks **theo thứ tự source** trong mỗi class?
- [ ] Có field initializer nào đọc field chưa được gán giá trị tùy chỉnh không?
- [ ] Có field trùng tên ở superclass/subclass, dễ nhầm với override?
- [ ] Superclass constructor có gọi overridable methods không?
- [ ] Có constructor hoặc initializer nào làm `this` escape sớm không?
- [ ] Với `this(...)` chain, đã tránh đếm instance initializers nhiều lần?
- [ ] Nếu có exception, đã xác định bước nào chạy và bước nào không?
- [ ] Với `final` fields, đã kiểm definite assignment, không gán lặp?
- [ ] Đã tách giá trị mặc định của instance fields khỏi giá trị do initializer gán?
- [ ] Nếu chỉ tạo mảng hoặc lấy class literal, có đang nhầm với tạo instance?
- [ ] Đã thử chạy ví dụ tối thiểu bằng `javac`/`java` và đối chiếu output từng dòng?

---

**Ghi nhớ cuối bài:** Khi tạo object của subclass, Java tách **khởi tạo class** khỏi **khởi tạo instance**. Class initializers của superclass/subclass chạy khi cần theo quy tắc active use, không lặp mỗi object. Trong quá trình tạo một instance, **constructor chain của lớp cha được thực hiện trước**, sau đó **instance field initializers và instance blocks của lớp con chạy đan xen theo thứ tự source**, cuối cùng mới tới **thân constructor lớp con**. Với `this(...)`, các constructor bodies có thể nối nhau nhưng instance initializers không chạy lặp cho cùng một object. Luôn tính đến **đánh giá arguments của `super(...)`**, **field defaults**, **exception**, và nguy cơ **gọi overridden method từ superclass constructor khi subclass state chưa sẵn sàng**. Nắm rõ các bước này giúp dự đoán stdout, xử lý lỗi constructor và thiết kế lớp kế thừa an toàn trong Java.