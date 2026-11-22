# Chuỗi `this()` và `super()`: vị trí lời gọi trong Java 21

## 1. Mục tiêu: hiểu cách các constructor nối tiếp nhau

Trong Java, constructor được dùng để hoàn tất quá trình khởi tạo một instance. Nếu một lớp có nhiều constructor, một constructor có thể **ủy quyền** cho constructor khác trong chính lớp đó bằng `this(...)`. Nếu lớp kế thừa từ lớp khác, constructor có thể gọi constructor của lớp cha bằng `super(...)`.

Hai dạng này thường được gọi chung là **explicit constructor invocation** (*lời gọi constructor tường minh*):

- **`this(...)`**: gọi **một constructor khác trong cùng lớp**, trên **cùng đối tượng đang được tạo**.
- **`super(...)`**: gọi **một constructor thích hợp của superclass trực tiếp**, để khởi tạo phần superclass của **cùng đối tượng**.

Chúng **không phải** instance method và cũng không có nghĩa “tạo một object khác”. Constructor không có kiểu trả về và không được gọi lại tùy ý trên object đã xây dựng xong.

**Quy tắc trọng tâm của Java 21:** nếu viết `this(...)` hoặc `super(...)` một cách tường minh trong thân constructor, **lời gọi đó phải là statement đầu tiên** của constructor. Trước nó không được đặt khai báo biến cục bộ, lệnh gán, `System.out.println(...)`, khối `if`, lời gọi method hay bất kỳ statement nào khác.

Ví dụ hợp lệ:

```java
class Base {
    Base(int code) {
        System.out.println("Base: " + code);
    }
}

class Child extends Base {
    Child() {
        this(5);  // Đầu constructor Child().
    }

    Child(int code) {
        super(code); // Đầu constructor Child(int).
        System.out.println("Child: " + code);
    }
}
```

Đây là **khai báo lớp biên dịch được**, chưa có `main` để chạy độc lập. Khi dùng `new Child()`, `Child()` gọi `Child(5)`, constructor `Child(5)` gọi `Base(5)`, rồi phần thân còn lại của `Child(5)` chạy. Không tạo thêm object `Child` hoặc `Base` nào ngoài instance đang xây dựng.

> Bài viết áp dụng **Java 21**. Khi tra cứu tài liệu của những phiên bản Java mới hơn, cần chú ý quy tắc về các statement trước constructor invocation có thể khác. Nếu cần biên dịch đúng theo Java 21, dùng JDK 21 hoặc trình biên dịch hỗ trợ chế độ `--release 21`, thay vì áp dụng cú pháp của phiên bản khác.

## 2. Phân biệt `this`, `this(...)`, `super` và `super(...)`

Cú pháp tương tự nhưng ý nghĩa khác nhau:

| Biểu thức | Loại | Dùng để làm gì? |
| --- | --- | --- |
| `this` | Tham chiếu trong ngữ cảnh instance | Chỉ đối tượng hiện tại, ví dụ `this.name`. |
| `this(...)` | Constructor invocation | Ủy quyền sang một constructor khác trong **cùng lớp**. |
| `super.field` | Truy cập thành viên superclass theo quy tắc | Chỉ rõ field superclass trong ngữ cảnh hợp lệ. |
| `super.method(...)` | Lời gọi method từ superclass | Dùng implementation superclass phù hợp, **không** phải constructor invocation. |
| `super(...)` | Constructor invocation | Gọi constructor của **superclass trực tiếp**. |
| `new Child(...)` | Class instance creation expression | Tạo instance mới, chọn constructor đích và bắt đầu chuỗi khởi tạo. |

Ví dụ:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;       // Gán field; KHÔNG phải this(...).
    }

    String name() {
        return this.name;       // Truy cập field của receiver.
    }
}
```

`this.name = name` **không cần** là statement đầu tiên, vì nó là phép gán field. Ràng buộc “statement đầu tiên” của Java 21 áp dụng riêng cho dạng **constructor invocation** `this(...)` hoặc `super(...)`.

Tương tự, trong một instance method, `super.toString()` là **method invocation**, không gọi lại constructor superclass, nên không chịu quy tắc vị trí đầu constructor.

## 3. `this(...)`: ủy quyền giữa các constructor cùng lớp

Giả sử một lớp hỗ trợ nhiều cách khởi tạo: không nhập thông tin, chỉ nhập tên hoặc nhập cả tên và số lượng. Không cần nhân bản logic kiểm tra ở từng constructor. Một constructor ít tham số có thể gọi overload nhiều tham số bằng `this(...)`.

```java
class Course {
    private final String title;
    private final int capacity;

    Course() {
        this("Untitled", 10);
    }

    Course(String title) {
        this(title, 10);
    }

    Course(String title, int capacity) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title required");
        }
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.title = title;
        this.capacity = capacity;
    }

    String summary() {
        return title + " (" + capacity + ")";
    }
}
```

Đây là **khai báo lớp có thể biên dịch** nhưng không có `main` riêng. Những lời gọi `new Course()`, `new Course("Java")` và `new Course("Java", 20)` đều dẫn về constructor `Course(String, int)`, nơi tập trung validation.

- `Course()` chọn constructor có danh sách tham số `(String, int)` vì nhận hai đối số `"Untitled"` và `10`.
- `Course(String)` cũng chọn constructor `(String, int)`, nhưng truyền tên người dùng.
- `Course(String, int)` là điểm cuối của chuỗi ủy quyền trong lớp này; nếu không có `super(...)` tường minh, Java 21 chèn lời gọi `super()` thích hợp ở đầu constructor.
- Các field `final` chỉ được gán trong constructor đủ tham số. Những constructor ủy quyền **không gán lại** chúng.

Một lần gọi `new Course()` tạo **một instance**, không phải ba instance. Việc đi qua nhiều constructor **không lặp** phần cấp phát bộ nhớ đối tượng hay initializer của lớp.

### Chương trình chạy độc lập minh họa `this(...)`

Tạo tệp **`ThisChainingDemo.java`**:

```java
class Ticket {
    private final String type;
    private final int quantity;

    Ticket() {
        this("standard");
        System.out.println("Ticket() body");
    }

    Ticket(String type) {
        this(type, 1);
        System.out.println("Ticket(String) body");
    }

    Ticket(String type, int quantity) {
        this.type = type;
        this.quantity = quantity;
        System.out.println("Ticket(String,int) body");
    }

    String summary() {
        return type + " x " + quantity;
    }
}

public class ThisChainingDemo {
    public static void main(String[] args) {
        Ticket ticket = new Ticket();
        System.out.println(ticket.summary());
    }
}
```

Biên dịch và chạy với Java 21:

```bash
javac --release 21 ThisChainingDemo.java
java ThisChainingDemo
```

**Standard output:**

```text
Ticket(String,int) body
Ticket(String) body
Ticket() body
standard x 1
```

Lời gọi `new Ticket()` vào `Ticket()`, sau đó ủy quyền theo chuỗi:

```text
new Ticket()
    |
    +--> Ticket()
             |
             +--> Ticket("standard")
                        |
                        +--> Ticket("standard", 1)
                                    |
                                    +--> super() tới Object()
                                    |
                                    +--> Gán type, quantity
                                    +--> In "Ticket(String,int) body"
                        |
                        +--> In "Ticket(String) body"
             |
             +--> In "Ticket() body"
    |
    +--> main gọi summary()
```

Đây là cấu trúc **gọi và quay lại**: constructor đích sâu nhất hoàn tất trước, rồi lần lượt trở về các constructor ủy quyền để chạy các statement **sau `this(...)`**. `Object()` không in ra gì trong ví dụ.

**Điểm dễ nhầm:** `this(...)` không phải lời gọi method tự do để đặt giữa constructor. Trong Java 21, nó **phải đứng đầu** constructor và không được dùng ở method hay initializer block.

## 4. `super(...)`: khởi tạo phần superclass

Constructor của lớp con luôn phải tuân thủ việc khởi tạo superclass thích hợp. Với Java 21, một constructor lớp con có thể mở đầu bằng lời gọi tường minh `super(args)` để chọn constructor của superclass trực tiếp.

```java
class Vehicle {
    private final String category;

    Vehicle(String category) {
        this.category = category;
    }

    String category() {
        return category;
    }
}

class Car extends Vehicle {
    private final String model;

    Car(String model) {
        super("road"); // Bắt buộc khi superclass không có Vehicle().
        this.model = model;
    }

    String describe() {
        return category() + ": " + model;
    }
}
```

Đoạn lớp trên biên dịch được, nhưng không chứa `main`. `Vehicle` chỉ có `Vehicle(String)`, nên `Car(String)` **phải** gọi constructor superclass tương thích. `super("road")` đứng đầu constructor rồi mới đến phép gán `this.model = model`.

Lệnh `super("road")` không làm xuất hiện một đối tượng `Vehicle` riêng. `new Car("Sedan")` tạo một instance `Car`, trong đó phần trạng thái kế thừa từ `Vehicle` cũng được khởi tạo thông qua constructor superclass.

### Ví dụ chạy độc lập: constructor cha thực thi trước constructor con

Tạo tệp **`SuperChainingDemo.java`**:

```java
class Equipment {
    private final String family;

    Equipment(String family) {
        this.family = family;
        System.out.println("Equipment constructor");
    }

    String family() {
        return family;
    }
}

class Laptop extends Equipment {
    private final String model;

    Laptop(String model) {
        super("computer");
        this.model = model;
        System.out.println("Laptop constructor");
    }

    String description() {
        return family() + "/" + model;
    }
}

public class SuperChainingDemo {
    public static void main(String[] args) {
        Laptop laptop = new Laptop("Think");
        System.out.println(laptop.description());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 SuperChainingDemo.java
java SuperChainingDemo
```

```text
Equipment constructor
Laptop constructor
computer/Think
```

Trong `Laptop(String)`, `super("computer")` chuyển quyền điều khiển sang `Equipment(String)`. Chỉ **sau khi constructor của `Equipment` hoàn thành bình thường**, phần tiếp theo của constructor `Laptop` mới thực hiện. Đây là một cách Java bảo đảm phần superclass được khởi tạo trước những câu lệnh trong thân constructor subclass.

### `super(...)` chỉ gọi superclass trực tiếp

Giả sử cây kế thừa là `Grandparent ← Parent ← Child`. Constructor `Child` không trực tiếp gọi constructor `Grandparent` bằng một dạng `super.super(...)`. `Child` gọi constructor `Parent`, và chính constructor `Parent` gọi constructor `Grandparent` theo chuỗi của lớp cha. Mỗi lớp chịu trách nhiệm về constructor của superclass **trực tiếp** của mình.

## 5. Quy tắc “statement đầu tiên” của Java 21

Trong **Java 21**, một constructor có thể có lời gọi `this(...)` hoặc `super(...)` tường minh, nhưng lời gọi đó **phải xuất hiện như statement đầu tiên trong thân constructor**.

### Hợp lệ

```java
class Valid {
    Valid() {
        this(1);
        System.out.println("after this");
    }

    Valid(int value) {
        super();
        System.out.println("value=" + value);
    }
}
```

`this(1)` đứng đầu `Valid()`. `super()` đứng đầu `Valid(int)`. Các câu `println` theo sau là hợp lệ.

### Không hợp lệ: statement đứng trước `this(...)`

```java
// class Invalid {
//     Invalid() {
//         int count = 1;    // Statement đứng trước.
//         this(count);       // Sai trong Java 21.
//     }
//
//     Invalid(int count) {
//     }
// }
```

Dòng `int count = 1;` không được đặt trước `this(count)` trong Java 21. Ngay cả khi muốn chuẩn bị giá trị truyền cho constructor khác, phải tính giá trị đó **trong biểu thức đối số** hợp lệ hoặc chuyển logic sang một static helper/factory thích hợp.

Sửa:

```java
class ValidCount {
    ValidCount() {
        this(1);
    }

    ValidCount(int count) {
        System.out.println(count);
    }
}
```

### Không hợp lệ: in log trước `super(...)`

```java
// class Parent {
//     Parent(int id) { }
// }
//
// class BadChild extends Parent {
//     BadChild() {
//         System.out.println("before parent");
//         super(7); // Sai: không đứng đầu trong Java 21.
//     }
// }
```

Sửa bằng cách đặt `super(7)` trước rồi mới in, hoặc đặt log trong phần thực thi của constructor superclass nếu đúng thiết kế.

```java
class Parent {
    Parent(int id) {
        System.out.println("parent " + id);
    }
}

class GoodChild extends Parent {
    GoodChild() {
        super(7);
        System.out.println("child");
    }
}
```

Nếu gọi `new GoodChild()` trong một method, hai dòng được in lần lượt là `parent 7` rồi `child`. Đoạn khai báo trên biên dịch được nhưng không chứa `main` riêng.

### Không hợp lệ: giấu constructor invocation trong khối điều kiện

```java
// class Bad {
//     Bad(boolean enabled) {
//         if (enabled) {
//             this(); // Sai: constructor invocation không đặt trong if.
//         }
//     }
//
//     Bad() { }
// }
```

Java 21 không cho đặt `this()` hoặc `super()` như statement tùy ý trong `if`, `for`, `while`, `try`, method hay instance initializer. Để chọn cách khởi tạo theo điều kiện, thường truyền **biểu thức điều kiện** như đối số của lời gọi đứng đầu:

```java
class Choice {
    private final int value;

    Choice(boolean enabled) {
        this(enabled ? 10 : 0);
    }

    Choice(int value) {
        this.value = value;
    }

    int getValue() {
        return value;
    }
}
```

Ví dụ `new Choice(true).getValue()` trả `10`; `new Choice(false).getValue()` trả `0`. Điều kiện được tính khi **đánh giá đối số** của `this(...)`, chứ không phải đặt một statement `if` trước constructor invocation.

## 6. Một constructor có được viết cả `this(...)` và `super(...)` không?

**Không.** Trong một constructor Java 21, không thể viết cả hai lời gọi constructor tường minh. Vì mỗi lời gọi phải là statement đầu tiên, không thể có hai statement đều đứng đầu một constructor.

Ví dụ cố ý sai:

```java
// class Parent {
//     Parent() { }
// }
//
// class Child extends Parent {
//     Child() {
//         this(1);
//         super(); // Sai: không được có lời gọi thứ hai.
//     }
//
//     Child(int value) {
//     }
// }
```

Nhưng **cả hai từ khóa vẫn có thể xuất hiện trong những constructor khác nhau của cùng lớp**:

```java
class Base {
    Base(String code) {
        System.out.println("Base:" + code);
    }
}

class Derived extends Base {
    Derived() {
        this("A");
    }

    Derived(String code) {
        super(code);
        System.out.println("Derived:" + code);
    }
}
```

`Derived()` mở đầu bằng `this("A")`. Constructor đích `Derived(String)` mở đầu bằng `super(code)`. Đây là **chuỗi hợp lệ** và không trái quy tắc: mỗi constructor chỉ có **một** lời gọi constructor tường minh ở đầu thân mình.

Nếu tạo `new Derived()`, hai dòng in là `Base:A` và `Derived:A`. Không có constructor `Base` thứ hai được gọi.

### Vì sao ủy quyền bằng `this(...)` vẫn có gọi superclass?

Chuỗi constructor của một instance phải cuối cùng đi tới việc khởi tạo superclass thích hợp. Nếu `Derived()` gọi `this("A")`, sau đó `Derived(String)` gọi `super("A")`, thì superclass đã được khởi tạo **qua constructor đích cuối của chuỗi trong `Derived`**.

Không được tự bổ sung `super()` vào `Derived()` sau `this("A")`. Điều đó sẽ gây xung đột và về mặt ý nghĩa còn là yêu cầu khởi tạo superclass lặp.

## 7. Nếu không viết `this(...)` hoặc `super(...)` thì sao?

Trong constructor của một class thông thường khác `Object`, nếu không ghi lời gọi constructor tường minh, Java 21 về cơ bản xử lý như có một lời gọi **`super()` ngầm** ở đầu constructor (nếu các điều kiện hợp lệ).

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

Trong ví dụ này, `Child()` không ghi `super()`, nhưng compiler vẫn gọi constructor không tham số của `Parent` trước khi thực hiện câu in ở thân `Child()`.

Cùng ý nghĩa thực thi thông thường:

```java
class Child extends Parent {
    Child() {
        super();
        System.out.println("Child()");
    }
}
```

Hai khai báo `Child` phía trên là **hai phiên bản riêng để so sánh**, không đặt đồng thời vào cùng chương trình. Khi gọi `new Child()`, output là:

```text
Parent()
Child()
```

### Quan hệ với default constructor

Nếu **cả lớp con không khai báo constructor nào**, compiler ngầm khai báo một **default constructor** không tham số và gọi `super()` tương ứng:

```java
class Parent {
    Parent() {
        System.out.println("Parent()");
    }
}

class Child extends Parent {
    // Không có constructor do người viết khai báo.
}
```

`Child` được cấp default constructor theo quy tắc của class thông thường. Nhưng nếu `Parent()` không tồn tại hoặc không thể truy cập, việc compiler muốn sinh default constructor cho `Child` **không bảo đảm class biên dịch được**. Sự vắng mặt của constructor declaration ở subclass **không khiến compiler bịa một constructor superclass phù hợp**.

### `java.lang.Object` là trường hợp gốc

Mọi class thông thường cuối cùng đều có `java.lang.Object` ở đỉnh chuỗi kế thừa. Constructor của chính `Object` không thể tiếp tục gọi một superclass không tồn tại. Hãy xem quy tắc `super()` ngầm là quy tắc của các class thông thường có superclass, **không áp dụng máy móc cho constructor của chính `Object`**.

## 8. Thiếu constructor `super()` phù hợp: lỗi biên dịch rất phổ biến

Ví dụ:

```java
// class Base {
//     Base(int id) { }
// }
//
// class Derived extends Base {
//     Derived() {
//         System.out.println("Derived");
//     }
// }
```

Đây là đoạn **cố ý sai**, được comment. `Base` chỉ khai báo `Base(int)`; nó **không có constructor `Base()`**. Vì `Derived()` không ghi `this(...)` hoặc `super(...)`, compiler sẽ cần gọi `super()` ngầm. Lời gọi đó không có constructor đích hợp lệ, nên biên dịch thất bại.

Sửa:

```java
class Base {
    private final int id;

    Base(int id) {
        this.id = id;
    }

    int id() {
        return id;
    }
}

class Derived extends Base {
    Derived() {
        super(7);
    }
}
```

Ở phiên bản sửa, `super(7)` đứng đầu `Derived()` và khớp constructor `Base(int)`. Mã này biên dịch được khi các constructor truy cập được trong ngữ cảnh tương ứng.

### Constructor superclass có tồn tại nhưng inaccessible

Không chỉ thiếu `Base()`, một constructor không tham số **không truy cập được** cũng khiến `super()` ngầm/tường minh không hợp lệ:

```java
// class Base {
//     private Base() { }
// }
//
// class Child extends Base {
//     Child() { } // Implicit super() không gọi được private Base().
// }
```

Ví dụ cố ý sai khi hai lớp là top-level, không có quan hệ đặc biệt cho phép truy cập private. Phải thiết kế constructor superclass có mức truy cập phù hợp, hoặc cung cấp đường khởi tạo được phép khác.

Nếu superclass yêu cầu đối số, cần **chọn constructor thích hợp bằng `super(args)`** từ constructor subclass; không tự thêm constructor rỗng vào superclass chỉ để qua lỗi compiler khi nó có thể tạo trạng thái thiếu hợp lệ.

## 9. Quy tắc chọn overload cho `this(...)` và `super(...)`

Cũng như lời gọi method được nạp chồng, một lớp có thể có **nhiều constructor khác danh sách tham số**, và compiler phải chọn một constructor đích tương ứng với **số lượng, kiểu tĩnh của biểu thức đối số và những chuyển đổi cho phép**.

```java
class Base {
    Base(int number) {
        System.out.println("Base.int=" + number);
    }

    Base(String name) {
        System.out.println("Base.String=" + name);
    }
}

class Child extends Base {
    Child() {
        super(5);
    }

    Child(String name) {
        super(name);
    }
}
```

`new Child()` dùng `super(5)` và gọi `Base(int)`. `new Child("Lan")` dùng `super(name)` và gọi `Base(String)`. Trong Java 21, cả hai constructor của `Child` hợp lệ vì `super(...)` đứng đầu.

### Ambiguous constructor invocation với `null`

```java
class Choice {
    Choice(String value) {
    }

    Choice(Integer value) {
    }

    static void demonstrate() {
        // new Choice(null); // Lỗi ambiguous: String hay Integer?
        new Choice((String) null);
    }
}
```

Java không dùng kiểu runtime của `null` để đoán overload. Hai kiểu `String` và `Integer` đều là reference type không có quan hệ subtype quyết định bản cụ thể nhất; cast tường minh có thể chọn một constructor, nhưng **giá trị vẫn là `null`**.

### Truyền đối số cho `this(...)` không có nghĩa sao chép object

Trong `Child() { this(5); }`, biểu thức `5` là đối số constructor khác, nhưng compiler/JVM không tạo thêm một `Child` vì có lời gọi `this(...)`. Một instance mới được tạo bởi **biểu thức `new Child()`**, còn các constructor trong chuỗi cùng tham gia xây dựng instance ấy.

## 10. Đối số của lời gọi đầu tiên: được dùng gì?

Vì Java 21 yêu cầu `this(...)`/`super(...)` đứng đầu constructor, bạn **không thể chuẩn bị một biến cục bộ bằng statement trước đó**. Tuy nhiên, đối số có thể là những **biểu thức hợp lệ** như tham số constructor, literal, phép tính hoặc static helper không phụ thuộc trạng thái instance chưa khởi tạo.

Ví dụ:

```java
class Document {
    private final String title;

    Document() {
        this(defaultTitle());
    }

    Document(String title) {
        this.title = title;
    }

    private static String defaultTitle() {
        return "Untitled";
    }

    String title() {
        return title;
    }
}
```

`defaultTitle()` là **static method** nên có thể dùng để tính đối số của `this(...)` mà không cần object đã dựng xong. `new Document().title()` trả `Untitled`.

### Dùng tham số constructor và biểu thức tính toán

```java
class CountBase {
    CountBase(int count) {
        System.out.println("count=" + count);
    }
}

class CountChild extends CountBase {
    CountChild(int requested) {
        super(Math.max(0, requested));
    }
}
```

`Math.max` là static method; constructor parameter `requested` đã có giá trị từ caller. `super(Math.max(0, requested))` là statement đầu tiên và có biểu thức đối số hợp lệ. `new CountChild(-2)` khiến superclass in `count=0`.

### Không truy cập instance chưa hoàn tất từ explicit constructor invocation

Trong Java 21, **explicit constructor invocation** là ngữ cảnh bị hạn chế về việc tham chiếu instance hiện tại (*static context* theo ngữ nghĩa liên quan của JLS). Không được dùng `this`, `super` làm receiver hoặc tham chiếu trực tiếp instance field/method của object đang khởi tạo để tính đối số.

Ví dụ lỗi có chủ đích:

```java
// class Bad {
//     private int amount = 10;
//
//     Bad() {
//         this(amount); // Lỗi: dùng instance field của object hiện tại ở đây.
//     }
//
//     Bad(int amount) {
//     }
// }
```

Sửa bằng tham số, literal hoặc static helper, hay đưa logic phụ thuộc instance field sang **sau khi** constructor invocation đã hoàn tất, nếu vẫn bảo đảm thiết kế hợp lệ.

Cũng không nên nhầm đây với lệnh `this.name = name;` **sau `super(...)`** trong thân constructor; phép gán field đó hợp lệ khi ngữ cảnh và definite assignment phù hợp.

### Side effect trong biểu thức đối số

Biểu thức đối số có thể gọi một static method in log hoặc thay đổi static state. Điều đó có thể tạo ra output **trước khi** phần thân constructor đích chạy, dù câu `this(...)`/`super(...)` vẫn đứng đầu constructor về **vị trí cú pháp**. “Lời gọi constructor phải đầu tiên” không đồng nghĩa “không biểu thức nào được đánh giá trước khi constructor đích chạy”.

Tệp **`ConstructorArgumentDemo.java`**:

```java
class Root {
    Root(int id) {
        System.out.println("Root(" + id + ")");
    }
}

class Branch extends Root {
    private static int supply() {
        System.out.println("computing argument");
        return 9;
    }

    Branch() {
        super(supply());
        System.out.println("Branch()");
    }
}

public class ConstructorArgumentDemo {
    public static void main(String[] args) {
        new Branch();
    }
}
```

```bash
javac --release 21 ConstructorArgumentDemo.java
java ConstructorArgumentDemo
```

```text
computing argument
Root(9)
Branch()
```

`supply()` được gọi để tính **đối số** của `super(...)`. Nó chạy trước khi constructor `Root(int)` bắt đầu in; điều này không vi phạm first-statement rule. Không nên lạm dụng những side effect ở đối số constructor vì làm mã khó dự đoán.

## 11. Thứ tự khởi tạo trong chuỗi nhiều lớp

Điều người học hay nhầm nhất không phải cú pháp đơn lẻ mà là **đâu chạy trước, đâu chạy sau** khi có:

- Constructor superclass.
- Instance field initializers và instance initializer blocks của superclass/subclass.
- Constructor chaining `this(...)` giữa các overload trong cùng lớp.
- Thân constructor ở mỗi mức.

Trong ví dụ class thường, quá trình được mô tả bằng thứ tự cơ bản:

1. Các lớp cần thiết được **class-initialized** theo quy tắc riêng khi dùng (static initialization); đây là cơ chế khác với instance initialization.
2. Khi `new Child(...)` được thực hiện, object được cấp phát và các instance fields được cấp **giá trị mặc định**.
3. Chuỗi constructor đi qua `this(...)` nếu có, sau đó tới lời gọi `super(...)` hoặc `super()` thích hợp.
4. Constructor/khởi tạo instance của các superclass thực hiện theo thứ tự từ **gốc đến con**.
5. Sau khi superclass constructor hoàn tất bình thường, các **instance field initializers** và **instance initializer blocks** của lớp hiện tại chạy theo **thứ tự xuất hiện trong mã nguồn**.
6. Thân constructor đích trong lớp hiện tại chạy; các constructor gọi `this(...)` ở lớp ấy tiếp tục chạy phần **sau lời gọi ủy quyền** khi constructor đích trả về.

Các initializer của **một lớp** không tự chạy lại nhiều lần vì một constructor `this(...)` ủy quyền qua một constructor khác của **cùng object**.

### Chương trình Java 21 tổng hợp và stdout xác định

Tạo tệp **`ConstructionOrderDemo.java`**:

```java
class Parent {
    Parent(int id) {
        System.out.println("Parent constructor: " + id);
    }
}

class Child extends Parent {
    private int value = initializeValue();

    {
        System.out.println("Child instance block");
    }

    Child() {
        this(3);
        System.out.println("Child() body");
    }

    Child(int id) {
        this(id, "ready");
        System.out.println("Child(int) body");
    }

    Child(int id, String label) {
        super(id);
        value += 2;
        System.out.println("Child(int,String) body: " + label);
    }

    private int initializeValue() {
        System.out.println("Child field initializer");
        return 5;
    }

    int value() {
        return value;
    }
}

public class ConstructionOrderDemo {
    public static void main(String[] args) {
        System.out.println("begin");
        Child child = new Child();
        System.out.println("value=" + child.value());
    }
}
```

Lệnh:

```bash
javac --release 21 ConstructionOrderDemo.java
java ConstructionOrderDemo
```

Output chính xác:

```text
begin
Parent constructor: 3
Child field initializer
Child instance block
Child(int,String) body: ready
Child(int) body
Child() body
value=7
```

**Giải thích từng dòng:**

1. `main` in `begin` trước khi gọi `new Child()`.
2. `Child()` gọi `this(3)`; `Child(int)` gọi `this(3, "ready")`; `Child(int, String)` gọi `super(3)`. Vì vậy constructor `Parent(int)` in `Parent constructor: 3`.
3. Sau khi superclass hoàn tất, field initializer `value = initializeValue()` chạy **một lần** trong quá trình xây dựng object `Child`, in `Child field initializer` và trả `5`.
4. Instance initializer block tiếp theo in `Child instance block`, cũng **chỉ một lần**.
5. Thân `Child(int, String)` tăng `value` từ `5` lên `7` và in `Child(int,String) body: ready`.
6. Constructor `Child(int)` đã chờ `this(...)` hoàn tất, giờ chạy dòng in `Child(int) body`.
7. Constructor `Child()` cũng tiếp tục sau `this(3)` và in `Child() body`.
8. `main` đọc field qua getter, in `value=7`.

Chương trình chứng minh ba điểm: **superclass được dựng trước phần instance của subclass**, **`this(...)` không tạo thêm object**, và **các instance initializers không lặp theo số overload được đi qua**.

### Sơ đồ luồng điều khiển

```text
main: new Child()
   |
   v
Child()
   | this(3)
   v
Child(int)
   | this(3, "ready")
   v
Child(int, String)
   | super(3)
   v
Parent(int)                 -> In Parent constructor: 3
   |
   v
Child field initializer     -> In Child field initializer; value = 5
   |
   v
Child instance block        -> In Child instance block
   |
   v
Child(int, String) body     -> value = 7; in Child(int,String) ...
   |
   v
Child(int) body             -> In Child(int) body
   |
   v
Child() body                -> In Child() body
   |
   v
main                        -> In value=7
```

Đây là sơ đồ riêng cho ví dụ, không biểu diễn đầy đủ mọi bước cấp phát, xác minh class, class loading hay các trường hợp exception.

## 12. Không được tạo chuỗi `this(...)` đệ quy vòng tròn

Một constructor `this(...)` phải cuối cùng chuyển sang một constructor **không ủy quyền ngược theo vòng lặp**. Nếu hai constructor gọi vòng qua nhau, Java phát hiện **recursive constructor invocation**.

Ví dụ cố ý không biên dịch:

```java
// class Loop {
//     Loop() {
//         this(1);
//     }
//
//     Loop(int n) {
//         this();
//     }
// }
```

Chuỗi `Loop() → Loop(int) → Loop() → ...` không có điểm dừng gọi superclass phù hợp. Compiler ngăn cấu trúc này.

Cách sửa là để một constructor đích cuối cùng thực hiện khởi tạo hợp lệ:

```java
class NonRecursive {
    private final int number;

    NonRecursive() {
        this(1);
    }

    NonRecursive(int number) {
        this.number = number;
    }
}
```

Trong `NonRecursive(int)` không có explicit constructor invocation; compiler thực hiện implicit `super()` thích hợp. Từ đó quá trình khởi tạo hoàn tất và trả về `NonRecursive()`.

### Tại sao Java cấm vòng constructor?

Mỗi constructor là một cách khởi tạo cùng instance. Nếu các constructor chỉ ủy quyền vòng quanh và không có đường tới superclass initialization/instance initialization hoàn chỉnh, không có một tiến trình xây dựng object hợp lệ. Cấm vòng ở **compile time** giúp ngăn lỗi này trước khi chương trình chạy.

## 13. `final` fields và constructor chaining

Một field `final` không có initializer tại nơi khai báo (*blank final instance field*) cần được **gán đúng quy tắc definite assignment** trong quá trình khởi tạo; không thể để các constructor hoàn tất bình thường mà field chưa được gán.

Constructor chaining thường giúp tập trung phép gán tại một điểm:

```java
class UserAccount {
    private final String username;
    private final int level;

    UserAccount(String username) {
        this(username, 1);
    }

    UserAccount(String username, int level) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username required");
        }
        if (level < 1) {
            throw new IllegalArgumentException("level must be positive");
        }
        this.username = username;
        this.level = level;
    }

    String summary() {
        return username + ":" + level;
    }
}
```

Hai field `final` được gán một lần ở constructor đích `UserAccount(String,int)`. `UserAccount(String)` gọi `this(username, 1)` và không phải gán lại các field. Nếu sau `this(...)` mà cố `this.level = 2;`, phép gán lại `final` đã được definite assigned có thể làm compiler báo lỗi.

Đặt validation ở constructor đích giúp các overload thống nhất bất biến; đây cũng là cách giữ một đường khởi tạo chính (*constructor delegation*).

### Phân biệt với phép gán field trong superclass

Subclass **không thể tự gán tùy ý private final field của superclass**. Nếu superclass có field bắt buộc, constructor superclass phải nhận đủ dữ liệu hoặc tự khởi tạo theo hợp đồng của nó; subclass chuyển dữ liệu hợp lệ bằng `super(args)`.

Không nên dùng `super(...)` chỉ để “đi qua compiler”, trong khi giá trị truyền vi phạm bất biến superclass.

## 14. `throws` và exception trên chuỗi constructor

Một constructor có thể **ném checked exception**. Nếu constructor superclass đích hoặc constructor cùng lớp đích có khai báo checked exception cần xử lý theo quy tắc, constructor đang gọi thường phải **khai báo `throws` phù hợp**. Trong Java 21, không thể bọc một explicit `super(...)`/`this(...)` bằng `try` đứng trước nó, vì lời gọi phải là statement đầu tiên.

Ví dụ hợp lệ:

```java
class DataSource {
    DataSource(String path) throws java.io.IOException {
        if (path.isBlank()) {
            throw new java.io.IOException("empty path");
        }
    }
}

class FileSource extends DataSource {
    FileSource(String path) throws java.io.IOException {
        super(path);
    }
}
```

`FileSource(String)` khai báo `throws IOException` để phù hợp với constructor superclass được gọi.

### Chương trình chạy có bắt ngoại lệ tại nơi tạo object

Tệp **`CheckedConstructorDemo.java`**:

```java
class ReaderBase {
    ReaderBase(String file) throws java.io.IOException {
        if (file.isEmpty()) {
            throw new java.io.IOException("filename missing");
        }
        System.out.println("reader opened");
    }
}

class TextReader extends ReaderBase {
    TextReader(String file) throws java.io.IOException {
        super(file);
        System.out.println("text reader ready");
    }
}

public class CheckedConstructorDemo {
    public static void main(String[] args) {
        try {
            new TextReader("");
        } catch (java.io.IOException ex) {
            System.out.println("error: " + ex.getMessage());
        }

        try {
            new TextReader("data.txt");
        } catch (java.io.IOException ex) {
            System.out.println("unexpected");
        }
    }
}
```

Lệnh:

```bash
javac --release 21 CheckedConstructorDemo.java
java CheckedConstructorDemo
```

Output:

```text
error: filename missing
reader opened
text reader ready
```

Ở lần tạo thứ nhất, constructor `ReaderBase` ném `IOException`, nên thân `TextReader` **không** chạy; ngoại lệ được bắt tại `main`. Ở lần tạo thứ hai, superclass hoàn tất, rồi subclass in dòng `text reader ready`. Ví dụ minh họa luồng exception, không thực sự mở file `data.txt`; tên file chỉ là chuỗi để kiểm tra điều kiện.

Một chi tiết đáng nhớ: nếu superclass chỉ có constructor không tham số `throws IOException` và subclass định dùng default constructor/implicit `super()`, vẫn phải đáp ứng quy tắc checked exception. Thường cần khai báo constructor subclass thích hợp có `throws IOException` thay vì mặc định hy vọng compiler tự thêm khai báo `throws`.

## 15. Constructor và phương thức ghi đè: tránh gọi method override quá sớm

Constructor superclass thực thi trước khi field initializers và constructor body của subclass hoàn tất. Nếu constructor superclass gọi một **instance method có thể override**, dynamic dispatch có thể chạy method của subclass **trước khi state subclass được khởi tạo xong**.

Tạo tệp **`EarlyDispatchDemo.java`**:

```java
class Parent {
    Parent() {
        display();
    }

    void display() {
        System.out.println("Parent.display");
    }
}

class Child extends Parent {
    private int level = 7;

    @Override
    void display() {
        System.out.println("level=" + level);
    }
}

public class EarlyDispatchDemo {
    public static void main(String[] args) {
        Child child = new Child();
        child.display();
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 EarlyDispatchDemo.java
java EarlyDispatchDemo
```

```text
level=0
level=7
```

**Vì sao lần đầu là 0?**

1. `new Child()` bắt đầu xây dựng `Child`, rồi qua constructor superclass `Parent()`.
2. `Parent()` gọi `display()`. Vì receiver runtime chính là object `Child`, Java **dispatch** đến `Child.display()` dù quá trình tạo object chưa hoàn tất.
3. Tại thời điểm đó, field `level` của `Child` mới mang **giá trị mặc định `0`**, chưa chạy field initializer `level = 7`.
4. Sau khi `Parent()` trả về, initializer của `Child` mới gán `7`. Lần gọi `child.display()` sau khi constructor hoàn tất in `level=7`.

Đây không phải lỗi của `this(...)` hay `super(...)` về cú pháp, mà là hậu quả của **runtime polymorphism trong lúc xây dựng object**. Tránh gọi method có thể override từ constructor khi implementation lớp con có thể phụ thuộc field chưa khởi tạo.

## 16. Những trường hợp đặc biệt cần biết để không áp dụng sai

### 16.1. Constructor không được kế thừa hoặc override

Subclass **không thừa hưởng** constructor superclass. `super(...)` là lời gọi constructor đích thích hợp, không phải overriding. Hai constructor ở hai lớp cùng nhận `String` **không phải** “ghi đè constructor”.

Constructor cũng không phải method, không khai báo `static`, `final` hoặc `abstract` và không có kiểu trả về.

### 16.2. Constructor mặc định khác `this()`

Nếu class thông thường **không khai báo constructor nào**, compiler có thể ngầm tạo **default constructor** không tham số, với implicit `super()` theo quy tắc.

Trong một constructor **do bạn viết**, `this()` lại là lời gọi **constructor không tham số của cùng lớp**; constructor đích phải tồn tại. Nếu chỉ có constructor nhận `int` và bạn viết `this()`, compiler không sinh thêm một no-arg constructor để đáp ứng.

```java
// class X {
//     X(int n) { }
//
//     X(String s) {
//         this(); // Lỗi: không có X() để gọi.
//     }
// }
```

### 16.3. Inner class và qualified superclass invocation

Với non-static inner class, đối tượng inner có thể cần **enclosing instance**. Một số constructor trong cây inner classes có thể dùng dạng qualified superclass constructor invocation như `enclosingExpression.super(...)` theo điều kiện ngôn ngữ riêng, ngoài hai dạng cơ bản `this(...)` và `super(...)`.

Ở mức kiến thức nhập môn, hãy nhớ yêu cầu có enclosing instance và không tự áp dụng cú pháp `super()` của top-level class cho mọi tình huống inner class phức tạp. Những trường hợp này vẫn chịu các ràng buộc tương ứng về explicit constructor invocation trong Java 21.

### 16.4. Enum và record có quy tắc constructor riêng

- **Enum** được Java quản lý tập instance theo enum constants; không tạo bằng `new EnumName()` từ code ứng dụng, và constructor enum có những hạn chế riêng.
- **Record** (Java 21 hỗ trợ) có **canonical constructor** liên quan tới record components; constructor bổ sung có những quy tắc delegation đặc biệt. Không thể giả định record `record Point(int x, int y) {}` tự có no-arg constructor giống class rỗng.
- **Anonymous class** cũng có quy tắc constructor ngầm riêng; nó không có tên class nguồn để bạn gọi `this(...)`/`super(...)` như class đặt tên thông thường.

Bài này tập trung vào **constructor chaining của class Java thông thường**. Khi làm việc với enum/record/inner/anonymous classes, hãy áp dụng đúng quy tắc theo loại khai báo.

### 16.5. Khi cần tương thích Java 21

Nếu dự án biên dịch với Java 21, ví dụ sau là **sai**, dù ai đó chỉ ra một ngôn ngữ hoặc phiên bản Java khác cho phép:

```java
// class Example {
//     Example() {
//         System.out.println("before");
//         super(); // Không được: trong Java 21 super() phải ở đầu.
//     }
// }
```

Để kiểm thử cú pháp Java 21 khi có JDK phù hợp, có thể biên dịch với `javac --release 21 FileName.java`. Nếu đang sử dụng chính JDK 21, lệnh `javac FileName.java` cũng dùng quy tắc ngôn ngữ của phiên bản đó theo cấu hình mặc định. Không nhầm cờ `--release` với việc runtime tự động chạy được trên JDK thấp hơn chỉ nhờ chọn cú pháp.

## 17. Checklist phân tích một chuỗi constructor Java 21

Khi đọc một constructor, lần lượt trả lời:

1. **Lớp hiện tại là gì?** Nó có superclass trực tiếp nào, superclass có constructor nào và mức truy cập của chúng ra sao?
2. **Statement đầu tiên của constructor là gì?** Nếu là `this(...)`, đi tới constructor cùng lớp; nếu là `super(...)`, đi tới constructor superclass; nếu không có explicit invocation, xét `super()` ngầm thích hợp.
3. **Các đối số phù hợp constructor đích nào?** Kiểm tra số lượng, kiểu, overload resolution, khả năng truy cập và checked exceptions.
4. **Có statement nào trước explicit constructor invocation không?** Trong **Java 21**, điều đó không hợp lệ.
5. **Có vòng gọi `this(...)` không?** Mọi chuỗi ủy quyền trong cùng lớp phải có đường kết thúc hợp lệ.
6. **Superclass được khởi tạo thế nào?** Theo chuỗi đi từ superclass gốc về subclass hiện tại, không tạo một superclass object riêng.
7. **Field initializer và instance initializer của từng lớp chạy lúc nào?** Theo thứ tự mã nguồn sau phần khởi tạo superclass, và **không lặp** do `this(...)` delegation.
8. **Thân constructor nào in/log/đổi field trước?** Ghi rõ lúc đi vào và lúc quay trở lại từ constructor đích.
9. **Có field `final` chưa được gán hay gán hai lần không?** Kiểm tra definite assignment trên mọi constructor hoàn tất bình thường.
10. **Có method overridable nào bị gọi trong superclass constructor không?** Nó có thể thấy subclass field chưa khởi tạo hoàn toàn.
11. **Có exception trong super constructor không?** Nếu có, phần còn lại của chuỗi không hoàn tất bình thường; checked exceptions phải được khai báo/xử lý hợp lệ.
12. **Có phụ thuộc cú pháp phiên bản Java khác không?** Nếu đề yêu cầu Java 21, luôn đối chiếu quy tắc phiên bản đó.

## 18. Các lỗi biên dịch và cách sửa nhanh

| Tình huống | Vì sao sai trong Java 21? | Cách sửa |
| --- | --- | --- |
| `println(...); this(...);` | `this(...)` không là statement đầu tiên | Đặt `this(...)` đầu; in sau |
| `int x = 1; super(x);` | `super(...)` không là statement đầu tiên | Truyền biểu thức `super(1)` hoặc tham số/static helper |
| `if (flag) this();` | Explicit constructor invocation không nằm trực tiếp ở vị trí đầu hợp lệ | Dùng một `this(flag ? a : b)` với constructor đích phù hợp |
| `this(...); super(...);` | Hai constructor invocations cùng một constructor; lời gọi sau không được phép | Để constructor `this(...)` đích xử lý super chain |
| `A() { this(1); }` và `A(int) { this(); }` | Recursive constructor invocation | Thiết kế một constructor đích không ủy quyền vòng |
| `Child() { }` khi `Parent` chỉ có `Parent(int)` | `super()` ngầm không tìm được đích | Viết `super(validInt)` ở đầu hoặc thay thiết kế superclass |
| `this(instanceField)` | Không được dùng instance hiện tại để đánh giá đối số explicit constructor invocation trong Java 21 | Dùng tham số/literal/static method |
| `this()` nhưng không có constructor cùng lớp không tham số | Không có constructor đích | Thêm explicit no-arg constructor hợp lệ hoặc gọi overload tồn tại |
| `super()` tới constructor private không truy cập được | Lỗi quyền truy cập | Cung cấp constructor superclass accessible phù hợp |
| `super(args)` gọi constructor có checked exception nhưng subclass không khai báo | Không đáp ứng kiểm tra checked exception | Khai báo `throws` phù hợp hoặc điều chỉnh thiết kế |

Các mảnh lỗi trong bảng được trình bày để **nhận diện và chẩn đoán**, không phải mã độc lập để biên dịch nguyên văn.

## 19. Tự luyện tập kèm đáp án

**Câu 1.** `this(...)` khác `super(...)` ở điểm cốt lõi nào?

*Đáp án:* `this(...)` gọi constructor khác của **cùng lớp**; `super(...)` gọi constructor của **superclass trực tiếp**. Cả hai tham gia xây dựng **cùng object**, không tạo thêm object.

**Câu 2.** Có được đặt `System.out.println("start");` trước `super(1);` trong constructor Java 21 không?

*Đáp án:* Không. `super(1)` tường minh phải là statement đầu tiên. Có thể đặt `println` sau nó.

**Câu 3.** Nếu `A() { this(1); }`, `A(int n) { this("x"); }` và `A(String s) { super(); }`, có bao nhiêu object `A` khi gọi `new A()`?

*Đáp án:* Một object. Chuỗi đi qua ba constructor trên cùng instance rồi khởi tạo superclass. Điều kiện superclass có constructor `super()` truy cập được vẫn phải đáp ứng.

**Câu 4.** `new Child()` có chạy constructor superclass nếu `Child()` chỉ viết `this(7)` không?

*Đáp án:* Có. Constructor `Child(int)` được ủy quyền sẽ tiếp tục chuỗi tới constructor superclass thích hợp (tường minh hoặc ngầm), miễn chuỗi hợp lệ.

**Câu 5.** Nếu superclass chỉ có `Parent(String)`, subclass viết `Child() { }` có biên dịch không?

*Đáp án:* Không, vì lời gọi ngầm `super()` không tìm thấy constructor superclass không tham số. Viết `Child() { super("default"); }` nếu đó là trạng thái hợp lệ.

**Câu 6.** Instance initializer của `Child` chạy bao nhiêu lần khi `Child()` gọi `this(1)` rồi `Child(int)` gọi `super()`?

*Đáp án:* Một lần cho mỗi object `Child` được tạo. `this(...)` không khởi tạo lại cùng lớp.

**Câu 7.** Vì sao `Child() { this(instanceField); }` không hợp lệ trong Java 21, dù field được gán initializer ở khai báo?

*Đáp án:* Đối số của explicit constructor invocation không thể dùng instance hiện tại ở ngữ cảnh này; field initializer của `Child` cũng chưa thể được dựa vào như trạng thái đã hoàn tất. Dùng tham số, literal hoặc static helper phù hợp.

**Câu 8.** Trong `ConstructionOrderDemo`, vì sao `Child(int,String) body` in trước `Child(int) body`?

*Đáp án:* `Child(int)` đã gọi `this(id, "ready")` và phải chờ constructor đích hoàn tất. Sau khi đích trả về mới chạy phần thân còn lại của `Child(int)`.

**Câu 9.** `super.method()` có tuân quy tắc phải là câu lệnh đầu tiên trong constructor không?

*Đáp án:* Không. Đó là **method invocation**, không phải constructor invocation `super(...)`. Nhưng lời gọi ấy vẫn phải nằm ở ngữ cảnh và thời điểm hợp lệ.

**Câu 10.** Hai constructor `C() { this(1); }` và `C(int x) { this(); }` có tạo chuỗi hợp lệ không?

*Đáp án:* Không. Đó là recursive constructor invocation, không có đường tới superclass initialization thích hợp.

**Câu 11.** Nếu superclass constructor ném `IOException`, subclass cần lưu ý gì?

*Đáp án:* Constructor subclass gọi nó phải thỏa quy tắc checked exception, thường khai báo `throws IOException` và để caller xử lý. Không thể đơn giản đặt `try` trước `super(...)` trong Java 21.

**Câu 12.** Vì sao constructor superclass gọi một overridable method có thể in giá trị mặc định của field subclass?

*Đáp án:* Runtime dispatch có thể gọi implementation subclass khi field initializer của subclass chưa chạy, nên các field đó vẫn ở giá trị mặc định trong giai đoạn này.

---

**Ghi nhớ:** Trong **Java 21**, lời gọi constructor tường minh **`this(...)` hoặc `super(...)` phải là statement đầu tiên** trong constructor. `this(...)` ủy quyền trong cùng lớp; `super(...)` gọi constructor superclass trực tiếp. Nếu không khai báo invocation tường minh, Java thông thường dùng `super()` ngầm; vì vậy superclass phải có constructor phù hợp và truy cập được. Một chuỗi `this(...)` không được đệ quy vòng, không khởi tạo lặp instance field và không tạo thêm object. Khi truy vết output, hãy đi theo chuỗi constructor tới superclass, rồi trở lại qua initializer và các thân constructor theo thứ tự hoàn tất.