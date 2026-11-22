# `super` để gọi hàm khởi tạo và truy cập thành viên lớp cha trong Java

## 1. `super` là gì, giải quyết vấn đề nào?

Trong Java, **`super`** là cú pháp dùng trong ngữ cảnh kế thừa để **tham chiếu tới phần khai báo/hành vi của lớp cha trực tiếp (*direct superclass*)** trong những trường hợp ngôn ngữ cho phép. Hai cách sử dụng quan trọng nhất là:

- **`super(arguments)`**: gọi một **constructor của lớp cha trực tiếp** từ constructor lớp con.
- **`super.member` / `super.method(arguments)`**: truy cập field hoặc gọi **instance method implementation thuộc phần superclass** từ ngữ cảnh instance của lớp con.

Hai trường hợp trông giống nhau nhưng có **ngữ nghĩa khác hẳn**. `super(...)` là *explicit constructor invocation* thực hiện trong quá trình xây dựng object. `super.method()` là lời gọi method chỉ rõ implementation của superclass, thường dùng khi subclass **override** method nhưng vẫn muốn dùng một phần hành vi cha.

~~~java
class Parent {
    Parent(String name) {
        System.out.println("Parent: " + name);
    }

    String description() {
        return "From Parent";
    }
}

class Child extends Parent {
    Child(String name) {
        super(name); // Gọi constructor Parent(String)
    }

    @Override
    String description() {
        return super.description() + " + Child";
    }
}
~~~

Đây là **khai báo class minh họa**, chưa có method `main` để chạy độc lập.

**Điểm mấu chốt:** `super` **không tạo object cha riêng**. Với `new Child("Lan")`, Java xây dựng **một object runtime type Child**, và constructor của Parent tham gia khởi tạo phần state/hợp đồng của Parent trong object ấy. Lời gọi `super.description()` vẫn chạy trên **cùng receiver object đang dùng**, nhưng chỉ rõ implementation từ superclass phù hợp.

Bài học dành cho **Java 17+**, thuộc chủ đề **Kế thừa và đa hình** trong Java Core. Ta sẽ lần lượt học cú pháp, constructor chaining, trường hợp thiếu `super()`, thứ tự khởi tạo, overriding và dynamic dispatch, `super.field`, access control, `InterfaceName.super`, lỗi compile/runtime, thiết kế inheritance đúng và các ví dụ hoàn chỉnh có stdout chính xác.

## 2. Phân biệt `this` và `super`

Một class con có hai cách tham chiếu trong instance context:

- **`this`**: đối tượng hiện tại (*current object*), có runtime class là class thực tế đang được tạo hoặc đang nhận method call.
- **`super`**: cú pháp cho phép chọn những thành viên/constructor từ phần superclass theo luật Java; **không phải tham chiếu tới một object khác**.

| Cú pháp | Công dụng | Vị trí điển hình |
| --- | --- | --- |
| `this.field` | Truy cập field của current object theo quy tắc tìm tên | Instance method/constructor/instance initializer |
| `super.field` | Truy cập field superclass bị che hoặc muốn chỉ rõ | Instance context của subclass |
| `this.method()` | Gọi instance method trên current object; vẫn có dynamic dispatch nếu overridable | Instance context |
| `super.method()` | Gọi superclass implementation thích hợp | Instance context của subclass |
| `this(args)` | Ủy quyền cho constructor khác **cùng class** | Constructor, theo vị trí Java 17 cho phép |
| `super(args)` | Gọi constructor của **direct superclass** | Constructor, theo vị trí Java 17 cho phép |
| `ClassName.staticMethod()` | Gọi static method | Nơi access hợp lệ |
| `InterfaceName.super.method()` | Chọn default method cụ thể của superinterface trong ngữ cảnh hợp lệ | Implementing class hoặc interface thích hợp |

**Không dùng `super` như một local variable hoặc standalone object expression**:

~~~java
// Object other = super; // Không hợp lệ
// System.out.println(super); // Không hợp lệ
~~~

Nếu cần object hiện tại để truyền parameter, dùng `this` ở instance context hợp lệ. Nếu cần gọi method của superclass, dùng `super.method(...)`; đừng tưởng `super` là tham chiếu đến một object Parent độc lập.

### 2.1. Một object Child có cả state khai báo ở Parent và Child

~~~java
class Base {
    private final String id;

    Base(String id) {
        this.id = id;
    }

    String id() {
        return id;
    }
}

class Derived extends Base {
    private final int version;

    Derived(String id, int version) {
        super(id);
        this.version = version;
    }
}
~~~

`Derived` object chứa phần state của superclass `Base.id` và field `Derived.version`. `super(id)` khởi tạo phần Base trước khi constructor Derived hoàn tất. Không phải một biến `Base` được tự tạo thêm bên trong Derived.

## 3. `super(...)` gọi constructor lớp cha trực tiếp

Khi subclass có constructor, nó phải đi qua **constructor chain** hợp lệ. Dạng tường minh:

~~~java
class Parent {
    Parent(int id) {
        System.out.println("Parent " + id);
    }
}

class Child extends Parent {
    Child(int id) {
        super(id);
        System.out.println("Child " + id);
    }
}
~~~

Lời gọi `new Child(5)` sẽ in:

~~~text
Parent 5
Child 5
~~~

**`super(id)` dùng constructor của class được đặt ngay sau `extends`**, không lựa chọn tùy ý constructor ở class ông/bà. Constructor Parent của ví dụ nhận một `int`; compiler áp dụng quy tắc overload resolution để chọn constructor phù hợp với arguments.

### 3.1. Constructors không được kế thừa

`class Child extends Parent` không có nghĩa Child tự “thừa hưởng” constructor `Parent(int)` để caller có thể dùng `new Child(5)` nếu Child chưa tự khai báo constructor thích hợp. Constructors thuộc class khai báo chúng, không phải instance methods được kế thừa.

~~~java
class Parent {
    Parent(int code) {
    }
}

class Child extends Parent {
    Child(int code) {
        super(code);
    }
}
~~~

Đoạn trên hợp lệ. Nếu Child không khai báo constructor, compiler sẽ cố tạo default constructor của Child với lời gọi superclass constructor không tham số. Vì Parent chỉ có `Parent(int)`, phiên bản Child không khai báo constructor sẽ **không biên dịch**.

### 3.2. Vì sao phải gọi constructor lớp cha?

Superclass có trách nhiệm khởi tạo state và bảo vệ invariants của chính nó. Ví dụ Parent cần một identifier hợp lệ:

~~~java
class Person {
    private final String name;

    Person(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name rỗng");
        }
        this.name = name;
    }

    public final String name() {
        return name;
    }
}
~~~

Một Employee subclass muốn tạo object hợp lệ phải cung cấp dữ liệu cần thiết:

~~~java
class Employee extends Person {
    private final int staffNumber;

    Employee(String name, int staffNumber) {
        super(name);
        if (staffNumber <= 0) {
            throw new IllegalArgumentException("Staff number sai");
        }
        this.staffNumber = staffNumber;
    }
}
~~~

Superclass tự validate/gán `name`; subclass tự validate/gán `staffNumber`. Đây là **phân chia trách nhiệm** phù hợp hơn việc subclass cố trực tiếp sửa private field của Parent.

## 4. `super()` ngầm định khi không viết constructor invocation

Trong Java 17, nếu constructor không bắt đầu bằng lời gọi tường minh `this(...)` hoặc `super(...)`, compiler sẽ đưa vào một lời gọi **`super()` ngầm định** theo các quy tắc liên quan.

~~~java
class Parent {
    Parent() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    Child() {
        System.out.println("Child");
    }
}
~~~

Về hiệu ứng constructor chaining, `Child()` gọi `Parent()` trước khi thực thi body của nó. Không có nghĩa compiler tự sinh constructor Parent nếu superclass thiếu constructor không tham số.

### 4.1. Constructor không tham số có thể không tồn tại

~~~java
class Parent {
    Parent(String name) {
    }
}

class BrokenChild extends Parent {
    // Compiler không tạo được implicit super().
}
~~~

Đoạn `BrokenChild` **không biên dịch**: Parent có một constructor nhận String nhưng không có constructor không tham số. Constructor mặc định mà compiler cố sinh cho BrokenChild sẽ cần `super()` không hợp lệ.

Cách sửa:

~~~java
class WorkingChild extends Parent {
    WorkingChild(String name) {
        super(name);
    }
}
~~~

Hai ví dụ là fragments minh họa độc lập; trong tệp thật bạn chỉ giữ phiên bản hợp lệ.

### 4.2. Superclass constructor có thể không truy cập được

Ngay cả khi Parent có constructor không tham số, nếu constructor đó là `private` và Child không nằm trong trường hợp access thích hợp, Child cũng không được gọi nó tùy ý.

~~~java
class Parent {
    private Parent() {
    }
}

// class Child extends Parent { } // Không truy cập được Parent()
~~~

Dùng `protected` constructor khi thiết kế class làm base cho subclasses, hoặc công bố factory/composition nếu không định hỗ trợ subclassing.

## 5. Java 17: `this(...)` hoặc `super(...)` phải là lời gọi constructor đầu tiên

Trong **Java 17**, explicit constructor invocation phải nằm ở **vị trí câu lệnh đầu tiên** của constructor body khi được sử dụng:

~~~java
class Child extends Parent {
    Child(String name) {
        super(name);
        // Từ đây mới thực hiện những câu lệnh body khác.
    }
}
~~~

Không được viết:

~~~java
class Child extends Parent {
    Child(String name) {
        // System.out.println("Start");
        // super(name); // Không hợp lệ Java 17: không phải câu lệnh đầu tiên
    }
}
~~~

Chú thích minh họa lỗi đã được comment. Cũng không được đặt hai explicit constructor invocations trong cùng constructor:

~~~java
// Child() {
//     this("A");
//     super("A"); // Không hợp lệ
// }
~~~

**Đặc biệt:** một số phiên bản Java sau Java 17 có thay đổi ngôn ngữ liên quan tới statements trước explicit constructor invocation. Bài này cố định **Java 17+ về những ví dụ tương thích Java 17**, nên áp dụng quy tắc Java 17 ở đây; đừng tự suy diễn cho các phiên bản mới nếu chưa kiểm tra language level thực tế của dự án.

### 5.1. `this(...)` và `super(...)` chọn hai đích khác nhau

~~~java
class Base {
    Base(String name) {
    }
}

class Child extends Base {
    Child() {
        this("anonymous");
    }

    Child(String name) {
        super(name);
    }
}
~~~

`Child()` gọi constructor `Child(String)`, sau đó `Child(String)` gọi `Base(String)`. Đây là **constructor chaining** giúp tập trung initialization/validation thay vì lặp lại các phép gán final fields trong mọi overload.

### 5.2. Tránh vòng đệ quy constructor invocation

~~~java
class Wrong {
    Wrong() {
        this(1);
    }

    Wrong(int n) {
        this();
    }
}
~~~

Đoạn này **không biên dịch** do recursive constructor invocation. Compiler không cho phép tạo chuỗi constructor `A → B → A` vô hạn để thay cho việc khởi tạo superclass.

## 6. Lời gọi `super(...)` phải dùng arguments hợp lệ trước khi superclass initialization

Khi đặt `super(expression)` trong subclass constructor, Java cần đánh giá arguments để chọn/cung cấp dữ liệu cho constructor cha. Trong **Java 17**, bạn không thể tự do dùng `this`, instance field của object đang xây dựng hoặc ordinary instance method trên current object trước superclass constructor.

Sai về ý định/cú pháp:

~~~java
class Parent {
    Parent(String value) {
    }
}

class Child extends Parent {
    private String name = "Child";

    Child() {
        // super(this.name);       // Không hợp lệ Java 17
        // super(makeName());      // Không hợp lệ nếu makeName là instance method
        super("Child");
    }

    String makeName() {
        return name;
    }
}
~~~

Field initializer `name = "Child"` của Child **chưa chạy** trước constructor Parent. Nếu cố lấy instance state Child để tính argument, đó là lệch thứ tự khởi tạo.

### 6.1. Dùng constructor parameters và static helper

~~~java
class Parent {
    private final String id;

    Parent(String id) {
        this.id = id;
    }
}

class Child extends Parent {
    Child(String raw) {
        super(normalize(raw));
    }

    private static String normalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        return raw.trim();
    }
}
~~~

`normalize` là static helper, không cần current Child object, nên phù hợp để tính dữ liệu đưa vào `super(...)`. Nếu normalize ném exception, quá trình construction thất bại trước khi Parent constructor được gọi.

**Thực hành tốt:** truyền **parameters, constants hoặc kết quả của helper không phụ thuộc state chưa khởi tạo**. Để superclass tự thiết lập invariant của nó.

## 7. Chương trình hoàn chỉnh: `super(...)` trong nhiều tầng constructor

Tạo tệp **`SuperConstructorDemo.java`**:

~~~java
public class SuperConstructorDemo {
    static class Person {
        private final String name;

        Person(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Name rỗng");
            }
            this.name = name;
            System.out.println("Person(" + name + ")");
        }

        public final String name() {
            return name;
        }
    }

    static class Employee extends Person {
        private int level = initializeLevel();
        private final int number;

        private int initializeLevel() {
            System.out.println("Employee field initializer");
            return 1;
        }

        Employee(String name, int number) {
            super(name);
            if (number <= 0) {
                throw new IllegalArgumentException("Number sai");
            }
            this.number = number;
            System.out.println("Employee(" + number + ")");
        }

        public final String summary() {
            return name() + "#" + number + ",level=" + level;
        }
    }

    static final class Manager extends Employee {
        Manager(String name, int number) {
            super(name, number);
            System.out.println("Manager constructor");
        }
    }

    public static void main(String[] args) {
        Manager manager = new Manager("Lan", 7);
        System.out.println("Ready = " + manager.summary());
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 SuperConstructorDemo.java
java SuperConstructorDemo
~~~

**Stdout chính xác:**

~~~text
Person(Lan)
Employee field initializer
Employee(7)
Manager constructor
Ready = Lan#7,level=1
~~~

**Diễn giải thứ tự:**

1. `new Manager("Lan", 7)` bắt đầu xây dựng object có runtime class Manager.
2. `Manager(...)` gọi `super(name, number)`, tức `Employee(String,int)`.
3. `Employee(...)` gọi `super(name)`, tức `Person(String)`.
4. `Person` khởi tạo field `name`, validate input rồi in `Person(Lan)`.
5. Khi Person constructor hoàn tất, phần khởi tạo instance của Employee thực hiện field initializer `initializeLevel()`, in dòng tương ứng rồi gán `level=1`.
6. Body của Employee constructor validate `number`, gán final field rồi in `Employee(7)`.
7. Manager constructor body in `Manager constructor`.
8. Caller chỉ nhận Manager object sau khi toàn bộ constructor chain kết thúc bình thường; `summary()` lúc đó đọc được state đã khởi tạo.

**Không có ba objects riêng Person, Employee, Manager.** Đó là **một Manager object** được khởi tạo qua ba mức superclass chain.

### 7.1. Nếu constructor cha ném exception?

Nếu Person constructor ném `IllegalArgumentException`, code sẽ **không** tiếp tục đến Employee field initializer, Employee constructor body hay Manager constructor body trong ví dụ. Một lời gọi constructor thất bại không trả object khởi tạo hoàn chỉnh cho caller.

### 7.2. Nếu subclass có nhiều constructors?

Một constructor có thể gọi `this(...)` để ủy quyền, nhưng chuỗi cuối cùng vẫn cần đường hợp lệ đến constructor superclass. `this(...)` không phải cách bỏ qua `super(...)` hoặc khởi tạo Parent state hai lần.

## 8. `super.method()`: gọi implementation từ superclass

Khi subclass override một instance method, lời gọi `this.method()` hoặc `method()` có thể chạy subclass implementation theo dynamic dispatch. Nếu code **muốn gọi phần hành vi superclass**, nó có thể dùng `super.method()`:

~~~java
class Parent {
    String greeting() {
        return "Hello";
    }
}

class Child extends Parent {
    @Override
    String greeting() {
        return super.greeting() + ", Java";
    }
}
~~~

Với `new Child().greeting()`, kết quả là `"Hello, Java"`.

Ở đây:

- `Child.greeting()` là overriding implementation.
- `super.greeting()` chỉ rõ method superclass thay vì gọi lại `Child.greeting()`.
- Nếu viết `return greeting() + ", Java";` trong Child.greeting, lời gọi có thể liên tục gọi lại chính override (đệ quy không có điểm dừng) và gây `StackOverflowError`.
- `super.greeting()` thực hiện trên cùng receiver Child object, không tạo Parent mới.

### 8.1. Có cần lúc nào cũng gọi `super.method()` khi override không?

**Không.** Java không bắt buộc overriding method phải gọi superclass implementation. Tùy hợp đồng:

- Override **thay thế hoàn toàn** hành vi: có thể không gọi `super`.
- Override **mở rộng** hành vi: thường gọi `super.method()` rồi làm thêm việc.
- Override muốn **bổ sung kiểm tra trước hoặc sau**: cần xem thứ tự xử lý, side effects và exceptions.
- Nếu superclass method quản lý invariant hoặc lifecycle bắt buộc, subclass phải tuân theo documented contract; đôi khi API nên đánh dấu entry point `final` và chỉ mở protected hooks thay vì kỳ vọng subclasses nhớ gọi `super`.

**Quy tắc thiết kế:** gọi `super` vì nó đúng hợp đồng của API, không phải vì một “nghi thức” bắt buộc trong mọi override.

## 9. Mẫu mở rộng hành vi mà vẫn giữ phần cha

Ví dụ lớp cha xử lý dữ liệu chuẩn, lớp con thêm metadata:

~~~java
class Report {
    String render() {
        return "Core report";
    }
}

class DetailedReport extends Report {
    @Override
    String render() {
        String base = super.render();
        return base + " / details";
    }
}
~~~

`new DetailedReport().render()` trả `"Core report / details"`.

### 9.1. Nên gọi `super` trước hay sau hành vi riêng?

Không có một thứ tự đúng cho mọi domain:

~~~java
@Override
void execute() {
    validateSpecialInput();
    super.execute();
    afterExecute();
}
~~~

Đây là **method fragment** minh họa, cần các methods tương ứng trong class. Nếu validation trước `super.execute()` có thể ném exception, superclass action sẽ không chạy. Nếu `super.execute()` ném exception, `afterExecute()` cũng không chạy trừ khi có `finally` hoặc handling thích hợp.

**Đối với cleanup/resource**, không nên tự động gọi `super.close()` theo bất kỳ thứ tự nào không dựa trên documented contract. Nên xem superclass có quản lý tài nguyên không, có yêu cầu idempotency không và exception handling thế nào.

### 9.2. `super` không phải cách “gọi method cha rồi tự động ghép hai kết quả”

Giá trị trả về của `super.method()` phải được xử lý tường minh. Nếu method là `void`, bạn chỉ gọi nó; nếu trả String/object, bạn có thể lưu kết quả, thay đổi hoặc trả thẳng theo ý nghĩa API.

Khi override có covariant return type, kết quả vẫn phải tuân thủ return type compatibility theo quy tắc Java.

## 10. Chương trình hoàn chỉnh: dynamic dispatch và `super.method()`

Tạo tệp **`SuperMethodDemo.java`**:

~~~java
public class SuperMethodDemo {
    static class Base {
        String kind() {
            return "base";
        }

        String describe() {
            return "Base[" + kind() + "]";
        }
    }

    static final class Child extends Base {
        @Override
        String kind() {
            return "child";
        }

        @Override
        String describe() {
            return "Child<" + super.describe() + ">";
        }

        String compareKinds() {
            return super.kind() + "/" + this.kind();
        }
    }

    public static void main(String[] args) {
        Base ref = new Child();
        Child child = (Child) ref;

        System.out.println("Description = " + ref.describe());
        System.out.println("Kinds = " + child.compareKinds());
        System.out.println("Runtime = "
                + ref.getClass().getSimpleName());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SuperMethodDemo.java
java SuperMethodDemo
~~~

**Stdout chính xác:**

~~~text
Description = Child<Base[child]>
Kinds = base/child
Runtime = Child
~~~

**Điều gì xảy ra?**

1. `Base ref = new Child()` là upcasting, không tạo object Base mới.
2. `ref.describe()` là virtual instance method call; runtime class Child khiến Java chọn `Child.describe()`.
3. Child.describe gọi `super.describe()` để thực hiện **Base.describe()` trên cùng Child object**.
4. **Trong Base.describe(), lời gọi `kind()` vẫn là virtual call**. Receiver vẫn là Child object, nên Java chọn `Child.kind()`, trả `"child"`. Vì thế Base.describe trả `"Base[child]"`.
5. Child.describe bao kết quả bằng `Child<...>`.
6. `super.kind()` trong Child.compareKinds chọn `Base.kind()`, trả `"base"`.
7. `this.kind()` là virtual call và trả `"child"`.
8. `ref.getClass()` trả runtime class Child, không phải compile-time type Base của biến ref.

**Đặc biệt quan trọng:** `super.describe()` chọn Base.describe ở **điểm vào lời gọi**, nhưng **không khóa mọi method call bên trong Base.describe vào Base**. Những virtual calls phát sinh bên trong vẫn có thể dispatch tới subclass override.

## 11. Vì sao `super.method()` không gọi lại cùng override vô hạn?

Với code:

~~~java
class Child extends Parent {
    @Override
    void run() {
        super.run();
    }
}
~~~

`super.run()` không được xử lý như `this.run()` để dispatch ngay tới Child.run một lần nữa. Nó xác định superclass implementation phù hợp theo luật Java, nên có thể giúp mở rộng behavior mà không tự gọi đệ quy trực tiếp.

Nhưng điều đó **không** bảo đảm superclass method không bao giờ **gián tiếp** gọi một overridable method khác mà Child đã override. Ví dụ Parent.run() có thể gọi `hook()`, và nếu Child.hook() lại gọi Child.run() thì call graph vẫn có khả năng đệ quy. Phải xem toàn bộ call path, không chỉ cú pháp `super` tại một dòng.

### 11.1. Có thể gọi `super.method()` ngoài overriding method không?

Có, nếu hợp lệ về access và method resolution. Chẳng hạn Child có method `displayBase()`, không override bất kỳ method nào, nhưng muốn gọi `super.describe()` từ instance context:

~~~java
class Child extends Parent {
    String displayBase() {
        return super.describe();
    }
}
~~~

Dạng này chỉ hợp lệ khi superclass khai báo/cung cấp `describe()` có thể truy cập từ Child và return type phù hợp. Không bắt buộc method đang viết phải có cùng tên với method được gọi.

## 12. `super.field`: truy cập field bị ẩn bởi khai báo lớp con

Fields trong Java **không override theo dynamic dispatch**. Nếu Parent và Child khai báo field cùng tên, Child field có thể **hide** Parent field, tạo hai field khác nhau trong **cùng object**.

~~~java
class Parent {
    protected String label = "P";
}

class Child extends Parent {
    private String label = "C";

    String both() {
        return this.label + "/" + super.label;
    }
}
~~~

Trong Child.both():

- `this.label` chọn field khai báo trong Child.
- `super.label` chọn field khai báo trong superclass Parent.
- Không có một object Parent riêng; chúng là hai fields được khai báo trong một inheritance chain và tồn tại trong Child instance.

### 12.1. Trường hợp dùng field hiding cần cân nhắc kỹ

Field hiding hợp lệ nhưng dễ gây hiểu nhầm:

~~~java
Parent ref = new Child();
System.out.println(ref.label);
~~~

`ref.label` được chọn theo **compile-time type Parent** của `ref`, không theo runtime Child object. Đây là khác biệt quan trọng với instance method overriding. Nếu muốn hành vi polymorphic, nên dùng method có contract rõ hơn là cố dùng field hiding.

**Khuyến nghị:** không chủ động khai báo field trùng tên với superclass chỉ để “thay giá trị của Parent”. Thường nên dùng private fields + protected/public methods có validation, hoặc constructor parameters khi subclass cần chọn state superclass.

## 13. Chương trình hoàn chỉnh: `super.field` và field hiding

Tạo tệp **`SuperFieldDemo.java`**:

~~~java
public class SuperFieldDemo {
    static class Parent {
        protected String code = "P";

        String parentCode() {
            return code;
        }
    }

    static final class Child extends Parent {
        private String code = "C";

        String bothCodes() {
            return this.code + "/" + super.code;
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        Parent ref = child;

        System.out.println("Parent ref field = " + ref.code);
        System.out.println("Parent method = " + ref.parentCode());
        System.out.println("Child both = " + child.bothCodes());
        System.out.println("Same object = " + (ref == child));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SuperFieldDemo.java
java SuperFieldDemo
~~~

**Stdout chính xác:**

~~~text
Parent ref field = P
Parent method = P
Child both = C/P
Same object = true
~~~

Lý giải:

1. `ref` có compile-time type Parent nên `ref.code` chọn `Parent.code`.
2. `Parent.parentCode()` được kế thừa; body đọc `code` khai báo trong Parent, trả P.
3. `Child.bothCodes()` gọi cả `this.code` (Child field C) và `super.code` (Parent field P).
4. Cả `child` lẫn `ref` là tham chiếu tới **cùng một Child object**, cho nên so sánh identity trả true.

### 13.1. Tại sao không nên dùng `super.field` để sửa private field?

Nếu Parent khai báo `private String code`, Child **không thể** viết `super.code` chỉ vì có quan hệ extends. `super` không bỏ qua visibility. Để Child tác động theo một hợp đồng được kiểm soát, Parent có thể cung cấp `protected final` method thích hợp, constructor parameter hoặc public API, thay vì làm lộ field.

## 14. `super` và access modifiers

Một subclass chỉ truy cập được superclass member nếu Java access rules cho phép. `super` **không phải cơ chế phá `private`**, package boundaries hay JPMS module encapsulation.

| Superclass member | `super` có thể dùng? | Ghi chú |
| --- | --- | --- |
| `public` instance method | Có, khi class/member accessible | Thường dùng để mở rộng override |
| `protected` instance method | Có trong subclass context phù hợp | Đặc biệt lưu ý package khác và receiver rules |
| Package-private member | Chỉ nếu access theo package hợp lệ | Không tự công khai xuyên package |
| `private` field/method | Không, từ subclass không được truy cập trực tiếp | Dùng controlled API nếu cần |
| `final` instance method | Có thể gọi nếu accessible | Nhưng subclass không được override method đó |
| Static method | Nên gọi qua `DeclaringClass.method()` | Static hiding, không phải instance overriding |
| Constructor | Dùng `super(args)` nếu accessible | Không được kế thừa như instance method |

### 14.1. `protected` không đồng nghĩa `public`

Giả sử Parent nằm ở package `model`, Child ở package `app`. Child có thể dùng protected instance member từ context subclass đúng quy tắc, nhưng không được tùy ý truy cập member đó qua **mọi Parent object**.

Ví dụ hai tệp:

**`model/Base.java`**

~~~java
package model;

public class Base {
    protected int value = 10;

    protected void check() {
        System.out.println(value);
    }
}
~~~

**`app/Derived.java`**

~~~java
package app;

public class Derived extends model.Base {
    public int readOwnInheritedValue() {
        return super.value;
    }

    public void runBaseCheck() {
        super.check();
    }

    // public int readAnyBase(model.Base other) {
    //     return other.value; // Không hợp lệ chỉ vì Derived extends Base
    // }
}
~~~

Đây là **minh họa cấu trúc package**, không phải một trong các chương trình chạy độc lập. Nếu build, đặt tệp đúng thư mục packages và bảo đảm các modules/exports tương thích khi dùng JPMS.

### 14.2. `private` superclass constructor

Nếu Parent có private constructor, chỉ các ngữ cảnh được access rules cho phép mới gọi được. Một class Child khác không thể giả định `super()` truy cập private constructor, dù nó ghi `extends Parent`.

Nếu không muốn class bị kế thừa, một `final class` hoặc thiết kế constructor visibility thích hợp làm ý định rõ hơn.

## 15. `super` và việc override method `final`

Một superclass có thể khóa một method bằng `final`:

~~~java
class Base {
    public final String id() {
        return "fixed";
    }
}

class Child extends Base {
    // public String id() { return "changed"; } // Lỗi: override final method
}
~~~

Child không được override `id()`, nhưng có thể **gọi method đó** thông qua inherited method call `id()`, `this.id()` hoặc cú pháp `super.id()` trong instance context nếu hợp lệ. Cú pháp `super.id()` không biến final method thành overridable.

Khi bạn muốn subclass mở rộng một workflow nhưng không thay validation bắt buộc, có thể thiết kế một `final template method` trong Base gọi các protected hooks phù hợp ở giai đoạn an toàn. Đó thường tốt hơn việc hy vọng mọi subclass override nhớ gọi `super.validate()` đúng cách.

## 16. Static method hiding không giống `super.method()` cho override

Nếu Parent và Child có static methods cùng tên/chữ ký phù hợp:

~~~java
class Parent {
    static String category() {
        return "Parent";
    }
}

class Child extends Parent {
    static String category() {
        return "Child";
    }
}
~~~

Đây là **static method hiding**, không phải instance overriding. Không có current object receiver dùng cho dynamic dispatch của static method.

Nên gọi rõ ràng:

~~~java
System.out.println(Parent.category());
System.out.println(Child.category());
~~~

Đừng xem `super.category()` là công cụ polymorphism cần thiết cho static methods. Trong code hiện đại, truy cập static member bằng **tên class khai báo** làm ý nghĩa rõ hơn.

### 16.1. `super` không hợp lệ trong static context của subclass

~~~java
class Child extends Parent {
    static void test() {
        // super.toString(); // Không hợp lệ: super trong static context
    }
}
~~~

Static method không có current Child instance, nên không thể dùng `super` để gọi instance method của superclass trên current object. Nếu cần xử lý Parent/Child object, hãy truyền receiver tường minh vào static method hoặc đổi thiết kế thành instance method.

### 16.2. `super` và `this` trong nested classes

Trong một **non-static inner class**, `this` là inner object và một cú pháp `Outer.this` có thể chỉ enclosing outer object trong ngữ cảnh hợp lệ. `super` trong instance method của inner class liên quan đến superclass của **inner class**, không tự động trở thành superclass của Outer.

Một **static nested class** vẫn có instance methods và có `this`/`super` của chính nested instance, dù nó không có enclosing Outer instance ngầm định.

Nếu không thực sự cần nested inheritance, thường nên giữ ví dụ `super` trên top-level classes hoặc static nested class để dễ nhận diện superclass.

## 17. `super.method()` vẫn dùng receiver thực tế, không gọi method trên “bản sao cha”

Khi Child override một instance method:

~~~java
class Base {
    protected int count;

    void increase() {
        count++;
    }

    int current() {
        return count;
    }
}

class Child extends Base {
    @Override
    void increase() {
        super.increase();
        super.increase();
    }
}
~~~

Với `Child child = new Child(); child.increase();`, field `count` của phần Base trong **chính Child object** tăng lên 2. Không có một `new Base()` ngầm diễn ra ở lời gọi `super.increase()`. Một subclass có thể truy cập state của Base qua protected field/method theo quy tắc phù hợp.

### 17.1. Không có `super.super.method()`

Java không cho viết:

~~~java
// super.super.method(); // Không hợp lệ
~~~

để “nhảy qua” superclass trực tiếp tới grandparent. Với `GrandParent → Parent → Child`, nếu muốn tái sử dụng hành vi grandparent, thiết kế các phương thức có contract phù hợp để Parent và Child phối hợp, chẳng hạn protected method hoặc composition. `super.method()` chọn implementation theo luật resolution từ superclass chain, không phải một cú pháp tùy ý chọn mọi ancestor.

### 17.2. Nếu superclass không khai báo method nhưng kế thừa nó thì sao?

`super.method()` có thể phân giải đến inherited implementation thích hợp từ một superclass xa hơn theo các quy tắc lookup. Không nhất thiết direct superclass có body method do chính nó viết.

~~~java
class Root {
    String label() {
        return "Root";
    }
}

class Middle extends Root {
}

class Leaf extends Middle {
    String baseLabel() {
        return super.label();
    }
}
~~~

`Leaf.baseLabel()` hợp lệ và nhận `"Root"` dù Middle không khai báo `label()` riêng. Đây **không phải** cú pháp `super.super`; lookup hợp lệ trên inheritance chain tìm method thích hợp.

## 18. `super` trong ba cấp kế thừa

~~~java
class Root {
    String label() {
        return "Root";
    }
}

class Middle extends Root {
    @Override
    String label() {
        return "Middle>" + super.label();
    }
}

class Leaf extends Middle {
    @Override
    String label() {
        return "Leaf>" + super.label();
    }
}
~~~

`new Leaf().label()` trả:

~~~text
Leaf>Middle>Root
~~~

Cách diễn giải:

1. Virtual call chọn Leaf.label.
2. `super.label()` trong Leaf chọn Middle.label.
3. `super.label()` trong Middle chọn Root.label.
4. Các strings được ghép theo stack unwind.

Đây là một ví dụ tốt cho **mở rộng hành vi qua nhiều mức** khi Parent/Middle đã có hợp đồng thích hợp. Nhưng nếu hierarchy sâu khiến ai cũng phải gọi `super` theo thứ tự phức tạp để đúng nghiệp vụ, có thể đã đến lúc xem lại composition hoặc một template method được kiểm soát.

## 19. `super(...)` và `super.method()` khi superclass là abstract

Một **abstract superclass** vẫn có constructor để khởi tạo phần state chung:

~~~java
abstract class Device {
    private final String serial;

    protected Device(String serial) {
        this.serial =
                java.util.Objects.requireNonNull(serial);
    }

    public final String serial() {
        return serial;
    }

    public abstract String kind();
}

class Sensor extends Device {
    Sensor(String serial) {
        super(serial);
    }

    @Override
    public String kind() {
        return "Sensor";
    }
}
~~~

`new Device(...)` không hợp lệ vì Device abstract, nhưng `new Sensor("S1")` hợp lệ nếu toàn bộ constructor chain/abstract method implementation đáp ứng quy tắc.

### 19.1. Không dùng `super.abstractMethod()` nếu không có superclass implementation

Nếu superclass chỉ khai báo:

~~~java
abstract class Parent {
    abstract void work();
}
~~~

Subclass implement `work()` không thể gọi `super.work()` để chạy “implementation của cha” bởi method abstract **không có method body** ở đó.

~~~java
class Child extends Parent {
    @Override
    void work() {
        // super.work(); // Không hợp lệ: abstract method không có body
        System.out.println("Child work");
    }
}
~~~

Nếu muốn tái sử dụng logic chung, superclass nên cung cấp một concrete helper như `protected final void validate()`, hoặc giao behavior cho collaborator.

### 19.2. Constructor abstract superclass không nên gọi abstract hook

Một lỗi thiết kế thường gặp:

~~~java
abstract class Base {
    Base() {
        onReady(); // Có thể dispatch tới Child khi Child chưa khởi tạo
    }

    abstract void onReady();
}
~~~

Khi tạo concrete subclass, JVM vẫn có thể dispatch tới override của Child **trước khi Child fields/constructor body chạy**. `super(...)` không bảo đảm subclass đã sẵn sàng ngay trong superclass constructor. Dành abstract hooks cho giai đoạn sau khi object hoàn tất construction hoặc truyền dữ liệu cần thiết qua constructor arguments.

## 20. `InterfaceName.super.method()`: chọn default method của interface

Bên cạnh class superclass, Java còn có **interfaces với default methods**. Một class implement nhiều interfaces có default method cùng signature có thể cần override để giải quyết xung đột.

Cú pháp:

~~~java
InterfaceName.super.method(arguments)
~~~

là cách chọn một **default method implementation** từ một **superinterface** thích hợp trong ngữ cảnh hợp lệ.

### 20.1. Ví dụ hai default methods trùng tên

~~~java
interface English {
    default String greeting() {
        return "Hello";
    }
}

interface Vietnamese {
    default String greeting() {
        return "Xin chào";
    }
}

class Bilingual implements English, Vietnamese {
    @Override
    public String greeting() {
        return English.super.greeting()
                + " / "
                + Vietnamese.super.greeting();
    }
}
~~~

Nếu class Bilingual không tự giải quyết xung đột, compiler sẽ không thể chọn mặc định một trong hai unrelated default methods. Cú pháp `English.super.greeting()` và `Vietnamese.super.greeting()` làm ý định rõ ràng.

**Khác biệt với `super(...)`:** interface không có constructors như class và không thể tạo bằng `new Interface()`. `English.super.greeting()` là lời gọi default method, **không phải constructor call**.

### 20.2. Khi class method và interface default method cùng tồn tại

Java có các quy tắc ưu tiên, thường được tóm tắt là **class methods thắng interface defaults** trong trường hợp thích hợp. Không tự giả định rằng chỉ cần có default implementation thì Java luôn dùng nó khi superclass đã cung cấp concrete instance method phù hợp.

Nếu muốn chọn rõ default implementation của một superinterface, cần xem quy tắc về direct superinterface, overriding và tính hợp lệ của qualified-super invocation; không phải mọi biểu thức `SomeInterface.super.method()` đều hợp lệ chỉ vì type đó xuất hiện đâu đó trong hierarchy.

## 21. Chương trình hoàn chỉnh: chọn nhiều interface default implementations

Tạo tệp **`InterfaceSuperDemo.java`**:

~~~java
public class InterfaceSuperDemo {
    interface English {
        default String greeting() {
            return "Hello";
        }
    }

    interface Vietnamese {
        default String greeting() {
            return "Xin chào";
        }
    }

    static final class Bilingual
            implements English, Vietnamese {
        @Override
        public String greeting() {
            return English.super.greeting()
                    + " / "
                    + Vietnamese.super.greeting();
        }
    }

    public static void main(String[] args) {
        Bilingual speaker = new Bilingual();

        System.out.println("Combined = " + speaker.greeting());
        System.out.println("English subtype = "
                + (speaker instanceof English));
        System.out.println("Vietnamese subtype = "
                + (speaker instanceof Vietnamese));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 InterfaceSuperDemo.java
java InterfaceSuperDemo
~~~

**Stdout chính xác:**

~~~text
Combined = Hello / Xin chào
English subtype = true
Vietnamese subtype = true
~~~

**Điều cần nhớ:**

- `Bilingual` không extends hai classes; nó implements hai interfaces.
- Mỗi interface khai báo default method `greeting()`.
- Bilingual override method để giải quyết xung đột và chọn hai implementations bằng `InterfaceName.super.method()`.
- `speaker instanceof English` và `speaker instanceof Vietnamese` đều true vì object hiện thực cả hai contracts.
- Đây không phải multiple inheritance of class state/constructors: không có `English()` hoặc `Vietnamese()` để gọi bằng `super(...)`.

## 22. Interface `extends` interface cũng không có constructor `super(...)`

Một interface có thể extends một hoặc nhiều interfaces khác:

~~~java
interface Readable {
    String read();
}

interface Writable {
    void write(String value);
}

interface ReadWrite extends Readable, Writable {
}
~~~

`ReadWrite` là subinterface của cả Readable và Writable. Nhưng **interface không có instance constructor**. Không đặt `super()` trong interface để khởi tạo các superinterfaces.

Class implement ReadWrite có thể cần hiện thực các abstract methods phù hợp. Nếu các interfaces có default methods, qualified-super syntax liên quan method resolution/default inheritance có thể hữu ích.

**Phân biệt hai chữ `extends`:**

- `class Child extends Parent`: một direct class superclass, constructor chain, class state/method inheritance.
- `interface ChildI extends ParentI1, ParentI2`: nhiều superinterfaces, không có constructor chain của interface.
- `class Concrete implements Interface`: quan hệ subtype interface, có thể cùng lúc extends một class hợp lệ.

## 23. `super` không bỏ qua nguyên tắc một direct superclass

Một class Java chỉ có **một direct superclass class**. Vì vậy `super(...)` không có nghĩa “chọn bất kỳ class cha nào trong danh sách”:

~~~java
// class Child extends A, B { } // Java không cho đa kế thừa class
~~~

Nếu Child cần kết hợp hai behaviors độc lập, có thể:

- Extends một superclass nếu thật sự là subtype.
- Implements nhiều interfaces.
- Dùng **composition** để giữ references tới collaborators.
- Gọi methods của collaborators thay vì cố dùng nhiều `super` constructor calls.

Một class chứa `private final Engine engine` là quan hệ **has-a**, không phải `super` relation. Constructor Child/Car có thể tạo/inject Engine, nhưng đó là khởi tạo object component tường minh, không phải một class superclass mới.

## 24. Error handling khi gọi `super(...)`

Superclass constructor có thể ném exception nếu input không hợp lệ:

~~~java
class Base {
    Base(int capacity) {
        if (capacity < 1) {
            throw new IllegalArgumentException("Capacity sai");
        }
    }
}

class Child extends Base {
    Child(int capacity) {
        super(capacity);
        System.out.println("Child ready");
    }
}
~~~

Khi `new Child(0)`:

- Parent/Base constructor được gọi trước Child body.
- Base ném `IllegalArgumentException`.
- Child body không chạy, nên không in `Child ready`.
- Lời gọi `new Child(0)` hoàn tất bất thường.

Nếu superclass constructor khai báo checked exception, subclass constructor phải xử lý theo **Java constructor invocation/throws rules**, thường là khai báo `throws` thích hợp; không thể đặt `try/catch` bên ngoài một lệnh `super(...)` trong constructor body để bao nó như ordinary call đứng sau dòng khác trong Java 17.

### 24.1. Một constructor đúng không đồng nghĩa object luôn invariant-safe

Nếu constructor superclass gọi overridable method dựa trên state Child chưa khởi tạo, cả constructor chain vẫn có thể **biên dịch** nhưng gặp bug ở runtime. `super(...)` chỉ bảo đảm khởi tạo theo trình tự, **không bảo đảm mọi hook đa hình được gọi trong constructor đều an toàn**.

## 25. Chương trình hoàn chỉnh: xử lý lỗi từ constructor cha

Tạo tệp **`SuperValidationDemo.java`**:

~~~java
public class SuperValidationDemo {
    static class Capacity {
        private final int limit;

        Capacity(int limit) {
            if (limit < 1) {
                throw new IllegalArgumentException("Limit phải dương");
            }
            this.limit = limit;
            System.out.println("Base accepted " + limit);
        }

        int limit() {
            return limit;
        }
    }

    static final class LimitedQueue extends Capacity {
        private final String name;

        LimitedQueue(String name, int limit) {
            super(limit);
            this.name = java.util.Objects.requireNonNull(
                    name, "name");
            System.out.println("Queue ready " + name);
        }

        String summary() {
            return name + "/" + limit();
        }
    }

    public static void main(String[] args) {
        LimitedQueue valid = new LimitedQueue("jobs", 3);
        System.out.println("Summary = " + valid.summary());

        try {
            new LimitedQueue("bad", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 SuperValidationDemo.java
java SuperValidationDemo
~~~

**Stdout chính xác:**

~~~text
Base accepted 3
Queue ready jobs
Summary = jobs/3
Rejected = Limit phải dương
~~~

`new LimitedQueue("bad",0)` không in `Queue ready bad` vì `super(0)` ném exception trước khi Child constructor body chạy. Parent vẫn kiểm soát validation `limit`, còn subclass kiểm soát `name` nếu constructor cha hoàn tất.

**Lưu ý:** ở tình huống exception, không có một Queue object hoàn tất construction được trả cho caller. Điều đó không đồng nghĩa mọi side effect đã xảy ra trong một constructor lỗi đều tự rollback; tránh đăng ký `this`, ghi resource không thể rollback hoặc publish event quá sớm.

## 26. `super.method()` với checked exceptions và override contracts

Nếu superclass method khai báo checked exception:

~~~java
class ReaderBase {
    String read() throws java.io.IOException {
        return "base";
    }
}
~~~

Subclass override muốn dùng `super.read()` phải tuân thủ checked exception handling:

~~~java
class ReaderChild extends ReaderBase {
    @Override
    String read() throws java.io.IOException {
        return super.read().toUpperCase(
                java.util.Locale.ROOT);
    }
}
~~~

Nếu method override muốn **không** khai báo checked exception, có thể bắt exception và xử lý phù hợp trong body. Nhưng không được âm thầm làm mất semantics nếu hợp đồng yêu cầu caller phải biết lỗi IO.

### 26.1. Visibility và return type khi override

Overriding method không được giảm visibility (ví dụ Parent public → Child protected) và return type phải phù hợp. Với reference types, Java cho phép **covariant return type**.

Cú pháp `super.method()` không giúp né các quy tắc override đó. Compiler vẫn kiểm tra declaration Child có hợp lệ so với superclass method hay không.

### 26.2. Overloading và chọn superclass overload

`super.print(argument)` là lời gọi method, nên compiler vẫn áp dụng overload resolution dựa trên **compile-time types** của argument.

~~~java
class Base {
    String print(Object value) {
        return "Object";
    }

    String print(String value) {
        return "String";
    }
}

class Child extends Base {
    String sample(Object value) {
        return super.print(value);
    }
}
~~~

`new Child().sample("hello")` trả `"Object"` vì formal parameter `value` trong `sample` có compile-time type Object. Runtime String object không buộc overload resolution chọn print(String).

**Không nhầm** lựa chọn overload ở compile time với override dispatch ở runtime. Trong trường hợp `super.print(...)`, việc chọn superclass implementation còn chịu quy tắc qualified-super invocation.

## 27. Khi nào nên gọi `super.method()` trong code thực tế?

### 27.1. Mở rộng hành vi nhưng giữ hợp đồng superclass

Ví dụ override `toString()` muốn bổ sung state Child sau khi gọi `super.toString()`:

~~~java
class Base {
    @Override
    public String toString() {
        return "Base";
    }
}

class Child extends Base {
    @Override
    public String toString() {
        return super.toString() + "(Child)";
    }
}
~~~

`new Child().toString()` là `"Base(Child)"`. Đây là use case đơn giản và có thể hợp lý khi superclass `toString()` đã công bố cách biểu diễn thích hợp.

### 27.2. Bổ sung xử lý trước/sau một bước superclass quản lý

Ví dụ một framework có protected hook mà subclass phải gọi `super.hook()` để giữ phần cleanup/base behavior. Chỉ làm vậy nếu **documented contract yêu cầu hoặc semantics thật sự phù hợp**. Một framework khác có thể định nghĩa hook độc lập và không muốn gọi `super`.

### 27.3. Truy cập hành vi bị override để kết hợp

Nếu Child muốn dùng cả Base version lẫn Child-specific logic:

~~~java
@Override
String label() {
    String parentPart = super.label();
    return parentPart + "-" + childPart;
}
~~~

Đây là method fragment; `childPart` cần thuộc class thực tế. Mục tiêu là **tái sử dụng một hành vi đã được định nghĩa**, không cố bắt mọi lớp con “luôn super-call”.

### 27.4. Khi không nên gọi `super.method()`

- Override cần thay thế toàn bộ algorithm theo contract.
- Superclass implementation có side effects không phù hợp trong subclass.
- Gọi super hai lần gây xử lý trùng hoặc double charge.
- Lệnh super đóng tài nguyên/đổi trạng thái trước khi Child hoàn tất việc cần làm.
- Subclass dùng `super` chỉ để “tái sử dụng code”, nhưng không thực sự là subtype hợp lệ.
- Cần behavior của một collaborator khác, không phải superclass behavior; dùng composition.

## 28. Khi nào `super.field` là dấu hiệu nên cải thiện thiết kế?

Dùng `super.field` để phân biệt fields bị hide có thể cần khi phân tích legacy code, nhưng thường không nên tạo hierarchy cố tình trùng tên field.

~~~java
class Base {
    protected int size = 10;
}

class Child extends Base {
    int size = 20;

    int both() {
        return size + super.size;
    }
}
~~~

Có hai fields `size`, không phải Child “đổi giá trị Base.size”. Khi class Base có method đọc `size` của nó, nó vẫn có thể thấy 10 trong khi Child code thấy 20. Điều này dễ làm invariant rối.

Thường rõ ràng hơn nếu:

- Chỉ giữ **một field** ở Base, truyền giá trị qua `super(size)`.
- Base để field private và cung cấp controlled setter/protected method nếu cần thay.
- Child sử dụng tên field khác nếu thông tin khác semantics.
- Dùng composition nếu dữ liệu không thực sự thuộc cùng subtype contract.

**`super.field` là công cụ cú pháp, không tự biến field hiding thành một pattern nên dùng.**

## 29. `super` không cho phép sửa mọi điều superclass cấm

Một số nhận định sai:

- “Có `super` thì đọc được private field Parent” → **Sai**.
- “Có `super` thì gọi được private Parent constructor từ bất kỳ subclass” → **Sai**.
- “Có `super` thì override được final method” → **Sai**.
- “Có `super` thì bỏ qua abstract method chưa có body được” → **Sai**.
- “Có `super` thì gọi được constructor của grandparent trực tiếp bằng `super.super()`” → **Sai**.
- “Có `super` thì subclass được phép phá invariants Parent” → **Sai** về thiết kế, và access controls vẫn được compiler áp dụng.
- “Có `super` trong static method thì sẽ tạo instance Parent tự động” → **Sai**.

Hãy nhớ `super` được compiler kiểm tra theo **ngữ cảnh khai báo, inheritance relationship, accessibility và member-resolution rules**. Nó không phải một đặc quyền vượt tất cả hạn chế của Java.

## 30. `super(...)` và final fields

Blank final instance field của superclass thường phải được constructor superclass hoặc instance initializer hợp lệ gán đúng một lần trên các đường khởi tạo hoàn tất bình thường:

~~~java
class Base {
    private final String id;

    Base(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    String id() {
        return id;
    }
}

class Child extends Base {
    private final String tag;

    Child(String id, String tag) {
        super(id);
        this.tag = java.util.Objects.requireNonNull(tag);
    }
}
~~~

`super(id)` để Base tự gán `Base.id`. Child không nên và không thể hợp lệ gán lại một final field đã được Parent khởi tạo. Child có trách nhiệm gán `Child.tag`.

### 30.1. Không sửa lỗi definite assignment bằng cách đẩy field Parent thành protected

Nếu Child cần cho Parent biết ID, hãy **truyền qua constructor**, không đổi `private final String id` thành `protected String id` rồi cho Child gán tự do. Cách đó làm suy yếu invariant của Parent và có thể phá vỡ immutability.

### 30.2. Static final không được khởi tạo bằng constructor

`static final` thuộc class, có quy tắc initializer khác. Gọi `super(...)` không có nghĩa subclass có thể gán blank static final field của superclass từ constructor. Superclass phải quản lý static state đúng theo quy tắc Java.

## 31. Chú ý đặc biệt với `Object`

Mọi class thông thường không ghi superclass tường minh có `java.lang.Object` là direct superclass theo quy tắc Java. Constructor của Object tham gia chuỗi khởi tạo instance.

~~~java
class Simple {
    Simple() {
        super(); // Hợp lệ: gọi Object()
    }
}
~~~

Không cần viết `super()` tường minh trong mọi constructor. Java có thể thêm lời gọi implicit super() khi phù hợp.

Với methods của Object:

- `toString()` thường có thể override; Child có thể gọi `super.toString()` để lấy implementation superclass.
- `equals(Object)` và `hashCode()` có contracts quan trọng; kế thừa/override cần giữ symmetry, transitivity và consistency.
- `getClass()` là final, không được override, và khi gọi trên Child object vẫn trả runtime class Child.
- `wait()`, `notify()` và `notifyAll()` liên quan monitor synchronization; không dùng `super` như cách bypass thread synchronization.

### 31.1. `super.toString()` không bảo đảm bỏ qua mọi subclass behavior

Nếu direct superclass đã override `toString()` và bên trong gọi một virtual hook, lời gọi `super.toString()` từ Child đi vào superclass toString, nhưng hook có thể tiếp tục dispatch đến Child. Điều này tương tự ví dụ `Base.describe()` gọi `kind()` trước đó.

Nếu cần log trạng thái trong constructor, tránh gọi `toString()` đa hình trên object chưa khởi tạo hoàn chỉnh.

## 32. `super` và sealed/final/record/enum trong Java 17

### 32.1. Final class

Nếu superclass là `final`, không thể khai báo subclass bằng `extends`, nên không có ngữ cảnh subclass hợp lệ để dùng `super(...)` đối với class final ấy.

~~~java
final class Closed {
}

// class Child extends Closed {} // Không hợp lệ
~~~

Một **final subclass** vẫn có superclass (nếu không phải Object) và có thể gọi `super(...)` trong constructor. Modifier `final` ở subclass chỉ cấm **subclasses tiếp theo**, không cấm nó kế thừa superclass.

### 32.2. Sealed class

Java 17 cho phép `sealed` class giới hạn direct permitted subclasses:

~~~java
sealed class Base permits ChildA, ChildB {
    Base(String id) {
    }
}

final class ChildA extends Base {
    ChildA() {
        super("A");
    }
}

final class ChildB extends Base {
    ChildB() {
        super("B");
    }
}
~~~

`ChildA` và `ChildB` vẫn dùng `super(...)` như class inheritance bình thường. Sealed kiểm soát **ai được extends**, không thay ngữ nghĩa cơ bản của superclass constructor.

### 32.3. Records

Một record của Java 17 implicitly final và kế thừa `java.lang.Record` theo ngữ nghĩa language. Bạn không được viết một record declaration với `extends CustomParent`, cũng không thể dùng record như subclass tùy ý trong hierarchy class.

~~~java
record Point(int x, int y) {
}
~~~

Record constructor có rules riêng về components, compact/canonical constructors; **không viết một `super(...)` tường minh để gọi custom superclass constructor** như subclass class thông thường. Record có thể implements interfaces với default methods phù hợp.

### 32.4. Enums

Một enum type có đặc điểm constructor/superclass riêng liên quan `java.lang.Enum`. Các enum constructors không được tự viết `super(...)` để gọi constructor của Enum theo cú pháp tùy ý:

~~~java
enum Mode {
    FAST, SAFE
}
~~~

Đây không phải một subclass thông thường mà developer tự gọi `super(...)` tới `Enum`. Compiler và ngôn ngữ quản lý construction của enum constants theo những quy tắc đặc biệt.

## 33. Lỗi thường gặp và cách sửa

| Lỗi / nhầm lẫn | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Không có constructor Parent không tham số, Child không ghi `super(args)` | Implicit `super()` không tồn tại hoặc không accessible | Khai báo constructor Child gọi constructor Parent phù hợp |
| Viết code trước `super(...)` trong Java 17 | Explicit constructor invocation phải là câu lệnh đầu tiên | Tính input qua parameters/static helper; đặt `super(...)` đầu body |
| Dùng cả `this(...)` và `super(...)` trong một constructor | Hai explicit constructor invocations không cùng tồn tại trong body như vậy | Chain `this(...)` sang constructor đích gọi `super(...)` |
| Viết `super.super.method()` | Java không có cú pháp chọn grandparent tùy ý | Thiết kế API/protected helper phù hợp |
| Gọi `super.privateField` | `super` không phá private access | Dùng controlled accessor/constructor argument |
| Gọi `super.abstractMethod()` | Không có method body để gọi | Tách concrete base helper, hoặc tự implement method |
| Dùng `super` trong static method | Không có current instance receiver | Truyền object rõ ràng; dùng tên class cho static |
| Nghĩ `super(...)` tạo Parent object riêng | Một Child object có phần superclass state | Hiểu lại constructor chain |
| Gọi `this.method()` thay `super.method()` trong override muốn dùng base behavior | Dynamic dispatch có thể gọi lại override | Dùng `super.method()` khi contract cần implementation cha |
| Nghĩ `super.method()` vô hiệu hóa dispatch mọi calls bên trong base body | Virtual calls sâu hơn vẫn dispatch theo runtime receiver | Kiểm tra call graph/invariant |
| Gọi `super.method()` trong mọi override như nghi thức | Không phải override nào cũng cần base behavior | Dựa vào contract/hook docs |
| Dùng `super.field` để giả lập override state | Fields bị hiding, không dispatch như methods | Private state + controlled APIs |
| Gọi `super(...)` với tham chiếu instance field Child chưa khởi tạo | Java 17 cấm và state chưa sẵn sàng | Dùng constructor parameters/static helper |
| Parent constructor gọi overridable hook | Child override chạy khi Child fields chưa ready | Không gọi virtual hooks trong constructors |
| Nhầm `InterfaceName.super.defaultMethod()` với constructor | Interface không có constructors | Chỉ dùng để chọn default implementation |
| Sử dụng `ClassName.super.method()` tùy ý | Qualified super có ngữ cảnh/lexical enclosing rules riêng | Học và dùng đúng cú pháp chỉ khi cần |
| Cố extends final superclass | `final` cấm subclassing | Composition/interface hoặc class được phép extends |
| Dùng `super.method()` trên API không accessible | Access rules vẫn áp dụng | Chỉnh design/access phù hợp |
| Parent constructor ném exception nhưng Child vẫn mong body chạy | Construction không hoàn tất bình thường | Validate input, xử lý exception ở caller |
| Cố gọi `super(...)` trên record/enum như normal class | Record/enum có construction rules đặc biệt | Dùng constructor/canonical/compact enum syntax phù hợp |

## 34. Phương pháp suy luận khi nhìn thấy `super`

Khi gặp một dòng code dùng `super`, hãy hỏi theo thứ tự:

1. **Dấu sau `super` là dấu ngoặc `(...)` hay dấu chấm?**
   - `super(...)`: constructor invocation.
   - `super.member`: member access/invocation.
2. **Đang ở constructor hay instance method?**
   - Constructor invocation thuộc constructor.
   - Member super access cần instance context phù hợp.
3. **Class có direct superclass nào?**
   - Xác định class sau `extends`, hoặc `Object` khi thích hợp.
4. **Nếu là constructor:** constructor superclass nào được overload resolution chọn?
5. **Có constructor không tham số không?** Đừng mặc định Parent có `Parent()`.
6. **Có access hợp lệ không?** Private/package/protected/JPMS vẫn quan trọng.
7. **Nếu là method:** Child đang override method đó hay chỉ muốn gọi inherited implementation?
8. **Nếu có method override:** có cần thực thi superclass behavior theo contract không?
9. **Nếu là field:** Parent và Child có hide field cùng tên không?
10. **Nếu là interface default:** `InterfaceName.super` có hợp lệ trong declaration hiện tại không?
11. **Nếu code trong constructor:** superclass/hook có dựa vào state Child chưa khởi tạo không?
12. **Nếu code chạy đa luồng:** gọi super không tự đồng bộ shared mutable state.
13. **Nếu có nhiều cấp inheritance:** `super` đi tới method được resolved theo superclass chain; không có `super.super` tùy ý.
14. **Nếu có exceptions:** constructor chain có thể dừng trước Child body.
15. **Nếu code đang quá phụ thuộc vào `super`:** có nên thay phần behavior độc lập bằng composition?

Cách đặt câu hỏi này giúp phân biệt một **lỗi compile-time về cú pháp/access**, một **lỗi runtime về trạng thái khởi tạo**, và một **vấn đề thiết kế về hợp đồng kế thừa**.

## 35. Bài tập tự kiểm tra có đáp án

**Câu 1.** `super(...)` trong constructor Child gọi constructor của class nào?

**Đáp án:** Direct superclass của Child theo class inheritance chain. Nó không tạo object superclass riêng.

**Câu 2.** Child không viết explicit `super(...)` hay `this(...)` trong constructor Java 17 thì sao?

**Đáp án:** Compiler cố dùng implicit `super()` theo quy tắc. Nếu superclass không có constructor không tham số accessible, code không biên dịch.

**Câu 3.** Constructor Parent có `Parent(int)` nhưng không có `Parent()`. Child có default constructor tự sinh được không?

**Đáp án:** Không nếu default constructor sẽ cần `super()` không tồn tại/access không hợp lệ. Child cần constructor gọi `super(int)`.

**Câu 4.** Một constructor Child Java 17 có được in log trước `super(args)` không?

**Đáp án:** Không nếu `super(args)` là explicit constructor invocation đặt sau lệnh log. Theo quy tắc Java 17, nó phải đứng đầu constructor body.

**Câu 5.** Khi nào dùng `this(args)` thay `super(args)`?

**Đáp án:** Khi constructor muốn ủy quyền cho một constructor khác cùng class. Constructor đích cuối cùng vẫn tham gia superclass initialization.

**Câu 6.** Có thể viết hai lệnh `super()` trong một constructor Child không?

**Đáp án:** Không. Constructor invocation tuân thủ cú pháp một lời gọi tường minh thích hợp; superclass initialization không được lặp tùy ý.

**Câu 7.** Nếu Parent constructor ném exception, Child constructor body có chạy tiếp không?

**Đáp án:** Không. Construction kết thúc bất thường nếu exception không được xử lý theo cách hợp lệ, và `new Child()` không trả một Child object hoàn tất.

**Câu 8.** `super.method()` có tạo một Parent object mới không?

**Đáp án:** Không. Nó gọi superclass implementation trên cùng receiver object hiện tại theo quy tắc Java.

**Câu 9.** Trong Child override `greet()`, vì sao `super.greet()` thường khác `this.greet()`?

**Đáp án:** `super.greet()` chọn superclass implementation. `this.greet()` dùng normal instance invocation và có thể dispatch tới Child.greet, dẫn đến gọi lại chính override.

**Câu 10.** Nếu Base.describe() gọi overridable `kind()`, `super.describe()` từ Child có bắt `kind()` chạy Base.kind() không?

**Đáp án:** Không. Bên trong Base.describe, `kind()` vẫn có thể dynamic dispatch tới Child.kind dựa trên runtime object.

**Câu 11.** `super.field` có thể truy cập private field Parent không?

**Đáp án:** Không. Private access rules vẫn áp dụng; dùng superclass API có kiểm soát nếu cần.

**Câu 12.** `this.code` và `super.code` có thể cho hai giá trị khác nhau không?

**Đáp án:** Có nếu Child và Parent khai báo **hai fields cùng tên**; đó là field hiding, không phải polymorphic overriding.

**Câu 13.** Parent có final method, Child có thể viết override rồi gọi `super.finalMethod()` không?

**Đáp án:** Không được override final method. Child vẫn có thể gọi inherited final method nếu access hợp lệ, nhưng không thể thay implementation.

**Câu 14.** `super.method()` có thể gọi một abstract method của Parent chưa có body không?

**Đáp án:** Không nếu method được chọn là abstract và không có implementation hợp lệ để gọi.

**Câu 15.** Có thể viết `super.toString()` trong static method Child không?

**Đáp án:** Không. Static method không có current instance receiver để gọi superclass instance implementation.

**Câu 16.** Java có cú pháp `super.super.method()` không?

**Đáp án:** Không. Dùng inheritance API hợp lệ, hoặc thiết kế helper/delegation phù hợp.

**Câu 17.** Nếu Middle không khai báo `label()` mà kế thừa Root.label(), Leaf extends Middle có thể gọi `super.label()` không?

**Đáp án:** Có nếu lookup/access hợp lệ; nó có thể chọn inherited implementation từ Root theo superclass chain.

**Câu 18.** `super.method()` có được dùng trong method không override method nào không?

**Đáp án:** Có thể, miễn ngữ cảnh instance và method resolution/access hợp lệ. Không bắt buộc method hiện tại cùng tên.

**Câu 19.** Tại sao `super(...)` không giúp bỏ qua validation của superclass?

**Đáp án:** Chính superclass constructor được gọi để thực hiện phần initialization/validation của superclass. Không có cơ chế bỏ qua một constructor chain hợp lệ bằng cú pháp `super` bình thường.

**Câu 20.** `English.super.greeting()` có gọi constructor English không?

**Đáp án:** Không. Interface không có constructors; cú pháp này chọn default method implementation ở ngữ cảnh hợp lệ.

**Câu 21.** Vì sao class implements hai interfaces có cùng default `greeting()` thường phải override?

**Đáp án:** Hai unrelated defaults gây conflict mà Java không tự chọn một cách tùy ý; class cần giải quyết method theo quy tắc.

**Câu 22.** `super.method()` có làm một method static thành polymorphic không?

**Đáp án:** Không. Static methods được resolved/hiding theo rules riêng và nên được gọi qua tên class khai báo.

**Câu 23.** Khi class Child là final, nó còn gọi `super(...)` được không?

**Đáp án:** Có. Final trên Child cấm class khác extends Child, không cấm Child extends một superclass hợp lệ.

**Câu 24.** Một record Java 17 có thể `extends Person` rồi gọi `super(name)` không?

**Đáp án:** Không. Record có superclass/constructor rules riêng và implicitly final, không được extends arbitrary class.

**Câu 25.** `super.field` có nên dùng làm thiết kế chính để hai classes cùng lưu state tên giống nhau?

**Đáp án:** Thường không. Field hiding dễ gây nhầm. Dùng một field có ownership rõ, constructor arguments hoặc controlled API.

**Câu 26.** Nếu gọi `super.method()` trong constructor Child, có luôn an toàn không?

**Đáp án:** Không. Method được gọi có thể phụ thuộc vào state chưa khởi tạo hoặc gọi overridable hooks khác. Cần xem call graph và thứ tự khởi tạo.

**Câu 27.** Subclass ở package khác có thể dùng mọi `protected` field trên mọi superclass object không?

**Đáp án:** Không. Java có các quy tắc protected access/receiver type đặc biệt qua package boundaries.

**Câu 28.** Nếu override muốn **thay thế hoàn toàn** hành vi Parent, có bắt buộc gọi `super.method()` không?

**Đáp án:** Không. Chỉ gọi nếu superclass contract hoặc ý nghĩa business thực sự yêu cầu.

**Câu 29.** Tại sao `super(...)` không tương đương `new Parent(...)`?

**Đáp án:** `super(...)` tham gia khởi tạo phần superclass của current Child object. `new Parent(...)` tạo một object Parent độc lập.

**Câu 30.** Khi nào nên chọn composition thay vì lạm dụng `super`?

**Đáp án:** Khi muốn tái sử dụng một capability hoặc phối hợp một collaborator nhưng Child không thật sự là subtype của Parent, hoặc hierarchy quá phụ thuộc vào các super-calls và hooks khó bảo trì.

## 36. Checklist khi viết code có `super`

Trước khi hoàn tất code, kiểm tra:

1. **Quan hệ subtype có hợp lý không?** Đừng dùng `extends` chỉ để lấy một helper.
2. **Direct superclass đúng chưa?** `super(...)` chỉ đến superclass chain phù hợp.
3. **Constructor Parent nào được chọn?** Có overload tương thích và accessible?
4. **Có implicit `super()` không?** Nếu thiếu explicit invocation, Parent() có tồn tại?
5. **Đã đặt `super(...)` đầu body theo Java 17 chưa?**
6. **Có dùng `this(...)` không?** Không dùng đồng thời một `super(...)` tường minh trong cùng delegating body.
7. **Arguments của `super(...)` có phụ thuộc instance state Child chưa khởi tạo không?** Tránh.
8. **Parent constructor có validate và có thể ném exception không?** Child body chỉ chạy khi chain thành công.
9. **Có gọi overridable method từ superclass constructor không?** Tránh dùng state Child chưa sẵn sàng.
10. **Child có override method thật không?** Dùng `@Override` để compiler kiểm tra.
11. **Override có cần superclass behavior không?** Gọi `super.method()` theo contract, không máy móc.
12. **Có đệ quy vô tình do gọi `this.method()` trong override không?** Xem call path.
13. **`super.method()` có gọi virtual hook sâu hơn không?** Không tự coi Base body là non-polymorphic hoàn toàn.
14. **`super.field` có đang che dấu field hiding không?** Xem lại representation/invariants.
15. **Member của Parent có accessible không?** `super` không bỏ qua private/protected/package/module restrictions.
16. **Có default methods xung đột từ interfaces không?** Dùng `InterfaceName.super.method()` khi hợp lệ.
17. **Có static member không?** Gọi qua tên class để tránh nhầm dynamic dispatch.
18. **Class đang là record/enum/sealed/final không?** Tôn trọng quy tắc extension/construction đặc thù.
19. **Có checked exceptions từ super-call không?** Xử lý theo constructor/method signature.
20. **Nếu inheritance ngày càng phức tạp, composition có rõ hơn không?** Cân nhắc trước khi mở thêm subclass.

## Kết luận

`super` là công cụ cốt lõi của Java class inheritance, nhưng cần phân biệt **hai vai trò hoàn toàn khác nhau**:

- **`super(arguments)`**: gọi constructor của superclass trực tiếp để khởi tạo phần superclass state của **cùng một object subclass**. Trong Java 17, explicit constructor invocation có vị trí bắt buộc và không được dùng để bỏ qua constructor/access/initialization rules.
- **`super.member` / `super.method()`**: truy cập superclass member hoặc gọi superclass implementation thích hợp, thường hữu ích khi subclass muốn **mở rộng method đã override**, hoặc cần phân biệt field bị hide.

Một lời gọi `super.method()` không tạo parent object mới, cũng **không khóa toàn bộ virtual dispatch** trong những method mà superclass implementation tiếp tục gọi. `super` không truy cập được private members tùy ý, không cho gọi abstract method không có body, không chạy trong static context như receiver instance, và không thay thế cú pháp `InterfaceName.super.method()` dành cho default methods.

Khi dùng `super`, hãy đặt trọng tâm vào **hợp đồng subtype, trách nhiệm khởi tạo, visibility, thứ tự lifecycle và tính đúng của overriding**. Nếu logic cần tái sử dụng chỉ là một collaborator độc lập, **composition** thường thích hợp hơn việc tạo thêm lớp con để có thể gọi `super`.
